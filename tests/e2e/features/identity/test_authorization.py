"""Autorização e não-vazamento pelo entrypoint real — CA20, CA21, CA22, CA25, CA26.

Os dois testes mais importantes deste arquivo comparam **respostas entre si**, em
vez de comparar cada resposta com um valor esperado. É a única forma de testar
indistinguibilidade: um teste que só assere "403" passa verde tanto na versão
segura quanto na que vaza a causa no corpo.
"""

from datetime import timedelta
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, text

from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import create_app
from tests.e2e.features.identity.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    auth,
    corpo_tenant,
    fazer_login,
    login_do_dono,
)
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e


async def _montar_tenant(
    client: AsyncClient, caixa: RecordingEmailSender, admin_tokens: dict, nome: str
) -> dict:
    """Cria restaurante + owner + unidade, e devolve os ids e o login do owner.

    O owner entra pelo convite (ADR 0.0.0018): define a senha pelo link e faz login.
    """
    email_owner = f"dono-{nome.lower()}@x.com"
    restaurante_id = (
        await client.post(
            f"{API}/restaurants",
            json=corpo_tenant(nome, email_owner),
            headers=auth(admin_tokens),
        )
    ).json()["id"]
    owner = await login_do_dono(client, caixa, email_owner)
    unidade_id = (
        await client.post(
            f"{API}/restaurants/{restaurante_id}/units",
            json={"name": f"Unidade {nome}"},
            headers=auth(owner),
        )
    ).json()["id"]
    return {"restaurante": restaurante_id, "owner": owner, "unidade": unidade_id}


# ---------------------------------------------------------------------------
# CA22 — o oráculo de enumeração cross-tenant
# ---------------------------------------------------------------------------


async def test_unidade_inexistente_e_de_outro_tenant_sao_indistinguiveis(
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
) -> None:
    """CA22 — o teste central de não-vazamento desta Stage.

    Um `manager` do tenant A itera `unit_id` em `POST /users`. Se "não existe" e
    "existe, em outro tenant" produzissem respostas diferentes, ele enumeraria os
    ids de unidade de **todos** os restaurantes da plataforma — atravessando
    exatamente a fronteira que o BC inteiro existe para isolar.

    A comparação é **byte a byte** de propósito: igualar só o status deixaria
    passar a versão que vaza a causa no corpo, e igualar só o corpo deixaria
    passar a que vaza no status.

    **O ator importa tanto quanto o oráculo.** O teste sonda com dois: o
    `manager` (unit-scoped) e o `owner` (tenant-scoped). Só o segundo chega à
    defesa que o teste nomeia — o primeiro é barrado antes, por escopo. Ver o
    comentário no corpo.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, caixa_de_entrada, admin, "Alfa")
    tenant_b = await _montar_tenant(client, caixa_de_entrada, admin, "Beta")

    # Um manager do tenant A, vinculado à unidade de A.
    await client.post(
        f"{API}/users",
        json={
            "email": "gerente@alfa.com",
            "password": SENHA_PADRAO,
            "role": "manager",
            "unit_ids": [tenant_a["unidade"]],
        },
        headers=auth(tenant_a["owner"]),
    )
    manager = await fazer_login(client, "gerente@alfa.com")

    def _tentativa(unit_id: str) -> dict:
        return {
            "email": f"sonda-{unit_id}@alfa.com",
            "password": SENHA_PADRAO,
            "role": "employee",
            "unit_ids": [unit_id],
        }

    inexistente = await client.post(
        f"{API}/users", json=_tentativa("unidade-que-nao-existe"), headers=auth(manager)
    )
    de_outro_tenant = await client.post(
        f"{API}/users", json=_tentativa(tenant_b["unidade"]), headers=auth(manager)
    )
    do_proprio_tenant_sem_vinculo = await client.post(
        f"{API}/restaurants/{tenant_a['restaurante']}/units",
        json={"name": "Segunda unidade de Alfa"},
        headers=auth(tenant_a["owner"]),
    )
    outra_unidade_de_a = do_proprio_tenant_sem_vinculo.json()["id"]
    nao_vinculada = await client.post(
        f"{API}/users", json=_tentativa(outra_unidade_de_a), headers=auth(manager)
    )

    # O MESMO sondar, agora pelo `owner` — o ator que realmente exercita a defesa.
    # O `manager` acima é unit-scoped e por isso é barrado antes, por
    # `UnitScopeRequiredError`: os três casos dele viram 403 por um motivo que não
    # é a tradução `UnitNotFoundError` → `UnitNotVisibleError` que o teste nomeia.
    # O `owner` é tenant-scoped, passa daquela checagem e chega à regra 4b — sem
    # ela, colhe o oráculo completo: 404 "unidade não encontrada" para a
    # inexistente e 422 "isolamento de tenant violado: ... unidade do tenant 'B'"
    # para a de outro tenant, que ainda vaza o UUID do tenant dono (§5 regra 10).
    owner_inexistente = await client.post(
        f"{API}/users",
        json=_tentativa("outra-unidade-que-nao-existe"),
        headers=auth(tenant_a["owner"]),
    )
    owner_de_outro_tenant = await client.post(
        f"{API}/users", json=_tentativa(tenant_b["unidade"]), headers=auth(tenant_a["owner"])
    )

    respostas = (
        inexistente,
        de_outro_tenant,
        nao_vinculada,
        owner_inexistente,
        owner_de_outro_tenant,
    )
    assert {r.status_code for r in respostas} == {HTTPStatus.FORBIDDEN}, (
        f"status divergentes: {[(r.status_code, r.text) for r in respostas]}"
    )
    assert len({r.content for r in respostas}) == 1, (
        "os cinco casos devem ser indistinguíveis byte a byte — "
        f"corpos: {[r.text for r in respostas]}"
    )
    # E nenhum deles nomeia o tenant dono da unidade sondada.
    for resposta in respostas:
        assert tenant_b["restaurante"] not in resposta.text


async def test_owner_de_outro_tenant_nao_enxerga_o_restaurante(
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
) -> None:
    """O tenant alvo vem do path; um owner alheio não passa da checagem de escopo.

    E o corpo é o mesmo de qualquer 403 — então tampouco revela se o restaurante
    do path existe.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, caixa_de_entrada, admin, "Alfa")
    tenant_b = await _montar_tenant(client, caixa_de_entrada, admin, "Beta")

    invasao = await client.post(
        f"{API}/restaurants/{tenant_a['restaurante']}/units",
        json={"name": "Filial Invasora"},
        headers=auth(tenant_b["owner"]),
    )
    inexistente = await client.post(
        f"{API}/restaurants/restaurante-que-nao-existe/units",
        json={"name": "Filial Fantasma"},
        headers=auth(tenant_b["owner"]),
    )

    assert invasao.status_code == HTTPStatus.FORBIDDEN
    assert inexistente.status_code == HTTPStatus.FORBIDDEN
    assert invasao.content == inexistente.content


# ---------------------------------------------------------------------------
# CA20 / CA21 — escalada e ator removido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel_alvo", ["platform_admin", "owner"])
async def test_manager_nao_escala_privilegio(
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
    papel_alvo: str,
) -> None:
    """CA20/CA14 — "não se concede o que não se detém", contra o banco real."""
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant = await _montar_tenant(client, caixa_de_entrada, admin, "Alfa")
    await client.post(
        f"{API}/users",
        json={
            "email": "gerente@alfa.com",
            "password": SENHA_PADRAO,
            "role": "manager",
            "unit_ids": [tenant["unidade"]],
        },
        headers=auth(tenant["owner"]),
    )
    manager = await fazer_login(client, "gerente@alfa.com")

    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "promovido@alfa.com",
            "password": SENHA_PADRAO,
            "role": papel_alvo,
            "unit_ids": [tenant["unidade"]],
        },
        headers=auth(manager),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_nem_o_platform_admin_cria_outro_platform_admin(
    client: AsyncClient, admin_semeado: User
) -> None:
    """CA20 — a garantia fail-closed vale inclusive para o papel mais alto.

    `platform_admin` detém `manage_platform` mas **não** `manage_users` ("acesso
    de plataforma não é acesso de restaurante"), então também não passa. A raiz de
    confiança nasce fora da API, por semeadura — registrado em §13 com Stage
    candidata para um comando de seed.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)

    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "segundo-admin@plataforma.com",
            "password": SENHA_PADRAO,
            "role": "platform_admin",
        },
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_token_valido_de_usuario_removido_e_401(
    client: AsyncClient, admin_semeado: User, engine: Engine
) -> None:
    """CA21 — inversão deliberada do mapa global.

    O token continua criptograficamente válido; o que sumiu é o sujeito. Isso é
    credencial inválida (401), não recurso ausente (404) — um 404 aqui responderia
    "não encontrado" a um problema de sessão, e confundiria cliente e operador.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    with engine.begin() as conexao:
        conexao.execute(text("DELETE FROM sessions"))
        conexao.execute(text("DELETE FROM users WHERE email = :e"), {"e": ADMIN_EMAIL})

    resposta = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Fantasma", "dono-fantasma@x.com"),
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# CA26 — corpo constante por faixa
# ---------------------------------------------------------------------------


async def test_corpos_de_403_sao_constantes_entre_causas_diferentes(
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
) -> None:
    """CA26 — três causas distintas de 403, um só corpo.

    Sem isto, o `detail` seria `str(exc)` e `TenantNotVisibleError` renderizaria
    "ator do tenant 'A' e alvo no tenant 'B'" — revelando qual tenant é dono do
    recurso, que é pior do que revelar que ele existe.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, caixa_de_entrada, admin, "Alfa")
    tenant_b = await _montar_tenant(client, caixa_de_entrada, admin, "Beta")

    sem_permissao = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("X", "dono-x@x.com"),
        headers=auth(tenant_a["owner"]),
    )
    tenant_alheio = await client.post(
        f"{API}/restaurants/{tenant_a['restaurante']}/units",
        json={"name": "Y"},
        headers=auth(tenant_b["owner"]),
    )
    escalada = await client.post(
        f"{API}/users",
        json={"email": "novo@x.com", "password": SENHA_PADRAO, "role": "platform_admin"},
        headers=auth(tenant_a["owner"]),
    )

    respostas = (sem_permissao, tenant_alheio, escalada)
    assert {r.status_code for r in respostas} == {HTTPStatus.FORBIDDEN}
    assert len({r.content for r in respostas}) == 1
    for resposta in respostas:
        assert tenant_a["restaurante"] not in resposta.text
        assert tenant_b["restaurante"] not in resposta.text


async def test_corpos_de_401_sao_constantes_entre_causas_diferentes(
    client: AsyncClient, admin_semeado: User
) -> None:
    """CA26 — três EXCEÇÕES diferentes da faixa 401, um só corpo.

    **A escolha dos cenários é o teste.** Uma versão anterior usava "sem header",
    "esquema Basic" e "token adulterado" — os três levantam a mesma
    `InvalidAccessTokenError`, com a mesma mensagem, então a igualdade byte a
    byte era garantida pela construção da exceção e não pela regra de corpo
    constante. O teste passava mesmo com a regra revertida para `str(exc)`: era
    teatro.

    Estes três atingem exceções distintas, com mensagens distintas:
    `InvalidCredentialsError` ("credenciais inválidas"),
    `InvalidAccessTokenError` ("token de acesso inválido") e
    `InvalidRefreshTokenError` ("token de renovação inválido"). Reverter o corpo
    constante agora reprova aqui.
    """
    tokens = await fazer_login(client, ADMIN_EMAIL)

    credencial_errada = await client.post(
        f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "errada"}
    )
    token_forjado = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("X", "dono-x@x.com"),
        headers={"Authorization": f"Bearer {tokens['access_token']}adulterado"},
    )
    refresh_desconhecido = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": "nunca-foi-emitido"}
    )

    respostas = (credencial_errada, token_forjado, refresh_desconhecido)
    assert {r.status_code for r in respostas} == {HTTPStatus.UNAUTHORIZED}
    assert len({r.content for r in respostas}) == 1, (
        f"corpos divergentes na faixa 401: {[r.text for r in respostas]}"
    )


async def test_tenant_id_no_corpo_e_descartado(
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
) -> None:
    """CA13 contra o grafo real — a defesa nº 3 do `POST /users`.

    O corpo tenta injetar o tenant de OUTRO restaurante. A resposta é 201 (o
    campo é descartado, não rejeitado) e o usuário nasce no tenant do **ator**.

    Exercitar isto contra o Postgres real, e não só contra fake, importa: é aqui
    que se vê que a linha gravada tem o tenant certo. Um teste que só olhasse o
    corpo da resposta poderia passar com o servidor devolvendo uma coisa e
    gravando outra.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, caixa_de_entrada, admin, "Alfa")
    tenant_b = await _montar_tenant(client, caixa_de_entrada, admin, "Beta")

    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "novo@alfa.com",
            "password": SENHA_PADRAO,
            "role": "employee",
            "unit_ids": [tenant_a["unidade"]],
            "tenant_id": tenant_b["restaurante"],
        },
        headers=auth(tenant_a["owner"]),
    )

    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    assert resposta.json()["tenant_id"] == tenant_a["restaurante"]
    assert resposta.json()["tenant_id"] != tenant_b["restaurante"]
    # E o usuário criado enxerga o tenant de A quando faz login de verdade.
    novo = await fazer_login(client, "novo@alfa.com")
    assert novo["access_token"]


# ---------------------------------------------------------------------------
# CA25 — TTL é configuração
# ---------------------------------------------------------------------------


async def test_ttl_configurado_reflete_na_resposta(
    engine: Engine, database_url: str, admin_semeado: User
) -> None:
    """CA25 — mudar `Settings` muda o comportamento observável da API.

    É o que prova que o TTL não é constante enterrada num use case. Este número é
    a janela de revogação do produto: revogar a sessão corta o refresh na hora, e
    o access sobrevive no máximo isso. Enterrá-lo tornaria a principal alavanca de
    segurança do sistema inalcançável sem deploy.
    """
    settings = Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret_key="segredo-de-teste-e2e-com-32-bytes-ou-mais",
        access_token_ttl_minutes=1,
        refresh_token_ttl_days=1,
    )
    app = create_app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        corpo = await fazer_login(c, ADMIN_EMAIL)

    from datetime import datetime  # noqa: PLC0415

    access_expira = datetime.fromisoformat(corpo["access_token_expires_at"])
    refresh_expira = datetime.fromisoformat(corpo["refresh_token_expires_at"])

    # 1 minuto de access e 1 dia de refresh — bem longe dos defaults (15 min, 14 d).
    assert refresh_expira - access_expira < timedelta(days=1)
    assert access_expira - datetime.now(access_expira.tzinfo) < timedelta(minutes=2)

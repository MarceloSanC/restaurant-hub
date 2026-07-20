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
    fazer_login,
)

pytestmark = pytest.mark.e2e


async def _montar_tenant(client: AsyncClient, admin_tokens: dict, nome: str) -> dict:
    """Cria restaurante + owner + unidade, e devolve os ids e o login do owner."""
    restaurante_id = (
        await client.post(f"{API}/restaurants", json={"name": nome}, headers=auth(admin_tokens))
    ).json()["id"]
    email_owner = f"dono-{nome.lower()}@x.com"
    await client.post(
        f"{API}/restaurants/{restaurante_id}/owners",
        json={"email": email_owner, "password": SENHA_PADRAO},
        headers=auth(admin_tokens),
    )
    owner = await fazer_login(client, email_owner)
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
    client: AsyncClient, admin_semeado: User
) -> None:
    """CA22 — o teste central de não-vazamento desta Stage.

    Um `manager` do tenant A itera `unit_id` em `POST /users`. Se "não existe" e
    "existe, em outro tenant" produzissem respostas diferentes, ele enumeraria os
    ids de unidade de **todos** os restaurantes da plataforma — atravessando
    exatamente a fronteira que o BC inteiro existe para isolar.

    A comparação é **byte a byte** de propósito: igualar só o status deixaria
    passar a versão que vaza a causa no corpo, e igualar só o corpo deixaria
    passar a que vaza no status.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, admin, "Alfa")
    tenant_b = await _montar_tenant(client, admin, "Beta")

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

    respostas = (inexistente, de_outro_tenant, nao_vinculada)
    assert {r.status_code for r in respostas} == {HTTPStatus.FORBIDDEN}
    assert len({r.content for r in respostas}) == 1, (
        "os três casos devem ser indistinguíveis byte a byte — "
        f"corpos: {[r.text for r in respostas]}"
    )


async def test_owner_de_outro_tenant_nao_enxerga_o_restaurante(
    client: AsyncClient, admin_semeado: User
) -> None:
    """O tenant alvo vem do path; um owner alheio não passa da checagem de escopo.

    E o corpo é o mesmo de qualquer 403 — então tampouco revela se o restaurante
    do path existe.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, admin, "Alfa")
    tenant_b = await _montar_tenant(client, admin, "Beta")

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
    client: AsyncClient, admin_semeado: User, papel_alvo: str
) -> None:
    """CA20/CA14 — "não se concede o que não se detém", contra o banco real."""
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant = await _montar_tenant(client, admin, "Alfa")
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
        f"{API}/restaurants", json={"name": "Fantasma"}, headers=auth(admin)
    )

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# CA26 — corpo constante por faixa
# ---------------------------------------------------------------------------


async def test_corpos_de_403_sao_constantes_entre_causas_diferentes(
    client: AsyncClient, admin_semeado: User
) -> None:
    """CA26 — três causas distintas de 403, um só corpo.

    Sem isto, o `detail` seria `str(exc)` e `TenantNotVisibleError` renderizaria
    "ator do tenant 'A' e alvo no tenant 'B'" — revelando qual tenant é dono do
    recurso, que é pior do que revelar que ele existe.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    tenant_a = await _montar_tenant(client, admin, "Alfa")
    tenant_b = await _montar_tenant(client, admin, "Beta")

    sem_permissao = await client.post(
        f"{API}/restaurants", json={"name": "X"}, headers=auth(tenant_a["owner"])
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
    """CA26 — credencial ausente, malformada e inválida respondem igual."""
    tokens = await fazer_login(client, ADMIN_EMAIL)

    sem_header = await client.post(f"{API}/restaurants", json={"name": "X"})
    esquema_errado = await client.post(
        f"{API}/restaurants",
        json={"name": "X"},
        headers={"Authorization": "Basic abc"},
    )
    token_forjado = await client.post(
        f"{API}/restaurants",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {tokens['access_token']}adulterado"},
    )

    respostas = (sem_header, esquema_errado, token_forjado)
    assert {r.status_code for r in respostas} == {HTTPStatus.UNAUTHORIZED}
    assert len({r.content for r in respostas}) == 1


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

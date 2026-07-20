"""Ciclo de vida da sessão pelo entrypoint real — CA1, CA2, CA4, CA5, CA7, CA23.

O que estes testes provam e nenhum teste unitário prova: que o token emitido pela
API é aceito pela API. Nos testes unitários o issuer é o mesmo objeto dos dois
lados do round-trip, então um adapter que assinasse e verificasse de formas
incompatíveis passaria verde. Aqui a assinatura atravessa HTTP e volta.
"""

from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import Engine, text

from restaurant_hub.features.identity.adapters.out.security.jwt_issuer import (
    JwtTokenIssuer,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.shared.infrastructure.config.settings import Settings
from tests.e2e.features.identity.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    auth,
    fazer_login,
)

pytestmark = pytest.mark.e2e


async def test_login_emite_par_de_tokens(client: AsyncClient, admin_semeado: User) -> None:
    """CA1 — o caminho feliz, com argon2 e JWT reais."""
    resposta = await client.post(
        f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": SENHA_PADRAO}
    )

    assert resposta.status_code == HTTPStatus.OK
    corpo = resposta.json()
    assert corpo["access_token"]
    assert corpo["refresh_token"]
    assert corpo["token_type"] == "bearer"
    assert corpo["access_token_expires_at"] < corpo["refresh_token_expires_at"]


async def test_sessao_persiste_o_fingerprint_e_nunca_o_token(
    client: AsyncClient, admin_semeado: User, engine: Engine, settings_e2e: Settings
) -> None:
    """CA1, metade destrutiva — a asserção que só um e2e com banco real faz.

    O ADR 2.2.0001 desenhou a sessão para que um dump do banco **não** devolvesse
    refresh token utilizável. Isso só é verificável olhando a linha gravada: um
    teste de use case com fake provaria apenas que o fake concorda consigo mesmo.
    """
    tokens = await fazer_login(client, ADMIN_EMAIL)
    refresh = tokens["refresh_token"]

    with engine.connect() as conexao:
        gravados = [
            linha[0]
            for linha in conexao.execute(text("SELECT refresh_token_fingerprint FROM sessions"))
        ]

    assert len(gravados) == 1
    fingerprint = gravados[0]
    assert fingerprint != refresh
    assert refresh not in fingerprint
    # E é o fingerprint DAQUELE token — não um valor qualquer que só parece opaco.
    issuer = JwtTokenIssuer(
        secret_key=settings_e2e.jwt_secret_key, algorithm=settings_e2e.jwt_algorithm
    )
    assert issuer.fingerprint(refresh) == fingerprint


@pytest.mark.parametrize(
    ("email", "senha", "cenario"),
    [
        (ADMIN_EMAIL, "senha-errada", "senha-incorreta"),
        ("nao-existe@lugar-nenhum.com", SENHA_PADRAO, "email-inexistente"),
    ],
)
async def test_credencial_invalida_e_401(
    client: AsyncClient, admin_semeado: User, email: str, senha: str, cenario: str
) -> None:
    resposta = await client.post(f"{API}/auth/login", json={"email": email, "password": senha})

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


async def test_as_duas_falhas_de_login_sao_indistinguiveis(
    client: AsyncClient, admin_semeado: User
) -> None:
    """CA2 — senha errada e e-mail inexistente respondem exatamente o mesmo.

    A metade de **tempo** desta defesa (verificar contra `dummy_hash()` quando o
    e-mail não existe) não é observável daqui, porque com adapters reais não há
    espião para contar chamadas. Ela está coberta, e permanece na suíte, em
    `tests/unit/features/identity/application/test_authenticate_user.py`, que
    assere `hasher.verify_args == [(senha, hasher.dummy_hash())]`.
    """
    senha_errada = await client.post(
        f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "errada"}
    )
    email_inexistente = await client.post(
        f"{API}/auth/login", json={"email": "ninguem@x.com", "password": SENHA_PADRAO}
    )

    assert senha_errada.status_code == email_inexistente.status_code
    assert senha_errada.json() == email_inexistente.json()
    assert senha_errada.headers.get("WWW-Authenticate") == email_inexistente.headers.get(
        "WWW-Authenticate"
    )


async def test_refresh_rotaciona_e_invalida_o_anterior(
    client: AsyncClient, admin_semeado: User
) -> None:
    """CA4 — o par novo funciona e o antigo morre."""
    tokens = await fazer_login(client, ADMIN_EMAIL)

    resposta = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert resposta.status_code == HTTPStatus.OK
    novos = resposta.json()
    assert novos["refresh_token"] != tokens["refresh_token"]
    # O access token novo é aceito pelo guard — o round-trip completo.
    protegida = await client.post(f"{API}/restaurants", json={"name": "Teste"}, headers=auth(novos))
    assert protegida.status_code == HTTPStatus.CREATED


async def test_reuso_de_refresh_rotacionado_derruba_todas_as_sessoes(
    client: AsyncClient, admin_semeado: User, engine: Engine
) -> None:
    """CA5 — a detecção de reuso, ponta a ponta e verificada no banco.

    O cenário é o do token roubado: o atacante apresenta um refresh que a vítima
    já rotacionou. A resposta correta não é só recusar — é derrubar **todas** as
    sessões do usuário, porque não se sabe qual das duas partes é a legítima.
    """
    primeira = await fazer_login(client, ADMIN_EMAIL)
    segunda = await fazer_login(client, ADMIN_EMAIL)  # outro "dispositivo"
    rotacionado = (
        await client.post(f"{API}/auth/refresh", json={"refresh_token": primeira["refresh_token"]})
    ).json()

    # O atacante reapresenta o token já rotacionado.
    resposta = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": primeira["refresh_token"]}
    )

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    with engine.connect() as conexao:
        ativas = conexao.execute(
            text("SELECT count(*) FROM sessions WHERE revoked_at IS NULL")
        ).scalar_one()
    assert ativas == 0, "a detecção de reuso deve revogar todas as sessões do usuário"
    # E as sessões das duas pontas realmente morreram.
    for tokens in (segunda, rotacionado):
        recusada = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert recusada.status_code == HTTPStatus.UNAUTHORIZED


async def test_logout_revoga_a_sessao(
    client: AsyncClient, admin_semeado: User, engine: Engine
) -> None:
    """CA7 — 204 e a sessão revogada no banco."""
    tokens = await fazer_login(client, ADMIN_EMAIL)

    resposta = await client.post(
        f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )

    assert resposta.status_code == HTTPStatus.NO_CONTENT
    with engine.connect() as conexao:
        revogadas = conexao.execute(
            text("SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL")
        ).scalar_one()
    assert revogadas == 1


@pytest.mark.parametrize("token", ["token-que-nunca-existiu", ""], ids=["desconhecido", "vazio"])
async def test_logout_e_sempre_204(client: AsyncClient, admin_semeado: User, token: str) -> None:
    """CA7 — sem oráculo: a resposta é a mesma para token que existe e que não.

    Um 404 aqui diria, a quem não tem credencial nenhuma, se um dado valor de
    refresh está registrado.
    """
    resposta = await client.post(f"{API}/auth/logout", json={"refresh_token": token})

    assert resposta.status_code == HTTPStatus.NO_CONTENT


async def test_refresh_apos_logout_e_tratado_como_reuso(
    client: AsyncClient, admin_semeado: User, engine: Engine
) -> None:
    """CA23 — o efeito colateral declarado do logout, fixado como contrato.

    O passo 3 da rotação não sabe **por que** a sessão foi revogada: há um único
    `revoked_at` para logout, rotação e incidente. Então reapresentar um token que
    saiu por logout conta como reuso e derruba as demais sessões do usuário.

    Um cliente correto não faz isso (recebeu 204 e descartou o token), mas um
    retry automático faz. O comportamento erra para o lado seguro; este teste
    existe para que ele não mude sem que ninguém perceba — em especial, para que
    uma Stage futura não "conserte" o passo 3 e, com isso, deixe um token roubado
    sobreviver a um logout.
    """
    celular = await fazer_login(client, ADMIN_EMAIL)
    desktop = await fazer_login(client, ADMIN_EMAIL)
    await client.post(f"{API}/auth/logout", json={"refresh_token": celular["refresh_token"]})

    resposta = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": celular["refresh_token"]}
    )

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    recusada = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": desktop["refresh_token"]}
    )
    assert recusada.status_code == HTTPStatus.UNAUTHORIZED, (
        "a sessão do outro dispositivo também cai — efeito colateral declarado"
    )


async def test_refresh_desconhecido_e_401(client: AsyncClient, admin_semeado: User) -> None:
    resposta = await client.post(f"{API}/auth/refresh", json={"refresh_token": "nunca-foi-emitido"})

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED


async def test_email_malformado_no_login_e_422(client: AsyncClient) -> None:
    """A conversão texto→VO no router é o que faz isto ser erro de domínio.

    Se o schema Pydantic validasse o formato, seria `RequestValidationError` e
    seguiria outro caminho, com outro formato de corpo — e o mapa de status do BC
    deixaria de ser fonte única.
    """
    resposta = await client.post(
        f"{API}/auth/login", json={"email": "nao-e-um-email", "password": "x"}
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

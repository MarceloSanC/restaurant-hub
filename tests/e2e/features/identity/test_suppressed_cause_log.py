"""Issue #26 — a causa dos 401/403 chega ao log pelo entrypoint real.

O teste unitário prova o handler sobre uma app mínima. Este prova o que só a app
montada pelo `create_app` prova: que o handler registrado é o que loga, que o
guard real anota o ator, que a exceção do PyJWT vira causa nomeada — e que o
logger de módulo **está ligado** depois de a fixture `engine` rodar o Alembic
(finding F1 da #6, corrigido na task-01; sem a correção, todo teste daqui
reprovaria por não achar registro algum).

Cada teste compara **duas** respostas: o corpo tem de seguir idêntico, e é o log
— nunca o corpo — que diz qual foi a causa.
"""

import logging
from http import HTTPStatus

import pytest
from httpx import AsyncClient

from restaurant_hub.features.identity.adapters.inbound.http import error_handlers
from restaurant_hub.features.identity.domain.entities.user import User
from tests.e2e.features.identity.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    auth,
    fazer_login,
)

pytestmark = pytest.mark.e2e

_LOGGER = error_handlers.__name__


def _registros(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _LOGGER]


def _campo(registro: logging.LogRecord, nome: str) -> object:
    return registro.__dict__[nome]


async def _owner_de(client: AsyncClient, admin: dict, nome: str) -> tuple[str, dict]:
    """Cria restaurante + owner e devolve o id do restaurante e o login do owner."""
    restaurante = (
        await client.post(f"{API}/restaurants", json={"name": nome}, headers=auth(admin))
    ).json()["id"]
    email = f"dono-{nome.lower()}@x.com"
    await client.post(
        f"{API}/restaurants/{restaurante}/owners",
        json={"email": email, "password": SENHA_PADRAO},
        headers=auth(admin),
    )
    return restaurante, await fazer_login(client, email)


async def test_403_de_causas_diferentes_corpo_igual_e_log_distinto(
    client: AsyncClient, admin_semeado: User, caplog: pytest.LogCaptureFixture
) -> None:
    admin = await fazer_login(client, ADMIN_EMAIL)
    restaurante_a, _ = await _owner_de(client, admin, "Alfa")
    _, owner_b = await _owner_de(client, admin, "Beta")
    caplog.clear()
    caplog.set_level(logging.DEBUG)

    sem_permissao = await client.post(
        f"{API}/restaurants", json={"name": "X"}, headers=auth(owner_b)
    )
    tenant_alheio = await client.post(
        f"{API}/restaurants/{restaurante_a}/units", json={"name": "Y"}, headers=auth(owner_b)
    )

    assert sem_permissao.status_code == tenant_alheio.status_code == HTTPStatus.FORBIDDEN
    assert sem_permissao.content == tenant_alheio.content
    registros = _registros(caplog)
    causas = [str(_campo(r, "auth_cause")) for r in registros]
    assert [c.split(":")[0] for c in causas] == ["PermissionDeniedError", "TenantNotVisibleError"]
    assert restaurante_a in causas[1]
    assert [_campo(r, "auth_route") for r in registros] == [
        f"{API}/restaurants",
        f"{API}/restaurants/{restaurante_a}/units",
    ]
    atores = {_campo(r, "auth_actor") for r in registros}
    assert len(atores) == 1
    assert None not in atores
    assert owner_b["access_token"] not in caplog.text


async def test_login_recusado_nao_leva_email_nem_senha_ao_log(
    client: AsyncClient, admin_semeado: User, caplog: pytest.LogCaptureFixture
) -> None:
    """E o log das duas falhas é o mesmo: a enumeração não volta pelo servidor.

    Senha errada e e-mail inexistente levantam a mesma exceção, sem causa
    encadeada — o registro não tem como distingui-las, e o e-mail digitado, que
    seria a única diferença, não é lido pelo handler.
    """
    caplog.set_level(logging.DEBUG)
    senha_errada = "senha-errada-que-nao-pode-ir-ao-log"

    errada = await client.post(
        f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": senha_errada}
    )
    inexistente = await client.post(
        f"{API}/auth/login", json={"email": "ninguem@x.com", "password": SENHA_PADRAO}
    )

    assert errada.status_code == inexistente.status_code == HTTPStatus.UNAUTHORIZED
    assert errada.content == inexistente.content
    [primeiro, segundo] = _registros(caplog)
    assert primeiro.getMessage() == segundo.getMessage()
    assert _campo(primeiro, "auth_cause") == "InvalidCredentialsError: credenciais inválidas"
    assert _campo(primeiro, "auth_actor") is None
    for vazamento in (ADMIN_EMAIL, "ninguem@x.com", senha_errada, SENHA_PADRAO):
        assert vazamento not in caplog.text


async def test_token_adulterado_nomeia_a_causa_da_lib_sem_o_token(
    client: AsyncClient, admin_semeado: User, caplog: pytest.LogCaptureFixture
) -> None:
    tokens = await fazer_login(client, ADMIN_EMAIL)
    adulterado = f"{tokens['access_token']}adulterado"
    caplog.set_level(logging.DEBUG)

    sem_header = await client.post(f"{API}/restaurants", json={"name": "X"})
    forjado = await client.post(
        f"{API}/restaurants",
        json={"name": "X"},
        headers={"Authorization": f"Bearer {adulterado}"},
    )

    assert sem_header.status_code == forjado.status_code == HTTPStatus.UNAUTHORIZED
    assert sem_header.content == forjado.content
    causas = [str(_campo(r, "auth_cause")) for r in _registros(caplog)]
    assert causas[0] == "InvalidAccessTokenError: token de acesso inválido"
    assert causas[1].startswith("InvalidAccessTokenError: token de acesso inválido <- jwt.")
    assert tokens["access_token"] not in caplog.text
    assert tokens["refresh_token"] not in caplog.text


async def test_token_de_definicao_de_senha_recusado_nao_vai_ao_log(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Rota pública de recuperação de conta: nem o token nem a senha nova."""
    caplog.set_level(logging.DEBUG)
    token = "token-de-definicao-chutado-0123456789"
    senha = "senha-nova-que-nao-pode-ir-ao-log"

    resposta = await client.post(f"{API}/auth/password", json={"token": token, "password": senha})

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    [registro] = _registros(caplog)
    assert str(_campo(registro, "auth_cause")).startswith("InvalidSetupTokenError")
    assert token not in caplog.text
    assert senha not in caplog.text

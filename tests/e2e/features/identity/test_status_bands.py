"""CA16b — cada faixa de status do mapa é exercitada **pela API**.

O teste unitário de `error_handlers` prova que o dicionário é total e que resolve
o status certo para cada exceção. Isso não prova que alguma requisição real
chegue a produzir aquele status: um mapa perfeito ligado a um router que nunca
levanta a exceção é um mapa decorativo.

Por isso o `parametrize` enumera as **cinco faixas explicitamente**. Uma faixa
sem cenário deixa a lista incompleta e falha — em vez de sumir sem que ninguém
note, que é como um 403 vira 422 em silêncio.
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus

import pytest
from httpx import AsyncClient, Response

from restaurant_hub.features.identity.domain.entities.user import User
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

# As cinco faixas do mapa (concept §6). A lista é a especificação: acrescentar
# uma faixa ao mapa sem cenário aqui deixa esta tupla desatualizada, e o teste de
# completude abaixo reprova.
FAIXAS_DO_MAPA = (
    HTTPStatus.UNAUTHORIZED,
    HTTPStatus.FORBIDDEN,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY,
)


async def _cenario_401(client: AsyncClient, _admin: dict, _caixa: RecordingEmailSender) -> Response:
    """Credencial ausente."""
    return await client.post(f"{API}/restaurants", json=corpo_tenant("X", "dono-x@x.com"))


async def _cenario_403(client: AsyncClient, admin: dict, _caixa: RecordingEmailSender) -> Response:
    """`platform_admin` não tem `manage_users` — escalada barrada."""
    return await client.post(
        f"{API}/users",
        json={"email": "x@y.com", "password": SENHA_PADRAO, "role": "employee"},
        headers=auth(admin),
    )


async def _cenario_404(client: AsyncClient, admin: dict, _caixa: RecordingEmailSender) -> Response:
    """Restaurante do path não existe (o ator é global, então chega ao use case)."""
    return await client.post(
        f"{API}/restaurants/restaurante-inexistente/owners",
        json={"email": "dono@x.com"},
        headers=auth(admin),
    )


async def _cenario_409(client: AsyncClient, admin: dict, _caixa: RecordingEmailSender) -> Response:
    """E-mail já registrado — unicidade global, imposta pelo índice do Postgres."""
    restaurante = (
        await client.post(
            f"{API}/restaurants",
            json=corpo_tenant("Cantina", "duplicado@x.com"),
            headers=auth(admin),
        )
    ).json()["id"]
    corpo = {"email": "duplicado@x.com"}
    return await client.post(
        f"{API}/restaurants/{restaurante}/owners", json=corpo, headers=auth(admin)
    )


async def _cenario_422(client: AsyncClient, admin: dict, caixa: RecordingEmailSender) -> Response:
    """Papel desconhecido — invariante de domínio violada pelo conteúdo enviado.

    Usa rota **autenticada** de propósito. Um 422 vindo só de rota pública
    deixaria `Role.from_string` sem exercício e2e algum, e é justamente a
    conversão texto→VO do router que faz este caso ser erro de domínio (422 pelo
    mapa) em vez de `RequestValidationError` do FastAPI.
    """
    await client.post(
        f"{API}/restaurants", json=corpo_tenant("Cantina", "dono-422@x.com"), headers=auth(admin)
    )
    owner = await login_do_dono(client, caixa, "dono-422@x.com")
    return await client.post(
        f"{API}/users",
        json={"email": "x@y.com", "password": SENHA_PADRAO, "role": "imperador"},
        headers=auth(owner),
    )


CENARIOS: dict[
    HTTPStatus, Callable[[AsyncClient, dict, RecordingEmailSender], Awaitable[Response]]
] = {
    HTTPStatus.UNAUTHORIZED: _cenario_401,
    HTTPStatus.FORBIDDEN: _cenario_403,
    HTTPStatus.NOT_FOUND: _cenario_404,
    HTTPStatus.CONFLICT: _cenario_409,
    HTTPStatus.UNPROCESSABLE_ENTITY: _cenario_422,
}


def test_toda_faixa_do_mapa_tem_cenario() -> None:
    """A completude do parametrize, verificada em vez de confiada.

    Sem esta asserção, remover um cenário simplesmente reduziria o número de
    testes rodados — e uma suíte menor passa mais fácil.
    """
    assert set(CENARIOS) == set(FAIXAS_DO_MAPA)


@pytest.mark.parametrize("faixa", FAIXAS_DO_MAPA, ids=lambda f: str(int(f)))
async def test_faixa_e_alcancavel_pela_api(
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
    faixa: HTTPStatus,
) -> None:
    """Cada uma das cinco faixas é produzida por uma requisição real."""
    admin = await fazer_login(client, ADMIN_EMAIL)

    resposta = await CENARIOS[faixa](client, admin, caixa_de_entrada)

    assert resposta.status_code == faixa, resposta.text


# ---------------------------------------------------------------------------
# Stage 3.5 (D8) — o byte NUL no e-mail é 422, não 500
# ---------------------------------------------------------------------------


async def test_convite_com_email_contendo_nul_e_422_e_nao_500(
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
) -> None:
    """Medido no Checkpoint A da Stage 3.5: era **500**.

    A regex de `Email` aceitava `fulano\x00@cantina.com` (a classe de espaço não
    casa o NUL), o valor seguia para `users.exists_by_email` e o `psycopg` o
    recusava client-side com `DataError` — que não é `IdentityError` e virava 500
    em `POST /users`, `POST /users/invitations` e `POST /auth/login`. Desde a Task
    06 da 3.5 o VO recusa o byte antes da regex, e a faixa é a de domínio (422).
    O cenário usa o convite porque é a rota que, em produção, recebe o e-mail
    digitado por alguém — o mesmo caminho que R17 de staff percorre atrás do
    gateway.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    await client.post(
        f"{API}/restaurants", json=corpo_tenant("Cantina", "dono-nul@x.com"), headers=auth(admin)
    )
    owner = await login_do_dono(client, caixa_de_entrada, "dono-nul@x.com")

    resposta = await client.post(
        f"{API}/users/invitations",
        json={"email": "fulano\x00@cantina.com", "role": "manager", "unit_ids": []},
        headers=auth(owner),
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resposta.text
    assert "e-mail inválido" in resposta.json()["detail"]

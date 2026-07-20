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
    fazer_login,
)

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


async def _cenario_401(client: AsyncClient, _admin: dict) -> Response:
    """Credencial ausente."""
    return await client.post(f"{API}/restaurants", json={"name": "X"})


async def _cenario_403(client: AsyncClient, admin: dict) -> Response:
    """`platform_admin` não tem `manage_users` — escalada barrada."""
    return await client.post(
        f"{API}/users",
        json={"email": "x@y.com", "password": SENHA_PADRAO, "role": "employee"},
        headers=auth(admin),
    )


async def _cenario_404(client: AsyncClient, admin: dict) -> Response:
    """Restaurante do path não existe (o ator é global, então chega ao use case)."""
    return await client.post(
        f"{API}/restaurants/restaurante-inexistente/owners",
        json={"email": "dono@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )


async def _cenario_409(client: AsyncClient, admin: dict) -> Response:
    """E-mail já registrado — unicidade global, imposta pelo índice do Postgres."""
    restaurante = (
        await client.post(f"{API}/restaurants", json={"name": "Cantina"}, headers=auth(admin))
    ).json()["id"]
    corpo = {"email": "duplicado@x.com", "password": SENHA_PADRAO}
    await client.post(f"{API}/restaurants/{restaurante}/owners", json=corpo, headers=auth(admin))
    return await client.post(
        f"{API}/restaurants/{restaurante}/owners", json=corpo, headers=auth(admin)
    )


async def _cenario_422(client: AsyncClient, admin: dict) -> Response:
    """Papel desconhecido — invariante de domínio violada pelo conteúdo enviado.

    Usa rota **autenticada** de propósito. Um 422 vindo só de rota pública
    deixaria `Role.from_string` sem exercício e2e algum, e é justamente a
    conversão texto→VO do router que faz este caso ser erro de domínio (422 pelo
    mapa) em vez de `RequestValidationError` do FastAPI.
    """
    restaurante = (
        await client.post(f"{API}/restaurants", json={"name": "Cantina"}, headers=auth(admin))
    ).json()["id"]
    await client.post(
        f"{API}/restaurants/{restaurante}/owners",
        json={"email": "dono-422@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )
    owner = await fazer_login(client, "dono-422@x.com")
    return await client.post(
        f"{API}/users",
        json={"email": "x@y.com", "password": SENHA_PADRAO, "role": "imperador"},
        headers=auth(owner),
    )


CENARIOS: dict[HTTPStatus, Callable[[AsyncClient, dict], Awaitable[Response]]] = {
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
    client: AsyncClient, admin_semeado: User, faixa: HTTPStatus
) -> None:
    """Cada uma das cinco faixas é produzida por uma requisição real."""
    admin = await fazer_login(client, ADMIN_EMAIL)

    resposta = await CENARIOS[faixa](client, admin)

    assert resposta.status_code == faixa, resposta.text

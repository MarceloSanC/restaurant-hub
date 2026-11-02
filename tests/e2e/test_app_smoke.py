"""Smoke e2e da app factory — exercita create_app, middlewares e error handlers.

Sem features registradas ainda, as rotas de sondagem (probe) são adicionadas ao
app criado pela factory real para percorrer o caminho completo HTTP → handler:
DomainError → 422 (contrato do error handler global). Desde a Stage 3.9 não há
handler global para `ApplicationError` nem para `NotFoundError` (ADR 3.9.0001 §5).
"""

from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from restaurant_hub.shared.application.errors import ApplicationError
from restaurant_hub.shared.domain.exceptions.base import DomainError
from restaurant_hub.shared.infrastructure.http.app import create_app

pytestmark = pytest.mark.e2e


@pytest.fixture
def probe_app() -> FastAPI:
    app = create_app()

    @app.get("/probe/domain-error")
    async def probe_domain_error() -> None:
        raise DomainError("regra de negocio de sonda violada")

    return app


@pytest.fixture
async def probe_client(probe_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=probe_app),
        base_url="http://testserver",
    ) as client:
        yield client


async def test_app_sobe_e_docs_responde(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/docs")
    assert response.status_code == HTTPStatus.OK


async def test_rota_inexistente_retorna_404_json(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/rota-que-nao-existe")
    assert response.status_code == HTTPStatus.NOT_FOUND
    assert "detail" in response.json()


def test_nao_ha_rede_generica_para_application_error(probe_app: FastAPI) -> None:
    """A rede de `shared` cobre só o domínio (ADR 3.9.0001 §5).

    Cada BC registra o seu handler sobre a própria raiz de aplicação; uma rede
    genérica aqui responderia em silêncio por um BC que esquecesse de registrá-la.
    """
    assert DomainError in probe_app.exception_handlers
    assert ApplicationError not in probe_app.exception_handlers


async def test_domain_error_vira_422(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/probe/domain-error")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["type"] == "domain_error"
    assert "sonda" in body["detail"]


async def test_middleware_cors_responde_a_origin(probe_client: AsyncClient) -> None:
    # Sem o CORSMiddleware registrado, a resposta não carrega o header —
    # este teste mata a mutação "remover add_middleware" em middlewares.py.
    response = await probe_client.get("/docs", headers={"Origin": "http://example.com"})
    assert response.status_code == HTTPStatus.OK
    # allow_origins=["*"] + allow_credentials=True => starlette espelha a origin
    assert response.headers.get("access-control-allow-origin") == "http://example.com"

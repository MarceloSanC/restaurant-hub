"""Smoke e2e da app factory — exercita create_app, middlewares e error handlers.

Sem features registradas ainda, as rotas de sondagem (probe) são adicionadas ao
app criado pela factory real para percorrer o caminho completo HTTP → handler:
NotFoundError → 404 e DomainError → 422 (contrato dos error handlers globais).
"""

from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from restaurant_hub.shared.domain.exceptions.base import DomainError, NotFoundError
from restaurant_hub.shared.infrastructure.http.app import create_app

pytestmark = pytest.mark.e2e


@pytest.fixture
def probe_app() -> FastAPI:
    app = create_app()

    @app.get("/probe/not-found")
    async def probe_not_found() -> None:
        raise NotFoundError("recurso de sonda nao encontrado")

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


async def test_not_found_error_vira_404(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/probe/not-found")
    assert response.status_code == HTTPStatus.NOT_FOUND
    body = response.json()
    assert body["type"] == "not_found"
    assert "sonda" in body["detail"]


async def test_domain_error_vira_422(probe_client: AsyncClient) -> None:
    response = await probe_client.get("/probe/domain-error")
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["type"] == "domain_error"
    assert "sonda" in body["detail"]

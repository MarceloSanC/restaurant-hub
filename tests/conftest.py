"""Fixtures globais de teste.

Fixtures de escopo `session` são criadas uma vez por execução do pytest — ideal
para recursos caros como engines de banco de dados. Fixtures de escopo padrão
(function) são recriadas a cada teste — ideal para estado que deve ser isolado
entre testes (ex: client HTTP). Use pytest.mark para filtrar suites no CI.

Este arquivo nasce com fixtures genéricas no template. Cada feature deve
adicionar fixtures próprias (CREATE TABLE da entity, factories de DTO, etc.)
em `tests/<categoria>/features/<feature>/conftest.py`.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from restaurant_hub.shared.infrastructure.http.app import create_app

# A fixture `test_engine` (SQLite in-memory), herdada do template, foi removida na
# Stage 2.3 — sem substituto aqui.
#
# Ela nunca chegou a ser usada por teste nenhum, e mantê-la seria pior que não
# tê-la: o schema desta Stage carrega as invariantes **no banco** — FKs compostas,
# a `CHECK` do iff de tenancy, `TIMESTAMPTZ`, constraints nomeadas que o adapter lê
# para traduzir erro —, e o SQLite diverge do Postgres em todos esses pontos. Uma
# suíte verde contra SQLite valeria menos que suíte nenhuma, porque inspiraria
# confiança no que não foi verificado.
#
# As fixtures de banco vivem agora em `tests/integration/conftest.py`, contra
# PostgreSQL real e sem caminho de skip (ADR 2.3.0001).


@pytest.fixture
async def client() -> AsyncClient:
    """Cliente HTTP assíncrono apontando para a aplicação FastAPI em memória.

    Usa ASGITransport do httpx para fazer requisições sem abrir porta TCP.
    Ideal para testes e2e que precisam testar o ciclo completo HTTP.
    """
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c

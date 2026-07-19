"""Fixtures específicas dos testes de integração.

As fixtures de conexão (`database_url`, `engine`) vivem em `tests/conftest.py`,
porque a suíte de **contrato** também precisa delas — ela roda o mesmo corpo de
teste contra o fake e contra o Postgres. Aqui fica só o que é exclusivo da
integração: o banco limpo por teste.

A exigência de banco real, sem caminho de skip (ADR 2.3.0001), está documentada
junto da fixture `engine`, na raiz.
"""

import pytest
from sqlalchemy import Engine, text

_TABELAS_EM_ORDEM_DE_LIMPEZA = (
    "sessions",
    "unit_memberships",
    "users",
    "units",
    "restaurants",
)


@pytest.fixture
def banco_limpo(engine: Engine) -> Engine:
    """Devolve o `Engine` com todas as tabelas do BC vazias.

    Devolve `Engine` — e não `Connection` — porque é `Engine` que os repositórios
    recebem no construtor (concept §7 Decisão 6): a fixture entrega ao teste
    exatamente o que a produção entrega ao adapter.

    O `TRUNCATE` roda **antes** do teste, não depois: quando um teste falha, o
    estado que ele deixou continua no banco para diagnóstico, e ainda assim o
    teste seguinte começa limpo.

    Ordem de truncamento: filhas antes das mães. O `CASCADE` resolveria sozinho,
    mas a ordem explícita documenta o grafo de dependências.
    """
    with engine.begin() as conexao:
        conexao.execute(text(f"TRUNCATE {', '.join(_TABELAS_EM_ORDEM_DE_LIMPEZA)} CASCADE"))
    return engine

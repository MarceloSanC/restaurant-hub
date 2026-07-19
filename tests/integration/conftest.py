"""Fixtures dos testes de integração — PostgreSQL **real**, sem caminho de skip.

Esta é a decisão de gate mais consequente da Stage 2.3 (ADR 2.3.0001), e ela vive
aqui em três linhas de código: quando o banco não responde, a fixture **falha**.
Nunca `pytest.skip`, e não existe variável de ambiente que desligue a exigência.

O motivo é o defeito que a Stage 1.2 catalogou. Um teste que se pula quando falta
infraestrutura reporta verde **por não ter olhado** — "a false negative wearing a
checkmark" (ADR 1.2.0001). Como o gate deste projeto é o mesmo comando local e no
runner (`make check`), qualquer válvula de escape que existisse aqui acabaria
aberta no CI, e o gate de persistência inteiro viraria decorativo.

A escolha tem um custo real, aceito de olhos abertos: `make check` passa a exigir
Docker rodando. A alternativa ("pular local, exigir no CI") foi medida e rejeitada
— com os adapters sem cobertura, o `fail_under = 90` reprovaria de todo jeito, de
modo que o skip não entregaria sequer o gate verde que prometia; entregaria uma
falha de cobertura confusa no lugar de uma mensagem dizendo o que fazer.

**O schema vem da migration, não de `metadata.create_all`.** Assim cada execução
da suíte exercita a migration de verdade, e um `upgrade` quebrado é pego aqui em
vez de no deploy. Também impede o schema dos testes de divergir do de produção,
que é o jeito clássico de uma suíte verde conviver com um banco quebrado.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from restaurant_hub.shared.infrastructure.config.settings import Settings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _REPO_ROOT / "migrations" / "alembic.ini"

# Ordem de truncamento: filhas antes das mães. `CASCADE` resolveria sozinho, mas
# a ordem explícita documenta o grafo de dependências e evita depender de cascade
# para o caso comum.
_TABLES_EM_ORDEM_DE_LIMPEZA = (
    "sessions",
    "unit_memberships",
    "users",
    "units",
    "restaurants",
)


def _database_url() -> str:
    """URL do banco de teste, do ambiente ou do `.env` da worktree.

    Não há default embutido de propósito: um fallback silencioso para
    `localhost:5432` faria a suíte de uma worktree paralela rodar contra o banco
    de **outra** — e a falha apareceria como dado estranho, não como erro.
    """
    return Settings().database_url


@pytest.fixture(scope="session")
def database_url() -> str:
    return _database_url()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Engine de teste contra o Postgres real, com o schema já migrado.

    Escopo `session`: subir conexão e aplicar migration por teste seria lento sem
    ganho — o isolamento entre testes é feito por `TRUNCATE` na fixture `conexao`.
    """
    engine = create_engine(
        database_url,
        connect_args={
            # Mesma fixação de fuso do `build_engine` de produção: o psycopg
            # devolve `timestamptz` no fuso da SESSÃO, não em UTC. Sem isto, um
            # round-trip de datetime volta em horário local e o mesmo teste passa
            # no runner (UTC) e falha numa máquina em America/Sao_Paulo. O mapper
            # ainda normaliza — cinto e suspensório, porque este Engine é só o
            # dos testes.
            "options": "-c timezone=UTC",
            # Falhar rápido faz parte de falhar alto. Sem timeout explícito, a
            # tentativa de conexão a um banco no ar fica pendurada por dezenas de
            # segundos antes de desistir, e o dev lê isso como "a suíte travou"
            # em vez de "falta subir o Postgres" — a mensagem acionável abaixo
            # chega tarde demais para servir de mensagem.
            "connect_timeout": 5,
        },
    )

    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        # Falha ALTA e acionável. Este é o ponto exato em que um `pytest.skip`
        # transformaria o gate de persistência em teatro (ADR 2.3.0001).
        pytest.fail(
            f"Postgres não está acessível em {database_url!r}.\n"
            f"Suba o banco com `make docker-up`. Os testes de integração desta "
            f"Stage não se pulam (ADR 2.3.0001): um gate que se pula sozinho "
            f"reporta verde por não ter olhado.\n"
            f"Erro original: {exc}",
            pytrace=False,
        )

    _aplicar_migrations(database_url)
    yield engine
    engine.dispose()


def _aplicar_migrations(database_url: str) -> None:
    """Leva o banco de teste até `head` aplicando a migration de verdade."""
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture
def banco_limpo(engine: Engine) -> Engine:
    """Devolve o `Engine` com todas as tabelas do BC vazias.

    Devolve `Engine` — e não `Connection` — porque é `Engine` que os repositórios
    recebem no construtor (concept §7 Decisão 6): a fixture entrega ao teste
    exatamente o que a produção entrega ao adapter.

    O `TRUNCATE` roda **antes** do teste, não depois: quando um teste falha, o
    estado que ele deixou continua no banco para diagnóstico, e ainda assim o
    teste seguinte começa limpo.
    """
    with engine.begin() as conexao:
        conexao.execute(text(f"TRUNCATE {', '.join(_TABLES_EM_ORDEM_DE_LIMPEZA)} CASCADE"))
    return engine

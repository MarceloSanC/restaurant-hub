"""Conexão que os repositórios Postgres de identity usam — a da unidade ativa, ou uma própria.

É a metade "repositório" do adapter da unidade de trabalho (ADR 2.6.0001 §3). Os
repositórios continuam recebendo um `Engine` no construtor e não sabem se há
unidade aberta: pedem a conexão a `for_write`/`for_read`, e estes decidem.

- **Sem unidade ativa** (lei L6): `for_write` abre `engine.begin()` e
  `for_read` abre `engine.connect()` — exatamente o que cada método público
  fazia antes da Stage 2.6. Cada chamada é a própria transação.
- **Com unidade ativa para o MESMO engine**: entregam a conexão da unidade, dentro
  de um `SAVEPOINT` (`Connection.begin_nested()`). O savepoint é o que faz a lei
  L3 valer no Postgres: uma instrução que falha aborta a transação inteira, e sem
  o savepoint a unidade ficaria envenenada — o `COMMIT` seguinte viraria um
  `ROLLBACK` silencioso. Com ele, a chamada que falha desfaz só o que ela mesma
  fez, e a unidade segue utilizável.

**Chaveada pelo engine**, não global: um repositório montado sobre outro `Engine`
(um teste, um script) não entra na unidade de ninguém. O preço é que repositório e
unidade precisam receber o **mesmo** engine — o composition root garante, e o teste
de bootstrap fixa (concept 2.6 R7).

A `ContextVar` é segura sob o threadpool do FastAPI: cada chamada roda num
`copy_context()` próprio (anyio 4.14.1, backend asyncio), então duas requisições
nunca enxergam a unidade uma da outra.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlalchemy import Connection, Engine

# (engine da unidade, conexão da unidade) enquanto uma unidade está aberta neste
# contexto de execução; `None` fora de unidade. Quem publica é o
# `PostgresUnitOfWork`, e só ele.
_active_unit: ContextVar[tuple[Engine, Connection] | None] = ContextVar(
    "unidade_de_trabalho_identity", default=None
)


def _unit_connection(engine: Engine) -> Connection | None:
    active = _active_unit.get()
    if active is None or active[0] is not engine:
        return None
    return active[1]


@contextmanager
def for_write(engine: Engine) -> Iterator[Connection]:
    """Conexão para uma escrita: a da unidade (em savepoint) ou uma transação própria."""
    connection = _unit_connection(engine)
    if connection is None:
        with engine.begin() as own:
            yield own
        return
    with connection.begin_nested():
        yield connection


@contextmanager
def for_read(engine: Engine) -> Iterator[Connection]:
    """Conexão para uma leitura: a da unidade (em savepoint, vê as escritas dela) ou uma própria.

    Dentro da unidade a leitura também vai em savepoint: uma leitura que falha (um
    `statement_timeout`, por exemplo) abortaria a transação da unidade do mesmo
    jeito que uma escrita.
    """
    connection = _unit_connection(engine)
    if connection is None:
        with engine.connect() as own:
            yield own
        return
    with connection.begin_nested():
        yield connection


# ---- publicação, de uso exclusivo do `PostgresUnitOfWork` ----


def has_open_unit() -> bool:
    """Há unidade aberta neste contexto de execução, de qualquer engine (lei L5)."""
    return _active_unit.get() is not None


def publish(engine: Engine, connection: Connection) -> Token[tuple[Engine, Connection] | None]:
    """Torna `connection` a conexão da unidade para os repositórios deste `engine`."""
    return _active_unit.set((engine, connection))


def unpublish(reset_token: Token[tuple[Engine, Connection] | None]) -> None:
    """Desfaz a publicação — chamado em `finally`, mesmo se o commit falhar."""
    _active_unit.reset(reset_token)

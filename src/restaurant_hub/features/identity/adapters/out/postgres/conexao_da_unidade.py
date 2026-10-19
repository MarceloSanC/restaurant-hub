"""Conexão que os repositórios Postgres de identity usam — a da unidade ativa, ou uma própria.

É a metade "repositório" do adapter da unidade de trabalho (ADR 2.6.0001 §3). Os
repositórios continuam recebendo um `Engine` no construtor e não sabem se há
unidade aberta: pedem a conexão a `para_escrita`/`para_leitura`, e estes decidem.

- **Sem unidade ativa** (lei L6): `para_escrita` abre `engine.begin()` e
  `para_leitura` abre `engine.connect()` — exatamente o que cada método público
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
_unidade_ativa: ContextVar[tuple[Engine, Connection] | None] = ContextVar(
    "unidade_de_trabalho_identity", default=None
)


def _conexao_da_unidade(engine: Engine) -> Connection | None:
    ativa = _unidade_ativa.get()
    if ativa is None or ativa[0] is not engine:
        return None
    return ativa[1]


@contextmanager
def para_escrita(engine: Engine) -> Iterator[Connection]:
    """Conexão para uma escrita: a da unidade (em savepoint) ou uma transação própria."""
    conexao = _conexao_da_unidade(engine)
    if conexao is None:
        with engine.begin() as propria:
            yield propria
        return
    with conexao.begin_nested():
        yield conexao


@contextmanager
def para_leitura(engine: Engine) -> Iterator[Connection]:
    """Conexão para uma leitura: a da unidade (em savepoint, vê as escritas dela) ou uma própria.

    Dentro da unidade a leitura também vai em savepoint: uma leitura que falha (um
    `statement_timeout`, por exemplo) abortaria a transação da unidade do mesmo
    jeito que uma escrita.
    """
    conexao = _conexao_da_unidade(engine)
    if conexao is None:
        with engine.connect() as propria:
            yield propria
        return
    with conexao.begin_nested():
        yield conexao


# ---- publicação, de uso exclusivo do `PostgresUnitOfWork` ----


def ha_unidade_aberta() -> bool:
    """Há unidade aberta neste contexto de execução, de qualquer engine (lei L5)."""
    return _unidade_ativa.get() is not None


def publicar(engine: Engine, conexao: Connection) -> Token[tuple[Engine, Connection] | None]:
    """Torna `conexao` a conexão da unidade para os repositórios deste `engine`."""
    return _unidade_ativa.set((engine, conexao))


def retirar(marca: Token[tuple[Engine, Connection] | None]) -> None:
    """Desfaz a publicação — chamado em `finally`, mesmo se o commit falhar."""
    _unidade_ativa.reset(marca)

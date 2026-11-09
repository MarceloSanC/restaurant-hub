"""Adapter Postgres de `UnitOfWork` (ADR 2.6.0001 §3).

Abre **uma** transação (`engine.begin()`) e a publica em `unit_connection`, de
onde os repositórios de identity montados sobre o **mesmo** engine a tiram — cada
chamada num savepoint próprio. Saída normal comita; saída por exceção desfaz e
deixa a exceção subir intacta (leis L1 e L2 do port): quem faz isso é o
`engine.begin()` do SQLAlchemy, que o adapter não envolve em `try` nenhum.

**L5 é checada antes de tocar no pool.** Uma unidade aninhada que retirasse
conexão para só depois recusar devolveria a conexão, mas teria aberto e fechado
uma transação à toa — e "antes de tocar em qualquer coisa" é a forma observável da
lei (nenhuma conexão retirada).

**A publicação é desfeita em `finally`**, mesmo que o commit falhe: um worker
thread do threadpool que ficasse com a unidade publicada faria a próxima
requisição dele herdar a conexão de outra.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine

from restaurant_hub.features.identity.adapters.out.postgres import unit_connection


class PostgresUnitOfWork:
    """Implementação PostgreSQL do port `UnitOfWork`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if unit_connection.has_open_unit():
            raise RuntimeError("unidade de trabalho já aberta neste contexto (L5)")
        with self._engine.begin() as connection:
            reset_token = unit_connection.publish(self._engine, connection)
            try:
                yield
            finally:
                unit_connection.unpublish(reset_token)

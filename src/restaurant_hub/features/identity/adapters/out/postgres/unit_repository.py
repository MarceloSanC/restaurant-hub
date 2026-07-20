"""Adapter Postgres de `UnitRepository`.

Mesma fronteira transacional do `PostgresRestaurantRepository` — ver o docstring
daquele módulo para por que a transação é aberta aqui e não por um unit-of-work.

Nota sobre erro: a unidade referencia o restaurante por FK, e restaurante
inexistente estoura `fk_units_restaurant`. Essa violação **não** é traduzida
(concept §7 Decisão 7): o `CreateUnitUseCase` da 2.2 já checa a existência do
restaurante antes de gravar e levanta `RestaurantNotFoundError`, então uma FK que
estoura aqui significa concorrência exótica ou bug — e vesti-la de erro de negócio
esconderia o defeito atrás de um 4xx plausível.
"""

from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.integrity_errors import (
    traduzir,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import units
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import UnitId


class PostgresUnitRepository:
    """Implementação PostgreSQL do port `UnitRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, unit: Unit) -> None:
        """Insere uma unidade. Id já gravado levanta `UnitAlreadyExistsError`."""
        try:
            with self._engine.begin() as conexao:
                self._add(conexao, unit)
        except IntegrityError as erro:
            raise traduzir(erro, unit.id) from erro

    def find_by_id(self, unit_id: UnitId) -> Unit | None:
        with self._engine.connect() as conexao:
            return self._find_by_id(conexao, unit_id)

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) ----

    def _add(self, conexao: Connection, unit: Unit) -> None:
        conexao.execute(units.insert().values(**mappers.unidade_para_linha(unit)))

    def _find_by_id(self, conexao: Connection, unit_id: UnitId) -> Unit | None:
        linha = conexao.execute(select(units).where(units.c.id == unit_id)).one_or_none()
        return mappers.linha_para_unidade(linha) if linha is not None else None

"""Fake in-memory de `UnitRepository`.

O contador `find_calls` não é enfeite: o critério CA4 exige provar que
`create_user` rejeita `platform_admin` com `unit_ids` **sem consultar** o
repositório de unidades — do contrário o erro vazaria a existência de unidades a
quem não deveria enxergá-las.
"""

from restaurant_hub.features.identity.application.errors import UnitAlreadyExistsError
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import UnitId


class InMemoryUnitRepository:
    """Implementação in-memory do port, com contador de leituras."""

    def __init__(self) -> None:
        self.units: dict[UnitId, Unit] = {}
        self.find_calls = 0

    def add(self, unit: Unit) -> None:
        # Inserção, não upsert — ver ADR 2.3.0003.
        if unit.id in self.units:
            raise UnitAlreadyExistsError(unit.id)
        self.units[unit.id] = unit

    def find_by_id(self, unit_id: UnitId) -> Unit | None:
        self.find_calls += 1
        return self.units.get(unit_id)


_conforms: UnitRepository = InMemoryUnitRepository()

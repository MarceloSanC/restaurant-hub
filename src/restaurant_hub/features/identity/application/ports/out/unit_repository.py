"""Port de saída: persistência de unidades (filiais).

A unidade referencia o restaurante por id (`restaurant_id`, que é o seu
`tenant_id`) — nunca por objeto, conforme ADR 2.1.0001.
"""

from typing import Protocol

from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import UnitId


class UnitRepository(Protocol):
    """Contrato de persistência da raiz de agregado `Unit`."""

    def add(self, unit: Unit) -> None:
        """Persiste uma unidade nova.

        **É inserção, não upsert** (ADR 2.3.0003): id já gravado levanta
        `UnitAlreadyExistsError`, imposto pela PK da tabela na 2.3.
        """
        ...

    def find_by_id(self, unit_id: UnitId) -> Unit | None:
        """Devolve a unidade, ou `None` se não existir."""
        ...

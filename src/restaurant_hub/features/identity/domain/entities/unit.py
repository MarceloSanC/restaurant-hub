"""Entidade Unit — unidade (filial) de um restaurante.

Raiz de agregado própria: referencia o restaurante **por id** (`restaurant_id`),
nunca por referência de objeto (ADR 2.1.0001). O `restaurant_id` é o `tenant_id`
da unidade — é ele que sustenta o isolamento row-level (ROADMAP-3).

Igualdade por **identidade**.
"""

from dataclasses import dataclass

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidNameError
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)


@dataclass(frozen=True, eq=False)
class Unit:
    """Unidade de um restaurante.

    Attributes:
        id: identidade da unidade.
        restaurant_id: restaurante dono da unidade — também o seu `tenant_id`.
        name: nome da unidade (não vazio).
    """

    id: UnitId
    restaurant_id: RestaurantId
    name: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidNameError("unidade")

    @property
    def tenant_id(self) -> RestaurantId:
        """Tenant da unidade — o restaurante a que ela pertence."""
        return self.restaurant_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Unit):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

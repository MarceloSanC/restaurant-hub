"""Entidade Restaurant — o restaurante cliente, que é o próprio tenant.

Raiz de agregado. No glossário do overview (§9) "tenant" é um restaurante cliente
isolado dos demais, então a identidade do `Restaurant` **é** o `tenant_id` de todas
as linhas que lhe pertencem (ADR 2.1.0001) — não existe entidade `Tenant` separada.

Igualdade por **identidade**: dois `Restaurant` com o mesmo id são a mesma
entidade, ainda que os demais campos difiram.
"""

from dataclasses import dataclass

from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)


@dataclass(eq=False)
class Restaurant:
    """Restaurante cliente da plataforma — a raiz da tenancy.

    Attributes:
        id: identidade do restaurante, que também é o seu `tenant_id`.
        name: nome do restaurante (não vazio).
    """

    id: RestaurantId
    name: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("nome do restaurante não pode ser vazio")

    @property
    def tenant_id(self) -> RestaurantId:
        """O restaurante é o próprio tenant."""
        return self.id

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Restaurant) and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

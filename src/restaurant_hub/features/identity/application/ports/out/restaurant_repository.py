"""Port de saída: persistência de restaurantes (tenants).

Implementado por Postgres na Stage 2.3 e por um fake in-memory nos testes desta.
`Protocol` (tipagem estrutural) em vez de `ABC`: o adapter não precisa herdar
nada, o que mantém a dependência apontando só para dentro (LAYOUT §3).
"""

from typing import Protocol

from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)


class RestaurantRepository(Protocol):
    """Contrato de persistência da raiz de agregado `Restaurant`."""

    def add(self, restaurant: Restaurant) -> None:
        """Persiste um restaurante novo.

        **É inserção, não upsert** (ADR 2.3.0003): id já gravado levanta
        `RestaurantAlreadyExistsError`. Na 2.3 quem impõe a regra é a PK da
        tabela, e o adapter traduz o `IntegrityError` para essa exceção.
        """
        ...

    def find_by_id(self, restaurant_id: RestaurantId) -> Restaurant | None:
        """Devolve o restaurante, ou `None` se não existir."""
        ...

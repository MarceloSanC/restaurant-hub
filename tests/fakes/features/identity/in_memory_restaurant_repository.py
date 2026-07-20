"""Fake in-memory de `RestaurantRepository`.

Fake, não mock: guarda estado observável em `dict`, então os testes verificam
**comportamento** (o restaurante ficou lá?) em vez de chamadas
(`assert_called_with`), que acoplam o teste à implementação do use case.
"""

from restaurant_hub.features.identity.application.errors import (
    RestaurantAlreadyExistsError,
)
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)


class InMemoryRestaurantRepository:
    """Implementação in-memory do port, com contadores para asserção de acesso."""

    def __init__(self) -> None:
        self.restaurants: dict[RestaurantId, Restaurant] = {}
        self.find_calls = 0

    def add(self, restaurant: Restaurant) -> None:
        # Inserção, não upsert (ADR 2.3.0003): a atribuição direta sobrescrevia em
        # silêncio o que a PK de `restaurants` rejeita — o fake sendo mais gentil
        # que a produção, que é o jeito exato de um teste passar e o sistema
        # falhar ao vivo.
        if restaurant.id in self.restaurants:
            raise RestaurantAlreadyExistsError(restaurant.id)
        self.restaurants[restaurant.id] = restaurant

    def find_by_id(self, restaurant_id: RestaurantId) -> Restaurant | None:
        self.find_calls += 1
        return self.restaurants.get(restaurant_id)


# Conformidade estrutural com o port, checada por mypy (alvo `typecheck` cobre
# tests/fakes/). Sem esta linha, um fake que divergisse do `Protocol` passaria em
# todos os gates — e a 2.3 herdaria a divergência como se fosse especificação.
_conforms: RestaurantRepository = InMemoryRestaurantRepository()

"""Use case: criar um restaurante (que é, ele próprio, o tenant).

O id vem do `IdGenerator` injetado, convertido pela forma canônica
`str(uuid)` (concept §5.3): fixar a conversão num único lugar evita que a
persistência (2.3) grave `hex` enquanto o HTTP (2.4) lê a forma com hífens.

Validação de nome é do domínio e **sobe sem reembrulho** — `InvalidNameError` já
é `IdentityError`, portanto já vira 4xx na 2.4. Capturar e relançar aqui só
perderia informação.
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    CreateRestaurantCommand,
)
from restaurant_hub.features.identity.application.dtos.results import RestaurantResult
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CreateRestaurantUseCase:
    """Cria um restaurante e o persiste."""

    def __init__(
        self,
        restaurants: RestaurantRepository,
        id_generator: IdGenerator,
    ) -> None:
        self._restaurants = restaurants
        self._id_generator = id_generator

    def execute(self, command: CreateRestaurantCommand) -> RestaurantResult:
        """Cria o restaurante.

        Raises:
            InvalidNameError: nome vazio (invariante do domínio).
        """
        restaurant = Restaurant(
            id=RestaurantId(str(self._id_generator.next_id())),
            name=command.name,
        )
        self._restaurants.add(restaurant)
        return RestaurantResult(id=restaurant.id, name=restaurant.name)

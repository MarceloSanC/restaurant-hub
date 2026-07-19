"""Testes do use case `create_restaurant` — concept CA1."""

from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    CreateRestaurantCommand,
)
from restaurant_hub.features.identity.application.use_cases.create_restaurant import (
    CreateRestaurantUseCase,
)
from restaurant_hub.features.identity.domain.exceptions.errors import InvalidNameError
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_FIXED_ID = UUID("11111111-1111-1111-1111-111111111111")


def _use_case(
    repo: InMemoryRestaurantRepository | None = None,
) -> tuple[CreateRestaurantUseCase, InMemoryRestaurantRepository]:
    restaurants = repo or InMemoryRestaurantRepository()
    use_case = CreateRestaurantUseCase(restaurants, FakeIdGenerator([_FIXED_ID]))
    return use_case, restaurants


def test_cria_restaurante_com_id_do_gerador_e_o_persiste() -> None:
    """CA1 — o id é `str(uuid)`, a forma canônica que a 2.3 vai persistir."""
    use_case, restaurants = _use_case()

    result = use_case.execute(CreateRestaurantCommand(name="Cantina da Esquina"))

    assert result.id == str(_FIXED_ID)
    assert result.name == "Cantina da Esquina"
    assert restaurants.restaurants[RestaurantId(str(_FIXED_ID))].name == "Cantina da Esquina"


def test_restaurante_e_o_proprio_tenant() -> None:
    """No glossário do projeto, tenant É o restaurante — não há entidade separada."""
    use_case, restaurants = _use_case()

    result = use_case.execute(CreateRestaurantCommand(name="Cantina"))

    persistido = restaurants.restaurants[RestaurantId(result.id)]
    assert persistido.tenant_id == result.id


def test_nome_vazio_propaga_erro_de_dominio_sem_reembrulho() -> None:
    """A invariante é do domínio; reembrulhar perderia especificidade na 2.4."""
    use_case, restaurants = _use_case()

    with pytest.raises(InvalidNameError):
        use_case.execute(CreateRestaurantCommand(name="   "))

    assert restaurants.restaurants == {}

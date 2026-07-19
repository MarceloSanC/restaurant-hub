"""Testes do use case `create_unit` — concept CA2."""

from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import CreateUnitCommand
from restaurant_hub.features.identity.application.errors import RestaurantNotFoundError
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.exceptions.errors import InvalidNameError
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_FIXED_ID = UUID("22222222-2222-2222-2222-222222222222")
_TENANT = RestaurantId("rest-1")


def _setup(
    *, com_restaurante: bool = True
) -> tuple[CreateUnitUseCase, InMemoryUnitRepository, InMemoryRestaurantRepository]:
    units = InMemoryUnitRepository()
    restaurants = InMemoryRestaurantRepository()
    if com_restaurante:
        restaurants.add(Restaurant(id=_TENANT, name="Cantina"))
    use_case = CreateUnitUseCase(units, restaurants, FakeIdGenerator([_FIXED_ID]))
    return use_case, units, restaurants


def test_cria_unidade_sob_restaurante_existente() -> None:
    """CA2 — caminho feliz."""
    use_case, units, _ = _setup()

    result = use_case.execute(CreateUnitCommand(restaurant_id=_TENANT, name="Centro"))

    assert result.id == str(_FIXED_ID)
    assert result.restaurant_id == _TENANT
    assert units.units[UnitId(str(_FIXED_ID))].name == "Centro"


def test_unidade_herda_o_tenant_do_restaurante() -> None:
    """É o `tenant_id` da unidade que sustenta o isolamento row-level (ROADMAP-3)."""
    use_case, units, _ = _setup()

    result = use_case.execute(CreateUnitCommand(restaurant_id=_TENANT, name="Centro"))

    assert units.units[UnitId(result.id)].tenant_id == _TENANT


def test_restaurante_inexistente_levanta_e_nao_grava_unidade() -> None:
    """CA2 — sem esta guarda, a unidade órfã ficaria invisível a toda consulta
    escopada por tenant, o que é vazamento silencioso, não erro visível."""
    use_case, units, _ = _setup(com_restaurante=False)

    with pytest.raises(RestaurantNotFoundError):
        use_case.execute(CreateUnitCommand(restaurant_id=_TENANT, name="Centro"))

    assert units.units == {}


def test_restaurante_e_resolvido_antes_de_qualquer_escrita() -> None:
    """A ordem importa: validar depois de gravar deixaria lixo no repositório."""
    use_case, units, restaurants = _setup(com_restaurante=False)

    with pytest.raises(RestaurantNotFoundError):
        use_case.execute(CreateUnitCommand(restaurant_id=_TENANT, name="Centro"))

    assert restaurants.find_calls == 1
    assert units.units == {}


def test_nome_vazio_propaga_erro_de_dominio() -> None:
    use_case, units, _ = _setup()

    with pytest.raises(InvalidNameError):
        use_case.execute(CreateUnitCommand(restaurant_id=_TENANT, name=""))

    assert units.units == {}

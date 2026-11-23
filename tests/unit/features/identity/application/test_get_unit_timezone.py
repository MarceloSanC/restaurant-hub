"""Testes do use case `get_unit_timezone` — issue #198 (ADR 4.1.0005).

O que se protege: o fuso devolvido é o da unidade pedida, não o de uma vizinha nem
o default; o endereço é o par (tenant, unidade), e a unidade de outro tenant
responde como inexistente; unidade desconhecida é `None`, não erro; a falha do
repositório sobe como é.
"""

import pytest

from restaurant_hub.features.identity.application.dtos.commands import GetUnitTimezoneCommand
from restaurant_hub.features.identity.application.dtos.results import UnitTimezoneResult
from restaurant_hub.features.identity.application.use_cases.get_unit_timezone import (
    GetUnitTimezoneUseCase,
)
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository

pytestmark = pytest.mark.unit

_TENANT = RestaurantId("rest-a")


def _repositorio() -> InMemoryUnitRepository:
    units = InMemoryUnitRepository()
    units.add(
        Unit(id=UnitId("u-mao"), restaurant_id=_TENANT, name="Manaus", timezone="America/Manaus")
    )
    # Vizinha do mesmo tenant em outro fuso: o use case tem de ler **a** unidade pedida.
    units.add(
        Unit(id=UnitId("u-lis"), restaurant_id=_TENANT, name="Lisboa", timezone="Europe/Lisbon")
    )
    units.add(Unit(id=UnitId("u-b"), restaurant_id=RestaurantId("rest-b"), name="Outro"))
    return units


@pytest.mark.parametrize(
    ("unidade", "fuso"), [("u-mao", "America/Manaus"), ("u-lis", "Europe/Lisbon")]
)
def test_devolve_o_fuso_da_unidade_pedida(unidade: str, fuso: str) -> None:
    resultado = GetUnitTimezoneUseCase(_repositorio()).execute(
        GetUnitTimezoneCommand(tenant_id=_TENANT, unit_id=UnitId(unidade))
    )

    assert resultado == UnitTimezoneResult(timezone=fuso)


def test_unidade_sem_fuso_declarado_devolve_o_default() -> None:
    resultado = GetUnitTimezoneUseCase(_repositorio()).execute(
        GetUnitTimezoneCommand(tenant_id=RestaurantId("rest-b"), unit_id=UnitId("u-b"))
    )

    assert resultado == UnitTimezoneResult(timezone="America/Sao_Paulo")


def test_unidade_de_outro_tenant_responde_como_inexistente() -> None:
    """O par (tenant, unidade): pedir a unidade de `rest-b` em nome de `rest-a` é `None`."""
    resultado = GetUnitTimezoneUseCase(_repositorio()).execute(
        GetUnitTimezoneCommand(tenant_id=_TENANT, unit_id=UnitId("u-b"))
    )

    assert resultado is None


def test_unidade_desconhecida_e_none_e_nao_erro() -> None:
    resultado = GetUnitTimezoneUseCase(_repositorio()).execute(
        GetUnitTimezoneCommand(tenant_id=_TENANT, unit_id=UnitId("nunca-existiu"))
    )

    assert resultado is None


class _RepositorioQuebrado(InMemoryUnitRepository):
    def find_by_id(self, unit_id: UnitId) -> Unit | None:
        raise RuntimeError("banco fora")


def test_falha_do_repositorio_sobe_como_e() -> None:
    with pytest.raises(RuntimeError, match="banco fora"):
        GetUnitTimezoneUseCase(_RepositorioQuebrado()).execute(
            GetUnitTimezoneCommand(tenant_id=_TENANT, unit_id=UnitId("u-mao"))
        )

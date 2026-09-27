"""Testes do VO DemandQuantity (value_objects/demand_quantity.py) — CA9."""

import dataclasses

import pytest

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDemandQuantityError,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", [-1, -100])
def test_quantidade_negativa_e_recusada(value: int) -> None:
    with pytest.raises(InvalidDemandQuantityError, match=">= 0"):
        DemandQuantity(value)


@pytest.mark.parametrize("value", [0, 1, 3, 1_000])
def test_zero_e_positivos_sao_aceitos(value: int) -> None:
    # 0 = faixa habilitada sem demanda dessa função; N é alvo, não teto.
    assert DemandQuantity(value).value == value


def test_quantidade_compara_por_valor() -> None:
    assert DemandQuantity(2) == DemandQuantity(2)
    assert hash(DemandQuantity(2)) == hash(DemandQuantity(2))
    assert DemandQuantity(2) != DemandQuantity(3)


def test_quantidade_e_imutavel() -> None:
    quantidade = DemandQuantity(2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        quantidade.value = 3  # type: ignore[misc]

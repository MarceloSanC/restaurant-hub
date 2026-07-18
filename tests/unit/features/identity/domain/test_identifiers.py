"""Testes dos identificadores tipados (value_objects/identifiers.py)."""

import pytest

from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)

pytestmark = pytest.mark.unit


def test_ids_devolvem_o_proprio_valor() -> None:
    # NewType é identidade só em tempo de type-check; em runtime devolve o argumento.
    assert RestaurantId("r1") == "r1"
    assert UnitId("u1") == "u1"
    assert UserId("us1") == "us1"


def test_nomes_dos_newtypes_batem_com_os_identificadores() -> None:
    # Um typo no argumento do NewType (ex.: "RestaurantID") não quebra nada em
    # runtime, mas degrada silenciosamente toda mensagem futura do mypy.
    assert RestaurantId.__name__ == "RestaurantId"
    assert UnitId.__name__ == "UnitId"
    assert UserId.__name__ == "UserId"

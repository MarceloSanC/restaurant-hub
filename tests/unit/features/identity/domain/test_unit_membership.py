"""Testes do value object UnitMembership (domain/value_objects/unit_membership.py)."""

import dataclasses

import pytest

from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)

pytestmark = pytest.mark.unit


def test_cria_vinculo_entre_usuario_e_unidade() -> None:
    vinculo = UnitMembership(user_id=UserId("us1"), unit_id=UnitId("u1"))
    assert vinculo.user_id == "us1"
    assert vinculo.unit_id == "u1"


def test_igualdade_por_valor() -> None:
    # VO: dois vínculos com o mesmo par (usuário, unidade) são o mesmo vínculo.
    assert UnitMembership(UserId("us1"), UnitId("u1")) == UnitMembership(
        UserId("us1"), UnitId("u1")
    )


def test_usuario_diferente_nao_e_o_mesmo_vinculo() -> None:
    assert UnitMembership(UserId("us1"), UnitId("u1")) != UnitMembership(
        UserId("us2"), UnitId("u1")
    )


def test_unidade_diferente_nao_e_o_mesmo_vinculo() -> None:
    assert UnitMembership(UserId("us1"), UnitId("u1")) != UnitMembership(
        UserId("us1"), UnitId("u2")
    )


def test_e_hashavel_e_deduplica_por_valor() -> None:
    vinculos = {
        UnitMembership(UserId("us1"), UnitId("u1")),
        UnitMembership(UserId("us1"), UnitId("u1")),
    }
    assert len(vinculos) == 1


def test_e_imutavel() -> None:
    vinculo = UnitMembership(user_id=UserId("us1"), unit_id=UnitId("u1"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        vinculo.unit_id = UnitId("u2")  # type: ignore[misc]

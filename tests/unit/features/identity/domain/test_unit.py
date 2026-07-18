"""Testes da entidade Unit (domain/entities/unit.py)."""

import pytest

from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)

pytestmark = pytest.mark.unit


def test_cria_unidade_valida() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade.id == "u1"
    assert unidade.restaurant_id == "r1"
    assert unidade.name == "Matriz"


def test_tenant_id_e_o_restaurante_dono() -> None:
    # É o tenant_id da unidade que sustenta o isolamento row-level (ROADMAP-3).
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade.tenant_id == "r1"


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    antes = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    depois = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Filial")
    assert antes == depois


def test_ids_diferentes_nao_sao_iguais() -> None:
    assert Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz") != Unit(
        id=UnitId("u2"), restaurant_id=RestaurantId("r1"), name="Matriz"
    )


def test_hash_segue_a_identidade() -> None:
    antes = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    depois = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Filial")
    assert len({antes, depois}) == 1


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade != "u1"


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(ValueError, match="nome da unidade não pode ser vazio"):
        Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name=invalido)

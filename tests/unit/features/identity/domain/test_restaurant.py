"""Testes da entidade Restaurant (domain/entities/restaurant.py)."""

import pytest

from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)

pytestmark = pytest.mark.unit


def test_cria_restaurante_valido() -> None:
    restaurante = Restaurant(id=RestaurantId("r1"), name="Cantina do Porto")
    assert restaurante.id == "r1"
    assert restaurante.name == "Cantina do Porto"


def test_tenant_id_e_o_proprio_id() -> None:
    # O restaurante É o tenant (ADR 2.1.0001): não há entidade Tenant separada.
    restaurante = Restaurant(id=RestaurantId("r1"), name="Cantina")
    assert restaurante.tenant_id == restaurante.id


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    # Entidade compara por id: renomear não cria outra entidade.
    antes = Restaurant(id=RestaurantId("r1"), name="Cantina")
    depois = Restaurant(id=RestaurantId("r1"), name="Cantina Renomeada")
    assert antes == depois


def test_ids_diferentes_nao_sao_iguais() -> None:
    assert Restaurant(id=RestaurantId("r1"), name="Cantina") != Restaurant(
        id=RestaurantId("r2"), name="Cantina"
    )


def test_hash_segue_a_identidade() -> None:
    antes = Restaurant(id=RestaurantId("r1"), name="Cantina")
    depois = Restaurant(id=RestaurantId("r1"), name="Outro nome")
    assert len({antes, depois}) == 1


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    assert Restaurant(id=RestaurantId("r1"), name="Cantina") != "r1"


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(ValueError, match="nome do restaurante não pode ser vazio"):
        Restaurant(id=RestaurantId("r1"), name=invalido)

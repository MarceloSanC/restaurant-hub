"""Testes do VO UnitEnablement e da habilitação em JobFunction (Stage 3.11, ADR 3.11.0001)."""

import dataclasses

import pytest

from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidUnitEnablementError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement

pytestmark = pytest.mark.unit

_A = UnitId("u-a")
_B = UnitId("u-b")


def test_todas_as_unidades_cobre_qualquer_unidade() -> None:
    todas = UnitEnablement.everywhere()
    assert todas.all_units is True
    assert todas.unit_ids == frozenset()
    assert todas.covers(_A)
    assert todas.covers(UnitId("unidade-criada-amanha"))


def test_conjunto_cobre_so_as_suas_unidades() -> None:
    so_a = UnitEnablement.only(frozenset({_A}))
    assert so_a.all_units is False
    assert so_a.unit_ids == frozenset({_A})
    assert so_a.covers(_A)
    assert not so_a.covers(_B)


def test_ca9a_conjunto_vazio_e_recusado() -> None:
    with pytest.raises(InvalidUnitEnablementError, match="ao menos uma unidade"):
        UnitEnablement.only(frozenset())


def test_todas_e_conjunto_ao_mesmo_tempo_e_recusado() -> None:
    """A forma incoerente que só a reidratação de uma linha corrompida produziria."""
    with pytest.raises(InvalidUnitEnablementError, match="não nomeia unidades"):
        UnitEnablement(all_units=True, unit_ids=frozenset({_A}))


def test_nenhum_dos_dois_e_recusado_tambem_pelo_construtor() -> None:
    with pytest.raises(InvalidUnitEnablementError):
        UnitEnablement(all_units=False, unit_ids=frozenset())


@pytest.mark.parametrize("em_branco", ["", "   ", "\t"])
def test_id_de_unidade_em_branco_e_recusado(em_branco: str) -> None:
    with pytest.raises(InvalidUnitEnablementError, match="identificador de unidade vazio"):
        UnitEnablement.only(frozenset({_A, UnitId(em_branco)}))


def test_vo_e_imutavel_e_igual_por_valor() -> None:
    um = UnitEnablement.only(frozenset({_A, _B}))
    outro = UnitEnablement.only(frozenset({_B, _A}))
    assert um == outro
    assert hash(um) == hash(outro)
    with pytest.raises(dataclasses.FrozenInstanceError):
        um.all_units = True  # type: ignore[misc]


def _funcao(**campos: object) -> JobFunction:
    return JobFunction(
        id=JobFunctionId("f1"),
        tenant_id=TenantId("t1"),
        name="Cozinheiro",
        **campos,  # type: ignore[arg-type]
    )


def test_funcao_sem_habilitacao_declarada_vale_em_todas_as_unidades() -> None:
    """D8 do concept: o default é o mesmo da migration `0005`."""
    assert _funcao().unit_enablement == UnitEnablement.everywhere()
    assert _funcao().is_enabled_in(_A)


def test_funcao_habilitada_so_em_a_nao_vale_em_b() -> None:
    funcao = _funcao(unit_enablement=UnitEnablement.only(frozenset({_A})))
    assert funcao.is_enabled_in(_A)
    assert not funcao.is_enabled_in(_B)


def test_with_enablement_devolve_nova_instancia_e_preserva_o_resto() -> None:
    original = _funcao(unit_enablement=UnitEnablement.only(frozenset({_A})))
    alterada = original.with_enablement(UnitEnablement.only(frozenset({_B})))
    assert alterada is not original
    assert alterada.unit_enablement.unit_ids == frozenset({_B})
    assert original.unit_enablement.unit_ids == frozenset({_A})
    assert (alterada.id, alterada.tenant_id, alterada.name) == (
        original.id,
        original.tenant_id,
        original.name,
    )


def test_igualdade_da_funcao_continua_por_identidade() -> None:
    a = _funcao(unit_enablement=UnitEnablement.only(frozenset({_A})))
    assert a == a.with_enablement(UnitEnablement.everywhere())

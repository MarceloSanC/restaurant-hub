"""Testes da entidade JobFunction (domain/entities/job_function.py)."""

import dataclasses

import pytest

from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidNameError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
)

pytestmark = pytest.mark.unit


def _funcao(name: str = "Cozinheiro", *, active: bool = True) -> JobFunction:
    return JobFunction(id=JobFunctionId("f1"), tenant_id=TenantId("t1"), name=name, active=active)


def test_cria_funcao_valida_com_active_default() -> None:
    funcao = _funcao()
    assert funcao.id == "f1"
    assert funcao.tenant_id == "t1"
    assert funcao.name == "Cozinheiro"
    assert funcao.active is True


@pytest.mark.parametrize("invalido", ["", "   "])
def test_id_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de função"):
        JobFunction(id=JobFunctionId(invalido), tenant_id=TenantId("t1"), name="Cozinheiro")


@pytest.mark.parametrize("invalido", ["", "   "])
def test_tenant_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de tenant da função"):
        JobFunction(id=JobFunctionId("f1"), tenant_id=TenantId(invalido), name="Cozinheiro")


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado_na_construcao(invalido: str) -> None:
    with pytest.raises(InvalidNameError, match="nome de função"):
        _funcao(name=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado_no_rename(invalido: str) -> None:
    # A transição passa pelo __post_init__ de novo — mesmo predicado da construção.
    with pytest.raises(InvalidNameError, match="nome de função"):
        _funcao().rename(invalido)


def test_nome_e_preservado_verbatim_na_construcao() -> None:
    # ADR 3.1.0002: sem trim/case silenciosos.
    assert _funcao(name="  Cozinheiro ").name == "  Cozinheiro "


def test_nome_e_preservado_verbatim_no_rename() -> None:
    renomeada = _funcao().rename("  Chapeiro ")
    assert renomeada.name == "  Chapeiro "


def test_deactivate_devolve_nova_instancia_inativa() -> None:
    original = _funcao()
    inativa = original.deactivate()
    assert inativa.active is False
    assert original.active is True  # original imutada


def test_reactivate_devolve_nova_instancia_ativa() -> None:
    original = _funcao(active=False)
    reativada = original.reactivate()
    assert reativada.active is True
    assert original.active is False  # original imutada


def test_transicoes_repetidas_sao_idempotentes_no_valor() -> None:
    # Decisão registrada na §7 do technical: repetir não é erro.
    assert _funcao(active=False).deactivate().active is False
    assert _funcao(active=True).reactivate().active is True


def test_entidade_e_imutavel() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _funcao().active = False  # type: ignore[misc]


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    mesma_id = JobFunction(id=JobFunctionId("f1"), tenant_id=TenantId("t1"), name="Chapeiro")
    assert _funcao() == mesma_id


def test_ids_diferentes_nao_sao_iguais() -> None:
    outra = JobFunction(id=JobFunctionId("f2"), tenant_id=TenantId("t1"), name="Cozinheiro")
    assert _funcao() != outra


def test_hash_segue_a_identidade() -> None:
    mesma_id = JobFunction(id=JobFunctionId("f1"), tenant_id=TenantId("t1"), name="Chapeiro")
    assert len({_funcao(), mesma_id}) == 1


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    assert _funcao() != "f1"


class _SempreIgual:
    """Objeto que se declara igual a qualquer coisa, para testar a reflexão."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


def test_eq_delega_ao_outro_operando_quando_o_tipo_e_estranho() -> None:
    # __eq__ devolve NotImplemented para tipo alheio: o outro operando decide.
    assert _funcao() == _SempreIgual()
    assert _SempreIgual() == _funcao()

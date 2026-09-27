"""Testes da entidade ShiftDemand (entities/shift_demand.py).

Parcial de CA10 (as duas duplicidades da demanda, na construção direta — o
caminho da reidratação da 4.4), CA15 (frozen e identidade por id) e CA22
(`ShiftDemandId`, `JobFunctionId`). Toda checagem par a par é provada com o par
**não consecutivo** (posições 0 e 2) numa coleção de 3: o laço "só vizinhos"
sobrevive ao par consecutivo.
"""

import dataclasses

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateAssignmentError,
    DuplicateEntityIdError,
    InvalidIdentifierError,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ShiftDemandId,
)

pytestmark = pytest.mark.unit

_ID = ShiftDemandId("dem-1")
_COZINHEIRO = JobFunctionId("cozinheiro")
_DOIS = DemandQuantity(2)


def _alocacao(aloc: str, funcionario: str) -> Assignment:
    return Assignment(id=AssignmentId(aloc), employee_id=EmployeeId(funcionario))


def _demanda(*alocacoes: Assignment) -> ShiftDemand:
    return ShiftDemand(id=_ID, job_function_id=_COZINHEIRO, quantity=_DOIS, assignments=alocacoes)


# --- CA10 (parcial): duplicidades par a par, par não consecutivo ----------------------


def test_mesmo_funcionario_em_posicoes_nao_consecutivas_e_recusado() -> None:
    with pytest.raises(DuplicateAssignmentError):
        _demanda(_alocacao("a1", "ana"), _alocacao("a2", "bia"), _alocacao("a3", "ana"))


def test_mesmo_funcionario_em_posicoes_consecutivas_e_recusado() -> None:
    with pytest.raises(DuplicateAssignmentError):
        _demanda(_alocacao("a1", "ana"), _alocacao("a2", "ana"))


def test_mesmo_assignment_id_em_posicoes_nao_consecutivas_e_recusado() -> None:
    with pytest.raises(DuplicateEntityIdError, match="AssignmentId"):
        _demanda(_alocacao("a1", "ana"), _alocacao("a2", "bia"), _alocacao("a1", "caio"))


def test_tres_alocacoes_distintas_sao_aceitas() -> None:
    demanda = _demanda(_alocacao("a1", "ana"), _alocacao("a2", "bia"), _alocacao("a3", "caio"))
    assert demanda.allocated == 3  # noqa: PLR2004


# --- allocated e N como alvo ----------------------------------------------------------


def test_allocated_conta_as_alocacoes() -> None:
    assert _demanda().allocated == 0
    assert _demanda(_alocacao("a1", "ana")).allocated == 1


def test_alocados_acima_de_n_sao_aceitos() -> None:
    # N é alvo, não teto (ADR 4.1.0003 (g)): sobre-cobertura é política da 4.2.
    demanda = ShiftDemand(
        id=_ID,
        job_function_id=_COZINHEIRO,
        quantity=DemandQuantity(0),
        assignments=(_alocacao("a1", "ana"), _alocacao("a2", "bia")),
    )
    assert demanda.allocated > demanda.quantity.value


def test_assignments_e_tupla() -> None:
    assert isinstance(_demanda(_alocacao("a1", "ana")).assignments, tuple)
    assert isinstance(
        _demanda(_alocacao("a1", "ana")).with_assignment(_alocacao("a2", "bia")).assignments, tuple
    )


# --- transições: nova instância, original intacta, revalidação ------------------------


def test_with_quantity_devolve_nova_instancia() -> None:
    original = _demanda(_alocacao("a1", "ana"), _alocacao("a2", "bia"))
    reduzida = original.with_quantity(DemandQuantity(1))
    assert reduzida is not original
    assert reduzida.quantity == DemandQuantity(1)
    assert reduzida.assignments == original.assignments
    assert original.quantity == _DOIS


def test_with_assignment_acrescenta_no_fim() -> None:
    original = _demanda(_alocacao("a1", "ana"))
    nova = _alocacao("a2", "bia")
    acrescida = original.with_assignment(nova)
    assert acrescida is not original
    assert acrescida.assignments[-1] is nova
    assert acrescida.allocated == 2  # noqa: PLR2004
    assert original.allocated == 1


def test_with_assignment_de_funcionario_repetido_e_recusado_na_revalidacao() -> None:
    original = _demanda(_alocacao("a1", "ana"), _alocacao("a2", "bia"))
    with pytest.raises(DuplicateAssignmentError):
        original.with_assignment(_alocacao("a3", "ana"))
    assert original.allocated == 2  # noqa: PLR2004


def test_with_assignment_de_id_repetido_e_recusado_na_revalidacao() -> None:
    with pytest.raises(DuplicateEntityIdError):
        _demanda(_alocacao("a1", "ana")).with_assignment(_alocacao("a1", "bia"))


def test_without_assignment_retira_so_a_alocacao_do_id() -> None:
    a1, a2, a3 = _alocacao("a1", "ana"), _alocacao("a2", "bia"), _alocacao("a3", "caio")
    original = _demanda(a1, a2, a3)
    reduzida = original.without_assignment(AssignmentId("a2"))
    assert reduzida is not original
    assert reduzida.assignments == (a1, a3)
    assert original.assignments == (a1, a2, a3)


def test_without_assignment_de_id_inexistente_e_no_op_silencioso() -> None:
    # A recusa AssignmentNotFoundError é da raiz (unassign).
    original = _demanda(_alocacao("a1", "ana"))
    assert original.without_assignment(AssignmentId("nao-existe")).assignments == (
        original.assignments
    )


# --- CA22: ShiftDemandId e JobFunctionId ----------------------------------------------


@pytest.mark.parametrize("vazio", ["", "   "])
def test_shift_demand_id_vazio_e_recusado(vazio: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="demanda"):
        ShiftDemand(id=ShiftDemandId(vazio), job_function_id=_COZINHEIRO, quantity=_DOIS)


@pytest.mark.parametrize("vazio", ["", "   "])
def test_job_function_id_vazio_e_recusado(vazio: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="função"):
        ShiftDemand(id=_ID, job_function_id=JobFunctionId(vazio), quantity=_DOIS)


# --- CA15: frozen e identidade por id -------------------------------------------------


def test_demanda_e_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _demanda().quantity = DemandQuantity(5)  # type: ignore[misc]


def test_igualdade_e_hash_por_id_ignoram_o_conteudo() -> None:
    a = _demanda()
    b = ShiftDemand(
        id=_ID,
        job_function_id=JobFunctionId("atendente"),
        quantity=DemandQuantity(9),
        assignments=(_alocacao("a1", "ana"),),
    )
    assert a == b
    assert hash(a) == hash(b)
    assert a != ShiftDemand(id=ShiftDemandId("dem-2"), job_function_id=_COZINHEIRO, quantity=_DOIS)
    assert a.__eq__("dem-1") is NotImplemented

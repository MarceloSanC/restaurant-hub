"""Testes da entidade Assignment (entities/assignment.py).

CA14 no lado da entidade (defaults e transições), o piso do intervalo da
alocação, CA22 para `AssignmentId`/`EmployeeId` e CA15 no que cabe (frozen e
identidade por id). O teto do intervalo é da `ShiftBand` (Task 07).
"""

import dataclasses
import inspect

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidAssignmentBreakError,
    InvalidIdentifierError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)

pytestmark = pytest.mark.unit

_ID = AssignmentId("aloc-1")
_ANA = EmployeeId("ana")

# Os métodos públicos que a v1 declara para a alocação (concept §4). A lista é
# cobrada contra a classe por introspecção: um `declare_function_exception`
# inventado reprova aqui (CA14 — estado da v1, não irrevogabilidade).
_METODOS_PUBLICOS = {"declare_workload_counting", "declare_break"}


def _alocacao(**campos: object) -> Assignment:
    base: dict[str, object] = {"id": _ID, "employee_id": _ANA}
    base.update(campos)
    return Assignment(**base)  # type: ignore[arg-type]


# --- CA14: as três marcas -------------------------------------------------------------


def test_defaults_das_tres_marcas() -> None:
    alocacao = Assignment(id=_ID, employee_id=_ANA)
    assert alocacao.counts_toward_workload is True
    assert alocacao.function_exception is False
    assert alocacao.break_minutes is None


def test_marcas_passadas_sao_gravadas() -> None:
    alocacao = Assignment(
        id=_ID,
        employee_id=_ANA,
        counts_toward_workload=False,
        function_exception=True,
        break_minutes=30,
    )
    assert alocacao.counts_toward_workload is False
    assert alocacao.function_exception is True
    assert alocacao.break_minutes == 30  # noqa: PLR2004


@pytest.mark.parametrize("inicial", [True, False])
def test_declare_workload_counting_alterna(inicial: bool) -> None:
    original = Assignment(id=_ID, employee_id=_ANA, counts_toward_workload=inicial)
    alternada = original.declare_workload_counting(not inicial)
    assert alternada.counts_toward_workload is (not inicial)
    assert original.counts_toward_workload is inicial
    assert alternada is not original


def test_declare_break_declara_e_limpa_com_none() -> None:
    original = Assignment(id=_ID, employee_id=_ANA)
    declarada = original.declare_break(60)
    assert declarada.break_minutes == 60  # noqa: PLR2004
    assert original.break_minutes is None
    limpa = declarada.declare_break(None)
    assert limpa.break_minutes is None
    assert declarada.break_minutes == 60  # noqa: PLR2004


def test_declare_break_zero_e_declaracao_e_nao_ausencia() -> None:
    assert Assignment(id=_ID, employee_id=_ANA).declare_break(0).break_minutes == 0


def test_transicoes_preservam_as_outras_marcas() -> None:
    original = Assignment(
        id=_ID, employee_id=_ANA, counts_toward_workload=False, function_exception=True
    )
    com_pausa = original.declare_break(15)
    assert com_pausa.counts_toward_workload is False
    assert com_pausa.function_exception is True
    contando = com_pausa.declare_workload_counting(True)
    assert contando.function_exception is True
    assert contando.break_minutes == 15  # noqa: PLR2004


def test_superficie_publica_da_v1_nao_altera_function_exception() -> None:
    publicos = {
        nome
        for nome, _ in inspect.getmembers(Assignment, inspect.isfunction)
        if not nome.startswith("_")
    }
    assert publicos == _METODOS_PUBLICOS


# --- piso do intervalo ----------------------------------------------------------------


def test_intervalo_negativo_e_recusado() -> None:
    with pytest.raises(InvalidAssignmentBreakError, match="negativo"):
        Assignment(id=_ID, employee_id=_ANA, break_minutes=-1)


def test_declare_break_revalida_o_piso() -> None:
    with pytest.raises(InvalidAssignmentBreakError, match="negativo"):
        Assignment(id=_ID, employee_id=_ANA).declare_break(-1)


def test_intervalo_alto_nao_e_recusado_aqui() -> None:
    # O teto (< nominal_minutes) só a faixa conhece (Task 07).
    assert Assignment(id=_ID, employee_id=_ANA, break_minutes=10_000).break_minutes == 10_000  # noqa: PLR2004


# --- CA22: AssignmentId e EmployeeId --------------------------------------------------


@pytest.mark.parametrize("campo", ["id", "employee_id"])
@pytest.mark.parametrize("vazio", ["", "   "])
def test_identificador_vazio_ou_so_espaco_e_recusado(campo: str, vazio: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        _alocacao(**{campo: vazio})


# --- CA15: frozen e identidade por id -------------------------------------------------


def test_alocacao_e_frozen() -> None:
    alocacao = Assignment(id=_ID, employee_id=_ANA)
    with pytest.raises(dataclasses.FrozenInstanceError):
        alocacao.break_minutes = 30  # type: ignore[misc]


def test_igualdade_e_hash_por_id_ignoram_o_conteudo() -> None:
    a = Assignment(id=_ID, employee_id=_ANA)
    b = Assignment(
        id=_ID,
        employee_id=EmployeeId("bia"),
        counts_toward_workload=False,
        function_exception=True,
        break_minutes=30,
    )
    assert a == b
    assert hash(a) == hash(b)
    assert a != Assignment(id=AssignmentId("aloc-2"), employee_id=_ANA)


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    assert Assignment(id=_ID, employee_id=_ANA) != "aloc-1"
    assert Assignment(id=_ID, employee_id=_ANA).__eq__("aloc-1") is NotImplemented

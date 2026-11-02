"""Hierarquia dos erros da application de scheduling (concept 4.3 §4).

Varredura por introspecção do módulo: classe nova que esqueça a raiz quebra aqui,
em vez de virar 500 na borda (ADR 2.2.0003).
"""

import inspect
from datetime import date
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.application import errors
from restaurant_hub.features.scheduling.domain.exceptions.errors import SchedulingError
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import AssignmentId
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from restaurant_hub.shared.domain.exceptions.base import NotFoundError

pytestmark = pytest.mark.unit

_NOT_FOUND = {
    errors.ScheduleNotFoundError,
    errors.StaffMemberNotFoundError,
    errors.JobFunctionNotFoundError,
}
_TOTAL = 12


def _classes() -> list[type]:
    return [
        valor
        for _, valor in inspect.getmembers(errors, inspect.isclass)
        if valor.__module__ == errors.__name__
    ]


def test_o_modulo_declara_os_doze_erros_do_concept() -> None:
    assert len(_classes()) == _TOTAL


@pytest.mark.parametrize("classe", _classes(), ids=lambda c: c.__name__)
def test_todo_erro_herda_de_scheduling_error(classe: type) -> None:
    assert issubclass(classe, SchedulingError)


@pytest.mark.parametrize("classe", _classes(), ids=lambda c: c.__name__)
def test_so_os_tres_nao_encontrados_herdam_de_not_found(classe: type) -> None:
    assert issubclass(classe, NotFoundError) is (classe in _NOT_FOUND)


@pytest.mark.parametrize("classe", sorted(_NOT_FOUND, key=lambda c: c.__name__))
def test_a_raiz_do_bc_vem_antes_do_not_found_na_mro(classe: type) -> None:
    mro = classe.__mro__
    assert mro.index(SchedulingError) < mro.index(NotFoundError)


def test_o_conflito_de_versao_carrega_a_versao_atual() -> None:
    erro = errors.ScheduleVersionConflictError(expected_version=2, current_version=5)
    assert (erro.expected_version, erro.current_version) == (2, 5)


def test_as_recusas_de_violacao_carregam_as_violacoes() -> None:
    violacao = Violation(
        policy=PolicyKind.OVERLAP,
        mode=EnforcementMode.BLOCK,
        employee_id=None,
        demand_id=None,
        operational_days=(date(2026, 11, 2),),
        assignment_ids=frozenset(),
        observed=Decimal(1),
        limit=Decimal(0),
    )
    assert errors.BlockingViolationsError((violacao,)).violations == (violacao,)
    assert errors.UnacknowledgedViolationsError((violacao,)).violations == (violacao,)


def test_d3_carrega_contagem_e_ids_de_alocacao() -> None:
    ids = (AssignmentId("a1"), AssignmentId("a2"))
    erro = errors.InactiveAllocationsInUseError(ids)
    assert erro.assignment_ids == ids
    assert erro.count == len(ids)


def test_registro_ausente_carrega_os_ids_das_alocacoes() -> None:
    ids = (AssignmentId("a1"),)
    assert errors.MissingStaffRecordsError(ids).assignment_ids == ids


def test_id_em_uso_diz_o_tipo_e_o_valor() -> None:
    erro = errors.IdentifierInUseError("AssignmentId", "a1")
    assert (erro.id_type, erro.value) == ("AssignmentId", "a1")

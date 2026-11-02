"""Hierarquia dos erros da application de scheduling (concept 4.3 §4).

Varredura por introspecção do módulo: classe nova que esqueça a raiz quebra aqui.
Cada erro tem **uma** raiz, escolhida pelo significado (ADR 3.9.0001): a partição
domínio e aplicação é travada por igualdade de conjuntos.
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
from restaurant_hub.shared.application.errors import ApplicationError
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit

# Falhas que não são regra (concept 3.9 §4): lookup, id do cliente que colide, pedido
# malformado, insumo de staff incompleto.
_DE_APLICACAO = {
    errors.ScheduleNotFoundError,
    errors.StaffMemberNotFoundError,
    errors.JobFunctionNotFoundError,
    errors.IdentifierInUseError,
    errors.InvalidScheduleRequestError,
    errors.MissingStaffRecordsError,
}
# Regras do produto: escalas não se sobrepõem, versão vigente (sponsor F8), violações,
# registro desligado.
_DE_DOMINIO = {
    errors.SchedulePeriodTakenError,
    errors.ScheduleVersionConflictError,
    errors.BlockingViolationsError,
    errors.UnacknowledgedViolationsError,
    errors.InactiveStaffMemberError,
    errors.InactiveAllocationsInUseError,
}
_NOMES = {
    "ScheduleNotFoundError",
    "ScheduleVersionConflictError",
    "SchedulePeriodTakenError",
    "IdentifierInUseError",
    "BlockingViolationsError",
    "UnacknowledgedViolationsError",
    "StaffMemberNotFoundError",
    "InactiveStaffMemberError",
    "JobFunctionNotFoundError",
    "InactiveAllocationsInUseError",
    "MissingStaffRecordsError",
    "InvalidScheduleRequestError",
}


def _classes() -> list[type]:
    return [
        valor
        for _, valor in inspect.getmembers(errors, inspect.isclass)
        # A raiz de aplicação (Stage 3.9) não é um erro do concept 4.3: é o tipo
        # sobre o qual a Stage 4.5 registrará o handler, e tem teste próprio.
        if valor.__module__ == errors.__name__ and valor is not errors.SchedulingApplicationError
    ]


def test_o_modulo_declara_os_doze_erros_do_concept() -> None:
    assert {c.__name__ for c in _classes()} == _NOMES


def test_a_particao_dominio_aplicacao_e_exata() -> None:
    assert not _DE_DOMINIO & _DE_APLICACAO
    assert set(_classes()) == _DE_DOMINIO | _DE_APLICACAO


@pytest.mark.parametrize("classe", _classes(), ids=lambda c: c.__name__)
def test_cada_erro_tem_so_a_raiz_da_sua_lista(classe: type) -> None:
    if classe in _DE_DOMINIO:
        assert classe.__bases__ == (SchedulingError,)
        assert not issubclass(classe, ApplicationError)
    else:
        assert classe.__bases__ == (errors.SchedulingApplicationError,)
        assert not issubclass(classe, DomainError)


def test_a_raiz_de_aplicacao_e_filha_direta_de_application_error() -> None:
    assert errors.SchedulingApplicationError.__bases__ == (ApplicationError,)


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

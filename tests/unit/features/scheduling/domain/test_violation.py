"""Testes da Violation e da sua identidade (value_objects/violation.py) — CA11 (forma).

A tabela de §5.8 do concept 4.2 decide, por política, se as alocações entram na
`key`. Aqui ela é cobrada sobre os **nove** `PolicyKind`, derivada do enum: uma
política nova sem decisão explícita reprova em vez de cair num default.
"""

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import (
    Violation,
    ViolationKey,
)

pytestmark = pytest.mark.unit

_COM_ALOCACOES_NA_CHAVE = {
    PolicyKind.OVERLAP: True,
    PolicyKind.UNAVAILABILITY: True,
    PolicyKind.REST_BETWEEN_SHIFTS: False,
    PolicyKind.DAILY_CAP: False,
    PolicyKind.WEEKLY_CAP: False,
    PolicyKind.WORKLOAD: False,
    PolicyKind.FUNCTION_MISMATCH: True,
    PolicyKind.OVER_COVERAGE: True,
    PolicyKind.BREAK_DIVERGENCE: True,
}

_DIA = date(2026, 9, 28)
_ALOCACOES = frozenset({AssignmentId("a1"), AssignmentId("a2")})


def _violacao(policy: PolicyKind, **campos: object) -> Violation:
    base: dict[str, object] = {
        "policy": policy,
        "mode": EnforcementMode.WARN,
        "employee_id": EmployeeId("ana"),
        "demand_id": None,
        "operational_days": (_DIA,),
        "assignment_ids": _ALOCACOES,
        "observed": Decimal(700),
        "limit": Decimal(600),
    }
    base.update(campos)
    return Violation(**base)  # type: ignore[arg-type]


def test_a_tabela_de_decisao_cobre_todo_policy_kind() -> None:
    assert set(_COM_ALOCACOES_NA_CHAVE) == set(PolicyKind)


@pytest.mark.parametrize(("policy", "com_alocacoes"), list(_COM_ALOCACOES_NA_CHAVE.items()))
def test_a_key_leva_as_alocacoes_so_nas_politicas_da_tabela(
    policy: PolicyKind, com_alocacoes: bool
) -> None:
    key = _violacao(policy).key

    assert key == ViolationKey(
        policy=policy,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=(_DIA,),
        assignment_ids=_ALOCACOES if com_alocacoes else frozenset(),
    )


def test_a_key_ignora_modo_e_medida() -> None:
    uma = _violacao(PolicyKind.DAILY_CAP)
    outra = _violacao(
        PolicyKind.DAILY_CAP,
        mode=EnforcementMode.BLOCK,
        observed=Decimal(900),
        limit=Decimal(480),
    )

    assert uma != outra
    assert uma.key == outra.key


def test_a_key_agregada_ignora_o_conjunto_de_alocacoes() -> None:
    uma = _violacao(PolicyKind.WEEKLY_CAP)
    outra = _violacao(PolicyKind.WEEKLY_CAP, assignment_ids=frozenset({AssignmentId("a9")}))

    assert uma.key == outra.key


def test_a_key_por_alocacao_distingue_conjuntos() -> None:
    uma = _violacao(PolicyKind.OVER_COVERAGE, employee_id=None, demand_id=ShiftDemandId("d1"))
    outra = _violacao(
        PolicyKind.OVER_COVERAGE,
        employee_id=None,
        demand_id=ShiftDemandId("d1"),
        assignment_ids=_ALOCACOES | {AssignmentId("a3")},
    )

    assert uma.key != outra.key


def test_a_key_distingue_dia_sujeito_e_politica() -> None:
    base = _violacao(PolicyKind.DAILY_CAP).key

    assert _violacao(PolicyKind.DAILY_CAP, operational_days=(date(2026, 9, 29),)).key != base
    assert _violacao(PolicyKind.DAILY_CAP, employee_id=EmployeeId("bruno")).key != base
    assert _violacao(PolicyKind.WEEKLY_CAP).key != base


def test_a_key_distingue_a_demanda_da_sobre_cobertura() -> None:
    uma = _violacao(PolicyKind.OVER_COVERAGE, employee_id=None, demand_id=ShiftDemandId("d1"))
    outra = _violacao(PolicyKind.OVER_COVERAGE, employee_id=None, demand_id=ShiftDemandId("d2"))

    assert (uma.key.demand_id, outra.key.demand_id) == ("d1", "d2")
    assert uma.key != outra.key


def test_a_violacao_nao_carrega_texto_livre() -> None:
    # Concept 4.2 §5.12: a mensagem é da borda; um campo `message` entraria aqui.
    assert {campo.name for campo in dataclasses.fields(Violation)} == {
        "policy",
        "mode",
        "employee_id",
        "demand_id",
        "operational_days",
        "assignment_ids",
        "observed",
        "limit",
    }

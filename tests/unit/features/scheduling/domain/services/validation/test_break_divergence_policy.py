"""Testes da política de divergência de intervalo — CA3, CA4, CA11, CA16."""

from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation import (
    break_divergence_policy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.unit.features.scheduling.domain.services.validation.scenario import (
    SEGUNDA,
    Turno,
    config,
    contexto,
    em,
    escala,
    fatos,
)

pytestmark = pytest.mark.unit

_POLITICA = break_divergence_policy.BreakDivergencePolicy()


def _avaliar(*turnos: Turno) -> tuple[Violation, ...]:
    return _POLITICA.evaluate(contexto(escala(turnos)), config())


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.BREAK_DIVERGENCE


def test_intervalo_da_alocacao_diferente_do_da_faixa_viola_com_os_dois_valores() -> None:
    (violacao,) = _avaliar(
        Turno("ana", em(2, 16), em(3, 0), band_break=0, alloc_break=60),
        Turno("bruno", em(2, 16), em(3, 0), band_break=0),
    )

    assert violacao == Violation(
        policy=PolicyKind.BREAK_DIVERGENCE,
        mode=EnforcementMode.WARN,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=(SEGUNDA + timedelta(days=2),),
        assignment_ids=frozenset({AssignmentId("s-a0")}),
        observed=Decimal(60),
        limit=Decimal(0),
    )
    assert violacao.key.assignment_ids == {AssignmentId("s-a0")}


def test_intervalo_da_alocacao_menor_que_o_da_faixa_tambem_viola() -> None:
    (violacao,) = _avaliar(Turno("ana", em(0, 8), em(0, 16), band_break=60, alloc_break=30))

    assert (violacao.observed, violacao.limit) == (Decimal(30), Decimal(60))


def test_intervalo_igual_ao_da_faixa_ou_herdado_nao_viola() -> None:
    assert _avaliar(Turno("ana", em(0, 8), em(0, 16), band_break=60, alloc_break=60)) == ()
    assert _avaliar(Turno("ana", em(0, 8), em(0, 16), band_break=60)) == ()


def test_ignora_a_vizinha_e_o_inativo() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    anterior = escala(
        [Turno("ana", em(0, 8, base=anterior_dia), em(0, 16, base=anterior_dia), alloc_break=30)],
        schedule_id="p",
        first_day=anterior_dia,
    )
    inativo = escala([Turno("bruno", em(0, 8), em(0, 16), alloc_break=30)])

    assert _POLITICA.evaluate(contexto(escala([]), previous=anterior), config()) == ()
    assert _POLITICA.evaluate(contexto(inativo, fatos("bruno", ativo=False)), config()) == ()


def test_o_modo_vem_da_config() -> None:
    bloqueio = config(break_divergence=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK))
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16), alloc_break=30)])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), bloqueio)

    assert violacao.mode is EnforcementMode.BLOCK

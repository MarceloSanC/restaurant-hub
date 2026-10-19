"""Testes da política de carga contratada — CA3, CA4, CA6, CA11, CA16."""

from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation.workload_policy import (
    WorkloadPolicy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
    WorkloadDirection,
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

_POLITICA = WorkloadPolicy()
_DIAS_DA_SEMANA = tuple(SEGUNDA + timedelta(days=indice) for indice in range(7))
_AMBOS = WorkloadDirection.BOTH


def _cinco_dias(minutos_extras: int = 0, *, counts: bool = True) -> list[Turno]:
    """Cinco turnos de 8h (40h) de segunda a sexta; o de sexta com `minutos_extras`."""
    turnos = [Turno("ana", em(dia, 8), em(dia, 16)) for dia in range(4)]
    fim = em(4, 16) + timedelta(minutes=minutos_extras)
    return [*turnos, Turno("ana", em(4, 8), fim, counts=counts)]


def _avaliar(
    turnos: list[Turno], horas: str | None = "40", **campos: object
) -> tuple[Violation, ...]:
    carga = None if horas is None else Decimal(horas)
    return _POLITICA.evaluate(contexto(escala(turnos), fatos("ana", horas=carga)), config(**campos))


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.WORKLOAD


def test_excesso_sobre_a_carga_viola() -> None:
    (violacao,) = _avaliar(_cinco_dias(1))

    assert violacao == Violation(
        policy=PolicyKind.WORKLOAD,
        mode=EnforcementMode.WARN,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=_DIAS_DA_SEMANA,
        assignment_ids=frozenset(AssignmentId(f"s-a{indice}") for indice in range(5)),
        observed=Decimal(2401),
        limit=Decimal(2400),
    )
    assert violacao.key.assignment_ids == frozenset()


def test_igual_a_carga_nao_viola() -> None:
    assert _avaliar(_cinco_dias()) == ()


def test_tolerancia_configurada_vale_e_e_estrita() -> None:
    assert _avaliar(_cinco_dias(60), workload_tolerance_minutes=60) == ()
    (violacao,) = _avaliar(_cinco_dias(61), workload_tolerance_minutes=60)
    assert violacao.observed == Decimal(2461)


def test_alocacao_que_nao_conta_fica_fora_da_soma_e_da_violacao() -> None:
    assert _avaliar(_cinco_dias(60, counts=False)) == ()
    (violacao,) = _avaliar([*_cinco_dias(), Turno("ana", em(5, 8), em(5, 9), counts=True)])
    assert AssignmentId("s-a5") in violacao.assignment_ids


def test_nao_conta_nao_entra_em_assignment_ids() -> None:
    turnos = [*_cinco_dias(1), Turno("ana", em(5, 8), em(5, 12), counts=False)]

    (violacao,) = _avaliar(turnos)

    assert violacao.observed == Decimal(2401)
    assert AssignmentId("s-a5") not in violacao.assignment_ids


def test_sob_demanda_nao_e_sujeito() -> None:
    assert _avaliar(_cinco_dias(600), horas=None) == ()
    assert _avaliar([], horas=None, workload_direction=_AMBOS) == ()


def test_inativo_nao_e_sujeito() -> None:
    contexto_ = contexto(escala([]), fatos("ana", horas=Decimal(40), ativo=False))

    assert _POLITICA.evaluate(contexto_, config(workload_direction=_AMBOS)) == ()


def test_excesso_ignora_falta() -> None:
    assert _avaliar(_cinco_dias()[:4]) == ()


def test_ambos_aponta_a_falta() -> None:
    (violacao,) = _avaliar(_cinco_dias()[:4], workload_direction=_AMBOS)

    assert (violacao.observed, violacao.limit) == (Decimal(1920), Decimal(2400))


def test_ambos_aponta_o_registro_fixo_sem_nenhuma_alocacao() -> None:
    (violacao,) = _avaliar([], workload_direction=_AMBOS)

    assert violacao.assignment_ids == frozenset()
    assert (violacao.observed, violacao.limit) == (Decimal(0), Decimal(2400))


def test_ambos_respeita_a_tolerancia_dos_dois_lados() -> None:
    campos: dict[str, object] = {"workload_direction": _AMBOS, "workload_tolerance_minutes": 30}

    assert _avaliar(_cinco_dias(-30), **campos) == ()
    assert _avaliar(_cinco_dias(30), **campos) == ()
    assert len(_avaliar(_cinco_dias(-31), **campos)) == 1
    assert len(_avaliar(_cinco_dias(31), **campos)) == 1


def test_carga_fracionaria_e_exata() -> None:
    meia = [Turno("ana", em(0, 8), em(0, 18)), Turno("ana", em(1, 8), em(1, 20, 30))]

    assert _avaliar(meia, horas="22.5") == ()
    (violacao,) = _avaliar([*meia[:1], Turno("ana", em(1, 8), em(1, 20, 31))], horas="22.5")
    assert (violacao.observed, violacao.limit) == (Decimal(1351), Decimal("1350.0"))


def test_alocacao_da_vizinha_fica_fora_da_soma() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    anterior = escala(
        [Turno("ana", em(0, 8, base=anterior_dia), em(0, 18, base=anterior_dia))],
        schedule_id="p",
        first_day=anterior_dia,
    )
    contexto_ = contexto(escala(_cinco_dias()), fatos("ana", horas=Decimal(40)), previous=anterior)

    assert _POLITICA.evaluate(contexto_, config()) == ()


def test_o_modo_vem_da_config() -> None:
    (violacao,) = _avaliar(
        _cinco_dias(1), workload=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK)
    )

    assert violacao.mode is EnforcementMode.BLOCK

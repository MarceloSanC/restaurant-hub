"""Testes do insumo do avaliador (services/validation/context.py) — CA9, CA10.

Cada linha de §6 do concept 4.2 sobre o insumo tem o seu teste; a projeção é
conferida contra as leituras da raiz (nenhuma aritmética de horas no contexto).
"""

import dataclasses
from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidEvaluationInputError,
)
from restaurant_hub.features.scheduling.domain.services.validation import (
    rest_between_shifts_policy,
)
from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from tests.unit.features.scheduling.domain.services.validation.scenario import (
    ATENDENTE,
    COZINHEIRO,
    SEGUNDA,
    Turno,
    config,
    contexto,
    em,
    escala,
    fatos,
)

pytestmark = pytest.mark.unit

_ANTERIOR = SEGUNDA - timedelta(days=7)
_SEGUINTE = SEGUNDA + timedelta(days=7)


def _semana(schedule_id: str = "s", first_day: date = SEGUNDA) -> Schedule:
    return escala(
        [Turno("ana", em(0, 8, base=first_day), em(0, 16, base=first_day), band_break=60)],
        schedule_id=schedule_id,
        first_day=first_day,
    )


def test_a_projecao_espelha_as_leituras_da_raiz() -> None:
    avaliada = escala(
        [
            Turno("ana", em(0, 8), em(0, 16), band_break=60, alloc_break=30, counts=False),
            Turno("bruno", em(1, 2), em(1, 6), function=ATENDENTE),
        ]
    )
    contexto_ = contexto(avaliada)

    ana, bruno = contexto_.allocations
    assert (ana.employee_id, ana.worked_minutes, ana.effective_break_minutes) == ("ana", 450, 30)
    assert (ana.band_break_minutes, ana.break_divergence, ana.counts_toward_workload) == (
        60,
        True,
        False,
    )
    assert ana.worked_minutes == avaliada.worked_minutes_of(ana.assignment_id)
    # Terça 02:00 é antes do corte (05:00): a faixa é do dia operacional de segunda.
    assert bruno.operational_day == SEGUNDA
    assert (bruno.break_divergence, bruno.counts_toward_workload) == (False, True)
    assert (bruno.band_break_minutes, bruno.effective_break_minutes) == (0, 0)
    assert (ana.in_evaluated, ana.schedule_id) == (True, "s")
    faixa_da_ana, faixa_do_bruno = avaliada.bands
    assert (ana.band_id, ana.time_range) == (faixa_da_ana.id, faixa_da_ana.time_range)
    assert (bruno.demand_id, bruno.job_function_id) == (
        faixa_do_bruno.demands[0].id,
        ATENDENTE,
    )
    assert ana.job_function_id == COZINHEIRO


def test_vizinhas_entram_em_all_allocations_e_nao_em_allocations() -> None:
    anterior = _semana("p", _ANTERIOR)
    seguinte = _semana("n", _SEGUINTE)
    contexto_ = contexto(_semana(), previous=anterior, next=seguinte)

    assert [vista.schedule_id for vista in contexto_.allocations] == ["s"]
    assert sorted(vista.schedule_id for vista in contexto_.all_allocations) == ["n", "p", "s"]
    assert {
        vista.in_evaluated for vista in contexto_.all_allocations if vista.schedule_id != "s"
    } == {False}


def test_inativo_some_da_projecao_e_dos_fatos_ativos() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16)), Turno("bruno", em(0, 8), em(0, 16))])
    contexto_ = contexto(avaliada, fatos("bruno", ativo=False))

    assert [vista.employee_id for vista in contexto_.allocations] == ["ana"]
    assert [vista.employee_id for vista in contexto_.all_allocations] == ["ana"]
    assert [fato.employee_id for fato in contexto_.active_facts] == ["ana"]
    assert contexto_.facts_of(EmployeeId("bruno")).active is False


def test_registro_alocado_sem_fatos_e_recusado() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])

    with pytest.raises(InvalidEvaluationInputError, match="sem fatos"):
        EvaluationContext(schedule=avaliada, facts=())


def test_registro_alocado_na_vizinha_sem_fatos_e_recusado() -> None:
    anterior = escala(
        [Turno("bruno", em(0, 8, base=_ANTERIOR), em(0, 16, base=_ANTERIOR))],
        schedule_id="p",
        first_day=_ANTERIOR,
    )

    with pytest.raises(InvalidEvaluationInputError, match="'bruno' sem fatos"):
        EvaluationContext(schedule=escala([]), facts=(fatos("ana"),), previous=anterior)


def test_fatos_repetidos_sao_recusados() -> None:
    with pytest.raises(InvalidEvaluationInputError, match="repetidos"):
        EvaluationContext(schedule=escala([]), facts=(fatos("ana"), fatos("ana")))


@pytest.mark.parametrize("dias", [1, 6, 8, 14])
def test_periodo_que_nao_e_de_sete_dias_e_recusado(dias: int) -> None:
    avaliada = dataclasses.replace(escala([]), period=SchedulePeriod(first_day=SEGUNDA, days=dias))

    with pytest.raises(InvalidEvaluationInputError, match="7 dias"):
        EvaluationContext(schedule=avaliada, facts=())


@pytest.mark.parametrize(("lado", "base"), [("previous", _ANTERIOR), ("next", _SEGUINTE)])
def test_vizinha_com_periodo_que_nao_e_de_sete_dias_e_recusada(lado: str, base: date) -> None:
    vizinha = dataclasses.replace(
        escala([], schedule_id="v", first_day=base),
        period=SchedulePeriod(first_day=base, days=14),
    )

    with pytest.raises(InvalidEvaluationInputError, match="7 dias"):
        EvaluationContext(schedule=escala([]), facts=(), **{lado: vizinha})  # type: ignore[arg-type]


@pytest.mark.parametrize("endereco", [("t2", "u1"), ("t1", "u2")])
@pytest.mark.parametrize("lado", ["previous", "next"])
def test_vizinha_de_outro_tenant_ou_unidade_e_recusada(
    lado: str, endereco: tuple[str, str]
) -> None:
    base = _ANTERIOR if lado == "previous" else _SEGUINTE
    vizinha = escala([], schedule_id="v", first_day=base, endereco=endereco)

    with pytest.raises(InvalidEvaluationInputError, match="outro tenant ou unidade"):
        EvaluationContext(schedule=escala([]), facts=(), **{lado: vizinha})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("lado", "base", "trecho"),
    [
        ("previous", SEGUNDA - timedelta(days=14), "anterior"),
        ("previous", _SEGUINTE, "anterior"),
        ("next", SEGUNDA + timedelta(days=14), "seguinte"),
        ("next", _ANTERIOR, "seguinte"),
    ],
)
def test_vizinha_nao_adjacente_e_recusada(lado: str, base: object, trecho: str) -> None:
    vizinha = escala([], schedule_id="v", first_day=base)  # type: ignore[arg-type]

    with pytest.raises(InvalidEvaluationInputError, match=f"{trecho} não é adjacente"):
        EvaluationContext(schedule=escala([]), facts=(), **{lado: vizinha})  # type: ignore[arg-type]


@pytest.mark.parametrize(("lado", "base"), [("previous", _ANTERIOR), ("next", _SEGUINTE)])
def test_vizinha_com_o_id_da_avaliada_e_recusada(lado: str, base: object) -> None:
    vizinha = escala([], schedule_id="s", first_day=base)  # type: ignore[arg-type]

    with pytest.raises(InvalidEvaluationInputError, match="id da avaliada ou da outra"):
        EvaluationContext(schedule=escala([]), facts=(), **{lado: vizinha})  # type: ignore[arg-type]


def test_as_duas_vizinhas_com_o_mesmo_id_sao_recusadas() -> None:
    anterior = escala([], schedule_id="v", first_day=_ANTERIOR)
    seguinte = escala([], schedule_id="v", first_day=_SEGUINTE)

    with pytest.raises(InvalidEvaluationInputError, match="id da avaliada ou da outra"):
        EvaluationContext(schedule=escala([]), facts=(), previous=anterior, next=seguinte)


def test_assignment_id_repetido_entre_escalas_e_recusado() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])
    anterior = escala(
        [Turno("ana", em(0, 8, base=_ANTERIOR), em(0, 16, base=_ANTERIOR))],
        schedule_id="p",
        first_day=_ANTERIOR,
    )
    # Mesmo AssignmentId nas duas: reconstrói a anterior com o id da avaliada.
    id_da_avaliada = avaliada.bands[0].demands[0].assignments[0].id
    faixa = anterior.bands[0]
    demanda = faixa.demands[0]
    alocacao = dataclasses.replace(demanda.assignments[0], id=id_da_avaliada)
    anterior = dataclasses.replace(
        anterior,
        bands=(faixa.with_demands((dataclasses.replace(demanda, assignments=(alocacao,)),)),),
    )

    assert id_da_avaliada == AssignmentId("s-a0")
    with pytest.raises(InvalidEvaluationInputError, match="AssignmentId repetido"):
        EvaluationContext(schedule=avaliada, facts=(fatos("ana"),), previous=anterior)


def test_vizinhas_adjacentes_validas_sao_aceitas() -> None:
    contexto_ = EvaluationContext(
        schedule=escala([]),
        facts=(),
        previous=escala([], schedule_id="p", first_day=_ANTERIOR),
        next=escala([], schedule_id="n", first_day=_SEGUINTE),
    )

    assert contexto_.allocations == ()


def test_dia_operacional_da_vizinha_usa_o_calendario_dela() -> None:
    # A anterior tem corte às 06:00: a faixa de segunda 05:00-05:30 é do domingo dela.
    corte_seis = OperationalCalendar(week_start=Weekday.MONDAY, day_cutoff=DayCutoff(time(6, 0)))
    anterior = dataclasses.replace(
        escala([], schedule_id="p", first_day=_ANTERIOR), calendar=corte_seis
    )
    anterior = anterior.enable_band(ShiftBandId("p-b0"), TimeRange(em(0, 5), em(0, 5, 30)))
    anterior = anterior.declare_demand(
        ShiftDemandId("p-d0"), ShiftBandId("p-b0"), COZINHEIRO, DemandQuantity(1)
    )
    anterior = anterior.assign(AssignmentId("p-a0"), ShiftDemandId("p-d0"), EmployeeId("ana"))
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])
    contexto_ = contexto(avaliada, previous=anterior)

    (vista,) = (v for v in contexto_.all_allocations if not v.in_evaluated)
    (violacao,) = rest_between_shifts_policy.RestBetweenShiftsPolicy().evaluate(contexto_, config())

    assert vista.operational_day == SEGUNDA - timedelta(days=1)
    assert violacao.operational_days == (SEGUNDA - timedelta(days=1), SEGUNDA)
    assert violacao.observed == Decimal(150)

"""Leituras: `get_schedule`, `get_calendar`, `list_past_schedules` (concept 4.3 §4, §5.14-§5.17).

CA13, CA15, CA16, CA18, CA19, CA26, CA27.
"""

import dataclasses
from datetime import date, datetime, time, timedelta

import pytest

from restaurant_hub.features.scheduling.application.dtos.queries import (
    GetCalendarQuery,
    GetScheduleQuery,
    ListPastSchedulesQuery,
)
from restaurant_hub.features.scheduling.application.errors import (
    InvalidScheduleRequestError,
    MissingStaffRecordsError,
    ScheduleNotFoundError,
)
from restaurant_hub.features.scheduling.application.use_cases.get_calendar import (
    GetCalendarUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_schedule import (
    GetScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.list_past_schedules import (
    ListPastSchedulesUseCase,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
)
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    T1,
    T2,
    U1,
    U2,
    World,
    at,
    blank_change,
    member,
    schedule,
)

pytestmark = pytest.mark.unit

_SEMANA = timedelta(days=7)


def _semana(sid: str, first_day: date, *alocados: str, unit: UnitId = U1) -> Schedule:
    escala = (
        schedule(sid, first_day, unit=unit)
        .enable_band(
            ShiftBandId(f"{sid}-f"), TimeRange(start=at(first_day, 10), end=at(first_day, 14))
        )
        .declare_demand(ShiftDemandId(f"{sid}-d"), ShiftBandId(f"{sid}-f"), COOK, DemandQuantity(3))
    )
    for eid in alocados:
        escala = escala.assign(
            AssignmentId(f"{sid}-{eid}"), ShiftDemandId(f"{sid}-d"), EmployeeId(eid)
        )
    return dataclasses.replace(escala, version=1)


def _get(world: World, sid: str = "s1") -> GetScheduleQuery:
    return GetScheduleQuery(world.manager, T1, U1, ScheduleId(sid))


def _get_uc(world: World) -> GetScheduleUseCase:
    return GetScheduleUseCase(world.schedules, world.config, world.staff, world.guard)


def _cal_uc(world: World) -> GetCalendarUseCase:
    return GetCalendarUseCase(world.schedules, world.staff, world.guard)


def _past_uc(world: World) -> ListPastSchedulesUseCase:
    return ListPastSchedulesUseCase(world.schedules, world.guard)


# --- get_schedule ---------------------------------------------------------------------------


def test_ca13_get_omite_inativo_e_usa_o_nome_atual(world: World) -> None:
    world.staff.add_member(T1, member("caio", active=False))
    world.schedules.add(_semana("s1", MONDAY, "ana", "caio"), blank_change())
    world.staff.add_member(T1, member("ana", name="Ana Renomeada"), user_id="user-ana")
    resultado = _get_uc(world).execute(_get(world))
    (alocacao,) = resultado.bands[0].demands[0].assignments
    assert (alocacao.employee_id, alocacao.display_name) == ("ana", "Ana Renomeada")


def test_get_traz_as_violacoes_atuais_inclusive_as_induzidas_por_staff(world: World) -> None:
    world.schedules.add(_semana("s1", MONDAY, "ana"), blank_change())
    ferias = UnavailabilityWindow(start=at(MONDAY, 0), end=at(MONDAY + timedelta(days=2), 0))
    world.staff.add_member(T1, member("ana", unavailabilities=(ferias,)), user_id="user-ana")
    resultado = _get_uc(world).execute(_get(world))
    assert PolicyKind.UNAVAILABILITY in {v.policy for v in resultado.violations}
    assert "save" not in world.schedules.calls


@pytest.mark.parametrize("endereco", [(T1, U2), (T2, U1)], ids=["outra-unidade", "outro-tenant"])
def test_ca26_get_de_outra_unidade_ou_tenant_nao_e_encontrada(
    world: World, endereco: tuple[TenantId, UnitId]
) -> None:
    escala = dataclasses.replace(_semana("s1", MONDAY), tenant_id=endereco[0], unit_id=endereco[1])
    world.schedules.add(escala, blank_change())
    with pytest.raises(ScheduleNotFoundError):
        _get_uc(world).execute(_get(world))


def test_ca16_get_recusa_registro_ausente(world: World) -> None:
    world.schedules.add(_semana("s1", MONDAY, "ze"), blank_change())
    with pytest.raises(MissingStaffRecordsError) as excinfo:
        _get_uc(world).execute(_get(world))
    assert excinfo.value.assignment_ids == (AssignmentId("s1-ze"),)


# --- get_calendar ---------------------------------------------------------------------------


def _cal(world: World, primeiro: object, ultimo: object) -> GetCalendarQuery:
    return GetCalendarQuery(world.manager, T1, U1, primeiro, ultimo)  # type: ignore[arg-type]


def test_ca15_calendario_sobre_duas_escalas_so_com_as_faixas_do_recorte(world: World) -> None:
    world.staff.add_member(T1, member("caio", active=False))
    world.schedules.add(_semana("s2", MONDAY + _SEMANA, "ana", "caio"), blank_change())
    world.schedules.add(_semana("s1", MONDAY, "bia"), blank_change())
    world.schedules.add(_semana("s3", MONDAY + 2 * _SEMANA, "ana"), blank_change())
    cal = _cal_uc(world).execute(_cal(world, MONDAY, MONDAY + _SEMANA))
    assert [s.schedule_id for s in cal.schedules] == ["s1", "s2"]
    assert [f.band_id for f in cal.bands] == ["s1-f", "s2-f"]
    assert [a.employee_id for a in cal.bands[1].demands[0].assignments] == ["ana"]


@pytest.mark.parametrize(
    ("primeiro", "ultimo"),
    [
        (MONDAY, MONDAY + timedelta(days=42)),
        (MONDAY, MONDAY - timedelta(days=1)),
        (datetime.combine(MONDAY, time(0)), MONDAY),
    ],
    ids=["43-dias", "invertido", "datetime"],
)
def test_ca15_ca19_recorte_invalido_recusa_sem_ler(
    world: World, primeiro: object, ultimo: object
) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        _cal_uc(world).execute(_cal(world, primeiro, ultimo))
    assert world.port_calls() == []


def test_ca16_calendario_recusa_registro_ausente(world: World) -> None:
    world.schedules.add(_semana("s1", MONDAY, "ze"), blank_change())
    with pytest.raises(MissingStaffRecordsError):
        _cal_uc(world).execute(_cal(world, MONDAY, MONDAY))


# --- list_past_schedules ---------------------------------------------------------------------


def _past(world: World, antes: object, limite: int = 10) -> ListPastSchedulesQuery:
    return ListPastSchedulesQuery(world.manager, T1, U1, antes, limite)  # type: ignore[arg-type]


def test_ca18_anteriores_da_mais_recente_ate_o_limite(world: World) -> None:
    for sid, semanas in (("s1", 0), ("s3", 2), ("s2", 1)):
        world.schedules.add(_semana(sid, MONDAY + semanas * _SEMANA), blank_change())
    antes = MONDAY + 2 * _SEMANA
    assert [r.schedule_id for r in _past_uc(world).execute(_past(world, antes))] == ["s2", "s1"]
    assert [r.schedule_id for r in _past_uc(world).execute(_past(world, antes, 1))] == ["s2"]


@pytest.mark.parametrize(
    ("antes", "limite"),
    [(MONDAY, 0), (MONDAY, 53), (datetime.combine(MONDAY, time(0)), 10)],
    ids=["limite-0", "limite-53", "datetime"],
)
def test_ca18_ca19_pedido_invalido_recusa(world: World, antes: object, limite: int) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        _past_uc(world).execute(_past(world, antes, limite))


def test_ca13_get_nao_traz_violacao_de_registro_inativo_alocado(world: World) -> None:
    ferias = UnavailabilityWindow(start=at(MONDAY, 0), end=at(MONDAY + timedelta(days=2), 0))
    world.staff.add_member(T1, member("caio", active=False, unavailabilities=(ferias,)))
    world.schedules.add(_semana("s1", MONDAY, "caio"), blank_change())
    resultado = _get_uc(world).execute(_get(world))
    assert resultado.violations == ()

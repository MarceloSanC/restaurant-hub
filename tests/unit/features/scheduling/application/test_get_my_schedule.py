"""`get_my_schedule` (concept 4.3 §5.18; CA17, CA19)."""

import dataclasses
from datetime import date, datetime, time, timedelta

import pytest

from restaurant_hub.features.scheduling.application.dtos.queries import GetMyScheduleQuery
from restaurant_hub.features.scheduling.application.errors import InvalidScheduleRequestError
from restaurant_hub.features.scheduling.application.use_cases.get_my_schedule import (
    GetMyScheduleUseCase,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ShiftBandId,
    ShiftDemandId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    T1,
    U1,
    U2,
    World,
    at,
    blank_change,
    member,
    schedule,
)

pytestmark = pytest.mark.unit

_TERCA = MONDAY + timedelta(days=1)


def _escala(sid: str = "s1", unit: UnitId = U1, first_day: date = MONDAY) -> Schedule:
    terca = first_day + timedelta(days=1)
    escala = (
        schedule(sid, first_day, unit=unit)
        .enable_band(ShiftBandId("f-ter"), TimeRange(start=at(terca, 18), end=at(terca, 22)))
        .enable_band(
            ShiftBandId("f-seg"), TimeRange(start=at(first_day, 10), end=at(first_day, 14))
        )
        .declare_demand(ShiftDemandId("d-ter"), ShiftBandId("f-ter"), COOK, DemandQuantity(3))
        .declare_demand(ShiftDemandId("d-seg"), ShiftBandId("f-seg"), COOK, DemandQuantity(3))
        .assign(AssignmentId("a-ter"), ShiftDemandId("d-ter"), EmployeeId("ana"))
        .assign(AssignmentId("a-seg"), ShiftDemandId("d-seg"), EmployeeId("ana"))
        .assign(AssignmentId("a-bia"), ShiftDemandId("d-seg"), EmployeeId("bia"))
        .assign(AssignmentId("a-velho"), ShiftDemandId("d-ter"), EmployeeId("ana-antiga"))
    )
    return dataclasses.replace(escala, version=1)


def _uc(world: World) -> GetMyScheduleUseCase:
    return GetMyScheduleUseCase(world.schedules, world.staff, world.guard)


def _q(world: World, primeiro: object = MONDAY, ultimo: object = None) -> GetMyScheduleQuery:
    fim = ultimo if ultimo is not None else MONDAY + timedelta(days=6)
    return GetMyScheduleQuery(world.employee, T1, U1, primeiro, fim)  # type: ignore[arg-type]


def test_ca17_so_as_alocacoes_dos_registros_ativos_do_ator(world: World) -> None:
    # Um registro antigo, desligado, do mesmo login: não tem "minha escala".
    world.staff.add_member(T1, member("ana-antiga", active=False), user_id="user-ana")
    world.schedules.add(_escala(), blank_change())
    minha = _uc(world).execute(_q(world))
    assert [(t.assignment_id, t.job_function_name) for t in minha.shifts] == [
        ("a-seg", "Cozinheiro"),
        ("a-ter", "Cozinheiro"),
    ]


def test_ca17_recorte_filtra_pelo_dia_operacional(world: World) -> None:
    world.schedules.add(_escala(), blank_change())
    minha = _uc(world).execute(_q(world, _TERCA, _TERCA))
    assert [t.assignment_id for t in minha.shifts] == ["a-ter"]


def test_ca17_outra_unidade_nao_entra(world: World) -> None:
    world.guard.grant("view_own_schedule", tenant_id=T1, unit_id=U2)
    world.staff.add_member(T1, member("ana-u2", unit=U2), user_id="user-ana")
    world.schedules.add(_escala(), blank_change())
    world.schedules.add(_escala("s9", U2), blank_change())
    minha = _uc(world).execute(GetMyScheduleQuery(world.employee, T1, U2, MONDAY, MONDAY))
    assert minha.shifts == ()


def test_ca17_sem_registro_ativo_e_vazia_sem_ler_escalas(world: World) -> None:
    world.staff.add_member(T1, member("ana", active=False), user_id="user-ana")
    world.schedules.add(_escala(), blank_change())
    world.schedules.calls.clear()
    minha = _uc(world).execute(_q(world))
    assert minha.shifts == ()
    assert world.schedules.calls == []


@pytest.mark.parametrize(
    ("primeiro", "ultimo"),
    [
        (MONDAY, MONDAY + timedelta(days=42)),
        (_TERCA, MONDAY),
        (datetime.combine(MONDAY, time(0)), MONDAY),
    ],
    ids=["43-dias", "invertido", "datetime"],
)
def test_ca17_ca19_recorte_invalido_recusa(world: World, primeiro: object, ultimo: object) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        _uc(world).execute(_q(world, primeiro, ultimo))

"""`create_schedule` (concept 4.3 §5.3; CA01, CA19, CA26)."""

from datetime import datetime, time, timedelta
from uuid import UUID

import pytest

from restaurant_hub.features.scheduling.application.dtos.commands import CreateScheduleCommand
from restaurant_hub.features.scheduling.application.errors import (
    InvalidScheduleRequestError,
    SchedulePeriodTakenError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.use_cases.create_schedule import (
    CreateScheduleUseCase,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidSchedulePeriodError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import ScheduleId
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    ValidationConfig,
)
from tests.unit.features.scheduling.application.conftest import (
    MONDAY,
    NOW,
    T1,
    T2,
    U1,
    World,
    blank_change,
    schedule,
)

pytestmark = pytest.mark.unit

_PRIMEIRO_ID = ScheduleId(str(UUID(int=1)))


def _use_case(world: World) -> CreateScheduleUseCase:
    return CreateScheduleUseCase(
        schedules=world.schedules,
        config=world.config,
        ids=world.ids,
        clock=world.clock,
        guard=world.guard,
    )


def _comando(world: World, first_day: object = MONDAY) -> CreateScheduleCommand:
    return CreateScheduleCommand(
        actor=world.manager,
        tenant_id=T1,
        unit_id=U1,
        first_day=first_day,  # type: ignore[arg-type]
    )


def test_ca01_cria_vazia_na_versao_1_com_o_calendario_default(world: World) -> None:
    resumo = _use_case(world).execute(_comando(world))
    assert (resumo.schedule_id, resumo.version, resumo.first_day) == (_PRIMEIRO_ID, 1, MONDAY)
    assert resumo.last_day == MONDAY + timedelta(days=6)
    gravada = world.schedules.find_by_id(T1, U1, _PRIMEIRO_ID)
    assert gravada is not None
    assert gravada.bands == ()
    assert gravada.calendar == OperationalCalendar.default()


def test_ca01_grava_a_mudanca_de_criacao_com_autor_e_instante(world: World) -> None:
    _use_case(world).execute(_comando(world))
    (mudanca,) = world.schedules.changes_of(_PRIMEIRO_ID)
    assert (mudanca.author_user_id, mudanca.occurred_at, mudanca.previous_version) == (
        "user-ger",
        NOW,
        None,
    )
    assert (mudanca.operations, mudanca.acknowledged) == ((), ())


def test_ca26_usa_e_fotografa_o_calendario_gravado_do_tenant(world: World) -> None:
    domingo = MONDAY - timedelta(days=1)
    calendario = OperationalCalendar(week_start=Weekday.SUNDAY, day_cutoff=DayCutoff(at=time(4)))
    world.config.set_settings(
        T1, SchedulingSettings(calendar=calendario, validation=ValidationConfig.default())
    )
    world.config.set_settings(
        T2,
        SchedulingSettings(
            calendar=OperationalCalendar.default(), validation=ValidationConfig.default()
        ),
    )
    resumo = _use_case(world).execute(_comando(world, domingo))
    gravada = world.schedules.find_by_id(T1, U1, resumo.schedule_id)
    assert gravada is not None
    assert gravada.calendar == calendario


def test_ca01_primeiro_dia_desalinhado_recusa_sem_gravar(world: World) -> None:
    with pytest.raises(InvalidSchedulePeriodError):
        _use_case(world).execute(_comando(world, MONDAY + timedelta(days=1)))
    assert "add" not in world.schedules.calls


def test_ca01_dia_ja_coberto_recusa(world: World) -> None:
    world.schedules.add(schedule("s0", MONDAY), blank_change())
    with pytest.raises(SchedulePeriodTakenError):
        _use_case(world).execute(_comando(world))
    assert world.schedules.calls.count("add") == 1


def test_ca01_semana_seguinte_e_permitida(world: World) -> None:
    world.schedules.add(schedule("s0", MONDAY), blank_change())
    resumo = _use_case(world).execute(_comando(world, MONDAY + timedelta(days=7)))
    assert resumo.first_day == MONDAY + timedelta(days=7)


@pytest.mark.parametrize("dia", [datetime.combine(MONDAY, time(0)), "2026-11-02"])
def test_ca19_dia_que_nao_e_date_recusa(world: World, dia: object) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        _use_case(world).execute(_comando(world, dia))


def test_guard_que_nega_nao_toca_port_nem_relogio_nem_gerador(world: World) -> None:
    estranho = world.guard.issue("user-x", "t9")
    comando = CreateScheduleCommand(actor=estranho, tenant_id=T1, unit_id=U1, first_day=MONDAY)
    with pytest.raises(Exception) as excinfo:
        _use_case(world).execute(comando)
    assert excinfo.value is world.guard.authorization_error
    assert world.port_calls() == []
    assert world.clock.reads == 0
    assert world.ids.next_id() == UUID(int=1)


def test_ca01_dia_coberto_no_meio_do_periodo_recusa_sem_chamar_add(world: World) -> None:
    # Escala antiga fotografada com outro alinhamento (quinta a quarta).
    quinta = MONDAY + timedelta(days=3)
    antiga = Schedule(
        id=ScheduleId("s-antiga"),
        tenant_id=T1,
        unit_id=U1,
        period=SchedulePeriod(first_day=quinta),
        calendar=OperationalCalendar(
            week_start=Weekday.THURSDAY, day_cutoff=OperationalCalendar.default().day_cutoff
        ),
    )
    world.schedules.add(antiga, blank_change())
    with pytest.raises(SchedulePeriodTakenError):
        _use_case(world).execute(_comando(world))
    assert world.schedules.calls.count("add") == 1

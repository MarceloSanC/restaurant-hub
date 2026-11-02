"""Construtores e cenário semeado dos testes da application de scheduling.

Semana de referência: segunda 2026-11-02 a domingo 2026-11-08, calendário default
(segunda, corte às 05:00). Tenant `t1`, unidade `u1`; a gerente `user-ger` tem
`manage_schedule` e `view_schedule` em (t1, u1).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
    StaffMember,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from tests.fakes.features.scheduling.in_memory_access_guard import (
    FakeActor,
    InMemoryAccessGuard,
)
from tests.fakes.features.scheduling.in_memory_schedule_config_repository import (
    InMemoryScheduleConfigRepository,
)
from tests.fakes.features.scheduling.in_memory_schedule_repository import (
    InMemoryScheduleRepository,
)
from tests.fakes.features.scheduling.in_memory_staff_read import InMemoryStaffRead
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

T1, T2 = TenantId("t1"), TenantId("t2")
U1, U2 = UnitId("u1"), UnitId("u2")
MONDAY = date(2026, 11, 2)
NOW = datetime(2026, 11, 1, 12, 0)
COOK, WAITER = JobFunctionId("cozinheiro"), JobFunctionId("atendente")


def at(day: date, hour: int, minute: int = 0) -> datetime:
    """Instante ingênuo no dia civil dado."""
    return datetime.combine(day, time(hour, minute))


def member(  # noqa: PLR0913
    eid: str,
    unit: UnitId = U1,
    *,
    active: bool = True,
    functions: tuple[JobFunctionId, ...] = (COOK,),
    hours: Decimal | None = None,
    unavailabilities: tuple[UnavailabilityWindow, ...] = (),
    name: str | None = None,
) -> StaffMember:
    """Um registro de staff como scheduling o lê."""
    return StaffMember(
        employee_id=EmployeeId(eid),
        unit_id=unit,
        display_name=name if name is not None else eid.capitalize(),
        active=active,
        job_function_ids=frozenset(functions),
        contracted_weekly_hours=hours,
        unavailabilities=unavailabilities,
    )


def schedule(
    sid: str = "s1",
    first_day: date = MONDAY,
    *,
    tenant: TenantId = T1,
    unit: UnitId = U1,
) -> Schedule:
    """Escala vazia de 7 dias, calendário default."""
    return Schedule(
        id=ScheduleId(sid),
        tenant_id=tenant,
        unit_id=unit,
        period=SchedulePeriod(first_day=first_day),
        calendar=OperationalCalendar.default(),
    )


def blank_change(previous_version: int | None = None) -> ScheduleChange:
    """Mudança sem operações — para semear escalas pelo próprio port."""
    return ScheduleChange("user-seed", NOW, previous_version, (), ())


class SpyClock(FakeClock):
    """Relógio fixo que conta as leituras (CA03: nenhum relógio lido antes da decisão)."""

    def __init__(self, now: datetime) -> None:
        super().__init__(now)
        self.reads = 0

    def now(self) -> datetime:
        self.reads += 1
        return super().now()


@dataclass
class World:
    """Os fakes semeados e o ator da gerente."""

    guard: InMemoryAccessGuard
    staff: InMemoryStaffRead
    clock: SpyClock
    ids: FakeIdGenerator
    manager: FakeActor
    employee: FakeActor
    schedules: InMemoryScheduleRepository = field(default_factory=InMemoryScheduleRepository)
    config: InMemoryScheduleConfigRepository = field(
        default_factory=InMemoryScheduleConfigRepository
    )

    def port_calls(self) -> list[str]:
        """Toda chamada recebida pelos ports de dados (para "nada tocado")."""
        return [*self.schedules.calls, *self.config.calls, *self.staff.calls]


def new_world() -> World:
    """Fakes de guard, staff, relógio e ids, com o quadro base semeado."""
    guard = InMemoryAccessGuard()
    manager = guard.issue("user-ger", T1)
    employee = guard.issue("user-ana", T1)
    for permissao in (PERMISSION_MANAGE_SCHEDULE, PERMISSION_VIEW_SCHEDULE):
        guard.grant(permissao, tenant_id=T1, unit_id=U1)
    guard.grant(PERMISSION_VIEW_OWN_SCHEDULE, tenant_id=T1, unit_id=U1)
    staff = InMemoryStaffRead()
    staff.add_member(T1, member("ana"), user_id="user-ana")
    staff.add_member(T1, member("bia", functions=(WAITER,)))
    staff.add_job_function(T1, JobFunctionEntry(COOK, "Cozinheiro"))
    staff.add_job_function(T1, JobFunctionEntry(WAITER, "Atendente"))
    ids = FakeIdGenerator([UUID(int=n) for n in range(1, 20)])
    return World(
        guard=guard,
        staff=staff,
        clock=SpyClock(NOW),
        ids=ids,
        manager=manager,
        employee=employee,
    )


@pytest.fixture
def world() -> World:
    return new_world()


ONE_DAY = timedelta(days=1)

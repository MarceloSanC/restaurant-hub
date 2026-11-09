"""Montagem do insumo dos use cases de scheduling — num sítio só (concept 4.3 §5.12 a §5.16).

Módulo privado (precedente `identity/application/use_cases/_invitation.py`): fica fora da
varredura de use cases por começar com `_`. **Não escreve** — só lê ports; a escrita de
cada use case fica no próprio `execute` (regra 10 do `check_layout`).

- `settings_of`: a configuração gravada do tenant, ou os defaults de domínio — o único
  sítio desses defaults na application.
- `require_day`/`require_range`/`require_limit`: validação do pedido
  (`InvalidScheduleRequestError`). `datetime` é subclasse de `date`, então o tipo
  sozinho não barra um instante onde se pede um dia.
- `neighbours_of`: a anterior e a seguinte adjacentes (ADR 4.2.0002 §1).
- `load_staff`: o quadro de staff — quadro ativo (opcional) + alocados + alvos, unidos
  por `employee_id` com o de `list_members` prevalecendo; alocado ausente ⇒
  `MissingStaffRecordsError` com os ids das alocações (fail-closed, ADR 4.3.0003 §3).
- `facts_of`: os `EmployeeFacts` do avaliador, a partir do quadro.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from restaurant_hub.features.scheduling.application.errors import (
    InvalidScheduleRequestError,
    MissingStaffRecordsError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffMember,
    StaffReadPort,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    EmployeeFacts,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    ValidationConfig,
)

MAX_RANGE_DAYS = 42  # grade de mês de 6 semanas (concept §7 D-CAL)
MAX_PAST_LIMIT = 52  # um ano de semanas (concept §7 D-PAST)
_ONE_DAY = timedelta(days=1)


def settings_of(config: ScheduleConfigRepository, tenant_id: TenantId) -> SchedulingSettings:
    """A configuração do tenant, ou os defaults de domínio (concept §5.12)."""
    stored = config.find_settings(tenant_id)
    if stored is not None:
        return stored
    return SchedulingSettings(
        calendar=OperationalCalendar.default(), validation=ValidationConfig.default()
    )


def require_day(value: object, name: str) -> date:
    """O valor é um `date` puro — nunca um `datetime` (concept §5.15)."""
    if isinstance(value, datetime) or not isinstance(value, date):
        raise InvalidScheduleRequestError(f"{name} deve ser um dia (date), não {value!r}")
    return value


def require_range(first_day: object, last_day: object) -> tuple[date, date]:
    """Recorte de dias válido: `date`, first ≤ last, até 42 dias (concept §5.16)."""
    first = require_day(first_day, "first_day")
    last = require_day(last_day, "last_day")
    if first > last:
        raise InvalidScheduleRequestError("first_day depois de last_day")
    if (last - first).days + 1 > MAX_RANGE_DAYS:
        raise InvalidScheduleRequestError(f"o recorte passa de {MAX_RANGE_DAYS} dias")
    return first, last


def require_limit(limit: int) -> int:
    """`1 ≤ limit ≤ 52` (concept §5.17)."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAST_LIMIT:
        raise InvalidScheduleRequestError(f"limit deve estar entre 1 e {MAX_PAST_LIMIT}")
    return limit


def neighbours_of(
    schedules: ScheduleRepository, schedule: Schedule
) -> tuple[Schedule | None, Schedule | None]:
    """A escala que termina no dia anterior e a que começa no dia seguinte (§5.13)."""
    prior = schedule.period.first_day - _ONE_DAY
    evaluated_after = schedule.period.last_day + _ONE_DAY
    previous = next(
        (
            e
            for e in schedules.list_in_range(schedule.tenant_id, schedule.unit_id, prior, prior)
            if e.period.last_day == prior and e.id != schedule.id
        ),
        None,
    )
    following = next(
        (
            e
            for e in schedules.list_in_range(
                schedule.tenant_id, schedule.unit_id, evaluated_after, evaluated_after
            )
            if e.period.first_day == evaluated_after and e.id != schedule.id
        ),
        None,
    )
    return previous, following


@dataclass(frozen=True)
class StaffView:
    """O quadro de staff lido para um use case.

    Attributes:
        members: os registros por id (ativos e inativos que vieram).
        function_names: o catálogo do tenant, id → nome.
    """

    members: dict[EmployeeId, StaffMember]
    function_names: dict[JobFunctionId, str]


def allocations_of(
    schedules: Iterable[Schedule],
) -> list[tuple[AssignmentId, EmployeeId]]:
    """Todas as alocações (id, registro) das escalas dadas."""
    return [
        (allocation.id, allocation.employee_id)
        for sched in schedules
        for band in sched.bands
        for demand in band.demands
        for allocation in demand.assignments
    ]


def load_staff(  # noqa: PLR0913 — endereço (3) + escalas + alvos + o quadro ativo
    staff: StaffReadPort,
    tenant_id: TenantId,
    unit_id: UnitId,
    schedules: Iterable[Schedule],
    *,
    targets: frozenset[EmployeeId] = frozenset(),
    with_roster: bool,
) -> StaffView:
    """O quadro: quadro ativo (se pedido) + alocados + alvos, fail-closed no ausente."""
    allocations = allocations_of(schedules)
    allocated_ids = frozenset(eid for _, eid in allocations)
    members: dict[EmployeeId, StaffMember] = {}
    if with_roster:
        members.update({m.employee_id: m for m in staff.list_active_members(tenant_id, unit_id)})
    requested = allocated_ids | targets
    if requested:
        # `list_members` prevalece sobre o quadro ativo: é a leitura mais específica.
        members.update(
            {m.employee_id: m for m in staff.list_members(tenant_id, unit_id, requested)}
        )
    missing = tuple(sorted({aid for aid, eid in allocations if eid not in members}))
    if missing:
        raise MissingStaffRecordsError(missing)
    names = {f.job_function_id: f.name for f in staff.list_job_functions(tenant_id)}
    return StaffView(members=members, function_names=names)


def facts_of(view: StaffView) -> tuple[EmployeeFacts, ...]:
    """Os fatos do avaliador, um por registro do quadro, em ordem de id."""
    return tuple(
        EmployeeFacts(
            employee_id=m.employee_id,
            active=m.active,
            job_function_ids=m.job_function_ids,
            contracted_weekly_hours=m.contracted_weekly_hours,
            unavailabilities=m.unavailabilities,
        )
        for _, m in sorted(view.members.items())
    )

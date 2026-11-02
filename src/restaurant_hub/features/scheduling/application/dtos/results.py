"""Results — a saída dos use cases do BC scheduling (concept 4.3 §4).

Use case devolve DTO, nunca entidade (CLAUDE.md nota 6, LAYOUT §7). **Cada result é
construído num sítio só, e o sítio mora aqui** (regra 8 do `check_layout`): as funções
`to_*` são o único lugar do BC que lê o agregado e escreve DTO.

**Reconciliação na leitura** (ADR 4.1.0006; concept §5.14): os mapeadores recebem o
índice de staff (`employee_id → StaffMember`) e **omitem** a alocação de registro que
não esteja ativo nele. O nome de exibição é o atual; função fora do catálogo sai com
nome `None`. A recusa do registro ausente acontece antes, no use case (§5.12).

**Ordem determinística** (§5.20): faixas por (início, id); demandas por (função, id);
alocações por (nome, id); turnos por (início, id da alocação); escalas por first_day;
violações na ordem do avaliador.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffMember,
)
from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

StaffIndex = Mapping[EmployeeId, StaffMember]
FunctionNames = Mapping[JobFunctionId, str]


@dataclass(frozen=True)
class ScheduleSummaryResult:
    """Resumo de uma escala (sem faixas)."""

    schedule_id: ScheduleId
    tenant_id: TenantId
    unit_id: UnitId
    first_day: date
    last_day: date
    version: int


@dataclass(frozen=True)
class AssignmentResult:
    """Uma alocação de registro ativo."""

    assignment_id: AssignmentId
    employee_id: EmployeeId
    display_name: str
    counts_toward_workload: bool
    function_exception: bool
    break_minutes: int | None
    worked_minutes: int


@dataclass(frozen=True)
class DemandResult:
    """Uma demanda, com as alocações de registros ativos."""

    demand_id: ShiftDemandId
    job_function_id: JobFunctionId
    job_function_name: str | None
    quantity: int
    assignments: tuple[AssignmentResult, ...]


@dataclass(frozen=True)
class BandResult:
    """Uma faixa, com o seu dia operacional e as demandas."""

    band_id: ShiftBandId
    schedule_id: ScheduleId
    operational_day: date
    time_range: TimeRange
    demands: tuple[DemandResult, ...]


@dataclass(frozen=True)
class ScheduleResult:
    """A escala com faixas e as violações atuais."""

    summary: ScheduleSummaryResult
    bands: tuple[BandResult, ...]
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class EvaluationResult:
    """A escala resultante de um lote, com as violações **introduzidas** separadas."""

    schedule: ScheduleResult
    blocking: tuple[Violation, ...]
    warnings: tuple[Violation, ...]


@dataclass(frozen=True)
class CalendarResult:
    """As escalas que cruzam o recorte e as faixas cujo dia operacional cai nele."""

    first_day: date
    last_day: date
    schedules: tuple[ScheduleSummaryResult, ...]
    bands: tuple[BandResult, ...]


@dataclass(frozen=True)
class MyShiftResult:
    """Um turno do próprio ator."""

    schedule_id: ScheduleId
    band_id: ShiftBandId
    assignment_id: AssignmentId
    employee_id: EmployeeId
    operational_day: date
    start: datetime
    end: datetime
    job_function_id: JobFunctionId
    job_function_name: str | None
    worked_minutes: int


@dataclass(frozen=True)
class MyScheduleResult:
    """Os turnos do próprio ator no recorte."""

    first_day: date
    last_day: date
    shifts: tuple[MyShiftResult, ...]


# --- mapeadores (um sítio de construção por classe) ----------------------------------


def _visible(assignment: Assignment, staff: StaffIndex) -> bool:
    member = staff.get(assignment.employee_id)
    return member is not None and member.active


def to_schedule_summary_result(schedule: Schedule) -> ScheduleSummaryResult:
    """O resumo da escala."""
    return ScheduleSummaryResult(
        schedule_id=schedule.id,
        tenant_id=schedule.tenant_id,
        unit_id=schedule.unit_id,
        first_day=schedule.period.first_day,
        last_day=schedule.period.last_day,
        version=schedule.version,
    )


def _to_assignment_result(
    schedule: Schedule, assignment: Assignment, member: StaffMember
) -> AssignmentResult:
    return AssignmentResult(
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        display_name=member.display_name,
        counts_toward_workload=assignment.counts_toward_workload,
        function_exception=assignment.function_exception,
        break_minutes=assignment.break_minutes,
        worked_minutes=schedule.worked_minutes_of(assignment.id),
    )


def _to_demand_result(
    schedule: Schedule, demand: ShiftDemand, staff: StaffIndex, names: FunctionNames
) -> DemandResult:
    allocations = sorted(
        (
            _to_assignment_result(schedule, allocation, staff[allocation.employee_id])
            for allocation in demand.assignments
            if _visible(allocation, staff)
        ),
        key=lambda a: (a.display_name, a.assignment_id),
    )
    return DemandResult(
        demand_id=demand.id,
        job_function_id=demand.job_function_id,
        job_function_name=names.get(demand.job_function_id),
        quantity=demand.quantity.value,
        assignments=tuple(allocations),
    )


def _to_band_result(
    schedule: Schedule, band: ShiftBand, staff: StaffIndex, names: FunctionNames
) -> BandResult:
    demands = sorted(band.demands, key=lambda d: (d.job_function_id, d.id))
    return BandResult(
        band_id=band.id,
        schedule_id=schedule.id,
        operational_day=schedule.operational_day_of(band),
        time_range=band.time_range,
        demands=tuple(_to_demand_result(schedule, d, staff, names) for d in demands),
    )


def _bands_of(
    schedules: Iterable[Schedule],
    staff: StaffIndex,
    names: FunctionNames,
    first_day: date | None = None,
    last_day: date | None = None,
) -> tuple[BandResult, ...]:
    bands = [
        _to_band_result(sched, band, staff, names)
        for sched in schedules
        for band in sched.bands
        if first_day is None
        or last_day is None
        or first_day <= sched.operational_day_of(band) <= last_day
    ]
    return tuple(sorted(bands, key=lambda f: (f.time_range.start, f.band_id)))


def to_schedule_result(
    schedule: Schedule,
    staff: StaffIndex,
    names: FunctionNames,
    violations: tuple[Violation, ...],
) -> ScheduleResult:
    """A escala com as faixas e as violações dadas (as atuais, do avaliador)."""
    return ScheduleResult(
        summary=to_schedule_summary_result(schedule),
        bands=_bands_of((schedule,), staff, names),
        violations=violations,
    )


def to_evaluation_result(
    schedule: ScheduleResult,
    blocking: tuple[Violation, ...],
    warnings: tuple[Violation, ...],
) -> EvaluationResult:
    """A avaliação: a escala resultante e as introduzidas por modo."""
    return EvaluationResult(schedule=schedule, blocking=blocking, warnings=warnings)


def to_calendar_result(
    first_day: date,
    last_day: date,
    schedules: tuple[Schedule, ...],
    staff: StaffIndex,
    names: FunctionNames,
) -> CalendarResult:
    """O calendário do recorte — faixas cujo dia operacional cai em [first, last]."""
    return CalendarResult(
        first_day=first_day,
        last_day=last_day,
        schedules=tuple(
            to_schedule_summary_result(e)
            for e in sorted(schedules, key=lambda e: e.period.first_day)
        ),
        bands=_bands_of(schedules, staff, names, first_day, last_day),
    )


def _to_my_shift_result(
    schedule: Schedule,
    band: ShiftBand,
    demand: ShiftDemand,
    assignment: Assignment,
    names: FunctionNames,
) -> MyShiftResult:
    return MyShiftResult(
        schedule_id=schedule.id,
        band_id=band.id,
        assignment_id=assignment.id,
        employee_id=assignment.employee_id,
        operational_day=schedule.operational_day_of(band),
        start=band.time_range.start,
        end=band.time_range.end,
        job_function_id=demand.job_function_id,
        job_function_name=names.get(demand.job_function_id),
        worked_minutes=schedule.worked_minutes_of(assignment.id),
    )


def to_my_schedule_result(  # noqa: PLR0913 — recorte (2) + escalas + registros + índices (2)
    first_day: date,
    last_day: date,
    schedules: tuple[Schedule, ...],
    mine: frozenset[EmployeeId],
    staff: StaffIndex,
    names: FunctionNames,
) -> MyScheduleResult:
    """Os turnos dos registros `mine` **ativos** cujo dia operacional cai no recorte."""
    shifts = [
        _to_my_shift_result(sched, band, demand, allocation, names)
        for sched in schedules
        for band in sched.bands
        if first_day <= sched.operational_day_of(band) <= last_day
        for demand in band.demands
        for allocation in demand.assignments
        if allocation.employee_id in mine and _visible(allocation, staff)
    ]
    return MyScheduleResult(
        first_day=first_day,
        last_day=last_day,
        shifts=tuple(sorted(shifts, key=lambda t: (t.start, t.assignment_id))),
    )

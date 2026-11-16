"""Mapeamento domínio ↔ linha do BC scheduling, e o codec da trilha.

Funções puras: recebem linhas, devolvem domínio; recebem domínio, devolvem `dict` de
colunas. Nenhuma consulta, nenhuma conexão — testáveis sem banco (Task 04 da 4.4).

**Regra 1 — reidratar sempre pelo construtor** (concept 4.4 §5.8). `Schedule`, `ShiftBand`,
`ShiftDemand`, `Assignment`, `TimeRange`, `SchedulePeriod`, `OperationalCalendar` e
`ValidationConfig` validam no `__post_init__`; uma linha que viola invariante **levanta ao
ser lida**, em vez de entrar como estado válido. As regras internas do agregado que o
schema não expressa (par `(início, fim)` distinto, uma demanda por função na faixa, um
registro por faixa) só são barradas por aqui.

**Regra 2 — a ordem é a coluna `position`, não a ordem das linhas** (L-SC8). O mapper
grava a posição de cada item na tupla do pai e, na volta, ordena por ela: quem consulta
não precisa de `ORDER BY` para a fidelidade valer.

**Regra 3 — dois regimes de tempo, sem conversão de fuso** (ADR 4.1.0007, concept §5.12).
Faixas atravessam **ingênuas**, como saíram: `TimeRange` recusa aware. O carimbo da trilha
é instante absoluto e volta normalizado para UTC.

**Regra 4 — o formato JSON da trilha é contrato de dados** (concept §5.6, ADR 4.4.0002):
`kind` discrimina a operação; instantes em ISO 8601 ingênuo; `Decimal` como texto (o
`json` do psycopg o recusaria, e fração em `float` perderia a medida). O leitor ignora
chave que não conhece. Trocar nome de chave ou valor de `kind` exige migration dos dados.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    LIMIT_CHECKS,
    POLICY_FIELDS,
)
from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    ChangeDemandQuantity,
    DeclareAllocationBreak,
    DeclareDemand,
    DeclareWorkloadCounting,
    DisableBand,
    EnableBand,
    RedeclareBandBreak,
    RescheduleBand,
    ScheduleOperation,
    UnassignEmployee,
    WithdrawDemand,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
)
from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
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
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
    ValidationConfig,
    WorkloadDirection,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

# `sqlalchemy.Row` acessado por atributo (`row.first_day`) não é checável pelo mypy — o
# mesmo escape nomeado do `mappers.py` de staff, visível na assinatura.
Row = Any
JsonObject = dict[str, Any]


# ---------------------------------------------------------------------------
# Agregado → linhas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleRows:
    """As linhas de uma escala, uma tupla por tabela, cada filha com a sua `position`."""

    root: dict[str, Any]
    bands: tuple[dict[str, Any], ...]
    demands: tuple[dict[str, Any], ...]
    assignments: tuple[dict[str, Any], ...]


def schedule_to_rows(schedule: Schedule) -> ScheduleRows:
    """A escala inteira em linhas; toda filha carrega tenant, unidade e escala (o cerco)."""
    address = {"tenant_id": schedule.tenant_id, "unit_id": schedule.unit_id}
    bands: list[dict[str, Any]] = []
    demands: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for band_position, band in enumerate(schedule.bands):
        bands.append(
            {
                **address,
                "id": band.id,
                "schedule_id": schedule.id,
                "position": band_position,
                "start_at": band.time_range.start,
                "end_at": band.time_range.end,
                "break_minutes": band.time_range.break_minutes,
            }
        )
        for demand_position, demand in enumerate(band.demands):
            demands.append(
                {
                    **address,
                    "id": demand.id,
                    "schedule_id": schedule.id,
                    "band_id": band.id,
                    "position": demand_position,
                    "job_function_id": demand.job_function_id,
                    "quantity": demand.quantity.value,
                }
            )
            for assignment_position, assignment in enumerate(demand.assignments):
                assignments.append(
                    {
                        **address,
                        "id": assignment.id,
                        "schedule_id": schedule.id,
                        "demand_id": demand.id,
                        "position": assignment_position,
                        "employee_id": assignment.employee_id,
                        "counts_toward_workload": assignment.counts_toward_workload,
                        "function_exception": assignment.function_exception,
                        "break_minutes": assignment.break_minutes,
                    }
                )
    root = {
        **address,
        "id": schedule.id,
        "first_day": schedule.period.first_day,
        "days": schedule.period.days,
        "week_start": schedule.calendar.week_start.value,
        "day_cutoff": schedule.calendar.day_cutoff.at,
        "version": schedule.version,
    }
    return ScheduleRows(
        root=root, bands=tuple(bands), demands=tuple(demands), assignments=tuple(assignments)
    )


# ---------------------------------------------------------------------------
# Linhas → agregado
# ---------------------------------------------------------------------------


def _by_parent(rows: Iterable[Row], parent_column: str) -> dict[str, list[Row]]:
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        grouped[getattr(row, parent_column)].append(row)
    for children in grouped.values():
        children.sort(key=lambda child: child.position)
    return grouped


def _row_to_assignment(row: Row) -> Assignment:
    return Assignment(
        id=AssignmentId(row.id),
        employee_id=EmployeeId(row.employee_id),
        counts_toward_workload=row.counts_toward_workload,
        function_exception=row.function_exception,
        break_minutes=row.break_minutes,
    )


def rows_to_schedule(
    root: Row,
    bands: Iterable[Row],
    demands: Iterable[Row],
    assignments: Iterable[Row],
) -> Schedule:
    """Reidrata a escala pelos construtores, com as filhas na ordem de `position`.

    `bands`, `demands` e `assignments` são as linhas **desta** escala, em qualquer ordem.
    """
    assignments_by_demand = _by_parent(assignments, "demand_id")
    demands_by_band = _by_parent(demands, "band_id")
    rehydrated_bands = tuple(
        ShiftBand(
            id=ShiftBandId(band.id),
            time_range=TimeRange(
                start=band.start_at, end=band.end_at, break_minutes=band.break_minutes
            ),
            demands=tuple(
                ShiftDemand(
                    id=ShiftDemandId(demand.id),
                    job_function_id=JobFunctionId(demand.job_function_id),
                    quantity=DemandQuantity(demand.quantity),
                    assignments=tuple(
                        _row_to_assignment(assignment)
                        for assignment in assignments_by_demand.get(demand.id, ())
                    ),
                )
                for demand in demands_by_band.get(band.id, ())
            ),
        )
        for band in sorted(bands, key=lambda band: band.position)
    )
    return Schedule(
        id=ScheduleId(root.id),
        tenant_id=TenantId(root.tenant_id),
        unit_id=UnitId(root.unit_id),
        period=SchedulePeriod(first_day=root.first_day, days=root.days),
        calendar=OperationalCalendar(
            week_start=Weekday.from_string(root.week_start),
            day_cutoff=DayCutoff(at=root.day_cutoff),
        ),
        bands=rehydrated_bands,
        version=root.version,
    )


# ---------------------------------------------------------------------------
# Configuração do tenant
# ---------------------------------------------------------------------------


def row_to_settings(row: Row) -> SchedulingSettings:
    """Reidrata a configuração; nenhum default é aplicado (L-CF1).

    As colunas de política e de limite são lidas pelas tuplas de `tables.py`, para que
    tabela e mapper não tenham duas listas. O corte com segundos, que a `CHECK` não
    expressa, é barrado aqui pelo construtor de `DayCutoff`.
    """
    validation: dict[str, Any] = {
        policy: PolicyRule(
            enabled=getattr(row, f"{policy}_enabled"),
            mode=EnforcementMode(getattr(row, f"{policy}_mode")),
        )
        for policy in POLICY_FIELDS
    }
    validation.update({name: getattr(row, name) for name, _ in LIMIT_CHECKS})
    validation["workload_direction"] = WorkloadDirection(row.workload_direction)
    return SchedulingSettings(
        calendar=OperationalCalendar(
            week_start=Weekday.from_string(row.week_start),
            day_cutoff=DayCutoff(at=row.day_cutoff),
        ),
        validation=ValidationConfig(**validation),
    )


# ---------------------------------------------------------------------------
# A trilha — `ScheduleChange` ↔ linha de `schedule_changes`
# ---------------------------------------------------------------------------

# O valor de `kind` de cada operação: literais do contrato de dados (§5.6).
OPERATION_KINDS: Mapping[type, str] = {
    EnableBand: "enable_band",
    RescheduleBand: "reschedule_band",
    RedeclareBandBreak: "redeclare_band_break",
    DisableBand: "disable_band",
    DeclareDemand: "declare_demand",
    ChangeDemandQuantity: "change_demand_quantity",
    WithdrawDemand: "withdraw_demand",
    AssignEmployee: "assign_employee",
    UnassignEmployee: "unassign_employee",
    DeclareWorkloadCounting: "declare_workload_counting",
    DeclareAllocationBreak: "declare_allocation_break",
}


def _instant(value: datetime) -> str:
    return value.isoformat()


def _encode_operation(  # noqa: PLR0911 — um ramo por tipo da união fechada
    operation: ScheduleOperation, function_exception: bool | None
) -> JsonObject:
    kind = {"kind": OPERATION_KINDS[type(operation)]}
    match operation:
        case EnableBand():
            return {
                **kind,
                "band_id": operation.band_id,
                "start": _instant(operation.time_range.start),
                "end": _instant(operation.time_range.end),
                "break_minutes": operation.time_range.break_minutes,
            }
        case RescheduleBand():
            return {
                **kind,
                "band_id": operation.band_id,
                "start": _instant(operation.start),
                "end": _instant(operation.end),
            }
        case RedeclareBandBreak():
            return {**kind, "band_id": operation.band_id, "break_minutes": operation.break_minutes}
        case DisableBand():
            return {**kind, "band_id": operation.band_id}
        case DeclareDemand():
            return {
                **kind,
                "demand_id": operation.demand_id,
                "band_id": operation.band_id,
                "job_function_id": operation.job_function_id,
                "quantity": operation.quantity.value,
            }
        case ChangeDemandQuantity():
            return {**kind, "demand_id": operation.demand_id, "quantity": operation.quantity.value}
        case WithdrawDemand():
            return {**kind, "demand_id": operation.demand_id}
        case AssignEmployee():
            return {
                **kind,
                "assignment_id": operation.assignment_id,
                "demand_id": operation.demand_id,
                "employee_id": operation.employee_id,
                "counts_toward_workload": operation.counts_toward_workload,
                "function_exception": function_exception,
            }
        case UnassignEmployee():
            return {**kind, "assignment_id": operation.assignment_id}
        case DeclareWorkloadCounting():
            return {**kind, "assignment_id": operation.assignment_id, "counts": operation.counts}
        case DeclareAllocationBreak():
            return {
                **kind,
                "assignment_id": operation.assignment_id,
                "break_minutes": operation.break_minutes,
            }


def _function_exception_marks(
    schedule: Schedule, operations: tuple[ScheduleOperation, ...]
) -> dict[int, bool]:
    """Índice da operação `assign_employee` → a marca gravada (§5.6).

    Recebe a marca só o **último** `assign_employee` de cada `assignment_id` no lote, e só
    se nenhum `unassign_employee` do mesmo id vier depois dele; a marca é a da alocação na
    escala gravada. Os demais ficam `null`: a alocação deles não está no estado gravado.
    """
    last_assign: dict[str, int] = {}
    for index, operation in enumerate(operations):
        if isinstance(operation, AssignEmployee):
            last_assign[operation.assignment_id] = index
        elif isinstance(operation, UnassignEmployee):
            last_assign.pop(operation.assignment_id, None)
    marks: dict[int, bool] = {}
    for assignment_id, index in last_assign.items():
        stored = _find_assignment(schedule, assignment_id)
        if stored is not None:
            marks[index] = stored.function_exception
    return marks


def _find_assignment(schedule: Schedule, assignment_id: str) -> Assignment | None:
    for band in schedule.bands:
        for demand in band.demands:
            for assignment in demand.assignments:
                if assignment.id == assignment_id:
                    return assignment
    return None


def _encode_violation(violation: Violation) -> JsonObject:
    return {
        "policy": violation.policy.value,
        "mode": violation.mode.value,
        "employee_id": violation.employee_id,
        "demand_id": violation.demand_id,
        "operational_days": [day.isoformat() for day in violation.operational_days],
        "assignment_ids": sorted(violation.assignment_ids),
        "observed": str(violation.observed),
        "limit": str(violation.limit),
    }


def change_to_row(schedule: Schedule, change: ScheduleChange, seq: int) -> dict[str, Any]:
    """A linha da trilha da escrita: `resulting_version` é a da escala gravada junto."""
    marks = _function_exception_marks(schedule, change.operations)
    return {
        "schedule_id": schedule.id,
        "seq": seq,
        "author_user_id": change.author_user_id,
        "occurred_at": change.occurred_at,
        "previous_version": change.previous_version,
        "resulting_version": schedule.version,
        "operations": [
            _encode_operation(operation, marks.get(index))
            for index, operation in enumerate(change.operations)
        ],
        "acknowledged": [_encode_violation(violation) for violation in change.acknowledged],
    }


def _decode_operation(data: Mapping[str, Any]) -> ScheduleOperation:  # noqa: PLR0911
    kind = data["kind"]
    match kind:
        case "enable_band":
            return EnableBand(
                band_id=ShiftBandId(data["band_id"]),
                time_range=TimeRange(
                    start=datetime.fromisoformat(data["start"]),
                    end=datetime.fromisoformat(data["end"]),
                    break_minutes=data["break_minutes"],
                ),
            )
        case "reschedule_band":
            return RescheduleBand(
                band_id=ShiftBandId(data["band_id"]),
                start=datetime.fromisoformat(data["start"]),
                end=datetime.fromisoformat(data["end"]),
            )
        case "redeclare_band_break":
            return RedeclareBandBreak(
                band_id=ShiftBandId(data["band_id"]), break_minutes=data["break_minutes"]
            )
        case "disable_band":
            return DisableBand(band_id=ShiftBandId(data["band_id"]))
        case "declare_demand":
            return DeclareDemand(
                demand_id=ShiftDemandId(data["demand_id"]),
                band_id=ShiftBandId(data["band_id"]),
                job_function_id=JobFunctionId(data["job_function_id"]),
                quantity=DemandQuantity(data["quantity"]),
            )
        case "change_demand_quantity":
            return ChangeDemandQuantity(
                demand_id=ShiftDemandId(data["demand_id"]),
                quantity=DemandQuantity(data["quantity"]),
            )
        case "withdraw_demand":
            return WithdrawDemand(demand_id=ShiftDemandId(data["demand_id"]))
        case "assign_employee":
            # `function_exception` é marca do estado gravado, não campo da operação.
            return AssignEmployee(
                assignment_id=AssignmentId(data["assignment_id"]),
                demand_id=ShiftDemandId(data["demand_id"]),
                employee_id=EmployeeId(data["employee_id"]),
                counts_toward_workload=data["counts_toward_workload"],
            )
        case "unassign_employee":
            return UnassignEmployee(assignment_id=AssignmentId(data["assignment_id"]))
        case "declare_workload_counting":
            return DeclareWorkloadCounting(
                assignment_id=AssignmentId(data["assignment_id"]), counts=data["counts"]
            )
        case "declare_allocation_break":
            return DeclareAllocationBreak(
                assignment_id=AssignmentId(data["assignment_id"]),
                break_minutes=data["break_minutes"],
            )
    raise ValueError(f"tipo de operação desconhecido na trilha: {kind!r}")


def _decode_violation(data: Mapping[str, Any]) -> Violation:
    employee_id, demand_id = data["employee_id"], data["demand_id"]
    return Violation(
        policy=PolicyKind(data["policy"]),
        mode=EnforcementMode(data["mode"]),
        employee_id=None if employee_id is None else EmployeeId(employee_id),
        demand_id=None if demand_id is None else ShiftDemandId(demand_id),
        operational_days=tuple(date.fromisoformat(day) for day in data["operational_days"]),
        assignment_ids=frozenset(AssignmentId(item) for item in data["assignment_ids"]),
        observed=Decimal(data["observed"]),
        limit=Decimal(data["limit"]),
    )


def row_to_change(row: Row) -> ScheduleChange:
    """Lê a linha da trilha; o instante volta aware, normalizado para UTC."""
    return ScheduleChange(
        author_user_id=row.author_user_id,
        occurred_at=row.occurred_at.astimezone(UTC),
        previous_version=row.previous_version,
        operations=tuple(_decode_operation(item) for item in row.operations),
        acknowledged=tuple(_decode_violation(item) for item in row.acknowledged),
    )

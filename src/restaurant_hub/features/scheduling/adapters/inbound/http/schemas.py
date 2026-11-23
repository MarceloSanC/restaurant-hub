"""Schemas Pydantic de request e response, e os conversores da borda — BC scheduling.

**Pydantic vive só aqui** (LAYOUT §7; skill `fastapi-thin-adapter`). Os use cases recebem e
devolvem dataclasses de `application`; nenhum schema atravessa para dentro. **Nenhuma
entidade de domínio aparece numa resposta**: as respostas são montadas a partir dos results.

Decisões deste módulo (concept 4.5 §4.2; ADR 4.5.0003 §Decision 5):

1. **Nenhum request tem `tenant_id`, `restaurant_id` nem `user_id`.** O tenant vem do token; o
   "eu" de "minha escala" é o sujeito do token (ADR 0.0.0005; ADR 4.3.0002 §4).
2. **O lote é uma lista de operações discriminada por `op`**, uma variante por operação da 4.3,
   cada uma com `extra="forbid"` — o campo a mais numa operação é o estado inválido que a união
   existe para recusar (precedente: a errata do ADR 3.6.0003). Os requests de topo seguem
   permissivos, como os de staff. Inteiros e booleanos são **estritos**: `true` não vira `1`
   numa quantidade, nem `1.0` vira `1`.
3. **No máximo 500 operações e 500 aceites por requisição** (D-BATCH): acima disso, 422 do
   framework, antes de qualquer leitura.
4. **Instantes de parede sem offset, nos dois sentidos** (ADR 3.6.0003 §Decision 3; D-TIME):
   valor com `Z` ou offset é parseado como tz-aware e recusado pelo `TimeRange` (422), nunca
   convertido. Na saída, o `datetime` ingênuo serializa sem offset.
5. **A medida de uma violação viaja como texto decimal**, nos dois sentidos (precedente
   `weekly_hours`, ADR 3.6.0003 §Decision 2). O aceite devolve a `key` **como a recebeu**: a
   borda não reordena nem deduplica os dias (concept 4.5 §4.2).

**Conversão em dois tempos.** `check_operation_identifiers`/`check_acknowledgement_identifiers`
validam só identificadores e rodam **antes** de autorizar (ADR 3.6.0002); `to_operation` e
`to_acknowledgement` constroem os DTOs (instantes, quantidade, decimais, `TimeRange`) e rodam
**depois**, como a conversão texto → value object de staff. Erro aqui é erro de scheduling, com
o corpo do BC — nunca um `RequestValidationError`, que teria outro corpo.
"""

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from restaurant_hub.features.scheduling.adapters.inbound.http.dependencies import (
    validate_creation_id,
    validate_identifier,
    validate_instant,
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
    ViolationAcknowledgement,
    WithdrawDemand,
)
from restaurant_hub.features.scheduling.application.dtos.results import (
    AssignmentResult,
    BandResult,
    CalendarResult,
    DemandResult,
    EvaluationResult,
    MyScheduleResult,
    MyShiftResult,
    ScheduleResult,
    ScheduleSummaryResult,
)
from restaurant_hub.features.scheduling.application.errors import InvalidScheduleRequestError
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import PolicyKind
from restaurant_hub.features.scheduling.domain.value_objects.violation import (
    Violation,
    ViolationKey,
)

MAX_BATCH: Final = 500
# O teto da coluna `quantity` (`INTEGER` do Postgres, -2147483648 a +2147483647 — D-QTY).
MAX_QUANTITY: Final = 2_147_483_647

_BAND, _DEMAND, _ASSIGNMENT = "faixa", "demanda", "alocação"
_EMPLOYEE, _FUNCTION = "funcionário", "função de trabalho"

_OPERATION_CONFIG: Final = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateScheduleRequest(BaseModel):
    """S1 — criação da escala do período que começa em `first_day` (id do servidor)."""

    first_day: date


class EnableBandOperation(BaseModel):
    """Habilita a faixa `band_id` (UUID criado pelo cliente)."""

    model_config = _OPERATION_CONFIG
    op: Literal["enable_band"]
    band_id: str
    start: datetime
    end: datetime
    break_minutes: StrictInt = 0


class RescheduleBandOperation(BaseModel):
    """Move os limites da faixa."""

    model_config = _OPERATION_CONFIG
    op: Literal["reschedule_band"]
    band_id: str
    start: datetime
    end: datetime


class RedeclareBandBreakOperation(BaseModel):
    """Redeclara o intervalo da faixa."""

    model_config = _OPERATION_CONFIG
    op: Literal["redeclare_band_break"]
    band_id: str
    break_minutes: StrictInt


class DisableBandOperation(BaseModel):
    """Desabilita a faixa."""

    model_config = _OPERATION_CONFIG
    op: Literal["disable_band"]
    band_id: str


class DeclareDemandOperation(BaseModel):
    """Declara a demanda `demand_id` (UUID criado pelo cliente) de uma função na faixa."""

    model_config = _OPERATION_CONFIG
    op: Literal["declare_demand"]
    demand_id: str
    band_id: str
    job_function_id: str
    quantity: StrictInt


class ChangeDemandQuantityOperation(BaseModel):
    """Troca a quantidade-alvo da demanda."""

    model_config = _OPERATION_CONFIG
    op: Literal["change_demand_quantity"]
    demand_id: str
    quantity: StrictInt


class WithdrawDemandOperation(BaseModel):
    """Retira a demanda."""

    model_config = _OPERATION_CONFIG
    op: Literal["withdraw_demand"]
    demand_id: str


class AssignEmployeeOperation(BaseModel):
    """Aloca o registro à demanda com a alocação `assignment_id` (UUID criado pelo cliente)."""

    model_config = _OPERATION_CONFIG
    op: Literal["assign_employee"]
    assignment_id: str
    demand_id: str
    employee_id: str
    counts_toward_workload: StrictBool = True


class UnassignEmployeeOperation(BaseModel):
    """Desaloca."""

    model_config = _OPERATION_CONFIG
    op: Literal["unassign_employee"]
    assignment_id: str


class DeclareWorkloadCountingOperation(BaseModel):
    """Re-declara se as horas da alocação contam para a carga."""

    model_config = _OPERATION_CONFIG
    op: Literal["declare_workload_counting"]
    assignment_id: str
    counts: StrictBool


class DeclareAllocationBreakOperation(BaseModel):
    """Declara o intervalo próprio da alocação; `null` volta a herdar o da faixa."""

    model_config = _OPERATION_CONFIG
    op: Literal["declare_allocation_break"]
    assignment_id: str
    break_minutes: StrictInt | None


OperationPayload = Annotated[
    EnableBandOperation
    | RescheduleBandOperation
    | RedeclareBandBreakOperation
    | DisableBandOperation
    | DeclareDemandOperation
    | ChangeDemandQuantityOperation
    | WithdrawDemandOperation
    | AssignEmployeeOperation
    | UnassignEmployeeOperation
    | DeclareWorkloadCountingOperation
    | DeclareAllocationBreakOperation,
    Field(discriminator="op"),
]


class ViolationKeyPayload(BaseModel):
    """A identidade de aceite de uma violação, ecoada como a resposta a trouxe."""

    model_config = _OPERATION_CONFIG
    policy: str
    employee_id: str | None
    demand_id: str | None
    operational_days: list[date]
    assignment_ids: list[str]


class AcknowledgementPayload(BaseModel):
    """Aceite consciente de uma violação `warn`: a `key` e a medida que a gerente viu."""

    model_config = _OPERATION_CONFIG
    key: ViolationKeyPayload
    observed: str
    limit: str


class EvaluateScheduleRequest(BaseModel):
    """S3 — o lote a avaliar sobre a versão que o editor viu."""

    expected_version: StrictInt
    operations: list[OperationPayload] = Field(max_length=MAX_BATCH)


class PublishScheduleRequest(BaseModel):
    """S4 — o lote a publicar, com os aceites dos avisos que ele introduz."""

    expected_version: StrictInt
    operations: list[OperationPayload] = Field(max_length=MAX_BATCH)
    acknowledgements: list[AcknowledgementPayload] = Field(
        default_factory=list, max_length=MAX_BATCH
    )


# ---------------------------------------------------------------------------
# Conversores de entrada
# ---------------------------------------------------------------------------


def check_operation_identifiers(operations: Iterable[OperationPayload]) -> None:
    """Valida os identificadores do lote — **antes** de autorizar (ADR 3.6.0002; D-IDS).

    Ids de criação (`band_id` de `enable_band`, `demand_id` de `declare_demand`,
    `assignment_id` de `assign_employee`) exigem UUID canônico; os de referência, só não ser
    vazio, só-espaço nem conter NUL.
    """
    for op in operations:
        match op:
            case EnableBandOperation():
                validate_creation_id(op.band_id, entity=_BAND)
            case DeclareDemandOperation():
                validate_creation_id(op.demand_id, entity=_DEMAND)
                validate_identifier(op.band_id, entity=_BAND)
                validate_identifier(op.job_function_id, entity=_FUNCTION)
            case AssignEmployeeOperation():
                validate_creation_id(op.assignment_id, entity=_ASSIGNMENT)
                validate_identifier(op.demand_id, entity=_DEMAND)
                validate_identifier(op.employee_id, entity=_EMPLOYEE)
            case RescheduleBandOperation() | RedeclareBandBreakOperation() | DisableBandOperation():
                validate_identifier(op.band_id, entity=_BAND)
            case ChangeDemandQuantityOperation() | WithdrawDemandOperation():
                validate_identifier(op.demand_id, entity=_DEMAND)
            case (
                UnassignEmployeeOperation()
                | DeclareWorkloadCountingOperation()
                | DeclareAllocationBreakOperation()
            ):
                validate_identifier(op.assignment_id, entity=_ASSIGNMENT)


def check_acknowledgement_identifiers(acknowledgements: Iterable[AcknowledgementPayload]) -> None:
    """Valida os identificadores das `key` dos aceites — antes de autorizar."""
    for ack in acknowledgements:
        if ack.key.employee_id is not None:
            validate_identifier(ack.key.employee_id, entity=_EMPLOYEE)
        if ack.key.demand_id is not None:
            validate_identifier(ack.key.demand_id, entity=_DEMAND)
        for assignment_id in ack.key.assignment_ids:
            validate_identifier(assignment_id, entity=_ASSIGNMENT)


def _quantity(value: int) -> DemandQuantity:
    if value > MAX_QUANTITY:
        raise InvalidScheduleRequestError(f"quantidade acima do máximo ({MAX_QUANTITY})")
    return DemandQuantity(value)


def to_operation(op: OperationPayload) -> ScheduleOperation:  # noqa: PLR0911 — um ramo por operação
    """O DTO de application da operação (instantes, quantidade e `TimeRange` aqui).

    Raises:
        InvalidScheduleRequestError: instante extremo ou quantidade acima do `INTEGER`.
        InvalidTimeRangeError, InvalidDemandQuantityError: do domínio, sem tradução.
    """
    match op:
        case EnableBandOperation():
            return EnableBand(
                band_id=ShiftBandId(op.band_id),
                time_range=TimeRange(
                    start=validate_instant(op.start, name="start"),
                    end=validate_instant(op.end, name="end"),
                    break_minutes=op.break_minutes,
                ),
            )
        case RescheduleBandOperation():
            return RescheduleBand(
                band_id=ShiftBandId(op.band_id),
                start=validate_instant(op.start, name="start"),
                end=validate_instant(op.end, name="end"),
            )
        case RedeclareBandBreakOperation():
            return RedeclareBandBreak(ShiftBandId(op.band_id), op.break_minutes)
        case DisableBandOperation():
            return DisableBand(ShiftBandId(op.band_id))
        case DeclareDemandOperation():
            return DeclareDemand(
                demand_id=ShiftDemandId(op.demand_id),
                band_id=ShiftBandId(op.band_id),
                job_function_id=JobFunctionId(op.job_function_id),
                quantity=_quantity(op.quantity),
            )
        case ChangeDemandQuantityOperation():
            return ChangeDemandQuantity(ShiftDemandId(op.demand_id), _quantity(op.quantity))
        case WithdrawDemandOperation():
            return WithdrawDemand(ShiftDemandId(op.demand_id))
        case AssignEmployeeOperation():
            return AssignEmployee(
                assignment_id=AssignmentId(op.assignment_id),
                demand_id=ShiftDemandId(op.demand_id),
                employee_id=EmployeeId(op.employee_id),
                counts_toward_workload=op.counts_toward_workload,
            )
        case UnassignEmployeeOperation():
            return UnassignEmployee(AssignmentId(op.assignment_id))
        case DeclareWorkloadCountingOperation():
            return DeclareWorkloadCounting(AssignmentId(op.assignment_id), op.counts)
        case DeclareAllocationBreakOperation():
            return DeclareAllocationBreak(AssignmentId(op.assignment_id), op.break_minutes)


def to_decimal(raw: str, *, name: str) -> Decimal:
    """Texto decimal finito — a medida de uma violação (decisão 5 do módulo).

    Raises:
        InvalidScheduleRequestError: não numérico, ou `NaN`/`Infinity` (422, nunca 500).
    """
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidScheduleRequestError(f"{name} não é número decimal") from exc
    if not value.is_finite():
        raise InvalidScheduleRequestError(f"{name} não é número finito")
    return value


def to_acknowledgement(ack: AcknowledgementPayload) -> ViolationAcknowledgement:
    """O aceite, com a `key` como o cliente a ecoou.

    Raises:
        InvalidScheduleRequestError: política desconhecida ou medida que não é decimal finito.
    """
    try:
        policy = PolicyKind(ack.key.policy)
    except ValueError as exc:
        raise InvalidScheduleRequestError(f"política desconhecida: {ack.key.policy!r}") from exc
    return ViolationAcknowledgement(
        key=ViolationKey(
            policy=policy,
            employee_id=(
                EmployeeId(ack.key.employee_id) if ack.key.employee_id is not None else None
            ),
            demand_id=(ShiftDemandId(ack.key.demand_id) if ack.key.demand_id is not None else None),
            operational_days=tuple(ack.key.operational_days),
            assignment_ids=frozenset(AssignmentId(a) for a in ack.key.assignment_ids),
        ),
        observed=to_decimal(ack.observed, name="observed"),
        limit=to_decimal(ack.limit, name="limit"),
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


def _decimal_text(value: Decimal) -> str:
    """Decimal sem notação científica (`Decimal("6.6E+2")` sai `"660"`)."""
    return format(value, "f")


class ScheduleSummaryResponse(BaseModel):
    """Resumo de uma escala."""

    schedule_id: str
    unit_id: str
    first_day: date
    last_day: date
    version: int

    @classmethod
    def from_result(cls, result: ScheduleSummaryResult) -> "ScheduleSummaryResponse":
        return cls(
            schedule_id=result.schedule_id,
            unit_id=result.unit_id,
            first_day=result.first_day,
            last_day=result.last_day,
            version=result.version,
        )


class AssignmentResponse(BaseModel):
    """Uma alocação de registro ativo."""

    assignment_id: str
    employee_id: str
    display_name: str
    counts_toward_workload: bool
    function_exception: bool
    break_minutes: int | None
    worked_minutes: int

    @classmethod
    def from_result(cls, result: AssignmentResult) -> "AssignmentResponse":
        return cls(
            assignment_id=result.assignment_id,
            employee_id=result.employee_id,
            display_name=result.display_name,
            counts_toward_workload=result.counts_toward_workload,
            function_exception=result.function_exception,
            break_minutes=result.break_minutes,
            worked_minutes=result.worked_minutes,
        )


class DemandResponse(BaseModel):
    """Uma demanda; `function_enabled_in_unit` falso é a demanda órfã (ADR 4.3.0005)."""

    demand_id: str
    job_function_id: str
    job_function_name: str | None
    function_enabled_in_unit: bool
    quantity: int
    assignments: list[AssignmentResponse]

    @classmethod
    def from_result(cls, result: DemandResult) -> "DemandResponse":
        return cls(
            demand_id=result.demand_id,
            job_function_id=result.job_function_id,
            job_function_name=result.job_function_name,
            function_enabled_in_unit=result.function_enabled_in_unit,
            quantity=result.quantity,
            assignments=[AssignmentResponse.from_result(a) for a in result.assignments],
        )


class BandResponse(BaseModel):
    """Uma faixa, em wall-clock da unidade, sem offset."""

    band_id: str
    schedule_id: str
    operational_day: date
    start: datetime
    end: datetime
    break_minutes: int
    demands: list[DemandResponse]

    @classmethod
    def from_result(cls, result: BandResult) -> "BandResponse":
        return cls(
            band_id=result.band_id,
            schedule_id=result.schedule_id,
            operational_day=result.operational_day,
            start=result.time_range.start,
            end=result.time_range.end,
            break_minutes=result.time_range.break_minutes,
            demands=[DemandResponse.from_result(d) for d in result.demands],
        )


class ViolationKeyResponse(BaseModel):
    """A identidade de aceite (ADR 4.2.0002) — o que o aceite devolve."""

    policy: str
    employee_id: str | None
    demand_id: str | None
    operational_days: list[date]
    assignment_ids: list[str]


class ViolationResponse(BaseModel):
    """Uma violação: política, modo, sujeito, dias, alocações e a medida; sem texto (D-TEXT)."""

    policy: str
    mode: str
    employee_id: str | None
    demand_id: str | None
    operational_days: list[date]
    assignment_ids: list[str]
    observed: str
    limit: str
    key: ViolationKeyResponse

    @classmethod
    def from_violation(cls, violation: Violation) -> "ViolationResponse":
        key = violation.key
        return cls(
            policy=violation.policy.value,
            mode=violation.mode.value,
            employee_id=violation.employee_id,
            demand_id=violation.demand_id,
            operational_days=list(violation.operational_days),
            assignment_ids=sorted(violation.assignment_ids),
            observed=_decimal_text(violation.observed),
            limit=_decimal_text(violation.limit),
            key=ViolationKeyResponse(
                policy=key.policy.value,
                employee_id=key.employee_id,
                demand_id=key.demand_id,
                operational_days=list(key.operational_days),
                assignment_ids=sorted(key.assignment_ids),
            ),
        )


class ScheduleResponse(BaseModel):
    """A escala com faixas e as violações atuais."""

    summary: ScheduleSummaryResponse
    bands: list[BandResponse]
    violations: list[ViolationResponse]

    @classmethod
    def from_result(cls, result: ScheduleResult) -> "ScheduleResponse":
        return cls(
            summary=ScheduleSummaryResponse.from_result(result.summary),
            bands=[BandResponse.from_result(b) for b in result.bands],
            violations=[ViolationResponse.from_violation(v) for v in result.violations],
        )


class EvaluationResponse(BaseModel):
    """A escala resultante do lote e as violações que ele **introduz**, por modo."""

    schedule: ScheduleResponse
    blocking: list[ViolationResponse]
    warnings: list[ViolationResponse]

    @classmethod
    def from_result(cls, result: EvaluationResult) -> "EvaluationResponse":
        return cls(
            schedule=ScheduleResponse.from_result(result.schedule),
            blocking=[ViolationResponse.from_violation(v) for v in result.blocking],
            warnings=[ViolationResponse.from_violation(v) for v in result.warnings],
        )


class CalendarResponse(BaseModel):
    """As escalas que cruzam o recorte e as faixas cujo dia operacional cai nele."""

    first_day: date
    last_day: date
    schedules: list[ScheduleSummaryResponse]
    bands: list[BandResponse]

    @classmethod
    def from_result(cls, result: CalendarResult) -> "CalendarResponse":
        return cls(
            first_day=result.first_day,
            last_day=result.last_day,
            schedules=[ScheduleSummaryResponse.from_result(s) for s in result.schedules],
            bands=[BandResponse.from_result(b) for b in result.bands],
        )


class MyShiftResponse(BaseModel):
    """Um turno do próprio ator."""

    schedule_id: str
    band_id: str
    assignment_id: str
    employee_id: str
    operational_day: date
    start: datetime
    end: datetime
    job_function_id: str
    job_function_name: str | None
    worked_minutes: int

    @classmethod
    def from_result(cls, result: MyShiftResult) -> "MyShiftResponse":
        return cls(
            schedule_id=result.schedule_id,
            band_id=result.band_id,
            assignment_id=result.assignment_id,
            employee_id=result.employee_id,
            operational_day=result.operational_day,
            start=result.start,
            end=result.end,
            job_function_id=result.job_function_id,
            job_function_name=result.job_function_name,
            worked_minutes=result.worked_minutes,
        )


class MyScheduleResponse(BaseModel):
    """Os turnos do próprio ator no recorte."""

    first_day: date
    last_day: date
    shifts: list[MyShiftResponse]

    @classmethod
    def from_result(cls, result: MyScheduleResult) -> "MyScheduleResponse":
        return cls(
            first_day=result.first_day,
            last_day=result.last_day,
            shifts=[MyShiftResponse.from_result(s) for s in result.shifts],
        )

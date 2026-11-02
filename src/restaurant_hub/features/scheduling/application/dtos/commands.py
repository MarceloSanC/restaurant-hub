"""Commands e operações — a entrada dos use cases de escrita do BC scheduling.

**Operações** (ADR 4.3.0001 §1): uma por mutação do agregado `Schedule` (as 11). Um lote
é uma tupla ordenada delas, que `evaluate_schedule` avalia e `publish_schedule` grava.
Os ids de **criação** (`EnableBand.band_id`, `DeclareDemand.demand_id`,
`AssignEmployee.assignment_id`) vêm do cliente (ADR 4.3.0004). `AssignEmployee` não
carrega `function_exception`: a marca é derivada pelo use case (concept §5.8).

**Commands** carregam `actor` como primeiro campo, `repr=False` (ADR 3.7.0001 §2; ADR
4.3.0002) e o endereço `(tenant_id, unit_id[, schedule_id])`, sem defaults.

Value objects imutáveis do domínio (`TimeRange`, `DemandQuantity`, `ViolationKey`)
trafegam por licença do LAYOUT §7; nenhuma entidade aparece aqui.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from restaurant_hub.features.scheduling.application.ports.out.access_guard import Actor
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
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.violation import ViolationKey

# --- operações (uma por mutação do agregado) ------------------------------------------


@dataclass(frozen=True)
class EnableBand:
    """Habilita a faixa `band_id` (id do cliente) com o intervalo dado."""

    band_id: ShiftBandId
    time_range: TimeRange


@dataclass(frozen=True)
class RescheduleBand:
    """Move os limites da faixa — instantes validados ingênuos e de minuto inteiro."""

    band_id: ShiftBandId
    start: datetime
    end: datetime


@dataclass(frozen=True)
class RedeclareBandBreak:
    """Redeclara o intervalo da faixa."""

    band_id: ShiftBandId
    break_minutes: int


@dataclass(frozen=True)
class DisableBand:
    """Desabilita a faixa."""

    band_id: ShiftBandId


@dataclass(frozen=True)
class DeclareDemand:
    """Declara a demanda `demand_id` (id do cliente) de uma função na faixa."""

    demand_id: ShiftDemandId
    band_id: ShiftBandId
    job_function_id: JobFunctionId
    quantity: DemandQuantity


@dataclass(frozen=True)
class ChangeDemandQuantity:
    """Troca a quantidade-alvo da demanda."""

    demand_id: ShiftDemandId
    quantity: DemandQuantity


@dataclass(frozen=True)
class WithdrawDemand:
    """Retira a demanda."""

    demand_id: ShiftDemandId


@dataclass(frozen=True)
class AssignEmployee:
    """Aloca o registro à demanda com a alocação `assignment_id` (id do cliente)."""

    assignment_id: AssignmentId
    demand_id: ShiftDemandId
    employee_id: EmployeeId
    counts_toward_workload: bool = True


@dataclass(frozen=True)
class UnassignEmployee:
    """Desaloca."""

    assignment_id: AssignmentId


@dataclass(frozen=True)
class DeclareWorkloadCounting:
    """Re-declara se as horas da alocação contam para a carga."""

    assignment_id: AssignmentId
    counts: bool


@dataclass(frozen=True)
class DeclareAllocationBreak:
    """Declara o intervalo próprio da alocação; `None` volta a herdar o da faixa."""

    assignment_id: AssignmentId
    break_minutes: int | None


ScheduleOperation = (
    EnableBand
    | RescheduleBand
    | RedeclareBandBreak
    | DisableBand
    | DeclareDemand
    | ChangeDemandQuantity
    | WithdrawDemand
    | AssignEmployee
    | UnassignEmployee
    | DeclareWorkloadCounting
    | DeclareAllocationBreak
)


@dataclass(frozen=True)
class ViolationAcknowledgement:
    """Aceite consciente de uma violação `warn`, com a medida que a gerente **viu**.

    Cobre a violação introduzida de mesma `key` cujo desvio (`observed - limit`) tem o
    mesmo sinal e magnitude não maior que o deste aceite (concept §5.7).
    """

    key: ViolationKey
    observed: Decimal
    limit: Decimal


# --- commands ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateScheduleCommand:
    """Criação da escala da unidade para o período que começa em `first_day`."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    first_day: date


@dataclass(frozen=True)
class PublishScheduleCommand:
    """Publicação de um lote sobre a versão que o editor viu, com os aceites."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    schedule_id: ScheduleId
    expected_version: int
    operations: tuple[ScheduleOperation, ...]
    acknowledgements: tuple[ViolationAcknowledgement, ...] = ()

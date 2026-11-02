"""Protocolo de publicação — compartilhado por `evaluate_schedule` e `publish_schedule`.

ADR 4.3.0001; concept 4.3 §5.5 a §5.10 e §5.21. Módulo privado (fora da varredura de
use cases); **não escreve** — a escrita é do `execute` do publish.

1. **Ids de criação** (`check_creation_ids`): id criado pelo lote que já existe, do
   mesmo tipo, na escala carregada ou numa vizinha ⇒ `IdentifierInUseError`.
2. **Aplicação** (`apply_operations`): operações em ordem, em memória; por operação, as
   pré-checagens da application (alvo de `AssignEmployee` presente e ativo, função no
   catálogo, instantes de `RescheduleBand` ingênuos e de minuto inteiro, D3) e depois o
   domínio, cujos erros sobem crus. Efetiva = o resultado não `is` a escala de entrada.
3. **Introduzidas** (`introduced`): desvio com sinal (`observed - limit`); a do depois é
   introduzida se a `key` é nova, ou se o desvio trocou de sinal ou cresceu em magnitude.
   Sobre-cobertura casa por demanda.
4. **Aceite** (`split_acknowledged`): um aceite cobre a `warn` de mesma `key` cujo desvio
   tem o mesmo sinal e magnitude não maior que a do aceite, calculada com o **limite que
   a gerente viu**.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    ChangeDemandQuantity,
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
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    InactiveAllocationsInUseError,
    InactiveStaffMemberError,
    JobFunctionNotFoundError,
    ScheduleNotFoundError,
    ScheduleVersionConflictError,
    StaffMemberNotFoundError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffReadPort,
)
from restaurant_hub.features.scheduling.application.use_cases._inputs import (
    StaffView,
    facts_of,
    load_staff,
    neighbours_of,
    settings_of,
)
from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.services.validation.evaluator import evaluate
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    ScheduleId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

# --- 1. ids de criação -----------------------------------------------------------------


def _ids_by_type(schedule: Schedule) -> dict[str, set[str]]:
    demandas = [d for f in schedule.bands for d in f.demands]
    return {
        "ShiftBandId": {f.id for f in schedule.bands},
        "ShiftDemandId": {d.id for d in demandas},
        "AssignmentId": {a.id for d in demandas for a in d.assignments},
    }


def _created_id(operation: ScheduleOperation) -> tuple[str, str] | None:
    if isinstance(operation, EnableBand):
        return ("ShiftBandId", operation.band_id)
    if isinstance(operation, DeclareDemand):
        return ("ShiftDemandId", operation.demand_id)
    if isinstance(operation, AssignEmployee):
        return ("AssignmentId", operation.assignment_id)
    return None


def check_creation_ids(
    schedules: Iterable[Schedule], operations: tuple[ScheduleOperation, ...]
) -> None:
    """Recusa id de criação já usado (mesmo tipo) nas escalas dadas (§5.21)."""
    usados: dict[str, set[str]] = {
        "ShiftBandId": set(),
        "ShiftDemandId": set(),
        "AssignmentId": set(),
    }
    for escala in schedules:
        for tipo, ids in _ids_by_type(escala).items():
            usados[tipo] |= ids
    for operacao in operations:
        criado = _created_id(operacao)
        if criado is not None and criado[1] in usados[criado[0]]:
            raise IdentifierInUseError(*criado)


# --- 2. aplicação ----------------------------------------------------------------------


@dataclass(frozen=True)
class AppliedBatch:
    """O estado final do lote e as operações que mudaram algo, em ordem."""

    schedule: Schedule
    effective: tuple[ScheduleOperation, ...]


def _guard_invisible(assignments: tuple[Assignment, ...], view: StaffView) -> None:
    """D3 — ao menos uma alocação e nenhuma de registro ativo ⇒ recusa com os ids."""
    if not assignments:
        return
    ativos = [
        a for a in assignments if (m := view.members.get(a.employee_id)) is not None and m.active
    ]
    if not ativos:
        raise InactiveAllocationsInUseError(tuple(sorted(a.id for a in assignments)))


def _assign(schedule: Schedule, operation: AssignEmployee, view: StaffView) -> Schedule:
    membro = view.members.get(operation.employee_id)
    if membro is None:
        raise StaffMemberNotFoundError(operation.employee_id)
    if not membro.active:
        raise InactiveStaffMemberError(operation.employee_id)
    _, demanda = schedule.locate_demand(operation.demand_id)
    return schedule.assign(
        operation.assignment_id,
        operation.demand_id,
        operation.employee_id,
        counts_toward_workload=operation.counts_toward_workload,
        # Marca derivada no ato de alocar, independente da config (§5.8, D-FEXC).
        function_exception=demanda.job_function_id not in membro.job_function_ids,
    )


def _apply_one(  # noqa: PLR0911 — um ramo por operação do lote
    schedule: Schedule, operation: ScheduleOperation, view: StaffView
) -> Schedule:
    if isinstance(operation, EnableBand):
        return schedule.enable_band(operation.band_id, operation.time_range)
    if isinstance(operation, RescheduleBand):
        # Instantes de fora do domínio: validados ingênuos e de minuto inteiro ANTES de
        # qualquer `operational_day_of` (§5.15; achado M4 da 4.1).
        TimeRange(start=operation.start, end=operation.end)
        return schedule.reschedule_band(operation.band_id, operation.start, operation.end)
    if isinstance(operation, RedeclareBandBreak):
        return schedule.redeclare_band_break(operation.band_id, operation.break_minutes)
    if isinstance(operation, DisableBand):
        faixa = schedule.band(operation.band_id)
        _guard_invisible(tuple(a for d in faixa.demands for a in d.assignments), view)
        return schedule.disable_band(operation.band_id)
    if isinstance(operation, DeclareDemand):
        if operation.job_function_id not in view.function_names:
            raise JobFunctionNotFoundError(operation.job_function_id)
        return schedule.declare_demand(
            operation.demand_id, operation.band_id, operation.job_function_id, operation.quantity
        )
    if isinstance(operation, ChangeDemandQuantity):
        return schedule.change_demand_quantity(operation.demand_id, operation.quantity)
    if isinstance(operation, WithdrawDemand):
        _, demanda = schedule.locate_demand(operation.demand_id)
        _guard_invisible(demanda.assignments, view)
        return schedule.withdraw_demand(operation.demand_id)
    if isinstance(operation, AssignEmployee):
        return _assign(schedule, operation, view)
    if isinstance(operation, UnassignEmployee):
        return schedule.unassign(operation.assignment_id)
    if isinstance(operation, DeclareWorkloadCounting):
        return schedule.declare_workload_counting(operation.assignment_id, operation.counts)
    return schedule.declare_allocation_break(operation.assignment_id, operation.break_minutes)


def apply_operations(
    schedule: Schedule, operations: tuple[ScheduleOperation, ...], view: StaffView
) -> AppliedBatch:
    """Aplica o lote em ordem; a 1ª recusa sobe e nada mais acontece (§5.5)."""
    atual = schedule
    efetivas: list[ScheduleOperation] = []
    for operacao in operations:
        proxima = _apply_one(atual, operacao, view)
        if proxima is not atual:
            efetivas.append(operacao)
        atual = proxima
    return AppliedBatch(schedule=atual, effective=tuple(efetivas))


# --- 3. introduzidas -------------------------------------------------------------------


def _sign(value: Decimal) -> int:
    return (value > 0) - (value < 0)


def _worse(current: Decimal, reference: Decimal) -> bool:
    """O desvio atual trocou de sinal ou cresceu em magnitude frente à referência."""
    return _sign(current) != _sign(reference) or abs(current) > abs(reference)


def _deviation(violation: Violation) -> Decimal:
    return violation.observed - violation.limit


def introduced(
    before: tuple[Violation, ...], after: tuple[Violation, ...]
) -> tuple[Violation, ...]:
    """As violações do depois que a mudança introduziu (§5.6), na ordem do avaliador."""
    por_chave = {v.key: v for v in before}
    sobre_antes = {v.demand_id: v for v in before if v.policy is PolicyKind.OVER_COVERAGE}
    novas: list[Violation] = []
    for violacao in after:
        if violacao.policy is PolicyKind.OVER_COVERAGE:
            antes = sobre_antes.get(violacao.demand_id)
            nova = (
                antes is None
                or not violacao.assignment_ids <= antes.assignment_ids
                or _deviation(violacao) > _deviation(antes)
            )
        else:
            anterior = por_chave.get(violacao.key)
            nova = anterior is None or _worse(_deviation(violacao), _deviation(anterior))
        if nova:
            novas.append(violacao)
    return tuple(novas)


# --- 4. aceite -------------------------------------------------------------------------


def _covers(ack: ViolationAcknowledgement, violation: Violation) -> bool:
    return ack.key == violation.key and not _worse(_deviation(violation), ack.observed - ack.limit)


def split_acknowledged(
    warnings: tuple[Violation, ...], acknowledgements: tuple[ViolationAcknowledgement, ...]
) -> tuple[tuple[Violation, ...], tuple[Violation, ...]]:
    """`(aceitas, pendentes)` entre as `warn` introduzidas (§5.7)."""
    aceitas = tuple(v for v in warnings if any(_covers(a, v) for a in acknowledgements))
    pendentes = tuple(v for v in warnings if v not in aceitas)
    return aceitas, pendentes


# --- carga para edição -----------------------------------------------------------------


def load_for_edit(
    schedules: ScheduleRepository,
    address: tuple[TenantId, UnitId, ScheduleId],
    expected_version: int,
) -> Schedule:
    """A escala no endereço de três partes, na versão que o editor viu (§5.2, §5.4)."""
    escala = schedules.find_by_id(*address)
    if escala is None:
        raise ScheduleNotFoundError(address[2])
    if escala.version != expected_version:
        raise ScheduleVersionConflictError(expected_version, escala.version)
    return escala


# --- o lote inteiro (leitura dos ports + avaliação antes x depois) -------------------


@dataclass(frozen=True)
class BatchOutcome:
    """O que avaliar e publicar precisam depois de aplicar o lote."""

    after: Schedule
    effective: tuple[ScheduleOperation, ...]
    view: StaffView
    after_violations: tuple[Violation, ...]
    introduced: tuple[Violation, ...]


def run_batch(
    schedules: ScheduleRepository,
    config: ScheduleConfigRepository,
    staff: StaffReadPort,
    loaded: Schedule,
    operations: tuple[ScheduleOperation, ...],
) -> BatchOutcome:
    """Lê o insumo, aplica o lote e avalia antes x depois com o mesmo insumo."""
    settings = settings_of(config, loaded.tenant_id)
    anterior, seguinte = neighbours_of(schedules, loaded)
    vizinhas = tuple(e for e in (anterior, seguinte) if e is not None)
    check_creation_ids((loaded, *vizinhas), operations)
    alvos = frozenset(
        EmployeeId(op.employee_id) for op in operations if isinstance(op, AssignEmployee)
    )
    view = load_staff(
        staff,
        loaded.tenant_id,
        loaded.unit_id,
        (loaded, *vizinhas),
        targets=alvos,
        with_roster=True,
    )
    aplicado = apply_operations(loaded, operations, view)
    fatos = facts_of(view)
    antes = evaluate(
        EvaluationContext(schedule=loaded, facts=fatos, previous=anterior, next=seguinte),
        settings.validation,
    )
    depois = evaluate(
        EvaluationContext(
            schedule=aplicado.schedule, facts=fatos, previous=anterior, next=seguinte
        ),
        settings.validation,
    )
    return BatchOutcome(
        after=aplicado.schedule,
        effective=aplicado.effective,
        view=view,
        after_violations=depois.violations,
        introduced=introduced(antes.violations, depois.violations),
    )

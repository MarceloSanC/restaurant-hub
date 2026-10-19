"""Insumo do avaliador — a escala, as vizinhas adjacentes e os fatos de staff.

`EvaluationContext` é o objeto imutável do **serviço** de validação, não conceito do
modelo (concept 4.2 §4): só o avaliador e as políticas o consomem. Valida o insumo
na construção, **fail-closed** (concept 4.2 §5.4; ADR 4.2.0002 §3), e oferece a
projeção `AllocationView` — cada alocação com a sua faixa, demanda, dia operacional e
minutos — para que nenhuma política percorra o agregado nem conte horas por conta
própria: `worked_minutes` vem de `Schedule.worked_minutes_of`, o sítio único
(ADR 4.1.0002 §3, 4.1.0011).

**Inativo some da projeção** (ADR 4.1.0006): `allocations` e `all_allocations` só
trazem alocações de registros ativos; `active_facts` só os fatos ativos.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidEvaluationInputError,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    EmployeeFacts,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange

_DIAS_DA_SEMANA_DE_APURACAO = 7
_UM_DIA = timedelta(days=1)


@dataclass(frozen=True)
class AllocationView:
    """Uma alocação com o que as políticas leem dela, achatada.

    Attributes:
        assignment_id … band_id: os ids da alocação e de quem a contém.
        time_range: a faixa da alocação (instantes e intervalo da faixa).
        operational_day: dia operacional da faixa (corte da escala de origem).
        worked_minutes: `horas(a)` em minutos, do sítio único.
        effective_break_minutes: intervalo efetivo da alocação.
        band_break_minutes: intervalo declarado da faixa.
        counts_toward_workload: se as horas contam para a carga.
        break_divergence: se o intervalo da alocação difere do da faixa.
        schedule_id: a escala de origem.
        in_evaluated: se a escala de origem é a avaliada (e não uma vizinha).
    """

    assignment_id: AssignmentId
    employee_id: EmployeeId
    demand_id: ShiftDemandId
    job_function_id: JobFunctionId
    band_id: ShiftBandId
    time_range: TimeRange
    operational_day: date
    worked_minutes: int
    effective_break_minutes: int
    band_break_minutes: int
    counts_toward_workload: bool
    break_divergence: bool
    schedule_id: ScheduleId
    in_evaluated: bool


def _projetar(schedule: Schedule, *, in_evaluated: bool) -> tuple[AllocationView, ...]:
    return tuple(
        AllocationView(
            assignment_id=alocacao.id,
            employee_id=alocacao.employee_id,
            demand_id=demanda.id,
            job_function_id=demanda.job_function_id,
            band_id=faixa.id,
            time_range=faixa.time_range,
            operational_day=schedule.operational_day_of(faixa),
            worked_minutes=schedule.worked_minutes_of(alocacao.id),
            effective_break_minutes=schedule.effective_break_minutes_of(alocacao.id),
            band_break_minutes=faixa.time_range.break_minutes,
            counts_toward_workload=alocacao.counts_toward_workload,
            break_divergence=schedule.has_break_divergence(alocacao.id),
            schedule_id=schedule.id,
            in_evaluated=in_evaluated,
        )
        for faixa in schedule.bands
        for demanda in faixa.demands
        for alocacao in demanda.assignments
    )


@dataclass(frozen=True)
class EvaluationContext:
    """O que o avaliador recebe: a escala, as vizinhas adjacentes e os fatos de staff.

    Attributes:
        schedule: a escala avaliada — a única que gera violação.
        facts: os fatos de todo registro alocado (nas três escalas) e do quadro ativo.
        previous: a escala imediatamente anterior da mesma unidade, se houver.
        next: a escala imediatamente seguinte da mesma unidade, se houver.
    """

    schedule: Schedule
    facts: tuple[EmployeeFacts, ...]
    previous: Schedule | None = None
    next: Schedule | None = None
    _por_registro: dict[EmployeeId, EmployeeFacts] = field(init=False, repr=False, compare=False)
    _vistas: tuple[AllocationView, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._validar_periodos()
        self._validar_vizinhas()
        vistas = tuple(
            vista
            for escala in self._escalas()
            for vista in _projetar(escala, in_evaluated=escala is self.schedule)
        )
        ids = [vista.assignment_id for vista in vistas]
        if len(set(ids)) != len(ids):
            raise InvalidEvaluationInputError(
                "AssignmentId repetido entre a escala avaliada e as vizinhas"
            )
        por_registro: dict[EmployeeId, EmployeeFacts] = {}
        for fatos in self.facts:
            if fatos.employee_id in por_registro:
                raise InvalidEvaluationInputError(f"fatos repetidos para {fatos.employee_id!r}")
            por_registro[fatos.employee_id] = fatos
        for vista in vistas:
            if vista.employee_id not in por_registro:
                raise InvalidEvaluationInputError(
                    f"registro alocado {vista.employee_id!r} sem fatos"
                )
        object.__setattr__(self, "_por_registro", por_registro)
        object.__setattr__(self, "_vistas", vistas)

    def _escalas(self) -> tuple[Schedule, ...]:
        return tuple(
            escala for escala in (self.previous, self.schedule, self.next) if escala is not None
        )

    def _validar_periodos(self) -> None:
        for escala in self._escalas():
            if escala.period.days != _DIAS_DA_SEMANA_DE_APURACAO:
                raise InvalidEvaluationInputError(
                    f"o período da escala {escala.id!r} deve ter "
                    f"{_DIAS_DA_SEMANA_DE_APURACAO} dias (recebido: {escala.period.days})"
                )

    def _validar_vizinhas(self) -> None:
        avaliada = self.schedule
        ids = [escala.id for escala in self._escalas()]
        if len(set(ids)) != len(ids):
            raise InvalidEvaluationInputError("escala vizinha com o id da avaliada ou da outra")
        for vizinha in (self.previous, self.next):
            if vizinha is None:
                continue
            if (vizinha.tenant_id, vizinha.unit_id) != (avaliada.tenant_id, avaliada.unit_id):
                raise InvalidEvaluationInputError(
                    f"escala vizinha {vizinha.id!r} de outro tenant ou unidade"
                )
        if (
            self.previous is not None
            and self.previous.period.last_day + _UM_DIA != avaliada.period.first_day
        ):
            raise InvalidEvaluationInputError("a escala anterior não é adjacente à avaliada")
        if (
            self.next is not None
            and avaliada.period.last_day + _UM_DIA != self.next.period.first_day
        ):
            raise InvalidEvaluationInputError("a escala seguinte não é adjacente à avaliada")

    def facts_of(self, employee_id: EmployeeId) -> EmployeeFacts:
        """Os fatos do registro — presentes para todo alocado, por construção."""
        return self._por_registro[employee_id]

    @property
    def active_facts(self) -> tuple[EmployeeFacts, ...]:
        """Os fatos dos registros ativos, na ordem recebida."""
        return tuple(fatos for fatos in self.facts if fatos.active)

    @property
    def allocations(self) -> tuple[AllocationView, ...]:
        """As alocações de registros ativos da escala **avaliada**."""
        return tuple(vista for vista in self.all_allocations if vista.in_evaluated)

    @property
    def all_allocations(self) -> tuple[AllocationView, ...]:
        """As alocações de registros ativos da avaliada **e** das vizinhas."""
        return tuple(
            vista for vista in self._vistas if self._por_registro[vista.employee_id].active
        )

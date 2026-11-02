"""Entidade Schedule — a raiz única do agregado da escala.

A escala de **uma** unidade de **um** tenant para **um** período (ADR 4.1.0009):
único caminho de escrita, dono das faixas (`ShiftBand`), que possuem as demandas
(`ShiftDemand`), que possuem as alocações (`Assignment`). As internas são
alcançadas só por aqui, por contenção.

O `calendar` é **fotografado** na criação (ADR 4.1.0009) e está vivo no
agregado: o alinhamento do período ao `week_start` e a contenção das faixas pelo
**dia operacional** são impostos no `__post_init__`, logo valem também na
reidratação da 4.4 (concept §5.2, §5.9).

Invariantes da raiz (concept §5), par a par sobre a coleção **inteira**:

- ids não-vazios; `version >= 1`;
- `calendar.is_aligned(period)`;
- ids internos únicos no agregado, **por tipo** — inclusive os de demanda e de
  alocação **entre** faixas e demandas distintas, que nenhum nível inferior vê
  (§5.15);
- `(start, end)` distinto entre as faixas — a chave **não** inclui o intervalo
  (§5.10, ADR 4.1.0011);
- toda faixa começa num dia operacional do período (§5.9, ADR 4.1.0008).

As leituras devolvem só tupla ou valor imutável. `worked_minutes_of` **delega**
ao sítio único de horas (`TimeRange.worked_minutes`) com o intervalo efetivo que
a faixa calcula — nenhuma aritmética de horas mora aqui (§5.7).

**Mutações.** Cada uma devolve **nova** instância com `version + 1` (ADR
4.1.0001 §2), reconstruindo a árvore por `dataclasses.replace` e passando de novo
pelo `__post_init__` da raiz e das internas — as recusas estruturais saem das
mesmas checagens da construção, sem cópia aqui. Só as guardas que nenhuma
invariante expressa (remoção com alocação pendente, reagendamento para outro dia)
são checadas no próprio método.

**Cláusula de no-op** (invariante 16): as cinco mutações idempotentes de valor
— `reschedule_band` para o próprio `(start, end)`, `redeclare_band_break` para o
próprio intervalo, `change_demand_quantity` para o próprio N (Stage 4.3, ADR
4.3.0001 §4 — a quinta, que a 4.1 deixara de fora da enumeração), e
`declare_workload_counting` e `declare_allocation_break` para o valor corrente —
devolvem **`self`**, sem incrementar a versão e sem erro de duplicidade. A
comparação vem **antes** de qualquer outra checagem.

Entidade **frozen**, igualdade por **identidade**.
"""

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    AssignmentNotFoundError,
    DuplicateEntityIdError,
    DuplicateShiftBandError,
    InvalidAssignmentBreakError,
    InvalidIdentifierError,
    InvalidSchedulePeriodError,
    InvalidScheduleVersionError,
    ShiftBandDayChangeError,
    ShiftBandInUseError,
    ShiftBandNotFoundError,
    ShiftDemandInUseError,
    ShiftDemandNotFoundError,
    TimeRangeOutsidePeriodError,
)
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
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange


def _has_duplicates(ids: tuple[str, ...]) -> bool:
    """Se algum valor se repete — par a par sobre a coleção inteira."""
    return any(value == other for index, value in enumerate(ids) for other in ids[index + 1 :])


@dataclass(frozen=True, eq=False)
class Schedule:
    """A escala de uma unidade para um período.

    Attributes:
        id: identidade da escala (surrogate).
        tenant_id: restaurante dono da escala.
        unit_id: unidade da escala.
        period: o período de dias operacionais.
        calendar: o calendário operacional fotografado na criação.
        bands: as faixas habilitadas.
        version: contador de versão; `>= 1`, +1 por mutação (ADR 4.1.0001 §2).
    """

    id: ScheduleId
    tenant_id: TenantId
    unit_id: UnitId
    period: SchedulePeriod
    calendar: OperationalCalendar
    bands: tuple[ShiftBand, ...] = ()
    version: int = 1

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("escala")
        if not self.tenant_id.strip():
            raise InvalidIdentifierError("tenant da escala")
        if not self.unit_id.strip():
            raise InvalidIdentifierError("unidade da escala")
        if self.version < 1:
            raise InvalidScheduleVersionError(self.version)
        if not self.calendar.is_aligned(self.period):
            raise InvalidSchedulePeriodError(
                "desalinhado: o primeiro dia não cai no início de semana do calendário"
            )
        self._validate_internal_ids()
        keys = tuple(band.time_range.hours_key for band in self.bands)
        for index, key in enumerate(keys):
            if key in keys[index + 1 :]:
                raise DuplicateShiftBandError()
        for band in self.bands:
            if not self.period.contains(self.operational_day_of(band)):
                raise TimeRangeOutsidePeriodError()

    def _validate_internal_ids(self) -> None:
        demands = tuple(demand for band in self.bands for demand in band.demands)
        assignments = tuple(assignment for demand in demands for assignment in demand.assignments)
        if _has_duplicates(tuple(band.id for band in self.bands)):
            raise DuplicateEntityIdError("ShiftBandId")
        if _has_duplicates(tuple(demand.id for demand in demands)):
            raise DuplicateEntityIdError("ShiftDemandId")
        if _has_duplicates(tuple(assignment.id for assignment in assignments)):
            raise DuplicateEntityIdError("AssignmentId")

    # --- mutações (nova instância, version + 1) -------------------------------------

    def enable_band(self, band_id: ShiftBandId, time_range: TimeRange) -> "Schedule":
        """Habilita uma faixa no período (id gerado fora do domínio).

        Colisão de `(start, end)` e início fora dos dias operacionais saem da
        revalidação da raiz. A faixa que começa no último dia operacional e
        termina depois dele é válida (ADR 4.1.0008 §3).
        """
        return self._replacing_bands((*self.bands, ShiftBand(id=band_id, time_range=time_range)))

    def reschedule_band(self, band_id: ShiftBandId, start: datetime, end: datetime) -> "Schedule":
        """Move os limites da faixa, preservando demandas, alocações e o intervalo.

        Recebe `start`/`end`, nunca um `TimeRange`: não mudar o intervalo é
        estrutural (§5.22). Destino fora do período → `TimeRangeOutsidePeriodError`;
        dentro do período mas em outro dia operacional → `ShiftBandDayChangeError`;
        colisão com **outra** faixa → `DuplicateShiftBandError` (a própria é
        substituída, logo não colide consigo).
        """
        band = self.band(band_id)
        if (start, end) == band.time_range.hours_key:
            return self
        target_day = self.calendar.operational_day_of(start)
        if not self.period.contains(target_day):
            raise TimeRangeOutsidePeriodError()
        if target_day != self.operational_day_of(band):
            raise ShiftBandDayChangeError()
        try:
            rescheduled = band.rescheduled_to(start, end)
        except InvalidAssignmentBreakError as exc:
            # A causa está dois níveis acima do ato (ADR 4.1.0011): a recusa nomeia
            # o encurtamento, e não a construção genérica da faixa.
            raise InvalidAssignmentBreakError(
                "o reagendamento encurta a faixa abaixo do intervalo declarado de uma alocação"
            ) from exc
        return self._replacing_band(rescheduled)

    def redeclare_band_break(self, band_id: ShiftBandId, break_minutes: int) -> "Schedule":
        """Redeclara o intervalo da faixa — verbo próprio (ADR 4.1.0011).

        Muda as horas de **todos** os alocados sem intervalo próprio. Fora de
        `0 <= break < nominal_minutes` → `InvalidTimeRangeError`, do `TimeRange`.
        Não recusa por causa de alocação: o teto do intervalo da alocação é a
        duração nominal, que não muda aqui (§7, `[deviation]` da Task 07).
        """
        band = self.band(band_id)
        if break_minutes == band.time_range.break_minutes:
            return self
        return self._replacing_band(band.with_band_break(break_minutes))

    def disable_band(self, band_id: ShiftBandId) -> "Schedule":
        """Desabilita a faixa — recusa enquanto houver alocação (§5.21).

        Sem alocação, as demandas saem junto: a guarda protege pessoas escaladas,
        não vagas vazias. Não há cascata sobre alocações.
        """
        band = self.band(band_id)
        if band.assignment_count > 0:
            raise ShiftBandInUseError()
        return self._replacing_bands(tuple(other for other in self.bands if other.id != band_id))

    def declare_demand(
        self,
        demand_id: ShiftDemandId,
        band_id: ShiftBandId,
        job_function_id: JobFunctionId,
        quantity: DemandQuantity,
    ) -> "Schedule":
        """Declara a demanda de uma função na faixa (uma por função, ADR 4.1.0010)."""
        band = self.band(band_id)
        demand = ShiftDemand(id=demand_id, job_function_id=job_function_id, quantity=quantity)
        return self._replacing_band(band.with_demand(demand))

    def change_demand_quantity(
        self, demand_id: ShiftDemandId, quantity: DemandQuantity
    ) -> "Schedule":
        """Troca a quantidade-alvo — abaixo dos alocados não é recusado (N é alvo).

        O próprio N devolve `self` (no-op, ADR 4.3.0001 §4).
        """
        band, demand = self.locate_demand(demand_id)
        if quantity == demand.quantity:
            return self
        return self._replacing_demand(band, demand.with_quantity(quantity))

    def withdraw_demand(self, demand_id: ShiftDemandId) -> "Schedule":
        """Retira a demanda — recusa enquanto houver alocação (§5.21)."""
        band, demand = self.locate_demand(demand_id)
        if demand.allocated > 0:
            raise ShiftDemandInUseError()
        return self._replacing_band(band.without_demand(demand_id))

    def assign(
        self,
        assignment_id: AssignmentId,
        demand_id: ShiftDemandId,
        employee_id: EmployeeId,
        *,
        counts_toward_workload: bool = True,
        function_exception: bool = False,
    ) -> "Schedule":
        """Aloca o registro a uma vaga da demanda.

        Grava as duas marcas recebidas; o intervalo nasce `None` (herda o da
        faixa). O registro já nesta demanda → `DuplicateAssignmentError` (da
        `ShiftDemand`); em outra demanda da mesma faixa →
        `DuplicateAssignmentInBandError` (da `ShiftBand`, §5.23). Faixas
        distintas seguem aceitas.
        """
        band, demand = self.locate_demand(demand_id)
        assignment = Assignment(
            id=assignment_id,
            employee_id=employee_id,
            counts_toward_workload=counts_toward_workload,
            function_exception=function_exception,
        )
        return self._replacing_demand(band, demand.with_assignment(assignment))

    def unassign(self, assignment_id: AssignmentId) -> "Schedule":
        """Desaloca — a vaga volta a ficar descoberta."""
        band, demand, _ = self.locate_assignment(assignment_id)
        return self._replacing_demand(band, demand.without_assignment(assignment_id))

    def declare_workload_counting(self, assignment_id: AssignmentId, counts: bool) -> "Schedule":
        """Re-declara se as horas da alocação contam para a carga (ADR 4.1.0003 (d))."""
        band, demand, assignment = self.locate_assignment(assignment_id)
        if counts == assignment.counts_toward_workload:
            return self
        return self._replacing_assignment(
            band, demand, assignment.declare_workload_counting(counts)
        )

    def declare_allocation_break(
        self, assignment_id: AssignmentId, break_minutes: int | None
    ) -> "Schedule":
        """Declara o intervalo próprio da alocação; `None` volta a herdar o da faixa.

        Negativo → `InvalidAssignmentBreakError` (da `Assignment`); `>=` a duração
        nominal da faixa → a mesma exceção (da `ShiftBand`, ADR 4.1.0011).
        """
        band, demand, assignment = self.locate_assignment(assignment_id)
        if break_minutes == assignment.break_minutes:
            return self
        return self._replacing_assignment(band, demand, assignment.declare_break(break_minutes))

    # --- reconstrução da árvore -----------------------------------------------------

    def _replacing_bands(self, bands: tuple[ShiftBand, ...]) -> "Schedule":
        return dataclasses.replace(self, bands=bands, version=self.version + 1)

    def _replacing_band(self, band: ShiftBand) -> "Schedule":
        return self._replacing_bands(
            tuple(band if existing.id == band.id else existing for existing in self.bands)
        )

    def _replacing_demand(self, band: ShiftBand, demand: ShiftDemand) -> "Schedule":
        demands = tuple(
            demand if existing.id == demand.id else existing for existing in band.demands
        )
        return self._replacing_band(band.with_demands(demands))

    def _replacing_assignment(
        self, band: ShiftBand, demand: ShiftDemand, assignment: Assignment
    ) -> "Schedule":
        assignments = tuple(
            assignment if existing.id == assignment.id else existing
            for existing in demand.assignments
        )
        return self._replacing_demand(band, dataclasses.replace(demand, assignments=assignments))

    # --- leituras -------------------------------------------------------------------

    def band(self, band_id: ShiftBandId) -> ShiftBand:
        """A faixa de id dado."""
        for band in self.bands:
            if band.id == band_id:
                return band
        raise ShiftBandNotFoundError()

    def locate_demand(self, demand_id: ShiftDemandId) -> tuple[ShiftBand, ShiftDemand]:
        """A demanda de id dado e a faixa que a contém."""
        for band in self.bands:
            for demand in band.demands:
                if demand.id == demand_id:
                    return (band, demand)
        raise ShiftDemandNotFoundError()

    def locate_assignment(
        self, assignment_id: AssignmentId
    ) -> tuple[ShiftBand, ShiftDemand, Assignment]:
        """A alocação de id dado, com a demanda e a faixa que a contêm."""
        for band in self.bands:
            for demand in band.demands:
                for assignment in demand.assignments:
                    if assignment.id == assignment_id:
                        return (band, demand, assignment)
        raise AssignmentNotFoundError()

    def bands_of(self, operational_day: date) -> tuple[ShiftBand, ...]:
        """As faixas do dia **operacional** dado (não do dia civil)."""
        return tuple(
            band for band in self.bands if self.operational_day_of(band) == operational_day
        )

    def operational_day_of(self, band: ShiftBand) -> date:
        """Dia operacional da faixa: o do corte que contém o seu início (§5.8)."""
        return self.calendar.operational_day_of(band.time_range.start)

    def worked_minutes_of(self, assignment_id: AssignmentId) -> int:
        """Minutos trabalhados da alocação — `horas(a)`, delegando ao sítio único."""
        band, _, assignment = self.locate_assignment(assignment_id)
        return band.time_range.worked_minutes(band.effective_break_of(assignment))

    def effective_break_minutes_of(self, assignment_id: AssignmentId) -> int:
        """Minutos de **intervalo** efetivo da alocação (não trabalhados)."""
        band, _, assignment = self.locate_assignment(assignment_id)
        return band.effective_break_of(assignment)

    def has_break_divergence(self, assignment_id: AssignmentId) -> bool:
        """Se a alocação declara intervalo diferente do da faixa (a terceira marca).

        Recebe o **id** e delega à faixa que contém a alocação, passando a
        instância **localizada** no agregado — o homônimo da faixa recebe a
        entidade.
        """
        band, _, assignment = self.locate_assignment(assignment_id)
        return band.has_break_divergence(assignment)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Schedule):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

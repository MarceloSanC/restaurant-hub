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

Entidade **frozen**, igualdade por **identidade**.
"""

from dataclasses import dataclass
from datetime import date

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    AssignmentNotFoundError,
    DuplicateEntityIdError,
    DuplicateShiftBandError,
    InvalidIdentifierError,
    InvalidSchedulePeriodError,
    InvalidScheduleVersionError,
    ShiftBandNotFoundError,
    ShiftDemandNotFoundError,
    TimeRangeOutsidePeriodError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
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


def _repetidos(ids: tuple[str, ...]) -> bool:
    """Se algum valor se repete — par a par sobre a coleção inteira."""
    return any(valor == outro for indice, valor in enumerate(ids) for outro in ids[indice + 1 :])


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
        self._validar_ids_internos()
        chaves = tuple(faixa.time_range.hours_key for faixa in self.bands)
        for indice, chave in enumerate(chaves):
            if chave in chaves[indice + 1 :]:
                raise DuplicateShiftBandError()
        for faixa in self.bands:
            if not self.period.contains(self.operational_day_of(faixa)):
                raise TimeRangeOutsidePeriodError()

    def _validar_ids_internos(self) -> None:
        demandas = tuple(demanda for faixa in self.bands for demanda in faixa.demands)
        alocacoes = tuple(alocacao for demanda in demandas for alocacao in demanda.assignments)
        if _repetidos(tuple(faixa.id for faixa in self.bands)):
            raise DuplicateEntityIdError("ShiftBandId")
        if _repetidos(tuple(demanda.id for demanda in demandas)):
            raise DuplicateEntityIdError("ShiftDemandId")
        if _repetidos(tuple(alocacao.id for alocacao in alocacoes)):
            raise DuplicateEntityIdError("AssignmentId")

    # --- leituras -------------------------------------------------------------------

    def band(self, band_id: ShiftBandId) -> ShiftBand:
        """A faixa de id dado."""
        for faixa in self.bands:
            if faixa.id == band_id:
                return faixa
        raise ShiftBandNotFoundError()

    def locate_demand(self, demand_id: ShiftDemandId) -> tuple[ShiftBand, ShiftDemand]:
        """A demanda de id dado e a faixa que a contém."""
        for faixa in self.bands:
            for demanda in faixa.demands:
                if demanda.id == demand_id:
                    return (faixa, demanda)
        raise ShiftDemandNotFoundError()

    def locate_assignment(
        self, assignment_id: AssignmentId
    ) -> tuple[ShiftBand, ShiftDemand, Assignment]:
        """A alocação de id dado, com a demanda e a faixa que a contêm."""
        for faixa in self.bands:
            for demanda in faixa.demands:
                for alocacao in demanda.assignments:
                    if alocacao.id == assignment_id:
                        return (faixa, demanda, alocacao)
        raise AssignmentNotFoundError()

    def bands_of(self, operational_day: date) -> tuple[ShiftBand, ...]:
        """As faixas do dia **operacional** dado (não do dia civil)."""
        return tuple(
            faixa for faixa in self.bands if self.operational_day_of(faixa) == operational_day
        )

    def operational_day_of(self, band: ShiftBand) -> date:
        """Dia operacional da faixa: o do corte que contém o seu início (§5.8)."""
        return self.calendar.operational_day_of(band.time_range.start)

    def worked_minutes_of(self, assignment_id: AssignmentId) -> int:
        """Minutos trabalhados da alocação — `horas(a)`, delegando ao sítio único."""
        faixa, _, alocacao = self.locate_assignment(assignment_id)
        return faixa.time_range.worked_minutes(faixa.effective_break_of(alocacao))

    def effective_break_minutes_of(self, assignment_id: AssignmentId) -> int:
        """Minutos de **intervalo** efetivo da alocação (não trabalhados)."""
        faixa, _, alocacao = self.locate_assignment(assignment_id)
        return faixa.effective_break_of(alocacao)

    def has_break_divergence(self, assignment_id: AssignmentId) -> bool:
        """Se a alocação declara intervalo diferente do da faixa (a terceira marca).

        Recebe o **id** e delega à faixa que contém a alocação, passando a
        instância **localizada** no agregado — o homônimo da faixa recebe a
        entidade.
        """
        faixa, _, alocacao = self.locate_assignment(assignment_id)
        return faixa.has_break_divergence(alocacao)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Schedule):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

"""Entidade ShiftBand — a faixa habilitada de um dia da escala e as suas demandas.

Interna ao agregado `Schedule` (ADR 4.1.0009): a "faixa de funcionamento" do dia
(ADR 4.1.0010), com o seu `TimeRange` e uma demanda por função.

A faixa é o **único** nível que vê `nominal_minutes` **e** as alocações ao mesmo
tempo; por isso vivem aqui:

- o **teto** do intervalo declarado da alocação — `break_minutes <
  time_range.nominal_minutes` (`InvalidAssignmentBreakError`, ADR 4.1.0011);
- o **intervalo efetivo** da alocação (o dela, se declarado; senão o da faixa) e
  a **divergência** entre os dois, **derivada** e nunca armazenada
  (concept §5.13);
- **uma vaga por registro na faixa** — o mesmo `employee_id` em alocações de
  demandas **distintas** (`DuplicateAssignmentInBandError`, ADR 4.1.0012). O
  mesmo registro duas vezes na **mesma** demanda é a `DuplicateAssignmentError`
  da `ShiftDemand`: as duas linhas da §6 são disjuntas por nível.

As checagens par a par varrem a coleção **inteira** (a reidratação da 4.4 entra
por aqui). Entidade **frozen**: transições via `dataclasses.replace`,
revalidadas pelo `__post_init__` — encurtar a faixa abaixo de um intervalo já
declarado é recusado sem checagem extra. Igualdade por **identidade**.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateAssignmentInBandError,
    DuplicateEntityIdError,
    DuplicateShiftDemandError,
    InvalidAssignmentBreakError,
    InvalidIdentifierError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange


@dataclass(frozen=True, eq=False)
class ShiftBand:
    """Faixa habilitada de um dia da escala.

    Attributes:
        id: identidade da faixa.
        time_range: o par de instantes e o intervalo declarado da faixa.
        demands: as demandas da faixa, uma por função.
    """

    id: ShiftBandId
    time_range: TimeRange
    demands: tuple[ShiftDemand, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("faixa")
        for index, demand in enumerate(self.demands):
            for other_demand in self.demands[index + 1 :]:
                if demand.id == other_demand.id:
                    raise DuplicateEntityIdError("ShiftDemandId")
                if demand.job_function_id == other_demand.job_function_id:
                    raise DuplicateShiftDemandError()
        nominal = self.time_range.nominal_minutes
        assignments = self._assignments()
        for assignment in assignments:
            if assignment.break_minutes is not None and assignment.break_minutes >= nominal:
                raise InvalidAssignmentBreakError(
                    "intervalo deve ser menor que a duração nominal da faixa"
                )
        # Entre demandas: dentro de uma mesma demanda a ShiftDemand já recusou
        # (DuplicateAssignmentError), logo todo par que chega aqui é de demandas
        # distintas. Par a par sobre a coleção inteira, não só vizinhos.
        for position, assignment in enumerate(assignments):
            for other_assignment in assignments[position + 1 :]:
                if assignment.employee_id == other_assignment.employee_id:
                    raise DuplicateAssignmentInBandError()

    def _assignments(self) -> tuple[Assignment, ...]:
        return tuple(assignment for demand in self.demands for assignment in demand.assignments)

    @property
    def assignment_count(self) -> int:
        """Quantas alocações a faixa tem, somadas sobre todas as demandas."""
        return sum(demand.allocated for demand in self.demands)

    def effective_break_of(self, assignment: Assignment) -> int:
        """Intervalo efetivo da alocação: o dela, se declarado; senão o da faixa."""
        if assignment.break_minutes is None:
            return self.time_range.break_minutes
        return assignment.break_minutes

    def has_break_divergence(self, assignment: Assignment) -> bool:
        """Se a alocação declara intervalo **diferente** do da faixa (derivado)."""
        return (
            assignment.break_minutes is not None
            and assignment.break_minutes != self.time_range.break_minutes
        )

    def rescheduled_to(self, start: datetime, end: datetime) -> "ShiftBand":
        """Outra faixa de relógio, preservando intervalo, demandas e alocações."""
        return dataclasses.replace(self, time_range=self.time_range.with_bounds(start, end))

    def with_band_break(self, break_minutes: int) -> "ShiftBand":
        """Mesma faixa com outro intervalo declarado da faixa."""
        return dataclasses.replace(self, time_range=self.time_range.with_break(break_minutes))

    def with_demand(self, demand: ShiftDemand) -> "ShiftBand":
        """Acrescenta uma demanda — duplicidade é recusada na revalidação."""
        return dataclasses.replace(self, demands=(*self.demands, demand))

    def with_demands(self, demands: tuple[ShiftDemand, ...]) -> "ShiftBand":
        """Substitui o conjunto de demandas (revalidado)."""
        return dataclasses.replace(self, demands=demands)

    def without_demand(self, demand_id: ShiftDemandId) -> "ShiftBand":
        """Retira a demanda de id dado — id inexistente é no-op silencioso.

        A recusa `ShiftDemandNotFoundError` é da raiz, que é quem localiza.
        """
        remaining = tuple(demand for demand in self.demands if demand.id != demand_id)
        return dataclasses.replace(self, demands=remaining)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShiftBand):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

"""Entidade ShiftDemand — a demanda de uma função numa faixa, e as suas alocações.

Interna ao agregado `Schedule` (ADR 4.1.0009), contida numa `ShiftBand`: uma
demanda por (faixa, função) (ADR 4.1.0010) — a unicidade da função é checada na
faixa, que é quem possui as demandas.

**N é alvo, não teto** (ADR 4.1.0003 (g)): alocados acima de `quantity` não é
recusado aqui; é situação de política da 4.2.

Duas checagens par a par sobre a coleção **inteira** de alocações, no molde de
`staff/domain/entities/employee.py` (a reidratação da 4.4 entra por aqui):
o mesmo registro duas vezes **nesta** demanda (`DuplicateAssignmentError`) e dois
`AssignmentId` iguais (`DuplicateEntityIdError`). O mesmo registro em demandas
**distintas** da mesma faixa é outra linha da §6 e vive na `ShiftBand`
(`DuplicateAssignmentInBandError`).

Entidade **frozen**: transições devolvem nova instância via
`dataclasses.replace`, revalidada pelo `__post_init__`. Igualdade por
**identidade**.
"""

import dataclasses
from dataclasses import dataclass

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateAssignmentError,
    DuplicateEntityIdError,
    InvalidIdentifierError,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    JobFunctionId,
    ShiftDemandId,
)


@dataclass(frozen=True, eq=False)
class ShiftDemand:
    """Demanda de uma função numa faixa.

    Attributes:
        id: identidade da demanda.
        job_function_id: a função demandada (valor emitido por staff).
        quantity: quantidade-alvo de pessoas.
        assignments: as alocações que ocupam vagas desta demanda.
    """

    id: ShiftDemandId
    job_function_id: JobFunctionId
    quantity: DemandQuantity
    assignments: tuple[Assignment, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("demanda")
        if not self.job_function_id.strip():
            raise InvalidIdentifierError("função da demanda")
        # Par a par sobre a coleção inteira — não só vizinhos: a reidratação da
        # 4.4 e as transições (via replace) passam por aqui.
        for index, assignment in enumerate(self.assignments):
            for other in self.assignments[index + 1 :]:
                if assignment.id == other.id:
                    raise DuplicateEntityIdError("AssignmentId")
                if assignment.employee_id == other.employee_id:
                    raise DuplicateAssignmentError()

    @property
    def allocated(self) -> int:
        """Quantas vagas desta demanda estão ocupadas."""
        return len(self.assignments)

    def with_quantity(self, quantity: DemandQuantity) -> "ShiftDemand":
        """Mesma demanda com outra quantidade-alvo (pode ficar abaixo de `allocated`)."""
        return dataclasses.replace(self, quantity=quantity)

    def with_assignment(self, assignment: Assignment) -> "ShiftDemand":
        """Acrescenta uma alocação — duplicidade é recusada na revalidação."""
        return dataclasses.replace(self, assignments=(*self.assignments, assignment))

    def without_assignment(self, assignment_id: AssignmentId) -> "ShiftDemand":
        """Retira a alocação de id dado — id inexistente é no-op silencioso.

        A recusa `AssignmentNotFoundError` é da raiz (`unassign`), que é quem
        localiza a alocação no agregado; não é duplicada aqui.
        """
        remaining = tuple(
            assignment for assignment in self.assignments if assignment.id != assignment_id
        )
        return dataclasses.replace(self, assignments=remaining)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShiftDemand):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

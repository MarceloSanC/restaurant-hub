"""Entidade Assignment — a alocação de um registro a uma vaga de demanda.

Interna ao agregado `Schedule` (ADR 4.1.0009): alcançada só pela raiz, através
da `ShiftBand` e da `ShiftDemand` que a contêm. Carrega as **três marcas** da
alocação:

- `counts_toward_workload` — se as horas contam para a carga (ADR 4.1.0003 (d));
  default "conta";
- `function_exception` — alocação em função que o registro não detém, só por
  declaração explícita (ADR 4.1.0003 (f)). **Sem mutação na v1**, por
  atribuição (a pergunta é lacuna da 4.2), não por irrevogabilidade (concept §7);
- `break_minutes` — o intervalo próprio da alocação; `None` = herda o da faixa
  (ADR 4.1.0011).

Aqui só o **piso** do intervalo (`>= 0`): o teto (`< nominal_minutes`) é da
`ShiftBand`, o único nível que conhece a duração da faixa e as alocações ao
mesmo tempo (concept §5.6).

Entidade **frozen**: transições devolvem nova instância via
`dataclasses.replace`, revalidada pelo `__post_init__`. Igualdade por
**identidade**.
"""

import dataclasses
from dataclasses import dataclass

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidAssignmentBreakError,
    InvalidIdentifierError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)


@dataclass(frozen=True, eq=False)
class Assignment:
    """Alocação de um registro de funcionário a uma vaga.

    Attributes:
        id: identidade da alocação.
        employee_id: o registro alocado (valor emitido por staff, tipo deste BC).
        counts_toward_workload: se as horas contam para a carga do registro.
        function_exception: se é alocação declarada em função não detida.
        break_minutes: intervalo próprio, em minutos; `None` herda o da faixa.
    """

    id: AssignmentId
    employee_id: EmployeeId
    counts_toward_workload: bool = True
    function_exception: bool = False
    break_minutes: int | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("alocação")
        if not self.employee_id.strip():
            raise InvalidIdentifierError("funcionário da alocação")
        if self.break_minutes is not None and self.break_minutes < 0:
            raise InvalidAssignmentBreakError("intervalo não pode ser negativo")

    def declare_workload_counting(self, counts: bool) -> "Assignment":
        """Declara se as horas desta alocação contam para a carga."""
        return dataclasses.replace(self, counts_toward_workload=counts)

    def declare_break(self, break_minutes: int | None) -> "Assignment":
        """Declara o intervalo próprio; `None` limpa e volta a herdar o da faixa."""
        return dataclasses.replace(self, break_minutes=break_minutes)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Assignment):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

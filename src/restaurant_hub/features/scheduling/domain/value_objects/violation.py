"""Value object Violation — o resultado de uma política, com identidade para o aceite.

Uma violação **descreve** um estado da escala; quem recusa (`block`) ou pede aceite
(`warn`) é o use case da 4.3, que compara as violações antes e depois da mutação
pela `key` (ADR 4.2.0002).

**Identidade sem medida** (concept 4.2 §5.8). A `key` é `(policy, employee_id,
demand_id, operational_days, assignment_ids)`; nas políticas de recorte agregado
(descanso, tetos, carga) `assignment_ids` sai da `key`, para que uma alocação a mais
no mesmo dia não vire violação "nova". A sobre-cobertura **mantém** as alocações na
`key`, porque o aceite dela é por alocação excedente (ADR 4.1.0003 (g)). A medida
(`observed`/`limit`) e o conjunto completo de alocações ficam ao lado da `key`.

Sem texto livre (concept 4.2 §5.12): a mensagem é da borda.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)

_POLITICAS_COM_ALOCACOES_NA_CHAVE = frozenset(
    {
        PolicyKind.OVERLAP,
        PolicyKind.UNAVAILABILITY,
        PolicyKind.FUNCTION_MISMATCH,
        PolicyKind.OVER_COVERAGE,
        PolicyKind.BREAK_DIVERGENCE,
    }
)


class ViolationKey(NamedTuple):
    """Identidade estável de uma violação entre avaliações do mesmo estado."""

    policy: PolicyKind
    employee_id: EmployeeId | None
    demand_id: ShiftDemandId | None
    operational_days: tuple[date, ...]
    assignment_ids: frozenset[AssignmentId]


@dataclass(frozen=True)
class Violation:
    """Uma violação de política na escala avaliada.

    Attributes:
        policy: a política que a produziu.
        mode: o modo da regra da política na config.
        employee_id: o registro sujeito; `None` só na sobre-cobertura.
        demand_id: a demanda sujeito; só na sobre-cobertura.
        operational_days: os dias operacionais do recorte, distintos e ordenados.
        assignment_ids: as alocações envolvidas (pode ser vazio na carga).
        observed: a medida, na unidade da política (concept 4.2 §5.9).
        limit: a referência da medida.
    """

    policy: PolicyKind
    mode: EnforcementMode
    employee_id: EmployeeId | None
    demand_id: ShiftDemandId | None
    operational_days: tuple[date, ...]
    assignment_ids: frozenset[AssignmentId]
    observed: Decimal
    limit: Decimal

    @property
    def key(self) -> ViolationKey:
        """Identidade para o aceite — sem modo e sem medida (ADR 4.2.0002 §5)."""
        alocacoes = (
            self.assignment_ids
            if self.policy in _POLITICAS_COM_ALOCACOES_NA_CHAVE
            else frozenset[AssignmentId]()
        )
        return ViolationKey(
            policy=self.policy,
            employee_id=self.employee_id,
            demand_id=self.demand_id,
            operational_days=self.operational_days,
            assignment_ids=alocacoes,
        )

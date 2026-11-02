"""Política de descanso entre jornadas — interjornada (doc §3.6.2; CLT art. 66).

Por registro, os dias operacionais **com alocação** em ordem (vizinhas incluídas);
para cada par consecutivo `(dᵢ, dⱼ)`:
`descanso = min(start das alocações de dⱼ) - max(end das alocações de dᵢ)`, e viola
se `descanso < min_rest_minutes`. Dias sem alocação no meio são pulados. O par é
reportado se um dos dois dias é da escala avaliada (concept 4.2 §5.6).

**Limites declarados da v1** (concept 4.2 §5.7): lacuna dentro do **mesmo** dia
operacional não conta (jornada partida é intrajornada, evolução); alocações
contíguas que atravessam o **corte** caem em dias distintos e dão descanso 0. O
descanso pode sair **negativo** quando há sobreposição entre os dias — as duas
políticas reportam. Medida: minutos de descanso; limite: o mínimo da config.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    AllocationView,
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import EmployeeId
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

_ONE_MINUTE = timedelta(minutes=1)


class RestBetweenShiftsPolicy:
    """Descanso mínimo entre os dias operacionais trabalhados — `warn` por default."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.REST_BETWEEN_SHIFTS

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        period = context.schedule.period
        by_employee: dict[EmployeeId, dict[date, list[AllocationView]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for allocation in context.all_allocations:
            by_employee[allocation.employee_id][allocation.operational_day].append(allocation)
        violations: list[Violation] = []
        for employee_id, by_day in by_employee.items():
            for earlier_day, later_day in pairwise(sorted(by_day)):
                if not (period.contains(earlier_day) or period.contains(later_day)):
                    continue
                end = max(allocation.time_range.end for allocation in by_day[earlier_day])
                start = min(allocation.time_range.start for allocation in by_day[later_day])
                rest_minutes = (start - end) // _ONE_MINUTE
                if rest_minutes >= config.min_rest_minutes:
                    continue
                involved = {
                    allocation.assignment_id
                    for allocation in by_day[earlier_day]
                    if allocation.time_range.end == end
                } | {
                    allocation.assignment_id
                    for allocation in by_day[later_day]
                    if allocation.time_range.start == start
                }
                violations.append(
                    Violation(
                        policy=self.kind,
                        mode=mode,
                        employee_id=employee_id,
                        demand_id=None,
                        operational_days=(earlier_day, later_day),
                        assignment_ids=frozenset(involved),
                        observed=Decimal(rest_minutes),
                        limit=Decimal(config.min_rest_minutes),
                    )
                )
        return tuple(violations)

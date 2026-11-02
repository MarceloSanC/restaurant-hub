"""Política de carga contratada — só jornada fixa (doc §3.6.5).

Por registro **ativo de jornada fixa** nos fatos — com ou sem alocação na escala:
`desvio = Σ horas(a) das alocações que contam - carga semanal vezes 60`, em minutos e
em `Decimal` exato (a carga de staff é fracionária: 22,5h). Viola se
`desvio > tolerância` (direção `excess`, default) ou `|desvio| > tolerância`
(`both`). Sob demanda não tem carga e não é sujeito. Só as alocações com "conta
para a carga" entram (ADR 4.1.0003 (d)); só a escala avaliada (a semana de apuração
é o período — ADR 4.1.0002 §1).

**Limites declarados** (concept 4.2 §5.4, §5.7): a indisponibilidade não abate a
carga; a completude do quadro sem alocação (os sujeitos de `both`) é contrato da
4.3. Medida: minutos que contam; limite: carga vezes 60.
"""

from collections import defaultdict
from decimal import Decimal

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    AllocationView,
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import EmployeeId
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
    ValidationConfig,
    WorkloadDirection,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

_MINUTES_PER_HOUR = 60


class WorkloadPolicy:
    """Carga contratada da jornada fixa — `warn` por default."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.WORKLOAD

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        counted_by_employee: dict[EmployeeId, list[AllocationView]] = defaultdict(list)
        for allocation in context.allocations:
            if allocation.counts_toward_workload:
                counted_by_employee[allocation.employee_id].append(allocation)
        tolerance = Decimal(config.workload_tolerance_minutes)
        violations: list[Violation] = []
        for facts in context.active_facts:
            contracted_hours = facts.contracted_weekly_hours
            if contracted_hours is None:
                continue
            allocations = counted_by_employee[facts.employee_id]
            minutes = Decimal(sum(allocation.worked_minutes for allocation in allocations))
            contracted_minutes = contracted_hours * _MINUTES_PER_HOUR
            deviation = minutes - contracted_minutes
            if config.workload_direction is WorkloadDirection.BOTH:
                deviation = abs(deviation)
            if deviation <= tolerance:
                continue
            violations.append(
                Violation(
                    policy=self.kind,
                    mode=mode,
                    employee_id=facts.employee_id,
                    demand_id=None,
                    operational_days=context.schedule.period.operational_days,
                    assignment_ids=frozenset(
                        allocation.assignment_id for allocation in allocations
                    ),
                    observed=minutes,
                    limit=contracted_minutes,
                )
            )
        return tuple(violations)

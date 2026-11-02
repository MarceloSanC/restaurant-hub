"""Política de sobreposição de alocações do mesmo registro (doc §3.6.1).

Viola o par de alocações do **mesmo** registro cujas faixas se sobrepõem na
semântica semi-aberta (`TimeRange.overlaps` — adjacentes não violam). O mesmo
registro duas vezes na **mesma** faixa já é recusado pelo agregado (ADR 4.1.0012);
aqui ficam as faixas **distintas**, inclusive entre a escala avaliada e as vizinhas
— o par é reportado se ao menos uma das duas alocações é da avaliada (concept 4.2
§5.6). Medida: minutos da interseção; limite 0.
"""

from datetime import timedelta
from decimal import Decimal

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

_ONE_MINUTE = timedelta(minutes=1)


class OverlapPolicy:
    """Sobreposição — `block` por default (impossibilidade física)."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.OVERLAP

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        allocations = context.all_allocations
        violations: list[Violation] = []
        for index, first in enumerate(allocations):
            for second in allocations[index + 1 :]:
                if first.employee_id != second.employee_id:
                    continue
                if not (first.in_evaluated or second.in_evaluated):
                    continue
                if not first.time_range.overlaps(second.time_range):
                    continue
                start = max(first.time_range.start, second.time_range.start)
                end = min(first.time_range.end, second.time_range.end)
                violations.append(
                    Violation(
                        policy=self.kind,
                        mode=mode,
                        employee_id=first.employee_id,
                        demand_id=None,
                        operational_days=tuple(
                            sorted({first.operational_day, second.operational_day})
                        ),
                        assignment_ids=frozenset({first.assignment_id, second.assignment_id}),
                        observed=Decimal((end - start) // _ONE_MINUTE),
                        limit=Decimal(0),
                    )
                )
        return tuple(violations)

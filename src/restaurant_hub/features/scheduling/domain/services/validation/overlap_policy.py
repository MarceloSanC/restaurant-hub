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

_UM_MINUTO = timedelta(minutes=1)


class OverlapPolicy:
    """Sobreposição — `block` por default (impossibilidade física)."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.OVERLAP

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        alocacoes = context.all_allocations
        violacoes: list[Violation] = []
        for indice, uma in enumerate(alocacoes):
            for outra in alocacoes[indice + 1 :]:
                if uma.employee_id != outra.employee_id:
                    continue
                if not (uma.in_evaluated or outra.in_evaluated):
                    continue
                if not uma.time_range.overlaps(outra.time_range):
                    continue
                inicio = max(uma.time_range.start, outra.time_range.start)
                fim = min(uma.time_range.end, outra.time_range.end)
                violacoes.append(
                    Violation(
                        policy=self.kind,
                        mode=mode,
                        employee_id=uma.employee_id,
                        demand_id=None,
                        operational_days=tuple(
                            sorted({uma.operational_day, outra.operational_day})
                        ),
                        assignment_ids=frozenset({uma.assignment_id, outra.assignment_id}),
                        observed=Decimal((fim - inicio) // _UM_MINUTO),
                        limit=Decimal(0),
                    )
                )
        return tuple(violacoes)

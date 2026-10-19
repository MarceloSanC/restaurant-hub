"""Política de divergência de intervalo (ADR 4.1.0011 Decision 4; concept 4.2 §7 D8).

Viola a alocação da escala avaliada que declara intervalo **diferente** do da faixa
(`has_break_divergence`, derivado — o domínio representa e não escolhe). O aviso
existe para perguntar ao editor qual intervalo manter: "manter o da faixa" é
`declare_allocation_break(None)` — volta a herdar —, e a pergunta é da borda (4.5).
Medida: intervalo da alocação / intervalo da faixa (não ordinal).
"""

from decimal import Decimal

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation


class BreakDivergencePolicy:
    """Divergência de intervalo — `warn` por default, `block` configurável."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.BREAK_DIVERGENCE

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        return tuple(
            Violation(
                policy=self.kind,
                mode=mode,
                employee_id=alocacao.employee_id,
                demand_id=None,
                operational_days=(alocacao.operational_day,),
                assignment_ids=frozenset({alocacao.assignment_id}),
                observed=Decimal(alocacao.effective_break_minutes),
                limit=Decimal(alocacao.band_break_minutes),
            )
            for alocacao in context.allocations
            if alocacao.break_divergence
        )

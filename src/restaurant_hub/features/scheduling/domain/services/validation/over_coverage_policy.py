"""Política de sobre-cobertura da demanda (doc §3.6.8; ADR 4.1.0003 (g)).

`N` é **alvo, não teto**: viola a demanda da escala avaliada com mais alocados
**ativos** que `N` — por demanda, que já é única por `(faixa, função)` (ADR
4.1.0010), sem agregar faixas sobrepostas da mesma função (ADR 4.2.0002,
Alternative F). `N = 0` com alocado viola; não há divisão (a cobertura como razão
é do hub). Alocação de registro inativo não conta: a vaga lê-se descoberta (ADR
4.1.0006).

O sujeito é a **demanda** (`employee_id` vazio) e as alocações ativas entram na
`key` — o aceite é por alocação excedente (concept 4.2 §5.8). Medida: alocados
ativos / `N`.
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


class OverCoveragePolicy:
    """Sobre-cobertura — `warn` por default; o aceite grava o excedente."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.OVER_COVERAGE

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        escala = context.schedule
        violacoes: list[Violation] = []
        for faixa in escala.bands:
            for demanda in faixa.demands:
                ativas = frozenset(
                    alocacao.id
                    for alocacao in demanda.assignments
                    if context.facts_of(alocacao.employee_id).active
                )
                if len(ativas) <= demanda.quantity.value:
                    continue
                violacoes.append(
                    Violation(
                        policy=self.kind,
                        mode=mode,
                        employee_id=None,
                        demand_id=demanda.id,
                        operational_days=(escala.operational_day_of(faixa),),
                        assignment_ids=ativas,
                        observed=Decimal(len(ativas)),
                        limit=Decimal(demanda.quantity.value),
                    )
                )
        return tuple(violacoes)

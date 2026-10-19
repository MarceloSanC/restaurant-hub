"""Política de função não detida (doc §3.6.7; ADR 4.1.0003 (f); ADR 4.2.0001).

Viola a alocação da escala avaliada cuja função da demanda **não** está entre as
funções que o registro detém **no momento da avaliação** — decisão do sponsor de
2026-10-18 ("segue o cadastro atual"). A marca `function_exception` da alocação
**não é lida**: ela registra o aceite dado ao alocar; quem ganhou a função deixa de
violar e quem a perdeu passa a violar. Medida: 1 / 0 (não ordinal).
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


class FunctionMismatchPolicy:
    """Função não detida — `warn` por default; o aceite grava a exceção."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.FUNCTION_MISMATCH

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
                observed=Decimal(1),
                limit=Decimal(0),
            )
            for alocacao in context.allocations
            if alocacao.job_function_id
            not in context.facts_of(alocacao.employee_id).job_function_ids
        )

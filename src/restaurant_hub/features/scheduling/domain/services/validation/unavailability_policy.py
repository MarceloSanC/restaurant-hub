"""Política de alocação contra indisponibilidade (doc §3.6.6) — `block` fixo.

Viola a alocação da escala avaliada cuja faixa `[start, end)` se sobrepõe a alguma
janela de indisponibilidade do registro (semi-aberto: adjacente não viola). Uma
violação por alocação, por mais janelas que ela toque. Sem conversão de fuso: faixa
e janela são wall-clock ingênuo da unidade (ADR 3.1.0005).

**Medida exata** (concept 4.2 §5.9): minutos da faixa dentro de indisponibilidade,
com as janelas **unidas** (duas janelas sobrepostas não contam o trecho comum duas
vezes) e contadas ao microssegundo — as janelas de staff admitem segundos, e
`Decimal(µs) / 60_000_000` nunca passa por `float`.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

_ONE_MICROSECOND = timedelta(microseconds=1)
_MICROSECONDS_PER_MINUTE = Decimal(60_000_000)


def _covered_microseconds(intervals: list[tuple[datetime, datetime]]) -> int:
    """Duração da união dos intervalos semi-abertos, em microssegundos."""
    total = 0
    current_end: datetime | None = None
    for start, end in sorted(intervals):
        effective_start = start if current_end is None else max(start, current_end)
        if end > effective_start:
            total += (end - effective_start) // _ONE_MICROSECOND
        current_end = end if current_end is None else max(current_end, end)
    return total


class UnavailabilityPolicy:
    """Indisponibilidade — sempre habilitada, `block` (ADR 4.2.0002 §4)."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.UNAVAILABILITY

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        violations: list[Violation] = []
        for allocation in context.allocations:
            band_range = allocation.time_range
            clipped = [
                (max(band_range.start, window.start), min(band_range.end, window.end))
                for window in context.facts_of(allocation.employee_id).unavailabilities
                if band_range.start < window.end and window.start < band_range.end
            ]
            if not clipped:
                continue
            violations.append(
                Violation(
                    policy=self.kind,
                    mode=mode,
                    employee_id=allocation.employee_id,
                    demand_id=None,
                    operational_days=(allocation.operational_day,),
                    assignment_ids=frozenset({allocation.assignment_id}),
                    observed=Decimal(_covered_microseconds(clipped)) / _MICROSECONDS_PER_MINUTE,
                    limit=Decimal(0),
                )
            )
        return tuple(violations)

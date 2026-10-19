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

_UM_MICROSSEGUNDO = timedelta(microseconds=1)
_MICROSSEGUNDOS_POR_MINUTO = Decimal(60_000_000)


def _microssegundos_cobertos(intervalos: list[tuple[datetime, datetime]]) -> int:
    """Duração da união dos intervalos semi-abertos, em microssegundos."""
    total = 0
    fim_corrente: datetime | None = None
    for inicio, fim in sorted(intervalos):
        efetivo = inicio if fim_corrente is None else max(inicio, fim_corrente)
        if fim > efetivo:
            total += (fim - efetivo) // _UM_MICROSSEGUNDO
        fim_corrente = fim if fim_corrente is None else max(fim_corrente, fim)
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
        violacoes: list[Violation] = []
        for alocacao in context.allocations:
            faixa = alocacao.time_range
            recortes = [
                (max(faixa.start, janela.start), min(faixa.end, janela.end))
                for janela in context.facts_of(alocacao.employee_id).unavailabilities
                if faixa.start < janela.end and janela.start < faixa.end
            ]
            if not recortes:
                continue
            violacoes.append(
                Violation(
                    policy=self.kind,
                    mode=mode,
                    employee_id=alocacao.employee_id,
                    demand_id=None,
                    operational_days=(alocacao.operational_day,),
                    assignment_ids=frozenset({alocacao.assignment_id}),
                    observed=Decimal(_microssegundos_cobertos(recortes))
                    / _MICROSSEGUNDOS_POR_MINUTO,
                    limit=Decimal(0),
                )
            )
        return tuple(violacoes)

"""Políticas de teto de horas — por dia operacional e por semana (doc §3.6.3, §3.6.4).

Duas classes, uma por linha do ADR 4.1.0003 (a), cada uma com regra própria na
config (concept 4.2 §7 D11):

- **teto diário** (CLT arts. 58 + 59 § 2º, default 10h): por registro e dia
  operacional, `Σ horas(a) > daily_cap_minutes`;
- **teto semanal** (CF art. 7º XIII, default 44h): por registro,
  `Σ horas(a)` da escala avaliada `> weekly_cap_minutes` — a semana de apuração é o
  período de 7 dias (ADR 4.1.0002 §1; o insumo recusa outro tamanho).

`horas(a)` é o `worked_minutes` da projeção, do sítio único; a soma é **por
alocação** (concept 4.2 §7 D5): faixas distintas sobrepostas contam a interseção
duas vezes, e quem governa isso é a política de sobreposição. Só a escala avaliada
entra — os dias das vizinhas pertencem às escalas delas (concept 4.2 §5.6).
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

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


class DailyCapPolicy:
    """Teto de horas do dia operacional — `warn` por default (CLT art. 61)."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.DAILY_CAP

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        por_dia: dict[tuple[EmployeeId, date], list[AllocationView]] = defaultdict(list)
        for alocacao in context.allocations:
            por_dia[(alocacao.employee_id, alocacao.operational_day)].append(alocacao)
        violacoes: list[Violation] = []
        for (registro, _), alocacoes in por_dia.items():
            minutos = sum(alocacao.worked_minutes for alocacao in alocacoes)
            if minutos <= config.daily_cap_minutes:
                continue
            violacoes.append(
                Violation(
                    policy=self.kind,
                    mode=mode,
                    employee_id=registro,
                    demand_id=None,
                    operational_days=(alocacoes[0].operational_day,),
                    assignment_ids=frozenset(alocacao.assignment_id for alocacao in alocacoes),
                    observed=Decimal(minutos),
                    limit=Decimal(config.daily_cap_minutes),
                )
            )
        return tuple(violacoes)


class WeeklyCapPolicy:
    """Teto de horas da semana de apuração — `warn` por default."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.WEEKLY_CAP

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        por_registro: dict[EmployeeId, list[AllocationView]] = defaultdict(list)
        for alocacao in context.allocations:
            por_registro[alocacao.employee_id].append(alocacao)
        dias = context.schedule.period.operational_days
        violacoes: list[Violation] = []
        for registro, alocacoes in por_registro.items():
            minutos = sum(alocacao.worked_minutes for alocacao in alocacoes)
            if minutos <= config.weekly_cap_minutes:
                continue
            violacoes.append(
                Violation(
                    policy=self.kind,
                    mode=mode,
                    employee_id=registro,
                    demand_id=None,
                    operational_days=dias,
                    assignment_ids=frozenset(alocacao.assignment_id for alocacao in alocacoes),
                    observed=Decimal(minutos),
                    limit=Decimal(config.weekly_cap_minutes),
                )
            )
        return tuple(violacoes)

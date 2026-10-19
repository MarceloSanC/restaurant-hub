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

_MINUTOS_POR_HORA = 60


class WorkloadPolicy:
    """Carga contratada da jornada fixa — `warn` por default."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.WORKLOAD

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        que_contam: dict[EmployeeId, list[AllocationView]] = defaultdict(list)
        for alocacao in context.allocations:
            if alocacao.counts_toward_workload:
                que_contam[alocacao.employee_id].append(alocacao)
        tolerancia = Decimal(config.workload_tolerance_minutes)
        violacoes: list[Violation] = []
        for fatos in context.active_facts:
            carga = fatos.contracted_weekly_hours
            if carga is None:
                continue
            alocacoes = que_contam[fatos.employee_id]
            minutos = Decimal(sum(alocacao.worked_minutes for alocacao in alocacoes))
            contratado = carga * _MINUTOS_POR_HORA
            desvio = minutos - contratado
            if config.workload_direction is WorkloadDirection.BOTH:
                desvio = abs(desvio)
            if desvio <= tolerancia:
                continue
            violacoes.append(
                Violation(
                    policy=self.kind,
                    mode=mode,
                    employee_id=fatos.employee_id,
                    demand_id=None,
                    operational_days=context.schedule.period.operational_days,
                    assignment_ids=frozenset(alocacao.assignment_id for alocacao in alocacoes),
                    observed=minutos,
                    limit=contratado,
                )
            )
        return tuple(violacoes)

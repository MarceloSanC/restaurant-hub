"""Política de descanso entre jornadas — interjornada (doc §3.6.2; CLT art. 66).

Por registro, os dias operacionais **com alocação** em ordem (vizinhas incluídas);
para cada par consecutivo `(dᵢ, dⱼ)`:
`descanso = min(start das alocações de dⱼ) - max(end das alocações de dᵢ)`, e viola
se `descanso < min_rest_minutes`. Dias sem alocação no meio são pulados. O par é
reportado se um dos dois dias é da escala avaliada (concept 4.2 §5.6).

**Limites declarados da v1** (concept 4.2 §5.7): lacuna dentro do **mesmo** dia
operacional não conta (jornada partida é intrajornada, evolução); alocações
contíguas que atravessam o **corte** caem em dias distintos e dão descanso 0. O
descanso pode sair **negativo** quando há sobreposição entre os dias — as duas
políticas reportam. Medida: minutos de descanso; limite: o mínimo da config.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

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

_UM_MINUTO = timedelta(minutes=1)


class RestBetweenShiftsPolicy:
    """Descanso mínimo entre os dias operacionais trabalhados — `warn` por default."""

    @property
    def kind(self) -> PolicyKind:
        return PolicyKind.REST_BETWEEN_SHIFTS

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        mode = config.rule_for(self.kind).mode
        periodo = context.schedule.period
        por_registro: dict[EmployeeId, dict[date, list[AllocationView]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for alocacao in context.all_allocations:
            por_registro[alocacao.employee_id][alocacao.operational_day].append(alocacao)
        violacoes: list[Violation] = []
        for registro, por_dia in por_registro.items():
            for anterior, seguinte in pairwise(sorted(por_dia)):
                if not (periodo.contains(anterior) or periodo.contains(seguinte)):
                    continue
                fim = max(alocacao.time_range.end for alocacao in por_dia[anterior])
                inicio = min(alocacao.time_range.start for alocacao in por_dia[seguinte])
                descanso = (inicio - fim) // _UM_MINUTO
                if descanso >= config.min_rest_minutes:
                    continue
                envolvidas = {
                    alocacao.assignment_id
                    for alocacao in por_dia[anterior]
                    if alocacao.time_range.end == fim
                } | {
                    alocacao.assignment_id
                    for alocacao in por_dia[seguinte]
                    if alocacao.time_range.start == inicio
                }
                violacoes.append(
                    Violation(
                        policy=self.kind,
                        mode=mode,
                        employee_id=registro,
                        demand_id=None,
                        operational_days=(anterior, seguinte),
                        assignment_ids=frozenset(envolvidas),
                        observed=Decimal(descanso),
                        limit=Decimal(config.min_rest_minutes),
                    )
                )
        return tuple(violacoes)

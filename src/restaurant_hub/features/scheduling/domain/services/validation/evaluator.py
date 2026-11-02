"""Avaliador das políticas de validação da escala (roadmap 4.2; concept 4.2 §5.10-§5.11).

Aplica **só as políticas habilitadas** na config do restaurante e devolve as
violações em ordem determinística, separando `block` de `warn`. Não recusa nada: a
recusa (`block`) e o pedido de aceite (`warn`) são da 4.3, que compara as violações
antes e depois da mutação pela `key` (ADR 4.2.0002). Todas as habilitadas rodam —
sem curto-circuito no primeiro `block`, porque a UI mostra tudo ao vivo.

`DEFAULT_POLICIES` tem **uma** política por `PolicyKind`, na ordem do enum (travado
por teste). Política nova = classe + membro do enum + campo na config.
"""

from dataclasses import dataclass

from restaurant_hub.features.scheduling.domain.services.validation import (
    break_divergence_policy,
    function_mismatch_policy,
    max_hours_policy,
    over_coverage_policy,
    overlap_policy,
    rest_between_shifts_policy,
    unavailability_policy,
    workload_policy,
)
from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.services.validation.policy_protocol import (
    ValidationPolicy,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

DEFAULT_POLICIES: tuple[ValidationPolicy, ...] = (
    overlap_policy.OverlapPolicy(),
    unavailability_policy.UnavailabilityPolicy(),
    rest_between_shifts_policy.RestBetweenShiftsPolicy(),
    max_hours_policy.DailyCapPolicy(),
    max_hours_policy.WeeklyCapPolicy(),
    workload_policy.WorkloadPolicy(),
    function_mismatch_policy.FunctionMismatchPolicy(),
    over_coverage_policy.OverCoveragePolicy(),
    break_divergence_policy.BreakDivergencePolicy(),
)

_POSITION = {kind: position for position, kind in enumerate(PolicyKind)}


@dataclass(frozen=True)
class Evaluation:
    """O resultado de uma avaliação.

    Attributes:
        violations: todas as violações, em ordem determinística (concept 4.2 §5.10).
    """

    violations: tuple[Violation, ...]

    @property
    def blocking(self) -> tuple[Violation, ...]:
        """As violações em modo `block` — as que a 4.3 recusa."""
        return tuple(v for v in self.violations if v.mode is EnforcementMode.BLOCK)

    @property
    def warnings(self) -> tuple[Violation, ...]:
        """As violações em modo `warn` — as que pedem aceite consciente."""
        return tuple(v for v in self.violations if v.mode is EnforcementMode.WARN)


def _sort_key(violation: Violation) -> tuple[int, tuple[object, ...], str, str, tuple[str, ...]]:
    return (
        _POSITION[violation.policy],
        violation.operational_days,
        violation.employee_id or "",
        violation.demand_id or "",
        tuple(sorted(violation.assignment_ids)),
    )


def evaluate(
    context: EvaluationContext,
    config: ValidationConfig,
    policies: tuple[ValidationPolicy, ...] = DEFAULT_POLICIES,
) -> Evaluation:
    """As violações da escala avaliada, só das políticas habilitadas na config."""
    violations = [
        violation
        for policy in policies
        if config.rule_for(policy.kind).enabled
        for violation in policy.evaluate(context, config)
    ]
    return Evaluation(violations=tuple(sorted(violations, key=_sort_key)))

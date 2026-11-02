"""Use case: avaliar ao vivo um lote de operações, sem gravar (ADR 4.3.0001).

Aplica o lote em memória sobre a versão que o editor viu e devolve a escala resultante
com **todas** as violações, mais as **introduzidas** separadas por modo — a tela do
editor mostra tudo e destaca o que a mudança traria. Nunca recusa por violação: a
recusa é do publish.
"""

from restaurant_hub.features.scheduling.application.dtos.queries import EvaluateScheduleQuery
from restaurant_hub.features.scheduling.application.dtos.results import (
    EvaluationResult,
    to_evaluation_result,
    to_schedule_result,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    AccessGuard,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffReadPort,
)
from restaurant_hub.features.scheduling.application.use_cases._publish import (
    load_for_edit,
    run_batch,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
)


class EvaluateScheduleUseCase:
    """Avalia o lote e separa as violações que ele introduz."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        config: ScheduleConfigRepository,
        staff: StaffReadPort,
        guard: AccessGuard,
    ) -> None:
        self._schedules = schedules
        self._config = config
        self._staff = staff
        self._guard = guard

    def execute(self, query: EvaluateScheduleQuery) -> EvaluationResult:
        """Avalia sem gravar.

        Raises:
            ScheduleNotFoundError, ScheduleVersionConflictError, IdentifierInUseError,
            MissingStaffRecordsError, os erros por operação e os do domínio (crus).
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3).
        self._guard.authorize(
            query.actor,
            PERMISSION_MANAGE_SCHEDULE,
            tenant_id=query.tenant_id,
            unit_id=query.unit_id,
        )
        carregada = load_for_edit(
            self._schedules,
            (query.tenant_id, query.unit_id, query.schedule_id),
            query.expected_version,
        )
        lote = run_batch(self._schedules, self._config, self._staff, carregada, query.operations)
        escala = to_schedule_result(
            lote.after, lote.view.members, lote.view.function_names, lote.after_violations
        )
        return to_evaluation_result(
            escala,
            blocking=tuple(v for v in lote.introduced if v.mode is EnforcementMode.BLOCK),
            warnings=tuple(v for v in lote.introduced if v.mode is EnforcementMode.WARN),
        )

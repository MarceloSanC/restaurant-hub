"""Use case: publicar (= salvar) um lote de operações (ADR 4.1.0001; ADR 4.3.0001).

Mesmo protocolo do evaluate; depois: `block` introduzida ⇒ `BlockingViolationsError`;
senão `warn` introduzida sem aceite que a cubra ⇒ `UnacknowledgedViolationsError`;
senão grava **uma** vez — a escala final e a `ScheduleChange` (autor = sujeito do
escopo, instante do `Clock`, versão anterior, operações efetivas, aceites) — ou nada,
se nenhuma operação mudou a escala (§5.10).
"""

from restaurant_hub.features.scheduling.application.dtos.commands import PublishScheduleCommand
from restaurant_hub.features.scheduling.application.dtos.results import (
    ScheduleResult,
    to_schedule_result,
)
from restaurant_hub.features.scheduling.application.errors import (
    BlockingViolationsError,
    UnacknowledgedViolationsError,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    AccessGuard,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffReadPort,
)
from restaurant_hub.features.scheduling.application.use_cases._publish import (
    load_for_edit,
    run_batch,
    split_acknowledged,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
)
from restaurant_hub.shared.application.ports.out.clock import Clock


class PublishScheduleUseCase:
    """Publica o lote, recusando ou pedindo aceite só do que ele introduz."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        config: ScheduleConfigRepository,
        staff: StaffReadPort,
        clock: Clock,
        guard: AccessGuard,
    ) -> None:
        self._schedules = schedules
        self._config = config
        self._staff = staff
        self._clock = clock
        self._guard = guard

    def execute(self, command: PublishScheduleCommand) -> ScheduleResult:
        """Publica e devolve a escala vigente.

        Raises:
            BlockingViolationsError: o lote introduz violação `block`.
            UnacknowledgedViolationsError: o lote introduz `warn` sem aceite.
            ScheduleNotFoundError, ScheduleVersionConflictError, IdentifierInUseError,
            MissingStaffRecordsError, os erros por operação e os do domínio (crus).
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3); o escopo
        # é lido só pelo sujeito (autor da trilha).
        scope = self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_SCHEDULE,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        loaded = load_for_edit(
            self._schedules,
            (command.tenant_id, command.unit_id, command.schedule_id),
            command.expected_version,
        )
        batch = run_batch(self._schedules, self._config, self._staff, loaded, command.operations)
        blocking = tuple(v for v in batch.introduced if v.mode is EnforcementMode.BLOCK)
        if blocking:
            raise BlockingViolationsError(blocking)
        warnings = tuple(v for v in batch.introduced if v.mode is EnforcementMode.WARN)
        accepted, pending = split_acknowledged(warnings, command.acknowledgements)
        if pending:
            raise UnacknowledgedViolationsError(pending)
        if batch.effective:
            self._schedules.save(
                batch.after,
                loaded.version,
                ScheduleChange(
                    author_user_id=scope.user_id,
                    occurred_at=self._clock.now(),
                    previous_version=loaded.version,
                    operations=batch.effective,
                    acknowledged=accepted,
                ),
            )
        return to_schedule_result(
            batch.after, batch.view.members, batch.view.function_names, batch.after_violations
        )

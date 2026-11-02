"""Use case: criar a escala de uma unidade para um período (concept 4.3 §5.3).

O período tem 7 dias a partir de `first_day`, alinhado ao calendário **atual** do tenant
(o desalinhado é recusado pelo domínio, `InvalidSchedulePeriodError`); a escala nasce
vazia, na versão 1, com o calendário **fotografado** (ADR 4.1.0009). Dia já coberto por
outra escala da unidade ⇒ `SchedulePeriodTakenError` — aqui e na lei L-SC2 do port. O id
da escala é do servidor (`IdGenerator`, ADR 4.3.0004).
"""

from restaurant_hub.features.scheduling.application.dtos.commands import CreateScheduleCommand
from restaurant_hub.features.scheduling.application.dtos.results import (
    ScheduleSummaryResult,
    to_schedule_summary_result,
)
from restaurant_hub.features.scheduling.application.errors import SchedulePeriodTakenError
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
from restaurant_hub.features.scheduling.application.use_cases._inputs import (
    require_day,
    settings_of,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import ScheduleId
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CreateScheduleUseCase:
    """Cria a escala vazia do período."""

    def __init__(
        self,
        schedules: ScheduleRepository,
        config: ScheduleConfigRepository,
        ids: IdGenerator,
        clock: Clock,
        guard: AccessGuard,
    ) -> None:
        self._schedules = schedules
        self._config = config
        self._ids = ids
        self._clock = clock
        self._guard = guard

    def execute(self, command: CreateScheduleCommand) -> ScheduleSummaryResult:
        """Cria e grava a escala, com a mudança de criação na trilha.

        Raises:
            InvalidScheduleRequestError: `first_day` não é um `date`.
            InvalidSchedulePeriodError: `first_day` desalinhado do calendário (domínio).
            SchedulePeriodTakenError: dia do período já coberto na unidade.
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3); o escopo
        # é lido só pelo sujeito (autor da trilha).
        scope = self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_SCHEDULE,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        first_day = require_day(command.first_day, "first_day")
        settings = settings_of(self._config, command.tenant_id)
        period = settings.calendar.period_starting_on(first_day)
        if self._schedules.list_in_range(
            command.tenant_id, command.unit_id, period.first_day, period.last_day
        ):
            raise SchedulePeriodTakenError()
        schedule = Schedule(
            id=ScheduleId(str(self._ids.next_id())),
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
            period=period,
            calendar=settings.calendar,
        )
        self._schedules.add(
            schedule,
            ScheduleChange(
                author_user_id=scope.user_id,
                occurred_at=self._clock.now(),
                previous_version=None,
                operations=(),
                acknowledged=(),
            ),
        )
        return to_schedule_summary_result(schedule)

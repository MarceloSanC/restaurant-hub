"""Use case: as escalas anteriores a um dia, como referência (concept 4.3 §5.17, D-PAST).

As que terminam antes de `before`, da mais recente, até `limit` (1 a 52). Só resumos.
"""

from restaurant_hub.features.scheduling.application.dtos.queries import ListPastSchedulesQuery
from restaurant_hub.features.scheduling.application.dtos.results import (
    ScheduleSummaryResult,
    to_schedule_summary_result,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_VIEW_SCHEDULE,
    AccessGuard,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.use_cases._inputs import (
    require_day,
    require_limit,
)


class ListPastSchedulesUseCase:
    """Lista as escalas anteriores da unidade."""

    def __init__(self, schedules: ScheduleRepository, guard: AccessGuard) -> None:
        self._schedules = schedules
        self._guard = guard

    def execute(self, query: ListPastSchedulesQuery) -> tuple[ScheduleSummaryResult, ...]:
        """Os resumos, da mais recente.

        Raises:
            InvalidScheduleRequestError: `before` não é `date` ou `limit` fora de [1, 52].
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3).
        self._guard.authorize(
            query.actor,
            PERMISSION_VIEW_SCHEDULE,
            tenant_id=query.tenant_id,
            unit_id=query.unit_id,
        )
        prior = require_day(query.before, "before")
        limit = require_limit(query.limit)
        found = self._schedules.list_ending_before(query.tenant_id, query.unit_id, prior, limit)
        return tuple(to_schedule_summary_result(e) for e in found)

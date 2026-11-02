"""Use case: o calendário de um recorte de dias (concept 4.3 §5.16, D-CAL).

As escalas da unidade que cruzam o recorte e as faixas cujo dia operacional (pelo
calendário fotografado de cada escala) cai nele. Recorte de até 42 dias. Sem avaliação:
o calendário é para ver, não para editar. Alocação de inativo não aparece; alocado
ausente em qualquer escala do recorte recusa o recorte (§5.12).
"""

from restaurant_hub.features.scheduling.application.dtos.queries import GetCalendarQuery
from restaurant_hub.features.scheduling.application.dtos.results import (
    CalendarResult,
    to_calendar_result,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_VIEW_SCHEDULE,
    AccessGuard,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffReadPort,
)
from restaurant_hub.features.scheduling.application.use_cases._inputs import (
    load_staff,
    require_range,
)


class GetCalendarUseCase:
    """Lê as faixas do recorte através das escalas que ele cruza."""

    def __init__(
        self, schedules: ScheduleRepository, staff: StaffReadPort, guard: AccessGuard
    ) -> None:
        self._schedules = schedules
        self._staff = staff
        self._guard = guard

    def execute(self, query: GetCalendarQuery) -> CalendarResult:
        """O calendário.

        Raises:
            InvalidScheduleRequestError: dia que não é `date`, recorte invertido ou > 42 dias.
            MissingStaffRecordsError: registro alocado que staff não devolve.
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3).
        self._guard.authorize(
            query.actor,
            PERMISSION_VIEW_SCHEDULE,
            tenant_id=query.tenant_id,
            unit_id=query.unit_id,
        )
        primeiro, ultimo = require_range(query.first_day, query.last_day)
        escalas = self._schedules.list_in_range(query.tenant_id, query.unit_id, primeiro, ultimo)
        view = load_staff(self._staff, query.tenant_id, query.unit_id, escalas, with_roster=False)
        return to_calendar_result(primeiro, ultimo, escalas, view.members, view.function_names)

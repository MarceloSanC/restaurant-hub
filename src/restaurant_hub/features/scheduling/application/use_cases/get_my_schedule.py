"""Use case: "minha escala" — os turnos do próprio ator numa unidade (concept 4.3 §5.18).

O "eu" é o sujeito do escopo autorizado (`AuthorizedScope.user_id`, derivado do token —
ADR 0.0.0005; ADR 4.3.0002 §4), nunca um campo do pedido. Os registros são os da unidade
vinculados a esse login (`list_members_of_user`), **só os ativos**: registro desligado
não tem "minha escala". Recorte de até 42 dias. Várias unidades = a borda (4.5) consulta
por unidade (concept, divergência 10).
"""

from restaurant_hub.features.scheduling.application.dtos.queries import GetMyScheduleQuery
from restaurant_hub.features.scheduling.application.dtos.results import (
    MyScheduleResult,
    to_my_schedule_result,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_VIEW_OWN_SCHEDULE,
    AccessGuard,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffReadPort,
)
from restaurant_hub.features.scheduling.application.use_cases._inputs import require_range


class GetMyScheduleUseCase:
    """Lê os turnos dos registros ativos do próprio ator na unidade."""

    def __init__(
        self, schedules: ScheduleRepository, staff: StaffReadPort, guard: AccessGuard
    ) -> None:
        self._schedules = schedules
        self._staff = staff
        self._guard = guard

    def execute(self, query: GetMyScheduleQuery) -> MyScheduleResult:
        """Os turnos do ator no recorte.

        Raises:
            InvalidScheduleRequestError: dia que não é `date`, recorte invertido ou > 42 dias.
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3); o escopo
        # é lido só pelo sujeito — o "eu" de "minha escala".
        scope = self._guard.authorize(
            query.actor,
            PERMISSION_VIEW_OWN_SCHEDULE,
            tenant_id=query.tenant_id,
            unit_id=query.unit_id,
        )
        primeiro, ultimo = require_range(query.first_day, query.last_day)
        meus = {
            m.employee_id: m
            for m in self._staff.list_members_of_user(query.tenant_id, query.unit_id, scope.user_id)
            if m.active
        }
        if not meus:
            return to_my_schedule_result(primeiro, ultimo, (), frozenset(), {}, {})
        escalas = self._schedules.list_in_range(query.tenant_id, query.unit_id, primeiro, ultimo)
        nomes = {f.job_function_id: f.name for f in self._staff.list_job_functions(query.tenant_id)}
        return to_my_schedule_result(primeiro, ultimo, escalas, frozenset(meus), meus, nomes)

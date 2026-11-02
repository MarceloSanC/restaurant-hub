"""Use case: ler a escala vigente com as violações atuais (concept 4.3 §4).

A tela do editor e a leitura do RH (família "ler", ADR 4.1.0004). As violações são as
do estado atual — inclusive as induzidas por mudança em staff (D1) —, avaliadas com o
mesmo insumo do protocolo de publicação (lote vazio). Alocação de inativo não aparece;
registro alocado ausente recusa (`MissingStaffRecordsError`, §5.12).
"""

from restaurant_hub.features.scheduling.application.dtos.queries import GetScheduleQuery
from restaurant_hub.features.scheduling.application.dtos.results import (
    ScheduleResult,
    to_schedule_result,
)
from restaurant_hub.features.scheduling.application.errors import ScheduleNotFoundError
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_VIEW_SCHEDULE,
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
from restaurant_hub.features.scheduling.application.use_cases._publish import run_batch


class GetScheduleUseCase:
    """Lê a escala com faixas, alocações de ativos e violações atuais."""

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

    def execute(self, query: GetScheduleQuery) -> ScheduleResult:
        """A escala vigente.

        Raises:
            ScheduleNotFoundError: escala inexistente no endereço (tenant, unidade, escala).
            MissingStaffRecordsError: registro alocado que staff não devolve.
        """
        # (0) Autorização do alvo do command antes de tudo (ADR 4.3.0002 §3).
        self._guard.authorize(
            query.actor,
            PERMISSION_VIEW_SCHEDULE,
            tenant_id=query.tenant_id,
            unit_id=query.unit_id,
        )
        escala = self._schedules.find_by_id(query.tenant_id, query.unit_id, query.schedule_id)
        if escala is None:
            raise ScheduleNotFoundError(query.schedule_id)
        atual = run_batch(self._schedules, self._config, self._staff, escala, ())
        return to_schedule_result(
            atual.after, atual.view.members, atual.view.function_names, atual.after_violations
        )

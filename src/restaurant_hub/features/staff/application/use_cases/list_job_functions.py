"""Use case: listar as funções de trabalho do restaurante.

Não há filtro de estado porque **não há estado**: a função não tem ciclo de vida
(ADR 3.2.0005, L-JF5). A listagem é tenant-wide por construção — a função é do
restaurante, não da unidade (workforce §3.2).
"""

from restaurant_hub.features.staff.application.dtos.queries import ListJobFunctionsQuery
from restaurant_hub.features.staff.application.dtos.results import (
    JobFunctionResult,
    to_job_function_result,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)


class ListJobFunctionsUseCase:
    """Lista as funções do tenant."""

    def __init__(self, job_functions: JobFunctionRepository, guard: AccessGuard) -> None:
        self._job_functions = job_functions
        self._guard = guard

    def execute(self, query: ListJobFunctionsQuery) -> tuple[JobFunctionResult, ...]:
        """Devolve as funções do tenant — nenhuma de outro (concept §5.4)."""
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            query.actor, PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=query.tenant_id
        )
        return tuple(
            to_job_function_result(job_function)
            for job_function in self._job_functions.list_by_tenant(query.tenant_id)
        )

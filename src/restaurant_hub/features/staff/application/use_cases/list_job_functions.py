"""Use case: listar as funções de trabalho do restaurante.

Não há filtro de estado porque **não há estado**: a função não tem ciclo de vida
(ADR 3.2.0005, L-JF5).

**Duas listagens** desde a Stage 3.11 (ADR 3.11.0001 §6). Sem unidade, o catálogo
inteiro — a função é do restaurante (workforce §3.2), e cada item diz onde vale.
Com unidade, só as funções habilitadas nela (L-JF6); a unidade é alvo de
autorização, e é o passo de visibilidade de identity que recusa a unidade que o
ator não enxerga.
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
        """Devolve as funções do tenant — nenhuma de outro (concept §5.4).

        Com `query.unit_id`, só as habilitadas na unidade (L-JF6).
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2). Com unidade, ela
        # é o alvo — `unit_id=None` mantém a chamada idêntica à do catálogo.
        self._guard.authorize(
            query.actor,
            PERMISSION_MANAGE_JOB_FUNCTIONS,
            tenant_id=query.tenant_id,
            unit_id=query.unit_id,
        )
        job_functions = (
            self._job_functions.list_by_tenant(query.tenant_id)
            if query.unit_id is None
            else self._job_functions.list_by_unit(query.tenant_id, query.unit_id)
        )
        return tuple(to_job_function_result(job_function) for job_function in job_functions)

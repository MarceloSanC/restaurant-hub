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
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)


class ListJobFunctionsUseCase:
    """Lista as funções do tenant."""

    def __init__(self, job_functions: JobFunctionRepository) -> None:
        self._job_functions = job_functions

    def execute(self, query: ListJobFunctionsQuery) -> tuple[JobFunctionResult, ...]:
        """Devolve as funções do tenant — nenhuma de outro (concept §5.4)."""
        return tuple(
            to_job_function_result(job_function)
            for job_function in self._job_functions.list_by_tenant(query.tenant_id)
        )

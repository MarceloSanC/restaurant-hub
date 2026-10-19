"""Use case: listar os funcionários de uma unidade.

**Não existe listagem tenant-wide de funcionário**, e a ausência é o contrato
(L-E6; workforce §3.1): a unidade é obrigatória na query e na assinatura do
port, o que torna a consulta que vazaria unidades irrepresentável — não
"proibida por convenção".

Por default a lista esconde os desligados; `include_inactive=True` é opt-in
explícito. O desligado não sumiu do sistema: continua endereçável por id e
continua contando como referência para a guarda de remoção de função.
"""

from restaurant_hub.features.staff.application.dtos.queries import ListEmployeesQuery
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    to_employee_result,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_STAFF,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class ListEmployeesUseCase:
    """Lista os funcionários de uma unidade do restaurante."""

    def __init__(self, employees: EmployeeRepository, guard: AccessGuard) -> None:
        self._employees = employees
        self._guard = guard

    def execute(self, query: ListEmployeesQuery) -> tuple[EmployeeResult, ...]:
        """Devolve os registros da unidade pedida — nenhum de outra, nenhum de outro tenant."""
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            query.actor, PERMISSION_MANAGE_STAFF, tenant_id=query.tenant_id, unit_id=query.unit_id
        )
        return tuple(
            to_employee_result(employee)
            for employee in self._employees.list_by_unit(
                query.tenant_id, query.unit_id, include_inactive=query.include_inactive
            )
        )

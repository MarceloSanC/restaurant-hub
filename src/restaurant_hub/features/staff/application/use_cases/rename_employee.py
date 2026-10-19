"""Use case: renomear o registro de funcionário.

Ciclo **carregar → transicionar → gravar o agregado inteiro**: as entidades da
3.1 são `frozen`, então a transição devolve nova instância e não há mutação
in-place que a persistência pudesse observar.

Nome de funcionário **não é único** (homônimos são legítimos — concept 3.1
§5.2), por isso não há guarda de conflito aqui, ao contrário da função.
"""

from restaurant_hub.features.staff.application.dtos.commands import RenameEmployeeCommand
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    to_employee_result,
)
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_STAFF,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class RenameEmployeeUseCase:
    """Renomeia o registro de um funcionário."""

    def __init__(self, employees: EmployeeRepository, guard: AccessGuard) -> None:
        self._employees = employees
        self._guard = guard

    def execute(self, command: RenameEmployeeCommand) -> EmployeeResult:
        """Renomeia o registro.

        Raises:
            EmployeeNotFoundError: id inexistente **no endereço (tenant + unidade)** — registro de
                outro restaurante cai aqui (concept §5.4).
            InvalidNameError: nome vazio (domínio, 3.1) — não reembrulhado.
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_STAFF,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        renamed = employee.rename(command.name)
        self._employees.update(renamed)
        return to_employee_result(renamed)

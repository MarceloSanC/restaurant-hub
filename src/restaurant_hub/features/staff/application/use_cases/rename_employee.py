"""Use case: renomear o registro de funcionário.

Ciclo **carregar → transicionar → gravar o agregado inteiro**: as entidades da
3.1 são `frozen`, então a transição devolve nova instância e não há mutação
in-place que a persistência pudesse observar.

Nome de funcionário **não é único** (homônimos são legítimos — concept 3.1
§5.2), por isso não há guarda de conflito aqui, ao contrário da função.
"""

from restaurant_hub.features.staff.application.dtos.commands import RenameEmployeeCommand
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class RenameEmployeeUseCase:
    """Renomeia o registro de um funcionário."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: RenameEmployeeCommand) -> EmployeeResult:
        """Renomeia o registro.

        Raises:
            EmployeeNotFoundError: id inexistente **no tenant** — registro de
                outro restaurante cai aqui (concept §5.4).
            InvalidNameError: nome vazio (domínio, 3.1) — não reembrulhado.
        """
        employee = self._employees.find_by_id(command.tenant_id, command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        renamed = employee.rename(command.name)
        self._employees.update(renamed)
        return EmployeeResult(
            id=renamed.id,
            tenant_id=renamed.tenant_id,
            unit_id=renamed.unit_id,
            name=renamed.name,
            workload_profile=renamed.workload_profile,
            shift_preference=renamed.shift_preference,
            job_function_ids=renamed.job_function_ids,
            unavailabilities=renamed.unavailabilities,
            active=renamed.active,
        )

"""Use case: remover um período de indisponibilidade do funcionário.

A remoção é **por igualdade de valor**: o período não tem identidade própria,
então quem o remove reapresenta o valor exato. Período ausente do registro
levanta `UnavailabilityNotFoundError` — que é **422, não 404** (concept §4):
ele fala de um valor **dentro** do agregado, não de um recurso endereçável. O
recurso — o funcionário — existe e foi encontrado.
"""

from restaurant_hub.features.staff.application.dtos.commands import RemoveUnavailabilityCommand
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.use_cases._results import employee_result


class RemoveUnavailabilityUseCase:
    """Remove um período de indisponibilidade do registro."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: RemoveUnavailabilityCommand) -> EmployeeResult:
        """Remove o período.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)** (404).
            UnavailabilityNotFoundError: o registro não tem aquele período
                (domínio, 3.1) — **422**, não 404.
        """
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        updated = employee.remove_unavailability(command.period)
        self._employees.update(updated)
        return employee_result(updated)

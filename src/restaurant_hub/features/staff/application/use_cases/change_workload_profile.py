"""Use case: trocar o perfil de jornada do funcionário (fixa ↔ sob demanda).

O command já chega com o `WorkloadProfile` **construído**: uma carga semanal
inválida levanta `InvalidWeeklyHoursError` na borda (hoje o teste, na 3.4 o
adapter HTTP), **antes** deste use case — é o terceiro bloco da §6 do concept.
Não há, portanto, caminho daqui que produza aquele erro.
"""

from restaurant_hub.features.staff.application.dtos.commands import ChangeWorkloadProfileCommand
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.use_cases._results import employee_result


class ChangeWorkloadProfileUseCase:
    """Troca o perfil de jornada de um funcionário."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: ChangeWorkloadProfileCommand) -> EmployeeResult:
        """Troca o perfil.

        Raises:
            EmployeeNotFoundError: id inexistente **no endereço (tenant + unidade)**.
        """
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        changed = employee.change_workload_profile(command.workload_profile)
        self._employees.update(changed)
        return employee_result(changed)

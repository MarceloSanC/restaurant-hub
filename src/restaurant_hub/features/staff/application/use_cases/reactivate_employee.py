"""Use case: recontratar um funcionário desligado (ADR 3.2.0006).

Devolve o registro à listagem default da unidade, com toda a história que ele
manteve enquanto esteve desligado — funções, preferência e indisponibilidades
nunca foram apagadas.

**Idempotente no valor**: recontratar quem já está ativo não é erro.
"""

from restaurant_hub.features.staff.application.dtos.commands import ReactivateEmployeeCommand
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class ReactivateEmployeeUseCase:
    """Recontrata um funcionário desligado."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: ReactivateEmployeeCommand) -> EmployeeResult:
        """Reativa o registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no tenant**. O
                desligado **não** cai aqui: ele continua endereçável por id, que
                é justamente o que torna a recontratação possível.
        """
        employee = self._employees.find_by_id(command.tenant_id, command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        reactivated = employee.reactivate()
        self._employees.update(reactivated)
        return EmployeeResult(
            id=reactivated.id,
            tenant_id=reactivated.tenant_id,
            unit_id=reactivated.unit_id,
            name=reactivated.name,
            workload_profile=reactivated.workload_profile,
            shift_preference=reactivated.shift_preference,
            job_function_ids=reactivated.job_function_ids,
            unavailabilities=reactivated.unavailabilities,
            active=reactivated.active,
        )

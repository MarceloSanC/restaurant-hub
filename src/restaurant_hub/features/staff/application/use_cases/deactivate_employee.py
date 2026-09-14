"""Use case: desligar um funcionário (ADR 3.2.0006).

**Desligar não é apagar.** O registro sobrevive com toda a história: some da
listagem default da unidade (L-E6), continua endereçável por id e continua
contando como referência para a guarda de remoção das suas funções (L-JF3).

A transição é **idempotente no valor**: desligar quem já está desligado não é
erro. É a mesma forma que a 3.1 fixara para a função — e a que evita que a
borda precise consultar o estado antes de agir.

O desligamento **não é datado**: o campo é booleano, e nenhum `Clock` é
injetado (ADR 3.2.0006). Se o produto pedir "desde quando", é campo aditivo.
"""

from restaurant_hub.features.staff.application.dtos.commands import DeactivateEmployeeCommand
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    to_employee_result,
)
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class DeactivateEmployeeUseCase:
    """Desliga um funcionário, preservando o registro."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: DeactivateEmployeeCommand) -> EmployeeResult:
        """Desliga o registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
        """
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        deactivated = employee.deactivate()
        self._employees.update(deactivated)
        return to_employee_result(deactivated)

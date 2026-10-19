"""Use case: declarar — ou **limpar** — a preferência de turno do funcionário.

`shift_preference=None` significa "**limpe** a preferência", não "não mexa". É a
razão de o ADR 3.2.0004 ter escolhido use cases granulares em vez de um
`update_employee` com campos opcionais: num update parcial, `None` teria de
significar as duas coisas ao mesmo tempo, e "sem preferência declarada" é um
estado legítimo do domínio (ADR 3.1.0004), não a ausência de um pedido.
"""

from restaurant_hub.features.staff.application.dtos.commands import DeclareShiftPreferenceCommand
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


class DeclareShiftPreferenceUseCase:
    """Declara ou limpa a preferência de turno de um funcionário."""

    def __init__(self, employees: EmployeeRepository, guard: AccessGuard) -> None:
        self._employees = employees
        self._guard = guard

    def execute(self, command: DeclareShiftPreferenceCommand) -> EmployeeResult:
        """Grava a preferência — ou a remove, quando o command traz `None`.

        Raises:
            EmployeeNotFoundError: id inexistente **no endereço (tenant + unidade)**.
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
        declared = employee.declare_shift_preference(command.shift_preference)
        self._employees.update(declared)
        return to_employee_result(declared)

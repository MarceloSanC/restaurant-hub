"""Use case: registrar um período de indisponibilidade do funcionário.

A não-sobreposição é **consistência transacional do agregado** (workforce §3.6):
quem a impõe é o próprio `Employee`, na revalidação do `add_unavailability`. O
use case não a reimplementa nem reembrulha o erro (§5.15) — o
`OverlappingUnavailabilityError` sobe como está.

O `UnavailabilityPeriod` já chega **construído** no command: período malformado
(`start >= end`, tz-aware) falha na borda, antes deste use case.
"""

from restaurant_hub.features.staff.application.dtos.commands import (
    RegisterUnavailabilityCommand,
)
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


class RegisterUnavailabilityUseCase:
    """Acrescenta um período de indisponibilidade ao registro."""

    def __init__(self, employees: EmployeeRepository, guard: AccessGuard) -> None:
        self._employees = employees
        self._guard = guard

    def execute(self, command: RegisterUnavailabilityCommand) -> EmployeeResult:
        """Registra o período.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            OverlappingUnavailabilityError: o período se sobrepõe a outro já
                registrado (domínio, 3.1). Adjacente — fim == início — **não**
                é sobreposição (semântica semi-aberta, ADR 3.1.0001).
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
        updated = employee.add_unavailability(command.period)
        self._employees.update(updated)
        return to_employee_result(updated)

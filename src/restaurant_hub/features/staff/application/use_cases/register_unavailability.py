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
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class RegisterUnavailabilityUseCase:
    """Acrescenta um período de indisponibilidade ao registro."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: RegisterUnavailabilityCommand) -> EmployeeResult:
        """Registra o período.

        Raises:
            EmployeeNotFoundError: registro inexistente **no tenant**.
            OverlappingUnavailabilityError: o período se sobrepõe a outro já
                registrado (domínio, 3.1). Adjacente — fim == início — **não**
                é sobreposição (semântica semi-aberta, ADR 3.1.0001).
        """
        employee = self._employees.find_by_id(command.tenant_id, command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        updated = employee.add_unavailability(command.period)
        self._employees.update(updated)
        return EmployeeResult(
            id=updated.id,
            tenant_id=updated.tenant_id,
            unit_id=updated.unit_id,
            name=updated.name,
            workload_profile=updated.workload_profile,
            shift_preference=updated.shift_preference,
            job_function_ids=updated.job_function_ids,
            unavailabilities=updated.unavailabilities,
            active=updated.active,
        )

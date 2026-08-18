"""Use case: substituir o conjunto de funções de um funcionário.

O conjunto **substitui**, não acumula — o command traz o estado final desejado,
não um delta (ADR 3.1.0006: é um conjunto, sem ordem e sem histórico).

Reimpõe a validade referencial (§5.8) numa **edição**: a mesma regra do
`create_employee`, e pela mesma razão — uma função pode ter sido apagada entre a
criação do registro e esta atribuição.

**A ordem aqui é a inversa do `create_employee`**, e não por descuido: lá o
registro ainda não existe e a única falha possível é referencial; aqui o
registro é um recurso endereçável que pode não existir, e §5.4 manda o
`EmployeeNotFoundError` vir primeiro — do contrário a resposta a um id alheio
revelaria algo sobre o catálogo de funções do tenant.
"""

from restaurant_hub.features.staff.application.dtos.commands import AssignJobFunctionsCommand
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)


class AssignJobFunctionsUseCase:
    """Substitui o conjunto de funções de um funcionário."""

    def __init__(self, employees: EmployeeRepository, job_functions: JobFunctionRepository) -> None:
        self._employees = employees
        self._job_functions = job_functions

    def execute(self, command: AssignJobFunctionsCommand) -> EmployeeResult:
        """Substitui o conjunto.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            JobFunctionNotFoundError: alguma id do conjunto não existe no
                tenant (ou existe em outro).
            EmptyJobFunctionsError: conjunto vazio (domínio, 3.1).
        """
        # (1) Existência do registro — antes de qualquer coisa (§5.4).
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        # (2) Validade referencial do conjunto pedido.
        found = self._job_functions.find_all_by_ids(command.tenant_id, command.job_function_ids)
        missing = command.job_function_ids - {job_function.id for job_function in found}
        if missing:
            raise JobFunctionNotFoundError(sorted(missing)[0])
        # (3) Transição e (4) escrita.
        assigned = employee.assign_job_functions(command.job_function_ids)
        self._employees.update(assigned)
        return EmployeeResult(
            id=assigned.id,
            tenant_id=assigned.tenant_id,
            unit_id=assigned.unit_id,
            name=assigned.name,
            workload_profile=assigned.workload_profile,
            shift_preference=assigned.shift_preference,
            job_function_ids=assigned.job_function_ids,
            unavailabilities=assigned.unavailabilities,
            active=assigned.active,
        )

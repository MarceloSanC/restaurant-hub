"""Use case: criar o registro de funcionário numa unidade.

Impõe a terceira regra cross-agregado delegada pela 3.1 (concept §5.8): **toda**
id do conjunto de funções existe no tenant.

**O port é consultado antes de a entidade ser construída, e isso é decisão** — a
inversa de `create_job_function`, pela mesma regra ("a checagem mais barata que
possa falhar sozinha vem primeiro", §5.16). Aqui a entidade **não pode** ser
construída sem o conjunto resolvido: construir primeiro, para só depois
descobrir que uma função não existe, produziria `InvalidNameError` num pedido
cuja falha real é **referencial** — escondendo do gerente a causa que ele
precisa ler. Daí `JobFunctionNotFoundError` vencer o nome vazio, e não o
contrário.

O conjunto **vazio** não é caso especial: `find_all_by_ids(frozenset())` devolve
vazio, nada falta, e o `EmptyJobFunctionsError` do domínio sobe na construção,
sem reembrulho (§5.15).
"""

from restaurant_hub.features.staff.application.dtos.commands import CreateEmployeeCommand
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    to_employee_result,
)
from restaurant_hub.features.staff.application.errors import JobFunctionNotFoundError
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_STAFF,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import EmployeeId
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CreateEmployeeUseCase:
    """Cria o registro de um funcionário numa unidade do restaurante."""

    def __init__(
        self,
        employees: EmployeeRepository,
        job_functions: JobFunctionRepository,
        id_generator: IdGenerator,
        guard: AccessGuard,
    ) -> None:
        self._employees = employees
        self._job_functions = job_functions
        self._id_generator = id_generator
        self._guard = guard

    def execute(self, command: CreateEmployeeCommand) -> EmployeeResult:
        """Cria o registro, já ativo.

        Raises:
            JobFunctionNotFoundError: alguma id do conjunto não existe **no
                tenant** — id de outro restaurante cai aqui, porque a resolução
                é escopada (§5.4).
            EmptyJobFunctionsError: conjunto vazio (domínio, 3.1).
            InvalidNameError: nome vazio (domínio, 3.1).
            InvalidIdentifierError: tenant ou unidade vazios (domínio, 3.1).
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_STAFF,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        # (1) Resolução do conjunto — antes da construção, de propósito.
        found = self._job_functions.find_all_by_ids(command.tenant_id, command.job_function_ids)
        missing = command.job_function_ids - {job_function.id for job_function in found}
        if missing:
            # `sorted` para a id reportada ser determinística quando falta
            # mais de uma: mensagem de erro instável é ruído em log e em teste.
            raise JobFunctionNotFoundError(sorted(missing)[0])

        # (2) Construção — o registro nasce ativo (ADR 3.2.0006).
        employee = Employee(
            id=EmployeeId(str(self._id_generator.next_id())),
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
            name=command.name,
            workload_profile=command.workload_profile,
            shift_preference=command.shift_preference,
            job_function_ids=command.job_function_ids,
            active=True,
        )
        # (3) Escrita.
        self._employees.add(employee)
        return to_employee_result(employee)

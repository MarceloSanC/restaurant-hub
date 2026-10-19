"""Use case: remover definitivamente uma função de trabalho, com guarda.

Impõe a segunda regra cross-agregado delegada pela 3.1 (concept §5.9): a
remoção só acontece quando **nenhuma** referência existe. Apagar função
referenciada deixaria o cadastro do funcionário apontando para função
inexistente, corrompendo o dado e furando a invariante "ao menos uma função"
(ADR 3.1.0006).

A consulta de referência é **tenant-wide por construção** — a função é do
restaurante, não da unidade (workforce §3.2) — e conta registros **ativos e
inativos**: o desligado sobrevive com a história e ainda aponta para a função
(ADR 3.2.0006).

**Limite honesto:** aqui a guarda é *check-then-act*. Quem a fecha de verdade é
a FK `RESTRICT` da 3.3; nesta Stage o par de fakes a simula por construção —
fiel em comportamento, não em atomicidade (tabela ao final do concept §5).
"""

from restaurant_hub.features.staff.application.dtos.commands import DeleteJobFunctionCommand
from restaurant_hub.features.staff.application.errors import (
    JobFunctionInUseError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)


class DeleteJobFunctionUseCase:
    """Remove uma função de trabalho sem referências."""

    def __init__(
        self,
        job_functions: JobFunctionRepository,
        employees: EmployeeRepository,
        guard: AccessGuard,
    ) -> None:
        self._job_functions = job_functions
        self._employees = employees
        self._guard = guard

    def execute(self, command: DeleteJobFunctionCommand) -> None:
        """Remove a função.

        A ordem é o contrato (concept §5.16, errata de 2026-10-19): a
        **autorização** do alvo antes de tudo (ADR 3.7.0001), depois a
        **existência**. Apagar
        uma função do tenant A com `tenant_id` do B devolve
        `JobFunctionNotFoundError` mesmo quando ela está referenciada — o erro
        não pode confirmar que ela existe *nem* que está em uso (§5.4).

        Raises:
            JobFunctionNotFoundError: id inexistente **no tenant**.
            JobFunctionInUseError: algum funcionário do tenant — em **qualquer**
                unidade, **ativo ou inativo** — referencia a função.
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor, PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=command.tenant_id
        )
        # (1) Existência no tenant.
        if self._job_functions.find_by_id(command.tenant_id, command.job_function_id) is None:
            raise JobFunctionNotFoundError(command.job_function_id)
        # (2) Guarda de referências.
        if self._employees.exists_by_job_function(command.tenant_id, command.job_function_id):
            raise JobFunctionInUseError(command.job_function_id)
        # (3) Remoção.
        self._job_functions.delete(command.tenant_id, command.job_function_id)

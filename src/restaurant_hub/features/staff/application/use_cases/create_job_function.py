"""Use case: criar uma função de trabalho no restaurante.

**A entidade é construída antes de o port ser tocado, e isso é decisão** — a
regra por trás é "a checagem mais barata que possa falhar sozinha vem primeiro"
(concept §5.16). A validação do nome é local, não custa I/O e é a única
pré-condição: validar antes evita uma consulta inútil ao repositório para um
payload que já se sabe inválido.

**Tudo isso vale depois da autorização** (Stage 3.7, ADR 3.7.0001 §4): o alvo do
command é autorizado antes de qualquer outra instrução — antes até do gerador de
id e da validação local do nome —, porque quem é negado não aprende nada, nem a
forma do pedido. A regra "a checagem mais barata primeiro" ordena as checagens de
**negócio** entre si.

A assimetria com `create_employee` (que consulta o port **antes** de construir)
é deliberada e tem a mesma regra atrás: lá a entidade **não pode** ser
construída sem o conjunto de funções resolvido, e construir primeiro esconderia
uma falha referencial atrás de um `InvalidNameError`.

**O id sai do gerador e é descartado quando o payload é inválido.** É consequência
declarada da ordem, não desperdício acidental: a alternativa seria duplicar a
validação de nome nesta camada, violando §5.15 (erros de domínio não são
reembrulhados nem reimplementados).
"""

from restaurant_hub.features.staff.application.dtos.commands import CreateJobFunctionCommand
from restaurant_hub.features.staff.application.dtos.results import (
    JobFunctionResult,
    to_job_function_result,
)
from restaurant_hub.features.staff.application.errors import JobFunctionNameAlreadyExistsError
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import JobFunctionId
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CreateJobFunctionUseCase:
    """Cria uma função de trabalho, com nome único no tenant."""

    def __init__(
        self, job_functions: JobFunctionRepository, id_generator: IdGenerator, guard: AccessGuard
    ) -> None:
        self._job_functions = job_functions
        self._id_generator = id_generator
        self._guard = guard

    def execute(self, command: CreateJobFunctionCommand) -> JobFunctionResult:
        """Cria a função.

        Raises:
            InvalidNameError: nome vazio ou só-whitespace (domínio, 3.1) —
                levantado **sem tocar o repositório**.
            InvalidIdentifierError: tenant vazio (domínio, 3.1).
            JobFunctionNameAlreadyExistsError: nome já usado no tenant,
                comparado **verbatim** (sem trim, sem case-folding).
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor, PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=command.tenant_id
        )
        # (1) Construção: o domínio rejeita o nome vazio aqui, antes do port.
        job_function = JobFunction(
            id=JobFunctionId(str(self._id_generator.next_id())),
            tenant_id=command.tenant_id,
            name=command.name,
        )
        # (2) Unicidade de nome no tenant.
        if self._job_functions.find_by_name(command.tenant_id, command.name) is not None:
            raise JobFunctionNameAlreadyExistsError(command.name)
        # (3) Escrita.
        self._job_functions.add(job_function)
        return to_job_function_result(job_function)

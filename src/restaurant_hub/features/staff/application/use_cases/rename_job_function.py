"""Use case: renomear uma função de trabalho.

O conflito de nome **ignora a própria função**: renomear para o nome que ela já
tem não é conflito (concept §5.5). É exatamente por causa deste caso que o port
expõe `find_by_name` (devolve a entidade) e não um `exists_by_name` booleano —
com booleano, renomear uma função para o próprio nome falharia.
"""

from restaurant_hub.features.staff.application.dtos.commands import RenameJobFunctionCommand
from restaurant_hub.features.staff.application.dtos.results import (
    JobFunctionResult,
    to_job_function_result,
)
from restaurant_hub.features.staff.application.errors import (
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)


class RenameJobFunctionUseCase:
    """Renomeia uma função existente do tenant."""

    def __init__(self, job_functions: JobFunctionRepository, guard: AccessGuard) -> None:
        self._job_functions = job_functions
        self._guard = guard

    def execute(self, command: RenameJobFunctionCommand) -> JobFunctionResult:
        """Renomeia a função.

        A ordem é o contrato (concept §5.16, com as erratas de 2026-08-30 e de
        2026-10-19): a **autorização** do alvo antes de tudo (ADR 3.7.0001),
        depois a **existência**, depois a **validação local do nome**, e só então
        a sonda de unicidade. Renomear uma função inexistente para um nome já
        usado devolve `JobFunctionNotFoundError`, não o conflito — do contrário a
        resposta confirmaria que aquele nome existe no tenant a quem pediu por um
        id que não é dele.

        A transição vem **antes** de `find_by_name` pela regra que a nota de
        §5.16 enuncia: *a checagem mais barata que possa falhar sozinha vem
        primeiro*. Nome inválido é validação local, sem I/O, e nenhum nome
        inválido pode estar gravado (o domínio o recusa na construção **e** na
        reidratação — ADR 3.4.0003), logo `find_by_name` sobre ele nunca teria o
        que encontrar. A troca não altera qual erro vence em nenhum cenário
        construível; o que ela remove é a consulta inútil — e, com ela, o 500 que
        o nome cru produzia no psycopg (ADR 3.6.0004).

        Raises:
            JobFunctionNotFoundError: id inexistente **no tenant** (id de outro
                restaurante cai aqui — concept §5.4).
            InvalidNameError: nome novo vazio ou com byte NUL (domínio, 3.1) —
                não reembrulhado, e levantado **sem sondar unicidade**.
            JobFunctionNameAlreadyExistsError: nome já usado por **outra**
                função do tenant.
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor, PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=command.tenant_id
        )
        # (1) Existência no tenant.
        job_function = self._job_functions.find_by_id(command.tenant_id, command.job_function_id)
        if job_function is None:
            raise JobFunctionNotFoundError(command.job_function_id)
        # (2) Transição: o domínio rejeita o nome inválido aqui, antes do port.
        renamed = job_function.rename(command.name)
        # (3) Conflito de nome, ignorando a própria função.
        namesake = self._job_functions.find_by_name(command.tenant_id, command.name)
        if namesake is not None and namesake.id != job_function.id:
            raise JobFunctionNameAlreadyExistsError(command.name)
        # (4) Escrita.
        self._job_functions.update(renamed)
        return to_job_function_result(renamed)

"""Use case: renomear uma função de trabalho.

O conflito de nome **ignora a própria função**: renomear para o nome que ela já
tem não é conflito (concept §5.5). É exatamente por causa deste caso que o port
expõe `find_by_name` (devolve a entidade) e não um `exists_by_name` booleano —
com booleano, renomear uma função para o próprio nome falharia.
"""

from restaurant_hub.features.staff.application.dtos.commands import RenameJobFunctionCommand
from restaurant_hub.features.staff.application.dtos.results import JobFunctionResult
from restaurant_hub.features.staff.application.errors import (
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)


class RenameJobFunctionUseCase:
    """Renomeia uma função existente do tenant."""

    def __init__(self, job_functions: JobFunctionRepository) -> None:
        self._job_functions = job_functions

    def execute(self, command: RenameJobFunctionCommand) -> JobFunctionResult:
        """Renomeia a função.

        A ordem é o contrato (concept §5.16): **existência primeiro**. Renomear
        uma função inexistente para um nome já usado devolve
        `JobFunctionNotFoundError`, não o conflito — do contrário a resposta
        confirmaria que aquele nome existe no tenant a quem pediu por um id que
        não é dele.

        Raises:
            JobFunctionNotFoundError: id inexistente **no tenant** (id de outro
                restaurante cai aqui — concept §5.4).
            JobFunctionNameAlreadyExistsError: nome já usado por **outra**
                função do tenant.
            InvalidNameError: nome novo vazio (domínio, 3.1) — não reembrulhado.
        """
        # (1) Existência no tenant.
        job_function = self._job_functions.find_by_id(command.tenant_id, command.job_function_id)
        if job_function is None:
            raise JobFunctionNotFoundError(command.job_function_id)
        # (2) Conflito de nome, ignorando a própria função.
        homonima = self._job_functions.find_by_name(command.tenant_id, command.name)
        if homonima is not None and homonima.id != job_function.id:
            raise JobFunctionNameAlreadyExistsError(command.name)
        # (3) Transição do domínio e (4) escrita.
        renomeada = job_function.rename(command.name)
        self._job_functions.update(renomeada)
        return JobFunctionResult(
            id=renomeada.id,
            tenant_id=renomeada.tenant_id,
            name=renomeada.name,
        )

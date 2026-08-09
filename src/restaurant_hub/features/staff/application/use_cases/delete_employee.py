"""Use case: remover definitivamente o registro de um funcionário.

É o irmão duro de `deactivate_employee`, e existe para o **cadastro criado por
engano** (ADR 3.2.0006): aqui a história some. Quem saiu da equipe é
**desligado**, não apagado.

**A guarda de referências da L-E5 é do port, não deste use case — de propósito.**
O concept §5.16 lista "(2) guarda de referências" na precedência desta operação
porque descreve a **sequência observável**, mas quem a impõe é o `delete` do
repositório (no fake, por construção; na 3.3, pela FK `RESTRICT`) — exatamente
como acontece com L-JF3 do lado da função.

Escrever aqui um `if` que levantasse `EmployeeInUseError` criaria um ramo
**morto**: em v1 nada referencia o registro de funcionário. Com `branch = true`
na cobertura, o próximo a passar por aqui o "resolveria" com um
`# pragma: no cover` — que é como um ramo inalcançável vira dívida permanente.
O use case chama `delete` e deixa o erro do port subir; quando o Step 4 criar o
produtor, **este arquivo não muda**.
"""

from restaurant_hub.features.staff.application.dtos.commands import DeleteEmployeeCommand
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)


class DeleteEmployeeUseCase:
    """Remove definitivamente o registro de um funcionário."""

    def __init__(self, employees: EmployeeRepository) -> None:
        self._employees = employees

    def execute(self, command: DeleteEmployeeCommand) -> None:
        """Remove o registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no tenant**.
            EmployeeInUseError: levantado **pelo port** quando algum outro
                agregado referenciar o registro. Sem produtor em v1 (L-E5).
        """
        if self._employees.find_by_id(command.tenant_id, command.employee_id) is None:
            raise EmployeeNotFoundError(command.employee_id)
        self._employees.delete(command.tenant_id, command.employee_id)

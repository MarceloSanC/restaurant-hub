"""Use case: desligar um funcionário (ADR 3.2.0006).

**Desligar não é apagar.** O registro sobrevive com toda a história: some da
listagem default da unidade (L-E6), continua endereçável por id e continua
contando como referência para a guarda de remoção das suas funções (L-JF3).

A transição é **idempotente no valor**: desligar quem já está desligado não é
erro. É a mesma forma que a 3.1 fixara para a função — e a que evita que a
borda precise consultar o estado antes de agir.

O desligamento **não é datado**: o campo é booleano, e nenhum `Clock` é
injetado (ADR 3.2.0006). Se o produto pedir "desde quando", é campo aditivo.

**Desligar corta o acesso, agora** (Stage 3.5, ADR 3.5.0003 §1). Se o registro
tem login vinculado, as sessões vivas da conta são revogadas pelo
`IdentityGateway` **antes** de o desligamento ser gravado: a pessoa perde o
acesso no ato, não quando o access token expirar. A ordem é deliberada — se a
revogação falhar, o registro continua ativo e a operação falha inteira; o
inverso (gravar e depois revogar) deixaria um desligado com sessão viva quando
identity estivesse fora. A conta **continua existindo** e continua podendo logar
(ADR 3.5.0003 §2): o que ela deixa de alcançar é decidido pela autorização, e o
`user_id` permanece no registro — desligar não é desvincular. Registro sem login
não toca o gateway.
"""

from restaurant_hub.features.staff.application.dtos.commands import DeactivateEmployeeCommand
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
)
from restaurant_hub.features.staff.application.use_cases._results import employee_result


class DeactivateEmployeeUseCase:
    """Desliga um funcionário, preservando o registro e cortando as sessões do login."""

    def __init__(self, employees: EmployeeRepository, gateway: IdentityGateway) -> None:
        self._employees = employees
        self._gateway = gateway

    def execute(self, command: DeactivateEmployeeCommand) -> EmployeeResult:
        """Desliga o registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            Exception: a falha da revogação em identity sobe crua (L-IG2) — e o
                registro **não** é gravado como desligado.
        """
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        if employee.user_id is not None:
            # Antes de gravar — ver o docstring do módulo. Idempotente do lado de
            # identity (L-IG4), então desligar de novo não é erro aqui tampouco.
            self._gateway.revoke_login_sessions(employee.user_id)
        deactivated = employee.deactivate()
        self._employees.update(deactivated)
        return employee_result(deactivated)

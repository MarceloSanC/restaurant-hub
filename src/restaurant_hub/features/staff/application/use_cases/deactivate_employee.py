"""Use case: desligar um funcionário (ADR 3.2.0006).

**Desligar não é apagar.** O registro sobrevive com toda a história: some da
listagem default da unidade (L-E6), continua endereçável por id e continua
contando como referência para a guarda de remoção das suas funções (L-JF3).

A transição é **idempotente no valor**: desligar quem já está desligado não é
erro. É a mesma forma que a 3.1 fixara para a função — e a que evita que a
borda precise consultar o estado antes de agir.

O desligamento **não é datado**: o campo é booleano, e nenhum `Clock` é
injetado (ADR 3.2.0006). Se o produto pedir "desde quando", é campo aditivo.

**Desligar corta o acesso que o registro concede — e só esse** (Stage 3.5, ADR
3.5.0003; alcance fixado pela Stage 3.8, ADR 3.8.0001). Se o registro tem login
vinculado, as sessões vivas da conta são revogadas pelo `IdentityGateway`
**antes** de o desligamento ser gravado, quando as três condições valem:

1. **o registro está ativo** — desligar de novo um desligado não toca identity:
   a conta continua existindo e a pessoa pode ter logado depois do primeiro
   desligamento; um duplo clique não derruba essas sessões. A nova tentativa
   depois de uma falha continua segura: como a revogação vem antes da escrita,
   um registro cuja gravação falhou ainda está ativo;
2. **nenhum outro registro ativo da mesma unidade aponta para o login** — se
   houver, é ele quem ainda concede o acesso. Só a unidade: nenhuma operação de
   staff atravessa unidades implicitamente (workforce §3.1), e o sponsor aceitou
   o custo — a pessoa com registro em outra unidade loga de novo;
3. **o login é de funcionário** (L-IG5) — gerente ou dono vinculado a um
   registro de escala tira a autoridade do papel, não do registro; revogar não
   protegeria nada e só interromperia o trabalho dele.

A ordem é a da lista, e cada passo só roda se o anterior pedir: a consulta local
decide sem cruzar a fronteira. Tudo acontece **antes** de gravar — se qualquer
chamada falhar, o registro continua ativo e a operação falha inteira; o inverso
(gravar e depois revogar) deixaria um desligado com sessão viva quando identity
estivesse fora. A conta **continua existindo** e continua podendo logar (ADR
3.5.0003 §3): o que ela deixa de alcançar é decidido pela autorização, e o
`user_id` permanece no registro — desligar não é desvincular. Desligar **nunca**
desativa a conta (ADR 3.8.0001 §4). Registro sem login não toca o gateway.
"""

from restaurant_hub.features.staff.application.dtos.commands import DeactivateEmployeeCommand
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
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import UserId


class DeactivateEmployeeUseCase:
    """Desliga um funcionário, preservando o registro e cortando o acesso que ele concede."""

    def __init__(
        self, employees: EmployeeRepository, gateway: IdentityGateway, guard: AccessGuard
    ) -> None:
        self._employees = employees
        self._gateway = gateway
        self._guard = guard

    def execute(self, command: DeactivateEmployeeCommand) -> EmployeeResult:
        """Desliga o registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            Exception: a falha da listagem da unidade, da consulta de papel (L-IG5)
                ou da revogação (L-IG2) sobe crua — e o registro **não** é gravado
                como desligado.
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
        if (
            employee.active
            and employee.user_id is not None
            and self._grants_the_login_access(employee, employee.user_id)
        ):
            # Antes de gravar — ver o docstring do módulo. Idempotente do lado de
            # identity (L-IG4).
            self._gateway.revoke_login_sessions(employee.user_id)
        deactivated = employee.deactivate()
        self._employees.update(deactivated)
        return to_employee_result(deactivated)

    def _grants_the_login_access(self, employee: Employee, user_id: UserId) -> bool:
        """Condições 2 e 3 do docstring do módulo, nessa ordem (ADR 3.8.0001 §1 e §2).

        `list_by_unit` devolve só ativos (L-E6), então "outro registro ativo"
        é "outro registro da listagem". A consulta a identity só acontece se a
        unidade não decidiu.
        """
        shared = any(
            other.user_id == user_id and other.id != employee.id
            for other in self._employees.list_by_unit(employee.tenant_id, employee.unit_id)
        )
        if shared:
            return False
        return self._gateway.is_employee_login(user_id)

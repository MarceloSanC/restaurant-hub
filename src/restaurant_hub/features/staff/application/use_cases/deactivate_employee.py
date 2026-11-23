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
2. **nenhum outro registro ativo da mesma unidade aponta para o login** — vale
   por construção e não é lido: o índice único da unidade impede dois registros
   dela com o mesmo login (issue #241, ADR 0.0.0025 §4). Só a unidade: nenhuma
   operação de staff atravessa unidades implicitamente (workforce §3.1), e o
   sponsor aceitou o custo — a pessoa com registro em outra unidade loga de novo;
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

**A regra mora no ponto único** `_login_link.end_active_link` (Stage 3.10, ADR
3.10.0001 §5): é a mesma que trocar e desvincular o login aplicam, porque a regra é
de "o vínculo ativo de um registro termina" (ADR 3.8.0001 decisão 5).

**A gravação confere o estado lido** (L-DEACT, ADR 3.10.0001 §4). O desligamento
grava só `active`, pelo `deactivate` do repositório, condicionado ao `user_id` e ao
estado ativo que este use case leu. Um vínculo criado, trocado ou desfeito, ou uma
recontratação, entre a leitura e a escrita recusa com `EmployeeLoginChangedError`
(409) e nada é gravado: sem isso, um vínculo concorrente deixaria o registro
desligado **e** vinculado a um login que a regra nunca considerou (a ordem inversa
do ADR 0.0.0010). A revogação que já tiver acontecido fica — o lado seguro, como
numa falha de escrita. Outro desligamento concorrente do mesmo registro não recusa.
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
from restaurant_hub.features.staff.application.use_cases._login_link import end_active_link


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
            EmployeeLoginChangedError: o vínculo ou o estado gravado não é o lido
                (L-DEACT) — nada é gravado; a nova tentativa lê o estado atual.
            Exception: a falha da consulta de papel (L-IG5) ou da revogação (L-IG2)
                sobe crua — e o registro **não** é gravado como desligado.
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
        # Antes de gravar — ver o docstring do módulo.
        end_active_link(self._gateway, employee)
        self._employees.deactivate(
            command.tenant_id,
            command.unit_id,
            command.employee_id,
            expected_user_id=employee.user_id,
            expected_active=employee.active,
        )
        return to_employee_result(employee.deactivate())

"""Use case: criar o login de um funcionário (R17, Stage 3.5).

Liga um registro de funcionário a uma conta de acesso em identity, pelo port
`IdentityGateway`. É a única operação de staff que **cria** algo do outro lado
da fronteira, e a ordem em que o faz é contrato (concept 3.5 §5.4):

1. **Ler o registro** no endereço (tenant + unidade) — 404 se não existe *ali*,
   como em toda operação sobre registro existente (ADR 3.4.0007).
2. **As guardas do domínio antes de identity.** `assert_can_link_login`
   recusa registro já vinculado e registro desligado, nessa precedência, **antes**
   de qualquer chamada ao gateway: uma conta em identity não pode nascer para
   um vínculo que o domínio vai recusar — seria conta órfã, com e-mail ocupado e
   sem registro que a aponte.
3. **Provisionar** em identity: a conta pendente e o token, com o prazo do canal.
4. **Gravar o vínculo antes de entregar** o segredo (ADR 3.5.0002 §4). Se o envio
   do e-mail falhar depois disto, o registro já aponta para a conta — e o caminho
   de recuperação é o pedido público de redefinição de senha, não um segundo
   R17 (que responderia 409, porque o registro já está vinculado). A ordem
   inversa deixaria conta **e** vínculo perdidos numa falha de SMTP.
5. **Entregar pelo canal.** `EMAIL`: o gateway envia e o result **não** carrega o
   link. `LINK`: o link volta no result — o único caminho pelo qual o segredo
   sai de identity por API, e sai para quem acabou de provar `manage_staff` e
   `manage_users` sobre a unidade (concept §5.3).

**Antes de tudo, autoriza — duas vezes** (Stage 3.7, ADR 3.7.0001): `manage_staff`
e depois `manage_users` sobre a unidade do command, as duas antes do passo 1, para
que uma negação na segunda não deixe leitura nem conta para trás. A rota autoriza
as mesmas duas antes de chegar aqui; esta é a linha que vale para qualquer driver.

O que este use case **não** faz: não escolhe o papel (é do port, L-IG1); não loga,
não formata nem repete o link em mensagem nenhuma (L-IG3) — e nenhuma exceção o
carrega (CA05).
"""

from restaurant_hub.features.staff.application.dtos.commands import (
    CreateLoginForEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeLoginResult,
    to_employee_login_result,
)
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_STAFF,
    PERMISSION_MANAGE_USERS,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
    LoginDelivery,
)


class CreateLoginForEmployeeUseCase:
    """Cria a conta pendente em identity e a vincula ao registro do funcionário."""

    def __init__(
        self, employees: EmployeeRepository, gateway: IdentityGateway, guard: AccessGuard
    ) -> None:
        self._employees = employees
        self._gateway = gateway
        self._guard = guard

    def execute(self, command: CreateLoginForEmployeeCommand) -> EmployeeLoginResult:
        """Vincula um login novo ao registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            EmployeeAlreadyHasLoginError: o registro já tem login (precede a próxima).
            TerminatedEmployeeLoginError: o registro está desligado.
            LoginEmailAlreadyInUseError: o e-mail já é login de alguém (do gateway, L-IG2).
            InvalidLoginEmailError: identity recusou o e-mail (do gateway, L-IG2).
            Exception: qualquer outra falha de identity sobe crua — inclusive a do
                envio, que acontece **depois** de o vínculo estar gravado.
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_STAFF,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_USERS,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        employee = self._employees.find_by_id(
            command.tenant_id, command.unit_id, command.employee_id
        )
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        employee.assert_can_link_login()

        provisioned = self._gateway.provision_employee_login(
            email=command.email,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
            delivery=command.delivery,
        )
        linked = employee.link_login(provisioned.user_id)
        self._employees.update(linked)

        if command.delivery is LoginDelivery.EMAIL:
            self._gateway.send_login_invitation(
                email=command.email, setup_link=provisioned.setup_link
            )
            # O link **não** volta no result: quem o recebe é a caixa de entrada.
            return to_employee_login_result(linked, setup_link=None)
        return to_employee_login_result(linked, setup_link=provisioned.setup_link)

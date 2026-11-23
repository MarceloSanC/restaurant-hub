"""Use case: vincular a um registro uma conta que já existe no restaurante (R18, Stage 3.10).

O caso imediato é o gerente ou dono que também trabalha na escala: ele já tem
conta, e R17 — que sempre cria conta nova — responde 409. Também é o caminho de
recuperação da conta órfã de uma falha de staff depois do provisionamento (concept
3.5 §6.4). A conta é nomeada pelo **e-mail** (ADR 3.10.0002 §1).

Ordem (concept 3.10 §5 R7), cada passo só se o anterior passou:

1. **Autoriza duas vezes** — `manage_staff` e depois `manage_users` sobre a unidade
   do command, antes de qualquer leitura (ADR 3.7.0001; o mesmo par de R17, ADR
   3.10.0002 §5). O ator pode vincular a própria conta.
2. **Lê o registro** no endereço de três partes — 404 se não existe ali.
3. **Guardas locais antes de identity** — `assert_can_link_login`: já vinculado ⇒
   409, depois desligado ⇒ 409 (concept 3.5 §5.5). Desligado não recebe login, nem
   conta existente.
4. **Resolve a conta** — `resolve_linkable_login`: existe, é do restaurante do
   registro e alcança a unidade dele, senão o mesmo 404 para todos os casos; e não
   está em outro registro da unidade, senão 409.
5. **Grava pelo `link_login`** (L-LINK, ADR 0.0.0010) — a escrita condicional que
   recusa um vínculo concorrente gravado depois da leitura.

Vincular **não encerra** vínculo nenhum, então não passa pela regra de fim de
vínculo e não toca as sessões da conta. Não cria membership e não muda o papel da
conta (ADR 3.10.0002 §4).
"""

from restaurant_hub.features.staff.application.dtos.commands import LinkExistingLoginCommand
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    to_employee_result,
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
)
from restaurant_hub.features.staff.application.use_cases._login_link import (
    resolve_linkable_login,
)


class LinkExistingLoginUseCase:
    """Vincula ao registro sem login uma conta existente do restaurante."""

    def __init__(
        self, employees: EmployeeRepository, gateway: IdentityGateway, guard: AccessGuard
    ) -> None:
        self._employees = employees
        self._gateway = gateway
        self._guard = guard

    def execute(self, command: LinkExistingLoginCommand) -> EmployeeResult:
        """Vincula a conta do e-mail ao registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            EmployeeAlreadyHasLoginError: o registro já tem login (precede a próxima)
                — também quando um vínculo concorrente foi gravado depois da leitura.
            TerminatedEmployeeLoginError: o registro está desligado.
            LoginAccountNotFoundError: nenhuma conta elegível com o e-mail.
            LoginAlreadyLinkedInUnitError: a conta já está em outro registro da unidade.
            InvalidLoginEmailError: e-mail malformado (do gateway, L-IG6).
            Exception: qualquer outra falha de identity sobe crua.
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
        user_id = resolve_linkable_login(self._employees, self._gateway, command.email, employee)
        self._employees.link_login(command.tenant_id, command.unit_id, command.employee_id, user_id)
        return to_employee_result(employee.link_login(user_id))

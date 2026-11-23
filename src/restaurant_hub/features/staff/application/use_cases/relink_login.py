"""Use case: trocar o login vinculado a um registro (R19, Stage 3.10).

Substitui o login do registro por **outra conta que já existe** no restaurante,
numa escrita só (ADR 3.10.0001 §1). O caso típico é o e-mail digitado errado em
R17: o registro ficou vinculado à conta errada, e a pessoa certa já tem conta.
Desvincular e vincular em duas chamadas deixaria o registro sem login quando a
segunda falhasse; aqui a conta nova é conferida **antes** de o vínculo antigo
terminar.

Ordem (concept 3.10 §5 R7):

1. **Autoriza duas vezes** — `manage_staff` e depois `manage_users` sobre a unidade
   do command, antes de qualquer leitura (ADR 3.10.0002 §5).
2. **Lê o registro** no endereço de três partes — 404 se não existe ali.
3. **Guardas locais antes de identity** — sem login ⇒ `EmployeeHasNoLoginError`,
   depois desligado ⇒ `TerminatedEmployeeLoginError` (desligado não recebe login).
4. **Resolve a conta nova** (`resolve_linkable_login`). Se é o login atual, devolve
   o registro **sem escrever nem revogar**: o vínculo não termina.
5. **Aplica a regra de fim de vínculo ao login antigo** pelo ponto único
   (`end_active_link`), com o registro lido, antes de gravar (ADR 3.5.0003 §2).
6. **Grava pelo `relink_login`** (L-RELINK) com o login lido como esperado.
"""

from restaurant_hub.features.staff.application.dtos.commands import RelinkLoginCommand
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
    end_active_link,
    resolve_linkable_login,
)


class RelinkLoginUseCase:
    """Troca o login vinculado ao registro por outra conta existente do restaurante."""

    def __init__(
        self, employees: EmployeeRepository, gateway: IdentityGateway, guard: AccessGuard
    ) -> None:
        self._employees = employees
        self._gateway = gateway
        self._guard = guard

    def execute(self, command: RelinkLoginCommand) -> EmployeeResult:
        """Troca o login do registro pela conta do e-mail.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            EmployeeHasNoLoginError: o registro não tem login (precede a próxima).
            TerminatedEmployeeLoginError: o registro está desligado.
            LoginAccountNotFoundError: nenhuma conta elegível com o e-mail.
            LoginAlreadyLinkedInUnitError: a conta já está em outro registro da unidade.
            InvalidLoginEmailError: e-mail malformado (do gateway, L-IG6).
            EmployeeLoginChangedError: o login gravado não é o lido (L-RELINK).
            Exception: qualquer outra falha de identity sobe crua — nada é gravado.
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
        current = employee.assert_can_relink_login()
        user_id = resolve_linkable_login(self._employees, self._gateway, command.email, employee)
        if user_id == current:
            return to_employee_result(employee)
        # Antes de gravar — ver o docstring do módulo.
        end_active_link(self._gateway, employee)
        self._employees.relink_login(
            command.tenant_id,
            command.unit_id,
            command.employee_id,
            expected_user_id=current,
            user_id=user_id,
        )
        return to_employee_result(employee.relink_login(current, user_id))

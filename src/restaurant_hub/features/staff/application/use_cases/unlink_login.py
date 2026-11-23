"""Use case: desvincular o login de um registro (R20, Stage 3.10).

É o caminho para corrigir um vínculo feito por engano — inclusive para remover
(R15) um registro que recebeu login errado, já que R15 recusa o vinculado (ADR
0.0.0013) — e o encerramento explícito do vínculo de quem deixou de usar a conta
nesse registro.

Ordem (concept 3.10 §5 R7):

1. **Autoriza duas vezes** — `manage_staff` e depois `manage_users` sobre a unidade
   do command, antes de qualquer leitura (ADR 3.10.0002 §5).
2. **Lê o registro** no endereço de três partes — 404 se não existe ali.
3. **Registro sem login** ⇒ `EmployeeHasNoLoginError` (409).
4. **Aplica a regra de fim de vínculo** pelo ponto único (`end_active_link`, ADR
   3.10.0001 §5), com o registro lido, **antes** de gravar (ADR 3.5.0003 §2): o
   registro ativo, único da unidade com o login, de login de funcionário, corta as
   sessões. Registro desligado desvincula sem tocar identity.
5. **Grava pelo `unlink_login`** (L-UNLINK) com o login e o estado lidos: um vínculo
   ou estado que mudou entre a leitura e a escrita recusa com 409 e nada é gravado.

A conta continua existindo em identity (desativar conta é non-goal, ADR 3.8.0001
§4).
"""

from restaurant_hub.features.staff.application.dtos.commands import UnlinkLoginCommand
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
from restaurant_hub.features.staff.application.use_cases._login_link import end_active_link
from restaurant_hub.features.staff.domain.exceptions.errors import EmployeeHasNoLoginError


class UnlinkLoginUseCase:
    """Retira o vínculo de login do registro, cortando o acesso que ele concedia."""

    def __init__(
        self, employees: EmployeeRepository, gateway: IdentityGateway, guard: AccessGuard
    ) -> None:
        self._employees = employees
        self._gateway = gateway
        self._guard = guard

    def execute(self, command: UnlinkLoginCommand) -> EmployeeResult:
        """Desvincula o login do registro.

        Raises:
            EmployeeNotFoundError: registro inexistente **no endereço (tenant + unidade)**.
            EmployeeHasNoLoginError: o registro não tem login — também quando foi
                desvinculado entre a leitura e a escrita.
            EmployeeLoginChangedError: o login ou o estado gravado não é o lido.
            Exception: a falha da listagem, da consulta de papel ou da revogação sobe
                crua — e nada é gravado.
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
        if employee.user_id is None:
            raise EmployeeHasNoLoginError(employee.id)
        # Antes de gravar — ver o docstring do módulo.
        end_active_link(self._employees, self._gateway, employee)
        self._employees.unlink_login(
            command.tenant_id,
            command.unit_id,
            command.employee_id,
            expected_user_id=employee.user_id,
            expected_active=employee.active,
        )
        return to_employee_result(
            employee.unlink_login(employee.user_id, was_active=employee.active)
        )

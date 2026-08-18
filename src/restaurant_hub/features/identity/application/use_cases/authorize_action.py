"""Use case: autorizar uma ação — o guard de acesso do BC identity.

Compõe os dois eixos ortogonais que a Stage 2.1 modelou, **sem colapsá-los**:
RBAC ("o que o papel pode fazer") e visibilidade de unidade ("o que o usuário
enxerga"), mais a checagem de escopo de tenant que o domínio não expressa
sozinho. Cada checagem tem a sua própria exceção — é isso que torna a
ortogonalidade observável em teste: não dá para fundir duas delas sem quebrar a
suíte (ADR 2.2.0002).

**A ordem dos passos é contrato** (concept §5.6). Quem falha em mais de uma
checagem recebe o erro da mais alta, e há teste dedicado fixando isso — do
contrário uma reordenação silenciosa passaria batida.

**Duas checagens são exigências, não filtros.** Um teste que só roda quando o
chamador se lembra de passar o parâmetro não é regra imposta: omitir vira o
caminho de escalada. Por isso quem pertence a um tenant **precisa** declarar o
tenant alvo, e quem não faz bypass de unidade **precisa** declarar a unidade
alvo. Negar por ausência é o que mantém o guard fail-closed.

**A única dispensa é por permissão.** Uma permissão cujo alvo é o restaurante e
não a unidade — as de `TENANT_WIDE_PERMISSIONS` — não tem unidade a nomear, e
exigi-la tornaria o recurso inalcançável para papel unit-scoped. A dispensa
remove uma *exigência de nomear unidade*; não remove nenhuma checagem: os passos
3 e 5 seguem intactos (ADR 3.4.0008 §2 e §4).

Nada de `can_view_unit` é reimplementado aqui: a regra de bypass e o casamento
`user_id`+`unit_id` vivem no domínio, e duplicá-los criaria duas fontes de
verdade capazes de divergir.
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
from restaurant_hub.features.identity.application.errors import (
    PermissionDeniedError,
    TenantNotVisibleError,
    TenantScopeRequiredError,
    UnitNotFoundError,
    UnitNotVisibleError,
    UnitScopeRequiredError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.identifiers import UnitId
from restaurant_hub.features.identity.domain.value_objects.permission import (
    TENANT_WIDE_PERMISSIONS,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role


class AuthorizeActionUseCase:
    """Decide se um ator pode executar uma ação sobre um escopo."""

    def __init__(self, users: UserRepository, units: UnitRepository) -> None:
        self._users = users
        self._units = units

    def execute(self, command: AuthorizeActionCommand) -> AuthorizedActor:
        """Autoriza a ação ou levanta o erro da primeira checagem que falhar.

        Raises:
            UserNotFoundError: ator inexistente.
            PermissionDeniedError: papel não concede a permissão (eixo RBAC).
            TenantScopeRequiredError: ator de tenant não declarou o tenant alvo.
            TenantNotVisibleError: tenant alvo não é o do ator, ou o par
                `tenant_id`/`unit_id` é incoerente.
            UnitScopeRequiredError: ator escopado por unidade não declarou a
                unidade, e a permissão exercida não é tenant-wide.
            UnitNotFoundError: unidade alvo inexistente.
            UnitNotVisibleError: ator não enxerga a unidade (eixo visibilidade).
        """
        # 1. Ator
        user = self._users.find_by_id(command.actor_id)
        if user is None:
            raise UserNotFoundError(command.actor_id)

        # 2. Eixo RBAC
        if not user.has_permission(command.permission):
            raise PermissionDeniedError(user.role.value, command.permission.value)

        # 3. Escopo de tenant (pulado para platform_admin, que não tem tenant)
        self._assert_tenant_scope(user, command)

        # 4. Exigência de escopo de unidade, dispensada para permissão tenant-wide.
        # A dispensa é **por permissão, nunca por papel**: pôr `manager`/`hr` em
        # `_UNIT_SCOPE_BYPASS_ROLES` lhes daria alcance tenant-wide sobre TODAS as
        # permissões que detêm — inclusive `MANAGE_STAFF`, ou seja, todo registro
        # de funcionário do restaurante. Assim o raio de explosão de um engano fica
        # em uma capacidade, não em um ator (ADR 3.4.0008 §3).
        if (
            command.unit_id is None
            and not user.bypasses_unit_scope()
            and command.permission not in TENANT_WIDE_PERMISSIONS
        ):
            raise UnitScopeRequiredError(user.role.value)

        # 5. Eixo visibilidade
        if command.unit_id is not None:
            self._assert_unit_visibility(user, command, command.unit_id)

        return AuthorizedActor(
            user_id=user.id,
            role=user.role,
            actor_tenant_id=user.tenant_id,
            scope_tenant_id=command.tenant_id,
            scope_unit_id=command.unit_id,
        )

    def _assert_tenant_scope(self, user: User, command: AuthorizeActionCommand) -> None:
        """Passo 3 — o ator só age dentro do próprio tenant.

        Existe porque o domínio só compara tenants **dentro** de `can_view_unit`,
        isto é, apenas quando há unidade alvo. Sem este passo, uma ação
        tenant-wide não teria nenhuma barreira de tenant.
        """
        if user.role is Role.PLATFORM_ADMIN:
            return
        if command.tenant_id is None:
            raise TenantScopeRequiredError(user.role.value)
        if command.tenant_id != user.tenant_id:
            raise TenantNotVisibleError(user.tenant_id, command.tenant_id)

    def _assert_unit_visibility(
        self,
        user: User,
        command: AuthorizeActionCommand,
        unit_id: UnitId,
    ) -> None:
        """Passo 5 — resolve a unidade e delega a visibilidade ao domínio.

        `unit_id` vem como parâmetro já estreitado pelo chamador: aceitar
        `UnitId | None` aqui exigiria um `return` inalcançável só para o
        type-checker, e código morto num guard de segurança é ruído que esconde.
        """
        unit = self._units.find_by_id(unit_id)
        if unit is None:
            raise UnitNotFoundError(unit_id)

        # Coerência do par alvo: vale inclusive para platform_admin, que pulou o
        # passo 3 — declarar o tenant B e mirar unidade do tenant C é incoerente.
        if command.tenant_id is not None and unit.tenant_id != command.tenant_id:
            raise TenantNotVisibleError(user.tenant_id, unit.tenant_id)

        # Sem filtrar o resultado: o domínio casa user_id E unit_id, então um
        # repositório permissivo não concede visibilidade indevida.
        if not user.can_view_unit(unit, self._users.list_memberships(user.id)):
            raise UnitNotVisibleError(user.id, unit.id)

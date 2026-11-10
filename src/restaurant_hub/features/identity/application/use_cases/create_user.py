"""Use case: criar uma conta de acesso, com credencial e vínculos de unidade.

**Autoriza antes de qualquer outra instrução** (Stage 2.7, ADR 0.0.0020 §Decision
3): o ator do command precisa de "não se concede o que não se detém" —
`required_permissions_for_role(command.role)` —, no tenant do command e em **cada**
unidade pedida. Como nenhum papel detém `manage_users` e `manage_platform`, nenhuma
chamada direta cria um `platform_admin`; e um `owner` de outro tenant é negado no
passo de tenant. A borda HTTP continua autorizando o mesmo requisito antes.

**A ordem das checagens que vem depois é contrato** (concept 2.2 §5.7), não detalhe
de implementação. Duas delas em especial:

- A unicidade de e-mail vem primeiro porque é a única checagem global; deixá-la
  para depois faria o caller receber "restaurante não encontrado" quando o
  problema real é que o e-mail já existe em outro tenant.
- A rejeição de `platform_admin` com `unit_ids` vem antes da resolução das unidades
  **por este use case**. Se as resolvêssemos primeiro, um `platform_admin`
  receberia `UnitNotFoundError` para unidade inexistente e
  `PlatformAdminMembershipError` para unidade existente — a diferença revelaria
  quais unidades existem. Desde a Stage 2.7 nenhum ator real chega a este ramo (o
  requisito de criar `platform_admin` não é de papel nenhum), e a autorização já
  passou pelas unidades pedidas, com unidade inexistente traduzida para
  `UnitNotVisibleError`. O ramo fica como defesa em profundidade (concept 2.7 D6).

O hash é gerado por último: se qualquer validação falhar, não se paga o custo do
KDF à toa.
"""

from collections.abc import Sequence

from restaurant_hub.features.identity.application.dtos.commands import CreateUserCommand
from restaurant_hub.features.identity.application.dtos.results import UserResult, to_user_result
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantNotFoundError,
    UnitNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.action_authorizer import (
    ActionAuthorizer,
    required_permissions_for_role,
)
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    authorize_requirement,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    PlatformAdminMembershipError,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CreateUserUseCase:
    """Cria um usuário, o seu hash de senha e os seus vínculos de unidade."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        users: UserRepository,
        restaurants: RestaurantRepository,
        units: UnitRepository,
        hasher: PasswordHasher,
        id_generator: IdGenerator,
        authorizer: ActionAuthorizer,
    ) -> None:
        self._users = users
        self._restaurants = restaurants
        self._units = units
        self._hasher = hasher
        self._id_generator = id_generator
        self._authorizer = authorizer

    def execute(self, command: CreateUserCommand) -> UserResult:
        """Cria o usuário.

        Raises:
            InvalidAccessTokenError, PermissionDeniedError, TenantScopeRequiredError,
                TenantNotVisibleError, UnitScopeRequiredError, UnitNotVisibleError:
                o ator não detém o requisito (ADR 2.7.0001 §Decision 3).
            EmailAlreadyRegisteredError: e-mail já usado em qualquer tenant.
            PlatformAdminMembershipError: `platform_admin` com `unit_ids`.
            RestaurantNotFoundError: tenant informado não existe.
            UnitNotFoundError: alguma unidade informada não existe.
            CrossTenantError: unidade pertence a outro tenant.
            MissingTenantError / PlatformAdminTenantError: invariantes de tenancy.
        """
        authorize_requirement(
            self._authorizer,
            command.actor_id,
            required_permissions_for_role(command.role),
            tenant_id=command.tenant_id,
            unit_ids=command.unit_ids,
        )

        if self._users.exists_by_email(command.email):
            raise EmailAlreadyRegisteredError(command.email.value)

        is_platform_admin = command.role is Role.PLATFORM_ADMIN
        if is_platform_admin and command.unit_ids:
            # Antes de tocar no UnitRepository — ver docstring do módulo.
            raise PlatformAdminMembershipError()

        tenant_id = command.tenant_id
        if (
            not is_platform_admin
            and tenant_id is not None
            and self._restaurants.find_by_id(tenant_id) is None
        ):
            raise RestaurantNotFoundError(tenant_id)

        # `tenant_id` ausente para papel de restaurante é invariante do domínio:
        # o próprio construtor levanta `MissingTenantError`.
        user = User(
            id=UserId(str(self._id_generator.next_id())),
            email=command.email,
            role=command.role,
            tenant_id=command.tenant_id,
        )

        memberships = self._link_units(user, command.unit_ids)
        password_hash = self._hasher.hash(command.plain_password)
        self._users.add(user, password_hash, memberships)

        return to_user_result(user, memberships)

    def _link_units(
        self,
        user: User,
        unit_ids: Sequence[UnitId],
    ) -> tuple[UnitMembership, ...]:
        """Resolve e vincula as unidades, deduplicando ids repetidos.

        Vínculo é relação, não multiconjunto: `unit_ids` repetido geraria dois
        `UnitMembership` idênticos e, na 2.3, conflito de chave primária.
        `dict.fromkeys` deduplica **preservando a ordem** — `set` não preserva, e
        a ordem dos vínculos é observável no result.

        O isolamento de tenant não é reimplementado aqui: `User.link_to_unit`
        já levanta `CrossTenantError`, e duplicar a regra criaria duas fontes de
        verdade que podem divergir.
        """
        memberships: list[UnitMembership] = []
        for unit_id in dict.fromkeys(unit_ids):
            unit = self._units.find_by_id(unit_id)
            if unit is None:
                raise UnitNotFoundError(unit_id)
            memberships.append(user.link_to_unit(unit))
        return tuple(memberships)

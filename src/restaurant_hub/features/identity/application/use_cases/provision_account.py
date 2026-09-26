"""Use case: provisionar uma conta pendente e devolver o link de definição de senha.

É `InviteUserUseCase` **sem o envio** e **com o link no result**. A separação
existe para o consumidor que não é a rota de convite: o gateway de staff
(Stage 3.5, R17) cria a conta do funcionário e decide, pelo canal escolhido pelo
gestor, se o link vai por e-mail (`SendInvitationUseCase`) ou volta na resposta
para ser entregue em mãos — impresso, QR, mensagem. Quem provisiona não sabe qual
dos dois vai acontecer; por isso não envia.

**Carve-out declarado da regra 1 da Stage 2.5** ("o valor do token existe entre a
emissão e o corpo do e-mail, e em nenhum outro lugar"): este é o **único** use
case de identity cujo result carrega o segredo, e a decisão está no ADR 3.5.0002
§Status. O `repr=False` em `ProvisionedAccountResult.setup_link` é a metade
mecânica da contenção; a outra metade é do consumidor — o gateway de staff só
expõe o link no canal `link`, e nenhuma exceção o carrega.

**O TTL depende do canal.** Um link entregue em mãos não chega em minutos, como
um e-mail: o gestor imprime hoje e a pessoa começa segunda. Por isso o command
carrega `handed_over` e o use case escolhe entre `invitation_ttl` (o das 72h da
2.5) e `handover_ttl` (o de `Settings.handover_link_ttl_hours`). Não há
reemissão nesta Stage — link perdido é recuperado pelo pedido público de
redefinição de senha, como qualquer convite (ADR 3.5.0002).

**A ordem das checagens é a de `InviteUserUseCase`, verbatim**, e pelas mesmas
razões (unicidade global primeiro; rejeição de `platform_admin` com unidades
antes de tocar no `UnitRepository`, senão a diferença entre `UnitNotFoundError`
e `PlatformAdminMembershipError` revelaria quais unidades existem). `_link_units`
é a terceira cópia da mesma mecânica — declarada no concept 3.5 §10; extrair
agora acoplaria três fluxos que ainda podem divergir.
"""

from collections.abc import Sequence
from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionAccountCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.results import (
    ProvisionedAccountResult,
    to_user_result,
)
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantNotFoundError,
    UnitNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)
from restaurant_hub.features.identity.application.ports.out.password_setup_token_repository import (
    PasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.application.ports.out.setup_token_issuer import (
    SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.application.use_cases._invitation import setup_link
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
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class ProvisionAccountUseCase:
    """Cria a conta sem senha utilizável, emite o token e devolve o link."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        users: UserRepository,
        restaurants: RestaurantRepository,
        units: UnitRepository,
        hasher: PasswordHasher,
        tokens: PasswordSetupTokenRepository,
        token_issuer: SetupTokenIssuer,
        id_generator: IdGenerator,
        clock: Clock,
        invitation_ttl: timedelta,
        handover_ttl: timedelta,
        base_url: str,
    ) -> None:
        self._users = users
        self._restaurants = restaurants
        self._units = units
        self._hasher = hasher
        self._tokens = tokens
        self._token_issuer = token_issuer
        self._id_generator = id_generator
        self._clock = clock
        self._invitation_ttl = invitation_ttl
        self._handover_ttl = handover_ttl
        self._base_url = base_url

    def execute(self, command: ProvisionAccountCommand) -> ProvisionedAccountResult:
        """Provisiona a conta pendente.

        Raises:
            EmailAlreadyRegisteredError: e-mail já usado em qualquer tenant.
            PlatformAdminMembershipError: `platform_admin` com `unit_ids`.
            RestaurantNotFoundError: tenant informado não existe.
            UnitNotFoundError: alguma unidade informada não existe.
            CrossTenantError: unidade pertence a outro tenant.
        """
        if self._users.exists_by_email(command.email):
            raise EmailAlreadyRegisteredError(command.email.value)

        is_platform_admin = command.role is Role.PLATFORM_ADMIN
        if is_platform_admin and command.unit_ids:
            # Antes de tocar no `UnitRepository` — ver `create_user`.
            raise PlatformAdminMembershipError()

        tenant_id = command.tenant_id
        if (
            not is_platform_admin
            and tenant_id is not None
            and self._restaurants.find_by_id(tenant_id) is None
        ):
            raise RestaurantNotFoundError(tenant_id)

        user = User(
            id=UserId(str(self._id_generator.next_id())),
            email=command.email,
            role=command.role,
            tenant_id=command.tenant_id,
        )
        memberships = self._link_units(user, command.unit_ids)

        # O hash inutilizável, e não `dummy_hash()` — ADR 2.5.0004. O dummy é
        # derivado de um literal deste repositório; gravá-lo aqui faria a senha
        # dessa string abrir a conta da pessoa.
        self._users.add(user, self._hasher.unusable_hash(), memberships)

        valor_do_token = self._emitir_token(user.id, handed_over=command.handed_over)

        return ProvisionedAccountResult(
            # Pelo mapper único de `UserResult` (regra 8 do `check_layout`, issue
            # #45): o result da conta provisionada é o **mesmo** que o convite
            # devolve, e um campo novo em `UserResult` aparece aqui sem edição.
            user=to_user_result(user, memberships),
            setup_link=setup_link(self._base_url, valor_do_token),
        )

    def _link_units(
        self,
        user: User,
        unit_ids: Sequence[UnitId],
    ) -> tuple[UnitMembership, ...]:
        """Resolve e vincula as unidades, deduplicando ids repetidos.

        `dict.fromkeys` deduplica **preservando a ordem** — `set` não preserva, e
        a ordem dos vínculos é observável no result. O isolamento de tenant não é
        reimplementado: `User.link_to_unit` já levanta `CrossTenantError`.
        """
        memberships: list[UnitMembership] = []
        for unit_id in dict.fromkeys(unit_ids):
            unit = self._units.find_by_id(unit_id)
            if unit is None:
                raise UnitNotFoundError(unit_id)
            memberships.append(user.link_to_unit(unit))
        return tuple(memberships)

    def _emitir_token(self, user_id: UserId, *, handed_over: bool) -> str:
        """Emite e persiste o token, devolvendo **só** o valor a colocar no link.

        O prazo é a única coisa que o canal muda: um link em mãos vive
        `handover_ttl`; um que vai por e-mail, `invitation_ttl`. O propósito é o
        mesmo `INVITATION` — quem redime não distingue o canal, nem precisa.
        """
        agora = self._clock.now()
        prazo = self._handover_ttl if handed_over else self._invitation_ttl
        emitido = self._token_issuer.issue()
        self._tokens.add(
            PasswordSetupToken(
                id=SetupTokenId(str(self._id_generator.next_id())),
                user_id=user_id,
                purpose=SetupTokenPurpose.INVITATION,
                token_fingerprint=emitido.fingerprint,
                issued_at=agora,
                expires_at=agora + prazo,
            )
        )
        return emitido.value

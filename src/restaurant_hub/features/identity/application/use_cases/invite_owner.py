"""Use case: convidar o `owner` de um restaurante existente — ação de **plataforma**.

É a entrada própria do convite de dono pela plataforma (`POST /restaurants/{id}/owners`),
que o ADR 0.0.0020 §Inventory exigiu e o ADR 2.7.0001 §Decision 4 escolheu. Até a Stage
2.7 a rota rodava `InviteUserUseCase` com o papel literal e o tenant do path. Só que um
use case que declara o próprio requisito não escolhe entre dois — o composto do convite
de tenant e o `manage_platform` deste — sem ler o papel do ator, que é a regra de acesso
vazando de `AuthorizeActionUseCase`. Então são dois use cases, cada um com o seu.

**Autoriza antes de qualquer outra instrução** (ADR 0.0.0020 §Decision 3): exige
`manage_platform`, com o tenant do command **nomeado**. Para `platform_admin` o passo de
tenant não se aplica, e qualquer outro papel é negado antes, no RBAC — a mesma resposta
que a borda dá, que autoriza sem nomear o tenant.

**O papel é o literal `Role.OWNER`, aqui** — não vem do command. Com ele, "nenhum
caminho emite `platform_admin`" vale para este use case qualquer que seja o adapter
que o chame (ADR 2.4.0003 §2b; ADR 0.0.0018 §Decision 3).

Depois da autorização, a sequência é a que `InviteUserUseCase` percorria para esta
rota (`role=OWNER`, sem unidades), e um teste de paridade a trava: unicidade global do
e-mail antes de qualquer outra consulta; o restaurante do path existe (senão 404);
conta e token numa unidade de trabalho (ADR 2.6.0001); o e-mail depois do commit, com a
falha trocada por `InvitationNotSentError` em `_invitation.deliver_invitation` (issue
#170). As escritas são chamadas diretas aos repositórios, à vista da regra 10 do
`check_layout`.
"""

from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import InviteOwnerCommand
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.results import UserResult, to_user_result
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.action_authorizer import (
    ActionAuthorizer,
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
from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.application.use_cases._invitation import (
    deliver_invitation,
    invitation_message,
    setup_link,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    authorize_requirement,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.email_sender import EmailSender
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class InviteOwnerUseCase:
    """Cria o `owner` pendente de um restaurante existente e envia o convite."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        users: UserRepository,
        restaurants: RestaurantRepository,
        hasher: PasswordHasher,
        tokens: PasswordSetupTokenRepository,
        token_issuer: SetupTokenIssuer,
        email_sender: EmailSender,
        id_generator: IdGenerator,
        clock: Clock,
        invitation_ttl: timedelta,
        base_url: str,
        unit_of_work: UnitOfWork,
        authorizer: ActionAuthorizer,
    ) -> None:
        self._users = users
        self._restaurants = restaurants
        self._hasher = hasher
        self._tokens = tokens
        self._token_issuer = token_issuer
        self._email_sender = email_sender
        self._id_generator = id_generator
        self._clock = clock
        self._invitation_ttl = invitation_ttl
        self._base_url = base_url
        self._unit_of_work = unit_of_work
        self._authorizer = authorizer

    def execute(self, command: InviteOwnerCommand) -> UserResult:
        """Convida o dono.

        Raises:
            InvalidAccessTokenError, PermissionDeniedError: o ator não pode agir
                como plataforma (ADR 2.7.0001 §Decision 3).
            EmailAlreadyRegisteredError: e-mail já usado em qualquer tenant.
            RestaurantNotFoundError: o restaurante do command não existe.
            InvitationNotSentError: o `EmailSender` falhou, com a conta e o token
                já comitados (regra 13 da 2.5; issue #170).
        """
        authorize_requirement(
            self._authorizer,
            command.actor_id,
            frozenset({Permission.MANAGE_PLATFORM}),
            tenant_id=command.tenant_id,
        )

        if self._users.exists_by_email(command.email):
            raise EmailAlreadyRegisteredError(command.email.value)

        if self._restaurants.find_by_id(command.tenant_id) is None:
            raise RestaurantNotFoundError(command.tenant_id)

        owner = User(
            id=UserId(str(self._id_generator.next_id())),
            email=command.email,
            role=Role.OWNER,
            tenant_id=command.tenant_id,
        )

        # O hash inutilizável, e não `dummy_hash()` — ADR 2.5.0004.
        with self._unit_of_work.transaction():
            self._users.add(owner, self._hasher.unusable_hash(), ())
            token_value = self._issue_token(owner.id)

        # Depois do commit (ADR 2.6.0002 §3).
        deliver_invitation(
            self._email_sender,
            invitation_message(command.email.value, setup_link(self._base_url, token_value)),
            owner.id,
        )

        return to_user_result(owner, ())

    def _issue_token(self, user_id: UserId) -> str:
        """Emite e persiste o token de convite, devolvendo **só** o valor a enviar.

        Quinta cópia do passo (com `InviteUserUseCase`, `ProvisionRestaurantUseCase`,
        `ProvisionAccountUseCase` e `RequestPasswordResetUseCase`), declarada no ADR
        2.7.0001 §Consequences — extraí-la sem esconder a escrita da regra 10 é
        `[finding]` da Stage 2.7.
        """
        now = self._clock.now()
        issued = self._token_issuer.issue()
        self._tokens.add(
            PasswordSetupToken(
                id=SetupTokenId(str(self._id_generator.next_id())),
                user_id=user_id,
                purpose=SetupTokenPurpose.INVITATION,
                token_fingerprint=issued.fingerprint,
                issued_at=now,
                expires_at=now + self._invitation_ttl,
            )
        )
        return issued.value

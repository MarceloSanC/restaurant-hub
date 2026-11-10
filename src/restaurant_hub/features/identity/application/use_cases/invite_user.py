"""Use case: convidar alguém, criando a conta sem senha e mandando o link.

É o irmão de `CreateUserUseCase` com uma diferença que muda tudo: **ninguém
escolhe a senha da pessoa convidada**. A conta nasce com um hash inutilizável e
a pessoa define a própria senha pelo link que recebe — de modo que quem convidou
jamais conhece, transporta ou digita a credencial de outra pessoa.

**Autoriza antes de qualquer outra instrução, o mesmo requisito de
`CreateUserUseCase`** (Stage 2.7, ADR 0.0.0020 §Decision 3): convidar concede o mesmo
acesso que criar. O convite do dono pela plataforma tem use case próprio,
`InviteOwnerUseCase` (ADR 2.7.0001 §Decision 4) — este serve só o convite de tenant.

**A ordem das checagens que vem depois é a mesma de `CreateUserUseCase`, e pelas
mesmas razões** (unicidade global primeiro; rejeição de `platform_admin` com
unidades antes de este use case resolver as unidades — defesa em profundidade desde
a 2.7, ver `create_user`). Duplicar a
mecânica é deliberado nesta Stage: extrair um passo compartilhado agora acoplaria
dois fluxos que ainda podem divergir — o convite não tem senha, e a criação
direta não tem token nem e-mail.

**Conta e token são uma unidade de trabalho** (Stage 2.6, ADR 2.6.0001): se o
`tokens.add` falha, o `users.add` é desfeito — nunca nasce conta sem link que a
abra (o `[finding]` de atomicidade escalado pela 3.5).

**A falha do `EmailSender` propaga** (concept §5 regra 13), trocada por
`InvitationNotSentError` em `_invitation.deliver_invitation` — que registra só o
tipo da falha e o `user_id`, porque a mensagem de um provedor pode ecoar o
destinatário e o link (issue #170). Reportar sucesso sem
que o e-mail tenha saído deixaria uma conta inacessível e um administrador
convencido de que convidou. O envio vem **depois** de a unidade comitar (ADR
2.6.0002 §3) — um rollback não desenvia e-mail, e um e-mail enviado de dentro de
uma unidade que depois desfizesse levaria um link para token inexistente. Então a
conta fica criada, e o caminho de recuperação é o **pedido público de redefinição
de senha**, não reconvidar: reconvidar responde 409, porque o e-mail já existe.

**Não invalida tokens anteriores**, e a ausência é correta: um usuário recém
criado não tem token anterior, e um segundo convite ao mesmo e-mail nunca chega
aqui (a checagem de unicidade o barra antes).
"""

from collections.abc import Sequence
from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import InviteUserCommand
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.results import UserResult, to_user_result
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
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
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
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
from restaurant_hub.shared.application.ports.out.email_sender import EmailSender
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class InviteUserUseCase:
    """Cria uma conta sem senha utilizável e envia o link de definição."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        users: UserRepository,
        restaurants: RestaurantRepository,
        units: UnitRepository,
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
        self._units = units
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

    def execute(self, command: InviteUserCommand) -> UserResult:
        """Convida a pessoa.

        Raises:
            InvalidAccessTokenError, PermissionDeniedError, TenantScopeRequiredError,
                TenantNotVisibleError, UnitScopeRequiredError, UnitNotVisibleError:
                o ator não detém o requisito (ADR 2.7.0001 §Decision 3).
            EmailAlreadyRegisteredError: e-mail já usado em qualquer tenant.
            PlatformAdminMembershipError: `platform_admin` com `unit_ids`.
            RestaurantNotFoundError: tenant informado não existe.
            UnitNotFoundError: alguma unidade informada não existe.
            CrossTenantError: unidade pertence a outro tenant.
            InvitationNotSentError: o `EmailSender` falhou, com a conta e o token
                já comitados (regra 13; issue #170).
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
            # Antes de este use case resolver as unidades — ver `create_user`.
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
        # dessa string abrir a conta da pessoa convidada.
        with self._unit_of_work.transaction():
            self._users.add(user, self._hasher.unusable_hash(), memberships)
            token_value = self._issue_token(user.id)

        # Depois do commit — ver o docstring do módulo (ADR 2.6.0002 §3).
        self._send_invitation_email(user.id, command.email.value, token_value)

        return to_user_result(user, memberships)

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

    def _issue_token(self, user_id: UserId) -> str:
        """Emite e persiste o token, devolvendo **só** o valor a enviar.

        O valor não entra em nenhum campo do result, de nenhum DTO persistido, de
        nenhuma mensagem de erro: ele existe entre esta linha e o corpo do
        e-mail, e em nenhum outro lugar (concept §5 regra 1).
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

    def _send_invitation_email(self, user_id: UserId, recipient: str, token_value: str) -> None:
        """Compõe e envia a mensagem.

        Desde a Stage 3.5 a composição vive em `_invitation.py`, a única casa do
        formato do link e do texto do convite — a mesma mensagem que o
        `SendInvitationUseCase` manda quando quem provisiona é o gateway de staff.
        Assunto, corpo e link são byte-idênticos aos da 2.5 (CA16 da 3.5). Desde a
        issue #170 o envio também passa por lá, em `deliver_invitation`.
        """
        deliver_invitation(
            self._email_sender,
            invitation_message(recipient, setup_link(self._base_url, token_value)),
            user_id,
        )

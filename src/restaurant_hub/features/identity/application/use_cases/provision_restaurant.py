"""Use case: provisionar um tenant — o restaurante e o seu primeiro `owner`, por convite.

**Restaurante e dono são uma unidade de trabalho** (ADR 0.0.0014, sobre o port
do ADR 2.6.0001). Antes, o provisionamento eram duas chamadas — criar o
restaurante (`CreateRestaurantUseCase`, removido na issue #67), depois criar o
dono —, e uma falha entre elas deixava um restaurante que ninguém opera: o
`platform_admin` só detém `manage_platform` e não age dentro do tenant. Aqui,
se o `users.add` ou o `tokens.add` falha (inclusive pelo índice único de
e-mail, numa corrida com outro cadastro), o `restaurants.add` é desfeito.

**O dono é convidado, não recebe senha** (ADR 0.0.0018, issue #114). A conta
nasce com o hash inutilizável e um token de convite, e o dono define a própria
senha pelo link que recebe por e-mail — a plataforma nunca escolhe, conhece ou
transporta a credencial do dono do tenant. É o mesmo mecanismo de
`InviteUserUseCase`: mesmo propósito de token, mesmo prazo, mesma mensagem.

**As escritas são chamadas diretas aos repositórios**, e não ao `execute` de
outros use cases (`InviteUserUseCase`): a regra 10 do `check_layout` enxerga
escrita por atributo de repositório, e escrita alcançada pelo `execute` de outro
use case é ponto cego declarado dela (ADR 2.6.0002 §5; ADR 0.0.0014
Alternativa F).

**O e-mail sai depois do commit, e a falha dele propaga** (ADR 2.6.0002 §3;
regra 13 da 2.5). Um rollback não desenvia e-mail, e um e-mail enviado de
dentro de uma unidade que depois desfizesse levaria um link para token
inexistente. Se o envio falha, restaurante, dono e token ficam comitados, e o
caminho de recuperação é o pedido público de redefinição de senha — repetir o
provisionamento responde 409, porque o e-mail do dono já existe. A falha sobe
como `InvitationNotSentError`, trocada em `_invitation.deliver_invitation`, que
registra só o tipo dela e o `user_id` do dono (issue #170).

**O papel é o literal `Role.OWNER`, aqui** — não vem do command. Com ele, "nenhum
caminho emite `platform_admin`" vale para este use case qualquer que seja o
adapter que o chame (ADR 0.0.0014 §3; ADR 2.4.0003 §2b).

**A autorização fica na borda**, como em todo use case de identity (ADR 2.4.0003
§1): este use case não recebe ator. O ADR 3.7.0001 trouxe a autorização para
dentro dos use cases de **staff**, não de identity (ADR 0.0.0014 §4).

Ordem: o nome (invariante do domínio, local e grátis) primeiro; depois a
unicidade global do e-mail, antes de qualquer escrita; as três escritas numa
unidade; o envio por último.
"""

from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.results import (
    ProvisionedRestaurantResult,
    to_user_result,
)
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import EmailAlreadyRegisteredError
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
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.email_sender import EmailSender
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class ProvisionRestaurantUseCase:
    """Cria o restaurante e o seu `owner` pendente, tudo ou nada, e convida o dono."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        restaurants: RestaurantRepository,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: PasswordSetupTokenRepository,
        token_issuer: SetupTokenIssuer,
        email_sender: EmailSender,
        id_generator: IdGenerator,
        clock: Clock,
        invitation_ttl: timedelta,
        base_url: str,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._restaurants = restaurants
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        self._token_issuer = token_issuer
        self._email_sender = email_sender
        self._id_generator = id_generator
        self._clock = clock
        self._invitation_ttl = invitation_ttl
        self._base_url = base_url
        self._unit_of_work = unit_of_work

    def execute(self, command: ProvisionRestaurantCommand) -> ProvisionedRestaurantResult:
        """Provisiona o tenant e convida o dono.

        Raises:
            InvalidNameError: nome do restaurante vazio (invariante do domínio).
            EmailAlreadyRegisteredError: e-mail do dono já usado em qualquer tenant —
                pela checagem prévia ou, numa corrida, pelo índice único dentro da
                unidade (e então o restaurante é desfeito).
            InvitationNotSentError: o `EmailSender` falhou, com o tenant já
                comitado (regra 13 da 2.5; issue #170).
        """
        restaurant = Restaurant(
            id=RestaurantId(str(self._id_generator.next_id())),
            name=command.name,
        )

        if self._users.exists_by_email(command.owner_email):
            raise EmailAlreadyRegisteredError(command.owner_email.value)

        owner = User(
            id=UserId(str(self._id_generator.next_id())),
            email=command.owner_email,
            role=Role.OWNER,
            tenant_id=restaurant.id,
        )

        # O hash inutilizável, e não `dummy_hash()` — ADR 2.5.0004: o dummy é
        # derivado de um literal do repositório e viraria senha válida do dono.
        with self._unit_of_work.transaction():
            self._restaurants.add(restaurant)
            self._users.add(owner, self._hasher.unusable_hash(), ())
            token_value = self._issue_token(owner.id)

        # Depois do commit — ver o docstring do módulo (ADR 2.6.0002 §3).
        deliver_invitation(
            self._email_sender,
            invitation_message(command.owner_email.value, setup_link(self._base_url, token_value)),
            owner.id,
        )

        return ProvisionedRestaurantResult(
            id=restaurant.id,
            name=restaurant.name,
            owner=to_user_result(owner, ()),
        )

    def _issue_token(self, user_id: UserId) -> str:
        """Emite e persiste o token de convite, devolvendo **só** o valor a enviar.

        O valor não entra no result, em DTO persistido nem em mensagem de erro:
        existe entre esta linha e o corpo do e-mail (regra 1 da 2.5). Quarta cópia
        do passo (com `InviteUserUseCase`, `ProvisionAccountUseCase` e
        `RequestPasswordResetUseCase`), declarada no ADR 0.0.0018.
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

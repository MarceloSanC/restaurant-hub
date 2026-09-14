"""Use case: autenticar por e-mail e senha, emitindo o par de tokens.

Duas propriedades de segurança governam o desenho deste fluxo:

**1. E-mail inexistente e senha errada precisam ser indistinguíveis.** Não basta
levantar a mesma exceção: se o caminho "e-mail não existe" retornasse sem chamar
o hasher, ele responderia em microssegundos enquanto o caminho "senha errada"
pagaria o custo do argon2 — e essa diferença de tempo, medida de fora, enumera as
contas cadastradas. Por isso o e-mail inexistente verifica contra
`hasher.dummy_hash()`: descarta-se o resultado, paga-se o mesmo custo.

**2. O valor do refresh token nunca é persistido.** A sessão guarda apenas o
fingerprint; o valor só existe no result devolvido ao cliente. Um dump do banco,
portanto, não devolve nenhum refresh token utilizável (ADR 2.2.0001).

Nenhuma sessão é criada em caminho de falha.
"""

from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthenticateUserCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.results import (
    AuthenticationResult,
    to_authentication_result,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import InvalidCredentialsError
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class AuthenticateUserUseCase:
    """Verifica credenciais e abre uma sessão de refresh."""

    # PLR0913 (muitos argumentos) existe para pegar função que faz coisas demais.
    # Aqui o construtor é a **costura de injeção de dependência**: são quatro
    # ports, dois colaboradores compartilhados e a configuração de TTL, todos
    # montados uma vez pelo composition root (2.4). Reduzir a contagem exigiria
    # agrupá-los num objeto-parâmetro artificial, escondendo o grafo de
    # dependências que o hexagonal quer justamente deixar explícito.
    def __init__(  # noqa: PLR0913
        self,
        users: UserRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        token_issuer: TokenIssuer,
        id_generator: IdGenerator,
        clock: Clock,
        access_token_ttl: timedelta,
        refresh_token_ttl: timedelta,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._hasher = hasher
        self._token_issuer = token_issuer
        self._id_generator = id_generator
        self._clock = clock
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl

    def execute(self, command: AuthenticateUserCommand) -> AuthenticationResult:
        """Autentica e abre a sessão.

        Raises:
            InvalidCredentialsError: e-mail inexistente **ou** senha incorreta —
                deliberadamente a mesma exceção, com a mesma mensagem.
        """
        credentials = self._users.find_credentials_by_email(command.email)

        if credentials is None:
            # Verificação descartada, feita só para igualar o tempo de resposta
            # ao do caminho de senha errada — ver docstring do módulo.
            self._hasher.verify(command.plain_password, self._hasher.dummy_hash())
            raise InvalidCredentialsError()

        if not self._hasher.verify(command.plain_password, credentials.password_hash):
            raise InvalidCredentialsError()

        user = credentials.user
        now = self._clock.now()
        session_id = SessionId(str(self._id_generator.next_id()))
        access_token_expires_at = now + self._access_token_ttl
        refresh_token_expires_at = now + self._refresh_token_ttl

        issued_refresh = self._token_issuer.issue_refresh_token()
        access_token = self._token_issuer.issue_access_token(
            AccessTokenClaims(
                subject=user.id,
                role=user.role,
                tenant_id=user.tenant_id,
                session_id=session_id,
                expires_at=access_token_expires_at,
            )
        )

        self._sessions.add(
            Session(
                id=session_id,
                user_id=user.id,
                refresh_token_fingerprint=issued_refresh.fingerprint,
                issued_at=now,
                expires_at=refresh_token_expires_at,
            )
        )

        return to_authentication_result(
            access_token=access_token,
            issued_refresh=issued_refresh,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            user_id=user.id,
        )

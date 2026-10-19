"""Use case: rotacionar um refresh token, detectando reuso.

É o consumidor que dá sentido ao desenho do ADR 2.2.0001. O port
`SessionRepository.find_by_fingerprint` é **não-filtrante de propósito**: devolve
a sessão mesmo revogada ou expirada. Se filtrasse, um refresh já rotacionado
voltaria `None` — indistinguível de um token forjado — e a resposta correta
(derrubar as sessões do usuário) seria inalcançável. Este módulo é onde essa
possibilidade vira comportamento.

**A ordem dos passos é contrato** (concept §5 regra 5), e um passo em especial:
a checagem de *revogada* vem **antes** da de *expirada*. Invertê-las faria um
refresh revogado **e** expirado ser tratado como simples expiração, sem revogar
nada — e esse é justamente o perfil do token roubado e guardado por um tempo. Há
teste dedicado fixando a precedência, porque a troca é invisível numa revisão de
diff e não quebra nenhum outro teste.

**Sobre "família".** O port só oferece `revoke_all_for_user`, e `Session` não tem
campo de linhagem nem de causa de revogação. Então "revogar a família" significa,
literalmente, revogar **todas as sessões do usuário**. A consequência declarada
(concept §5 regra 6): reapresentar um refresh que saiu por *logout* também conta
como reuso e derruba as demais sessões. Erra para o lado seguro, e está registrado
como `[finding]` para uma Stage que distinga a causa.

**A rotação é uma unidade de trabalho, e a corrida perdida é reuso** (Stage 2.6,
ADR 2.6.0002 §1b). `revoke` da antiga e `add` da nova vão juntos: se o `add`
falha, a antiga continua válida e a retentativa do cliente funciona — antes da
2.6 ela ficava revogada sem substituta, e a retentativa caía na detecção de reuso
e derrubava **todas** as sessões do usuário por causa de um erro transitório.

E `revoke` devolve se revogou. Duas rotações concorrentes do mesmo refresh leem a
sessão ativa; a segunda espera o lock da linha e, quando a primeira comita,
revoga **zero** linhas. Antes da 2.6 o retorno era descartado e as duas emitiam
par novo — dois refresh vivos, medidos em 11 de 12 corridas na auditoria de
2026-09-28 —, ao contrário do que o concept 2.4 §6 descrevia como aceito. Agora a
perdedora desfaz a própria unidade, revoga todas as sessões **fora** dela (essa
escrita precisa comitar) e levanta `RefreshTokenReuseError`: fail-closed, a
semântica de reuso do ADR 2.2.0001. Se a primeira rotação é que desfaz, a segunda
revoga uma linha e rotaciona normalmente.
"""

from datetime import timedelta

from restaurant_hub.features.identity.application.dtos.commands import (
    RefreshSessionCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.results import (
    AuthenticationResult,
    to_authentication_result,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
)
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class _RotacaoPerdida(Exception):
    """A rotação perdeu a corrida dentro da unidade (`revoke` devolveu `False`).

    Classe privada do módulo, fora da hierarquia de erros de identity: só existe
    para sair da unidade por exceção — o que a desfaz — e é capturada no próprio
    `execute`. Nunca chega ao chamador, e por isso as varreduras do mapa de status
    não precisam (nem devem) enxergá-la.
    """


class RefreshSessionUseCase:
    """Troca um refresh token válido por um par novo, revogando o antigo."""

    # PLR0913: o construtor é a costura de injeção de dependência — quatro ports,
    # dois colaboradores compartilhados e os dois TTLs, montados uma vez pelo
    # composition root. Agrupá-los num objeto-parâmetro esconderia o grafo de
    # dependências que o hexagonal existe para deixar explícito.
    def __init__(  # noqa: PLR0913
        self,
        users: UserRepository,
        sessions: SessionRepository,
        token_issuer: TokenIssuer,
        id_generator: IdGenerator,
        clock: Clock,
        access_token_ttl: timedelta,
        refresh_token_ttl: timedelta,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._token_issuer = token_issuer
        self._id_generator = id_generator
        self._clock = clock
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl
        self._unit_of_work = unit_of_work

    def execute(self, command: RefreshSessionCommand) -> AuthenticationResult:
        """Rotaciona a sessão.

        Raises:
            RefreshTokenReuseError: o token já havia sido revogado — reuso. Todas
                as sessões do usuário são revogadas **antes** de levantar.
            InvalidRefreshTokenError: token desconhecido, expirado, ou de um
                usuário que não existe mais. Os três casos são deliberadamente
                indistinguíveis para o cliente.
        """
        fingerprint = self._token_issuer.fingerprint(command.refresh_token)
        session = self._sessions.find_by_fingerprint(fingerprint)

        if session is None:
            raise InvalidRefreshTokenError()

        now = self._clock.now()

        # PASSO 3 — antes da checagem de expiração, e a ordem é contrato.
        # Um token revogado que também expirou continua sendo reuso: quem o
        # guardou para usar depois é exatamente o cenário de roubo.
        if session.revoked_at is not None:
            self._sessions.revoke_all_for_user(session.user_id, now)
            raise RefreshTokenReuseError()

        # PASSO 4 — aqui `revoked_at is None`, então `is_active` falso significa
        # exclusivamente "expirada".
        if not session.is_active(now):
            raise InvalidRefreshTokenError()

        user = self._users.find_by_id(session.user_id)
        if user is None:
            # Sessão órfã: o usuário sumiu por baixo dela. Não é reuso, e não é
            # 404 — para quem apresenta o token, é apenas credencial inválida.
            raise InvalidRefreshTokenError()

        # A partir daqui a rotação acontece. A emissão dos tokens é CPU, sem I/O,
        # e fica antes da unidade para não alongar o lock da linha da sessão.
        new_session_id = SessionId(str(self._id_generator.next_id()))
        access_token_expires_at = now + self._access_token_ttl
        refresh_token_expires_at = now + self._refresh_token_ttl

        issued_refresh = self._token_issuer.issue_refresh_token()
        access_token = self._token_issuer.issue_access_token(
            AccessTokenClaims(
                subject=user.id,
                # Recarregado do repositório, não copiado da sessão: se o papel
                # ou o tenant do usuário mudou desde o login, o token novo já
                # reflete o estado atual.
                role=user.role,
                tenant_id=user.tenant_id,
                session_id=new_session_id,
                expires_at=access_token_expires_at,
            )
        )

        nova = Session(
            id=new_session_id,
            user_id=user.id,
            refresh_token_fingerprint=issued_refresh.fingerprint,
            issued_at=now,
            # Renovado a partir de `now`: não há teto absoluto de vida de
            # sessão nesta Stage (`[finding]`, concept §13).
            expires_at=refresh_token_expires_at,
        )

        # `revoke` antes de `add`, numa unidade — ver o docstring do módulo.
        try:
            with self._unit_of_work.transaction():
                if not self._sessions.revoke(session.id, now):
                    raise _RotacaoPerdida()
                self._sessions.add(nova)
        except _RotacaoPerdida:
            # Fora da unidade (já desfeita): esta revogação precisa comitar.
            self._sessions.revoke_all_for_user(session.user_id, now)
            raise RefreshTokenReuseError() from None

        return to_authentication_result(
            access_token=access_token,
            issued_refresh=issued_refresh,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
            user_id=user.id,
        )

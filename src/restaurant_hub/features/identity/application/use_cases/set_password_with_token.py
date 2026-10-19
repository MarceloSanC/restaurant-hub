"""Use case: definir a senha apresentando o token recebido por e-mail.

**É o use case mais sensível da Stage**, porque é alcançado por uma requisição
**não autenticada** que, se der certo, muda uma credencial. Três decisões
carregam a segurança inteira, e nenhuma delas é óbvia lendo o código de fora.

**1. O usuário alvo vem exclusivamente do token.** O command não tem `user_id` —
nem poderia: se tivesse, quem pedisse uma redefinição para a própria conta
definiria a senha de qualquer outra pessoa. O alvo é
`PasswordSetupToken.user_id`, isto é, o valor que **o servidor** gravou quando
emitiu o token.

**2. As quatro escritas são uma unidade de trabalho, e a ordem continua fail-closed:**

    consume  →  revoke_all_for_user  →  invalidate_all_for_user  →  set_password_hash

Desde a Stage 2.6 (issue #46, ADR 2.6.0001) as quatro escritas rodam numa
`UnitOfWork`: se qualquer uma falha, nenhuma fica gravada — o link continua
válido e o mesmo link funciona na tentativa seguinte. `consume` continua primeiro
porque é ele que decide a corrida: dentro da unidade, a linha do token fica
travada até o commit, e uma redenção concorrente espera e então reavalia
`consumed_at IS NULL` contra a linha comitada.

A ordem fail-closed da 2.5 — evicções **antes** da senha — fica, e fica
**redundante**, não errada: na ordem ingênua uma falha em `revoke_all_for_user`
deixaria a sessão do atacante viva depois de uma redefinição concluída (o buraco
do ADR 2.5.0003); com a unidade, essa falha desfaz a senha também. **Troca
declarada** (concept 2.6 R2): antes, uma falha parcial deixava as sessões já
revogadas com a senha inalterada; agora desfaz a revogação junto. Com a senha
inalterada, quem a tem reabre sessão de qualquer jeito, e a retentativa funciona
com o mesmo link.

**O hash é calculado antes de a unidade abrir** (R5): é CPU (argon2), e dentro da
unidade ele alongaria o tempo em que a linha do token e as sessões ficam travadas.

**3. Toda falha é a mesma exceção, com a mesma mensagem.** Token desconhecido,
expirado, já consumido ou de usuário apagado levantam `InvalidSetupTokenError`.
A conversão do `UserNotFoundError` (regra 16) é a menos evidente e a mais
importante: sem ela, o mapa de status responderia **404 com corpo falante** a um
token cujo dono foi removido, e o atacante distinguiria "esta string era um token
de verdade" de "chutei" — numa rota pública.

A invalidação em massa aqui é **sem escopo de propósito**, ao contrário da que
acontece na emissão: nada do usuário pode sobreviver à troca de senha, inclusive
um convite antigo de TTL longo (ADR 2.5.0003).
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    SetPasswordWithTokenCommand,
)
from restaurant_hub.features.identity.application.errors import (
    InvalidSetupTokenError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)
from restaurant_hub.features.identity.application.ports.out.password_setup_token_repository import (
    PasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.features.identity.application.ports.out.setup_token_issuer import (
    SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.shared.application.ports.out.clock import Clock


class SetPasswordWithTokenUseCase:
    """Redime um token de setup e grava a senha nova."""

    def __init__(  # noqa: PLR0913 — grafo de dependências, não parâmetros de chamada
        self,
        users: UserRepository,
        sessions: SessionRepository,
        tokens: PasswordSetupTokenRepository,
        token_issuer: SetupTokenIssuer,
        hasher: PasswordHasher,
        clock: Clock,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._tokens = tokens
        self._token_issuer = token_issuer
        self._hasher = hasher
        self._clock = clock
        self._unit_of_work = unit_of_work

    def execute(self, command: SetPasswordWithTokenCommand) -> None:
        """Define a senha do dono do token.

        Não devolve nada, e a ausência é deliberada (concept §5 regra 14):
        devolver um par de tokens transformaria o link de e-mail numa credencial
        de sessão.

        Raises:
            InvalidSetupTokenError: token desconhecido, expirado, já consumido ou
                de usuário inexistente — **uma** exceção para as quatro causas.
        """
        agora = self._clock.now()

        token = self._tokens.find_by_fingerprint(self._token_issuer.fingerprint(command.token))
        if token is None or not token.is_usable(agora):
            # `is_usable` é a checagem barata que evita ir ao banco à toa. Não é
            # a trava: quem decide a corrida é o `consume` abaixo.
            raise InvalidSetupTokenError()

        # Antes da unidade — ver a nota 2 do módulo (R5).
        hash_novo = self._hasher.hash(command.plain_password)

        with self._unit_of_work.transaction():
            if not self._tokens.consume(token.id, agora):
                # Perdeu a corrida para outra redenção do mesmo token. É aqui, e
                # só aqui, que o replay morre.
                raise InvalidSetupTokenError()

            # As duas evicções ANTES da escrita — ver a nota 2 do módulo.
            self._sessions.revoke_all_for_user(token.user_id, agora)
            # Sem `purpose`: nada do usuário sobrevive à troca de senha.
            self._tokens.invalidate_all_for_user(token.user_id, agora)

            try:
                self._users.set_password_hash(token.user_id, hash_novo)
            except UserNotFoundError as exc:
                # Regra 16. Sem esta conversão o mapa da 2.4 responderia 404 com
                # corpo falante, e o 401/404 distinguiria token real de chutado.
                raise InvalidSetupTokenError() from exc

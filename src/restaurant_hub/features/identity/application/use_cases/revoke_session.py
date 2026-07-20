"""Use case: logout — revoga a sessão do refresh token apresentado.

**Nunca levanta, e isso é a decisão de desenho do módulo.** Token desconhecido,
expirado ou já revogado terminam em sucesso silencioso. Duas razões:

1. **Não há nada a proteger.** Quem apresenta o token já o possui; recusar o
   logout não impede nada e apenas mantém viva uma sessão que o dono pediu para
   encerrar.
2. **Uma resposta distinta seria oráculo.** Um logout que respondesse "não
   encontrado" para token desconhecido e "ok" para token válido diria a qualquer
   um se um dado valor de refresh existe — sem precisar de credencial nenhuma.

A revogação em si é idempotente no port (`revoke` preserva o `revoked_at`
original), então repetir o logout não apaga o instante da primeira revogação —
que é o dado de que a forense de um incidente precisa (ADR 2.2.0001).
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    RevokeSessionCommand,
)
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.shared.application.ports.out.clock import Clock


class RevokeSessionUseCase:
    """Encerra a sessão associada a um refresh token."""

    def __init__(
        self,
        sessions: SessionRepository,
        token_issuer: TokenIssuer,
        clock: Clock,
    ) -> None:
        self._sessions = sessions
        self._token_issuer = token_issuer
        self._clock = clock

    def execute(self, command: RevokeSessionCommand) -> None:
        """Revoga a sessão do token, se houver. **Nunca levanta.**

        Note que a sessão é revogada mesmo se já estiver expirada: o custo é uma
        escrita inócua, e a alternativa — ramificar por estado — só criaria um
        caminho a mais para testar sem mudar o resultado observável.
        """
        fingerprint = self._token_issuer.fingerprint(command.refresh_token)
        session = self._sessions.find_by_fingerprint(fingerprint)

        if session is None:
            return

        self._sessions.revoke(session.id, self._clock.now())

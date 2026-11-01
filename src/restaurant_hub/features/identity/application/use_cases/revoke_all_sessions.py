"""Use case: revogar todas as sessões de um usuário.

Nasce na Stage 3.5 para o desligamento de funcionário (ADR 3.5.0003): quando o
desligamento em staff decide cortar o acesso, o gateway corta as sessões vivas do
login vinculado **antes** de gravar — a pessoa perde o acesso agora, não quando o
access token expirar. **Quando** cortar é decisão do consumidor, não deste use
case (ADR 3.8.0001: só o login de funcionário, e só se o registro desligado é a
fonte do acesso dele). A conta continua existindo e continua podendo logar; o que
ela deixa de alcançar é decidido pela autorização, não por este use case.

É uma linha sobre o port: `sessions.revoke_all_for_user(user_id, clock.now())`.
Idempotente porque o port já é — revogar de novo preserva o instante da primeira
revogação (regra 2 do `SessionRepository`), e um `user_id` sem sessão nenhuma,
ou desconhecido, não levanta: não há nada a cortar, e o desligamento não pode
falhar por isso.

Não é o logout (`RevokeSessionUseCase`): aquele revoga **uma** sessão pela posse
do refresh token; este revoga **todas** pela identidade do usuário, e a
autoridade para chamá-lo é do consumidor (a permissão `manage_staff` de quem
desliga, checada na rota de staff).
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    RevokeAllSessionsCommand,
)
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.shared.application.ports.out.clock import Clock


class RevokeAllSessionsUseCase:
    """Corta todas as sessões vivas do usuário, agora."""

    def __init__(self, sessions: SessionRepository, clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    def execute(self, command: RevokeAllSessionsCommand) -> None:
        """Revoga; nunca levanta por usuário sem sessão."""
        self._sessions.revoke_all_for_user(command.user_id, self._clock.now())

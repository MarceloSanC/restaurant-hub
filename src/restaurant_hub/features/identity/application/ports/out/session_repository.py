"""Port de saída: persistência de sessões de refresh (ADR 2.2.0001).

É o que torna o logout real: um JWT puro vale até expirar, então demissão e
logout precisam de estado do lado do servidor para cortar acesso de verdade.

**Semântica normativa** — a Stage 2.3 implementa exatamente isto em Postgres, e
cada regra existe por um motivo concreto:

1. **`find_by_fingerprint` não filtra.** Devolve a sessão mesmo revogada ou
   expirada. Se filtrasse, um refresh token já rotacionado (reuso — sinal
   clássico de token roubado) voltaria `None`, indistinguível de um token
   forjado, e a resposta padrão de revogar toda a família de sessões da vítima
   ficaria inalcançável. Filtrar é papel do chamador, via `Session.is_active`.
2. **`revoke` é idempotente no sentido forte.** Revogar sessão já revogada é
   *no-op* e **preserva o `revoked_at` original** — sobrescrever apagaria o
   instante da primeira revogação, que é justamente o dado que a forense de um
   incidente de reuso precisa.
3. **Id inexistente não levanta.** Revogar o que não existe é sucesso vazio;
   quem revoga não deve precisar checar antes.
"""

from datetime import datetime
from typing import Protocol

from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class SessionRepository(Protocol):
    """Contrato de persistência de sessões de refresh."""

    def add(self, session: Session) -> None:
        """Persiste uma sessão recém-criada."""
        ...

    def find_by_fingerprint(self, fingerprint: str) -> Session | None:
        """Devolve a sessão do fingerprint, **sem** filtrar revogada/expirada."""
        ...

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> None:
        """Revoga uma sessão (logout). Idempotente; id inexistente é no-op."""
        ...

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        """Revoga todas as sessões do usuário (demissão). Mesmas regras."""
        ...

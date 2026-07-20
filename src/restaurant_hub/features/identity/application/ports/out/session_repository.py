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
        """Persiste uma sessão recém-criada.

        **É inserção, não upsert** (ADR 2.3.0003). Id já gravado levanta
        `SessionAlreadyExistsError`; fingerprint já gravado levanta
        `SessionFingerprintAlreadyExistsError`. Os dois erros são distintos de
        propósito: id repetido é colisão, fingerprint repetido é o sinal de reuso
        de refresh token que esta tabela existe para tornar detectável.
        """
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

    def purge_expired(self, before: datetime) -> int:
        """Remove as sessões já expiradas em `before`. Devolve quantas removeu.

        O predicado é `expires_at <= before`, **inclusive** — a mesma fronteira de
        `Session.is_active`, que é half-open (em `now == expires_at` a sessão já
        expirou). Um `<` aqui deixaria para trás exatamente a sessão que
        `is_active` considera expirada, e "expirada" e "expurgável" passariam a
        discordar na fronteira.

        **A política de retenção é do chamador, não deste port** (ADR 2.3.0004):
        quem quiser preservar 90 dias de histórico forense passa `now - 90d`.
        Enterrar a janela aqui destruiria, num prazo que ninguém escolheu, o
        `revoked_at` que o ADR 2.2.0001 preserva justamente para investigar reuso
        de token.

        Sessão ainda válida nunca é removida, revogada ou não.
        """
        ...

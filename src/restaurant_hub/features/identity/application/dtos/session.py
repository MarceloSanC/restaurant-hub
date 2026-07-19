"""Sessão de refresh — o registro que torna o logout real.

Um JWT puro não é revogável: uma vez assinado, vale até expirar. Como demissão e
logout precisam **cortar acesso de verdade** (dado de jornada é sensível — LGPD),
o refresh token é persistido como sessão, e revogar a sessão invalida a
renovação (ADR 2.2.0001).

Guarda apenas o **fingerprint** do refresh token, nunca o valor.

Não expõe método de revogação de propósito: revogar é operação de port
(`SessionRepository.revoke`). Como o contrato não tem `save(session)`, um
`Session` "revogado em memória" não teria caminho de volta ao banco — o método
seria código morto convidando fake e adapter a divergirem.
"""

from dataclasses import dataclass
from datetime import datetime

from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


@dataclass(frozen=True)
class Session:
    """Sessão de refresh de um usuário.

    Attributes:
        id: identidade da sessão.
        user_id: dono da sessão.
        refresh_token_fingerprint: derivação do refresh token emitido.
        issued_at: instante da emissão.
        expires_at: instante em que a sessão deixa de valer.
        revoked_at: instante da revogação, ou `None` se nunca revogada.
    """

    id: SessionId
    user_id: UserId
    refresh_token_fingerprint: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """True se a sessão ainda vale em `now`.

        Intervalo **half-open**: em `now == expires_at` a sessão já expirou. A
        convenção precisa ser explícita porque o instante de fronteira é
        exatamente onde fake e adapter real tendem a divergir em silêncio.
        """
        return self.revoked_at is None and now < self.expires_at

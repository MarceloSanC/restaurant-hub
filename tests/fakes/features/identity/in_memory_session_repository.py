"""Fake in-memory de `SessionRepository`.

Este fake é, na prática, a **especificação executável** da tabela de sessões que
a Stage 2.3 vai criar. Por isso implementa a semântica normativa do port ao pé da
letra — inclusive as partes contraintuitivas (busca que não filtra, revogação que
não sobrescreve) — em vez da versão "mais óbvia", que é justamente onde um
adapter real costuma divergir.

Como `Session` é `frozen`, atualizar significa `dataclasses.replace`: o mesmo
caminho que a 2.1 fixou para mutação de entidade, que reexecuta validações em vez
de contorná-las por atribuição.
"""

import dataclasses
from datetime import datetime

from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class InMemorySessionRepository:
    """Implementação in-memory do port, honrando a semântica normativa."""

    def __init__(self) -> None:
        self.sessions: dict[SessionId, Session] = {}

    def add(self, session: Session) -> None:
        self.sessions[session.id] = session

    def find_by_fingerprint(self, fingerprint: str) -> Session | None:
        # Sem filtro por revogação/expiração — regra 1 do port. É o que permite
        # detectar reuso de refresh token na 2.4.
        for session in self.sessions.values():
            if session.refresh_token_fingerprint == fingerprint:
                return session
        return None

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return  # regra 3: id inexistente é no-op
        self._revoke_one(session, revoked_at)

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        for session in list(self.sessions.values()):
            if session.user_id == user_id:
                self._revoke_one(session, revoked_at)

    def _revoke_one(self, session: Session, revoked_at: datetime) -> None:
        if session.revoked_at is not None:
            # Regra 2: preserva o instante da PRIMEIRA revogação.
            return
        self.sessions[session.id] = dataclasses.replace(session, revoked_at=revoked_at)


_conforms: SessionRepository = InMemorySessionRepository()

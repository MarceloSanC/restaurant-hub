"""Adapter Postgres de `SessionRepository`.

A semântica normativa deste port tem três regras contraintuitivas, e o SQL
"natural" quebra as três. Elas estão implementadas aqui exatamente como o port as
descreve — e cada uma existe por um motivo de segurança concreto:

**1. `find_by_fingerprint` NÃO filtra.** Sem `WHERE revoked_at IS NULL`, sem
`WHERE expires_at > now()`. Parece um descuido e é o contrário: um refresh token já
rotacionado precisa ser **encontrável** para que a 2.4 saiba distinguir "token
reusado" (sinal clássico de roubo, que manda revogar a família inteira de sessões
da vítima) de "token forjado". Filtrar aqui devolveria `None` nos dois casos e
tornaria a resposta de incidente inalcançável.

**2. `revoke` usa `WHERE revoked_at IS NULL`.** Sem essa cláusula, revogar duas
vezes sobrescreveria o instante da **primeira** revogação — que é justamente o dado
que a forense de um incidente de reuso precisa. Idempotência aqui é "no-op de
verdade", não "escreve de novo o mesmo campo".

**3. `purge_expired` usa `<=`, não `<`.** `Session.is_active` é half-open, então em
`expires_at == before` a sessão **já expirou**. Um `<` deixaria para trás
exatamente a sessão que `is_active` considera expirada.
"""

from datetime import datetime

from sqlalchemy import Connection, Engine, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.integrity_errors import (
    constraint_name,
    translate,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import sessions
from restaurant_hub.features.identity.adapters.out.postgres.unit_connection import (
    for_read,
    for_write,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class PostgresSessionRepository:
    """Implementação PostgreSQL do port `SessionRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, session: Session) -> None:
        try:
            with for_write(self._engine) as connection:
                connection.execute(sessions.insert().values(**mappers.session_to_row(session)))
        except IntegrityError as error:
            detail = (
                session.refresh_token_fingerprint
                if constraint_name(error) == "uq_sessions_fingerprint"
                else session.id
            )
            raise translate(error, detail) from error

    def find_by_fingerprint(self, fingerprint: str) -> Session | None:
        """Devolve a sessão **sem filtrar** revogada nem expirada (regra 1)."""
        with for_read(self._engine) as connection:
            row = connection.execute(
                select(sessions).where(sessions.c.refresh_token_fingerprint == fingerprint)
            ).one_or_none()
            return mappers.row_to_session(row) if row is not None else None

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> bool:
        """Revoga uma sessão. `True` só se esta chamada revogou (`rowcount == 1`)."""
        with for_write(self._engine) as connection:
            return self._revoke(connection, sessions.c.id == session_id, revoked_at) == 1

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        """Revoga todas as sessões do usuário (demissão). Mesmas regras."""
        with for_write(self._engine) as connection:
            self._revoke(connection, sessions.c.user_id == user_id, revoked_at)

    def purge_expired(self, before: datetime) -> int:
        """Remove as sessões já expiradas em `before` (`expires_at <= before`)."""
        with for_write(self._engine) as connection:
            result = connection.execute(delete(sessions).where(sessions.c.expires_at <= before))
            return result.rowcount

    # ---- núcleo sobre `Connection` (a mesma dentro ou fora da unidade de trabalho) ----

    def _revoke(
        self, connection: Connection, criterion: ColumnElement[bool], revoked_at: datetime
    ) -> int:
        """Devolve quantas sessões esta chamada revogou — já revogadas não contam."""
        result = connection.execute(
            update(sessions)
            # `revoked_at IS NULL` é o que torna a idempotência forte: sessão já
            # revogada não é tocada, e o instante da PRIMEIRA revogação sobrevive.
            .where(criterion, sessions.c.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        return int(result.rowcount)

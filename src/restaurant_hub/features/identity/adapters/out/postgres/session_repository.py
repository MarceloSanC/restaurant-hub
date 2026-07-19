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
    nome_da_constraint,
    traduzir,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import sessions
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class PostgresSessionRepository:
    """Implementação PostgreSQL do port `SessionRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, session: Session) -> None:
        try:
            with self._engine.begin() as conexao:
                conexao.execute(sessions.insert().values(**mappers.sessao_para_linha(session)))
        except IntegrityError as erro:
            detalhe = (
                session.refresh_token_fingerprint
                if nome_da_constraint(erro) == "uq_sessions_fingerprint"
                else session.id
            )
            raise traduzir(erro, detalhe) from erro

    def find_by_fingerprint(self, fingerprint: str) -> Session | None:
        """Devolve a sessão **sem filtrar** revogada nem expirada (regra 1)."""
        with self._engine.connect() as conexao:
            linha = conexao.execute(
                select(sessions).where(sessions.c.refresh_token_fingerprint == fingerprint)
            ).one_or_none()
            return mappers.linha_para_sessao(linha) if linha is not None else None

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> None:
        """Revoga uma sessão. Id inexistente é no-op; já revogada preserva o original."""
        with self._engine.begin() as conexao:
            self._revoke(conexao, sessions.c.id == session_id, revoked_at)

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        """Revoga todas as sessões do usuário (demissão). Mesmas regras."""
        with self._engine.begin() as conexao:
            self._revoke(conexao, sessions.c.user_id == user_id, revoked_at)

    def purge_expired(self, before: datetime) -> int:
        """Remove as sessões já expiradas em `before` (`expires_at <= before`)."""
        with self._engine.begin() as conexao:
            resultado = conexao.execute(delete(sessions).where(sessions.c.expires_at <= before))
            return resultado.rowcount

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) ----

    def _revoke(
        self, conexao: Connection, criterio: ColumnElement[bool], revoked_at: datetime
    ) -> None:
        conexao.execute(
            update(sessions)
            # `revoked_at IS NULL` é o que torna a idempotência forte: sessão já
            # revogada não é tocada, e o instante da PRIMEIRA revogação sobrevive.
            .where(criterio, sessions.c.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )

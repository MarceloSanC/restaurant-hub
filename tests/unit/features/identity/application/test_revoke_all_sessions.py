"""Testes do use case `revoke_all_sessions` — Stage 3.5, CA17 (ADR 3.5.0003).

O que se protege: **todas** as sessões vivas do usuário são cortadas no instante
do relógio injetado, as de outros usuários ficam intactas, e um usuário sem
sessão — ou desconhecido — não faz o desligamento falhar.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    RevokeAllSessionsCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.use_cases.revoke_all_sessions import (
    RevokeAllSessionsUseCase,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.shared.fake_clock import FakeClock

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_ANTES = _AGORA - timedelta(hours=2)
_ALVO = UserId("user-alvo")
_OUTRO = UserId("user-outro")


class _Fixture:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.clock = FakeClock(_AGORA)
        self.use_case = RevokeAllSessionsUseCase(sessions=self.sessions, clock=self.clock)

    def com_sessao(
        self,
        session_id: str,
        *,
        user_id: UserId = _ALVO,
        revogada_em: datetime | None = None,
    ) -> Session:
        session = Session(
            id=SessionId(session_id),
            user_id=user_id,
            refresh_token_fingerprint=f"fp::{session_id}",
            issued_at=_ANTES,
            expires_at=_AGORA + timedelta(days=14),
            revoked_at=revogada_em,
        )
        self.sessions.add(session)
        return session

    def revogar(self, user_id: UserId = _ALVO) -> None:
        self.use_case.execute(RevokeAllSessionsCommand(user_id=user_id))


def test_revoga_todas_as_sessoes_do_usuario_no_instante_do_relogio() -> None:
    fixture = _Fixture()
    fixture.com_sessao("sess-1")
    fixture.com_sessao("sess-2")

    fixture.revogar()

    assert fixture.sessions.sessions[SessionId("sess-1")].revoked_at == _AGORA
    assert fixture.sessions.sessions[SessionId("sess-2")].revoked_at == _AGORA


def test_nao_toca_nas_sessoes_de_outro_usuario() -> None:
    fixture = _Fixture()
    fixture.com_sessao("sess-alvo")
    fixture.com_sessao("sess-outro", user_id=_OUTRO)

    fixture.revogar()

    assert fixture.sessions.sessions[SessionId("sess-alvo")].revoked_at == _AGORA
    assert fixture.sessions.sessions[SessionId("sess-outro")].revoked_at is None


def test_usuario_sem_sessao_nao_levanta() -> None:
    """Idempotência — o desligamento não pode falhar porque não havia o que cortar."""
    fixture = _Fixture()

    fixture.revogar()
    fixture.revogar(UserId("nunca-logou"))

    assert fixture.sessions.sessions == {}


def test_revogar_de_novo_preserva_o_instante_da_primeira_revogacao() -> None:
    """Regra 2 do port, observada pelo use case: revogação não sobrescreve."""
    fixture = _Fixture()
    fixture.com_sessao("sess-1", revogada_em=_ANTES)

    fixture.revogar()

    assert fixture.sessions.sessions[SessionId("sess-1")].revoked_at == _ANTES


def test_usa_o_relogio_injetado_e_nao_o_do_sistema() -> None:
    fixture = _Fixture()
    fixture.com_sessao("sess-1")
    depois = _AGORA + timedelta(minutes=5)
    fixture.clock.advance(timedelta(minutes=5))

    fixture.revogar()

    assert fixture.sessions.sessions[SessionId("sess-1")].revoked_at == depois

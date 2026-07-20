"""Testes do logout — o use case que **nunca levanta**.

Quase todo o valor aqui está nos caminhos degenerados. Um logout que falhasse
para token desconhecido seria um oráculo: qualquer um, sem credencial nenhuma,
descobriria se um dado valor de refresh existe. Por isso os testes de "não
levanta" não são preenchimento de cobertura — são a especificação.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    RevokeSessionCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.use_cases.revoke_session import (
    RevokeSessionUseCase,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.shared.fake_clock import FakeClock

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_ANTES = _NOW - timedelta(hours=2)
_USER_ID = UserId("user-1")


class _Fixture:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.issuer = FakeTokenIssuer()
        self.clock = FakeClock(_NOW)
        self.use_case = RevokeSessionUseCase(
            sessions=self.sessions,
            token_issuer=self.issuer,
            clock=self.clock,
        )

    def com_sessao(
        self,
        *,
        refresh_value: str = "refresh-1",
        revogada_em: datetime | None = None,
        expirada: bool = False,
        session_id: str = "sess-1",
    ) -> Session:
        session = Session(
            id=SessionId(session_id),
            user_id=_USER_ID,
            refresh_token_fingerprint=self.issuer.fingerprint(refresh_value),
            issued_at=_ANTES,
            expires_at=_ANTES if expirada else _NOW + timedelta(days=14),
            revoked_at=revogada_em,
        )
        self.sessions.add(session)
        return session

    def logout(self, valor: str = "refresh-1") -> None:
        self.use_case.execute(RevokeSessionCommand(refresh_token=valor))


def test_logout_revoga_a_sessao_do_token() -> None:
    fixture = _Fixture()
    session = fixture.com_sessao()

    fixture.logout()

    assert fixture.sessions.sessions[session.id].revoked_at == _NOW


def test_logout_nao_derruba_as_outras_sessoes_do_usuario() -> None:
    """Logout é por dispositivo, não por conta.

    Quem quer derrubar tudo é a detecção de reuso e a demissão — não o botão
    "sair" de um celular.
    """
    fixture = _Fixture()
    alvo = fixture.com_sessao()
    outra = fixture.com_sessao(refresh_value="refresh-2", session_id="sess-2")

    fixture.logout()

    assert fixture.sessions.sessions[alvo.id].revoked_at == _NOW
    assert fixture.sessions.sessions[outra.id].revoked_at is None


def test_logout_de_token_desconhecido_nao_levanta() -> None:
    """Sem oráculo: a resposta é a mesma para token que existe e que não existe.

    Um 404 aqui diria, a quem não tem credencial nenhuma, se um dado valor de
    refresh está registrado.
    """
    fixture = _Fixture()

    fixture.logout("token-que-ninguem-emitiu")  # não levanta


def test_logout_de_sessao_ja_revogada_preserva_o_instante_original() -> None:
    """Idempotência no sentido forte (regra 2 do port).

    Sobrescrever `revoked_at` apagaria o instante da **primeira** revogação — que
    é exatamente o dado que a forense de um incidente de reuso precisa
    (ADR 2.2.0001). Repetir o logout não pode destruir essa evidência.
    """
    fixture = _Fixture()
    primeira_revogacao = _NOW - timedelta(minutes=30)
    session = fixture.com_sessao(revogada_em=primeira_revogacao)

    fixture.logout()

    assert fixture.sessions.sessions[session.id].revoked_at == primeira_revogacao


def test_logout_de_sessao_expirada_nao_levanta() -> None:
    """Expirada ainda é revogável — ramificar por estado só criaria caminho novo."""
    fixture = _Fixture()
    session = fixture.com_sessao(expirada=True)

    fixture.logout()

    assert fixture.sessions.sessions[session.id].revoked_at == _NOW


def test_logout_e_repetivel_sem_erro() -> None:
    fixture = _Fixture()
    fixture.com_sessao()

    fixture.logout()
    fixture.logout()
    fixture.logout()  # nenhuma das repetições levanta

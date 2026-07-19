"""Testes do fake de `SessionRepository` — concept CA16.

Estes testes valem mais como **especificação para a Stage 2.3** do que como
verificação do dicionário: cada um fixa uma regra que o SQL do adapter real pode
facilmente implementar "de forma mais natural" e, com isso, quebrar.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
_TTL = timedelta(days=7)


def _session(
    session_id: str = "sess-1",
    user_id: str = "user-1",
    fingerprint: str = "fp::abc",
    *,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> Session:
    return Session(
        id=SessionId(session_id),
        user_id=UserId(user_id),
        refresh_token_fingerprint=fingerprint,
        issued_at=_NOW,
        expires_at=expires_at if expires_at is not None else _NOW + _TTL,
        revoked_at=revoked_at,
    )


def test_sessao_faz_round_trip_por_fingerprint() -> None:
    repo = InMemorySessionRepository()
    session = _session()

    repo.add(session)

    assert repo.find_by_fingerprint("fp::abc") == session


def test_fingerprint_desconhecido_devolve_none() -> None:
    assert InMemorySessionRepository().find_by_fingerprint("fp::nada") is None


def test_busca_devolve_sessao_revogada() -> None:
    """Regra 1 do port — e a base da detecção de reuso de refresh token.

    Se a busca escondesse a sessão revogada, um token já rotacionado (sinal de
    roubo) seria indistinguível de um token forjado, e a 2.4 não teria como
    revogar a família de sessões da vítima.
    """
    repo = InMemorySessionRepository()
    repo.add(_session())
    repo.revoke(SessionId("sess-1"), _NOW + timedelta(hours=1))

    encontrada = repo.find_by_fingerprint("fp::abc")

    assert encontrada is not None
    assert encontrada.revoked_at == _NOW + timedelta(hours=1)


def test_busca_devolve_sessao_expirada() -> None:
    """Regra 1 do port — filtrar por validade é papel do chamador."""
    repo = InMemorySessionRepository()
    repo.add(_session(expires_at=_NOW - timedelta(seconds=1)))

    encontrada = repo.find_by_fingerprint("fp::abc")

    assert encontrada is not None
    assert encontrada.is_active(_NOW) is False


def test_revogar_duas_vezes_preserva_o_instante_da_primeira() -> None:
    """Regra 2 do port.

    Sobrescrever o `revoked_at` apagaria o instante em que o acesso foi cortado
    de fato — exatamente o dado que a apuração de um incidente precisa.
    """
    repo = InMemorySessionRepository()
    repo.add(_session())
    primeira = _NOW + timedelta(hours=1)
    segunda = _NOW + timedelta(hours=5)

    repo.revoke(SessionId("sess-1"), primeira)
    repo.revoke(SessionId("sess-1"), segunda)

    encontrada = repo.find_by_fingerprint("fp::abc")
    assert encontrada is not None
    assert encontrada.revoked_at == primeira


def test_revogar_id_inexistente_nao_levanta() -> None:
    """Regra 3 do port — quem revoga não precisa checar existência antes."""
    InMemorySessionRepository().revoke(SessionId("nao-existe"), _NOW)


def test_revogar_todas_de_usuario_inexistente_nao_levanta() -> None:
    InMemorySessionRepository().revoke_all_for_user(UserId("nao-existe"), _NOW)


def test_revogar_todas_do_usuario_atinge_todas_as_sessoes_dele() -> None:
    """Cenário de demissão: cortar acesso em todos os dispositivos de uma vez."""
    repo = InMemorySessionRepository()
    repo.add(_session("sess-1", "user-1", "fp::a"))
    repo.add(_session("sess-2", "user-1", "fp::b"))

    repo.revoke_all_for_user(UserId("user-1"), _NOW)

    for fingerprint in ("fp::a", "fp::b"):
        session = repo.find_by_fingerprint(fingerprint)
        assert session is not None
        assert session.is_active(_NOW) is False


def test_revogar_todas_do_usuario_nao_afeta_outro_usuario() -> None:
    """Demitir alguém não pode deslogar o restaurante inteiro."""
    repo = InMemorySessionRepository()
    repo.add(_session("sess-1", "user-1", "fp::a"))
    repo.add(_session("sess-2", "user-2", "fp::b"))

    repo.revoke_all_for_user(UserId("user-1"), _NOW)

    intacta = repo.find_by_fingerprint("fp::b")
    assert intacta is not None
    assert intacta.revoked_at is None
    assert intacta.is_active(_NOW) is True


def test_revogar_todas_preserva_o_instante_de_quem_ja_estava_revogado() -> None:
    """Regra 2 vale também no caminho em lote."""
    repo = InMemorySessionRepository()
    primeira = _NOW + timedelta(hours=1)
    repo.add(_session("sess-1", "user-1", "fp::a"))
    repo.revoke(SessionId("sess-1"), primeira)
    repo.add(_session("sess-2", "user-1", "fp::b"))

    repo.revoke_all_for_user(UserId("user-1"), _NOW + timedelta(hours=9))

    ja_revogada = repo.find_by_fingerprint("fp::a")
    recem_revogada = repo.find_by_fingerprint("fp::b")
    assert ja_revogada is not None
    assert recem_revogada is not None
    assert ja_revogada.revoked_at == primeira
    assert recem_revogada.revoked_at == _NOW + timedelta(hours=9)

"""`PostgresSessionRepository` contra PostgreSQL real — CA9-CA14.

Cada teste aqui fixa uma regra que o SQL "natural" quebraria: a busca que não
filtra, a revogação que não sobrescreve, o expurgo com fronteira inclusiva.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.errors import (
    SessionAlreadyExistsError,
    SessionFingerprintAlreadyExistsError,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_MICROSSEGUNDOS = 123456
_SESSOES_EXPIRADAS = 2
_TTL = timedelta(days=7)
_HASH = PasswordHash("hashed::s3nha")


@pytest.fixture
def cenario(banco_limpo: Engine) -> Engine:
    """Um tenant e dois usuários — sessões precisam de dono (FK)."""
    PostgresRestaurantRepository(banco_limpo).add(
        Restaurant(id=RestaurantId("rest-a"), name="Cantina")
    )
    usuarios = PostgresUserRepository(banco_limpo)
    for user_id, email in (("user-1", "a@x.com"), ("user-2", "b@x.com")):
        usuarios.add(
            User(
                id=UserId(user_id),
                email=Email(email),
                role=Role.OWNER,
                tenant_id=RestaurantId("rest-a"),
            ),
            _HASH,
        )
    return banco_limpo


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


# ---------------------------------------------------------------------------
# Round-trip, fuso e schema — CA9, CA14
# ---------------------------------------------------------------------------


def test_sessao_faz_round_trip_preservando_fuso_e_instante(cenario: Engine) -> None:
    """CA14 — volta aware em UTC, mesmo instante, com microssegundos intactos."""
    repo = PostgresSessionRepository(cenario)
    sessao = _session(expires_at=_NOW + _TTL + timedelta(microseconds=_MICROSSEGUNDOS))
    repo.add(sessao)

    lida = repo.find_by_fingerprint("fp::abc")

    assert lida is not None
    assert lida.issued_at.tzinfo == UTC
    assert lida.expires_at.tzinfo == UTC
    assert lida.issued_at == sessao.issued_at
    assert lida.expires_at == sessao.expires_at
    assert lida.expires_at.microsecond == _MICROSSEGUNDOS


def test_is_active_da_o_mesmo_resultado_antes_e_depois_de_gravar(cenario: Engine) -> None:
    """CA14 — inclusive no instante de fronteira, onde half-open decide.

    Se o round-trip mudasse fuso ou truncasse precisão, `is_active` divergiria
    exatamente aqui, e a sessão viveria um instante a mais ou a menos do que
    deveria.
    """
    repo = PostgresSessionRepository(cenario)
    fronteira = _NOW + _TTL
    sessao = _session(expires_at=fronteira)
    repo.add(sessao)

    lida = repo.find_by_fingerprint("fp::abc")
    assert lida is not None

    for momento in (fronteira - timedelta(microseconds=1), fronteira, fronteira + _TTL):
        assert lida.is_active(momento) == sessao.is_active(momento)
    # E a convenção half-open segue valendo depois do banco.
    assert lida.is_active(fronteira) is False


def test_sessions_nao_guarda_valor_de_token(cenario: Engine) -> None:
    """CA9 — asserção de igualdade de conjunto sobre o schema real."""
    with cenario.connect() as conexao:
        colunas = {
            linha[0]
            for linha in conexao.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'sessions'"
                )
            )
        }
    assert colunas == {
        "id",
        "user_id",
        "refresh_token_fingerprint",
        "issued_at",
        "expires_at",
        "revoked_at",
    }


# ---------------------------------------------------------------------------
# find_by_fingerprint NÃO filtra — I6 / CA10
# ---------------------------------------------------------------------------


def test_find_by_fingerprint_devolve_sessao_revogada(cenario: Engine) -> None:
    """Filtrar aqui tornaria indistinguíveis token reusado e token forjado."""
    repo = PostgresSessionRepository(cenario)
    repo.add(_session())
    repo.revoke(SessionId("sess-1"), _NOW)

    lida = repo.find_by_fingerprint("fp::abc")
    assert lida is not None
    assert lida.revoked_at is not None


def test_find_by_fingerprint_devolve_sessao_expirada(cenario: Engine) -> None:
    repo = PostgresSessionRepository(cenario)
    repo.add(_session(expires_at=_NOW - timedelta(seconds=1)))

    lida = repo.find_by_fingerprint("fp::abc")
    assert lida is not None
    assert lida.is_active(_NOW) is False


def test_find_by_fingerprint_inexistente_devolve_none(cenario: Engine) -> None:
    assert PostgresSessionRepository(cenario).find_by_fingerprint("fp::nada") is None


# ---------------------------------------------------------------------------
# revoke — I7 / CA11, CA12
# ---------------------------------------------------------------------------


def test_revogar_duas_vezes_preserva_o_instante_da_primeira(cenario: Engine) -> None:
    """CA11 — idempotência **forte**.

    Sem `WHERE revoked_at IS NULL`, a segunda revogação sobrescreveria o instante
    da primeira — que é o dado que a forense de um incidente de reuso precisa.
    """
    repo = PostgresSessionRepository(cenario)
    repo.add(_session())
    primeira = _NOW
    segunda = _NOW + timedelta(hours=1)

    assert repo.revoke(SessionId("sess-1"), primeira) is True
    assert repo.revoke(SessionId("sess-1"), segunda) is False

    lida = repo.find_by_fingerprint("fp::abc")
    assert lida is not None
    assert lida.revoked_at == primeira


def test_revogar_id_inexistente_nao_levanta(cenario: Engine) -> None:
    """CA11 — quem revoga não deve precisar checar antes."""
    assert PostgresSessionRepository(cenario).revoke(SessionId("fantasma"), _NOW) is False


def test_revoke_all_atinge_so_as_sessoes_do_usuario(cenario: Engine) -> None:
    """CA12."""
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-1", "user-1", "fp::a"))
    repo.add(_session("sess-2", "user-1", "fp::b"))
    repo.add(_session("sess-3", "user-2", "fp::c"))

    repo.revoke_all_for_user(UserId("user-1"), _NOW)

    assert repo.find_by_fingerprint("fp::a").revoked_at == _NOW  # type: ignore[union-attr]
    assert repo.find_by_fingerprint("fp::b").revoked_at == _NOW  # type: ignore[union-attr]
    assert repo.find_by_fingerprint("fp::c").revoked_at is None  # type: ignore[union-attr]


def test_revoke_all_preserva_instante_de_sessao_ja_revogada(cenario: Engine) -> None:
    """A idempotência forte vale também na revogação em lote."""
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-1", "user-1", "fp::a"))
    repo.add(_session("sess-2", "user-1", "fp::b"))
    antes = _NOW - timedelta(hours=2)
    repo.revoke(SessionId("sess-1"), antes)

    repo.revoke_all_for_user(UserId("user-1"), _NOW)

    assert repo.find_by_fingerprint("fp::a").revoked_at == antes  # type: ignore[union-attr]
    assert repo.find_by_fingerprint("fp::b").revoked_at == _NOW  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# add é inserção — CA6
# ---------------------------------------------------------------------------


def test_sessao_com_id_duplicado_levanta(cenario: Engine) -> None:
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-1", fingerprint="fp::a"))

    with pytest.raises(SessionAlreadyExistsError):
        repo.add(_session("sess-1", fingerprint="fp::b"))


def test_fingerprint_duplicado_levanta_erro_proprio(cenario: Engine) -> None:
    """CA6 — distinguível de id duplicado, porque significa reuso de token."""
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-1", fingerprint="fp::a"))

    with pytest.raises(SessionFingerprintAlreadyExistsError):
        repo.add(_session("sess-2", fingerprint="fp::a"))


def test_sessao_de_usuario_inexistente_nao_e_traduzida(cenario: Engine) -> None:
    """Decisão 7 — FK sobe como `IntegrityError`."""
    with pytest.raises(IntegrityError):
        PostgresSessionRepository(cenario).add(_session(user_id="fantasma"))


# ---------------------------------------------------------------------------
# purge_expired — I9 / CA13
# ---------------------------------------------------------------------------


def test_purge_usa_fronteira_inclusiva(cenario: Engine) -> None:
    """CA13 — `expires_at == before` já expirou e tem de sair.

    É a mesma fronteira de `is_active`; um `<` deixaria para trás exatamente a
    sessão que o DTO considera expirada.
    """
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-borda", fingerprint="fp::borda", expires_at=_NOW))

    assert repo.purge_expired(_NOW) == 1
    assert repo.find_by_fingerprint("fp::borda") is None


def test_purge_preserva_sessoes_validas_e_conta_o_que_removeu(cenario: Engine) -> None:
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-viva", fingerprint="fp::viva", expires_at=_NOW + _TTL))
    repo.add(_session("sess-morta1", fingerprint="fp::m1", expires_at=_NOW - _TTL))
    repo.add(_session("sess-morta2", "user-2", "fp::m2", expires_at=_NOW - _TTL))

    removidas = repo.purge_expired(_NOW)

    assert removidas == _SESSOES_EXPIRADAS
    assert repo.find_by_fingerprint("fp::viva") is not None
    assert repo.find_by_fingerprint("fp::m1") is None
    assert repo.find_by_fingerprint("fp::m2") is None


def test_purge_poupa_sessao_revogada_mas_ainda_nao_expirada(cenario: Engine) -> None:
    """O expurgo é por expiração, não por revogação.

    Preservar o `revoked_at` de uma sessão ainda não expirada é o que sustenta a
    forense do ADR 2.2.0001 — e a janela de retenção é escolha do chamador, não
    deste adapter.
    """
    repo = PostgresSessionRepository(cenario)
    repo.add(_session("sess-1", fingerprint="fp::a", expires_at=_NOW + _TTL))
    repo.revoke(SessionId("sess-1"), _NOW)

    assert repo.purge_expired(_NOW) == 0
    assert repo.find_by_fingerprint("fp::a") is not None


def test_purge_em_banco_vazio_devolve_zero(cenario: Engine) -> None:
    assert PostgresSessionRepository(cenario).purge_expired(_NOW) == 0

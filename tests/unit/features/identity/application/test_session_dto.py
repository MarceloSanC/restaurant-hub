"""Testes dos DTOs de credencial, token e sessão.

O foco é `Session.is_active`, cuja fronteira é contrato: a Stage 2.3 vai
implementar a mesma regra em SQL, e um `<` virando `<=` ali é o tipo de
divergência que só aparece como sessão fantasma em produção.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.credentials import UserCredentials
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.tokens import (
    AccessTokenClaims,
    IssuedRefreshToken,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
_TTL = timedelta(days=7)


def _session(*, revoked_at: datetime | None = None) -> Session:
    return Session(
        id=SessionId("sess-1"),
        user_id=UserId("user-1"),
        refresh_token_fingerprint="fp::abc",
        issued_at=_NOW,
        expires_at=_NOW + _TTL,
        revoked_at=revoked_at,
    )


def test_sessao_recem_emitida_esta_ativa() -> None:
    assert _session().is_active(_NOW) is True


def test_sessao_expirada_nao_esta_ativa() -> None:
    assert _session().is_active(_NOW + _TTL + timedelta(seconds=1)) is False


def test_sessao_expira_no_instante_exato_do_vencimento() -> None:
    """Intervalo half-open: em `now == expires_at` a sessão JÁ expirou.

    É a fronteira que separa `<` de `<=`. Sem este teste, trocar um pelo outro —
    aqui ou no SQL da 2.3 — passa despercebido e concede uma janela extra de
    acesso a quem já deveria estar fora.
    """
    assert _session().is_active(_NOW + _TTL) is False


def test_sessao_revogada_nao_esta_ativa_mesmo_dentro_do_prazo() -> None:
    """Revogação vence prazo — é isso que faz logout e demissão cortarem acesso."""
    revogada = _session(revoked_at=_NOW + timedelta(hours=1))
    assert revogada.is_active(_NOW + timedelta(hours=2)) is False


def test_sessao_nao_expoe_metodo_de_revogacao() -> None:
    """Revogar é operação de port; um método aqui seria código morto (ADR 2.2.0001)."""
    for atributo in ("revoke", "revoked", "revogar"):
        assert not hasattr(_session(), atributo)


def test_sessao_e_imutavel() -> None:
    with pytest.raises(FrozenInstanceError):
        _session().revoked_at = _NOW  # type: ignore[misc]


def test_sessao_guarda_fingerprint_e_nunca_o_valor_do_token() -> None:
    """O campo existe para o fingerprint; não há onde guardar o segredo."""
    campos = set(vars(_session()))
    assert "refresh_token_fingerprint" in campos
    assert "refresh_token" not in campos
    assert "value" not in campos


def test_issued_refresh_token_separa_valor_de_fingerprint() -> None:
    emitido = IssuedRefreshToken(value="tok-secreto", fingerprint="fp::tok-secreto")
    assert emitido.value == "tok-secreto"
    assert emitido.fingerprint != emitido.value


def test_access_token_claims_carrega_a_sessao_de_origem() -> None:
    """`session_id` nas claims é o que permitirá fechar a janela residual na 2.4."""
    claims = AccessTokenClaims(
        subject=UserId("user-1"),
        role=Role.MANAGER,
        tenant_id=RestaurantId("rest-1"),
        session_id=SessionId("sess-1"),
        expires_at=_NOW + timedelta(minutes=15),
    )
    assert claims.session_id == "sess-1"
    assert claims.tenant_id == "rest-1"


def test_access_token_claims_aceita_ator_sem_tenant() -> None:
    """`platform_admin` vive fora de qualquer tenant (ADR 2.1.0002)."""
    claims = AccessTokenClaims(
        subject=UserId("admin-1"),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
        session_id=SessionId("sess-2"),
        expires_at=_NOW,
    )
    assert claims.tenant_id is None


def test_user_credentials_pareia_usuario_e_hash() -> None:
    """O par existe porque `User` não carrega senha e o login precisa dos dois."""
    user = User(
        id=UserId("user-1"),
        email=Email("dono@x.com"),
        role=Role.OWNER,
        tenant_id=RestaurantId("rest-1"),
    )
    credenciais = UserCredentials(user=user, password_hash=PasswordHash("hashed::s3nha"))
    assert credenciais.user.id == "user-1"
    assert credenciais.password_hash == "hashed::s3nha"

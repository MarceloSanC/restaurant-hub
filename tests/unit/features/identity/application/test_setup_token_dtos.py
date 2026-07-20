"""Testes dos DTOs, commands e erro do token de setup (Stage 2.5, CA4/CA11b/CA14)."""

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    SetPasswordWithTokenCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    IssuedSetupToken,
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import InvalidSetupTokenError
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId

_AGORA = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _token(
    *,
    expires_at: datetime | None = None,
    consumed_at: datetime | None = None,
    purpose: SetupTokenPurpose = SetupTokenPurpose.INVITATION,
) -> PasswordSetupToken:
    return PasswordSetupToken(
        id=SetupTokenId("tok-1"),
        user_id=UserId("user-1"),
        purpose=purpose,
        token_fingerprint="fp-1",
        issued_at=_AGORA,
        expires_at=expires_at if expires_at is not None else _AGORA + timedelta(hours=72),
        consumed_at=consumed_at,
    )


class TestIsUsable:
    """CA4 — a fronteira é half-open, e o consumo é terminal."""

    def test_usavel_antes_de_expirar(self) -> None:
        assert _token().is_usable(_AGORA) is True

    def test_nao_usavel_exatamente_no_instante_da_expiracao(self) -> None:
        """`now == expires_at` já expirou — mesma convenção de `Session.is_active`.

        É o instante em que um `<=` no lugar do `<` passaria despercebido, e é
        por isso que ele tem teste próprio.
        """
        expira = _AGORA + timedelta(hours=1)

        assert _token(expires_at=expira).is_usable(expira) is False

    def test_nao_usavel_depois_de_expirar(self) -> None:
        expira = _AGORA + timedelta(hours=1)

        assert _token(expires_at=expira).is_usable(expira + timedelta(seconds=1)) is False

    def test_nao_usavel_depois_de_consumido(self) -> None:
        assert _token(consumed_at=_AGORA).is_usable(_AGORA) is False

    def test_consumido_e_terminal_mesmo_dentro_do_prazo(self) -> None:
        token = _token(expires_at=_AGORA + timedelta(days=30), consumed_at=_AGORA)

        assert token.is_usable(_AGORA + timedelta(days=1)) is False


class TestIssuedSetupToken:
    def test_valor_nao_aparece_no_repr(self) -> None:
        """O repr default imprimiria a credencial em qualquer traceback."""
        emitido = IssuedSetupToken(value="segredo-do-token", fingerprint="fp-1")

        assert "segredo-do-token" not in repr(emitido)
        assert "fp-1" in repr(emitido)


class TestSetPasswordWithTokenCommand:
    def test_nao_carrega_identificador_de_usuario(self) -> None:
        """CA11b parte 1 — a ausência do campo é a defesa (concept §5 regra 10).

        Se o command tivesse `user_id`, alguém acabaria por lê-lo, e quem tivesse
        um token legítimo da própria conta definiria a senha de outra pessoa. O
        teste falha no instante em que o campo aparecer.
        """
        nomes = {campo.name for campo in dataclasses.fields(SetPasswordWithTokenCommand)}

        assert nomes == {"token", "plain_password"}

    def test_nem_token_nem_senha_aparecem_no_repr(self) -> None:
        comando = SetPasswordWithTokenCommand(token="token-vivo", plain_password="senha-em-claro")

        assert "token-vivo" not in repr(comando)
        assert "senha-em-claro" not in repr(comando)


class TestInvalidSetupTokenError:
    def test_mensagem_e_constante(self) -> None:
        """CA14 — a mensagem não pode variar com a causa nem carregar segredo."""
        assert str(InvalidSetupTokenError()) == str(InvalidSetupTokenError())

    @pytest.mark.parametrize(
        "proibido",
        ["fingerprint", "expir", "usuário", "usuario", "token de definição de senha inválido"],
    )
    def test_mensagem_nao_revela_a_causa(self, proibido: str) -> None:
        """A única string aceita é a genérica; qualquer pista de causa é oráculo."""
        mensagem = str(InvalidSetupTokenError())

        if proibido == "token de definição de senha inválido":
            assert mensagem == proibido
        else:
            assert proibido not in mensagem

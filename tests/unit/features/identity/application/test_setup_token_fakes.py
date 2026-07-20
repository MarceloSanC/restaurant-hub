"""Testes dos fakes do token de setup (Stage 2.5, CA5 lado fake).

Os fakes são a especificação executável dos adapters. Se a semântica do `consume`
condicional não for asserida **aqui**, o teste de replay dos use cases fica verde
sobre um fake permissivo, e a divergência só aparece contra o Postgres.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash, SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import UserNotFoundError
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
    SetupTokenAlreadyExistsError,
)
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

_AGORA = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_DEPOIS = _AGORA + timedelta(minutes=5)


# `noqa: PLR0913` — é uma fábrica de fixture, não uma função de produção: cada
# parâmetro corresponde a uma coluna do registro, e agrupá-los num objeto de
# opções só empurraria a mesma lista para outro lugar, com mais cerimônia.
def _token(  # noqa: PLR0913
    token_id: str = "tok-1",
    *,
    user_id: str = "user-1",
    purpose: SetupTokenPurpose = SetupTokenPurpose.INVITATION,
    fingerprint: str | None = None,
    expires_at: datetime | None = None,
    consumed_at: datetime | None = None,
) -> PasswordSetupToken:
    return PasswordSetupToken(
        id=SetupTokenId(token_id),
        user_id=UserId(user_id),
        purpose=purpose,
        token_fingerprint=fingerprint if fingerprint is not None else f"fp::{token_id}",
        issued_at=_AGORA,
        expires_at=expires_at if expires_at is not None else _AGORA + timedelta(hours=72),
        consumed_at=consumed_at,
    )


class TestFakeSetupTokenIssuer:
    def test_lei_do_port_vale_por_construcao(self) -> None:
        issuer = FakeSetupTokenIssuer()

        emitido = issuer.issue()

        assert issuer.fingerprint(emitido.value) == emitido.fingerprint

    def test_duas_emissoes_produzem_valores_distintos(self) -> None:
        issuer = FakeSetupTokenIssuer()

        primeiro, segundo = issuer.issue(), issuer.issue()

        assert primeiro.value != segundo.value
        assert primeiro.fingerprint != segundo.fingerprint

    def test_fingerprint_e_deterministico(self) -> None:
        issuer = FakeSetupTokenIssuer()

        assert issuer.fingerprint("abc") == issuer.fingerprint("abc")


class TestConsumeCondicional:
    """CA5 (fake) — o booleano do `consume` é o contrato de uso único."""

    def test_primeira_chamada_devolve_true(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token())

        assert repo.consume(SetupTokenId("tok-1"), _AGORA) is True

    def test_segunda_chamada_devolve_false(self) -> None:
        """O replay perde. Sem esta linha, o uso único não existe."""
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token())
        repo.consume(SetupTokenId("tok-1"), _AGORA)

        assert repo.consume(SetupTokenId("tok-1"), _DEPOIS) is False

    def test_segunda_chamada_preserva_o_instante_do_primeiro_consumo(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token())
        repo.consume(SetupTokenId("tok-1"), _AGORA)
        repo.consume(SetupTokenId("tok-1"), _DEPOIS)

        assert repo.tokens[SetupTokenId("tok-1")].consumed_at == _AGORA

    def test_token_inexistente_devolve_false_sem_levantar(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()

        assert repo.consume(SetupTokenId("nao-existe"), _AGORA) is False


class TestFindByFingerprintNaoFiltra:
    def test_encontra_token_ja_consumido(self) -> None:
        """Filtrar tornaria um token usado indistinguível de um forjado."""
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token(consumed_at=_AGORA))

        assert repo.find_by_fingerprint("fp::tok-1") is not None

    def test_encontra_token_expirado(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token(expires_at=_AGORA - timedelta(hours=1)))

        assert repo.find_by_fingerprint("fp::tok-1") is not None

    def test_fingerprint_desconhecido_devolve_none(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()

        assert repo.find_by_fingerprint("fp::inexistente") is None


class TestInvalidateAllForUser:
    def test_com_proposito_nao_toca_no_outro_proposito(self) -> None:
        """CA13 — o escopo por propósito é o que impede a negação de serviço.

        Sem ele, a rota **pública** de redefinição de senha mataria o convite
        pendente de qualquer vítima, em laço, indefinidamente.
        """
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token("convite", purpose=SetupTokenPurpose.INVITATION))
        repo.add(_token("reset", purpose=SetupTokenPurpose.PASSWORD_RESET))

        invalidados = repo.invalidate_all_for_user(
            UserId("user-1"), _AGORA, purpose=SetupTokenPurpose.PASSWORD_RESET
        )

        assert invalidados == 1
        assert repo.tokens[SetupTokenId("convite")].consumed_at is None
        assert repo.tokens[SetupTokenId("reset")].consumed_at == _AGORA

    def test_sem_proposito_atinge_todos(self) -> None:
        """Na redenção o escopo some: nada do usuário sobrevive à troca de senha."""
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token("convite", purpose=SetupTokenPurpose.INVITATION))
        repo.add(_token("reset", purpose=SetupTokenPurpose.PASSWORD_RESET))

        invalidados = repo.invalidate_all_for_user(UserId("user-1"), _AGORA)

        esperado = 2
        assert invalidados == esperado
        assert all(token.consumed_at == _AGORA for token in repo.tokens.values())

    def test_nao_toca_em_token_de_outro_usuario(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token("meu", user_id="user-1"))
        repo.add(_token("alheio", user_id="user-2"))

        repo.invalidate_all_for_user(UserId("user-1"), _AGORA)

        assert repo.tokens[SetupTokenId("alheio")].consumed_at is None

    def test_nao_reescreve_consumo_ja_gravado(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token(consumed_at=_AGORA))

        invalidados = repo.invalidate_all_for_user(UserId("user-1"), _DEPOIS)

        assert invalidados == 0
        assert repo.tokens[SetupTokenId("tok-1")].consumed_at == _AGORA

    def test_invalida_token_expirado_e_nao_consumido(self) -> None:
        """Regra 4 do port — o predicado é `consumed_at IS NULL`, sem expiração.

        Este é o caso que fake e adapter Postgres discordariam em silêncio: sob a
        leitura "só os que ainda valem", o retorno seria 1 em vez de 2. Como o
        retorno é observável e a CA13 assere sobre ele, a fronteira precisa de
        teste próprio — senão o adapter da Task 08 pode escolher a outra leitura
        com o contrato inteiro verde.
        """
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token("expirado", expires_at=_AGORA - timedelta(hours=1)))
        repo.add(_token("vivo", fingerprint="fp::vivo"))

        invalidados = repo.invalidate_all_for_user(UserId("user-1"), _AGORA)

        esperado = 2
        assert invalidados == esperado
        assert repo.tokens[SetupTokenId("expirado")].consumed_at == _AGORA

    def test_usuario_sem_token_devolve_zero(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()

        assert repo.invalidate_all_for_user(UserId("ninguem"), _AGORA) == 0


class TestAddEPurge:
    def test_id_repetido_levanta(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token())

        with pytest.raises(SetupTokenAlreadyExistsError):
            repo.add(_token())

    def test_fingerprint_repetido_levanta(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token("tok-1", fingerprint="mesmo"))

        with pytest.raises(SetupTokenAlreadyExistsError):
            repo.add(_token("tok-2", fingerprint="mesmo"))

    def test_purge_e_inclusivo_na_fronteira(self) -> None:
        """Mesma fronteira half-open de `is_usable`: em `expires_at == before`
        o token já expirou, logo tem de ser expurgável."""
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token(expires_at=_AGORA))

        assert repo.purge_expired(_AGORA) == 1
        assert repo.tokens == {}

    def test_purge_preserva_token_ainda_valido(self) -> None:
        repo = InMemoryPasswordSetupTokenRepository()
        repo.add(_token(expires_at=_AGORA + timedelta(seconds=1)))

        assert repo.purge_expired(_AGORA) == 0


class TestSetPasswordHashNoFake:
    """O fake do `UserRepository` precisa recusar o que o Postgres recusa.

    Se o fake criasse a credencial órfã em silêncio, o teste de "token cujo
    usuário foi apagado" passaria verde sobre um caminho que, no banco, levanta.
    """

    def test_troca_o_hash_de_usuario_existente(self) -> None:
        repo = InMemoryUserRepository()
        usuario = User(
            id=UserId("user-1"),
            email=Email("a@x.com"),
            role=Role.OWNER,
            tenant_id=RestaurantId("rest-a"),
        )
        repo.add(usuario, PasswordHash("hashed::antiga"))

        repo.set_password_hash(UserId("user-1"), PasswordHash("hashed::nova"))

        credenciais = repo.find_credentials_by_email(Email("a@x.com"))
        assert credenciais is not None
        assert credenciais.password_hash == "hashed::nova"

    def test_usuario_inexistente_levanta_e_nao_grava(self) -> None:
        repo = InMemoryUserRepository()

        with pytest.raises(UserNotFoundError):
            repo.set_password_hash(UserId("fantasma"), PasswordHash("hashed::x"))

        assert UserId("fantasma") not in repo.password_hashes

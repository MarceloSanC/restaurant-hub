"""Testes dos fakes de segurança e dos fakes de ports compartilhados.

O alvo principal é a **lei do `TokenIssuer`**: emissão e consulta precisam
derivar o mesmo fingerprint. É uma daquelas regras cuja violação não quebra nada
localmente — cada metade parece certa — e só aparece na 2.4, como "nenhum refresh
token jamais é encontrado".
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def test_hash_e_verify_casam() -> None:
    hasher = FakePasswordHasher()
    password_hash = hasher.hash("s3nha")

    assert hasher.verify("s3nha", password_hash) is True


def test_verify_rejeita_senha_errada() -> None:
    hasher = FakePasswordHasher()

    assert hasher.verify("outra", hasher.hash("s3nha")) is False


def test_verify_nunca_levanta_com_hash_malformado() -> None:
    """Lei 1 do port: hash inválido é `False`, não exceção.

    Um argon2 cru levantaria `InvalidHash` aqui, e a exceção viraria 500 no lugar
    de um 401 — por isso a lei pertence ao contrato, não ao adapter.
    """
    hasher = FakePasswordHasher()

    for malformado in ("", "nao-e-um-hash", "$argon2id$truncado"):
        assert hasher.verify("s3nha", PasswordHash(malformado)) is False


def test_dummy_hash_e_inatingivel_por_qualquer_senha() -> None:
    """Lei 2 do port — é o que permite equalizar o tempo do login sem autenticar."""
    hasher = FakePasswordHasher()
    dummy = hasher.dummy_hash()

    for tentativa in ("s3nha", "", "dummy::inatingivel", "inatingivel"):
        assert hasher.verify(tentativa, dummy) is False


def test_hasher_conta_verificacoes() -> None:
    """O contador sustenta o CA7 (verify também no caminho de e-mail inexistente)."""
    hasher = FakePasswordHasher()
    assert hasher.verify_calls == 0

    tentativas = [("s3nha", hasher.hash("s3nha")), ("x", hasher.dummy_hash())]
    for plain, password_hash in tentativas:
        hasher.verify(plain, password_hash)

    assert hasher.verify_calls == len(tentativas)


def test_lei_do_token_issuer_fingerprint_do_valor_emitido_bate() -> None:
    """`fingerprint(t.value) == t.fingerprint` — a lei do port, testada de fato.

    Comparar `t.fingerprint` consigo mesmo passaria mesmo com um adapter que
    derivasse o fingerprint de dois jeitos diferentes. Aqui recomputamos a partir
    do valor, que é o caminho que a 2.4 percorre ao procurar a sessão.
    """
    issuer = FakeTokenIssuer()

    emitido = issuer.issue_refresh_token()

    assert issuer.fingerprint(emitido.value) == emitido.fingerprint


def test_refresh_tokens_emitidos_sao_distintos() -> None:
    """Dois logins não podem compartilhar refresh token — nem no fake."""
    issuer = FakeTokenIssuer()

    primeiro = issuer.issue_refresh_token()
    segundo = issuer.issue_refresh_token()

    assert primeiro.value != segundo.value
    assert primeiro.fingerprint != segundo.fingerprint


def test_fingerprint_e_deterministico_e_diferente_do_valor() -> None:
    issuer = FakeTokenIssuer()

    assert issuer.fingerprint("abc") == issuer.fingerprint("abc")
    assert issuer.fingerprint("abc") != "abc"


def test_access_token_registra_as_claims_emitidas() -> None:
    issuer = FakeTokenIssuer()
    claims = AccessTokenClaims(
        subject=UserId("user-1"),
        role=Role.OWNER,
        tenant_id=RestaurantId("rest-1"),
        session_id=SessionId("sess-1"),
        expires_at=_NOW,
    )

    token = issuer.issue_access_token(claims)

    assert "user-1" in token
    assert issuer.issued_claims == [claims]


def test_decode_inverte_a_emissao() -> None:
    """Round-trip do port estendido (Stage 2.4, ADR 2.4.0002).

    A lei é `decode(issue(c)) == c`. O fake a honra guardando o que emitiu, em
    vez de reconstruir claims a partir do texto do token — reconstruir seria uma
    segunda implementação, capaz de divergir da primeira em silêncio.
    """
    # Relógio injetado: `_NOW` é uma data fixa do passado, e o fake agora expira
    # de verdade. Sem controlar o relógio, este teste passaria a medir o
    # calendário em vez do round-trip.
    issuer = FakeTokenIssuer(clock=FakeClock(_NOW))
    claims = AccessTokenClaims(
        subject=UserId("user-1"),
        role=Role.MANAGER,
        tenant_id=RestaurantId("rest-1"),
        session_id=SessionId("sess-1"),
        expires_at=_NOW + timedelta(minutes=15),
    )

    assert issuer.decode_access_token(issuer.issue_access_token(claims)) == claims


def test_decode_preserva_tenant_nulo_de_platform_admin() -> None:
    """`tenant_id=None` é estado legítimo, não ausência de dado (ADR 2.1.0002).

    Um decode que colapsasse `None` numa string vazia quebraria a invariante de
    `User` no outro lado do round-trip.
    """
    issuer = FakeTokenIssuer(clock=FakeClock(_NOW))
    claims = AccessTokenClaims(
        subject=UserId("admin-1"),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
        session_id=SessionId("sess-9"),
        expires_at=_NOW + timedelta(minutes=15),
    )

    assert issuer.decode_access_token(issuer.issue_access_token(claims)).tenant_id is None


def test_decode_recusa_token_nao_emitido_por_este_emissor() -> None:
    """Token forjado com o formato certo não passa.

    No adapter real quem barra é a assinatura; no fake, o não-reconhecimento. A
    exceção precisa ser a mesma, senão o contrato fake≡real não vale.
    """
    issuer = FakeTokenIssuer()

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode_access_token("access::user-1::sess-1")


def test_decode_recusa_token_expirado() -> None:
    """O fake expira de verdade, com relógio injetado.

    Antes ele só checava se reconhecia o valor, e aceitava token vencido para
    sempre — divergindo do adapter real justamente na metade da lei que o guard
    HTTP delega inteiramente ao issuer.
    """
    clock = FakeClock(_NOW)
    issuer = FakeTokenIssuer(clock=clock)
    token = issuer.issue_access_token(
        AccessTokenClaims(
            subject=UserId("user-1"),
            role=Role.EMPLOYEE,
            tenant_id=RestaurantId("rest-1"),
            session_id=SessionId("sess-1"),
            expires_at=_NOW + timedelta(minutes=15),
        )
    )
    assert issuer.decode_access_token(token).subject == UserId("user-1")

    clock.advance(timedelta(minutes=15))

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode_access_token(token)


def test_fake_clock_fica_parado_e_avanca_sob_demanda() -> None:
    clock = FakeClock(_NOW)
    assert clock.now() == _NOW

    clock.advance(timedelta(hours=2))

    assert clock.now() == _NOW + timedelta(hours=2)


def test_fake_id_generator_gera_sequencia_previsivel() -> None:
    generator = FakeIdGenerator()

    primeiro = generator.next_id()
    segundo = generator.next_id()

    assert primeiro == UUID(int=1)
    assert segundo == UUID(int=2)
    assert generator.generated == [primeiro, segundo]


def test_fake_id_generator_aceita_sequencia_pre_definida() -> None:
    """Permite fixar o id de cada agregado quando o teste precisa nomeá-los."""
    esperado = UUID("11111111-1111-1111-1111-111111111111")
    generator = FakeIdGenerator([esperado])

    assert generator.next_id() == esperado
    assert generator.next_id() == UUID(int=1)

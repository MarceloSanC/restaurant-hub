"""Contrato dos dois ports de segurança — CA8 e CA9.

**Cada teste deste arquivo roda duas vezes**, com o **mesmo corpo**: contra o fake
determinístico e contra o adapter real (argon2id / JWT). É a mesma mecânica que a
Stage 2.3 aplicou aos repositórios, agora sobre `PasswordHasher` e `TokenIssuer`.

O motivo é específico e vale explicitar. Os fakes de segurança são triviais de
fazer passar por acidente: `hashed::<senha>` sempre "verifica", e um
`decode` que reconstruísse claims do texto sempre "bate". Um fake assim satisfaz
todo teste unitário da 2.2 e mesmo assim mente sobre o port — e a mentira só
apareceria em produção, no primeiro login real. Rodar as **leis** contra as duas
implementações é o que impede isso.

Fora do contrato, por decisão explícita: os ganchos que só existem no fake e não
pertencem ao port — `invalidar()` e `issued_claims` do `FakeTokenIssuer`,
`verify_calls`/`verify_args` do `FakePasswordHasher`. São instrumentação de teste;
exigi-los do adapter real seria inventar requisito.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.adapters.out.security.jwt_issuer import (
    JwtTokenIssuer,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer

pytestmark = pytest.mark.contract

_SENHA = "s3nha-de-contrato"
# >= 32 bytes (RFC 7518 §3.2).
_SEGREDO = "segredo-de-contrato-com-32-bytes-ou-+"


@pytest.fixture(params=["fake", "argon2"])
def hasher(request: pytest.FixtureRequest) -> PasswordHasher:
    """O mesmo corpo de teste, as duas implementações do port."""
    if request.param == "fake":
        return FakePasswordHasher()
    return Argon2PasswordHasher()


@pytest.fixture(params=["fake", "jwt"])
def issuer(request: pytest.FixtureRequest) -> Iterator[TokenIssuer]:
    if request.param == "fake":
        yield FakeTokenIssuer()
    else:
        yield JwtTokenIssuer(secret_key=_SEGREDO)


# ---------------------------------------------------------------------------
# PasswordHasher — as duas leis do port
# ---------------------------------------------------------------------------


def test_hash_e_verify_casam(hasher: PasswordHasher) -> None:
    assert hasher.verify(_SENHA, hasher.hash(_SENHA)) is True


def test_verify_rejeita_senha_errada(hasher: PasswordHasher) -> None:
    assert hasher.verify("senha-errada", hasher.hash(_SENHA)) is False


@pytest.mark.parametrize(
    "degenerado",
    ["", "nao-e-um-hash", "$argon2id$truncado", "$2b$12$bcrypt-de-outro-algoritmo"],
)
def test_lei_1_verify_nunca_levanta(hasher: PasswordHasher, degenerado: str) -> None:
    """Lei 1 — hash inválido devolve `False`, jamais exceção.

    É a lei que impede um 500 no login. O argon2 cru levanta `InvalidHashError`
    para cada uma destas entradas; se o adapter deixasse escapar, um registro
    corrompido derrubaria a requisição em vez de recusá-la — e a diferença entre
    500 e 401 diria ao atacante que aquela conta é diferente das outras.
    """
    assert hasher.verify(_SENHA, PasswordHash(degenerado)) is False


@pytest.mark.parametrize("tentativa", ["", _SENHA, "dummy", "admin"])
def test_lei_2_dummy_hash_e_inatingivel(hasher: PasswordHasher, tentativa: str) -> None:
    """Lei 2 — nenhuma senha autentica contra o dummy.

    É o hash contra o qual `authenticate_user` verifica quando o e-mail não
    existe, para pagar o mesmo custo do caminho "senha errada" e não vazar a
    existência da conta pelo relógio.
    """
    assert hasher.verify(tentativa, hasher.dummy_hash()) is False


def test_lei_2_dummy_hash_e_estavel(hasher: PasswordHasher) -> None:
    """O dummy não muda entre chamadas — as duas implementações concordam nisso."""
    assert hasher.dummy_hash() == hasher.dummy_hash()


# ---------------------------------------------------------------------------
# TokenIssuer — lei do fingerprint e lei da decodificação verificada
# ---------------------------------------------------------------------------


def test_lei_do_fingerprint(issuer: TokenIssuer) -> None:
    """`issuer.fingerprint(t.value) == t.fingerprint`.

    Asserida via `fingerprint(...)`, e não por igualdade de campo, porque é essa
    formulação que pega a implementação que derivasse o fingerprint de um jeito
    na emissão e de outro na consulta. As duas metades pareceriam corretas
    isoladamente e **toda** busca de sessão falharia.
    """
    emitido = issuer.issue_refresh_token()

    assert issuer.fingerprint(emitido.value) == emitido.fingerprint


def test_fingerprint_e_deterministico(issuer: TokenIssuer) -> None:
    assert issuer.fingerprint("valor-x") == issuer.fingerprint("valor-x")
    assert issuer.fingerprint("valor-x") != issuer.fingerprint("valor-y")


def test_refresh_tokens_sao_distintos(issuer: TokenIssuer) -> None:
    primeiro = issuer.issue_refresh_token()
    segundo = issuer.issue_refresh_token()

    assert primeiro.value != segundo.value
    assert primeiro.fingerprint != segundo.fingerprint


@pytest.mark.parametrize(
    ("role", "tenant_id"),
    [
        (Role.OWNER, RestaurantId("rest-1")),
        (Role.EMPLOYEE, RestaurantId("rest-2")),
        # `None` é o tenant legítimo do platform_admin (ADR 2.1.0002), não dado
        # ausente. Uma implementação que o colapsasse em "" quebraria a
        # invariante de `User` do outro lado do round-trip.
        (Role.PLATFORM_ADMIN, None),
    ],
)
def test_lei_do_round_trip_de_claims(
    issuer: TokenIssuer,
    role: Role,
    tenant_id: RestaurantId | None,
) -> None:
    """`decode(issue(c))` devolve `c`, nas duas implementações."""
    claims = AccessTokenClaims(
        subject=UserId("user-1"),
        role=role,
        tenant_id=tenant_id,
        session_id=SessionId("sess-1"),
        # Segundo cheio: o `exp` do JWT tem resolução de segundo, e um instante
        # com microssegundos faria o round-trip real perder precisão — o fake
        # não perderia, e o teste passaria a distinguir as implementações por um
        # detalhe que o port não promete.
        expires_at=(datetime.now(UTC) + timedelta(minutes=15)).replace(microsecond=0),
    )

    assert issuer.decode_access_token(issuer.issue_access_token(claims)) == claims


def test_lei_da_decodificacao_recusa_token_nao_emitido(issuer: TokenIssuer) -> None:
    """Token que este emissor não produziu não atravessa.

    No adapter real quem barra é a assinatura; no fake, o não-reconhecimento do
    valor. O contrato exige que a **exceção seja a mesma** — se divergisse, o
    guard HTTP trataria os dois casos de formas diferentes conforme a montagem.
    """
    with pytest.raises(InvalidAccessTokenError):
        issuer.decode_access_token("token-que-ninguem-emitiu")

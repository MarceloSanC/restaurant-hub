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
pertencem ao port — `issued_claims` do `FakeTokenIssuer`,
`verify_calls`/`verify_args` do `FakePasswordHasher`. São instrumentação de teste;
exigi-los do adapter real seria inventar requisito.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    _DUMMY_SENTINEL,
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.adapters.out.security.jwt_issuer import (
    JwtTokenIssuer,
)
from restaurant_hub.features.identity.adapters.out.security.setup_token_issuer import (
    Sha256SetupTokenIssuer,
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
from restaurant_hub.features.identity.application.ports.out.setup_token_issuer import (
    SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
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
    [
        "",
        "nao-e-um-hash",
        "$argon2id$truncado",
        "$2b$12$bcrypt-de-outro-algoritmo",
        # Nao-ASCII: o argon2 real faz hash.encode("ascii") antes de qualquer
        # coisa, levantando UnicodeEncodeError fora da sua propria hierarquia.
        "$argon2id$café",
    ],
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
    """O dummy não muda entre chamadas — as duas implementações concordam nisso.

    Estabilidade é **obrigatória** aqui e **proibida** em `unusable_hash()`, e o
    contraste não é acidente: recomputar o dummy faria o caminho "e-mail
    inexistente" pagar dois KDFs contra um do caminho "senha errada", reabrindo
    pelo relógio o oráculo que a lei 2 fecha.
    """
    assert hasher.dummy_hash() == hasher.dummy_hash()


# ---------------------------------------------------------------------------
# unusable_hash — o hash de uma conta convidada que ainda não definiu senha
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tentativa",
    [
        "",
        _SENHA,
        "admin",
        # **A senha que importa.** `dummy_hash()` é o hash desta string literal,
        # que está no código-fonte; se `unusable_hash()` fosse "simplificado"
        # para devolver o dummy, qualquer pessoa faria login como qualquer
        # convidado que ainda não ativou a conta. Este parâmetro é o que impede
        # a regressão, e é por isso que ele é nomeado e não genérico
        # (ADR 2.5.0004).
        _DUMMY_SENTINEL,
    ],
)
def test_lei_1_unusable_hash_nao_autentica_nenhuma_senha(
    hasher: PasswordHasher, tentativa: str
) -> None:
    """Lei 1 de `unusable_hash` — nenhuma senha conhecida verifica contra ele."""
    assert hasher.verify(tentativa, hasher.unusable_hash()) is False


def test_lei_2_unusable_hash_muda_a_cada_chamada(hasher: PasswordHasher) -> None:
    """Lei 2 — dois convidados não compartilham a mesma string no banco.

    Um valor constante entregaria, a quem tem leitura em `users`, a lista exata
    das contas que ainda não foram ativadas — o conjunto de alvos mais valioso
    do sistema, e justamente aquele para o qual a lei 1 é a única defesa.
    """
    assert hasher.unusable_hash() != hasher.unusable_hash()


def test_unusable_hash_nao_e_o_dummy_hash(hasher: PasswordHasher) -> None:
    """A distinção entre os dois métodos é asserida, não confiada à leitura.

    Se alguém apontar `unusable_hash` para `dummy_hash` — o "simplifiquei, era a
    mesma coisa" que o ADR 2.5.0004 existe para impedir —, este teste falha
    antes de o código chegar ao banco.
    """
    assert hasher.unusable_hash() != hasher.dummy_hash()


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


def test_lei_da_decodificacao_recusa_token_expirado(issuer: TokenIssuer) -> None:
    """Verificar é assinatura **e** expiração — a metade que um fake esquece.

    Esta lei entrou no contrato depois de o fake ser pego aceitando
    indefinidamente um token vencido, enquanto o adapter real o recusava. A
    divergência importa porque o guard HTTP delega a expiração inteiramente ao
    issuer: um teste de guard escrito com o fake permissivo passaria verde sobre
    um sistema que não expira nada, e o TTL de 15 minutos — que é a janela de
    revogação inteira do produto — seria decorativo.
    """
    claims = AccessTokenClaims(
        subject=UserId("user-1"),
        role=Role.OWNER,
        tenant_id=RestaurantId("rest-1"),
        session_id=SessionId("sess-1"),
        expires_at=(datetime.now(UTC) - timedelta(seconds=1)).replace(microsecond=0),
    )
    token = issuer.issue_access_token(claims)

    with pytest.raises(InvalidAccessTokenError):
        issuer.decode_access_token(token)


# ---------------------------------------------------------------------------
# SetupTokenIssuer — a mesma lei do fingerprint, num port deliberadamente separado
# ---------------------------------------------------------------------------


@pytest.fixture(params=["fake", "sha256"])
def setup_issuer(request: pytest.FixtureRequest) -> SetupTokenIssuer:
    """Fake e adapter real respondem à mesma bateria.

    O port é separado do `TokenIssuer` de propósito (ADR 2.5.0002), mas a lei do
    fingerprint é a mesma — e é a lei que, se quebrada, faz **toda** redenção de
    token falhar com as duas metades parecendo corretas isoladamente.
    """
    if request.param == "fake":
        return FakeSetupTokenIssuer()
    return Sha256SetupTokenIssuer()


def test_lei_do_fingerprint_do_setup_token(setup_issuer: SetupTokenIssuer) -> None:
    """`issuer.fingerprint(t.value) == t.fingerprint`, via o método."""
    emitido = setup_issuer.issue()

    assert setup_issuer.fingerprint(emitido.value) == emitido.fingerprint


def test_setup_token_muda_a_cada_emissao(setup_issuer: SetupTokenIssuer) -> None:
    """Dois convites não podem compartilhar o mesmo link."""
    assert setup_issuer.issue().value != setup_issuer.issue().value


def test_fingerprint_do_setup_token_e_deterministico(setup_issuer: SetupTokenIssuer) -> None:
    """Sem determinismo, a redenção não acha o registro que a emissão gravou."""
    assert setup_issuer.fingerprint("valor-x") == setup_issuer.fingerprint("valor-x")


def test_fingerprint_do_setup_token_nao_devolve_o_proprio_valor(
    setup_issuer: SetupTokenIssuer,
) -> None:
    """Um "fingerprint" igual ao valor faria o banco guardar o token utilizável."""
    assert setup_issuer.fingerprint("valor-x") != "valor-x"

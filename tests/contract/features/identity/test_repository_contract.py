"""Contrato dos quatro ports-out de identity — CA16.

**Cada teste deste arquivo roda duas vezes**: contra o fake in-memory e contra o
adapter PostgreSQL, com o **mesmo corpo**. É o que a Stage 2.2 encomendou à 2.3
para fechar o risco que ela registrou: "fake e futuro adapter Postgres divergirem
no contrato".

O valor está no que o teste **não** faz: não sabe qual implementação está usando,
não tem `if`, não tem variante. Um comportamento que difira entre as duas aparece
como o mesmo teste passando em `[fake]` e falhando em `[postgres]`.

Divergências que esta suíte já pegou (todas corrigidas na Stage 2.3, e todas
invisíveis para quem só rodasse os testes unitários da 2.2):

- os quatro fakes faziam upsert silencioso onde a PK do Postgres rejeita;
- o fake de usuário aceitava re-gravar o mesmo id, com um teste da 2.2 afirmando
  que isso era correto — contra o docstring do próprio port;
- vínculos repetidos eram acumulados pelo fake e rejeitados pela PK composta.

Fora do contrato, por decisão explícita (CA16): os ganchos que só existem no fake
e não pertencem ao port — `seed_membership`, `list_all_memberships`,
`leak_foreign_memberships` e os contadores `find_calls`. São instrumentação de
teste; exigi-los do adapter real seria inventar requisito.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantAlreadyExistsError,
    SessionAlreadyExistsError,
    SessionFingerprintAlreadyExistsError,
    UnitAlreadyExistsError,
    UserAlreadyExistsError,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from tests.contract.features.identity.conftest import Repositorios

pytestmark = pytest.mark.contract

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_TTL = timedelta(days=7)
_HASH = PasswordHash("hashed::s3nha")


def _semear_tenant(repos: Repositorios, tenant: str = "rest-a", unidade: str = "unit-a1") -> None:
    """Pré-requisitos de FK, criados pelos próprios ports.

    Semear pelos ports (e não por SQL) é o que mantém o corpo do teste idêntico
    para as duas implementações — o fake apenas guarda, o Postgres também satisfaz
    as chaves estrangeiras.
    """
    repos.restaurantes.add(Restaurant(id=RestaurantId(tenant), name="Cantina"))
    repos.unidades.add(Unit(id=UnitId(unidade), restaurant_id=RestaurantId(tenant), name="Centro"))


def _user(
    user_id: str = "user-1",
    email: str = "dono@x.com",
    tenant: str | None = "rest-a",
    role: Role = Role.OWNER,
) -> User:
    return User(
        id=UserId(user_id),
        email=Email(email),
        role=role,
        tenant_id=RestaurantId(tenant) if tenant is not None else None,
    )


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
# RestaurantRepository
# ---------------------------------------------------------------------------


def test_restaurante_round_trip(repos: Repositorios) -> None:
    repos.restaurantes.add(Restaurant(id=RestaurantId("rest-a"), name="  Cantina  "))

    lido = repos.restaurantes.find_by_id(RestaurantId("rest-a"))

    assert lido is not None
    assert lido.id == "rest-a"
    # `name` verbatim nas duas implementações (ADR 2.3.0005).
    assert lido.name == "  Cantina  "


def test_restaurante_inexistente_devolve_none(repos: Repositorios) -> None:
    assert repos.restaurantes.find_by_id(RestaurantId("fantasma")) is None


def test_restaurante_duplicado_levanta(repos: Repositorios) -> None:
    """Divergência histórica: o fake sobrescrevia; o Postgres rejeitava."""
    repos.restaurantes.add(Restaurant(id=RestaurantId("rest-a"), name="Cantina"))

    with pytest.raises(RestaurantAlreadyExistsError):
        repos.restaurantes.add(Restaurant(id=RestaurantId("rest-a"), name="Outra"))


# ---------------------------------------------------------------------------
# UnitRepository
# ---------------------------------------------------------------------------


def test_unidade_round_trip(repos: Repositorios) -> None:
    _semear_tenant(repos)

    lida = repos.unidades.find_by_id(UnitId("unit-a1"))

    assert lida is not None
    assert lida.id == "unit-a1"
    assert lida.restaurant_id == "rest-a"
    assert lida.name == "Centro"


def test_unidade_inexistente_devolve_none(repos: Repositorios) -> None:
    assert repos.unidades.find_by_id(UnitId("fantasma")) is None


def test_unidade_duplicada_levanta(repos: Repositorios) -> None:
    _semear_tenant(repos)

    with pytest.raises(UnitAlreadyExistsError):
        repos.unidades.add(
            Unit(id=UnitId("unit-a1"), restaurant_id=RestaurantId("rest-a"), name="Praia")
        )


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


def test_usuario_round_trip(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)

    lido = repos.usuarios.find_by_id(UserId("user-1"))

    assert lido is not None
    assert lido.id == "user-1"
    assert lido.email == Email("dono@x.com")
    assert lido.role is Role.OWNER
    assert lido.tenant_id == "rest-a"


def test_usuario_inexistente_devolve_none(repos: Repositorios) -> None:
    assert repos.usuarios.find_by_id(UserId("fantasma")) is None


def test_platform_admin_round_trip_sem_tenant(repos: Repositorios) -> None:
    repos.usuarios.add(_user("adm", "adm@x.com", tenant=None, role=Role.PLATFORM_ADMIN), _HASH)

    lido = repos.usuarios.find_by_id(UserId("adm"))
    assert lido is not None
    assert lido.tenant_id is None


def test_usuario_com_id_duplicado_levanta_erro_de_id(repos: Repositorios) -> None:
    """**A divergência principal que esta Stage foi encomendada para fechar.**

    O fake aceitava re-gravar o mesmo `user_id` (com um teste da 2.2 afirmando que
    era correto), enquanto a PK do Postgres rejeita. O erro é o de **id**, não o de
    e-mail: o e-mail é do próprio usuário.
    """
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)

    with pytest.raises(UserAlreadyExistsError):
        repos.usuarios.add(_user(), _HASH)


def test_email_duplicado_em_outro_tenant_levanta(repos: Repositorios) -> None:
    """Unicidade GLOBAL — um índice por `(tenant_id, email)` passaria batido."""
    _semear_tenant(repos)
    _semear_tenant(repos, tenant="rest-b", unidade="unit-b1")
    repos.usuarios.add(_user("user-1", "dono@x.com", tenant="rest-a"), _HASH)

    with pytest.raises(EmailAlreadyRegisteredError):
        repos.usuarios.add(_user("user-2", "dono@x.com", tenant="rest-b"), _HASH)


def test_exists_by_email_e_global_e_ignora_caixa(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)

    assert repos.usuarios.exists_by_email(Email("dono@x.com")) is True
    assert repos.usuarios.exists_by_email(Email("DONO@X.COM")) is True
    assert repos.usuarios.exists_by_email(Email("ninguem@x.com")) is False


def test_find_credentials_devolve_usuario_e_hash(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)

    credencial = repos.usuarios.find_credentials_by_email(Email("dono@x.com"))

    assert credencial is not None
    assert credencial.user.id == "user-1"
    assert credencial.password_hash == _HASH


def test_find_credentials_de_email_inexistente_devolve_none(repos: Repositorios) -> None:
    assert repos.usuarios.find_credentials_by_email(Email("ninguem@x.com")) is None


def test_vinculos_sao_gravados_com_o_usuario(repos: Repositorios) -> None:
    """Comparação como **conjunto**: ordem não faz parte do contrato.

    O fake devolve em ordem de inserção; SQL sem `ORDER BY` não garante ordem
    nenhuma. Asserir sequência aqui produziria um teste que passa por acidente e
    fica intermitente quando o plano de query mudar.
    """
    _semear_tenant(repos)
    repos.unidades.add(
        Unit(id=UnitId("unit-a2"), restaurant_id=RestaurantId("rest-a"), name="Praia")
    )
    user = _user()
    vinculos = [
        UnitMembership(user_id=user.id, unit_id=UnitId("unit-a1")),
        UnitMembership(user_id=user.id, unit_id=UnitId("unit-a2")),
    ]

    repos.usuarios.add(user, _HASH, vinculos)

    assert set(repos.usuarios.list_memberships(user.id)) == set(vinculos)


def test_usuario_sem_vinculo_devolve_tupla_vazia(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)

    assert repos.usuarios.list_memberships(UserId("user-1")) == ()


# ---------------------------------------------------------------------------
# SessionRepository
# ---------------------------------------------------------------------------


def test_sessao_round_trip_em_utc(repos: Repositorios) -> None:
    """O fuso precisa sobreviver nas duas implementações.

    O fake guarda o objeto e devolve exatamente o que recebeu; o Postgres passa por
    `timestamptz` e volta no fuso da sessão, normalizado pelo mapper. Sem a
    normalização, este teste passaria em `[fake]` e falharia em `[postgres]` fora
    de UTC — que é precisamente o tipo de divergência que a suíte existe para pegar.
    """
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    sessao = _session()

    repos.sessoes.add(sessao)
    lida = repos.sessoes.find_by_fingerprint("fp::abc")

    assert lida is not None
    assert lida.issued_at == sessao.issued_at
    assert lida.expires_at == sessao.expires_at
    assert lida.issued_at.tzinfo is not None
    assert lida.expires_at.utcoffset() == timedelta(0)


def test_find_by_fingerprint_nao_filtra_revogada(repos: Repositorios) -> None:
    """Regra 1 do port: filtrar tornaria reuso de token indetectável na 2.4."""
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session())

    repos.sessoes.revoke(SessionId("sess-1"), _NOW)

    lida = repos.sessoes.find_by_fingerprint("fp::abc")
    assert lida is not None
    assert lida.revoked_at is not None


def test_find_by_fingerprint_nao_filtra_expirada(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session(expires_at=_NOW - timedelta(seconds=1)))

    lida = repos.sessoes.find_by_fingerprint("fp::abc")
    assert lida is not None
    assert lida.is_active(_NOW) is False


def test_find_by_fingerprint_inexistente_devolve_none(repos: Repositorios) -> None:
    assert repos.sessoes.find_by_fingerprint("fp::nada") is None


def test_revogar_duas_vezes_preserva_o_primeiro_instante(repos: Repositorios) -> None:
    """Regra 2 — idempotência forte, nas duas implementações."""
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session())
    primeira = _NOW
    segunda = _NOW + timedelta(hours=1)

    repos.sessoes.revoke(SessionId("sess-1"), primeira)
    repos.sessoes.revoke(SessionId("sess-1"), segunda)

    lida = repos.sessoes.find_by_fingerprint("fp::abc")
    assert lida is not None
    assert lida.revoked_at == primeira


def test_revogar_id_inexistente_nao_levanta(repos: Repositorios) -> None:
    """Regra 3 — no-op silencioso."""
    repos.sessoes.revoke(SessionId("fantasma"), _NOW)


def test_revoke_all_atinge_so_o_usuario_indicado(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user("user-1", "a@x.com"), _HASH)
    repos.usuarios.add(_user("user-2", "b@x.com"), _HASH)
    repos.sessoes.add(_session("sess-1", "user-1", "fp::a"))
    repos.sessoes.add(_session("sess-2", "user-2", "fp::b"))

    repos.sessoes.revoke_all_for_user(UserId("user-1"), _NOW)

    do_um = repos.sessoes.find_by_fingerprint("fp::a")
    do_dois = repos.sessoes.find_by_fingerprint("fp::b")
    assert do_um is not None and do_um.revoked_at == _NOW
    assert do_dois is not None and do_dois.revoked_at is None


def test_sessao_com_id_duplicado_levanta(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session("sess-1", fingerprint="fp::a"))

    with pytest.raises(SessionAlreadyExistsError):
        repos.sessoes.add(_session("sess-1", fingerprint="fp::b"))


def test_fingerprint_duplicado_levanta_erro_proprio(repos: Repositorios) -> None:
    """Erro distinto do de id: fingerprint repetido é sinal de reuso de token."""
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session("sess-1", fingerprint="fp::a"))

    with pytest.raises(SessionFingerprintAlreadyExistsError):
        repos.sessoes.add(_session("sess-2", fingerprint="fp::a"))


def test_purge_expired_usa_fronteira_inclusiva(repos: Repositorios) -> None:
    """`expires_at == before` já expirou — a mesma fronteira de `is_active`."""
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session("sess-borda", fingerprint="fp::borda", expires_at=_NOW))

    assert repos.sessoes.purge_expired(_NOW) == 1
    assert repos.sessoes.find_by_fingerprint("fp::borda") is None


def test_purge_expired_preserva_validas_e_conta_o_removido(repos: Repositorios) -> None:
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session("viva", fingerprint="fp::viva", expires_at=_NOW + _TTL))
    repos.sessoes.add(_session("morta", fingerprint="fp::morta", expires_at=_NOW - _TTL))

    assert repos.sessoes.purge_expired(_NOW) == 1
    assert repos.sessoes.find_by_fingerprint("fp::viva") is not None
    assert repos.sessoes.find_by_fingerprint("fp::morta") is None


def test_purge_expired_poupa_revogada_ainda_nao_expirada(repos: Repositorios) -> None:
    """Expurgo é por expiração, não por revogação — preserva a forense."""
    _semear_tenant(repos)
    repos.usuarios.add(_user(), _HASH)
    repos.sessoes.add(_session(expires_at=_NOW + _TTL))
    repos.sessoes.revoke(SessionId("sess-1"), _NOW)

    assert repos.sessoes.purge_expired(_NOW) == 0
    assert repos.sessoes.find_by_fingerprint("fp::abc") is not None


def test_purge_expired_em_repositorio_vazio_devolve_zero(repos: Repositorios) -> None:
    assert repos.sessoes.purge_expired(_NOW) == 0

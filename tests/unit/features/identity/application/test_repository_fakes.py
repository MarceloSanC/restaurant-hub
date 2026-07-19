"""Testes dos fakes de repositório.

Os fakes são a **especificação executável** que a Stage 2.3 vai reimplementar em
Postgres. Por isso o que se testa aqui não é "o dicionário funciona", e sim as
regras de contrato que o adapter real precisa honrar — sobretudo a unicidade
global de e-mail, que é onde o SQL tende a divergir (um índice único por
`(tenant_id, email)` em vez de por `email` passaria despercebido).
"""

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
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
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

pytestmark = pytest.mark.unit

_HASH = PasswordHash("hashed::s3nha")


def _user(
    user_id: str = "user-1",
    email: str = "dono@x.com",
    tenant: str = "rest-1",
    role: Role = Role.OWNER,
) -> User:
    return User(
        id=UserId(user_id),
        email=Email(email),
        role=role,
        tenant_id=RestaurantId(tenant),
    )


def test_restaurante_faz_round_trip() -> None:
    repo = InMemoryRestaurantRepository()
    restaurante = Restaurant(id=RestaurantId("rest-1"), name="Cantina")

    repo.add(restaurante)

    assert repo.find_by_id(RestaurantId("rest-1")) == restaurante


def test_restaurante_inexistente_devolve_none() -> None:
    assert InMemoryRestaurantRepository().find_by_id(RestaurantId("nao-existe")) is None


def test_unidade_faz_round_trip() -> None:
    repo = InMemoryUnitRepository()
    unidade = Unit(id=UnitId("unit-1"), restaurant_id=RestaurantId("rest-1"), name="Centro")

    repo.add(unidade)

    assert repo.find_by_id(UnitId("unit-1")) == unidade


def test_unidade_inexistente_devolve_none() -> None:
    assert InMemoryUnitRepository().find_by_id(UnitId("nao-existe")) is None


def test_repositorios_contam_leituras() -> None:
    """O contador sustenta o CA4 — provar que uma consulta NÃO aconteceu."""
    repo = InMemoryUnitRepository()
    assert repo.find_calls == 0

    repo.find_by_id(UnitId("unit-1"))

    assert repo.find_calls == 1


def test_usuario_faz_round_trip_com_credencial_e_vinculos() -> None:
    """`add` grava as três coisas de uma vez — na 2.3 elas são a mesma transação."""
    repo = InMemoryUserRepository()
    user = _user()
    vinculo = UnitMembership(user_id=user.id, unit_id=UnitId("unit-1"))

    repo.add(user, _HASH, [vinculo])

    assert repo.find_by_id(user.id) == user
    assert repo.list_memberships(user.id) == (vinculo,)
    credenciais = repo.find_credentials_by_email(Email("dono@x.com"))
    assert credenciais is not None
    assert credenciais.password_hash == _HASH


def test_usuario_pode_ser_gravado_sem_vinculo() -> None:
    repo = InMemoryUserRepository()
    user = _user()

    repo.add(user, _HASH)

    assert repo.list_memberships(user.id) == ()


def test_unicidade_de_email_e_global_e_nao_por_tenant() -> None:
    """Regra de kickoff #2 — e a que o índice do Postgres precisa espelhar na 2.3.

    Um índice único por `(tenant_id, email)` passaria neste cenário e quebraria a
    regra: o mesmo login existiria em dois restaurantes.
    """
    repo = InMemoryUserRepository()
    repo.add(_user(user_id="user-1", email="dono@x.com", tenant="rest-1"), _HASH)

    assert repo.exists_by_email(Email("dono@x.com")) is True


def test_unicidade_de_email_ignora_caixa() -> None:
    """`Email` normaliza no domínio; o índice do fake herda isso de graça."""
    repo = InMemoryUserRepository()
    repo.add(_user(email="dono@x.com"), _HASH)

    assert repo.exists_by_email(Email("DONO@X.COM")) is True


def test_email_nao_registrado_nao_existe_e_nao_tem_credencial() -> None:
    repo = InMemoryUserRepository()

    assert repo.exists_by_email(Email("ninguem@x.com")) is False
    assert repo.find_credentials_by_email(Email("ninguem@x.com")) is None


def test_list_memberships_devolve_apenas_os_do_usuario_por_padrao() -> None:
    repo = InMemoryUserRepository()
    meu = UnitMembership(user_id=UserId("user-1"), unit_id=UnitId("unit-1"))
    alheio = UnitMembership(user_id=UserId("user-2"), unit_id=UnitId("unit-2"))
    repo.seed_membership(meu)
    repo.seed_membership(alheio)

    assert repo.list_memberships(UserId("user-1")) == (meu,)


def test_fake_pode_simular_adapter_permissivo_que_vaza_vinculo_alheio() -> None:
    """O gancho existe para provar que a visibilidade não depende deste filtro.

    Quem casa `user_id` **e** `unit_id` é `User.can_view_unit`, no domínio. O
    CA12 usa este modo para exercitar essa garantia.
    """
    repo = InMemoryUserRepository()
    alheio = UnitMembership(user_id=UserId("user-2"), unit_id=UnitId("unit-2"))
    repo.seed_membership(alheio)
    repo.leak_foreign_memberships = True

    assert repo.list_memberships(UserId("user-1")) == (alheio,)


def test_list_memberships_preserva_a_ordem_de_insercao() -> None:
    repo = InMemoryUserRepository()
    primeiro = UnitMembership(user_id=UserId("user-1"), unit_id=UnitId("unit-1"))
    segundo = UnitMembership(user_id=UserId("user-1"), unit_id=UnitId("unit-2"))

    repo.add(_user(), _HASH, [primeiro, segundo])

    assert repo.list_memberships(UserId("user-1")) == (primeiro, segundo)
    assert repo.list_all_memberships() == (primeiro, segundo)

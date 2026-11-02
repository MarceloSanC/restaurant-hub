"""Testes do use case `get_account_role` — Stage 3.8, CA01 (ADR 3.8.0001 §3).

O que se protege: o papel devolvido é o da conta pedida, para **cada** papel —
não um representante, porque é sobre esse valor que staff decide se revoga as
sessões de quem é desligado —; conta desconhecida é `None`, não erro; a consulta
não escreve; e a falha do repositório sobe como é, porque um `None` no lugar dela
faria o desligamento gravar com a sessão viva.
"""

import pytest

from restaurant_hub.features.identity.application.dtos.commands import GetAccountRoleCommand
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.dtos.results import AccountRoleResult
from restaurant_hub.features.identity.application.use_cases.get_account_role import (
    GetAccountRoleUseCase,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

pytestmark = pytest.mark.unit

_TENANT = RestaurantId("rest-1")
_HASH = PasswordHash("hashed::s3nha")


def _conta(user_id: str, role: Role) -> User:
    # `platform_admin` não tem tenant, e todos os outros papéis exigem um (User).
    tenant = None if role is Role.PLATFORM_ADMIN else _TENANT
    return User(id=UserId(user_id), email=Email(f"{user_id}@x.com"), role=role, tenant_id=tenant)


@pytest.mark.parametrize("papel", list(Role), ids=lambda papel: papel.value)
def test_devolve_o_papel_da_conta_pedida(papel: Role) -> None:
    users = InMemoryUserRepository()
    users.add(_conta("alvo", papel), _HASH)
    # Uma vizinha de papel diferente: o use case tem de ler **a** conta pedida.
    vizinho = Role.OWNER if papel is not Role.OWNER else Role.EMPLOYEE
    users.add(_conta("vizinha", vizinho), _HASH)

    resultado = GetAccountRoleUseCase(users).execute(GetAccountRoleCommand(user_id=UserId("alvo")))

    assert resultado == AccountRoleResult(role=papel)


def test_conta_desconhecida_e_none_e_nao_erro() -> None:
    resultado = GetAccountRoleUseCase(InMemoryUserRepository()).execute(
        GetAccountRoleCommand(user_id=UserId("nunca-existiu"))
    )

    assert resultado is None


def test_a_consulta_nao_altera_o_repositorio() -> None:
    users = InMemoryUserRepository()
    users.add(_conta("alvo", Role.EMPLOYEE), _HASH)
    antes = (dict(users.users), dict(users.password_hashes), list(users.memberships))

    GetAccountRoleUseCase(users).execute(GetAccountRoleCommand(user_id=UserId("alvo")))

    assert (dict(users.users), dict(users.password_hashes), list(users.memberships)) == antes


def test_falha_do_repositorio_sobe_na_mesma_instancia() -> None:
    falha = RuntimeError("banco fora")

    class _RepositorioQueFalha(InMemoryUserRepository):
        def find_by_id(self, user_id: UserId) -> User | None:
            raise falha

    with pytest.raises(RuntimeError) as excinfo:
        GetAccountRoleUseCase(_RepositorioQueFalha()).execute(
            GetAccountRoleCommand(user_id=UserId("alvo"))
        )

    assert excinfo.value is falha

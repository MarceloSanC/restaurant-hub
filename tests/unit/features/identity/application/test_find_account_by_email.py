"""`FindAccountByEmailUseCase` — a consulta facade-only da Stage 3.10 (ADR 3.10.0002 §2).

Três fatos por conta — tenant, unidades de que **ela** é membro e alcance de todas as
unidades — e `None` para e-mail sem conta. Os casos que importam à elegibilidade em
staff estão aqui um por um: o dono sem membership, o `platform_admin` sem tenant e o
repositório que devolve membership de terceiro (o port não promete o filtro).
"""

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    FindAccountByEmailCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.dtos.results import AccountSummaryResult
from restaurant_hub.features.identity.application.use_cases.find_account_by_email import (
    FindAccountByEmailUseCase,
)
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
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

pytestmark = pytest.mark.unit

_TENANT = RestaurantId("rest-a")
_HASH = PasswordHash("hash")


def _usuario(  # noqa: PLR0913 — os cinco campos da conta mais o repositório
    users: InMemoryUserRepository,
    user_id: str,
    email: str,
    role: Role,
    *,
    tenant: RestaurantId | None = _TENANT,
    unidades: tuple[str, ...] = (),
) -> None:
    usuario = User(id=UserId(user_id), email=Email(email), role=role, tenant_id=tenant)
    users.add(
        usuario,
        _HASH,
        tuple(UnitMembership(user_id=UserId(user_id), unit_id=UnitId(u)) for u in unidades),
    )


def _consultar(users: InMemoryUserRepository, email: str) -> AccountSummaryResult | None:
    return FindAccountByEmailUseCase(users).execute(FindAccountByEmailCommand(email=Email(email)))


@pytest.mark.parametrize("role", [Role.MANAGER, Role.HR, Role.EMPLOYEE])
def test_conta_membro_devolve_tenant_e_unidades_ordenadas_sem_alcance_total(role: Role) -> None:
    users = InMemoryUserRepository()
    _usuario(users, "u-1", "ana@cantina.com", role, unidades=("unit-b", "unit-a"))

    assert _consultar(users, "ana@cantina.com") == AccountSummaryResult(
        user_id=UserId("u-1"),
        tenant_id=_TENANT,
        unit_ids=(UnitId("unit-a"), UnitId("unit-b")),
        sees_every_unit=False,
    )


def test_dono_sem_membership_alcanca_todas_as_unidades() -> None:
    users = InMemoryUserRepository()
    _usuario(users, "u-dono", "dono@cantina.com", Role.OWNER)

    assert _consultar(users, "dono@cantina.com") == AccountSummaryResult(
        user_id=UserId("u-dono"), tenant_id=_TENANT, unit_ids=(), sees_every_unit=True
    )


def test_platform_admin_nao_tem_tenant_nem_alcance() -> None:
    """`bypasses_unit_scope` é verdadeiro para ele; o fato devolvido é falso — sem tenant."""
    users = InMemoryUserRepository()
    _usuario(users, "u-adm", "adm@plataforma.com", Role.PLATFORM_ADMIN, tenant=None)

    assert _consultar(users, "adm@plataforma.com") == AccountSummaryResult(
        user_id=UserId("u-adm"), tenant_id=None, unit_ids=(), sees_every_unit=False
    )


def test_email_sem_conta_e_none() -> None:
    users = InMemoryUserRepository()
    _usuario(users, "u-1", "ana@cantina.com", Role.MANAGER)

    assert _consultar(users, "outra@cantina.com") is None


def test_email_e_normalizado_pelo_vo() -> None:
    users = InMemoryUserRepository()
    _usuario(users, "u-1", "ana@cantina.com", Role.MANAGER)

    resultado = _consultar(users, "  Ana@Cantina.COM ")

    assert resultado is not None
    assert resultado.user_id == UserId("u-1")


def test_membership_de_terceiro_devolvida_pelo_repositorio_nao_entra() -> None:
    """O port pode devolver vínculo alheio (decisão 3 do seu docstring); o use case filtra."""
    users = InMemoryUserRepository()
    _usuario(users, "u-1", "ana@cantina.com", Role.MANAGER, unidades=("unit-a",))
    _usuario(users, "u-2", "bia@cantina.com", Role.MANAGER, unidades=("unit-z",))
    users.leak_foreign_memberships = True

    resultado = _consultar(users, "ana@cantina.com")

    assert resultado is not None
    assert resultado.unit_ids == (UnitId("unit-a"),)


def test_falha_do_repositorio_sobe_crua() -> None:
    falha = RuntimeError("banco fora")

    class _Quebrado(InMemoryUserRepository):
        def find_credentials_by_email(self, email: Email) -> None:  # type: ignore[override]
            raise falha

    with pytest.raises(RuntimeError) as excinfo:
        _consultar(_Quebrado(), "ana@cantina.com")

    assert excinfo.value is falha

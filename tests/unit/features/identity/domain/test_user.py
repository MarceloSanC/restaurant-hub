"""Testes da entidade User — construção, invariante de tenancy e RBAC.

As invariantes de vínculo e visibilidade ficam em `test_visibility.py`.
"""

import pytest

from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    MissingTenantError,
    PlatformAdminTenantError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.unit

TENANT = RestaurantId("r1")
_RESTAURANT_ROLES = [Role.OWNER, Role.MANAGER, Role.HR, Role.EMPLOYEE]


def _user(
    role: Role,
    tenant_id: RestaurantId | None = TENANT,
    user_id: str = "us1",
) -> User:
    return User(
        id=UserId(user_id),
        email=Email("pessoa@restaurante.com"),
        role=role,
        tenant_id=tenant_id,
    )


@pytest.mark.parametrize("role", _RESTAURANT_ROLES)
def test_usuario_de_restaurante_pertence_a_um_tenant(role: Role) -> None:
    assert _user(role).tenant_id == TENANT


@pytest.mark.parametrize("role", _RESTAURANT_ROLES)
def test_usuario_de_restaurante_sem_tenant_e_rejeitado(role: Role) -> None:
    # Invariante 1: papel de restaurante exige tenant_id.
    with pytest.raises(MissingTenantError, match=role.value):
        _user(role, tenant_id=None)


def test_platform_admin_sem_tenant_e_valido() -> None:
    # Invariante 2 (ADR 2.1.0002): acesso de plataforma vive fora de tenant.
    assert _user(Role.PLATFORM_ADMIN, tenant_id=None).tenant_id is None


def test_platform_admin_com_tenant_e_rejeitado() -> None:
    with pytest.raises(PlatformAdminTenantError, match="platform_admin"):
        _user(Role.PLATFORM_ADMIN, tenant_id=TENANT)


@pytest.mark.parametrize(
    ("role", "permission", "esperado"),
    [
        (Role.PLATFORM_ADMIN, Permission.MANAGE_PLATFORM, True),
        (Role.PLATFORM_ADMIN, Permission.MANAGE_TENANT, False),
        (Role.PLATFORM_ADMIN, Permission.MANAGE_USERS, False),
        (Role.OWNER, Permission.MANAGE_TENANT, True),
        (Role.OWNER, Permission.MANAGE_USERS, True),
        (Role.OWNER, Permission.MANAGE_PLATFORM, False),
        (Role.MANAGER, Permission.MANAGE_USERS, True),
        (Role.MANAGER, Permission.MANAGE_TENANT, False),
        (Role.MANAGER, Permission.MANAGE_PLATFORM, False),
        (Role.HR, Permission.MANAGE_USERS, True),
        (Role.HR, Permission.MANAGE_TENANT, False),
        (Role.EMPLOYEE, Permission.MANAGE_USERS, False),
        (Role.EMPLOYEE, Permission.MANAGE_TENANT, False),
        (Role.EMPLOYEE, Permission.MANAGE_PLATFORM, False),
    ],
)
def test_has_permission_reflete_o_mapa_do_papel(
    role: Role, permission: Permission, esperado: bool
) -> None:
    tenant = None if role is Role.PLATFORM_ADMIN else TENANT
    assert _user(role, tenant_id=tenant).has_permission(permission) is esperado


@pytest.mark.parametrize(
    ("role", "esperado"),
    [
        (Role.PLATFORM_ADMIN, True),
        (Role.OWNER, True),
        (Role.MANAGER, False),
        (Role.HR, False),
        (Role.EMPLOYEE, False),
    ],
)
def test_bypass_de_escopo_de_unidade_por_papel(role: Role, esperado: bool) -> None:
    tenant = None if role is Role.PLATFORM_ADMIN else TENANT
    assert _user(role, tenant_id=tenant).bypasses_unit_scope() is esperado


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    antes = _user(Role.OWNER)
    depois = User(
        id=UserId("us1"),
        email=Email("outro@restaurante.com"),
        role=Role.HR,
        tenant_id=TENANT,
    )
    assert antes == depois
    assert len({antes, depois}) == 1


def test_ids_diferentes_nao_sao_iguais() -> None:
    assert _user(Role.OWNER, user_id="us1") != _user(Role.OWNER, user_id="us2")


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    assert _user(Role.OWNER) != "us1"

"""Testes de vínculo e visibilidade — as invariantes de isolamento (concept §5.3-5.4).

Este é o arquivo que guarda o isolamento entre tenants: se ele afrouxar, um
usuário passa a enxergar dados de outro restaurante.
"""

import pytest

from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    CrossTenantError,
    PlatformAdminMembershipError,
)
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

pytestmark = pytest.mark.unit

TENANT_A = RestaurantId("rA")
TENANT_B = RestaurantId("rB")

UNIT_A1 = Unit(id=UnitId("uA1"), restaurant_id=TENANT_A, name="Matriz A")
UNIT_A2 = Unit(id=UnitId("uA2"), restaurant_id=TENANT_A, name="Filial A")
UNIT_B1 = Unit(id=UnitId("uB1"), restaurant_id=TENANT_B, name="Matriz B")

_SCOPED_ROLES = [Role.MANAGER, Role.HR, Role.EMPLOYEE]


def _user(role: Role, tenant_id: RestaurantId | None, user_id: str = "us1") -> User:
    return User(
        id=UserId(user_id),
        email=Email("pessoa@restaurante.com"),
        role=role,
        tenant_id=tenant_id,
    )


# --- link_to_unit -----------------------------------------------------------


def test_link_to_unit_cria_o_vinculo_no_mesmo_tenant() -> None:
    usuario = _user(Role.EMPLOYEE, TENANT_A)
    assert usuario.link_to_unit(UNIT_A1) == UnitMembership(UserId("us1"), UnitId("uA1"))


@pytest.mark.parametrize("role", [*_SCOPED_ROLES, Role.OWNER])
def test_link_to_unit_entre_tenants_diferentes_e_bloqueado(role: Role) -> None:
    # Invariante 3: o vínculo nunca cruza a fronteira do tenant.
    usuario = _user(role, TENANT_A)
    with pytest.raises(CrossTenantError, match="isolamento de tenant"):
        usuario.link_to_unit(UNIT_B1)


def test_platform_admin_nao_recebe_vinculo_de_unidade() -> None:
    admin = _user(Role.PLATFORM_ADMIN, None)
    with pytest.raises(PlatformAdminMembershipError, match="unidade"):
        admin.link_to_unit(UNIT_A1)


# --- can_view_unit ----------------------------------------------------------


def test_owner_enxerga_qualquer_unidade_do_proprio_tenant_sem_vinculo() -> None:
    owner = _user(Role.OWNER, TENANT_A)
    assert owner.can_view_unit(UNIT_A1, []) is True
    assert owner.can_view_unit(UNIT_A2, []) is True


def test_owner_nao_enxerga_unidade_de_outro_tenant() -> None:
    owner = _user(Role.OWNER, TENANT_A)
    assert owner.can_view_unit(UNIT_B1, []) is False


def test_platform_admin_enxerga_unidade_de_qualquer_tenant() -> None:
    # Bypass total: é resolvido antes da comparação de tenant (não tem tenant_id).
    admin = _user(Role.PLATFORM_ADMIN, None)
    assert admin.can_view_unit(UNIT_A1, []) is True
    assert admin.can_view_unit(UNIT_B1, []) is True


@pytest.mark.parametrize("role", _SCOPED_ROLES)
def test_papel_escopado_enxerga_somente_a_unidade_vinculada(role: Role) -> None:
    usuario = _user(role, TENANT_A)
    vinculo = usuario.link_to_unit(UNIT_A1)
    assert usuario.can_view_unit(UNIT_A1, [vinculo]) is True
    assert usuario.can_view_unit(UNIT_A2, [vinculo]) is False


@pytest.mark.parametrize("role", _SCOPED_ROLES)
def test_papel_escopado_sem_vinculo_nao_enxerga_nada(role: Role) -> None:
    assert _user(role, TENANT_A).can_view_unit(UNIT_A1, []) is False


def test_vinculo_de_outro_usuario_nao_concede_visibilidade() -> None:
    # Furo de escopo intra-tenant: o filtro precisa casar user_id E unit_id.
    alvo = _user(Role.EMPLOYEE, TENANT_A, user_id="us1")
    colega = _user(Role.EMPLOYEE, TENANT_A, user_id="us2")
    vinculo_do_colega = colega.link_to_unit(UNIT_A1)
    assert alvo.can_view_unit(UNIT_A1, [vinculo_do_colega]) is False


def test_vinculo_forjado_para_outro_tenant_nao_vence_o_isolamento() -> None:
    # Mesmo com um vínculo apontando para a unidade de outro tenant, a checagem
    # de tenant vem antes e nega — o isolamento não depende do vínculo.
    usuario = _user(Role.EMPLOYEE, TENANT_A)
    forjado = UnitMembership(UserId("us1"), UnitId("uB1"))
    assert usuario.can_view_unit(UNIT_B1, [forjado]) is False


def test_visibilidade_considera_apenas_o_vinculo_correspondente() -> None:
    usuario = _user(Role.MANAGER, TENANT_A)
    outros_vinculos = [
        UnitMembership(UserId("us2"), UnitId("uA1")),
        UnitMembership(UserId("us1"), UnitId("uA2")),
    ]
    assert usuario.can_view_unit(UNIT_A1, outros_vinculos) is False
    assert usuario.can_view_unit(UNIT_A2, outros_vinculos) is True

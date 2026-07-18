"""Teste de fluxo do domínio de identity — amarra as peças de ponta a ponta.

Esta Stage é domínio puro (sem API/CLI/job), então o "fluxo de negócio" é este:
restaurante (tenant) → unidade → usuário → vínculo → visibilidade + permissão.
Os ids são **derivados das entidades** (`restaurante.tenant_id`), não literais, de
modo que o `Restaurant` participe de verdade da amarração em vez de ficar órfão.
"""

import pytest

from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import CrossTenantError
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.unit


def test_fluxo_do_restaurante_ate_a_visibilidade_da_unidade() -> None:
    cantina = Restaurant(id=RestaurantId("r1"), name="Cantina do Porto")
    matriz = Unit(id=UnitId("u1"), restaurant_id=cantina.tenant_id, name="Matriz")
    filial = Unit(id=UnitId("u2"), restaurant_id=cantina.tenant_id, name="Filial")
    gerente = User(
        id=UserId("us1"),
        email=Email("gerente@cantina.com"),
        role=Role.MANAGER,
        tenant_id=cantina.tenant_id,
    )

    vinculo = gerente.link_to_unit(matriz)

    # Eixo B (visibilidade): só a unidade vinculada.
    assert gerente.can_view_unit(matriz, [vinculo]) is True
    assert gerente.can_view_unit(filial, [vinculo]) is False


def test_os_dois_eixos_de_acesso_sao_ortogonais() -> None:
    # A permissão é do papel e não muda com a unidade; a visibilidade é do
    # vínculo e não muda com o papel (para papéis escopados).
    cantina = Restaurant(id=RestaurantId("r1"), name="Cantina do Porto")
    matriz = Unit(id=UnitId("u1"), restaurant_id=cantina.tenant_id, name="Matriz")
    filial = Unit(id=UnitId("u2"), restaurant_id=cantina.tenant_id, name="Filial")
    gerente = User(
        id=UserId("us1"),
        email=Email("gerente@cantina.com"),
        role=Role.MANAGER,
        tenant_id=cantina.tenant_id,
    )
    vinculo = gerente.link_to_unit(matriz)

    assert gerente.can_view_unit(matriz, [vinculo]) is True
    assert gerente.has_permission(Permission.MANAGE_USERS) is True

    # Na unidade não vinculada perde a visibilidade, mas mantém a permissão.
    assert gerente.can_view_unit(filial, [vinculo]) is False
    assert gerente.has_permission(Permission.MANAGE_USERS) is True
    assert gerente.has_permission(Permission.MANAGE_PLATFORM) is False


def test_dono_de_outro_restaurante_nao_alcanca_a_unidade_alheia() -> None:
    cantina = Restaurant(id=RestaurantId("r1"), name="Cantina do Porto")
    concorrente = Restaurant(id=RestaurantId("r2"), name="Bistrô Rival")
    matriz_da_cantina = Unit(id=UnitId("u1"), restaurant_id=cantina.tenant_id, name="Matriz")
    dono_rival = User(
        id=UserId("us9"),
        email=Email("dono@rival.com"),
        role=Role.OWNER,
        tenant_id=concorrente.tenant_id,
    )

    # Nem enxerga (bypass de owner não vence o isolamento) nem consegue vincular.
    assert dono_rival.can_view_unit(matriz_da_cantina, []) is False
    with pytest.raises(CrossTenantError):
        dono_rival.link_to_unit(matriz_da_cantina)


def test_platform_admin_atravessa_os_tenants_mas_sem_permissao_de_restaurante() -> None:
    cantina = Restaurant(id=RestaurantId("r1"), name="Cantina do Porto")
    concorrente = Restaurant(id=RestaurantId("r2"), name="Bistrô Rival")
    unidade_a = Unit(id=UnitId("u1"), restaurant_id=cantina.tenant_id, name="Matriz")
    unidade_b = Unit(id=UnitId("u2"), restaurant_id=concorrente.tenant_id, name="Matriz Rival")
    admin = User(
        id=UserId("adm"),
        email=Email("admin@plataforma.com"),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )

    assert admin.can_view_unit(unidade_a, []) is True
    assert admin.can_view_unit(unidade_b, []) is True
    # Acesso de plataforma != acesso de restaurante (concept §5.7).
    assert admin.has_permission(Permission.MANAGE_PLATFORM) is True
    assert admin.has_permission(Permission.MANAGE_TENANT) is False
    assert admin.has_permission(Permission.MANAGE_USERS) is False

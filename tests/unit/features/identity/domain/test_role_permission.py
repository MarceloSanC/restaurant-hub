"""Testes de Role, Permission e do mapa RBAC (concept §5, regras 5-7)."""

import pytest

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidRoleError
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.unit

_RESTAURANT_ROLES = (Role.OWNER, Role.MANAGER, Role.HR, Role.EMPLOYEE)


def test_role_e_conjunto_fechado_de_cinco_papeis() -> None:
    assert {r.value for r in Role} == {
        "platform_admin",
        "owner",
        "manager",
        "hr",
        "employee",
    }


def test_permission_e_conjunto_fechado() -> None:
    assert {p.value for p in Permission} == {
        "manage_platform",
        "manage_tenant",
        "manage_users",
    }


@pytest.mark.parametrize("valor", ["platform_admin", "owner", "manager", "hr", "employee"])
def test_from_string_aceita_papel_conhecido(valor: str) -> None:
    assert Role.from_string(valor).value == valor


@pytest.mark.parametrize("desconhecido", ["chef", "", "OWNER", "admin", "gerente"])
def test_from_string_rejeita_papel_desconhecido(desconhecido: str) -> None:
    with pytest.raises(InvalidRoleError, match="papel inválido"):
        Role.from_string(desconhecido)


def test_from_string_preserva_a_causa_original() -> None:
    # `raise ... from exc` mantém o ValueError do enum como causa, preservando
    # o rastro para depuração nas camadas de fora.
    with pytest.raises(InvalidRoleError) as excinfo:
        Role.from_string("chef")
    assert isinstance(excinfo.value.__cause__, ValueError)


def test_role_compara_por_valor() -> None:
    # VO: igualdade estrutural; StrEnum também compara com a própria string.
    assert Role.from_string("owner") == Role.OWNER
    assert Role.OWNER == "owner"


def test_mapa_de_permissoes_e_total_sobre_todos_os_papeis() -> None:
    # Guarda contra papel novo adicionado sem entrada no mapa: sem entrada,
    # `role.permissions` levanta KeyError e este teste quebra.
    for role in Role:
        assert isinstance(role.permissions, frozenset)


@pytest.mark.parametrize(
    ("role", "esperado"),
    [
        (Role.PLATFORM_ADMIN, {Permission.MANAGE_PLATFORM}),
        (Role.OWNER, {Permission.MANAGE_TENANT, Permission.MANAGE_USERS}),
        (Role.MANAGER, {Permission.MANAGE_USERS}),
        (Role.HR, {Permission.MANAGE_USERS}),
        (Role.EMPLOYEE, set()),
    ],
)
def test_conteudo_exato_do_mapa_por_papel(role: Role, esperado: set[Permission]) -> None:
    assert role.permissions == frozenset(esperado)


def test_platform_admin_nao_tem_permissao_operacional_de_restaurante() -> None:
    # concept §5 regra 7: acesso de plataforma != acesso de restaurante.
    assert Permission.MANAGE_TENANT not in Role.PLATFORM_ADMIN.permissions
    assert Permission.MANAGE_USERS not in Role.PLATFORM_ADMIN.permissions


@pytest.mark.parametrize("role", _RESTAURANT_ROLES)
def test_nenhum_papel_de_restaurante_gerencia_a_plataforma(role: Role) -> None:
    assert Permission.MANAGE_PLATFORM not in role.permissions


def test_employee_nao_tem_capacidade_de_gestao() -> None:
    assert Role.EMPLOYEE.permissions == frozenset()

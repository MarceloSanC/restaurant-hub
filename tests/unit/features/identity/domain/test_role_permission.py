"""Testes de Role, Permission e do mapa RBAC (concept §5, regras 5-7)."""

import pytest

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidRoleError
from restaurant_hub.features.identity.domain.value_objects.permission import (
    TENANT_WIDE_PERMISSIONS,
    Permission,
)
from restaurant_hub.features.identity.domain.value_objects.role import (
    _ROLE_PERMISSIONS,
    Role,
)

pytestmark = pytest.mark.unit

_RESTAURANT_ROLES = (Role.OWNER, Role.MANAGER, Role.HR, Role.EMPLOYEE)

# As duas capacidades que o BC `staff` introduziu no vocabulário (ADR 3.4.0006 §4).
_STAFF_PERMISSIONS = frozenset({Permission.MANAGE_STAFF, Permission.MANAGE_JOB_FUNCTIONS})

# As quatro de escala (Stage 4.5, ADR 4.5.0001).
_SCHEDULE_PERMISSIONS = frozenset(
    {
        Permission.VIEW_SCHEDULE,
        Permission.MANAGE_SCHEDULE,
        Permission.VIEW_OWN_SCHEDULE,
        Permission.MANAGE_SCHEDULE_SETTINGS,
    }
)


def test_role_e_conjunto_fechado_de_cinco_papeis() -> None:
    assert {r.value for r in Role} == {
        "platform_admin",
        "owner",
        "manager",
        "hr",
        "employee",
    }


def test_permission_e_conjunto_fechado() -> None:
    # Fixture de **fechamento de vocabulário**: existe para exigir atualização
    # consciente quando o conjunto cresce. Ela mudar é o teste funcionando —
    # a não-regressão de decisão de acesso é provada em `test_rbac_additivity.py`.
    assert {p.value for p in Permission} == {
        "manage_platform",
        "manage_tenant",
        "manage_users",
        "manage_staff",
        "manage_job_functions",
        "view_schedule",
        "manage_schedule",
        "view_own_schedule",
        "manage_schedule_settings",
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
    # Asserção sobre as CHAVES, não sobre o tipo do retorno: se o acesso ao mapa
    # virasse `.get(role, frozenset())`, um papel sem entrada passaria a negar
    # tudo em silêncio e um assert de tipo não perceberia.
    assert set(_ROLE_PERMISSIONS) == set(Role)


@pytest.mark.parametrize(
    ("role", "esperado"),
    [
        (Role.PLATFORM_ADMIN, {Permission.MANAGE_PLATFORM}),
        (
            Role.OWNER,
            {
                Permission.MANAGE_TENANT,
                Permission.MANAGE_USERS,
                Permission.MANAGE_STAFF,
                Permission.MANAGE_JOB_FUNCTIONS,
                Permission.VIEW_SCHEDULE,
                Permission.MANAGE_SCHEDULE,
                Permission.VIEW_OWN_SCHEDULE,
                Permission.MANAGE_SCHEDULE_SETTINGS,
            },
        ),
        (
            Role.MANAGER,
            {
                Permission.MANAGE_USERS,
                Permission.MANAGE_STAFF,
                Permission.MANAGE_JOB_FUNCTIONS,
                Permission.VIEW_SCHEDULE,
                Permission.MANAGE_SCHEDULE,
                Permission.VIEW_OWN_SCHEDULE,
            },
        ),
        (
            Role.HR,
            {
                Permission.MANAGE_USERS,
                Permission.MANAGE_STAFF,
                Permission.MANAGE_JOB_FUNCTIONS,
                Permission.VIEW_SCHEDULE,
                Permission.VIEW_OWN_SCHEDULE,
            },
        ),
        (Role.EMPLOYEE, {Permission.VIEW_OWN_SCHEDULE}),
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
    """Desde a Stage 4.5 o `employee` vê a própria escala, e só isso (ADR 4.5.0001)."""
    assert Role.EMPLOYEE.permissions == frozenset({Permission.VIEW_OWN_SCHEDULE})
    assert not any(p.value.startswith("manage_") for p in Role.EMPLOYEE.permissions)


# --------------------------------------------------------------------------
# Stage 4.5 (CA11) — as quatro permissões de escala no mapa de papéis
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "esperado"),
    [
        (Role.OWNER, set(_SCHEDULE_PERMISSIONS)),
        (
            Role.MANAGER,
            {Permission.VIEW_SCHEDULE, Permission.MANAGE_SCHEDULE, Permission.VIEW_OWN_SCHEDULE},
        ),
        (Role.HR, {Permission.VIEW_SCHEDULE, Permission.VIEW_OWN_SCHEDULE}),
        (Role.EMPLOYEE, {Permission.VIEW_OWN_SCHEDULE}),
        (Role.PLATFORM_ADMIN, set()),
    ],
)
def test_subconjunto_de_escala_por_papel(role: Role, esperado: set[Permission]) -> None:
    """ADR 4.5.0001 §Decision 3 — o mapa de escala, papel a papel."""
    assert role.permissions & _SCHEDULE_PERMISSIONS == frozenset(esperado)


def test_hr_nao_mexe_na_escala() -> None:
    """ADR 3.4.0006 §3 (mantido pelos ADRs 4.1.0004 e 4.5.0001): `hr` lê, não gerencia."""
    assert Permission.MANAGE_SCHEDULE not in Role.HR.permissions
    assert Permission.MANAGE_SCHEDULE_SETTINGS not in Role.HR.permissions


def test_so_o_owner_detem_a_configuracao_de_escala() -> None:
    """ADR 4.5.0001 §Decision 5 — tenant-wide, só do dono."""
    assert [r for r in Role if Permission.MANAGE_SCHEDULE_SETTINGS in r.permissions] == [Role.OWNER]


# --------------------------------------------------------------------------
# CA2, CA3 — as duas permissões de staff no mapa de papéis
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "esperado"),
    [
        (Role.OWNER, _STAFF_PERMISSIONS),
        (Role.MANAGER, _STAFF_PERMISSIONS),
        (Role.HR, _STAFF_PERMISSIONS),
        (Role.EMPLOYEE, frozenset()),
        (Role.PLATFORM_ADMIN, frozenset()),
    ],
)
def test_subconjunto_de_staff_por_papel(role: Role, esperado: frozenset[Permission]) -> None:
    """CA2 — `owner`, `manager` e `hr` detêm as duas; os outros dois, nenhuma."""
    assert role.permissions & _STAFF_PERMISSIONS == esperado


def test_hr_e_manager_tem_conjuntos_de_staff_identicos() -> None:
    """CA3 — dentro de staff, `hr` ≡ `manager` (ADR 3.4.0006 §2).

    A divergência hr/manager é por **família de operação** (escala, no Step 4),
    não por alcance. Este teste falha se alguém os separar aqui sem ADR novo.
    """
    assert Role.HR.permissions & _STAFF_PERMISSIONS == Role.MANAGER.permissions & _STAFF_PERMISSIONS


# --------------------------------------------------------------------------
# CA6, CA7 — TENANT_WIDE_PERMISSIONS
# --------------------------------------------------------------------------


def test_tenant_wide_permissions_e_a_lista_esperada_explicita() -> None:
    """CA6 — totalidade é teste (ADR 3.4.0008 §5).

    Asserção sobre o conjunto **exato**: acrescentar membro passa a ser ato
    deliberado e revisado, e não um diff de uma palavra que nada observa.
    """
    assert set(TENANT_WIDE_PERMISSIONS) == {
        Permission.MANAGE_JOB_FUNCTIONS,
        Permission.MANAGE_SCHEDULE_SETTINGS,
    }


@pytest.mark.parametrize(
    "permissao",
    [Permission.VIEW_SCHEDULE, Permission.MANAGE_SCHEDULE, Permission.VIEW_OWN_SCHEDULE],
)
def test_permissoes_de_escala_da_unidade_nao_sao_tenant_wide(permissao: Permission) -> None:
    """A escala mora numa unidade (ADR 4.1.0004 §1): ler, gerenciar e a própria são unit-scoped."""
    assert permissao not in TENANT_WIDE_PERMISSIONS


def test_manage_staff_nao_e_tenant_wide() -> None:
    """CA7 — mata a mutação que daria alcance cross-unidade sobre registros.

    `MANAGE_STAFF` é unit-scoped por desenho: registro de funcionário mora numa
    unidade. Pô-lo no conjunto dispensaria a unidade para todo papel unit-scoped.
    """
    assert Permission.MANAGE_STAFF not in TENANT_WIDE_PERMISSIONS

"""Testes do use case `authorize_action` — concept CA8 a CA12.

Esta é a suíte de maior valor da Stage. O que ela protege não é "a função roda",
e sim que **as checagens não se fundam** e que **a ordem não mude** — dois
defeitos que passariam por qualquer teste de caminho feliz e virariam falha de
isolamento em produção.
"""

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import (
    PermissionDeniedError,
    TenantNotVisibleError,
    TenantScopeRequiredError,
    UnitNotFoundError,
    UnitNotVisibleError,
    UnitScopeRequiredError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

pytestmark = pytest.mark.unit

_TENANT_A = RestaurantId("rest-a")
_TENANT_B = RestaurantId("rest-b")
_UNIT_A1 = UnitId("unit-a1")
_UNIT_A2 = UnitId("unit-a2")
_UNIT_B1 = UnitId("unit-b1")
_HASH = PasswordHash("hashed::x")


class _Fixture:
    """Dois tenants, duas unidades em A, uma em B, e um ator por papel."""

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.units = InMemoryUnitRepository()
        self.units.add(Unit(id=_UNIT_A1, restaurant_id=_TENANT_A, name="Centro"))
        self.units.add(Unit(id=_UNIT_A2, restaurant_id=_TENANT_A, name="Praia"))
        self.units.add(Unit(id=_UNIT_B1, restaurant_id=_TENANT_B, name="Outra"))
        self.use_case = AuthorizeActionUseCase(self.users, self.units)

    def add_user(
        self,
        user_id: str,
        role: Role,
        tenant: RestaurantId | None,
        units: tuple[UnitId, ...] = (),
    ) -> User:
        user = User(
            id=UserId(user_id),
            email=Email(f"{user_id}@x.com"),
            role=role,
            tenant_id=tenant,
        )
        memberships = [UnitMembership(user_id=user.id, unit_id=u) for u in units]
        self.users.add(user, _HASH, memberships)
        return user


def _command(
    actor: str,
    permission: Permission = Permission.MANAGE_USERS,
    tenant: RestaurantId | None = _TENANT_A,
    unit: UnitId | None = _UNIT_A1,
) -> AuthorizeActionCommand:
    return AuthorizeActionCommand(
        actor_id=UserId(actor),
        permission=permission,
        tenant_id=tenant,
        unit_id=unit,
    )


# --------------------------------------------------------------------------
# CA8 — caminho feliz
# --------------------------------------------------------------------------


def test_manager_vinculado_a_unidade_e_autorizado() -> None:
    """CA8 — permissão concedida e unidade visível."""
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    actor = fixture.use_case.execute(_command("m"))

    assert actor.user_id == "m"
    assert actor.role is Role.MANAGER
    assert actor.actor_tenant_id == _TENANT_A
    assert actor.scope_tenant_id == _TENANT_A
    assert actor.scope_unit_id == _UNIT_A1


def test_resultado_devolve_o_escopo_validado_e_nao_so_o_ator() -> None:
    """Sem o escopo no result, a 2.4 teria de re-derivá-lo do request."""
    fixture = _Fixture()
    fixture.add_user("admin", Role.PLATFORM_ADMIN, None)

    actor = fixture.use_case.execute(
        _command("admin", Permission.MANAGE_PLATFORM, tenant=_TENANT_B, unit=_UNIT_B1)
    )

    assert actor.actor_tenant_id is None
    assert actor.scope_tenant_id == _TENANT_B
    assert actor.scope_unit_id == _UNIT_B1


# --------------------------------------------------------------------------
# CA9 — os dois eixos, e a precedência entre eles
# --------------------------------------------------------------------------


def test_employee_e_negado_por_rbac_mesmo_na_propria_unidade() -> None:
    """CA9 — eixo RBAC. `employee` não tem permissão alguma no mapa da 2.1."""
    fixture = _Fixture()
    fixture.add_user("e", Role.EMPLOYEE, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(PermissionDeniedError):
        fixture.use_case.execute(_command("e"))


def test_manager_e_negado_em_unidade_do_mesmo_tenant_sem_vinculo() -> None:
    """CA9 — eixo visibilidade. Ter permissão não implica enxergar a unidade."""
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(UnitNotVisibleError):
        fixture.use_case.execute(_command("m", unit=_UNIT_A2))


def test_quem_falha_nos_dois_eixos_recebe_o_erro_do_rbac() -> None:
    """CA9 — a precedência é normativa, e é o que impede uma reordenação silenciosa.

    Se a visibilidade fosse avaliada antes do RBAC, este caso devolveria
    `UnitNotVisibleError`. Ambos negam, então só a asserção de **qual** erro
    sobe detecta a troca de ordem.
    """
    fixture = _Fixture()
    fixture.add_user("e", Role.EMPLOYEE, _TENANT_A)

    with pytest.raises(PermissionDeniedError):
        fixture.use_case.execute(_command("e", unit=_UNIT_A2))


def test_ator_inexistente_e_rejeitado_antes_de_qualquer_checagem() -> None:
    fixture = _Fixture()

    with pytest.raises(UserNotFoundError):
        fixture.use_case.execute(_command("fantasma"))


# --------------------------------------------------------------------------
# CA10 — as quatro negativas de escopo
# --------------------------------------------------------------------------


def test_manager_agindo_sobre_outro_tenant_e_negado() -> None:
    """CA10.1 — isolamento multi-tenant no eixo de escopo."""
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(TenantNotVisibleError):
        fixture.use_case.execute(_command("m", tenant=_TENANT_B, unit=_UNIT_B1))


def test_manager_sem_declarar_tenant_e_negado() -> None:
    """CA10.2 — a checagem de tenant é exigência, não filtro opcional.

    Se rodasse só quando `tenant_id` fosse informado, omitir o campo viraria o
    caminho de escalada.
    """
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(TenantScopeRequiredError):
        fixture.use_case.execute(_command("m", tenant=None))


def test_manager_sem_declarar_unidade_e_negado() -> None:
    """CA10.3 — papel escopado por unidade não tem autoridade tenant-wide.

    Sem esta guarda, um `manager` vinculado a uma única unidade obteria alcance
    sobre o tenant inteiro apenas omitindo `unit_id`.
    """
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(UnitScopeRequiredError):
        fixture.use_case.execute(_command("m", unit=None))


def test_escopo_de_tenant_e_cobrado_antes_do_escopo_de_unidade() -> None:
    """A precedência entre os passos 3 e 4, que nenhum outro teste distingue.

    Os testes de CA10.2 e CA10.3 isolam uma checagem cada, então ambos passam
    mesmo com os dois passos trocados. Só um command que falha nas **duas** —
    sem tenant e sem unidade — revela qual roda primeiro. Verificado por mutação:
    trocar os passos derruba apenas este teste.
    """
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(TenantScopeRequiredError):
        fixture.use_case.execute(_command("m", tenant=None, unit=None))


def test_hr_tambem_precisa_declarar_a_unidade() -> None:
    """`hr` não faz bypass de escopo — mesma regra do `manager`."""
    fixture = _Fixture()
    fixture.add_user("h", Role.HR, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(UnitScopeRequiredError):
        fixture.use_case.execute(_command("h", unit=None))


def test_owner_pode_omitir_a_unidade() -> None:
    """CA10.4 — `owner` faz bypass de escopo dentro do próprio tenant."""
    fixture = _Fixture()
    fixture.add_user("o", Role.OWNER, _TENANT_A)

    actor = fixture.use_case.execute(_command("o", unit=None))

    assert actor.scope_unit_id is None


def test_owner_enxerga_unidade_do_proprio_tenant_sem_vinculo() -> None:
    """CA10.4 — bypass vale para as unidades do seu tenant, sem `UnitMembership`."""
    fixture = _Fixture()
    fixture.add_user("o", Role.OWNER, _TENANT_A)

    actor = fixture.use_case.execute(_command("o", unit=_UNIT_A2))

    assert actor.scope_unit_id == _UNIT_A2


def test_owner_nao_enxerga_unidade_de_outro_tenant() -> None:
    """CA10.4 — bypass é dentro do tenant, nunca entre tenants."""
    fixture = _Fixture()
    fixture.add_user("o", Role.OWNER, _TENANT_A)

    with pytest.raises(TenantNotVisibleError):
        fixture.use_case.execute(_command("o", unit=_UNIT_B1))


def test_unidade_alvo_inexistente_e_rejeitada() -> None:
    fixture = _Fixture()
    fixture.add_user("o", Role.OWNER, _TENANT_A)

    with pytest.raises(UnitNotFoundError):
        fixture.use_case.execute(_command("o", unit=UnitId("nao-existe")))


# --------------------------------------------------------------------------
# CA11 — platform_admin: enxerga tudo, pode pouco
# --------------------------------------------------------------------------


def test_platform_admin_enxerga_unidade_de_qualquer_tenant() -> None:
    """CA11 — bypass total de escopo, mesmo sem ter tenant."""
    fixture = _Fixture()
    fixture.add_user("admin", Role.PLATFORM_ADMIN, None)

    actor = fixture.use_case.execute(
        _command("admin", Permission.MANAGE_PLATFORM, tenant=_TENANT_B, unit=_UNIT_B1)
    )

    assert actor.scope_unit_id == _UNIT_B1


def test_platform_admin_pode_omitir_o_tenant() -> None:
    """CA11 — ele vive fora de qualquer tenant, então o passo 3 é pulado."""
    fixture = _Fixture()
    fixture.add_user("admin", Role.PLATFORM_ADMIN, None)

    actor = fixture.use_case.execute(
        _command("admin", Permission.MANAGE_PLATFORM, tenant=None, unit=None)
    )

    assert actor.scope_tenant_id is None


def test_platform_admin_nao_recebe_permissao_de_restaurante() -> None:
    """CA11 — a prova de que os dois eixos NÃO se confundem.

    O mesmo ator que enxerga toda unidade da plataforma é negado ao pedir uma
    capacidade operacional de restaurante: visibilidade ampla não vira permissão.
    """
    fixture = _Fixture()
    fixture.add_user("admin", Role.PLATFORM_ADMIN, None)

    with pytest.raises(PermissionDeniedError):
        fixture.use_case.execute(_command("admin", Permission.MANAGE_USERS, tenant=None, unit=None))


def test_platform_admin_com_par_tenant_unidade_incoerente_e_negado() -> None:
    """CA11 — bypass dispensa pertencimento, não coerência do alvo."""
    fixture = _Fixture()
    fixture.add_user("admin", Role.PLATFORM_ADMIN, None)

    with pytest.raises(TenantNotVisibleError):
        fixture.use_case.execute(
            _command("admin", Permission.MANAGE_PLATFORM, tenant=_TENANT_B, unit=_UNIT_A1)
        )


def test_mensagem_de_tenant_invisivel_descreve_o_tenant_do_ator() -> None:
    """A mensagem compara o tenant do **ator** com o do alvo, não o alvo consigo.

    Sem esta asserção, inverter os argumentos produz uma mensagem plausível e
    errada — para o `platform_admin` ela chegou a afirmar que o ator pertencia a
    um tenant, quando ele não pertence a nenhum.
    """
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A, (_UNIT_A1,))

    with pytest.raises(TenantNotVisibleError) as erro:
        fixture.use_case.execute(_command("m", tenant=_TENANT_A, unit=_UNIT_B1))

    assert _TENANT_A in str(erro.value)
    assert _TENANT_B in str(erro.value)


# --------------------------------------------------------------------------
# CA12 — a visibilidade não confia no filtro do repositório
# --------------------------------------------------------------------------


def test_vinculo_de_outro_usuario_nao_concede_visibilidade() -> None:
    """CA12 — mesmo com um repositório permissivo, o domínio casa user_id.

    Simula um adapter cuja query esqueceu o `WHERE user_id`. Se o use case
    filtrasse por conta própria, este teste passaria por acidente; ele passa
    porque `can_view_unit` casa usuário **e** unidade.
    """
    fixture = _Fixture()
    fixture.add_user("m", Role.MANAGER, _TENANT_A)
    fixture.users.seed_membership(UnitMembership(user_id=UserId("outro"), unit_id=_UNIT_A1))
    fixture.users.leak_foreign_memberships = True

    with pytest.raises(UnitNotVisibleError):
        fixture.use_case.execute(_command("m", unit=_UNIT_A1))

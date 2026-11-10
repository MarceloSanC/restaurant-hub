"""`authorize_requirement` — a expansão única de um requisito em pedidos (Stage 2.7).

A borda HTTP (`IdentityGuard.authorize_all`) e os use cases de identity que agem por
um ator chamam esta função (ADR 2.7.0001 §Decision 3). O que se trava aqui é a forma
da expansão — ordem, ausência de deduplicação, pedido sem unidade, interrupção na
primeira recusa — e as duas traduções de vazamento, pelo autorizador real.
"""

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    PermissionDeniedError,
    UnitNotFoundError,
    UnitNotVisibleError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.action_authorizer import (
    required_permissions_for_role,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
    authorize_requirement,
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
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.features.identity.stub_action_authorizers import (
    INFIDEL_ACTOR,
    DenyingActionAuthorizer,
    RecordingActionAuthorizer,
)

pytestmark = pytest.mark.unit

_ATOR = UserId("ator-1")
_TENANT = RestaurantId("rest-1")
_U1 = UnitId("u1")
_U2 = UnitId("u2")


def test_permissoes_em_ordem_por_fora_e_unidades_na_ordem_dada_sem_deduplicar() -> None:
    """O cenário discriminante do CA04: 4 permissões vezes (U2, U1, U2) = 12 pedidos.

    Iterar as unidades por fora, ordenar as unidades ou deduplicá-las muda a
    sequência — e, com ela, qual erro o cliente vê quando falha em mais de uma.
    """
    autorizador = RecordingActionAuthorizer()

    authorize_requirement(
        autorizador,
        _ATOR,
        required_permissions_for_role(Role.OWNER),
        tenant_id=_TENANT,
        unit_ids=(_U2, _U1, _U2),
    )

    esperado = [
        AuthorizeActionCommand(actor_id=_ATOR, permission=p, tenant_id=_TENANT, unit_id=u)
        for p in (
            Permission.MANAGE_JOB_FUNCTIONS,
            Permission.MANAGE_STAFF,
            Permission.MANAGE_TENANT,
            Permission.MANAGE_USERS,
        )
        for u in (_U2, _U1, _U2)
    ]
    assert autorizador.calls == esperado


def test_sem_unidade_um_pedido_sem_unidade_por_permissao() -> None:
    autorizador = RecordingActionAuthorizer()

    authorize_requirement(
        autorizador,
        _ATOR,
        frozenset({Permission.MANAGE_USERS, Permission.MANAGE_PLATFORM}),
        tenant_id=None,
    )

    assert autorizador.calls == [
        AuthorizeActionCommand(actor_id=_ATOR, permission=Permission.MANAGE_PLATFORM),
        AuthorizeActionCommand(actor_id=_ATOR, permission=Permission.MANAGE_USERS),
    ]


def test_a_primeira_recusa_interrompe_e_sobe_crua() -> None:
    autorizador = DenyingActionAuthorizer()

    with pytest.raises(type(autorizador.denial)) as erro:
        authorize_requirement(
            autorizador,
            _ATOR,
            frozenset({Permission.MANAGE_USERS, Permission.MANAGE_STAFF}),
            tenant_id=_TENANT,
            unit_ids=(_U1, _U2),
        )

    assert erro.value is autorizador.denial
    assert len(autorizador.calls) == 1


def test_devolve_o_resultado_do_primeiro_pedido() -> None:
    autorizado = authorize_requirement(
        RecordingActionAuthorizer(),
        _ATOR,
        frozenset({Permission.MANAGE_TENANT}),
        tenant_id=_TENANT,
    )

    assert autorizado.user_id == INFIDEL_ACTOR


def _autorizador_real() -> tuple[AuthorizeActionUseCase, InMemoryUserRepository]:
    users = InMemoryUserRepository()
    units = InMemoryUnitRepository()
    units.add(Unit(id=_U1, restaurant_id=_TENANT, name="Centro"))
    return AuthorizeActionUseCase(users=users, units=units), users


def test_ator_inexistente_vira_credencial_invalida() -> None:
    """R5 — a tradução de `authorize_at_boundary`, que agora vale no use case."""
    autorizador, _ = _autorizador_real()

    with pytest.raises(InvalidAccessTokenError) as erro:
        authorize_requirement(
            autorizador, _ATOR, frozenset({Permission.MANAGE_TENANT}), tenant_id=_TENANT
        )

    assert isinstance(erro.value.__cause__, UserNotFoundError)


def test_unidade_inexistente_vira_nao_visivel() -> None:
    """R5 — "não existe" e "existe e não é sua" são a mesma resposta."""
    autorizador, users = _autorizador_real()
    owner = User(id=_ATOR, email=Email("dono@x.com"), role=Role.OWNER, tenant_id=_TENANT)
    users.add(owner, PasswordHash("hashed::x"), ())

    with pytest.raises(UnitNotVisibleError) as erro:
        authorize_requirement(
            autorizador,
            _ATOR,
            frozenset({Permission.MANAGE_USERS}),
            tenant_id=_TENANT,
            unit_ids=(UnitId("unidade-que-nao-existe"),),
        )

    assert isinstance(erro.value.__cause__, UnitNotFoundError)


def test_recusa_de_rbac_sobe_sem_traducao() -> None:
    autorizador, users = _autorizador_real()
    employee = User(id=_ATOR, email=Email("e@x.com"), role=Role.EMPLOYEE, tenant_id=_TENANT)
    users.add(employee, PasswordHash("hashed::x"), ())

    with pytest.raises(PermissionDeniedError):
        authorize_requirement(
            autorizador, _ATOR, frozenset({Permission.MANAGE_USERS}), tenant_id=_TENANT
        )

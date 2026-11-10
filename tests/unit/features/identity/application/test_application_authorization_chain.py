"""Cadeia real: os use cases de identity sobre o `AuthorizeActionUseCase` de produção (CA06, CA12).

Concept 2.7 §6, "Matriz da cadeia real". Os dublês de `test_use_cases_authorize.py`
provam a **forma** (pede o requisito certo, não faz nada se negado); esta suíte prova
o **resultado**: com o autorizador de verdade, sobre repositórios em memória com os
tenants A e B, nenhuma chamada direta — sem HTTP, como faria um CLI, um worker ou um
seed — cria `platform_admin` nem `owner` fora do tenant do ator, e cada recusa sai com
o tipo exato que a ordem dos passos de `AuthorizeActionUseCase` determina.

"Nenhum efeito" aqui é medido pelo estado: contas, restaurantes, unidades, tokens e
e-mails iguais antes e depois.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    CreateUnitCommand,
    CreateUserCommand,
    InviteOwnerCommand,
    InviteUserCommand,
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    PermissionDeniedError,
    TenantNotVisibleError,
    UnitNotVisibleError,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_owner import (
    InviteOwnerUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
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
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
_A = RestaurantId("rest-a")
_B = RestaurantId("rest-b")
_UA = UnitId("unit-a")
_UB = UnitId("unit-b")

# Os atores. Os de A com tenant A e, os escopados por unidade, membros de `unit-a`.
_ATORES: dict[str, tuple[Role, RestaurantId | None]] = {
    "owner-a": (Role.OWNER, _A),
    "manager-a": (Role.MANAGER, _A),
    "hr-a": (Role.HR, _A),
    "employee-a": (Role.EMPLOYEE, _A),
    "platform-admin": (Role.PLATFORM_ADMIN, None),
    "owner-b": (Role.OWNER, _B),
}
_PAPEIS_DA_MATRIZ = ("owner-a", "manager-a", "hr-a", "employee-a", "platform-admin")


class _Mundo:
    """Dois tenants, uma unidade em cada, os atores — e os cinco use cases sobre eles."""

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.restaurants = InMemoryRestaurantRepository()
        self.units = InMemoryUnitRepository()
        self.tokens = InMemoryPasswordSetupTokenRepository()
        self.sender = RecordingEmailSender()
        for tenant in (_A, _B):
            self.restaurants.add(Restaurant(id=tenant, name=f"Cantina {tenant}"))
        self.units.add(Unit(id=_UA, restaurant_id=_A, name="Centro A"))
        self.units.add(Unit(id=_UB, restaurant_id=_B, name="Centro B"))
        for ator, (papel, tenant) in _ATORES.items():
            user = User(id=UserId(ator), email=Email(f"{ator}@x.com"), role=papel, tenant_id=tenant)
            escopado = papel in (Role.MANAGER, Role.HR, Role.EMPLOYEE)
            vinculos = (user.link_to_unit(self.units.units[_UA]),) if escopado else ()
            self.users.add(user, PasswordHash("hashed::x"), vinculos)

        autorizador = AuthorizeActionUseCase(users=self.users, units=self.units)
        convite = {
            "users": self.users,
            "restaurants": self.restaurants,
            "hasher": FakePasswordHasher(),
            "tokens": self.tokens,
            "token_issuer": FakeSetupTokenIssuer(),
            "email_sender": self.sender,
            "id_generator": FakeIdGenerator(),
            "clock": FakeClock(_AGORA),
            "invitation_ttl": timedelta(hours=72),
            "base_url": "https://app.exemplo.com",
            "authorizer": autorizador,
        }
        self.provision_restaurant = ProvisionRestaurantUseCase(
            **convite,
            unit_of_work=InMemoryUnitOfWork(self.restaurants, self.users, self.tokens),
        )
        self.invite_owner = InviteOwnerUseCase(
            **convite, unit_of_work=InMemoryUnitOfWork(self.users, self.tokens)
        )
        self.invite_user = InviteUserUseCase(
            **convite,
            units=self.units,
            unit_of_work=InMemoryUnitOfWork(self.users, self.tokens),
        )
        self.create_unit = CreateUnitUseCase(
            units=self.units,
            restaurants=self.restaurants,
            id_generator=FakeIdGenerator(),
            authorizer=autorizador,
        )
        self.create_user = CreateUserUseCase(
            users=self.users,
            restaurants=self.restaurants,
            units=self.units,
            hasher=FakePasswordHasher(),
            id_generator=FakeIdGenerator(),
            authorizer=autorizador,
        )

    def estado(self) -> tuple[object, ...]:
        return (
            dict(self.users.users),
            list(self.users.memberships),
            dict(self.restaurants.restaurants),
            dict(self.units.units),
            dict(self.tokens.tokens),
            self.sender.sent,
        )


# Cada caso: ator → execução no mundo. `role=owner` em tenant B (o critério da #184,
# "dono em tenant alheio") e `role=platform_admin` sem tenant (a chamada direta).
_Caso = Callable[[_Mundo, UserId], object]
_CASOS: dict[str, _Caso] = {
    "provision_restaurant": lambda m, a: m.provision_restaurant.execute(
        ProvisionRestaurantCommand(actor_id=a, name="Nova", owner_email=Email("nd@x.com"))
    ),
    "invite_owner em B": lambda m, a: m.invite_owner.execute(
        InviteOwnerCommand(actor_id=a, email=Email("db@x.com"), tenant_id=_B)
    ),
    "create_unit em B": lambda m, a: m.create_unit.execute(
        CreateUnitCommand(actor_id=a, restaurant_id=_B, name="Filial B")
    ),
    "create_user owner em B": lambda m, a: m.create_user.execute(
        CreateUserCommand(
            actor_id=a, email=Email("ob@x.com"), plain_password="s", role=Role.OWNER, tenant_id=_B
        )
    ),
    "invite_user owner em B": lambda m, a: m.invite_user.execute(
        InviteUserCommand(actor_id=a, email=Email("ob@x.com"), role=Role.OWNER, tenant_id=_B)
    ),
    "create_user platform_admin": lambda m, a: m.create_user.execute(
        CreateUserCommand(
            actor_id=a,
            email=Email("pa@x.com"),
            plain_password="s",
            role=Role.PLATFORM_ADMIN,
            tenant_id=None,
        )
    ),
    "invite_user platform_admin": lambda m, a: m.invite_user.execute(
        InviteUserCommand(
            actor_id=a, email=Email("pa@x.com"), role=Role.PLATFORM_ADMIN, tenant_id=None
        )
    ),
}

_P = PermissionDeniedError
_T = TenantNotVisibleError
# A matriz do concept 2.7 §6, transcrita; `None` = concede (controle positivo).
_MATRIZ: dict[str, tuple[type[Exception] | None, ...]] = {
    #                              owner-a manager-a hr-a employee-a platform-admin
    "provision_restaurant": (_P, _P, _P, _P, None),
    "invite_owner em B": (_P, _P, _P, _P, None),
    "create_unit em B": (_T, _P, _P, _P, _P),
    "create_user owner em B": (_T, _T, _T, _P, _P),
    "invite_user owner em B": (_T, _T, _T, _P, _P),
    "create_user platform_admin": (_P, _P, _P, _P, _P),
    "invite_user platform_admin": (_P, _P, _P, _P, _P),
}

_CELULAS = [
    (caso, ator, esperado)
    for caso, linha in _MATRIZ.items()
    for ator, esperado in zip(_PAPEIS_DA_MATRIZ, linha, strict=True)
]


def test_a_matriz_cobre_todo_caso() -> None:
    assert set(_MATRIZ) == set(_CASOS)


@pytest.mark.parametrize(
    ("caso", "ator", "esperado"),
    [c for c in _CELULAS if c[2] is not None],
    ids=lambda v: getattr(v, "__name__", v),
)
def test_chamada_direta_negada_com_o_tipo_exato_e_sem_efeito(
    caso: str, ator: str, esperado: type[Exception]
) -> None:
    """CA06 — cada célula negada da matriz, pela cadeia de produção."""
    mundo = _Mundo()
    antes = mundo.estado()

    with pytest.raises(esperado) as erro:
        _CASOS[caso](mundo, UserId(ator))

    assert type(erro.value) is esperado
    assert mundo.estado() == antes


@pytest.mark.parametrize(("caso", "ator"), [(c, a) for c, a, e in _CELULAS if e is None], ids=str)
def test_plataforma_provisiona_e_convida_dono(caso: str, ator: str) -> None:
    """CA06 — controle positivo das células que concedem."""
    mundo = _Mundo()

    _CASOS[caso](mundo, UserId(ator))

    assert len(mundo.sender.sent) == 1


def test_dono_de_b_cria_unidade_e_dono_em_b() -> None:
    """Controle positivo: o mesmo command, pelo dono do tenant certo, passa."""
    mundo = _Mundo()

    _CASOS["create_unit em B"](mundo, UserId("owner-b"))
    criado = _CASOS["create_user owner em B"](mundo, UserId("owner-b"))

    assert {u.restaurant_id for u in mundo.units.units.values()} == {_A, _B}
    unidades_em_b = [u for u in mundo.units.units.values() if u.restaurant_id == _B]
    assert [u.name for u in unidades_em_b] == ["Centro B", "Filial B"]
    assert criado.tenant_id == _B  # type: ignore[attr-defined]


def test_gerente_cria_funcionario_na_propria_unidade() -> None:
    """Controle positivo de papel escopado por unidade: sem ele, uma regressão por
    excesso de negação (gerente barrado na própria unidade) só apareceria no e2e."""
    mundo = _Mundo()

    criado = mundo.create_user.execute(
        CreateUserCommand(
            actor_id=UserId("manager-a"),
            email=Email("func@x.com"),
            plain_password="s",
            role=Role.EMPLOYEE,
            tenant_id=_A,
            unit_ids=(_UA,),
        )
    )

    assert criado.unit_ids == (_UA,)


def test_ator_inexistente_e_credencial_invalida_sem_efeito() -> None:
    """CA12 — a tradução de `authorize_at_boundary` vale dentro do use case."""
    mundo = _Mundo()
    antes = mundo.estado()

    with pytest.raises(InvalidAccessTokenError):
        _CASOS["create_unit em B"](mundo, UserId("ninguem"))

    assert mundo.estado() == antes


def test_unidade_inexistente_e_nao_visivel_sem_efeito() -> None:
    """CA12 — "não existe" e "existe e não é sua" são a mesma resposta, também fora
    do HTTP (antes da Stage 2.7 o use case respondia `UnitNotFoundError`)."""
    mundo = _Mundo()
    antes = mundo.estado()

    with pytest.raises(UnitNotVisibleError):
        mundo.invite_user.execute(
            InviteUserCommand(
                actor_id=UserId("owner-a"),
                email=Email("x@x.com"),
                role=Role.EMPLOYEE,
                tenant_id=_A,
                unit_ids=(UnitId("unidade-que-nao-existe"),),
            )
        )

    assert mundo.estado() == antes

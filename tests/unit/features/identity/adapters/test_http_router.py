"""Testes das rotas de tenancy, pela app FastAPI montada com fakes.

Montar a app de verdade (e não chamar as funções de rota diretamente) é o que faz
estes testes exercitarem o caminho completo: `Depends`, guard, use case, mapa de
erro e serialização. Chamar a função nua pularia justamente as camadas onde um
adapter costuma errar.

Os repositórios são fakes; o que se testa aqui é **a rota**, não a persistência.
O caminho com Postgres real é a Task 12.
"""

import importlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_restaurant import (
    CreateRestaurantUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
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
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

router_module = importlib.import_module("restaurant_hub.features.identity.adapters.in.http.router")
dependencies_module = importlib.import_module(
    "restaurant_hub.features.identity.adapters.in.http.dependencies"
)
error_handlers_module = importlib.import_module(
    "restaurant_hub.features.identity.adapters.in.http.error_handlers"
)

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_TENANT = RestaurantId("rest-1")
_OUTRO_TENANT = RestaurantId("rest-2")
_SENHA = "s3nha-valida"


class _Ambiente:
    """App real montada com fakes — o mesmo caminho que o composition root monta."""

    def __init__(self) -> None:
        self.restaurants = InMemoryRestaurantRepository()
        self.units = InMemoryUnitRepository()
        self.users = InMemoryUserRepository()
        self.clock = FakeClock(_NOW)
        self.issuer = FakeTokenIssuer(clock=self.clock)
        self.hasher = FakePasswordHasher()

        autorizar = AuthorizeActionUseCase(users=self.users, units=self.units)
        guard = dependencies_module.IdentityGuard(
            token_issuer=self.issuer, authorize_action=autorizar
        )

        self.app = FastAPI()
        error_handlers_module.register_identity_error_handlers(self.app)
        self.app.dependency_overrides.update(
            {
                router_module._get_guard: lambda: guard,
                router_module._get_create_restaurant: lambda: CreateRestaurantUseCase(
                    restaurants=self.restaurants, id_generator=FakeIdGenerator()
                ),
                router_module._get_create_unit: lambda: CreateUnitUseCase(
                    units=self.units,
                    restaurants=self.restaurants,
                    id_generator=FakeIdGenerator(),
                ),
                router_module._get_create_user: lambda: CreateUserUseCase(
                    users=self.users,
                    restaurants=self.restaurants,
                    units=self.units,
                    hasher=self.hasher,
                    id_generator=FakeIdGenerator(),
                ),
            }
        )
        self.app.include_router(router_module.router, prefix="/api/v1")

    def com_restaurante(self, restaurant_id: RestaurantId = _TENANT) -> RestaurantId:
        self.restaurants.add(Restaurant(id=restaurant_id, name="Cantina"))
        return restaurant_id

    def com_unidade(self, unit_id: str, tenant_id: RestaurantId = _TENANT) -> UnitId:
        unit = Unit(id=UnitId(unit_id), restaurant_id=tenant_id, name="Unidade")
        self.units.add(unit)
        return unit.id

    def com_usuario(
        self,
        *,
        user_id: str,
        role: Role,
        tenant_id: RestaurantId | None,
        unidades: tuple[UnitId, ...] = (),
    ) -> User:
        user = User(
            id=UserId(user_id),
            email=Email(f"{user_id}@x.com"),
            role=role,
            tenant_id=tenant_id,
        )
        memberships = tuple(user.link_to_unit(self.units.units[u]) for u in unidades)
        self.users.add(user, PasswordHash("hashed::x"), memberships)
        return user

    def auth(self, user: User) -> dict[str, str]:
        token = self.issuer.issue_access_token(
            AccessTokenClaims(
                subject=user.id,
                role=user.role,
                tenant_id=user.tenant_id,
                session_id=SessionId("sess-1"),
                expires_at=_NOW + timedelta(minutes=15),
            )
        )
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ambiente() -> _Ambiente:
    return _Ambiente()


@pytest.fixture
async def client(ambiente: _Ambiente) -> Iterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


# ---------------------------------------------------------------------------
# CA11 — POST /restaurants
# ---------------------------------------------------------------------------


async def test_platform_admin_cria_restaurante(ambiente: _Ambiente, client: AsyncClient) -> None:
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        "/api/v1/restaurants", json={"name": "Cantina"}, headers=ambiente.auth(admin)
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["name"] == "Cantina"


async def test_owner_nao_cria_restaurante(ambiente: _Ambiente, client: AsyncClient) -> None:
    """CA11 — só `platform_admin` cria tenant (decisão do sponsor)."""
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/restaurants", json={"name": "Outra"}, headers=ambiente.auth(owner)
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_sem_token_e_401_com_www_authenticate(client: AsyncClient) -> None:
    resposta = await client.post("/api/v1/restaurants", json={"name": "X"})

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("corpo", "cenario"),
    [
        ({"name": "X"}, "corpo-valido"),
        ({"campo": "errado"}, "corpo-malformado"),
        ({}, "corpo-vazio"),
    ],
)
async def test_sem_credencial_o_401_vem_antes_da_validacao_do_corpo(
    client: AsyncClient, corpo: dict[str, str], cenario: str
) -> None:
    """A autenticação é `Depends`, então roda ANTES da validação do corpo.

    Se ela vivesse no corpo da rota, o 422 da validação chegaria primeiro para o
    corpo malformado — e um cliente **sem credencial nenhuma** passaria a
    distinguir "meu corpo tem forma válida" de "não tem", sondando o schema de
    endpoints protegidos. Com o guard como dependência, os três cenários são
    indistinguíveis.
    """
    resposta = await client.post("/api/v1/restaurants", json=corpo)

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED


# ---------------------------------------------------------------------------
# CA24 — POST /restaurants/{id}/owners
# ---------------------------------------------------------------------------


async def test_platform_admin_provisiona_owner_com_tenant_do_path(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """CA24 — o tenant vem do PATH, não do ator (que não tem nenhum)."""
    ambiente.com_restaurante()
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        f"/api/v1/restaurants/{_TENANT}/owners",
        json={"email": "dono@x.com", "password": _SENHA},
        headers=ambiente.auth(admin),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["tenant_id"] == _TENANT
    assert resposta.json()["role"] == "owner"


async def test_restaurante_inexistente_devolve_404_sem_gravar_usuario(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """CA24, metade destrutiva: 404 **e** nada gravado."""
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)
    antes = len(ambiente.users.users)

    resposta = await client.post(
        "/api/v1/restaurants/rest-que-nao-existe/owners",
        json={"email": "dono@x.com", "password": _SENHA},
        headers=ambiente.auth(admin),
    )

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    assert len(ambiente.users.users) == antes


async def test_owner_nao_provisiona_outro_owner_pela_rota_de_plataforma(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        f"/api/v1/restaurants/{_TENANT}/owners",
        json={"email": "outro@x.com", "password": _SENHA},
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


# ---------------------------------------------------------------------------
# CA12 — POST /restaurants/{id}/units
# ---------------------------------------------------------------------------


async def test_owner_cria_unidade_no_proprio_tenant(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        f"/api/v1/restaurants/{_TENANT}/units",
        json={"name": "Filial Centro"},
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["restaurant_id"] == _TENANT


async def test_owner_de_outro_tenant_nao_cria_unidade(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """CA12 — o isolamento entre tenants, pelo caminho HTTP real."""
    ambiente.com_restaurante()
    ambiente.com_restaurante(_OUTRO_TENANT)
    intruso = ambiente.com_usuario(user_id="intruso", role=Role.OWNER, tenant_id=_OUTRO_TENANT)

    resposta = await client.post(
        f"/api/v1/restaurants/{_TENANT}/units",
        json={"name": "Filial Invasora"},
        headers=ambiente.auth(intruso),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize("papel", [Role.MANAGER, Role.HR, Role.EMPLOYEE])
async def test_papeis_sem_manage_tenant_nao_criam_unidade(
    ambiente: _Ambiente, client: AsyncClient, papel: Role
) -> None:
    ambiente.com_restaurante()
    unidade = ambiente.com_unidade("unit-1")
    ator = ambiente.com_usuario(user_id="ator", role=papel, tenant_id=_TENANT, unidades=(unidade,))

    resposta = await client.post(
        f"/api/v1/restaurants/{_TENANT}/units",
        json={"name": "Nova"},
        headers=ambiente.auth(ator),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_platform_admin_nao_cria_unidade(ambiente: _Ambiente, client: AsyncClient) -> None:
    """ "Acesso de plataforma não é acesso de restaurante" — o `owner` gerencia unidades."""
    ambiente.com_restaurante()
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        f"/api/v1/restaurants/{_TENANT}/units",
        json={"name": "Nova"},
        headers=ambiente.auth(admin),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


# ---------------------------------------------------------------------------
# CA13, CA14, CA15, CA20 — POST /users
# ---------------------------------------------------------------------------


async def test_owner_cria_usuario_com_tenant_do_ator(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users",
        json={"email": "novo@x.com", "password": _SENHA, "role": "manager"},
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["tenant_id"] == _TENANT


async def test_tenant_id_do_corpo_e_ignorado(ambiente: _Ambiente, client: AsyncClient) -> None:
    """CA13 — o corpo tenta injetar outro tenant e o servidor decide sozinho.

    A resposta é 201, não 422: o campo é **descartado**, não rejeitado. Rejeitar
    seria defensável, mas tornaria a defesa invisível — este teste é o que prova
    que o valor enviado não teve efeito nenhum.
    """
    ambiente.com_restaurante()
    ambiente.com_restaurante(_OUTRO_TENANT)
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users",
        json={
            "email": "novo@x.com",
            "password": _SENHA,
            "role": "employee",
            "tenant_id": _OUTRO_TENANT,
        },
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["tenant_id"] == _TENANT


async def test_manager_nao_cria_owner(ambiente: _Ambiente, client: AsyncClient) -> None:
    """CA14 — "não se concede o que não se detém", pelo caminho HTTP real."""
    ambiente.com_restaurante()
    unidade = ambiente.com_unidade("unit-1")
    manager = ambiente.com_usuario(
        user_id="manager", role=Role.MANAGER, tenant_id=_TENANT, unidades=(unidade,)
    )

    resposta = await client.post(
        "/api/v1/users",
        json={
            "email": "promovido@x.com",
            "password": _SENHA,
            "role": "owner",
            "unit_ids": [unidade],
        },
        headers=ambiente.auth(manager),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    ("papel_do_ator", "tenant_do_ator"),
    [
        (Role.OWNER, _TENANT),
        (Role.MANAGER, _TENANT),
        (Role.PLATFORM_ADMIN, None),
    ],
)
async def test_ninguem_cria_platform_admin(
    ambiente: _Ambiente,
    client: AsyncClient,
    papel_do_ator: Role,
    tenant_do_ator: RestaurantId | None,
) -> None:
    """CA20 — a garantia fail-closed, exercitada pela API por três papéis.

    Inclusive o próprio `platform_admin`: ele detém `manage_platform` mas não
    `manage_users`, então também não passa. A criação do primeiro admin é
    semeadura fora da API, como toda raiz de confiança (concept §13).
    """
    ambiente.com_restaurante()
    unidade = ambiente.com_unidade("unit-1")
    unidades = () if papel_do_ator is Role.PLATFORM_ADMIN else (unidade,)
    ator = ambiente.com_usuario(
        user_id="ator", role=papel_do_ator, tenant_id=tenant_do_ator, unidades=unidades
    )

    resposta = await client.post(
        "/api/v1/users",
        json={"email": "novo-admin@x.com", "password": _SENHA, "role": "platform_admin"},
        headers=ambiente.auth(ator),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_manager_cria_usuario_na_unidade_que_enxerga(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    ambiente.com_restaurante()
    unidade = ambiente.com_unidade("unit-1")
    manager = ambiente.com_usuario(
        user_id="manager", role=Role.MANAGER, tenant_id=_TENANT, unidades=(unidade,)
    )

    resposta = await client.post(
        "/api/v1/users",
        json={
            "email": "novo@x.com",
            "password": _SENHA,
            "role": "employee",
            "unit_ids": [unidade],
        },
        headers=ambiente.auth(manager),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["unit_ids"] == [unidade]


async def test_manager_nao_cria_usuario_em_unidade_que_nao_enxerga(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """CA15 — o eixo de visibilidade, pelo caminho HTTP real."""
    ambiente.com_restaurante()
    visivel = ambiente.com_unidade("unit-visivel")
    invisivel = ambiente.com_unidade("unit-invisivel")
    manager = ambiente.com_usuario(
        user_id="manager", role=Role.MANAGER, tenant_id=_TENANT, unidades=(visivel,)
    )

    resposta = await client.post(
        "/api/v1/users",
        json={
            "email": "novo@x.com",
            "password": _SENHA,
            "role": "employee",
            "unit_ids": [invisivel],
        },
        headers=ambiente.auth(manager),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_papel_desconhecido_e_422(ambiente: _Ambiente, client: AsyncClient) -> None:
    """A conversão texto→VO no router é o que faz isto ser erro de domínio."""
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users",
        json={"email": "novo@x.com", "password": _SENHA, "role": "imperador"},
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

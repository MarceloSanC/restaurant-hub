"""Testes das rotas de tenancy, pela app FastAPI montada com fakes.

Montar a app de verdade (e não chamar as funções de rota diretamente) é o que faz
estes testes exercitarem o caminho completo: `Depends`, guard, use case, mapa de
erro e serialização. Chamar a função nua pularia justamente as camadas onde um
adapter costuma errar.

Os repositórios são fakes; o que se testa aqui é **a rota**, não a persistência.
O caminho com Postgres real é a Task 12.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.identity.adapters.inbound.http import (
    dependencies as dependencies_module,
)
from restaurant_hub.features.identity.adapters.inbound.http import (
    error_handlers as error_handlers_module,
)
from restaurant_hub.features.identity.adapters.inbound.http import router as router_module
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
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
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
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
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_TENANT = RestaurantId("rest-1")
_OUTRO_TENANT = RestaurantId("rest-2")
_SENHA = "s3nha-valida"


class _SenderQuebravel(RecordingEmailSender):
    """Sender que pode ser quebrado **depois** de montado.

    O `RecordingEmailSender` decide falhar no construtor, e o grafo do `_Ambiente`
    é montado antes de o teste escolher o cenário. Este subtipo move a decisão
    para o corpo do teste.
    """

    def quebrar(self) -> None:
        self._fail_with = EmailSenderFailure("provedor fora do ar")


class _Ambiente:
    """App real montada com fakes — o mesmo caminho que o composition root monta."""

    def __init__(self) -> None:
        self.restaurants = InMemoryRestaurantRepository()
        self.units = InMemoryUnitRepository()
        self.users = InMemoryUserRepository()
        self.clock = FakeClock(_NOW)
        self.issuer = FakeTokenIssuer(clock=self.clock)
        self.hasher = FakePasswordHasher()
        self.setup_tokens = InMemoryPasswordSetupTokenRepository()
        self.sender = _SenderQuebravel()

        autorizar = AuthorizeActionUseCase(users=self.users, units=self.units)
        guard = dependencies_module.IdentityGuard(
            token_issuer=self.issuer, authorize_action=autorizar
        )

        self.app = FastAPI()
        error_handlers_module.register_identity_error_handlers(self.app)
        self.app.dependency_overrides.update(
            {
                router_module._get_guard: lambda: guard,
                router_module._get_provision_restaurant: lambda: ProvisionRestaurantUseCase(
                    restaurants=self.restaurants,
                    users=self.users,
                    hasher=self.hasher,
                    tokens=self.setup_tokens,
                    token_issuer=FakeSetupTokenIssuer(),
                    email_sender=self.sender,
                    id_generator=FakeIdGenerator(),
                    clock=self.clock,
                    invitation_ttl=timedelta(hours=72),
                    base_url="https://app.exemplo.com",
                    unit_of_work=InMemoryUnitOfWork(
                        self.restaurants, self.users, self.setup_tokens
                    ),
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
                router_module._get_invite_user: lambda: InviteUserUseCase(
                    users=self.users,
                    restaurants=self.restaurants,
                    units=self.units,
                    hasher=self.hasher,
                    tokens=self.setup_tokens,
                    token_issuer=FakeSetupTokenIssuer(),
                    email_sender=self.sender,
                    id_generator=FakeIdGenerator(),
                    clock=self.clock,
                    invitation_ttl=timedelta(hours=72),
                    base_url="https://app.exemplo.com",
                    unit_of_work=InMemoryUnitOfWork(self.users, self.setup_tokens),
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


def _tenant(nome: str = "Cantina", email: str = "dono@cantina.com") -> dict[str, object]:
    """Corpo de `POST /restaurants`: o restaurante e o e-mail do primeiro dono.

    Issue #67 (ADR 0.0.0014) juntou restaurante e dono; a #114 (ADR 0.0.0018)
    tirou a senha — o dono é convidado.
    """
    return {"name": nome, "owner": {"email": email}}


async def test_platform_admin_provisiona_restaurante_com_dono(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """Issue #67 — o restaurante nasce com o dono, numa chamada."""
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        "/api/v1/restaurants", json=_tenant(), headers=ambiente.auth(admin)
    )

    assert resposta.status_code == HTTPStatus.CREATED
    corpo = resposta.json()
    assert corpo["name"] == "Cantina"
    assert corpo["owner"]["email"] == "dono@cantina.com"
    assert corpo["owner"]["role"] == "owner"
    assert corpo["owner"]["tenant_id"] == corpo["id"]
    assert corpo["owner"]["unit_ids"] == []
    assert RestaurantId(corpo["id"]) in ambiente.restaurants.restaurants
    dono = ambiente.users.users[UserId(corpo["owner"]["id"])]
    assert (dono.role, dono.tenant_id) == (Role.OWNER, corpo["id"])
    assert ambiente.users.password_hashes[dono.id].startswith("unusable::")
    assert [m.to for m in ambiente.sender.sent] == ["dono@cantina.com"]


async def test_senha_enviada_por_cliente_antigo_nao_vira_a_senha_do_dono(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """ADR 0.0.0018 — a senha do dono não transita pela API de plataforma.

    O schema não tem o campo; uma `password` enviada mesmo assim é descartada como
    todo campo extra (nota 3 de `schemas.py`) e nunca chega ao hasher: o dono
    nasce pendente, e só o link do convite define a senha dele.
    """
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)
    corpo = _tenant()
    corpo["owner"] = {"email": "dono@cantina.com", "password": _SENHA}

    resposta = await client.post("/api/v1/restaurants", json=corpo, headers=ambiente.auth(admin))

    assert resposta.status_code == HTTPStatus.CREATED
    gravado = ambiente.users.password_hashes[UserId(resposta.json()["owner"]["id"])]
    assert gravado != ambiente.hasher.hash(_SENHA)
    assert ambiente.hasher.verify(_SENHA, gravado) is False
    assert _SENHA not in ambiente.sender.sent[0].body_text


async def test_resposta_do_provisionamento_nao_carrega_o_link_do_convite(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """O link existe só no e-mail (regra 1 da 2.5): nem token nem link na resposta."""
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        "/api/v1/restaurants", json=_tenant(), headers=ambiente.auth(admin)
    )

    corpo_do_email = ambiente.sender.sent[0].body_text
    _, _, resto = corpo_do_email.partition("token=")
    assert resto.split()[0] not in resposta.text
    assert "token" not in resposta.text


async def test_falha_do_sender_no_provisionamento_devolve_500(ambiente: _Ambiente) -> None:
    """ADR 0.0.0018 §4 — a falha de envio sobe como 5xx, com o tenant já comitado.

    `raise_app_exceptions=False` pelo mesmo motivo do teste de convite abaixo.
    """
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)
    ambiente.sender.quebrar()

    async with AsyncClient(
        transport=ASGITransport(app=ambiente.app, raise_app_exceptions=False),
        base_url="http://t",
    ) as cliente:
        resposta = await cliente.post(
            "/api/v1/restaurants", json=_tenant(), headers=ambiente.auth(admin)
        )

    assert resposta.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert len(ambiente.restaurants.restaurants) == 1
    assert ambiente.users.exists_by_email(Email("dono@cantina.com")) is True


async def test_resposta_do_provisionamento_nao_carrega_a_senha(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        "/api/v1/restaurants", json=_tenant(), headers=ambiente.auth(admin)
    )

    assert _SENHA not in resposta.text
    assert "password" not in resposta.json()["owner"]


async def test_email_do_dono_ocupado_devolve_409_sem_criar_restaurante(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        "/api/v1/restaurants", json=_tenant(email="admin@x.com"), headers=ambiente.auth(admin)
    )

    assert resposta.status_code == HTTPStatus.CONFLICT
    assert resposta.json() == {
        "detail": "e-mail já registrado: 'admin@x.com'",
        "type": "identity_error",
    }
    assert ambiente.restaurants.restaurants == {}


@pytest.mark.parametrize(
    "corpo",
    [
        _tenant(email="sem-arroba"),
        _tenant(nome="   "),
    ],
    ids=["email-invalido", "nome-vazio"],
)
async def test_corpo_invalido_devolve_422_sem_gravar_nada(
    ambiente: _Ambiente, client: AsyncClient, corpo: dict[str, object]
) -> None:
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)
    usuarios_antes = set(ambiente.users.users)

    resposta = await client.post("/api/v1/restaurants", json=corpo, headers=ambiente.auth(admin))

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert ambiente.restaurants.restaurants == {}
    assert set(ambiente.users.users) == usuarios_antes


async def test_provisionamento_sem_dono_e_422(ambiente: _Ambiente, client: AsyncClient) -> None:
    """O dono é obrigatório: não há caminho na API que crie restaurante sem dono."""
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)

    resposta = await client.post(
        "/api/v1/restaurants", json={"name": "Cantina"}, headers=ambiente.auth(admin)
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert ambiente.restaurants.restaurants == {}


async def test_papel_no_corpo_do_dono_e_ignorado(ambiente: _Ambiente, client: AsyncClient) -> None:
    """ADR 2.4.0003 §2b — nenhuma rota emite `platform_admin`: o papel não vem do request."""
    admin = ambiente.com_usuario(user_id="admin", role=Role.PLATFORM_ADMIN, tenant_id=None)
    corpo = _tenant()
    corpo["owner"] = {"email": "dono@cantina.com", "role": "platform_admin"}

    resposta = await client.post("/api/v1/restaurants", json=corpo, headers=ambiente.auth(admin))

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["owner"]["role"] == "owner"


async def test_owner_nao_cria_restaurante(ambiente: _Ambiente, client: AsyncClient) -> None:
    """CA11 — só `platform_admin` cria tenant (decisão do sponsor)."""
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/restaurants",
        json=_tenant(nome="Outra", email="novo@x.com"),
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN
    assert set(ambiente.restaurants.restaurants) == {_TENANT}
    assert not ambiente.users.exists_by_email(Email("novo@x.com"))


async def test_sem_token_e_401_com_www_authenticate(client: AsyncClient) -> None:
    resposta = await client.post("/api/v1/restaurants", json=_tenant(nome="X"))

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("corpo", "cenario"),
    [
        (_tenant(nome="X"), "corpo-valido"),
        ({"campo": "errado"}, "corpo-malformado"),
        ({}, "corpo-vazio"),
    ],
)
async def test_sem_credencial_o_401_vem_antes_da_validacao_do_corpo(
    client: AsyncClient, corpo: dict[str, object], cenario: str
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


@pytest.mark.parametrize(
    "provedor",
    [
        "_get_authenticate_user",
        "_get_refresh_session",
        "_get_revoke_session",
        "_get_provision_restaurant",
        "_get_create_unit",
        "_get_create_user",
        "_get_invite_user",
        "_get_request_password_reset",
        "_get_set_password_with_token",
        "_get_guard",
    ],
)
def test_provedor_nao_conectado_falha_alto(provedor: str) -> None:
    """Os `_get_*` são chaves de `dependency_overrides`, não fábricas.

    Se algum for chamado de verdade, o wiring do composition root não aconteceu —
    e a resposta certa é explodir na hora, com o nome da dependência na mensagem.
    Devolver `None` "para não quebrar" empurraria a falha três camadas adiante,
    onde ela apareceria como `AttributeError: 'NoneType'` sem pista da causa.
    """
    with pytest.raises(RuntimeError, match="composition root"):
        getattr(router_module, provedor)()


# ---------------------------------------------------------------------------
# Rota de convite — as MESMAS defesas de `POST /users` (Stage 2.5, CA7)
# ---------------------------------------------------------------------------


async def test_manager_nao_convida_usuario_em_unidade_que_nao_enxerga(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """A defesa 2 da rota de convite, que o Checkpoint C achou descoberta.

    O e2e não cobria: todos os convites de lá passam `unit_ids: []`, e com a
    lista vazia o parâmetro de unidades não muda nada.

    **Este teste sozinho não basta, e o par com o positivo abaixo é o que fecha.**
    Verificado por mutação real: removendo `unit_ids=unit_ids` da chamada a
    `guard.authorize_all`, este teste continua verde — `authorize_all` passa a ser
    chamado com `unit_ids=()`, o `manager` cai em `UnitScopeRequiredError` e o
    403 sai pelo motivo errado. Quem derruba a mutação é
    `test_manager_convida_em_unidade_que_enxerga`, que passa a receber 403 onde
    esperava 201. Um teste negativo isolado, aqui, seria falso verde.
    """
    ambiente.com_restaurante()
    visivel = ambiente.com_unidade("unit-visivel-conv")
    invisivel = ambiente.com_unidade("unit-invisivel-conv")
    manager = ambiente.com_usuario(
        user_id="manager-conv", role=Role.MANAGER, tenant_id=_TENANT, unidades=(visivel,)
    )

    resposta = await client.post(
        "/api/v1/users/invitations",
        json={"email": "convidado@x.com", "role": "employee", "unit_ids": [invisivel]},
        headers=ambiente.auth(manager),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_manager_convida_em_unidade_que_enxerga(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    """Contraparte positiva — e é ela quem mata a mutação (ver o teste acima).

    Sem este caso, qualquer implementação que respondesse 403 sempre passaria no
    teste negativo, inclusive uma que tivesse perdido a autorização por unidade.
    """
    ambiente.com_restaurante()
    visivel = ambiente.com_unidade("unit-ok-conv")
    manager = ambiente.com_usuario(
        user_id="manager-ok-conv", role=Role.MANAGER, tenant_id=_TENANT, unidades=(visivel,)
    )

    resposta = await client.post(
        "/api/v1/users/invitations",
        json={"email": "convidado-ok@x.com", "role": "employee", "unit_ids": [visivel]},
        headers=ambiente.auth(manager),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["unit_ids"] == [visivel]


async def test_manager_nao_convida_owner(ambiente: _Ambiente, client: AsyncClient) -> None:
    """ "Não se concede o que não se detém", também pela rota de convite."""
    ambiente.com_restaurante()
    manager = ambiente.com_usuario(user_id="manager-escalada", role=Role.MANAGER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users/invitations",
        json={"email": "novo-dono@x.com", "role": "owner", "unit_ids": []},
        headers=ambiente.auth(manager),
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_convite_nao_aceita_tenant_do_corpo(ambiente: _Ambiente, client: AsyncClient) -> None:
    """O tenant vem do ator. Campo extra no corpo é ignorado, não obedecido."""
    ambiente.com_restaurante()
    ambiente.com_restaurante(_OUTRO_TENANT)
    owner = ambiente.com_usuario(user_id="owner-conv", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users/invitations",
        json={
            "email": "convidado-tenant@x.com",
            "role": "manager",
            "unit_ids": [],
            "tenant_id": _OUTRO_TENANT,
        },
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["tenant_id"] == _TENANT


async def test_convite_de_papel_desconhecido_e_422(
    ambiente: _Ambiente, client: AsyncClient
) -> None:
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner-422", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users/invitations",
        json={"email": "x@x.com", "role": "faxineiro", "unit_ids": []},
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_convite_com_email_malformado_e_422(ambiente: _Ambiente, client: AsyncClient) -> None:
    """A conversão texto→VO no router é o que faz isto ser erro de domínio."""
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner-mail", role=Role.OWNER, tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/users/invitations",
        json={"email": "isto-nao-e-email", "role": "manager", "unit_ids": []},
        headers=ambiente.auth(owner),
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_falha_do_sender_no_convite_devolve_500(ambiente: _Ambiente) -> None:
    """Regra 13 no nível HTTP: a falha de envio **sobe**, e sobe como 5xx.

    O risco que isto fecha é o oposto do da rota de redefinição: se um handler
    convertesse a falha do provedor num 4xx plausível, quem convidou leria
    "requisição inválida" e tentaria de novo — enquanto a conta já existe e o
    e-mail nunca saiu. Aqui o barulho é o comportamento certo.

    O cliente é montado com `raise_app_exceptions=False` de propósito: com o
    default, a exceção escapa pelo transporte e nunca vira resposta, de modo que
    o teste observaria uma propriedade do cliente em vez do status da aplicação.
    """
    ambiente.com_restaurante()
    owner = ambiente.com_usuario(user_id="owner-500", role=Role.OWNER, tenant_id=_TENANT)
    ambiente.sender.quebrar()

    async with AsyncClient(
        transport=ASGITransport(app=ambiente.app, raise_app_exceptions=False),
        base_url="http://t",
    ) as cliente:
        resposta = await cliente.post(
            "/api/v1/users/invitations",
            json={"email": "convidado-500@x.com", "role": "manager", "unit_ids": []},
            headers=ambiente.auth(owner),
        )

    assert resposta.status_code == HTTPStatus.INTERNAL_SERVER_ERROR

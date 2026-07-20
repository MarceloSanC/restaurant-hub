"""Testes do guard de autenticação e da composição de autorização.

Dois grupos importam mais que o resto:

- **As quatro formas de 401** (CA10, CA21) — porque cada uma é uma porta, e uma
  delas aberta vale por todas fechadas.
- **A derivação do conjunto de permissões** (CA14, CA20) — porque é o que impede
  um `manager` de fabricar um `owner`, e a regra tem de sair do mapa de papéis da
  2.1, não de uma segunda tabela.
"""

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    PermissionDeniedError,
    UnitNotVisibleError,
    UnitScopeRequiredError,
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
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock

pytestmark = pytest.mark.unit

dependencies = importlib.import_module(
    "restaurant_hub.features.identity.adapters.in.http.dependencies"
)

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_TENANT = RestaurantId("rest-1")
_OUTRO_TENANT = RestaurantId("rest-2")


def _request(headers: dict[str, str] | None = None) -> Request:
    """Request ASGI mínimo — só o que o guard lê."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/users",
        "headers": Headers(headers or {}).raw,
    }
    return Request(scope)


class _Fixture:
    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.units = InMemoryUnitRepository()
        self.clock = FakeClock(_NOW)
        self.issuer = FakeTokenIssuer(clock=self.clock)
        self.guard = dependencies.IdentityGuard(
            token_issuer=self.issuer,
            authorize_action=AuthorizeActionUseCase(users=self.users, units=self.units),
        )

    def com_usuario(
        self,
        *,
        user_id: str = "user-1",
        role: Role = Role.OWNER,
        tenant_id: RestaurantId | None = _TENANT,
        unidades_vinculadas: tuple[UnitId, ...] = (),
    ) -> User:
        user = User(
            id=UserId(user_id),
            email=Email(f"{user_id}@restaurante.com"),
            role=role,
            tenant_id=tenant_id,
        )
        memberships = tuple(
            user.link_to_unit(self.units.units[unit_id]) for unit_id in unidades_vinculadas
        )
        self.users.add(user, PasswordHash("hashed::x"), memberships)
        return user

    def com_unidade(self, unit_id: str, tenant_id: RestaurantId = _TENANT) -> UnitId:
        unit = Unit(id=UnitId(unit_id), restaurant_id=tenant_id, name="Unidade")
        self.units.add(unit)
        return unit.id

    def token_de(self, user: User, *, expira_em: timedelta = timedelta(minutes=15)) -> str:
        return self.issuer.issue_access_token(
            AccessTokenClaims(
                subject=user.id,
                role=user.role,
                tenant_id=user.tenant_id,
                session_id=SessionId("sess-1"),
                expires_at=_NOW + expira_em,
            )
        )

    def autenticar(self, token: str) -> object:
        return self.guard.authenticate(_request({"Authorization": f"Bearer {token}"}))

    def ator(self, user: User, *, expira_em: timedelta = timedelta(minutes=15)) -> object:
        return self.autenticar(self.token_de(user, expira_em=expira_em))


# ---------------------------------------------------------------------------
# CA10 — as formas de 401
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("headers", "cenario"),
    [
        ({}, "header-ausente"),
        ({"Authorization": ""}, "header-vazio"),
        ({"Authorization": "Bearer"}, "sem-token"),
        ({"Authorization": "Bearer   "}, "token-em-branco"),
        ({"Authorization": "Basic dXNlcjpwYXNz"}, "esquema-basic"),
        ({"Authorization": "Token abc"}, "esquema-desconhecido"),
        ({"Authorization": "abc"}, "sem-esquema"),
    ],
)
def test_header_invalido_e_sempre_a_mesma_falha(headers: dict[str, str], cenario: str) -> None:
    """CA10 — sete formas de errar o header, uma só resposta.

    Distinguir "faltou o header" de "esquema errado" de "token vazio" diria ao
    cliente exatamente o que corrigir para avançar um passo — que é útil para
    quem está sondando e irrelevante para quem tem credencial.
    """
    with pytest.raises(InvalidAccessTokenError):
        dependencies.extract_bearer_token(_request(headers))


def test_esquema_bearer_e_case_insensitive() -> None:
    """RFC 7235: o esquema é case-insensitive. Recusar `bearer` quebraria clientes."""
    assert dependencies.extract_bearer_token(_request({"Authorization": "bearer abc"})) == "abc"
    assert dependencies.extract_bearer_token(_request({"Authorization": "BEARER abc"})) == "abc"


def test_token_nao_emitido_e_recusado() -> None:
    fixture = _Fixture()

    with pytest.raises(InvalidAccessTokenError):
        fixture.guard.authenticate(_request({"Authorization": "Bearer forjado"}))


def test_token_expirado_e_recusado() -> None:
    """A expiração é verificada em `authenticate`, que é onde o token é decodificado.

    O guard não a reimplementa — delega ao `TokenIssuer`. O que este teste
    garante é que ele não a **engole**: um `authenticate` que ignorasse a exceção
    do issuer faria o TTL de 15 minutos, que é a janela de revogação inteira do
    produto, virar decoração.
    """
    fixture = _Fixture()
    token = fixture.token_de(fixture.com_usuario(), expira_em=timedelta(minutes=15))
    assert fixture.autenticar(token) is not None

    fixture.clock.advance(timedelta(minutes=15))

    with pytest.raises(InvalidAccessTokenError):
        fixture.autenticar(token)


def test_ator_removido_do_banco_vira_401_e_nao_404() -> None:
    """CA21 — inversão deliberada do mapa global (concept §6).

    `UserNotFoundError` vale 404 quando o usuário é **alvo**. Vindo do guard, ele
    só pode ser o **ator** — e um token cujo sujeito sumiu é credencial inválida.
    Um 404 aqui responderia "restaurante não encontrado" a um problema de sessão.
    """
    fixture = _Fixture()
    user = fixture.com_usuario()
    ator = fixture.ator(user)
    fixture.users.users.clear()

    with pytest.raises(InvalidAccessTokenError):
        fixture.guard.authorize(ator, Permission.MANAGE_USERS, tenant_id=_TENANT)


# ---------------------------------------------------------------------------
# CA22 — o oráculo de enumeração cross-tenant
# ---------------------------------------------------------------------------


def test_unidade_inexistente_vira_unit_not_visible() -> None:
    """CA22 — 404 viraria oráculo de existência atravessando tenant.

    `UnitRepository.find_by_id` não filtra por tenant (por desenho: quem casa
    tenant e vínculo é o domínio). Sem esta tradução, um `manager` itera ids e lê
    404 = "não existe em lugar nenhum" contra 403 = "existe, em algum tenant".
    """
    fixture = _Fixture()
    unidade = fixture.com_unidade("unit-1")
    user = fixture.com_usuario(role=Role.MANAGER, unidades_vinculadas=(unidade,))
    ator = fixture.ator(user)

    with pytest.raises(UnitNotVisibleError):
        fixture.guard.authorize(
            ator,
            Permission.MANAGE_USERS,
            tenant_id=_TENANT,
            unit_id=UnitId("unidade-que-nao-existe"),
        )


def test_unidade_de_outro_tenant_tambem_e_recusada() -> None:
    """A outra metade do par: existe, mas não é sua.

    O status é o mesmo (403) e o corpo é constante (error_handlers), então as duas
    respostas são indistinguíveis — que é a propriedade que fecha o oráculo.
    """
    fixture = _Fixture()
    unidade_propria = fixture.com_unidade("unit-1")
    unidade_alheia = fixture.com_unidade("unit-de-outro", tenant_id=_OUTRO_TENANT)
    user = fixture.com_usuario(role=Role.MANAGER, unidades_vinculadas=(unidade_propria,))
    ator = fixture.ator(user)

    with pytest.raises(Exception) as excinfo:
        fixture.guard.authorize(
            ator, Permission.MANAGE_USERS, tenant_id=_TENANT, unit_id=unidade_alheia
        )

    # Faixa 403 nos dois casos — o corpo constante faz o resto (CA26).
    assert type(excinfo.value).__name__ in {"TenantNotVisibleError", "UnitNotVisibleError"}


# ---------------------------------------------------------------------------
# CA14 / CA20 — "não se concede o que não se detém"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("papel_alvo", "esperado"),
    [
        (Role.EMPLOYEE, {Permission.MANAGE_USERS}),
        (Role.MANAGER, {Permission.MANAGE_USERS}),
        (Role.HR, {Permission.MANAGE_USERS}),
        (Role.OWNER, {Permission.MANAGE_USERS, Permission.MANAGE_TENANT}),
        (Role.PLATFORM_ADMIN, {Permission.MANAGE_USERS, Permission.MANAGE_PLATFORM}),
    ],
)
def test_conjunto_de_permissoes_exigidas_por_papel_alvo(
    papel_alvo: Role, esperado: set[Permission]
) -> None:
    """A regra sai do mapa da 2.1, papel a papel — os cinco, sem exceção."""
    assert dependencies.required_permissions_for_role(papel_alvo) == esperado


def test_nenhum_papel_pode_criar_platform_admin() -> None:
    """CA20 — a garantia fail-closed, verificada em vez de argumentada.

    Criar um `platform_admin` exigiria `manage_users` mais `manage_platform`, e o
    mapa da 2.1 não dá os dois a ninguém: `platform_admin` tem só
    `manage_platform` ("acesso de plataforma não é acesso de restaurante").
    """
    exigido = dependencies.required_permissions_for_role(Role.PLATFORM_ADMIN)

    for papel in Role:
        assert not exigido.issubset(papel.permissions), (
            f"{papel.value} conseguiria criar um platform_admin"
        )


def test_manager_nao_cria_owner() -> None:
    """CA14 — a escalada concreta que a regra fecha, pelo caminho real do guard."""
    fixture = _Fixture()
    unidade = fixture.com_unidade("unit-1")
    manager = fixture.com_usuario(role=Role.MANAGER, unidades_vinculadas=(unidade,))
    ator = fixture.ator(manager)

    with pytest.raises(PermissionDeniedError):
        fixture.guard.authorize_all(
            ator,
            dependencies.required_permissions_for_role(Role.OWNER),
            tenant_id=_TENANT,
            unit_ids=(unidade,),
        )


def test_owner_cria_manager() -> None:
    """O contra-exemplo: sem ele, um guard que negasse tudo passaria no teste acima."""
    fixture = _Fixture()
    owner = fixture.com_usuario(role=Role.OWNER)

    autorizado = fixture.guard.authorize_all(
        fixture.ator(owner),
        dependencies.required_permissions_for_role(Role.MANAGER),
        tenant_id=_TENANT,
    )

    assert autorizado.actor_tenant_id == _TENANT


# ---------------------------------------------------------------------------
# Escopo de unidade — exigência, não filtro
# ---------------------------------------------------------------------------


def test_ator_escopado_sem_unidade_e_negado() -> None:
    """Omitir a unidade não promove ninguém (ADR 2.2.0002)."""
    fixture = _Fixture()
    unidade = fixture.com_unidade("unit-1")
    manager = fixture.com_usuario(role=Role.MANAGER, unidades_vinculadas=(unidade,))

    with pytest.raises(UnitScopeRequiredError):
        fixture.guard.authorize_all(
            fixture.ator(manager),
            frozenset({Permission.MANAGE_USERS}),
            tenant_id=_TENANT,
        )


def test_autoriza_uma_vez_por_unidade_requisitada() -> None:
    """Uma unidade visível não autoriza as outras — cada uma é checada.

    É o que impede um `manager` de criar um usuário vinculado à unidade que ele
    enxerga **e** a outra que ele não enxerga, na mesma requisição.
    """
    fixture = _Fixture()
    visivel = fixture.com_unidade("unit-visivel")
    invisivel = fixture.com_unidade("unit-invisivel")
    manager = fixture.com_usuario(role=Role.MANAGER, unidades_vinculadas=(visivel,))
    ator = fixture.ator(manager)

    with pytest.raises(UnitNotVisibleError):
        fixture.guard.authorize_all(
            ator,
            frozenset({Permission.MANAGE_USERS}),
            tenant_id=_TENANT,
            unit_ids=(visivel, invisivel),
        )


def test_guard_nao_tem_tabela_de_papeis_propria() -> None:
    """O adapter declara requisito; a política vive no domínio (ADR 2.4.0003).

    Uma segunda fonte de verdade sobre o que cada papel pode divergiria da
    primeira, e a divergência apareceria como escalada silenciosa. Este teste
    prova que a derivação é do mapa da 2.1 — mexer lá muda o resultado aqui.
    """
    esperado = frozenset({Permission.MANAGE_USERS}) | Role.OWNER.permissions

    assert dependencies.required_permissions_for_role(Role.OWNER) == esperado

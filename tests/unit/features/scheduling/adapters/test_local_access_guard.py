"""As leis do `AccessGuard` de scheduling contra a implementação de produção (Stage 4.5).

O fake as prova em `tests/unit/features/scheduling/application/test_access_guard_laws.py`;
aqui o sujeito é o `LocalAccessGuard` — lei que só um dos dois obrigados cumpre não é lei
(ADR 3.4.0001 §Implementation notes). Duas metades:

1. **Leis contra dublês** da fachada e do chamável de autenticação (o que o adapter recebe
   por construtor), com a conformidade de forma do dublê à fachada real asserida.
2. **A cadeia real** (CA12): `LocalAccessGuard` → `IdentityAccessFacade` →
   `AuthorizeActionUseCase` sobre os repositórios de identity em memória, com o ator vindo
   de um Bearer verificado pelo `IdentityGuard`. É o que pega uma constante de permissão do
   port divergente do enum de identity (`Permission(permission)` levanta `ValueError`) e o
   mapa de papéis da Stage 4.5 — papéis x as três permissões x membro e não membro x tenant
   omitido e nomeado.
"""

import datetime
import inspect
from typing import Final

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from restaurant_hub.features.identity.adapters.inbound.http.dependencies import IdentityGuard
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    PermissionDeniedError,
    TenantNotVisibleError,
    UnitNotVisibleError,
)
from restaurant_hub.features.identity.application.facade import (
    AccessGrant,
    AccessPrincipal,
    IdentityAccessFacade,
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
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from restaurant_hub.features.scheduling.adapters.out.identity.local_access_guard import (
    LocalAccessGuard,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
    AccessGuard,
)
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository

pytestmark = pytest.mark.unit


class _SpyAccessFacade:
    """`IdentityAccessFacade` de mentira: guarda o pedido, devolve ou levanta o pré-montado."""

    def __init__(self, grant: AccessGrant | None = None) -> None:
        self.grant = grant
        self.received: dict[str, object] = {}
        self.error: Exception | None = None

    def authorize(
        self,
        principal: AccessPrincipal,
        permission: str,
        *,
        tenant_id: str | None,
        unit_id: str | None,
    ) -> AccessGrant:
        self.received = {
            "principal": principal,
            "permission": permission,
            "tenant_id": tenant_id,
            "unit_id": unit_id,
        }
        if self.error is not None:
            raise self.error
        assert self.grant is not None
        return self.grant


class _SpyAuthentication:
    def __init__(self, principal: AccessPrincipal | None = None) -> None:
        self.principal = principal
        self.error: Exception | None = None
        self.requests: list[object] = []

    def __call__(self, request: object) -> AccessPrincipal:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        assert self.principal is not None
        return self.principal


def _guard(
    facade: _SpyAccessFacade, authentication: _SpyAuthentication | None = None
) -> LocalAccessGuard:
    return LocalAccessGuard(
        facade,  # type: ignore[arg-type]
        authentication or _SpyAuthentication(),
    )


def _grant(*, actor_tenant_id: str | None = "t1", role: str = "manager") -> AccessGrant:
    return AccessGrant(role=role, actor_tenant_id=actor_tenant_id, scope_unit_id="u1")


def _ator(*, tenant_id: str | None = "t1") -> AccessPrincipal:
    return AccessPrincipal(user_id="user-1", tenant_id=tenant_id)


# O eixo do tenant na chamada e o que tem de chegar à fachada: nomeado, omitido (o do
# ator) e vazio. O vazio é o que refuta a troca do teste de ausência por truthiness (só a
# ausência é resolvida; precedente de L-AG3 em staff).
_TENANT_RESOLVIDO = [
    pytest.param("t1", "t1", id="tenant-nomeado"),
    pytest.param(None, "t1", id="tenant-omitido"),
    pytest.param("", "", id="tenant-vazio"),
]

_PERMISSOES = [PERMISSION_VIEW_SCHEDULE, PERMISSION_MANAGE_SCHEDULE, PERMISSION_VIEW_OWN_SCHEDULE]


def _forma(alvo: object, metodo: str) -> list[tuple[str, object, object]]:
    return [
        (nome, parametro.kind, parametro.default)
        for nome, parametro in inspect.signature(getattr(alvo, metodo)).parameters.items()
        if nome != "self"
    ]


@pytest.mark.parametrize("metodo", ["authenticate", "authorize"])
def test_o_adapter_tem_a_forma_do_port(metodo: str) -> None:
    assert _forma(LocalAccessGuard, metodo) == _forma(AccessGuard, metodo)


def test_o_spy_tem_a_mesma_assinatura_da_fachada_real() -> None:
    assert _forma(_SpyAccessFacade, "authorize") == _forma(IdentityAccessFacade, "authorize")


def test_l_sg1_authenticate_repassa_e_nao_traduz() -> None:
    authentication = _SpyAuthentication()
    authentication.error = InvalidAccessTokenError()
    guard = _guard(_SpyAccessFacade(), authentication)
    pedido = object()
    with pytest.raises(InvalidAccessTokenError) as excinfo:
        guard.authenticate(pedido)
    assert excinfo.value is authentication.error
    assert authentication.requests == [pedido]


def test_authenticate_devolve_o_principal_do_chamavel() -> None:
    principal = _ator()
    guard = _guard(_SpyAccessFacade(), _SpyAuthentication(principal))
    assert guard.authenticate(object()) is principal


@pytest.mark.parametrize(
    "erro",
    [PermissionDeniedError("employee", "manage_schedule"), UnitNotVisibleError("user-1", "u1")],
    ids=["permissao", "unidade"],
)
def test_l_sg1_a_recusa_de_identity_sobe_crua(erro: Exception) -> None:
    facade = _SpyAccessFacade()
    facade.error = erro
    with pytest.raises(type(erro)) as excinfo:
        _guard(facade).authorize(_ator(), PERMISSION_MANAGE_SCHEDULE, unit_id="u1")
    assert excinfo.value is erro


@pytest.mark.parametrize(("pedido", "resolvido"), _TENANT_RESOLVIDO)
def test_l_sg5_so_a_ausencia_resolve_o_tenant_do_ator(pedido: str | None, resolvido: str) -> None:
    facade = _SpyAccessFacade(_grant())
    guard = _guard(facade)
    if pedido == "":
        # O tenant vazio chega à fachada como vazio e não vira escopo (L-SG2).
        with pytest.raises(PermissionDeniedError):
            guard.authorize(_ator(), PERMISSION_MANAGE_SCHEDULE, tenant_id=pedido, unit_id="u1")
    else:
        guard.authorize(_ator(), PERMISSION_MANAGE_SCHEDULE, tenant_id=pedido, unit_id="u1")
    assert facade.received == {
        "principal": _ator(),
        "permission": PERMISSION_MANAGE_SCHEDULE,
        "tenant_id": resolvido,
        "unit_id": "u1",
    }


@pytest.mark.parametrize(("pedido", "resolvido"), _TENANT_RESOLVIDO[:2])
def test_l_sg2_l_sg4_o_escopo_e_o_alvo_com_o_sujeito_do_token(
    pedido: str | None, resolvido: str
) -> None:
    escopo = _guard(_SpyAccessFacade(_grant())).authorize(
        _ator(), PERMISSION_VIEW_SCHEDULE, tenant_id=pedido, unit_id="u7"
    )
    assert (escopo.tenant_id, escopo.unit_id, escopo.user_id) == (resolvido, "u7", "user-1")


@pytest.mark.parametrize("tenant_do_ator", [None, ""], ids=["ausente", "vazio"])
@pytest.mark.parametrize("pedido", ["t1", None], ids=["tenant-nomeado", "tenant-omitido"])
def test_l_sg2_l_sg5_ator_sem_tenant_e_negado_mesmo_concedido(
    tenant_do_ator: str | None, pedido: str | None
) -> None:
    facade = _SpyAccessFacade(_grant(actor_tenant_id=tenant_do_ator, role="platform_admin"))
    with pytest.raises(PermissionDeniedError) as excinfo:
        _guard(facade).authorize(
            _ator(tenant_id=tenant_do_ator),
            PERMISSION_MANAGE_SCHEDULE,
            tenant_id=pedido,
            unit_id="u1",
        )
    # A mensagem vai para o log (o corpo 403 é constante): papel e permissão do grant.
    assert "platform_admin" in str(excinfo.value)
    assert PERMISSION_MANAGE_SCHEDULE in str(excinfo.value)


def test_l_sg2_o_escopo_traz_o_tenant_pedido_e_nao_o_lido_do_banco() -> None:
    """O escopo é o alvo pedido (ou resolvido) confirmado — não `grant.actor_tenant_id`.

    Na cadeia real identity força os dois a serem iguais; o dublê os separa para que a troca
    de um pelo outro no adapter não sobreviva (Checkpoint C, bloco 01–03).
    """
    facade = _SpyAccessFacade(_grant(actor_tenant_id="t-do-banco"))
    escopo = _guard(facade).authorize(
        _ator(), PERMISSION_VIEW_SCHEDULE, tenant_id="t1", unit_id="u1"
    )
    assert escopo.tenant_id == "t1"


def test_ator_que_nao_veio_do_guard_e_defeito_de_wiring() -> None:
    with pytest.raises(TypeError, match="object"):
        _guard(_SpyAccessFacade(_grant())).authorize(
            object(), PERMISSION_MANAGE_SCHEDULE, unit_id="u1"
        )


# ---------------------------------------------------------------------------
# A cadeia real (CA12)
# ---------------------------------------------------------------------------

_TENANT: Final = RestaurantId("tenant-a")
_OUTRO_TENANT: Final = RestaurantId("tenant-x")
_U1: Final = UnitId("u1")
_U2: Final = UnitId("u2")
_X1: Final = UnitId("x1")
_HASH: Final = PasswordHash("hashed::x")


class _Mundo:
    """Identity em memória, com o guard montado como no `composition_root`."""

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        units = InMemoryUnitRepository()
        units.add(Unit(id=_U1, restaurant_id=_TENANT, name="Centro"))
        units.add(Unit(id=_U2, restaurant_id=_TENANT, name="Praia"))
        units.add(Unit(id=_X1, restaurant_id=_OUTRO_TENANT, name="Outra"))
        self.tokens = FakeTokenIssuer()
        authorize_action = AuthorizeActionUseCase(users=self.users, units=units)
        identity_guard = IdentityGuard(self.tokens, authorize_action)
        self.guard = LocalAccessGuard(
            access=IdentityAccessFacade(authorize_action=authorize_action),
            authenticate_request=identity_guard.authenticate_principal,
        )

    def ator(self, papel: Role, tenant: RestaurantId | None, unidade: UnitId | None) -> object:
        """Usuário gravado em identity (membro de `unidade`, se houver) e o ator do token."""
        user_id = UserId(f"{papel.value}-{tenant}-{unidade}")
        vinculos = [UnitMembership(user_id=user_id, unit_id=unidade)] if unidade else []
        self.users.add(
            User(id=user_id, email=Email(f"{user_id}@x.com"), role=papel, tenant_id=tenant),
            _HASH,
            vinculos,
        )
        token = self.tokens.issue_access_token(
            AccessTokenClaims(
                subject=user_id,
                role=papel,
                tenant_id=tenant,
                session_id=SessionId(f"sessao-{user_id}"),
                expires_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
            )
        )
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/units/u1/calendar",
                "headers": Headers({"Authorization": f"Bearer {token}"}).raw,
            }
        )
        return self.guard.authenticate(request)


# A matriz da §4.4 do concept (ADR 4.5.0001), papel → permissões de escala da unidade.
_CONCEDIDAS: Final = {
    Role.OWNER: {
        PERMISSION_VIEW_SCHEDULE,
        PERMISSION_MANAGE_SCHEDULE,
        PERMISSION_VIEW_OWN_SCHEDULE,
    },
    Role.MANAGER: {
        PERMISSION_VIEW_SCHEDULE,
        PERMISSION_MANAGE_SCHEDULE,
        PERMISSION_VIEW_OWN_SCHEDULE,
    },
    Role.HR: {PERMISSION_VIEW_SCHEDULE, PERMISSION_VIEW_OWN_SCHEDULE},
    Role.EMPLOYEE: {PERMISSION_VIEW_OWN_SCHEDULE},
}


@pytest.mark.parametrize("tenant_pedido", [None, _TENANT], ids=["tenant-omitido", "tenant-nomeado"])
@pytest.mark.parametrize("permissao", _PERMISSOES)
@pytest.mark.parametrize("papel", list(_CONCEDIDAS))
def test_cadeia_real_papel_na_propria_unidade(
    papel: Role, permissao: str, tenant_pedido: str | None
) -> None:
    mundo = _Mundo()
    unidade = None if papel is Role.OWNER else _U1
    ator = mundo.ator(papel, _TENANT, unidade)
    if permissao in _CONCEDIDAS[papel]:
        escopo = mundo.guard.authorize(ator, permissao, tenant_id=tenant_pedido, unit_id=_U1)
        assert (escopo.tenant_id, escopo.unit_id) == (_TENANT, _U1)
        assert escopo.user_id == f"{papel.value}-{_TENANT}-{unidade}"
    else:
        with pytest.raises(PermissionDeniedError):
            mundo.guard.authorize(ator, permissao, tenant_id=tenant_pedido, unit_id=_U1)


@pytest.mark.parametrize("permissao", _PERMISSOES)
@pytest.mark.parametrize("papel", [Role.MANAGER, Role.HR, Role.EMPLOYEE])
def test_cadeia_real_nao_membro_da_unidade_e_negado(papel: Role, permissao: str) -> None:
    mundo = _Mundo()
    ator = mundo.ator(papel, _TENANT, _U2)
    esperado = UnitNotVisibleError if permissao in _CONCEDIDAS[papel] else PermissionDeniedError
    with pytest.raises(esperado):
        mundo.guard.authorize(ator, permissao, unit_id=_U1)


@pytest.mark.parametrize("permissao", _PERMISSOES)
def test_cadeia_real_dono_de_outro_tenant_e_negado_no_tenant_nomeado(permissao: str) -> None:
    mundo = _Mundo()
    ator = mundo.ator(Role.OWNER, _OUTRO_TENANT, None)
    with pytest.raises(TenantNotVisibleError):
        mundo.guard.authorize(ator, permissao, tenant_id=_TENANT, unit_id=_U1)


@pytest.mark.parametrize("permissao", _PERMISSOES)
def test_cadeia_real_dono_de_outro_tenant_com_tenant_omitido_nao_alcanca_a_unidade_alheia(
    permissao: str,
) -> None:
    mundo = _Mundo()
    ator = mundo.ator(Role.OWNER, _OUTRO_TENANT, None)
    # O tenant resolvido é o do ator (tenant-x) e a unidade é de tenant-a: identity recusa
    # pela coerência do par alvo — 403 de corpo constante, como a unidade invisível.
    with pytest.raises(TenantNotVisibleError):
        mundo.guard.authorize(ator, permissao, unit_id=_U1)


@pytest.mark.parametrize("permissao", _PERMISSOES)
def test_cadeia_real_platform_admin_e_negado(permissao: str) -> None:
    mundo = _Mundo()
    ator = mundo.ator(Role.PLATFORM_ADMIN, None, None)
    with pytest.raises(PermissionDeniedError):
        mundo.guard.authorize(ator, permissao, unit_id=_U1)


# --- auditoria de testes, rodada 2 (Task 12 extra): L-SG3 no adapter ---------------------------


class _FachadaPorAlvo(_SpyAccessFacade):
    """Concede só a unidade `u1` e registra cada pedido — uma decisão por alvo."""

    def __init__(self) -> None:
        super().__init__(_grant())
        self.pedidos: list[tuple[str, str | None]] = []

    def authorize(
        self,
        principal: AccessPrincipal,
        permission: str,
        *,
        tenant_id: str | None,
        unit_id: str | None,
    ) -> AccessGrant:
        self.pedidos.append((permission, unit_id))
        if unit_id != "u1" or permission != PERMISSION_MANAGE_SCHEDULE:
            raise PermissionDeniedError("manager", permission)
        return super().authorize(principal, permission, tenant_id=tenant_id, unit_id=unit_id)


def test_l_sg3_cada_alvo_e_uma_decisao_no_adapter() -> None:
    """Autorizar u1 não autoriza u2, e uma permissão não autoriza outra (L-SG3)."""
    fachada = _FachadaPorAlvo()
    guard = _guard(fachada)
    escopo = guard.authorize(_ator(), PERMISSION_MANAGE_SCHEDULE, unit_id="u1")
    assert escopo.unit_id == "u1"
    with pytest.raises(PermissionDeniedError):
        guard.authorize(_ator(), PERMISSION_MANAGE_SCHEDULE, unit_id="u2")
    with pytest.raises(PermissionDeniedError):
        guard.authorize(_ator(), PERMISSION_VIEW_SCHEDULE, unit_id="u1")
    assert fachada.pedidos == [
        (PERMISSION_MANAGE_SCHEDULE, "u1"),
        (PERMISSION_MANAGE_SCHEDULE, "u2"),
        (PERMISSION_VIEW_SCHEDULE, "u1"),
    ]

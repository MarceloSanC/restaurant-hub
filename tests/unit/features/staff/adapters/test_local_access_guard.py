"""As quatro leis do port `AccessGuard`, contra a implementação de produção (#47).

**Migrado de `test_composition_root_staff.py`** junto com a classe: até a issue
#47 o tradutor era `composition_root._IdentityAccessGuard`, e as suas leis eram
cobradas ali. O fake as prova em
`tests/unit/features/staff/application/test_access_guard_laws.py`; aqui o sujeito
é a outra implementação, porque lei que só um dos dois obrigados cumpre não é
lei (ADR 3.4.0001 §Implementation notes). Os eixos parametrizados (`_ALVOS`,
`_TENANT_NA_CHAMADA`, `_TENANT_RESOLVIDO`, `_ATOR_SEM_TENANT`) têm a **mesma
forma** que os da suíte do fake, de propósito — cobrar as duas com conjuntos de
valores diferentes é o sinal mais forte da família "lei universal, representante
estreito", e foi assim que a Stage 3.4 vazou duas mutações.

**Os dublês são da fachada e do chamável de autenticação**, não do
`IdentityGuard`: é o que o adapter recebe por construtor. A conformidade de forma
do dublê com a `IdentityAccessFacade` real é asserida abaixo — o dublê que
divergisse da fachada faria os testes de comportamento passarem contra uma forma
que não existe. A cadeia **real** (adapter → fachada → use case sobre fakes de
identity) é exercitada em `test_application_authorization_chain.py`.
"""

import contextlib
import inspect

import pytest

from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    PermissionDeniedError,
    UnitNotVisibleError,
)
from restaurant_hub.features.identity.application.facade import (
    AccessGrant,
    AccessPrincipal,
    IdentityAccessFacade,
)
from restaurant_hub.features.staff.adapters.out.identity.local_access_guard import (
    LocalAccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)

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
    """O chamável que o `composition_root` liga a `IdentityGuard.authenticate_principal`."""

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
    # O dublê é estrutural; o adapter anota a classe concreta porque é o tipo
    # que a fachada publica. A forma é cobrada por
    # `test_o_spy_tem_a_mesma_assinatura_da_fachada_real`.
    return LocalAccessGuard(
        facade,  # type: ignore[arg-type]
        authentication or _SpyAuthentication(),
    )


def _grant(
    *,
    actor_tenant_id: str | None = "t1",
    scope_unit_id: str | None = "u1",
    role: str = "manager",
) -> AccessGrant:
    return AccessGrant(role=role, actor_tenant_id=actor_tenant_id, scope_unit_id=scope_unit_id)


def _ator(*, tenant_id: str | None = "t1") -> AccessPrincipal:
    return AccessPrincipal(user_id="user-1", tenant_id=tenant_id)


# **O eixo do tenant na chamada — nomeado x omitido x vazio** (ADR 0.0.0005).
#
# O terceiro valor é `""`, e a sua ausência era **reincidência de L-AG3**: com só
# dois valores, `tenant_id if tenant_id is not None else …` → `tenant_id or …`
# sobrevivia, aqui e na suíte do fake. O caso `""` é o único que refuta a
# truthiness: o chamador pede `tenant_id=""` e identity receberia o tenant do
# ator — um alvo que a decisão negaria vira o tenant do próprio ator, concedido.
_TENANT_NA_CHAMADA = [
    pytest.param("t1", id="tenant-nomeado"),
    pytest.param(None, id="tenant-omitido"),
    pytest.param("", id="tenant-vazio"),
]

# O mesmo eixo com o **tenant que tem de chegar à fachada** para cada valor.
_TENANT_RESOLVIDO = [
    pytest.param("t1", "t1", id="tenant-nomeado"),
    pytest.param(None, "t1", id="tenant-omitido"),
    pytest.param("", "", id="tenant-vazio"),
]

_VALORES_DO_EIXO_DO_TENANT = 3

# **A segunda dimensão de L-AG3.** Com as leis escritas só sobre `manage_staff`,
# condicionar a guarda a `permission != "manage_job_functions"` mantinha a suíte
# verde — e a permissão que escapava era a de alcance tenant-wide.
_ALVOS = [
    pytest.param("manage_staff", "u1", id="unit-scoped"),
    pytest.param("manage_job_functions", None, id="tenant-wide"),
]

# Os dois valores que L-AG3 nomeia — *"`tenant_id` vazio **ou** ausente"*. Com só
# `None`, trocar `if not actor_tenant_id` por `if actor_tenant_id is None` deixa
# tudo verde e reabre o caso vazio.
_ATOR_SEM_TENANT = [
    pytest.param(None, "platform_admin", id="ausente"),
    pytest.param("", "manager", id="vazio"),
]


def test_o_eixo_do_tenant_na_chamada_tem_os_tres_valores_do_contrato() -> None:
    """A cardinalidade do eixo — a suíte do fake carrega a asserção gêmea."""
    assert len(_TENANT_NA_CHAMADA) == _VALORES_DO_EIXO_DO_TENANT
    assert len(_TENANT_RESOLVIDO) == _VALORES_DO_EIXO_DO_TENANT
    assert [caso.id for caso in _TENANT_NA_CHAMADA] == [caso.id for caso in _TENANT_RESOLVIDO]


# ---------------------------------------------------------------------------
# Forma
# ---------------------------------------------------------------------------


def _forma(alvo: object, metodo: str) -> list[tuple[str, object, object]]:
    return [
        (nome, parametro.kind, parametro.default)
        for nome, parametro in inspect.signature(getattr(alvo, metodo)).parameters.items()
        if nome != "self"
    ]


@pytest.mark.parametrize("metodo", ["authenticate", "authorize"])
def test_o_adapter_tem_a_forma_do_port(metodo: str) -> None:
    """`AccessGuard` é `Protocol` — a aridade é cobrada onde o mypy não alcança."""
    assert _forma(LocalAccessGuard, metodo) == _forma(AccessGuard, metodo)


def test_o_spy_tem_a_mesma_assinatura_da_fachada_real() -> None:
    """Nome, `kind` e default — a outra ponta da conformidade dos dublês."""
    assert _forma(_SpyAccessFacade, "authorize") == _forma(IdentityAccessFacade, "authorize")


# ---------------------------------------------------------------------------
# L-AG1 — a exceção de autenticação sai crua
# ---------------------------------------------------------------------------


def test_l_ag1_o_adapter_nao_traduz_a_excecao_de_autenticacao() -> None:
    """**O mesmo objeto** sobe — um `except` que relançasse um novo falha aqui."""
    authentication = _SpyAuthentication()
    authentication.error = InvalidAccessTokenError()
    guard = _guard(_SpyAccessFacade(), authentication)

    with pytest.raises(InvalidAccessTokenError) as excinfo:
        guard.authenticate(object())

    assert excinfo.value is authentication.error


def test_authenticate_repassa_a_requisicao_e_devolve_o_ator_sem_tocar_nele() -> None:
    principal = _ator()
    authentication = _SpyAuthentication(principal)
    guard = _guard(_SpyAccessFacade(), authentication)
    request = object()

    assert guard.authenticate(request) is principal
    assert authentication.requests == [request]


# ---------------------------------------------------------------------------
# L-AG2 — a exceção de autorização sai crua
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag2_o_adapter_nao_traduz_a_excecao_de_autorizacao(
    permission: str,
    unit: str | None,
) -> None:
    """Com `UnitNotVisibleError` — a exceção que carrega o oráculo fechado por identity."""
    facade = _SpyAccessFacade()
    facade.error = UnitNotVisibleError("user-1", "u9")
    guard = _guard(facade)

    with pytest.raises(UnitNotVisibleError) as excinfo:
        guard.authorize(_ator(), permission, tenant_id="t1", unit_id=unit)

    assert excinfo.value is facade.error


# ---------------------------------------------------------------------------
# ADR 0.0.0005 — o tenant omitido é o do ator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("tenant_na_chamada", "tenant_alvo"), _TENANT_RESOLVIDO)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_o_tenant_da_chamada_decide_o_que_chega_a_identity(
    permission: str,
    unit: str | None,
    tenant_na_chamada: str | None,
    tenant_alvo: str,
) -> None:
    """A asserção é sobre o **pedido** que chegou à fachada, não só sobre o escopo.

    O escopo sai do `actor_tenant_id` que identity devolve e carregaria `"t1"`
    mesmo com a resolução esquecida — uma asserção só sobre ele ficaria verde
    com a mutação viva.
    """
    facade = _SpyAccessFacade(_grant(scope_unit_id=unit))
    guard = _guard(facade)

    scope = guard.authorize(
        _ator(tenant_id="t1"), permission, tenant_id=tenant_na_chamada, unit_id=unit
    )

    assert facade.received["tenant_id"] == tenant_alvo
    assert scope == AuthorizedScope(
        tenant_id=TenantId("t1"),
        unit_id=UnitId(unit) if unit is not None else None,
    )


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_omitir_o_tenant_produz_o_mesmo_resultado_que_nomear_o_do_ator(
    permission: str,
    unit: str | None,
) -> None:
    guard = _guard(_SpyAccessFacade(_grant(scope_unit_id=unit)))
    ator = _ator(tenant_id="t1")

    nomeado = guard.authorize(ator, permission, tenant_id="t1", unit_id=unit)
    omitido = guard.authorize(ator, permission, tenant_id=None, unit_id=unit)

    assert nomeado == omitido


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_o_tenant_nomeado_pelo_chamador_nao_e_sobrescrito_pelo_do_ator(
    permission: str,
    unit: str | None,
) -> None:
    """Quem nomeia `t9` declara `t9`, e é `t9` que a decisão tem de receber para negá-lo."""
    facade = _SpyAccessFacade(_grant(scope_unit_id=unit))

    _guard(facade).authorize(_ator(tenant_id="t1"), permission, tenant_id="t9", unit_id=unit)

    assert facade.received["tenant_id"] == "t9"


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_ator_sem_tenant_com_tenant_omitido_delega_a_omissao(
    permission: str,
    unit: str | None,
) -> None:
    """A leitura sem valor **nega**, nunca alarga: `None` chega a identity como "não declarei".

    Sucessor de `test_ator_sem_claims_com_tenant_omitido_falha_fechado`: com o ator
    tipado, "sem claims" deixou de existir; o que sobra é o token sem tenant, e
    nada é inventado no lugar dele.
    """
    facade = _SpyAccessFacade(_grant())

    _guard(facade).authorize(_ator(tenant_id=None), permission, tenant_id=None, unit_id=unit)

    assert facade.received["tenant_id"] is None


def test_ator_que_nao_veio_deste_guard_e_defeito_e_nao_concessao() -> None:
    """`Actor = object` no port; um objeto estranho não chega à fachada."""
    facade = _SpyAccessFacade(_grant())

    with pytest.raises(TypeError, match="object"):
        _guard(facade).authorize(object(), "manage_staff", tenant_id="t1", unit_id="u1")

    assert facade.received == {}


# ---------------------------------------------------------------------------
# L-AG3 — `tenant_id` nunca sai vazio
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize(("actor_tenant_id", "role"), _ATOR_SEM_TENANT)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_ator_sem_tenant_e_negado_pelo_adapter(
    permission: str,
    unit: str | None,
    actor_tenant_id: str | None,
    role: str,
    tenant_na_chamada: str | None,
) -> None:
    """Imposta aqui, não delegada à matriz de papéis — o cenário é o pior caso.

    Identity **autorizou** e devolveu um ator sem tenant. Montar o caso com um
    `platform_admin` real produziria verde pela **permissão** (negado no passo 2)
    e a mutação "remover a checagem de tenant" sobreviveria.
    """
    facade = _SpyAccessFacade(_grant(actor_tenant_id=actor_tenant_id, role=role))

    with pytest.raises(PermissionDeniedError) as excinfo:
        _guard(facade).authorize(
            _ator(tenant_id=actor_tenant_id),
            permission,
            tenant_id=tenant_na_chamada,
            unit_id=unit,
        )

    assert role in str(excinfo.value)
    assert permission in str(excinfo.value)


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize(("actor_tenant_id", "role"), _ATOR_SEM_TENANT)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_o_adapter_nunca_coage_tenant_ausente_para_string_vazia(
    permission: str,
    unit: str | None,
    actor_tenant_id: str | None,
    role: str,
    tenant_na_chamada: str | None,
) -> None:
    """`TenantId(actor_tenant_id or "")` compila e passa mypy strict — **nada** é devolvido."""
    facade = _SpyAccessFacade(_grant(actor_tenant_id=actor_tenant_id, role=role))

    scopes = []
    with contextlib.suppress(PermissionDeniedError):
        scopes.append(
            _guard(facade).authorize(
                _ator(tenant_id=actor_tenant_id),
                permission,
                tenant_id=tenant_na_chamada,
                unit_id=unit,
            )
        )

    assert scopes == []


# ---------------------------------------------------------------------------
# Tradução de vocabulário
# ---------------------------------------------------------------------------


def test_o_adapter_repassa_ator_permissao_e_alvo_como_valores() -> None:
    """A permissão atravessa como **valor**; o ator, como o próprio principal."""
    facade = _SpyAccessFacade(_grant())
    ator = _ator()

    scope = _guard(facade).authorize(ator, "manage_staff", tenant_id="t1", unit_id="u1")

    assert facade.received == {
        "principal": ator,
        "permission": "manage_staff",
        "tenant_id": "t1",
        "unit_id": "u1",
    }
    assert scope == AuthorizedScope(tenant_id=TenantId("t1"), unit_id=UnitId("u1"))


def test_permissao_tenant_wide_atravessa_sem_unidade_e_volta_sem_unidade() -> None:
    """Sem este caso o `None` viraria `UnitId("None")` sem que nada reclamasse."""
    facade = _SpyAccessFacade(_grant(scope_unit_id=None))

    scope = _guard(facade).authorize(_ator(), "manage_job_functions", tenant_id="t1")

    assert facade.received["unit_id"] is None
    assert scope.unit_id is None
    assert scope.tenant_id == "t1"


def test_papel_com_bypass_volta_sem_unidade_em_permissao_unit_scoped() -> None:
    """`unit_id=None` **não** significa "ação tenant-wide" — o `owner` prova.

    O adapter não aperta isso, e é o correto: recusar contradiria decisão
    ratificada (kickoff #9, ADR 2.1.0001). O pedido chegou **sem** unidade — é o
    passo 4 de identity que dispensa, não o adapter que inventa uma.
    """
    facade = _SpyAccessFacade(_grant(scope_unit_id=None, role="owner"))

    scope = _guard(facade).authorize(_ator(), "manage_staff", tenant_id="t1")

    assert scope.unit_id is None
    assert scope.tenant_id == "t1"
    assert facade.received["unit_id"] is None
    assert facade.received["permission"] == "manage_staff"


def test_o_escopo_carrega_o_tenant_do_ator_e_nao_o_do_pedido() -> None:
    """O tenant concedido é o que identity leu do banco, não o que o chamador pediu."""
    facade = _SpyAccessFacade(_grant(actor_tenant_id="t-do-banco"))

    scope = _guard(facade).authorize(
        _ator(tenant_id="t1"), "manage_staff", tenant_id="t1", unit_id="u1"
    )

    assert scope.tenant_id == "t-do-banco"

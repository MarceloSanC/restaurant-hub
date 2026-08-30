"""Wiring dos repositórios e dos 16 use cases de staff no composition root — CA18.

Espelho de `test_composition_root_identity.py`, e o espelho é deliberado: a regra
que ele guarda ("só o composition root instancia adapter") é a mesma, e o BC
staff acabou de ganhar o seu primeiro pacote de adapters de saída.

**Os 16 use cases nascem sem consumidor**, e é por isso que estes testes têm de
ser mais do que "o campo existe". Não há adapter de entrada de staff até a
Stage 3.4: nenhum request, nenhum e2e e nenhum teste de integração passa por
`wire_dependencies()` para staff. Se o wiring estiver errado — um repositório
trocado, um fake no lugar do adapter, um use case montado com o repositório do
outro agregado — **nada mais no repositório reclama**. Este arquivo é o único
lugar onde esse erro é visível antes da 3.4.

Por isso as asserções são sobre **o que foi injetado**, não sobre o tipo do use
case: `isinstance(deps.staff_create_employee, CreateEmployeeUseCase)` é
verdadeiro por construção do `dataclass` e não prova nada que o type-checker já
não provasse.

**Stage 3.4 — o tradutor do `AccessGuard`, e a prova de que nada mais nasceu.**
O arquivo ganha dois assuntos, e os dois pertencem a ele porque o sujeito é o
mesmo módulo. O primeiro é o `_IdentityAccessGuard` (CA15): ele é a implementação
de **produção** das quatro leis do port, e a Stage não teria onde prová-las de
outro modo — o fake as prova em
`tests/unit/features/staff/application/test_access_guard_laws.py`, e lei que só
um dos dois obrigados cumpre não é lei. O segundo é o CA21: a Stage promete que
**nenhuma rota nasce**, e a promessa fica verificada aqui, contra o
`build_http_wiring` real, em vez de afirmada num documento.
"""

import ast
import contextlib
import datetime
import importlib
import inspect
import pathlib
from collections.abc import Callable
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from restaurant_hub.composition_root import (
    ApplicationDependencies,
    _IdentityAccessGuard,
    build_http_wiring,
    wire_dependencies,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    PermissionDeniedError,
    UnitNotVisibleError,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    UnitId as IdentityUnitId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId as StaffTenantId,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    UnitId as StaffUnitId,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit

_SRC = pathlib.Path(__file__).resolve().parents[5] / "src" / "restaurant_hub"
_PACOTE_DE_ADAPTERS = _SRC / "features" / "staff" / "adapters"
_MODULO_DE_ADAPTERS = "restaurant_hub.features.staff.adapters"
_COMPOSITION_ROOT = _SRC / "composition_root.py"

# Os 16 de `features/staff/application/use_cases/`, na forma como o contêiner os
# expõe. A lista é **explícita** e não derivada por varredura de pasta de
# propósito: derivada, ela se ajustaria sozinha a um use case que alguém
# esquecesse de wirar, e o teste passaria a confirmar o esquecimento.
_USE_CASES_DE_STAFF = (
    "staff_create_job_function",
    "staff_rename_job_function",
    "staff_delete_job_function",
    "staff_list_job_functions",
    "staff_create_employee",
    "staff_rename_employee",
    "staff_list_employees",
    "staff_delete_employee",
    "staff_assign_job_functions",
    "staff_change_workload_profile",
    "staff_declare_shift_preference",
    "staff_register_unavailability",
    "staff_remove_unavailability",
    "staff_deactivate_employee",
    "staff_reactivate_employee",
    "staff_copy_employee_to_unit",
)

_TOTAL_DE_USE_CASES = 16


def _dependencias() -> ApplicationDependencies:
    """O grafo real, sem banco no ar — `create_engine` não abre conexão."""
    return wire_dependencies(Settings(_env_file=None))


def test_ca18_os_dezesseis_use_cases_de_staff_estao_no_conteiner() -> None:
    """A contagem é asserção, não decoração.

    O número 16 vem do plano e da pasta `use_cases/`. Sem asserir a contagem, um
    use case esquecido no wiring não teria sintoma nenhum até a 3.4 — quando
    apareceria como `AttributeError` num router recém-escrito, longe da causa.
    """
    deps = _dependencias()

    assert len(_USE_CASES_DE_STAFF) == _TOTAL_DE_USE_CASES
    ausentes = [nome for nome in _USE_CASES_DE_STAFF if getattr(deps, nome, None) is None]
    assert ausentes == [], f"use cases de staff não montados: {ausentes}"


def test_ca18_a_lista_deste_teste_cobre_a_pasta_de_use_cases_inteira() -> None:
    """Fecha o buraco da lista explícita: ela pode ficar **incompleta**.

    A lista acima é escrita à mão para que um use case não wirado apareça como
    falha em vez de sumir da varredura. O preço é que ela mesma pode envelhecer:
    um use case novo entra na pasta, ninguém acrescenta aqui, e o teste anterior
    continua verde. Esta asserção cobra a pasta contra a lista — e é a **única**
    varredura de diretório do arquivo, feita de propósito no lugar onde
    derivar ajuda em vez de esconder.
    """
    pasta = _SRC / "features" / "staff" / "application" / "use_cases"
    na_pasta = {arquivo.stem for arquivo in pasta.glob("*.py") if arquivo.stem != "__init__"}
    na_lista = {nome.removeprefix("staff_") for nome in _USE_CASES_DE_STAFF}

    assert na_pasta == na_lista, (
        f"a lista deste teste divergiu da pasta — só na pasta: {sorted(na_pasta - na_lista)}; "
        f"só na lista: {sorted(na_lista - na_pasta)}"
    )


def test_ca18_os_use_cases_recebem_os_adapters_postgres_e_nao_fakes() -> None:
    """O que CA18 realmente pede: o repositório **injetado** é o do Postgres.

    Trocar `PostgresEmployeeRepository` por um fake no composition root passaria
    despercebido em toda a suíte — não há consumidor de staff até a 3.4 — e o
    sintoma seria uma aplicação que aceita cadastros e os perde no restart.
    """
    deps = _dependencias()

    assert isinstance(deps.staff_create_employee._employees, PostgresEmployeeRepository)
    assert isinstance(deps.staff_create_employee._job_functions, PostgresJobFunctionRepository)
    assert isinstance(deps.staff_list_job_functions._job_functions, PostgresJobFunctionRepository)
    assert isinstance(deps.staff_delete_job_function._employees, PostgresEmployeeRepository)
    assert isinstance(deps.staff_copy_employee_to_unit._employees, PostgresEmployeeRepository)


def test_os_dois_ports_cruzados_compartilham_a_mesma_instancia_de_repositorio() -> None:
    """Os use cases que tocam os dois agregados veem **o mesmo** par.

    `delete_job_function` consulta funcionário (L-JF3) e `create_employee`
    consulta função (L-E4). Com instâncias diferentes — pior, com `Engine`
    diferentes — as duas guardas passariam a olhar para pools distintos sem ganho
    nenhum, e o wiring estaria pagando conexão por engano. A identidade de objeto
    é a forma mais direta de travar isso.
    """
    deps = _dependencias()

    assert deps.staff_create_employee._employees is deps.staff_delete_employee._employees
    assert (
        deps.staff_create_employee._job_functions is deps.staff_delete_job_function._job_functions
    )
    assert deps.staff_delete_job_function._employees is deps.staff_list_employees._employees


def test_duas_chamadas_devolvem_grafos_de_staff_independentes() -> None:
    """Sem singleton global (skill `composition-root`), também para staff."""
    primeiro = _dependencias()
    segundo = _dependencias()

    assert primeiro.staff_create_employee is not segundo.staff_create_employee
    assert primeiro.staff_create_employee._employees is not segundo.staff_create_employee._employees


def _modulos_que_importam_adapters_de_staff() -> set[str]:
    """Varre `src/` por imports do pacote de adapters de staff.

    Ignora os arquivos **de dentro do próprio pacote**: um repositório importar
    `mappers`, `tables` ou `integrity_errors` do vizinho é coesão interna, não a
    violação que este teste procura (um consumidor externo pulando o composition
    root).
    """
    culpados: set[str] = set()
    for arquivo in _SRC.rglob("*.py"):
        if arquivo.is_relative_to(_PACOTE_DE_ADAPTERS):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            alvo = ""
            if isinstance(no, ast.ImportFrom) and no.module:
                alvo = no.module
            elif isinstance(no, ast.Import):
                alvo = " ".join(alias.name for alias in no.names)
            if _MODULO_DE_ADAPTERS in alvo:
                culpados.add(str(arquivo.relative_to(_SRC)))
    return culpados


def test_so_o_composition_root_importa_os_adapters_de_staff() -> None:
    """A regra que o import-linter não cobre, como asserção mecânica.

    `bc-independence` compara `features.identity` contra `features.staff`, e o
    composition root não pertence a nenhum dos dois — então nada nos contratos
    impede um **outro** módulo de importar os adapters de staff direto. Este
    teste fecha a janela pelo lado do consumidor, como o de identity faz.
    """
    esperado = {str(_COMPOSITION_ROOT.relative_to(_SRC))}
    assert _modulos_que_importam_adapters_de_staff() == esperado, (
        f"apenas composition_root.py pode importar {_MODULO_DE_ADAPTERS}; "
        f"receba o repositório por injeção (LAYOUT §6)"
    )


def test_um_import_proibido_plantado_reprova() -> None:
    """Teste negativo: o detector detecta.

    Um guarda que nunca viu um caso positivo não é um guarda — é uma função que
    devolve conjunto vazio.
    """
    codigo_violador = (
        "from restaurant_hub.features.staff.adapters.out.postgres.employee_repository "
        "import PostgresEmployeeRepository"
    )
    arvore = ast.parse(codigo_violador)

    alvos = [no.module for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.module]

    assert any(_MODULO_DE_ADAPTERS in alvo for alvo in alvos)


# ---------------------------------------------------------------------------
# Stage 3.4 — o tradutor do `AccessGuard` (CA15) e a prova de CA21
#
# O tradutor é a implementação de **produção** das quatro leis do port. O fake
# as prova em `tests/unit/features/staff/application/test_access_guard_laws.py`;
# aqui o sujeito é a outra implementação, porque lei que só um dos dois obrigados
# cumpre não é lei (ADR 3.4.0001 §Implementation notes).
# ---------------------------------------------------------------------------


class _SpyIdentityGuard:
    """`IdentityGuard` de mentira, para exercitar o tradutor sem banco.

    Não é fake de port — é dublê do objeto **embrulhado**, que o composition
    root guarda como `Any` por necessidade (o pacote `in` é keyword Python).
    Guarda o que recebeu, para que as asserções de tradução sejam sobre o valor
    que atravessou, e não sobre o que o teste imaginou ter passado.
    """

    def __init__(self, result: AuthorizedActor | None = None) -> None:
        self.result = result
        self.received: dict[str, object] = {}
        self.authentication_error: Exception | None = None
        self.authorization_error: Exception | None = None

    def authenticate(self, request: object) -> object:
        if self.authentication_error is not None:
            raise self.authentication_error
        return ("ator", request)

    def authorize(
        self,
        actor: object,
        permission: object,
        *,
        tenant_id: object = None,
        unit_id: object = None,
    ) -> AuthorizedActor:
        self.received = {
            "actor": actor,
            "permission": permission,
            "tenant_id": tenant_id,
            "unit_id": unit_id,
        }
        if self.authorization_error is not None:
            raise self.authorization_error
        assert self.result is not None
        return self.result


def _authorized_actor(
    *,
    actor_tenant_id: str | None = "t1",
    scope_unit_id: str | None = "u1",
    role: Role = Role.MANAGER,
) -> AuthorizedActor:
    """`AuthorizedActor` **real**, e não um stub com os mesmos atributos.

    O DTO de identity é o que o tradutor lê. Um stub anônimo passaria a testar a
    forma que este arquivo imaginou, e um campo renomeado do outro lado da
    fronteira sairia da suíte em silêncio para reaparecer em runtime.
    """
    return AuthorizedActor(
        user_id=UserId("user-1"),
        role=role,
        actor_tenant_id=RestaurantId(actor_tenant_id) if actor_tenant_id is not None else None,
        scope_tenant_id=RestaurantId("t1"),
        scope_unit_id=IdentityUnitId(scope_unit_id) if scope_unit_id is not None else None,
    )


def _ator_autenticado(*, tenant_id: str | None = "t1") -> object:
    """`AuthenticatedActor` **real** de identity, e não um stub com um `.claims`.

    É o objeto que `IdentityGuard.authenticate` devolve em produção, e é dele que
    o tradutor lê o tenant quando a chamada o omite (ADR 0.0.0005, cláusula 3).
    Um stub anônimo com os mesmos atributos testaria a forma que **este arquivo**
    imaginou: `claims` renomeado do outro lado da fronteira sairia da suíte em
    silêncio e reapareceria como 403 universal em runtime — que é precisamente o
    defeito que a resolução do tenant existe para fechar.

    O módulo mora sob o pacote `in`, keyword Python, então chega por `importlib`
    (LAYOUT §8) — o mesmo caminho que o composition root usa.
    """
    dependencies = importlib.import_module(
        "restaurant_hub.features.identity.adapters.in.http.dependencies"
    )
    actor: object = dependencies.AuthenticatedActor(
        claims=AccessTokenClaims(
            subject=UserId("user-1"),
            role=Role.MANAGER,
            tenant_id=RestaurantId(tenant_id) if tenant_id is not None else None,
            session_id=SessionId("session-1"),
            expires_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
    )
    return actor


# **O eixo do tenant na chamada — nomeado x omitido** (ADR 0.0.0005).
#
# Mesmo `parametrize`, na mesma forma, que o de
# `tests/unit/features/staff/application/test_access_guard_laws.py`: a lei do
# tenant resolvido vale para as **duas** implementações do port, e cobrá-las com
# conjuntos de valores diferentes é o sinal de alerta mais forte da família "lei
# universal, representante estreito" — foi assim que a Stage 3.4 vazou duas
# mutações. Os dois arquivos são comparáveis linha a linha de propósito.
# Cardinalidades declaradas — piso contra a varredura encolher em silencio.
_TOTAL_DE_OVERRIDES_DE_STAFF = 17
_TOTAL_DE_ROTAS_DE_STAFF = 16
_TOTAL_DE_ROTAS_DE_IDENTITY = 10
_PACOTE_HTTP_IDENTITY = "restaurant_hub.features.identity.adapters.in.http"
_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"
_PREFIXO_DA_API = "/api/v1"

# O inventário de identity, **literal**, como o cliente o alcança. Transcrito e
# não derivado do router: derivá-lo faria a expectativa acompanhar qualquer
# mudança de path, e "não regrediu" passaria a significar "concorda consigo
# mesmo". Uma contagem sozinha também não bastava — trocar `/users` por
# `/usuarios` mantém o total em dez.
_ROTAS_DE_IDENTITY: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/auth/password"),
        ("POST", "/api/v1/auth/password-reset-requests"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/restaurants"),
        ("POST", "/api/v1/restaurants/{restaurant_id}/owners"),
        ("POST", "/api/v1/restaurants/{restaurant_id}/units"),
        ("POST", "/api/v1/users"),
        ("POST", "/api/v1/users/invitations"),
    }
)

_TENANT_NA_CHAMADA = [
    pytest.param("t1", id="tenant-nomeado"),
    pytest.param(None, id="tenant-omitido"),
]


# **A segunda dimensão de L-AG3 — e ela não é simetria decorativa.**
#
# Com as leis escritas só sobre `manage_staff`, a recusa fica travada **por
# permissão** e não como propriedade do guard: condicionar a guarda a
# `permission != "manage_job_functions"` mantinha a suíte inteira verde e
# deixava `AuthorizedScope(tenant_id=StaffTenantId(None))` sair daqui. Medido —
# a mutação sobrevivia nesta suíte e na do fake, e a permissão que escapava era
# justamente a de alcance **tenant-wide**.
#
# O código do tradutor já argumenta contra isso: ele impõe L-AG3 em vez de
# confiar no "`platform_admin` é negado antes, no passo 2" porque o mapa RBAC é
# editável. Uma profundidade de defesa que cobre metade do vocabulário é meia
# defesa.
_ALVOS = [
    pytest.param("manage_staff", "u1", id="unit-scoped"),
    pytest.param("manage_job_functions", None, id="tenant-wide"),
]


def test_ca15_o_access_guard_de_staff_tem_a_forma_do_port() -> None:
    """`AccessGuard` é `Protocol` — `isinstance` não responde, a assinatura sim.

    A conformidade estrutural já é gate em `make typecheck` (o campo do contêiner
    é anotado com o port). Esta asserção cobre o que `mypy` não alcança —
    `tests/integration/` e `tests/e2e/` —, onde uma aridade divergente viraria
    `TypeError` em execução: a mesma propriedade que a Task 04 usou para a
    assinatura de `find_by_id`.
    """
    deps = _dependencias()

    for method in ("authenticate", "authorize"):
        port_signature = [
            (name, parameter.kind, parameter.default)
            for name, parameter in inspect.signature(
                getattr(AccessGuard, method)
            ).parameters.items()
            if name != "self"
        ]
        translator_signature = [
            (name, parameter.kind, parameter.default)
            for name, parameter in inspect.signature(
                getattr(deps.staff_access_guard, method)
            ).parameters.items()
        ]
        assert translator_signature == port_signature, f"{method} divergiu do port"


@pytest.mark.parametrize("method", ["authenticate", "authorize"])
def test_o_spy_tem_a_mesma_assinatura_do_identity_guard_real(method: str) -> None:
    """Fecha a outra ponta da conformidade — a que faltava.

    Há teste de que o **tradutor** casa com o `AccessGuard`; não havia nenhum de
    que o `_SpyIdentityGuard` casa com o `IdentityGuard` **real**. É a metade que
    importa para os sete testes de comportamento acima: eles exercitam o tradutor
    contra o dublê, e o objeto embrulhado em produção chega como `Any` (o pacote
    `in` é keyword Python), então **nada** no repositório compara os dois. Um
    parâmetro renomeado ou promovido a posicional em `IdentityGuard.authorize`
    passaria por toda a suíte e só apareceria como `TypeError` no primeiro
    request da Stage 3.6.

    Comparam-se nome, `kind` e default — **não** as anotações. O spy anota tudo
    como `object` de propósito: ele é um dublê, não uma segunda implementação, e
    exigir os tipos de identity aqui obrigaria o arquivo a reencenar o
    vocabulário do outro BC para provar uma propriedade de forma.
    """
    identity_guard = importlib.import_module(
        "restaurant_hub.features.identity.adapters.in.http.dependencies"
    ).IdentityGuard

    def forma(alvo: object) -> list[tuple[str, object, object]]:
        return [
            (name, parameter.kind, parameter.default)
            for name, parameter in inspect.signature(getattr(alvo, method)).parameters.items()
        ]

    assert forma(_SpyIdentityGuard) == forma(identity_guard), (
        f"o dublê divergiu de IdentityGuard.{method} — os testes de comportamento "
        f"do tradutor passariam contra uma forma que não existe mais"
    )


def test_ca15_o_tradutor_embrulha_o_mesmo_identity_guard_das_rotas() -> None:
    """Identidade de objeto, e não `isinstance`.

    Um **segundo** `IdentityGuard` satisfaria qualquer teste de tipo e faria as
    duas bordas — a de identity e a de staff da Stage 3.6 — decidirem acesso
    sobre grafos distintos, com dois `AuthorizeActionUseCase` e dois `Engine`.
    A divergência só apareceria como comportamento estranho em produção.
    """
    deps = _dependencias()

    assert deps.staff_access_guard._guard is deps.identity_guard


def test_l_ag1_o_tradutor_nao_traduz_a_excecao_de_autenticacao() -> None:
    """L-AG1 na implementação de produção: **o mesmo objeto** sobe.

    É o que fará a faixa 401 da Stage 3.6 ser byte-idêntica à de identity. Um
    `try/except` que relançasse um `InvalidAccessTokenError()` novo passaria em
    `pytest.raises(InvalidAccessTokenError)` e falha aqui.
    """
    spy = _SpyIdentityGuard()
    spy.authentication_error = InvalidAccessTokenError()
    translator = _IdentityAccessGuard(spy)

    with pytest.raises(InvalidAccessTokenError) as excinfo:
        translator.authenticate(object())

    assert excinfo.value is spy.authentication_error


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag2_o_tradutor_nao_traduz_a_excecao_de_autorizacao(
    permission: str,
    unit: str | None,
) -> None:
    """L-AG2, e com `UnitNotVisibleError` de propósito.

    É a exceção que carrega a conversão de `UnitNotFoundError` feita por
    identity — o fechamento do oráculo de enumeração cross-tenant
    (ADR 2.4.0001 §5). Embrulhá-la aqui apagaria essa propriedade sem que nenhum
    teste de identity notasse.

    Parametrizado sobre as duas permissões porque este é o **ramo de recusa**:
    sem isso, `manage_job_functions` só apareceria em caminho de sucesso, e um
    `except` que a tratasse à parte não teria teste que o observasse.
    """
    spy = _SpyIdentityGuard()
    spy.authorization_error = UnitNotVisibleError("user-1", "u9")
    translator = _IdentityAccessGuard(spy)

    with pytest.raises(UnitNotVisibleError) as excinfo:
        translator.authorize(object(), permission, tenant_id="t1", unit_id=unit)

    assert excinfo.value is spy.authorization_error


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_o_tenant_omitido_e_resolvido_do_ator_antes_de_delegar_a_identity(
    permission: str,
    unit: str | None,
    tenant_na_chamada: str | None,
) -> None:
    """ADR 0.0.0005 na implementação de produção — e a asserção é sobre o **pedido**.

    Sem esta resolução as 16 rotas de staff são inalcançáveis por **todos** os
    papéis: o inventário não carrega tenant (cláusula 2), então o tradutor
    delegaria `tenant_id=None` e o passo 3 de `AuthorizeActionUseCase` recusaria
    com `TenantScopeRequiredError`. O que se assere aqui é o que **chegou** ao
    `IdentityGuard` — `spy.received["tenant_id"]` —, e não só o escopo devolvido:
    o escopo sai do `actor_tenant_id` que identity devolve e carregaria `"t1"`
    mesmo se a resolução tivesse sido esquecida, então uma asserção só sobre ele
    ficaria verde com a mutação viva.

    **A asserção é contra o valor esperado, escrito por extenso**, e não contra o
    resultado do eixo vizinho: comparar nomeado com omitido passaria se os dois
    estivessem errados do mesmo jeito.
    """
    spy = _SpyIdentityGuard(_authorized_actor(scope_unit_id=unit))
    translator = _IdentityAccessGuard(spy)

    scope = translator.authorize(
        _ator_autenticado(tenant_id="t1"),
        permission,
        tenant_id=tenant_na_chamada,
        unit_id=unit,
    )

    assert spy.received["tenant_id"] == "t1"
    assert scope == AuthorizedScope(
        tenant_id=StaffTenantId("t1"),
        unit_id=StaffUnitId(unit) if unit is not None else None,
    )


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_omitir_o_tenant_produz_o_mesmo_resultado_que_nomear_o_do_ator(
    permission: str,
    unit: str | None,
) -> None:
    """A equivalência literal do critério, do lado do tradutor."""
    spy = _SpyIdentityGuard(_authorized_actor(scope_unit_id=unit))
    translator = _IdentityAccessGuard(spy)
    ator = _ator_autenticado(tenant_id="t1")

    nomeado = translator.authorize(ator, permission, tenant_id="t1", unit_id=unit)
    omitido = translator.authorize(ator, permission, tenant_id=None, unit_id=unit)

    assert nomeado == omitido


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_o_tenant_nomeado_pelo_chamador_nao_e_sobrescrito_pelo_do_ator(
    permission: str,
    unit: str | None,
) -> None:
    """Só a **ausência** carrega significado — o resto do contrato não mudou.

    Uma resolução escrita como "sempre use o tenant do ator" satisfaria os dois
    testes acima e apagaria em silêncio o alvo que o chamador nomeou. Quem
    nomeia `t9` está declarando `t9`, e é `t9` que a decisão de acesso — passo 3,
    contra o usuário carregado do banco — tem de receber para poder negá-lo.
    """
    spy = _SpyIdentityGuard(_authorized_actor(scope_unit_id=unit))
    translator = _IdentityAccessGuard(spy)

    translator.authorize(
        _ator_autenticado(tenant_id="t1"),
        permission,
        tenant_id="t9",
        unit_id=unit,
    )

    assert spy.received["tenant_id"] == "t9"


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_ator_sem_claims_com_tenant_omitido_falha_fechado(
    permission: str,
    unit: str | None,
) -> None:
    """A leitura malsucedida **nega**, nunca alarga.

    `Actor = object`: o port aceita qualquer objeto, e um ator que não seja o
    `AuthenticatedActor` de identity não tem `claims` para ler. O tradutor
    resolve `None` e delega `None` — que é "não declarei tenant" —, e a decisão
    de acesso recusa. O que este teste trava é que a leitura ausente **não** vira
    curinga: nada é inventado no lugar do tenant.
    """
    spy = _SpyIdentityGuard(_authorized_actor())
    translator = _IdentityAccessGuard(spy)

    translator.authorize(object(), permission, tenant_id=None, unit_id=unit)

    assert spy.received["tenant_id"] is None


# Os dois valores que L-AG3 nomeia — *"`tenant_id` vazio **ou** ausente"* —, e
# são casos **distintos** na implementação, não sinônimos:
#
# - `None` é o que `AuthorizedActor.actor_tenant_id` traz hoje para
#   `platform_admin`, o único papel sem tenant;
# - `""` é o que a coerção proibida (`StaffTenantId(actor_tenant_id or "")`)
#   produziria, e é o balde de falso isolamento que `InvalidIdentifierError`
#   nomeia — um tenant vazio consulta como se fosse um tenant.
#
# Parametrizar é o que dá refutação à guarda escrita: com só `None` na suíte,
# trocar `if not actor_tenant_id` por `if actor_tenant_id is None` deixa tudo
# verde e reabre o caso vazio. É a mesma parametrização que
# `test_access_guard_laws.py` já aplica do lado do fake — as duas
# implementações do port passam a ser cobradas pelo mesmo par de valores.
_ATOR_SEM_TENANT = [
    pytest.param(None, Role.PLATFORM_ADMIN, id="ausente"),
    pytest.param("", Role.MANAGER, id="vazio"),
]


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize(("actor_tenant_id", "role"), _ATOR_SEM_TENANT)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_ator_sem_tenant_e_negado_pelo_tradutor(
    permission: str,
    unit: str | None,
    actor_tenant_id: str | None,
    role: Role,
    tenant_na_chamada: str | None,
) -> None:
    """L-AG3 imposta no tradutor, e não delegada à matriz de papéis.

    Hoje `platform_admin` já seria negado antes, no passo 2 do guard, por não
    deter as permissões de staff. Confiar nisso faria o isolamento de tenant
    refém do mapa RBAC — que é editável, e cuja edição nenhum teste desta lei
    observaria. Por isso o cenário montado é o pior caso: identity **autorizou**
    e devolveu um ator sem tenant — e vale para as **duas** permissões, porque
    L-AG3 é propriedade do guard e não de uma capacidade.

    **O eixo do tenant omitido usa o mesmo dublê, e a escolha é o que separa o
    teste do teatro.** Montar este caso com um `platform_admin` real produziria
    verde pela **permissão** — `role.py` dá a ele só `MANAGE_PLATFORM`, negado no
    passo 2, antes de a execução chegar à guarda desta lei —, e a mutação
    "remover a checagem de tenant" sobreviveria com a suíte parecendo cobri-la.
    O spy é o que faz o cenário ser o que a lei descreve.
    """
    spy = _SpyIdentityGuard(_authorized_actor(actor_tenant_id=actor_tenant_id, role=role))
    translator = _IdentityAccessGuard(spy)

    with pytest.raises(PermissionDeniedError):
        translator.authorize(
            _ator_autenticado(tenant_id=actor_tenant_id),
            permission,
            tenant_id=tenant_na_chamada,
            unit_id=unit,
        )


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize(("actor_tenant_id", "role"), _ATOR_SEM_TENANT)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_o_tradutor_nunca_coage_tenant_ausente_para_string_vazia(
    permission: str,
    unit: str | None,
    actor_tenant_id: str | None,
    role: Role,
    tenant_na_chamada: str | None,
) -> None:
    """A mutação que L-AG3 existe para matar, escrita como asserção.

    `StaffTenantId(actor_tenant_id or "")` compila, passa mypy strict e devolve
    um escopo de tenant vazio — consultas que atravessariam todos os tenants.
    A exigência aqui é dupla: **nada** é devolvido, e o que sobe é negação.

    O eixo `nomeado x omitido` entra porque a resolução do ADR 0.0.0005 abre um
    segundo caminho até a mesma coerção: `tenant_id or actor_tenant or ""`
    passaria no eixo nomeado e reabriria o tenant vazio no omitido.
    """
    spy = _SpyIdentityGuard(_authorized_actor(actor_tenant_id=actor_tenant_id, role=role))
    translator = _IdentityAccessGuard(spy)

    scopes = []
    with contextlib.suppress(PermissionDeniedError):
        scopes.append(
            translator.authorize(
                _ator_autenticado(tenant_id=actor_tenant_id),
                permission,
                tenant_id=tenant_na_chamada,
                unit_id=unit,
            )
        )

    assert scopes == []


def test_o_tradutor_converte_o_vocabulario_nos_dois_sentidos() -> None:
    """`str` opaca entra como tipo de identity; `AuthorizedActor` sai como escopo.

    A asserção é sobre o que **chegou** ao objeto embrulhado, e não sobre o que o
    teste passou: é a única forma de provar que a permissão virou `Permission` de
    verdade. `IdentityGuard` aceitaria a `str` crua em runtime — `Permission` é
    `StrEnum` —, então a tradução ausente não teria sintoma nenhum aqui, e
    reapareceria no dia em que alguém trocasse uma comparação por identidade do
    outro lado da fronteira.
    """
    spy = _SpyIdentityGuard(_authorized_actor())
    translator = _IdentityAccessGuard(spy)

    scope = translator.authorize(object(), "manage_staff", tenant_id="t1", unit_id="u1")

    assert spy.received["permission"] is Permission.MANAGE_STAFF
    assert spy.received["tenant_id"] == "t1"
    assert spy.received["unit_id"] == "u1"
    assert scope == AuthorizedScope(tenant_id=StaffTenantId("t1"), unit_id=StaffUnitId("u1"))


def test_permissao_tenant_wide_atravessa_sem_unidade_e_volta_sem_unidade() -> None:
    """`manage_job_functions` não nomeia unidade — nos dois sentidos da tradução.

    Sem este caso, o ramo `unit_id is None` das duas conversões ficaria sem
    execução, e o `None` viraria `UnitId("None")` sem que nada reclamasse.
    """
    spy = _SpyIdentityGuard(_authorized_actor(scope_unit_id=None))
    translator = _IdentityAccessGuard(spy)

    scope = translator.authorize(object(), "manage_job_functions", tenant_id="t1")

    assert spy.received["unit_id"] is None
    assert scope.unit_id is None
    assert scope.tenant_id == "t1"


def test_papel_com_bypass_volta_sem_unidade_em_permissao_unit_scoped() -> None:
    """`unit_id=None` **não** significa "ação tenant-wide", e este é o caso que prova.

    `owner` e `platform_admin` estão em `_UNIT_SCOPE_BYPASS_ROLES`
    (`user.py:45`), então o passo 4 do guard os dispensa de nomear a unidade
    **por papel** — kickoff #9, ADR 2.1.0001, `workforce.md` §4: o dono enxerga
    o tenant inteiro por desenho. Um `owner` exercendo `manage_staff` sem
    declarar unidade é autorizado, e o escopo volta com `unit_id=None` sobre uma
    permissão que é **unit-scoped**.

    **O tradutor não aperta isso, e é o correto.** Recusar aqui — exigir unidade
    quando a permissão não é tenant-wide — contradiria decisão ratificada, e
    mudá-la exigiria o sponsor. O que estava errado era a **docstring** do port,
    que afirmava que `None` significa tenant-wide; foi corrigida no mesmo commit.
    Sem este teste, a docstring corrigida voltaria a ser prosa não verificada, que
    é a classe de defeito que esta Stage existe para fechar.

    Consequência viva para a Stage 3.6, registrada como `[finding]` na §7: o
    router **não pode** inferir "tenant-wide" de `unit_id is None`.
    """
    spy = _SpyIdentityGuard(_authorized_actor(scope_unit_id=None, role=Role.OWNER))
    translator = _IdentityAccessGuard(spy)

    scope = translator.authorize(object(), "manage_staff", tenant_id="t1")

    assert scope.unit_id is None
    assert scope.tenant_id == "t1"
    # E o pedido chegou a identity **sem** unidade: é o passo 4 que dispensa, não
    # o tradutor que inventa uma.
    assert spy.received["unit_id"] is None
    assert spy.received["permission"] is Permission.MANAGE_STAFF


def test_o_tradutor_repassa_o_ator_de_authenticate_sem_tocar_nele() -> None:
    """`Actor = object`: staff não interpreta a credencial, e o tradutor tampouco."""
    spy = _SpyIdentityGuard()
    translator = _IdentityAccessGuard(spy)
    request = object()

    assert translator.authenticate(request) == ("ator", request)


def _app_do_wiring() -> FastAPI:
    """Monta a app do mesmo jeito que `create_app()` — routers, handlers, overrides."""
    wiring = build_http_wiring(_dependencias())
    app = FastAPI()
    for registrar in wiring.register_error_handlers:
        registrar(app)
    app.dependency_overrides.update(wiring.dependency_overrides)
    for router in wiring.routers:
        app.include_router(router, prefix="/api/v1")
    return app


def _pares_montados(app: FastAPI) -> set[tuple[str, str]]:
    """Os `(método, path)` que a app **publica**, lidos do esquema OpenAPI.

    Ler do esquema, e não de `app.routes`, é medição e não preferência: nesta
    versão do FastAPI um router incluído vira um `_IncludedRouter` opaco, sem
    `.routes`, então varrer a lista de rotas devolve **zero** `APIRoute` e a
    asserção passaria vacuamente. O esquema é o que o cliente enxerga, e é
    estável entre versões — é a leitura certa para "a app registra as rotas".
    """
    esquema = app.openapi()
    return {
        (metodo.upper(), caminho)
        for caminho, operacoes in esquema["paths"].items()
        for metodo in operacoes
    }


def _pares_do_router(modulo: str) -> set[tuple[str, str]]:
    """Os `(método, path)` que um router **declara**, com o prefixo da aplicação.

    **A partição staff/identity vem daqui, e não de uma heurística sobre o
    texto do path.** A primeira versão separava as duas superfícies por
    substring (`"/job-functions" in path or "/units/" in path`), e ela funcionava
    por acidente: a rota de identity é `POST /restaurants/{id}/units`, sem barra
    final, e por um caractere não caía no balde de staff. Um `/units/{id}/…` novo
    em identity — ou um recurso de staff que não contivesse nenhuma das duas
    palavras — jogaria rotas no lado errado, e a contagem denunciaria com uma
    mensagem que não explica nada.

    O router **é** o contrato de quem publica o quê: pedir a ele a lista é a
    pergunta certa. E é o router isolado, não o incluído na app — só ele ainda
    tem `APIRoute` de verdade (ver `_pares_montados`).
    """
    router = importlib.import_module(f"{modulo}.router").router
    pares = {
        (sorted(rota.methods - {"HEAD", "OPTIONS"})[0], f"{_PREFIXO_DA_API}{rota.path}")
        for rota in router.routes
        if isinstance(rota, APIRoute)
    }
    assert pares, f"o router de {modulo} não declarou rota nenhuma"
    return pares


def _provedores_de(modulo: ModuleType) -> set[Callable[..., object]]:
    """As funções-chave de `dependency_overrides` **definidas** neste módulo.

    "Chave de override" é, por convenção do projeto, uma função sem argumentos que
    o router injeta por `Depends` e que o composition root substitui: `_get_*` nos
    módulos de router, `get_*` em `dependencies.py`. As duas formas são varridas
    porque as duas existem.

    O filtro por `__module__` é o que separa provedor de **import**: `get_args` e
    `get_origin`, importados de `typing`, casam o prefixo e não são chaves de nada.
    """
    return {
        valor
        for nome, valor in vars(modulo).items()
        if nome.startswith(("_get_", "get_"))
        and callable(valor)
        and getattr(valor, "__module__", None) == modulo.__name__
    }


def test_ca30_o_wiring_registra_os_dois_routers_e_os_dois_registradores() -> None:
    """CA30 — e é aqui que CA21 termina a sua vida útil.

    Até a Task 08 este arquivo guardava a promessa *"nenhuma rota de staff está
    registrada"*. A Task 09 é a que a torna **falsa de propósito**: as 16 rotas
    passam a existir na aplicação, que é o objetivo da Stage inteira. O que
    substitui a promessa não é nada — é a asserção de que as duas superfícies
    estão montadas, por identidade de objeto.
    """
    wiring = build_http_wiring(_dependencias())
    identity_router = importlib.import_module(f"{_PACOTE_HTTP_IDENTITY}.router").router
    staff_router = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router").router

    assert wiring.routers == (identity_router, staff_router)
    assert wiring.register_error_handlers == (
        importlib.import_module(
            f"{_PACOTE_HTTP_IDENTITY}.error_handlers"
        ).register_identity_error_handlers,
        importlib.import_module(
            f"{_PACOTE_HTTP_STAFF}.error_handlers"
        ).register_staff_error_handlers,
    )


def test_ca30_o_mapa_de_overrides_cobre_todo_provedor_do_router_de_staff() -> None:
    """A completude é **derivada**, e é o que a escrita explícita do wiring exige.

    Os 17 overrides são escritos um a um no composition root — como os de
    identity —, porque wiring é onde a ligação entre duas peças é declarada. O
    preço de escrever à mão é esquecer um; esta asserção é o troco: os provedores
    saem dos **dois** módulos por varredura, e um provedor novo sem override
    reprova aqui em vez de levantar `RuntimeError` no primeiro request.

    **Os dois módulos, e não só o router.** A primeira versão varria
    `vars(router)` atrás de `_get_*` e **acrescentava `get_access_guard` à mão**,
    porque ele mora em `dependencies.py`. O acréscimo manual era o buraco: um
    provedor novo nesse módulo — a chave de um `IdentityGateway`, quando o Step 4
    o trouxer — escaparia da varredura, entraria sem override, e voltaria a ser
    `RuntimeError` no primeiro request, que é exatamente o modo de falha que este
    teste existe para tornar impossível.

    **A varredura é filtrada por dono (`__module__`), e o filtro é necessário**:
    `dependencies.py` importa `get_args` e `get_origin` de `typing`, e os dois
    casam qualquer regra de nome que comece por `get_`. Sem o filtro, a
    cardinalidade subiria para 19 e a lista de "sem override" nomearia peças da
    biblioteca padrão.
    """
    wiring = build_http_wiring(_dependencias())
    staff_router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
    staff_dependencies = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.dependencies")

    provedores = _provedores_de(staff_router_module) | _provedores_de(staff_dependencies)

    sem_override = sorted(
        getattr(p, "__name__", repr(p)) for p in provedores if p not in wiring.dependency_overrides
    )

    assert sem_override == [], f"provedor de staff sem override no wiring: {sem_override}"
    assert len(provedores) == _TOTAL_DE_OVERRIDES_DE_STAFF


def test_ca30_cada_override_de_staff_devolve_a_dependencia_montada() -> None:
    """Existir a chave não basta: o valor tem de ser **o objeto do contêiner**.

    Um override que devolvesse um use case novo faria a app decidir sobre um grafo
    diferente do que o composition root montou — dois `Engine`, duas verdades. A
    asserção é de identidade, e é a mesma disciplina de
    `test_ca15_o_tradutor_embrulha_o_mesmo_identity_guard_das_rotas`.
    """
    deps = _dependencias()
    wiring = build_http_wiring(deps)
    staff_router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
    staff_dependencies = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.dependencies")

    assert wiring.dependency_overrides[staff_dependencies.get_access_guard]() is (
        deps.staff_access_guard
    )
    for nome, provedor in vars(staff_router_module).items():
        if not nome.startswith("_get_") or not callable(provedor):
            continue
        esperado = getattr(deps, f"staff_{nome.removeprefix('_get_')}")
        assert wiring.dependency_overrides[provedor]() is esperado, nome


def test_ca30_as_dezesseis_rotas_de_staff_ficam_montadas_sob_o_prefixo() -> None:
    """As 16 rotas passam a responder — e as de identity continuam como estavam.

    A varredura é sobre a **app real**, e não sobre o router isolado: é a app que
    o cliente alcança, e é nela que um prefixo errado ou um router não incluído
    apareceria. O que o router isolado entrega é a **partição**: quais pares são de
    staff e quais de identity — ver `_pares_do_router`, e a heurística de substring
    que ela substituiu.

    A interseção é a asserção que importa: `de_staff` não é "o que sobrou de um
    filtro de texto", é "o que o router de staff declara **e** a app publica". Se o
    router não estivesse incluído, ou estivesse sob outro prefixo, a interseção
    seria vazia e a contagem denunciaria.
    """
    montadas = _pares_montados(_app_do_wiring())
    de_staff = montadas & _pares_do_router(_PACOTE_HTTP_STAFF)

    assert len(de_staff) == _TOTAL_DE_ROTAS_DE_STAFF
    assert montadas - de_staff == _ROTAS_DE_IDENTITY
    assert all(path.startswith(_PREFIXO_DA_API) for _, path in montadas)


def test_ca30_o_inventario_de_identity_nao_regrediu() -> None:
    """CA31 pela via estrutural: identity continua servindo exatamente o que servia.

    O router de identity é o **mesmo objeto** que ele sempre foi — nada nesta
    Stage o reescreve —, então a asserção mede o que poderia ter mudado sem
    ninguém notar: o conjunto de rotas que a app monta a partir dele.

    **A comparação é com o conjunto literal, e a contagem sozinha não bastava.**
    A primeira versão asseria só `len(de_identity) == 10`: trocar `POST /users` por
    `POST /usuarios` — ou perder `/auth/logout` e ganhar outra rota no mesmo commit
    — mantinha o total em dez e passava. O que "não regrediu" quer dizer é *estes
    dez pares*, e é isso que `_ROTAS_DE_IDENTITY` escreve.

    A expectativa é **transcrita**, não colhida do router de identity: colhê-la
    dele faria os dois lados da igualdade virem da mesma fonte, e o teste passaria
    a confirmar que o router concorda consigo mesmo.
    """
    identity_router = importlib.import_module(f"{_PACOTE_HTTP_IDENTITY}.router").router
    wiring = build_http_wiring(_dependencias())

    assert wiring.routers[0] is identity_router
    de_identity = _pares_montados(_app_do_wiring()) - _pares_do_router(_PACOTE_HTTP_STAFF)

    assert de_identity == _ROTAS_DE_IDENTITY
    assert len(de_identity) == _TOTAL_DE_ROTAS_DE_IDENTITY

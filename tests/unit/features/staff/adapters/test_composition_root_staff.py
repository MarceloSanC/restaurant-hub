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
import importlib
import inspect
import pathlib

import pytest

from restaurant_hub.composition_root import (
    ApplicationDependencies,
    _IdentityAccessGuard,
    build_http_wiring,
    wire_dependencies,
)
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
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


@pytest.mark.parametrize(("actor_tenant_id", "role"), _ATOR_SEM_TENANT)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_ator_sem_tenant_e_negado_pelo_tradutor(
    permission: str,
    unit: str | None,
    actor_tenant_id: str | None,
    role: Role,
) -> None:
    """L-AG3 imposta no tradutor, e não delegada à matriz de papéis.

    Hoje `platform_admin` já seria negado antes, no passo 2 do guard, por não
    deter as permissões de staff. Confiar nisso faria o isolamento de tenant
    refém do mapa RBAC — que é editável, e cuja edição nenhum teste desta lei
    observaria. Por isso o cenário montado é o pior caso: identity **autorizou**
    e devolveu um ator sem tenant — e vale para as **duas** permissões, porque
    L-AG3 é propriedade do guard e não de uma capacidade.
    """
    spy = _SpyIdentityGuard(_authorized_actor(actor_tenant_id=actor_tenant_id, role=role))
    translator = _IdentityAccessGuard(spy)

    with pytest.raises(PermissionDeniedError):
        translator.authorize(object(), permission, tenant_id="t1", unit_id=unit)


@pytest.mark.parametrize(("actor_tenant_id", "role"), _ATOR_SEM_TENANT)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_o_tradutor_nunca_coage_tenant_ausente_para_string_vazia(
    permission: str,
    unit: str | None,
    actor_tenant_id: str | None,
    role: Role,
) -> None:
    """A mutação que L-AG3 existe para matar, escrita como asserção.

    `StaffTenantId(actor_tenant_id or "")` compila, passa mypy strict e devolve
    um escopo de tenant vazio — consultas que atravessariam todos os tenants.
    A exigência aqui é dupla: **nada** é devolvido, e o que sobe é negação.
    """
    spy = _SpyIdentityGuard(_authorized_actor(actor_tenant_id=actor_tenant_id, role=role))
    translator = _IdentityAccessGuard(spy)

    scopes = []
    with contextlib.suppress(PermissionDeniedError):
        scopes.append(translator.authorize(object(), permission, tenant_id="t1", unit_id=unit))

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


def test_ca21_nenhuma_rota_de_staff_nasceu_nesta_stage() -> None:
    """CA21 — a promessa "nenhuma rota nasce aqui" verificada, não afirmada.

    Três asserções, e as três são necessárias: o pacote de adapters de entrada de
    staff **não existe**; `build_http_wiring` devolve o router **de identity**,
    por identidade de objeto; e nenhuma rota registrada endereça recurso de
    staff — que é o que pegaria uma rota de funcionário pendurada no router de
    identity, cenário em que as duas primeiras asserções continuariam verdes.
    """
    assert not (_SRC / "features" / "staff" / "adapters" / "in").exists()

    wiring = build_http_wiring(_dependencias())
    identity_router = importlib.import_module(
        "restaurant_hub.features.identity.adapters.in.http.router"
    ).router

    assert wiring.router is identity_router

    paths = [getattr(rota, "path", "") for rota in wiring.router.routes]
    assert not [
        path for path in paths if "employee" in path or "job-function" in path or "staff" in path
    ], f"rota de staff registrada nesta Stage: {paths}"

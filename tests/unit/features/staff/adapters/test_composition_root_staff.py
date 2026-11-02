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
O arquivo ganhou dois assuntos. O primeiro era o `_IdentityAccessGuard` (CA15),
a implementação de **produção** das quatro leis do port, que morava neste
módulo; a issue #47 o moveu para `staff/adapters/out/identity/` como
`LocalAccessGuard`, e as leis foram com ele para `test_local_access_guard.py`.
Aqui fica o que é do wiring: qual classe é montada e sobre quais objetos. O
segundo é o CA21: a Stage promete que
**nenhuma rota nasce**, e a promessa fica verificada aqui, contra o
`build_http_wiring` real, em vez de afirmada num documento.
"""

import ast
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
    build_http_wiring,
    wire_dependencies,
)
from restaurant_hub.features.identity.adapters.inbound.http.dependencies import IdentityGuard
from restaurant_hub.features.identity.adapters.inbound.http.error_handlers import (
    register_identity_error_handlers,
)
from restaurant_hub.features.identity.adapters.inbound.http.router import router as identity_router
from restaurant_hub.features.identity.application.facade import (
    IdentityAccessFacade,
    IdentityFacade,
)
from restaurant_hub.features.staff.adapters.inbound.http import dependencies as staff_dependencies
from restaurant_hub.features.staff.adapters.inbound.http import router as staff_router_module
from restaurant_hub.features.staff.adapters.inbound.http.error_handlers import (
    register_staff_error_handlers,
)
from restaurant_hub.features.staff.adapters.inbound.http.router import router as staff_router
from restaurant_hub.features.staff.adapters.out.identity.local_access_guard import (
    LocalAccessGuard,
)
from restaurant_hub.features.staff.adapters.out.identity.local_identity_gateway import (
    LocalIdentityGateway,
)
from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
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
    "staff_create_login_for_employee",
)

# 16 até a 3.4; a Stage 3.5 acrescenta `create_login_for_employee` (R17).
_TOTAL_DE_USE_CASES = 17


def _dependencias() -> ApplicationDependencies:
    """O grafo real, sem banco no ar — `create_engine` não abre conexão."""
    return wire_dependencies(Settings(_env_file=None))


def test_ca18_todos_os_use_cases_de_staff_estao_no_conteiner() -> None:
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
    # Módulos `_`-prefixados são auxiliares da camada, não use cases — a mesma
    # convenção de `test_application_guards.py`. Hoje não há nenhum: o mapper
    # único de `EmployeeResult`, que a Stage 3.5 criou como `_results.py`, mora
    # em `dtos/results.py` desde a sincronização com a issue #45.
    na_pasta = {arquivo.stem for arquivo in pasta.glob("*.py") if not arquivo.stem.startswith("_")}
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


def test_ca08_todo_use_case_de_staff_recebe_o_mesmo_guard_das_rotas() -> None:
    """Identidade de objeto, para os 17 (Stage 3.7, ADR 3.7.0001 §1).

    Um segundo `LocalAccessGuard` satisfaria qualquer teste de tipo e faria a
    borda e a application decidirem acesso sobre grafos diferentes — a rota
    autorizaria contra um `IdentityGuard`, o use case contra outro, e a defesa em
    profundidade deixaria de ser a mesma decisão tomada duas vezes.
    """
    deps = _dependencias()

    diferentes = [
        nome
        for nome in _USE_CASES_DE_STAFF
        if getattr(deps, nome)._guard is not deps.staff_access_guard
    ]
    assert diferentes == []


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


@pytest.mark.parametrize(
    "codigo_violador",
    [
        pytest.param(
            "from restaurant_hub.features.staff.adapters.out.postgres.employee_repository "
            "import PostgresEmployeeRepository",
            id="repositorio-postgres",
        ),
        pytest.param(
            "from restaurant_hub.features.staff.adapters.out.identity.local_identity_gateway "
            "import LocalIdentityGateway",
            id="gateway-de-identity",
        ),
    ],
)
def test_um_import_proibido_plantado_reprova(codigo_violador: str) -> None:
    """Teste negativo: o detector detecta — e alcança o pacote novo da Stage 3.5.

    Um guarda que nunca viu um caso positivo não é um guarda — é uma função que
    devolve conjunto vazio. O segundo caso existe porque `adapters/out/identity/`
    nasceu depois do detector: a cobertura da varredura sobre ele é o que se
    verifica, não o resultado dela.
    """
    arvore = ast.parse(codigo_violador)

    alvos = [no.module for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.module]

    assert any(_MODULO_DE_ADAPTERS in alvo for alvo in alvos)


# ---------------------------------------------------------------------------
# Stage 3.5 — o gateway de identity (CA07 wiring, CA32)
# ---------------------------------------------------------------------------


def test_ca07_o_gateway_de_identity_e_o_local_sobre_a_fachada_das_rotas() -> None:
    """Identidade de objeto, não `isinstance`: um grafo, não dois.

    A fachada por baixo do gateway tem de usar **os mesmos** repositórios,
    `sender` e `clock` que servem as rotas de identity. Uma segunda
    `PostgresUserRepository` satisfaria qualquer teste de tipo e faria o login do
    funcionário nascer num pool diferente do que a rota `/auth/login` consulta —
    sem ganho nenhum e com um `Engine` a mais (ADR 3.5.0001 §Implementation
    notes; mesmo raciocínio de CA15 para o `IdentityGuard`).
    """
    deps = _dependencias()

    assert isinstance(deps.staff_identity_gateway, LocalIdentityGateway)
    fachada = deps.staff_identity_gateway._facade
    assert isinstance(fachada, IdentityFacade)

    provisao = fachada._provision_account
    convite = deps.identity_invite_user
    assert provisao._users is convite._users
    assert provisao._restaurants is convite._restaurants
    assert provisao._units is convite._units
    assert provisao._hasher is convite._hasher
    assert provisao._tokens is convite._tokens
    assert provisao._token_issuer is convite._token_issuer
    assert provisao._clock is convite._clock
    assert fachada._send_invitation._email_sender is convite._email_sender
    assert fachada._revoke_all_sessions._sessions is deps.identity_revoke_session._sessions
    assert fachada._revoke_all_sessions._clock is deps.identity_revoke_session._clock
    # Stage 3.8 — a consulta do papel lê o **mesmo** `users` que cria as contas:
    # um segundo repositório responderia "desconhecido" ao login recém-criado,
    # e o desligamento nunca revogaria (ADR 3.8.0001 §3).
    assert fachada._get_account_role._users is convite._users


def test_o_conteiner_de_staff_tem_exatamente_os_campos_declarados() -> None:
    """Os 17 use cases mais os dois ports consumidos — nenhum campo entra de carona.

    Como `staff_access_guard` na 3.4, `staff_identity_gateway` é anotado com o
    **port**, não com a classe. Este teste trava o conjunto para que um campo
    novo entre por decisão.
    """
    campos_de_staff = {
        nome for nome in ApplicationDependencies.__dataclass_fields__ if nome.startswith("staff_")
    }

    assert campos_de_staff == {*_USE_CASES_DE_STAFF, "staff_access_guard", "staff_identity_gateway"}
    assert ApplicationDependencies.__dataclass_fields__["staff_identity_gateway"].type is (
        IdentityGateway
    )


# ---------------------------------------------------------------------------
# O `AccessGuard` de staff montado (CA15) e a prova de CA21
#
# As quatro leis do port, contra a implementação de produção, moram em
# `test_local_access_guard.py` desde a issue #47 — que tirou o tradutor deste
# módulo (`_IdentityAccessGuard`) e o pôs em `staff/adapters/out/identity/`.
# Aqui fica só o que é do wiring: qual classe, sobre quais objetos.
# ---------------------------------------------------------------------------


# Cardinalidades declaradas — piso contra a varredura encolher em silencio.
# 17 overrides (16 `_get_*` + `get_access_guard`) e 16 rotas até a 3.6; a Stage
# 3.5 acrescenta o provedor e a rota de R17.
_TOTAL_DE_OVERRIDES_DE_STAFF = 18
_TOTAL_DE_ROTAS_DE_STAFF = 17
_TOTAL_DE_ROTAS_DE_IDENTITY = 10
_PACOTE_HTTP_IDENTITY = "restaurant_hub.features.identity.adapters.inbound.http"
_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.inbound.http"
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


def test_ca15_o_access_guard_de_staff_e_o_local_sobre_a_fachada_de_acesso() -> None:
    """A implementação montada é a do adapter — e o composition root não tem mais classe.

    `AccessGuard` é `Protocol`, então `isinstance` contra o port não responde; a
    forma é cobrada em `test_local_access_guard.py`. O que se assere aqui é a
    troca da issue #47: o campo é preenchido pelo adapter de staff, e nenhuma
    classe que não seja contêiner sobrou no `composition_root`.
    """
    deps = _dependencias()

    assert isinstance(deps.staff_access_guard, LocalAccessGuard)
    assert isinstance(deps.staff_access_guard._access, IdentityAccessFacade)
    assert ApplicationDependencies.__dataclass_fields__["staff_access_guard"].type is AccessGuard
    classes_do_root = {
        no.name
        for no in ast.parse(_COMPOSITION_ROOT.read_text(encoding="utf-8")).body
        if isinstance(no, ast.ClassDef)
    }
    assert classes_do_root == {"ApplicationDependencies", "HttpWiring"}


def test_ca15_o_guard_de_staff_decide_sobre_o_mesmo_grafo_das_rotas_de_identity() -> None:
    """Identidade de objeto, e não `isinstance` — nas **duas** metades do guard.

    Um **segundo** `AuthorizeActionUseCase` (ou um segundo `IdentityGuard`)
    satisfaria qualquer teste de tipo e faria as duas bordas decidirem acesso
    sobre grafos distintos, com dois `Engine`. Autenticar tem de ser o método
    do **mesmo** guard que serve as rotas de identity — é ele que anota o ator
    para o log (#26) — e autorizar tem de passar pelo **mesmo** use case.
    """
    deps = _dependencias()
    guard = deps.staff_access_guard
    assert isinstance(guard, LocalAccessGuard)

    assert guard._access._authorize_action is deps.identity_authorize_action
    assert deps.identity_guard._authorize_action is deps.identity_authorize_action
    autenticar = guard._authenticate_request
    assert getattr(autenticar, "__self__", None) is deps.identity_guard
    assert getattr(autenticar, "__func__", None) is IdentityGuard.authenticate_principal


def test_o_campo_identity_guard_e_tipado_desde_a_47() -> None:
    """Era `Any` (herança do pacote `in`); a #47, que moveu o consumidor, o anotou."""
    assert ApplicationDependencies.__dataclass_fields__["identity_guard"].type is IdentityGuard


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

    assert wiring.routers == (identity_router, staff_router)

    assert wiring.register_error_handlers == (
        register_identity_error_handlers,
        register_staff_error_handlers,
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

    assert wiring.dependency_overrides[staff_dependencies.get_access_guard]() is (
        deps.staff_access_guard
    )
    for nome, provedor in vars(staff_router_module).items():
        if not nome.startswith("_get_") or not callable(provedor):
            continue
        esperado = getattr(deps, f"staff_{nome.removeprefix('_get_')}")
        assert wiring.dependency_overrides[provedor]() is esperado, nome


def test_ca30_todas_as_rotas_de_staff_ficam_montadas_sob_o_prefixo() -> None:
    """As 17 rotas passam a responder — e as de identity continuam como estavam.

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

    wiring = build_http_wiring(_dependencias())

    assert wiring.routers[0] is identity_router
    de_identity = _pares_montados(_app_do_wiring()) - _pares_do_router(_PACOTE_HTTP_STAFF)

    assert de_identity == _ROTAS_DE_IDENTITY
    assert len(de_identity) == _TOTAL_DE_ROTAS_DE_IDENTITY


def test_ca07_deactivate_e_create_login_recebem_a_mesma_instancia_do_gateway() -> None:
    """Um gateway, uma fachada, um grafo — identidade de objeto nos dois consumidores."""
    deps = _dependencias()

    assert deps.staff_deactivate_employee._gateway is deps.staff_identity_gateway
    assert deps.staff_create_login_for_employee._gateway is deps.staff_identity_gateway
    assert (
        deps.staff_create_login_for_employee._employees is deps.staff_deactivate_employee._employees
    )


@pytest.mark.parametrize(
    ("campo", "recebe_gateway"),
    [
        pytest.param("staff_create_login_for_employee", True, id="create-login"),
        pytest.param("staff_deactivate_employee", True, id="deactivate"),
        pytest.param("staff_delete_employee", False, id="delete"),
        pytest.param("staff_reactivate_employee", False, id="reactivate"),
    ],
)
def test_so_r13_e_r17_recebem_o_gateway(campo: str, recebe_gateway: bool) -> None:
    """ADR 3.5.0003: R15 recusa sem falar com identity; R14 não altera o vínculo.

    A assinatura do construtor é a evidência: um `gateway` que aparecesse em
    `DeleteEmployeeUseCase` seria o começo de "apagar revoga", a alternativa E
    rejeitada no ADR.
    """
    deps = _dependencias()
    parametros = inspect.signature(type(getattr(deps, campo)).__init__).parameters

    assert ("gateway" in parametros) is recebe_gateway

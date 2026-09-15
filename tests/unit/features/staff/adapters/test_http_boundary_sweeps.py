"""Varreduras de borda do adapter HTTP de staff — CA01, CA02(b), CA05, CA14, CA20, CA21, CA23, CA24.

**Nenhum `parametrize` deste arquivo lista rota, campo ou módulo à mão.** Os
domínios saem de `router.routes`, de `model_fields`, do helper de introspecção de
`dependencies.py` e do próprio pacote. É o que faz uma rota escrita nas Tasks
06/07/08 entrar automaticamente nestas travas — e é a razão de este módulo nascer
com quatro rotas em vez de dezesseis: ele não mede as rotas de hoje, mede a
**lei**, e o conjunto sobre o qual a lei é cobrada cresce sozinho.

## As duas defesas contra o falso verde, e as duas são necessárias

Das 14 rotas com identificador, oito terão corpo obrigatório e uma exigirá
`start`/`end` na query. Invocada **sem** corpo válido, qualquer uma delas responde
**422 pelo `RequestValidationError` do framework** — o que significa que uma
varredura de identificador inválido que assere só `status == 422` fica **verde
mesmo com o validador ausente**. Duas defesas fecham isso:

1. **Invocar sempre pelo `_INVOCACOES`** — corpo e query válidos, só o
   identificador sob teste corrompido —, para que o 422 do framework não apareça;
2. **Asserir o discriminador de corpo de staff** (`type == "staff_error"`), para
   que, se ele aparecer mesmo assim, não conte como aprovação.

A totalidade da fixture é asserção, não convenção:
`set(_INVOCACOES) == {chave(r) for r in router.routes}`. Rota sem declaração
**reprova** — é o que obriga a Task que escreve uma rota nova a dizer como
invocá-la, em vez de deixá-la entrar muda na varredura.
"""

import ast
import importlib
import pathlib
import pkgutil
import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, get_args, get_origin

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response
from pydantic import BaseModel

from restaurant_hub.features.staff.domain.exceptions.errors import InvalidIdentifierError
from tests.fakes.features.staff.in_memory_access_guard import FakeAuthorizationRejected
from tests.unit.features.staff.adapters.test_http_router_job_functions import Ambiente

pytestmark = pytest.mark.unit

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"
_PACOTE_TESTES_ADAPTER = "tests.unit.features.staff.adapters"

router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
dependencies_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.dependencies")
schemas_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.schemas")

_CORPO_DE_STAFF = "staff_error"

# Um passo de caminho é o **nome** de um campo ou o **índice** de um elemento de
# lista. O índice é o que permite corromper um período de `shift_preference` sem
# desmontar a lista que o carrega.
Caminho = tuple[str | int, ...]

# O tamanho do domínio de corpo de CA24 **depois** de a varredura descer por
# lista. Eram dez pares (rota, caminho); os três novos são um elemento de
# `job_function_ids` em cada uma das duas rotas que o aceitam e o período de
# `shift_preference`. A contagem é transcrita, e não derivada: é ela que faz um
# encolhimento do domínio reprovar em vez de reduzir em silêncio os casos rodados.
# 13 até a 3.6; a Stage 3.5 acrescenta `email` e `delivery` de R17.
_TOTAL_DE_CAMPOS_ESCALARES = 15

# Alias local do tipo devolvido por `identifier_fields` — o módulo chega por
# `importlib` (o pacote `in` é keyword), então o nome não existe como import.
IdentifierField = dependencies_module.IdentifierField

# Os três valores que o ADR 3.6.0002 §2 rejeita. O eixo de **path** usa só dois:
# um segmento vazio não casa `[^/]+`, e o Starlette responde 404/405 sem que o
# handler rode (§6.3 do concept). Exigir 422 ali produziria célula vermelha
# irredutível — e critério de segurança que não fecha é critério que alguém
# relaxa.
_IDENTIFICADORES_INVALIDOS = ("", "   ", "\x00")
_IDENTIFICADORES_INVALIDOS_EM_PATH = ("   ", "\x00")

# Os valores do conjunto adversarial abaixo que o **validador de identificador**
# recusa (ADR 3.6.0002 §2). Transcritos, e nao perguntados ao codigo sob teste:
# perguntar faria a expectativa seguir o defeito. Ha teste que cruza esta
# transcricao com o validador real, para que ela nao possa envelhecer em silencio.
# O e-mail com NUL (3.5) tambem cai aqui: o validador recusa **qualquer** string
# com o byte, e o eixo de path o exercita como identificador.
_ADVERSARIAIS_RECUSADOS_PELO_VALIDADOR = frozenset({"", "\x00", "nul\x00@dentro.com"})

# Conjunto adversarial da Stage 3.3 mais os numéricos degenerados de CA24. O
# critério é **ausência de 500**: qualquer um destes pode ser aceito ou recusado,
# e as duas coisas são respostas legítimas; o que não pode é o servidor quebrar.
_VALORES_ADVERSARIAIS = (
    "José Antônio",
    "\U0001f469‍\U0001f373",
    "linha1\nlinha2",
    'Ana "Nana" O\'Brien',
    "a" * 1000,
    "\x00",
    "abc",
    "",
    "40,5",
    "NaN",
    "Infinity",
    "-1",
    "0",
    # Stage 3.5 (D8): um e-mail **bem-formado para a regex** com NUL no meio. Era
    # 500 em identity; aqui só se prova "sem 500" — o 422 é do VO `Email` (Task
    # 06) e do e2e (Task 12).
    "nul\x00@dentro.com",
)


# ---------------------------------------------------------------------------
# O domínio derivado: rotas, invocações e a totalidade que liga as duas
# ---------------------------------------------------------------------------

ChaveDeRota = tuple[str, str]


@dataclass(frozen=True)
class Invocacao:
    """A declaração de **uma** rota: como invocá-la, e o que a §4.1 promete.

    Attributes:
        path: um valor válido para cada parâmetro de path.
        query: os parâmetros de query que a rota exige.
        body: o corpo mínimo que o framework aceita, ou `None`.
        sucesso: o status de sucesso da tabela do concept §4.1 — **transcrito à
            mão**, e não derivado de `rota.status_code`. Derivá-lo provaria
            apenas que o código concorda consigo mesmo; é o contrato externo que
            precisa ser conferido contra a implementação, e para isso ele tem de
            vir de fora dela.
    """

    path: dict[str, str]
    query: dict[str, str]
    body: dict[str, Any] | None
    sucesso: int


def _rotas() -> list[APIRoute]:
    """As rotas do router de staff, e só elas."""
    encontradas = [rota for rota in router_module.router.routes if isinstance(rota, APIRoute)]
    assert encontradas, "a varredura precisa de rotas para ter o que medir"
    return encontradas


def chave(rota: APIRoute) -> ChaveDeRota:
    """`(método, path)` — a identidade de uma rota para todas as varreduras."""
    metodos = sorted(rota.methods - {"HEAD", "OPTIONS"})
    assert len(metodos) == 1, f"rota com mais de um método: {rota.path} {metodos}"
    return (metodos[0], rota.path)


def _invocacoes_declaradas() -> dict[ChaveDeRota, Invocacao]:
    """Colhe as declarações de invocação dos módulos de teste de rota do pacote.

    **Derivado, e não importado nominalmente.** Um `import` explícito por módulo
    faria cada Task de rota editar este arquivo — exatamente o acoplamento que a
    estratégia da Stage existe para evitar. Varrer o pacote deixa a declaração no
    módulo da Task que escreveu a rota, e a totalidade abaixo cobra quem esquecer.
    """
    pacote = importlib.import_module(_PACOTE_TESTES_ADAPTER)
    reunidas: dict[ChaveDeRota, Invocacao] = {}

    for info in sorted(pkgutil.iter_modules(list(pacote.__path__)), key=lambda i: i.name):
        if not info.name.startswith("test_http_router_"):
            continue
        modulo = importlib.import_module(f"{_PACOTE_TESTES_ADAPTER}.{info.name}")
        declaradas: dict[ChaveDeRota, dict[str, Any]] = getattr(modulo, "INVOCACOES", {})

        colisoes = sorted(set(declaradas) & set(reunidas))
        assert not colisoes, f"{info.name} redeclara invocação de rota já declarada: {colisoes}"

        for chave_da_rota, bruta in declaradas.items():
            reunidas[chave_da_rota] = Invocacao(
                path=dict(bruta["path"]),
                query=dict(bruta["query"]),
                body=bruta["body"],
                sucesso=int(bruta["sucesso"]),
            )
    return reunidas


_INVOCACOES = _invocacoes_declaradas()


def test_a_fixture_de_invocacao_e_total_sobre_as_rotas_do_router() -> None:
    """Rota sem invocação declarada **reprova** — é o gate da estratégia inteira.

    Sem esta asserção, uma rota nova entraria muda em CA20/CA23/CA24: nenhuma
    varredura a alcançaria, todas continuariam verdes, e a Task que a escreveu não
    reprovaria a si mesma. É o mesmo mecanismo que CA17 aplica às exceções, e
    removê-lo porque "uma rota nova não tem chave" é o mesmo movimento que
    relaxar CA17 porque "um erro novo não tem entrada".
    """
    assert set(_INVOCACOES) == {chave(rota) for rota in _rotas()}


def test_a_totalidade_e_o_que_trava_o_inventario_de_rotas() -> None:
    """CA01, a metade "nem rota a mais nem a menos" — e onde ela agora vive.

    Com a aposentadoria da lista literal, é a **totalidade** que impede uma 17ª
    rota de existir em silêncio: ela teria de vir acompanhada de uma declaração
    escrita à mão num módulo de teste, que é um ato deliberado e visível em
    revisão — exatamente o que a lista literal cobrava, sem o custo de alguém ter
    de lembrar de estendê-la.

    É assim que o `non_goal` "leitura de funcionário por id" fica travado: não
    por ninguém lembrar dele, mas porque a rota nova reprova até ser declarada.
    """
    declaradas = set(_INVOCACOES)
    registradas = {chave(rota) for rota in _rotas()}

    assert declaradas == registradas
    assert len(declaradas) == len(_rotas()), "duas rotas com a mesma chave"


def _url(chave_da_rota: ChaveDeRota, invocacao: Invocacao, *, sobrescreve: dict[str, str]) -> str:
    """Monta a URL concreta, com os parâmetros de path **percent-encoded**.

    **O encoding não é conveniência de teste: é como o caso chega em produção.**
    O concept nomeia literalmente `GET /units/%00/employees`, e um cliente HTTP
    não tem outra forma de pôr um byte NUL — ou uma quebra de linha — num path.
    Medido: `httpx` recusa montar a URL com o caractere cru
    (`InvalidURL: Invalid non-printable ASCII character`), então enviar o valor
    literal não testaria a rota, testaria o cliente. O Starlette decodifica o
    `%00` de volta antes de entregar o parâmetro ao handler, que é exatamente o
    caminho que o validador de identificador existe para fechar.
    """
    _, template = chave_da_rota
    valores = {**invocacao.path, **sobrescreve}
    caminho = template
    for nome, valor in valores.items():
        caminho = caminho.replace(f"{{{nome}}}", urllib.parse.quote(valor, safe=""))
    return f"/api/v1{caminho}"


async def _invocar(
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    *,
    path: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Response:
    """Invoca a rota pela sua invocação declarada, salvo o que o teste sobrescreve.

    A invocação vem sempre do `_INVOCACOES` — não é parâmetro — para que nenhum
    teste possa, por descuido, invocar uma rota com corpo vazio e medir o 422 do
    framework em vez do erro de staff.
    """
    invocacao = _INVOCACOES[chave_da_rota]
    metodo, _ = chave_da_rota
    return await client.request(
        metodo,
        _url(chave_da_rota, invocacao, sobrescreve=path or {}),
        params={**invocacao.query, **(query or {})},
        json=invocacao.body if body is None else body,
    )


@pytest.fixture
def ambiente() -> Ambiente:
    return Ambiente()


@pytest.fixture
async def client(ambiente: Ambiente) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


# ---------------------------------------------------------------------------
# CA01 — o inventário de rotas
# ---------------------------------------------------------------------------
#
# **Não há lista literal de rotas neste arquivo, e a ausência é a decisão.** Uma
# tabela aqui teria de ser estendida por cada Task que acrescenta rota — isto é,
# o instrumento que existe para matar a família "lei universal, representante
# estreito" reinstalaria a mesma família em si mesmo, na forma de uma lista que
# alguém precisa lembrar de manter. O contrato do §4.1 continua **transcrito à
# mão**, rota a rota, no campo `sucesso` da declaração — só que co-locado com a
# invocação, no módulo da Task que escreveu a rota.


@pytest.mark.parametrize("rota", _rotas(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}")
def test_ca01_o_status_de_sucesso_bate_com_o_declarado_no_concept(rota: APIRoute) -> None:
    """Método e status de sucesso, rota a rota, contra a transcrição do §4.1.

    O valor comparado **não** sai do router: sai da declaração escrita por quem
    leu a tabela do concept. É isso que faz esta asserção medir conformidade com
    o contrato em vez de tautologia.
    """
    # `status_code` fica `None` quando a rota não o declara — o default do
    # FastAPI é 200, e é ele que a declaração registra.
    assert (rota.status_code or HTTPStatus.OK) == _INVOCACOES[chave(rota)].sucesso


@pytest.mark.parametrize("rota", _rotas(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}")
def test_ca01_cada_rota_chama_exatamente_um_use_case(rota: APIRoute) -> None:
    """Uma rota que orquestrasse dois use cases seria regra de negócio no adapter.

    O domínio sai do próprio handler: contam-se as chamadas `<algo>.execute(...)`
    no corpo da função de rota. Duas seriam composição — que pertence a um use
    case, não à borda.
    """
    fonte = ast.parse(pathlib.Path(router_module.__file__).read_text(encoding="utf-8"))
    handler = next(
        no
        for no in ast.walk(fonte)
        if isinstance(no, ast.FunctionDef) and no.name == rota.endpoint.__name__
    )

    execucoes = [
        no
        for no in ast.walk(handler)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr == "execute"
    ]

    assert len(execucoes) == 1, f"{rota.path} chama {len(execucoes)} use cases"


# ---------------------------------------------------------------------------
# CA02(b) e CA14 — varreduras de AST sobre o módulo do router
# ---------------------------------------------------------------------------


def _arvore_do_router() -> ast.Module:
    return ast.parse(pathlib.Path(router_module.__file__).read_text(encoding="utf-8"))


def _variaveis_de_escopo(handler: ast.FunctionDef) -> set[str]:
    """Nomes ligados ao retorno de `<guard>.authorize(...)` dentro do handler.

    Derivar o nome — em vez de presumir que se chama `scope` — é o que faz a
    varredura continuar valendo se uma rota futura o chamar de outra coisa.
    """
    ligados: set[str] = set()
    for no in ast.walk(handler):
        if not isinstance(no, ast.Assign) or not isinstance(no.value, ast.Call):
            continue
        chamada = no.value
        if isinstance(chamada.func, ast.Attribute) and chamada.func.attr == "authorize":
            ligados |= {alvo.id for alvo in no.targets if isinstance(alvo, ast.Name)}
    return ligados


def _handlers_do_router() -> list[ast.FunctionDef]:
    nomes = {rota.endpoint.__name__ for rota in _rotas()}
    encontrados = [
        no
        for no in ast.walk(_arvore_do_router())
        if isinstance(no, ast.FunctionDef) and no.name in nomes
    ]
    assert len(encontrados) == len(nomes), "algum handler de rota não foi encontrado no AST"
    return encontrados


def test_ca02b_o_tenant_id_de_todo_command_vem_do_escopo_autorizado() -> None:
    """A metade que a lista negra dos schemas não alcança.

    CA02(a) prova que nenhum request **declara** um campo de tenant; esta metade
    prova que o router não o tira de lugar nenhum além de
    `AuthorizedScope.tenant_id`. Sem ela, um `restaurant_id` de corpo consumido
    aqui passaria pela lista negra sem tocá-la.
    """
    problemas: list[str] = []
    for handler in _handlers_do_router():
        escopos = _variaveis_de_escopo(handler)
        for no in ast.walk(handler):
            if not isinstance(no, ast.Call):
                continue
            for argumento in no.keywords:
                if argumento.arg != "tenant_id":
                    continue
                origem = argumento.value
                correto = (
                    isinstance(origem, ast.Attribute)
                    and origem.attr == "tenant_id"
                    and isinstance(origem.value, ast.Name)
                    and origem.value.id in escopos
                )
                if not correto:
                    problemas.append(f"{handler.name}:{no.lineno}")

    assert problemas == [], f"tenant_id com origem diferente do escopo autorizado: {problemas}"


def test_ca02b_a_varredura_de_tenant_reprova_um_caso_plantado() -> None:
    """Guarda que nunca viu um positivo não é guarda.

    Sem este teste, um `_variaveis_de_escopo` que devolvesse o universo — ou um
    laço que nunca entrasse — deixaria a asserção acima verde por vacuidade.
    """
    fonte = ast.parse(
        "def rota(payload, guard, actor):\n"
        "    scope = guard.authorize(actor, 'p')\n"
        "    return Cmd(tenant_id=payload.restaurant_id)\n"
    )
    handler = next(no for no in ast.walk(fonte) if isinstance(no, ast.FunctionDef))
    escopos = _variaveis_de_escopo(handler)

    origens = [
        argumento.value
        for no in ast.walk(handler)
        if isinstance(no, ast.Call)
        for argumento in no.keywords
        if argumento.arg == "tenant_id"
    ]

    assert escopos == {"scope"}
    assert len(origens) == 1
    assert not (
        isinstance(origens[0], ast.Attribute)
        and isinstance(origens[0].value, ast.Name)
        and origens[0].value.id in escopos
    )


def test_ca14_nenhum_handler_le_o_unit_id_do_escopo_autorizado() -> None:
    """Defesa em profundidade, **não** a trava — e o docstring diz por quê.

    `getattr(scope, "unit_id")`, `astuple(scope)` e `asdict(scope)["unit_id"]`
    contornam esta varredura sem esforço. A trava de verdade é CA15, com o dublê
    adversarial que **contradiz de propósito** as duas implementações do port.

    A busca é pelo **atributo sobre a variável do escopo**, e não pela string
    `unit_id` no arquivo: parâmetros de path chamam-se legitimamente `unit_id`, e
    procurar o texto reprovaria as rotas de funcionário por existirem.
    """
    leituras: list[str] = []
    for handler in _handlers_do_router():
        escopos = _variaveis_de_escopo(handler)
        leituras += [
            f"{handler.name}:{no.lineno}"
            for no in ast.walk(handler)
            if isinstance(no, ast.Attribute)
            and no.attr == "unit_id"
            and isinstance(no.value, ast.Name)
            and no.value.id in escopos
        ]

    assert leituras == [], f"handler lendo AuthorizedScope.unit_id: {leituras}"


# ---------------------------------------------------------------------------
# `AccessRequirement.names_unit` — a declaração cobrada contra a chamada
# ---------------------------------------------------------------------------
#
# **O campo era declarado e nunca lido.** `grep -rn "names_unit" src/` devolvia
# só a definição: cada rota decidia à mão se passava `unit_id=` ao guard, e a
# promessa do docstring — *"concentrá-lo num valor por rota é o que impede que
# duas rotas do mesmo recurso declarem requisitos diferentes sem que ninguém
# note"* — valia só para a **permissão**. Uma rota de funcionário que esquecesse
# o `unit_id=` autorizaria contra o tenant inteiro, e nenhuma varredura acusaria:
# no ambiente unitário o fake concede pelo alvo pedido, e em produção o passo 4
# do guard só reclamaria se a permissão não fosse tenant-wide.
#
# A varredura é o que torna `names_unit` **carga real** sem replumbar produção no
# fim da Stage: quem lê o campo é este teste, e ler é o que impede a declaração e
# a chamada de divergirem. Plugá-lo no router seria a outra saída, e mexeria nas
# 19 chamadas ao guard por um ganho que esta asserção já entrega.
#
# 17 até a 3.6 (16 rotas + a segunda autorização de R16); a Stage 3.5 acrescenta
# R17, que autoriza **duas** vezes sobre o mesmo alvo (`manage_staff` e
# `manage_users`, concept 3.5 §5.3) — 19.
_TOTAL_DE_AUTORIZACOES = 19


def _requisitos_declarados() -> dict[str, object]:
    """Os `AccessRequirement` de `dependencies.py`, por nome do símbolo.

    Derivado do módulo, e não listado: um requisito novo entra na varredura sem
    que ninguém precise lembrar deste arquivo.
    """
    return {
        nome: valor
        for nome, valor in vars(dependencies_module).items()
        if isinstance(valor, dependencies_module.AccessRequirement)
    }


def _autorizacoes(handler: ast.FunctionDef) -> list[tuple[str, bool, int]]:
    """Cada `<guard>.authorize(...)` do handler: requisito nomeado, se passa unidade, linha.

    O requisito é lido do **segundo argumento posicional**, que por convenção do
    router é `<REQUISITO>.permission`. Uma chamada que passasse a permissão como
    string crua não seria classificável — e é justamente isso que o teste de
    totalidade abaixo reprova, em vez de deixá-la sair da varredura em silêncio.
    """
    encontradas: list[tuple[str, bool, int]] = []
    for no in ast.walk(handler):
        if not isinstance(no, ast.Call):
            continue
        if not (isinstance(no.func, ast.Attribute) and no.func.attr == "authorize"):
            continue
        permissao = no.args[1] if len(no.args) > 1 else None
        nome_do_requisito = (
            permissao.value.id
            if isinstance(permissao, ast.Attribute)
            and permissao.attr == "permission"
            and isinstance(permissao.value, ast.Name)
            else ""
        )
        nomeia_unidade = any(argumento.arg == "unit_id" for argumento in no.keywords)
        encontradas.append((nome_do_requisito, nomeia_unidade, no.lineno))
    return encontradas


def test_toda_autorizacao_do_router_nomeia_um_requisito_declarado() -> None:
    """A pré-condição da varredura seguinte, e uma lei por si.

    Sem ela, uma chamada `guard.authorize(actor, "manage_staff")` com a permissão
    como string crua sairia do domínio sem sintoma — a varredura de `names_unit`
    a ignoraria, e a lei ficaria verde sobre um conjunto menor. É a mesma
    disciplina que a totalidade de `_INVOCACOES` aplica às rotas.

    A cardinalidade é **19**: 17 rotas, mais a segunda chamada de R16 (a cópia
    autoriza **dois alvos**, L-AG4) e a segunda de R17 (o login autoriza **duas
    permissões** sobre o mesmo alvo, concept 3.5 §5.3). Travar o número em 17
    esconderia exatamente as chamadas que o ADR 3.4.0007 e o §5.3 existem para
    exigir.
    """
    declarados = set(_requisitos_declarados())
    chamadas = [
        (handler.name, nome, linha)
        for handler in _handlers_do_router()
        for nome, _, linha in _autorizacoes(handler)
    ]

    assert declarados, "nenhum AccessRequirement em dependencies.py — a varredura não mede nada"
    assert len(chamadas) == _TOTAL_DE_AUTORIZACOES, chamadas
    fora = [caso for caso in chamadas if caso[1] not in declarados]
    assert fora == [], f"autorização que não nomeia um AccessRequirement declarado: {fora}"


def test_o_names_unit_declarado_decide_se_a_rota_nomeia_unidade_ao_guard() -> None:
    """A declaração e a chamada têm de concordar, nos **dois** sentidos.

    `names_unit=True` obriga a passar `unit_id=`; `names_unit=False` proíbe. Os
    dois sentidos importam por razões diferentes: esquecer o `unit_id=` numa rota
    de funcionário autorizaria contra o tenant inteiro; passá-lo numa rota de
    catálogo pediria escopo sobre um recurso que não é da unidade, e o passo 4 do
    guard dispensa a unidade **por permissão** (ADR 3.4.0008).

    É esta asserção que faz `names_unit` deixar de ser campo decorativo: ele passa
    a ter um leitor, e leitor é o que separa declaração de comentário.
    """
    requisitos = _requisitos_declarados()
    divergencias = [
        f"{handler.name}:{linha} declara names_unit="
        f"{requisitos[nome].names_unit} e {'passa' if nomeia else 'não passa'} unit_id"
        for handler in _handlers_do_router()
        for nome, nomeia, linha in _autorizacoes(handler)
        if nome in requisitos and requisitos[nome].names_unit != nomeia
    ]

    assert divergencias == [], divergencias


def test_os_dois_valores_de_names_unit_sao_exercitados_pelo_router() -> None:
    """A guarda contra a lei colapsada num lado só.

    Se todas as 17 autorizações fossem `names_unit=True`, a asserção acima
    estaria provando metade da regra e ninguém veria — é a forma "lei universal,
    representante estreito" aplicada ao próprio instrumento. As duas espécies têm
    de aparecer, e cada requisito declarado tem de ser usado por alguma rota:
    requisito declarado e nunca chamado é a mesma dívida que `names_unit`
    declarado e nunca lido.
    """
    requisitos = _requisitos_declarados()
    usados = {
        nome
        for handler in _handlers_do_router()
        for nome, _, _ in _autorizacoes(handler)
        if nome in requisitos
    }

    assert usados == set(requisitos), (
        f"requisito declarado e nunca chamado: {set(requisitos) - usados}"
    )
    assert {requisitos[nome].names_unit for nome in usados} == {True, False}


def test_a_varredura_de_names_unit_reprova_os_dois_casos_plantados() -> None:
    """Guarda que nunca viu um positivo não é guarda — e aqui os positivos são dois.

    Um handler que declara o requisito tenant-wide e **passa** unidade, e outro
    que declara o unit-scoped e **não passa**: os dois têm de ser vistos pela
    extração, com o sentido certo. Sem este teste, um `_autorizacoes` que
    devolvesse sempre `nomeia_unidade=True` deixaria metade da lei acima verde por
    construção.
    """
    fonte = ast.parse(
        "def catalogo(actor, guard):\n"
        "    scope = guard.authorize(actor, MANAGE_JOB_FUNCTIONS_ACCESS.permission, unit_id=u)\n"
        "def funcionario(actor, guard):\n"
        "    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission)\n"
    )
    handlers = [no for no in ast.walk(fonte) if isinstance(no, ast.FunctionDef)]
    requisitos = _requisitos_declarados()

    extraidas = [
        (nome, nomeia) for handler in handlers for nome, nomeia, _ in _autorizacoes(handler)
    ]

    assert extraidas == [
        ("MANAGE_JOB_FUNCTIONS_ACCESS", True),
        ("MANAGE_STAFF_IN_UNIT_ACCESS", False),
    ]
    assert all(requisitos[nome].names_unit != nomeia for nome, nomeia in extraidas)


def test_ca23_nenhum_modulo_do_adapter_constroi_day_period_diretamente() -> None:
    """`DayPeriod(...)` levanta `ValueError`, que vira 500; `from_string` vira 422.

    A varredura é sobre o **pacote**, não sobre o router: o conversor errado é
    igualmente fatal em `schemas.py`, e o domínio cresce sozinho com os módulos.
    """
    culpados: list[str] = []
    for arquivo in _modulos_do_pacote_http():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        culpados += [
            f"{arquivo.name}:{no.lineno}"
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Name)
            and no.func.id == "DayPeriod"
        ]

    assert culpados == [], f"construção direta de DayPeriod (use from_string): {culpados}"


def _modulos_do_pacote_http() -> list[pathlib.Path]:
    pacote = importlib.import_module(_PACOTE_HTTP_STAFF)
    raiz = pathlib.Path(next(iter(pacote.__path__)))
    encontrados = sorted(raiz.glob("*.py"))
    assert encontrados, "a varredura precisa de módulos para ter o que negar"
    return encontrados


def test_ca05_nenhum_modulo_do_adapter_importa_entidade_de_dominio() -> None:
    """A varredura da Task 02, agora alcançando `router.py` por já estar no pacote.

    É o mesmo teste, sobre o mesmo domínio derivado — e é a prova de que "derivar
    do pacote" funciona: ninguém acrescentou `router.py` a lista nenhuma.
    """
    culpados: list[str] = []
    for arquivo in _modulos_do_pacote_http():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and "staff.domain.entities" in (no.module or ""):
                culpados.append(f"{arquivo.name}:{no.lineno}")

    assert culpados == [], f"import de entidade de domínio no adapter: {culpados}"


def test_ca05_a_varredura_de_import_ja_alcanca_o_router() -> None:
    """Fecha a ponta que faria o teste acima passar sobre um universo menor."""
    assert "router" in {arquivo.stem for arquivo in _modulos_do_pacote_http()}


# ---------------------------------------------------------------------------
# CA20 e CA21 — identificador inválido, por eixo
# ---------------------------------------------------------------------------


def _params_de_query(rota: APIRoute) -> list[str]:
    """Os parâmetros de query da rota — derivados do `dependant` do FastAPI.

    Derivar do `dependant`, e não da assinatura crua, é o que separa parâmetro de
    query de dependência resolvida por `Depends`: as duas aparecem lado a lado na
    assinatura do handler e só o framework sabe distingui-las.
    """
    return [parametro.name for parametro in rota.dependant.query_params]


def _params_de_query_de_id(rota: APIRoute) -> list[str]:
    """Os parâmetros de query que são **identificador** (`*_id` / `*_ids`).

    Hoje **nenhum** — `include_inactive` é booleano e `start`/`end` são
    instantes. O eixo de query de CA20 é portanto vazio, e a ausência é
    **declarada** e travada por `test_o_eixo_de_query_de_ca20_esta_vazio_...`,
    em vez de descoberta: o dia em que um identificador chegar por query, aquele
    teste fica vermelho e obriga a estender a varredura.
    """
    return [nome for nome in _params_de_query(rota) if nome.endswith(("_id", "_ids"))]


def _params_de_path_de_id(rota: APIRoute) -> list[str]:
    """Parâmetros de path que são identificador — derivado do template da rota."""
    return [
        segmento[1:-1]
        for segmento in rota.path.split("/")
        if segmento.startswith("{") and segmento.endswith("}") and segmento[1:-1].endswith("_id")
    ]


_CASOS_DE_PATH = [
    pytest.param(
        chave(rota),
        parametro,
        valor,
        id=f"{sorted(rota.methods)[0]}{rota.path}-{parametro}-{indice}",
    )
    for rota in _rotas()
    for parametro in _params_de_path_de_id(rota)
    for indice, valor in enumerate(_IDENTIFICADORES_INVALIDOS_EM_PATH)
]


@pytest.mark.parametrize(("chave_da_rota", "parametro", "valor"), _CASOS_DE_PATH)
async def test_ca20_identificador_invalido_em_path_recebe_422_de_staff(
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    parametro: str,
    valor: str,
) -> None:
    """RID x {só-whitespace, NUL}, com corpo e query **válidos**.

    A invocação vem do `_INVOCACOES` de propósito: sem corpo válido, uma rota com
    corpo obrigatório responderia 422 pelo `RequestValidationError` e este teste
    ficaria verde com o validador ausente. O discriminador `staff_error` é a
    segunda defesa, para o caso de o 422 do framework aparecer mesmo assim.
    """
    resposta = await _invocar(client, chave_da_rota, path={parametro: valor})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == _CORPO_DE_STAFF


def _campos_de_id_do_corpo(chave_da_rota: ChaveDeRota) -> list[IdentifierField]:
    """Campos de identificador do schema de corpo da rota, por introspecção."""
    invocacao = _INVOCACOES[chave_da_rota]
    if invocacao.body is None:
        return []
    modelo = _schema_do_corpo(chave_da_rota)
    if modelo is None:
        return []
    return [
        campo
        for campo in dependencies_module.identifier_fields(modelo)
        if campo.name in invocacao.body
    ]


def _schema_do_corpo(chave_da_rota: ChaveDeRota) -> type[BaseModel] | None:
    """O `*Request` que a rota recebe no corpo, derivado da assinatura do handler.

    **A anotação `return` é excluída, e a exclusão é carga.** O `response_model`
    de toda rota de escrita também é um `BaseModel` — `EmployeeResponse` tem um
    campo `name` —, então varrer `__annotations__` inteiro faz uma rota **sem
    corpo** (`termination`, `rehire`, `DELETE .../unavailabilities`) devolver o
    modelo de **resposta** como se fosse o de requisição. Hoje os dois chamadores
    daqui já filtram por `invocacao.body is None` e o defeito não se realiza — mas
    "inofensivo por acidente do chamador" é o estado em que um helper espera pelo
    terceiro chamador. `test_o_schema_do_corpo_ignora_a_anotacao_de_retorno`
    trava a exclusão diretamente, sem depender daquele filtro.
    """
    rota = next(r for r in _rotas() if chave(r) == chave_da_rota)
    for nome, anotacao in getattr(rota.endpoint, "__annotations__", {}).items():
        if nome == "return":
            continue
        if isinstance(anotacao, type) and issubclass(anotacao, BaseModel):
            return anotacao
    return None


def test_o_schema_do_corpo_ignora_a_anotacao_de_retorno() -> None:
    """Rota sem corpo não tem schema de corpo — nem o de resposta, por engano.

    A asserção é sobre a **equivalência** entre "a invocação declara corpo" e "o
    helper acha schema de corpo": as duas fontes são independentes (`_INVOCACOES`
    é declarado à mão pelas Tasks de rota; o helper deriva das anotações do
    handler), e é a discordância entre elas que denuncia a varredura errada.

    A contagem de rotas sem corpo é asserida junto porque uma equivalência sobre
    conjunto vazio é verdadeira: se toda rota passasse a ter corpo, este teste
    ficaria verde sem medir nada.
    """
    sem_corpo = [chave for chave in _INVOCACOES if _INVOCACOES[chave].body is None]

    assert sem_corpo, "nenhuma rota sem corpo — a guarda não mede nada"
    for chave_da_rota in sem_corpo:
        assert _schema_do_corpo(chave_da_rota) is None, (
            f"{chave_da_rota} não tem corpo, mas o helper devolveu "
            f"{_schema_do_corpo(chave_da_rota)} — provavelmente o `response_model`"
        )
    for chave_da_rota in set(_INVOCACOES) - set(sem_corpo):
        assert _schema_do_corpo(chave_da_rota) is not None, (
            f"{chave_da_rota} declara corpo, mas o helper não achou o schema"
        )


_CASOS_DE_CORPO = [
    pytest.param(
        chave_da_rota,
        campo,
        valor,
        id=f"{chave_da_rota[0]}{chave_da_rota[1]}-{campo.name}-{indice}",
    )
    for chave_da_rota in sorted(_INVOCACOES)
    for campo in _campos_de_id_do_corpo(chave_da_rota)
    for indice, valor in enumerate(_IDENTIFICADORES_INVALIDOS)
]


@pytest.mark.parametrize(("chave_da_rota", "campo", "valor"), _CASOS_DE_CORPO)
async def test_ca20_identificador_invalido_no_corpo_recebe_422_de_staff(
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    campo: IdentifierField,
    valor: str,
) -> None:
    """Os três valores, sobre os campos de id **derivados por introspecção**.

    Numa coleção o que se corrompe é um **elemento**, e não o campo: trocar a
    lista inteira por uma string produziria erro de **forma** — o 422 do
    framework — e a varredura mediria outra coisa.
    """
    invocacao = _INVOCACOES[chave_da_rota]
    assert invocacao.body is not None
    corpo = dict(invocacao.body)
    corpo[campo.name] = [valor] if campo.is_collection else valor

    resposta = await _invocar(client, chave_da_rota, body=corpo)

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == _CORPO_DE_STAFF


def test_o_eixo_de_corpo_de_ca20_nao_esta_vazio() -> None:
    """O eixo tem de ter casos, e a exigência é **incondicional**.

    A primeira versão deste teste comparava `bool(_CASOS_DE_CORPO)` com
    `bool(rotas_com_corpo_de_id)` — e os dois lados derivavam do **mesmo**
    helper, então esvaziar o helper deixava os dois falsos e o teste passava.
    Guarda que concorda consigo mesma não é guarda. Com R05 declarando
    `job_function_ids`, o eixo é não-vazio e a exigência pode ser direta.
    """
    campos_existentes = {
        campo.name
        for modelo in _requests_do_modulo()
        for campo in dependencies_module.identifier_fields(modelo)
    }

    assert campos_existentes == {"target_unit_id", "job_function_ids"}
    assert _CASOS_DE_CORPO, "o eixo de corpo de CA20 ficou vazio — a varredura não mede nada"


def _requests_do_modulo() -> list[type[BaseModel]]:
    return [
        objeto
        for nome, objeto in vars(schemas_module).items()
        if nome.endswith("Request") and isinstance(objeto, type) and issubclass(objeto, BaseModel)
    ]


@pytest.mark.parametrize(("chave_da_rota", "parametro", "valor"), _CASOS_DE_PATH)
async def test_ca21_a_validacao_roda_antes_de_autorizar(
    client: AsyncClient,
    ambiente: Ambiente,
    chave_da_rota: ChaveDeRota,
    parametro: str,
    valor: str,
) -> None:
    """A prova é a **ausência de chamada**, não o status.

    Um 422 na resposta é compatível tanto com "validou antes" quanto com "o guard
    rodou, passou, e a validação veio depois" — e é o segundo caso que a regra
    protege, porque é ele que deixa um valor cru alcançar `units.find_by_id`
    dentro de identity.

    A asserção é sobre `authorize`, **não** sobre `calls == []`: o fake registra
    também `authenticate`, que §5.1 exige que rode **primeiro**. Exigir a lista
    vazia obrigaria a validar antes de autenticar, e aí uma requisição sem Bearer
    com id inválido receberia 422 em vez de 401 — a sondagem que §5.1 impede.
    """
    ambiente.guard.calls.clear()

    await _invocar(client, chave_da_rota, path={parametro: valor})

    autorizacoes = [c for c in ambiente.guard.calls if c.startswith("authorize(")]
    assert autorizacoes == [], f"o guard foi consultado antes da validação: {ambiente.guard.calls}"
    assert "authenticate" in ambiente.guard.calls, "a autenticação tem de ter rodado antes"


@pytest.mark.parametrize(("chave_da_rota", "campo", "valor"), _CASOS_DE_CORPO)
async def test_ca21_a_validacao_do_corpo_tambem_roda_antes_de_autorizar(
    client: AsyncClient,
    ambiente: Ambiente,
    chave_da_rota: ChaveDeRota,
    campo: IdentifierField,
    valor: str,
) -> None:
    """A **mesma** lei, no eixo que faltava — e a falta era uma fresta medida.

    O ADR 3.6.0002 §3 enuncia a ordem para *"path, query string, or body"*, e até
    aqui só o eixo de path a travava: mover a validação dos ids do corpo para
    **depois** de `guard.authorize` deixava a suíte inteira verde. E o corpo é
    justamente onde o valor cru chega mais longe — cada elemento de
    `job_function_ids` vai para `find_all_by_ids` **antes** da construção da
    entidade, e `target_unit_id` vai para `units.find_by_id` **dentro de
    identity**, que é onde o NUL vira 500.

    A asserção é a mesma de sempre: **ausência** de `authorize(`, nunca status.
    """
    invocacao = _INVOCACOES[chave_da_rota]
    assert invocacao.body is not None
    corpo = dict(invocacao.body)
    corpo[campo.name] = [valor] if campo.is_collection else valor

    ambiente.guard.calls.clear()
    await _invocar(client, chave_da_rota, body=corpo)

    autorizacoes = [c for c in ambiente.guard.calls if c.startswith("authorize(")]
    assert autorizacoes == [], (
        f"o guard foi consultado antes de validar {campo.name}: {ambiente.guard.calls}"
    )
    assert "authenticate" in ambiente.guard.calls, "a autenticação tem de ter rodado antes"


# ---------------------------------------------------------------------------
# CA24 — nenhum campo escalar devolve 500
# ---------------------------------------------------------------------------


def _modelos_em(anotacao: object) -> list[type[BaseModel]]:
    """Os `BaseModel` alcançáveis de uma anotação, inclusive sob união e `Annotated`."""
    if isinstance(anotacao, type) and issubclass(anotacao, BaseModel):
        return [anotacao]
    encontrados: list[type[BaseModel]] = []
    for argumento in getattr(anotacao, "__args__", ()):
        encontrados.extend(_modelos_em(argumento))
    for metadado in getattr(anotacao, "__metadata__", ()):
        encontrados.extend(_modelos_em(metadado))
    return encontrados


def _elemento_de(anotacao: object) -> object:
    """O tipo do **elemento** de uma anotação de lista, inclusive sob `| None`.

    `shift_preference` é `list[str] | None`: sem descer pela união, o elemento
    ficaria sem anotação e `_quem_parseia` o classificaria como do framework —
    o oposto do que acontece, já que a lista chega intacta ao router e é
    `DayPeriod.from_string` quem recusa.
    """
    if get_origin(anotacao) is list:
        argumentos = get_args(anotacao)
        return argumentos[0] if argumentos else None
    for argumento in get_args(anotacao):
        if (encontrado := _elemento_de(argumento)) is not None:
            return encontrado
    return None


def _descendo(anotacao: object, resto: Caminho) -> object:
    """A anotação alcançada por um resto de caminho — índice desce por lista."""
    if not resto:
        return anotacao
    if isinstance(resto[0], int):
        return _descendo(_elemento_de(anotacao), resto[1:])
    for aninhado in _modelos_em(anotacao):
        if resto[0] in aninhado.model_fields:
            return _anotacao_no_caminho(aninhado, resto)
    return None


def _anotacao_no_caminho(modelo: type[BaseModel], caminho: Caminho) -> object:
    """A anotação declarada para um caminho, descendo por aninhados e por listas."""
    nome, resto = caminho[0], caminho[1:]
    assert isinstance(nome, str), "o primeiro passo de um caminho é sempre um campo"
    campo = modelo.model_fields.get(nome)
    if campo is None:
        return None
    return _descendo(campo.annotation, resto)


def _escalares(valor: object, prefixo: Caminho = ()) -> list[Caminho]:
    """Caminhos até os valores **string** do corpo, descendo por aninhados e listas.

    Descer por **dicionário** é exigência antiga do critério: o concept nomeia
    `weekly_hours` entre os campos que CA24 tem de varrer — *"por onde escapou o
    500 do `decimal.InvalidOperation`"* —, e ele vive dentro da união de perfil
    de jornada.

    Descer por **lista** é a correção de um domínio que excluía elementos
    justamente onde o critério os nomeia. CA24 diz, na letra, *"todos os campos
    escalares de todos os `*Request` … o que inclui `weekly_hours` … e os
    períodos de `shift_preference`"* — e a versão anterior devolvia `[]` para
    `list`, deixando de fora os períodos de `shift_preference` e os elementos de
    `job_function_ids`. A assimetria que denunciava o buraco: um dos dois campos
    que o mesmo parágrafo nomeia tinha guarda dedicada, e o outro não tinha
    nenhuma.

    O passo por lista é o **índice**, e não o nome do campo: é o que permite
    corromper um elemento mantendo a forma da lista — corromper o campo inteiro
    produziria um `RequestValidationError` do framework em vez do erro que se
    quer medir. É a mesma distinção que `IdentifierField.is_collection` já
    carrega para o eixo de identificadores.
    """
    if isinstance(valor, str):
        return [prefixo]
    if isinstance(valor, dict):
        return [
            caminho
            for chave_do_campo, aninhado in valor.items()
            for caminho in _escalares(aninhado, (*prefixo, str(chave_do_campo)))
        ]
    if isinstance(valor, list):
        return [
            caminho
            for indice, item in enumerate(valor)
            for caminho in _escalares(item, (*prefixo, indice))
        ]
    return []


def _campos_escalares_do_corpo(chave_da_rota: ChaveDeRota) -> list[Caminho]:
    """Caminhos escalares do corpo da invocação, derivados do corpo declarado."""
    invocacao = _INVOCACOES[chave_da_rota]
    if invocacao.body is None:
        return []
    return _escalares(invocacao.body)


def _nome_do_campo(caminho: Caminho) -> str:
    """O último passo **nomeado** do caminho — o campo a que o valor pertence.

    Um caminho que termina em índice (`job_function_ids.0`) continua sendo do
    campo `job_function_ids`: é o nome que decide a espécie em
    `_e_alvo_de_autorizacao`, e usar o índice ali seria erro de tipo silencioso.
    """
    return next(passo for passo in reversed(caminho) if isinstance(passo, str))


def _e_alvo_de_autorizacao(nome: str) -> bool:
    """Se um identificador nomeia uma **unidade** — e por isso é alvo de acesso.

    Neste bounded context o alvo de autorização, além do tenant, é sempre uma
    **unidade** (ADR 3.4.0007, ADR 3.4.0008). Por isso a espécie não depende de
    **onde** o identificador chega: `unit_id` no path e `target_unit_id` no corpo
    de R16 são os dois um alvo, e um valor bem-formado que o ator não tem
    concedido é negado pelo **guard** nos dois casos — não pelo validador, que
    não tem por que recusar um identificador válido.

    A regra está travada por `test_os_alvos_de_autorizacao_sao_exatamente_os_de_hoje`:
    um identificador de unidade novo, com outro nome, fica vermelho lá em vez de
    entrar mudo na espécie errada.
    """
    return nome.endswith("unit_id")


def _quem_parseia(chave_da_rota: ChaveDeRota, caminho: Caminho) -> str:
    """Quem recusa um valor degenerado neste campo: `"staff"` ou `"framework"`.

    **A distinção é de responsabilidade, e ignorá-la faria o teste medir a peça
    errada** — é a mesma correção que o eixo de path já carrega para `unit_id`.
    Um campo declarado `str` no schema chega **intacto** ao router, e é staff quem
    o converte e recusa: ali o 422 tem de trazer o corpo de staff. Um campo
    declarado `datetime` (ou `bool`) é parseado pelo **framework** antes de o
    handler rodar, e lixo nele é erro de **forma** — `validation_error` é a
    resposta correta, e exigir corpo de staff seria exigir que staff assumisse
    uma recusa que não é dele.

    O caso em que staff **é** responsável por um `datetime` — o valor bem-formado
    com `Z`, que `UnavailabilityPeriod` recusa — é coberto por teste dedicado em
    `test_http_router_employee_profile.py`, com a exigência do corpo de staff.
    """
    modelo = _schema_do_corpo(chave_da_rota)
    if modelo is None:
        return "framework"
    anotacao = _anotacao_no_caminho(modelo, caminho)
    return "staff" if anotacao is str else "framework"


_CASOS_ADVERSARIAIS = [
    pytest.param(
        chave_da_rota,
        caminho,
        valor,
        id=(
            f"{chave_da_rota[0]}{chave_da_rota[1]}-"
            f"{'.'.join(str(passo) for passo in caminho)}-{indice}"
        ),
    )
    for chave_da_rota in sorted(_INVOCACOES)
    for caminho in _campos_escalares_do_corpo(chave_da_rota)
    for indice, valor in enumerate(_VALORES_ADVERSARIAIS)
]


def _substituindo(alvo: object, caminho: Caminho, valor: str) -> object:
    """Copia `alvo` trocando **só** o que o caminho endereça — dicionário ou lista."""
    passo, resto = caminho[0], caminho[1:]
    if isinstance(passo, int):
        assert isinstance(alvo, list), f"índice {passo} sobre {type(alvo).__name__}"
        copia = list(alvo)
        copia[passo] = valor if not resto else _substituindo(alvo[passo], resto, valor)
        return copia
    assert isinstance(alvo, dict), f"campo {passo!r} sobre {type(alvo).__name__}"
    return {**alvo, passo: valor if not resto else _substituindo(alvo[passo], resto, valor)}


def _com_valor_em(corpo: dict[str, Any], caminho: Caminho, valor: str) -> dict[str, Any]:
    """Copia o corpo trocando **só** o campo do caminho — o resto fica válido."""
    resultado = _substituindo(corpo, caminho, valor)
    assert isinstance(resultado, dict)
    return resultado


@pytest.mark.parametrize(("chave_da_rota", "caminho", "valor"), _CASOS_ADVERSARIAIS)
async def test_ca24_nenhum_campo_escalar_devolve_500(
    client: AsyncClient,
    ambiente: Ambiente,
    chave_da_rota: ChaveDeRota,
    caminho: Caminho,
    valor: str,
) -> None:
    """Aceitar ou recusar são as duas respostas legítimas; quebrar não é.

    E onde o valor é recusado, a asserção sobre a **origem** do 422 se aplica ao
    que **staff** parseia — ver `_quem_parseia`. Num campo que o framework parseia
    (`datetime`, `bool`), o `validation_error` é a resposta correta, e exigir
    corpo de staff mediria a peça errada.
    """
    invocacao = _INVOCACOES[chave_da_rota]
    assert invocacao.body is not None
    corpo = _com_valor_em(dict(invocacao.body), caminho, valor)

    # Mesma espécie do eixo de path: um identificador de **unidade** que chega
    # pelo corpo (o `target_unit_id` de R16) é o segundo alvo de autorização, e
    # um valor bem-formado não concedido é negado pelo guard, cru.
    e_alvo = _e_alvo_de_autorizacao(_nome_do_campo(caminho))
    deve_escapar = (
        e_alvo
        and valor not in _ADVERSARIAIS_RECUSADOS_PELO_VALIDADOR
        and valor not in _unidades_concedidas(ambiente)
    )
    try:
        resposta = await _invocar(client, chave_da_rota, body=corpo)
    except FakeAuthorizationRejected as exc:
        # **O ramo é da espécie, não da rota.** A primeira versão capturava a
        # sentinela para qualquer campo, e com isso um `authorize` disparado a
        # partir de um campo que **não** é alvo — `name`, texto livre do cliente
        # — passava em silêncio, quando é justamente o defeito a acusar.
        assert e_alvo, (
            f"{chave_da_rota[1]}: a sentinela do guard escapou de "
            f"{'.'.join(str(passo) for passo in caminho)}, "
            "que não é identificador de unidade — a rota autorizou contra um campo arbitrário"
        )
        assert exc is ambiente.guard.authorization_error, (
            f"{chave_da_rota[1]}: a recusa do guard foi traduzida em outra exceção (L-AG2)"
        )
        return

    if deve_escapar:
        pytest.fail(
            f"{chave_da_rota[1]}: destino não concedido {valor!r} devolveu "
            f"{resposta.status_code} em vez de deixar a sentinela do guard subir crua."
        )

    assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
    if (
        resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        and _quem_parseia(chave_da_rota, caminho) == "staff"
    ):
        assert resposta.json()["type"] == _CORPO_DE_STAFF


def test_os_alvos_de_autorizacao_sao_exatamente_os_de_hoje() -> None:
    """Declara quais identificadores são alvo de acesso, para que a lista não cresça muda.

    `_e_alvo_de_autorizacao` decide qual asserção CA24 aplica; se um identificador
    de unidade novo chegasse com outro nome, ele cairia na espécie errada em
    silêncio — e a varredura mediria o validador onde deveria medir o guard.
    """
    de_path = {parametro for rota in _rotas() for parametro in _params_de_path_de_id(rota)}
    de_corpo = {
        campo.name
        for modelo in _requests_do_modulo()
        for campo in dependencies_module.identifier_fields(modelo)
    }
    alvos = {nome for nome in de_path | de_corpo if _e_alvo_de_autorizacao(nome)}

    assert alvos == {"unit_id", "target_unit_id"}


def test_a_varredura_de_ca24_alcanca_os_dois_campos_que_o_criterio_nomeia() -> None:
    """`weekly_hours` **e** os períodos de `shift_preference` — o parágrafo nomeia os dois.

    O primeiro é aninhado dentro da união de perfil de jornada; os segundos são
    **elementos de lista**, e ficavam de fora porque `_escalares` devolvia `[]`
    para `list`. A assimetria que denunciava o buraco: um dos dois campos que o
    critério nomeia tinha guarda dedicada, e o outro não tinha nenhuma.

    A contagem entra junto porque é ela que prova que o domínio **cresceu**: dez
    pares (rota, caminho) antes de descer por lista, treze depois — um elemento de
    `job_function_ids` em cada uma das duas rotas que o aceitam, e o período de
    `shift_preference`.
    """
    casos = [
        (chave_da_rota, caminho)
        for chave_da_rota in _INVOCACOES
        for caminho in _campos_escalares_do_corpo(chave_da_rota)
    ]
    caminhos = {caminho for _, caminho in casos}

    assert ("workload_profile", "weekly_hours") in caminhos
    assert ("name",) in caminhos
    assert ("shift_preference", 0) in caminhos
    assert ("job_function_ids", 0) in caminhos
    assert len(casos) == _TOTAL_DE_CAMPOS_ESCALARES, sorted(casos, key=str)


def test_os_elementos_de_lista_sao_do_lado_de_staff_no_dominio_de_ca24() -> None:
    """Elemento de lista é `str` no schema, e por isso a recusa dele é de **staff**.

    É a metade que faz a extensão valer alguma coisa. Se `_elemento_de` não
    descesse pela união de `list[str] | None`, o período de `shift_preference`
    entraria no domínio classificado como "framework", e a exigência do corpo de
    staff — a defesa contra o 422 que não é desta borda — ficaria desligada
    justamente nos caminhos recém-abertos.

    A segunda asserção fecha o outro lado: nenhum elemento de lista é **alvo de
    autorização**, então nenhum deles pode cair no ramo da sentinela do guard.
    Hoje isso é verdade porque o único identificador de unidade que chega pelo
    corpo é escalar (`target_unit_id`); no dia em que uma lista de unidades
    existir, este teste é quem obriga a revisitar a espécie.
    """
    novos = [
        (chave_da_rota, caminho)
        for chave_da_rota in _INVOCACOES
        for caminho in _campos_escalares_do_corpo(chave_da_rota)
        if any(isinstance(passo, int) for passo in caminho)
    ]

    assert novos, "nenhum elemento de lista no domínio — a descida por lista sumiu"
    assert {_quem_parseia(chave_da_rota, caminho) for chave_da_rota, caminho in novos} == {"staff"}
    assert not any(_e_alvo_de_autorizacao(_nome_do_campo(caminho)) for _, caminho in novos)


def test_a_classificacao_de_quem_parseia_nao_colapsou_para_um_lado_so() -> None:
    """Guarda da distinção: se tudo virasse "framework", a exigência sumiria.

    `_quem_parseia` decide se o 422 precisa trazer o corpo de staff. Um bug que a
    fizesse devolver sempre `"framework"` desligaria essa metade de CA24 em
    silêncio, e nenhum caso ficaria vermelho. As duas espécies têm de existir.
    """
    especies = {
        _quem_parseia(chave_da_rota, caminho)
        for chave_da_rota in _INVOCACOES
        for caminho in _campos_escalares_do_corpo(chave_da_rota)
    }

    assert especies == {"staff", "framework"}


@pytest.mark.parametrize("valor", _VALORES_ADVERSARIAIS)
async def test_ca24_nenhum_identificador_de_path_adversarial_devolve_500(
    client: AsyncClient, ambiente: Ambiente, valor: str
) -> None:
    """O mesmo conjunto no eixo de path, onde o NUL produzia 500 dentro de identity.

    **Há dois desfechos legítimos, e reconhecer o segundo é correção de erro de
    categoria, não afrouxamento.** Os parâmetros de path deste inventário são de
    duas espécies:

    - `job_function_id` e `employee_id` — o valor entra num command e a resposta
      é HTTP; aqui a asserção é sobre o **status**;
    - `unit_id` — o valor é o **alvo de autorização**. Um valor bem-formado que
      o ator não tem concedido passa pelo validador de identificador (ele é
      bem-formado: a peça que recusaria é outra) e é negado pelo **guard**.
      Exigir 422 aí mediria a peça errada — o validador não tem por que recusar
      um identificador válido, e quem nega é a autorização.

    Nesse segundo caso o `InMemoryAccessGuard` levanta a **sua própria
    sentinela**, que não é `StaffError` nem `IdentityError` e não tem handler
    nesta app mínima. Em produção quem responde é o handler de identity, com 403
    de corpo constante — a mesma razão pela qual CA08/CA09 vivem no e2e, já
    declarada no plano.

    **O que cada asserção mede — enunciado com honestidade, porque a primeira
    redação deste docstring exagerava e foi refutada por medição.** A asserção
    antiga (status < 500 para todos os parâmetros) era **insatisfazível** na
    espécie `unit_id`: contra um router **correto** a sentinela escapa, não há
    resposta nenhuma, e onze casos ficavam vermelhos sem defeito algum. A nova
    exige que a sentinela **tenha escapado** e que seja **o mesmo objeto**, o que
    pega as duas traduções que L-AG2 proíbe:

    - **tradução em exceção** — capturar e relançar um erro novo do mesmo tipo:
      morre na asserção de identidade;
    - **tradução em resposta** — capturar e devolver `HTTPException(403)`: morre
      no `pytest.fail` abaixo. *(Era esta que sobrevivia antes de o ramo existir:
      sem exceção, o teste caía no ramo de status, e `403 < 500` aceitava
      exatamente a tradução que o parágrafo acima diz proibir.)*

    O que **nenhuma** das duas mede é a **forma HTTP** da recusa em produção — o
    403 de corpo constante do handler de identity. Isso é CA09/CA11, na Task 11,
    com a app real montada. Aqui a app mínima não tem esse handler, e dizer o
    contrário seria prometer o que este ambiente não entrega.
    """
    for rota in _rotas():
        for parametro in _params_de_path_de_id(rota):
            # A espécie do parâmetro decide qual asserção se aplica. `unit_id` é
            # o **alvo de autorização**: um valor bem-formado que o ator não tem
            # concedido passa pelo validador — ele é bem-formado — e é negado
            # pelo **guard**, cru. Os demais entram num command, e a recusa, se
            # houver, é HTTP.
            deve_escapar = (
                parametro == "unit_id"
                and valor not in _ADVERSARIAIS_RECUSADOS_PELO_VALIDADOR
                and valor not in _unidades_concedidas(ambiente)
            )
            try:
                resposta = await _invocar(client, chave(rota), path={parametro: valor})
            except FakeAuthorizationRejected as exc:
                assert exc is ambiente.guard.authorization_error, (
                    f"{rota.path}: a recusa do guard foi traduzida em outra exceção (L-AG2)"
                )
                continue

            if deve_escapar:
                pytest.fail(
                    f"{rota.path}: unidade não concedida {valor!r} devolveu "
                    f"{resposta.status_code} em vez de deixar a sentinela do guard subir crua. "
                    "Traduzir a recusa em resposta é a metade de L-AG2 que o status não pega."
                )
            assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (
                f"{rota.path} devolveu {resposta.status_code} para {valor!r}"
            )


def _unidades_concedidas(ambiente: Ambiente) -> set[str]:
    """As unidades que o guard do ambiente concede — derivado, não transcrito."""
    return {unidade for _, _, unidade in ambiente.guard.grants if unidade is not None}


def test_a_transcricao_do_que_o_validador_recusa_bate_com_o_validador() -> None:
    """Cruza a transcrição do ADR 3.6.0002 §2 com o validador real.

    A classificação acima decide **qual** asserção CA24 aplica a cada valor, e por
    isso não pode ser perguntada ao código sob teste — a expectativa seguiria o
    defeito. Transcrever exige este cruzamento: se o validador mudar de opinião
    sobre algum valor do conjunto adversarial, é aqui que fica vermelho, e não
    numa célula de CA24 medindo silenciosamente a peça errada.
    """
    medido = set()
    for valor in _VALORES_ADVERSARIAIS:
        try:
            dependencies_module.validate_identifier(valor, entity="teste")
        except InvalidIdentifierError:
            medido.add(valor)

    assert medido == set(_ADVERSARIAIS_RECUSADOS_PELO_VALIDADOR)


_CASOS_DE_QUERY = [
    pytest.param(
        chave_da_rota,
        parametro,
        valor,
        id=f"{chave_da_rota[0]}{chave_da_rota[1]}-{parametro}-{indice}",
    )
    for rota in _rotas()
    for chave_da_rota in [chave(rota)]
    for parametro in _params_de_query(rota)
    for indice, valor in enumerate(_VALORES_ADVERSARIAIS)
]


@pytest.mark.parametrize(("chave_da_rota", "parametro", "valor"), _CASOS_DE_QUERY)
async def test_ca24_nenhum_parametro_de_query_devolve_500(
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    parametro: str,
    valor: str,
) -> None:
    """O terceiro eixo de CA24, que o critério nomeia e que faltava.

    O concept diz *"todos os campos escalares de todos os `*Request`, **mais os
    parâmetros de query**"*, e desde que R06 ganhou `include_inactive` e R12
    ganhou `start`/`end` o eixo existia sem ser varrido.

    **A asserção é só sobre o 500, e a assimetria com o eixo de corpo é
    deliberada.** Os parâmetros de query de hoje são `bool` e `datetime`: um
    valor degenerado neles é erro de **forma**, recusado pelo framework com
    `type: "validation_error"`, e isso é o comportamento correto. Exigir o corpo
    de staff aqui mediria a peça errada — pela mesma razão que CA24 no eixo de
    path distingue `unit_id` dos demais. O dia em que um **identificador** chegar
    por query, o teste abaixo obriga a estender a varredura com a exigência mais
    forte.
    """
    resposta = await _invocar(client, chave_da_rota, query={parametro: valor})

    assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (
        f"{chave_da_rota[1]}?{parametro}={valor!r} devolveu {resposta.status_code}"
    )


def test_o_eixo_de_query_de_ca20_esta_vazio_e_a_ausencia_e_declarada() -> None:
    """CA20 tem eixo de query, e hoje ele é **legitimamente** vazio.

    Nenhum parâmetro de query de staff é identificador: `include_inactive` é
    booleano, `start` e `end` são instantes. Declarar a ausência — em vez de
    deixá-la implícita — é o que faz este teste ficar **vermelho** no dia em que
    alguém acrescentar um `*_id` por query, obrigando a estender a varredura em
    vez de deixar o eixo passar mudo.

    A lição é a do guarda do eixo de corpo: ausência não declarada é
    indistinguível de varredura quebrada.
    """
    de_id = {
        (chave(rota), parametro) for rota in _rotas() for parametro in _params_de_query_de_id(rota)
    }
    existentes = {parametro for rota in _rotas() for parametro in _params_de_query(rota)}

    assert existentes == {"include_inactive", "start", "end"}
    assert de_id == set(), f"identificador chegando por query sem varredura: {sorted(de_id)}"


def test_o_dominio_adversarial_de_ca24_nao_esta_vazio() -> None:
    """Sem casos, o critério passaria por vacuidade — e passaria para sempre."""
    assert _CASOS_ADVERSARIAIS
    assert _CASOS_DE_PATH
    assert _CASOS_DE_QUERY


# ---------------------------------------------------------------------------
# CA13 (Stage 3.5) — toda resposta de funcionário carrega `user_id`
# ---------------------------------------------------------------------------

# Rotas cujo `response_model` **é** ou **embute** `EmployeeResponse`: as 11 de
# funcionário da 3.6 (uma delas como `list[...]`) mais R17, cujo
# `EmployeeLoginResponse` embrulha o registro. Transcrita, como as outras
# contagens: uma rota nova de funcionário que respondesse com outro schema
# reprovaria aqui até que alguém decidisse que ela não devolve o registro.
_TOTAL_DE_ROTAS_QUE_DEVOLVEM_FUNCIONARIO = 12


def _devolve_funcionario(modelo: object) -> bool:
    """Se a anotação de resposta é, contém ou embute `EmployeeResponse`."""
    schemas = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.schemas")
    if modelo is schemas.EmployeeResponse:
        return True
    if get_origin(modelo) is not None:
        return any(_devolve_funcionario(arg) for arg in get_args(modelo))
    if isinstance(modelo, type) and issubclass(modelo, BaseModel):
        return any(_devolve_funcionario(campo.annotation) for campo in modelo.model_fields.values())
    return False


def test_ca13_toda_resposta_de_funcionario_carrega_o_user_id() -> None:
    """Derivado de `router.routes`: o campo entra em toda rota que devolve o registro.

    A trava é sobre o **schema** (`EmployeeResponse.user_id`) e sobre a
    **cardinalidade** das rotas que o devolvem — inclusive por embrulho
    (`EmployeeLoginResponse.employee`). O e2e (Task 12) prova o valor no fio.
    """
    schemas = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.schemas")
    campo = schemas.EmployeeResponse.model_fields["user_id"]
    assert campo.annotation == str | None
    assert campo.is_required(), "user_id sem default: `from_result` sempre o preenche"

    rotas_de_funcionario = [rota for rota in _rotas() if _devolve_funcionario(rota.response_model)]
    assert len(rotas_de_funcionario) == _TOTAL_DE_ROTAS_QUE_DEVOLVEM_FUNCIONARIO, sorted(
        rota.path for rota in rotas_de_funcionario
    )
    assert any(rota.path.endswith("/login") for rota in rotas_de_funcionario)
    assert schemas.EmployeeLoginResponse.model_fields["employee"].annotation is (
        schemas.EmployeeResponse
    )

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
from typing import Any

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response
from pydantic import BaseModel

from tests.fakes.features.staff.in_memory_access_guard import FakeAuthorizationRejected
from tests.unit.features.staff.adapters.test_http_router_job_functions import Ambiente

pytestmark = pytest.mark.unit

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"
_PACOTE_TESTES_ADAPTER = "tests.unit.features.staff.adapters"

router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
dependencies_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.dependencies")
schemas_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.schemas")

_CORPO_DE_STAFF = "staff_error"

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
    """O `*Request` que a rota recebe no corpo, derivado da assinatura do handler."""
    rota = next(r for r in _rotas() if chave(r) == chave_da_rota)
    for anotacao in getattr(rota.endpoint, "__annotations__", {}).values():
        if isinstance(anotacao, type) and issubclass(anotacao, BaseModel):
            return anotacao
    return None


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


def test_o_eixo_de_corpo_de_ca20_nao_esta_vazio_por_engano() -> None:
    """Hoje é vazio — e a ausência tem de ser **declarada**, não descoberta.

    Nenhuma das quatro rotas de catálogo carrega identificador no corpo: os dois
    campos que carregam (`target_unit_id` e `job_function_ids`) pertencem a rotas
    de funcionário, que nascem nas Tasks 06 e 08. Este teste existe para que o
    dia em que elas nascerem e o eixo **continuar** vazio seja um dia em que
    algo fica vermelho.
    """
    campos_existentes = {
        campo.name
        for modelo in _requests_do_modulo()
        for campo in dependencies_module.identifier_fields(modelo)
    }
    rotas_com_corpo_de_id = {
        chave_da_rota for chave_da_rota in _INVOCACOES if _campos_de_id_do_corpo(chave_da_rota)
    }

    assert campos_existentes == {"target_unit_id", "job_function_ids"}
    assert bool(_CASOS_DE_CORPO) == bool(rotas_com_corpo_de_id)


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


# ---------------------------------------------------------------------------
# CA24 — nenhum campo escalar devolve 500
# ---------------------------------------------------------------------------


def _campos_escalares_do_corpo(chave_da_rota: ChaveDeRota) -> list[str]:
    """Campos de corpo de valor escalar, derivados de `model_fields`."""
    invocacao = _INVOCACOES[chave_da_rota]
    if invocacao.body is None:
        return []
    modelo = _schema_do_corpo(chave_da_rota)
    if modelo is None:
        return []
    return [
        nome
        for nome in modelo.model_fields
        if nome in invocacao.body and isinstance(invocacao.body[nome], str)
    ]


_CASOS_ADVERSARIAIS = [
    pytest.param(
        chave_da_rota, campo, valor, id=f"{chave_da_rota[0]}{chave_da_rota[1]}-{campo}-{indice}"
    )
    for chave_da_rota in sorted(_INVOCACOES)
    for campo in _campos_escalares_do_corpo(chave_da_rota)
    for indice, valor in enumerate(_VALORES_ADVERSARIAIS)
]


@pytest.mark.parametrize(("chave_da_rota", "campo", "valor"), _CASOS_ADVERSARIAIS)
async def test_ca24_nenhum_campo_escalar_devolve_500(
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    campo: str,
    valor: str,
) -> None:
    """Aceitar ou recusar são as duas respostas legítimas; quebrar não é.

    E onde o valor é **recusado**, a asserção inclui o corpo: um 422 sem
    discriminador de staff seria o framework recusando a forma, não o domínio
    recusando o conteúdo — e a diferença é exatamente o que este critério mede.
    """
    invocacao = _INVOCACOES[chave_da_rota]
    assert invocacao.body is not None
    corpo = {**invocacao.body, campo: valor}

    resposta = await _invocar(client, chave_da_rota, body=corpo)

    assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
    if resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY:
        assert resposta.json()["type"] == _CORPO_DE_STAFF


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

    **A asserção sobre a sentinela é estritamente mais forte que uma sobre
    status:** ela exige **identidade de objeto**, que é L-AG2 — a exceção sobe
    **crua**, sem tradução. Um adapter que a capturasse e relançasse uma exceção
    nova passaria em `pytest.raises(TipoX)` e falha aqui.
    """
    for rota in _rotas():
        for parametro in _params_de_path_de_id(rota):
            try:
                resposta = await _invocar(client, chave(rota), path={parametro: valor})
            except FakeAuthorizationRejected as exc:
                assert exc is ambiente.guard.authorization_error, (
                    f"{rota.path}: a recusa do guard foi traduzida no caminho (L-AG2)"
                )
                continue
            assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (
                f"{rota.path} devolveu {resposta.status_code} para {valor!r}"
            )


def test_o_dominio_adversarial_de_ca24_nao_esta_vazio() -> None:
    """Sem casos, o critério passaria por vacuidade — e passaria para sempre."""
    assert _CASOS_ADVERSARIAIS
    assert _CASOS_DE_PATH

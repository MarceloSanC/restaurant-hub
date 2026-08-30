"""Faixas de status do BC staff pela API real — CA19, CA22 e a metade e2e de CA24.

**"Pelo HTTP real" é o critério, e não redundância com a Task 03.** Lá o mapa
`STAFF_ERROR_STATUS` é verificado par a par contra o dicionário, e é assim que se
prova que a **classificação** está certa. Aqui prova-se outra coisa: que a exceção
de fato **atravessa** — sobe do use case, passa pelo handler registrado em
`create_app` e chega ao cliente com o corpo que `build_error_response` monta. Um
mapa perfeito ligado a um router que nunca levanta a exceção é um mapa decorativo,
e nenhum teste do dicionário percebe isso.

## As duas defesas contra o 422 que não é de staff

Nesta app a faixa 422 tem **duas origens**: o erro de staff e o
`RequestValidationError` do framework, que o handler compartilhado responde com
`{"detail": "requisição inválida", "type": "validation_error"}`. Asserir
`status == 422` é, portanto, uma asserção fraca: ela fica verde com o validador de
staff ausente. As duas defesas são as mesmas das varreduras unitárias:

1. **invocar com corpo e query válidos**, degradando só o campo sob teste — o que
   `ROTAS`, declarado na suíte de autorização, entrega por construção;
2. **asserir o discriminador** `type == "staff_error"` sempre que a recusa for de
   staff.

## O domínio é derivado, e nunca listado

- **CA22** sai da introspecção dos schemas: as rotas cujo `*Request` tem um campo
  `name`. Listar *"R01, R03, R05, R07"* deixaria uma quinta rota que aceitasse nome
  escapar em silêncio — no arquivo cuja tese é derivar.
- **CA24** sai do corpo declarado de cada rota (descendo pelos aninhados, porque
  `weekly_hours` mora dentro da união de perfil de jornada) e dos parâmetros de
  query do `dependant` do FastAPI.

Os dois carregam a **contagem** do domínio junto com a lei: uma varredura que ficou
vazia deixa qualquer asserção universal verde, e foi a contagem — não a asserção —
que pegou o falso verde de CA30 na Task 09.

## Por que a suíte de autorização é importada, e não copiada

`ROTAS`, `Recursos` e `_semear` são a declaração de **como se invoca cada rota
contra recursos vivos**. Duplicá-los aqui criaria duas verdades sobre o corpo válido
de cada rota, e a divergência apareceria como um 422 do framework satisfazendo um
critério de staff — exatamente o defeito que este módulo existe para não ter.
"""

import importlib
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Any, Final

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient, Response
from pydantic import BaseModel

from tests.e2e.features.staff.conftest import API, Cenario, auth
from tests.e2e.features.staff.test_staff_authorization import (
    ROTAS,
    ChaveDeRota,
    Recursos,
    _semear,
    _url,
    chave,
)

pytestmark = pytest.mark.e2e

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"
router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
error_handlers_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.error_handlers")

_DISCRIMINADOR_DE_STAFF: Final = "staff_error"

# As **três** faixas de §6.1 — transcritas do concept, e não colhidas do mapa. O
# cruzamento com o mapa é o teste abaixo: se os dois lados saíssem da mesma fonte,
# uma faixa nova entraria com cenário nenhum e a totalidade continuaria verde.
FAIXAS_DO_MAPA: Final = (
    HTTPStatus.NOT_FOUND,
    HTTPStatus.CONFLICT,
    HTTPStatus.UNPROCESSABLE_ENTITY,
)

# O conjunto adversarial da Stage 3.3 mais os numéricos degenerados que CA24 nomeia.
# O critério é **ausência de 500**: aceitar ou recusar são as duas respostas
# legítimas; quebrar não é.
_VALORES_ADVERSARIAIS: Final = (
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

_NOME_COM_NUL: Final = "Ana\x00Souza"

# Um período que nunca foi registrado — `_semear` grava outro, e R11 acrescenta um
# terceiro. É o insumo de `UnavailabilityNotFoundError`, que CA19 exige que responda
# 422 e não 404.
_PERIODO_NUNCA_REGISTRADO: Final = {
    "start": "2030-01-01T08:00:00",
    "end": "2030-01-01T12:00:00",
}


# ---------------------------------------------------------------------------
# Invocação: sempre a partir do corpo/query válidos da rota
# ---------------------------------------------------------------------------


async def _requisitar(  # noqa: PLR0913
    # A aridade é a da invocação: cliente, rota, estado, credencial e os dois
    # eixos que um teste pode degradar. Agrupá-los num objeto esconderia que
    # corpo e query têm defaults **válidos**, que é a defesa contra o 422 do
    # framework — e é ela que o docstring abaixo precisa poder prometer.
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    recursos: Recursos,
    cabecalho: dict[str, str],
    *,
    body: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
) -> Response:
    """Invoca a rota com a sua declaração, sobrescrevendo só o que o teste pede.

    O corpo default é o **válido** da declaração. Sem isso, uma rota com corpo
    obrigatório responderia 422 pelo `RequestValidationError` do framework, e toda
    asserção de faixa deste módulo ficaria verde contra o erro errado.
    """
    metodo, _ = chave_da_rota
    rota = ROTAS[chave_da_rota]
    return await client.request(
        metodo,
        _url(chave_da_rota, recursos, sobrescreve={}),
        params={**rota.query(recursos), **(query or {})},
        json=rota.body(recursos) if body is None else body,
        headers=cabecalho,
    )


@pytest.fixture
async def recursos(client: AsyncClient, cenario: Cenario) -> Recursos:
    """Função, função livre, funcionário e um período registrado, na unidade A."""
    return await _semear(client, cenario, cenario.unidade_a, cenario.unidade_b, "faixas")


@pytest.fixture
def cabecalho(cenario: Cenario) -> dict[str, str]:
    """O `manager`: detém as duas permissões, e é o ator do DoD (CA25)."""
    return auth(cenario.manager)


# ---------------------------------------------------------------------------
# CA19 — as três faixas, pelo HTTP real
# ---------------------------------------------------------------------------


async def _cenario_404(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`JobFunctionNotFoundError` — a função endereçada não existe no tenant.

    A faixa 404 é exercitada pela **função**, e não pelo funcionário, de propósito:
    `EmployeeNotFoundError` já chega ao fio em `test_staff_authorization.py`, na
    metade 404 de CA13. Duas faixas provadas pelo mesmo caminho provariam o caminho,
    não a faixa.
    """
    return await client.patch(
        f"{API}/job-functions/funcao-que-nunca-existiu",
        json={"name": "Sommelier"},
        headers=cabecalho,
    )


async def _cenario_409(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`JobFunctionInUseError` — o payload está correto, e **outro registro** impede.

    É a definição de faixa do ADR 3.4.0002 §4 no fio: a função semeada está atribuída
    ao funcionário semeado, e a FK `RESTRICT` da 3.3 recusa a remoção. O caminho
    inteiro é exercitado — `IntegrityError` do Postgres, tradução por operação
    (ADR 3.3.0004), erro de application, handler, 409.
    """
    return await client.delete(f"{API}/job-functions/{recursos.job_function_id}", headers=cabecalho)


async def _cenario_422(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`InvalidDayPeriodError` — invariante violada **pelo conteúdo enviado**.

    É o caso que §5.15 existe para produzir: `DayPeriod("xpto")` levantaria
    `ValueError` e viraria 500; `from_string` levanta um `StaffError` que o mapa
    classifica como 422. O 422 aqui só conta com o corpo de staff — sem isso, um
    router que tivesse esquecido o conversor passaria com o 422 do framework.
    """
    return await client.put(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/shift-preference",
        json={"shift_preference": ["xpto"]},
        headers=cabecalho,
    )


Cenario422 = Callable[[AsyncClient, dict[str, str], Recursos], Awaitable[Response]]

CENARIOS: dict[HTTPStatus, Cenario422] = {
    HTTPStatus.NOT_FOUND: _cenario_404,
    HTTPStatus.CONFLICT: _cenario_409,
    HTTPStatus.UNPROCESSABLE_ENTITY: _cenario_422,
}


def test_toda_faixa_do_mapa_de_staff_tem_cenario_e2e() -> None:
    """A completude do `parametrize`, verificada em vez de confiada — nos dois lados.

    A primeira asserção cruza a transcrição de §6.1 com o **mapa real**: uma faixa
    nova em `STAFF_ERROR_STATUS` (um 400, um 410) deixa a tupla desatualizada e
    reprova aqui, em vez de nascer sem nenhum exercício e2e. A segunda cobra o
    cenário. Sem as duas, remover um cenário apenas reduziria o número de testes
    rodados — e uma suíte menor passa mais fácil.
    """
    faixas_do_dicionario = set(error_handlers_module.STAFF_ERROR_STATUS.values())

    assert faixas_do_dicionario == set(FAIXAS_DO_MAPA)
    assert set(CENARIOS) == set(FAIXAS_DO_MAPA)


@pytest.mark.parametrize("faixa", FAIXAS_DO_MAPA, ids=lambda f: str(int(f)))
async def test_ca19_cada_faixa_e_alcancavel_pelo_http_real(
    client: AsyncClient,
    cabecalho: dict[str, str],
    recursos: Recursos,
    faixa: HTTPStatus,
) -> None:
    """CA19 — cada faixa produzida por uma requisição de verdade, com corpo de staff.

    O corpo é asserido junto com o status porque é ele que identifica **quem**
    respondeu: um 404 do roteador (path que não casa rota nenhuma) e um 422 do
    framework satisfariam o status sem que o mapa de staff tivesse sido consultado.
    """
    resposta = await CENARIOS[faixa](client, cabecalho, recursos)

    assert resposta.status_code == faixa, resposta.text
    assert resposta.json()["type"] == _DISCRIMINADOR_DE_STAFF, resposta.text


async def test_ca19_periodo_inexistente_responde_422_e_nao_404(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> None:
    """CA19, segunda metade — `UnavailabilityNotFoundError` é **422**, pelo fio.

    O período é um **valor dentro do agregado**, não um recurso endereçável: o
    funcionário existe e foi encontrado, e o que falhou foi a igualdade de valor que
    o cliente reapresentou. A classe herda **só** de `StaffError` precisamente para
    que a MRO não a leve ao 404 (ADR 3.4.0002 §4), e este teste é o que reprova se
    alguém a fizer herdar de `NotFoundError`: a herança mudaria o status para 404 sem
    tocar em nenhuma linha do mapa.
    """
    resposta = await client.delete(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/unavailabilities",
        params=dict(_PERIODO_NUNCA_REGISTRADO),
        headers=cabecalho,
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resposta.text
    assert resposta.json()["type"] == _DISCRIMINADOR_DE_STAFF


# ---------------------------------------------------------------------------
# O domínio derivado: schemas de corpo, campos escalares e parâmetros de query
# ---------------------------------------------------------------------------


def _rota_de(chave_da_rota: ChaveDeRota) -> APIRoute:
    return next(
        rota
        for rota in router_module.router.routes
        if isinstance(rota, APIRoute) and chave(rota) == chave_da_rota
    )


def _schema_do_corpo(chave_da_rota: ChaveDeRota) -> type[BaseModel] | None:
    """O `*Request` que a rota recebe, derivado das anotações do handler.

    **A anotação `return` é excluída, e a exclusão é a correção de um falso
    positivo medido.** O `response_model` de toda rota de escrita também é um
    `BaseModel` — `EmployeeResponse` tem um campo `name` —, então varrer
    `__annotations__` inteiro fazia `termination`, `rehire` e `DELETE
    .../unavailabilities` entrarem no domínio de CA22 como se aceitassem nome no
    corpo. Elas não têm corpo nenhum: o teste enviava `null` e media o 422 do
    framework. Uma varredura que erra **para mais** é tão ruim quanto uma que erra
    para menos — só falha de um jeito mais barulhento.
    """
    rota = _rota_de(chave_da_rota)
    anotacoes = getattr(rota.endpoint, "__annotations__", {})
    for nome, anotacao in anotacoes.items():
        if nome == "return":
            continue
        if isinstance(anotacao, type) and issubclass(anotacao, BaseModel):
            return anotacao
    return None


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


def _anotacao_no_caminho(modelo: type[BaseModel], caminho: tuple[str, ...]) -> object:
    """A anotação declarada para um caminho de campos, descendo pelos aninhados."""
    nome, resto = caminho[0], caminho[1:]
    campo = modelo.model_fields.get(nome)
    if campo is None:
        return None
    if not resto:
        return campo.annotation
    for aninhado in _modelos_em(campo.annotation):
        if resto[0] in aninhado.model_fields:
            return _anotacao_no_caminho(aninhado, resto)
    return None


def _escalares(valor: object, prefixo: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Caminhos até os valores **string** do corpo, descendo pelos aninhados.

    Descer é exigência do critério: o concept nomeia `weekly_hours` como o campo
    *"por onde escapou o 500 do `decimal.InvalidOperation`"*, e ele vive **dentro**
    da união de perfil de jornada. Uma varredura de primeiro nível o deixaria de fora
    exatamente no campo que motivou CA24.
    """
    if isinstance(valor, str):
        return [prefixo]
    if isinstance(valor, dict):
        return [
            caminho
            for nome, aninhado in valor.items()
            for caminho in _escalares(aninhado, (*prefixo, str(nome)))
        ]
    return []


def _com_valor_em(corpo: dict[str, Any], caminho: tuple[str, ...], valor: str) -> dict[str, Any]:
    """Copia o corpo trocando **só** o campo do caminho — o resto continua válido."""
    if len(caminho) == 1:
        return {**corpo, caminho[0]: valor}
    aninhado = corpo[caminho[0]]
    assert isinstance(aninhado, dict)
    return {**corpo, caminho[0]: _com_valor_em(aninhado, caminho[1:], valor)}


def _quem_parseia(chave_da_rota: ChaveDeRota, caminho: tuple[str, ...]) -> str:
    """Quem recusa um valor degenerado neste campo: `"staff"` ou `"framework"`.

    Um campo declarado `str` chega **intacto** ao router, e é staff quem o converte e
    recusa: ali o 422 tem de trazer o corpo de staff. Um campo declarado `datetime`,
    `bool` ou `Literal` é parseado pelo **framework** antes de o handler rodar, e lixo
    nele é erro de **forma** — `validation_error` é a resposta correta, e exigir corpo
    de staff seria exigir que staff assumisse uma recusa que não é dele.
    """
    modelo = _schema_do_corpo(chave_da_rota)
    if modelo is None:
        return "framework"
    return "staff" if _anotacao_no_caminho(modelo, caminho) is str else "framework"


def _campos_escalares(chave_da_rota: ChaveDeRota) -> list[tuple[str, ...]]:
    corpo = ROTAS[chave_da_rota].body(_RECURSOS_DE_INTROSPECCAO)
    return [] if corpo is None else _escalares(corpo)


def _params_de_query(chave_da_rota: ChaveDeRota) -> list[str]:
    """Os parâmetros de query da rota, derivados do `dependant` do FastAPI.

    Derivar do `dependant`, e não da assinatura crua, é o que separa parâmetro de
    query de dependência resolvida por `Depends`: as duas aparecem lado a lado na
    assinatura do handler, e só o framework sabe distingui-las.
    """
    return [parametro.name for parametro in _rota_de(chave_da_rota).dependant.query_params]


# Recursos de mentira, usados **só** para colher a forma do corpo declarado em tempo
# de coleta. Nenhuma requisição sai daqui: os valores reais entram no momento do
# teste, pela fixture.
_RECURSOS_DE_INTROSPECCAO: Final = Recursos(
    unidade="u",
    unidade_destino="v",
    employee_id="e",
    job_function_id="f",
    job_function_livre="g",
    sufixo="introspecção",
)

# As rotas cujo `*Request` declara um campo `name` — o domínio de CA22, derivado.
ROTAS_COM_NOME: Final = tuple(
    sorted(
        chave_da_rota
        for chave_da_rota in ROTAS
        if (modelo := _schema_do_corpo(chave_da_rota)) is not None and "name" in modelo.model_fields
    )
)

_CASOS_DE_CORPO: Final = tuple(
    sorted(
        (chave_da_rota, caminho)
        for chave_da_rota in ROTAS
        for caminho in _campos_escalares(chave_da_rota)
    )
)

_CASOS_DE_QUERY: Final = tuple(
    sorted(
        (chave_da_rota, parametro)
        for chave_da_rota in ROTAS
        for parametro in _params_de_query(chave_da_rota)
    )
)


def _id_do_caso(caso: object) -> str:
    if isinstance(caso, tuple):
        return "-".join(str(parte) for parte in caso)
    return str(caso)


def test_os_dominios_derivados_de_ca22_e_ca24_nao_estao_vazios() -> None:
    """Sem casos, os dois critérios passariam por vacuidade — e para sempre.

    A contagem é a única guarda contra um helper de introspecção que pare de
    encontrar o que procura: `all(...)` sobre conjunto vazio é verdadeiro, e nenhuma
    asserção universal deste módulo perceberia. Os números **não** são fixados de
    propósito, exceto onde o critério os fixa: uma quinta rota que aceite nome
    **deve** entrar em CA22 sozinha, e travar o total em quatro seria reinstalar a
    lista literal que a derivação existe para aposentar.
    """
    assert ROTAS_COM_NOME, "nenhuma rota com campo `name` — a varredura de CA22 não mede nada"
    assert _CASOS_DE_CORPO, "nenhum campo escalar de corpo — a varredura de CA24 não mede nada"
    assert _CASOS_DE_QUERY, "nenhum parâmetro de query — o terceiro eixo de CA24 sumiu"
    assert _VALORES_ADVERSARIAIS, "o conjunto adversarial ficou vazio"


def test_a_varredura_de_ca24_alcanca_o_campo_aninhado_que_o_criterio_nomeia() -> None:
    """`weekly_hours` tem de estar no domínio, e é **aninhado**.

    O concept o nomeia como o campo por onde escapou o 500 do
    `decimal.InvalidOperation`. Uma varredura de primeiro nível o deixaria de fora
    justamente ali, e CA24 ficaria verde sobre o conjunto errado.
    """
    caminhos = {caminho for _, caminho in _CASOS_DE_CORPO}

    assert ("workload_profile", "weekly_hours") in caminhos
    assert ("name",) in caminhos


def test_a_classificacao_de_quem_parseia_nao_colapsou_para_um_lado_so() -> None:
    """Guarda da distinção: se tudo virasse "framework", a exigência de corpo sumiria.

    `_quem_parseia` decide se o 422 precisa trazer o discriminador de staff. Um bug
    que a fizesse devolver sempre `"framework"` desligaria essa metade de CA24 em
    silêncio, e nenhum caso ficaria vermelho.
    """
    especies = {_quem_parseia(chave_da_rota, caminho) for chave_da_rota, caminho in _CASOS_DE_CORPO}

    assert especies == {"staff", "framework"}


# ---------------------------------------------------------------------------
# CA22 — nome com byte NUL, em todas as rotas que aceitam nome
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chave_da_rota", ROTAS_COM_NOME, ids=_id_do_caso)
async def test_ca22_nome_com_byte_nul_recebe_422_de_staff(
    client: AsyncClient,
    cabecalho: dict[str, str],
    recursos: Recursos,
    chave_da_rota: ChaveDeRota,
) -> None:
    """CA22 — o domínio é **derivado**, e as rotas de edição contam tanto quanto as de criação.

    A rejeição do NUL em nome é do **domínio** desde a 3.4 (ADR 3.4.0003); o que se
    prova aqui é que a borda a alcança e a classifica **em cada caminho que a
    produz**. Travar o critério nas duas rotas de criação deixaria de fora
    exatamente as rotas de renomear — que é por onde um nome inválido entra num
    registro que já existe.

    O corpo é o válido da rota com **só** o `name` corrompido: sem isso, R05
    responderia 422 pelo `RequestValidationError` por falta do perfil de jornada, e o
    critério ficaria verde com a validação de nome ausente.
    """
    corpo = ROTAS[chave_da_rota].body(recursos)
    assert corpo is not None and "name" in corpo
    corpo = {**corpo, "name": _NOME_COM_NUL}

    resposta = await _requisitar(client, chave_da_rota, recursos, cabecalho, body=corpo)

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resposta.text
    assert resposta.json()["type"] == _DISCRIMINADOR_DE_STAFF, resposta.text


# ---------------------------------------------------------------------------
# CA24, metade e2e — nenhum campo escalar nem parâmetro de query devolve 500
# ---------------------------------------------------------------------------
#
# **O produto é percorrido dentro do caso, e não por `parametrize`.** Cada célula
# e2e reprovisiona o cenário inteiro pela API (com argon2 em cada ator), e o produto
# `13 campos x 13 valores` custaria ~3 minutos para provar uma lei cujo veredito é um
# único bit por célula. O que a parametrização compra — saber *qual* célula quebrou —
# é comprado aqui pela mensagem da asserção, que nomeia rota, campo e valor. O que
# ela **não** compra, e que continua garantido, é a totalidade do domínio: os casos
# saem da introspecção e a contagem é asserida acima.


@pytest.mark.parametrize(("chave_da_rota", "caminho"), _CASOS_DE_CORPO, ids=_id_do_caso)
async def test_ca24_nenhum_campo_escalar_do_corpo_devolve_500(
    client: AsyncClient,
    cabecalho: dict[str, str],
    recursos: Recursos,
    chave_da_rota: ChaveDeRota,
    caminho: tuple[str, ...],
) -> None:
    """Aceitar ou recusar são as duas respostas legítimas; quebrar não é.

    E onde a recusa é de **staff** — campo declarado `str`, que chega intacto ao
    router —, o 422 tem de trazer o discriminador. Num campo que o framework parseia,
    `validation_error` é a resposta correta e exigir corpo de staff mediria a peça
    errada.

    O `target_unit_id` de R16 é o caso que mostra por que a asserção forte é
    condicional: ele é **alvo de autorização**, e um valor bem-formado que o ator não
    tem concedido é negado pelo guard com **403** — resposta legítima, e nem 422 nem
    500.
    """
    corpo = ROTAS[chave_da_rota].body(recursos)
    assert corpo is not None
    exige_corpo_de_staff = _quem_parseia(chave_da_rota, caminho) == "staff"

    for valor in _VALORES_ADVERSARIAIS:
        resposta = await _requisitar(
            client,
            chave_da_rota,
            recursos,
            cabecalho,
            body=_com_valor_em(corpo, caminho, valor),
        )

        onde = f"{chave_da_rota[0]} {chave_da_rota[1]} {'.'.join(caminho)}={valor!r}"
        assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (
            f"{onde} devolveu {resposta.status_code}: {resposta.text}"
        )
        if resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY and exige_corpo_de_staff:
            assert resposta.json()["type"] == _DISCRIMINADOR_DE_STAFF, (
                f"{onde} recebeu um 422 que não é de staff: {resposta.text}"
            )


@pytest.mark.parametrize(("chave_da_rota", "parametro"), _CASOS_DE_QUERY, ids=_id_do_caso)
async def test_ca24_nenhum_parametro_de_query_devolve_500(
    client: AsyncClient,
    cabecalho: dict[str, str],
    recursos: Recursos,
    chave_da_rota: ChaveDeRota,
    parametro: str,
) -> None:
    """O terceiro eixo, que o critério nomeia — *"mais os parâmetros de query"*.

    **A asserção é só sobre o 500, e a assimetria com o eixo de corpo é deliberada.**
    Os parâmetros de query de hoje são `bool` (`include_inactive`) e `datetime`
    (`start`/`end`): um valor degenerado neles é erro de **forma**, recusado pelo
    framework, e isso é o comportamento correto. O dia em que um identificador chegar
    por query, a varredura de CA20 nas unitárias fica vermelha e obriga a estender a
    exigência aqui também.
    """
    for valor in _VALORES_ADVERSARIAIS:
        resposta = await _requisitar(
            client, chave_da_rota, recursos, cabecalho, query={parametro: valor}
        )

        assert resposta.status_code < HTTPStatus.INTERNAL_SERVER_ERROR, (
            f"{chave_da_rota[1]}?{parametro}={valor!r} devolveu {resposta.status_code}: "
            f"{resposta.text}"
        )

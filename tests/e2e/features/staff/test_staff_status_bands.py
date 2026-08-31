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
from typing import Any, Final, get_args, get_origin

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

# Um passo de caminho é o **nome** de um campo ou o **índice** de um elemento de
# lista. O índice é o que permite corromper um período de `shift_preference` sem
# desmontar a lista que o carrega.
Caminho = tuple[str | int, ...]

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
# O eixo inteiro do mapa — toda exceção **alcançável** tem cenário HTTP
# ---------------------------------------------------------------------------
#
# **CA19 cobra as três faixas; o domínio quantificado do mapa é o mapa.** Um
# representante por faixa deixa quinze das dezoito entradas sem nenhuma travessia
# pelo fio: o erro está classificado (CA18), a faixa está exercitada (CA19), e
# ninguém verificou que a borda **produz** aquela exceção. Foi por essa fresta que
# `EmptyShiftPreferenceError` passou a Stage inteira sem um só caminho HTTP — com
# cobertura de linha e de ramo em 100% —, e com ela a mutação `if periodos is None`
# → `if not periodos` no conversor do router, que apaga em silêncio a preferência
# declarada como `[]` e responde 200 onde o contrato promete 422.
#
# O eixo é a **totalidade** do mapa menos as entradas declaradas inalcançáveis, e
# a declaração é transcrita à mão abaixo: derivá-la do código faria a expectativa
# seguir o defeito, e uma exceção que deixasse de ser produzida sairia do domínio
# sozinha.


async def _sem_funcao(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`JobFunctionNotFoundError` — a função endereçada não existe no tenant."""
    return await _cenario_404(client, cabecalho, recursos)


async def _sem_funcionario(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`EmployeeNotFoundError` — o registro endereçado não existe na unidade."""
    return await client.patch(
        f"{API}/units/{recursos.unidade}/employees/funcionário-que-nunca-existiu",
        json={"name": "Beltrano"},
        headers=cabecalho,
    )


async def _nome_de_funcao_repetido(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`JobFunctionNameAlreadyExistsError` — o nome já está gravado no tenant.

    O nome é o que `_semear` criou, e a comparação é **verbatim** (workforce §3.2):
    reenviá-lo idêntico é a única forma de colidir.
    """
    return await client.post(
        f"{API}/job-functions",
        json={"name": f"Função {recursos.sufixo}"},
        headers=cabecalho,
    )


async def _funcao_em_uso(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`JobFunctionInUseError` — a FK `RESTRICT` da 3.3 recusa a remoção."""
    return await _cenario_409(client, cabecalho, recursos)


async def _identificador_em_branco(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`InvalidIdentifierError` — o destino da cópia chega só-whitespace.

    O eixo escolhido é o **corpo**, e não o path: um segmento de path em branco é
    interceptado pelo roteador antes do handler (§6.3), e mediria o Starlette.
    """
    return await client.post(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/copies",
        json={"target_unit_id": "   "},
        headers=cabecalho,
    )


async def _nome_com_byte_nul(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`InvalidNameError` — a rejeição é do domínio desde a 3.4, e a borda a alcança."""
    return await client.patch(
        f"{API}/job-functions/{recursos.job_function_id}",
        json={"name": _NOME_COM_NUL},
        headers=cabecalho,
    )


async def _carga_semanal_nao_numerica(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`InvalidWeeklyHoursError` — o 500 do `decimal.InvalidOperation`, traduzido."""
    return await client.put(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/workload-profile",
        json={"workload_profile": {"type": "fixed", "weekly_hours": "abc"}},
        headers=cabecalho,
    )


async def _periodo_do_dia_desconhecido(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`InvalidDayPeriodError` — `DayPeriod.from_string` em vez do `ValueError` cru."""
    return await _cenario_422(client, cabecalho, recursos)


async def _preferencia_de_turno_vazia(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`EmptyShiftPreferenceError` — o eixo `[]`, que é **o achado desta correção**.

    `null` limpa a preferência (CA03); `[]` é o cliente declarando "prefiro nada",
    que o domínio recusa desde o ADR 3.1.0004 porque "sem preferência" já tem uma
    representação. O conversor do router distingue os dois pela **ausência**
    (`is None`), e não por truthiness: com `if not periodos`, a lista vazia
    passaria por `null`, a preferência gravada seria apagada em silêncio e a
    resposta seria 200 — a corrupção silenciosa que o ADR 2.3.0005 recusa.
    """
    return await client.put(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/shift-preference",
        json={"shift_preference": []},
        headers=cabecalho,
    )


async def _sem_nenhuma_funcao(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`EmptyJobFunctionsError` — a substituição que deixaria o registro sem função."""
    return await client.put(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/job-functions",
        json={"job_function_ids": []},
        headers=cabecalho,
    )


async def _periodo_malformado(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`InvalidUnavailabilityPeriodError` — `start >= end`, recusado pelo value object."""
    return await client.post(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/unavailabilities",
        json={"start": "2029-03-10T12:00:00", "end": "2029-03-10T08:00:00"},
        headers=cabecalho,
    )


async def _periodo_sobreposto(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`OverlappingUnavailabilityError` — sobreposição com o período que `_semear` gravou.

    A semântica é semi-aberta `[início, fim)` (ADR 3.1.0001): adjacente **não**
    conflita, então o período enviado começa dentro do semeado, e não no seu fim.
    """
    return await client.post(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/unavailabilities",
        json={"start": "2026-05-04T10:00:00", "end": "2026-05-04T14:00:00"},
        headers=cabecalho,
    )


async def _periodo_nunca_registrado(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`UnavailabilityNotFoundError` — remoção por igualdade de valor que não casa."""
    return await client.delete(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/unavailabilities",
        params=dict(_PERIODO_NUNCA_REGISTRADO),
        headers=cabecalho,
    )


async def _copia_para_a_propria_unidade(
    client: AsyncClient, cabecalho: dict[str, str], recursos: Recursos
) -> Response:
    """`SameUnitCopyError` — o cliente nomeou a origem como destino."""
    return await client.post(
        f"{API}/units/{recursos.unidade}/employees/{recursos.employee_id}/copies",
        json={"target_unit_id": recursos.unidade},
        headers=cabecalho,
    )


# As entradas do mapa que **nenhuma requisição consegue produzir**, e a razão de
# cada uma. Transcritas do comentário da entrada correspondente em
# `error_handlers.py` — este é o outro lado daquela declaração, e é o que faz dela
# uma afirmação verificada em vez de uma nota de rodapé:
#
# - `EmployeeInUseError` — sem produtor em v1; nasce com o Step 4 (alocação);
# - `EmployeeRelocationError` — nenhuma rota permite enviar `unit_id` num update;
# - as duas colisões de **id** — o id é UUID gerado dentro do use case, nunca
#   enviado pelo cliente, e produzi-las exigiria dois UUID4 iguais.
#
# Escritas por **nome**, e não por classe, porque o nome é o que a declaração de
# `error_handlers.py` carrega — e é a divergência entre os dois lados que este
# módulo precisa poder acusar.
INALCANCAVEIS_POR_HTTP: Final = frozenset(
    {
        "EmployeeInUseError",
        "EmployeeRelocationError",
        "JobFunctionAlreadyExistsError",
        "EmployeeAlreadyExistsError",
    }
)

CenarioDeExcecao = Callable[[AsyncClient, dict[str, str], Recursos], Awaitable[Response]]

# Cenário por exceção, com o **trecho da mensagem transcrito à mão**. O status
# sozinho não identifica a exceção — sete entradas compartilham o 422 —, e sem o
# trecho um cenário que produzisse a exceção errada da mesma faixa passaria.
CENARIOS_POR_EXCECAO: dict[str, tuple[CenarioDeExcecao, str]] = {
    "JobFunctionNotFoundError": (_sem_funcao, "função de trabalho não encontrada"),
    "EmployeeNotFoundError": (_sem_funcionario, "funcionário não encontrado"),
    "JobFunctionNameAlreadyExistsError": (
        _nome_de_funcao_repetido,
        "nome de função de trabalho já usado no restaurante",
    ),
    "JobFunctionInUseError": (_funcao_em_uso, "função de trabalho em uso por algum funcionário"),
    "InvalidIdentifierError": (_identificador_em_branco, "identificador de unidade"),
    "InvalidNameError": (_nome_com_byte_nul, "nome de função não pode conter o byte NUL"),
    "InvalidWeeklyHoursError": (
        _carga_semanal_nao_numerica,
        "carga semanal contratada inválida",
    ),
    "InvalidDayPeriodError": (_periodo_do_dia_desconhecido, "período do dia inválido"),
    "EmptyShiftPreferenceError": (
        _preferencia_de_turno_vazia,
        "preferência de turno exige ao menos um período",
    ),
    "EmptyJobFunctionsError": (
        _sem_nenhuma_funcao,
        "funcionário exige ao menos uma função atribuída",
    ),
    "InvalidUnavailabilityPeriodError": (
        _periodo_malformado,
        "período de indisponibilidade inválido",
    ),
    "OverlappingUnavailabilityError": (
        _periodo_sobreposto,
        "períodos de indisponibilidade não podem se sobrepor",
    ),
    "UnavailabilityNotFoundError": (
        _periodo_nunca_registrado,
        "período de indisponibilidade não encontrado",
    ),
    "SameUnitCopyError": (
        _copia_para_a_propria_unidade,
        "cópia exige unidade destino diferente da origem",
    ),
}

_TOTAL_DE_ENTRADAS_DO_MAPA: Final = 18

# O tamanho do domínio de corpo de CA24 **depois** de a varredura descer por
# lista. Eram dez caminhos; os três novos são um elemento de `job_function_ids`
# em cada uma das duas rotas que o aceitam e o período de `shift_preference`.
# A contagem é transcrita, e não derivada: é ela que faz um encolhimento do
# domínio reprovar em vez de reduzir em silêncio o número de casos rodados.
_TOTAL_DE_CAMPOS_ESCALARES: Final = 13


def test_toda_excecao_alcancavel_do_mapa_tem_cenario_e2e() -> None:
    """A totalidade do eixo, e é ela que impede a próxima `EmptyShiftPreferenceError`.

    O domínio quantificado de "a exceção atravessa o fio" é o **mapa**, e não as
    três faixas: exceção nova sem cenário — ou exceção que deixasse de ser
    produzida — reprova aqui, em vez de nascer coberta pela faixa de um irmão.

    As duas metades são necessárias. A partição cobra que cada entrada esteja de
    **um** dos dois lados; a cardinalidade cobra que o mapa não tenha encolhido —
    um mapa esvaziado satisfaria a partição com os dois conjuntos vazios.
    """
    entradas = {classe.__name__ for classe in error_handlers_module.STAFF_ERROR_STATUS}

    assert len(entradas) == _TOTAL_DE_ENTRADAS_DO_MAPA, sorted(entradas)
    assert set(CENARIOS_POR_EXCECAO) | INALCANCAVEIS_POR_HTTP == entradas
    assert set(CENARIOS_POR_EXCECAO) & INALCANCAVEIS_POR_HTTP == set()


@pytest.mark.parametrize("nome_da_excecao", sorted(CENARIOS_POR_EXCECAO))
async def test_cada_excecao_alcancavel_atravessa_o_http_real(
    client: AsyncClient,
    cabecalho: dict[str, str],
    recursos: Recursos,
    nome_da_excecao: str,
) -> None:
    """Uma requisição real por exceção, com o status **do mapa** e a mensagem dela.

    O status esperado sai de `STAFF_ERROR_STATUS`, e a mensagem é transcrita: o
    par é o que separa "alguma exceção de staff saiu" de "**esta** exceção saiu".
    Sem o trecho da mensagem, um cenário que produzisse o irmão de faixa — dois
    422 quaisquer — passaria, e o eixo voltaria a ser um representante por faixa
    com mais casos.
    """
    cenario, trecho = CENARIOS_POR_EXCECAO[nome_da_excecao]
    esperado = next(
        status
        for classe, status in error_handlers_module.STAFF_ERROR_STATUS.items()
        if classe.__name__ == nome_da_excecao
    )

    resposta = await cenario(client, cabecalho, recursos)

    assert resposta.status_code == esperado, resposta.text
    corpo = resposta.json()
    assert corpo["type"] == _DISCRIMINADOR_DE_STAFF, resposta.text
    assert trecho in corpo["detail"], resposta.text


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


def _elemento_de(anotacao: object) -> object:
    """O tipo do **elemento** de uma anotação de lista, inclusive sob `| None`.

    `shift_preference` é `list[str] | None`: sem descer pela união, o elemento
    ficaria sem anotação e `_quem_parseia` o classificaria como do framework —
    exatamente ao contrário do que acontece, já que a lista chega intacta ao
    router e é `DayPeriod.from_string` quem recusa.
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
    `weekly_hours` como o campo *"por onde escapou o 500 do
    `decimal.InvalidOperation`"*, e ele vive dentro da união de perfil de jornada.

    Descer por **lista** é a correção de um domínio que excluía elementos justamente
    onde o critério os nomeia. CA24 diz, na letra, *"todos os campos escalares de
    todos os `*Request` … o que inclui `weekly_hours` … e os períodos de
    `shift_preference`"* — e a versão anterior devolvia `[]` para `list`, deixando
    de fora os períodos de `shift_preference` e os elementos de `job_function_ids`.
    A assimetria que denunciava: `weekly_hours` tinha guarda dedicada, e o outro
    campo que o mesmo parágrafo nomeia não tinha nenhuma.

    O passo por lista é o **índice**, e não o nome do campo: é o que permite
    corromper um elemento mantendo a forma da lista — corromper o campo inteiro
    produziria um erro de forma do framework em vez do erro que se quer medir.
    """
    if isinstance(valor, str):
        return [prefixo]
    if isinstance(valor, dict):
        return [
            caminho
            for nome, aninhado in valor.items()
            for caminho in _escalares(aninhado, (*prefixo, str(nome)))
        ]
    if isinstance(valor, list):
        return [
            caminho
            for indice, item in enumerate(valor)
            for caminho in _escalares(item, (*prefixo, indice))
        ]
    return []


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
    """Copia o corpo trocando **só** o campo do caminho — o resto continua válido."""
    resultado = _substituindo(corpo, caminho, valor)
    assert isinstance(resultado, dict)
    return resultado


def _quem_parseia(chave_da_rota: ChaveDeRota, caminho: Caminho) -> str:
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


def _campos_escalares(chave_da_rota: ChaveDeRota) -> list[Caminho]:
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


def test_a_varredura_de_ca24_alcanca_os_dois_campos_que_o_criterio_nomeia() -> None:
    """`weekly_hours` **e** os períodos de `shift_preference` — o parágrafo nomeia os dois.

    O primeiro é aninhado dentro da união de perfil de jornada; os segundos são
    **elementos de lista**, e ficavam de fora porque `_escalares` devolvia `[]`
    para `list`. A assimetria que denunciava o buraco: um dos dois campos que o
    critério nomeia tinha guarda dedicada, e o outro não tinha nenhuma.

    A contagem entra junto porque é ela que prova que o domínio **cresceu**: dez
    caminhos antes de descer por lista, treze depois — os três novos são um
    elemento de `job_function_ids` em cada uma das duas rotas que o aceitam, e o
    período de `shift_preference`.
    """
    caminhos = {caminho for _, caminho in _CASOS_DE_CORPO}

    assert ("workload_profile", "weekly_hours") in caminhos
    assert ("name",) in caminhos
    assert ("shift_preference", 0) in caminhos
    assert ("job_function_ids", 0) in caminhos
    assert len(_CASOS_DE_CORPO) == _TOTAL_DE_CAMPOS_ESCALARES, sorted(_CASOS_DE_CORPO)


def test_os_elementos_de_lista_sao_do_lado_de_staff_no_dominio_de_ca24() -> None:
    """Elemento de lista é `str` no schema, e por isso a recusa dele é de **staff**.

    É a metade que faz a extensão valer alguma coisa. Se `_elemento_de` não
    descesse pela união de `list[str] | None`, o período de `shift_preference`
    entraria no domínio classificado como "framework", e a exigência do corpo de
    staff — a defesa contra o 422 que não é desta borda — ficaria desligada
    justamente nos caminhos recém-abertos.
    """
    novos = [
        (chave_da_rota, caminho)
        for chave_da_rota, caminho in _CASOS_DE_CORPO
        if any(isinstance(passo, int) for passo in caminho)
    ]

    assert novos, "nenhum elemento de lista no domínio — a descida por lista sumiu"
    assert {_quem_parseia(chave_da_rota, caminho) for chave_da_rota, caminho in novos} == {"staff"}


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
    caminho: Caminho,
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

        onde = (
            f"{chave_da_rota[0]} {chave_da_rota[1]} "
            f"{'.'.join(str(passo) for passo in caminho)}={valor!r}"
        )
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

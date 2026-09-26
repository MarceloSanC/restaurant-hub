"""Matriz papel x rota pela API real — CA08, CA09, CA10, CA11, CA12, CA13, CA29 e CA36.

**O eixo desta suíte é "quem alcança o quê", e só ele.** A classificação do erro
— as três faixas do BC staff — é o outro assunto, e mora em
`test_staff_status_bands.py`. Separá-los não é organização: juntos, os dois
produzem um commit que nenhum revisor lê, e um vermelho que não diz qual dos dois
assuntos quebrou.

## O domínio é derivado do router, e a cardinalidade é asserida junto

Toda lei aqui é universal sobre as 17 rotas (16 da 3.6 + R17 da 3.5), e o produto
cartesiano é **explícito** — `{employee, platform_admin} x R01…R17` são 34 casos,
não dois. As chaves saem de
`router.routes`; a declaração `ROTAS` diz como invocar cada uma contra recursos
**vivos**, e `test_a_declaracao_de_rotas_e_total_sobre_o_router` reprova a rota que
entrar sem declaração — a mesma disciplina do `_INVOCACOES` das varreduras
unitárias, aqui aplicada ao ambiente que tem banco.

**Todo conjunto derivado tem a sua contagem asserida**, e a exigência é a lição da
Task 09: uma varredura que ficou vazia deixa qualquer `all(...)` verde, e foi a
contagem — não a asserção — que pegou o falso verde de CA30.

## Por que estes critérios só existem aqui

No ambiente unitário o dublê do port levanta a **sua própria** sentinela, que não é
`IdentityError` e não tem handler: as recusas não têm forma HTTP. É a app real, com
os dois registradores de handlers montados (Task 09), que dá 401 e 403 com o corpo
constante de identity — e é por isso que CA08/CA09/CA13 são e2e, como o plano
declarou desde a Task 05.

## `hr ≡ manager`, e por que isso é um teste e não um comentário

O ADR 3.4.0006 §1 decidiu que `hr` e `manager` detêm as mesmas duas permissões de
staff, com o mesmo alcance. CA12 trava a decisão como propriedade: os dois papéis
respondem o **mesmo status** nas 17 rotas, sobre estados isomorfos. Um mapa de
papéis editado para dar a `hr` alcance diferente reprova aqui.
"""

import importlib
import urllib.parse
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Final

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient, Response

from tests.e2e.features.staff.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    Cenario,
    auth,
    fazer_login,
)

pytestmark = pytest.mark.e2e

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"
router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")

# A cardinalidade declarada do inventário (concept §4.1). Ela é o piso que
# transforma "toda rota satisfaz P" numa afirmação com conteúdo: sem ela, um
# `_rotas()` que devolvesse a lista vazia deixaria todo `parametrize` deste
# módulo sem um único caso, e a suíte ficaria verde por não medir nada.
# 16 até a 3.6; a Stage 3.5 acrescenta R17 (`POST .../login`).
_TOTAL_DE_ROTAS: Final = 17

# As três partições do inventário e os dois produtos que os critérios nomeiam.
# São **números transcritos do concept**, não derivados do código: derivá-los faria
# a expectativa acompanhar qualquer encolhimento do domínio, que é precisamente o
# modo de falha que estas contagens existem para pegar.
_TOTAL_DE_RJF: Final = 4
_TOTAL_DE_REMP: Final = 13
_TOTAL_COM_EMPLOYEE_ID: Final = 11
_CASOS_DE_CA09: Final = 34
_CASOS_DE_CA36: Final = 51

# Os corpos constantes de identity (`identity/adapters/in/http/error_handlers.py`).
# **Transcritos, e não importados**: o critério é sobre o contrato que o cliente
# recebe, e perguntá-lo ao módulo sob teste faria a expectativa seguir o defeito.
_CORPO_401: Final = {"detail": "não autenticado", "type": "unauthorized"}
_CORPO_403: Final = {"detail": "acesso negado", "type": "forbidden"}
_DISCRIMINADOR_DE_STAFF: Final = "staff_error"

# Os cinco papéis de §5.13, separados pelo que decidem: os três primeiros detêm as
# duas permissões de staff; os dois últimos não detêm nenhuma.
_PAPEIS_COM_PERMISSAO: Final = ("owner", "manager", "hr")
_PAPEIS_SEM_PERMISSAO: Final = ("employee", "platform_admin")

# O período semeado por `_semear`, que R12 remove **por igualdade de valor**, e um
# segundo que R11 acrescenta sem sobrepor o primeiro.
_PERIODO_SEMEADO: Final = {"start": "2026-05-04T08:00:00", "end": "2026-05-04T12:00:00"}
_PERIODO_NOVO: Final = {"start": "2026-06-01T08:00:00", "end": "2026-06-01T12:00:00"}

_UNIDADE_INEXISTENTE: Final = "unidade-que-nunca-existiu"

ChaveDeRota = tuple[str, str]


def _rotas() -> list[APIRoute]:
    """As rotas do router de staff, e só elas."""
    encontradas = [rota for rota in router_module.router.routes if isinstance(rota, APIRoute)]
    assert encontradas, "a matriz precisa de rotas para ter o que medir"
    return encontradas


def chave(rota: APIRoute) -> ChaveDeRota:
    """`(método, path)` — a identidade de uma rota para toda a matriz."""
    metodos = sorted(rota.methods - {"HEAD", "OPTIONS"})
    assert len(metodos) == 1, f"rota com mais de um método: {rota.path} {metodos}"
    return (metodos[0], rota.path)


# ---------------------------------------------------------------------------
# Os recursos vivos e a declaração de invocação por rota
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Recursos:
    """Os registros que uma invocação bem-sucedida precisa encontrar no banco.

    Attributes:
        unidade: a unidade do **path** — a que endereça o registro.
        unidade_destino: a outra unidade do mesmo restaurante, destino de R16.
        employee_id: o funcionário semeado em `unidade`.
        job_function_id: a função atribuída a esse funcionário.
        job_function_livre: uma segunda função, **sem** nenhum funcionário — R04
            a remove, e removê-la é 204; remover a primeira seria 409
            (`JobFunctionInUseError`), que mediria outra coisa.
        sufixo: discrimina os nomes quando dois conjuntos isomorfos coexistem
            (CA12) ou quando duas unidades são semeadas lado a lado (CA11).
    """

    unidade: str
    unidade_destino: str
    employee_id: str
    job_function_id: str
    job_function_livre: str
    sufixo: str


Efeito = Callable[[AsyncClient, dict[str, str], Response, Recursos], Awaitable[None]]


async def _efeito_no_registro_da_unidade_do_path(
    _client: AsyncClient, _cabecalho: dict[str, str], resposta: Response, recursos: Recursos
) -> None:
    """O default: a resposta de escrita devolve o registro, e ele é da unidade do path."""
    assert resposta.json()["unit_id"] == recursos.unidade


async def _efeito_listagem_so_da_unidade_do_path(
    _client: AsyncClient, _cabecalho: dict[str, str], resposta: Response, recursos: Recursos
) -> None:
    """R06 não devolve um registro: devolve o conjunto, que tem de ser o da unidade."""
    itens = resposta.json()
    assert itens, "a listagem da unidade do path veio vazia — não há efeito a observar"
    assert {item["unit_id"] for item in itens} == {recursos.unidade}


async def _efeito_removido_da_unidade_do_path(
    client: AsyncClient, cabecalho: dict[str, str], _resposta: Response, recursos: Recursos
) -> None:
    """R15 responde 204 sem corpo — o efeito só é observável relendo a unidade."""
    restante = await client.get(
        f"{API}/units/{recursos.unidade}/employees",
        headers=cabecalho,
        params={"include_inactive": "true"},
    )
    assert recursos.employee_id not in {item["id"] for item in restante.json()}


async def _efeito_login_no_registro_da_unidade_do_path(
    _client: AsyncClient, _cabecalho: dict[str, str], resposta: Response, recursos: Recursos
) -> None:
    """R17 (3.5) embrulha o registro: o `unit_id` está em `employee`, e o vínculo também."""
    corpo = resposta.json()
    assert corpo["employee"]["unit_id"] == recursos.unidade
    assert corpo["employee"]["id"] == recursos.employee_id
    assert corpo["employee"]["user_id"] is not None


async def _efeito_copia_lida_da_unidade_do_path(
    client: AsyncClient, cabecalho: dict[str, str], resposta: Response, recursos: Recursos
) -> None:
    """R16 é a rota com **duas** unidades, e as duas pontas precisam ser asseridas.

    A cópia cai no **destino** (é o que `target_unit_id` significa), mas o registro
    lido é o da unidade do **path** — e é essa metade que a inversão origem↔destino
    quebra sem mudar status nenhum. A prova é o nome: as duas unidades são semeadas
    com sufixos diferentes, então copiar a pessoa errada troca o nome da resposta.
    """
    copia = resposta.json()
    assert copia["unit_id"] == recursos.unidade_destino

    listagem = await client.get(f"{API}/units/{recursos.unidade}/employees", headers=cabecalho)
    original = next(item for item in listagem.json() if item["id"] == recursos.employee_id)
    assert copia["name"] == original["name"]


@dataclass(frozen=True)
class Rota:
    """Como invocar uma rota contra recursos vivos, e o que ela promete.

    Attributes:
        path: os valores de path, a partir dos recursos semeados.
        query: os parâmetros de query que a rota exige.
        body: o corpo válido, ou `None` quando a rota não tem corpo.
        sucesso: o status de sucesso da tabela do concept §4.1, **transcrito à
            mão** — derivá-lo de `rota.status_code` provaria só que o código
            concorda consigo mesmo.
        efeito: como se observa que o efeito recaiu sobre a unidade do path
            (CA11). `None` nas rotas de catálogo, que não têm unidade.
    """

    path: Callable[[Recursos], dict[str, str]]
    query: Callable[[Recursos], dict[str, str]]
    body: Callable[[Recursos], dict[str, Any] | None]
    sucesso: HTTPStatus
    efeito: Efeito | None = None


def _sem_path(_recursos: Recursos) -> dict[str, str]:
    return {}


def _sem_query(_recursos: Recursos) -> dict[str, str]:
    return {}


def _sem_corpo(_recursos: Recursos) -> dict[str, Any] | None:
    return None


def _do_funcionario(recursos: Recursos) -> dict[str, str]:
    return {"unit_id": recursos.unidade, "employee_id": recursos.employee_id}


_EMPLOYEES: Final = "/units/{unit_id}/employees"

ROTAS: dict[ChaveDeRota, Rota] = {
    # --- RJF: catálogo, tenant-scoped, sem unidade no endereço ---------------
    ("POST", "/job-functions"): Rota(
        path=_sem_path,
        query=_sem_query,
        body=lambda r: {"name": f"Garçom {r.sufixo}"},
        sucesso=HTTPStatus.CREATED,
    ),
    ("GET", "/job-functions"): Rota(
        path=_sem_path, query=_sem_query, body=_sem_corpo, sucesso=HTTPStatus.OK
    ),
    ("PATCH", "/job-functions/{job_function_id}"): Rota(
        path=lambda r: {"job_function_id": r.job_function_id},
        query=_sem_query,
        body=lambda r: {"name": f"Chefe de salão {r.sufixo}"},
        sucesso=HTTPStatus.OK,
    ),
    ("DELETE", "/job-functions/{job_function_id}"): Rota(
        path=lambda r: {"job_function_id": r.job_function_livre},
        query=_sem_query,
        body=_sem_corpo,
        sucesso=HTTPStatus.NO_CONTENT,
    ),
    # --- REMP: funcionário, unit-scoped, unidade no path --------------------
    ("POST", _EMPLOYEES): Rota(
        path=lambda r: {"unit_id": r.unidade},
        query=_sem_query,
        body=lambda r: {
            "name": f"Novato {r.sufixo}",
            "workload_profile": {"type": "on_demand"},
            "job_function_ids": [r.job_function_id],
        },
        sucesso=HTTPStatus.CREATED,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("GET", _EMPLOYEES): Rota(
        path=lambda r: {"unit_id": r.unidade},
        query=_sem_query,
        body=_sem_corpo,
        sucesso=HTTPStatus.OK,
        efeito=_efeito_listagem_so_da_unidade_do_path,
    ),
    ("PATCH", f"{_EMPLOYEES}/{{employee_id}}"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda r: {"name": f"Renomeado {r.sufixo}"},
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("PUT", f"{_EMPLOYEES}/{{employee_id}}/job-functions"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda r: {"job_function_ids": [r.job_function_id]},
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("PUT", f"{_EMPLOYEES}/{{employee_id}}/workload-profile"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda _r: {"workload_profile": {"type": "fixed", "weekly_hours": "30.00"}},
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("PUT", f"{_EMPLOYEES}/{{employee_id}}/shift-preference"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda _r: {"shift_preference": ["morning"]},
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("POST", f"{_EMPLOYEES}/{{employee_id}}/unavailabilities"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda _r: dict(_PERIODO_NOVO),
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("DELETE", f"{_EMPLOYEES}/{{employee_id}}/unavailabilities"): Rota(
        path=_do_funcionario,
        query=lambda _r: dict(_PERIODO_SEMEADO),
        body=_sem_corpo,
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("POST", f"{_EMPLOYEES}/{{employee_id}}/termination"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=_sem_corpo,
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("POST", f"{_EMPLOYEES}/{{employee_id}}/rehire"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=_sem_corpo,
        sucesso=HTTPStatus.OK,
        efeito=_efeito_no_registro_da_unidade_do_path,
    ),
    ("DELETE", f"{_EMPLOYEES}/{{employee_id}}"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=_sem_corpo,
        sucesso=HTTPStatus.NO_CONTENT,
        efeito=_efeito_removido_da_unidade_do_path,
    ),
    ("POST", f"{_EMPLOYEES}/{{employee_id}}/copies"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda r: {"target_unit_id": r.unidade_destino},
        sucesso=HTTPStatus.CREATED,
        efeito=_efeito_copia_lida_da_unidade_do_path,
    ),
    # Stage 3.5 — R17. O e-mail leva o **sufixo** do cenário: a unicidade é global
    # em identity, e duas células que semeiem recursos lado a lado (CA11, CA12)
    # colidiriam num e-mail fixo. Canal `link` para que nenhum e-mail saia no
    # cenário da matriz — o canal `email` é do e2e de fluxo (Task 12).
    ("POST", f"{_EMPLOYEES}/{{employee_id}}/login"): Rota(
        path=_do_funcionario,
        query=_sem_query,
        body=lambda r: {"email": f"login-{r.sufixo}@cantina.com", "delivery": "link"},
        sucesso=HTTPStatus.CREATED,
        efeito=_efeito_login_no_registro_da_unidade_do_path,
    ),
}

# Os dois subconjuntos que o concept §4.1 nomeia, **derivados** do template da
# rota: REMP é o que carrega a unidade no endereço; `_COM_EMPLOYEE_ID` é o que
# endereça um registro, e é sobre ele que a metade 404 de CA13 se aplica.
REMP: Final = tuple(sorted(c for c in ROTAS if "{unit_id}" in c[1]))
_COM_EMPLOYEE_ID: Final = tuple(sorted(c for c in ROTAS if "{employee_id}" in c[1]))
RJF: Final = tuple(sorted(c for c in ROTAS if "{unit_id}" not in c[1]))


def _id_da_rota(chave_da_rota: ChaveDeRota) -> str:
    return f"{chave_da_rota[0]}{chave_da_rota[1]}"


# ---------------------------------------------------------------------------
# Totalidade e cardinalidade — as guardas que impedem o verde vazio
# ---------------------------------------------------------------------------


def test_a_declaracao_de_rotas_e_total_sobre_o_router() -> None:
    """Rota sem declaração **reprova**, e é isso que faz a matriz crescer sozinha.

    Sem esta asserção, uma 17ª rota entraria muda em CA08, CA09, CA12 e CA36: os
    `parametrize` continuariam com 16 casos, todos verdes, e a rota nova nunca
    teria sido submetida a papel nenhum.
    """
    registradas = {chave(rota) for rota in _rotas()}

    assert set(ROTAS) == registradas
    assert len(ROTAS) == _TOTAL_DE_ROTAS


def test_os_subconjuntos_da_matriz_tem_a_cardinalidade_declarada() -> None:
    """Conjunto derivado sem contagem é conjunto que ninguém percebe esvaziar.

    Foi assim que CA30 quase passou vazio na Task 09: a asserção universal estava
    certa e o domínio estava vazio. Aqui as três partições declaram o seu tamanho.
    """
    assert len(RJF) == _TOTAL_DE_RJF, RJF
    assert len(REMP) == _TOTAL_DE_REMP, REMP
    assert len(_COM_EMPLOYEE_ID) == _TOTAL_COM_EMPLOYEE_ID, _COM_EMPLOYEE_ID
    assert set(RJF) | set(REMP) == set(ROTAS)
    assert set(RJF) & set(REMP) == set()


def test_os_produtos_cartesianos_tem_o_tamanho_que_os_criterios_exigem() -> None:
    """CA09 são **32** casos e CA36 são **48** — a contagem é parte do critério.

    Um `parametrize` que perdesse um papel continuaria verde com metade dos casos.
    A exigência numérica é o que separa "o produto foi exercitado" de "algum
    subconjunto dele foi".
    """
    assert len(_PAPEIS_SEM_PERMISSAO) * len(ROTAS) == _CASOS_DE_CA09
    assert len(_PAPEIS_COM_PERMISSAO) * len(ROTAS) == _CASOS_DE_CA36


# ---------------------------------------------------------------------------
# Atores — provisionados **pela API**, com os tokens que a aplicação emite
# ---------------------------------------------------------------------------


async def _criar_ator(
    client: AsyncClient, cenario: Cenario, email: str, papel: str, unidades: tuple[str, ...]
) -> dict:
    """Cria um usuário pelo `owner` e devolve o par de tokens do seu login."""
    resposta = await client.post(
        f"{API}/users",
        json={
            "email": email,
            "password": SENHA_PADRAO,
            "role": papel,
            "unit_ids": list(unidades),
        },
        headers=auth(cenario.owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return await fazer_login(client, email)


@pytest.fixture
def owner(cenario: Cenario) -> dict:
    return cenario.owner


@pytest.fixture
def manager(cenario: Cenario) -> dict:
    return cenario.manager


@pytest.fixture
async def hr(client: AsyncClient, cenario: Cenario) -> dict:
    """`hr` membro das **duas** unidades — o gêmeo do `manager` do cenário.

    A paridade de membership é pré-condição de CA12: um `hr` com menos unidades
    faria a igualdade de status falhar por visibilidade, e o teste acusaria a
    decisão do ADR 3.4.0006 §1 de um defeito que seria da fixture.
    """
    return await _criar_ator(
        client, cenario, "rh@cantina.com", "hr", (cenario.unidade_a, cenario.unidade_b)
    )


@pytest.fixture
async def gerente_de_a(client: AsyncClient, cenario: Cenario) -> dict:
    """`manager` membro **só** de A — o ator sem o qual CA13 não tem como acontecer.

    O `manager` do cenário é membro das duas unidades de propósito (CA26), então
    ele não pode provar a recusa por unidade não-membro. Este pode.
    """
    return await _criar_ator(
        client, cenario, "gerente-a@cantina.com", "manager", (cenario.unidade_a,)
    )


@pytest.fixture
async def funcionario_ator(client: AsyncClient, cenario: Cenario) -> dict:
    """Ator de papel `employee`: autenticado, e **sem nenhuma** permissão de staff."""
    return await _criar_ator(
        client, cenario, "funcionario@cantina.com", "employee", (cenario.unidade_a,)
    )


@pytest.fixture
async def platform_admin(client: AsyncClient, cenario: Cenario) -> dict:
    """O `platform_admin` semeado, autenticado pela API.

    Ele **não tem tenant** (ADR 2.1.0002), e por isso é negado duas vezes: não
    detém as permissões de staff, e L-AG3 recusa ator sem tenant no tradutor. As
    duas recusas produzem o mesmo 403 de corpo constante, que é o desejado.
    """
    return await fazer_login(client, ADMIN_EMAIL)


# ---------------------------------------------------------------------------
# Semeadura e invocação
# ---------------------------------------------------------------------------


async def _criar_funcao(client: AsyncClient, cabecalho: dict[str, str], nome: str) -> str:
    resposta = await client.post(f"{API}/job-functions", json={"name": nome}, headers=cabecalho)
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["id"])


async def _semear(
    client: AsyncClient, cenario: Cenario, unidade: str, destino: str, sufixo: str
) -> Recursos:
    """Cria, **pelo `owner`**, tudo o que uma invocação bem-sucedida encontra.

    Semear pelo `owner` — e não pelo ator sob teste — mantém os dois eixos
    separados: um 403 de CA09 tem de vir da rota medida, e não da incapacidade do
    ator de montar o próprio cenário.
    """
    cabecalho = auth(cenario.owner)
    job_function_id = await _criar_funcao(client, cabecalho, f"Função {sufixo}")
    job_function_livre = await _criar_funcao(client, cabecalho, f"Função livre {sufixo}")

    criado = await client.post(
        f"{API}/units/{unidade}/employees",
        json={
            "name": f"Fulano {sufixo}",
            "workload_profile": {"type": "on_demand"},
            "job_function_ids": [job_function_id],
        },
        headers=cabecalho,
    )
    assert criado.status_code == HTTPStatus.CREATED, criado.text
    employee_id = str(criado.json()["id"])

    # O período que R12 remove por igualdade de valor. Sem ele, R12 responderia
    # 422 (`UnavailabilityNotFoundError`) e CA10/CA36 mediriam a ausência do dado
    # em vez do alcance do papel.
    marcado = await client.post(
        f"{API}/units/{unidade}/employees/{employee_id}/unavailabilities",
        json=dict(_PERIODO_SEMEADO),
        headers=cabecalho,
    )
    assert marcado.status_code == HTTPStatus.OK, marcado.text

    return Recursos(
        unidade=unidade,
        unidade_destino=destino,
        employee_id=employee_id,
        job_function_id=job_function_id,
        job_function_livre=job_function_livre,
        sufixo=sufixo,
    )


def _url(chave_da_rota: ChaveDeRota, recursos: Recursos, *, sobrescreve: dict[str, str]) -> str:
    """Monta a URL concreta, com os parâmetros de path percent-encoded."""
    _, template = chave_da_rota
    valores = {**ROTAS[chave_da_rota].path(recursos), **sobrescreve}
    caminho = template
    for nome, valor in valores.items():
        caminho = caminho.replace(f"{{{nome}}}", urllib.parse.quote(valor, safe=""))
    return f"{API}{caminho}"


async def _invocar(
    client: AsyncClient,
    chave_da_rota: ChaveDeRota,
    recursos: Recursos,
    *,
    cabecalho: dict[str, str] | None = None,
    path: dict[str, str] | None = None,
) -> Response:
    """Invoca a rota com corpo e query **válidos**, salvo o que o teste sobrescreve.

    O corpo válido não é conforto: com corpo ausente, uma rota com corpo
    obrigatório responderia 422 pelo `RequestValidationError` do framework, e um
    critério de acesso que esperasse 401/403 ficaria vermelho — ou, pior, um que
    esperasse "não é 2xx" ficaria verde pela razão errada.
    """
    metodo, _ = chave_da_rota
    rota = ROTAS[chave_da_rota]
    return await client.request(
        metodo,
        _url(chave_da_rota, recursos, sobrescreve=path or {}),
        params=rota.query(recursos),
        json=rota.body(recursos),
        headers=cabecalho or {},
    )


@pytest.fixture
async def recursos_em_a(client: AsyncClient, cenario: Cenario) -> Recursos:
    """O conjunto padrão: função, função livre, funcionário e período, na unidade A."""
    return await _semear(client, cenario, cenario.unidade_a, cenario.unidade_b, "a")


# ---------------------------------------------------------------------------
# CA08 — sem Bearer, 401 em todas as 16
# ---------------------------------------------------------------------------

# Recursos fictícios: CA08 não chega ao banco. A autenticação é `Depends` e o
# FastAPI a resolve **antes** de o handler rodar, então nenhum identificador do
# path precisa existir — e não deve, porque um 401 que dependesse do estado do
# banco não seria a propriedade que §5.1 promete.
_RECURSOS_FICTICIOS: Final = Recursos(
    unidade="unidade-fictícia",
    unidade_destino="outra-unidade-fictícia",
    employee_id="funcionário-fictício",
    job_function_id="função-fictícia",
    job_function_livre="função-livre-fictícia",
    sufixo="401",
)


@pytest.mark.parametrize("chave_da_rota", sorted(ROTAS), ids=_id_da_rota)
async def test_ca08_toda_rota_sem_bearer_recebe_401(
    client: AsyncClient, chave_da_rota: ChaveDeRota
) -> None:
    """CA08 — 401 com corpo constante e `WWW-Authenticate: Bearer`, nas **17**.

    O domínio é `router.routes`, não uma amostra: "nenhuma rota de staff é
    pública" (§5.1) é uma lei universal, e uma lei universal travada em duas rotas
    é a família de defeito que esta Stage existe, em parte, para matar.

    **O corpo é o de identity, byte a byte.** É consequência de L-AG1: o tradutor
    do `AccessGuard` não captura, então `InvalidAccessTokenError` sobe crua e é o
    handler de identity que responde. Um corpo próprio de staff aqui significaria
    que alguém traduziu a exceção — e criaria uma faixa 401 distinguível entre os
    dois BCs, que é exatamente o oráculo que a ausência de `try/except` compra.
    """
    resposta = await _invocar(client, chave_da_rota, _RECURSOS_FICTICIOS)

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED, resposta.text
    assert resposta.json() == _CORPO_401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# §5.1 — autenticar antes de validar o corpo, em **toda** rota com entrada
# ---------------------------------------------------------------------------
#
# **CA08 não alcança esta lei, e a diferença é o corpo.** Ele invoca as 17 rotas
# com a entrada **válida** da declaração, então o 422 do framework nunca compete
# com o 401 — e um handler que autenticasse no próprio corpo passaria em CA08
# inteiro. A lei de §5.1 é sobre a **corrida** entre os dois: sem credencial, a
# falha é 401 mesmo com entrada que não casa o schema, senão um cliente sem
# credencial nenhuma sonda a forma do payload de rotas protegidas.
#
# Estava travada **à mão em uma rota de nove** — `POST /job-functions`, em
# `test_http_router_job_functions.py`. Medido: trocar `actor: CurrentActor` por
# `request: Request` + `guard.authenticate(request)` na primeira linha de
# `create_employee` sobrevivia à suíte inteira, e a app real passava a responder
# 422 `validation_error` onde o contrato promete 401 `unauthorized`.
#
# O domínio é **derivado do router**, não listado: uma rota nova com corpo entra
# sozinha. `include_inactive` fica de fora porque tem default — omiti-lo não
# produz 422, e um caso que não degrada não mede a corrida.

# Dez até a 3.6; R17 (3.5) tem corpo — onze.
_TOTAL_DE_ROTAS_COM_ENTRADA: Final = 11

# O corpo que nenhum `*Request` aceita. Não é um campo com valor errado: é a
# **ausência** dos campos obrigatórios, que é o 422 mais barato de produzir e o
# único que não depende da forma de nenhum schema em particular.
_CORPO_FORA_DE_QUALQUER_SCHEMA: Final = {"campo-que-nenhum-request-declara": "x"}

# O corpo constante do handler compartilhado (`shared/infrastructure/http`).
# Transcrito, como os de identity: é o contrato que o cliente recebe, e
# perguntá-lo ao módulo sob teste faria a expectativa seguir o defeito.
_CORPO_422: Final = {"detail": "requisição inválida", "type": "validation_error"}


def _rota_de(chave_da_rota: ChaveDeRota) -> APIRoute:
    """A `APIRoute` registrada para uma chave — a ponte da declaração ao framework."""
    return next(rota for rota in _rotas() if chave(rota) == chave_da_rota)


def _tem_corpo(rota: APIRoute) -> bool:
    """Se a rota declara corpo — `body_field` é o que o FastAPI montou para ele."""
    return rota.body_field is not None


def _tem_query_obrigatoria(rota: APIRoute) -> bool:
    """Se algum parâmetro de query da rota é obrigatório.

    Derivado do `dependant`, e não da assinatura crua: é o framework quem separa
    parâmetro de query de dependência resolvida por `Depends`, e as duas aparecem
    lado a lado na assinatura do handler.
    """
    return any(parametro.field_info.is_required() for parametro in rota.dependant.query_params)


ROTAS_COM_ENTRADA: Final = tuple(
    sorted(chave(rota) for rota in _rotas() if _tem_corpo(rota) or _tem_query_obrigatoria(rota))
)


async def _invocar_com_entrada_degradada(
    client: AsyncClient, chave_da_rota: ChaveDeRota, *, cabecalho: dict[str, str] | None = None
) -> Response:
    """Invoca a rota com a entrada **deliberadamente degradada**, e nada mais.

    Corpo trocado pelo que nenhum schema aceita; query obrigatória **omitida**. É
    a única forma de o 422 do framework existir para competir com o 401 — e é o
    que separa esta varredura de CA08, que invoca com a entrada válida.
    """
    rota = _rota_de(chave_da_rota)
    metodo, _ = chave_da_rota
    return await client.request(
        metodo,
        _url(chave_da_rota, _RECURSOS_FICTICIOS, sobrescreve={}),
        params={}
        if _tem_query_obrigatoria(rota)
        else ROTAS[chave_da_rota].query(_RECURSOS_FICTICIOS),
        json=_CORPO_FORA_DE_QUALQUER_SCHEMA if _tem_corpo(rota) else None,
        headers=cabecalho or {},
    )


def test_o_dominio_das_rotas_com_entrada_tem_a_cardinalidade_declarada() -> None:
    """Dez rotas com corpo e uma com query obrigatória — **onze**, e a contagem é a prova.

    Um `_tem_corpo` que parasse de encontrar `body_field` esvaziaria o
    `parametrize` e deixaria a lei verde sobre conjunto nenhum. E travar a
    contagem em dez é o que faz uma rota nova com corpo **reprovar** aqui até que
    alguém confirme que ela entrou na varredura — o mesmo mecanismo da totalidade
    de `ROTAS`.
    """
    assert len(ROTAS_COM_ENTRADA) == _TOTAL_DE_ROTAS_COM_ENTRADA, ROTAS_COM_ENTRADA
    assert set(ROTAS_COM_ENTRADA) <= set(ROTAS)
    assert ("POST", _EMPLOYEES) in ROTAS_COM_ENTRADA
    assert ("DELETE", f"{_EMPLOYEES}/{{employee_id}}/unavailabilities") in ROTAS_COM_ENTRADA


@pytest.mark.parametrize("chave_da_rota", ROTAS_COM_ENTRADA, ids=_id_da_rota)
async def test_a_entrada_degradada_de_cada_rota_e_de_fato_recusada_pelo_schema(
    client: AsyncClient, cenario: Cenario, chave_da_rota: ChaveDeRota
) -> None:
    """A guarda anti-vácuo da lei abaixo: a degradação **produz** o 422 concorrente.

    Sem esta metade, um corpo que por acaso satisfizesse o schema faria o teste de
    §5.1 provar apenas o que CA08 já prova — 401 numa requisição sem nada de
    errado além da credencial. O que se cobra aqui é que o mesmo par
    (URL, entrada) tenha **duas** respostas possíveis, e que a ordem entre elas
    seja o que a lei decide.

    O ator é um `manager` com as duas permissões: o 422 tem de vir da **forma**,
    e não de uma recusa de acesso que chegaria antes.
    """
    resposta = await _invocar_com_entrada_degradada(
        client, chave_da_rota, cabecalho=auth(cenario.manager)
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resposta.text
    assert resposta.json() == _CORPO_422, resposta.text


@pytest.mark.parametrize("chave_da_rota", ROTAS_COM_ENTRADA, ids=_id_da_rota)
async def test_a_autenticacao_roda_antes_da_validacao_da_entrada_em_toda_rota(
    client: AsyncClient, chave_da_rota: ChaveDeRota
) -> None:
    """§5.1 sobre o domínio quantificado real — **toda** rota com corpo ou query.

    A mesma requisição que o teste acima mostra ser um 422 legítimo responde
    **401** quando falta a credencial: é a autenticação como `Depends`, que o
    FastAPI resolve antes de validar o corpo contra o schema. Autenticar no corpo
    do handler inverte a ordem, e o cliente sem credencial nenhuma passa a
    distinguir payload aceito de payload recusado em rota protegida.

    O corpo é o de identity, byte a byte, pela mesma razão de CA08: L-AG1 proíbe
    traduzir, então `InvalidAccessTokenError` sobe crua do port e é o handler de
    identity que responde.
    """
    resposta = await _invocar_com_entrada_degradada(client, chave_da_rota)

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED, resposta.text
    assert resposta.json() == _CORPO_401, resposta.text
    assert resposta.headers["WWW-Authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# CA09 e CA29 — os dois papéis sem permissão, 403 nas 16
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", _PAPEIS_SEM_PERMISSAO)
@pytest.mark.parametrize("chave_da_rota", sorted(ROTAS), ids=_id_da_rota)
async def test_ca09_papel_sem_permissao_recebe_403_na_rota(  # noqa: PLR0913
    # A aridade é a do produto cartesiano: um cliente, o estado semeado, um
    # ator por papel do eixo, e as duas coordenadas do caso. Agrupar os atores
    # num objeto esconderia as fixtures que os provisionam — e é a lista de
    # fixtures que declara, na assinatura, o que este teste precisa que exista.
    client: AsyncClient,
    recursos_em_a: Recursos,
    funcionario_ator: dict,
    platform_admin: dict,
    papel: str,
    chave_da_rota: ChaveDeRota,
) -> None:
    """CA09 — produto `{employee, platform_admin} x R01…R17`: **34 casos**.

    **Os recursos existem**, e é isso que separa 403 de 404: se o funcionário e a
    função não estivessem semeados, metade destas rotas poderia responder 404 por
    ausência de registro e o teste passaria sem nunca exercitar a autorização.

    Os dois papéis são negados por razões **diferentes** e produzem a **mesma**
    resposta, que é a propriedade desejada: `employee` não detém as permissões de
    staff; `platform_admin` também não, e ainda por cima não tem tenant (L-AG3).
    Um corpo que distinguisse os dois casos seria um oráculo sobre a conta.
    """
    tokens = {"employee": funcionario_ator, "platform_admin": platform_admin}[papel]

    resposta = await _invocar(client, chave_da_rota, recursos_em_a, cabecalho=auth(tokens))

    assert resposta.status_code == HTTPStatus.FORBIDDEN, resposta.text
    assert resposta.json() == _CORPO_403


async def test_ca29_o_employee_recebe_403_ao_criar_funcao_e_ao_listar_funcionarios(
    client: AsyncClient, cenario: Cenario, funcionario_ator: dict
) -> None:
    """CA29 — as duas rotas que a issue #43 nomeia, pela API real.

    É um subconjunto de CA09 e existe assim mesmo: o critério nomeia estas duas
    rotas literalmente, e um teste que só existisse como célula de um produto de
    32 não deixaria rastro de que a exigência específica foi atendida.
    """
    cabecalho = auth(funcionario_ator)

    criacao = await client.post(f"{API}/job-functions", json={"name": "Garçom"}, headers=cabecalho)
    listagem = await client.get(f"{API}/units/{cenario.unidade_a}/employees", headers=cabecalho)

    assert criacao.status_code == HTTPStatus.FORBIDDEN, criacao.text
    assert listagem.status_code == HTTPStatus.FORBIDDEN, listagem.text
    assert criacao.json() == _CORPO_403
    assert listagem.json() == _CORPO_403


# ---------------------------------------------------------------------------
# CA10, CA11 e CA36 — os três papéis com permissão alcançam as 16
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", _PAPEIS_COM_PERMISSAO)
@pytest.mark.parametrize("chave_da_rota", sorted(ROTAS), ids=_id_da_rota)
async def test_ca10_ca11_ca36_papel_com_permissao_alcanca_a_rota(  # noqa: PLR0913
    # A aridade é a do produto cartesiano: um cliente, o estado semeado, um
    # ator por papel do eixo, e as duas coordenadas do caso. Agrupar os atores
    # num objeto esconderia as fixtures que os provisionam — e é a lista de
    # fixtures que declara, na assinatura, o que este teste precisa que exista.
    client: AsyncClient,
    recursos_em_a: Recursos,
    owner: dict,
    manager: dict,
    hr: dict,
    papel: str,
    chave_da_rota: ChaveDeRota,
) -> None:
    """Produto `{owner, manager, hr} x R01…R17` — **51 casos**, e três critérios.

    - **CA10** é a linha do `manager`: nenhuma das 16 responde 401 ou 403. Era o
      critério que a fork F1 reprovava; desde o ADR 0.0.0005 é o teste de
      não-regressão do alcance. Antes da Task 01, **todas** as 48 células eram 403.
    - **CA11**, primeira metade: a linha do `owner`. Ele não é membro de unidade
      nenhuma — o bypass é por papel, no passo 5 do guard —, então alcançar
      `/units/A/...` já é "alcançar unidade da qual não é membro". A segunda
      metade (o efeito recai sobre a unidade do path) é o teste seguinte.
    - **CA36**: `TenantScopeRequiredError` responde **403**, com o mesmo corpo
      constante de qualquer outra recusa. Não há como distingui-lo pela resposta —
      e não deve haver. O que se assere é o contrapositivo: para os três papéis que
      detêm permissão, **nenhuma** das 17 rotas produz 403 de espécie alguma. Se o
      tradutor deixasse de resolver o tenant (ADR 0.0.0005 cláusula 3), as 48
      células ficariam vermelhas de uma vez.

    A asserção é o **status de sucesso declarado**, e não "diferente de 401/403":
    o estado é semeado para que cada rota possa de fato ter sucesso, e aceitar um
    404 aqui deixaria passar uma rota que responde sem alcançar registro nenhum.
    """
    tokens = {"owner": owner, "manager": manager, "hr": hr}[papel]

    resposta = await _invocar(client, chave_da_rota, recursos_em_a, cabecalho=auth(tokens))

    assert resposta.status_code not in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN), (
        f"{papel} foi recusado em {chave_da_rota[1]}: {resposta.status_code} {resposta.text}"
    )
    assert resposta.status_code == ROTAS[chave_da_rota].sucesso, resposta.text


@pytest.mark.parametrize("chave_da_rota", REMP, ids=_id_da_rota)
async def test_ca11_o_efeito_do_owner_recai_sobre_a_unidade_do_path(
    client: AsyncClient, cenario: Cenario, owner: dict, chave_da_rota: ChaveDeRota
) -> None:
    """CA11, segunda metade — parametrizada sobre REMP, com **duas** unidades vivas.

    O `owner` bypassa memberships, e é justamente por isso que ele é o ator certo
    para este critério: se o alcance ampliado dele viesse acompanhado de um alvo
    ampliado, a escrita cairia em qualquer unidade e nenhum critério de alcance
    perceberia. As duas unidades são semeadas com sufixos diferentes, então uma
    operação que lesse a unidade errada devolveria o nome errado.

    A verificação do efeito é **declarada por rota**: as três que não devolvem o
    registro afetado — a listagem, a remoção e a cópia — dizem no `ROTAS` como se
    observa o seu efeito, em vez de ficarem de fora da parametrização.
    """
    recursos_b = await _semear(client, cenario, cenario.unidade_b, cenario.unidade_a, "b")
    await _semear(client, cenario, cenario.unidade_a, cenario.unidade_b, "a")
    cabecalho = auth(owner)

    resposta = await _invocar(client, chave_da_rota, recursos_b, cabecalho=cabecalho)

    assert resposta.status_code == ROTAS[chave_da_rota].sucesso, resposta.text
    efeito = ROTAS[chave_da_rota].efeito
    assert efeito is not None, f"{chave_da_rota[1]} é de REMP e não declarou como observar o efeito"
    await efeito(client, cabecalho, resposta, recursos_b)


# ---------------------------------------------------------------------------
# CA12 — hr ≡ manager
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chave_da_rota", sorted(ROTAS), ids=_id_da_rota)
async def test_ca12_hr_e_manager_produzem_o_mesmo_status_na_rota(
    client: AsyncClient, cenario: Cenario, manager: dict, hr: dict, chave_da_rota: ChaveDeRota
) -> None:
    """CA12 — os dois papéis, a mesma rota, **estados isomorfos**.

    "Sobre o mesmo estado" não pode ser lido como "sobre o mesmo registro": a
    maioria destas rotas **escreve**, e a segunda invocação encontraria o efeito da
    primeira (desligar duas vezes é idempotente, mas apagar duas vezes é 404). O
    que se monta são dois conjuntos **isomorfos** — mesma unidade, mesmas formas,
    nomes distintos —, um por ator. Qualquer divergência de status entre eles é
    divergência de papel, que é o que o ADR 3.4.0006 §1 nega.

    A asserção é dupla de propósito: a igualdade sozinha ficaria verde se os dois
    papéis fossem negados **juntos** — dois 403 são iguais. Exigir também o status
    de sucesso impede que a paridade seja satisfeita pela ausência de acesso.
    """
    recursos_do_manager = await _semear(
        client, cenario, cenario.unidade_a, cenario.unidade_b, "manager"
    )
    recursos_do_hr = await _semear(client, cenario, cenario.unidade_a, cenario.unidade_b, "hr")

    do_manager = await _invocar(client, chave_da_rota, recursos_do_manager, cabecalho=auth(manager))
    do_hr = await _invocar(client, chave_da_rota, recursos_do_hr, cabecalho=auth(hr))

    assert do_manager.status_code == do_hr.status_code, (
        f"{chave_da_rota[1]}: manager={do_manager.status_code} hr={do_hr.status_code}"
    )
    assert do_hr.status_code == ROTAS[chave_da_rota].sucesso, do_hr.text


# ---------------------------------------------------------------------------
# CA13 — isolamento nos dois endereços, com os dois status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("chave_da_rota", _COM_EMPLOYEE_ID, ids=_id_da_rota)
async def test_ca13_o_funcionario_de_outra_unidade_responde_404(
    client: AsyncClient, cenario: Cenario, manager: dict, chave_da_rota: ChaveDeRota
) -> None:
    """CA13, metade 404 — o endereço não casa, e "não casa" é *não existe*.

    O ator é o `manager` das **duas** unidades de propósito: ele enxerga B, então a
    recusa não pode ser explicada por visibilidade. O que a produz é o endereço —
    `find_by_id(tenant, A, id-de-B)` não casa (ADR 3.4.0007 §4) — e é por isso que
    o status é 404 e não 403: um registro que existe noutra unidade do mesmo tenant
    é *não encontrado*, exatamente como o de outro tenant já era.

    O corpo é o de **staff**: quem responde é o handler de `StaffError`, não o de
    identity. Sem essa asserção um 404 do roteador (path que não casa rota nenhuma)
    satisfaria o critério.
    """
    recursos_b = await _semear(client, cenario, cenario.unidade_b, cenario.unidade_a, "b")
    recursos_a = await _semear(client, cenario, cenario.unidade_a, cenario.unidade_b, "a")
    enderecado_por_a = Recursos(
        unidade=recursos_a.unidade,
        unidade_destino=recursos_a.unidade_destino,
        employee_id=recursos_b.employee_id,
        job_function_id=recursos_a.job_function_id,
        job_function_livre=recursos_a.job_function_livre,
        sufixo=recursos_a.sufixo,
    )

    resposta = await _invocar(client, chave_da_rota, enderecado_por_a, cabecalho=auth(manager))

    assert resposta.status_code == HTTPStatus.NOT_FOUND, resposta.text
    assert resposta.json()["type"] == _DISCRIMINADOR_DE_STAFF


@pytest.mark.parametrize("chave_da_rota", REMP, ids=_id_da_rota)
async def test_ca13_a_unidade_da_qual_o_ator_nao_e_membro_responde_403(
    client: AsyncClient,
    cenario: Cenario,
    recursos_em_a: Recursos,
    gerente_de_a: dict,
    chave_da_rota: ChaveDeRota,
) -> None:
    """CA13, primeira metade 403 — a unidade B existe, e o ator não a enxerga.

    Este é o eixo de **visibilidade**, e não o de endereço: a unidade é real, o
    tenant é o mesmo, e o que falta é membership. Quem recusa é o guard, no passo 5
    de `AuthorizeActionUseCase`, com `UnitNotVisibleError` — e o corpo é o
    constante de identity, porque o tradutor não captura (L-AG1).
    """
    resposta = await _invocar(
        client,
        chave_da_rota,
        recursos_em_a,
        cabecalho=auth(gerente_de_a),
        path={"unit_id": cenario.unidade_b},
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN, resposta.text
    assert resposta.json() == _CORPO_403


@pytest.mark.parametrize("chave_da_rota", REMP, ids=_id_da_rota)
async def test_ca13_a_unidade_inexistente_responde_o_mesmo_403_indistinguivel(
    client: AsyncClient,
    recursos_em_a: Recursos,
    gerente_de_a: dict,
    chave_da_rota: ChaveDeRota,
) -> None:
    """CA13, segunda metade 403 — e a indistinguibilidade é o critério, não o status.

    Uma unidade **inexistente** e uma unidade **existente e não visível** produzem
    a mesma resposta byte a byte, porque `UnitNotFoundError` é convertida em
    `UnitNotVisibleError` antes de sair do guard (ADR 2.4.0001 §5). Distinguir as
    duas daria a quem não enxerga a unidade um oráculo para enumerar as unidades
    dos outros restaurantes — que é o mesmo defeito que a Stage 3.4 fechou no eixo
    de funcionário.

    A asserção é sobre o corpo constante inteiro, e não sobre o status: dois 403
    com mensagens diferentes já seriam o oráculo.
    """
    resposta = await _invocar(
        client,
        chave_da_rota,
        recursos_em_a,
        cabecalho=auth(gerente_de_a),
        path={"unit_id": _UNIDADE_INEXISTENTE},
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN, resposta.text
    assert resposta.json() == _CORPO_403

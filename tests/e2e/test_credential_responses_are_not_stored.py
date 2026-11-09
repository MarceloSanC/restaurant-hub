"""Resposta com credencial não fica em cache, pelo HTTP real — issue #61.

**Por que na raiz de `tests/e2e/`.** A regra é da aplicação inteira, não de um
bounded context: hoje são duas rotas de identity e uma de staff, e a próxima pode
ser de qualquer um. É o mesmo nível de `test_deny_by_default.py`.

**Duas partes, uma por critério de aceite.**

1. **As três rotas de hoje, pelo caminho feliz, contra Postgres** — login (200),
   refresh (200) e R17 nos dois canais (201). É o corpo 2xx que carrega o
   segredo, então é nele que os cabeçalhos são cobrados. O canal `email` de R17
   entra também: o link não volta no corpo, mas a política é da rota.
2. **A varredura.** O domínio sai do documento OpenAPI da app real: toda rota
   cujo schema de resposta traz a marca `x-credential`, em qualquer nível. Cada
   uma é chamada com corpo vazio e sem credencial, e a recusa que volta (401 ou
   422) tem de sair sem cache também, porque a política é da rota. Uma rota nova
   com campo marcado entra aqui sem edição, sob qualquer nome de schema.

**O domínio vem do OpenAPI, e não do detector de `shared`.** Perguntar ao código
sob teste o que testar faria a expectativa seguir o defeito: se o detector
deixasse de ver uma forma de schema, a varredura deixaria de cobrá-la junto. O
caminhador daqui é independente, e `test_o_caminhador_e_o_detector_concordam`
cruza os dois sobre as rotas reais, para que nenhum envelheça em silêncio. Rota
escondida do schema (`include_in_schema=False`) sairia desta varredura, e por
isso `test_nenhuma_rota_esta_escondida_do_schema` (`test_deny_by_default.py`) já
a reprova.

**O que esta varredura não pega, declarado.** Um campo de credencial que nasça
**sem** a marca não entra no domínio, e nada aqui o acusa. O resíduo e a razão de
nenhuma forma por rota fechá-lo estão no docstring de
`shared/infrastructure/http/credential_no_store.py`.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import cache
from http import HTTPStatus
from typing import Annotated, Any

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from restaurant_hub.composition_root import build_http_wiring, wire_dependencies
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import API_PREFIX, create_app
from restaurant_hub.shared.infrastructure.http.credential_no_store import declares_credential
from tests.conftest import truncar_tudo
from tests.e2e.features.identity.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    auth,
    corpo_tenant,
    fazer_login,
    login_do_dono,
)
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e

# A marca, transcrita: é contrato do documento OpenAPI, e o teste a lê dali sem
# perguntar ao módulo de `shared` qual é.
_MARCA = "x-credential"

# Os dois cabeçalhos e os valores exatos que a issue #61 pede.
_SEM_CACHE = (("cache-control", "no-store"), ("pragma", "no-cache"))

# As rotas que carregam credencial no corpo hoje. É a guarda de não-vacuidade:
# a varredura tem de encontrá-las, e uma marca removida de qualquer uma reprova
# aqui mesmo que o caminho feliz abaixo também a pegasse.
_ROTAS_DE_HOJE = frozenset(
    {
        ("POST", f"{API}/auth/login"),
        ("POST", f"{API}/auth/refresh"),
        ("POST", f"{API}/units/{{unit_id}}/employees/{{employee_id}}/login"),
    }
)

# Substituto de parâmetro de caminho: a recusa acontece antes de o alvo ser
# procurado, então qualquer valor serve.
_PARAMETRO = "x"


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret_key="segredo-de-teste-e2e-com-32-bytes-ou-mais",
    )


# Banco inexistente de propósito: `create_engine` não abre conexão, e as funções
# que usam esta URL só leem o schema ou chamam rotas plantadas sem banco.
_SEM_BANCO = "postgresql+psycopg://x:x@localhost:1/x"


def _cabecalhos_que_faltam(resposta: httpx.Response) -> list[str]:
    """O que falta para a resposta sair sem cache — vazio é aprovação.

    Exige **um** valor por cabeçalho, e o exato: um `no-store` ao lado de um
    `public, max-age=3600` deixaria a resposta contraditória para quem a lê.
    """
    return [
        f"{nome}: {valor}"
        for nome, valor in _SEM_CACHE
        if resposta.headers.get_list(nome) != [valor]
    ]


# ---------------------------------------------------------------------------
# Parte 1 — as três rotas de hoje, pelo caminho feliz, contra Postgres
# ---------------------------------------------------------------------------


@pytest.fixture
def caixa_de_entrada() -> RecordingEmailSender:
    """O canal `email` de R17 envia; nada sai da máquina (ADR 0.0.0004 §Decision 7)."""
    return RecordingEmailSender()


@pytest.fixture
def app_e2e(engine: Engine, database_url: str, caixa_de_entrada: RecordingEmailSender) -> FastAPI:
    """App real, montada pelo composition root de produção, com banco limpo."""
    truncar_tudo(engine)
    return create_app(_settings(database_url), email_sender=caixa_de_entrada)


@pytest.fixture
async def client(app_e2e: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app_e2e), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def admin_semeado(engine: Engine, app_e2e: FastAPI) -> User:
    """O `platform_admin`, semeado pelo repositório — nenhuma rota o cria."""
    admin = User(
        id=UserId("platform-admin-no-store"),
        email=Email(ADMIN_EMAIL),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )
    PostgresUserRepository(engine).add(admin, Argon2PasswordHasher().hash(SENHA_PADRAO), ())
    return admin


@dataclass(frozen=True)
class Cenario:
    """Um restaurante com uma unidade, o `owner` e dois funcionários sem login."""

    owner: dict[str, Any]
    unidade: str
    funcionarios: tuple[str, str]


async def _criar(client: AsyncClient, caminho: str, corpo: dict[str, Any], tokens: dict) -> str:
    resposta = await client.post(f"{API}{caminho}", json=corpo, headers=auth(tokens))
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["id"])


@pytest.fixture
async def cenario(
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
) -> Cenario:
    """A cadeia inteira pela API: admin → restaurante → owner → unidade → funcionários.

    O `owner` faz R17 porque detém `manage_staff` e `manage_users` e enxerga toda
    unidade do próprio tenant — um `manager` só acrescentaria o vínculo de
    unidade, que não é o que este arquivo mede.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)
    restaurante = await _criar(
        client, "/restaurants", corpo_tenant("Cantina sem cache", "dono-no-store@x.com"), admin
    )
    owner = await login_do_dono(client, caixa_de_entrada, "dono-no-store@x.com")
    unidade = await _criar(client, f"/restaurants/{restaurante}/units", {"name": "Centro"}, owner)
    funcao = await _criar(client, "/job-functions", {"name": "Cozinha"}, owner)

    funcionarios = []
    for nome in ("Ana", "Bruno"):
        resposta = await client.post(
            f"{API}/units/{unidade}/employees",
            json={
                "name": nome,
                "workload_profile": {"type": "on_demand"},
                "job_function_ids": [funcao],
            },
            headers=auth(owner),
        )
        assert resposta.status_code == HTTPStatus.CREATED, resposta.text
        funcionarios.append(str(resposta.json()["id"]))

    return Cenario(owner=owner, unidade=unidade, funcionarios=(funcionarios[0], funcionarios[1]))


async def test_login_responde_sem_cache(client: AsyncClient, admin_semeado: User) -> None:
    resposta = await client.post(
        f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": SENHA_PADRAO}
    )

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert resposta.json()["access_token"]
    assert _cabecalhos_que_faltam(resposta) == []


async def test_refresh_responde_sem_cache(client: AsyncClient, admin_semeado: User) -> None:
    tokens = await fazer_login(client, ADMIN_EMAIL)

    resposta = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert resposta.json()["refresh_token"] != tokens["refresh_token"]
    assert _cabecalhos_que_faltam(resposta) == []


async def test_r17_no_canal_link_responde_sem_cache(client: AsyncClient, cenario: Cenario) -> None:
    """O caso que motivou a issue: o link de definição de senha, válido por 168h."""
    funcionario = cenario.funcionarios[0]

    resposta = await client.post(
        f"{API}/units/{cenario.unidade}/employees/{funcionario}/login",
        json={"email": "ana-no-store@x.com", "delivery": "link"},
        headers=auth(cenario.owner),
    )

    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    assert "token=" in resposta.json()["setup_link"]
    assert _cabecalhos_que_faltam(resposta) == []


async def test_r17_no_canal_email_tambem_responde_sem_cache(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    """Sem o link no corpo, e ainda assim sem cache: a política é da rota, não do valor."""
    funcionario = cenario.funcionarios[1]

    resposta = await client.post(
        f"{API}/units/{cenario.unidade}/employees/{funcionario}/login",
        json={"email": "bruno-no-store@x.com", "delivery": "email"},
        headers=auth(cenario.owner),
    )

    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    assert resposta.json()["setup_link"] is None
    # O primeiro é o convite do dono, que o cenário provisionou (ADR 0.0.0018).
    assert [m.to for m in caixa_de_entrada.sent] == [
        "dono-no-store@x.com",
        "bruno-no-store@x.com",
    ]
    assert _cabecalhos_que_faltam(resposta) == []


async def test_rota_sem_credencial_segue_sem_politica_de_cache(
    client: AsyncClient, cenario: Cenario
) -> None:
    """O controle negativo numa rota real: a listagem de funcionários não é tocada.

    A política de cache das demais rotas é non-goal da issue #61 — "dado de
    equipe não é credencial". Um `no-store` global passaria em todos os testes
    acima deste.
    """
    resposta = await client.get(
        f"{API}/units/{cenario.unidade}/employees", headers=auth(cenario.owner)
    )

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert "cache-control" not in resposta.headers
    assert "pragma" not in resposta.headers


# ---------------------------------------------------------------------------
# Parte 2 — a varredura, com o domínio derivado do documento OpenAPI
# ---------------------------------------------------------------------------


def _resolver(referencia: str, spec: dict[str, Any]) -> object:
    alvo: Any = spec
    for parte in referencia.removeprefix("#/").split("/"):
        alvo = alvo[parte]
    return alvo


def _declara_credencial(no: object, spec: dict[str, Any], vistos: frozenset[str]) -> bool:
    """A marca em qualquer nível, seguindo `$ref` — com memória contra schema recursivo."""
    if isinstance(no, list):
        return any(_declara_credencial(item, spec, vistos) for item in no)
    if not isinstance(no, dict):
        return False
    if no.get(_MARCA) is True:
        return True
    filhos = list(no.values())
    referencia = no.get("$ref")
    if isinstance(referencia, str) and referencia not in vistos:
        # O alvo do `$ref` é mais um filho; a memória impede o laço num schema
        # que referencia a si mesmo.
        vistos = vistos | {referencia}
        filhos.append(_resolver(referencia, spec))
    return any(_declara_credencial(filho, spec, vistos) for filho in filhos)


def _rotas_que_declaram_credencial(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Toda rota cuja resposta documentada traz a marca — o domínio da varredura."""
    return sorted(
        (metodo.upper(), caminho)
        for caminho, operacoes in spec["paths"].items()
        for metodo, operacao in operacoes.items()
        if any(
            _declara_credencial(conteudo.get("schema", {}), spec, frozenset())
            for resposta in operacao.get("responses", {}).values()
            for conteudo in resposta.get("content", {}).values()
        )
    )


@cache
def _spec() -> dict[str, Any]:
    """O schema OpenAPI da app real, sem banco no ar."""
    return create_app(_settings(_SEM_BANCO)).openapi()


def _url(caminho: str) -> str:
    """Substitui os parâmetros de caminho por um valor qualquer."""
    partes = caminho.split("{")
    return partes[0] + "".join(_PARAMETRO + parte.split("}", 1)[1] for parte in partes[1:])


def _identificador(rota: tuple[str, str]) -> str:
    return f"{rota[0]} {rota[1]}"


_COM_CREDENCIAL = _rotas_que_declaram_credencial(_spec())


def test_a_varredura_encontra_as_tres_rotas_de_hoje() -> None:
    """Guarda contra a varredura vacuamente verde, e contra marca removida.

    `parametrize` sobre lista vazia produz zero testes e reporta sucesso. Exigir
    as três rotas de hoje é o piso; rota nova com credencial só aumenta o
    domínio, e não pede edição aqui.
    """
    faltando = sorted(_identificador(rota) for rota in _ROTAS_DE_HOJE - set(_COM_CREDENCIAL))

    assert faltando == [], f"rotas com credencial que a varredura não encontrou: {faltando}"


def test_o_caminhador_e_o_detector_concordam() -> None:
    """O caminhador deste arquivo e o detector de `shared` veem as mesmas rotas.

    Os dois leem a mesma marca por caminhos diferentes: o daqui, o documento
    OpenAPI; o de `shared`, o `response_model` de cada rota. Uma rota que só o
    detector visse sairia desta varredura sem sintoma, e uma que só o caminhador
    visse reprovaria por falta de cabeçalho com um motivo enganoso. O universo é
    o router que o composition root monta, lido direto.
    """
    wiring = build_http_wiring(wire_dependencies(_settings(_SEM_BANCO)))
    pelo_detector = sorted(
        (metodo, f"{API_PREFIX}{rota.path}")
        for router in wiring.routers
        for rota in router.routes
        if isinstance(rota, APIRoute) and declares_credential(rota.response_model)
        for metodo in rota.methods - {"HEAD", "OPTIONS"}
    )

    assert pelo_detector == _COM_CREDENCIAL


@pytest.mark.parametrize("rota", _COM_CREDENCIAL, ids=_identificador)
async def test_rota_que_declara_credencial_responde_sem_cache(
    client: AsyncClient, rota: tuple[str, str]
) -> None:
    """Sem credencial e com corpo vazio, a recusa também sai sem cache.

    A política é da rota, então a resposta de qualquer chamada serve de prova; a
    recusa tem a vantagem de não exigir cenário, e é o que deixa a varredura
    acompanhar rota nova sozinha. Um 500 aqui não é aprovação: o erro não
    tratado é respondido por fora do middleware, e a rota quebrou com corpo vazio.
    """
    metodo, caminho = rota

    resposta = await client.request(metodo, _url(caminho), json={})

    assert resposta.status_code != HTTPStatus.INTERNAL_SERVER_ERROR, resposta.text
    assert _cabecalhos_que_faltam(resposta) == [], (
        f"{_identificador(rota)} declara credencial no schema de resposta e "
        f"respondeu {resposta.status_code} sem {_cabecalhos_que_faltam(resposta)}"
    )


# ---------------------------------------------------------------------------
# Os violadores plantados — a varredura precisa reprovar o que existe para pegar
# ---------------------------------------------------------------------------


class LinkReemitido(BaseModel):
    """O schema que a rota irmã de R17 poderia ter: outro nome, a mesma marca."""

    link: Annotated[str, Field(json_schema_extra={_MARCA: True})]


def _router_de_reemissao() -> APIRouter:
    router = APIRouter()

    @router.post("/sonda/reemitir", response_model=LinkReemitido)
    def reemitir() -> LinkReemitido:
        return LinkReemitido(link="https://x/definir-senha?token=t")

    return router


def _post_que_devolve(schema: str) -> dict[str, Any]:
    """Uma operação `POST` cuja resposta 200 é o schema nomeado, por `$ref`."""
    referencia = {"$ref": f"#/components/schemas/{schema}"}
    resposta = {"content": {"application/json": {"schema": referencia}}}
    return {"post": {"responses": {"200": resposta}}}


def test_a_classificacao_segue_a_marca_e_nao_o_nome() -> None:
    """Um `TokenResponse` sem marca fica de fora; um nome qualquer com a marca entra.

    A marca do schema plantado está **dois `$ref` abaixo** da resposta, porque é
    assim que um envelope novo a esconderia. Uma classificação por nome de
    schema inverteria as duas primeiras rotas. A terceira é um schema que
    referencia a si mesmo, sem marca: a varredura tem de terminar e deixá-lo de
    fora, em vez de seguir o `$ref` para sempre.
    """
    plantado = {
        "paths": {
            "/reemitir": _post_que_devolve("Reemissao"),
            "/impostor": _post_que_devolve("TokenResponse"),
            "/arvore": _post_que_devolve("No"),
        },
        "components": {
            "schemas": {
                "Reemissao": {"properties": {"entrega": {"$ref": "#/components/schemas/Entrega"}}},
                "Entrega": {"properties": {"link": {"type": "string", _MARCA: True}}},
                "TokenResponse": {"properties": {"access_token": {"type": "string"}}},
                "No": {
                    "properties": {
                        "filhos": {"type": "array", "items": {"$ref": "#/components/schemas/No"}}
                    }
                },
            }
        },
    }

    assert _rotas_que_declaram_credencial(plantado) == [("POST", "/reemitir")]


async def test_rota_nova_com_credencial_entra_na_varredura_e_nasce_sem_cache() -> None:
    """É o critério de aceite visto do lado de quem escreve a rota nova.

    A rota plantada entra na app que a fábrica real monta, sem edição em
    `shared` nem neste arquivo, e duas coisas acontecem: ela passa a fazer parte
    do domínio da varredura, e a resposta 2xx dela — a que traria o segredo — sai
    sem cache.
    """
    app = create_app(_settings(_SEM_BANCO))
    app.include_router(_router_de_reemissao(), prefix=API_PREFIX)

    assert ("POST", f"{API_PREFIX}/sonda/reemitir") in _rotas_que_declaram_credencial(app.openapi())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        resposta = await c.post(f"{API_PREFIX}/sonda/reemitir")

    assert resposta.status_code == HTTPStatus.OK
    assert _cabecalhos_que_faltam(resposta) == []


async def test_a_varredura_reprova_rota_com_credencial_sem_o_cabecalho() -> None:
    """A mesma rota, numa app sem o middleware: a varredura a encontra e a recusa.

    Sem isto, um verificador que aprovasse tudo passaria em todos os testes
    acima, porque na app real os cabeçalhos estão lá.
    """
    app = FastAPI()
    app.include_router(_router_de_reemissao(), prefix=API_PREFIX)

    dominio = _rotas_que_declaram_credencial(app.openapi())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        resposta = await c.post(f"{API_PREFIX}/sonda/reemitir")

    assert dominio == [("POST", f"{API_PREFIX}/sonda/reemitir")]
    assert _cabecalhos_que_faltam(resposta) == ["cache-control: no-store", "pragma: no-cache"]


def test_os_parametros_de_caminho_sao_substituidos() -> None:
    """Dois parâmetros, como em R17: um `{x}` literal na URL viraria 404 de rota."""
    url = _url(f"{API}/units/{{unit_id}}/employees/{{employee_id}}/login")

    assert url == f"{API}/units/{_PARAMETRO}/employees/{_PARAMETRO}/login"

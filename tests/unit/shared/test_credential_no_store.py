"""Resposta com credencial não fica em cache — o middleware de `shared` (issue #61).

**Os modelos daqui são plantados, e os nomes não lembram schema real nenhum.** A
detecção tem de seguir a marca `x-credential`, e um teste que usasse
`TokenResponse` não distinguiria "segue a marca" de "segue o nome" — que é
exatamente o defeito que a issue pede para não ter, porque a rota irmã de R17
que vai reemitir o link nascerá com outro schema.

As rotas também são plantadas, numa app sem banco: o que se mede aqui é o
middleware e a detecção, e o HTTP real das três rotas de hoje é do e2e
(`tests/e2e/test_credential_responses_are_not_stored.py`).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Annotated

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field, computed_field
from starlette.types import Message

from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import create_app
from restaurant_hub.shared.infrastructure.http.credential_no_store import (
    CREDENTIAL_MARK,
    CredentialNoStoreMiddleware,
    declares_credential,
)

pytestmark = pytest.mark.unit

# A marca escrita como os schemas de feature a escrevem: por extenso, num alias.
_Segredo = Annotated[str, Field(json_schema_extra={CREDENTIAL_MARK: True})]


class Comprovante(BaseModel):
    """Um nome que nenhuma regra por nome de schema reconheceria."""

    chave: _Segredo
    rotulo: str


class Rotulo(BaseModel):
    rotulo: str


class Envelope(BaseModel):
    interno: Comprovante


class ComprovanteOpcional(BaseModel):
    """A marca num membro de união: o JSON Schema a põe dentro de uma lista (`anyOf`)."""

    chave: _Segredo | None


class LinkDerivado(BaseModel):
    """Credencial calculada: um `computed_field` só existe no schema de serialização."""

    base: str

    @computed_field(json_schema_extra={CREDENTIAL_MARK: True})
    @property
    def link(self) -> str:
        return f"https://x/definir-senha?token={self.base}"


class CampoChamadoComoAMarca(BaseModel):
    """O **nome** do campo é a chave da marca, e o campo não é marcado."""

    model_config = ConfigDict(populate_by_name=True)

    valor: str = Field(alias=CREDENTIAL_MARK)


def _sem_cache(resposta: httpx.Response) -> bool:
    """Os dois cabeçalhos, cada um com **um** valor só, e o valor exato."""
    no_store = resposta.headers.get_list("cache-control") == ["no-store"]
    no_cache = resposta.headers.get_list("pragma") == ["no-cache"]
    return no_store and no_cache


# ---------------------------------------------------------------------------
# A detecção: segue a marca, em qualquer forma de schema
# ---------------------------------------------------------------------------


def test_campo_marcado_declara_credencial_seja_qual_for_o_nome_do_schema() -> None:
    assert declares_credential(Comprovante) is True


def test_schema_sem_marca_nao_declara_credencial() -> None:
    assert declares_credential(Rotulo) is False


def test_rota_sem_schema_de_resposta_nao_declara_credencial() -> None:
    """`None` é o `response_model` de rota `204` ou de `Response` cru."""
    assert declares_credential(None) is False


@pytest.mark.parametrize(
    "forma",
    [
        Envelope,
        list[Comprovante],
        Comprovante | None,
        dict[str, Comprovante],
        ComprovanteOpcional,
    ],
    ids=["aninhado", "lista", "opcional", "dicionario", "membro-de-uniao"],
)
def test_a_marca_e_achada_em_qualquer_forma_do_schema(forma: object) -> None:
    """A marca pode estar num modelo dentro de outro, de uma lista ou de uma união.

    É o que sustenta "independente do nome do schema" de verdade: uma rota que
    embrulhe o segredo num envelope novo continua declarando credencial, e uma
    detecção que olhasse só as propriedades do topo a deixaria passar. O membro de
    união é o caso em que a marca fica **dentro de uma lista** do schema
    (`anyOf`), e não sob `$defs`.
    """
    assert declares_credential(forma) is True


def test_credencial_calculada_conta_porque_a_resposta_e_serializacao() -> None:
    """O schema lido é o de **serialização**, o que a resposta de fato manda.

    Um `computed_field` não existe no schema de validação: lido por ele, um link
    calculado a partir de outro campo sairia como resposta sem credencial.
    """
    assert declares_credential(LinkDerivado) is True


def test_campo_cujo_nome_e_a_chave_da_marca_nao_e_credencial() -> None:
    """A marca é o valor `true` sob a chave, não a presença da chave.

    Um campo chamado `x-credential` vira chave do dicionário `properties`, com um
    schema como valor. Uma detecção por presença da chave o tomaria por
    credencial declarada.
    """
    assert declares_credential(CampoChamadoComoAMarca) is False


# ---------------------------------------------------------------------------
# O middleware, numa app plantada
# ---------------------------------------------------------------------------


def _app_plantada() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CredentialNoStoreMiddleware)

    @app.post("/segredo", response_model=Comprovante)
    def segredo() -> Comprovante:
        return Comprovante(chave="s3gr3do", rotulo="r")

    @app.post("/rotulo", response_model=Rotulo)
    def rotulo() -> Rotulo:
        return Rotulo(rotulo="r")

    @app.post("/segredo-recusado", response_model=Comprovante)
    def segredo_recusado() -> Comprovante:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="recusado")

    @app.post("/segredo-com-corpo", response_model=Comprovante)
    def segredo_com_corpo(corpo: Rotulo) -> Comprovante:
        return Comprovante(chave="s3gr3do", rotulo=corpo.rotulo)

    @app.post("/segredo-com-cache", response_model=Comprovante)
    def segredo_com_cache(response: Response) -> Comprovante:
        response.headers["Cache-Control"] = "public, max-age=3600"
        return Comprovante(chave="s3gr3do", rotulo="r")

    @app.post("/segredo-cru", response_model=Comprovante)
    def segredo_cru() -> JSONResponse:
        return JSONResponse({"chave": "s3gr3do", "rotulo": "r"})

    # O formato de produção: a rota mora num `APIRouter` incluído com prefixo.
    roteador = APIRouter()

    @roteador.post("/segredo", response_model=Comprovante)
    def segredo_no_roteador() -> Comprovante:
        return Comprovante(chave="s3gr3do", rotulo="r")

    app.include_router(roteador, prefix="/api/v1")

    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=_app_plantada()), base_url="http://testserver"
    ) as c:
        yield c


async def test_resposta_de_rota_que_declara_credencial_sai_sem_cache(client: AsyncClient) -> None:
    resposta = await client.post("/segredo")

    assert resposta.status_code == HTTPStatus.OK
    assert _sem_cache(resposta), dict(resposta.headers)


async def test_rota_sem_marca_nao_e_tocada(client: AsyncClient) -> None:
    """A política de cache das demais rotas é non-goal da issue #61.

    É este teste que separa "no-store onde há credencial" de "no-store em tudo":
    o segundo passaria em todos os outros testes deste arquivo.
    """
    resposta = await client.post("/rotulo")

    assert resposta.status_code == HTTPStatus.OK
    assert "cache-control" not in resposta.headers
    assert "pragma" not in resposta.headers


@pytest.mark.parametrize(
    ("caminho", "status_esperado"),
    [
        ("/segredo-recusado", HTTPStatus.UNAUTHORIZED),
        ("/segredo-com-corpo", HTTPStatus.UNPROCESSABLE_ENTITY),
    ],
    ids=["recusa-do-handler", "recusa-da-validacao"],
)
async def test_a_politica_e_da_rota_e_vale_tambem_na_recusa(
    client: AsyncClient, caminho: str, status_esperado: HTTPStatus
) -> None:
    """Os cabeçalhos saem em toda resposta da rota marcada, não só na que traz o segredo.

    A recusa não carrega credencial; o ponto é que a regra é declarada pela rota,
    e uma regra por status teria de adivinhar qual status leva o segredo.
    """
    resposta = await client.post(caminho, json={})

    assert resposta.status_code == status_esperado
    assert _sem_cache(resposta), dict(resposta.headers)


async def test_no_store_substitui_o_cache_que_o_handler_pediu(client: AsyncClient) -> None:
    """Um `Cache-Control` posto pelo handler perde: sai um valor só, e é `no-store`.

    Acrescentar em vez de substituir deixaria `public, max-age=3600` ao lado de
    `no-store` — um par contraditório para quem lê a resposta.
    """
    resposta = await client.post("/segredo-com-cache")

    assert resposta.status_code == HTTPStatus.OK
    assert _sem_cache(resposta), dict(resposta.headers)


async def test_handler_que_devolve_response_cru_tambem_sai_sem_cache(client: AsyncClient) -> None:
    """Um handler que devolve `Response` próprio continua sem cache.

    É o caso que justifica middleware em vez de dependência por rota: o FastAPI
    descarta os cabeçalhos da sub-resposta quando o handler devolve um `Response`.
    Trocar o middleware por `Depends` reprovaria aqui.
    """
    resposta = await client.post("/segredo-cru")

    assert resposta.status_code == HTTPStatus.OK
    assert _sem_cache(resposta), dict(resposta.headers)


async def test_rota_marcada_em_router_incluido_sai_sem_cache(client: AsyncClient) -> None:
    """A rota de produção vem de um `APIRouter` incluído com prefixo, e a regra vale nela."""
    resposta = await client.post("/api/v1/segredo")

    assert resposta.status_code == HTTPStatus.OK
    assert _sem_cache(resposta), dict(resposta.headers)


async def test_rota_inexistente_passa_sem_cabecalho(client: AsyncClient) -> None:
    """Sem rota casada não há `scope["route"]`, e nada a declarar."""
    resposta = await client.post("/nao-existe")

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    assert "cache-control" not in resposta.headers


async def test_a_fabrica_real_registra_o_middleware() -> None:
    """`create_app()` é quem monta a app servida, e é nela que a regra tem de estar.

    Sem isto, remover o `add_middleware` de `register_middlewares` passaria em
    todos os testes acima, que montam a própria app. `create_engine` não abre
    conexão, então a app de produção sobe aqui sem banco.
    """
    app = create_app(Settings(_env_file=None))

    @app.post("/sonda/segredo", response_model=Comprovante)
    def sonda() -> Comprovante:
        return Comprovante(chave="s3gr3do", rotulo="r")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        resposta = await c.post("/sonda/segredo")

    assert resposta.status_code == HTTPStatus.OK
    assert _sem_cache(resposta), dict(resposta.headers)


async def test_o_lifespan_atravessa_o_middleware() -> None:
    """O escopo `lifespan` passa intacto: é por ele que a app sobe e desce.

    O `ASGITransport` do httpx, que os testes acima usam, não envia `lifespan`; o
    servidor de produção envia. Um middleware que só repassasse `http` passaria
    em todos os testes acima e deixaria a app sem subir. O protocolo é dirigido à
    mão porque o `TestClient` do Starlette 1.x com httpx é depreciado.
    """
    eventos: list[str] = []

    @asynccontextmanager
    async def ciclo(_: FastAPI) -> AsyncIterator[None]:
        eventos.append("subiu")
        yield
        eventos.append("desceu")

    app = FastAPI(lifespan=ciclo)
    app.add_middleware(CredentialNoStoreMiddleware)

    recebidas = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    enviadas: list[str] = []

    async def receber() -> Message:
        return next(recebidas)

    async def enviar(mensagem: Message) -> None:
        enviadas.append(mensagem["type"])

    await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receber, enviar)

    assert eventos == ["subiu", "desceu"]
    assert enviadas == ["lifespan.startup.complete", "lifespan.shutdown.complete"]

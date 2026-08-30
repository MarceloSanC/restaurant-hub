"""CA15 — a unidade que chega ao use case é a do **path**, provada por contradição.

## Por que este arquivo precisa de um dublê próprio

A lei da §5.4 do concept fala de **independência** entre duas fontes: o `unit_id`
do path e o `AuthorizedScope.unit_id` devolvido pelo guard. Independência só se
prova fazendo as duas fontes **discordarem** — e as duas implementações do port
que o sistema tem **ecoam** a unidade pedida:

- `_IdentityAccessGuard` devolve `scope_unit_id`, que `AuthorizeActionUseCase`
  monta com `scope_unit_id=command.unit_id`;
- `InMemoryAccessGuard` devolve literalmente o `unit_id` que recebeu.

Com qualquer uma delas, *"o router usou o path"* e *"o router usou o escopo"* são
**o mesmo objeto**: a mutação `unit_id=scope.unit_id` sobrevive, a cobertura
fecha em 100%, e a propriedade nunca foi exercida. O domínio quantificado tem, no
sistema inteiro, um **único** valor observável — então o segundo é **fabricado**,
em `tests/fakes/features/staff/adversarial_access_guard.py`.

## Por que a asserção é sobre o command, e não sobre a resposta

A resposta de uma rota de escrita é montada a partir do `EmployeeResult`, que sai
do use case — e o use case recebe o command. Asserir a resposta mediria a mesma
coisa por um caminho mais longo **quando dá certo**, e mediria nada quando o use
case é um dublê. O que a lei protege é **o que chega ao use case**, e é isso que
o espião registra.

## Por que o domínio sai de `router.routes`

As rotas de funcionário das Tasks 07 e 08 entram nesta trava **sem edição deste
arquivo**: o filtro é "tem `{unit_id}` no path", e as invocações vêm do mesmo
coletor que as varreduras usam. Se uma rota futura ler o escopo em vez do path, é
a **própria** Task que a escreveu que fica vermelha.
"""

import importlib
import typing
import urllib.parse
from functools import partial
from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import OnDemand
from restaurant_hub.shared.infrastructure.http.error_handlers import register_error_handlers
from tests.fakes.features.staff.adversarial_access_guard import (
    UNIDADE_ADVERSARIAL,
    AdversarialAccessGuard,
    ModoAdversarial,
)
from tests.unit.features.staff.adapters.test_http_boundary_sweeps import _INVOCACOES, chave

pytestmark = pytest.mark.unit

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"
router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
dependencies_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.dependencies")
error_handlers_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.error_handlers")

# A unidade que o cliente **pede**. Diferente da que o dublê devolve, e diferente
# da que as outras suítes usam, para que uma confusão de fixture não passe por
# acaso.
_UNIDADE_PEDIDA = "unit-DO-PATH"
_TENANT = "rest-1"


def _rotas_de_funcionario() -> list[APIRoute]:
    """REMP — as rotas cujo path endereça uma unidade. Derivado, não listado."""
    return [
        rota
        for rota in router_module.router.routes
        if isinstance(rota, APIRoute) and "{unit_id}" in rota.path
    ]


class _UseCaseEspiao:
    """Dublê de use case que **registra o command** e devolve um result plausível."""

    def __init__(self, resultado: object) -> None:
        self.recebidos: list[Any] = []
        self._resultado = resultado

    def execute(self, comando: object) -> object:
        self.recebidos.append(comando)
        return self._resultado


_RESULTADO_DE_FUNCIONARIO = EmployeeResult(
    id=EmployeeId("emp-1"),
    tenant_id=TenantId(_TENANT),
    unit_id=UnitId(_UNIDADE_PEDIDA),
    name="Ana",
    workload_profile=OnDemand(),
    shift_preference=None,
    job_function_ids=frozenset(),
    unavailabilities=(),
    active=True,
)


def _resultado_para(anotacao: object) -> object:
    """O valor que o espião devolve, **derivado** do retorno do use case real.

    Sem a derivação, cada Task de rota teria de acrescentar uma linha aqui. Com
    ela, uma rota nova só precisa que o seu use case devolva algo que a borda já
    sabe serializar — e se não devolver, a falha é imediata e nomeada.
    """
    if anotacao is None or anotacao is type(None):
        return None
    if typing.get_origin(anotacao) is tuple:
        return (_RESULTADO_DE_FUNCIONARIO,)
    return _RESULTADO_DE_FUNCIONARIO


def _devolve(instancia: object) -> object:
    """Provedor de override — devolve a instancia ja construida."""
    return instancia


def _montar_app(modo: ModoAdversarial) -> tuple[FastAPI, dict[str, _UseCaseEspiao]]:
    """App real, guard adversarial, e um espião por provedor `_get_*`."""
    guard = AdversarialAccessGuard(tenant_id=_TENANT, modo=modo)

    app = FastAPI()
    register_error_handlers(app)
    error_handlers_module.register_staff_error_handlers(app)
    app.dependency_overrides[dependencies_module.get_access_guard] = lambda: guard

    espioes: dict[str, _UseCaseEspiao] = {}
    for nome, provedor in vars(router_module).items():
        if not nome.startswith("_get_") or not callable(provedor):
            continue
        classe = typing.get_type_hints(provedor)["return"]
        retorno = typing.get_type_hints(classe.execute).get("return")
        espiao = _UseCaseEspiao(_resultado_para(retorno))
        espioes[nome] = espiao
        # `partial`, e nao `lambda`: um lambda no corpo do laco captura a
        # variavel e nao o valor, e todos os overrides devolveriam o ultimo
        # espiao construido — silenciosamente.
        app.dependency_overrides[provedor] = partial(_devolve, espiao)

    app.include_router(router_module.router, prefix="/api/v1")
    return app, espioes


def _url_da_rota(rota: APIRoute) -> str:
    """URL concreta com a unidade **pedida** e os demais parâmetros da invocação."""
    invocacao = _INVOCACOES[chave(rota)]
    valores = {**invocacao.path, "unit_id": _UNIDADE_PEDIDA}
    caminho = rota.path
    for nome, valor in valores.items():
        caminho = caminho.replace(f"{{{nome}}}", urllib.parse.quote(valor, safe=""))
    return f"/api/v1{caminho}"


async def _invocar(client: AsyncClient, rota: APIRoute) -> Response:
    invocacao = _INVOCACOES[chave(rota)]
    metodo, _ = chave(rota)
    return await client.request(
        metodo, _url_da_rota(rota), params=invocacao.query, json=invocacao.body
    )


def _espiao_chamado(espioes: dict[str, _UseCaseEspiao]) -> _UseCaseEspiao:
    """O único espião que recebeu um command — a rota chama exatamente um."""
    chamados = [espiao for espiao in espioes.values() if espiao.recebidos]
    assert len(chamados) == 1, f"a rota consultou {len(chamados)} use cases, e devia consultar 1"
    return chamados[0]


_MODOS = [
    pytest.param(ModoAdversarial.UNIDADE_DIVERGENTE, id="escopo-com-unidade-divergente"),
    pytest.param(ModoAdversarial.SEM_UNIDADE, id="escopo-sem-unidade"),
]
_ROTAS = [
    pytest.param(rota, id=f"{sorted(rota.methods)[0]} {rota.path}")
    for rota in _rotas_de_funcionario()
]


@pytest.mark.parametrize("rota", _ROTAS)
@pytest.mark.parametrize("modo", _MODOS)
async def test_ca15_a_unidade_do_use_case_e_a_do_path(
    rota: APIRoute, modo: ModoAdversarial
) -> None:
    """Para **toda** rota de funcionário, nos **dois** modos do dublê.

    O guard devolve uma unidade que o cliente não pediu (ou nenhuma); o command
    tem de carregar a do path mesmo assim. Um router que lesse o escopo mandaria
    a escrita para outra unidade — e, com o fake sancionado, nenhum teste notaria.
    """
    app, espioes = _montar_app(modo)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resposta = await _invocar(client, rota)

    assert resposta.status_code < HTTPStatus.BAD_REQUEST, (
        f"invocação inválida: {resposta.status_code}"
    )
    comando = _espiao_chamado(espioes).recebidos[0]

    assert comando.unit_id == _UNIDADE_PEDIDA
    assert comando.unit_id != UNIDADE_ADVERSARIAL


@pytest.mark.parametrize("rota", _ROTAS)
async def test_ca15_o_guard_e_consultado_com_a_unidade_do_path(rota: APIRoute) -> None:
    """A **mesma** variável alimenta o guard e o command.

    Dois nomes para um valor é como este defeito volta (ADR 3.6.0001
    §Implementation notes): autorizar a unidade A e escrever na B é escalada de
    escopo silenciosa, e nenhuma das duas asserções sozinha a pega — esta prova
    que o alvo autorizado é o do path, e a de cima prova que o efeito também é.
    """
    app, _ = _montar_app(ModoAdversarial.UNIDADE_DIVERGENTE)
    guard = app.dependency_overrides[dependencies_module.get_access_guard]()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await _invocar(client, rota)

    autorizacoes = [c for c in guard.calls if c.startswith("authorize(")]
    assert autorizacoes, "a rota não autorizou nada"
    assert all(c.endswith(f",{_UNIDADE_PEDIDA})") for c in autorizacoes), autorizacoes


def test_o_dominio_de_ca15_cobre_as_rotas_de_funcionario_existentes() -> None:
    """Sem rotas, a lei passaria por vacuidade — e passaria para sempre.

    A asserção é sobre a **cardinalidade derivada**: toda rota com `{unit_id}` no
    path está na trava, e o número cresce sozinho nas Tasks 07 e 08.
    """
    assert _rotas_de_funcionario()
    assert {rota.path for rota in _rotas_de_funcionario()} == {
        rota.path
        for rota in router_module.router.routes
        if isinstance(rota, APIRoute) and rota.path.startswith("/units/")
    }


def test_o_duble_adversarial_contradiz_de_proposito_o_fake_sancionado() -> None:
    """A premissa deste arquivo, escrita como asserção.

    Se um dia o dublê passasse a **ecoar** a unidade pedida — por refactor
    distraído, ou por alguém "consertando" a estranheza —, todos os testes acima
    continuariam verdes e não provariam mais nada. Esta é a asserção que impede
    isso: o escopo devolvido **tem** de discordar do pedido.
    """
    guard = AdversarialAccessGuard(modo=ModoAdversarial.UNIDADE_DIVERGENTE)
    escopo = guard.authorize(object(), "manage_staff", unit_id=_UNIDADE_PEDIDA)

    assert escopo.unit_id != _UNIDADE_PEDIDA
    assert escopo.unit_id == UNIDADE_ADVERSARIAL

    sem_unidade = AdversarialAccessGuard(modo=ModoAdversarial.SEM_UNIDADE)
    assert sem_unidade.authorize(object(), "manage_staff", unit_id=_UNIDADE_PEDIDA).unit_id is None

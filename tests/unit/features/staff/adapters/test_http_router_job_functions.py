"""Rotas do catálogo de funções de trabalho (R01…R04), pela app FastAPI montada.

Montar a app de verdade — e não chamar as funções de rota diretamente — é o que
faz estes testes exercitarem o caminho completo: `Depends`, guard, validador,
use case, mapa de erro e serialização. Chamar a função nua pularia justamente as
camadas onde um adapter costuma errar.

Os repositórios são fakes; o que se testa aqui é **a rota**, não a persistência.
O caminho com Postgres real é o e2e das Tasks 10 a 12.

## `INVOCACOES` — por que é público, e por que mora aqui

O módulo de varreduras (`test_http_boundary_sweeps.py`) precisa, **por rota**, de
um corpo e uma query **válidos**: sem isso, uma rota com corpo obrigatório
invocada vazia responde 422 pelo `RequestValidationError` do **framework**, e uma
varredura que assere só `status == 422` fica verde mesmo com o validador de
identificador ausente.

Essa declaração vive **no módulo da Task que escreveu a rota**, e as varreduras a
colhem de todos os `test_http_router_*` do pacote. É a mesma disciplina de
"derivar o domínio do código" que governa o resto da Stage, aplicada ao próprio
arranjo dos testes: a Task que acrescenta uma rota declara como invocá-la no seu
próprio arquivo, e a totalidade (`set(_INVOCACOES) == {chave(r) for r in
router.routes}`) reprova quem esquecer. O efeito colateral é que nenhuma Task de
rota precisa editar o módulo de varreduras — a alternativa seria justamente essa,
e ela faria cada Task tocar um arquivo fora da sua lista.
"""

import importlib
import inspect
import typing
from collections.abc import Iterator
from functools import partial
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import OnDemand
from restaurant_hub.shared.infrastructure.http.error_handlers import register_error_handlers
from tests.fakes.features.staff.in_memory_access_guard import (
    FakeActor,
    FakeAuthorizationRejected,
    FakeCredentialRejected,
    InMemoryAccessGuard,
)
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"

router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")
dependencies_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.dependencies")
error_handlers_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.error_handlers")

_TENANT = "rest-1"
_UNIDADE = "unit-1"

# **A declaração de cada rota desta Task** — ver o docstring do módulo. `path`
# traz um valor válido para cada parâmetro de path; `query` e `body` trazem o
# mínimo que a rota aceita sem que o framework recuse a forma.
#
# **`sucesso` é a transcrição manual da tabela do concept §4.1, e a manualidade é
# o ponto.** Derivá-lo de `rota.status_code` provaria apenas que o código
# concorda consigo mesmo; escrito à mão, ele é o contrato externo conferido
# contra a implementação. Mora aqui, junto da invocação, porque as duas coisas
# são a **mesma** declaração: quem acrescenta uma rota declara de uma vez como
# invocá-la e o que a §4.1 promete que ela responde — e a asserção de totalidade
# cobra as duas de uma vez.
INVOCACOES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", "/job-functions"): {
        "path": {},
        "query": {},
        "body": {"name": "Garçom"},
        "sucesso": HTTPStatus.CREATED,
    },
    ("GET", "/job-functions"): {
        "path": {},
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.OK,
    },
    ("PATCH", "/job-functions/{job_function_id}"): {
        "path": {"job_function_id": "jf-1"},
        "query": {},
        "body": {"name": "Garçom Sênior"},
        "sucesso": HTTPStatus.OK,
    },
    ("DELETE", "/job-functions/{job_function_id}"): {
        "path": {"job_function_id": "jf-1"},
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.NO_CONTENT,
    },
}


class Ambiente:
    """App real montada com fakes — o mesmo caminho que o composition root monta.

    **Os `_get_*` são conectados por derivação, e não por lista.** Para cada
    provedor do módulo do router, a anotação de retorno nomeia a classe do use
    case, e o construtor dela pede apenas os três ports que os 16 use cases de
    staff conhecem (`employees`, `job_functions`, `id_generator`). Isso deixa o
    wiring de teste **fechado sob acréscimo de rota**: uma rota escrita numa Task
    seguinte já nasce conectada aqui, e nenhum arquivo desta Task precisa mudar.
    """

    def __init__(self) -> None:
        self.fakes: StaffFakes = staff_repositories()
        self.guard = InMemoryAccessGuard(credential=FakeActor(id="ator-1", tenant_id=_TENANT))
        self.guard.grant("manage_job_functions", tenant_id=_TENANT)
        self.guard.grant("manage_staff", tenant_id=_TENANT, unit_id=_UNIDADE)

        # A ordem espelha `create_app`: genéricos primeiro, de feature depois.
        # **Registrar os genéricos aqui não é zelo** — é o que torna o ambiente
        # capaz de distinguir os dois 422 da app real. Sem o handler de
        # `RequestValidationError` de `shared`, o 422 do framework sai com o corpo
        # **default** do FastAPI, que não tem `type` nenhum: asserir
        # `type == "staff_error"` passaria por ausência de chave em vez de por
        # diferença de origem, e a trava valeria menos do que parece.
        self.app = FastAPI()
        register_error_handlers(self.app)
        error_handlers_module.register_staff_error_handlers(self.app)
        self.app.dependency_overrides.update(
            {dependencies_module.get_access_guard: lambda: self.guard}
        )
        self.app.dependency_overrides.update(overrides_de_use_case(self.fakes))
        self.app.include_router(router_module.router, prefix="/api/v1")

    def com_funcao(self, job_function_id: str = "jf-1", name: str = "Garçom") -> JobFunction:
        funcao = JobFunction(
            id=JobFunctionId(job_function_id), tenant_id=TenantId(_TENANT), name=name
        )
        self.fakes.job_functions.add(funcao)
        return funcao

    def com_funcionario_usando(self, job_function_id: str) -> Employee:
        funcionario = Employee(
            id=EmployeeId("emp-1"),
            tenant_id=TenantId(_TENANT),
            unit_id=UnitId(_UNIDADE),
            name="Ana",
            workload_profile=OnDemand(),
            shift_preference=None,
            job_function_ids=frozenset({JobFunctionId(job_function_id)}),
        )
        self.fakes.employees.add(funcionario)
        return funcionario


def _devolve(instancia: object) -> object:
    """Provedor de override — devolve a instância já construída."""
    return instancia


def overrides_de_use_case(fakes: StaffFakes) -> dict[object, object]:
    """Constrói um override por provedor `_get_*` do router, **derivando** o alvo.

    Cada `_get_*` declara no retorno a classe do use case; cada construtor de use
    case de staff pede um subconjunto de `employees`, `job_functions` e
    `id_generator`. Montar por reflexão em vez de por lista é o que faz este
    ambiente cobrir automaticamente as rotas das Tasks seguintes — e é a mesma
    razão pela qual as varreduras derivam o domínio de `router.routes`.
    """
    disponiveis: dict[str, object] = {
        "employees": fakes.employees,
        "job_functions": fakes.job_functions,
        "id_generator": FakeIdGenerator(),
    }

    construidos: dict[object, object] = {}
    for nome, provedor in vars(router_module).items():
        if not nome.startswith("_get_") or not callable(provedor):
            continue
        classe = typing.get_type_hints(provedor)["return"]
        argumentos = {
            parametro: disponiveis[parametro]
            for parametro in inspect.signature(classe.__init__).parameters
            if parametro in disponiveis
        }
        # `partial` em vez de `lambda`: um `lambda` no corpo do laço captura a
        # variável, não o valor, e todos os overrides devolveriam o último use
        # case construído — o defeito clássico, e aqui ele seria silencioso.
        construidos[provedor] = partial(_devolve, classe(**argumentos))

    assert construidos, "nenhum provedor `_get_*` encontrado no router"
    return construidos


@pytest.fixture
def ambiente() -> Ambiente:
    return Ambiente()


@pytest.fixture
async def client(ambiente: Ambiente) -> Iterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


# ---------------------------------------------------------------------------
# Caminho feliz das quatro rotas
# ---------------------------------------------------------------------------


async def test_r01_cria_funcao_com_201_e_o_tenant_do_escopo(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """O `tenant_id` da resposta é o do **escopo autorizado**, não do corpo.

    O corpo não tem como declará-lo — nenhum schema o aceita —, então a asserção
    prova que a rota o tirou do único lugar de onde pode tirar.
    """
    resposta = await client.post("/api/v1/job-functions", json={"name": "Garçom"})

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["tenant_id"] == _TENANT
    assert resposta.json()["name"] == "Garçom"


async def test_r02_lista_o_catalogo_do_tenant_com_200(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A listagem sai na ordem total de `L-ORD`, consumida e não estendida."""
    ambiente.com_funcao("jf-2", "Cozinheiro")
    ambiente.com_funcao("jf-1", "Garçom")

    resposta = await client.get("/api/v1/job-functions")

    assert resposta.status_code == HTTPStatus.OK
    assert [item["name"] for item in resposta.json()] == ["Cozinheiro", "Garçom"]


async def test_r03_renomeia_funcao_com_200(client: AsyncClient, ambiente: Ambiente) -> None:
    ambiente.com_funcao("jf-1", "Garçom")

    resposta = await client.patch("/api/v1/job-functions/jf-1", json={"name": "Garçom Sênior"})

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json() == {"id": "jf-1", "tenant_id": _TENANT, "name": "Garçom Sênior"}


async def test_r04_remove_funcao_com_204_e_corpo_vazio(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """204 não carrega corpo — um 200 com corpo aqui seria contrato diferente."""
    ambiente.com_funcao("jf-1")

    resposta = await client.delete("/api/v1/job-functions/jf-1")

    assert resposta.status_code == HTTPStatus.NO_CONTENT
    assert resposta.content == b""
    assert ambiente.fakes.job_functions.find_by_id(TenantId(_TENANT), JobFunctionId("jf-1")) is None


# ---------------------------------------------------------------------------
# As três faixas de erro, pelo HTTP real
# ---------------------------------------------------------------------------


async def test_funcao_inexistente_recebe_404_com_o_corpo_de_staff(client: AsyncClient) -> None:
    """404 é a faixa do recurso endereçável ausente **no tenant do ator**."""
    resposta = await client.patch("/api/v1/job-functions/jf-404", json={"name": "X"})

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    assert resposta.json()["type"] == "staff_error"


async def test_nome_repetido_recebe_409_com_o_corpo_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """409 é conflito com estado **já gravado** — a chave existe."""
    ambiente.com_funcao("jf-1", "Garçom")

    resposta = await client.post("/api/v1/job-functions", json={"name": "Garçom"})

    assert resposta.status_code == HTTPStatus.CONFLICT
    assert resposta.json()["type"] == "staff_error"


async def test_funcao_em_uso_recebe_409_e_nao_e_removida(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """O par `InUse` é 409 e não 422: o payload está certo, outro registro impede."""
    ambiente.com_funcao("jf-1")
    ambiente.com_funcionario_usando("jf-1")

    resposta = await client.delete("/api/v1/job-functions/jf-1")

    assert resposta.status_code == HTTPStatus.CONFLICT
    assert resposta.json()["type"] == "staff_error"
    assert (
        ambiente.fakes.job_functions.find_by_id(TenantId(_TENANT), JobFunctionId("jf-1"))
        is not None
    )


async def test_nome_vazio_recebe_422_com_o_corpo_de_staff(client: AsyncClient) -> None:
    """422 é a invariante violada **pelo conteúdo enviado** — e é erro de domínio.

    O discriminador `staff_error` é o que separa este 422 do 422 do
    `RequestValidationError`, que o handler compartilhado renderiza com
    `type: "validation_error"`. Sem ele, a asserção não distinguiria "o domínio
    recusou o nome" de "a forma do corpo não casou o schema".
    """
    resposta = await client.post("/api/v1/job-functions", json={"name": "   "})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_corpo_fora_do_schema_recebe_o_422_do_framework_e_nao_o_de_staff(
    client: AsyncClient,
) -> None:
    """A outra metade da distinção — e é ela que torna a asserção acima refutável.

    Se os dois 422 tivessem o mesmo corpo, asserir `type == "staff_error"` não
    provaria nada. Aqui o corpo **não** casa o schema, e a resposta vem do
    handler compartilhado, com outro discriminador.
    """
    resposta = await client.post("/api/v1/job-functions", json={"nome": "Garçom"})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] != "staff_error"


# ---------------------------------------------------------------------------
# Acesso — o adapter declara, o port decide
# ---------------------------------------------------------------------------


async def test_sem_concessao_a_rota_nao_responde_pelo_handler_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A recusa do port sobe **crua** (L-AG2) e não vira erro de staff.

    O fake levanta a própria sentinela, que não é `StaffError` nem
    `IdentityError`. Em produção quem responde é o handler de identity, com 403 de
    corpo constante — e é por isso que CA08/CA09 vivem no e2e, não aqui: uma
    asserção de status neste ambiente mediria o dublê, não a faixa.
    """
    ambiente.guard.grants.clear()

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        await client.get("/api/v1/job-functions")

    assert excinfo.value is ambiente.guard.authorization_error


async def test_a_autenticacao_roda_antes_da_validacao_do_corpo(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """§5.1: sem credencial, a falha é de autenticação mesmo com corpo inválido.

    Se a autenticação fosse chamada no corpo da rota, o 422 do schema chegaria
    primeiro — e um cliente sem credencial nenhuma passaria a sondar a forma do
    payload de rotas protegidas.
    """
    ambiente.guard.credential = None

    with pytest.raises(FakeCredentialRejected) as excinfo:
        await client.post("/api/v1/job-functions", json={"nome": "fora do schema"})

    assert excinfo.value is ambiente.guard.credential_error


async def test_as_rotas_de_catalogo_autorizam_sem_nomear_unidade(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`manage_job_functions` é tenant-wide: o alvo é o restaurante inteiro.

    A asserção é sobre o **alvo registrado** pelo guard, e não sobre o status: um
    router que nomeasse uma unidade aqui continuaria devolvendo 200 no ambiente de
    teste, e só falharia em produção, onde o passo 4 do guard pediria escopo de
    unidade que a permissão dispensa (ADR 3.4.0008).
    """
    ambiente.guard.calls.clear()

    await client.get("/api/v1/job-functions")

    assert ambiente.guard.calls == ["authenticate", "authorize(manage_job_functions,None,None)"]


# ---------------------------------------------------------------------------
# Os provedores `_get_*` — chaves de override, não fábricas
# ---------------------------------------------------------------------------


def _provedores_do_router() -> list[str]:
    """Derivado, e não listado: um provedor novo entra na trava sozinho."""
    encontrados = sorted(
        nome
        for nome, valor in vars(router_module).items()
        if nome.startswith("_get_") and callable(valor)
    )
    assert encontrados, "a varredura precisa de provedores para ter o que exigir"
    return encontrados


@pytest.mark.parametrize("provedor", _provedores_do_router())
def test_provedor_nao_conectado_falha_alto(provedor: str) -> None:
    """Se um `_get_*` for chamado de verdade, o wiring não aconteceu.

    A resposta certa é explodir na hora, com o nome da dependência na mensagem.
    Devolver `None` "para não quebrar" empurraria a falha três camadas adiante,
    onde ela apareceria como `AttributeError: 'NoneType'` sem pista da causa — e
    numa rota de escrita isso é uma falha de acesso disfarçada de bug de tipo.
    """
    with pytest.raises(RuntimeError, match="composition root"):
        getattr(router_module, provedor)()

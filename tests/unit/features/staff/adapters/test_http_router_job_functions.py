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

import inspect
import typing
from collections.abc import Iterator
from functools import partial
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.staff.adapters.inbound.http import dependencies as dependencies_module
from restaurant_hub.features.staff.adapters.inbound.http import (
    error_handlers as error_handlers_module,
)
from restaurant_hub.features.staff.adapters.inbound.http import router as router_module
from restaurant_hub.features.staff.application.ports.out.access_guard import AccessGuard
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
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit


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
        # Stage 3.11 — o ator do ambiente é o gerente da unidade: cria a função
        # **para a unidade dele**. Sem `unit_ids` o pedido é "todas as unidades",
        # que exige `manage_tenant` (ADR 3.11.0001 §4) e ele não detém.
        "body": {"name": "Garçom", "unit_ids": [_UNIDADE]},
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
    case, e o construtor dela pede apenas os ports que os use cases de staff
    conhecem (`employees`, `job_functions`, `id_generator`, desde a 3.5
    `gateway` e, desde a 3.7, `guard` — o mesmo guard do ambiente). Isso deixa o
    wiring de teste **fechado sob acréscimo de rota**: uma rota escrita numa Task
    seguinte já nasce conectada aqui, e nenhum arquivo desta Task precisa mudar.
    """

    def __init__(self) -> None:
        self.fakes: StaffFakes = staff_repositories()
        self.guard = InMemoryAccessGuard(credential=FakeActor(id="ator-1", tenant_id=_TENANT))
        self.guard.grant("manage_job_functions", tenant_id=_TENANT)
        # Stage 3.11 — o catálogo também é exercido **com** unidade nomeada: criar
        # para a unidade, listar a unidade, mudar as unidades de uma função.
        self.guard.grant("manage_job_functions", tenant_id=_TENANT, unit_id=_UNIDADE)
        self.guard.grant("manage_staff", tenant_id=_TENANT, unit_id=_UNIDADE)
        # Stage 3.5 — R17 exige também `manage_users` sobre a unidade. O ator do
        # ambiente detém as três, como `manager`/`hr` em produção: as varreduras
        # medem a borda com o ator autorizado; a **recusa** por permissão é
        # cenário de `test_http_router_login.py`, que a retira de propósito.
        self.guard.grant("manage_users", tenant_id=_TENANT, unit_id=_UNIDADE)

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
        self.app.dependency_overrides.update(overrides_de_use_case(self.fakes, self.guard))
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


def overrides_de_use_case(fakes: StaffFakes, guard: AccessGuard) -> dict[object, object]:
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
        # Stage 3.5 — `deactivate_employee` e `create_login_for_employee` pedem o
        # gateway; o fake basta para as rotas que não o exercitam, e o módulo de
        # R17 substitui por instância própria quando precisa observá-lo.
        "gateway": InMemoryIdentityGateway(),
        # Stage 3.7 — os use cases autorizam também (ADR 3.7.0001). O guard é o
        # **do ambiente**, e não um novo: o `InMemoryAccessGuard` só reconhece o
        # ator que ele mesmo emitiu (L-AG2), então um segundo guard recusaria
        # toda chamada da application — e as concessões do ambiente valem para
        # as duas camadas, como o mesmo `staff_access_guard` vale em produção.
        "guard": guard,
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
    resposta = await client.post(
        "/api/v1/job-functions", json={"name": "Garçom", "unit_ids": [_UNIDADE]}
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["tenant_id"] == _TENANT
    assert resposta.json()["name"] == "Garçom"
    # Stage 3.11 — a função nasce habilitada só na unidade pedida (CA1).
    assert resposta.json()["all_units"] is False
    assert resposta.json()["unit_ids"] == [_UNIDADE]


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
    assert resposta.json() == {
        "id": "jf-1",
        "tenant_id": _TENANT,
        "name": "Garçom Sênior",
        "all_units": True,
        "unit_ids": [],
    }


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

    resposta = await client.post(
        "/api/v1/job-functions", json={"name": "Garçom", "unit_ids": [_UNIDADE]}
    )

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
    resposta = await client.post(
        "/api/v1/job-functions", json={"name": "   ", "unit_ids": [_UNIDADE]}
    )

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

    # A rota omite o tenant (ADR 0.0.0005); o use case o **nomeia**, com o
    # tenant do escopo que a rota lhe passou (ADR 3.7.0001 §3). Os dois sem
    # unidade.
    assert ambiente.guard.calls == [
        "authenticate",
        "authorize(manage_job_functions,None,None)",
        f"authorize(manage_job_functions,{_TENANT},None)",
    ]


# ---------------------------------------------------------------------------
# Stage 3.11 — habilitação por unidade na criação e no catálogo (ADR 3.11.0001)
# ---------------------------------------------------------------------------


async def test_ca2_gerente_sem_unit_ids_pede_todas_e_o_guard_nega_cru(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Sem `unit_ids` o pedido é "todas as unidades", e o ator do ambiente não detém
    `manage_tenant`. A recusa é do **guard**, sobe crua (L-AG2), e nada é gravado."""
    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        await client.post("/api/v1/job-functions", json={"name": "Garçom"})

    assert excinfo.value is ambiente.guard.authorization_error
    assert ambiente.guard.calls[-1] == f"authorize(manage_tenant,{_TENANT},None)"
    assert ambiente.fakes.job_functions.list_by_tenant(TenantId(_TENANT)) == ()


@pytest.mark.parametrize("corpo", [{"name": "Garçom"}, {"name": "Garçom", "unit_ids": None}])
async def test_ca2_quem_alcanca_o_restaurante_cria_para_todas(
    client: AsyncClient, ambiente: Ambiente, corpo: dict[str, object]
) -> None:
    """Ausente e `null` são o mesmo pedido; com `manage_tenant` a função vale em todas."""
    ambiente.guard.grant("manage_tenant", tenant_id=_TENANT)

    resposta = await client.post("/api/v1/job-functions", json=corpo)

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["all_units"] is True
    assert resposta.json()["unit_ids"] == []


async def test_ca2_unidade_que_o_ator_nao_enxerga_e_negada_pelo_guard(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        await client.post(
            "/api/v1/job-functions", json={"name": "Garçom", "unit_ids": [_UNIDADE, "unit-2"]}
        )

    assert excinfo.value is ambiente.guard.authorization_error
    assert ambiente.fakes.job_functions.list_by_tenant(TenantId(_TENANT)) == ()


async def test_ca9a_lista_de_unidades_vazia_recebe_422_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`[]` não é "todas": é a habilitação vazia que o domínio recusa."""
    resposta = await client.post("/api/v1/job-functions", json={"name": "Garçom", "unit_ids": []})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"
    assert "habilitação por unidade inválida" in resposta.json()["detail"]


@pytest.mark.parametrize("ruim", ["", "   ", "u\x00"])
async def test_id_de_unidade_invalido_no_corpo_e_422_antes_de_alcancar_o_guard(
    client: AsyncClient, ambiente: Ambiente, ruim: str
) -> None:
    """ADR 3.6.0002 — o validador recusa antes de o valor virar alvo de autorização."""
    ambiente.guard.calls.clear()

    resposta = await client.post(
        "/api/v1/job-functions", json={"name": "Garçom", "unit_ids": [_UNIDADE, ruim]}
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"
    assert ambiente.guard.calls == ["authenticate"]


async def test_campo_desconhecido_no_corpo_da_criacao_e_422_e_nada_e_criado(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Mesmo quem alcança o restaurante: `unit_id` (singular) não cria "em todas"."""
    ambiente.guard.grant("manage_tenant", tenant_id=_TENANT)

    resposta = await client.post(
        "/api/v1/job-functions", json={"name": "Garçom", "unit_id": [_UNIDADE]}
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] != "staff_error"
    assert ambiente.fakes.job_functions.list_by_tenant(TenantId(_TENANT)) == ()


async def test_unidades_repetidas_no_corpo_colapsam_no_conjunto(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """R11 do concept — `unit_ids` é conjunto, como `job_function_ids`."""
    resposta = await client.post(
        "/api/v1/job-functions", json={"name": "Garçom", "unit_ids": [_UNIDADE, _UNIDADE]}
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["unit_ids"] == [_UNIDADE]


async def test_ca11_o_catalogo_devolve_a_habilitacao_de_cada_funcao(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    ambiente.com_funcao("jf-1", "Cozinheiro")
    await client.post("/api/v1/job-functions", json={"name": "Garçom", "unit_ids": [_UNIDADE]})

    resposta = await client.get("/api/v1/job-functions")

    assert [(i["name"], i["all_units"], i["unit_ids"]) for i in resposta.json()] == [
        ("Cozinheiro", True, []),
        ("Garçom", False, [_UNIDADE]),
    ]


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

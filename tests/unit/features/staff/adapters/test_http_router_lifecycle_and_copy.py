"""Ciclo de vida e cópia (R13, R14, R16) — CA16 e a metade unitária de CA34.

As três rotas que fecham o inventário em **16**. Duas são transições nomeadas do
ciclo de vida; a terceira é a única do BC que autoriza **dois** alvos, e é onde a
orientação origem→destino precisa estar travada por teste em vez de por
convenção: inverter os dois responde 201 e sobrevive a todo critério que só olha
status.
"""

import importlib
from collections.abc import Iterator
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import OnDemand
from tests.fakes.features.staff.in_memory_access_guard import FakeAuthorizationRejected
from tests.unit.features.staff.adapters.test_http_router_job_functions import (
    _TENANT,
    _UNIDADE,
    Ambiente,
)

pytestmark = pytest.mark.unit

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.inbound.http"
router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")

_SUFIXO = "/units/{unit_id}/employees/{employee_id}"
_DESTINO = "unit-2"

# As declarações das três rotas que fecham o inventário. R16 é **201**: a cópia
# cria um registro novo, com id próprio, e esse recurso passa a existir.
INVOCACOES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", f"{_SUFIXO}/termination"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.OK,
    },
    ("POST", f"{_SUFIXO}/rehire"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.OK,
    },
    ("POST", f"{_SUFIXO}/copies"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"target_unit_id": _DESTINO},
        "sucesso": HTTPStatus.CREATED,
    },
}

_BASE = f"/api/v1/units/{_UNIDADE}/employees/emp-1"


@pytest.fixture
def ambiente() -> Ambiente:
    ambiente = Ambiente()
    # O destino é concedido por default: os testes que medem a **recusa** do
    # destino o retiram explicitamente, para que a recusa seja a variável do
    # cenário e não um efeito colateral da montagem.
    ambiente.guard.grant("manage_staff", tenant_id=_TENANT, unit_id=_DESTINO)
    return ambiente


@pytest.fixture
async def client(ambiente: Ambiente) -> Iterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


def _com_funcionario(ambiente: Ambiente, *, active: bool = True) -> Employee:
    ambiente.com_funcao("jf-1")
    funcionario = Employee(
        id=EmployeeId("emp-1"),
        tenant_id=TenantId(_TENANT),
        unit_id=UnitId(_UNIDADE),
        name="Ana",
        workload_profile=OnDemand(),
        shift_preference=None,
        job_function_ids=frozenset({JobFunctionId("jf-1")}),
    )
    if not active:
        funcionario = funcionario.deactivate()
    ambiente.fakes.employees.add(funcionario)
    return funcionario


def _ids_na_unidade(ambiente: Ambiente, unidade: str) -> set[str]:
    return {
        empregado.id
        for empregado in ambiente.fakes.employees.list_by_unit(
            TenantId(_TENANT), UnitId(unidade), include_inactive=True
        )
    }


# ---------------------------------------------------------------------------
# R13 e R14 — as duas transições nomeadas
# ---------------------------------------------------------------------------


async def test_r13_desliga_o_funcionario_e_o_registro_sobrevive(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Desligar não apaga: o registro continua, com `active=false` (ADR 3.2.0006)."""
    _com_funcionario(ambiente)

    resposta = await client.post(f"{_BASE}/termination")

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["active"] is False
    assert _ids_na_unidade(ambiente, _UNIDADE) == {"emp-1"}


async def test_r14_recontrata_o_funcionario_desligado(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    _com_funcionario(ambiente, active=False)

    resposta = await client.post(f"{_BASE}/rehire")

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["active"] is True


async def test_as_transicoes_sao_sub_recursos_post_e_nao_edicao_de_campo() -> None:
    """A forma é a decisão (ADR 3.2.0007), e é verificável no inventário.

    Um `PATCH {"active": false}` faria a transição parecer atribuição de
    atributo. A ausência de `active` entre os campos que qualquer request aceita
    é o que impede essa leitura de voltar pela porta dos fundos.
    """
    schemas = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.schemas")
    campos = {
        nome
        for atributo, objeto in vars(schemas).items()
        if atributo.endswith("Request") and hasattr(objeto, "model_fields")
        for nome in objeto.model_fields
    }

    assert "active" not in campos


# ---------------------------------------------------------------------------
# CA16 — R16 autoriza dois alvos
# ---------------------------------------------------------------------------


async def test_ca16_a_copia_chama_o_guard_duas_vezes_com_alvos_distintos(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """L-AG4 aplicada, **não** otimizada.

    Reusar o escopo da origem para alcançar o destino é escalada de escopo: o
    ator passaria a gravar numa unidade que nunca foi autorizada a alcançar. A
    asserção é sobre os **alvos registrados**, e não sobre o status — com uma
    chamada só, a rota continuaria respondendo 201.
    """
    _com_funcionario(ambiente)
    ambiente.guard.calls.clear()

    resposta = await client.post(f"{_BASE}/copies", json={"target_unit_id": _DESTINO})

    assert resposta.status_code == HTTPStatus.CREATED
    autorizacoes = [c for c in ambiente.guard.calls if c.startswith("authorize(")]
    assert autorizacoes == [
        f"authorize(manage_staff,None,{_UNIDADE})",
        f"authorize(manage_staff,None,{_DESTINO})",
    ]


async def test_ca16_a_origem_nao_visivel_e_recusada_antes_de_qualquer_escrita(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """O caso que mata a mutação "remover a primeira chamada".

    Sem a autorização da **origem**, um ator que enxerga só o destino leria o
    registro de uma unidade que não alcança e o copiaria para a sua. Com a
    primeira chamada removida, todos os outros testes desta suíte continuariam
    verdes — este é o único que fica vermelho.
    """
    _com_funcionario(ambiente)
    ambiente.guard.grants = {
        alvo for alvo in ambiente.guard.grants if alvo[2] != _UNIDADE or alvo[0] != "manage_staff"
    }

    with pytest.raises(FakeAuthorizationRejected):
        await client.post(f"{_BASE}/copies", json={"target_unit_id": _DESTINO})

    assert _ids_na_unidade(ambiente, _DESTINO) == set()


async def test_ca16_o_destino_nao_concedido_e_recusado_sem_gravar_nada(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A segunda chamada é a que fecha a exfiltração para a unidade alheia."""
    _com_funcionario(ambiente)
    ambiente.guard.grants = {alvo for alvo in ambiente.guard.grants if alvo[2] != _DESTINO}

    with pytest.raises(FakeAuthorizationRejected):
        await client.post(f"{_BASE}/copies", json={"target_unit_id": _DESTINO})

    assert _ids_na_unidade(ambiente, _DESTINO) == set()
    assert _ids_na_unidade(ambiente, _UNIDADE) == {"emp-1"}


@pytest.mark.parametrize(
    "destino",
    [
        pytest.param("unit-de-outro-tenant", id="outro-tenant"),
        pytest.param("unit-que-nao-existe", id="inexistente"),
        pytest.param("unit-9", id="nao-visivel"),
    ],
)
async def test_ca16_as_tres_recusas_do_destino_sao_indistinguiveis(
    client: AsyncClient, ambiente: Ambiente, destino: str
) -> None:
    """As três produzem **a mesma** recusa, e a indistinguibilidade é o desenho.

    Outro tenant, inexistente e não visível chegam todas ao mesmo ponto: o guard
    não concede o alvo. Quem não enxerga a unidade não pode usar a resposta para
    descobrir se ela existe — é o oráculo de enumeração que L-AG2 fecha, e por
    isso a asserção é de **identidade da sentinela**, não de status: um adapter
    que traduzisse uma das três de forma diferente reabriria a distinção.
    """
    _com_funcionario(ambiente)

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        await client.post(f"{_BASE}/copies", json={"target_unit_id": destino})

    assert excinfo.value is ambiente.guard.authorization_error
    assert _ids_na_unidade(ambiente, destino) == set()


# ---------------------------------------------------------------------------
# CA34 (metade unitária) — a orientação origem→destino
# ---------------------------------------------------------------------------


async def test_ca34_o_command_carrega_a_origem_no_path_e_o_destino_no_corpo(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A metade unitária de CA34, asserida no **command** e não na resposta.

    A inversão origem↔destino sobrevive a CA11, CA13, CA16 e CA25, porque nenhum
    deles exercita uma cópia que **dá certo** e olha onde ela caiu. Aqui o efeito
    é medido no store: o clone aparece no destino, o original permanece na
    origem, e os dois ids diferem.
    """
    _com_funcionario(ambiente)

    resposta = await client.post(f"{_BASE}/copies", json={"target_unit_id": _DESTINO})

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["unit_id"] == _DESTINO
    assert resposta.json()["id"] != "emp-1"
    assert _ids_na_unidade(ambiente, _UNIDADE) == {"emp-1"}
    assert _ids_na_unidade(ambiente, _DESTINO) == {resposta.json()["id"]}


async def test_r16_copia_para_a_mesma_unidade_recebe_422_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`SameUnitCopyError` é 422 e não 409: nada está em conflito.

    O cliente nomeou a origem como destino — é o payload que está errado, não o
    estado gravado.
    """
    _com_funcionario(ambiente)

    resposta = await client.post(f"{_BASE}/copies", json={"target_unit_id": _UNIDADE})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_r16_destino_invalido_e_recusado_antes_de_qualquer_autorizacao(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`target_unit_id` é o segundo alvo, e vai para `units.find_by_id` de identity.

    Por isso ele passa pelo validador **antes** de qualquer chamada ao guard — a
    mesma ordem que CA21 trava nos outros eixos. A asserção é a ausência de
    `authorize(`, não o status.
    """
    _com_funcionario(ambiente)
    ambiente.guard.calls.clear()

    resposta = await client.post(f"{_BASE}/copies", json={"target_unit_id": "   "})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"
    assert [c for c in ambiente.guard.calls if c.startswith("authorize(")] == []

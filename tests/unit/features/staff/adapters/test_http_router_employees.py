"""Rotas de CRUD de funcionário (R05, R06, R07, R15), pela app FastAPI montada.

Mesmo ambiente e mesma disciplina do módulo de catálogo: app real, fakes de
repositório, e o `INVOCACOES` deste módulo declarando como cada rota nova é
invocada com corpo e query **válidos** — que é o que as varreduras de borda
colhem do pacote, e o que a asserção de totalidade cobra.

A trava do endereçamento (CA15) **não** está aqui: ela precisa de um dublê que
contradiga o pedido, e mora em `test_http_path_addresses_the_record.py`. O que
este arquivo cobre é o comportamento das quatro rotas.
"""

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
from tests.unit.features.staff.adapters.test_http_router_job_functions import (
    _TENANT,
    _UNIDADE,
    Ambiente,
)

pytestmark = pytest.mark.unit


_PERFIL_SOB_DEMANDA = {"type": "on_demand"}

# **As invocações válidas das quatro rotas desta Task.** Declaradas aqui, no
# módulo da Task que escreveu as rotas — as varreduras as colhem do pacote. Uma
# rota sem chave reprova a asserção de totalidade, que é o mecanismo que obriga
# quem acrescenta rota a dizer como invocá-la.
INVOCACOES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", "/units/{unit_id}/employees"): {
        "path": {"unit_id": _UNIDADE},
        "query": {},
        "body": {
            "name": "Ana",
            "workload_profile": _PERFIL_SOB_DEMANDA,
            "job_function_ids": ["jf-1"],
        },
        "sucesso": HTTPStatus.CREATED,
    },
    ("GET", "/units/{unit_id}/employees"): {
        "path": {"unit_id": _UNIDADE},
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.OK,
    },
    ("PATCH", "/units/{unit_id}/employees/{employee_id}"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"name": "Ana Maria"},
        "sucesso": HTTPStatus.OK,
    },
    ("DELETE", "/units/{unit_id}/employees/{employee_id}"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.NO_CONTENT,
    },
}

_BASE = f"/api/v1/units/{_UNIDADE}/employees"


@pytest.fixture
def ambiente() -> Ambiente:
    return Ambiente()


@pytest.fixture
async def client(ambiente: Ambiente) -> Iterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


def _corpo_de_criacao(**extras: object) -> dict[str, object]:
    return {
        "name": "Ana",
        "workload_profile": _PERFIL_SOB_DEMANDA,
        "job_function_ids": ["jf-1"],
        **extras,
    }


def _com_funcionario(
    ambiente: Ambiente,
    *,
    employee_id: str = "emp-1",
    unit_id: str = _UNIDADE,
    job_function_id: str = "jf-1",
    active: bool = True,
) -> Employee:
    """Semeia um funcionário no store, no endereço pedido.

    Mora aqui, e não no `Ambiente`, porque é o vocabulário **desta** Task: o
    módulo de catálogo não precisa endereçar registro por unidade, e alargar o
    ambiente compartilhado para caber este caso o faria crescer a cada Task.
    """
    funcionario = Employee(
        id=EmployeeId(employee_id),
        tenant_id=TenantId(_TENANT),
        unit_id=UnitId(unit_id),
        name="Ana",
        workload_profile=OnDemand(),
        shift_preference=None,
        job_function_ids=frozenset({JobFunctionId(job_function_id)}),
    )
    if not active:
        funcionario = funcionario.deactivate()
    ambiente.fakes.employees.add(funcionario)
    return funcionario


# ---------------------------------------------------------------------------
# Caminho feliz
# ---------------------------------------------------------------------------


async def test_r05_cria_funcionario_na_unidade_do_path_com_201(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A unidade da resposta é a do **endereço**, e o tenant vem do escopo."""
    ambiente.com_funcao("jf-1")

    resposta = await client.post(_BASE, json=_corpo_de_criacao())

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["unit_id"] == _UNIDADE
    assert resposta.json()["tenant_id"] == _TENANT
    assert resposta.json()["active"] is True


async def test_r05_aceita_preferencia_de_turno_e_a_devolve_na_ordem_do_enum(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A conversão de período do dia acontece no router, por `from_string`.

    A ordem de saída é a de declaração do enum, e não a alfabética — que aqui
    discordam, e é a discordância que dá refutação à asserção.
    """
    ambiente.com_funcao("jf-1")

    resposta = await client.post(
        _BASE, json=_corpo_de_criacao(shift_preference=["overnight", "morning"])
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert resposta.json()["shift_preference"] == ["morning", "overnight"]


async def test_r06_lista_a_unidade_e_esconde_o_desligado_por_default(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`include_inactive` é opt-in explícito: o default esconde os desligados."""
    ambiente.com_funcao("jf-1")
    _com_funcionario(ambiente)
    _com_funcionario(ambiente, employee_id="emp-2", active=False)

    default = await client.get(_BASE)
    com_inativos = await client.get(_BASE, params={"include_inactive": "true"})

    assert [item["id"] for item in default.json()] == ["emp-1"]
    assert {item["id"] for item in com_inativos.json()} == {"emp-1", "emp-2"}


async def test_r07_renomeia_o_funcionario_enderecado_com_200(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    ambiente.com_funcao("jf-1")
    _com_funcionario(ambiente)

    resposta = await client.patch(f"{_BASE}/emp-1", json={"name": "Ana Maria"})

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["name"] == "Ana Maria"


async def test_r15_remove_o_funcionario_com_204_e_corpo_vazio(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    ambiente.com_funcao("jf-1")
    _com_funcionario(ambiente)

    resposta = await client.delete(f"{_BASE}/emp-1")

    assert resposta.status_code == HTTPStatus.NO_CONTENT
    assert resposta.content == b""
    assert (
        ambiente.fakes.employees.find_by_id(
            TenantId(_TENANT), UnitId(_UNIDADE), EmployeeId("emp-1")
        )
        is None
    )


# ---------------------------------------------------------------------------
# O endereço é (tenant, unidade, id) — ADR 3.4.0007
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metodo", "sufixo", "corpo"),
    [
        pytest.param("patch", "/emp-1", {"name": "X"}, id="R07"),
        pytest.param("delete", "/emp-1", None, id="R15"),
    ],
)
async def test_funcionario_de_outra_unidade_recebe_404_pelo_endereco_proprio(
    client: AsyncClient,
    ambiente: Ambiente,
    metodo: str,
    sufixo: str,
    corpo: dict[str, str] | None,
) -> None:
    """404 quando o id existe, mas **não** na unidade do endereço.

    É a metade de CA13 que se observa sem papéis: `find_by_id(tenant, unidade,
    id)` não casa, e o registro de outra unidade fica invisível — não por
    permissão, mas por **endereçamento**. Confundir este 404 com o 403 do guard
    faria metade da parametrização de CA13 reprovar no e2e.
    """
    ambiente.com_funcao("jf-1")
    _com_funcionario(ambiente, unit_id="unit-2")
    ambiente.guard.grant("manage_staff", tenant_id=_TENANT, unit_id="unit-2")

    resposta = await client.request(metodo, f"{_BASE}{sufixo}", json=corpo)

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    assert resposta.json()["type"] == "staff_error"


async def test_a_listagem_de_uma_unidade_nao_mostra_funcionario_de_outra(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """O isolamento entre unidades, visto do lado da leitura."""
    ambiente.com_funcao("jf-1")
    _com_funcionario(ambiente, employee_id="emp-a")
    _com_funcionario(ambiente, employee_id="emp-b", unit_id="unit-2")

    resposta = await client.get(_BASE)

    assert [item["id"] for item in resposta.json()] == ["emp-a"]


async def test_o_guard_e_consultado_com_a_unidade_do_path(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """O alvo declarado ao port é a unidade do endereço, e a permissão é de equipe.

    A asserção é sobre o **alvo registrado**: um router que autorizasse sem
    nomear a unidade continuaria devolvendo 200 aqui, e só falharia em produção,
    onde o passo 4 do guard exigiria o escopo que `manage_staff` não dispensa.
    """
    ambiente.com_funcao("jf-1")
    ambiente.guard.calls.clear()

    await client.get(_BASE)

    assert ambiente.guard.calls == [
        "authenticate",
        f"authorize(manage_staff,None,{_UNIDADE})",
    ]


# ---------------------------------------------------------------------------
# Erros de conteúdo
# ---------------------------------------------------------------------------


async def test_periodo_do_dia_desconhecido_recebe_422_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`DayPeriod("xpto")` levantaria `ValueError` e viraria 500; `from_string` não."""
    ambiente.com_funcao("jf-1")

    resposta = await client.post(_BASE, json=_corpo_de_criacao(shift_preference=["xpto"]))

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_conjunto_de_funcoes_vazio_recebe_422_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Funcionário exige ao menos uma função atribuída (ADR 3.1.0006)."""
    resposta = await client.post(_BASE, json=_corpo_de_criacao(job_function_ids=[]))

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_funcao_inexistente_no_tenant_recebe_erro_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """A validade referencial é do use case; a borda só a deixa chegar lá."""
    resposta = await client.post(_BASE, json=_corpo_de_criacao(job_function_ids=["jf-404"]))

    assert resposta.status_code in {HTTPStatus.NOT_FOUND, HTTPStatus.UNPROCESSABLE_ENTITY}
    assert resposta.json()["type"] == "staff_error"


async def test_carga_semanal_nao_numerica_recebe_422_de_staff_e_nao_500(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Sem o conversor da borda, `Decimal("abc")` levantaria `ArithmeticError`.

    Nenhum handler alcança `ArithmeticError` — a resposta seria **500**. O
    discriminador de corpo é o que separa este 422 do 422 de forma do framework.
    """
    ambiente.com_funcao("jf-1")

    resposta = await client.post(
        _BASE,
        json=_corpo_de_criacao(workload_profile={"type": "fixed", "weekly_hours": "abc"}),
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"

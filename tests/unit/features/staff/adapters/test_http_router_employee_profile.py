"""Perfil, preferência de turno e indisponibilidades (R08…R12), pela app montada.

As cinco rotas de edição do registro que não são renomeação nem ciclo de vida. A
construção dos value objects acontece **no router** (concept §5.5), e é o que faz
cada recusa ser erro de **domínio** — com o corpo de staff — em vez de um
`RequestValidationError` do framework.

O `INVOCACOES` deste módulo entra automaticamente nas varreduras de borda e na
trava de CA15, sem que nenhum arquivo daquelas Tasks mude: é o mecanismo que a
Task 05 montou e que esta Task é a primeira a exercitar de verdade.
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
from tests.unit.features.staff.adapters.test_http_router_job_functions import (
    _TENANT,
    _UNIDADE,
    Ambiente,
)

pytestmark = pytest.mark.unit

_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.inbound.http"
router_module = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.router")

_PERFIL_FIXO = {"type": "fixed", "weekly_hours": "40.0"}
_INICIO = "2026-03-01T08:00:00"
_FIM = "2026-03-01T12:00:00"
_SUFIXO = "/units/{unit_id}/employees/{employee_id}"

# **As declarações das cinco rotas desta Task** — invocação válida e o status de
# sucesso transcrito da tabela do concept §4.1. R11 é **200, não 201**: o período
# não é recurso endereçável e não ganha URL própria.
INVOCACOES: dict[tuple[str, str], dict[str, object]] = {
    ("PUT", f"{_SUFIXO}/job-functions"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"job_function_ids": ["jf-1"]},
        "sucesso": HTTPStatus.OK,
    },
    ("PUT", f"{_SUFIXO}/workload-profile"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"workload_profile": _PERFIL_FIXO},
        "sucesso": HTTPStatus.OK,
    },
    ("PUT", f"{_SUFIXO}/shift-preference"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"shift_preference": ["morning"]},
        "sucesso": HTTPStatus.OK,
    },
    ("POST", f"{_SUFIXO}/unavailabilities"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"start": _INICIO, "end": _FIM},
        "sucesso": HTTPStatus.OK,
    },
    ("DELETE", f"{_SUFIXO}/unavailabilities"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {"start": _INICIO, "end": _FIM},
        "body": None,
        "sucesso": HTTPStatus.OK,
    },
}

_BASE = f"/api/v1/units/{_UNIDADE}/employees/emp-1"


@pytest.fixture
def ambiente() -> Ambiente:
    return Ambiente()


@pytest.fixture
async def client(ambiente: Ambiente) -> Iterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


def _com_funcionario(ambiente: Ambiente, *, funcoes: tuple[str, ...] = ("jf-1",)) -> Employee:
    # Nomes distintos por funcao: o repositorio recusa homonimos no mesmo tenant
    # (L-JF), e um nome repetido aqui faria a fixture falhar por uma razao que
    # nada tem a ver com a rota sob teste.
    for indice, job_function_id in enumerate(funcoes):
        ambiente.com_funcao(job_function_id, name=f"Funcao {indice}")
    funcionario = Employee(
        id=EmployeeId("emp-1"),
        tenant_id=TenantId(_TENANT),
        unit_id=UnitId(_UNIDADE),
        name="Ana",
        workload_profile=OnDemand(),
        shift_preference=None,
        job_function_ids=frozenset({JobFunctionId(funcoes[0])}),
    )
    ambiente.fakes.employees.add(funcionario)
    return funcionario


# ---------------------------------------------------------------------------
# R08 — substituição do conjunto de funções
# ---------------------------------------------------------------------------


async def test_r08_substitui_o_conjunto_de_funcoes_e_nao_acrescenta(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`PUT` porque é **substituição**: o conjunto antigo some, não se soma."""
    _com_funcionario(ambiente, funcoes=("jf-1", "jf-2"))

    resposta = await client.put(f"{_BASE}/job-functions", json={"job_function_ids": ["jf-2"]})

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["job_function_ids"] == ["jf-2"]


async def test_r08_conjunto_vazio_recebe_422_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Funcionário exige ao menos uma função (ADR 3.1.0006)."""
    _com_funcionario(ambiente)

    resposta = await client.put(f"{_BASE}/job-functions", json={"job_function_ids": []})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


# ---------------------------------------------------------------------------
# R09 — perfil de jornada
# ---------------------------------------------------------------------------


async def test_r09_troca_o_perfil_para_jornada_fixa_preservando_a_escala(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`"22.50"` entra e `"22.50"` volta — a escala é propriedade do valor."""
    _com_funcionario(ambiente)

    resposta = await client.put(
        f"{_BASE}/workload-profile",
        json={"workload_profile": {"type": "fixed", "weekly_hours": "22.50"}},
    )

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["workload_profile"] == {"type": "fixed", "weekly_hours": "22.50"}


async def test_r09_carga_nao_numerica_recebe_422_de_staff_e_nao_500(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Sem o conversor da borda seria `ArithmeticError`, que nenhum handler alcança."""
    _com_funcionario(ambiente)

    resposta = await client.put(
        f"{_BASE}/workload-profile",
        json={"workload_profile": {"type": "fixed", "weekly_hours": "40,5"}},
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


# ---------------------------------------------------------------------------
# R10 — preferência de turno (CA03)
# ---------------------------------------------------------------------------


async def test_ca03_shift_preference_null_limpa_a_preferencia(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`null` significa **limpe**, e a resposta tem de mostrar a limpeza."""
    _com_funcionario(ambiente)
    await client.put(f"{_BASE}/shift-preference", json={"shift_preference": ["morning"]})

    resposta = await client.put(f"{_BASE}/shift-preference", json={"shift_preference": None})

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["shift_preference"] is None


async def test_ca03_corpo_vazio_recebe_422_por_campo_obrigatorio(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Corpo `{}` é recusado — com default, ele limparia a preferência em silêncio.

    Este 422 é do **framework** (campo obrigatório ausente), e não de staff: a
    forma do corpo não casa o schema. O discriminador prova a origem, e é o que
    distingue este caso do de cima.
    """
    _com_funcionario(ambiente)

    resposta = await client.put(f"{_BASE}/shift-preference", json={})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] != "staff_error"


async def test_ca23_periodo_do_dia_desconhecido_recebe_422_de_staff_em_r10(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """`DayPeriod("xpto")` seria `ValueError` e 500; `from_string` é 422.

    A metade comportamental de CA23 no segundo ponto de construção — R05 é a
    outra. A varredura de AST da Task 05 cobre a metade estrutural.
    """
    _com_funcionario(ambiente)

    resposta = await client.put(f"{_BASE}/shift-preference", json={"shift_preference": ["xpto"]})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_r10_preferencia_sai_na_ordem_de_declaracao_do_enum(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Ordem do enum, não alfabética — e as duas discordam neste conjunto."""
    _com_funcionario(ambiente)

    resposta = await client.put(
        f"{_BASE}/shift-preference", json={"shift_preference": ["night", "morning", "afternoon"]}
    )

    assert resposta.json()["shift_preference"] == ["morning", "afternoon", "night"]


# ---------------------------------------------------------------------------
# R11 e R12 — indisponibilidades
# ---------------------------------------------------------------------------


async def test_r11_registra_indisponibilidade_com_200_e_nao_201(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """O período não é recurso endereçável: um 201 sem `Location` mentiria."""
    _com_funcionario(ambiente)

    resposta = await client.post(f"{_BASE}/unavailabilities", json={"start": _INICIO, "end": _FIM})

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["unavailabilities"] == [{"start": _INICIO, "end": _FIM}]


async def test_ca04_instante_com_z_recebe_422_e_nao_e_convertido_em_silencio(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Tz-aware é recusado por `UnavailabilityPeriod`, não deslocado.

    Converter seria mudar o que o gerente declarou: os instantes são wall-clock
    do fuso da unidade (ADR 3.1.0005).
    """
    _com_funcionario(ambiente)

    resposta = await client.post(
        f"{_BASE}/unavailabilities",
        json={"start": "2026-03-01T08:00:00Z", "end": "2026-03-01T12:00:00Z"},
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_r11_periodo_sobreposto_recebe_422_de_staff(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Sobreposição é invariante do agregado violada pelo período **enviado**."""
    _com_funcionario(ambiente)
    await client.post(f"{_BASE}/unavailabilities", json={"start": _INICIO, "end": _FIM})

    resposta = await client.post(
        f"{_BASE}/unavailabilities",
        json={"start": "2026-03-01T10:00:00", "end": "2026-03-01T14:00:00"},
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_r12_remove_o_periodo_por_igualdade_de_valor(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """Quem remove reapresenta o **valor** — o período não tem identidade."""
    _com_funcionario(ambiente)
    await client.post(f"{_BASE}/unavailabilities", json={"start": _INICIO, "end": _FIM})

    resposta = await client.delete(
        f"{_BASE}/unavailabilities", params={"start": _INICIO, "end": _FIM}
    )

    assert resposta.status_code == HTTPStatus.OK
    assert resposta.json()["unavailabilities"] == []


async def test_ca19_periodo_inexistente_recebe_422_e_nao_404(
    client: AsyncClient, ambiente: Ambiente
) -> None:
    """**422, não 404** — a metade comportamental de CA19 alcançável aqui.

    O período é um valor **dentro** do agregado, não um recurso endereçável: o
    funcionário existe e foi encontrado. `UnavailabilityNotFoundError` herda só
    de `StaffError` precisamente para que a MRO não a leve ao 404.
    """
    _com_funcionario(ambiente)

    resposta = await client.delete(
        f"{_BASE}/unavailabilities", params={"start": _INICIO, "end": _FIM}
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"


async def test_r12_com_query_faltando_recebe_o_422_do_framework(client: AsyncClient) -> None:
    """`start` e `end` são obrigatórios: sem eles a **forma** não casa.

    O discriminador distingue este 422 do de staff — é a mesma separação que a
    varredura de borda depende para não medir a peça errada.
    """
    resposta = await client.delete(f"{_BASE}/unavailabilities")

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] != "staff_error"

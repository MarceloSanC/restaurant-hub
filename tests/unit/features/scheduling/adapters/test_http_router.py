"""As sete rotas de scheduling pela app FastAPI, sobre os fakes (Stage 4.5).

Cobre o caminho feliz de cada rota, a totalidade `router.routes` contra `INVOCACOES`, a
autorização da **rota** com espião (CA14 — na matriz e2e o use case negaria igual), a ordem
validar → autorizar (CA7), o offset recusado e o instante sem offset na saída (CA8), a recusa
otimista da vizinha (CA5, por dublê: o entrelace real é do teste de conduta da 4.4) e a trava
de AST contra ler `scope.unit_id` (CA9).
"""

import ast
import inspect
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient, Response

from restaurant_hub.features.scheduling.adapters.inbound.http import router as router_module
from restaurant_hub.features.scheduling.application.errors import ScheduleVersionConflictError
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
)
from tests.unit.features.scheduling.adapters.http_support import API, Ambiente, bearer
from tests.unit.features.scheduling.application.conftest import COOK, T1

pytestmark = pytest.mark.unit

_U = "u1"
_GERENTE = bearer("user-ger")
_ANA = bearer("user-ana")
_FAIXA = "11111111-1111-4111-8111-111111111111"
_DEMANDA = "22222222-2222-4222-8222-222222222222"
_ALOCACAO = "33333333-3333-4333-8333-333333333333"
_ALOCACAO_2 = "44444444-4444-4444-8444-444444444444"

_LOTE_DA_ANA = [
    {
        "op": "enable_band",
        "band_id": _FAIXA,
        "start": "2026-11-02T10:00:00",
        "end": "2026-11-02T16:00:00",
    },
    {
        "op": "declare_demand",
        "demand_id": _DEMANDA,
        "band_id": _FAIXA,
        "job_function_id": "cozinheiro",
        "quantity": 1,
    },
    {
        "op": "assign_employee",
        "assignment_id": _ALOCACAO,
        "demand_id": _DEMANDA,
        "employee_id": "ana",
    },
]

# Como invocar cada rota com corpo e query **válidos**, a permissão que ela exige e o status
# de sucesso. A totalidade é cobrada contra `router.routes`.
INVOCACOES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/units/{unit_id}/schedules"): {
        "body": {"first_day": "2026-11-09"},
        "query": {},
        "permissao": PERMISSION_MANAGE_SCHEDULE,
        "sucesso": HTTPStatus.CREATED,
    },
    ("GET", "/units/{unit_id}/schedules"): {
        "body": None,
        "query": {"before": "2026-12-31"},
        "permissao": PERMISSION_VIEW_SCHEDULE,
        "sucesso": HTTPStatus.OK,
    },
    ("GET", "/units/{unit_id}/schedules/{schedule_id}"): {
        "body": None,
        "query": {},
        "permissao": PERMISSION_VIEW_SCHEDULE,
        "sucesso": HTTPStatus.OK,
    },
    ("POST", "/units/{unit_id}/schedules/{schedule_id}/evaluations"): {
        "body": {"expected_version": 1, "operations": _LOTE_DA_ANA},
        "query": {},
        "permissao": PERMISSION_MANAGE_SCHEDULE,
        "sucesso": HTTPStatus.OK,
    },
    ("POST", "/units/{unit_id}/schedules/{schedule_id}/publications"): {
        "body": {"expected_version": 1, "operations": _LOTE_DA_ANA, "acknowledgements": []},
        "query": {},
        "permissao": PERMISSION_MANAGE_SCHEDULE,
        "sucesso": HTTPStatus.OK,
    },
    ("GET", "/units/{unit_id}/calendar"): {
        "body": None,
        "query": {"first_day": "2026-11-02", "last_day": "2026-11-08"},
        "permissao": PERMISSION_VIEW_SCHEDULE,
        "sucesso": HTTPStatus.OK,
    },
    ("GET", "/units/{unit_id}/my-schedule"): {
        "body": None,
        "query": {"first_day": "2026-11-02", "last_day": "2026-11-08"},
        "permissao": PERMISSION_VIEW_OWN_SCHEDULE,
        "sucesso": HTTPStatus.OK,
    },
}


@pytest.fixture
def ambiente() -> Ambiente:
    return Ambiente()


@pytest.fixture
async def client(ambiente: Ambiente) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


async def _criar(client: AsyncClient, first_day: str = "2026-11-02") -> str:
    resposta = await client.post(
        f"{API}/units/{_U}/schedules", json={"first_day": first_day}, headers=_GERENTE
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["schedule_id"])


def _url(chave: tuple[str, str], schedule_id: str = "s-x", unit_id: str = _U) -> str:
    return API + chave[1].replace("{unit_id}", unit_id).replace("{schedule_id}", schedule_id)


async def _invocar(  # noqa: PLR0913 — cliente, rota, cabeçalho e o endereço (3)
    client: AsyncClient,
    chave: tuple[str, str],
    headers: dict[str, str],
    *,
    schedule_id: str = "s-x",
    unit_id: str = _U,
    body: object = None,
) -> Response:
    invocacao = INVOCACOES[chave]
    return await client.request(
        chave[0],
        _url(chave, schedule_id, unit_id),
        json=body if body is not None else invocacao["body"],
        params=invocacao["query"],
        headers=headers,
    )


# --- totalidade ---------------------------------------------------------------------------


def test_cada_rota_do_router_tem_invocacao_declarada() -> None:
    rotas = {
        (metodo, rota.path)
        for rota in router_module.router.routes
        if isinstance(rota, APIRoute)
        for metodo in rota.methods
    }
    assert rotas == set(INVOCACOES)


def test_cada_rota_usa_um_provedor_de_use_case_distinto() -> None:
    provedores = [nome for nome, valor in vars(router_module).items() if nome.startswith("_get_")]
    assert len(provedores) == len(INVOCACOES) == 7  # noqa: PLR2004


# --- caminho feliz --------------------------------------------------------------------------


async def test_s1_cria_a_escala_e_s2_le_a_vazia(client: AsyncClient) -> None:
    sid = await _criar(client)
    resposta = await client.get(f"{API}/units/{_U}/schedules/{sid}", headers=_GERENTE)
    assert resposta.status_code == HTTPStatus.OK
    corpo = resposta.json()
    assert corpo["summary"] == {
        "schedule_id": sid,
        "unit_id": _U,
        "first_day": "2026-11-02",
        "last_day": "2026-11-08",
        "version": 1,
    }
    assert (corpo["bands"], corpo["violations"]) == ([], [])


async def test_s3_avalia_sem_gravar_e_s4_publica(client: AsyncClient) -> None:
    sid = await _criar(client)
    avaliada = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/evaluations",
        json={"expected_version": 1, "operations": _LOTE_DA_ANA},
        headers=_GERENTE,
    )
    assert avaliada.status_code == HTTPStatus.OK, avaliada.text
    assert avaliada.json()["schedule"]["summary"]["version"] == 4  # noqa: PLR2004
    lida = await client.get(f"{API}/units/{_U}/schedules/{sid}", headers=_GERENTE)
    assert lida.json()["summary"]["version"] == 1  # avaliar não grava

    publicada = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": _LOTE_DA_ANA},
        headers=_GERENTE,
    )
    assert publicada.status_code == HTTPStatus.OK, publicada.text
    corpo = publicada.json()
    assert corpo["summary"]["version"] == 4  # noqa: PLR2004 — 1 + três operações efetivas
    (faixa,) = corpo["bands"]
    assert (faixa["start"], faixa["end"]) == ("2026-11-02T10:00:00", "2026-11-02T16:00:00")
    (demanda,) = faixa["demands"]
    assert demanda["function_enabled_in_unit"] is True
    assert [a["employee_id"] for a in demanda["assignments"]] == ["ana"]


async def test_s4_sem_aceite_pede_aceite_e_com_aceite_publica(client: AsyncClient) -> None:
    sid = await _criar(client)
    excedente = [
        *_LOTE_DA_ANA,
        {
            "op": "assign_employee",
            "assignment_id": _ALOCACAO_2,
            "demand_id": _DEMANDA,
            "employee_id": "bia",
        },
    ]
    recusa = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": excedente},
        headers=_GERENTE,
    )
    assert recusa.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    corpo = recusa.json()
    assert (corpo["type"], corpo["code"]) == ("scheduling_error", "unacknowledged_violations")
    aceites = [
        {"key": v["key"], "observed": v["observed"], "limit": v["limit"]}
        for v in corpo["violations"]
    ]
    publicada = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": excedente, "acknowledgements": aceites},
        headers=_GERENTE,
    )
    assert publicada.status_code == HTTPStatus.OK, publicada.text
    assert publicada.json()["summary"]["version"] == 5  # noqa: PLR2004


async def test_s5_s6_s7_leem_o_que_foi_publicado(client: AsyncClient) -> None:
    sid = await _criar(client)
    await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": _LOTE_DA_ANA},
        headers=_GERENTE,
    )
    cal = await client.get(
        f"{API}/units/{_U}/calendar",
        params={"first_day": "2026-11-02", "last_day": "2026-11-02"},
        headers=_GERENTE,
    )
    assert cal.status_code == HTTPStatus.OK
    assert [s["schedule_id"] for s in cal.json()["schedules"]] == [sid]
    assert cal.json()["bands"][0]["demands"][0]["function_enabled_in_unit"] is True

    anteriores = await client.get(
        f"{API}/units/{_U}/schedules", params={"before": "2026-11-30"}, headers=_GERENTE
    )
    assert [s["schedule_id"] for s in anteriores.json()] == [sid]

    minha = await client.get(
        f"{API}/units/{_U}/my-schedule",
        params={"first_day": "2026-11-02", "last_day": "2026-11-08"},
        headers=_ANA,
    )
    assert minha.status_code == HTTPStatus.OK
    (turno,) = minha.json()["shifts"]
    assert (turno["employee_id"], turno["start"]) == ("ana", "2026-11-02T10:00:00")


# --- CA14: a autorização da rota, com espião --------------------------------------------------


@pytest.mark.parametrize("chave", sorted(INVOCACOES), ids=lambda c: f"{c[0]} {c[1]}")
async def test_ca14_a_rota_pede_a_sua_permissao_na_unidade_do_path_sem_tenant(
    ambiente: Ambiente, client: AsyncClient, chave: tuple[str, str]
) -> None:
    ambiente.world.guard.calls.clear()
    await _invocar(client, chave, _GERENTE)
    autorizacoes = [c for c in ambiente.world.guard.calls if c.startswith("authorize")]
    # A primeira é a da rota: tenant omitido (L-SG5), a permissão declarada, a unidade do path.
    assert autorizacoes[0] == f"authorize({INVOCACOES[chave]['permissao']},None,{_U})"


@pytest.mark.parametrize("chave", sorted(INVOCACOES), ids=lambda c: f"{c[0]} {c[1]}")
async def test_ca14_guard_negando_o_use_case_nao_e_chamado(
    ambiente: Ambiente, client: AsyncClient, chave: tuple[str, str]
) -> None:
    ambiente.world.guard.calls.clear()
    antes = list(ambiente.world.port_calls())
    resposta = await _invocar(client, chave, _GERENTE, unit_id="u-sem-concessao")
    assert resposta.status_code == HTTPStatus.FORBIDDEN
    autorizacoes = [c for c in ambiente.world.guard.calls if c.startswith("authorize")]
    assert len(autorizacoes) == 1  # só a da rota: o use case não rodou
    assert ambiente.world.port_calls() == antes


@pytest.mark.parametrize("chave", sorted(INVOCACOES), ids=lambda c: f"{c[0]} {c[1]}")
async def test_sem_credencial_e_401_antes_de_tudo(
    ambiente: Ambiente, client: AsyncClient, chave: tuple[str, str]
) -> None:
    resposta = await _invocar(client, chave, {})
    assert resposta.status_code == HTTPStatus.UNAUTHORIZED
    assert not [c for c in ambiente.world.guard.calls if c.startswith("authorize")]


# --- CA7: identificador inválido recusa antes de autorizar -----------------------------------


@pytest.mark.parametrize("chave", sorted(INVOCACOES), ids=lambda c: f"{c[0]} {c[1]}")
@pytest.mark.parametrize("unidade", [" ", "u%00"], ids=["espaco", "nul"])
async def test_ca7_unidade_invalida_no_path_e_422_sem_autorizar(
    ambiente: Ambiente, client: AsyncClient, chave: tuple[str, str], unidade: str
) -> None:
    ambiente.world.guard.calls.clear()
    resposta = await _invocar(client, chave, _GERENTE, unit_id=unidade)
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_identifier"
    assert not [c for c in ambiente.world.guard.calls if c.startswith("authorize")]


@pytest.mark.parametrize(
    "chave",
    [k for k in sorted(INVOCACOES) if "{schedule_id}" in k[1]],
    ids=lambda c: f"{c[0]} {c[1]}",
)
async def test_ca7_escala_invalida_no_path_e_422_sem_autorizar(
    ambiente: Ambiente, client: AsyncClient, chave: tuple[str, str]
) -> None:
    ambiente.world.guard.calls.clear()
    for invalido in ("s%00", "%20"):
        ambiente.world.guard.calls.clear()
        resposta = await _invocar(client, chave, _GERENTE, schedule_id=invalido)
        assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, invalido
        assert resposta.json()["code"] == "invalid_identifier"
        assert not [c for c in ambiente.world.guard.calls if c.startswith("authorize")]
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_identifier"
    assert not [c for c in ambiente.world.guard.calls if c.startswith("authorize")]


@pytest.mark.parametrize("rota", ["evaluations", "publications"])
async def test_ca7_id_de_criacao_nao_uuid_e_422_sem_autorizar(
    ambiente: Ambiente, client: AsyncClient, rota: str
) -> None:
    ambiente.world.guard.calls.clear()
    lote = [{**_LOTE_DA_ANA[0], "band_id": "f1"}]
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/s1/{rota}",
        json={"expected_version": 1, "operations": lote},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_identifier"
    assert not [c for c in ambiente.world.guard.calls if c.startswith("authorize")]


async def test_ca7_quantidade_acima_do_integer_e_422_de_scheduling(client: AsyncClient) -> None:
    sid = await _criar(client)
    lote = [_LOTE_DA_ANA[0], {**_LOTE_DA_ANA[1], "quantity": 2_147_483_648}]
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": lote},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_schedule_request"


@pytest.mark.parametrize(
    ("chave", "query"),
    [
        (
            ("GET", "/units/{unit_id}/calendar"),
            {"first_day": "0001-01-01", "last_day": "0001-01-02"},
        ),
        (("GET", "/units/{unit_id}/schedules"), {"before": "9999-12-31"}),
        (
            ("GET", "/units/{unit_id}/my-schedule"),
            {"first_day": "9999-12-30", "last_day": "9999-12-31"},
        ),
    ],
)
async def test_ca7_dia_extremo_e_422_e_nunca_500(
    client: AsyncClient, chave: tuple[str, str], query: dict[str, str]
) -> None:
    headers = _ANA if "my-schedule" in chave[1] else _GERENTE
    resposta = await client.get(_url(chave), params=query, headers=headers)
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_schedule_request"


async def test_ca7_s1_com_dia_extremo_e_422(client: AsyncClient) -> None:
    resposta = await client.post(
        f"{API}/units/{_U}/schedules", json={"first_day": "9999-12-31"}, headers=_GERENTE
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_schedule_request"


async def test_ca7_limite_de_faixa_extremo_e_422(client: AsyncClient) -> None:
    sid = await _criar(client)
    lote = [{**_LOTE_DA_ANA[0], "start": "0001-01-01T03:00:00", "end": "0001-01-01T05:00:00"}]
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/evaluations",
        json={"expected_version": 1, "operations": lote},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_schedule_request"


async def test_ca7_id_da_key_do_aceite_invalido_e_422_sem_autorizar(
    ambiente: Ambiente, client: AsyncClient
) -> None:
    ambiente.world.guard.calls.clear()
    aceite = {
        "key": {
            "policy": "over_coverage",
            "employee_id": "\x00",
            "demand_id": None,
            "operational_days": ["2026-11-02"],
            "assignment_ids": [],
        },
        "observed": "2",
        "limit": "1",
    }
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/s1/publications",
        json={"expected_version": 1, "operations": [], "acknowledgements": [aceite]},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_identifier"
    assert not [c for c in ambiente.world.guard.calls if c.startswith("authorize")]


async def test_ca7_medida_gigante_no_aceite_que_casa_a_key_e_422_e_nunca_500(
    client: AsyncClient,
) -> None:
    """A subtração do aceite estouraria o contexto decimal (`decimal.Overflow`) — 500."""
    sid = await _criar(client)
    excedente = [
        *_LOTE_DA_ANA,
        {
            "op": "assign_employee",
            "assignment_id": _ALOCACAO_2,
            "demand_id": _DEMANDA,
            "employee_id": "bia",
        },
    ]
    recusa = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": excedente},
        headers=_GERENTE,
    )
    aceites = [
        {"key": v["key"], "observed": "1E+1000000", "limit": v["limit"]}
        for v in recusa.json()["violations"]
    ]
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": excedente, "acknowledgements": aceites},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_schedule_request"


async def test_ca7_decimal_malformado_no_aceite_e_422_de_scheduling(client: AsyncClient) -> None:
    sid = await _criar(client)
    aceite = {
        "key": {
            "policy": "over_coverage",
            "employee_id": None,
            "demand_id": _DEMANDA,
            "operational_days": ["2026-11-02"],
            "assignment_ids": [],
        },
        "observed": "NaN",
        "limit": "1",
    }
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": _LOTE_DA_ANA, "acknowledgements": [aceite]},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["code"] == "invalid_schedule_request"


async def test_s5_o_recorte_chega_ao_use_case_na_ordem(client: AsyncClient) -> None:
    sid = await _criar(client)
    await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": _LOTE_DA_ANA},
        headers=_GERENTE,
    )
    cal = await client.get(
        f"{API}/units/{_U}/calendar",
        params={"first_day": "2026-11-01", "last_day": "2026-11-03"},
        headers=_GERENTE,
    )
    assert cal.status_code == HTTPStatus.OK, cal.text
    assert (cal.json()["first_day"], cal.json()["last_day"]) == ("2026-11-01", "2026-11-03")
    assert len(cal.json()["bands"]) == 1


async def test_s6_o_limite_chega_ao_use_case(client: AsyncClient) -> None:
    primeira = await _criar(client, "2026-11-02")
    segunda = await _criar(client, "2026-11-09")
    um = await client.get(
        f"{API}/units/{_U}/schedules",
        params={"before": "2026-11-30", "limit": 1},
        headers=_GERENTE,
    )
    assert [s["schedule_id"] for s in um.json()] == [segunda]
    dois = await client.get(
        f"{API}/units/{_U}/schedules", params={"before": "2026-11-30"}, headers=_GERENTE
    )
    assert [s["schedule_id"] for s in dois.json()] == [segunda, primeira]
    fora = await client.get(
        f"{API}/units/{_U}/schedules",
        params={"before": "2026-11-30", "limit": 53},
        headers=_GERENTE,
    )
    assert fora.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert fora.json()["code"] == "invalid_schedule_request"


# --- CA8: offset recusado -----------------------------------------------------------------


async def test_ca8_limite_com_offset_e_422_de_scheduling(client: AsyncClient) -> None:
    sid = await _criar(client)
    lote = [{**_LOTE_DA_ANA[0], "start": "2026-11-02T10:00:00Z"}]
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/evaluations",
        json={"expected_version": 1, "operations": lote},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (resposta.json()["type"], resposta.json()["code"]) == (
        "scheduling_error",
        "invalid_time_range",
    )


# --- CA5: a recusa otimista ---------------------------------------------------------------


async def test_ca5_a_propria_escala_mudou_409_com_a_versao_atual(client: AsyncClient) -> None:
    sid = await _criar(client)
    corpo = {"expected_version": 1, "operations": _LOTE_DA_ANA}
    primeira = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications", json=corpo, headers=_GERENTE
    )
    assert primeira.status_code == HTTPStatus.OK
    segunda = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications", json=corpo, headers=_GERENTE
    )
    assert segunda.status_code == HTTPStatus.CONFLICT
    recusa = segunda.json()
    assert recusa["code"] == "schedule_version_conflict"
    assert (recusa["expected_version"], recusa["current_version"]) == (1, 4)
    assert recusa["changed_neighbour_id"] is None


class _PublicaComVizinhaQueMudou:
    def execute(self, command: object) -> object:
        raise ScheduleVersionConflictError(2, 2, changed_neighbour_id="s-vizinha")


async def test_ca5_a_vizinha_mudou_409_com_o_id_e_as_versoes_iguais() -> None:
    ambiente = Ambiente(overrides={router_module._get_publish_schedule: _PublicaComVizinhaQueMudou})
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        resposta = await c.post(
            f"{API}/units/{_U}/schedules/s1/publications",
            json={"expected_version": 2, "operations": []},
            headers=_GERENTE,
        )
    assert resposta.status_code == HTTPStatus.CONFLICT
    corpo = resposta.json()
    assert corpo["changed_neighbour_id"] == "s-vizinha"
    assert corpo["expected_version"] == corpo["current_version"] == 2  # noqa: PLR2004


# --- CA9: nenhuma rota lê `scope.unit_id` ---------------------------------------------------


def _leituras_de_unit_id_do_escopo(fonte: str) -> list[int]:
    return [
        no.lineno
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Attribute)
        and no.attr == "unit_id"
        and isinstance(no.value, ast.Name)
        and no.value.id == "scope"
    ]


def test_ca9_nenhuma_rota_le_o_unit_id_do_escopo() -> None:
    assert _leituras_de_unit_id_do_escopo(inspect.getsource(router_module)) == []


def test_ca9_o_detector_reprova_um_caso_plantado() -> None:
    assert _leituras_de_unit_id_do_escopo("x = scope.unit_id\n") == [1]


def test_ca9_o_tenant_de_todo_command_vem_do_escopo() -> None:
    """Toda chamada `tenant_id=` no router lê `scope.tenant_id` — nenhuma outra origem."""
    origens = [
        ast.unparse(kw.value)
        for no in ast.walk(ast.parse(inspect.getsource(router_module)))
        if isinstance(no, ast.Call)
        for kw in no.keywords
        if kw.arg == "tenant_id"
    ]
    assert origens
    assert set(origens) == {"scope.tenant_id"}


# --- auditoria de testes (Task 11 extra) ------------------------------------------------------


async def test_a_demanda_orfa_sai_false_em_s2_e_s5(ambiente: Ambiente, client: AsyncClient) -> None:
    """A função estreitada para outra unidade: a demanda gravada fica e sai `false` (CA6)."""
    sid = await _criar(client)
    publicada = await client.post(
        f"{API}/units/{_U}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": _LOTE_DA_ANA[:2]},
        headers=_GERENTE,
    )
    assert publicada.status_code == HTTPStatus.OK, publicada.text
    ambiente.world.staff.add_job_function(
        T1, JobFunctionEntry(COOK, "Cozinheiro"), units=frozenset({"u2"})
    )
    lida = await client.get(f"{API}/units/{_U}/schedules/{sid}", headers=_GERENTE)
    cal = await client.get(
        f"{API}/units/{_U}/calendar",
        params={"first_day": "2026-11-02", "last_day": "2026-11-02"},
        headers=_GERENTE,
    )
    assert lida.json()["bands"][0]["demands"][0]["function_enabled_in_unit"] is False
    assert cal.json()["bands"][0]["demands"][0]["function_enabled_in_unit"] is False


_CORPO_DE_VALIDACAO = {"detail": "requisição inválida", "type": "validation_error"}


@pytest.mark.parametrize(
    "operacoes",
    [[{"op": "apagar_tudo"}], [{"op": "disable_band", "band_id": "f1"}] * 501],
    ids=["op-desconhecida", "lote-acima-de-500"],
)
async def test_corpo_fora_do_schema_e_422_do_framework_com_corpo_constante(
    ambiente: Ambiente, client: AsyncClient, operacoes: list[dict[str, str]]
) -> None:
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/s1/evaluations",
        json={"expected_version": 1, "operations": operacoes},
        headers=_GERENTE,
    )
    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json() == _CORPO_DE_VALIDACAO


async def test_sem_credencial_com_corpo_invalido_e_401_antes_do_422(client: AsyncClient) -> None:
    """A autenticação é `Depends`: roda antes da validação do corpo."""
    resposta = await client.post(
        f"{API}/units/{_U}/schedules/s1/evaluations",
        json={"expected_version": "x", "operations": [{"op": "apagar_tudo"}]},
    )
    assert resposta.status_code == HTTPStatus.UNAUTHORIZED


def _leituras_de_unit_id(fonte: str) -> list[int]:
    """Qualquer leitura de atributo `unit_id` — qualquer que seja o nome do objeto."""
    return [
        no.lineno
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Attribute) and no.attr == "unit_id" and isinstance(no.ctx, ast.Load)
    ]


def test_ca9_o_router_nao_le_unit_id_de_objeto_nenhum() -> None:
    """Mais forte que a trava por nome `scope`: renomear a variável não a contorna."""
    assert _leituras_de_unit_id(inspect.getsource(router_module)) == []


def test_ca9_o_detector_forte_reprova_outro_nome() -> None:
    assert _leituras_de_unit_id("s = guard.authorize(a)\nx = s.unit_id\n") == [2]

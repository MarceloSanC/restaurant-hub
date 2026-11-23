"""Faixas de status de scheduling pela API real — CA4 (metade e2e), CA7 e CA8 da Stage 4.5.

O mapa é verificado par a par em `test_http_error_handlers.py`; aqui prova-se que cada erro
**atravessa**: sobe do use case ou do domínio, passa pelo handler registrado em `create_app`
e chega ao cliente com o status do mapa, o discriminador `scheduling_error` e o `code`.

**Totalidade:** todo erro do mapa ou tem cenário aqui, ou está em `INALCANCAVEIS` com o
motivo (concept §6). Um erro novo no mapa sem cenário reprova
`test_todo_erro_do_mapa_tem_cenario_ou_e_inalcancavel`.
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus

import pytest
from httpx import AsyncClient, Response

from restaurant_hub.features.scheduling.adapters.inbound.http.error_handlers import (
    SCHEDULING_ERROR_STATUS,
    error_code,
)
from tests.e2e.features.scheduling.conftest import (
    API,
    SEGUNDA,
    Escala,
    auth,
    criar_escala,
    criar_funcao,
    criar_funcionario,
)

pytestmark = pytest.mark.e2e

_F1 = "11111111-1111-4111-8111-111111111111"
_F2 = "11111111-1111-4111-8111-111111111112"
_D1 = "22222222-2222-4222-8222-222222222221"
_D2 = "22222222-2222-4222-8222-222222222222"
_A1 = "33333333-3333-4333-8333-333333333331"
_A2 = "33333333-3333-4333-8333-333333333332"

# Inalcançáveis por HTTP na Stage 4.5 (concept §6): entrada por totalidade.
INALCANCAVEIS = {
    "invalid_weekday": "a configuração de escala é editada na Stage 4.8",
    "invalid_day_cutoff": "a configuração de escala é editada na Stage 4.8",
    "invalid_validation_config": "a configuração de escala é editada na Stage 4.8",
    "invalid_evaluation_input": "o insumo do avaliador é montado pelo use case",
    "invalid_schedule_version": "a versão comparada é a lida do banco",
}


def _faixa(bid: str, inicio: str = "10:00", fim: str = "16:00", dia: str = SEGUNDA) -> dict:
    return {
        "op": "enable_band",
        "band_id": bid,
        "start": f"{dia}T{inicio}:00",
        "end": f"{dia}T{fim}:00",
    }


def _demanda(did: str, funcao: str, bid: str = _F1, quantidade: int = 1) -> dict:
    return {
        "op": "declare_demand",
        "demand_id": did,
        "band_id": bid,
        "job_function_id": funcao,
        "quantity": quantidade,
    }


def _alocacao(aid: str, funcionario: str, did: str = _D1) -> dict:
    return {
        "op": "assign_employee",
        "assignment_id": aid,
        "demand_id": did,
        "employee_id": funcionario,
    }


class _Contexto:
    """O cenário de cada teste: a escala criada, o gerente e os atalhos de publicação."""

    def __init__(self, client: AsyncClient, escala: Escala, sid: str) -> None:
        self.client, self.escala, self.sid = client, escala, sid
        self.gerente = auth(escala.base.manager)
        self.versao = 1

    def base(self) -> list[dict]:
        return [
            _faixa(_F1),
            _demanda(_D1, self.escala.funcao),
            _alocacao(_A1, self.escala.ana_id),
        ]

    async def publicar(self, lote: list[dict]) -> Response:
        resposta = await self.client.post(
            f"{API}/units/{self.escala.unidade}/schedules/{self.sid}/publications",
            json={"expected_version": self.versao, "operations": lote},
            headers=self.gerente,
        )
        if resposta.status_code == HTTPStatus.OK:
            self.versao = resposta.json()["summary"]["version"]
        return resposta

    async def preparar(self, lote: list[dict]) -> None:
        resposta = await self.publicar(lote)
        assert resposta.status_code == HTTPStatus.OK, resposta.text


Cenario = Callable[[_Contexto], Awaitable[Response]]


Lote = Callable[[_Contexto], list[dict]]


def _lote(construir: Lote, antes: Lote | None = None) -> Cenario:
    async def cenario(ctx: _Contexto) -> Response:
        if antes is not None:
            await ctx.preparar(antes(ctx))
        return await ctx.publicar(construir(ctx))

    return cenario


async def _segunda_funcao(ctx: _Contexto) -> str:
    return await criar_funcao(
        ctx.client, auth(ctx.escala.base.owner), [ctx.escala.unidade], "Atendente da faixa"
    )


async def _desligar(ctx: _Contexto, employee_id: str) -> None:
    resposta = await ctx.client.post(
        f"{API}/units/{ctx.escala.unidade}/employees/{employee_id}/termination",
        headers=ctx.gerente,
    )
    assert resposta.status_code == HTTPStatus.OK, resposta.text


async def _escala_nao_encontrada(ctx: _Contexto) -> Response:
    return await ctx.client.get(
        f"{API}/units/{ctx.escala.unidade}/schedules/nao-existe", headers=ctx.gerente
    )


async def _versao_vencida(ctx: _Contexto) -> Response:
    ctx.versao = 7
    return await ctx.publicar([_faixa(_F1)])


async def _periodo_tomado(ctx: _Contexto) -> Response:
    return await ctx.client.post(
        f"{API}/units/{ctx.escala.unidade}/schedules",
        json={"first_day": SEGUNDA},
        headers=ctx.gerente,
    )


async def _periodo_desalinhado(ctx: _Contexto) -> Response:
    return await ctx.client.post(
        f"{API}/units/{ctx.escala.unidade}/schedules",
        json={"first_day": "2030-01-15"},  # terça
        headers=ctx.gerente,
    )


async def _recorte_longo(ctx: _Contexto) -> Response:
    return await ctx.client.get(
        f"{API}/units/{ctx.escala.unidade}/calendar",
        params={"first_day": SEGUNDA, "last_day": "2030-03-31"},
        headers=ctx.gerente,
    )


async def _identificador_invalido(ctx: _Contexto) -> Response:
    return await ctx.client.get(f"{API}/units/%20/schedules/{ctx.sid}", headers=ctx.gerente)


async def _funcionario_inativo(ctx: _Contexto) -> Response:
    await _desligar(ctx, ctx.escala.bruno_id)
    return await ctx.publicar(
        [_faixa(_F1), _demanda(_D1, ctx.escala.funcao), _alocacao(_A1, ctx.escala.bruno_id)]
    )


async def _alocacoes_inativas(ctx: _Contexto) -> Response:
    await ctx.preparar(
        [_faixa(_F1), _demanda(_D1, ctx.escala.funcao), _alocacao(_A1, ctx.escala.bruno_id)]
    )
    await _desligar(ctx, ctx.escala.bruno_id)
    return await ctx.publicar([{"op": "withdraw_demand", "demand_id": _D1}])


async def _registros_ausentes(ctx: _Contexto) -> Response:
    dani = await criar_funcionario(
        ctx.client, ctx.gerente, ctx.escala.unidade, "Dani", ctx.escala.funcao
    )
    await ctx.preparar([_faixa(_F1), _demanda(_D1, ctx.escala.funcao), _alocacao(_A1, dani)])
    removido = await ctx.client.delete(
        f"{API}/units/{ctx.escala.unidade}/employees/{dani}", headers=ctx.gerente
    )
    assert removido.status_code == HTTPStatus.NO_CONTENT, removido.text
    return await ctx.client.get(
        f"{API}/units/{ctx.escala.unidade}/schedules/{ctx.sid}", headers=ctx.gerente
    )


async def _funcao_nao_habilitada(ctx: _Contexto) -> Response:
    outra = await criar_funcao(
        ctx.client, auth(ctx.escala.base.owner), [ctx.escala.base.unidade_b], "Só na praia"
    )
    return await ctx.publicar([_faixa(_F1), _demanda(_D1, outra)])


async def _duplicada_na_faixa(ctx: _Contexto) -> Response:
    atendente = await _segunda_funcao(ctx)
    await ctx.preparar([_faixa(_F1), _demanda(_D1, ctx.escala.funcao), _demanda(_D2, atendente)])
    return await ctx.publicar(
        [_alocacao(_A1, ctx.escala.ana_id, _D1), _alocacao(_A2, ctx.escala.ana_id, _D2)]
    )


# code → (status esperado, cenário)
CENARIOS: dict[str, tuple[HTTPStatus, Cenario]] = {
    "schedule_not_found": (HTTPStatus.NOT_FOUND, _escala_nao_encontrada),
    "staff_member_not_found": (
        HTTPStatus.NOT_FOUND,
        _lote(
            lambda c: [_alocacao(_A1, "nao-existe")],
            lambda c: [_faixa(_F1), _demanda(_D1, c.escala.funcao)],
        ),
    ),
    "job_function_not_found": (
        HTTPStatus.NOT_FOUND,
        _lote(lambda c: [_demanda(_D1, "nao-existe")], lambda c: [_faixa(_F1)]),
    ),
    "schedule_version_conflict": (HTTPStatus.CONFLICT, _versao_vencida),
    "schedule_period_taken": (HTTPStatus.CONFLICT, _periodo_tomado),
    "identifier_in_use": (
        HTTPStatus.CONFLICT,
        _lote(lambda c: [_faixa(_F1, "17:00", "20:00")], lambda c: [_faixa(_F1)]),
    ),
    "inactive_staff_member": (HTTPStatus.CONFLICT, _funcionario_inativo),
    "job_function_not_enabled_in_unit": (HTTPStatus.CONFLICT, _funcao_nao_habilitada),
    "inactive_allocations_in_use": (HTTPStatus.CONFLICT, _alocacoes_inativas),
    "missing_staff_records": (HTTPStatus.CONFLICT, _registros_ausentes),
    "shift_band_in_use": (
        HTTPStatus.CONFLICT,
        _lote(lambda c: [{"op": "disable_band", "band_id": _F1}], lambda c: c.base()),
    ),
    "shift_demand_in_use": (
        HTTPStatus.CONFLICT,
        _lote(lambda c: [{"op": "withdraw_demand", "demand_id": _D1}], lambda c: c.base()),
    ),
    "blocking_violations": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(
            lambda c: [
                *c.base(),
                _faixa(_F2, "14:00", "18:00"),
                _demanda(_D2, c.escala.funcao, _F2),
                _alocacao(_A2, c.escala.ana_id, _D2),
            ]
        ),
    ),
    "unacknowledged_violations": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [*c.base(), _alocacao(_A2, c.escala.bruno_id)]),
    ),
    "invalid_schedule_request": (HTTPStatus.UNPROCESSABLE_ENTITY, _recorte_longo),
    "invalid_identifier": (HTTPStatus.UNPROCESSABLE_ENTITY, _identificador_invalido),
    "invalid_time_range": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [_faixa(_F1, "16:00", "10:00")]),
    ),
    "invalid_schedule_period": (HTTPStatus.UNPROCESSABLE_ENTITY, _periodo_desalinhado),
    "invalid_demand_quantity": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [_faixa(_F1), _demanda(_D1, c.escala.funcao, quantidade=-1)]),
    ),
    "invalid_assignment_break": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(
            lambda c: [
                {"op": "declare_allocation_break", "assignment_id": _A1, "break_minutes": 999}
            ],
            lambda c: c.base(),
        ),
    ),
    "duplicate_entity_id": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [_faixa(_F1), _faixa(_F1, "17:00", "20:00")]),
    ),
    "duplicate_shift_band": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [_faixa(_F1), _faixa(_F2)]),
    ),
    "duplicate_shift_demand": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(
            lambda c: [_faixa(_F1), _demanda(_D1, c.escala.funcao), _demanda(_D2, c.escala.funcao)]
        ),
    ),
    "duplicate_assignment": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [_alocacao(_A2, c.escala.ana_id)], lambda c: c.base()),
    ),
    "duplicate_assignment_in_band": (HTTPStatus.UNPROCESSABLE_ENTITY, _duplicada_na_faixa),
    "shift_band_not_found": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [{"op": "disable_band", "band_id": "nao-existe"}]),
    ),
    "shift_band_day_change": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(
            lambda c: [
                {
                    "op": "reschedule_band",
                    "band_id": _F1,
                    "start": "2030-01-08T10:00:00",
                    "end": "2030-01-08T16:00:00",
                }
            ],
            lambda c: [_faixa(_F1)],
        ),
    ),
    "time_range_outside_period": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [_faixa(_F1, dia="2030-01-25")]),
    ),
    "shift_demand_not_found": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [{"op": "withdraw_demand", "demand_id": "nao-existe"}]),
    ),
    "assignment_not_found": (
        HTTPStatus.UNPROCESSABLE_ENTITY,
        _lote(lambda c: [{"op": "unassign_employee", "assignment_id": "nao-existe"}]),
    ),
}


def test_todo_erro_do_mapa_tem_cenario_ou_e_inalcancavel() -> None:
    codes = {error_code(classe.__new__(classe)) for classe in SCHEDULING_ERROR_STATUS}
    assert set(CENARIOS) | set(INALCANCAVEIS) == codes
    assert not set(CENARIOS) & set(INALCANCAVEIS)


def test_o_status_do_cenario_e_o_do_mapa() -> None:
    por_code = {
        error_code(classe.__new__(classe)): status
        for classe, status in SCHEDULING_ERROR_STATUS.items()
    }
    assert {code: int(status) for code, (status, _) in CENARIOS.items()} == {
        code: por_code[code] for code in CENARIOS
    }


@pytest.mark.parametrize("code", sorted(CENARIOS))
async def test_cada_erro_alcancavel_atravessa_a_api_real(
    client: AsyncClient, escala: Escala, code: str
) -> None:
    sid = await criar_escala(client, auth(escala.base.manager), escala.unidade)
    status, cenario = CENARIOS[code]
    resposta = await cenario(_Contexto(client, escala, sid))
    assert resposta.status_code == status, resposta.text
    assert (resposta.json()["type"], resposta.json()["code"]) == ("scheduling_error", code)


# --- CA7 e CA8: entradas adversariais, nunca 500 ----------------------------------------------


async def test_ca7_ca8_entradas_adversariais_recusam_com_422_de_scheduling(
    client: AsyncClient, escala: Escala
) -> None:
    gerente = auth(escala.base.manager)
    sid = await criar_escala(client, gerente, escala.unidade)
    url = f"{API}/units/{escala.unidade}/schedules/{sid}"
    lotes = {
        "invalid_identifier": [{**_faixa(_F1), "band_id": "f1"}],
        "invalid_schedule_request": [_faixa(_F1), _demanda(_D1, escala.funcao, 2_147_483_648)],
        "invalid_time_range": [{**_faixa(_F1), "start": f"{SEGUNDA}T10:00:00Z"}],
    }
    # Lotes que só valem sobre a faixa e a demanda já gravadas.
    await client.post(
        f"{url}/publications",
        json={"expected_version": 1, "operations": [_faixa(_F1), _demanda(_D1, escala.funcao)]},
        headers=gerente,
    )
    sobre_a_gravada = {
        "invalid_schedule_request": [
            {"op": "change_demand_quantity", "demand_id": _D1, "quantity": 2_147_483_648}
        ],
        "invalid_identifier": [{"op": "withdraw_demand", "demand_id": "  "}],
    }
    for code, lote in sobre_a_gravada.items():
        resposta = await client.post(
            f"{url}/evaluations", json={"expected_version": 3, "operations": lote}, headers=gerente
        )
        assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (code, resposta.text)
        assert resposta.json()["code"] == code
    faixa_extrema = [{**_faixa(_F2), "start": "9999-12-31T10:00:00", "end": "9999-12-31T16:00:00"}]
    extrema = await client.post(
        f"{url}/evaluations",
        json={"expected_version": 3, "operations": faixa_extrema},
        headers=gerente,
    )
    assert (extrema.status_code, extrema.json()["code"]) == (422, "invalid_schedule_request")
    for code, lote in lotes.items():
        resposta = await client.post(
            f"{url}/evaluations", json={"expected_version": 1, "operations": lote}, headers=gerente
        )
        assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, (code, resposta.text)
        assert resposta.json()["code"] == code

    nul = await client.get(f"{API}/units/u%00/schedules/{sid}", headers=gerente)
    assert (nul.status_code, nul.json()["code"]) == (422, "invalid_identifier")

    extremo = await client.get(
        f"{API}/units/{escala.unidade}/calendar",
        params={"first_day": "9999-12-30", "last_day": "9999-12-31"},
        headers=gerente,
    )
    assert (extremo.status_code, extremo.json()["code"]) == (422, "invalid_schedule_request")

    aceite = {
        "key": {
            "policy": "over_coverage",
            "employee_id": None,
            "demand_id": _D1,
            "operational_days": [SEGUNDA],
            "assignment_ids": [],
        },
        "observed": "NaN",
        "limit": "1",
    }
    decimal = await client.post(
        f"{url}/publications",
        json={"expected_version": 1, "operations": [], "acknowledgements": [aceite]},
        headers=gerente,
    )
    assert (decimal.status_code, decimal.json()["code"]) == (422, "invalid_schedule_request")

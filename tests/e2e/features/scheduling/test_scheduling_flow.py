"""E2E do editor e de "minha escala" — o DoD da Stage 4.5 contra Postgres real.

"montar demanda → alocar → ver violações → aceitar warn → publicar → funcionário consulta a
própria escala" (roadmap §Stage 4.5 › `definition_of_done`), mais CA3 (só os próprios turnos;
registro desligado vê vazio), CA5 (a recusa otimista da própria escala) e CA6 (a função que
deixou de valer na unidade: recusa e sinalização).
"""

from http import HTTPStatus

import pytest
from httpx import AsyncClient

from tests.e2e.features.scheduling.conftest import (
    API,
    DOMINGO,
    SEGUNDA,
    SENHA_DO_FUNCIONARIO,
    Escala,
    auth,
    criar_escala,
    criar_funcao,
    fazer_login,
)

pytestmark = pytest.mark.e2e

_FAIXA = "11111111-1111-4111-8111-111111111111"
_DEMANDA = "22222222-2222-4222-8222-222222222222"
_ALOCACAO_ANA = "33333333-3333-4333-8333-333333333333"
_ALOCACAO_BRUNO = "44444444-4444-4444-8444-444444444444"
_DEMANDA_GARCOM = "55555555-5555-4555-8555-555555555555"


def _lote(escala: Escala, quantidade: int = 1) -> list[dict[str, object]]:
    """Uma faixa de segunda 10h-16h, a demanda de cozinheiro e as alocações de Ana e Bruno."""
    return [
        {
            "op": "enable_band",
            "band_id": _FAIXA,
            "start": f"{SEGUNDA}T10:00:00",
            "end": f"{SEGUNDA}T16:00:00",
        },
        {
            "op": "declare_demand",
            "demand_id": _DEMANDA,
            "band_id": _FAIXA,
            "job_function_id": escala.funcao,
            "quantity": quantidade,
        },
        {
            "op": "assign_employee",
            "assignment_id": _ALOCACAO_ANA,
            "demand_id": _DEMANDA,
            "employee_id": escala.ana_id,
        },
        {
            "op": "assign_employee",
            "assignment_id": _ALOCACAO_BRUNO,
            "demand_id": _DEMANDA,
            "employee_id": escala.bruno_id,
        },
    ]


async def _minha_escala(client: AsyncClient, escala: Escala, tokens: dict) -> dict:
    resposta = await client.get(
        f"{API}/units/{escala.unidade}/my-schedule",
        params={"first_day": SEGUNDA, "last_day": DOMINGO},
        headers=auth(tokens),
    )
    assert resposta.status_code == HTTPStatus.OK, resposta.text
    return dict(resposta.json())


async def test_ca1_dod_montar_alocar_ver_violacoes_aceitar_publicar_e_minha_escala(
    client: AsyncClient, escala: Escala
) -> None:
    gerente = auth(escala.base.manager)
    sid = await criar_escala(client, gerente, escala.unidade)
    lote = _lote(escala)  # N = 1 com duas alocações: sobre-cobertura, `warn` por default

    # Ver as violações que o lote introduz, sem gravar.
    avaliada = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/evaluations",
        json={"expected_version": 1, "operations": lote},
        headers=gerente,
    )
    assert avaliada.status_code == HTTPStatus.OK, avaliada.text
    avaliacao = avaliada.json()
    assert avaliacao["blocking"] == []
    assert [v["policy"] for v in avaliacao["warnings"]] == ["over_coverage"]

    # Publicar sem aceite: o servidor pede o aceite.
    sem_aceite = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": lote},
        headers=gerente,
    )
    assert sem_aceite.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    recusa = sem_aceite.json()
    assert (recusa["type"], recusa["code"]) == ("scheduling_error", "unacknowledged_violations")

    # Aceitar o aviso e publicar: a versão soma 1 por operação efetiva.
    aceites = [
        {"key": v["key"], "observed": v["observed"], "limit": v["limit"]}
        for v in recusa["violations"]
    ]
    publicada = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": lote, "acknowledgements": aceites},
        headers=gerente,
    )
    assert publicada.status_code == HTTPStatus.OK, publicada.text
    assert publicada.json()["summary"]["version"] == 1 + len(lote)

    lida = await client.get(f"{API}/units/{escala.unidade}/schedules/{sid}", headers=gerente)
    assert lida.json()["summary"]["version"] == 1 + len(lote)
    assert [v["policy"] for v in lida.json()["violations"]] == ["over_coverage"]

    # O funcionário consulta a própria escala — só o próprio turno.
    minha = await _minha_escala(client, escala, escala.ana)
    (turno,) = minha["shifts"]
    assert turno["employee_id"] == escala.ana_id
    assert (turno["start"], turno["end"]) == (f"{SEGUNDA}T10:00:00", f"{SEGUNDA}T16:00:00")


async def test_ca3_cada_um_ve_so_o_proprio_e_o_desligado_ve_vazio(
    client: AsyncClient, escala: Escala
) -> None:
    gerente = auth(escala.base.manager)
    sid = await criar_escala(client, gerente, escala.unidade)
    publicada = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": _lote(escala, quantidade=2)},
        headers=gerente,
    )
    assert publicada.status_code == HTTPStatus.OK, publicada.text

    ana = await _minha_escala(client, escala, escala.ana)
    bruno = await _minha_escala(client, escala, escala.bruno)
    assert [t["employee_id"] for t in ana["shifts"]] == [escala.ana_id]
    assert [t["employee_id"] for t in bruno["shifts"]] == [escala.bruno_id]

    # Bruno, alocado no recorte, é desligado: as sessões caem (ADR 3.5.0003), ele entra de novo
    # e "minha escala" volta vazia — o corte estrutural pelo registro (D-DEACT).
    desligado = await client.post(
        f"{API}/units/{escala.unidade}/employees/{escala.bruno_id}/termination",
        headers=gerente,
    )
    assert desligado.status_code == HTTPStatus.OK, desligado.text
    de_novo = await fazer_login(client, "bruno@cantina.com", SENHA_DO_FUNCIONARIO)
    assert (await _minha_escala(client, escala, de_novo))["shifts"] == []


async def test_ca3_funcionario_de_outra_unidade_nao_le_minha_escala_aqui(
    client: AsyncClient, escala: Escala
) -> None:
    resposta = await client.get(
        f"{API}/units/{escala.unidade}/my-schedule",
        params={"first_day": SEGUNDA, "last_day": DOMINGO},
        headers=auth(escala.caio),
    )
    assert resposta.status_code == HTTPStatus.FORBIDDEN
    assert resposta.json() == {"detail": "acesso negado", "type": "forbidden"}


async def test_ca5_duas_publicacoes_sobre_a_mesma_versao_a_segunda_recebe_409(
    client: AsyncClient, escala: Escala
) -> None:
    gerente = auth(escala.base.manager)
    sid = await criar_escala(client, gerente, escala.unidade)
    corpo = {"expected_version": 1, "operations": _lote(escala, quantidade=2)}
    primeira = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications", json=corpo, headers=gerente
    )
    assert primeira.status_code == HTTPStatus.OK, primeira.text
    segunda = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications", json=corpo, headers=gerente
    )
    assert segunda.status_code == HTTPStatus.CONFLICT
    recusa = segunda.json()
    assert recusa["code"] == "schedule_version_conflict"
    assert recusa["changed_neighbour_id"] is None
    assert recusa["expected_version"] == 1
    assert recusa["current_version"] == primeira.json()["summary"]["version"]


async def test_ca6_funcao_nao_habilitada_recusa_e_a_orfa_aparece_sinalizada(
    client: AsyncClient, escala: Escala
) -> None:
    gerente = auth(escala.base.manager)
    dono = auth(escala.base.owner)
    # Uma segunda função, sem registro que a detenha na unidade — staff só estreita a função
    # que ninguém da unidade detém (ADR 3.11.0001).
    garcom = await criar_funcao(
        client, dono, [escala.unidade, escala.base.unidade_b], "Garçom da escala"
    )
    sid = await criar_escala(client, gerente, escala.unidade)
    lote = [
        *_lote(escala, quantidade=2),
        {
            "op": "declare_demand",
            "demand_id": _DEMANDA_GARCOM,
            "band_id": _FAIXA,
            "job_function_id": garcom,
            "quantity": 1,
        },
    ]
    publicada = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": lote},
        headers=gerente,
    )
    assert publicada.status_code == HTTPStatus.OK, publicada.text
    versao = publicada.json()["summary"]["version"]

    async def _sinais() -> list[dict[str, bool]]:
        lida = await client.get(f"{API}/units/{escala.unidade}/schedules/{sid}", headers=gerente)
        cal = await client.get(
            f"{API}/units/{escala.unidade}/calendar",
            params={"first_day": SEGUNDA, "last_day": DOMINGO},
            headers=gerente,
        )
        assert lida.status_code == cal.status_code == HTTPStatus.OK
        return [
            {d["demand_id"]: d["function_enabled_in_unit"] for d in corpo["bands"][0]["demands"]}
            for corpo in (lida.json(), cal.json())
        ]

    esperado = {_DEMANDA: True, _DEMANDA_GARCOM: True}
    assert await _sinais() == [esperado, esperado]

    # Staff estreita o garçom para a outra unidade: a demanda gravada fica (D1) e sai órfã.
    estreitada = await client.put(
        f"{API}/job-functions/{garcom}/units",
        json={"unit_ids": [escala.base.unidade_b]},
        headers=dono,
    )
    assert estreitada.status_code == HTTPStatus.OK, estreitada.text
    esperado = {_DEMANDA: True, _DEMANDA_GARCOM: False}
    assert await _sinais() == [esperado, esperado]

    # Aumentar o N da demanda órfã é introduzi-la: 409 com a função.
    aumento = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={
            "expected_version": versao,
            "operations": [
                {"op": "change_demand_quantity", "demand_id": _DEMANDA_GARCOM, "quantity": 3}
            ],
        },
        headers=gerente,
    )
    assert aumento.status_code == HTTPStatus.CONFLICT
    assert (aumento.json()["code"], aumento.json()["job_function_id"]) == (
        "job_function_not_enabled_in_unit",
        garcom,
    )

    # Reduzir passa (D1): a demanda órfã não trava a edição que não a introduz.
    reducao = await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={
            "expected_version": versao,
            "operations": [
                {"op": "change_demand_quantity", "demand_id": _DEMANDA_GARCOM, "quantity": 0}
            ],
        },
        headers=gerente,
    )
    assert reducao.status_code == HTTPStatus.OK, reducao.text

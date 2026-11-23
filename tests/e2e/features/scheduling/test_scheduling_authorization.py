"""Matriz e2e papel x rota de scheduling — CA2 da Stage 4.5, contra Postgres real.

Oito atores contra as sete rotas, na unidade A do cenário: permitido onde o mapa de papéis
da Stage 4.5 concede (ADR 4.5.0001; concept §4.4), 403 de identity com o corpo **constante**
no resto. O dono e o gerente membro gerenciam; o RH membro lê e vê a própria; o funcionário
membro só vê a própria; o gerente e o funcionário de **outra** unidade, o dono de **outro**
restaurante e o `platform_admin` são negados em tudo.

A autorização da **rota** é provada pelo teste de borda com espião (CA14, unitário): aqui a
decisão é a de ponta a ponta — rota e use case juntos.
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient, Response

from restaurant_hub.features.scheduling.adapters.inbound.http.router import (
    router as scheduling_router,
)
from tests.e2e.features.identity.conftest import login_do_dono
from tests.e2e.features.scheduling.conftest import (
    API,
    DOMINGO,
    SEGUNDA,
    SENHA_PADRAO,
    Escala,
    auth,
    criar_escala,
    fazer_login,
)
from tests.e2e.features.staff.conftest import ADMIN_EMAIL
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e

_CORPO_403 = {"detail": "acesso negado", "type": "forbidden"}
_OUTRA_SEMANA = "2030-01-14"

Rota = Callable[[AsyncClient, Escala, str, dict[str, str]], Awaitable[Response]]


async def _s1(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.post(
        f"{API}/units/{escala.unidade}/schedules", json={"first_day": _OUTRA_SEMANA}, headers=h
    )


async def _s2(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.get(f"{API}/units/{escala.unidade}/schedules/{sid}", headers=h)


async def _s3(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/evaluations",
        json={"expected_version": 1, "operations": []},
        headers=h,
    )


async def _s4(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.post(
        f"{API}/units/{escala.unidade}/schedules/{sid}/publications",
        json={"expected_version": 1, "operations": []},
        headers=h,
    )


async def _s5(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.get(
        f"{API}/units/{escala.unidade}/calendar",
        params={"first_day": SEGUNDA, "last_day": DOMINGO},
        headers=h,
    )


async def _s6(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.get(
        f"{API}/units/{escala.unidade}/schedules", params={"before": "2030-12-31"}, headers=h
    )


async def _s7(client: AsyncClient, escala: Escala, sid: str, h: dict[str, str]) -> Response:
    return await client.get(
        f"{API}/units/{escala.unidade}/my-schedule",
        params={"first_day": SEGUNDA, "last_day": DOMINGO},
        headers=h,
    )


ROTAS: dict[str, tuple[Rota, HTTPStatus]] = {
    "S1 criar": (_s1, HTTPStatus.CREATED),
    "S2 ler": (_s2, HTTPStatus.OK),
    "S3 avaliar": (_s3, HTTPStatus.OK),
    "S4 publicar": (_s4, HTTPStatus.OK),
    "S5 calendario": (_s5, HTTPStatus.OK),
    "S6 anteriores": (_s6, HTTPStatus.OK),
    "S7 minha escala": (_s7, HTTPStatus.OK),
}

_TODAS = frozenset(ROTAS)
_LER = frozenset({"S2 ler", "S5 calendario", "S6 anteriores"})
_PROPRIA = frozenset({"S7 minha escala"})

# A matriz da §4.4 do concept, transcrita (não derivada do mapa de papéis).
PERMITIDAS: dict[str, frozenset[str]] = {
    "dono": _TODAS,
    "gerente membro": _TODAS,
    "gerente de outra unidade": frozenset(),
    "rh membro": _LER | _PROPRIA,
    "funcionario membro": _PROPRIA,
    "funcionario de outra unidade": frozenset(),
    "dono de outro restaurante": frozenset(),
    "platform_admin": frozenset(),
}


async def _gerente_da_unidade_b(client: AsyncClient, escala: Escala) -> dict:
    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "gerente-b@cantina.com",
            "password": SENHA_PADRAO,
            "role": "manager",
            "unit_ids": [escala.base.unidade_b],
        },
        headers=auth(escala.base.owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return await fazer_login(client, "gerente-b@cantina.com")


async def _dono_de_outro_restaurante(client: AsyncClient, caixa: RecordingEmailSender) -> dict:
    admin = await fazer_login(client, ADMIN_EMAIL)
    resposta = await client.post(
        f"{API}/restaurants",
        json={"name": "Outro Restaurante", "owner": {"email": "dono@outro.com"}},
        headers=auth(admin),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return await login_do_dono(client, caixa, "dono@outro.com")


async def _tokens(  # noqa: PLR0911 — um ramo por ator da matriz
    ator: str, client: AsyncClient, escala: Escala, caixa: RecordingEmailSender
) -> dict:
    match ator:
        case "dono":
            return escala.base.owner
        case "gerente membro":
            return escala.base.manager
        case "gerente de outra unidade":
            return await _gerente_da_unidade_b(client, escala)
        case "rh membro":
            return escala.hr
        case "funcionario membro":
            return escala.ana
        case "funcionario de outra unidade":
            return escala.caio
        case "dono de outro restaurante":
            return await _dono_de_outro_restaurante(client, caixa)
        case "platform_admin":
            return await fazer_login(client, ADMIN_EMAIL)
    raise AssertionError(ator)


# Cada rota da matriz e o par (método, caminho) do router que ela exercita.
_ENDERECOS: dict[str, tuple[str, str]] = {
    "S1 criar": ("POST", "/units/{unit_id}/schedules"),
    "S2 ler": ("GET", "/units/{unit_id}/schedules/{schedule_id}"),
    "S3 avaliar": ("POST", "/units/{unit_id}/schedules/{schedule_id}/evaluations"),
    "S4 publicar": ("POST", "/units/{unit_id}/schedules/{schedule_id}/publications"),
    "S5 calendario": ("GET", "/units/{unit_id}/calendar"),
    "S6 anteriores": ("GET", "/units/{unit_id}/schedules"),
    "S7 minha escala": ("GET", "/units/{unit_id}/my-schedule"),
}


def test_a_matriz_e_total_sobre_o_router_de_scheduling() -> None:
    """Uma rota nova no router (a da configuração, na 4.8) reprova aqui até entrar na matriz."""
    rotas = {
        (metodo, rota.path)
        for rota in scheduling_router.routes
        if isinstance(rota, APIRoute)
        for metodo in rota.methods
    }
    assert set(_ENDERECOS) == set(ROTAS)
    assert set(_ENDERECOS.values()) == rotas
    assert len(PERMITIDAS) == 8  # noqa: PLR2004
    assert all(permitidas <= _TODAS for permitidas in PERMITIDAS.values())


@pytest.mark.parametrize("rota", sorted(ROTAS))
@pytest.mark.parametrize("ator", sorted(PERMITIDAS))
async def test_ca2_matriz_papel_por_rota(
    client: AsyncClient,
    escala: Escala,
    caixa_de_entrada: RecordingEmailSender,
    ator: str,
    rota: str,
) -> None:
    sid = await criar_escala(client, auth(escala.base.manager), escala.unidade)
    tokens = await _tokens(ator, client, escala, caixa_de_entrada)
    chamar, sucesso = ROTAS[rota]

    resposta = await chamar(client, escala, sid, auth(tokens))

    if rota in PERMITIDAS[ator]:
        assert resposta.status_code == sucesso, resposta.text
    else:
        assert resposta.status_code == HTTPStatus.FORBIDDEN, resposta.text
        assert resposta.json() == _CORPO_403

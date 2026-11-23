"""Fixtures dos e2e de scheduling — app real (composition root de produção) contra Postgres.

O cenário vem **inteiro pela API**, como em staff: restaurante, duas unidades, a função de
trabalho habilitada na unidade A, o gerente (membro das duas unidades), o RH (membro de A), dois
funcionários com login por R17 (Ana e Bruno, registros na unidade A) e um funcionário com
login na unidade B (Caio). O único objeto semeado fora da API é o `platform_admin`, que
nenhuma rota cria. O token que scheduling recebe é, assim, um token emitido pela aplicação,
com o tenant no lugar que o ADR 0.0.0005 exige.

Semana de referência: segunda 2030-01-07 (calendário default — segunda, corte às 05:00).
"""

from dataclasses import dataclass
from http import HTTPStatus

import pytest
from httpx import AsyncClient

from tests.e2e.features.staff.conftest import (
    API,
    SENHA_PADRAO,
    Cenario,
    admin_semeado,
    app_e2e,
    auth,
    caixa_de_entrada,
    cenario,
    client,
    fazer_login,
    settings_e2e,
)

__all__ = [
    "admin_semeado",
    "app_e2e",
    "caixa_de_entrada",
    "cenario",
    "client",
    "settings_e2e",
]

SEGUNDA = "2030-01-07"
DOMINGO = "2030-01-13"
SENHA_DO_FUNCIONARIO = "s3nha-do-funcionario-escala"


def token_de(link: str) -> str:
    _, _, resto = link.partition("token=")
    return resto.split()[0]


async def criar_funcao(
    client: AsyncClient, cabecalho: dict[str, str], unidades: list[str], nome: str
) -> str:
    resposta = await client.post(
        f"{API}/job-functions", json={"name": nome, "unit_ids": unidades}, headers=cabecalho
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["id"])


async def criar_funcionario(
    client: AsyncClient, cabecalho: dict[str, str], unidade: str, nome: str, funcao: str
) -> str:
    resposta = await client.post(
        f"{API}/units/{unidade}/employees",
        json={
            "name": nome,
            "workload_profile": {"type": "on_demand"},
            "job_function_ids": [funcao],
        },
        headers=cabecalho,
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["id"])


async def dar_login(
    client: AsyncClient, cabecalho: dict[str, str], unidade: str, employee_id: str, email: str
) -> dict:
    """R17 pelo canal `link`, define a senha e faz login: o token do funcionário."""
    criado = await client.post(
        f"{API}/units/{unidade}/employees/{employee_id}/login",
        json={"email": email, "delivery": "link"},
        headers=cabecalho,
    )
    assert criado.status_code == HTTPStatus.CREATED, criado.text
    definido = await client.post(
        f"{API}/auth/password",
        json={"token": token_de(criado.json()["setup_link"]), "password": SENHA_DO_FUNCIONARIO},
    )
    assert definido.status_code == HTTPStatus.NO_CONTENT, definido.text
    return await fazer_login(client, email, SENHA_DO_FUNCIONARIO)


@dataclass(frozen=True)
class Escala:
    """O cenário de escala: o de staff, mais funcionários com login, RH e a função."""

    base: Cenario
    funcao: str
    hr: dict
    ana_id: str
    ana: dict
    bruno_id: str
    bruno: dict
    caio_id: str
    caio: dict

    @property
    def unidade(self) -> str:
        return self.base.unidade_a


@pytest.fixture
async def escala(client: AsyncClient, cenario: Cenario) -> Escala:
    gerente = auth(cenario.manager)
    funcao = await criar_funcao(client, gerente, [cenario.unidade_a], "Cozinheiro")
    funcao_b = await criar_funcao(client, gerente, [cenario.unidade_b], "Cozinheiro B")

    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "rh@cantina.com",
            "password": SENHA_PADRAO,
            "role": "hr",
            "unit_ids": [cenario.unidade_a],
        },
        headers=auth(cenario.owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    hr = await fazer_login(client, "rh@cantina.com")

    ana_id = await criar_funcionario(client, gerente, cenario.unidade_a, "Ana", funcao)
    ana = await dar_login(client, gerente, cenario.unidade_a, ana_id, "ana@cantina.com")
    bruno_id = await criar_funcionario(client, gerente, cenario.unidade_a, "Bruno", funcao)
    bruno = await dar_login(client, gerente, cenario.unidade_a, bruno_id, "bruno@cantina.com")
    caio_id = await criar_funcionario(client, gerente, cenario.unidade_b, "Caio", funcao_b)
    caio = await dar_login(client, gerente, cenario.unidade_b, caio_id, "caio@cantina.com")
    return Escala(
        base=cenario,
        funcao=funcao,
        hr=hr,
        ana_id=ana_id,
        ana=ana,
        bruno_id=bruno_id,
        bruno=bruno,
        caio_id=caio_id,
        caio=caio,
    )


async def criar_escala(
    client: AsyncClient, cabecalho: dict[str, str], unidade: str, first_day: str = SEGUNDA
) -> str:
    resposta = await client.post(
        f"{API}/units/{unidade}/schedules", json={"first_day": first_day}, headers=cabecalho
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["schedule_id"])

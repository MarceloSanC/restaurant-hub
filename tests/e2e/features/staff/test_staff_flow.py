"""O DoD da Stage pelo entrypoint real — CA25, CA26, CA27, CA28, CA34 e CA04.

**Ator `manager`, e não `owner`, no fluxo feliz.** É exigência literal de CA25, e
a razão é que o `owner` faz bypass de escopo de unidade: um fluxo feliz com ele
passaria mesmo que a autorização por unidade estivesse quebrada, porque o passo 4
do guard o dispensa. O `manager` alcança só as unidades das quais é membro, então
é ele quem exercita o caminho que a Stage precisa provar.

**E é aqui que o ADR 0.0.0005 é medido de ponta a ponta.** Nenhuma destas
requisições nomeia o tenant: ele viaja claim do token → `LocalAccessGuard` (o
tradutor de staff, no composition root até a issue #47) → passo 3 de
`AuthorizeActionUseCase`, comparado com o tenant do usuário
**carregado do banco**. Antes da Task 01, todas as 16 rotas respondiam 403 para
todos os papéis.
"""

from decimal import Decimal
from http import HTTPStatus
from typing import Any

import pytest
from httpx import AsyncClient, Response

from tests.e2e.features.staff.conftest import API, Cenario, auth

pytestmark = pytest.mark.e2e


async def _listar(client: AsyncClient, cenario: Cenario, unidade: str, **params: str) -> Response:
    return await client.get(
        f"{API}/units/{unidade}/employees", headers=auth(cenario.manager), params=params
    )


async def _criar_funcao(client: AsyncClient, cenario: Cenario, nome: str) -> str:
    resposta = await client.post(
        f"{API}/job-functions", json={"name": nome}, headers=auth(cenario.manager)
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["id"])


async def _criar_funcionario(
    client: AsyncClient,
    cenario: Cenario,
    unidade: str,
    nome: str,
    job_function_id: str,
    **extras: object,
) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "name": nome,
        "workload_profile": {"type": "on_demand"},
        "job_function_ids": [job_function_id],
        **extras,
    }
    resposta = await client.post(
        f"{API}/units/{unidade}/employees", json=corpo, headers=auth(cenario.manager)
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return dict(resposta.json())


async def test_ca25_fluxo_feliz_completo_com_ator_manager(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA25 — autentica, cria função, cria funcionário, registra ausência, lista.

    Cada passo usa o token que a **aplicação** emitiu, contra o banco real. É o
    round-trip que nenhum teste unitário exercita: neles o issuer é o mesmo objeto
    dos dois lados, e o tenant nunca precisa sobreviver a uma serialização.
    """
    cabecalho = auth(cenario.manager)

    job_function_id = await _criar_funcao(client, cenario, "Garçom")

    funcionario = await _criar_funcionario(
        client,
        cenario,
        cenario.unidade_a,
        "Ana Souza",
        job_function_id,
        workload_profile={"type": "fixed", "weekly_hours": "22.50"},
        shift_preference=["night", "morning"],
    )
    employee_id = funcionario["id"]

    # CA04 no fio: a escala sobrevive ao round-trip pelo Postgres real, e a
    # preferência sai na ordem de declaração do enum — não na alfabética.
    assert funcionario["workload_profile"] == {"type": "fixed", "weekly_hours": "22.50"}
    assert Decimal(funcionario["workload_profile"]["weekly_hours"]) == Decimal("22.50")
    assert funcionario["shift_preference"] == ["morning", "night"]
    assert funcionario["unit_id"] == cenario.unidade_a
    assert funcionario["tenant_id"] == cenario.restaurante_id

    resposta = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/unavailabilities",
        json={"start": "2026-03-01T08:00:00", "end": "2026-03-01T12:00:00"},
        headers=cabecalho,
    )
    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert resposta.json()["unavailabilities"] == [
        {"start": "2026-03-01T08:00:00", "end": "2026-03-01T12:00:00"}
    ]

    listagem = await _listar(client, cenario, cenario.unidade_a)
    assert listagem.status_code == HTTPStatus.OK, listagem.text
    assert [item["id"] for item in listagem.json()] == [employee_id]


async def test_ca26_funcionario_de_a_nao_aparece_na_listagem_de_b(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA26 — isolamento entre unidades, para um ator que enxerga as **duas**.

    O `manager` é membro de A e de B, então a ausência não pode ser explicada por
    falta de visibilidade: se ele não vê o funcionário em B, é porque o registro
    é **por unidade** (ADR 3.4.0007), e não porque a porta estava fechada.
    """
    job_function_id = await _criar_funcao(client, cenario, "Cozinheiro")
    await _criar_funcionario(client, cenario, cenario.unidade_a, "Bruno", job_function_id)

    em_a = await _listar(client, cenario, cenario.unidade_a)
    em_b = await _listar(client, cenario, cenario.unidade_b)

    assert [item["name"] for item in em_a.json()] == ["Bruno"]
    assert em_b.json() == []


async def test_ca27_desligado_some_da_default_e_volta_com_include_inactive(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA27 — o desligamento esconde, não apaga; e a recontratação devolve.

    As três leituras são pela API real, e a última é a que fecha o ciclo: sem
    ela, um `deactivate` que apagasse o registro passaria nas duas primeiras.
    """
    cabecalho = auth(cenario.manager)
    job_function_id = await _criar_funcao(client, cenario, "Caixa")
    criado = await _criar_funcionario(client, cenario, cenario.unidade_a, "Carla", job_function_id)
    base = f"{API}/units/{cenario.unidade_a}/employees/{criado['id']}"

    desligado = await client.post(f"{base}/termination", headers=cabecalho)
    assert desligado.status_code == HTTPStatus.OK, desligado.text
    assert desligado.json()["active"] is False

    default = await _listar(client, cenario, cenario.unidade_a)
    com_inativos = await _listar(client, cenario, cenario.unidade_a, include_inactive="true")
    assert default.json() == []
    assert [item["id"] for item in com_inativos.json()] == [criado["id"]]

    recontratado = await client.post(f"{base}/rehire", headers=cabecalho)
    assert recontratado.status_code == HTTPStatus.OK, recontratado.text

    de_volta = await _listar(client, cenario, cenario.unidade_a)
    assert [item["id"] for item in de_volta.json()] == [criado["id"]]


async def test_ca28_a_ordem_da_listagem_e_a_de_l_ord_e_e_estavel(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA28 — ordem total por nome, e a mesma em leituras repetidas.

    Os nomes são escolhidos para que a ordem de **inserção** discorde da ordem
    esperada: inserir já ordenado faria o teste passar com qualquer `ORDER BY` —
    ou com nenhum.
    """
    job_function_id = await _criar_funcao(client, cenario, "Apoio")
    for nome in ("Zeca", "Ana", "Marta"):
        await _criar_funcionario(client, cenario, cenario.unidade_a, nome, job_function_id)

    primeira = await _listar(client, cenario, cenario.unidade_a)
    segunda = await _listar(client, cenario, cenario.unidade_a)

    assert [item["name"] for item in primeira.json()] == ["Ana", "Marta", "Zeca"]
    assert [item["id"] for item in primeira.json()] == [item["id"] for item in segunda.json()]


async def test_ca34_a_copia_cai_na_unidade_de_destino_e_o_original_fica(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA34, metade e2e — **onde** a cópia caiu, que é o que a inversão quebra.

    A inversão origem↔destino no router sobrevive a CA11, CA13, CA16 e CA25,
    porque nenhum deles exercita uma cópia bem-sucedida e olha o resultado. Aqui
    as três asserções juntas a matam: o clone está em B, o original continua em A,
    e os ids diferem.
    """
    job_function_id = await _criar_funcao(client, cenario, "Chefe")
    original = await _criar_funcionario(
        client,
        cenario,
        cenario.unidade_a,
        "Duda",
        job_function_id,
        workload_profile={"type": "fixed", "weekly_hours": "40.0"},
    )

    copia = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{original['id']}/copies",
        json={"target_unit_id": cenario.unidade_b},
        headers=auth(cenario.manager),
    )
    assert copia.status_code == HTTPStatus.CREATED, copia.text

    em_a = await _listar(client, cenario, cenario.unidade_a)
    em_b = await _listar(client, cenario, cenario.unidade_b)

    assert copia.json()["id"] != original["id"]
    assert copia.json()["unit_id"] == cenario.unidade_b
    assert [item["id"] for item in em_a.json()] == [original["id"]]
    assert [item["id"] for item in em_b.json()] == [copia.json()["id"]]
    # A cópia é integral: o perfil de jornada atravessou com valor e escala.
    assert copia.json()["workload_profile"] == {"type": "fixed", "weekly_hours": "40.0"}


async def test_ca36_o_manager_alcanca_as_rotas_sem_nomear_tenant(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA36, amostra e2e — o alcance que o ADR 0.0.0005 destravou.

    Antes da Task 01 estas duas chamadas respondiam **403** por
    `TenantScopeRequiredError`: o inventário não carrega tenant, então nada o
    nomeava, e o passo 3 recusava todo ator escopado. A trava completa sobre
    `{owner, manager, hr} x R01…R16` é da Task 11; aqui prova-se que o caminho
    está aberto no fluxo que o DoD exercita.
    """
    catalogo = await client.get(f"{API}/job-functions", headers=auth(cenario.manager))
    equipe = await _listar(client, cenario, cenario.unidade_a)

    assert catalogo.status_code == HTTPStatus.OK, catalogo.text
    assert equipe.status_code == HTTPStatus.OK, equipe.text

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
from tests.e2e.features.staff.test_staff_authorization import _CORPO_403, _criar_ator

pytestmark = pytest.mark.e2e


async def _listar(client: AsyncClient, cenario: Cenario, unidade: str, **params: str) -> Response:
    return await client.get(
        f"{API}/units/{unidade}/employees", headers=auth(cenario.manager), params=params
    )


async def _criar_funcao(client: AsyncClient, cenario: Cenario, nome: str) -> str:
    """Cria a função **nas duas unidades** do gerente (Stage 3.11).

    Sem `unit_ids` o pedido seria "todas as unidades", que exige `manage_tenant`
    (ADR 3.11.0001 §4) — o gerente nomeia as unidades de que é membro, e os fluxos
    que cadastram em A e copiam para B encontram a função habilitada nas duas.
    """
    resposta = await client.post(
        f"{API}/job-functions",
        json={"name": nome, "unit_ids": [cenario.unidade_a, cenario.unidade_b]},
        headers=auth(cenario.manager),
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


async def test_ca5_copia_para_unidade_sem_a_funcao_habilitada_e_409_e_nada_e_gravado(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA5 da Stage 3.11, pelo HTTP real — a regra da cópia do ADR 3.11.0002.

    A função vale **só em A**. Copiar para B é recusado com 409 de staff: a cópia
    não habilita a função no destino, não copia sem ela e não deixa registro em B.
    Habilitada a função em B, a mesma cópia passa — é o caminho que a recusa
    aponta.
    """
    funcao = await client.post(
        f"{API}/job-functions",
        json={"name": "Sushiman", "unit_ids": [cenario.unidade_a]},
        headers=auth(cenario.manager),
    )
    assert funcao.status_code == HTTPStatus.CREATED, funcao.text
    job_function_id = str(funcao.json()["id"])
    original = await _criar_funcionario(
        client, cenario, cenario.unidade_a, "Kenji", job_function_id
    )
    destino = {"target_unit_id": cenario.unidade_b}
    copias = f"{API}/units/{cenario.unidade_a}/employees/{original['id']}/copies"

    recusada = await client.post(copias, json=destino, headers=auth(cenario.manager))

    assert recusada.status_code == HTTPStatus.CONFLICT, recusada.text
    assert recusada.json()["type"] == "staff_error"
    assert "não está habilitada na unidade" in recusada.json()["detail"]
    em_b = await _listar(client, cenario, cenario.unidade_b)
    assert em_b.json() == []
    catalogo = await client.get(f"{API}/job-functions", headers=auth(cenario.manager))
    assert [f["unit_ids"] for f in catalogo.json() if f["id"] == job_function_id] == [
        [cenario.unidade_a]
    ]

    # O caminho que a recusa aponta: habilitar a função no destino e repetir.
    habilitada = await client.put(
        f"{API}/job-functions/{job_function_id}/units",
        json={"unit_ids": [cenario.unidade_a, cenario.unidade_b]},
        headers=auth(cenario.manager),
    )
    assert habilitada.status_code == HTTPStatus.OK, habilitada.text
    aceita = await client.post(copias, json=destino, headers=auth(cenario.manager))
    assert aceita.status_code == HTTPStatus.CREATED, aceita.text
    assert aceita.json()["unit_id"] == cenario.unidade_b
    assert aceita.json()["job_function_ids"] == [job_function_id]


async def _funcoes_da_unidade(
    client: AsyncClient, tokens: dict, unidade: str
) -> tuple[HTTPStatus, list[str]]:
    resposta = await client.get(f"{API}/units/{unidade}/job-functions", headers=auth(tokens))
    ids = [item["id"] for item in resposta.json()] if resposta.status_code == HTTPStatus.OK else []
    return HTTPStatus(resposta.status_code), ids


async def test_ca1_ca2_gerente_cria_para_a_sua_unidade_e_o_dono_para_todas(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA1 e CA2 da Stage 3.11 — os dois primeiros critérios da issue #41, pelo HTTP real.

    O gerente **só de A** cria uma função para a unidade dele: ela aparece na
    listagem de A e não na de B. Pedir a unidade B, que ele não enxerga, ou "todas
    as unidades" (sem `unit_ids`) é 403 com o corpo constante de identity. O dono
    cria sem nomear unidade, e a função vale nas duas.
    """
    gerente_de_a = await _criar_ator(
        client, cenario, "gerente-so-de-a@cantina.com", "manager", (cenario.unidade_a,)
    )
    funcoes = f"{API}/job-functions"

    da_unidade = await client.post(
        funcoes,
        json={"name": "Pizzaiolo", "unit_ids": [cenario.unidade_a]},
        headers=auth(gerente_de_a),
    )
    assert da_unidade.status_code == HTTPStatus.CREATED, da_unidade.text
    assert da_unidade.json()["all_units"] is False
    assert da_unidade.json()["unit_ids"] == [cenario.unidade_a]

    de_outra = await client.post(
        funcoes,
        json={"name": "Barista", "unit_ids": [cenario.unidade_a, cenario.unidade_b]},
        headers=auth(gerente_de_a),
    )
    para_todas = await client.post(funcoes, json={"name": "Barista"}, headers=auth(gerente_de_a))
    for negada in (de_outra, para_todas):
        assert negada.status_code == HTTPStatus.FORBIDDEN, negada.text
        assert negada.json() == _CORPO_403

    do_dono = await client.post(
        funcoes, json={"name": "Gerente de salão"}, headers=auth(cenario.owner)
    )
    assert do_dono.status_code == HTTPStatus.CREATED, do_dono.text
    assert do_dono.json()["all_units"] is True
    assert do_dono.json()["unit_ids"] == []

    # Listagem por unidade: A vê as duas; B só a do dono (CA1, CA3). O gerente de
    # A não lista B — a unidade é alvo de autorização.
    status_a, em_a = await _funcoes_da_unidade(client, gerente_de_a, cenario.unidade_a)
    status_b, em_b = await _funcoes_da_unidade(client, cenario.owner, cenario.unidade_b)
    status_negado, _ = await _funcoes_da_unidade(client, gerente_de_a, cenario.unidade_b)

    assert (status_a, status_b, status_negado) == (
        HTTPStatus.OK,
        HTTPStatus.OK,
        HTTPStatus.FORBIDDEN,
    )
    assert set(em_a) == {da_unidade.json()["id"], do_dono.json()["id"]}
    assert em_b == [do_dono.json()["id"]]
    # Nenhuma das recusas gravou a função pedida.
    catalogo = await client.get(funcoes, headers=auth(cenario.owner))
    assert sorted(f["name"] for f in catalogo.json()) == ["Gerente de salão", "Pizzaiolo"]


async def test_ca7_o_gerente_habilita_na_sua_unidade_e_so_mexe_no_que_enxerga(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA7 da Stage 3.11 — alterar onde a função vale exige alcance sobre o que muda.

    A função nasce só em B (criada pelo dono). O gerente só de A a habilita em A —
    só A é autorizada — e passa a listá-la; tirar B, ou pedir "todas", é 403 e nada
    muda. O dono alarga para todas. A persistência é a real: flag e vínculos.
    """
    gerente_de_a = await _criar_ator(
        client, cenario, "gerente-so-de-a@cantina.com", "manager", (cenario.unidade_a,)
    )
    criada = await client.post(
        f"{API}/job-functions",
        json={"name": "Sommelier", "unit_ids": [cenario.unidade_b]},
        headers=auth(cenario.owner),
    )
    assert criada.status_code == HTTPStatus.CREATED, criada.text
    funcao_id = str(criada.json()["id"])
    unidades = f"{API}/job-functions/{funcao_id}/units"
    as_duas = sorted([cenario.unidade_a, cenario.unidade_b])

    _, antes = await _funcoes_da_unidade(client, gerente_de_a, cenario.unidade_a)
    habilitada = await client.put(unidades, json={"unit_ids": as_duas}, headers=auth(gerente_de_a))
    _, depois = await _funcoes_da_unidade(client, gerente_de_a, cenario.unidade_a)

    assert antes == []
    assert habilitada.status_code == HTTPStatus.OK, habilitada.text
    assert habilitada.json()["unit_ids"] == as_duas
    assert depois == [funcao_id]

    tirando_b = await client.put(
        unidades, json={"unit_ids": [cenario.unidade_a]}, headers=auth(gerente_de_a)
    )
    para_todas = await client.put(unidades, json={"unit_ids": None}, headers=auth(gerente_de_a))
    for negada in (tirando_b, para_todas):
        assert negada.status_code == HTTPStatus.FORBIDDEN, negada.text
        assert negada.json() == _CORPO_403
    _, em_b = await _funcoes_da_unidade(client, cenario.owner, cenario.unidade_b)
    assert em_b == [funcao_id]

    do_dono = await client.put(unidades, json={"unit_ids": None}, headers=auth(cenario.owner))
    assert do_dono.status_code == HTTPStatus.OK, do_dono.text
    assert do_dono.json()["all_units"] is True
    assert do_dono.json()["unit_ids"] == []

    # Com a unidade B no corpo — que o gerente de A não enxerga —, para que o 404
    # prove a ordem: a existência é respondida **antes** de qualquer autorização de
    # unidade (R8). Com a ordem trocada, a resposta seria o 403 de B.
    inexistente = await client.put(
        f"{API}/job-functions/funcao-que-nunca-existiu/units",
        json={"unit_ids": [cenario.unidade_b]},
        headers=auth(gerente_de_a),
    )
    assert inexistente.status_code == HTTPStatus.NOT_FOUND, inexistente.text
    assert inexistente.json()["type"] == "staff_error"


async def test_ca7_estreitar_com_funcionario_na_unidade_removida_e_409(
    client: AsyncClient, cenario: Cenario
) -> None:
    """ADR 3.11.0002 — a função não sai de uma unidade em que algum registro a detém."""
    job_function_id = await _criar_funcao(client, cenario, "Maître")
    await _criar_funcionario(client, cenario, cenario.unidade_b, "Bruno", job_function_id)

    recusada = await client.put(
        f"{API}/job-functions/{job_function_id}/units",
        json={"unit_ids": [cenario.unidade_a]},
        headers=auth(cenario.manager),
    )

    assert recusada.status_code == HTTPStatus.CONFLICT, recusada.text
    assert recusada.json()["type"] == "staff_error"
    assert "função de trabalho em uso por algum funcionário" in recusada.json()["detail"]
    _, em_b = await _funcoes_da_unidade(client, cenario.manager, cenario.unidade_b)
    assert em_b == [job_function_id]

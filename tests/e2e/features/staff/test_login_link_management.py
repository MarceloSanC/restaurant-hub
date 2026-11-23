"""E2E da gestão do vínculo de login — Stage 3.10 (CA1, CA2, CA4, CA5, CA12, CA14).

O fluxo pelo entrypoint real, contra Postgres: o `manager` vincula a um registro a
conta que já existe no restaurante (R18), troca o login por outra conta (R19),
desvincula (R20) e remove o registro (R15). O efeito sobre as sessões é observado
por `POST /auth/refresh`, sempre com o refresh **rotacionado** (reapresentar o
original dispara a detecção de reuso e daria um 401 que não prova nada).

As recusas do DoD por rota — unidade fora do alcance (403) e registro de outra
unidade no endereço (404) — são cobradas para **toda** rota de staff, inclusive as
três desta Stage, pela matriz de `test_staff_authorization.py` (CA13). Aqui ficam
as recusas da **conta**: de outro restaurante e `platform_admin`, em R18 e R19, com
o mesmo 404 e o mesmo corpo de uma conta inexistente.
"""

from http import HTTPStatus

import pytest
from httpx import AsyncClient

from tests.e2e.features.staff.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    Cenario,
    auth,
    fazer_login,
)

pytestmark = pytest.mark.e2e


async def _criar_funcionario(
    client: AsyncClient, cabecalho: dict[str, str], unidade: str, nome: str
) -> str:
    funcao = await client.post(
        f"{API}/job-functions",
        json={"name": f"Função de {nome}", "unit_ids": [unidade]},
        headers=cabecalho,
    )
    assert funcao.status_code == HTTPStatus.CREATED, funcao.text
    criado = await client.post(
        f"{API}/units/{unidade}/employees",
        json={
            "name": nome,
            "workload_profile": {"type": "on_demand"},
            "job_function_ids": [funcao.json()["id"]],
        },
        headers=cabecalho,
    )
    assert criado.status_code == HTTPStatus.CREATED, criado.text
    return str(criado.json()["id"])


async def _criar_conta(
    client: AsyncClient, cenario: Cenario, email: str, papel: str, unidades: list[str]
) -> str:
    """Cria uma conta com senha pelo `owner` — a conta "que já existe"."""
    resposta = await client.post(
        f"{API}/users",
        json={"email": email, "password": SENHA_PADRAO, "role": papel, "unit_ids": unidades},
        headers=auth(cenario.owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return str(resposta.json()["id"])


def _url(unidade: str, employee_id: str) -> str:
    return f"{API}/units/{unidade}/employees/{employee_id}/login-link"


async def _refresh(client: AsyncClient, tokens: dict) -> tuple[int, dict]:
    """Apresenta o refresh atual; no 200 devolve o par rotacionado para a próxima vez."""
    resposta = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    return resposta.status_code, (
        resposta.json() if resposta.status_code == HTTPStatus.OK else tokens
    )


async def test_ca14_percurso_vincular_trocar_desvincular_e_remover(
    client: AsyncClient, cenario: Cenario
) -> None:
    """CA1, CA4, CA5 pelo fio: cada transição, o efeito no registro e nas sessões."""
    gerente = auth(cenario.manager)
    unidade = cenario.unidade_a
    registro = await _criar_funcionario(client, gerente, unidade, "Carla")
    conta_errada = await _criar_conta(client, cenario, "errada@cantina.com", "employee", [unidade])
    conta_certa = await _criar_conta(client, cenario, "certa@cantina.com", "employee", [unidade])
    sessao_errada = await fazer_login(client, "errada@cantina.com")
    sessao_certa = await fazer_login(client, "certa@cantina.com")

    # R18 — vincula a conta existente (o e-mail com espaço e maiúscula a encontra).
    vinculado = await client.post(
        _url(unidade, registro), json={"email": " Errada@Cantina.com"}, headers=gerente
    )
    assert vinculado.status_code == HTTPStatus.OK, vinculado.text
    assert vinculado.json()["user_id"] == conta_errada
    status, sessao_errada = await _refresh(client, sessao_errada)
    assert status == HTTPStatus.OK  # vincular não toca as sessões

    # R19 — troca: a conta antiga, de funcionário e única da unidade, perde as sessões.
    trocado = await client.put(
        _url(unidade, registro), json={"email": "certa@cantina.com"}, headers=gerente
    )
    assert trocado.status_code == HTTPStatus.OK, trocado.text
    assert trocado.json()["user_id"] == conta_certa
    status, _ = await _refresh(client, sessao_errada)
    assert status == HTTPStatus.UNAUTHORIZED, "a troca não revogou o login antigo"
    status, sessao_certa = await _refresh(client, sessao_certa)
    assert status == HTTPStatus.OK, "a troca revogou o login novo"

    # R19 pelo login atual: nada muda, nada é revogado.
    mesmo = await client.put(
        _url(unidade, registro), json={"email": "certa@cantina.com"}, headers=gerente
    )
    assert mesmo.status_code == HTTPStatus.OK, mesmo.text
    status, sessao_certa = await _refresh(client, sessao_certa)
    assert status == HTTPStatus.OK

    # R20 — desvincula: a conta perde as sessões; o registro fica sem login.
    desvinculado = await client.delete(_url(unidade, registro), headers=gerente)
    assert desvinculado.status_code == HTTPStatus.OK, desvinculado.text
    assert desvinculado.json()["user_id"] is None
    status, _ = await _refresh(client, sessao_certa)
    assert status == HTTPStatus.UNAUTHORIZED, "desvincular não revogou o login"
    # A conta continua existindo e logando (desativar conta é non-goal).
    await fazer_login(client, "certa@cantina.com")

    # R15 — sem vínculo, o registro se remove.
    removido = await client.delete(f"{API}/units/{unidade}/employees/{registro}", headers=gerente)
    assert removido.status_code == HTTPStatus.NO_CONTENT, removido.text


async def test_ca1_o_dono_sem_membership_vincula_a_propria_conta(
    client: AsyncClient, cenario: Cenario
) -> None:
    """O caso imediato do roadmap: o dono nasce sem membership e alcança toda unidade."""
    dono = auth(cenario.owner)
    registro = await _criar_funcionario(client, dono, cenario.unidade_b, "Zé")

    resposta = await client.post(
        _url(cenario.unidade_b, registro), json={"email": "dono@cantina.com"}, headers=dono
    )

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert resposta.json()["user_id"] is not None


async def test_ca1_ca4_o_gerente_vincula_a_propria_conta_e_desvincular_nao_o_derruba(
    client: AsyncClient, cenario: Cenario
) -> None:
    """Autovínculo de um gerente; R20 não revoga login que não é de funcionário."""
    gerente = auth(cenario.manager)
    registro = await _criar_funcionario(client, gerente, cenario.unidade_a, "Gerente na escala")

    vinculado = await client.post(
        _url(cenario.unidade_a, registro), json={"email": "gerente@cantina.com"}, headers=gerente
    )
    assert vinculado.status_code == HTTPStatus.OK, vinculado.text

    desvinculado = await client.delete(_url(cenario.unidade_a, registro), headers=gerente)
    assert desvinculado.status_code == HTTPStatus.OK, desvinculado.text
    status, _ = await _refresh(client, cenario.manager)
    assert status == HTTPStatus.OK, "desvincular derrubou a sessão de um gerente"


async def _conta_de_outro_restaurante(client: AsyncClient) -> str:
    admin = await fazer_login(client, ADMIN_EMAIL)
    resposta = await client.post(
        f"{API}/restaurants",
        json={"name": "Outra Cantina", "owner": {"email": "dono@outra-cantina.com"}},
        headers=auth(admin),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return "dono@outra-cantina.com"


@pytest.mark.parametrize("metodo", ["POST", "PUT"])
async def test_ca2_conta_de_outro_tenant_e_platform_admin_recebem_o_mesmo_404(
    client: AsyncClient, cenario: Cenario, metodo: str
) -> None:
    """DoD: as duas recusas da conta, em R18 e em R19, indistinguíveis de "não existe"."""
    gerente = auth(cenario.manager)
    unidade = cenario.unidade_a
    registro = await _criar_funcionario(client, gerente, unidade, f"Registro {metodo}")
    atual = None
    sessao_atual: dict = {}
    if metodo == "PUT":
        atual = await _criar_conta(client, cenario, "atual@cantina.com", "employee", [unidade])
        sessao_atual = await fazer_login(client, "atual@cantina.com")
        vinculado = await client.post(
            _url(unidade, registro), json={"email": "atual@cantina.com"}, headers=gerente
        )
        assert vinculado.status_code == HTTPStatus.OK, vinculado.text
    alheia = await _conta_de_outro_restaurante(client)

    respostas = {}
    for email in (alheia, ADMIN_EMAIL, "ninguem@cantina.com"):
        respostas[email] = await client.request(
            metodo, _url(unidade, registro), json={"email": email}, headers=gerente
        )

    assert {r.status_code for r in respostas.values()} == {HTTPStatus.NOT_FOUND}, {
        e: r.text for e, r in respostas.items()
    }
    corpos = {r.json()["detail"].replace(email, "<e-mail>") for email, r in respostas.items()}
    assert len(corpos) == 1, corpos
    assert {r.json()["type"] for r in respostas.values()} == {"staff_error"}
    relido = await client.get(f"{API}/units/{unidade}/employees", headers=gerente)
    (item,) = [i for i in relido.json() if i["id"] == registro]
    assert item["user_id"] == atual, "a recusa mudou o vínculo"
    if metodo == "PUT":
        status, _ = await _refresh(client, sessao_atual)
        assert status == HTTPStatus.OK, "a recusa revogou a sessão do login atual"


async def test_ca12_a_conta_ja_vinculada_a_outro_registro_da_unidade_e_409(
    client: AsyncClient, cenario: Cenario
) -> None:
    gerente = auth(cenario.manager)
    unidade = cenario.unidade_a
    primeiro = await _criar_funcionario(client, gerente, unidade, "Primeiro")
    segundo = await _criar_funcionario(client, gerente, unidade, "Segundo")
    await _criar_conta(client, cenario, "unica@cantina.com", "employee", [unidade])
    vinculado = await client.post(
        _url(unidade, primeiro), json={"email": "unica@cantina.com"}, headers=gerente
    )
    assert vinculado.status_code == HTTPStatus.OK, vinculado.text

    resposta = await client.post(
        _url(unidade, segundo), json={"email": "unica@cantina.com"}, headers=gerente
    )

    assert resposta.status_code == HTTPStatus.CONFLICT, resposta.text
    assert "outro registro da unidade" in resposta.json()["detail"]


async def test_ca5_desvincular_registro_desligado_nao_revoga_e_libera_a_remocao(
    client: AsyncClient, cenario: Cenario
) -> None:
    """R8: o vínculo de um desligado é história; desvinculá-lo não toca identity."""
    gerente = auth(cenario.manager)
    unidade = cenario.unidade_a
    registro = await _criar_funcionario(client, gerente, unidade, "Desligada")
    await _criar_conta(client, cenario, "desligada@cantina.com", "employee", [unidade])
    vinculado = await client.post(
        _url(unidade, registro), json={"email": "desligada@cantina.com"}, headers=gerente
    )
    assert vinculado.status_code == HTTPStatus.OK, vinculado.text
    desligado = await client.post(
        f"{API}/units/{unidade}/employees/{registro}/termination", headers=gerente
    )
    assert desligado.status_code == HTTPStatus.OK, desligado.text
    # A pessoa loga de novo depois do desligamento (a conta continua existindo).
    sessao = await fazer_login(client, "desligada@cantina.com")

    desvinculado = await client.delete(_url(unidade, registro), headers=gerente)

    assert desvinculado.status_code == HTTPStatus.OK, desvinculado.text
    assert (desvinculado.json()["user_id"], desvinculado.json()["active"]) == (None, False)
    status, _ = await _refresh(client, sessao)
    assert status == HTTPStatus.OK, "desvincular um desligado revogou as sessões"
    removido = await client.delete(f"{API}/units/{unidade}/employees/{registro}", headers=gerente)
    assert removido.status_code == HTTPStatus.NO_CONTENT, removido.text

"""CA18 — a cadeia completa de provisionamento, pelo entrypoint real.

Este é o teste que o DoD da issue #24 pede: "admin cria tenant → unidade →
usuário", com os **atores corretos** conforme a decisão do sponsor de 2026-07-19.
O `platform_admin` provisiona o restaurante e o seu primeiro `owner`; o `owner`
opera dali em diante.
"""

from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import Engine, text

from restaurant_hub.features.identity.domain.entities.user import User
from tests.e2e.features.identity.conftest import API, SENHA_PADRAO, auth, fazer_login

pytestmark = pytest.mark.e2e


async def test_cadeia_completa_de_provisionamento(client: AsyncClient, admin_semeado: User) -> None:
    """CA18 — a cadeia inteira, do login do admin ao 403 do funcionário.

    Cada passo usa o token emitido pelo passo anterior, então o teste também
    prova que o JWT emitido pela API é aceito pelo guard da API — o round-trip
    que nenhum teste unitário exercita, porque em todos eles o issuer é o mesmo
    objeto dos dois lados.
    """
    # 1. platform_admin faz login
    admin = await fazer_login(client, admin_semeado.email.value)

    # 2. platform_admin cria o restaurante (o tenant)
    resposta = await client.post(
        f"{API}/restaurants", json={"name": "Cantina do Zé"}, headers=auth(admin)
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    restaurante_id = resposta.json()["id"]

    # 3. platform_admin provisiona o primeiro owner — sem isto a cadeia trava,
    #    porque ele não tem manage_users e o owner ainda não existe.
    resposta = await client.post(
        f"{API}/restaurants/{restaurante_id}/owners",
        json={"email": "dono@cantina.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    assert resposta.json()["role"] == "owner"
    # O tenant do owner veio do PATH, não do ator (que não tem tenant nenhum).
    assert resposta.json()["tenant_id"] == restaurante_id

    # 4. o owner faz login
    owner = await fazer_login(client, "dono@cantina.com")

    # 5. o owner cria uma unidade
    resposta = await client.post(
        f"{API}/restaurants/{restaurante_id}/units",
        json={"name": "Filial Centro"},
        headers=auth(owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    unidade_id = resposta.json()["id"]

    # 6. o owner cria um funcionário vinculado à unidade
    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "func@cantina.com",
            "password": SENHA_PADRAO,
            "role": "employee",
            "unit_ids": [unidade_id],
        },
        headers=auth(owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    assert resposta.json()["tenant_id"] == restaurante_id
    assert resposta.json()["unit_ids"] == [unidade_id]

    # 7. o funcionário faz login e é barrado ao tentar criar unidade
    funcionario = await fazer_login(client, "func@cantina.com")
    resposta = await client.post(
        f"{API}/restaurants/{restaurante_id}/units",
        json={"name": "Filial Pirata"},
        headers=auth(funcionario),
    )
    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_restaurante_inexistente_devolve_404_e_nao_grava_usuario(
    client: AsyncClient, admin_semeado: User, engine: Engine
) -> None:
    """CA24, metade destrutiva — contada no banco real, não no fake.

    Um 404 acompanhado de escrita parcial seria o pior dos mundos: o cliente
    acredita que nada aconteceu e existe uma conta órfã. Contar as linhas antes e
    depois é a única forma de provar que não.
    """
    admin = await fazer_login(client, admin_semeado.email.value)
    with engine.connect() as conexao:
        antes = conexao.execute(text("SELECT count(*) FROM users")).scalar_one()

    resposta = await client.post(
        f"{API}/restaurants/restaurante-que-nao-existe/owners",
        json={"email": "fantasma@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    with engine.connect() as conexao:
        depois = conexao.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert depois == antes


async def test_owner_nao_cria_restaurante(client: AsyncClient, admin_semeado: User) -> None:
    """CA11 — só `platform_admin` cria tenant, agora contra o banco real."""
    admin = await fazer_login(client, admin_semeado.email.value)
    restaurante_id = (
        await client.post(f"{API}/restaurants", json={"name": "Cantina"}, headers=auth(admin))
    ).json()["id"]
    await client.post(
        f"{API}/restaurants/{restaurante_id}/owners",
        json={"email": "dono@cantina.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )
    owner = await fazer_login(client, "dono@cantina.com")

    resposta = await client.post(
        f"{API}/restaurants", json={"name": "Império"}, headers=auth(owner)
    )

    assert resposta.status_code == HTTPStatus.FORBIDDEN


async def test_email_duplicado_entre_tenants_e_409(
    client: AsyncClient, admin_semeado: User
) -> None:
    """A unicidade global de e-mail, imposta pelo índice único do Postgres.

    Atravessa tenants de propósito (decisão de kickoff #2). Aqui o adapter real é
    indispensável: no fake a checagem prévia do use case resolveria o caso, e a
    garantia dura — a que vale sob concorrência — é o índice do banco.
    """
    admin = await fazer_login(client, admin_semeado.email.value)
    primeiro = (
        await client.post(f"{API}/restaurants", json={"name": "A"}, headers=auth(admin))
    ).json()["id"]
    segundo = (
        await client.post(f"{API}/restaurants", json={"name": "B"}, headers=auth(admin))
    ).json()["id"]

    await client.post(
        f"{API}/restaurants/{primeiro}/owners",
        json={"email": "repetido@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )
    resposta = await client.post(
        f"{API}/restaurants/{segundo}/owners",
        json={"email": "repetido@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.CONFLICT

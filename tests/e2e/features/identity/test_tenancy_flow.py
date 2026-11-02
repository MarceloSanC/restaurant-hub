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
from tests.e2e.features.identity.conftest import (
    API,
    SENHA_PADRAO,
    auth,
    corpo_tenant,
    fazer_login,
)

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

    # 2-3. platform_admin provisiona o restaurante (o tenant) **com** o primeiro
    #      owner, numa chamada (issue #67) — sem o dono a cadeia trava, porque o
    #      admin não tem manage_users.
    resposta = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Cantina do Zé", "dono@cantina.com"),
        headers=auth(admin),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    restaurante_id = resposta.json()["id"]
    assert resposta.json()["owner"]["role"] == "owner"
    # O tenant do owner é o restaurante que nasceu junto com ele.
    assert resposta.json()["owner"]["tenant_id"] == restaurante_id

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
    await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Cantina", "dono@cantina.com"),
        headers=auth(admin),
    )
    owner = await fazer_login(client, "dono@cantina.com")

    resposta = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Império", "dono@imperio.com"),
        headers=auth(owner),
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
    await client.post(
        f"{API}/restaurants", json=corpo_tenant("A", "repetido@x.com"), headers=auth(admin)
    )
    segundo = (
        await client.post(
            f"{API}/restaurants", json=corpo_tenant("B", "dono-b@x.com"), headers=auth(admin)
        )
    ).json()["id"]

    resposta = await client.post(
        f"{API}/restaurants/{segundo}/owners",
        json={"email": "repetido@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.CONFLICT


# ---------------------------------------------------------------------------
# Issue #67 — o restaurante nasce com o dono, ou não nasce (ADR 0.0.0014)
# ---------------------------------------------------------------------------


def _contagens(engine: Engine) -> tuple[int, int]:
    with engine.connect() as conexao:
        return (
            conexao.execute(text("SELECT count(*) FROM restaurants")).scalar_one(),
            conexao.execute(text("SELECT count(*) FROM users")).scalar_one(),
        )


async def test_email_do_dono_ocupado_nao_deixa_restaurante_orfao(
    client: AsyncClient, admin_semeado: User, engine: Engine
) -> None:
    """O defeito que a issue #67 fecha, pela API e contra o banco real.

    Antes, o restaurante era criado numa chamada e o dono noutra; um 409 na
    segunda deixava um restaurante que ninguém opera. Agora o 409 vem da mesma
    requisição e **nenhuma** linha nova fica — nem restaurante, nem usuário.
    """
    admin = await fazer_login(client, admin_semeado.email.value)
    antes = _contagens(engine)

    resposta = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Órfão", admin_semeado.email.value),
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.CONFLICT
    assert _contagens(engine) == antes


async def test_dono_provisionado_opera_o_proprio_restaurante_e_so_ele(
    client: AsyncClient, admin_semeado: User
) -> None:
    """O dono que nasce com o restaurante tem o tenant certo: cria unidade no dele
    e é barrado no de outro."""
    admin = await fazer_login(client, admin_semeado.email.value)
    meu = (
        await client.post(
            f"{API}/restaurants", json=corpo_tenant("Meu", "dono@meu.com"), headers=auth(admin)
        )
    ).json()["id"]
    alheio = (
        await client.post(
            f"{API}/restaurants",
            json=corpo_tenant("Alheio", "dono@alheio.com"),
            headers=auth(admin),
        )
    ).json()["id"]
    dono = await fazer_login(client, "dono@meu.com")

    no_meu = await client.post(
        f"{API}/restaurants/{meu}/units", json={"name": "Centro"}, headers=auth(dono)
    )
    no_alheio = await client.post(
        f"{API}/restaurants/{alheio}/units", json={"name": "Centro"}, headers=auth(dono)
    )

    assert no_meu.status_code == HTTPStatus.CREATED
    assert no_alheio.status_code == HTTPStatus.FORBIDDEN


async def test_rota_de_owner_acrescenta_dono_a_restaurante_existente(
    client: AsyncClient, admin_semeado: User
) -> None:
    """`POST /restaurants/{id}/owners` deixou de ser o bootstrap e segue como o
    caminho de suporte da plataforma (ADR 0.0.0014 §3)."""
    admin = await fazer_login(client, admin_semeado.email.value)
    restaurante = (
        await client.post(
            f"{API}/restaurants",
            json=corpo_tenant("Cantina", "primeiro@x.com"),
            headers=auth(admin),
        )
    ).json()["id"]

    resposta = await client.post(
        f"{API}/restaurants/{restaurante}/owners",
        json={"email": "segundo@x.com", "password": SENHA_PADRAO},
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert (resposta.json()["role"], resposta.json()["tenant_id"]) == ("owner", restaurante)
    await fazer_login(client, "segundo@x.com")

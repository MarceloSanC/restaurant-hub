"""CA18 — a cadeia completa de provisionamento, pelo entrypoint real.

Este é o teste que o DoD da issue #24 pede: "admin cria tenant → unidade →
usuário", com os **atores corretos** conforme a decisão do sponsor de 2026-07-19.
O `platform_admin` provisiona o restaurante e o seu primeiro `owner`; o `owner`
opera dali em diante.
"""

import logging
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
    login_do_dono,
)
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e


async def test_cadeia_completa_de_provisionamento(
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
) -> None:
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

    # 4. o owner define a senha pelo convite (ADR 0.0.0018) e faz login
    owner = await login_do_dono(client, caixa_de_entrada, "dono@cantina.com")

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
        json={"email": "fantasma@x.com"},
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    with engine.connect() as conexao:
        depois = conexao.execute(text("SELECT count(*) FROM users")).scalar_one()
    assert depois == antes


async def test_owner_nao_cria_restaurante(
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
) -> None:
    """CA11 — só `platform_admin` cria tenant, agora contra o banco real."""
    admin = await fazer_login(client, admin_semeado.email.value)
    await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Cantina", "dono@cantina.com"),
        headers=auth(admin),
    )
    owner = await login_do_dono(client, caixa_de_entrada, "dono@cantina.com")

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
        json={"email": "repetido@x.com"},
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
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
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
    dono = await login_do_dono(client, caixa_de_entrada, "dono@meu.com")

    no_meu = await client.post(
        f"{API}/restaurants/{meu}/units", json={"name": "Centro"}, headers=auth(dono)
    )
    no_alheio = await client.post(
        f"{API}/restaurants/{alheio}/units", json={"name": "Centro"}, headers=auth(dono)
    )

    assert no_meu.status_code == HTTPStatus.CREATED
    assert no_alheio.status_code == HTTPStatus.FORBIDDEN


# ---------------------------------------------------------------------------
# Issue #114 — a senha do dono não transita pela API de plataforma (ADR 0.0.0018)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rota", ["provisionamento", "rota-de-owner"])
async def test_senha_enviada_pela_plataforma_nao_abre_a_conta_do_dono(  # noqa: PLR0913 — as fixtures do cenário, o log e o eixo da rota
    client: AsyncClient,
    admin_semeado: User,
    caixa_de_entrada: RecordingEmailSender,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
    rota: str,
) -> None:
    """O critério de aceite da #114, pelo entrypoint real e contra o banco real.

    O admin manda uma senha no corpo, como um cliente antigo faria. Ela é
    descartada: o login com ela é 401, nada dela chega ao banco, ao e-mail nem ao
    log da requisição, e a conta só abre depois que o próprio dono define a senha
    pelo link do convite.
    """
    admin = await fazer_login(client, admin_semeado.email.value)
    senha_da_plataforma = "senha-escolhida-pela-plataforma"
    email = "dono-convidado@x.com"
    # DEBUG no root e no `sqlalchemy.engine` — que o boot fixa em WARNING
    # (`configure_logging`) e que, aberto, registra os parâmetros de cada
    # statement: uma senha que chegasse ao banco apareceria no log.
    caplog.clear()
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="sqlalchemy.engine")
    if rota == "provisionamento":
        corpo = corpo_tenant("Cantina", email)
        corpo["owner"]["password"] = senha_da_plataforma
        resposta = await client.post(f"{API}/restaurants", json=corpo, headers=auth(admin))
    else:
        restaurante = (
            await client.post(
                f"{API}/restaurants",
                json=corpo_tenant("Cantina", "primeiro@x.com"),
                headers=auth(admin),
            )
        ).json()["id"]
        resposta = await client.post(
            f"{API}/restaurants/{restaurante}/owners",
            json={"email": email, "password": senha_da_plataforma},
            headers=auth(admin),
        )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    # Antes do login abaixo, que manda a senha de propósito pela rota pública. O
    # e-mail no log prova que a captura vê os parâmetros do INSERT — sem ele, a
    # ausência da senha seria verdade vazia.
    assert email in caplog.text
    assert senha_da_plataforma not in caplog.text

    com_a_senha_da_plataforma = await client.post(
        f"{API}/auth/login", json={"email": email, "password": senha_da_plataforma}
    )
    assert com_a_senha_da_plataforma.status_code == HTTPStatus.UNAUTHORIZED
    convite = next(m for m in caixa_de_entrada.sent if m.to == email)
    assert senha_da_plataforma not in convite.body_text
    assert "token" not in resposta.text
    with engine.connect() as conexao:
        hash_gravado = conexao.execute(
            text("SELECT password_hash FROM users WHERE email = :e"), {"e": email}
        ).scalar_one()
    assert senha_da_plataforma not in hash_gravado

    dono = await login_do_dono(client, caixa_de_entrada, email, "senha-escolhida-pelo-dono")
    assert dono["access_token"]


async def test_rota_de_owner_acrescenta_dono_a_restaurante_existente(
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
) -> None:
    """`POST /restaurants/{id}/owners` deixou de ser o bootstrap e segue como o
    caminho de suporte da plataforma (ADR 0.0.0014 §3) — e convida o dono, que
    define a própria senha pelo link (ADR 0.0.0018)."""
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
        json={"email": "segundo@x.com"},
        headers=auth(admin),
    )

    assert resposta.status_code == HTTPStatus.CREATED
    assert (resposta.json()["role"], resposta.json()["tenant_id"]) == ("owner", restaurante)
    await login_do_dono(client, caixa_de_entrada, "segundo@x.com")

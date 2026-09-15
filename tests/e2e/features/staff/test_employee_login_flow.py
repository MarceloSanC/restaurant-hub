"""E2E do login do funcionário — Stage 3.5 (CA13, CA14, CA22 a CA26, CA30 a CA32).

O fluxo inteiro pelo entrypoint real, contra Postgres: o `manager` cria o
funcionário e o login; o link sai pelo canal escolhido; o funcionário define a
senha e autentica; o desligamento corta a sessão; a remoção recusa o vinculado;
a cópia não carrega o vínculo; e o **valor do token** só aparece onde deve —
no e-mail capturado ou no corpo de R17 no canal `link`, nunca em tabela de
staff nem em log.

O `RecordingEmailSender` entra pela costura de `create_app(..., email_sender=)`,
como no e2e de convite de identity: é o composition root de produção montando o
grafo real, com **um** port trocado.
"""

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, text

from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    _SENTINELA_DUMMY,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import create_app
from tests.conftest import truncar_tudo
from tests.e2e.features.staff.conftest import API, Cenario, auth
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

pytestmark = pytest.mark.e2e

_SENHA_DO_FUNCIONARIO = "senha-escolhida-pela-pessoa"
_TABELAS_DE_STAFF = (
    "job_functions",
    "employees",
    "employee_job_functions",
    "employee_unavailabilities",
    "employee_shift_preferences",
)


# ---------------------------------------------------------------------------
# A app com a caixa de entrada capturada — sobrescreve `app_e2e` do conftest
# ---------------------------------------------------------------------------


@pytest.fixture
def caixa_de_entrada(request: pytest.FixtureRequest) -> RecordingEmailSender:
    """A caixa capturada — ou, por parametrização indireta, uma que falha (CA30)."""
    parametro = getattr(request, "param", None)
    return parametro if parametro is not None else RecordingEmailSender()


@pytest.fixture
def app_e2e(
    engine: Engine, settings_e2e: Settings, caixa_de_entrada: RecordingEmailSender
) -> object:
    """A mesma app do conftest, com o `EmailSender` trocado pela costura do root."""
    truncar_tudo(engine)
    return create_app(settings_e2e, email_sender=caixa_de_entrada)


@pytest.fixture
async def client_500(app_e2e: object) -> AsyncIterator[AsyncClient]:
    """Cliente que **recebe** o 500 em vez de relançar a exceção da app (CA30)."""
    async with AsyncClient(
        transport=ASGITransport(app=app_e2e, raise_app_exceptions=False),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers de fluxo
# ---------------------------------------------------------------------------


async def _criar_funcionario(
    client: AsyncClient, cabecalho: dict[str, str], unidade: str, nome: str
) -> str:
    funcao = await client.post(
        f"{API}/job-functions", json={"name": f"Função de {nome}"}, headers=cabecalho
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
    assert criado.json()["user_id"] is None
    return str(criado.json()["id"])


async def _criar_login(  # noqa: PLR0913 — a invocação de R17, com os dois campos do corpo nomeados
    client: AsyncClient,
    cabecalho: dict[str, str],
    unidade: str,
    employee_id: str,
    *,
    email: str,
    delivery: str,
) -> dict:
    resposta = await client.post(
        f"{API}/units/{unidade}/employees/{employee_id}/login",
        json={"email": email, "delivery": delivery},
        headers=cabecalho,
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    return resposta.json()


def _token_de(link: str) -> str:
    _, _, resto = link.partition("token=")
    return resto.split()[0]


def _link_do_ultimo_email(caixa: RecordingEmailSender) -> str:
    return next(linha for linha in caixa.sent[-1].body_text.splitlines() if "token=" in linha)


async def _definir_senha(client: AsyncClient, token: str) -> None:
    definir = await client.post(
        f"{API}/auth/password", json={"token": token, "password": _SENHA_DO_FUNCIONARIO}
    )
    assert definir.status_code == HTTPStatus.NO_CONTENT, definir.text


async def _login(client: AsyncClient, email: str, senha: str = _SENHA_DO_FUNCIONARIO) -> dict:
    entrou = await client.post(f"{API}/auth/login", json={"email": email, "password": senha})
    assert entrou.status_code == HTTPStatus.OK, entrou.text
    return entrou.json()


async def _registro(
    client: AsyncClient, cabecalho: dict[str, str], unidade: str, employee_id: str
) -> dict:
    listagem = await client.get(
        f"{API}/units/{unidade}/employees",
        params={"include_inactive": "true"},
        headers=cabecalho,
    )
    assert listagem.status_code == HTTPStatus.OK, listagem.text
    return next(item for item in listagem.json() if item["id"] == employee_id)


def _token_de_setup_do_usuario(engine: Engine, user_id: str) -> tuple[timedelta, str]:
    with engine.connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT issued_at, expires_at, token_fingerprint FROM password_setup_tokens "
                "WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        ).one()
    return linha.expires_at - linha.issued_at, str(linha.token_fingerprint)


def _valor_aparece_em_alguma_tabela_de_staff(engine: Engine, valor: str) -> bool:
    with engine.connect() as conexao:
        for tabela in _TABELAS_DE_STAFF:
            for linha in conexao.execute(text(f"SELECT * FROM {tabela}")):
                if valor in str(tuple(linha)):
                    return True
    return False


# ---------------------------------------------------------------------------
# CA22 — canal e-mail: o DoD inteiro pelo entrypoint real
# ---------------------------------------------------------------------------


async def test_ca22_canal_email_do_convite_ao_login_do_funcionario(
    client: AsyncClient,
    cenario: Cenario,
    caixa_de_entrada: RecordingEmailSender,
    engine: Engine,
) -> None:
    """Manager cria funcionário e login por e-mail; o link sai no e-mail; a pessoa
    define a senha e autentica; o registro mostra o `user_id`; o `employee` não
    alcança a equipe (403)."""
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Maria")

    corpo = await _criar_login(
        client,
        cabecalho,
        cenario.unidade_a,
        employee_id,
        email="maria@cantina.com",
        delivery="email",
    )

    assert corpo["setup_link"] is None
    assert corpo["employee"]["id"] == employee_id
    user_id = corpo["employee"]["user_id"]
    assert user_id
    assert len(caixa_de_entrada.sent) == 1
    assert caixa_de_entrada.sent[0].to == "maria@cantina.com"

    token = _token_de(_link_do_ultimo_email(caixa_de_entrada))
    await _definir_senha(client, token)
    tokens = await _login(client, "maria@cantina.com")
    assert tokens["access_token"] and tokens["refresh_token"]

    # CA13 — o gerente vê o vínculo no registro.
    assert (await _registro(client, cabecalho, cenario.unidade_a, employee_id))["user_id"] == (
        user_id
    )
    # O funcionário autenticado não detém `manage_staff`: 403, não 401.
    negado = await client.get(f"{API}/units/{cenario.unidade_a}/employees", headers=auth(tokens))
    assert negado.status_code == HTTPStatus.FORBIDDEN
    # CA32 — o token do canal e-mail vive o prazo do convite.
    prazo, _ = _token_de_setup_do_usuario(engine, user_id)
    assert prazo == timedelta(hours=72)


# ---------------------------------------------------------------------------
# CA23 — canal link: o segredo volta no corpo e nenhum e-mail sai
# ---------------------------------------------------------------------------


async def test_ca23_canal_link_devolve_o_link_e_nao_envia_email(
    client: AsyncClient,
    cenario: Cenario,
    caixa_de_entrada: RecordingEmailSender,
    engine: Engine,
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "João")

    corpo = await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="joao@cantina.com", delivery="link"
    )

    assert caixa_de_entrada.sent == ()
    link = corpo["setup_link"]
    assert link and "definir-senha?token=" in link
    assert link.startswith("http://localhost:8000/")  # `app_base_url` default

    # Antes de definir a senha, nenhuma senha abre a conta — nem a sentinela do dummy.
    for chute in (_SENTINELA_DUMMY, "qualquer-coisa"):
        tentativa = await client.post(
            f"{API}/auth/login", json={"email": "joao@cantina.com", "password": chute}
        )
        assert tentativa.status_code == HTTPStatus.UNAUTHORIZED

    await _definir_senha(client, _token_de(link))
    tokens = await _login(client, "joao@cantina.com")
    assert tokens["access_token"]
    # CA32 — o token do canal link vive o prazo de entrega em mãos.
    prazo, _ = _token_de_setup_do_usuario(engine, corpo["employee"]["user_id"])
    assert prazo == timedelta(hours=168)


# ---------------------------------------------------------------------------
# CA14 — o valor do token só aparece onde deve
# ---------------------------------------------------------------------------


async def test_ca14_o_valor_do_token_nao_aparece_em_staff_nem_em_log(
    client: AsyncClient,
    cenario: Cenario,
    caixa_de_entrada: RecordingEmailSender,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Ana")

    corpo = await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="ana@cantina.com", delivery="link"
    )
    valor = _token_de(corpo["setup_link"])

    assert not _valor_aparece_em_alguma_tabela_de_staff(engine, valor)
    assert valor not in caplog.text
    # Em identity só o fingerprint é gravado — e ele não é o valor.
    _, fingerprint = _token_de_setup_do_usuario(engine, corpo["employee"]["user_id"])
    assert fingerprint != valor
    assert valor not in fingerprint


# ---------------------------------------------------------------------------
# CA24 — desligamento corta a sessão; remoção recusa o vinculado
# ---------------------------------------------------------------------------


async def test_ca24_desligar_corta_o_refresh_mas_a_conta_continua_logando(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Bia")
    corpo = await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="bia@cantina.com", delivery="link"
    )
    await _definir_senha(client, _token_de(corpo["setup_link"]))
    tokens = await _login(client, "bia@cantina.com")

    desligado = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/termination", headers=cabecalho
    )

    assert desligado.status_code == HTTPStatus.OK, desligado.text
    assert desligado.json()["active"] is False
    assert desligado.json()["user_id"] == corpo["employee"]["user_id"]
    # A sessão foi revogada: o refresh morre.
    refresh = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == HTTPStatus.UNAUTHORIZED, refresh.text
    # O access token é stateless e ainda autentica (janela de `access_token_ttl`): 403, não 401.
    ainda = await client.get(f"{API}/units/{cenario.unidade_a}/employees", headers=auth(tokens))
    assert ainda.status_code == HTTPStatus.FORBIDDEN
    # A conta continua existindo e continua podendo logar (ADR 3.5.0003 §2).
    de_novo = await _login(client, "bia@cantina.com")
    assert de_novo["access_token"]
    # R14 não altera o vínculo.
    recontratado = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/rehire", headers=cabecalho
    )
    assert recontratado.status_code == HTTPStatus.OK
    assert recontratado.json()["user_id"] == corpo["employee"]["user_id"]


@pytest.mark.parametrize("desligado_antes", [False, True], ids=["ativo", "desligado"])
async def test_ca24_remover_vinculado_e_409_e_o_registro_e_a_sessao_ficam(
    client: AsyncClient,
    cenario: Cenario,
    caixa_de_entrada: RecordingEmailSender,
    desligado_antes: bool,
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Caio")
    corpo = await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="caio@cantina.com", delivery="link"
    )
    await _definir_senha(client, _token_de(corpo["setup_link"]))
    tokens = await _login(client, "caio@cantina.com")
    if desligado_antes:
        await client.post(
            f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/termination",
            headers=cabecalho,
        )
        # O desligamento já revogou; para medir "R15 não toca a sessão", loga de novo.
        tokens = await _login(client, "caio@cantina.com")

    removido = await client.delete(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}", headers=cabecalho
    )

    assert removido.status_code == HTTPStatus.CONFLICT, removido.text
    assert removido.json()["type"] == "staff_error"
    assert "desligue-o" in removido.json()["detail"]
    registro = await _registro(client, cabecalho, cenario.unidade_a, employee_id)
    assert registro["user_id"] == corpo["employee"]["user_id"]
    assert registro["active"] is not desligado_antes
    refresh = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == HTTPStatus.OK, refresh.text


# ---------------------------------------------------------------------------
# CA25 — as recusas, com corpo
# ---------------------------------------------------------------------------


async def test_ca25_segundo_login_para_o_mesmo_registro_e_409_ja_vinculado(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Duda")
    await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="duda@cantina.com", delivery="link"
    )

    for email in ("duda@cantina.com", "duda-novo@cantina.com"):
        segundo = await client.post(
            f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login",
            json={"email": email, "delivery": "link"},
            headers=cabecalho,
        )
        assert segundo.status_code == HTTPStatus.CONFLICT, segundo.text
        assert segundo.json()["type"] == "staff_error"
        assert "já tem login vinculado" in segundo.json()["detail"]
    assert len(caixa_de_entrada.sent) == 0


async def test_ca25_email_do_gerente_e_409_em_uso_com_o_email_no_detail(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Edu")

    recusado = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login",
        json={"email": "gerente@cantina.com", "delivery": "email"},
        headers=cabecalho,
    )

    assert recusado.status_code == HTTPStatus.CONFLICT, recusado.text
    assert recusado.json() == {
        "detail": "e-mail já usado como login: 'gerente@cantina.com'",
        "type": "staff_error",
    }
    assert caixa_de_entrada.sent == ()
    registro = await _registro(client, cabecalho, cenario.unidade_a, employee_id)
    assert registro["user_id"] is None


async def test_ca25_desligado_e_409_terminated(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Fê")
    await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/termination", headers=cabecalho
    )

    recusado = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login",
        json={"email": "fe@cantina.com", "delivery": "link"},
        headers=cabecalho,
    )

    assert recusado.status_code == HTTPStatus.CONFLICT, recusado.text
    assert "funcionário desligado não pode receber login" in recusado.json()["detail"]


async def test_ca25_registro_de_outra_unidade_e_404(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    """A unidade faz parte do endereço: B não é alcançado por A (ADR 3.4.0007)."""
    cabecalho = auth(cenario.manager)
    em_b = await _criar_funcionario(client, cabecalho, cenario.unidade_b, "Gui")

    recusado = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{em_b}/login",
        json={"email": "gui@cantina.com", "delivery": "link"},
        headers=cabecalho,
    )

    assert recusado.status_code == HTTPStatus.NOT_FOUND, recusado.text
    assert recusado.json()["type"] == "staff_error"
    assert (await _registro(client, cabecalho, cenario.unidade_b, em_b))["user_id"] is None


# ---------------------------------------------------------------------------
# CA26 — a cópia não carrega o vínculo
# ---------------------------------------------------------------------------


async def test_ca26_a_copia_de_um_vinculado_nasce_sem_login(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Hugo")
    corpo = await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="hugo@cantina.com", delivery="link"
    )

    copia = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/copies",
        json={"target_unit_id": cenario.unidade_b},
        headers=cabecalho,
    )

    assert copia.status_code == HTTPStatus.CREATED, copia.text
    assert copia.json()["user_id"] is None
    assert copia.json()["unit_id"] == cenario.unidade_b
    origem = await _registro(client, cabecalho, cenario.unidade_a, employee_id)
    assert origem["user_id"] == corpo["employee"]["user_id"]


# ---------------------------------------------------------------------------
# CA30 — gravar antes de entregar, pelo HTTP real
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "caixa_de_entrada",
    [RecordingEmailSender(fail_with=EmailSenderFailure("smtp fora"))],
    indirect=True,
    ids=["smtp-fora"],
)
async def test_ca30_falha_do_envio_e_500_e_o_vinculo_ja_esta_gravado(
    client_500: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    """O SMTP cai depois de a conta existir: a resposta é 500, e o registro aponta.

    O caminho de recuperação é o pedido público de redefinição de senha — não um
    segundo R17, que responde 409 (ADR 3.5.0002 §4).
    """
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client_500, cabecalho, cenario.unidade_a, "Iara")

    resposta = await client_500.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login",
        json={"email": "iara@cantina.com", "delivery": "email"},
        headers=cabecalho,
    )

    assert resposta.status_code == HTTPStatus.INTERNAL_SERVER_ERROR, resposta.text
    registro = await _registro(client_500, cabecalho, cenario.unidade_a, employee_id)
    assert registro["user_id"] is not None
    segundo = await client_500.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login",
        json={"email": "iara@cantina.com", "delivery": "email"},
        headers=cabecalho,
    )
    assert segundo.status_code == HTTPStatus.CONFLICT


# ---------------------------------------------------------------------------
# CA13 — o `user_id` sai em toda resposta de funcionário
# ---------------------------------------------------------------------------


async def test_ca13_o_vinculo_aparece_na_listagem_e_nas_escritas(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Lia")
    corpo = await _criar_login(
        client, cabecalho, cenario.unidade_a, employee_id, email="lia@cantina.com", delivery="link"
    )
    user_id = corpo["employee"]["user_id"]
    base = f"{API}/units/{cenario.unidade_a}/employees/{employee_id}"

    escritas = [
        await client.patch(base, json={"name": "Lia Souza"}, headers=cabecalho),
        await client.put(
            f"{base}/shift-preference", json={"shift_preference": ["night"]}, headers=cabecalho
        ),
        await client.post(f"{base}/termination", headers=cabecalho),
        await client.post(f"{base}/rehire", headers=cabecalho),
    ]

    for resposta in escritas:
        assert resposta.status_code == HTTPStatus.OK, resposta.text
        assert resposta.json()["user_id"] == user_id
    assert (await _registro(client, cabecalho, cenario.unidade_a, employee_id))["user_id"] == (
        user_id
    )


# ---------------------------------------------------------------------------
# CA31 — o byte NUL no e-mail é 422, não 500
# ---------------------------------------------------------------------------


async def test_ca31_email_com_byte_nul_e_422_de_staff(
    client: AsyncClient, cenario: Cenario, caixa_de_entrada: RecordingEmailSender
) -> None:
    """Era 500 (D8): a regex de `Email` aceitava o NUL e o `psycopg` o recusava.

    Agora o VO recusa, o gateway traduz para `InvalidLoginEmailError` (L-IG2) e o
    mapa de staff classifica como 422 — pelo HTTP real, contra Postgres.
    """
    cabecalho = auth(cenario.manager)
    employee_id = await _criar_funcionario(client, cabecalho, cenario.unidade_a, "Nul")

    resposta = await client.post(
        f"{API}/units/{cenario.unidade_a}/employees/{employee_id}/login",
        json={"email": "nul\x00@dentro.com", "delivery": "link"},
        headers=cabecalho,
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resposta.text
    assert resposta.json()["type"] == "staff_error"
    assert "e-mail de login inválido" in resposta.json()["detail"]
    assert (await _registro(client, cabecalho, cenario.unidade_a, employee_id))["user_id"] is None

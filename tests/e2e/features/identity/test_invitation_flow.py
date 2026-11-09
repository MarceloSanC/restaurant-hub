"""Fluxo de convite e redefinição pela app real — CA6c, CA7, CA11, CA12, CA15.

**É esta suíte que satisfaz o DoD da Stage 2.5**: "convite gera e-mail com link;
o token define a senha; login funciona". Não há fake de repositório nem de
segurança — o grafo sai do `wire_dependencies` de produção, com argon2, SHA-256 e
Postgres de verdade.

O **único** ponto substituído é o `EmailSender`, trocado por um que captura em
memória. Não é conveniência de teste: é requisito do ADR 0.0.0004 §Decision 7 —
nada sai da máquina. E a captura é o que permite pegar o link como a pessoa
convidada pegaria, em vez de espiar o banco (que só guarda o fingerprint) ou a
resposta da API (que, por desenho, não carrega o token).
"""

from collections.abc import AsyncIterator
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine

from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    _DUMMY_SENTINEL,
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import API_PREFIX, create_app
from tests.conftest import truncar_tudo
from tests.e2e.features.identity.conftest import (
    ADMIN_EMAIL,
    API,
    SENHA_PADRAO,
    auth,
    corpo_tenant,
    fazer_login,
)
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.e2e

SENHA_DEFINIDA = "senha-escolhida-pelo-convidado"


@pytest.fixture
def caixa_de_entrada() -> RecordingEmailSender:
    """O sender que captura tudo — nada sai da máquina (ADR 0.0.0004 §7)."""
    return RecordingEmailSender()


@pytest.fixture
def app_com_captura(
    engine: Engine, settings_e2e: Settings, caixa_de_entrada: RecordingEmailSender
) -> object:
    """App de produção com **apenas** o `EmailSender` substituído.

    A troca passa pela costura do composition root (`create_app(...,
    email_sender=...)`), que é o lugar certo: escolher a implementação de um port
    é literalmente o trabalho dele. A alternativa — montar a app, montar um
    **segundo** grafo e sobrescrever um atributo privado do use case — funcionava
    por acidente (dependia de os dois grafos terem exatamente as mesmas chaves de
    override) e deixava um `Engine` inteiro pendurado a cada teste.

    Tudo o mais continua sendo o wiring real: Postgres, argon2, SHA-256, JWT.
    """
    truncar_tudo(engine)
    return create_app(settings_e2e, email_sender=caixa_de_entrada)


@pytest.fixture
async def client_com_captura(app_com_captura: object) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_com_captura),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
def admin(engine: Engine, app_com_captura: object) -> User:
    """O `platform_admin` nasce fora da API — nenhuma rota o cria."""
    usuario = User(
        id=UserId("platform-admin-2-5"),
        email=Email(ADMIN_EMAIL),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )
    PostgresUserRepository(engine).add(usuario, Argon2PasswordHasher().hash(SENHA_PADRAO), ())
    return usuario


def _link_do_ultimo_email(caixa: RecordingEmailSender) -> str:
    """Extrai o token do corpo, como a pessoa convidada faria ao clicar."""
    corpo = caixa.sent[-1].body_text
    _, _, resto = corpo.partition("token=")
    return resto.split()[0]


async def _montar_restaurante_com_owner(
    client: AsyncClient, email_do_owner: str = "dono@cantina.com"
) -> tuple[str, dict]:
    """Semeia o cenário mínimo: um restaurante e o seu `owner` autenticado."""
    tokens_admin = await fazer_login(client, ADMIN_EMAIL)

    resposta = await client.post(
        f"{API}/restaurants",
        json=corpo_tenant("Cantina", email_do_owner),
        headers=auth(tokens_admin),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    restaurant_id = resposta.json()["id"]

    tokens_owner = await fazer_login(client, email_do_owner)
    return restaurant_id, tokens_owner


class TestFluxoCompletoDeConvite:
    async def test_convite_link_senha_e_login(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA15 — o DoD inteiro, pelo entrypoint real.

        Convite → e-mail capturado → link extraído → senha definida → login
        funciona. Cada seta é uma requisição HTTP de verdade contra Postgres.
        """
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)

        convite = await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "convidado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )
        assert convite.status_code == HTTPStatus.CREATED, convite.text

        assert len(caixa_de_entrada.sent) == 1
        assert caixa_de_entrada.sent[0].to == "convidado@cantina.com"
        token = _link_do_ultimo_email(caixa_de_entrada)

        definir = await client_com_captura.post(
            f"{API}/auth/password", json={"token": token, "password": SENHA_DEFINIDA}
        )
        assert definir.status_code == HTTPStatus.NO_CONTENT, definir.text

        entrou = await client_com_captura.post(
            f"{API}/auth/login",
            json={"email": "convidado@cantina.com", "password": SENHA_DEFINIDA},
        )
        assert entrou.status_code == HTTPStatus.OK, entrou.text
        assert entrou.json()["access_token"]
        assert entrou.json()["refresh_token"]

    async def test_resposta_do_convite_nao_carrega_o_token(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA14 — o token existe no e-mail e em lugar nenhum mais."""
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)

        convite = await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "convidado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )

        token = _link_do_ultimo_email(caixa_de_entrada)
        assert token not in convite.text

    async def test_login_antes_de_definir_a_senha_falha(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA11 — a conta existe e não é utilizável até a senha ser definida."""
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "convidado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )

        tentativa = await client_com_captura.post(
            f"{API}/auth/login",
            json={"email": "convidado@cantina.com", "password": "chute-qualquer"},
        )

        assert tentativa.status_code == HTTPStatus.UNAUTHORIZED

    async def test_login_com_a_sentinela_do_dummy_hash_falha(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA6c — o teste que existe por causa de uma vulnerabilidade real.

        `dummy_hash()` é o hash de `_DUMMY_SENTINEL`, uma constante **literal
        deste repositório**. Se a conta convidada carregasse esse hash — que era
        o plano original desta Stage —, qualquer pessoa que tivesse lido o código
        faria login como qualquer convidado que ainda não ativou a conta,
        recebendo o par de tokens com o papel e o tenant da vítima.

        O ADR 2.5.0004 trocou por `unusable_hash()`, aleatório por chamada. Este
        teste é o que impede a regressão pelo caminho real — os testes de contrato
        cobrem a lei do port; este cobre a rota.
        """
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "convidado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )

        tentativa = await client_com_captura.post(
            f"{API}/auth/login",
            json={"email": "convidado@cantina.com", "password": _DUMMY_SENTINEL},
        )

        assert tentativa.status_code == HTTPStatus.UNAUTHORIZED

    async def test_replay_do_link_falha_e_a_senha_continua_a_primeira(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA9 pelo caminho real: o mesmo link, duas vezes."""
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "convidado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )
        token = _link_do_ultimo_email(caixa_de_entrada)
        await client_com_captura.post(
            f"{API}/auth/password", json={"token": token, "password": SENHA_DEFINIDA}
        )

        segunda = await client_com_captura.post(
            f"{API}/auth/password", json={"token": token, "password": "senha-do-atacante"}
        )

        assert segunda.status_code == HTTPStatus.UNAUTHORIZED
        entrou = await client_com_captura.post(
            f"{API}/auth/login",
            json={"email": "convidado@cantina.com", "password": SENHA_DEFINIDA},
        )
        assert entrou.status_code == HTTPStatus.OK


class TestAutorizacaoDoConvite:
    """CA7 — convidar concede o mesmo acesso que criar, e exige o mesmo."""

    async def test_manager_nao_convida_owner(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """ "Não se concede o que não se detém", pela rota de convite.

        Um `manager` tem `manage_users` e **não** tem `manage_tenant`; emitir um
        `owner` seria escalada de privilégio numa requisição. Se a rota de convite
        afrouxasse aqui, seria a porta lateral da defesa que `POST /users` fecha.
        """
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "gerente@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )
        token = _link_do_ultimo_email(caixa_de_entrada)
        await client_com_captura.post(
            f"{API}/auth/password", json={"token": token, "password": SENHA_DEFINIDA}
        )
        tokens_manager = await fazer_login(
            client_com_captura, "gerente@cantina.com", SENHA_DEFINIDA
        )

        tentativa = await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "novo-dono@cantina.com", "role": "owner", "unit_ids": []},
            headers=auth(tokens_manager),
        )

        assert tentativa.status_code == HTTPStatus.FORBIDDEN

    async def test_convite_sem_autenticacao_e_401(
        self, client_com_captura: AsyncClient, admin: User
    ) -> None:
        resposta = await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "qualquer@x.com", "role": "manager", "unit_ids": []},
        )

        assert resposta.status_code == HTTPStatus.UNAUTHORIZED

    async def test_convite_de_email_ja_cadastrado_e_409(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """Reconvidar não funciona — o caminho de recuperação é a redefinição."""
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        corpo = {"email": "convidado@cantina.com", "role": "manager", "unit_ids": []}
        await client_com_captura.post(
            f"{API}/users/invitations", json=corpo, headers=auth(tokens_owner)
        )

        segunda = await client_com_captura.post(
            f"{API}/users/invitations", json=corpo, headers=auth(tokens_owner)
        )

        assert segunda.status_code == HTTPStatus.CONFLICT
        assert len(caixa_de_entrada.sent) == 1


class TestRedefinicaoDeSenha:
    async def test_respostas_sao_identicas_nos_tres_cenarios(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA12 pelo caminho real — status, corpo e cabeçalhos.

        Os três cenários: e-mail cadastrado e **ativo**, e-mail cadastrado e
        **ainda não ativado**, e e-mail **não cadastrado**. O segundo é o que um
        teste de dois cenários esqueceria, e é justamente o estado em que uma
        implementação distraída se comportaria diferente.
        """
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "nao-ativado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )

        respostas = [
            await client_com_captura.post(
                f"{API}/auth/password-reset-requests", json={"email": email}
            )
            for email in ("dono@cantina.com", "nao-ativado@cantina.com", "ninguem@x.com")
        ]

        comparaveis = {
            (
                r.status_code,
                r.content,
                tuple(
                    sorted(
                        (k.lower(), v)
                        for k, v in r.headers.items()
                        if k.lower() not in {"date", "server"}
                    )
                ),
            )
            for r in respostas
        }
        assert len(comparaveis) == 1
        assert respostas[0].status_code == HTTPStatus.ACCEPTED

    async def test_redefinicao_troca_a_senha_e_derruba_a_sessao(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """ADR 2.5.0003 pelo caminho real: o refresh anterior morre.

        É o cenário de retomada de conta: o atacante tinha uma sessão aberta, a
        vítima redefine a senha, e a sessão do atacante precisa parar de renovar.
        """
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)

        pedido = await client_com_captura.post(
            f"{API}/auth/password-reset-requests", json={"email": "dono@cantina.com"}
        )
        assert pedido.status_code == HTTPStatus.ACCEPTED
        token = _link_do_ultimo_email(caixa_de_entrada)

        await client_com_captura.post(
            f"{API}/auth/password", json={"token": token, "password": SENHA_DEFINIDA}
        )

        renovar = await client_com_captura.post(
            f"{API}/auth/refresh", json={"refresh_token": tokens_owner["refresh_token"]}
        )
        assert renovar.status_code == HTTPStatus.UNAUTHORIZED

        entrou = await client_com_captura.post(
            f"{API}/auth/login",
            json={"email": "dono@cantina.com", "password": SENHA_DEFINIDA},
        )
        assert entrou.status_code == HTTPStatus.OK

    async def test_pedido_de_reset_nao_mata_convite_pendente(
        self,
        client_com_captura: AsyncClient,
        caixa_de_entrada: RecordingEmailSender,
        admin: User,
    ) -> None:
        """CA13 pelo caminho real — o escopo por propósito impede a negação de serviço.

        Sem ele, qualquer pessoa na internet mataria o link de convite de qualquer
        vítima, em laço, batendo nesta rota pública.
        """
        _, tokens_owner = await _montar_restaurante_com_owner(client_com_captura)
        await client_com_captura.post(
            f"{API}/users/invitations",
            json={"email": "convidado@cantina.com", "role": "manager", "unit_ids": []},
            headers=auth(tokens_owner),
        )
        token_do_convite = _link_do_ultimo_email(caixa_de_entrada)

        await client_com_captura.post(
            f"{API}/auth/password-reset-requests", json={"email": "convidado@cantina.com"}
        )

        definir = await client_com_captura.post(
            f"{API}/auth/password",
            json={"token": token_do_convite, "password": SENHA_DEFINIDA},
        )
        assert definir.status_code == HTTPStatus.NO_CONTENT


def test_prefixo_da_api_e_o_esperado() -> None:
    """Guarda o caminho que os testes acima montam à mão."""
    assert API == API_PREFIX

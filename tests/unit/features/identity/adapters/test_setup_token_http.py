"""Boundary HTTP do fluxo de convite e redefinição — CA7, CA10, CA14, CA14b.

Estes testes montam a app real e batem nela pelo cliente HTTP; o que substituem
é o banco, não o boundary. O que protegem é o que só é observável **de fora**:
status, corpo e cabeçalhos — que é exatamente a superfície pela qual um atacante
distingue os casos que precisam ser indistinguíveis.
"""

import dataclasses
import importlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import InvalidSetupTokenError
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.infrastructure.http.error_handlers import (
    register_error_handlers,
)
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

# `in` é keyword Python: import estático deste caminho é SyntaxError (LAYOUT §8).
_PACOTE = "restaurant_hub.features.identity.adapters.in.http"
schemas = importlib.import_module(f"{_PACOTE}.schemas")
router_module = importlib.import_module(f"{_PACOTE}.router")
identity_error_handlers = importlib.import_module(f"{_PACOTE}.error_handlers")

_AGORA = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_VALOR = "setup-1"
_CADASTRADO = "cadastrado@x.com"

# Cabeçalhos que variam por natureza e não carregam informação sobre a base.
_CABECALHOS_VOLATEIS = frozenset({"date", "server"})

HTTP_NO_CONTENT = 204
HTTP_ACCEPTED = 202
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE = 422
HTTP_SERVER_ERROR = 500


class _UsuariosQueFalhamAoGravar(InMemoryUserRepository):
    """Falha só em `set_password_hash`, para observar a resposta HTTP."""

    def set_password_hash(self, user_id: UserId, password_hash: PasswordHash) -> None:
        raise RuntimeError("banco indisponível")


@dataclasses.dataclass
class Montagem:
    """A app real com os use cases reais e repositórios in-memory."""

    client: TestClient
    tokens: InMemoryPasswordSetupTokenRepository
    users: InMemoryUserRepository
    sessions: InMemorySessionRepository


# `noqa: PLR0913` — cada parâmetro liga/desliga um cenário do grafo de fakes.
def _montar(  # noqa: PLR0913
    *,
    com_token: bool = True,
    com_usuario: bool = True,
    expirado: bool = False,
    sender: RecordingEmailSender | None = None,
    users_quebrado: bool = False,
    propagar_excecao: bool = True,
) -> Montagem:
    users = _UsuariosQueFalhamAoGravar() if users_quebrado else InMemoryUserRepository()
    sessions = InMemorySessionRepository()
    tokens = InMemoryPasswordSetupTokenRepository()
    issuer = FakeSetupTokenIssuer()
    hasher = FakePasswordHasher()

    if com_usuario:
        users.add(
            User(
                id=UserId("user-1"),
                email=Email(_CADASTRADO),
                role=Role.MANAGER,
                tenant_id=RestaurantId("rest-a"),
            ),
            hasher.hash("senha-atual"),
        )
    if com_token:
        tokens.add(
            PasswordSetupToken(
                id=SetupTokenId("tok-1"),
                user_id=UserId("user-1"),
                purpose=SetupTokenPurpose.INVITATION,
                token_fingerprint=issuer.fingerprint(_VALOR),
                issued_at=_AGORA,
                expires_at=(
                    _AGORA - timedelta(seconds=1) if expirado else _AGORA + timedelta(hours=72)
                ),
            )
        )

    app = FastAPI()
    register_error_handlers(app)
    identity_error_handlers.register_identity_error_handlers(app)
    app.include_router(router_module.router)

    set_password = SetPasswordWithTokenUseCase(
        users=users,
        sessions=sessions,
        tokens=tokens,
        token_issuer=issuer,
        hasher=hasher,
        clock=FakeClock(_AGORA),
    )
    pedir_reset = RequestPasswordResetUseCase(
        users=users,
        tokens=tokens,
        token_issuer=issuer,
        email_sender=sender if sender is not None else RecordingEmailSender(),
        id_generator=FakeIdGenerator(),
        clock=FakeClock(_AGORA),
        reset_ttl=timedelta(minutes=30),
        base_url="https://app.exemplo.com",
    )
    app.dependency_overrides[router_module._get_set_password_with_token] = lambda: set_password
    app.dependency_overrides[router_module._get_request_password_reset] = lambda: pedir_reset

    return Montagem(client=TestClient(app), tokens=tokens, users=users, sessions=sessions)


def _resposta_comparavel(resposta: object) -> tuple[int, bytes, tuple[tuple[str, str], ...]]:
    """Status, corpo cru e cabeçalhos estáveis — tudo o que o cliente observa.

    Devolve uma tupla (hasheável) para que várias respostas possam ir para um
    `set` e a asserção seja "todas iguais", em vez de comparações par a par que
    esquecem um dos pares.
    """
    cabecalhos = tuple(
        sorted(
            (chave.lower(), valor)
            for chave, valor in resposta.headers.items()  # type: ignore[attr-defined]
            if chave.lower() not in _CABECALHOS_VOLATEIS
        )
    )
    return (resposta.status_code, resposta.content, cabecalhos)  # type: ignore[attr-defined]


class TestDefinirSenha:
    def test_token_valido_devolve_204_sem_corpo(self) -> None:
        """Regra 14 — definir a senha **não** autentica."""
        montagem = _montar()

        resposta = montagem.client.post(
            "/auth/password", json={"token": _VALOR, "password": "senha-nova"}
        )

        assert resposta.status_code == HTTP_NO_CONTENT
        assert resposta.content == b""

    def test_as_causas_de_falha_sao_indistinguiveis(self) -> None:
        """CA10 (HTTP) — status, corpo **e cabeçalhos** iguais nos quatro casos.

        Igualar só o status não bastaria: o corpo default é `{"detail": str(exc)}`
        e as mensagens deste BC carregam ids. É a faixa 401 de corpo constante que
        fecha isso, e este teste é quem prova que o erro novo caiu nela.
        """
        respostas = []

        montagem = _montar()
        respostas.append(
            montagem.client.post("/auth/password", json={"token": "nunca-emitido", "password": "x"})
        )

        montagem = _montar()
        montagem.client.post("/auth/password", json={"token": _VALOR, "password": "primeira"})
        respostas.append(
            montagem.client.post("/auth/password", json={"token": _VALOR, "password": "replay"})
        )

        montagem = _montar(com_usuario=False)
        respostas.append(
            montagem.client.post("/auth/password", json={"token": _VALOR, "password": "x"})
        )

        # A quarta causa, que a primeira versão deste teste omitia. As quatro
        # passam pelo mesmo `raise`, então o risco prático era baixo — mas a CA10
        # nomeia "token expirado" explicitamente, e um teste que não exercita o
        # que a CA nomeia é um teste que documenta a intenção sem verificá-la.
        montagem = _montar(expirado=True)
        respostas.append(
            montagem.client.post("/auth/password", json={"token": _VALOR, "password": "x"})
        )

        comparaveis = {_resposta_comparavel(r) for r in respostas}
        assert len(comparaveis) == 1
        assert respostas[0].status_code == HTTP_UNAUTHORIZED

    def test_corpo_do_401_nao_carrega_o_token(self) -> None:
        montagem = _montar()

        resposta = montagem.client.post(
            "/auth/password", json={"token": "token-secreto-do-atacante", "password": "x"}
        )

        assert "token-secreto-do-atacante" not in resposta.text

    def test_corpo_malformado_nao_ecoa_o_token(self) -> None:
        """CA14b — o handler default do FastAPI devolveria o `input` inteiro.

        É o vazamento que a regra 1 não previa, porque não vem do nosso código:
        vem do framework. Sem o handler de corpo constante, este teste falha com
        o token vivo dentro do JSON de erro — e o token vai junto para qualquer
        log de acesso que registre a resposta.
        """
        montagem = _montar()

        resposta = montagem.client.post("/auth/password", json={"token": "token-vivo-secreto"})

        assert resposta.status_code == HTTP_UNPROCESSABLE
        assert "token-vivo-secreto" not in resposta.text

    def test_falha_ao_gravar_a_senha_nao_vira_4xx(self) -> None:
        """§6 — consume OK e `set_password_hash` falhando propaga como 5xx.

        A conta fica **mais fechada** (token queimado, sessões revogadas, senha
        inalterada — regra 5), e o cliente precisa ver que algo deu errado. Um
        4xx aqui diria "seu token é inválido" a quem tem um token perfeitamente
        válido, e a pessoa pediria outro para sempre.
        """
        montagem = _montar(users_quebrado=True)

        with pytest.raises(RuntimeError):
            montagem.client.post("/auth/password", json={"token": _VALOR, "password": "x"})

    def test_replay_nao_regrava_a_senha(self) -> None:
        montagem = _montar()
        montagem.client.post("/auth/password", json={"token": _VALOR, "password": "primeira"})

        montagem.client.post("/auth/password", json={"token": _VALOR, "password": "do-atacante"})

        credenciais = montagem.users.find_credentials_by_email(Email(_CADASTRADO))
        assert credenciais is not None
        assert credenciais.password_hash == "hashed::primeira"


class TestPedirRedefinicao:
    def test_email_cadastrado_e_desconhecido_produzem_a_mesma_resposta(self) -> None:
        """CA12 (HTTP) — status, corpo e cabeçalhos idênticos, nos três cenários."""
        montagem = _montar()

        cadastrado = montagem.client.post(
            "/auth/password-reset-requests", json={"email": _CADASTRADO}
        )
        desconhecido = montagem.client.post(
            "/auth/password-reset-requests", json={"email": "nunca-vi@x.com"}
        )

        assert cadastrado.status_code == HTTP_ACCEPTED
        assert _resposta_comparavel(cadastrado) == _resposta_comparavel(desconhecido)

    def test_corpo_e_vazio_nos_dois_casos(self) -> None:
        """Sem corpo não há campo, mensagem nem contagem que difira."""
        montagem = _montar()

        cadastrado = montagem.client.post(
            "/auth/password-reset-requests", json={"email": _CADASTRADO}
        )
        desconhecido = montagem.client.post(
            "/auth/password-reset-requests", json={"email": "nunca-vi@x.com"}
        )

        assert cadastrado.content == b""
        assert desconhecido.content == b""

    def test_falha_do_sender_nao_muda_a_resposta(self) -> None:
        """CA12b no nível HTTP — a versão anterior comparava `None == None`.

        É o cenário do atacante: sondar endereços durante uma queda do provedor
        de e-mail. Se a exceção subisse, o cadastrado daria 500 e o desconhecido
        202 — enumeração completa pelo status, sem medir tempo.
        """
        montagem = _montar(sender=RecordingEmailSender(fail_with=RuntimeError("fora")))

        cadastrado = montagem.client.post(
            "/auth/password-reset-requests", json={"email": _CADASTRADO}
        )
        desconhecido = montagem.client.post(
            "/auth/password-reset-requests", json={"email": "nunca-vi@x.com"}
        )

        assert cadastrado.status_code == HTTP_ACCEPTED
        assert _resposta_comparavel(cadastrado) == _resposta_comparavel(desconhecido)

    def test_email_malformado_e_422(self) -> None:
        """Não fura a regra 7: o formato não revela nada sobre a base."""
        montagem = _montar()

        resposta = montagem.client.post(
            "/auth/password-reset-requests", json={"email": "isto-nao-e-email"}
        )

        assert resposta.status_code == HTTP_UNPROCESSABLE


class TestSchemasDeResposta:
    def test_nenhum_schema_de_resposta_carrega_token_de_setup(self) -> None:
        """CA14 — varredura enumerativa, não lista mantida à mão.

        Um schema novo entra na varredura sem ninguém lembrar dele, que é o
        ponto: a proteção não pode depender de alguém reler o concept.
        """
        proibidos = ("token", "setup", "link")

        for nome, obj in vars(schemas).items():
            if (
                not isinstance(obj, type)
                or not issubclass(obj, BaseModel)
                or not nome.endswith("Response")
            ):
                continue
            for campo in obj.model_fields:
                if nome == "TokenResponse":
                    # A única resposta que legitimamente carrega token é a do
                    # login/rotação, e ali o token **é** o produto da rota.
                    continue
                for proibido in proibidos:
                    assert proibido not in campo.lower(), f"{nome}.{campo}"

    def test_set_password_request_nao_tem_campo_de_usuario(self) -> None:
        """A ausência é a defesa — o alvo vem do token, nunca do corpo."""
        assert set(schemas.SetPasswordRequest.model_fields) == {"token", "password"}

    def test_invite_request_nao_tem_campo_de_senha_nem_de_tenant(self) -> None:
        """Quem convida não escolhe a senha, e o tenant vem do ator."""
        campos = set(schemas.InviteUserRequest.model_fields)

        assert "password" not in campos
        assert "tenant_id" not in campos


class TestErroDeSetupTokenNoMapa:
    def test_invalid_setup_token_cai_na_faixa_401_de_corpo_constante(self) -> None:
        resposta = identity_error_handlers.build_error_response(InvalidSetupTokenError())

        assert resposta.status_code == HTTP_UNAUTHORIZED
        assert resposta.headers["WWW-Authenticate"] == "Bearer"


def test_definir_senha_e_publica() -> None:
    """Sem `Authorization`, e é o desenho: quem esqueceu a senha não tem token.

    Se estas rotas exigissem autenticação, o fluxo de recuperação seria
    inalcançável exatamente por quem precisa dele.

    A asserção é o **204 do caminho feliz**, e não "não deu 401": aqui o 401 é
    ambíguo por natureza — é também a resposta legítima a um token inválido
    (`InvalidSetupTokenError`), de modo que uma asserção negativa não conseguiria
    separar "rota exige login" de "token não serve". Só a requisição que deveria
    ter sucesso, sem cabeçalho nenhum, distingue os dois.
    """
    montagem = _montar()

    resposta = montagem.client.post(
        "/auth/password", json={"token": _VALOR, "password": "senha-nova"}
    )

    assert resposta.status_code == HTTP_NO_CONTENT


def test_pedir_redefinicao_e_publica() -> None:
    """Idem para o pedido de redefinição — ver `test_definir_senha_e_publica`."""
    montagem = _montar()

    resposta = montagem.client.post("/auth/password-reset-requests", json={"email": _CADASTRADO})

    assert resposta.status_code == HTTP_ACCEPTED

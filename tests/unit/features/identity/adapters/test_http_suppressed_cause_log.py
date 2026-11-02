"""Issue #26 — a causa que o corpo constante dos 401/403 esconde vai para o log.

Duas propriedades andam juntas e são testadas juntas:

- o **corpo** segue idêntico entre causas diferentes da mesma faixa (o oráculo
  de enumeração continua fechado);
- o **log** as distingue — com status, rota, ator e a cadeia de causas — sem
  carregar material de credencial.

Uma sem a outra é o defeito que a issue nomeou: esconder do cliente prometendo
preservar noutro canal, e o canal não existir.
"""

import itertools
import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient, Response

from restaurant_hub.features.identity.adapters.inbound.http import error_handlers as handlers
from restaurant_hub.features.identity.adapters.inbound.http.dependencies import IdentityGuard
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    InvalidAccessTokenError,
    InvalidRefreshTokenError,
    InvalidSetupTokenError,
    PermissionDeniedError,
    RestaurantNotFoundError,
    UnitNotFoundError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    IdentityError,
    InvalidRoleError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock

pytestmark = pytest.mark.unit

_LOGGER = handlers.__name__
_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
_TENANT = RestaurantId("rest-1")
_SEGREDO_DA_LIB = "texto-que-a-lib-ecoou"


class _NegacaoComQuebraDeLinha(PermissionDeniedError):
    """Cobaia: mensagem com CR/LF crus, que nenhum erro de produção produz hoje."""

    def __init__(self) -> None:
        Exception.__init__(self, "linha 1\r\nWARNING forjado ator=admin")


class _Ambiente:
    """App mínima: o handler de verdade e o guard de verdade, sobre fakes."""

    def __init__(self) -> None:
        self.clock = FakeClock(_NOW)
        self.issuer = FakeTokenIssuer(clock=self.clock)
        self.users = InMemoryUserRepository()
        self.units = InMemoryUnitRepository()
        guard = IdentityGuard(
            token_issuer=self.issuer,
            authorize_action=AuthorizeActionUseCase(users=self.users, units=self.units),
        )
        app = FastAPI()
        handlers.register_identity_error_handlers(app)

        @app.post("/units/{unit_id}/users")
        def protegida(unit_id: str, request: Request) -> dict[str, str]:
            ator = guard.authenticate(request)
            guard.authorize(
                ator, Permission.MANAGE_USERS, tenant_id=_TENANT, unit_id=UnitId(unit_id)
            )
            return {"ok": "sim"}

        @app.post("/tenants/{tenant_id}/users")
        def outro_tenant(tenant_id: str, request: Request) -> dict[str, str]:
            ator = guard.authenticate(request)
            guard.authorize(ator, Permission.MANAGE_USERS, tenant_id=RestaurantId(tenant_id))
            return {"ok": "sim"}

        @app.post("/expirado")
        def expirado() -> None:
            try:
                raise jwt.ExpiredSignatureError(_SEGREDO_DA_LIB)
            except jwt.ExpiredSignatureError as exc:
                raise InvalidAccessTokenError() from exc

        @app.post("/refresh")
        def refresh() -> None:
            raise InvalidRefreshTokenError()

        @app.post("/quebra-de-linha")
        def quebra_de_linha() -> None:
            raise _NegacaoComQuebraDeLinha()

        @app.post("/faixa/{status}")
        def faixa(status: int) -> None:
            erros = {
                404: RestaurantNotFoundError("rest-9"),
                409: EmailAlreadyRegisteredError("a@b.com"),
                422: InvalidRoleError("papel-x"),
            }
            raise erros[status]

        self.app = app

    def owner(self, user_id: str = "user-7") -> str:
        user = User(
            id=UserId(user_id),
            email=Email(f"{user_id}@restaurante.com"),
            role=Role.OWNER,
            tenant_id=_TENANT,
        )
        self.users.add(user, PasswordHash("hashed::x"), ())
        return self.issuer.issue_access_token(
            AccessTokenClaims(
                subject=user.id,
                role=user.role,
                tenant_id=user.tenant_id,
                session_id=SessionId("sess-1"),
                expires_at=_NOW + timedelta(minutes=15),
            )
        )

    async def post(self, path: str, token: str | None = None) -> Response:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://t") as c:
            return await c.post(path, headers=headers)


def _campo(registro: logging.LogRecord, nome: str) -> object:
    """Campo estruturado que o handler passa em `extra`."""
    return registro.__dict__[nome]


def _registros(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _LOGGER]


@pytest.fixture
def ambiente() -> _Ambiente:
    return _Ambiente()


# ---------------------------------------------------------------------------
# O log registra a causa — e o corpo continua constante
# ---------------------------------------------------------------------------


async def test_403_registra_ator_rota_e_cadeia_de_causas(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    """A unidade inexistente vira `UnitNotVisibleError` no guard; o log guarda as duas."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    token = ambiente.owner("user-7")

    resposta = await ambiente.post("/units/unit-fantasma/users", token)

    assert resposta.status_code == handlers.HTTP_FORBIDDEN
    [registro] = _registros(caplog)
    assert registro.levelno == logging.WARNING
    assert _campo(registro, "auth_status") == handlers.HTTP_FORBIDDEN
    assert _campo(registro, "auth_method") == "POST"
    assert _campo(registro, "auth_route") == "/units/unit-fantasma/users"
    assert _campo(registro, "auth_actor") == "user-7"
    assert _campo(registro, "auth_cause") == (
        "UnitNotVisibleError: usuário 'user-7' não enxerga a unidade 'unit-fantasma'"
        " <- UnitNotFoundError"
    )
    mensagem = registro.getMessage()
    assert mensagem.startswith("resposta 403 com causa suprimida: POST /units/unit-fantasma/users")
    assert "ator=user-7" in mensagem
    assert "causa=UnitNotVisibleError" in mensagem


async def test_corpo_403_igual_e_log_diferente_entre_causas(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    """O par que a issue pediu: o corpo iguala, o log distingue."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    token = ambiente.owner()

    unidade = await ambiente.post("/units/unit-fantasma/users", token)
    tenant = await ambiente.post("/tenants/rest-2/users", token)

    assert unidade.status_code == tenant.status_code == handlers.HTTP_FORBIDDEN
    assert unidade.content == tenant.content
    causas = [str(_campo(r, "auth_cause")) for r in _registros(caplog)]
    assert [c.split(":")[0] for c in causas] == ["UnitNotVisibleError", "TenantNotVisibleError"]
    assert causas[0].startswith("UnitNotVisibleError")
    assert causas[1].startswith("TenantNotVisibleError")
    assert "'rest-2'" in causas[1]


async def test_corpo_401_igual_e_log_diferente_entre_causas(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    expirado = await ambiente.post("/expirado")
    refresh = await ambiente.post("/refresh")

    assert expirado.status_code == refresh.status_code == handlers.HTTP_UNAUTHORIZED
    assert expirado.content == refresh.content
    assert expirado.headers["WWW-Authenticate"] == refresh.headers["WWW-Authenticate"]
    causas = [str(_campo(r, "auth_cause")) for r in _registros(caplog)]
    assert causas == [
        "InvalidAccessTokenError: token de acesso inválido <- jwt.exceptions.ExpiredSignatureError",
        "InvalidRefreshTokenError: token de renovação inválido",
    ]


async def test_401_sem_autenticacao_registra_sem_ator(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    resposta = await ambiente.post("/units/unit-1/users")

    assert resposta.status_code == handlers.HTTP_UNAUTHORIZED
    [registro] = _registros(caplog)
    assert _campo(registro, "auth_actor") is None
    assert "ator=- " in registro.getMessage()


# ---------------------------------------------------------------------------
# O que NÃO entra no log
# ---------------------------------------------------------------------------


async def test_token_recusado_nao_aparece_no_log(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    """Nem o token forjado, nem o header — e o ator que ele alega não é atribuído."""
    caplog.set_level(logging.DEBUG)
    token = "token-forjado-que-nao-pode-ir-ao-log"

    resposta = await ambiente.post("/units/unit-1/users", token)

    assert resposta.status_code == handlers.HTTP_UNAUTHORIZED
    assert _registros(caplog)
    assert token not in caplog.text
    assert "Bearer" not in caplog.text


async def test_token_valido_nao_aparece_no_log_do_403(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    token = ambiente.owner()

    await ambiente.post("/units/unit-fantasma/users", token)

    assert _registros(caplog)
    assert token not in caplog.text


async def test_mensagem_de_excecao_de_fora_do_bc_nao_vai_ao_log(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    """Da exceção da lib entra só a classe: a mensagem pode ecoar o que o cliente mandou."""
    caplog.set_level(logging.DEBUG)

    await ambiente.post("/expirado")

    assert "ExpiredSignatureError" in caplog.text
    assert _SEGREDO_DA_LIB not in caplog.text


async def test_quebra_de_linha_na_mensagem_nao_forja_linha_de_log(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    """CWE-117 — CR/LF chegam escapados, e o registro continua sendo uma linha."""
    caplog.set_level(logging.WARNING, logger=_LOGGER)

    await ambiente.post("/quebra-de-linha")

    [registro] = _registros(caplog)
    mensagem = registro.getMessage()
    assert "\n" not in mensagem
    assert "\r" not in mensagem
    assert "linha 1\\r\\nWARNING forjado" in mensagem


async def test_caractere_de_controle_no_path_sai_escapado(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O path do `scope` ASGI vem decodificado e é do cliente: também é escapado.

    CR/LF/TAB o próprio Starlette já tira (`request.url` passa por `urlsplit`,
    que os descarta); o resto dos caracteres de controle passa — `ESC` abre
    sequência ANSI no terminal de quem lê o log. Chama o handler registrado
    direto, com o `scope` montado à mão, porque o cliente httpx normaliza o
    path antes de enviar.
    """
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    app = FastAPI()
    handlers.register_identity_error_handlers(app)
    handler = app.exception_handlers[IdentityError]
    request = Request(
        {"type": "http", "method": "POST", "path": "/units/a\x1b[2Jb\x00c", "headers": []}
    )

    await handler(request, PermissionDeniedError("owner", "manage_users"))  # type: ignore[misc]

    [registro] = _registros(caplog)
    mensagem = registro.getMessage()
    assert "\x1b" not in mensagem
    assert "\x00" not in mensagem
    assert _campo(registro, "auth_route") == "/units/a\\x1b[2Jb\\x00c"


@pytest.mark.parametrize("status", [404, 409, 422])
async def test_faixas_que_mostram_a_mensagem_nao_registram(
    ambiente: _Ambiente, caplog: pytest.LogCaptureFixture, status: int
) -> None:
    """Só 401/403 escondem a causa; as outras faixas a entregam no corpo."""
    caplog.set_level(logging.DEBUG, logger=_LOGGER)

    resposta = await ambiente.post(f"/faixa/{status}")

    assert resposta.status_code == status
    assert _registros(caplog) == []


# ---------------------------------------------------------------------------
# A cadeia de causas
# ---------------------------------------------------------------------------


def test_cadeia_segue_o_contexto_implicito() -> None:
    """`raise` dentro de `except`, sem `from`: o contexto implícito também é causa."""
    try:
        try:
            raise KeyError("sub")
        except KeyError:
            raise InvalidAccessTokenError()  # noqa: B904 — é o caso sob teste
    except InvalidAccessTokenError as exc:
        descricao = handlers.describe_suppressed_cause(exc)

    assert descricao == "InvalidAccessTokenError: token de acesso inválido <- KeyError"


def test_cadeia_respeita_from_none() -> None:
    """`from None` suprime o contexto — é como `RefreshTokenReuseError` sai."""
    try:
        try:
            raise ValueError("interno")
        except ValueError:
            raise InvalidRefreshTokenError() from None
    except InvalidRefreshTokenError as exc:
        descricao = handlers.describe_suppressed_cause(exc)

    assert descricao == "InvalidRefreshTokenError: token de renovação inválido"


def test_cadeia_com_ciclo_termina() -> None:
    externa = InvalidAccessTokenError()
    interna = UnitNotFoundError("u-1")
    externa.__cause__ = interna
    interna.__cause__ = externa

    descricao = handlers.describe_suppressed_cause(externa)

    assert descricao == "InvalidAccessTokenError: token de acesso inválido <- UnitNotFoundError"


def test_cadeia_longa_para_no_teto() -> None:
    elos = [UnitNotFoundError(f"u-{i}") for i in range(handlers._ELOS_MAXIMOS + 2)]
    for externa, interna in itertools.pairwise(elos):
        externa.__cause__ = interna

    descricao = handlers.describe_suppressed_cause(elos[0])

    assert descricao.count("UnitNotFoundError") == handlers._ELOS_MAXIMOS
    assert descricao.startswith("UnitNotFoundError: unidade não encontrada: 'u-0' <- ")


def test_mensagem_de_causa_do_bc_nao_vai_ao_log() -> None:
    """Só a mensagem do elo externo entra — a das causas foi escrita para outro corpo.

    `InvalidSetupTokenError` nasce `from UserNotFoundError(user_id)` na rota
    pública de definição de senha; o id do dono do token, que ela própria se
    recusa a interpolar, não pode chegar ao log pela causa.
    """
    try:
        try:
            raise UserNotFoundError("id-do-dono-do-token")
        except UserNotFoundError as exc:
            raise InvalidSetupTokenError() from exc
    except InvalidSetupTokenError as exc:
        descricao = handlers.describe_suppressed_cause(exc)

    assert descricao == (
        "InvalidSetupTokenError: token de definição de senha inválido <- UserNotFoundError"
    )

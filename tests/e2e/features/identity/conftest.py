"""Fixtures dos testes e2e de identity — app FastAPI real contra Postgres real.

**É esta suíte que satisfaz o DoD da issue #24.** O requisito não é "os use cases
funcionam" — isso as Stages 2.2 e 2.3 já provaram —, e sim que o fluxo seja
exercitado pelo **entrypoint real**. Por isso aqui não há fake nenhum: o grafo
sai do `wire_dependencies` de produção, com argon2 de verdade, JWT de verdade e
os repositórios Postgres de verdade.

**O `platform_admin` é semeado pelo repositório, não por rota** — e isso não é
atalho de teste: **nenhuma rota o cria** (concept §5 regra 8), porque criar um
`platform_admin` exigiria `manage_users` mais `manage_platform`, e o mapa de
papéis da 2.1 não dá os dois a ninguém. A raiz de confiança nasce fora da API,
como em qualquer sistema; o `[finding]` de um comando de seed está registrado
para o Step 6.
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
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import create_app
from tests.conftest import truncar_tudo

SENHA_PADRAO = "s3nha-de-teste-e2e"
ADMIN_EMAIL = "admin@plataforma.com"
API = "/api/v1"


@pytest.fixture
def settings_e2e(database_url: str) -> Settings:
    """`Settings` do teste, apontando para o banco da worktree.

    Construído explicitamente (e não por `get_settings()`) porque `get_settings`
    é cacheado por processo: um teste que quisesse outro TTL não conseguiria
    trocá-lo sem contaminar os demais.
    """
    return Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret_key="segredo-de-teste-e2e-com-32-bytes-ou-mais",
    )


@pytest.fixture
def app_e2e(engine: Engine, settings_e2e: Settings) -> object:
    """App real, montada pelo composition root de produção, com banco limpo.

    O `TRUNCATE` roda **antes** do teste: quando um teste falha, o estado que ele
    deixou permanece para diagnóstico, e ainda assim o próximo começa limpo.
    """
    truncar_tudo(engine)
    return create_app(settings_e2e)


@pytest.fixture
async def client(app_e2e: object) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_e2e),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
def admin_semeado(engine: Engine, app_e2e: object) -> User:
    """Insere o `platform_admin` direto pelo repositório — ver docstring do módulo.

    Usa o **hasher real**, para que a senha semeada seja verificável pelo login
    de verdade. Um hash de fake aqui faria o primeiro login falhar por motivo
    completamente alheio ao que o teste investiga.
    """
    admin = User(
        id=UserId("platform-admin-e2e"),
        email=Email(ADMIN_EMAIL),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )
    PostgresUserRepository(engine).add(admin, Argon2PasswordHasher().hash(SENHA_PADRAO), ())
    return admin


async def fazer_login(client: AsyncClient, email: str, senha: str = SENHA_PADRAO) -> dict:
    """Faz login pela API e devolve o corpo do par de tokens."""
    resposta = await client.post(f"{API}/auth/login", json={"email": email, "password": senha})
    assert resposta.status_code == HTTPStatus.OK, resposta.text
    return resposta.json()


def corpo_tenant(nome: str, email_do_dono: str, senha: str = SENHA_PADRAO) -> dict:
    """Corpo de `POST /restaurants`: o restaurante **e** o seu primeiro dono.

    Desde a issue #67 (ADR 0.0.0012) o restaurante nasce com o dono, numa unidade
    de trabalho — não há mais chamada que crie restaurante sozinho.
    """
    return {"name": nome, "owner": {"email": email_do_dono, "password": senha}}


def auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}

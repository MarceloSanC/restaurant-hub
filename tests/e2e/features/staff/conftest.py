"""Fixtures dos e2e de staff — app FastAPI real contra Postgres real.

**É esta suíte que satisfaz o DoD do roadmap e da issue #43.** O requisito não é
"os use cases funcionam" — as Stages 3.2 e 3.3 já provaram isso —, e sim que a
equipe seja gerida pelo **entrypoint real**. Não há fake nenhum aqui: o grafo sai
do `wire_dependencies` de produção, com argon2, JWT e os repositórios Postgres de
verdade.

**A cadeia de provisionamento vem inteira pela API de identity**, e isso não é
cerimônia: é o que faz o token que staff recebe ser um token **emitido pela
aplicação**, com as claims que a aplicação de verdade coloca nele. Semear o
usuário pelo repositório pouparia meia dúzia de chamadas e apagaria justamente a
propriedade que o ADR 0.0.0005 introduziu — que o tenant vem do **token**.

O único objeto semeado fora da API é o `platform_admin`, pela mesma razão que a
suíte de identity documenta: **nenhuma rota o cria**, porque criá-lo exigiria
`manage_users` mais `manage_platform`, e o mapa de papéis não dá os dois a
ninguém. A raiz de confiança nasce fora da API, como em qualquer sistema.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
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
from tests.e2e.features.identity.conftest import login_do_dono
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

SENHA_PADRAO = "s3nha-de-teste-e2e"
ADMIN_EMAIL = "admin-staff@plataforma.com"
API = "/api/v1"


@pytest.fixture
def settings_e2e(database_url: str) -> Settings:
    """`Settings` do teste, apontando para o banco da worktree."""
    return Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret_key="segredo-de-teste-e2e-com-32-bytes-ou-mais",
    )


@pytest.fixture
def caixa_de_entrada() -> RecordingEmailSender:
    """Captura os e-mails: o dono provisionado entra pelo convite (ADR 0.0.0018)."""
    return RecordingEmailSender()


@pytest.fixture
def app_e2e(
    engine: Engine, settings_e2e: Settings, caixa_de_entrada: RecordingEmailSender
) -> object:
    """App real, montada pelo composition root de produção, com banco limpo.

    O `TRUNCATE` roda **antes** do teste: quando um teste falha, o estado que ele
    deixou permanece para diagnóstico, e ainda assim o próximo começa limpo. Só o
    `EmailSender` é trocado, pela costura do composition root.
    """
    truncar_tudo(engine)
    return create_app(settings_e2e, email_sender=caixa_de_entrada)


@pytest.fixture
async def client(app_e2e: object) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_e2e),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as c:
        yield c


def auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def fazer_login(client: AsyncClient, email: str, senha: str = SENHA_PADRAO) -> dict:
    """Faz login pela API e devolve o corpo do par de tokens."""
    resposta = await client.post(f"{API}/auth/login", json={"email": email, "password": senha})
    assert resposta.status_code == HTTPStatus.OK, resposta.text
    return resposta.json()


@dataclass(frozen=True)
class Cenario:
    """O restaurante provisionado, com duas unidades e os atores de cada papel.

    Duas unidades porque **o isolamento é a propriedade central** desta Stage:
    com uma só, CA26 e CA34 não teriam onde acontecer.
    """

    restaurante_id: str
    unidade_a: str
    unidade_b: str
    owner: dict
    manager: dict


@pytest.fixture
def admin_semeado(engine: Engine, app_e2e: object) -> User:
    """Insere o `platform_admin` direto pelo repositório — ver docstring do módulo."""
    admin = User(
        id=UserId("platform-admin-staff-e2e"),
        email=Email(ADMIN_EMAIL),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )
    PostgresUserRepository(engine).add(admin, Argon2PasswordHasher().hash(SENHA_PADRAO), ())
    return admin


@pytest.fixture
async def cenario(
    client: AsyncClient, admin_semeado: User, caixa_de_entrada: RecordingEmailSender
) -> Cenario:
    """Provisiona restaurante, duas unidades e os atores — **tudo pela API**.

    O `manager` é membro das **duas** unidades de propósito: o alcance dele é
    "as unidades das quais é membro", e um manager de uma unidade só faria CA26
    passar por falta de visibilidade em vez de por isolamento — que é medir outra
    coisa.
    """
    admin = await fazer_login(client, ADMIN_EMAIL)

    resposta = await client.post(
        f"{API}/restaurants",
        json={
            "name": "Cantina do Zé",
            "owner": {"email": "dono@cantina.com"},
        },
        headers=auth(admin),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    restaurante_id = resposta.json()["id"]
    owner = await login_do_dono(client, caixa_de_entrada, "dono@cantina.com")

    unidades = []
    for nome in ("Filial Centro", "Filial Praia"):
        resposta = await client.post(
            f"{API}/restaurants/{restaurante_id}/units",
            json={"name": nome},
            headers=auth(owner),
        )
        assert resposta.status_code == HTTPStatus.CREATED, resposta.text
        unidades.append(resposta.json()["id"])

    resposta = await client.post(
        f"{API}/users",
        json={
            "email": "gerente@cantina.com",
            "password": SENHA_PADRAO,
            "role": "manager",
            "unit_ids": unidades,
        },
        headers=auth(owner),
    )
    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    manager = await fazer_login(client, "gerente@cantina.com")

    return Cenario(
        restaurante_id=restaurante_id,
        unidade_a=unidades[0],
        unidade_b=unidades[1],
        owner=owner,
        manager=manager,
    )

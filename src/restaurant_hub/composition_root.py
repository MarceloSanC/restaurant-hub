"""Composition Root — único ponto de wiring de dependências da aplicação.

Este módulo é o ÚNICO lugar que conhece as implementações concretas. Ele instancia
cada dependência de infraestrutura e injeta nas camadas de aplicação. Se você
precisar trocar uma implementação (ex: Postgres → DynamoDB), mude APENAS aqui.
Nenhuma regra de negócio deve ser alterada.

Regra: nenhum outro módulo deve instanciar diretamente classes de `infrastructure/`
ou de `adapters/`. Há teste mecânico disso em
`tests/unit/features/identity/adapters/test_composition_root_identity.py` — a regra
é fácil de violar sem querer e invisível numa revisão de diff.

**Sobre o `ignore_imports` que este arquivo motiva** (Stage 2.3): a partir daqui o
composition root importa `features.identity.adapters`, e
`shared/infrastructure/http/app.py` importa o composition root. A cadeia
`shared → composition_root → features.adapters` viola literalmente o contrato
`shared-independence` do import-linter, e é a **exceção declarada em LAYOUT §6**.
A supressão lá é a mais estreita possível: só este par.

**Sobre o `importlib` do adapter de entrada** (Stage 2.4): o pacote se chama `in`,
que é palavra reservada do Python — `from ...adapters.in.http...` é **SyntaxError**,
não ImportError. Não há como importá-lo estaticamente, e o `importlib` é a única
forma suportada (LAYOUT §8), não um contorno do gate.

**Por que o composition root entrega também o mapa de `dependency_overrides`:** as
chaves desse dicionário são os provedores `_get_*` definidos dentro de `router.py`.
Se `app.py` tivesse de alcançá-los, `shared` passaria a importar feature — e a
supressão estreita acima deixaria de bastar. Entregando o mapa pronto, `app.py`
continua sem conhecer feature nenhuma.
"""

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, FastAPI

from restaurant_hub.features.identity.adapters.out.postgres.password_setup_token_repository import (
    PostgresPasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.adapters.out.security.jwt_issuer import (
    JwtTokenIssuer,
)
from restaurant_hub.features.identity.adapters.out.security.setup_token_issuer import (
    Sha256SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_restaurant import (
    CreateRestaurantUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_session import (
    RevokeSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
)
from restaurant_hub.shared.infrastructure.clock.system_clock import SystemClock
from restaurant_hub.shared.infrastructure.config.settings import Settings, get_settings
from restaurant_hub.shared.infrastructure.database.connection import build_engine
from restaurant_hub.shared.infrastructure.email.console_sender import ConsoleSender
from restaurant_hub.shared.infrastructure.uuid_generator.uuid4_generator import (
    Uuid4Generator,
)

_PACOTE_HTTP_IDENTITY = "restaurant_hub.features.identity.adapters.in.http"


@dataclass
class ApplicationDependencies:
    """Contêiner com as dependências montadas e prontas para uso.

    Expõe **use cases**, não repositórios: a partir da Stage 2.4 os repositórios
    recuam para dentro deles, que é o que o docstring da versão anterior deste
    arquivo já antecipava. Os tipos são as classes de use case, e não ports,
    porque use case é código nosso — o que precisa ser abstrato é o que ele
    **consome**, e isso já está garantido pelas anotações de port nos construtores.
    """

    identity_authenticate_user: AuthenticateUserUseCase
    identity_refresh_session: RefreshSessionUseCase
    identity_revoke_session: RevokeSessionUseCase
    identity_create_restaurant: CreateRestaurantUseCase
    identity_create_unit: CreateUnitUseCase
    identity_create_user: CreateUserUseCase
    identity_invite_user: InviteUserUseCase
    identity_request_password_reset: RequestPasswordResetUseCase
    identity_set_password_with_token: SetPasswordWithTokenUseCase
    identity_authorize_action: AuthorizeActionUseCase
    # `Any` porque o tipo real (`IdentityGuard`) vive num pacote que só pode ser
    # carregado por `importlib` — anotá-lo exigiria o import estático que a
    # keyword `in` torna sintaticamente impossível.
    identity_guard: Any


@dataclass
class HttpWiring:
    """O que `create_app()` registra, montado sem que ele conheça features.

    São três peças, e as três são necessárias: o router; o registrador de handlers
    de erro (que recebe o `app`, porque só o app registra exception handlers); e o
    mapa de overrides, cujas chaves vivem dentro do módulo do router.
    """

    router: APIRouter
    register_error_handlers: Callable[[FastAPI], None]
    dependency_overrides: dict[Callable[..., Any], Callable[..., Any]]


def wire_dependencies(settings: Settings | None = None) -> ApplicationDependencies:
    """Monta o grafo de dependências completo e devolve o contêiner.

    Chamado uma única vez na inicialização da aplicação (dentro de `create_app()`).
    Em testes, pode receber um `Settings` apontando para outro banco ou com outros
    TTLs — é o que torna o TTL observável como configuração (CA25).

    **Sem singleton global.** O `Engine` é criado aqui e vive dentro dos
    repositórios que o receberam; não há variável de módulo guardando conexão. Duas
    chamadas devolvem dois grafos independentes.

    `create_engine` **não abre conexão** (o pool é preguiçoso), então montar o grafo
    não exige banco no ar e o boot da aplicação não falha por causa de um Postgres
    que ainda está subindo.
    """
    cfg = settings or get_settings()
    engine = build_engine(cfg.database_url)

    restaurants = PostgresRestaurantRepository(engine)
    units = PostgresUnitRepository(engine)
    users = PostgresUserRepository(engine)
    sessions = PostgresSessionRepository(engine)

    setup_tokens = PostgresPasswordSetupTokenRepository(engine)

    hasher = Argon2PasswordHasher()
    setup_token_issuer = Sha256SetupTokenIssuer()
    # `ConsoleSender` é o adapter desta Stage: escreve local, nada sai da máquina
    # (ADR 0.0.0004 §Decision 7). O provedor real (Resend, kickoff #7) entra na
    # 6.2 e é a troca de **uma linha** aqui — nenhum use case muda, porque todos
    # dependem do port `EmailSender`, não desta classe.
    email_sender = ConsoleSender()
    token_issuer = JwtTokenIssuer(secret_key=cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)
    clock = SystemClock()
    id_generator = Uuid4Generator()

    # TTLs vêm da configuração, nunca de literal no corpo de use case
    # (concept §5 regra 12 — este número é a janela de revogação do produto).
    access_ttl = timedelta(minutes=cfg.access_token_ttl_minutes)
    refresh_ttl = timedelta(days=cfg.refresh_token_ttl_days)
    # Unidades diferentes de propósito — ver `Settings`: convite tolera dias de
    # atraso humano, redefinição de senha é emergência de minutos.
    invitation_ttl = timedelta(hours=cfg.invitation_token_ttl_hours)
    reset_ttl = timedelta(minutes=cfg.password_reset_token_ttl_minutes)

    authorize_action = AuthorizeActionUseCase(users=users, units=units)

    dependencies_module = importlib.import_module(f"{_PACOTE_HTTP_IDENTITY}.dependencies")
    guard = dependencies_module.IdentityGuard(
        token_issuer=token_issuer,
        authorize_action=authorize_action,
    )

    return ApplicationDependencies(
        identity_authenticate_user=AuthenticateUserUseCase(
            users=users,
            sessions=sessions,
            hasher=hasher,
            token_issuer=token_issuer,
            id_generator=id_generator,
            clock=clock,
            access_token_ttl=access_ttl,
            refresh_token_ttl=refresh_ttl,
        ),
        identity_refresh_session=RefreshSessionUseCase(
            users=users,
            sessions=sessions,
            token_issuer=token_issuer,
            id_generator=id_generator,
            clock=clock,
            access_token_ttl=access_ttl,
            refresh_token_ttl=refresh_ttl,
        ),
        identity_revoke_session=RevokeSessionUseCase(
            sessions=sessions, token_issuer=token_issuer, clock=clock
        ),
        identity_create_restaurant=CreateRestaurantUseCase(
            restaurants=restaurants, id_generator=id_generator
        ),
        identity_create_unit=CreateUnitUseCase(
            units=units, restaurants=restaurants, id_generator=id_generator
        ),
        identity_create_user=CreateUserUseCase(
            users=users,
            restaurants=restaurants,
            units=units,
            hasher=hasher,
            id_generator=id_generator,
        ),
        identity_invite_user=InviteUserUseCase(
            users=users,
            restaurants=restaurants,
            units=units,
            hasher=hasher,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            email_sender=email_sender,
            id_generator=id_generator,
            clock=clock,
            invitation_ttl=invitation_ttl,
            base_url=cfg.app_base_url,
        ),
        identity_request_password_reset=RequestPasswordResetUseCase(
            users=users,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            email_sender=email_sender,
            id_generator=id_generator,
            clock=clock,
            reset_ttl=reset_ttl,
            base_url=cfg.app_base_url,
        ),
        identity_set_password_with_token=SetPasswordWithTokenUseCase(
            users=users,
            sessions=sessions,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            hasher=hasher,
            clock=clock,
        ),
        identity_authorize_action=authorize_action,
        identity_guard=guard,
    )


def build_http_wiring(deps: ApplicationDependencies) -> HttpWiring:
    """Carrega o adapter HTTP de identity e monta o que `create_app()` registra."""
    router_module = importlib.import_module(f"{_PACOTE_HTTP_IDENTITY}.router")
    error_handlers_module = importlib.import_module(f"{_PACOTE_HTTP_IDENTITY}.error_handlers")

    overrides: dict[Callable[..., Any], Callable[..., Any]] = {
        router_module._get_authenticate_user: lambda: deps.identity_authenticate_user,
        router_module._get_refresh_session: lambda: deps.identity_refresh_session,
        router_module._get_revoke_session: lambda: deps.identity_revoke_session,
        router_module._get_create_restaurant: lambda: deps.identity_create_restaurant,
        router_module._get_create_unit: lambda: deps.identity_create_unit,
        router_module._get_create_user: lambda: deps.identity_create_user,
        router_module._get_invite_user: lambda: deps.identity_invite_user,
        router_module._get_request_password_reset: (lambda: deps.identity_request_password_reset),
        router_module._get_set_password_with_token: (lambda: deps.identity_set_password_with_token),
        router_module._get_guard: lambda: deps.identity_guard,
    }

    return HttpWiring(
        router=router_module.router,
        register_error_handlers=error_handlers_module.register_identity_error_handlers,
        dependency_overrides=overrides,
    )

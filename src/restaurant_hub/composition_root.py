"""Composition Root — único ponto de wiring de dependências da aplicação.

Este módulo é o ÚNICO lugar que conhece as implementações concretas. Ele instancia
cada dependência de infraestrutura e injeta nas camadas de aplicação. Se você
precisar trocar uma implementação (ex: Postgres → DynamoDB), mude APENAS aqui.
Nenhuma regra de negócio deve ser alterada.

Regra: nenhum outro módulo deve instanciar diretamente classes de `infrastructure/`
ou de `adapters/out/`. Sempre receba dependências via construtor (injeção
explícita). Há teste mecânico disso em
`tests/unit/features/identity/adapters/test_composition_root_identity.py` — a regra
é fácil de violar sem querer e invisível numa revisão de diff.

**Sobre o `ignore_imports` que este arquivo motiva** (Stage 2.3): a partir daqui o
composition root importa `features.identity.adapters.out.postgres`, e
`shared/infrastructure/http/app.py` importa o composition root. A cadeia
`shared → composition_root → features.adapters` viola literalmente o contrato
`shared-independence` do import-linter, e é a **exceção declarada em LAYOUT §6** —
prevista, inclusive, no cabeçalho do próprio `.importlinter` desde a Stage 1.1. A
supressão lá é a mais estreita possível: só este par.
"""

from dataclasses import dataclass

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
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.application.ports.out.session_repository import (
    SessionRepository,
)
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings, get_settings
from restaurant_hub.shared.infrastructure.database.connection import build_engine


@dataclass
class ApplicationDependencies:
    """Contêiner com as dependências montadas e prontas para uso.

    Os campos são anotados com os **ports** (`RestaurantRepository`, …), não com as
    classes concretas. Não é decoração: é o que faz o type-checker recusar um
    consumidor que passe a depender de detalhe do Postgres, e o que permite injetar
    os fakes aqui sem mudar assinatura nenhuma.

    Os repositórios ficam expostos porque a Stage 2.3 ainda não tem use cases
    montados — eles chegam na 2.4, e então este contêiner passa a expor use cases,
    com os repositórios recuando para dentro deles.
    """

    identity_restaurants: RestaurantRepository
    identity_units: UnitRepository
    identity_users: UserRepository
    identity_sessions: SessionRepository


def wire_dependencies(settings: Settings | None = None) -> ApplicationDependencies:
    """Monta o grafo de dependências completo e devolve o contêiner.

    Chamado uma única vez na inicialização da aplicação (dentro de `create_app()`).
    Em testes, pode receber um `Settings` apontando para outro banco.

    **Sem singleton global.** O `Engine` é criado aqui e vive dentro dos
    repositórios que o receberam; não há variável de módulo guardando conexão. Duas
    chamadas devolvem dois grafos independentes — é o que permite a um teste montar
    o seu próprio grafo sem contaminar o de outro.

    `create_engine` **não abre conexão** (o pool é preguiçoso), então montar o grafo
    não exige banco no ar e o boot da aplicação não falha por causa de um Postgres
    que ainda está subindo.
    """
    cfg = settings or get_settings()
    engine = build_engine(cfg.database_url)
    return ApplicationDependencies(
        identity_restaurants=PostgresRestaurantRepository(engine),
        identity_units=PostgresUnitRepository(engine),
        identity_users=PostgresUserRepository(engine),
        identity_sessions=PostgresSessionRepository(engine),
    )

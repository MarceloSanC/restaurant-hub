"""Fixtures do contrato — a MESMA suíte rodando contra o fake e contra o Postgres.

Este arquivo é o mecanismo que a Stage 2.2 encomendou à 2.3. O concept da 2.2
registrou como risco "fake e futuro adapter Postgres divergirem no contrato", e
mitigou com "semântica normativa escrita como lei testável; **contract tests são da
2.3**". É aqui que a dívida é paga.

**Por que os quatro repositórios vêm num pacote só** (`Repositorios`), em vez de uma
fixture por port: o Postgres tem chaves estrangeiras e o fake não. Uma sessão exige
um usuário, que exige um restaurante. Se cada port fosse parametrizado
isoladamente, o corpo do teste teria de semear pré-requisitos de um jeito para o
fake e de outro para o real — e testes que se ramificam por implementação deixam de
ser testes de contrato. Com o pacote, o teste semeia pelos próprios ports e o mesmo
código serve às duas implementações.

**O que fica de fora, explicitamente** (CA16): os ganchos que só existem no fake e
não pertencem ao port — `seed_membership`, `list_all_memberships`,
`leak_foreign_memberships` e os contadores `find_calls`. Não são divergência: são
instrumentação de teste, e um contrato que os exigisse do adapter real estaria
inventando requisito.
"""

from dataclasses import dataclass

import pytest
from sqlalchemy import Engine

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
from tests.conftest import truncar_tudo
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository


@dataclass(frozen=True)
class Repositorios:
    """Os quatro repositórios de uma mesma implementação.

    O corpo do teste recebe isto e **não sabe** se está falando com dicionários em
    memória ou com o PostgreSQL. Essa ignorância é o ponto: qualquer `if` sobre a
    implementação transformaria o teste de contrato em dois testes diferentes que
    apenas se parecem.
    """

    restaurantes: RestaurantRepository
    unidades: UnitRepository
    usuarios: UserRepository
    sessoes: SessionRepository


@pytest.fixture(params=["fake", "postgres"])
def repos(request: pytest.FixtureRequest) -> Repositorios:
    """Parametriza a suíte inteira sobre as duas implementações.

    O id do parâmetro aparece no nome do teste (`[fake]` / `[postgres]`), então uma
    divergência é lida direto no output: o mesmo teste passa numa implementação e
    falha na outra.
    """
    if request.param == "fake":
        return Repositorios(
            restaurantes=InMemoryRestaurantRepository(),
            unidades=InMemoryUnitRepository(),
            usuarios=InMemoryUserRepository(),
            sessoes=InMemorySessionRepository(),
        )

    # `engine` vem do conftest de integração, que exige Postgres real e falha alto
    # quando ele não está no ar (ADR 2.3.0001) — o contrato herda essa exigência.
    engine: Engine = request.getfixturevalue("engine")
    truncar_tudo(engine)
    return Repositorios(
        restaurantes=PostgresRestaurantRepository(engine),
        unidades=PostgresUnitRepository(engine),
        usuarios=PostgresUserRepository(engine),
        sessoes=PostgresSessionRepository(engine),
    )

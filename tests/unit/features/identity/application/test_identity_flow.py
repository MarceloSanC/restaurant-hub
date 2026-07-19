"""Fluxo ponta-a-ponta de tenancy e acesso — concept CA18.

Esta Stage não tem superfície de runtime (a API é da 2.4), então a verificação
end-to-end possível é esta: os **cinco use cases reais** encadeados sobre uma
única bateria de fakes, exatamente como o composition root vai montá-los.

O que só este teste pega, e nenhum teste unitário pegaria: a **integração entre
os use cases**. Cada um sozinho pode estar correto e ainda assim o conjunto
falhar — se `create_user` gravasse o hash de um jeito que `authenticate_user` não
soubesse verificar, ou se o vínculo criado na criação não fosse o que a
autorização consulta. Aqui nenhum estado é injetado à mão entre etapas: tudo o
que uma etapa usa foi produzido pela anterior.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthenticateUserCommand,
    AuthorizeActionCommand,
    CreateRestaurantCommand,
    CreateUnitCommand,
    CreateUserCommand,
)
from restaurant_hub.features.identity.application.errors import (
    PermissionDeniedError,
    TenantNotVisibleError,
    UnitNotVisibleError,
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
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
_ACCESS_TTL = timedelta(minutes=15)
_REFRESH_TTL = timedelta(days=7)
_SENHA_GERENTE = "s3nha-gerente"


class _Sistema:
    """Bateria única de fakes, compartilhada pelos cinco use cases.

    É o papel que o `composition_root` cumpre na 2.4 — aqui montado à mão para
    que o teste exercite a mesma topologia de dependências.
    """

    def __init__(self) -> None:
        restaurants = InMemoryRestaurantRepository()
        units = InMemoryUnitRepository()
        users = InMemoryUserRepository()
        sessions = InMemorySessionRepository()
        hasher = FakePasswordHasher()
        issuer = FakeTokenIssuer()
        clock = FakeClock(_NOW)
        ids = FakeIdGenerator()

        self.restaurants = restaurants
        self.units = units
        self.users = users
        self.sessions = sessions
        self.hasher = hasher
        self.issuer = issuer
        self.clock = clock

        self.create_restaurant = CreateRestaurantUseCase(restaurants, ids)
        self.create_unit = CreateUnitUseCase(units, restaurants, ids)
        self.create_user = CreateUserUseCase(users, restaurants, units, hasher, ids)
        self.authenticate = AuthenticateUserUseCase(
            users, sessions, hasher, issuer, ids, clock, _ACCESS_TTL, _REFRESH_TTL
        )
        self.authorize = AuthorizeActionUseCase(users, units)


def _montar_restaurante_com_gerente() -> tuple[_Sistema, RestaurantId, UnitId, UnitId, UserId]:
    """Restaurante → duas unidades → gerente vinculado só à primeira."""
    sistema = _Sistema()

    restaurante = sistema.create_restaurant.execute(
        CreateRestaurantCommand(name="Cantina da Esquina")
    )
    tenant = RestaurantId(restaurante.id)

    centro = sistema.create_unit.execute(CreateUnitCommand(restaurant_id=tenant, name="Centro"))
    praia = sistema.create_unit.execute(CreateUnitCommand(restaurant_id=tenant, name="Praia"))

    gerente = sistema.create_user.execute(
        CreateUserCommand(
            email=Email("gerente@cantina.com"),
            plain_password=_SENHA_GERENTE,
            role=Role.MANAGER,
            tenant_id=tenant,
            unit_ids=(UnitId(centro.id),),
        )
    )

    return sistema, tenant, UnitId(centro.id), UnitId(praia.id), UserId(gerente.id)


def test_fluxo_completo_de_tenancy_ate_autorizacao() -> None:
    """CA18 — restaurante → unidade → usuário → autenticação → autorização.

    Nenhum estado é semeado à mão: o tenant sai do primeiro use case, a unidade
    do segundo, a credencial do terceiro, e assim por diante.
    """
    sistema, tenant, centro, _praia, gerente_id = _montar_restaurante_com_gerente()

    # A credencial gravada na criação autentica de fato — prova que `hash` e
    # `verify` casam através do port, e não apenas dentro de cada teste unitário.
    autenticacao = sistema.authenticate.execute(
        AuthenticateUserCommand(email=Email("gerente@cantina.com"), plain_password=_SENHA_GERENTE)
    )
    assert autenticacao.user_id == gerente_id

    # A sessão persistida corresponde ao refresh token devolvido.
    sessao = sistema.sessions.find_by_fingerprint(
        sistema.issuer.fingerprint(autenticacao.refresh_token)
    )
    assert sessao is not None
    assert sessao.is_active(_NOW) is True

    # E o vínculo criado lá atrás é o que a autorização consulta agora.
    ator = sistema.authorize.execute(
        AuthorizeActionCommand(
            actor_id=gerente_id,
            permission=Permission.MANAGE_USERS,
            tenant_id=tenant,
            unit_id=centro,
        )
    )
    assert ator.user_id == gerente_id
    assert ator.scope_unit_id == centro


def test_fluxo_nega_acao_na_unidade_a_que_o_gerente_nao_esta_vinculado() -> None:
    """A variante negativa do mesmo fluxo — o eixo de visibilidade em ação.

    O gerente foi criado vinculado só ao Centro; a Praia pertence ao mesmo
    tenant e ele continua sem enxergá-la.
    """
    sistema, tenant, _centro, praia, gerente_id = _montar_restaurante_com_gerente()

    with pytest.raises(UnitNotVisibleError):
        sistema.authorize.execute(
            AuthorizeActionCommand(
                actor_id=gerente_id,
                permission=Permission.MANAGE_USERS,
                tenant_id=tenant,
                unit_id=praia,
            )
        )


def test_fluxo_com_dono_enxerga_as_duas_unidades_do_tenant() -> None:
    """O mesmo tenant, com um `owner`: bypass de escopo sem vínculo nenhum."""
    sistema, tenant, centro, praia, _gerente = _montar_restaurante_com_gerente()

    dono = sistema.create_user.execute(
        CreateUserCommand(
            email=Email("dono@cantina.com"),
            plain_password="s3nha-dono",
            role=Role.OWNER,
            tenant_id=tenant,
        )
    )

    for unidade in (centro, praia):
        ator = sistema.authorize.execute(
            AuthorizeActionCommand(
                actor_id=UserId(dono.id),
                permission=Permission.MANAGE_TENANT,
                tenant_id=tenant,
                unit_id=unidade,
            )
        )
        assert ator.scope_unit_id == unidade


def test_fluxo_nega_funcionario_por_falta_de_permissao() -> None:
    """`employee` autentica normalmente, mas não é autorizado a nada.

    Separar "quem é você" de "o que você pode" é o ponto dos dois eixos: a
    autenticação bem-sucedida não implica autorização alguma.
    """
    sistema, tenant, centro, _praia, _gerente = _montar_restaurante_com_gerente()

    funcionario = sistema.create_user.execute(
        CreateUserCommand(
            email=Email("funcionario@cantina.com"),
            plain_password="s3nha-func",
            role=Role.EMPLOYEE,
            tenant_id=tenant,
            unit_ids=(centro,),
        )
    )

    autenticacao = sistema.authenticate.execute(
        AuthenticateUserCommand(email=Email("funcionario@cantina.com"), plain_password="s3nha-func")
    )
    assert autenticacao.user_id == funcionario.id

    with pytest.raises(PermissionDeniedError):
        sistema.authorize.execute(
            AuthorizeActionCommand(
                actor_id=UserId(funcionario.id),
                permission=Permission.MANAGE_USERS,
                tenant_id=tenant,
                unit_id=centro,
            )
        )


def test_fluxo_isola_tenants_distintos() -> None:
    """Dois restaurantes no mesmo sistema não se enxergam.

    É o cenário multi-tenant de verdade: o gerente do primeiro restaurante não
    alcança a unidade do segundo, ainda que ambos vivam na mesma instalação.
    """
    sistema, _tenant_a, _centro, _praia, gerente_a = _montar_restaurante_com_gerente()

    outro = sistema.create_restaurant.execute(CreateRestaurantCommand(name="Outro"))
    tenant_b = RestaurantId(outro.id)
    unidade_b = sistema.create_unit.execute(
        CreateUnitCommand(restaurant_id=tenant_b, name="Filial B")
    )

    # Negado no eixo de tenant, antes mesmo de olhar a visibilidade da unidade.
    with pytest.raises(TenantNotVisibleError):
        sistema.authorize.execute(
            AuthorizeActionCommand(
                actor_id=gerente_a,
                permission=Permission.MANAGE_USERS,
                tenant_id=tenant_b,
                unit_id=UnitId(unidade_b.id),
            )
        )

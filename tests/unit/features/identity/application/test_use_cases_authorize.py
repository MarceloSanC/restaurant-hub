"""Os use cases de identity que agem por um ator autorizam o próprio alvo (Stage 2.7).

Concept 2.7 §11. Cada use case afetado tem uma entrada em `CENARIOS`: como montá-lo
sobre fakes semeados — com **espiões** em volta de cada port, para medir "nenhum
efeito" sem depender dos contadores que cada fake tem ou não tem — e um command
válido. Três propriedades, parametrizadas pela tabela:

- **CA03 — negar é não fazer nada.** Com o autorizador que nega, o use case levanta
  a sentinela dele (`is`) e nenhum outro port é chamado. O conjunto espionado é o
  dos parâmetros do construtor, menos o autorizador e os escalares — conferido por
  `inspect.signature`, para que um port novo não fique fora do espião.
- **CA04 — o requisito é exatamente o de R3.** A sequência de pedidos é comparada a
  `_MATRIZ_R3`, uma transcrição literal do concept R3, **independente** de
  `CENARIOS` e do código (o erro clássico da 3.7: tabela e código errando juntos).
- **R4 — o escopo devolvido não é lido.** Com o autorizador que concede e devolve um
  escopo infiel, o result carrega o tenant do command.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
    CreateUnitCommand,
    InviteOwnerCommand,
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_owner import (
    InviteOwnerUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.features.identity.stub_action_authorizers import (
    DenyingActionAuthorizer,
    RecordingActionAuthorizer,
)
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
ATOR = UserId("ator-do-command")
TENANT = RestaurantId("rest-a")
# Os parâmetros de construtor que não são port: não têm o que espionar.
ESCALARES = frozenset({"invitation_ttl", "base_url", "authorizer"})


class Espiao:
    """Envolve um port e registra toda chamada de método, na ordem, num registro comum."""

    def __init__(self, alvo: object, nome: str, registro: list[str]) -> None:
        self._alvo = alvo
        self._nome = nome
        self._registro = registro

    def __getattr__(self, atributo: str) -> object:
        valor = getattr(self._alvo, atributo)
        if not callable(valor):
            return valor

        def chamada(*args: object, **kwargs: object) -> object:
            self._registro.append(f"{self._nome}.{atributo}")
            return valor(*args, **kwargs)

        return chamada


@dataclass
class Montagem:
    """Um use case afetado montado com espiões, e o command que o exercita."""

    use_case: object
    command: object
    chamadas: list[str]
    espionados: frozenset[str]


def montar(
    classe: type,
    command: object,
    ports: dict[str, object],
    autorizador: object,
    escalares: dict[str, object] | None = None,
) -> Montagem:
    """Constrói `classe` com cada port de `ports` envolvido num `Espiao`."""
    chamadas: list[str] = []
    espioes = {nome: Espiao(port, nome, chamadas) for nome, port in ports.items()}
    use_case = classe(**espioes, **(escalares or {}), authorizer=autorizador)
    return Montagem(use_case, command, chamadas, frozenset(espioes))


def _grafo_de_convite() -> dict[str, object]:
    """Fakes semeados para os use cases que convidam: um restaurante, nada mais."""
    users = InMemoryUserRepository()
    restaurants = InMemoryRestaurantRepository()
    tokens = InMemoryPasswordSetupTokenRepository()
    restaurants.add(Restaurant(id=TENANT, name="Cantina A"))
    return {
        "users": users,
        "restaurants": restaurants,
        "units": InMemoryUnitRepository(),
        "hasher": FakePasswordHasher(),
        "tokens": tokens,
        "token_issuer": FakeSetupTokenIssuer(),
        "email_sender": RecordingEmailSender(),
        "id_generator": FakeIdGenerator(),
        "clock": FakeClock(_AGORA),
        "unit_of_work": InMemoryUnitOfWork(users, restaurants, tokens),
    }


_ESCALARES_DE_CONVITE = {
    "invitation_ttl": timedelta(hours=72),
    "base_url": "https://app.exemplo.com",
}


def _invite_owner(autorizador: object) -> Montagem:
    grafo = _grafo_de_convite()
    del grafo["units"]
    return montar(
        InviteOwnerUseCase,
        InviteOwnerCommand(actor_id=ATOR, email=Email("dono-novo@x.com"), tenant_id=TENANT),
        grafo,
        autorizador,
        _ESCALARES_DE_CONVITE,
    )


def _provision_restaurant(autorizador: object) -> Montagem:
    grafo = _grafo_de_convite()
    del grafo["units"]
    return montar(
        ProvisionRestaurantUseCase,
        ProvisionRestaurantCommand(
            actor_id=ATOR, name="Cantina Nova", owner_email=Email("dono-novo@x.com")
        ),
        grafo,
        autorizador,
        _ESCALARES_DE_CONVITE,
    )


def _create_unit(autorizador: object) -> Montagem:
    grafo = _grafo_de_convite()
    return montar(
        CreateUnitUseCase,
        CreateUnitCommand(actor_id=ATOR, restaurant_id=TENANT, name="Filial"),
        {
            "units": grafo["units"],
            "restaurants": grafo["restaurants"],
            "id_generator": grafo["id_generator"],
        },
        autorizador,
    )


# módulo de `use_cases/` → montagem. Cresce por Task; a totalidade contra a pasta
# nasce na Task 06, quando os cinco estão aqui.
CENARIOS: dict[str, Callable[[object], Montagem]] = {
    "invite_owner": _invite_owner,
    "provision_restaurant": _provision_restaurant,
    "create_unit": _create_unit,
}


def _pedido(
    command: object, permissao: Permission, tenant: RestaurantId | None, unidade: object = None
) -> AuthorizeActionCommand:
    return AuthorizeActionCommand(
        actor_id=command.actor_id, permission=permissao, tenant_id=tenant, unit_id=unidade
    )


# Transcrição literal do concept 2.7 R3, campo a campo do command. Não importa
# `required_permissions_for_role` nem `authorize_requirement`: se a regra e o código
# errarem juntos, esta tabela é a terceira voz.
_MATRIZ_R3: dict[str, Callable[[object], list[AuthorizeActionCommand]]] = {
    "invite_owner": lambda c: [_pedido(c, Permission.MANAGE_PLATFORM, c.tenant_id)],
    "provision_restaurant": lambda c: [_pedido(c, Permission.MANAGE_PLATFORM, None)],
    "create_unit": lambda c: [_pedido(c, Permission.MANAGE_TENANT, c.restaurant_id)],
}


def _classe(nome: str) -> type:
    return type(CENARIOS[nome](RecordingActionAuthorizer()).use_case)


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_autorizador_que_nega_impede_todo_efeito(nome: str) -> None:
    """CA03 — a sentinela sobe por identidade e nenhum outro port é tocado."""
    autorizador = DenyingActionAuthorizer()
    montagem = CENARIOS[nome](autorizador)

    with pytest.raises(type(autorizador.denial)) as erro:
        montagem.use_case.execute(montagem.command)

    assert erro.value is autorizador.denial
    assert montagem.chamadas == []
    assert len(autorizador.calls) == 1


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_o_espiao_cobre_todo_port_do_construtor(nome: str) -> None:
    """CA03 — sem isto, um port fora do espião faria "nenhuma chamada" mentir."""
    montagem = CENARIOS[nome](DenyingActionAuthorizer())
    parametros = set(inspect.signature(_classe(nome)).parameters) - ESCALARES

    assert montagem.espionados == parametros


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_o_requisito_e_exatamente_o_de_r3(nome: str) -> None:
    """CA04 — a sequência exata de pedidos, contra a transcrição independente."""
    autorizador = RecordingActionAuthorizer()
    montagem = CENARIOS[nome](autorizador)

    montagem.use_case.execute(montagem.command)

    assert autorizador.calls == _MATRIZ_R3[nome](montagem.command)
    assert all(pedido.actor_id == ATOR for pedido in autorizador.calls)


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_o_use_case_opera_no_command_e_nao_no_escopo_devolvido(nome: str) -> None:
    """R4 — o escopo infiel do autorizador não chega ao result."""
    montagem = CENARIOS[nome](RecordingActionAuthorizer())

    resultado = montagem.use_case.execute(montagem.command)

    tenant_esperado = getattr(montagem.command, "tenant_id", None) or getattr(
        montagem.command, "restaurant_id", None
    )
    tenant_obtido = getattr(resultado, "tenant_id", None) or getattr(
        resultado, "restaurant_id", None
    )
    if tenant_esperado is None:
        # Provisionamento: o tenant nasce no use case — não é o infiel.
        tenant_obtido = resultado.owner.tenant_id
        assert tenant_obtido == resultado.id
    else:
        assert tenant_obtido == tenant_esperado

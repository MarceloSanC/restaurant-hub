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

import ast
import importlib
import inspect
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import get_type_hints

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
    CreateUnitCommand,
    CreateUserCommand,
    InviteOwnerCommand,
    InviteUserCommand,
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.ports.out.action_authorizer import (
    ActionAuthorizer,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_owner import (
    InviteOwnerUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
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
U1 = UnitId("unit-1")
U2 = UnitId("unit-2")
# O cenário discriminante do CA04: unidades fora de ordem e repetidas. Uma
# expansão que iterasse as unidades por fora, as ordenasse ou as deduplicasse
# produziria outra sequência de pedidos.
UNIDADES_PEDIDAS = (U2, U1, U2)
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
    units = InMemoryUnitRepository()
    for unidade in (U1, U2):
        units.add(Unit(id=unidade, restaurant_id=TENANT, name=f"Unidade {unidade}"))
    return {
        "users": users,
        "restaurants": restaurants,
        "units": units,
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


def _create_user(autorizador: object) -> Montagem:
    grafo = _grafo_de_convite()
    return montar(
        CreateUserUseCase,
        CreateUserCommand(
            actor_id=ATOR,
            email=Email("novo-dono@x.com"),
            plain_password="s3nha",
            role=Role.OWNER,
            tenant_id=TENANT,
            unit_ids=UNIDADES_PEDIDAS,
        ),
        {k: grafo[k] for k in ("users", "restaurants", "units", "hasher", "id_generator")},
        autorizador,
    )


def _invite_user(autorizador: object) -> Montagem:
    return montar(
        InviteUserUseCase,
        InviteUserCommand(
            actor_id=ATOR,
            email=Email("convidado@x.com"),
            role=Role.MANAGER,
            tenant_id=TENANT,
            unit_ids=UNIDADES_PEDIDAS,
        ),
        _grafo_de_convite(),
        autorizador,
        _ESCALARES_DE_CONVITE,
    )


# módulo de `use_cases/` → montagem. Cresce por Task; a totalidade contra a pasta
# nasce na Task 06, quando os cinco estão aqui.
CENARIOS: dict[str, Callable[[object], Montagem]] = {
    "invite_owner": _invite_owner,
    "provision_restaurant": _provision_restaurant,
    "create_unit": _create_unit,
    "create_user": _create_user,
    "invite_user": _invite_user,
}


def _pedido(
    command: object, permissao: Permission, tenant: RestaurantId | None, unidade: object = None
) -> AuthorizeActionCommand:
    return AuthorizeActionCommand(
        actor_id=command.actor_id, permission=permissao, tenant_id=tenant, unit_id=unidade
    )


def _composto(command: object) -> list[AuthorizeActionCommand]:
    """R3 de `create_user`/`invite_user`: `{manage_users} | role.permissions`, em
    `sorted`, por fora; as unidades do command, na ordem e sem deduplicar, por dentro."""
    permissoes = sorted({Permission.MANAGE_USERS} | command.role.permissions)
    return [_pedido(command, p, command.tenant_id, u) for p in permissoes for u in command.unit_ids]


# Transcrição literal do concept 2.7 R3, campo a campo do command. Não importa
# `required_permissions_for_role` nem `authorize_requirement`: se a regra e o código
# errarem juntos, esta tabela é a terceira voz.
_MATRIZ_R3: dict[str, Callable[[object], list[AuthorizeActionCommand]]] = {
    "invite_owner": lambda c: [_pedido(c, Permission.MANAGE_PLATFORM, c.tenant_id)],
    "provision_restaurant": lambda c: [_pedido(c, Permission.MANAGE_PLATFORM, None)],
    "create_unit": lambda c: [_pedido(c, Permission.MANAGE_TENANT, c.restaurant_id)],
    "create_user": _composto,
    "invite_user": _composto,
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


# ---------------------------------------------------------------------------
# Totalidade, forma e alcance (Task 06) — derivados da pasta, não de uma lista
# ---------------------------------------------------------------------------

_SRC = pathlib.Path(__file__).resolve().parents[5] / "src" / "restaurant_hub"
_PASTA = _SRC / "features" / "identity" / "application" / "use_cases"

# As exclusões nomeadas do ADR 0.0.0020 §Inventory (concept 2.7 R1). Um módulo novo
# da pasta entra aqui, com o motivo, ou em `CENARIOS` — nunca por omissão.
_EXCLUSOES: dict[str, str] = {
    "authenticate_user": "a senha é a autoridade; ainda não existe ator",
    "refresh_session": "a posse do refresh token é a autoridade",
    "revoke_session": "a posse do refresh token é a autoridade",
    "request_password_reset": "público por desenho, resposta constante",
    "set_password_with_token": "o token de setup é a autoridade",
    "authorize_action": "é a própria decisão",
    "provision_account": "só a fachada o chama; o consumidor autoriza (ADR 3.5.0001 §1)",
    "send_invitation": "só a fachada o chama; o consumidor autoriza (ADR 3.5.0001 §1)",
    "revoke_all_sessions": "só a fachada o chama; o consumidor autoriza (ADR 3.5.0001 §1)",
    "get_account_role": "só a fachada o chama; o consumidor autoriza (ADR 3.5.0001 §1)",
}

# Os módulos facade-only (CA14): o resíduo de `provision_account` (concept 2.7 §13)
# é guardado pelo alcance — só a fachada e o composition root os importam.
_FACADE_ONLY = frozenset(
    {"provision_account", "send_invitation", "revoke_all_sessions", "get_account_role"}
)
_IMPORTADORES_PERMITIDOS = frozenset(
    {
        _SRC / "features" / "identity" / "application" / "facade.py",
        _SRC / "composition_root.py",
    }
)

# A forma de R2/R3, em código-fonte: (permissões, tenant_id, unit_ids ou None).
# `<p>` é o primeiro parâmetro de `execute`. Transcrição do concept, não do código.
_FORMA_R3: dict[str, tuple[str, str, str | None]] = {
    "provision_restaurant": ("frozenset({Permission.MANAGE_PLATFORM})", "None", None),
    "invite_owner": ("frozenset({Permission.MANAGE_PLATFORM})", "<p>.tenant_id", None),
    "create_unit": ("frozenset({Permission.MANAGE_TENANT})", "<p>.restaurant_id", None),
    "create_user": (
        "required_permissions_for_role(<p>.role)",
        "<p>.tenant_id",
        "<p>.unit_ids",
    ),
    "invite_user": (
        "required_permissions_for_role(<p>.role)",
        "<p>.tenant_id",
        "<p>.unit_ids",
    ),
}


def _modulos_da_pasta() -> set[str]:
    return {a.stem for a in _PASTA.glob("*.py") if not a.stem.startswith("_")}


def _execute(modulo: str) -> ast.FunctionDef:
    arvore = ast.parse((_PASTA / f"{modulo}.py").read_text("utf-8"))
    execs = [
        m
        for c in arvore.body
        if isinstance(c, ast.ClassDef) and c.name.endswith("UseCase")
        for m in c.body
        if isinstance(m, ast.FunctionDef) and m.name == "execute"
    ]
    assert len(execs) == 1, modulo
    return execs[0]


def _expr(fonte: str, parametro: str) -> str:
    return ast.dump(ast.parse(fonte.replace("<p>", parametro), mode="eval").body)


def test_a_pasta_e_exatamente_afetados_mais_exclusoes_nomeadas() -> None:
    """CA01 — totalidade nos dois sentidos, e as duas listas disjuntas."""
    assert set(CENARIOS).isdisjoint(_EXCLUSOES)
    assert set(CENARIOS) | set(_EXCLUSOES) == _modulos_da_pasta()
    assert set(_FORMA_R3) == set(CENARIOS) == set(_MATRIZ_R3)
    assert all(motivo.strip() for motivo in _EXCLUSOES.values())


@pytest.mark.parametrize("modulo", sorted(_modulos_da_pasta()))
def test_so_os_afetados_recebem_o_autorizador(modulo: str) -> None:
    """CA01 — `authorizer: ActionAuthorizer` em todo afetado e em nenhuma exclusão."""
    modulo_py = importlib.import_module(
        f"restaurant_hub.features.identity.application.use_cases.{modulo}"
    )
    classes = [
        c
        for c in vars(modulo_py).values()
        if inspect.isclass(c)
        and c.__module__ == modulo_py.__name__
        and c.__name__.endswith("UseCase")
    ]
    assert len(classes) == 1, modulo
    dicas = get_type_hints(classes[0].__init__)

    if modulo in CENARIOS:
        assert dicas.get("authorizer") is ActionAuthorizer
    else:
        assert "authorizer" not in dicas


@pytest.mark.parametrize("modulo", sorted(_FORMA_R3))
def test_a_primeira_instrucao_de_execute_e_a_autorizacao_de_r3(modulo: str) -> None:
    """CA05 — descontado o docstring, a primeira instrução é a chamada de R2 com os
    argumentos de R3; nenhuma condição, leitura ou checagem antes dela."""
    funcao = _execute(modulo)
    p = funcao.args.args[1].arg
    corpo = funcao.body
    if (
        isinstance(corpo[0], ast.Expr)
        and isinstance(corpo[0].value, ast.Constant)
        and isinstance(corpo[0].value.value, str)
    ):
        corpo = corpo[1:]
    primeira = corpo[0]
    permissoes, tenant, unidades = _FORMA_R3[modulo]

    assert isinstance(primeira, ast.Expr), ast.dump(primeira)
    chamada = primeira.value
    assert isinstance(chamada, ast.Call)
    assert isinstance(chamada.func, ast.Name)
    assert chamada.func.id == "authorize_requirement"
    assert [ast.dump(a) for a in chamada.args] == [
        _expr("self._authorizer", p),
        _expr("<p>.actor_id", p),
        _expr(permissoes, p),
    ]
    palavras = {k.arg: ast.dump(k.value) for k in chamada.keywords}
    esperadas = {"tenant_id": _expr(tenant, p)}
    if unidades is not None:
        esperadas["unit_ids"] = _expr(unidades, p)
    assert palavras == esperadas


@pytest.mark.parametrize("modulo", sorted(_FORMA_R3))
def test_nao_ha_outra_autorizacao_no_corpo(modulo: str) -> None:
    """CA05 — uma autorização só, a primeira; nada de `self._authorizer` depois."""
    funcao = _execute(modulo)
    chamadas = [
        n
        for n in ast.walk(funcao)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "authorize_requirement"
    ]
    usos_do_autorizador = [
        n for n in ast.walk(funcao) if isinstance(n, ast.Attribute) and n.attr == "_authorizer"
    ]

    assert len(chamadas) == 1
    assert len(usos_do_autorizador) == 1


def _importa_facade_only(no: ast.ImportFrom, prefixo: str, alvos: set[str]) -> bool:
    """Absoluto (`from <prefixo>.provision_account import …`, `from <prefixo> import
    provision_account`) **ou relativo** (`from .provision_account import …`, `from .
    import provision_account`): um import relativo de irmão passa no lint e não pode
    passar por aqui."""
    nomes = {a.name for a in no.names}
    if no.level == 0:
        return no.module in alvos or (no.module == prefixo and bool(nomes & _FACADE_ONLY))
    ultimo = (no.module or "").split(".")[-1]
    return ultimo in _FACADE_ONLY or (not no.module and bool(nomes & _FACADE_ONLY))


def test_a_varredura_de_alcance_ve_import_relativo() -> None:
    """Controle da varredura do CA14: os dois idiomas de import relativo contam."""
    prefixo = "restaurant_hub.features.identity.application.use_cases"
    alvos = {f"{prefixo}.{nome}" for nome in _FACADE_ONLY}
    for fonte in (
        "from .provision_account import ProvisionAccountUseCase",
        "from . import get_account_role",
        "from ..use_cases.send_invitation import SendInvitationUseCase",
    ):
        no = ast.parse(fonte).body[0]
        assert isinstance(no, ast.ImportFrom)
        assert _importa_facade_only(no, prefixo, alvos), fonte


def test_os_facade_only_so_sao_importados_pela_fachada_e_pelo_composition_root() -> None:
    """CA14 — o resíduo de `ProvisionAccountUseCase` (aceita qualquer papel) fica
    guardado pelo alcance: um terceiro importador reabre a decisão (ADR 0.0.0020)."""
    prefixo = "restaurant_hub.features.identity.application.use_cases"
    alvos = {f"{prefixo}.{nome}" for nome in _FACADE_ONLY}
    importadores: set[pathlib.Path] = set()
    for arquivo in _SRC.rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text("utf-8"))):
            if isinstance(no, ast.ImportFrom) and _importa_facade_only(no, prefixo, alvos):
                importadores.add(arquivo)
            if isinstance(no, ast.Import) and {a.name for a in no.names} & alvos:
                importadores.add(arquivo)

    assert importadores == _IMPORTADORES_PERMITIDOS

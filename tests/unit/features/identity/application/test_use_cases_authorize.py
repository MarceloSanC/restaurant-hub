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
import configparser
import functools
import importlib
import importlib.util
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
    "get_unit_timezone": "só a fachada o chama; o consumidor autoriza (issue #198, ADR 4.1.0005)",
    "find_account_by_email": "só a fachada o chama; o consumidor autoriza (ADR 3.10.0002 §2)",
}

# Os módulos facade-only (CA14): o resíduo de `provision_account` (concept 2.7 §13)
# é guardado pelo alcance — só a fachada e o composition root os importam.
_FACADE_ONLY = frozenset(
    {
        "provision_account",
        "send_invitation",
        "revoke_all_sessions",
        "get_account_role",
        "get_unit_timezone",
        "find_account_by_email",
    }
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


# ---------------------------------------------------------------------------
# Os idiomas indiretos do alcance (issue #233)
# ---------------------------------------------------------------------------

_PACOTE_USE_CASES = "restaurant_hub.features.identity.application.use_cases"
_PAI_DE_USE_CASES = _PACOTE_USE_CASES.rsplit(".", 1)[0]
_IMPORTADORES_DINAMICOS = frozenset({"import_module", "__import__"})
# Piso da varredura: `src/restaurant_hub` tinha 236 módulos em 2026-11-23. Um `_SRC`
# errado ou um `rglob` vazio daria "nenhum importador" sem varrer nada.
_PISO_DE_ARQUIVOS_VARRIDOS = 200


def _pacote_do_arquivo(arquivo: pathlib.Path, raiz: pathlib.Path) -> str:
    """O pacote contra o qual os imports relativos de `arquivo` se resolvem;
    `raiz` é a pasta do pacote de topo (`.../src/restaurant_hub`)."""
    partes = arquivo.relative_to(raiz.parent).with_suffix("").parts
    return ".".join(partes[:-1])


def _resolver(nome: str, pacote: str) -> str:
    """`importlib.util.resolve_name` sem importar nada: `..x` a partir de `a.b.c` é `a.b.x`."""
    nivel = len(nome) - len(nome.lstrip("."))
    if not nivel:
        return nome
    base = pacote.split(".")[: len(pacote.split(".")) - (nivel - 1)]
    resto = nome[nivel:]
    return ".".join([*base, resto] if resto else base)


def _nomeia_facade_only(modulo: str) -> bool:
    """O pacote `use_cases` de identity, ou um módulo facade-only (ou algo dentro dele)."""
    if modulo == _PACOTE_USE_CASES:
        return True
    if not modulo.startswith(f"{_PACOTE_USE_CASES}."):
        return False
    return modulo.removeprefix(f"{_PACOTE_USE_CASES}.").split(".")[0] in _FACADE_ONLY


def _nomes_do_topo(arvore: ast.AST) -> set[str]:
    """Os nomes que um módulo define no topo: classe, função e atribuição a nome."""
    nomes: set[str] = set()
    for no in getattr(arvore, "body", []):
        if isinstance(no, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            nomes.add(no.name)
        elif isinstance(no, ast.Assign | ast.AnnAssign):
            alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
            nomes |= {a.id for a in alvos if isinstance(a, ast.Name)}
    return nomes


@functools.cache
def _simbolos_facade_only() -> frozenset[str]:
    """O que os módulos facade-only definem no topo (`SendInvitationUseCase`,
    `PROVISIONABLE_ROLES`…): quem os nomeia fora dali chegou a eles por algum
    reexport (a fachada, o composition root, um `__init__`)."""
    return frozenset(
        nome
        for modulo in _FACADE_ONLY
        for nome in _nomes_do_topo(ast.parse((_PASTA / f"{modulo}.py").read_text("utf-8")))
        if not nome.startswith("__")
    )


def _literal(no: ast.expr | None) -> str | None:
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    return None


def _argumento(chamada: ast.Call, posicao: int, nome: str) -> ast.expr | None:
    if len(chamada.args) > posicao:
        return chamada.args[posicao]
    return next((k.value for k in chamada.keywords if k.arg == nome), None)


def _import_dinamico_alcanca(chamada: ast.Call) -> bool:
    """`importlib.import_module(nome, package)` e `__import__(nome, g, l, fromlist, level)`.

    Fail-closed no que não se decide estaticamente: nome não literal, `package` não
    literal num nome relativo, `level` diferente do literal 0, `fromlist` não literal
    sobre o pai de `use_cases` — tudo isso reprova. Não havia nenhuma chamada dessas em
    `src/` quando a regra nasceu (2026-11-23), então ela não acusa código legítimo; a
    primeira que aparecer vem para a lista de permitidos com motivo, ou muda de forma."""
    nome = _literal(_argumento(chamada, 0, "name"))
    if nome is None:
        return True
    funcao = chamada.func
    chamada_de = funcao.id if isinstance(funcao, ast.Name) else getattr(funcao, "attr", "")
    if chamada_de == "import_module":
        if not nome.startswith("."):
            return _nomeia_facade_only(nome)
        base = _literal(_argumento(chamada, 1, "package"))
        return base is None or _nomeia_facade_only(_resolver(nome, base))
    return _dunder_import_alcanca(chamada, nome)


def _dunder_import_alcanca(chamada: ast.Call, nome: str) -> bool:
    """O ramo `__import__` de `_import_dinamico_alcanca`, com `nome` já literal."""
    nivel = _argumento(chamada, 4, "level")
    if nivel is not None and not (isinstance(nivel, ast.Constant) and nivel.value == 0):
        return True
    if _nomeia_facade_only(nome):
        return True
    lista = _argumento(chamada, 3, "fromlist")
    if lista is None or nome != _PAI_DE_USE_CASES:
        return False
    if not isinstance(lista, ast.List | ast.Tuple):
        return True
    itens = [_literal(e) for e in lista.elts]
    return None in itens or "use_cases" in itens


def _achados_do_from(no: ast.ImportFrom, pacote: str, simbolos: frozenset[str]) -> list[str]:
    """O ramo `from … import …` de `_alcance_indireto`, com o relativo resolvido."""
    modulo = _resolver("." * no.level + (no.module or ""), pacote)
    achados: list[str] = []
    for a in no.names:
        if a.name == "*" and _nomeia_facade_only(modulo):
            achados.append(f"from {modulo} import *")
        if a.name == "use_cases" and f"{modulo}.use_cases" == _PACOTE_USE_CASES:
            achados.append(f"from {modulo} import use_cases")
        if a.name in _IMPORTADORES_DINAMICOS and a.asname not in (None, a.name):
            achados.append(f"{a.name} como {a.asname}")
        if modulo == _PACOTE_USE_CASES and a.name in _FACADE_ONLY:
            achados.append(f"from {modulo} import {a.name}")
        if a.name in simbolos:
            achados.append(f"from {modulo} import {a.name} (símbolo facade-only)")
    return achados


def _alcance_indireto(arvore: ast.AST, pacote: str) -> list[str]:
    """Os idiomas que `_importa_facade_only` não vê, cada achado descrito numa linha.

    Reprova: (a) `import_module`/`__import__` que nomeie um facade-only ou o pacote
    `use_cases` (e o indecidível, fail-closed — ver `_import_dinamico_alcanca`), e
    `import_module`/`__import__` referidos sem ser chamados (alias, passagem como
    valor), que esconderiam a chamada da regra; (b) o pacote `use_cases` de identity
    ligado como módulo — `import <pacote>`, `from <pai> import use_cases`, o relativo
    resolvido pelo caminho do arquivo e `from <pacote> import *`; e o acesso por
    atributo `use_cases.<facade_only>` (o que o pacote ligado, ou `import
    restaurant_hub…` encadeado, permitiria). Também (auditoria do PR #240): o import
    relativo resolvido que chega a um facade-only (`from ..use_cases import
    send_invitation`, que `_importa_facade_only` não resolve); qualquer literal de
    texto que nomeie um facade-only, também na forma `pacote:atributo` (`pydoc.locate`,
    `pkgutil.resolve_name("…:Classe")`, `sys.modules["…"]`); e o símbolo definido
    num facade-only (`SendInvitationUseCase`) nomeado fora do próprio módulo — importado
    ou acessado pela fachada, pelo composition root ou por um `__init__` que o reexporte.

    Não alcança um facade-only, e passa: importar o pai para outro irmão (`from <pai>
    import dtos`), um use case comum (`from <pacote> import create_user`), o `use_cases`
    de outra feature por relativo, um atributo homônimo fora de `use_cases`
    (`self._facade.provision_account`) e um nome homônimo definido no próprio arquivo.

    Limite declarado — fica de fora, porque não há forma estática sem falso positivo
    no código atual: nome calculado em `getattr`/`vars()`/`__dict__` (há `getattr`
    legítimo em `src/`), `sys.modules[...]` com chave calculada, `importlib.util`/
    `runpy`/`pkgutil` com nome não literal, `exec`/`eval` de fonte, e o pacote
    `use_cases` religado a outro nome por atribuição (`uc = application.use_cases`) e
    lido como `uc.send_invitation` sem chegar a um símbolo. A varredura guarda os
    idiomas de import, não a execução."""
    achados: list[str] = []
    chamadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)]
    funcoes_chamadas = {id(c.func) for c in chamadas}
    simbolos = _simbolos_facade_only() - _nomes_do_topo(arvore)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            achados += [f"import {a.name}" for a in no.names if a.name == _PACOTE_USE_CASES]
        elif isinstance(no, ast.ImportFrom):
            achados += _achados_do_from(no, pacote, simbolos)
        elif isinstance(no, ast.Constant):
            # `pkgutil.resolve_name` aceita `pacote:atributo`; o pacote sozinho não basta.
            texto = no.value.replace(":", ".") if isinstance(no.value, str) else ""
            if texto != _PACOTE_USE_CASES and _nomeia_facade_only(texto):
                achados.append(f"literal {texto!r} na linha {no.lineno}")
        elif isinstance(no, ast.Call):
            funcao = no.func
            nome = funcao.id if isinstance(funcao, ast.Name) else getattr(funcao, "attr", None)
            if nome in _IMPORTADORES_DINAMICOS and _import_dinamico_alcanca(no):
                achados.append(f"{nome}(...) na linha {no.lineno}")
        elif isinstance(no, ast.Name | ast.Attribute):
            nome = no.id if isinstance(no, ast.Name) else no.attr
            if nome in _IMPORTADORES_DINAMICOS and id(no) not in funcoes_chamadas:
                achados.append(f"{nome} sem chamada na linha {no.lineno}")
            dono = getattr(no, "value", None)
            dono_nome = dono.id if isinstance(dono, ast.Name) else getattr(dono, "attr", None)
            if nome in _FACADE_ONLY and isinstance(no, ast.Attribute) and dono_nome == "use_cases":
                achados.append(f"use_cases.{nome} na linha {no.lineno}")
            if nome in simbolos:
                achados.append(f"símbolo facade-only {nome} na linha {no.lineno}")
    return achados


def _alcanca_facade_only(fonte: str, pacote: str) -> bool:
    """Um módulo de código-fonte `fonte`, no pacote `pacote`, alcança um facade-only?"""
    prefixo = _PACOTE_USE_CASES
    alvos = {f"{prefixo}.{nome}" for nome in _FACADE_ONLY}
    arvore = ast.parse(fonte)
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and _importa_facade_only(no, prefixo, alvos):
            return True
        if isinstance(no, ast.Import) and {a.name for a in no.names} & alvos:
            return True
    return bool(_alcance_indireto(arvore, pacote))


def _importadores(raiz: pathlib.Path) -> tuple[set[pathlib.Path], int]:
    """Os arquivos sob `raiz` que alcançam um facade-only, e quantos foram varridos."""
    arquivos = sorted(raiz.rglob("*.py"))
    importadores = {
        arquivo
        for arquivo in arquivos
        if _alcanca_facade_only(arquivo.read_text("utf-8"), _pacote_do_arquivo(arquivo, raiz))
    }
    return importadores, len(arquivos)


# Cada idioma de #233, plantado num módulo fora da fachada; o pacote é o do arquivo.
_PACOTE_INTRUSO = "restaurant_hub.features.staff.adapters.out.identity"
_IDIOMAS_INDIRETOS: dict[str, tuple[str, str]] = {
    "import_module literal": (
        f'import importlib\nm = importlib.import_module("{_PACOTE_USE_CASES}.send_invitation")',
        _PACOTE_INTRUSO,
    ),
    "import_module importado do importlib": (
        "from importlib import import_module\n"
        f'm = import_module("{_PACOTE_USE_CASES}.revoke_all_sessions")',
        _PACOTE_INTRUSO,
    ),
    "import_module do pacote use_cases": (
        f'import importlib\nuc = importlib.import_module("{_PACOTE_USE_CASES}")',
        _PACOTE_INTRUSO,
    ),
    "import_module relativo com package literal": (
        "import importlib\n"
        f'm = importlib.import_module(".get_account_role", "{_PACOTE_USE_CASES}")',
        _PACOTE_INTRUSO,
    ),
    "import_module com nome não literal": (
        'import importlib\nnome = "x"\nm = importlib.import_module(nome)',
        _PACOTE_INTRUSO,
    ),
    "import_module relativo com package não literal": (
        'import importlib\nm = importlib.import_module(".send_invitation", __package__)',
        _PACOTE_INTRUSO,
    ),
    "import_module passado como valor": (
        "import importlib\ncarregar = importlib.import_module",
        _PACOTE_INTRUSO,
    ),
    "import_module com alias": (
        "from importlib import import_module as carregar",
        _PACOTE_INTRUSO,
    ),
    "__import__ literal": (
        f'm = __import__("{_PACOTE_USE_CASES}.provision_account")',
        _PACOTE_INTRUSO,
    ),
    "__import__ com fromlist use_cases": (
        f'm = __import__("{_PAI_DE_USE_CASES}", fromlist=["use_cases"])',
        _PACOTE_INTRUSO,
    ),
    "__import__ com fromlist não literal": (
        f'nomes = ["use_cases"]\nm = __import__("{_PAI_DE_USE_CASES}", fromlist=nomes)',
        _PACOTE_INTRUSO,
    ),
    "__import__ relativo": (
        'm = __import__("use_cases", globals(), None, ["send_invitation"], 1)',
        _PACOTE_INTRUSO,
    ),
    "__import__ com nome não literal": ('nome = "x"\nm = __import__(nome)', _PACOTE_INTRUSO),
    "__import__ com item não literal no fromlist": (
        f'n = "use_cases"\nm = __import__("{_PAI_DE_USE_CASES}", fromlist=[n])',
        _PACOTE_INTRUSO,
    ),
    "import_module de algo dentro de um facade-only": (
        "import importlib\n"
        f'm = importlib.import_module("{_PACOTE_USE_CASES}.send_invitation.interno")',
        _PACOTE_INTRUSO,
    ),
    "from pai import use_cases": (f"from {_PAI_DE_USE_CASES} import use_cases", _PACOTE_INTRUSO),
    "from pai import use_cases com alias": (
        f"from {_PAI_DE_USE_CASES} import use_cases as uc",
        _PACOTE_INTRUSO,
    ),
    "import pacote use_cases": (f"import {_PACOTE_USE_CASES}", _PACOTE_INTRUSO),
    "import pacote use_cases com alias": (f"import {_PACOTE_USE_CASES} as uc", _PACOTE_INTRUSO),
    "relativo from .. import use_cases": (
        "from .. import use_cases",
        f"{_PAI_DE_USE_CASES}.ports",
    ),
    "relativo from . import use_cases": ("from . import use_cases", _PAI_DE_USE_CASES),
    "from use_cases import *": (f"from {_PACOTE_USE_CASES} import *", _PACOTE_INTRUSO),
    "atributo encadeado a partir do pacote de topo": (
        f"import {_PACOTE_USE_CASES}.create_user\n"
        f"x = {_PACOTE_USE_CASES}.send_invitation.SendInvitationUseCase",
        _PACOTE_INTRUSO,
    ),
    "atributo use_cases.<facade_only> isolado": (
        "def f(use_cases):\n    return use_cases.get_account_role",
        _PACOTE_INTRUSO,
    ),
    # Auditoria do PR #240: idiomas que escapavam da primeira versão.
    "relativo from ..use_cases import <facade_only>": (
        "from ..use_cases import send_invitation",
        f"{_PAI_DE_USE_CASES}.ports",
    ),
    "relativo pelo pai com o nome do pacote": (
        "from ...application.use_cases import get_account_role",
        f"{_PAI_DE_USE_CASES}.ports",
    ),
    "literal em pydoc.locate": (
        f'import pydoc\nc = pydoc.locate("{_PACOTE_USE_CASES}.send_invitation.Classe")',
        _PACOTE_INTRUSO,
    ),
    "literal em pkgutil.resolve_name": (
        f'import pkgutil\nc = pkgutil.resolve_name("{_PACOTE_USE_CASES}.send_invitation:X")',
        _PACOTE_INTRUSO,
    ),
    "literal pacote:módulo em pkgutil.resolve_name": (
        f'import pkgutil\nm = pkgutil.resolve_name("{_PACOTE_USE_CASES}:get_unit_timezone")',
        _PACOTE_INTRUSO,
    ),
    "literal em sys.modules": (
        f'import sys\nm = sys.modules["{_PACOTE_USE_CASES}.revoke_all_sessions"]',
        _PACOTE_INTRUSO,
    ),
    "símbolo reexportado pela fachada": (
        f"from {_PAI_DE_USE_CASES}.facade import SendInvitationUseCase",
        _PACOTE_INTRUSO,
    ),
    "símbolo reexportado com alias": (
        "from restaurant_hub.composition_root import RevokeAllSessionsUseCase as R",
        _PACOTE_INTRUSO,
    ),
    "símbolo por atributo da fachada": (
        f"from {_PAI_DE_USE_CASES} import facade\nc = facade.GetAccountRoleUseCase",
        _PACOTE_INTRUSO,
    ),
    "símbolo por import estrela da fachada": (
        f"from {_PAI_DE_USE_CASES}.facade import *\nc = ProvisionAccountUseCase",
        _PACOTE_INTRUSO,
    ),
    "constante facade-only por atributo": (
        f"from {_PAI_DE_USE_CASES} import facade\npapeis = facade.PROVISIONABLE_ROLES",
        _PACOTE_INTRUSO,
    ),
    "símbolo pelo pacote religado a outro nome": (
        f"import {_PACOTE_USE_CASES}.create_user\n"
        f"uc = {_PACOTE_USE_CASES}\nc = uc.send_invitation.SendInvitationUseCase",
        _PACOTE_INTRUSO,
    ),
}

# Imports do pai ou do pacote `use_cases` que não chegam a um facade-only: passam.
_NAO_ALCANCAM: dict[str, tuple[str, str]] = {
    "irmão de use_cases pelo pai": (f"from {_PAI_DE_USE_CASES} import dtos", _PACOTE_INTRUSO),
    "use case comum pelo pacote": (
        f"from {_PACOTE_USE_CASES} import create_user",
        _PACOTE_INTRUSO,
    ),
    "use case comum por import absoluto": (
        f"import {_PACOTE_USE_CASES}.create_user",
        _PACOTE_INTRUSO,
    ),
    "import_module literal de use case comum": (
        f'import importlib\nm = importlib.import_module("{_PACOTE_USE_CASES}.create_user")',
        _PACOTE_INTRUSO,
    ),
    "__import__ do pai sem fromlist": (f'm = __import__("{_PAI_DE_USE_CASES}")', _PACOTE_INTRUSO),
    "__import__ com fromlist use_cases de outra feature": (
        'm = __import__("restaurant_hub.features.staff.application", fromlist=["use_cases"])',
        _PACOTE_INTRUSO,
    ),
    "__import__ do pai com fromlist de irmão": (
        f'm = __import__("{_PAI_DE_USE_CASES}", fromlist=["dtos"], level=0)',
        _PACOTE_INTRUSO,
    ),
    "use_cases de outra feature por relativo": (
        "from .. import use_cases",
        "restaurant_hub.features.staff.application.ports",
    ),
    "atributo homônimo fora de use_cases": (
        "def f(self):\n    return self._facade.provision_account",
        _PACOTE_INTRUSO,
    ),
    "use case comum por relativo": (
        "from ..use_cases import create_user",
        f"{_PAI_DE_USE_CASES}.ports",
    ),
    "literal de use case comum": (f'n = "{_PACOTE_USE_CASES}.create_user"', _PACOTE_INTRUSO),
    "nome homônimo definido no próprio arquivo": (
        "class SendInvitationUseCase:\n    pass\n\nx = SendInvitationUseCase",
        _PACOTE_INTRUSO,
    ),
    "constante homônima definida no próprio arquivo": (
        "PROVISIONABLE_ROLES: frozenset[str] = frozenset()\nx = PROVISIONABLE_ROLES",
        _PACOTE_INTRUSO,
    ),
    "import_module relativo com package literal de use case comum": (
        f'import importlib\nm = importlib.import_module(".create_user", "{_PACOTE_USE_CASES}")',
        _PACOTE_INTRUSO,
    ),
}


@pytest.mark.parametrize("idioma", sorted(_IDIOMAS_INDIRETOS))
def test_a_varredura_de_alcance_ve_cada_idioma_indireto(idioma: str) -> None:
    """Controle do CA14 (issue #233): import por string e pelo pacote pai contam."""
    fonte, pacote = _IDIOMAS_INDIRETOS[idioma]

    assert _alcanca_facade_only(fonte, pacote), fonte


@pytest.mark.parametrize("caso", sorted(_NAO_ALCANCAM))
def test_a_varredura_de_alcance_nao_acusa_o_que_nao_alcanca(caso: str) -> None:
    """O contrário do controle: o pai e o pacote, sem chegar a um facade-only, passam."""
    fonte, pacote = _NAO_ALCANCAM[caso]

    assert not _alcanca_facade_only(fonte, pacote), fonte


@pytest.mark.parametrize(
    ("nome", "pacote", "esperado"),
    [
        ("x", "a.b.c", "x"),
        (".x", "a.b.c", "a.b.c.x"),
        ("..x", "a.b.c", "a.b.x"),
        ("..", "a.b.c", "a.b"),
        ("...x.y", "a.b.c", "a.x.y"),
    ],
)
def test_a_resolucao_relativa_e_a_do_importlib(nome: str, pacote: str, esperado: str) -> None:
    """A resolução local, comparada à do `importlib`, que é a regra do interpretador."""
    assert _resolver(nome, pacote) == esperado == importlib.util.resolve_name(nome, pacote)


def test_a_varredura_resolve_o_relativo_pelo_caminho_do_arquivo(tmp_path: pathlib.Path) -> None:
    """Uma árvore plantada: o mesmo `from .. import use_cases` reprova em identity (num
    módulo e num `__init__.py`, que resolve contra o próprio pacote) e passa em staff; a
    fachada e o composition root contam como importadores, como no CA14."""
    raiz = tmp_path / "restaurant_hub"
    plantados = {
        "features/identity/application/facade.py": f"from {_PACOTE_USE_CASES} import *",
        "composition_root.py": f"import {_PACOTE_USE_CASES}",
        "features/identity/application/ports/intruso.py": "from .. import use_cases",
        "features/identity/application/ports/__init__.py": "from .. import use_cases",
        "features/staff/application/ports/vizinho.py": "from .. import use_cases",
        "features/staff/application/ports/__init__.py": "from .. import dtos",
    }
    for caminho, fonte in plantados.items():
        (raiz / caminho).parent.mkdir(parents=True, exist_ok=True)
        (raiz / caminho).write_text(fonte, "utf-8")

    importadores, varridos = _importadores(raiz)

    assert varridos == len(plantados)
    assert importadores == {
        raiz / "features/identity/application/facade.py",
        raiz / "composition_root.py",
        raiz / "features/identity/application/ports/intruso.py",
        raiz / "features/identity/application/ports/__init__.py",
    }


def test_os_facade_only_so_sao_importados_pela_fachada_e_pelo_composition_root() -> None:
    """CA14 — os facade-only não autorizam, então um terceiro importador reabre a
    decisão (ADR 0.0.0020). Desde a issue #211 o papel de `ProvisionAccountUseCase`
    não depende mais deste alcance: o use case recusa sozinho todo papel fora de
    `PROVISIONABLE_ROLES` (`test_provision_account.py` › `TestPapelProvisionavel`).

    Desde a issue #233 a varredura vê, além dos imports diretos (`_importa_facade_only`),
    o import por string e pelo pacote pai (`_alcance_indireto`, onde está também o
    limite declarado: o que só se decide em execução fica de fora). O piso de arquivos
    impede que uma varredura vazia passe."""
    importadores, varridos = _importadores(_SRC)

    assert varridos >= _PISO_DE_ARQUIVOS_VARRIDOS
    assert importadores == _IMPORTADORES_PERMITIDOS


_IMPORTLINTER = _SRC.parents[1] / ".importlinter"
_SECAO_FACADE_ONLY = "importlinter:contract:identity-facade-only-reach"


def _lista_do_contrato(contrato: configparser.SectionProxy, opcao: str) -> set[str]:
    """Uma opção multilinha do `.importlinter`, como conjunto de nomes de módulo."""
    return {linha.strip() for linha in contrato.get(opcao, "").splitlines() if linha.strip()}


def test_a_lista_do_contrato_facade_only_e_a_do_ca14() -> None:
    """Issue #246 — o contrato `identity-facade-only-reach` do `.importlinter` repete o
    CA14 no `lint-imports`. As duas listas (módulos protegidos e importadores
    permitidos) têm de ser as deste arquivo: um use case facade-only novo que entrasse
    só em `_FACADE_ONLY` deixaria o contrato protegendo menos do que o CA14, sem
    ninguém notar. A seção é lida como configuração, não como texto."""
    parser = configparser.ConfigParser()
    parser.read(_IMPORTLINTER, encoding="utf-8")
    assert parser.has_section(_SECAO_FACADE_ONLY), (
        f"o contrato {_SECAO_FACADE_ONLY!r} sumiu do .importlinter"
    )
    contrato = parser[_SECAO_FACADE_ONLY]
    importadores = {
        ".".join(caminho.relative_to(_SRC.parent).with_suffix("").parts)
        for caminho in _IMPORTADORES_PERMITIDOS
    }

    assert contrato["type"] == "protected"
    assert _lista_do_contrato(contrato, "protected_modules") == {
        f"{_PACOTE_USE_CASES}.{nome}" for nome in _FACADE_ONLY
    }
    assert _lista_do_contrato(contrato, "allowed_importers") == importadores


def test_a_regra_de_composicao_e_definida_num_so_modulo_de_src() -> None:
    """CA09 — `required_permissions_for_role` tem **uma** definição em `src/`, no
    módulo do port. Uma cópia local (na borda, num use case) passaria no teste que
    só olha `dependencies.py`, e a borda e a application exigiriam coisas diferentes."""
    definidores = {
        arquivo
        for arquivo in _SRC.rglob("*.py")
        for no in ast.walk(ast.parse(arquivo.read_text("utf-8")))
        if isinstance(no, ast.FunctionDef) and no.name == "required_permissions_for_role"
    }

    assert definidores == {
        _SRC / "features" / "identity" / "application" / "ports" / "out" / "action_authorizer.py"
    }

"""A application de scheduling nega sozinha — propriedade sobre a pasta `use_cases/` (CA03).

ADR 4.3.0002 (o padrão do ADR 3.7.0001 reaplicado). Trava a propriedade **por use case e
não por representante**:

- **pasta == tabela**: use case novo entra na tabela ou reprova aqui;
- **guard que nega** ⇒ a sentinela sobe crua (`is`) e nada acontece: nenhuma chamada a
  port de dados, nenhuma leitura do relógio, nenhum id gerado;
- **guard permissivo** ⇒ exatamente um `authorize`, com (permissão, tenant, unidade) do
  command;
- **guard adversarial** (escopo com tenant e unidade inventados) ⇒ leitura e efeito
  caem no endereço do **command** — o escopo não é endereço (ADR 3.7.0001 §3);
- **forma (AST)**: descontado o docstring, a 1ª instrução de `execute` é a chamada
  canônica ao guard, com a permissão como constante do port; `Assign` a `scope` só nos
  três use cases que leem o sujeito, e `scope` só é lido como `.user_id`;
- **retorno**: nenhum `execute` devolve entidade do domínio (LAYOUT §7).
"""

import ast
import dataclasses
import importlib
import inspect
import pkgutil
import typing
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Final
from uuid import UUID

import pytest

from restaurant_hub.features.scheduling.application import use_cases as pacote
from restaurant_hub.features.scheduling.application.dtos.commands import (
    ChangeDemandQuantity,
    CreateScheduleCommand,
    PublishScheduleCommand,
)
from restaurant_hub.features.scheduling.application.dtos.queries import (
    EvaluateScheduleQuery,
    GetCalendarQuery,
    GetMyScheduleQuery,
    GetScheduleQuery,
    ListPastSchedulesQuery,
)
from restaurant_hub.features.scheduling.application.ports.out import access_guard
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.scheduling.application.use_cases.create_schedule import (
    CreateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.evaluate_schedule import (
    EvaluateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_calendar import (
    GetCalendarUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_my_schedule import (
    GetMyScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_schedule import (
    GetScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.list_past_schedules import (
    ListPastSchedulesUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.publish_schedule import (
    PublishScheduleUseCase,
)
from restaurant_hub.features.scheduling.domain.entities import (
    assignment,
    shift_band,
    shift_demand,
)
from restaurant_hub.features.scheduling.domain.entities import (
    schedule as schedule_module,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    T1,
    U1,
    World,
    at,
    blank_change,
    new_world,
    schedule,
)

pytestmark = pytest.mark.unit

_ULTIMO = MONDAY + timedelta(days=6)


@dataclass(frozen=True)
class Cenario:
    """Como montar e chamar um use case da pasta."""

    classe: type
    pedido: Callable[[object], object]  # ator → command/query
    permissao: str
    le_o_sujeito: bool
    confere: Callable[[World, object], None]  # o efeito/leitura caiu no endereço do command


def _resumo_em_t1(world: World, resultado: object) -> None:
    assert getattr(getattr(resultado, "summary", resultado), "tenant_id", None) == T1


def _criada_em_t1(world: World, resultado: object) -> None:
    sid = getattr(resultado, "schedule_id", None)
    assert world.schedules.find_by_id(T1, U1, ScheduleId(str(sid))) is not None


def _avaliou_s1(world: World, resultado: object) -> None:
    assert getattr(resultado, "schedule").summary.schedule_id == "s1"  # noqa: B009


def _calendario_com_s1(world: World, resultado: object) -> None:
    assert [s.schedule_id for s in getattr(resultado, "schedules")] == ["s1"]  # noqa: B009


def _anteriores_com_s0(world: World, resultado: object) -> None:
    assert [s.schedule_id for s in resultado] == ["s0"]  # type: ignore[attr-defined]


def _turnos_da_ana(world: World, resultado: object) -> None:
    assert [t.assignment_id for t in getattr(resultado, "shifts")] == ["a-ana"]  # noqa: B009


_LOTE = (ChangeDemandQuantity(ShiftDemandId("d1"), DemandQuantity(2)),)

CENARIOS: Final[dict[str, Cenario]] = {
    "create_schedule": Cenario(
        CreateScheduleUseCase,
        lambda a: CreateScheduleCommand(a, T1, U1, MONDAY + timedelta(days=14)),
        PERMISSION_MANAGE_SCHEDULE,
        le_o_sujeito=True,
        confere=_criada_em_t1,
    ),
    "evaluate_schedule": Cenario(
        EvaluateScheduleUseCase,
        lambda a: EvaluateScheduleQuery(a, T1, U1, ScheduleId("s1"), 1, _LOTE),
        PERMISSION_MANAGE_SCHEDULE,
        le_o_sujeito=False,
        confere=_avaliou_s1,
    ),
    "publish_schedule": Cenario(
        PublishScheduleUseCase,
        lambda a: PublishScheduleCommand(a, T1, U1, ScheduleId("s1"), 1, _LOTE),
        PERMISSION_MANAGE_SCHEDULE,
        le_o_sujeito=True,
        confere=_resumo_em_t1,
    ),
    "get_schedule": Cenario(
        GetScheduleUseCase,
        lambda a: GetScheduleQuery(a, T1, U1, ScheduleId("s1")),
        PERMISSION_VIEW_SCHEDULE,
        le_o_sujeito=False,
        confere=_resumo_em_t1,
    ),
    "get_calendar": Cenario(
        GetCalendarUseCase,
        lambda a: GetCalendarQuery(a, T1, U1, MONDAY, _ULTIMO),
        PERMISSION_VIEW_SCHEDULE,
        le_o_sujeito=False,
        confere=_calendario_com_s1,
    ),
    "list_past_schedules": Cenario(
        ListPastSchedulesUseCase,
        lambda a: ListPastSchedulesQuery(a, T1, U1, MONDAY, 5),
        PERMISSION_VIEW_SCHEDULE,
        le_o_sujeito=False,
        confere=_anteriores_com_s0,
    ),
    "get_my_schedule": Cenario(
        GetMyScheduleUseCase,
        lambda a: GetMyScheduleQuery(a, T1, U1, MONDAY, _ULTIMO),
        PERMISSION_VIEW_OWN_SCHEDULE,
        le_o_sujeito=True,
        confere=_turnos_da_ana,
    ),
}


def _semeado() -> World:
    """s0 (semana anterior, vazia) e s1 (Ana em d1, N=1) em (t1, u1)."""
    world = new_world()
    world.schedules.add(schedule("s0", MONDAY - timedelta(days=7)), blank_change())
    s1 = (
        schedule("s1")
        .enable_band(ShiftBandId("f1"), TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 14)))
        .declare_demand(ShiftDemandId("d1"), ShiftBandId("f1"), COOK, DemandQuantity(1))
        .assign(AssignmentId("a-ana"), ShiftDemandId("d1"), EmployeeId("ana"))
    )
    world.schedules.add(dataclasses.replace(s1, version=1), blank_change())
    world.schedules.calls.clear()
    return world


def _montar(classe: type, world: World, guard: object) -> object:
    fakes: dict[str, object] = {
        "schedules": world.schedules,
        "config": world.config,
        "staff": world.staff,
        "ids": world.ids,
        "clock": world.clock,
        "guard": guard,
    }
    parametros = list(inspect.signature(classe).parameters)
    return classe(**{nome: fakes[nome] for nome in parametros})


def _modulos_da_pasta() -> list[str]:
    return sorted(
        m.name for m in pkgutil.iter_modules(pacote.__path__) if not m.name.startswith("_")
    )


def _classe_do_modulo(nome: str) -> type:
    modulo = importlib.import_module(f"{pacote.__name__}.{nome}")
    [classe] = [
        obj
        for _, obj in inspect.getmembers(modulo, inspect.isclass)
        if obj.__module__ == modulo.__name__ and obj.__name__.endswith("UseCase")
    ]
    return classe


def test_a_tabela_cobre_a_pasta_use_cases_inteira() -> None:
    assert sorted(CENARIOS) == _modulos_da_pasta()
    assert all(CENARIOS[n].classe is _classe_do_modulo(n) for n in CENARIOS)


@pytest.mark.parametrize("nome", _modulos_da_pasta())
def test_todo_use_case_recebe_o_guard_pelo_port(nome: str) -> None:
    assert typing.get_type_hints(_classe_do_modulo(nome).__init__).get("guard") is AccessGuard


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_ca03_guard_que_nega_nao_produz_efeito_nenhum(nome: str) -> None:
    world = _semeado()
    cenario = CENARIOS[nome]
    estranho = world.guard.issue("user-x", "t9")
    use_case = _montar(cenario.classe, world, world.guard)
    with pytest.raises(Exception) as excinfo:
        use_case.execute(cenario.pedido(estranho))  # type: ignore[attr-defined]
    assert excinfo.value is world.guard.authorization_error
    assert world.port_calls() == []
    assert world.clock.reads == 0
    assert world.ids.next_id() == UUID(int=1)


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_ca03_guard_permissivo_recebe_exatamente_o_alvo_do_command(nome: str) -> None:
    world = _semeado()
    cenario = CENARIOS[nome]
    ator = world.employee if cenario.permissao == PERMISSION_VIEW_OWN_SCHEDULE else world.manager
    use_case = _montar(cenario.classe, world, world.guard)
    use_case.execute(cenario.pedido(ator))  # type: ignore[attr-defined]
    assert world.guard.calls == [f"authorize({cenario.permissao},{T1},{U1})"]


@dataclass
class _GuardAdversarial:
    """Concede tudo e devolve um escopo com tenant e unidade **inventados**."""

    def authorize(
        self, actor: object, permission: str, *, tenant_id: str, unit_id: str
    ) -> AuthorizedScope:
        return AuthorizedScope(
            tenant_id=TenantId("t-inventado"), unit_id=UnitId("u-inventada"), user_id="user-ana"
        )


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_o_escopo_nao_e_endereco_o_efeito_cai_no_command(nome: str) -> None:
    world = _semeado()
    cenario = CENARIOS[nome]
    use_case = _montar(cenario.classe, world, _GuardAdversarial())
    resultado = use_case.execute(cenario.pedido(world.manager))  # type: ignore[attr-defined]
    cenario.confere(world, resultado)


# --- forma (AST) ---------------------------------------------------------------------------

_NOME_DA_PERMISSAO: Final = {
    getattr(access_guard, n): n for n in dir(access_guard) if n.startswith("PERMISSION_")
}


def _execute(nome: str) -> ast.FunctionDef:
    modulo = importlib.import_module(f"{pacote.__name__}.{nome}")
    arvore = ast.parse(inspect.getsource(modulo))
    [classe] = [n for n in arvore.body if isinstance(n, ast.ClassDef)]
    [execute] = [n for n in classe.body if isinstance(n, ast.FunctionDef) and n.name == "execute"]
    return execute


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_ca03_a_primeira_instrucao_e_a_chamada_canonica_ao_guard(nome: str) -> None:
    execute = _execute(nome)
    param = execute.args.args[1].arg
    corpo = execute.body
    if isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
        corpo = corpo[1:]
    primeira = corpo[0]
    permissao = _NOME_DA_PERMISSAO[CENARIOS[nome].permissao]
    esperada = ast.dump(
        ast.parse(
            f"self._guard.authorize({param}.actor, {permissao}, "
            f"tenant_id={param}.tenant_id, unit_id={param}.unit_id)",
            mode="eval",
        ).body
    )
    if CENARIOS[nome].le_o_sujeito:
        assert isinstance(primeira, ast.Assign), f"{nome}: o escopo deveria ser guardado"
        assert [ast.dump(t) for t in primeira.targets] == [
            ast.dump(ast.Name(id="scope", ctx=ast.Store()))
        ]
    else:
        assert isinstance(primeira, ast.Expr), f"{nome}: escopo guardado sem precisar do sujeito"
    assert ast.dump(primeira.value) == esperada  # type: ignore[attr-defined]
    chamadas = [
        n
        for n in ast.walk(execute)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "authorize"
    ]
    assert len(chamadas) == 1, f"{nome}: authorize fora da abertura"


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_o_escopo_so_e_lido_pelo_sujeito(nome: str) -> None:
    execute = _execute(nome)
    usos = [n for n in ast.walk(execute) if isinstance(n, ast.Name) and n.id == "scope"]
    leituras = [n for n in usos if isinstance(n.ctx, ast.Load)]
    pais = {id(filho): pai for pai in ast.walk(execute) for filho in ast.iter_child_nodes(pai)}
    for leitura in leituras:
        pai = pais[id(leitura)]
        assert isinstance(pai, ast.Attribute) and pai.attr == "user_id", (
            f"{nome}: o escopo é lido além do sujeito"
        )
    assert bool(leituras) is CENARIOS[nome].le_o_sujeito


_ENTIDADES: Final = {
    schedule_module.Schedule,
    shift_band.ShiftBand,
    shift_demand.ShiftDemand,
    assignment.Assignment,
}


@pytest.mark.parametrize("nome", _modulos_da_pasta())
def test_nenhum_use_case_devolve_entidade(nome: str) -> None:
    retorno = typing.get_type_hints(_classe_do_modulo(nome).execute)["return"]
    tipos = {retorno, *typing.get_args(retorno)}
    assert not (tipos & _ENTIDADES), f"{nome} devolve entidade do domínio"

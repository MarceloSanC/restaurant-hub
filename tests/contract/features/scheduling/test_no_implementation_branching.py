"""CA04 — nenhum corpo de lei de scheduling ramifica por implementação.

Forma de `tests/contract/features/staff/test_no_implementation_branching.py`, e pela mesma
razão: um teste de contrato que sabe qual implementação está exercitando virou dois testes
que apenas se parecem, e a divergência que a suíte existe para revelar passa a ser
acomodada. A verificação é por AST — grep acusaria a palavra em docstring e comentário.

O `conftest.py` e o `support.py` ficam fora de propósito: é lá que a ramificação e a
semeadura por implementação **devem** existir.

A segunda metade fecha o risco central da Stage: `[postgres]` rodar contra o fake. Para
cada fixture **já promovida**, a tupla é exatamente `{"fake", "postgres"}` (o parâmetro
não some) e o ramo `postgres` entrega o adapter concreto (o ramo não constrói a coisa
errada). Cada Task que promove uma fixture acrescenta aqui o seu caso.
"""

import ast
from pathlib import Path

import pytest

from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_config_repository import (
    PostgresScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository import (
    PostgresScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from tests.contract.features.scheduling.conftest import (
    CONFIG_IMPLEMENTATIONS,
    SCHEDULE_IMPLEMENTATIONS,
)

pytestmark = pytest.mark.contract

_PASTA = Path(__file__).parent

# Módulo de lei → a fixture de implementações que todo teste dele recebe. Escrita à mão:
# um módulo removido da pasta tem de aparecer como falha, e a pasta é cobrada contra ela.
_MODULOS_DE_LEI: dict[str, str] = {
    "test_schedule_repository_laws.py": "schedule_repo",
    "test_schedule_config_repository_laws.py": "config_world",
    "test_staff_read_port_laws.py": "mundo",
}
_PADRAO_DE_MODULO_DE_LEI = "test_*laws*.py"

_NOMES_PROIBIDOS = frozenset({"request", "param", "getfixturevalue"})
_LITERAIS_PROIBIDOS = frozenset({"fake", "postgres"})

_Funcao = ast.FunctionDef | ast.AsyncFunctionDef


def _funcoes(modulo: str) -> list[_Funcao]:
    arvore = ast.parse((_PASTA / modulo).read_text(encoding="utf-8"))
    return [no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)]


def _corpo_sem_docstring(funcao: _Funcao) -> list[ast.stmt]:
    corpo = funcao.body
    primeiro = corpo[0] if corpo else None
    if (
        isinstance(primeiro, ast.Expr)
        and isinstance(primeiro.value, ast.Constant)
        and isinstance(primeiro.value.value, str)
    ):
        return corpo[1:]
    return corpo


def _nos(funcao: _Funcao) -> list[ast.AST]:
    return [no for stmt in _corpo_sem_docstring(funcao) for no in ast.walk(stmt)]


def test_a_lista_de_modulos_de_lei_cobre_a_pasta_inteira() -> None:
    na_pasta = {arquivo.name for arquivo in _PASTA.glob(_PADRAO_DE_MODULO_DE_LEI)}
    assert na_pasta == set(_MODULOS_DE_LEI)


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_nenhum_corpo_alcanca_o_parametro_da_fixture(modulo: str) -> None:
    violacoes = [
        (funcao.name, no.id if isinstance(no, ast.Name) else no.attr)
        for funcao in _funcoes(modulo)
        for no in _nos(funcao)
        if (isinstance(no, ast.Name) and no.id in _NOMES_PROIBIDOS)
        or (isinstance(no, ast.Attribute) and no.attr in _NOMES_PROIBIDOS)
    ]
    assert violacoes == [], f"{modulo}: corpo alcança o parâmetro da fixture: {violacoes}"


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_nenhum_corpo_menciona_o_id_de_uma_implementacao(modulo: str) -> None:
    violacoes = [
        (funcao.name, no.value)
        for funcao in _funcoes(modulo)
        for no in _nos(funcao)
        if isinstance(no, ast.Constant)
        and isinstance(no.value, str)
        and no.value in _LITERAIS_PROIBIDOS
    ]
    assert violacoes == [], f"{modulo}: corpo cita a implementação: {violacoes}"


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_nenhum_corpo_inspeciona_o_tipo_por_tras_da_fixture(modulo: str) -> None:
    """Escopado à fixture: `type(excinfo.value) is X` sobre exceção continua legítimo."""
    fixture = _MODULOS_DE_LEI[modulo]
    violacoes: list[tuple[str, str]] = []
    for funcao in _funcoes(modulo):
        for no in _nos(funcao):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Name):
                continue
            if no.func.id not in {"isinstance", "type"} or not no.args:
                continue
            if any(
                isinstance(interno, ast.Name) and interno.id == fixture
                for interno in ast.walk(no.args[0])
            ):
                violacoes.append((funcao.name, no.func.id))
    assert violacoes == [], f"{modulo}: corpo inspeciona o tipo por trás de `{fixture}`"


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_todo_teste_de_lei_recebe_a_fixture(modulo: str) -> None:
    """Quem não recebe a fixture roda uma vez só, contra uma implementação só."""
    fixture = _MODULOS_DE_LEI[modulo]
    sem_fixture = [
        funcao.name
        for funcao in _funcoes(modulo)
        if funcao.name.startswith("test_")
        and fixture not in {argumento.arg for argumento in funcao.args.args}
    ]
    assert sem_fixture == [], f"{modulo}: teste de lei sem a fixture `{fixture}`: {sem_fixture}"


# --- fixtures promovidas: o parâmetro existe e o ramo entrega o adapter real ------------


def test_config_world_roda_sobre_o_fake_e_o_postgres() -> None:
    assert set(CONFIG_IMPLEMENTATIONS) == {"fake", "postgres"}


@pytest.mark.parametrize("config_world", ["postgres"], indirect=True)
def test_o_ramo_postgres_de_config_world_e_o_adapter_real(
    config_world: tuple[ScheduleConfigRepository, SchedulingSettings],
) -> None:
    repo, _ = config_world
    assert isinstance(repo, PostgresScheduleConfigRepository)


def test_schedule_repo_roda_sobre_o_fake_e_o_postgres() -> None:
    assert set(SCHEDULE_IMPLEMENTATIONS) == {"fake", "postgres"}


@pytest.mark.parametrize("schedule_repo", ["postgres"], indirect=True)
def test_o_ramo_postgres_de_schedule_repo_e_o_adapter_real(
    schedule_repo: ScheduleRepository,
) -> None:
    assert isinstance(schedule_repo, PostgresScheduleRepository)

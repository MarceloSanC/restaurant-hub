"""O wiring de scheduling no composition root — CA10 da Stage 4.5.

A Stage 4.4 montou só os três ports de dados, provisórios (concept 4.4 §7 D-WIRING); a 4.5
monta os sete use cases sobre eles e o `AccessGuard` de scheduling, e os três campos saem.
As travas:

1. o contêiner tem os sete use cases e o guard, e **nenhum** port de dados de scheduling;
2. cada use case sobre os adapters reais, o **mesmo** `Engine`, as **mesmas** instâncias de
   repositório de staff, e o **mesmo** guard;
3. o guard sobre o **mesmo** `AuthorizeActionUseCase` e o **mesmo** `IdentityGuard` das rotas
   de identity e de staff — uma decisão de acesso;
4. todo provedor da borda de scheduling tem override, que devolve o objeto do contêiner;
5. só o composition root importa os adapters de scheduling (varredura com caso plantado);
6. o LAYOUT §6 registra que a exceção provisória foi removida.
"""

import ast
import inspect
import pathlib
from collections.abc import Callable
from types import ModuleType

import pytest

from restaurant_hub.composition_root import (
    ApplicationDependencies,
    build_http_wiring,
    wire_dependencies,
)
from restaurant_hub.features.identity.application.facade import IdentityAccessFacade
from restaurant_hub.features.scheduling.adapters.inbound.http import (
    dependencies as scheduling_dependencies,
)
from restaurant_hub.features.scheduling.adapters.inbound.http import (
    router as scheduling_router_module,
)
from restaurant_hub.features.scheduling.adapters.out.identity.local_access_guard import (
    LocalAccessGuard,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_config_repository import (
    PostgresScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository import (
    PostgresScheduleRepository,
)
from restaurant_hub.features.scheduling.adapters.out.staff.local_staff_read_adapter import (
    LocalStaffReadAdapter,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import AccessGuard
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
from restaurant_hub.features.staff.application.facade import StaffReadFacade
from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit

_REPO = pathlib.Path(__file__).resolve().parents[5]
_SRC = _REPO / "src" / "restaurant_hub"
_PACOTE_DE_ADAPTERS = _SRC / "features" / "scheduling" / "adapters"
_MODULO_DE_ADAPTERS = "restaurant_hub.features.scheduling.adapters"
_COMPOSITION_ROOT = _SRC / "composition_root.py"
_LAYOUT = _REPO / "docs" / "LAYOUT.md"
_USE_CASES = _SRC / "features" / "scheduling" / "application" / "use_cases"

# O contêiner de scheduling, transcrito: campo → tipo.
_CAMPOS: dict[str, type] = {
    "scheduling_create_schedule": CreateScheduleUseCase,
    "scheduling_get_schedule": GetScheduleUseCase,
    "scheduling_evaluate_schedule": EvaluateScheduleUseCase,
    "scheduling_publish_schedule": PublishScheduleUseCase,
    "scheduling_get_calendar": GetCalendarUseCase,
    "scheduling_list_past_schedules": ListPastSchedulesUseCase,
    "scheduling_get_my_schedule": GetMyScheduleUseCase,
    "scheduling_access_guard": AccessGuard,
}
_PROVISORIOS = ("scheduling_schedules", "scheduling_settings", "scheduling_staff_read")


def _dependencias() -> ApplicationDependencies:
    """O grafo real, sem banco no ar — `create_engine` não abre conexão."""
    return wire_dependencies(Settings(_env_file=None))


def test_o_conteiner_tem_os_sete_use_cases_e_o_guard_e_nenhum_port_de_dados() -> None:
    campos = {
        nome: campo.type
        for nome, campo in ApplicationDependencies.__dataclass_fields__.items()
        if nome.startswith("scheduling_")
    }
    assert campos == _CAMPOS
    assert not set(_PROVISORIOS) & set(ApplicationDependencies.__dataclass_fields__)


def test_um_campo_por_modulo_de_use_case() -> None:
    """Totalidade: todo módulo público de `use_cases/` tem o seu campo no contêiner."""
    modulos = {p.stem for p in _USE_CASES.glob("*.py") if not p.stem.startswith("_")}
    campos = {nome.removeprefix("scheduling_") for nome in _CAMPOS} - {"access_guard"}
    assert modulos == campos


def test_os_use_cases_sobre_os_adapters_reais_e_o_mesmo_grafo() -> None:
    deps = _dependencias()
    guard = deps.scheduling_access_guard
    assert isinstance(guard, LocalAccessGuard)

    publicar = deps.scheduling_publish_schedule
    escalas, configuracao, leitura = publicar._schedules, publicar._config, publicar._staff
    assert isinstance(escalas, PostgresScheduleRepository)
    assert isinstance(configuracao, PostgresScheduleConfigRepository)
    assert isinstance(leitura, LocalStaffReadAdapter)

    funcionarios = deps.staff_list_employees._employees
    funcoes = deps.staff_list_job_functions._job_functions
    assert escalas._engine is funcionarios._engine
    assert configuracao._engine is funcionarios._engine
    fachada = leitura._facade
    assert isinstance(fachada, StaffReadFacade)
    assert fachada._employees is funcionarios
    assert fachada._job_functions is funcoes

    for nome in _CAMPOS:
        if nome == "scheduling_access_guard":
            continue
        use_case = getattr(deps, nome)
        assert use_case._guard is guard, nome
        assert use_case._schedules is escalas, nome
        for atributo, esperado in (("_config", configuracao), ("_staff", leitura)):
            if hasattr(use_case, atributo):
                assert getattr(use_case, atributo) is esperado, (nome, atributo)


def test_o_guard_decide_sobre_o_mesmo_authorize_action_e_autentica_pelo_mesmo_identity_guard() -> (
    None
):
    deps = _dependencias()
    guard = deps.scheduling_access_guard
    assert isinstance(guard, LocalAccessGuard)
    fachada = guard._access
    assert isinstance(fachada, IdentityAccessFacade)
    assert fachada._authorize_action is deps.identity_authorize_action
    autenticar = guard._authenticate_request
    assert getattr(autenticar, "__self__", None) is deps.identity_guard
    assert getattr(autenticar, "__func__", None) is type(deps.identity_guard).authenticate_principal


def test_duas_chamadas_devolvem_grafos_independentes() -> None:
    primeiro, segundo = _dependencias(), _dependencias()
    for nome in _CAMPOS:
        assert getattr(primeiro, nome) is not getattr(segundo, nome), nome


# ---------------------------------------------------------------------------
# A borda: todo provedor tem override, e ele devolve o objeto do contêiner
# ---------------------------------------------------------------------------


def _provedores_de(modulo: ModuleType) -> set[Callable[..., object]]:
    """As chaves de override do módulo: funções **sem parâmetros** `_get_*`/`get_*`.

    O "sem parâmetros" separa provedor de rota: três handlers do router de scheduling
    (`get_schedule`, `get_calendar`, `get_my_schedule`) casam o prefixo e não são chaves.
    """
    return {
        valor
        for nome, valor in vars(modulo).items()
        if nome.startswith(("_get_", "get_"))
        and inspect.isfunction(valor)
        and valor.__module__ == modulo.__name__
        and not inspect.signature(valor).parameters
    }


def test_todo_provedor_da_borda_de_scheduling_tem_override() -> None:
    wiring = build_http_wiring(_dependencias())
    provedores = _provedores_de(scheduling_router_module) | _provedores_de(scheduling_dependencies)
    assert len(provedores) == len(_CAMPOS)
    assert [p.__name__ for p in provedores if p not in wiring.dependency_overrides] == []


def test_cada_override_devolve_o_objeto_do_conteiner() -> None:
    deps = _dependencias()
    overrides = build_http_wiring(deps).dependency_overrides
    assert overrides[scheduling_dependencies.get_access_guard]() is deps.scheduling_access_guard
    por_provedor = {
        "_get_create_schedule": deps.scheduling_create_schedule,
        "_get_get_schedule": deps.scheduling_get_schedule,
        "_get_evaluate_schedule": deps.scheduling_evaluate_schedule,
        "_get_publish_schedule": deps.scheduling_publish_schedule,
        "_get_calendar": deps.scheduling_get_calendar,
        "_get_list_past_schedules": deps.scheduling_list_past_schedules,
        "_get_my_schedule": deps.scheduling_get_my_schedule,
    }
    for nome, esperado in por_provedor.items():
        assert overrides[getattr(scheduling_router_module, nome)]() is esperado, nome


def test_o_wiring_registra_o_router_e_o_registrador_de_scheduling() -> None:
    wiring = build_http_wiring(_dependencias())
    assert wiring.routers[-1] is scheduling_router_module.router
    assert wiring.register_error_handlers[-1].__name__ == "register_scheduling_error_handlers"


# ---------------------------------------------------------------------------
# Só o composition root importa os adapters de scheduling
# ---------------------------------------------------------------------------


def _alvos(arvore: ast.AST) -> list[str]:
    alvos: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            alvos.append(no.module)
        elif isinstance(no, ast.Import):
            alvos.extend(alias.name for alias in no.names)
    return alvos


def _importadores_dos_adapters() -> set[str]:
    culpados: set[str] = set()
    for arquivo in _SRC.rglob("*.py"):
        if arquivo.is_relative_to(_PACOTE_DE_ADAPTERS):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        if any(alvo.startswith(_MODULO_DE_ADAPTERS) for alvo in _alvos(arvore)):
            culpados.add(arquivo.relative_to(_SRC).as_posix())
    return culpados


def test_so_o_composition_root_importa_os_adapters_de_scheduling() -> None:
    assert _importadores_dos_adapters() == {_COMPOSITION_ROOT.relative_to(_SRC).as_posix()}


@pytest.mark.parametrize(
    "codigo_violador",
    [
        "from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository "
        "import PostgresScheduleRepository",
        "import restaurant_hub.features.scheduling.adapters.inbound.http.router",
    ],
    ids=["repositorio-postgres", "router"],
)
def test_um_import_proibido_plantado_reprova(codigo_violador: str) -> None:
    assert any(alvo.startswith(_MODULO_DE_ADAPTERS) for alvo in _alvos(ast.parse(codigo_violador)))


# ---------------------------------------------------------------------------
# LAYOUT §6 — a exceção provisória foi removida
# ---------------------------------------------------------------------------


def test_o_layout_6_registra_a_remocao_dos_campos_provisorios() -> None:
    texto = _LAYOUT.read_text(encoding="utf-8")
    inicio = texto.index("## 6. Composition Root")
    secao = texto[inicio : texto.index("\n## 7.", inicio)]
    assert "removeu" in secao
    for nome in _PROVISORIOS:
        assert f"`{nome}`" in secao, nome

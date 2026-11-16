"""O wiring de scheduling no composition root — CA16 e a nota do LAYOUT §6 (CA19).

A Stage 4.4 monta os **três ports de dados** de scheduling, não os use cases (concept §7
D-WIRING): os sete use cases exigem o `AccessGuard` de scheduling, que é da 4.5. Os três
campos são provisórios e ficam contidos por três travas, todas aqui:

1. montados sobre os adapters reais, o **mesmo** `Engine` e as **mesmas** instâncias de
   repositório de staff que servem as rotas de staff;
2. só o composition root importa os adapters de scheduling (varredura com caso plantado);
3. **nenhum** provedor de `build_http_wiring` entrega um dos três campos — um port de dados
   numa rota leria escala e staff sem a autorização dos use cases —, e o detector reprova
   um provedor plantado.

E a exceção ao "expõe use cases" do LAYOUT §6 está escrita lá, com os três nomes de campo.
"""

import ast
import pathlib
from collections.abc import Callable, Mapping
from typing import Any

import pytest

from restaurant_hub.composition_root import (
    ApplicationDependencies,
    build_http_wiring,
    wire_dependencies,
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
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffReadPort,
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

_CAMPOS: Mapping[str, type] = {
    "scheduling_schedules": ScheduleRepository,
    "scheduling_settings": ScheduleConfigRepository,
    "scheduling_staff_read": StaffReadPort,
}


def _dependencias() -> ApplicationDependencies:
    """O grafo real, sem banco no ar — `create_engine` não abre conexão."""
    return wire_dependencies(Settings(_env_file=None))


def test_o_conteiner_tem_exatamente_os_tres_campos_anotados_com_os_ports() -> None:
    campos = {
        nome: campo.type
        for nome, campo in ApplicationDependencies.__dataclass_fields__.items()
        if nome.startswith("scheduling_")
    }
    assert campos == dict(_CAMPOS)


def test_os_campos_sao_os_adapters_reais_sobre_o_mesmo_engine_e_os_mesmos_repositorios() -> None:
    deps = _dependencias()
    escalas, configuracao, leitura = (
        deps.scheduling_schedules,
        deps.scheduling_settings,
        deps.scheduling_staff_read,
    )
    assert isinstance(escalas, PostgresScheduleRepository)
    assert isinstance(configuracao, PostgresScheduleConfigRepository)
    assert isinstance(leitura, LocalStaffReadAdapter)

    funcionarios = deps.staff_list_employees._employees
    funcoes = deps.staff_list_job_functions._job_functions
    engine = funcionarios._engine
    assert escalas._engine is engine
    assert configuracao._engine is engine

    fachada = leitura._facade
    assert isinstance(fachada, StaffReadFacade)
    assert fachada._employees is funcionarios
    assert fachada._job_functions is funcoes


def test_duas_chamadas_devolvem_grafos_independentes() -> None:
    primeiro, segundo = _dependencias(), _dependencias()
    for nome in _CAMPOS:
        assert getattr(primeiro, nome) is not getattr(segundo, nome), nome


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
    """Módulos de `src/` fora do próprio pacote de adapters que o importam."""
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
        "import restaurant_hub.features.scheduling.adapters.out.staff.local_staff_read_adapter",
    ],
    ids=["repositorio-postgres", "adapter-de-staff"],
)
def test_um_import_proibido_plantado_reprova(codigo_violador: str) -> None:
    assert any(alvo.startswith(_MODULO_DE_ADAPTERS) for alvo in _alvos(ast.parse(codigo_violador)))


# ---------------------------------------------------------------------------
# Nenhum provedor HTTP entrega um port de dados de scheduling
# ---------------------------------------------------------------------------


def _provedores_que_entregam_os_campos(
    overrides: Mapping[Callable[..., Any], Callable[..., Any]], deps: ApplicationDependencies
) -> list[str]:
    """Os provedores cujo valor devolvido **é** um dos três objetos (identidade)."""
    proibidos = {id(getattr(deps, nome)): nome for nome in _CAMPOS}
    return [
        f"{getattr(chave, '__qualname__', chave)} -> {proibidos[id(valor)]}"
        for chave, provedor in overrides.items()
        if id(valor := provedor()) in proibidos
    ]


def test_nenhum_provedor_de_build_http_wiring_entrega_um_dos_tres_campos() -> None:
    deps = _dependencias()
    overrides = build_http_wiring(deps).dependency_overrides
    assert overrides, "a varredura ficaria vazia sem provedores"
    assert _provedores_que_entregam_os_campos(overrides, deps) == []


def test_o_detector_reprova_um_provedor_plantado() -> None:
    deps = _dependencias()

    def _get_schedules() -> None: ...

    plantado = {
        **build_http_wiring(deps).dependency_overrides,
        _get_schedules: lambda: deps.scheduling_schedules,
    }
    assert _provedores_que_entregam_os_campos(plantado, deps) == [
        f"{_get_schedules.__qualname__} -> scheduling_schedules"
    ]


# ---------------------------------------------------------------------------
# CA19 — a exceção está escrita no LAYOUT §6
# ---------------------------------------------------------------------------


def test_a_nota_do_layout_6_nomeia_os_tres_campos_provisorios() -> None:
    texto = _LAYOUT.read_text(encoding="utf-8")
    inicio = texto.index("## 6. Composition Root")
    secao = texto[inicio : texto.index("\n## 7.", inicio)]
    for nome in _CAMPOS:
        assert f"`{nome}`" in secao, nome
    assert "4.5" in secao

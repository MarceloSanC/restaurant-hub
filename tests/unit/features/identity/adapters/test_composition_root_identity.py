"""Wiring dos repositórios de identity no composition root — CA17.

Dois testes com propósitos diferentes: o primeiro confere que o grafo é montado; o
segundo é o **guarda mecânico** da regra que o `ignore_imports` do import-linter
deixou de cobrir.

Esse segundo teste existe porque a regra "só o composition root instancia adapter"
é fácil de violar sem querer (basta um import "prático" num router da 2.4) e
invisível numa revisão de diff — exatamente o perfil de regra que precisa de gate
automático em vez de prosa. LAYOUT §6 registra que o `check_layout.py` não detecta
o caminho indireto; este teste fecha essa lacuna pelo lado do consumidor.
"""

import ast
import pathlib

import pytest

from restaurant_hub.composition_root import ApplicationDependencies, wire_dependencies
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
from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit

_SRC = pathlib.Path(__file__).resolve().parents[5] / "src" / "restaurant_hub"
_MODULO_DE_ADAPTERS = "restaurant_hub.features.identity.adapters.out.postgres"
_COMPOSITION_ROOT = _SRC / "composition_root.py"


def test_wire_dependencies_monta_os_quatro_repositorios_postgres() -> None:
    """CA17 — o grafo real, com as implementações concretas.

    Note que `wire_dependencies()` roda **sem banco no ar**: `create_engine` não
    abre conexão, então o boot não depende de o Postgres já ter subido.
    """
    deps = wire_dependencies(Settings(_env_file=None))

    assert isinstance(deps, ApplicationDependencies)
    assert isinstance(deps.identity_restaurants, PostgresRestaurantRepository)
    assert isinstance(deps.identity_units, PostgresUnitRepository)
    assert isinstance(deps.identity_users, PostgresUserRepository)
    assert isinstance(deps.identity_sessions, PostgresSessionRepository)


def test_duas_chamadas_devolvem_grafos_independentes() -> None:
    """Sem singleton global (skill `composition-root`).

    Um `Engine` guardado em variável de módulo faria dois testes compartilharem
    conexão e estado, e tornaria impossível montar um grafo apontando para outro
    banco sem contaminar o primeiro.
    """
    primeiro = wire_dependencies(Settings(_env_file=None))
    segundo = wire_dependencies(Settings(_env_file=None))

    assert primeiro is not segundo
    assert primeiro.identity_users is not segundo.identity_users


def _modulos_que_importam_adapters() -> set[str]:
    """Varre `src/` por imports do pacote de adapters Postgres de identity.

    Ignora os arquivos **de dentro do próprio pacote**: um repositório importar
    `mappers`, `tables` ou `integrity_errors` do vizinho é coesão interna, não a
    violação que este teste procura (um consumidor externo pulando o composition
    root).
    """
    pacote_de_adapters = _SRC / "features" / "identity" / "adapters" / "out" / "postgres"
    culpados: set[str] = set()
    for arquivo in _SRC.rglob("*.py"):
        if arquivo.is_relative_to(pacote_de_adapters):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            alvo = ""
            if isinstance(no, ast.ImportFrom) and no.module:
                alvo = no.module
            elif isinstance(no, ast.Import):
                alvo = " ".join(alias.name for alias in no.names)
            if _MODULO_DE_ADAPTERS in alvo:
                culpados.add(str(arquivo.relative_to(_SRC)))
    return culpados


def test_so_o_composition_root_importa_os_adapters_de_identity() -> None:
    """A regra que o `ignore_imports` deixou de cobrir, como asserção mecânica.

    O contrato `shared-independence` do import-linter ganhou uma supressão para o
    par `shared.infrastructure.http.app -> composition_root` (LAYOUT §6). A
    supressão é estreita, mas ainda assim abre uma janela: nada no import-linter
    impediria um **outro** módulo de importar os adapters direto. Este teste fecha
    a janela pelo lado do consumidor.
    """
    esperado = {str(_COMPOSITION_ROOT.relative_to(_SRC))}
    assert _modulos_que_importam_adapters() == esperado, (
        "apenas composition_root.py pode importar "
        f"{_MODULO_DE_ADAPTERS}; receba o repositório por injeção (LAYOUT §6)"
    )

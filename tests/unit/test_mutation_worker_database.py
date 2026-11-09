"""Sob o mutmut, cada processo de pytest ganha um banco próprio — issue #132.

O mutmut 3.7.0 põe o nome do mutante em `MUTANT_UNDER_TEST` no worker
(`os.fork()` e então `os.environ["MUTANT_UNDER_TEST"] = mutant_name`), e
`stats`/`fail` nas corridas do processo pai. Fora dele a variável não existe, e
a suíte segue no banco que a guarda conferiu. A criação e o drop do banco são
medidos contra o Postgres em `tests/integration/test_mutation_worker_database.py`.
"""

import pytest
from sqlalchemy import make_url

from tests.conftest import MUTMUT_MUTANT_ENV, mutation_worker_database_url

pytestmark = pytest.mark.unit

_BASE = "postgresql+psycopg://user:pass@localhost:5433/restaurant_hub"


def test_a_variavel_e_a_que_o_mutmut_preenche() -> None:
    assert MUTMUT_MUTANT_ENV == "MUTANT_UNDER_TEST"


def test_fora_do_mutmut_a_suite_fica_no_banco_da_guarda() -> None:
    assert mutation_worker_database_url(_BASE, "", 4242) is None


@pytest.mark.parametrize(
    "mutant_under_test",
    [
        "restaurant_hub.features.identity.domain.entities.user.x_can__mutmut_3",
        "stats",
        "fail",
    ],
)
def test_sob_o_mutmut_o_banco_e_o_do_processo(mutant_under_test: str) -> None:
    url = mutation_worker_database_url(_BASE, mutant_under_test, 4242)

    assert url is not None
    assert make_url(url).database == "restaurant_hub_mutmut_4242"


def test_dois_workers_simultaneos_nunca_dividem_banco() -> None:
    """O PID é único entre os processos vivos — é ele, e não o mutante, que nomeia o banco."""
    um = mutation_worker_database_url(_BASE, "m__mutmut_1", 100)
    outro = mutation_worker_database_url(_BASE, "m__mutmut_1", 101)

    assert um != outro


def test_so_o_nome_do_banco_muda() -> None:
    """Host, porta e credenciais são os da URL que a guarda conferiu (porta da worktree)."""
    url = mutation_worker_database_url(_BASE, "m__mutmut_1", 7)
    assert url is not None

    base, worker = make_url(_BASE), make_url(url)
    assert worker.set(database=base.database) == base
    assert worker.password == "pass"

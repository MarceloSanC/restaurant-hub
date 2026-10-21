"""A guarda da `DATABASE_URL` da suíte contra a `POSTGRES_PORT` da worktree (issue #58).

O incidente de origem (Stage 4.1, Task 01): a worktree tinha `POSTGRES_PORT=5433`
e nenhuma `DATABASE_URL`; o `Settings` caiu no default — porta 5432, o Postgres
do checkout principal —, e 629 testes deram `ERROR at setup` com
`ResolutionError: No such revision '0004'`. O banco era o de outra sessão, e a
fixture `engine`, que recria o schema, só não o derrubou porque a migration
`0004` não existia na branch. A guarda roda na fixture `database_url`, antes de
qualquer conexão.

Os primeiros testes fixam a regra. Os do fim leem um `.env` de verdade, pelo
mesmo pydantic-settings da app — inclusive o `.env` que o
`scripts/worktree-new.py` escreve, que a guarda tem de aceitar sempre: o script
escreve, a guarda confere, e os dois têm de concordar sobre o que é loopback.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import make_url

from tests.conftest import database_port_mismatch, is_loopback, resolve_test_database_url

pytestmark = pytest.mark.unit
pytest_plugins = ["pytester"]

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "worktree-new.py"

PUBLISHED_PORT = 5440
LIBPQ_DEFAULT_PORT = 5432
OTHER_PORT = 5999
SECRET = "s3gr3d0"
PORTS = {"APP_PORT": 8008, "POSTGRES_PORT": PUBLISHED_PORT, "REDIS_PORT": 6387}


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worktree_new", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wn = _load_script()


def _url(host_port: str) -> str:
    return f"postgresql+psycopg://user:{SECRET}@{host_port}/restaurant_hub"


# ---------------------------------------------------------------------------
# A regra
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host_port", ["localhost:5440", "127.0.0.1:5440", "[::1]:5440", "LOCALHOST:5440"]
)
def test_loopback_url_on_the_published_port_passes(host_port: str) -> None:
    assert database_port_mismatch(_url(host_port), PUBLISHED_PORT) is None


@pytest.mark.parametrize(
    ("host_port", "reached"),
    [
        ("localhost:5432", "porta 5432 de localhost"),
        ("127.0.0.1:5433", "porta 5433 de 127.0.0.1"),
        ("[::1]:5999", "porta 5999 de ::1"),
    ],
)
def test_loopback_url_on_another_port_is_refused(host_port: str, reached: str) -> None:
    mismatch = database_port_mismatch(_url(host_port), PUBLISHED_PORT)

    assert mismatch is not None
    assert reached in mismatch
    assert f"POSTGRES_PORT desta worktree é {PUBLISHED_PORT}" in mismatch
    assert "docker compose up -d --wait postgres" in mismatch


def test_refusal_never_echoes_the_password() -> None:
    mismatch = database_port_mismatch(_url("localhost:5432"), PUBLISHED_PORT)

    assert mismatch is not None
    assert SECRET not in mismatch


def test_url_without_port_counts_as_the_libpq_default() -> None:
    """Sem porta na URL, a libpq vai à 5432 — medido com o psycopg 3.3.4."""
    assert database_port_mismatch(_url("localhost"), LIBPQ_DEFAULT_PORT) is None

    mismatch = database_port_mismatch(_url("localhost"), PUBLISHED_PORT)
    assert mismatch is not None
    assert f"porta {LIBPQ_DEFAULT_PORT} de localhost" in mismatch


@pytest.mark.parametrize(
    "url",
    [
        # dentro da rede do compose, o service responde na 5432 do contêiner
        _url("postgres:5432"),
        _url("db.example.com:5432"),
        _url("10.0.0.5:5432"),
        "postgresql+psycopg://user:pass@/restaurant_hub?host=/var/run/postgresql",
    ],
)
def test_hosts_off_the_published_port_are_not_bound_to_it(url: str) -> None:
    assert database_port_mismatch(url, PUBLISHED_PORT) is None


@pytest.mark.parametrize("host_port", ["localhost:5432", "localhost:5999", "postgres:5432"])
def test_rule_does_not_apply_without_a_declared_postgres_port(host_port: str) -> None:
    """CI e checkout sem `.env`: não há porta publicada declarada a comparar."""
    assert database_port_mismatch(_url(host_port), None) is None


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "LocalHost",
        "127.0.0.1",
        "127.255.255.254",
        "::1",
        "postgres",
        "0.0.0.0",
        "10.0.0.5",
        "localhost.example.com",
        "",
        None,
    ],
)
def test_guard_and_script_agree_on_what_is_loopback(host: str | None) -> None:
    """O script só reescreve o que a guarda confere — um critério só, em dois lugares."""
    assert is_loopback(host) is wn.is_loopback(host)


# ---------------------------------------------------------------------------
# A fixture, contra um `.env` de verdade
# ---------------------------------------------------------------------------


@pytest.fixture
def worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Diretório corrente sem ambiente herdado: só vale o `.env` que o teste escrever."""
    for name in ("DATABASE_URL", "POSTGRES_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_issue_58_env_is_refused(worktree: Path) -> None:
    """O `.env` exato que o script antigo gerava: três portas e nenhuma `DATABASE_URL`."""
    (worktree / ".env").write_text(
        "# Portas auto-geradas para esta worktree paralela (scripts/worktree-new.py)\n"
        "APP_PORT=8001\n"
        "POSTGRES_PORT=5433\n"
        "REDIS_PORT=6380\n",
        encoding="utf-8",
    )

    with pytest.raises(pytest.fail.Exception, match="porta 5432 de localhost"):
        resolve_test_database_url()


def test_process_environment_wins_over_the_dotenv_as_in_compose(
    worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`POSTGRES_PORT=5999 docker compose config` publica a 5999 por cima do `.env`."""
    wn.write_worktree_env_ports(worktree, PORTS)
    monkeypatch.setenv("POSTGRES_PORT", str(OTHER_PORT))

    with pytest.raises(pytest.fail.Exception, match=f"desta worktree é {OTHER_PORT}"):
        resolve_test_database_url()


def test_database_url_fixture_runs_the_guard(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fixture é o ponto de integração: sem a chamada, a regra existiria e nada a aplicaria.

    Sessão interna cujo único teste pede `database_url` — nenhuma conexão é
    aberta, nem se a guarda falhar. O diretório corrente é o do `pytester`, sem
    `.env`: a URL é o default do `Settings`, na 5432.
    """
    pytester.makeconftest("from tests.conftest import database_url  # noqa: F401\n")
    pytester.makepyfile("def test_asks_for_the_url(database_url):\n    pass\n")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_PORT", str(PUBLISHED_PORT))

    # A sessão interna não lê o pyproject; sem o plugin, o pytest-asyncio não
    # reclama da configuração que falta — o teste interno é síncrono.
    result = pytester.runpytest_inprocess("-p", "no:cacheprovider", "-p", "no:asyncio")

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*A DATABASE_URL aponta para a porta 5432 de localhost*"])


def test_url_passes_through_when_no_postgres_port_is_declared(worktree: Path) -> None:
    (worktree / ".env").write_text(f"DATABASE_URL={_url('localhost:5999')}\n", encoding="utf-8")

    assert resolve_test_database_url() == _url("localhost:5999")


@pytest.mark.parametrize(
    ("copied", "expected_port"),
    [
        ([], PUBLISHED_PORT),  # o caso medido: o checkout principal não tem `.env`
        (
            [
                "DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/restaurant_hub",
                "POSTGRES_PORT=5432",
            ],
            PUBLISHED_PORT,
        ),
        (["DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1/restaurant_hub"], PUBLISHED_PORT),
        (
            ['DATABASE_URL="postgresql+psycopg://user:pass@[::1]:5432/restaurant_hub"'],
            PUBLISHED_PORT,
        ),
        (
            [
                "POSTGRES_PORT=5432",
                "DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/restaurant_hub",
                "POSTGRES_PORT=5433",
                "DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/restaurant_hub",
            ],
            PUBLISHED_PORT,
        ),
        # caminho A/B: a URL fala com o service do compose, e fica como estava
        (
            ["DATABASE_URL=postgresql+psycopg://user:pass@postgres:5432/restaurant_hub"],
            LIBPQ_DEFAULT_PORT,
        ),
    ],
)
def test_every_env_the_script_writes_passes_the_guard(
    worktree: Path, copied: list[str], expected_port: int
) -> None:
    if copied:
        (worktree / ".env").write_text("\n".join(copied) + "\n", encoding="utf-8")

    wn.write_worktree_env_ports(worktree, PORTS)

    assert make_url(resolve_test_database_url()).port == expected_port

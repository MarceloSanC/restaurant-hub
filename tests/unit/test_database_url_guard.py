"""A guarda da `DATABASE_URL` da suíte contra a porta que o compose publica (issue #58).

O incidente de origem (Stage 4.1, Task 01): a worktree tinha `POSTGRES_PORT=5433`
e nenhuma `DATABASE_URL`; o `Settings` caiu no default — porta 5432, o Postgres
do checkout principal —, e 629 testes deram `ERROR at setup` com
`ResolutionError: No such revision '0004'`. O banco era o de outra sessão, e a
fixture `engine`, que recria o schema, só não o derrubou porque a migration
`0004` não existia na branch. A guarda roda na fixture `database_url`, antes de
qualquer conexão; a regra é a de `scripts/database_url_guard.py` (issue #85).

"A porta que o compose publica" é resolvida como o compose a resolve:
`POSTGRES_PORT` do ambiente, depois a do `.env` da raiz do checkout, e a 5432 do
`${POSTGRES_PORT:-5432}` sem nenhuma das duas. Os primeiros testes fixam a regra;
os do fim leem um `.env` de verdade, pelo mesmo pydantic-settings da app —
inclusive o `.env` que o `scripts/worktree-new.py` escreve, que a guarda tem de
aceitar sempre: o script escreve, a guarda confere, e o critério de loopback dos
dois é um só (o script importa o da guarda, issue #85).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from sqlalchemy import make_url

from restaurant_hub.shared.infrastructure.config.settings import get_settings
from scripts import database_url_guard as guard
from scripts.database_url_guard import (
    COMPOSE_DEFAULT_POSTGRES_PORT,
    database_port_mismatch,
    is_loopback,
    published_postgres_port,
)
from tests.conftest import resolve_test_database_url

pytestmark = pytest.mark.unit
pytest_plugins = ["pytester"]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "worktree-new.py"
_GUARD = _REPO_ROOT / "scripts" / "database_url_guard.py"

PUBLISHED_PORT = 5440
LIBPQ_DEFAULT_PORT = 5432
OTHER_PORT = 5999
SECRET = "s3gr3d0"
PORTS = {"APP_PORT": 8008, "POSTGRES_PORT": PUBLISHED_PORT, "REDIS_PORT": 6387}
COMMAND_FAILED = 3
SIGINT_EXIT = 130
ARGPARSE_USAGE_EXIT = 2


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
    assert f"publica o Postgres na porta {PUBLISHED_PORT}" in mismatch
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


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", True),
        ("LocalHost", True),
        ("127.0.0.1", True),
        ("127.255.255.254", True),
        ("::1", True),
        ("postgres", False),
        ("0.0.0.0", False),
        ("10.0.0.5", False),
        ("localhost.example.com", False),
        ("", False),
        (None, False),
    ],
)
def test_is_loopback(host: str | None, expected: bool) -> None:
    assert is_loopback(host) is expected


def test_script_rewrites_by_the_guard_criterion() -> None:
    """O script só reescreve o que a guarda confere: o `is_loopback` dele é o da guarda.

    Até a #85 eram duas cópias com um teste de concordância; agora a cópia não
    existe, e o que se cobra é que ela não volte.
    """
    assert Path(wn.is_loopback.__code__.co_filename).resolve() == _GUARD.resolve()


def test_guard_module_top_is_standard_library() -> None:
    """O `worktree-new.py` roda sem o venv e importa a guarda.

    O topo dela não pode puxar SQLAlchemy, pydantic nem o pacote da app.
    """
    probe = (
        "import sys; sys.path.insert(0, sys.argv[1]); import database_url_guard; "
        "print(sorted({m.split('.')[0] for m in sys.modules} & "
        "{'sqlalchemy', 'pydantic', 'pydantic_settings', 'restaurant_hub'}))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(_GUARD.parent)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "[]"


# ---------------------------------------------------------------------------
# A porta publicada, como o compose a resolve
# ---------------------------------------------------------------------------


def test_compose_default_mirrors_the_compose_file() -> None:
    """A 5432 sem `POSTGRES_PORT` é a do `docker-compose.yml` — e a do script."""
    compose = yaml.safe_load((_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["postgres"]["ports"] == [
        f"${{POSTGRES_PORT:-{COMPOSE_DEFAULT_POSTGRES_PORT}}}:5432"
    ]
    assert wn.PORT_DEFAULTS["POSTGRES_PORT"] == COMPOSE_DEFAULT_POSTGRES_PORT


@pytest.fixture
def no_port_in_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "POSTGRES_PORT"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.usefixtures("no_port_in_environment")
@pytest.mark.parametrize("env_lines", [None, "DEBUG=true\n", "POSTGRES_PORT=\n"])
def test_missing_or_empty_postgres_port_means_the_compose_default(
    tmp_path: Path, env_lines: str | None
) -> None:
    """Sem `.env`, sem a chave, ou com ela vazia: o `:-` do compose publica a 5432."""
    if env_lines is not None:
        (tmp_path / ".env").write_text(env_lines, encoding="utf-8")

    assert published_postgres_port(tmp_path) == COMPOSE_DEFAULT_POSTGRES_PORT


@pytest.mark.usefixtures("no_port_in_environment")
def test_published_port_comes_from_the_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(f"POSTGRES_PORT={PUBLISHED_PORT}\n", encoding="utf-8")

    assert published_postgres_port(tmp_path) == PUBLISHED_PORT


def test_process_environment_wins_over_the_dotenv_as_in_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`POSTGRES_PORT=5999 docker compose config` publica a 5999 por cima do `.env`."""
    (tmp_path / ".env").write_text(f"POSTGRES_PORT={PUBLISHED_PORT}\n", encoding="utf-8")
    monkeypatch.setenv("POSTGRES_PORT", str(OTHER_PORT))

    assert published_postgres_port(tmp_path) == OTHER_PORT


# ---------------------------------------------------------------------------
# A fixture, contra um `.env` de verdade
# ---------------------------------------------------------------------------


@pytest.fixture
def worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_port_in_environment: None
) -> Iterator[Path]:
    """Checkout falso como diretório corrente, sem ambiente nem `get_settings()` herdados."""
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_issue_58_env_is_refused(worktree: Path) -> None:
    """O `.env` exato que o script antigo gerava: três portas e nenhuma `DATABASE_URL`."""
    (worktree / ".env").write_text(
        "# Portas auto-geradas para esta worktree paralela (scripts/worktree-new.py)\n"
        "APP_PORT=8001\n"
        "POSTGRES_PORT=5433\n"
        "REDIS_PORT=6380\n",
        encoding="utf-8",
    )

    with pytest.raises(pytest.fail.Exception, match="porta 5432 de localhost") as refusal:
        resolve_test_database_url(compose_dir=worktree)

    # da raiz, a dica do diretório corrente seria falsa
    assert "raiz do checkout" not in str(refusal.value)


def test_reverse_issue_58_is_refused(worktree: Path) -> None:
    """A #58 ao contrário: sem `POSTGRES_PORT`, a URL aponta para o banco de uma worktree."""
    (worktree / ".env").write_text(f"DATABASE_URL={_url('localhost:5440')}\n", encoding="utf-8")

    with pytest.raises(pytest.fail.Exception, match="publica o Postgres na porta 5432"):
        resolve_test_database_url(compose_dir=worktree)


def test_ci_shape_passes(worktree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """O job de gate: `DATABASE_URL` na 5432 por `env:`, sem `.env` nem `POSTGRES_PORT`."""
    monkeypatch.setenv("DATABASE_URL", _url("localhost:5432"))

    assert resolve_test_database_url(compose_dir=worktree) == _url("localhost:5432")


def test_pytest_from_a_subdirectory_is_refused_with_a_hint(worktree: Path) -> None:
    """O `Settings` lê o `.env` do diretório corrente; o compose, o da raiz.

    De um subdiretório, a URL cai no default (5432) enquanto o compose da worktree
    publica a dela — a #58 de novo, pela porta do diretório corrente.
    """
    wn.write_worktree_env_ports(worktree, PORTS)
    subdirectory = worktree / "tests" / "unit"
    subdirectory.mkdir(parents=True)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(subdirectory)

        with pytest.raises(pytest.fail.Exception) as refusal:
            resolve_test_database_url(compose_dir=worktree)

    assert "porta 5432 de localhost" in str(refusal.value)
    assert "rode o pytest e o make da raiz do checkout" in str(refusal.value)


def test_stale_get_settings_cache_does_not_decide_the_url(
    worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guarda devolve a URL do ambiente de agora, não a do `get_settings()` em cache.

    Até a #86 ela recusava um cache divergente, porque era ele que o Alembic lia.
    Desde a #86 o Alembic migra a URL que `_recriar_schema` lhe passa — esta —, e
    o cache não decide nada: a guarda nem o consulta.
    """
    wn.write_worktree_env_ports(worktree, PORTS)
    monkeypatch.setenv("DATABASE_URL", _url("localhost:5999"))
    get_settings()  # outro teste deixou o cache com uma URL que o ambiente já não tem
    monkeypatch.setenv("DATABASE_URL", _url(f"localhost:{PUBLISHED_PORT}"))

    assert resolve_test_database_url(compose_dir=worktree) == _url(f"localhost:{PUBLISHED_PORT}")


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
        # devcontainer ou compose direto: a URL fala com o service, e fica como estava
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

    assert make_url(resolve_test_database_url(compose_dir=worktree)).port == expected_port


# ---------------------------------------------------------------------------
# `make migrate` e `make run` (issue #85)
# ---------------------------------------------------------------------------


class _Ran:
    """O `subprocess.run` trocado: guarda o comando e devolve o exit code pedido.

    Sem `cwd` nem `env`: o comando roda no diretório corrente, com o ambiente do
    `make` — os mesmos que a guarda acabou de conferir.
    """

    def __init__(self, returncode: int = 0) -> None:
        self.commands: list[list[str]] = []
        self.returncode = returncode

    def __call__(
        self, command: list[str], *, check: bool, **options: object
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert options == {}
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncode)


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> _Ran:
    fake = _Ran()
    monkeypatch.setattr(guard.subprocess, "run", fake)
    return fake


@pytest.mark.parametrize("target", ["migrate", "run"])
def test_make_target_refuses_with_the_suite_message(
    worktree: Path, ran: _Ran, capsys: pytest.CaptureFixture[str], target: str
) -> None:
    """O `.env` da #58: o alvo sai com 1, a mensagem é a da suíte e nada roda."""
    (worktree / ".env").write_text(f"POSTGRES_PORT={PUBLISHED_PORT}\n", encoding="utf-8")

    assert guard.main([target], compose_dir=worktree) == 1

    assert ran.commands == []
    with pytest.raises(pytest.fail.Exception) as refusal:
        resolve_test_database_url(compose_dir=worktree)
    assert capsys.readouterr().err.strip() == str(refusal.value).strip()


@pytest.mark.parametrize(
    ("target", "tail"),
    [
        ("migrate", ["-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"]),
        ("run", ["-m", "uvicorn", "restaurant_hub.main:app", "--reload", "--host", "0.0.0.0"]),
    ],
)
def test_make_target_runs_its_command_when_the_url_matches(
    worktree: Path, ran: _Ran, target: str, tail: list[str]
) -> None:
    wn.write_worktree_env_ports(worktree, PORTS)

    assert guard.main([target], compose_dir=worktree) == 0

    [command] = ran.commands
    assert command[0] == sys.executable
    assert command[1 : 1 + len(tail)] == tail


@pytest.mark.parametrize(
    ("dotenv", "expected_port"),
    [
        (None, guard.COMPOSE_DEFAULT_APP_PORT),  # checkout principal: sem `.env`
        ("APP_PORT=\n", guard.COMPOSE_DEFAULT_APP_PORT),  # vazio é ausente, como no `:-`
        (f"APP_PORT={PORTS['APP_PORT']}\n", PORTS["APP_PORT"]),  # worktree paralela
    ],
)
def test_make_run_serves_on_the_checkout_app_port(
    worktree: Path,
    ran: _Ran,
    monkeypatch: pytest.MonkeyPatch,
    dotenv: str | None,
    expected_port: int,
) -> None:
    """A porta do `make run` é a `APP_PORT` do checkout, não a 8000 fixa."""
    monkeypatch.delenv("APP_PORT", raising=False)
    if dotenv is not None:
        (worktree / ".env").write_text(dotenv, encoding="utf-8")

    assert guard.main(["run"], compose_dir=worktree) == 0

    [command] = ran.commands
    assert command[-2:] == ["--port", str(expected_port)]


def test_app_port_from_the_environment_wins_over_the_dotenv(
    worktree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (worktree / ".env").write_text(f"APP_PORT={PORTS['APP_PORT']}\n", encoding="utf-8")
    monkeypatch.setenv("APP_PORT", "8999")

    assert guard.command_for("run", compose_dir=worktree)[-2:] == ["--port", "8999"]


def test_migrate_has_no_port(worktree: Path) -> None:
    assert "--port" not in guard.command_for("migrate", compose_dir=worktree)


def test_compose_default_app_port_mirrors_the_compose_file() -> None:
    compose = yaml.safe_load((_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["services"]["app"]["ports"] == [
        f"${{APP_PORT:-{guard.COMPOSE_DEFAULT_APP_PORT}}}:8000"
    ]
    assert wn.PORT_DEFAULTS["APP_PORT"] == guard.COMPOSE_DEFAULT_APP_PORT


def test_make_run_inside_the_app_container_serves_on_the_mapped_port() -> None:
    """No devcontainer, o `make run` sobe na porta do container, não na `APP_PORT` do host.

    O `env_file` do service `app` carrega o `.env` da worktree (`APP_PORT=8001`)
    para dentro do container, onde o mapeamento publica só a 8000: sem o
    `environment` fixando a `APP_PORT` na porta do container, o uvicorn do
    `make run` subiria numa porta que nada publica.
    """
    compose = yaml.safe_load((_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    app = compose["services"]["app"]
    container_port = app["ports"][0].rsplit(":", 1)[1]

    assert app["environment"]["APP_PORT"] == container_port


def test_make_target_returns_the_command_exit_code(worktree: Path, ran: _Ran) -> None:
    """Migration que falha reprova o `make migrate` — o exit code do Alembic passa adiante."""
    ran.returncode = COMMAND_FAILED

    assert guard.main(["migrate"], compose_dir=worktree) == COMMAND_FAILED


@pytest.mark.parametrize(
    "database_url",
    [
        # CI: URL por `env:` na 5432, sem `.env` nem `POSTGRES_PORT`
        _url("localhost:5432"),
        # devcontainer/compose: o service, que a regra não amarra
        _url("postgres:5432"),
        # produção: banco remoto
        _url("db.example.com:5432"),
    ],
)
def test_ci_compose_and_production_shapes_pass(
    worktree: Path, ran: _Ran, monkeypatch: pytest.MonkeyPatch, database_url: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)

    assert guard.main(["migrate"], compose_dir=worktree) == 0
    assert len(ran.commands) == 1


def test_ctrl_c_on_make_run_exits_quietly(worktree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupted(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        raise KeyboardInterrupt

    monkeypatch.setattr(guard.subprocess, "run", interrupted)

    assert guard.main(["run"], compose_dir=worktree) == SIGINT_EXIT


def test_unknown_target_is_a_usage_error(worktree: Path, ran: _Ran) -> None:
    with pytest.raises(SystemExit) as usage:
        guard.main(["upgrade"], compose_dir=worktree)

    assert usage.value.code == ARGPARSE_USAGE_EXIT
    assert ran.commands == []


def test_makefile_routes_migrate_and_run_through_the_guard() -> None:
    """Sem isto, a guarda existiria e o Makefile a contornaria."""
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    recipes: dict[str, list[str]] = {}
    current: str | None = None
    for line in makefile.splitlines():
        if line.startswith("\t") and current is not None:
            recipes[current].append(line.strip())
        elif line and not line.startswith(("#", " ")) and ":" in line:
            current = line.split(":", 1)[0]
            recipes[current] = []
        elif not line.startswith("\t"):
            current = None

    assert recipes["migrate"] == ["uv run python scripts/database_url_guard.py migrate"]
    assert recipes["run"] == ["uv run python scripts/database_url_guard.py run"]


def test_guard_script_refuses_end_to_end(tmp_path: Path) -> None:
    """O `make migrate` de verdade, sem o `make`: o processo sai com 1 antes do Alembic."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "POSTGRES_PORT"}
    }
    env["POSTGRES_PORT"] = str(PUBLISHED_PORT)
    env["DATABASE_URL"] = _url("localhost:5999")
    env["PYTHONIOENCODING"] = "utf-8"

    result = subprocess.run(
        [sys.executable, str(_GUARD), "migrate"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 1
    assert "A DATABASE_URL aponta para a porta 5999 de localhost" in result.stderr
    assert SECRET not in result.stderr
    assert "alembic" not in result.stdout.lower()

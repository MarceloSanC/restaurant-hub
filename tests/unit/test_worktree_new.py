"""Unit de `scripts/worktree-new.py` — o `.env` da worktree nasce coerente (issue #58).

O script copia o `.env` do checkout principal e desloca as portas do compose. A
app, porém, lê a URL inteira (`DATABASE_URL`), não a `POSTGRES_PORT`: deslocar só
a porta deixava a suíte da worktree no banco de outra frente — na Stage 4.1, 629
testes caíram com `ResolutionError: No such revision '0004'`, e a fixture de
schema teria recriado aquele banco. Os testes fixam a regra da reescrita:

- host loopback → só a porta muda, e o resto da URL fica byte a byte;
- outro host (`postgres` dentro da rede do compose, banco remoto) → intacto;
- chave ausente → a `DATABASE_URL` entra com o default do `Settings`, na porta da
  worktree; a `REDIS_URL`, que nada lê, nunca é acrescentada.

Git e GitHub ficam de fora: o fluxo de `main()` roda com eles substituídos, e o
resto (cópia do `.env`, escolha de porta, escrita) é o código real em `tmp_path`.
"""

from __future__ import annotations

import importlib.util
import io
import socket
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import pytest
from dotenv import dotenv_values

from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "worktree-new.py"

APP_PORT = 8008
POSTGRES_PORT = 5440
REDIS_PORT = 6387
PORTS = {"APP_PORT": APP_PORT, "POSTGRES_PORT": POSTGRES_PORT, "REDIS_PORT": REDIS_PORT}
URL_5432 = "postgresql+psycopg://user:pass@localhost:5432/restaurant_hub"
URL_WORKTREE = f"postgresql+psycopg://user:pass@localhost:{POSTGRES_PORT}/restaurant_hub"
HEADER = "# Portas e URLs auto-geradas para esta worktree paralela (scripts/worktree-new.py)"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worktree_new", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wn = _load()
# antes de a fixture `repo` o trocar: o teste do Docker parado usa o real
_REAL_DOCKER_RESERVED_PORTS = wn.docker_reserved_ports


def _write_env(directory: Path, *lines: str) -> Path:
    envfile = directory / ".env"
    envfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return envfile


def _env_lines(directory: Path) -> list[str]:
    return (directory / ".env").read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# url_with_port — a regra da reescrita
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (URL_5432, URL_WORKTREE),
        (
            "postgresql+psycopg://user:pass@127.0.0.1:5432/restaurant_hub",
            f"postgresql+psycopg://user:pass@127.0.0.1:{POSTGRES_PORT}/restaurant_hub",
        ),
        # 127.0.0.0/8 inteira é loopback, não só o .1
        (
            "postgresql+psycopg://user:pass@127.0.0.2:5432/restaurant_hub",
            f"postgresql+psycopg://user:pass@127.0.0.2:{POSTGRES_PORT}/restaurant_hub",
        ),
        (
            "postgresql+psycopg://user:pass@[::1]:5432/restaurant_hub",
            f"postgresql+psycopg://user:pass@[::1]:{POSTGRES_PORT}/restaurant_hub",
        ),
        # sem porta: a libpq iria à 5432 — a URL ganha a da worktree
        ("postgresql+psycopg://user:pass@localhost/restaurant_hub", URL_WORKTREE),
        (
            "postgresql+psycopg://user:pass@[::1]/restaurant_hub",
            f"postgresql+psycopg://user:pass@[::1]:{POSTGRES_PORT}/restaurant_hub",
        ),
        # host é case-insensitive; a grafia do original é preservada
        (
            "postgresql+psycopg://user:pass@LOCALHOST:5432/restaurant_hub",
            f"postgresql+psycopg://user:pass@LOCALHOST:{POSTGRES_PORT}/restaurant_hub",
        ),
        # credencial percent-encoded e query ficam byte a byte
        (
            "postgresql+psycopg://us%40er:p%3Ass%2Fw@localhost:5432/restaurant_hub?sslmode=disable",
            f"postgresql+psycopg://us%40er:p%3Ass%2Fw@localhost:{POSTGRES_PORT}"
            "/restaurant_hub?sslmode=disable",
        ),
        ("redis://:segredo@localhost/0", f"redis://:segredo@localhost:{POSTGRES_PORT}/0"),
    ],
)
def test_loopback_url_gets_only_the_port_swapped(url: str, expected: str) -> None:
    assert wn.url_with_port(url, POSTGRES_PORT) == expected


@pytest.mark.parametrize(
    "url",
    [
        # o service do compose: dentro da rede ele responde na 5432 do contêiner
        "postgresql+psycopg://user:pass@postgres:5432/restaurant_hub",
        "postgresql+psycopg://user:pass@db.example.com:5432/restaurant_hub",
        "postgresql+psycopg://user:pass@10.0.0.5:5432/restaurant_hub",
        # socket Unix: sem host na URL
        "postgresql+psycopg://user:pass@/restaurant_hub?host=/var/run/postgresql",
        # ilegíveis: ficam como estão, e a guarda da suíte responde por elas
        "postgresql+psycopg://user:pass@localhost:abc/restaurant_hub",
        "postgresql+psycopg://user:pass@localhost:70000/restaurant_hub",
        "postgresql+psycopg://user:pass@[::1/restaurant_hub",
        # tab no host: o urlsplit o descarta, e o netloc deixa de ser trecho literal
        "postgresql+psycopg://user:pass@local\thost:5432/restaurant_hub",
        "não é uma url",
        "",
    ],
)
def test_url_off_the_published_port_is_left_alone(url: str) -> None:
    assert wn.url_with_port(url, POSTGRES_PORT) is None


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
        ("192.168.0.10", False),
        ("localhost.example.com", False),
        ("", False),
        (None, False),
    ],
)
def test_is_loopback(host: str | None, expected: bool) -> None:
    assert wn.is_loopback(host) is expected


# ---------------------------------------------------------------------------
# write_worktree_env_ports — o .env que a worktree recebe
# ---------------------------------------------------------------------------


def test_absent_env_gets_ports_and_database_url(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """O caso medido: o checkout principal não tem `.env`, então não há o que copiar.

    Antes, o arquivo nascia só com as três portas, e o `Settings` caía no default
    5432 — o Postgres do checkout principal.
    """
    wn.write_worktree_env_ports(tmp_path, PORTS)

    assert _env_lines(tmp_path) == [
        HEADER,
        f"APP_PORT={APP_PORT}",
        f"POSTGRES_PORT={POSTGRES_PORT}",
        f"REDIS_PORT={REDIS_PORT}",
        f"DATABASE_URL={URL_WORKTREE}",
    ]
    assert f"DATABASE_URL acrescentada na porta {POSTGRES_PORT}" in capsys.readouterr().out


def test_commented_out_keys_are_left_alone(tmp_path: Path) -> None:
    """Linha comentada não é chave: fica como está, e a URL real entra no bloco."""
    commented = [f"# DATABASE_URL={URL_5432}", "#POSTGRES_PORT=5432"]
    _write_env(tmp_path, *commented)

    wn.write_worktree_env_ports(tmp_path, {"POSTGRES_PORT": POSTGRES_PORT})

    assert _env_lines(tmp_path) == [
        *commented,
        "",
        HEADER,
        f"POSTGRES_PORT={POSTGRES_PORT}",
        f"DATABASE_URL={URL_WORKTREE}",
    ]


def test_appended_database_url_is_the_settings_default() -> None:
    """A cópia do default no script não pode envelhecer em silêncio.

    O script roda sem o pacote instalado (`python scripts/worktree-new.py`), então
    não importa o `Settings` — guarda uma cópia, e este teste a cobra.
    """
    assert wn.URL_DEFAULTS["DATABASE_URL"] == Settings.model_fields["database_url"].default


def test_copied_env_is_rewritten_in_place(tmp_path: Path) -> None:
    _write_env(
        tmp_path,
        "# copiado do checkout principal",
        "DEBUG=true",
        f"DATABASE_URL={URL_5432}",
        "",
        "APP_PORT=8000",
        "POSTGRES_PORT=5432",
        "REDIS_PORT=6379",
    )

    wn.write_worktree_env_ports(tmp_path, PORTS)

    assert _env_lines(tmp_path) == [
        "# copiado do checkout principal",
        "DEBUG=true",
        f"DATABASE_URL={URL_WORKTREE}",
        "",
        f"APP_PORT={APP_PORT}",
        f"POSTGRES_PORT={POSTGRES_PORT}",
        f"REDIS_PORT={REDIS_PORT}",
    ]


def test_ports_present_but_url_absent_appends_only_the_url(tmp_path: Path) -> None:
    _write_env(tmp_path, "APP_PORT=8000", "POSTGRES_PORT=5432", "REDIS_PORT=6379")

    wn.write_worktree_env_ports(tmp_path, PORTS)

    assert _env_lines(tmp_path) == [
        f"APP_PORT={APP_PORT}",
        f"POSTGRES_PORT={POSTGRES_PORT}",
        f"REDIS_PORT={REDIS_PORT}",
        "",
        HEADER,
        f"DATABASE_URL={URL_WORKTREE}",
    ]


@pytest.mark.parametrize(
    "line",
    [
        f'DATABASE_URL="{URL_5432}"',
        f"DATABASE_URL='{URL_5432}'",
        f"DATABASE_URL={URL_5432}  # copiada do checkout principal",
        f'DATABASE_URL = "{URL_5432}" # com espaços e comentário',
    ],
)
def test_quoted_or_commented_url_is_read_like_dotenv(tmp_path: Path, line: str) -> None:
    _write_env(tmp_path, line)

    wn.write_worktree_env_ports(tmp_path, PORTS)

    assert f"DATABASE_URL={URL_WORKTREE}" in _env_lines(tmp_path)


def test_non_loopback_database_url_is_kept_and_not_duplicated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Devcontainer ou compose direto: a app fala com `postgres:5432`."""
    line = "DATABASE_URL=postgresql+psycopg://user:pass@postgres:5432/restaurant_hub"
    _write_env(tmp_path, line)

    wn.write_worktree_env_ports(tmp_path, PORTS)

    lines = _env_lines(tmp_path)
    assert line in lines
    assert [entry for entry in lines if entry.startswith("DATABASE_URL")] == [line]
    assert "DATABASE_URL mantida" in capsys.readouterr().out


def test_every_occurrence_of_a_duplicated_key_is_rewritten(tmp_path: Path) -> None:
    """O dotenv e o compose ficam com a ÚLTIMA ocorrência (medido nos dois).

    Reescrever só a primeira — o comportamento anterior para as portas — deixava
    a antiga valendo.
    """
    _write_env(
        tmp_path,
        "POSTGRES_PORT=5432",
        f"DATABASE_URL={URL_5432}",
        "POSTGRES_PORT=5433",
        "DATABASE_URL=postgresql+psycopg://user:pass@localhost:5433/restaurant_hub",
    )

    wn.write_worktree_env_ports(tmp_path, PORTS)

    lines = _env_lines(tmp_path)
    assert [entry for entry in lines if entry.startswith("POSTGRES_PORT")] == [
        f"POSTGRES_PORT={POSTGRES_PORT}"
    ] * 2
    assert [entry for entry in lines if entry.startswith("DATABASE_URL")] == [
        f"DATABASE_URL={URL_WORKTREE}"
    ] * 2


def test_export_prefixed_entries_are_rewritten_in_place(tmp_path: Path) -> None:
    """O python-dotenv lê `export CHAVE=valor` como `CHAVE`.

    Sem reconhecer o prefixo, o script não achava a URL, acrescentava o default
    do Settings no fim — que vencia por ser o último — e trocava usuário, senha
    e banco da worktree em silêncio.
    """
    _write_env(
        tmp_path,
        "export DATABASE_URL=postgresql+psycopg://app:s3cr3t@localhost:5432/mydb",
        "export	POSTGRES_PORT=5432",
        "exported_KEY=1",
    )

    wn.write_worktree_env_ports(tmp_path, PORTS)

    lines = _env_lines(tmp_path)
    assert lines[:3] == [
        f"export DATABASE_URL=postgresql+psycopg://app:s3cr3t@localhost:{POSTGRES_PORT}/mydb",
        f"export POSTGRES_PORT={POSTGRES_PORT}",
        "exported_KEY=1",
    ]
    assert not any("user:pass" in line for line in lines)
    assert dotenv_values(tmp_path / ".env")["DATABASE_URL"] == (
        f"postgresql+psycopg://app:s3cr3t@localhost:{POSTGRES_PORT}/mydb"
    )


def test_crlf_env_is_rewritten_without_carriage_returns(tmp_path: Path) -> None:
    """`.env` salvo no Windows: o `\\r` não pode vazar para o valor da URL."""
    (tmp_path / ".env").write_bytes(f"DATABASE_URL={URL_5432}\r\nPOSTGRES_PORT=5432\r\n".encode())

    wn.write_worktree_env_ports(tmp_path, PORTS)

    raw = (tmp_path / ".env").read_bytes().decode("utf-8")
    assert "\r\r" not in raw
    assert _env_lines(tmp_path)[:2] == [
        f"DATABASE_URL={URL_WORKTREE}",
        f"POSTGRES_PORT={POSTGRES_PORT}",
    ]
    assert dotenv_values(tmp_path / ".env")["DATABASE_URL"] == URL_WORKTREE


def test_bom_first_line_leaves_the_url_dotenv_reads_coherent(tmp_path: Path) -> None:
    """Com BOM, o python-dotenv lê a 1ª chave como `\\ufeffDATABASE_URL` — outra chave.

    O script a trata igual (não a reescreve) e acrescenta a `DATABASE_URL` no fim:
    a URL que a app de fato lê fica na porta da worktree.
    """
    (tmp_path / ".env").write_bytes(
        ("﻿" + f"DATABASE_URL={URL_5432}\nPOSTGRES_PORT=5432\n").encode()
    )

    wn.write_worktree_env_ports(tmp_path, PORTS)

    values = dotenv_values(tmp_path / ".env")
    assert values["DATABASE_URL"] == URL_WORKTREE
    assert values["POSTGRES_PORT"] == str(POSTGRES_PORT)


def test_redis_url_is_rewritten_when_present(tmp_path: Path) -> None:
    _write_env(tmp_path, "REDIS_URL=redis://localhost:6379/0")

    wn.write_worktree_env_ports(tmp_path, PORTS)

    assert f"REDIS_URL=redis://localhost:{REDIS_PORT}/0" in _env_lines(tmp_path)


def test_redis_url_is_never_appended(tmp_path: Path) -> None:
    """Nada no projeto lê uma URL de Redis — acrescentá-la seria ruído."""
    wn.write_worktree_env_ports(tmp_path, PORTS)

    assert not [entry for entry in _env_lines(tmp_path) if entry.startswith("REDIS_URL")]


def test_url_is_left_alone_when_its_port_is_not_assigned(tmp_path: Path) -> None:
    line = f"DATABASE_URL={URL_5432}"
    _write_env(tmp_path, line)

    wn.write_worktree_env_ports(tmp_path, {"APP_PORT": APP_PORT})

    assert _env_lines(tmp_path) == [line, "", HEADER, f"APP_PORT={APP_PORT}"]


def test_output_never_prints_the_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A URL carrega senha; o terminal mostra só chave e porta."""
    _write_env(tmp_path, "DATABASE_URL=postgresql+psycopg://user:s3gr3d0@localhost:5432/db")

    wn.write_worktree_env_ports(tmp_path, PORTS)

    out = capsys.readouterr().out
    assert f"DATABASE_URL reescrita na porta {POSTGRES_PORT}" in out
    assert "s3gr3d0" not in out


# ---------------------------------------------------------------------------
# main() — o fluxo com git e GitHub substituídos
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Checkout principal falso + outra worktree já registrada, com a 5433 tomada."""
    main_checkout = tmp_path / "restaurant-hub"
    other = tmp_path / "restaurant-hub-worktrees" / "feat-1-other"
    main_checkout.mkdir()
    other.mkdir(parents=True)
    _write_env(other, "APP_PORT=8001", "POSTGRES_PORT=5433", "REDIS_PORT=6380")

    def _create_worktree(_branch: str, _base: str, path: Path, _local: bool, _remote: bool) -> None:
        path.mkdir(parents=True)

    monkeypatch.setattr(wn, "git_top", lambda: main_checkout)
    monkeypatch.setattr(wn, "ensure_issue", lambda num, **_kwargs: num)
    monkeypatch.setattr(wn, "branch_exists", lambda _branch: (False, False))
    monkeypatch.setattr(wn, "create_worktree", _create_worktree)
    monkeypatch.setattr(wn, "_list_worktree_paths", lambda: [main_checkout, other])
    # host e Docker sem nada nas portas: os testes da sonda (issue #84) trocam estes dois
    monkeypatch.setattr(wn, "host_port_busy", lambda _port: False)
    monkeypatch.setattr(wn, "docker_reserved_ports", set)
    return main_checkout


def _run_main(monkeypatch: pytest.MonkeyPatch, *flags: str) -> None:
    argv = ["worktree-new.py", "chore/58-db-url", "--no-fetch", "--no-setup", "--no-vscode", *flags]
    monkeypatch.setattr(sys, "argv", argv)
    assert wn.main() == 0


def test_main_creates_worktree_whose_url_follows_its_port(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_env(repo, "DEBUG=true", f"DATABASE_URL={URL_5432}", "POSTGRES_PORT=5432")

    _run_main(monkeypatch)

    lines = _env_lines(repo.parent / "restaurant-hub-worktrees" / "chore-58-db-url")
    # a 5433 está na outra worktree; a primeira livre é a 5434
    assert "POSTGRES_PORT=5434" in lines
    assert "DATABASE_URL=postgresql+psycopg://user:pass@localhost:5434/restaurant_hub" in lines
    out = capsys.readouterr().out
    assert "docker compose up -d --wait postgres" in out
    assert "derruba também o Postgres desta worktree" in out
    assert "python scripts/worktree-rm.py chore/58-db-url --delete-remote" in out
    assert "git pull origin develop" in out


def test_main_without_port_assignment_keeps_the_copied_url(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = ["DEBUG=true", f"DATABASE_URL={URL_5432}", "POSTGRES_PORT=5432"]
    _write_env(repo, *lines)

    _run_main(monkeypatch, "--no-port-assign")

    assert _env_lines(repo.parent / "restaurant-hub-worktrees" / "chore-58-db-url") == lines


# ---------------------------------------------------------------------------
# setup_env — o venv da worktree, sem tocar nos hooks do git (issue #100)
# ---------------------------------------------------------------------------


def test_setup_runs_only_uv_sync_in_the_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O `make setup` reinstalava os hooks, que são de todas as worktrees, com o
    venv desta: removida ela, o commit das outras quebrava. Só o `uv sync` fica.
    """
    calls: list[tuple[list[str], Path | None]] = []
    monkeypatch.setattr(wn.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(wn, "_run", lambda cmd, *, cwd=None, **_kw: calls.append((cmd, cwd)))

    wn.setup_env(tmp_path)

    assert calls == [(["uv", "sync", "--extra", "dev"], tmp_path)]


def test_setup_without_uv_warns_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(wn.shutil, "which", lambda _name: None)
    monkeypatch.setattr(wn, "_run", lambda cmd, **_kw: calls.append(cmd))

    wn.setup_env(tmp_path)

    assert calls == []
    assert "`uv` não encontrado" in capsys.readouterr().err


def test_main_sets_up_the_new_worktree_unless_no_setup(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: list[Path] = []
    monkeypatch.setattr(wn, "setup_env", created.append)
    argv = ["worktree-new.py", "chore/100-hooks", "--no-fetch", "--no-vscode"]

    monkeypatch.setattr(sys, "argv", argv)
    assert wn.main() == 0
    assert created == [repo.parent / "restaurant-hub-worktrees" / "chore-100-hooks"]

    monkeypatch.setattr(sys, "argv", [*argv[:1], "chore/100-other", *argv[2:], "--no-setup"])
    assert wn.main() == 0
    assert len(created) == 1


# ---------------------------------------------------------------------------
# a porta ocupada fora dos `.env` — o Postgres órfão (issue #84)
# ---------------------------------------------------------------------------


def test_port_busy_on_the_host_is_skipped(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O Postgres de uma worktree removida segue publicando a 5434: nenhum `.env` a
    mostra, e a worktree nova a recebia.
    """
    monkeypatch.setattr(wn, "host_port_busy", lambda port: port in {5434, 8002})

    ports = wn.assign_worktree_ports(repo.parent / "restaurant-hub-worktrees" / "new")

    assert ports == {"APP_PORT": 8003, "POSTGRES_PORT": 5435, "REDIS_PORT": 6381}
    out = capsys.readouterr().out
    assert "POSTGRES_PORT: 5434 ocupada no host" in out
    assert "APP_PORT: 8002 ocupada no host" in out


def test_port_published_by_a_stopped_container_is_skipped(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Container parado não ocupa a porta agora, mas o `start` dele a toma de volta;
    a reserva vale para qualquer chave (a 6381 do Postgres de outro projeto também).
    """
    monkeypatch.setattr(wn, "docker_reserved_ports", lambda: {5434, 5435, 6381})
    probed: list[int] = []
    monkeypatch.setattr(wn, "host_port_busy", lambda port: probed.append(port) or False)

    ports = wn.assign_worktree_ports(repo.parent / "restaurant-hub-worktrees" / "new")

    assert ports == {"APP_PORT": 8002, "POSTGRES_PORT": 5436, "REDIS_PORT": 6382}
    assert probed == [8002, 5436, 6382]  # reservada nem chega à sonda
    assert "POSTGRES_PORT: 5434 reservada por um container" in capsys.readouterr().out


def test_ports_of_the_env_files_are_never_probed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probed: list[int] = []
    monkeypatch.setattr(wn, "host_port_busy", lambda port: probed.append(port) or False)

    wn.assign_worktree_ports(repo.parent / "restaurant-hub-worktrees" / "new")

    assert 5433 not in probed  # noqa: PLR2004 — a da outra worktree
    assert probed == [8002, 5434, 6381]


def test_no_free_port_in_range_fails(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wn, "host_port_busy", lambda _port: True)

    with pytest.raises(SystemExit):
        wn.assign_worktree_ports(repo.parent / "restaurant-hub-worktrees" / "new")


def test_docker_down_warns_and_still_assigns_by_env_and_probe(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Docker parado: nada publica porta agora, e a sonda basta para o presente; o que
    não se sabe são as portas dos containers parados — o aviso diz isso, em vez de
    o script fingir que conferiu.
    """

    def _down() -> set[int]:
        raise wn.worktree_docker.DockerUnavailable("failed to connect to the docker API")

    monkeypatch.setattr(wn, "docker_reserved_ports", _REAL_DOCKER_RESERVED_PORTS)
    monkeypatch.setattr(wn.worktree_docker, "published_host_ports", _down)
    monkeypatch.setattr(wn, "host_port_busy", lambda port: port == 5434)  # noqa: PLR2004

    ports = wn.assign_worktree_ports(repo.parent / "restaurant-hub-worktrees" / "new")

    assert ports["POSTGRES_PORT"] == 5435  # noqa: PLR2004
    err = capsys.readouterr().err
    assert "Docker indisponível (failed to connect to the docker API)" in err
    assert "não foram conferidas" in err
    assert "make worktree-orphans" in err


def test_docker_reserved_ports_passes_the_published_ports_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wn.worktree_docker, "published_host_ports", lambda: {5434})
    assert wn.docker_reserved_ports() == {5434}


def test_host_port_busy_sees_a_listening_socket() -> None:
    """Sonda real: um serviço ouvindo no loopback ocupa a porta; fechado, ela volta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert wn.host_port_busy(port) is True
    assert wn.host_port_busy(port) is False


def test_host_port_busy_sees_a_wildcard_bind() -> None:
    """O Docker publica em `0.0.0.0` — sem `listen`, só o bind de teste o vê."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("0.0.0.0", 0))
        port = server.getsockname()[1]
        assert wn.host_port_busy(port) is True


def test_host_port_busy_sees_a_bind_on_another_loopback_address() -> None:
    """Bind em `127.0.0.2`, sem `listen`: o connect no `127.0.0.1` é recusado, e no
    Windows só o `SO_EXCLUSIVEADDRUSE` faz o bind curinga da sonda falhar.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        try:
            server.bind(("127.0.0.2", 0))
        except OSError:
            pytest.skip("127.0.0.2 não é loopback neste sistema (macOS)")
        port = server.getsockname()[1]
        assert wn.host_port_busy(port) is True


class _FakeSocket:
    """Socket cujo bind sempre passa; o `connect_ex` responde `answer`."""

    answer = 0
    connects: ClassVar[list[tuple[str, int]]] = []
    timeouts: ClassVar[list[float]] = []

    def __init__(self, *_args: object) -> None:
        pass

    def __enter__(self) -> _FakeSocket:
        return self

    def __exit__(self, *_exc: object) -> None:
        pass

    def setsockopt(self, *_args: object) -> None:
        pass

    def bind(self, _addr: object) -> None:
        pass

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def connect_ex(self, addr: tuple[str, int]) -> int:
        self.connects.append(addr)
        return self.answer


@pytest.mark.parametrize(("answer", "busy"), [(0, True), (10061, False)])
def test_host_port_busy_counts_an_accepted_connection(
    monkeypatch: pytest.MonkeyPatch, answer: int, busy: bool
) -> None:
    """O bind de teste passa (serviço com `SO_REUSEADDR`, relay do WSL), mas o
    loopback aceita a conexão: a porta está ocupada.
    """
    monkeypatch.setattr(_FakeSocket, "answer", answer)
    monkeypatch.setattr(_FakeSocket, "connects", [])
    monkeypatch.setattr(_FakeSocket, "timeouts", [])
    monkeypatch.setattr(wn.socket, "socket", _FakeSocket)

    assert wn.host_port_busy(5434) is busy
    assert _FakeSocket.connects == [("127.0.0.1", 5434)]
    assert _FakeSocket.timeouts == [wn.CONNECT_PROBE_TIMEOUT]


def test_docker_reserved_ports_is_none_with_docker_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def _down() -> set[int]:
        raise wn.worktree_docker.DockerUnavailable("down")

    monkeypatch.setattr(wn.worktree_docker, "published_host_ports", _down)
    assert _REAL_DOCKER_RESERVED_PORTS() is None


def test_docker_reserved_ports_does_not_swallow_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _bug() -> set[int]:
        raise RuntimeError("bug")

    monkeypatch.setattr(wn.worktree_docker, "published_host_ports", _bug)
    with pytest.raises(RuntimeError):
        _REAL_DOCKER_RESERVED_PORTS()


# ---------------------------------------------------------------------------
# helpers de processo — `_run`, git e gh com o subprocess substituído
# ---------------------------------------------------------------------------

EXIT_VALIDATION = 1
EXIT_SUBPROCESS = 2
ISSUE_NUM = 42
CREATED_NUM = 77
FAILED_RC = 3


class _FakeRun:
    """`subprocess.run` falso: registra `(cmd, kwargs)` e devolve `returncode`/`stdout`."""

    def __init__(
        self, *, returncode: int = 0, stdout: str = "", exc: Exception | None = None
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.exc = exc
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((cmd, kwargs))
        if self.exc is not None:
            raise self.exc
        return subprocess.CompletedProcess(cmd, self.returncode, stdout=self.stdout, stderr="")


def test_run_echoes_the_command_and_forwards_the_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(stdout="ok")
    monkeypatch.setattr(wn.subprocess, "run", fake)

    cp = wn._run(["git", "status"], cwd=tmp_path, check=False)

    assert cp.stdout == "ok"
    assert fake.calls == [
        (
            ["git", "status"],
            {
                "cwd": str(tmp_path),
                "check": False,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "capture_output": False,
            },
        )
    ]
    assert capsys.readouterr().out == "  $ git status\n"


def test_run_captured_is_silent_and_without_cwd_passes_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun()
    monkeypatch.setattr(wn.subprocess, "run", fake)

    wn._run(["git", "rev-parse"], capture=True)

    assert fake.calls == [
        (
            ["git", "rev-parse"],
            {
                "cwd": None,
                "check": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "capture_output": True,
            },
        )
    ]
    assert capsys.readouterr().out == ""


def test_run_missing_executable_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(wn.subprocess, "run", _FakeRun(exc=FileNotFoundError("sem gh")))

    with pytest.raises(SystemExit) as exc:
        wn._run(["gh", "issue", "view"], capture=True)

    assert exc.value.code == EXIT_SUBPROCESS
    assert "ERRO: executável não encontrado: gh (sem gh)" in capsys.readouterr().err


def test_run_failed_command_with_capture_shows_its_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    error = subprocess.CalledProcessError(FAILED_RC, ["gh"], output="saida-x", stderr="erro-y")
    monkeypatch.setattr(wn.subprocess, "run", _FakeRun(exc=error))

    with pytest.raises(SystemExit) as exc:
        wn._run(["gh", "issue", "create"], capture=True)

    assert exc.value.code == EXIT_SUBPROCESS
    err = capsys.readouterr().err
    assert f"ERRO: comando falhou (exit {FAILED_RC}): gh issue create" in err
    assert "saida-x" in err
    assert "erro-y" in err


def test_run_failed_command_without_capture_does_not_repeat_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem captura, a saída já foi para o terminal; o erro não a repete."""
    error = subprocess.CalledProcessError(FAILED_RC, ["git"], output="saida-x", stderr="erro-y")
    monkeypatch.setattr(wn.subprocess, "run", _FakeRun(exc=error))

    with pytest.raises(SystemExit) as exc:
        wn._run(["git", "fetch"])

    assert exc.value.code == EXIT_SUBPROCESS
    err = capsys.readouterr().err
    assert f"comando falhou (exit {FAILED_RC}): git fetch" in err
    assert "saida-x" not in err
    assert "erro-y" not in err


def test_run_failed_command_with_capture_but_empty_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    error = subprocess.CalledProcessError(FAILED_RC, ["git"], output="", stderr="")
    monkeypatch.setattr(wn.subprocess, "run", _FakeRun(exc=error))

    with pytest.raises(SystemExit):
        wn._run(["git", "x"], capture=True)

    assert capsys.readouterr().err == f"ERRO: comando falhou (exit {FAILED_RC}): git x\n"


def test_force_utf8_stdio_reconfigures_only_non_utf8_text_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cp1252 = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    utf8 = io.TextIOWrapper(io.BytesIO(), encoding="UTF-8")
    monkeypatch.setattr(sys, "stdout", cp1252)
    monkeypatch.setattr(sys, "stderr", utf8)

    wn._force_utf8_stdio()

    assert cp1252.encoding == "utf-8"
    assert utf8.encoding == "UTF-8"  # já era UTF-8: nem tocado


class _NotAWrapper:
    encoding = "cp1252"


class _BrokenWrapper(io.TextIOWrapper):
    def reconfigure(self, **_kwargs: object) -> None:
        raise OSError("console não deixa")


def test_force_utf8_stdio_leaves_other_streams_and_swallows_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _NotAWrapper()
    broken = _BrokenWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", other)
    monkeypatch.setattr(sys, "stderr", broken)

    wn._force_utf8_stdio()

    assert other.encoding == "cp1252"
    assert broken.encoding == "cp1252"


def test_gh_available_without_gh_binary_skips_auth_check(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun()
    monkeypatch.setattr(wn.shutil, "which", lambda _name: None)
    monkeypatch.setattr(wn.subprocess, "run", fake)

    assert wn.gh_available() is False
    assert fake.calls == []


@pytest.mark.parametrize(("returncode", "expected"), [(0, True), (1, False)])
def test_gh_available_follows_auth_status(
    monkeypatch: pytest.MonkeyPatch, returncode: int, expected: bool
) -> None:
    fake = _FakeRun(returncode=returncode)
    looked_up: list[str] = []

    def _which(name: str) -> str:
        looked_up.append(name)
        return "/bin/gh"

    monkeypatch.setattr(wn.shutil, "which", _which)
    monkeypatch.setattr(wn.subprocess, "run", fake)

    assert wn.gh_available() is expected
    assert looked_up == ["gh"]
    assert [cmd for cmd, _kw in fake.calls] == [["gh", "auth", "status"]]
    assert fake.calls[0][1]["check"] is False
    assert fake.calls[0][1]["encoding"] == "utf-8"


@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    [
        (0, f'{{"number": {ISSUE_NUM}, "state": "OPEN"}}', True),
        (0, f'{{"number": {ISSUE_NUM}, "state": "CLOSED"}}', True),
        (0, '{"number": 7, "state": "OPEN"}', False),  # número divergente
        (0, '{"state": "OPEN"}', False),
        (0, "não é json", False),
        (1, f'{{"number": {ISSUE_NUM}}}', False),  # gh falhou: stdout nem é lido
    ],
)
def test_gh_issue_exists(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, expected: bool
) -> None:
    fake = _FakeRun(returncode=returncode, stdout=stdout)
    monkeypatch.setattr(wn.subprocess, "run", fake)

    assert wn.gh_issue_exists(ISSUE_NUM) is expected
    assert [cmd for cmd, _kw in fake.calls] == [
        ["gh", "issue", "view", str(ISSUE_NUM), "--json", "number,state"]
    ]
    assert fake.calls[0][1]["encoding"] == "utf-8"  # não o locale (issue #143)


class _FakeCapturedRun:
    """`_run` falso para `gh issue create`: registra a chamada e devolve `stdout`."""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="")


def test_gh_issue_create_returns_the_number_from_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCapturedRun(
        f"Creating issue in o/r\n\nhttps://github.com/o/r/issues/{CREATED_NUM}  \n"
    )
    monkeypatch.setattr(wn, "_run", fake)

    assert wn.gh_issue_create("feat: título", "corpo") == CREATED_NUM
    assert fake.calls == [
        (["gh", "issue", "create", "--title", "feat: título", "--body", "corpo"], {"capture": True})
    ]


@pytest.mark.parametrize(
    "last_line",
    ["https://github.com/o/r/pull/12", "https://github.com/o/r/issues/12/extra", "ok"],
)
def test_gh_issue_create_without_issue_url_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], last_line: str
) -> None:
    monkeypatch.setattr(wn, "_run", _FakeCapturedRun(f"linha\n{last_line}\n"))

    with pytest.raises(SystemExit) as exc:
        wn.gh_issue_create("t", "b")

    assert exc.value.code == EXIT_SUBPROCESS
    assert f"não foi possível extrair o número da issue criada: {last_line!r}" in (
        capsys.readouterr().err
    )


# ---------------------------------------------------------------------------
# git de verdade, num repositório em tmp_path
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repositório com um commit em `develop`; o cwd do processo vai para ele."""
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    principal = tmp_path / "principal"
    principal.mkdir()
    _git(principal, "init", "-q", "-b", "develop")
    _git(principal, "config", "user.name", "Teste")
    _git(principal, "config", "user.email", "teste@example.com")
    _git(principal, "config", "commit.gpgsign", "false")
    _git(principal, "commit", "-q", "--allow-empty", "--no-verify", "-m", "init")
    monkeypatch.chdir(principal)
    return principal


def test_git_top_from_a_subdirectory_is_the_checkout_root(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = git_repo / "a" / "b"
    sub.mkdir(parents=True)
    monkeypatch.chdir(sub)

    assert wn.git_top() == git_repo.resolve()


def test_git_common_dir_from_a_linked_worktree_is_the_main_git_dir(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert wn.git_common_dir() == (git_repo / ".git").resolve()

    linked = tmp_path / "linked"
    _git(git_repo, "worktree", "add", "-q", "-b", "feat/1-x", str(linked))
    monkeypatch.chdir(linked)

    assert wn.git_common_dir() == (git_repo / ".git").resolve()


def test_branch_exists_tells_local_from_remote(git_repo: Path) -> None:
    _git(git_repo, "branch", "feat/1-local")
    _git(git_repo, "update-ref", "refs/remotes/origin/feat/2-remote", "HEAD")

    assert wn.branch_exists("feat/1-local") == (True, False)
    assert wn.branch_exists("feat/2-remote") == (False, True)
    assert wn.branch_exists("feat/3-nada") == (False, False)


_REAL_SUBPROCESS_RUN = subprocess.run


def _windows_locale_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[object]:
    """`subprocess.run` de verdade, decodificando a saída como o Windows sem `encoding=`.

    Em `text=True` sem `encoding`, o Python decodifica pelo locale — no Windows,
    cp1252 — e o git escreve caminhos em UTF-8: `ç` vira `Ã§` (issue #143). O
    Linux do CI decodifica em UTF-8 e esconderia o defeito; aqui o processo roda
    em bytes e a decodificação segue o que a chamada pediu, com cp1252 no lugar
    do locale.
    """
    text = kwargs.pop("text", False)
    encoding = kwargs.pop("encoding", None)
    errors = kwargs.pop("errors", None)
    cp = _REAL_SUBPROCESS_RUN(cmd, **kwargs)  # type: ignore[call-overload]
    if not (text or encoding or errors):
        return cp  # type: ignore[no-any-return]

    def _decode(raw: bytes | None) -> str | None:
        if raw is None:
            return None
        return raw.decode(str(encoding or "cp1252"), str(errors or "strict"))

    return subprocess.CompletedProcess(
        cp.args, cp.returncode, _decode(cp.stdout), _decode(cp.stderr)
    )


NON_ASCII_DIR = "espaço çã"  # espaço e acento no caminho: o porcelain não cita nenhum dos dois
LINKED_APP_PORT = 8123


def test_list_worktree_paths_lists_main_and_linked(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / NON_ASCII_DIR
    _git(git_repo, "worktree", "add", "-q", "-b", "feat/1-x", str(linked))
    monkeypatch.setattr(wn.subprocess, "run", _windows_locale_run)

    paths = [p.resolve() for p in wn._list_worktree_paths()]

    assert paths == [git_repo.resolve(), linked.resolve()]


def test_collect_used_ports_reads_the_env_of_a_non_ascii_worktree(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caminho com acento: o `.env` da worktree é achado e a porta dela não volta (#143)."""
    linked = tmp_path / NON_ASCII_DIR
    _git(git_repo, "worktree", "add", "-q", "-b", "feat/1-x", str(linked))
    _write_env(linked, f"APP_PORT={LINKED_APP_PORT}")
    monkeypatch.setattr(wn.subprocess, "run", _windows_locale_run)

    assert wn._collect_used_ports()["APP_PORT"] == {8000, LINKED_APP_PORT}


def test_list_worktree_paths_outside_git_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun(returncode=128, stdout="worktree /nao/vale\n")
    monkeypatch.setattr(wn.subprocess, "run", fake)

    assert wn._list_worktree_paths() == []
    assert [cmd for cmd, _kw in fake.calls] == [["git", "worktree", "list", "--porcelain"]]


# ---------------------------------------------------------------------------
# _collect_used_ports — o que os `.env` das worktrees já tomam
# ---------------------------------------------------------------------------


def test_collect_used_ports_skips_noise_and_the_new_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one, new, no_env = tmp_path / "one", tmp_path / "new", tmp_path / "no-env"
    for d in (one, new, no_env):
        d.mkdir()
    _write_env(
        one,
        "",
        "# APP_PORT=8100",
        "SEM_IGUAL",
        "APP_PORT=8101  # comentário",
        "POSTGRES_PORT=abc",
        "REDIS_PORT=",
        "OUTRA=1",
    )
    _write_env(new, "APP_PORT=8200")
    monkeypatch.setattr(wn, "_list_worktree_paths", lambda: [one, new, no_env])

    used = wn._collect_used_ports(skip=new)

    assert used == {"APP_PORT": {8000, 8101}, "POSTGRES_PORT": {5432}, "REDIS_PORT": {6379}}


# `type(Path())` é `WindowsPath`/`PosixPath` conforme o SO: base dinâmica que o mypy recusa [misc].
class _UnresolvablePath(type(Path())):  # type: ignore[misc]
    """Worktree registrada cujo caminho não resolve mais (disco removido, permissão)."""

    def resolve(self, strict: bool = False) -> Path:
        raise OSError("caminho sumiu")


def test_collect_used_ports_ignores_worktrees_it_cannot_resolve_or_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gone = tmp_path / "gone"
    gone.mkdir()
    _write_env(gone, "APP_PORT=8300")
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    _write_env(unreadable, "APP_PORT=8400")
    readable = tmp_path / "readable"
    readable.mkdir()
    _write_env(readable, "APP_PORT=8500")
    monkeypatch.setattr(
        wn, "_list_worktree_paths", lambda: [_UnresolvablePath(gone), unreadable, readable]
    )
    real_read_text = Path.read_text

    def _read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.parent.name == "unreadable":
            raise OSError("sem permissão")
        # os `*args`/`**kwargs` chegam como `object`; o `read_text` real os tipa [arg-type].
        return real_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _read_text)

    used = wn._collect_used_ports(skip=tmp_path / "new")

    assert used["APP_PORT"] == {8000, 8500}


def test_collect_used_ports_without_skip_reads_every_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(tmp_path, "REDIS_PORT=6390")
    monkeypatch.setattr(wn, "_list_worktree_paths", lambda: [tmp_path])

    assert wn._collect_used_ports()["REDIS_PORT"] == {6379, 6390}


# ---------------------------------------------------------------------------
# a sonda sem `SO_EXCLUSIVEADDRUSE` (fora do Windows)
# ---------------------------------------------------------------------------


class _RecordingSocket(_FakeSocket):
    options: ClassVar[list[tuple[object, ...]]] = []

    def setsockopt(self, *args: object) -> None:
        self.options.append(args)


@pytest.mark.parametrize("has_exclusive", [True, False])
def test_host_port_busy_sets_exclusive_addr_only_where_it_exists(
    monkeypatch: pytest.MonkeyPatch, has_exclusive: bool
) -> None:
    monkeypatch.setattr(_RecordingSocket, "options", [])
    monkeypatch.setattr(_RecordingSocket, "connects", [])
    monkeypatch.setattr(_RecordingSocket, "timeouts", [])
    monkeypatch.setattr(_RecordingSocket, "answer", 1)
    monkeypatch.setattr(wn.socket, "socket", _RecordingSocket)
    exclusive = -5  # valor que nenhuma outra opção tem
    if has_exclusive:
        monkeypatch.setattr(wn.socket, "SO_EXCLUSIVEADDRUSE", exclusive, raising=False)
    else:
        monkeypatch.delattr(wn.socket, "SO_EXCLUSIVEADDRUSE", raising=False)

    assert wn.host_port_busy(5434) is False

    expected = [(wn.socket.SOL_SOCKET, exclusive, 1)] * 2 if has_exclusive else []
    assert _RecordingSocket.options == expected


# ---------------------------------------------------------------------------
# ensure_issue — o gate issue-first
# ---------------------------------------------------------------------------


class _Gh:
    """`gh` falso: disponível ou não, com as issues que existem e o número da criada."""

    def __init__(self, *, available: bool = True, existing: frozenset[int] = frozenset()) -> None:
        self.available = available
        self.existing = existing
        self.viewed: list[int] = []
        self.created: list[tuple[str, str]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> _Gh:
        monkeypatch.setattr(wn, "gh_available", lambda: self.available)
        monkeypatch.setattr(wn, "gh_issue_exists", self._exists)
        monkeypatch.setattr(wn, "gh_issue_create", self._create)
        return self

    def _exists(self, num: int) -> bool:
        self.viewed.append(num)
        return num in self.existing

    def _create(self, title: str, body: str) -> int:
        self.created.append((title, body))
        return CREATED_NUM


@pytest.mark.parametrize("title", [None, "feat: algo"])
def test_ensure_issue_without_gh_warns_and_goes_on(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], title: str | None
) -> None:
    gh = _Gh(available=False).install(monkeypatch)

    assert wn.ensure_issue(ISSUE_NUM, create_title=title, create_body=None) == ISSUE_NUM
    assert gh.viewed == []
    assert gh.created == []
    assert "AVISO: `gh` indisponível ou não autenticado" in capsys.readouterr().err


def test_ensure_issue_existing_issue_passes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = _Gh(existing=frozenset({ISSUE_NUM})).install(monkeypatch)

    assert wn.ensure_issue(ISSUE_NUM, create_title=None, create_body=None) == ISSUE_NUM
    assert gh.viewed == [ISSUE_NUM]
    assert f"issue #{ISSUE_NUM} OK" in capsys.readouterr().out


def test_ensure_issue_missing_issue_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = _Gh().install(monkeypatch)

    with pytest.raises(SystemExit) as exc:
        wn.ensure_issue(ISSUE_NUM, create_title=None, create_body=None)

    assert exc.value.code == EXIT_VALIDATION
    assert gh.viewed == [ISSUE_NUM]
    assert f"issue #{ISSUE_NUM} não encontrada no GitHub" in capsys.readouterr().err


def test_ensure_issue_without_number_and_without_create_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = _Gh().install(monkeypatch)

    with pytest.raises(SystemExit) as exc:
        wn.ensure_issue(0, create_title=None, create_body=None)

    assert exc.value.code == EXIT_VALIDATION
    assert gh.viewed == []
    assert "nome de branch sem número de issue" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("body", "expected_body"),
    [
        (None, "_criada via scripts/worktree-new.py_"),
        ("", "_criada via scripts/worktree-new.py_"),
        ("corpo próprio", "corpo próprio"),
    ],
)
def test_ensure_issue_creates_when_branch_has_no_number(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: str | None,
    expected_body: str,
) -> None:
    gh = _Gh().install(monkeypatch)

    assert wn.ensure_issue(0, create_title="feat: nova", create_body=body) == CREATED_NUM
    assert gh.created == [("feat: nova", expected_body)]
    assert gh.viewed == []  # a recém-criada não é revalidada
    assert f"issue criada: #{CREATED_NUM}" in capsys.readouterr().out


def test_ensure_issue_create_is_ignored_when_branch_has_a_number(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Com número no nome, `--create-issue` não cria nada — e a issue ainda é conferida."""
    gh = _Gh().install(monkeypatch)

    with pytest.raises(SystemExit) as exc:
        wn.ensure_issue(ISSUE_NUM, create_title="feat: nova", create_body=None)

    assert exc.value.code == EXIT_VALIDATION
    assert gh.created == []
    assert gh.viewed == [ISSUE_NUM]
    assert f"--create-issue ignorado: já há issue #{ISSUE_NUM}" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# nome do branch, path, `git worktree add`, cópia do `.env`, VS Code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("branch", "message"),
    [
        ("feat/1-" + "a" * wn.BRANCH_MAX_LEN, f"chars (limite {wn.BRANCH_MAX_LEN})"),
        ("feat/sem-numero", "nome de branch inválido: 'feat/sem-numero'"),
        ("feat/1-Maiuscula", "nome de branch inválido"),
        ("foo/1-bar", "tipo de branch inválido: 'foo'"),
    ],
)
def test_parse_branch_rejects(
    capsys: pytest.CaptureFixture[str], branch: str, message: str
) -> None:
    with pytest.raises(SystemExit) as exc:
        wn.parse_branch(branch)

    assert exc.value.code == EXIT_VALIDATION
    assert message in capsys.readouterr().err


def test_parse_branch_accepts_the_max_length() -> None:
    branch = "feat/1-" + "a" * (wn.BRANCH_MAX_LEN - len("feat/1-"))
    assert wn.parse_branch(branch)["full"] == branch


def test_parse_branch_decomposes_a_stage_branch() -> None:
    assert wn.parse_branch("feat/89-2-3-s3-adapter") == {
        "type": "feat",
        "num": "89",
        "stage": "2-3",
        "slug": "s3-adapter",
        "full": "feat/89-2-3-s3-adapter",
    }


@pytest.mark.parametrize(
    ("branch", "create_issue", "expected"),
    [
        ("feat/-add-foo", True, (0, True, "add-foo", "")),
        ("feat/-2-3-add-foo", True, (0, True, "add-foo", "2-3")),
        ("feat/42-add-foo", True, (ISSUE_NUM, False, "add-foo", "")),
        ("feat/42-add-foo", False, (ISSUE_NUM, False, "add-foo", "")),
    ],
)
def test_validate_branch_accepts_placeholder_only_in_create_mode(
    branch: str, create_issue: bool, expected: tuple[int, bool, str, str]
) -> None:
    parts, num, create_mode = wn._validate_branch(branch, create_issue=create_issue)
    assert (num, create_mode, parts["slug"], parts["stage"]) == expected


def test_validate_branch_placeholder_without_create_is_invalid() -> None:
    with pytest.raises(SystemExit):
        wn._validate_branch("feat/-add-foo", create_issue=False)


@pytest.mark.parametrize(
    ("stage", "expected"),
    [("", f"feat/{CREATED_NUM}-add-foo"), ("2-3", f"feat/{CREATED_NUM}-2-3-add-foo")],
)
def test_assemble_branch(stage: str, expected: str) -> None:
    parts = {"type": "feat", "slug": "add-foo", "stage": stage}
    assert wn._assemble_branch(parts, CREATED_NUM) == expected


@pytest.mark.parametrize(("branch_type", "base"), [("hotfix", "main"), ("feat", "develop")])
def test_default_base(branch_type: str, base: str) -> None:
    assert wn.default_base(branch_type) == base


def test_compute_worktree_path_default_is_beside_the_repo(tmp_path: Path) -> None:
    repo_root = tmp_path / "restaurant-hub"

    path = wn.compute_worktree_path(repo_root, "feat/42-add-foo", None)

    assert path == (tmp_path / "restaurant-hub-worktrees" / "feat-42-add-foo").resolve()
    assert wn.compute_worktree_path(repo_root, "feat/42-add-foo", "") == path


def test_compute_worktree_path_override_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    path = wn.compute_worktree_path(tmp_path / "repo", "feat/42-x", "outro/lugar")

    assert path == (tmp_path / "outro" / "lugar").resolve()


@pytest.mark.parametrize(
    ("local", "remote", "expected_cmd"),
    [
        (True, True, ["git", "worktree", "add", "{path}", "feat/42-x"]),
        (
            False,
            True,
            ["git", "worktree", "add", "--track", "-b", "feat/42-x", "{path}", "origin/feat/42-x"],
        ),
        (False, False, ["git", "worktree", "add", "-b", "feat/42-x", "{path}", "origin/develop"]),
    ],
)
def test_create_worktree_picks_the_add_form(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local: bool,
    remote: bool,
    expected_cmd: list[str],
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(wn, "_run", lambda cmd, **_kw: calls.append(cmd))
    path = tmp_path / "pai-novo" / "wt"

    wn.create_worktree("feat/42-x", "develop", path, local, remote)

    assert path.parent.is_dir()  # o pai é criado; a worktree, o git cria
    assert not path.exists()
    assert calls == [[str(path) if arg == "{path}" else arg for arg in expected_cmd]]


@pytest.mark.parametrize(
    ("present", "copied"),
    [((), []), ((".env",), [".env"]), ((".env", ".env.local"), [".env", ".env.local"])],
)
def test_copy_env_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    present: tuple[str, ...],
    copied: list[str],
) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / ".env.example").write_text("X=1\n", encoding="utf-8")
    for name in present:
        (src / name).write_text(f"{name}=conteúdo\n", encoding="utf-8")

    wn.copy_env_files(src, dst)

    assert sorted(p.name for p in dst.iterdir()) == copied
    for name in copied:
        assert (dst / name).read_text(encoding="utf-8") == f"{name}=conteúdo\n"
    out = capsys.readouterr().out
    assert [line for line in out.splitlines() if "copiado" in line] == [
        f"  • copiado {name}" for name in copied
    ]


def test_copy_env_files_skips_a_directory_named_env(tmp_path: Path) -> None:
    src, dst = tmp_path / "src", tmp_path / "dst"
    (src / ".env").mkdir(parents=True)
    dst.mkdir()

    wn.copy_env_files(src, dst)

    assert list(dst.iterdir()) == []


def test_open_vscode_without_code_prints_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(wn.shutil, "which", lambda _name: None)
    monkeypatch.setattr(wn, "_run", lambda cmd, **_kw: calls.append(cmd))

    wn.open_vscode(tmp_path)

    assert calls == []
    assert f"Abra manualmente:\n     {tmp_path}" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("found", "expected"),
    [
        ({"code": "/bin/code", "code.cmd": "/bin/code.cmd"}, "/bin/code"),
        ({"code.cmd": "C:/code.cmd"}, "C:/code.cmd"),
    ],
)
def test_open_vscode_opens_a_new_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, found: dict[str, str], expected: str
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(wn.shutil, "which", found.get)
    monkeypatch.setattr(wn, "_run", lambda cmd, **kw: calls.append((cmd, kw)))

    wn.open_vscode(tmp_path)

    assert calls == [([expected, "-n", str(tmp_path)], {"check": False})]


@pytest.mark.parametrize(("issue", "shown"), [(ISSUE_NUM, True), (0, False)])
def test_print_summary_shows_issue_only_when_known(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], issue: int, shown: bool
) -> None:
    wn._print_summary(branch="feat/42-x", path=tmp_path, issue=issue, base="main")

    out = capsys.readouterr().out
    assert (f"  ✓ Issue: #{issue}" in out) is shown
    assert "  ✓ Base: origin/main" in out
    assert "gh pr create --base main" in out


# ---------------------------------------------------------------------------
# main() — os trechos que o fluxo feliz não passa
# ---------------------------------------------------------------------------

_NEW_WT = ("restaurant-hub-worktrees", "chore-58-db-url")


def test_main_fetches_origin_unless_no_fetch(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(wn, "_run", lambda cmd, **_kw: calls.append(cmd))
    argv = ["worktree-new.py", "chore/58-db-url", "--no-setup", "--no-vscode"]
    monkeypatch.setattr(sys, "argv", argv)

    assert wn.main() == 0
    assert calls == [["git", "fetch", "--prune", "origin"]]


def test_main_create_issue_requires_a_title(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, "--create-issue")

    assert exc.value.code == EXIT_VALIDATION
    assert "--create-issue requer --issue-title" in capsys.readouterr().err
    assert not repo.parent.joinpath(*_NEW_WT).exists()


def test_main_create_issue_names_the_branch_with_the_new_number(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    received: list[tuple[int, dict[str, object]]] = []

    def _ensure(num: int, **kwargs: object) -> int:
        received.append((num, kwargs))
        return CREATED_NUM

    created: list[tuple[str, str]] = []

    def _create(branch: str, base: str, path: Path, _local: bool, _remote: bool) -> None:
        created.append((branch, base))
        path.mkdir(parents=True)

    monkeypatch.setattr(wn, "ensure_issue", _ensure)
    monkeypatch.setattr(wn, "create_worktree", _create)
    argv = [
        "worktree-new.py",
        "chore/-db-url",
        "--create-issue",
        "--issue-title",
        "chore: banco",
        "--issue-body",
        "corpo",
        "--no-fetch",
        "--no-setup",
        "--no-vscode",
        "--no-port-assign",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    assert wn.main() == 0
    final = f"chore/{CREATED_NUM}-db-url"
    assert received == [(0, {"create_title": "chore: banco", "create_body": "corpo"})]
    assert created == [(final, "develop")]
    assert repo.parent.joinpath("restaurant-hub-worktrees", f"chore-{CREATED_NUM}-db-url").is_dir()
    out = capsys.readouterr().out
    assert f"nome final do branch: {final}" in out
    assert f"✓ Issue: #{CREATED_NUM}" in out


def test_main_title_without_create_issue_is_not_passed_on(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    received: list[dict[str, object]] = []

    def _ensure(num: int, **kwargs: object) -> int:
        received.append(kwargs)
        return num

    monkeypatch.setattr(wn, "ensure_issue", _ensure)

    _run_main(monkeypatch, "--issue-title", "chore: x", "--no-port-assign")

    assert received == [{"create_title": None, "create_body": None}]
    assert "nome final do branch" not in capsys.readouterr().out


def test_main_hotfix_branches_from_main(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bases: list[str] = []

    def _create(_branch: str, base: str, path: Path, _local: bool, _remote: bool) -> None:
        bases.append(base)
        path.mkdir(parents=True)

    monkeypatch.setattr(wn, "create_worktree", _create)
    flags = ["--no-fetch", "--no-setup", "--no-vscode", "--no-port-assign"]
    monkeypatch.setattr(sys, "argv", ["worktree-new.py", "hotfix/9-prod", *flags])
    assert wn.main() == 0
    monkeypatch.setattr(
        sys, "argv", ["worktree-new.py", "hotfix/10-prod", *flags, "--base", "develop"]
    )
    assert wn.main() == 0

    assert bases == ["main", "develop"]


def test_main_passes_branch_existence_to_create_worktree(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[str, bool, bool]] = []
    queried: list[str] = []

    def _create(branch: str, _base: str, path: Path, local: bool, remote: bool) -> None:
        seen.append((branch, local, remote))
        path.mkdir(parents=True)

    def _exists(branch: str) -> tuple[bool, bool]:
        queried.append(branch)
        return False, True

    monkeypatch.setattr(wn, "branch_exists", _exists)
    monkeypatch.setattr(wn, "create_worktree", _create)

    _run_main(monkeypatch, "--no-port-assign")

    assert queried == ["chore/58-db-url"]
    assert seen == [("chore/58-db-url", False, True)]


def test_main_refuses_an_existing_path(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    existing = repo.parent.joinpath(*_NEW_WT)
    existing.mkdir(parents=True)
    created: list[str] = []
    monkeypatch.setattr(wn, "create_worktree", lambda branch, *_a: created.append(branch))

    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch)

    assert exc.value.code == EXIT_VALIDATION
    assert f"path já existe: {existing.resolve()}" in capsys.readouterr().err
    assert created == []


def test_main_no_env_does_not_copy_the_main_env(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(repo, "DEBUG=true", f"DATABASE_URL={URL_5432}")

    _run_main(monkeypatch, "--no-env")

    lines = _env_lines(repo.parent.joinpath(*_NEW_WT))
    assert "DEBUG=true" not in lines
    assert lines[0] == HEADER


def test_main_no_env_and_no_port_assign_leaves_no_env_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(repo, "DEBUG=true")

    _run_main(monkeypatch, "--no-env", "--no-port-assign")

    assert not repo.parent.joinpath(*_NEW_WT, ".env").exists()


def test_main_opens_vscode_unless_no_vscode(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Path] = []
    monkeypatch.setattr(wn, "open_vscode", opened.append)
    flags = ["--no-fetch", "--no-setup", "--no-port-assign"]
    monkeypatch.setattr(sys, "argv", ["worktree-new.py", "chore/58-db-url", *flags])

    assert wn.main() == 0
    assert opened == [repo.parent.joinpath(*_NEW_WT).resolve()]

    monkeypatch.setattr(sys, "argv", ["worktree-new.py", "chore/59-other", *flags, "--no-vscode"])
    assert wn.main() == 0
    assert len(opened) == 1

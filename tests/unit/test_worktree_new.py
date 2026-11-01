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
import sys
from pathlib import Path
from types import ModuleType

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
    assert "docker compose down -v" in out
    assert "python scripts/worktree-rm.py chore/58-db-url" in out


def test_main_without_port_assignment_keeps_the_copied_url(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines = ["DEBUG=true", f"DATABASE_URL={URL_5432}", "POSTGRES_PORT=5432"]
    _write_env(repo, *lines)

    _run_main(monkeypatch, "--no-port-assign")

    assert _env_lines(repo.parent / "restaurant-hub-worktrees" / "chore-58-db-url") == lines

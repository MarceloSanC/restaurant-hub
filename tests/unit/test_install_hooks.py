"""Unit de `scripts/install_hooks.py` — só o checkout principal instala os hooks (issue #100).

Os hooks do git moram no diretório comum, um só para todas as worktrees, e o
`pre-commit install` grava neles o python que o rodou. Instalado de dentro de uma
worktree, o hook passava a depender do venv dela; removida a worktree, todo
commit de toda worktree falhava com "`pre-commit` not found". Os testes fixam:

- no checkout principal, o `INSTALL_PYTHON` gravado é o python do processo;
- numa worktree, o hook fica byte a byte como estava — e o script acusa (exit 1)
  hook cujo python sumiu, com o comando de religar;
- o ciclo inteiro: worktree criada, "setup" rodado nela, worktree removida, e o
  commit numa outra worktree passa pelos hooks.

Git é real, num repositório em `tmp_path`; o `pre-commit` é o do venv da suíte,
com `PRE_COMMIT_HOME` também em `tmp_path` (não suja o cache do usuário).
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_hooks.py"

# Um hook `local`/`system` de cada tipo, como os do `.pre-commit-config.yaml` do
# projeto: o framework roda com o `INSTALL_PYTHON`; o hook, com o comando do
# `entry` — aqui o python da suíte, por caminho, para não depender do PATH.
_PY = shlex.quote(Path(sys.executable).as_posix())
_CONFIG = f"""\
repos:
  - repo: local
    hooks:
      - id: marca-pre-commit
        name: marca-pre-commit
        entry: {_PY} -c "open('pre-commit-rodou', 'w').close()"
        language: system
        pass_filenames: false
        always_run: true
      - id: marca-commit-msg
        name: marca-commit-msg
        entry: {_PY} -c "open('commit-msg-rodou', 'w').close()"
        language: system
        pass_filenames: false
        always_run: true
        stages: [commit-msg]
"""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("install_hooks", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ih = _load()


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _hook(principal: Path, hook_type: str = "pre-commit") -> Path:
    return principal / ".git" / "hooks" / hook_type


def _write_hook(principal: Path, hook_type: str, python: Path | str) -> Path:
    hook = _hook(principal, hook_type)
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/usr/bin/env bash\n# start templated\n"
        f"INSTALL_PYTHON={shlex.quote(str(python))}\n"
        "ARGS=(hook-impl)\n# end templated\n",
        encoding="utf-8",
    )
    return hook


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Checkout principal com um commit e o `.pre-commit-config.yaml` de teste.

    O ambiente do git que chama a suíte (um hook rodando o pytest, por exemplo)
    não pode vazar para o repositório temporário.
    """
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PRE_COMMIT_HOME", str(tmp_path / "pre-commit-home"))
    principal = tmp_path / "restaurant-hub"
    principal.mkdir()
    for args in (
        ("init", "-q", "-b", "develop"),
        ("config", "user.name", "Teste"),
        ("config", "user.email", "teste@example.com"),
        ("config", "core.autocrlf", "false"),
    ):
        assert _git(principal, *args).returncode == 0
    (principal / ".pre-commit-config.yaml").write_text(_CONFIG, encoding="utf-8")
    assert _git(principal, "add", ".").returncode == 0
    assert _git(principal, "commit", "-q", "-m", "inicial").returncode == 0
    return principal


def _worktree(principal: Path, name: str) -> Path:
    path = principal.parent / "restaurant-hub-worktrees" / name
    cp = _git(principal, "worktree", "add", "-q", "-b", name, str(path))
    assert cp.returncode == 0, cp.stderr
    return path


# ---------------------------------------------------------------------------
# hook_python — a leitura do INSTALL_PYTHON
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "python",
    [
        r"C:\Users\Marcelo\Documents\Code\restaurant-hub\.venv\Scripts\python.exe",
        "/home/dev/restaurant hub/.venv/bin/python",
        "/app/.venv/bin/python",
    ],
)
def test_hook_python_reads_the_quoted_path_back(tmp_path: Path, python: str) -> None:
    hook = _write_hook(tmp_path, "pre-commit", python)

    assert ih.hook_python(hook) == Path(python)


def test_hook_python_is_none_without_hook_or_without_the_line(tmp_path: Path) -> None:
    assert ih.hook_python(tmp_path / "ausente") is None
    alheio = tmp_path / "alheio"
    alheio.write_text("#!/bin/sh\nexec make lint\n", encoding="utf-8")
    assert ih.hook_python(alheio) is None
    assert ih.hook_python(_write_hook(tmp_path, "vazio", "")) is None


def test_dead_hooks_lists_only_the_missing_python(tmp_path: Path) -> None:
    common = tmp_path / ".git"
    _write_hook(tmp_path, "pre-commit", sys.executable)
    _write_hook(tmp_path, "commit-msg", tmp_path / "sumiu" / "python.exe")

    assert ih.dead_hooks(common) == [("commit-msg", tmp_path / "sumiu" / "python.exe")]


# ---------------------------------------------------------------------------
# main() — principal instala, worktree não toca
# ---------------------------------------------------------------------------


def test_main_checkout_installs_both_hooks_with_its_own_python(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(repo)

    assert ih.main() == 0

    for hook_type in ih.HOOK_TYPES:
        assert ih.hook_python(_hook(repo, hook_type)) == Path(sys.executable)


def test_git_dirs_tell_the_main_checkout_from_a_worktree(repo: Path) -> None:
    wt = _worktree(repo, "feat-1-a")

    git_dir, common = ih.git_dirs(repo)
    wt_git_dir, wt_common = ih.git_dirs(wt)

    assert git_dir == common == (repo / ".git").resolve()
    assert wt_common == common
    assert wt_git_dir != wt_common
    assert ih.main_checkout(wt_common) == repo.resolve()


def test_worktree_leaves_the_shared_hooks_untouched(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hooks = [_write_hook(repo, hook_type, sys.executable) for hook_type in ih.HOOK_TYPES]
    before = [hook.read_bytes() for hook in hooks]
    monkeypatch.chdir(_worktree(repo, "feat-1-a"))

    assert ih.main() == 0

    assert [hook.read_bytes() for hook in hooks] == before
    assert "nada a instalar" in capsys.readouterr().out


def test_worktree_flags_a_hook_whose_python_is_gone(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gone = repo.parent / "restaurant-hub-worktrees" / "removida" / ".venv" / "python"
    hook = _write_hook(repo, "pre-commit", gone)
    before = hook.read_bytes()
    monkeypatch.chdir(_worktree(repo, "feat-1-a"))

    assert ih.main() == ih.EXIT_DEAD_HOOK

    assert hook.read_bytes() == before
    err = capsys.readouterr().err
    assert str(gone) in err
    assert ih.RELINK_HINT in err


def test_main_outside_a_repository_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    fora = tmp_path / "fora"
    fora.mkdir()
    monkeypatch.chdir(fora)

    assert ih.main() == ih.EXIT_ERROR
    assert "repositório git" in capsys.readouterr().err


def test_failed_install_exits_2(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setattr(ih, "install", lambda _cwd: 1)

    assert ih.main() == ih.EXIT_ERROR


# ---------------------------------------------------------------------------
# O ciclo da issue: setup numa worktree, remoção, commit em outra
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("git") is None, reason="precisa do git")
def test_removing_a_worktree_keeps_the_commits_of_the_others(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O critério de aceite: depois de criar e remover uma worktree, o hook aponta
    para um python que existe, e o commit numa outra worktree passa pelos hooks.

    `PATH` sem `pre-commit`: com ele, o hook cairia no fallback do PATH e o teste
    passaria mesmo com o `INSTALL_PYTHON` morto — foi assim que o defeito ficou
    escondido nas máquinas com o pre-commit global.
    """
    monkeypatch.chdir(repo)
    assert ih.main() == 0
    saindo = _worktree(repo, "feat-1-saindo")
    outra = _worktree(repo, "feat-2-outra")

    monkeypatch.chdir(saindo)
    assert ih.main() == 0  # o "make setup" dentro da worktree que vai sair
    monkeypatch.chdir(repo)
    assert _git(repo, "worktree", "remove", "--force", str(saindo)).returncode == 0

    assert ih.dead_hooks((repo / ".git").resolve()) == []
    (outra / "arquivo.txt").write_text("x\n", encoding="utf-8")
    assert _git(outra, "add", "arquivo.txt").returncode == 0
    path = os.pathsep.join(
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry
        and not (Path(entry) / "pre-commit").exists()
        and not (Path(entry) / "pre-commit.exe").exists()
    )
    cp = subprocess.run(
        ["git", "commit", "-q", "-m", "na outra worktree"],
        cwd=outra,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": path},
    )

    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert (outra / "pre-commit-rodou").exists()
    assert (outra / "commit-msg-rodou").exists()


# ---------------------------------------------------------------------------
# Contrato: exit codes, comando do install e a ligação no `make setup`
# ---------------------------------------------------------------------------


def test_exit_codes_are_the_documented_ones() -> None:
    """A docstring e o GIT-WORKFLOW prometem 0/1/2; quem chama distingue hook morto
    (1, religar no principal) de erro de git ou do pre-commit (2).
    """
    assert (ih.EXIT_OK, ih.EXIT_DEAD_HOOK, ih.EXIT_ERROR) == (0, 1, 2)


def test_install_runs_pre_commit_for_both_hook_types_in_the_given_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[list[str], str]] = []

    def _fake_run(cmd: list[str], *, cwd: str, check: bool) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ih.subprocess, "run", _fake_run)

    assert ih.install(tmp_path) == 0
    assert calls == [
        (
            [
                sys.executable,
                *("-m", "pre_commit", "install", "--install-hooks"),
                *("--hook-type", "pre-commit", "--hook-type", "commit-msg"),
            ],
            str(tmp_path),
        )
    ]


def test_unexpected_git_output_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`rev-parse` com uma linha só (git antigo sem `--path-format`, por exemplo)."""
    monkeypatch.setattr(
        ih.subprocess,
        "run",
        lambda cmd, **_kw: subprocess.CompletedProcess(cmd, 0, stdout="/repo/.git\n"),
    )

    assert ih.main() == ih.EXIT_ERROR
    assert "repositório git" in capsys.readouterr().err


def test_make_setup_installs_hooks_only_through_the_script() -> None:
    """A linha que causava a issue: `pre-commit install` direto no `make setup`
    reescrevia os hooks de todas as worktrees com o venv de quem o rodava.
    """
    makefile = Path(__file__).resolve().parents[2] / "Makefile"
    lines = makefile.read_text(encoding="utf-8").splitlines()
    recipe: list[str] = []
    for line in lines[lines.index("setup:") + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip())

    assert "uv run python scripts/install_hooks.py" in recipe
    assert not [cmd for cmd in recipe if "pre-commit install" in cmd]

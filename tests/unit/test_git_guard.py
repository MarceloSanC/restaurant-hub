"""Unit do hook `.claude/hooks/git_guard.py`.

A decisão roda com git e sistema de arquivos injetados, sem I/O; só as duas
consultas ao git (`is_main_worktree`, `branch_exists`) usam um repositório real em
`tmp_path` (issue #91).
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "git_guard.py"
MAIN = Path("/repo").resolve()
WORKTREE = Path("/repo-worktrees/feat-1").resolve()
LOCAL_BRANCHES = {
    "develop",
    "feat/55-4-1-scheduling-domain",
    "feat/57-remote-only",
}  # local ou remota


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("git_guard", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gg = _load()


def _blocked(command: str, cwd: Path = MAIN) -> bool:
    return bool(
        gg.blocked(
            command,
            cwd,
            is_main=lambda p: p == MAIN,
            exists=lambda _p, name: name in LOCAL_BRANCHES,
        )
    )


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b feat/99-x",
        "git switch -c feat/99-x",
        "git switch --create feat/99-x",
        "git switch feat/55-4-1-scheduling-domain",
        "git checkout feat/55-4-1-scheduling-domain",
        "git worktree add ../x feat/99-x",
        "git checkout feat/57-remote-only",
        "git checkout --track origin/feat/57-remote-only",
        "git checkout -t origin/feat/57-remote-only",
        "git switch -",
        "git checkout -",
        "git status && git checkout -b feat/99-x",
        f"git -C {MAIN} switch -c feat/99-x",
    ],
)
def test_blocks_branch_changes_in_main_checkout(command: str) -> None:
    assert _blocked(command)


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git checkout develop",
        "git switch develop",
        "git checkout -- src/restaurant_hub/main.py",
        "git checkout src/restaurant_hub/main.py",
        "git log --oneline -5",
        "python scripts/worktree-new.py feat/99-x --no-vscode",
    ],
)
def test_allows_safe_commands_in_main_checkout(command: str) -> None:
    assert not _blocked(command)


def test_allows_branch_work_inside_a_worktree() -> None:
    assert not _blocked("git checkout -b feat/99-x", cwd=WORKTREE)
    assert not _blocked(f"git -C {WORKTREE} switch -c feat/99-x")
    assert not _blocked(f"cd {WORKTREE} && git switch -c feat/99-x")


# --- borda: o git real, a quebra de tokens e o `main()` do hook (issue #91) ---


def _git_real(cwd: Path, *args: str) -> None:
    cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert cp.returncode == 0, cp.stderr


@pytest.fixture
def real_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Checkout principal real, com a branch `feat/1-a` presa a uma worktree."""
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    principal = tmp_path / "principal"
    principal.mkdir()
    _git_real(principal, "init", "-q", "-b", "develop")
    _git_real(principal, "config", "user.name", "Teste")
    _git_real(principal, "config", "user.email", "teste@example.com")
    _git_real(principal, "commit", "-q", "--allow-empty", "-m", "inicial")
    worktree = tmp_path / "wt"
    _git_real(principal, "worktree", "add", "-q", "-b", "feat/1-a", str(worktree))
    return principal, worktree


def test_is_main_worktree_against_real_git(real_repo: tuple[Path, Path], tmp_path: Path) -> None:
    principal, worktree = real_repo
    fora = tmp_path / "fora"
    fora.mkdir()
    assert gg.is_main_worktree(principal) is True
    assert gg.is_main_worktree(worktree) is False
    assert gg.is_main_worktree(fora / "nao-existe") is False


def test_branch_exists_against_real_git(real_repo: tuple[Path, Path]) -> None:
    principal, _ = real_repo
    assert gg.branch_exists(principal, "feat/1-a") is True
    assert gg.branch_exists(principal, "feat/2-nao-existe") is False


def test_git_helper_returns_none_when_git_cannot_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def _sem_git(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(gg.subprocess, "run", _sem_git)
    assert gg._git(MAIN, "status") is None
    assert gg.is_main_worktree(MAIN) is False


def test_unbalanced_quote_still_splits_on_whitespace() -> None:
    """Aspa sem par não derruba o hook: o segmento é quebrado por espaço."""
    assert _blocked('git checkout -b feat/99-x "sem-fechar')


def test_relative_cd_moves_the_target_out_of_the_main_checkout() -> None:
    assert not _blocked("cd ../repo-worktrees/feat-1 && git switch -c feat/99-x")


def _stdin(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))


def test_main_denies_blocked_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, Path]] = []

    def _always(command: str, cwd: Path) -> bool:
        seen.append((command, cwd))
        return True

    monkeypatch.setattr(gg, "blocked", _always)
    payload = {"tool_input": {"command": "git checkout -b feat/99-x"}, "cwd": str(MAIN)}
    _stdin(monkeypatch, json.dumps(payload).encode("utf-8"))

    assert gg.main() == 0

    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert out["hookSpecificOutput"]["permissionDecisionReason"] == gg.REASON
    assert seen == [("git checkout -b feat/99-x", MAIN)]


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"tool_input": {"command": "git status"}, "cwd": "."}).encode("utf-8"),
        json.dumps({"tool_input": {}}).encode("utf-8"),
        b"nao e json",
        b"\xff\xfe",
    ],
    ids=["permitido", "sem-comando", "json-invalido", "utf8-invalido"],
)
def test_main_stays_silent_otherwise(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], raw: bytes
) -> None:
    monkeypatch.setattr(gg, "blocked", lambda _command, _cwd: False)
    _stdin(monkeypatch, raw)
    assert gg.main() == 0
    assert capsys.readouterr().out == ""


def test_empty_segment_and_dangling_option_are_skipped() -> None:
    """Segmento vazio (`;;`) e `-C` sem valor no fim não quebram a varredura."""
    assert _blocked("git status ;; git checkout -b feat/99-x")
    assert not _blocked("git -C")

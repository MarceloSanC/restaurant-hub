"""Unit do hook `.claude/hooks/git_guard.py`.

A decisão roda com git e sistema de arquivos injetados, sem I/O; só as duas
consultas ao git (`is_main_worktree`, `branch_exists`) usam um repositório real em
`tmp_path` (issue #91).
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
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
    if str(_HOOK.parent) not in sys.path:  # o hook importa o helper vizinho `_shell_segments`
        sys.path.insert(0, str(_HOOK.parent))
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


# --- separadores e grupos escondendo o git (issue #65, port da FF#183) ---


@pytest.mark.parametrize(
    "command",
    [
        "git status || git checkout -b feat/99-x",
        "git status; git checkout -b feat/99-x",
        "git log | git checkout -b feat/99-x",
        "git status\ngit checkout -b feat/99-x",
        "git status\r\ngit checkout -b feat/99-x",
        "git status & git checkout -b feat/99-x",
        "& git checkout -b feat/99-x",
        "& 'C:\\Program Files\\Git\\bin\\git.exe' checkout -b feat/99-x",
        "(git checkout -b feat/99-x)",
        "( git checkout -b feat/99-x )",
        "{ git checkout -b feat/99-x; }",
        "$(git switch -c feat/99-x)",
        "FOO=1 git switch -c feat/99-x",
        "if true; then git switch -c feat/99-x; fi",
        "git status\n(git switch feat/55-4-1-scheduling-domain)",
        # checkout de branch existente casa pelo nome exato: `)` colado ou solto não pode vazar
        "(git checkout feat/55-4-1-scheduling-domain)",
        "( git checkout feat/55-4-1-scheduling-domain )",
        "{ git checkout feat/55-4-1-scheduling-domain;}",
    ],
)
def test_blocks_branch_change_after_any_separator(command: str) -> None:
    assert _blocked(command)


@pytest.mark.parametrize(
    "command",
    [
        "(git checkout develop)",
        "( git switch develop )",
        "git status\ngit log -1 & git diff",
        "{ git checkout -- src/restaurant_hub/main.py; }",
    ],
)
def test_groups_and_new_separators_do_not_create_false_positives(command: str) -> None:
    assert not _blocked(command)


def test_cd_to_worktree_on_a_previous_line_is_honored() -> None:
    assert not _blocked(f"cd {WORKTREE}\ngit switch -c feat/99-x")
    assert _blocked(f"cd {WORKTREE}\ncd {MAIN}\ngit switch -c feat/99-x")


@pytest.mark.parametrize(
    "command",
    [
        f"(cd {WORKTREE}) ; git checkout -b feat/99-x",
        f"(cd {WORKTREE} && git status); git checkout -b feat/99-x",
        f"pushd {WORKTREE}; popd; git checkout -b feat/99-x",
        "if ($true) { git checkout -b feat/99-x }",
        "if (Test-Path x) { git switch -c feat/99-x }",
        "foreach ($b in 'x') { git checkout -b feat/99-x }",
    ],
)
def test_subshell_cd_and_powershell_blocks_do_not_hide_the_branch_change(command: str) -> None:
    assert _blocked(command)


def test_uses_the_shared_segmentation_helper() -> None:
    import _shell_segments  # noqa: PLC0415 — carregado do mesmo diretório que o git_guard

    assert gg.commands is _shell_segments.commands
    assert gg.git_invocation is _shell_segments.git_invocation


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


# --- processo real, como o Claude Code chama o hook (issue #65) ---

# GIT_DIR/GIT_WORK_TREE herdados apontariam o git para o repo real
_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


@pytest.fixture
def main_checkout(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True, env=_ENV)
    return tmp_path


def _run_hook(payload: str) -> subprocess.CompletedProcess[str]:
    """`python <hook>.py` com o payload no stdin: o helper vizinho `_shell_segments` resolve
    pelo diretório do script, sem o sys.path do pytest."""
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=60,
        env=_ENV,
    )


@pytest.mark.parametrize(
    "command",
    [
        "git status\ngit checkout -b feat/99-x",
        "git status & git switch -c feat/99-x",
        "(git checkout -b feat/99-x)",
        "if ($true) { git checkout -b feat/99-x }",
    ],
)
def test_process_denies_branch_creation_on_a_later_segment(
    main_checkout: Path, command: str
) -> None:
    payload = {"tool_input": {"command": command}, "cwd": str(main_checkout)}
    out = json.loads(_run_hook(json.dumps(payload)).stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"] == gg.REASON


def test_process_reads_payload_with_utf8_bom(main_checkout: Path) -> None:
    """Pipe do Windows PowerShell 5.1 prefixa BOM; sem `utf-8-sig` o hook calava (fail open)."""
    payload = {"tool_input": {"command": "git switch -c feat/99-x"}, "cwd": str(main_checkout)}
    out = json.loads(_run_hook("﻿" + json.dumps(payload)).stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_process_is_silent_on_safe_commands(main_checkout: Path) -> None:
    payload = {"tool_input": {"command": "git status\ngit log -1"}, "cwd": str(main_checkout)}
    assert _run_hook(json.dumps(payload)).stdout == ""

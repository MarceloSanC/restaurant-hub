"""Unit de `scripts/worktree-rm.py` — a worktree é achada pela branch (issue #81).

Na corrida de 2026-11-01, `worktree-rm.py <branch>` falhou com "worktree não
registrada" quando a pasta tinha slug diferente do da branch (pasta
`refactor-46-3-7-unit-of-work` para a branch `refactor/46-2-6-identity-unit-of-work`):
o script derivava o caminho do nome da branch e exigia `--path`. Agora ele lê o
`git worktree list --porcelain` e acha a worktree pela branch checada nela. Os
testes fixam a regra:

- a branch casa pelo nome inteiro (prefixo não casa) e devolve o caminho do
  bloco dela, não o do bloco anterior nem o do seguinte;
- `--path` continua vencendo;
- sem worktree com a branch, cai no caminho-padrão do slug — que o `main()`
  recusa adiante como "não registrada", como antes.

A resolução do caminho é testada com git e docker de fora.

Os hooks do git (issue #100): depois da remoção, o script confere o
`INSTALL_PYTHON` dos hooks, que valem para todas as worktrees. Se o python sumiu
com a worktree, religa a partir do checkout principal; se o religamento não
resolver, sai com 2. Esse ciclo roda com git real num repositório em `tmp_path`.
"""

from __future__ import annotations

import importlib.util
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "worktree-rm.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worktree_rm", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wr = _load()

BRANCH = "refactor/46-2-6-identity-unit-of-work"


def _porcelain(tmp_path: Path) -> tuple[str, Path, Path, Path]:
    """Três worktrees: a principal em develop, a da branch (pasta divergente) e uma vizinha.

    A vizinha tem branch cujo nome começa com o de `BRANCH`: prefixo não pode casar.
    O bloco destacado (`detached`) não tem linha `branch` e fica no meio de propósito.
    """
    main = tmp_path / "restaurant-hub"
    target = tmp_path / "restaurant-hub-worktrees" / "refactor-46-3-7-unit-of-work"
    neighbour = tmp_path / "restaurant-hub-worktrees" / "refactor-46-2-6-identity-unit-of-work-v2"
    detached = tmp_path / "restaurant-hub-worktrees" / "detached"
    text = "\n".join(
        [
            f"worktree {main}",
            "HEAD 1111111111111111111111111111111111111111",
            "branch refs/heads/develop",
            "",
            f"worktree {neighbour}",
            "HEAD 2222222222222222222222222222222222222222",
            f"branch refs/heads/{BRANCH}-v2",
            "",
            f"worktree {detached}",
            "HEAD 3333333333333333333333333333333333333333",
            "detached",
            "",
            f"worktree {target}",
            "HEAD 4444444444444444444444444444444444444444",
            f"branch refs/heads/{BRANCH}",
            "",
        ]
    )
    return text, main, target, neighbour


def test_finds_worktree_whose_folder_diverges_from_branch_slug(tmp_path: Path) -> None:
    porcelain, _, target, _ = _porcelain(tmp_path)

    assert wr.find_worktree_by_branch(porcelain, BRANCH) == target.resolve()


def test_branch_prefix_does_not_match(tmp_path: Path) -> None:
    porcelain, _, _, neighbour = _porcelain(tmp_path)

    assert wr.find_worktree_by_branch(porcelain, f"{BRANCH}-v2") == neighbour.resolve()
    assert wr.find_worktree_by_branch(porcelain, "refactor/46-2-6-identity") is None


def test_returns_none_when_no_worktree_has_the_branch(tmp_path: Path) -> None:
    porcelain, _, _, _ = _porcelain(tmp_path)

    assert wr.find_worktree_by_branch(porcelain, "feat/99-absent") is None
    assert wr.find_worktree_by_branch("", BRANCH) is None


def test_branch_line_before_any_worktree_line_is_ignored(tmp_path: Path) -> None:
    assert wr.find_worktree_by_branch(f"branch refs/heads/{BRANCH}\n", BRANCH) is None


def test_resolve_prefers_branch_lookup_over_slug_path(tmp_path: Path) -> None:
    porcelain, main, target, _ = _porcelain(tmp_path)

    resolved = wr.resolve_worktree_path(main, BRANCH, None, porcelain)

    assert resolved == target.resolve()
    assert resolved != wr.compute_worktree_path(main, BRANCH, None)


def test_resolve_override_wins_over_branch_lookup(tmp_path: Path) -> None:
    porcelain, main, _, _ = _porcelain(tmp_path)
    forced = tmp_path / "elsewhere"

    assert wr.resolve_worktree_path(main, BRANCH, str(forced), porcelain) == forced.resolve()


def test_main_removes_the_worktree_found_by_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O `main()` usa a resolução pela branch: sem `--path`, acha a pasta divergente.

    `--dry-run --no-docker --force` deixa o fluxo real rodar sem tocar git nem docker;
    só o registro de worktrees e a raiz do repo vêm do teste.
    """
    porcelain, main, target, _ = _porcelain(tmp_path)
    monkeypatch.setattr(wr, "git_top", lambda: main)
    monkeypatch.setattr(wr, "worktree_list_porcelain", lambda: porcelain)
    monkeypatch.setattr(wr, "check_worktree_registered", lambda p: p == target.resolve())
    monkeypatch.setattr(wr.install_hooks, "git_dirs", lambda: (main / ".git", main / ".git"))
    monkeypatch.setattr(
        sys, "argv", ["worktree-rm.py", BRANCH, "--dry-run", "--no-docker", "--force"]
    )

    assert wr.main() == 0
    out = capsys.readouterr().out
    assert f"git worktree remove {target.resolve()}" in out
    assert "[dry-run] hooks do git não dependem desta worktree" in out


def test_resolve_falls_back_to_slug_path_without_matching_worktree(tmp_path: Path) -> None:
    porcelain, main, _, _ = _porcelain(tmp_path)
    branch = "feat/99-absent"

    resolved = wr.resolve_worktree_path(main, branch, None, porcelain)

    assert resolved == (tmp_path / "restaurant-hub-worktrees" / "feat-99-absent").resolve()


# ---------------------------------------------------------------------------
# hooks do git — religados quando o python deles sai junto com a worktree
# ---------------------------------------------------------------------------


def _write_hook(common: Path, hook_type: str, python: Path) -> Path:
    hook = common / "hooks" / hook_type
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(f"INSTALL_PYTHON={shlex.quote(str(python))}\n", encoding="utf-8")
    return hook


def _venv_python(root: Path) -> Path:
    python = root / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


def test_hooks_inside_names_only_the_hooks_living_in_the_worktree(tmp_path: Path) -> None:
    common = tmp_path / "restaurant-hub" / ".git"
    wt = tmp_path / "restaurant-hub-worktrees" / "feat-1-a"
    vizinha = tmp_path / "restaurant-hub-worktrees" / "feat-1-a-v2"
    _write_hook(common, "pre-commit", _venv_python(wt))
    _write_hook(common, "commit-msg", _venv_python(vizinha))

    assert wr.hooks_inside(common, wt) == ["pre-commit"]
    assert wr.hooks_inside(common, vizinha) == ["commit-msg"]
    assert wr.hooks_inside(tmp_path / "sem-hooks" / ".git", wt) == []


def test_dry_run_reports_the_hooks_that_would_be_relinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    common = tmp_path / "restaurant-hub" / ".git"
    wt = tmp_path / "restaurant-hub-worktrees" / "feat-1-a"
    python = _venv_python(wt)
    for hook_type in ("pre-commit", "commit-msg"):
        _write_hook(common, hook_type, python)
    calls: list[list[str]] = []
    monkeypatch.setattr(wr, "_run", lambda cmd, **_kw: calls.append(cmd))

    assert wr.relink_hooks(common, wt, wr.hooks_inside(common, wt), dry_run=True) is True

    out = capsys.readouterr().out
    assert "hooks pre-commit, commit-msg apontam para dentro da worktree" in out
    assert str(tmp_path / "restaurant-hub") in out
    assert calls == []


def test_live_hooks_are_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    common = tmp_path / "restaurant-hub" / ".git"
    _write_hook(common, "pre-commit", _venv_python(tmp_path / "restaurant-hub"))
    calls: list[list[str]] = []
    monkeypatch.setattr(wr, "_run", lambda cmd, **_kw: calls.append(cmd))

    assert wr.relink_hooks(common, tmp_path / "wt", [], dry_run=False) is True

    assert calls == []
    assert "não dependem da worktree removida" in capsys.readouterr().out


def test_dead_hook_is_relinked_from_the_main_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    principal = tmp_path / "restaurant-hub"
    common = principal / ".git"
    python = _venv_python(principal)
    _write_hook(common, "commit-msg", tmp_path / "removida" / ".venv" / "python.exe")
    calls: list[tuple[list[str], Path]] = []

    def _relink(cmd: list[str], *, cwd: Path, check: bool) -> None:
        calls.append((cmd, cwd))
        _write_hook(common, "commit-msg", python)

    monkeypatch.setattr(wr, "_run", _relink)

    assert wr.relink_hooks(common, tmp_path / "removida", [], dry_run=False) is True
    assert calls == [
        (["uv", "run", "--extra", "dev", "python", "scripts/install_hooks.py"], principal)
    ]


def test_relink_that_leaves_a_dead_hook_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    common = tmp_path / "restaurant-hub" / ".git"
    _write_hook(common, "pre-commit", tmp_path / "removida" / "python.exe")
    monkeypatch.setattr(wr, "_run", lambda cmd, **_kw: None)

    assert wr.relink_hooks(common, tmp_path / "removida", [], dry_run=False) is False
    assert wr.install_hooks.RELINK_HINT in capsys.readouterr().err


def test_relink_that_leaves_a_dead_hook_outside_the_worktree_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hook morto por uma remoção anterior, fora da worktree que sai agora: se o
    religamento não resolver, o script não pode anunciar sucesso.
    """
    common = tmp_path / "restaurant-hub" / ".git"
    _write_hook(common, "pre-commit", tmp_path / "outra-removida" / "python.exe")
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.relink_hooks(common, tmp_path / "removida", [], dry_run=False) is False


def test_partially_removed_worktree_with_python_still_on_disk_is_relinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git worktree remove` no Windows pode parar no meio ("Filename too long"): o
    `python.exe` fica, as dependências do pre-commit não. Existir não basta.
    """
    principal = tmp_path / "restaurant-hub"
    common = principal / ".git"
    wt = tmp_path / "restaurant-hub-worktrees" / "feat-1-a"
    _write_hook(common, "pre-commit", _venv_python(wt))
    main_python = _venv_python(principal)
    calls: list[Path] = []

    def _install(cwd: Path) -> None:
        calls.append(cwd)
        _write_hook(common, "pre-commit", main_python)

    monkeypatch.setattr(wr, "run_install_hooks", _install)

    assert wr.install_hooks.dead_hooks(common) == []
    assert wr.relink_hooks(common, wt, ["pre-commit"], dry_run=False) is True
    assert calls == [principal]


def test_relink_that_leaves_the_hook_inside_the_worktree_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    common = tmp_path / "restaurant-hub" / ".git"
    wt = tmp_path / "restaurant-hub-worktrees" / "feat-1-a"
    _write_hook(common, "pre-commit", _venv_python(wt))
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.relink_hooks(common, wt, ["pre-commit"], dry_run=False) is False


def _git(cwd: Path, *args: str) -> None:
    cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert cp.returncode == 0, cp.stderr


@pytest.fixture
def real_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Checkout principal real com uma worktree da branch `feat/1-a`."""
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    principal = tmp_path / "restaurant-hub"
    principal.mkdir()
    _git(principal, "init", "-q", "-b", "develop")
    _git(principal, "config", "user.name", "Teste")
    _git(principal, "config", "user.email", "teste@example.com")
    _git(principal, "commit", "-q", "--allow-empty", "-m", "inicial")
    wt = tmp_path / "restaurant-hub-worktrees" / "feat-1-a"
    _git(principal, "worktree", "add", "-q", "-b", "feat/1-a", str(wt))
    monkeypatch.chdir(principal)
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "feat/1-a", "--no-docker", "--force"])
    return principal, wt


def test_main_relinks_the_hooks_of_a_removed_worktree(
    real_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """O ciclo da issue com git real: o hook aponta para o venv da worktree, ela sai
    pelo `main()` do script, e o hook volta a apontar para um python que existe.

    O religamento real (`uv run ... install_hooks.py` no principal) é trocado por
    gravar o python do principal: o repositório temporário não tem projeto uv.
    """
    principal, wt = real_repo
    common = (principal / ".git").resolve()
    hook = _write_hook(common, "pre-commit", _venv_python(wt))
    main_python = _venv_python(principal)
    relinked: list[Path] = []

    def _install(cwd: Path) -> None:
        relinked.append(cwd)
        _write_hook(common, "pre-commit", main_python)

    monkeypatch.setattr(wr, "run_install_hooks", _install)

    assert wr.main() == 0

    assert not wt.exists()
    assert relinked == [common.parent]
    assert wr.install_hooks.hook_python(hook) == main_python


def test_main_exits_2_when_the_hooks_stay_dead(
    real_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    principal, wt = real_repo
    _write_hook((principal / ".git").resolve(), "commit-msg", _venv_python(wt))
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.main() == 2  # noqa: PLR2004 — o exit code documentado do script
    assert not wt.exists()


def test_main_relinks_when_the_removal_leaves_the_venv_behind(
    real_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A remoção que para no meio: a pasta e o `python.exe` ficam, e o hook ainda
    aponta para eles — o `main()` religa mesmo assim.
    """
    principal, wt = real_repo
    common = (principal / ".git").resolve()
    hook = _write_hook(common, "pre-commit", _venv_python(wt))
    main_python = _venv_python(principal)
    monkeypatch.setattr(wr, "remove_worktree_git", lambda *_a, **_kw: None)
    monkeypatch.setattr(
        wr, "run_install_hooks", lambda _cwd: _write_hook(common, "pre-commit", main_python)
    )

    assert wr.main() == 0

    assert wt.exists()
    assert wr.install_hooks.hook_python(hook) == main_python

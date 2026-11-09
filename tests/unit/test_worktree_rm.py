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
import io
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

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
    monkeypatch.setattr(wr, "remove_worktree_git", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        wr, "run_install_hooks", lambda _cwd: _write_hook(common, "pre-commit", main_python)
    )

    assert wr.main() == 2  # noqa: PLR2004 — remoção que falhou não sai com 0

    assert wt.exists()
    assert wr.install_hooks.hook_python(hook) == main_python


def test_forced_removal_that_fails_is_reported_and_exits_2(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--force` cuja segunda tentativa também falha: a pasta fica, e o script não
    anuncia sucesso nem sai com 0 (finding da #100, "Filename too long" no Windows).
    """
    _, wt = real_repo
    (wt / "sujo.txt").write_text("x", encoding="utf-8")  # 1ª tentativa recusa: arquivo novo
    real_run = subprocess.run

    def _run(cmd: list[str], *a: object, **kw: object) -> object:
        if cmd[:4] == ["git", "worktree", "remove", "--force"]:
            return subprocess.CompletedProcess(cmd, 1)  # "Filename too long"
        return real_run(cmd, *a, **kw)  # type: ignore[call-overload]

    monkeypatch.setattr(wr.subprocess, "run", _run)
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.main() == 2  # noqa: PLR2004 — o exit code documentado do script
    assert wt.exists()
    captured = capsys.readouterr()
    assert "a pasta ficou no disco" in captured.err
    assert "NÃO removida" in captured.out
    assert "✓ Worktree" not in captured.out


def test_forced_removal_that_succeeds_exits_0(
    real_repo: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, wt = real_repo
    (wt / "sujo.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.main() == 0
    assert not wt.exists()


# ---------------------------------------------------------------------------
# o compose da worktree — derrubado pelo rótulo do projeto (issue #84)
# ---------------------------------------------------------------------------

PROJECT = "fix-84-orphan-port"


@pytest.fixture
def compose(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """O `worktree_docker` com o daemon de pé e um projeto com Postgres e volume.

    `calls` registra quem foi chamado com qual projeto; `failures` é o que o
    `remove_project` devolve como não removido.
    """
    state: dict[str, list[str]] = {"calls": [], "failures": []}
    wd = wr.worktree_docker

    def _found() -> object:
        return wd.ProjectResources(
            containers=[f"{PROJECT}-postgres-1"], volumes=[f"{PROJECT}_pgdata"]
        )

    def _remove(project: str) -> tuple[object, list[str]]:
        state["calls"].append(f"remove {project}")
        return _found(), state["failures"]

    def _resources(project: str) -> object:
        state["calls"].append(f"list {project}")
        return _found()

    monkeypatch.setattr(wd, "ensure_daemon", lambda: None)
    monkeypatch.setattr(wd, "remove_project", _remove)
    monkeypatch.setattr(wd, "project_resources", _resources)
    monkeypatch.setattr(wr, "_docker_available", lambda: False)
    return state


def _docker_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def _down() -> None:
        raise wr.worktree_docker.DockerUnavailable("failed to connect to the docker API")

    monkeypatch.setattr(wr.worktree_docker, "ensure_daemon", _down)


def test_compose_project_of_the_folder_is_taken_down_even_with_the_folder_gone(
    tmp_path: Path, compose: dict[str, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    gone = tmp_path / "restaurant-hub-worktrees" / PROJECT  # nunca criada

    assert wr.compose_cleanup(gone, dry_run=False) is True

    assert compose["calls"] == [f"remove {PROJECT}"]
    out = capsys.readouterr().out
    assert "projeto compose derrubado" in out
    assert f"{PROJECT}-postgres-1" in out
    assert f"{PROJECT}_pgdata" in out


def test_dry_run_only_lists_the_compose_project(
    tmp_path: Path, compose: dict[str, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert wr.compose_cleanup(tmp_path / PROJECT, dry_run=True) is True

    assert compose["calls"] == [f"list {PROJECT}"]
    assert "[dry-run] seria derrubado" in capsys.readouterr().out


def test_compose_leftover_is_reported_as_failure(
    tmp_path: Path, compose: dict[str, list[str]], capsys: pytest.CaptureFixture[str]
) -> None:
    compose["failures"].append(f"volume {PROJECT}_pgdata: in use")

    assert wr.compose_cleanup(tmp_path / PROJECT, dry_run=False) is False
    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is False
    assert f"não saiu — volume {PROJECT}_pgdata: in use" in capsys.readouterr().err


def test_empty_compose_project_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, compose: dict[str, list[str]]
) -> None:
    empty = wr.worktree_docker.ProjectResources()
    monkeypatch.setattr(wr.worktree_docker, "remove_project", lambda _p: (empty, []))

    assert wr.compose_cleanup(tmp_path / PROJECT, dry_run=False) is True


def test_docker_down_warns_with_the_project_and_the_way_out(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    compose: dict[str, list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Docker parado: nada foi conferido — o aviso diz o quê, e como derrubar depois."""
    _docker_down(monkeypatch)
    devcontainer: list[bool] = []
    monkeypatch.setattr(wr, "_docker_available", lambda: devcontainer.append(True) or False)

    assert wr.compose_cleanup(tmp_path / PROJECT, dry_run=False) is None
    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is True

    assert compose["calls"] == []
    assert devcontainer == []  # sem daemon, a limpeza do devcontainer nem pergunta
    err = capsys.readouterr().err
    assert f"`{PROJECT}`" in err
    assert "NÃO foi derrubado" in err
    assert "make worktree-orphans ARGS=--prune" in err


def test_main_takes_down_the_compose_before_removing_the_worktree(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    compose: dict[str, list[str]],
) -> None:
    _, wt = real_repo
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "feat/1-a", "--force"])
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)
    existed: list[bool] = []
    recorded = wr.worktree_docker.remove_project  # o da fixture, que registra a chamada

    def _remove(project: str) -> tuple[object, list[str]]:
        existed.append(wt.exists())
        return recorded(project)

    monkeypatch.setattr(wr.worktree_docker, "remove_project", _remove)

    assert wr.main() == 0

    assert compose["calls"] == ["remove feat-1-a"]
    assert existed == [True]
    assert not wt.exists()


def test_main_exits_2_when_the_compose_leaves_something_behind(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    compose: dict[str, list[str]],
) -> None:
    _, wt = real_repo
    compose["failures"].append("volume feat-1-a_pgdata: in use")
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "feat/1-a", "--force"])
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.main() == 2  # noqa: PLR2004 — o exit code documentado do script
    assert not wt.exists()  # a worktree sai mesmo assim; o exit code acusa o resto


def test_main_with_docker_down_still_removes_and_exits_0(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    compose: dict[str, list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, wt = real_repo
    _docker_down(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "feat/1-a", "--force"])
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.main() == 0
    assert not wt.exists()
    assert "make worktree-orphans ARGS=--prune" in capsys.readouterr().err


def test_main_refuses_the_branch_of_the_main_checkout(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    compose: dict[str, list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`develop` está no checkout principal: o projeto compose dele é o banco de
    quem fica. O script recusa antes de qualquer docker ou git.
    """
    principal, _ = real_repo
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "develop", "--force"])

    with pytest.raises(SystemExit) as exc:
        wr.main()

    assert exc.value.code == 1
    assert compose["calls"] == []
    assert principal.exists()
    assert "checkout principal" in capsys.readouterr().err


def test_main_refuses_a_worktree_whose_compose_project_is_the_main_checkouts(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    compose: dict[str, list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Worktree criada à mão em `../x/Restaurant-Hub`: o compose dá a ela o projeto
    `restaurant-hub`, o do checkout principal. Derrubá-lo apagaria o banco de quem
    fica — o script recusa antes de qualquer docker ou git.
    """
    principal, _ = real_repo
    clash = principal.parent / "x" / "Restaurant-Hub"
    _git(principal, "worktree", "add", "-q", "-b", "fix/2-b", str(clash))
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "fix/2-b", "--force"])

    with pytest.raises(SystemExit) as exc:
        wr.main()

    assert exc.value.code == 1
    assert compose["calls"] == []
    assert clash.exists()
    assert "--no-docker" in capsys.readouterr().err


def test_folder_name_is_normalized_like_compose_does(
    tmp_path: Path, compose: dict[str, list[str]]
) -> None:
    wr.compose_cleanup(tmp_path / "Feat-1-A", dry_run=False)

    assert compose["calls"] == ["remove feat-1-a"]


def test_compose_leftover_fails_the_cleanup_with_the_devcontainer_path_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, compose: dict[str, list[str]]
) -> None:
    """Com o daemon de pé, o `docker_cleanup` passa pelo devcontainer e pela imagem e
    ainda devolve o resultado do compose.
    """
    compose["failures"].append(f"volume {PROJECT}_pgdata: in use")
    monkeypatch.setattr(wr, "_docker_available", lambda: True)
    monkeypatch.setattr(wr, "find_containers_for_worktree", lambda _p: [])
    monkeypatch.setattr(
        wr.subprocess, "run", lambda cmd, *_a, **_kw: subprocess.CompletedProcess(cmd, 1)
    )

    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is False
    compose["failures"].clear()
    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is True


# ---------------------------------------------------------------------------
# helpers de processo — `_run`, `_force_utf8_stdio` (issue #91)
# ---------------------------------------------------------------------------

EXIT_SUBPROCESS = 2  # exit code documentado para erro de subprocess
EXIT_CHECK = 1  # exit code documentado para verificação que falhou


class _FakeRun:
    """Troca do `subprocess.run`: registra comando e kwargs, responde por `responder`."""

    def __init__(
        self,
        responder: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []
        self._responder = responder

    def __call__(
        self, cmd: list[str], *_a: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(cmd))
        self.kwargs.append(kwargs)
        if self._responder is None:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return self._responder(list(cmd))


def _cp(
    cmd: list[str], rc: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)


def test_run_prints_the_command_and_forwards_cwd_and_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(lambda cmd: _cp(cmd, stdout="ok"))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    cp = wr._run(["git", "status"], cwd=tmp_path, check=False)

    assert cp.stdout == "ok"
    assert fake.kwargs == [
        {"cwd": str(tmp_path), "check": False, "text": True, "capture_output": False}
    ]
    assert "  $ git status" in capsys.readouterr().out


def test_run_with_capture_stays_quiet_and_has_no_cwd(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun()
    monkeypatch.setattr(wr.subprocess, "run", fake)

    wr._run(["git", "rev-parse"], capture=True)

    assert fake.kwargs == [{"cwd": None, "check": True, "text": True, "capture_output": True}]
    assert capsys.readouterr().out == ""


def test_run_missing_executable_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _missing(cmd: list[str], *_a: object, **_kw: object) -> object:
        raise FileNotFoundError("sem docker")

    monkeypatch.setattr(wr.subprocess, "run", _missing)

    with pytest.raises(SystemExit) as exc:
        wr._run(["docker", "info"], capture=True)

    assert exc.value.code == EXIT_SUBPROCESS
    assert "executável não encontrado: docker (sem docker)" in capsys.readouterr().err


def test_run_failed_command_with_capture_echoes_its_output_and_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fails(cmd: list[str], *_a: object, **_kw: object) -> object:
        raise subprocess.CalledProcessError(3, cmd, output="saida-do-git", stderr="erro-do-git")

    monkeypatch.setattr(wr.subprocess, "run", _fails)

    with pytest.raises(SystemExit) as exc:
        wr._run(["git", "log"], capture=True)

    assert exc.value.code == EXIT_SUBPROCESS
    err = capsys.readouterr().err
    assert "comando falhou (exit 3): git log" in err
    assert "saida-do-git" in err
    assert "erro-do-git" in err


def test_run_failed_command_without_capture_does_not_echo_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem `capture`, a saída já foi para o terminal: o script não a repete."""

    def _fails(cmd: list[str], *_a: object, **_kw: object) -> object:
        raise subprocess.CalledProcessError(1, cmd, output="saida-do-git", stderr="erro-do-git")

    monkeypatch.setattr(wr.subprocess, "run", _fails)

    with pytest.raises(SystemExit) as exc:
        wr._run(["git", "log"])

    assert exc.value.code == EXIT_SUBPROCESS
    err = capsys.readouterr().err
    assert "comando falhou (exit 1): git log" in err
    assert "saida-do-git" not in err
    assert "erro-do-git" not in err


class _RecordingWrapper(io.TextIOWrapper):
    reconfigured: list[object]

    def reconfigure(self, **kwargs: Any) -> None:  # noqa: ANN401 — assinatura do typeshed
        self.reconfigured.append(kwargs.get("encoding"))
        super().reconfigure(**kwargs)


class _BrokenWrapper(io.TextIOWrapper):
    def reconfigure(self, **_kwargs: Any) -> None:  # noqa: ANN401 — assinatura do typeshed
        raise OSError("console não deixa")


def test_force_utf8_reconfigures_only_non_utf8_wrappers(monkeypatch: pytest.MonkeyPatch) -> None:
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    err = _RecordingWrapper(io.BytesIO(), encoding="UTF-8")
    err.reconfigured = []
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    wr._force_utf8_stdio()

    assert out.encoding == "utf-8"
    assert err.reconfigured == []  # já era UTF-8 (em maiúsculas): fica como está


def test_force_utf8_tolerates_oserror_and_skips_non_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = _BrokenWrapper(io.BytesIO(), encoding="cp1252")
    plain = io.StringIO()  # sob captura do pytest o stream é outro objeto, sem `reconfigure`
    monkeypatch.setattr(sys, "stdout", broken)
    monkeypatch.setattr(sys, "stderr", plain)

    wr._force_utf8_stdio()

    assert broken.encoding == "cp1252"


def test_loading_by_path_puts_scripts_on_sys_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Carregado pelo caminho (os testes), o script põe `scripts/` no `sys.path`."""
    scripts = str(_SCRIPT.parent)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != scripts])
    spec = importlib.util.spec_from_file_location("worktree_rm_fresh", _SCRIPT)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(importlib.util.module_from_spec(spec))

    assert sys.path[0] == scripts

    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert sys.path.count(scripts) == 1  # já presente: não entra de novo


# ---------------------------------------------------------------------------
# git helpers — registro e sincronização com o remoto
# ---------------------------------------------------------------------------


def test_compute_worktree_path_honours_the_override(tmp_path: Path) -> None:
    forced = tmp_path / "outro-lugar"

    assert wr.compute_worktree_path(tmp_path / "repo", BRANCH, str(forced)) == forced.resolve()


def test_worktree_registered_compares_resolved_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    porcelain, main, target, _ = _porcelain(tmp_path)
    fake = _FakeRun(lambda cmd: _cp(cmd, stdout=porcelain))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    assert wr.check_worktree_registered(target) is True
    assert wr.check_worktree_registered(main) is True
    assert wr.check_worktree_registered(tmp_path / "restaurant-hub-worktrees") is False
    assert wr.check_worktree_registered(target.parent / "nao-registrada") is False
    assert fake.calls[0] == ["git", "worktree", "list", "--porcelain"]


def _sync_responder(
    *, status: str = "", remote: bool = True, ahead: str = ""
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    def _respond(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "status":
            return _cp(cmd, stdout=status)
        if cmd[1] == "show-ref":
            return _cp(cmd, 0 if remote else 1)
        if cmd[1] == "log":
            return _cp(cmd, stdout=ahead)
        raise AssertionError(f"comando inesperado: {cmd}")

    return _respond


def test_check_sync_refuses_a_dirty_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(_sync_responder(status=" M app.py\n?? novo.txt\n"))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    with pytest.raises(SystemExit) as exc:
        wr.check_sync(tmp_path, "feat/1-a")

    assert exc.value.code == EXIT_CHECK
    assert fake.calls == [["git", "status", "--porcelain"]]
    assert fake.kwargs[0]["cwd"] == str(tmp_path)
    err = capsys.readouterr().err
    assert "alterações não commitadas" in err
    assert "?? novo.txt" in err


def test_check_sync_without_remote_branch_only_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(_sync_responder(remote=False))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    wr.check_sync(tmp_path, "feat/1-a")

    assert fake.calls == [
        ["git", "status", "--porcelain"],
        ["git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/feat/1-a"],
    ]
    captured = capsys.readouterr()
    assert "origin/feat/1-a não encontrada" in captured.err
    assert "em dia" not in captured.out


def test_check_sync_refuses_unpushed_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(_sync_responder(ahead="abc1234 feat: coisa nova\n"))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    with pytest.raises(SystemExit) as exc:
        wr.check_sync(tmp_path, "feat/1-a")

    assert exc.value.code == EXIT_CHECK
    assert fake.calls[-1] == ["git", "log", "origin/feat/1-a..HEAD", "--oneline"]
    assert fake.kwargs[-1]["cwd"] == str(tmp_path)
    err = capsys.readouterr().err
    assert "commits não enviados" in err
    assert "abc1234 feat: coisa nova" in err


def test_check_sync_passes_when_in_step_with_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(_sync_responder(status="  \n", ahead="\n"))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    wr.check_sync(tmp_path, "feat/1-a")

    assert [c[1] for c in fake.calls] == ["status", "show-ref", "log"]
    assert "branch feat/1-a em dia com origin" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# docker helpers — daemon, variantes de caminho, containers e volumes
# ---------------------------------------------------------------------------


def test_docker_available_follows_the_exit_code_of_docker_info(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    up = _FakeRun()
    monkeypatch.setattr(wr.subprocess, "run", up)
    assert wr._docker_available() is True
    assert up.calls == [["docker", "info"]]

    monkeypatch.setattr(wr.subprocess, "run", _FakeRun(lambda cmd: _cp(cmd, 1)))
    assert wr._docker_available() is False


def test_path_variants_have_both_slashes_and_the_resolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    rel = Path("rel") / "wt"
    resolved = rel.resolve()

    variants = wr._path_variants(rel)

    # No Windows são quatro grafias (barra invertida e normal, relativa e
    # resolvida); no Linux, duas. A ordem e a deduplicação são as mesmas.
    spellings = [str(rel), "rel/wt", str(resolved), str(resolved).replace("\\", "/")]
    assert variants == list(dict.fromkeys(spellings))


# `type(Path())` é `WindowsPath`/`PosixPath` conforme o SO: base dinâmica que o mypy recusa [misc].
class _UnresolvablePath(type(Path())):  # type: ignore[misc]
    def resolve(self, strict: bool = False) -> Path:
        raise OSError("caminho inacessível")


# `type(Path())` é `WindowsPath`/`PosixPath` conforme o SO: base dinâmica que o mypy recusa [misc].
class _AlreadyResolvedPath(type(Path())):  # type: ignore[misc]
    def resolve(self, strict: bool = False) -> Path:
        return self


def test_path_variants_do_not_repeat_equal_spellings() -> None:
    """Caminho sem barra invertida e já resolvido: as quatro grafias são uma só."""
    assert wr._path_variants(_AlreadyResolvedPath("wt")) == ["wt"]


def test_path_variants_survive_an_unresolvable_path() -> None:
    p = _UnresolvablePath("rel", "wt")

    assert wr._path_variants(p) == list(dict.fromkeys([str(p), "rel/wt"]))


def test_find_containers_queries_every_label_and_path_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uma consulta por (rótulo, variante); linhas vazias e JSON inválido são ignorados;
    o mesmo container achado por duas consultas entra uma vez, por `ID` ou `Id`.
    """
    monkeypatch.setattr(wr, "_path_variants", lambda _p: ["C:\\wt", "C:/wt"])
    by_filter = {
        "label=vsch.local.folder=C:\\wt": '{"ID": "aaa", "Names": "dev"}\n\nnão é json\n',
        "label=vsch.local.folder=C:/wt": '  {"ID": "aaa", "Names": "dev-dup"}  \n',
        "label=devcontainer.local_folder=C:\\wt": '{"Id": "bbb", "Name": "old"}\n{"Names": "x"}',
        "label=devcontainer.local_folder=C:/wt": '{"Id": "bbb"}\n{"ID": "ccc"}\n',
    }
    fake = _FakeRun(lambda cmd: _cp(cmd, stdout=by_filter[cmd[4]]))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    found = wr.find_containers_for_worktree(Path("ignorado"))

    assert fake.calls == [
        ["docker", "ps", "-a", "--filter", f"label={key}={variant}", "--format", "{{json .}}"]
        for key in ("vsch.local.folder", "devcontainer.local_folder")
        for variant in ("C:\\wt", "C:/wt")
    ]
    assert found == [
        {"ID": "aaa", "Names": "dev"},
        {"Id": "bbb", "Name": "old"},
        {"ID": "ccc"},
    ]


def test_container_volumes_are_the_named_mounts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRun(lambda cmd: _cp(cmd, stdout="vol_a\n\n  vol_b  \n   \n"))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    assert wr.get_container_volumes("abc") == ["vol_a", "vol_b"]
    assert fake.calls == [
        [
            "docker",
            "inspect",
            "abc",
            "--format",
            '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}\n{{end}}{{end}}',
        ]
    ]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("  apagar volumes  ", True), ("apagar", False), ("", False), ("APAGAR VOLUMES", False)],
)
def test_confirm_requires_the_exact_phrase(
    answer: str,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)

    assert wr._confirm("Apagar mesmo?", "apagar volumes") is expected
    out = capsys.readouterr().out
    assert "Apagar mesmo?" in out
    assert '"apagar volumes"' in out


@pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
def test_confirm_treats_eof_and_ctrl_c_as_no(
    interrupt: type[BaseException], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(_prompt: str) -> str:
        raise interrupt

    monkeypatch.setattr("builtins.input", _raise)

    assert wr._confirm("Apagar?", "apagar volumes") is False


# ---------------------------------------------------------------------------
# limpeza do devcontainer — containers, volumes (com confirmação) e imagem
# ---------------------------------------------------------------------------

IMAGE = "restaurant_hub-app:dev"
CONTAINERS: list[dict[str, str]] = [
    {"ID": "abc123def4567890xyz", "Names": "wt-dev", "State": "running"},
    {"Id": "fff000", "Name": "wt-old", "Status": "Exited (0) 2 days ago"},
    {"ID": "up1", "Names": "wt-up", "State": "", "Status": "Up 5 minutes"},
]


class _FakeDocker(_FakeRun):
    """O CLI do docker: volumes por container, falhas escolhidas, imagem presente ou não."""

    def __init__(self) -> None:
        super().__init__(self._respond)
        self.mounts = {"abc123def4567890xyz": "vol_b\nvol_a\n", "fff000": "vol_a\n", "up1": ""}
        self.rm_fail: set[str] = set()
        self.volume_fail: set[str] = set()
        self.image = True
        self.rmi_ok = True

    def _respond(self, cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "inspect":
            return _cp(cmd, stdout=self.mounts[cmd[2]])
        if cmd[1] == "rm":
            failed = cmd[2] in self.rm_fail
            return _cp(cmd, 1 if failed else 0, stderr="rm: em uso" if failed else "")
        if cmd[1:3] == ["volume", "rm"]:
            failed = cmd[3] in self.volume_fail
            return _cp(cmd, 1 if failed else 0, stderr="volume: em uso" if failed else "")
        if cmd[1:3] == ["image", "inspect"]:
            return _cp(cmd, 0 if self.image else 1)
        if cmd[1] == "rmi":
            return _cp(cmd, 0 if self.rmi_ok else 1, stderr="" if self.rmi_ok else "rmi: em uso")
        return _cp(cmd)

    def destructive(self) -> list[list[str]]:
        return [
            c for c in self.calls if c[1] in ("stop", "rm", "rmi") or c[1:3] == ["volume", "rm"]
        ]


@pytest.fixture
def devcontainer(monkeypatch: pytest.MonkeyPatch, compose: dict[str, list[str]]) -> _FakeDocker:
    """Daemon de pé, compose limpo e três containers do devcontainer da worktree."""
    fake = _FakeDocker()
    monkeypatch.setattr(wr, "_docker_available", lambda: True)
    monkeypatch.setattr(wr, "find_containers_for_worktree", lambda _p: CONTAINERS)
    monkeypatch.setattr(wr.subprocess, "run", fake)
    return fake


def _answers(monkeypatch: pytest.MonkeyPatch, *answers: str) -> list[str]:
    asked: list[str] = []
    pending = iter(answers)

    def _input(prompt: str) -> str:
        asked.append(prompt)
        return next(pending)

    monkeypatch.setattr("builtins.input", _input)
    return asked


def test_devcontainer_dry_run_destroys_nothing_and_asks_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devcontainer: _FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked = _answers(monkeypatch)

    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=True) is True

    assert devcontainer.destructive() == []
    assert asked == []
    out = capsys.readouterr().out
    assert "container: wt-dev (abc123def456) [running]" in out
    assert "Volumes encontrados (2):" in out
    assert "[dry-run] 2 volume(s) seriam removidos" in out
    assert f"[dry-run] imagem {IMAGE} seria removida" in out


def test_devcontainer_removes_containers_volumes_and_image_with_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devcontainer: _FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked = _answers(monkeypatch, "apagar volumes", "apagar imagens")

    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is True

    assert devcontainer.destructive() == [
        ["docker", "stop", "abc123def4567890xyz"],
        ["docker", "rm", "abc123def4567890xyz"],
        ["docker", "rm", "fff000"],  # parado: sem `stop`
        ["docker", "stop", "up1"],  # `Status` "Up ..." quando o `State` vem vazio
        ["docker", "rm", "up1"],
        ["docker", "volume", "rm", "vol_a"],  # ordenados e sem repetição
        ["docker", "volume", "rm", "vol_b"],
        ["docker", "rmi", IMAGE],
    ]
    assert len(asked) == len(["volumes", "imagem"])
    out = capsys.readouterr().out
    assert "→ removido: wt-old" in out
    assert "volume removido: vol_a" in out
    assert f"imagem removida: {IMAGE}" in out


def test_devcontainer_keeps_volumes_and_image_without_the_exact_phrase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devcontainer: _FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A frase de um prompt não vale no outro: trocadas, nada persistente sai."""
    _answers(monkeypatch, "apagar imagens", "apagar volumes")

    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is True

    assert [c for c in devcontainer.destructive() if c[1] in ("volume", "rmi")] == []
    out = capsys.readouterr().out
    assert "volumes mantidos (confirmação não fornecida)" in out
    assert "imagem mantida (confirmação não fornecida)" in out


def test_devcontainer_failures_are_warned_not_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devcontainer: _FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    devcontainer.rm_fail = {"fff000"}
    devcontainer.volume_fail = {"vol_b"}
    devcontainer.rmi_ok = False
    _answers(monkeypatch, "apagar volumes", "apagar imagens")

    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is True

    captured = capsys.readouterr()
    assert "falha ao remover wt-old: rm: em uso" in captured.err
    assert "falha ao remover vol_b: volume: em uso" in captured.err
    assert "falha ao remover imagem (em uso?): rmi: em uso" in captured.err
    assert "volume removido: vol_a" in captured.out
    assert "→ removido: wt-old" not in captured.out


def test_devcontainer_without_volumes_or_image_asks_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    devcontainer: _FakeDocker,
    capsys: pytest.CaptureFixture[str],
) -> None:
    devcontainer.mounts = dict.fromkeys(devcontainer.mounts, "")
    devcontainer.image = False
    asked = _answers(monkeypatch)

    assert wr.docker_cleanup(tmp_path / PROJECT, dry_run=False) is True

    assert asked == []
    assert ["docker", "image", "inspect", IMAGE] in devcontainer.calls
    out = capsys.readouterr().out
    assert "Volumes encontrados" not in out
    assert "Imagem encontrada" not in out


# ---------------------------------------------------------------------------
# remoção git — branch remota, `branch -d` recusado e `worktree remove` sem --force
# ---------------------------------------------------------------------------


def test_dry_run_mentions_the_remote_branch_only_when_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun()
    monkeypatch.setattr(wr.subprocess, "run", fake)

    assert wr.remove_worktree_git(
        tmp_path, "feat/1-a", dry_run=True, delete_remote=True, force=False
    )
    assert "[dry-run] git push origin --delete feat/1-a" in capsys.readouterr().out

    wr.remove_worktree_git(tmp_path, "feat/1-a", dry_run=True, delete_remote=False, force=False)
    assert "push origin --delete" not in capsys.readouterr().out
    assert fake.calls == []


@pytest.mark.parametrize(("push_rc", "ok"), [(0, True), (1, False)])
def test_delete_remote_pushes_the_deletion(
    push_rc: int,
    ok: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _respond(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["git", "push"]:
            return _cp(cmd, push_rc, stderr="remote: proibido")
        return _cp(cmd)

    fake = _FakeRun(_respond)
    monkeypatch.setattr(wr.subprocess, "run", fake)
    monkeypatch.setattr(wr, "_remove_worktree_dir", lambda _p, *, force: True)

    assert wr.remove_worktree_git(
        tmp_path, "feat/1-a", dry_run=False, delete_remote=True, force=False
    )

    assert ["git", "push", "origin", "--delete", "feat/1-a"] in fake.calls
    captured = capsys.readouterr()
    assert ("branch remota origin/feat/1-a deletada" in captured.out) is ok
    assert ("falha ao deletar branch remota: remote: proibido" in captured.err) is not ok


def test_unmerged_branch_is_kept_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _respond(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[:2] == ["git", "branch"]:
            return _cp(cmd, 1, stderr="not fully merged")
        return _cp(cmd)

    fake = _FakeRun(_respond)
    monkeypatch.setattr(wr.subprocess, "run", fake)
    monkeypatch.setattr(wr, "_remove_worktree_dir", lambda _p, *, force: True)

    wr.remove_worktree_git(tmp_path, "feat/1-a", dry_run=False, delete_remote=False, force=False)

    assert fake.calls == [
        ["git", "branch", "-d", "feat/1-a"],
        ["git", "remote", "prune", "origin"],
    ]
    captured = capsys.readouterr()
    assert "git branch -d falhou (branch não mergeada localmente?): not fully merged" in (
        captured.err
    )
    assert "deletada" not in captured.out


def test_worktree_remove_failure_without_force_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _FakeRun(lambda cmd: _cp(cmd, 1, stderr="contains modified files"))
    monkeypatch.setattr(wr.subprocess, "run", fake)

    with pytest.raises(SystemExit) as exc:
        wr._remove_worktree_dir(tmp_path, force=False)

    assert exc.value.code == EXIT_CHECK
    assert fake.calls == [["git", "worktree", "remove", str(tmp_path)]]  # sem 2ª tentativa
    assert "git worktree remove falhou: contains modified files" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() — worktree não registrada e a verificação de sync
# ---------------------------------------------------------------------------


def _fake_main_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, registered: bool, argv: list[str]
) -> Path:
    porcelain, main, target, _ = _porcelain(tmp_path)
    monkeypatch.setattr(wr, "git_top", lambda: main)
    monkeypatch.setattr(wr, "worktree_list_porcelain", lambda: porcelain)
    monkeypatch.setattr(wr, "check_worktree_registered", lambda _p: registered)
    monkeypatch.setattr(wr.install_hooks, "git_dirs", lambda: (main / ".git", main / ".git"))
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", BRANCH, *argv])
    return target


def test_main_refuses_an_unregistered_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _fake_main_env(tmp_path, monkeypatch, registered=False, argv=["--no-docker"])
    removed: list[object] = []
    monkeypatch.setattr(wr, "remove_worktree_git", lambda *a, **_kw: removed.append(a))

    with pytest.raises(SystemExit) as exc:
        wr.main()

    assert exc.value.code == EXIT_CHECK
    assert removed == []
    assert f"worktree não registrada no git: {target.resolve()}" in capsys.readouterr().err


def test_main_skips_the_sync_check_when_the_folder_is_gone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_main_env(tmp_path, monkeypatch, registered=True, argv=["--dry-run", "--no-docker"])
    synced: list[Path] = []
    monkeypatch.setattr(wr, "check_sync", lambda p, _b: synced.append(p))

    assert wr.main() == 0

    assert synced == []
    out = capsys.readouterr().out
    assert "diretório não existe no disco — pulando check de sync" in out
    assert "[modo dry-run" in out


def test_main_without_force_checks_sync_on_the_real_worktree(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sem `--force`: a worktree limpa e sem remoto só gera aviso, e sai."""
    _, wt = real_repo
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "feat/1-a", "--no-docker"])
    monkeypatch.setattr(wr, "run_install_hooks", lambda _cwd: None)

    assert wr.main() == 0

    assert not wt.exists()
    captured = capsys.readouterr()
    assert "origin/feat/1-a não encontrada" in captured.err
    assert "--force: verificação de sync pulada" not in captured.out


def test_main_without_force_keeps_a_dirty_worktree(
    real_repo: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, wt = real_repo
    (wt / "sujo.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["worktree-rm.py", "feat/1-a", "--no-docker"])

    with pytest.raises(SystemExit) as exc:
        wr.main()

    assert exc.value.code == EXIT_CHECK
    assert (wt / "sujo.txt").exists()
    assert "?? sujo.txt" in capsys.readouterr().err

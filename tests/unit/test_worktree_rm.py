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

Só a resolução do caminho é testada: git e docker ficam fora.
"""

from __future__ import annotations

import importlib.util
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
    monkeypatch.setattr(
        sys, "argv", ["worktree-rm.py", BRANCH, "--dry-run", "--no-docker", "--force"]
    )

    assert wr.main() == 0
    assert f"git worktree remove {target.resolve()}" in capsys.readouterr().out


def test_resolve_falls_back_to_slug_path_without_matching_worktree(tmp_path: Path) -> None:
    porcelain, main, _, _ = _porcelain(tmp_path)
    branch = "feat/99-absent"

    resolved = wr.resolve_worktree_path(main, branch, None, porcelain)

    assert resolved == (tmp_path / "restaurant-hub-worktrees" / "feat-99-absent").resolve()

"""Instala os hooks do git (`pre-commit` e `commit-msg`) a partir do checkout principal.

Os hooks moram no diretório comum do repositório (`git rev-parse --git-common-dir`),
um só para todas as worktrees. O `pre-commit install` grava neles o caminho
absoluto do python que o rodou (`INSTALL_PYTHON`, pre-commit 4.6.0
`commands/install_uninstall.py`, `_install_hook_script`). Instalados de dentro de
uma worktree, os hooks passavam a depender do venv **dela**; removida a
worktree, os commits de todas as outras quebravam (issue #100).

Regra: só o checkout principal, que nunca é removido, instala os hooks.

- No checkout principal: roda `pre-commit install` com o python deste processo
  (`uv run` → o `.venv` do principal), e o `INSTALL_PYTHON` aponta para ele.
- Numa worktree: não toca nos hooks. Só confere se o python deles existe e,
  se não existir, diz como religar.

O python dos hooks roda só o framework do pre-commit. Cada hook do
`.pre-commit-config.yaml` é `language: system` e chama `uv run`, que resolve o
venv da worktree que commita — então o venv do principal serve a todas.

Chamado por `make setup` e pelo `scripts/worktree-rm.py` (religamento depois da
remoção). Procedimento: docs/GIT-WORKFLOW.md §"Hooks do git".

Uso (de qualquer checkout):
    uv run python scripts/install_hooks.py

Exit codes:
  0  hooks instalados (principal) ou nada a fazer (worktree)
  1  hooks de uma worktree apontam para python inexistente (religar no principal)
  2  falha do git ou do pre-commit
"""

from __future__ import annotations

import contextlib
import shlex
import subprocess
import sys
from pathlib import Path

HOOK_TYPES = ("pre-commit", "commit-msg")
EXIT_OK = 0
EXIT_DEAD_HOOK = 1
EXIT_ERROR = 2
RELINK_HINT = "uv run python scripts/install_hooks.py   # no checkout principal"


def _force_utf8_stdio() -> None:
    """Garante UTF-8 em stdout/stderr (Windows defaulta cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() == "utf-8":
            continue
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def git_dirs(cwd: Path | None = None) -> tuple[Path, Path]:
    """`(git-dir, git-common-dir)` absolutos do checkout em `cwd`.

    Iguais no checkout principal; numa worktree, o git-dir é
    `<common>/worktrees/<nome>`.
    """
    cp = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=True,
    )
    git_dir, common_dir = cp.stdout.strip().splitlines()
    return Path(git_dir).resolve(), Path(common_dir).resolve()


def main_checkout(common_dir: Path) -> Path:
    """Raiz do checkout principal: o pai do `.git` comum (repositório não bare)."""
    return common_dir.parent


def hook_python(hook_file: Path) -> Path | None:
    """O `INSTALL_PYTHON` gravado no hook, ou None se o hook não existe ou não o traz.

    O pre-commit grava a linha com `shlex.quote`; o `shlex.split` a desfaz.
    """
    if not hook_file.is_file():
        return None
    for line in hook_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("INSTALL_PYTHON="):
            parts = shlex.split(line.partition("=")[2], posix=True)
            return Path(parts[0]) if parts and parts[0] else None
    return None


def dead_hooks(common_dir: Path) -> list[tuple[str, Path]]:
    """Hooks instalados cujo `INSTALL_PYTHON` não existe mais no disco."""
    dead: list[tuple[str, Path]] = []
    for hook_type in HOOK_TYPES:
        python = hook_python(common_dir / "hooks" / hook_type)
        if python is not None and not python.exists():
            dead.append((hook_type, python))
    return dead


def install(cwd: Path) -> int:
    """`pre-commit install` dos dois tipos de hook com o python deste processo."""
    cmd = [sys.executable, "-m", "pre_commit", "install", "--install-hooks"]
    for hook_type in HOOK_TYPES:
        cmd += ["--hook-type", hook_type]
    return subprocess.run(cmd, cwd=str(cwd), check=False).returncode


def main() -> int:
    _force_utf8_stdio()
    try:
        git_dir, common_dir = git_dirs()
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError) as e:
        print(f"ERRO: não consegui ler o repositório git ({e}).", file=sys.stderr)
        return EXIT_ERROR

    if git_dir == common_dir:
        return EXIT_OK if install(main_checkout(common_dir)) == 0 else EXIT_ERROR

    principal = main_checkout(common_dir)
    print(
        f"  • worktree: os hooks do git são do checkout principal ({principal}); nada a instalar."
    )
    dead = dead_hooks(common_dir)
    if not dead:
        return EXIT_OK
    for hook_type, python in dead:
        print(f"ERRO: o hook {hook_type} aponta para {python}, que não existe.", file=sys.stderr)
    print(f"  Religar:\n    cd {principal}\n    {RELINK_HINT}", file=sys.stderr)
    return EXIT_DEAD_HOOK


if __name__ == "__main__":
    raise SystemExit(main())

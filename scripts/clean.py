"""Remove artefatos de build, cache e arquivos gerados.

Chamado por `make clean` — a receita do Makefile é shell-agnostic
(ADR 1.1.0001), então a lógica de varredura/remoção vive aqui, em
Python puro, em vez de `find`/`rm -rf`.

Remove: __pycache__/, *.egg-info/, .pytest_cache/, .mypy_cache/,
.ruff_cache/, dist/, build/, htmlcov/, .coverage, coverage.xml, tree.txt.
Ignora .git/ e .venv/ (caches internos do venv são inofensivos e a
varredura ficaria lenta).
"""

from __future__ import annotations

import shutil
from pathlib import Path

SKIP_DIRS = {".git", ".venv"}
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
ROOT_DIRS = ("dist", "build", "htmlcov")
ROOT_FILES = (".coverage", "coverage.xml", "tree.txt")


def _cache_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in CACHE_DIR_NAMES or path.name.endswith(".egg-info"):
            found.append(path)
    return found


def main() -> int:
    root = Path.cwd()
    removed = 0

    for directory in _cache_dirs(root):
        shutil.rmtree(directory, ignore_errors=True)
        print(f"removido: {directory.relative_to(root)}")
        removed += 1

    for name in ROOT_DIRS:
        directory = root / name
        if directory.is_dir():
            shutil.rmtree(directory, ignore_errors=True)
            print(f"removido: {name}/")
            removed += 1

    for name in ROOT_FILES:
        file = root / name
        if file.is_file():
            file.unlink()
            print(f"removido: {name}")
            removed += 1

    print(f"Artefatos removidos: {removed}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

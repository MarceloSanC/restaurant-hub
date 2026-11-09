"""Unit de `scripts/clean.py` — remoção de artefatos, sempre dentro de `tmp_path`.

O script varre `Path.cwd()`; o `monkeypatch.chdir` o aponta para um repositório de
mentira, de modo que nada fora de `tmp_path` pode ser apagado.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "clean.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("clean", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cl = _load()


def _mkdir(root: Path, rel: str) -> Path:
    path = root / rel
    path.mkdir(parents=True, exist_ok=True)
    (path / "lixo.txt").write_text("x", encoding="utf-8")
    return path


def test_removes_caches_root_dirs_and_root_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cada classe de artefato some, e o total impresso bate com o que foi apagado."""
    caches = [
        _mkdir(tmp_path, "src/pkg/__pycache__"),
        _mkdir(tmp_path, ".pytest_cache"),
        _mkdir(tmp_path, ".mypy_cache"),
        _mkdir(tmp_path, ".ruff_cache"),
        _mkdir(tmp_path, "src/restaurant_hub.egg-info"),
    ]
    root_dirs = [_mkdir(tmp_path, name) for name in cl.ROOT_DIRS]
    root_files = [tmp_path / name for name in cl.ROOT_FILES]
    for file in root_files:
        file.write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cl.main() == 0

    for path in [*caches, *root_dirs, *root_files]:
        assert not path.exists(), path
    out = capsys.readouterr().out
    total = len(caches) + len(root_dirs) + len(root_files)
    assert f"Artefatos removidos: {total}." in out
    assert "removido: dist/" in out
    assert "removido: coverage.xml" in out


def test_keeps_source_git_and_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.git/` e `.venv/` ficam fora da varredura; código-fonte nunca é tocado."""
    git_cache = _mkdir(tmp_path, ".git/hooks/__pycache__")
    venv_cache = _mkdir(tmp_path, ".venv/lib/__pycache__")
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print(1)\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cl.main() == 0

    assert git_cache.is_dir()
    assert venv_cache.is_dir()
    assert source.is_file()
    assert "Artefatos removidos: 0." in capsys.readouterr().out


def test_root_name_that_is_not_the_expected_kind_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dist` como arquivo e `tree.txt` como pasta não casam o tipo esperado: ficam."""
    dist_file = tmp_path / "dist"
    dist_file.write_text("x", encoding="utf-8")
    tree_dir = tmp_path / "tree.txt"
    tree_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    assert cl.main() == 0

    assert dist_file.is_file()
    assert tree_dir.is_dir()
    assert "Artefatos removidos: 0." in capsys.readouterr().out

"""Unit de `scripts/regen_tree.py` — a árvore gerada, escrita só em `tmp_path`.

`main()` grava `OUTPUT` na raiz do repositório; os testes trocam `ROOT` e `OUTPUT`
por um repositório de mentira para que o `tree.txt` real nunca seja escrito.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "regen_tree.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("regen_tree", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rt = _load()


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "meu-repo"
    for rel in ("src/pkg/mod.py", "src/pkg/__pycache__/mod.pyc", "docs/LAYOUT.md"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (root / "src" / "pkg.egg-info").mkdir()
    (root / ".git").mkdir()
    (root / "Makefile").write_text("", encoding="utf-8")
    return root


def test_main_writes_tree_dirs_first_and_skips_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Diretórios antes de arquivos, conectores por posição, caches e o próprio output fora."""
    root = _repo(tmp_path)
    output = root / "tree.txt"
    output.write_text("versão velha", encoding="utf-8")  # não pode se auto-listar
    monkeypatch.setattr(rt, "ROOT", root)
    monkeypatch.setattr(rt, "OUTPUT", output)

    rt.main()

    expected = (
        "meu-repo/\n"
        "├── docs\n"
        "│   └── LAYOUT.md\n"
        "├── src\n"
        "│   └── pkg\n"
        "│       └── mod.py\n"
        "└── Makefile\n"
    )
    assert output.read_text(encoding="utf-8") == expected
    out = capsys.readouterr().out
    assert out.startswith("Escrito: tree.txt\n")
    assert expected in out


def test_should_ignore_matches_names_and_egg_info() -> None:
    """Nome da lista ou sufixo `.egg-info` é ignorado; o resto entra na árvore."""
    assert rt._should_ignore(Path("a/__pycache__"))
    assert rt._should_ignore(Path("restaurant_hub.egg-info"))
    assert not rt._should_ignore(Path("src"))


def test_force_utf8_reconfigures_only_non_utf8_text_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cp1252 vira UTF-8; stream sem `reconfigure` (StringIO) fica como está."""
    cp1252 = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    other = io.StringIO()
    monkeypatch.setattr(sys, "stdout", cp1252)
    monkeypatch.setattr(sys, "stderr", other)

    rt._force_utf8_stdio()

    assert cp1252.encoding == "utf-8"
    assert sys.stderr is other


def test_force_utf8_swallows_oserror_from_reconfigure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falha de `reconfigure` não derruba o script: o encoding só fica o antigo."""

    class _Stubborn(io.TextIOWrapper):
        def reconfigure(self, **_kwargs: object) -> None:
            raise OSError("console não deixa")

    stubborn = _Stubborn(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stubborn)
    monkeypatch.setattr(sys, "stderr", stubborn)

    rt._force_utf8_stdio()

    assert stubborn.encoding == "cp1252"

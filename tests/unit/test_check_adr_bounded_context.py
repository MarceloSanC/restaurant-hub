"""Unit de `scripts/check_adr_bounded_context.py` — BC de ADR vem do roadmap."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_adr_bounded_context.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_adr_bounded_context", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cabc = _load()

# Exit 2: sem conjunto de BC derivável do roadmap (fail closed).
_EXIT_NO_BC_SET = 2

_ROADMAP_TEXT = (
    "# Roadmap\n\n"
    "```yaml\n"
    "bounded_context: identity\n"
    "bounded_context: scheduling (escala + turnos)\n"
    "```\n"
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repo descartável com roadmap válido e pasta de ADRs vazia."""
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    roadmap = tmp_path / "docs" / "roadmap.md"
    roadmap.write_text(_ROADMAP_TEXT, encoding="utf-8")
    monkeypatch.setattr(cabc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cabc, "ROADMAP", roadmap)
    return tmp_path


def _adr(repo: Path, name: str, text: str) -> Path:
    path = repo / "docs" / "adr" / name
    path.write_text(text, encoding="utf-8")
    return path


# --- roadmap_bounded_contexts ---------------------------------------------


def test_roadmap_set_takes_leading_token_and_strips_bom(repo: Path) -> None:
    """O conjunto vem do token inicial de cada linha; BOM é ignorado."""
    cabc.ROADMAP.write_text("﻿" + _ROADMAP_TEXT, encoding="utf-8")
    assert cabc.roadmap_bounded_contexts() == {"identity", "scheduling"}


# --- _frontmatter -----------------------------------------------------------


def test_frontmatter_returns_lines_between_fences() -> None:
    assert cabc._frontmatter("---\na: 1\nb: 2\n---\ncorpo\n") == ["a: 1", "b: 2"]


@pytest.mark.parametrize(
    "text",
    ["", "sem fence\n---\n", "---\na: 1\nnunca fecha\n"],
    ids=["vazio", "sem-fence-inicial", "sem-fence-final"],
)
def test_frontmatter_absent_or_unclosed_is_none(text: str) -> None:
    """Sem fence inicial, vazio ou sem fechamento → None."""
    assert cabc._frontmatter(text) is None


# --- check_adr --------------------------------------------------------------


def test_check_adr_valid_value_with_qualifier(repo: Path) -> None:
    """Qualificador após o token não impede o match."""
    path = _adr(repo, "a.md", "---\nbounded_context: scheduling (algo)\n---\n")
    assert cabc.check_adr(path, {"scheduling"}) is None


def test_check_adr_missing_frontmatter(repo: Path) -> None:
    path = _adr(repo, "a.md", "# ADR sem frontmatter\n")
    msg = cabc.check_adr(path, {"identity"})
    assert msg is not None
    assert "frontmatter YAML ausente" in msg
    assert msg.startswith(str(Path("docs/adr/a.md")))


def test_check_adr_missing_field(repo: Path) -> None:
    path = _adr(repo, "a.md", "---\ntitle: x\n---\nbounded_context: identity\n")
    msg = cabc.check_adr(path, {"identity"})
    assert msg is not None and "falta `bounded_context`" in msg


def test_check_adr_field_without_recognizable_value(repo: Path) -> None:
    """Valor que não começa com [a-z_] (ex.: maiúscula) não é reconhecível."""
    path = _adr(repo, "a.md", "---\nbounded_context: Identity\n---\n")
    msg = cabc.check_adr(path, {"identity"})
    assert msg is not None and "sem valor reconhecivel" in msg


def test_check_adr_value_outside_valid_set(repo: Path) -> None:
    path = _adr(repo, "a.md", "---\nbounded_context: payments\n---\n")
    msg = cabc.check_adr(path, {"identity", "scheduling"})
    assert msg is not None
    assert "bounded_context='payments'" in msg
    assert "(identity, scheduling)" in msg


def test_check_adr_uses_first_declaration_only(repo: Path) -> None:
    """Só a primeira declaração vale; uma segunda inválida é ignorada."""
    path = _adr(repo, "a.md", "---\nbounded_context: identity\nbounded_context: bogus\n---\n")
    assert cabc.check_adr(path, {"identity"}) is None


# --- main -------------------------------------------------------------------


def test_main_fails_closed_when_roadmap_missing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cabc.ROADMAP.unlink()
    assert cabc.main() == _EXIT_NO_BC_SET
    err = capsys.readouterr().err
    assert "roadmap ausente" in err and "fail closed" in err


def test_main_fails_closed_when_roadmap_has_no_bc(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cabc.ROADMAP.write_text("# Roadmap sem BC\n", encoding="utf-8")
    assert cabc.main() == _EXIT_NO_BC_SET
    assert "nenhum `bounded_context` no roadmap" in capsys.readouterr().err


def test_main_ok_accepts_roadmap_bc_and_transversal(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """BC do roadmap e o sentinela `transversal` são aceitos."""
    _adr(repo, "0_0_0001.md", "---\nbounded_context: transversal\n---\n")
    _adr(repo, "2_1_0001.md", "---\nbounded_context: identity\n---\n")
    assert cabc.main() == 0
    assert capsys.readouterr().err == ""


def test_main_ok_with_no_adrs(repo: Path) -> None:
    assert cabc.main() == 0


def test_main_reports_every_violation_sorted(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 1 e cada violação listada, em ordem de arquivo."""
    _adr(repo, "b.md", "---\nbounded_context: payments\n---\n")
    _adr(repo, "a.md", "sem frontmatter\n")
    _adr(repo, "c.md", "---\nbounded_context: identity\n---\n")
    assert cabc.main() == 1
    err = capsys.readouterr().err
    assert "ADRs com bounded_context invalido" in err
    lines = [line.strip() for line in err.splitlines()[1:]]
    assert len(lines) == len(["a.md", "b.md"])
    assert lines[0].startswith(str(Path("docs/adr/a.md")))
    assert lines[1].startswith(str(Path("docs/adr/b.md")))

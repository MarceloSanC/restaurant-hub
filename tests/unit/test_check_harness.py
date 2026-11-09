"""Unit de `scripts/check_harness.py` — frontmatter de skills/subagentes."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_harness.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_harness", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ch = _load()


def _skill(tmp_path: Path, frontmatter: str) -> list[str]:
    path = tmp_path / "SKILL.md"
    path.write_text(f"---\n{frontmatter}\n---\n\ncorpo\n", encoding="utf-8")
    return list(ch.check_file(path, ch.SKILL_FIELDS, ()))


def test_clean_skill_has_no_findings(tmp_path: Path) -> None:
    assert _skill(tmp_path, "name: x\ndescription: Faz X quando Y.") == []


def test_plain_scalar_hash_truncation_is_caught(tmp_path: Path) -> None:
    # caso real da issue-audit: ` #` sem aspas vira comentário YAML
    found = _skill(tmp_path, "description: Audita o CORPO (## Escopo + ## Critério) da issue")
    assert any("truncada" in f for f in found)


def test_quoted_hash_is_fine(tmp_path: Path) -> None:
    assert _skill(tmp_path, 'description: "Audita o CORPO (## Escopo) com \\"aspas\\""') == []


def test_unknown_field_and_invalid_yaml(tmp_path: Path) -> None:
    assert any("desconhecido" in f for f in _skill(tmp_path, "description: x\nallowed_tools: Read"))
    assert any("YAML inválido" in f for f in _skill(tmp_path, "description: a: b: c"))


def test_description_over_listing_cap(tmp_path: Path) -> None:
    long_desc = "x" * (ch.DESC_CAP + 1)
    assert any("cortada" in f for f in _skill(tmp_path, f"description: {long_desc}"))


def test_agent_requires_name_and_description(tmp_path: Path) -> None:
    path = tmp_path / "agent.md"
    path.write_text("---\nmodel: opus\n---\nprompt\n", encoding="utf-8")
    found = ch.check_file(path, ch.AGENT_FIELDS, ("name", "description"))
    assert len([f for f in found if "obrigatório" in f]) == len(("name", "description"))


def test_overrides_must_point_to_existing_skills(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"skillOverrides": {"ghost": "off"}}), encoding="utf-8")
    assert ch.check_overrides(settings, {"real"}) == [
        "skillOverrides aponta skill inexistente: `ghost`"
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("name: x\n", "sem frontmatter"),
        ("---\nname: x\n", "sem `---` de fechamento"),
        ("---\n- a\n- b\n---\ncorpo\n", "não é um mapa YAML"),
    ],
)
def test_malformed_frontmatter_is_reported(tmp_path: Path, text: str, expected: str) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    found = ch.check_file(path, ch.SKILL_FIELDS, ())
    assert len(found) == 1
    assert expected in found[0]


def test_missing_settings_has_no_override_findings(tmp_path: Path) -> None:
    assert ch.check_overrides(tmp_path / "settings.json", set()) == []


def _harness(root: Path, skill_fm: str, agent_fm: str, overrides: dict[str, str]) -> None:
    skill = root / ".claude" / "skills" / "real" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"---\n{skill_fm}\n---\ncorpo\n", encoding="utf-8")
    agent = root / ".claude" / "agents" / "revisor.md"
    agent.parent.mkdir(parents=True)
    agent.write_text(f"---\n{agent_fm}\n---\nprompt\n", encoding="utf-8")
    settings = root / ".claude" / "settings.json"
    settings.write_text(json.dumps({"skillOverrides": overrides}), encoding="utf-8")


def test_main_clean_harness_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _harness(tmp_path, "description: X.", "name: r\ndescription: Y.", {"real": "off"})
    monkeypatch.setattr(ch, "ROOT", tmp_path)
    assert ch.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "0 achado(s)" in captured.err


def test_main_reports_findings_with_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Skill, agente e override com defeito: um achado de cada, exit 1."""
    _harness(tmp_path, "description: x\nbogus: 1", "description: Y.", {"ghost": "off"})
    monkeypatch.setattr(ch, "ROOT", tmp_path)
    assert ch.main() == 1
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    skill_rel = str(Path(".claude/skills/real/SKILL.md"))
    agent_rel = str(Path(".claude/agents/revisor.md"))
    assert any(line.startswith(f"{skill_rel}: campo desconhecido") for line in lines)
    assert any(line.startswith(f"{agent_rel}: campo obrigatório ausente: `name`") for line in lines)
    assert "skillOverrides aponta skill inexistente: `ghost`" in lines
    assert f"{len(lines)} achado(s)" in captured.err

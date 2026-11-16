"""Unit de `scripts/check_harness.py` — frontmatter e estrutura de skills, subagentes e hooks."""

from __future__ import annotations

import importlib.util
import json
import re
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
    monkeypatch.setattr(ch, "KNOWN_DEBT", {})  # o débito do repo não existe no tmp_path
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
    monkeypatch.setattr(ch, "KNOWN_DEBT", {})  # o débito do repo não existe no tmp_path
    assert ch.main() == 1
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    skill_rel = str(Path(".claude/skills/real/SKILL.md"))
    agent_rel = str(Path(".claude/agents/revisor.md"))
    assert any(line.startswith(f"{skill_rel}: campo desconhecido") for line in lines)
    assert any(line.startswith(f"{agent_rel}: campo obrigatório ausente: `name`") for line in lines)
    assert "skillOverrides aponta skill inexistente: `ghost`" in lines
    assert f"{len(lines)} achado(s)" in captured.err


# --- estrutura de skill, subagente e hooks (issue #65, port da FF#161) ---


def _skill_dir(root: Path, body: str, name: str = "demo") -> Path:
    skill = root / ".claude" / "skills" / name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(f"---\nname: {name}\ndescription: x\n---\n{body}", encoding="utf-8")
    return skill


def _layout(root: Path, skill: Path) -> dict[str, str]:
    return dict(ch.check_skill_layout(skill, root))


def test_clean_skill_layout(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "Ver [regra](reference/rule.md) e `scripts/run.py`.\n")
    (skill.parent / "reference").mkdir()
    (skill.parent / "reference" / "rule.md").write_text("# Regra\n", encoding="utf-8")
    (skill.parent / "scripts").mkdir()
    (skill.parent / "scripts" / "run.py").write_text("", encoding="utf-8")

    assert _layout(tmp_path, skill) == {}


def test_body_over_500_lines_counts_only_the_body(tmp_path: Path) -> None:
    at_cap = _skill_dir(tmp_path, "x\n" * ch.SKILL_BODY_CAP, name="at-cap")
    over = _skill_dir(tmp_path, "x\n" * (ch.SKILL_BODY_CAP + 1), name="over")

    assert _layout(tmp_path, at_cap) == {}
    assert list(_layout(tmp_path, over)) == [".claude/skills/over::body"]


def test_reference_must_be_one_level_and_linked(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "sem links\n")
    nested = skill.parent / "reference" / "deep"
    nested.mkdir(parents=True)
    (skill.parent / "reference" / "orphan.md").write_text("# x\n", encoding="utf-8")

    assert set(_layout(tmp_path, skill)) == {
        ".claude/skills/demo/reference/deep::depth",
        ".claude/skills/demo/reference/orphan.md::unlinked",
    }


@pytest.mark.parametrize(
    ("head", "ok"),
    [
        pytest.param("# Tema\n\n## Sumário\n", True, id="titulo-sumario"),
        pytest.param("# Topic\n\n## Contents\n", True, id="titulo-contents"),
        pytest.param("# Tema\n- [A](#a)\n- [B](#b)\n", True, id="links-de-ancora"),
        pytest.param("# Tema\n- [A](#a)\n", False, id="um-link-so"),
        pytest.param("# Tema\n\ntexto\n", False, id="sem-sumario"),
    ],
)
def test_long_reference_needs_a_table_of_contents(tmp_path: Path, head: str, ok: bool) -> None:
    skill = _skill_dir(tmp_path, "[r](references/long.md)\n")
    ref = skill.parent / "references" / "long.md"
    ref.parent.mkdir()
    ref.write_text(head + "linha\n" * ch.TOC_THRESHOLD, encoding="utf-8")

    found = _layout(tmp_path, skill)

    assert (".claude/skills/demo/references/long.md::toc" not in found) is ok


def test_short_reference_needs_no_table_of_contents(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "[r](reference/short.md)\n")
    ref = skill.parent / "reference" / "short.md"
    ref.parent.mkdir()
    ref.write_text("linha\n" * ch.TOC_THRESHOLD, encoding="utf-8")

    assert _layout(tmp_path, skill) == {}


def test_cited_files_must_exist_relative_to_skill_or_root(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gate.py").write_text("", encoding="utf-8")
    body = (
        "Roda `scripts/gate.py` e `scripts/ghost.py`; ver [doc](docs/missing.md), "
        "[site](https://x.org/a.md) e [exemplo](caminho).\n"
    )
    skill = _skill_dir(tmp_path, body)

    assert set(_layout(tmp_path, skill)) == {
        ".claude/skills/demo::missing:scripts/ghost.py",
        ".claude/skills/demo::missing:docs/missing.md",
    }


# --- conteúdo de reference/ e âncora de link (issue #196) ---

_DEMO = ".claude/skills/demo"
_REAL_SKILLS = Path(__file__).resolve().parents[2] / ".claude" / "skills"


def _reference(skill: Path, name: str, text: str) -> Path:
    ref = skill.parent / "reference" / name
    ref.parent.mkdir(exist_ok=True)
    ref.write_text(text, encoding="utf-8")
    return ref


def test_reference_content_and_anchors_happy_path(tmp_path: Path) -> None:
    """Os três sentidos de âncora, link relativo ao próprio arquivo e script: nada a acusar."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gate.py").write_text("", encoding="utf-8")
    skill = _skill_dir(
        tmp_path,
        "## Fase B\n\nVer [Gate inerte](reference/cat.md#gate-inerte-ou-míope), "
        "[outro](reference/outro.md) e [início](#fase-b).\n",
    )
    (skill.parent / "scripts").mkdir()
    (skill.parent / "scripts" / "run.py").write_text("", encoding="utf-8")
    _reference(skill, "outro.md", "# Outro\n")
    _reference(
        skill,
        "cat.md",
        "# Catálogo\n\n- [Gate inerte ou míope](#gate-inerte-ou-míope)\n\n"
        "### Gate inerte ou míope\n\n"
        "Usado na [Fase B](../SKILL.md#fase-b); ver [outro](outro.md#outro).\n"
        "Roda `scripts/gate.py` (raiz) e `scripts/run.py` (da skill).\n",
    )

    assert _layout(tmp_path, skill) == {}


def test_broken_link_inside_reference_is_reported(tmp_path: Path) -> None:
    """O link de `reference/` resolve da pasta do próprio arquivo, não da pasta da skill."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guia.md").write_text("# Guia\n", encoding="utf-8")
    skill = _skill_dir(tmp_path, "[catálogo](reference/cat.md)\n")
    _reference(
        skill,
        "cat.md",
        "[volta](../SKILL.md), [sumiu](../SKILL-inexistente.md), [irmão](reference/cat.md) "
        "e [raiz](docs/guia.md).\n",
    )

    assert set(_layout(tmp_path, skill)) == {
        f"{_DEMO}/reference/cat.md::missing:../SKILL-inexistente.md",
        f"{_DEMO}/reference/cat.md::missing:reference/cat.md",
    }


def test_missing_script_cited_inside_reference_is_reported(tmp_path: Path) -> None:
    """Script citado só em `reference/` é conferido, bloco de código incluso (é onde aparece)."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gate.py").write_text("", encoding="utf-8")
    skill = _skill_dir(tmp_path, "[mapa](reference/mapa.md)\n")
    _reference(
        skill,
        "mapa.md",
        "| critério | onde |\n|---|---|\n| layout | `scripts/gate.py` |\n\n"
        "```bash\nuv run python scripts/nao_existe.py\n```\n",
    )

    found = _layout(tmp_path, skill)

    assert found == {
        f"{_DEMO}/reference/mapa.md::missing:scripts/nao_existe.py": (
            "cita `scripts/nao_existe.py`, que não existe"
        )
    }


def test_anchor_from_skill_to_reference_must_match_a_heading(tmp_path: Path) -> None:
    skill = _skill_dir(
        tmp_path,
        "[certo](reference/cat.md#gate-inerte-ou-míope) e [morto](reference/cat.md#gate-inerte)\n",
    )
    _reference(skill, "cat.md", "### Gate inerte ou míope\n")

    found = _layout(tmp_path, skill)

    assert found == {
        f"{_DEMO}::anchor:reference/cat.md#gate-inerte": (
            "âncora `reference/cat.md#gate-inerte` não casa com título de `cat.md`"
        )
    }


def test_anchor_from_reference_back_to_skill_must_match_a_heading(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "## Fase B\n\n[catálogo](reference/cat.md)\n")
    _reference(skill, "cat.md", "[certo](../SKILL.md#fase-b) e [morto](../SKILL.md#fase-z)\n")

    assert set(_layout(tmp_path, skill)) == {f"{_DEMO}/reference/cat.md::anchor:../SKILL.md#fase-z"}


def test_internal_anchor_must_match_a_heading_of_the_same_file(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "## Topo\n\n[certo](#topo) e [morto](#fundo)\n")

    assert set(_layout(tmp_path, skill)) == {f"{_DEMO}::anchor:#fundo"}


def test_table_of_contents_with_a_false_anchor_is_reported(tmp_path: Path) -> None:
    """Sumário que cita título inexistente: o `has_toc` conta o link, não confere o alvo."""
    skill = _skill_dir(tmp_path, "[catálogo](reference/cat.md)\n")
    _reference(
        skill,
        "cat.md",
        "# Catálogo\n\n## Sumário\n\n- [Literal ≠ espírito](#literal--espírito)\n"
        "- [Renomeado](#nome-antigo)\n\n### Literal ≠ espírito\n\n### Nome novo\n",
    )

    assert set(_layout(tmp_path, skill)) == {f"{_DEMO}/reference/cat.md::anchor:#nome-antigo"}


def test_anchor_of_a_missing_file_reports_only_the_file(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "[morto](reference/sumiu.md#titulo)\n")

    assert set(_layout(tmp_path, skill)) == {f"{_DEMO}::missing:reference/sumiu.md"}


def test_fenced_code_block_holds_no_link_and_no_heading(tmp_path: Path) -> None:
    """Template de relatório em bloco cercado: o link de exemplo não conta, o título também não."""
    body = (
        "[a](#titulo-do-template)\n\n"
        "```markdown\n## Titulo do template\n[arquivo](pasta/sumiu.md) [x](#nao-existe)\n```\n\n"
        "~~~\n[arquivo](pasta/sumiu-til.md)\n~~~\n\n"
        "1. passo de lista:\n\n     ```\n     [arquivo](pasta/sumiu-lista.md)\n     ```\n"
    )
    skill = _skill_dir(tmp_path, body)

    assert set(_layout(tmp_path, skill)) == {f"{_DEMO}::anchor:#titulo-do-template"}


@pytest.mark.parametrize(
    ("block", "inside"),
    [
        # só a mesma marca, de tamanho igual ou maior e sem mais nada na linha, fecha o bloco
        pytest.param("```\n```bash\n{link}\n```\n", True, id="abertura-nao-fecha"),
        pytest.param("````\n```\n{link}\n````\n", True, id="cerca-menor-nao-fecha"),
        pytest.param("```\n~~~\n{link}\n```\n", True, id="outra-marca-nao-fecha"),
        pytest.param("```\n{link}\n", True, id="sem-fechamento-vai-ate-o-fim"),
        pytest.param("```\ncódigo\n```\n{link}\n", False, id="depois-do-fechamento"),
        pytest.param("```\ncódigo\n`````\n{link}\n", False, id="fechamento-maior"),
        pytest.param("```código``` em linha\n{link}\n", False, id="codigo-em-linha"),
    ],
)
def test_fence_boundaries(tmp_path: Path, block: str, inside: bool) -> None:
    skill = _skill_dir(tmp_path, block.replace("{link}", "[x](pasta/sumiu.md)"))

    assert (_layout(tmp_path, skill) == {}) is inside


def test_placeholder_external_and_non_markdown_targets_do_not_fail(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gate.py").write_text("", encoding="utf-8")
    body = (
        "[exemplo](caminho), [exemplo](caminho#secao), [site](https://x.org/a.md#frag), "
        "[mail](mailto:a@b.c), [linha](scripts/gate.py#L10), [vazio](#) e [nada]().\n"
    )
    skill = _skill_dir(tmp_path, "[r](reference/r.md)\n" + body)
    _reference(skill, "r.md", body)

    assert _layout(tmp_path, skill) == {}


def test_percent_encoded_anchor_resolves(tmp_path: Path) -> None:
    skill = _skill_dir(tmp_path, "## Gate míope\n\n[a](#gate-m%C3%ADope) [b](#gate-m%C3%ADopes)\n")

    assert set(_layout(tmp_path, skill)) == {f"{_DEMO}::anchor:#gate-m%C3%ADopes"}


@pytest.mark.parametrize(
    ("title", "anchor"),
    [
        # Pares (título do repo, id que o GitHub gerou), lidos do HTML de
        # `gh api repos/<repo>/contents/<arquivo> -H "Accept: application/vnd.github.html+json"`.
        ("Literal ≠ espírito", "literal--espírito"),
        ("Gate inerte ou míope", "gate-inerte-ou-míope"),
        ("Definido mas não plugado (dead-config)", "definido-mas-não-plugado-dead-config"),
        ("Lei universal, representante estreito", "lei-universal-representante-estreito"),
        (
            "Referência da stage-audit — catálogo de falsos verdes",
            "referência-da-stage-audit--catálogo-de-falsos-verdes",
        ),
        (
            "Fase D — Judgment (a parte que NÃO se mecaniza)",
            "fase-d--judgment-a-parte-que-não-se-mecaniza",
        ),
        (
            "2. O que é → o que faz no sistema → por que importa",
            "2-o-que-é--o-que-faz-no-sistema--por-que-importa",
        ),
        ("DON'T", "dont"),
        (
            "🚦 Iniciar uma Stage (antes de qualquer passo do RUNBOOK)",
            "-iniciar-uma-stage-antes-de-qualquer-passo-do-runbook",
        ),
        # o seletor de variação do emoji (U+FE0F, marca combinante) fica no id
        (
            "✍\N{VARIATION SELECTOR-16} `git commit -m`",
            "\N{VARIATION SELECTOR-16}-git-commit--m",
        ),
        (
            "Identificador da Stage — `stage_id` × número",  # noqa: RUF001 — título real
            "identificador-da-stage--stage_id--número",
        ),
        (
            "(a) Commits de Task — Conventional Commits + `[N.M/task-NN]` + `Refs #<issue>`",
            "a-commits-de-task--conventional-commits--nmtask-nn--refs-issue",
        ),
        # CHANGELOG do keep-a-changelog (link por referência no título), mesma medição
        ("[1.1.1] - 2023-03-05", "111---2023-03-05"),
        # da doc do GitHub ("Markup formatting is removed"), sem título no repo para medir
        ("[Guia](docs/guia.md#topo) rápido", "guia-rápido"),
    ],
)
def test_slug_matches_the_anchor_github_generates(title: str, anchor: str) -> None:
    assert ch._slug(title) == anchor


def test_heading_anchors_number_repeated_titles_and_skip_what_is_not_a_title() -> None:
    text = (
        "---\n# comentário do frontmatter\nname: x\n---\n"
        "# Added\n\n## Added ##\n\n### Added\n\n#sem-espaço\n\n    # código indentado\n\n"
        "```\n# comentário de shell\n```\n"
    )

    assert ch.heading_anchors(text) == {"added", "added-1", "added-2"}


def _copy_real_skill(name: str, root: Path) -> Path:
    skill = root / ".claude" / "skills" / name / "SKILL.md"
    skill.parent.mkdir(parents=True)
    (skill.parent / "reference").mkdir()
    for source in (_REAL_SKILLS / name).rglob("*.md"):
        target = skill.parent / source.relative_to(_REAL_SKILLS / name)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return skill


def _anchor_findings(root: Path, skill: Path) -> set[str]:
    return {key for key in _layout(root, skill) if "::anchor:" in key}


@pytest.mark.parametrize(("name", "floor"), [("stage-audit", 20), ("issue-audit", 16)])
def test_real_audit_skills_anchors_are_all_checked(tmp_path: Path, name: str, floor: int) -> None:
    """Piso sobre as skills reais: sem os títulos do catálogo, cada âncora para ele reprova.

    O `test_real_harness_passes` fica verde tanto com as âncoras conferidas quanto com o
    check cego. Este mede quantas ele enxerga: a cópia intacta não acusa nenhuma, e a
    cópia com o catálogo sem títulos acusa as do `SKILL.md` e as do sumário (26 na
    `stage-audit` e 22 na `issue-audit` em 2026-11-16; o piso deixa folga para edição).
    """
    skill = _copy_real_skill(name, tmp_path)
    catalog = skill.parent / "reference" / "falso-verde.md"
    assert _anchor_findings(tmp_path, skill) == set()

    text = catalog.read_text(encoding="utf-8")
    catalog.write_text(re.sub(r"(?m)^#+ ", "", text), encoding="utf-8")
    found = _anchor_findings(tmp_path, skill)

    from_skill = {key for key in found if key.startswith(f".claude/skills/{name}::")}
    assert len(found) >= floor
    assert from_skill and found - from_skill  # do SKILL.md e do sumário do próprio catálogo


@pytest.mark.parametrize("name", ["stage-audit", "issue-audit"])
def test_renaming_a_real_catalog_title_is_reported(tmp_path: Path, name: str) -> None:
    """Critério da #196: renomear um título de conceito do catálogo reprova."""
    skill = _copy_real_skill(name, tmp_path)
    catalog = skill.parent / "reference" / "falso-verde.md"
    lines = catalog.read_text(encoding="utf-8").splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("### "))
    lines[index] += " renomeado"
    catalog.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert _anchor_findings(tmp_path, skill)


def test_agent_skills_must_exist(tmp_path: Path) -> None:
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: a\ndescription: b\nskills: [real, ghost]\n---\n", encoding="utf-8")

    assert ch.check_agent_skills(agent, {"real"}) == ["`skills:` aponta skill inexistente: `ghost`"]


def test_agent_skills_as_comma_string_and_broken_frontmatter(tmp_path: Path) -> None:
    agent = tmp_path / "agent.md"
    agent.write_text("---\nname: a\ndescription: b\nskills: real, ghost\n---\n", encoding="utf-8")
    assert ch.check_agent_skills(agent, {"real"}) == ["`skills:` aponta skill inexistente: `ghost`"]

    agent.write_text("sem frontmatter\n", encoding="utf-8")
    assert ch.check_agent_skills(agent, {"real"}) == []  # o check_file já reporta


def test_hook_scripts_without_settings(tmp_path: Path) -> None:
    assert ch.check_hook_scripts(tmp_path / "settings.json", tmp_path) == []


def test_hook_scripts_must_exist(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks" / "real.py").write_text("", encoding="utf-8")
    hook = {"type": "command", "command": "python"}
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "hooks": [
                                {**hook, "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/real.py"]}
                            ]
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    **hook,
                                    "command": "python ${CLAUDE_PROJECT_DIR}/.claude/hooks/x.py",
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    assert ch.check_hook_scripts(settings, tmp_path) == [
        "hook aponta arquivo inexistente: `.claude/hooks/x.py`"
    ]


def test_known_debt_tolerates_shrinks_and_needs_an_owner() -> None:
    found = {"a/skill::body": "corpo longo", "b/skill::body": "corpo longo"}
    debt = {"a/skill::body": ("legado", 7), "gone::toc": ("legado", 7), "b/skill::body": ("", 7)}

    assert ch.reconcile_debt(found, debt) == [
        "b/skill: corpo longo",
        "KNOWN_DEBT `gone::toc` não ocorre mais (remover a entrada)",
        "KNOWN_DEBT `b/skill::body` sem motivo ou issue (débito sem dono)",
    ]


def test_known_debt_stays_empty() -> None:
    """A lista só encolhe, e zerou na #162: reabri-la é decisão que muda este teste.

    O `reconcile_debt` cobra cada entrada (viva e com dono), nunca o conjunto. Sem esta
    asserção, uma skill acima do teto entraria em `KNOWN_DEBT` com a suíte verde, e o
    débito voltaria a crescer calado, como cresceu entre a #65 e a #162.
    """
    assert ch.KNOWN_DEBT == {}


def test_real_harness_passes() -> None:
    """O harness do repo (skills, subagentes, settings) passa com o débito declarado."""
    assert ch.main() == 0


def test_body_without_frontmatter_is_the_whole_text() -> None:
    assert ch._body("sem frontmatter\n") == "sem frontmatter\n"


def test_hook_settings_with_non_string_values_and_no_file(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    hook = {"type": "command", "timeout": 5, "async": True, "args": ["x"]}
    settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [hook]}]}}), encoding="utf-8")

    assert ch.check_hook_scripts(settings, tmp_path) == []
    assert ch.check_hook_scripts(tmp_path / "ausente.json", tmp_path) == []

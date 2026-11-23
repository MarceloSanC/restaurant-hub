"""O gate do campo `Verificado:` nos registros `[decision:E|C]` (issue #212).

**O que o gate protege.** A skill `evidence-resolution` §5 grava cada fork E/C com
o campo `Verificado:` de vocabulário fechado. O concept da Stage 2.7 foi aprovado
com `Verificado: ver §7 do technical (...)`, uma verificação que ainda não existia,
e o `make docs-check` não olhava o campo. O gate reprova campo ausente, repetido ou
fora do vocabulário, e deixa passar, sem edição, os registros anteriores (o corte).

**A forma vem da skill real.** O registro "bom" dos testes é o bloco do §5 da
skill com os campos preenchidos, e o vocabulário do gate é comparado com a linha
`Verificado:` de lá: se a skill mudar a forma, estes testes reprovam antes de
reprovar o primeiro concept que a seguir.

**Os docs são plantados num repositório de mentira** em `tmp_path` (o script
recebe `repo_root`). Os testes do fim rodam contra os docs reais.
"""

import importlib.util
import pathlib
import re
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_decision_records.py"
_SKILL = _REPO_ROOT / ".claude" / "skills" / "evidence-resolution" / "SKILL.md"


def _load_script() -> types.ModuleType:
    """Importa `scripts/check_decision_records.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_decision_records", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_script()

_FATAL_EXIT = 2
_NEW_STAGE = "9.9-brand-new"
_NEW_ADR = "9_9_0001-brand-new.md"
_SKILL_TEXT = _SKILL.read_text(encoding="utf-8")
# O bloco do formato no §5 da skill, como está escrito nela.
_SKILL_RECORD = re.search(
    r"## 5\. .*?```\n(?P<block>\[decision:E\|C\].*?)```", _SKILL_TEXT, re.DOTALL
)
assert _SKILL_RECORD is not None, "o §5 da evidence-resolution perdeu o bloco do formato"
_TEMPLATE_LINES = _SKILL_RECORD.group("block").splitlines()
_TEMPLATE_VERIFIED = next(line for line in _TEMPLATE_LINES if line.startswith("Verificado:"))


def _record(verified: str | None = "Verificado: sustenta", record_id: str = "D1") -> str:
    """O bloco do §5 preenchido, numa cerca nua, com a linha `Verificado:` pedida (ou sem ela)."""
    lines = [
        f"[decision:C] {record_id} — onde mora a regra",
        "Escolha: no use case · Alternativas: no adapter · Degrau (C): 1",
        'Base: LAYOUT §5 › "O use case depende da interface"',
    ]
    if verified is not None:
        lines.append(verified)
    lines.append("Configuração candidata: nenhuma · Reversível: sim")
    return "```\n" + "\n".join(lines) + "\n```\n"


def _concept(*blocks: str, status: str = "done") -> str:
    """Um concept com frontmatter e os blocos pedidos na §7."""
    body = "\n".join(blocks)
    return f"---\ntitle: X\nstatus: {status}\n---\n\n# Concept\n\n## 7. Decisões\n\n{body}\n"


def _repo(
    tmp_path: pathlib.Path,
    concepts: dict[str, str] | None = None,
    adrs: dict[str, str] | None = None,
) -> pathlib.Path:
    """Um repositório de mentira com os concepts (por pasta de Stage) e os ADRs pedidos."""
    for stage, content in (concepts or {}).items():
        path = tmp_path / "docs" / "stages" / stage / "concept.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for name, content in (adrs or {}).items():
        path = tmp_path / "docs" / "adr" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def _problems(text: str) -> list[str]:
    found: list[str] = gate.file_problems(text, "x.md", frozenset())
    return found


# ---------------------------------------------------------------------------
# O vocabulário: o que passa
# ---------------------------------------------------------------------------


def test_the_vocabulary_is_the_skill_vocabulary() -> None:
    """O gate e o §5 da skill falam os mesmos três termos, na mesma grafia."""
    terms = tuple(
        term.strip() for term in _TEMPLATE_VERIFIED.removeprefix("Verificado:").split("|")
    )
    assert terms == gate.VOCABULARY


@pytest.mark.parametrize("term", gate.VOCABULARY)
def test_each_term_alone_passes(term: str) -> None:
    assert _problems(_concept(_record(f"Verificado: {term}"))) == []


@pytest.mark.parametrize(
    "value",
    [
        "sustenta — evidence-verifier no Checkpoint A (2026-11-20), 4/4 itens",
        "sustenta (evidence-verifier, 2026-11-09, 6/6 items); completeness by decision-reviewer",
        "parcial→corrigido — a citação do ADR 2.2.0002 trocou de seção",
        "não verificado (§4.2) — decisão de processo, fora de port, schema, OpenAPI e segurança",
        "não verificado (§4.2)",
        "`sustenta`",
    ],
)
def test_a_term_followed_by_free_text_passes(value: str) -> None:
    assert _problems(_concept(_record(f"Verificado: {value}"))) == []


def test_the_skill_template_filled_passes() -> None:
    """O bloco do §5 da skill, com cada linha preenchida como o formato pede, passa."""
    labels = [line.split(" ", 1)[0] for line in _TEMPLATE_LINES]
    assert labels == ["[decision:E|C]", "Escolha:", "Base:", "Verificado:", "Configuração"]
    filled = [
        "[decision:E] D1 — x",
        "Escolha: a · Alternativas: b · Degrau (C): 1",
        'Base: RFC 9110 §15.5.5 "404"',
        "Verificado: parcial→corrigido",
        "Configuração candidata: nenhuma · Reversível: sim",
    ]
    assert _problems("```\n" + "\n".join(filled) + "\n```\n") == []


def test_the_skill_template_copied_without_choosing_is_rejected() -> None:
    """A linha do template (`sustenta | parcial→corrigido | ...`) não é uma escolha."""
    [problem] = _problems(_concept(_record(_TEMPLATE_VERIFIED)))
    assert "fora do vocabulário" in problem


# ---------------------------------------------------------------------------
# Fora do vocabulário, ausente, repetido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "ver §7 do technical (evidence-verifier, Checkpoint A)",  # o caso da 2.7 (PR #187)
        "não se aplica o §4.2 (decisão de processo)",  # o caso do ADR 0.0.0022
        "sustentado",
        "Sustenta",
        "nao verificado (§4.2)",
        "não verificado",
        "não verificado §4.2",
        "parcial",
        "parcial->corrigido",
        "parcial → corrigido",
        "sim",
        "",
    ],
)
def test_a_value_outside_the_vocabulary_is_rejected(value: str) -> None:
    [problem] = _problems(_concept(_record(f"Verificado: {value}")))
    assert "fora do vocabulário" in problem
    assert "registro D1" in problem


def test_a_record_without_the_field_is_rejected() -> None:
    [problem] = _problems(_concept(_record(None)))
    assert "registro D1 sem o campo 'Verificado:" in problem


def test_a_record_with_two_fields_is_rejected() -> None:
    text = _concept(_record("Verificado: sustenta\nVerificado: não verificado (§4.2)"))
    [problem] = _problems(text)
    assert "2 campos 'Verificado:'" in problem


def test_a_label_in_another_case_counts_as_missing() -> None:
    """Fail-closed: rótulo fora da grafia não é o campo, e o registro fica sem ele."""
    [problem] = _problems(_concept(_record("verificado: sustenta")))
    assert "sem o campo" in problem


def test_each_record_is_judged_on_its_own() -> None:
    text = _concept(_record("Verificado: sustenta", "D1"), _record(None, "D2"))
    [problem] = _problems(text)
    assert "registro D2" in problem


def test_the_reported_line_is_the_record_header() -> None:
    text = _concept(_record("Verificado: ok"))
    [problem] = _problems(text)
    line = text.splitlines().index("[decision:C] D1 — onde mora a regra") + 1
    assert problem.startswith(f"x.md:{line}: ")


# ---------------------------------------------------------------------------
# As formas de escrever o registro que o projeto usa
# ---------------------------------------------------------------------------

_ONE_LINE = (
    "- `[decision:C] D5 — substituir ou delta. Escolha: substituir · Alternativas: delta · "
    "Degrau (C): 1 · Verificado: {value} · Configuração candidata: nenhuma · Reversível: sim.`"
)
_HEADING = (
    "### [decision:C] D1 — onde vive a indisponibilidade\n"
    "Escolha: no avaliador · Alternativas: no use case · Degrau: 1 ·\n"
    "Verificado: {value} · Reversível: sim. ADR 4.2.0002.\n"
)
_BACKTICK_HEADER = (
    "`[decision:C] 0.0.0012 — how other docs cite the roadmap`\n"
    "Escolha: anchor · Alternativas: remap per PR · Degrau (C): 4\n"
    "Verificado: {value}\n"
    "Configuração candidata: nenhuma · Reversível: sim\n"
)
_BOLD = (
    "- **[decision:E]** não é cabeçalho; o registro abaixo é:\n\n"
    "[decision:E] D2 — horas na interseção\n"
    "**Escolha:** soma por alocação\n"
    "**Verificado:** {value}\n"
)
_BLOCKQUOTE = "> [decision:C] D3 — x\n> Escolha: a · Degrau (C): 5\n> Verificado: {value}\n"


@pytest.mark.parametrize(
    "shape",
    [_ONE_LINE, _HEADING, _BACKTICK_HEADER, _BOLD, _BLOCKQUOTE],
    ids=["one-line-bullet", "heading", "backtick-header", "bold-labels", "blockquote"],
)
def test_the_project_shapes_are_checked(shape: str) -> None:
    """Cada forma em uso passa com um termo e reprova com texto livre (mutação da forma)."""
    assert _problems(_concept(shape.format(value="não verificado (§4.2) — fonte interna"))) == []
    [problem] = _problems(_concept(shape.format(value="conferido pelo revisor")))
    assert "fora do vocabulário" in problem


def test_the_one_line_value_ends_at_the_next_field() -> None:
    """No registro de uma linha, o valor vai até o próximo ` · `, não até o fim da linha."""
    text = _concept(_ONE_LINE.format(value="sustenta"))
    [record] = gate.records(text)
    assert gate.verified_values(record) == ["sustenta"]


def test_a_mention_without_the_choice_field_is_not_a_record() -> None:
    """A tag no começo de uma frase corrida (`[decision:C] rung 1 — ...`) é menção."""
    text = _concept(
        "   [decision:C] rung 1 — the invitation use case exists and already does this.",
        "- **Por quê:** `[decision:C]` degrau 1 — LAYOUT §4.",
        "- **Why rejected:** [decision:E] still two operations.",
    )
    assert gate.records(text) == []
    assert _problems(text) == []


def test_a_choice_field_in_another_case_still_makes_a_record() -> None:
    """Na dúvida, o bloco é registro: `escolha:` minúsculo não o tira do gate."""
    text = _concept("[decision:C] D9 — x\nescolha: a")
    [problem] = _problems(text)
    assert "sem o campo" in problem


def test_a_plain_decision_tag_is_not_scanned() -> None:
    """`[decision] P delegado` é fork P, sem o formato do §5."""
    text = _concept("- `[decision] P delegado — recusar, motivo: fail-closed. Escolha: recusar`")
    assert gate.records(text) == []


def test_the_record_ends_at_the_blank_line() -> None:
    """O `Verificado:` de um parágrafo seguinte não é do registro."""
    text = _concept("[decision:C] D1 — x\nEscolha: a\n\nVerificado: sustenta\n")
    [problem] = _problems(text)
    assert "sem o campo" in problem


@pytest.mark.parametrize("language", ["markdown", "text", "python", "md"])
def test_a_record_in_a_fence_with_a_language_is_ignored(language: str) -> None:
    """Cerca com linguagem é citação ou código: um exemplo ali não é registro."""
    fenced = f"```{language}\n[decision:C] D1 — x\nEscolha: a\nVerificado: talvez\n```\n"
    assert _problems(_concept(fenced)) == []


def test_a_bare_fence_is_the_record_container() -> None:
    """Cerca nua é a forma do template do §5 e é conferida."""
    [problem] = _problems(_concept(_record("Verificado: talvez")))
    assert "fora do vocabulário" in problem


def test_a_record_after_a_quoted_fence_is_checked() -> None:
    text = _concept("```markdown\n[decision:C] D0 — x\nEscolha: a\n```\n", _record(None, "D2"))
    [problem] = _problems(text)
    assert "registro D2" in problem


def test_a_longer_fence_keeps_inner_fences_inside() -> None:
    """Cerca de quatro crases com linguagem engole a de três dentro dela."""
    inner = "````markdown\n```\n[decision:C] D1 — x\nEscolha: a\n```\n````\n"
    assert _problems(_concept(inner)) == []


# ---------------------------------------------------------------------------
# Quem é varrido: concept fora de draft, ADR sempre, o corte
# ---------------------------------------------------------------------------


def test_a_draft_concept_is_skipped(tmp_path: pathlib.Path) -> None:
    """O campo só é final no Checkpoint A: o rascunho da Fase 3A não é conferido."""
    repo = _repo(tmp_path, {_NEW_STAGE: _concept(_record(None), status="draft")})
    assert gate.problems(repo) == []


def test_the_same_concept_leaving_draft_is_rejected(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {_NEW_STAGE: _concept(_record(None), status="done")})
    [problem] = gate.problems(repo)
    assert problem.startswith(f"docs/stages/{_NEW_STAGE}/concept.md:")


def test_draft_counts_only_in_the_frontmatter(tmp_path: pathlib.Path) -> None:
    text = _concept(_record(None)) + "\nstatus: draft\n"
    assert gate.problems(_repo(tmp_path, {_NEW_STAGE: text}))


@pytest.mark.parametrize(
    "head",
    ["# Concept sem frontmatter\n", "---\nstatus: draft\n\n# frontmatter sem fechar\n"],
    ids=["no-frontmatter", "unclosed-frontmatter"],
)
def test_a_concept_without_a_closed_frontmatter_is_checked(
    tmp_path: pathlib.Path, head: str
) -> None:
    """Sem frontmatter fechado não há `draft` a isentar: fail-closed."""
    text = head + "\n" + _record(None)
    assert gate.problems(_repo(tmp_path, {_NEW_STAGE: text}))


def test_an_adr_is_always_checked(tmp_path: pathlib.Path) -> None:
    """O ADR nasce `accepted` (PROMPT-stage, Fase 3A passo 6): não há rascunho a isentar."""
    adr = _concept(_record(None), status="draft")
    [problem] = gate.problems(_repo(tmp_path, adrs={_NEW_ADR: adr}))
    assert problem.startswith(f"docs/adr/{_NEW_ADR}:")


def test_a_technical_is_not_scanned(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {_NEW_STAGE: _concept(_record())})
    technical = repo / "docs" / "stages" / _NEW_STAGE / "technical.md"
    technical.write_text(_concept(_record(None)), encoding="utf-8")
    assert gate.problems(repo) == []


def test_the_cut_is_by_file_and_record_id(tmp_path: pathlib.Path) -> None:
    text = _concept(_record(None, "D1"), _record(None, "D2"))
    repo = _repo(tmp_path, {_NEW_STAGE: text})
    rel = f"docs/stages/{_NEW_STAGE}/concept.md"
    [problem] = gate.problems(repo, frozenset({(rel, "D1")}))
    assert "registro D2" in problem
    assert gate.problems(repo, frozenset({("docs/stages/other/concept.md", "D2"), (rel, "D1")}))


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_decision_records.py", "--repo", str(repo)])
    return int(gate.main())


def test_main_exits_0_on_a_clean_repo(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {_NEW_STAGE: _concept(_record())})
    assert _main(monkeypatch, repo) == 0
    assert "do vocabulário" in capsys.readouterr().out


def test_main_exits_1_and_names_file_and_line(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {_NEW_STAGE: _concept(_record("Verificado: ok"))})
    assert _main(monkeypatch, repo) == 1
    captured = capsys.readouterr()
    assert f"docs/stages/{_NEW_STAGE}/concept.md:" in captured.err
    assert "1 problema(s)" in captured.err
    assert "parcial→corrigido" in captured.err
    assert captured.out == ""


def test_main_exits_2_when_nothing_is_found(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--repo` errado não pode sair verde: sem concept nem ADR, o gate falha fechado."""
    assert _main(monkeypatch, tmp_path) == _FATAL_EXIT
    assert "FATAL" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Contra os docs reais
# ---------------------------------------------------------------------------

# O corte, transcrito: os 20 registros que reprovavam no merge da issue #212 (19 sem o
# campo, 1 fora do vocabulário). Este conjunto não cresce; registro novo traz o campo.
_LEGACY_COUNT = 20
_ADR = "docs/adr/"
_C37 = "docs/stages/3.7-application-authorization/concept.md"
_C42 = "docs/stages/4.2-validation-policies/concept.md"
_LEGACY = {
    (_ADR + "0_0_0012-cite-the-roadmap-by-stable-anchor.md", "0.0.0012"),
    (_ADR + "0_0_0017-cite-domain-docs-by-stable-anchor.md", "0.0.0017"),
    (_ADR + "0_0_0019-cite-overview-adrs-and-code-by-stable-anchor.md", "0.0.0019"),
    (_ADR + "0_0_0022-audit-session-closes-the-pr-it-validated.md", "D1"),
    (_ADR + "2_7_0001-identity-authorizes-through-a-narrow-port.md", "2.7.0001-2"),
    ("docs/stages/3.11-job-function-unit-enablement/concept.md", "D8"),
    *((_C37, f"D{number}") for number in range(1, 4)),
    *((_C42, f"D{number}") for number in range(1, 12)),
}
# Piso da varredura real (medição de 2026-11-23): 30 registros em 3 concepts e 9 ADRs
# fora do corte e dentro dele. Só cresce.
_REAL_RECORDS_FLOOR = 30
_REAL_PASSING_FLOOR = 10


def test_the_cut_does_not_grow() -> None:
    """A lista do corte é fechada: acrescentar um registro a ela reprova aqui."""
    assert len(_LEGACY) == _LEGACY_COUNT
    assert gate.LEGACY_RECORDS == _LEGACY


def test_every_record_in_the_cut_exists_and_still_fails() -> None:
    """Par errado no corte não isenta ninguém; registro corrigido sai do corte."""
    for rel, record_id in sorted(gate.LEGACY_RECORDS):
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        matching = [record for record in gate.records(text) if record.record_id == record_id]
        assert len(matching) == 1, (rel, record_id)
        assert gate.record_problem(matching[0]) is not None, (rel, record_id)


def test_the_cut_holds_only_done_concepts_and_accepted_adrs() -> None:
    for rel, _ in gate.LEGACY_RECORDS:
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        expected = "status: done" if rel.endswith("concept.md") else "status: accepted"
        assert f"\n{expected}\n" in text, rel


def test_the_real_docs_are_clean() -> None:
    assert gate.problems(_REPO_ROOT) == []


def test_the_real_scan_reaches_the_records() -> None:
    """Piso de contagem: um parser que deixe de achar registros não passa verde."""
    found = [
        (path, record)
        for path in gate.scanned_files(_REPO_ROOT)
        for record in gate.records(path.read_text(encoding="utf-8"))
    ]
    assert len(found) >= _REAL_RECORDS_FLOOR
    passing = [record for _, record in found if gate.record_problem(record) is None]
    assert len(passing) >= _REAL_PASSING_FLOOR


def test_free_text_in_a_real_record_is_rejected(tmp_path: pathlib.Path) -> None:
    """Mutação sobre docs reais: trocar um `Verificado:` por texto livre reprova.

    O concept da 2.7 (o caso da issue) e o ADR 0.0.0021, copiados para um
    repositório de mentira com o primeiro valor trocado pela frase que a 2.7
    tinha na aprovação.
    """
    cases = {
        "docs/stages/2.7-identity-application-authorization/concept.md": "2.7-D1",
        "docs/adr/0_0_0021-planned-full-gate-budget-per-stage.md": "D1",
    }
    for rel, record_id in cases.items():
        real = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert gate.file_problems(real, rel, frozenset()) == [], rel
        line = next(item for item in real.splitlines() if item.startswith("Verificado: "))
        mutated = real.replace(line, "Verificado: ver §7 do technical (Checkpoint A)", 1)
        repo = tmp_path / record_id
        target = repo / rel
        target.parent.mkdir(parents=True)
        target.write_text(mutated, encoding="utf-8")
        [problem] = gate.problems(repo)
        assert f"registro {record_id}:" in problem and "fora do vocabulário" in problem

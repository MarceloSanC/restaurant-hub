"""O guard de regra aposentada, contra frases plantadas (issue #163, ADR 0.0.0021).

**O que o gate protege.** O `make check` completo deixou de rodar em todo commit:
por Task rodam só os testes dela, e o gate completo fica nos 1 a 3 pontos do
plano de gates. A regra antiga estava escrita em dois prompts. Se ela voltar a
um doc que alguém segue para trabalhar, volta a ser cumprida. O gate reprova a
frase, e reprova também o sumiço das duas seções para onde os docs apontam.

**As frases são plantadas num repositório de mentira** em `tmp_path` (o script
recebe `repo_root`). Dois testes rodam contra os docs reais: um trava o estado
desta issue, o outro reintroduz a frase antiga no PROMPT-stage real e confere
que o gate a pega.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_docs_pointers.py"


def _load_script() -> types.ModuleType:
    """Importa `scripts/check_docs_pointers.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_docs_pointers", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_script()

_FATAL_EXIT = 2

# As duas frases que os docs traziam antes da issue #163, como estavam escritas.
# A do PROMPT-stage atravessava a quebra de linha, com recuo e negrito.
_PROMPT_STAGE_OLD = """\
5. **Rodar checks da Task.** Baseline inegociável: **`make check` verde
   antes de todo commit**, além dos checks específicos da Task.
"""
_PROMPT_STEP_OLD = (
    "| **4 — Execução** | executor | roda as Tasks em ordem (`make check` por commit) |\n"
)


def _repo(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """Um repositório de mentira com as duas seções exigidas e os arquivos pedidos."""
    base = {
        "docs/PIPELINE.md": "# Pipeline\n\n### 9.6 Plano de gates\n\nRegra.\n",
        "docs/templates/stage-technical.md": "# Technical\n\n### Plano de gates\n\nTabela.\n",
    }
    for rel, content in {**base, **files}.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# A regra aposentada: o que reprova
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        _PROMPT_STAGE_OLD,
        _PROMPT_STEP_OLD,
        "Rodar `make check` antes de cada commit.",
        "Rode make check antes de qualquer commit.",
        "`make check` completo antes de todo commit.",
        "`make check` por Task, sem exceção.",
        "`make check` **verde** a cada Task.",
        "`make check` em todo commit.",
        "`make check` em cada commit.",
        "`make check` a cada commit.",
        "`make check` antes de cada Task.",
        "Run `make check` after each Task.",
        "Antes de cada commit, rode o `make check`.",
        "Antes de todo commit, executar `make check` inteiro.",
        "Run `make check` before every commit.",
        "The full gate: `make check` green on each Task.",
        "`make check` per commit is the baseline.",
        "> o `make check` verde\n> antes de todo commit continua valendo.",
        "Não rode o `make check` antes de todo commit.",
    ],
)
def test_the_retired_rule_is_rejected(text: str) -> None:
    """Cada forma da regra antiga, as duas históricas e as paráfrases, é reprovada."""
    found = gate.retired_rules_in(text)
    assert len(found) == 1, f"não reprovou: {text!r}"
    assert "ADR 0.0.0021" in found[0][1]


@pytest.mark.parametrize(
    "text",
    [
        # A regra nova, como os docs a escrevem hoje.
        "O `make check` completo roda só nos pontos do plano de gates.",
        "Orçamento de 1 a 3 `make check` por Stage no lugar do gate por Task.",
        "testes da Task antes do commit; `make check` completo só nos pontos do plano",
        "`make check` verde em cada ponto do plano de gates.",
        "Antes do commit de cada Task rodam só os testes dela.",
        # A exceção de orquestração do PROMPT-stage: a ordem invertida sem verbo de mando.
        "empurra a cada Task, porque o `make check` completo roda no GitHub Actions do PR",
        # Vizinhos que não são a regra.
        "**1 Task = 1 commit.** Humano revisa o diff antes de cada commit.",
        "`make check` verde localmente.",
        "`make check` green on the current branch **before** starting (baseline).",
        "`make docs-check` por commit seria barato.",
        "`make check-task` por commit não existe neste repositório.",
        # Linha em branco separa parágrafos: a frase não a atravessa.
        "Depois rode o `make check`\n\nantes de todo commit, revise o diff.",
        # Outra célula da tabela não completa a frase.
        "| `make check` | por commit |",
    ],
)
def test_legitimate_text_is_not_rejected(text: str) -> None:
    """A regra nova e os vizinhos da frase antiga passam: gate frouxo é gate ignorado."""
    assert gate.retired_rules_in(text) == []


def test_the_reported_line_is_where_the_phrase_starts() -> None:
    """Na frase quebrada em duas linhas, a linha apontada é a do `make check`."""
    text = "# Título\n\nprosa\n" + _PROMPT_STAGE_OLD
    [(line, _)] = gate.retired_rules_in(text)
    assert text.splitlines()[line - 1].endswith("**`make check` verde")


def test_two_occurrences_are_two_findings() -> None:
    """Cada ocorrência é um achado, com a sua linha."""
    text = "`make check` por commit.\n\nprosa\n\n`make check` por Task.\n"
    expected_lines = [1, 5]
    assert [line for line, _ in gate.retired_rules_in(text)] == expected_lines


def test_a_phrase_at_the_very_start_of_a_line_reports_that_line() -> None:
    """A frase que começa na coluna zero não é atribuída à linha de cima."""
    text = "prosa\n\nmake check por commit\n"
    expected_line = 3
    assert [line for line, _ in gate.retired_rules_in(text)] == [expected_line]


# ---------------------------------------------------------------------------
# O que é varrido e o que fica fora
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "CLAUDE.md",
        "README.md",
        "docs/PROMPT-stage-single-session.md",
        "docs/roadmap.md",
        "docs/runbooks/validate-ci-gate.md",
        "docs/templates/stage-concept.md",
        ".claude/skills/task-ordering-hex/SKILL.md",
        ".claude/skills/stage-audit/reference/gates.md",
        ".claude/agents/decision-reviewer.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
    ],
)
def test_normative_docs_are_scanned(tmp_path: pathlib.Path, rel: str) -> None:
    """Todo doc que alguém segue para trabalhar é varrido, e o achado traz o caminho."""
    repo = _repo(tmp_path, {rel: "prosa\n" + _PROMPT_STEP_OLD})
    [problem] = gate.problems(repo)
    assert problem.startswith(f"{rel}:2: ")


@pytest.mark.parametrize(
    "rel",
    [
        "docs/adr/0_0_0021-planned-full-gate-budget-per-stage.md",
        "docs/stages/3.6-staff-http/technical.md",
        "docs/audits/2026-09-28.md",
        "docs/domain/staff/workforce.md",
        "tree.txt",
        "scripts/check_docs_pointers.py",
    ],
)
def test_historical_records_are_out_of_scope(tmp_path: pathlib.Path, rel: str) -> None:
    """ADR, Stage, auditoria e doc de domínio registram a época: a frase pode estar lá."""
    repo = _repo(tmp_path, {rel: _PROMPT_STAGE_OLD})
    assert gate.problems(repo) == []


def test_a_file_matched_by_two_globs_is_scanned_once(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Glob sobreposto não duplica o achado."""
    monkeypatch.setattr(gate, "SCANNED_GLOBS", ("docs/*.md", "docs/x.md"))
    repo = _repo(tmp_path, {"docs/x.md": _PROMPT_STEP_OLD})
    assert len(gate.problems(repo)) == 1


def test_a_directory_named_like_a_doc_is_ignored(tmp_path: pathlib.Path) -> None:
    """Pasta que casa o glob não é lida como arquivo."""
    repo = _repo(tmp_path, {})
    (repo / "docs" / "pasta.md").mkdir()
    assert gate.problems(repo) == []


# ---------------------------------------------------------------------------
# Os títulos exigidos
# ---------------------------------------------------------------------------


def test_required_headings_present_is_clean(tmp_path: pathlib.Path) -> None:
    assert gate.problems(_repo(tmp_path, {})) == []


@pytest.mark.parametrize("required", gate.REQUIRED_HEADINGS, ids=lambda r: r.path)
def test_a_renamed_required_heading_is_rejected(tmp_path: pathlib.Path, required: object) -> None:
    """Título renomeado ou rebaixado de nível deixa os ponteiros sem alvo."""
    assert isinstance(required, gate.RequiredHeading)
    repo = _repo(tmp_path, {required.path: f"# Doc\n\n#{required.heading}\n\nRegra.\n"})
    [problem] = gate.problems(repo)
    assert problem.startswith(f"{required.path}: falta o título '{required.heading}'")


@pytest.mark.parametrize("required", gate.REQUIRED_HEADINGS, ids=lambda r: r.path)
def test_a_missing_required_file_is_rejected(tmp_path: pathlib.Path, required: object) -> None:
    """O arquivo que abrigava a seção sumiu: o achado diz qual."""
    assert isinstance(required, gate.RequiredHeading)
    repo = _repo(tmp_path, {})
    (repo / required.path).unlink()
    [problem] = gate.problems(repo)
    assert problem.startswith(f"{required.path}: arquivo não existe")


def test_trailing_spaces_do_not_hide_a_heading(tmp_path: pathlib.Path) -> None:
    """Espaço no fim da linha do título não conta como ausência."""
    repo = _repo(tmp_path, {"docs/PIPELINE.md": "### 9.6 Plano de gates   \n"})
    assert gate.problems(repo) == []


# ---------------------------------------------------------------------------
# `main` e os códigos de saída
# ---------------------------------------------------------------------------


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_docs_pointers.py", "--repo", str(repo)])
    return int(gate.main())


def test_main_exits_0_on_a_clean_repo(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, _repo(tmp_path, {})) == 0
    assert "nenhuma regra aposentada" in capsys.readouterr().out


def test_main_exits_1_and_names_file_and_line(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"docs/PROMPT-stage-single-session.md": "x\n\n" + _PROMPT_STAGE_OLD})
    assert _main(monkeypatch, repo) == 1
    captured = capsys.readouterr()
    assert "docs/PROMPT-stage-single-session.md:3: " in captured.err
    assert "1 problema(s)" in captured.err
    assert captured.out == ""


def test_main_exits_2_when_no_normative_doc_is_found(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--repo` errado não pode sair verde: sem doc para varrer, o gate falha fechado."""
    assert _main(monkeypatch, tmp_path) == _FATAL_EXIT
    assert "FATAL" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Contra os docs reais
# ---------------------------------------------------------------------------


def test_the_real_docs_are_clean() -> None:
    """Trava o estado da issue #163: nenhum doc normativo traz a regra antiga."""
    assert gate.problems(_REPO_ROOT) == []


def test_the_real_scan_reaches_the_docs_that_carried_the_rule() -> None:
    """Os dois prompts que traziam a frase estão entre os arquivos varridos."""
    scanned = {path.relative_to(_REPO_ROOT).as_posix() for path in gate.normative_files(_REPO_ROOT)}
    assert {
        "docs/PROMPT-stage-single-session.md",
        "docs/PROMPT-step-single-session.md",
        "docs/RUNBOOK-STAGE-LIFECYCLE.md",
        "docs/templates/stage-technical.md",
        ".claude/skills/task-ordering-hex/SKILL.md",
    } <= scanned


@pytest.mark.parametrize(
    ("rel", "old_rule"),
    [
        ("docs/PROMPT-stage-single-session.md", _PROMPT_STAGE_OLD),
        ("docs/PROMPT-step-single-session.md", _PROMPT_STEP_OLD),
    ],
)
def test_reintroducing_the_old_rule_in_a_real_doc_is_rejected(
    tmp_path: pathlib.Path, rel: str, old_rule: str
) -> None:
    """Mutação sobre o doc real: a frase antiga de volta ao prompt reprova."""
    real = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    assert gate.retired_rules_in(real) == []
    repo = _repo(tmp_path, {rel: real + "\n" + old_rule})
    [problem] = gate.problems(repo)
    assert problem.startswith(f"{rel}:")
    assert "regra aposentada pelo ADR 0.0.0021" in problem


@pytest.mark.parametrize("required", gate.REQUIRED_HEADINGS, ids=lambda r: r.path)
def test_removing_a_required_heading_from_a_real_doc_is_rejected(
    tmp_path: pathlib.Path, required: object
) -> None:
    """Mutação sobre o doc real: sem o título, os ponteiros para a seção ficam sem alvo."""
    assert isinstance(required, gate.RequiredHeading)
    real = (_REPO_ROOT / required.path).read_text(encoding="utf-8")
    assert f"\n{required.heading}\n" in real
    mutated = real.replace(f"\n{required.heading}\n", "\n")
    repo = _repo(tmp_path, {required.path: mutated})
    assert any(
        problem.startswith(f"{required.path}: falta o título") for problem in gate.problems(repo)
    )

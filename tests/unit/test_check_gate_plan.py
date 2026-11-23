"""O gate do plano de gates no technical.md novo (issue #201, ADR 0.0.0021).

**O que o gate protege.** Desde o ADR 0.0.0021 o `make check` completo roda só
nos 1 a 3 pontos que a tabela "Plano de gates" da §1 do `technical.md` nomeia.
Um technical novo sem a tabela, ou com a tabela do template ainda em branco,
passava no `make docs-check`. O gate reprova os dois e deixa passar, sem edição,
os technicals aprovados antes do ADR (o corte).

**A forma vem do template real.** O technical "bom" dos testes é o próprio
`docs/templates/stage-technical.md` com a linha da tabela preenchida: se o
template mudar a forma do plano, estes testes reprovam antes de reprovar a
primeira Stage que o seguir.

**Os technicals são plantados num repositório de mentira** em `tmp_path` (o
script recebe `repo_root`). Os testes do fim rodam contra os docs reais.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_gate_plan.py"
_TEMPLATE = _REPO_ROOT / "docs" / "templates" / "stage-technical.md"


def _load_script() -> types.ModuleType:
    """Importa `scripts/check_gate_plan.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_gate_plan", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_script()

_FATAL_EXIT = 2
_NEW_STAGE = "9.9-brand-new"
_TEMPLATE_TEXT = _TEMPLATE.read_text(encoding="utf-8")
# A linha da tabela do template, como está escrita nele.
_TEMPLATE_ROW = next(
    line for line in _TEMPLATE_TEXT.splitlines() if line.startswith("| 1 | <Task NN")
)
_EXIT_ROW = "| 1 | saída | gate de saída (§3) |"


def _technical(*rows: str) -> str:
    """O template real com a linha da tabela trocada pelas linhas pedidas."""
    return _TEMPLATE_TEXT.replace(_TEMPLATE_ROW, "\n".join(rows))


def _repo(tmp_path: pathlib.Path, technicals: dict[str, str]) -> pathlib.Path:
    """Um repositório de mentira com um technical por pasta de Stage pedida."""
    for stage, content in technicals.items():
        path = tmp_path / "docs" / "stages" / stage / "technical.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def _reasons(text: str) -> list[str]:
    return [reason for _, reason in gate.plan_problems(text)]


# ---------------------------------------------------------------------------
# A forma do template: o que passa
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rows",
    [
        (_EXIT_ROW,),
        ("| 1 | Task 12 | gate de saída (§3) |",),
        ("| 1 | Task 12 (saida) | último ponto |",),
        (
            "| 1 | Task 03 | muda o port lido pelo adapter da Task 05 |",
            "| 2 | Task 07 | primeira Task que alimenta o mapa de status |",
            "| 3 | saída | gate de saída (§3) |",
        ),
        (
            "|1|Task 02|composition root muda|",
            "|2|saída|gate de saída (§3)|",
        ),
        ("| 1 | saída | gate de saída (§3); o `a \\| b` do motivo é texto |",),
    ],
    ids=["exit-only", "exit-in-reason", "saida-sem-acento", "three-points", "compact", "pipe"],
)
def test_a_filled_template_plan_passes(rows: tuple[str, ...]) -> None:
    assert gate.plan_problems(_technical(*rows)) == []


def test_a_fourth_point_with_a_concrete_reason_passes() -> None:
    """Do 4º ponto em diante basta o motivo escrito; o mérito fica com a revisão."""
    text = _technical(
        "| 1 | Task 02 | migration lida pelas Tasks 03 a 06 |",
        "| 2 | Task 04 | port do outro BC |",
        "| 3 | Task 06 | primeira rota do mapa de overrides |",
        "| 4 | Task 09 | troca o conftest compartilhado; o ponto 5 pegaria depois de 3 Tasks |",
        "| 5 | saída | gate de saída (§3) |",
    )
    assert gate.plan_problems(text) == []


# ---------------------------------------------------------------------------
# O que reprova
# ---------------------------------------------------------------------------


def test_the_unedited_template_is_rejected() -> None:
    """Copiar o template sem preencher a tabela não é um plano."""
    reasons = _reasons(_TEMPLATE_TEXT)
    assert "ponto 1 sem 'Depois da Task' preenchido" in reasons
    assert "ponto 1 sem 'Motivo' preenchido" in reasons


def test_a_technical_without_the_section_is_rejected() -> None:
    text = _technical(_EXIT_ROW).replace("### Plano de gates\n", "")
    [(line, reason)] = gate.plan_problems(text)
    assert line == 1
    assert reason.startswith("falta o título '### Plano de gates' na §1")


def test_the_section_outside_section_one_is_rejected() -> None:
    """A casa do plano é a §1: o título movido para a §2 não conta."""
    text = _technical(_EXIT_ROW)
    block_start = text.index("### Plano de gates")
    block_end = text.index("### Estrutura de pastas afetada")
    block = text[block_start:block_end]
    moved = text[:block_start] + text[block_end:]
    moved = moved.replace("## 2. Tasks\n", "## 2. Tasks\n\n" + block)
    assert _reasons(moved)[0].startswith("falta o título")


def test_a_heading_inside_a_code_fence_does_not_count() -> None:
    text = _technical(_EXIT_ROW).replace("### Plano de gates\n", "```\n### Plano de gates\n```\n")
    assert _reasons(text)[0].startswith("falta o título")


def test_a_technical_without_section_one_is_rejected() -> None:
    assert _reasons("# Technical\n\n### Plano de gates\n\n" + _EXIT_ROW + "\n")[0].startswith(
        "falta o título"
    )


@pytest.mark.parametrize(
    "header",
    ["| # | Task | Motivo |", "| Depois da Task | Motivo |", "Sem tabela nenhuma."],
)
def test_a_table_without_the_template_header_is_rejected(header: str) -> None:
    text = _technical(_EXIT_ROW).replace("| # | Depois da Task | Motivo |", header)
    assert any("não tem a tabela do template" in reason for reason in _reasons(text))


def test_a_table_without_rows_is_rejected() -> None:
    text = _technical(_EXIT_ROW).replace(_EXIT_ROW + "\n", "")
    assert _reasons(text) == ["o plano de gates não tem nenhum ponto; o de saída é obrigatório"]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ("| 1 | saída | |", "ponto 1 sem 'Motivo' preenchido"),
        ("| 1 | saída |", "ponto 1 sem 'Motivo' preenchido"),
        ("| 1 | | gate de saída (§3) |", "ponto 1 sem 'Depois da Task' preenchido"),
        ("| 1 | saída | <motivo> |", "ponto 1 sem 'Motivo' preenchido"),
        ("| 2 | saída | gate de saída (§3) |", "ponto numerado '2'; esperado 1 (1, 2, 3...)"),
        ("| um | saída | gate de saída (§3) |", "ponto numerado 'um'; esperado 1 (1, 2, 3...)"),
    ],
)
def test_an_incomplete_row_is_rejected(row: str, expected: str) -> None:
    assert expected in _reasons(_technical(row))


def test_a_row_with_too_many_cells_is_rejected() -> None:
    reasons = _reasons(_technical("| 1 | saída | gate | extra |"))
    assert reasons == ["linha do plano com 4 células; a tabela tem 3"]


def test_a_plan_without_the_exit_point_is_rejected() -> None:
    text = _technical("| 1 | Task 03 | muda o port |", "| 2 | Task 05 | composition root |")
    assert _reasons(text) == ["nenhum ponto é o de saída: o gate de saída é sempre um deles (§9.6)"]


@pytest.mark.parametrize(
    "reason", ["por segurança", "Por precaução.", "to be safe", "**por segurança**"]
)
def test_a_fourth_point_to_be_safe_is_rejected(reason: str) -> None:
    text = _technical(
        "| 1 | Task 02 | migration |",
        "| 2 | Task 04 | port |",
        "| 3 | Task 06 | rota |",
        f"| 4 | Task 08 | {reason} |",
        "| 5 | saída | gate de saída (§3) |",
    )
    [problem] = _reasons(text)
    assert problem.startswith("ponto 4 acima do orçamento de 3 sem justificativa")


def test_to_be_safe_within_the_budget_is_left_to_review() -> None:
    """Dentro do orçamento o gate confere só que o motivo existe; o mérito é da revisão."""
    text = _technical(
        "| 1 | saída | gate de saída (§3) |",
        "| 2 | Task 02 | por segurança |",
        "| 3 | Task 04 | por segurança |",
    )
    assert gate.plan_problems(text) == []


def test_the_reported_line_is_the_row() -> None:
    text = _technical("| 1 | saída | |")
    [(line, _)] = gate.plan_problems(text)
    assert text.splitlines()[line - 1] == "| 1 | saída | |"


# ---------------------------------------------------------------------------
# O corte e a varredura
# ---------------------------------------------------------------------------


def test_a_legacy_stage_without_plan_is_skipped(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {"4.4-scheduling-persistence": "# Technical\n\n## 1. Contexto\n"})
    assert gate.problems(repo) == []


def test_a_new_stage_without_plan_is_rejected(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {_NEW_STAGE: "# Technical\n\n## 1. Contexto\n"})
    [problem] = gate.problems(repo)
    assert problem.startswith(f"docs/stages/{_NEW_STAGE}/technical.md:1: falta o título")


def test_the_cut_is_by_folder_name_not_by_stage_number(tmp_path: pathlib.Path) -> None:
    """Um 4.4 com outro slug é outra Stage: o corte não isenta por número (colisão de N.M)."""
    repo = _repo(tmp_path, {"4.4-another-slug": "# Technical\n\n## 1. Contexto\n"})
    assert len(gate.problems(repo)) == 1


def test_a_concept_md_is_not_scanned(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "docs" / "stages" / _NEW_STAGE / "concept.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Concept\n", encoding="utf-8")
    assert gate.problems(tmp_path)[0].startswith("FATAL")


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_gate_plan.py", "--repo", str(repo)])
    return int(gate.main())


def test_main_exits_0_on_a_clean_repo(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {_NEW_STAGE: _technical(_EXIT_ROW)})
    assert _main(monkeypatch, repo) == 0
    assert "traz o plano de gates" in capsys.readouterr().out


def test_main_exits_1_and_names_file_and_line(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = _technical("| 1 | saída | |")
    repo = _repo(tmp_path, {_NEW_STAGE: text})
    assert _main(monkeypatch, repo) == 1
    captured = capsys.readouterr()
    line = text.splitlines().index("| 1 | saída | |") + 1
    assert f"docs/stages/{_NEW_STAGE}/technical.md:{line}: " in captured.err
    assert "1 problema(s)" in captured.err
    assert captured.out == ""


def test_main_exits_2_when_no_technical_is_found(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--repo` errado não pode sair verde: sem technical para varrer, o gate falha fechado."""
    assert _main(monkeypatch, tmp_path) == _FATAL_EXIT
    assert "FATAL" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Contra os docs reais
# ---------------------------------------------------------------------------

# O corte, transcrito: as Stages aprovadas antes do merge do ADR 0.0.0021. Este
# conjunto não cresce; Stage nova traz o plano.
_LEGACY = {
    "1.1-bootstrap",
    "1.2-ci",
    "2.1-identity-domain",
    "2.2-identity-application",
    "2.3-identity-persistence",
    "2.4-identity-http",
    "2.5-email-invite",
    "2.6-identity-unit-of-work",
    "2.7-identity-application-authorization",
    "3.1-staff-domain",
    "3.2-staff-application",
    "3.3-staff-persistence",
    "3.4-staff-access-scope",
    "3.5-employee-login-link",
    "3.6-staff-http",
    "3.7-application-authorization",
    "3.8-termination-access-scope",
    "3.9-error-hierarchy",
    "3.11-job-function-unit-enablement",
    "4.1-scheduling-domain",
    "4.2-validation-policies",
    "4.3-scheduling-application",
    "4.4-scheduling-persistence",
}
_LEGACY_COUNT = 23


def test_the_cut_does_not_grow() -> None:
    """A lista do corte é fechada: adicionar uma Stage a ela reprova aqui."""
    assert len(_LEGACY) == _LEGACY_COUNT
    assert gate.LEGACY_STAGES == _LEGACY


def test_every_stage_in_the_cut_exists() -> None:
    """Nome errado na lista não isenta ninguém e esconderia a Stage certa."""
    for stage in gate.LEGACY_STAGES:
        assert (_REPO_ROOT / "docs" / "stages" / stage / "technical.md").is_file(), stage


def test_the_real_technicals_are_clean() -> None:
    """Os technicals de develop passam sem edição: os anteriores pelo corte, os novos pela forma."""
    assert gate.problems(_REPO_ROOT) == []


def test_the_real_scan_reaches_every_technical() -> None:
    scanned = {path.parent.name for path in gate.technical_files(_REPO_ROOT)}
    assert len(scanned) >= _LEGACY_COUNT
    assert scanned >= _LEGACY


def test_the_real_legacy_technicals_would_fail_without_the_cut(tmp_path: pathlib.Path) -> None:
    """Mutação do corte: cada technical anterior ao ADR, numa pasta nova, reprova.

    Prova que é o corte, e não a forma deles, que os mantém verdes; e que um
    technical sem plano copiado de uma Stage antiga não escapa.
    """
    for stage in sorted(gate.LEGACY_STAGES):
        real = (_REPO_ROOT / "docs" / "stages" / stage / "technical.md").read_text(encoding="utf-8")
        assert gate.plan_problems(real), stage


def test_the_template_header_is_the_gate_header() -> None:
    """O gate exige a forma do template: título na §1 e a tabela com o mesmo cabeçalho."""
    section = gate.plan_section(_TEMPLATE_TEXT)
    assert section is not None
    _, body = section
    header = next(line for _, line in body if line.startswith("|"))
    assert tuple(gate._cells(header)) == gate.TABLE_HEADER


def test_removing_the_section_from_a_new_technical_is_rejected(tmp_path: pathlib.Path) -> None:
    """Mutação: o technical novo (template preenchido) passa; sem a seção, reprova."""
    good = _technical(_EXIT_ROW)
    assert gate.problems(_repo(tmp_path / "good", {_NEW_STAGE: good})) == []
    start = good.index("### Plano de gates")
    end = good.index("### Estrutura de pastas afetada")
    mutated = good[:start] + good[end:]
    [problem] = gate.problems(_repo(tmp_path / "bad", {_NEW_STAGE: mutated}))
    assert "falta o título '### Plano de gates'" in problem

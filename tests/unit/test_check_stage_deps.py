"""Unit de `scripts/check_stage_deps.py` — pré-condição de dependência de Stage (ADR 0.0.0009).

O que se protege é a conversão que errou duas vezes enquanto era prosa (issue #12): o
`depends_on` carrega o `stage_id` com slug (`1.1-bootstrap`) e o commit reservado de
fechamento carrega só o número (`stage 1.1: complete`). Substituir um pelo outro deu
HALT falso (F-C do PR #11); casar só o prefixo `stage 1.1` deu verde falso (F4).

Os testes montam um roadmap de mentira em `tmp_path` e **injetam** o histórico: nenhum
lê o git deste repositório, então rodam igual no clone raso do job de mutação.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_stage_deps.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_stage_deps", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # O dataclass resolve as anotações pelo módulo registrado em sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


csd = _load()

_HEADER = "| Stage | Título | Camada-alvo | Status | Depende de |\n|---|---|---|---|---|\n"
_ISSUES = (
    "| [#45](https://x/45) | Gates de arquitetura | shared | tooling | done | — |\n"
    "| [#46](https://x/46) | Fronteira transacional | shared | application | open | — |\n"
)


def _row(stage_id: str, status: str = "done", deps: str = "—") -> str:
    return f"| `{stage_id}` | Título | domain | {status} | {deps} |\n"


def _roadmap(rows: str, header: str = _HEADER, issues: str = _ISSUES) -> str:
    """Roadmap mínimo com as vizinhas reais da Tabela de Stages: Steps antes, Issues depois."""
    return (
        "# Roadmap\n\n"
        "## Tabela de Steps\n\n| ID | Step | Status |\n|---|---|---|\n| 1 | Fundação | done |\n\n"
        f"## Tabela de Stages\n\n{header}{rows}\n"
        "**Legenda de status (Stage):** `draft`, `done`.\n\n"
        "## Tabela de Issues\n\n"
        "| Issue | Título | BC | Camada-alvo | Status | Depende de |\n|---|---|---|---|---|---|\n"
        "| [#59](https://x/59) | Achados da Stage 1.1 | staff | docs | done | — |\n"
        f"{issues}"
    )


_CHAIN = (
    _row("1.1-bootstrap")
    + _row("1.2-ci", deps="`1.1-bootstrap`")
    + _row("2.1-identity-domain", status="draft", deps="`1.2-ci`")
)
_CLOSED = frozenset({"stage 1.1: complete", "stage 1.2: complete", "stage 2.1: conceptual draft"})
_WHERE = ("origin/develop",)


def _rows(rows: str) -> list[Any]:
    parsed, problems = csd.parse_stage_table(_roadmap(rows))
    assert problems == []
    return parsed


def _history(subjects: frozenset[str] = _CLOSED) -> Any:  # noqa: ANN401
    return csd.History(subjects, _WHERE)


def _check(targets: Sequence[str], rows: str, subjects: frozenset[str]) -> list[str]:
    issues = csd.parse_issue_table(_roadmap(rows))
    verdict = csd.check_targets(targets, _rows(rows), _history(subjects), issues)
    return list(verdict.violations)


# --- stage_id → número --------------------------------------------------------------


@pytest.mark.parametrize(
    ("stage_id", "number"),
    [
        ("1.1-bootstrap", "1.1"),
        ("3.5-employee-login-link", "3.5"),
        ("12.10-multi-tenant", "12.10"),
        ("X.4-openai-gateway", "X.4"),
        ("2.1-oauth2-login", "2.1"),
    ],
)
def test_number_is_the_prefix_up_to_the_first_hyphen(stage_id: str, number: str) -> None:
    assert csd.stage_number(stage_id) == number


@pytest.mark.parametrize(
    "not_a_stage_id",
    [
        "1.1",
        "bootstrap",
        "1.1-",
        "1-1-bootstrap",
        "1.1-Bootstrap",
        "`1.1-bootstrap`",
        "",
        "1.1-bootstrap/",
        "1.1-bootstrap extra",
    ],
)
def test_number_refuses_what_is_not_a_stage_id(not_a_stage_id: str) -> None:
    with pytest.raises(ValueError, match="stage_id malformado"):
        csd.stage_number(not_a_stage_id)


def test_complete_subject_carries_the_number_not_the_stage_id() -> None:
    assert csd.complete_subject("1.1-bootstrap") == "stage 1.1: complete"


# --- leitura da Tabela de Stages ----------------------------------------------------


def test_parse_reads_status_and_dependencies() -> None:
    rows = _rows(
        _row("1.1-bootstrap")
        + _row("4.2-validation-policies", status="draft", deps="`4.1-scheduling-domain`")
        + _row("7.2-timeclock-domain", deps="`7.1-controlid-spike`, `4.5-scheduling-http`")
        + _row("4.3-scheduling-application", deps="`4.2-validation-policies`, `#46`")
    )

    assert [(r.stage_id, r.status, r.depends_on, r.depends_on_issues) for r in rows] == [
        ("1.1-bootstrap", "done", (), ()),
        ("4.2-validation-policies", "draft", ("4.1-scheduling-domain",), ()),
        ("7.2-timeclock-domain", "done", ("7.1-controlid-spike", "4.5-scheduling-http"), ()),
        ("4.3-scheduling-application", "done", ("4.2-validation-policies",), (46,)),
    ]


def test_parse_finds_columns_by_header_name_not_position() -> None:
    header = "| Depende de | Status | Título | Stage |\n|---|---|---|---|\n"
    text = _roadmap("| `1.1-bootstrap` | draft | T | `1.2-ci` |\n", header=header)

    rows, problems = csd.parse_stage_table(text)

    assert problems == []
    assert [(r.stage_id, r.status, r.depends_on) for r in rows] == [
        ("1.2-ci", "draft", ("1.1-bootstrap",))
    ]


def test_parse_reads_only_the_stage_table() -> None:
    rows, problems = csd.parse_stage_table(_roadmap(_row("1.1-bootstrap")))

    # As tabelas de Steps (antes) e de Issues (depois) não viram linhas nem problemas.
    assert [r.stage_id for r in rows] == ["1.1-bootstrap"]
    assert problems == []


def test_parse_keeps_an_escaped_pipe_inside_a_cell() -> None:
    rows = _rows("| `1.1-bootstrap` | lint \\| types | bootstrap | done | — |\n")

    assert [(r.stage_id, r.status) for r in rows] == [("1.1-bootstrap", "done")]


_SECTION = "## Tabela de Stages\n\n"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("# Roadmap\n\n## Tabela de Issues\n", "ausente"),
        (_SECTION + "texto sem tabela\n", "sem cabeçalho"),
        (
            _SECTION + "| Stage | Status | Depende de |\n| `1.1-x` | done | — |\n",
            "não é o separador",
        ),
        (_SECTION + "| Stage | Status | Depende de |\n|---|x|---|\n", "não é o separador"),
        (_SECTION + "| Stage | Status |\n|---|---|\n| `1.1-x` | done |\n", "Depende de"),
    ],
)
def test_parse_fails_closed_when_the_table_is_not_readable(text: str, reason: str) -> None:
    with pytest.raises(csd.RoadmapError, match=reason):
        csd.parse_stage_table(text)


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ("| 1.1 | T | domain | done | — |\n", "não é um stage_id"),
        ("| `1.1-bootstrap` | T | domain | done | 1.1 |\n", "nem issue `#N`"),
        ("| `1.1-bootstrap` | T | domain | done | issue 45 |\n", "nem issue `#N`"),
        ("| `1.1-bootstrap` | T | done | — |\n", "4 célula(s)"),
        ("| `1.1-bootstrap` | T | domain | done | — | extra |\n", "6 célula(s)"),
        (_row("1.1-bootstrap") + _row("1.1-bootstrap", status="draft"), "mais de uma linha"),
    ],
)
def test_parse_reports_rows_it_cannot_trust(rows: str, reason: str) -> None:
    _, problems = csd.parse_stage_table(_roadmap(rows))

    assert len(problems) == 1
    assert reason in problems[0]


def test_issue_table_status_is_read_by_issue_number() -> None:
    issues = (
        "| [#45](https://x/45) | A | shared | tooling | done | — |\n"
        "| #46 | B | shared | app | open | — |\n"
        "| [Sem número](https://x) | C | shared | docs | done | — |\n"
    )

    assert csd.parse_issue_table(_roadmap(_row("1.1-bootstrap"), issues=issues)) == {
        59: "done",
        45: "done",
        46: "open",
    }


# --- a checagem ---------------------------------------------------------------------


def test_closed_dependency_passes() -> None:
    assert _check(["1.2-ci"], _CHAIN, _CLOSED) == []


def test_stage_without_dependencies_needs_no_history() -> None:
    assert _check(["1.1-bootstrap"], _CHAIN, frozenset()) == []


def test_dependency_not_done_in_the_roadmap_is_a_violation() -> None:
    rows = _row("1.1-bootstrap", status="review") + _row("1.2-ci", deps="`1.1-bootstrap`")

    assert _check(["1.2-ci"], rows, _CLOSED) == [
        "1.2-ci → 1.1-bootstrap: status `review` na Tabela de Stages (esperado `done`)"
    ]


def test_a_complete_commit_that_is_not_merged_does_not_close_a_dependency() -> None:
    """Branch empilhada: o `complete` da dependência existe, mas fora das refs conferidas."""
    assert _check(["1.2-ci"], _CHAIN, frozenset({"stage 1.2: complete"})) == [
        "1.2-ci → 1.1-bootstrap: commit `stage 1.1: complete` não está mergeado em origin/develop"
    ]


def test_partial_gate_commits_do_not_close_a_dependency() -> None:
    """F4 do PR #11: `stage 1.1` casava `conceptual approved` — verde para quem não fechou."""
    partial = frozenset(
        {
            "stage 1.1: conceptual draft",
            "stage 1.1: conceptual approved",
            "stage 1.1: technical approved",
        }
    )

    assert _check(["1.2-ci"], _CHAIN, partial) == [
        "1.2-ci → 1.1-bootstrap: commit `stage 1.1: complete` não está mergeado em origin/develop"
    ]


_NOT_MERGED_1_1 = [
    "1.2-ci → 1.1-bootstrap: commit `stage 1.1: complete` não está mergeado em origin/develop"
]


def test_the_stage_id_in_the_subject_does_not_close_a_dependency() -> None:
    """F-C do PR #11: o commit reservado carrega o número; o `stage_id` ali não casa nada."""
    assert _check(["1.2-ci"], _CHAIN, frozenset({"stage 1.1-bootstrap: complete"})) == (
        _NOT_MERGED_1_1
    )
    assert _check(["1.2-ci"], _CHAIN, frozenset({"stage 1.1: complete"})) == []


@pytest.mark.parametrize(
    "lookalike",
    [
        "stage 11.1: complete",
        "stage 1.10: complete",
        "stage 1.1: completed",
        'Revert "stage 1.1: complete"',
        "docs(roadmap): stage 1.1: complete",
    ],
)
def test_the_subject_must_match_exactly(lookalike: str) -> None:
    assert _check(["1.2-ci"], _CHAIN, frozenset({lookalike})) == _NOT_MERGED_1_1


def test_status_and_commit_are_reported_together() -> None:
    rows = _row("1.1-bootstrap", status="draft") + _row("1.2-ci", deps="`1.1-bootstrap`")

    assert len(_check(["1.2-ci"], rows, frozenset())) == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    "deps",
    [
        "`7.1-controlid-spike`, `4.5-scheduling-http`",  # a aberta por último
        "`4.5-scheduling-http`, `7.1-controlid-spike`",  # a aberta primeiro, a fechada depois
    ],
)
def test_an_open_dependency_is_reported_in_any_position(deps: str) -> None:
    rows = (
        _row("4.5-scheduling-http", status="draft")
        + _row("7.1-controlid-spike")
        + _row("7.2-timeclock-domain", deps=deps)
    )

    violations = _check(["7.2-timeclock-domain"], rows, frozenset({"stage 7.1: complete"}))

    assert {v.split(":")[0] for v in violations} == {"7.2-timeclock-domain → 4.5-scheduling-http"}
    assert len(violations) == 2  # status e commit da 4.5  # noqa: PLR2004


@pytest.mark.parametrize(
    ("deps", "subjects"),
    [
        ("`1.1-bootstrap`, `#46`", frozenset({"stage 1.1: complete"})),  # Stage fecha, issue não
        ("`#45`, `1.1-bootstrap`", frozenset()),  # issue fecha, Stage não
    ],
)
def test_stage_and_issue_dependencies_are_both_checked(deps: str, subjects: frozenset[str]) -> None:
    rows = _row("1.1-bootstrap") + _row("4.3-scheduling-application", deps=deps)

    assert len(_check(["4.3-scheduling-application"], rows, subjects)) == 1


def test_every_target_is_checked_not_only_the_first() -> None:
    violations = _check(
        ["1.2-ci", "2.1-identity-domain"], _CHAIN, frozenset({"stage 1.1: complete"})
    )

    assert violations == [
        "2.1-identity-domain → 1.2-ci: commit `stage 1.2: complete` não está mergeado em "
        "origin/develop"
    ]


@pytest.mark.parametrize(
    "status",
    [
        "draft",
        "in_progress",
        "review",
        "archived",
        "Done",
        "not done",
        "undone",
        "done?",
        "`done`",
        "**done**",
    ],
)
def test_only_done_closes_a_dependency(status: str) -> None:
    rows = _row("1.1-bootstrap", status=status) + _row("1.2-ci", deps="`1.1-bootstrap`")

    assert _check(["1.2-ci"], rows, _CLOSED) == [
        f"1.2-ci → 1.1-bootstrap: status `{status}` na Tabela de Stages (esperado `done`)"
    ]


def test_target_without_a_row_is_a_violation() -> None:
    assert _check(["9.9-unplanned"], _CHAIN, _CLOSED) == [
        "9.9-unplanned: sem linha na Tabela de Stages — as dependências não são determináveis"
    ]


def test_dependency_without_a_row_is_a_violation() -> None:
    rows = _row("1.2-ci", deps="`1.1-bootstrap`")

    assert _check(["1.2-ci"], rows, _CLOSED) == [
        "1.2-ci → 1.1-bootstrap: a dependência não tem linha na Tabela de Stages"
    ]


def test_a_number_shared_by_two_stages_cannot_close_either() -> None:
    rows = (
        _row("3.7-application-authorization")
        + _row("3.7-termination-access-scope")
        + _row("4.3-scheduling-application", deps="`3.7-application-authorization`")
    )

    violations = _check(["4.3-scheduling-application"], rows, frozenset({"stage 3.7: complete"}))

    assert len(violations) == 1
    assert "3.7-application-authorization, 3.7-termination-access-scope" in violations[0]


def test_homonyms_that_nobody_depends_on_do_not_fail_anyone() -> None:
    rows = _CHAIN + _row("3.7-application-authorization") + _row("3.7-termination-access-scope")

    assert _check(["1.2-ci"], rows, _CLOSED) == []


def test_issue_dependency_is_closed_by_its_status_in_the_issue_table() -> None:
    rows = _row("4.3-scheduling-application", deps="`#45`")

    assert _check(["4.3-scheduling-application"], rows, frozenset()) == []


def test_issue_dependency_not_done_is_a_violation() -> None:
    rows = _row("4.3-scheduling-application", deps="`#46`")

    assert _check(["4.3-scheduling-application"], rows, _CLOSED) == [
        "4.3-scheduling-application → #46: status `open` na Tabela de Issues (esperado `done`)"
    ]


@pytest.mark.parametrize("order", ["open-then-done", "done-then-open"])
def test_an_issue_with_two_rows_cannot_close_a_dependency(order: str) -> None:
    open_row = "| [#47](https://x/47) | C | shared | docs | open | — |\n"
    done_row = "| #47 | C | shared | docs | done | — |\n"
    issues = open_row + done_row if order == "open-then-done" else done_row + open_row
    rows = _row("4.3-scheduling-application", deps="`#47`")
    statuses = csd.parse_issue_table(_roadmap(rows, issues=issues))

    verdict = csd.check_targets(
        ["4.3-scheduling-application"], _rows(rows), _history(_CLOSED), statuses
    )

    assert list(verdict.violations) == [
        "4.3-scheduling-application → #47: a issue aparece em mais de uma linha da Tabela de Issues"
    ]


@pytest.mark.parametrize("status", ["not done", "undone", "done?", "`done`", "**done**"])
def test_only_the_exact_done_closes_an_issue_dependency(status: str) -> None:
    issues = f"| [#47](https://x/47) | C | shared | docs | {status} | — |\n"
    rows = _row("4.3-scheduling-application", deps="`#47`")
    statuses = csd.parse_issue_table(_roadmap(rows, issues=issues))

    verdict = csd.check_targets(
        ["4.3-scheduling-application"], _rows(rows), _history(_CLOSED), statuses
    )

    assert list(verdict.violations) == [
        f"4.3-scheduling-application → #47: status `{status}` na Tabela de Issues (esperado `done`)"
    ]


def test_issue_outside_the_issue_table_points_to_the_stage_id_form() -> None:
    rows = _row("4.3-scheduling-application", deps="`#43`")  # #43 é a issue da Stage 3.6

    violations = _check(["4.3-scheduling-application"], rows, _CLOSED)

    assert len(violations) == 1
    assert "issue fora da Tabela de Issues" in violations[0]
    assert "stage_id" in violations[0]


def test_without_history_only_the_status_is_checked() -> None:
    rows = _row("1.1-bootstrap") + _row("1.2-ci", deps="`1.1-bootstrap`")
    draft = _row("1.1-bootstrap", status="draft") + _row("1.2-ci", deps="`1.1-bootstrap`")

    assert csd.check_targets(["1.2-ci"], _rows(rows), None, {}).violations == ()
    assert len(csd.check_targets(["1.2-ci"], _rows(draft), None, {}).violations) == 1


def test_the_verdict_counts_what_was_actually_checked() -> None:
    """O resumo `OK — N Stage(s), M dependência(s)` só pode afirmar o que o laço olhou."""
    targets = ["1.1-bootstrap", "1.2-ci", "2.1-identity-domain", "9.9-unplanned"]

    verdict = csd.check_targets(targets, _rows(_CHAIN), _history(), {})

    assert (verdict.stages, verdict.dependencies) == (4, 2)
    assert len(verdict.violations) == 1  # só a 9.9, sem linha


# --- alvos --------------------------------------------------------------------------


def test_discovery_takes_only_stage_folders(tmp_path: Path) -> None:
    stages = tmp_path / "docs" / "stages"
    for folder in ("1.2-ci", "1.1-bootstrap", "_archived", "1.3-Not-Kebab"):
        (stages / folder).mkdir(parents=True)
    (stages / "2.1-identity-domain").write_text("arquivo, não pasta", encoding="utf-8")

    assert csd.discover_stage_folders(tmp_path) == ["1.1-bootstrap", "1.2-ci"]


def test_discovery_without_stages_folder_finds_nothing(tmp_path: Path) -> None:
    assert csd.discover_stage_folders(tmp_path) == []


def test_a_stage_id_is_a_valid_target() -> None:
    assert csd.target_problem("4.3-scheduling-application") is None


def test_a_bare_number_is_refused_with_the_form_to_use() -> None:
    problem = csd.target_problem("4.3")

    assert problem is not None
    assert "número da Stage" in problem
    assert "`4.3-<slug>`" in problem


def test_anything_else_is_refused() -> None:
    problem = csd.target_problem("bootstrap")

    assert problem is not None
    assert "não é um stage_id" in problem


# --- main ---------------------------------------------------------------------------


class _History:
    """Leitor de histórico injetado: registra a chamada, devolve subjects fixos."""

    def __init__(self, subjects: frozenset[str] = _CLOSED, error: Exception | None = None) -> None:
        self.subjects = subjects
        self.error = error
        self.calls: list[tuple[tuple[str, ...], Path, bool]] = []

    def __call__(self, refs: Sequence[str], repo: Path, every_ref: bool) -> Any:  # noqa: ANN401
        self.calls.append((tuple(refs), repo, every_ref))
        if self.error is not None:
            raise self.error
        return csd.History(self.subjects, tuple(refs))


def _repo(tmp_path: Path, rows: str = _CHAIN, folders: Sequence[str] = ()) -> Path:
    roadmap = tmp_path / "docs" / "roadmap.md"
    roadmap.parent.mkdir(parents=True, exist_ok=True)
    roadmap.write_text(_roadmap(rows), encoding="utf-8")
    for folder in folders:
        (tmp_path / "docs" / "stages" / folder).mkdir(parents=True)
    return tmp_path


def _main(repo: Path, history: _History, *args: str) -> int:
    return int(csd.main([*args, "--repo", str(repo)], read_history=history))


def test_main_checks_every_stage_folder_against_the_integration_branches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, folders=("1.1-bootstrap", "1.2-ci"))
    history = _History()

    assert _main(repo, history) == csd.EXIT_OK
    assert history.calls == [(csd.INTEGRATION_REFS, repo, False)]
    out = capsys.readouterr().out
    assert "2 Stage(s), 1 dependência(s) fechada(s) em origin/develop, develop" in out


def test_main_violation_exits_1_and_explains_the_number(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, folders=("2.1-identity-domain",))

    assert _main(repo, _History(frozenset({"stage 1.1: complete"}))) == csd.EXIT_VIOLATION
    err = capsys.readouterr().err
    assert "2.1-identity-domain → 1.2-ci: commit `stage 1.2: complete` não está mergeado" in err
    assert "`1.1-bootstrap` → `stage 1.1: complete`" in err


def test_main_explicit_targets_replace_discovery(tmp_path: Path) -> None:
    rows = _CHAIN + _row("3.1-staff-domain", status="draft", deps="`2.1-identity-domain`")
    repo = _repo(tmp_path, rows=rows, folders=("3.1-staff-domain",))  # a 2.1 não fechou

    assert _main(repo, _History()) == csd.EXIT_VIOLATION
    assert _main(repo, _History(), "1.2-ci") == csd.EXIT_OK


@pytest.mark.parametrize(
    ("args", "refs"),
    [
        (("--ref", "origin/develop"), ("origin/develop",)),
        (("--ref", "origin/develop", "--ref", "origin/main"), ("origin/develop", "origin/main")),
    ],
)
def test_main_explicit_refs_must_all_resolve(
    tmp_path: Path, args: tuple[str, ...], refs: tuple[str, ...]
) -> None:
    repo = _repo(tmp_path)
    history = _History()

    assert _main(repo, history, "1.2-ci", *args) == csd.EXIT_OK
    assert history.calls == [(refs, repo, True)]


@pytest.mark.parametrize("target", ["4.3", "bootstrap", "1.1-bootstrap/"])
def test_main_refuses_a_target_that_is_not_a_stage_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], target: str
) -> None:
    history = _History()

    assert _main(tmp_path, history, target) == csd.EXIT_ERROR  # nem precisa de roadmap
    assert history.calls == []
    assert target in capsys.readouterr().err


def test_main_fails_closed_without_roadmap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(tmp_path, _History()) == csd.EXIT_ERROR
    assert "roadmap ausente" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"## Tabela de Stages\n\xed\xa0\x80\n", None])
def test_main_fails_closed_on_an_unreadable_roadmap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes | None
) -> None:
    roadmap = tmp_path / "docs" / "roadmap.md"
    if content is None:
        roadmap.mkdir(parents=True)  # um diretório no lugar do arquivo: OSError
    else:
        roadmap.parent.mkdir(parents=True)
        roadmap.write_bytes(content)  # não é UTF-8: UnicodeDecodeError

    # Exit 1 seria lido como "dependência aberta"; sem leitura, não há veredito.
    assert _main(tmp_path, _History(), "1.2-ci") == csd.EXIT_ERROR
    assert "roadmap ilegível" in capsys.readouterr().err


def test_main_fails_closed_without_the_stage_table(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "docs" / "roadmap.md").write_text("# Roadmap\n\n## Outra\n", encoding="utf-8")

    assert _main(repo, _History(), "1.2-ci") == csd.EXIT_ERROR


def test_main_fails_closed_when_the_stage_folders_cannot_be_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_: Path) -> list[str]:
        raise PermissionError("docs/stages")

    monkeypatch.setattr(csd, "discover_stage_folders", denied)

    assert _main(_repo(tmp_path), _History()) == csd.EXIT_ERROR


def test_main_an_explicit_target_without_history_has_no_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pré-condição de quem vai abrir uma Stage não aceita verde sem ter olhado."""
    history = _History(error=csd.HistoryUnavailable("clone raso"))

    assert _main(_repo(tmp_path), history, "1.2-ci") == csd.EXIT_ERROR
    assert "clone raso (fail closed)" in capsys.readouterr().err


def test_main_docs_check_without_history_checks_status_and_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem alvo, o `make check` local não exige histórico (ADR 1.2.0001): status + WARN."""
    history = _History(error=csd.HistoryUnavailable("clone raso"))
    repo = _repo(tmp_path, folders=("1.2-ci",))

    assert _main(repo, history) == csd.EXIT_OK
    captured = capsys.readouterr()
    assert "WARN — clone raso" in captured.err
    assert "1 Stage(s), 1 dependência(s) fechada(s)\n" in captured.out


def test_main_docs_check_without_history_still_catches_a_status(tmp_path: Path) -> None:
    history = _History(error=csd.HistoryUnavailable("clone raso"))
    repo = _repo(tmp_path, folders=("2.1-identity-domain", "3.1-staff-domain"))
    rows = _CHAIN + _row("3.1-staff-domain", deps="`2.1-identity-domain`")  # a 2.1 é draft
    (repo / "docs" / "roadmap.md").write_text(_roadmap(rows), encoding="utf-8")

    assert _main(repo, history) == csd.EXIT_VIOLATION


def test_main_docs_check_with_an_unresolvable_explicit_ref_has_no_verdict(tmp_path: Path) -> None:
    history = _History(error=csd.GitError("ref(s) origin/nada não resolve(m)"))
    repo = _repo(tmp_path, folders=("1.2-ci",))

    assert _main(repo, history, "--ref", "origin/nada") == csd.EXIT_ERROR


def test_main_without_stage_folders_reads_no_history(tmp_path: Path) -> None:
    history = _History()

    assert _main(_repo(tmp_path), history) == csd.EXIT_OK
    assert history.calls == []


def test_main_gives_a_verdict_without_history_when_no_target_has_dependencies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem dependência, o histórico não é preciso: clone raso não tira o veredito."""
    history = _History(error=csd.HistoryUnavailable("clone raso"))

    assert _main(_repo(tmp_path), history, "1.1-bootstrap") == csd.EXIT_OK
    assert history.calls == []
    assert "1 Stage(s), 0 dependência(s)" in capsys.readouterr().out


def test_main_checks_issue_dependencies_against_the_issue_table(tmp_path: Path) -> None:
    rows = _row("4.3-scheduling-application", deps="`#46`")  # a #46 está open
    repo = _repo(tmp_path, rows=rows, folders=("4.3-scheduling-application",))

    assert _main(repo, _History()) == csd.EXIT_VIOLATION


def test_main_fails_closed_without_the_issue_table_when_it_is_needed(tmp_path: Path) -> None:
    rows = _row("4.3-scheduling-application", deps="`#45`")
    repo = _repo(tmp_path, rows=rows, folders=("4.3-scheduling-application",))
    text = _roadmap(rows).split("## Tabela de Issues")[0]
    (repo / "docs" / "roadmap.md").write_text(text, encoding="utf-8")

    assert _main(repo, _History()) == csd.EXIT_ERROR


def test_main_reports_roadmap_problems_even_without_targets(tmp_path: Path) -> None:
    repo = _repo(tmp_path, rows=_CHAIN + "| 2.2 | T | domain | draft | — |\n")

    assert _main(repo, _History()) == csd.EXIT_VIOLATION


def test_main_keeps_roadmap_problems_next_to_closed_dependencies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _CHAIN + "| 2.2 | T | domain | draft | — |\n"
    repo = _repo(tmp_path, rows=rows, folders=("1.2-ci",))  # a 1.2 está fechada

    assert _main(repo, _History()) == csd.EXIT_VIOLATION
    assert "`2.2` não é um stage_id" in capsys.readouterr().err


# --- leitura do histórico (git injetado via subprocess.run) --------------------------


class _Git:
    """Substituto de `subprocess.run` para os comandos que o script usa."""

    def __init__(
        self,
        *,
        shallow: bool = False,
        resolvable: Sequence[str] = ("origin/develop", "develop"),
        log: bytes = b"",
    ) -> None:
        self.shallow = shallow
        self.resolvable = set(resolvable)
        self.log = log
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:  # noqa: ANN401
        self.calls.append((cmd, dict(kwargs)))
        if cmd[1:3] == ["rev-parse", "--is-shallow-repository"]:
            return self._done(0, b"true\n" if self.shallow else b"false\n")
        if cmd[1:3] == ["rev-parse", "--verify"]:
            ref = cmd[-1].removesuffix("^{commit}")
            return self._done(0 if ref in self.resolvable else 1, b"")
        if cmd[1] == "log":
            return self._done(0, self.log)
        return self._done(128, b"", b"comando inesperado")

    @staticmethod
    def _done(code: int, out: bytes, err: bytes = b"") -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=[], returncode=code, stdout=out, stderr=err)


def test_history_is_the_union_of_the_integration_branches_that_resolve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    git = _Git(log="stage 1.1: complete\nfeat(x): acentuação  \n".encode())
    monkeypatch.setattr(csd.subprocess, "run", git)

    history = csd.git_history(csd.INTEGRATION_REFS, tmp_path, False)

    assert history.subjects == frozenset({"stage 1.1: complete", "feat(x): acentuação"})
    assert history.refs == ("origin/develop", "develop")
    assert all(kwargs["cwd"] == tmp_path for _, kwargs in git.calls)
    assert git.calls[-1][0] == ["git", "log", "--format=%s", "origin/develop", "develop"]


def test_an_explicit_ref_that_does_not_resolve_is_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(csd.subprocess, "run", _Git())

    with pytest.raises(csd.GitError, match=r"origin/nada não resolve.*git fetch") as raised:
        csd.git_history(("origin/develop", "origin/nada"), tmp_path, True)
    assert not isinstance(raised.value, csd.HistoryUnavailable)


def test_no_integration_branch_means_no_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(csd.subprocess, "run", _Git(resolvable=()))

    with pytest.raises(csd.HistoryUnavailable, match="nenhuma branch de integração"):
        csd.git_history(csd.INTEGRATION_REFS, tmp_path, False)


def test_shallow_clone_means_no_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(csd.subprocess, "run", _Git(shallow=True))

    with pytest.raises(csd.HistoryUnavailable, match="clone raso"):
        csd.git_history(csd.INTEGRATION_REFS, tmp_path, False)


def test_git_that_cannot_run_means_no_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def no_git(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:  # noqa: ANN401
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr(csd.subprocess, "run", no_git)

    with pytest.raises(csd.HistoryUnavailable, match="`git` não pôde ser executado"):
        csd.git_history(csd.INTEGRATION_REFS, tmp_path, False)


def test_git_failure_carries_the_command_and_its_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def broken(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:  # noqa: ANN401
        return subprocess.CompletedProcess(cmd, 128, b"", b"fatal: not a git repository")

    monkeypatch.setattr(csd.subprocess, "run", broken)

    with pytest.raises(csd.GitError, match="not a git repository"):
        csd.git_history(csd.INTEGRATION_REFS, tmp_path, False)


def test_main_without_git_has_no_verdict_for_an_explicit_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_git(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:  # noqa: ANN401
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr(csd.subprocess, "run", no_git)
    repo = _repo(tmp_path)

    assert int(csd.main(["1.2-ci", "--repo", str(repo)])) == csd.EXIT_ERROR  # leitor real
    assert "`git` não pôde ser executado" in capsys.readouterr().err


# --- o que a auditoria de testes da #12 pegou sobrevivendo ---------------------------


@pytest.mark.parametrize("missing", ["Stage", "Status", "Depende de"])
def test_each_required_column_is_required(missing: str) -> None:
    columns = [c for c in ("Stage", "Título", "Status", "Depende de") if c != missing]
    header = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"

    with pytest.raises(csd.RoadmapError, match=f"coluna\\(s\\) {missing}$"):
        csd.parse_stage_table(_SECTION + header)


def test_a_table_with_no_rows_is_empty_not_unreadable() -> None:
    assert csd.parse_stage_table(_SECTION + _HEADER) == ([], [])


def test_a_second_table_in_the_section_is_not_read() -> None:
    text = (
        _SECTION
        + _HEADER
        + _row("1.1-bootstrap")
        + "\nOutra tabela, de exemplo:\n\n"
        + _HEADER
        + "| 2.1 | T | domain | done | — |\n\n## Próxima seção\n"
    )

    assert csd.parse_stage_table(text) == (
        [csd.StageRow("1.1-bootstrap", "done", (), ())],
        [],
    )


def test_a_section_without_a_table_does_not_borrow_the_next_one() -> None:
    text = (
        "## Tabela de Stages\n\nAinda sem Stages.\n\n"
        "## Tabela de Issues\n\n| Stage | Status | Depende de |\n|---|---|---|\n"
    )

    with pytest.raises(csd.RoadmapError, match="sem cabeçalho e separador"):
        csd.parse_stage_table(text)


@pytest.mark.parametrize("cell", ["—", "-", ""])
def test_the_no_dependency_markers(cell: str) -> None:
    (row,) = _rows(f"| `1.1-bootstrap` | T | domain | done | {cell} |\n")

    assert (row.depends_on, row.depends_on_issues) == ((), ())


def test_cells_may_omit_the_code_span() -> None:
    (row,) = _rows("| 1.2-ci | T | domain | done | 1.1-bootstrap, #45 |\n")

    assert (row.stage_id, row.depends_on, row.depends_on_issues) == (
        "1.2-ci",
        ("1.1-bootstrap",),
        (45,),
    )


def test_a_bare_x_number_gets_the_same_explanation() -> None:
    problem = csd.target_problem("X.4")

    assert problem is not None
    assert "número da Stage" in problem


def test_main_refuses_a_bad_target_in_any_position(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    history = _History()

    assert _main(_repo(tmp_path), history, "1.2-ci", "4.3") == csd.EXIT_ERROR
    assert history.calls == []
    assert "`4.3` é o número da Stage" in capsys.readouterr().err


def test_main_checks_every_folder_not_only_the_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, folders=("1.1-bootstrap", "2.1-identity-domain"))

    assert _main(repo, _History(frozenset({"stage 1.1: complete"}))) == csd.EXIT_VIOLATION
    assert "2.1-identity-domain → 1.2-ci" in capsys.readouterr().err


def test_main_reports_every_violation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rows = _row("1.1-bootstrap", status="draft") + _row("1.2-ci", deps="`1.1-bootstrap`")
    repo = _repo(tmp_path, rows=rows, folders=("1.2-ci",))

    assert _main(repo, _History(frozenset())) == csd.EXIT_VIOLATION
    err = capsys.readouterr().err
    assert "FALHA — 2 violação(ões)" in err
    assert "status `draft`" in err
    assert "não está mergeado" in err


def test_main_closes_an_issue_dependency_without_reading_git(tmp_path: Path) -> None:
    rows = _row("4.3-scheduling-application", deps="`#45`")  # a #45 está done
    repo = _repo(tmp_path, rows=rows, folders=("4.3-scheduling-application",))
    history = _History()

    assert _main(repo, history) == csd.EXIT_OK
    assert history.calls == []


def test_git_runs_with_exact_commands_and_without_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bytes capturados e `check=False`: erro do git vira `GitError`, nunca traceback."""
    git = _Git(log=b"stage 1.1: complete\n")
    monkeypatch.setattr(csd.subprocess, "run", git)

    csd.git_history(("origin/develop",), tmp_path, True)

    assert [cmd for cmd, _ in git.calls] == [
        ["git", "rev-parse", "--is-shallow-repository"],
        ["git", "rev-parse", "--verify", "--quiet", "origin/develop^{commit}"],
        ["git", "log", "--format=%s", "origin/develop"],
    ]
    assert all(
        kwargs == {"cwd": tmp_path, "capture_output": True, "check": False}
        for _, kwargs in git.calls
    )


def test_integration_branches_are_the_ones_the_section_7_freeze_uses() -> None:
    """ "Mergeada" quer dizer o mesmo aqui e no `check_technical_postexec.py` (ADR 1.2.0001)."""
    path = _SCRIPT.parent / "check_technical_postexec.py"
    spec = importlib.util.spec_from_file_location("check_technical_postexec", path)
    assert spec is not None and spec.loader is not None
    postexec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(postexec)

    assert csd.INTEGRATION_REFS == postexec._INTEGRATION_REFS
    assert csd.INTEGRATION_REFS == ("origin/develop", "develop", "origin/main", "main")

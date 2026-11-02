"""O hook `commit-msg` (`scripts/check_commit_msg.py`) valida a marca de Task.

Issue #34. Até ela, o grupo da marca no `CC_PATTERN` era opcional e a descrição
engolia qualquer `[...]` que não casasse com `task-NN` ou `--`. Os três subjects
do achado F9 da auditoria da Stage 4.1 saíam com exit 0 — `[4.1/task-03-fix]`
(forma legítima, mas que o hook nunca via), `[4.1/tsk-3]` e `[41/--]`
(malformadas). Os commits `-fix` do histórico passaram pelo hook assim, sem
validação nenhuma da marca.

A gramática travada aqui é a de CONVENTIONS.md §4(a), subseção "Marca de Task":
`[<dono>/<posição>]`, dono `N.M` (Stage) ou `#<num>` (issue avulsa), posição
`task-NN`, `task-NN-fix`, `task-NN-extra` ou `--`.

**Por que conferir o grupo capturado, e não só o exit code.** Antes da #34,
`[4.1/task-03-fix]` também dava exit 0 — como texto livre. Aceitar não basta
para provar que a marca foi validada; o teste exige que ela tenha sido lida
como marca (`group("tag")`).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_commit_msg.py"

_EXIT_OK = 0
_EXIT_REJECTED = 1
_EXIT_USAGE = 2


def _load() -> ModuleType:
    """Importa `scripts/check_commit_msg.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_commit_msg", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ccm = _load()


def _accepted(subject: str) -> bool:
    return bool(ccm.validate_subject(subject) == _EXIT_OK)


def _captured_tag(subject: str) -> str | None:
    match = ccm.CC_PATTERN.match(subject)
    assert match is not None, f"nem casa Conventional Commits: {subject!r}"
    tag: str | None = match.group("tag")
    return tag


# --- Os três casos do achado F9 ---------------------------------------------


def test_f9_fix_suffix_is_read_as_a_tag_and_accepted() -> None:
    subject = "feat(scheduling): x [4.1/task-03-fix]"
    assert _captured_tag(subject) == "4.1/task-03-fix"
    assert _accepted(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "feat(scheduling): x [4.1/tsk-3]",
        "feat(scheduling): x [41/--]",
    ],
)
def test_f9_malformed_tags_are_rejected(subject: str) -> None:
    assert not _accepted(subject)


# --- A gramática: dono x posição --------------------------------------------

_WELL_FORMED_TAGS = [
    # Stage: o dono é o número N.M.
    "4.1/task-03",
    "4.1/task-03-fix",
    "4.1/task-11-extra",
    "4.1/--",
    "12.10/task-07",
    # Issue avulsa: o dono é #<num> (PROMPT-issue-single-session.md, issue-audit).
    "#34/task-01",
    "#34/task-01-fix",
    "#34/task-06-extra",
    "#34/--",
]


@pytest.mark.parametrize("tag", _WELL_FORMED_TAGS)
def test_well_formed_tag_is_read_as_a_tag_and_accepted(tag: str) -> None:
    subject = f"docs(conventions): documentar a marca [{tag}]"
    assert _captured_tag(subject) == tag
    assert _accepted(subject)


_MALFORMED_TAGS = [
    "4.1/tsk-3",
    "4.1/task-3",  # NN com um dígito
    "4.1/task-003",  # NN com três dígitos
    "4.1/task-03-fixx",
    "4.1/task-03-fix2",  # ordinal: fora da gramática (CONVENTIONS §4(a))
    "4.1/task-03-extra2",
    "4.1/task-03-fix-extra",
    "4.1/task-03-",
    "4.1/task-",
    "4.1/TASK-03",
    "4.1/post-done",
    "4.1/-",
    "4.1/---",
    "4.1/",
    "4.1",
    "41/--",  # dono sem o ponto
    "4/task-03",
    "4.1.2/task-03",
    "v4.1/task-03",
    "1.1-bootstrap/--",  # stage_id no lugar do número
    ".1/task-03",  # componente do N.M vazio
    "4./task-03",
    "#4.1/task-01",  # número de Stage com `#`
    "#34.1/--",
    "/task-03",
    "#/task-01",
    "#a/task-01",
    "34/task-01",  # issue sem `#`
    "#34",
    " 4.1/task-03",
    "4.1/task-03 ",
    "4.1 /task-03",
    "4.1/ task-03",
    "",
    # Dígito não-ASCII: em `str`, `\d` casa qualquer dígito Unicode.
    "\u0664.\u0661/task-03",
    "4.1/task-\u0660\u0663",
    "4.1/task-\uff10\uff13",
    "#\uff13\uff14/--",
]


@pytest.mark.parametrize("tag", _MALFORMED_TAGS)
def test_malformed_tag_at_the_end_is_rejected(tag: str) -> None:
    assert not _accepted(f"feat(scheduling): x [{tag}]")


@pytest.mark.parametrize(
    "subject",
    [
        "feat(shared): tipar o retorno como list[int]",  # colchete colado à palavra
        "feat(shared): aceitar o campo [opcional]",
        "feat(scheduling): x[4.1/task-03]",  # marca válida, sem o espaço
        "feat(scheduling): x  [4.1/task-03]",  # marca válida, dois espaços
        "feat(scheduling): x \u00a0[4.1/task-03]",  # espaço + espaço não separável
        "feat(scheduling): x\t[4.1/task-03]",  # tab no lugar do espaço
        "feat(scheduling): [4.1/task-03]",  # marca válida, sem descrição
        "feat(scheduling): x [[4.1/task-03]]",
        "feat(scheduling): x [4.1/task-03]]",
        "docs(overview): approved [projects/My_Project]",  # bootstrap fora do reservado
    ],
)
def test_subject_ending_in_bracket_must_end_in_a_tag(subject: str) -> None:
    assert not _accepted(subject)


@pytest.mark.parametrize(
    "subject",
    [
        "feat(shared): tipar o retorno como list[int] [4.1/task-03]",
        "feat(shared): tipar list[int] no retorno",
        "feat(scheduling): x [4.1/task-03] y [4.1/task-04]",
    ],
)
def test_brackets_inside_the_description_stay_free_text(subject: str) -> None:
    assert _accepted(subject)


def test_only_the_last_group_is_read_as_the_tag() -> None:
    subject = "feat(scheduling): x [4.1/task-03] y [4.1/task-04]"
    assert _captured_tag(subject) == "4.1/task-04"


def test_a_tag_in_the_middle_of_the_subject_is_free_text() -> None:
    """A marca fecha o subject; no meio, é descrição (CONVENTIONS §4(a), regra 4:
    o hook só recusa o subject que termina em `]`)."""
    subject = "feat(scheduling): x [4.1/task-03] y"
    assert _captured_tag(subject) is None
    assert _accepted(subject)


# --- O motivo da recusa -------------------------------------------------------


def test_rejection_names_the_group_read_as_the_tag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert ccm.validate_subject("feat(scheduling): x [4.1/tsk-3]") == _EXIT_REJECTED
    err = capsys.readouterr().err
    assert "marca de Task inválida no fim do subject (lido: `[4.1/tsk-3]`)" in err


def test_rejection_without_a_readable_group_still_explains_the_tag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert ccm.validate_subject("feat(scheduling): x [[4.1/task-03]]") == _EXIT_REJECTED
    err = capsys.readouterr().err
    assert "marca de Task inválida no fim do subject —" in err


# --- Escopo que nomeia a Stage (issue #90) -----------------------------------
#
# CONVENTIONS.md §4(a), regra de escopo mínimo: o escopo é o BC/módulo, nunca a
# Stage. Até a #90 o grupo `scope` aceitava qualquer `[a-z0-9._-]+`, e
# `docs(stage-1-1): ...` entrou em develop (§7 da `1.2-ci/technical.md`).

_STAGE_SCOPES = [
    "stage",
    "stage-2.3",  # o ❌ do §4(a)
    "stage-12.10",  # o ❌ do §4(c)
    "stage-1-1",  # o precedente do histórico
    "stage.2.3",
    "stage_2_3",
    "stage2.3",
    "stage-1",
    "docs.stage-2.3",
    "roadmap-stage-4.1",
    "2.3",
    "12.10",
    "1-1",
    "1_1",
    "4.1-scheduling-domain",  # o stage_id
    "3.6-staff-http",
]


@pytest.mark.parametrize("scope", _STAGE_SCOPES)
def test_scope_naming_the_stage_is_rejected_citing_the_rule(
    scope: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ccm.validate_subject(f"feat({scope}): x [2.3/task-01]") == _EXIT_REJECTED
    err = capsys.readouterr().err
    assert f"escopo `{scope}` nomeia a Stage" in err
    assert "CONVENTIONS.md §4(a)" in err


@pytest.mark.parametrize("scope", _STAGE_SCOPES)
def test_scope_naming_the_stage_is_rejected_without_a_tag(scope: str) -> None:
    """A recusa não depende da marca: sem ela, o subject é o mesmo erro."""
    assert not _accepted(f"docs({scope}): x")


# Escopos que contêm `stage` ou números sem nomear a Stage. `prompt-stage` está
# no histórico de develop (o doc `PROMPT-stage-*.md`); `stage-audit` é a skill.
_LEGIT_SCOPES = [
    "staging",
    "stages",
    "stage-audit",
    "prompt-stage",
    "prompt-stage-autonomous",
    "backstage",
    "process",
    "tooling",
    "scheduling",
    "payment.retry",
    "v2",
    "oauth2",
    "0.0.0016",  # número de ADR: três componentes
    "1.2.3",
    "2fa",
    "2-factor",
    "concept",
]


@pytest.mark.parametrize("scope", _LEGIT_SCOPES)
def test_legitimate_scope_is_still_accepted(scope: str) -> None:
    assert _accepted(f"docs({scope}): x [2.3/task-01]")


@pytest.mark.parametrize(
    "subject",
    [
        "stage 3.9: conceptual draft",
        "stage 3.9: technical approved",
        "stage 3.9: complete",
        "chore(concept): revert to draft -- revision-from-technical: gap",
        "chore(technical): revert to draft — revision-from-execution: gap",
        "refactor(shared): mover a hierarquia de erros [3.9/task-01]",
    ],
)
def test_reserved_gates_and_stage_tags_are_not_scopes(subject: str) -> None:
    """O número da Stage segue valendo onde ele mora: no gate reservado e na marca."""
    assert _accepted(subject)


def test_the_conventions_negative_scope_examples_are_rejected_by_the_hook() -> None:
    """Os ❌ de escopo do §4(a)/(c) são o que a regra proíbe; o hook tem de recusá-los."""
    conventions = (_REPO_ROOT / "docs" / "CONVENTIONS.md").read_text(encoding="utf-8")
    negatives = re.findall(
        r"❌ `((?:" + "|".join(ccm.ALLOWED_TYPES) + r")\(stage[^)]*\): [^`]+)`",
        conventions,
    )
    scopes = {subject.split(":")[0] for subject in negatives}
    assert {"feat(stage-2.3)", "feat(stage-12.10)"} <= scopes
    accepted = [subject for subject in negatives if _accepted(subject)]
    assert not accepted, f"❌ de escopo que o hook aceita: {accepted}"


def test_the_scope_check_reads_the_scope_not_the_description() -> None:
    assert _accepted("docs(conventions): proibir stage-2.3 como escopo [#90/task-02]")


# --- O que a #34 não mudou ---------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "stage 4.1: conceptual draft",
        "stage 4.1: technical approved",
        "stage 4.1: complete",
        "docs(roadmap): approved",
        "docs(overview): approved [projects/restaurant-hub]",
        "docs(roadmap): approved [projects/restaurant-hub] (adoption)",
        "chore(technical): revert to draft — revision-from-execution: gap no plano",
        "chore: bootstrap from whaka-dev-project-template",
        "Merge pull request #66 from MarceloSanC/feat/64-4-2-validation-policies",
        "Revert [4.1/tsk-3]",
        "chore(roadmap): fechar issue #34",
    ],
)
def test_reserved_passthrough_and_untagged_subjects_are_accepted(subject: str) -> None:
    assert _accepted(subject)


@pytest.mark.parametrize(
    ("subject", "reason"),
    [
        ("", "empty subject"),
        ("feat: x [4.1/task-03]", "escopo ausente"),
        ("feature(x): y [4.1/task-03]", "não bate com Conventional Commits"),
        ("feat(x): " + "y" * 100 + " [4.1/task-03]", "subject too long"),
    ],
)
def test_other_rejections_keep_their_reasons(
    subject: str, reason: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ccm.validate_subject(subject) == _EXIT_REJECTED
    assert reason in capsys.readouterr().err


# O limite que os technicals citam (`subject ≤ 100 caracteres`, `MAX_SUBJECT_LEN`).
_SUBJECT_LIMIT = 100


@pytest.mark.parametrize(
    ("length", "exit_code"),
    [(_SUBJECT_LIMIT, _EXIT_OK), (_SUBJECT_LIMIT + 1, _EXIT_REJECTED)],
)
def test_subject_limit_is_inclusive_and_counts_the_tag(length: int, exit_code: int) -> None:
    head, tag = "feat(scheduling): ", " [4.1/task-03]"
    subject = head + "x" * (length - len(head) - len(tag)) + tag
    assert len(subject) == length
    assert ccm.validate_subject(subject) == exit_code


# --- O hook como o git o chama -------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "exit_code"),
    [
        ("feat(scheduling): x [4.1/task-03-fix]", _EXIT_OK),
        ("feat(scheduling): x [4.1/tsk-3]", _EXIT_REJECTED),
        ("feat(scheduling): x [41/--]", _EXIT_REJECTED),
        ("feat(stage-2.3): x", _EXIT_REJECTED),
        ("feat(stage-12.10): x", _EXIT_REJECTED),
    ],
)
def test_hook_exit_code_on_a_commit_message_file(
    tmp_path: Path, subject: str, exit_code: int
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        f"# comentário do git\n{subject}\n\n- bullet\n\nRefs #34\n", encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), str(message)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == exit_code, result.stderr


@pytest.mark.parametrize(
    ("subject", "exit_code"),
    [
        ("feat(scheduling): x [4.1/task-03-fix]  \t", _EXIT_OK),
        # O espaço no fim não esconde a marca malformada: a checagem "termina em
        # `]`" depende do `rstrip` do main.
        ("feat(scheduling): x [4.1/tsk-3]  \t", _EXIT_REJECTED),
    ],
)
def test_main_reads_the_subject_after_git_comments_without_trailing_spaces(
    tmp_path: Path, subject: str, exit_code: int
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        f"# Please enter the commit message\n#\n{subject}\n\n- bullet\n", encoding="utf-8"
    )
    assert ccm.main(["check_commit_msg.py", str(message)]) == exit_code


def test_main_with_only_git_comments_rejects_the_empty_subject(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("# Please enter the commit message\n#\n", encoding="utf-8")
    assert ccm.main(["check_commit_msg.py", str(message)]) == _EXIT_REJECTED


def test_main_without_the_message_file_argument_exits_usage() -> None:
    assert ccm.main(["check_commit_msg.py"]) == _EXIT_USAGE


def test_main_with_an_unreadable_message_file_exits_usage(tmp_path: Path) -> None:
    assert ccm.main(["check_commit_msg.py", str(tmp_path / "ausente")]) == _EXIT_USAGE


# --- Os docs que prescrevem a marca, contra o hook -----------------------------
#
# O hook que recusa marca fora da gramática cria o risco inverso do que ele
# fecha: uma forma que um prompt, runbook ou skill manda usar e que o hook não
# conhece trava o commit de quem segue o doc. Esta varredura passa pelo hook
# cada marca escrita nos docs que PRESCREVEM a forma do commit.
#
# Ficam fora `docs/stages/**` e `docs/adr/**`: registram o que aconteceu, e o
# histórico tem formas anteriores à gramática (`-extra2`, …) que não se
# reescrevem (CONVENTIONS.md §4(a), "Marca de Task", regra 5). Exemplo negativo
# vai numa linha marcada com ❌.

_PRESCRIBING_DOCS = (
    "CLAUDE.md",
    "README.md",
    "docs/CONVENTIONS.md",
    "docs/GIT-WORKFLOW.md",
    "docs/LAYOUT.md",
    "docs/PIPELINE.md",
    "docs/PROMPT-*.md",
    "docs/RUNBOOK-*.md",
    "docs/templates/*.md",
    "docs/runbooks/*.md",
    ".claude/skills/*/SKILL.md",
    ".claude/agents/*.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

# Marca escrita num doc: dono reconhecível (placeholder ou número) e posição. Dono
# que não casa (`<stage_id>`, `1.1-bootstrap`) fica fora: o que a varredura cobra
# é a posição, que é onde doc e hook divergem.
_DOC_TAG = re.compile(
    r"\[(?P<owner><N\.M>|N\.M|\$N\.\$M|\d+\.\d+|#<issue>|#<num>|#\d+)"
    r"/(?P<position>[^\]\s`|]+)\]"
)
_OWNER_EXAMPLE = {
    "<N.M>": "4.1",
    "N.M": "4.1",
    "$N.$M": "4.1",
    "#<issue>": "#34",
    "#<num>": "#34",
}
_NEGATIVE_EXAMPLE = "❌"
_ANY_SLASHED_GROUP = re.compile(r"\[[^\]\s`/]+/[^\]\s`]+\]")
_ELLIPSIS = frozenset({"...", "…"})


def _prescribed_tags() -> list[tuple[str, str, str]]:
    """(onde, dono, posição) de cada marca escrita nos docs que prescrevem."""
    found: list[tuple[str, str, str]] = []
    for pattern in _PRESCRIBING_DOCS:
        for path in sorted(_REPO_ROOT.glob(pattern)):
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, start=1):
                if _NEGATIVE_EXAMPLE in line:
                    continue
                for tag in _DOC_TAG.finditer(line):
                    if tag["position"] in _ELLIPSIS:
                        continue
                    where = f"{path.relative_to(_REPO_ROOT)}:{number}"
                    found.append((where, tag["owner"], tag["position"]))
    return found


_PRESCRIBED = _prescribed_tags()


def _instantiate(owner: str, position: str) -> str:
    return f"{_OWNER_EXAMPLE.get(owner, owner)}/{position.replace('NN', '07')}"


def _kind(owner: str, position: str) -> tuple[str, str]:
    owner_kind = "issue" if owner.startswith("#") else "stage"
    if position == "--":
        return owner_kind, "off-task"
    for suffix in ("fix", "extra"):
        if position.endswith(f"-{suffix}"):
            return owner_kind, suffix
    return owner_kind, "task"


def test_every_tag_the_docs_prescribe_is_accepted_by_the_hook() -> None:
    refused = [
        f"{where}: [{owner}/{position}]"
        for where, owner, position in _PRESCRIBED
        if not _accepted(f"docs(conventions): exemplo [{_instantiate(owner, position)}]")
    ]
    assert not refused, (
        "marca prescrita que o hook recusa — alinhe o doc à gramática de "
        'CONVENTIONS.md §4(a), "Marca de Task", ou, se for exemplo negativo, '
        "marque a linha com ❌:\n" + "\n".join(refused)
    )


def test_the_scan_sees_every_position_for_both_owners() -> None:
    """Sem este piso, um `_DOC_TAG` quebrado não acharia marca nenhuma e a
    varredura acima passaria vazia."""
    seen = {_kind(owner, position) for _, owner, position in _PRESCRIBED}
    expected = {
        (owner, position)
        for owner in ("stage", "issue")
        for position in ("task", "fix", "extra", "off-task")
    }
    assert expected <= seen, f"faltam na varredura: {sorted(expected - seen)}"


def test_a_negative_example_is_really_refused_by_the_hook() -> None:
    """O ❌ tira a linha da varredura; o exemplo negativo do §4(a) tem de ser
    mesmo recusado, senão a marca de negativo esconde uma forma válida."""
    conventions = (_REPO_ROOT / "docs" / "CONVENTIONS.md").read_text(encoding="utf-8")
    # Padrão mais largo que o `_DOC_TAG`: o negativo existe justamente para ter
    # dono fora da gramática (`[41/--]`, `[4.1-scheduling-domain/--]`).
    negatives = [
        tag.group(0)
        for line in conventions.splitlines()
        if _NEGATIVE_EXAMPLE in line
        for tag in _ANY_SLASHED_GROUP.finditer(line)
    ]
    assert {"[41/--]", "[4.1-scheduling-domain/--]"} <= set(negatives), (
        "o §4(a) perdeu os exemplos negativos de dono da marca"
    )
    accepted = [tag for tag in negatives if _accepted(f"docs(conventions): exemplo {tag}")]
    assert not accepted, f"negativo (❌) que o hook aceita: {accepted}"


def test_every_example_in_the_hook_help_is_accepted_by_the_hook() -> None:
    """A ajuda sai em toda recusa: exemplo dela que o hook recusa ensina a forma
    errada justamente a quem acabou de errar."""
    starts = (*(f"{kind}(" for kind in ccm.ALLOWED_TYPES), "stage ")
    examples = [
        line.strip()
        for line in ccm._format_help().splitlines()
        if line.startswith(" " * 6)
        and not line.startswith(" " * 7)
        and line.strip().startswith(starts)
    ]
    assert examples, "a ajuda do hook perdeu os exemplos"
    refused = [
        example
        for example in examples
        if not _accepted(example.replace("N.M", "4.1").replace("<motivo>", "motivo"))
    ]
    assert not refused, f"exemplos da ajuda que o hook recusa: {refused}"


@pytest.mark.parametrize(
    "ending",
    ["/task-01]", "/task-01-fix]", "/task-13-extra]", "/--]", "#34/task-02]"],
)
def test_the_hook_help_shows_every_position_of_the_tag(ending: str) -> None:
    """Quem teve a marca recusada aprende a forma pela ajuda: sem exemplo de cada
    posição (e do dono de issue), a ajuda deixa de ensinar o `-fix`/`-extra`."""
    examples = [line.strip() for line in ccm._format_help().splitlines()]
    assert any(line.endswith(ending) for line in examples), ending

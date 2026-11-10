"""Unit de `scripts/check_technical_postexec.py` — marcadores e freeze da §7.

A checagem 2 (freeze da §7, CONVENTIONS §3.4) lê o histórico do git: os testes
dela montam um repositório real em `tmp_path`, com o commit reservado
`stage N.M: technical approved`, e rodam o script com o `cwd` lá dentro.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_technical_postexec.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_technical_postexec", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ctp = _load()

_REL = Path("docs/stages/1.2-ci/technical.md")
_APPROVED = "stage 1.2: technical approved"


def _technical(*, status: str = "done", plano: str = "plano", post: str = "nada ainda") -> str:
    return (
        f"---\nstatus: {status}\n---\n\n# Technical\n\n{plano}\n\n## 7. Pós-execução\n\n"
        f"{ctp.BEGIN_MARKER}\n{post}\n{ctp.END_MARKER}\n\nrodapé\n"
    )


def _git(cwd: Path, *args: str) -> str:
    cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert cp.returncode == 0, cp.stderr
    return cp.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repositório git com `develop` num commit inicial e o `cwd` apontado para ele."""
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(var, raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "develop")
    _git(root, "config", "user.name", "Teste")
    _git(root, "config", "user.email", "teste@example.com")
    _git(root, "config", "core.autocrlf", "false")
    _git(root, "commit", "-q", "--allow-empty", "-m", "inicial")
    monkeypatch.chdir(root)
    return root


def _commit_technical(root: Path, text: str, message: str) -> str:
    path = root / _REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", _REL.as_posix())
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _approve_on_stage_branch(root: Path, text: str) -> str:
    """O commit de aprovação numa branch de Stage que ainda não mergeou."""
    _git(root, "checkout", "-q", "-b", "feat/1-1-2-ci")
    return _commit_technical(root, text, _APPROVED)


# --- estrutura: marcadores e status ----------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("---\nstatus: done\n---\ncorpo\n", True),
        ("---\nstatus: draft\n---\ncorpo\n", False),
        ("sem frontmatter\nstatus: done\n", False),
        # `status: done` só no corpo, depois do fechamento do frontmatter, não conta.
        ("---\nstatus: draft\n---\nstatus: done\n", False),
    ],
    ids=["done", "draft", "sem-frontmatter", "done-so-no-corpo"],
)
def test_has_status_done_reads_only_the_frontmatter(text: str, *, expected: bool) -> None:
    assert ctp._has_status_done(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("sem marcadores\n", "1 BEGIN e 1 END, encontrei 0 BEGIN e 0 END"),
        (
            "{b}\n{b}\n{e}\n",
            "encontrei 2 BEGIN e 1 END",
        ),
        ("{e}\nmeio\n{b}\n", "marcador END (linha 1) deve vir depois do BEGIN (linha 3)"),
    ],
    ids=["ausentes", "begin-duplicado", "end-antes-do-begin"],
)
def test_invalid_markers_are_reported(tmp_path: Path, text: str, expected: str) -> None:
    path = tmp_path / "technical.md"
    path.write_text(text.format(b=ctp.BEGIN_MARKER, e=ctp.END_MARKER), encoding="utf-8")
    [error] = ctp.check_file(path)
    assert expected in error
    assert str(path) in error


def test_markers_return_their_line_indexes(tmp_path: Path) -> None:
    content = _technical()
    lines = content.splitlines()
    assert ctp._check_markers(content, tmp_path) == (
        lines.index(ctp.BEGIN_MARKER),
        lines.index(ctp.END_MARKER),
    )


def test_draft_needs_only_valid_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Com `status: draft` o histórico nem é consultado."""

    def _no_git(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("draft não consulta o git")

    monkeypatch.setattr(ctp.subprocess, "run", _no_git)
    path = tmp_path / "technical.md"
    path.write_text(_technical(status="draft"), encoding="utf-8")
    assert ctp.check_file(path) == []


# --- checagem 2: freeze da §7 enquanto a Stage não mergeou ------------------


def test_change_outside_section_7_during_execution_is_rejected(repo: Path) -> None:
    sha = _approve_on_stage_branch(repo, _technical())
    (repo / _REL).write_text(_technical(plano="plano reescrito"), encoding="utf-8")

    errors = ctp.check_file(_REL)

    assert errors, "mudança fora da §7 com a Stage em execução precisa reprovar"
    assert "há mudanças fora dos marcadores" in errors[0]
    assert sha[:8] in errors[0]
    assert errors[1].startswith("  replace: baseline[")


def test_change_inside_section_7_during_execution_is_allowed(repo: Path) -> None:
    _approve_on_stage_branch(repo, _technical())
    (repo / _REL).write_text(_technical(post="[decision] x\n[finding] y"), encoding="utf-8")

    assert ctp.check_file(_REL) == []


def test_absolute_path_is_made_repo_relative_for_git_show(repo: Path) -> None:
    """Na descoberta o caminho é absoluto; o `git show <sha>:<path>` exige relativo."""
    _approve_on_stage_branch(repo, _technical())
    absolute = repo / _REL
    absolute.write_text(_technical(plano="outro plano"), encoding="utf-8")

    assert ctp._repo_relative_posix(absolute) == _REL.as_posix()
    assert ctp.check_file(absolute) != []


def test_path_outside_the_repo_stays_as_is(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "fora" / "technical.md"
    assert ctp._repo_relative_posix(outside) == outside.as_posix()


def test_non_ascii_baseline_is_decoded_as_utf8(repo: Path) -> None:
    """Acento no plano não vira diff espúrio (mojibake do locale no Windows)."""
    _approve_on_stage_branch(repo, _technical(plano="Decisão — pós-execução"))
    assert ctp.check_file(_REL) == []


def test_merged_stage_is_no_longer_frozen(repo: Path) -> None:
    """Aprovação ancestral de `develop`: a §7 é doc de referência mutável."""
    _commit_technical(repo, _technical(), _APPROVED)
    (repo / _REL).write_text(_technical(plano="revisado depois do merge"), encoding="utf-8")

    assert ctp.check_file(_REL) == []


def test_no_integration_ref_fails_open(repo: Path) -> None:
    """Sem `develop`/`main` resolvível (clone raso), não dá para afirmar execução."""
    _git(repo, "branch", "-m", "develop", "trabalho")
    sha = _commit_technical(repo, _technical(), _APPROVED)
    (repo / _REL).write_text(_technical(plano="mudou"), encoding="utf-8")

    assert ctp._stage_is_merged(sha) is True
    assert ctp.check_file(_REL) == []


def test_without_approval_commit_there_is_no_baseline(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feat/1-1-2-ci")
    _commit_technical(repo, _technical(), "docs(ci): rascunho do technical")
    (repo / _REL).write_text(_technical(plano="mudou"), encoding="utf-8")

    assert ctp._approved_commit_for(_REL) is None
    assert ctp.check_file(_REL) == []


def test_approval_of_another_stage_is_not_the_baseline(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feat/1-1-2-ci")
    _commit_technical(repo, _technical(), "stage 1.3: technical approved")

    assert ctp._approved_commit_for(_REL) is None


def test_baseline_before_the_section_7_contract_is_accepted(repo: Path) -> None:
    """Aprovada antes dos marcadores existirem: sem janela no baseline, não compara."""
    _approve_on_stage_branch(repo, "---\nstatus: done\n---\n\n# Technical antigo\n")
    (repo / _REL).write_text(_technical(plano="migrado"), encoding="utf-8")

    assert ctp.check_file(_REL) == []


def test_unreadable_baseline_is_an_error(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sha = _approve_on_stage_branch(repo, _technical())
    monkeypatch.setattr(ctp, "_git_show", lambda _sha, _path: None)

    [error] = ctp.check_file(_REL)

    assert f"baseline do commit {sha[:8]}" in error


def test_git_show_of_a_missing_path_is_none(repo: Path) -> None:
    sha = _approve_on_stage_branch(repo, _technical())
    assert ctp._git_show(sha, Path("docs/nao-existe.md")) is None


def test_path_outside_stages_has_no_approval_commit(repo: Path) -> None:
    assert ctp._approved_commit_for(Path("docs/roadmap.md")) is None


def test_outside_a_git_repo_there_is_no_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git log` falhando (fora de repositório) pula a checagem 2 em vez de quebrar."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert ctp._approved_commit_for(_REL) is None


def test_repo_relative_falls_back_outside_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    absolute = tmp_path / _REL
    assert ctp._repo_relative_posix(absolute) == absolute.as_posix()


# --- main ------------------------------------------------------------------


def test_main_without_targets_is_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ctp.main(["--root", str(tmp_path)]) == 0
    assert "Nenhum technical.md encontrado" in capsys.readouterr().err


def test_main_discovers_and_validates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    for slug in ("1.1-a", "1.2-b"):
        path = tmp_path / "docs" / "stages" / slug / "technical.md"
        path.parent.mkdir(parents=True)
        path.write_text(_technical(status="draft"), encoding="utf-8")

    assert ctp.main(["--root", str(tmp_path)]) == 0
    assert "OK — 2 arquivo(s) validado(s)." in capsys.readouterr().out


def test_main_reports_every_error_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "technical.md"
    broken.write_text("sem marcadores\n", encoding="utf-8")
    missing = tmp_path / "nao-existe.md"

    assert ctp.main([str(broken), str(missing)]) == 1

    err = capsys.readouterr().err
    assert "marcadores de §7 inválidos" in err
    assert f"{missing}: arquivo não encontrado." in err
    assert "2 erro(s) em 2 arquivo(s)." in err


# --- fronteira da janela (auditoria de testes da #91) ----------------------


def _with_section_7(post_lines: list[str], after_end: list[str]) -> str:
    return (
        "---\nstatus: done\n---\n\n# Technical\n\nplano\n\n## 7. Pós-execução\n\n"
        + "\n".join([ctp.BEGIN_MARKER, *post_lines, ctp.END_MARKER, *after_end])
        + "\n"
    )


def test_content_moved_past_the_end_marker_is_rejected(repo: Path) -> None:
    """Um lado dentro da janela não basta: a linha que sai da §7 para fora reprova.

    O `delete` da linha cai dentro das duas janelas, mas o `insert` depois do END
    está dentro da janela da baseline e fora da atual — os dois lados precisam
    estar dentro.
    """
    _approve_on_stage_branch(repo, _with_section_7(["nada ainda"], []))
    (repo / _REL).write_text(_with_section_7([], ["nada ainda"]), encoding="utf-8")

    assert ctp.check_file(_REL) != []


def test_line_appended_at_the_end_of_section_7_is_allowed(repo: Path) -> None:
    _approve_on_stage_branch(repo, _with_section_7(["a"], ["", "rodapé"]))
    (repo / _REL).write_text(_with_section_7(["a", "b"], ["", "rodapé"]), encoding="utf-8")

    assert ctp.check_file(_REL) == []


def test_line_added_right_after_the_end_marker_is_rejected(repo: Path) -> None:
    _approve_on_stage_branch(repo, _with_section_7(["a"], ["", "rodapé"]))
    (repo / _REL).write_text(_with_section_7(["a"], ["fora", "", "rodapé"]), encoding="utf-8")

    assert ctp.check_file(_REL) != []


# --- checagem 1b: vocabulário de tags da §7 (issue #65, port da FF#157) ---


def _tagged_technical(
    tmp_path: Path, section: str, *, status: str = "draft", outside: str = ""
) -> Path:
    path = tmp_path / "technical.md"
    path.write_text(
        f"---\nstatus: {status}\n---\n\n# Technical\n{outside}\n"
        f"## 7. Execução\n<!-- BEGIN: post-execution -->\n{section}\n"
        "<!-- END: post-execution -->\n",
        encoding="utf-8",
    )
    return path


def _tag_entry(tag: str, sep: str = "—") -> str:
    return f"### 2026-10-17 {sep} [{tag}] task-01 — escopo — Claude\n**Contexto:** x\n"


@pytest.mark.parametrize(
    "tag", ["decision", "decision:E", "decision:C", "finding", "deviation", "measurement"]
)
def test_vocabulary_tags_pass(tmp_path: Path, tag: str) -> None:
    assert ctp.check_file(_tagged_technical(tmp_path, _tag_entry(tag))) == []


@pytest.mark.parametrize(
    "tag", ["nota", "fix", "P", "decision:P", "Measurement", "measurements", "", "deviation "]
)
def test_tag_outside_vocabulary_is_refused(tmp_path: Path, tag: str) -> None:
    errors = ctp.check_file(_tagged_technical(tmp_path, _tag_entry("finding") + _tag_entry(tag)))
    assert len(errors) == 1
    assert f"`[{tag}]`" in errors[0]
    assert "CONVENTIONS §3.4" in errors[0]


def test_error_points_to_the_offending_line(tmp_path: Path) -> None:
    path = _tagged_technical(tmp_path, _tag_entry("nota"))
    line = path.read_text(encoding="utf-8").splitlines().index(_tag_entry("nota").splitlines()[0])
    assert ctp.check_file(path)[0].startswith(f"{path}:{line + 1}: ")


@pytest.mark.parametrize("sep", ["\u2013", "-"])
def test_other_dash_separators_are_checked(tmp_path: Path, sep: str) -> None:
    assert len(ctp.check_file(_tagged_technical(tmp_path, _tag_entry("nota", sep)))) == 1


def test_every_offending_entry_is_reported(tmp_path: Path) -> None:
    section = _tag_entry("nota") + _tag_entry("measurement") + _tag_entry("fix")
    errors = ctp.check_file(_tagged_technical(tmp_path, section))
    assert [e.split("`[")[1].split("]`")[0] for e in errors] == ["nota", "fix"]


def test_refused_also_when_status_done(tmp_path: Path) -> None:
    # Sem commit `stage N.M: technical approved` (caminho fora de docs/stages),
    # a checagem de diff é pulada; a de tag continua valendo.
    assert len(ctp.check_file(_tagged_technical(tmp_path, _tag_entry("nota"), status="done"))) == 1


def test_header_outside_the_window_is_not_checked(tmp_path: Path) -> None:
    assert ctp.check_file(_tagged_technical(tmp_path, "", outside=_tag_entry("nota"))) == []


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_header_inside_a_code_fence_is_not_checked(tmp_path: Path, fence: str) -> None:
    section = f"{fence}markdown\n{_tag_entry('nota')}{fence}\n" + _tag_entry("nota")
    # só a entrada depois do fence conta: o fence fechou e voltou a valer
    assert len(ctp.check_file(_tagged_technical(tmp_path, section))) == 1


def test_untagged_entry_and_template_placeholder_pass(tmp_path: Path) -> None:
    section = (
        "### 2026-10-17 — Checkpoint C — disposições — Claude\n"
        "### YYYY-MM-DD — [tag] <Task NN ou escopo> — <Autor>\n"
        "#### Saída com a mutação [nota]\n"
        "#### Execução — 2026-06-29 (todas as Tasks)\n"
        "## [nota] título de nível 2 não é entrada\n"
    )
    assert ctp.check_file(_tagged_technical(tmp_path, section)) == []


@pytest.mark.parametrize(
    "header",
    [
        "#### 2026-10-17 — [nota] entrada de nível 4",
        "#### [nota] formato anterior ao template (1.2, 2.1)",
        "### Task 03 — `[nota]` formato anterior ao template (2.4)",
        "### [nota] sem data",
    ],
)
def test_entry_header_outside_the_template_format_is_checked(tmp_path: Path, header: str) -> None:
    errors = ctp.check_file(_tagged_technical(tmp_path, f"{header}\n**Contexto:** x\n"))
    assert len(errors) == 1
    assert "`[nota]`" in errors[0]


@pytest.mark.parametrize(
    "header",
    [
        "#### [deviation] formato anterior ao template",
        "### Task 06 — `[finding]` `uv sync` remove o extra `.[dev]`",
        "#### [finding] DuckDB devolve `datetime64[us, UTC]`",
    ],
)
def test_legacy_header_with_vocabulary_tag_passes(tmp_path: Path, header: str) -> None:
    # Só a primeira marca do título é a tag; colchetes no resto do título não contam.
    assert ctp.check_file(_tagged_technical(tmp_path, f"{header}\n")) == []


def test_main_exit_code_follows_the_tags(tmp_path: Path) -> None:
    good = _tagged_technical(tmp_path, _tag_entry("measurement"))
    assert ctp.main([str(good)]) == 0
    bad = _tagged_technical(tmp_path, _tag_entry("nota"))
    assert ctp.main([str(bad)]) == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("sem marcadores\n", "encontrei 0 BEGIN e 0 END"),
        (
            "<!-- BEGIN: post-execution -->\n<!-- BEGIN: post-execution -->\n"
            "<!-- END: post-execution -->\n",
            "encontrei 2 BEGIN e 1 END",
        ),
        ("<!-- END: post-execution -->\n<!-- BEGIN: post-execution -->\n", "deve vir depois"),
    ],
)
def test_invalid_markers_are_refused(tmp_path: Path, body: str, expected: str) -> None:
    path = tmp_path / "technical.md"
    path.write_text(f"---\nstatus: draft\n---\n\n{body}", encoding="utf-8")
    errors = ctp.check_file(path)
    assert len(errors) == 1
    assert expected in errors[0]


def test_file_without_frontmatter_is_not_done(tmp_path: Path) -> None:
    assert not ctp._has_status_done("# Technical\nstatus: done\n")


def test_main_reports_missing_file(tmp_path: Path) -> None:
    assert ctp.main([str(tmp_path / "ausente.md")]) == 1


def test_main_without_targets_passes(tmp_path: Path) -> None:
    assert ctp.main(["--root", str(tmp_path)]) == 0

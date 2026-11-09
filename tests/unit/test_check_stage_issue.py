"""Unit de `scripts/check_stage_issue.py` — toda Stage tem issue no GitHub."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_stage_issue.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_stage_issue", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


csi = _load()

# Exit 2: alvo explícito inexistente (erro de uso, não Stage inválida).
_EXIT_USAGE = 2
_STAGES = 2


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def _raising(exc: BaseException) -> Callable[..., Any]:
    def fake(*_args: object, **_kwargs: object) -> object:
        raise exc

    return fake


def _fake_gh(existing: set[int], *, auth_ok: bool = True) -> Callable[..., Any]:
    """Fake de `gh`: `auth status` conforme `auth_ok`; `issue view` acha `existing`."""

    def fake(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[:3] == ["gh", "auth", "status"]:
            return _completed(0 if auth_ok else 1)
        assert cmd[:3] == ["gh", "issue", "view"]
        number = int(cmd[3])
        if number in existing:
            return _completed(0, json.dumps({"number": number, "state": "OPEN"}))
        return _completed(1)

    return fake


def _technical(root: Path, slug: str, frontmatter: str) -> Path:
    path = root / "docs" / "stages" / slug / "technical.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n# corpo\n", encoding="utf-8")
    return path


# --- gh_available -----------------------------------------------------------


def test_gh_available_false_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csi.shutil, "which", lambda _name: None)
    monkeypatch.setattr(csi.subprocess, "run", _raising(AssertionError("não deve rodar")))
    assert csi.gh_available() is False


@pytest.mark.parametrize(("rc", "expected"), [(0, True), (1, False)])
def test_gh_available_follows_auth_status(
    monkeypatch: pytest.MonkeyPatch, rc: int, expected: bool
) -> None:
    monkeypatch.setattr(csi.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(csi.subprocess, "run", lambda *_a, **_k: _completed(rc))
    assert csi.gh_available() is expected


@pytest.mark.parametrize(
    "exc",
    [subprocess.TimeoutExpired(cmd="gh", timeout=5), OSError("boom")],
    ids=["timeout", "oserror"],
)
def test_gh_available_false_on_subprocess_error(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    monkeypatch.setattr(csi.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(csi.subprocess, "run", _raising(exc))
    assert csi.gh_available() is False


# --- issue_exists -----------------------------------------------------------


def test_issue_exists_true_when_number_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh({42}))
    assert csi.issue_exists(42) is True


def test_issue_exists_false_on_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh(set()))
    assert csi.issue_exists(42) is False


def test_issue_exists_false_when_number_differs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resposta de outra issue (ex.: redirect de transferência) não conta."""
    monkeypatch.setattr(
        csi.subprocess, "run", lambda *_a, **_k: _completed(0, json.dumps({"number": 7}))
    )
    assert csi.issue_exists(42) is False


@pytest.mark.parametrize(
    "fake",
    [
        lambda *_a, **_k: _completed(0, "não é json"),
        _raising(subprocess.TimeoutExpired(cmd="gh", timeout=15)),
        _raising(OSError("boom")),
    ],
    ids=["json-invalido", "timeout", "oserror"],
)
def test_issue_exists_false_on_errors(
    monkeypatch: pytest.MonkeyPatch, fake: Callable[..., Any]
) -> None:
    monkeypatch.setattr(csi.subprocess, "run", fake)
    assert csi.issue_exists(42) is False


# --- parse_frontmatter ------------------------------------------------------


def test_parse_frontmatter_flat_fields_skip_list_items(tmp_path: Path) -> None:
    """Pares key: value viram dict; itens de lista e linhas sem `:` são ignorados."""
    path = _technical(tmp_path, "1.1-x", "issue_id: 12\nstatus: done\ndeps:\n  - a: b\nsolto")
    assert csi.parse_frontmatter(path) == {"issue_id": "12", "status": "done", "deps": ""}


def test_parse_frontmatter_without_block_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "technical.md"
    path.write_text("# sem frontmatter\nissue_id: 3\n", encoding="utf-8")
    assert csi.parse_frontmatter(path) == {}


# --- check_one --------------------------------------------------------------


def test_check_one_missing_issue_id(tmp_path: Path) -> None:
    path = _technical(tmp_path, "1.1-x", "status: draft")
    assert csi.check_one(path) == (False, "campo `issue_id` ausente no frontmatter")


def test_check_one_non_integer_issue_id(tmp_path: Path) -> None:
    path = _technical(tmp_path, "1.1-x", "issue_id: abc")
    ok, msg = csi.check_one(path)
    assert ok is False and "`issue_id: 'abc'` não é inteiro" in msg


def test_check_one_issue_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh(set()))
    path = _technical(tmp_path, "1.1-x", "issue_id: 9")
    assert csi.check_one(path) == (False, "issue #9 não encontrada via `gh issue view`")


def test_check_one_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh({9}))
    path = _technical(tmp_path, "1.1-x", "issue_id: 9")
    assert csi.check_one(path) == (True, "issue #9 OK")


# --- discover_technicals ----------------------------------------------------


def test_discover_explicit_target(tmp_path: Path) -> None:
    path = _technical(tmp_path, "1.1-x", "issue_id: 1")
    assert csi.discover_technicals(path) == [path]


def test_discover_missing_target_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        csi.discover_technicals(tmp_path / "nao-existe.md")
    assert excinfo.value.code == _EXIT_USAGE
    assert "arquivo não existe" in capsys.readouterr().err


def test_discover_without_stages_dir_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert csi.discover_technicals(None) == []


def test_discover_globs_stages_sorted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _technical(tmp_path, "2.1-b", "issue_id: 2")
    _technical(tmp_path, "1.1-a", "issue_id: 1")
    (tmp_path / "docs" / "stages" / "3.1-sem-technical").mkdir()
    monkeypatch.chdir(tmp_path)
    assert csi.discover_technicals(None) == [
        Path("docs/stages/1.1-a/technical.md"),
        Path("docs/stages/2.1-b/technical.md"),
    ]


# --- main -------------------------------------------------------------------


def _argv(monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["check_stage_issue.py", *args])


def test_main_no_stages_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _argv(monkeypatch)
    monkeypatch.setattr(csi.subprocess, "run", _raising(AssertionError("não deve rodar")))
    assert csi.main() == 0
    assert "nenhuma Stage encontrada" in capsys.readouterr().out


def test_main_without_gh_warns_and_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Best-effort: sem `gh` autenticado, WARN e exit 0 — mesmo com Stage inválida."""
    _technical(tmp_path, "1.1-x", "status: draft")
    monkeypatch.chdir(tmp_path)
    _argv(monkeypatch)
    monkeypatch.setattr(csi.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh(set(), auth_ok=False))
    assert csi.main() == 0
    assert "WARN" in capsys.readouterr().err


def test_main_all_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _technical(tmp_path, "1.1-a", "issue_id: 1")
    _technical(tmp_path, "1.2-b", "issue_id: 2")
    monkeypatch.chdir(tmp_path)
    _argv(monkeypatch)
    monkeypatch.setattr(csi.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh({1, 2}))
    assert csi.main() == 0
    out = capsys.readouterr().out
    assert "OK — 2 stage(s) checada(s)" in out
    assert out.count("OK    ") == _STAGES


def test_main_reports_failures_and_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Uma Stage válida e duas inválidas: exit 1, só as inválidas no stderr."""
    _technical(tmp_path, "1.1-a", "issue_id: 1")
    _technical(tmp_path, "1.2-b", "issue_id: 99")
    _technical(tmp_path, "1.3-c", "status: draft")
    monkeypatch.chdir(tmp_path)
    _argv(monkeypatch)
    monkeypatch.setattr(csi.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh({1}))
    assert csi.main() == 1
    captured = capsys.readouterr()
    assert captured.out.count("FALHA") == _STAGES
    assert "FALHA — 2 Stage(s) sem issue válida" in captured.err
    assert "issue #99 não encontrada" in captured.err
    assert "campo `issue_id` ausente" in captured.err
    assert "1.1-a" not in captured.err


def test_main_explicit_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Com alvo explícito só ele é checado, ignorando o resto de docs/stages."""
    target = _technical(tmp_path, "1.1-a", "issue_id: 1")
    _technical(tmp_path, "1.2-b", "issue_id: 99")
    monkeypatch.chdir(tmp_path)
    _argv(monkeypatch, str(target))
    monkeypatch.setattr(csi.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(csi.subprocess, "run", _fake_gh({1}))
    assert csi.main() == 0
    assert "OK — 1 stage(s) checada(s)" in capsys.readouterr().out


def test_issue_exists_false_when_gh_fails_even_with_matching_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O código de saída decide antes do JSON: `gh` que falha não confirma a issue."""
    monkeypatch.setattr(
        csi.subprocess, "run", lambda *_a, **_k: _completed(1, json.dumps({"number": 42}))
    )
    assert csi.issue_exists(42) is False

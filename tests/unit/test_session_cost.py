"""Unit de `scripts/session_cost.py` — custo medido do transcript."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "session_cost.py"
_OUT = 10
_CACHE_READ = 100
_HUMAN_WAIT_S = 30.0


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("session_cost", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sc = _load()


def _assistant(req: str, ts: str, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    usage = {"input_tokens": 1, "output_tokens": _OUT, "cache_read_input_tokens": _CACHE_READ}
    return {
        "type": "assistant",
        "requestId": req,
        "timestamp": ts,
        "message": {"model": "m", "usage": usage, "content": blocks or []},
    }


def _human(ts: str, text: str = "oi") -> dict[str, Any]:
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def _write(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return path


def test_streaming_blocks_of_one_request_count_once(tmp_path: Path) -> None:
    # o transcript repete a mesma `usage` em cada bloco de streaming da requisição
    entries = [_assistant("r1", "2026-01-01T00:00:00Z")] * 3 + [
        _assistant("r2", "2026-01-01T00:00:05Z")
    ]
    cost = sc.session_cost(_write(tmp_path / "s.jsonl", entries))
    assert cost.requests == len({"r1", "r2"})
    assert cost.tokens["output_tokens"] == 2 * _OUT


def test_human_time_turns_and_questions(tmp_path: Path) -> None:
    ask = [{"type": "tool_use", "name": "AskUserQuestion"}]
    entries = [
        _human("2026-01-01T00:00:00Z", "tarefa"),
        _assistant("r1", "2026-01-01T00:01:00Z", ask),
        _human("2026-01-01T00:01:30Z", "resposta"),
        {
            "type": "user",
            "timestamp": "2026-01-01T00:02:00Z",
            "message": {"content": [{"type": "tool_result"}]},
        },
        _human("2026-01-01T00:02:10Z", "<command-name>/cost</command-name>"),
    ]
    cost = sc.session_cost(_write(tmp_path / "s.jsonl", entries))
    assert cost.human_turns == len(["tarefa", "resposta"])
    assert cost.human_s == _HUMAN_WAIT_S
    assert cost.ask_user_question == 1


def test_subagent_tokens_are_added(tmp_path: Path) -> None:
    main = _write(tmp_path / "s.jsonl", [_assistant("r1", "2026-01-01T00:00:00Z")])
    (tmp_path / "s" / "subagents").mkdir(parents=True)
    _write(tmp_path / "s" / "subagents" / "a.jsonl", [_assistant("x1", "2026-01-01T00:00:01Z")])
    cost = sc.session_cost(main)
    assert cost.requests == len(["r1", "x1"])
    assert cost.tokens["cache_read_input_tokens"] == 2 * _CACHE_READ


def test_resolve_accepts_an_existing_path(tmp_path: Path) -> None:
    path = _write(tmp_path / "s.jsonl", [])
    assert sc.resolve(str(path)) == path


def test_resolve_finds_session_id_under_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um id de sessão é procurado em `PROJECTS/*/<id>.jsonl`."""
    (tmp_path / "proj").mkdir()
    found = _write(tmp_path / "proj" / "abc.jsonl", [])
    monkeypatch.setattr(sc, "PROJECTS", tmp_path)
    assert sc.resolve("abc") == found


@pytest.mark.parametrize("copies", [0, 2])
def test_resolve_refuses_missing_or_ambiguous_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, copies: int
) -> None:
    """Nenhum ou mais de um transcript com o id: aborta em vez de escolher."""
    for i in range(copies):
        (tmp_path / f"p{i}").mkdir()
        _write(tmp_path / f"p{i}" / "abc.jsonl", [])
    monkeypatch.setattr(sc, "PROJECTS", tmp_path)
    with pytest.raises(SystemExit, match=r"não encontrada \(ou ambígua\)"):
        sc.resolve("abc")


def test_meta_and_sidechain_user_entries_are_not_human_turns(tmp_path: Path) -> None:
    """Lembrete do sistema (`isMeta`) e mensagem de subagente não são o humano."""
    entries = [
        {**_human("2026-01-01T00:00:00Z"), "isMeta": True},
        {**_human("2026-01-01T00:00:01Z"), "isSidechain": True},
        {"type": "user", "message": {"content": 42}},  # conteúdo nem str nem lista
    ]
    cost = sc.session_cost(_write(tmp_path / "s.jsonl", entries))
    assert cost.human_turns == 0
    assert cost.wall_clock_s == 1.0


def test_entries_without_timestamp_or_ids_and_bad_lines(tmp_path: Path) -> None:
    """Sem timestamp: parede zero; sem `requestId`/`uuid`: a 2ª conta como repetida."""
    usage = {"output_tokens": _OUT}
    no_id = {"type": "assistant", "message": {"model": "m", "usage": usage, "content": ["txt"]}}
    path = tmp_path / "s.jsonl"
    path.write_text(
        "\n".join([json.dumps(no_id), "{linha truncada", json.dumps(no_id)]), encoding="utf-8"
    )
    cost = sc.session_cost(path)
    assert cost.wall_clock_s == 0.0
    assert cost.requests == 1
    assert cost.tokens["output_tokens"] == _OUT


def test_main_prints_one_line_per_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(
        tmp_path / "s.jsonl",
        [_assistant("r1", "2026-01-01T00:00:00Z"), _assistant("r2", "2026-01-01T00:02:00Z")],
    )
    assert sc.main([str(path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"{path}: 2 req | in 2 | cache_w 0 | cache_r 200 | out 20 | parede 2.0")
    assert "AskUserQuestion 0 | m" in out


def test_main_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path / "s.jsonl", [_assistant("r1", "2026-01-01T00:00:00Z")])
    assert sc.main([str(path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[str(path)]["requests"] == 1
    assert data[str(path)]["models"] == ["m"]

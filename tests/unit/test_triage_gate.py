"""Unit do hook `.claude/hooks/triage_gate.py`.

Casos reais: as mensagens de fim de turno vêm das sessões da Stage 5.4 e da #78
(forks "a ratificar" que chegaram ao humano sendo convenção metodológica).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "triage_gate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("triage_gate", _HOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass resolve o módulo pelo nome
    spec.loader.exec_module(module)
    return module


tg = _load()


def _ask(*headers: str) -> dict[str, Any]:
    questions = [{"question": f"q{i}?", "header": h, "options": []} for i, h in enumerate(headers)]
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": questions},
    }


def _stop(message: str, *, active: bool = False, event: str = "Stop") -> dict[str, Any]:
    return {"hook_event_name": event, "stop_hook_active": active, "last_assistant_message": message}


def test_ask_with_all_p_headers_passes() -> None:
    assert tg.decide(_ask("P:Escopo", "P:Prazo")) is None


def test_ask_with_unclassified_header_is_denied() -> None:
    out = tg.decide(_ask("P:Escopo", "B2 — Horizon"))
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "q1?" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_other_tools_are_ignored() -> None:
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}}
    assert tg.decide(payload) is None


@pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
def test_stop_blocks_on_pending_ratification(event: str) -> None:
    msg = '2. **8 forks para você ratificar** (marcados "a ratificar — B-…" no §10): B-CRPS'
    out = tg.decide(_stop(msg, event=event))
    assert out is not None and out["decision"] == "block"


def test_stop_blocks_on_b_label_offered_as_question() -> None:
    assert tg.decide(_stop('## B2 — Gate H1 (que teste único decide "calibrado"?)')) is not None


def test_stop_passes_when_fork_is_tagged_p() -> None:
    assert tg.decide(_stop("**B1 [P]** — a busca de hiperparâmetros cabe nesta Stage?")) is None


def test_stop_passes_on_resolved_fork_narration() -> None:
    msg = (
        "Sobre B4: sem limite de tarefas, o varredor Optuna permanece na Stage.\nSegui com **B1**."
    )
    assert tg.decide(_stop(msg)) is None


def test_stop_passes_on_prose_about_ratification() -> None:
    # falso positivo real (sessão de criação do hook): narrar o caso da #78
    msg = "- O agente citou Eq./página e devolveu 11 convenções para você ratificar (B-CRPS)."
    assert tg.decide(_stop(msg)) is None


def test_stop_passes_when_line_declares_the_forks_closed() -> None:
    # falso positivo real (sessão que fechou a #78): o marcador citado como nome
    msg = '- **As 11 bifurcações "a ratificar" estão fechadas**, com registro em §10.1 do doc.'
    assert tg.decide(_stop(msg)) is None


@pytest.mark.parametrize(
    "msg",
    [
        "B-HORIZON (a ratificar): ainda não decidido",
        "3 forks a ratificar, a ser resolvido por você",
        "(a ratificar — B-GATE) será tratado no próximo PR",
        'As bifurcações "a ratificar" não estão fechadas',
    ],
)
def test_stop_still_blocks_when_closing_word_is_negated_or_future(msg: str) -> None:
    # a palavra de fechamento sozinha não basta: pendência negada/futura segue bloqueando
    out = tg.decide(_stop(msg))
    assert out is not None and out["decision"] == "block"


def test_stop_never_blocks_twice() -> None:
    assert tg.decide(_stop("B-GATE a ratificar", active=True)) is None


# Casos do restaurant-hub (issue #56): forks aqui aparecem como lista de opções com
# "(Recomendada)" (PROMPT-step §2) ou "Fork <tema>"; F1/F2 são findings de auditoria.
@pytest.mark.parametrize(
    "msg",
    [
        "**Fork RBAC** — o RH pode editar a escala ou só consultar?",
        "1. Bloquear a alocação (Recomendada) — ou só avisar o gerente?",
        "Qual default para o descanso entre jornadas? A) 11h (Recomendado) B) configurável vazio",
    ],
)
def test_stop_blocks_on_local_fork_shapes(msg: str) -> None:
    out = tg.decide(_stop(msg))
    assert out is not None and out["decision"] == "block"


@pytest.mark.parametrize(
    "msg",
    [
        "**F2** — o mapper de result duplica o DTO? Corrigido em `dtos/results.py`.",
        "Segui a opção (Recomendada) do ADR 2.4.0004 para o hash de senha.",
        "**Fork RBAC [P]** — o RH pode editar a escala ou só consultar?",
    ],
)
def test_stop_passes_on_findings_and_tagged_or_settled_recommendations(msg: str) -> None:
    assert tg.decide(_stop(msg)) is None


# --- `main()`: stdin em bytes, saída JSON só quando bloqueia (issue #91) ---


def _stdin(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> None:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))


def test_main_prints_the_decision_when_it_blocks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _ask("Escopo")
    expected = tg.decide(payload)
    assert expected is not None, "o caso precisa bloquear para o teste valer"
    _stdin(monkeypatch, json.dumps(payload).encode("utf-8"))

    assert tg.main() == 0
    assert json.loads(capsys.readouterr().out) == expected


@pytest.mark.parametrize(
    "raw",
    [json.dumps(_ask("P: escopo")).encode("utf-8"), b"nao e json", b"\xff\xfe"],
    ids=["permitido", "json-invalido", "utf8-invalido"],
)
def test_main_is_silent_when_it_does_not_block(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], raw: bytes
) -> None:
    _stdin(monkeypatch, raw)
    assert tg.main() == 0
    assert capsys.readouterr().out == ""

"""Invariantes do workflow de CI que nenhum outro gate protege.

Por que este teste existe (Stage 1.2, ADR 1.2.0001): o gate `make check` valida
o *código*, mas nada no repositório valida o *workflow que roda o gate*. A
Stage 1.2 descobriu que o clone raso default do `actions/checkout`
(`fetch-depth: 1`) fazia a checagem 2 do `scripts/check_technical_postexec.py`
(freeze da §7 — CONVENTIONS §3.4) se pular em silêncio no runner: verde por não
ter olhado. A correção é uma única linha (`fetch-depth: 0`) — e, sem este teste,
apagá-la deixaria `make check` inteiro verde, ressuscitando o bug sem nenhum
sinal. Um gate protegido só por prosa é exatamente o defeito que a Stage 1.2
cataloga.

Escopo deliberadamente estreito, em duas classes:

1. **Invariantes cuja quebra é silenciosa** — o caso original, `fetch-depth: 0`.
2. **Requisitos de ambiente dos quais o veredito do gate depende** (Stage 2.3):
   o `make check` passou a exigir Postgres real, e o job precisa servi-lo. A
   quebra aqui não é silenciosa — o CI fica vermelho —, mas o teste antecipa o
   diagnóstico para o `make check` local, em vez de deixá-lo para um run vermelho
   depois do push, onde a causa ("faltou o service") é bem menos óbvia que o
   sintoma ("os testes de integração falharam").

Não testar aqui estilo, nomes de step ou coisas que qualquer leitura do diff
pega.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

# Cadeia real do target `check` (Makefile). O step do CI roda literalmente
# `make check` — invariante I3 do concept da Stage 1.2: política específica de CI
# viaja por `env:`, nunca por argumento na linha de comando, senão o argumento de
# transitividade do runbook `validate-ci-gate.md` deixa de valer.
GATE_COMMAND = "make check"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    """O `ci.yml` parseado."""
    content = CI_WORKFLOW.read_text(encoding="utf-8")
    parsed: dict[str, Any] = yaml.safe_load(content)
    return parsed


@pytest.fixture(scope="module")
def gate_job(workflow: dict[str, Any]) -> dict[str, Any]:
    """O job que roda o gate (`make check`)."""
    job: dict[str, Any] = workflow["jobs"]["lint-and-test"]
    return job


def _checkout_steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        step
        for step in job["steps"]
        if isinstance(step.get("uses"), str) and step["uses"].startswith("actions/checkout@")
    ]


@pytest.mark.unit
def test_gate_job_checks_out_full_history(gate_job: dict[str, Any]) -> None:
    """O checkout do job de gate traz o histórico completo.

    Sem `fetch-depth: 0` o runner não enxerga o commit-baseline
    `stage N.M: technical approved` nem a ref `origin/develop`, e a checagem 2 do
    `check_technical_postexec.py` devolve verde sem ter validado nada — na única
    janela em que ela protege (Stage `done` e ainda não mergeada = todo PR de
    Stage). Provado por par A/B de runs reais na Stage 1.2; ver
    `docs/stages/1.2-ci/technical.md` §7.
    """
    checkouts = _checkout_steps(gate_job)
    assert checkouts, "job de gate não faz checkout — o `make check` rodaria sobre o quê?"

    for step in checkouts:
        with_block = step.get("with") or {}
        assert with_block.get("fetch-depth") == 0, (
            "o checkout do job de gate precisa de `fetch-depth: 0`. Com o clone raso "
            "default (fetch-depth: 1), a checagem 2 do check_technical_postexec.py "
            "(freeze da §7) se pula EM SILÊNCIO no runner e o CI fica verde sem ter "
            "olhado. Ver ADR 1.2.0001."
        )


@pytest.mark.unit
def test_gate_step_runs_make_check_literally(gate_job: dict[str, Any]) -> None:
    """O step do gate roda `make check` sem argumentos extras (invariante I3).

    O runbook `validate-ci-gate.md` prova classe a classe **localmente** e conclui
    que o runner rejeita o mesmo, porque o step roda *literalmente* `make check`.
    Um argumento extra na linha de comando quebra essa transitividade em silêncio:
    o runbook seguiria afirmando o que não vale mais.
    """
    run_commands = [step["run"].strip() for step in gate_job["steps"] if "run" in step]
    assert GATE_COMMAND in run_commands, (
        f"o job de gate precisa rodar exatamente `{GATE_COMMAND}` "
        f"(sem argumentos extras — I3). Comandos encontrados: {run_commands}"
    )


# ---------------------------------------------------------------------------
# Stage 2.3 — o gate passou a exigir Postgres real (ADR 2.3.0001).
#
# Os testes de integração não têm caminho de skip: sem banco eles falham alto.
# Isso torna o service do Postgres um REQUISITO do veredito do gate, e não uma
# conveniência — daí ele ser asserido aqui, junto do `fetch-depth: 0`.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gate_job_declara_service_de_postgres(gate_job: dict[str, Any]) -> None:
    """Sem o service, `make check` no runner não tem banco contra o que rodar.

    As duas saídas possíveis sem ele seriam CI permanentemente vermelho ou testes
    que se auto-pulam — e a segunda é exatamente o falso-verde que a Stage 1.2
    consertou ("verde por não ter olhado"). Esta Stage escolheu não ter caminho de
    skip, o que só é sustentável se o runner realmente servir o banco.
    """
    services = gate_job.get("services") or {}
    assert "postgres" in services, (
        "o job de gate precisa de um service `postgres`: a partir da Stage 2.3 o "
        "`make check` roda testes de integração que exigem banco real e NÃO se "
        "pulam quando ele falta. Ver ADR 2.3.0001."
    )

    image = str(services["postgres"].get("image", ""))
    assert image.startswith("postgres:"), (
        f"o service de gate precisa ser uma imagem oficial do Postgres; veio {image!r}"
    )

    # Sem health check o job corre contra um banco ainda subindo, e a falha vira
    # intermitente — a pior espécie de falha num gate, porque ensina a equipe a
    # re-rodar o CI em vez de acreditar nele.
    options = str(services["postgres"].get("options", ""))
    assert "--health-cmd" in options, (
        "o service de postgres precisa de health check, senão o job corre contra "
        "um banco que ainda não aceita conexão e o gate fica intermitente"
    )


@pytest.mark.unit
def test_gate_job_exporta_database_url_por_env(gate_job: dict[str, Any]) -> None:
    """A URL do banco viaja por `env:` do job, nunca como argumento do comando.

    É o invariante I3 da Stage 1.2: o step roda **literalmente** `make check`, e é
    isso que sustenta o argumento de transitividade do `validate-ci-gate.md`.
    Passar configuração na linha de comando quebraria esse argumento em silêncio —
    o runbook seguiria afirmando o que já não vale.
    """
    env = gate_job.get("env") or {}
    assert "DATABASE_URL" in env, (
        "o job de gate precisa exportar DATABASE_URL por `env:` — sem ela os "
        "testes de integração não sabem onde está o service de postgres"
    )

    url = str(env["DATABASE_URL"])
    assert url.startswith("postgresql+psycopg://"), (
        f"a DATABASE_URL do CI precisa nomear o driver (`+psycopg`), como o resto "
        f"do projeto faz desde a Stage 2.3; veio {url!r}"
    )

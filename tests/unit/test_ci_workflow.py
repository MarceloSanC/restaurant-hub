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
3. **O que a cadeia do `make check` confere** (issue #99): a transitividade só
   carrega para o runner o que o `make check` de fato roda. Tirar o `fmt-check`
   da cadeia, trocar o `--check` por uma formatação que conserta e aprova, ou
   esquecer um diretório com `.py` nos alvos de ruff deixa o CI verde sobre o que
   o hook do pre-commit reprovaria — e código commitado com `--no-verify`, ou de
   uma worktree sem hook, passa.

Não testar aqui estilo, nomes de step ou coisas que qualquer leitura do diff
pega.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = REPO_ROOT / "Makefile"

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


# ---------------------------------------------------------------------------
# Issue #99 — o `make check` confere formatação e cobre todo `.py` versionado.
#
# O hook do pre-commit formata e linta todo `.py` do commit; o gate só confere o
# que a cadeia do `check` roda, sobre os diretórios que os alvos nomeiam. As
# duas lacunas da #7 (F1 e F2) eram exatamente essas: sem conferência de
# formatação na cadeia e `migrations/` fora do lint.
# ---------------------------------------------------------------------------

# `uv run ruff <subcomando>`: os tokens antes das flags e dos caminhos.
_RUFF_PREFIX_LEN = 4

# Os alvos de ruff que o `check` precisa rodar, cada um com o subcomando e as
# flags exatas. Flag a mais muda o veredito: `--fix` no `lint` ou a falta do
# `--check` no `fmt-check` consertam o arquivo no runner e saem com 0.
_GATE_RUFF_TARGETS = {
    "lint": (["uv", "run", "ruff", "check"], set[str]()),
    "fmt-check": (["uv", "run", "ruff", "format"], {"--check"}),
}

# Alvos de ruff que precisam alcançar todo `.py` versionado: os dois do gate e o
# `fmt`, que é como o projeto formata (um diretório fora dele fica desformatado
# para sempre, e o `fmt-check` reprovaria sem que o `make fmt` resolvesse).
_RUFF_TARGETS = ("lint", "fmt-check", "fmt")


def _makefile_lines() -> list[str]:
    return MAKEFILE.read_text(encoding="utf-8").splitlines()


def _recipe(target: str) -> list[list[str]]:
    """Os comandos da receita de `target` no Makefile, já quebrados em tokens."""
    lines = _makefile_lines()
    header = f"{target}:"
    # Uma segunda regra com o mesmo alvo troca a receita (o make avisa "overriding
    # recipe" e roda a última); ler só a primeira seria cobrar a receita morta.
    assert lines.count(header) == 1, (
        f"o Makefile precisa declarar o target `{target}` exatamente uma vez; tem "
        f"{lines.count(header)}"
    )
    commands: list[list[str]] = []
    for line in lines[lines.index(header) + 1 :]:
        if not line.startswith("	"):
            break
        commands.append(shlex.split(line))
    assert commands, f"o target `{target}` do Makefile não tem receita"
    return commands


def _check_prerequisites() -> list[str]:
    """Os pré-requisitos do target `check`: a cadeia que o CI roda."""
    [line] = [line for line in _makefile_lines() if line.startswith("check:")]
    return line.removeprefix("check:").split()


def _versioned_python_files() -> list[str]:
    """Todo `.py`/`.pyi` versionado: o que o hook do pre-commit pode receber."""
    listed = subprocess.run(
        ["git", "ls-files", "--", "*.py", "*.pyi"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    files = listed.stdout.splitlines()
    assert files, "git ls-files não listou nenhum .py — o teste não teria o que cobrar"
    return files


@pytest.mark.unit
@pytest.mark.parametrize("target", sorted(_GATE_RUFF_TARGETS))
def test_check_chain_runs_ruff_target(target: str) -> None:
    """O `check` roda o `lint` e o `fmt-check`, com as flags que só conferem.

    Fora da cadeia, o alvo não roda no runner. Com a flag errada, roda e aprova:
    `ruff check --fix` corrige o erro corrigível e sai com 0, e `ruff format` sem
    `--check` formata o arquivo e sai com 0. Nos dois casos o CI fica verde sobre
    o código que o hook do pre-commit reprovaria.
    """
    assert target in _check_prerequisites(), (
        f"o `make check` não roda o `{target}`: o CI roda `make check` literalmente, e "
        f"o que sai da cadeia deixa de ser conferido no runner (issue #99)"
    )
    prefix, flags = _GATE_RUFF_TARGETS[target]
    [command] = _recipe(target)
    assert command[:_RUFF_PREFIX_LEN] == prefix, (
        f"o `make {target}` roda {command}; o gate espera {prefix}"
    )
    used = {token for token in command[_RUFF_PREFIX_LEN:] if token.startswith("-")}
    assert used == flags, (
        f"o `make {target}` passa {sorted(used)} ao ruff, e o gate espera {sorted(flags)}: "
        f"flag que conserta em vez de conferir faz o runner aprovar o que devia reprovar"
    )


@pytest.mark.unit
@pytest.mark.parametrize("target", _RUFF_TARGETS)
def test_ruff_target_covers_every_versioned_python_file(target: str) -> None:
    """Cada comando de ruff do alvo alcança todo `.py` versionado do repositório.

    O hook do pre-commit recebe todo `.py` do commit, de qualquer diretório. O
    alvo só confere os diretórios que nomeia: um `.py` fora deles passa no gate
    sem nunca ter sido conferido — era o caso de `migrations/` até a issue #99.
    A cobrança é sobre o que está versionado, e não sobre uma lista fixa: um
    diretório novo com Python reprova aqui até entrar nos alvos.
    """
    files = _versioned_python_files()
    for command in _recipe(target):
        assert command[: _RUFF_PREFIX_LEN - 1] == ["uv", "run", "ruff"], (
            f"o `make {target}` roda {command}, que não é o ruff do projeto"
        )
        positional = [token for token in command[_RUFF_PREFIX_LEN:] if not token.startswith("-")]
        # Todo posicional é um diretório do repositório: um `|| true` ou `; exit 0`
        # no fim da receita vira token aqui e deixaria o alvo sempre verde.
        not_dirs = [token for token in positional if not (REPO_ROOT / token).is_dir()]
        assert not_dirs == [], (
            f"`{shlex.join(command)}` (make {target}) passa {not_dirs} ao ruff, que não "
            f"são diretórios do repositório: operador de shell na receita muda o veredito"
        )
        paths = [token.rstrip("/") + "/" for token in positional]
        uncovered = sorted(path for path in files if not path.startswith(tuple(paths)))
        assert uncovered == [], (
            f"`{shlex.join(command)}` (make {target}) não alcança {uncovered}: o hook do "
            f"pre-commit confere esses arquivos e o gate não (issue #99)"
        )


@pytest.mark.unit
def test_fmt_formats_and_fixes() -> None:
    """O `make fmt` formata e aplica as correções seguras do lint.

    Sem o `ruff check --fix`, o `make fmt` deixa de consertar o que o `make lint`
    reprova e só o formatador corrige (o I001 de import fora de ordem, por exemplo).
    """
    subcommands = sorted(tuple(command[2:4]) for command in _recipe("fmt"))
    assert subcommands == [("ruff", "check"), ("ruff", "format")], (
        f"o `make fmt` precisa rodar `ruff format` e `ruff check --fix`; roda {subcommands}"
    )
    [fix] = [command for command in _recipe("fmt") if command[3] == "check"]
    assert "--fix" in fix, f"o `ruff check` do `make fmt` precisa de `--fix`: {fix}"


@pytest.mark.unit
def test_ruff_configuration_does_not_skip_versioned_python() -> None:
    """A configuração do ruff não tira de volta o que os alvos nomeiam.

    O Makefile nomear `migrations/` não basta: um `extend-exclude` no pyproject faz
    o ruff pular o diretório, um `exclude` do formatador o tira só do `fmt-check`,
    e um `per-file-ignores` com `ALL` deixa o lint ver o arquivo e não cobrar
    regra nenhuma. Nos três casos o hook pula junto (`--force-exclude`), a paridade
    continua e ninguém confere o arquivo. A exclusão do lint é medida pelo próprio
    ruff (`--show-files`, a resolução que o `make lint` usa); as outras duas, na
    configuração.
    """
    [lint] = _recipe("lint")
    listed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--show-files", *lint[_RUFF_PREFIX_LEN:]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    seen = {
        Path(line).resolve().relative_to(REPO_ROOT).as_posix()
        for line in listed.stdout.splitlines()
        if line.strip()
    }
    skipped = sorted(set(_versioned_python_files()) - seen)
    assert skipped == [], (
        f"o `make lint` nomeia o diretório, mas a configuração do ruff pula {skipped}"
    )

    ruff = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ruff = ruff.get("tool", {}).get("ruff", {})
    format_exclude = ruff.get("format", {}).get("exclude", [])
    assert format_exclude == [], (
        f"`[tool.ruff.format] exclude = {format_exclude}` tira arquivos só do "
        f"`fmt-check`: o lint os vê e a formatação deles nunca é conferida"
    )
    per_file = {
        **ruff.get("per-file-ignores", {}),
        **ruff.get("lint", {}).get("per-file-ignores", {}),
    }
    silenced = sorted(pattern for pattern, codes in per_file.items() if "ALL" in codes)
    assert silenced == [], (
        f"`per-file-ignores` com `ALL` em {silenced}: o lint vê esses arquivos e não "
        f"cobra regra nenhuma, o que equivale a excluí-los"
    )

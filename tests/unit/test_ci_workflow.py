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

Escopo deliberadamente estreito, nestas classes:

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
4. **O que o `make typecheck` confere** (issue #91): o mypy alcança todo `.py`
   versionado fora das exceções declaradas, e a configuração não o tira de volta.
5. **O que o `make docs-check` roda** (issue #97): todo `scripts/check_*.py` é
   validador de docs ligado no `docs-check`, salvo as exceções declaradas, cada
   uma conferida onde diz rodar. Um validador novo que ninguém liga reprova aqui.

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

from tests.unit._makefile import prerequisites
from tests.unit._makefile import recipe as _recipe

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

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


def _check_prerequisites() -> list[str]:
    """Os pré-requisitos do target `check`: a cadeia que o CI roda."""
    return prerequisites("check")


def _versioned_python_files() -> list[str]:
    """Todo `.py`/`.pyi` versionado: o que o hook do pre-commit pode receber.

    A pathspec `:(top)` e o `--full-name` leem a partir da raiz do git, não do
    `cwd`. Na corrida de mutação, `REPO_ROOT` é a cópia `mutants/`, que fica
    dentro do checkout e não tem arquivo rastreado: sem a âncora na raiz, o
    `ls-files` saía vazio e derrubava a coleta de estatísticas (issue #87, run
    41489942553).
    """
    listed = subprocess.run(
        ["git", "ls-files", "--full-name", "--", ":(top)*.py", ":(top)*.pyi"],
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


# ---------------------------------------------------------------------------
# O que o `make typecheck` confere (issue #91)
#
# A paridade hook↔target (`test_precommit_config.py`) não pega a remoção
# simultânea de um diretório nos dois lados: o hook continua rodando "o comando
# do target", e o diretório sai do mypy sem nenhum teste vermelho. Foi assim que
# `scripts/` ficou fora do `mypy --strict` até a #91, acumulando 23 erros.
# ---------------------------------------------------------------------------

# Versionado em Python e fora do `mypy --strict`, por decisão: os testes (exceto
# os fakes, que implementam os ports por tipagem estrutural) e as migrations,
# geradas pelo Alembic. Entrada nova aqui é decisão, editando o teste.
_TYPECHECK_EXEMPT = ("tests/", "migrations/")
_TYPECHECK_REQUIRED_INSIDE_EXEMPT = ("tests/fakes/",)

# `uv run mypy`: os tokens antes dos caminhos.
_MYPY_PREFIX_LEN = 3


def _typechecked(path: str, roots: list[str]) -> bool:
    return path.startswith(tuple(roots))


@pytest.mark.unit
def test_typecheck_covers_every_versioned_python_outside_the_exemptions() -> None:
    """O `make typecheck` alcança todo `.py` versionado fora de `tests/` e `migrations/`.

    A cobrança é sobre o que está versionado, não sobre uma lista fixa: um
    diretório novo com Python (ou um script novo fora de `scripts/`) reprova aqui
    até entrar no alvo. Os fakes de `tests/fakes/` são cobrados mesmo dentro da
    exceção (Stage 2.2).
    """
    assert "typecheck" in _check_prerequisites(), (
        "o `make check` não roda o `typecheck`: o CI roda `make check` literalmente"
    )
    [command] = _recipe("typecheck")
    assert command[:_MYPY_PREFIX_LEN] == ["uv", "run", "mypy"], (
        f"o `make typecheck` roda {command}, que não é o mypy do projeto"
    )
    roots = [
        token.rstrip("/") + "/" for token in command[_MYPY_PREFIX_LEN:] if not token.startswith("-")
    ]
    not_dirs = [root for root in roots if not (REPO_ROOT / root).is_dir()]
    assert not_dirs == [], (
        f"o `make typecheck` passa {not_dirs} ao mypy, que não são diretórios do "
        f"repositório: operador de shell na receita muda o veredito"
    )
    files = _versioned_python_files()
    unchecked = sorted(
        path
        for path in files
        if not _typechecked(path, roots)
        and (
            not path.startswith(_TYPECHECK_EXEMPT)
            or path.startswith(_TYPECHECK_REQUIRED_INSIDE_EXEMPT)
        )
    )
    assert unchecked == [], (
        f"o `make typecheck` ({shlex.join(command)}) não alcança {unchecked}: erro de "
        f"tipo nesses arquivos passa no gate (issue #91)"
    )


@pytest.mark.unit
def test_mypy_configuration_does_not_skip_what_typecheck_names() -> None:
    """A configuração do mypy não tira de volta o que o `make typecheck` nomeia.

    Um `exclude` em `[tool.mypy]` pula arquivo mesmo quando o diretório é passado
    na linha de comando, e um override com `ignore_errors` deixa o mypy ler o
    módulo sem reportar nada: nos dois casos o alvo nomeia o diretório e o erro
    de tipo passa.
    """
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    mypy = config.get("tool", {}).get("mypy", {})
    assert mypy.get("strict") is True, "`[tool.mypy]` precisa de `strict = true`"
    assert "exclude" not in mypy, (
        f"`[tool.mypy] exclude = {mypy['exclude']!r}` pula arquivos que o `make typecheck` nomeia"
    )
    silenced = [
        override.get("module")
        for override in mypy.get("overrides", [])
        if override.get("ignore_errors")
    ]
    assert silenced == [], (
        f"`[[tool.mypy.overrides]]` com `ignore_errors` em {silenced}: o mypy lê esses "
        f"módulos e não reporta erro nenhum, o que equivale a excluí-los"
    )


# ---------------------------------------------------------------------------
# O que o `make test-gate` mede (issue #91)
#
# Até a #91 a cobertura media só `src/` (`omit = */scripts/*`), e um gate podia
# perder teste sem que o `make check` acusasse. O alvo roda a suíte uma vez e
# relata duas partes, cada uma sob o `fail_under` do pyproject: um gate só sobre
# o total esconderia uma parte abaixo de 90% atrás da outra.
# ---------------------------------------------------------------------------

# As partes relatadas à parte, cada uma com o seu `coverage report --include`.
_COVERAGE_PARTS = (
    frozenset({"src/*"}),
    frozenset({"scripts/*", ".claude/hooks/*"}),
)
_MAIN_GUARD = 'if __name__ == "__main__":'


def _coverage_config() -> dict[str, Any]:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    coverage: dict[str, Any] = config["tool"]["coverage"]
    return coverage


@pytest.mark.unit
def test_test_gate_measures_every_versioned_python_outside_the_exemptions() -> None:
    """O pytest do `test-gate` mede todo `.py` versionado fora de `tests/` e `migrations/`."""
    assert "test-gate" in _check_prerequisites(), (
        "o `make check` não roda o `test-gate`: o CI roda `make check` literalmente"
    )
    pytest_command = _recipe("test-gate")[0]
    assert pytest_command[:3] == ["uv", "run", "pytest"], (
        f"o primeiro comando do `make test-gate` precisa ser a suíte: {pytest_command}"
    )
    roots = [
        token.removeprefix("--cov=").rstrip("/") + "/"
        for token in pytest_command
        if token.startswith("--cov=")
    ]
    unmeasured = sorted(
        path
        for path in _versioned_python_files()
        if not path.startswith(_TYPECHECK_EXEMPT) and not path.startswith(tuple(roots))
    )
    assert unmeasured == [], (
        f"o `make test-gate` ({shlex.join(pytest_command)}) não mede {unmeasured}: um "
        f"gate pode perder teste sem que o `make check` acuse (issue #91)"
    )


@pytest.mark.unit
def test_test_gate_reports_each_part_under_the_configured_threshold() -> None:
    """Um `coverage report --include` por parte, sem flag que mude limiar ou escopo."""
    reports = _recipe("test-gate")[1:]
    parts: list[frozenset[str]] = []
    for command in reports:
        assert command[:4] == ["uv", "run", "coverage", "report"], (
            f"o `make test-gate` roda {command}; depois da suíte só cabem os relatórios"
        )
        flags = [token for token in command[4:] if token.startswith("-")]
        includes = [flag for flag in flags if flag.startswith("--include=")]
        assert len(includes) == 1 and flags == includes, (
            f"`{shlex.join(command)}` passa {flags}: só o `--include` da parte é "
            f"permitido — `--fail-under` ou `--omit` mudariam o veredito do gate"
        )
        parts.append(frozenset(includes[0].removeprefix("--include=").split(",")))
    assert sorted(parts, key=sorted) == sorted(_COVERAGE_PARTS, key=sorted), (
        f"o `make test-gate` relata as partes {[sorted(p) for p in parts]}; o gate "
        f"espera {[sorted(p) for p in _COVERAGE_PARTS]}"
    )
    threshold = 90
    assert _coverage_config()["report"]["fail_under"] >= threshold


@pytest.mark.unit
def test_coverage_configuration_does_not_drop_tooling() -> None:
    """Nem `omit` nem `exclude` tiram de volta o que o `test-gate` mede.

    `omit` só para `migrations/` (geradas pelo Alembic) e, como exclusão de
    linha, só o bloco `if __name__ == "__main__":`, que roda por subprocess e
    apenas chama o `main()` testado in-process.
    """
    coverage = _coverage_config()
    assert coverage["run"].get("omit", []) == ["*/migrations/*"], (
        f"`[tool.coverage.run] omit = {coverage['run'].get('omit')}`: arquivo omitido "
        f"some do relatório e do gate"
    )
    report = coverage["report"]
    assert report.get("exclude_lines", []) == [], "`exclude_lines` troca as exclusões padrão"
    assert report.get("exclude_also", []) == [_MAIN_GUARD], (
        f"`exclude_also = {report.get('exclude_also')}`: exclusão nova precisa de "
        f"justificativa e de entrar aqui por decisão"
    )


@pytest.mark.unit
def test_test_gate_pytest_passes_only_measurement_flags() -> None:
    """No pytest do `test-gate`, só `--cov=` e `--cov-report=`.

    `--cov-fail-under` ou `--cov-config` apontando para outro arquivo mudariam o
    limiar sem tocar o pyproject que os outros testes leem.
    """
    pytest_command = _recipe("test-gate")[0]
    flags = [token for token in pytest_command[3:] if token.startswith("-")]
    unexpected = [flag for flag in flags if not flag.startswith(("--cov=", "--cov-report="))]
    assert unexpected == [], (
        f"o pytest do `make test-gate` passa {unexpected}: flag que muda o limiar ou a "
        f"configuração da cobertura muda o veredito do gate"
    )


# ---------------------------------------------------------------------------
# O que o `make docs-check` roda (issue #97)
#
# Cada validador de docs tem teste unitário próprio, mas o teste do script não
# vê o Makefile: apagar a linha dele do `docs-check` deixava a suíte verde e o
# gate inerte — definido, testado, nunca chamado no `make check` nem no CI.
# ---------------------------------------------------------------------------

_SCRIPTS = REPO_ROOT / "scripts"

# Os `scripts/check_*.py` que NÃO são validador de docs, cada um com o lugar onde
# roda. Fora destas exceções, todo `check_*.py` é validador de docs e precisa
# estar no `docs-check`: o conjunto esperado é derivado da pasta, e o teste não
# muda a cada validador novo. Exceção nova é decisão, editando o teste.
#
# - `check_layout.py` e `check_dead_shared.py` validam o código de `src/`, não
#   docs: rodam no `layout-check`, que também está na cadeia do `check`.
_IN_OTHER_TARGET = {
    "check_layout.py": "layout-check",
    "check_dead_shared.py": "layout-check",
}
# - `check_commit_msg.py` lê a mensagem do commit: é o hook `commit-msg`, e o
#   `make check` não tem mensagem a validar.
# - `check_mutation_run.py` lê o resumo de uma corrida do mutmut, que só existe
#   no job noturno do `audit-gate.yml`.
# - `check_mutation_db_isolation.py` lê o log do service Postgres durante essa
#   corrida, que também só existe no job noturno (issue #132).
_OUTSIDE_MAKE = {
    "check_commit_msg.py": ".pre-commit-config.yaml",
    "check_mutation_run.py": ".github/workflows/audit-gate.yml",
    "check_mutation_db_isolation.py": ".github/workflows/audit-gate.yml",
}

# `uv run python scripts/<validador>.py`, sem argumento: argumento ou operador de
# shell na receita (`|| true`, `; exit 0`) muda o que o validador confere ou o
# veredito do target.
_PYTHON_SCRIPT_PREFIX = ["uv", "run", "python"]


def _check_scripts() -> set[str]:
    return {path.name for path in _SCRIPTS.glob("check_*.py")}


def _docs_validators() -> set[str]:
    return _check_scripts() - set(_IN_OTHER_TARGET) - set(_OUTSIDE_MAKE)


def _scripts_run_by(target: str) -> list[str]:
    """Os scripts que a receita de `target` roda, conferindo a forma do comando."""
    scripts: list[str] = []
    for command in _recipe(target):
        *prefix, path = command
        assert prefix == _PYTHON_SCRIPT_PREFIX, (
            f"o `make {target}` roda `{shlex.join(command)}`; cada linha precisa ser "
            f"`uv run python scripts/<validador>.py`, sem argumento nem operador de shell"
        )
        assert path.startswith("scripts/"), f"o `make {target}` roda {path}, fora de scripts/"
        scripts.append(path.removeprefix("scripts/"))
    return scripts


@pytest.mark.unit
def test_check_depends_on_docs_check() -> None:
    """O `check` roda o `docs-check`: fora da cadeia, nenhum validador de docs roda no CI."""
    assert "docs-check" in _check_prerequisites(), (
        "o `make check` não roda o `docs-check`: o CI roda `make check` literalmente, e "
        "os validadores de docs deixam de ser conferidos no runner (issue #97)"
    )


@pytest.mark.unit
def test_docs_check_runs_every_docs_validator() -> None:
    """O `docs-check` roda exatamente os validadores de docs de `scripts/`.

    O esperado é derivado da pasta (`scripts/check_*.py` menos as exceções), e a
    comparação é de conjunto: tirar uma linha do `docs-check` reprova, um
    `check_*.py` novo sem linha reprova, e uma linha que aponta para script que
    não existe (renomeado, apagado) também.
    """
    expected = _docs_validators()
    assert expected, "nenhum validador de docs em scripts/: o teste não teria o que cobrar"
    run = _scripts_run_by("docs-check")
    repeated = sorted({script for script in run if run.count(script) > 1})
    assert repeated == [], f"o `make docs-check` roda {repeated} mais de uma vez"
    missing = sorted(expected - set(run))
    assert missing == [], (
        f"o `make docs-check` não roda {missing}: validador fora do target é gate inerte "
        f"— testado e nunca chamado no `make check` nem no CI. Ligue-o no `docs-check` "
        f"ou declare a exceção em `_IN_OTHER_TARGET`/`_OUTSIDE_MAKE` (issue #97)"
    )
    unexpected = sorted(set(run) - expected)
    assert unexpected == [], (
        f"o `make docs-check` roda {unexpected}, que não são validadores de docs em "
        f"scripts/ (script inexistente ou declarado como exceção)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("script", sorted(_IN_OTHER_TARGET))
def test_non_docs_validator_runs_in_its_declared_target(script: str) -> None:
    """A exceção de Makefile roda no target que declara, e o target está no `check`."""
    assert script in _check_scripts(), f"exceção obsoleta: scripts/{script} não existe"
    target = _IN_OTHER_TARGET[script]
    assert target in _check_prerequisites(), (
        f"o `make check` não roda o `{target}`, onde `{script}` diz rodar"
    )
    assert script in _scripts_run_by(target), (
        f"`{script}` está fora do `docs-check` por rodar no `{target}`, e não roda lá"
    )


@pytest.mark.unit
@pytest.mark.parametrize("script", sorted(_OUTSIDE_MAKE))
def test_non_docs_validator_runs_where_declared_outside_make(script: str) -> None:
    """A exceção fora do Makefile é chamada no arquivo que declara.

    Conta só a linha que invoca o script (`python scripts/<x>.py`) fora de
    comentário YAML: o `audit-gate.yml` cita `scripts/check_mutation_run.py` num
    comentário, e a simples menção deixava o teste verde com a chamada apagada.
    """
    assert script in _check_scripts(), f"exceção obsoleta: scripts/{script} não existe"
    where = REPO_ROOT / _OUTSIDE_MAKE[script]
    invocations = [
        line
        for line in where.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#") and f"python scripts/{script}" in line
    ]
    assert invocations, (
        f"`{script}` está fora do `docs-check` por rodar em {_OUTSIDE_MAKE[script]}, e "
        f"esse arquivo não o chama"
    )

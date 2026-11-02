"""Pré-condição de dependência de Stage: toda dependência em `Depende de` fechou.

Uso (depois de `git fetch origin`):
    python scripts/check_stage_deps.py                                   # docs-check
    python scripts/check_stage_deps.py 4.3-scheduling-application        # uma Stage
    python scripts/check_stage_deps.py 4.3-scheduling-application --ref origin/develop

Decisão: ADR 0.0.0009. Ligado em `make docs-check`.

---

**Por que existe (issue #12).** A Stage tem um identificador e formas derivadas
(CONVENTIONS §1, "Identificador da Stage"). Duas delas se encontram aqui e não se
trocam: o `depends_on` carrega o `stage_id` com slug (`1.1-bootstrap`); o commit
reservado de fechamento carrega só o número (`stage 1.1: complete`, CONVENTIONS
§4(b)). Feita à mão, em prosa, a conversão já errou nos dois sentidos — o padrão
`stage <dep>` casava `conceptual approved` (verde falso, F4 do PR #11) e o
`stage_id` no lugar do número não casava nada (HALT falso, F-C). Aqui a conversão
é código com teste: quem chama passa o `stage_id` que já tem.

**Fechada quer dizer mergeada.** Uma Stage só abre com as dependências mergeadas
(pré-requisitos do RUNBOOK-STAGE-LIFECYCLE, PIPELINE "Linearidade estrita",
GIT-WORKFLOW §"Branches em execução"). Para cada dependência da Stage-alvo, lida na
linha da alvo na *Tabela de Stages* do `docs/roadmap.md`:

- **Stage** (`stage_id`): tem linha na tabela; o número dela identifica uma única
  linha (senão `stage N.M: complete` não diz qual fechou); o status é `done`; e há um
  commit cujo subject é **exatamente** `stage <N.M>: complete` alcançável de uma
  branch de integração — `origin/develop`, `develop`, `origin/main`, `main`, as que
  resolverem (as mesmas do `check_technical_postexec.py`). Exato: `conceptual
  approved` ou `stage 11.1: complete` nunca satisfazem `1.1`. `--ref` (repetível)
  troca essas branches por refs explícitas, que precisam resolver todas.
- **issue** (`#N`): tem linha na *Tabela de Issues* com status `done` — a regra que o
  PROMPT-issue já usa. Issue de Stage não entra naquela tabela: liste o `stage_id`.

O status vem do roadmap da working tree; os commits, das refs. Roadmap sem `git pull`
dá vermelho falso, nunca verde.

**O alvo é o `stage_id`, nunca o número.** `4.3` sozinho é recusado (exit 2) com a
explicação: o número não carrega o slug, e pasta e roadmap são indexados pelo
`stage_id`. Sem argumento, os alvos são as pastas `docs/stages/N.M-<slug>/`.

**Sem histórico** (clone raso, nenhuma branch de integração, git que não executa).
Com alvo explícito — a pré-condição de quem vai abrir uma Stage —, exit 2: sem
veredito, e nunca verde. Sem alvo (`docs-check`), o status ainda é conferido e os
commits viram WARN: o `make check` local não deve exigir histórico completo (ADR
1.2.0001), e no CI ele existe (`fetch-depth: 0`, travado por
`tests/unit/test_ci_workflow.py`).

Códigos de saída:
  0  toda dependência fechada (sem alvo e sem histórico: status conferido + WARN)
  1  violação — dependência aberta ou linha do roadmap ilegível (motivo impresso)
  2  sem veredito — roadmap ausente ou ilegível, sem a seção ou as colunas; ref
     explícita que não resolve; alvo malformado; sem histórico com alvo explícito
     (fail closed). Nunca 1: quem chama lê 1 como violação
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = Path("docs") / "roadmap.md"
STAGES_DIR = Path("docs") / "stages"

STAGES_TABLE = "Tabela de Stages"
ISSUES_TABLE = "Tabela de Issues"
STAGE_COLUMN = "Stage"
ISSUE_COLUMN = "Issue"
STATUS_COLUMN = "Status"
DEPS_COLUMN = "Depende de"
DONE = "done"
# Status-sentinela de issue com mais de uma linha na Tabela de Issues (nunca `done`).
DUPLICATED_ISSUE = "<mais de uma linha>"
NO_DEPS = frozenset({"—", "-", ""})

# Onde "mergeada" é verdade: as mesmas branches, na mesma ordem, do
# `check_technical_postexec.py` (ADR 1.2.0001).
INTEGRATION_REFS = ("origin/develop", "develop", "origin/main", "main")

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

# stage_id = N.M-<slug>. N é o Step (número) ou `X`, o bucket de escopo órfão
# (CONVENTIONS §1 "Numeração"); o slug é kebab-case ASCII.
_STAGE_ID = re.compile(r"^(?P<number>(?:\d+|X)\.\d+)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_BARE_NUMBER = re.compile(r"^(?:\d+|X)\.\d+$")
_ISSUE_REF = re.compile(r"^#(?P<number>\d+)$")
# Célula `Issue` da Tabela de Issues: `[#59](https://…/issues/59)` ou `#59`.
_ISSUE_CELL = re.compile(r"^\[#(?P<linked>\d+)\]\([^)]*\)$|^#(?P<bare>\d+)$")
_CODE_SPAN = re.compile(r"^`([^`]*)`$")
_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_HEADER_AND_SEPARATOR = 2
# `\|` é pipe escapado dentro de célula markdown: não separa colunas.
_ESCAPED_PIPE = "\\|"
_PIPE_PLACEHOLDER = "\0"


class RoadmapError(Exception):
    """O roadmap não tem a forma que o script lê — sem veredito (exit 2)."""


class GitError(Exception):
    """O git respondeu, mas não com o que a checagem precisa — sem veredito (exit 2)."""


class HistoryUnavailable(GitError):
    """Não há histórico para olhar: clone raso, nenhuma branch de integração, git ausente."""


@dataclass(frozen=True)
class StageRow:
    """Uma linha da Tabela de Stages: o que a checagem precisa dela."""

    stage_id: str
    status: str
    depends_on: tuple[str, ...]
    depends_on_issues: tuple[int, ...] = ()

    @property
    def number(self) -> str:
        return stage_number(self.stage_id)


@dataclass(frozen=True)
class History:
    """Subjects alcançáveis das refs que resolveram — e quais foram (o "onde")."""

    subjects: frozenset[str]
    refs: tuple[str, ...]

    @property
    def where(self) -> str:
        return ", ".join(self.refs)


@dataclass(frozen=True)
class Verdict:
    """O que a checagem achou e o que ela de fato conferiu.

    As contagens saem do próprio laço — não da lista de alvos —, então o resumo
    `OK — N Stage(s), M dependência(s)` só afirma o que foi olhado.
    """

    violations: tuple[str, ...]
    stages: int
    dependencies: int


@dataclass(frozen=True)
class _Index:
    """As linhas da tabela por `stage_id` e por número."""

    by_id: dict[str, StageRow] = field(default_factory=dict)
    by_number: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def of(cls, rows: Sequence[StageRow]) -> _Index:
        index = cls()
        for row in rows:
            index.by_id[row.stage_id] = row
            index.by_number.setdefault(row.number, []).append(row.stage_id)
        return index


def stage_number(stage_id: str) -> str:
    """`1.1-bootstrap` → `1.1`: a forma que o commit reservado carrega."""
    match = _STAGE_ID.match(stage_id)
    if match is None:
        msg = f"stage_id malformado: {stage_id!r} (esperado `N.M-<slug>`)"
        raise ValueError(msg)
    return match.group("number")


def complete_subject(stage_id: str) -> str:
    """Subject do commit reservado que fecha a Stage (CONVENTIONS §4(b))."""
    return f"stage {stage_number(stage_id)}: complete"


def _cells(line: str) -> list[str]:
    body = line.strip().removeprefix("|").removesuffix("|")
    protected = body.replace(_ESCAPED_PIPE, _PIPE_PLACEHOLDER)
    return [cell.replace(_PIPE_PLACEHOLDER, "|").strip() for cell in protected.split("|")]


def _unquote(cell: str) -> str:
    """Tira a crase de code span: `` `1.1-bootstrap` `` → `1.1-bootstrap`."""
    text = cell.strip()
    match = _CODE_SPAN.match(text)
    return match.group(1).strip() if match else text


def _parse_deps(cell: str) -> tuple[tuple[str, ...], tuple[int, ...], list[str]]:
    """Da célula `Depende de`: Stages, issues e os tokens que não são nenhum dos dois."""
    if cell.strip() in NO_DEPS:
        return (), (), []
    stages: list[str] = []
    issues: list[int] = []
    unknown: list[str] = []
    for token in cell.split(","):
        candidate = _unquote(token)
        if _STAGE_ID.match(candidate):
            stages.append(candidate)
        elif issue := _ISSUE_REF.match(candidate):
            issues.append(int(issue.group("number")))
        else:
            unknown.append(token.strip())
    return tuple(stages), tuple(issues), unknown


def _table_lines(text: str, table_name: str) -> list[str]:
    """Linhas `|...|` da tabela que vem logo depois do título `## <table_name>`."""
    lines = text.splitlines()
    heading = f"## {table_name}"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        msg = f"seção `{heading}` ausente do roadmap"
        raise RoadmapError(msg) from None
    table: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        if line.lstrip().startswith("|"):
            table.append(line)
        elif table:
            break
    return table


def _columns(table: Sequence[str], table_name: str, wanted: Sequence[str]) -> list[int]:
    """Índice de cada coluna pedida, achada pelo nome no cabeçalho — não pela posição.

    O último elemento é a largura do cabeçalho.
    """
    if len(table) < _HEADER_AND_SEPARATOR:
        msg = f"`## {table_name}` sem cabeçalho e separador"
        raise RoadmapError(msg)
    header = _cells(table[0])
    if not all(_SEPARATOR_CELL.match(cell) for cell in _cells(table[1])):
        msg = f"`## {table_name}`: a linha depois do cabeçalho não é o separador `|---|`"
        raise RoadmapError(msg)
    missing = [column for column in wanted if column not in header]
    if missing:
        msg = f"`## {table_name}`: cabeçalho sem a(s) coluna(s) {', '.join(missing)}"
        raise RoadmapError(msg)
    return [header.index(column) for column in wanted] + [len(header)]


def parse_stage_table(text: str) -> tuple[list[StageRow], list[str]]:
    """Linhas da Tabela de Stages + problemas de forma (cada um, uma violação)."""
    table = _table_lines(text, STAGES_TABLE)
    i_stage, i_status, i_deps, width = _columns(
        table, STAGES_TABLE, (STAGE_COLUMN, STATUS_COLUMN, DEPS_COLUMN)
    )
    rows: list[StageRow] = []
    problems: list[str] = []
    seen: set[str] = set()
    for line in table[_HEADER_AND_SEPARATOR:]:
        cells = _cells(line)
        if len(cells) != width:
            problems.append(
                f"roadmap: linha da {STAGES_TABLE} com {len(cells)} célula(s), o cabeçalho "
                f"tem {width}: {line.strip()}"
            )
            continue
        stage_id = _unquote(cells[i_stage])
        if not _STAGE_ID.match(stage_id):
            problems.append(f"roadmap: `{cells[i_stage]}` não é um stage_id `N.M-<slug>`")
            continue
        if stage_id in seen:
            problems.append(f"roadmap: `{stage_id}` aparece em mais de uma linha da {STAGES_TABLE}")
            continue
        seen.add(stage_id)
        stages, issues, unknown = _parse_deps(cells[i_deps])
        problems.extend(
            f"roadmap: {stage_id}: `{token}` em {DEPS_COLUMN} não é stage_id `N.M-<slug>` "
            "nem issue `#N`"
            for token in unknown
        )
        rows.append(
            StageRow(
                stage_id=stage_id,
                status=cells[i_status],
                depends_on=stages,
                depends_on_issues=issues,
            )
        )
    return rows, problems


def parse_issue_table(text: str) -> dict[int, str]:
    """Status de cada issue da Tabela de Issues, pelo número.

    Linha cuja célula `Issue` não é `[#N](…)` nem `#N` fica de fora: uma
    dependência dela aparece como "fora da tabela" — vermelho, nunca verde.
    Issue com mais de uma linha vira `DUPLICATED_ISSUE`: escolher uma das linhas
    (a primeira ou a última) decidiria o verde pela ordem da tabela.
    """
    table = _table_lines(text, ISSUES_TABLE)
    i_issue, i_status, width = _columns(table, ISSUES_TABLE, (ISSUE_COLUMN, STATUS_COLUMN))
    statuses: dict[int, str] = {}
    for line in table[_HEADER_AND_SEPARATOR:]:
        cells = _cells(line)
        match = _ISSUE_CELL.match(cells[i_issue]) if len(cells) == width else None
        if match is not None:
            number = int(match.group("linked") or match.group("bare"))
            statuses[number] = DUPLICATED_ISSUE if number in statuses else cells[i_status]
    return statuses


def check_targets(
    targets: Sequence[str],
    rows: Sequence[StageRow],
    history: History | None,
    issues: Mapping[int, str],
) -> Verdict:
    """Confere as dependências de cada Stage-alvo (sem violação = todas fechadas).

    `history` None é o modo sem histórico do `docs-check`: o status é conferido, o
    commit não.
    """
    index = _Index.of(rows)
    violations: list[str] = []
    stages = dependencies = 0
    for target in targets:
        stages += 1
        row = index.by_id.get(target)
        if row is None:
            violations.append(
                f"{target}: sem linha na {STAGES_TABLE} — as dependências não são determináveis"
            )
            continue
        for dep in row.depends_on:
            dependencies += 1
            violations.extend(_check_stage_dependency(f"{target} → {dep}", dep, index, history))
        for number in row.depends_on_issues:
            dependencies += 1
            violations.extend(_check_issue_dependency(f"{target} → #{number}", number, issues))
    return Verdict(tuple(violations), stages, dependencies)


def _check_stage_dependency(
    where: str,
    dep: str,
    index: _Index,
    history: History | None,
) -> list[str]:
    dep_row = index.by_id.get(dep)
    if dep_row is None:
        return [f"{where}: a dependência não tem linha na {STAGES_TABLE}"]
    homonyms = index.by_number[dep_row.number]
    if len(homonyms) > 1:
        return [
            f"{where}: o número {dep_row.number} identifica mais de uma Stage "
            f"({', '.join(homonyms)}) — `stage {dep_row.number}: complete` não diz qual fechou"
        ]
    problems: list[str] = []
    if dep_row.status != DONE:
        problems.append(f"{where}: status `{dep_row.status}` na {STAGES_TABLE} (esperado `{DONE}`)")
    subject = complete_subject(dep)
    if history is not None and subject not in history.subjects:
        problems.append(f"{where}: commit `{subject}` não está mergeado em {history.where}")
    return problems


def _check_issue_dependency(where: str, number: int, issues: Mapping[int, str]) -> list[str]:
    status = issues.get(number)
    if status is None:
        return [
            f"{where}: issue fora da {ISSUES_TABLE} — se é a issue de uma Stage, a "
            "dependência se escreve com o stage_id dela (CONVENTIONS §1)"
        ]
    if status == DUPLICATED_ISSUE:
        return [f"{where}: a issue aparece em mais de uma linha da {ISSUES_TABLE}"]
    if status != DONE:
        return [f"{where}: status `{status}` na {ISSUES_TABLE} (esperado `{DONE}`)"]
    return []


def _git(args: Sequence[str], repo: Path) -> str:
    # Bytes + decode explícito: com `text=True` o subprocess usaria o locale do SO
    # (cp1252 no Windows) e um subject acentuado viraria mojibake.
    try:
        result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    except OSError as exc:
        # git fora do PATH ou cwd inexistente. Sem isto o traceback sairia com 1 —
        # o código de violação.
        msg = f"`git` não pôde ser executado: {exc}"
        raise HistoryUnavailable(msg) from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        msg = f"`git {' '.join(args)}` falhou ({result.returncode}): {detail}"
        raise GitError(msg)
    return result.stdout.decode("utf-8", errors="replace")


def _resolves(ref: str, repo: Path) -> bool:
    try:
        _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo)
    except HistoryUnavailable:
        raise
    except GitError:
        return False
    return True


def git_history(refs: Sequence[str], repo: Path, every_ref: bool) -> History:
    """Subjects de todo commit alcançável de qualquer uma das `refs` que resolvem.

    `every_ref` (refs explícitas, `--ref`): ref que não resolve é erro. Sem ele (as
    branches de integração), basta uma resolver.
    """
    if _git(["rev-parse", "--is-shallow-repository"], repo).strip() == "true":
        msg = (
            "clone raso: os commits reservados `stage N.M: complete` não estão no "
            "histórico — rode com histórico completo (o ci.yml usa fetch-depth: 0; "
            "ADR 1.2.0001)"
        )
        raise HistoryUnavailable(msg)
    resolved = tuple(ref for ref in refs if _resolves(ref, repo))
    missing = [ref for ref in refs if ref not in resolved]
    if every_ref and missing:
        msg = f"ref(s) {', '.join(missing)} não resolve(m) para um commit (faltou `git fetch`?)"
        raise GitError(msg)
    if not resolved:
        msg = f"nenhuma branch de integração resolve ({', '.join(refs)}) — faltou `git fetch`?"
        raise HistoryUnavailable(msg)
    log = _git(["log", "--format=%s", *resolved], repo)
    return History(frozenset(line.strip() for line in log.splitlines()), resolved)


def read_roadmap(repo: Path) -> str:
    """Texto do roadmap; ausente ou ilegível vira `RoadmapError` (sem veredito)."""
    try:
        return (repo / ROADMAP).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        msg = f"roadmap ausente em {ROADMAP}"
        raise RoadmapError(msg) from None
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"roadmap ilegível em {ROADMAP}: {exc}"
        raise RoadmapError(msg) from exc


def discover_stage_folders(repo: Path) -> list[str]:
    """`stage_id` de cada pasta `docs/stages/N.M-<slug>/` (ignora `_archived/` e afins)."""
    stages = repo / STAGES_DIR
    if not stages.is_dir():
        return []
    return sorted(p.name for p in stages.iterdir() if p.is_dir() and _STAGE_ID.match(p.name))


def target_problem(target: str) -> str | None:
    """Por que `target` não serve de alvo — ou None, se é um `stage_id`."""
    if _STAGE_ID.match(target):
        return None
    if _BARE_NUMBER.match(target):
        return (
            f"`{target}` é o número da Stage; o alvo é o stage_id com slug, como na coluna "
            f"{STAGE_COLUMN} do roadmap (`{target}-<slug>`). O número do commit reservado o "
            "script deriva sozinho — CONVENTIONS §1, ADR 0.0.0009."
        )
    return f"`{target}` não é um stage_id `N.M-<slug>` (ex.: `1.1-bootstrap`)."


def _report(violations: Sequence[str]) -> None:
    print(f"check_stage_deps: FALHA — {len(violations)} violação(ões):", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nO número do commit reservado sai do stage_id (`1.1-bootstrap` → "
        "`stage 1.1: complete`, CONVENTIONS §1). Uma Stage só abre com as dependências "
        "`done` no roadmap e mergeadas (ADR 0.0.0009).",
        file=sys.stderr,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "stages",
        nargs="*",
        help="stage_id(s) `N.M-<slug>`; vazio = toda pasta em docs/stages/",
    )
    parser.add_argument(
        "--ref",
        action="append",
        help=(
            "ref onde procurar `stage N.M: complete` (repetível); default: as branches "
            f"de integração que resolverem ({', '.join(INTEGRATION_REFS)})"
        ),
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    return parser


HistoryReader = Callable[[Sequence[str], Path, bool], History]


def main(argv: Sequence[str] | None = None, *, read_history: HistoryReader = git_history) -> int:
    args = _parser().parse_args(argv)
    problem = next((p for t in args.stages if (p := target_problem(t)) is not None), None)
    if problem is not None:
        print(f"check_stage_deps: {problem}", file=sys.stderr)
        return EXIT_ERROR

    refs = tuple(args.ref) if args.ref else INTEGRATION_REFS
    warning: str | None = None
    history: History | None = None
    try:
        text = read_roadmap(args.repo)
        rows, problems = parse_stage_table(text)
        targets = list(args.stages) or discover_stage_folders(args.repo)
        index = _Index.of(rows)
        wanted = [index.by_id[t] for t in targets if t in index.by_id]
        # O histórico só é lido se alguma Stage-alvo depende de Stage: sem isso há
        # veredito mesmo num clone raso.
        if any(row.depends_on for row in wanted):
            try:
                history = read_history(refs, args.repo, bool(args.ref))
            except HistoryUnavailable as exc:
                if args.stages:
                    raise
                warning = str(exc)
        issues = parse_issue_table(text) if any(r.depends_on_issues for r in wanted) else {}
        verdict = check_targets(targets, rows, history, issues)
    except (RoadmapError, GitError, OSError) as exc:
        print(f"check_stage_deps: {exc} (fail closed)", file=sys.stderr)
        return EXIT_ERROR

    if warning is not None:
        print(
            f"check_stage_deps: WARN — {warning}. Status conferido no roadmap; os commits "
            "`stage N.M: complete` não (no CI há histórico: fetch-depth: 0).",
            file=sys.stderr,
        )
    violations = [*problems, *verdict.violations]
    if violations:
        _report(violations)
        return EXIT_VIOLATION
    where = f" em {history.where}" if history is not None else ""
    print(
        f"check_stage_deps: OK — {verdict.stages} Stage(s), "
        f"{verdict.dependencies} dependência(s) fechada(s){where}"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

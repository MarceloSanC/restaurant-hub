"""Pré-condição de dependência de Stage: toda Stage em `depends_on` fechou.

Uso:
    python scripts/check_stage_deps.py                    # docs-check: toda pasta, contra HEAD
    python scripts/check_stage_deps.py 4.3-scheduling-application        # uma Stage
    python scripts/check_stage_deps.py 4.3-scheduling-application --ref origin/develop

Decisão: ADR 0.0.0007. Ligado em `make docs-check`.

---

**Por que existe (issue #12).** A Stage tem um identificador e formas derivadas
(CONVENTIONS §1, "Identificador da Stage"). Duas delas se encontram aqui e não se
trocam: o `depends_on` carrega o `stage_id` com slug (`1.1-bootstrap`); o commit
reservado de fechamento carrega só o número (`stage 1.1: complete`, CONVENTIONS
§4(b)). Feita à mão, em prosa, a conversão já errou nos dois sentidos — o padrão
`stage <dep>` casava `conceptual approved` (verde falso, F4 do PR #11) e o
`stage_id` no lugar do número não casava nada (HALT falso, F-C). Aqui a conversão
é código com teste: quem chama passa o `stage_id` que já tem.

**O que se confere, para cada dependência da Stage-alvo** (lida na linha da alvo
na *Tabela de Stages* do `docs/roadmap.md`, a fonte do `depends_on` e do status):

1. a dependência tem linha na tabela;
2. o número dela identifica uma única linha — senão `stage N.M: complete` não diz
   qual Stage fechou;
3. o status dela é `done`;
4. há no histórico de `--ref` um commit cujo subject é **exatamente**
   `stage <N.M>: complete` (exato: `conceptual approved` ou `stage 11.1: complete`
   nunca satisfazem `1.1`).

**O alvo é o `stage_id`, nunca o número.** `4.3` sozinho é recusado (exit 2) com a
explicação: o número não carrega o slug, e pasta e roadmap são indexados pelo
`stage_id`. Sem argumento, os alvos são as pastas `docs/stages/N.M-<slug>/`.

**`--ref`.** `HEAD` (default) é "o que este branch carrega": a regra do prompt
canônico (dependências fechadas antes de abrir a Stage), e determinística. É a
semântica do `docs-check`: uma pasta de Stage só existe depois do esqueleto, e o
esqueleto só é legítimo com as dependências fechadas — nenhum estado legítimo deixa
o gate vermelho para PR alheio. `origin/develop` (depois de `git fetch`) é
"mergeado em develop": a variante autônoma §4 e a mestra do Step ao abrir Stage.

Códigos de saída:
  0  toda dependência conferida
  1  violação (Stage, dependência e motivo impressos)
  2  não dá para decidir — roadmap, seção ou colunas ausentes; ref que não resolve;
     clone raso (os commits reservados não estão no histórico — ADR 1.2.0001); alvo
     malformado (fail closed)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = Path("docs") / "roadmap.md"
STAGES_DIR = Path("docs") / "stages"

TABLE_NAME = "Tabela de Stages"
SECTION = f"## {TABLE_NAME}"
STAGE_COLUMN = "Stage"
STATUS_COLUMN = "Status"
DEPS_COLUMN = "Depende de"
DONE = "done"
NO_DEPS = frozenset({"—", "-", ""})

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_ERROR = 2

# stage_id = N.M-<slug>. N é o Step (número) ou `X`, o bucket de escopo órfão
# (CONVENTIONS §1 "Numeração"); o slug é kebab-case ASCII.
_STAGE_ID = re.compile(r"^(?P<number>(?:\d+|X)\.\d+)-[a-z0-9]+(?:-[a-z0-9]+)*$")
_BARE_NUMBER = re.compile(r"^(?:\d+|X)\.\d+$")
_CODE_SPAN = re.compile(r"^`([^`]*)`$")
_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_HEADER_AND_SEPARATOR = 2
# `\|` é pipe escapado dentro de célula markdown: não separa colunas.
_ESCAPED_PIPE = "\\|"
_PIPE_PLACEHOLDER = "\0"


class RoadmapError(Exception):
    """O roadmap não tem a forma que o script lê — sem veredito (exit 2)."""


class GitError(Exception):
    """O histórico não pôde ser lido — sem veredito (exit 2)."""


@dataclass(frozen=True)
class StageRow:
    """Uma linha da Tabela de Stages: o que a checagem precisa dela."""

    stage_id: str
    status: str
    depends_on: tuple[str, ...]

    @property
    def number(self) -> str:
        return stage_number(self.stage_id)


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


def _parse_deps(cell: str) -> tuple[tuple[str, ...], list[str]]:
    """Dependências da célula `Depende de` + os tokens que não são `stage_id`."""
    if cell.strip() in NO_DEPS:
        return (), []
    deps: list[str] = []
    unknown: list[str] = []
    for token in cell.split(","):
        candidate = _unquote(token)
        if _STAGE_ID.match(candidate):
            deps.append(candidate)
        else:
            unknown.append(token.strip())
    return tuple(deps), unknown


def _table_lines(text: str) -> list[str]:
    """Linhas `|...|` da tabela que vem logo depois do título da seção."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == SECTION)
    except StopIteration:
        msg = f"seção `{SECTION}` ausente do roadmap"
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


def _column_indexes(table: Sequence[str]) -> tuple[int, int, int, int]:
    """(stage, status, deps, largura) achados pelo nome no cabeçalho, não pela posição."""
    if len(table) < _HEADER_AND_SEPARATOR:
        msg = f"`{SECTION}` sem cabeçalho e separador"
        raise RoadmapError(msg)
    header = _cells(table[0])
    if not all(_SEPARATOR_CELL.match(cell) for cell in _cells(table[1])):
        msg = f"`{SECTION}`: a linha depois do cabeçalho não é o separador `|---|`"
        raise RoadmapError(msg)
    missing = [c for c in (STAGE_COLUMN, STATUS_COLUMN, DEPS_COLUMN) if c not in header]
    if missing:
        msg = f"`{SECTION}`: cabeçalho sem a(s) coluna(s) {', '.join(missing)}"
        raise RoadmapError(msg)
    return (
        header.index(STAGE_COLUMN),
        header.index(STATUS_COLUMN),
        header.index(DEPS_COLUMN),
        len(header),
    )


def parse_stage_table(text: str) -> tuple[list[StageRow], list[str]]:
    """Linhas da Tabela de Stages + problemas de forma (cada um, uma violação)."""
    table = _table_lines(text)
    i_stage, i_status, i_deps, width = _column_indexes(table)
    rows: list[StageRow] = []
    problems: list[str] = []
    seen: set[str] = set()
    for line in table[_HEADER_AND_SEPARATOR:]:
        cells = _cells(line)
        if len(cells) != width:
            problems.append(
                f"roadmap: linha da {TABLE_NAME} com {len(cells)} célula(s), o cabeçalho "
                f"tem {width}: {line.strip()}"
            )
            continue
        stage_id = _unquote(cells[i_stage])
        if not _STAGE_ID.match(stage_id):
            problems.append(f"roadmap: `{cells[i_stage]}` não é um stage_id `N.M-<slug>`")
            continue
        if stage_id in seen:
            problems.append(f"roadmap: `{stage_id}` aparece em mais de uma linha da {TABLE_NAME}")
            continue
        seen.add(stage_id)
        deps, unknown = _parse_deps(cells[i_deps])
        problems.extend(
            f"roadmap: {stage_id}: `{token}` em {DEPS_COLUMN} não é um stage_id `N.M-<slug>`"
            for token in unknown
        )
        rows.append(StageRow(stage_id=stage_id, status=cells[i_status], depends_on=deps))
    return rows, problems


def check_targets(
    targets: Sequence[str],
    rows: Sequence[StageRow],
    subjects: frozenset[str],
    ref: str,
) -> list[str]:
    """Violações das dependências de cada Stage-alvo (vazia = todas fechadas)."""
    index = _Index.of(rows)
    violations: list[str] = []
    for target in targets:
        row = index.by_id.get(target)
        if row is None:
            violations.append(
                f"{target}: sem linha na {TABLE_NAME} — as dependências não são determináveis"
            )
            continue
        for dep in row.depends_on:
            violations.extend(_check_dependency(f"{target} → {dep}", dep, index, subjects, ref))
    return violations


def _check_dependency(
    where: str,
    dep: str,
    index: _Index,
    subjects: frozenset[str],
    ref: str,
) -> list[str]:
    dep_row = index.by_id.get(dep)
    if dep_row is None:
        return [f"{where}: a dependência não tem linha na {TABLE_NAME}"]
    homonyms = index.by_number[dep_row.number]
    if len(homonyms) > 1:
        return [
            f"{where}: o número {dep_row.number} identifica mais de uma Stage "
            f"({', '.join(homonyms)}) — `stage {dep_row.number}: complete` não diz qual fechou"
        ]
    problems: list[str] = []
    if dep_row.status != DONE:
        problems.append(f"{where}: status `{dep_row.status}` na {TABLE_NAME} (esperado `{DONE}`)")
    subject = complete_subject(dep)
    if subject not in subjects:
        problems.append(f"{where}: commit `{subject}` ausente do histórico de {ref}")
    return problems


def _git(args: Sequence[str], repo: Path) -> str:
    # Bytes + decode explícito: com `text=True` o subprocess usaria o locale do SO
    # (cp1252 no Windows) e um subject acentuado viraria mojibake.
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        msg = f"`git {' '.join(args)}` falhou ({result.returncode}): {detail}"
        raise GitError(msg)
    return result.stdout.decode("utf-8", errors="replace")


def git_subjects(ref: str, repo: Path) -> frozenset[str]:
    """Subject de todo commit alcançável a partir de `ref`."""
    if _git(["rev-parse", "--is-shallow-repository"], repo).strip() == "true":
        msg = (
            "clone raso: os commits reservados `stage N.M: complete` não estão no "
            "histórico — rode com histórico completo (o ci.yml usa fetch-depth: 0; "
            "ADR 1.2.0001)"
        )
        raise GitError(msg)
    try:
        _git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo)
    except GitError:
        msg = f"a ref `{ref}` não resolve para um commit (faltou `git fetch`?)"
        raise GitError(msg) from None
    log = _git(["log", "--format=%s", ref], repo)
    return frozenset(line.strip() for line in log.splitlines())


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
            "script deriva sozinho — CONVENTIONS §1, ADR 0.0.0007."
        )
    return f"`{target}` não é um stage_id `N.M-<slug>` (ex.: `1.1-bootstrap`)."


def _report(violations: Sequence[str]) -> None:
    print(f"check_stage_deps: FALHA — {len(violations)} violação(ões):", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nO número do commit reservado sai do stage_id (`1.1-bootstrap` → "
        "`stage 1.1: complete`, CONVENTIONS §1). Uma Stage só abre com as dependências "
        "`done` no roadmap e fechadas no histórico (ADR 0.0.0007).",
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
        default="HEAD",
        help="histórico onde procurar `stage N.M: complete` (default: HEAD)",
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    read_subjects: Callable[[str, Path], frozenset[str]] = git_subjects,
) -> int:
    args = _parser().parse_args(argv)
    problem = next((p for t in args.stages if (p := target_problem(t)) is not None), None)
    if problem is not None:
        print(f"check_stage_deps: {problem}", file=sys.stderr)
        return EXIT_ERROR

    roadmap = args.repo / ROADMAP
    try:
        if not roadmap.is_file():
            msg = f"roadmap ausente em {ROADMAP}"
            raise RoadmapError(msg)
        rows, violations = parse_stage_table(roadmap.read_text(encoding="utf-8-sig"))
        targets = list(args.stages) or discover_stage_folders(args.repo)
        if targets:
            subjects = read_subjects(args.ref, args.repo)
            violations += check_targets(targets, rows, subjects, args.ref)
    except (RoadmapError, GitError) as exc:
        print(f"check_stage_deps: {exc} (fail closed)", file=sys.stderr)
        return EXIT_ERROR

    if violations:
        _report(violations)
        return EXIT_VIOLATION
    index = _Index.of(rows)
    checked = sum(len(index.by_id[t].depends_on) for t in targets)
    print(
        f"check_stage_deps: OK — {len(targets)} Stage(s), "
        f"{checked} dependência(s) fechada(s) em {args.ref}"
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

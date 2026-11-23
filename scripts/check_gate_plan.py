"""Guard: todo `technical.md` novo traz o plano de gates na forma do template.

Uso:
    python scripts/check_gate_plan.py
    python scripts/check_gate_plan.py --repo .

Issue #201, ADR 0.0.0021. Ligado em `make docs-check`.

---

**Por que existe.** O ADR 0.0.0021 trocou o `make check` antes de todo commit
por um plano: a tabela "Plano de gates" da §1 do `technical.md` diz depois de
quais Tasks o gate completo precisa estar verde, de 1 a 3 pontos por Stage, o
de saída incluído (regra em `docs/PIPELINE.md` §9.6). Sem este script, um
`technical.md` sem a seção, ou com a tabela do template ainda em branco, passa
no `make docs-check`; só a revisão humana do technical o pegaria.

**O que ele confere (a forma, não o mérito).** Em cada
`docs/stages/<N.M-slug>/technical.md` fora do corte e fora de `draft`:

1. a §1 (`## 1. ...`) tem o título `### Plano de gates`;
2. a subseção tem a tabela com o cabeçalho do template,
   `| # | Depois da Task | Motivo |`, e pelo menos uma linha;
3. as linhas são numeradas 1, 2, 3... na ordem, sem buraco;
4. toda célula está preenchida e nenhuma é o marcador do template
   (`<...>`): um ponto sem motivo é um ponto sem plano;
5. um dos pontos é o de saída: a palavra "saída" (ou "saida") numa das
   células de "Depois da Task" ou "Motivo", como o template sugere
   (`"saída"`, `gate de saída (§3)`);
6. do 4º ponto em diante, o motivo não é "por segurança" (ou "to be safe"):
   a §9.6 diz que isso não justifica um ponto extra.

Se o motivo diz de fato qual quebra o ponto pega e por que o seguinte pegaria
tarde é julgamento: fica com o gate do technical (RUNBOOK Passo 7, Checkpoint
B) e com a auditoria.

**O corte.** As Stages cujo `technical.md` foi aprovado antes do merge do ADR
0.0.0021 em `develop` não têm plano e não devem ganhar um (ADR 0.0.0021,
Decisão 11). Elas estão em `LEGACY_STAGES`, uma lista fechada de nomes de
pasta. A lista não cresce: o teste trava o conjunto exato. Por que uma lista e
não uma data:

- a data do commit `stage N.M: technical approved` precisa do histórico do git,
  e a Stage 4.4 foi aprovada 26 segundos antes do merge do ADR (17:23:14 e
  17:23:40 de 2026-11-16): um corte por data depende do segundo e do fuso;
- o `created_at` do frontmatter da 4.4 é o próprio dia do merge, e o campo é
  editável à mão;
- um marcador ("só confere quem tem a seção") isenta justamente o technical
  que esqueceu a seção.

Pasta nova em `docs/stages/` não está na lista, então é conferida. Stage
renomeada sai da lista pelo nome antigo: o teste que exige a pasta de cada nome
reprova, e a lista troca o nome (não cresce). Stage sem pasta ou sem
`technical.md` (`draft` no roadmap) não tem o que conferir.

**O `technical.md` em `draft` fica de fora.** O scaffold da Stage cria o
technical com o template em branco e `status: draft`, e a Fase 3B o preenche
até o Checkpoint B. Conferir o rascunho deixaria o `make docs-check` vermelho
durante toda a escrita do plano. O gate morde quando o technical sai de `draft`
(o commit `stage N.M: technical approved`), antes da primeira Task.

**Tolerância de escrita.** Título e cabeçalho comparam sem diferença de
maiúsculas; a linha separadora aceita alinhamento (`|:-|`, `|--:|`); "saída"
vale em qualquer caixa e sem acento. O resto é a forma literal do template.

Códigos de saída:
  0  todo technical fora do corte traz o plano na forma do template
  1  há technical sem plano ou com plano fora da forma (arquivo:linha + motivo)
  2  nenhum `technical.md` encontrado (fail closed: `--repo` errado)
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

TECHNICAL_GLOB = "docs/stages/*/technical.md"

# As Stages aprovadas antes do merge do ADR 0.0.0021 (PR #192, 2026-11-16): as 20
# que estavam em `docs/stages/` e as três em execução no merge (2.7, 3.11 e 4.4,
# ADR 0.0.0021 Decisão 11). Lista fechada: não se adiciona Stage aqui. Parecida, mas
# de outra regra e outra data: `LEGACY_CHECKPOINT_STAGES` em
# `scripts/check_technical_postexec.py` (disposições dos Checkpoints, issue #210,
# com a 3.10) — as duas não se unificam. Uma terceira, por registro e não por Stage:
# `LEGACY_RECORDS` em `scripts/check_decision_records.py` (campo Verificado, #212).
LEGACY_STAGES: frozenset[str] = frozenset(
    {
        "1.1-bootstrap",
        "1.2-ci",
        "2.1-identity-domain",
        "2.2-identity-application",
        "2.3-identity-persistence",
        "2.4-identity-http",
        "2.5-email-invite",
        "2.6-identity-unit-of-work",
        "2.7-identity-application-authorization",
        "3.1-staff-domain",
        "3.2-staff-application",
        "3.3-staff-persistence",
        "3.4-staff-access-scope",
        "3.5-employee-login-link",
        "3.6-staff-http",
        "3.7-application-authorization",
        "3.8-termination-access-scope",
        "3.9-error-hierarchy",
        "3.11-job-function-unit-enablement",
        "4.1-scheduling-domain",
        "4.2-validation-policies",
        "4.3-scheduling-application",
        "4.4-scheduling-persistence",
    }
)

PLAN_HEADING = "### Plano de gates"
# O cabeçalho da tabela do template `docs/templates/stage-technical.md`.
TABLE_HEADER = ("#", "Depois da Task", "Motivo")
BUDGET = 3

_SECTION_ONE = re.compile(r"^## 1\.")
_SECTION = re.compile(r"^## ")
_SUBSECTION = re.compile(r"^#{2,3} ")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")
# O `status` do frontmatter (o bloco entre as duas primeiras linhas `---`).
_DRAFT_STATUS = re.compile(r"^status:\s*draft\s*(?:#.*)?$", re.MULTILINE)
# Barra escapada (`\|`) é texto dentro da célula, não divisa.
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_PLACEHOLDER = re.compile(r"^<.*>$")
_EXIT = re.compile(r"sa[ií]da", re.IGNORECASE)
# "Por segurança" não justifica ponto extra (docs/PIPELINE.md §9.6).
_NOT_A_REASON = re.compile(
    r"^\W*(?:por (?:seguran[cç]a|precau[cç][aã]o)|to be safe|just in case)\W*$", re.IGNORECASE
)


@dataclass(frozen=True)
class PlanRow:
    """Uma linha da tabela do plano: o número, o ponto e o motivo, com a linha do arquivo."""

    line: int
    number: str
    after: str
    reason: str


def technical_files(repo_root: Path) -> list[Path]:
    """Todo `technical.md` de `docs/stages/`, em ordem."""
    return sorted(path for path in repo_root.glob(TECHNICAL_GLOB) if path.is_file())


def is_draft(text: str) -> bool:
    """O technical ainda está em `status: draft` no frontmatter (o plano em escrita)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return False
    return bool(_DRAFT_STATUS.search("\n".join(lines[1:end])))


def _unfenced(lines: list[str]) -> list[tuple[int, str]]:
    """As linhas fora de bloco cercado, com o número (1-based): título em exemplo não conta."""
    kept: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(lines, 1):
        match = _FENCE.match(line)
        if fence is None and match:
            fence = match.group(1)
            continue
        if fence is not None:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
                fence = None
            continue
        kept.append((number, line.rstrip()))
    return kept


def _cells(line: str) -> list[str]:
    """As células de uma linha de tabela markdown, sem as barras das pontas."""
    body = line.strip().removeprefix("|")
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in _CELL_SPLIT.split(body)]


def plan_section(text: str) -> tuple[int, list[tuple[int, str]]] | None:
    """O título do plano dentro da §1 e as linhas da subseção, ou None se não há."""
    lines = _unfenced(text.splitlines())
    in_section_one = False
    for index, (number, line) in enumerate(lines):
        if _SECTION_ONE.match(line):
            in_section_one = True
            continue
        if in_section_one and _SECTION.match(line):
            return None
        if in_section_one and line.casefold() == PLAN_HEADING.casefold():
            body: list[tuple[int, str]] = []
            for item in lines[index + 1 :]:
                if _SUBSECTION.match(item[1]):
                    break
                body.append(item)
            return number, body
    return None


def plan_problems(text: str) -> list[tuple[int, str]]:
    """O que falta ao plano de gates de um technical, como (linha, motivo)."""
    section = plan_section(text)
    if section is None:
        return [
            (
                1,
                f"falta o título '{PLAN_HEADING}' na §1 (ADR 0.0.0021; forma em "
                "docs/templates/stage-technical.md)",
            )
        ]
    heading_line, body = section

    table = [(number, line) for number, line in body if line.lstrip().startswith("|")]
    if not table or tuple(cell.casefold() for cell in _cells(table[0][1])) != tuple(
        cell.casefold() for cell in TABLE_HEADER
    ):
        return [
            (
                heading_line,
                "o plano de gates não tem a tabela do template: cabeçalho "
                f"'| {' | '.join(TABLE_HEADER)} |'",
            )
        ]

    rows: list[PlanRow] = []
    for number, line in table[1:]:
        cells = _cells(line)
        if all(_SEPARATOR_CELL.match(cell) for cell in cells):
            continue
        if len(cells) > len(TABLE_HEADER):
            return [(number, f"linha do plano com {len(cells)} células; a tabela tem 3")]
        cells += [""] * (len(TABLE_HEADER) - len(cells))
        rows.append(PlanRow(number, cells[0], cells[1], cells[2]))

    if not rows:
        return [(heading_line, "o plano de gates não tem nenhum ponto; o de saída é obrigatório")]

    found: list[tuple[int, str]] = []
    for position, row in enumerate(rows, 1):
        if row.number != str(position):
            found.append(
                (row.line, f"ponto numerado '{row.number}'; esperado {position} (1, 2, 3...)")
            )
        for label, cell in (("Depois da Task", row.after), ("Motivo", row.reason)):
            if not cell or _PLACEHOLDER.match(cell):
                found.append((row.line, f"ponto {position} sem '{label}' preenchido"))
        if position > BUDGET and _NOT_A_REASON.match(row.reason):
            found.append(
                (
                    row.line,
                    f"ponto {position} acima do orçamento de {BUDGET} sem justificativa: "
                    "'por segurança' não justifica (docs/PIPELINE.md §9.6)",
                )
            )
    if not any(_EXIT.search(row.after) or _EXIT.search(row.reason) for row in rows):
        found.append(
            (heading_line, "nenhum ponto é o de saída: o gate de saída é sempre um deles (§9.6)")
        )
    return found


def problems(repo_root: Path) -> list[str]:
    """Todo technical fora do corte com plano ausente ou fora da forma."""
    files = technical_files(repo_root)
    if not files:
        return [f"FATAL: nenhum technical.md em {repo_root} (glob: {TECHNICAL_GLOB})"]

    found: list[str] = []
    for path in files:
        if path.parent.name in LEGACY_STAGES:
            continue
        text = path.read_text(encoding="utf-8-sig")
        if is_draft(text):
            continue
        rel = path.relative_to(repo_root).as_posix()
        for line, reason in plan_problems(text):
            found.append(f"{rel}:{line}: {reason}")
    return found


def main() -> int:
    """Varre os technicals e reprova plano de gates ausente ou fora da forma do template."""
    parser = argparse.ArgumentParser(
        description=(
            "Reprova technical.md novo sem plano de gates na forma do template"
            " (issue #201, ADR 0.0.0021)"
        )
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    found = problems(Path(args.repo).resolve())
    if found and found[0].startswith("FATAL:"):
        print(f"check_gate_plan: {found[0]}", file=sys.stderr)
        return 2
    if found:
        print(f"check_gate_plan: {len(found)} problema(s):\n", file=sys.stderr)
        for problem in found:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("check_gate_plan: todo technical fora do corte traz o plano de gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

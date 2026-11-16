"""Guard: regra aposentada não volta aos docs normativos, e a casa da regra nova existe.

Uso:
    python scripts/check_docs_pointers.py
    python scripts/check_docs_pointers.py --repo .

Issue #163, ADR 0.0.0021. Ligado em `make docs-check`. É o guard mecânico que a
"Regra do eco" de `docs/CONVENTIONS.md` §0 previa.

---

**Por que existe.** Declarar uma fonte única num doc não impede que outro doc
continue com a paráfrase antiga. Quem executa lê o texto que está no ponto de
uso (o prompt, o runbook, o template), não o doc que se diz dono da regra. Uma
regra aposentada que sobrevive num prompt continua sendo cumprida.

**As duas tabelas.**

1. `RETIRED_RULES`: frase de regra aposentada que os docs normativos não podem
   trazer. Cada entrada nasce de uma regra que foi de fato aposentada por um
   ADR, com a frase que os docs traziam. Hoje há uma: o `make check` completo
   amarrado a todo commit ou a toda Task, trocado pelo plano de gates.
2. `REQUIRED_HEADINGS`: título que precisa existir, porque outros docs apontam
   para ele. Hoje são as duas casas do plano de gates: a seção do PIPELINE que
   é a fonte única e a seção do template onde o technical.md lista os pontos.

**O que é varrido.** Os docs que alguém segue para trabalhar: `CLAUDE.md`,
`README.md`, a raiz de `docs/` (sem descer), `docs/runbooks/`,
`docs/templates/`, as skills e os subagentes de `.claude/` e o template de PR.
Bloco cercado entra: o prompt de Stage inteiro mora dentro de uma cerca.

**O que fica fora, de propósito.** `docs/adr/`, `docs/stages/`, `docs/audits/`
e `docs/domain/` registram o que era verdade quando foram escritos. O ADR que
aposenta a regra precisa poder citá-la.

**A frase pode estar quebrada em duas linhas.** A do PROMPT-stage estava
(`make check` verde / antes de todo commit). Por isso a busca corre sobre o
parágrafo com as quebras de linha, o recuo e o `>` de citação trocados por um
espaço. Linha em branco separa parágrafos e a frase não a atravessa.

**Negação também reprova.** "Não rode o `make check` antes de todo commit" traz
a frase e é reprovada. O doc normativo diz a regra nova e aponta o ADR; a regra
antiga fica descrita no ADR.

**Manutenção.**

- Entrada nova exige evidência: uma regra aposentada por ADR e a frase que
  sobrevivia. Não se adiciona padrão por precaução.
- Se um padrão existente deveria ter pego uma paráfrase, alarga-se o padrão.
- Padrão frouxo dispara em prosa legítima e ensina a ignorar o gate. Cada
  padrão tem, no teste, as frases legítimas que ele não pode pegar.

Códigos de saída:
  0  nenhuma regra aposentada e todo título exigido presente
  1  há regra aposentada ou título ausente (arquivo:linha + motivo)
  2  nenhum doc normativo encontrado (fail closed: `--repo` errado)
"""

import argparse
import re
import sys
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

SCANNED_GLOBS = (
    "CLAUDE.md",
    "README.md",
    "docs/*.md",
    "docs/runbooks/*.md",
    "docs/templates/*.md",
    ".claude/skills/**/*.md",
    ".claude/agents/*.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)


@dataclass(frozen=True)
class RetiredRule:
    """Frase de uma regra aposentada, com o que dizer a quem a escreveu."""

    pattern: re.Pattern[str]
    reason: str


@dataclass(frozen=True)
class RequiredHeading:
    """Título que outros docs apontam e que, por isso, precisa existir."""

    path: str
    heading: str
    reason: str


# `make check`, com a crase e o negrito que os docs põem em volta, e os adjetivos
# que já apareceram entre o comando e a amarração.
_GATE = r"make\s+check`?[\s*]*(?:(?:completo|verde|green)[\s*]*)*"
# A amarração a todo commit ou a toda Task, em português e em inglês (as skills
# são escritas em inglês).
_EVERY_COMMIT = (
    r"(?:antes\s+de\s+(?:todo|cada|qualquer)\s+(?:commit|task)"
    r"|(?:por|a\s+cada|em\s+(?:todo|cada))\s+(?:commit|task)"
    r"|(?:before|on|after)\s+(?:every|each)\s+(?:commit|task)"
    r"|per\s+(?:commit|task))\b"
)
# A ordem invertida só com o verbo de mando colado: "a cada Task, porque o
# `make check` roda no Actions" é prosa legítima do PROMPT-stage.
_EVERY_COMMIT_FIRST = (
    r"antes\s+de\s+(?:todo|cada|qualquer)\s+commit,?\s+"
    r"(?:rodar?|rode|executar?|execute)\s+(?:o\s+)?\**`?make\s+check"
)

RETIRED_RULES: tuple[RetiredRule, ...] = (
    RetiredRule(
        # Issue #163: o PROMPT-stage (Fase 4, passo 5) mandava "`make check`
        # verde antes de todo commit" e o PROMPT-step repetia "`make check` por
        # commit" na tabela de fases.
        pattern=re.compile(f"{_GATE}{_EVERY_COMMIT}|{_EVERY_COMMIT_FIRST}", re.IGNORECASE),
        reason=(
            "`make check` completo amarrado a todo commit ou a toda Task: regra aposentada "
            "pelo ADR 0.0.0021. Por Task rodam só os testes dela; o `make check` completo "
            "roda nos 1 a 3 pontos do plano de gates (docs/PIPELINE.md §9.6)"
        ),
    ),
)

REQUIRED_HEADINGS: tuple[RequiredHeading, ...] = (
    RequiredHeading(
        path="docs/PIPELINE.md",
        heading="### 9.6 Plano de gates",
        reason=(
            "fonte única do plano de gates (ADR 0.0.0021): RUNBOOK, PROMPTs e template "
            "apontam para a §9.6"
        ),
    ),
    RequiredHeading(
        path="docs/templates/stage-technical.md",
        heading="### Plano de gates",
        reason=(
            "seção da §1 em que o technical.md lista os pontos de `make check` "
            "(ADR 0.0.0021); o próprio template linka para ela"
        ),
    ),
)

# Recuo e `>` de citação no começo da linha: somem antes da busca.
_LINE_PREFIX = re.compile(r"^[\s>]*")
# Separa parágrafos no texto achatado. Não é espaço, então `\s` não o atravessa.
_PARAGRAPH_BREAK = "\x00"


def normative_files(repo_root: Path) -> list[Path]:
    """Os docs normativos que existem, na ordem dos globs, sem repetição."""
    found: dict[Path, None] = {}
    for pattern in SCANNED_GLOBS:
        for path in sorted(repo_root.glob(pattern)):
            if path.is_file():
                found.setdefault(path, None)
    return list(found)


def flatten(text: str) -> tuple[str, list[int]]:
    """O texto numa linha só, e onde cada linha original começa nele.

    Quebra de linha, recuo e `>` de citação viram um espaço, para a frase
    quebrada em duas linhas ser achada. Linha em branco vira um separador que
    nenhum padrão atravessa.
    """
    parts: list[str] = []
    starts: list[int] = []
    position = 0
    for line in text.splitlines():
        content = _LINE_PREFIX.sub("", line).rstrip()
        piece = (content or _PARAGRAPH_BREAK) + " "
        starts.append(position)
        parts.append(piece)
        position += len(piece)
    return "".join(parts), starts


def retired_rules_in(text: str) -> list[tuple[int, str]]:
    """Cada regra aposentada achada no texto, como (linha em que começa, motivo)."""
    flat, starts = flatten(text)
    found: list[tuple[int, str]] = []
    for rule in RETIRED_RULES:
        for match in rule.pattern.finditer(flat):
            found.append((bisect_right(starts, match.start()), rule.reason))
    return sorted(found)


def missing_headings(repo_root: Path) -> list[str]:
    """Os títulos exigidos que sumiram, como `arquivo: motivo`."""
    problems: list[str] = []
    for required in REQUIRED_HEADINGS:
        path = repo_root / required.path
        if not path.is_file():
            problems.append(f"{required.path}: arquivo não existe; era a {required.reason}")
            continue
        lines = {line.rstrip() for line in path.read_text(encoding="utf-8-sig").splitlines()}
        if required.heading not in lines:
            problems.append(
                f"{required.path}: falta o título '{required.heading}', {required.reason}"
            )
    return problems


def problems(repo_root: Path) -> list[str]:
    """Toda regra aposentada nos docs normativos e todo título exigido ausente."""
    files = normative_files(repo_root)
    if not files:
        return [f"FATAL: nenhum doc normativo em {repo_root} (globs: {', '.join(SCANNED_GLOBS)})"]

    found: list[str] = []
    for path in files:
        rel = path.relative_to(repo_root).as_posix()
        for line, reason in retired_rules_in(path.read_text(encoding="utf-8-sig")):
            found.append(f"{rel}:{line}: {reason}")
    found.extend(missing_headings(repo_root))
    return found


def main() -> int:
    """Varre os docs normativos e reprova regra aposentada ou título exigido ausente."""
    parser = argparse.ArgumentParser(
        description=(
            "Reprova regra aposentada nos docs normativos e título exigido ausente"
            " (issue #163, ADR 0.0.0021)"
        )
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    found = problems(Path(args.repo).resolve())
    if found and found[0].startswith("FATAL:"):
        print(f"check_docs_pointers: {found[0]}", file=sys.stderr)
        return 2
    if found:
        print(f"check_docs_pointers: {len(found)} problema(s):\n", file=sys.stderr)
        for problem in found:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("check_docs_pointers: nenhuma regra aposentada nos docs normativos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

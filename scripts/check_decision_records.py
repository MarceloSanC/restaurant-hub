"""Guard: todo registro `[decision:E|C]` traz o campo `Verificado:` do vocabulário fechado.

Uso:
    python scripts/check_decision_records.py
    python scripts/check_decision_records.py --repo .

Issue #212. Ligado em `make docs-check`.

---

**Por que existe.** A skill `evidence-resolution` §5 grava cada fork E/C num
registro com o campo `Verificado:`, de vocabulário fechado: `sustenta`,
`parcial→corrigido` ou `não verificado (§4.2)`. O concept da Stage 2.7 foi
aprovado com `Verificado: ver §7 do technical (evidence-verifier, Checkpoint A)`
quando o `evidence-verifier` ainda não tinha rodado (auditoria da 2.7, PR #187):
o campo afirmava uma verificação que não existia, e nada no `make docs-check`
olhava para ele.

**O que é um registro.** Uma linha que começa por `[decision:E]` ou
`[decision:C]` — depois de recuo, `>`, marcador de título (`###`), de lista
(`-`, `1.`) e crase opcionais — e as linhas que a seguem até a primeira linha em
branco, cerca, título, item de lista ou registro novo. Só conta como registro o
bloco que tem o campo `Escolha:`, o primeiro do formato do §5: a tag no começo de
uma frase corrida (`[decision:C] rung 1 — ...` no corpo de um ADR) é menção, não
registro.

**O que ele confere (a forma, não o mérito).** Em todo registro de
`docs/stages/*/concept.md` fora de `draft` e de `docs/adr/*.md`:

1. há exatamente um campo `Verificado:` (em linha própria ou no meio da linha, como
   no registro de uma linha só que separa os campos com ` · `; com ou sem negrito no
   rótulo; o rótulo em outra caixa não conta, e o registro fica sem o campo);
2. o valor começa por um dos três termos do vocabulário, escritos como no §5, e o
   termo não continua em letra (`sustentado` não é `sustenta`) nem em `|` (a linha
   do template, `sustenta | parcial→corrigido | ...`, copiada sem escolher). Crase em volta do
   valor é tolerada; caixa, acento e a seta `→` não (`parcial->corrigido` reprova).
   O que vem depois do termo (quem verificou, quando, por que o §4.2 não se aplica)
   é livre, e acaba no próximo ` · `.

Se `não verificado (§4.2)` é legítimo — a decisão fica fora das quatro classes do
§4.2 (port, schema persistido, contrato OpenAPI, regra de segurança/tenant) — é
julgamento: não se decide por texto. Quem cobra é o Checkpoint A
(`docs/PROMPT-stage-single-session.md`, Fase 3A) e a `stage-audit` (Fase C).

**Cercas.** Cerca nua (```` ``` ```` sem linguagem) é o contêiner do registro: é a
forma do próprio template do §5, e os registros das Stages 2.7 e 3.7 e dos ADRs
0.0.0020 a 0.0.0022 vivem nela. Cerca com linguagem (```` ```python ````,
```` ```markdown ````, ```` ```text ````) é código ou citação e fica de fora.

**O concept em `draft` fica de fora.** O campo só é final no Checkpoint A, que é
quando o `evidence-verifier` roda (§4.2): conferir o rascunho deixaria o
`make docs-check` vermelho durante a Fase 3A. O gate morde no commit
`stage N.M: conceptual approved` (concept em `done`). O ADR não tem rascunho no
processo (nasce `accepted`, PROMPT-stage Fase 3A passo 6) e é conferido sempre.

**O corte.** Concept de Stage `done` é registro histórico (CONVENTIONS §5) e o
corpo de um ADR `accepted` não se reescreve (só errata e nota datada): os
registros anteriores à regra que reprovariam ficam em `LEGACY_RECORDS`, uma lista
fechada de pares (arquivo, id do registro). Reescrevê-los com um valor do
vocabulário seria afirmar hoje uma verificação que ninguém fez. A lista não
cresce, e o teste exige que cada par ainda exista e ainda reprove sem o corte:
registro corrigido sai da lista.

Códigos de saída:
  0  todo registro fora do corte traz `Verificado:` do vocabulário
  1  há registro sem o campo, com o campo repetido ou fora do vocabulário
  2  nenhum concept nem ADR encontrado (fail closed: `--repo` errado)
"""

import argparse
import io
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CONCEPT_GLOB = "docs/stages/*/concept.md"
ADR_GLOB = "docs/adr/*.md"

# O vocabulário de `.claude/skills/evidence-resolution/SKILL.md` §5, escrito como lá.
VOCABULARY: tuple[str, ...] = ("sustenta", "parcial→corrigido", "não verificado (§4.2)")

# Os registros anteriores à issue #212 que reprovariam (medição de 2026-11-23 em
# `develop` 1d95ab8): 19 sem o campo e 1 fora do vocabulário (ADR 0.0.0022 D1,
# "não se aplica o §4.2"). Todos em concept de Stage `done` ou em ADR `accepted`.
# Lista fechada: não se acrescenta registro aqui. Parecidas, mas de outras regras e
# outras datas: `LEGACY_STAGES` em `scripts/check_gate_plan.py` (plano de gates,
# ADR 0.0.0021) e `LEGACY_CHECKPOINT_STAGES` em `scripts/check_technical_postexec.py`
# (disposições dos Checkpoints, issue #210) — as três não se unificam.
LEGACY_RECORDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("docs/adr/0_0_0012-cite-the-roadmap-by-stable-anchor.md", "0.0.0012"),
        ("docs/adr/0_0_0017-cite-domain-docs-by-stable-anchor.md", "0.0.0017"),
        ("docs/adr/0_0_0019-cite-overview-adrs-and-code-by-stable-anchor.md", "0.0.0019"),
        ("docs/adr/0_0_0022-audit-session-closes-the-pr-it-validated.md", "D1"),
        ("docs/adr/2_7_0001-identity-authorizes-through-a-narrow-port.md", "2.7.0001-2"),
        ("docs/stages/3.11-job-function-unit-enablement/concept.md", "D8"),
        ("docs/stages/3.7-application-authorization/concept.md", "D1"),
        ("docs/stages/3.7-application-authorization/concept.md", "D2"),
        ("docs/stages/3.7-application-authorization/concept.md", "D3"),
        ("docs/stages/4.2-validation-policies/concept.md", "D1"),
        ("docs/stages/4.2-validation-policies/concept.md", "D2"),
        ("docs/stages/4.2-validation-policies/concept.md", "D3"),
        ("docs/stages/4.2-validation-policies/concept.md", "D4"),
        ("docs/stages/4.2-validation-policies/concept.md", "D5"),
        ("docs/stages/4.2-validation-policies/concept.md", "D6"),
        ("docs/stages/4.2-validation-policies/concept.md", "D7"),
        ("docs/stages/4.2-validation-policies/concept.md", "D8"),
        ("docs/stages/4.2-validation-policies/concept.md", "D9"),
        ("docs/stages/4.2-validation-policies/concept.md", "D10"),
        ("docs/stages/4.2-validation-policies/concept.md", "D11"),
    }
)

# Abertura ou fechamento de cerca, com a linguagem depois dela.
_FENCE = re.compile(r"^[\s>]*(`{3,}|~{3,})\s*(\S*)")
# Começo de registro: prefixos de markdown opcionais, a tag e o resto da linha.
_HEADER = re.compile(
    r"^[\s>]*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)?`?\[decision:[EC]\]\s*(?P<rest>.*)$"
)
# O id do registro: o que vem depois da tag até o travessão (ou o fim da linha).
_RECORD_ID = re.compile(r"^(?P<id>[^\s—`]+)")
_HEADING = re.compile(r"^[\s>]*#{1,6}\s")
_LIST_ITEM = re.compile(r"^[\s>]*(?:[-*+]|\d+[.)])\s")
_LINE_PREFIX = re.compile(r"^[\s>]*")
# O campo `Escolha:` (com ou sem negrito, em qualquer caixa) marca o registro do §5:
# na dúvida, o bloco é registro e é conferido.
_CHOICE_FIELD = re.compile(r"\bEscolha(?:\*\*)?\s*:", re.IGNORECASE)
# O rótulo `Verificado:`, com ou sem negrito, em qualquer ponto da linha (registro de uma
# linha só separa os campos com ` · `). Rótulo em outra caixa não conta: é campo ausente.
_VERIFIED_LABEL = re.compile(r"\bVerificado(?:\*\*)?\s*:(?:\*\*)?\s*")
_FIELD_SEPARATOR = "·"
# O `status` do frontmatter (o bloco entre as duas primeiras linhas `---`).
_DRAFT_STATUS = re.compile(r"^status:\s*draft\s*(?:#.*)?$", re.MULTILINE)


@dataclass(frozen=True)
class DecisionRecord:
    """Um registro `[decision:E|C]`: a linha do cabeçalho, o id e as linhas do bloco."""

    line: int
    record_id: str
    lines: tuple[str, ...]


def scanned_files(repo_root: Path) -> list[Path]:
    """Todo `concept.md` de Stage e todo ADR, em ordem."""
    found = [*repo_root.glob(CONCEPT_GLOB), *repo_root.glob(ADR_GLOB)]
    return sorted(path for path in found if path.is_file())


def is_draft(text: str) -> bool:
    """O doc ainda está em `status: draft` no frontmatter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return False
    return bool(_DRAFT_STATUS.search("\n".join(lines[1:end])))


def _visible(lines: list[str]) -> list[tuple[int, str, bool]]:
    """Cada linha fora de cerca com linguagem: (número 1-based, texto, é linha de cerca)."""
    kept: list[tuple[int, str, bool]] = []
    fence: str | None = None
    quoted = False
    for number, line in enumerate(lines, 1):
        match = _FENCE.match(line)
        if fence is None and match:
            fence, quoted = match.group(1), bool(match.group(2))
            if not quoted:
                kept.append((number, line, True))
            continue
        if fence is not None and match and not match.group(2):
            marker = match.group(1)
            if marker[0] == fence[0] and len(marker) >= len(fence):
                if not quoted:
                    kept.append((number, line, True))
                fence, quoted = None, False
                continue
        if not quoted:
            kept.append((number, line, False))
    return kept


def records(text: str) -> list[DecisionRecord]:
    """Os registros `[decision:E|C]` do texto (só os blocos com `Escolha:`)."""
    visible = _visible(text.splitlines())
    found: list[DecisionRecord] = []
    index = 0
    while index < len(visible):
        number, line, is_fence = visible[index]
        header = None if is_fence else _HEADER.match(line)
        index += 1
        if header is None:
            continue
        block = [header.group("rest")]
        while index < len(visible):
            _, follow, follow_is_fence = visible[index]
            if (
                follow_is_fence
                or not follow.strip()
                or _HEADING.match(follow)
                or _LIST_ITEM.match(follow)
                or _HEADER.match(follow)
            ):
                break
            block.append(_LINE_PREFIX.sub("", follow))
            index += 1
        if not any(_CHOICE_FIELD.search(item) for item in block):
            continue
        id_match = _RECORD_ID.match(header.group("rest"))
        record_id = id_match.group("id") if id_match else "?"
        found.append(DecisionRecord(number, record_id, tuple(block)))
    return found


def verified_values(record: DecisionRecord) -> list[str]:
    """Os valores dos campos `Verificado:` do registro, na ordem."""
    values: list[str] = []
    for line in record.lines:
        for match in _VERIFIED_LABEL.finditer(line):
            value = line[match.end() :].split(_FIELD_SEPARATOR, 1)[0]
            values.append(value.strip().strip("`").strip())
    return values


def in_vocabulary(value: str) -> bool:
    """O valor começa por um termo do vocabulário, e o termo não continua em letra.

    O termo seguido de `|` é a linha do template do §5 copiada sem escolher.
    """
    normalized = unicodedata.normalize("NFC", value)
    for term in VOCABULARY:
        if normalized.startswith(term):
            rest = normalized[len(term) :]
            if not rest:
                return True
            return not rest[0].isalnum() and not rest.lstrip().startswith("|")
    return False


def record_problem(record: DecisionRecord) -> str | None:
    """O que está errado no campo `Verificado:` do registro, ou None."""
    values = verified_values(record)
    vocabulary = " | ".join(VOCABULARY)
    if not values:
        return f"registro {record.record_id} sem o campo 'Verificado: {vocabulary}'"
    if len(values) > 1:
        return f"registro {record.record_id} com {len(values)} campos 'Verificado:'; é um só"
    if not in_vocabulary(values[0]):
        return (
            f"registro {record.record_id}: 'Verificado: {values[0][:60]}' fora do vocabulário "
            f"({vocabulary}; evidence-resolution §5)"
        )
    return None


def file_problems(text: str, rel: str, legacy: frozenset[tuple[str, str]]) -> list[str]:
    """Os registros do arquivo que reprovam, fora do corte, como 'arquivo:linha: motivo'."""
    found: list[str] = []
    for record in records(text):
        if (rel, record.record_id) in legacy:
            continue
        problem = record_problem(record)
        if problem is not None:
            found.append(f"{rel}:{record.line}: {problem}")
    return found


def problems(repo_root: Path, legacy: frozenset[tuple[str, str]] = LEGACY_RECORDS) -> list[str]:
    """Todo registro fora do corte sem `Verificado:` do vocabulário."""
    files = scanned_files(repo_root)
    if not files:
        return [f"FATAL: nenhum concept nem ADR em {repo_root} ({CONCEPT_GLOB}, {ADR_GLOB})"]

    found: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8-sig")
        if path.name == "concept.md" and is_draft(text):
            continue
        found.extend(file_problems(text, path.relative_to(repo_root).as_posix(), legacy))
    return found


def main() -> int:
    """Varre concepts e ADRs e reprova `Verificado:` ausente ou fora do vocabulário."""
    parser = argparse.ArgumentParser(
        description=(
            "Reprova registro [decision:E|C] sem 'Verificado:' do vocabulário da"
            " evidence-resolution §5 (issue #212)"
        )
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()
    # O `→` do vocabulário não existe no cp1252 do console do Windows.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="backslashreplace")

    found = problems(Path(args.repo).resolve())
    if found and found[0].startswith("FATAL:"):
        print(f"check_decision_records: {found[0]}", file=sys.stderr)
        return 2
    if found:
        print(f"check_decision_records: {len(found)} problema(s):\n", file=sys.stderr)
        for problem in found:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print("check_decision_records: todo registro fora do corte traz 'Verificado:' do vocabulário.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

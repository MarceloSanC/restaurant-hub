"""Valida que o subject do commit segue a convenção do projeto.

Ligado como hook `commit-msg` no `.pre-commit-config.yaml`. Recebe o caminho
do arquivo da mensagem de commit como primeiro argumento; lê só a primeira
linha (o subject) e a confere contra:

  (1) Mensagens reservadas de gate (CONVENTIONS.md §4(b)).
  (2) Conventional Commits em português com escopo obrigatório (ASCII/kebab)
      e marca de Task opcional no fim, `[<dono>/<posição>]` (CONVENTIONS.md
      §4(a), subseção "Marca de Task"): dono `N.M` (Stage) ou `#<num>`
      (issue avulsa); posição `task-NN`, `task-NN-fix`, `task-NN-extra` ou
      `--`.

**A marca é opcional; a malformada é recusada.** Um subject que termina em `]`
precisa terminar numa marca da gramática. Até a issue #34, o grupo da marca era
opcional e a descrição engolia qualquer `[...]` que não casasse com ele:
`[4.1/tsk-3]` e `[41/--]` passavam como texto livre, sem validação nenhuma.

A descrição aceita qualquer UTF-8 (PT-BR acentuado é o padrão); só o escopo
fica restrito a ASCII/kebab, para não exigir acento no terminal.

O corpo NÃO é validado aqui — a lista de bullets é regra dos docs, cobrada no
code review e não no hook (evita falso positivo em commit trivial, cujo corpo
fica ausente de propósito).

Códigos de saída:
  0  subject OK
  1  subject viola a convenção (motivo impresso no stderr)
  2  argumento ausente ou arquivo da mensagem ilegível
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_TYPES = (
    "feat",
    "fix",
    "refactor",
    "test",
    "docs",
    "chore",
    "perf",
    "style",
    "build",
    "ci",
)

# Reserved subjects — fixed text, NOT Conventional Commits.
RESERVED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^stage \d+\.\d+: (conceptual|technical) (draft|approved)$"),
    re.compile(r"^stage \d+\.\d+: complete$"),
    re.compile(
        r"^docs\((overview|roadmap)\): approved"
        r"(?: \[projects/[a-z0-9._-]+\](?: \(adoption\))?)?$"
    ),
    re.compile(
        r"^chore\((concept|technical)\): revert to draft "
        r"[—-] revision-from-(technical|execution): .+$"
    ),
    re.compile(r"^chore(?:\([a-z0-9._-]+\))?: bootstrap from [a-z0-9._-]+$"),
)

# Marca de Task, `[<dono>/<posição>]` — gramática de CONVENTIONS.md §4(a),
# subseção "Marca de Task" (mudou aqui, atualizar lá). Dono: `N.M` (número da
# Stage) ou `#<num>` (issue avulsa). Posição: `task-NN` (Task do plano),
# `task-NN-fix` (correção da Task NN), `task-NN-extra` (Task acrescentada acima
# do plano) ou `--` (off-task).
TAG_PATTERN = r"(?:\d+\.\d+|#\d+)/(?:task-\d{2}(?:-fix|-extra)?|--)"

# Conventional Commits: <tipo>(<escopo>): <descrição> [marca opcional].
# O escopo é OBRIGATÓRIO aqui (CONVENTIONS.md §4(a), "regra de escopo mínimo");
# as exceções que de fato não têm escopo passam por RESERVED_PATTERNS ou pelos
# prefixos de passagem (merge/revert). A marca, quando vem, fecha o subject,
# separada da descrição por um espaço.
CC_PATTERN = re.compile(
    r"^(?P<type>" + "|".join(ALLOWED_TYPES) + r")"
    r"\((?P<scope>[a-z0-9._-]+)\)"
    r": (?P<desc>\S.*?)"
    r"(?: \[(?P<tag>" + TAG_PATTERN + r")\])?$"
)

# O último grupo `[...]` do subject. Só serve para a recusa mostrar o que foi
# lido como marca — quem decide se a marca é válida é o CC_PATTERN.
_TRAILING_GROUP = re.compile(r"\[[^\[\]]*\]$")

# Allow merges and reverts without further checks.
PASSTHROUGH_PREFIXES = ("Merge ", "Revert ")

MAX_SUBJECT_LEN = 100

# argv esperado: [script_name, commit_msg_path]
_REQUIRED_ARGC = 2


def _format_help() -> str:
    return (
        "\nFormato esperado (um destes):\n"
        "  <tipo>(<escopo>): <descrição em português> [marca opcional]\n"
        f"    onde <tipo> é um de: {', '.join(ALLOWED_TYPES)}\n"
        "    escopo em ASCII/kebab (snake/kebab); descrição livre em PT-BR\n"
        "    marca: [<dono>/<posição>] no fim, separada da descrição por um espaço\n"
        "      dono: N.M (número da Stage) ou #<num> (issue avulsa)\n"
        "      posição: task-NN (Task do plano), task-NN-fix (correção da Task NN),\n"
        "               task-NN-extra (Task acrescentada acima do plano) ou -- (off-task)\n"
        "    exemplos:\n"
        "      feat(ingestion): adicionar S3 source adapter [2.3/task-01]\n"
        "      fix(ingestion): fechar o achado do Checkpoint C [2.3/task-01-fix]\n"
        "      test(ingestion): cobrir o que a auditoria de testes pediu [2.3/task-13-extra]\n"
        "      docs(roadmap): marcar stage 2.3 como done [2.3/--]\n"
        "      docs(conventions): documentar a marca de Task [#34/task-02]\n"
        "      fix(payment.retry): limitar backoff exponencial em 30s\n"
        "\n  Mensagens reservadas de gate (ver docs/CONVENTIONS.md §4(b)):\n"
        "      stage N.M: conceptual draft\n"
        "      stage N.M: conceptual approved\n"
        "      stage N.M: technical draft\n"
        "      stage N.M: technical approved\n"
        "      stage N.M: complete\n"
        "      docs(overview): approved\n"
        "      docs(roadmap): approved\n"
        "      chore(concept): revert to draft — revision-from-technical: <motivo>\n"
        "      chore(technical): revert to draft — revision-from-execution: <motivo>\n"
        "\nRegras completas: docs/CONVENTIONS.md §4 e docs/GIT-WORKFLOW.md §Commits.\n"
    )


def _error(subject: str, reason: str) -> int:
    print("check_commit_msg: rejected commit subject", file=sys.stderr)
    print(f"  subject: {subject!r}", file=sys.stderr)
    print(f"  reason : {reason}", file=sys.stderr)
    print(_format_help(), file=sys.stderr)
    return 1


def _no_match_reason(subject: str) -> str:
    no_scope = re.match(
        r"^(?:" + "|".join(ALLOWED_TYPES) + r"): ",
        subject,
    )
    if no_scope:
        return (
            "escopo ausente — subject precisa ser "
            "`<tipo>(<escopo>): <descrição>` (CONVENTIONS.md §4(a) — "
            "regra de escopo mínimo)"
        )
    return (
        "não bate com Conventional Commits "
        "(`<tipo>(<escopo>): <descrição>`) nem com nenhuma mensagem "
        "reservada de gate"
    )


def _malformed_tag_reason(subject: str) -> str:
    trailing = _TRAILING_GROUP.search(subject)
    read = f" (lido: `{trailing.group(0)}`)" if trailing else ""
    return (
        f"marca de Task inválida no fim do subject{read} — subject que termina "
        "em `]` precisa terminar em `<descrição> [<dono>/<posição>]`: dono `N.M` "
        "ou `#<num>`; posição `task-NN`, `task-NN-fix`, `task-NN-extra` ou `--` "
        '(CONVENTIONS.md §4(a), subseção "Marca de Task")'
    )


def _conventional_commit_reason(subject: str) -> str | None:
    """Motivo para recusar o subject como Conventional Commits, ou None se vale."""
    match = CC_PATTERN.match(subject)
    if match is None:
        return _no_match_reason(subject)

    # Sem esta checagem, a marca malformada vira parte da descrição e o subject
    # passa como se não tivesse marca nenhuma (achado F9 da auditoria da 4.1).
    if match.group("tag") is None and subject.endswith("]"):
        return _malformed_tag_reason(subject)

    return None


def validate_subject(subject: str) -> int:
    if not subject:
        return _error(subject, "empty subject")

    if subject.startswith(PASSTHROUGH_PREFIXES):
        return 0

    if len(subject) > MAX_SUBJECT_LEN:
        return _error(
            subject,
            f"subject too long ({len(subject)} chars; max {MAX_SUBJECT_LEN})",
        )

    if any(pat.match(subject) for pat in RESERVED_PATTERNS):
        return 0

    reason = _conventional_commit_reason(subject)
    return 0 if reason is None else _error(subject, reason)


def main(argv: list[str]) -> int:
    if len(argv) < _REQUIRED_ARGC:
        print(
            "check_commit_msg: missing commit message file argument",
            file=sys.stderr,
        )
        return 2

    msg_path = Path(argv[1])
    try:
        content = msg_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check_commit_msg: cannot read {msg_path}: {exc}", file=sys.stderr)
        return 2

    # Skip lines comencing with `#` (git commentary) when looking for subject.
    subject = ""
    for line in content.splitlines():
        if not line.startswith("#"):
            subject = line
            break

    return validate_subject(subject.rstrip())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Guard: every ADR declares a `bounded_context` drawn from the roadmap.

Wired into `make docs-check`. Each ADR frontmatter carries a
`bounded_context` whose value is one of the bounded contexts the project
actually declares in `docs/roadmap.md` — a new BC keyword cannot be
minted in an ADR.

Why this exists: "ADRs of the same bounded context" is a load-context
step of the Stage flow (`PROMPT-stage-single-session.md`). Without a
first-class field the retrieval is a fragile prose judgment; with it the
same-BC set is a single `grep`. The valid set is **extracted from the
roadmap** (leading token of each `bounded_context:` YAML line), never
hardcoded here, so the two cannot drift.

Rule: global ADRs (`0_0_*`, `1_1_*`) carry `transversal`; every other ADR
inherits the BC of its `context_stage` from the roadmap.

Only the frontmatter block is inspected — a `bounded_context:` mention in
the ADR body (e.g. a frontmatter *example* quoted inside an ADR) is not
the declaration.

Exit codes:
  0  all ADRs valid
  1  violations found (file + reason printed to stderr)
  2  could not derive the valid BC set from the roadmap (fail closed)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROADMAP = REPO_ROOT / "docs" / "roadmap.md"
ADR_GLOB = "docs/adr/*.md"

# Leading token of a `bounded_context:` YAML line (e.g.
# "transversal (spans payments + billing)" -> "transversal").
_BC_LINE = re.compile(r"^bounded_context:\s*([a-z_]+)", re.MULTILINE)


def valid_bounded_contexts() -> set[str]:
    """The set of BC keywords the roadmap declares (single source)."""
    # utf-8-sig: some docs carry a UTF-8 BOM; strip it transparently.
    text = ROADMAP.read_text(encoding="utf-8-sig")
    return set(_BC_LINE.findall(text))


def _frontmatter(text: str) -> list[str] | None:
    """Lines between the first two `---` fences, or None if absent."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i]
    return None


def check_adr(path: Path, valid: set[str]) -> str | None:
    """Return a violation message, or None if the ADR is valid."""
    fm = _frontmatter(path.read_text(encoding="utf-8-sig"))
    rel = path.relative_to(REPO_ROOT)
    if fm is None:
        return f"{rel}: frontmatter YAML ausente ou malformado"
    declared = [line for line in fm if line.startswith("bounded_context:")]
    if not declared:
        return f"{rel}: falta `bounded_context` no frontmatter"
    value = declared[0].split(":", 1)[1].strip()
    if value not in valid:
        return (
            f"{rel}: bounded_context='{value}' nao esta no conjunto do "
            f"roadmap ({', '.join(sorted(valid))})"
        )
    return None


def main() -> int:
    if not ROADMAP.exists():
        print(
            f"check_adr_bounded_context: roadmap ausente em "
            f"{ROADMAP.relative_to(REPO_ROOT)} — nao ha conjunto de BC "
            "para validar (fail closed)",
            file=sys.stderr,
        )
        return 2
    valid = valid_bounded_contexts()
    if not valid:
        print(
            "check_adr_bounded_context: nenhum `bounded_context` no roadmap "
            "— nao ha conjunto valido para validar (fail closed)",
            file=sys.stderr,
        )
        return 2

    violations = [
        msg
        for path in sorted(REPO_ROOT.glob(ADR_GLOB))
        if (msg := check_adr(path, valid)) is not None
    ]

    if violations:
        print("check_adr_bounded_context: ADRs com bounded_context invalido", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

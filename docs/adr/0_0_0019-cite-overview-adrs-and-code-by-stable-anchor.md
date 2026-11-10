---
title: ADR 0.0.0019 — Docs cite the overview, ADRs and code by stable anchor, never by line number
description: Architecture Decision Record
when-use: Reference before citing the overview, an ADR or a code/config file from any doc, before adding an errata banner or a section to an ADR, before renumbering an overview section or rewording a passage another doc quotes, or before changing what make docs-check enforces about those citations
keywords: [adr, process, docs, overview, adr-citation, code-citation, anchor, symbol, line-number, docs-check, gate, issue-154]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-09
adr_id: "0.0.0019"
decision: 'Docs cite the overview by section plus label (`overview.md` §3 › "salvar = publicar"), an ADR by an optional locator plus a quoted passage (ADR 4.1.0003 (c) › "block only for physical impossibility"), and a code or config file by symbol (`employee.py` › `Employee.__post_init__`), never by line number. check_domain_citations.py now also covers the overview; the new check_adr_code_citations.py rejects line numbers after an ADR or a repo file and checks every ADR passage. Code symbols are not resolved, and third-party files, fenced blocks, ADR errata sections and technical §7 stay out.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0019 — Docs cite the overview, ADRs and code by stable anchor, never by line number

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #154 (finding of the PR #151 audit). **Partially supersedes**
[ADR 0.0.0012](./0_0_0012-cite-the-roadmap-by-stable-anchor.md) — the "Limits" sentence that kept
`overview.md` out ("does not grow in the middle on every PR") — and
[ADR 0.0.0017](./0_0_0017-cite-domain-docs-by-stable-anchor.md) — Decision 5's last sentence, which
kept the overview, ADRs and code out. Everything else in both stands.

## Context

1. **Three targets were still cited by line.** After ADRs 0.0.0012 and 0.0.0017, docs still cited
   three targets by line number: the overview, with about 130 citations, mostly in the scheduling domain
   doc and the 4.1 ADRs; ADRs, with about 110, by a locator followed by *"linhas 95–97"*; and code
   or config files, with about 140 references, as `file:line` or as a range after the file name.
   No gate failed on any of them.
2. **They had already drifted.** Issue #129 inserted the kickoff-decision list at the end of
   overview §3 the day this issue opened, so every overview citation below it (§5 to §10) pointed
   about 24 lines too high. The 4.1 technical cited the CLT rule by the numbering from before
   `5edb725`, which had since become the LGPD line. In the 4.1 technical, an `employee.py` range
   no longer held the loop it described even in the commit that wrote it.
3. **Accepted ADRs grow at the top and at the end.** An errata banner goes right under the title and
   a `## Supersessão parcial` section at the end (CONVENTIONS §5), so line citations to an ADR
   drift on every errata.
4. **Each target already had a stable handle.** The overview has numbered `##` sections. The ADRs
   are cited by decision item (`§2`, `(c)`, `§Alternative B`), and quoting the passage is already
   common practice. Code has symbols (`Employee.terminate`, `REQUIRED_FEATURE_DIRS`) and config
   has keys or contracts (`[importlinter:contract:bc-independence]`).

## Decision

`[decision:C] 0.0.0019 — how other docs cite the overview, an ADR and a code file`
Escolha: overview by section + label in the domain-doc gate; ADR by locator + quoted passage, and code
by symbol, in a third gate · Alternativas: one gate for all three; gate only the overview; anchors
without gate; resolve code symbols against HEAD · Degrau (C): 1 (ADRs 0.0.0012 and 0.0.0017 are
the ratified form for the other two targets; their criterion "one script per grammar" decides the
split). Base: issue #154 body; ADR 0.0.0017 §Decision 3 and 5; ADR 0.0.0012 "Limits".
Configuração candidata: nenhuma · Reversível: sim (convert back; drop the gate or the overview entry).

Decided target by target:

1. **Overview — gated, same rule as the domain docs.** Form `` `overview.md` §N › "<passage>" ``
   (section is the `## N.` heading and includes its `###` subsections; label is prose, compared
   without `*`, backticks or `>`). Same grammar as the domain docs, so the overview is a fixed extra
   target of `check_domain_citations.py` instead of a new script (ADR 0.0.0017 Decision 3: one
   script per *grammar*). In the same change, the bare name followed by a number
   (`overview 44/137`, `workforce 120`) became a reference too, and times, month/year and
   `PEP N`/`RFC N` are no longer read as lines. A name inside a code span that continues with a
   space (`` `overview.md 46` ``) is the forbidden form quoted as an example, not a citation, and is
   skipped. ADRs 0.0.0012 and 0.0.0017 use it that way and cannot be edited.
2. **ADR — gated, passage checked, locator free.** Form
   `ADR N.N.NNNN <locator> › "<passage>"`, where the locator is optional and free (`§Decision 2`,
   `(c)`, `§Alternative B`) because ADRs have no single sub-section shape, and the passage is text
   of the ADR. The gate checks that the ADR exists and that each passage is in it.
3. **Code and config — gated, symbol not resolved.** Form `` `<file>` › `<symbol>` ``: a class,
   method, function, constant, test name, Makefile target, YAML key or import-linter contract. A
   line outside any symbol (module docstring, comment) is cited as `__doc__` or by a short quoted
   passage. The gate rejects the line number after a repo file. It does **not** resolve the
   symbol: concepts and technicals of `done` Stages describe the code of their time, and checking
   them against HEAD would fail the history on every refactor. The symbol's value is that it does
   not move when a line is inserted above it, and `git log -S` finds it.
4. **New gate.** `scripts/check_adr_code_citations.py`, in `make docs-check`, over the same files as
   the other two gates. Rule 1, line number after an ADR reference: the full reading of ADRs
   0.0.0012/0.0.0017. Rule 1, line number after a code file: only the number right after the file
   (`x.py:113`, `x.py 113–116`, `x.py (113)`), the word `linha`/`line`, and `#L113`. Prose about
   code counts things ("13 → 15", "sobe de 22 para 34"), and the loose reading flagged dozens of
   counts. Rule 2: every ADR passage resolves.
5. **Out of every gate, with the reason:**
   - **Third-party files** (`engine/base.py` of SQLAlchemy 2.0.51, `fastapi/routing.py`): the
     citation names a pinned version, whose lines never move. A path is a repo file when it is a
     suffix of a repo file, or a bare name of one.
   - **Fenced blocks**: captured output (a traceback's `file:line` frames), not a pointer.
   - **YAML frontmatter**: metadata, not citation.
   - **An ADR's `## Errata` section**: it records the number a pointer *used to* say and the one it
     says now (ADR 3.4.0001, for a composition-root pointer). Rewriting it would erase the fact it
     records, the same reason the technical §7 is out.
   - **The technical §7**, as in ADRs 0.0.0012 and 0.0.0017.
   - **Other targets**: `LAYOUT.md`, Stage concepts/technicals and runbooks cited by line
     (`concept.md 301–308`, `LAYOUT.md §2 (linha 38)`) are outside issue #154's scope. They are
     recorded as a finding on the issue.
6. **Conversion.** All citations were converted in this issue, each to the content it cited in the
   commit where the number was written. That commit is the `git blame` of the citing line, ignoring
   this issue's commits, or the pickaxe commit of the number when the two disagreed. For a doc born
   on a parallel branch, it is the version its ranges followed (`e8a7180` for the ADRs cited by
   `shift-scheduling.md`). The overview citations followed the numbering of `68f9f38^`, except
   one in the 4.1 technical. Accepted ADRs changed only in the pointer. A zero-context verifier
   checked a sample by content (recorded in the PR body).

## Alternatives

- **A — One gate for all three targets.** The overview shares the domain-doc grammar and its
  failure messages. ADR passages and code symbols do not: the ADR has no section grammar, and code
  is not resolved. Folding them together would branch every rule on the target. ADR 0.0.0017
  Decision 3 rejected this for the same reason.
- **B — Gate only the overview; leave ADRs and code to review.** ADRs are where the drift is most
  certain, because errata banners are routine. Code citations are the most numerous. Review did
  not catch any of them, and no gate existed.
- **C — Resolve code symbols against HEAD.** It would catch a renamed function, but it would fail
  the docs of every `done` Stage on each refactor, which forces rewriting historical records. The
  cost lands on every code PR, which is the same shape of cost ADR 0.0.0012 Alternative B
  rejected.
- **D — Anchors without a gate.** The next concept that writes `x.py:113` brings the drift back,
  as it did for the roadmap before ADR 0.0.0012.

## Consequences

- An errata banner on an ADR, a dated note in the overview or a line inserted in a code file no
  longer moves any citation.
- Renumbering an overview section or rewording a passage another doc quotes, in the overview or
  in an ADR, fails `make docs-check` with the citing `file:line`.
- Renaming a code symbol does not fail the gate. The stale symbol is still greppable in history,
  and the line number, which the gate now forbids, was no better.
- **Limits.** A citation is recognised by the name of its target. A line number cited without it
  (`na linha 50`, with the ADR implied by the sentence) is invisible, as in the other two gates. The
  conversion named the target in each one it found. For code, a number followed by a word
  (`x.py 113 diz`) reads as a count, not a line. The CONVENTIONS form never writes it that way.

## References

- Issue #154; PR #151 audit (issue #116).
- [ADR 0.0.0012](./0_0_0012-cite-the-roadmap-by-stable-anchor.md) and
  [ADR 0.0.0017](./0_0_0017-cite-domain-docs-by-stable-anchor.md) — the two precedents, partially
  superseded here.
- [`CONVENTIONS.md`](../CONVENTIONS.md) §5 "Citação ao overview, a ADR e a código" — the rule.
- [`scripts/check_domain_citations.py`](../../scripts/check_domain_citations.py) (overview) and
  [`tests/unit/test_check_domain_citations.py`](../../tests/unit/test_check_domain_citations.py).
- [`scripts/check_adr_code_citations.py`](../../scripts/check_adr_code_citations.py) and
  [`tests/unit/test_check_adr_code_citations.py`](../../tests/unit/test_check_adr_code_citations.py).

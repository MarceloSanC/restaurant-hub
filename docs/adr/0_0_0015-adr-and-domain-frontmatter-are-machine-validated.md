---
title: ADR 0.0.0015 — ADR and domain-doc frontmatter is machine-validated, and adr_id is unique and matches the filename
description: Architecture Decision Record
when-use: Reference before creating or renumbering an ADR, before linking an ADR from a docs/domain doc, before closing or re-addressing a "Lacuna para o concept da Stage N.M", or before changing what make docs-check enforces about frontmatter
keywords: [adr, process, docs, frontmatter, yaml, adr-id, uniqueness, domain, references, lacuna, docs-check, gate, issue-102]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
adr_id: "0.0.0015"
decision: 'scripts/check_doc_frontmatter.py, run by make docs-check, parses the frontmatter of docs/adr/*.md and docs/domain/**/*.md with yaml.safe_load and rejects: invalid YAML; an adr_id that is not "N.M.NNNN", differs from the N_M_NNNN filename prefix or repeats across ADRs; and, in a domain doc, a references entry or relative link that does not resolve, an ADR linked in the body but absent from references, and a "Lacuna para o concept da Stage N.M" still open when a listed Stage is done. shift-scheduling.md keeps an exact, shrink-only valve for its missing references.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0015 — ADR and domain-doc frontmatter is machine-validated

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #102 (findings F1 and F2 of issue #37), with the scope added by the audit of
PR #110 (unique `adr_id`). **Partially supersedes** [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md):
its trade-off *"No machine validation enforces these categories … conformance is a code-review
concern"* no longer holds for `docs/domain/`. The rest of 0.0.0003 stands.

## Context

1. **Frontmatter that is not YAML reached `develop` seven times.** `yaml.safe_load` refused the
   frontmatter of ADRs 0.0.0009, 0.0.0010, 1.2.0001, 2.3.0001, 3.5.0003 and 3.5.0004 — a
   `decision:` starting with a backtick, a `title:` with `: ` inside. Issue #37 counted four;
   0.0.0009 and 0.0.0010 landed afterwards, and 0.0.0013 (PR #109) landed while this issue ran. No gate parses ADR frontmatter:
   `check_adr_bounded_context.py` reads one key by regex, `check_harness.py` parses `.claude/` only.
2. **The same `adr_id` was minted twice, twice.** The branch of issue #12 created 0.0.0007 on
   2026-10-21 (`eb7be50`) and the orchestrator ADR took 0.0.0007 on 2026-11-01 (`4062cbb`); #12
   renumbered to 0.0.0009 (`5abc76a`). On 2026-11-02 PRs #109 and #110 both created 0.0.0011.
   The filenames differ by slug, so git sees no conflict; #110 was renumbered by hand. At the time
   of this ADR, open PR #111 still carries a second `0_0_0012-*.md`.
3. **Domain docs drift from their own frontmatter.** Before #37, `workforce.md` linked 18 ADRs and
   listed 8 in `references`, and four "Lacuna para o concept da Stage N.M" stayed open after the
   Stage was `done`. Stage 3.8 repeated it. `shift-scheduling.md` had ten such markers open for
   Stages 4.1–4.3 (all `done`) when this gate was written; its §6 notes had answered them, the
   markers in the body had not changed.
4. **`shift-scheduling.md` is cited by line number** from the body of accepted ADRs (4.1.0008,
   4.1.0011, 4.1.0012) and from the 4.1 concept — text that is not edited (CONVENTIONS §5). The
   4.1 closing decided not to add ADRs to its `references` because every new frontmatter line
   shifts those citations silently (technical 4.1 §7, 2026-09-27). Issue #79 / ADR 0.0.0012 turned
   citations **to the roadmap** into anchors; citations **to this doc** are untouched, so the
   reason still holds.

## Decision

1. **One validator, in `make docs-check`:** `scripts/check_doc_frontmatter.py`.
2. **ADRs (`docs/adr/*.md`).** The frontmatter is a YAML mapping; the filename is
   `N_M_NNNN-<slug>.md`; `adr_id` is the string `N.M.NNNN` equal to the filename prefix; no
   `adr_id` appears in two files. A clash is fixed by renumbering the newer ADR to the next free id.
3. **Domain docs (`docs/domain/**/*.md`).** The frontmatter is a YAML mapping; `references`, if
   present, is a list of paths that resolve; every relative link in the body resolves (fragment
   ignored, fenced code and inline code skipped); every ADR linked in the body is in `references`.
4. **Open gaps.** A "Lacuna para o concept da Stage N.M" (or `N.M/P.Q`) fails as soon as **any**
   listed Stage is `done` in the *Tabela de Stages*. A closed gap is rewritten in place
   ("Lacuna fechada pela Stage N.M (source)"); what is left for another Stage is re-addressed to it.
5. **Valve.** `VALVULA_REFERENCES` in the script maps `shift-scheduling.md` to the exact set of
   ADRs it links without listing (16 today). The gate demands **equality**: a new ADR linked
   outside `references` fails, and an entry that stops being missing fails until it is removed.
   The valve only shrinks.
6. **Syntax repair is not a body edit.** Quoting a frontmatter value so that it parses, with the
   parsed value byte-identical to the previous text, does not touch the decision body that
   CONVENTIONS §5 protects; it needs no errata and no `updated_at` bump.

## Alternatives considered

### Alternative A — extend `check_adr_bounded_context.py`
- **Pros:** one script fewer.
- **Cons:** that script is about one key and the roadmap's BC set; it reads by regex on purpose.
  Domain docs are a second category with link and roadmap rules.
- **Why rejected:** two concerns in one file; a separate validator keeps each failure message
  owned by one rule set.

### Alternative B — derive uniqueness from the filename only
- **Pros:** no YAML needed.
- **Cons:** `0_0_0011-a.md` and `0_0_0011-b.md` are distinct filenames; uniqueness has to be checked
  on the id, and the id has to be tied to the filename or the two can disagree.
- **Why rejected:** both checks are needed, and both are cheap.

### Alternative C — gap fails only when **all** listed Stages are done
- **Pros:** fewer forced edits for split gaps (`4.3/4.5`).
- **Cons:** `4.3/4.5` with 4.3 done would stay "open" with no signal of whether 4.3 answered it — the
  4.3/4.5 "unidade de salvamento" gap was in fact closed by ADR 4.3.0001.
- **Why rejected:** "any" forces the honest state: closed, or re-addressed to the Stage that still
  owes it.

### Alternative D — no valve: add the 16 ADRs to `shift-scheduling.md`'s `references`
- **Pros:** no exception.
- **Cons:** 16 new frontmatter lines shift every line of the doc, and with it the line citations in
  three accepted ADR bodies and a `done` concept, with no error anywhere. Packing the entries into
  a flow list of the same line count would avoid the shift but make the frontmatter unreadable.
- **Why rejected:** the exception is cheaper than silent drift; it is explicit, counted and
  shrink-only, and goes away when those citations become anchors.

## Consequences

### Positive
- Frontmatter breakage, `adr_id` collisions and `references` drift fail at PR time, with
  `file:line: reason`.
- A parallel session that picks a taken `adr_id` learns it from CI after rebasing, instead of from
  an auditor.

### Negative
- A PR in flight that adds an ADR with an unquoted backtick-leading `decision:` fails
  `docs-check` after rebasing until it quotes it — a true positive, but extra work at rebase time.
  ADR 0.0.0013 (PR #109, merged first) was quoted by this issue; PR #111 also carries a second
  `adr_id` 0.0.0012 and has to renumber.
- The valve is a list of filenames inside a script; it has to be edited when the doc changes.

### Neutral / trade-offs accepted
- `docs/audits/` is not covered: it has no instance yet (ADR 0.0.0003, Alternative C). The first
  audit should extend the validator.
- The content of a citation is not checked (does the cited section say what the doc claims?) —
  that stays with the claims audit.

## References

- [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md) — the `domain/` contract
  this ADR enforces (partially superseded).
- [ADR 0.0.0012](./0_0_0012-cite-the-roadmap-by-stable-anchor.md) — the roadmap-citation gate, the
  precedent for this one.
- [CONVENTIONS.md §2](../CONVENTIONS.md) (ADR frontmatter) and §5 (accepted ADR body).
- [`scripts/check_doc_frontmatter.py`](../../scripts/check_doc_frontmatter.py) and
  [`tests/unit/test_check_doc_frontmatter.py`](../../tests/unit/test_check_doc_frontmatter.py).
- Issue #102; issue #37 (findings F1, F2); PR #110 audit comment on issue #102.

---
title: ADR 0.0.0017 — Docs cite docs/domain by stable anchor, never by line number, and a gate enforces it
description: Architecture Decision Record
when-use: Reference before citing a docs/domain doc from any other doc, before renumbering or renaming a section of a domain doc or rewording a passage that another doc quotes as a label, before adding a domain doc with a filename already used under docs/domain, or before changing what make docs-check enforces about domain-doc citations
keywords: [adr, process, docs, domain, citation, anchor, line-number, docs-check, gate, references, valve, issue-116]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-09
adr_id: "0.0.0017"
decision: 'A doc cites a docs/domain doc by section plus label (`shift-scheduling.md` §3.4 › "não ocupa duas vagas da mesma demanda"), never by line number; scripts/check_domain_citations.py, run by make docs-check, rejects a line number after a domain-doc reference and an anchor whose section or label does not exist in the cited doc. With no line citation left, the references valve of shift-scheduling.md (ADR 0.0.0015 Decision 5) is removed.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0017 — Docs cite docs/domain by stable anchor, never by line number

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #116 (finding of the PR #112 audit). **Partially supersedes**
[ADR 0.0.0015](./0_0_0015-adr-and-domain-frontmatter-are-machine-validated.md) — Decision 5 (the
`VALVULA_REFERENCES` exception for `shift-scheduling.md`) and Alternative D's rejection, whose
premise was the line citations this ADR removes. The rest of 0.0.0015 stands. Extends
[ADR 0.0.0012](./0_0_0012-cite-the-roadmap-by-stable-anchor.md) — the same rule for the roadmap —
to a second target, as its "Limits" paragraph foresaw.

## Context

1. **The domain docs were cited by line number.** ADRs 4.1.0007–4.1.0012 and the Stage 4.1
   concept cited `shift-scheduling.md` by line — the filename followed by a bare number,
   *"§6 (line 1086)"*, *"doc §3.1 (linha 166)"*: 57 citations in all. The 4.1 remap (commit `7856466`)
   had verified them by content; since then two lines left the doc above §6, and the three
   citations to the §6 gap table (1086–1088) already pointed two rows below their target.
   Nothing failed.
2. **The line citations held a valve open.** Issue #102 (ADR 0.0.0015 §Decision 5) could not add
   the 16 ADRs that `shift-scheduling.md` links in its body to its `references`: 16 new
   frontmatter lines would shift every one of those citations silently. It kept an exact,
   shrink-only exception instead, to go away "when those citations become anchors".
3. **Domain docs already had section anchors.** 366 section anchors in the corpus were already
   `` `workforce.md` §3.1 ``/`workforce §3.7` — the numbered headings of the domain-doc template.
   What the line numbers did was point *inside* a section.
4. **Precedent.** ADR 0.0.0012 solved the same problem for the roadmap with section + label and
   a gate (`check_roadmap_citations.py`), and named "a second target" as the way to extend it.

## Decision

`[decision:C] 0.0.0017 — how other docs cite a docs/domain doc`
Escolha: anchor (section + label) **and** a sibling gate · Alternativas: generalise the roadmap
gate; anchor without gate; keep line numbers and the valve · Degrau (C): 1 (ADR 0.0.0012 is the
ratified form for the roadmap; the domain-doc template's numbered headings fix the section part).
Base: issue #116 body; ADR 0.0.0012; ADR 0.0.0015 §Decision 5 and Alternative D.
Configuração candidata: nenhuma · Reversível: sim (convert anchors back to numbers; drop the gate).

1. **Form.** `` `<doc>.md` §<section> › <label>, <label> ``.
   - Reference: the domain doc's filename (`` `shift-scheduling.md` ``, a link to it, or its path),
     or the bare name followed by ` §` (`workforce §3.7`, the form the corpus already used).
   - Section: `§N`, `§N.M`, `§N.M.K` — the number of a heading in that doc — or `§"<heading>"`
     for an unnumbered one. A section includes its subsections (`§6` covers the gap table under
     its `###` heading).
   - Label (optional): `"<passage>"` — text of the section, compared without `*`, backticks,
     blockquote markers or extra whitespace, so a label can quote across bold and line breaks — or
     `` `<literal>` `` (raw). Unlike the roadmap's labels, a domain-doc label need not be bold:
     domain docs state rules in prose, and the cited thing is a sentence.
   - An anchor with a label names the doc, even where the paragraph already did ("doc §2, linha
     107" became `` `shift-scheduling.md` §2 › "Faixas de funcionamento" ``): the gate only sees
     anchors that follow a reference.
   - The rule lives in CONVENTIONS §5 ("Citação a doc de domínio").
2. **Gate.** `scripts/check_domain_citations.py`, a sibling of `check_roadmap_citations.py`, in
   `make docs-check`, over `docs/` (domain docs and the roadmap included), `.claude/`, `.github/`
   and the root `*.md`:
   - **No line number.** After a domain-doc reference, up to the end of the sentence, a table cell,
     the paragraph or another source (`x.md`, `ADR N`, `overview`, `concept`, `technical`), no 2–4
     digit number may remain once section numbers, issue numbers, dates, versions, URLs, HTTP
     statuses and quoted text are set aside; a number right after the reference, `linha N`/`line
     N`/`l. N`, and `<doc>.md#LN` are lines always.
   - **The anchor resolves.** The chain of anchors right after the reference (separated by `,`,
     `;`, `/`, `–`, `e`/`and`, with parenthetical notes between them) must exist in the cited
     doc, each label inside its section. Prose between two `§` ends the chain, so `workforce
     §3.8; as docstrings de §8` does not read the citing concept's §8 as the domain doc's.
   - Domain docs are discovered from the folder: a new one is covered without editing the gate.
     Two domain docs with the same filename make a reference ambiguous and fail closed (exit 2).
3. **Sibling, not a generalised roadmap gate.** The two grammars differ — roadmap sections are
   `§Stage N.M`/`§Step N` and its labels are bold text, YAML keys, dated notes and issue rows;
   domain sections are heading numbers and labels are prose — and so do the targets (one file vs.
   a discovered set). One script per citation target keeps each failure message owned by one rule
   set, the reason ADR 0.0.0015 Alternative A gave for a separate validator. The shared part (where
   a citation ends, what is not a line number) is a few regexes, duplicated on purpose.
4. **The valve goes.** The 16 ADRs enter `shift-scheduling.md`'s `references`, and
   `VALVULA_REFERENCES` is removed from `check_doc_frontmatter.py` instead of left empty: with no
   line citation to a domain doc, a frontmatter line shifts nothing, and an empty exception table
   would only invite a new entry.
5. **Out of scope.** `technical.md` from `## 7.` to the end (the post-execution log records past
   remaps by number), as in ADR 0.0.0012. Line citations to other docs (`overview.md 41`, an ADR's
   `lines 95–97`, code files) stay outside this decision.
6. **Conversion.** All 57 citations were converted in this issue, each to the content it cited
   when the 4.1 remap last verified it (`7856466`), not to a fixed offset; ADR bodies changed only
   in the pointer. A zero-context verifier checked a sample by content (recorded in the PR body).

## Alternatives

- **A — Generalise `check_roadmap_citations.py` to several targets.** One gate fewer, but every
  rule would branch on the target: two section grammars, two label grammars, one fixed file vs. a
  discovered set. Rejected for the reason in Decision 3.
- **B — Convert the citations, no gate.** The next ADR that quotes "line 344" brings the drift
  back silently — the roadmap had three bulk remaps before ADR 0.0.0012 added its gate.
- **C — Keep line numbers and the valve (status quo).** Every edit above a cited line (a dated
  note, a closed gap rewritten in place) moves the citations of accepted ADRs without an error,
  and the valve stays as a standing exception in the frontmatter validator.
- **D — Bold-only labels, as in the roadmap.** Most cited passages are not bold; it would force
  bolding text in an accepted domain doc just to anchor it, or leave the citation at section level
  and lose the precision the line number had.

## Consequences

- An edit above a cited passage — a dated note, a gap closed in place, a new `references` line —
  no longer moves any citation.
- Renumbering a domain-doc section, or rewording a passage another doc uses as a label, fails
  `make docs-check` with the citing `file:line`; the fix is in the citing doc or the edit is
  reverted. A domain doc's numbered headings are now part of its contract.
- `shift-scheduling.md`'s `references` is complete, and rule 7 of `check_doc_frontmatter.py` has
  no exception.
- **Limits.** The gate recognises a citation by the doc's name. A line number cited without it
  (*"doc §3.1 (linha 166)"*, with the doc implied by the paragraph) is invisible, as it was before;
  the converted corpus has none, and the CONVENTIONS form always names the doc. A label is checked
  only in the chain right after a reference.

## References

- Issue #116; PR #112 audit (issue #102); ADR 0.0.0015 §Decision 5 and Alternative D.
- [ADR 0.0.0012](./0_0_0012-cite-the-roadmap-by-stable-anchor.md) — the roadmap precedent.
- [`CONVENTIONS.md`](../CONVENTIONS.md) §5 "Citação a doc de domínio" — the rule.
- [`scripts/check_domain_citations.py`](../../scripts/check_domain_citations.py) and
  [`tests/unit/test_check_domain_citations.py`](../../tests/unit/test_check_domain_citations.py).
- [`scripts/check_doc_frontmatter.py`](../../scripts/check_doc_frontmatter.py) — valve removed.

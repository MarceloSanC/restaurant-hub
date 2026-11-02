---
title: ADR 0.0.0012 — Docs cite the roadmap by stable anchor, never by line number, and a gate enforces it
description: Architecture Decision Record
when-use: Reference before citing docs/roadmap.md from any other doc, before renaming a roadmap heading or a bold label/YAML key inside a Stage block, or before changing what make docs-check enforces about roadmap citations
keywords: [adr, process, docs, roadmap, citation, anchor, line-number, docs-check, gate]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
adr_id: "0.0.0012"
decision: A doc cites docs/roadmap.md by section plus label (`roadmap.md` §Stage N.M › "Descrição humana", `definition_of_done`), never by line number; scripts/check_roadmap_citations.py, run by make docs-check, rejects a line number after a roadmap reference and an anchor whose section or label does not exist. The technical.md §7 log and the roadmap itself are out of scope.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0012 — Docs cite the roadmap by stable anchor, never by line number

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #79, whose scope asked for exactly this call: *"avaliar um gate mecânico (ex.: em
`check_docs_claims`) ou a troca de citação por linha por âncora estável, para que o próximo bloco
de Stage não repita o problema"*, with the acceptance criterion *"decisão registrada sobre gate ou
âncora estável"*.

## Context

The scheduling domain doc, five scheduling ADRs and the 4.1 concept cited the roadmap by line
(`` `roadmap.md` <line> ``), 161 citations in all. The roadmap grows in the middle, so every one of
them drifts:

1. **Every new issue moves every Step block.** The *Tabela de Issues* sits above *Detalhamento por
   Step*. Between the 4.2 merge (`5e21239`) and this issue (`666bf61`), the Stage 2.6/3.7/3.8
   blocks and the issue rows registered meanwhile moved the Step 4 heading from line 1219 to 1408.
   Two more branches were open while this issue ran (#26, #68), each adding a row.
2. **Bulk remapping has been done three times and lost every time.** Stage 4.1 remapped 134
   citations after a rebase (+39); Stage 3.7 remapped 178 for its own block (+58); Stage 3.8
   remapped them again (+48). Each was correct for its branch and wrong after the next merge: the
   +65 of Stage 2.6 was never applied, which is how #79 was born. When this issue started, the
   citations were off by +83 for Step 4 onward and by +3 in the Stage table.
3. **Nothing failed.** A stale line number points silently at a neighbour — a blank line, a YAML
   label, another Stage's block. Two such pairs crossed two audits in the Step 4 domain gate (PR
   #53) because the verifier compared stability, not content.
4. **A section-level anchor already existed.** Stage concepts and ADRs cite
   `` roadmap.md §"Stage 2.1 — `2.1-identity-domain`" ``/`§Stage 2.4`, and the concept template's source field reads
   `Roadmap §Stage N.M`. What it lacked was a way to point *inside* a block (the
   *Descrição humana*, the `definition_of_done`, a dated note), which is what the line numbers were
   doing.

## Decision

`[decision:C] 0.0.0012 — how other docs cite the roadmap`
Escolha: anchor (section + label) **and** a gate · Alternativas: remap per PR; content-hash gate;
move the issue table; gate alone · Degrau (C): 4 (the reversible form that does not have to be
redone on every PR; degrau 1 — the already-ratified `§Stage N.M` — fixes the section part).
Base: issue #79 body; Stage 3.7/3.8/4.1 technical §7 (three remaps); this ADR's Context.
Configuração candidata: nenhuma · Reversível: sim (convert anchors back to numbers; drop the gate).

1. **Form.** `` `roadmap.md` §<section> › <label>, <label> ``.
   - Section: `§Stage N.M`, `§Step N`, or `§"<roadmap heading>"` (`§"Tabela de Stages"`,
     `§"Lacunas conhecidas"`, `§"Premissas adotadas no Roadmap"`, `§"Visão geral"`). The long form
     `§"Stage N.M — `slug`"` stays valid.
   - Label (optional): `"<bold text>"` (`"Descrição humana"`, `"Resultado de negócio"`,
     `"ROADMAP-3"`), `` `<literal>` `` (YAML key, table cell, graph edge), `nota YYYY-MM-DD` (a
     dated note in the section), `#N` (an issue-table row). Anchors in different sections are
     separated by `;`.
   - The rule lives in CONVENTIONS §5 ("Citação ao roadmap"); other docs point there.
2. **Gate.** `scripts/check_roadmap_citations.py`, in `make docs-check`, over `docs/`, `.claude/`,
   `.github/` and the root `*.md`:
   - **No line number.** After a reference to the roadmap, up to the end of the sentence, a table
     cell, the paragraph or another source (`x.md`, `ADR N`, `overview`), no 2–4 digit number may
     remain once Stage/Step numbers, issue numbers, dates, versions, URLs and quoted text are set
     aside; a number right after the reference is always a line.
   - **The anchor resolves.** Every `§Stage N.M`/`§Step N` must exist; every label after ` › ` must
     exist *inside that section* (a Step section includes its Stage blocks). Renaming a heading or
     deleting a label breaks the build instead of leaving a dangling pointer.
3. **Out of scope.** The roadmap itself, and `technical.md` from `## 7.` to the end: the §7 log
   records past remaps by number ("1481→1517"), and rewriting those would erase the fact they
   record.
4. **Conversion.** All 161 citations were converted in this issue, each to the content it cited when
   it was last verified (the doc/roadmap pair at the 4.2 merge, `5e21239`; the 2.2 concept against
   the roadmap of its own commit), not to a fixed offset. A zero-context verifier checked a sample by
   content (recorded in the PR body).

## Alternatives

- **A — Keep line numbers; remap on every PR that shifts the roadmap (status quo).** Rejected by the
  record: three bulk remaps in six weeks, each undone by the next merge, and the drift is caused by
  routine work (registering an issue), not by Stage blocks only. It also makes every PR that adds
  an issue row touch seven scheduling docs.
- **B — Keep line numbers; gate checks them by content** (e.g. require a quoted fragment next to the
  number and check that the line contains it). Catches drift but does not remove it: every
  issue-row PR would turn the build red until someone remaps. It moves the cost, it does not cut it.
- **C — Move the issue table below the Step blocks (or into its own file).** Reduces the churn but
  does not end it: Stage blocks and dated notes are still inserted above later Steps (2.6, 3.7 and
  3.8 all did it).
- **D — Gate that only forbids line numbers, no anchor resolution.** Stops the drift but lets a
  renamed heading or a deleted label leave a pointer to nothing. Resolving the anchor makes it as
  checkable as the number was supposed to be.

## Consequences

- An issue row or a new Stage block no longer touches any citing doc.
- Renaming a roadmap heading (`#### Stage N.M — ...`), a bold label or a YAML key that a doc cites
  fails `make docs-check` with `arquivo:linha` of the citation; the fix is in the citing doc or the
  rename is reverted.
- Precision drops from one line to one labelled element. The quoted text next to most citations
  (e.g. *"alocação dentro do período"*) keeps pinpointing the phrase; no citation in the corpus
  needed more than a label.
- **Limits.** The gate recognises a citation by the word `roadmap`. A line number cited without it
  (`tabela de Stages 125`) is invisible, as it was before. Line citations to other docs
  (`overview.md 46`) are out of this decision: `overview.md` does not grow in the middle on every
  PR. If it starts to, the same gate can take a second target.
- ADR bodies were edited only in the pointer (line number → anchor), as the 3.7 and 4.1 remaps did;
  no decision content changed.

## References

- Issue #79 (and its comment from the Stage 3.8 re-audit); issue #49 (Stage 3.7 audit that found it).
- [`CONVENTIONS.md`](../CONVENTIONS.md) §5 "Citação ao roadmap" — the rule.
- [`scripts/check_roadmap_citations.py`](../../scripts/check_roadmap_citations.py) and
  [`tests/unit/test_check_roadmap_citations.py`](../../tests/unit/test_check_roadmap_citations.py).
- Stage technical §7 entries of 3.7, 3.8 and 4.1 — the three bulk remaps.

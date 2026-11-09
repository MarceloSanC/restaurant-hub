---
title: ADR 4.1.0011 — The declared break exists on both the band and the allocation; the divergence is represented, surfaced and resolved by an explicit choice
description: Architecture Decision Record
when-use: Reference before storing the meal break in a single place, before adding a second site that computes allocation hours, before keying band uniqueness on the whole TimeRange value, or when Stage 4.2 names the break-divergence policy and Stage 4.5 asks the editor which break to keep
keywords: [adr, scheduling, break, meal-break, allocation, band, effective-break, divergence, hours, uniqueness, clt-art-71]
status: accepted
created_at: 2026-09-27
updated_at: 2026-09-27
adr_id: 4.1.0011
decision: The declared break lives on the band (default 0) and, optionally, on the allocation (absent means it inherits the band's); the allocation's effective break is the input of the single hours-counting site; when the two differ the allocation carries a derived break-divergence mark that the domain represents but never resolves, leaving "which one to keep" to the policy of 4.2 and the boundary of 4.5; and the band's uniqueness key inside a schedule narrows from the whole TimeRange value to the (start, end) pair.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0011 — The declared break lives on the band and on the allocation

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md) §3
settled fork F3 — *"Menos intervalo declarado (Recomendada)"* — and put the break
**on the time range**, i.e. on the band: `hours(a) = (end − start) − break`, a
**single function** consumed by every policy that sums and by the hub. The domain
doc glosses it the same way: *"Minutos de intervalo dentro da faixa, declarados
pelo editor; default 0"* (`shift-scheduling.md` §2 › "Intervalo declarado").

The Checkpoint A review of this Stage's concept (2026-09-26) showed that the
single-level shape is contradictory in practice, and that both ways out of the
contradiction were broken:

- `overview.md` line 41 puts **two functions on one band**: *"qua = 1 cozinheiro
  16h–00h + 1 assistente 18h–23h + 2 atendentes 16h–00h"*. With the break only on
  the band, the cozinheiro and the atendentes who share `16h–00h` are **forced to
  share the same declared break**. A manager contradicts that: CLT art. 71 scales
  the rest break with the **person's** working day, and the intra-shift-break
  policy that the domain doc defers (§3.6.9) will need it per person.
- Keeping the break on the band **and** keying band uniqueness on the whole
  `TimeRange` value made two bands `16h–00h` with breaks 0 and 60 legitimate on one
  Wednesday — which is exactly the shape
  [ADR 4.1.0010](./4_1_0010-enabled-band-is-an-element-of-the-day.md) rejected as
  Alternative A, because *"the same visual band can count 8h for the cozinheiro and
  7h for the atendentes, which the 'single counting rule' of ADR 4.1.0002 §3 exists
  to prevent"*.
- Narrowing the key to `(start, end)` without moving the break would have made the
  **real** case unrepresentable: an 8h cook with a 1h break and an 8h waiter with no
  break on the same clock band.

So the question was put to the sponsor, who answered on 2026-09-26, verbatim:
*"pode ser na alocacao e na faixa, mas precisa apontar conflito, e perguntar qual
horario quer manter"*.

Two constraints frame the answer. First, ADR 4.1.0002 §3 fixed **one** counting
rule, and this Stage's concept fixed **one** computation site — neither may be
duplicated. Second, this BC refuses structurally only what it cannot represent
(ADR 4.1.0003 (c); concept §5.18): "pointing at a conflict and asking which one to
keep" is a policy with a mode and a boundary interaction, not a structural refusal.

## Decision

1. **The band carries `break_minutes` (default 0)**, as ADR 4.1.0002 §3 ratified,
   with `0 <= break_minutes < nominal_minutes`.
2. **The allocation may carry its own `break_minutes`, optional.** `None` — the
   default — means it **inherits** the band's. When declared it must satisfy
   `0 <= break_minutes < nominal_minutes` **of the band that contains it**, checked
   in `ShiftBand.__post_init__`, the only level that sees both the range and the
   allocations. Violation raises `InvalidAssignmentBreakError`, on every path:
   construction, `assign`, `declare_allocation_break`, and a `reschedule_band` that
   shortens the band below an already declared break.
3. **The allocation's effective break is the input of the single counting site.**
   `TimeRange.worked_minutes(break_minutes=None)` is the one arithmetic expression;
   it takes the effective break as an argument and falls back to the band's own.
   `Schedule.worked_minutes_of(assignment_id)` is the one path per allocation. The
   rule of ADR 4.1.0002 §3 is unchanged — only the **source** of its input widened,
   which is why that ADR gets a dated **errata** and not a supersession.
4. **The divergence is a derived mark on the allocation, sibling of the other two.**
   `Schedule.has_break_divergence(assignment_id)` is true when the allocation
   declares a break **different** from the band's. It is **derived**, not a stored
   boolean: the two break values already are the truth, and a stored flag could
   contradict them (see Alternative C). The domain **represents** the conflict and
   never resolves it: **naming the policy, its mode, and asking the editor "which
   one do you want to keep"** belongs to 4.2 (`warn` proposed, `block`
   configurable) and 4.5. The domain neither chooses nor silences.
5. **Changing the band's break is its own verb.** `redeclare_band_break(band_id,
   break_minutes)` exists so that "I changed everyone's hours" cannot hide inside
   "I changed the schedule": `reschedule_band` takes `start`/`end` and preserves the
   break **by signature**, so the forbidden act is unrepresentable rather than
   checked, and the 4.4 audit trail gets two distinct names.
6. **The band's uniqueness key narrows to `(start, end)`.** Two bands of a schedule
   may not share that pair; `break_minutes` is out of the key. This closes the
   twin-band pathology of ADR 4.1.0010's Alternative A, and it costs nothing now
   that per-person breaks live on the allocation. ADR 4.1.0010 Decision 3 is
   restated accordingly in that ADR (which was still uncommitted at the time).

## Alternatives considered

### Alternative A — Break only on the band (the shape before this ADR)
- **Description:** ADR 4.1.0002 §3 read literally and narrowly: one break per band,
  shared by everyone allocated to it.
- **Pros:** one field, one number per band; the simplest possible counting; matches
  the domain doc's gloss literally.
- **Cons:** the ratified two-functions-on-one-band example forces the cook and the
  waiter to share a break, so an 8h waiter with no break and an 8h cook with a 1h
  break cannot coexist on one clock band; the editor's workaround is two twin bands,
  which is the pathology ADR 4.1.0010 rejected — and which only stayed *possible*
  because the uniqueness key included the break; CLT art. 71 scales the break with
  the person's day, and the deferred intra-shift-break policy will need it per
  person.
- **Why rejected:** it makes a real and common shape unrepresentable, and its only
  workaround reopens a defect this Stage had already closed.

### Alternative B — Break only on the allocation
- **Description:** remove the break from the band; every allocation declares its
  own.
- **Pros:** one level, no divergence to represent, no inheritance rule; the break is
  always the person's, which is what the law scales.
- **Cons:** it contradicts ADR 4.1.0002 §3 head-on (the break is *"declared on the
  time range"*), so it would need a supersession rather than an errata; a band with
  no allocations yet — the legitimate result of the first act, per ADR 4.1.0010
  Decision 2 — could not express "this shift has a one-hour break", which is
  information the editor has **before** choosing people and which the auto-fill of
  Step 5 will want; and the common case (everyone on this band takes the same hour)
  would be retyped once per person, with nothing keeping the copies equal.
- **Why rejected:** it discards ratified information for a uniformity the operation
  does not have, and it breaks the "band first, people later" order the overview
  describes.

### Alternative C — Both levels, with the divergence stored as a boolean on the allocation
- **Description:** the chosen shape, except that `break_divergence` is a field
  written at `assign`/`declare_allocation_break` time, sibling of
  `counts_toward_workload` and `function_exception` in storage as well as in meaning.
- **Pros:** symmetric with the other two marks; the 4.4 mapper persists one boolean
  and the 4.2 evaluator reads it without comparing anything.
- **Cons:** it is a **second source of truth** for something the two break values
  already determine, so it can contradict them — a `reschedule_band` or a
  `redeclare_band_break` that makes the two values equal would leave the flag true
  unless every mutation recomputes it, and a mapper could rehydrate a row whose flag
  disagrees with its own numbers. The repo has ruled against exactly this shape
  before: the operational day is *derived, never stored*, because *"a stored day
  would be a second source of truth for something the cutoff already determines"*
  (ADR 4.1.0007 Decision 4).
- **Why rejected:** the same argument that keeps the operational day derived keeps
  this mark derived. "Sibling of the other two marks" is a statement about meaning —
  what the policy and the boundary read — not about storage.

### Alternative D — Both levels, and the domain picks a winner
- **Description:** on divergence, the domain silently keeps one of the two (the
  allocation's, as the more specific).
- **Pros:** no conflict ever surfaces; one number, always defined; nothing for 4.2
  or 4.5 to do.
- **Cons:** it is precisely what the sponsor ruled out — *"precisa apontar conflito,
  e perguntar qual horario quer manter"*. Silently preferring the allocation turns a
  typo into a payroll-visible hour difference with no trace, and it would make the
  divergence invisible to the audit trail of 4.4 and to the hub.
- **Why rejected:** it contradicts the literal answer, and it hides a difference the
  editor asked to be shown.

### Alternative E — Do nothing / leave the break's place to a later Stage
- **Why not acceptable:** `TimeRange` is built in this Stage and `worked_minutes` has
  to exist before 4.2 can sum anything; the 4.4 mapper is about to persist the break
  in a column of the band. Deferring would mean persisting the single-level shape
  and paying a migration to undo it — the opposite of the project's
  progressive-scalability criterion.

## Consequences

### Positive
- The ratified case works: cook 16h–00h with a 1h break counts **7h** and waiter on
  the **same** band with no break counts **8h**, with one band, one card and one
  audit subject.
- The counting rule and its computation site stay **single**; only the input widened.
- The twin-band pathology is now structurally impossible, since the uniqueness key is
  `(start, end)`.
- The common case stays cheap: nobody declares a break per person unless it differs.
- "I moved the shift" and "I changed everyone's break" are two verbs, so the 4.4
  trail can tell them apart and 4.5 can confirm the second one.

### Negative
- A third thing to render and explain in 4.5: the band's break, the allocation's
  optional break, and the fact that they may differ.
- One more nullable column for 4.4, and a mapper that must round-trip `None` as
  "inherits" rather than as zero — the two are **not** the same value.
- The divergence being derived means every consumer computes it; the domain offers
  one read (`has_break_divergence`) so that nobody re-derives it by hand.
- A `reschedule_band` that shortens a band can now fail because of a break declared
  on an **allocation**, which is a refusal whose cause is two levels away from the
  act; the exception must name it (`InvalidAssignmentBreakError`).

### Neutral / trade-offs accepted
- The **name and mode** of the break-divergence policy, and whether choosing "keep
  the band's" erases the allocation's value or keeps it with the mark, stay a **4.2**
  decision — this ADR gives the policy something to read, not a verdict.
- The intra-shift-break policy deferred by ADR 4.1.0002 §4 and the domain doc §3.6.9
  will read the **effective** break, so its arrival changes no shape here.
- Night-hour fiction (CLT art. 73 § 1º), also deferred, still enters as a parameter
  of the same single site.

## Implementation notes

- `value_objects/time_range.py`: `worked_minutes(break_minutes: int | None = None)`
  (no longer a property), `with_break`, `with_bounds` (which preserves the break and
  is what makes Decision 5 structural).
- `entities/assignment.py`: `break_minutes: int | None = None`, `declare_break`;
  the non-negative check is local, the upper bound is the band's.
- `entities/shift_band.py`: `effective_break_of`, `has_break_divergence`, and the
  `__post_init__` check of every allocation's break against `nominal_minutes`.
- `entities/schedule.py`: `redeclare_band_break`, `declare_allocation_break`,
  `effective_break_minutes_of`, `has_break_divergence`; uniqueness over
  `(start, end)`; both new mutations obey the no-op clause (return `self` when the
  value is unchanged).
- Acceptance criteria CA2, CA10, CA11, CA11b, CA14, CA16, CA21 and CA23 in the
  concept.

## References

- Related ADRs:
  [ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
  §3 (fork F3: hours = nominal − declared break; the break on the range) and §4
  (intra-shift break and night-hour fiction deferred) — **widened by this ADR, with
  a dated errata there**;
  [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (a)/(c)
  (policies with modes; structural refusal reserved for the impossible) and (d)/(f)
  (the allocation's two stored marks, of which the divergence is the derived
  sibling);
  [ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md) (the single
  hours site, and Decision 4's "derived, never stored" precedent that Alternative C
  falls foul of);
  [ADR 4.1.0009](./4_1_0009-schedule-is-the-single-aggregate-root.md) (the root's
  mutations and where the flags live — the count goes from nine to eleven here);
  [ADR 4.1.0010](./4_1_0010-enabled-band-is-an-element-of-the-day.md) (Alternative A's
  twin-band pathology, and Decision 3's uniqueness key, narrowed here to
  `(start, end)`).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §2 › "Intervalo declarado", "Horas de uma alocação" (`hours(a)`), §3.2, §3.6.3, §3.6.9
  (intra-shift break as deferred policy), §3.6.10.
- [`overview.md`](../overview.md) line 41 (two functions on one band — the case that
  forces the decision), line 46 (the hub's single hours number).
- Concept: [`docs/stages/4.1-scheduling-domain/concept.md`](../stages/4.1-scheduling-domain/concept.md)
  §4, §5.6, §5.7, §5.10, §5.13, §7, §13 (Q3, answered).
- Sponsor decision (2026-09-26, via the master session), verbatim: *"pode ser na
  alocacao e na faixa, mas precisa apontar conflito, e perguntar qual horario quer
  manter"*.
- External (primary, already verified in the domain gate): BRASIL. **Decreto-Lei
  nº 5.452/1943** (CLT), art. 71, § 2º (rest breaks are not counted in the working
  time) and art. 73, § 1º (night hour). Disponível em:
  https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em:
  13 set. 2026.

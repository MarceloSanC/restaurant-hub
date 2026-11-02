---
title: ADR 4.1.0008 — A band that crosses the next cutoff is allowed and belongs to the operational day in which it starts, with nominal duration bounded at 24h and period containment measured at the start instant
description: Architecture Decision Record
when-use: Reference before forbidding or splitting a band that runs past the next cutoff (e.g. 22:00-06:00 with cutoff 05:00), before deciding which operational day such a band counts in, or before measuring whether an allocation is inside the schedule period
keywords: [adr, scheduling, operational-day, cutoff, night-shift, band, split, containment, period, daily-cap]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: 4.1.0008
decision: A band whose range extends past the next cutoff is accepted as a single band and belongs to the operational day in which it starts; the nominal duration is structurally bounded at 24h; containment in the schedule period is measured at the start instant, so a band that starts on the last day of the period and ends after it is valid.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0008 — A band past the next cutoff belongs to its start day

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
§2 fixed the operational day as a 24h window from a configurable cutoff (default
05:00) and the rule that a band belongs to the operational day **in which it
starts**, quoting the sponsor: *"começou sexta as 18h e acabou sabado as 2h conta
como um dia só"*. The same ADR left one case open, in §4, verbatim: *"A range
that crosses the **next** cutoff (e.g. 22:00–06:00 with cutoff 05:00): forbid,
split or allow-and-assign-to-start-day — a gap for the 4.1 concept."* The domain
doc repeats it as gap (b) of §3.2 (line 224) and lists it for this Stage in §6
(line 1086).

The forces:

- A 22:00–06:00 night shift is **8 nominal hours**, below the 10h default of the
  daily cap (ADR 4.1.0003), and the 05:00 default cutoff was itself chosen as the
  end of the CLT night period — the very operation the default exists to serve.
- Splitting at the cutoff is the same move ADR 4.1.0002 already **rejected** as
  Alternative E (slicing at civil midnight): *"one shift becomes two pieces in UI,
  demand and hub"*, and it contradicts "conta como um dia só".
- Structural refusal in this BC is reserved for what cannot be represented:
  everything that is a product rule with an alternative behaviour is a policy with
  a configurable mode (ADR 4.1.0003 (c); concept §5.18).
- Overlap and rest are geometric (doc §3.6.10), so a band that runs into the next
  operational day still collides correctly with bands that start there — the
  overlap policy sees instants, not day labels.
- The period invariant "toda alocação está **dentro do período** da escala"
  (`roadmap.md` 1362, the same line the domain doc cites —
  `shift-scheduling.md` 171) has to be given a precise meaning once a band can end
  after the period's last operational day.

## Decision

1. **Allowed, not forbidden and not split.** A band whose range extends past the
   next cutoff is a single band, and its operational day is the day of its
   `start`. The general rule of ADR 4.1.0002 §2 has no exception, which is what
   keeps every derived quantity (daily cap, accounting week, calendar, hub) from
   needing a special case.
2. **Nominal duration is bounded at 24h** (`InvalidTimeRangeError` above that;
   exactly 24h is accepted). The bound is what keeps "belongs to the day it
   starts" meaningful: a band longer than the operational window would span an
   entire day plus part of another, and "which day does it count in" would stop
   being answerable by looking at its start. It also keeps the value inside the
   range of what a shift can physically be, without touching the configurable cap
   (a 12h band under the 12x36 regime, CLT art. 59-A, remains representable and is
   the daily-cap policy's business, not a structural refusal).
3. **Containment in the period is measured at the `start` instant:**
   `period.contains(calendar.operational_day_of(band.time_range.start))`. A band
   that starts on the period's last operational day and ends after it is valid —
   consistent with the day rule, and the only reading that does not truncate a
   Sunday-night shift out of the week it belongs to.
4. **Consequences stay with the policies.** Overlap with a band of the following
   operational day is a `overlap` violation (4.2, default `block`); hours count in
   the day of the start, which is exactly the ratified formula of doc §3.6.3
   (*"toda alocação `a` … cuja faixa pertence ao dia operacional `d`"*).

## Alternatives considered

### Alternative A — Forbid the band (structural refusal)
- **Description:** reject any range whose `end` falls after the next cutoff.
- **Pros:** every band lies entirely inside one operational window, so daily sums
  never "overflow" a day.
- **Cons:** rejects a legitimate 8h night shift at the default cutoff, i.e. the
  product would refuse the operation its own default was chosen for; the editor
  would have to move the cutoff (a tenant-wide setting) to enter one shift; and it
  turns a product judgement into a structural refusal, which ADR 4.1.0003 reserves
  for physical impossibility.
- **Why rejected:** it is the only option that makes a valid shift unrepresentable.

### Alternative B — Split the band at the cutoff
- **Description:** store 22:00–05:00 and 05:00–06:00 as two bands on two days.
- **Pros:** each piece lies inside one window; per-day sums are exact by
  construction.
- **Cons:** one shift becomes two rows in demand, two cards in the calendar, two
  allocations to fill and two lines in the hub; the declared break would have to
  be apportioned between the pieces; it contradicts the sponsor's "conta como um
  dia só".
- **Why rejected:** ADR 4.1.0002 already rejected this exact shape (Alternative E)
  for the civil-midnight case; the cutoff case is the same argument.

### Alternative C — Allow, and assign the band to the day where most of it falls
- **Description:** keep one band but pick the day by majority of minutes.
- **Pros:** daily sums look "fairer" for a band that mostly falls after the cutoff.
- **Cons:** the day of a band would depend on its length, so extending a shift by
  30 minutes could silently move it to another day — and to another accounting
  week; it contradicts the ratified "belongs to the day in which it starts".
- **Why rejected:** unanchored, and it makes the day non-monotonic under editing.

### Alternative D — Do nothing / leave it undefined
- **Why not acceptable:** `enable_band` has to accept or refuse the value, and
  `operational_day_of` has to return one day. Leaving it undefined means the first
  implementation decides it silently, which is what the gap was raised to prevent.

## Consequences

### Positive
- Night operations are first-class at the default cutoff, without configuration.
- One band, one card, one allocation, one declared break — in UI, demand and hub.
- Every "which day?" question is answered by the start instant alone, with no
  length-dependent rule.
- Period containment has one precise definition, testable without persistence.

### Negative
- A daily sum may include minutes worked after the next cutoff (the band's hours
  count in the day where it starts) — a declared limit, visible in the daily cap
  formula that doc §3.6.3 already ratifies.
- A band may extend beyond the schedule's last day; whatever reads "the week of
  the schedule" (image, e-mail, hub) must accept an end date outside the period.
- The 24h bound is a refusal the editor can hit when entering a nonsense value —
  which is the point. Reporting it is the boundary's concern, governed by
  [ADR 3.6.0003](./3_6_0003-wire-representation-preserves-domain-guarantees.md);
  this ADR states the consequence and does not prescribe 4.5's conduct.

### Neutral / trade-offs accepted
- Two bands of consecutive operational days can overlap in time; that is handled
  by the overlap policy with its configurable mode, not here.
- The 24h bound is reversible: relaxing or tightening it changes one `__post_init__`
  check and its test, with no effect on stored shape.

## Implementation notes

- `TimeRange.__post_init__` carries the 24h bound
  ([ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md));
  `Schedule.__post_init__`, `enable_band` and `reschedule_band` carry the
  containment check, raising `TimeRangeOutsidePeriodError`.
- Acceptance criteria CA1 (24h exactly is accepted), CA5 (22:00–06:00 with cutoff
  05:00 accepted, day = start's day — **and** the band that starts on the period's
  last operational day and ends after it, which is Decision 3's accepted case) and
  CA10 (containment on the rehydration path) in the concept. Decision 3 also
  reshapes the concept's invariant 4: two schedules of one unit have **disjoint
  sets of operational days**, since forbidding overlap *in time* became impossible
  the moment a band could spill past the period's last day (concept §5.4).

## References

- Related ADRs: [ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
  §2 and §4 (the rule and the gap), Alternatives E/F;
  [ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md) (the range's
  form and the single hours site); [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md)
  (`block` reserved for physical impossibility; daily cap default 10h).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §3.2 (gap (b), line 224), §3.6.1, §3.6.3, §3.6.10, §6 (line 1086).
- [`roadmap.md`](../roadmap.md) 1362 ("alocação dentro do período").
- Concept: [`docs/stages/4.1-scheduling-domain/concept.md`](../stages/4.1-scheduling-domain/concept.md)
  §5.5, §5.8, §5.9, §7.
- External (primary, already verified in the domain gate): BRASIL. **Decreto-Lei
  nº 5.452/1943** (CLT), art. 73, § 2º (night period 22h–5h, the rationale of the
  05:00 default) and art. 59-A (12x36 regime). Disponível em:
  https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em:
  13 set. 2026.

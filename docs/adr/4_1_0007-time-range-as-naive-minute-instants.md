---
title: ADR 4.1.0007 — TimeRange is a half-open pair of naive whole-minute instants carrying the declared break, and the single site where allocation hours are counted
description: Architecture Decision Record
when-use: Reference before modeling or changing TimeRange, before adding a second place that computes allocation hours, before storing the operational day on a band, or when a Stage proposes (day, start_time, end_time) as the wire or persisted shape
keywords: [adr, scheduling, time-range, naive-datetime, wall-clock, half-open, whole-minute, break, hours, operational-day, exactness]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: 4.1.0007
decision: The band's time value is a frozen TimeRange holding a half-open pair of naive wall-clock datetimes truncated to whole minutes plus a declared break in minutes; worked_minutes (nominal minus break) is the single site where allocation hours are counted, in integer minutes; the operational day is always derived from the cutoff and never stored on the range.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0007 — TimeRange as naive whole-minute instants

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.2 leaves the
**internal form** of `TimeRange` as an explicit gap for this concept: *"par de
instantes wall-clock × `(dia, hora_início, hora_fim)` — desde que preserve as
invariantes e a comparação direta com a indisponibilidade"* (line 224). The
constraints that surround the gap are all ratified:

- Half-open `[start, end)` semantics, the same ones staff assumes, so that a
  shift and an unavailability can be crossed without conversion
  ([ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) 47–51,
  decision (i); the literal *"adjacent intervals do not conflict"* is on line 50).
- Staff's `UnavailabilityPeriod` is literally a pair of **naive** datetimes and
  rejects tz-aware input (`unavailability_period.py` 31–41;
  [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md) 41–46).
- A band belongs to the **operational day in which it starts**, a 24h window from
  a configurable cutoff, and crossing civil midnight is explicitly *not* a
  special case ([ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md) §2).
- The range **carries the declared break**, and `hours(a) = nominal − break` is a
  **single function** consumed by every policy that sums and by the hub
  (ADR 4.1.0002 §3; doc §3.6.10).
- Overlap and rest are **geometric** — comparisons between instants, never
  between counted hours (doc §3.6.10).

Three policies (daily cap, weekly cap, contracted workload) sum these numbers and
compare them against configured limits, and the hub reports the same number. An
inexact unit therefore drifts into validation results, not just into a display.

## Decision

`TimeRange` is a frozen value object with three fields:

```python
start: datetime         # naive (tzinfo is None), second == microsecond == 0
end: datetime           # naive, whole minute; start < end; end - start <= 24h
break_minutes: int = 0  # 0 <= break_minutes < nominal_minutes
```

1. **A pair of instants, not `(day, start_time, end_time)`.** The dates live
   inside the value, so a band that ends after midnight is one interval, and the
   comparison with staff's unavailability is naive-vs-naive with no conversion.
2. **Naive wall-clock in the unit's timezone.** Tz-aware input is rejected at
   construction, exactly as staff does, which makes every comparison in the BC
   safe by construction. No object of this Stage holds a timezone
   ([ADR 4.1.0005](./4_1_0005-unit-timezone-owned-by-identity.md)).
3. **Whole minutes.** `second` and `microsecond` must be zero. `nominal_minutes`
   is therefore an integer, and so is `worked_minutes = nominal_minutes −
   effective break` — the **single site** of `hours(a)`. Since
   [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md) the break
   exists on the band **and**, optionally, on the allocation, so `worked_minutes`
   takes the effective break as an argument (defaulting to the band's own) instead
   of being a property: one arithmetic expression, two possible inputs. The band's
   uniqueness key inside the aggregate is `(start, end)`, **not** the whole value,
   for the same reason (4.1.0011). Minutes, not `Decimal`
   hours, are the canonical unit of the BC: a 20-minute band is 1/3 h, which
   `Decimal` cannot represent exactly, so sums of thirds would drift while the
   comparison against a configured cap is exact in minutes. Converting to hours is
   a presentation and comparison concern of the consumer (4.2, 4.5, hub).
4. **The operational day is derived, never stored.** `DayCutoff.operational_day_of`
   maps an instant to its operational day; the range does not carry a day field.
   A stored day would be a second source of truth for something the cutoff already
   determines, and would have to be rewritten whenever a band is rescheduled.
5. **`overlaps` is the half-open predicate** `start_A < end_B and start_B < end_A`
   — adjacent bands do not overlap — identical in text and meaning to
   `UnavailabilityPeriod.overlaps`.

The structural bounds (`start < end`, nominal ≤ 24h, `0 ≤ break < nominal`) are
enforced in `__post_init__`, so they hold on every construction path, including
rehydration by the 4.4 mapper.

## Alternatives considered

### Alternative A — `(operational_day: date, start_time: time, end_time: time)`
- **Description:** the shape the UI thinks in: a day plus two clock times, with
  `end_time <= start_time` meaning "ends on the next day".
- **Pros:** compact; the day is explicit; matches a grid layout directly.
- **Cons:** reintroduces the midnight special case that ADR 4.1.0002 abolished
  (every comparison must first reconstruct instants and decide whether to add a
  day); every crossing with staff's unavailability needs a conversion, and the one
  place that forgets it silently compares wrong values; the stored day can
  contradict the cutoff after a settings change.
- **Why rejected:** it trades one ratified guarantee (direct comparison, no
  conversion) for a convenience that belongs to the HTTP/wire layer, where
  ADR 3.6.0003 already governs the representation.

### Alternative B — Pair of aware datetimes (UTC or unit-local)
- **Description:** store instants with `tzinfo`.
- **Pros:** unambiguous absolute time; no conversion needed by timeclock or hub.
- **Cons:** contradicts ADR 3.1.0005 — a declared wall-clock fact must not be
  displaced by a timezone correction — and makes every comparison with staff's
  naive unavailability a mixed-type error waiting to happen; the unit's timezone
  lives in identity, so the domain would need it injected everywhere.
- **Why rejected:** the two regimes (wall-clock bands, UTC audit stamps) are
  ratified in doc §3.9; conversion is the job of whoever knows the timezone.

### Alternative C — Second/microsecond resolution, hours as `Decimal`
- **Description:** no whole-minute invariant; `hours` as a `Decimal` property.
- **Pros:** no truncation rule to explain; hours read naturally.
- **Cons:** `Decimal(20)/60` is inexact, so a week of 20-minute fragments sums to
  a number that depends on rounding; nobody schedules at second resolution, so
  the extra resolution only creates values that cannot be displayed or compared
  reliably.
- **Why rejected:** exactness of the number that three policies compare against a
  cap outranks the convenience of an hours-typed property.

### Alternative D — Do nothing / leave the form to the persistence Stage
- **Description:** keep the domain range abstract and let 4.4 pick a shape.
- **Why not acceptable:** the form is what makes the ratified invariants
  expressible; `worked_minutes` has to exist before 4.2 can sum anything, and the
  gap was explicitly addressed to this concept (doc §6, line 1086).

## Consequences

### Positive
- Crossing band × unavailability is a direct comparison between two pairs of naive
  datetimes — the guarantee ADR 3.1.0001 was written to enable.
- Midnight, and the cutoff, stop being special cases anywhere in the BC.
- One integer counting site (`worked_minutes`); policies and hub cannot disagree.
- Rescheduling a band changes one value; nothing derived has to be rewritten.

### Negative
- The wire and persistence layers must convert to and from the shape the UI wants
  (a day plus two times), and 4.4/4.5 own that mapping.
- The whole-minute rule is a rejection the editor can hit if a client sends
  seconds. The boundary Stage therefore inherits the truncate-or-refuse decision,
  governed by [ADR 3.6.0003](./3_6_0003-wire-representation-preserves-domain-guarantees.md);
  this ADR states the consequence and does not prescribe 4.5's conduct.
- Consumers that want hours divide by 60 themselves.

### Neutral / trade-offs accepted
- Night-hour fiction (CLT art. 73 § 1º), deferred by ADR 4.1.0002 §4, will enter
  as a parameter of this same single site — the shape does not change.
- The bound "nominal ≤ 24h" is fixed by
  [ADR 4.1.0008](./4_1_0008-band-crossing-the-next-cutoff.md), which needs it to
  keep "belongs to the day it starts" total.

## Implementation notes

- `features/scheduling/domain/value_objects/time_range.py`; the cutoff geometry
  lives in `operational_calendar.py` (`DayCutoff.operational_day_of`), so the
  range has no dependency on configuration.
- Validate tz-awareness **before** comparing `start < end`, as
  `unavailability_period.py` does, so the comparison only ever runs naive-vs-naive.
- All defects raise `InvalidTimeRangeError(reason=…)`, following staff's
  `InvalidNameError(entity, reason)` precedent: the message must not describe the
  wrong defect.

## References

- Related ADRs: [ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
  (operational day, `hours(a)`, break); [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md)
  (half-open semantics, decision (i)); [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md)
  (naive wall-clock, conversion by the consumer); [ADR 4.1.0005](./4_1_0005-unit-timezone-owned-by-identity.md)
  (timezone owned by identity); [ADR 3.6.0003](./3_6_0003-wire-representation-preserves-domain-guarantees.md)
  (precedent for the boundary representation); [ADR 4.1.0008](./4_1_0008-band-crossing-the-next-cutoff.md);
  [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md) (the break on
  both levels, the effective break as the argument of this single site, and the
  `(start, end)` uniqueness key).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §2, §3.2 (the gap, line 224), §3.6.1, §3.6.10, §3.9, §6 (line 1086).
- Code: `features/staff/domain/value_objects/unavailability_period.py` 23–49
  (the shape being mirrored: naive pair at 31–32, tz check before comparison at
  34–41, half-open `overlaps` at 43–49).
- Concept: [`docs/stages/4.1-scheduling-domain/concept.md`](../stages/4.1-scheduling-domain/concept.md)
  §4, §5.5–§5.7, §7.

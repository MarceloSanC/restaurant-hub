---
title: ADR 3.1.0005 — Unavailability instants stored as naive wall-clock datetimes in the unit's timezone
description: Architecture Decision Record
when-use: Reference when handling unavailability datetimes anywhere in staff (Stages 3.1–3.4), when scheduling (Step 4) converts them to absolute instants, or before proposing UTC/aware storage
keywords: [adr, staff, workforce, unavailability, datetime, naive, wall-clock, timezone, utc]
status: accepted
created_at: 2026-07-27
updated_at: 2026-07-27
adr_id: 3.1.0005
decision: UnavailabilityPeriod stores NAIVE datetimes meaning wall-clock time in the unit's timezone; timezone-aware values are rejected at construction; conversion to absolute instants is the responsibility of consumers that know the unit's timezone configuration (scheduling/adapters), not of the staff domain.
context_stage: 3.1-staff-domain
bounded_context: staff
---

# ADR 3.1.0005 — Unavailability instants as naive wall-clock datetimes

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (decision i) fixed the
**interpretation** of unavailability instants: they are read "in the unit's timezone"
(workforce §3.6; overview §6 — timezone is per-unit configuration). It did not fix the
**representation** the staff domain stores. Forces:

- The unit's timezone lives in **configuration outside staff** (overview §6); the staff domain
  is pure (stdlib-only, no I/O) and cannot resolve a unit to its timezone.
- The industry default for absolute events is aware/UTC storage — a real alternative.
- What the user declares ("unavailable from 08:00 to 12:00 on the 14th") is a **wall-clock**
  fact of the unit's locality: if the unit's timezone configuration is later corrected, the
  declared wall-clock times must keep meaning 08:00–12:00 locally.
- Python refuses naive×aware comparisons (`TypeError`) — mixing representations inside the
  domain would make the overlap invariant fragile.

## Decision

`UnavailabilityPeriod` stores **naive `datetime` values** whose meaning is **wall-clock time in
the timezone of the unit of the employee's record**. Construction **rejects timezone-aware
values** (`tzinfo is not None` → the period-validation domain error), so the domain never
compares mixed representations. Conversion wall-clock → absolute instant is performed by the
consumer that knows the unit's timezone (scheduling validations in Step 4; adapters if ever
needed) — never by the staff domain.

## Alternatives considered

### Alternative A — Store aware datetimes in UTC
- **Description:** convert to UTC at the boundary; domain holds aware UTC instants.
- **Pros:** unambiguous absolute ordering; industry default for event timestamps.
- **Cons:** the conversion needs the unit's timezone at **write time** — pulling configuration
  into the staff domain or smearing conversion across adapters; a later timezone
  correction/DST rule change silently shifts the local meaning of stored periods (08:00
  becomes 09:00), falsifying what the manager declared; the declared fact is local wall-clock,
  not an absolute instant.
- **Why rejected:** couples the pure domain to per-unit configuration and stores a derived
  value where the source value (wall-clock) is the invariant one.

### Alternative B — Store aware datetimes in the unit's zone
- **Description:** attach the unit's `ZoneInfo` to each stored datetime.
- **Pros:** self-describing values.
- **Cons:** same write-time configuration dependency as A; duplicates the unit's timezone into
  every row, inviting drift when the unit's configuration changes.
- **Why rejected:** the timezone belongs to the unit's configuration, single-sourced — not to
  each period.

### Alternative C — Do nothing (leave representation unspecified until Stage 3.3)
- **Description:** let the persistence stage pick.
- **Pros:** less to decide now.
- **Cons:** the domain invariant (overlap comparisons) already depends on comparability; leaving
  it open makes the 3.1 contract ambiguous and pushes a domain decision into an adapter stage.
- **Why rejected:** representation is part of the VO contract being introduced in 3.1.

## Consequences

### Positive
- Staff domain stays pure and configuration-free; overlap comparisons are always naive×naive.
- Timezone corrections on a unit never mutate the meaning of declared periods.
- Step 4 converts on read with the current unit timezone — the general form it already needs.

### Negative
- Consumers MUST NOT compare staff datetimes with aware datetimes without converting first;
  the rejection at construction plus docstrings are the guard rails.
- Absolute-time edge cases (DST gaps/overlaps of the unit's zone) are resolved by the consumer
  at conversion time, not pre-resolved in storage (accepted: v1 pilot timezone, América/São
  Paulo, currently has no DST).

### Neutral / trade-offs accepted
- Persistence (Stage 3.3) stores `timestamp without time zone` accordingly.

## Implementation notes

- Stage 3.1: `features/staff/domain/value_objects/unavailability_period.py` — `__post_init__`
  rejects `tzinfo is not None` on either bound with the period-validation error.

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (decision i —
  interpretation in the unit's timezone).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.6 (temporal
  interpretation); [`overview.md`](../overview.md) §6 (timezone per unit is configuration).
- Process: [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §2; raised as a
  finding by the Checkpoint A conformity reviewer (2026-07-27) — representation had a real
  discarded alternative and lacked an ADR.

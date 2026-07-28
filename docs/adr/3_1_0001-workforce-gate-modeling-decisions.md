---
title: ADR 3.1.0001 — Workforce gate modeling decisions (half-open datetime unavailability, single contracted weekly workload, copy without login link)
description: Architecture Decision Record
when-use: Reference when modeling unavailability intervals, workload profiles or the copy-employee-to-unit behavior in the staff BC, before changing their semantics, or when tracing why the workforce domain doc states these rules
keywords: [adr, staff, workforce, unavailability, half-open-interval, datetime-granularity, workload, contracted-hours, copy-employee, user-id, domain-gate]
status: accepted
created_at: 2026-07-23
updated_at: 2026-07-23
adr_id: 3.1.0001
decision: Model unavailability as half-open [start, end) datetime intervals (full day as a particular case), store a single contracted weekly workload in hours per fixed-schedule employee (the cap being a scheduling validation policy), and make copy-employee-to-unit duplicate the record without carrying the user_id login link.
context_stage: 3.1-staff-domain
bounded_context: staff
---

# ADR 3.1.0001 — Workforce gate modeling decisions

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

These three decisions were taken at the **domain gate of Step 3** (2026-07-23), while
synthesizing the theory layer [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md)
required by [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1. Per §2 of the
same prompt, every fork with a **real discarded alternative** is registered as an ADR — this ADR
consolidates the three forks of the gate that met that bar. Decision **(i)** was made by the
**human sponsor** (Marcelo, 2026-07-23, via assisted decision); decisions **(ii)** and **(iii)**
were resolved by the master session **anchored in project docs** (roadmap Stage 4.2 / Step 5;
kickoff decisions #2/#5; [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md);
overview §3/§9).

Forces at play:

- The staff BC holds the **data** that scheduling (Step 4) validates and the auto-fill (Step 5)
  optimizes — its shapes must be consumable downstream without conversion, per the ratified
  criterion of progressive scalability (minimal implementation on a scalable shape).
- Overview §3 fixes the use cases: unavailability covers vacations/medical leave in v1; fixed
  schedule means a determined workload; copy-to-unit must not share or leak data between units.
- Person/login (User) is global and unique (kickoff #2), while the employee record is per unit —
  the two must not be conflated by convenience features such as copy.

## Decision

**(i) Unavailability is a DATETIME interval with half-open `[start, end)` semantics.**
An unavailability period is an instant-to-instant interval; a full day is the particular case
`00:00 → 00:00 of the next day`. Two intervals of the same employee overlap iff
`start_A < end_B` **and** `start_B < end_A`; **adjacent intervals do not conflict** (ending at
14:00 and starting at 14:00 is valid). Instants are interpreted in the **unit's timezone**
(overview §6). Rationale: this is the general form Step 4 consumes without conversion when
matching allocation × unavailability, and the standard convention for time ranges — it is what
scheduling assumes when crossing unavailability with shifts (e.g. the glossary's 16h–00h shift);
the UI may start by offering full days only.

**(ii) ONE contracted weekly workload (hours, positive number) per fixed-schedule employee.**
Staff persists a single number. The **hours cap is not staff data**: it is a restaurant-configurable
validation policy in scheduling — roadmap Stage 4.2 lists `workload_policy` and `max_hours_policy`
as **distinct** policies; the contracted workload feeds the former, the cap is configuration of the
latter. The same number is read as the **fairness target** by the auto-fill (Step 5).

**(iii) Copying an employee to another unit does NOT carry the `user_id` login link.**
Copy duplicates the record in the destination unit; linking a record to a login is an **explicit
per-record decision** (Stage 3.5). The same person may hold several employee records (one per
unit) pointing at the **same** global User — compatible with the n:n user↔unit membership
([ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md)) — but only ever through
explicit linking, never as a side effect of copy.

## Alternatives considered

### Decision (i) — Alternative A: whole-day granularity
- **Description:** unavailability as a date range (whole days only).
- **Pros:** simplest UI and model; covers vacations/medical leave.
- **Cons:** cannot express partial-day unavailability (e.g. a morning medical appointment);
  migrating stored data to a finer granularity later is expensive.
- **Why rejected:** fails the progressive-scalability criterion — the shape would have to be
  remade for Step 4.

### Decision (i) — Alternative B: whole-day OR named period of day
- **Description:** unavailability as either a full day or a named period (manhã/tarde/noite/madrugada).
- **Pros:** matches the shift-preference vocabulary.
- **Cons:** mixes two granularities in one concept; depends on period→time-range boundaries that
  **staff does not fix** (the mapping belongs to scheduling — see the workforce doc §3.5).
- **Why rejected:** couples staff to a scheduling configuration and still cannot express arbitrary
  partial intervals.

### Decision (i) — Alternative C: closed intervals `[start, end]`
- **Description:** datetime intervals where adjacency counts as overlap.
- **Pros:** none material.
- **Cons:** adjacent periods (end of one == start of the next) would be rejected artificially;
  diverges from the time-range semantics of shifts in the glossary (16h–00h).
- **Why rejected:** sponsor decision (2026-07-23) — half-open is the standard convention for time
  ranges and what Step 4 assumes.

### Decision (i) — Alternative D: defer the overlap definition to the Stage 3.1 concept
- **Description:** state the non-overlap invariant in the domain doc without a precise definition.
- **Pros:** less to decide at the gate.
- **Cons:** leaves a load-bearing invariant without a precise definition in an `accepted` domain doc.
- **Why rejected:** the invariant is only testable and consumable downstream if its definition is
  canonical.

### Decision (ii) — Alternative A: two fields per employee (target + cap)
- **Description:** persist both the contracted target and a per-employee hours cap in staff.
- **Pros:** cap visible next to the employee.
- **Cons:** duplicates in staff what roadmap 4.2 defines as a **restaurant-level configurable
  validation policy** (`max_hours_policy`), inviting drift between the two; overloads staff with
  scheduling behavior.
- **Why rejected:** the docs already split the concerns — one number in staff (semantics: base of
  `workload_policy` validation and fairness target of Step 5), cap in scheduling configuration.

### Decision (iii) — Alternative A: copy carries the login link
- **Description:** copying an employee to another unit also copies `user_id`.
- **Pros:** one less manual step when the person will log in at both units.
- **Cons:** turns an explicit access decision into a silent side effect; conflates person (global
  User, kickoff #2) with the per-unit record; bypasses the Stage 3.5 flow that creates the
  membership for the destination unit.
- **Why rejected:** linking is an explicit per-record decision; copy must duplicate data, not
  propagate access.

### Do nothing / status quo
Not applicable as a standing option: the Step 3 domain gate **requires** these semantics to be
fixed before Stage 3.1 — leaving them open would push the fork into each Stage concept, which is
exactly the drift the gate exists to prevent.

## Consequences

### Positive
- Step 4 consumes unavailability and workload without conversion or re-interpretation.
- Adjacent unavailability periods compose naturally (no artificial rejections).
- Copy-to-unit cannot leak access; access grants remain auditable, explicit acts (Stage 3.5).
- One number, two documented readings (validation base + fairness target) — no duplicate fields
  to drift.

### Negative
- Partial-day granularity makes the v1 UI slightly richer than a date picker (mitigated: UI may
  offer whole days only, stored as the particular case).
- Users copying an employee who already has a login must link the new record explicitly —
  one extra step, by design.

### Neutral / trade-offs accepted
- The per-employee hours cap, if a restaurant wants one, lives only as scheduling configuration —
  staff has no field for it.
- Recurrence of unavailability stays out of v1 (overview §3 limits the use case to absolute
  periods); the instant-to-instant shape admits it as an additive evolution.

## Implementation notes

- Lands in Stage 3.1 (`features/staff/domain/value_objects/{workload_profile,unavailability_period}.py`)
  and Stage 3.2 (copy use case). The theory these decisions serve lives in
  [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.3, §3.6, §3.7.
- The non-overlap invariant is per employee, using the half-open definition above.

## References

- Related ADRs: [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md) (UnitMembership,
  n:n user↔unit); [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md)
  (domain-doc category this gate produces).
- [`roadmap.md`](../roadmap.md) — Stage 4.2 (`workload_policy` × `max_hours_policy` as distinct
  policies); Step 5 (fairness target of auto-fill); Stage 3.5 (explicit login link per record);
  Stage 3.1 (unavailability invariant).
- [`overview.md`](../overview.md) — §3 (copy without sharing; unavailability use cases; fixed ×
  on-demand profiles), §6 (timezone per unit; configurable validations), §9 (glossary — shift
  time ranges).
- Kickoff decisions (project memory, 2026-07-16/19): #2 (global unique e-mail/User), #5 (fixed
  schedule = hours/week).
- Process: [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1 (domain gate),
  §2 (fork with real alternative → ADR); sponsor decision (i) on 2026-07-23.

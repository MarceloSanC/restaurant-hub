---
title: ADR 4.1.0009 — Schedule is the single aggregate root; bands, demands and assignments are internal entities reached only through it, and the root carries the version counter and a snapshot of the operational calendar
description: Architecture Decision Record
when-use: Reference before making ShiftBand, ShiftDemand or Assignment an aggregate root of its own, before adding a repository or use case that writes one of them directly, before moving the version counter out of the domain, or before reading the tenant's calendar live inside the aggregate
keywords: [adr, scheduling, aggregate, aggregate-root, containment, invariants, version, optimistic-concurrency, calendar-snapshot, allocation-flags]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: 4.1.0009
decision: Schedule is the only aggregate root of the scheduling domain in v1; ShiftBand, ShiftDemand and Assignment are internal entities held by containment and mutated only through the root, which also carries the version counter incremented by every mutation and a snapshot of the operational calendar taken when the schedule is created; the two allocation flags are attributes of Assignment.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0009 — Schedule is the single aggregate root

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.1 lists
`Schedule`, `ShiftDemand` and `Assignment` as the entities of this Stage and says
that `Schedule` being the **aggregate root** is a *"proposta do gate (†), a
confirmar na 4.1"* (`shift-scheduling.md` §3.1 › "a confirmar na 4.1"); §6 lists the confirmation for this Stage
(`shift-scheduling.md` §6 › "Schedule como raiz do agregado — confirmar"), together with where the allocation flags and the hours counting
live.

What has to be guarded, from the ratified invariants:

- at most one demand per (band, function), and no duplicated band (doc §3.3;
  [ADR 4.1.0010](./4_1_0010-enabled-band-is-an-element-of-the-day.md));
- an assignment references **a demand of the same schedule**, and the same
  employee does not take two slots of the same demand (doc §3.4);
- every band lies inside the schedule's period
  ([ADR 4.1.0008](./4_1_0008-band-crossing-the-next-cutoff.md));
- every mutation increments the schedule's **version**, which the server compares
  before applying a change ([ADR 4.1.0001](./4_1_0001-every-saved-change-is-the-live-schedule.md) §2);
- the two flags of the allocation ("counts toward workload", "function exception")
  are attributes of the allocation, which ADR 4.1.0003 §Implementation notes
  places on `Assignment` **in this Stage**.

Two further forces:

- The operational day of every band depends on the **cutoff**, a per-tenant
  setting; the same is true of the period's alignment and the week start. Whether
  changing those settings affects **existing** schedules is explicitly a gap for
  the 4.3 concept (doc §3.1).
- Staff's precedent is an aggregate root holding an internal collection whose
  pairwise invariant is validated in `__post_init__` — including on the
  rehydration path (`employee.py` › `Employee.__post_init__`), a hardening that the 3.1 execution
  added after a surviving-mutation finding.

## Decision

1. **`Schedule` is the only aggregate root** of the BC in v1. `ShiftBand`,
   `ShiftDemand` and `Assignment` are **internal entities**: they have their own
   ids (so the audit trail of 4.4 and the routes of 4.5 can address them), they
   are `frozen` and compare by identity, and they are **only reachable and only
   mutated through the root**.
2. **Containment, not references by id.** A schedule holds a tuple of bands, a
   band holds a tuple of demands, a demand holds a tuple of assignments. The
   ratified invariant *"uma alocação referencia … uma demanda da mesma escala"*
   becomes true **by construction** rather than by validation, and every
   uniqueness rule is enforced by the level that owns the collection.
3. **Eleven mutations on the root**, each returning a new instance with
   `version + 1`: `enable_band`, `reschedule_band`, `redeclare_band_break`,
   `disable_band`, `declare_demand`, `change_demand_quantity`, `withdraw_demand`,
   `assign`, `unassign`, `declare_workload_counting`, `declare_allocation_break`.
   The last two break-related verbs come from
   [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md); the count
   was nine before it. A mutation called with the value it already holds returns
   `self`, leaving the version untouched — without that clause an optimistic check
   in 4.4 would make another editor lose work over a no-op (precedent:
   `workforce.md` §3.1, "idempotentes no valor"). The version counter lives in the
   domain because the law *"every mutation increments"* is a property of the
   aggregate and is testable without a database; 4.4 owns the **column** and the
   optimistic comparison, 4.5 the refusal status.
4. **The root carries a snapshot of the `OperationalCalendar`** (week start and
   cutoff) taken when the schedule is created. The aggregate is then
   self-contained: `operational_day_of`, containment and `bands_of` need no
   injected configuration, and changing the tenant's cutoff cannot silently
   re-slice a schedule that is already live (an employee's Friday shift will not
   become Thursday's without any mutation or audit entry). This **frames** the 4.3
   gap — it makes "only future periods" the cheap default — but does not decide
   it: an explicit migration use case remains possible in 4.3.
5. **The allocation flags are attributes of `Assignment`**
   (`counts_toward_workload`, default `True`; `function_exception`, default
   `False`; and, since
   [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md), an optional
   `break_minutes`), and **the hours of an allocation are read from the band that
   contains it** through `Schedule.worked_minutes_of`, whose only computation site
   is `TimeRange.worked_minutes`
   ([ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md)) — fed with
   the allocation's **effective** break. The break divergence is a **derived**
   mark, not a stored field. The domain never verifies `function_exception` against
   staff: the record's function set lives in another BC and arrives by port in 4.3,
   and whether the exception is re-evaluated later is a 4.2 gap
   ([ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (f)),
   which is why v1 exposes no mutation for it.
6. **Every invariant is validated in `__post_init__`** at its owning level, pairwise
   over whole collections, so the 4.4 mapper cannot rehydrate an invalid aggregate.
   This explicitly includes the two rules that were only enforced by factories
   before the Checkpoint A review: the period is **aligned to the snapshot
   calendar's week start** (`InvalidSchedulePeriodError`), and internal ids
   (`ShiftBandId`, `ShiftDemandId`, `AssignmentId`) are **unique across the whole
   aggregate** (`DuplicateEntityIdError`). Without the first, `calendar.week_start`
   would be dead data inside the root; without the second, `locate_*` would not be
   a function. Since
   [ADR 4.1.0012](./4_1_0012-one-record-occupies-at-most-one-slot-per-band.md)
   (sponsor, 2026-09-27) it also includes the band-level rule that one record
   occupies **at most one slot per band**, checked pairwise over the flattened
   allocations of the band's demands — the level that owns them.

## Alternatives considered

### Alternative A — Three aggregate roots (Schedule, ShiftDemand, Assignment) referencing each other by id
- **Description:** the flat shape the roadmap's file list suggests; each entity has
  its own repository, and cross-entity rules are checked in the use case.
- **Pros:** smaller objects to load and persist; a single assignment can be written
  without touching the schedule; scales to very large periods.
- **Cons:** every invariant of doc §3.3/§3.4 becomes a query-plus-check in the
  application, i.e. a race between two editors that the version check no longer
  covers (the schedule's version would not change when an assignment is written);
  "a demanda da mesma escala" becomes a validation that can be forgotten; the
  repo's own precedent for cross-aggregate rules
  ([ADR 3.2.0001](./3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md))
  shows the cost of that path, and it was accepted there because the entities were
  genuinely independent — these are not.
- **Why rejected:** the consistency boundary of the ratified invariants is the
  schedule; splitting it moves the invariants out of the only place that can hold
  them atomically.

### Alternative B — Single root, but internal entities referenced by id inside the root (flat tuples + parent ids)
- **Description:** `Schedule` holds three flat tuples; demands carry `band_id`,
  assignments carry `demand_id`.
- **Pros:** maps 1:1 to three tables; a self-contained assignment object is easy to
  hand to the 4.2 evaluator.
- **Cons:** referential integrity inside the aggregate becomes a validation
  ("every `demand_id` exists") instead of a structural fact; the uniqueness rules
  need grouping logic; the shape allows an orphan demand to be constructed and then
  rejected, which is exactly the state `ddd-tactical-patterns` says should be
  unrepresentable.
- **Why rejected:** containment gives the same persistence mapping (4.4 writes
  three child tables either way) without the orphan states.

### Alternative C — Version counter only in persistence (4.4)
- **Description:** the domain has no `version`; the repository bumps a column.
- **Pros:** one less field in the domain; matches the letter of ADR 4.1.0001, which
  names 4.4 and 4.5 as the candidate Stages.
- **Cons:** the law "every mutation increments" cannot be expressed or unit-tested;
  a mutation added later could bypass it, and the bypass would only show as a lost
  update in production.
- **Why rejected:** keeping the counter in the domain does not take anything away
  from 4.4 (which still owns the column and the comparison) and makes the law
  provable without a database.

### Alternative D — Read the tenant's calendar live instead of snapshotting it
- **Description:** the aggregate takes the calendar as an argument wherever it needs
  the cutoff.
- **Pros:** one source of truth for the setting; no duplication per schedule.
- **Cons:** changing the cutoff silently changes which day past bands belong to,
  with no mutation and therefore no audit entry; every method that touches a day
  grows a configuration parameter, and the 4.2 policies inherit it.
- **Why rejected:** live re-slicing of a published schedule is a data change no one
  asked for; the snapshot keeps the aggregate pure and leaves the migration
  question where the domain doc put it (4.3).

### Alternative E — Do nothing / leave the root unconfirmed
- **Why not acceptable:** the doc explicitly asked this Stage to confirm the root
  (`shift-scheduling.md` §6 › "Schedule como raiz do agregado — confirmar"); without it, 4.3 would have to guess the transaction boundary and
  4.4 the write granularity.

## Consequences

### Positive
- One transaction = one aggregate; the version check of ADR 4.1.0001 covers every
  change to the schedule, including a single assignment.
- "The allocation belongs to a demand of this schedule" and "the demand belongs to
  a band of this schedule" cannot be violated, not even by a mapper.
- The aggregate is pure: no configuration, no clock, no timezone, no port.
- The audit trail of 4.4 has stable ids to name what changed.

### Negative
- Any mutation loads and rewrites the whole aggregate; for a 7-day period with the
  pilot's volume this is cheap, but 4.4 owns the loading strategy and may need a
  narrower write path if periods grow.
- A frozen nested tree means each mutation rebuilds the path down to the changed
  element; more code in the root than a flat shape would need.
- The calendar is duplicated per schedule, and a schedule created before a settings
  change keeps the old calendar — visible, declared, and the 4.3 gap's input.

### Neutral / trade-offs accepted
- The 4.2 evaluator needs allocations paired with their band and function;
  `locate_assignment` and `worked_minutes_of` give it that, and the shape of the
  evaluator's input stays a 4.2 decision.
- Whether `disable_band`/`withdraw_demand` refuse or cascade when allocations exist
  was a product question at the time of writing; the sponsor answered **refuse**
  on 2026-09-26 (*"Recusa, desaloque primeiro (Recomendada)"*, concept §5.21) — and
  either answer keeps this aggregate shape, which is why the question never blocked
  this ADR.

## Implementation notes

- `features/scheduling/domain/entities/{schedule,shift_band,shift_demand,assignment}.py`.
  The root is the only module with mutation methods that a use case calls; the
  child entities expose `with_*`/`without_*` helpers used **by the root**.
- Follow the 3.1 hardening: validate pairwise over the whole collection in
  `__post_init__` (not just consecutive pairs) — the finding that survived mutation
  testing in Stage 3.1.
- Reads never return a mutable structure: tuples in, tuples out
  (`ddd-tactical-patterns`, "don't leak the aggregate from inside").

## References

- Related ADRs: [ADR 4.1.0001](./4_1_0001-every-saved-change-is-the-live-schedule.md)
  (no draft; version counter for optimistic concurrency);
  [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md)
  (§Implementation notes: both flags land on `Assignment` in 4.1);
  [ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md) (single hours
  site); [ADR 4.1.0008](./4_1_0008-band-crossing-the-next-cutoff.md) (containment
  measured at the start); [ADR 4.1.0010](./4_1_0010-enabled-band-is-an-element-of-the-day.md)
  (the band as an element and demand cardinality);
  [ADR 3.2.0001](./3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md)
  (the cost of guarding rules across aggregates);
  [ADR 3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md)
  (staff's last-write-wins, superseded for the schedule by 4.1.0001);
  [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) › "The state is a boolean, not a dated event"
  (domain without `Clock`);
  [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md) (the optional
  break on `Assignment`, the effective break feeding the single hours site, the
  derived divergence mark, and the two extra mutations that take the count from
  nine to eleven).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §3.1 › "a confirmar na 4.1", "O período é não vazio, contíguo e alinhado" (the gate's proposal that `Schedule` is the root, to be
  confirmed here; the period invariant that Decision 6 now enforces), §3.3, §3.4,
  §3.5, §6 › "Schedule como raiz do agregado — confirmar".
- Code: `features/staff/domain/entities/employee.py` › `Employee.__post_init__` (pairwise validation on
  every construction path, including rehydration).
- Skill `ddd-tactical-patterns` (§Aggregate, §Invariants, §DON'T).
- Concept: [`docs/stages/4.1-scheduling-domain/concept.md`](../stages/4.1-scheduling-domain/concept.md)
  §4, §5.2, §5.10–§5.22, §7, §13.

---
title: ADR 3.2.0006 — The employee record has a termination state AND a guarded definitive removal
description: Architecture Decision Record
when-use: Reference when implementing employee deactivation/reactivation or deletion (Stages 3.2–3.4), when designing the employee table (3.3), when Step 4 adds allocations that reference the record, or before changing the default of the unit listing
keywords: [adr, staff, employee, lifecycle, active, inactive, termination, rehire, hard-delete, guard, sponsor, fork-f1]
status: accepted
created_at: 2026-08-08
updated_at: 2026-09-14
adr_id: 3.2.0006
decision: The Employee record carries an active/inactive state with deactivate (termination) and reactivate (rehire) — the unit listing hides inactive records by default and the history survives — AND a definitive delete_employee guarded by the absence of references, for the cadastre created by mistake.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0006 — Employee lifecycle: termination state plus guarded definitive removal

> ⚠️ **Errata (2026-09-14):** Implementation notes — "Step 4: when allocations reference the employee, the FK becomes the hard half of the `delete` guard" is superseded: there is no foreign key between bounded contexts; the `delete` guard (L-E5, `EmployeeInUseError`) is a **reverse query port** declared in staff and implemented outside staff over a scheduling query, and termination is reconciled on read by scheduling — ver [ADR 4.1.0006](./4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The roadmap asks for "CRUD de funcionário" and the **D** had no answer in any ratified source:
`overview.md`, [`workforce.md`](../domain/staff/workforce.md), the roadmap and ADRs
3.1.0001–3.1.0006 **never mention** termination, dismissal or removal of an employee record
(verified by textual search while writing the Stage 3.2 concept). The asymmetry was itself the
signal: for the **job function** a lifecycle had been decided with its own ADR, and for the
**employee** — the record that actually has a story — nothing had.

The Stage 3.2 concept author returned this as **fork F1** to the master session, with four
alternatives. The question could not be deferred: Stage 3.3 designs the table immediately after, so
deciding later costs a migration.

Forces:

- An employee who leaves must stop appearing in the unit's list and in the scheduling picker of
  Step 4 — otherwise the manager schedules a person who no longer works there.
- The record carries **history the hub reads** (overview §3, "previsto × realizado" per unit and
  per function). Erasing it erases the past.
- A cadastre created by mistake (wrong unit, duplicate, typo) has no history and should be fully
  removable — the same reason the job function keeps a delete.
- The ratified progressive-scalability criterion: minimal implementation on a shape Step 4 consumes
  without remodeling.

The **human sponsor decided on 2026-08-08** (via the master session), choosing **option (d)** — the
concept had recommended (c).

## Decision

**The employee record has both halves of the lifecycle.**

1. **Termination state.** `Employee` carries `active: bool = True`, with `deactivate()` (termination)
   and `reactivate()` (rehire), **idempotent in value** — deactivating an already-inactive record is
   not an error. Stage 3.2 adds the field and the transitions to
   `features/staff/domain/entities/employee.py`, with tests (declared expansion of the Stage's
   target layer), and exposes `DeactivateEmployeeUseCase` / `ReactivateEmployeeUseCase`.
2. **The listing hides the inactive by default.** `EmployeeRepository.list_by_unit(..., *,
   include_inactive: bool = False)`; the record stays addressable by id, keeps its whole cadastre,
   and **keeps counting as a reference** for the job-function removal guard — a terminated record
   still points at its functions, so deleting one would corrupt it.
3. **Definitive removal, guarded.** `DeleteEmployeeUseCase` + `EmployeeRepository.delete` remove the
   record permanently, and are **refused with `EmployeeInUseError` when anything references it**. In
   v1 nothing references an employee record, so the guard is vacuously satisfied — it is published
   now as the **contract Step 4 fills** when allocations start pointing at employees. Publishing it
   now is deliberate: Stage 2.2 shipped a port without its insertion law and Stage 2.3 had to
   retrofit the contract ([ADR 2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md)); this ADR
   refuses to repeat it.

### Why this is the opposite of ADR 3.2.0005, on purpose

[ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) removes the lifecycle from the
**job function** on the grounds that an unused function is **inert**. An employee record is not:

| | Unused job function | Terminated employee |
|---|---|---|
| Shows up in operational flows when unused? | **No** — nothing references it, so nothing lists it | **Yes** — it is a member of the unit; it appears in the unit list and in the Step 4 picker |
| Schedulable? | Not by itself | **Yes** — the record is exactly what Step 4 allocates |
| Carries history of its own? | No — history lives in the allocations that reference it | **Yes** — worked shifts, the hub's "previsto × realizado" |
| Cost of having no state | Zero | The manager schedules someone who left |

The asymmetry is a **consequence of the same criterion applied to two different objects**, not an
inconsistency. Both ADRs state it, from their own side.

## Alternatives considered

These are the four alternatives of fork F1 as returned to the sponsor.

### Alternative A — Out of scope for Stage 3.2
- **Description:** no exit operation at all; the record is only created and edited.
- **Pros:** zero cost now; the decision can be taken later.
- **Cons:** an employee who leaves keeps appearing in the unit list and, from Step 4 on, in the
  scheduling picker, with no action available to the manager; and "later" is after Stage 3.3 has
  created the table, so it costs a migration.
- **Why rejected (sponsor, 2026-08-08):** it leaves the product visibly wrong and moves the cost to
  the most expensive moment.

### Alternative B — Definitive removal only (hard delete, guarded)
- **Description:** `delete_employee` when nothing references the record; no state.
- **Pros:** one use case, one guard; nothing to filter in listings.
- **Cons:** once Step 4 exists, anyone who ever worked a shift can **never** be removed — and has no
  other exit either, so they stay in the list forever. The extra who worked one day in January
  becomes permanent. It also erases the hub's history when it *does* succeed.
- **Why rejected:** it breaks precisely for the people the product is about, and only after Step 4
  ships — the most expensive moment to discover it.

### Alternative C — Termination state only (soft state, no delete)
- **Description:** `active`/`inactive` with the two transitions; no definitive removal.
- **Pros:** history survives, the unit list stays clean, rehiring is reactivating; it is the shape
  Step 4 and the hub consume.
- **Cons:** a cadastre created by mistake (wrong unit, duplicate) can only be *deactivated*, so it
  lingers forever behind `include_inactive` and in every export.
- **Why rejected (sponsor, 2026-08-08):** right for the person who left, wrong for the record that
  should never have existed. This was the concept's recommendation; the sponsor extended it.

### Alternative D — Both (**chosen**)
- **Description:** soft state for who has history, guarded hard delete for the cadastre created by
  mistake.
- **Pros:** each case gets the operation that fits it; the guard makes the destructive path
  impossible exactly when it would destroy history.
- **Cons:** one more use case, one more error, one more guard to test; and in v1 the guard has no
  producer, so it is a declared contract rather than an exercised path.
- **Why chosen (sponsor, 2026-08-08):** the two operations answer two different questions, and the
  cost of the second is one use case plus one law — paid once, here, instead of as a migration
  after Step 4.

### Do nothing / status quo
Not viable: "CRUD de funcionário" is in the roadmap scope of this Stage and Stage 3.3 designs the
table next; an undecided **D** becomes a migration.

## Consequences

### Positive
- The manager has an exit for both cases, and neither one destroys the hub's history.
- Stage 3.3 creates the `active` column from the start — no migration.
- Step 4 receives a record shape it can filter (`active`) and a removal law already written, so it
  adds its reference without retrofitting the port contract.
- Rehiring is one reactivation, preserving the person's unavailability history and preferences.

### Negative
- **Already-merged Stage 3.1 code changes.** Adding the field and two transitions to `Employee` is
  an additive edit to a Stage that is `done` — declared as an expansion of Stage 3.2's target layer,
  with a dated reconciliation note in `roadmap.md` at closing.
- `EmployeeInUseError` ships **without a producer** in v1. Mitigated by an explicit acceptance
  criterion that states the absence (rather than pretending the path is exercised) and by the law
  being documented in the `Protocol`.
- Every listing call site now has a default that hides data; a future report that needs everyone
  must remember `include_inactive=True`. Accepted: the default protects the common case
  (scheduling), and the flag is explicit at the signature.

### Neutral / trade-offs accepted
- **The state is a boolean, not a dated event.** There is no `terminated_at`, because staff v1
  carries no `Clock` ([ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md)) and
  no entity has audit timestamps. "Since when" is an additive field the day a consumer asks for it.
- **The copy carries `active` as-is.** `copy_employee_to_unit` duplicates the whole aggregate
  ([ADR 3.2.0003](./3_2_0003-copy-employee-full-duplication.md)), and the state is part of it.
  Copying a terminated record produces a terminated record in the target unit — hidden from the
  default listing and unschedulable — which is a state already reachable by create-then-deactivate.
  Refusing the copy instead would add a fourth item to an exclusion list that ADR 3.2.0003 closed at
  three, to prevent a degenerate case that harms nothing.
- A terminated record still blocks the deletion of its job functions
  ([ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md), guard). That is intended: the
  reference is real and the cadastre would be corrupted.

## Implementation notes

- Stage 3.2, dedicated Task: `active: bool = True` on
  `src/restaurant_hub/features/staff/domain/entities/employee.py`, plus `deactivate()`/`reactivate()`
  via `dataclasses.replace` (frozen-entity pattern), with tests mirroring the ones being removed from
  `test_job_function.py` by ADR 3.2.0005 — including idempotency in value.
- `EmployeeResult` gains `active: bool`; `ListEmployeesQuery` gains `include_inactive: bool = False`.
- Stage 3.3: boolean column `active` (default true, not null); the listing filters on it; the
  `RESTRICT` FK employee→function is unaffected by the employee's state.
- Step 4: when allocations reference the employee, the FK becomes the hard half of the `delete`
  guard and `EmployeeInUseError` acquires its producer.

## References

- Related ADRs: [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) (the opposite
  decision for the job function, and the asymmetry rationale);
  [ADR 3.2.0003](./3_2_0003-copy-employee-full-duplication.md) (the copy carries the state);
  [ADR 2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md) (why the removal law is published before
  it has a producer); [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md) (no
  `Clock` in staff v1, hence a boolean and not a date).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.1 (record per unit);
  [`overview.md`](../overview.md) §3 (the hub reads the history).
- [`docs/stages/3.2-staff-application/concept.md`](../stages/3.2-staff-application/concept.md) §5.7,
  §7, §13 (fork F1 and the four alternatives as returned).
- Authorship: **human sponsor, 2026-08-08**, via the master session — fork F1 of the Stage 3.2
  concept, decided on option (d).

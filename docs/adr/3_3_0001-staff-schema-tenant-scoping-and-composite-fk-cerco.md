---
title: ADR 3.3.0001 — The staff schema carries tenant_id only where cross-tenant linkage is representable, anchored by composite foreign keys
description: Architecture Decision Record
when-use: Reference before adding a table to the staff schema, before adding a tenant column to a child table, before changing the employee aggregate's child tables, or when deciding between child tables and a JSONB column for an aggregate collection
keywords: [adr, schema, staff, multi-tenancy, tenant-id, composite-fk, restrict, cascade, aggregate, child-tables, jsonb, check-constraint]
status: accepted
created_at: 2026-08-10
updated_at: 2026-08-10
adr_id: 3.3.0001
decision: job_functions, employees and employee_job_functions carry a NOT NULL tenant_id — the last one anchored by two composite foreign keys that make cross-tenant assignment unrepresentable — while employee_unavailabilities and employee_shift_preferences do not, and the aggregate's collections live in child tables rather than JSONB so that the port's guard laws rest on real foreign keys
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0001 — Staff schema: tenant scoping and the composite-FK cerco

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ROADMAP-3 fixes multi-tenancy as row-level `tenant_id` in a single PostgreSQL for
v1. ADR 3.2.0002 pushed `tenant_id` into every port signature of staff, so every
query is `(tenant_id, key)` and never the key alone.

Two of the twelve port laws published by Stage 3.2 do not describe a single
aggregate — they describe the relationship **between** aggregates:

- **L-JF3** — deleting a job function referenced by any employee (active *or*
  terminated) must raise `JobFunctionInUseError`, and the function must remain
  readable.
- **L-E4** — every id in `employee.job_function_ids` must exist **in the same
  tenant**; a missing one raises `JobFunctionNotFoundError` and nothing is
  written. The port docstring states explicitly that the race the fake simulates
  must become a *translated* error in this Stage, not a raw `IntegrityError`.

The `Employee` aggregate also owns two collections — unavailability periods and
the declared shift preference — plus a workload profile that is a **union type**
(`FixedSchedule | OnDemand`) whose "exactly one profile" property is currently a
static guarantee of mypy, with no runtime check.

Identity's Stage 2.3 established the criterion for where the tenant discriminator
goes (ADR 2.3.0002): it is denormalised **only where it anchors a fence**.
`unit_memberships` carries it `NOT NULL` with two composite FKs; `sessions` does
not carry it at all, because the port could not supply one.

## Decision

**Five tables, and the tenant column follows the identity criterion literally.**

`job_functions`, `employees` and `employee_job_functions` carry
`tenant_id NOT NULL`. `employee_unavailabilities` and
`employee_shift_preferences` do not.

`employee_job_functions` is the staff analogue of `unit_memberships`: it is the
only table where a cross-tenant link is *representable* (employee of tenant A
pointing at a job function of tenant B). It is fenced by **two** composite
foreign keys — `(employee_id, tenant_id) → employees(id, tenant_id)` and
`(job_function_id, tenant_id) → job_functions(id, tenant_id)` — which requires
`UNIQUE (id, tenant_id)` anchors on both parents (PostgreSQL demands a unique
index covering the referenced columns). One FK alone would leave the other side
free, which is half a fence and no guarantee.

The FK to `job_functions` is `ON DELETE RESTRICT` — that is L-JF3, enforced by
the database rather than hoped for by the application, and it counts terminated
employees because the link table does not know about `active`. The FK to
`employees`, and the FKs of the other two child tables, are `ON DELETE CASCADE`:
they are parts of the aggregate and die with it.

**The aggregate's collections are child tables, not JSONB.** A `jsonb` array of
job-function ids is not referenceable, so L-JF3 and L-E4 would fall back to
check-then-act — precisely what Stage 3.2 escaped.

**Domain invariants that the database can carry, it carries.** The workload
profile becomes `workload_kind text NOT NULL` plus `weekly_hours numeric NULL`
with an *iff* CHECK, `(workload_kind = 'fixed') = (weekly_hours IS NOT NULL)`,
over `NOT NULL` columns — the `NOT NULL` is load-bearing for the same
three-valued-logic reason as `ck_users_tenant_iff_platform_admin`. The period
table carries `CHECK (start_at < end_at)` and a primary key of
`(employee_id, start_at)`, which is legitimate precisely because periods of one
employee never overlap, so `start_at` is unique per employee.

**Unavailability instants are `TIMESTAMP` without time zone**, unlike every
timestamp in identity. `UnavailabilityPeriod` *rejects* tz-aware datetimes
(ADR 3.1.0005 — wall clock in the unit's time zone), so a `timestamptz` column
plus the identity mapper's "always return aware UTC" rule would make rehydration
raise `InvalidUnavailabilityPeriodError` on perfectly valid data.

## Alternatives considered

### Alternative A — `tenant_id` on every table, including the two leaf child tables
- **Description:** denormalise the discriminator everywhere, "for symmetry".
- **Pros:** uniform; a future tenant-wide purge is a single predicate per table.
- **Cons:** on `employee_unavailabilities` and `employee_shift_preferences` the
  column anchors nothing — the only reference is `employee_id`, whose parent
  already carries the tenant — so it is a denormalisation that can drift out of
  sync with its parent and that no constraint can catch.
- **Why rejected:** ADR 2.3.0002 already settled the criterion, and applying it
  honestly means these two tables do not qualify. Symmetry is not a fence.

### Alternative B — single FK on `employee_job_functions` (no tenant column)
- **Description:** `job_function_id → job_functions(id)` and
  `employee_id → employees(id)`, plain.
- **Pros:** simpler; no anchor unique indexes needed.
- **Cons:** cross-tenant assignment becomes representable at the database level;
  L-E4's "or existing in another tenant" clause would rest entirely on the
  application's pre-check, which is exactly the race the law was written to close.
- **Why rejected:** it converts a structural guarantee into a discipline.

### Alternative C — JSONB column for `job_function_ids` and the two collections
- **Description:** store the aggregate as one row with `jsonb` columns.
- **Pros:** one-statement writes; no child tables; naturally atomic.
- **Cons:** no foreign key, so `RESTRICT` is impossible and L-JF3 becomes
  check-then-act; `exists_by_job_function` becomes a containment scan;
  the fake and the adapter would have different failure modes for the same law.
- **Why rejected:** two of the twelve laws are defined by referential integrity.
  Removing the references removes the laws.

### Alternative D — Do nothing / one flat table with array columns
Not acceptable: `Employee` cannot be persisted at all without a decision here,
and the Stage's whole purpose is that the twelve laws hold against a real
database.

## Consequences

### Positive
- L-JF3 and L-E4 are enforced by PostgreSQL, not by application discipline.
- Cross-tenant assignment is unrepresentable, not merely rejected.
- Rehydration of `WorkloadProfile` cannot produce an impossible combination even
  from hand-written SQL.

### Negative
- Five tables instead of one: writing an `Employee` costs a parent statement plus
  up to three child statements, all inside one transaction.
- `update` of an employee must write the child rows **by difference** (delete only
  what was removed, insert only what was added). A wholesale rewrite is simpler to
  code and was measured to deadlock against a concurrent job-function deletion —
  see ADR 3.3.0006.
- Two anchor unique indexes (`uq_job_functions_id_tenant`,
  `uq_employees_id_tenant`) exist solely to satisfy the composite FKs and are
  otherwise unreachable — the same cost identity already pays.

### Neutral / trade-offs accepted
- Cross-BC referential integrity is deliberately *not* part of this schema — see
  ADR 3.3.0002.
- `employee_shift_preferences` encodes "no preference" as *no rows*. An
  explicitly declared empty set is indistinguishable from absence, which is
  harmless because `ShiftPreference` rejects the empty set at construction
  (ADR 3.1.0004).

## Implementation notes

- Every constraint is named explicitly: the error translator reads
  `diag.constraint_name`, and an autogenerated name would differ between
  environments (ADR 2.3.0002; see also ADR 3.3.0004).
- **Column types are part of this decision, not an afterthought.**
  `weekly_hours` is `NUMERIC` with **no declared precision**: `FixedSchedule`
  accepts any finite positive `Decimal`, and a `NUMERIC(5,2)` — the natural-looking
  choice for "weekly hours" — silently rounds (`22.555 → 22.56`, `0.001 → 0.00`,
  measured), which is data corruption under the project's verbatim discipline.
  `start_at`/`end_at` are `TIMESTAMP WITHOUT TIME ZONE`; identifiers and names are
  `TEXT`; `active` is `BOOLEAN NOT NULL`. The integration suite asserts the types,
  not only the constraint names.
- Three entity invariants are **not** representable here without triggers or an
  `EXCLUDE` extension — non-empty function set, non-overlapping periods, non-blank
  name. They stay enforced by `__post_init__`, which means a row written by hand
  that violates them raises **when read**. That is the declared limit, and it is
  what the rehydration-through-the-constructor rule buys.
- `tables.py` is the single source of the schema; `migrations/versions/0003_staff.py`
  is hand-written and frozen, as `0001` and `0002` are.
- Schema probed against the compose PostgreSQL on 2026-08-10; results are in
  `docs/stages/3.3-staff-persistence/concept.md` §9.

## References

- Related ADRs: [2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md),
  [3.2.0002](./3_2_0002-tenant-scoped-repository-signatures.md),
  [3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md),
  [3.1.0004](./3_1_0004-shift-preference-scope-and-cardinality.md),
  [3.3.0002](./3_3_0002-no-cross-bounded-context-foreign-keys.md)
- Port laws: `src/restaurant_hub/features/staff/application/ports/out/`
- Issue: https://github.com/MarceloSanC/restaurant-hub/issues/38

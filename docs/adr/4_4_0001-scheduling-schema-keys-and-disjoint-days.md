---
title: ADR 4.4.0001 — The scheduling schema keeps the aggregate in relational child tables keyed per unit, enforces disjoint days with an exclusion constraint, stores bands as naive timestamps and the tenant configuration as one fully typed row
description: Architecture Decision Record
when-use: Reference before changing a table, key, constraint or column type of the scheduling schema, before replacing the exclusion constraint, before adding an index, or when Stage 4.8 writes the tenant configuration
keywords: [adr, scheduling, schema, postgres, exclusion-constraint, btree-gist, composite-key, tenant, unit, timestamp, settings, constraint]
status: accepted
created_at: 2026-11-16
updated_at: 2026-11-16
adr_id: 4.4.0001
decision: 'The schedule aggregate is stored in four relational tables (schedules, schedule_bands, schedule_demands, schedule_assignments); child rows carry tenant_id, unit_id and schedule_id, their primary key is (tenant_id, unit_id, id) and they reference the parent through a composite foreign key with ON DELETE CASCADE; schedules.id is a global primary key; disjoint days per unit are enforced by an exclusion constraint over daterange(first_day, first_day + days) with the btree_gist extension; bands are TIMESTAMP WITHOUT TIME ZONE, the trail instant is TIMESTAMP WITH TIME ZONE; scheduling_settings is one row per tenant with every field a NOT NULL typed column; no foreign key leaves the scheduling metadata and only one non-key index exists.'
context_stage: 4.4-scheduling-persistence
bounded_context: scheduling
---

# ADR 4.4.0001 — Scheduling schema: per-unit keys, disjoint days, time regimes, typed settings

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-16.

## Context

Stage 4.3 published `ScheduleRepository` and `ScheduleConfigRepository` with their laws (L-SC1 to
L-SC8, L-CF1). Stage 4.4 gives them a PostgreSQL 16 schema. Four forces shape it:

- ids of bands, demands and assignments come from the client and are unique per (tenant, unit)
  (ADR 4.3.0004 §1); the schedule id is unique globally (law L-SC1);
- two schedules of the same unit never share a day (law L-SC2), and periods are not always equal:
  the week start is configuration, so periods may be offset;
- bands are wall-clock values of the unit, the audit instant is absolute
  (ADR 4.1.0007, ADR 3.1.0005);
- the tenant configuration is only read today, and Stage 4.8 will write it.

Bounded contexts share no foreign key (ADR 3.3.0002).

## Decision

1. **Relational aggregate.** `schedules` → `schedule_bands` → `schedule_demands` →
   `schedule_assignments`. Every child row carries `tenant_id`, `unit_id`, `schedule_id` and a
   `position` (the order of the tuple it came from). The primary key of each child table is
   `(tenant_id, unit_id, id)`, which is the per-unit uniqueness of ADR 4.3.0004. Each child
   references its parent by a composite foreign key that includes `schedule_id`, with
   `ON DELETE CASCADE`; a demand of one schedule attached to a band of another is not
   representable.
2. **Global schedule id.** `schedules` has primary key `(id)` and a unique
   `(tenant_id, unit_id, id)` that anchors the child foreign keys.
3. **Disjoint days.** `EXCLUDE USING gist (tenant_id WITH =, unit_id WITH =,
   daterange(first_day, first_day + days) WITH &&)`, named `ex_schedules_unit_days_disjoint`. The
   migration creates the `btree_gist` extension it needs.
4. **Time.** `start_at`/`end_at` are `TIMESTAMP WITHOUT TIME ZONE`; `first_day` is `DATE`;
   `day_cutoff` is `TIME WITHOUT TIME ZONE`; `schedule_changes.occurred_at` is
   `TIMESTAMP WITH TIME ZONE`.
5. **Settings.** `scheduling_settings` has primary key `(tenant_id)` and one typed `NOT NULL`
   column per field of `OperationalCalendar` and `ValidationConfig` (an `_enabled`/`_mode` pair
   per configurable policy), with `CHECK` constraints mirroring what the value objects refuse and
   no server default. A row is always a complete configuration.
6. **Opaque references, one index.** `tenant_id`, `unit_id`, `employee_id`, `job_function_id` and
   `author_user_id` are `TEXT` with no foreign key. Beyond the keys, the only index is
   `(tenant_id, unit_id, first_day)` on `schedules`, the access path of the three reads.
7. **Aggregate-internal uniqueness stays in the domain.** Distinct `(start, end)` among bands,
   one demand per function in a band and one record per band are enforced by `Schedule` on write
   and again on rehydration (the mappers build through the constructors); they get no constraint.

## Alternatives considered

### Alternative A — The aggregate as one JSONB document per schedule
Rejected: per-unit uniqueness of internal ids (law L-SC4) and the reverse query of the delete
guard (ADR 4.1.0006 §3) need rows. Same reasoning as ADR 3.3.0001.

### Alternative B — A day ledger: one row per (tenant, unit, day) with a primary key
Portable and extension-free, and it enforces the same rule. Rejected as the default because the
PostgreSQL documentation presents the exclusion constraint as the mechanism for non-overlapping
ranges per key, and the ledger adds a table and seven rows per schedule. **It is the recorded
fallback** if a future host does not allow `btree_gist`.

### Alternative C — Only an application lock with check-then-insert
Rejected as the guarantee: an advisory lock is an application convention the database does not
enforce. The lock exists (ADR 4.4.0003), but for ordering errors, not for integrity.

### Alternative D — Settings as a JSONB document, or one row per policy
Rejected: `ValidationConfig` requires all its fields, the port does not invent defaults, and a
child row per policy makes a configuration with a missing policy representable.

### Alternative E — Unique constraints for the aggregate-internal rules
Rejected: each one is an index with no measured access, guarding a rule the domain already
enforces on both directions.

## Consequences

### Positive
- The laws that span schedules (L-SC1, L-SC2, L-SC4) rest on database constraints.
- Stage 4.8 can write today's fields with one upsert and no migration. Authorship, an instant or
  a version on the configuration are open questions of that Stage; if it wants them, it adds the
  columns.
- The reverse guard query is answerable from `schedule_assignments.employee_id` and
  `schedule_demands.job_function_id` with tenant and unit on the row.

### Negative
- The schema depends on the `btree_gist` extension (trusted in PostgreSQL 16; Stage 6.1 confirms
  it on the chosen host).
- A new configurable policy needs a migration with an explicit default.

### Neutral / trade-offs accepted
- Child rows repeat `tenant_id`, `unit_id` and `schedule_id`; that repetition is what anchors the
  keys.

## Implementation notes

`features/scheduling/adapters/out/postgres/tables.py` is the single source of the schema;
`migrations/versions/0006_scheduling.py` is its frozen record. The exclusion element is declared
with `func.daterange(...)`: SQLAlchemy 2.0.51 treats a plain string element as a column name.

## References

- ADR 3.1.0005, ADR 3.3.0001, ADR 3.3.0002, ADR 3.3.0005, ADR 4.1.0006, ADR 4.1.0007, ADR 4.3.0004
- PostgreSQL 16 documentation: "Range Types" (Constraints on Ranges), "btree_gist",
  "CREATE TABLE" (EXCLUDE), "PostgreSQL Error Codes"
- `docs/stages/4.4-scheduling-persistence/concept.md` §7 D-DISJOINT, D-IDS, D-TIME, D-CONFIG; §9

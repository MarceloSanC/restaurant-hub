---
title: ADR 3.3.0005 — Staff indexes follow the measured access pattern, and native row-level security is rejected
description: Architecture Decision Record
when-use: Reference before adding or removing an index on a staff table, before considering CREATE POLICY / row-level security for tenant isolation, or when a staff listing becomes slow enough to justify a covering index
keywords: [adr, index, composite-index, tenant, postgres, rls, row-level-security, write-amplification, covering-index, restrict, foreign-key-index, staff]
status: accepted
created_at: 2026-08-10
updated_at: 2026-08-10
adr_id: 3.3.0005
decision: staff gets exactly three purposeful indexes beyond the primary keys — the unique (tenant_id, name), a (tenant_id, unit_id) index on employees and a (job_function_id, tenant_id) index on the link table — while redundant (tenant_id, id) indexes, ordered covering indexes and row-level security are all rejected with stated triggers for revisiting
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0005 — Tenant-scoped indexing, without row-level security

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ADR 3.2.0002 put `tenant_id` in every out-port signature of staff, and recorded
the consequence as a `[finding]` for this Stage: the access pattern of *every*
staff query became `(tenant_id, key)` and never the key alone. The finding named
three candidate strategies — a composite index `(tenant_id, id)`, the plain
primary key plus a filter, or row-level security — and deliberately did not
choose, saying the trade-offs (write amplification, index size, plan stability)
belong to the Stage that can measure them.

The actual access pattern, read off the two port interfaces:

| Query | Predicate | Selectivity |
|---|---|---|
| `find_by_id(tenant, id)` (both ports) | `id = ?` then `tenant_id = ?` | ≤ 1 row before the tenant filter |
| `find_by_name(tenant, name)` | `tenant_id = ? AND name = ?` | ≤ 1 row |
| `list_by_tenant(tenant)` | `tenant_id = ?` | tens of rows in v1 |
| `find_all_by_ids(tenant, ids)` | `id = ANY(?) AND tenant_id = ?` | ≤ len(ids) |
| `list_by_unit(tenant, unit, include_inactive)` | `tenant_id = ? AND unit_id = ?` (+ `active`) | tens to hundreds in v1 |
| `exists_by_job_function(tenant, fn)` | `tenant_id = ? AND job_function_id = ?` on the link table | existence only |
| `delete` of a job function | PostgreSQL's own `RESTRICT` check scans the *referencing* table by `(job_function_id, tenant_id)` | full scan without an index |

Identity already evaluated and rejected native row-level security for the same
multi-tenancy model (ADR 2.3.0002), in a codebase with the same connection
strategy: one pooled `Engine` built in the composition root, no per-tenant
database role, no session GUC.

## Decision

Beyond the primary keys and the two composite-FK anchor uniques, staff gets
**three** indexes, each justified by a query above:

1. `uq_job_functions_tenant_name (tenant_id, name)` — already required for the
   uniqueness law; because `tenant_id` leads, it also serves `find_by_name` and
   `list_by_tenant` with no extra object.
2. `ix_employees_tenant_unit (tenant_id, unit_id)` — serves `list_by_unit`, the
   only staff query whose result grows with the size of a unit.
3. `ix_employee_job_functions_function (job_function_id, tenant_id)` — serves
   `exists_by_job_function` **and**, more importantly, the `RESTRICT` check
   PostgreSQL performs on every job-function deletion. This one is not an
   optimisation: without it, every deletion scans the whole link table.

Three things are explicitly **not** created:

- **A composite `(tenant_id, id)` index.** `find_by_id` and `find_all_by_ids`
  resolve through the primary key and return at most one row per id; the tenant
  predicate then filters that row. A composite index would pay write
  amplification and storage on every insert to avoid filtering zero additional
  rows.
- **An ordered covering index** such as `(tenant_id, unit_id, name COLLATE "C", id COLLATE "C")`.
  It would freeze the collation choice into the schema, turning a future change of
  ordering (ADR 3.3.0003 declares linguistic display order an open presentation
  question) from one line of SQL into a migration — expensive exactly where the
  decision is most likely to move.
- **Row-level security.**

**Triggers for revisiting**, declared so the deferral is auditable rather than
permanent: a unit listing exceeding roughly 10⁴ rows, or Stage 3.4's pagination
showing a costly `Sort` node in `EXPLAIN`. Either one justifies the covering
index; adding an index is an online, reversible migration.

## Alternatives considered

### Alternative A — Row-level security (`CREATE POLICY` per tenant)
- **Description:** enable RLS on the staff tables and set the tenant in a session
  GUC or a per-tenant role, so the database filters even when a query forgets to.
- **Pros:** defence in depth; a forgotten `WHERE tenant_id = ?` stops leaking.
- **Cons:** there is no per-tenant database role and no session GUC in this
  project, and the `Engine` is a shared pool — introducing RLS means every
  checkout must `SET LOCAL`, and a missed one either fails closed (outage) or,
  worse, leaves the previous tenant's setting on a recycled connection. It also
  makes a *missing* tenant predicate invisible: the query returns correct results
  under RLS and would leak the moment RLS is off (a restore, a superuser
  connection, `BYPASSRLS`) — so the tests stop being able to catch the bug they
  exist to catch.
- **Why rejected:** the same reasoning identity already accepted (ADR 2.3.0002),
  plus the concrete pooling problem. Isolation stays where a test can see it: in
  the port signature (ADR 3.2.0002) and in the SQL.

### Alternative B — Composite `(tenant_id, id)` index on both aggregates
- **Description:** index the exact predicate shape of `find_by_id`.
- **Pros:** the predicate is served by a single index; plans are uniform.
- **Cons:** a primary-key lookup already returns one row; the composite index
  duplicates the PK's payload, doubles the write cost of every insert, and
  displaces buffer cache — for a filter over one row.
- **Why rejected:** cost with no measurable benefit at any plausible volume.

### Alternative C — Ordered covering index for the listing
- **Description:** `(tenant_id, unit_id, name COLLATE "C", id COLLATE "C")` so `list_by_unit`
  is an index-only scan with no sort.
- **Pros:** removes the sort; the natural end state if the listing grows.
- **Cons:** at v1 volumes the sort is on tens of rows; and it welds the collation
  decision into the schema.
- **Why rejected now, with a trigger:** deferred, not dismissed — see the two
  triggers above.

### Alternative D — Do nothing / no indexes beyond the primary keys
- **Description:** rely on sequential scans at v1 volumes.
- **Pros:** minimum write cost.
- **Cons:** the `RESTRICT` check on job-function deletion would scan the link
  table every time, and that is a correctness-critical path invoked by a normal
  user action.
- **Why rejected:** one of the three indexes is not optional.

## Consequences

### Positive
- The finding from ADR 3.2.0002 is closed with a written rationale per index
  rather than by habit.
- Write amplification stays minimal: the aggregate write path touches four tables
  already.
- Tenant isolation remains verifiable by tests, because it lives in the SQL.

### Negative
- `list_by_unit` performs an in-memory sort in PostgreSQL. Harmless at v1
  volumes, and the trigger for changing it is written down.
- Nothing in the database prevents a future query from forgetting the tenant
  predicate. The port signature makes it hard, but not impossible.

### Neutral / trade-offs accepted
- Index choices are cheap to reverse (an index is added or dropped online), which
  is why this ADR prefers deferral with a trigger over speculative optimisation.

## Implementation notes

- Indexes are declared in `tables.py` and reproduced verbatim in
  `migrations/versions/0003_staff.py`; the migration is frozen and hand-written.
- The integration suite asserts constraint and index **names** against
  `pg_constraint`/`pg_indexes`, because the error translator depends on the names
  (ADR 3.3.0004).

## References

- Related ADRs: [3.2.0002](./3_2_0002-tenant-scoped-repository-signatures.md),
  [2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md),
  [3.3.0001](./3_3_0001-staff-schema-tenant-scoping-and-composite-fk-cerco.md),
  [3.3.0003](./3_3_0003-total-ordering-with-c-collation-as-port-law.md)
- Finding: `docs/stages/3.2-staff-application/concept.md` §10

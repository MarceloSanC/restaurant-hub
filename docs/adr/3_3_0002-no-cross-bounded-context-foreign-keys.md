---
title: ADR 3.3.0002 — Staff tables do not carry foreign keys into the identity schema
description: Architecture Decision Record
when-use: Reference before adding a foreign key between tables of different bounded contexts, before deciding how a bounded context validates an identifier owned by another, or when a contract test needs to seed data from a foreign bounded context
keywords: [adr, bounded-context, foreign-key, referential-integrity, staff, identity, metadata, alembic, contract-test, coupling]
status: accepted
created_at: 2026-08-10
updated_at: 2026-08-10
adr_id: 3.3.0002
decision: employees.tenant_id and employees.unit_id stay opaque Text columns with no foreign key into identity's restaurants and units tables; referential validity across bounded contexts is enforced at the boundary that knows both, not by the database
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0002 — No foreign keys across bounded contexts

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

`employees` carries a `tenant_id` (the restaurant) and a `unit_id` (the unit).
Both are rows that exist in identity's `restaurants` and `units` tables, in the
**same PostgreSQL database**. Nothing physical prevents a foreign key.

Three project facts pull the other way:

1. `.importlinter` has a `bc-independence` contract, active since Stage 3.1, that
   forbids staff from importing identity at all.
2. `features/staff/domain/value_objects/identifiers.py` states the rule in prose:
   staff defines its own `TenantId`/`UnitId` because "identificadores atravessam
   a fronteira entre BCs como strings opacas, e cada BC tipa os seus".
3. `migrations/env.py` says each bounded context describes its schema in its own
   `MetaData`, and instructs the next BC to **combine** the metadatas
   (`target_metadata` accepts a list) rather than share one — because a shared
   `MetaData` would let one BC's Alembic run see another's tables and propose
   spurious drops.

Concept 3.2 §3 already declared the consistency `unit_id ↔ tenant_id` (the unit
belongs to the tenant) as a **premise of the boundary**, not an invariant of this
layer, and escalated a `[finding]` to Stage 3.4 requiring it to validate
`target_unit_id` against the actor's memberships.

There is also a concrete cost on the test side. Identity's contract suite has to
seed restaurants and units through the ports because its FKs demand them; the
docstring of `tests/contract/features/identity/conftest.py` explains that this is
why the four repositories are parametrised as one package. If staff had FKs into
identity, the staff contract suite would have to seed *identity* data to test
*staff* — through identity's ports, in a suite that is supposed to prove staff's
own contract.

## Decision

`employees.tenant_id`, `employees.unit_id` and `job_functions.tenant_id` remain
`Text NOT NULL` with **no foreign key** into identity. `staff_metadata` is a
separate `MetaData`, and `migrations/env.py` combines the two into a list.

Referential validity across the boundary is enforced where both sides are known —
the HTTP boundary of Stage 3.4, via authorisation and unit membership — and is
documented here as an honest limit of the schema, not as an omission.

Inside staff, referential integrity is enforced normally and structurally: see
ADR 3.3.0001.

## Alternatives considered

### Alternative A — Composite FK from `employees` into `units`
- **Description:** `(unit_id, tenant_id) → units(id, restaurant_id)`, reusing the
  `uq_units_id_restaurant` anchor identity already has.
- **Pros:** an employee could never point at a nonexistent unit, or at a unit of
  another restaurant; the fence identity built would extend to staff for free.
- **Cons:** staff's schema stops being deployable without identity's; the two
  contexts are welded to one database forever; the staff contract suite must seed
  identity through identity's ports, making staff's proof depend on another BC's
  adapter; and the `bc-independence` contract becomes true in Python and false in
  SQL, which is worse than either extreme because the gate reports green.
- **Why rejected:** it buys a guarantee this Stage does not owe (concept 3.2 §3
  assigned it to the boundary) at the price of the independence three separate
  project artefacts declare.

### Alternative B — FK plus a documented exception in `.importlinter`
- **Description:** keep the FK and widen the contract's comment to say the
  coupling is intentional at the data layer only.
- **Pros:** keeps the guarantee and is honest about the coupling.
- **Cons:** `.importlinter` cannot express or check a database-level dependency,
  so the "exception" would be prose that no gate enforces — the exact class of
  aspirational claim this project has been bitten by.
- **Why rejected:** an exception that no tool can verify is not an exception, it
  is a hope.

### Alternative C — Do nothing / leave it undecided until Step 4
- **Description:** ship without FKs and without recording why.
- **Pros:** zero words.
- **Cons:** Step 4 will add a schedule that references both employees and units,
  and will face the same fork with no precedent; and a future reader would read
  the missing FK as an oversight and "fix" it.
- **Why rejected:** the decision is being made either way; only the record is
  optional, and the record is the cheap part.

## Consequences

### Positive
- Staff's schema can be created, migrated and tested without identity present.
- The staff contract suite seeds nothing but staff, so its body is identical for
  the fake and for PostgreSQL with no cross-BC scaffolding.
- The door stays open for the per-restaurant instance split the roadmap keeps in
  view for Step 6.

### Negative
- The database will accept an employee whose `unit_id` does not exist, or belongs
  to another restaurant. Only the boundary prevents it.
- Deleting a restaurant or a unit in identity leaves staff rows orphaned, with no
  cascade and no error.

### Neutral / trade-offs accepted
- Detecting orphans becomes an operational concern (a reconciliation query), not
  a constraint. It is not in scope for v1; it is escalated as a `[finding]` with
  candidate Stage `6.3-ops-baseline`, and the line is registered in §10 of this
  Stage's concept — a finding that lives only inside an ADR body is not swept by
  the pipeline (rule inherited from concept 3.2 §10).

## Implementation notes

- `migrations/env.py`: `target_metadata = [identity_metadata, staff_metadata]`.
- `tests/conftest.py`: the staff tables join the single
  `TABELAS_EM_ORDEM_DE_LIMPEZA` tuple (children before parents), keeping one
  source of truth shared by the integration and contract suites.
- Stage 3.4 must honour the `[finding]` from concept 3.2 §10 about
  `target_unit_id`; this ADR is the reason it cannot be delegated downward to the
  database.

## References

- Related ADRs: [3.3.0001](./3_3_0001-staff-schema-tenant-scoping-and-composite-fk-cerco.md),
  [3.2.0002](./3_2_0002-tenant-scoped-repository-signatures.md),
  [2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md)
- `.importlinter` — contract `bc-independence`
- `src/restaurant_hub/features/staff/domain/value_objects/identifiers.py`
- `migrations/env.py` — comment on `target_metadata`

---
title: ADR 3.1.0003 — Job function lifecycle as soft active/inactive state, hard removal only when unreferenced
description: Architecture Decision Record
when-use: Reference when implementing job-function deactivation or removal (Stages 3.1–3.3), when a use case must decide what an inactive function allows, or before changing the removal semantics
keywords: [adr, staff, workforce, job-function, lifecycle, active, inactive, soft-delete, hard-delete, references]
status: accepted
created_at: 2026-07-27
updated_at: 2026-07-27
adr_id: 3.1.0003
decision: JobFunction carries an active/inactive soft state — deactivation blocks NEW assignments but keeps existing references valid; definitive (hard) removal is allowed only when no employee references the function; both cross-aggregate checks are enforced in the application layer (Stage 3.2), while Stage 3.1 models the state and its transitions.
context_stage: 3.1-staff-domain
bounded_context: staff
---

# ADR 3.1.0003 — Job function lifecycle: soft active/inactive state, hard removal only when unreferenced

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.2 marks the
**job-function lifecycle** as a lacuna for the Stage 3.1/3.2 concept, explicitly requiring an ADR
("há alternativa real: soft-state × hard-delete"). Ratified sources only say "CRUD de função"
(roadmap 3.2). Forces:

- Employees reference their function; the scheduling demand (Step 4) is defined **per function**
  ("Demanda por função×faixa", roadmap 4.1) and the hub reads history per function
  ("previsto × realizado", overview §3). A vanished function breaks both.
- Restaurants evolve their operation: a function stops being used (no more "sushiman") but its
  history and current holders must not be corrupted.
- A function created by mistake (typo, duplicate intent) should be fully removable — keeping
  garbage forever pollutes the controlled vocabulary that function names are (unique per tenant,
  workforce §3.2).
- Progressive-scalability criterion (ratified): minimal implementation on a shape that Step 4
  consumes without remodeling.

## Decision

`JobFunction` carries a **soft lifecycle state**: `active` (default) / `inactive`, with domain
operations `deactivate()` and `reactivate()` (Stage 3.1).

**Semantics with referencing employees:**

1. **Deactivation** blocks the function from being assigned to **new** employees/records;
   employees already referencing it keep the reference — their cadastre, the schedule history and
   the hub metrics stay intact. Reactivation restores assignability. The "cannot assign inactive"
   rule crosses aggregates (needs the function's state while editing an employee), so it is
   enforced in the **application layer use cases (Stage 3.2)** — the domain in 3.1 models the
   state and transitions.
2. **Definitive (hard) removal** is allowed **only when no employee references the function**
   (typo/mistake cleanup). With any referencing employee, removal is refused — the path is
   deactivation. The reference check requires the repository, so it too is enforced in the
   **application layer (Stage 3.2)**, backed by the persistence constraint (Stage 3.3).

## Alternatives considered

### Alternative A — Hard delete only (plain CRUD)
- **Description:** removal always allowed; references handled by cascade or nulling.
- **Pros:** simplest model; no state flag.
- **Cons:** cascade destroys employee cadastre or schedule history the hub and Step 4 read;
  nulling silently rewrites employee records the manager never touched (and whether a record
  may exist without a function at all is the pending F1 cardinality fork of the Stage 3.1
  concept — not a premise this ADR takes); "stop using a function" becomes impossible without
  destroying data.
- **Why rejected:** the product's own metrics (overview §3) require function history to survive
  operational churn.

### Alternative B — Soft state only, no hard removal ever
- **Description:** functions are never deleted, only deactivated.
- **Pros:** no reference check needed.
- **Cons:** typo functions pollute the tenant's vocabulary forever; the unique-name invariant
  (workforce §3.2) would trap the correct spelling behind a dead record ("Cozinheiro " with a
  trailing space blocks nothing, but a wrong duplicate concept lingers in every picker).
- **Why rejected:** removal of an **unreferenced** function is safe by construction and keeps the
  vocabulary clean; refusing it buys nothing.

### Alternative C — Removal with migration (reassign employees to a replacement function)
- **Description:** deleting a referenced function prompts a bulk reassignment to another one.
- **Pros:** powerful cleanup.
- **Cons:** v1 has no feature demanding bulk reassignment; complects removal with a batch
  operation; history rewrite (old allocations pointing at the replacement) falsifies hub metrics.
- **Why rejected:** overkill for v1 and partially wrong (history rewrite); can be added later as
  a separate explicit operation without changing this shape.

### Do nothing / status quo
Not viable: the domain doc requires the lifecycle fixed by ADR before the 3.2 use cases exist —
leaving it open would push the fork into the CRUD implementation, exactly what the gate prevents.

## Consequences

### Positive
- Function history survives operational churn; Step 4 and the hub read stable references.
- Mistake cleanup stays possible and safe (only when unreferenced).
- The pattern (soft state + guarded hard removal) extends naturally to other staff vocabularies
  if needed.

### Negative
- Pickers and use cases must filter `active` — one more condition in 3.2/3.4.
- "Cannot remove: function in use" is a new application error path the UI must present.

### Neutral / trade-offs accepted
- The domain entity cannot itself enforce the two cross-aggregate rules; they live in use cases
  (3.2) and persistence constraints (3.3). The concept records this split explicitly.
- Whether an **inactive** function's name still blocks the creation of a new function with the
  same name: **yes** — uniqueness is over the tenant's function set regardless of state
  (reactivation must not create a collision).

## Implementation notes

- Stage 3.1: `features/staff/domain/entities/job_function.py` — `active: bool`, `deactivate()`,
  `reactivate()` (idempotency or error on repeated transition is a technical.md detail).
- Stage 3.2: `create/assign` use cases refuse inactive functions; `delete_job_function` refuses
  when referenced.
- Stage 3.3: FK from employee to function with `RESTRICT` (no cascade), unique name per tenant.

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (tenant-scoped
  functions); [ADR 2.3.0005](./2_3_0005-names-persisted-verbatim.md) (verbatim unique names).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.2 (lacuna + ADR demand).
- [`roadmap.md`](../roadmap.md) — Stage 3.2 (CRUD de função), Stage 4.1 (demanda por função),
  Step 5 (auto-fill per function); [`overview.md`](../overview.md) §3 (hub previsto × realizado).
- Process: [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §2 (fork anchored
  in docs → decided by the concept author subagent, 2026-07-27).

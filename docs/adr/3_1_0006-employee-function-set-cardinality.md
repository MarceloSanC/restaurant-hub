---
title: ADR 3.1.0006 — Employee references a non-empty SET of job functions
description: Architecture Decision Record
when-use: Reference when modeling or consuming the employee→function reference (Stages 3.1–3.4), when the Step 4/5 matcher crosses employees with function demand, or before changing the reference's cardinality
keywords: [adr, staff, workforce, employee, job-function, cardinality, set, matching, fork-f1]
status: accepted
created_at: 2026-07-28
updated_at: 2026-07-28
adr_id: 3.1.0006
decision: The employee record references its job functions as a NON-EMPTY SET of JobFunctionId (frozenset, at least one) — the general form the Step 4/5 matching consumes without conversion; exactly-one is the particular case, and a record without functions is invalid.
context_stage: 3.1-staff-domain
bounded_context: staff
---

# ADR 3.1.0006 — Employee references a non-empty set of job functions

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The workforce domain doc confirms the employee record **references** the job function (§3.7 —
"a função referenciada existe na unidade destino sem recriação" is what keeps copy-to-unit
coherent), but **no ratified source fixes how many** functions one record may hold. The Stage
3.1 concept author raised this as **fork F1** (not 100% answerable by docs) and returned it to
the master session; the **human sponsor decided on 2026-07-28** (via the master session).

Forces:

- Scheduling demand is "N people of a function per shift" (roadmap 4.1: "Demanda por
  função×faixa"); the auto-fill (Step 5) matches employees to function vacancies.
- Cross-function people are common in restaurant operations (the extra who both waits tables
  and helps in the kitchen).
- The ratified progressive-scalability criterion (the same that fixed datetime granularity in
  [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) decision i): minimal
  implementation on the general shape Step 4/5 consume without remodeling.
- Migrating a scalar column to a collection later (persistence, Stage 3.3) remakes the
  persisted shape — the expensive path.

## Decision

**The employee record references its job functions as a NON-EMPTY SET**:
`job_function_ids: frozenset[JobFunctionId]`, with **at least one** element — an empty set is
invalid (domain error at construction/transition). Exactly one function is the particular case
of the set; the UI may start with single-select. The record matches vacancies of **any** of its
functions (Step 4/5 semantics). Reference is by id only (separate aggregates); referential
validity and the inactive-function assignment block remain application/persistence concerns
([ADR 3.1.0003](./3_1_0003-job-function-lifecycle-soft-state.md)).

## Alternatives considered

### Alternative A — Exactly one function per record
- **Description:** a single mandatory `job_function_id` field.
- **Pros:** cheapest now; simplest form and persistence (one column).
- **Cons:** a cross-function person needs duplicate records in the same unit (the manager pays
  with double bookkeeping and split unavailability/preference data); moving to a set later is
  an expensive persisted-shape migration (column → join table); the matcher can never consider
  a person for a second function.
- **Why rejected (sponsor, 2026-07-28):** fails the progressive-scalability criterion — the
  shape would have to be remade for a common operational reality.

### Alternative B — Possibly-empty set
- **Description:** like the decision, but a record may hold zero functions (e.g. cadastre
  before any function exists).
- **Pros:** looser onboarding order (employees before functions).
- **Cons:** creates unschedulable records that Step 4 must special-case; "employee with no
  function" has no meaning in the demand model; the onboarding order (create functions first)
  is already the natural flow (roadmap 3.4 e2e: manager creates function, then employee).
- **Why rejected (sponsor, 2026-07-28):** Step 4 would pay for a state the product does not
  need.

### Do nothing / status quo
Not viable: the reference exists (workforce §3.7) and the 3.2 `create_employee` use case and
the 3.3 schema need its cardinality fixed; leaving it open would push the fork downstream —
exactly what the gate exists to prevent.

## Consequences

### Positive
- Step 4/5 match one shape, no conversion; a person covers vacancies of any of their functions.
- One record per person per unit — unavailability, preference and workload stay unsplit.
- Single-function restaurants lose nothing: the set with one element is the particular case.

### Negative
- Persistence (3.3) models a collection (join table or array) instead of one column.
- Use cases (3.2) validate every id of the set (existence, tenant, active state) instead of one.

### Neutral / trade-offs accepted
- No "primary function" notion in v1; if prioritization between an employee's functions is ever
  needed (Step 5 fairness), it is an additive attribute on the relation.
- Copy-to-unit (3.2) carries the set as-is — coherent because functions are tenant-scoped
  (workforce §3.2/§3.7).

## Implementation notes

- Stage 3.1: `features/staff/domain/entities/employee.py` —
  `job_function_ids: frozenset[JobFunctionId]`; empty → the dedicated staff domain error;
  transition method returns a new instance (frozen entity pattern).
- Stage 3.3: FK per element with `RESTRICT` (supports ADR 3.1.0003 removal guard).

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (general-form
  precedent, decision i); [ADR 3.1.0003](./3_1_0003-job-function-lifecycle-soft-state.md)
  (lifecycle guards this cardinality interacts with).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.2, §3.7.
- [`roadmap.md`](../roadmap.md) — Stage 4.1 (demand per function), Step 5 (auto-fill), Stage
  3.4 (e2e ordering).
- Process: fork F1 returned by the Stage 3.1 concept author
  ([`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §2); **decided by the
  human sponsor on 2026-07-28** via the master session (option b of the rich-format fork).

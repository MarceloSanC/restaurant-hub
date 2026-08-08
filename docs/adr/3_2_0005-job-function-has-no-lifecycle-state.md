---
title: ADR 3.2.0005 — A job function has no lifecycle state; removal stays guarded
description: Architecture Decision Record
when-use: Reference before adding any state, flag or lifecycle transition to JobFunction, before reintroducing an "inactive function" rule in staff use cases (3.2–3.4), or when reading ADR 3.1.0003, which this ADR supersedes
keywords: [adr, staff, job-function, lifecycle, soft-delete, hard-delete, active, inactive, supersedes, sponsor]
status: accepted
created_at: 2026-08-08
updated_at: 2026-08-08
adr_id: 3.2.0005
decision: JobFunction carries no active/inactive state and has no deactivate/reactivate transitions — an unused function is inert and simply sits there; the user who no longer wants it deletes it, and deletion stays guarded (refused while any employee references it). This supersedes ADR 3.1.0003.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0005 — Job function has no lifecycle state (supersedes ADR 3.1.0003)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

Supersedes [ADR 3.1.0003](./3_1_0003-job-function-lifecycle-soft-state.md), whose status
becomes `superseded` with `superseded_by: 3.2.0005`.

## Context

[ADR 3.1.0003](./3_1_0003-job-function-lifecycle-soft-state.md) (2026-07-27) gave `JobFunction`
a soft `active`/`inactive` state with `deactivate()`/`reactivate()`, plus a guarded hard removal.
It was decided by the **concept author subagent** of Stage 3.1, from the lacuna that
[`workforce.md`](../domain/staff/workforce.md) §3.2 had flagged ("há alternativa real: soft-state
× hard-delete"). The ratified sources say only "CRUD de função" (roadmap 3.2) — they do not
mandate a lifecycle.

Stage 3.2 is the Stage that would have to **pay** for that state, and the bill became visible
while writing its concept:

- two more use cases (`deactivate_job_function`, `reactivate_job_function`) and two commands;
- an `include_inactive` flag threaded through the listing port, the query DTO and the HTTP layer;
- a cross-aggregate rule — "an inactive function accepts no NEW assignment" — that is **pure
  check-then-act** with no port law able to express it, because the state it consults does not
  participate in the write. Of the four rules Stage 3.1 delegated, it was the only one that could
  not be closed under concurrency at any layer;
- an unresolved intersection with [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md)
  ("copy-to-unit carries the set as-is") that the Stage 3.2 concept had to return to the sponsor
  as an open fork (F2), because the two accepted ADRs pointed in opposite directions for the same
  case.

The **human sponsor decided on 2026-08-08** (via the master session), in these terms:

> "não tem que desativar função; se ela não estiver em uso ela só fica lá parada, sem ninguém
> ser atribuído a ela; se o usuário não quiser mais ela pode simplesmente deletar"

The observation that settles it: **an unused function is inert.** Nobody is assigned to it, so it
never appears in an operational flow, it is never scheduled, and it carries no history of its own
(history is carried by the allocations, which reference it and therefore keep it undeletable). A
state that distinguishes "used" from "unused" duplicates information the reference graph already
holds.

## Decision

**`JobFunction` has no lifecycle state.**

1. The entity has **no `active` field** and **no `deactivate()`/`reactivate()` transitions**.
   Stage 3.2 removes them from `features/staff/domain/entities/job_function.py` and drops the
   corresponding tests (declared expansion of the Stage's target layer).
2. There are **no** `deactivate_job_function` / `reactivate_job_function` use cases, no
   `include_inactive` parameter anywhere, and **no rule** about inactive functions and new
   assignments. The set of cross-aggregate rules Stage 3.1 delegated to 3.2 drops from four to
   three: (i) name unique within the tenant, (ii) removal only when unreferenced, (iii) referential
   validity of the employee's function set.
3. **Removal stays guarded.** Deleting a function referenced by any employee — active or
   deactivated — is refused with `JobFunctionInUseError`. This is not a leftover of the superseded
   ADR; it is a separate decision of the master session, on its own rationale: an employee record
   must reference at least one function (`job_function_ids ≥ 1`,
   [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md)), so deleting a referenced
   function would leave the cadastre pointing at something that does not exist — corrupting the
   data and breaking a Stage 3.1 invariant. The path for "stop using this function" is: reassign
   the employees, then delete.
4. **Consequence for [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md):** its
   consequence "use cases (3.2) validate every id of the set (existence, tenant, **active state**)"
   loses its third item. Existence and tenant remain; active state has nothing to validate. The
   ADR is not superseded — its decision (non-empty set) is untouched; only that clause is void, and
   the Stage 3.2 concept says so where it cites it (§5.8).

## Alternatives considered

### Alternative A — Keep the soft state (status quo of ADR 3.1.0003)
- **Description:** `active` flag, `deactivate()`/`reactivate()`, listing filter, and the "no new
  assignment to an inactive function" rule.
- **Pros:** the manager can hide a function from pickers without touching the employees who hold
  it; "stop using" is one click instead of a reassignment; the vocabulary keeps its history.
- **Cons:** the state has no consumer that the reference graph does not already serve — a function
  nobody is assigned to never surfaces anyway; it adds two operations, one field, one flag on
  three layers, and the only delegated rule with no possible port law (unclosable under
  concurrency); and it created a genuine contradiction with ADR 3.1.0006 for copy-to-unit that had
  to be escalated as a fork.
- **Why rejected (sponsor, 2026-08-08):** the cost is real and recurring, the benefit is
  hypothetical, and the state is not what Step 4 or the hub consume — they consume the reference.

### Alternative B — No state and no removal guard (plain CRUD, hard delete always)
- **Description:** drop the state *and* the guard; deleting a referenced function cascades or nulls
  the employee's reference.
- **Pros:** the simplest possible model; one operation less to explain.
- **Cons:** cascade destroys employee cadastre; nulling produces an employee with an **empty**
  function set, which the domain rejects (`EmptyJobFunctionsError`) — so the write would fail
  anyway, just later and as an integrity error instead of a business one. It also silently rewrites
  records the manager never touched.
- **Why rejected:** it does not simplify anything real; it converts a clear refusal into data
  corruption or a 500.

### Alternative C — No state, guard replaced by forced reassignment on delete
- **Description:** deleting a referenced function prompts a bulk reassignment to another function.
- **Pros:** the manager is never stuck.
- **Cons:** v1 has no feature demanding bulk reassignment; it complects removal with a batch
  operation; and rewriting past allocations to point at a replacement falsifies the hub's
  "previsto × realizado".
- **Why rejected:** overkill for v1 and partly wrong. It stays available as an additive, explicit
  operation later, without changing anything decided here.

### Do nothing / status quo
Not viable in the strict sense: "do nothing" here means Alternative A, which is exactly what the
sponsor decided against. Leaving the state in place would also leave fork F2 open, blocking Stage
3.2 from entering Fase 3B.

## Consequences

### Positive
- One field, two entity transitions, two use cases, two commands, one port parameter and one query
  parameter disappear from the Stage — and the corresponding HTTP surface never exists in 3.4.
- The only delegated rule that could not be closed under concurrency at any layer disappears with
  the state it consulted. All three remaining rules have a port law.
- Fork F2 of the Stage 3.2 concept is **dissolved** (it had no object left), and the contradiction
  between ADR 3.1.0003 and ADR 3.1.0006 for copy-to-unit stops existing.
- The Stage 3.3 schema is simpler: no `active` column, no partial index, no filter in the listing
  query.

### Negative
- **Already-merged Stage 3.1 code changes.** Removing `active`/`deactivate()`/`reactivate()` and
  their tests is a subtractive edit to a Stage that is `done` — declared as an expansion of Stage
  3.2's target layer, with a dated reconciliation note in `roadmap.md` at closing.
- A manager who wants to retire a function without touching cadastres has **no** intermediate move:
  either the function keeps existing (harmless, but visible in the picker) or the employees are
  reassigned first. This is the accepted cost.
- The Stage 3.1 `technical.md` §7 decision "lifecycle transitions are idempotent in value" becomes
  void along with the transitions.

### Neutral / trade-offs accepted
- If a real need for hiding functions ever appears (a tenant with dozens of retired functions
  polluting a picker), the additive move is **ordering/filtering in the UI** or a flag reintroduced
  then, with a consumer to justify it. Reintroducing it is a schema addition, not a reshape — the
  progressive-scalability criterion is respected in the cheap direction.
- Name uniqueness is unaffected: it was already "over the tenant's function set regardless of
  state", and now there is no state to qualify it. The verbatim comparison is anchored in
  [`workforce.md`](../domain/staff/workforce.md) §3.2.

## Implementation notes

- Stage 3.2, dedicated Task: remove `active`, `deactivate()`, `reactivate()` from
  `src/restaurant_hub/features/staff/domain/entities/job_function.py`, adjust its docstring, and
  drop `test_deactivate_devolve_nova_instancia_inativa`,
  `test_reactivate_devolve_nova_instancia_ativa` and
  `test_transicoes_repetidas_sao_idempotentes_no_valor` from
  `tests/unit/features/staff/domain/test_job_function.py` (plus the `active` argument of its
  `_funcao` helper and the assertions that read the field).
- No orphan exception to remove: `InactiveJobFunctionError` was **never implemented** — it existed
  only as a planned name in the Stage 3.2 concept draft (verified by grep over
  `features/staff/domain/exceptions/errors.py`, which declares `StaffError` + 8 subclasses, none of
  them about inactivity).
- Stage 3.3: no `active` column on the function table; the unique index `(tenant_id, name)` and the
  `RESTRICT` FK from employee to function remain (the FK is now the *only* lifecycle-related
  constraint).

## References

- **Supersedes:** [ADR 3.1.0003](./3_1_0003-job-function-lifecycle-soft-state.md).
- Related ADRs: [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md) (its "active state"
  consequence is void; its decision stands);
  [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) (the *opposite* decision for
  the employee record, and why the asymmetry is intentional);
  [ADR 3.2.0001](./3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md) (the delegated rules
  after this decision).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.2 (the lacuna this ADR closes
  differently from 3.1.0003).
- [`docs/stages/3.2-staff-application/concept.md`](../stages/3.2-staff-application/concept.md) §5.6,
  §7, §13 (fork F2 dissolved).
- Authorship: **human sponsor, 2026-08-08**, via the master session — a sponsor-level decision,
  which by the project's hierarchy prevails over a prior ADR taken by a concept-author subagent.

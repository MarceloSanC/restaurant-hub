---
title: ADR 3.2.0004 — One use case per aggregate transition instead of a partial-update use case
description: Architecture Decision Record
when-use: Reference when adding an employee-editing use case (Stages 3.2, 3.5), or when designing the HTTP surface of Stage 3.4 for employee edits
keywords: [adr, staff, application, use-case, granularity, partial-update, optional-fields, unset-sentinel, dto]
status: accepted
created_at: 2026-08-08
updated_at: 2026-08-08
adr_id: 3.2.0004
decision: Employee editing is exposed as one use case per business transition (rename, assign functions, change workload profile, declare shift preference, register/remove unavailability) rather than a single update_employee taking optional fields, because None already carries domain meaning for shift_preference and a partial-update DTO would have to overload it.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0004 — Granular use cases instead of a partial update

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.2 must expose the editing operations of the employee record. The roadmap names some of them
individually ("definir jornada/preferência", "registrar indisponibilidade") and leaves the shape
open. Two shapes are viable and both are common in practice: a single `update_employee` taking
optional fields, or one use case per transition.

Two facts constrain the choice:

1. **`None` already means something in this domain.** `shift_preference=None` is the ratified
   encoding of "no preference declared" — an empty set is invalid and `None` is the way to say the
   employee has not declared one ([ADR 3.1.0004](./3_1_0004-shift-preference-scope-and-cardinality.md);
   concept 3.1 §5.7).
2. **The Stage 3.1 aggregate is already granular.** `Employee` exposes `rename`,
   `assign_job_functions`, `change_workload_profile`, `declare_shift_preference`,
   `add_unavailability` and `remove_unavailability` — each returning a revalidated new instance
   (frozen-entity pattern, concept 3.1 §4/§7).

LAYOUT §7 also states "um use case por arquivo" — which settles file layout but not how many
operations one use case may cover.

## Decision

Each business transition gets **its own use case**, mirroring the aggregate's own transitions:
`RenameEmployeeUseCase`, `AssignJobFunctionsUseCase`, `ChangeWorkloadProfileUseCase`,
`DeclareShiftPreferenceUseCase`, `RegisterUnavailabilityUseCase`, `RemoveUnavailabilityUseCase`.
Each takes a command with the tenant, the employee id and **exactly the data that transition
needs**; each returns the full `EmployeeResult` of the new state.

The same shape applies to the lifecycle transitions added by
[ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) —
`DeactivateEmployeeUseCase` (termination) and `ReactivateEmployeeUseCase` (rehire) are two use
cases, not one `set_employee_active(flag)`: the two operations have different business meanings,
different authorizations in Stage 3.4 and different audit weight, and a boolean parameter would
make the log line "someone set active=false" instead of "someone terminated this employee". And to
the job function, which after [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) has
exactly one editing transition: `RenameJobFunctionUseCase`.

## Alternatives considered

### Alternative A — Single `UpdateEmployeeUseCase` with optional fields
- **Description:** one command with `name: str | None`, `workload_profile: WorkloadProfile | None`,
  `shift_preference: ShiftPreference | None`, `job_function_ids: frozenset | None`; `None` means
  "leave untouched".
- **Pros:** one use case, one route in Stage 3.4, one round trip for a form that edits several
  fields at once.
- **Cons:** `None` would have to mean both "leave untouched" and "clear the preference", which are
  different operations; the usual escape (an `UNSET` sentinel) imports into the application layer an
  ambiguity the domain does not have, and every consumer — the Stage 3.4 schema, the fake, the test
  — must then reason about three states per field instead of two. The failure mode is silent: a
  caller that omits the preference intending "don't touch" and a caller that sends `None` intending
  "clear" produce the same wire payload.
- **Why rejected:** it re-creates at the boundary exactly the ambiguity that ADR 3.1.0004 removed
  from the domain.

### Alternative B — Single use case with an explicit sentinel (`UNSET`)
- **Description:** as A, but with a dedicated sentinel value distinguishing "untouched" from
  "cleared".
- **Pros:** unambiguous; still one route.
- **Cons:** the sentinel must be modelled, typed, serialized at the HTTP boundary in 3.4, and
  honoured by every implementation; mypy strict handling of a sentinel union is noisy; and the
  single use case accumulates the *union* of all the cross-aggregate checks (resolving and
  validating the whole function set against the tenant) even for a call that only renames.
- **Why rejected:** it buys one route at the cost of a concept (the sentinel) that leaks into three
  Stages and of a use case whose checks no longer match what it does.

### Alternative C — Full-replacement update (`PUT` semantics)
- **Description:** the command carries the complete desired state; missing fields are cleared.
- **Pros:** no partial-update ambiguity at all; idempotent.
- **Cons:** the client must send the entire record — including the unavailability collection — to
  change a name, which makes every edit a lost-update race over fields nobody meant to touch
  (concept §5.17 already flags that there is no concurrency control in this Stage); and it invites
  clients to reconstruct the aggregate, which is the repository's job.
- **Why rejected:** amplifies the concurrency risk the Stage explicitly did not solve.

### Do nothing / status quo
Not viable: the editing operations are in scope of this Stage; some shape must be chosen.

## Consequences

### Positive
- Each use case has exactly the dependencies and the checks its own operation needs — the rename
  never touches `JobFunctionRepository`.
- The command types are total: there is no field whose absence has to be interpreted.
- The acceptance criteria map one-to-one onto use cases, which keeps the traceability matrix of
  Stage 3.2 honest.

### Negative
- More files and more Tasks: this is one of the reasons the Stage sits **above** the healthy 3–12
  Task range, at 13 (concept §10/§12).
- Stage 3.4 exposes several narrow endpoints instead of one `PATCH`; a UI form editing three fields
  makes three calls.

### Neutral / trade-offs accepted
- If a future screen genuinely needs an atomic multi-field edit, it can be added as **one more**
  use case that composes the transitions inside a single aggregate write — additive, and it does not
  invalidate anything decided here.
- Every editing use case returns the whole `EmployeeResult`, so a client that made several calls can
  always resynchronize from the last response.

## References

- Related ADRs: [ADR 3.1.0004](./3_1_0004-shift-preference-scope-and-cardinality.md) (`None` means
  "no preference"); [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md) (the function
  set is replaced wholesale by `assign_job_functions`);
  [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) (the two lifecycle
  transitions this shape applies to);
  [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) (why the job function has only
  one editing transition).
- [`docs/stages/3.1-staff-domain/concept.md`](../stages/3.1-staff-domain/concept.md) §4 (the
  aggregate's transitions), §7 (frozen entities).
- [`docs/LAYOUT.md`](../LAYOUT.md) §7 ("um use case por arquivo").

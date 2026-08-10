---
title: ADR 3.2.0007 — A terminated employee record stays editable, and no edit reactivates it
description: Architecture Decision Record
when-use: Reference when implementing or changing any employee edit use case (Stages 3.2–3.4), when exposing those operations over HTTP, or before adding a state guard to an edit path
keywords: [adr, staff, employee, lifecycle, active, inactive, terminated, edit, reactivate, orthogonality, sponsor]
status: accepted
created_at: 2026-08-09
updated_at: 2026-08-09
adr_id: 3.2.0007
decision: A terminated (inactive) employee record remains editable by every edit use case, and none of those operations changes `active` — reactivation is an explicit act, available only through reactivate_employee.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0007 — The terminated employee stays editable, and editing never reactivates

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) gave the employee record a
termination state, and [ADR 3.2.0004](./3_2_0004-granular-use-cases-over-partial-update.md) split
editing into six granular use cases (`rename_employee`, `change_workload_profile`,
`declare_shift_preference`, `assign_job_functions`, `register_unavailability`,
`remove_unavailability`). Neither answered the question the combination raises:

**What happens when one of those six is called on a record that is already terminated?**

No ratified source answered it. The Stage 3.2 concept describes the six operations and the two
lifecycle transitions as independent features and never states how they interact; `workforce.md` is
silent; the roadmap is silent. The gap was found by the **independent test audit of Stage 3.2**
(2026-08-09), and it was found the hard way: a mutation battery showed that **nine** distinct
mutations of the production code survived a suite with 100% line and branch coverage. Among them:

- replacing the preserved `active=<value>` with a hard-coded `active=True` in any of the six use
  cases — no test failed;
- embedding `.reactivate()` inside `rename_employee` or `register_unavailability`, which
  **silently resurrects a terminated employee** — no test failed;
- the *opposite* reading — refusing the edit with a `raise` when the record is inactive — also
  passed green.

That last one is the diagnosis, not just a symptom: the suite did not discriminate between two
**contradictory** specifications, which means the behaviour was never specified at all. The fixtures
of every edit suite created records with `active=True`, so no test ever exercised an edit on a
terminated record.

This is exactly the trap recorded in the project memory as *"teste trava o caso, não a
propriedade"* — 100% coverage over a narrow representative.

The **human sponsor decided on 2026-08-09** (via the master session).

## Decision

**A terminated employee record remains editable by all six edit use cases, and none of them changes
`active`.**

1. **Editability is orthogonal to lifecycle state.** Every edit use case treats `active` as data it
   carries forward untouched. Fixing a typo in the name of someone who left does not require
   bringing them back onto the team.
2. **Reactivation is an explicit act.** `active` transitions to `True` only through
   `reactivate_employee`, and to `False` only through `deactivate_employee`. No other operation in
   the bounded context writes that field.
3. **This is a testable property, not a convention.** Stage 3.2 adds an acceptance criterion that
   exercises **each** of the six operations against an already-terminated record, asserting both
   that the edit took effect (re-read through the port) and that `active` is still `False`.

The orthogonality is what makes the rule cheap: there is no state guard to write, no new error, and
no branch in any use case. What the decision buys is that the property is now **pinned**, so the
next person cannot silently pick either of the two readings.

## Alternatives considered

### Alternative A — Fully editable, no operation touches `active` (**chosen**)
- **Description:** the six edit use cases work on terminated records exactly as on active ones;
  `active` is carried forward untouched.
- **Pros:** correcting an accent in a departed employee's name is one call, not two. No new error, no
  new branch, no state guard to keep in sync across six use cases. The history stays correctable —
  which matters precisely because the hub reads it. And it does not close any door: moving to (C)
  later is an **addition** of guards, not a rewrite.
- **Cons:** it allows edits that are meaningless for someone who left — declaring a shift preference
  for a terminated employee is legal and inert. The product tolerates a nonsensical-but-harmless
  operation rather than paying for a rule that prevents it.
- **Why chosen (sponsor, 2026-08-09):** correcting a record is not the same act as rehiring a person,
  and the system should not force one to get the other.

### Alternative B — Terminated records are read-only
- **Description:** the six edit use cases refuse an inactive record with a new error.
- **Pros:** protects the history from post-hoc alteration; makes "terminated" mean something strong
  and easy to explain; any edit becomes an auditable reactivate→edit→deactivate sequence.
- **Cons:** turns fixing a typo into two extra state transitions, each of which is a *lie* about what
  happened (the person was not rehired and re-terminated). Requires a new error, its HTTP mapping in
  3.4, and a guard replicated across six use cases — six places to forget.
- **Why rejected (sponsor, 2026-08-09):** the cost lands on the legitimate case (correcting data)
  to prevent a case that harms nothing.

### Alternative C — Granular: identification editable, scheduling data frozen
- **Description:** name and identification editable while terminated; workload profile, shift
  preference, job functions and unavailabilities blocked until reactivation.
- **Pros:** the most faithful to reality — the data that only matters for scheduling is frozen
  exactly while the person cannot be scheduled.
- **Cons:** every operation needs its own rule, its own test and its own error case, and the split
  between "identification" and "scheduling data" is a judgement call that will be re-litigated with
  each new field.
- **Why rejected (sponsor, 2026-08-09):** the fidelity is real but it is not free, and it is
  **not lost by choosing (A)**: migrating from (A) to (C) later adds guards to specific operations,
  which is an increment rather than rework. Deferring it costs nothing; adopting it now costs six
  rules and six tests for a distinction nobody has asked for yet.

### Do nothing / status quo
Not viable, and this ADR exists because "nothing" was the actual state: the code carried an
**accidental** behaviour (it happened to preserve `active`) that no test pinned, and the audit proved
both readings passed. An unspecified interaction between two shipped features is a defect waiting for
the first person who assumes the other reading.

## Consequences

### Positive
- The nine surviving mutations of the audit acquire a killer test; in particular the two that
  **resurrected a terminated employee in silence** — the worst of the batch, because the record would
  reappear in the unit listing and in the Step 4 scheduling picker with nobody having rehired anyone.
- No production code changes: the current implementation already matches the decision. The Stage pays
  only the tests that pin it.
- Stage 3.4 gets an unambiguous rule for the HTTP surface: no edit endpoint needs a state check, and
  none may flip `active` as a side effect.

### Negative
- Meaningless-but-legal operations exist (declaring a shift preference for someone who left). They
  are inert: a terminated record is hidden from the default listing and is not schedulable.
- The rule is enforced by tests, not by a type. A seventh edit use case could write `active` and only
  the mutation-minded reviewer would notice — mitigated by the acceptance criterion being written per
  operation, so adding a seventh without a test is visible in review.

### Neutral / trade-offs accepted
- The decision is **silent about authorization**: who may edit a terminated record is an RBAC
  question for Stage 3.4, not a domain rule (concept §5.13 — no use case receives an actor).
- `copy_employee_to_unit` is unaffected: it carries `active` as-is by
  [ADR 3.2.0003](./3_2_0003-copy-employee-full-duplication.md), which is the same principle seen from
  the copy's side — no operation other than the two transitions decides that field.

## Implementation notes

- No change to `src/`. The six use cases already build the result from the loaded aggregate, and the
  frozen-entity transitions of Stage 3.1 preserve every untouched field by construction.
- Stage 3.2 acceptance criterion (concept §11): each of the six operations exercised against a
  record created with `active=False`, asserting the edit's effect **re-read through the port** and
  `active is False` afterwards.
- Delivered as an extra test Task in Stage 3.2 (`[3.2/task-14-extra]`), not by reopening the Tasks
  that shipped the use cases.

## References

- Related ADRs: [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) (which created
  the state this ADR constrains); [ADR 3.2.0004](./3_2_0004-granular-use-cases-over-partial-update.md)
  (which created the six granular operations); [ADR 3.2.0003](./3_2_0003-copy-employee-full-duplication.md)
  (the copy carries `active` as-is, same principle).
- [`docs/stages/3.2-staff-application/concept.md`](../stages/3.2-staff-application/concept.md) §5, §11.
- Project memory: *"teste trava o caso, não a propriedade"* — 100% coverage over a narrow
  representative; this ADR is a direct instance.
- Authorship: **human sponsor, 2026-08-09**, via the master session, after the independent test audit
  of Stage 3.2 returned the gap as finding F-01.

---
title: ADR 4.2.0001 — The function-mismatch policy evaluates the record's current functions and never reads the stored function-exception flag
description: Architecture Decision Record
when-use: Reference before letting a policy read Assignment.function_exception, before freezing the exception mark at allocation time, before adding a mutation for the flag, or when 4.3/4.5/8.1 decide how the "exceção" label and the exception count are derived
keywords: [adr, scheduling, validation, function-mismatch, function-exception, reconciliation-on-read, staff, policy]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 4.2.0001
decision: The function-mismatch policy is evaluated against the employee record's functions at evaluation time; the stored function_exception flag is read by no policy and stays as the record of the acknowledgement made when allocating, so a record that gains the function stops violating and an ordinary allocation whose record loses the function starts violating.
context_stage: 4.2-validation-policies
bounded_context: scheduling
---

# ADR 4.2.0001 — Function mismatch follows the current staff record

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

[ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (f) made assigning a
record to a demand for a function it does not hold a `warn` policy: the acknowledgement saves the
allocation flagged `function_exception`, and the staff record is untouched. It left one gap to
this Stage: *"Whether the exception is re-evaluated when the record later gains or loses the
function is a Stage 4.2 concept gap."* Stage 4.1 deliberately gave the flag no mutation for the
same reason (4.1 concept §5.13).

The policy reads the record's functions through data supplied by 4.3 (`EmployeeFacts`), so the
question is which truth the policy uses after the fact: the functions **now**, or the decision
taken **when allocating**. It changes what the manager sees and is therefore a product decision
(skill `evidence-resolution`, class P).

Forces: the sponsor chose, for termination, that every read reflects the record's current state
"como um refresh F5" ([ADR 4.1.0006](./4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md));
a stored flag that is the only source of the label would go stale when staff changes.

## Decision

Sponsor, 2026-10-18, verbatim choice: *"Segue o cadastro atual (Recomendada)"*.

1. `function_mismatch` violates iff `job_function_id(demand) ∉ job_function_ids(record)` with the
   record's functions **at evaluation time**. Ana, allocated as cook by acknowledged exception,
   who later gains the cook function, **stops** violating. Bruno, allocated normally as cook, who
   later loses it, **starts** violating.
2. **No policy reads `Assignment.function_exception`.** The flag stays as the record of the
   acknowledgement given when the allocation was made. Where the "exceção" label (4.5) and the
   hub's exception count (8.1) come from is **not** decided here: with the policy disabled there
   is no live violation, so neither can depend on the violation alone without losing the signal
   ADR 4.1.0003 (f) requires ("visible on the schedule") — recorded finding for 4.5 and 8.1.
3. **No mutation for the flag is added in 4.2.** Nothing in this Stage needs to change it.

## Alternatives considered

### Alternative A — Freeze at allocation time
- **Description:** the mark is decided when allocating and never re-evaluated.
- **Cons:** Bruno keeps an allocation for a function he no longer holds with no warning; the
  schedule stops reflecting who is qualified for what; a stateless evaluator cannot express it
  without knowing which allocation is "new".
- **Why rejected:** the sponsor chose otherwise.

### Alternative B — Mixed
- **Description:** staff changes create new warnings (Bruno warns) but never clear an accepted
  mark (Ana stays "exceção").
- **Cons:** the label lies after the record gains the function; two sources of truth.
- **Why rejected:** the sponsor chose otherwise.

### Alternative C — Do nothing
- Not applicable: the policy cannot be written without choosing.

## Consequences

### Positive
- The schedule is always consistent with staff, same principle as ADR 4.1.0006.
- The evaluator stays stateless; no mutation and no extra field.

### Negative
- A violation can appear on the live schedule without any schedule mutation introducing it
  (Bruno). Under `block` this means the live schedule can hold a `block` violation that came from
  staff. How the 4.3 acceptance protocol treats staff-induced violations is a recorded finding.
- The stored flag can disagree with the live state (Ana); consumers must not show it alone as
  the label.
- The domain doc invariants of §3.5, §3.6.6 and §3.6.7 hold only for what a **schedule** mutation
  introduces; a staff-side guard versus show-and-fix is a product question for the 4.3 concept.

## Implementation notes

- Stage 4.2: `services/validation/function_mismatch_policy.py`; CA7 of the 4.2 concept fixes the
  two scenarios.

## References

- [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (f);
  [ADR 4.1.0006](./4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md).
- [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.6.7 (the gap).
- [`docs/stages/4.2-validation-policies/concept.md`](../stages/4.2-validation-policies/concept.md) §7.

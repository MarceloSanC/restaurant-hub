---
title: ADR 4.2.0002 — The evaluator takes the schedule, its neighbours and staff facts by data, skips inactive records, refuses incomplete input, evaluates unavailability with a fixed block mode, and returns violations whose identity excludes the measure
description: Architecture Decision Record
when-use: Reference before moving the unavailability check out of the evaluator, before changing what the evaluator receives, before changing which policies carry their allocations in a violation's identity or adding the measure to it, or when 4.3 designs the acceptance protocol on top of Violation.key
keywords: [adr, scheduling, validation, evaluator, violation, identity, acceptance, unavailability, neighbours, inactive, fail-closed]
status: accepted
created_at: 2026-10-18
updated_at: 2026-10-18
adr_id: 4.2.0002
decision: The scheduling evaluator is a pure domain function over an EvaluationContext (the schedule, the previous/next schedules of the same unit as counterparts only, and staff facts by data including the active flag); it skips inactive records, refuses incomplete or cross-unit input, runs unavailability as an always-enabled fixed-block policy, and returns violations whose key is (policy, subject, scope days, allocations only for per-allocation policies and over-coverage) with the measure carried beside the key.
context_stage: 4.2-validation-policies
bounded_context: scheduling
---

# ADR 4.2.0002 — Evaluator input and violation identity

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The domain doc (`shift-scheduling.md` §6) left to this Stage the shape of `Violation`, the
evaluation order and where unavailability is checked, and to 4.2/4.3 the identity of a violation
for acceptance. Stage 4.1 (concept §8) added: whether the evaluator receives the neighbouring
schedules, and the `N = 0` reading. The 4.3 acceptance protocol will compare the violations
before and after a mutation; it needs a stable identity to tell "introduced by this change" from
"already there".

## Decision

1. **Input.** `EvaluationContext(schedule, facts, previous=None, next=None)`. `previous`/`next`
   are the adjacent schedules of the same unit (ADR 4.1.0003 (a): *"Every policy receives the
   record's neighbouring allocations (previous/next schedule)"*); they are **counterparts only** —
   a violation is reported only if it involves the evaluated schedule, so a boundary violation
   shows, with the same key, in both schedules. All three periods must have 7 days (the
   accounting week is the period — ADR 4.1.0002 §1). Staff data arrives as `EmployeeFacts`
   (functions, contracted weekly hours as `Decimal`, unavailability windows, `active`), a type of
   this BC.
2. **Inactive records are skipped** by every policy, including the over-coverage count
   (ADR 4.1.0006: inactive records and their allocations are absent from every read; the slot
   reads as uncovered).
3. **Fail-closed input.** Missing facts for an allocated record, duplicated facts, a neighbour of
   another tenant or unit, with a repeated id, not adjacent to the evaluated period, an
   `AssignmentId` repeated across the three schedules, or a period other than 7 days are refused
   with `InvalidEvaluationInputError`. Skipping a record with missing facts would let a `block`
   violation pass silently; mixing tenants would be a leak; a wrong neighbour would hide the
   boundary overlap. Completeness of the roster **without** allocations (the `both` workload
   subjects) is not checkable here and is a 4.3 contract.
4. **Unavailability lives in the evaluator**, always enabled, mode fixed to `block`, with no
   configuration entry (ADR 4.1.0003 (a) "Configurable: nothing"). One evaluator serves the live
   warnings of the editor and the Step 5 proposal ("nasce sem violações block").
5. **Identity.** `Violation.key = (policy, employee_id, demand_id, operational_days,
   assignment_ids)`, with `assignment_ids` **empty** for aggregate scopes (rest, daily cap,
   weekly cap, workload) and present for overlap, unavailability, function mismatch, break
   divergence **and over-coverage** — the over-coverage acknowledgement is per surplus allocation
   (ADR 4.1.0003 (g); doc §3.6.8: no surplus allocation without an acknowledgement), so allocating
   or removing one changes the key, while lowering `N` over the same set does not (only the
   measure worsens). The measure (`observed`, `limit`) and the full allocation set are carried
   **beside** the key. Over-coverage is counted **per demand**, never aggregated across
   overlapping bands of the same function.
6. **No short-circuit, deterministic order:** all enabled policies run, in `PolicyKind` order,
   each sorted by scope.

## Alternatives considered

### Alternative A — Unavailability checked in the 4.3 use case
- **Cons:** two places for "is this allocation valid"; the Step 5 auto-fill would need the same
  check again; the editor's live list would miss the most important `block`.
- **Why rejected:** one evaluator for every consumer is what the roadmap describes.

### Alternative B — Identity includes the measure
- **Cons:** every change of a number is a new violation: accept 46h, reach 47h, asked again — and
  also asked again when the number improves.
- **Why rejected:** the measure is kept beside the key, so 4.3 can still re-ask on worsening
  without changing the shape (most reversible).

### Alternative C — Identity includes all involved allocations for every policy
- **Cons:** removing a shift that improves the day changes the set and reads as a new violation.
- **Why rejected:** same reason; the set is on the `Violation` anyway.

### Alternative D — Treat missing facts as inactive
- **Cons:** an orchestration bug becomes a silent pass of `block` rules.
- **Why rejected:** fail-closed.

### Alternative E — Evaluate only the current schedule
- **Cons:** loses rest and overlap across the period boundary (Sunday night → Monday morning).
- **Why rejected:** contradicts ADR 4.1.0003 (a).

### Alternative F — Aggregate over-coverage per function across overlapping bands
- **Description:** count "2 atendentes 16h–00h + 1 atendente 18h–22h" (ADR 4.1.0010 Decision 4)
  together, per function and time slice.
- **Cons:** `N` is a target of the **declared band**; aggregating needs slicing time into
  intervals and a second notion of "allocated", with no source.
- **Why rejected:** per demand is the formula of ADR 4.1.0003 (g), `allocated(demand) > N`.

## Consequences

### Positive
- 4.3 can implement either re-ask rule (by key only, or by key plus worsening measure) on the
  same shape — **except** for over-coverage, where lowering `N` over an accepted set adds surplus
  allocations without changing the key, so the doc §3.6.8 invariant requires 4.3 to re-ask on a
  worsening measure there (recorded constraint).
- Tenant and unit mixing is impossible to evaluate.

### Negative
- 4.3 must fetch facts for inactive allocated records too (to satisfy completeness).
- Violations induced by staff changes appear without a schedule mutation; the doc invariants of
  §3.5, §3.6.6 and §3.6.7 hold only for what the schedule itself introduces. A staff-side guard
  versus show-and-fix is a product question for the 4.3 concept (declared divergence 5 of the
  4.2 concept).

### Neutral / trade-offs accepted
- Hours on intersecting distinct bands are summed per allocation (doc §3.6.3, §3.6.10); the
  double count exists only when overlap is disabled or accepted in `warn`.

## Implementation notes

- Stage 4.2: `services/validation/{context,policy_protocol,evaluator}.py`,
  `value_objects/violation.py`.

## References

- [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (a), (g);
  [ADR 4.1.0006](./4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md);
  [ADR 4.1.0012](./4_1_0012-one-record-occupies-at-most-one-slot-per-band.md) Decision 5.
- [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.5, §3.6.0, §6.
- [`docs/stages/4.2-validation-policies/concept.md`](../stages/4.2-validation-policies/concept.md) §5, §7.

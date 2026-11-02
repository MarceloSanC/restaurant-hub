---
title: ADR 4.3.0001 — Publishing is an atomic batch of named operations that refuses or asks acceptance only for the violations it introduces
description: Architecture Decision Record
when-use: Reference before changing how scheduling saves an edit, what counts as an introduced violation, how an acceptance matches a violation, what a no-op operation does, or how a band held only by terminated records' allocations is released
keywords: [adr, scheduling, publish, batch, acceptance, introduced-violation, over-coverage, no-op, version, terminated, inactive-allocations]
status: accepted
created_at: 2026-11-01
updated_at: 2026-11-01
adr_id: 4.3.0001
decision: evaluate_schedule and publish_schedule take an ordered batch of the aggregate's eleven mutations as named operations, apply it in memory atomically against the version the editor saw, evaluate the schedule before and after with the same input, and refuse (block) or ask acceptance (warn) only for violations the batch introduced — new key, or a signed deviation (observed − limit) that changed sign or grew, with over-coverage matched by demand; operations returning the same schedule are no-ops (change_demand_quantity with the current N included, in the domain); a band or demand holding at least one allocation and none of an active record is refused with their count and assignment ids so the manager unassigns them explicitly.
context_stage: 4.3-scheduling-application
bounded_context: scheduling
---

# ADR 4.3.0001 — Publishing is an atomic batch that refuses or asks only what it introduces

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-01. D1/D3 product forks delegated by the sponsor and ratified on 2026-11-01.

## Context

ADR 4.1.0001 fixed *save = publish*: every save is the live schedule, `block` refuses the
mutation, `warn` is accepted consciously at save time, and every mutation carries the version the
editor saw. ADR 4.2.0002 gave violations an identity (`key`) without the measure, so the
application layer can compare evaluations. Four gaps reached Stage 4.3: the save unit (one
mutation per call or a batch), what "introduced by this change" means, when an acceptance covers a
violation (the measure may worsen under the same key), and what a no-op mutation does to the
version. Two forks were product questions (D1 — staff changes that make the schedule violate; D3 —
a band held only by a terminated record's allocation, which is invisible on every screen).

## Decision

1. **Batch.** `evaluate_schedule` and `publish_schedule` receive an ordered tuple of operations, one
   type per aggregate mutation (11). They are applied in order, in memory, on the loaded schedule;
   the first failure refuses the whole batch with its own error (domain errors are not wrapped);
   only the final state is evaluated and saved. The version check happens once, before applying.
2. **Introduced violation.** The schedule is evaluated before and after with the same neighbours,
   staff facts and config. An after-violation is introduced iff its key is absent before, or the
   key is present and its signed deviation (`observed − limit`) changed sign or grew in magnitude —
   one rule for every policy (constant-measure policies reduce to key only; the sign catches a
   workload `both` underload turning into overload). Over-coverage — whose key carries its allocations — matches by (policy, demand): it is
   introduced iff the demand was not over-covered before, an allocation outside the before set
   entered, or the excess grew. Pre-existing violations (from staff changes, D1, or from a config
   changed later) are shown and never refuse nor ask on a change that did not introduce them.
3. **Refuse or ask.** Publish refuses with `BlockingViolationsError` if any introduced violation is
   `block`; otherwise refuses with `UnacknowledgedViolationsError` if an introduced `warn` is not
   covered by an acknowledgement `(key, observed, limit)` — the measure the manager saw, with its
   own limit — of the same key, same deviation sign and a magnitude not smaller than the current
   one (so lowering N or a workload edit after evaluating asks again). Covered warns are recorded as acknowledged in the change record. Evaluate never refuses; it
   returns the introduced ones split by mode.
4. **No-op.** An operation whose result `is` the input schedule is not effective: it does not count
   in the version nor enter the trail; a batch with no effective operation does not write.
   `Schedule.change_demand_quantity` gains the no-op clause in the domain (D2), so the five
   idempotent mutations share one rule (ADR 4.1.0009 Decision 3).
5. **Held by the invisible (D3).** Disabling a band or withdrawing a demand holding **at least
   one** allocation and **none** of an active record raises `InactiveAllocationsInUseError` carrying the count and the
   assignment ids (never the record's id or name). Unassigning them in the same batch releases it.
   With at least one active record's allocation, the domain refusal stands — that one is visible.

## Alternatives considered

### Alternative A — One mutation per call
Each use-case call applies one mutation and saves. Rejected: the acceptance of a warn would be
asked at every intermediate step (an edit sequence goes through invalid intermediate states), and
the version would increase N times for one editor intent with N trail entries. The batch serves
both UX shapes (save-per-action is a batch of one), which 4.5 chooses.

### Alternative B — Refuse or ask every violation present after
Rejected: a violation induced by staff (D1) or by a later config change would block every
unrelated edit to the schedule — the manager could not even fix a different problem.

### Alternative C — Compare by key only, including over-coverage
Rejected: lowering N under an already accepted excess keeps the key and worsens the measure without
asking again (finding of 4.2), and unassigning one excess allocation changes the over-coverage key
and would re-ask a reduction.

### Alternative D (D3) — Auto-remove the invisible allocations, or refuse opaquely
Removing them with the band reintroduces the cascade refused in Q1 of concept 4.1 and disarms the
L-E5 guard without an act of the manager; refusing opaquely is a dead end (the terminated record is
invisible, ADR 4.1.0006).

## Consequences

### Positive
- The rule of ADR 4.1.0001 becomes executable without a parallel "draft" state.
- Pre-existing violations of any origin are visible and never hold an unrelated edit hostage.
- Acceptances re-ask when the measure worsens, closing the 4.2 finding.

### Negative
- A batch with null net effect (N → N+1 → N) still raises the version twice and writes one entry —
  net-effect folding is out of scope.
- Exposing assignment ids of terminated records (D3) is metadata about them; accepted as the
  minimum to unlock the band.

### Neutral / trade-offs accepted
- Evaluating twice per batch is acceptable at pilot volume.

## Implementation notes

`use_cases/_publish.py` holds the protocol (apply, introduced, acknowledgement) shared by
evaluate and publish. Errata dated in concept 4.1 CA11b (four → five idempotent mutations).

## References

- ADR 4.1.0001, ADR 4.1.0006, ADR 4.1.0009 Decision 3, ADR 4.2.0002
- `docs/stages/4.3-scheduling-application/concept.md` §5.5–§5.10, §7 D1–D3, D-ACK, D-NOOP

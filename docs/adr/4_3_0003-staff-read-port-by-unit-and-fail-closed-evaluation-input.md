---
title: ADR 4.3.0003 — Scheduling reads staff through a unit-addressed batch read port served by a non-authorizing staff facade, builds the evaluator input fail-closed, and shows staff-induced violations live instead of guarding staff
description: Architecture Decision Record
when-use: Reference before changing what scheduling reads from staff, how the staff adapter is served, what happens when an allocated record is missing, or before adding a guard in staff against changes that make a published schedule violate
keywords: [adr, scheduling, staff, read-port, facade, fail-closed, roster, reconciliation, inactive, unavailability, staff-induced-violation]
status: accepted
created_at: 2026-11-01
updated_at: 2026-11-01
adr_id: 4.3.0003
decision: StaffReadPort has four batch reads — the active roster of a unit, given records of a unit (active or not), the unit's records linked to a login, and the tenant's job-function catalogue — returning a scheduling-owned StaffMember DTO; the 4.4 adapter serves it from a staff facade that does not authorize (the scheduling use case already did); the evaluator input is the whole active roster plus every allocated record, and an allocated record staff does not return is refused fail-closed, never turned into inactive; staff changes that make the live schedule violate are not guarded in staff but shown live for the manager to fix.
context_stage: 4.3-scheduling-application
bounded_context: scheduling
---

# ADR 4.3.0003 — Staff read port, fail-closed input, staff-induced violations shown live

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-01. D1 (product) delegated by the sponsor and ratified on 2026-11-01.

## Context

Scheduling evaluates staff facts by data (ADR 4.2.0002) and reconciles terminations on read (ADR
4.1.0006). Stage 4.3 must define the read port, its completeness (the workload policy reads the
whole active roster), who serves it (finding 1 of issue #72: staff use cases need a staff actor and
authorize; a facade, per ADR 3.5.0001, does not), what a missing allocated record means, and
whether staff should refuse changes (vacation, removed function, edited workload, rehire) that make
a published schedule violate (D1).

## Decision

1. **Four reads, addressed by unit** (the catalogue by tenant): `list_active_members`,
   `list_members(ids)`, `list_members_of_user(user_id)`, `list_job_functions`; no tenant-wide
   listing of records. They return `StaffMember`/`JobFunctionEntry`, scheduling's own DTOs.
2. **Served by a non-authorizing staff facade** (4.4). The scheduling use case authorized the read
   with a scheduling permission; going through staff use cases would demand a staff actor and a
   staff permission for a read scheduling already authorized.
3. **Input completeness, fail-closed.** Facts = active roster ∪ allocated records (schedule and
   neighbours) ∪ assignment targets. An allocated record staff does not return is **absent**, not
   inactive: the use case refuses before evaluating with `MissingStaffRecordsError`, carrying the
   affected assignment ids (ADR 4.2.0002 Alt D rejected) — in evaluate, publish, get and the
   calendar alike. The reverse guard that makes the state unreachable is Stage 4.4's; it is a
   check-then-act across BCs, so a race can still produce the state, and the refusal also blocks
   the neighbours (they enter the input). A repair use case is a 4.4 finding.
4. **Staff-induced violations are shown, not guarded (D1).** Staff keeps accepting cadastro edits
   (ADR 3.4.0006); the next evaluation shows the violation live, it never blocks an unrelated edit
   (ADR 4.3.0001 §2), and the manager fixes it. The domain doc's invariants §3.5/§3.6.6/§3.6.7/§3.6.8 hold
   for what the **schedule** introduces (dated note).

## Alternatives considered

### Alternative A — Read through staff use cases
Rejected (finding 1 of #72): needs a staff actor and authorizes twice with different vocabularies.

### Alternative B — Treat a missing allocated record as inactive
Rejected: hides a real inconsistency as a reconciliation; ADR 4.2.0002 Alt D.

### Alternative C (D1) — Guard in staff
Rejected: inverts ADR 3.4.0006 (HR would depend on the manager editing the schedule first), does
not cover workload edits nor rehire, and is impractical on a terminated record nobody sees.

## Consequences

### Positive
- No cross-BC transaction, no reverse dependency from staff for D1.
- A missing record surfaces as a refusal instead of silently dropping hours.

### Negative
- A published schedule may contain a `block` unavailability until the manager acts.
- Until 4.4 wires the reverse guard, a hard-deleted record makes its schedule unreadable with
  evaluation (fail-closed by design).

### Neutral / trade-offs accepted
- One extra roster read per evaluation; fine at pilot volume.

## Implementation notes

`use_cases/_inputs.py` builds the facts in one place. The first `find_by_user_id` in staff decides
scope and index (ADR 3.5.0004 Alt C) — 4.4.

## References

- ADR 3.4.0006, ADR 3.5.0001, ADR 4.1.0006, ADR 4.2.0001, ADR 4.2.0002
- `docs/domain/scheduling/shift-scheduling.md` §3.5, §3.6.6, §3.6.7, §3.6.8, §3.10.1, §6

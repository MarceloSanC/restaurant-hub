---
title: ADR 4.3.0002 — Every scheduling use case authorizes its own target through a scheduling AccessGuard whose scope carries the authenticated subject
description: Architecture Decision Record
when-use: Reference before adding a scheduling use case, changing the scheduling permission names, reading the AuthorizedScope in a use case, or promoting the authorize-first rule to a transversal ADR
keywords: [adr, scheduling, authorization, access-guard, fail-closed, permission, subject, user-id, my-schedule]
status: accepted
created_at: 2026-11-01
updated_at: 2026-11-01
adr_id: 4.3.0002
decision: scheduling reapplies ADR 3.7.0001 with a port of its own — every use case receives an AccessGuard by constructor and, as the first statement of execute, authorizes one of three unit-scoped permissions (view_schedule, manage_schedule, view_own_schedule) on the command's tenant and unit; the returned scope is never an address, but carries the authenticated subject's user_id, which is read for the trail author and for "my schedule"; the rule is not promoted to a transversal ADR until a third bounded context repeats it.
context_stage: 4.3-scheduling-application
bounded_context: scheduling
---

# ADR 4.3.0002 — Every scheduling use case authorizes its own target

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-01.

## Context

ADR 3.7.0001 made every staff use case authorize the target its command declares before any other
statement, through staff's `AccessGuard`. The auditor of Stage 3.7 attached to issue #72 the
question of whether scheduling adopts the pattern from its first use case, and whether the rule
becomes a transversal ADR or is reapplied per bounded context. Scheduling also needs something
staff never needed: the **subject** — who saved (the trail author, ADR 4.1.0001) and whose
schedule "my schedule" is (ADR 0.0.0005: the subject derives from the token, never from the
request).

## Decision

1. **A port of scheduling's own** in `application/ports/out/access_guard.py`, with only
   `authorize(actor, permission, *, tenant_id, unit_id) -> AuthorizedScope`; both targets are
   required, because every scheduling permission is unit-scoped (ADR 4.1.0004 §1).
   `AuthorizedScope` carries `tenant_id`, `unit_id` and `user_id`.
2. **Permissions** are `str` values in the port module: `view_schedule`, `manage_schedule`,
   `view_own_schedule` (the identity enum and role map are Stage 4.5's, ADR 4.1.0004).
3. **Authorize first.** The first statement of every `execute` is the `authorize` call with the
   command's actor, tenant and unit (ADR 3.7.0001 §3–§4). Nothing — no port, clock, id generator
   or request validation — runs before it.
4. **The scope is not an address** (ADR 3.7.0001 §3), **but its `user_id` is read**: as the trail
   author in `publish`/`create`, and as the "me" of `get_my_schedule`. Laws L-SG1–L-SG4 (raw
   refusal; confirmed tenant and unit, never empty; one authorization per target; subject from the
   token, never empty) live in the port docstring and are proven against the fake.
5. **Per bounded context, not transversal.** The rule is now applied in two BCs with two ports of
   different shape; it becomes a transversal ADR when a third BC repeats it.

## Alternatives considered

### Alternative A — Reuse staff's port or move it to `shared/`
Rejected: `bc-independence` forbids importing staff's port, and its shape is staff's (it has
`authenticate`, staff's permission names, and a scope without subject). A `shared/` port would need
BC-neutral types and would still not fit both consumers (LAYOUT §4: moving to `shared/` is measured).

### Alternative B — Authorize only at the HTTP boundary (4.5)
Rejected: the regression ADR 3.7.0001 closed in staff — a use case that answers whatever the caller
asks — would be born in scheduling, and retrofitting cost 17 use cases and ~20 suites in 3.7.

### Alternative C — Carry the subject in the query
Rejected: the subject would come from the request (ADR 0.0.0005 clause 1).

## Consequences

### Positive
- Scheduling is fail-closed from its first commit; a property test over `use_cases/` keeps it so.
- The trail author and "my schedule" have one trusted source.

### Negative
- The guard does not authenticate the actor (same threat model as ADR 3.7.0001): an in-process
  driver that forges an actor passes; finding for the first non-HTTP driver.

### Neutral / trade-offs accepted
- A permission-name typo is caught by tests, not by the type checker (ADR 3.4.0001 price).

## Implementation notes

4.4/4.5 wire the translator in the composition root (identity's decision, scheduling's vocabulary).

## References

- ADR 3.7.0001, ADR 3.4.0001, ADR 0.0.0005, ADR 4.1.0004
- Issue #72 comments (findings of the 3.7 auditor)

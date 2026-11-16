---
title: ADR 4.4.0004 — Staff exposes a non-authorizing read facade over its repositories, scheduling implements StaffReadPort in a gateway that imports only that facade through a second named bc-independence pair, the login lookup is unit-scoped with no new index, and the reverse delete guard is not wired by Stage 4.4
description: Architecture Decision Record
when-use: Reference before letting scheduling read staff any other way, before adding a method or an index to staff for the login lookup, before adding a third import pair between bounded contexts, or when the Stage that owns the reverse delete guard starts
keywords: [adr, scheduling, staff, facade, gateway, bc-independence, import-linter, staff-read-port, user-id, reverse-guard, cross-bc]
status: accepted
created_at: 2026-11-16
updated_at: 2026-11-16
adr_id: 4.4.0004
decision: 'features/staff/application/facade.py exposes StaffReadFacade, an in-process open host service with four read methods in primitive types built over EmployeeRepository and JobFunctionRepository, which does not authorize; scheduling implements StaffReadPort in features/scheduling/adapters/out/staff/local_staff_read_adapter.py importing only that facade, under a second named ignore_imports pair pinned by test; the records linked to a login are found by filtering the unit listing, with no new port method and no index; the reverse delete guard of ADR 4.1.0006 is a staff deliverable and is left to issue #194.'
context_stage: 4.4-scheduling-persistence
bounded_context: scheduling
---

# ADR 4.4.0004 — Staff read facade, the scheduling → staff edge, and the reverse guard left out

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-16. Leaving the reverse guard out is a scope fork delegated by the sponsor
to the orchestrator and decided with the recommended option.

## Context

ADR 4.3.0003 fixed that scheduling reads staff through `StaffReadPort`, served by a staff facade
that does not authorize. Three things were left for Stage 4.4: where the adapter lives
(ADR 4.1.0006), the scope and index of the lookup by `user_id` (ADR 3.5.0004), and the Stage that
wires the reverse delete guard (concept 4.3 named 4.4). LAYOUT §3 allows exactly one shape for a
crossing between bounded contexts: a facade in the supplier's application layer, a gateway in the
consumer's `adapters/out/<supplier>/`, and a named import pair.

Stage 3.11 is in flight and adds methods to the staff ports.

## Decision

1. **`StaffReadFacade`** in `features/staff/application/facade.py`: `list_active_records`,
   `list_records`, `list_records_of_user` (unit-addressed) and `list_functions`
   (tenant-addressed). Primitive signatures; it returns frozen dataclasses of primitives. It is
   built over `EmployeeRepository` and `JobFunctionRepository`, using only `list_by_unit` and
   `list_by_tenant`. It does not authorize: the scheduling use case already authorized the read
   with a scheduling permission.
2. **`LocalStaffReadAdapter`** in `features/scheduling/adapters/out/staff/` implements
   `StaffReadPort`, imports from staff only the facade, and translates primitives into
   scheduling's own types.
3. **Second named pair** in the `bc-independence` contract:
   `restaurant_hub.features.scheduling.adapters.out.staff.* ->
   restaurant_hub.features.staff.application.facade`. The exact list of pairs stays pinned by
   test on both sides.
4. **Login lookup is unit-scoped and unindexed.** `list_records_of_user` filters the unit listing
   (inactive included) by `user_id`. No `find_by_user_id` is added to the staff port and
   `employees.user_id` gets no index.
5. **The reverse delete guard is not wired here.** It is a deliverable of the staff bounded
   context — a new port in staff, a behaviour change in `delete_employee` and
   `delete_job_function`, a staff adapter over a scheduling read facade and a third named pair.
   Issue #194 gives it an owner in the roadmap. Stage 4.4 delivers the schema that answers the
   query (ADR 4.4.0001).

## Alternatives considered

### Alternative A — A translator class in the composition root
Rejected: the composition root holds only wiring since ADR 0.0.0016.

### Alternative B — The adapter calls staff use cases
Rejected by ADR 4.3.0003 (Alternative A there): every staff use case authorizes with a staff
actor and a staff permission.

### Alternative C — A dedicated `find_by_user_id` with an index
Rejected for now: `StaffReadPort` only asks for the link inside one unit, the unit listing
already has its index (ADR 3.3.0005), and changing the staff port would collide with Stage 3.11.
It is the candidate when a read by login crosses units.

### Alternative D — Wire the reverse guard in Stage 4.4, whole or only the scheduling query
Rejected: the whole guard adds deliverables in a second bounded context and five or more tasks
to a Stage whose target layer is `adapters/out` of scheduling (PIPELINE §4.2); the query alone
would be a port method with no consumer. The risk it covers needs allocations in production,
which only exist after Stage 4.5.

## Consequences

### Positive
- No existing staff file changes; the staff side of the edge is one new module.
- The edge has the validated form of ADR 3.5.0001, pinned by the same kind of test.

### Negative
- Every facade read loads the whole roster of the unit. Accepted at pilot volume.
- Until issue #194 lands, a hard-deleted record with allocations makes its schedule and the
  neighbours refuse with `MissingStaffRecordsError` (ADR 4.3.0003 §3), and a deleted job function
  still referenced by a demand is not refused at all: the demand reads with no function name.
  Issue #194 must land before schedule editing reaches production.
- ADR 4.1.0006, ADR 4.3.0003 and ADR 3.5.0004 expected Stage 4.4 to wire the guard and to add
  `find_by_user_id` with its index; they receive a dated erratum pointing here.

### Neutral / trade-offs accepted
- The facade reads repositories directly, unlike identity's facade, which wraps use cases:
  identity's use cases do not take an actor, staff's do.

## Implementation notes

The composition root builds the facade over the same repository instances that serve the staff
routes. `tests/unit/features/staff/test_bc_independence.py` and
`tests/unit/features/scheduling/test_bc_independence.py` assert the exact pairs.

## References

- ADR 0.0.0016, ADR 3.3.0005, ADR 3.5.0001, ADR 3.5.0004, ADR 3.7.0001, ADR 4.1.0006, ADR 4.3.0003
- `docs/LAYOUT.md` §3
- `docs/stages/4.4-scheduling-persistence/concept.md` §4, §7 D-STAFF, D-USERID, D-REVERSE

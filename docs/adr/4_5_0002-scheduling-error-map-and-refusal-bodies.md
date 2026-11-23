---
title: ADR 4.5.0002 — Scheduling maps its errors to 404/409/422 by the staff band definitions, answers the optimistic refusal with 409 carrying changed_neighbour_id, and adds a code and the refusal state to the error body
description: Architecture Decision Record
when-use: Reference before adding a scheduling error, before changing a status or a refusal body of the scheduling edge, or when a client has to tell a resend from a reload
keywords: [adr, scheduling, http, error-map, status, 409, 422, optimistic-locking, changed_neighbour_id, refusal-body]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: 4.5.0002
decision: 'The scheduling error map lives in the inbound HTTP adapter, registered on both roots, with the staff band definitions (404 addressed resource absent, 409 conflict with stored state, 422 content that violates an invariant); the optimistic refusal is 409 with expected_version, current_version and changed_neighbour_id; blocking and unacknowledged violations are 422 with the violations; every scheduling error body carries type=scheduling_error and a code derived from the class name.'
context_stage: 4.5-scheduling-http
bounded_context: scheduling
---

# ADR 4.5.0002 — Scheduling error map and refusal bodies

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-23 (Stage 4.5, issue #254).

## Context

Scheduling has two error roots (ADR 3.9.0001) and no edge until this Stage. Several refusals
carry state the client needs: the current version and the neighbour that changed
(`ScheduleVersionConflictError`, ADR 4.4.0005 §Decision 3: "how the client offers it is Stage
4.5's"), the violations a batch introduces (ADR 4.3.0001), the allocation ids that block a
removal or that staff no longer returns (ADR 4.3.0003 §3), and the function not enabled in the
unit (ADR 4.3.0005). Staff's map (ADR 3.4.0002 §4) defines the bands; staff's body carries a
`type` discriminator (ADR 3.6.0002).

## Decision

1. **Map in the feature, one handler on both roots** (`SchedulingError`,
   `SchedulingApplicationError`), resolving by MRO against an explicit dict; totality and pair-by-pair
   checks as in ADR 3.4.0002 §3 and §3b.
2. **Bands by the staff definitions**: 404 — the addressed resource is absent at the address
   (`ScheduleNotFoundError`; and, as staff's `JobFunctionNotFoundError`, the staff record or the
   function of **another aggregate** the body names); 409 — conflict with stored state (version,
   period taken, id in use, a reference that forbids removal, a terminated record, a function not
   enabled in the unit, allocations of invisible records); 422 — the request or the content violates
   an invariant, including **blocking and unacknowledged violations** (the batch is well-formed; the
   schedule it would produce breaks a rule), an **internal value** of the schedule the batch names and
   that does not exist, and an aggregate invariant the batch itself breaks — the four `Duplicate*`
   (band, demand, assignment, assignment in band) and the same creation id twice, as staff's
   `OverlappingUnavailabilityError` (ADR 3.4.0002 §4). The batch is applied in memory (ADR 4.3.0001 ›
   "atomic batch"); a creation id already stored is refused earlier, as `IdentifierInUseError`, in the
   conflict band. The full
   table is in concept 4.5 §6.
3. **The optimistic refusal is 409** (RFC 9110 §15.5.10), never 412: the version travels in the body,
   not in a conditional header field (RFC 9110 §15.5.13). The body carries `expected_version`,
   `current_version` and `changed_neighbour_id`. `null` means the edited schedule changed — reload and
   redo; a value means a neighbour changed and the edited schedule did not — resend the same batch
   (ADR 4.4.0005 §Decision 3).
4. **Body** `{"detail", "type": "scheduling_error", "code", ...state}`. `code` is the class name in
   snake_case without the `Error` suffix, pinned by a test listing every code. State fields:
   `violations` (blocking/unacknowledged), `assignment_ids` and `count` (inactive allocations,
   missing records), `job_function_id` (not enabled), `id_type` and `value` (id in use). No field
   names an **invisible** record — inactive or missing in staff — other than by allocation id (ADR
   4.3.0001 §5); `employee_id` in a violation is an active record the editor already sees.
5. **No 401/403 entry**: they are identity's, with constant bodies (ADR 2.4.0001), raised raw by the
   guard (L-SG1).

## Alternatives considered

### Alternative A — 412 Precondition Failed for the version conflict
- **Why rejected:** 412 is for conditions in request header fields; the expected version is a body
  field of the batch, and the neighbour case is not a precondition the client stated at all.

### Alternative B — violations as 409
- **Why rejected:** ADR 3.4.0002 §4 keeps 409 for "something else in the database is in the way";
  a rule broken by the produced schedule is content the client sent, as
  `OverlappingUnavailabilityError` is in staff.

### Alternative C — distinguish refusals only by `detail` text
- **Why rejected:** the client must branch (resend, reload, acknowledge, undo) on a stable value;
  text is for people.

## Consequences

### Positive
- The client can implement resend × reload × acknowledge from the body alone.
- A new scheduling error without an entry fails `tests/unit/test_status_map.py`.

### Negative
- Renaming an error class changes its `code`; the pinned code list makes it a reviewed change.

### Neutral / trade-offs accepted
- Five entries are unreachable over HTTP in Stage 4.5 and exist by totality (concept 4.5 §6).
- `MissingStaffRecordsError` (409) also comes out of reads, and no client action resolves it; issue
  #194 must close before schedule editing reaches production.

## References

- [ADR 3.4.0002](./3_4_0002-staff-http-error-status-mapping.md),
  [ADR 3.6.0002](./3_6_0002-boundary-identifier-validation.md),
  [ADR 3.9.0001](./3_9_0001-error-roots-by-meaning-status-by-map.md),
  [ADR 2.4.0001](./2_4_0001-http-error-status-mapping.md),
  [ADR 4.4.0005](./4_4_0005-save-checks-the-neighbour-versions-the-evaluation-read.md),
  [ADR 4.3.0005](./4_3_0005-demand-accepts-only-functions-enabled-in-the-unit.md)
- HTTP semantics: RFC 9110, section 15.5.10 (Conflict) and section 15.5.13 (Precondition Failed)
- Concept: [`../stages/4.5-scheduling-http/concept.md`](../stages/4.5-scheduling-http/concept.md) §4.3, §6, §7 D-ERR

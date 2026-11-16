---
title: ADR 4.4.0002 — The schedule audit trail is one append-only row per change record, with operations and acknowledgements as JSON documents, kept as long as the schedule and not read by the product in v1
description: Architecture Decision Record
when-use: Reference before changing how the schedule trail is stored, before adding a purge or a retention window, before exposing the trail to managers or employees, or when Step 7 needs the state of a schedule at a past date
keywords: [adr, scheduling, audit-trail, jsonb, change-record, retention, lgpd, granularity, append-only, history]
status: accepted
created_at: 2026-11-16
updated_at: 2026-11-16
adr_id: 4.4.0002
decision: 'Each accepted add or save writes exactly one row in schedule_changes, in the same transaction as the state: a per-schedule ordinal, the author user id, the absolute instant, the previous and the resulting version, the ordered effective operations and the acknowledged violations as two JSONB arrays whose decimals, dates and instants are text. The trail is append-only, is kept as long as the schedule exists (no purge in v1), carries only opaque identifiers, and has no read path in the product: the employee sees only the live schedule.'
context_stage: 4.4-scheduling-persistence
bounded_context: scheduling
---

# ADR 4.4.0002 — Audit trail: one row per change record

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-16. The retention and the employee-visibility forks are product questions
delegated by the sponsor to the orchestrator and decided with the recommended option.

## Context

ADR 4.3.0004 made every scheduling write a single repository call carrying a `ScheduleChange`
(author, instant, previous version, effective operations in order, acknowledged violations) and
left the storage granularity to Stage 4.4. The domain doc asks three more questions of this
Stage: snapshot or diff, how long the trail is kept (basic LGPD), and what an employee sees when
an allocation of theirs changes. The definition of done is "every schedule mutation generates an
audit entry".

## Decision

1. **One row per `ScheduleChange`.** Table `schedule_changes`, primary key `(schedule_id, seq)`;
   `seq` is 1 on creation and the next ordinal on each save. Columns: `author_user_id`,
   `occurred_at` (absolute instant), `previous_version` (null on creation), `resulting_version`
   (the version of the schedule written with it), `operations`, `acknowledged`.
2. **Diff as JSON documents.** `operations` is an ordered JSONB array with one object per
   effective operation; a `kind` field discriminates the eleven operation types.
   `acknowledged` is a JSONB array of violations. `Decimal`, dates and instants are stored as
   text so the round trip is exact. The codec is a pair of pure functions in `mappers.py`; the
   keys are listed field by field in concept 4.4 §5.6 and pinned by literal tests.
   **The diff must not lose state.** The trail is the source of "what applied that day" for
   Step 7 (ADR 4.1.0001). The state of a schedule has three parts: the period and the calendar,
   which belong to creation, never change and stay on the root row; the bands, which the
   operations describe; and the `function_exception` mark, derived by the use case when the
   allocation is made and absent from the operation. The `assign_employee` object therefore
   records the mark the allocation received, read from the schedule written with it. Only the
   last `assign_employee` of an assignment id in the batch, with no later `unassign_employee` of
   that id, gets the mark; the others get `null`. The root row plus the operations replayed from
   creation reproduce every **written** version of a schedule born through `create_schedule`.
3. **Same transaction as the state** (law L-SC3): a refused or failed write leaves neither.
4. **Append-only.** The adapter never updates or deletes a trail row. The foreign key to
   `schedules` is `ON DELETE RESTRICT`.
5. **Retention.** The trail is kept as long as the schedule exists; v1 has no purge. It stores
   opaque identifiers only (login id of the author, employee record ids, function ids), never a
   name or an e-mail.
6. **No reader in the product.** No port, use case or route reads the trail in Step 4. An
   employee sees the live schedule; the change notice is the optional e-mail of Stage 4.6.

## Alternatives considered

### Alternative A — One row per operation in a child table
Rejected: it stores the same information in more rows and needs a second table for the
acknowledgements, which belong to the batch. Both shapes satisfy "every mutation generates an
entry", and each converts into the other by a migration, so the simpler one wins.

### Alternative B — Typed columns per operation type
Rejected: eleven sparse shapes for a log no law reads.

### Alternative C — A snapshot of the aggregate per version
Rejected for v1: it multiplies storage by the number of saves and no consumer exists; with the
mark recorded (Decision 2) the root row and the diff are enough to rebuild any written version. It stays the candidate if
Stage 7.2 prefers reading a ready state to replaying operations.

### Alternative D — Purge after a retention window, or anonymise the author
Rejected for v1: nothing deletes a schedule, the sponsor ruled that historical data stays
(ADR 4.1.0006), and deleting is the irreversible side. A per-tenant retention window with a purge
job is the candidate for Stage 6.3 or for the Stage that brings a legal requirement.

### Alternative E — Show the employee a "changed since" mark or the history
Rejected: the overview lists no history for the employee and the notification has its own Stage.

## Consequences

### Positive
- One port object, one row: the trail cannot disagree with the write that produced it.
- A new field of an operation needs no migration: the reader ignores unknown keys and supplies,
  for old rows, the value they imply. Renaming a key or a `kind` value does need a data
  migration.

### Negative
- "Who changed assignment X" is a JSON query, not an indexed lookup.
- The trail is write-only in the product until a Stage gives it a reader.
- The port accepts `add` of a schedule that already has content with no operations (the law
  suite does it); that initial state is not in the trail. No use case reaches it.

### Neutral / trade-offs accepted
- JSONB here does not contradict ADR 3.3.0001: that ADR keeps **aggregate state** out of JSONB
  because guard laws rest on foreign keys; the trail is a log with no law resting on it.

## Implementation notes

psycopg 3.3.4 serialises JSONB with `json.dumps` and reads with `json.loads`; `Decimal`, `date`
and `datetime` raise on write and fractions come back as `float`, hence text. `occurred_at` is
an aware instant by the port's law and is always read back aware in UTC; a naive value is
outside the contract.

## References

- ADR 3.3.0001, ADR 4.1.0001, ADR 4.1.0006, ADR 4.3.0001, ADR 4.3.0004
- `docs/domain/scheduling/shift-scheduling.md` §3.5, §6
- `docs/stages/4.4-scheduling-persistence/concept.md` §5, §7 D-AUDIT, D-RET, D-EMP, D-TRAILREAD

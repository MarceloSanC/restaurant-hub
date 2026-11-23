---
title: ADR 4.4.0003 — Every schedule write takes a transaction-scoped advisory lock on its unit, checks the port laws explicitly in their order, compares the version inside the lock and rewrites the children; aggregate reads use a single snapshot
description: Architecture Decision Record
when-use: Reference before adding a writer of the schedules tables, before replacing the unit lock by a row lock, before changing how the version conflict is detected, or before changing the isolation level of the schedule reads
keywords: [adr, scheduling, concurrency, advisory-lock, optimistic-locking, version, transaction, repeatable-read, write-protocol, integrity-error]
status: accepted
created_at: 2026-11-16
updated_at: 2026-11-22
adr_id: 4.4.0003
decision: 'PostgresScheduleRepository.add and save run in one transaction that first takes pg_advisory_xact_lock on a hash of (tenant_id, unit_id), then runs the checks of the port laws explicitly and in the order the laws fix, then writes the root, rewrites the children by delete and reinsert, and inserts the trail row; the stored version is compared with expected_version inside the lock; the database constraints remain the integrity guarantee and two of them are translated by name on add; save writes the version and the children, never the period or the calendar; find_by_id and the two listings read root and children inside one REPEATABLE READ transaction.'
context_stage: 4.4-scheduling-persistence
bounded_context: scheduling
---

# ADR 4.4.0003 — Unit lock, explicit law checks and version comparison on schedule writes

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-16.

## Context

The laws of `ScheduleRepository` compare a schedule with the **other** schedules of its unit:
a period that crosses another schedule is refused (L-SC2), an internal id used by another schedule
is refused (L-SC4), and the laws fix the order of the checks. The contract suite runs the
same body against the fake and the adapter, so the adapter must refuse with the same error in the
same order, also under concurrency. ADR 4.1.0001 requires the optimistic version check to be
atomic.

Two facts from the PostgreSQL 16 sources constrain the design. An exclusion constraint hit by two
concurrent inserts may answer with a deadlock (reported as `OperationalError`) instead of a
violation. And the id that collided on a primary key reaches the client only inside the message
text, which the project does not parse (ADR 3.3.0004).

## Decision

1. **Unit lock first.** `add` and `save` open one transaction and execute
   `pg_advisory_xact_lock(hashtextextended(<tenant_id> || <separator> || <unit_id>, 0))`. The lock
   is released at commit or rollback and serialises the schedule writers of one unit.
2. **Explicit checks, in the order of the law.** `add`: schedule id (global) → period → internal
   ids. `save`: address → version → internal ids. Each check is a query run inside the
   lock; under `READ COMMITTED` every statement after acquiring the lock sees what the previous
   writer committed. The id reported by `IdentifierInUseError` is canonical — first colliding
   type in the order band → demand → assignment, then the smallest id by code point, computed in
   Python — and the port docstring, the fake and the law suite are aligned to it in this Stage
   (the fake used to report by insertion order of the other schedules, which a database does not
   have).
3. **Version inside the lock.** `save` reads the stored version at the three-part address and
   compares it with `expected_version`; a mismatch raises `ScheduleVersionConflictError` with the
   stored one.
4. **Rewrite of the children.** `save` updates the version on the root, deletes the bands of the
   schedule (the cascade removes demands and assignments) and reinserts the aggregate with its
   positions. It does not write the period or the calendar: they belong to creation
   (ADR 4.1.0009), no domain mutation changes them, and a schedule reaching `save` with different
   ones is outside the port's contract. `save` therefore cannot violate L-SC2.
5. **Constraints are the guarantee, not the error source.** Two are translated by constraint
   name, both in the map of `add`. `pk_schedules` is reachable through the adapter: two `add` with the same schedule id in
   different units do not contend for the same lock. `ex_schedules_unit_days_disjoint` only
   answers a writer that bypassed the lock; its translation is one map entry that keeps the
   database guarantee from surfacing unnamed. The others surface as a raw `IntegrityError`.
6. **Single-snapshot reads.** `find_by_id`, `list_in_range` and `list_ending_before` read the
   root and the three child tables inside one `REPEATABLE READ` transaction.

## Alternatives considered

### Alternative A — Row lock on the schedule (`SELECT … FOR UPDATE`) plus translation by name
The staff precedent (ADR 3.3.0006). Rejected: the row lock serialises writers of **one**
schedule, while L-SC2 and L-SC4 compare **different** schedules of the unit; the id collision
would land on a child primary key whose colliding value is only in the message text; and the
exclusion constraint may deadlock under concurrent inserts.

### Alternative B — `UPDATE … WHERE version = :expected` and check the row count
Rejected: it cannot tell "not found" from "version conflict" without a second query, does not
carry the current version, and still leaves the cross-schedule checks unserialised.

### Alternative C — Diff the children instead of rewriting them
Staff diffs because a rewrite re-takes locks on rows of another aggregate. A schedule's children
reference nothing outside the aggregate and the unit lock excludes concurrent writers, so the
rewrite is safe and far simpler. Revisit if a schedule grows beyond the pilot volume.

## Consequences

### Positive
- Deterministic refusals, the same in the fake and in the adapter, under concurrency.
- The optimistic check has no window between reading and writing the version.

### Negative
- Writes to different schedules of the same unit are serialised. Accepted at pilot volume.
- The lock is a convention: any future writer of these tables must take it. Without it, the
  constraints still protect the data, with an untranslated error.

### Neutral / trade-offs accepted
- A hash collision between two units only serialises them needlessly.
- The lock does not close the boundary write skew of concept 4.3 §3: the evaluation happens in
  the use case, before this transaction.

## Implementation notes

`features/scheduling/adapters/out/postgres/schedule_repository.py`. The reads set the isolation
level before the first statement of the transaction, as `PostgresEmployeeRepository` does.

## References

- ADR 3.2.0001, ADR 3.3.0004, ADR 3.3.0006, ADR 4.1.0001, ADR 4.3.0004, ADR 4.4.0001
- PostgreSQL 16 documentation: "Explicit Locking" (Advisory Locks), "Transaction Isolation"
- `docs/stages/4.4-scheduling-persistence/concept.md` §5, §6, §7 D-LOCK, D-SKEW
- [ADR 4.4.0005](./4_4_0005-save-checks-the-neighbour-versions-the-evaluation-read.md) (issue #199)

## Supersessão parcial

**2026-11-22 — o último item de §Consequences › "Neutral / trade-offs accepted" (*"The lock
does not close the boundary write skew of concept 4.3 §3"*) foi superado pelo ADR 4.4.0005; a
ordem do `save` em §Decision 2 ganha um passo.** O `save` recebe agora as versões das escalas
adjacentes que a avaliação leu (`ExpectedNeighbours`, lei L-SC9 do port) e as compara **dentro
deste lock**, depois da versão e antes dos ids internos: onde §Decision 2 diz *"`save`: address
→ version → internal ids"*, leia-se endereço → versão → vizinhas → ids internos. O lock é o que
torna a comparação válida no commit: todo escritor da unidade o toma, então a vaga conferida não
muda entre a checagem e o commit. O resto da decisão — o lock, a comparação da versão, a
reescrita das filhas, as leituras em snapshot único — continua valendo. Motivo e alternativas:
ADR 4.4.0005.

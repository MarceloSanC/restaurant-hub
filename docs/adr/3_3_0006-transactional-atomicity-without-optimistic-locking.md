---
title: ADR 3.3.0006 — Staff writes are transactionally atomic with guards inside the transaction, but lost update remains possible and is escalated
description: Architecture Decision Record
when-use: Reference before adding a version column or an If-Match/ETag flow to staff, when reasoning about concurrent edits of the same employee record, or before changing the transactional boundary of a staff repository method
keywords: [adr, concurrency, lost-update, optimistic-locking, version, select-for-update, transaction, atomicity, read-modify-write, staff, etag]
status: accepted
created_at: 2026-08-10
updated_at: 2026-11-23
adr_id: 3.3.0006
decision: every staff repository method runs its guards and its write inside one transaction and the employee update takes a row lock on the lookup, which closes partial-aggregate states and guard interleaving; optimistic concurrency control is not introduced because it would require a version token to cross the port signature published by Stage 3.2, and is escalated to Stage 3.4
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0006 — Transactional atomicity, without optimistic locking

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Concept 3.2 §5 rule 17 states that every edit is a read-modify-write of the whole
`Employee`, with no concurrency control, so two simultaneous edits have
"last write wins" semantics — and escalated a `[finding]` to this Stage
(concept 3.2 §10) naming `version` or `SELECT … FOR UPDATE` as directions.

The relevant shape of the existing contract:

- The ports are **synchronous** and there is no Unit of Work port (ADR 2.2.0004);
  identity fixed the transactional boundary as `Engine` injected, one transaction
  per public method (concept 2.3 §7, Decision 6).
- `find_by_id` returns an `Employee`; `update` takes an `Employee`. Neither
  carries a version, and `Employee` is a `frozen` dataclass of Stage 3.1 with no
  such field.
- The read that a use case does (`find_by_id`) and the write it later performs
  (`update`) are **two separate port calls**, hence two separate transactions.
- Issue #38 lists as an explicit non-goal: "Mudança de comportamento dos use
  cases da 3.2 — esta Stage implementa a fronteira, não a redefine."

There are two distinct hazards behind the word "concurrency", and conflating them
is what makes this decision look harder than it is:

1. **Torn or interleaved writes** — an aggregate observable in a half-written
   state, or two writers whose guard evaluations interleave so that both pass a
   guard only one should pass.
2. **Lost update** — two writers who each read state *v*, each compute a
   different *v+1*, and the second silently discards the first's change.

## Decision

**This Stage closes hazard 1 and explicitly does not close hazard 2.** Closing
hazard 1 takes three pieces, and all three were shown by measurement to be
necessary.

**(a) One transaction per write, guards included.** Every public write method
opens `engine.begin()` around its guards *and* its write.
`EmployeeRepository.update` performs its normative lookup as
`SELECT unit_id … WHERE id = :id AND tenant_id = :t FOR UPDATE` inside that
transaction. Absent row ⇒ `EmployeeNotFoundError`; different `unit_id` ⇒
`EmployeeRelocationError`; then the parent `UPDATE` and the child write. The row
lock serialises two concurrent updates of the same record, so their guard
evaluations cannot interleave. The referential pre-check of law L-E4 runs in the
same transaction as the insert of the link rows, with the foreign key as the
backstop (ADR 3.3.0004).

**(b) The child tables are written by difference, not rewritten wholesale.**
Deleting every link row and re-inserting it would touch rows that did not change
and would invert the lock order against a concurrent `delete_job_function`, which
holds `KEY SHARE` through the `RESTRICT` check. Measured: that produces
`DeadlockDetected` and kills the *legitimate* `update` — the one that was not even
changing the function set. Worse, `40P01` is an `OperationalError`, not an
`IntegrityError`, so it bypasses the translator entirely and would surface as a
500. Deleting only the removed links and inserting only the added ones means an
update that does not touch a function never contends for it.

**(c) Reads of a multi-table aggregate run under `REPEATABLE READ`.** This is the
piece that a "we have transactions, we're fine" reading misses. `find_by_id` and
`list_by_unit` assemble an `Employee` from four tables in separate statements;
under `READ COMMITTED` — the default — each statement takes a fresh snapshot.
Measured, a write committing between the statements yields an aggregate that
**never existed** (old parent, new child), and a concurrent `delete` yields an
employee with no job functions at all — which, because rehydration goes through the
constructor, raises `EmployeeNotFoundError`'s neighbour `EmptyJobFunctionsError`
from a method the port types as `Employee | None`. Under `REPEATABLE READ` the
divergence disappears. Atomicity is therefore closed on **both** ends: writes are
transactional, and reads see one snapshot.

**"Last write wins" therefore remains the semantics of two concurrent edits**, and
is documented as such rather than quietly implied. So does the residual deadlock:
two actors genuinely contending for *the same* job function can still produce
`40P01`, which rises raw and is escalated to Stage 3.4 for HTTP treatment.

Optimistic concurrency control is **escalated** as a `[finding]` to
**Stage 3.4-staff-http**, with the version column entering in that Stage's
migration alongside the `ETag`/`If-Match` surface.

## Alternatives considered

### Alternative A — `version` column with `UPDATE … WHERE version = :expected`
- **Description:** add an integer column, bump it on write, and reject when the
  expected version does not match.
- **Pros:** the textbook answer; cheap at the database level; no locks held.
- **Cons:** it only works if the expected version *travelled out* on the read and
  *came back* on the write. That means adding a field to `Employee` (Stage 3.1's
  frozen entity) or a parameter to `update` (Stage 3.2's port signature) — a
  retroaction of the contract this Stage exists to implement, and a declared
  non-goal of issue #38. Reading the version inside the write transaction instead
  protects nothing: it is the same read, so it always matches.
- **Why rejected here, not in general:** it is the right answer, in the Stage that
  owns the surface where the token can travel. Escalated to 3.4.

### Alternative B — `SELECT … FOR UPDATE` spanning the use case's read and write
- **Description:** hold the row lock from the use case's `find_by_id` until its
  `update`.
- **Pros:** genuinely prevents lost update, with no contract change to the
  entity.
- **Cons:** the two calls are separate transactions by construction (one
  transaction per public method, no Unit of Work port). Making the lock span them
  requires introducing a Unit of Work / session-scoped transaction — a new
  contract with no consumer, which concept 2.3 §7 Decision 6 explicitly declined
  to invent. It would also hold a write lock across application think-time and,
  at the HTTP boundary of 3.4, across a network round trip.
- **Why rejected:** it trades a rare silent overwrite for a common held lock, and
  requires inventing the abstraction the project deliberately postponed.

### Alternative C — `SERIALIZABLE` isolation on the staff repositories
- **Description:** raise the isolation level so conflicting read-modify-write
  pairs abort.
- **Pros:** correct without changing any signature.
- **Cons:** it does nothing here for the same reason as A: the read happens in a
  different, already-committed transaction, so there is no conflict for the
  serialisable checker to detect. It would also introduce retry-on-40001 handling
  across every write path, for a guarantee it does not actually provide in this
  shape.
- **Why rejected:** it looks like a solution and is not one.

### Alternative D — Do nothing and say nothing
- **Description:** implement the adapters and leave concurrency unmentioned.
- **Pros:** less writing.
- **Cons:** the finding was escalated *to this Stage*; closing it silently would
  leave "we have transactions, so we're fine" as the reader's default conclusion,
  which is false for lost update.
- **Why rejected:** the honest limit is the deliverable here, not the absence of
  the feature.

## Consequences

### Positive
- No partially written aggregate is committed, no torn aggregate is read, and no
  guard can be bypassed by interleaving.
- The distinction between the two hazards is written down, so Stage 3.4 inherits
  a precise problem instead of a vague one.
- The port signature published by Stage 3.2 survives untouched.

### Negative
- Two managers editing the same employee record at the same time still produce a
  silent overwrite of the earlier change.
- `FOR UPDATE` holds a row lock for the duration of the write transaction; it is
  short (a handful of statements, no network wait), but it exists.
- A genuine conflict — one actor updating an employee's function set while another
  deletes exactly that function — can still deadlock, and `40P01` rises as an
  `OperationalError` that the integrity translator never sees.
- `REPEATABLE READ` on the read paths means a read can, in principle, fail with a
  serialisation error under extreme contention; at v1 volumes this is theoretical,
  and it is the same escalated `40001` class.

### Neutral / trade-offs accepted
- The version column will cost a migration in Stage 3.4 rather than being
  speculatively added now. That is cheaper than adding a column nothing reads and
  that would appear, unexplained, in every rehydration.

## Implementation notes

- The `[finding]` for Stage 3.4 must state both halves: the `version` column plus
  the `ETag`/`If-Match` surface. A version column without a transport is dead
  weight, and a transport without the column cannot be enforced.
- An integration test should demonstrate the atomicity that *is* guaranteed — a
  failed write leaves the previously stored aggregate byte-identical, including
  child rows; and a read interleaved with a committing write returns a consistent
  aggregate.
- The `FOR UPDATE` needs a **conduct** assertion, not a result assertion: two
  connections, where the second `update` of the same record blocks until the first
  commits. The final state alone does not distinguish a row lock from its absence.

## References

- Related ADRs: [2.2.0004](./2_2_0004-synchronous-port-signatures.md),
  [3.2.0004](./3_2_0004-granular-use-cases-over-partial-update.md),
  [3.3.0004](./3_3_0004-per-operation-integrity-error-translation.md)
- Finding: `docs/stages/3.2-staff-application/concept.md` §5 rule 17 and §10
- Transactional precedent: `docs/stages/2.3-identity-persistence/concept.md` §7 Decision 6

## Notas datadas

**2026-11-23 — a §Decision (c) passou a valer também para as leituras de função (issue #225).**
Desde a Stage 3.11 a `JobFunction` é remontada de duas tabelas — a flag
`enabled_in_all_units` em `job_functions` e os vínculos de `job_function_units` —, mas as
leituras de `PostgresJobFunctionRepository` seguiam em `READ COMMITTED`: uma alteração de
"conjunto" para "todas" comitando entre os dois statements fazia a leitura levantar
`InvalidUnitEnablementError` (422). As cinco leituras (`find_by_id`, `find_by_name`,
`find_all_by_ids`, `list_by_tenant`, `list_by_unit`) rodam agora sob `REPEATABLE READ`, com o
mesmo `_in_single_snapshot` do repositório de funcionário, e numa listagem todas as funções
vêm do mesmo instante (lei "Leitura coerente" no port). Ficam em `READ COMMITTED`, de
propósito, a remontagem de `update_enablement` — sob o lock da linha, que precisa reler o que
a alteração anterior comitou (ADR 0.0.0010) — e o lookup de `delete`, que deixou de remontar a
habilitação e só confere a existência. Uma correção ao texto de §Consequences → Negative: o
erro de serialização ali previsto "in principle" para as leituras não ocorre em leitura pura —
"read-only transactions will never have serialization conflicts" (PostgreSQL 16, §13.2.2);
só a transação que escreve ou trava linha o sofre. Provas: os testes `test_issue_225_*` de
`test_staff_conduct.py`, com duas conexões. Nota *append-only*; o corpo acima não foi editado.

**2026-11-23 — o lookup de `delete` de função volta a remontar a habilitação, sob lock (issue
#207).** A nota de 2026-11-23 (issue #225) deixa em `READ COMMITTED` o lookup de `delete`, "que
deixou de remontar a habilitação". Pelo [ADR 0.0.0023](./0_0_0023-rename-and-delete-job-function-need-reach-over-its-units.md), renomear e apagar passaram a ser escritas condicionais
à habilitação lida, como `update_enablement`: o lookup de `delete` é `SELECT … FOR UPDATE` e
remonta a habilitação para compará-la, e o de `update` (renomear) também é `SELECT … FOR UPDATE`
— `name` está num índice único, e o `UPDATE` do nome já tomava esse lock. Sob o lock
da linha a remontagem em `READ COMMITTED` é coerente pelo mesmo argumento de `update_enablement`
(todo escritor dos vínculos toma a linha-pai antes). Provas: os testes `test_issue_207_*` de
`test_staff_conduct.py`. Nota *append-only*; o corpo acima não foi editado.

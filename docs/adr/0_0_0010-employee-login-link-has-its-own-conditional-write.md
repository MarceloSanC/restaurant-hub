---
title: ADR 0.0.0010 — The employee login link has its own conditional write on the staff port, and the aggregate update no longer writes it
description: Architecture Decision Record
when-use: Reference before writing `employees.user_id`, before changing `EmployeeRepository.update` or `link_login`, before implementing "link an existing login" or "unlink", or when a staff use case needs to write one column without carrying the whole aggregate
keywords: [adr, user_id, employee, login-link, lost-update, conditional-write, for-update, staff, port, issue-68]
status: accepted
created_at: 2026-11-01
updated_at: 2026-11-03
adr_id: "0.0.0010"
decision: '`EmployeeRepository` gains `link_login(tenant_id, unit_id, employee_id, user_id)` — the only writer of `employees.user_id` after the record exists — which locks the row, re-runs the domain guards of `Employee.link_login` on the stored record and writes only `user_id`; `update` ignores the entity''s `user_id` and keeps the stored one; `CreateLoginForEmployeeUseCase` links through `link_login`'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0010 — The employee login link has its own conditional write

> ⚠️ **Errata (2026-11-03):** §Decision 3 and §Status — the adapter constants were renamed to English in issue #135 (pure rename, no behaviour change): `_COLUNAS_COM_ESCRITA_PROPRIA` is now `_COLUMNS_WITH_OWN_WRITE` and `_COLUNAS_IMUTAVEIS` is now `_IMMUTABLE_COLUMNS`, both in `staff/adapters/out/postgres/employee_repository.py`. The quoted sentence of ADR 3.5.0004 keeps the old name because it is a quotation. Pointer only; no decision content changes — ver issue #135

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #68 (standalone issue, hence the `0.0` prefix — CONVENTIONS §1, "ADR global":
decisions taken outside the scope of a specific Stage — and, as every global ADR,
`bounded_context: transversal` (CONVENTIONS §2). The decision is about the staff bounded context;
a search for staff ADRs finds it through ADR 3.5.0004's `## Supersessão parcial`.)

**Partially supersedes [ADR 3.5.0004](./3_5_0004-user-id-as-nullable-opaque-column.md) §4**, the
sentence *"The column is **not** in `_COLUNAS_IMUTAVEIS`: it is set by `update`"*, and the first
bullet of its `### Negative` (*"'Set once' holds on the in-memory entity, not on the row"*). The
rest of ADR 3.5.0004 — nullable opaque column, no FK, no UNIQUE, no index, never copied — stands.

## Context

- **The window.** Concept 3.5 §6.4 declared "last write wins on `user_id`": `update` writes the
  whole aggregate (ADR 3.3.0006), so an R07 (rename) that read the record **before** a concurrent
  R17 (create login) and writes **after** it erases the link in silence, and two concurrent R17
  with different e-mails both succeed and the last one wins. In Stage 3.3 the consequence of last
  write wins was a lost, redoable edit (ADR 3.3.0006). Here it is an orphan account in identity
  with its e-mail taken.
- **The fix was named, and routed here.** Concept 3.5 §10 and ADR 3.5.0004 `### Negative` named
  the cheap fix — "a dedicated conditional-update port method" — and deferred it to the Stage of
  #46. ADR 2.6.0002 §2 ruled that the window is lost update **inside staff**, not identity
  atomicity, that the identity unit of work cannot reach staff (`bc-independence`), and escalated
  the dedicated conditional update on the staff port to its own issue: #68.
- **What already exists.** `PostgresEmployeeRepository.update` locks the row with
  `SELECT … FOR UPDATE` before its guards (module note 2), which serializes two writes of the same
  row but does not help a writer whose entity was read before the lock. The domain owns the link
  guards: `Employee.assert_can_link_login` refuses a linked record, then a terminated one (concept
  3.5 CA01), and `__post_init__` refuses an empty `user_id`.
- **Not the race of concept 3.8 D7.** D7 (two concurrent terminations of records that share a
  `user_id`) is about several records per login and is owned by the Stage that implements "link an
  existing login", with a lock per `user_id` (ADR 3.8.0001 Alt. H). #68 is about one record and its
  own row; it locks per employee row and does not close D7.

## Decision

1. **`EmployeeRepository.link_login(tenant_id, unit_id, employee_id, user_id) -> None`** — law
   `L-LINK`. Three-part address (ADR 3.4.0007). Order of checks: not found **at the address** ⇒
   `EmployeeNotFoundError`; already linked **on the stored record** ⇒
   `EmployeeAlreadyHasLoginError`; terminated **on the stored record** ⇒
   `TerminatedEmployeeLoginError`. On any error nothing is written; on success only `user_id`
   changes.
2. **The guards are the domain's, run on the stored record.** The fake applies
   `Employee.link_login` to the stored entity. The Postgres adapter locks the row
   (`SELECT … FOR UPDATE`, three-part address), rebuilds the aggregate under the lock, applies
   `Employee.link_login`, and runs `UPDATE employees SET user_id = :u`. Check and write are one
   transaction, so a second linker that waits on the lock re-reads the committed link and is
   refused. The aggregate is rebuilt at the default `READ COMMITTED`, not under the
   `REPEATABLE READ` that ADR 3.3.0006 §(c) asks of aggregate reads: the parent row is held by
   `FOR UPDATE`, and every writer of the child tables (`update`, `delete`) takes that same lock
   first, so no write can commit between the four statements. `REPEATABLE READ` with
   `FOR UPDATE` would turn the wait of a second linker into a serialization error (`40001`)
   instead of a re-read.
3. **`update` no longer writes `user_id`.** The adapter keeps it out of the `SET`
   (`_COLUNAS_COM_ESCRITA_PROPRIA`, next to `_COLUNAS_IMUTAVEIS`); the fake stores the received
   entity with the stored `user_id`. A stale entity cannot erase a link, and once the record
   exists no write path other than `link_login` can set one. `add` still inserts the entity's
   `user_id` as it comes (the column is part of the row); no use case creates a linked record —
   `create_employee` and the copy never name the field (ADR 3.5.0004 §5) — and the guards of a link
   on an existing record are what this ADR is about. Last write wins (ADR 3.3.0006) still holds for
   every other field.
4. **`CreateLoginForEmployeeUseCase` links through `link_login`.** Its order (concept 3.5 §5.4)
   is unchanged: domain guard on the read record, provision in identity, link, then deliver. The
   result is built from the record it read, with the new link.

## Alternatives considered

### Alternative A — Conditional `UPDATE … WHERE user_id IS NULL` with no lock
- **Description:** the shape the issue suggested: one `UPDATE` guarded in its `WHERE`, and on zero
  rows a second read to say which error applies.
- **Pros:** one statement on the happy path.
- **Cons:** the diagnosis read runs after the failed write, so a state that changes in between
  (a reactivation, a delete) is reported with the wrong error; the precedence and the empty-id
  check would be rewritten in SQL, a second source next to the domain's; and `active` would have to
  enter the `WHERE` too.
- **Why rejected:** [decision:C] rung 1 — the adapter's own `update` already decides under
  `FOR UPDATE` before writing (module note 2, CA6b); the same form keeps one place for the guards.
  The `WHERE user_id IS NULL` is redundant under the lock and was not added.

### Alternative B — `update` keeps writing `user_id`, but only when the stored one is `NULL`
- **Description:** `SET user_id = COALESCE(user_id, :u)`; no change to the use case.
- **Pros:** smallest diff; tests that seed a link through `update` keep working.
- **Cons:** two writers of the link — `update` and whatever closes the two-R17 race — so the
  concurrent R17 still has a path that does not go through the atomic check; and an `update`
  carrying a link for an unlinked record links it with no domain guard on the stored state
  (a terminated record would be linked).
- **Why rejected:** [decision:C] rung 4 — one writer per column is the form that "link an existing
  login" and "unlink" can extend (each gets its own method) without reopening `update`.

### Alternative C — Optimistic locking of the whole aggregate
- **Description:** a version column checked by every write.
- **Why rejected:** non-goal of the issue and of ADR 3.3.0006; it changes every staff write to
  close a window that is about one column.

### Alternative D — `link_login` returns the linked aggregate
- **Description:** the port returns the `Employee` it wrote, so the use case's result reflects the
  stored record (including a concurrent rename).
- **Why rejected:** [decision:C] rung 5 — the result before #68 was also built from the record the
  use case read; returning the aggregate widens the port for a display detail. Reversible.

## Consequences

### Positive
- A concurrent edit can no longer erase a link (pinned by the contract test
  `test_l_e2_update_com_entidade_lida_antes_do_vinculo_nao_o_apaga` and by the two-connection
  conduct test `test_issue_68_renomear_concorrente_nao_apaga_o_vinculo_gravado`).
- Two concurrent R17 no longer both succeed: the one that commits second gets `409`
  (`EmployeeAlreadyHasLoginError`) instead of a silent swap (conduct test
  `test_issue_68_dois_vinculos_concorrentes_o_segundo_e_recusado_e_nao_troca_o_primeiro`).
- A termination committed between R17's read and its link makes R17 answer `409`
  (`TerminatedEmployeeLoginError`) instead of linking a terminated record.

### Negative
- The losing R17 of a race, and an R17 that loses to a concurrent termination, leave the account
  they provisioned in identity without a record pointing to it — the orphan window that concept
  3.5 §6.4 already declares for a failing staff write after provisioning. What changes is that the
  client now gets a `409` for it instead of a `201` over a swapped link. The recovery path ("link
  an existing login") is still the finding of concept 3.5 §10.
- **The reverse order of the termination race is not closed.** An R13 that read the record before
  an R17 linked it, and writes `active = False` after, now keeps the link (before #68 it erased
  it): the record ends terminated **and** linked, R17 answered `201` with a setup link, and R13
  revoked nothing because it read no `user_id`. The account is pending at that point, so there is
  no session to revoke, and what a login reaches goes through an active record (ADR 3.5.0003,
  ADR 4.1.0006), so the state grants nothing today. It contradicts "a terminated record does not
  receive a login" (concept 3.5 §5.5) as a stored state, and is declared, not fixed: closing it
  means R13 re-checking the link under the row lock, which reopens the partial-success shape ADR
  3.5.0003 §2 avoids. Escalated as a finding on issue #68.
- **Delete has the same check-then-act shape.** `DeleteEmployeeUseCase` refuses a linked record by
  reading the entity, and the adapter's `DELETE` does not look at the stored `user_id`; an R17 that
  links between the read and the delete leaves the record deleted and the account orphaned.
  Outside this issue (it is about the remove path, not the edit path); escalated as a finding on
  issue #68.
- `update` silently ignores the `user_id` of the entity it receives. That is the point, and it is
  in the port's docstring; a caller that wants to link must call `link_login`.

### Neutral / trade-offs accepted
- `link_login` reads the four tables of the aggregate under the lock to reuse the domain guards —
  three reads more than a column check, on a rare operation.

## References
- Issue #68; `docs/stages/3.5-employee-login-link/concept.md` §6.4, §9, §10;
  `docs/stages/2.6-identity-unit-of-work/technical.md` §7 (finding that opened #68)
- [ADR 3.5.0004](./3_5_0004-user-id-as-nullable-opaque-column.md) §2, §4, `### Negative`
- [ADR 2.6.0002](./2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md) §2
- [ADR 3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md)
- [ADR 3.4.0007](./3_4_0007-unit-enters-the-employee-address.md)
- [ADR 3.8.0001](./3_8_0001-termination-revokes-only-access-the-record-grants.md) Alt. H;
  `docs/stages/3.8-termination-access-scope/concept.md` D7
- `src/restaurant_hub/features/staff/application/ports/out/employee_repository.py` (`update`,
  `link_login`)

## Supersessão parcial

**2026-11-02 — o quarto item de `### Negative` (*"Delete has the same check-then-act shape …
escalated as a finding on issue #68"*) foi superado por
[ADR 0.0.0013](./0_0_0013-employee-delete-refuses-a-stored-login-link.md) (issue #108).**
`EmployeeRepository.delete` ganhou a lei `L-DEL-LINK`: o registro vinculado **no gravado** é
recusado com `EmployeeHasLoginError`, e o adapter Postgres prende a linha com `SELECT … FOR UPDATE`
antes da guarda e do `DELETE`. Um R17 que vincula entre a leitura do R15 e a remoção não deixa mais
conta órfã. O resto deste ADR continua valendo. Nota *append-only*; o corpo acima não foi editado.

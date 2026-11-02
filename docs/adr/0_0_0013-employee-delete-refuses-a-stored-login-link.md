---
title: ADR 0.0.0013 — Definitive removal of an employee record refuses a login link on the stored record, under the row lock
description: Architecture Decision Record
when-use: Reference before changing `EmployeeRepository.delete` or `DeleteEmployeeUseCase`, before implementing "unlink login", or when a staff write must re-check on the stored record a guard that a use case already ran on the record it read
keywords: [adr, delete, employee, user_id, login-link, orphan-account, for-update, check-then-act, staff, port, issue-108]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
adr_id: "0.0.0013"
decision: '`EmployeeRepository.delete` gains law `L-DEL-LINK` — a record linked **on the stored row** is refused with `EmployeeHasLoginError` and nothing is removed, checked after the address and before references; the Postgres adapter locks the row (`SELECT user_id … FOR UPDATE`, three-part address) before the guard and the `DELETE`, in one transaction; `DeleteEmployeeUseCase` keeps its refusal on the record it read (ADR 3.5.0003 §1b) and lets the port''s error propagate'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0013 — Definitive removal refuses a stored login link

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #108 (standalone issue, hence the `0.0` prefix — CONVENTIONS §1, "ADR global",
and `bounded_context: transversal` as every global ADR, CONVENTIONS §2). The decision is about the
staff bounded context and extends [ADR 0.0.0010](./0_0_0010-employee-login-link-has-its-own-conditional-write.md)
to the remove path. It closes the fourth item of ADR 0.0.0010 `### Negative` (*"Delete has the
same check-then-act shape"*), recorded there in a `## Supersessão parcial` note.

It does **not** supersede [ADR 3.5.0003](./3_5_0003-termination-revokes-sessions-account-remains.md)
§1b: the use case still refuses a linked record after `find_by_id` and before calling `delete`.
This ADR adds a second refusal on the stored row, for the window §1b cannot see.

## Context

- **The rule.** "A record with a login is not removed — terminate it first" (ADR 3.5.0003 §1b;
  concept 3.5 §5.6). Deleting a linked record leaves an account in identity that no record points
  to: e-mail taken globally, membership alive, unrecoverable until "link an existing login"
  exists.
- **The window.** `DeleteEmployeeUseCase` decided on the entity it read
  (`if employee.user_id is not None: raise EmployeeHasLoginError`), and
  `PostgresEmployeeRepository.delete` ran `DELETE … WHERE id, tenant, unit` without looking at the
  stored `user_id`. An R17 (create login) that linked between the `find_by_id` and the `delete`
  had already answered `201` with a setup link; the record was then deleted and the account left
  orphan. Silent: nothing reports it.
- **Same class as #68.** ADR 0.0.0010 closed the edit path of the same check-then-act race by
  giving the link its own conditional write (`L-LINK`) under `SELECT … FOR UPDATE`. It named this
  remove path in `### Negative` and escalated it as a finding; the audit of PR #103 confirmed it
  and opened #108.
- **What the lock already covers.** `link_login` and `update` take `FOR UPDATE` on the employee
  row before their guards (ADR 0.0.0010 §2; adapter module note 2). Before #108, `delete` took the
  same row lock only through the `DELETE` itself, after any check.

## Decision

1. **Law `L-DEL-LINK` on `EmployeeRepository.delete`.** Order of checks: not found **at the
   address** `(tenant_id, unit_id, id)` ⇒ `EmployeeNotFoundError`; linked **on the stored record**
   ⇒ `EmployeeHasLoginError`; referenced by another aggregate ⇒ `EmployeeInUseError` (L-E5, still
   no producer in v1). On any error nothing is removed. It holds for an active **and** a
   terminated linked record, as §1b does.
2. **Postgres: guard under the row lock.** The adapter runs `SELECT user_id FROM employees WHERE
   id, tenant_id, unit_id FOR UPDATE`, then the guard, then `DELETE`, in one transaction at the
   default `READ COMMITTED`. An R17 that commits before the lock is seen (the `FOR UPDATE` waits
   for its commit and returns the updated row); an R17 that arrives after waits on the lock and
   finds the record gone. The `DELETE`'s `rowcount` is no longer the existence check: under the
   lock the row cannot disappear between lookup and write.
3. **Fake: the same order on the stored entity.** `InMemoryEmployeeRepository.delete` resolves the
   address, then refuses a stored `user_id`, then removes. The contract suite runs one body against
   both.
4. **The use case keeps its own refusal.** `DeleteEmployeeUseCase` still raises
   `EmployeeHasLoginError` from the record it read, with no `delete` call (ADR 3.5.0003
   implementation notes, CA11). The port's `EmployeeHasLoginError` propagates unchanged and maps
   to the same `409`.

## Alternatives considered

### Alternative A — Conditional `DELETE … WHERE user_id IS NULL`, then discriminate by a `SELECT`
- **Description:** the issue's first suggestion: a `DELETE` that only matches an unlinked row; on
  `rowcount == 0`, a second `SELECT` tells "not found" from "linked".
- **Pros:** one statement on the happy path; Postgres re-evaluates the `WHERE` on the row a
  concurrent R17 committed, so the race is closed too.
- **Cons:** the address check and the link check become an inference from a zero `rowcount`
  plus a second read outside the predicate that decided; the order of checks is implicit.
- **Why rejected:** [decision:C] rung 4 (consistency with the established form) — `link_login`
  and `update` both lock the row first and run their guards on what the lock returned (ADR
  0.0.0010 §2); one form for every guarded write on the employee row is what the next one
  ("unlink login") extends. Reversible inside the adapter, with the contract unchanged.

### Alternative B — Move the refusal from the use case to the port only
- **Description:** drop the use case's check; the port alone refuses.
- **Cons:** the use case would call `delete` on a record it already knows is linked, contrary to
  ADR 3.5.0003 §1b and its CA11 ("R15 on a linked record produces **no** `delete` entry").
- **Why rejected:** [decision:E] ADR 3.5.0003 §1b is in force (its `## Supersessão parcial`
  keeps §1b) and is higher than this issue in the source hierarchy.

### Alternative C — Re-check in the use case right before `delete`
- **Description:** a second `find_by_id` before `delete`.
- **Why rejected:** [decision:E] still two operations; the window shrinks and stays open.

## Consequences

### Positive
- An R17 that links between R15's read and its removal no longer leaves an orphan account: R15
  answers `409` and the record and the link stay (contract `test_l_del_link_*`; conduct tests
  `test_issue_108_r17_entre_a_leitura_e_o_delete_recusa_a_remocao`,
  `test_issue_108_delete_bloqueia_no_lookup_e_nao_depois`,
  `test_issue_108_delete_que_espera_um_vinculo_em_curso_o_rele_e_recusa`).
- Every guarded write on the employee row (`update`, `link_login`, `delete`) now decides under
  the same row lock.

### Negative
- **The reverse order still provisions an account.** An R17 whose domain guard ran on a record
  that an R15 then deletes provisions the account in identity and gets `EmployeeNotFoundError`
  (`404`) from `link_login`. The account is left without a record — the orphan window concept
  3.5 §6.4 and ADR 0.0.0010 `### Negative` already declare for a failing staff write after
  provisioning. What changed is that the client is told (`404`), instead of the record vanishing
  after a `201`. Recovery of such accounts is the scope of issue #107.
- `delete` reads one column more than before (the lookup), on a rare operation.

### Neutral / trade-offs accepted
- The refusal "a linked record is not removed" now lives in two places (use case on the read
  record, port on the stored one). Both raise the same error; the port's is the one that decides
  under concurrency.

## References
- Issue #108; issue #68 and PR #103 (audit verdict that confirmed the finding)
- [ADR 0.0.0010](./0_0_0010-employee-login-link-has-its-own-conditional-write.md) §2,
  `### Negative`
- [ADR 3.5.0003](./3_5_0003-termination-revokes-sessions-account-remains.md) §1b, implementation
  notes (CA11)
- [ADR 3.4.0007](./3_4_0007-unit-enters-the-employee-address.md) §4 (address before any other
  guard)
- [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md) (authorization
  stays the use case's first instruction; unchanged)
- `src/restaurant_hub/features/staff/application/ports/out/employee_repository.py` (`delete`)

---
title: ADR 3.10.0001 — Linking an existing account, swapping and unlinking are three staff operations, each written by a conditional port method on the link state read; termination writes the same way; every end of an active link goes through one rule; one login per unit
description: Architecture Decision Record
when-use: Reference before adding or changing any operation that writes `employees.user_id` or `employees.active`, before changing `deactivate_employee`, before touching `_login_link.py` or rule 10 of `check_layout.py`, or when revisiting the concurrent end-of-link race of ADR 3.8.0001
keywords: [adr, login-link, unlink, relink, conditional-write, termination, revoke-sessions, single-point, one-per-unit, staff, race]
status: accepted
created_at: 2026-11-22
updated_at: 2026-11-22
adr_id: 3.10.0001
decision: 'Staff gains three login-link operations — link an existing account (R18, through the existing L-LINK), swap the linked login (R19) and unlink (R20). `EmployeeRepository` gains `unlink_login`, `relink_login` and `deactivate`, each locking the row, re-running a domain guard on the stored record against the link state the use case read (login, and active state where it decides revocation), and writing one column; termination (R13) writes through `deactivate`, so a link or rehire that lands between its read and its write makes it answer 409. The ADR 3.8.0001 rule moves to one helper, `_login_link.end_active_link`, called before the write by R13, R19 and R20; nothing else calls the revocation, and rule 10 of check_layout counts the helper as the cross-BC write. R18 and R19 refuse an account already linked to another record of the same unit (workforce §3.1, one per unit); only two concurrent links of one account in one unit remain as a declared residual.'
context_stage: 3.10-login-link-management
bounded_context: staff
---

# ADR 3.10.0001 — Login-link transitions by conditional write, and one end-of-link rule

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — Stage 3.10 concept §7 D1, D5–D8 (sponsor-delegated product forks, 2026-11-22;
revised after Checkpoint A, concept §13).

**Partially supersedes** (each gets an append-only dated note in this Stage):

- **ADR 3.5.0004 §2** — "set once", set only through `Employee.link_login`: the link now has
  three conditional writers on an existing record (`link_login`, `relink_login`,
  `unlink_login`).
- **ADR 0.0.0010 Decision 3** and its `decision` field — `link_login` as "the only writer of
  `employees.user_id` after the record exists" — for the same reason; and its `### Negative`
  bullet *"The reverse order of the termination race is not closed"*, closed by Decision 4.
- **ADR 3.8.0001 `### Negative`**, the *"Owner: the Stage that implements 'link an existing
  login'"* sentence: this Stage closes the path that makes the race producible (Decision 6)
  and hands the residual lock to its own issue.
- **ADR 2.6.0002**, whose `decision` lists two staff crossings: R19 and R20 join the
  allowlist of rule 10 (Decision 5).

It **implements ADR 3.8.0001 Decision 5**.

## Context

- The link has one conditional writer, `link_login` (ADR 0.0.0010): lock the row, re-run the
  domain guards on the stored record, write `user_id` only. `update` ignores `user_id` but
  still writes `active` (last write wins, ADR 3.3.0006).
- Workforce §3.8 said there is no unlink and no link of an existing login in v1; concept 3.5
  §10 and §6.4 named both as the recovery path for orphan accounts, mistyped e-mails and
  records linked by mistake (which R15 refuses, ADR 0.0.0013).
- ADR 3.8.0001 Decision 5: the termination rule belongs to "a record's active link ends".
- ADR 0.0.0010 `### Negative`: an R13 that read an unlinked record and writes after a
  concurrent link leaves it terminated **and** linked, revoking nothing.
- ADR 3.8.0001 `### Negative`: two concurrent terminations of two same-unit records of one
  login may each read the other as active; owner, the Stage that implements "link an existing
  login", with a lock per `user_id`.
- Workforce §3.1 and ADR 3.1.0001 iii: one person may have several records, **one per unit**.
- Rule 10 of `check_layout.py` (ADR 2.6.0002 §5) sees only writes made through
  `self.<attribute>.<method>`.

## Decision

**1. Three operations, swap included.** R18 links an existing account to a record with no
link, R19 replaces the linked login by another existing account, R20 removes the link. R19
checks the new account before it ends the old link and writes the swap once.

**2. One conditional port method per transition, guarded on the state read.**

```
unlink_login(tenant, unit, employee, *, expected_user_id, expected_active)  # L-UNLINK
relink_login(tenant, unit, employee, *, expected_user_id, user_id)          # L-RELINK
deactivate(tenant, unit, employee, *, expected_user_id, expected_active)    # L-DEACT
```

Not found at the three-part address ⇒ `EmployeeNotFoundError`; then the domain guard runs on
the stored record — `Employee.unlink_login`, `Employee.relink_login`,
`Employee.deactivate_as_read` — and only then one column is written. A stored login that
differs from the expected one, or a record read terminated and stored active (rehired in
between), raises `EmployeeLoginChangedError` (409) and writes nothing. A record read active
and stored terminated does not refuse: whoever terminated it in between went through the
rule, so two concurrent R13 on one record both answer 200. `relink_login` needs no expected active state: the domain refuses a terminated
record. The Postgres adapter takes `SELECT … FOR UPDATE` before the guard, as `link_login`
does. R18 keeps `link_login` (L-LINK).

**3. The expected state is the one the use case read.** The client does not send it. The
intent of R19 and R20 holds over whatever link is there; the expected state protects the
revocation decision, which depends on the login read and on the record being active (a rehire
between read and write would otherwise end an **active** link without the rule).

**4. Termination writes through `deactivate` with the state it read.** A link created or
removed, or a rehire, between R13's read and its write makes R13 answer 409 with nothing
written; the retry applies the rule to the new state. What may already be persisted is a
revocation (the safe side, as with a failing write today), never the "terminated with a
live session" ADR 3.5.0003 §2 avoids. Termination now writes `active` only.

**5. One end-of-link rule.** `features/staff/application/use_cases/_login_link.py` ›
`end_active_link(employees, gateway, employee)` holds ADR 3.8.0001 Decisions 1–2: revoke iff
the record is active, linked, no other active record of the same unit carries the login, and
the login is an `employee` account. R13, R19 (with the **old** login) and R20 call it with the
record read, before the write. An AST sweep pins that `revoke_login_sessions` and
`is_employee_login` are called only there, and that every use case calling `deactivate`,
`relink_login` or `unlink_login` on its `EmployeeRepository` attribute calls
`end_active_link` first. Rule 10 of `check_layout.py` gets a named table of helpers that write
outside the bounded context and counts a call to `end_active_link` as that write;
`RelinkLoginUseCase` and `UnlinkLoginUseCase` join `MULTI_WRITE_ALLOWLIST` (revocation in
identity, then the write in staff — ADR 2.6.0002 §2).

**6. One login per unit; the race shrinks to a residual.** R18 and R19 refuse
(`LoginAlreadyLinkedInUnitError`, 409) an account already linked to another record of the
same unit, active or terminated. This removes the API path to two same-unit records of one
login, on which the ADR 3.8.0001 race depends. The check reads the unit before writing
another row, so two **concurrent** links of the same account into two records of one unit can
still both pass; only then can the termination race recur. Closing that residual needs a
staff transaction holding the read and the write (a lock per `user_id`), and staff has no
unit of work (ADR 2.6.0002 §2). It goes to its own issue.

## Alternatives considered

### Alternative A — Swap as unlink + link by the client
- **Cons:** a failing second call leaves the record unlinked; the old link ends before the new
  account is checked.
- **Why rejected:** sponsor-delegated product fork (concept D1).

### Alternative B — `UPDATE … WHERE user_id = :expected` without a lock
- **Why rejected:** ADR 0.0.0010 Alternative A — the diagnosis read after a failed write
  reports the wrong error, and the guards would be rewritten in SQL.

### Alternative C — One method `replace_login(expected, new | None)`
- **Why rejected:** a mode flag in a port signature; ADR 0.0.0010 Alternative B › "each gets
  its own method".

### Alternative D — The client sends the expected `user_id`
- **Cons:** reintroduces `user_id` into staff requests, which the schema sweep forbids; R19
  and R20 intents do not depend on which login is there.
- **Why rejected:** `[decision:C]` rung 1 (concept D5).

### Alternative E — Keep the reverse-order termination race declared
- **Why rejected:** concept 3.5 §5.5 ("a terminated record does not receive a login") is a
  rule about the stored state, and the conditional write enforces it without a partial
  success.

### Alternative F — A partial unique index `(tenant_id, unit_id, user_id)`
- **Pros:** makes one-per-unit atomic and closes the race by construction.
- **Cons:** a migration; the Stage 3.8 suites arrange ADR 3.8.0001 case (a) inside one unit
  with a direct `UPDATE` and would have to be rewritten; the same-unit condition of ADR
  3.8.0001 becomes dead.
- **Why not now:** the application check closes the API path; the index stays the candidate
  for the residual. `[decision:C]` rung 4.

### Alternative G — Lock per `user_id`
- **Why rejected now:** needs one staff transaction across the unit read, the identity call
  and the write; staff has no unit of work.

### Alternative H — Give `active` its own write (as `user_id`)
- **Pros:** closes the stale `update` that rewrites the state.
- **Cons:** changes `update`'s law for every edit and the rehire path.
- **Why rejected now:** the defect class predates this Stage; declared, with a finding.

## Consequences

### Positive
- Every transition of the link, and termination, is conditional on the stored state; the
  #68/#108 defect class stays closed for the new operations.
- The ADR 3.8.0001 rule has one implementation, pinned by an AST sweep and by rule 10.
- A concurrent link no longer leaves a terminated linked record through R13.

### Negative
- R13 may now answer 409 (`EmployeeLoginChangedError`) under a concurrent change; the client
  retries.
- R13, R19 and R20 revoke before writing; a 409 or a failed write afterwards leaves the
  revocation persisted and costs the person a new login (same trade as ADR 3.5.0003 §2).
- Two concurrent links of one account into one unit remain possible (Decision 6).
- An edit that read the record before a rehire still writes the old `active` through `update`
  (ADR 3.3.0006); with a link in between, the record may end terminated and linked.

### Neutral / trade-offs accepted
- `EmployeeRepository` gains three methods, each with fake, adapter, contract and conduct
  test.

## Implementation notes
- Errors: `EmployeeHasNoLoginError`, `EmployeeLoginChangedError` (domain, 409);
  `LoginAlreadyLinkedInUnitError` (`StaffError` in `application/errors.py`, like
  `LoginEmailAlreadyInUseError`; 409).
- Conduct tests with two connections, one per law (concept CA10).

## References
- Stage 3.10 concept §5 R1–R3, R10, §6.1, §7 D1, D5–D8, §13; issue #218; issue #107
  (comment of 2026-11-02)
- ADR 0.0.0010, ADR 0.0.0013, ADR 2.6.0002, ADR 3.1.0001, ADR 3.3.0006, ADR 3.5.0003,
  ADR 3.5.0004, ADR 3.8.0001
- `docs/domain/staff/workforce.md` §3.1, §3.8; concept 3.5 §5.5, §6.4, §10

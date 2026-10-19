---
title: ADR 2.6.0002 — The unit of work covers identity use cases that write more than once; no transaction spans bounded contexts, side effects run after commit, and a layout gate keeps every multiple-write use case inside a unit or in a counted allowlist
description: Architecture Decision Record
when-use: Reference before adding a second write to any use case, before making a staff use case transactional with identity, before sending an e-mail or calling another BC from inside a unit, or when check_layout rule 10 rejects a use case
keywords: [adr, unit-of-work, scope, bounded-context, cross-bc, side-effect, email, outbox, gate, check-layout, allowlist, staff, identity]
status: accepted
created_at: 2026-10-19
updated_at: 2026-10-19
adr_id: 2.6.0002
decision: the five identity use cases that write more than once (set_password_with_token, invite_user, provision_account, request_password_reset, refresh_session's rotation) run their writes inside the identity unit; staff gets no unit because none of its use cases writes twice inside staff, and its two cross-BC crossings (create_login_for_employee, deactivate_employee) keep their ordered, declared windows because a transaction across bounded contexts is rejected by ADR 4.1.0006; e-mail is sent after commit; SessionRepository.revoke reports whether it revoked so that a concurrent rotation loser is treated as reuse; check_layout rule 10 requires every use case with two or more writes to keep all of them inside exactly one unit (only write-and-refuse tolerated outside) unless it is in a counted allowlist citing this ADR
context_stage: 2.6-identity-unit-of-work
bounded_context: identity
---

# ADR 2.6.0002 — Unit of work scope: identity only, no cross-BC transaction, side effects after commit, and a gate

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Issue #46 asks that "use cases that write to more than one repository operate
inside a unit". Reading every use case (Stage 2.6 concept §3) gives three
populations:

| Population | Use cases | Writes |
|---|---|---|
| identity, 2+ writes | `set_password_with_token` (4), `invite_user` (2), `provision_account` (2), `request_password_reset` (2), `refresh_session` rotation (2) | all inside identity |
| staff, cross-BC | `create_login_for_employee` (identity `users.add`+`tokens.add` via facade, then `employees.update`), `deactivate_employee` (identity `revoke_all_for_user` via facade, then `employees.update`) | one per BC |
| check-then-act, 1 write | `delete_job_function`, `create_employee`, `assign_job_functions`, `create_unit`, `create_user`, … | one |

Constraints already ratified:

- ADR 4.1.0006, Alternative A: a transaction spanning bounded contexts is
  rejected — "what Evans, Vernon and Grzybek say not to do", and it welds the BCs
  to one database, the objection ADR 3.3.0002 made to cross-BC foreign keys.
- ADR 3.5.0002 §4 and `invite_user`'s rule 13: the account and its link are
  persisted **before** the secret is delivered, and a delivery failure surfaces to
  the actor.
- Concept 3.5 §6.4 declared five windows of "two BCs written in one request
  without a Unit of Work" and pointed them at #46.
- Issue #46 names a "#45 allowlist gate for declared multi-repository writes" to
  update or remove. **That gate does not exist** in `scripts/` or `tests/` at
  `2c71615`: #45 closed without it.

## Decision

**1. Identity: the five use cases above put their writes in one unit.**
`refresh_session` only on the rotation path (`revoke` + `add`); its reuse path
revokes every session and then raises, and that revocation must **commit**, so it
stays outside the unit as a single write.

**1b. `SessionRepository.revoke` reports whether it revoked.** The port method
returns `bool` (`rowcount == 1` in Postgres), an additive change following the
precedent of `PasswordSetupTokenRepository.consume`. Inside the rotation unit,
`False` means a concurrent rotation already revoked that session: the use case
leaves the unit (rolling it back), revokes every session of the user outside it,
and raises `RefreshTokenReuseError`. Without this, the unit would *widen* a
pre-existing window — a replay that reads the session before the first rotation
commits waits on its row lock, revokes zero rows and gets a valid pair with no
alarm. [decision:C] rung 1 (the `consume` precedent) and rung 2 (fail-closed,
the reuse semantics of ADR 2.2.0001). Logout (`revoke_session`) keeps ignoring
the value.

**2. Staff: no unit, and no transaction across BCs.** No staff use case writes
twice inside staff, so a staff unit would make nothing atomic. The two crossings
keep their order and their windows, now narrower: the identity half of
`create_login_for_employee` (`users.add` + `tokens.add`) becomes atomic through
`provision_account`, which closes the "orphan inside identity" window of concept
3.5 §6.4; the "orphan account in identity when `employees.update` fails" window
remains declared; its recovery path (link an existing login) does **not** exist
yet — concept 3.5 §10 names it as a finding for a later Stage. The last-write-wins
window on `Employee.user_id` (concept 3.5 §6.4/§10, which named "the Stage of
#46" for it) is lost update inside staff, not identity atomicity: this port cannot
reach staff, and the cheap fix 3.5 named (a dedicated conditional update on the
staff port) is escalated as a finding with its own issue. [decision:C] rung 1 — ADR 4.1.0006 and ADR 3.3.0002.

**3. Side effects run after commit.** `invite_user` and `request_password_reset`
send their e-mail after the unit closes. A rollback cannot unsend an e-mail; an
e-mail sent from inside a unit that later rolls back delivers a link to a token
that does not exist. Behaviour is therefore unchanged where it is observable:
`invite_user` still leaves the account created when sending fails (rule 13), and
`request_password_reset` still absorbs every failure, now with the unit inside its
`try` so that a rollback is absorbed too. [decision:C] rung 1 — ADR 3.5.0002 §4.

**4. Check-then-act with a single write is out of scope.** A `READ COMMITTED`
unit around a check and one write does not close the race; the schema backstops
(`RESTRICT`, unique indexes) do, and they are declared where they live
(ADR 3.3.0006, `delete_job_function`'s docstring).

**5. A gate replaces the one #46 assumed.** `scripts/check_layout.py` gains
rule 10. For every class in `features/*/application/use_cases/`, its write call
sites are collected — followed transitively through `self._helper()` calls — and
a write call site inside a loop (`for`, `while`, comprehension) counts as two. If
the class has two or more writes:

- **all** of them must be lexically inside a `with self.<attr>.transaction():`
  block whose attribute is annotated as `UnitOfWork` in the constructor;
- there must be **exactly one** such block (two consecutive units are two
  transactions);
- the only write tolerated outside is the **"write and refuse"** pattern: a write
  immediately followed by `raise` in the same statement block (the reuse path of
  `refresh_session`).

A write is a call on an attribute whose constructor annotation is a repository
port (`ports/out/*_repository.py`) to a method not starting with `find_`,
`exists_` or `list_`, or a call to a gateway method the script declares as a
write. Exceptions live in a **counted allowlist** with a reason citing this ADR,
in the same style as rule 6: a new entry fails until justified, an entry that no
longer matches anything fails too. It starts with the two staff crossings.

**Scope across bounded contexts.** The rule reads every BC's `use_cases/`. The
first scheduling use case that writes twice (Stage 4.4 plans "every schedule
mutation produces an audit entry") will have to choose: a unit port of its own,
moving this one to `shared/` (then measured, LAYOUT §4), or an allowlist entry —
the gate forces the choice instead of letting it pass silently.

**Known blind spots, declared:** a repository aliased to a local
(`r = self._tokens`), a repository handed to a module-level function, and
compositions outside `use_cases/` (the identity facade delegates to use cases,
which the rule does see; the staff gateway is an adapter). None exists today.

## Alternatives considered

### Alternative A — One unit spanning staff and identity
- **Description:** staff opens a unit; identity's use cases behind the facade join
  it, so `create_login_for_employee` becomes all-or-nothing.
- **Pros:** closes the last orphan-account window.
- **Cons:** contradicts ADR 4.1.0006 Alternative A and ADR 3.3.0002; makes the
  facade's behaviour depend on an ambient transaction of the caller; requires
  reentrance and a shared ambient connection across BCs.
- **Why rejected:** a ratified project decision. The window it would close
  stays open and declared, with a recovery path still to be built.

### Alternative B — A staff unit as well, for symmetry
- **Pros:** "every BC has one".
- **Cons:** no staff use case writes twice in staff; staff reads run under
  `REPEATABLE READ` (ADR 3.3.0006 §c), which a unit opened at the default level
  would silently drop for reads moved inside it. A port with no consumer.
- **Why rejected:** LAYOUT §4 — measured, not predicted.

### Alternative C — Send e-mail inside the unit
- **Pros:** an SMTP failure rolls the account back, so re-inviting works instead
  of answering 409.
- **Cons:** a commit failure after a successful send mails a dead link; the
  transaction stays open across a network call. Changes rule 13 of 2.5.
- **Why rejected:** the observable improvement belongs to an outbox, which is a
  separate decision (ADR 4.1.0006 already names it as an evolution).

### Alternative D — No gate; the docstrings are enough
- **Cons:** the next write added to a use case lands outside the unit with the
  suite green — the failure mode the project's memory records as "tests pin cases,
  not properties".
- **Why rejected:** #45's rationale: a gate written with the code prevents; one
  written later documents.

## Consequences

### Positive
- Every multiple-write path in identity is atomic, and moving a write out of the
  unit, splitting the unit in two, or adding a second write outside one fails
  `make check` (within the blind spots of §5).
- Staff production code, its isolation level and its ADRs stay untouched (its
  gateway contract fixture changes, and the allowlist names two staff use cases).

### Negative
- The orphan-account window of `create_login_for_employee` (identity committed,
  `employees.update` failed) stays open, as declared in concept 3.5 §6.4.
- The gate classifies writes by name. A repository port method that writes but
  starts with `find_`/`exists_`/`list_` would escape it; the naming is pinned by
  the ports' own docstrings and a test of the classifier.

### Neutral / trade-offs accepted
- `deactivate_employee` keeps revoking sessions before writing the termination
  (ADR 3.5.0003): a failure leaves sessions revoked and the record active — the
  fail-closed half.

## References

- Related ADRs: [2.6.0001](./2_6_0001-identity-unit-of-work-port-and-ambient-connection.md),
  [4.1.0006](./4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md),
  [3.3.0002](./3_3_0002-no-cross-bounded-context-foreign-keys.md),
  [3.5.0002](./3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md),
  [3.5.0003](./3_5_0003-termination-revokes-sessions-account-remains.md),
  [3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md)
- Concept 3.5 §6.4 and §10; concept 2.5 §5 rule 13
- Issue: #46; issue #45 (gates)

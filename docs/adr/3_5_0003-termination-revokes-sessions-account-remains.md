---
title: ADR 3.5.0003 — Terminating an employee revokes the sessions of the linked login through the gateway, before the record is written; deleting a linked record is refused; the account remains and `is_active` is deferred with an explicit trigger
description: Architecture Decision Record
when-use: Reference before changing what `deactivate_employee` or `delete_employee` does with a linked login, before adding `User.is_active` or an account-deactivation route, or when the first self-service permission for `employee` is about to be granted (the trigger recorded here)
keywords: [adr, termination, deactivate, delete, revoke-sessions, is_active, employee-login, identity-gateway, staff, identity]
status: accepted
created_at: 2026-09-12
updated_at: 2026-10-19
adr_id: 3.5.0003
decision: '`DeactivateEmployeeUseCase` (R13) gains the `IdentityGateway` and, when the record carries a `user_id`, calls `revoke_login_sessions` **before** writing `active=False`; `DeleteEmployeeUseCase` (R15) refuses a linked record (`EmployeeHasLoginError`, 409 — terminate first) and does not touch identity; the account is not deactivated (`User.is_active` does not exist and is not added), so the person can authenticate again and reaches nothing; `reactivate_employee` does nothing with identity; `is_active` is deferred with the trigger "before the first self-service permission of `employee`"'
context_stage: 3.5-employee-login-link
bounded_context: staff
---

# ADR 3.5.0003 — Termination revokes login sessions; the account remains

## Status

`accepted` — decided by the sponsor on 2026-09-12 (concept §13 Q3) for the
termination. Checkpoint A (blocker B1) showed that R15 on a linked record left
sessions alive; the sponsor decided on 2026-09-13 (concept §13 Q7) that R15
**refuses** a linked record rather than revoking and deleting.

## Context

Kickoff decision #4 says *"logout/termination cut access"*, and decision #13
(round 3) fixes the shape of the cut: *"the refresh right away, the access token
within 15 minutes"* (short access TTL, no per-request introspection). Stage 2.4
delivered logout and recorded, as a `[finding]` with this Stage as candidate,
that **termination has no route**: `SessionRepository.revoke_all_for_user` has
no production caller outside reuse detection and `SetPasswordWithTokenUseCase`,
`User` has no `is_active`, and identity has no operation that deactivates or
removes a user (the only write on `UserRepository` besides `add` is
`set_password_hash`, from 2.5).

Stage 3.5 is the first in which a staff record points to a login, so
`deactivate_employee` (R13 of Stage 3.6) and `delete_employee` (R15) are the
first places where "the person left" and "the person has a login" meet.

Forces:

- `employee` has an **empty** permission set (`Role.EMPLOYEE: frozenset()`):
  today a terminated person's login reaches **nothing** in staff — the risk of
  leaving the account alive is nil until Step 4 grants "see my schedule".
- Adding `User.is_active` means an identity migration, a change to `User`,
  `AuthenticateUserUseCase` refusing inactive users, and a use case/route —
  schema and entity deliverables in identity, beyond the application-only
  limit this Stage set for itself (concept §5.13).
- Revoking sessions is available today (`revoke_all_for_user`) and needs only
  a small identity use case behind the facade (ADR 3.5.0001).
- Two writes in two BCs happen in one request without a Unit of Work (#46);
  the **order** decides which partial failure the client can see.
- The sponsor's words: *"revoke sessions via the gateway; the user can still
  log in but no longer has access to the establishment's information, because
  access was cut — perhaps leaving only information about themselves (schedule,
  clock-in history) in the future; for now it only shows they no longer have
  access to the company/unit information."*

## Decision

**1. `DeactivateEmployeeUseCase` revokes the linked login's sessions.** It
receives the `IdentityGateway`; after `find_by_id` (404 as today), if
`employee.user_id is not None` it calls `revoke_login_sessions(user_id)`, then
writes `deactivate()`. Records without a login make **no** gateway call.

**1b. `DeleteEmployeeUseCase` refuses a linked record.** After `find_by_id`, if
`employee.user_id is not None` it raises `EmployeeHasLoginError` (409) before
`delete`, and it does **not** receive the gateway. Definitive removal exists
for *"the cadastre created by mistake"* (ADR 3.2.0006); a record that was
granted a login is not a mistake, deleting it would leave an account that no
record points to (e-mail taken globally, membership alive — unrecoverable
until "link/unlink existing login" exists), and the sponsor wants the record
alive to show the person their own schedule and clock-ins later. The path is
R13. A terminated **and** linked record is still refused: the link is history
(concept §5.5). A wrong e-mail is fixed by terminating the wrong record and
creating a new one.

**2. Revoke first, write second (R13).** The two possible partial failures
have asymmetric costs: revoking and then failing to write leaves the record
**active and consistent** — the person merely logs in again; writing and then
failing to revoke would return an error to the client with the termination
**already persisted** — partial success hidden behind a 500. The order that
never hides partial success is revoke → write.

**3. The account remains.** No `User.is_active`, no identity migration, no
refusal at login. A terminated person authenticates again and obtains tokens
that grant nothing. And the cut is of the **refresh**: an access token already
issued stays valid until it expires (15 minutes by default — kickoff #13,
ADR 2.2.0001); this is the behaviour, not a defect, and the e2e asserts it
positively so nobody "fixes" it later. Cutting access to the unit's information is **structural**:
today by the empty permission set; tomorrow (Step 4) because self-service goes
through the employee record, which is `active=False`.

**4. `reactivate_employee` does nothing with identity.** Sessions were revoked,
not the account; the person logs in again. Re-hire is a staff transition only.

**5. `is_active` is deferred with a trigger, not a date.** The moment `employee`
receives its **first self-service permission** (Step 4, "see my schedule"), a
terminated person who can authenticate starts reaching something. That Stage —
or an identity Stage immediately before it — must add account deactivation (and
decide whether termination calls it). Recorded as `[finding]` in the concept
§10 and here.

**6. Revocation is idempotent and total (L-IG4).** A login with no live session,
or an unknown id, is not an error — the port law makes the fake and the real
implementation agree, and makes a double termination harmless.

## Alternatives considered

### Alternative A — do nothing now; pure finding
- **Description:** R13 keeps ignoring identity; the whole topic waits for an
  identity user-lifecycle Stage.
- **Pros:** zero identity work; zero risk today (empty permissions).
- **Cons:** the kickoff's *"termination cuts the refresh right away"* stays
  unimplemented although the tool exists; the first crossing of "record ↔
  login" would ship without any lifecycle coupling, and the sponsor asked for
  the cut.
- **Why rejected:** the sponsor chose the cut, and it costs one small use case
  behind a facade that this Stage builds anyway.

### Alternative B — full account deactivation in identity
- **Description:** `User.is_active`, migration, `authenticate` refuses inactive,
  `DeactivateUserUseCase` + route, called by R13 through the gateway.
- **Pros:** faithful to "termination cuts access" in the strongest sense.
- **Cons:** three to four Tasks in another BC, a schema change in identity, and
  a product decision the sponsor explicitly did **not** take (they want the
  person to keep authenticating and, later, to see their own information).
- **Why rejected:** more than asked, and against the stated product intent.

### Alternative C — write first, revoke second
- **Description:** same as the decision with the order inverted.
- **Pros:** "the termination is the important write, persist it first".
- **Cons:** a revocation failure returns 500 to a client whose termination
  **did** persist — partial success the client cannot see; retrying the
  request is harmless (idempotent) but the client does not know it should.
- **Why rejected:** hides partial success; the inverse order hides nothing.

### Alternative D — remove the unit membership on termination
- **Description:** besides revoking sessions, unlink the `User` from the unit.
- **Pros:** cuts visibility at identity's level too.
- **Cons:** identity has no "unlink membership" use case; `employee` has no
  permission that the membership would gate today; and the sponsor wants the
  person to later see **their own** information for that unit, which the
  membership will likely be needed for.
- **Why rejected:** premature, and possibly the opposite of the future need.

### Alternative E — allow R15 on a linked record, revoking sessions first
- **Description:** `DeleteEmployeeUseCase` gains the gateway, revokes, then
  deletes; the account stays alive with no record pointing to it (the round-1
  wording of this Stage's concept).
- **Pros:** the only way today to "erase" a link made to the wrong e-mail
  without leaving a terminated record behind; symmetric with R13.
- **Cons:** produces an **orphan account** whose e-mail stays taken globally
  and whose unit membership stays alive, unrecoverable until "link/unlink
  existing login" exists; contradicts the semantics of ADR 3.2.0006 (removal is
  for mistakes); and destroys the record the sponsor wants to keep for the
  person's own future view.
- **Why rejected:** sponsor's decision (concept §13 Q7): refuse, terminate
  first.

## Consequences

### Positive
- The kickoff's "refresh cut right away" is true for terminated employees
  **with a login**, using a mechanism that already existed; and no account is
  ever orphaned by a staff route — R15 refuses instead.
- The order never hides a partial success; CA11 pins it through the two fakes'
  call logs.
- `is_active` is deferred **with a condition** that a future Stage can check
  mechanically (the first non-empty permission of `Role.EMPLOYEE`).

### Negative
- A terminated person can still authenticate. Accepted by the sponsor; the
  structural cut relies on `employee` having no permission, which the concept
  of Step 4 must keep in mind (the trigger).
- `DeactivateEmployeeUseCase` (Stage 3.2, merged) gains a dependency and
  `DeleteEmployeeUseCase` a guard — the fourth backward layer expansion in the
  staff BC (3.6's finding), declared.
- A record linked by mistake cannot be deleted; it can only be terminated, and
  its wrongly-linked account lives on until "link/unlink existing login"
  exists (concept §10).
- A second request in the same transaction-less crossing (#46) — recorded as a
  reinforcement of that issue.

### Neutral / trade-offs accepted
- No termination timestamp, no "who terminated" — unchanged from ADR 3.2.0006;
  the revocation is dated by identity's `Session.revoked_at`.
- Re-hire does not restore anything: there is nothing to restore.

## Implementation notes

- `RevokeAllSessionsUseCase(sessions, clock)` in identity; exposed as
  `IdentityFacade.revoke_all_sessions(user_id: str)`; the gateway maps
  `revoke_login_sessions(UserId)` to it.
- The fake gateway records `revoke_login_sessions` in `calls`; the staff store
  fake records `employees.update` / `employees.delete`; CA11 asserts the
  relative order across the two logs for R13, that a failing gateway leaves the
  record intact, and that R15 on a linked record produces **no** `delete`
  entry.
- `EmployeeHasLoginError` lives in `staff/application/errors.py` next to
  `EmployeeInUseError` (both guard the removal), maps to 409, and brings the
  status map to 23 entries.
- CA24 (e2e): after R13 the employee's `POST /auth/refresh` returns 401, the
  access token in hand is still accepted until expiry, and `POST /auth/login`
  still succeeds; R15 on a linked record (active or terminated) returns 409
  and leaves record and session untouched.

## References
- `docs/stages/3.5-employee-login-link/concept.md` §5.5, §5.6, §6.1, §6.4,
  §7 D3, §10 (finding `is_active`), §13 Q3 and Q7, CA11, CA20, CA24
- `docs/stages/2.4-identity-http/technical.md` §7 — `[finding]` 2026-07-20
  ("Rota de desativação/demissão de usuário")
- ADR 2.2.0001 (revocable sessions), ADR 3.2.0006 (employee lifecycle and
  guarded deletion — the semantics R15 keeps), ADR 3.5.0001 (the facade the
  revocation goes through)
- Kickoff decisions #4 and #13 (memory `loop-kickoff-decisions-2026-07`)
- Issue #46 (Unit of Work)

## Supersessão parcial

**2026-10-19 — §1 e metade do §5 superadas por ADR 3.8.0001.**

- §1, *"if `employee.user_id is not None` it calls `revoke_login_sessions(user_id)`"*:
  a chamada passa a exigir também que o registro esteja ativo, que nenhum outro registro
  **ativo da mesma unidade** aponte para o login e que o papel da conta seja `employee`
  (ADR 3.8.0001 §1). A premissa deste ADR — toda
  conta vinculada é `employee` com um registro — não vale para "vincular login existente"
  (issue #60).
- §5, *"must add account deactivation (and decide whether termination calls it)"*: a metade
  *"decide whether termination calls it"* está decidida — **nunca chama** (ADR 3.8.0001 §4).
  Acrescentar a desativação de conta, com o gatilho daqui, continua valendo.

O resto deste ADR (§1b, §2, §3, §4, §6) continua em vigor.

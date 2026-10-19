---
title: ADR 3.7.0001 — Terminating an employee record revokes the login's sessions only when the login is an `employee` account with no other active record in the same unit; termination never deactivates the account
description: Architecture Decision Record
when-use: Reference before changing what `deactivate_employee` (R13) does with a linked login, before implementing "link an existing login" or "unlink a login", before adding `User.is_active` or account deactivation, or when a login may hold more than one staff record or a role other than `employee`
keywords: [adr, termination, deactivate, revoke-sessions, is_active, employee-login, manager-login, identity-gateway, staff, identity]
status: accepted
created_at: 2026-10-19
updated_at: 2026-10-19
adr_id: 3.7.0001
decision: R13 revokes the linked login's sessions only when (1) no other **active** record of the **same unit** carries that login and (2) the login's role in identity is `employee`, and only when the record being terminated is still active; otherwise it writes the termination and leaves sessions alone. Condition 1 is read from `EmployeeRepository.list_by_unit` (no new repository method); condition 2 through a new `IdentityGateway.is_employee_login` (L-IG5), backed by a read-only `IdentityFacade.account_role`. Termination never deactivates the account, now or when account deactivation exists
context_stage: 3.7-termination-access-scope
bounded_context: staff
---

# ADR 3.7.0001 — Termination revokes only the access the record grants

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — decided by the sponsor on 2026-10-19 (Stage 3.7 concept §13 Q1–Q4).

**Partially supersedes ADR 3.5.0003**, by dated note in that ADR's
`## Supersessão parcial` (CONVENTIONS §5):

- **§1** — *"if `employee.user_id is not None` it calls
  `revoke_login_sessions(user_id)`"* is superseded by Decision 1 below: the
  call is now conditional on three more facts.
- **§5**, the clause *"must add account deactivation (and decide whether
  termination calls it)"* — the *decide whether termination calls it* half is
  decided here (Decision 4: it never does). Adding account deactivation itself,
  with its trigger, stays as ADR 3.5.0003 §5 recorded it.

Everything else in ADR 3.5.0003 stands: revoke **before** write (§2), the
account remains (§3), re-hire does nothing with identity (§4), L-IG4 (§6), and
R15 refusing a linked record (§1b).

## Context

ADR 3.5.0003 made R13 revoke **all** sessions of the linked login. That was
right under its premise: every link was created by R17, which always creates a
**new** account with role `employee` and **one** record; `employee` has no
permission at all, so the revocation is the whole cut.

The premise does not survive two cases the domain already admits (issue #60,
finding F2 of the post-merge audit of Stage 3.5):

- **(a) A login with two records.** Workforce §3.1 and §3.7: the same person may
  have several records, all pointing at the same `User` (ADR 3.1.0001 iii).
- **(b) A manager or owner who also works the schedule.** Concept 3.5 §4 and
  §10: the link does not require the `employee` role, and "link an existing
  login" names exactly this case as the first one. Their authority comes from
  their role in identity, not from the record: revoking their sessions protects
  nothing (they log in again and get every management permission back) and only
  interrupts their work.

Neither case can be produced today — the copy never carries `user_id`
(ADR 3.5.0004) and "link an existing login" does not exist — and that is the
point: the rule must be in place **before** the first login has a second
record or a non-`employee` role.

Two constraints shaped the answer:

- Workforce §3.1: *"no staff operation crosses units implicitly — only the
  explicit copy (§3.7)"*. The sponsor kept it literally (concept §13 Q4): the
  "other active record" check looks at the **same unit** only.
- The sponsor's intent about the account, already on record (ADR 3.5.0003
  Context): a terminated person *"can still log in … perhaps leaving only
  information about themselves (schedule, clock-in history) in the future"* —
  confirmed for account deactivation on 2026-10-19 (concept §13 Q2).

Revoking sessions does not lock anyone out: the account remains and the person
can log in again (ADR 3.5.0003 §3). What a wrong revocation costs is an
interrupted session and a new login — which is why the residual cases below are
acceptable.

## Decision

**1. R13 revokes only when the record is the source of the login's access.**
After `find_by_id` (404 as today), with `user_id = employee.user_id`:

```
if employee.active and user_id is not None
   and not any(other.user_id == user_id and other.id != employee.id
               for other in employees.list_by_unit(tenant, unit))   # active only (L-E6)
   and gateway.is_employee_login(user_id):
       gateway.revoke_login_sessions(user_id)
employees.update(employee.deactivate())
```

- `employee.active`: terminating an already-terminated record touches nothing in
  identity. Sessions the person opened legitimately after the first termination
  (the account remains) are not cut by a double-click or a retry. A retry after
  a failed write is still safe: revocation comes before the write, so a record
  whose write failed is still active and the retry revokes again.
- The same-unit check covers case (a) inside a unit. Across units, terminating
  the record in unit X **does** revoke even if the login has an active record in
  unit Y; the person logs in again and keeps the access unit Y's record grants.
  This is the sponsor's choice (concept §13 Q4), traded for keeping workforce
  §3.1 literal.
- The role check covers case (b) for every non-`employee` role.

**2. The staff fact is asked first, the identity fact second, both before the
write.** The local read decides the same-unit case without crossing the
boundary. Any failure — in the listing, in the role query or in the revocation —
leaves the record active and the request failed in full (ADR 3.5.0003 §2).

**3. The identity fact comes through one new port operation.**
`IdentityGateway.is_employee_login(user_id) -> bool` — **L-IG5**: `True` iff
identity knows the login **and** its role is the employee role; an unknown login
is `False`, not an error (it has no session to revoke); any other failure rises
raw, same instance (same reasoning as L-IG2 — a `False` on failure would be
fail-open). The real implementation reads a new read-only
`IdentityFacade.account_role(user_id: str) -> str | None` and compares it with
the `"employee"` literal the adapter already owns (L-IG1); staff application
code never sees the role vocabulary.

**4. Termination never deactivates the account.** When account deactivation
exists (ADR 3.5.0003 §5 trigger: the first self-service permission of
`employee`), it is a separate act in identity, never a consequence of R13.

**5. The rule belongs to "a record's active link ends" (same-unit check, role
check), not to R13 alone.** Today
R13 is the only path that ends a record's active link (R15 refuses a linked
record, the copy never carries `user_id`). Any future operation that ends one —
"unlink a login", "relink to another login" — must apply the same rule.

## Alternatives considered

### Alternative A — revoke only when no other active record carries the login (no role check)
- **Pros:** staff-only change.
- **Cons:** case (b) unchanged — a manager with one schedule record loses their
  sessions for nothing.
- **Why rejected:** sponsor's decision (concept §13 Q1).

### Alternative B — never revoke on termination
- **Pros:** simplest; no cross-BC call in R13.
- **Cons:** drops kickoff #13's "the refresh is cut right away" for the one case
  where it is the whole cut (an `employee` login with one record).
- **Why rejected:** sponsor's decision (concept §13 Q1).

### Alternative C — look for other active records in every unit of the tenant
- **Description:** a tenant-wide `exists_other_active_with_login` in the
  repository (a new law, L-E8).
- **Pros:** closes case (a) across units too.
- **Cons:** a staff operation whose outcome depends on records of other units,
  against workforce §3.1; a new port method with two implementations and a
  contract.
- **Why rejected:** sponsor's decision (concept §13 Q4); the cost of not doing it
  is one re-login.

### Alternative D — revoke by scope (unit)
- **Pros:** the most precise cut.
- **Cons:** sessions have no scope today; changes `SessionRepository`, the token
  and the refresh flow — a Stage of its own — and a manager session would still
  need the role rule.
- **Why rejected:** cost far beyond the problem.

### Alternative E — put the role rule inside identity's revocation
- **Description:** one gateway call, `revoke_login_sessions`, whose identity
  side revokes only `employee` accounts.
- **Cons:** hides a staff policy inside an identity operation whose law (L-IG4)
  says "idempotent and total"; the use case could no longer state, or be tested
  on, why it did or did not cut.
- **Why rejected:** each BC decides on the fact it owns; the policy stays in R13.

### Alternative F — the port returns the role (`login_role(user_id) -> str | None`)
- **Cons:** staff would start naming identity's role vocabulary in application
  code; the `bc-independence` sweep (concept 3.5 CA07, inherited from 3.4 CA12)
  keeps `Role` out of staff and the `"employee"` literal lives only in the
  adapter.
- **Why rejected:** the boolean keeps the vocabulary at the edge; widening it
  later is additive.

### Alternative G — deactivate the account under the same condition as the revocation
- **Description:** when deactivation exists, R13 on the last active record of an
  `employee` account also deactivates it.
- **Pros:** strongest cut once `employee` gains self-service.
- **Cons:** the person loses the future view of their own information, which the
  sponsor wants; self-service already goes through the record, which is
  `active=False`.
- **Why rejected:** sponsor's decision (concept §13 Q2).

### Alternative H — re-check after the write to close the concurrent-termination race
- **Description:** after `update`, re-read the unit and revoke if no other active
  record remains.
- **Pros:** closes the race described under Negative.
- **Cons:** a failing post-write revocation returns 500 with the termination
  already persisted — the hidden partial success ADR 3.5.0003 §2 exists to
  prevent — and, with Decision 1's `employee.active` guard, a retry would no
  longer revoke.
- **Why rejected:** trades a rare, low-impact race for a guaranteed class of
  hidden partial success. `[decision:C]`, degree 4 (the reversible option that
  does not close the Unit of Work path, #46).

## Consequences

### Positive
- Case (b) and case (a) inside a unit are safe before "link an existing login"
  can create them; the rule is pinned by unit tests on fakes, by the gateway
  contract and by e2e.
- The single-record `employee` case behaves as ADR 3.5.0003 delivered on the
  first termination (CA24 of Stage 3.5 keeps passing unchanged); a repeated
  termination no longer revokes (Decision 1).
- A future account deactivation cannot be triggered by a staff termination.
- No new repository method, no schema change, no index.

### Negative
- **Case (a) across units still revokes**: a person with records in two units
  terminated in one has to log in again. Accepted (concept §13 Q4).
- **Concurrent termination of two same-unit records of one login**: each request
  may read the other as still active, and neither revokes. The login keeps live
  sessions that reach nothing in staff (`employee` has no permission; Step 4
  self-service goes through the record, now `active=False`) until the refresh
  expires. Closed by a Unit of Work (#46) or by the Stage that makes two
  same-unit links possible ("link an existing login").
- R13 now reads the whole unit listing before terminating a linked record — tens
  to hundreds of aggregates, once per termination.
- Identity gains a fourth facade operation and a use case whose only consumer is
  the facade (same posture as ADR 3.5.0001 §Consequences).
- The Stage delivers in two bounded contexts (PIPELINE §4.2 #1(b), #4), authorized
  by the sponsor (concept §13 Q3).

### Neutral / trade-offs accepted
- The role is read at termination time; roles are fixed in identity today
  (`User.role`), so it cannot change between the check and the revocation.
- `is_employee_login` takes no tenant: today a login only reaches records of its
  own tenant because R17 provisions inside the record's tenant. "Link an
  existing login" must check that tenant (finding in the Stage 3.7 technical §7).

## Implementation notes

- `GetAccountRoleUseCase(users).execute(GetAccountRoleCommand) -> AccountRoleResult | None`
  in identity (`AccountRoleResult.role: Role`, converted to its value by the
  facade), exposed as `IdentityFacade.account_role`; wired once in
  `composition_root` over the same `UserRepository` the identity routes use.
- The fake gateway answers L-IG5 from its ledger: provisioned logins are
  `employee`, a second ledger holds logins of other roles, anything else is
  unknown (`False`). Stage 3.5's unit tests of R13 are re-arranged to provision
  the login through the fake instead of linking an unknown id.
- The e2e arranges cases (a) and (b) with a direct `UPDATE employees SET user_id`
  — the only way to produce them until "link an existing login" exists — and
  asserts the effect through `POST /auth/refresh`, always presenting the
  **rotated** refresh token (presenting a used one triggers reuse detection and
  a 401 that proves nothing).

## References
- Issue #60; Stage 3.7 concept §5, §7, §11, §13
- ADR 3.5.0003 (partially superseded here), ADR 3.5.0001 (facade), ADR 3.5.0004
  (`user_id` column), ADR 3.1.0001 iii (several records per person), ADR 0.0.0006
  (use cases return result DTOs)
- `docs/domain/staff/workforce.md` §3.1, §3.7, §3.8; concept 3.5 §4, §10, CA07
- Kickoff decision #13 (memory `loop-kickoff-decisions-2026-07`)

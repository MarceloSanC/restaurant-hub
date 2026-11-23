---
title: ADR 3.10.0002 — An existing account is named by its e-mail and is linkable only if it belongs to the record's tenant and reaches the record's unit (membership, or the every-unit reach identity gives the owner), every refusal looking the same; the three link transitions require manage_staff and manage_users on the unit
description: Architecture Decision Record
when-use: Reference before changing who may link, swap or unlink a login, before changing which accounts are linkable to a staff record, before adding a role check to linking, or before widening `IdentityFacade.find_account_by_email`
keywords: [adr, login-link, existing-account, e-mail, tenant, membership, platform-admin, oracle, facade, identity-gateway, staff, identity]
status: accepted
created_at: 2026-11-22
updated_at: 2026-11-22
adr_id: 3.10.0002
decision: 'R18 and R19 name the account by e-mail. Identity answers through a read-only facade-only use case, `IdentityFacade.find_account_by_email(email) -> AccountSummary | None` (id, tenant, its unit ids, whether it sees every unit — no role), consumed by `IdentityGateway.find_login_by_email` (L-IG6). The account is linkable iff it exists, its tenant is the record''s tenant and it reaches the record''s unit — a member of it, or an account identity lets see every unit of its tenant (the owner, created with no membership); unknown, other-tenant, platform_admin and out-of-unit accounts all raise the same `LoginAccountNotFoundError` (404). Linking does not create membership and does not look at the role. R18, R19 and R20 authorize manage_staff then manage_users on the unit, like R17; an actor may link their own account.'
context_stage: 3.10-login-link-management
bounded_context: staff
---

# ADR 3.10.0002 — Existing-account eligibility, by e-mail

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — Stage 3.10 concept §7 D2–D4 and D10 (sponsor-delegated product forks,
2026-11-22; revised after Checkpoint A, concept §13 A-1 and A-12).

## Context

- Technical 3.8 §7 finding: `is_employee_login` takes no tenant, and nothing would stop a
  future link from pointing a record at an account of another tenant (`employees.user_id`
  has no FK, ADR 3.5.0004). Direction: refuse another tenant's account and `platform_admin`.
- Concept 3.5 §10: the link needs its own rule (tenant of the `User`, unit membership) and
  does **not** require the `employee` role.
- No identity route lists accounts; R17 names the account by e-mail, and the staff request
  sweep forbids `user_id` in requests because identity generates it.
- `User.tenant_id` is `None` only for `platform_admin`, who holds no membership
  (ADR 2.1.0002).
- The owner is created with no membership (`provision_restaurant.py`, `invite_owner.py`) and
  sees every unit of its tenant through `User.bypasses_unit_scope` (`can_view_unit`).
- `UserRepository.list_memberships` "does not need to filter" by user (its docstring, point 3).
- ADR 3.4.0007 §4: no error confirms the existence of what the caller cannot address.

## Decision

**1. The account is named by e-mail.** R18 and R19 take `email`. Staff asks
`IdentityGateway.find_login_by_email(email) -> ExistingLogin | None` (**L-IG6**): the
account with that e-mail (as identity normalizes it) in any tenant, with its tenant (`None`
outside any restaurant), the units **it** is a member of, and `every_unit` — whether it sees
every unit of its tenant without membership (always false without a tenant); no account ⇒ `None`; malformed ⇒ `InvalidLoginEmailError`
(same translation as L-IG2); any other failure rises raw, same instance.

**2. Identity answers through a facade-only read.** `FindAccountByEmailUseCase(users)`
returns `AccountSummaryResult(user_id, tenant_id, unit_ids, sees_every_unit)` or `None`,
reading `find_credentials_by_email` (the hash never leaves the use case) and `list_memberships`
filtered by the account's id; `sees_every_unit` is `User.bypasses_unit_scope()` for an
account with a tenant and false for `platform_admin`, so the visibility rule stays in
identity.
`IdentityFacade.find_account_by_email(email: str) -> AccountSummary | None` converts to
primitives. It is a named exclusion of the ADR 0.0.0020 inventory ("facade-only; the
consumer authorizes") and joins the facade-only reach sweep of Stage 2.7. No role is
returned (ADR 3.8.0001 Alternative F: the role vocabulary stays at the edge; the owner's
reach arrives as a visibility fact, not as a role).

**3. Eligibility, decided in staff's application layer.** Linkable iff the account exists,
`tenant_id` equals the record's tenant, and `every_unit` is true or the record's unit is in
`unit_ids`. Every other case — unknown e-mail, another tenant, `platform_admin`, same tenant
without reach over the unit —
raises one `LoginAccountNotFoundError` (application root, 404) with one message. The rule
lives in `_login_link.resolve_linkable_login`, shared by R18 and R19. One exception: when the
account found is the record's current login (reachable only from R19), the helper returns it
without checking eligibility; the login already belongs to the record, and R19 then writes
and revokes nothing.

**4. Linking creates no membership and ignores the role.** A manager, hr or `employee`
account is linkable where it is a member; the owner anywhere in its tenant. A manager, hr or
employee account without membership in the record's unit is not linkable until identity
manages memberships.

**5. Who may.** R18, R19 and R20 authorize `manage_staff` then `manage_users` on the
record's unit before any read — the R17 pair (concept 3.5 §5.3; ADR 3.7.0001). An actor may
link their own account: it is the case the Stage exists for.

## Alternatives considered

### Alternative A — Name the account by `user_id`
- **Cons:** no API gives a manager another person's id; reopens the request sweep.
- **Why rejected:** sponsor-delegated product fork (concept D2).

### Alternative B — Distinct errors for unknown, other tenant and non-member
- **Pros:** clearer message to the manager.
- **Cons:** tells a manager that an e-mail is an account elsewhere — an oracle across
  tenants and units.
- **Why rejected:** `[decision:C]` rung 2 (tenant isolation, fail-closed).

### Alternative C — The link creates the membership
- **Cons:** a write in identity from staff, with identity's membership rules
  (ADR 2.1.0001), and a cross-BC two-write request without a unit of work.
- **Why rejected:** sponsor-delegated product fork (concept D3).

### Alternative D — Require membership for every role, the owner included
- **Pros:** one fact, no every-unit flag.
- **Cons:** the owner is created with no membership, so no owner would ever be linkable —
  half of the case this Stage exists for (Checkpoint A, concept §13 A-1).
- **Why rejected:** sponsor-delegated product fork (concept D3), revised.

### Alternative E — Require the actor to be able to grant the account's role
- **Cons:** moves `required_permissions_for_role` across the facade for an act that grants
  no permission.
- **Why rejected:** sponsor-delegated product fork (concept D4).

### Alternative F — A new `UserRepository.find_by_email`
- **Why rejected for now:** a port change in identity (fake, adapter, contract) while
  another branch edits identity; additive later. `[decision:C]` rung 4.

## Consequences

### Positive
- The DoD's three refusals (another tenant, `platform_admin`, out of the actor's reach)
  hold by construction and are pinned by unit and e2e tests.
- No new cross-tenant oracle: the refusal is uniform.

### Negative
- A manager, hr or employee account without membership in a unit cannot be linked to a
  record there.
- The lookup reads the password hash it discards.
- Identity gains a fifth facade operation and a fifth facade-only use case.

### Neutral / trade-offs accepted
- R17 still answers 409 for an e-mail used in any tenant (declared oracle since Stage 2.5);
  this ADR does not change it.

## References
- Stage 3.10 concept §5 R4–R6, §7 D2–D4, D10; issue #218
- Technical 3.8 §7 (finding "vincular login existente precisa checar o tenant do `User`");
  concept 3.5 §5.3, §10
- ADR 0.0.0020, ADR 2.1.0001, ADR 2.1.0002, ADR 3.4.0007, ADR 3.5.0001, ADR 3.5.0004,
  ADR 3.7.0001, ADR 3.8.0001

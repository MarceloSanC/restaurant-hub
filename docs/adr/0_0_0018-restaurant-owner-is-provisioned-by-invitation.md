---
title: ADR 0.0.0018 — The restaurant owner is provisioned by invitation; no platform route takes the owner's password
description: Architecture Decision Record
when-use: Reference before changing `POST /restaurants`, `POST /restaurants/{id}/owners` or `ProvisionRestaurantUseCase`, before adding any route that creates an account with a password chosen by someone other than its holder, or when designing the owner self-signup (Step 13) or a "must change password" feature
keywords: [adr, provisioning, restaurant, owner, invitation, pending-account, setup-token, unusable-hash, platform-admin, credential, identity, issue-114]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-09
adr_id: "0.0.0018"
decision: "The owner emitted by `POST /restaurants` and by `POST /restaurants/{id}/owners` is born as a pending account (unusable hash + single-use INVITATION setup token) and receives the setup link by e-mail sent after the identity unit commits; neither request body has a password field any more. `ProvisionRestaurantUseCase` writes `restaurants.add` + `users.add` + `tokens.add` in one unit and sends with the existing invitation message; the owner route reuses `InviteUserUseCase` with the literal `Role.OWNER` and the tenant from the path. A failed send propagates (5xx) with restaurant, owner and token committed; the recovery is the public password-reset request."
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0018 — The restaurant owner is provisioned by invitation

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided in issue #114 (standalone issue, hence the `0.0` prefix — CONVENTIONS §1,
"ADR global" — and `bounded_context: transversal`, as for ADR 0.0.0014, which this one amends).
The issue marks the fork as **P** (sponsor); the sponsor delegated P forks to the orchestrator,
which takes the recommended option:

```
[decision] P delegado — Opção A (convite), motivo: é a única opção em que a plataforma nunca
conhece nem transporta a senha do dono, reusa o fluxo de conta pendente que identity já tem
(ADR 2.5.0002/2.5.0004, ADR 3.5.0002) sem schema nem entidade nova, e é o esqueleto que o
auto-cadastro do Step 13 também usa; troca obrigatória seria mais código para uma propriedade
mais fraca (ADR 3.5.0002 Alternativa B).
```

The number was checked free on `develop`, on every remote branch and in every open worktree on
2026-11-09 (`0.0.0017` was the last one taken).

**Partially supersedes [ADR 0.0.0014](./0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md):**
§Decision 5 (*"The owner gets a password, not an invitation"*), the credential half of §Decision 1
(the `owner_plain_password` field and the hashing step) and of §Decision 2 (the `password` in the
`owner` body), the sentence of §Decision 3 *"Its contract does not change"*, and the negative
consequence *"The platform admin still chooses the owner's first password"*. Everything else in
0.0.0014 stands: restaurant and owner in one identity unit of work, no API path that creates a
restaurant without an owner, the owner route kept as the platform's support path, the role as a
code literal, authorization at the HTTP boundary. 0.0.0014 receives an append-only dated note.

**Amends [ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md) §4 and §5** only where
they name `CreateUserUseCase` as the use case behind `POST /restaurants/{restaurant_id}/owners`:
the route now runs `InviteUserUseCase`, with the same literal role, the same tenant origin (the
path) and the same 404 for an unknown restaurant. 2.4.0003 receives an append-only dated note.

## Context

- **The gap (issue #114, finding F1 of #67).** `POST /restaurants` and
  `POST /restaurants/{id}/owners` took the owner's password in the request body, chosen by the
  `platform_admin`. The platform knew the first credential of every tenant's owner, and nothing
  forced it to change — the password the admin typed could stay the owner's password forever.
- **What security guidance says.** OWASP ASVS 4.0.3, V2.3.1: *"Verify system generated initial
  passwords or activation codes SHOULD be securely randomly generated, … and expire after a short
  period of time. These initial secrets must not be permitted to become the long term password."*
  The requirement is written for *system-generated* initial secrets; a password chosen by the
  platform admin is a weaker case of the same thing (not random, known to a third party), so the
  requirement is applied here by analogy, not quoted as a literal rule about admin-chosen
  passwords. Under the old routes that initial secret became the long-term password.
- **Identity already has the whole pending-account flow.** `PasswordHasher.unusable_hash`
  (ADR 2.5.0004), the single-use, purpose-bound, expiring `PasswordSetupToken` (ADR 2.5.0002),
  `SetPasswordWithTokenUseCase` behind the public `POST /auth/password`, the shared invitation
  message (`_invitation.py`), and `InviteUserUseCase`, which already resolves a tenant id and
  answers `RestaurantNotFoundError` (404) for one that does not exist.
- **Identity has no forced-change mechanism.** `User` has no flag, `AuthenticateUserUseCase`
  enforces nothing, and no route changes a password other than the setup-token one — the
  measurement ADR 3.5.0002 made for employees still holds.
- **Who calls these routes.** Only the test suites; the API is pre-release `/api/v1` with no
  external client (same as ADR 0.0.0014).

## Decision

1. **The owner is a pending account.** Both routes that emit an `owner` create it with
   `hasher.unusable_hash()` and an `INVITATION` setup token whose link goes **only** in the
   e-mail. No request schema of either route has a password field; the response is the same
   `UserResponse` as before, with no token or link.
2. **`ProvisionRestaurantUseCase`** takes `ProvisionRestaurantCommand(name, owner_email)` and, in
   order: builds the `Restaurant` (domain name invariant); refuses an `owner_email` already
   registered; builds the owner with the literal `Role.OWNER` and the new restaurant as tenant;
   then **one unit** — `restaurants.add`, `users.add(owner, unusable_hash, ())`, `tokens.add` —
   and, **after the unit commits**, sends `invitation_message(owner_email, setup_link(...))`.
   The token is issued inline, not through `InviteUserUseCase.execute`: writes reached through
   another use case's `execute` are `check_layout` rule 10's declared blind spot (ADR 2.6.0002
   §5; ADR 0.0.0014 Alternative F). [decision:C] rung 1.
3. **`POST /restaurants/{restaurant_id}/owners` reuses `InviteUserUseCase`** with
   `InviteUserCommand(email, role=Role.OWNER, tenant_id=<path>, unit_ids=())`. The role stays a
   router literal and the tenant stays the path (ADR 0.0.0005, ADR 2.4.0003 §4); the 404 band for
   an unknown restaurant and the 409 band for a taken e-mail are the use case's, unchanged.
   [decision:C] rung 1 — the invitation use case exists and already does exactly this.
4. **The e-mail runs after the commit, and its failure propagates.** As for every identity
   invitation (rule 13 of Stage 2.5; ADR 2.6.0002 §3): restaurant, owner and token stay
   committed, the response is 500, and the recovery is the public password-reset request
   (`POST /auth/password-reset-requests`), not a second provisioning (which answers 409).
   [decision:C] rung 1.
5. **TTL and message are the invitation's.** `invitation_ttl` (`Settings.invitation_token_ttl_hours`)
   and the same subject and body as `POST /users/invitations` — the message is not changed, so
   nothing the pilot sees changes except that the owner receives an invitation. [decision:C]
   rung 1.
6. **A `password` sent by an old client is ignored, not refused.** Extra fields are ignored across
   the identity schemas on purpose (schemas module note 3); the sent value never reaches a use
   case, and the e2e suite proves it does not open the account. [decision:C] rung 1.

## Alternatives considered

### Alternative A — Invitation (chosen)
- **Pros:** the platform never knows, transports or types the owner's credential; the initial
  secret is random, single-use and expiring and cannot become the long-term password (in line
  with ASVS V2.3.1); zero schema, entity or port change — only application wiring; the owner's onboarding
  is the same mechanism Step 13 self-signup would need.
- **Cons:** breaking change to both request bodies (pre-release, no external client); one more
  side effect with its own failure surface (§4); provisioning now depends on a working e-mail
  sender.

### Alternative B — Keep the password, force a change on first login
- **Description:** `User.must_change_password`, a migration, `authenticate` refusing or
  restricting until a change route is used.
- **Pros:** the admin flow keeps its shape.
- **Cons:** entity change, **schema migration**, login enforcement and a new route; and the
  outcome is weaker — the password still crosses the platform API and the admin knows it until
  the first login (and can log in as the owner before the owner does).
- **Why rejected:** the same trade ADR 3.5.0002 Alternative B rejected for employees: more scope
  for a worse property.

### Alternative C — Keep the password and accept the risk
- **Pros:** no change.
- **Cons:** the initial secret becomes the long-term password (against ASVS V2.3.1, by analogy); the
  platform holds every tenant's owner credential.
- **Why rejected:** the issue asks for this before the first real tenant; nothing in the project
  argues for keeping the exposure.

### Alternative D — Invitation with the link returned to the admin (in-hand channel)
- **Description:** like `ProvisionAccountUseCase`, return the setup link in the 201 body for the
  admin to pass on.
- **Pros:** works without an e-mail provider.
- **Cons:** the admin holds a secret that sets the owner's password — the platform can still
  take the account before the owner. ADR 3.5.0002 confines that carve-out to one staff route,
  for employees who may have no e-mail; an owner always has one (it is the login).
- **Why rejected:** reopens, for the most privileged role of a tenant, the exposure this issue
  closes. Recorded as a **candidate strategy** only if a pilot without e-mail ever needs it.

## Consequences

### Positive
- No platform route carries the owner's password; a test sends one and proves it does not open
  the account.
- The owner's first password is chosen only by the owner, through a single-use link that expires.
- Provisioning stays atomic and now covers three writes (pinned by the unit and Postgres
  failure-after-write-N suites).

### Negative
- **Breaking change** to the bodies of `POST /restaurants` and `POST /restaurants/{id}/owners`.
  Accepted pre-release; every test call site was migrated in the same change.
- A send failure leaves a committed tenant whose owner has not yet received a link; the admin
  sees 500 and the owner recovers through the public reset — the same window every invitation
  has. An outbox would close it (ADR 2.6.0002 Alternative C), and stays out of scope.
- **The guarantee depends on a real e-mail sender.** Until one is wired, `wire_dependencies`
  falls back to `ConsoleSender`, which prints the message body — the setup link included — to the
  server's stdout (`shared/infrastructure/email/console_sender.py`). Whoever reads that output can
  set the owner's password first, which is the exposure Alternative D was rejected for. This is
  not new — every invitation and reset has had it since Stage 2.5 — and it closes when the real
  adapter lands; it is recorded as a finding on issue #114 so the pilot does not run on the
  console sender.
- **A wrong owner e-mail has no clean recovery.** If the admin mistypes the address, the reset
  goes to the same wrong address; re-provisioning with the right one creates a second restaurant
  (names are not unique), and there is neither a restaurant listing nor an account deactivation
  to clean up the first. The old flow had the same hole (an owner nobody could reach); it is
  recorded as a finding, not solved here.
- **A send failure surfaces as an unhandled exception**, logged by the server's default handler
  with its traceback, as `POST /users/invitations` already does. Whether a provider's message can
  carry the recipient or the link into that log (the concern `request_password_reset.py` handles
  by logging only the exception type) applies to every invitation path; recorded as a finding.
- `ProvisionRestaurantUseCase` now holds a fourth copy of the token-issuing step (after
  `InviteUserUseCase`, `ProvisionAccountUseCase` and `RequestPasswordResetUseCase`); extracting
  it is left to the change that makes the copies diverge or adds a fifth.

### Neutral / trade-offs accepted
- The e2e suites activate each provisioned owner the way a real owner would: read the captured
  e-mail, define the password through `POST /auth/password`, then log in.

## References
- Issue #114; issue #67 (finding F1); OWASP ASVS 4.0.3, V2.3.1 —
  https://github.com/OWASP/ASVS/blob/v4.0.3/4.0/en/0x11-V2-Authentication.md
- [ADR 0.0.0014](./0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) §Decision 1–3, 5, Alternative E
- [ADR 2.5.0002](./2_5_0002-dedicated-single-use-setup-token.md), [ADR 2.5.0004](./2_5_0004-unusable-hash-for-pending-accounts.md)
- [ADR 2.6.0002](./2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md) §3, §5
- [ADR 3.5.0002](./3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) Alternative B
- `src/restaurant_hub/features/identity/application/use_cases/provision_restaurant.py`,
  `src/restaurant_hub/features/identity/application/use_cases/invite_user.py`

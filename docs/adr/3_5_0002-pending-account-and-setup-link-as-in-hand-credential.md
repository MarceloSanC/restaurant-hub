---
title: ADR 3.5.0002 — The "provisional password handed in person" is a pending account plus a one-time setup link; identity separates provisioning from delivery, and the link may leave through the API only on the staff route's `link` channel
description: Architecture Decision Record
when-use: Reference before adding any credential-delivery path, before letting a setup token or link appear in any API response, before changing the order of `CreateLoginForEmployeeUseCase`, or when designing a "must change password" feature
keywords: [adr, login, invitation, setup-token, setup-link, pending-account, unusable-hash, provisional-password, delivery-channel, staff, identity]
status: accepted
created_at: 2026-09-12
updated_at: 2026-09-13
adr_id: 3.5.0002
decision: there is no provisional password — an employee login is born as a pending account (unusable hash + single-use setup token, ADR 2.5.0002/0004) and the manager chooses the delivery channel of the setup link (`email` sent by identity, or `link` returned once in the 201 body to an actor holding `manage_users`); identity exposes `provision_account` and `send_invitation` as separate operations so that staff writes `user_id` between them, the link handed over in person lives under its own configurable TTL (`handover_link_ttl_hours`, default 168h), `InviteUserUseCase` is left intact (only the link/message composition moves to a shared helper), and forced password change is structural because the handed-over secret can only define a password, never authenticate
context_stage: 3.5-employee-login-link
bounded_context: staff
---

# ADR 3.5.0002 — Pending account + one-time setup link as the in-hand credential

## Status

`accepted` — decided by the sponsor on 2026-09-12 (concept §13 Q1).

This ADR **narrowly carves out** rule 1 of the Stage 2.5 concept (*"the token
never leaves through API, log or redirect URL"*): the carve-out is **one**
identity operation (`ProvisionAccountUseCase`, whose result carries the link)
and **one** staff route in **one** channel (R17 with `delivery="link"`). Rule 1
continues to hold everywhere else, including R17's `email` channel.

## Context

The overview (§3) promises an optional employee login *"via e-mail invitation
or a provisional password handed in person"*, and the domain doc
(`workforce.md` §3.8) adds *"with mandatory change on first access"*. Measured
against the code:

- identity has **no mechanism for forced password change**: `User` has no flag,
  `AuthenticateUserUseCase` enforces nothing, and no route offers a change
  flow other than the public reset.
- identity **does** have everything a pending account needs:
  `PasswordHasher.unusable_hash` (ADR 2.5.0004), `PasswordSetupToken`
  (single-use, expiring, ADR 2.5.0002), `SetPasswordWithTokenUseCase` and the
  public `POST /auth/password`. Today the only carrier of the token is the
  e-mail composed inside `InviteUserUseCase`.
- `CreateUserUseCase` — the roadmap's literal `create_user` — creates a
  **usable** account with a password chosen by the caller. The 2.5 concept
  called that shape *"impossible in a real product, where whoever invites does
  not know the invitee's password"*.
- `InviteUserUseCase` provisions **and** sends in one operation. A staff use
  case calling it cannot record `user_id` **before** the e-mail goes out; if
  the e-mail fails, the account exists and staff has not linked it.
- The sponsor described the intended flow as *"a pre-created account not yet
  ready for use; the manager sends the link or QR code inviting the person to
  set up the account (choose the password, fill in what the manager does not
  know)"*.

## Decision

**1. No provisional password exists.** An employee login is always born
**pending**: `User` with `unusable_hash`, `role = employee`, membership of the
employee's unit, and a `PasswordSetupToken` (`INVITATION` purpose; TTL by
channel — §3b). The account becomes usable only through the
setup link and `POST /auth/password`. **Forced change is structural**, not a
rule: the secret in the manager's hands cannot authenticate anyone.

**2. The manager chooses the delivery channel, not the credential.**
`CreateLoginRequest.delivery ∈ {"email", "link"}`, required, no default:

- `email` — identity sends the link (`SendInvitationUseCase`); the 201 body has
  `setup_link: null`. Rule 1 of 2.5 holds unchanged for this channel.
- `link` — the 201 body carries `setup_link` **once**, to the actor who was
  just authorized with `manage_staff` **and** `manage_users` on the unit;
  nothing is sent. There is no route to see it again; recovery through the
  public reset requires a **working e-mail** — and the population this channel
  exists for may not have one (see Neutral; concept §6.4, §13 Q5).

**3. identity separates provisioning from delivery — and does not recompose
`InviteUserUseCase`.** `ProvisionAccountUseCase` creates the pending account and
returns the composed link (`{base_url}/definir-senha?token=<value>`);
`SendInvitationUseCase` composes the message and sends it. The link format and
the message text move to **one** shared helper
(`identity/application/use_cases/_invitation.py`). The format lives today in
**two** modules — `invite_user.py:209` and `request_password_reset.py:147` —
and both switch to the helper (two lines each; constructors, check order,
behaviour and tests stay intact). Recomposing `InviteUserUseCase` over the two new use
cases is **not** done: it is not needed for the DoD, it would change a
constructor that two 2.5 tests and the composition root call, and it is the item
that would most touch merged code of another BC. The duplication of the check
order across `create_user`, `invite_user` and `provision_account` is recorded as
a finding for identity (concept §10). The link is composed on identity's side —
staff never learns the URL format.

**3b. The TTL follows the channel.** `ProvisionAccountCommand.handed_over` picks
`handover_link_ttl` (Settings `handover_link_ttl_hours`, default **168**) or
`invitation_ttl` (72h). The 2.5 concept separated invitation from reset because
they are different risk windows; a link handed on paper and used days later is a
third one. A longer window makes the dead end of a lost link rarer; it does not
close it (see Neutral).

**4. staff writes the link between the two.** `CreateLoginForEmployeeUseCase`
runs, in this order: staff guards (record exists; not already linked; not
terminated) → `provision_employee_login` → `employees.update(link_login(user_id))`
→ deliver (`send_login_invitation` or return). Guards run **before** identity is
touched so a request staff would always refuse never leaves a pending account
behind; the write runs **before** delivery so the most likely failure (the
e-mail) leaves an account that is **linked** and recoverable through reset.

**5. The secret is handled as a secret.** `setup_link` is `repr=False` in every
DTO that carries it (`ProvisionedAccountResult`, `ProvisionedLogin`,
`EmployeeLoginResult`); staff never persists it, never logs it, never puts it
in an exception message; the `RequestValidationError` handler with constant body
(2.5 D6) already prevents the framework from echoing request bodies.

## Alternatives considered

### Alternative A — literal provisional password via `CreateUserUseCase`
- **Description:** the manager types a password in the request body; identity
  creates a usable account; "forced change" becomes a finding for an identity
  hardening Stage (`must_change_password` + login enforcement + migration).
- **Pros:** zero change in identity; consumes exactly what the roadmap lists.
- **Cons:** the manager **knows** the employee's password (the property 2.5
  built the invitation flow to avoid); the mandatory change of `workforce.md`
  §3.8 becomes a declared gap; a plaintext password field enters staff's HTTP
  boundary.
- **Why rejected:** weaker security for the same UX, and it re-opens a question
  2.5 closed.

### Alternative B — full `must_change_password` in identity
- **Description:** `User.must_change_password`, migration, `authenticate`
  signals/blocks, a change-password route, staff's route sets the flag.
- **Pros:** faithful to the domain doc's wording.
- **Cons:** an identity Stage's worth of work — entity change, **schema
  migration**, login enforcement, a change-password route, e2e — inside a staff
  Stage estimated S (the chosen option also touches identity, but at the
  application level and one VO rule, with no schema, entity or port change —
  concept §5.13); and the outcome is **weaker** than the pending account — the
  manager still knows the first password.
- **Why rejected:** more scope for a worse property.

### Alternative C — e-mail invitation only in this Stage
- **Description:** the in-hand path becomes its own Stage later.
- **Pros:** smallest scope.
- **Cons:** contradicts the kickoff decision ("both paths, the manager chooses
  per employee") and `workforce.md` §3.8; the pilot's staff includes people
  without reliable e-mail.
- **Why rejected:** drops half the DoD.

### Alternative D — one identity operation with a `delivery` flag (provision + send inside)
- **Description:** `ProvisionAccountUseCase(delivery=EMAIL|HANDOVER)` sends
  when asked and returns the link otherwise; staff calls it once.
- **Pros:** one call, one operation.
- **Cons:** staff cannot write `user_id` before the e-mail is sent; an e-mail
  failure leaves an **unlinked** pending account whose e-mail is now taken. In
  the chosen design the retry UX is the same (500, then 409 on retry — the
  record is already linked), but the account is **linked and visible** in R06
  and recoverable through the public reset; here the only recovery would be a
  "link existing login" capability that does not exist. It also folds two
  intentions (make an account; deliver a credential) into one operation.
- **Why rejected:** the separation is what makes the failure story recoverable
  with tools that already exist (public reset).

### Alternative E — do nothing (no in-hand path, no pending account)
The Stage's DoD is the login link. Not acceptable.

## Consequences

### Positive
- The manager never knows, transports or types an employee's password — the
  property 2.5 fought for extends to the in-hand path.
- "Mandatory change" is enforced by **construction**, with zero code in the
  login path.
- Both channels share one credential mechanism; a QR code and a profile
  completion step (sponsor's fuller description) are **presentation** over the
  same link, deferred as findings.
- `SendInvitationUseCase` and `ProvisionAccountUseCase` are the bricks the
  "resend invitation" finding of 2.5 will use.

### Negative
- Rule 1 of the 2.5 concept is **no longer absolute**: one operation returns the
  secret and one route in one channel exposes it. The domain of the exception
  is written here and pinned by CA14 of the concept (the link appears **only**
  where the channel says, and nowhere in `employees`).
- identity's application layer grows three use cases, a shared helper and a
  facade inside a staff Stage — the second declared expansion into identity
  (the first was 3.4, ADR 3.4.0006/0008), authorized explicitly by the sponsor
  (concept §13 Q6, which also weighed and declined a separate identity Stage).
- The link in the 201 body is a secret in transit through the manager's client
  and whatever channel they use to hand it over (WhatsApp, paper, QR). Accepted
  as the meaning of "handed in person"; mitigated by single use and TTL.

### Neutral / trade-offs accepted
- The in-hand link uses its **own** TTL (168h default, configurable), the
  e-mailed one the invitation TTL (72h): same credential, different courier,
  different window.
- **A lost or expired in-hand link is a dead end for a person without a working
  e-mail** — the public reset sends e-mail. Re-issuing is only safe for a
  **pending** account (for an active one it would be a manager resetting an
  employee's password), and identity cannot tell the two apart today
  (`unusable_hash` is random per account — ADR 2.5.0004 law 2 — and expired
  tokens are purged). Safe re-issue needs a "pending" signal in identity
  (column + migration); deferred as a finding with that design (concept §10,
  §13 Q5). Declared, not softened.
- An employee without an e-mail address still needs one as the login
  identifier (kickoff #2: global unique e-mail login). Declared, not solved.
- A residual orphan window remains (`update` failing after provisioning;
  `tokens.add` failing after `users.add`) — the same class the 2.5 accepted,
  narrowed by ordering, declared in concept §6.4, recovery deferred to the
  "link existing login" finding.

## Implementation notes

- `ProvisionAccountUseCase` keeps `InviteUserUseCase`'s check order verbatim
  (global uniqueness → `platform_admin` **with** `unit_ids` → restaurant →
  build → units); the 2.5 precedence test is replicated (CA15).
- Link and message composition live in `_invitation.py`; `InviteUserUseCase`,
  `RequestPasswordResetUseCase`, `ProvisionAccountUseCase` and
  `SendInvitationUseCase` call it — `grep "definir-senha" src/` returns one
  file (CA17); the invitation and reset e-mails stay byte-identical (CA16).
- The staff request has **no** identifier in its body (`email`, `delivery`), so
  the 3.6 boundary identifier validator does not apply to it; `email` is
  validated by identity's `Email` VO through the facade and translated by the
  gateway (L-IG2). The VO gains a NUL-byte rejection in this Stage (concept
  §7 D8) — without it a well-formed address containing `\x00` reaches Postgres
  and turns into a 500.
- `setup_link` is `repr=False` on `ProvisionedAccountResult`,
  `ProvisionedAccount`, `ProvisionedLogin` and `EmployeeLoginResult`; staff's
  CA14 asserts the token value appears nowhere in staff's tables or logs.

## References
- `docs/stages/3.5-employee-login-link/concept.md` §3, §5.4, §5.8, §6.4,
  §7 D2, §13 Q1, CA03, CA09, CA14, CA15, CA16, CA22, CA23
- `docs/stages/2.5-email-invite/concept.md` §1 (invite ≠ create), §5 rules 1,
  12, 13; §7 D5; §13 (resend finding)
- ADR 2.5.0002 (dedicated single-use setup token), ADR 2.5.0004 (unusable hash
  for pending accounts), ADR 2.5.0003 (setting the password revokes sessions)
- `docs/overview.md` §3; `docs/domain/staff/workforce.md` §3.8 (dated note
  added at Stage close)
- Kickoff decisions #2 and the derived "both paths" decision (memory
  `loop-kickoff-decisions-2026-07`)

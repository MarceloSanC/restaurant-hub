---
title: ADR 2.5.0003 — Setting a password revokes every session of that user
description: Architecture Decision Record
when-use: Reference when adding any other password-changing path (self-service change, admin reset), or when deciding whether a security event should revoke sessions
keywords: [adr, password, session, revocation, reset, account-takeover, identity, security]
status: accepted
created_at: 2026-07-20
updated_at: 2026-07-20
adr_id: "2.5.0003"
decision: set_password_with_token revokes all of the user's refresh sessions and invalidates all of the user's remaining setup tokens, so that a password reset actually evicts whoever held the previous credential.
context_stage: 2.5-email-invite
bounded_context: identity
---

# ADR 2.5.0003 — Setting a password revokes every session of that user

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.5 introduces the first path that changes an existing user's password:
`set_password_with_token`, reached from a password-reset e-mail.

The primary reason a person resets a password is that someone else may have it.
If the reset leaves the previous refresh sessions alive, the attacker keeps
access indefinitely — refresh tokens rotate and renew, so their lifetime is
effectively unbounded (see the `[finding]` from 2.4 about the absence of an
absolute session cap). The reset would then be theatre: the victim changes a
secret the attacker no longer needs.

`SessionRepository.revoke_all_for_user` already exists — ADR 2.2.0001 built it
precisely so that a server-side event can cut access for real, rather than
waiting for a JWT to expire on its own.

## Decision

`SetPasswordWithTokenUseCase`, after successfully consuming the token and
**before** writing the new hash (see the ordering paragraph below), performs two
evictions:

1. `sessions.revoke_all_for_user(user_id, now)` — every refresh session dies.
2. `tokens.invalidate_all_for_user(user_id, now)` — every other outstanding setup
   token of that user dies.

Both are needed. A live session and a pending invitation link are the two ways
the previous access survives a password change; closing one and leaving the other
open closes nothing. The second eviction is deliberately **not** scoped by
`SetupTokenPurpose`: a stale invitation token, issued days earlier with a long
TTL, must not survive to redefine the password after the account is active.

**The two evictions run before the password is written**, not after. There is no
unit of work spanning the four repository calls on this plan (the 2.4 stage
escalated a `[finding]` about atomicity, targeted at 4.4). With the evictions
first, every partial failure leaves the account *less* accessible: the worst case
is a burned token, revoked sessions and an unchanged password, from which the
user recovers by requesting another reset. With the naive order — password first —
a transient failure in `revoke_all_for_user` would leave the attacker's session
alive *after* a completed reset, which is precisely the hole this ADR closes,
reachable by a dropped connection. Ordering buys the guarantee that a transaction
would otherwise be needed for.

The access token is **not** revoked, and cannot be: it is a signed JWT with no
introspection on this plan. Its residual window is the configured
`access_token_ttl_minutes` (15 by default) — the same window the sponsor already
accepted on 2026-07-19 as the system's revocation latency. This ADR does not
change that trade; it inherits it.

## Alternatives considered

### Alternative A — Keep sessions alive after a password change
- **Description:** change the credential, leave existing sessions untouched.
- **Pros:** the legitimate user is not logged out of their other devices.
- **Cons:** an attacker holding a refresh token keeps access forever; the reset
  does not restore control of the account. This is the exact hole ADR 2.2.0001 was
  written to close, reopened at the one moment it matters most.
- **Why rejected:** it makes the account-recovery flow non-recovering.

### Alternative B — Revoke all sessions except the one making the request
- **Description:** the common "keep me signed in here" behaviour.
- **Pros:** better ergonomics for a self-service password change.
- **Cons:** meaningless here — `set_password_with_token` is reached by an
  **unauthenticated** request carrying only the e-mailed token. There is no
  current session to preserve, so the exception has no referent.
- **Why rejected:** not applicable to this stage's flow. It becomes a real option
  when an authenticated self-service password change is added; that stage may
  revisit this ADR.

### Alternative C — Revoke on reset, but not on invitation acceptance
- **Description:** discriminate by `SetupTokenPurpose`.
- **Pros:** slightly fewer writes on the invitation path.
- **Cons:** an invited user has no sessions to revoke, so the "saving" is a no-op
  call, while the branch adds a purpose-dependent security rule that a future
  reader must reason about. Rules that are conditional on a discriminator are
  where the discriminator eventually gets forgotten.
- **Why rejected:** unconditional is cheaper to keep correct than conditional.

## Consequences

### Positive
- A password reset actually evicts whoever held the previous credential.
- The rule is unconditional, so no future caller can reach the password write
  while skipping the eviction — and, because the evictions run first, no partial
  failure can reach the password write while skipping them either.
- Reuses an existing port method; no new contract surface for the session side.

### Negative
- A user who resets their password is signed out of every device, including the
  ones they trust. Accepted: someone who just proved control of their mailbox can
  sign in again.
- Up to `access_token_ttl_minutes` of residual access via a still-valid access
  token. Inherited from the 2026-07-19 sponsor decision, not introduced here.

### Neutral / trade-offs accepted
- Two extra writes on a path that runs rarely.

## References
- `docs/adr/2_2_0001-revocable-refresh-session-port.md`
- `docs/stages/2.4-identity-http/technical.md` §7 — `[finding]` absolute session cap
- GitHub issue #27, "Cuidados de segurança"
- `docs/stages/2.5-email-invite/concept.md` §5 regra 4, §7 D3
</content>

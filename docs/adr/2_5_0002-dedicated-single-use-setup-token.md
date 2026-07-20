---
title: ADR 2.5.0002 — Password setup tokens use a dedicated, persisted, single-use mechanism
description: Architecture Decision Record
when-use: Reference before reusing TokenIssuer for anything other than session tokens, before changing the setup token lifecycle, or when adding a new out-of-band token flow
keywords: [adr, token, invitation, password-reset, single-use, replay, identity, security]
status: accepted
created_at: 2026-07-20
updated_at: 2026-07-20
adr_id: "2.5.0002"
decision: Invitation and password-reset tokens get their own SetupTokenIssuer port and their own persisted password_setup_tokens table with an atomic conditional consume, instead of reusing the session TokenIssuer or deriving a stateless token from the current password hash.
context_stage: 2.5-email-invite
bounded_context: identity
---

# ADR 2.5.0002 — Password setup tokens use a dedicated, persisted, single-use mechanism

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.5 needs a token that travels by e-mail, lets an unauthenticated person
set a password, and dies after one use.

The codebase already has an opaque token persisted by fingerprint: the refresh
token (ADR 2.2.0001). It is tempting to reuse `TokenIssuer.issue_refresh_token()`
— the shape is identical (opaque value + fingerprint). Issue #27 flags this
explicitly: *"reusing a session token as an invitation token is a vulnerability,
not an economy."*

The two tokens differ on every axis that matters:

| | refresh token | setup token |
|---|---|---|
| lifetime | days/weeks, renewed on rotation | hours, fixed |
| consumption | **rotated** (old revoked, new issued) | **consumed** once, never reissued |
| delivery | HTTPS response body to an authenticated client | e-mail, out of band |
| holder | someone who already authenticated | someone who never has |
| revocation trigger | logout, reuse detection, dismissal | password set, new token issued, expiry |

Single use is the hard requirement, and it is the requirement that decides the
shape: a token that cannot be marked as spent is not single use.

## Decision

1. **A dedicated port**, `SetupTokenIssuer`, in
   `features/identity/application/ports/out/setup_token_issuer.py`, with
   `issue() -> IssuedSetupToken` and `fingerprint(value) -> str`, obeying the same
   law as `TokenIssuer`: `issuer.fingerprint(t.value) == t.fingerprint`.
2. **A dedicated persisted record**, `PasswordSetupToken`, in a dedicated table
   `password_setup_tokens`, storing **only the fingerprint** — never the value,
   exactly as `sessions` does.
3. **Single use is enforced by an atomic conditional transition.**
   `PasswordSetupTokenRepository.consume(token_id, consumed_at) -> bool` returns
   `True` only if it moved `consumed_at` from NULL to a value. In Postgres this is
   `UPDATE ... SET consumed_at = :now WHERE id = :id AND consumed_at IS NULL`, and
   the boolean is the affected-row count. The use case treats `False` as
   `InvalidSetupTokenError`.
4. **Consume happens before the password is written.** Inverting the order would
   let a replay that loses the consume race still have written the attacker's
   password.
5. **Issuing** a new token invalidates that user's outstanding tokens **of the
   same purpose only**, so re-inviting leaves exactly one live invitation and
   re-requesting a reset leaves exactly one live reset. Scoping by purpose here is
   not tidiness: without it, anyone on the internet could kill any victim's pending
   invitation in a loop through the *public* reset route, indefinitely.
   **Redeeming** a token, by contrast, invalidates the user's tokens of *every*
   purpose — see ADR 2.5.0003.

## Alternatives considered

### Alternative A — Reuse `TokenIssuer.issue_refresh_token()` and the `sessions` table
- **Description:** treat an invitation as a session with a special flag.
- **Pros:** no new port, no new table, no migration.
- **Cons:** the `sessions` semantics are rotation-based and explicitly *not*
  single-use; `SessionRepository.revoke` is documented as idempotent-preserving,
  which is the opposite of the conditional transition needed here. A `purpose`
  flag on `sessions` would make every session query carry a discriminator, and any
  code path that forgot it would treat an invitation as a login session — which is
  precisely the privilege confusion issue #27 warns about.
- **Why rejected:** overloading a table with two lifecycles makes the dangerous
  case (invitation accepted as session credential) representable.

### Alternative B — Reuse only the crypto (`TokenIssuer`), with a separate table
- **Description:** keep the new table, but call `issue_refresh_token()` for material.
- **Pros:** one fewer small adapter; "all token crypto in one port" is that port's
  stated purpose.
- **Cons:** it couples the invitation token's material to the session token's
  material. A future change to refresh-token crypto (e.g. moving to RS256 or
  changing the fingerprint derivation, both anticipated by ADR 2.4.0002) would
  silently change invitation tokens too, invalidating in-flight invites with no
  test pointing at the cause. The saving is roughly twenty lines.
- **Why rejected:** the coupling is invisible and the saving is negligible.

### Alternative C — Stateless token bound to the current password hash (Django style)
- **Description:** sign `(user_id, purpose, expires_at)` with an HMAC keyed partly
  by the user's current password hash; setting a password changes the hash and
  therefore kills the token. No table, no migration.
- **Pros:** genuinely simpler on the persistence axis; single use falls out of the
  binding; well-known design (Django's `PasswordResetTokenGenerator` uses
  `user.password` and `last_login` in the hash).
- **Cons:** three real ones. (a) The token's validity becomes coupled to KDF
  internals — rehashing users with new argon2 parameters, an ordinary security
  maintenance action, silently invalidates every in-flight invite. (b) There is no
  way to **kill** a mis-sent invitation before it expires, which is exactly the
  revocability argument ADR 2.2.0001 made for sessions. (c) It requires reading the
  stored password hash on a pre-authentication path and a new
  `find_credentials_by_id` on `UserRepository`, so it is not free either.
- **Why rejected:** (b) is decisive — an unrevocable credential sent over e-mail
  repeats the mistake ADR 2.2.0001 exists to correct.

## Consequences

### Positive
- Replay is impossible rather than improbable: the guarantee is a database
  transition, not an application-level check-then-act.
- A mis-sent invitation can be killed (issue a new one, or purge).
- Refresh tokens and setup tokens cannot be confused: different type, different
  port, different table, different verb.
- `purge_expired` mirrors `sessions`, so retention policy stays the caller's
  (ADR 2.3.0004) and the operational shape is already familiar.

### Negative
- One extra table, one migration, one adapter, one fake, plus contract tests —
  roughly four of the stage's tasks.
- The stage now touches persistence, which the roadmap's file list for 2.5 did not
  enumerate. This is declared as divergence #1 in `concept.md` §1 ("Divergências
  declaradas em relação ao bloco do roadmap"), following the precedent the 2.4
  stage recorded; the dated note on `roadmap.md` itself lands with the stage's
  closing commit. The roadmap's DoD (single-use token) is unreachable without it.
- Single use requires an atomicity guarantee that only the real database provides,
  so the contract test alone is not sufficient evidence — a concurrency test
  against real Postgres is required (concept CA9b). Without it, a
  `SELECT`-then-`UPDATE` adapter satisfies every sequential test and still loses
  the race in production, which would make this ADR's central claim decorative.

### Neutral / trade-offs accepted
- Two token TTLs to configure (invitation long, reset short) instead of one.

## References
- `docs/adr/2_2_0001-revocable-refresh-session-port.md` (revocability argument)
- `docs/adr/2_3_0003-add-is-insertion-not-upsert.md`, `2_3_0004-session-retention-and-purge.md`
- `docs/adr/2_4_0002-decode-extends-token-issuer.md` (anticipated crypto changes)
- GitHub issue #27, "Decisões herdadas" and "Cuidados específicos"
- `docs/stages/2.5-email-invite/concept.md` §4, §5, §7 D2
</content>

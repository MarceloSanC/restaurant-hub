---
title: ADR 2.2.0001 — Persisted, revocable refresh session as its own out port
description: Architecture Decision Record
when-use: Reference whenever revisiting how refresh tokens are stored, rotated or revoked, or before adding session state to the token issuer
keywords: [adr, identity, session, refresh-token, revocation, port, lgpd]
status: accepted
created_at: 2026-07-18
updated_at: 2026-07-18
adr_id: "2.2.0001"
decision: Model the refresh session as a SessionRepository out port separate from TokenIssuer, storing only a fingerprint of the refresh token plus expiry and revocation timestamps.
context_stage: 2.2-identity-application
bounded_context: identity
---

# ADR 2.2.0001 — Persisted, revocable refresh session as its own out port

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Kickoff decision #1 (2026-07-16, recorded in issue #20) settled the session model
for the platform: **JWT access token + a refresh token that is persisted and
rotated** (a session table), so that logout and employee termination actually cut
access. The driver is concrete and legal, not aesthetic: schedule data is
sensitive personal data under the LGPD, and a purely stateless JWT scheme cannot
revoke anything before the token's own expiry.

Stage 2.2 is the application layer of BC `identity`. It owns no technology — it
publishes the **out ports** that Stage 2.3 (Postgres repositories) and Stage 2.4
(HTTP, argon2, JWT) will implement. Forces:

- **Adapter boundary.** Issuing/signing a token is cryptography, implemented by
  the security adapter in 2.4. Storing a session row is persistence, implemented
  by the Postgres adapter in 2.3. These are different technologies, different
  Stages, different failure modes.
- **Port shape is the expensive decision here.** Two later Stages implement these
  contracts; reshaping a port after 2.3 and 2.4 exist breaks both.
- **Project decision criterion** (overview §4 + ADR 0.0.0004 §Decision #4):
  install the scalable skeleton with a minimal implementation inside; do not take
  the shortcut that forces reshaping later, and do not overengineer.
- **Roadmap scope.** The `contratos_introduzidos` block for Stage 2.2 lists five
  ports and does not mention a session port; issue #20 — later, and operative for
  this Stage — explicitly instructs evaluating it and recording the outcome in an
  ADR. The extension is additive, not contradictory.
- **Secret handling.** A refresh token is bearer material. Storing it verbatim
  means a database leak is an immediate account-takeover of every live session.

## Decision

The refresh session is modelled as a **dedicated out port**,
`SessionRepository`, separate from `TokenIssuer`:

```python
class SessionRepository(Protocol):
    def add(self, session: Session) -> None: ...
    def find_by_fingerprint(self, fingerprint: str) -> Session | None: ...
    def revoke(self, session_id: SessionId, revoked_at: datetime) -> None: ...
    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None: ...
```

It traffics in a frozen `Session` record — `id`, `user_id`,
`refresh_token_fingerprint`, `issued_at`, `expires_at`, `revoked_at | None` — with
a single pure predicate, `is_active(now)` (true iff `revoked_at is None and
now < expires_at`; half-open, so `now == expires_at` is already expired).

The record deliberately has **no** revocation method. Revoking is a port
operation, not a DTO operation: there is no `save(session)` in the contract, so a
`Session` "revoked in memory" would have no path back to storage, and a method
producing one would be dead code that invites the fake and the real adapter to
disagree. `revoke` and `revoke_all_for_user` are silent for an unknown id and **idempotent in
the strong sense**: re-revoking an already-revoked session is a no-op that
**preserves the original `revoked_at`** rather than overwriting it. Without that
precision, the fake and the 2.3 adapter can diverge observably, and the forensics
of a token-reuse incident lose the instant of the first revocation.

`find_by_fingerprint` is normatively **non-filtering**: it returns the session
even when revoked or expired, and the caller decides via `is_active(now)`. This is
what makes refresh-token *reuse* detectable in 2.4 — if the port silently returned
`None` for a revoked session, a replayed (already-rotated) token would be
indistinguishable from a forged one, and the standard response of revoking the
victim's whole session family would be unreachable.

The stored value is a **fingerprint**, never the refresh token itself. All token
material — generating the opaque refresh value and deriving its fingerprint — sits
behind `TokenIssuer`, which returns `IssuedRefreshToken(value, fingerprint)` and
exposes `fingerprint(value)` for later lookup. The application layer therefore
never hashes, signs, or generates secret material itself.

`authenticate_user` creates and persists exactly one active session per successful
login. The two revocation methods map to the two scenarios the kickoff named:
`revoke` is logout, `revoke_all_for_user` is termination. The rotation
flow (find by fingerprint → revoke old → add new) is expressible with this port
today; the use case that orchestrates it belongs to Stage 2.4, next to the
`POST /auth/refresh` endpoint the roadmap allocates there.

## Alternatives considered

### Alternative A — Stateless JWT refresh, no persistence
- **Description:** issue a long-lived signed refresh JWT; validate by signature only.
- **Pros:** no table, no repository, no extra port; trivial to implement.
- **Cons:** cannot revoke before expiry — logout is cosmetic and a terminated
  employee keeps access to schedule data until the token lapses.
- **Why rejected:** directly contradicts kickoff decision #1 and the LGPD driver
  behind it. This is the shortcut the project criterion warns against: adding
  revocation later means introducing the table, the port, and the adapter anyway,
  after two Stages have already been written against the stateless shape.

### Alternative B — One combined `TokenService` port (issue + store + revoke)
- **Description:** a single port owning both token cryptography and session persistence.
- **Pros:** one dependency in the use case; the "session" concept lives in one place.
- **Cons:** forces one adapter to depend on both JWT and Postgres, splitting it
  across Stages 2.3 and 2.4 with no clean owner; makes the port untestable without
  both technologies; violates the adapter boundary that the two Stages are
  organised around.
- **Why rejected:** it collapses two genuinely different concerns that this
  project has already decided to implement in two different Stages with two
  different technologies.

### Alternative C — Store the refresh token verbatim
- **Description:** persist the refresh token value and compare on lookup.
- **Pros:** marginally simpler — no fingerprint concept.
- **Cons:** a database dump hands over every live session; comparison also
  invites non-constant-time equality.
- **Why rejected:** unacceptable secret handling for no meaningful simplification.
  The fingerprint costs one extra field and one port method.

### Alternative D — Rich session entity now (device, IP, user agent, last_seen)
- **Description:** model the full session audit record in this Stage.
- **Pros:** ready for device management and "log out other devices" UX.
- **Cons:** overengineering against overview §4; commits to a shape before any
  requirement exists; every field becomes a column 2.3 must migrate.
- **Why rejected:** the minimal record already supports both named scenarios, and
  adding fields later is additive — no reshape of the port.

### Alternative E — Do nothing / defer the port to Stage 2.3
- **Description:** ship 2.2 with `TokenIssuer` only; let the persistence Stage
  invent the session contract.
- **Pros:** keeps the roadmap's contract list literal.
- **Cons:** ports are the application layer's responsibility, not the adapter's
  (LAYOUT §5, `hex-arch-python`). 2.3 would either define an out port from inside
  the adapter layer, or 2.4 would find `authenticate_user` unable to issue a
  revocable refresh token and have to reopen this Stage.
- **Why rejected:** it defers the single most expensive decision of the Stage past
  the point where two Stages depend on it — and issue #20 explicitly asks for it here.

## Consequences

### Positive
- Logout and termination are implementable without touching the application layer
  again: the port already carries both revocation shapes.
- Token cryptography and session storage stay in the Stage (and adapter) that owns
  each — 2.4 and 2.3 respectively.
- A database leak does not yield usable refresh tokens.
- `Session` maps 1:1 to the table 2.3 will create, with `tenant_id` isolation
  reached through `user_id` (ROADMAP-3).

### Negative
- Every login writes a row — refresh becomes stateful, and the session table
  needs a cleanup policy for expired rows (not in this Stage; flagged for 2.3).
- One more port for 2.3 to implement and for the composition root to wire.
- **Residual access window — the honest limit of "cuts access".** Revocation
  invalidates the *refresh* token. An access token already issued stays
  cryptographically valid until its own `expires_at`, because nothing validates it
  against the session on each request. So logout and termination cut access after
  at most `access_token_ttl`, not instantly. `AccessTokenClaims` therefore carries
  `session_id`, so a future introspection check in 2.4 can close the window
  without reshaping this port — but that check does not exist yet. Keeping
  `access_token_ttl` short (minutes) is what bounds the exposure, and 2.4 owns
  that configuration.

### Neutral / trade-offs accepted
- The rotation use case is deferred to 2.4. The port supports it, and this Stage
  ships no *production* consumer for `find_by_fingerprint`/`revoke*` — deliberate
  skeleton-with-minimal-implementation, recorded as a `[finding]` pointing at 2.4.
  The three methods are nonetheless covered by tests that pin their normative
  semantics against the fake (concept CA16), so 2.3 implements against a specified
  contract rather than an empty one.
- **Roadmap reconciliation.** This port lands in three roadmap blocks that do not
  mention it: 2.2 (`contratos_introduzidos`), 2.3 (no `session_repository.py`, no
  session table) and 2.4 (no `refresh_session.py` use case). Issue #20 authorizes
  the port for 2.2; the other two are direct consequences. All three are
  reconciled with a dated note at Stage close — see concept §7.8.
- `Session` lives in `application/dtos/` rather than in the domain: 2.1 is closed
  and this Stage targets the application layer. It carries only pure predicates,
  so promoting it to a domain entity later is a move, not a redesign.
- The fingerprint algorithm is unspecified here on purpose — it is the security
  adapter's choice in 2.4 (a SHA-256 digest of a high-entropy value is the
  expected implementation, since the input is not low-entropy like a password).

## Implementation notes

- `authenticate_user` must persist the session **only after** credential
  verification succeeds; a failed login writes nothing.
- `expires_at = clock.now() + refresh_token_ttl`, with the TTL injected into the
  use case (LAYOUT §3 forbids reading `Settings` from `application`).
- `AuthenticationResult` carries the refresh token **value**; the `Session` carries
  only the fingerprint. A test asserts the value never reaches the repository.

## References

- Related ADRs: [`2_2_0002-authorization-two-axes-fail-closed.md`](./2_2_0002-authorization-two-axes-fail-closed.md),
  [`2_2_0003-application-errors-in-identity-hierarchy.md`](./2_2_0003-application-errors-in-identity-hierarchy.md),
  [`2_1_0002-platform-admin-without-tenant.md`](./2_1_0002-platform-admin-without-tenant.md)
- Concept: [`../stages/2.2-identity-application/concept.md`](../stages/2.2-identity-application/concept.md) §4, §7.1
- Kickoff decisions: issue #20 body; ADR 0.0.0004 §Authorized runs
- Roadmap: Stage `2.3-identity-persistence` (repositories), Stage `2.4-identity-http` (`jwt_issuer`)

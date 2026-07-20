---
title: ADR 2.4.0002 — Access-token verification extends the existing TokenIssuer port instead of introducing a separate verifier port
description: Architecture Decision Record
when-use: Reference before adding a token-related method to an identity port, or when splitting issuing from verifying (e.g. moving to asymmetric keys or an external gateway)
keywords: [adr, port, token-issuer, jwt, decode, verification, interface-segregation, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.4.0002
decision: Add decode_access_token to the existing TokenIssuer out-port rather than create a separate AccessTokenVerifier port, because issuing and verifying share the secret and algorithm and splitting them would create two configuration points that can silently diverge
context_stage: 2.4-identity-http
bounded_context: identity
---

# ADR 2.4.0002 — `decode_access_token` extends `TokenIssuer`

## Status

`accepted`

## Context

The HTTP guard introduced in Stage 2.4 must turn an `Authorization: Bearer <jwt>`
header into an actor identity before any use case runs. That requires **verifying**
a token: checking the signature, checking expiry, and reading the claims.

Nothing in the codebase can do this today. `TokenIssuer` (Stage 2.2) only issues:
`issue_access_token`, `issue_refresh_token`, `fingerprint`. Its module docstring
states the port's purpose in strong terms — it "concentra **toda** a criptografia de
token" and "a aplicação nunca assina, gera segredo nem hasheia por conta própria".

The guard lives in `adapters/in/http/dependencies.py`. An inbound adapter may depend
on application ports, but it must not do cryptography itself, and it must not import
another adapter (LAYOUT §3).

Forces:

- Interface Segregation argues for a narrow port: a consumer that only verifies
  should not depend on an interface that also issues.
- Configuration cohesion argues the opposite: with HS256, issuing and verifying use
  **the same secret and the same algorithm**. Two ports means two wirings of the
  same two values.
- Every fake and every real implementation must be kept in lockstep; the project
  already gates that with `mypy` over `tests/fakes/` and a `_conforms: <Port> = Fake()`
  declaration per fake.

## Decision

Add to the existing `TokenIssuer` protocol:

```python
def decode_access_token(self, token: str) -> AccessTokenClaims: ...
```

Contract:

- Verifies signature **and** expiry before returning anything.
- Raises `InvalidAccessTokenError` for **every** failure mode — bad signature,
  malformed token, expired, unknown algorithm, missing or unparseable claim.
- **Never** returns claims for a token that failed verification. There is no
  "decode without verifying" variant on the port, because such a method is the
  classic footgun: a caller reaches for it "just to read the subject" and skips
  verification entirely.

`FakeTokenIssuer` implements it symmetrically with `issue_access_token`, honouring
the same round-trip law style already used for `fingerprint`.

## Alternatives considered

### Alternative A — a new `AccessTokenVerifier` port
- **Description:** a separate out-port with only `decode_access_token`, implemented
  by the same JWT adapter.
- **Pros:** textbook Interface Segregation; a future deployment where a gateway
  verifies with a public key while only the auth service signs would map cleanly.
- **Cons:** the secret and the algorithm would be wired in two places, and nothing
  would force them to agree. A mismatch produces "every token is invalid" — which
  looks like an auth bug, not a config bug, and both halves look correct in
  isolation. It is the same failure class the `fingerprint` law in Stage 2.2 was
  written to prevent.
- **Why rejected:** the segregation buys nothing today (one implementation, one
  consumer) and costs a real, hard-to-diagnose failure mode. The split remains cheap
  to do later, when asymmetric keys actually arrive — it is a port extraction, not a
  redesign.

### Alternative B — decode inside the HTTP adapter
- **Description:** `dependencies.py` calls PyJWT directly.
- **Pros:** no port change at all.
- **Cons:** puts the JWT secret and algorithm into an inbound adapter, contradicting
  the `TokenIssuer` docstring and scattering token cryptography across two layers;
  swapping JWT for opaque tokens would then require editing the HTTP layer.
- **Why rejected:** breaks the port's stated reason to exist.

### Alternative C — the guard calls a use case that decodes
- **Description:** a `VerifyAccessTokenUseCase` wrapping the port.
- **Pros:** the adapter touches only use cases.
- **Cons:** a use case with no orchestration, no policy and one delegated call —
  pure ceremony. `AuthorizeActionUseCase` is already the policy step that follows.
- **Why rejected:** adds a layer without adding a decision.

## Consequences

### Positive
- All token cryptography stays behind one port, as designed in Stage 2.2.
- One secret, one algorithm, one wiring — issuing and verifying cannot drift.
- Swapping JWT for opaque tokens plus server-side lookup is a single adapter change.

### Negative
- `TokenIssuer` now has four methods and two responsibilities in the strict ISP
  reading. A consumer that only verifies still depends on the issuing surface.
- The port is extended after being merged in Stage 2.2, so the fake, the type
  conformance declaration and the contract tests all move together. Additive only —
  no existing signature changes.

### Neutral / trade-offs accepted
- If a future deployment separates signing from verifying (asymmetric keys, edge
  gateway), this ADR should be superseded by one that extracts the verifier port.
  The extraction is mechanical; nothing here forecloses it.

## References
- `docs/stages/2.4-identity-http/concept.md` §4, §7.2
- `src/restaurant_hub/features/identity/application/ports/out/token_issuer.py`
- ADR 2.2.0001 (revocable refresh session port), ADR 2.2.0004 (synchronous ports)
- `docs/LAYOUT.md` §3, §5

---
title: ADR 2.4.0004 — Security adapter choices — argon2id via argon2-cffi, HS256 JWT via PyJWT, and an unsalted SHA-256 refresh fingerprint
description: Architecture Decision Record
when-use: Reference before changing a password-hashing parameter, before switching JWT algorithm or library, or when questioning why the refresh fingerprint is an unsalted hash while passwords are salted
keywords: [adr, argon2, argon2id, pyjwt, hs256, jwt, sha256, fingerprint, password-hashing, ttl, configuration, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.4.0004
decision: Use argon2-cffi with argon2id at library defaults for password hashing, PyJWT with HS256 for access tokens, a 256-bit secrets.token_urlsafe value with an unsalted SHA-256 fingerprint for refresh tokens, and keep both token TTLs in Settings rather than as literals
context_stage: 2.4-identity-http
bounded_context: identity
---

# ADR 2.4.0004 — Security adapter parameters

## Status

`accepted`

## Context

Stage 2.4 implements the two security ports that Stage 2.2 declared and left
unimplemented. These are the project's first real cryptographic choices; until now
only deterministic fakes existed (`hashed::<senha>`, `fp::<value>`).

Constraints already fixed elsewhere:

- ROADMAP-4 mandates JWT access + refresh and argon2 hashing.
- ADR 2.2.0001: the database stores the refresh token's **fingerprint**, never its
  value; a database dump must not yield a usable token.
- `TokenIssuer`'s law: `issuer.fingerprint(t.value) == t.fingerprint`.
- `PasswordHasher`'s two laws: `verify` never raises, and `dummy_hash()` returns a
  **valid** hash with production cost parameters that `verify` always rejects.
- The sponsor (2026-07-19) fixed a 15-minute access TTL and required it be
  **configuration**, not a hard-coded constant.

## Decision

### Password hashing — `argon2-cffi`, argon2id, library defaults

`argon2-cffi`'s `PasswordHasher` with default parameters. argon2id is the OWASP
Password Storage Cheat Sheet's first recommendation, and `argon2-cffi` is the
reference CFFI binding to the reference C implementation. Defaults are used rather
than hand-tuned values because a wrong hand-tuned cost is worse than a maintained
default, and the library tracks the current recommendation across releases.

Port laws are honoured in the adapter:

- `verify` catches `VerifyMismatchError`, `InvalidHashError` and
  `VerificationError` and returns `False`. Letting them escape would turn "wrong
  password" into a 500.
- `dummy_hash()` returns a hash of a fixed sentinel string, computed with the same
  parameters, so the account-enumeration defence in `AuthenticateUserUseCase` pays
  the real KDF cost. It is computed **once per adapter instance**, not per call:
  recomputing it per login would double the cost of the failure path and reintroduce
  the timing signal from the other side.

Argon2's own salt is per-hash and embedded in the encoded output; the adapter adds
none.

### Access token — `PyJWT`, HS256

`PyJWT` is the de facto standard Python JWT library and is actively maintained.
`python-jose` was rejected: it has accumulated CVEs and has been sparsely
maintained. `authlib` was rejected as a full OAuth framework where a JWT codec is
needed.

HS256 (symmetric) is chosen because a single service both signs and verifies. RS256
buys key separation that has no consumer today and costs key management; the port
shape (ADR 2.4.0002) makes the switch an adapter-internal change.

`decode` is always called with `algorithms=[configured_algorithm]` — an explicit
allowlist. Passing the decoded header's algorithm back to `decode` is the classic
`alg=none` / algorithm-confusion vulnerability, and PyJWT requires the allowlist
precisely to prevent it.

### Refresh token — 256 bits of randomness, unsalted SHA-256 fingerprint

- Value: `secrets.token_urlsafe(32)` — 32 bytes (256 bits) from the OS CSPRNG.
  Opaque; it carries no claims and is never parsed.
- Fingerprint: `hashlib.sha256(value).hexdigest()` — 64 hex characters, which the
  `Text` column from Stage 2.3 accommodates.

**Why unsalted SHA-256 here, when passwords require a salted slow KDF.** The two
threats are different. Passwords are low-entropy and human-chosen, so an attacker
with the hashes runs a dictionary; salt plus a slow KDF is what defeats that. A
refresh token is 256 bits of uniform randomness — there is no dictionary to run and
no rainbow table that could exist, so a fast hash leaks nothing. And the fingerprint
**must** be deterministic: `find_by_fingerprint` looks up by exact value, so a
per-record salt would make lookup impossible. Using argon2 here would be both slower
and non-functional.

The law `fingerprint(t.value) == t.fingerprint` is honoured **by construction** —
`issue_refresh_token` derives the fingerprint by calling `self.fingerprint(...)`
rather than repeating the formula, mirroring what `FakeTokenIssuer` already does.

### TTLs and secret are configuration

`Settings` gains `access_token_ttl_minutes` (default 15), `refresh_token_ttl_days`
(default 14), `jwt_secret_key` and `jwt_algorithm` (default `HS256`). No `timedelta`
literal appears in a use case or adapter body.

`jwt_secret_key` has an obviously-unsafe development default
(`dev-insecure-change-me`), matching how `database_url` already behaves. Fail-fast
on a default secret in production is **deliberately not** implemented here: the test
suite boots with `debug=false`, so the check would break the suite rather than
production. It is escalated as a finding to `6.2-deploy-pipeline`, where a boot-time
configuration gate belongs.

## Alternatives considered

### Alternative A — `passlib` for hashing
- **Pros:** familiar; multi-scheme with built-in migration support.
- **Cons:** no release since 1.7.4 (2020) and known friction with newer bcrypt
  backends; it would add an abstraction layer over `argon2-cffi`, which the
  `PasswordHasher` port already provides.
- **Why rejected:** the port *is* the abstraction; a second one adds an unmaintained
  dependency for nothing.

### Alternative B — bcrypt instead of argon2
- **Pros:** ubiquitous; ROADMAP-4 lists it as an acceptable option.
- **Cons:** memory-hard argon2id resists GPU/ASIC attack better; bcrypt silently
  truncates input at 72 bytes, which quietly weakens long passphrases.
- **Why rejected:** argon2 is named first in ROADMAP-4 and is the stronger default.

### Alternative C — argon2 for the refresh fingerprint too
- **Pros:** superficially "consistent — hash everything slowly".
- **Cons:** **it does not work**. Argon2 salts per hash, so the digest is not
  reproducible from the value alone, and `find_by_fingerprint` — a lookup by exact
  value — has nothing to look up. It would also make every refresh cost a KDF.
- **Why rejected:** breaks the port contract while protecting against a threat that
  does not apply to a 256-bit random value.

### Alternative D — RS256 with a key pair
- **Pros:** verifiers need only the public key; better fit for multi-service.
- **Cons:** key generation, storage and rotation with no second verifier to justify
  them.
- **Why rejected:** premature. `jwt_algorithm` is configuration and the port hides
  the change, so this is reversible.

## Consequences

### Positive
- Both security ports get maintained, standard implementations, with the port laws
  tested against the real adapter and not only the fake.
- The `algorithms=[...]` allowlist closes algorithm confusion at the only place it
  could enter.
- TTL, secret and algorithm are all configuration, so tuning needs no code change.

### Negative
- argon2 at default cost makes every login and user creation measurably slower; the
  e2e suite pays it. Accepted, and measured during execution.
- Two runtime dependencies added (`argon2-cffi`, `pyjwt`); both must also be listed
  in the `.importlinter` forbidden-module lists, per that file's standing rule that a
  new I/O dependency is added there in the same commit.
- The insecure default secret is a real foot-gun until `6.2-deploy-pipeline` adds the
  boot-time gate. Stated plainly rather than papered over.

### Neutral / trade-offs accepted
- Revoked-then-rotated session rows accumulate; `purge_expired` exists for that and
  its production caller is Step 6 (finding inherited from Stage 2.3).

## References
- `docs/stages/2.4-identity-http/concept.md` §7.4, §10
- ADR 2.2.0001 (refresh session stores fingerprint only)
- `src/restaurant_hub/features/identity/application/ports/out/{password_hasher,token_issuer}.py`
- OWASP Password Storage Cheat Sheet; OWASP JSON Web Token Cheat Sheet
- RFC 8725 (JWT Best Current Practices) §3.1 — explicit algorithm allowlist
- RFC 6819 §5.2.2.3 — refresh token rotation and reuse detection

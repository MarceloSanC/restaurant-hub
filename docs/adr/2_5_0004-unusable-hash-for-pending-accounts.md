---
title: ADR 2.5.0004 — Pending accounts store an unusable random hash, never the timing dummy
description: Architecture Decision Record
when-use: Reference before persisting any placeholder credential, before reusing dummy_hash outside the login timing path, or when adding another "account exists but has no password yet" state
keywords: [adr, password, hash, argon2, invitation, dummy-hash, authentication-bypass, identity, security]
status: accepted
created_at: 2026-07-20
updated_at: 2026-11-09
adr_id: "2.5.0004"
decision: PasswordHasher gains unusable_hash(), a fresh random-seeded argon2 hash with no known preimage, and invited accounts store that instead of dummy_hash() — whose preimage is a literal in this repository and would otherwise become a working password for every pending invite.
context_stage: 2.5-email-invite
bounded_context: identity
---

# ADR 2.5.0004 — Pending accounts store an unusable random hash, never the timing dummy

> ⚠️ **Errata (2026-11-09):** §Context and §Decision 3 — the constant `_SENTINELA_DUMMY` of `identity/adapters/out/security/argon2_hasher.py` was renamed to `_DUMMY_SENTINEL` in issue #136 (pure rename; the literal value is unchanged), and the contract test asserts the law for `_DUMMY_SENTINEL`. Pointer only; no decision content changes — ver issue #136

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.5 creates a user **before** that user has chosen a password. The
`users.password_hash` column is `NOT NULL` (2.3 schema, deliberately: the 1:1
relation with a credential is written in the same transaction as the user), so
something has to go in it.

`PasswordHasher` already advertises exactly the needed thing. Its law 2 reads:

> `dummy_hash()` devolve um hash **válido**, com os mesmos parâmetros de custo da
> produção, contra o qual `verify` sempre falha.

The first draft of this stage's concept relied on that law. **The law is false as
implemented**, and the Checkpoint A reviewers found it independently:

```python
# src/restaurant_hub/features/identity/adapters/out/security/argon2_hasher.py
_SENTINELA_DUMMY = "dummy-password-that-never-authenticates"   # :22
...
self._dummy_hash = PasswordHash(self._backend.hash(_SENTINELA_DUMMY))   # :36
```

`verify` fails for every password *except one*, and that one is a literal in a
source file. The contract test that supposedly proves the law
(`tests/contract/features/identity/test_security_contract.py`) parametrises four
strings and never the sentinel.

Until now this was harmless, and that is the interesting part: `dummy_hash()` was
only ever fed to a `verify` whose result is discarded, on the "e-mail not found"
branch of `authenticate_user`, to equalise response time. A constant nobody
persists has no attack surface. **Persisting it changes its category** — from a
timing artefact into a live credential.

The concrete failure it would have caused: an owner invites `victim@x.com`; before
the victim opens the e-mail, anyone who has read this repository posts
`{"email": "victim@x.com", "password": "dummy-password-that-never-authenticates"}`
to `/auth/login`, `verify` returns `True`, and the API issues a full access +
refresh pair carrying the victim's real role and tenant. No token, no mailbox
access, no rate limit (rate limiting is out of scope for this stage). Every
pending invitation on the platform, simultaneously.

## Decision

1. `PasswordHasher` gains **`unusable_hash() -> PasswordHash`**. The adapter
   derives it from fresh random material (`secrets`) that is discarded
   immediately; nothing anywhere retains a preimage.
2. `InviteUserUseCase` stores `unusable_hash()` as the initial credential.
   `dummy_hash()` keeps its single existing job — equalising login timing — and is
   never persisted.
3. **Two laws**, binding on the fake and on the argon2 adapter alike:
   - `verify(p, unusable_hash())` is `False` for **every** `p`, and the contract
     test asserts it **explicitly for `_SENTINELA_DUMMY`**. That one parameter is
     what prevents a future refactor from quietly collapsing the two methods back
     together.
   - Two calls return **different** hashes.
4. Randomness stays behind the port, in the adapter, so the application layer
   still generates no secrets (LAYOUT §3, CLAUDE.md).

## Alternatives considered

### Alternative A — Reuse `dummy_hash()` (the original plan)
- **Description:** store the timing constant as the pending account's credential.
- **Pros:** no port change, no new code.
- **Cons:** full authentication bypass for every pending invite, via a string
  published in the repository. Additionally, every invited user would carry a
  byte-identical `password_hash`, letting anyone with read access to `users` list
  exactly which accounts are un-activated — the highest-value target set — and
  defeating argon2's per-hash salt by hashing one constant once and reusing it.
- **Why rejected:** it is a critical vulnerability, not a trade-off.

### Alternative B — Strengthen `dummy_hash()` to be random per instance
- **Description:** seed the existing dummy from `secrets` and keep one method.
- **Pros:** one method instead of two; fixes the preimage problem.
- **Cons:** the two uses have genuinely opposed requirements. The timing dummy
  must be computed **once per process** and reused, or the "e-mail not found" path
  pays two argon2 derivations while the "wrong password" path pays one — which
  reopens, from the other side, the exact timing oracle law 2 exists to close (the
  adapter documents this in the constructor). The pending-account hash must be
  **fresh per call**, or all invited users share a value. One method cannot be both.
- **Why rejected:** merging them trades a credential leak for a timing leak.

### Alternative C — Make `users.password_hash` nullable, add a "pending" state
- **Description:** model the absence of a password explicitly in the schema.
- **Pros:** honest data model; enables listing pending invitations.
- **Cons:** touches the 2.3 schema and every read path, and it *creates* the
  enumeration signal that Alternative A leaks accidentally — "has no password"
  becomes a queryable, and eventually API-visible, property. It also weakens the
  `NOT NULL` that makes "user without credential" unrepresentable.
- **Why rejected:** larger blast radius for a benefit this stage does not need.
  Recorded as a `[finding]` for whichever stage actually needs to list pending
  invitations.

## Consequences

### Positive
- A pending account has no working password, for anyone, including the authors.
- The sentinel-parameterised contract test makes the regression loud: any future
  attempt to store `dummy_hash()` fails a test that names the exact attack.
- Per-call randomness removes the "all invited users look identical in the DB"
  fingerprint.

### Negative
- One more method on a port implemented by an adapter and a fake, plus the
  contract tests for its two laws.
- `dummy_hash()` keeps its misleading docstring ("`verify` sempre falha"). This
  stage restates the law honestly in the concept premises, but the docstring
  itself is corrected only where it is read — a `[finding]` covers tightening the
  port text so the next reader does not repeat the mistake.

### Neutral / trade-offs accepted
- Invited users still occupy a normal `users` row with a normal-looking hash;
  "not yet activated" remains implicit rather than modelled.

## References
- `src/restaurant_hub/features/identity/adapters/out/security/argon2_hasher.py:22,36`
- `src/restaurant_hub/features/identity/application/ports/out/password_hasher.py` (laws 1 and 2)
- `docs/adr/2_4_0004-security-adapter-parameters.md`
- `docs/stages/2.5-email-invite/concept.md` §3 (premises), §5 regra 9, §7 D4, CA6b/CA6c
- Checkpoint A of stage 2.5 — two independent reviewers, blocker, 2026-07-20

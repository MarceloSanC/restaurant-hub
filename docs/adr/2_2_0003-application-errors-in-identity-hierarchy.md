---
title: ADR 2.2.0003 — Application errors inherit from IdentityError, not ApplicationError
description: Architecture Decision Record
when-use: Reference whenever adding an error to the identity application layer, or before introducing an ApplicationError subclass anywhere
keywords: [adr, identity, errors, exceptions, http-mapping, domain-error, not-found]
status: superseded
created_at: 2026-07-18
updated_at: 2026-11-02
adr_id: "2.2.0003"
superseded_by: "3.9.0001"
decision: Errors raised by identity use cases subclass IdentityError (hence DomainError), and not-found errors additionally subclass NotFoundError, so no business path can escape to HTTP 500.
context_stage: 2.2-identity-application
bounded_context: identity
---

# ADR 2.2.0003 — Application errors inherit from IdentityError, not ApplicationError

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`superseded`

> **Superseded (2026-11-02) by [ADR 3.9.0001](./3_9_0001-error-roots-by-meaning-status-by-map.md)** (Stage 3.9, issue #48). The status no
> longer comes from the inheritance: each bounded context resolves it from an explicit,
> test-guarded map in its inbound adapter, registered on both of its roots. Errors that are
> not business-rule violations now descend from `ApplicationError` (back, in
> `shared/application/errors.py`) through the BC's application root; `NotFoundError` and the
> `(IdentityError, NotFoundError)` multiple inheritance are gone. The body below is the
> historical record of the 2026-07-18 decision and was not edited.

## Context

Stage 2.2 introduces error conditions that do not exist in the 2.1 domain because
they only arise during orchestration: e-mail already registered, invalid
credentials, the five access-denial outcomes of `authorize_action` (permission
denied, tenant scope required, tenant not visible, unit scope required, unit not
visible), and three not-found cases (restaurant, unit, user).

The shared kernel offers two roots (`shared/domain/exceptions/base.py`):

- `DomainError` — business rule violation. **Registered** in
  `shared/infrastructure/http/error_handlers.py` → HTTP 422.
- `NotFoundError(DomainError)` — **registered** → HTTP 404.
- `ApplicationError(Exception)` — documented as "use case orchestration error",
  and **not registered with any handler**.

Stage 2.1 already paid for this asymmetry once. Its technical §7 records a
`[deviation]`: name/identifier validation originally raised `ValueError`, which
"escapes both handlers and becomes a **500**". The fix was to introduce
`InvalidNameError`/`InvalidIdentifierError` under `IdentityError`. The 2.1 concept
§6 closes with the rule "all subclasses of `IdentityError` → `DomainError`".

By its own docstring, `ApplicationError` is the semantically natural parent for
several of these errors. But choosing it would re-create, in a Stage that has
already been told about the trap, exactly the 500-by-omission the previous Stage
escalated — since nothing in 2.2 can register an HTTP handler (that is 2.4, and
`application` may not import `shared/infrastructure` at all, LAYOUT §3).

## Decision

All errors raised by identity use cases live in
`src/restaurant_hub/features/identity/application/errors.py` and inherit from
**`IdentityError`** (the BC root from 2.1, itself a `DomainError`):

- `EmailAlreadyRegisteredError(IdentityError)`
- `InvalidCredentialsError(IdentityError)`
- `PermissionDeniedError(IdentityError)` — RBAC axis
- `TenantScopeRequiredError(IdentityError)` — target tenant not declared
- `TenantNotVisibleError(IdentityError)` — target tenant is not the actor's
- `UnitScopeRequiredError(IdentityError)` — target unit not declared by a
  unit-scoped actor
- `UnitNotVisibleError(IdentityError)` — visibility axis

The three not-found errors inherit from **both**, in this order:

- `RestaurantNotFoundError(IdentityError, NotFoundError)`
- `UnitNotFoundError(IdentityError, NotFoundError)`
- `UserNotFoundError(IdentityError, NotFoundError)`

Both bases converge on `DomainError`, so the MRO is well-formed. Starlette
resolves a handler by walking `type(exc).__mro__` and taking the first registered
class: `IdentityError` has no handler, so the lookup reaches `NotFoundError`
before `DomainError` and yields 404 — without 2.2 knowing anything about HTTP.

The invariant this buys: **no business error from this BC can produce a 500**. The
worst untuned case is 422. Stage 2.4 then refines the precise codes (401 for
`InvalidCredentialsError`, 403 for the five denial errors) by registering handlers,
with no change to this layer.

Domain errors from 2.1 (`CrossTenantError`, `PlatformAdminMembershipError`, …) are
**not re-wrapped** — they already satisfy the same invariant, and re-wrapping would
discard the specificity 2.4 needs.

## Alternatives considered

### Alternative A — Subclass `ApplicationError`
- **Description:** a parallel `IdentityApplicationError(ApplicationError)` root for
  orchestration errors.
- **Pros:** semantically cleanest — these genuinely are orchestration outcomes, not
  domain invariant violations; keeps a crisp layer distinction in the type system.
- **Cons:** `ApplicationError` has **no** registered handler, so every one of these
  becomes a 500 until 2.4 remembers to add one. A 500 on a wrong password is both a
  bug and an operational alarm. It also splits the BC's errors across two roots, so
  "catch everything identity raises" stops being one `except`.
- **Why rejected:** it recreates the exact failure the 2.1 `[deviation]` documented,
  and the safety of the default matters more than taxonomic purity. The cost of
  being wrong is asymmetric: 422-instead-of-403 is a refinement, 500-instead-of-401
  is an incident.

### Alternative B — Subclass `ApplicationError` *and* register handlers now
- **Description:** take Alternative A and add the missing handler in this Stage.
- **Pros:** keeps the clean taxonomy without the 500 risk.
- **Cons:** `application` cannot import `shared/infrastructure` (LAYOUT §3), and
  editing `error_handlers.py` from an application-layer Stage puts HTTP concerns in
  a Stage whose target layer is `application` — work the roadmap assigns to 2.4.
- **Why rejected:** it buys taxonomy by breaking the layer boundary and the Stage
  boundary at once.

### Alternative C — Not-found errors inherit only from `NotFoundError`
- **Description:** drop `IdentityError` from the not-found bases.
- **Pros:** simpler, no multiple inheritance.
- **Cons:** breaks the 2.1 concept rule that every identity error is an
  `IdentityError`; `except IdentityError` would silently miss three errors, which is
  precisely the kind of hole a future middleware or test would not notice.
- **Why rejected:** the multiple inheritance is two well-behaved bases meeting at a
  common ancestor — a small, well-understood cost for a uniform BC hierarchy.

### Alternative D — Return result objects instead of raising
- **Description:** use cases return `Result[Ok, Err]`-style unions.
- **Pros:** no exception control flow; errors are total and explicit.
- **Cons:** alien to the codebase (2.1 and the shared kernel are exception-based),
  and for authorization it reintroduces the ignorable-verdict problem that ADR
  2.2.0002 rejects.
- **Why rejected:** inconsistent with the established convention, for no gain here.

### Alternative E — Do nothing / reuse only 2.1's existing exceptions
- **Description:** raise `IdentityError` directly, or force-fit existing subclasses.
- **Pros:** no new file.
- **Cons:** callers cannot distinguish "wrong password" from "unknown restaurant",
  so 2.4 cannot map status codes at all.
- **Why rejected:** the distinctions are exactly what the next Stage consumes.

## Consequences

### Positive
- No identity business error can reach HTTP 500; the untuned default is 422.
- `except IdentityError` catches everything the BC raises, from either layer.
- The three not-found errors already map to 404 with the handlers that exist today
  — 2.4 inherits correct behaviour for free.
- 2.4 refines status codes purely additively, touching no application code.

### Negative
- An application-layer concern (invalid credentials) is typed as a `DomainError`,
  which is a mild semantic stretch. Documented here so it is a recorded trade-off
  rather than an accident.
- `ApplicationError` remains unused in the codebase, and the reason is non-obvious
  without this ADR.

### Neutral / trade-offs accepted
- Multiple inheritance in three classes. Deliberate, shallow, and covered by a test
  that asserts the MRO resolves to `NotFoundError` before `DomainError`.
- If a future error is genuinely infrastructural rather than business (say, a
  repository timeout), it should **not** follow this rule — it is not a business
  outcome. This ADR governs business errors raised by use cases only.

## Implementation notes

- One test asserts, for every error class in the module, that it is an
  `IdentityError` **and** a `DomainError`; and for the three not-found classes,
  that they are `NotFoundError`. This makes the invariant regression-proof as the
  module grows.
- `InvalidCredentialsError` must carry a message that does **not** distinguish
  unknown e-mail from wrong password (concept §5.14, which also requires the
  dummy-hash verification so the two paths do not differ in response time).

## References

- Related ADRs: [`2_2_0001-revocable-refresh-session-port.md`](./2_2_0001-revocable-refresh-session-port.md),
  [`2_2_0002-authorization-two-axes-fail-closed.md`](./2_2_0002-authorization-two-axes-fail-closed.md)
- Concept: [`../stages/2.2-identity-application/concept.md`](../stages/2.2-identity-application/concept.md) §6, §7.3
- Prior art in-repo: [`../stages/2.1-identity-domain/technical.md`](../stages/2.1-identity-domain/technical.md) §7
  (`[deviation]` — `ValueError` would become 500)
- Code: `src/restaurant_hub/shared/infrastructure/http/error_handlers.py`,
  `src/restaurant_hub/shared/domain/exceptions/base.py`

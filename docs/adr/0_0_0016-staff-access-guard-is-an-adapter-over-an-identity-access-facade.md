---
title: ADR 0.0.0016 — The staff AccessGuard is an outbound adapter over an identity access facade, not a class in the composition root
description: Architecture Decision Record
when-use: Reference before placing a cross-BC translator in composition_root.py, before adding an operation to identity's facade, when another bounded context needs authentication or authorization from identity, or when moving where the omitted tenant is resolved
keywords: [adr, transversal, composition-root, anticorruption-layer, open-host-service, facade, access-guard, authorization, authentication, tenant, bc-independence, issue-47]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
adr_id: "0.0.0016"
decision: 'Staff''s AccessGuard is implemented by LocalAccessGuard in features/staff/adapters/out/identity/, importing only identity.application.facade: authorization goes through a new IdentityAccessFacade (primitive signature, the two leak translations shared with the HTTP guard via authorize_at_boundary), and authentication is an injected callable bound by the composition root to IdentityGuard.authenticate_principal, which returns the facade-published AccessPrincipal. The composition root keeps only wiring (Gate 1 allowlists emptied); the omitted-tenant resolution of ADR 0.0.0005 clause 3 moves with the translator.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0016 — The staff `AccessGuard` is an outbound adapter over an identity access facade

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided in issue #47 (orchestrated session; the product-preference fork was
delegated by the sponsor to the recommended option).

**Supersedes [ADR 3.4.0001](./3_4_0001-staff-owned-access-guard-port.md) §Decision 3** (the
translator is assembled in `composition_root.py`) and **closes
[ADR 3.5.0001](./3_5_0001-cross-bc-facade-and-gateway-edge.md) §Decision 5** (the translator
stays in the composition root until identity exposes access outside its inbound adapter).
**Amends the location named by [ADR 0.0.0005](./0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
clause 3 for `staff`** — the principle ("one trusted layer, whose location follows the opacity
of the actor") is unchanged; the derived location moves from the composition root to the
adapter. Each of the three receives an append-only dated note (CONVENTIONS §5, third form). The
rest of all three stands: the staff-owned port, its four laws (L-AG1..L-AG4), the single named
`bc-independence` edge, the three clauses of 0.0.0005.

## Context

1. **The debt was measured, not aesthetic.** `_IdentityAccessGuard` lived in
   `composition_root.py`, with its helper `_tenant_id_do_ator`. It translated vocabulary between
   two bounded contexts (an anticorruption layer) and **decided access** — the
   `raise PermissionDeniedError` of L-AG3 (tenant isolation) and the resolution of an omitted
   tenant (ADR 0.0.0005 clause 3). Clean Architecture ch. 26 has Main create and inject, with no
   policy; Evans ch. 14 puts the ACL in the downstream context's infrastructure. Issue #45's
   Gate 1 (`check_layout.py` rule 6) made the debt countable: two allowlist entries citing #47.
2. **Why it could not move before.** ADR 3.4.0001 (alternative A) and ADR 3.5.0001 (§5,
   alternative C) measured the obstacle: the translator wrapped `IdentityGuard`, built by
   identity's **inbound HTTP adapter**. Moving the wrapper into staff would create an
   adapter → adapter, cross-BC edge held as `Any`, invisible to import-linter. 3.5 named the
   precondition: identity must expose access **outside** its inbound adapter (an access facade).
3. **The two halves of access are not the same kind of thing.** *Authorization* is an
   application decision — `AuthorizeActionUseCase` plus two leak translations
   (`UserNotFoundError` → 401, `UnitNotFoundError` → `UnitNotVisibleError`, ADR 2.4.0001 §5)
   that lived in the HTTP guard. *Authentication* of a staff request is reading an HTTP header,
   verifying the Bearer, and annotating the request with the actor for the 401/403 log
   (issue #26) under an attribute name private to identity's HTTP adapter. The staff port takes
   `authenticate(request: object)`, and ADR 3.7.0001 leaves driver-independent authentication to
   the Stage that creates the first non-HTTP driver.

## Decision

1. **`LocalAccessGuard`** in `features/staff/adapters/out/identity/local_access_guard.py`
   implements staff's `AccessGuard`. It imports only `identity.application.facade` — the edge
   `bc-independence` already names for the package (ADR 3.5.0001 §3); no new `ignore_imports`.
2. **Authorization goes through `IdentityAccessFacade`**, a second class in the **same**
   `facade.py` (so the edge stays one named pair): `authorize(principal, permission, *,
   tenant_id, unit_id) -> AccessGrant`, primitives in and out, converting to value objects
   inside. The two leak translations move from `IdentityGuard.authorize` to
   `authorize_at_boundary` in `use_cases/authorize_action.py`, which **both** the HTTP guard and
   the facade call — one copy of a leak rule. The facade does not resolve the omitted tenant:
   omission has a meaning only in the caller's contract.
3. **Authentication stays in identity's inbound adapter** and is published, not imported:
   `IdentityGuard.authenticate_principal(request: object) -> AccessPrincipal` (fail-closed
   `InvalidAccessTokenError` for anything that is not an HTTP request). The composition root
   injects the bound method into `LocalAccessGuard` as `Callable[[object], AccessPrincipal]`;
   `AccessPrincipal` is the facade's type. Bearer parsing and the #26 annotation keep one copy,
   and staff's 401 band stays byte-identical to identity's (L-AG1).
4. **What the adapter decides:** no `try/except` (L-AG1/L-AG2); the omitted tenant is the
   actor's (`tenant_id if tenant_id is not None else actor.tenant_id`, a typed read — clause 3
   of 0.0.0005, the location now being the module that produced the actor); L-AG3 raises
   `PermissionDeniedError` (re-exported by the facade) when identity authorizes an actor with no
   tenant; an actor not produced by this guard is a `TypeError` (wiring defect, not a 403).
5. **The composition root only wires.** `_IdentityAccessGuard` and `_tenant_id_do_ator` are
   gone; `COMPOSITION_ROOT_CLASS_ALLOWLIST` and `COMPOSITION_ROOT_FUNCTION_ALLOWLIST` are empty
   (tests pin `set()`); `ApplicationDependencies.identity_guard` is typed. The mutation scope
   (`[tool.mutmut] only_mutate`) follows the logic: `local_access_guard.py` replaces
   `composition_root.py`.

## Alternatives considered

### Alternative A — issue #47 literally: move the wrapper with its `Any`
- **Description:** `_IdentityAccessGuard` moves to `staff/adapters/out/identity/` still wrapping
  `IdentityGuard`, typed or `Any`, with `ignore_imports` for `Permission`, `RestaurantId`,
  `UnitId` (and now `IdentityGuard`).
- **Why rejected:** an adapter → adapter cross-BC import (ADR 3.5.0001 alternative C); three
  to four suppressions; staff would **name** `Permission`, which `test_bc_independence.py`
  forbids. The issue body predates the facade edge of 3.5.

### Alternative B — facade also authenticates: `authenticate(token: str)`
- **Description:** the facade decodes the token; `LocalAccessGuard` extracts the Bearer from the
  request itself.
- **Why rejected:** Bearer parsing (whose seven malformed forms must all yield the same 401)
  would get a second copy in staff, and the #26 log annotation would either be lost on staff
  routes or require staff to write identity's private `request.state` attribute. The HTTP
  knowledge belongs to identity's inbound adapter; publishing its result is cheaper than
  duplicating it. Revisit when a non-HTTP driver exists (ADR 3.7.0001's reopening trigger).

### Alternative C — a second facade module (`access_facade.py`)
- **Why rejected:** a second named pair in `bc-independence` and a second module in the
  detectors of `test_bc_independence.py`, for no isolation gained: both classes are identity's
  published surface. Convention without a winner, closed by "one module to import" (ADR
  3.5.0001 §1).

### Alternative D — keep it in the composition root
- **Why rejected:** leaves the only module with a tenant-isolation `raise` outside every import
  gate, and the Gate 1 allowlists permanently non-empty.

## Consequences

### Positive
- The composition root's charter is literally true: no class but containers, no function but
  wiring, no `raise`.
- The tenant-isolation logic now lives in a module that import-linter, `check_layout.py` and
  the mutation scope all see.
- The `Any` and the `getattr` reads are gone; the actor is a typed `AccessPrincipal`.
- A foreign actor fails with a typed, named `TypeError` (was an `AttributeError` deep in
  identity — finding of Stage 3.7 §7).

### Negative
- identity's facade module grows a class whose purpose **is** exposing access decisions, while
  LAYOUT §3 says "the facade does not authorize". The clause now reads as "does not gate its own
  operations"; the facade docstring and LAYOUT say so explicitly.
- Staff's out adapter depends at runtime on a method of identity's inbound adapter, through an
  injected callable. The dependency is typed and visible in the constructor, not hidden, but
  no import contract describes it — the composition root is where it is legible.

### Neutral / trade-offs accepted
- The two leak translations moved from the HTTP adapter to the application layer; the HTTP
  guard's behaviour is unchanged (its tests are untouched and green).
- `PermissionDeniedError` is re-exported by the facade, as the 3.5 facade re-exports the errors
  its consumer must name.

## Implementation notes
- Tests: the four laws migrated to `tests/unit/features/staff/adapters/test_local_access_guard.py`
  with the same parametrized axes as the fake's suite; the real chain (Bearer → adapter →
  facade → use case over identity fakes) is CA14 of Stage 3.7,
  `test_application_authorization_chain.py`; wiring identities in
  `test_composition_root_staff.py` (CA15).
- LAYOUT §3 (crossing between BCs) and §6 (charter) are updated in the same issue.

## References
- Issue #47 and its comments (the #45 finding; the 3.5 re-scope)
- ADR 3.4.0001 §3 (superseded here), ADR 3.5.0001 §5 (closed here), ADR 0.0.0005 clause 3
  (location amended here), ADR 3.7.0001 (authorization in staff's application layer), ADR
  2.4.0001 §5 (cross-tenant enumeration oracle)
- `src/restaurant_hub/features/staff/adapters/out/identity/local_access_guard.py`,
  `src/restaurant_hub/features/identity/application/facade.py`,
  `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
- Robert C. Martin, *Clean Architecture*, ch. 26; Eric Evans, *Domain-Driven Design*, ch. 14

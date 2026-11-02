---
title: ADR 0.0.0014 — Creating a restaurant provisions its first owner in the same identity unit of work; the owner route stays as the way to add an owner to an existing restaurant
description: Architecture Decision Record
when-use: Reference before changing `POST /restaurants`, `ProvisionRestaurantUseCase` or `POST /restaurants/{id}/owners`, before adding another route that emits a role without the "cannot grant what you do not hold" composition, or when revisiting ADR 2.4.0003 Alternative B
keywords: [adr, provisioning, restaurant, owner, tenant, bootstrap, unit-of-work, atomicity, platform-admin, identity, issue-67]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
adr_id: "0.0.0014"
decision: `POST /restaurants` takes the restaurant name and its first owner's e-mail and password and runs `ProvisionRestaurantUseCase`, which writes `restaurants.add` + `users.add` inside one identity `UnitOfWork` with the role fixed to `owner` in the use case; `CreateRestaurantUseCase` is removed, so no API path creates a restaurant without an owner; `POST /restaurants/{id}/owners` stays, re-scoped to adding an owner to an existing restaurant; authorization stays at the HTTP boundary as for every identity use case
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0014 — Restaurant provisioning creates its owner in one unit of work

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #67 (standalone issue, hence the `0.0` prefix — CONVENTIONS §1, "ADR global" —
and `bounded_context: transversal`, CONVENTIONS §2). The decision is about the identity bounded
context; a search for identity ADRs finds it through ADR 2.4.0003's `## Supersessão parcial`.
The number `0.0.0014` was assigned by the orchestrator: `0.0.0011` and `0.0.0012` belong to
issue #79 (PR #110) and `0.0.0013` to PR #109.

**Partially supersedes [ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md):**

- **Alternative B** (*"a composite `ProvisionRestaurantUseCase` … Why rejected: false atomicity is
  worse than two explicit calls. Revisit when a transaction port exists."*) — the transaction port
  exists (ADR 2.6.0001), and Alternative B is now the decision.
- **§5**, the sentence *"exactly one such route exists"* and the description of
  `POST /restaurants/{restaurant_id}/owners` as **the** bootstrap route. Two routes now emit an
  `owner` without the §2 composition; both are listed in §3 below.

Everything else in ADR 2.4.0003 stands: the adapter declares required permissions and delegates
the decision (§1), the "cannot grant what you do not hold" composition on tenant routes (§2), the
guarantee that **no route emits `platform_admin`** (§2b — now held by two code literals instead of
one), per-unit authorization (§3), and the tenant origins (§4).

Extends, without superseding, the population of
[ADR 2.6.0002](./2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md) §1: the
identity use cases that write more than once are now six, and `check_layout` rule 10 sees the
new one like the others (no allowlist entry).

## Context

- **The gap.** Provisioning a tenant took two calls: `POST /restaurants`, then
  `POST /restaurants/{id}/owners`. A failure between them (the second call refused, the client
  gone, the admin interrupted) leaves a restaurant nobody can operate: `platform_admin` holds only
  `manage_platform`, so it cannot act inside the tenant, and the recovery is a second call the
  admin has to remember to make (issue #67).
- **Why it was two calls.** ADR 2.4.0003 Alternative B rejected the composite route because there
  was no unit of work: each repository opened its own transaction, and a failure after the
  restaurant insert would leave the orphan while the response said the whole thing failed.
- **The port now exists.** ADR 2.6.0001 gives identity a `UnitOfWork` with laws L1–L6, pinned by a
  contract suite (fake × Postgres), and five use cases already compose their writes in it.
  `users.tenant_id` references `restaurants.id`; inside a unit, the restaurant insert is visible to
  the user insert (L4), so the foreign key holds.
- **Who calls `POST /restaurants`.** Only the test suites (unit, e2e) — there is no frontend or
  external client yet. The API is `/api/v1`, pre-release.
- **Identity use cases do not authorize.** ADR 3.7.0001 moved authorization into the **staff**
  use cases; identity's `CreateRestaurantUseCase`, `CreateUserUseCase` and `CreateUnitUseCase`
  take no actor, and the HTTP adapter authorizes (ADR 2.4.0003 §1).

## Decision

1. **`ProvisionRestaurantUseCase`** (`features/identity/application/use_cases/`) takes a
   `ProvisionRestaurantCommand(name, owner_email, owner_plain_password)` and returns a
   `ProvisionedRestaurantResult(id, name, owner: UserResult)`. Order:
   1. build the `Restaurant` (the name invariant is the domain's, local and free);
   2. refuse an `owner_email` already registered (`EmailAlreadyRegisteredError`, global
      uniqueness — before any write);
   3. build the owner `User` with `role=Role.OWNER` **fixed in the use case** and
      `tenant_id` = the new restaurant's id; hash the password (CPU work before the unit,
      ADR 2.6.0001 §2);
   4. `with unit_of_work.transaction(): restaurants.add(...); users.add(owner, hash, ())`.

   A failure of either write — including a concurrent registration of the same e-mail caught by
   the unique index after the check — leaves neither row.
2. **`POST /restaurants` is the composite route.** Body
   `{"name": …, "owner": {"email": …, "password": …}}`, response `201`
   `{"id", "name", "owner": UserResponse}`. It still requires `manage_platform` and authorizes
   before converting the body to value objects, as before. `CreateRestaurantUseCase`,
   `CreateRestaurantCommand`, `RestaurantResult` and `RestaurantResponse` are removed: no API path
   creates a restaurant without an owner.
3. **`POST /restaurants/{restaurant_id}/owners` stays**, re-scoped from "the bootstrap" to "add an
   owner to an existing restaurant": the platform's support path when a tenant's owners lost
   access, and the recovery for restaurants created before this decision. Its contract does not
   change. The inventory of routes that emit a role without ADR 2.4.0003 §2 is now **two**, both
   requiring `manage_platform`, both emitting the literal `Role.OWNER` (one in the router, one in
   `ProvisionRestaurantUseCase`); neither reads a role from the request.
4. **Authorization stays at the boundary.** `ProvisionRestaurantUseCase` takes no actor, like
   every identity use case. [decision:C] rung 1 — ADR 3.7.0001 is scoped to staff
   (`bounded_context: staff`, "every **staff** use case"), and ADR 2.4.0003 §1 is the identity rule;
   making one identity use case authorize would leave the bounded context with two conventions.
   Whether identity follows staff is a decision for the whole bounded context, not for this route.
5. **The owner gets a password, not an invitation.** The composite keeps the credential shape of
   the owner route it replaces in the bootstrap (`CreateOwnerRequest`: e-mail + password).

## Alternatives considered

### Alternative A — Keep two routes, update the reason (confirm 2.4.0003 Alt. B)
- **Pros:** no contract change.
- **Cons:** the reason given in 2.4.0003 no longer holds, and the orphan restaurant stays
  reachable through the only provisioning flow there is.
- **Why rejected:** the issue's own trigger — the transaction port — fired; keeping the gap
  would need a new reason, and none was found.

### Alternative B — A new composite route next to the old two (`POST /restaurants/provisionings`)
- **Pros:** additive; no test or client changes.
- **Cons:** `POST /restaurants` alone keeps creating owner-less restaurants, so the gap stays open
  for whoever uses the old flow; three platform routes for one job.
- **Why rejected:** P delegated by the sponsor to the recommended option — closing the gap beats
  sparing a pre-release contract with no external consumer.

### Alternative C — `POST /restaurants` with an **optional** `owner`
- **Pros:** backwards-compatible.
- **Cons:** one route, two behaviours and two response shapes; the orphan path is the default.
- **Why rejected:** same as B.

### Alternative D — Remove `POST /restaurants/{id}/owners` too
- **Pros:** the inventory of §5 back to one route.
- **Cons:** the platform loses its only way to restore access to a tenant whose owners are gone,
  and restaurants created before this decision would have no way to get an owner.
- **Why rejected:** [decision:C] rung 2 — removing the recovery path is the irreversible option;
  keeping a route whose guarantees (manage_platform, literal role) are unchanged costs nothing.

### Alternative E — Invite the owner (pending account + setup link by e-mail)
- **Pros:** the platform admin never knows the owner's password; matches `POST /users/invitations`.
- **Cons:** changes the admin flow and the credential model of the owner route; the e-mail is a
  side effect that must run after commit (ADR 2.6.0002 §3), with its own failure surface.
- **Why rejected:** P delegated — out of the issue's scope (which composes the existing two
  writes); recorded as a finding on issue #67 for a later decision.

### Alternative F — The composite calls `CreateRestaurantUseCase` and `CreateUserUseCase`
- **Pros:** reuses the two use cases.
- **Cons:** `check_layout` rule 10 classifies writes by repository attribute; writes reached
  through another use case's `execute` are its declared blind spot (ADR 2.6.0002 §5), so the gate
  would not see that they share a unit. `CreateUserUseCase` also re-reads the restaurant it is
  told about, which inside the unit is the row just inserted.
- **Why rejected:** [decision:C] rung 1 — ADR 2.6.0002 §5 and issue #67 ask for
  `restaurants.add` + `users.add` visible in one unit.

## Consequences

### Positive
- No API path creates a restaurant without its owner; a failure in either write leaves the
  database unchanged (pinned by a Postgres test: failure after write N ⇒ tables identical, for
  every N, and a database-originated e-mail conflict after the restaurant insert ⇒ no restaurant).
- Provisioning is one round trip, and the role it emits is a literal in the application layer —
  a second inbound adapter (CLI, admin console) calling the use case cannot pass another role.

### Negative
- **Breaking change** to `POST /restaurants` (request and response). Accepted pre-release; every
  test call site was migrated in the same change.
- Two routes now emit an `owner` without the §2 composition. Both are listed here and in the
  router's docstrings; a third needs its own ADR, as ADR 2.4.0003 §5 already requires.
- The platform admin still chooses the owner's first password (Alternative E is a finding).

### Neutral / trade-offs accepted
- `POST /restaurants/{id}/owners` keeps its `RestaurantNotFoundError` (404) band; it is now the
  support route, not the bootstrap.

## References
- Issue #67; `docs/stages/2.4-identity-http/technical.md` §7 ("Atomicidade da rotação e do
  provisionamento"); `docs/stages/2.6-identity-unit-of-work/technical.md` §7 (finding that opened #67)
- [ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md) Alternative B, §2b, §5
- [ADR 2.6.0001](./2_6_0001-identity-unit-of-work-port-and-ambient-connection.md) (port, L1–L6)
- [ADR 2.6.0002](./2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md) §1, §3, §5
- [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md) (scope: staff)
- `src/restaurant_hub/features/identity/application/use_cases/provision_restaurant.py`

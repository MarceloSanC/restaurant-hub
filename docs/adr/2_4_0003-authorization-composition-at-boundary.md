---
title: ADR 2.4.0003 — The HTTP adapter composes authorization by declaring required permissions, and tenant provisioning gets a dedicated platform-scoped route
description: Architecture Decision Record
when-use: Reference before adding a route that creates or elevates a user, when a role appears able to grant a permission it does not hold, or when questioning why platform_admin has a dedicated owner-creation route
keywords: [adr, authorization, rbac, privilege-escalation, bootstrap, tenancy, provisioning, boundary, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-11-02
adr_id: 2.4.0003
decision: The HTTP adapter declares which permissions an action requires (including every permission of the role being granted, so no actor can grant what it does not hold) and delegates every decision to AuthorizeActionUseCase; tenant provisioning gets a dedicated manage_platform route that creates the restaurant's first owner, which is what makes the roadmap's end-to-end chain reachable at all
context_stage: 2.4-identity-http
bounded_context: identity
---

# ADR 2.4.0003 — Authorization composition at the HTTP boundary

## Status

`accepted`

## Context

Issue #24 fixes two constraints that interact badly if taken naively:

- The HTTP adapter **delegates** authorization to the use case; it does not
  reimplement it (ADR 2.2.0002, two orthogonal fail-closed axes).
- Only `platform_admin` creates a restaurant (tenant); `owner` creates and manages
  units from there on (sponsor, 2026-07-19).

`AuthorizeActionUseCase` decides whether an actor may perform an action, but it
takes the action's required `permission` and its target scope (`tenant_id`,
`unit_id`) **as input** — the caller supplies them. So the boundary must supply
something, and *what* it supplies is a design decision.

Two concrete problems surface when writing the routes:

**1. Privilege escalation through user creation.** `manager` holds `manage_users`
(the permission for "create a user"). `owner` holds `manage_tenant` **and**
`manage_users`. If the required permission for `POST /users` is simply
`manage_users`, then a `manager` can create a user with `role=owner` — minting an
account more powerful than its creator. The role→permission map from Stage 2.1
(`_ROLE_PERMISSIONS`) makes this exploitable in one request.

**2. The tenancy bootstrap is unreachable.** `platform_admin` holds **only**
`manage_platform` — Stage 2.1's concept states this deliberately ("acesso de
plataforma não é acesso de restaurante"). So `platform_admin` cannot create any
user. But it is the only role that can create a restaurant. The result: a
restaurant is created with **nobody able to operate it**, and the roadmap's DoD
chain ("admin cria tenant → unidade → usuário") cannot be executed by anyone. This
is not a hypothetical — it blocks the Stage's acceptance criteria.

## Decision

### 1. Declaring the requirement is the adapter's job; deciding it is not

The adapter maps *endpoint + payload* → *set of required permissions* + *target
scope*, then calls `AuthorizeActionUseCase` once per required permission. No access
rule is evaluated in the adapter: it holds no role table, no bypass logic, no
membership check. Those stay in `User` (domain) and `AuthorizeActionUseCase`
(application), which remain the single source of truth.

### 2. "You cannot grant what you do not hold" — on tenant-facing routes

On `POST /users`, creating a user with role `P` requires the actor to hold:

```
{manage_users} ∪ P.permissions
```

derived at request time from the Stage 2.1 map — **no second role table**, no new
policy code, no domain change. The rule is enforced purely by calling the existing
use case once per permission in the set.

Consequences, all fail-closed and all intended:

| Actor | Target role | Outcome |
|---|---|---|
| `owner` | `manager` / `hr` / `employee` / `owner` | allowed (subset of owner's permissions) |
| `manager` / `hr` | `manager` / `hr` / `employee` | allowed |
| `manager` / `hr` | `owner` | **denied** — lacks `manage_tenant` |
| any | `platform_admin` | **denied** — no role holds `manage_users` ∪ `manage_platform` |

The table above describes `POST /users` only. **It is not a universal property of
the system**, and saying otherwise would be the more dangerous error — see §5.

Within `POST /users`, the last row means `platform_admin` is not creatable there.
The first `platform_admin` is seeded outside the API like any root of trust
(concept §13).

### 2b. What actually guarantees that no `platform_admin` is minted

It is tempting — and wrong — to argue "rule 2 forbids it, therefore it cannot
happen". Rule 2 governs one route. The real, checkable guarantee is:

> **No route emits `platform_admin`.** `POST /users` cannot, by composition;
> `POST /restaurants/{id}/owners` cannot, because its role is the literal
> `Role.OWNER` fixed in code, never read from the request.

This distinction is load-bearing because the second formulation is the one a future
author re-reads before adding the next provisioning route. If they believe the
composition is a system-wide invariant, they will add a route that bypasses it
without realising a guarantee was lost. The property is pinned by a test (concept
CA20), not by this paragraph.

### 3. Unit scope is enforced per requested unit

When the request names `unit_ids`, the adapter authorizes **once per requested
unit**. A `manager` creating a user in a unit it cannot see is denied by the
visibility axis it already fails. When no unit is named, the call passes
`unit_id=None`, and a unit-scoped actor is denied by `UnitScopeRequiredError` —
omission is not a path to escalation, exactly as ADR 2.2.0002 requires.

### 4. The target user's tenant never comes from the request **body**

Two origins are permitted, selected by route — not one, as an earlier draft of this
ADR claimed:

- **Tenant routes** (`POST /users`): the tenant is `AuthorizedActor.actor_tenant_id`.
  A `tenant_id` accepted from the body would be a cross-tenant escalation vector.
- **The platform route** (`POST /restaurants/{restaurant_id}/owners`): the tenant is
  the `{restaurant_id}` **path segment**. It cannot be the actor's: the actor is
  `platform_admin`, whose `actor_tenant_id` is necessarily `None`
  (`User.__post_init__` raises `PlatformAdminTenantError` otherwise, ADR 2.1.0002),
  so taking it from the actor would produce `MissingTenantError` and make the route
  dead on arrival.

A path segment is not equivalent to a body field: it **names the resource being
acted on** and is resolved against the database (`CreateUserUseCase` raises
`RestaurantNotFoundError` when it does not exist), whereas a body field is an
unverified client assertion. The route is safe because only `manage_platform`
reaches it, and that role is global by construction — `_assert_tenant_scope`
short-circuits for it, so nothing else would have checked the path against the actor
anyway.

### 5. Tenant provisioning is a platform action: `POST /restaurants/{id}/owners`

A dedicated route requiring `manage_platform` creates the restaurant's first
`owner`, reusing `CreateUserUseCase` with `role=owner` fixed in code. No new use
case, no new permission, no change to the role map. It reads exactly as the
sponsor's decision: `platform_admin` provisions the restaurant and its owner; the
`owner` operates it from there.

**This route is a declared exception to §2, and pretending otherwise would be the
worst outcome of this ADR.** `platform_admin` holds neither `manage_tenant` nor
`manage_users`, yet the route mints an `owner` holding both. That is not an
oversight — it is what bootstrap *means*: someone outside a tenant's hierarchy must
create the top of it, or the tenant is born inoperable. What contains the exception
is not the composition rule but the **route inventory**: exactly one such route
exists, it requires `manage_platform`, and the role it creates is a code literal.
Any future route that emits a role without going through §2 needs its own ADR
justifying why, and must state which guarantee it is spending.

## Alternatives considered

### Alternative A — grant `manage_users` to `platform_admin`
- **Description:** extend `_ROLE_PERMISSIONS` so the bootstrap works through
  `POST /users`.
- **Pros:** one line; no new route.
- **Cons:** contradicts Stage 2.1's concept ("acesso de plataforma não é acesso de
  restaurante") and silently gives `platform_admin` the ability to create users in
  **any** tenant through the ordinary route, with tenant derived from an actor that
  has no tenant. It rewrites a merged domain decision to fix an adapter-level gap.
- **Why rejected:** the fix belongs at the boundary that has the problem, not in the
  domain model that is correct.

### Alternative B — a composite `ProvisionRestaurantUseCase` (restaurant + owner in one call)
- **Description:** `POST /restaurants` takes the owner's e-mail and password and
  creates both.
- **Pros:** one round trip; reads like SaaS tenant provisioning.
- **Cons:** it would **claim** atomicity it cannot deliver. There is no unit-of-work
  port spanning repositories — each Stage 2.3 adapter opens its own transaction — so
  a failure after the restaurant insert leaves an orphan tenant while the response
  says the whole thing failed. Building the UoW port is a Stage of its own.
- **Why rejected:** false atomicity is worse than two explicit calls. Revisit when a
  transaction port exists.

### Alternative C — move the escalation guard into `CreateUserUseCase`
- **Description:** the use case takes the actor and refuses to create a more
  privileged user.
- **Pros:** the rule cannot be bypassed by a future second adapter (CLI, worker).
- **Cons:** changes the signature of a use case merged in Stage 2.2, and makes
  `CreateUserUseCase` depend on the actor — turning a creation use case into an
  authorization use case, which `AuthorizeActionUseCase` already is. Two places would
  then evaluate access.
- **Why rejected:** duplicates the authorization decision, which ADR 2.2.0002
  centralised on purpose. **Noted as a real residual risk** — see Consequences.

### Alternative D — leave the bootstrap to a seed script only
- **Description:** no owner-creation route; the first owner is inserted by an
  operator.
- **Pros:** smallest surface.
- **Cons:** every new restaurant would require database access, which is exactly the
  operational coupling the platform role exists to remove. And the roadmap DoD chain
  would remain unexecutable through the API.
- **Why rejected:** it turns routine tenant onboarding into a manual DB operation.

## Consequences

### Positive
- Privilege escalation through user creation is closed by construction, using the
  role map that already exists and is already tested for totality.
- The bootstrap impasse is resolved without touching domain or application layers.
- Every access decision still happens in exactly one place.

### Negative
- **The escalation guard lives at the boundary, so a future second inbound adapter
  (CLI, worker, admin console) that calls `CreateUserUseCase` directly would not
  inherit it.** This is the real cost of choosing composition over Alternative C. It
  is acceptable now because HTTP is the only inbound adapter; it must be revisited
  the moment a second one appears, and that is recorded as a finding rather than
  left to memory.
- Authorizing once per required permission (and per requested unit) means up to
  `|permissions| × |units|` calls, each re-reading the actor. Cheap at these sizes,
  and the alternative is a bulk-authorize port shape nobody needs yet.

### Neutral / trade-offs accepted
- `platform_admin` cannot be created through the API. Recorded in concept §13 with
  `6.3-ops-baseline` as the candidate Stage for an idempotent seed command.

## References
- `docs/stages/2.4-identity-http/concept.md` §5 regras 2–4, 7, 8; §7.3
- ADR 2.2.0002 (authorization on two fail-closed axes)
- ADR 2.1.0002 (`platform_admin` without tenant)
- `src/restaurant_hub/features/identity/domain/value_objects/role.py`
  (`_ROLE_PERMISSIONS`)
- Issue #24, sponsor decisions of 2026-07-19

## Supersessão parcial

**2026-11-02 — a Alternativa B (*"a composite `ProvisionRestaurantUseCase` … Revisit when a
transaction port exists."*) e a frase de §5 *"exactly one such route exists"* foram superadas por
[ADR 0.0.0014](./0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) (issue #67).**
O port de transação existe (ADR 2.6.0001): `POST /restaurants` passou a criar o restaurante **e**
o primeiro `owner` numa unidade de trabalho de identity (`ProvisionRestaurantUseCase`), e
`POST /restaurants/{restaurant_id}/owners` deixou de ser *o* bootstrap — ficou como a rota de
plataforma que acrescenta um `owner` a restaurante existente. São agora **duas** as rotas que
emitem papel sem a composição de §2, ambas exigindo `manage_platform` e ambas com o literal
`Role.OWNER` (no router e no use case). Tudo o mais deste ADR — §1, §2, §2b ("nenhuma rota emite
`platform_admin`"), §3 e §4 — continua valendo. Nota *append-only*; o corpo acima não foi editado.

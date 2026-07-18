---
title: ADR 2.1.0001 — Identity aggregate boundaries and the user↔unit membership skeleton
description: Architecture Decision Record
when-use: Reference whenever revisiting how identity models Restaurant/Unit/User and the user↔unit link, or before adding per-unit roles
keywords: [adr, identity, ddd, aggregate, membership, tenancy, rbac]
status: accepted
created_at: 2026-07-17
updated_at: 2026-07-17
adr_id: "2.1.0001"
decision: Model Restaurant, Unit and User as three separate aggregate roots that reference each other only by id, and install the user↔unit link as a minimal UnitMembership value object created through User.link_to_unit.
context_stage: 2.1-identity-domain
bounded_context: identity
---

# ADR 2.1.0001 — Identity aggregate boundaries and the user↔unit membership skeleton

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.1 is the first domain code in the project (BC `identity`). It must model
the multi-tenant foundation — `Restaurant` (the tenant), `Unit`, `User` — and the
user↔unit relationship, and enforce the tenancy-isolation and RBAC invariants with
unit tests only (no I/O).

Forces:

- **Kickoff decision #1 (2026-07-16):** a user has a single role at the tenant
  level, plus a user↔unit link table for *visibility*. `owner` and
  `platform_admin` see the whole tenant and ignore the link. Per-unit roles are a
  future evolution. The sponsor asked for the **link skeleton now, in minimal
  form** — not the rich membership.
- **Project decision criterion:** prefer installing the scalable skeleton with a
  minimal implementation inside, over the simple shortcut that forces reshaping
  later — without overengineering (overview §4).
- **DDD tactical rules** (skill `ddd-tactical-patterns`): reference other
  aggregates by identity; one transaction = one aggregate; do not leak an
  aggregate from inside.
- **Hexagonal purity** (skill `hex-arch-python`, LAYOUT §3): domain imports only
  stdlib and other domain modules.
- ROADMAP-3: row-level `tenant_id` isolation, reinforced in code + tests.

## Decision

`Restaurant`, `Unit` and `User` are **three separate aggregate roots**. They
reference each other **only by id** — `Unit.restaurant_id`, `User.tenant_id` — and
never hold object references across aggregate boundaries. `tenant_id` is a
`RestaurantId` (a restaurant *is* its tenant; there is no separate `Tenant`
entity).

The user↔unit link is installed as a **minimal value object**
`UnitMembership(user_id: UserId, unit_id: UnitId)` — no per-unit role field. It is
created through the `User` aggregate root: `User.link_to_unit(unit) ->
UnitMembership`, which enforces the isolation invariants (same tenant; not a
platform_admin). Unit visibility is expressed by pure domain predicates on `User`
(`bypasses_unit_scope`, `can_view_unit(unit, memberships)`), keeping the two
access axes explicit and orthogonal:

- **RBAC** — what a role may do (`Role -> frozenset[Permission]`).
- **Visibility scope** — which units a user sees (owner/platform_admin bypass the
  link; manager/hr/employee are scoped to their memberships).

## Alternatives considered

### Alternative A — Restaurant as a single large aggregate containing Units and Users
- **Description:** one `Restaurant` root holding lists of `Unit` and `User`.
- **Pros:** a single consistency boundary; invariants enforced in one place.
- **Cons:** loads the whole tenant to touch one user; fights row-level `tenant_id`
  persistence (2.3); a hot, contended aggregate; violates "one transaction = one
  aggregate" for common operations.
- **Why rejected:** the tenant is large and long-lived; Unit and User have
  independent lifecycles and are persisted as their own rows (ROADMAP-3).

### Alternative B — Rich membership entity now (per-unit role, status, dates)
- **Description:** model the full membership (role-per-unit, active flag, audit
  fields) in this Stage.
- **Pros:** future-proof for per-unit roles.
- **Cons:** overengineering against the sponsor's explicit "minimal skeleton"
  (kickoff #1) and overview §4 ("no overengineering"); commits to a shape before
  the requirement exists.
- **Why rejected:** the minimal VO already leaves room to add a `role` column
  later without reshaping — exactly the progressive-scalability criterion.

### Alternative C — Membership as a plain collection on User (set of unit_ids)
- **Description:** `User` holds `_unit_ids: set[UnitId]`; no membership type.
- **Pros:** slightly less code.
- **Cons:** the link is a "table" (kickoff #1) that will gain columns
  (role-per-unit); a bare `set[UnitId]` has nowhere to grow and would be reshaped
  into a type later — the shortcut this project's criterion warns against.
- **Why rejected:** a named `UnitMembership` VO is the minimal shape that still
  scales.

### Alternative D — Do nothing / defer the link
- Not acceptable: the DoD requires the tenancy-isolation invariant (which is
  expressed precisely through the link creation rule), and kickoff #1 mandates the
  skeleton now.

## Consequences

### Positive
- Aggregates map 1:1 to future persistence rows (2.3) with `tenant_id` isolation.
- Adding per-unit roles later = a field on `UnitMembership` + a rule, no reshape.
- The two access axes are explicit and independently testable.

### Negative
- Cross-aggregate invariants (same-tenant link) are enforced by a factory method
  on `User` rather than by a single owning aggregate — a discipline the code must
  keep (mitigated by tests).

### Neutral / trade-offs accepted
- No `Tenant` entity: `tenant_id == RestaurantId`. Accepted; a `Tenant` synonym
  would add a type without behavior.
- `UnitMembership` is a VO now; if per-unit role turns it stateful it may become a
  small entity — a cheap, localized change.
- `UnitMembership` is an **ownerless association record** (a link between two
  aggregates), not embedded in either root. This is deliberate for a many-to-many
  link that persists as its own rows (2.3): `User` creates it and both `User` and
  `Unit` reference it by id, but neither retains it. Standard for a join table; the
  same-tenant invariant is enforced at creation (`User.link_to_unit`), not by an
  owning aggregate.

## Implementation notes

- `User.link_to_unit`: raise `PlatformAdminMembershipError` for platform_admin,
  `CrossTenantError` when `user.tenant_id != unit.tenant_id`.
- `User.can_view_unit`: platform_admin → always true; different tenant → false;
  owner (bypass) → true; otherwise the membership lookup must match **both**
  `m.user_id == self.id` **and** `m.unit_id == unit.id` — matching on `unit_id`
  alone would let another user's membership grant visibility (an intra-tenant
  scope hole). `UnitMembership` carries `user_id` precisely for this filter.
- Entities compare by identity (id); VOs (`Email`, `Role`, `UnitMembership`)
  compare by value, per `ddd-tactical-patterns`.

## References

- Related ADRs: [`2_1_0002-platform-admin-without-tenant.md`](./2_1_0002-platform-admin-without-tenant.md)
- Concept: [`../stages/2.1-identity-domain/concept.md`](../stages/2.1-identity-domain/concept.md) §5, §7
- Skills: `ddd-tactical-patterns`, `hex-arch-python`
- Kickoff decisions: issue #17 body; ADR 0.0.0004 §Authorized runs

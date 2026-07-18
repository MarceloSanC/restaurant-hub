---
title: ADR 2.1.0002 — Represent platform_admin as a tenant-less user
description: Architecture Decision Record
when-use: Reference whenever revisiting how platform_admin is modeled relative to tenancy, or before adding tenant-scoped rules to User
keywords: [adr, identity, platform-admin, tenancy, isolation, rbac]
status: accepted
created_at: 2026-07-17
updated_at: 2026-07-17
adr_id: "2.1.0002"
decision: Model platform_admin as a User with tenant_id None, enforced by a role-conditional invariant, instead of a separate entity or a sentinel platform tenant.
context_stage: 2.1-identity-domain
bounded_context: identity
---

# ADR 2.1.0002 — Represent platform_admin as a tenant-less user

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The `platform_admin` (Marcelo, the platform operator) creates and manages tenants.
Per kickoff decision #3 (2026-07-16), platform access is **not** restaurant access
and the platform_admin **lives outside any tenant** — it must have no `tenant_id`,
an explicit exception to the isolation invariants, and it must be modeled in the
domain **without a hack** (no fabricated "platform tenant").

Every other role (`owner`, `manager`, `hr`, `employee`) belongs to exactly one
tenant and must carry a `tenant_id` (ROADMAP-3, row-level isolation).

## Decision

`User.tenant_id` is typed `RestaurantId | None`. `None` is valid **iff**
`role == Role.PLATFORM_ADMIN`. The `User` constructor enforces the conditional
invariant:

- `role == platform_admin` and `tenant_id is not None` → `PlatformAdminTenantError`.
- `role != platform_admin` and `tenant_id is None` → `MissingTenantError`.

The tenant-less nature also drives the visibility rules: `platform_admin` bypasses
unit scope entirely (`can_view_unit` returns true regardless of tenant), while
still holding only the platform-management permission, not restaurant-operational
permissions — the two access axes stay orthogonal (see ADR 2.1.0001).

## Alternatives considered

### Alternative A — Separate `PlatformAdmin` entity, outside `User`
- **Description:** a distinct type with no tenant, parallel to `User`.
- **Pros:** the type system guarantees "no tenant" structurally.
- **Cons:** duplicates identity/email/authentication; forces every later use case
  (login in 2.2, auth in 2.4) to handle two account types; RBAC becomes two code
  paths.
- **Why rejected:** platform_admin authenticates and is authorized like any user;
  the only difference is tenancy — a field, not a type.

### Alternative B — Sentinel "platform tenant"
- **Description:** a reserved `Restaurant`/tenant id that platform_admins belong to.
- **Pros:** keeps `tenant_id` non-nullable.
- **Cons:** fabricates a fake tenant that isolation rules must special-case
  everywhere; leaks a magic id into persistence and queries; exactly the "invente
  tenant plataforma" hack the kickoff forbids.
- **Why rejected:** violates kickoff #3; pushes the special case into every layer
  instead of localizing it in one invariant.

### Alternative C — Nullable `tenant_id` with no invariant
- **Description:** allow `None` for anyone.
- **Pros:** simplest.
- **Cons:** lets a tenant user exist without a tenant (isolation hole) and a
  platform_admin exist inside a tenant (contradiction) — silently.
- **Why rejected:** the DoD is precisely the isolation invariant; leaving it
  unenforced defeats the Stage.

### Alternative D — Do nothing
- Not acceptable: the model cannot represent the platform operator at all.

## Consequences

### Positive
- One account type across all identity use cases; RBAC is uniform.
- The platform-vs-tenant boundary is a single, tested invariant, not scattered
  special-casing.

### Negative
- `tenant_id: RestaurantId | None` forces `None`-handling in later code (e.g.,
  visibility short-circuits platform_admin before comparing tenants). Localized
  and covered by tests.

### Neutral / trade-offs accepted
- The invariant couples `role` and `tenant_id` at construction; acceptable — it is
  the business rule.

## Implementation notes

- Enforce in `User.__post_init__`.
- `can_view_unit` must short-circuit `platform_admin` **before** any
  `tenant_id` comparison (a `None` tenant compared to a unit's tenant would
  otherwise read as "different tenant").

## References

- Related ADRs: [`2_1_0001-identity-aggregates-and-membership.md`](./2_1_0001-identity-aggregates-and-membership.md)
- Concept: [`../stages/2.1-identity-domain/concept.md`](../stages/2.1-identity-domain/concept.md) §5, §7
- Kickoff decisions: issue #17 body; ADR 0.0.0004 §Authorized runs

---
title: ADR 2.2.0002 — Authorization composes the two access axes and fails closed
description: Architecture Decision Record
when-use: Reference whenever revisiting how authorize_action combines RBAC with unit visibility, or before turning a denial into a boolean return
keywords: [adr, identity, authorization, rbac, visibility, fail-closed, use-case]
status: accepted
created_at: 2026-07-18
updated_at: 2026-11-09
adr_id: "2.2.0002"
decision: authorize_action evaluates RBAC, tenant scope, unit-scope requirement and unit visibility in a normative order, raises a distinct exception per check, and never returns a boolean verdict.
context_stage: 2.2-identity-application
bounded_context: identity
---

# ADR 2.2.0002 — Authorization composes the two access axes and fails closed

> ⚠️ **Errata (2026-11-09):** §Context and Alternatives B and D — "Kickoff decision #4" is the **position** of the "two orthogonal access axes" item in issue #20's "Decisões já fechadas" list, not a kickoff decision. That item is Stage 2.1's modeling, recorded in [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md) and derived from kickoff decision #1; in the canonical list ([`overview.md`](../overview.md) §3 "Decisões de kickoff (2026-07)") decision #4 is the persisted, rotated refresh token. Pointer only; no decision content changes — ver issue #129

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.1 modelled access along **two deliberately orthogonal axes** (ADR
2.1.0001, confirmed by the Stage's independent audit as its key structural idea):

- **RBAC** — what a role may *do*: `User.has_permission(permission)`, from the
  fixed, total map `Role → frozenset[Permission]`.
- **Unit visibility** — what a user *sees*: `User.can_view_unit(unit, memberships)`,
  where `owner` and `platform_admin` bypass the `UnitMembership` link.

The vocabulary was kept deliberately narrow: "see the whole tenant" is **not** a
permission, it is scope bypass. Kickoff decision #4 (issue #20) requires that
`authorize_action` respect both axes **without collapsing them into one**.

Stage 2.2 must now compose them in a single use case. Forces:

- Collapsing the axes is the easy mistake: a single `is_allowed` boolean that ORs
  or ANDs the two checks reads fine and silently destroys the distinction that
  2.1 was built around.
- The use case is a **security guard**. Stage 2.4 will consume it as a FastAPI
  dependency, and its DoD is "an action without permission returns 403".
- Stage 2.1 left a `[finding]`: when two validations coincide, which error wins
  was never specified, so a mutation reordering the checks survived the suite.
  The analogous question exists here, and it is answerable now rather than later.
- `platform_admin` has no tenant (ADR 2.1.0002) and holds only
  `MANAGE_PLATFORM` — it sees everything but may do very little. `owner` is the
  mirror image inside its own tenant. Any composition must keep both true.
- **The domain has no tenant-level check.** Tenant isolation is expressed only
  inside `can_view_unit`, which compares `user.tenant_id` to `unit.tenant_id` —
  and therefore runs only when a unit is being targeted. Nothing in 2.1 answers
  "may this actor act on tenant X?" for an action that names no unit. The
  application layer has to supply that, or tenant-wide actions cross tenants
  unchecked (ROADMAP-3 is about row-level isolation in persistence, which does not
  substitute for an authorization check).

## Decision

A single `AuthorizeActionUseCase` evaluates the checks **in sequence, with a
distinct exception per check**, and **raises** on denial rather than returning a
verdict:

1. Resolve the actor — `UserNotFoundError` if absent.
2. **RBAC axis** — `user.has_permission(command.permission)`; on failure raise
   `PermissionDeniedError`.
3. **Tenant scope** — for an actor that is not a `platform_admin`:
   `command.tenant_id is None` → `TenantScopeRequiredError`;
   `command.tenant_id != user.tenant_id` → `TenantNotVisibleError`. Skipped for
   `platform_admin`, which has no tenant.
4. **Unit-scope requirement** — if `command.unit_id is None` and
   `not user.bypasses_unit_scope()`, raise `UnitScopeRequiredError`.
5. **Visibility axis** — when the command carries a `unit_id`: resolve the unit
   (`UnitNotFoundError`); if `command.tenant_id is not None` and
   `unit.tenant_id != command.tenant_id`, raise `TenantNotVisibleError` (target-pair
   coherence, which applies to `platform_admin` too); then apply
   `user.can_view_unit(unit, repo.list_memberships(user.id))`; on failure raise
   `UnitNotVisibleError`.

On success it returns
`AuthorizedActor(user_id, role, actor_tenant_id, scope_tenant_id, scope_unit_id)`
— never a boolean. It echoes both the resolved actor and **the scope that was just
validated**: `actor_tenant_id` is the actor's own tenant (`None` for
`platform_admin`), while `scope_tenant_id`/`scope_unit_id` are the approved target.
Returning only the actor's tenant would hand 2.4 a `None` for exactly the role that
acts across tenants, forcing it to re-derive the target from the request — the
adapter-side decision this use case exists to prevent.

Two of these steps deserve their justification stated, because neither is in the
2.1 domain:

- **Step 3 exists because the domain expresses tenant isolation only *inside*
  `can_view_unit`** — that is, only when there is a target unit. A tenant-wide
  action (`unit_id is None`) would therefore cross tenants with nothing to stop
  it: a `manager` of tenant A holding `MANAGE_USERS` would be authorized for a
  tenant-B action, since step 2 passes and step 5 never runs. The target tenant
  has to be an input for the check to be possible at all.
  **Crucially, step 3 is an obligation, not a filter.** An earlier draft ran it
  only `if command.tenant_id is not None`, which merely relocated the escalation:
  an `owner` bypasses step 4, so with both `tenant_id` and `unit_id` omitted it
  reached success with no tenant comparison executed at all. A check that runs only
  when the caller remembers to supply the parameter is not an enforced rule — so a
  non-`platform_admin` actor that omits the target tenant is now **denied**.
- **Step 4 closes the escalation-by-omission hole.** Unit visibility is only a
  constraint while a `unit_id` is supplied; without step 4, a `manager` linked to
  U1 alone obtains tenant-wide authority simply by omitting `unit_id`, and the
  unit-scoping of `manager`/`hr` — the entire point of the second axis —
  evaporates. The rule is derived from the domain rather than invented: an actor
  for whom `bypasses_unit_scope()` is false has, by construction, no tenant-wide
  authority, so a command without a unit is denied. `owner` and `platform_admin`
  bypass and may omit it.

The order is **normative**: an actor failing several checks receives the error of
the earliest one. This is fixed by dedicated tests, so that a silent reordering
breaks the suite instead of passing it.

## Alternatives considered

### Alternative A — Single boolean verdict (`authorize(...) -> bool`)
- **Description:** the use case returns True/False; the caller decides what to do.
- **Pros:** composable, trivially testable, no exception control flow.
- **Cons:** a forgotten `if not authorized:` is an open door, and it reads exactly
  like correct code at the call site. In a guard, the default failure mode of a
  boolean is *allow*.
- **Why rejected:** fail-closed matters more than composability here. Raising
  makes the denial impossible to ignore: the request cannot continue by accident.

### Alternative B — One `AuthorizationDenied` exception for both axes
- **Description:** deny with a single exception type, optionally carrying a reason string.
- **Pros:** fewer exception classes; simpler mapping to a single 403.
- **Cons:** the orthogonality of the two axes stops being observable in tests —
  a refactor that checks visibility inside the permission branch (or drops one
  axis entirely) still produces the same exception and the suite stays green.
- **Why rejected:** the distinctness of the two errors is precisely what makes
  kickoff #4 enforceable rather than aspirational. Stage 2.4 can still map both to
  403; it loses nothing.

### Alternative C — Two separate use cases (`check_permission`, `check_unit_visibility`)
- **Description:** expose each axis as its own use case and let callers combine them.
- **Pros:** maximum separation; each axis independently reusable.
- **Cons:** every caller re-implements the composition, and any caller that
  forgets the second call gets a partial check that looks complete. It pushes a
  security invariant into every adapter.
- **Why rejected:** the composition itself is the business rule and belongs in one
  tested place. (The axes remain independently testable through the 2.1 domain
  predicates, which is where their unit coverage already lives.)

### Alternative D — Fold visibility into the permission vocabulary
- **Description:** add a `VIEW_TENANT`-style permission and evaluate a single axis.
- **Pros:** one concept instead of two; one check.
- **Cons:** it is exactly the collapse that 2.1 rejected — bypass becomes a
  permission, and per-unit scope then has to be re-expressed as a permission per
  unit, which does not scale.
- **Why rejected:** contradicts ADR 2.1.0001 and kickoff #4 explicitly.

### Alternative E — No tenant check; let the caller scope writes by `actor.tenant_id`
- **Description:** omit step 3 and return `AuthorizedActor`; the adapter uses the
  returned `tenant_id` to scope whatever it writes, so a cross-tenant write is
  impossible by construction of the caller.
- **Pros:** fewer inputs on the command; one less error type; arguably the tenant
  never needs to be *asked for* if it is always *derived*.
- **Cons:** it makes the isolation invariant a property of every call site rather
  than of the guard — the same "push a security invariant into every adapter"
  failure this ADR rejects in Alternative C. It is also untestable at this layer:
  nothing in 2.2 could demonstrate that a cross-tenant action is refused, so the
  Stage would claim isolation it does not verify.
- **Why rejected:** an isolation rule that only holds if every future caller
  derives the tenant correctly is not an enforced rule. Making the target tenant
  an explicit, optional input costs one field and makes the refusal testable here.

### Alternative F — Do nothing / defer authorization to the HTTP layer in 2.4
- **Description:** let the router check `has_permission` inline.
- **Pros:** no use case to write now.
- **Cons:** puts a business rule in an adapter, unreachable by unit tests and
  duplicated per endpoint; the roadmap lists `authorize_action` as in-scope here.
- **Why rejected:** contradicts the Stage's declared scope and LAYOUT §3.

## Consequences

### Positive
- The two axes stay observably distinct: no implementation can merge them without
  turning a test red.
- Denials cannot be ignored by a caller — the guard is fail-closed by construction.
- Stage 2.4 maps the five denial errors (`PermissionDeniedError`,
  `TenantScopeRequiredError`, `TenantNotVisibleError`, `UnitScopeRequiredError`,
  `UnitNotVisibleError`) to 403 with one handler, while keeping the reasons
  distinguishable in logs.
- The precedence question that 2.1 left open is closed here for this use case.

### Negative
- Exception-based control flow for an expected outcome (a denial is not a bug).
  Accepted: the alternative failure mode is silent authorization.
- Five denial exception types for 2.4 to map instead of one — four more than a
  single collapsed `AuthorizationDenied` would need. They all map to 403; the
  multiplicity buys test-observable orthogonality, not endpoint complexity.

### Neutral / trade-offs accepted
- `AuthorizedActor` duplicates fields the caller could re-read from the repository;
  returning it avoids a second lookup in 2.4, keeps the entity from leaking, and
  carries the validated scope so the guard's decision is not silently discarded.
- A command without `unit_id` skips the visibility axis, but only an actor that
  bypasses unit scope can obtain that outcome (step 4). The caller still chooses
  what to pass, yet a wrong choice now **denies** rather than over-grants — the
  failure mode is closed, not open.
- The use case does **not** decide which permission a given action requires; that
  mapping lives in the concept's permission↔action table and is applied by 2.4
  when it composes the guard as a dependency (concept §7.7). This keeps the
  decision-making here and the wiring there, which is the split the roadmap
  assigns ("enforcement de RBAC via dependência", roadmap §Stage 2.4).

## Implementation notes

- The visibility axis must call `list_memberships` **only** when a `unit_id` is
  present — `owner`/`platform_admin` short-circuit inside `can_view_unit`, but the
  repository call would still be wasted work.
- Do not re-implement any part of `can_view_unit` in the use case: cross-tenant
  rejection and bypass already live in the domain and are tested there.
- Test matrix that pins the orthogonality (full command tuple matters, because the
  step order decides which error surfaces first): `employee` + own unit →
  `PermissionDeniedError`; `manager` of A + `tenant_id=A` + unlinked same-tenant
  unit → `UnitNotVisibleError`; `manager` of A + `tenant_id=B` + unit of B →
  `TenantNotVisibleError`; `manager` of A + `tenant_id=None` →
  `TenantScopeRequiredError`; `manager` of A + `tenant_id=A` + no `unit_id` →
  `UnitScopeRequiredError`; `owner` of A + `tenant_id=A` + no `unit_id` →
  authorized; `owner` of A + `tenant_id=A` + unit of B → `TenantNotVisibleError`;
  `platform_admin` + `MANAGE_PLATFORM` + any tenant's unit → authorized;
  `platform_admin` + `tenant_id=B` + unit of C → `TenantNotVisibleError`;
  `platform_admin` + `MANAGE_USERS` → `PermissionDeniedError` (sees everything,
  may not do restaurant work); `employee` + unlinked unit →
  `PermissionDeniedError` (precedence).
- `employee` holds no permission at all (`Role.EMPLOYEE → frozenset()`), so every
  employee command stops at step 2. That is the 2.1 RBAC map working as designed,
  not a defect here; the Stage that introduces employee self-service will need a
  permission for it. Recorded as a `[finding]`.

## References

- Related ADRs: [`2_1_0001-identity-aggregates-and-membership.md`](./2_1_0001-identity-aggregates-and-membership.md),
  [`2_1_0002-platform-admin-without-tenant.md`](./2_1_0002-platform-admin-without-tenant.md),
  [`2_2_0003-application-errors-in-identity-hierarchy.md`](./2_2_0003-application-errors-in-identity-hierarchy.md)
- Concept: [`../stages/2.2-identity-application/concept.md`](../stages/2.2-identity-application/concept.md) §5.6, §7.2
- Kickoff decisions: issue #20 body (#4)
- Roadmap: Stage `2.4-identity-http` DoD ("ação sem permissão retorna 403")

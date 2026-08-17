---
title: ADR 3.4.0008 — A permission may be declared tenant-wide, exempting it from the unit-scope requirement, so a unit-scoped role can act on a resource that belongs to the restaurant
description: Architecture Decision Record
when-use: Reference before adding a permission to TENANT_WIDE_PERMISSIONS, when a unit-scoped role is unexpectedly denied on a restaurant-level resource, or before relaxing step 4 of AuthorizeActionUseCase
keywords: [adr, authorization, unit-scope, fail-closed, permission, tenant-wide, job-function, catalogue, identity, staff]
status: accepted
created_at: 2026-08-12
updated_at: 2026-08-12
adr_id: 3.4.0008
decision: Identity gains an explicit TENANT_WIDE_PERMISSIONS set consulted by step 4 of AuthorizeActionUseCase, so a permission opted into it does not demand a unit target and a unit-scoped role such as manager or hr can manage the restaurant-level job-function catalogue; the default stays fail-closed and membership is per permission, enumerated and tested
context_stage: 3.4-staff-http
bounded_context: staff
---

# ADR 3.4.0008 — Tenant-wide permissions are exempt from the unit-scope requirement

## Status

`accepted`

## Context

The job-function catalogue belongs to the **restaurant**, not to a unit — a
canonical rule of `workforce.md` §3.2, and the reason a copied employee stays
coherent in the destination unit without recreating anything. So the four
catalogue routes have no unit to name.

But `AuthorizeActionUseCase` step 4 denies any actor that does not bypass unit
scope when no unit is declared:

```python
if command.unit_id is None and not user.bypasses_unit_scope():
    raise UnitScopeRequiredError(user.role.value)
```

and `_UNIT_SCOPE_BYPASS_ROLES = frozenset({Role.OWNER, Role.PLATFORM_ADMIN})`.
Consequence: **only `owner` can manage the catalogue**, while the roadmap DoD for
this Stage requires *"gerente cria função custom"*. Both Checkpoint A reviewers
found this independently; it was not in the first draft of the concept.

The rule that denies is correct and deliberate: omitting the unit must not be a
path to escalation (ADR 2.2.0002). The problem is not the rule — it is that the
rule assumes every restaurant-facing action targets a unit, and the catalogue is
a counterexample the model did not have when the rule was written.

The sponsor decided on 2026-08-12: keep the catalogue tenant-scoped (status quo)
and give this Stage a catalogue permission that does not require a unit.

## Decision

**1. `TENANT_WIDE_PERMISSIONS` is an explicit, enumerated set** in
`features/identity/domain/value_objects/permission.py` — a `frozenset[Permission]`
listing the permissions whose target is the restaurant rather than a unit. Today
it contains exactly one member, `MANAGE_JOB_FUNCTIONS` (ADR 3.4.0006).

**2. Step 4 consults it**, and only it:

```python
if (
    command.unit_id is None
    and not user.bypasses_unit_scope()
    and command.permission not in TENANT_WIDE_PERMISSIONS
):
    raise UnitScopeRequiredError(user.role.value)
```

**3. The default stays fail-closed, and the exemption is per permission — never
per role.** A permission is exempt only by being written into the set. A role
gains nothing: `manager` remains unit-scoped for every other permission it holds,
including `MANAGE_STAFF`. This is what keeps the exemption from becoming a
bypass: the blast radius of a mistaken entry is one capability, not one actor.

**4. Steps 3 and 5 are untouched.** Tenant scope (step 3) still applies — the
router passes the tenant of the actor, and an actor of another tenant is denied
exactly as before. Unit visibility (step 5) still runs whenever a unit **is**
declared. The exemption removes a *requirement to name a unit*; it does not
remove a check.

**5. Totality is a test.** Every member of `TENANT_WIDE_PERMISSIONS` is asserted
against an explicit expected list, so adding a permission to the set is a
deliberate, reviewed act rather than a one-word diff that no test observes. A
second test asserts that `MANAGE_STAFF` is **not** in the set — the mutation that
would silently grant cross-unit reach over employee records.

**6. Declared target-layer expansion into `features/identity`** (domain value
object plus the application use case), authorised by the sponsor.

**7. It is the foundation issue #41 will need.** Issue #41 makes job functions
enablable per unit while the function keeps belonging to the restaurant. That
feature needs "manage the catalogue" to be a first-class, separately-scoped
capability, which is exactly what this ADR and ADR 3.4.0006 create. Nothing here
presumes the design of #41; it only avoids foreclosing it.

## Alternatives considered

### Alternative A — nest the catalogue under a unit in the URL
- **Description:** `POST /units/{unit_id}/job-functions`, with the function still
  valid restaurant-wide; the unit exists only to prove membership.
- **Pros:** no change to identity at all; the existing rule applies unmodified.
- **Cons:** the URL would assert something false about where the function lives,
  permanently and publicly, and issue #41 — which introduces a *real* per-unit
  notion — would arrive to find the honest name already spent on a lie.
- **Why rejected:** it buys a smaller diff with a permanently misleading contract.

### Alternative B — add `manager` and `hr` to `_UNIT_SCOPE_BYPASS_ROLES`
- **Description:** make the two roles bypass unit scope entirely.
- **Pros:** one line.
- **Cons:** catastrophic scope creep — it would grant them tenant-wide reach over
  **every** permission, including `MANAGE_STAFF`, handing them every employee
  record in the restaurant. It fixes a catalogue problem by dissolving the unit
  axis.
- **Why rejected:** it is precisely the escalation-by-omission that step 4 exists
  to prevent.

### Alternative C — only owner and hr manage the catalogue
- **Description:** accept the status quo for `manager`.
- **Pros:** no change to identity.
- **Cons:** contradicts the DoD of this Stage, and makes a routine act (adding
  "confeiteiro") depend on the owner.
- **Why rejected:** the sponsor asked for the manager to create functions.

### Alternative D — a separate authorization use case for tenant-level actions
- **Description:** a second entry point that never asks for a unit.
- **Pros:** leaves `AuthorizeActionUseCase` untouched.
- **Cons:** two authorization paths, and the newer one is the permissive one —
  the shape most likely to drift, and the one a future author reaches for when
  the strict path is inconvenient.
- **Why rejected:** ADR 2.2.0002 centralised the decision on purpose; a second
  door reopens what it closed.

## Consequences

### Positive
- A restaurant-level capability is expressible without weakening any role.
- The DoD becomes reachable by the actor the DoD names.
- The exemption is enumerable: "which permissions do not require a unit" is a
  one-line read, and it is tested.

### Negative
- **Step 4 of the authorization guard gains a condition**, and that guard is the
  fail-closed core of the system. Any change there is security-relevant by
  definition. Mitigated by the per-permission granularity, by the two totality
  tests, and by the fact that the condition can only *exempt* a permission the
  actor already holds — it never grants one.
- A future permission added to the set by mistake would be tenant-wide silently
  from the point of view of the actor. The expected-list test is the only thing
  standing between that and production, and it must be kept exhaustive.

### Neutral / trade-offs accepted
- `owner` and `platform_admin` are unaffected: they already bypass the step.
- The catalogue routes therefore have no unit-level visibility check at all,
  which is correct — a restaurant-level resource has no unit to be visible in.

## References
- Sponsor decision, 2026-08-12, on fork F3 of
  `docs/stages/3.4-staff-http/concept.md`
- `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  (step 4) and `.../domain/entities/user.py` (`_UNIT_SCOPE_BYPASS_ROLES`)
- `docs/domain/staff/workforce.md` §3.2
- ADR 2.2.0002 (two fail-closed axes), ADR 3.4.0006 (the two staff permissions)
- Issue #41 — per-unit enablement of job functions

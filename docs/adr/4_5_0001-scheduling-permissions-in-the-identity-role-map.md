---
title: ADR 4.5.0001 — The scheduling permissions enter identity's Permission enum and role map, view_own_schedule is held by every restaurant role, and the tenant-wide manage_schedule_settings is owner-only
description: Architecture Decision Record
when-use: Reference before granting a scheduling permission to a role, before adding a route that requires one, before Stage 4.8 consumes the configuration permission, or when the who-creates-whom matrix of identity changes
keywords: [adr, scheduling, identity, rbac, permission, role-map, tenant-wide, view_own_schedule, manage_schedule_settings]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: 4.5.0001
decision: 'Permission gains view_schedule, manage_schedule and view_own_schedule (unit-scoped) and manage_schedule_settings (tenant-wide); owner holds all four, manager the three unit-scoped, hr view_schedule and view_own_schedule, employee view_own_schedule, platform_admin none; manage_schedule covers edit, evaluate, acknowledge and publish; hr can no longer create or invite a manager, by the existing rule that a creator must hold every permission of the created role.'
context_stage: 4.5-scheduling-http
bounded_context: scheduling
---

# ADR 4.5.0001 — Scheduling permissions in the identity role map

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-23 (Stage 4.5, issue #254). Three of the choices below were product forks
(class P) that the sponsor delegated to the implementing session; each records the option taken
and why.

## Context

ADR 4.1.0004 fixed three unit-scoped families of scheduling capability — **read**, **manage**,
**own** — and who holds each (hr reads its member units; manager and owner read and manage;
employee gets "own"; platform_admin nothing). It left to Stage 4.5 the names, whether "save" and
"edit" are one permission, and whether the tenant-wide configuration needs its own permission
(ADR 4.1.0004 › "are gaps for the Stage 4.5 concept"). Stage 4.3 already put the three values in
scheduling's port as strings (`access_guard.py` › `PERMISSION_VIEW_SCHEDULE`,
`PERMISSION_MANAGE_SCHEDULE`, `PERMISSION_VIEW_OWN_SCHEDULE`), and decided save = edit (concept 4.3
D-PERM). The roadmap asks 4.5 to decide and record the configuration permission that Stage 4.8
consumes (`roadmap.md` §Stage 4.8 › `contratos_consumidos`).

Two existing identity rules interact with any new permission:

- `required_permissions_for_role` — whoever creates a user of role R must hold `manage_users`
  **and** every permission R holds ("não se concede o que não se detém", concept 2.4 §5 rule 4).
- The frozen who-creates-whom matrix (`test_matriz_de_quem_cria_quem_nao_regride`) asserts that no
  vocabulary growth changes who can create whom.

## Decision

1. **Four new `Permission` members**: `VIEW_SCHEDULE = "view_schedule"`,
   `MANAGE_SCHEDULE = "manage_schedule"`, `VIEW_OWN_SCHEDULE = "view_own_schedule"` (unit-scoped)
   and `MANAGE_SCHEDULE_SETTINGS = "manage_schedule_settings"`, which joins
   `TENANT_WIDE_PERMISSIONS` (ADR 3.4.0008: the target is the restaurant, not a unit).
2. **`manage_schedule` is one permission for edit, evaluate, acknowledge `warn` and publish.**
   Under F1 every saved change is the live schedule (ADR 4.1.0001), so "save" and "edit" are the
   same act.
3. **Role map additions**: owner — all four; manager — `view_schedule`, `manage_schedule`,
   `view_own_schedule`; hr — `view_schedule`, `view_own_schedule`; employee — `view_own_schedule`;
   platform_admin — none.
4. **`view_own_schedule` is held by every restaurant role** (P delegated — all restaurant roles).
   Managers and owners who work shifts got a login link in Stage 3.10 precisely to see "my
   schedule"; and without it identity's create and invite routes would stop managers, hr and owners
   from creating employees, whose role now holds the permission. Staff's login creation (R17) goes
   through the facade, which skips the rule (ADR 2.7.0001 §Decision 5); there the risk is the
   opposite one, and it is closed by a property test: every role holding `manage_staff` and
   `manage_users` (R17's requirement) holds what `employee` holds.
5. **`manage_schedule_settings` is owner-only** (P delegated — owner only). The configuration is
   restaurant-wide, and a manager sees only its member units (ADR 2.1.0001, axis B): granting it
   would let a manager change the rule of units it cannot see — and, the permission being
   tenant-wide, widening it to the manager would grant exactly that reach, so widening needs a new
   sponsor decision. While only the owner holds it, the `TENANT_WIDE_PERMISSIONS` entry changes no
   access decision (the owner already bypasses the unit, ADR 3.4.0008); it classifies the target, the
   restaurant, which is the set's criterion. No route requires it in Stage 4.5; Stage 4.8 consumes
   it, extends the scheduling guard port with a restaurant-wide target (an application port change)
   and decides who reads the configuration.
6. **hr no longer creates or invites a manager** (P delegated — accept the consequence). The
   creation rule now requires `manage_schedule` to create a manager, and hr does not hold it. The
   frozen matrix gets a new dated baseline that differs from the old one only in that cell. This is
   the first vocabulary growth that does not make the requirement "stricter only on permissions the
   creator gained in the same act": hr does not gain `manage_schedule`. The `role.py` comment that
   manager and hr "coincide in identity" is rewritten — they coincide on identity's and staff's
   permissions and diverge on the schedule.

## Alternatives considered

### Alternative A — `view_own_schedule` only for employee
- **Pros:** narrowest literal reading of ADR 4.1.0004 §Decision 4.
- **Cons:** manager, hr and owner could no longer create employees (they would not hold the
  employee's permission); the manager who works shifts and was linked in Stage 3.10 would not see
  "my schedule".
- **Why rejected:** breaks user creation and the purpose of Stage 3.10.

### Alternative B — exclude scheduling permissions from `required_permissions_for_role`
- **Pros:** keeps the who-creates-whom matrix untouched (hr keeps creating managers).
- **Cons:** hr would create an account that manages the schedule, a power hr itself does not
  hold — the escalation the rule exists to close, and against the sponsor's "only the manager or
  owner touches the schedule" (ADR 3.4.0006 §1, kept by ADR 4.1.0004 §Decision 2).
- **Why rejected:** fail-closed (ADR 2.2.0002).

### Alternative C — `manage_schedule_settings` for owner and manager (precedent `MANAGE_JOB_FUNCTIONS`)
- **Pros:** follows the job-function catalogue precedent (ADR 3.4.0008).
- **Cons:** the catalogue only names functions; the configuration changes what blocks and what
  warns in every unit, and when the operational day starts.
- **Why rejected:** fail-closed; additive to widen later.

### Alternative D — leave the configuration permission to Stage 4.8
- **Pros:** no member without a consumer today.
- **Cons:** Stage 4.8 would deliver in identity, and the roadmap assigns the decision here.
- **Why rejected:** the roadmap (`roadmap.md` §Stage 4.8) and ADR 4.1.0004 put the decision in 4.5.

### Do nothing
Not applicable: no scheduling route can be authorized without the enum members.

## Consequences

### Positive
- The three families of ADR 4.1.0004 become observable, per role, in a totality-tested map.
- The creation rule covers the new permissions with no second table.

### Negative
- hr loses the ability to create or invite managers. An owner or manager has to do it.
- `manage_schedule_settings` has no consumer until Stage 4.8.

### Neutral / trade-offs accepted
- A terminated employee whose account remains still authenticates; "my schedule" reads only active
  linked records and answers empty (ADR 3.5.0003 §3). The account-deactivation trigger of ADR
  3.5.0003 §5 is re-addressed to an identity issue (concept 4.5 §7 D-DEACT).

## Implementation notes

- Files: `features/identity/domain/value_objects/{permission,role}.py`; the docstring of
  `features/identity/application/facade.py` (property 3); tests `test_role_permission.py`,
  `test_http_dependencies.py` (matrix baseline and the R17 pin, rewritten as "every role holding
  `manage_staff` and `manage_users` holds what an employee holds").
- Dated notes on ADR 3.4.0006, ADR 4.1.0004, ADR 3.5.0003 and ADR 2.7.0001 (and on ADR 4.3.0002 for the port change of ADR 4.5.0003).
- Concept: [`../stages/4.5-scheduling-http/concept.md`](../stages/4.5-scheduling-http/concept.md) §7
  D-PERM, D-OWNALL, D-CONFIG, D-CREATE.

## References

- [ADR 4.1.0004](./4_1_0004-hr-reads-schedules-in-member-units.md),
  [ADR 3.4.0006](./3_4_0006-staff-rbac-two-permissions-and-hr-parity.md),
  [ADR 3.4.0008](./3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md),
  [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md),
  [ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md),
  [ADR 4.1.0001](./4_1_0001-every-saved-change-is-the-live-schedule.md),
  [ADR 3.5.0003](./3_5_0003-termination-revokes-sessions-account-remains.md)

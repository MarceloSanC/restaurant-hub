---
title: ADR 4.1.0004 — hr reads the schedule and the calendar of the units it belongs to (unit-scoped read permission), never writes or publishes — superseding in part the forward constraint of ADR 3.4.0006 §3
description: Architecture Decision Record
when-use: Reference before extending the identity role map for scheduling, before granting or denying any schedule capability to hr, or when reading ADR 3.4.0006 §3 ("must not grant hr any permission over the schedule") and needing to know how far it still binds
keywords: [adr, rbac, permission, role, hr, manager, owner, employee, scheduling, read, manage, own, unit-scoped, supersedes-in-part, identity]
status: accepted
created_at: 2026-09-13
updated_at: 2026-09-13
adr_id: 4.1.0004
decision: Scheduling capabilities come in three unit-scoped families — read (live schedule + calendar of a unit), manage (edit demand and allocations, acknowledge warnings, save) and own ("my schedule") — and hr receives the read family for the units it is a member of, while manage stays with manager and owner and own goes to employee; this supersedes in part ADR 3.4.0006 §3, whose "any permission over the schedule" now reads as "any write permission".
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0004 — hr reads schedules in its member units

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

Supersedes **in part** [ADR 3.4.0006](./3_4_0006-staff-rbac-two-permissions-and-hr-parity.md)
§3 ("Stage 4.x must not grant `hr` any permission over the schedule"): the write half of that
constraint stands; the read half is lifted. ADR 3.4.0006 keeps `status: accepted` and receives
an errata banner dated 2026-09-13 (CONVENTIONS §5) pointing here.

## Context

Taken at the **domain gate of Step 4** (2026-09-13) for
[`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md), fork
F5 of the gate triage. Decided by the **human sponsor** (Marcelo, 2026-09-13).

Forces:

- On 2026-08-12 the sponsor decided, verbatim, *"RH pode mexer nos cadastros dos funcionários
  (cadastrar, desativar, editar etc). Apenas o gerente ou dono pode **mexer** na escala."*
  [ADR 3.4.0006](./3_4_0006-staff-rbac-two-permissions-and-hr-parity.md) §3 generalised that
  into a binding forward constraint: *"Stage 4.x must not grant `hr` **any** permission over the
  schedule."*
- In this system **reading also requires a permission** — every route declares the set it
  requires ([ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md) §1) and the
  authorization axes fail closed ([ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md)).
  So "any permission" literally denies hr the schedule screen — including the case where hr has
  just registered an unavailability and wants to see whether it collides with an allocation.
- `overview.md` §5 › "Montar/ajustar escala rápido" (2026-07-23 — earlier than the decision) still lists "Gerente / RH"
  as primary users who "montam/ajustam escala". Overview outranks the ADR in the doc hierarchy,
  but the ADR is the later, sponsor-made decision; the skeptic review (finding #7) required this
  contradiction to be resolved by a dated note in the overview **in the same PR**, not by a
  proposal.
- `workforce.md` §4 says *"é NO STAFF que hr diverge do manager"*; ADR 3.4.0006 placed the
  divergence on the scheduling axis instead, and the Stage 3.6 concept (finding, lines 926–933)
  asked for a dated note in `workforce.md` §4 when the divergence became text.
- The `employee` role has an empty permission set today (`role.py` 77) and must gain one to see
  "my schedule" ([ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md) 231–234) — so a
  read-type capability distinct from "manage" is born in Step 4 regardless of hr.

## Decision

Sponsor: *"Sim — leitura nas suas unidades"*.

1. **Three families of scheduling capability, all unit-scoped** (the schedule belongs to the
   unit — domain doc §3.1; unit exemption is by permission, never by role,
   [ADR 3.4.0008](./3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md)):
   - **read** — the live schedule and the calendar of a unit;
   - **manage** — edit demand and allocations, acknowledge `warn` violations, save;
   - **own** — "my schedule": only the caller's own allocations.
2. **`hr` receives `read` for the units it is a member of.** It does not edit, acknowledge or
   save. The sponsor's original word — *mexer* — is honoured; *ler* is granted.
3. **`manager` and `owner` receive `read` + `manage`** (owner across every unit of the tenant,
   by visibility bypass — [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md)).
4. **`employee` receives `own`** (a new permission, created by the Stage that exposes "my
   schedule"). **`platform_admin`** receives nothing.
5. **Reconciliation, in this PR:** ADR 3.4.0006 gets the errata banner; `overview.md` §5 › "Montar/ajustar escala rápido"
   gets a dated note (hr **consults** the schedule; building/adjusting is manager/owner);
   `workforce.md` §4 gets a dated note (the hr × manager divergence is on the **schedule** —
   read, not manage).

Permission **names** (`VIEW_SCHEDULE`, `MANAGE_SCHEDULE`, `VIEW_OWN_SCHEDULE`, …), whether
"save" and "edit" are one permission, and whether the tenant-wide **validation configuration**
needs its own permission are gaps for the Stage 4.5 concept.

## Alternatives considered

### Alternative A — Literal ADR 3.4.0006: hr holds no schedule permission at all, not even read (triage's recommendation)
- **Description:** hr never opens the schedule tab; it sees vacations only in the employee record.
- **Pros:** zero cost; follows the letter of the standing ADR; the read/manage split is installed
  by `employee` anyway, so granting read to hr later is one line in `role.py`.
- **Cons:** hr registers an unavailability "blind"; the collision only appears to the manager;
  an HR person cannot answer "is João scheduled on the Thursday of his vacation?".
- **Why rejected:** **the sponsor rejected it.** It was the triage's recommended option;
  recorded so the recommendation is not read back as the decision.

### Alternative B — hr sees only the calendar of the employee whose record it is editing
- **Description:** a read-only calendar embedded in the staff screen.
- **Pros:** narrowest possible exposure.
- **Cons:** a staff → scheduling crossing in the API and UI for one use case; more complex than
  a unit-scoped read permission; couples screens.
- **Why rejected:** overengineering relative to B's one line in the role map.

### Alternative C — hr ≡ manager on the schedule (read + manage)
- **Pros:** simplest role map.
- **Cons:** discards the sponsor's 2026-08-12 decision ("apenas o gerente ou dono pode mexer na
  escala") and the whole content of the hr/manager divergence.
- **Why rejected:** contradicts a standing sponsor decision; the sponsor confirmed "leitura",
  not "mexer".

### Do nothing / status quo
Not applicable: Stage 4.5 must extend the role map, and the forward constraint of ADR 3.4.0006
would have made the read grant a violation without this record.

## Consequences

### Positive
- hr can verify its own registrations against the live schedule without asking the manager.
- The hr/manager divergence finally has observable content (hr reads, manager manages) — the
  role map is testable on the schedule axis, which ADR 3.4.0006 could only promise.
- Three families (read / manage / own) give Stage 4.5 a vocabulary that also expresses the
  employee's self-service without a second refactor.

### Negative
- A standing `accepted` ADR now carries an errata banner — the reader must follow two documents
  to know what hr may do. Mitigated by the banner pointing here and by this ADR restating the
  surviving half of the constraint.
- Three documents receive dated notes in one PR (overview §5, workforce §4, ADR 3.4.0006).

### Neutral / trade-offs accepted
- hr's reach does not change: **member units only**, as in staff. Cross-unit reach for hr was
  rejected in ADR 3.4.0006 and is not reopened here.
- Whether the validation configuration (tenant-wide) is a fourth family is left to 4.5.

## Implementation notes

- Lands in Stage 4.5 (role map entries in `features/identity/domain/value_objects/{permission,
  role}.py` — a declared expansion into identity, authorised by the sponsor in ADR 3.4.0006 §5;
  routes declaring `read` vs `manage`). Theory: [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §4.
- The role map's totality test forces every role to be classified for each new permission.

## References

- Related ADRs: [ADR 3.4.0006](./3_4_0006-staff-rbac-two-permissions-and-hr-parity.md)
  (superseded in part — §3; errata 2026-09-13); [ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md)
  (fail-closed axes; `employee` needs a permission, 231–234); [ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md)
  (permission set declared per route); [ADR 3.4.0008](./3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md)
  (unit exemption by permission); [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md)
  (owner visibility bypass).
- [`overview.md`](../overview.md) — §3 › "RBAC: papéis dono, gerente, RH e funcionário", "funcionário com login consulta a própria escala" (RBAC; employee
  consults own schedule); §5 › "RH consulta a escala" (dated note added in this PR).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §4 (dated note added in this
  PR); `docs/stages/3.6-staff-http/concept.md` 926–933 (finding that asked for it).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.7,
  §4, §6.
- `src/restaurant_hub/features/identity/domain/value_objects/role.py` (lines 50–52, 77);
  `permission.py` (8–9, 32–44).
- Sponsor decisions: 2026-08-12 (ADR 3.4.0006 — "apenas o gerente ou dono pode mexer na
  escala"); 2026-09-13, fork F5 — *"Sim — leitura nas suas unidades"* (session record
  `gate-decisions.md`).
- Process: [`CONVENTIONS.md`](../CONVENTIONS.md) §5 (errata banner, append-only, no body edit).
- External: none — an access-control product decision.

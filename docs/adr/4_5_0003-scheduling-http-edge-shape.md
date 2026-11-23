---
title: ADR 4.5.0003 — The scheduling HTTP edge addresses the unit in the path, authenticates and authorizes through the scheduling AccessGuard port (now with authenticate and an optional tenant) implemented over identity's access facade, answers "my schedule" per unit and flags a demand whose function is no longer enabled
description: Architecture Decision Record
when-use: Reference before adding a scheduling route, before promoting an access guard to shared/, before composing "my schedule" across units, or before changing how the edge shows a stale demand
keywords: [adr, scheduling, http, access-guard, edge, my-schedule, unit, orphan-demand, wall-clock, batch]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: 4.5.0003
decision: 'Scheduling routes live under /units/{unit_id}; the scheduling AccessGuard port gains authenticate and an optional tenant_id (the actor tenant when omitted, unit still required), implemented by a LocalAccessGuard in scheduling/adapters/out/identity over IdentityAccessFacade, and the guard is not promoted to shared/; "my schedule" answers per unit; DemandResult gains function_enabled_in_unit; band limits travel as ISO wall-clock without offset; batches are capped at 500 operations; the edge returns violation codes and measures, never text.'
context_stage: 4.5-scheduling-http
bounded_context: scheduling
---

# ADR 4.5.0003 — Shape of the scheduling HTTP edge

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-23 (Stage 4.5, issue #254). Decisions 3 and 4 were product forks (class P)
delegated by the sponsor to the implementing session.

## Context

Stage 4.3 left authentication to the edge ("Só `authorize`. A autenticação é da borda (4.5)",
`access_guard.py`) and a port that requires both tenant and unit. The edge does not know the tenant
— it comes from the token (ADR 0.0.0005) — and the token does not carry the actor's units. The
domain doc asks 4.5 to decide whether the `AccessGuard` is promoted to `shared/` (§3.10.2: "a 4.5 é
o segundo consumidor (LAYOUT §4) e decide"). ADR 4.3.0005 asks how the edge flags a demand recorded
before staff narrowed the function.

## Decision

1. **The port takes staff's shape** (ADR 3.7.0001): `authenticate(request) -> Actor` and
   `authorize(actor, permission, *, tenant_id: str | None = None, unit_id: str)`; an omitted tenant is
   the actor's (ADR 0.0.0005 clause 3), the unit stays required, and a new law L-SG5 says the scope
   then carries the actor's tenant and an actor without tenant is denied. The use cases keep passing
   the named tenant. The edge depends on the port (LAYOUT §5), not on a protocol of its own.
2. **The adapter** `scheduling/adapters/out/identity/local_access_guard.py` implements it over
   `IdentityAccessFacade` and the `authenticate_principal` callable the composition root injects (the
   shape of ADR 0.0.0016). A second named pair enters `bc-independence`:
   `scheduling.adapters.out.identity.* -> identity.application.facade`. **No promotion to
   `shared/`**: the two ports still differ (scheduling: unit required, the subject in the scope;
   staff: unit optional, no subject). LAYOUT §4 measures reuse; ADR 4.3.0002 chose a port per BC.
3. **"My schedule" answers per unit** (P delegated — route per unit). Composing all of the actor's
   units needs a new identity facade read (facade-only inventory, ADR 0.0.0020) or a staff read by
   login across units; both are deliveries outside the edge. The per-unit route is the primitive the
   composed one reuses (re-addressed to issue #258). Declared limit: no route returns a login its own
   units yet, so #258 is a prerequisite of a pilot with employees.
4. **`DemandResult.function_enabled_in_unit`** (P delegated — a flag per demand). The editor's use
   cases already read the unit's enabled functions; the calendar starts reading them too. The edge
   exposes the flag on every demand, so a stale demand reads as "uncovered, function no longer
   enabled here" without a second request.
5. **Wire shapes**: band limits as ISO 8601 without offset (wall-clock of the unit), an offset value
   refused by the domain with 422 and never converted (ADR 3.6.0003 §Decision 3); days as
   `YYYY-MM-DD`; decimals of a violation as strings (ADR 3.6.0003 §Decision 2); the batch is a list of
   operations discriminated by `op`, each variant `extra="forbid"`; at most 500 operations and 500
   acknowledgements per request; creation ids in canonical UUID text; every identifier refuses empty,
   whitespace-only and NUL before authorization (ADR 3.6.0002); a quantity above the Postgres
   `INTEGER` range is refused with 422.
6. **No violation text.** The edge returns policy, mode, subject, days and measure; wording is the
   client's (concept 4.2 §5.12: "a mensagem é da borda" — the client being that edge's consumer).

## Alternatives considered

### Alternative A — a protocol declared in the inbound adapter, implemented by the outbound adapter
- **Pros:** the 4.3 port stays untouched.
- **Cons:** a port living under `adapters/`, a shape LAYOUT §5 does not know; staff's precedent puts
  `authenticate` on the application port.
- **Why rejected:** the Checkpoint A of Stage 4.5 measured it as an undeclared LAYOUT divergence; the
  port change is small (one method, one optional argument, one law) and follows the precedent.

### Alternative B — promote one `AccessGuard` to `shared/`
- **Why rejected:** two different contracts; a shared port would carry the union of both.

### Alternative C — compose "my schedule" across units now
- **Why rejected:** delivery in identity or staff outside the edge; additive later.

### Alternative D — the client crosses demands with staff's unit-function list
- **Cons:** two non-atomic reads; requires `manage_job_functions` of whoever only reads the schedule.
- **Why rejected:** the server already has the fact at read time.

### Alternative E — server-side violation sentences in Portuguese
- **Why rejected:** first UI string of the API, no i18n, and the client still needs the codes.

## Consequences

### Positive
- The edge reuses identity's decision and 401/403 bodies byte-for-byte.
- Stage 4.8 extends the same adapter with a tenant-wide target.

### Negative
- A login with records in several units calls "my schedule" once per unit and has no route that
  lists its units yet (#258).
- The 4.3 port changes in an HTTP Stage (declared divergence, concept 4.5 §1).
- `DemandResult` grows a field in an HTTP Stage (declared divergence, concept 4.5 §1).

## References

- [ADR 0.0.0005](./0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md),
  [ADR 0.0.0016](./0_0_0016-staff-access-guard-is-an-adapter-over-an-identity-access-facade.md),
  [ADR 0.0.0020](./0_0_0020-identity-use-cases-authorize-their-own-target.md),
  [ADR 3.6.0002](./3_6_0002-boundary-identifier-validation.md),
  [ADR 3.6.0003](./3_6_0003-wire-representation-preserves-domain-guarantees.md),
  [ADR 4.3.0002](./4_3_0002-every-scheduling-use-case-authorizes-its-own-target.md),
  [ADR 4.3.0004](./4_3_0004-client-ids-and-one-write-carrying-the-change-record.md),
  [ADR 4.3.0005](./4_3_0005-demand-accepts-only-functions-enabled-in-the-unit.md)
- Concept: [`../stages/4.5-scheduling-http/concept.md`](../stages/4.5-scheduling-http/concept.md) §7

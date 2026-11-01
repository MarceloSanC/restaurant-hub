---
title: ADR 3.7.0001 — Every staff use case authorizes its own target through the injected AccessGuard
description: Architecture Decision Record
when-use: Reference before adding a staff use case, changing a staff command, or deciding where authorization runs in another bounded context's application layer
keywords: [adr, staff, authorization, access-guard, application, fail-closed, defense-in-depth]
status: accepted
created_at: 2026-10-19
updated_at: 2026-10-19
adr_id: 3.7.0001
decision: Every staff use case receives the AccessGuard by constructor and, before any other statement, authorizes the target its command declares — the tenant is confirmed, not derived — while the HTTP boundary keeps its own authorization as defense in depth
context_stage: 3.7-application-authorization
bounded_context: staff
---

# ADR 3.7.0001 — Every staff use case authorizes its own target through the injected AccessGuard

## Status

`accepted`

Partially supersedes, each by a dated append-only note in the superseded ADR
(CONVENTIONS §5):

- **ADR 3.2.0002** — its statement that staff use cases *"deliberately take no
  actor (authorization is Stage 3.4…)"* stops being true: the actor now travels
  in every command (§2).
- **ADR 3.6.0004** — its principle *"the cheapest local check that can fail on
  its own comes first"* now applies **after** the authorization block, which does
  I/O and precedes every check (§4).
- **ADR 3.4.0001 §4** — the caveat that LAYOUT §5 is "not yet literally true" is
  discharged **for `authorize` only**; `authenticate` keeps a single consumer, the
  inbound adapter (§Consequences).

Answers without superseding **ADR 0.0.0005, Alternatives B and C**: their
rejection reasons are addressed for the application layer (Alternative G below).
No clause of 0.0.0005's decision changes — the HTTP boundary still omits the
tenant and resolves it in the composition root — so 0.0.0005 gets no note.

## Context

Issue #49 measured that `AccessGuard` (ADR 3.4.0001) is a **driven** port whose
only consumer was the **driving** adapter: the 17 staff use cases never call it.
`ListEmployeesUseCase.execute(ListEmployeesQuery(tenant_id, unit_id))` returns
whatever the caller asks for. Tenant and unit isolation is a discipline of
`adapters/inbound/http/router.py`, not a property of the application — and the
premise of Ports & Adapters is that the application behaves the same whatever
drives it. A worker, a CLI or the next bounded context calling a staff use case
would enter with no check. Issue #45's Gate 2 (deny-by-default over `app.routes`)
closes the HTTP door; it cannot close a door that is not HTTP.

ADR 3.4.0001 §4 already recorded the debt: the port was placed in
`application/ports/out/` *anticipating* a use-case consumer, and LAYOUT §5 —
"driven ports are what the use case consumes" — was declared **not yet literally
true**. ADR 3.2.0002 had written the other half of the same choice: staff use
cases *"deliberately take no actor"*, because authorization was to be a Stage
3.4 concern.

Forces and constraints already ratified:

- **LAYOUT §5 and ADR 0.0.0006** fix the driving port as
  `execute(<Command>) -> <Result>`: one argument, a DTO.
- **ADR 0.0.0005 clause 1**: the tenant that decides access derives from the
  token; a tenant that arrives with the request is a *declaration confirmed
  against* it. Clause 3: for staff, the token is read in the composition root,
  because the port keeps `Actor = object`.
- **ADR 3.2.0002** and the `commands.py` docstring: every staff command carries
  `tenant_id`, and the ones on an existing record carry `unit_id` too — no
  operation is expressible without scope.
- **ADR 3.6.0001**: the path addresses the record, not the authorized scope; no
  route reads `AuthorizedScope.unit_id`.
- The four port laws (L-AG1..L-AG4), the `str` permission vocabulary and the role
  matrix are non-goals of #49 and do not change.
- Issue #49's done-criteria already name the shape: *every write and scoped-read
  use case receives the guard by constructor*.

## Decision

**1. The guard is injected into every staff use case by constructor.** All 17
use cases gain a `guard: AccessGuard` parameter, wired in `composition_root.py`
to the same `staff_access_guard` instance the router uses. "Every" is literal:
the catalogue reads (`list_job_functions`) and the lifecycle transitions are
included. Issue #49's uncertainty — all use cases, or only the ones that cross
tenant/unit — resolves to *all*, because every one of the 17 carries a tenant in
its command and therefore crosses the tenant line; no exception had a written
justification, which is the burden the issue placed on exceptions.

**2. The actor travels inside the command.** Every staff command and query gains
a first field `actor: Actor` (`Actor = object`, the port's opaque credential),
declared `field(repr=False)`. `execute` keeps its single-argument shape. The
command now states *who asks* alongside *what is asked*, and a caller that has
no actor cannot form the request by omission. (An explicit `actor=None` still
type-checks — `Actor` is `object` — and is refused by the guard, not by the
type system: see the threat model below.)

**3. The use case authorizes the target its command declares, and the tenant is
confirmed, not derived.** The call passes the command's own target explicitly:

```python
self._guard.authorize(
    command.actor, PERMISSION_MANAGE_STAFF,
    tenant_id=command.tenant_id, unit_id=command.unit_id,
)
```

With `tenant_id` named, the production chain refuses an actor of another tenant
at the first check that applies to it: identity's step 2 (RBAC —
`PermissionDeniedError`, which is where `employee` and `platform_admin` stop for
staff permissions), then step 3 (`_assert_tenant_scope` —
`TenantNotVisibleError` for `owner`/`manager`/`hr` of another tenant), and, for
an actor with no tenant that slipped through, L-AG3 in the composition-root
translator. The use case then operates on the command's target, which is the
target that was authorized. **The returned `AuthorizedScope` is not read by any
use case**: the guard is the confirmer, never the source of the address — the
application-layer twin of ADR 3.6.0001.

Targets follow the access requirements the router already declares
(`dependencies.py`), unchanged:

| Use cases | Permission | Target |
|---|---|---|
| the 4 catalogue use cases | `manage_job_functions` | tenant only (`TENANT_WIDE_PERMISSIONS`, ADR 3.4.0008) |
| the 11 employee use cases other than copy and create-login | `manage_staff` | tenant + the command's unit |
| `copy_employee_to_unit` | `manage_staff`, **twice** | origin unit, then target unit (L-AG4) |
| `create_login_for_employee` | `manage_staff`, then `manage_users` | tenant + the command's unit, both times |

**4. Authorization precedes every other statement of `execute`.** No port is
touched before the decision — no repository read, no id generated, no gateway
call — and no pure check either: a denied caller must learn nothing, and a
validation error returned before the decision would be an oracle about the
request's shape. Multi-target use cases authorize **all** targets before the
first port call, so a denial on the second target is as effect-free as a denial
on the first. The ordering of business checks among themselves (concept 3.2
§5.16, ADR 3.6.0004) applies **after** the authorization block, unchanged.

**5. The permission vocabulary moves to the port module.** The three values
(`PERMISSION_MANAGE_STAFF`, `PERMISSION_MANAGE_JOB_FUNCTIONS`,
`PERMISSION_MANAGE_USERS`) move from `adapters/inbound/http/dependencies.py` to
`application/ports/out/access_guard.py`, where the port docstring already cites
them; the adapter imports them from there. They keep their names and stay `str`
values, never an identity enum.

**6. The HTTP boundary keeps authorizing.** The router's `guard.authorize` calls,
their order (authenticate → validate → authorize) and their status bands stay as
they are: the boundary becomes defense in depth, not the only line (#49
non-goal). It still takes the command's `tenant_id` from `AuthorizedScope`, the
only place the token's tenant reaches it.

### Threat model — what "fail-closed by itself" means here

The guarantee this ADR buys is: **no staff use case produces an effect unless
the guard authorizes, for the command's own target, the actor the command
carries.** It does **not** make the actor authentic. Authenticity is the job of
`AccessGuard.authenticate`, which the driver calls; the production chain — the
translator, then identity's `IdentityGuard.authorize`, which reads
`actor.claims.subject` — does not check that the actor came from
`authenticate` (the fake enforces "an actor this guard did not issue is denied",
production does not). An in-process driver that forges an `AuthenticatedActor`
therefore passes. Before this Stage that gap was unreachable — the router was
the only actor source; it becomes relevant with the first non-HTTP driver, and
is recorded as a finding for the Stage that creates one. A non-actor object
(`actor=None`) is refused, but as a raw `AttributeError` from `IdentityGuard`, not
as an access error — fail-closed, untyped.

## Alternatives considered

### Alternative A — An authorizing decorator / application service around the use cases
- **Description:** keep the 17 use cases unaware of access; wrap each in an
  `Authorizing<X>` (or one generic wrapper with a per-use-case requirement table)
  that the composition root exposes instead of the raw use case.
- **Pros:** use cases stay single-purpose; the requirement table lives in one
  place.
- **Cons:** the unguarded inner use case still exists and is constructible by any
  driver — fail-closed becomes a property of the wiring, which is the exact
  shape #49 refutes (a property of one adapter, now of one module). The wrapper
  must know how to extract the target from each command type, re-encoding every
  command's address in a second place.
- **Why rejected:** the guarantee must hold for whoever constructs the use case,
  not for whoever wires it; issue #49's done-criteria name constructor injection.

### Alternative B — The actor as a second `execute` parameter
- **Description:** `execute(command, actor)` (or `execute(actor, command)`), with
  commands unchanged.
- **Pros:** the command stays pure intent; no DTO field holds a credential.
- **Cons:** changes the driving-port shape that LAYOUT §5 and ADR 0.0.0006 state
  as `execute(<Command>) -> <Result>`; the churn on call sites is the same.
- **Why rejected:** convention without a winner; the shape already ratified in
  the project decides.

### Alternative C — Derive the tenant from `AuthorizedScope`, removing `tenant_id` from commands
- **Description:** commands lose `tenant_id`; the use case calls `authorize` with
  the tenant omitted and operates on `scope.tenant_id`.
- **Pros:** no caller can even name a tenant.
- **Cons:** contradicts ADR 3.2.0002's command contract and makes the use case
  read the scope that ADR 3.6.0001 forbids the boundary to read for the unit —
  two rules for the same object. For the unit there is no such option at all
  (the scope echoes the requested unit, `authorize_action.py:113`), so the
  address would come from two different sources.
- **Why rejected:** confirming the declared target keeps one address source (the
  command) and one authority (the guard).

### Alternative D — Guard only the use cases that cross tenant/unit
- **Why rejected:** every staff command carries a tenant; a catalogue read for
  another tenant is a cross-tenant read. The issue required a written
  justification per exception; none survives.

### Alternative E — Move authorization out of the HTTP boundary
- **Why rejected:** explicit non-goal of #49. The router's call also keeps the
  identifier-validation order (CA21 of Stage 3.6, ADR 3.6.0002): validation runs
  before the first identity read. The application has no identifier validation,
  so a non-HTTP driver sending a raw `\x00` id reaches `units.find_by_id` inside
  identity (`DataError`, untyped) — fail-closed, recorded as a finding.

### Alternative F — Status quo
- Fail-closed remains a discipline of one adapter; any non-HTTP driver bypasses
  it. That is the defect #49 names.

### Alternative G — Do not name the tenant (answering ADR 0.0.0005 Alternatives B and C)
- **What 0.0.0005 rejected:** B — every `authorize` call naming its target in
  full, because it moves the tenant into many call sites and *"an input is
  manipulable in a way an outcome is not"*; C's cost — *"a comparison that can
  only ever fail on abuse"* is redundancy that must still be tested.
- **Why it does not carry over to the application:** both arguments were about
  the **HTTP** boundary, where the only tenant source is the token and the
  composition root resolves it. At the application layer the command's tenant
  **is** an input — every non-HTTP driver supplies one — and confirming it is the
  only check such a driver meets. The comparison is redundant on the HTTP path
  (the router names the scope's own tenant, so it never fails there) and
  load-bearing on every other path. Its test cost is accepted, not avoided: the
  real-chain test runs per use case × per role (17 × 5) — the price 0.0.0005
  called *"the worst of both"* for HTTP, paid here because at this layer the
  comparison is the only line a non-HTTP driver meets. The trusted
  layer is unchanged: identity still decides against the user loaded from its
  repository.

## Consequences

### Positive
- No staff use case produces an effect without the guard authorizing its target
  — pinned by a property over the whole `use_cases/` folder, by a structural
  check of every `execute`, and through the real identity chain for every role.
- `AccessGuard.authorize` becomes a driven-port operation in the literal sense of
  LAYOUT §5.
- `create_login_for_employee` and `deactivate_employee` — the two use cases that
  act on identity through `IdentityGateway` — now authorize before crossing the
  bounded-context edge.

### Negative
- **Every staff HTTP request authorizes twice** (router + use case). The 17 use
  cases add 19 `authorize` calls (copy and create-login make two each) on top of
  the router's 19. Each call is `users.find_by_id` and, when a unit is named,
  `units.find_by_id` plus `users.list_memberships` (`authorize_action.py:80,142,
  153`). Accepted: the boundary call is a non-goal of #49, and the reads are by
  key; not measured under load.
- Every command construction now names an actor; test suites pay a mechanical
  churn once.
- **`AccessGuard.authenticate` keeps a single consumer, the inbound adapter.**
  Its parameter is the HTTP request; a driver-agnostic authentication operation
  is not designed here. Recorded as a finding.

### Neutral / trade-offs accepted
- A future non-HTTP driver will need an actor the guard recognises — a system
  actor or a delegated one — and its own identifier validation.
- Identity's facade still does not authorize (ADR 3.5.0001 §1); extending the
  pattern to identity is a non-goal of #49.

## Implementation notes

- Properties live at
  `tests/unit/features/staff/application/test_use_cases_authorize.py` (denying
  guard ⇒ no effect; folder totality; exact targets; infidel scope ignored) and a
  structural AST check of every `execute`; the real-chain test (translator →
  `IdentityGuard` → `AuthorizeActionUseCase` over in-memory identity
  repositories) lives next to the composition-root tests.
- `actor` is `repr=False` because staff does not know what the opaque credential
  prints, and a command reaches tracebacks and logs.

## References

- Related ADRs: 0.0.0005 (tenant from the token), 0.0.0006 (driving port is the
  use case class), 2.4.0003 (authorization composition at the boundary —
  its Alternative C rejected putting the actor into identity's use cases, an
  identity-scoped choice this ADR does not touch), 3.2.0002 (tenant-scoped
  signatures), 3.4.0001 (staff-owned AccessGuard port), 3.4.0008 (tenant-wide
  permissions), 3.5.0001 (cross-BC facade), 3.6.0001 (path addresses the
  record), 3.6.0002 (boundary identifier validation), 3.6.0004 (cheapest local
  check first)
- Code: `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  (steps 2–5), `src/restaurant_hub/composition_root.py` (`_IdentityAccessGuard`)
- Issue: #49

---
title: ADR 3.6.0001 — The staff router addresses records from the request path and never reads AuthorizedScope.unit_id, because a missing unit in the granted scope has two producers and no consumer can tell them apart
description: Architecture Decision Record
when-use: Reference when writing or reviewing a staff HTTP handler, when adding a field to AuthorizedScope, or whenever code is tempted to infer "tenant-wide" from a null unit
keywords: [adr, http, authorization, scope, unit, owner, bypass, staff, router]
status: accepted
created_at: 2026-08-18
updated_at: 2026-08-18
adr_id: 3.6.0001
decision: Every staff HTTP handler builds its command's unit from the already-authorized path segment and never reads AuthorizedScope.unit_id; the scope contributes only tenant_id, and the absence of a unit in it is never interpreted
context_stage: 3.6-staff-http
bounded_context: staff
---

# ADR 3.6.0001 — The path addresses the record, not the authorized scope

## Status

`accepted`

## Context

`AuthorizedScope` (Stage 3.4) carries two fields: `tenant_id`, which is never
empty (law L-AG3), and `unit_id`, which may be `None`. The obvious reading of a
null unit — *"this action is tenant-wide"* — was written into the port's docstring
and shipped, and the Stage 3.4 test audit measured it to be **false**. There are
**two** producers of `None`, and the scope does not distinguish them:

- **by permission** — `manage_job_functions` belongs to `TENANT_WIDE_PERMISSIONS`,
  so step 4 of `AuthorizeActionUseCase` waives the unit requirement
  (ADR 3.4.0008);
- **by role** — `_UNIT_SCOPE_BYPASS_ROLES = {OWNER, PLATFORM_ADMIN}`
  (`user.py` › `_UNIT_SCOPE_BYPASS_ROLES`), and step 4 also waives the requirement when
  `user.bypasses_unit_scope()` is true (`authorize_action.py` › `AuthorizeActionUseCase.execute`). An `owner`
  exercising `manage_staff` **without naming a unit** is authorized and comes back
  with `unit_id=None` — over a permission that is unit-scoped.

**What the scope actually carries, measured before this ADR was written.**
`AuthorizeActionUseCase` returns `scope_unit_id=command.unit_id`
(`authorize_action.py` › `AuthorizeActionUseCase.execute`), and the production translator passes it through. The
granted scope therefore **echoes the requested unit**: `None` appears **exactly
when the caller omitted the unit**, for every role. An `owner` that names unit A
gets `"A"` back, like anyone else; the owner bypass acts on step 5 (visibility),
not on the returned value. The qualifier *"without naming a unit"* above is
load-bearing, and an earlier draft of this Stage's concept dropped it and
concluded — wrongly — that `owner` and `manager` diverge here. They do not.

**So why forbid reading the field at all, if today it equals the path?** Three
reasons, none of which is "the roles diverge":

1. **No port law promises the echo.** L-AG1…L-AG4 constrain raw exceptions, a
   non-empty tenant, and one authorization per target. **None** of them requires
   `AuthorizedScope.unit_id` to equal the requested unit. The equality is a
   property of the two implementations that exist today, not of the contract a
   consumer is entitled to rely on.
2. **`copy_employee_to_unit` authorizes two units.** In that route "the
   authorized scope" stops being a well-formed expression, and any code phrased
   that way is one line away from swapping source and destination — the inversion
   the use case itself names as reopening the exfiltration ADR 3.4.0007 closes.
3. **The `None ⇒ tenant-wide` inference is still wrong**, by a different
   mechanism than assumed: `None` says *the call* named no unit, not that *the
   action* is tenant-wide. On the four catalogue routes the two coincide; on a
   future unit-scoped route that forgets to pass the unit they do not.

Two further facts frame the decision:

1. **The unit is already in the URL.** Since ADR 3.4.0007 the unit is part of an
   employee record's address, up to the repository port signature, and the twelve
   employee routes are nested under `/units/{unit_id}/…`. The router therefore
   already holds the unit it needs, as a value the guard has just authorized.
2. **The failure mode is silent.** A misuse here raises no exception and fails no
   type check; it merely couples the router to an unspecified behaviour, and in
   the copy route it can widen reach. That is the class of defect that only a test
   written *for it* can catch — and, because both implementations echo, only a
   test with a **deliberately divergent** double can catch it at all.

## Decision

1. **Every staff handler builds its command's `unit_id` from the path segment**
   it just had authorized. The employee routes pass the path's `unit_id`; the
   copy route additionally passes the body's `target_unit_id`, each authorized in
   its own `authorize` call (law L-AG4).
2. **`AuthorizedScope.tenant_id` is the only field the router reads.** It is the
   tenant of every command and query.
3. **No handler reads `AuthorizedScope.unit_id`.** Not to infer scope, not to
   cross-check the path, not to log. The field is not consumed by this Stage at
   all.
4. **The prohibition is pinned two ways**, because either alone is weak:
   - **structurally** — an AST sweep of the router module asserts there is no
     attribute access `unit_id` on the object returned by the guard (concept
     CA14). This survives a scenario nobody thought to write.
   - **behaviourally** — for every employee route, a test with a port double
     that returns a **divergent** scope asserts the command carries the **path's**
     unit (concept CA15). Parameterised over the twelve routes, not one.
5. **The behavioural test must use an adversarial double, and this is the
   load-bearing clause.** Both existing implementations echo the requested unit,
   so a test written against either one **cannot distinguish** "the router used
   the path" from "the router used the scope" — the two values are the same
   object, and the mutation stays green at 100% line and branch coverage. No role
   makes them diverge, `owner` included. The double must therefore return a scope
   whose `unit_id` is a **different** value (and, in a second case, `None`), and
   it must be documented as contradicting both implementations *on purpose*.
   This is the "universal law, narrow representative" family in its most
   deceptive form: the quantified domain has a single observable value in the
   whole system, so the second one has to be manufactured before the law can be
   refuted at all.

## Alternatives considered

### Alternative A — add the exercised permission (or a scope discriminator) to `AuthorizedScope`
- **Description:** the port returns `AuthorizedScope(tenant_id, unit_id, permission)`
  (or a `scope_kind` enum), so a consumer can tell "tenant-wide by permission"
  from "unit action by a bypassing role".
- **Pros:** makes the ambiguity representable instead of merely avoided; a future
  consumer that genuinely needs the distinction gets it.
- **Cons:** amends a port merged one Stage earlier, and obliges **both**
  implementations (production translator and the in-memory fake) plus the law
  suite to follow — for information the router already has, having supplied it to
  `authorize` itself one line earlier.
- **Why rejected:** it answers a question this design does not need to ask. The
  cost is a contract change; the benefit is zero for every route in the
  inventory. It stays available for the Stage that actually needs it.

### Alternative B — infer the scope from `unit_id is None`
- **Description:** treat a null unit as "tenant-wide" and skip the unit in the
  command.
- **Pros:** none that survive contact with the measurement.
- **Cons:** `None` means *the caller omitted the unit*, not *the action is
  tenant-wide*. The two coincide on today's four catalogue routes and diverge the
  moment a unit-scoped route omits the unit — at which point the command would
  address the tenant instead of the unit, silently, with no exception and no type
  error.
- **Why rejected:** it is the defect this ADR exists to forbid, and its
  correctness today rests on a coincidence between two independent facts.

### Alternative C — cross-check the path unit against the scope unit and reject on mismatch
- **Description:** keep reading `scope.unit_id`, and 403 when it differs from the
  path.
- **Pros:** looks like defence in depth.
- **Cons:** it is defence in **theatre**: for a bypassing role the scope unit is
  `None`, so the check would have to special-case exactly the case that motivated
  the ADR — and the special case is the bug, relocated. It also re-implements, in
  the adapter, a decision the guard already made, which is what ADR 2.4.0003
  forbids.
- **Why rejected:** adds a branch whose only correct behaviour is to do nothing.

## Consequences

### Positive
- The dangerous inference is not merely avoided but **visible in review**: the
  structural criterion fails on the first handler that reaches for the field.
  (It is defence in depth, not a proof — `getattr`, `astuple` and `asdict`
  all bypass an AST sweep. The behavioural criterion with the divergent double is
  the actual lock.)
- The port is untouched, so Stage 3.4's contract, its law suite and its two
  implementations stay exactly as merged.
- `owner`, `manager` and `hr` follow the same code path; there is no role-shaped
  branch in the adapter.

### Negative
- A future consumer that genuinely needs "was this tenant-wide?" will have to
  reopen Alternative A. This ADR does not pre-build it, and says so.
- The structural (AST) criterion is coupled to the module's shape: renaming the
  scope variable or destructuring it would need the sweep updated. That is
  accepted — the sweep is short and the coupling is visible when it breaks.

### Neutral / trade-offs accepted
- `AuthorizedScope.unit_id` becomes a field with no consumer in production. It is
  still produced and still tested by Stage 3.4's law suite; leaving it is cheaper
  and less disruptive than removing a field from a merged DTO.

## Implementation notes

- The guard call and the command build must read the **same** variable — the path
  parameter — so that "authorized target" and "addressed record" cannot drift.
  Two names for one value is how this defect comes back.
- The AST sweep of concept CA14 should look for the attribute name on the guard's
  return value, not for the string `unit_id` anywhere in the file (path
  parameters are legitimately called `unit_id`).

## References
- `src/restaurant_hub/features/staff/application/ports/out/access_guard.py` —
  docstring of `AuthorizedScope.unit_id` (the two producers of `None`)
- `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  — step 4
- `src/restaurant_hub/features/identity/domain/entities/user.py` —
  `_UNIT_SCOPE_BYPASS_ROLES`
- `docs/stages/3.4-staff-access-scope/technical.md` §7 — `[finding]` of
  2026-08-18, *"`unit_id=None` no `AuthorizedScope` não significa tenant-wide"*
- `docs/stages/3.6-staff-http/concept.md` §5.4, §7 D1, CA14, CA15
- ADR 2.1.0001, ADR 2.4.0003, ADR 3.4.0007, ADR 3.4.0008
- `.claude/skills/stage-audit/SKILL.md` §"Lei universal, representante estreito"

---
title: ADR 3.9.0001 — Error roots say what failed, the adapter map says which status; ApplicationError returns for failures that are not business rules
description: Architecture Decision Record
when-use: Reference when adding an error to any bounded context, when choosing between DomainError and ApplicationError, before ordering base classes of an exception, or when reading ADR 2.2.0003, which this ADR supersedes
keywords: [adr, errors, exceptions, domain-error, application-error, not-found, mro, http-mapping, supersedes, dependency-rule]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
adr_id: "3.9.0001"
decision: "Every error class has exactly one root chosen by meaning — DomainError (via the BC's domain root) when it names a business rule, ApplicationError (via the BC's application root) when the use case could not be served for a reason that is not a business rule — and the HTTP status comes only from the BC's explicit, test-guarded map; NotFoundError and multiple inheritance chosen to steer handler lookup are removed. Supersedes ADR 2.2.0003."
context_stage: 3.9-error-hierarchy
bounded_context: shared
supersedes: "2.2.0003"
---

# ADR 3.9.0001 — Error roots by meaning, status by map

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Supersedes [ADR 2.2.0003](./2_2_0003-application-errors-in-identity-hierarchy.md) in full.
Partially supersedes, by dated append-only notes in each:
[ADR 2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md) (Decision 2, "all subclasses of
`IdentityError`", and the paragraph that preserves Stage 2.2's invariant #16 — the five
`*AlreadyExistsError` classes now descend from the identity application root);
[ADR 2.4.0001](./2_4_0001-http-error-status-mapping.md) (decisions 2 and 3: the handler is
registered on **both** identity roots and totality is checked over both; and, in the closing
sentence "The generic `shared` handlers stay as the safety net for non-identity `DomainError`s
and for future bounded contexts", the plural — only the `DomainError → 422` handler stays, the
generic `NotFoundError → 404` one is deleted) and
[ADR 3.4.0002](./3_4_0002-staff-http-error-status-mapping.md) (the same two clauses, for staff,
and the rule "never from `ApplicationError`" in its Context).

## Context

ADR 2.2.0003 put every identity application error under `IdentityError` (hence `DomainError`)
because `ApplicationError` had no HTTP handler and would have produced a 500. It also made the
three not-found errors inherit `(IdentityError, NotFoundError)` **in that order**, so that
Starlette — which picks a handler by walking `type(exc).__mro__` — would reach the 404 handler
before the 422 one. Staff (3.2) and scheduling (4.3) copied the arrangement, and their
`errors.py` docstrings say literally that the base order was chosen for the framework's lookup.

Two things changed since:

1. Stage 2.4 (ADR 2.4.0001) and Stage 3.6 (ADR 3.4.0002) moved status resolution into an
   **explicit map per bounded context**, and issue #45 (Gate 3, `tests/unit/test_status_map.py`)
   made the map's totality a test across every BC. An unmapped error now fails the build. The
   inheritance trick no longer carries any status: the BC handler wins the lookup and reads the
   map; the generic `NotFoundError → 404` handler in `shared` is never reached by any BC error.
2. Issue #45 (Gate 7) deleted the template's `ApplicationError` because nothing used it — so the
   2.2.0003 rule "never `ApplicationError`" stopped being representable, while its consequence
   stayed: credential, protocol, lookup and storage-collision failures are typed as violations
   of a **business** rule. `InvalidAccessTokenError` is a `DomainError`.

The inner circle knows about the outer one: `shared/domain/exceptions/base.py` defines its two
classes by HTTP status ("convertida em HTTP 404"), and the application error modules justify
their base order by Starlette's algorithm (Clean Architecture, ch. 22: nothing in an inner
circle can know anything about an outer circle, framework included).

Forces:
- Observable behaviour must not change: every status band and body of the HTTP API (identity
  401/403 constant bodies with `WWW-Authenticate`, the #26 suppressed-cause log line, staff's
  `"type": "staff_error"` discriminator) is an oracle covered by e2e tests that stay untouched.
- The guard conversions of ADR 2.4.0001 §5 close enumeration oracles and are out of scope.
- Scheduling has no HTTP edge yet (Stage 4.5) but already has application errors.

## Decision

1. **`ApplicationError` returns, in `shared/application/errors.py`.** It is an application-layer
   concept, so it lives in `shared/application`, not back in `shared/domain`. The import
   contracts already allow it — `.importlinter` `shared-layers` orders `application` above
   `domain`, and no `*-application-purity` contract forbids `restaurant_hub.shared.application`
   — while LAYOUT §3, whose Application list names only `shared/application/ports/`, is amended
   by this Stage to name `shared/application/errors.py` too. It does **not** subclass
   `DomainError`.
2. **One root per meaning, per BC.** Each BC has a domain root (`IdentityError`, `StaffError`,
   `SchedulingError`, unchanged) and an application root in its `application/errors.py`
   (`IdentityApplicationError`, `StaffApplicationError`, `SchedulingApplicationError`, each a
   direct subclass of `ApplicationError`). Every concrete error has **exactly one** base that is
   a root or a descendant of exactly one root: no class has two roots, and no base order is
   chosen for any framework.
3. **The criterion.** It classifies the errors the **application layer** raises (use cases and
   the laws of their ports — the `application/errors.py` modules). Errors raised by domain
   objects (entities, value objects, aggregates, domain services) are domain errors by
   construction: they guard the model's own consistency, the domain layer cannot depend on
   `shared/application`, and an absent element **inside** an aggregate already loaded
   (`ShiftBandNotFoundError`, `ShiftDemandNotFoundError`, `AssignmentNotFoundError`,
   `UnavailabilityNotFoundError`) or a duplicate internal id (`DuplicateEntityIdError`) is an
   invariant of that aggregate, not a lookup. For application-layer errors: an error is a
   **domain** error when the condition it names is a rule the **business** states — sourced in a
   domain doc, a product decision (kickoff, sponsor answer) or an ADR that records such a
   product rule — and would hold under any protocol, storage or client. A rule that exists only
   as a technical design decision (insertion-not-upsert, session-reuse detection, client-supplied
   ids) does not qualify; when a condition fits both branches, the domain branch wins only with a
   product source. It is an **application** error when it names a use case that could not be
   served for a reason that is not a business rule:
   - the addressed resource does not exist (lookup: `*NotFoundError`);
   - the presented credential or token does not authenticate (`InvalidCredentialsError`,
     `InvalidAccessTokenError`, `InvalidRefreshTokenError`, `RefreshTokenReuseError`,
     `InvalidSetupTokenError`);
   - a technical identifier collides in storage (`*AlreadyExistsError` on ids, the session
     fingerprint, the membership pair, scheduling's `IdentifierInUseError`);
   - the request or an input from another BC is malformed or incomplete
     (`InvalidScheduleRequestError`, `MissingStaffRecordsError`).
   Authorization denials stay in identity's **domain**: who may do what is a product rule
   (ADR 2.2.0002), and identity is the access-control domain. Product rules that need storage
   to check stay domain too: global e-mail uniqueness (kickoff decision #2 —
   `EmailAlreadyRegisteredError`, and its staff translation `LoginEmailAlreadyInUseError`),
   job-function name per tenant (workforce §3.2, §6), schedules of a unit never overlap in time
   (`docs/domain/scheduling/shift-scheduling.md`, enforced as port law L-SC2 —
   `SchedulePeriodTakenError`), and optimistic concurrency on the schedule (sponsor decision
   F8, shift-scheduling.md "Regra canônica — concorrência": no mutation applies over a version
   the editor did not see — `ScheduleVersionConflictError`).
   The resulting split is pinned by an explicit list per BC in each `test_errors.py`.
4. **Status comes only from the BC map.** Each BC with an HTTP edge registers its single handler
   on **both** of its roots, and the map is keyed by concrete classes under either root (the
   roots themselves are not keys — the staff band oracle counts the map's entries). The Gate 3 test
   derives both roots per BC and requires an own entry for every concrete subclass of either,
   plus a handler registered on every root. Bodies, log lines and bands are unchanged: the
   identity handler treats both roots alike (same constant 401/403 bodies, same short class name
   in the suppressed-cause log), and the staff handler keeps `"type": "staff_error"`.
5. **`NotFoundError` and its generic 404 handler are deleted.** With no subclass left they are
   dead code (LAYOUT §4, `check_dead_shared.py`). The generic `DomainError → 422` handler stays
   as before. **No generic handler is registered for `ApplicationError`**: an application error
   outside every BC map would surface as a 500 — loud — and the build already forbids that
   state (every exception in a BC's error modules descends from one of its roots; every root of a
   BC with an edge has a handler; every concrete class has a map entry).
6. **A detector keeps protocol out of the hierarchy.** `scripts/check_layout.py` gains a rule
   that fails when a module defining the exception hierarchy — `shared/domain/exceptions/`,
   `shared/application/errors.py`, `features/*/domain/exceptions/`,
   `features/*/application/errors.py` — mentions the transport (`HTTP`, `FastAPI`, `Starlette`,
   exception `handler`, method-resolution order, or a `4xx`/`5xx` status number) in code,
   docstring or comment. The mapping is described where it lives: in the adapter.

## Alternatives considered

### Alternative A — Keep ADR 2.2.0003, only scrub the docstrings
- **Description:** remove HTTP words from the docstrings, keep `(BCError, NotFoundError)`.
- **Pros:** smallest diff.
- **Cons:** the base order still exists only to steer the framework; the words would go, the
  coupling would stay. Credential and lookup failures stay typed as business-rule violations.
- **Why rejected:** it hides the inversion instead of removing it.

### Alternative B — Every error in `application/errors.py` becomes an `ApplicationError`
- **Description:** classify by the layer of the module instead of by meaning.
- **Pros:** mechanical, no judgement per class.
- **Cons:** several application-layer errors name business rules that need storage to check
  (global e-mail uniqueness, function in use, one schedule per day, blocking violations). Typing
  them as "not a business rule" repeats, in the other direction, the misclassification this ADR
  removes; issue #48 asks to migrate only the errors that are **not** rule violations.
- **Why rejected:** layer of definition is where the check runs, not what the error means.

### Alternative C — `ApplicationError` back in `shared/domain/exceptions/base.py`
- **Description:** where the template had it.
- **Pros:** one module for both roots.
- **Cons:** an application-layer concept in the domain package; the template's version also sat
  there with no consumer for six Stages.
- **Why rejected:** the layer split of `shared` (`shared-layers` import contract: `application`
  above `domain`) is where an application concept belongs; LAYOUT §3 is amended to say so.

### Alternative D — Keep `NotFoundError` as a shared application base for lookups
- **Description:** `NotFoundError(ApplicationError)`, with BC not-found errors under it.
- **Pros:** "not found" is reusable vocabulary.
- **Cons:** a BC not-found error would then need both its BC application root and
  `NotFoundError` — two roots again — or drop its BC root and escape the BC handler.
- **Why rejected:** reintroduces the multiple inheritance this ADR removes; the map already
  names each not-found class.

### Alternative E — A generic `ApplicationError` handler in `shared` (422 or 404)
- **Description:** a safety net parallel to the `DomainError → 422` one.
- **Pros:** symmetric with the domain side; nothing can become a 500.
- **Cons:** any status it picks is wrong for some member (a lookup as 422, a bad token as 404),
  and it would answer quietly for a BC that forgot to register its root — exactly the silent
  degradation the Gate 3 map exists to prevent.
- **Why rejected:** the build-time gates make the state unreachable; a net would only hide a
  regression of those gates.

## Consequences

### Positive
- "`DomainError`" means "a business rule was violated" again; a reader can tell a wrong
  password from a broken invariant by the type.
- No class's base order depends on the web framework; the domain and application packages carry
  no protocol vocabulary, and a rule keeps it so.
- `ApplicationError` has consumers in all three BCs.

### Negative
- "Catch everything a BC raises" is now two roots (`except (StaffError, StaffApplicationError)`)
  — the cost ADR 2.2.0003 Alternative A named. Nothing in `src/` catches a root; the handlers
  register both.
- One judgement per error class (the criterion in decision 3); borderline cases are recorded in
  the Stage's technical §7.

### Neutral / trade-offs accepted
- The generic `DomainError → 422` net stays and has no `ApplicationError` twin (decision 5).
- Scheduling's lookup, collision and malformed-input errors change root before scheduling has an edge; their
  status is Stage 4.5's.

## Implementation notes

- `tests/unit/test_status_map.py` derives, per BC, the domain root (direct subclass of
  `DomainError` in `domain/exceptions/errors.py`) and the optional application root (direct
  subclass of `ApplicationError` in `application/errors.py`).
- `test_suppressed_cause_log.py` (unit and e2e), `test_status_bands.py` and
  `test_staff_status_bands.py` are the behavioural oracle and are not edited by the Stage.

## References

- Issue #48; issue #45 (Gates 3 and 7).
- Robert C. Martin, *Clean Architecture* (2017), ch. 22 "The Clean Architecture" — the
  Dependency Rule.
- Related ADRs: 2.2.0002 (authorization as a product rule), 2.3.0003, 2.4.0001, 3.4.0002,
  4.1.0001, 4.3.0004.
- Code: `src/restaurant_hub/shared/domain/exceptions/base.py`,
  `src/restaurant_hub/features/*/application/errors.py`,
  `src/restaurant_hub/features/*/adapters/inbound/http/error_handlers.py`.

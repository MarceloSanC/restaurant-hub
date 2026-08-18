---
title: ADR 3.6.0003 — The staff wire format mirrors the domain's guarantees instead of flattening them, so the boundary cannot undo what the domain and the persistence layer already prove
description: Architecture Decision Record
when-use: Reference when adding a staff request or response field, when tempted to serialise a Decimal as a JSON number or a naive datetime with an offset, or when flattening a discriminated union into optional fields
keywords: [adr, http, schemas, pydantic, decimal, datetime, discriminated-union, serialization, staff]
status: accepted
created_at: 2026-08-18
updated_at: 2026-08-18
adr_id: 3.6.0003
decision: The staff HTTP boundary carries the workload profile as a union discriminated by type, weekly_hours as a string, unavailability datetimes without offset, and set-valued fields sorted on output — each because the alternative destroys a property the domain or the persistence layer already guarantees
context_stage: 3.6-staff-http
bounded_context: staff
---

# ADR 3.6.0003 — The wire representation preserves domain guarantees

## Status

`accepted`

## Context

Four staff values carry a property that is easy to lose in JSON, and in each case
the loss is silent — the response is well-formed, the tests that only check field
presence pass, and the damage shows up in a client weeks later.

1. **The workload profile is a type union.** `WorkloadProfile = FixedSchedule |
   OnDemand`, and its module docstring says the union exists so that *"sob demanda
   com carga"* and *"fixa sem carga"* **do not compile** — the guarantee is
   static, from mypy strict, not a runtime check.
2. **`weekly_hours` is a `Decimal` whose scale is meaningful.** Stage 3.3 proved
   value **and scale** survive the Postgres round trip; `Decimal("22.50")` is not
   interchangeable with `Decimal("22.5")` for a contract in hours.
3. **`UnavailabilityPeriod.start/end` are naive datetimes** — wall clock in the
   unit's local time (ADR 3.1.0005) — and the value object **rejects** tz-aware
   inputs.
4. **Two response fields are `frozenset`-derived, not one.**
   `EmployeeResult.job_function_ids` is a `frozenset` — `results.py` states the
   order is not the domain's and that ordering for display belongs to the HTTP
   adapter — and so is `ShiftPreference.periods`. Fixing the order of one and
   leaving the other is how a "byte-identical response" guarantee becomes false
   in a field nobody was looking at.

The framework's defaults work against all four. Pydantic will happily model a
flat object with optional fields; JSON has no decimal type, so a `Decimal`
serialised as a number becomes a float in every mainstream client; a datetime
rendered with `Z` is a different instant; and iterating a `frozenset` gives an
order that varies between processes.

## Decision

The boundary mirrors the guarantee rather than the shape that is convenient:

1. **The workload profile travels as a union discriminated by `type`** —
   `{"type": "fixed", "weekly_hours": "40.0"}` or `{"type": "on_demand"}` — in
   both requests and responses. `{"type": "on_demand", "weekly_hours": "40"}` and
   `{"type": "fixed"}` are rejected with 422.
2. **`weekly_hours` travels as a string**, in and out, and the boundary owns a
   **converter**, not a bare constructor call. Measured: `Decimal("abc")`,
   `Decimal("")` and `Decimal("40,5")` raise `decimal.InvalidOperation`, which is
   an `ArithmeticError` — **not** a `StaffError`, not a `DomainError`, not
   anything the app registers a handler for — so a bare `Decimal(payload)` in the
   router answers **500**. Only the *non-finite* cases (`"NaN"`, `"Infinity"`)
   construct and then reach `FixedSchedule.__post_init__`'s
   `InvalidWeeklyHoursError`. The converter therefore catches
   `decimal.InvalidOperation` and raises `InvalidWeeklyHoursError` → 422,
   mirroring in form the `DayPeriod.from_string` the same boundary already uses
   for exactly this reason.

   > An earlier draft of this clause asserted that a "non-numeric" value already
   > produced `InvalidWeeklyHoursError`. It did not, and the probe that refuted it
   > is why the converter is now part of the decision rather than an
   > implementation detail.
3. **`start` and `end` travel without offset.** A value carrying `Z` or an offset
   is parsed as tz-aware and rejected by `UnavailabilityPeriod` →
   `InvalidUnavailabilityPeriodError` (422). It is **not** silently converted.
4. **Both set-valued fields are sorted on output, each with a named key.**
   `job_function_ids` is emitted sorted by the id itself; `shift_preference` is
   emitted in the **declaration order of the `DayPeriod` enum** (morning,
   afternoon, night, overnight), because that order is the one the domain's
   ubiquitous language already carries and alphabetical order would scramble a
   sequence a human reads as chronological. Naming the key matters: "sorted" alone
   leaves two defensible readings for this field.
5. All of the above are pinned by a single round-trip criterion (concept CA04)
   plus the union criterion (CA06). **CA04 asserts equality against the expected
   sorted list, not equality between two responses**: `frozenset` iteration is
   deterministic *within a process* (`PYTHONHASHSEED` is drawn per process), so
   "two calls return the same body" holds with or without the sort and kills no
   mutation. Measured during this Stage's Checkpoint A.

## Alternatives considered

### Alternative A — flatten the profile into optional fields
- **Description:** `{"weekly_hours": "40.0"}` with `null` meaning on-demand, or a
  flat object with both fields optional.
- **Pros:** simpler schema; one less concept for a client.
- **Cons:** re-admits at the boundary exactly the invalid states the union was
  built to make unrepresentable, and pushes the "exactly one profile" check back
  into runtime validation the domain deleted. `null` would also become a second
  spelling of "on demand", competing with the existing `null` semantics of
  `shift_preference` ("clear it"), which means two different meanings for the same
  token in the same payload.
- **Why rejected:** it converts a static guarantee into a runtime one, in the
  layer least able to enforce it.

### Alternative B — serialise `weekly_hours` as a JSON number
- **Description:** `{"weekly_hours": 40.0}`.
- **Pros:** natural for clients; no string-to-number step.
- **Cons:** JSON numbers are parsed as IEEE-754 doubles by every mainstream
  client, so `22.50` and `22.5` become indistinguishable and the scale that
  Stage 3.3 proved end-to-end is destroyed at the last hop. Accumulated
  arithmetic on the client then diverges from the server's decimal arithmetic.
- **Why rejected:** the whole point of storing a `Decimal` is lost in the one
  place the value leaves the system.

### Alternative C — normalise datetimes to UTC with an offset
- **Description:** accept and emit `2026-01-01T08:00:00Z`.
- **Pros:** unambiguous instants; friendly to date libraries.
- **Cons:** the domain value is a **wall clock**, not an instant (ADR 3.1.0005):
  "unavailable from 08:00" means 08:00 where the unit is, across DST changes.
  Attaching an offset asserts an instant the system does not know, and converting
  it back would move the boundary by an hour twice a year.
- **Why rejected:** it encodes a fact the domain deliberately does not model.

### Alternative D — emit `job_function_ids` in set order
- Nothing forbids it, and it looks harmless. But two responses for the same
  record would differ between processes, which makes response equality unusable as
  a test assertion and makes client-side caching and diffing unreliable. Sorting
  costs one call.

## Consequences

### Positive
- Every property the domain and the persistence layer prove survives the last
  hop, and the survival is asserted rather than assumed.
- Malformed profiles and offset-bearing datetimes fail as **domain** errors, so
  they land in this Stage's status map with the rest of the 422 band instead of
  in the framework's parallel one.
- Response equality becomes a legitimate test assertion.

### Negative
- Clients must handle a string where a number would be idiomatic, and a
  discriminated union where a flat object would be simpler. This is a real
  ergonomics cost, paid by every consumer.
- Naive datetimes will surprise a client that assumes UTC. The contract has to say
  so; there is no representation that is both correct and self-evident here.

### Neutral / trade-offs accepted
- The OpenAPI schema for the profile is a `oneOf`, which some generators render
  awkwardly. Accepted: the generated shape reflects the real domain, and the
  alternative is a schema that lies about which combinations are legal.

## Implementation notes

- Build the `Decimal` in the **router**, not in a Pydantic validator, so the
  failure is `InvalidWeeklyHoursError` and not a coercion error — same rule as
  every other text-to-value-object conversion at this boundary. Wrap it:
  `try: Decimal(value) except InvalidOperation: raise InvalidWeeklyHoursError(...)`.
- **Open at the boundary, and deliberately left to Phase 3B:** `Decimal("  40  ")`
  constructs `Decimal("40")` — the whitespace is trimmed silently, which is the
  normalisation ADR 2.3.0005 refuses. Either the converter rejects padded input or
  the trimming is accepted and declared; it must not be discovered by a client.
- Do not add `extra="forbid"` to the request models: the identity boundary
  deliberately keeps Pydantic's default of ignoring unknown fields so that a
  malicious extra field is **disarmed** rather than answered with a 422, and the
  test can observe the disarming. Diverging here would create two behaviours for
  the same class of request across the API.
- The sort key for `job_function_ids` is the id itself; it is arbitrary but must
  be stable and stated, so nobody "improves" it into a name-based order that would
  require a second query.

## References
- `src/restaurant_hub/features/staff/domain/value_objects/workload_profile.py` —
  module docstring (the union makes invalid states unrepresentable)
- `src/restaurant_hub/features/staff/domain/value_objects/unavailability_period.py`
- `src/restaurant_hub/features/staff/application/dtos/results.py` — *"a ordem não
  é do domínio"*
- `src/restaurant_hub/features/identity/adapters/in/http/schemas.py` — the
  boundary conventions this ADR follows
- `src/restaurant_hub/features/staff/domain/value_objects/shift_preference.py` —
  `ShiftPreference.periods` is also a `frozenset`
- `docs/stages/3.6-staff-http/concept.md` §4.2, §6.3, §7 D3, CA04, CA06, CA24
- ADR 3.1.0004, ADR 3.1.0005, **ADR 3.1.0006** (the order of the job-function set
  is not domain data), ADR 2.3.0005; Stage 3.3 CA17 (value **and** scale survive
  the Postgres round trip)

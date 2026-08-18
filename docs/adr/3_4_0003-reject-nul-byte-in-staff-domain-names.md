---
title: ADR 3.4.0003 — The NUL byte is rejected in the staff domain rather than translated at the HTTP boundary, and DayPeriod gains a from_string mirroring Role.from_string
description: Architecture Decision Record
when-use: Reference before adding character validation to a verbatim name field, when a driver-level DataError reaches a route, or when a StrEnum needs to be built from request text
keywords: [adr, domain, validation, nul-byte, dataerror, verbatim, fake-parity, layer-expansion, staff, enum]
status: accepted
created_at: 2026-08-12
updated_at: 2026-08-12
adr_id: 3.4.0003
decision: Employee and JobFunction reject names containing the NUL byte in the domain (Stage 3.1 layer expansion), so fake and Postgres agree by construction instead of the boundary translating psycopg.DataError; and DayPeriod gains from_string raising InvalidDayPeriodError, so text-to-enum conversion fails as a domain error rather than a 500
context_stage: 3.4-staff-access-scope
bounded_context: staff
---

# ADR 3.4.0003 — Reject the NUL byte in the staff domain

## Status

`accepted`

## Context

Stage 3.3's independent test audit found, and Stage 3.3 reproduced and measured,
a divergence between the in-memory fake and the real Postgres adapter:

| Input | Fake | Postgres |
|---|---|---|
| `"a\x00b"` | stored verbatim | `sqlalchemy.exc.DataError` |
| quotes, accents, ZWJ emoji, `\n`, 1000 chars | stored verbatim | stored verbatim |

**Only the NUL diverges.** Everything else in the adversarial set round-trips
perfectly on both sides, which is a positive result for the verbatim discipline of
ADR 2.3.0005.

Three measured facts constrain the fix, and Stage 3.3 corrected the audit's own
report on the first of them:

- The `sqlstate` is **`None`**, not `22021`, and `constraint_name` is `None` too:
  the refusal is **client-side, in psycopg**, before the statement reaches the
  server. Any boundary handling would have to match on **exception type**, not on
  a server error code.
- `DataError` is **not** an `IntegrityError`, so the per-operation translator
  built in Stage 3.3 (ADR 3.3.0004) is never invoked and the error rises raw.
- The port-law contract suite cannot cover the case: if it exercised a NUL name it
  would **fail under `[postgres]`**, because the divergence is real.

Consequence today: a name containing `\x00` becomes a **500** at the HTTP boundary
this Stage introduces. Stage 3.3 escalated it to 3.4 with a stated preference for
fixing it in the domain, and issue #40 asks this concept to evaluate and decide.

A second, smaller instance of the same class of defect surfaced while drafting the
routes: `DayPeriod` is a `StrEnum` with no converter, so `DayPeriod("xpto")` raises
`ValueError` — not a `StaffError`, no handler, another 500.

## Decision

**1. `Employee.name` and `JobFunction.name` reject names containing `\x00`**, in
`__post_init__`, raising the existing `InvalidNameError`. This is a declared
expansion of this Stage's target layer into the domain of Stage 3.1 — the same
manoeuvre, with the same declaration, that Stage 3.2 performed on Stage 3.1's
entities.

**2. The rejection is scoped to the NUL byte and to nothing else.** No control
characters, no whitespace normalisation, no length cap. Stage 3.3 measured that
every other adversarial input round-trips verbatim on both sides; widening the rule
would be silent normalisation under another name, against ADR 2.3.0005.

**3. `DayPeriod` gains `from_string`**, raising a new
`InvalidDayPeriodError(StaffError)`, mirroring identity's
`Role.from_string`/`InvalidRoleError`. The staff router converts request text to
the enum there, so an unknown period is a 422 domain error rather than a 500.

**4. The port-law suites gain the NUL case.** With the domain rejecting it, the
fake and Postgres agree **by construction**, and the contract suite can finally
assert the behaviour under both parametrisations — which is the property that
distinguishes this fix from merely hiding the 500.

**5. Identity is not touched.** `Restaurant`, `Unit` and `User` have the same
defect. Fixing them is outside this Stage's bounded context and is escalated as a
`[finding]`.

## Alternatives considered

### Alternative A — translate `DataError` at the HTTP boundary
- **Description:** catch `sqlalchemy.exc.DataError` in the staff error handler and
  map it to 422, next to the raw `40P01`/`40001` cases.
- **Pros:** no change to merged domain code; strictly smaller diff; keeps this
  Stage's target layer honest.
- **Cons:** it closes the 500 and **keeps fake and real disagreeing about what is
  storable**. The contract suite still cannot cover the case; a future in-memory
  adapter, a future non-Postgres store, or a unit test would all keep accepting a
  value the production database refuses. It also leaks a persistence detail into
  the presentation layer: the boundary would be catching a driver exception to
  express a rule about names.
- **Why rejected:** it documents the divergence instead of removing it. Stage 3.3
  ranked it second for exactly this reason, and the ranking survives re-reading.

### Alternative B — reject all C0 control characters
- **Description:** refuse `\x00`–`\x1f` in names.
- **Pros:** arguably none of them is defensible business data; one rule covers a
  class rather than a case.
- **Cons:** it refuses inputs the database accepts and that Stage 3.3 measured
  round-tripping verbatim (`\n` among them). It converts a *storage* constraint
  into a *policy* decision that nobody asked for, and it is the kind of quiet
  tightening ADR 2.3.0005 exists to prevent.
- **Why rejected:** the fix should be exactly as wide as the divergence it closes.

### Alternative C — normalise silently (strip the NUL)
- **Pros:** no error surface at all.
- **Cons:** the stored name would differ from what the user typed, which is the
  precise behaviour ADR 2.3.0005 forbids, and the user would never learn.
- **Why rejected:** silent data corruption dressed as convenience.

### Alternative D — do nothing
The 500 stays. Issue #40's finding nº 3 remains open and the Stage would ship a
route that returns 500 for a request body — violating concept §5.10, which is a
stated acceptance criterion.

## Consequences

### Positive
- Fake ≡ real for name storage, by construction, and provable by the existing
  contract suite rather than by a comment.
- The 500 disappears without the boundary learning anything about psycopg.
- `InvalidDayPeriodError` closes the second 500 path with a pattern already proven
  in identity.

### Negative
- **Target-layer expansion.** This Stage, whose declared layer is
  `adapters/in/http`, edits two merged domain entities and their tests. The cost is
  real and is declared in concept §1 and in the roadmap block's dated note. It is
  accepted because no boundary-only fix reaches the property that matters.
- A previously-accepted value becomes invalid. In practice nothing legitimate is
  affected — a NUL in a person's name is not data, it is a bug or an attack — but
  it is technically a narrowing of an already-merged contract.

### Neutral / trade-offs accepted
- Identity keeps the defect until a Stage that owns that BC fixes it. Recorded as
  a `[finding]` with a candidate Stage rather than left to memory.
- The new error `InvalidDayPeriodError` needs an entry in the status map of
  ADR 3.4.0002; the totality test enforces this automatically.

## Implementation notes

- Validate in `__post_init__` of both entities, so **every** construction path is
  covered — including the mapper rehydration of Stage 3.3, which is what makes the
  rule an invariant rather than an input filter.
- Reuse `InvalidNameError`; a dedicated error class would fragment the 422 band
  without changing any observable behaviour.
- `DayPeriod.from_string` goes next to the enum in
  `domain/value_objects/shift_preference.py`, mirroring `Role.from_string`'s
  placement in identity.

## References
- `docs/stages/3.3-staff-persistence/technical.md` §7 —
  `[finding]` of 2026-08-11, with the measurement table and the sqlstate correction
- Issue #40, inherited finding nº 3
- `docs/stages/3.4-staff-access-scope/concept.md` §5.10 (só o NUL), §6 (a tabela
  do que muda no comportamento de erro), §7 D2, CA16–CA19
- ADR 2.3.0005 (names persisted verbatim), ADR 3.3.0004 (per-operation integrity
  translation), ADR 3.2.0005 (precedent for a later Stage amending 3.1's domain)
- `src/restaurant_hub/features/identity/domain/value_objects/role.py`
  (`from_string`)

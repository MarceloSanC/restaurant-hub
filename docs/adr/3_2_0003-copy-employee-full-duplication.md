---
title: ADR 3.2.0003 — Copying an employee to another unit duplicates the whole record, with a closed exclusion list
description: Architecture Decision Record
when-use: Reference when implementing or changing copy_employee_to_unit (Stage 3.2), when Stage 3.5 adds the login link, or before adding any new field to the employee record
keywords: [adr, staff, application, copy, unit, duplication, independence, user-id, unavailability, idempotence]
status: accepted
created_at: 2026-08-08
updated_at: 2026-08-08
adr_id: 3.2.0003
decision: copy_employee_to_unit creates an independent record in the target unit carrying the whole aggregate — name, workload profile, shift preference, job-function set, unavailability periods and lifecycle state — excluding only identity (new id), location (target unit) and any login link (never carried, now or after Stage 3.5); copying into the source's own unit is refused, and repeating a copy to the same destination is an accepted, declared limit rather than a guarded one.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0003 — Copy to unit duplicates the whole record, with a closed exclusion list

> ⚠️ **Errata (2026-11-09, Stage 3.11):** "The copy does not consume `JobFunctionRepository`" is superseded in part — job functions are now enabled per unit, so the same ids are no longer valid in every unit; the copy resolves the source's functions and refuses a destination where one is not enabled. The closed exclusion list is unchanged — ver [ADR 3.11.0002](./3_11_0002-employee-holds-only-functions-enabled-in-its-unit.md)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Copying an employee to another unit of the same restaurant is a named feature of the product
(overview §3) and the **Definition of Done of this Stage**: "cópia entre unidades duplica cadastro
sem vazar dados entre unidades" (roadmap 3.2).

The ratified theory states the rule and, importantly, enumerates its exclusions
([`workforce.md`](../domain/staff/workforce.md) §3.7):

- copying "**duplica o registro** — não compartilha, não vincula, não vaza";
- "após a cópia, os dois registros são **independentes**: alterar um não altera o outro";
- "a cópia **NÃO carrega o `user_id`**" — and this is the **only** exclusion named
  ([ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md), decision iii);
- functions are tenant-scoped, so a referenced function already exists for the target unit
  ([`workforce.md`](../domain/staff/workforce.md) §3.2/§3.7;
  [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md)).

What the sources do **not** spell out is (a) whether the non-cadastral content of the aggregate —
the **unavailability periods** — travels with the copy, (b) what happens when the target unit is
the source's own, and (c) what happens when the **same** copy is made twice. Three behaviours the
use case must fix.

A fourth question existed while the job function had a lifecycle ("does the copy carry a function
that has since been deactivated?", fork F2 of the Stage 3.2 concept). It was **dissolved on
2026-08-08** by [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md): there is no
inactive function, so there is nothing for the copy to decide. What remains from that family is the
**employee's own** state, settled below.

## Decision

`CopyEmployeeToUnitUseCase` creates a **new, independent** employee record in the target unit
carrying the **entire aggregate**:

| Field | In the copy |
|---|---|
| `id` | **new**, from `IdGenerator` |
| `tenant_id` | same (copy is always intra-tenant) |
| `unit_id` | **target unit** |
| `name` | duplicated, verbatim |
| `workload_profile` | duplicated |
| `shift_preference` | duplicated (including `None`) |
| `job_function_ids` | duplicated — the functions are tenant-scoped, so the same ids are valid in the target unit |
| `unavailabilities` | **duplicated** |
| `active` (lifecycle, ADR 3.2.0006) | **duplicated as-is** |
| login link (`user_id`, Stage 3.5) | **never carried** |

Three corollaries:

1. **Independence is structural, not conventional.** The Stage 3.1 entities and value objects are
   `frozen`, so the copy shares no mutable object with the source; "altering one does not alter the
   other" holds by construction rather than by a defensive deep copy. The test that proves it must
   **mutate one side and re-read the other through the port** — comparing field values right after
   the copy would survive a shared-reference implementation, and comparing the entities themselves
   proves nothing at all (`Employee.__eq__` compares only by id).
2. **Copying into the source's own unit is refused** with `SameUnitCopyError`. The operation is
   "copy to *another* unit" (workforce §3.7); allowing the same destination would silently mint an
   indistinguishable twin in the same unit — and employee names are legitimately non-unique
   (concept 3.1 §5.2), so nothing downstream would flag it.
3. **Repeating the copy to the same destination is an accepted, declared limit — not a guarded
   one.** Copying Ana from unit A to unit B twice produces **two** records in unit B, mutually
   indistinguishable. There is no guard because any guard would require the copy to record **where
   it came from**, and "não **vincula**" is literal in workforce §3.7 — a provenance link is exactly
   what the theory forbids. The asymmetry with corollary 2 is precisely this: "destination equals
   origin" is detectable **without any link** (two `unit_id` values the use case already holds);
   "I already copied this before" is not. The limit is recorded in the Stage 3.2 concept (§5.11),
   pinned by an acceptance criterion so nobody "fixes" it by accident, and escalated as a
   `[finding]` to Stage 3.4, where the boundary can make the operation explicit (confirmation,
   or feedback that a homonym already exists in the target unit).

**The copy does not consume `JobFunctionRepository`.** The only reason to query it would have been
the (now nonexistent) function state; referential validity of the copied set is guaranteed by the
port law `EmployeeRepository.add` (concept §4, L-E4), which also closes the race where a function is
deleted between reading the source and writing the copy.

## Alternatives considered

### Alternative A — Copy only the cadastral core (no unavailability periods)
- **Description:** duplicate name, workload, preference and functions; start the new record with an
  empty unavailability collection.
- **Pros:** reads "cadastro" in the DoD line literally; the target unit's manager starts from a
  clean slate and declares what they know about.
- **Cons:** an unavailability is a fact about the **person** (vacation, medical leave), not about
  the unit. Dropping it produces, in the target unit, a record that is schedulable during the
  employee's own vacation — a silent correctness hole that only surfaces in Step 4, as a person
  scheduled while away. It also contradicts the theory's own wording ("duplica o registro") and its
  single-item exclusion list.
- **Why rejected:** it trades a real scheduling defect for a cosmetic reading of one word.

### Alternative B — Copy everything including the login link
- **Description:** the copy also points at the same `user_id`.
- **Pros:** the person logs in once and sees both records.
- **Cons:** directly contradicts ADR 3.1.0001 decision iii — linking a record to a login is an
  explicit per-record decision (Stage 3.5), never a by-product of copying.
- **Why rejected:** contradicts an accepted ADR.

### Alternative C — Share instead of duplicate (one record visible in two units)
- **Description:** model a single employee with multiple unit associations.
- **Pros:** no data duplication; editing once updates everywhere.
- **Cons:** contradicts the canonical rule "unidades não compartilham funcionários" (workforce §3.1)
  and the explicit "não compartilha, não vincula" of §3.7; each unit must be able to hold different
  workload, preference and functions for the same person.
- **Why rejected:** contradicts the domain theory.

### Alternative D — Allow copying into the same unit
- **Description:** no destination check.
- **Pros:** one less error path; a cheap "clone this record" for near-duplicate cadastres.
- **Cons:** creates a twin nothing can distinguish (names are non-unique by design), in the unit
  where the manager is least likely to notice; and the feature's stated purpose is cross-unit.
- **Why rejected:** silent duplication with no way to detect it.

### Alternative E — Refuse to copy a terminated (inactive) record
- **Description:** `copy_employee_to_unit` raises when `employee.active is False`, on the grounds
  that "this person also works at unit B" contradicts "this person was dismissed".
- **Pros:** the target unit never receives a record that is dead on arrival.
- **Cons:** it adds a **fourth** item to an exclusion list this ADR closes at three, for a
  degenerate case that harms nothing: the resulting record is hidden from the default listing and
  is not schedulable, and that exact state is already reachable by create-then-deactivate. It also
  forces the manager to reactivate-copy-deactivate for the legitimate case of preparing a rehire in
  another unit.
- **Why rejected:** carrying `active` as-is creates **no state unreachable by another path**, which
  is the same test that decided the (dissolved) fork F2 family; refusing creates an error path with
  no protective value.

### Alternative F — Guard against repeated copies to the same destination
- **Description:** refuse (or no-op) when the source has already been copied into that unit.
- **Pros:** the copy becomes idempotent; no accidental twins.
- **Cons:** requires storing "copied from X" on the new record — a **link** between the two records,
  which workforce §3.7 forbids in the same sentence that defines the operation. A weaker guard
  ("same name already exists in the target unit") is wrong on its own terms: employee names are
  legitimately non-unique, so it would refuse legitimate homonyms and still miss renamed copies.
- **Why rejected:** the only correct implementation contradicts the theory; the cheap approximation
  is wrong. The limit is declared and escalated to the boundary instead.

### Do nothing / status quo
Not viable: the use case is required by the roadmap DoD of this Stage.

## Consequences

### Positive
- The copy is faithful: what the manager sees in unit A is what appears in unit B.
- A person on vacation cannot be scheduled in the unit they were copied into.
- The exclusion list is **closed and written down**, so Stage 3.5 knows exactly what it must not
  break when it introduces `user_id`, and Stage 3.2's own lifecycle decision (3.2.0006) did not have
  to reopen it.

### Negative
- Duplicated unavailability periods drift: cancelling a vacation must be done in both records. This
  is the accepted cost of "os dois registros são independentes" (workforce §3.7) — the alternative
  would be sharing, which the theory rejects.
- **The operation is not idempotent**, and nothing in this layer can make it so (corollary 3). A
  double-click at the boundary produces two records.
- One more application error (`SameUnitCopyError`) for Stage 3.4 to present.

### Neutral / trade-offs accepted
- **The copied instants keep their wall-clock reading, not their absolute one.** Unavailability
  datetimes are naive and interpreted in the timezone of the record's unit
  ([ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md)); if the two units sit
  in different timezones, "from the 10th at 00:00" means the local 10th in each. That is the
  correct reading for the fact being declared (a vacation is a local calendar fact, not an instant),
  and it is the direct consequence of a decision already taken — recorded here so it is not
  discovered as a surprise in Step 4.
- No "copy in bulk" and no "sync after copy" in v1; both are additive later.
- The copy does not check that the target unit exists **or that it belongs to the actor's tenant** —
  `Unit` belongs to identity and staff is import-independent from it. `target_unit_id` arrives in
  the request body and is **not** covered by the `AuthorizedActor` composition, so Stage 3.4 must
  validate it explicitly; escalated as a `[finding]` in the Stage 3.2 concept §10.

## Implementation notes

- Stage 3.2: `features/staff/application/use_cases/copy_employee_to_unit.py`; the new id comes from
  `IdGenerator` with the canonical `EmployeeId(str(next_id()))` conversion (concept 2.2 §5.3).
  Dependencies: `EmployeeRepository` + `IdGenerator` only.
- Test that proves independence must **mutate the copy and re-read the source through the port**
  (and vice versa), comparing the `EmployeeResult` field by field against a snapshot taken before
  the copy — asserting equal field values right after the copy would survive a shared-reference
  implementation, and asserting entity equality would pass unconditionally.
- Stage 3.5: when `user_id` is added to the record, the copy keeps it unset; the acceptance criteria
  of that Stage must include it.

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (decision iii — the
  `user_id` exclusion); [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md) (the
  function set is a non-empty set of tenant-scoped ids);
  [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) (dissolved the inactive-function
  question); [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) (the state the
  copy carries); [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md) (the copied
  instants are wall-clock in the unit's timezone).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.1, §3.2, §3.7.
- [`roadmap.md`](../roadmap.md) — Stage 3.2 DoD; [`overview.md`](../overview.md) §3.

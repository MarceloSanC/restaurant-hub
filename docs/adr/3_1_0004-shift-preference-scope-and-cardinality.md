---
title: ADR 3.1.0004 — Shift preference on the employee record regardless of profile, as a non-empty set of named day periods
description: Architecture Decision Record
when-use: Reference when modeling or consuming the shift preference (Stages 3.1–3.4, Step 5 auto-fill), when questioning whether on-demand employees declare preference, or before changing its cardinality
keywords: [adr, staff, workforce, shift-preference, day-period, cardinality, on-demand, fixed-schedule]
status: accepted
created_at: 2026-07-27
updated_at: 2026-07-27
adr_id: 3.1.0004
decision: Shift preference is an optional attribute of the employee record, declarable by BOTH workload profiles (fixed and on-demand), expressed as a NON-EMPTY SET of named day periods (manhã/tarde/noite/madrugada); absence means no declared preference (indifferent for the auto-fill).
context_stage: 3.1-staff-domain
bounded_context: staff
---

# ADR 3.1.0004 — Shift preference: scope (both profiles) and cardinality (set of named periods)

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The domain doc [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) delegates two
lacunas to the Stage 3.1 concept:

- **§3.3:** kickoff #5 ties the preference to the **fixed** schedule ("carga = horas/semana +
  preferência de turno"), while overview §3 lists the preference next to the jornada profile **in
  general** ("perfil de jornada fixa (…) ou sob demanda (…), com preferência de turno") — whether
  the **on-demand** employee also declares a preference is not fixed.
- **§3.5:** the **cardinality** (one named period or several) is not fixed; kickoff #6 only fixes
  the vocabulary (manhã/tarde/noite/madrugada — a closed set).

Forces:

- Source hierarchy: **Overview > Roadmap > Domain > Concept** — overview §3 attaches the
  preference to the profile disjunction as a whole.
- The auto-fill (Step 5) "respeita carga, preferência de turno e indisponibilidade" and uses
  on-demand people as **overflow** (overview §3) — with no per-profile carve-out.
- Precedent: at the Step 3 domain gate the sponsor chose the **general form** for unavailability
  (datetime interval; the UI may start simpler) — ADR
  [3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) decision (i); the ratified
  progressive-scalability criterion prefers shapes Step 4/5 consume without remodeling.

## Decision

**(a) Scope — the preference belongs to the employee record, independent of the workload
profile.** Both fixed-schedule and on-demand employees may declare it. It is **optional**:
absence (no preference declared) means *indifferent* — the auto-fill treats the employee as
schedulable in any period. Kickoff #5 remains honored: a fixed jornada is still "hours/week +
preference"; this decision only refrains from **denying** the same signal to on-demand people
(an extra who only works nights is exactly the case the overflow logic wants to know about).

**(b) Cardinality — a NON-EMPTY SET of named periods.** The preference value is a non-empty
subset of the closed set {manhã, tarde, noite, madrugada} (workforce §3.5 invariant). One period
is the particular case of the set; declaring all four is equivalent in effect to no preference,
but remains an explicit declaration. The empty set is invalid (declaring "no periods" is
expressed by not declaring a preference).

Structurally the preference is a **value object attached to the employee record**, not a field
inside the workload-profile VO — switching profile (fixed ↔ on-demand) must not silently drop
the declared preference.

## Alternatives considered

### Alternative A — Preference only for fixed-schedule employees (kickoff #5 literal)
- **Description:** on-demand employees cannot declare a preference.
- **Pros:** literal reading of kickoff #5; one less field on on-demand records.
- **Cons:** contradicts the natural reading of overview §3 (higher source); throws away a real
  signal the Step 5 overflow allocation would respect; would force remodeling when the first
  night-only extra appears.
- **Why rejected:** overview §3 lists the preference with the profile in general, and kickoff #5
  defines the fixed jornada's composition without excluding the other profile.

### Alternative B — Single named period per employee
- **Description:** preference is one value of the enum, or none.
- **Pros:** simplest field; single-select UI.
- **Cons:** "tarde e noite" — a common restaurant reality — is inexpressible; migrating a scalar
  column to a collection later remakes the persisted shape (same cost that rejected whole-day
  granularity in ADR 3.1.0001 alt. A); the set is what the Step 5 matcher consumes directly.
- **Why rejected:** fails the progressive-scalability criterion; the single period is already the
  particular case of the set, and the UI may start with single-select.

### Alternative C — Preference inside the WorkloadProfile VO
- **Description:** model the preference as a field of FixedSchedule (and possibly OnDemand).
- **Pros:** matches kickoff #5's phrasing ("carga = horas + preferência").
- **Cons:** replacing the profile VO (update_workload, Stage 3.2) would silently drop or force
  re-copying the preference; couples two orthogonal declarations.
- **Why rejected:** the preference describes the **person's** disposition, not the contract
  shape; orthogonality keeps both editable independently.

### Do nothing / status quo
Not viable: both lacunas are explicitly delegated to this concept by the accepted domain doc;
the 3.2 use cases and the Step 5 matcher need the shape fixed.

## Consequences

### Positive
- Step 5 consumes the preference uniformly for both profiles — no special-casing.
- One period, several periods and "no preference" are all expressible without shape changes.
- Profile switches never lose the declared preference.

### Negative
- The UI must distinguish "no preference" from "all periods" (semantically near-equivalent for
  the matcher, but distinct declarations).

### Neutral / trade-offs accepted
- The period → concrete time-range mapping stays in scheduling (workforce §3.5); staff stores
  only the named periods.
- The preference is a soft signal for the auto-fill (fairness/affinity), not a hard constraint —
  hard blocking is unavailability's job. The matcher semantics belong to Step 5.

## Implementation notes

- Stage 3.1: `features/staff/domain/value_objects/shift_preference.py` — `DayPeriod` closed enum
  (English identifiers glossing manhã/tarde/noite/madrugada) + `ShiftPreference` frozen VO
  wrapping a non-empty `frozenset[DayPeriod]`; employee field `shift_preference: ShiftPreference | None`.
- Stage 3.3: persist as a set (join table or array column — technical decision there).

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (general-form
  precedent, decision i).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.3 (lacuna scope), §3.5
  (lacuna cardinality; closed vocabulary; boundaries belong to scheduling).
- [`overview.md`](../overview.md) §3 (profile "com preferência de turno"; auto-fill respects
  preference; on-demand as overflow).
- Kickoff decisions (project memory, 2026-07-16): #5 (fixed = hours/week + preference), #6
  (named periods vocabulary).
- Process: [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §2 (fork anchored
  in docs → decided by the concept author subagent, 2026-07-27).

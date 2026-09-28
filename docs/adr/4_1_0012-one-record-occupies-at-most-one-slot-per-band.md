---
title: ADR 4.1.0012 — One record occupies at most one slot per band — a structural invariant, not a policy
description: Architecture Decision Record
when-use: Reference before allowing the same employee record in two demands of one band, before adding a second definition of allocation hours to deduplicate overlapping time, or when Stage 4.2 scopes the overlap policy and Stage 4.5 renders a person who covers two functions in one shift
keywords: [adr, scheduling, allocation, band, duplicate-assignment, structural-invariant, overlap-policy, hours, double-counting, coverage]
status: accepted
created_at: 2026-09-27
updated_at: 2026-09-27
adr_id: 4.1.0012
decision: The same employee record may not occupy two slots of the same band — not even in demands for different functions; the aggregate refuses it structurally with a dedicated exception (DuplicateAssignmentInBandError), validated in ShiftBand.__post_init__ and in Schedule.assign, while the overlap policy keeps its full scope over distinct bands (including partially overlapping ones), and hours keep being counted per allocation from the single site of ADR 4.1.0002 §3.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0012 — One record occupies at most one slot per band

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md) §3
fixed **one** counting rule for allocation hours — nominal duration minus the
declared break — consumed by every policy that sums and by the hub's
"horas contratadas × escaladas × cumpridas" (`overview.md` 46). The domain doc sums
**per allocation**: *"toda alocação `a` … cuja faixa pertence ao dia operacional
`d`"* (`shift-scheduling.md` §3.6.3).

The Checkpoint A review of this Stage's concept (2026-09-26) found a state in which
that single rule returns a wrong number. The ratified example puts **two functions
on one band** — *"qua = 1 cozinheiro 16h–00h + 1 assistente 18h–23h + 2 atendentes
16h–00h"* (`overview.md` 41) — so one band may carry a cozinheiro demand and an
atendente demand over the **same** `(start, end)`. Nothing in the aggregate stopped
the **same** record from taking one slot in each: summing per allocation then
returned **16h for 8h of clock time**, and that number fed the daily cap, the weekly
cap, the contracted workload and the hub.

Two forces framed the question:

- The overlap policy's default mode is **`block`**, and ADR 4.1.0003 (c) (lines
  95–97) states why: `block` is reserved for **physical impossibility** — *"`block`
  for overlap (one person in two places)"*. Its only configurable dimension is the
  mode, so that a tenant may *"tolerar sobreposição deliberada de troca 'na porta'"*
  (`shift-scheduling.md` 481–482).
- This BC refuses structurally only what it cannot represent (concept §5.18). A
  declared limit ("the number may double, the policy guards it") was therefore the
  cheap answer, and the concept recommended it.

The question went to the sponsor as Q4 with three options. He rejected the
recommended one, verbatim (2026-09-27): *"como ela é alocada 2 vezes? nao faz
sentido"* — the state itself, not its accounting, is what does not make sense.

## Decision

**The same `EmployeeId` may not appear in two allocations of the same band**, not
even in demands for different functions. This is a **structural invariant** of the
aggregate with a dedicated exception, `DuplicateAssignmentInBandError`.

1. **Where it is enforced.** In `ShiftBand.__post_init__`, pairwise over **all**
   allocations of **all** demands of the band — the band is the level that owns the
   demands, so it is the only level that sees the pair (the same principle as
   ADR 4.1.0009 Decision 2: every uniqueness rule is enforced by the level that owns
   the collection). Because every transition revalidates, the rule holds in
   `Schedule.assign` and in the 4.4 mapper's rehydration alike.
2. **Two disjoint exceptions, by level.** A second slot in the **same demand**
   remains `DuplicateAssignmentError` (the ratified invariant,
   `shift-scheduling.md` 344: *"o mesmo funcionário **não ocupa duas vagas da mesma
   demanda**"*). A slot in **another demand of the same band** is
   `DuplicateAssignmentInBandError`. The error map of the concept §6 carries both,
   and they never overlap.
3. **Why structural and not a ninth policy.** The same person in two slots of the
   **same** interval is physical impossibility in its purest form: there is no second
   person to take the second slot. `block` is exactly what ADR 4.1.0003 (c) reserves
   for that, and a configurable mode here would let a tenant switch on the
   impossible. The "troca na porta" that the configurable mode exists to allow
   happens between **distinct** bands (one leaves 16h–00h, another enters
   22h–02h), never between two slots of one interval.
4. **The overlap policy keeps its full scope.** Allocations of the same record on
   **distinct** bands — including partially overlapping ones, and including different
   functions (`16h–00h` and `18h–23h` of one Wednesday) — remain **accepted** by the
   domain and governed by the overlap policy of 4.2, with its configurable mode. This
   ADR removes one degenerate sub-case from the configurable surface; it does not
   narrow the policy anywhere else, and the concept declares that narrowing
   explicitly (§5.23, §12) because the doc's predicate read literally covered it.
5. **Hours stay per allocation, from one site.** With the degenerate state gone, the
   single formula of ADR 4.1.0002 §3 is **correct again without a second
   definition**: no allocation pair can now count the **same** interval twice.
   Overlapping **distinct** bands still count their intersection twice; that is two
   distinct shifts, not a degenerate aggregate, and how the caps and the hub treat it
   is a declared 4.2 gap (concept §5.7, §8).
6. **The product consequence is stated, not hidden.** Someone covering two functions
   in one shift fills **one** slot, and the other stays **uncovered**: Ana, Friday
   16h–00h, with a cozinheiro slot and an atendente slot on the same band, takes one
   of them and the day's coverage drops **below 100%** — a legitimate, visible state
   (`shift-scheduling.md` 243–244: *"Cobertura **< 100% é estado legítimo**"*; `N` is
   a target, not a cap — ADR 4.1.0003 (g)). That is more honest than declaring both
   slots filled by one person and sending 16h to the hub. Representing "one person,
   two functions, one shift" as full coverage — a multi-function slot, or coverage
   counted per person — is a product request for 4.2/4.5, not a state 4.1 accepts
   silently.

## Alternatives considered

### Alternative A — Count per allocation and declare the doubled number as a limit
- **Description:** the option this Stage's concept recommended: allow the same record
  in two slots of one band, declare in §5.7 that `Σ hours` returns 16h for 8h of
  clock time, and rely on the overlap policy (default `block`) to keep the state from
  appearing silently.
- **Pros:** no new invariant, no new exception, no narrowing of any policy; the
  ratified per-allocation formula is untouched; "sum per record" could still arrive
  additively in 4.2.
- **Cons:** the wrong number is visible in the product — daily cap, weekly cap,
  contracted workload and the hub's "horas escaladas" all double — and a tenant with
  the overlap policy in `warn` reaches that state with one click. The limit is
  declared in a document nobody reads while looking at a dashboard.
- **Why rejected:** **rejected by the sponsor**, verbatim: *"como ela é alocada 2
  vezes? nao faz sentido"*. He did not treat it as an accounting question: the state
  is nonsensical, so the fix belongs where the state is created, not where it is
  summed.

### Alternative B — Allow the state, and sum per record with a geometric union of the time ranges
- **Description:** keep the allocation pair legal and make the hours reading return
  the real 8h, by unioning the intervals of the record's allocations per operational
  day.
- **Pros:** the number is right without forbidding anything; it also fixes the
  intersection of distinct overlapping bands, which this ADR leaves declared.
- **Cons:** it creates a **second** definition of allocation hours beside the single
  one ADR 4.1.0002 §3 fixed and this Stage's single computation site
  (ADR 4.1.0007) — exactly what both exist to prevent. It changes the **subject** of
  the reading (from the allocation to the record × day), needs the whole collection to
  answer, and reopens "which number is the hub's".
- **Why rejected:** it pays for a nonsensical state with a duplicated core formula,
  and it would still leave the aggregate holding a person in two slots of one shift —
  the thing the sponsor objected to.

### Alternative C — Allow it and let only the overlap policy warn
- **Description:** no invariant and no declared limit either: treat the same-band
  duplicate as an ordinary overlap violation, which the policy already detects
  (`início_A < fim_B ∧ início_B < fim_A` is trivially true for one band), leaving the
  mode configurable per tenant.
- **Pros:** zero change to the aggregate; one uniform mechanism for every overlap;
  the tenant decides.
- **Cons:** in `warn` the acknowledgement **saves** the allocation
  (ADR 4.1.0001 §1), so the doubled hours reach the caps and the hub with the
  editor's blessing — a wrong number, not a tolerated risk. And it offers as a
  configuration something that has no meaning in the world: nobody staffs one
  interval twice with one person.
- **Why rejected:** it leaves a wrong number in the hub by design, and `block` in
  ADR 4.1.0003 (c) is reserved for precisely this case, which makes "configurable"
  the wrong shape for it.

### Alternative D — Do nothing / status quo
- **Why not acceptable:** the status quo *is* Alternative A (the concept already
  declared the limit), and the sponsor rejected it. Leaving the question open would
  also leave `worked_minutes_of` with a known-wrong sum for a state the aggregate
  produces, and 4.4 would persist it.

## Consequences

### Positive
- The single hours rule of ADR 4.1.0002 §3 is **correct** again for the whole
  aggregate, with no second definition and no geometric union.
- The nonsensical state is impossible at the root, so it cannot be created by a
  mutation, by a tenant's `warn` configuration, or by the 4.4 mapper rehydrating old
  data.
- The refusal is **named** (`DuplicateAssignmentInBandError`), so 4.5 can say "Ana
  already has a slot on this band" instead of showing a generic conflict.
- The invariant is cheap and testable without a database: one pairwise check in
  `ShiftBand.__post_init__`.

### Negative
- The concept **narrows** the literal reading of the doc's overlap policy
  (`shift-scheduling.md` 476, 481–482), which covered the same-band case with a
  configurable mode. The narrowing has to be declared and carried in every derived
  sweep (concept §5.18, §5.23, §12, CA13).
- A person who really covers two functions in one shift leaves a slot **uncovered**,
  and the schedule shows coverage below 100%. Whoever reads the calendar sees a gap
  where a manager sees a person doing two jobs — a product gap for 4.2/4.5, and a
  support question in the meantime.
- One more exception in the hierarchy (20 instead of 19) and one more row in the
  error map, with the pair of duplicate-allocation rows needing the "disjoint by
  level" explanation.

### Neutral / trade-offs accepted
- Hours of the same record on **distinct** overlapping bands still count the
  intersection twice. That stays a declared limit governed by the overlap policy, and
  how the caps and the hub treat it is a 4.2 gap (concept §5.7, §8 (b)).
- Whether "one person, two functions, one shift" deserves a first-class
  representation (a multi-function slot, or coverage per person) is left to product,
  not decided here.
- The demand-level rule survives as its own exception even though the band-level one
  implies it: `ShiftDemand` validates the collection it owns, and the two exceptions
  name different facts for the editor.

## Implementation notes

- `ShiftBand.__post_init__` gains a pairwise check over the flattened allocations of
  its demands, alongside the two checks already there (demand ids, and the allocation
  break against `nominal_minutes`). Pairwise over the **whole** collection, proven
  with a **non-consecutive** pair in a collection of three — the Checkpoint C lesson
  of Stage 3.1 (`3.1-staff-domain/technical.md` §7, `[decision]` of 2026-07-29).
- `Schedule.assign` needs no separate guard beyond rebuilding the band: the
  revalidation raises. The concept's acceptance criterion CA25 pins both directions
  (refused on the same band, accepted on distinct bands) and CA10 pins the
  rehydration path.
- This changes no Task boundary in the concept's measurement: the check lands in the
  `ShiftBand` Task, the exception in the exceptions Task, the `assign` path in the
  mutations Task (concept §12, still 11 Tasks).

## References

- Related ADRs:
  [ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md) §3
  (the single counting rule, correct again without a second definition);
  [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (a)
  line 73 (the overlap row: *"— (physical impossibility) | **block**"*), (c) lines
  95–97 (*"`block` for overlap (one person in two places)"*) and (g) (`N` is a
  target, not a cap, so an uncovered slot is legitimate);
  [ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md) (the single hours
  computation site that Alternative B would duplicate);
  [ADR 4.1.0009](./4_1_0009-schedule-is-the-single-aggregate-root.md) Decisions 2 and
  6 (uniqueness enforced by the level that owns the collection; every invariant
  validated in `__post_init__`, so rehydration cannot bypass this one);
  [ADR 4.1.0010](./4_1_0010-enabled-band-is-an-element-of-the-day.md) (two functions
  on one band, and distinct overlapping bands as legitimate);
  [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md) (the same band
  now carries per-person breaks, which is what makes "two slots, one person" clearly
  redundant rather than a way to model different hours).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §3.3 lines 243–244 (coverage below 100% is a legitimate state), §3.4 line 344 (the
  ratified per-demand invariant this ADR extends), §3.6.1 lines 476 and 481–482 (the
  overlap predicate and its configurable mode — narrowed here in the degenerate
  sub-case), §3.6.3 (hours summed per allocation).
- [`overview.md`](../overview.md) line 41 (two functions on one band), line 46 (the
  hub's single hours number).
- Concept: [`docs/stages/4.1-scheduling-domain/concept.md`](../stages/4.1-scheduling-domain/concept.md)
  §4, §5.7, §5.12, §5.18, §5.23, §6, §7, §10, §11 (CA10, CA12, CA13, CA25), §12,
  §13 (Q4, answered).
- Sponsor decision (2026-09-27, via the master session), verbatim: *"como ela é
  alocada 2 vezes? nao faz sentido"*.

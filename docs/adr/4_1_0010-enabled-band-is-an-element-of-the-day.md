---
title: ADR 4.1.0010 — The enabled band is an element of the schedule's day, and a demand is unique per (band, function) while distinct overlapping bands are allowed
description: Architecture Decision Record
when-use: Reference before embedding the time range inside ShiftDemand, before allowing two demands of the same function on the same band, before forbidding overlapping bands on one day, or when Stage 4.2 decides whether over-coverage is counted per demand or per (day, band, function)
keywords: [adr, scheduling, shift-band, enabled-band, demand, cardinality, overlap, break, coverage, peak-staffing]
status: accepted
created_at: 2026-09-26
updated_at: 2026-09-27
adr_id: 4.1.0010
decision: The enabled band (faixa de funcionamento) is a first-class internal entity of the schedule holding the TimeRange and its declared break; demands live inside a band and are unique per (band, function), quantity zero included; two bands of the same day may not share the same (start, end) pair, but distinct bands may overlap in time, including for the same function.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0010 — The enabled band is an element of the day

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

[`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.3 leaves the
**cardinality of the demand** as a gap for this concept (lines 257–258): *"no máximo
uma demanda por `(dia, faixa, função)`, ou duas da mesma função em faixas
parcialmente sobrepostas?"* — and §6 lists it for this Stage (line 1087). Stage
4.2's own gap (lines 632–634) is written on top of the answer: whether over-coverage is
counted per demand or per `(day, band, function)` *"quando a cardinalidade da 4.1
admitir duas demandas da mesma função em faixas sobrepostas"*.

The ratified material is unusually precise here. `overview.md` line 41 reads:
*"Escala com período configurável (default **semanal**): por dia, **habilitam-se
faixas de horário livres** e define-se a **demanda por função × faixa** (ex.: qua
= 1 cozinheiro 16h–00h + 1 assistente 18h–23h + 2 atendentes 16h–00h)"*. Three
facts follow from that single line:

1. **Two acts, not one:** bands are *enabled* per day; demand is *defined* per
   function × band. The domain doc names the result of the first act "faixas de
   funcionamento — as faixas **habilitadas por dia** na escala" (§2, line 107),
   the same thing the calendar draws its mini-cards over (`overview.md` 46).
2. **Two functions share one band:** `16h–00h` carries both the cozinheiro and the
   two atendentes.
3. **Two bands of the same day overlap:** `16h–00h` and `18h–23h` are both
   Wednesday's.

And the band is what **carries the declared break** that
[ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
§3 put on the time range, from which every allocated person's hours are counted.

## Decision

1. **The enabled band is a first-class internal entity — `ShiftBand`** — holding
   the `TimeRange` (with its declared break) and the demands declared on it. It is
   the fourth entity of the Stage, beyond the three the roadmap block lists.
2. **A demand belongs to a band**, by containment, and is **unique per (band,
   function)**: a band's demands have pairwise distinct `job_function_id`. Quantity
   `0` is a legitimate demand ("band enabled, no demand of this function"), and a
   band with no demand at all is legitimate too — it is the result of the first act
   before the second.
3. **No duplicated band:** two bands of a schedule may not have the same
   **`(start, end)` pair** — same day, same hours. The key is the pair, **not** the
   whole `TimeRange` value: keying on the value would include `break_minutes`, so
   `16h–00h` with break 0 and `16h–00h` with break 60 would be two legitimate bands
   on one Wednesday — exactly the defect for which Alternative A is rejected below.
   The case that a wider key would have served (different breaks for different
   people on one clock band) is served instead by the optional break on the
   allocation ([ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md),
   sponsor, 2026-09-26).
4. **Distinct bands may overlap in time, including for the same function:**
   `2 atendentes 16h–00h` plus `1 atendente 18h–22h` for the peak is a legitimate
   schedule. The consequence for the same person being allocated to two
   **distinct** overlapping bands is the **overlap policy** of 4.2, with its
   configurable mode — not a structural refusal here. Two slots of the **same**
   band are a different case: since
   [ADR 4.1.0012](./4_1_0012-one-record-occupies-at-most-one-slot-per-band.md)
   (sponsor, 2026-09-27) the same record in two demands of one band is refused
   structurally, which leaves this decision's scope — distinct bands — untouched.
5. **This cardinality is what makes the ratified over-coverage formula
   well-defined.** `alocados(demanda) > N`
   ([ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (g))
   has an unambiguous subject once a demand is unique per (band, function): the
   surplus person belongs to exactly one demand. **How the warning is counted and
   reported — per demand, or aggregated per `(day, band, function)` — remains a 4.2
   decision** (domain doc §3.6.8, lines 632–634), now *informed* by this answer
   instead of blocked by it. This ADR frames the gap; it does not close it.

## Alternatives considered

### Alternative A — The time range is an attribute of each demand (no band entity)
- **Description:** the shape the roadmap's file list suggests: `ShiftDemand(day,
  time_range, job_function_id, quantity)`, and "the day's enabled bands" is a
  derived set of the distinct ranges of its demands.
- **Pros:** three entities instead of four; matches the roadmap block literally;
  one table fewer in 4.4.
- **Cons:** the ratified example stores `16h–00h` **twice** on one Wednesday, once
  per function — and each copy carries its own **declared break**, so the same
  visual band can count 8h for the cozinheiro and 7h for the atendentes, which the
  "single counting rule" of ADR 4.1.0002 §3 exists to prevent (the aggregate would
  need a new invariant just to keep the copies equal). Enabling a band before
  choosing functions is not representable, although `overview.md` 41 describes it
  as the first act. Moving a band's hours means editing every demand that shares
  it, and a partial edit silently splits one band into two.
- **Why rejected:** it makes a ratified sentence ("habilitam-se faixas … e
  define-se a demanda") unrepresentable and turns an equality between copies into
  an invariant the domain has to police.

### Alternative B — Band as a value inside the schedule (a set of ranges per day), demands referencing it by value
- **Description:** no identity for the band; `Schedule.enabled_ranges` keyed by
  operational day, demands holding the range value.
- **Pros:** no fourth entity; uniqueness per (range, function) is still expressible.
- **Cons:** a band has no stable address, so moving a band's hours is a remove plus
  an add — which discards the demands and allocations hanging off it, and gives the
  4.4 audit trail nothing stable to name. The product case (adjust Friday from
  16h–00h to 17h–01h after the night is built) would mean rebuilding it.
- **Why rejected:** identity is exactly what the band needs in order to be adjusted
  without losing the work attached to it — which the sponsor then confirmed as the
  product behaviour (*"Permite mover (Recomendada)"*, 2026-09-26; concept §5.22).

### Alternative C — At most one demand per (day, function), i.e. forbid overlapping bands for the same function
- **Description:** the narrow reading of the gap: a function may be demanded once
  per day.
- **Pros:** over-coverage and hour sums per (day, function) become trivial; no
  ambiguity about which demand a surplus belongs to.
- **Cons:** forbids peak reinforcement, the commonest shape in a restaurant — and
  the ratified example already reinforces the same interval with a second function;
  the editor's workaround (one wide band with a bigger `N`) loses the information
  that the extra person is only needed at the peak, which is precisely what the
  demand exists to express.
- **Why rejected:** it restricts the shape for a counting convenience, and undoing
  the restriction later would mean reshaping stored data — the opposite of the
  project's progressive-scalability criterion.

### Alternative D — Allow several demands of the same function on the same band
- **Description:** `N` split over two rows for the same (band, function).
- **Pros:** it is the literal second reading of the gap as the domain doc writes it
   (*"ou duas da mesma função em faixas parcialmente sobrepostas?"*, line 258), so it
   had to be answered rather than assumed away; it would let an editor split `N`
   into rows with different provenance (e.g. fixed staff versus on-demand).
- **Cons:** two rows for the same slot are just `N₁+N₂`, and
  `alocados(demanda) > N` becomes ambiguous: the same surplus person is over the
  target of one row and inside the other.
- **Why rejected:** the provenance it would express has no ratified requirement
   behind it, while the redundancy breaks the ratified over-coverage formula — the
   same `N` split over two rows makes the surplus person over one target and inside
   the other.

### Alternative E — Do nothing / leave cardinality to 4.2
- **Why not acceptable:** 4.2's own gap is written as depending on this answer
  (doc lines 632–634), and `declare_demand` must accept or refuse the second demand of a
  function on a band.

## Consequences

### Positive
- One band, one declared break, one hours number for everyone allocated to it.
- "The day's enabled bands" is a direct read (`bands_of`), which is what the
  calendar of 4.5/4.7 and the hub draw.
- Peak reinforcement is representable without inflating a wide band's `N`.
- Uniqueness per (band, function) is structural: it lives in `ShiftBand`.

### Negative
- A fourth entity beyond the roadmap block — declared as divergence 3 of the
  concept §1 — and a fourth child table for 4.4.
- Overlapping **distinct** bands mean the same person can be allocated twice in
  overlapping hours without the domain objecting; the guarantee comes from the
  overlap policy (4.2, default `block`), so a tenant that configures it to `warn`
  accepts it knowingly. Two slots of the **same** band are not in that set: they are
  refused structurally
  ([ADR 4.1.0012](./4_1_0012-one-record-occupies-at-most-one-slot-per-band.md)).
- Reading "how many people does Wednesday need as cozinheiro" is a sum over bands,
  not a single row.

### Neutral / trade-offs accepted
- Whether the surplus warning is reported per demand or per `(day, band, function)`
  stays a 4.2 decision (consistent with Decision 5, which frames it rather than
  answering it); so does whether lowering `N` reopens an acknowledged violation
  (doc §3.6.8).
- The named-period map (manhã/tarde/noite → concrete bands, doc §3.2) is unaffected:
  it produces `TimeRange` values, and its owner Stage is still open in the roadmap.

## Implementation notes

- `features/scheduling/domain/entities/shift_band.py`; pairwise uniqueness of
  `job_function_id` in `ShiftBand.__post_init__` and of the band's `(start, end)`
  pair in `Schedule.__post_init__`, each validated over the whole collection (so a
  non-consecutive duplicate pair is caught — the Stage 3.1 lesson, recorded as
  `[decision] Checkpoint C` in `3.1-staff-domain/technical.md` §7, 2026-07-29).
- `declare_demand` raises `DuplicateShiftDemandError`; `enable_band` raises
  `DuplicateShiftBandError`.

## References

- Related ADRs: [ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
  §3 (the break lives on the range; one counting rule);
  [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (g)
  (over-coverage per demand; `N` is a target) and (c) (configurable modes);
  [ADR 4.1.0011](./4_1_0011-declared-break-on-band-and-allocation.md) (the break on
  both levels, which narrows this ADR's uniqueness key to `(start, end)`);
  [ADR 4.1.0007](./4_1_0007-time-range-as-naive-minute-instants.md) (the range as a
  value); [ADR 4.1.0009](./4_1_0009-schedule-is-the-single-aggregate-root.md)
  (containment and the single root).
- [`overview.md`](../overview.md) line 41 (two acts and the three-band example),
  line 46 (calendar over the "faixas de funcionamento").
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md)
  §2 (line 107), §3.3 (the gap, lines 257–258), §3.6.8 (the 4.2 gap on how the
  surplus is counted, lines 632–634), §6 (line 1087).
- [`roadmap.md`](../roadmap.md) 1320–1323 (the three-entity file list this ADR
  diverges from; the entities line is 1321).
- Concept: [`docs/stages/4.1-scheduling-domain/concept.md`](../stages/4.1-scheduling-domain/concept.md)
  §1 (divergence 3), §4, §5.10–§5.12, §5.22, §7, §13 (Q2 and Q3, both answered by
  the sponsor on 2026-09-26).

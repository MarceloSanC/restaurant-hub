---
title: ADR 4.1.0002 — Weekly schedule period with a configurable start day, operational day from a configurable cutoff (default 05:00), and allocation hours = nominal duration minus declared break
description: Architecture Decision Record
when-use: Reference before modeling SchedulePeriod or TimeRange, before deciding which day a shift that crosses midnight belongs to, before summing hours for any policy or hub metric, or when a future Stage proposes fortnightly/monthly periods, night-hour fiction or an intra-shift-break policy
keywords: [adr, scheduling, schedule-period, week-start, operational-day, cutoff, time-range, midnight, break, hours, nominal, clt, domain-gate]
status: accepted
created_at: 2026-09-13
updated_at: 2026-09-13
adr_id: 4.1.0002
decision: The v1 schedule period is a week whose start day is configurable per restaurant (end = start + 6); a day is an operational day — a 24h window starting at a per-restaurant cutoff time (default 05:00) — and a time range/allocation belongs to the operational day in which it starts; the hours of an allocation are its nominal duration minus a break declared on the time range (minutes, default 0), a single function consumed by every policy and by the hub; night-hour fiction and an intra-shift-break policy are deferred as evolution.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0002 — Weekly period, operational day and allocation hours

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Taken at the **domain gate of Step 4** (2026-09-13) for
[`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md). It
consolidates fork F2 (period shape and week start), its follow-up question (the cutoff default)
and fork F3 (how many hours an allocation counts). All three were decided by the **human
sponsor** (Marcelo, 2026-09-13).

Forces:

- `overview.md` §3 fixes "escala com período configurável (default **semanal**)" (line 40) and
  the glossary example "qua = 1 cozinheiro **16h–00h**" — a shift that ends at midnight is listed
  under Wednesday. Nothing ratified says what happens to a shift that ends at 02:00, nor on which
  day the week begins.
- Three policies sum hours (daily cap, weekly cap, contracted workload) and the hub reports
  "horas contratadas × escaladas × cumpridas" (`overview.md` 45) — one number, so one counting
  rule. CLT art. 71 § 2º says rest breaks are not counted in the working time; art. 73 § 1º says a
  night hour counts as 52 min 30 s. The product does not pay hours (`overview.md` 56), so this is
  counting for validation and reporting only.
- The skeptic review of the draft (finding #3) rejected "the range belongs to the civil day in
  which it starts" as an unanchored extension of the 16h–00h example, and (finding #1) showed
  that evaluating rest "between civil days" mis-handles split shifts.
- Two independent sources converge on Monday as a plausible week start — ISO 8601 via the Python
  docs (`isoweekday()`: "Monday is 1") and Decreto 10.854/2021 art. 158 § 4º (a "semana" for
  **remuneration** purposes runs Monday to Sunday) — but neither binds a scheduling calendar, and
  many restaurants close their week on another day.

## Decision

### 1. Period = a week with a configurable start day (F2)

Sponsor, verbatim: *"incio e fim da semana sao configuraveis"*. The schedule period is the
sequence of **7 operational days** starting on the **week start day configured per restaurant**
(end = start + 6). The **accounting week** used by the weekly cap and the workload policy is the
same 7 operational days; the two concepts stay distinct in the model so that fortnightly/monthly
periods remain an additive evolution, but in v1 they coincide. No fixed default day is imposed by
law; the **default is Monday** — anchored on ISO 8601 (via `isoweekday()`) and Decreto 10.854/2021
art. 158 § 4º — and every restaurant may change it.

### 2. Operational day from a configurable cutoff, default 05:00 (F2)

Sponsor, verbatim: *"horario de fim do dia pode ser configurado tambem (por exemplo, jornada até
as 2h da manha conta no mesmo dia anterior, começou sexta as 18h e acabou sabado as 2h conta como
um dia só)"*. A day of the schedule is a **24h window starting at the cutoff time** configured per
restaurant. A time range — and the allocation on it — **belongs to the operational day in which
it starts**. Daily cap, accounting week and rest-between-shifts all use the operational day, not
the civil day. Asked for the default, the sponsor chose **"05:00 (Recomendada)"**; the rationale
for that default is the end of the CLT night period (art. 73 § 2º: "entre as 22 horas de um dia
e as 5 horas do dia seguinte") — a default only, configurable, with no force of rule.

### 3. Allocation hours = nominal duration − declared break (F3)

Sponsor: *"Menos intervalo declarado (Recomendada)"*. The time range carries a **break in
minutes, default 0**, declared by the editor. `hours(a) = (end − start) − break`. This is the
**single function** consumed by every policy that sums hours and by the hub. A restaurant that
declares no break gets nominal hours; one that declares it gets the number the law describes
(CLT art. 71 § 2º). The invariant `0 ≤ break < nominal duration` follows (an allocation of zero
hours is not work).

### 4. Deferred as evolution (recorded, not decided)

- **Night-hour fiction** (CLT art. 73 § 1º, 52'30" per hour between 22:00 and 05:00): a
  per-restaurant flag inside the same `hours(a)` function — no change of shape.
- **Intra-shift-break policy** (CLT art. 71 caput/§ 1º; 30-minute floor by CCT, art. 611-A III):
  now feasible because the break is declared; a new strategy in the same protocol (see
  [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md)).
- A range that crosses the **next** cutoff (e.g. 22:00–06:00 with cutoff 05:00): forbid, split or
  allow-and-assign-to-start-day — a gap for the 4.1 concept.

## Alternatives considered

### Period and week start (F2)

- **A — Free date interval with an independent accounting week (triage's recommendation).**
  The most general shape (fortnight/month are just longer intervals), but a 30-day "published"
  schedule crosses several accounting weeks and invites bad practice. *Rejected:* the sponsor
  chose the week with configurable boundaries; the general form stays as evolution.
- **B — Fixed ISO week (Monday), no configuration.** Zero configuration, but a restaurant that
  closes its week on Sunday/Saturday sees the "wrong" week and the weekly counter resets on the
  wrong day. *Rejected:* the sponsor asked for configurable start/end.
- **C — Enum {weekly, monthly}, configurable week start.** The civil month becomes a 28–31-day
  aggregate that "publish" publishes whole. *Rejected:* not needed by the pilot; covered by the
  evolution path.
- **D — Fixed Sunday week (spreadsheet habit).** *Rejected:* the inverse of B, same rigidity.

### Day of a range (cutoff)

- **E — Slice at civil midnight into two segments** (Fri 22–24 + Sat 00–02). Exact per civil
  day, but one shift becomes two pieces in UI, demand and hub, a Sunday-night shift falls into
  the next week, and it contradicts the sponsor's "conta como um dia só". *Rejected.*
- **F — Civil day of start, no cutoff.** A 02:00–06:00 shift would belong to the next civil day
  while 22:00–02:00 belongs to the previous; not anchored (skeptic finding #3). *Rejected:* the
  operational day with a cutoff is the general form; the civil day is the case cutoff = 00:00.

### Hours of an allocation (F3)

- **G — Gross nominal `end − start`.** Overstates hours for anyone with a meal break (a 40h
  contract "closes exactly" while the person works 35h); the hub inherits the error.
  *Rejected:* the declared break with default 0 gives the same number when nothing is declared
  and the right one when it is.
- **H — Break derived from the law** (> 6h → −1h; 4–6h → −15 min). Hard-codes CLT art. 71,
  contradicting `overview.md` §6, and ignores CCTs that fix 30 min (art. 611-A III).
  *Rejected:* the product declares, it does not guess.
- **I — Night-hour fiction in v1.** A flag the pilot does not need yet; it changes the weekly
  sum of night workers (35h nominal vs 40h fictional for five 22:00–05:00 nights). *Deferred:*
  it enters the same function later without changing shape.

### Do nothing / status quo
Not applicable: the daily cap, the weekly cap and the workload policy cannot be specified
without knowing which day an allocation belongs to and how many hours it counts.

## Consequences

### Positive
- The sponsor's own example ("sexta 18h–sábado 2h conta como um dia só") is the rule; night
  operations are first-class, not an edge case.
- One counting function; one number for policies and hub.
- Configurable start day and cutoff absorb restaurants that close their week or their day
  differently, without code.

### Negative
- Two per-restaurant settings (start day, cutoff) that must be explained; changing them with
  existing schedules is a 4.3 concept gap.
- A range that crosses the next cutoff is undefined until the 4.1 concept decides.
- Editors who forget to declare the break get nominal hours (no worse than today's spreadsheet).

### Neutral / trade-offs accepted
- Rest-between-shifts is evaluated **between operational days**; gaps inside the same
  operational day are treated as intra-shift breaks (an evolution policy) — a declared v1 limit,
  see [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md).
- Monday is not imposed; the sources only make it a plausible default.

## Implementation notes

- Lands in Stage 4.1 (`SchedulePeriod`, `TimeRange` with `break`, the `hours()` function), with
  the tenant settings (start day, cutoff) persisted in 4.4 next to the validation config. Theory:
  [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.1, §3.2, §3.6.9.

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (half-open
  `[start, end)` semantics that scheduling assumes — decision (i)); [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md)
  (wall-clock in the unit's timezone); [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md)
  (policies that consume the operational day and `hours(a)`).
- [`overview.md`](../overview.md) — §3 line 40 (configurable period, default weekly; 16h–00h
  example), line 45 (one hours number), line 56 (no money); §6 line 110 (CLT not hard-coded).
- [`roadmap.md`](../roadmap.md) — Stage 4.1 (`SchedulePeriod`, `TimeRange`, line 1206), Stage 4.2
  (policies that sum hours).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §2,
  §3.1, §3.2, §3.6.2–§3.6.5, §3.6.9, §6.
- Sponsor decisions F2 (+ cutoff default) and F3 on 2026-09-13 (session record
  `gate-decisions.md`).
- External (primary, verified on the Planalto consolidated text by direct download,
  2026-09-13):
  - BRASIL. **Decreto-Lei nº 5.452, de 1º de maio de 1943** (CLT), art. 71, *caput*, §§ 1º–2º
    (redação original) — "Os intervalos de descanso não serão computados na duração do
    trabalho."; art. 73, §§ 1º, 2º e 4º (Decreto-Lei nº 9.666/1946) — night hour of 52'30",
    night period 22h–5h; art. 611-A, III (Lei nº 13.467/2017) — 30-minute floor by CCT.
    Disponível em: https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em:
    13 set. 2026.
  - BRASIL. **Decreto nº 10.854, de 10 de novembro de 2021**, art. 158, § 4º — "Considera-se
    semana, para fins de pagamento de remuneração, o período de segunda-feira a domingo que
    antecede o dia determinado como repouso semanal remunerado." (remuneration definition only;
    supports Monday as a plausible default). Disponível em:
    https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/decreto/D10854.htm. Acesso em:
    13 set. 2026.
  - PYTHON SOFTWARE FOUNDATION. **datetime — Basic date and time types**, `date.isoweekday()`
    ("Monday is 1 and Sunday is 7"), `date.isocalendar()`. Disponível em:
    https://docs.python.org/3/library/datetime.html. Acesso em: 13 set. 2026. (Anchor for the
    ISO 8601 week convention; the ISO standard itself is paywalled and was not consulted.)

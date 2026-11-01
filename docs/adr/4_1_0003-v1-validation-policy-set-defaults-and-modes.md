---
title: ADR 4.1.0003 — The v1 validation policy set (eight policies), their value defaults from primary sources, their block/warn mode defaults, the "counts toward workload" flag on the allocation, the employee record per unit as the policy subject, and the function-mismatch and over-coverage policies with acknowledged exceptions
description: Architecture Decision Record
when-use: Reference before adding, removing or re-defaulting a scheduling validation policy, before changing a block/warn default, before touching the "counts toward workload" or "function exception" flags on the allocation, before letting anything but a manual acknowledgement assign a record to a function it does not hold or allocate beyond the demand, or when a future Stage proposes weekly rest, Sunday-off, intra-shift break, 12x36 or hours-bank policies
keywords: [adr, scheduling, validation, policy, block, warn, overlap, rest-between-shifts, max-hours, workload, unavailability, counts-toward-workload, function-mismatch, function-exception, over-coverage, coverage, clt, cct, configurable, domain-gate]
status: accepted
created_at: 2026-09-13
updated_at: 2026-09-26
adr_id: 4.1.0003
decision: v1 ships eight configurable-per-restaurant validation policies (including over-coverage, N being a target rather than a cap) — overlap (block), allocation × unavailability (fixed block), rest between shifts (11h, warn), daily cap (10h, warn), weekly cap (44h, warn), contracted workload (tolerance 0h, excess direction, warn, fixed-schedule only), function mismatch (warn; the acknowledgement saves the allocation flagged as a function exception without touching the employee record; block configurable) and over-coverage (warn; `N` is a target, not a cap, and the acknowledgement saves the surplus allocation; block configurable) — with block reserved by default for physical impossibility; the "counts toward workload" flag lives on the allocation, is declared by the editor, defaults to "counts" and is read only by the workload policy; every policy's subject is the employee record per unit; the auto-fill never creates a function exception; weekly rest, Sunday-off, intra-shift break, 12x36 and hours bank are deferred as evolution.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0003 — v1 validation policy set, defaults and modes

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Taken at the **domain gate of Step 4** for
[`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md): fork
F4 of the gate triage (decided by the **human sponsor**, Marcelo, on 2026-09-13 after a worked
example with real data) and fork F9 — what happens when an editor assigns a record to a demand
for a function the record does not hold (decided by the sponsor on 2026-09-14). F9 is recorded
here as sub-decisions (f) and (g) because each adds a row to the same policy table.

Forces:

- `overview.md` §3 (line 43) lists the validations with an open "etc." — "sobreposição de
  alocação, descanso entre jornadas, tetos de horas **etc.**" — in **block or warn** mode, live,
  with conscious acceptance. `roadmap.md` Stage 4.2 (1373, 1380) closes the list at four:
  overlap, rest between shifts, daily/weekly cap, contracted workload.
- `workforce.md` §1/§3.6 and [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md)
  treat **allocation × unavailability** as "validação do Step 4" — it is not one of the four.
- `overview.md` §6 (line 111): **labour law is not hard-coded**; every legal value is a default
  of a per-restaurant parameter, because the collective agreement (CCT) of each restaurant's
  territorial base may change it (CF art. 7º XIII; CLT art. 611-A). The product embeds no CCT.
- The external-sources pass (2026-09-13) verified, on the Planalto consolidated text, the legal
  values that serve as defaults (CLT 66; 58 + 59; CF 7º XIII) and found other validations the
  law supports but the roadmap does not list (weekly rest — CLT 67, 611-B IX; Sunday off every
  three weeks — Lei 10.101 art. 6º p.u.; intra-shift break — CLT 71; 12x36 — CLT 59-A;
  compensation/hours bank — CLT 59 §§ 2º/5º/6º).
- Kickoff decision #11 models the "extra period" as a **classification** ("counts or not toward
  the contracted workload") without money, with the real effect in 4.x; the code
  (`workload_profile.py` 35–39) places the classification on the **allocation**. Its default and
  the direction of the workload policy were open.
- The skeptic review (finding #2) noted that the same person may hold N employee records in N
  units (`workforce.md` §3.1) while the legal limits belong to the employee vis-à-vis the
  employer; the draft did not say whether policies evaluate per record or per person.
- [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md) fixes that a record "matches
  vacancies of **any** of its functions" — the **matching** semantics — but not what the system
  does when the editor assigns a record to a function it does not hold. The draft treated it as
  a structural refusal ("fix the record in staff"); the skeptic review (finding #10) pointed out
  the real alternative (emergency cover with a warning) and the question was escalated (F9).

## Decision

Sponsor (F4, 2026-09-13): *"Confirmar a tabela (Recomendada)"*. The sponsor treated the first
six rows below as **one** decision. The sub-decisions (a)–(e) are enumerated here only so that
each can be traced and, if needed, superseded independently — they were not five separate
questions. The seventh row is sub-decision (f), taken on 2026-09-14 (F9); the eighth is sub-decision (g),
taken on 2026-09-26 (F10).

### (a) The v1 policy set — eight policies

| Policy | What it validates (formula) | Default value (source) | Default mode | Configurable |
|---|---|---|---|---|
| Overlap | same record, `start_A < end_B ∧ start_B < end_A` (half-open) | — (physical impossibility) | **block** | mode |
| Allocation × unavailability | overlap with an unavailability period of the record | — | **block, fixed** | nothing |
| Rest between shifts | `start of the first allocation of the next operational day with allocations − end of the last allocation of the previous operational day < minimum` | **11h** — CLT art. 66 | **warn** | value ≥ 0, mode |
| Daily cap | `Σ hours(allocations of the operational day) > cap` | **10h** — CLT art. 58 (8h) + art. 59 (2h; § 2º "limite máximo de dez horas diárias") | **warn** (art. 61) | value, mode |
| Weekly cap | `Σ hours(accounting week) > cap` | **44h** — CF art. 7º XIII | **warn** | value, mode |
| Contracted workload (fixed schedule only) | `Σ hours(allocations that count) − contracted workload > tolerance` | tolerance **0h**; direction **excess** | **warn** | tolerance, direction, mode |
| Function mismatch (2026-09-14) | `function(demand) ∉ functions(record)` | — (product rule) | **warn** — the acknowledgement saves the allocation flagged as a **function exception** | mode (`block`) |
| Over-coverage (2026-09-26) | `allocated(demand) > N` | — (product rule) | **warn** — the acknowledgement saves the surplus allocation | mode (`block`) |

Operational day, accounting week and `hours(a)` are defined in
[ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md). Every policy
receives the record's **neighbouring allocations** (previous/next schedule) so that rest and the
accounting week cross the period boundary.

### (b) Value defaults come from verified primary sources; none is a floor

Each default is the legal value; the parameter is free (the rest minimum is `≥ 0` — whether a
CCT may reduce the 11h is not settled by any primary source consulted, so no floor is imposed).
The contracted workload is never validated against 44h as a floor: part-time contracts exist
(CLT art. 58-A). Direction of the workload policy defaults to **excess** (a product decision —
no legal source fixes it), with **both** configurable.

### (c) Mode defaults: `block` only for physical impossibility

`block` for overlap (one person in two places) and for unavailability (the record "cannot be
scheduled", and the sponsor confirmed the fixed block). `warn` everywhere the law itself admits
exceptions: art. 61 (above 10h under imperious necessity), compensation regimes (art. 59), and
the remuneratory — not nullifying — consequence of breaching art. 66 (OJ 355 SBDI-1 / Súmula 110
of the TST). This matches "o editor corrige ou aceita conscientemente".

### (d) "Counts toward workload" lives on the allocation, declared, default "counts"

The classification exists on **every** allocation regardless of profile; it is **declared by the
editor** (not derived); its default is **counts**; the editor marks "does not count" for the
extra period (kickoff #11). Only the workload policy reads it — an on-demand record has no
contracted workload, so for it the flag has no validation effect. It carries no money.

### (f) Function mismatch: warn by default, acknowledged exception flag on the allocation, record untouched, block configurable

Sponsor, verbatim (2026-09-14): *"Nao permite alocar no primeiro momento, mas aparece "pop-up"
(custom) que nao possui o cargo daquela conta registrado apra aquele horario, e pergunta se
deseja adicionar mesmo assim. (nao muda a escala padrao, fica com uma excessao, como um extra na
escala)"*.

Assigning a record to a demand for a function it does not hold is **not a structural refusal**:
it is a seventh policy, `function_mismatch`. The allocation is not saved at once; the editor
sees the warning ("does not hold function X for this slot — add anyway?"); the conscious
acknowledgement saves the allocation **flagged as a function exception** — visible on the
schedule, "like an extra". The **employee record is untouched** (its function set in staff stays
as it is). Default mode **warn**; a restaurant may configure **block** (same protocol as the
other policies). The flag is an attribute of the allocation, sibling of "counts toward workload"
(d). The **auto-fill (Step 5) never creates an exception** — it keeps matching by function only
(ADR 3.1.0006); an exception is always a manual act. Whether the exception is re-evaluated when
the record later gains or loses the function is a Stage 4.2 concept gap.

### (g) Over-coverage: `N` is a target, not a cap — warn and acknowledge

Sponsor, verbatim (2026-09-26): *"Permite com aviso"*.

Allocating beyond the demand (`allocated(demand) > N`) is **allowed**: `N` is a **target**, not
a cap. The editor sees the warning ("demand for N already covered") and the conscious
acknowledgement (ADR 4.1.0001 §1) saves the allocation. Coverage **above** 100% is therefore a
legitimate, visible state of the live schedule — symmetric with coverage below 100%, which the
overview already treats as normal ("vagas descobertas"). Default mode **warn**; a restaurant
may configure **block**, and then covering a surplus shift requires raising `N` first. No legal
source: coverage is a product concept, not a CLT one. The **auto-fill (Step 5) does not
over-cover** — it fills up to `N`; surplus is always a manual act. Whether the count is per
demand or per `(day, band, function)` once Stage 4.1 settles demand cardinality, and whether
lowering `N` reopens the violation on allocations already acknowledged, are Stage 4.2 concept
gaps.

This closes the gap the draft had left to the Stage 4.1 concept ("alocar mais do que N é
recusado, avisado ou livre?"): it is a policy, and the answer is *avisado*.

### (e) The subject of every policy is the employee record per unit

Anchored in "Unidades não compartilham funcionários (não se enxergam)" (`overview.md` 37) and
the single-unit pilot (ASSUM-4). **Declared v1 limit:** the same person copied to two units has
hours and rest evaluated **per record**, not summed across units, although the legal limits are
per employee. Evaluating the **person** across units is an evolution conditioned on the
`user_id` link (Stage 3.5) — recorded, not decided.

### Deferred as evolution (with the source already verified)

Weekly rest 24h in every 7 days (CLT 67; non-negotiable floor, 611-B IX); Sunday off at least
once every three weeks (Lei 10.101 art. 6º p.u. — whether a restaurant is "comércio em geral" is
not verified in a primary source); intra-shift break (CLT 71; 30-minute CCT floor, 611-A III —
now feasible because the break is declared); 12x36 (CLT 59-A — requires a regime attribute
staff does not have); compensation/hours bank (CLT 59 §§ 2º/5º/6º — out of v1 by the overview);
intermittent call-up notice (CLT 452-A — the product does not know who is intermittent). Each
enters as a new strategy in the same protocol, still configurable per `overview.md` §6.

## Alternatives considered

- **A — Table + weekly rest 24h as a fifth configurable policy (warn).** Makes "seven days
  without a day off" — the most common restaurant violation — visible in v1 for one class plus
  the 7-day window rest-between-shifts already needs; grows Stage 4.2's ratified scope.
  *Rejected:* the sponsor confirmed the table as is; the protocol makes this the first cheap
  evolution.
- **B — Table + weekly rest + intra-shift break.** Two more classes; couples to the declared
  break. *Rejected:* same as A, larger.
- **C — Edit values/modes** (rest as `block`; daily cap 8h with warn between 8h and 10h and
  block above; workload "both"). `block` on a rule the law itself allows to be breached
  (art. 61) forces the manager to lie to the system; two thresholds double the configuration
  surface. *Rejected:* the sponsor kept the proposed defaults.
- **D — Derive "counts toward workload" from the excess over the contract.** The editor loses
  the ability to say "this shift is extra even though the week is under contract" (a swap, a
  covered absence); welds the flag to one policy's arithmetic. *Rejected:* kickoff #11 models a
  classification the manager makes; the sponsor confirmed the declared flag, default "counts".
- **E — Evaluate policies per person across units.** Requires the `user_id` link (3.5, still
  draft) and an evaluator that merges records across units that "do not see each other"; the
  pilot has one unit. *Rejected for v1:* anchored in the overview and ASSUM-4; kept as
  evolution with the limit declared in the domain doc.
- **F (function mismatch) — Structural refusal** (the draft's rule and the triage's derivation
  I-4): assigning to a function the record does not hold is an error; the fix is in the staff
  record. Simplest; but it blocks emergency cover ("quebra-galho") and forces the manager to
  edit the employee's functions — a contractual fact — to cover one shift. *Rejected:* **the
  sponsor rejected it** on 2026-09-14; the exception must be visible on the schedule and must
  not change the record.
- **G (function mismatch) — Silently allow.** No warning, no flag. *Rejected:* the schedule
  would stop reflecting who is qualified for what; the hub and the auto-fill lose the signal.
- **H (function mismatch) — Auto-add the function to the record on acknowledgement.**
  *Rejected:* the sponsor's "nao muda a escala padrao" — the record must stay as it is; one
  cover shift is not a change of role.
- **I (over-coverage) — Refuse the surplus (`N` as a hard cap).** *Rejected by the sponsor* on
  2026-09-26: covering a shift with one extra person is a normal restaurant act; forcing the
  manager to raise `N` first turns the demand into paperwork.
- **J (over-coverage) — Allow silently.** *Rejected:* the surplus would be invisible, and
  coverage — the metric the hub reports (`overview.md` 46) — would silently exceed the plan
  with no acknowledgement in the audit trail.
- **K (over-coverage) — Auto-raise `N` on acknowledgement.** *Rejected:* it would rewrite the
  plan to match the exception, losing the record of what was actually demanded (the same
  reasoning as H for function mismatch).
- **Do nothing / status quo.** Not applicable: Stage 4.2 cannot start without the set, the
  defaults and the modes; leaving them open would push five forks into one concept.

## Consequences

### Positive
- Stage 4.2 has an exact scope (eight strategies + evaluator + per-tenant config) with every
  number traceable to a verified primary source and every mode justified.
- Emergency cover is expressible without corrupting the employee record, and it is visible
  (the exception flag) rather than hidden in an edited function set.
- No labour rule is hard-coded; the CCT of any restaurant is one parameter edit.
- The pluggable protocol makes every deferred policy a one-class addition.

### Negative
- The pilot discovers "seven days in a row" only in the hub (Step 8), not as a live warning.
- The per-record subject can under-count a person who works in two units — declared, accepted
  for the single-unit pilot.
- Rest between shifts is evaluated between operational days only; a split shift inside one
  operational day (08–12 + 22–02) raises no warning in v1 — declared limit (see ADR 4.1.0002).

### Neutral / trade-offs accepted
- Whether unavailability is evaluated inside the evaluator with a fixed mode or checked in the
  use case is a 4.2 concept gap.
- The function-mismatch policy needs the record's function set on every evaluation — one more
  read through `StaffReadPort` (already needed for eligibility).
- Allocations flagged as exceptions are a hub quantity the Step 8 concept may name; the flag's
  behaviour when the record's function set changes later is a 4.2 concept gap.
- The "does not count" allocations of fixed-schedule records are a hub quantity distinct from
  "uso de extras" (on-demand allocations); its name and computation are a Step 8 gap.
- `workforce.md` §3.3(b), which described the classification as "atuação de quem é sob demanda",
  receives a dated reconciliation note in this PR.

## Implementation notes

- Lands in Stage 4.2 (`policy_protocol`, `overlap_policy`, `rest_between_shifts_policy`,
  `max_hours_policy`, `workload_policy`, `function_mismatch_policy`, `evaluator`,
  `validation_config`) and 4.4 (per-tenant persistence). Both flags ("counts toward workload",
  "function exception") land on `Assignment` in 4.1. Theory:
  [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.4, §3.6.

## References

- Related ADRs: [ADR 3.1.0001](./3_1_0001-workforce-gate-modeling-decisions.md) (half-open
  overlap; `workload_policy` ≠ `max_hours_policy`); [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md)
  (matching by any held function; non-empty function set); [ADR 3.1.0004](./3_1_0004-shift-preference-scope-and-cardinality.md)
  ("hard blocking is unavailability's job"); [ADR 3.2.0003](./3_2_0003-copy-employee-full-duplication.md)
  (copy carries unavailabilities); [ADR 4.1.0002](./4_1_0002-weekly-period-operational-day-and-allocation-hours.md)
  (operational day, `hours(a)`).
- [`overview.md`](../overview.md) — §3 lines 37, 39, 43, 46, 57; §3 ASSUM-4 (70); §6 line 111;
  §7 line 115.
- [`roadmap.md`](../roadmap.md) — Stage 4.2 (1373–1393); Step 5 (1548).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §1, §2, §3.1, §3.3, §3.4, §3.6.
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.4,
  §3.6, §6.
- `src/restaurant_hub/features/staff/domain/value_objects/workload_profile.py` lines 35–39;
  kickoff decision #11 (project memory).
- Sponsor decisions F4 (2026-09-13) and F9 (2026-09-14) — session record `gate-decisions.md`.
- External (primary; verified on the Planalto consolidated text by direct download on
  2026-09-13; TST texts confirmed in an official-backend acórdão):
  - BRASIL. **Constituição da República Federativa do Brasil de 1988**, art. 7º, XIII —
    "duração do trabalho normal não superior a oito horas diárias e quarenta e quatro semanais,
    facultada a compensação de horários e a redução da jornada, mediante acordo ou convenção
    coletiva de trabalho". Disponível em:
    https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm. Acesso em: 13 set. 2026.
  - BRASIL. **Decreto-Lei nº 5.452, de 1º de maio de 1943** (CLT), arts. 58 *caput*; 58-A;
    59 *caput* e § 2º ("limite máximo de dez horas diárias"); 59-A; 61 § 2º; 66 ("Entre 2 (duas)
    jornadas de trabalho haverá um período mínimo de 11 (onze) horas consecutivas para
    descanso."); 67; 71; 452-A; 611-A, I–III; 611-B, IX e parágrafo único — redações vigentes
    conforme o consolidado. Disponível em:
    https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em: 13 set. 2026.
  - BRASIL. **Lei nº 605, de 5 de janeiro de 1949**, art. 1º. Disponível em:
    https://www.planalto.gov.br/ccivil_03/leis/l0605.htm. Acesso em: 13 set. 2026.
  - BRASIL. **Lei nº 10.101, de 19 de dezembro de 2000**, art. 6º, *caput* e parágrafo único
    (Lei nº 11.603/2007). Disponível em: https://www.planalto.gov.br/ccivil_03/leis/l10101.htm.
    Acesso em: 13 set. 2026.
  - BRASIL. Tribunal Superior do Trabalho. **OJ nº 355 da SBDI-1** and **Súmula nº 110**,
    transcribed in acórdão TST-RR-1009-03.2014.5.12.0016 (3ª Turma, 17/08/2016). Disponível em:
    https://jurisprudencia-backend2.tst.jus.br/rest/documentos/714434b5f87efd0dcf3f5eb4171a6706.
    Acesso em: 13 set. 2026.
  - BRASIL. Tribunal Superior do Trabalho. **Súmula nº 444** (pre-reform; more restrictive than
    art. 59-A), transcribed in acórdão TST-RR-29800-32.2009.5.17.0011. Disponível em:
    https://jurisprudencia-backend2.tst.jus.br/rest/documentos/6f4e26b667217defc1c7671a8f88e5da.
    Acesso em: 13 set. 2026.

---
title: ADR 4.1.0005 — The unit's timezone is an attribute of Unit in identity (IANA key, default America/Sao_Paulo), read by scheduling — and later timeclock and hub — through a port
description: Architecture Decision Record
when-use: Reference before adding or reading a timezone anywhere in the system, before converting a wall-clock schedule time to an absolute instant, before adding a cross-BC read port from scheduling to identity, or when deciding which Stage adds the Unit.timezone column
keywords: [adr, scheduling, identity, unit, timezone, iana, zoneinfo, wall-clock, port, cross-bc, dst, configuration, domain-gate]
status: accepted
created_at: 2026-09-13
updated_at: 2026-09-26
adr_id: 4.1.0005
decision: The unit's timezone is owned by identity as Unit.timezone — an IANA time-zone key validated by the standard library, default America/Sao_Paulo — and scheduling (later timeclock and hub) reads it through a port; which Stage adds the column is a roadmap scope gap (candidates 4.4 or a standalone identity issue), recorded here and not decided.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0005 — Unit timezone owned by identity

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Taken at the **domain gate of Step 4** (2026-09-13) for
[`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md), fork
F6 of the gate triage (the draft's HALT H2). Decided by the **human sponsor** (Marcelo,
2026-09-13).

Forces:

- `overview.md` §6 › "Fuso horário configurável por unidade" fixes **"Fuso horário configurável por unidade"** as a technical
  constraint of the whole product.
- [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md) stores staff
  unavailability as naive wall-clock datetimes and states that *"The unit's timezone lives in
  configuration outside staff"*, delegating wall-clock → instant conversion to *"scheduling
  validations in Step 4"* (ADR 3.1.0005 › "configuration outside staff", "performed by the consumer that knows the unit's timezone"). It also records, **without a source**,
  that the pilot timezone has no DST (ADR 3.1.0005 › "currently has no DST").
- **Nothing in the merged code holds a timezone.** `Unit` (identity) has only `id`,
  `restaurant_id` and `name` (`unit.py` › `Unit`); no settings, no config table. Step 4 needs the
  timezone to turn "16h" into an instant when the timeclock (Step 7) compares planned × actual,
  when an e-mail is sent, or when the hub aggregates units. A ratified rule had no owner.
- The external-sources pass verified: an IANA key is the standard representation (PEP 615;
  `zoneinfo` — "`key` must be in the form of a relative, normalized POSIX path"); Brazil ended
  daylight-saving time by Decreto 9.772/2019 (art. 1º — "Fica encerrada a hora de verão no
  território nacional"); ambiguous/missing local times only arise under DST (PEP 495 `fold`).
- The sponsor authorised touching identity from other Steps: *"não há problema em tocar o módulo
  de acesso — isso irá acontecer ao longo do desenvolvimento quando forem surgindo mais
  features"* ([ADR 3.4.0006](./3_4_0006-staff-rbac-two-permissions-and-hr-parity.md) §5).

## Decision

Sponsor: *"Unit em identity + port (Recomendada)"*.

1. **`Unit.timezone` belongs to identity**, the owner of the unit resource. It is an **IANA
   time-zone key** (`Area/Location`, e.g. `America/Sao_Paulo`), validated by the standard library
   (`zoneinfo`), with **default `America/Sao_Paulo`**. It is unit configuration, not scheduling
   domain data.
2. **Scheduling reads it through a port** (its own port, with the adapter **outside scheduling**
   — the pattern of [ADR 3.4.0001](./3_4_0001-staff-owned-access-guard-port.md); where the
   adapter lives is a decision of the 4.4 `technical.md`, see issue #47); timeclock (Step
   7) and hub (Step 8) read it from the same owner the same way. No BC other than identity
   stores it.
3. **Wall-clock stays wall-clock.** Time ranges and allocations are local times of the unit
   (domain doc §3.9); conversion to an absolute instant happens only when a consumer needs one,
   using the unit's timezone read from identity — never inside the scheduling domain.
4. **Which Stage adds the column is a roadmap scope gap — recorded, not decided.** Candidates:
   **Stage 4.4** (the first Step 4 Stage with a migration) or a **standalone identity issue**
   landing before 4.3 (which needs the port). The coordinating session annotates the roadmap at
   gate closure.
5. **DST edge cases are evolution.** Brazil has no DST (Decreto 9.772/2019), which also supplies
   the source ADR 3.1.0005 lacked; ambiguous/missing local times (PEP 495 `fold`) become
   relevant only for units outside Brazil or if DST returns — the IANA key absorbs that without
   a schema change.

## Alternatives considered

### Alternative A — Timezone in scheduling's per-unit configuration (`ScheduleConfig`)
- **Description:** only scheduling knows the timezone; timeclock and hub read it from scheduling.
- **Pros:** no change to identity.
- **Cons:** a unit attribute stored in the wrong bounded context; Steps 7 and 8 would depend on
  scheduling for a datum that is not about schedules; moving it later means a column move plus
  rewriting every consumer.
- **Why rejected:** the timezone is a fact about the unit; identity owns the unit.

### Alternative B — One global deployment setting
- **Description:** a single `TIMEZONE` setting for the whole installation.
- **Pros:** one line; enough for a single-unit pilot.
- **Cons:** contradicts "fuso horário configurável por unidade" (`overview.md` §6 › "Fuso horário configurável por unidade") and ASSUM-4
  ("multi-unidade modelado desde já"); the second unit in another timezone forces a rewrite.
- **Why rejected:** violates a ratified constraint to save one column.

### Alternative C — Store schedule times as UTC instants and drop the wall-clock model
- **Description:** convert at write time using the unit's timezone; no naive datetimes.
- **Pros:** industry default for absolute events.
- **Cons:** "16h–00h" is a local fact (`overview.md` §9 › "Turno: faixa de horário demandada/trabalhada num dia"); crossing allocation × unavailability
  would require converting staff's naive datetimes on every comparison; contradicts
  ADR 3.1.0005's rationale; DST (if ever) would silently shift stored shifts.
- **Why rejected:** the wall-clock model is ratified for staff and is what the glossary uses;
  this ADR only gives the conversion its missing input.

### Alternative D — Decide the Stage for the column here
- **Why rejected:** roadmap scope is the coordinating session's to annotate; a domain-gate ADR
  records the ownership decision, not the delivery slot.

### Do nothing / status quo
Not acceptable: the Step 4 conversion that ADR 3.1.0005 delegates has nowhere to read the
timezone from; every consumer would invent its own.

## Consequences

### Positive
- Every BC that needs the timezone reads it from the owner; one column, one port pattern.
- The pilot needs no configuration (default `America/Sao_Paulo`); a second unit in Manaus is one
  field on the unit screen (`America/Manaus`), and the same 16h shift becomes a different instant
  for the timeclock without code.
- ADR 3.1.0005's unsourced "no DST" premise now has a primary source (Decreto 9.772/2019).

### Negative
- Identity's schema is extended by a scheduling need (authorised, but the identity domain doc —
  issue #30 backfill — should mention the attribute when written).
- A cross-BC read port scheduling → identity is added (the second, after the e-mail address
  via `user_id`); the composition root grows one translator.

### Neutral / trade-offs accepted
- The port's shape (timezone via `AuthorizedScope` vs a dedicated `UnitReadPort`) is a 4.3/4.4
  concept decision.
- Validation of the key (a `ValueError` from `zoneinfo` for a non-conforming key) is a boundary
  concern of the identity Stage that adds the column.

## Implementation notes

- Column + migration in identity (Stage to be named in the roadmap); field on the unit DTO;
  a read port in scheduling (4.3) with its adapter outside scheduling (4.4 `technical.md` names
  the place — composition root today, `adapters/out/` if issue #47 moves it). Theory:
  [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.9, §3.10.2.

## References

- Related ADRs: [ADR 3.1.0005](./3_1_0005-naive-wall-clock-unavailability-datetimes.md)
  (wall-clock in the unit's timezone; timezone outside staff; conversion by the consumer);
  [ADR 3.4.0001](./3_4_0001-staff-owned-access-guard-port.md) (BC-owned port with translator in
  the composition root); [ADR 3.4.0006](./3_4_0006-staff-rbac-two-permissions-and-hr-parity.md)
  §5 (touching identity authorised); [ADR 3.2.0003](./3_2_0003-copy-employee-full-duplication.md) › "The copied instants keep their wall-clock reading"
  (copy between units of different timezones keeps wall-clock).
- [`overview.md`](../overview.md) — §6 › "Fuso horário configurável por unidade"; §3 › "ASSUM-4";
  §9 › "Turno: faixa de horário demandada/trabalhada num dia" (16h–00h as local time).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.9,
  §3.10.2, §6.
- `src/restaurant_hub/features/identity/domain/entities/unit.py` › `Unit` (no timezone
  today).
- Sponsor decision F6 on 2026-09-13 (session record `gate-decisions.md`).
- External (primary; verified 2026-09-13):
  - IANA — INTERNET ASSIGNED NUMBERS AUTHORITY. **Time Zone Database** (tz / zoneinfo), tzdata
    2026d (2026-09-11). Disponível em: https://www.iana.org/time-zones. Acesso em: 13 set. 2026.
  - GANSSLE, Paul. **PEP 615 – Support for the IANA Time Zone Database in the Standard
    Library**. Python Enhancement Proposals, 2020 (Final; Python 3.9). Disponível em:
    https://peps.python.org/pep-0615/. Acesso em: 13 set. 2026.
  - PYTHON SOFTWARE FOUNDATION. **zoneinfo — IANA time zone support** ("`key` must be in the
    form of a relative, normalized POSIX path, with no up-level references. The constructor will
    raise `ValueError` if a non-conforming key is passed."). Disponível em:
    https://docs.python.org/3/library/zoneinfo.html. Acesso em: 13 set. 2026.
  - BELOPOLSKY, Alexander; PETERS, Tim. **PEP 495 – Local Time Disambiguation** (`fold`;
    ambiguous and missing local times). Python Enhancement Proposals, 2015 (Final; Python 3.6).
    Disponível em: https://peps.python.org/pep-0495/. Acesso em: 13 set. 2026.
  - BRASIL. **Decreto nº 9.772, de 25 de abril de 2019**, art. 1º — "Fica encerrada a hora de
    verão no território nacional." Disponível em:
    https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/decreto/D9772.htm. Acesso em:
    13 set. 2026.

---
title: ADR 4.4.0005 — ScheduleRepository.save receives the versions of the adjacent schedules the evaluation read and refuses with ScheduleVersionConflictError when either slot changed, closing the boundary write skew before the pilot
description: Architecture Decision Record
when-use: Reference before adding a writer that calls ScheduleRepository.save, before changing how the publish use case reads the neighbours, before mapping ScheduleVersionConflictError to HTTP (Stage 4.5), or before the Step 5 auto-fill apply writes allocations
keywords: [adr, scheduling, concurrency, write-skew, optimistic-locking, version, neighbours, advisory-lock, port-law, publish]
status: accepted
created_at: 2026-11-22
updated_at: 2026-11-22
adr_id: 4.4.0005
decision: 'The boundary write skew is closed now (issue #199): ScheduleRepository.save takes a required ExpectedNeighbours (the previous and the following adjacent schedule as the evaluation read them, each a schedule id and version or None for an empty slot) and, after the address and version checks and inside the unit lock of ADR 4.4.0003, refuses with ScheduleVersionConflictError carrying changed_neighbour_id when a slot holds another schedule, another version, became empty or became occupied; the publish use case passes the neighbours run_batch read; the trail keeps one row per accepted write and none per refusal.'
context_stage: 4.4-scheduling-persistence
bounded_context: scheduling
---

# ADR 4.4.0005 — `save` checks the neighbour versions the evaluation read

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-22 (issue #199). The choice to close the window now was a product fork
(class P) that the sponsor delegated to the implementing session; it took the recommended
option and records the reason below.

## Context

The evaluation of a publish reads the schedule being edited **and** its two adjacent
schedules (ADR 4.2.0002 §1): rest between shifts and overlap cross the period boundary, so a
violation can exist only when two weeks are read together. The optimistic version
(ADR 4.1.0001 §2) protects only the edited schedule. Two managers publishing adjacent weeks
of the same unit at the same time can therefore each be evaluated against the **old** state
of the other week and both commit, leaving on the live schedule a boundary violation that no
evaluation saw (concept 4.3 §3, "Limite declarado"; concept 4.4 §7 D-SKEW).

The unit lock of ADR 4.4.0003 serialises the **writes**, but the evaluation happens in the use
case, before the write transaction, so the lock alone does not close the window.

Facts that weighed on the decision:

- **The window can break a canonical invariant, not only a warning.** The domain doc states
  that the live schedule never contains a `block` violation (`docs/domain/scheduling/shift-scheduling.md`
  §3.5, "Regra canônica — concorrência", Invariantes). Overlap is `block` by default and applies
  across the boundary (§3.6.1), so two concurrent publishes could commit a `block` overlap at
  the turn of the week. A warning-level rest violation would also be live without the
  acknowledgement the domain doc requires.
- **No production data exists to measure.** The issue asked to measure how many concurrent
  publishes in adjacent weeks happen. The pilot has not started; there is no traffic to count.
  The decision is taken without that measurement and says so, instead of inventing a number.
- **Changing the port is cheap now and expensive later.** Only the publish use case calls
  `save` today. Stage 4.5 (HTTP) has not mapped `ScheduleVersionConflictError` yet, and the
  Step 5 apply (`apply_autofill`, Stage 5.2, which consumes `ScheduleRepository` and writes many
  allocations at once) will be a second caller of `save`. Stage 4.8 writes the configuration
  port, not `save`. A new required parameter now touches one caller and no published error
  body; later it would touch the 5.2 apply and the 4.5 mapping.
- **The extension is small.** The neighbour notion, the version, the refusal error and the
  unit lock already exist. The law is an extension of L-SC4 (optimistic save) to the two
  schedules the evaluation consumed; no migration is needed.

## Decision

1. **Close the window before the pilot.** `ScheduleRepository.save(schedule, expected_version,
   expected_neighbours, change)` gains a **required** `ExpectedNeighbours`: `previous` and
   `following`, each a `NeighbourVersion(schedule_id, version)` or `None` for an empty slot.
   Required, not optional: a writer that did not declare what it read would reopen the skew
   with nothing refusing it.
2. **The slots.** `previous` is the schedule of the same (tenant, unit) whose last day is the
   day before the period; `following` is the one whose first day is the day after. This is the
   rule of `neighbours_of` in the application (ADR 4.2.0002 §1), repeated in the fake and in the
   adapter. A schedule two weeks away, or adjacent in another unit or tenant, is not a slot.
3. **The law (L-SC9).** Any difference refuses: another schedule in the slot, another
   version, a slot read occupied that became empty, **and a slot read empty that became
   occupied**. The last case is required: without it, creating the adjacent week and
   publishing it concurrently reopens the same skew. The refusal is
   `ScheduleVersionConflictError` with `changed_neighbour_id` naming the schedule now in the
   slot (or the expected one if the slot emptied); its two versions are the edited
   schedule's, equal because the edited schedule did not change. The previous slot is checked
   before the following. The edited schedule being unchanged, the editor's batch is still
   valid: re-sending it on the same version re-evaluates against the current neighbour. That
   differs from the F8 conflict of ADR 4.1.0001 §2 ("atualizar" discards the screen), and how
   the client offers it is Stage 4.5's to decide with `changed_neighbour_id` in hand.
4. **Order of `save`:** address → version → neighbours → internal ids. Staleness first: a
   collision found against a neighbour that changed is better answered by re-reading. This
   amends the `save` order of ADR 4.4.0003 §Decision 2 (dated note there).
5. **Where.** In the Postgres adapter the check runs inside the transaction, after
   `pg_advisory_xact_lock` on the unit (ADR 4.4.0003 §1): every writer of the unit takes that
   lock, so the slot checked is the slot at commit. The fake applies the same rule. The
   contract suite runs one body against both.
6. **The caller.** `run_batch` returns, in `BatchOutcome.neighbours`, the versions of the
   neighbours that entered the evaluation, and `PublishScheduleUseCase` passes them to `save`.
   `add` is unchanged: creation writes an empty schedule and evaluates nothing.
7. **Trail.** One row per accepted write, none per refusal (L-SC3 unchanged).

### Decision records

```
[decision] P delegado — fechar a janela agora (Recomendada), motivo: a janela pode deixar
uma violação block viva, contra o invariante canônico do doc de domínio; mudar a assinatura
de save hoje toca um chamador e depois tocaria o apply da 5.2 e o mapa de erros da 4.5; não há
dado de produção para medir a frequência (o piloto não começou), e a decisão não depende dele.

[decision:E] D199-1 — vaga vazia na leitura que passou a ter escala conta?
Escolha: conta (recusa) · Alternativas: só vizinha lida que mudou de versão
Base: análise interna — sem ela, criar a semana adjacente e publicá-la concorrentemente
reabre o mesmo skew (a publicação da semana existente leu a vaga vazia e grava sem conferir)
Verificado: teste de contrato (fake e Postgres) e de conduta com duas conexões
Configuração candidata: nenhuma · Reversível: sim

[decision:C] D199-2 — forma do conflito de vizinha
Escolha: o mesmo ScheduleVersionConflictError com changed_neighbour_id (só por palavra-chave,
None = a própria escala mudou) · Alternativas: reusar sem campo (perde qual mudou); classe
nova (a issue pede a recusa com ScheduleVersionConflictError) · Degrau: 1 (issue) e 4 (a 4.5
pode distinguir as duas causas sem refazer a forma)
Configuração candidata: nenhuma · Reversível: sim, até a 4.5 publicar o corpo da recusa

[decision:C] D199-3 — ordem da checagem no save
Escolha: endereço → versão → vizinhas → ids; anterior antes da seguinte · Alternativas:
vizinhas depois dos ids · Degrau: 4 (recusas de "releia" antes da de conteúdo)
Configuração candidata: nenhuma · Reversível: sim
```

The litmus of `docs/PIPELINE.md` §4.5 (issue × Stage) was weighed: the change adds a port
law, which is the signal of a Stage, but it is an extension of an existing law (L-SC4) over
concepts already modelled (neighbour, version, refusal, unit lock), and the issue body already
stated the solution (`save` receives the neighbour versions and refuses with
`ScheduleVersionConflictError`). The body was the concept; it stays an issue, with this ADR.

## Alternatives considered

### Alternative A — Keep it as a declared limit until Step 5
The next evaluation of either week shows the violation live, so it is visible after the
fact. Rejected: it lets a `block` violation be live, against the domain invariant; and the
signature change it postpones grows with every consumer (4.5, 4.8, Step 5 apply). No usage
data exists to argue that the window is rare enough to accept.

### Alternative B — Run the whole use case in one `SERIALIZABLE` transaction
Reads and write in one serialisable transaction would make PostgreSQL detect the dependency.
Rejected: scheduling has no unit of work (ADR 2.6.0002 keeps it per BC and only identity has
one); the reads also cross into staff through the facade; serialisation failures need a retry
loop in the use case; and the fake could not reproduce the behaviour, breaking the
fake ≡ Postgres contract.

### Alternative C — Hold the unit lock for the whole use case
A port that takes the unit lock before the reads would serialise evaluation and write.
Rejected: it adds a lock port to the application, holds a database lock across the staff
reads, and serialises read-heavy evaluations of the unit, while the version comparison
achieves the same guarantee optimistically.

## Consequences

### Positive
- Two publishes in adjacent weeks never both commit when either evaluation was stale; the
  refused one re-evaluates against the current neighbour and sees the boundary violation.
- The live schedule keeps the domain invariant across the week boundary.
- Every future writer through `save` (the Step 5 apply first) must state what it read.

### Negative
- A publish can now be refused because the **neighbour** changed, even when the edited
  schedule did not, including when the change cannot create a boundary violation — the
  common case being another manager **creating** the adjacent week (an empty schedule) while
  this one publishes. Accepted: the rule compares versions, not content, so it stays the same
  in the fake and in the adapter; the refused editor re-sends the same batch.
- Two extra reads per `save`, under the unit lock. The following slot filters `first_day`
  (served by `ix_schedules_tenant_unit_first_day`); the previous slot filters the expression
  `first_day + days`, which the index serves only by its (tenant, unit) prefix — a scan of the
  unit's schedules, about 52 rows per unit-year at pilot volume. Not measured; revisit with an
  expression index if a unit grows far beyond that.

### Neutral / trade-offs accepted
- The HTTP body and status of the neighbour refusal are Stage 4.5's; the error carries what
  it needs (`changed_neighbour_id`).
- Misaligned calendars (a schedule covering the adjacent day without ending there) are not a
  slot, exactly as in the evaluation; both sides use the same rule.
- **Other unversioned inputs of the evaluation stay open.** The evaluation also reads the
  staff facts (unavailability is a fixed `block`) and the validation configuration (written by
  Stage 4.8). Neither is versioned in `save`: a change to them between evaluation and write is
  not refused. This ADR closes only the neighbour window that issue #199 names; those two are
  recorded as findings of the issue, with the reconciliation-on-read stance of ADR 4.1.0006
  for staff and the 4.8 transition rule for the configuration as their current answers.

## Implementation notes

- Port and law text: `features/scheduling/application/ports/out/schedule_repository.py` › L-SC9.
- Adapter: `features/scheduling/adapters/out/postgres/schedule_repository.py` ›
  `neighbour_statements` and `_check_neighbours`.
- Caller: `features/scheduling/application/use_cases/_publish.py` › `BatchOutcome.neighbours`;
  `publish_schedule.py`.
- Tests: `tests/contract/features/scheduling/test_schedule_repository_laws.py` (L-SC9),
  `tests/integration/features/scheduling/adapters/out/postgres/test_schedule_conduct.py`
  (two connections), `tests/unit/features/scheduling/application/test_publish_neighbour_skew.py`.

## References

- ADR 4.1.0001, ADR 4.2.0002, ADR 4.4.0003, ADR 2.6.0002
- `docs/stages/4.3-scheduling-application/concept.md` §3 ("Limite declarado")
- `docs/stages/4.4-scheduling-persistence/concept.md` §7 D-SKEW
- `docs/domain/scheduling/shift-scheduling.md` §3.5 (concorrência, invariantes), §3.6.1
- Issue #199

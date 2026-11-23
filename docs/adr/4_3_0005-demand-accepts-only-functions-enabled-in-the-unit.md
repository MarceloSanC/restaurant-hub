---
title: ADR 4.3.0005 — A unit's demand accepts only job functions enabled in that unit, refused when the batch introduces it, read through a fifth unit-addressed StaffReadPort read
description: Architecture Decision Record
when-use: Reference before changing how a batch declares a demand or changes its quantity, before adding a read to StaffReadPort or StaffReadFacade, before mapping JobFunctionNotEnabledInUnitError to HTTP (Stage 4.5), before the Step 5 auto-fill reads demands, or before letting staff refuse a narrowing because of the schedule
keywords: [adr, scheduling, demand, job-function, unit, enablement, staff-read-port, facade, publish, d1]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: 4.3.0005
decision: 'A demand of a unit accepts only job functions enabled in that unit (issue #209): in the publish batch, DeclareDemand of a function that is in the tenant catalogue but not enabled in the schedule''s unit, and ChangeDemandQuantity that raises N of such a demand, raise JobFunctionNotEnabledInUnitError (root SchedulingError) after the catalogue check; a demand stored before staff narrowed the function stays, does not block an edit that does not introduce it (lowering, zeroing, withdrawing and moving its band pass) and staff never refuses a narrowing because of it; scheduling reads the enablement through a fifth StaffReadPort read, list_unit_job_functions(tenant, unit) (law L-ST6), served by StaffReadFacade.list_unit_functions over JobFunctionRepository.list_by_unit; allocation is unchanged.'
context_stage: 4.3-scheduling-application
bounded_context: scheduling
---

# ADR 4.3.0005 — A unit's demand accepts only functions enabled in the unit

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — 2026-11-23 (issue #209). Whether to restrict was a product fork (class P) that the
sponsor delegated to the implementing session; it took the recommended option and records the
reason below.

**Partially supersedes ADR 4.3.0003** (stays `accepted`, dated note in its `## Supersessão
parcial`): §Decision 1 › "Four reads, addressed by unit" becomes five. **Partially supersedes
ADR 4.4.0004** (same form): §Decision 1 › "using only `list_by_unit` and `list_by_tenant`" now
also covers `JobFunctionRepository.list_by_unit`, and the facade gains a fifth method.

## Context

Since Stage 3.11 a job function belongs to the tenant and is valid in every unit or in a
non-empty set of units (ADR 3.11.0001), and an employee record holds only functions enabled in
its unit (ADR 3.11.0002). Scheduling did not read the enablement: the publish batch checked
only that the demanded function was in the tenant catalogue (`_publish.py` › `_apply_one`,
`JobFunctionNotFoundError`), so a unit could demand a function that is not valid there, and
the allocation could only find records that cannot hold it (concept 3.11 §1, "Fora do escopo";
`shift-scheduling.md` §3.3, dated note of 2026-11-16).

Facts that weighed on the decision:

- **The rule already exists on the staff side.** Staff refuses, with `409`, a record holding a
  function not enabled in its unit (ADR 3.11.0002 §Decision › "a function not enabled in the
  record's unit raises"). A demand for such a function is the same mismatch seen from the
  schedule.
- **D1 bounds the answer.** Staff keeps accepting cadastro edits; a violation that staff
  introduces later is shown live and never blocks an unrelated edit (ADR 4.3.0003 §Decision 4 ›
  "it never blocks an unrelated edit"; `shift-scheduling.md` §6, dated note of 2026-11-01). So
  staff narrowing a function cannot be refused because a demand uses it, and an old demand
  cannot block the next save.
- **The extension points exist.** The batch already has an application pre-check for the
  function (the catalogue). `StaffReadPort` and its adapter over `StaffReadFacade` exist
  (Stage 4.4), and staff already lists the functions enabled in one unit
  (`job_function_repository.py` › `JobFunctionRepository.list_by_unit`, law L-JF6).
- **Stage 4.5 (HTTP) has not started.** Without the rule, the first route that writes a demand
  would publish the hole.

## Decision

1. **Restrict at introduction.** In `apply_operations`, after the catalogue check:
   - `DeclareDemand` of a function not enabled in the schedule's unit raises
     `JobFunctionNotEnabledInUnitError(job_function_id, unit_id)` — also with `N = 0`: the
     refusal is about the function, not the vacancy.
   - `ChangeDemandQuantity` that **raises** `N` of a demand whose function is not enabled raises
     the same error. Raising `N` (including `0 → N`) opens vacancies, the same thing a new
     declaration does, so it counts as introducing (ADR 4.3.0001 refuses or asks only what the
     batch introduces).
   - Lowering or zeroing `N`, withdrawing the demand, keeping `N` and moving or re-breaking its
     band pass: the manager is fixing it, or not touching it.
   The error's root is `SchedulingError`: it is a product rule, not a lookup or malformed input
   (`errors.py` module docstring, ADR 3.9.0001). It carries the function and the unit, both
   named by the request's address.
2. **A demand stored before a narrowing stays (D1).** Nothing is cleaned, staff refuses
   nothing, and an edit that does not introduce it is not blocked. It shows as an uncovered
   demand. A record allocated to it falls in the existing function-mismatch policy (ADR
   4.2.0001), because staff keeps unit records holding only enabled functions.
3. **The read.** `StaffReadPort.list_unit_job_functions(tenant_id, unit_id)` returns the
   tenant's functions enabled in the unit — enabled in every unit or naming this one — and no
   other (law **L-ST6**, contract suite with one body for the fake and the real adapter).
   `LocalStaffReadAdapter` serves it over a new, additive `StaffReadFacade.list_unit_functions`
   on `JobFunctionRepository.list_by_unit`; the facade stays primitive-only and non-authorizing.
   Scheduling reads it only in the edit path (`run_batch`, `load_staff(...,
   with_unit_functions=True)`); a view built without it holds an empty set, so every
   declaration is refused (fail-closed). No foreign key crosses the contexts (ADR 3.3.0002).
4. **Allocation is unchanged.** The allocation targets records of the unit, and those hold only
   enabled functions (ADR 3.11.0002); the function exception stays as it is (ADR 4.1.0003 (f)).

### Decision records

```
[decision] P delegado — restringir na introdução (Recomendada), motivo: fecha o buraco antes
da borda HTTP da 4.5 com uma leitura e uma recusa sobre sítios que já existem (checagem de
catálogo do lote; StaffReadPort e fachada da 4.4), é a mesma regra que staff já impõe ao
registro (ADR 3.11.0002) e respeita a D1 (o que staff muda depois aparece e não bloqueia);
nada a refazer quando a Stage que tocar a demanda chegar.

[decision:C] #209-C1 — como scheduling lê a habilitação
Escolha: quinta leitura do StaffReadPort, endereçada por unidade (list_unit_job_functions,
L-ST6), sobre StaffReadFacade.list_unit_functions → JobFunctionRepository.list_by_unit ·
Alternativas: estender JobFunctionEntry com a habilitação (todas × conjunto) e filtrar em
scheduling · Degrau: 1
Base: ADR 4.3.0003 §Decision 1 "Four reads, addressed by unit (the catalogue by tenant)" ·
workforce.md §3.2 "a listagem de uma unidade mostra só as habilitadas nela" ·
job_function_repository.py › JobFunctionRepository.list_by_unit (L-JF6)
Verificado: sustenta
Configuração candidata: nenhuma · Reversível: sim (o port tem um consumidor e a borda HTTP
não existe)

[decision:C] #209-C2 — recusa estrutural no lote × política de validação
Escolha: pré-checagem da application na aplicação do lote, no sítio da checagem de catálogo ·
Alternativas: 10ª política de validação (block/warn configurável) · Degrau: 1
Base: _publish.py, docstring do módulo, item 2 "pré-checagens da application (... função no
catálogo ...)" · ADR 3.11.0002 §Decision 1/2 (recusa 409) · ADR 4.3.0003 §Decision 4 (D1)
Verificado: sustenta
Configuração candidata: a política (alternativa B abaixo), se um restaurante pedir só aviso ·
Reversível: sim

[decision:C] #209-C3 — raiz do erro novo
Escolha: SchedulingError · Alternativas: SchedulingApplicationError · Degrau: 1
Base: application/errors.py, docstring do módulo (ADR 3.9.0001): regra que o produto enuncia
× falha que não é regra
Verificado: não verificado (§4.2)
Configuração candidata: nenhuma · Reversível: sim, até a 4.5 mapear o status
```

The litmus of `docs/PIPELINE.md` §4.5 (issue × Stage) was weighed: the enablement concept and
the "valid only where enabled" rule are Stage 3.11's; this decision extends an existing read
(port, facade, adapter) and adds one refusal at the site of an existing pre-check, with no new
policy, schema or route. The issue body held the concept; it stays an issue, with this ADR.

## Alternatives considered

### Alternative B — A tenth validation policy (`block`/`warn`, configurable)
Would show a stale demand as a live violation and let a restaurant only warn. Rejected now:
configurable policies carry labour rules
(`overview.md` §6 › "Regras trabalhistas (CLT) não são hard-coded"), not catalogue integrity; it needs a new `PolicyKind`, configuration default,
violation identity and evaluator input — Stage-sized with no product ask. Kept as the candidate
configuration if a restaurant asks for a warning instead of a refusal.

### Alternative C — Do not restrict now; record and implement with the Stage that touches demand
The pilot may never narrow a function in a multi-unit restaurant. Rejected: Stage 4.5 would
expose the hole on its first demand route, and the cost now is one read and one refusal on
sites that exist.

### Alternative D — Restrict and make staff refuse a narrowing while a demand uses the function
Would keep no stale demand. Rejected: contradicts D1 (staff never refuses because of the
schedule) and would need a reverse read from staff into scheduling for a third reason.

### Alternative E — Extend `JobFunctionEntry` with the enablement and filter in scheduling
Rejected (record #209-C1): scheduling would learn staff's enablement model (every unit × a set)
instead of asking the unit-addressed question staff already answers.

## Consequences

### Positive
- No route of Stage 4.5 can write a demand for a function that is not valid in the unit.
- One rule on both sides: staff for the record, scheduling for the demand.

### Negative
- **A stale demand is never covered by the auto-fill.** Staff narrows only when no record of
  the removed unit holds the function (ADR 3.11.0002 §Decision 4), and the auto-fill never
  creates a function exception; with function mismatch in `block`, not even by hand. It weighs
  on coverage and "unfillable vacancies" (Step 5) until the manager lowers or withdraws it.
- **Check-then-act, twice.** Staff's own race (narrowing × assignment, ADR 3.11.0002
  "Declared limit") and a cross-context one: scheduling reads the enablement, staff narrows,
  then the publish saves. `save` versions only the schedule and its neighbours (ADR 4.4.0005,
  "Other unversioned inputs of the evaluation stay open"). Both end in the tolerated state of
  Decision 2.

### Neutral / trade-offs accepted
- One extra staff read per evaluate/publish; reads elsewhere are unchanged.
- The HTTP status and body of the refusal, and how the edge flags a stale demand, are Stage
  4.5's (`shift-scheduling.md` §6 › "Lacunas para o concept de cada Stage").

## Implementation notes

- Rule: `features/scheduling/application/use_cases/_publish.py` › `_require_enabled`,
  `_change_quantity`; read: `_inputs.py` › `load_staff`.
- Error: `features/scheduling/application/errors.py` › `JobFunctionNotEnabledInUnitError`.
- Port and law: `staff_read_port.py` › `StaffReadPort.list_unit_job_functions` (L-ST6);
  adapter `local_staff_read_adapter.py` › `LocalStaffReadAdapter.list_unit_job_functions`;
  facade `features/staff/application/facade.py` › `StaffReadFacade.list_unit_functions`.
- Tests: `tests/unit/features/scheduling/application/test_publish_protocol.py` and
  `test_evaluate_and_publish.py` (`issue_209`),
  `tests/contract/features/scheduling/test_staff_read_port_laws.py` (L-ST6),
  `tests/unit/features/staff/application/test_facade.py`.

## References

- ADR 3.3.0002, ADR 3.9.0001, ADR 3.11.0001, ADR 3.11.0002, ADR 4.1.0003, ADR 4.2.0001,
  ADR 4.3.0001, ADR 4.3.0003, ADR 4.4.0004, ADR 4.4.0005
- `docs/domain/scheduling/shift-scheduling.md` §3.3; `docs/domain/staff/workforce.md` §3.2
- `docs/stages/3.11-job-function-unit-enablement/concept.md` §1, §8
- Issue #209

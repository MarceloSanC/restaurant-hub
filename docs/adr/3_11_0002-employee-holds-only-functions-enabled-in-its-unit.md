---
title: ADR 3.11.0002 — An employee record holds only job functions enabled in its unit, so copying to a unit where a function is not enabled is refused rather than enabling it or copying anyway
description: Architecture Decision Record
when-use: Reference before changing copy_employee_to_unit, before letting an employee hold a function that is not enabled in its unit, or before narrowing a function's enablement without checking who holds it
keywords: [adr, copy, employee, job-function, unit, enablement, invariant, staff]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-09
adr_id: 3.11.0002
decision: Every write that sets an employee's functions or a function's units keeps the rule that an employee holds only functions enabled in its unit; create and assign refuse a function not enabled in the record's unit, copy refuses a destination where any copied function is not enabled (JobFunctionNotEnabledInUnitError, 409) without enabling it or changing the copy's exclusion list, and narrowing a function's units refuses while a record in a removed unit holds it (JobFunctionInUseError, 409)
context_stage: 3.11-job-function-unit-enablement
bounded_context: staff
---

# ADR 3.11.0002 — An employee holds only functions enabled in its unit

## Status

`accepted`

> Decided under delegation (issue #41: "É o principal fork deste trabalho"). The
> sponsor delegated the product forks to the recommended option.

## Context

The copy of an employee between units (ADR 3.2.0003, `workforce.md` §3.7) duplicates
the whole record, function set included, and is coherent today **because** a function
is valid in every unit. ADR 3.11.0001 makes the function valid only where it is
enabled. Issue #41 names three answers for a copy whose functions are not enabled in
the destination: refuse, enable them together, or copy anyway.

The question is wider than the copy. Creating a record, replacing its functions and
narrowing a function's units are the other three writes that can put a record in a
unit where one of its functions is not enabled. The answer for the copy has to be the
answer for all four, or the rule is decorative.

## Decision

**The invariant:** an employee record holds only functions enabled in its unit
(enablement *every unit* covers every unit). It is a cross-aggregate rule, so it lives
in the use cases with the port queries that support it (ADR 3.2.0001), at four points:

1. **Create employee** and 2. **assign job functions** — after the existing referential
   check, a function not enabled in the record's unit raises
   `JobFunctionNotEnabledInUnitError` (`409`).
3. **Copy to unit — refuse.** If any function of the source is not enabled in the
   destination, the copy raises `JobFunctionNotEnabledInUnitError` (`409`) and writes
   nothing. Order: both units authorized → source exists → destination differs
   from source → the source's functions resolved through `JobFunctionRepository`
   (a function deleted meanwhile ⇒ `JobFunctionNotFoundError`, as in assign) →
   enablement in the destination → write. The copy therefore **consumes
   `JobFunctionRepository`**, superseding on this point ADR 3.2.0003 › "The copy does
   not consume `JobFunctionRepository`" (dated note there): the reason it gave — the
   functions are tenant-scoped, so the same ids are valid in the target unit — no
   longer holds. The copy still duplicates the record whole; its closed exclusion list (ADR
   3.2.0003) is unchanged. `P delegado — recusar, motivo: mantém a cópia sem efeito
   colateral no catálogo e sem permissão nova (quem copia tem manage_staff, não
   manage_job_functions), e mantém a invariante; o gerente habilita a função no destino
   e repete a cópia.`
4. **Narrowing a function's units** (ADR 3.11.0001 §5) — if any record of a
   unit the new enablement no longer covers holds the function, the change raises
   `JobFunctionInUseError` (`409`), the same error the guarded delete uses for the same
   reason. Terminated records count: the record survives termination and still points
   at the function (ADR 3.2.0006). The supporting query is the new
   `EmployeeRepository` law `L-E8` (`units_referencing_job_function`).

**Declared limit:** the four checks are check-then-act. Unlike the delete guard, no
foreign key closes the race — the enablement is "a flag or a row", which a
constraint cannot express against `employee_job_functions`. A concurrent narrowing and
assignment can leave one record holding a function not enabled in its unit. The
consequence is a function visible on the record and absent from the unit listing; no
access is granted by it.

## Alternatives considered

### Alternative A — enable the missing functions in the destination together with the copy
- **Pros:** one click for the manager.
- **Cons:** the copy (permission `manage_staff`) would change the catalogue (permission
  `manage_job_functions`) as a side effect — a privilege the copier may not hold — and
  writes two aggregates in one use case without a unit of work (regra 10 of
  `check_layout`).

### Alternative B — copy anyway
- **Pros:** the copy stays exactly as in ADR 3.2.0003.
- **Cons:** creates the state the invariant forbids, and a record whose function is not
  in the unit listing cannot be edited back to the same set (assign would refuse it).

### Alternative C — drop the non-enabled functions from the copy
- **Pros:** never fails.
- **Cons:** adds an exclusion to a list ADR 3.2.0003 closed, silently; and a record left
  with no function violates ADR 3.1.0006 ("ao menos uma função").

## Consequences

### Positive
- One rule, four enforcement points, one error for the employee writes.
- The copy keeps its permission and its "duplicates, does not share" semantics.

### Negative
- A copy can now fail for a reason outside the source record; the `409` body names the
  function and the destination unit so the manager knows what to enable.
- Check-then-act race declared above.

## References

- ADR 3.2.0003, ADR 3.2.0001, ADR 3.2.0006, ADR 3.1.0006, ADR 3.11.0001
- Issue #41; `docs/domain/staff/workforce.md` §3.7

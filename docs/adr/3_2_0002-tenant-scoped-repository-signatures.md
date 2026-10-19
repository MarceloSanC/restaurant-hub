---
title: ADR 3.2.0002 — Tenant scope is a parameter of every staff repository operation
description: Architecture Decision Record
when-use: Reference when adding a method to a staff out port, when implementing the Postgres repositories (Stage 3.3), or before introducing any lookup that takes only an entity id
keywords: [adr, staff, application, port, multi-tenant, isolation, scope, repository, fail-closed]
status: accepted
created_at: 2026-08-08
updated_at: 2026-10-19
adr_id: 3.2.0002
decision: Every read, write and delete operation of the staff out ports takes tenant_id as an explicit parameter (and unit_id for the employee listing) — there is no unscoped find_by_id; an id from another tenant is therefore indistinguishable from a nonexistent one.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0002 — Tenant scope in the port signature, not in the use-case body

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The staff bounded context is multi-tenant and, inside a tenant, **unit-partitioned**. Two ratified
rules govern it:

- "Um registro de funcionário pertence a exatamente uma unidade de exatamente um tenant" and
  "**nenhuma operação de staff atravessa unidades implicitamente** — só a cópia explícita"
  ([`workforce.md`](../domain/staff/workforce.md) §3.1).
- Row-level isolation by `tenant_id` in a single Postgres (ROADMAP-3).

The Definition of Done of Stage 3.2 is explicit about the failure mode it fears: "cópia entre
unidades duplica cadastro **sem vazar dados entre unidades**", and Stage 3.4's e2e is "funcionário
de outra unidade **não aparece**".

The precedent from identity is only a partial guide. There, `UnitRepository.find_by_id(unit_id)` is
unscoped, and isolation is decided by a dedicated `authorize_action` use case
([ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md)). Staff has no equivalent: its
use cases deliberately take **no actor** (authorization is Stage 3.4, same split as concept 2.2
§7.7). So whatever isolation Stage 3.2 offers must come from the shape of its own contracts.

The project has also recorded the general failure this concerns
(project memory, "teste trava o caso, não a propriedade"): a guard that each call site must
remember to apply is a guard that a future call site will silently omit, with the suite still green.

## Decision

**Tenant scope is part of the port signature.** Every operation of `JobFunctionRepository` and
`EmployeeRepository` takes `tenant_id` explicitly:

```python
find_by_id(tenant_id, job_function_id) -> JobFunction | None
find_by_name(tenant_id, name) -> JobFunction | None
find_all_by_ids(tenant_id, job_function_ids) -> tuple[JobFunction, ...]
list_by_tenant(tenant_id) -> tuple[JobFunction, ...]
delete(tenant_id, job_function_id) -> None
find_by_id(tenant_id, employee_id) -> Employee | None
list_by_unit(tenant_id, unit_id, *, include_inactive=False) -> tuple[Employee, ...]
delete(tenant_id, employee_id) -> None
exists_by_job_function(tenant_id, job_function_id) -> bool
```

`add`/`update` carry the scope inside the entity itself and match on it.

(The only non-tenant flag in the list is `include_inactive`, which selects **lifecycle state of the
employee record** — [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) — not
scope. The job-function listing has no flag at all, because the function has no state
— [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md).)

Two corollaries are normative:

1. **An id belonging to another tenant is indistinguishable from a nonexistent one** — the use
   case raises `JobFunctionNotFoundError` / `EmployeeNotFoundError`, never an error that would
   confirm that someone else's record exists.
2. **There is no tenant-wide listing of employees.** `list_by_unit` requires the unit. The absence
   of the broader method is the enforcement: the query that would leak units cannot be expressed.

## Alternatives considered

### Alternative A — Unscoped lookup + tenant comparison inside the use case
- **Description:** `find_by_id(employee_id)` returns the record; the use case compares
  `employee.tenant_id != command.tenant_id` and raises.
- **Pros:** matches the identity precedent literally; slightly smaller signatures; one index-free
  lookup path.
- **Cons:** the isolation holds only while **every** use case remembers the comparison. A new use
  case that forgets it compiles, type-checks and passes its own tests — the leak is invisible until
  someone crosses tenants in production. With 16 use cases in this Stage alone and more in 3.4/3.5,
  the number of places that must remember grows monotonically.
- **Why rejected:** it makes a security property depend on author discipline instead of on the
  type system, which is the exact class of defect recorded in the project's memory.

### Alternative B — Ambient scope (tenant carried in a context object / thread local)
- **Description:** a request-scoped `TenantContext` the repository reads implicitly.
- **Pros:** the shortest call sites; impossible to forget at the call site.
- **Cons:** hides the dependency (the use case no longer declares what it needs); makes the port
  untestable without setting up ambient state; couples the application layer to a request lifecycle
  it must not know about (LAYOUT §3); a bug in propagation silently scopes to the *previous*
  tenant, the worst possible failure.
- **Why rejected:** implicit state is precisely what the hexagonal boundary of this project exists
  to avoid, and it degrades from "wrong error" to "wrong tenant's data".

### Alternative C — Scope enforced only by the database (row-level security)
- **Description:** rely on Postgres RLS policies in Stage 3.3.
- **Pros:** one enforcement point, impossible to bypass with SQL.
- **Cons:** the fakes of this Stage would have no scope at all, so no unit test could exercise the
  property; the rule would be untestable until Stage 3.3; and the application would still need the
  tenant to set the session variable — the parameter reappears, just less visibly.
- **Why rejected:** it does not remove the need for the parameter, and it postpones the only tests
  that can prove the property to a later Stage. RLS remains available as an **additional** layer in
  3.3, and this decision does not preclude it.

### Do nothing / status quo
Not viable: without a decision, each use case would pick its own convention, which is how a leak
enters.

## Consequences

### Positive
- A leak between tenants becomes a **type error**, not a review finding.
- Every fake and every adapter is testable for the property directly ("record of tenant A is not
  found with tenant B's id").
- Cross-tenant probing cannot be used to detect the existence of another restaurant's records.

### Negative
- Signatures are longer, and callers always thread `tenant_id`.
- The scope parameter is redundant with what the entity already carries in `add`/`update`, so the
  port law has to say what happens when the two disagree. **Neither side "wins" silently:** a
  divergent `(tenant_id, unit_id)` on `update` is refused with a **named** error,
  `EmployeeRelocationError` (concept §4, law L-E3). Letting the incoming value win would move the
  record between units in silence; letting the stored one win would discard the write in silence.
  Both are corruption; the third option is to say so out loud.

### Neutral / trade-offs accepted
- Unit scope is **not** given the same treatment for single-record lookups: `find_by_id` is scoped
  by tenant only. Restricting a manager to their own units is an **authorization** decision, and it
  belongs to Stage 3.4 with `authorize_action` — collapsing it into the repository would duplicate
  the RBAC rule in two places that can diverge. The listing is the exception, because a listing
  without a unit filter has no legitimate caller in v1.
- Every lookup now filters on `tenant_id` in addition to the key, which has an indexing
  consequence in Stage 3.3. This ADR does **not** decide it: choosing between a composite index
  `(tenant_id, id)`, the plain primary key plus a filter, or row-level security is a persistence
  decision with its own trade-offs (write amplification, index size, plan stability), and it belongs
  to the Stage that measures them. Recorded as a **`[finding]` for Stage 3.3**: *the access pattern
  of every staff lookup is `(tenant_id, key)` — pick the indexing strategy deliberately.*

## References

- Related ADRs: [ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md) (where identity
  puts isolation, and why staff cannot reuse it in this Stage);
  [ADR 3.2.0001](./3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md) (the other half of
  the port-law contract).
- [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.1 (invariants of tenancy and
  unit partition), §3.7 (copy is the only explicit cross-unit operation).
- [`roadmap.md`](../roadmap.md) — Stage 3.2 DoD, Stage 3.4 DoD, ROADMAP-3.
- Project memory: "teste trava o caso, não a propriedade" (2026-07) — the class of defect this
  decision removes structurally.

## Supersessão parcial

**2026-10-19 — Context, a frase *"Staff has no equivalent: its use cases deliberately take **no
actor** (authorization is Stage 3.4 …)"*, superada por
[ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md).** Desde a Stage
3.7 todo command e query de staff carrega `actor`, e todo use case autoriza o alvo do command
pelo `AccessGuard` antes de tocar o repositório. A decisão deste ADR — assinaturas de
repositório escopadas por tenant, para que o isolamento venha da **forma** dos contratos — fica
intacta e passa a ser a **segunda** linha, não a única. Nota *append-only*; o corpo acima não
foi editado (CONVENTIONS §5).

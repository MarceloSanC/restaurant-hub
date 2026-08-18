---
title: ADR 3.4.0007 — The unit becomes part of the employee's internal address, in the port signature and in the commands, so the fake carries the same law as Postgres
description: Architecture Decision Record
when-use: Reference before looking up an employee by tenant and id alone, when adding a use case that acts on an existing employee record, or when someone proposes a tenant-wide employee search
keywords: [adr, scope, unit, tenant, port-signature, repository, command, contract-test, staff, isolation]
status: accepted
created_at: 2026-08-12
updated_at: 2026-08-12
adr_id: 3.4.0007
decision: EmployeeRepository.find_by_id and delete take (tenant_id, unit_id, employee_id), and the ten commands acting on an existing record carry unit_id, so unit isolation is a port law that the fake and the Postgres adapter prove identically — rather than a filter added only in the adapter's SQL or only at the HTTP boundary
context_stage: 3.4-staff-access-scope
bounded_context: staff
---

# ADR 3.4.0007 — The unit enters the employee's address

## Status

`accepted`

## Context

ADR 3.2.0002 scoped every staff repository signature by tenant, and recorded a
deliberate gap in its §Neutral section:

> Unit scope is **not** given the same treatment for single-record lookups:
> `find_by_id` is scoped by tenant only. Restricting a manager to their own units
> is an **authorization** decision, and it belongs to Stage 3.4 with
> `authorize_action` — collapsing it into the repository would duplicate the RBAC
> rule in two places that can diverge.

Stage 3.4's concept discovered that the boundary alone cannot close it. The
routes are nested under `/units/{unit_id}`, and the guard authorizes that unit
**against the actor** — but nothing checks it against the **record**. Because the
lookup is `(tenant_id, employee_id)`, a manager of unit A reaches any employee of
the same restaurant by putting its own unit in the path. Three consequences,
found at Checkpoint A:

- **Mutation** of a record in another unit.
- **Reading** it: every mutation route returns the full `EmployeeResponse`, so a
  rename to the same name is an idempotent probe that returns unit, workload,
  preference and unavailabilities of any employee in the tenant.
- **Exfiltration**: `POST /units/A/employees/{id-in-B}/copies` targeting A
  clones B's record into the attacker's own unit — both authorization calls pass,
  because the actor sees A twice.

`workforce.md` §3.1 ratifies the invariant this violates: *"nenhuma operação de
staff atravessa unidades implicitamente — só a cópia explícita"*.

The sponsor decided on 2026-08-12, verbatim: *"na busca por funcionário da
requisição do gerente/RH precisa filtrar apenas os que são da mesma unidade do
RH/gerente (que ele está usando/editando no momento e se ele estiver associado a
essa unidade)"*.

## Decision

**1. The unit becomes part of the address, in the port signature.**

```python
def find_by_id(
    self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId
) -> Employee | None: ...
def delete(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId) -> None: ...
```

**2. It is a port law, not adapter SQL.** Putting the filter only in the Postgres
`WHERE` clause would leave the in-memory fake accepting what the real adapter
refuses — the exact fake ≢ real divergence the byte-NUL finding cost this Step
already. As a signature, the fake carries the same law and the promoted contract
suite (ADR 3.3.0007) proves both sides with one test body.

**3. The ten commands that act on an existing record carry `unit_id`**: rename,
assign job functions, change workload profile, declare shift preference, register
and remove unavailability, deactivate, reactivate, delete, and copy (the
**source** unit; `target_unit_id` already existed). `CreateEmployeeCommand`
already carried it. The two queries are unchanged.

**4. The lookup law absorbs the unit, and the not-found rule wins.** The
normative order stays as ADR 3.2.0002 wrote it, with the unit folded into the
first step: resolve `(tenant_id, unit_id, employee_id)` — absent ⇒
`EmployeeNotFoundError` — and only then evaluate any other guard. A record that
exists in **another unit of the same tenant** is therefore *not found*, exactly
as a record of another tenant already was (concept 3.2 §5.4). No error confirms
the existence of a record the caller may not address.

**5. `L-E3` survives, with a narrower trigger.** `EmployeeRelocationError` still
guards `update` against relocating a stored record. It simply becomes
unreachable through the use cases, which now reload from the same unit they write
to. It remains a port law because a second inbound adapter could still attempt it.

**6. Declared target-layer expansion into Stages 3.2 and 3.3**, both merged: the
port, the ten commands, the twelve use cases, the fakes, the two Postgres
adapters and the contract suite. The roadmap block gets the reconciliation note.

**7. Non-goal, explicitly: the tenant-wide employee search.** The sponsor
described a *distinct, future* operation — when registering someone new, search
the already-registered people of the **whole restaurant**, *"aí pode aparecer se
ele tiver a permissão de ver todos os funcionários de todas as unidades"*. That
is a separate operation with its **own** permission, and it does **not** exist
today. It must never be obtained by loosening the normal lookup: the broad search
is an added capability, not a relaxed one.

## Alternatives considered

### Alternative A — read the record first, then compare its unit at the boundary
- **Description:** a new "find employee by id" use case; the route loads the
  record, compares `unit_id`, and only then acts.
- **Pros:** purely additive — no merged signature changes; and it yields the
  `GET /employees/{id}` any UI will eventually want.
- **Cons:** the rule lives in the adapter, so a second inbound adapter (CLI,
  worker) would not inherit it — the residual risk ADR 2.4.0003 already records
  for the escalation guard, repeated for isolation. And it costs an extra read on
  every write.
- **Why rejected:** **the sponsor chose the signature.** It was this concept's
  recommended option; recorded so the recommendation is not read as the decision.
  Its upside — a read-by-id route — is not lost, only unscheduled.

### Alternative B — filter by unit only in the Postgres `WHERE`
- **Description:** no signature change; the adapter narrows the query.
- **Pros:** smallest diff; no merged contract touched.
- **Cons:** the fake would accept lookups the real adapter refuses, so unit
  isolation would hold in production and not in unit tests — and the contract
  suite could not express it, because the signature would not carry the unit.
- **Why rejected:** it reintroduces fake ≢ real on a **security** invariant,
  which is strictly worse than on a storage detail.

### Alternative C — do nothing (keep tenant-only lookups)
The three consequences above ship. Not acceptable.

## Consequences

### Positive
- Unit isolation becomes impossible to omit: a caller that does not know the unit
  cannot form the call. This is the same property that made the tenant scope of
  ADR 3.2.0002 hold.
- One contract-test body proves it for the fake and for Postgres.
- The probe and the exfiltration paths close together, because both went through
  the same lookup.

### Negative
- **Two merged Stages are amended** — around 25 files across 3.2 and 3.3, plus
  the contract suite. This is the largest single cost in Stage 3.4 and the main
  reason its size alarm fires (concept §12).
- The `EmployeeRepository` signature is now three positional identifiers, which is
  easy to mis-order at a call site. Mitigated by the distinct `NewType`s, which
  make a swapped `unit_id`/`employee_id` a type error under mypy strict.
- ADR 3.2.0002's §Neutral text becomes historical: the gap it recorded is closed
  by a mechanism it did not anticipate (signature, not authorization alone). Noted
  rather than silently contradicted.

### Neutral / trade-offs accepted
- `exists_by_job_function` stays tenant-wide, by design: the removal guard must
  count references in **any** unit (`workforce.md` §3.2).
- No read-by-id route exists after this Stage. Recorded as a finding.

## References
- Sponsor decision, 2026-08-12, on fork F2 of
  `docs/stages/3.4-staff-access-scope/concept.md`
- ADR 3.2.0002 §Neutral (the gap this closes), ADR 3.3.0007 (promoted contract
  suites), ADR 3.3.0003 (`L-ORD`)
- `docs/domain/staff/workforce.md` §3.1
- `src/restaurant_hub/features/staff/application/ports/out/employee_repository.py`
- `src/restaurant_hub/features/staff/application/dtos/commands.py`

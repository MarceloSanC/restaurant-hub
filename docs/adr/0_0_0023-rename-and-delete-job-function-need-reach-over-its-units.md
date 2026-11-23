---
title: ADR 0.0.0023 — Renaming and deleting a job function need reach over every unit where it is enabled, and both writes are conditional on the enablement that was read
description: Architecture Decision Record
when-use: Reference before changing who may rename or delete a job function, before relaxing the reach rule of `_unit_enablement.py`, before changing `JobFunctionRepository.update` or `delete`, or when a manager is unexpectedly denied on a function enabled in every unit
keywords: [adr, staff, job-function, authorization, unit, enablement, manage-tenant, rename, delete, conditional-write, fail-closed, issue-207]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: "0.0.0023"
decision: 'RenameJobFunctionUseCase and DeleteJobFunctionUseCase authorize, after the tenant and after reading the function (404 first), the actor''s reach over the stored enablement with the same rule creation uses (`authorize_enablement` in `_unit_enablement.py`): manage_job_functions on each named unit, in sorted order, or manage_tenant when the function is enabled in every unit; the denial is the guard''s exception (403) and comes before name validation, the uniqueness probe and the reference guard. `JobFunctionRepository.update` (L-JF2) and `delete` (L-JF3) receive the enablement that was read and refuse with JobFunctionEnablementChangedError (409) when the stored one changed, deciding under the row lock as `update_enablement` does since issue #206.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0023 — Rename and delete of a job function need reach over its units

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided in issue #207 (standalone issue, hence the `0.0` prefix — CONVENTIONS §1,
"ADR global" — and `bounded_context: transversal`, CONVENTIONS §2; the decision is about the staff
bounded context, and the staff ADRs it touches point here through their dated notes). The number
was checked free on `develop`, on every remote branch and in every open worktree on 2026-11-23.

> Decided under delegation: the sponsor delegated the product fork of issue #207 to the
> recommended option (orchestrated run of 2026-11-23). It is recorded below as `P delegado`.

**Partially supersedes**, each keeping `accepted` with an append-only dated note (CONVENTIONS §5):

- [ADR 3.11.0001](./3_11_0001-job-function-unit-enablement-model.md) §Consequences, Neutral — the
  bullet *"Renaming and deleting a function keep the tenant-wide authorization of ADR 3.4.0008"*;
- [ADR 3.4.0008](./3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md) §Consequences,
  Neutral — *"The catalogue routes therefore have no unit-level visibility check at all"*, for
  rename and delete (the HTTP boundary still has none; the use case now has one);
- [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md) §Decision 3, the
  table row *"the 4 catalogue use cases — tenant only"*, and §Decision 4 — the declared exception
  (read before the derived target) now covers rename and delete as well as the change of units.

## Context

Since Stage 3.11 a job function belongs to the restaurant and is enabled either in every unit or
in a non-empty set of units ([ADR 3.11.0001](./3_11_0001-job-function-unit-enablement-model.md)
§Decision 1–2). Who may create it and who may change its units was decided by reach:
`manage_job_functions` on each named unit, `manage_tenant` for every unit (§Decision 4), and, for a
change, reach over every unit added or removed (§Decision 5). The rule lives once, in
`features/staff/application/use_cases/_unit_enablement.py`.

Rename and delete were left out on purpose (non-goal of concept 3.11 §1; ADR 3.11.0001
§Consequences, Neutral): they kept the tenant-wide authorization of ADR 3.4.0008. Two holes follow:

- a manager of unit A renames a function enabled only in B — the name changes in a unit he does
  not see;
- a manager of A deletes a function enabled only in B that no record holds (the reference guard
  still refuses a function in use), and recreates it for A — the function leaves B by a path that
  the change of units forbids.

So "cannot remove a unit he does not see" held for the change of units and not for the catalogue
as a whole. Issue #207 asked whether rename and delete should need the same reach.

Facts that constrain the answer, all verified on `develop` at 7a05854:

- `manage_tenant` is held only by `owner` (`identity/domain/value_objects/role.py`), and `manager`
  and `hr` hold `manage_job_functions` and are unit-scoped (`_UNIT_SCOPE_BYPASS_ROLES` in
  `identity/domain/entities/user.py` is `owner` and `platform_admin`).
- ADR 3.4.0008's exemption removes only the *requirement* to name a unit: *"Unit visibility
  (step 5) still runs whenever a unit **is** declared"* (§Decision 4). A use case that names a unit
  gets the visibility check for free; no identity change is needed.
- `GET /job-functions` shows every function of the restaurant with `all_units` and `unit_ids` to
  anyone holding the catalogue in the tenant (ADR 3.11.0001 §Decision 6; `JobFunctionResponse`).
- `SetJobFunctionUnitsUseCase` already reads the function before authorizing the units that depend
  on it, as a declared exception to ADR 3.7.0001 §4 with no oracle (ADR 3.11.0001 §Decision 5).
- Issue #206 closed the read-then-write race of the change of units with a conditional write under
  the row lock (ADR 3.11.0001, dated note of 2026-11-22), the shape
  [ADR 0.0.0010](./0_0_0010-employee-login-link-has-its-own-conditional-write.md) gave `link_login`.

## Decision

**1. Rename and delete need reach over the stored enablement.** After authorizing the tenant
(unchanged) and reading the function (404 if absent in the tenant), both use cases call
`authorize_enablement(guard, actor, tenant_id, named_units(job_function.unit_enablement))` — the
same function creation calls on the requested units:

- function enabled in named units → `manage_job_functions` on **each** of them, sorted; one unit
  outside the actor's reach is enough to deny;
- function enabled in every unit → `manage_tenant`. Holding every unit that exists today is not
  enough: "every unit" covers units created later (ADR 3.11.0001 §Decision 2).

`P delegado — opção A (alcance sobre a habilitação gravada, pela mesma regra), motivo: é a opção
fail-closed com uma cópia só da regra de alcance; a alternativa C (só a função restrita pede
alcance) não fecha o buraco — apagar uma função de todas as unidades e recriá-la só para a unidade
do gerente a tira de todas —, e a D (sempre manage_tenant) tiraria do gerente a gestão das funções
só da unidade dele, que a Stage 3.11 lhe deu.`

The denial is the guard's exception, raw (L-AG2), with no effect, and it comes **before** every
business check: the name validation and uniqueness probe of rename (ADR 3.6.0004 keeps ordering
them among themselves, after it) and the reference guard of delete — an actor without reach does
not learn whether the function is in use.

**2. 404 before 403, as in the change of units.** A function absent from the tenant is
`JobFunctionNotFoundError` (404) before any unit is authorized; an existing function outside the
actor's reach is the guard's denial (403, identity's constant body). `decision:C`, rung 1 (already
ratified): the order and the responses of `PUT /job-functions/{id}/units`. Answering 404 for
"exists but out of reach" would hide what `GET /job-functions` already publishes to the same actor
— the function, its name and its units — and would make the sister route answer differently for
the same situation. This read before the derived target is the declared exception to ADR 3.7.0001
§4 that `set_job_function_units` already uses, with the same justification: it reveals only what
the catalogue shows to whoever passed the tenant authorization.

**3. Both writes are conditional on the enablement that was read.** The reach is authorized against
the enablement the use case **read**; a change of units committing between that read and the write
would reopen the hole (with the function in `{A}`, the owner widens it to `{A, B}`; a manager of A
who read `{A}` would rename it, or delete it, in B). So:

- `JobFunctionRepository.update(job_function, expected)` — law **L-JF2 (revised)**;
- `JobFunctionRepository.delete(tenant_id, job_function_id, expected)` — law **L-JF3 (revised)**;

compare the stored enablement with `expected` and refuse with `JobFunctionEnablementChangedError`
(409, the entry the staff map already has since issue #206) without writing. Order: lookup
(`JobFunctionNotFoundError`) → comparison → name guard (rename) or reference guard (delete). The
Postgres adapter decides under the row lock, in one private helper shared by the three writes on an
existing function, taking in the lookup the lock the write itself would take: `FOR NO KEY UPDATE`
for the change of units (a non-key column, which does not conflict with the `KEY SHARE` an
assignment takes), `FOR UPDATE` for rename (`name` is in the unique index
`uq_job_functions_tenant_name`, which PostgreSQL counts as a key update) and for delete. `decision:C`, rung 1 (issue #206 / ADR
0.0.0010) and rung 2 (fail-closed). No migration, no new map entry.

The lookup of `delete` rebuilds the enablement again — issue #225 had removed that rebuild because,
without a lock, two statements under `READ COMMITTED` could see two instants. Under the row lock
they cannot: every writer of the link rows takes the parent row first (the argument of
`update_enablement`). The #225 conduct test of an unlocked lookup is replaced by a wait-and-reread
test.

**4. The HTTP boundary is unchanged.** It keeps authorizing `manage_job_functions` on the tenant
(ADR 3.4.0008); the unit-level decision is the use case's (ADR 3.7.0001). No route, schema or
status changes; the boundary's tenant-only check stays defense in depth.

## Decision records

The product fork (Decision 1) is `P delegado`, recorded inline above. The two forks the agent closed,
in the format of the `evidence-resolution` skill §5, verified by an `evidence-verifier` run over the
cited sources on 2026-11-23 (eight items: seven `sustenta`, one `parcial` — the delete-and-recreate
hole only applies to a function that no record holds, corrected in §Context):

[decision:C] D2 — what an actor without reach receives: 403 or 404
Escolha: 404 for a function absent from the tenant (before reach); 403 (guard's raw denial) for an existing function out of reach · Alternativas: 404 for both · Degrau (C): 1
Base: ADR 3.11.0001 §Decision 5 "The read is no oracle: what it reveals — the function's enablement — is what the catalogue (`GET /job-functions`) already shows to anyone who passed the tenant authorization." · ADR 3.11.0001 §Decision 6 "each item now says where it is enabled"; `JobFunctionResponse` carries `all_units` and `unit_ids`
Verificado: sustenta (evidence-verifier, 2026-11-23)
Configuração candidata: nenhuma · Reversível: sim (status of a denial; no persisted shape)

[decision:C] D3 — the read-then-write race between authorizing on the stored enablement and renaming or deleting
Escolha: close it with a conditional write on the enablement read (L-JF2 and L-JF3 revised), decided under the row lock · Alternativas: declare the limit with an issue · Degrau (C): 1 (issue #206 / ADR 0.0.0010), 2 (fail-closed)
Base: ADR 3.11.0001, dated note of 2026-11-22 "recusa com `JobFunctionEnablementChangedError` quando a gravada mudou — sem gravar nada; o mapa de staff a responde como `409`. O adapter Postgres decide sob `SELECT … FOR NO KEY UPDATE`"
Verificado: sustenta (evidence-verifier, 2026-11-23)
Configuração candidata: nenhuma · Reversível: sim (port signature, no migration)

## Alternatives considered

### Alternative B — keep the tenant-wide authorization and declare the limit
- **Pros:** no change; a manager keeps renaming functions created before Stage 3.11.
- **Cons:** leaves both holes open, and the rule "you cannot remove a unit you do not see" keeps
  depending on which route the actor uses.
- **Why rejected:** an access rule that holds on one path and not on the other is not a rule; the
  sponsor's criterion is fail-closed.

### Alternative C — only a restricted function needs reach; "every unit" stays tenant-wide
- **Pros:** managers keep renaming and deleting the functions that are enabled everywhere (all the
  functions migrated from before Stage 3.11).
- **Cons:** the delete-and-recreate hole stays open in its largest form: a manager deletes a
  function enabled in every unit that no record holds and recreates it only for his unit — it
  leaves every other unit. It also contradicts ADR 3.11.0001 §Decision 5, where a manager cannot
  even narrow a function enabled everywhere.
- **Why rejected:** it trades the rule for convenience exactly where the blast radius is largest.

### Alternative D — rename and delete always need `manage_tenant`
- **Pros:** simplest rule.
- **Cons:** a manager could no longer rename or delete a function he created for his own unit —
  undoing the capability Stage 3.11 gave him (ADR 3.11.0001 §Decision 4) for no security gain.
- **Why rejected:** stricter than the threat requires.

### Alternative E — declare the read-then-write race instead of closing it
- **Pros:** no port change.
- **Cons:** the race reopens, by timing, the hole Decision 1 closes; issue #206 already paid for
  the shape that closes it, so closing it here is one more caller of an existing helper.
- **Why rejected:** fail-closed, and the cost is small.

## Consequences

### Positive
- "Cannot act on a unit you do not see" holds for every catalogue write: create, change of units,
  rename and delete — one rule, one copy (`_unit_enablement.py`).
- The three writes on an existing function share one conditional shape and one adapter helper.

### Negative
- A `manager` or `hr` can no longer rename or delete a function enabled in every unit, including
  every function migrated from before Stage 3.11; the owner does it. This is the same limit ADR
  3.11.0001 §Consequences (Negative) already records for narrowing or widening such a function. A
  manager who needs it can ask the owner to restrict the function to named units first.
- **In a restaurant with a single unit — the most common pilot case — the manager and the hr lose
  rename and delete over every function that already exists**, because every function migrated
  from before Stage 3.11 is enabled in every unit, and they cannot narrow it to their unit to get it
  back (narrowing is the owner's too). What stays with them: the functions they create naming their
  unit, and assigning functions to records. The same holds for a manager who is a member of every
  unit of a multi-unit restaurant: "every unit" covers future units. This consequence was not read
  by the sponsor before the delegated choice; the question — keep, add a single-unit shortcut,
  migrate the old functions to named units, or revert — is issue #248 (raised by the audit of
  PR #239).
- Two port signatures changed (`update`, `delete` gain `expected`); every caller passes what it read.

### Neutral / trade-offs accepted
- A rename or delete racing a change of units of the same function now answers 409 and asks the
  client to reread, as the change of units already did.
- Rename and delete now take `FOR UPDATE` in the lookup instead of only at the `UPDATE`/`DELETE`;
  both already waited there for an assignment of the same function in progress, so no new wait
  exists.

## References

- Issue #207; issue #206; issue #225
- [ADR 3.11.0001](./3_11_0001-job-function-unit-enablement-model.md),
  [ADR 3.4.0008](./3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md),
  [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md),
  [ADR 3.6.0004](./3_6_0004-cheapest-local-check-first-in-rename-job-function.md),
  [ADR 0.0.0010](./0_0_0010-employee-login-link-has-its-own-conditional-write.md),
  [ADR 3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md)
- `docs/domain/staff/workforce.md` §3.2
- Code: `features/staff/application/use_cases/_unit_enablement.py` (`authorize_enablement`),
  `rename_job_function.py`, `delete_job_function.py`,
  `features/staff/application/ports/out/job_function_repository.py` (L-JF2, L-JF3),
  `features/staff/adapters/out/postgres/job_function_repository.py` (`_lock_unchanged`)
- Tests: `tests/unit/features/staff/adapters/test_job_function_reach_chain.py` (the property, every
  role x stored enablement x memberships, through identity's production chain),
  `tests/unit/features/staff/application/test_job_function_reach.py` (order, targets, race),
  `tests/contract/features/staff/test_job_function_repository_laws.py` (L-JF2/L-JF3 revised),
  `tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py` (`test_issue_207_*`),
  `tests/e2e/features/staff/test_staff_flow.py` (`test_issue_207_*`)

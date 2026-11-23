---
title: ADR 0.0.0025 — One login per unit is a partial unique index on `employees`, translated by the two link writes; the end-of-link rule stops reading the unit
description: Architecture Decision Record
when-use: Reference before writing `employees.user_id`, before changing `link_login`, `relink_login`, `_transition_under_lock` or `_login_link.end_active_link`, before arranging two records of one login in a test, or when revisiting the concurrent end-of-link race of ADR 3.8.0001 and the residual of ADR 3.10.0001 §6
keywords: [adr, user_id, login-link, one-per-unit, unique-index, partial-index, race, termination, revoke-sessions, staff, migration, issue-241]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: "0.0.0025"
decision: 'The rule "one login per unit" (ADR 3.10.0001 §6) is enforced by the database: migration `0008` creates the partial unique index `uq_employees_tenant_unit_user` on `employees (tenant_id, unit_id, user_id) WHERE user_id IS NOT NULL`, which counts active and terminated records alike. `link_login` (L-LINK) and `relink_login` (L-RELINK) gain a last check — another record of the same tenant and unit carrying the login ⇒ `LoginAlreadyLinkedInUnitError` (409), nothing written — after the address and the domain guards; the Postgres adapter gets it by translating the index violation by name, the fake by reading its store. `resolve_linkable_login` keeps its read as the common path. `_login_link.end_active_link` no longer lists the unit: under the index no other record of the unit carries the login, so ADR 3.8.0001 condition 1 holds by construction and the check could only fail open. No lock per `user_id`.'
context_stage: 0.0-global
bounded_context: staff
---

# ADR 0.0.0025 — One login per unit is a partial unique index

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided in issue #241 (standalone issue derived from Stage 3.10, hence the `0.0`
prefix — CONVENTIONS §1, "ADR global"). The issue lists two forms and asks for an ADR between
them; the sponsor delegated P forks to the implementing session, which takes the recommended
option:

```
[decision] P delegado — índice único parcial (tenant_id, unit_id, user_id), motivo: é a forma em
que o banco impõe a regra a todo escritor de `user_id`, sem depender de cada um lembrar de tomar
um lock, e é fail-closed (a escrita que violaria a regra não grava); a implementação é mínima —
um índice, uma tradução por nome e uma checagem no fake — e não exige unidade de trabalho em staff.
```

The number was checked free on `develop`, on every remote branch and in every open worktree on
2026-11-23. Migration `0008` was checked the same way (no other in-flight session creates one).

**Closes** the residual of ADR 3.10.0001 §6 ("two concurrent links of the same account into two
records of one unit can still both pass") and, with it, the race of ADR 3.8.0001 › `### Negative`
(two concurrent terminations of two same-unit records of one login). **Takes** ADR 3.10.0001
Alternative F, which that ADR kept as "the candidate for the residual". **Partially supersedes**
ADR 3.5.0004 §3 ("no UNIQUE" on `user_id`): uniqueness now holds per unit, never across units,
which is what workforce §3.1 ("one per unit") and §3.7 (several records across units) allow.
Each gets an append-only dated note.

## Context

- **How the link is written today (measured in the code).** `PostgresEmployeeRepository`
  `_transition_under_lock` locks **one** row — `SELECT employees … WHERE id, tenant_id, unit_id
  … FOR UPDATE` — runs the domain transition and writes one column. Every writer of `user_id`
  after creation (`link_login`, `relink_login`, `unlink_login`) goes through it.
- **How one-per-unit is checked today.** `_login_link.resolve_linkable_login` lists the unit
  (`list_by_unit(…, include_inactive=True)`) in its own read transaction, then the use case
  calls the port. Two R18/R19 for one account into two records of one unit can both read "no
  other record" and both write: each locks only its own row.
- **What the race needs.** ADR 3.8.0001's end-of-link race (each termination reads the other
  record as active, neither revokes) needs two same-unit rows carrying one login. Only the
  residual above produces them through the API; tests produced them with a direct `UPDATE`.
- **Staff has no unit of work** (ADR 2.6.0002 §2); `_transition_under_lock` opens its own
  transaction per call.
- **No production data.** The project has no deployment yet; every database that will run
  `0008` today is a development, CI or test database.

## Decision

**1. The database enforces one login per unit.** Migration `0008_employees_one_login_per_unit`
(`down_revision = "0007"`) creates, and `tables.py` declares:

```sql
CREATE UNIQUE INDEX uq_employees_tenant_unit_user
    ON employees (tenant_id, unit_id, user_id) WHERE user_id IS NOT NULL;
```

The index has no `active` in its predicate: the rule counts terminated records (ADR 3.10.0001
§6), and so does the index. Across units nothing changes.

**2. L-LINK and L-RELINK gain one check, last.** After the address (`EmployeeNotFoundError`) and
the domain guards on the stored record, a login already carried by **another** record of the same
tenant and unit, active or terminated, raises `LoginAlreadyLinkedInUnitError` (409) and nothing
is written. The Postgres adapter reaches it by the index: `_transition_under_lock` translates an
`IntegrityError` through a new per-operation map `ON_WRITE_LOGIN_LINK = {
"uq_employees_tenant_unit_user": LoginAlreadyLinkedInUnitError }` by constraint name (ADR
3.3.0004), with the record's id as detail. The fake checks its store at the same point.
`unlink_login`, `deactivate` and `reactivate` never write a non-null `user_id` and cannot reach
it. No new error, no new HTTP status: the error map stays at 30 entries.

**3. The read check stays.** `resolve_linkable_login` still refuses from its read, before the
write: it is the common path and keeps the order of R7 (identity lookup, then the unit). The
index is the backstop for the concurrent case and for any other writer.

**4. The end-of-link rule stops reading the unit.** `end_active_link` revokes iff the record is
active, linked and the login is an `employee` account. ADR 3.8.0001 condition 1 ("no other active
record of the same unit carries that login") is now true of every linked record by construction;
the listing that checked it could only change the outcome on a state the database refuses, and
there it would keep sessions alive (fail open). R13, R19 and R20 no longer list the unit.

**5. Existing data.** `0008` does not repair duplicates: if two rows of one unit carry one
login, `CREATE UNIQUE INDEX` fails and the migration aborts with nothing applied. Premise,
registered: there is no production data, and the API could only produce such rows through the
residual race. `downgrade` drops the index.

## Alternatives considered

### Alternative A — Lock per `user_id` (`SELECT … FOR UPDATE` over the login's records in the unit)
- **Pros:** no migration; same-unit duplicates written by a direct `UPDATE` stay arrangeable.
- **Cons:** the rows to lock are the ones that do **not** carry the login yet — `FOR UPDATE`
  locks only what the `SELECT` returns, so two links into two different records lock disjoint
  sets and both pass (the phantom). Closing it needs a lock on something that exists before the
  write: an advisory lock keyed by `(tenant, unit, user_id)`, or a parent row staff does not own
  (`units` is identity's, ADR 3.3.0002). An advisory lock is not enforced by the database: every
  writer of `user_id` — the three port methods today, any future one, a fix-up script — has to
  remember it. And the unit read would have to move into the adapter's transaction, i.e. a port
  law change anyway, with a second lock taken after the row lock in some paths (new lock order).
- **Why rejected:** fail-closed (rung 2) — the index refuses every writer, including one that
  forgets; the lock protects only writers that take it.

### Alternative B — Keep the same-unit listing in `end_active_link`
- **Pros:** no change to R13/R19/R20 or to their call-order tests.
- **Cons:** dead under the index, and the only state where it matters is one the index refuses,
  where it fails open; one unit listing per termination for nothing; its `if shared: return`
  becomes a mutant no test can kill (the mutation gate of issue #217 refuses unknown survivors).
- **Why rejected:** rung 2 (fail-closed) and rung 5 (simpler).

### Alternative C — Translate the index violation into a new error
- **Why rejected:** the meaning is exactly `LoginAlreadyLinkedInUnitError`; a second name for one
  rule would split the 409 the client already handles. `[decision:C]` rung 1.

## Consequences

### Positive
- Two concurrent links of one account into one unit: the second waits for the first and is
  refused with the 409 the rule already uses. Pinned by conduct tests with two connections.
- The ADR 3.8.0001 race cannot be produced on a database at `0008`: it needs two same-unit rows of
  one login, and no writer can create them.
- R13, R19 and R20 do one read fewer.

### Negative
- Arrangements of case (a) **inside a unit** describe a state that no longer exists: Stage 3.8's
  unit tests `test_ca06`/`test_ca07` of `test_employee_lifecycle.py` leave; its e2e `test_ca16`
  now asserts the refusal; Stage 3.10's `test_ca4_*` of `test_login_link_single_point.py` writes
  the state straight into the fake store and asserts that it no longer holds sessions; the
  scheduling contract world (`tests/contract/features/scheduling/conftest.py`) gives the
  terminated record its own login. Case (a) across units is unchanged (still revokes, ADR
  3.8.0001 Q4).
- A failed `0008` on a database with duplicates needs a manual fix before retrying.
- `add` with a preset `user_id` is not a production path (R12 and R15 build records without a
  login) and is not translated: on Postgres the index refuses it raw. Only tests take that path.

### Neutral / trade-offs accepted
- `LoginAlreadyLinkedInUnitError` now has two producers: the use-case read and the port.

## Decision records

```
[decision:E] 241-D1 — O que fecha o resíduo: lock por `user_id` ou índice único parcial
Escolha: índice único parcial `(tenant_id, unit_id, user_id) WHERE user_id IS NOT NULL` · Alternativas: `SELECT … FOR UPDATE` sobre os registros do login na unidade; advisory lock por `(tenant, unit, user_id)`
Base: PostgreSQL 16, §64.5 Index Uniqueness Checks: "If a conflicting row has been inserted by an as-yet-uncommitted transaction, the would-be inserter must wait to see if that transaction commits." · §11.8 Partial Indexes: "This enforces uniqueness among the rows that satisfy the index predicate, without constraining those that do not." · §13.3.2 Row-Level Locks: "FOR UPDATE causes the rows retrieved by the SELECT statement to be locked as though for update." · §13.3.5 Advisory Locks: "the system does not enforce their use — it is up to the application to use them correctly." · medição: `test_issue_241_*` de `test_staff_conduct.py` (dois `link_login`/`relink_login` concorrentes em dois registros da unidade, o segundo recusado)
Verificado: parcial→corrigido — evidence-verifier, 2026-11-23: §13.3.2 e §64.5 voltaram parciais (o texto não afirma o fantasma nem a checagem em `UPDATE` que muda a chave); o registro deixou de apoiar essas duas inferências na documentação e as apoia na medição (conduta com duas conexões no CI); §13.3.5, §11.8 e o estado atual do adapter sustentam
Configuração candidata: nenhuma · Reversível: sim (`downgrade` da `0008` remove o índice)
```

```
[decision:E] 241-D2 — Como o adapter reconhece a violação do índice
Escolha: tradução por nome, `uq_employees_tenant_unit_user` ⇒ `LoginAlreadyLinkedInUnitError`, num mapa da operação · Alternativas: texto da mensagem; recontar a unidade depois do erro
Base: postgres REL_16_STABLE src/backend/access/nbtree/nbtinsert.c, `_bt_check_unique`: `errtableconstraint(heapRel, RelationGetRelationName(rel))` — o campo de constraint do erro é o nome do índice · ADR 3.3.0004 (tradução por nome e por operação)
Verificado: sustenta — evidence-verifier, 2026-11-23
Configuração candidata: nenhuma · Reversível: sim
```

```
[decision:C] 241-D3 — A regra de fim de vínculo continua lendo a unidade?
Escolha: não; `end_active_link` decide por ativo, vinculado e papel `employee` · Alternativas: manter a listagem como defesa · Degrau (C): 2
Base: ADR 3.8.0001, `decision`: "R13 revokes the linked login's sessions only when (1) no other **active** record of the **same unit** carries that login" — sob o índice (§Decision 1) a condição vale para todo registro vinculado; mantida, a listagem só mudaria o desfecho num estado que o banco recusa, e ali deixaria as sessões vivas (fail-open)
Verificado: não verificado (§4.2) — decisão de implementação de regra já ratificada (ADR 3.8.0001); a citação é do próprio projeto, conferida no arquivo
Configuração candidata: nenhuma · Reversível: sim
```

## References

- Issue #241; ADR 3.10.0001 §6 and Alternatives F/G; ADR 3.8.0001 › `### Negative`; ADR 3.5.0004
  §3; ADR 2.6.0002 §2; ADR 3.3.0002; ADR 3.3.0004; ADR 0.0.0010; ADR 0.0.0013
- `docs/domain/staff/workforce.md` §3.1, §3.7
- PostgreSQL 16 documentation §11.8, §13.3.2, §13.3.5, §64.5; `nbtinsert.c` (REL_16_STABLE)

---
title: ADR 3.3.0004 — Integrity errors in staff are translated by constraint name AND by the operation that raised them
description: Architecture Decision Record
when-use: Reference before adding a constraint to the staff schema, before mapping an IntegrityError to a domain exception, when a foreign key can be violated by more than one operation, or when deciding whether a foreign-key violation should surface as a business error
keywords: [adr, integrity-error, constraint-name, psycopg, diag, foreign-key, restrict, translation, staff, error-mapping, race-condition]
status: accepted
created_at: 2026-08-10
updated_at: 2026-08-10
adr_id: 3.3.0004
decision: the staff translator takes a per-operation constraint map instead of a single module-level dictionary, because fk_employee_job_functions_job_function means JobFunctionNotFoundError when inserting a link and JobFunctionInUseError when deleting the parent; and that one foreign key is translated, unlike identity's rule, because port law L-E4 requires it
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0004 — Per-operation translation of integrity errors

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Identity's Stage 2.3 established the translation mechanism
(`integrity_errors.py`): read `diag.constraint_name` from psycopg — never parse
the driver's message, whose text varies by version and locale — and look it up in
a module-level `dict[str, Callable[[str], Exception]]`. It also established a
policy (concept 2.3 §7, Decision 7): **only constraints with business meaning are
translated**; foreign-key violations rise as raw `IntegrityError`, because the use
case already validated existence before writing, so an FK that fires means exotic
concurrency or a bug, and dressing it as a 4xx would hide the defect.

Two facts of the staff schema collide with that mechanism.

**First, one constraint has two business meanings.** Probed against the compose
PostgreSQL on 2026-08-10:

| Operation | sqlstate | `diag.constraint_name` |
|---|---|---|
| `INSERT INTO employee_job_functions` with a job function of another tenant | 23503 | `fk_employee_job_functions_job_function` |
| `DELETE FROM job_functions` for a referenced function | 23503 | `fk_employee_job_functions_job_function` |

Same name, same sqlstate. The first must become `JobFunctionNotFoundError`
(law L-E4); the second must become `JobFunctionInUseError` (law L-JF3). Only
`diag.message_detail` differs, and reading it is message parsing by another name.

**Second, law L-E4 explicitly demands that a foreign key be translated.** The
docstring of `EmployeeRepository.add` says it in full: without the law, a job
function removed between the use case's check and the write would hit the
`RESTRICT` and raise "um erro **não previsto pelo contrato** — que a 3.4
converteria em 500. Com ela, a corrida termina no mesmo erro tipado do caminho
comum."

## Decision

The staff translator takes the map as an argument:

```python
ConstraintMap = Mapping[str, Callable[[str], Exception]]
def translate(error: IntegrityError, constraint_map: ConstraintMap, detail: str) -> Exception: ...
```

The module exports one named map per operation — `ON_INSERT_JOB_FUNCTION`,
`ON_UPDATE_JOB_FUNCTION`, `ON_DELETE_JOB_FUNCTION`, `ON_WRITE_EMPLOYEE` — and each
repository method passes the map for what it was doing. Ambiguity is resolved by
the **caller's intent**, which is always known, and never by inspecting text.

**The names are in English, diverging from identity's `traduzir`.** CONVENTIONS §1
is literal — all source code in English, including constants — and Stage 3.2
already recorded a `[finding]` about Portuguese identifiers inside `src/` for this
bounded context, whose stated direction is to rename them. These six names are
**module API**, not locals; adding them in Portuguese would deepen an acknowledged
debt. The divergence from `integrity_errors.py` in identity is recorded here so a
future sweep treats that module as the debt rather than as the pattern to copy.

`fk_employee_job_functions_job_function` is translated in both maps that can
reach it, to different exceptions. Every other foreign key
(`fk_employee_job_functions_employee`, and the two on the leaf child tables) and
every CHECK constraint remains untranslated and rises intact, exactly as identity
decided: those are reachable only through a mapper bug or manual corruption, and
the corresponding invariants are already enforced by the entities'
`__post_init__`.

As in identity, `translate` **returns** the exception rather than raising it, so
the repository keeps the `raise … from error` and the causal chain survives.

**The message shape is contract, not prose.** For law L-E4 the common path
pre-checks the requested ids inside the same transaction and names the **smallest
missing id in lexicographic order** — `sorted()`, matching what the fake already
does, because a `frozenset` iterates in an order that depends on
`PYTHONHASHSEED` and one existing law test asserts a specific id. On the backstop
path — the genuine race that the FK catches — PostgreSQL does not expose *which*
id failed through a structured field, so the message cites the requested set,
also rendered with `sorted()`.

That difference in shape is not cosmetic: it is the only **observable
discriminator** of which of the two guard layers answered, and it is how this
Stage discharges the fourth inherited finding ("the suite pinned the result, not
the conduct"). Both layers raise the same exception type, so a test asserting only
the type and the final state is satisfied by an implementation with no adapter-side
pre-check at all.

**Not translated, and not `IntegrityError` at all:** `DeadlockDetected` (`40P01`)
and serialisation failures (`40001`) are `OperationalError`. They never reach this
module and rise raw; their HTTP treatment is escalated to Stage 3.4.

## Alternatives considered

### Alternative A — Keep identity's single module-level map
- **Description:** one `dict` keyed by constraint name for the whole bounded
  context.
- **Pros:** identical shape to identity; nothing new to learn.
- **Cons:** it cannot answer the shared-name case. Whichever exception was
  registered would be wrong roughly half the time: deleting a referenced function
  would report "job function not found", or assigning a foreign tenant's function
  would report "job function in use". Both are worse than an untranslated error,
  because they are plausible.
- **Why rejected:** measured to be ambiguous; a lookup table that cannot express
  the distinction is not a smaller solution, it is an incorrect one.

### Alternative B — Disambiguate with `diag.message_detail`
- **Description:** the detail text differs ("is not present in table" versus "is
  still referenced from table"); branch on it.
- **Pros:** keeps the single map.
- **Cons:** it is message parsing, which the identity module rejects by name and
  by docstring; the text is version- and locale-dependent, and the gate would not
  catch the day it changes.
- **Why rejected:** it re-adopts the exact fragility the mechanism was built to
  avoid.

### Alternative C — Split the constraint in two so each name has one meaning
- **Description:** e.g. add a redundant trigger or a second constraint so the
  insert path and the delete path report different names.
- **Pros:** preserves the single map.
- **Cons:** a foreign key is one object in PostgreSQL; producing two names means
  triggers or a check that duplicates the FK's job, adding a second enforcement
  path that can drift from the first.
- **Why rejected:** it distorts the schema to fit the translator, rather than the
  reverse.

### Alternative D — Do nothing / let both rise as raw `IntegrityError`
- **Description:** apply identity's Decision 7 literally, translating no FK.
- **Pros:** the simplest rule, and consistent with the neighbouring bounded
  context.
- **Cons:** it directly violates law L-E4, which Stage 3.2 published in the port
  docstring and which Stage 3.4 relies on to avoid 500s on a legitimate race; and
  L-JF3's `JobFunctionInUseError` would only ever be produced by the use case's
  pre-check, i.e. the database guard would exist and never be reachable as a
  typed error.
- **Why rejected:** the contract this Stage implements says otherwise.

## Consequences

### Positive
- The two cross-aggregate laws produce the same typed error on the common path
  and on the racing path — indistinguishable to Stage 3.4, which is what the law
  promised.
- Adding a constraint later forces an explicit choice of *which* operations can
  violate it, instead of a silent append to a global dict.

### Negative
- Staff's translator differs in signature from identity's. Someone reading both
  will notice, which is why the reason is written here and referenced from the
  module docstring.
- Four maps must be kept in step with the schema; a constraint added without a
  map entry rises untranslated (which is the safe direction, but is still a gap
  a test must cover).

### Neutral / trade-offs accepted
- The `detalhe` on the L-E4 backstop path is the requested set rather than the
  offending id.
- Identity is **not** retrofitted to this shape: it has no ambiguous constraint,
  and changing it would be churn without a defect to fix.

## Implementation notes

- The contract/integration suite must cover **both** sides of
  `fk_employee_job_functions_job_function` explicitly — one test inserting a link
  to a foreign tenant's function, one deleting a referenced function — otherwise
  a single-map regression passes.
- A test should also assert that an unmapped constraint rises as
  `IntegrityError`, so "translate everything" cannot creep back in.

## References

- Related ADRs: [2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md),
  [3.3.0001](./3_3_0001-staff-schema-tenant-scoping-and-composite-fk-cerco.md),
  [3.2.0001](./3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md)
- Precedent module: `src/restaurant_hub/features/identity/adapters/out/postgres/integrity_errors.py`
- Probe results: `docs/stages/3.3-staff-persistence/concept.md` §9

---
title: ADR 3.3.0003 — Staff listings have a total order fixed as a port law, using the C collation so the fake and PostgreSQL agree byte for byte
description: Architecture Decision Record
when-use: Reference before adding an ORDER BY to a staff query, before paginating a staff listing, before changing how a repository rehydrates an aggregate's ordered collection, or when a contract test compares sequences produced by a fake and by a database
keywords: [adr, ordering, order-by, collation, c-collation, pagination, port-law, contract-test, determinism, locale, staff]
status: accepted
created_at: 2026-08-10
updated_at: 2026-08-10
adr_id: 3.3.0003
decision: the staff listings order by name COLLATE "C" then id COLLATE "C" — both terms carry the collation — and the employee aggregate rehydrates unavailability periods ordered by start_at; the ordering is declared as port law L-ORD so it binds the in-memory fake as well as the PostgreSQL adapter
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0003 — Total ordering as a port law, with the C collation

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.2's audit escalated a `[finding]` to this Stage: `list_by_unit` (L-E6)
and `list_by_tenant` (L-JF5) declare **no order**, and no test pins one. The
omission was correct in that layer — pinning an order against the fakes would
have broken the reuse of that suite as a contract test — but PostgreSQL returns
rows from a `SELECT` without `ORDER BY` in an order that is unstable across
plans, and Stage 3.4 will paginate these listings. Pagination over an unstable
order silently duplicates and omits rows.

The finding's suggested direction was a business key plus `id` as a tiebreaker,
so the order is **total** and not merely stable on a non-unique column. Employee
names are explicitly non-unique (homonyms are legitimate), and job-function names
are unique only within a tenant.

Two things the finding did not anticipate surfaced while designing the schema:

1. **Collation is environment-dependent.** `ORDER BY name` uses the database's
   default collation. The compose container reports `datcollate = en_US.utf8`.
   Under a linguistic collation, `"ana"` sorts next to `"Ana"`; under byte order
   it sorts after `"Zeus"`. Python's `sorted()` is always codepoint order. A
   contract test that runs the same body against the fake and against PostgreSQL
   would therefore pass or fail depending on the host's locale — the worst
   possible failure mode, because it is green on the machine that wrote it.
2. **The aggregate has an ordered collection too.** `Employee.unavailabilities`
   is a `tuple`. The fake preserves insertion order; a `SELECT` of the child
   table has no order at all. The round-trip comparison in a contract test would
   diverge for exactly the same reason, and the port says nothing about it.

`job_function_ids` and `ShiftPreference.periods` are `frozenset`s, so they have
no order to agree on.

## Decision

A thirteenth named law, **`L-ORD`**, is added to the two port docstrings
alongside the twelve published by Stage 3.2 (it adds, it does not amend any of
them):

- `list_by_tenant`, `list_by_unit` and `find_all_by_ids` return rows ordered by
  `name COLLATE "C"`, then by `id COLLATE "C"`. **Both** terms carry the
  collation: `COLLATE` binds to the operand on its left, so an `id` written
  without it falls back to the database's collation — in the tiebreaker, which is
  exactly the term Stage 3.4's pagination will use as a cursor. Measured against a
  column with a linguistic collation, `ORDER BY name COLLATE "C", id` yields
  `('Maria','_z') < ('Maria','0') < ('Maria','a') < ('Maria','B')`, while Python's
  `sorted()` yields `'0' < 'B' < '_z' < 'a'`.
- `find_by_id` and `list_by_unit` — the two `EmployeeRepository` methods that
  assemble an aggregate — rehydrate `Employee.unavailabilities` ordered by
  `start_at`. That is a total order per employee because periods of one employee
  never overlap, so `start_at` is unique within the aggregate. (`find_all_by_ids`
  belongs to `JobFunctionRepository` and returns no `Employee`; it is covered by
  the listing clause above.)

The law binds **both implementations**. The in-memory fake is corrected to sort
the same way; the law is not relaxed to accommodate it. That is the literal
precedent of ADR 2.3.0003, where identity's fakes were corrected rather than the
contract retroacted.

`COLLATE "C"` is explicit in the SQL rather than inherited from the database.
Measured on 2026-08-10 against the compose PostgreSQL over
`["Ana", "ana", "Zeus", "Álvaro", "Maria", "Cozinheiro ", "cozinheiro"]`, the
result of `ORDER BY name COLLATE "C", id COLLATE "C"` is **identical** to
Python's `sorted()`.

**The clause needs a positive control, and this is not optional.** The project's
image is `postgres:16-alpine`, i.e. musl libc, where `strcoll` is `strcmp`:
`pg_database.datcollate` reports `en_US.utf8`, but `pg_collation` has no such
entry and the default ordering behaves as byte order. Consequently, on this image
`ORDER BY name` and `ORDER BY name COLLATE "C"` produce identical output for
every dataset — including the adversarial one above. An implementer who omits the
clause would pass every ordering test, forever. The Stage therefore requires a
test that runs the same `ORDER BY` with `COLLATE "und-x-icu"` (present in the
image, and measured to order `Álvaro < ana < Ana < Zeus`) and asserts that it
**diverges** from `sorted()` — proving that the choice of collation has semantic
effect.

But that control alone does not catch the omission, and the distinction matters:
no assertion about the adapter's **result** can fail on this image, because the
default ordering already equals `C`. The clause is therefore also pinned by an
assertion about **conduct** — that the compiled SQL of each listing statement
contains `COLLATE "C"` on both `ORDER BY` terms. Result-only tests here are the
"pins the case, not the property" failure mode: they stay green while the bug
waits for the first glibc/ICU cluster.

## Alternatives considered

### Alternative A — `ORDER BY name` with the database's default collation
- **Description:** rely on whatever collation the cluster was initialised with.
- **Pros:** reads naturally to a Portuguese speaker when the collation is
  linguistic; no `COLLATE` noise in the SQL.
- **Cons:** the contract test's outcome depends on the host's locale, so the
  suite would be green in CI and red on a developer machine (or the reverse);
  replicating ICU/glibc collation inside the Python fake is not feasible; and
  restoring a dump into a differently-initialised cluster would silently change
  pagination boundaries.
- **Why rejected:** it makes the Stage's central deliverable — proof that fake ≡
  real — depend on an environment variable.

### Alternative B — `ORDER BY id` only
- **Description:** order by the surrogate identifier and let the boundary sort
  for display.
- **Pros:** trivially total, trivially identical between fake and database, and
  immune to collation entirely.
- **Cons:** the listing order becomes UUID order, i.e. arbitrary; every consumer
  that wants a readable list must fetch everything and sort client-side, which is
  precisely what paginating exists to avoid.
- **Why rejected:** it makes pagination correct and useless in the same move.

### Alternative C — normalise a sort key column (`name_sortable`, folded and unaccented)
- **Description:** persist a derived column, index it, order by it.
- **Pros:** linguistic-looking order that is deterministic and environment-independent.
- **Cons:** it is a second source of truth for the name, which the project has
  explicitly refused for staff (names are stored **verbatim**, ADR 3.1.0002 /
  ADR 2.3.0005); the fake would have to reimplement the folding rule exactly; and
  the rule itself (which accents fold to what) is a product decision nobody has
  made.
- **Why rejected:** it reintroduces normalisation into a bounded context whose
  defining choice about names is that they are never normalised.

### Alternative D — Do nothing / leave the order undeclared
- **Description:** ship without `ORDER BY`, as Stage 3.2 did.
- **Pros:** no decision to defend.
- **Cons:** it is precisely the escalated finding, and Stage 3.4 would paginate
  over it. It is much cheaper to fix before the `ORDER BY` exists than after the
  boundary has paginated on it.
- **Why rejected:** the finding exists.

## Consequences

### Positive
- Pagination in Stage 3.4 has a stable, total cursor to build on.
- The contract suite can compare sequences directly, with one body, on any host.
- The unavailability round-trip becomes deterministic, closing a divergence that
  no existing test would have caught.

### Negative
- The order is by codepoint, not linguistic: `"Álvaro"` comes after `"Zeus"`, and
  `"ana"` after `"Zeus"` as well. For a list of a few dozen employees this is
  visible.
- The fake gains a sort, which makes it very slightly less "obviously trivial".

### Neutral / trade-offs accepted
- Display ordering is a presentation concern. If Stage 3.4 wants a
  Portuguese-linguistic list, it sorts for display or exposes an ordering
  parameter — **without** touching `L-ORD`, which the pagination cursor depends
  on. This is escalated as a `[finding]` to Stage 3.4.
- The ordering is deliberately **not** baked into a covering index (see
  ADR 3.3.0005), which keeps a future change to one line of SQL rather than a
  migration.

## Implementation notes

- The `ORDER BY` goes in the SQL, never in Python: sorting after the fetch would
  make future `LIMIT`/`OFFSET` return the wrong page.
- Contract test data must include an accented name, mixed case, a trailing-space
  variant, and **two homonyms with different ids** — otherwise the tiebreaker, the
  only term the pagination cursor depends on, is never exercised.
- The suite must carry **both** checks described above: the assertion on the
  compiled SQL (which is what fails when the clause is dropped) and the
  `COLLATE "und-x-icu"` positive control (which shows the clause is not a no-op).
- The fake's ordering must use plain `sorted()` on the same key tuple
  `(name, id)`; any normalisation there would reintroduce the divergence this ADR
  removes.

## References

- Related ADRs: [2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md),
  [3.1.0002](./3_1_0002-minimal-employee-record-attributes.md),
  [2.3.0005](./2_3_0005-names-persisted-verbatim.md),
  [3.3.0005](./3_3_0005-tenant-scoped-indexing-without-row-level-security.md)
- Finding: `docs/stages/3.2-staff-application/technical.md` §7, entry of 2026-08-09
- Probe results: `docs/stages/3.3-staff-persistence/concept.md` §9

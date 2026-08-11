---
title: ADR 3.3.0007 — The port-law suites of Stage 3.2 are moved into tests/contract and parametrised over the fake and the PostgreSQL pair, not duplicated
description: Architecture Decision Record
when-use: Reference before writing a contract test for a staff port, before copying a law suite, when deciding where a suite that pins port semantics should live, or when choosing what belongs in a contract fixture versus fake-only instrumentation
keywords: [adr, contract-test, fakes, pytest, parametrize, port-law, test-layout, staff, single-source, instrumentation]
status: accepted
created_at: 2026-08-10
updated_at: 2026-08-10
adr_id: 3.3.0007
decision: test_job_function_repository_laws.py and test_employee_repository_laws.py move from tests/unit to tests/contract/features/staff and take a repos fixture parametrised over ["fake", "postgres"], with a new RepositoriosDeStaff holder, because StaffFakes types a concrete in-memory store that the real pair does not have
context_stage: 3.3-staff-persistence
bounded_context: staff
---

# ADR 3.3.0007 — Law suites promoted to contract tests

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.2 wrote two suites — `test_job_function_repository_laws.py` (21 tests) and
`test_employee_repository_laws.py` (25 tests) — that pin the twelve named port
laws. They live in `tests/unit/features/staff/application/`, are marked
`pytest.mark.unit`, and build their subject by calling `staff_repositories()`,
which returns a `StaffFakes` holder.

Both suites say, in their own module docstrings, that they exist so that
"o teste de contrato da 3.3 possa pareá-los **lei a lei**". `StaffFakes` says the
same: its two repository fields are annotated with the `Protocol`s, not the
concrete classes, "é o que torna este holder reusável pela 3.3, que o preenche
com os adapters Postgres sem mudar uma linha dos testes de lei."

Identity established the mechanism in Stage 2.3: `tests/contract/features/identity/`
with a frozen `Repositorios` holder and a `repos` fixture with
`params=["fake", "postgres"]`, so each test runs twice and a divergence reads
directly off the output as `[fake]` green / `[postgres]` red.

The `pytest-with-fakes` skill is explicit on the layout question:
`contract/` is "1 suite per port; runs against fake + real", and under DON'T,
"Don't duplicate contract tests inside unit (defeats the point: the contract is
single)."

One obstacle: `StaffFakes` is not literally reusable. It has three fields, and
the third is `store: InMemoryStaffStore` — a concrete in-memory type that the
PostgreSQL pair has no analogue for. Its docstring justifies the field by the
`calls` list, which backs the "did not touch the port" assertions.

## Decision

The two suites **move** to `tests/contract/features/staff/`, change
`pytestmark` from `unit` to `contract`, and take a `repos` fixture instead of
calling `staff_repositories()`. The 46 test functions keep their **names** —
which carry the law identifiers — and their **assertions**, so the pairing is
literally law by law.

**What does change, stated so the task is not underpriced.** 45 of the 46
functions are declared `def test_…() -> None` and build their subject in the body;
there are 56 call sites of `staff_repositories()` and of helpers that return
`StaffFakes`. Every signature and every construction line changes, and the helpers
are re-typed to the new holder. Separately, `L-ORD` (ADR 3.3.0003) **adds** tests:
the existing listing assertions use *sets* deliberately, so they pin no order at
all. And the module comment in `test_employee_repository_laws.py` that declares the
ordering as deliberately un-pinned becomes false and is removed in the same commit.
The invariant to protect during the move is that the count and content of
assertions per law are unchanged — a mechanical check, not a reading.

`tests/contract/features/staff/conftest.py` defines a new frozen holder,
`RepositoriosDeStaff(job_functions, employees)`, typed with the two `Protocol`s,
and a `repos` fixture with `params=["fake", "postgres"]`. The `fake` parameter
builds it from `staff_repositories()`; the `postgres` parameter pulls the
session-scoped `engine` fixture, truncates, and builds it from the two adapters.

`StaffFakes` is **not** widened or genericised. It stays exactly as Stage 3.2
shipped it, as the holder used by the use-case suites that need `store.calls`.
Fake-only instrumentation is deliberately outside the contract, on identity's
CA16 criterion: requiring it of a real adapter would be inventing a requirement.
This costs nothing here — grep confirms neither law suite references
`store.calls` or `fakes.store`.

## Alternatives considered

### Alternative A — Keep the suites in `tests/unit` and write a second contract suite
- **Description:** leave Stage 3.2's tests untouched; add a parallel suite under
  `tests/contract/features/staff/` exercising the same laws against both
  implementations.
- **Pros:** Stage 3.2's artefacts are not moved; unit coverage numbers are
  undisturbed; the diff of this Stage is purely additive.
- **Cons:** two suites for one contract. The day someone tightens a law, they
  edit one of them, and the other keeps asserting the old behaviour — green.
  This is exactly what the skill's DON'T is about, and it also doubles the
  maintenance of the most semantically dense tests in the bounded context.
- **Why rejected:** a contract with two definitions is not a contract.

### Alternative B — Parametrise in place, leaving the files under `tests/unit`
- **Description:** add the fixture but keep the path and just change the marker.
- **Pros:** smallest possible move; git history stays on one path.
- **Cons:** a suite under `tests/unit/` that requires a live PostgreSQL
  contradicts the layout that `LAYOUT.md` and the skill both define (`unit/` is
  "pure domain + use cases with fake"); `-m unit` would stop being runnable
  without Docker; and the next reader looking for the contract tests would not
  find them where every other contract test lives.
- **Why rejected:** it makes the directory names lie, which is the cheapest thing
  in a repo to keep true.

### Alternative C — Widen `StaffFakes` (make `store` optional or generic)
- **Description:** reuse the existing holder for both implementations by relaxing
  the `store` field.
- **Pros:** no new type; the docstring's promise of reusability is honoured
  literally.
- **Cons:** an optional `store` means every use-case test that relies on
  `store.calls` must now handle `None`, and a holder named `StaffFakes` would be
  carrying real PostgreSQL adapters — a name that would actively mislead.
- **Why rejected:** the promise in the docstring is about the two `Protocol`-typed
  fields, and that promise *is* honoured: the new holder reuses them verbatim. A
  separate holder for a separate purpose is cheaper than a union type nobody can
  name.

### Alternative D — Do nothing / test the adapters only with integration tests
- **Description:** write integration tests for the PostgreSQL adapters and leave
  the law suites pinned to the fake.
- **Pros:** conventional; no movement of existing files.
- **Cons:** it reproduces the exact defect Stage 2.3 had to pay off — fakes and
  adapters agreeing in prose and diverging in behaviour, with both suites green.
  The definition of done in issue #38 says the contract test must prove fake ≡
  real for the twelve laws.
- **Why rejected:** it is the failure mode this Stage exists to prevent.

## Consequences

### Positive
- One definition of the contract, executed twice, with the law name in the test
  id on both sides.
- Any divergence between the fake and the adapter surfaces as the same test
  passing in `[fake]` and failing in `[postgres]`, with no reading required.
- The new `L-ORD` law (ADR 3.3.0003) lands in the same place, binding both
  implementations from the moment it is written.

### Negative
- The 46 tests now require a live PostgreSQL for half of their runs, so
  `-m contract` joins `-m integration` in needing Docker (ADR 2.3.0001 already
  made that true for the suite as a whole).
- `tests/unit/features/staff/application/` loses 46 tests; the coverage the fakes
  used to get from them now arrives via the `[fake]` parameter, which must be
  confirmed when checking per-file coverage.

### Neutral / trade-offs accepted
- Fake-only instrumentation (`store.calls`) stays out of the contract, and the
  use-case suites that rely on it keep using `StaffFakes` unchanged.
- Contract runtime roughly doubles for these suites; measured against the cost of
  the divergence class they catch, this is not close.

## Implementation notes

- Move with `git mv` so the history of the 46 tests follows them.
- The `postgres` parameter must truncate before building, exactly as identity's
  fixture does, and must obtain `engine` via `request.getfixturevalue` so that a
  pure-`fake` run does not open a connection.
- The `[fake]`/`[postgres]` parameter ids must appear in `pytest --collect-only`;
  that is the mechanical check that the promotion actually happened rather than
  the suite silently running once.

## References

- Related ADRs: [2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md),
  [2.3.0001](./2_3_0001-integration-tests-require-real-postgres.md),
  [3.2.0001](./3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md),
  [3.3.0003](./3_3_0003-total-ordering-with-c-collation-as-port-law.md)
- Skill: `.claude/skills/pytest-with-fakes`
- Precedent: `tests/contract/features/identity/conftest.py`
- Issue: https://github.com/MarceloSanC/restaurant-hub/issues/38

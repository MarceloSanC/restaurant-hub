---
title: ADR 2.3.0001 — Integration tests require a real Postgres in both environments; no self-skipping path
description: Architecture Decision Record
when-use: Reference before adding a test that needs an external service, before adding a skip guard to the test suite, or when revisiting what `make check` requires to run
keywords: [adr, ci, postgres, integration-tests, gate, false-green, skip, docker, coverage]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.3.0001
decision: 'Integration tests run against a real Postgres in both the laptop and the runner — `ci.yml` gains a `services: postgres`, and an unreachable database fails loudly instead of skipping, so no code path can report green without having touched the database'
context_stage: 2.3-identity-persistence
bounded_context: identity
---

# ADR 2.3.0001 — Integration tests require a real Postgres in both environments

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.3 is the first stage in this project that touches real I/O. Until now the
whole suite was pure: 347 tests, no database, no network in any verdict.

The gate is `make check`, which expands to
`lint typecheck layout-check import-check lock-check docs-check test-gate`, and
`test-gate` runs `uv run pytest tests/ --cov=src/restaurant_hub`. The CI job
`lint-and-test` runs **literally `make check`** — that literalness is invariant I3
of Stage 1.2, and it is what makes the transitivity argument in
`docs/runbooks/validate-ci-gate.md` valid ("every class that fails locally fails on
the runner"). CI-specific policy therefore travels via `env:`, never as an extra
command-line argument.

`.github/workflows/ci.yml` has **no Postgres service**. The moment integration tests
exist, exactly two things can happen:

1. they fail on the runner, and CI is permanently red; or
2. they skip themselves when the database is unreachable, and the gate reports green
   **because it did not look**.

Option 2 is precisely the defect catalogued by
[ADR 1.2.0001](./1_2_0001-deterministic-pr-path-gates.md), which classifies gate
degradation into three kinds and rules that degradation is legitimate only when it
is **decided** (coverage relocated elsewhere) or **semantic** (the rule does not
apply), and is a **defect** when it is an accident of the environment. Its wording
is blunt: *"A skipped check is not a neutral check. It reports green because it did
not look — a false negative wearing a checkmark."*

There is one further fact, and it is measured rather than argued. The coverage gate
is `fail_under = 90` with `branch = true` over `src`. The baseline measured on this
branch before any Stage 2.3 code existed:

```
TOTAL     606     1     76     1    99%
Required test coverage of 90.0% reached. Total coverage: 99.71%
```

The Postgres adapters, mappers and tables of this Stage add a few hundred statements
whose **only** coverage comes from integration tests.

## Decision

Integration tests require a reachable Postgres, symmetrically, in every environment
that runs `make check`:

1. `.github/workflows/ci.yml` gains a `services: postgres` (postgres:16-alpine) on
   the `lint-and-test` job, with a health check, and `DATABASE_URL` passed through
   `env:` — not through a command-line argument, preserving I3.
2. Locally, the database comes from the already-enabled `postgres` service in
   `docker-compose.yml` (`make docker-up`).
3. When the database is unreachable, the session-scoped fixture **fails with an
   actionable message**. It never calls `pytest.skip`. There is no environment
   variable that turns the requirement off, because such a variable is exactly the
   lever that would eventually be set on the runner.
4. `tests/unit/test_ci_workflow.py` — the existing home for CI invariants whose
   breakage is silent — gains assertions that the gate job declares the Postgres
   service and exports `DATABASE_URL`. Deleting the service turns `make check` red
   locally, the same way `fetch-depth: 0` is protected today.

## Alternatives considered

### Alternative A — Skip locally when the DB is unreachable, require it in CI via a guard variable
- **Description:** the fixture skips when it cannot connect, unless
  `REQUIRE_INTEGRATION_DB=1` is set; `ci.yml` sets it. The asymmetry is explicit and
  covered by a workflow test.
- **Pros:** a developer without Docker can still run `make check`; the asymmetry is
  the shape the Stage brief explicitly contemplated; it fits ADR 1.2.0001's
  "**decided** degradation" category, since the coverage is relocated to CI rather
  than nowhere.
- **Cons:** **it does not deliver the green local run it promises.** With the
  integration tests skipped, the Stage's adapter files contribute several hundred
  uncovered statements against a 606-statement baseline, so `fail_under = 90` fails
  anyway. The developer without a database does not get a passing gate — they get a
  confusing coverage failure instead of a message saying "start Postgres". To
  actually deliver a green local run, the adapters would have to be excluded from
  coverage when skipped, which is the myopic gate this Stage exists to avoid.
  It also introduces a switch whose only job is to disable a safety check.
- **Why rejected:** it buys a real cost (a disable lever, an asymmetry to keep
  tested) for a benefit that the coverage arithmetic shows is illusory.

### Alternative B — Run integration tests against SQLite in-memory
- **Description:** keep the template's `test_engine` fixture and point the adapters
  at SQLite, so no service is needed anywhere.
- **Pros:** zero infrastructure; fast; works on any machine.
- **Cons:** the schema of this Stage carries its invariants **in the database**: a
  `CHECK` expressing the platform-admin iff, a composite foreign key anchoring the
  denormalised tenant discriminator, `TIMESTAMP WITH TIME ZONE` round-tripping, and
  named constraints whose names the adapter reads to translate `IntegrityError` into
  domain exceptions. SQLite's behaviour differs on every one of those points. Tests
  would pass against a database that is not the one in production — a green that
  means less than no test at all, because it inspires confidence.
- **Why rejected:** it validates the wrong artefact. The roadmap DoD is explicit:
  "testes de integração e de contrato verdes contra Postgres real (docker)".

### Alternative C — Mark integration tests `slow` and exclude them from `make check`
- **Description:** `test-gate` runs `-m "not integration"`; a separate target runs
  the rest.
- **Pros:** the fast loop stays fast; no service needed for the common path.
- **Cons:** breaks invariant I3 — the CI step would need an argument or a different
  target, and the runbook's transitivity argument stops holding. It also relocates
  the coverage of the adapters to a target that nothing enforces, which is ADR
  1.2.0001's "coverage relocated to **nowhere**".
- **Why rejected:** it converts a blocking gate into an optional one silently.

### Alternative D — Do nothing / status quo
- **Description:** add integration tests, leave `ci.yml` alone.
- **Why rejected:** CI goes red on every PR from this Stage onward, or the tests
  quietly skip. The Stage brief names this as the gap to close.

## Consequences

### Positive
- The gate keeps its teeth: there is no code path where the suite is green without
  having exercised the database, so the failure mode of ADR 1.2.0001 cannot recur
  through this door.
- Local and CI stay symmetric, so `validate-ci-gate.md`'s transitivity argument
  survives intact — one fewer exception to reason about.
- The error message on a missing database is actionable ("run `make docker-up`"),
  which is strictly better than the coverage failure Alternative A would produce.

### Negative
- `make check` now requires Docker running locally. This is real friction for a
  Windows-native workflow (ADR 1.1.0001), and it is the cost being accepted. It is
  bounded: `docker-compose.yml` already ships the service enabled and `make
  docker-up` is a single command; Docker was already a day-one dependency of the
  project per CLAUDE.md.
- CI jobs get slower by the time it takes Postgres to become healthy (seconds).

### Neutral / trade-offs accepted
- A developer who genuinely cannot run Docker can still run `make lint`,
  `make typecheck` and the unit subset directly; what they cannot do is claim the
  full gate passed. That is the intended semantics, not a gap.
- If a future Stage needs a second service (Redis), it follows this same shape:
  service in `ci.yml`, loud failure when absent, invariant asserted in
  `test_ci_workflow.py`.

## Implementation notes

- The fixture lives in `tests/integration/conftest.py` and is session-scoped; it
  applies the Alembic migration once and truncates between tests.
- `docs/runbooks/validate-ci-gate.md` §Maintenance requires this hardening to be
  documented there in the same Stage — a new error class covering "integration test
  fails" plus the environment precondition for the class.

## References

- Related ADRs: [ADR 1.2.0001](./1_2_0001-deterministic-pr-path-gates.md) (gate
  degradation taxonomy), [ADR 1.1.0001](./1_1_0001-windows-native-dev-environment.md)
  (the Windows-native cost being weighed)
- Runbook: [`../runbooks/validate-ci-gate.md`](../runbooks/validate-ci-gate.md)
- Stage 1.2 concept, invariants I1–I5: [`../stages/1.2-ci/concept.md`](../stages/1.2-ci/concept.md)

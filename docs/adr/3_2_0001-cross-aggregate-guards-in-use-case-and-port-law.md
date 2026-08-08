---
title: ADR 3.2.0001 — Cross-aggregate guards live in the use case AND as a declared law of the out port
description: Architecture Decision Record
when-use: Reference when implementing or changing the job-function uniqueness, removal or referential-validity guards (Stages 3.2–3.4), when writing the staff repository fakes, or when the Postgres adapter of Stage 3.3 translates an integrity error
keywords: [adr, staff, application, port, guard, uniqueness, check-then-act, fake, contract-test, concurrency, referential-integrity]
status: accepted
created_at: 2026-08-08
updated_at: 2026-08-08
adr_id: 3.2.0001
decision: Each cross-aggregate rule delegated by Stage 3.1 is enforced twice — anticipated by the use case with an explicit port query, and declared as a named law of the out port (add/update/delete raise the corresponding error) binding both the in-memory fakes and the Postgres adapter of Stage 3.3; the fakes are a coupled pair over a single store, because the laws span aggregates, and each rule's honest concurrency guarantee is stated rule by rule.
context_stage: 3.2-staff-application
bounded_context: staff
---

# ADR 3.2.0001 — Cross-aggregate guards in the use case and as port law

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 3.1 modelled the staff domain and **declared invariants it could not enforce**, because each
one crosses aggregate boundaries — no single entity can decide them (concept 3.1 §5, invariants 3,
10 and 11). Mapping them precisely (the earlier "three rules in §5.3/§5.10/§5.11" shorthand was
wrong — invariant 10 held **two** rules and invariant 11 delegated a fourth):

| Concept 3.1 | Rule delegated to Stage 3.2 |
|---|---|
| invariant 3 | Job-function name is unique within the tenant (verbatim). |
| invariant 10, first half | An inactive function accepts no NEW assignment. |
| invariant 10, second half | Definitive removal of a function only when no employee references it. |
| invariant 11 | Referential validity: every id of `job_function_ids` exists in the tenant. |

[ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) (sponsor, 2026-08-08) **removed
the job-function lifecycle**, so the second row no longer exists. Three rules remain, and — this is
the point worth recording — the rule that disappeared was the **only one of the four that was pure
check-then-act with no possible port law**, because the state it consulted did not participate in
any write.

ADR 3.1.0003 had already fixed *which layers* own the guards ("enforced in the application layer
(Stage 3.2), backed by the persistence constraint (Stage 3.3)"); that allocation survives its
supersession. What it did **not** fix is *how* the application layer states the rule — the decision
this ADR records, because the shape chosen here is the specification Stage 3.3 implements.

Forces:

- A check inside a use case is **check-then-act**: correct in the common case, unsound under
  concurrency. Two requests can both read "name is free" before either writes.
- The precedent is documented and painful. Stage 2.2 put the uniqueness check only in
  `CreateUserUseCase`; the in-memory fake silently overwrote what Postgres rejects, and Stage 2.3
  had to retrofit the port contract with a family of `*AlreadyExists` errors
  ([ADR 2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md)). The divergence was invisible until
  the first real adapter existed.
- The fakes written in this Stage are the **executable specification** the contract tests of
  Stage 3.3 parametrize. A law that is not in the port is a law the fake will not have, and
  therefore a law the contract test cannot check.
- A guard living *only* in the database surfaces as a raw `IntegrityError`, which the application
  layer must not know how to read — and which the HTTP layer would turn into a 500.
- Two of the three laws speak about data that lives in **the other aggregate's** store. A fake built
  as an isolated dictionary literally cannot implement them.

## Decision

Every remaining cross-aggregate rule is enforced in **two places, on purpose**, and the laws are
**named** so acceptance criteria and contract tests can reference them individually:

1. **In the use case**, by an explicit query to the out port before acting — `find_by_name` for
   uniqueness, `exists_by_job_function` for the removal guard, `find_all_by_ids` for referential
   validity. This produces the precise, well-worded error in the common case, and keeps the rule
   readable where the business operation lives.
2. **As a declared law of the out port**, documented in the `Protocol` docstring and binding on
   every implementation: `add` is insert-not-upsert (L-JF1/L-E1), `update` is UPDATE-not-upsert
   (L-JF2/L-E2), `JobFunctionRepository.delete` refuses a referenced function (L-JF3),
   `EmployeeRepository.add`/`update` refuse a set containing an unknown function id (L-E4), and
   `EmployeeRepository.update` refuses to relocate a record (L-E3). The full list lives in the Stage
   3.2 concept §4.

**The fakes are a coupled pair, not two dictionaries.** `InMemoryJobFunctionRepository` and
`InMemoryEmployeeRepository` are **views over a single injected store**
(`InMemoryStaffStore`), because L-JF3 needs employee data to answer and L-E4 needs function data to
answer. A pair built over two different stores is a test error, not a valid configuration. **Stage
3.3's contract test parametrizes the pair** (fake-pair × Postgres-adapter-pair), not one repository
at a time — the cross-aggregate laws are only verifiable over the pair, and that fixture shape is
part of what this Stage hands downstream.

**The guarantee is stated rule by rule, not claimed uniformly:**

| Rule | Use-case check | Port law | Honest limit under concurrency |
|---|---|---|---|
| Name unique in tenant | `find_by_name` | L-JF1 / L-JF2 | **Closed.** Fake enforces in the store; Stage 3.3 in the unique index `(tenant_id, name)`. The loser of a race gets the **same exception type**, raised by the port instead of the use case — indistinguishable to Stage 3.4, and it must stay that way |
| Removal only when unreferenced | `exists_by_job_function` | L-JF3 | **Closed only in Stage 3.3**, by the `RESTRICT` FK. Here the coupled fake closes it by construction, which is a *simulation* of the FK — faithful in behaviour, not in atomicity |
| Referential validity of the set | `find_all_by_ids` | L-E4 | **Closed only in Stage 3.3**, by the same FK. The law's value in this Stage is to fix the **error type** of the race: the adapter translates `IntegrityError` into `JobFunctionNotFoundError`, which the contract already declares, instead of surfacing an unforeseen error as a 500 |

## Alternatives considered

### Alternative A — Guard only in the use case
- **Description:** the use case queries and decides; the port is a dumb store.
- **Pros:** one place to read the rule; simplest port; the fakes stay independent dictionaries.
- **Cons:** check-then-act race; the fake accepts what Postgres will reject, so the whole unit
  suite can be green over a state the real system cannot hold; the divergence is only discovered
  in Stage 3.3, exactly as happened in 2.2 → 2.3. Specifically for L-E4, the undeclared race
  reaches Stage 3.4 as a **500**, because the error the adapter raises is not in any contract.
- **Why rejected:** the project already paid this cost once and recorded the lesson in
  ADR 2.3.0003.

### Alternative B — Guard only in persistence (constraint + error translation)
- **Description:** no query in the use case; let the unique index and the `RESTRICT` FK fail, and
  translate.
- **Pros:** single source of truth; no race.
- **Cons:** the rule becomes invisible in the layer that owns the business operation; error
  messages degrade to whatever the constraint name suggests; the fake would have to reimplement
  the constraint anyway to keep unit tests meaningful — which is the port law by another name;
  and the removal guard would need the FK to exist before any use case could be tested (Stage 3.3
  is downstream).
- **Why rejected:** it hides business rules in infrastructure and makes Stage 3.2 untestable on
  its own terms.

### Alternative C — Guard in the domain entity
- **Description:** teach `JobFunction`/`Employee` to validate against the rest of the tenant.
- **Pros:** the invariant would hold "by construction".
- **Cons:** impossible without I/O — the entity would need to query other aggregates, breaking
  domain purity (LAYOUT §3) and the `staff-domain-purity` import contract. This is precisely why
  Stage 3.1 declared and delegated instead of enforcing.
- **Why rejected:** contradicts the hexagonal boundary the project enforces mechanically.

### Alternative D — Port laws, but independent fakes (cross-aggregate laws left unimplemented)
- **Description:** declare L-JF3/L-E4 in the `Protocol` docstrings, but let each fake hold its own
  dictionary and simply not enforce the laws it cannot see.
- **Pros:** the simplest fakes; each one testable alone.
- **Cons:** a declared-but-unimplemented law is worse than no law — the concept would claim a
  guarantee the unit suite never exercises, and the first implementation to honour it would be the
  Postgres adapter, i.e. the divergence would again be discovered downstream. It also leaves Stage
  3.3 without a fixture shape for the contract test.
- **Why rejected:** it reproduces the 2.2 → 2.3 defect with better documentation.

### Do nothing / status quo
Not viable: the rules are declared invariants of an accepted domain doc; leaving them unowned in
3.2 is the exact risk the Stage 3.1 concept flagged in its §10.

## Consequences

### Positive
- Fake and real adapter answer the same thing to the same scenario, and the contract test of
  Stage 3.3 can prove it — over the **pair**, which is the only level at which the cross-aggregate
  laws exist.
- The race window of check-then-act stops at a typed domain error instead of a 500.
- Stage 3.3 receives a written specification (named laws) rather than an inferred one.
- The per-rule table makes the *remaining* risk explicit, so Stage 3.3 knows which two laws it must
  back with a real constraint and which one is already sound.

### Negative
- Each rule is written twice (use case + port law), so a change to a rule has two edit sites.
- The fakes are heavier than a dictionary — they carry uniqueness, reference and referential logic,
  and they are coupled through a shared store, which is more setup in every test module.

### Neutral / trade-offs accepted
- The double enforcement means the use-case check is, strictly, an optimization for error quality.
  That is accepted deliberately: the message the manager reads is part of the product.
- Under concurrency the caller may receive the port-level error instead of the use-case-level one.
  Both are the **same exception type**, so callers (Stage 3.4) cannot tell — and must not need to.
- The coupled store makes the fake pair a small in-memory database. That is a known cost of this
  shape and the reason the pair is built by an explicit constructor rather than assembled ad hoc.

## Implementation notes

- Stage 3.2: laws documented (with their L-* names) in the `Protocol` docstrings of
  `features/staff/application/ports/out/{job_function_repository,employee_repository}.py`;
  fakes in `tests/fakes/features/staff/` — `InMemoryStaffStore` plus the two repository views —
  implement them and are tested directly, law by law.
- Stage 3.3: unique index `(tenant_id, name)` on the function table; FK employee→function with
  `RESTRICT`; adapter translates `IntegrityError` into the same exception types; contract test
  parametrizes the **pair**.

## References

- Related ADRs: [ADR 3.2.0005](./3_2_0005-job-function-has-no-lifecycle-state.md) (removed the
  fourth rule); [ADR 3.1.0003](./3_1_0003-job-function-lifecycle-soft-state.md) (`superseded`, but
  the layer allocation of the guards originates there);
  [ADR 3.1.0006](./3_1_0006-employee-function-set-cardinality.md) (per-id validation);
  [ADR 2.3.0003](./2_3_0003-add-is-insertion-not-upsert.md) (precedent and lesson);
  [ADR 2.3.0005](./2_3_0005-names-persisted-verbatim.md) (verbatim storage).
- [`docs/stages/3.1-staff-domain/concept.md`](../stages/3.1-staff-domain/concept.md) §5 (invariants
  3, 10, 11), §10; [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md) §3.2.
- [`docs/stages/3.2-staff-application/concept.md`](../stages/3.2-staff-application/concept.md) §4
  (the named laws), end of §5 (the per-rule guarantee table).
- Skill `pytest-with-fakes` (fake as executable specification; contract tests).

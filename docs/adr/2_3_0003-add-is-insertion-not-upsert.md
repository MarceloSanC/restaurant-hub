---
title: ADR 2.3.0003 — add() is insertion, not upsert, in all four identity repositories — the fakes are corrected to match the ports
description: Architecture Decision Record
when-use: Reference when a fake and a real adapter disagree, before relaxing a fake to make a test pass, or when adding an error to the identity application error hierarchy
keywords: [adr, contract-test, fake, upsert, insertion, repository, integrity-error, primary-key, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.3.0003
decision: All four in-memory identity repository fakes stop silently overwriting an existing key and instead raise a dedicated AlreadyExists error mirroring what the Postgres primary key enforces (with a separate error for refresh-token fingerprint reuse), and the Stage 2.2 test asserting the opposite is inverted because it encoded a behaviour its own port forbids
context_stage: 2.3-identity-persistence
bounded_context: identity
---

# ADR 2.3.0003 — `add()` is insertion, not upsert, in all four identity repositories

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.2 shipped six out-ports together with in-memory fakes that are, by explicit
design, "a especificação executável" of those ports. Stage 2.3 implements the same
ports against Postgres, and contract tests exist to prove the two agree.

The `UserRepository.add` docstring is unambiguous:

> **É inserção, não upsert.** E-mail já registrado levanta
> `EmailAlreadyRegisteredError` […] Sem essa regra no contrato, o fake sobrescreveria
> em silêncio e o Postgres levantaria — divergência que só apareceria no teste de
> contrato da 2.3.

The other three ports say the same thing in weaker words — "Persiste um restaurante
**novo**", "Persiste uma unidade **nova**", "Persiste uma sessão **recém-criada**".

**All four fakes violate it.** Each one writes with a plain assignment:

```python
# in_memory_restaurant_repository.py
def add(self, restaurant: Restaurant) -> None:
    self.restaurants[restaurant.id] = restaurant

# in_memory_unit_repository.py
def add(self, unit: Unit) -> None:
    self.units[unit.id] = unit

# in_memory_session_repository.py
def add(self, session: Session) -> None:
    self.sessions[session.id] = session
```

`InMemoryUserRepository.add` is subtler: it *does* raise
`EmailAlreadyRegisteredError` when an email belongs to a **different** user, but its
guard is `existing is not None and existing != user.id`, so re-adding the **same**
`user_id` silently overwrites — including overwriting the password hash. Stage 2.2
then wrote a test pinning that behaviour:

```python
def test_regravar_o_mesmo_usuario_nao_e_conflito_de_email() -> None:
    """O conflito é entre usuários distintos — o mesmo id pode ser regravado."""
    repo.add(user, _HASH)
    repo.add(user, _HASH)
    assert repo.find_by_id(UserId("user-1")) == user
```

Against Postgres every one of these tables has a primary key, so the second `add`
raises `IntegrityError`. This is a genuine conflict of sources: a **test** from 2.2
contradicts the **port contract** from 2.2.

The Stage brief flagged the `UserRepository` half of this as the most important
inherited finding. Checkpoint A established that it is not a `UserRepository` problem
— it is the same defect in four places, and fixing only one would leave the contract
test proving far less than it appears to.

## Decision

The ports are right; the fakes and the test are wrong.

1. **All four fakes raise on a duplicate primary key.** `add` checks the key before
   writing, in every repository.
2. **Five new errors** join `application/errors.py`, all subclasses of
   `IdentityError`: `RestaurantAlreadyExistsError`, `UnitAlreadyExistsError`,
   `UserAlreadyExistsError`, `SessionAlreadyExistsError` and
   `SessionFingerprintAlreadyExistsError`. They are symmetric with the three
   `*NotFoundError` classes the module already has, so the hierarchy stays predictable
   rather than acquiring special cases.
3. **One error per violation, not one per table.** `UserAlreadyExistsError` is distinct
   from `EmailAlreadyRegisteredError` because the two describe different violations and
   Stage 2.4's HTTP mapping will want to tell them apart. The same reasoning forces
   `sessions` to have two: a duplicate **id** is a collision, while a duplicate
   **fingerprint** is the refresh-token-reuse signal that ADR 2.2.0001 exists to make
   detectable. Collapsing them into one class would hand Stage 2.4 a single error for
   a benign collision and a possible stolen token — the one distinction the session
   design is built around.
4. **The Postgres adapters translate by constraint name** — primary-key violation to
   the matching `*AlreadyExistsError`, `uq_users_email` to
   `EmailAlreadyRegisteredError`, `uq_sessions_fingerprint` to
   `SessionFingerprintAlreadyExistsError` — relying on the explicit constraint names
   from [ADR 2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md).
5. **`test_regravar_o_mesmo_usuario_nao_e_conflito_de_email` is inverted**: re-writing
   the same user now raises. Its docstring records why the expectation flipped.
6. **No port signature changes.** Nothing in Stage 2.2's application layer or use
   cases is affected — the only behaviour that changes is a case that was previously
   undefined in practice.

All four errors subclass `IdentityError`, preserving Stage 2.2's invariant #16 (every
error reachable from a use case is an `IdentityError`, so nothing becomes an
accidental 500 — ADR 2.2.0003).

## Alternatives considered

### Alternative A — Relax the real adapters to upsert, matching the fakes
- **Description:** `INSERT … ON CONFLICT (id) DO UPDATE` in each repository.
- **Pros:** no test changes; the fakes stay as they are; `add` becomes idempotent,
  which is convenient for retries.
- **Cons:** it contradicts the ports' stated contract in writing. For `users` it
  silently changes which credential an account authenticates with — a second `add`
  would overwrite the password hash with no error, which the port docstring calls out
  as the very reason the rule exists. For `sessions` it would let a re-issued session
  id quietly replace an existing session's revocation state.
- **Why rejected:** it resolves a contradiction by demoting the contract to match the
  weakest implementation — the direction that loses information every time.

### Alternative B — Fix only `UserRepository` (the finding as originally scoped)
- **Description:** treat it as the `users` problem the Stage brief described.
- **Pros:** smallest diff; addresses the case that was actually flagged; the other
  three duplicates are arguably unreachable in production since ids come from
  `Uuid4Generator`.
- **Cons:** the contract test would then assert insertion semantics for one of four
  repositories and silently assert nothing for the other three, while *looking* like
  a complete fake≡real proof. That is a worse outcome than not testing it, because it
  manufactures confidence. The unreachability argument applies equally to `users`, so
  it cannot justify treating them differently.
- **Why rejected:** partial coverage presented as complete coverage is the failure
  mode this project keeps legislating against.

### Alternative C — One shared `AlreadyExistsError` for all four
- **Description:** a single error class carrying the entity name as a field.
- **Pros:** one class instead of four; less to maintain.
- **Cons:** breaks symmetry with the existing `RestaurantNotFoundError` /
  `UnitNotFoundError` / `UserNotFoundError` trio, so the module would have two
  different conventions for the same shape of problem; and it makes Stage 2.4's
  handler registration coarser, since Starlette dispatches on exception type.
- **Why rejected:** the existing hierarchy already chose per-entity classes; matching
  it costs three extra classes and keeps the module predictable.

### Alternative D — Let duplicates raise a raw `IntegrityError` in both fake and real
- **Description:** treat it as a programming error, not a business error.
- **Pros:** arguably honest — ids come from uuid4, so a collision really does mean a
  bug, and a 500 is a defensible response to a bug.
- **Cons:** breaks invariant #16 of Stage 2.2, and forces the in-memory fakes to
  import or fabricate a SQLAlchemy exception type purely to stay equivalent —
  coupling dependency-free test doubles to the database driver.
- **Why rejected:** the coupling cost lands on the fakes, which exist precisely to be
  free of it.

### Alternative E — Do nothing / status quo
- **Description:** ship the contract test with an exemption for `add`.
- **Why rejected:** the exemption would be the first crack in "fake ≡ real", and the
  contract test was commissioned in Stage 2.2 specifically to catch this.

## Consequences

### Positive
- Fake and real adapter agree on `add` in all four repositories — the property Stage
  2.2 deferred to this Stage is actually delivered, not partially delivered.
- The fakes stop being *more permissive* than production, which is the failure mode
  that makes fakes dangerous: tests pass locally and behaviour differs live.
- Stage 2.4 gets distinguishable errors to map to distinguishable HTTP responses.

### Negative
- A merged, passing test from Stage 2.2 is inverted, and three fakes on `develop`
  change behaviour. This is a deliberate change to work already merged. It is recorded
  here, and the Stage's execution **will** record in §7 of `technical.md` the exact
  list of tests that had to change — `test_repository_fakes.py` and
  `test_session_repository_fake.py` together hold 21 `add(...)` call sites, and which
  of them break is a fact of execution, not something this ADR can assert in advance.
- Five new classes in the identity error hierarchy.

### Neutral / trade-offs accepted
- Re-adding an existing key is not a scenario production reaches today (ids come from
  `Uuid4Generator`), so the practical blast radius is limited to tests and to future
  callers that construct ids themselves. The value is in the contract being coherent,
  not in the case being frequent.
- Duplicate `UnitMembership` values passed to `UserRepository.add` are likewise
  rejected (composite primary key), matching the fake once it stops using `extend`.
  Stage 2.2's use case already deduplicates `unit_ids` (invariant #15), so no
  production path regresses.

## Implementation notes

- Fake `UserRepository`: guard on `user.id in self.users` **before** the email check,
  so re-adding the same user raises `UserAlreadyExistsError` rather than the email
  error.
- Adapters: match `IntegrityError.orig` against the named constraints (`pk_users`,
  `uq_users_email`, `pk_sessions`, `uq_sessions_fingerprint`, …) — see ADR 2.3.0002
  for why the names are explicit.
- Contract test: one shared body asserting the duplicate-key error, parametrised over
  each fake and its Postgres counterpart.

## References

- Related ADRs: [ADR 2.2.0003](./2_2_0003-application-errors-in-identity-hierarchy.md)
  (why every error is an `IdentityError`),
  [ADR 2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md) (named
  constraints enabling the translation)
- Port contracts: `src/restaurant_hub/features/identity/application/ports/out/`
- Superseded expectation: `tests/unit/features/identity/application/test_repository_fakes.py::test_regravar_o_mesmo_usuario_nao_e_conflito_de_email`

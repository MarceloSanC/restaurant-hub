---
title: ADR 2.6.0001 — Identity gets a UnitOfWork out port whose Postgres adapter shares one connection with the repositories through a context variable keyed by engine, with a savepoint per repository call
description: Architecture Decision Record
when-use: Reference before adding a write to an identity use case that already writes, before changing how an identity repository obtains its connection, before introducing a unit of work in another bounded context, or when revisiting concept 2.3 §7 Decision 6
keywords: [adr, unit-of-work, transaction, atomicity, contextvar, savepoint, sqlalchemy, identity, port, repository, fail-closed]
status: accepted
created_at: 2026-10-19
updated_at: 2026-10-19
adr_id: 2.6.0001
decision: identity publishes a `UnitOfWork` out port in `features/identity/application/ports/out/` with one method, `transaction()`, a context manager that commits on clean exit and rolls back on exception, is not reentrant, and is opened by the use case around exactly the writes that must be atomic; the Postgres adapter keeps the repository constructors as they are (`Engine`) and shares the unit's connection with them through a `ContextVar` keyed by the engine, each repository call inside a unit running in its own savepoint so that the fake and the real adapter agree on what a failed call leaves behind
context_stage: 2.6-identity-unit-of-work
bounded_context: identity
---

# ADR 2.6.0001 — Identity `UnitOfWork`: port, ambient connection, savepoint per call

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

**Supersedes, for identity, concept 2.3 §7 Decision 6** ("one transaction per
public repository method, no Unit of Work port — it would be a contract without a
consumer"). The reason given there no longer holds: five identity use cases now
write more than once per request (see ADR 2.6.0002), and the 2.4 and 3.5 findings
escalated their atomicity explicitly. The rest of Decision 6 — `Engine` injected,
session pinned to UTC, one transaction per public method **outside** a unit —
remains in force. Staff is not affected (ADR 2.6.0002 §2); ADR 3.3.0006 stands as
written.

## Context

Facts measured on `develop` at `2c71615`:

- Seven Postgres repositories (five in identity, two in staff) receive an `Engine`
  and open `engine.begin()` / `engine.connect()` in every public method. Most
  delegate to a private helper that takes a `Connection`, marked as "the swap
  point for a future UoW" (restaurant, unit, user and session repositories, e.g.
  `restaurant_repository.py:55`; the setup-token repository has no such helper). The module docstring
  (`:14-18`) foresaw the swap as a **constructor change** ("passar a aceitar uma
  `Connection` de fora vira uma mudança de construtor"); this ADR departs from that
  plan — Alternative B says why.
- Use cases and repositories are built **once** in `wire_dependencies` and shared
  by every concurrent request (`composition_root.py:480-690`); FastAPI runs the
  sync endpoints in its threadpool.
- `SetPasswordWithTokenUseCase` performs four writes over three repositories with
  no enclosing transaction; its docstring points the debt at Stage 4.4, whose
  scope (scheduling persistence) cannot hold it (issue #46).
- `application/` may not import SQLAlchemy (`identity-application-purity`,
  `check_layout.py` rule 2).
- Ports are synchronous (ADR 2.2.0004).

Two forces shape the decision beyond "add a transaction":

1. **Where the boundary is drawn is use-case knowledge.** `RefreshSessionUseCase`
   must *commit* the mass revocation of the reuse path and then raise; the
   e-mail of `InviteUserUseCase` must leave *after* the commit, never inside it
   (ADR 2.6.0002 §3). A boundary placed from outside the use case cannot express
   either.
2. **The fake must be able to tell the same story as Postgres.** Issue #46
   requires the fake and the real unit to pass one contract suite. A Postgres
   transaction in which a statement failed is *aborted*: every later statement
   fails, and `COMMIT` silently becomes `ROLLBACK`. An in-memory fake has no such
   state. Either the contract encodes the poisoning (and the fake simulates it) or
   the real adapter removes it.

## Decision

**1. The port.** `features/identity/application/ports/out/unit_of_work.py`:

```python
class UnitOfWork(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...
```

Laws, each pinned by the contract suite (fake × Postgres):

- **L1 — all or nothing.** Every repository write performed inside the block is
  made durable if the block exits normally, and none is if it exits by exception.
- **L2 — the exception passes through unchanged.** The unit never translates,
  wraps or swallows what left the block: the caller receives the **same object**
  (`is`). Exception: if the rollback itself fails, its error surfaces (chained to
  the original) — the connection is lost either way.
- **L3 — a failed call leaves nothing of its own and does not poison the unit.**
  A repository call that raises inside the block has no effect of its own; the
  writes before it are still pending, and the block's exit decides their fate.
- **L4 — reads inside the block see the block's own writes.**
- **L5 — not reentrant.** Opening `transaction()` while one is open in the same
  execution context raises `RuntimeError` before touching anything — observable as
  no connection checked out of the pool and no new state published.
- **L6 — outside a block nothing changes.** Each repository call is its own
  transaction, exactly as before this Stage.

**2. The use case opens the block, around the writes only.** It receives the port
by constructor, like any other out port, and writes
`with self._unit_of_work.transaction():` around the writes that must be atomic.
Reads and checks that decide whether to write stay before it; CPU work (password
hashing) happens before it; side effects that cannot be rolled back (e-mail)
happen after it.

**3. The Postgres adapter: ambient connection keyed by engine.** A module in
`features/identity/adapters/out/postgres/` holds a
`ContextVar[tuple[Engine, Connection] | None]`. `PostgresUnitOfWork(engine)`
opens `engine.begin()`, publishes `(engine, connection)` and resets it in
`finally`. The repositories replace `engine.begin()` / `engine.connect()` by two
helpers of that module: when a unit is active **for the same engine**, they run
on its connection inside `connection.begin_nested()` (a `SAVEPOINT`; released on
success, rolled back to on exception — SQLAlchemy 2.0.51
`engine/base.py:867`, `:2771`); otherwise they open their own transaction as
today. Repository constructors do not change.

The context variable is safe under the threadpool: on the asyncio backend (the
one uvicorn runs), anyio 4.14.1 runs every `to_thread.run_sync` call inside a
fresh `copy_context()` of the caller's context
(`anyio/_backends/_asyncio.py:2588`, executed at `:1029`); Starlette's
`run_in_threadpool` delegates to it (`starlette/concurrency.py:32-34`), and
FastAPI runs sync endpoints and sync dependencies through it
(`fastapi/routing.py:343-346`, `fastapi/dependencies/utils.py:677-680`). No unit
is ever open in the event loop's context, so the copy starts empty of units; two
requests never share the variable, and the `finally` reset keeps a worker thread
clean even if they did. The trio backend was not checked — the project does not
run it.

**4. The fake** (`tests/fakes/features/identity/in_memory_unit_of_work.py`)
receives the in-memory repositories it guards. A table in the fake's own module
**declares**, per in-memory repository class (resolved through the MRO, so fault
injector subclasses inherit it), which attributes are persisted state (the dicts
and lists that stand for rows — not call counters, not fault-injection flags or
logs); guarding a repository with no entry raises at construction. The fake
snapshots exactly those on entry and, on exception, restores them **in place**
(`clear` + `update`/`extend`), so a reference a test took to the dict stays
valid and a fault injector's log survives the rollback. L3 holds for the fake
because the in-memory repositories validate before they mutate — which this
Stage pins by asserting the unchanged state after every duplicate refusal in the
identity contract suite (until now those tests asserted only the `raises`). L5 is
implemented with a module-level `ContextVar` in the fake as well, so nesting two
distinct fake units raises as it does in Postgres.

**5. Isolation stays `READ COMMITTED`.** The anti-replay lock of
`PasswordSetupTokenRepository.consume` is a conditional `UPDATE … WHERE
consumed_at IS NULL`; inside a unit the row lock is held until commit, and a
concurrent redemption waits and then re-evaluates the predicate against the
committed row. This is measured by an integration test with two threads, not
assumed.

## Alternatives considered

### Alternative A — Port in `shared/application/ports/out/`
- **Description:** the location issue #46 suggests first.
- **Pros:** the next bounded context that needs a unit finds it ready.
- **Cons:** only identity consumes it (ADR 2.6.0002 §2). LAYOUT §4 says reuse is
  measured, not predicted, and `check_dead_shared.py` exists because two shared
  names lived six Stages without a consumer. The port is also cheap to move: one
  `Protocol`, no state.
- **Why rejected:** [decision:C] rung 1 — the project already ratified the rule
  (LAYOUT §4, issue #45). LAYOUT outranks the issue text.

### Alternative B — Unit of Work owns the repositories (*Cosmic Python* shape)
- **Description:** `with uow_factory() as uow: uow.tokens.consume(...)`; the
  repositories are built per unit on its connection; use cases receive the factory
  instead of the repositories.
- **Pros:** no ambient state; the connection travels explicitly; a repository
  cannot run outside a unit by accident.
- **Cons:** every identity use case and its tests change constructor shape,
  including the six that write once; repositories become per-request objects while
  the composition root builds everything once, so every use case would need a
  factory instead of instances. The atomicity gained is identical.
- **Why rejected:** [decision:C] rung 4 — same guarantee at several times the
  surface, and a shape change that a later Stage could still adopt behind the same
  port if ambient state ever becomes a problem.

### Alternative C — Wrap `execute` from outside the use case (decorator)
- **Description:** a wrapper instantiated by the composition root runs each
  multi-write use case's `execute` in a transaction; the use case knows nothing.
  (Issue #46's "context manager delivered by the composition root" is read here
  as the chosen design — the root delivers the port, the use case opens it — not
  as this alternative.)
- **Pros:** zero change in `application/`.
- **Cons:** the boundary becomes the whole `execute`. The reuse path of
  `RefreshSessionUseCase` would roll back the very revocation it exists to commit
  (it raises after revoking); the e-mail of `InviteUserUseCase` would be sent
  inside a transaction that may still roll back, mailing a link to a token that
  does not exist; password hashing would run inside the lock window.
- **Why rejected:** [decision:E] — the two use-case behaviours above are
  measurable consequences.

### Alternative D — No savepoint; the failed call poisons the unit
- **Description:** run repository calls directly on the unit's connection; the
  contract states that any exception inside the block dooms it.
- **Pros:** fewer round trips.
- **Cons:** a use case that catches a translated repository error and continues
  inside the block would commit an aborted transaction, which Postgres turns into
  a silent `ROLLBACK` — writes reported as done and not done. The fake cannot
  reproduce that without wrapping every fake repository. Fail-open by default.
- **Why rejected:** [decision:C] rung 2 — the unit guards credential writes; the
  fail-closed option wins, and it is also the one where fake and real agree
  without special machinery.

### Alternative E — Do nothing (keep the fail-closed ordering)
- **Description:** the status quo; every partial failure leaves the account
  *more closed*.
- **Cons:** it is an argument of ordering, not atomicity. Measured consequences
  today: a failed password set burns the link; a failure between `revoke` and
  `add` in session rotation leaves the client with a revoked refresh token, whose
  retry is then classified as **reuse** and revokes every session of the user; a
  failure between `users.add` and `tokens.add` leaves an account no link can open,
  whose re-invitation answers 409.
- **Why rejected:** those are the findings escalated by Stages 2.4 and 3.5.

## Consequences

### Positive
- A failed write in any of the five use cases leaves the database as it was:
  the setup link survives a failed redemption, a failed rotation leaves the old
  refresh token valid instead of turning a retry into a reuse alarm, and no
  account is born without its token.
- Repository constructors and the persistence ports are untouched (except the
  additive `revoke -> bool` of ADR 2.6.0002 §1b); staff production code is
  untouched.
- The fake and Postgres agree on the unit by contract, not by assumption.

### Negative
- Ambient state: a repository wired with a different `Engine` than the unit
  ignores the unit silently. Mitigated by a bootstrap test that pins the identity
  of the engine shared by the unit and the repositories.
- Each repository call inside a unit costs a `SAVEPOINT` / `RELEASE` pair.
- Locks now span statements: two units of the same user (an invitation and a
  reset link redeemed at the same time) can deadlock; Postgres aborts one with
  `40P01`, which rises as `OperationalError` (500) and rolls back whole — safe,
  rare, declared.
- A `COMMIT` lost with the connection is in doubt: it may have happened. It
  rises raw; the application cannot know.
- **Concurrent refresh rotation:** with the revocation visible only at commit, a
  replay of the same refresh token that reads the session before that commit
  would find it active, wait on the row lock, revoke zero rows and rotate. This is
  closed by ADR 2.6.0002 §1b (`revoke` reports whether it revoked; losing is reuse),
  not by this ADR.
- The unit holds row locks (the consumed token, revoked sessions) until commit; the
  blocks contain only writes, so the window is a handful of statements.

### Neutral / trade-offs accepted
- Not reentrant: a use case calling another use case that opens a unit would fail
  loudly. No such composition exists; when one does, joining the outer unit is a
  one-line change in the adapter and a new law in the contract.
- `READ COMMITTED` is kept; nothing in identity reads-then-writes across
  aggregates in a way that a higher level would fix (ADR 3.3.0006 §Alternative C
  explains why `SERIALIZABLE` would not help that shape anyway).

## Implementation notes

- `RuntimeError` for reentrance is a programming error and reaches HTTP as 500 —
  deliberately not in the status map.
- The fake restores only the declared persisted state; counters and injector
  logs live through a rollback, which is what lets a unit test assert that the
  failure fired at write N.
- The bootstrap test reads the private `_engine` of the unit and of every identity
  repository injected into each of the five use cases (including the facade's
  `ProvisionAccountUseCase`); it is the only place where the wiring invariant can
  be observed.
- A mechanical test asserts that no `_engine.begin(` / `_engine.connect(` is left
  in the identity repositories: a method missed in the migration commits alone,
  reads outside the unit, or — worse — waits on a row the unit already locked
  from a second pooled connection, a wait Postgres cannot see as a deadlock.

## References

- Related ADRs: [2.2.0004](./2_2_0004-synchronous-port-signatures.md),
  [3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md),
  [2.6.0002](./2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
- Superseded clause: `docs/stages/2.3-identity-persistence/concept.md` §7 Decision 6
- Findings closed: the **rotation half** of
  `docs/stages/2.4-identity-http/technical.md` §7 "Atomicidade da rotação e do
  provisionamento" (its restaurant+owner provisioning half — ADR 2.4.0003 Alt. B —
  stays open, escalated with its own issue); `docs/stages/3.5-employee-login-link/concept.md`
  §6.4 "Órfão dentro de identity"
- External: Fowler, *PoEAA*, "Unit of Work"; Vernon, *IDDD* ch. 12 (application
  service as transaction boundary)
- Library sources (versions from `uv.lock`): SQLAlchemy 2.0.51
  `lib/sqlalchemy/engine/base.py` (`Connection.begin_nested`, `NestedTransaction`);
  anyio 4.14.1 `src/anyio/_backends/_asyncio.py` (worker `copy_context`);
  Starlette 1.3.1 `starlette/concurrency.py` (`run_in_threadpool`)
- Issue: #46

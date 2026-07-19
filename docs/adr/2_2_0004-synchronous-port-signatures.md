---
title: ADR 2.2.0004 — Synchronous signatures for identity out ports and use cases
description: Architecture Decision Record
when-use: Reference before introducing async/await into the identity application layer, or when the persistence or HTTP adapter is written
keywords: [adr, identity, async, sync, port, sqlalchemy, fastapi, concurrency]
status: accepted
created_at: 2026-07-18
updated_at: 2026-07-18
adr_id: "2.2.0004"
decision: Identity out ports and use cases are synchronous; async is deferred until a measured need exists, and the migration path is a mechanical rewrite of the ports plus their two adapters.
context_stage: 2.2-identity-application
bounded_context: identity
---

# ADR 2.2.0004 — Synchronous signatures for identity out ports and use cases

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.2 publishes six out ports that Stages 2.3 (Postgres) and 2.4 (HTTP,
argon2, JWT) will implement. Whether those signatures are `def` or `async def` is
decided here, once, for all of them — the choice propagates to every use case,
every fake, both adapters, and every test.

Facts, verified rather than assumed:

- `async` and `await` appear **zero** times in `docs/roadmap.md`,
  `docs/overview.md` and `docs/LAYOUT.md`. No document asks for concurrency.
- Async exists in the repository today **only at the framework surface**: the two
  Starlette exception handlers in
  `shared/infrastructure/http/error_handlers.py` (signature imposed by Starlette)
  and the `httpx.AsyncClient` used by the e2e tests (`tests/conftest.py`,
  `tests/e2e/test_app_smoke.py`). There is **no** async in `domain/` or
  `application/` — the layers this decision governs. The only I/O-bearing shared
  infrastructure is `shared/infrastructure/database/connection.py` (SQLAlchemy
  sync engine).
- The stack does support async on both ends: FastAPI accepts `def` handlers
  (running them in a threadpool) and `async def` alike, and SQLAlchemy 2 ships
  both `Session` and `AsyncSession`.
- The product is an internal back-office for restaurant scheduling. The expected
  concurrency is dozens of simultaneous users, not thousands of idle long-lived
  connections.
- Argon2 password hashing — the 2.4 adapter — is **CPU-bound**, not I/O-bound. It
  does not benefit from async and would block an event loop if run naively inside
  a coroutine.

## Decision

All identity out ports, use cases and fakes are **synchronous** (`def`, not
`async def`). FastAPI endpoints in 2.4 that consume them are declared `def`, so
Starlette runs them in its threadpool and no event loop is blocked. Stage 2.3
uses SQLAlchemy 2 in sync mode.

If a measured need for async appears later, the migration is mechanical and
localized: the six `Protocol` definitions, their two adapter implementations,
their fakes, and the use case bodies — all in one bounded context, all covered by
the tests written in this Stage.

## Alternatives considered

### Alternative A — Async ports from the start
- **Description:** `async def` on every port method and use case; `AsyncSession`
  in 2.3; `async def` handlers in 2.4.
- **Pros:** no future migration; idiomatic for FastAPI's async-first reputation;
  better throughput under high I/O-bound concurrency.
- **Cons:** every test becomes a coroutine test; fakes become async for no reason;
  the CPU-bound argon2 adapter still needs a threadpool escape hatch, so the
  uniformity is illusory; async SQLAlchemy has sharper edges (greenlet
  requirement, lazy-load failures) that cost debugging time in the Stage where the
  team is also learning the mapper layer. All of this is paid now for a throughput
  need that no document states and no user count justifies.
- **Why rejected:** it is a real cost today against a speculative benefit. The
  project criterion prefers the simplest solution that does not constrain growth,
  and sync does not constrain growth here — it constrains *throughput*, which is
  measurable and not yet a problem.

### Alternative B — Mixed: async for I/O ports, sync for CPU ports
- **Description:** repositories async, `PasswordHasher` sync.
- **Pros:** each port matches its true nature.
- **Cons:** use cases would have to be async (they await repositories), so the
  sync hasher must be dispatched to a threadpool from inside the use case — that
  is infrastructure knowledge leaking into the application layer, which LAYOUT §3
  forbids in spirit and `hex-arch-python` in letter.
- **Why rejected:** it buys precision at the cost of putting an executor concern
  in the wrong layer.

### Alternative C — Defer: leave the ports untyped as to sync/async
- **Description:** do not decide; let 2.3 pick.
- **Pros:** no decision to defend now.
- **Cons:** impossible in practice — a `Protocol` signature is either `def` or
  `async def`, and 2.2 must write it to have testable use cases. Deferring means
  2.3 defines the application layer's contracts from inside the adapter layer.
- **Why rejected:** the decision cannot actually be postponed; only hidden.

### Alternative D — Do nothing / status quo
Status quo *is* sync in `domain/` and `application/` (the async that exists is
confined to the framework surface described in §Context), so this ADR mostly
records why the status quo was kept deliberately rather than by inertia — and what
would have to change to revisit it.

## Consequences

### Positive
- Tests, fakes and use cases stay plain functions; the test suite needs no
  `asyncio` ceremony for this BC.
- The argon2 adapter runs naturally, with no event-loop hazard.
- SQLAlchemy 2 sync in 2.3 avoids the greenlet/lazy-load class of bugs while the
  mapper layer is being written for the first time.

### Negative
- Under genuinely high concurrency, threadpool-based handlers cap throughput
  earlier than an async stack would. Accepted: revisit with a measurement, not a
  hunch.
- If async is later required, six ports, two adapters, the fakes and the use case
  bodies must be rewritten. Bounded and mechanical, but not free.

### Neutral / trade-offs accepted
- FastAPI's `def` handlers run in a threadpool with a bounded worker count; 2.4
  should be aware of that limit when it configures the app.
- This ADR governs BC `identity` only. A future BC with a genuinely async
  workload (e.g. an external timeclock integration in Step 7) may choose
  differently — ports are per-BC contracts.

## Implementation notes

- Trigger to revisit: a measured latency problem attributable to threadpool
  saturation, or a downstream dependency that is async-only.
- If revisited, change the `Protocol` definitions first and let mypy strict
  enumerate every call site.

## References

- Related ADRs: [`2_2_0001-revocable-refresh-session-port.md`](./2_2_0001-revocable-refresh-session-port.md),
  [`0_0_0004-autonomous-overnight-mode.md`](./0_0_0004-autonomous-overnight-mode.md) §Decision #4
- Concept: [`../stages/2.2-identity-application/concept.md`](../stages/2.2-identity-application/concept.md) §4, §7.5
- Code: `src/restaurant_hub/shared/infrastructure/database/connection.py` (sync engine)

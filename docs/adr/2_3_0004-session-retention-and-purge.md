---
title: ADR 2.3.0004 — Session purge is an operation on the port; the retention window belongs to the caller
description: Architecture Decision Record
when-use: Reference when scheduling session cleanup, when changing the session retention window, or before adding a maintenance operation to an out-port
keywords: [adr, session, purge, retention, refresh-token, forensics, cleanup, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.3.0004
decision: SessionRepository gains purge_expired(before) which deletes sessions already expired at a caller-supplied instant (expires_at <= before, matching the half-open is_active boundary) and returns the count, keeping the retention policy with the caller so revoked-session forensics stay recoverable
context_stage: 2.3-identity-persistence
bounded_context: identity
---

# ADR 2.3.0004 — Session purge is an operation on the port; retention belongs to the caller

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.2 closed with an explicit finding assigned to **this** Stage:

> **[finding] limpeza de sessões expiradas** — Contexto: cada login grava uma linha
> de sessão; nada as remove. Em produção a tabela cresce indefinidamente.
> Direção sugerida: política de expurgo (job periódico ou índice com TTL) na Stage
> que cria a tabela. **Stage candidata:** `2.3-identity-persistence`.

Stage 2.3 is the Stage that creates the table, so the policy has to be decided here.

Two constraints shape the answer. First, PostgreSQL has no native row TTL — there is
no "expire this row" primitive; deletion is something someone must run. Second,
[ADR 2.2.0001](./2_2_0001-revocable-refresh-session-port.md) makes the preservation
of `revoked_at` a security property: the port's `revoke` is idempotent *in the strong
sense* precisely so that the instant of first revocation survives, because that is
the datum an incident investigation into refresh-token reuse needs. Deleting revoked
sessions eagerly would destroy exactly that evidence.

## Decision

`SessionRepository` gains one method:

```python
def purge_expired(self, before: datetime) -> int:
    """Remove sessões já expiradas em `before` (`expires_at <= before`).

    Devolve quantas removeu.
    """
```

- The predicate is `expires_at <= before`, **inclusive**. This is not a detail: the
  DTO's `is_active` uses a half-open interval (`now < self.expires_at`), so a session
  whose `expires_at` equals the instant in question is **already expired**. A `<`
  predicate would leave exactly that session behind, so that "expired" and "purgeable"
  would disagree on the boundary — the kind of off-by-one that two engineers write two
  different tests for. Sessions that are still valid are never touched, regardless of
  revocation state.
- **The retention window is the caller's decision, not the adapter's.** An operator
  wanting ninety days of forensic history calls `purge_expired(now - 90d)`; one
  wanting aggressive cleanup calls `purge_expired(now)`. No policy constant is
  buried in the repository.
- The return value is the number of rows removed, so a future scheduled job can log
  and alert on it.
- `sessions.expires_at` gets an index, so the purge is a range scan rather than a
  sequential one.
- Fake, real adapter and contract test all implement it; the fake is not exempt.

This Stage delivers the **operation and the policy shape**. Wiring it to a scheduler
is deployment concern (Step 6) and is escalated as a finding, not built here.

## Alternatives considered

### Alternative A — Purge inside the adapter on a fixed internal policy
- **Description:** the repository deletes anything expired more than N days ago,
  with N a constant in the adapter (or opportunistically, on every `add`).
- **Pros:** nothing to schedule; no port change; the table is bounded automatically.
- **Cons:** it hides a data-destruction policy inside an adapter, where no one
  reviewing the application layer would look for it — and it destroys the
  `revoked_at` forensics that ADR 2.2.0001 deliberately preserves, on a timetable
  nobody chose. Opportunistic purging on write also makes an ordinary login pay an
  unbounded delete, with a latency spike proportional to how long the system was
  idle.
- **Why rejected:** it puts an irreversible policy in the layer least visible to the
  people who own the policy.

### Alternative B — A scheduled `DELETE` in SQL, outside the application (cron/pg_cron)
- **Description:** an operational job runs the SQL directly; no application code.
- **Pros:** zero port surface; classic, well-understood ops pattern.
- **Cons:** the schema knowledge leaks into an artefact that lives outside the
  repository and outside every gate — no test, no type check, no contract. When the
  column is renamed, nothing catches it. It also cannot be exercised by the contract
  test that proves fake ≡ real, so the fake would silently lack the behaviour.
- **Why rejected:** untested and ungated by construction, which is the property this
  project consistently refuses.

### Alternative C — Partition `sessions` by expiry window and drop partitions
- **Description:** range-partition on `expires_at`; cleanup becomes `DROP PARTITION`.
- **Pros:** cleanup is O(1) and never bloats; the standard answer at scale.
- **Cons:** substantially more schema machinery, a partition-maintenance job of its
  own, and Alembic migrations that are much harder to write and reverse — all for a
  single-restaurant pilot whose session volume is a rounding error (ASSUM-5).
- **Why rejected:** correct answer to a problem this system does not have yet, at a
  cost paid immediately. `purge_expired` can be reimplemented over partitions later
  without changing its signature.

### Alternative D — Do nothing / status quo
- **Description:** leave the finding open, escalate it again.
- **Why rejected:** the finding names this Stage. The table is created here; leaving
  it unbounded means the first stage to notice is production.

## Consequences

### Positive
- The finding from Stage 2.2 is closed where it was assigned, and the table has a
  defined, testable path to staying bounded.
- Forensic history is preserved by default: nothing is deleted while a session is
  still valid, and how long expired sessions linger is an explicit choice at the call
  site rather than a hidden constant.
- Being on the port means the fake implements it too, so it is covered by the same
  contract test as everything else.

### Negative
- The port grows a method that has no production caller in this Stage — a small,
  deliberate piece of dead code until the scheduler exists. This is the honest cost;
  the alternative (add it when the scheduler arrives) would mean the table is
  unbounded in the interim and the contract test never covers it.
- Adding a method to a port published by an already-merged Stage means Stage 2.2's
  fake and its `_conforms` check must be updated in step.

### Neutral / trade-offs accepted
- `purge_expired` deletes by expiry only, ignoring revocation. A revoked but not yet
  expired session stays until its natural expiry — correct, since it is still the
  record of an active-until-revoked credential.
- No cascade concerns: `sessions` is a leaf table.

## Implementation notes

- Escalate as `[finding]`: wire `purge_expired` to a scheduled job (Step 6 /
  deployment), including the retention window choice and alerting on the returned
  count.
- Index: `ix_sessions_expires_at` on `expires_at`.

## References

- Related ADRs: [ADR 2.2.0001](./2_2_0001-revocable-refresh-session-port.md)
  (why `revoked_at` is worth preserving),
  [ADR 2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md) (the table)
- Source finding: §7 of [`../stages/2.2-identity-application/technical.md`](../stages/2.2-identity-application/technical.md)

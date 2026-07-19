---
title: ADR 2.3.0002 — The tenant discriminator is denormalised only where it makes cross-tenant linkage representable, and is anchored by composite foreign keys
description: Architecture Decision Record
when-use: Reference before changing the identity schema, before adding a tenant column to a new table, before writing a composite foreign key involving a nullable column, or when evaluating native row-level security
keywords: [adr, schema, multi-tenancy, tenant-id, postgres, constraints, check-constraint, composite-fk, match-simple, three-valued-logic, rls]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.3.0002
decision: unit_memberships carries a NOT NULL tenant_id anchored by composite foreign keys to both its user and its unit, making cross-tenant linkage unrepresentable; sessions does not get a tenant column because the port cannot supply one; and the platform-admin tenancy rule is expressed as an iff CHECK over a NOT NULL role
context_stage: 2.3-identity-persistence
bounded_context: identity
---

# ADR 2.3.0002 — Tenant discriminator placement and the constraints that carry the domain invariants

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

ROADMAP-3 fixes multi-tenancy as **row-level `tenant_id` in a single PostgreSQL** for
v1, with "isolamento reforçado em código + testes", and keeps the door open to a
per-restaurant instance later (Step 6). The roadmap entry for this Stage describes it
as "repositórios PostgreSQL de identity (**com `tenant_id` em todas as tabelas** —
ROADMAP-3)". Native row-level security (`CREATE POLICY`) is an explicit non-goal of
this Stage.

The domain (Stage 2.1) establishes that a `Restaurant` **is** its own tenant (ADR
2.1.0001), that `User.tenant_id` is `None` **iff** the role is `platform_admin` (ADR
2.1.0002), and that `User.link_to_unit` refuses to link across tenants:

```python
if self.tenant_id != unit.tenant_id:
    raise CrossTenantError(self.tenant_id, unit.tenant_id)
```

Stage 2.1's audit singled out persistence as the place where such invariants are most
likely to be quietly bypassed, which is why entities were made `frozen`.

Reading "tenant_id em todas as tabelas" literally runs into three facts that only
surface when the SQL is written out:

1. **`sessions` has no tenant to write.** The `Session` DTO
   (`application/dtos/session.py`) is `{id, user_id, refresh_token_fingerprint,
   issued_at, expires_at, revoked_at}`, and `SessionRepository.add(session)` receives
   nothing else. Populating a `sessions.tenant_id` would require the adapter to issue
   an extra `SELECT` against `users` on every write, and the in-memory fake — which
   stores the DTO — could not carry the column at all. The contract test that is the
   entire point of this Stage could never reach it.
2. **A composite FK over a nullable column is inert.** PostgreSQL foreign keys default
   to **MATCH SIMPLE**: if *any* referencing column is NULL, the constraint is not
   checked at all. Since `platform_admin` has `tenant_id IS NULL`, a composite FK
   `sessions(user_id, tenant_id) → users(id, tenant_id)` would be silently disabled
   for exactly the privileged role it was meant to constrain.
3. **A CHECK constraint accepts NULL.** Only `FALSE` rejects a row; `NULL` passes. So
   `CHECK ((role = 'platform_admin') = (tenant_id IS NULL))` has a hole whenever
   `role` is NULL — the predicate evaluates to NULL and the row is accepted, letting
   in a tenant-less would-be owner.

The table where the discriminator genuinely earns its place is `unit_memberships`: it
is the only one where a *cross-tenant linkage* is representable at all, and it is the
row an attacker or a buggy migration would forge to gain visibility into another
restaurant.

## Decision

1. **`unit_memberships` carries `tenant_id NOT NULL`, anchored on both sides.** Two
   composite foreign keys:
   - `(unit_id, tenant_id) → units(id, restaurant_id)`
   - `(user_id, tenant_id) → users(id, tenant_id)`

   Together they make a membership whose user and unit belong to different tenants
   **unrepresentable**, not merely discouraged. Because the column is `NOT NULL`, the
   MATCH SIMPLE trap of point 2 cannot fire here. As a welcome side effect, a
   `platform_admin` (NULL tenant) cannot satisfy the user-side FK, so the database now
   enforces `PlatformAdminMembershipError`, which until now only the domain enforced.
2. **The referenced keys get explicit unique anchors.** PostgreSQL requires the
   referenced column list of a composite FK to be covered by a unique index, so
   `units` gets `UNIQUE (id, restaurant_id)` and `users` gets `UNIQUE (id, tenant_id)`.
   These are not redundancy for its own sake — without them the migration does not
   run at all.
3. **`sessions` does not get a `tenant_id`.** A session reaches its tenant through
   `user_id → users.tenant_id`, which is the source of truth. No session query is
   tenant-scoped: sessions are looked up by fingerprint or by user.
4. **The platform-admin rule is an iff over a constrained `role`.** `role` is
   `NOT NULL` and restricted by `CHECK (role IN ('platform_admin', 'owner', 'manager',
   'hr', 'employee'))`; on top of that,
   `CHECK ((role = 'platform_admin') = (tenant_id IS NULL))`. The `NOT NULL` is
   load-bearing, not decoration — it is what closes the three-valued-logic hole.
5. **`users.email` gets `CHECK (email = lower(btrim(email)))`.** Postgres compares
   text byte-wise, so a unique index alone would accept `A@X.com` and `a@x.com` as two
   rows that both rehydrate to the same login through the `Email` value object, which
   normalises on read. The CHECK makes the domain's guarantee explicit in the schema.
6. **Every constraint gets an explicit name** (`pk_`/`uq_`/`fk_`/`ck_`/`ix_`). The
   adapter translates `IntegrityError` into domain exceptions by matching the
   constraint that fired; auto-generated names would make that fragile.

## Alternatives considered

### Alternative A — Put `tenant_id` on literally every table, including `sessions`
- **Description:** the literal reading of the roadmap line.
- **Pros:** uniform; every table filterable without a join; a future `CREATE POLICY`
  needs no migration anywhere.
- **Cons:** for `sessions` the column is unreachable from the port and impossible for
  the fake, so it would be the one column in the schema with **no contract-test
  coverage** — and it would be anchored by an FK that MATCH SIMPLE disables for
  platform admins, i.e. an anchor that looks protective and is not. It would also put
  an extra `SELECT users` inside every session write, on the login hot path.
- **Why rejected:** it buys uniformity by adding an unverifiable column and a
  decorative constraint. Uniformity that the tests cannot check is not a guarantee.

### Alternative B — Denormalise the tenant everywhere without composite foreign keys
- **Description:** add the columns, keep them correct by application discipline.
- **Pros:** simplest to write; no extra unique anchors needed.
- **Cons:** the classic denormalisation failure — the copy drifts from its source and
  nothing notices. A membership row whose `tenant_id` disagrees with its unit's is a
  silent isolation hole, and it is exactly what a bug in a *future* stage would
  introduce, long after this code was reviewed.
- **Why rejected:** the entire benefit of a local column is being able to trust it;
  an untrusted one is worse than a join, because it invites trust it has not earned.

### Alternative C — Store the tenant only where intrinsic; join to reach it elsewhere
- **Description:** no `tenant_id` on `unit_memberships` either; derive via `users`
  and `units`.
- **Pros:** fully normalised; no drift possible by construction.
- **Cons:** it leaves cross-tenant membership **representable** — the row `(user in
  tenant A, unit in tenant B)` would be perfectly legal SQL, and only application code
  would stand between it and a visibility leak. That is precisely the isolation
  ROADMAP-3 says to reinforce. Adopting RLS later would also require migrating the
  table and backfilling on live tenant data.
- **Why rejected:** it optimises for normal form at the cost of the one property the
  roadmap names as the point.

### Alternative D — Native row-level security now (`CREATE POLICY` + `SET LOCAL`)
- **Description:** enforce isolation in the database rather than in repository code.
- **Pros:** the strongest possible guarantee — a forgotten `WHERE` cannot leak.
- **Cons:** explicit non-goal of this Stage in the roadmap; needs a per-connection
  session variable and a role model the project does not have; interacts with
  connection pooling in ways that need their own design.
- **Why rejected:** out of scope by roadmap decision. This ADR's shape keeps later
  adoption additive for the table that matters.

### Alternative E — Do nothing / status quo
- **Description:** model only what the entities strictly need, with single-column FKs.
- **Why rejected:** the roadmap names `tenant_id` as part of this Stage's deliverable,
  and the cross-tenant membership row would stay representable.

## Consequences

### Positive
- Cross-tenant membership is **unrepresentable**, not merely rejected by code — the
  guarantee survives raw `INSERT`s, data migrations and future application bugs.
- `platform_admin` memberships are now blocked by the database as well as the domain.
- The iff and the closed role set are enforced where they cannot be bypassed, with
  the three-valued-logic hole closed deliberately rather than accidentally.
- Named constraints make `IntegrityError` translation deterministic.
- No column exists that the contract test cannot reach.

### Negative
- Two unique constraints (`uq_units_id_restaurant`, `uq_users_id_tenant`) exist
  largely as FK anchors and partially duplicate the primary keys — extra index
  maintenance on write, accepted as the price of the composite FKs.
- `unit_memberships` writes must supply the tenant, so the mapper has one more field
  to get right — mitigated by the composite FKs rejecting a wrong value outright.
- The roadmap's "tenant_id em todas as tabelas" is implemented in spirit rather than
  literally. The deviation is argued here, and the Stage's closing roadmap note must
  correct that phrase in the block's human description — otherwise the roadmap keeps
  asserting a literal reading that the schema deliberately does not implement (Stage
  concept §7 Decisão 9).

### Neutral / trade-offs accepted
- Identifiers are stored as text (`str(uuid4)` canonical form, invariant #3 of Stage
  2.2), not the native `UUID` type. The database does **not** validate that format:
  the domain treats ids as opaque by explicit decision
  (`value_objects/identifiers.py`), and a format CHECK would contradict it.
- `users.password_hash` is a `NOT NULL` column on `users` rather than a separate
  credentials table: the relation is 1:1 and mandatory, and the port writes both in
  one transaction.
- Text columns are `TEXT`, never `CHAR(n)` — `CHAR` right-pads, which would break the
  verbatim round-trip of `name` required by ADR 2.3.0005.

## Implementation notes

- The schema lives in `features/identity/adapters/out/postgres/tables.py` as a
  `MetaData` in SQLAlchemy 2 **Core** (no declarative ORM — CLAUDE.md stack rule),
  consumed by `migrations/env.py` as `target_metadata`.
- Timestamp columns are `TIMESTAMP WITH TIME ZONE` at full microsecond precision; see
  the Stage concept I10 for why the mapper still normalises to UTC on read.

## References

- Related ADRs: [ADR 2.1.0001](./2_1_0001-identity-aggregates-and-membership.md)
  (restaurant is the tenant), [ADR 2.1.0002](./2_1_0002-platform-admin-without-tenant.md)
  (the iff), [ADR 2.3.0005](./2_3_0005-names-persisted-verbatim.md) (why `TEXT`),
  [ADR 2.3.0001](./2_3_0001-integration-tests-require-real-postgres.md) (how these
  constraints get exercised)
- Roadmap premise ROADMAP-3: [`../roadmap.md`](../roadmap.md)
- PostgreSQL semantics relied upon: MATCH SIMPLE foreign keys skip the check when any
  referencing column is NULL; CHECK constraints reject only on `FALSE`, not on `NULL`.

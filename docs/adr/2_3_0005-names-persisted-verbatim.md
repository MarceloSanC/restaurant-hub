---
title: ADR 2.3.0005 — Names are persisted verbatim; the persistence boundary does not normalise
description: Architecture Decision Record
when-use: Reference before adding normalisation to a mapper or repository, or when a uniqueness/ordering requirement on a name field appears
keywords: [adr, normalization, mapper, round-trip, name, persistence-boundary, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-07-19
adr_id: 2.3.0005
decision: Repositories persist and return name fields byte-for-byte as given, performing no trimming or case folding, so that add/find is a faithful round-trip and the in-memory fake cannot diverge from the Postgres adapter
context_stage: 2.3-identity-persistence
bounded_context: identity
---

# ADR 2.3.0005 — Names are persisted verbatim; the persistence boundary does not normalise

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.1 closed with a finding addressed to this Stage:

> **[finding] `name` não é normalizado nas entidades** — `Email` normaliza (trim +
> lowercase) e guarda o valor normalizado; já `Restaurant.name`/`Unit.name`
> **validam** com `.strip()` mas **armazenam o valor cru**
> (`Restaurant(name="  Cantina  ").name == "  Cantina  "`). […]
> **Direção sugerida:** decidir na persistência se `name` é normalizado na escrita
> (afeta unicidade e ordenação por nome). **Stage candidata:**
> `2.3-identity-persistence`.

So the decision is owed here. The asymmetry with `Email` is real: `Email.__post_init__`
calls `object.__setattr__` to store a trimmed, lowercased value, precisely because
global uniqueness of login is a rule and case-insensitivity is part of it.

Two facts about the present system bear on the answer. There is **no uniqueness
constraint** on any `name` column, and there is **no query anywhere that orders by
name** — the two motivations the finding cites are hypothetical today. And the
in-memory fakes, which the contract tests of this Stage require to be equivalent to
the real adapters, store whatever they are handed.

## Decision

Repositories persist `name` exactly as received and return it exactly as stored. No
trimming, no case folding, no Unicode normalisation at the persistence boundary.

The finding is thereby **closed with a decision, not deferred**: normalising `name`
is declined, and the reasoning is recorded so a future Stage that acquires a real
uniqueness or ordering requirement knows where to implement it — in the entity
constructor, alongside what `Email` already does, not in the mapper.

## Alternatives considered

### Alternative A — Normalise (trim) on write in the mapper
- **Description:** the repository trims `name` before the `INSERT`.
- **Pros:** stored data is tidy; a future `UNIQUE` on name would behave more
  intuitively; it is where the finding suggested looking.
- **Cons:** it makes `add` **lossy** — what you read back is not what you wrote —
  which breaks the round-trip property that every other repository test in this Stage
  relies on. Worse for this Stage specifically: the in-memory fake stores verbatim,
  so a normalising adapter would be *observably different from the fake*, which is
  exactly the class of divergence the contract tests exist to eliminate. Fixing that
  would mean teaching the fake to normalise too — pushing a domain rule into two test
  doubles instead of into the domain.
- **Why rejected:** it introduces a fake/real divergence in the very Stage whose
  purpose is to eliminate them, to serve a requirement that does not exist.

### Alternative B — Normalise in the entity constructor, like `Email`
- **Description:** `Restaurant.__post_init__` / `Unit.__post_init__` store
  `name.strip()`.
- **Pros:** the genuinely correct home — one rule, one place, applying to every path
  into the system, with the fake and the adapter both inheriting it for free. It is
  the shape `Email` already proves works.
- **Cons:** it is a change to `features/identity/domain/`, which is **not this
  Stage's target layer** (`adapters/out/postgres`); Stage 2.1 considered and did not
  make it; and it would silently change behaviour that merged domain tests assert.
- **Why rejected here:** right idea, wrong Stage. Recorded as the recommended
  destination if a requirement ever justifies it — this ADR is the pointer.

### Alternative C — Normalise on read
- **Description:** the mapper trims when rehydrating.
- **Pros:** stored data stays faithful.
- **Cons:** strictly worse than A — the same fake/real divergence, plus the database
  and the application now disagree about what the value is, so an operator querying
  directly sees something different from the API.
- **Why rejected:** all of A's costs and none of its benefit.

### Alternative D — Do nothing / status quo, leaving the finding open
- **Description:** re-escalate to a later Stage.
- **Why rejected:** the finding was addressed to this Stage. "No change" is a
  legitimate answer, but it has to be an argued decision with a recorded rationale,
  otherwise the next Stage rediscovers the question with less context than we have
  now.

## Consequences

### Positive
- `add` followed by `find_by_id` is a faithful round-trip, which keeps every
  repository test simple and keeps fake and adapter trivially equivalent.
- The finding is closed with reasoning rather than passed along.
- The decision is cheap to reverse: adding trimming to the entity constructor later
  affects one place and is covered by existing tests.

### Negative
- `"  Cantina  "` and `"Cantina"` remain distinct values in the database, so a future
  uniqueness rule on name would need a data cleanup before it could be enforced.
  Accepted knowingly: no such rule exists, and inventing one now to justify the
  cleanup would be backwards.
- The asymmetry with `Email` persists and may surprise a reader. Mitigated by this
  ADR being greppable from both the finding and the entities.

### Neutral / trade-offs accepted
- Identifiers are likewise stored verbatim (canonical `str(uuid4)`, invariant #3 of
  Stage 2.2) — same principle, and there the canonical form is already guaranteed
  upstream by the generator.
- A `CHECK` asserting `email = lower(email)` is added to `users` regardless: there the
  normalisation *is* a domain guarantee (`Email` enforces it), so the constraint
  makes an existing invariant explicit rather than imposing a new one.

## References

- Related ADRs: [ADR 2.3.0002](./2_3_0002-identity-schema-tenant-and-constraints.md)
  (the schema these columns live in)
- Source finding: §7 of [`../stages/2.1-identity-domain/technical.md`](../stages/2.1-identity-domain/technical.md)
- Precedent for constructor-level normalisation: `features/identity/domain/value_objects/email.py`

---
title: ADR 3.5.0004 — The login link is a nullable opaque `user_id` column on `employees`, set once by a guarded domain transition, never copied, with no FK, no UNIQUE and no index
description: Architecture Decision Record
when-use: Reference before touching `employees.user_id`, before adding a constraint or index to it, before implementing "link an existing login", or when Step 4 adds `find_by_user_id`
keywords: [adr, user_id, employee, login-link, schema, nullable, opaque, no-fk, no-unique, copy, staff]
status: accepted
created_at: 2026-09-12
updated_at: 2026-09-13
adr_id: 3.5.0004
decision: `Employee.user_id: UserId | None` (default `None`) persisted as `employees.user_id TEXT NULL` — opaque (no FK to identity, ADR 3.3.0002), not unique (workforce §3.7 allows several records per person), not indexed (no access path by `user_id` yet, ADR 3.3.0005); set only through `Employee.link_login`, which refuses a record that is already linked or terminated; never carried by the copy, by construction (explicit field-by-field clone with the default left untouched)
context_stage: 3.5-employee-login-link
bounded_context: staff
---

# ADR 3.5.0004 — `user_id` as a nullable opaque column on `employees`

## Status

`accepted`

## Context

Stage 3.5 adds the login link to the employee record. The domain doc fixed the
semantics before any code existed: *"the copy does NOT carry the `user_id` — the
login link is an explicit per-record decision; the same person may end up with
several records pointing to the same User through explicit links, never by
drag of the copy"* (`workforce.md` §3.7; ADR 3.1.0001 iii; ADR 3.2.0003's closed
exclusion list has `user_id — never carried`). Stages 3.2 and 3.6 left
**vacuous** guards for this field (result DTO has no login field; request
schemas blacklist `user_id`).

Forces:

- **No FK crosses a bounded context** (ADR 3.3.0002): `tenant_id` and `unit_id`
  are already opaque `TEXT` columns without FK to identity's tables.
- **Indexing follows measured access** (ADR 3.3.0005): no operation of this
  Stage reads by `user_id`; the first one ("my schedule") belongs to Step 4.
- **Cardinality is decided by the domain doc**: N records → 1 login is
  legitimate (the same person in two units). In this Stage every R17 creates a
  **new** login, so uniqueness is de facto — but a `UNIQUE` would freeze the
  opposite of what the doc allows.
- **Terminated records** must not receive a login (termination cuts access —
  kickoff #4, ADR 3.5.0003), and a linked record must not receive a second one
  (there is no "change login" in this Stage).
- `Employee` is `frozen`; transitions return new instances via
  `dataclasses.replace`; the copy use case constructs the clone **field by
  field** (`copy_employee_to_unit.py:71`).

## Decision

**1. Field.** `Employee.user_id: UserId | None = None`, with
`UserId = NewType("UserId", str)` in staff's `identifiers.py` — staff's own
type for an id that belongs to identity, per the module's rule (*"identifiers
cross the BC boundary as opaque strings, and each BC types its own"*). When
present it must be **non-empty** (`InvalidIdentifierError` in `__post_init__`),
so a rehydrated `""` cannot become a phantom link that blocks R17 forever — the
3.1 principle "invariant on every construction path". The field's semantics do
**not** restrict the role of the `User` it points to: today the only producer
creates `employee` accounts, but a future link to a manager who also works
shifts is legitimate (workforce §3.3(b), §3.7).

**2. Transition, guarded in the entity.** `Employee.link_login(user_id)` returns
a new instance; it calls `Employee.assert_can_link_login()`, which raises
`EmployeeAlreadyHasLoginError` when `user_id` is set and
`TerminatedEmployeeLoginError` when `active` is `False` — in that order of
precedence. The guard is a separate, public method because the use case must
ask **before** provisioning the account in identity; `link_login` calls it
again so the rule has one home. A terminated record that already **has** a
login keeps it: history, like functions and unavailabilities (ADR 3.2.0006).

**3. Column.** `employees.user_id TEXT NULL`. No `FOREIGN KEY`, no `UNIQUE`, no
index. Migration `0004_employees_user_id` adds the column; `downgrade` drops it.

**4. Persistence.** `mappers.employee_to_row` writes it; `row_to_employee`
rehydrates `UserId(row.user_id)` when present. The column is **not** in
`_COLUNAS_IMUTAVEIS`: it is set by `update` (the record exists when the login
is created). "Set once" is the entity's law, not the adapter's — fake and
Postgres inherit it from `assert_can_link_login`.

**5. Copy never carries it — by construction.** `CopyEmployeeToUnitUseCase`
builds the clone naming every field it copies and **does not name** `user_id`;
the default `None` applies. The guard that was vacuous in 3.2 becomes a real
test: copying a linked record yields a clone with `user_id is None` and an
origin that keeps its own (concept CA04, CA26).

**6. Every result carries it.** `EmployeeResult.user_id` is filled by the
single `employee_result()` mapper used by the **12** use cases that return an
employee (the 11 existing construction sites plus `CreateLoginForEmployee`), so
every route that embeds an employee shows the link (concept §5.12, CA06, CA13).

## Alternatives considered

### Alternative A — a separate `employee_logins` table (1:1)
- **Description:** `employee_logins(employee_id PK, user_id, linked_at)`.
- **Pros:** the record stays untouched; room for link metadata (`linked_at`,
  `linked_by`).
- **Cons:** a `JOIN` on every read of the aggregate for one nullable value; the
  aggregate already owns three child tables that exist because they are
  **collections** — this is a scalar; metadata nobody asked for; N→N would be
  representable, which the domain doc does **not** allow (one login per record).
- **Why rejected:** structure for a relationship that a column represents
  exactly.

### Alternative B — `UNIQUE (user_id)`
- **Description:** one record per login, enforced by the schema.
- **Pros:** prevents a bug where two records point to the same login.
- **Cons:** contradicts `workforce.md` §3.7 (*"several records pointing to the
  same User via explicit links"*) — a decision this Stage does not reopen; and
  the only producer today creates a fresh `User` per call, so the constraint
  would guard against a path that does not exist.
- **Why rejected:** would freeze the opposite of the ratified domain rule.

### Alternative C — index on `user_id` now
- **Description:** `ix_employees_user_id` (possibly partial `WHERE user_id IS NOT NULL`).
- **Pros:** ready for "my schedule".
- **Cons:** no query uses it in this Stage; ADR 3.3.0005 ties indexes to
  measured access; the consumer (Step 4, `find_by_user_id`) will also decide
  whether the lookup is tenant-scoped, which shapes the index.
- **Why rejected:** index without access path; deferred with the consumer
  (concept §10 finding).

### Alternative D — allow linking a terminated record
- **Description:** no `TerminatedEmployeeLoginError`; ADR 3.2.0007 says
  terminated records remain editable.
- **Pros:** one guard fewer; symmetric with editing.
- **Cons:** creating a login is **granting access**, not editing a field;
  termination cuts access (kickoff #4; ADR 3.5.0003). Granting fresh access to a
  terminated record contradicts the cut this same Stage implements on R13.
- **Why rejected:** editing ≠ granting; the two ADRs (3.2.0007 and this one) are
  about different acts.

### Alternative E — do nothing (no field; login link lives only in identity)
- **Description:** identity's `UnitMembership` already links user → unit; infer
  the employee from it.
- **Pros:** no staff change.
- **Cons:** a membership is per **unit**, not per **record**; two records in
  the same unit (homonyms are legitimate) would be indistinguishable; and staff
  would have to read identity's model to know who is who — the coupling the
  ports exist to avoid.
- **Why rejected:** the link is a fact of the staff record (workforce §3.8).

## Consequences

### Positive
- Additive, nullable, opaque: no existing row changes meaning; the migration
  is trivially reversible.
- The copy invariant of ADR 3.2.0003 gets its first non-vacuous test.
- The entity, not the adapter, owns "set once" and "not for terminated
  records" — both implementations inherit them.

### Negative
- Uniqueness is not enforced by the schema; when "link an existing login"
  arrives (concept §10 finding) its rules (same tenant, membership of the unit;
  **not** a role restriction — see §1) must live in the use case/entity.
- "Set once" holds on the in-memory entity, not on the row: `update` writes the
  whole aggregate and the 3.3 posture is "last write wins" (ADR 3.3.0006). A
  concurrent edit that read the record before a link and writes after it erases
  the link silently, leaving an orphan account. Declared in concept §6.4 with
  the cheap fix named (a dedicated conditional-update port method) and deferred
  with issue #46.
- No index: the first `find_by_user_id` must add it together with its access
  path (Step 4).

### Neutral / trade-offs accepted
- `user_id` may point to a login that identity has since removed or changed;
  there is no FK to tell. Same posture as `tenant_id`/`unit_id` (ADR 3.3.0002)
  — the boundary owes the coherence, not the schema.
- No `linked_at`/`linked_by`: auditing of access grants is a roadmap concern
  (overview §3 "audit trail") not yet modeled anywhere; adding it here would
  invent the model. Declared.

## Implementation notes

- `row_to_employee` passes `user_id=UserId(row.user_id) if row.user_id is not None else None`
  through the constructor, so any future validation added to the entity also
  covers rehydration (3.1's principle).
- `test_schema.py` asserts: column present, nullable, no FK, no unique, no
  index; migration `0004` upgrades and downgrades against real Postgres.
- The contract suite of `EmployeeRepository` gains `user_id` in the "no other
  field changed" snapshot and a round-trip case for `link_login` + `update`.

## References
- `docs/stages/3.5-employee-login-link/concept.md` §4, §5.2, §5.5, §7 D4, §9,
  CA01, CA04, CA19, CA26
- `docs/domain/staff/workforce.md` §3.7, §3.8
- ADR 3.1.0001 (iii), ADR 3.2.0003 (exclusion list), ADR 3.2.0006, ADR 3.2.0007,
  ADR 3.3.0002 (no cross-BC FK), ADR 3.3.0005 (indexing follows access),
  ADR 3.5.0003 (termination cuts access)
- `src/restaurant_hub/features/staff/application/use_cases/copy_employee_to_unit.py:71`

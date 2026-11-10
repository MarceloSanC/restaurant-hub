---
title: ADR 3.11.0001 — A job function keeps belonging to the restaurant and carries where it is enabled, as either every unit or a non-empty set of units, with the name still unique in the restaurant and every-unit reach gated by manage_tenant
description: Architecture Decision Record
when-use: Reference before changing how a job function is scoped to units, before relaxing who may enable a function in every unit, or before making the function name unique per unit
keywords: [adr, job-function, unit, enablement, catalogue, manage-tenant, migration, staff, uniqueness]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-09
adr_id: 3.11.0001
decision: JobFunction stays tenant-owned and gains a UnitEnablement value object that is either every unit of the restaurant, present and future, or a non-empty explicit set of units; the name stays unique in the restaurant; enabling in every unit requires manage_tenant on top of manage_job_functions, enabling in named units requires manage_job_functions on each unit; changing the enablement replaces it whole and needs reach over the units added and removed (manage_tenant when every unit is on either side); existing functions migrate to every unit
context_stage: 3.11-job-function-unit-enablement
bounded_context: staff
---

# ADR 3.11.0001 — Job-function enablement per unit

## Status

`accepted`

> Decided under delegation: the sponsor delegated the product forks of this Stage
> to the recommended option (issue #41, orchestrated run of 2026-11-09). Each
> delegated fork is recorded below as `P delegado` with its reason.

## Context

Until Stage 3.11 a job function was valid for the whole restaurant, with no notion
of unit: `workforce.md` §3.2 ("Escopo: o restaurante (tenant), não a unidade"), the
schema (`job_functions` with no unit column, `uq_job_functions_tenant_name`) and the
catalogue permission (`manage_job_functions` is tenant-wide, ADR 3.4.0008).

While deciding the forks of Stage 3.4 the sponsor asked that **each unit sees its own
functions**, and that someone with reach beyond a unit may create a function for every
unit. Issue #41 weighed two readings — move the owner to the unit, or keep the owner and
control where the function is valid — and the sponsor chose the second. What the issue
left to this Stage: the shape of the enablement, its invariant, name uniqueness, who
may enable a function everywhere, and how existing data migrates.

Two facts of the codebase constrain the shape:

- **Units live in identity, and no foreign key crosses bounded contexts** (ADR
  3.3.0002). Staff has no list of the restaurant's units and no port that returns one.
  Any rule phrased as "all units" must therefore be expressible without enumerating
  them.
- **Identity's grant does not tell staff whether the actor bypasses unit scope.** The
  `AccessGrant` of the access facade carries the role, the actor's tenant and the
  approved unit; with `manage_job_functions` in `TENANT_WIDE_PERMISSIONS`, a manager
  authorized without a unit is indistinguishable from an owner (the `AuthorizedScope`
  docstring says exactly this: `unit_id is None` does not mean "tenant-wide").

## Decision

**1. The owner stays the restaurant.** `JobFunction.tenant_id` is unchanged; the
function gains `unit_enablement`, a value object of the staff domain.

**2. `UnitEnablement` is "every unit" or a non-empty explicit set** — never empty,
never both. *Every unit* is a value of its own, not the list of today's units: it
covers units created later, and it is what existing functions migrate to without staff
reading identity's `units` table. *A set* names units by opaque id. An empty set is
refused by the domain (`InvalidUnitEnablementError`): a function enabled nowhere would
be invisible in every unit listing and reachable only through the catalogue — the way
out of the catalogue is to delete the function (ADR 3.2.0005), not to hide it.
`P delegado — conjunto não-vazio ou "todas", motivo: função habilitada em nenhum lugar
seria inalcançável pelas listagens de unidade, e "todas" como valor próprio evita ler
unidades de identity na migration e cobre unidades futuras.`

**3. The name stays unique in the restaurant** — verbatim, as ADR 3.3.0001 and ADR
2.3.0005 fixed it; `uq_job_functions_tenant_name` is unchanged. A manager who needs a
function that already exists in another unit enables it in his unit (decision 5)
instead of creating a homonym. `P delegado — único no restaurante, motivo: a função é
do restaurante (decisão 1), o índice único segue sendo uma constraint de banco, e
"único por unidade" exigiria comparar nomes entre conjuntos de unidades — inclusive
contra funções de todas as unidades — sem índice que a imponha.`

**4. Reach.** Enabling in named units requires `manage_job_functions` **on each unit**
(one authorization per target, L-AG4) — identity runs the unit-visibility step whenever
a unit is named, so a manager reaches only units he is a member of. Enabling in **every
unit** requires `manage_tenant` **in addition** to `manage_job_functions` on the tenant:
deciding the catalogue of the whole restaurant is a restaurant-level act, and
`manage_tenant` is the restaurant-level permission (today held only by `owner`, the
role that bypasses unit scope). Staff cites it as a value in `access_guard.py`, like the
other three. `P delegado — exigir manage_tenant, motivo: é o único sinal de alcance
sobre o restaurante inteiro que o guard já expõe sem tocar identity (a Stage 2.7 está
em voo nos arquivos de identity), e é fail-closed: um papel futuro com alcance
multi-unidade e sem manage_tenant é negado, não promovido.`

**5. Changing the enablement replaces it whole** — one operation, `PUT
/job-functions/{id}/units`, with the same body shape as creation. The actor needs reach
over **what changes**, not over the whole old or new enablement: `manage_job_functions`
on each unit **added** and on each unit **removed**, in a stable order; `manage_tenant`
when either side is *every unit* and the two differ. So a manager enables in his own
unit a function that exists only in another unit — the path decision 3 relies on,
since the name is unique — without reaching the other unit; and he cannot remove a
unit he does not see, nor narrow a function enabled everywhere. The
replace-not-delta shape follows `assign_job_functions` (ADR 3.1.0006: a set, no order,
no history) — `decision:C`, rung 1 (already ratified in the project).

**Declared exception to ADR 3.7.0001 §4** ("all targets before the first port call").
The units to authorize depend on the stored enablement, so the use case authorizes the
tenant, reads the function (404 if absent), and only then authorizes the difference.
The read is no oracle: what it reveals — the function's enablement — is what the
catalogue (`GET /job-functions`) already shows to anyone who passed the tenant
authorization. ADR 3.7.0001 gets a dated note.

The write is a port operation of its own (`update_enablement`, law `L-JF7`), separate
from the rename's `update` (`L-JF2`, which keeps writing only the name): a rename racing
a change of units must not write the old enablement back.

**6. Listing.** `GET /job-functions` stays the restaurant's whole catalogue — the
function belongs to the restaurant, and the catalogue permission is tenant-wide — and
each item now says where it is enabled. `GET /units/{unit_id}/job-functions` is new and
lists only the functions enabled in that unit, ordered by `L-ORD`; the unit is a target
of authorization. `P delegado — catálogo inteiro mantido + rota por unidade, motivo:
preserva o contrato atual da rota de catálogo e cumpre "a listagem de uma unidade não
mostra função não habilitada nela" numa rota que nomeia a unidade, como as de
funcionário (ADR 3.4.0007).`

**7. Migration.** Existing rows become *every unit* through the column's server
default; no row of the new link table is written and identity is not read. Behaviour
before and after the migration is the same for every existing function.

## Alternatives considered

### Alternative A — move the owner to the unit
- **Pros:** "each unit sees its functions" falls out of the key.
- **Cons:** reverts a ratified decision (`overview.md` §3, `workforce.md` §3.2), breaks
  the copy of employees between units, and forces a duplicate per unit for functions
  every unit uses. Rejected by the sponsor in issue #41.

### Alternative B — explicit set only, migration enumerating today's units
- **Pros:** one representation.
- **Cons:** the migration would have to read identity's `units` (cross-BC data access,
  against ADR 3.3.0002), and a unit created tomorrow would see none of the functions
  that "every unit" used to mean. It also gives the owner no way to say "everywhere".

### Alternative C — empty set allowed
- **Pros:** narrowing never fails on the last unit.
- **Cons:** a function in no unit is listed nowhere but still occupies its name in the
  restaurant — a hidden blocker for the next creation with that name.

### Alternative D — name unique per unit
- **Pros:** two units may each have their own "Cozinheiro".
- **Cons:** see decision 3; it also makes a function enabled in every unit collide
  with any homonym in any unit, a rule no index can impose.

### Alternative E — identity exposes "bypasses unit scope" in the access grant
- **Pros:** reach is asked on the visibility axis it belongs to, not inferred from a
  capability.
- **Cons:** touches identity's facade and use case while Stage 2.7 is changing them.
  Kept as the candidate evolution (finding in the technical §7): if a future role gets
  multi-unit reach without `manage_tenant`, this is the shape to adopt.

### Alternative F — enable/disable one unit at a time
- **Pros:** smaller requests.
- **Cons:** two operations instead of one, and neither can turn "every unit" into a set
  without enumerating units; the replace shape covers both directions.

## Consequences

### Positive
- The catalogue keeps one owner and one uniqueness rule; unit listings show only what
  is enabled there.
- Migration is a column default: no backfill, no cross-BC read, no behaviour change.
- The reach rule is fail-closed and needs no identity change.

### Negative
- `manage_tenant` now carries a second meaning (catalogue for every unit). Recorded in
  `access_guard.py` next to the value.
- A manager cannot narrow or widen a function that is enabled in every unit; the owner
  does it.

### Neutral / trade-offs accepted
- Renaming and deleting a function keep the tenant-wide authorization of ADR 3.4.0008:
  a manager can still rename a function enabled only in another unit. Non-goal of this
  Stage; finding in the technical §7.

## Implementation notes

- `UnitEnablement` lives in `features/staff/domain/value_objects/`; `JobFunction`
  validates it in `__post_init__`, so rehydration of an inconsistent row fails loudly
  (ADR 3.4.0003 precedent).
- Persistence: `job_functions.enabled_in_all_units` (`boolean NOT NULL DEFAULT true`) and
  the link table `job_function_units`, with a composite foreign key to
  `job_functions (id, tenant_id)` `ON DELETE CASCADE` — the link rows are part of the
  aggregate, not a reference to it.
- Port laws: `L-JF1` persists the enablement with the row; `L-JF6` is the new
  `list_by_unit`; `L-JF7` is the new `update_enablement`, and `L-JF2` keeps writing
  only the name; contract suite keeps one body for fake and Postgres (ADR 3.3.0007).

## References

- Issue #41; `docs/stages/3.11-job-function-unit-enablement/concept.md`
- ADR 3.3.0001, ADR 3.3.0002, ADR 3.3.0007, ADR 3.4.0001, ADR 3.4.0003, ADR 3.4.0006,
  ADR 3.4.0007, ADR 3.4.0008, ADR 3.1.0006, ADR 3.2.0005, ADR 3.7.0001
- `docs/domain/staff/workforce.md` §3.2

---
title: ADR 3.4.0006 — Staff introduces two permissions in identity, and hr holds exactly the same staff operations as manager because the hr/manager divergence is about scheduling, not about reach
description: Architecture Decision Record
when-use: Reference before granting hr any scheduling permission in Step 4, before adding a staff permission, or when someone proposes giving hr cross-unit reach
keywords: [adr, rbac, permission, role, hr, manager, staff, scheduling, forward-constraint, identity]
status: accepted
created_at: 2026-08-12
updated_at: 2026-09-13
adr_id: 3.4.0006
decision: Identity gains MANAGE_STAFF and MANAGE_JOB_FUNCTIONS, both granted to owner, manager and hr; within staff hr and manager are equivalent, because the sponsor placed the hr/manager divergence on the scheduling axis (Step 4) rather than on reach — hr edits employee records including workload, shift preference and unavailability, and only manager/owner touch the schedule itself
context_stage: 3.4-staff-access-scope
bounded_context: staff
---

# ADR 3.4.0006 — Staff RBAC: two permissions, and hr ≡ manager inside staff

> ⚠️ **Errata (2026-09-13):** §3 "Stage 4.x must not grant `hr` any permission over the schedule" is superseded in part — the sponsor granted `hr` unit-scoped **read** access on 2026-09-13 (write/publish remain manager/owner only) — ver [ADR 4.1.0004](./4_1_0004-hr-reads-schedules-in-member-units.md)

## Status

`accepted`

## Context

`workforce.md` §4 (`accepted`) fixes four of the five roles for the staff
bounded context: `owner` manages the team and bypasses unit memberships;
`manager` manages the team of the units it belongs to; `employee` sees nothing
of staff; `platform_admin` has no restaurant access. It also states that *"é NO
STAFF que hr diverge do manager — visibilidade e permissões de equipe são o
único eixo de divergência"*, and explicitly assigns the **degree** of that
divergence to this Stage's concept.

Two facts made the question unanswerable from the repository:

- `Role.MANAGER` and `Role.HR` hold **identical** permission sets
  (`{MANAGE_USERS}`), so no divergence is expressible without new vocabulary.
- The only restaurant-facing permission that exists, `MANAGE_USERS`, is about
  **login accounts**. Reusing it for team management would mean that whoever can
  create a user account can manage the workforce, and vice versa — two unrelated
  capabilities welded together.

`permission.py` anticipates the extension: *"Semente enxuta do BC identity; as
Stages/BCs seguintes (`staff`, `scheduling`) estendem o vocabulário com as suas
próprias capacidades."*

The concept escalated the question. The sponsor answered on 2026-08-12, and
**reframed the axis** rather than picking one of the offered options.

## Decision

### 1. The divergence is by operation family, not by reach

Sponsor, verbatim: *"RH pode mexer nos cadastros dos funcionários (cadastrar,
desativar, editar etc). Apenas o gerente ou dono pode mexer na escala."*

Asked to disambiguate the boundary, the sponsor confirmed explicitly that
**contracted workload, shift preference and unavailability are `cadastro`** —
they are contractual and personal facts about the employee, not schedule
decisions — and that **hr edits them**. What manager and owner hold exclusively
is the **schedule itself**, which is Step 4 (bounded context `scheduling`).

### 2. Inside staff, hr and manager are equivalent

Every operation this Stage exposes belongs to the `cadastro` family. Therefore
`hr` and `manager` hold the **same** staff permissions and the **same** reach:
the units they are members of. The divergence the kickoff predicted is real, and
it materialises one Step later.

**hr does NOT receive cross-unit reach.** The concept offered that as its
recommended option (hr seeing every unit of the restaurant); the sponsor did not
take it, and this ADR records the rejection explicitly so the recommendation is
not later mistaken for the decision.

### 3. Forward constraint on Step 4 (binding)

**Stage 4.x must not grant `hr` any permission over the schedule.** This is the
whole content of the hr/manager divergence, and it lives outside this Stage.
Recorded here, in the ADR that creates the permissions, because that is the file
a Step 4 author reads before extending the role map.

### 4. Two permissions, not one

Identity gains, in `features/identity/domain/value_objects/permission.py`:

| Permission | Family | Scope |
|---|---|---|
| `MANAGE_STAFF` | employee records — the twelve employee routes | **unit-scoped** |
| `MANAGE_JOB_FUNCTIONS` | the job-function catalogue — the four catalogue routes | **tenant-wide** (ADR 3.4.0008) |

They are two because they must differ on the unit axis: the catalogue belongs to
the restaurant (`workforce.md` §3.2) and cannot require a unit target, while
employee records must require one. A single permission cannot be both.

Splitting them also makes issue #41 expressible later: "my unit's functions" vs
"all units' functions" is a distinction that needs the catalogue capability to
be its own thing.

`_ROLE_PERMISSIONS` gains both for `OWNER`, `MANAGER` and `HR`. `EMPLOYEE` and
`PLATFORM_ADMIN` gain nothing.

### 5. This is a declared target-layer expansion into `features/identity/domain`

The sponsor authorised it explicitly: *"não há problema em tocar o módulo de
acesso — isso irá acontecer ao longo do desenvolvimento quando forem surgindo
mais features."* The roadmap block of Stage 3.4 gets the reconciliation note.

## Alternatives considered

### Alternative A — hr manages every unit of the restaurant; manager only its own
- **Description:** the divergence is **reach**: hr bypasses unit memberships.
- **Pros:** it is the literal reading of "diverge na **visibilidade**"; matches
  how an HR department usually operates across a whole company.
- **Cons:** it hands cross-unit power to a role that has none today, and it does
  not reflect how the sponsor's restaurants work.
- **Why rejected:** **the sponsor rejected it.** It was this concept's
  recommended option; recorded here so that the recommendation is not read back
  as the decision.

### Alternative B — hr is a reduced manager (registration only, no workload/preference/unavailability)
- **Description:** hr creates and renames employees; workload, shift preference
  and unavailability are manager-only.
- **Pros:** a tidy line between "who the person is" and "how the person works".
- **Cons:** the sponsor rejected the premise: workload, preference and
  unavailability **are** registration data — contractual and personal facts —
  and HR is precisely who holds them. The tidy line was tidy in the wrong place.
- **Why rejected:** it misclassifies three of the twelve operations.

### Alternative C — hr ≡ manager everywhere, forever
- **Description:** no divergence at all, in any Step.
- **Pros:** simplest; no forward constraint to remember.
- **Cons:** it discards a ratified decision (kickoff #10, `workforce.md` §4)
  instead of scheduling it. The divergence exists; it just is not here.
- **Why rejected:** the outcome inside staff is identical, but the record would
  be wrong, and Step 4 would have no constraint to honour.

### Alternative D — reuse `MANAGE_USERS` for staff
- **Description:** no new permission.
- **Pros:** zero change to identity.
- **Cons:** welds "manage login accounts" to "manage the workforce", so granting
  one silently grants the other; and it makes the hr/manager divergence
  permanently inexpressible.
- **Why rejected:** it collapses two unrelated capabilities to avoid a
  three-line change.

## Consequences

### Positive
- The staff capability is named, so an audit of who can touch the workforce is a
  grep over `_ROLE_PERMISSIONS`, not a reading of routes.
- Issue #41 and Step 4 both inherit a vocabulary that can express their
  distinctions without another refactor.

### Negative
- **Identity's domain is edited by a staff Stage.** Authorised, but it means the
  role map now has entries no identity Stage introduced, and a reader of
  `role.py` must follow the ADR trail to know why. Mitigated by the map's
  existing totality test, which forces every role to be classified.
- The forward constraint of §3 is enforced by this document and by a test only
  once Step 4 exists. Until then it is a written commitment.

### Neutral / trade-offs accepted
- Inside this Stage, `hr` and `manager` are indistinguishable, so no test can
  observe the divergence yet. The acceptance criterion asserts the **equality**
  instead — which is the property that is actually true today.

## References
- Sponsor decision, 2026-08-12 (via the coordinating session), on fork F1 of
  `docs/stages/3.4-staff-access-scope/concept.md`
- `docs/domain/staff/workforce.md` §4; kickoff decision #10
- `src/restaurant_hub/features/identity/domain/value_objects/{role,permission}.py`
- ADR 2.2.0002 (two fail-closed axes), ADR 2.4.0003 (composition at the boundary)
- ADR 3.4.0008 (tenant-wide permissions)
- Issue #41 — per-unit enablement of job functions

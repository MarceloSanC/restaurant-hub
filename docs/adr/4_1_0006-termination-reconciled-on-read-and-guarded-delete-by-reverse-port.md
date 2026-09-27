---
title: ADR 4.1.0006 — Employee termination is reconciled on read by scheduling (no cross-BC write, no domain event, no outbox); inactive records are invisible in every scheduling view; definitive removal keeps the L-E5 guard through a reverse query port in staff implemented outside staff, without a foreign key
description: Architecture Decision Record
when-use: Reference before making staff write anything into scheduling on termination or removal, before adding a domain-event dispatcher or an outbox for staff → scheduling propagation, before showing an inactive employee anywhere in the schedule, calendar, image or e-mail, before implementing EmployeeInUseError, or when a future "employee history" page needs to reopen access to inactive records
keywords: [adr, scheduling, staff, termination, deactivate, reconcile-on-read, read-model, staff-read-port, employee-in-use, guarded-delete, reverse-port, composition-root, no-foreign-key, domain-event, outbox, cross-bc, domain-gate]
status: accepted
created_at: 2026-09-14
updated_at: 2026-09-26
adr_id: 4.1.0006
decision: When staff terminates an employee record (active=False) nothing is written into scheduling — no domain event, no dispatcher, no outbox, no port hook; every scheduling read consults the record's current state through StaffReadPort and omits an inactive record entirely (including its past allocations) until a future employee-history page exists; definitive removal keeps the L-E5 guard (EmployeeInUseError) through a reverse query port declared in staff and implemented outside staff (location decided by the 4.4 technical) over a scheduling query, with no foreign key between bounded contexts, generalisable to demanded job functions.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0006 — Termination reconciled on read; guarded delete by reverse query port

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Taken at the **domain gate of Step 4** for
[`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md): fork
F7 of the gate triage (the draft's HALT H1) and its sub-question about definitive removal.
Decided by the **human sponsor** (Marcelo) on **2026-09-14**, after an architecture research
pass he had requested on 2026-09-13 (*"isso é uma questao melhor respondida por uma pesquisa de
arquitetura de software, nao por suposicao, buscar a alternativa que possui melhor
desacoplamento de açao"*).

Forces:

- **Product rule already given by the sponsor (2026-09-13):** when an employee is removed or
  terminated, *"automaticamente os dados dele que estavam em escala ou como fucionario devem ser
  desativados, fica apenas a conta dele como desativada e os registros historicos"*. Nothing is
  erased; the question was the **mechanism** by which scheduling reflects a change that happens
  in staff.
- **Two ratified positions contradicted each other (HALT H1).** [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md)
  (Implementation notes) and [ADR 3.4.0002](./3_4_0002-staff-http-error-status-mapping.md)
  (§Decision 5) assumed that Step 4 would add a **foreign key** allocation → employee and that
  the FK would be "the hard half of the `delete` guard" producing `EmployeeInUseError` (staff
  law L-E5). [ADR 3.3.0002](./3_3_0002-no-cross-bounded-context-foreign-keys.md) fixed **"no
  foreign keys between bounded contexts"** and warned (Alternative C) that Step 4 "will face the
  same fork with no precedent". Bounded contexts talk through ports, with ids as opaque strings
  (`.importlinter` `bc-independence`; `identifiers.py`).
- **Staff's termination is a boolean** (`active`, [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md));
  there is no termination date. The terminated record leaves the unit listing by default but
  stays readable by id; rehire is an explicit, idempotent transition.
- **Every saved change is the live schedule** ([ADR 4.1.0001](./4_1_0001-every-saved-change-is-the-live-schedule.md)):
  there is no draft in which a "deactivate allocations" step could hide.
- **The research** (`f7-architecture-research.md`, 2026-09-13; sources in §References) compared
  five mechanisms — A: in-process event in the **same** transaction; B: in-process event
  dispatched **after** staff's commit (with an outbox as later evolution); C: a direct port hook
  from staff into scheduling; D: **reconcile on read**; E: FK/trigger in the database — and
  **recommended B**, on the strength of Vernon ("use eventual consistency outside the
  boundary"; "ask whose job it is"), Evans ("across boundaries, handle updates asynchronously"),
  Microsoft ("integration events … only if the entity is successfully persisted"), Grzybek
  ("Messaging — ensures the lowest coupling") and Khononov (contract coupling at high distance =
  loose coupling). It listed D's costs explicitly: no termination date to cut "future × past",
  no audit entry on the schedule, and the rule living on every read path.

## Decision

### 1. Termination is reconciled on read (F7)

Sponsor, verbatim: *"nao deveria mudar um parametro no banco dizendo que aquela conta nao esta
mais ativa, e em qualquer proxima requisicao que envolver o dado, ja busca do banco com essa
informacao atualizada (assim como um refresh F5)"*.

- **Staff only sets `active=False`** — the transition that already exists. **Nothing is written
  into scheduling** on termination: no domain event, no dispatcher, no outbox, no port hook.
- **Every scheduling read consults the record's current state** through `StaffReadPort`
  (roadmap Stage 4.3) and treats an inactive record accordingly. The rule applies to **all**
  reads, present and future: live schedule, calendar, "my schedule", past schedules, the
  rendered image (4.7) and the notification recipients (4.6).

### 2. An inactive record is invisible everywhere — until an employee-history page exists

Sponsor, verbatim (sub-question on definitive removal): *"Manter a guarda, mas por enquanto o
perfil ou qualquer informacao dele nao aparece mais em qualquer tela, no futuro quando for
prioridade criamos a pagina de consultar historico de funcionarios, que ai sim vai ser possivel
buscar as informacoes historicas daquela conta."*

An inactive record **does not appear on any scheduling screen — not even its past
allocations**. The data stays in the database (nothing is erased); a future **employee-history
page** (evolution, domain doc §5) reopens access to it. Until then, the timeclock (Step 7) and
the hub (Step 8) do not show inactive records either.

### 3. Definitive removal keeps L-E5 through a reverse query port, without a foreign key

The guard is **kept**: `delete` is refused with `EmployeeInUseError` while **any** allocation —
future or historical — references the record. The mechanism is a **reverse query port declared
in staff** ("is this record referenced?"), **implemented outside staff** by a staff-side
adapter/translator over a scheduling query (`has_allocations_for(tenant, unit, employee)`) —
the form of [ADR 3.4.0001](./3_4_0001-staff-owned-access-guard-port.md) (BC-owned port,
translator outside the BC) as revised by issue #47: **where** the translator lives (composition
root vs. `adapters/out/`) is a decision of the Stage 4.4 `technical.md`, not of this ADR. **No foreign key** between bounded contexts: this
fulfils the prediction of ADR 3.3.0002 Alternative C. The same port generalises to a **demanded
job function** (`JobFunctionInUseError`) without a new import pair; the Stage in which staff
starts consulting it is a concept gap (4.3/4.4).

### 4. What is explicitly deferred or left to Stage concepts

- Whether to **clear future allocations at termination time** (the sponsor did not ask for it;
  default: do not clear) — Stage 4.3 concept.
- **Batch reads** of `StaffReadPort` to bound the per-read cost — Stage 4.3/4.4 concept.
- The **employee-history page** and the exposure of inactive records to Steps 7/8 — evolution;
  roadmap scope gap for the Step 7 and Step 8 domain gates.

## Alternatives considered

### Alternative A — In-process domain event dispatched inside staff's transaction
- **Description:** `deactivate_employee` records `EmployeeTerminated`; a shared unit of work
  dispatches it before commit; the scheduling handler writes in the same transaction.
- **Pros:** atomic: both sides roll back together.
- **Cons:** requires the unit of work the project does not have (issue #46); a transaction
  spanning bounded contexts is what Evans, Vernon and Grzybek say not to do ("no transactions
  between them"); welds staff and scheduling to one database — the objection ADR 3.3.0002 made
  to the FK.
- **Why rejected:** blocked and architecturally wrong for a cross-BC crossing; the sponsor
  chose D anyway.

### Alternative B — In-process domain event dispatched after staff's commit (the research's recommendation)
- **Description:** staff publishes `EmployeeTerminated(tenant, unit, employee, occurred_at)`
  through a `DomainEventPublisher` port in `shared`; a synchronous in-memory dispatcher wired in
  the composition root calls a scheduling use case `DeactivateAllocationsOfEmployee` in its own
  transaction; an outbox is a later evolution behind the same port.
- **Pros:** contract coupling at high distance (Khononov); staff knows nobody; the same
  skeleton serves `JobFunctionRemoved`, `UnitDeactivated`, `SchedulePublished` (e-mail, Step 7);
  future database separation swaps the dispatcher for an outbox without touching staff; the
  schedule gets an audit entry ("deactivated by termination — system, when"); "future × past"
  is cut at `occurred_at`. Recommended by the research on Vernon, Evans, Microsoft, Grzybek and
  Khononov.
- **Cons:** two new concepts (event, dispatcher) and ~6–8 small files in v1; implicit flow
  (Fowler: "hard to see such a flow as it's not explicit in any program text"), mitigated by a
  single subscription site and a test; a residual window between staff's commit and the handler.
- **Why rejected:** **the sponsor overrode the recommendation.** Asked to choose, he answered
  that nothing should be propagated — *"nao deveria mudar um parametro no banco … e em qualquer
  proxima requisicao que envolver o dado, ja busca do banco com essa informacao atualizada
  (assim como um refresh F5)"* — preferring the simplicity of reading the current state over an
  event skeleton the pilot does not need yet. Recorded verbatim so the research's
  recommendation is not later read back as the decision.

### Alternative C — Direct port hook (staff port "on employee deactivated" → scheduling use case)
- **Description:** staff declares a listener port; the composition root (C1) or a facade +
  gateway pair (C2) implements it by calling scheduling.
- **Pros:** fewer files than B; explicit call.
- **Cons:** C1 grows behaviour in the composition root file the linter does not gate (#45),
  one method per reaction, nothing reusable; C2 makes the upstream (staff) depend on the
  downstream (scheduling) — a bidirectional BC dependency with no support in the sources;
  functional coupling if the port names scheduling's intent.
- **Why rejected:** same write-side machinery as B with worse coupling; the sponsor chose no
  propagation at all. (The **query** form of C1 survives as the L-E5 guard — §3 — because a
  question needs an answer and an event cannot give one.)

### Alternative E — Foreign key / trigger in the database
- **Description:** `allocations.employee_id → employees.id` with `ON DELETE RESTRICT`, plus a
  trigger on `active` to deactivate future allocations.
- **Pros:** the database answers the guard alone.
- **Cons:** intrusive coupling; `bc-independence` green in Python and false in SQL; `ON DELETE`
  does not cover `active=False`, so a business rule ("only future ones") would live in SQL.
- **Why rejected:** ADR 3.3.0002 already rejected it; the sponsor kept the guard in application
  code.

### Sub-question alternative — Cascade delete on definitive removal
- **Description:** drop L-E5; removing the record deletes or orphans its allocations.
- **Pros:** no reverse port.
- **Cons:** erases history the hub reads; an orphan allocation shows "unknown employee"; L-E5 is
  a ratified staff law with `EmployeeInUseError` already in the error hierarchy.
- **Why rejected:** the sponsor: *"Manter a guarda"*.

### Do nothing / status quo
Not acceptable: two ratified ADRs assumed a FK that a third forbids; Step 4 needed one answer
before Stage 4.3 designs `StaffReadPort` and Stage 4.4 designs the schema.

## Consequences

### Positive
- **Zero propagation machinery in v1**: no event, dispatcher, outbox, handler or cross-BC write
  path. Staff stays upstream and knows nobody; scheduling reads staff as it already must.
- Consistency is never "in flight": there is no window between two commits, no retry, no
  compensation — the current state is what the next request reads.
- `bc-independence` stays honest in Python **and** in SQL (no FK); the reverse query port keeps
  the guard in application code in the form the project already validated (ADR 3.4.0001).
- ADR 3.3.0002's Alternative C is fulfilled with a precedent for the next cross-BC reference
  (demanded job function; unit deactivation in identity).

### Negative — the five declared limits of the v1 (recorded, not hidden)
1. The demand an inactive record covered **reads as uncovered**; the manager re-fills it. There
   is no automatic "vacancy reopened" signal beyond the coverage figure.
2. Planned × actual (Step 7), past schedules and the hub (Step 8) **do not show inactive
   records** until the employee-history page exists — a roadmap scope gap for the Step 7 and
   Step 8 gates.
3. Termination leaves **no audit entry on the schedule**: the schedule "changed" on read without
   an edit; the audit of the act belongs to staff. (Under B the schedule would have carried
   "deactivated by termination — system, when".)
4. **Rehire** (ADR 3.2.0006) makes the old allocations — including future ones never cleared —
   **reappear**. Clearing future allocations at termination is a Stage 4.3 concept gap; the
   default is not to clear.
5. The rule applies to **every** read, present and future: a per-read cost and one more thing
   each new consumer (hub, timeclock, image) must implement. Mitigated by batch reads of
   `StaffReadPort` (4.3/4.4).

### Neutral / trade-offs accepted
- With no termination date in staff, the "future × past" cut that the sponsor's 2026-09-13 rule
  implied is not computed at all: the inactive record is simply omitted, past and future alike,
  which is what the sub-question answer asks for.
- Identity's session revocation on termination (Stage 3.5, draft: a direct call) is untouched —
  with no dispatcher there is nothing for it to migrate to.
- The event skeleton described under B remains available as a future evolution if a consumer
  ever needs a write-side reaction (e.g. audit on the schedule); nothing in this decision
  blocks it.

## Implementation notes

- Stage 4.3: `StaffReadPort` returns the record's `active` state; every read use case filters
  on it (batch lookup per schedule/calendar). Stage 4.4: no FK; a scheduling query
  `has_allocations_for(tenant, unit, employee)` (and later `has_demands_for(tenant, function)`).
  Staff: a reverse query port (declared expansion, one method), consulted by `delete`; the
  translator lives **outside staff** — `composition_root.py` today, `adapters/out/` if issue #47
  moves it — and **where** is a decision of the 4.4 `technical.md`. The Stage that wires it is a
  concept gap (4.3/4.4).
- Theory: [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.3, §3.4, §3.7,
  §3.10.1, §6; [`workforce.md`](../domain/staff/workforce.md) §3.1 (dated note 2026-09-14).

## References

- Related ADRs: [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md)
  (termination state; guarded removal; errata 2026-09-14 on "the FK becomes the hard half of the
  `delete` guard"); [ADR 3.4.0002](./3_4_0002-staff-http-error-status-mapping.md) (errata
  2026-09-14 on "via the 3.3 foreign key"); [ADR 3.3.0002](./3_3_0002-no-cross-bounded-context-foreign-keys.md)
  (no cross-BC FKs — Alternative C fulfilled); [ADR 3.4.0001](./3_4_0001-staff-owned-access-guard-port.md)
  (BC-owned port with translator outside the BC — the form reused for the guard);
  [ADR 3.2.0007](./3_2_0007-terminated-employee-remains-editable.md) (rehire is explicit);
  [ADR 4.1.0001](./4_1_0001-every-saved-change-is-the-live-schedule.md) (live schedule; audit
  log); [ADR 2.2.0004](./2_2_0004-synchronous-port-signatures.md) (synchronous ports).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.4
  (rule, five limits), §3.3, §3.7, §3.10.1, §5, §6; [`docs/domain/staff/workforce.md`](../domain/staff/workforce.md)
  §3.1; `docs/stages/3.2-staff-application/concept.md` 301–308 (law L-E5).
- `.importlinter` (`bc-independence`, lines 219–228);
  `src/restaurant_hub/features/staff/domain/value_objects/identifiers.py` 5–7.
- Sponsor decisions: 2026-09-13 (product rule; research requested) and 2026-09-14 (F7 →
  reconcile on read; sub-question → keep the guard, inactive invisible) — session record
  `gate-decisions.md`, "Rodada 2". Research: `f7-architecture-research.md` (2026-09-13), whose
  recommendation (B) the sponsor overrode.
- External (primary; consulted by the research on 2026-09-13 and cited in the alternatives
  above):
  - VERNON, Vaughn. **Effective Aggregate Design — Part II: Making Aggregates Work Together**.
    2011. ("Reference Other Aggregates By Identity"; "Use Eventual Consistency Outside the
    Boundary"; "Ask Whose Job It Is".) Disponível em:
    https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf. Acesso
    em: 13 set. 2026.
  - EVANS, Eric. **Domain-Driven Design Reference: Definitions and Pattern Summaries**. Domain
    Language, 2015. ("Within an aggregate boundary, apply consistency rules synchronously.
    Across boundaries, handle updates asynchronously."; Domain Events.) Disponível em:
    https://www.domainlanguage.com/ddd/reference/. Acesso em: 13 set. 2026.
  - FOWLER, Martin. **Domain Event**. martinfowler.com (PoEAA development), 2005. Disponível em:
    https://martinfowler.com/eaaDev/DomainEvent.html. Acesso em: 13 set. 2026.
  - FOWLER, Martin. **What do you mean by "Event-Driven"?** martinfowler.com, 2017. (Event
    Notification: "the source system doesn't really care much about the response"; "hard to see
    such a flow".) Disponível em: https://martinfowler.com/articles/201701-event-driven.html.
    Acesso em: 13 set. 2026.
  - MICROSOFT. **Domain events: design and implementation**. .NET Microservices: Architecture
    for Containerized .NET Applications, 2024. ("integration events … should occur only if the
    entity is successfully persisted"; deferred dispatch before/after commit.) Disponível em:
    https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/domain-events-design-implementation.
    Acesso em: 13 set. 2026.
  - GRZYBEK, Kamil. **Modular Monolith: Integration Styles**. 2020. ("no transactions between
    them"; Direct Call vs Messaging.) Disponível em:
    https://www.kamilgrzybek.com/blog/posts/modular-monolith-integration-styles. Acesso em:
    13 set. 2026.
  - RICHARDSON, Chris. **Pattern: Transactional outbox**. microservices.io. ("Messages are
    guaranteed to be sent if and only if the database transaction commits".) Disponível em:
    https://microservices.io/patterns/data/transactional-outbox.html. Acesso em: 13 set. 2026.
  - KHONONOV, Vlad. **Balanced Coupling — Integration Strength; Balance**. coupling.dev (site of
    *Balancing Coupling in Software Design*, Addison-Wesley, 2024). (Intrusive / functional /
    model / contract coupling; "(STRENGTH XOR DISTANCE) OR NOT VOLATILITY".) Disponível em:
    https://coupling.dev/. Acesso em: 13 set. 2026.

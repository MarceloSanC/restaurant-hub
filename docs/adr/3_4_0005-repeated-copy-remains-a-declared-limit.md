---
title: ADR 3.4.0005 — Repeated copy of an employee into the same unit stays a declared limit, because the only guard available at the boundary would forbid legitimate homonyms
description: Architecture Decision Record
when-use: Reference before adding a duplicate-detection guard to the copy route, or when someone proposes making employee names unique within a unit
keywords: [adr, copy, duplication, idempotency, homonyms, boundary, thin-adapter, staff]
status: accepted
created_at: 2026-08-12
updated_at: 2026-08-12
adr_id: 3.4.0005
decision: The copy route adds no duplicate-detection guard; the only heuristic available at the boundary — a name already present in the destination unit — is false by construction because the domain declares homonyms legitimate, so the limit stays declared and the response makes the outcome observable through a distinct new id
context_stage: 3.4-staff-access-scope
bounded_context: staff
---

# ADR 3.4.0005 — Repeated copy remains a declared limit

## Status

`accepted`

> **Decidido na Stage 3.4, executado na Stage 3.6.** A Stage `3.4-staff-http`
> foi cortada em duas (CONVENTIONS §6 — 14 Tasks): `3.4-staff-access-scope`
> entrega a fundação de acesso e escopo, e `3.6-staff-http` entrega a borda HTTP.
> Esta decisão é de **borda**, logo governa a 3.6. O `context_stage` continua
> apontando para a 3.4 porque o campo registra a Stage em que a decisão foi
> **tomada** (CONVENTIONS §2), e ADR `accepted` não migra.

## Context

Stage 3.2 fixed the semantics of `copy_employee_to_unit`: it **duplicates the whole
record** into another unit of the same tenant (ADR 3.2.0003), with an explicit
exclusion list, and the two records are independent afterwards. It also recorded a
limit and escalated it:

> **`[finding]` para a 3.4 — cópia repetida para o mesmo destino.** Sem guarda
> possível nesta camada (§5.11); a borda deve tornar a operação explícita
> (confirmação / feedback de que já existe registro homônimo na unidade destino).

Two facts constrain what the boundary can actually do:

- **The record has no natural key.** `Employee.name` is verbatim and explicitly
  **not unique** — the entity's own docstring says *"não-único (homônimos são
  legítimos)"*, and Stage 3.3's schema carries no unique index over
  `(unit_id, name)`. So "a record with this name already exists in the destination"
  does not mean "this is a repeated copy"; it also, and much more often, means "two
  people share a name".
- **The copy carries no provenance.** ADR 3.2.0003 duplicates the record without a
  `copied_from` field, deliberately: the two records are independent. Nothing in the
  data distinguishes a second copy from an independent registration.

The remaining ideas — an idempotency key, a `confirm=true` flag — are boundary
protocol, and both push a decision onto a client that this version of the product
does not have (frontend is out of scope for the whole Step).

## Decision

**The copy route adds no duplicate-detection guard.** `POST /units/{unit_id}/employees/{employee_id}/copies`
performs the two authorization calls (source unit, destination unit — concept §5.6),
calls the use case, and returns **201** with the new record.

**The limit stays declared**, in concept §5.7, and what the boundary owes —
"make the operation explicit" — is discharged by the response itself: the body
carries an `id` **different** from the source and a `unit_id` equal to the
destination, so a client can tell exactly what was created, and the destination's
listing shows both records immediately.

**The residual concern is escalated as a UX finding**, with the first frontend
Stage of Step 3 as the candidate. A confirmation dialogue is a legitimate answer to
this problem; it is just not an API answer.

## Alternatives considered

### Alternative A — 409 when the destination unit already holds a record with the same name
- **Description:** the router lists the destination unit and refuses on a name
  match.
- **Pros:** catches the accidental double-click.
- **Cons:** it is **wrong by construction** — it would refuse the legitimate
  registration of a second person with the same name, which the domain explicitly
  permits and which a restaurant will hit (two "João Silva" in one unit is
  ordinary). It also puts a business rule in the adapter, which the
  `fastapi-thin-adapter` skill forbids, and invents a uniqueness constraint that
  Stages 3.1 and 3.3 both declined to create.
- **Why rejected:** it trades a rare annoyance for a recurring false refusal, and
  it does so by inventing a domain rule at the boundary.

### Alternative B — a non-refusing informative field in the 201 body
- **Description:** the copy succeeds always, and the response carries something like
  `homonyms_in_target: N` — the literal *"feedback de que já existe registro
  homônimo na unidade destino"* the finding asks for, with no refusal attached.
- **Pros:** it is the only option that answers the finding's second clause as
  written, and it refuses nothing, so it cannot reject a legitimate registration.
- **Cons:** it costs an extra listing query on **every** copy, to produce a number
  the client can obtain itself with one `GET` on the destination — and, worse, the
  number **does not mean what its name suggests**. A homonym is not a duplicate;
  the field would read as "you already copied this" while measuring "two people
  share a name". A field whose name implies a fact it does not establish is a worse
  artefact than its absence, because it will be trusted.
- **Why rejected:** it buys the letter of the finding at the price of a misleading
  signal. **Recorded explicitly because rejecting it silently would mean closing
  the finding on a truncated quote** — the finding asked for two things, and this
  ADR refuses both, for different reasons.

### Alternative C — idempotency key header (`Idempotency-Key`)
- **Description:** the client sends a key; the server stores it and replays the
  first response.
- **Pros:** the correct general solution to duplicate submission, and it is
  content-agnostic, so no false refusals.
- **Cons:** requires persisted keys with a retention policy — a table, a migration,
  an expiry job — i.e. a Stage of its own; and it protects **only** clients that
  choose to send the key, so it is not a guard, it is an opt-in. It would also be
  the first cross-cutting protocol concern in the codebase, and it belongs in
  `shared`, not in staff.
- **Why rejected:** correct but disproportionate here, and it is the wrong Stage to
  introduce a cross-cutting protocol facility. Recorded as the shape to reach for
  if duplicate submission becomes a real operational problem.

### Alternative D — `confirm=true` query parameter
- **Description:** the first call returns 409 with a hint; the caller repeats with
  `confirm=true`.
- **Pros:** cheap; no storage.
- **Cons:** it still needs a detector to decide when to demand confirmation, so it
  inherits Alternative A's false-positive problem entirely — plus it makes the
  route non-idempotent in a second, protocol-level way, and moves UX into the API.
- **Why rejected:** it is Alternative A with an extra round trip.

### Alternative E — make the record's name unique within the unit
- **Pros:** would make duplicate detection sound.
- **Cons:** contradicts ADR 3.1.0002 and the entity contract, and would break real
  restaurants.
- **Why rejected:** it changes the domain to make an adapter convenience possible.

## Consequences

### Positive
- No legitimate registration is ever refused.
- The adapter stays thin: authorize, convert, call, map.
- The response is sufficient for a client to detect duplication itself, because the
  new `id` is returned and the listing is authoritative.

### Negative
- **A double-click creates two records.** They are indistinguishable afterwards, by
  the same design that makes homonyms legitimate, so cleanup means deleting one by
  id — which the delete route supports (guarded by `EmployeeInUseError` from
  Step 4 onward).
- The Stage 3.2 finding is closed with "declared limit" rather than with a guard,
  which is a weaker outcome than the finding's wording suggested. Stated plainly
  here so the record does not read as a silent drop.

### Neutral / trade-offs accepted
- The UX answer is deferred to the frontend, where the confirmation actually
  belongs and where the operator has the context to confirm.

## References
- `docs/stages/3.2-staff-application/concept.md` §5.11, §10 (`[finding]`)
- ADR 3.2.0003 (copy duplicates the whole record), ADR 3.1.0002 (minimal employee
  attributes, verbatim non-unique name)
- `src/restaurant_hub/features/staff/domain/entities/employee.py` (docstring:
  homonyms are legitimate)
- `docs/stages/3.4-staff-access-scope/concept.md` §13 (fronteira com a 3.6) — esta
  decisão é executada na **3.6**; o desenho da rota de cópia e os critérios estão no
  commit `d878060`, em `docs/stages/3.4-staff-http/concept.md` §5.6-5.7 e §11
- `docs/roadmap.md` — bloco Stage 3.6
- Skill `fastapi-thin-adapter`

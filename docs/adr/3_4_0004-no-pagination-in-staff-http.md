---
title: ADR 3.4.0004 — The staff HTTP listings ship unpaginated, keeping L-ORD as a cursor that is prepared but not yet spent
description: Architecture Decision Record
when-use: Reference before adding LIMIT/OFFSET or a cursor parameter to a staff listing, or when the ORDER BY regex of the conduct suite starts failing on a correct adapter
keywords: [adr, pagination, cursor, ordering, l-ord, collation, listing, staff, scope]
status: accepted
created_at: 2026-08-12
updated_at: 2026-08-12
adr_id: 3.4.0004
decision: Stage 3.4 exposes both staff listings unpaginated, because paginating would retroact the port signatures of Stages 3.2 and 3.3; L-ORD remains the prepared cursor, and the one-line antidote for the ORDER BY regex is escalated together with the pagination that will need it
context_stage: 3.4-staff-http
bounded_context: staff
---

# ADR 3.4.0004 — No pagination in the staff HTTP listings

## Status

`accepted`

## Context

Stage 3.3 introduced `L-ORD` (ADR 3.3.0003): a total-ordering law on both staff
ports, `ORDER BY name COLLATE "C", id COLLATE "C"`, explicitly designed so that
`(name, id)` can serve as a **pagination cursor**. The roadmap's 3.3 note says the
law is *"contrato consumido pela 3.4, cuja paginação usa `(name, id)` como cursor"*.

That sentence describes an intent, not a requirement, and the requirement side of
the record says something else:

- The roadmap's **3.4 block** states a DoD about *"gerente cria função custom e
  funcionário com jornada; funcionário de outra unidade não aparece"* and
  `complexidade_estimada: S`. Pagination appears nowhere in it.

  > The same block also declares `contratos_introduzidos: []`, and that field is
  > **deliberately not used as evidence here**: Stage 3.4's concept §1 shows the
  > field does not describe the Stage (four contracts are introduced) and
  > reconciles it in the dated note. Citing a field as proof in one section while
  > refuting it in another would be the kind of convenient reading this project
  > has already been caught making.
- The two ports have **no cursor parameters**:
  `JobFunctionRepository.list_by_tenant(tenant_id)` and
  `EmployeeRepository.list_by_unit(tenant_id, unit_id, *, include_inactive)`.
  Adding pagination means changing both Protocols, both fakes, both Postgres
  adapters and the promoted contract suites — i.e. amending two closed Stages.

There is also a booby trap. Stage 3.3's audit escalated a `[finding]`: the regex
`_ORDER_BY = re.compile(r'ORDER BY (?P<clausula>.+?)(?:\s*$)', re.DOTALL)` in
`tests/integration/.../test_staff_conduct.py:194` captures everything after
`ORDER BY` to the end of the statement, and the three CA10b assertions compare that
capture by **equality**. Today the `ORDER BY` is the last element of all three
statements, so the assertions are exactly right — and equality is the correct form,
because a substring assertion would accept `ORDER BY name, id COLLATE "C"`, which
puts `name` in the database collation. The moment `LIMIT`/`OFFSET` is appended, the
capture swallows them, the three equalities fail **on a correct adapter**, and the
signal reads as a collation regression.

## Decision

**Stage 3.4 ships both listings unpaginated.** `GET /job-functions` and
`GET /units/{unit_id}/employees` return the full collection in the port's order.

**`L-ORD` stays a prepared cursor, not a spent one.** Nothing about the law
changes; it simply is not consumed as a cursor yet, and the Stage that consumes it
inherits a guarantee that is already tested against Postgres.

**Two ratified sentences become false and are corrected, not left standing.** The
roadmap's 3.3 note (*"contrato consumido pela 3.4, cuja paginação usa `(name, id)`
como cursor"*) and the 3.3 technical's finding (*"a paginação da 3.4 acrescenta
`LIMIT`/`OFFSET`"*) both assert that this Stage paginates. Both are corrected in the
dated note of the 3.4 roadmap block: the cursor is **prepared, not consumed**.
Leaving them standing would be exactly the "document asserting something about
another file without checking" failure the project already recorded.

**The regex antidote is escalated with the pagination, not applied now.** With no
`LIMIT`/`OFFSET`, the regex is correct as written, and changing it today would edit
a passing assertion for a condition that does not exist — the kind of pre-emptive
edit that later reads as unexplained. The antidote is one line — anchor the capture
at the end of the ordering clause, e.g. `(?=\s+LIMIT|\s+OFFSET|\s*$)` — and the
`[finding]` names it, so whoever adds pagination applies both in the same commit.

## Alternatives considered

### Alternative A — cursor pagination now, using `(name, id)`
- **Description:** add `after: (name, id) | None` and `limit` to both ports and
  both adapters; expose `?after=&limit=` on both routes.
- **Pros:** consumes `L-ORD` for the purpose it was designed for; the collection
  endpoints never become unbounded; correct under concurrent insertion, unlike
  offset.
- **Cons:** amends the Protocols, fakes, Postgres adapters and the promoted
  contract suites of two closed Stages — precisely the retroaction that publishing
  `L-ORD` and `EmployeeInUseError` early was meant to avoid. It also breaks the
  conduct suite's regex, so the same PR must touch a test whose failure mode is
  misleading. And it inflates a Stage the roadmap sized `S` and that already grew
  by a guard, a port, an adapter and a domain expansion.
- **Why rejected:** the port change is real work with no requirement behind it in
  this Stage. Deferred, not refused — this is the shape the future Stage should
  take.

### Alternative B — offset pagination (`?page=&size=`)
- **Pros:** trivial to implement; familiar to clients.
- **Cons:** it is the option `L-ORD` was designed to make unnecessary. Under
  concurrent insertion, offset paging silently skips and repeats rows, and doing it
  *while* a stable cursor sits unused would be an odd record to leave.
- **Why rejected:** strictly worse than A, and A is already deferred.

### Alternative C — a hard cap without a cursor (e.g. return at most 500)
- **Pros:** bounds the response with no port change.
- **Cons:** truncates without telling the client, which is data loss disguised as a
  limit; and there is no way to fetch the remainder.
- **Why rejected:** silent truncation is worse than an unbounded list of a size the
  domain bounds anyway.

### Alternative D — do nothing *and not record it*
Leaving the decision implicit would let the next reader assume pagination was
forgotten, and would leave the regex trap unattributed. The decision is cheap; the
record is the point.

## Consequences

### Positive
- Two closed Stages keep their contracts intact.
- The conduct suite stays green **without editing**, which is itself an acceptance
  criterion of this Stage (CA35): the absence of a test edit is evidence that no
  ordering behaviour changed.
- The Stage stays inside a defensible size after already absorbing a port, an
  adapter and a domain expansion.

### Negative
- **Both listings are unbounded.** A tenant with thousands of job functions, or a
  unit with thousands of employee records, gets one large response. The domain
  bounds this in practice — functions are a hand-curated catalogue, and employee
  records are per unit — but it is a real limit, not a proof.
- The client cannot page, so a future UI that wants infinite scroll waits for the
  escalated Stage.

### Neutral / trade-offs accepted
- The regex trap stays armed. It is disarmed by the same commit that arms it —
  which is the only ordering in which the antidote can be verified rather than
  assumed.

## Implementation notes

- Do **not** add `limit`/`offset` query parameters "for later". An accepted-and-
  ignored parameter is worse than an absent one: clients would send it and get
  full collections back.
- `include_inactive` stays on the employee listing; it is not pagination, it is the
  opt-in the query DTO already declares.

## References
- `docs/roadmap.md` — block Stage 3.4 (`contratos_introduzidos`, DoD,
  `complexidade_estimada`) and the dated note of Stage 3.3
- ADR 3.3.0003 (total ordering with C collation as port law)
- `docs/stages/3.3-staff-persistence/technical.md` §7 — `[finding]` of 2026-08-12
  on the `ORDER BY` regex
- `docs/stages/3.4-staff-http/concept.md` §5.11, §7 D6, CA32, CA35
- `src/restaurant_hub/features/staff/application/dtos/queries.py`

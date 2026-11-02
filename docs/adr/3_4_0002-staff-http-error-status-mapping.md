---
title: ADR 3.4.0002 — A single StaffError handler resolves HTTP status from a total map, with UnavailabilityNotFoundError deliberately 422 and the 409 band reserved for stored-state conflicts
description: Architecture Decision Record
when-use: Reference when adding an error to the staff hierarchy, when a staff error surfaces with the wrong HTTP status, or before deciding whether a new conflict is 409 or 422
keywords: [adr, http, error-handling, status-code, fastapi, mro, totality, staff]
status: accepted
created_at: 2026-08-12
updated_at: 2026-11-02
adr_id: 3.4.0002
decision: Register one FastAPI exception handler on StaffError that resolves status by walking the exception MRO against an explicit total map, guarded by a test enumerating every concrete subclass; UnavailabilityNotFoundError stays 422 because it names a value inside the aggregate, and the 409 band is reserved for conflicts with already-stored identity or references
context_stage: 3.4-staff-access-scope
bounded_context: staff
---

# ADR 3.4.0002 — Staff HTTP error status mapping

> ⚠️ **Errata (2026-09-14):** §Decision 5 — "`EmployeeInUseError` has no producer in v1 (Step 4 introduces it via the 3.3 foreign key)" is superseded in its mechanism: there is no foreign key between bounded contexts; Step 4 produces the error through a **reverse query port** declared in staff and implemented outside staff over a scheduling query (the 409 mapping itself is unchanged) — ver [ADR 4.1.0006](./4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md)

## Status

`accepted`

> **Decidido na Stage 3.4, executado na Stage 3.6.** A Stage `3.4-staff-http`
> foi cortada em duas (CONVENTIONS §6 — 14 Tasks): `3.4-staff-access-scope`
> entrega a fundação de acesso e escopo, e `3.6-staff-http` entrega a borda HTTP.
> Esta decisão é de **borda**, logo governa a 3.6. O `context_stage` continua
> apontando para a 3.4 porque o campo registra a Stage em que a decisão foi
> **tomada** (CONVENTIONS §2), e ADR `accepted` não migra.

## Context

Stage 3.2 built the staff error hierarchy so that HTTP refinement would be
possible **without touching the application layer**. Its `errors.py` docstring
says so literally: every staff application error inherits from `StaffError` (and
therefore `DomainError`), never from `ApplicationError`, because the latter has no
handler and would become a 500 — *"o pior caso não-ajustado é 422; a Stage 3.4
refina para 404/409 registrando handlers, sem tocar nesta camada"*.

More than that, the **inheritance order was engineered for this Stage**. The two
"not found" errors inherit `(StaffError, NotFoundError)` in that order, so the MRO
is `… → StaffError → NotFoundError → DomainError`. Starlette resolves a handler by
walking `type(exc).__mro__` and taking the first registered class, so a handler on
`StaffError` wins over the generic `NotFoundError`/`DomainError` handlers that
`shared/infrastructure/http/error_handlers.py` already registers. And
`UnavailabilityNotFoundError` inherits **only** from `StaffError`, deliberately, so
that no 404 handler ever sees it.

The BC exposes **18** concrete error classes — **9** in
`domain/exceptions/errors.py` (plus the root `StaffError` itself, which the handler
is registered *on* and which is **not** an entry in the map) and **9** in
`application/errors.py`; `InvalidDayPeriodError` was added by **Stage 3.4**
(Task 02, ADR 3.4.0003 §3). They must land on three bands: 404, 409 and
422. The 401/403 bands belong to identity's handler, because every error in them is
raised by the guard.

Forces:

- A silently unmapped error is the dangerous failure mode. A new 409-worthy error
  added in Stage 4.x would answer 422, invisible in review and invisible in logs.
- `shared` cannot reference feature classes (LAYOUT §7), so the map cannot live
  there.
- Stage 2.4 already solved this exact problem for identity (ADR 2.4.0001). A
  second, different solution in the same repo would be the worse outcome
  regardless of which is better in isolation.

## Decision

1. The map lives in the feature, at
   `features/staff/adapters/in/http/error_handlers.py`.
2. A **single** handler is registered on `StaffError`, resolving the status by
   walking the MRO against an explicit `dict[type[StaffError], int]`, falling back
   to 422 only if nothing matches.
3. The map's **totality is a test**: the suite enumerates every concrete subclass
   of `StaffError` recursively — **excluding the root itself** — and asserts each
   has an **explicit own entry**. Inheriting a parent's entry is not enough.
3b. **The map is also verified pair by pair.** A totality test plus a
   "every band is reachable" test still lets two entries swap **within already
   exercised bands** — moving `OverlappingUnavailabilityError` to 409 and
   `JobFunctionInUseError` to 422 keeps both bands covered and passes. So a
   parameterised test asserts the concrete `class → status` pair for all 18
   entries, not just the bands.
4. **The bands, and the four classifications that had a plausible alternative:**

   - **404** — `JobFunctionNotFoundError`, `EmployeeNotFoundError`. An addressable
     resource that does not exist *in the actor's tenant*; a record belonging to
     another tenant lands here too, by the §5.4 rule of Stage 3.2, so 404 never
     confirms someone else's record.
   - **409** — `JobFunctionNameAlreadyExistsError`, `JobFunctionAlreadyExistsError`,
     `EmployeeAlreadyExistsError`, `JobFunctionInUseError`, `EmployeeInUseError`.
     The band is **conflict with already-stored state**: either a key is taken, or
     an existing reference forbids the removal. The payload is fine; something
     else in the database is in the way.
   - **422** — everything else, including the four below.

   **`UnavailabilityNotFoundError` is 422, not 404.** It names a **value inside the
   aggregate**, not an addressable resource: the employee exists and was found;
   what does not exist is the period the client re-presented for removal by value.
   The class inherits only from `StaffError` so the MRO cannot drift it into 404.

   **`OverlappingUnavailabilityError` is 422, not 409.** It is an aggregate
   invariant violated by the period **the client sent**. Filing it under 409 would
   widen that band to "any disagreement with stored data", which would make 409 and
   422 indistinguishable in practice and destroy the signal the band carries.

   **`SameUnitCopyError` is 422, not 409.** Nothing is in conflict: the client named
   the source unit as the destination. That is invalid content.

   **`EmployeeRelocationError` is 422 and unreachable over HTTP in this Stage**, as
   no route lets a client send `unit_id` on an employee update. It gets an entry by
   totality, and the unreachability is recorded so nobody writes an e2e expecting it.

5. `EmployeeInUseError` has **no producer in v1** (Step 4 introduces it via the
   3.3 foreign key) and still gets its own entry. Totality is about the hierarchy,
   not about what is reachable today.
6. Staff registers **no 401/403 entry**. Those errors are `IdentityError`
   subclasses raised by the guard, and identity's handler — which applies the
   constant-body rule — catches them first by MRO. Staff inheriting that behaviour
   is the point: a 403 from a staff route must be indistinguishable from a 403
   from an identity route.

The generic `shared` handlers stay as the safety net.

## Alternatives considered

### Alternative A — `try/except` per route
- **Description:** each of the 16 routes catches and maps its own errors.
- **Pros:** the mapping is visible where the call happens.
- **Cons:** 16 places to forget; the same exception would drift to different
  statuses per route; and it puts protocol decisions inside handlers that are
  supposed to be four lines long.
- **Why rejected:** identity already rejected it for the same reasons
  (ADR 2.4.0001), and a second, divergent convention is worse than either.

### Alternative B — one handler per error class
- **Description:** 18 registrations, one per concrete class.
- **Pros:** no MRO reasoning needed.
- **Cons:** totality becomes "did someone remember to register it", which is
  unverifiable without the same enumeration test — so it costs more and proves
  less.
- **Why rejected:** strictly dominated by the map plus test.

### Alternative C — extend the generic `shared` handler with a status table
- **Description:** teach `shared` about staff's classes.
- **Pros:** one place for the whole app.
- **Cons:** violates LAYOUT §7 — `shared` must not import features — and would
  couple every future BC's error taxonomy to a shared file.
- **Why rejected:** structurally forbidden.

### Alternative D — do nothing (let everything fall to the generic handlers)
`NotFoundError → 404` and `DomainError → 422` would give the right answer for the
two not-found errors and the wrong answer for all five conflicts, which would
answer 422 where the client needs 409 to distinguish "your payload is wrong" from
"someone else's data is in the way". And `UnavailabilityNotFoundError` would be
correct only by accident. Not acceptable.

## Consequences

### Positive
- A new staff error cannot ship unclassified; the suite fails.
- The 401/403 uniformity of identity is inherited rather than reimplemented, so
  there is exactly one place where those bodies are decided.
- The application layer is untouched, exactly as Stage 3.2 planned.

### Negative
- Two handlers now compete on MRO (`IdentityError` and `StaffError`), and the
  reasoning about which wins is non-local. It is stated in both modules'
  docstrings, and it only works because no exception inherits from both roots —
  which is itself worth a test if a shared error root ever appears.
- The 409/422 line is a judgement call at the margin. This ADR pins the four
  contested cases so the line is documented rather than re-litigated per PR.

### Neutral / trade-offs accepted
- 404, 409 and 422 keep `str(exc)` in the body. Safe here because every staff
  error message speaks only about records inside the actor's own tenant — the
  scope checks run in the guard, before the use case.

## Implementation notes

- Mirror `resolve_status` / `build_error_response` from identity's module,
  including the MRO walk with a 422 default. The default exists so an unclassified
  error degrades sensibly in production; the totality test is what keeps it from
  becoming the silent path.
- The totality test must enumerate `__subclasses__` **recursively**, and must
  assert an entry keyed by the class itself, not by any ancestor.

## References
- `docs/stages/3.4-staff-access-scope/concept.md` §13 (fronteira com a 3.6) — esta
  decisão é executada na **3.6**; o desenho completo do mapa está no commit
  `d878060`, em `docs/stages/3.4-staff-http/concept.md` §6
- `docs/roadmap.md` — bloco Stage 3.6
- `src/restaurant_hub/features/staff/application/errors.py` (module docstring)
- `src/restaurant_hub/features/staff/domain/exceptions/errors.py`
- `src/restaurant_hub/features/identity/adapters/in/http/error_handlers.py`
- ADR 2.4.0001, ADR 2.3.0003, ADR 3.2.0006
- `docs/stages/3.2-staff-application/concept.md` §4 (the note on
  `UnavailabilityNotFoundError`), §6

## Supersessão parcial

**2026-11-02 — a decisão 2 (*"A **single** handler is registered on `StaffError`"*), a decisão 3
(totalidade sobre *"every concrete subclass of `StaffError`"*) e a regra do Context de que todo
erro de aplicação de staff herda de `StaffError`, *"never from `ApplicationError`"*, com os dois
"não encontrado" herdando `(StaffError, NotFoundError)` nesta ordem, foram superadas por [ADR 3.9.0001](./3_9_0001-error-roots-by-meaning-status-by-map.md)**
(Stage 3.9, issue #48). `JobFunctionNotFoundError`, `EmployeeNotFoundError`,
`JobFunctionAlreadyExistsError` e `EmployeeAlreadyExistsError` descendem agora só de
`StaffApplicationError`; o handler único é registrado sobre as duas raízes, e a totalidade é
cobrada sobre as subclasses das duas. As faixas, as classificações de §4, o discriminador
`"type": "staff_error"` e a contagem de 23 entradas continuam valendo, byte a byte. Nota
*append-only*; o corpo acima não foi editado.

## Errata

**2026-08-18 — contagem e atribuição corrigidas; decisão inalterada.** Achado na
Fase 3A da Stage 3.6, ao varrer os ADRs pré-corte atrás de ponteiros defasados
(o mesmo defeito que gerou a `## Errata` do ADR 3.4.0001). O que muda é uma
contagem factual e a Stage a que ela atribui um acréscimo; **nenhuma frase de
`Decision`, `Alternatives considered` ou `Consequences` teve o seu conteúdo
alterado**, e o total de **18** entradas — que é o número que a decisão usa — é
o mesmo antes e depois.

| Onde | Dizia | Diz | Medição |
|---|---|---|---|
| `## Context` | *"The BC currently exposes **17** concrete error classes — **8** in `domain/exceptions/errors.py` … and **9** in `application/errors.py` — and **this Stage adds** `InvalidDayPeriodError`, for **18**"* | *"The BC exposes **18** concrete error classes — **9** in `domain/exceptions/errors.py` … and **9** in `application/errors.py`"* | `InvalidDayPeriodError` foi acrescentado pela **Stage 3.4** (Task 02, ADR 3.4.0003 §3), não pela Stage que executa este ADR. Contagem conferida no código: `domain/exceptions/errors.py` tem `InvalidIdentifierError`, `InvalidNameError`, `InvalidDayPeriodError`, `InvalidWeeklyHoursError`, `EmptyShiftPreferenceError`, `EmptyJobFunctionsError`, `InvalidUnavailabilityPeriodError`, `OverlappingUnavailabilityError`, `UnavailabilityNotFoundError` = **9** (mais a raiz `StaffError`, que não é entrada); `application/errors.py` tem **9** |

**O que NÃO mudou, e por quê.** O texto redigido quando este ADR nasceu dizia
"this Stage" para a Stage `3.4-staff-http` **antes do corte**, quando fundação e
borda eram a mesma Stage. Depois do corte, o acréscimo do erro ficou na 3.4 e o
mapa ficou na 3.6 — as duas metades da mesma frase foram para lados diferentes.
A errata desfaz a ambiguidade nomeando a Stage, em vez de deixar "this Stage"
significar coisas diferentes em parágrafos vizinhos do mesmo documento.

**2026-08-29 — a correção acima aplicada ao corpo; nada de novo foi decidido.**
Achado no Checkpoint C da Fase 4 da Stage 3.6, que **executa** este ADR. A
entrada de 2026-08-18 declarava o texto novo na coluna "Diz", mas o `## Context`
nunca foi editado: o documento seguia dizendo *"**17** concrete error classes —
**8** … and **9** … and this Stage adds `InvalidDayPeriodError`, for **18**"*
enquanto o seu próprio `## Decision` §3b falava em *"all **18** entries"* —
**dois números incompatíveis no mesmo documento**, que é exatamente a ambiguidade
que a errata de 2026-08-18 existia para fechar.

O corpo passa agora a dizer o que aquela linha já ratificou. A medição é a mesma
e continua conferida no código: `domain/exceptions/errors.py` tem **9** concretas
e `application/errors.py` tem **9**, total **18** — o número que
`STAFF_ERROR_STATUS` implementa e que CA17/CA18 travam por enumeração recursiva.

A lição, e é por isso que fica escrito: **errata que descreve a correção não é
correção**. Uma tabela "Dizia → Diz" cujo "Diz" nunca chegou ao corpo deixa o
documento com as duas versões vivas, e a errata passa a parecer conformidade que
o arquivo não tem.

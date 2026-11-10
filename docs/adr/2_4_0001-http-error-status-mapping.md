---
title: ADR 2.4.0001 — A single IdentityError handler resolves HTTP status from a total map, instead of per-route try/except or one handler per class
description: Architecture Decision Record
when-use: Reference when adding an error to the identity hierarchy, when a domain error surfaces with the wrong HTTP status, or before adding a try/except to a route handler
keywords: [adr, http, error-handling, status-code, fastapi, starlette, exception-handler, totality, identity]
status: accepted
created_at: 2026-07-19
updated_at: 2026-11-09
adr_id: 2.4.0001
decision: Register one FastAPI exception handler on IdentityError that resolves the HTTP status by walking the exception's MRO against an explicit type-to-status map, and guard the map's totality with a test that enumerates every concrete IdentityError subclass, so an unmapped error fails the suite instead of silently degrading to 422
context_stage: 2.4-identity-http
bounded_context: identity
---

# ADR 2.4.0001 — HTTP error status mapping

## Status

`accepted`

## Context

Stage 2.2 built the identity error hierarchy deliberately so that HTTP status
refinement would be possible **without touching the application layer**. Its
`errors.py` module docstring says so explicitly: every application error inherits
from `IdentityError` (and therefore `DomainError`), never from `ApplicationError`,
because the latter has no handler and would become a 500. The worst unrefined case
is 422, and "a Stage 2.4 refina para 401/403/404 registrando handlers".

That refinement is now due. The BC currently exposes **24 concrete error classes** —
8 in `domain/exceptions/errors.py` (`InvalidEmailError`, `CrossTenantError`, …) and
16 in `application/errors.py` (`InvalidCredentialsError`, `PermissionDeniedError`,
`EmailAlreadyRegisteredError`, …) — and this Stage adds three more
(`InvalidAccessTokenError`, `InvalidRefreshTokenError`, `RefreshTokenReuseError`),
for **27**. They must land on five distinct status bands — 401, 403, 404, 409,
422 — and the issue #24 DoD requires that the mapping be **tested, not presumed**.

Two properties of the runtime shape the choice:

- Starlette resolves an exception handler by walking `type(exc).__mro__` and taking
  the first registered class. Stage 2.2 already relied on this: the three
  `*NotFoundError` classes inherit `(IdentityError, NotFoundError)` in that order
  precisely so the 404 handler is reached before the 422 one.
- `shared/infrastructure/http/error_handlers.py` already registers generic
  `NotFoundError → 404` and `DomainError → 422` handlers. Those are in `shared`,
  which **must not import from features** (LAYOUT §7). So the identity-specific
  mapping cannot live there.

Forces:

- A silently unmapped error is the dangerous failure: a new `403`-worthy error added
  in Stage 3.x would answer `422`, and nothing would notice. The failure mode is
  invisible in review and invisible in production logs.
- The mapping is a boundary concern; it must not leak back into the use cases.

## Decision

1. The mapping lives in the feature, at
   `features/identity/adapters/in/http/error_handlers.py` — not in `shared`.
2. A **single** handler is registered on `IdentityError`. It resolves the status by
   walking `type(exc).__mro__` against an explicit `dict[type[IdentityError], int]`,
   falling back to 422 only if nothing matches.
3. The map's **totality is a test**: the suite enumerates every concrete subclass of
   `IdentityError` (recursively, via `__subclasses__`) and asserts each has an
   **explicit own entry**. Inheriting a parent's entry is not enough — a new error
   must be classified deliberately.
4. **`401` and `403` bodies are constant per band; the exception message never
   reaches the client.** Equalising the status is not enough — the default body
   shape is `{"detail": str(exc)}`, and these messages carry ids and tenants
   (`TenantNotVisibleError` renders *"ator do tenant 'A' e alvo no tenant 'B'"*).
   Leaking it would re-open through the body the very enumeration oracle that
   decision 5 below closes through the status, and would additionally disclose
   which tenant owns a resource. `401` also carries `WWW-Authenticate: Bearer`
   (RFC 6750 §3). The specific message still goes to the server log, where it is
   diagnostic rather than oracle.

   `404`, `409` and `422` keep `str(exc)`: those messages describe a resource the
   client itself named or an invariant its own payload violated. For the
   *resource-scoped* errors this is safe because `AuthorizeActionUseCase` runs its
   scope checks first — and, for `POST /users`, because the adapter authorizes
   once **per requested unit** (ADR 2.4.0003 §3) — so a 404 or 422 only ever
   speaks about the actor's own tenant.

   **One documented exception, stated rather than glossed over:**
   `EmailAlreadyRegisteredError` (409) *is* reachable across tenants —
   `CreateUserUseCase` checks e-mail uniqueness globally and **first**, before any
   scope logic, because uniqueness is global by kickoff decision #2. So a tenant
   actor can learn that an address is already registered somewhere. Suppressing
   the message would buy nothing: the signal is the **status**, not the body, and
   the body only echoes the address the client itself submitted — no tenant, id or
   role of the owner. Closing it would mean revisiting global e-mail uniqueness,
   which is out of scope here.
5. **Two errors do not reach this handler at all**, because the guard converts
   them first, and both conversions close an information leak:
   - `UserNotFoundError` raised while resolving the **actor** becomes
     `InvalidAccessTokenError` → 401. A token whose subject no longer exists is an
     invalid credential, not a missing resource.
   - `UnitNotFoundError` raised by `AuthorizeActionUseCase` becomes
     `UnitNotVisibleError` → 403. Left as 404 it would form a **cross-tenant
     existence oracle**: `UnitRepository.find_by_id` does not filter by tenant, so
     a caller iterating unit ids reads 404 as "does not exist anywhere" and 403 as
     "exists in some tenant". For an actor who cannot see the unit, "absent" and
     "not yours" must be the same answer — the same reasoning `create_user.py`
     already applies when ordering its checks.

   Both conversions are narrow and unambiguous: in `AuthorizeActionCommand` the
   only user is the actor, and the only unit is the authorization target.
6. `SessionFingerprintAlreadyExistsError` maps to **401**, not 409, despite being
   an "already exists" error. Its own docstring says a repeated fingerprint *is*
   the refresh-token-reuse signal; filing it under write conflicts would both
   record the opposite of its meaning and emit a **distinguishable** status on an
   auth endpoint, breaking the uniform-failure rule.

The generic `shared` handlers stay as the safety net for non-identity `DomainError`s
and for future bounded contexts.

## Alternatives considered

### Alternative A — `try/except` in each route handler
- **Description:** each endpoint catches the errors it can raise and maps them.
- **Pros:** locally explicit; the mapping is visible next to the call.
- **Cons:** the policy is duplicated across 7 endpoints and grows with every route;
  a new error is mapped in the routes the author remembered and forgotten in the
  rest; it fattens the adapter, which the `fastapi-thin-adapter` skill wants thin.
- **Why rejected:** it converts one omission into N omissions and has no totality
  check to catch any of them.

### Alternative B — one `@app.exception_handler` per error class
- **Description:** 27 explicit registrations, one per concrete error.
- **Pros:** maximally explicit; no MRO walking.
- **Cons:** identical omission risk (forgetting a registration is silent, and the
  error falls through to the generic `DomainError → 422`), plus ~22 near-identical
  function bodies.
- **Why rejected:** same failure mode as the chosen option would have **without**
  the totality test — and the totality test is the actual protection, not the
  registration style. Given the test, the compact form wins.

### Alternative C — status carried on the exception class (e.g. `http_status` attribute)
- **Description:** each error declares its own status.
- **Pros:** no map to keep in sync; totality is structural.
- **Cons:** puts an HTTP concern inside `domain/` and `application/` — the exact
  coupling that ADR 2.2.0003 and LAYOUT §3 forbid. A domain exception would know
  about a transport protocol.
- **Why rejected:** violates the layering the whole BC was built to preserve.

## Consequences

### Positive
- Adding an error to the hierarchy without classifying it **breaks the suite**,
  which is the only mechanism that survives an author who is not thinking about HTTP.
- The full policy is readable in one table, in one file, next to the ADR that
  explains it.
- The application layer stays untouched, as Stage 2.2 planned.

### Negative
- The MRO walk is one indirection between "exception raised" and "status returned";
  a reader must know Starlette resolves handlers by MRO. Mitigated by the module
  docstring.
- The totality test uses `__subclasses__`, which only sees **imported** classes. The
  test therefore imports both error modules explicitly; if a third error module is
  added and not imported there, the guard silently shrinks. The test asserts a
  minimum known count as a tripwire against exactly that.

### Neutral / trade-offs accepted
- Generic 401 bodies make client-side debugging harder. That is the deliberate
  anti-enumeration posture inherited from Stage 2.2 (`dummy_hash`, single
  `InvalidCredentialsError` message), not an oversight.

## References
- `docs/stages/2.4-identity-http/concept.md` §6, §5 regra 11
- ADR 2.2.0003 (application errors in the identity hierarchy)
- `src/restaurant_hub/shared/infrastructure/http/error_handlers.py`
- RFC 6750 §3 (`WWW-Authenticate`); RFC 9110 §15.5 (4xx semantics)

## Supersessão parcial

**2026-11-02 — as decisões 2 e 3 (*"A **single** handler is registered on `IdentityError`"*;
a totalidade sobre *"every concrete subclass of `IdentityError`"*) e, na frase final *"The
generic `shared` handlers stay as the safety net for non-identity `DomainError`s and for future
bounded contexts"*, o plural, foram superados por [ADR 3.9.0001](./3_9_0001-error-roots-by-meaning-status-by-map.md)** (Stage 3.9, issue #48). O handler
único passa a ser registrado sobre as **duas** raízes de identity — `IdentityError` e
`IdentityApplicationError` —, e a totalidade é cobrada sobre as subclasses das duas
(`tests/unit/test_status_map.py`). Da rede genérica de `shared` para a hierarquia de erros fica
só `DomainError → 422` (a de `RequestValidationError` não muda):
`NotFoundError → 404` saiu com a classe, e não há rede para `ApplicationError`. O Context deste
ADR descreve a regra "never from `ApplicationError`" do ADR 2.2.0003, também superada. Mapa,
faixas, corpos constantes 401/403, `WWW-Authenticate` e as conversões do guard (decisão 5)
continuam valendo, byte a byte. Nota *append-only*; o corpo acima não foi editado.

## Nota — a faixa 500 (issue #170)

**2026-11-09 — o mapa de identity ganhou uma sexta faixa, 500, com corpo constante; nada acima
foi revogado.** O `## Context` fala em *"five distinct status bands — 401, 403, 404, 409, 422"*,
e a decisão 4 trata só dessas cinco. Desde a issue #170 (PR #173) o mapa tem uma entrada fora da
família 4xx: `InvitationNotSentError → 500`, a falha de entrega do convite **depois** de a conta
ser comitada (regra 13 da Stage 2.5; ADR 0.0.0018 §4 já dizia 500). O que vale para ela:

- **Corpo constante**, como 401/403: `{"detail": "erro interno", "type": "internal_error"}`,
  escolhido pelo status (`status >= 500` em `build_error_response`), nunca `str(exc)`. A causa
  vai ao log por quem a levanta (`_invitation.deliver_invitation`: só o tipo da falha e o
  `user_id`, sem traceback), e não pelo handler — a faixa não entra no log de causa suprimida.
- **A decisão 4 continua literal para 401/403 e para 404/409/422.** A faixa nova não muda o
  corpo de nenhuma outra resposta.
- **A família 4xx deixa de ser absoluta, por allowlist contável.** O gate
  `test_o_mapa_do_bc_so_declara_status_da_familia_4xx` (`tests/unit/test_status_map.py`, issue
  #45) aceita só as entradas de `_FORA_DA_FAMILIA_4XX`, por classe e status exato, e reprova
  entrada morta nela. O oráculo `tests/e2e/features/identity/test_status_bands.py` passa a
  conferir a lista de faixas contra os valores do mapa.

Nota *append-only*; o corpo acima não foi editado.

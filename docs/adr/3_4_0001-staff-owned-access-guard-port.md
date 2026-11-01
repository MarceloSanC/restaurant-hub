---
title: ADR 3.4.0001 — Staff declares its own AccessGuard port and the translator to identity is assembled in the composition root, keeping bc-independence absolute
description: Architecture Decision Record
when-use: Reference before letting any staff module import from features.identity, before adding an ignore_imports to bc-independence, or when wiring a second bounded context that needs authorization
keywords: [adr, bounded-context, independence, port, adapter, authorization, import-linter, composition-root, staff, identity]
status: accepted
created_at: 2026-08-12
updated_at: 2026-10-19
adr_id: 3.4.0001
decision: The staff HTTP adapter depends on an AccessGuard Protocol owned by staff (opaque string identifiers, permission named as str, four published laws), whose implementation is assembled in composition_root.py — the module that already imports both bounded contexts — so bc-independence stays absolute with zero ignore_imports
context_stage: 3.4-staff-access-scope
bounded_context: staff
---

# ADR 3.4.0001 — Staff-owned `AccessGuard` port, translator in the composition root

## Status

`accepted`

## Context

Every one of the sixteen staff use cases takes a `tenant_id`, and the twelve
employee routes address a unit. None of that scope is recoverable inside the staff
bounded context: `tenant_id` comes from the authenticated actor, and the coherence
between a unit and its tenant is stated by `Employee`'s own docstring as *"premissa
da borda"* — a premise the boundary owes, not an invariant the entity can check.

The authority that answers both questions is `AuthorizeActionUseCase` (Stage 2.2),
reached through `IdentityGuard` (Stage 2.4). The roadmap's 3.4 block lists it as a
consumed contract: *"authorize de identity (via dependency)"*.

Four forces collide:

- **`bc-independence`** in `.importlinter` is an `independence` contract between
  `restaurant_hub.features.identity` and `restaurant_hub.features.staff`. It
  forbids **any** import in **either** direction, including
  `staff.adapters → identity.application`.
- **LAYOUT §1** states bounded contexts communicate through ports, with identifiers
  crossing as opaque strings — which `staff/domain/value_objects/identifiers.py`
  repeats in its own docstring.
- The **roadmap's 3.5 block** fixes the shape of the next crossing:
  `features/staff/application/ports/out/identity_gateway.py` plus
  `features/staff/adapters/out/identity/local_identity_gateway.py`.
- **`IdentityGuard` cannot be imported statically at all.** It lives in
  `features/identity/adapters/in/http/dependencies.py`, and `in` is a Python
  keyword: `from ...adapters.in.http.dependencies import IdentityGuard` is a
  **SyntaxError**, not an ImportError. `composition_root.py` already documents this
  and types the object as `Any` (`identity_guard: Any`, lines 185-188).

A fifth force matters for security: `IdentityGuard.authorize` converts
`UnitNotFoundError` into `UnitNotVisibleError`, which is what stops a caller from
using 404-vs-403 as a cross-tenant existence oracle, and the identity error handler
gives the 401/403 bands constant bodies. Any shape that reimplements or *translates*
authorization loses those properties silently.

## Decision

**1. Staff declares its own port.**
`features/staff/application/ports/out/access_guard.py` holds an `AccessGuard`
Protocol with `authenticate` and `authorize`, plus the frozen DTO
`AuthorizedScope`. Its vocabulary is staff's: identifiers are `str`, the required
permission is named as `str`. The port names *what staff needs*, never *how
identity decides*.

**2. The port publishes four laws**, because a Protocol alone does not carry the
security properties this design depends on. A second implementation satisfying only
the types would destroy them without failing any type check:

- **L-AG1** — `authenticate` raises when the credential is absent or invalid, and
  the exception **propagates raw**: the implementation does not translate it. This
  is what makes staff's 401 band byte-identical to identity's.
- **L-AG2** — `authorize` raises when the actor may not act on the target, and the
  exception **propagates raw**, for the same reason (constant-body 403).
- **L-AG3** — `authorize` never returns an `AuthorizedScope` whose `tenant_id` is
  empty or absent. An actor without a tenant (today only `platform_admin`) is
  **denied**, never coerced to `""`. `TenantId` is a `NewType` with no runtime
  validation, so `TenantId(actor_tenant_id or "")` would compile, pass mypy strict,
  and produce tenant-empty queries — the false-isolation bucket that
  `InvalidIdentifierError` is named after.
- **L-AG4** — `authorize` is called once per target; authorizing one target does
  not authorize another.

**3. The implementation is assembled in `composition_root.py`**, the module that
already imports both bounded contexts by design and already holds the guard as
`Any`. The router receives the port through `dependency_overrides`.
**No module under `features/staff/` imports `features/identity/`**, and
`bc-independence` keeps **zero** `ignore_imports` — a property pinned by a test
that reads `.importlinter` and fails if the list ever appears (concept CA13).

**4. The port lives in `application/ports/out/`, not inside the HTTP adapter.**
This Stage's only consumer is the router, which would argue for
`adapters/in/http/`. The placement anticipates Stage 3.5, whose `IdentityGateway`
is consumed by a **use case** and whose folder the roadmap already names. The
justification is the project's progressive-scalability criterion, **not** LAYOUT §5
— which describes driven ports as consumed by use cases, and is therefore not yet
literally true here.

## Alternatives considered

### Alternative A — adapter in `features/staff/adapters/out/identity/` with a narrow `ignore_imports`
- **Description:** the translator lives in staff, mirroring the shape the roadmap
  fixes for Stage 3.5, with a suppression on `bc-independence`.
- **Pros:** matches 3.5's planned layout exactly; keeps the composition root purely
  declarative; the suppression sits on a small, rarely-edited module.
- **Cons — measured, and decisive:** the promise that justified it, *"one pair, one
  direction"*, is **false**. The object being wrapped is unimportable
  (`in` is a keyword), so the module could not even annotate it — it would hold the
  same `Any` the composition root holds, and that edge would be **invisible to
  import-linter anyway**. What the module *would* import is `Permission`,
  `RestaurantId` and `UnitId` from `identity.domain` — **three** pairs, not one. So
  the alternative buys the 3.5-shaped layout at the cost of three suppressions on
  the project's strongest structural contract, while not even typing the object it
  exists to wrap.
- **Why rejected:** the cost was mispriced. Once counted, it buys layout symmetry
  with an architectural guarantee. **This was the first choice of this ADR and was
  reversed at Checkpoint A**, when the keyword-`in` constraint was measured against
  it.

### Alternative B — the staff router imports `IdentityGuard` directly
- **Description:** no port at all.
- **Pros:** fewest files.
- **Cons:** impossible as written (`in` keyword), and if worked around with
  `importlib` it would put an untyped cross-BC reach into the package most likely to
  grow, with every future route author inheriting the precedent.
- **Why rejected:** the boundary would exist in the document and not in the graph.

### Alternative C — promote an authorization port to `shared/`
- **Description:** `shared/application/ports/out/access_guard.py` for every BC.
- **Pros:** one port for all future bounded contexts.
- **Cons:** LAYOUT §4 says move to `shared` only when a **second** feature needs the
  same code; scheduling does not exist and its access needs are unknown. And it does
  not remove the need for a translator — it only moves the Protocol.
- **Why rejected:** premature abstraction over an unstable vocabulary, with no cost
  removed.

### Alternative D — staff reimplements the access decision
- **Description:** staff reads memberships itself and decides.
- **Pros:** no crossing at all.
- **Cons:** two sources of truth for access, which ADR 2.2.0002 centralised on
  purpose; and it would lose the `UnitNotFoundError → UnitNotVisibleError`
  conversion, reopening the cross-tenant enumeration oracle that ADR 2.4.0001 §5
  closed.
- **Why rejected:** it is the failure mode the whole authorization design exists to
  prevent.

### Alternative E — do nothing (no authorization crossing in 3.4)
The staff routes would have to take `tenant_id` from the request body — a
cross-tenant escalation vector (ADR 2.4.0003 §4) — and the copy's `target_unit_id`
would stay unvalidated, which is the finding this Stage inherited. Not acceptable.

## Consequences

### Positive
- **`bc-independence` stays absolute.** No suppression, no precedent, and the
  absence is testable (CA13) rather than a matter of review vigilance.
- The security properties of `IdentityGuard` are inherited **by law, not by
  coincidence**: L-AG1/L-AG2 make "the exception propagates raw" a contract that a
  fake must satisfy, so the constant-body bands cannot be lost by swapping the
  implementation.
- L-AG3 closes a `None → ""` coercion that would otherwise be invisible to mypy
  strict and would silently break tenant isolation.

### Negative
- **The composition root gains roughly thirty lines with behaviour** — vocabulary
  translation — which is not wiring. Its charter (LAYOUT §6) is to instantiate and
  inject, and this stretches it. Accepted as the smaller cost, and recorded as a
  finding to revisit in Stage 3.5.
- The `AccessGuard` Protocol has one consumer that is not a use case, so the
  `ports/out/` placement is justified by anticipation rather than by the letter of
  LAYOUT §5. Stated openly rather than glossed.

### Neutral / trade-offs accepted
- The permission name crosses as `str`, so a typo is not caught by the type checker.
  It is caught by the per-role, per-route tests of concept CA10–CA12.
- `AuthorizedScope` duplicates two fields of identity's `AuthorizedActor`. That is
  the price of not sharing DTOs across bounded contexts, and it is intentional.
- Moving the translator into `features/staff/adapters/out/identity/` later is a
  file move plus whatever suppression is decided **then**, with Stage 3.5's real
  consumer in hand. Nothing here forecloses it.

## Implementation notes

- The translator is built over the **same** `IdentityGuard` instance already
  constructed for identity's routes — not a second graph, not a second `Engine`.
- L-AG3 must be enforced in the translator, not left to the RBAC map: relying on
  "`platform_admin` is denied first" makes tenant isolation hostage to the role
  matrix, which is still an open fork.
- The laws need a fake implementation in the test suite; a port law that only the
  production implementation satisfies is not a law, it is a description.

## References
- `docs/stages/3.4-staff-access-scope/concept.md` §4 (o port e as leis), §5.8 (a
  decisão de acesso não acontece em staff), §5.9 (`bc-independence` absoluto),
  §7 D1, CA12–CA15
- `docs/roadmap.md` — blocks Stage 3.4 and Stage 3.5
- `.importlinter` — contract `bc-independence`
- `docs/LAYOUT.md` §1, §4, §5, §6, §8
- `src/restaurant_hub/composition_root.py:24-27` (the `in` keyword) and `:300-305`
  (`identity_guard: Any`)
- ADR 2.2.0002, ADR 2.4.0001 §5, ADR 2.4.0003
- `src/restaurant_hub/features/staff/domain/value_objects/identifiers.py`

## Errata

**2026-08-18 — referência cruzada corrigida; decisão inalterada.** Achado no
Checkpoint C da Fase 4 e corrigido aqui como **errata**, não como revisão: o que
muda é para onde o texto aponta, e nenhuma frase de `## Decision`,
`## Alternatives considered` ou `## Consequences` teve o seu conteúdo alterado.

| Onde | Dizia | Diz | Medição |
|---|---|---|---|
| `## Decision` §3 | *"a property pinned by a test that reads `.importlinter` … (concept **CA14**)"* | **CA13** | `concept.md` §11: CA13 é *"o contrato `bc-independence` continua sem nenhum `ignore_imports`; teste lê o `.importlinter`"*; **CA14** é *"as leis L-AG1…L-AG4 são testadas contra uma segunda implementação"* — outra propriedade, outro teste |
| `## Consequences` | *"the absence is testable (**CA14**)"* | **CA13** | idem — "a ausência" é a ausência de `ignore_imports` |
| `## References` | `composition_root.py:185-188` | `:300-305` | o campo `identity_guard: Any` está hoje na linha **305**; o intervalo antigo ficou obsoleto quando a Task 06 desta Stage acrescentou o tradutor **acima** dele |

O erro entrou em `7676a95` (o corte da Stage 3.4 em fundação + borda 3.6), que
**renumerou os critérios do concept** sem reconciliar os ponteiros deste ADR.

**O que NÃO foi corrigido, e por quê.** `## Trade-offs` cita *"the per-role,
per-route tests of concept CA10–CA12"*. Aquele intervalo também é anterior ao
corte, mas o conserto **não** é uma renumeração: os testes por papel e por rota
não existem mais nesta Stage — migraram para a **3.6** junto com a borda HTTP.
Escolher o texto novo seria decidir onde a propriedade passa a ser provada, e
isso é mudança de conteúdo de um ADR `accepted`, não errata. Fica registrado como
`[finding]` na §7 do `technical.md` desta Stage, para a auditoria dispor com a
3.6 em mãos.

---

**2026-08-18 (segunda entrada) — o intervalo `CA10–CA12` do `## Trade-offs` fica
resolvido, agora que a Stage 3.6 existe.** A entrada anterior escalou este item de
propósito: com a 3.4 em mãos não havia para onde apontar, porque os testes por
papel e por rota tinham migrado para uma Stage que ainda não tinha concept. Ela
agora tem, e o ponteiro passa a ter destino — continua sendo **errata de
ponteiro**, não mudança de conteúdo: a frase afirma que um erro de digitação no
nome da permissão é pego por testes por papel e por rota, e essa afirmação segue
idêntica; só o endereço dos testes muda.

| Onde | Dizia | Diz | Medição |
|---|---|---|---|
| `## Trade-offs` | *"It is caught by the per-role, per-route tests of concept **CA10–CA12**"* | *"...of Stage 3.6's concept **CA09–CA12**"* | `docs/stages/3.6-staff-http/concept.md` §11: CA09 (papéis sem permissão recebem 403 nas 16 rotas), CA10 (`manager` alcança as 16), CA11 (`owner` alcança as 16), CA12 (`hr` ≡ `manager` nas 16) — os quatro são parametrizados sobre o produto papel × rota, que é o que "per-role, per-route" nomeia |
| `## References` | `concept.md` §7 D1, `CA12–CA15` | `CA12–CA15` **da 3.4** — correto como está | conferido: no `concept.md` da 3.4, CA12–CA15 são os critérios do port `AccessGuard`; o intervalo é desta Stage e não migrou |

## Supersessão parcial

**2026-09-26 — a cláusula "zero `ignore_imports`" de `## Decision` §3 foi superada por
[ADR 3.5.0001](./3_5_0001-cross-bc-facade-and-gateway-edge.md).** A frase *"`bc-independence`
keeps **zero** `ignore_imports` — a property pinned by a test that reads `.importlinter` and
fails if the list ever appears (concept CA13)"* deixou de valer na Stage 3.5: o contrato passou a
carregar **um** par nomeado (`restaurant_hub.features.staff.adapters.out.identity.* ->
restaurant_hub.features.identity.application.facade`, com `unmatched_ignore_imports_alerting =
error`), e o teste passou a asserir a **lista exata** em vez da ausência. Tudo o mais desta
decisão continua em vigor — o port `AccessGuard` de staff, as quatro leis, a colocação do port em
`application/ports/out/` e a montagem do tradutor de autorização no `composition_root` (que o
ADR 3.5.0001 §5 reafirma). Nota *append-only*; o corpo acima não foi editado (CONVENTIONS §5,
terceira forma).

**2026-10-19 — §4, a ressalva *"LAYOUT §5 … is therefore not yet literally true here"*, superada
por [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md) — só para
`authorize`.** A partir da Stage 3.7 os 17 use cases de staff recebem o `AccessGuard` por
construtor e chamam `authorize` antes de qualquer outra instrução: a operação passa a ter o
consumidor que LAYOUT §5 descreve. `authenticate` **não** muda — continua com um único
consumidor, o adapter de entrada, e recebe a requisição HTTP; para ela a ressalva segue
verdadeira (finding da 3.7). Nota *append-only*; o corpo acima não foi editado (CONVENTIONS §5).

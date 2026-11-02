---
title: ADR 3.5.0001 — In-process integration between bounded contexts is an upstream facade consumed by a downstream gateway adapter through one named import edge; the access-guard translator stays in the composition root
description: Architecture Decision Record
when-use: Reference before any module of one bounded context imports another, before adding or widening an ignore_imports on bc-independence, when a new BC needs to consume identity or staff in-process, or when revisiting issue #47
keywords: [adr, bounded-context, anticorruption-layer, open-host-service, facade, gateway, import-linter, ignore-imports, bc-independence, composition-root, staff, identity]
status: accepted
created_at: 2026-09-12
updated_at: 2026-11-02
adr_id: 3.5.0001
decision: identity exposes an in-process Open Host Service (`features/identity/application/facade.py`, primitive types, no authorization, re-exports the errors a consumer must translate); staff implements its `IdentityGateway` port in `features/staff/adapters/out/identity/` importing only that facade; `bc-independence` receives exactly one `ignore_imports` pair (`staff.adapters.out.identity.* -> identity.application.facade`) whose exact list is pinned by test; `_IdentityAccessGuard` remains in `composition_root.py` because the object it wraps is unimportable, and issue #47 is re-scoped accordingly
context_stage: 3.5-employee-login-link
bounded_context: staff
---

# ADR 3.5.0001 — Cross-BC in-process integration: upstream facade, downstream gateway, one named edge

## Status

`accepted` — decided by the sponsor on 2026-09-12 after a primary-source
research round requested by them (concept §13 Q2).

**Partially supersedes ADR 3.4.0001 §Decision 3** — the clause *"`bc-independence`
keeps zero `ignore_imports` — a property pinned by a test"* no longer holds; the
contract now carries **one** named pair, and the test pins the **exact list**.
Decisions §1, §2 and §4 of ADR 3.4.0001 (staff-owned `AccessGuard` port, the four
laws, port placement) and its §3 placement of the translator remain in force.
CONVENTIONS §5 names exactly two non-destructive ways to keep an `accepted`
ADR honest — a new ADR with `superseded_by`, or an errata banner — and neither
fits a **partial** supersession (the decision as a whole stands; one clause of
one section is replaced). ADR 3.4.0001 therefore stays `accepted` and receives
an **append-only dated note of partial supersession** pointing here — a third
form, declared as a divergence from §5 (it does not rewrite the body, which is
what §5 protects); adding this form to CONVENTIONS §5 is part of this Stage's
documentation close. It is not an errata: ADR 3.4.0001's own `## Errata`
defines errata as pointer correction with no change of decision content, and
this is a change of content.

## Context

Stage 3.5 is the first Stage in which a **use case** of one bounded context
needs another one: `CreateLoginForEmployeeUseCase` (staff) must have identity
create a pending account, send an invitation and — on termination — revoke
sessions. The roadmap fixed the shape: a port
`features/staff/application/ports/out/identity_gateway.py` and an adapter
`features/staff/adapters/out/identity/local_identity_gateway.py` that *"calls
identity use cases in-process"*.

Forces:

- **`bc-independence`** is an `independence` contract between
  `restaurant_hub.features.identity` and `restaurant_hub.features.staff`. It
  forbids imports in **either** direction, **including indirect ones**. Until
  this Stage it held with zero `ignore_imports`, and
  `tests/unit/features/staff/test_bc_independence.py` asserted the list did not
  exist (ADR 3.4.0001 §3, CA13 of Stage 3.4).
- An adapter inside staff that calls identity **must** import something from
  identity. The only question is **what** and **how much**.
- Importing identity's internals (use cases, command/result DTOs, `Email`,
  `Role`, `RestaurantId`, `UnitId`, two error classes) costs roughly **ten**
  pairs and couples staff to identity's internal shape: every new internal
  used is a new pair.
- ADR 3.4.0001 chose to assemble the previous crossing (`_IdentityAccessGuard`)
  in `composition_root.py`, the one module that already imports both BCs. Its
  own `## Consequences` recorded the cost — *"roughly thirty lines with
  behaviour, which is not wiring"* — as a finding for this Stage. Issue #47
  asks to move it into `features/staff/adapters/out/identity/`, accepting the
  suppressions. Issue #45 (M1/Gate 1) measured the deeper problem: the
  composition root is the one file no import contract inspects, and *"when an
  import rule got in the way, the code went where the linter does not look"*.
- **`IdentityGuard` is unimportable.** It lives in
  `features/identity/adapters/in/http/dependencies.py`; `in` is a Python
  keyword, so no static import can name it. Any module wrapping it holds an
  `Any` obtained via `importlib` — and that edge is invisible to import-linter
  wherever the wrapper lives.
- The sponsor asked for the approach to be checked against **official
  documentation and validated projects** before deciding.

### What the sources say

| Source | Finding |
|---|---|
| Evans, *DDD* (Anticorruption Layer; Open Host Service; Published Language); Vernon, *IDDD* and the reference implementation [IDDD_Samples](https://github.com/VaughnVernon/IDDD_Samples/tree/master/iddd_collaboration/src/main/java/com/saasovation/collaboration/port/adapter/service) | The ACL belongs to the **downstream** context and lives in its **adapters**: `collaboration/port/adapter/service/{UserInRoleAdapter, TranslatingCollaboratorService, CollaboratorTranslator}` translate IdentityAccess for Collaboration. The upstream offers an OHS with a Published Language. |
| Grzybek, [*Modular Monolith: Integration Styles*](https://www.kamilgrzybek.com/blog/posts/modular-monolith-integration-styles) | *"On the caller side, it could just be a gateway, on the callee side a facade."* Modules treat each other as external and expose **only what is needed**. |
| Martin, *Clean Architecture* ch. 26 (read through a [third-party summary](https://github.com/serodriguez68/clean-architecture/blob/master/part-5-2-architecture.md), not the book) | Main is *"the lowest-level policy"* and a plugin to the application: it creates Factories, Strategies and global facilities, then hands control to the high-level portions of the system. Business rules are not its job. |
| Garrido de Paz, [*The right boundary*](https://jmgarridopaz.github.io/content/therightboundary.html) | *"Put everything that touches the real world on the outside."* ACL semantics and the technological adapter are distinct concerns — **and he places the semantic translation inside the hexagon**, not in the adapter. This ADR follows Vernon instead (translation in the downstream's adapter): with `bc-independence` forbidding identity's types inside staff's application, the adapter is the only place the translation can live. Divergence stated, not glossed. |
| Microsoft, [*Anti-Corruption Layer pattern*](https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer) | *"Make sure that you maintain and monitor transaction and data consistency"* (verbatim, in the considerations). And, stated as the condition under which the pattern may not fit: *"focus the anti-corruption layer on translation logic. Avoid placing business rules or orchestration in the layer."* Read here as the discipline for the gateway, not as a general prescription. |
| import-linter, [*Independence*](https://import-linter.readthedocs.io/en/stable/contract_types/independence/) (project pins 2.13) | `ignore_imports` is the **official** exemption mechanism; `*` stands in for a module name and `**` for subpackages (this ADR uses `*`); there is **no** notion of a "public API" — the discipline has to be the **shape** of the pairs. |

Against the project's own premises: LAYOUT §1 and §3 are compatible and
silent on "adapter → another BC's application", which this ADR now regulates
(the sentence *"BCs communicate through ports; identifiers cross as opaque
strings"* lives in the `.importlinter` comment of `bc-independence` and in
staff's `identifiers.py`, not in LAYOUT); the `composition-root` skill's
*"integration between BCs lives in bootstrap"* speaks of **wiring**, which stays
in the composition root; ADR 0.0.0005 clause 3 names the composition root as the
trusted layer that resolves the tenant — still true, because the guard does not
move.

## Decision

**1. identity exposes an in-process Open Host Service.**
`features/identity/application/facade.py` holds `IdentityFacade`: operations
with **primitive** signatures (`str`, `Sequence[str]`), converting to value
objects internally (`Email(...)`, `Role.from_string(...)`, `RestaurantId`,
`UnitId`), calling identity's own use cases, and **raising identity's exceptions
untranslated**. The module **re-exports** the exception classes a consumer is
expected to translate (today `EmailAlreadyRegisteredError`, `InvalidEmailError`),
so that a consumer never needs a second identity module. The facade does **not**
authorize — no identity use case does today (#49); the caller's boundary does.

**2. staff implements its port in a gateway adapter that imports only the
facade.** `features/staff/adapters/out/identity/local_identity_gateway.py`
implements `IdentityGateway` (staff vocabulary, four published laws — concept §4)
over `IdentityFacade`, pins the role to `"employee"` as a **value**, translates
exactly the errors the port names and lets everything else propagate raw (same
reasoning as L-AG1/L-AG2: no second error band for a condition that already has
a handler).

**3. `bc-independence` carries exactly one named pair, and the shape is the
rule:**

```
ignore_imports =
    restaurant_hub.features.staff.adapters.out.identity.* -> restaurant_hub.features.identity.application.facade
unmatched_ignore_imports_alerting = error
```

The wildcard is on the **consumer side only** and matches module names, not
subpackages: any module added under `adapters/out/identity/` inherits the
permission; any staff module elsewhere, and any import of identity that is not
the facade, still fails. `test_bc_independence.py` stops asserting *"the list
does not exist"* and asserts **the exact list**, so that a second edge enters by
decision, never by drift. The AST sweep for identity's access vocabulary
(`Role`, `Permission` never **named** in staff) is unchanged and still passes.

**4. This is the pattern for every future in-process crossing.** LAYOUT §3 gains
the rule: *an adapter of one bounded context may import from another bounded
context **only** that context's facade, through a named `ignore_imports` pair.*
When `scheduling` needs `staff` (roadmap 4.3, `StaffReadPort`), staff gets a
facade and scheduling a gateway, and the contract gets a second — named — pair.

**5. `_IdentityAccessGuard` stays in `composition_root.py`; issue #47 is
re-scoped.** The translator wraps `IdentityGuard`, which lives under the `in`
package and is therefore an `Any` obtained by `importlib` wherever it is placed.
Moving it into staff would create an **adapter → adapter, cross-BC edge that no
import contract can see** — the opposite of what #47 seeks. The honest move
requires identity to expose authentication/authorization **outside `in/`**
(an access facade), which is a redesign of the 2.4 guard, not a file move. That
is recorded on #47 at Stage close; the Gate 1 allowlist of #45 keeps the debt
countable meanwhile.

## Alternatives considered

### Alternative A — the gateway imports identity's internals directly
- **Description:** no facade; the adapter imports `ProvisionAccountUseCase`,
  `SendInvitationUseCase`, `RevokeAllSessionsUseCase`, their commands and
  results, `Email`, `Role`, `RestaurantId`, `UnitId` and two error classes.
- **Pros:** no new module in identity; the adapter is a plain wrapper.
- **Cons:** about **ten** `ignore_imports` pairs, each coupling staff to an
  internal name of identity; a refactor inside identity (rename a command,
  split a use case) breaks staff; every new internal used is a new pair, and
  the exact-list test becomes a changelog rather than a guard. It is precisely
  what Grzybek and Vernon warn against — a module reaching into another
  module's interior instead of its published surface.
- **Why rejected:** buys nothing the facade does not, and trades one edge for
  ten.

### Alternative B — assemble the gateway in the composition root (the 3.4 shape)
- **Description:** repeat ADR 3.4.0001 §3: the gateway class lives in
  `composition_root.py`, zero suppressions.
- **Pros:** `bc-independence` stays literally absolute.
- **Cons:** Main would host **orchestration and translation** for a use case —
  the thing Martin ch. 26 says Main must not do, and the exact debt #45/#47
  already measured for the guard; the roadmap's fixed layout for 3.5 would be
  contradicted; the composition root — the one un-gated file — would grow by
  another ~80 lines of behaviour.
- **Why rejected:** repeats a debt the project has already decided to stop
  accruing.

### Alternative C — facade, and move `_IdentityAccessGuard` too (issue #47 literally)
- **Description:** both translators in `features/staff/adapters/out/identity/`.
- **Pros:** closes #47; symmetric layout.
- **Cons:** the guard translator would still hold an `Any` from `importlib`
  and still reach `identity/adapters/in/http/` — an edge invisible to
  import-linter, now between two adapters of two BCs. The debt would stop being
  **countable** (Gate 1 allowlist) and become **unmeasured**.
- **Why rejected:** trades visible debt for invisible coupling. The right fix
  is on identity's side and is the re-scoped #47.

### Alternative D — an event/message between the two BCs
- **Description:** staff publishes "login requested", identity reacts.
- **Pros:** lowest coupling.
- **Cons:** the request is synchronous by nature — the manager needs the link in
  the response; there is no bus in the project; a monolith-internal message bus
  for one use case is machinery without a second consumer (LAYOUT §4 rule for
  `shared`).
- **Why rejected:** wrong tool for a request/response the client waits on.

### Alternative E — do nothing (no gateway; staff never talks to identity)
The DoD of the Stage is the crossing. Not acceptable.

## Consequences

### Positive
- The crossing is **one aresta**, named, tested exactly, and shaped as the DDD
  literature prescribes (OHS upstream, ACL downstream).
- identity gains a **Published Language** for in-process consumers; the next BC
  reuses the pattern instead of re-deciding it.
- The composition root stays wiring-only for this Stage; nothing new escapes
  the linter's sight.
- The re-scoped #47 now names the actual precondition for moving the guard.

### Negative
- `bc-independence` is no longer *absolute*: a suppression exists. The
  exact-list test and `unmatched_ignore_imports_alerting = error` are the
  compensations, and CA07 of the concept pins both.
- identity's application layer grows a module whose only consumer is another
  BC — a small surface that must be kept **primitive** and **unauthorized**
  (the caller authorizes), which is a discipline, not a gate.
- Two translators of identity now live in two places (facade-based gateway in
  staff; `Any`-based guard in the composition root) until #47 lands.

### Neutral / trade-offs accepted
- The facade duplicates two error names in its namespace (re-export). That is
  the price of "one module to import".
- The facade is **not** a `Protocol`: it is identity's concrete surface. The
  abstraction staff depends on is staff's own port; a fake for the facade is
  not needed because the gateway's contract test runs the **real** facade over
  identity's in-memory fakes.

## Implementation notes

- Facade construction happens in `composition_root.py`, over the **same**
  repositories, `Engine`, `EmailSender` and `Clock` that serve identity's
  routes — not a second graph (CA21 asserts object identity).
- The gateway's contract test (`tests/contract/features/staff/test_identity_gateway_laws.py`)
  runs one suite against `InMemoryIdentityGateway` and against
  `LocalIdentityGateway(IdentityFacade(...over identity fakes...))` — the
  fake-vs-real pairing of ADR 2.3.0003 / 3.3.0007 applied to a cross-BC
  adapter.
- `check_layout.py` needs no change: rule 3 forbids `adapters/out` importing
  another feature's **adapters**; `identity.application.facade` is application.
- `LAYOUT.md` §3 gets the one-sentence rule and the tree in §2 gets
  `application/facade.py` as an optional per-feature module.

## References
- `docs/stages/3.5-employee-login-link/concept.md` §5.9, §5.10, §7 D1, §13 Q2,
  CA07, CA08, CA21
- ADR 3.4.0001 (§3 partially superseded; §Alternative A measured the same
  keyword-`in` constraint); ADR 0.0.0005 clause 3; ADR 2.3.0003; ADR 3.3.0007
- Issues #45 (M1, Gate 1), #47 (re-scoped), #49
- `.importlinter` — contract `bc-independence`
- `docs/LAYOUT.md` §1, §3, §6
- External: the six sources in the table above

## Supersessão parcial

**2026-11-02 — §5, *"`_IdentityAccessGuard` stays in `composition_root.py`"*, fechada por
[ADR 0.0.0016](./0_0_0016-staff-access-guard-is-an-adapter-over-an-identity-access-facade.md)
(issue #47, re-escopada aqui).** identity passou a expor a decisão de acesso fora do adapter de
entrada — `IdentityAccessFacade`, segunda classe de `application/facade.py` —, e o tradutor é
`LocalAccessGuard`, segundo módulo de `staff/adapters/out/identity/`. A aresta continua **um**
par nomeado (§3): o módulo da fachada é o mesmo. A propriedade "a fachada não autoriza" (§1) se
lê, desde então, como "não autoriza as **próprias** operações": a fachada de acesso **expõe** a
decisão, não a exige de quem a chama. Nota *append-only*; o corpo acima não foi editado
(CONVENTIONS §5).

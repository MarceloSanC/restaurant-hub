---
title: ADR 0.0.0005 — The tenant appears in the request path only when the bounded context owns it as a resource or the actor may act outside its own tenant; otherwise it comes from the token, resolved in one trusted layer whose location follows the opacity of the actor
description: Architecture Decision Record
when-use: Reference before adding an HTTP route in any bounded context, when deciding whether a tenant/restaurant identifier belongs in the URL, when choosing where to resolve the tenant, or when a role gains the ability to act across tenants
keywords: [adr, transversal, multi-tenancy, tenant, rbac, boundary, confused-deputy, bola, asvs, http, routing]
status: accepted
created_at: 2026-08-18
updated_at: 2026-11-09
adr_id: 0.0.0005
decision: Three clauses — the tenant that decides access always derives from the token and any tenant in the request is only a declaration confirmed against it; it appears in the path only when the bounded context owns the tenant as an addressable resource or the actor may act outside its own tenant; and it is resolved in a single trusted layer whose location follows the opacity of the actor (the context's own adapter in identity, the composition root in staff)
context_stage: 3.6-staff-http
bounded_context: transversal
---

# ADR 0.0.0005 — The tenant comes from the token unless the context owns it as a resource

> ⚠️ **Errata (2026-11-09):** §Decision, the clause on where `identity` resolves the tenant — the router local `ator` was renamed to `actor` in issue #136 (pure rename, no behaviour change), so the read is now `actor.claims.tenant_id`, at `identity/adapters/inbound/http/router.py` › `create_user` and `invite_user` (the cited `:385`/`:435` had already drifted). Pointer only; no decision content changes — ver issue #136

## Status

`accepted`

> **Global (`bounded_context: transversal`), decided during Stage 3.6.** The rule
> governs `identity` retroactively and every bounded context that comes after, so
> pinning it to `staff` would hide it from the deterministic
> `grep -l "bounded_context: transversal" docs/adr/*.md` that every Stage runs when
> loading context. `context_stage` records where the decision was taken
> (CONVENTIONS §2), which is Stage 3.6.

## Context

Stage 3.6 exposes the `staff` bounded context over HTTP. Its route inventory,
ratified in `roadmap.md`, carries **no tenant segment**: `/job-functions` and
`/units/{unit_id}/employees`. Stage 3A measured that this makes all sixteen routes
**unreachable by every role**: `AuthorizeActionUseCase` step 3
(`_assert_tenant_scope`) denies any tenant-bound actor that does not name the
target tenant, and the `AccessGuard` port deliberately keeps the actor **opaque**
to staff (`Actor = object` — *"staff não interpreta o ator"*), so the router has
nothing to name it with.

```
manage_staff          RAISED TenantScopeRequiredError  ação de papel 'manager' exige declarar o tenant alvo
manage_job_functions  RAISED TenantScopeRequiredError  ação de papel 'manager' exige declarar o tenant alvo
```

The narrow question was where staff's router gets the tenant. The broad question —
which this ADR answers, because the narrow one cannot be settled without it — is
**where a tenant identifier belongs in a multi-tenant HTTP surface**, given that
`identity` already puts it in the path (`/restaurants/{restaurant_id}/units`) and
`staff` does not. Left unanswered, the difference reads as inconsistency, and the
next bounded context guesses.

Two facts frame the answer:

- **`identity` and `staff` differ in a principled way, not accidentally** — and
  the difference is **ownership of the resource**, not the shape of the actor.
  `identity` owns `Restaurant`: it creates it, addresses it, and nests units and
  owners under it. `staff` does not and cannot — the `bc-independence` contract
  forbids it from importing anything of `identity`, and it knows the restaurant
  only as an opaque string. On top of that, in `identity` the `platform_admin`
  operates **outside any tenant** (ADR 2.1.0002, ADR 2.4.0003), while in `staff`
  every actor is bound to exactly one tenant and no operation crosses tenants.
- **A user belongs to exactly one tenant** (`User.tenant_id`, `None` only for
  `platform_admin`), and the access token already carries it
  (`AccessTokenClaims.tenant_id`).

### What the literature says, and what it does not

Twelve sources were consulted. Six are load-bearing here; three arguments commonly
made in favour of putting the tenant in the path turned out to have **no primary
source at all** and are recorded as such.

- **Hardy, N. "The Confused Deputy (or why capabilities might have been
  invented)." ACM SIGOPS Operating Systems Review 22(4):36–38, 1988.** The
  prescription is that **designation and authority travel together** — *"The
  capability both identifies the file and authorizes"*. A `restaurant_id` in the
  path is **designation without authority**: it does not approximate a capability,
  it creates a name that then requires the separate "authority checking mechanism"
  Hardy is criticising. Moreover the attack requires a deputy serving **two
  masters** (*"serves two masters… no way to keep them apart"*); in this system a
  user has one tenant and `platform_admin` holds only `manage_platform`, so it
  never reaches a staff route. **The confused-deputy case is not instantiable
  today** — which is why this ADR carries a reopening trigger rather than a
  mitigation.
- **OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization.**
  Treats **path, query, header and body** as one and the same channel ("input from
  the client"). Putting the tenant in the URL therefore *increases* the API1
  surface by sixteen routes rather than reducing it. It also warns that
  *"comparing the user ID of the current session… with the vulnerable ID parameter
  isn't a sufficient solution"* — unit-level and record-level checks stay
  mandatory under every option (see Consequences).
- **OWASP ASVS 4.0.3, V4.1.2** — *"all user and data attributes and policy
  information used by access controls cannot be manipulated by end users"*. The
  chosen option satisfies this **structurally** (the attribute never leaves the
  token); the path option satisfies it only **procedurally**, contingent on none of
  the sixteen routes forgetting the comparison. **V4.1.1** — access-control rules
  enforced in a **single trusted service layer** — is what rejects the
  port-signature option below.
- **Microsoft Azure Architecture Center — "Identity in a multitenant solution."**
  Discriminates by **cardinality**: when a user belongs to one tenant, *"a tenant
  identifier claim is added to the token"*; when a user spans tenants, the caller
  declares which one. That is this system's model, literally.
- **AWS Well-Architected SaaS Lens — "Preventing cross-tenant access."** Tenant
  context via JWT **and** resolved centrally, *"outside the view of developers"*.
  The prescription is **centrality**, not a particular module — which is why
  clause 3 names the principle and derives the location instead of fixing it. In
  `staff` that location is `composition_root.py`, the single module that already
  imports both bounded contexts by design; in `identity` it is identity's own
  adapter.
- **Auth0 — "Work with Organization tokens."** Where a URL does participate, it
  **confirms** the claim (*"in conjunction with the current request URL"*), never
  replaces it. This is the shape defence-in-depth would take here if it is ever
  wanted, and it is the shape the reopening trigger points to.

**Market practice — convergent evidence, not prescription.** Across GitHub
(`/orgs/{org}`), Stripe (`/v2/core/accounts/{id}`), Twilio subaccounts, Stripe
Connect (header), Slack, Shopify and Auth0, the tenant sits **in the path when it
is the resource** and **in the credential when the credential belongs to the
tenant**. No vendor documents this as a rule; it is observed regularity, and it is
cited as corroboration only. This project's JWT is tenant-bound ⇒ credential.

**Three arguments that have no primary source.** No consulted documentation
prescribes (a) uniform tenant placement *across modules* of one API — Zalando's
"same author" is a product principle, and Google AIP-122 is a `should` about
**naming**, not authority; (b) cacheability, (c) audit-by-URL or
"self-descriptive URLs". If any of these are raised later they are judgement, not
literature, and should be labelled as such.

## Decision

**The rule (transversal), in three clauses.** It was written in one and the
first draft was **falsified by the merged `identity` code** during
re-verification; the version below is the one that survives measurement against
all ten identity routes and all sixteen staff routes.

> **1 — Authority.** The tenant that decides access always derives from the
> authenticated token. A tenant that arrives in the request is a **declaration
> confirmed against** the token — never a substitute for it, never the source.
> (ASVS V4.1.2; Auth0's *"in conjunction with the current request URL"*.)
>
> **2 — Placement.** A tenant identifier appears in the request path **only when**
> (i) the bounded context **owns the tenant as an addressable resource**, and the
> route addresses it or a sub-resource of it; or (ii) the actor may act **outside
> its own tenant**. Otherwise the tenant does not appear in the request at all.
>
> **3 — Resolution point.** Where the tenant comes from the token, it is resolved
> in a **single trusted layer** (ASVS V4.1.1), never per route. *Which* layer
> follows the **opacity of the actor**: the bounded context's own adapter when the
> token is that context's own, the **composition root** when a port deliberately
> keeps the actor opaque.

Measured against both bounded contexts, route by route:

| Rota | Clause | Onde o tenant vem |
|---|---|---|
| `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/password-reset-requests`, `/auth/password` (identity) | nenhuma — **não há decisão de acesso**: são públicas ou autorizadas pela posse do token apresentado | não há tenant alvo |
| `POST /restaurants` (identity) | — o tenant está sendo criado | corpo; ator é `platform_admin` |
| `POST /restaurants/{id}/owners` (identity) | 2(i) **e** 2(ii) — identity é dona de `Restaurant`, e `platform_admin` age fora de tenant | path, confirmado no passo 3 |
| `POST /restaurants/{id}/units` (identity) | **2(i) apenas** — identity é dona de `Restaurant` e a rota endereça um sub-recurso dele; o ator (`owner`) é de **um** tenant, logo 2(ii) é falsa | path, confirmado no passo 3 |
| `POST /users`, `POST /users/invitations` (identity) | nenhuma | claims, lidas no **adapter de identity** (cláusula 3: o token é de identity, o ator não é opaco para ela) |
| as 16 rotas de `staff` | nenhuma — **staff não é dona do restaurante**: não o importa (`bc-independence`), não o expõe, e só o conhece como string opaca | claims, resolvidas no **composition root** (cláusula 3: o port mantém `Actor = object`) |

**Duas correções que a medição impôs, e que valem mais que o enunciado original:**

- **`POST /restaurants/{id}/units` refutava a primeira redação.** Exige
  `MANAGE_TENANT`, que só o `owner` detém — ator de um único tenant —, e o recurso
  criado é a *unidade*. Nem "o tenant é o recurso" nem "o ator age fora do próprio
  tenant" a cobriam, e o ADR a apresentava como conforme. O que a cobre é a
  cláusula 2(i) reformulada: **identity é dona de `Restaurant` como recurso
  endereçável**, e `/restaurants/{id}/units` endereça um sub-recurso dele. Em
  `staff` essa cláusula é estruturalmente indisponível — o contrato
  `bc-independence` proíbe staff de conhecer `Restaurant` —, e é essa a diferença
  principiada entre os dois BCs, não uma preferência de estilo.
- **O ponto de resolução não é "o composition root" em toda parte.** `identity`
  lê `ator.claims.tenant_id` **no próprio router** (`router.py` › `create_user` e `invite_user`), e
  isso está certo: o token é dela, o ator não lhe é opaco, e o router é o seu
  *trusted layer*. Em `staff` o mesmo lugar é impossível por desenho — o port
  declara `Actor = object` justamente para que staff não leia atributo de ator —,
  e por isso a resolução desce ao composition root. A cláusula 3 nomeia o
  princípio (camada única) e deriva o lugar; a primeira redação nomeava o lugar e
  por isso descrevia mal um BC inteiro.

> **Limite honesto sobre `identity`, registrado e não corrigido aqui.** O
> docstring de `create_unit` justifica o `restaurant_id` do path pelo seu **efeito
> de autorização** (*"de modo que um `owner` de outro tenant falha em
> `_assert_tenant_scope`"*) — que é o argumento **fraco**, e é o mesmo que este
> ADR usa para **rejeitar** a Alternativa C em `staff`. O argumento que sustenta a
> rota é o outro: o path endereça um sub-recurso de um recurso que identity possui,
> e a autorização vem de carona. A distinção importa porque é ela que impede este
> ADR de provar coisas demais: em `staff` **não há** endereçamento de que a
> autorização pegue carona, então o parâmetro existiria *só* como alvo — a
> redundância que a Alternativa C paga sem contrapartida. Reescrever o docstring de
> `identity` é fora do escopo desta Stage; fica como `[finding]` no concept §10.

**The application in Stage 3.6:** `_IdentityAccessGuard.authorize` fills
`tenant_id` from the authenticated actor when the caller does not name one. **No
port signature changes** — `access_guard.py` already declares
`tenant_id: str | None = None`. What changes is that `None` acquires a documented
meaning at this boundary — *"the actor's own tenant"* — and that meaning is
recorded in the port docstring, so the contract states it instead of leaving it to
be inferred from one implementation.

**The law binds both implementations.** The in-memory fake must resolve the
actor's tenant the same way. A law honoured only by the production translator is
not a law; and two implementations exercised over different value sets is the
exact alert the `stage-audit` skill records as the strongest early signal of
"universal law, narrow representative".

**The resulting check is not vacuous.** The tenant travels token-claim → guard →
`AuthorizeActionUseCase` step 3, which compares it against the tenant of the user
**loaded from the database**. A token whose tenant no longer matches the stored
user is denied.

## Alternatives considered

### Alternative B — the port hands the actor's tenant to the router
- **Description:** `authenticate` returns a typed context carrying `tenant_id`, and
  each route passes it explicitly to `authorize`.
- **Pros:** every `authorize` call names its target in full, with no parameter
  whose absence carries meaning.
- **Cons:** it moves the tenant **out of** the trusted layer and into sixteen call
  sites, against **ASVS V4.1.1** (rules enforced in a single trusted service
  layer). It changes the signature of a port merged one Stage earlier, obliging
  both implementations and the law suite to follow. And it defeats the port's own
  reason for `Actor = object`: staff would begin reading attributes off the actor,
  which is where re-implementing the access decision starts.
- **Why rejected:** the objective is already met without it. `AuthorizedScope`
  returns the tenant **after** the decision, which is the correct moment —
  identity as an *outcome*. B moves it to before the decision, where the same value
  becomes an *input*, and an input is manipulable in a way an outcome is not.

### Alternative C — put the tenant in the path (`/restaurants/{id}/job-functions`)
- **Description:** mirror identity's URL shape across all sixteen staff routes.
- **Pros:** superficially uniform with identity; the tenant is visible in the URL.
- **Cons, each with a source:**
  - **No security gain.** Hardy: designation without authority is not a capability
    and adds an authority-checking obligation. OWASP API1:2023: a path parameter is
    client input like any other, so this adds sixteen routes to the BOLA surface.
    ASVS V4.1.2 goes from structurally satisfied to procedurally satisfied.
  - **No normative basis for the consistency argument.** No primary source
    prescribes uniform tenant placement across modules, and the difference between
    the two bounded contexts is principled (clause ii), not accidental.
  - **Concrete cost.** The parameter would have **exactly one legal value per
    caller** — the caller's own tenant — so every route would need a comparison
    that can only ever fail on abuse, plus a per-route × per-role test proving the
    comparison exists. Redundancy that must nonetheless be tested is the worst of
    both.
- **Why rejected:** it contradicts the ratified route inventory in `roadmap.md`,
  and buys nothing measurable in exchange.

### Alternative D — leave it unresolved and let each route decide
Rejected without discussion: it is the state that produced sixteen unreachable
routes and a difference between two bounded contexts that nobody could explain.

## Consequences

### Positive
- Cross-tenant action becomes **inexpressible** from `staff`: there is no input
  through which a client can name another tenant. This is the most restrictive of
  the three options, not the most permissive.
- Tenant resolution lives in one module, matching the AWS SaaS Lens shape
  ("outside the view of developers").
- The next bounded context has a criterion instead of a precedent to guess at, and
  the existing difference between `identity` and `staff` is explained rather than
  tolerated — **route by route, and not by generalisation**: the first draft of
  this rule classified `identity` in one line and was falsified by
  `POST /restaurants/{id}/units` on re-verification.
- Reversal is cheap: the port still accepts an explicit `tenant_id`, so adopting
  the Auth0 shape (URL confirms the claim) is additive.

### Negative
- `tenant_id=None` now carries meaning at this boundary, and meaning attached to
  absence is a pattern this project has been bitten by twice. The mitigation is
  that the meaning here is **restrictive** (the actor's own tenant, never a wider
  set), that it is written in the port docstring rather than inferred, and that
  both implementations are held to it by the same law.
- The tenant is not visible in a staff URL, so log correlation by URL alone is
  insufficient; it requires the token subject. Accepted — no consulted source
  treats audit-by-URL as a requirement.

### Neutral / trade-offs accepted — the limits this ADR does **not** remove
- **Unit-level and record-level authorization stay mandatory on every route**,
  under any of the three options. OWASP API1:2023 is explicit that matching the
  session's tenant is *not* sufficient. In this system that obligation is met by
  ADR 3.4.0007 (the unit is part of an employee's address, down to the repository
  port signature) and by the per-route unit authorization of Stage 3.6 §5.4.
- **`copy_employee_to_unit` is where that obligation is most fragile**, because it
  authorizes **two** targets — source and destination — and an inversion between
  them is silent. Stage 3.6 pins it with a dedicated criterion (CA16 and CA34).
- **`identity` is not migrated by this ADR, and two things there are left as they
  are.** Its tenant resolution lives in its own router (clause 3 covers it), and
  the docstring of `create_unit` justifies its path parameter by the weaker of the
  two available arguments. Both are recorded as `[finding]` in Stage 3.6's concept
  §10 rather than changed from a Stage whose target layer is `staff`.

## Reopening trigger

This decision rests on a measured property of the current access model, and the
property can change. **Revisit this ADR if either becomes true:**

1. a user can belong to, or act across, **more than one tenant**; or
2. `platform_admin` — or any role without a tenant of its own — gains reach over
   routes of a tenant-scoped bounded context.

Either one makes Hardy's confused deputy **instantiable**: the deputy would then
serve two masters, and the token would no longer determine the tenant on its own.
The sourced remedy is the **Auth0 shape** — the URL confirms the claim rather than
replacing it — and the cost of adopting it is low, because the port already accepts
an explicit `tenant_id` and the resolution point is a single module.

## Implementation notes

- **In `staff`**, resolve the tenant in `_IdentityAccessGuard.authorize`
  (composition root) and **not in staff's router**: the port keeps the actor
  opaque, so the composition root is the only module that legitimately knows both
  vocabularies. This is clause 3 applied to *this* context — it is **not** a
  prohibition on identity's router, which reads its own claims correctly and is
  not migrated by this ADR.
- Update the `AccessGuard.authorize` docstring so `tenant_id=None` states its
  meaning. The contract must not depend on reading the implementation.
- Update the in-memory fake to resolve the actor's tenant identically, and
  parameterise the law over **both** the "named tenant" and "omitted tenant" cases
  in **both** implementations.
- Do **not** add a `restaurant_id` query parameter as a compromise: OWASP API1
  treats query and path as the same channel, so it would carry every cost of C and
  none of its (absent) benefit.

## References
- HARDY, Norm. **The Confused Deputy (or why capabilities might have been
  invented).** ACM SIGOPS Operating Systems Review, v. 22, n. 4, p. 36–38, 1988.
  https://dl.acm.org/doi/10.1145/54289.871709 · full text:
  https://css.csail.mit.edu/6.858/2015/readings/confused-deputy.html
- OWASP. **API1:2023 Broken Object Level Authorization.** OWASP API Security Top 10
  — 2023 edition.
  https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP. **Application Security Verification Standard 4.0.3**, V4 Access Control
  (V4.1.1, V4.1.2).
  https://github.com/OWASP/ASVS/blob/v4.0.3/4.0/en/0x12-V4-Access-Control.md
- MICROSOFT. **Identity in a multitenant solution.** Azure Architecture Center.
  https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/identity
- AMAZON WEB SERVICES. **Preventing cross-tenant access.** AWS Well-Architected
  SaaS Lens.
  https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/preventing-cross-tenant-access.html
- AUTH0. **Work with Organization tokens.**
  https://auth0.com/docs/manage-users/organizations/using-tokens
- `docs/stages/3.6-staff-http/concept.md` §5.3, §7 D9, CA10, CA36
- `docs/stages/3.4-staff-access-scope/concept.md` §4 (the `AccessGuard` port and
  its four laws)
- `src/restaurant_hub/features/staff/application/ports/out/access_guard.py`
- `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  (step 3, `_assert_tenant_scope`)
- `src/restaurant_hub/composition_root.py` (`_IdentityAccessGuard`)
- ADR 2.1.0002 (platform_admin without tenant), ADR 2.4.0003 (authorization
  composed at the boundary), ADR 3.4.0007 (the unit enters the employee address),
  ADR 3.4.0008 (tenant-wide permissions), ADR 3.6.0001 (the path addresses the
  record)

## Supersessão parcial

**2026-11-02 — o local derivado pela cláusula 3 para `staff` (*"the composition root in
staff"*, frontmatter `decision` e §Implementation notes) superado por
[ADR 0.0.0016](./0_0_0016-staff-access-guard-is-an-adapter-over-an-identity-access-facade.md)
(issue #47).** O princípio não muda — uma camada confiável única, cujo lugar segue a opacidade
do ator. O que mudou foi a premissa da derivação: o ator deixou de ser um `Any` que só o
`composition_root` podia ler e passou a ser o `AccessPrincipal` publicado pela fachada de
identity, produzido e lido pelo `LocalAccessGuard` de `staff/adapters/out/identity/`. É lá que o
tenant omitido é resolvido agora, com leitura tipada — e, como antes, **nunca** no router de
staff. As cláusulas 1 e 2 seguem intactas. Nota *append-only*; o corpo acima não foi editado
(CONVENTIONS §5).

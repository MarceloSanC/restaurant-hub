---
title: ADR 0.0.0020 — Identity use cases that act for an actor authorize their own target, and the rule becomes transversal
description: Architecture Decision Record
when-use: Reference before adding or changing an identity use case that creates, invites or provisions an account, a restaurant or a unit; before adding any non-HTTP inbound adapter (CLI, worker, admin console, seed command) to identity; before adding a use case to a new bounded context; or when revisiting ADR 2.4.0003 Alternative C
keywords: [adr, identity, authorization, application, fail-closed, defense-in-depth, second-driver, platform-admin, escalation, transversal, issue-115]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-09
adr_id: "0.0.0020"
decision: 'Identity adopts the ADR 3.7.0001 shape for the four use cases that act on behalf of an authenticated actor (ProvisionRestaurant, CreateUnit, CreateUser, InviteUser): the actor travels in the command, and the use case declares its own access requirement and runs it through AuthorizeActionUseCase before any other statement, while the HTTP boundary keeps authorizing as defense in depth. The ten other identity use cases are out by kind (credential-as-authority, the decision itself, facade-only) and the inventory says why. Implementation is Stage 2.7-identity-application-authorization. With a third bounded context following it, the rule "every use case that acts for an actor authorizes its own target" is transversal (ADR 4.3.0002 §5 trigger): each bounded context keeps its own port shape.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0020 — Identity use cases that act for an actor authorize their own target

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided in issue #115 (finding F2 of issue #67). Standalone issue, hence the `0.0`
prefix and `bounded_context: transversal` (CONVENTIONS §1, "ADR global"; the
`check_adr_bounded_context` gate requires `transversal` for a `0_0_*` ADR), as for ADRs 0.0.0014
and 0.0.0018, which also decided identity questions in standalone issues. The content is in fact
transversal: §Decision 5 is the promotion that ADR 4.3.0002 §Decision 5 scheduled for the third
bounded context. The number was checked free on `develop`, on every remote branch and in every
open worktree on 2026-11-09 (`0.0.0019` is taken by issue #154, PR #157).

The decision is taken now and implemented by Stage `2.7-identity-application-authorization`
(roadmap §Stage 2.7). Until that Stage merges, the code still matches ADR 2.4.0003 §1. Several
texts still call the question open, and Stage 2.7 updates them: the facade module docstring, the
docstrings of two identity use cases and two staff modules, the domain doc
`tenancy-and-access.md`, and ADR 3.5.0001 (§Implementation notes).

**Will partially supersede, when Stage 2.7 merges** (each gets an append-only dated note in
that Stage, CONVENTIONS §5):

- ADR 2.4.0003 §Alternative C, the rejection *"duplicates the authorization decision"* (§Decision 3
  below answers it), and the negative consequence about the second inbound adapter.
- ADR 0.0.0014 §Decision 4 › "takes no actor, like every identity use case". The four use cases
  of the inventory take an actor, and the boundary keeps authorizing.
- ADR 0.0.0018 §Decision 3, where the owner route *"reuses"* `InviteUserUseCase`: the owner
  invitation gets its own entry point (§Inventory).
- The check order that ADR 0.0.0018 §Decision 2 and ADR 0.0.0014 §Decision 1 set for
  `ProvisionRestaurantUseCase`, and that concept 2.2 §5.7 sets for user creation (global e-mail
  uniqueness first). That order still holds, but **after** the authorization block. This is the
  same partial supersession ADR 3.7.0001 applied to ADR 3.6.0004.

## Context

1. **Where identity authorizes today.** In the identity HTTP router, every authenticated route
   calls the guard and then the use case. The use cases take no actor (ADR 2.4.0003 §1). Staff
   (ADR 3.7.0001) and scheduling (ADR 4.3.0002) authorize inside each use case.
2. **What a second driver gets today.** It gets more than the issue states. The issue notes that
   the provisioning role is the literal owner role. But `CreateUserUseCase` and
   `InviteUserUseCase` take the role from the command and accept `Role.PLATFORM_ADMIN` with no
   tenant (`create_user.py` › `CreateUserUseCase.execute`, `invite_user.py` ›
   `InviteUserUseCase.execute`). The HTTP guarantee that no route emits a
   platform administrator (ADR 2.4.0003 §2b) comes from the requirement set the router adds in
   `dependencies.py` › `required_permissions_for_role`, because no role holds both
   `manage_users` and `manage_platform`. That set is not part of the use case. A CLI, worker or
   console that calls either use case directly can create a platform administrator, or create an
   owner in any tenant. ADR 2.4.0003 had already flagged this: *"it must be revisited the moment a
   second one appears"* (§Consequences).
3. **When a second driver may appear.** There is no non-HTTP identity driver today. Two are
   foreseeable. The first is an idempotent seed command for the first platform administrator
   (ADR 2.4.0003 §Consequences, with Stage 6.3 as the candidate). The second is any admin console
   or worker that comes with the pilot. The issue asks for the decision before either one exists.
4. **Precedent and its price.** ADR 4.3.0002 §Alternative B rejected retrofitting scheduling
   later because the staff retrofit had cost *"17 use cases and ~20 suites in 3.7"*. Identity's
   affected set is four use cases (inventory below).
5. **What ADR 2.4.0003 §Alternative C objected to.** Its argument was that *"Two places would
   then evaluate access."* The 3.7 shape does not create a second evaluator. The use case
   **declares** a requirement and calls the same `AuthorizeActionUseCase`, which remains the only
   place that **decides**.

## Decision

```
[decision:C] 0.0.0020-1 — does identity authorize its own target in the application layer?
Escolha: yes, ADR 3.7.0001 shape · Alternativas: boundary only (status quo); boundary only + gate
that forbids a non-HTTP identity adapter until a Stage decides; authorizing decorator · Degrau (C): 2
Base: ADR 2.4.0003 §Consequences › "it must be revisited the moment a second one appears";
ADR 3.7.0001 §Alternative A › "the guarantee must hold for whoever constructs the use case";
create_user.py › CreateUserUseCase.execute (accepts Role.PLATFORM_ADMIN with no tenant)
Verificado: sustenta (evidence-verifier, 2026-11-09, 6/6 items); completeness by decision-reviewer
Configuração candidata: nenhuma · Reversível: sim (pre-release; commands and constructors are internal)
```

Rung 2 decides. The fork concerns authentication, tenant isolation and the creation of the most
privileged role, and the option that denies by default is the one where the use case refuses
without help from the caller. Rung 1 points the same way: two bounded contexts already follow the
rule.

```
[decision] P delegado — adotar agora, com Stage própria no roadmap (2.7) e sem esperar o segundo
driver, motivo: critério do sponsor (esqueleto escalável com implementação mínima, não o atalho
que exige refazer a forma depois); o conjunto afetado é de quatro use cases, o custo da dupla
autorização cai em rotas administrativas de baixa frequência, e esperar o driver faria o retrofit
competir com a Stage que o cria.
```

1. **The affected set is every identity use case that acts on behalf of an authenticated actor.**
   Today that is four: `ProvisionRestaurantUseCase`, `CreateUnitUseCase`, `CreateUserUseCase` and
   `InviteUserUseCase`. The inventory below records why each of the other ten is out. "Every" is
   enforced by a property over the `use_cases/` folder (as in staff). An exclusion is a named entry
   with its reason, not something left out by omission.
2. **The actor travels in the command.** The use case keeps its `execute(<Command>) -> <Result>`
   shape (LAYOUT §5, ADR 0.0.0006, ADR 3.7.0001 §Decision 2). The command does not carry the HTTP
   type `AuthenticatedActor`, because the application layer cannot import an inbound adapter. Stage
   2.7's concept picks the application-side type.
3. **The use case declares its requirement, and `AuthorizeActionUseCase` decides it.** Each
   affected use case authorizes its own target before any other statement of `execute`, with the
   permission set it requires. For user creation, that set is "you cannot grant what you do not
   hold" (ADR 2.4.0003 §2), so `required_permissions_for_role` moves from the HTTP adapter to the
   application layer, as ADR 3.7.0001 §Decision 5 moved staff's permission vocabulary into its
   port module. No role table is added, and no access rule is evaluated outside
   `AuthorizeActionUseCase` and the `User` entity (ADR 2.2.0002).
4. **The HTTP boundary keeps authorizing.** Its calls, their order and its status bands do not
   change: the boundary becomes defense in depth, not the only line (ADR 3.7.0001 §Decision 6). The
   e2e suites must pass unchanged.
5. **The rule is transversal from now on.** ADR 4.3.0002 §Decision 5 said that *"it becomes a
   transversal ADR when a third BC repeats it"*. Identity is that third bounded context. The rule:
   **every use case that acts on behalf of an authenticated actor authorizes, before any other
   statement, the target its command declares, and the HTTP boundary keeps its own check.** A new
   bounded context follows it from its first use case. Each bounded context keeps its own port
   shape (ADR 4.3.0002 §Alternative A: no shared port, because `bc-independence` forbids it and the
   shapes differ). For identity, the decision is its own use case. Whether the four use cases
   depend on `AuthorizeActionUseCase` directly or on a narrow port of their own is left to the
   Stage 2.7 concept. LAYOUT §5 has the use case depend on an interface, and a port also gives the
   "denying decision means no effect" property a fake to deny with. A direct dependency has to
   justify the deviation in the concept.
   **Exclusions are named, never implicit.** A use case may stay outside the rule only through an
   entry, with its reason, in its bounded context's inventory, as the table below does for
   identity and ADR 3.7.0001 §Alternative D did for staff (none survived). A use case driven by a
   system job, with no authenticated actor (for example the timeclock sync planned for Stage 7.3),
   is not exempt by default. It waits for the system or delegated actor of issue #75, or for an
   exclusion recorded in its own Stage.

### Inventory — identity use cases on develop at 883ccb8

| Use case | Driver today | Boundary requirement | Status |
|---|---|---|---|
| `ProvisionRestaurantUseCase` | `POST /restaurants` | `manage_platform`, no tenant | **affected** |
| `CreateUnitUseCase` | `POST /restaurants/{id}/units` | `manage_tenant` on the path tenant | **affected** |
| `CreateUserUseCase` | `POST /users` | `{manage_users} ∪ role.permissions`, per requested unit, actor's tenant | **affected** |
| `InviteUserUseCase` | `POST /users/invitations` **and** `POST /restaurants/{id}/owners` | two different requirements (see below) | **affected** |
| `AuthenticateUserUseCase` | `POST /auth/login` | public | out: the password is the authority, no actor exists yet |
| `RefreshSessionUseCase` | `POST /auth/refresh` | public | out: possession of the refresh token is the authority |
| `RevokeSessionUseCase` | `POST /auth/logout` | public | out: same as refresh |
| `RequestPasswordResetUseCase` | `POST /auth/password-reset-requests` | public | out: public by design, constant answer |
| `SetPasswordWithTokenUseCase` | `POST /auth/password` | public | out: the setup token is the authority |
| `AuthorizeActionUseCase` | the guards | — | out: it **is** the decision |
| `ProvisionAccountUseCase` | `IdentityFacade` only | — | out: facade-only; the consumer authorizes (ADR 3.5.0001 §Decision 1; staff's use case authorizes `manage_staff` and `manage_users` before it crosses, ADR 3.7.0001) |
| `SendInvitationUseCase` | `IdentityFacade` only | — | out: facade-only, same reason |
| `RevokeAllSessionsUseCase` | `IdentityFacade` only | — | out: facade-only, same reason |
| `GetAccountRoleUseCase` | `IdentityFacade` only | — | out: facade-only, same reason |

`_invitation.py` is a helper module, not a use case. The four facade-only use cases are out
because ADR 3.5.0001 says the facade does not authorize: its consumer does. Making them authorize
would mean carrying identity's actor across the facade, which reverses ADR 3.5.0001 §Decision 1.
**This exclusion leaves a known residual.** `ProvisionAccountUseCase`, and
`IdentityFacade.provision_account` above it, take the role as input (a string at the facade) and
accept `platform_admin` with no tenant, just as `CreateUserUseCase` does today. Only the staff
gateway's fixed `"employee"` and staff's own authorization protect them. ADR 3.5.0001 already
calls this protection *"a discipline, not a gate"*. Stage 2.7's concept must close or restate it.
The cheapest closure that keeps the facade unauthorized is to restrict the roles the facade accepts
(the facade serves employee logins). A new consumer of any facade-only use case has to be
classified against this table.

**`InviteUserUseCase` carries two requirements.** The tenant route requires the composition set
with the actor's tenant. The platform route requires `manage_platform`, with the literal owner
role and the tenant taken from the path (ADR 0.0.0018 §Decision 3). A single use case that declares
its own requirement cannot choose between the two without reading the actor's role, which is the
access rule leaking out of `AuthorizeActionUseCase`. Stage 2.7 must give the platform owner
invitation its own entry point. A separate use case and a separate command are both acceptable. The
concept picks one, and the owner role stays a code literal.

## Alternatives considered

### Alternative A — Keep authorization at the boundary only (status quo)
- **Pros:** no work; one authorization per request.
- **Cons:** the defect in Context 2 stays reachable as soon as a non-HTTP driver exists, and the
  only reminder is a paragraph in ADR 2.4.0003. The project would also have two conventions, one
  for staff and scheduling and one for identity, which is the split ADR 0.0.0014 §Decision 4 left
  for this issue.
- **Why rejected:** rung 2. Fail-closed depends on a caller's discipline.

### Alternative B — Boundary only, plus a gate that forbids a non-HTTP identity adapter
- **Description:** a test asserts that `features/identity/adapters/inbound/` holds only `http/`,
  so the Stage that adds a driver is forced to reopen the question.
- **Pros:** costs one test now and defers the work until there is a real consumer.
- **Cons:** it closes only the door the gate looks at. A seed script under `scripts/` or a worker
  wired in the composition root calls the use case without being an inbound adapter of identity.
  The retrofit would also land inside the Stage that introduces the driver, which is the
  "redo the shape later" outcome the sponsor's criterion rejects.
- **Why rejected:** this is the shortcut that requires redoing the shape later. Recorded as the
  fallback if Stage 2.7 is ever dropped.

### Alternative C — An authorizing decorator around the four use cases
- **Why rejected:** for the reason in ADR 3.7.0001 §Alternative A. The unguarded use case still
  exists and can be constructed, so the guarantee belongs to the wiring and not to the use case.

### Alternative D — Put all fourteen use cases in scope
- **Why rejected:** five of them have no actor by definition (the credential is the authority),
  one of them is the decision, and four are facade operations whose caller already authorizes. An
  actor field in a login command would be a field nobody can fill.

## Consequences

### Positive
- No direct caller of the four use cases can create a `platform_admin`, an `owner` outside its
  tenant, or a unit in another tenant, because the composition rule of ADR 2.4.0003 §2 is enforced
  wherever the use case is constructed. This holds for those four use cases only, not for account
  creation in identity as a whole: the facade path is the residual named in §Inventory.
- Every bounded context follows the same rule, and a new one starts with it.

### Negative
- **Double authorization on four routes.** Each provisioning and unit route adds one
  `AuthorizeActionUseCase` call: one `users.find_by_id`, plus the unit reads when a unit is named.
  User creation and invitation add `|{manage_users} ∪ role.permissions| × max(1, |units|)` calls,
  which is 1 for an employee, 3 for a manager or hr, and 4 for an owner, per unit. All of these are
  keyed reads on administrative writes, which are expected to be infrequent. That frequency is an
  expectation, not a measurement. Login, refresh, logout and reset take no actor and pay nothing.
  Under load, nothing has been measured. Issue #78 measures staff's double authorization, and the
  same measurement would cover these four routes.
- Mechanical churn: the four commands, their call sites and their unit suites change, and the
  owner invitation gets its own entry point.
- **The guarantee is "authorized", not "authentic".** This is the threat model of ADR 3.7.0001:
  an in-process driver that forges an actor still passes. Issue #75 (actor authenticity, including
  a system or delegated actor that identity issues) and issue #76 (identifier validation outside
  HTTP) were written for staff. Identity has the same two gaps. Widening both issues to identity
  was still pending on 2026-11-09 (a finding recorded on issue #115). Both stay non-goals of
  Stage 2.7.
- **A seed command for the first `platform_admin`** has no actor that can authorize it, by
  definition, since it is the root of trust (ADR 2.4.0003 §2). It needs its own path outside these
  use cases, decided by the Stage that builds it, and it must not reuse `CreateUserUseCase` with a
  bypass.

### Neutral
- Owner self-signup (Step 13) will be a public use case of its own, not
  `ProvisionRestaurantUseCase` with a missing actor: the requirement belongs to the use case.

## Implementation notes (for Stage 2.7)

- Questions for the concept: the application-side actor type; whether the two leak translations
  of `authorize_at_boundary` (ADR 2.4.0001 §5, ADR 0.0.0016) also apply inside the use case or
  stay at the boundary; and the owner invitation's entry point.
- Properties as in staff (`test_use_cases_authorize.py`): a denying decision means no effect;
  totality over `use_cases/` with the named exclusions of the inventory; exact targets; and a
  real-chain test for each role, including a direct call that tries to create a `platform_admin`.
- The append-only notes listed under §Status go in that Stage, along with the texts that still
  call the question open. Those are: the facade module docstring;
  `get_account_role.py` and `provision_restaurant.py` (docstrings);
  `staff/application/ports/out/identity_gateway.py` and
  `staff/adapters/out/identity/local_identity_gateway.py` (docstrings);
  `docs/domain/identity/tenancy-and-access.md`; and ADR 3.5.0001 (append-only note).

## References

- Issue #115; issue #67 (finding F2); issues #75, #76, #78
- [ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md) §1, §2, §2b, §Alternative C, §Consequences
- [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md) §Decision 2–6, §Alternative A, threat model
- [ADR 4.3.0002](./4_3_0002-every-scheduling-use-case-authorizes-its-own-target.md) §Decision 5, §Alternatives A and B
- [ADR 0.0.0014](./0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) §Decision 4
- [ADR 0.0.0018](./0_0_0018-restaurant-owner-is-provisioned-by-invitation.md) §Decision 3
- [ADR 3.5.0001](./3_5_0001-cross-bc-facade-and-gateway-edge.md) §Decision 1
- [ADR 2.2.0002](./2_2_0002-authorization-two-axes-fail-closed.md), [ADR 0.0.0006](./0_0_0006-primary-ports-are-the-use-case-classes.md), [ADR 0.0.0016](./0_0_0016-staff-access-guard-is-an-adapter-over-an-identity-access-facade.md)
- `src/restaurant_hub/features/identity/adapters/inbound/http/router.py`,
  `src/restaurant_hub/features/identity/adapters/inbound/http/dependencies.py` › `required_permissions_for_role`,
  `src/restaurant_hub/features/identity/application/use_cases/`

## Nota — implementado pela Stage 2.7, com uma correção de §Inventory

**2026-11-09 — [ADR 2.7.0001](./2_7_0001-identity-authorizes-through-a-narrow-port.md) (Stage 2.7, issue #184).** A decisão está implementada. Os pontos que
este ADR deixou para o concept foram fechados lá: o ator é `actor_id: UserId`; os use cases
dependem de um port estreito (`ActionAuthorizer`) que `AuthorizeActionUseCase` cumpre; as duas
traduções de `authorize_at_boundary` valem dentro do use case, pela mesma função que a borda
usa; e o convite de dono tem use case próprio, `InviteOwnerUseCase`. O inventário passou a ter
quinze use cases, cinco afetados e as mesmas dez exclusões.

**Correção de §Inventory.** O parágrafo do resíduo diz que `IdentityFacade.provision_account`
aceita `platform_admin` sem tenant. A fachada nunca aceitou: ela recebe `tenant_id: str` e o
converte para `RestaurantId`, e o `User` recusa `platform_admin` com tenant
(`PlatformAdminTenantError`). Só o use case aceita. O que a fachada aceitava era `owner`,
`manager` ou `hr` em qualquer tenant existente, e a Stage 2.7 fechou isso: a fachada só provisiona
`employee`. No `ProvisionAccountUseCase` o resíduo continua. Um teste garante que só a fachada e o
composition root importam os use cases facade-only, e o primeiro chamador novo reabre a questão.
Nota *append-only*; o corpo acima não foi editado.

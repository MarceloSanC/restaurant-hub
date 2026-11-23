---
title: ADR 2.7.0001 — Identity use cases authorize through a narrow port over AuthorizeActionUseCase, the owner invitation gets its own use case, and the facade provisions employees only
description: Architecture Decision Record
when-use: Reference before adding an identity use case that acts on behalf of an actor, changing an identity command, adding a caller of authorize_requirement or required_permissions_for_role, or widening the roles IdentityFacade.provision_account accepts
keywords: [adr, identity, authorization, action-authorizer, port, invite-owner, facade, platform-admin, fail-closed, defense-in-depth]
status: accepted
created_at: 2026-11-09
updated_at: 2026-11-23
adr_id: "2.7.0001"
decision: 'The identity use cases that act for an actor carry actor_id: UserId first in their command, depend on a narrow ActionAuthorizer port that AuthorizeActionUseCase satisfies, and open execute with one authorize_requirement call that applies the boundary leak translations (the HTTP guard delegates to the same function); the platform owner invitation becomes InviteOwnerUseCase; IdentityFacade.provision_account refuses any role but employee.'
context_stage: 2.7-identity-application-authorization
bounded_context: identity
---

# ADR 2.7.0001 — Identity use cases authorize through a narrow port over AuthorizeActionUseCase

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — Stage 2.7 (issue #184). It implements
[ADR 0.0.0020](./0_0_0020-identity-use-cases-authorize-their-own-target.md) and answers the three
questions its §Implementation notes left to the Stage concept, plus the residual its §Inventory
left open (the facade). Number checked free on `develop`, on every remote branch and in every open
worktree on 2026-11-09.

## Context

1. ADR 0.0.0020 decided that `ProvisionRestaurantUseCase`, `CreateUnitUseCase`,
   `CreateUserUseCase` and `InviteUserUseCase` authorize their own target before any other
   statement, with `AuthorizeActionUseCase` as the only place that decides. It left open the
   application-side actor type, whether the use cases depend on `AuthorizeActionUseCase` or on a
   port, whether the two leak translations of `authorize_at_boundary` apply inside the use case,
   and the owner invitation's entry point.
2. Staff (ADR 3.7.0001) and scheduling (ADR 4.3.0002) carry an opaque `Actor = object`, because
   neither may name an identity type. Identity already names its actor in its own application:
   `AuthorizeActionCommand.actor_id: UserId`.
3. The requirement for user creation is a set (`{manage_users} ∪ role.permissions`) times the
   requested units. Today only `IdentityGuard.authorize_all`, in the HTTP adapter, expands it.
4. Measured on `develop` c753a52: `IdentityFacade.provision_account` takes `tenant_id: str`, so a
   `platform_admin` request fails in `User.__post_init__` (`PlatformAdminTenantError`). The facade
   does not emit a `platform_admin`; it does emit `owner`, `manager` or `hr` in any existing tenant.
   Its only consumer, staff's gateway, passes the literal `"employee"`.

## Decision

1. **The actor is `actor_id: UserId`**, the first field of each affected command, with no
   default. It is an identifier, not a credential, so it keeps its `repr`.
2. **The use cases depend on a narrow port.** `application/ports/out/action_authorizer.py`
   declares `ActionAuthorizer` (`execute(AuthorizeActionCommand) -> AuthorizedActor`).
   `AuthorizeActionUseCase` satisfies it structurally. The composition root injects the same
   instance the HTTP guard and the access facade use. This is a declared deviation from LAYOUT §5,
   where an outbound port is implemented by an adapter: here the decision belongs to identity, so
   no adapter exists. The port lets the use case depend on an interface and lets a test deny with
   a double. `required_permissions_for_role` moves into the same module, as ADR 3.7.0001
   §Decision 5 moved staff's vocabulary into its port module.
3. **One function expands and translates, for both callers.** `authorize_requirement`, beside
   `authorize_at_boundary` in `use_cases/authorize_action.py`, issues one request per
   (permission, unit), permissions sorted and units in the given order (one request with no unit
   when none is given), each through `authorize_at_boundary`. The first statement of every affected
   `execute` is a single call to it. `IdentityGuard.authorize_all` delegates to it, so the
   expansion has one copy (ADR 0.0.0016's rule for the leak translations, applied to the
   expansion). A direct driver therefore gets the same answer the boundary gives:
   `InvalidAccessTokenError` for an unknown actor and `UnitNotVisibleError` for an unknown unit.
4. **The platform owner invitation is `InviteOwnerUseCase`** with
   `InviteOwnerCommand(actor_id, email, tenant_id)`. It requires `manage_platform` with the
   tenant named, keeps `Role.OWNER` as a code literal and takes no units.
   `POST /restaurants/{id}/owners` runs it; `InviteUserUseCase` keeps only the tenant route.
5. **`IdentityFacade.provision_account` accepts `employee` only.** Any other known role raises
   `RoleNotProvisionableError`, a new error under identity's **application** root (ADR 3.9.0001:
   the role is valid in the domain; it is this entry that refuses it), as the first statement,
   before the e-mail conversion and before any port is called. An unknown role still raises
   `InvalidRoleError`. The facade still does not authorize (ADR 3.5.0001 §Decision 1): it narrows
   the input domain it serves. `ProvisionAccountUseCase` keeps accepting any role; what stops
   being a discipline is its reach — a test asserts that only `application/facade.py` and
   `composition_root.py` import the four facade-only use cases.

```
[decision:C] 2.7.0001-2 — port estreito × dependência direta de AuthorizeActionUseCase
Escolha: Protocol ActionAuthorizer · Alternativas: AuthorizeActionUseCase direto · Degrau (C): 1
Base: ADR 0.0.0020 §Decision 5 › "A direct dependency has to justify the deviation in the concept"; LAYOUT §5 › "O use case depende da interface"
Configuração candidata: nenhuma · Reversível: sim
```

```
[decision] P delegado — a fachada só provisiona employee (Recomendada), motivo: é o fechamento
que o ADR 0.0.0020 §Inventory aponta como o mais barato sem autorizar na fachada; o único
consumidor já passa "employee".
```

`required_permissions_for_role` moving module carries the mutation scope with it: the new port
module joins `only_mutate` in `pyproject.toml` and the exact list in `test_mutation_scope.py`, or
the rule would silently leave the set of access modules that mutation testing measures.

## Alternatives considered

### Alternative A — Depend on `AuthorizeActionUseCase` directly
- **Pros:** no new module; the real decision runs in every unit test.
- **Cons:** the use case depends on a concrete class, against LAYOUT §5, and the "a denying
  decision means no effect" property needs a full identity fixture to deny.
- **Why rejected:** ADR 0.0.0020 §Decision 5 asks the direct dependency to justify itself, and
  nothing does.

### Alternative B — Call `execute` raw inside the use case
- **Cons:** an unknown unit becomes `UnitNotFoundError` (404 band) inside the use case. If a route
  ever stops authorizing at the boundary, the enumeration oracle that ADR 2.4.0001 §5 closed
  reopens. It also keeps two copies of the permission × unit expansion.
- **Why rejected:** rung 2 of the convention ladder (fail-closed), and ADR 0.0.0016.

### Alternative C — `InviteUserUseCase` accepting two command types
- **Cons:** the requirement would be chosen by a type dispatch at the top of `execute`, which is
  the conditional the shape test forbids, and LAYOUT §7 asks for one use case per file.
- **Why rejected:** the separate use case keeps every affected `execute` the same shape. Its cost
  is a fifth copy of the invitation token step (ADR 0.0.0018 declared the earlier copies).

### Alternative D — Restate the facade residual instead of closing it
- **Cons:** the facade would keep emitting `owner`, `manager` or `hr` in any tenant, protected only
  by the gateway's literal. ADR 3.5.0001 calls that protection "a discipline, not a gate".
- **Why rejected:** the closure costs one check and one test, and it is what ADR 0.0.0020 names.

### Alternative E — Restrict the role inside `ProvisionAccountUseCase`
- **Cons:** the command is identity's and models any role; the restriction is about what the
  cross-context entry serves, and the facade is where the role arrives as text.
- **Why rejected:** the facade is the entry that decides what it serves; the use case's reach is
  pinned by the import test instead.

### Alternative F — Reuse `InvalidRoleError` for the facade refusal
- **Pros:** no new class and no new entry in the status map.
- **Cons:** `InvalidRoleError` is a domain error meaning "unknown role". A known role refused by an
  entry is not a domain rule; it would change the meaning of a domain error (ADR 3.9.0001, two
  roots by meaning).
- **Why rejected:** one class and one map entry cost less than a domain error with two meanings.

## Consequences

### Positive
- No direct caller of the five use cases or of the facade can create a `platform_admin`, or an
  `owner` outside the actor's tenant.
- The boundary and the application expand and translate the same way, because both call one
  function.

### Negative
- A fifth copy of the invitation token step.
- An outbound port with no adapter, declared here as a deviation.
- **Residual:** `ProvisionAccountUseCase`, called directly, still creates a `platform_admin` or an
  `owner` in any tenant. Only its reach is gated (the import test). The first new caller reopens
  the question, as ADR 0.0.0020 §Inventory requires.
- The `is_platform_admin` branches of `CreateUserUseCase` and `InviteUserUseCase` are no longer
  reachable by any real actor (no role holds `manage_users` and `manage_platform`). They stay as
  the check order of concept 2.2 §5.7, reachable with a test double.
- A new error class (`RoleNotProvisionableError`) with a 422 entry that no HTTP route reaches.

### Neutral
- The status bands do not change: the boundary authorizes the same requirement first.

## References

- [ADR 0.0.0020](./0_0_0020-identity-use-cases-authorize-their-own-target.md) §Decision, §Inventory, §Implementation notes
- [ADR 3.7.0001](./3_7_0001-every-staff-use-case-authorizes-its-own-target.md) §Decision 5
- [ADR 0.0.0016](./0_0_0016-staff-access-guard-is-an-adapter-over-an-identity-access-facade.md)
- [ADR 2.4.0001](./2_4_0001-http-error-status-mapping.md) §5; [ADR 2.4.0003](./2_4_0003-authorization-composition-at-boundary.md) §2, §2b
- [ADR 3.5.0001](./3_5_0001-cross-bc-facade-and-gateway-edge.md) §Decision 1
- [ADR 0.0.0018](./0_0_0018-restaurant-owner-is-provisioned-by-invitation.md)
- [LAYOUT](../LAYOUT.md) §5, §7
- Concept [2.7](../stages/2.7-identity-application-authorization/concept.md)

## Nota — o resíduo de `ProvisionAccountUseCase` fechado no use case

**2026-11-22 — issue [#211](https://github.com/MarceloSanC/restaurant-hub/issues/211).** A
última frase de §Decision 5 (*"`ProvisionAccountUseCase` keeps accepting any role"*), a rejeição
de §Alternative E e o item *"Residual"* de §Consequences › "Negative" deixam de valer. O use case
declara `PROVISIONABLE_ROLES` (hoje `{employee}`) em `provision_account.py` e recusa todo papel
fora dele como primeira instrução de `ProvisionAccountUseCase.execute`, antes de qualquer porta,
com a mesma `RoleNotProvisionableError` da fachada. Quem chama o use case direto, sem a fachada,
não cria mais `platform_admin` nem `owner`, `manager` ou `hr`.

O que muda em relação à Alternative E: ela foi rejeitada porque o command "models any role" e
porque a restrição seria sobre o que a entrada entre contextos serve. O command continua modelando
qualquer papel. Mas o use case também cria conta sem autorizar, então ele é, ele mesmo, uma entrada
que não autoriza, e o alcance (CA14) protegia só contra quem importa pelos idiomas que a varredura
vê. O resto desta decisão continua valendo. A fachada mantém a sua checagem, que é a primeira
instrução de `IdentityFacade.provision_account` e vem antes da conversão do e-mail, e as faixas HTTP
não mudam. Para as duas cópias da regra não divergirem, `test_facade.py` ›
`test_a_fachada_aceita_exatamente_os_papeis_que_o_use_case_aceita` as compara papel a papel sobre o
enum. `provision_account.py` entrou no escopo `only_mutate` do teste de mutação.

```
[decision] P delegado — fechar o papel no use case (Recomendada) em vez de registrar o resíduo como
aceito, motivo: critério do sponsor (fail-closed em código de acesso; esqueleto escalável com
implementação mínima).
```

```
[decision:C] #211-1 — forma do fechamento
Escolha: conjunto aceito declarado no use case (PROVISIONABLE_ROLES), checado primeiro · Alternativas: papel fixo no command (sem ProvisionAccountCommand.role, literal no use case, como InviteOwnerUseCase com Role.OWNER); resíduo aceito · Degrau (C): 2 descarta o resíduo; 4 decide entre o conjunto e o papel fixo
Base: §Decision 5 › "ProvisionAccountUseCase keeps accepting any role"; §Consequences › "Residual"; ADR 0.0.0020 §Inventory › "This exclusion leaves a known residual"
Verificado: sustenta — evidence-verifier (2026-11-23, auditoria do PR #235, 4/4 itens: as três citações da Base e PROVISIONABLE_ROLES checado primeiro em provision_account.py); completude por decision-reviewer (2026-11-22)
Configuração candidata: nenhuma · Reversível: sim
```

O degrau 4 decide porque o conjunto não muda a forma do command nem dos seus consumidores (fachada,
contrato de staff, integração). Alargar o conjunto continua sendo decisão de ADR: cada papel a mais
é conta privilegiada criada sem "não se concede o que não se detém". O ramo `platform_admin` com
unidades do use case fica, inalcançável enquanto o conjunto não incluir `platform_admin`, pela ordem
verbatim de `InviteUserUseCase` e pela mesma razão do concept 2.7 D6. Nota *append-only*; o corpo
acima não foi editado.

## Nota — a fachada lê `PROVISIONABLE_ROLES`: a regra de papel tem uma cópia só

**2026-11-23 — issue [#234](https://github.com/MarceloSanC/restaurant-hub/issues/234).** Na nota
de 2026-11-22 acima, *"A fachada mantém a sua checagem"* continua valendo, mas a checagem deixou de
ser uma segunda cópia da regra. `IdentityFacade.provision_account` confere
`papel not in PROVISIONABLE_ROLES`, com a constante importada de `provision_account.py`, no lugar do
literal `papel is not Role.EMPLOYEE`. A recusa continua sendo a primeira instrução depois da
conversão do papel (`Role.from_string`), antes do e-mail e de qualquer porta, com a mesma
`RoleNotProvisionableError`; papel desconhecido continua subindo `InvalidRoleError`.

A frase *"Para as duas cópias da regra não divergirem, `test_facade.py` ›
`test_a_fachada_aceita_exatamente_os_papeis_que_o_use_case_aceita` as compara papel a papel"* descreve
um estado que já não existe. Comparar a fachada com a constante que ela lê seria tautológico:
alargar o conjunto passaria verde. O teste virou
`test_a_fachada_recusa_antes_do_use_case_todo_papel_fora_do_conjunto`, que percorre o enum inteiro,
exige que o papel recusado não chegue ao use case e compara o conjunto aceito com `{employee}`
transcrito no próprio teste. Um segundo teste,
`test_a_fachada_segue_o_conjunto_do_use_case_e_nao_um_literal`, alarga a constante por dublê e trava
que a fachada a segue. Alargar o conjunto agora é editar um lugar no código, e a edição solta
continua reprovando nos dois testes que transcrevem `{employee}` (este e `test_provision_account.py`
› `test_o_conjunto_aceito_e_exatamente_employee`) até que um ADR a decida.

```
[decision:C] #234-1 — onde mora PROVISIONABLE_ROLES quando a fachada também a lê
Escolha: continua em use_cases/provision_account.py, importada pela fachada · Alternativas: mover para o domínio (value_objects/role.py); módulo de application próprio só para a constante · Degrau (C): 1
Base: nota de 2026-11-22 deste ADR, [decision:C] #211-1 › "conjunto aceito declarado no use case (PROVISIONABLE_ROLES)"; .importlinter › identity-facade-only-reach › "allowed_importers = restaurant_hub.features.identity.application.facade"
Verificado: sustenta — evidence-verifier (2026-11-23, 6/6 itens: as duas citações da Base, o import já existente na fachada, a checagem primeira em facade.py, o concept 2.7 D5 e os importadores permitidos do CA14); completude por decision-reviewer (2026-11-23)
Configuração candidata: nenhuma · Reversível: sim
```

O degrau 1 decide porque a casa da constante já foi ratificada na #211, e a fachada já importa
`provision_account.py` (para `ProvisionAccountUseCase`), pela aresta que o contrato
`identity-facade-only-reach` e o CA14 permitem a ela; nenhum import novo entre módulos nasce. Movê-la
para o domínio daria ao `Role` um conhecimento que não é dele: o papel é válido no domínio, é a
entrada que não o aceita (concept 2.7 D5). Nota *append-only*; o corpo acima não foi editado.

**Auditoria do PR #255 — o teste do dublê não via uma cópia com o mesmo nome.**
`test_a_fachada_segue_o_conjunto_do_use_case_e_nao_um_literal` troca o nome nos dois módulos; uma
constante homônima declarada na própria fachada (`PROVISIONABLE_ROLES = frozenset({Role.EMPLOYEE})`
em `facade.py`) também era trocada, e a fachada "seguia" o dublê. Por mutação local, essa segunda
cópia passou as unit de identity e de staff. O terceiro teste,
`test_o_nome_que_a_fachada_le_e_o_objeto_do_use_case`, exige que o nome no namespace de `facade.py`
seja o **mesmo objeto** (`is`) que `provision_account.PROVISIONABLE_ROLES`, e mata essa mutação.
`facade.py` está fora do `only_mutate`; a mutação acima foi feita à mão e não roda de novo quando a
fachada muda. Pôr a fachada no escopo é a issue
[#262](https://github.com/MarceloSanC/restaurant-hub/issues/262).

```
[decision:C] #234-2 — como a fachada lê PROVISIONABLE_ROLES e como o teste trava a cópia única
Escolha: manter `from ...provision_account import PROVISIONABLE_ROLES` na fachada e travar no teste a identidade (`is`) entre o nome no namespace de facade.py e a constante do use case · Alternativas: a fachada ler o atributo do módulo (`provision_account.PROVISIONABLE_ROLES`) e o teste trocar a constante só no módulo de origem · Degrau (C): 5
Base: Python Language Reference 3.12, §7.11 The import statement (forma `from`) "a reference to that value is stored in the local namespace"; mutação local da auditoria do PR #255: a constante homônima em facade.py passou as unit de identity e de staff sem o teste de identidade e reprova com ele
Verificado: sustenta — evidence-verifier (2026-11-23, 4/4 itens: o trecho da referência do Python, o import e a ordem das checagens em facade.py, o dublê nos dois módulos e a asserção de identidade); completude por decision-reviewer (2026-11-23)
Configuração candidata: nenhuma · Reversível: sim
```

As duas formas dão uma fonte só em produção: o `from ... import` guarda uma referência ao objeto
do use case, e o módulo de origem termina de executar antes da fachada ligar o nome, então uma
reatribuição no próprio `provision_account.py` também chega a ela. Elas diferem só no que o teste
consegue ver, e a identidade fecha esse buraco sem mudar `src/` nem a forma de import do resto da
fachada. Degrau 5, a mais simples: os degraus 1 a 4 não discriminam (as duas são fail-closed e
reversíveis).

## Nota — criar `employee` deixa de exigir só `manage_users`

**2026-11-23 — Stage 4.5 ([ADR 4.5.0001](./4_5_0001-scheduling-permissions-in-the-identity-role-map.md)).**
Com `view_own_schedule` no `employee`, `required_permissions_for_role(EMPLOYEE)` passa a
`{manage_users, view_own_schedule}`. O argumento da §Decision 5 (a fachada pode pular a regra porque
`provision_account` só aceita `employee`, que exige só `manage_users`) continua valendo por uma
propriedade, não pela igualdade: todo papel que detém `manage_staff` e `manage_users` — o requisito
da rota R17 — detém também o que o `employee` detém. O pino de igualdade de
`test_http_dependencies.py` virou teste dessa propriedade.

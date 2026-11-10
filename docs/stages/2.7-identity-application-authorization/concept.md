---
title: Concept — Autorização na camada application de identity
description: Os use cases de identity que agem em nome de um ator autenticado passam a autorizar, antes de qualquer outra instrução, o alvo que o próprio command declara — por um port estreito sobre AuthorizeActionUseCase —, o convite de dono pela plataforma ganha use case próprio e a fachada deixa de aceitar papel que não seja employee
when-use: Consultar ao iniciar a Fase 3B desta Stage; antes de acrescentar use case ou command em identity; antes de criar qualquer driver não-HTTP (CLI, worker, seed, console) sobre identity
keywords: [concept, identity-application-authorization, identity, authorization, action-authorizer, fail-closed, defense-in-depth, invite-owner, platform-admin, facade]
status: done
created_at: 2026-11-09
updated_at: 2026-11-09
stage_id: 2.7-identity-application-authorization
stage_title: Autorização na camada application de identity
step_id: 2
step_title: Restaurante e acesso
depends_on: [3.7-application-authorization]
---

# Concept — Stage 2.7 — Autorização na camada application de identity

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e as decisões que o
> [ADR 0.0.0020](../../adr/0_0_0020-identity-use-cases-authorize-their-own-target.md) deixou
> para ela (§Implementation notes). O plano executável fica no [`technical.md`](./technical.md).
>
> **Origem.** Issue [#184](https://github.com/MarceloSanC/restaurant-hub/issues/184), aberta pela
> issue #115, que decidiu a regra no ADR 0.0.0020 com o inventário dos 14 use cases de identity.
> A forma espelha a Stage 3.7 de staff
> ([concept 3.7](../3.7-application-authorization/concept.md), ADR 3.7.0001) e a 4.3 de
> scheduling (ADR 4.3.0002).

## 1. Escopo

### Dentro do escopo
- Os use cases de identity que agem em nome de um ator autenticado — os quatro do inventário
  (`ProvisionRestaurantUseCase`, `CreateUnitUseCase`, `CreateUserUseCase`, `InviteUserUseCase`)
  e o quinto que esta Stage cria (`InviteOwnerUseCase`, D4) — recebem o port `ActionAuthorizer`
  por construtor e abrem `execute` com **uma** chamada que declara o próprio requisito e o passa
  a `AuthorizeActionUseCase`.
- Os cinco commands ganham `actor_id: UserId` como primeiro campo, sem default.
- Port novo `features/identity/application/ports/out/action_authorizer.py`: o Protocol
  `ActionAuthorizer` (o que `AuthorizeActionUseCase` já cumpre) e `required_permissions_for_role`,
  que **desce** de `adapters/inbound/http/dependencies.py` para este módulo.
- Função `authorize_requirement` em `use_cases/authorize_action.py`, ao lado de
  `authorize_at_boundary`: expande o requisito (permissão × unidade, em ordem determinística) e
  passa cada pedido pelas duas traduções de vazamento. `IdentityGuard.authorize_all` passa a
  delegar a ela — **uma** cópia da expansão para a borda e para a application.
- Use case novo `InviteOwnerUseCase` (`use_cases/invite_owner.py`) com `InviteOwnerCommand`: o
  convite de dono pela plataforma (`POST /restaurants/{id}/owners`) deixa de rodar
  `InviteUserUseCase`.
- Consumidores: `composition_root.py` injeta o **mesmo** `AuthorizeActionUseCase` do guard nos
  cinco; `router.py` passa `actor_id` e continua autorizando como hoje.
- `IdentityFacade.provision_account` recusa papel que não seja `employee` (D5) — fecha **na
  fachada** o resíduo que o ADR 0.0.0020 §Inventory deixou para este concept. No
  `ProvisionAccountUseCase` o resíduo continua, guardado por uma varredura nova: os quatro use
  cases facade-only só são importados pela fachada e pelo `composition_root.py` (CA14).
- `required_permissions_for_role` mudando de módulo leva junto o escopo de mutação: o módulo novo
  do port entra em `pyproject.toml` (`only_mutate`) e na lista exata de `test_mutation_scope.py`.
- Suítes novas: propriedade "autorização que nega ⇒ nenhum efeito", requisito exato, forma de
  todo `execute` afetado por AST, totalidade sobre a pasta `use_cases/` com as exclusões
  **nomeadas** do ADR 0.0.0020, mesmo autorizador no grafo e cadeia real por papel — inclusive a
  chamada direta que tenta criar `platform_admin` (§11).
- Documentação que esta Stage torna falsa: notas append-only nos ADRs 2.4.0003, 0.0.0014,
  0.0.0018, 3.5.0001 e 0.0.0020 (este, pela correção de §3 sobre a fachada);
  `docs/domain/identity/tenancy-and-access.md`; e os docstrings listados em CA11 — fachada,
  `get_account_role.py`, `provision_restaurant.py`, `create_user.py`, `invite_user.py`,
  `authorize_action.py` (`authorize_at_boundary`), `router.py` (rota de dono), `dependencies.py`
  e os dois módulos de staff (`identity_gateway.py`, `local_identity_gateway.py`).

### Fora do escopo (explicitamente)
- **Remover a autorização da borda HTTP** — continua, como defesa em profundidade.
- **Mudar faixa HTTP, corpo de erro ou rota.** `tests/e2e/` não muda (CA08).
- **Autorizar dentro da fachada** (ADR 3.5.0001 §1). D5 restringe o **domínio de entrada** da
  fachada; não lhe dá ator nem decisão de acesso.
- **Autenticidade do ator e ator de sistema** (#75) e **validação de identificador fora da borda**
  (#76): o modelo de ameaça é o do ADR 3.7.0001 (§5, último parágrafo).
- **Seed do primeiro `platform_admin`** — raiz de confiança, sem ator que o autorize (ADR
  0.0.0020 §Consequences).
- **Medir sob carga a dupla autorização** (#78).
- **Deduplicar a emissão do token de convite** entre os use cases que convidam (§13).

### Vínculo com o roadmap
Step 2 — Restaurante e acesso. Bloco em [`roadmap.md`](../../roadmap.md) §Stage 2.7. Precede todo
driver não-HTTP de identity e a Stage 3.10, que depende desta pelo inventário de exclusões.

## 2. Objetivo da Stage

Ao fechar, **nenhum use case de identity que age em nome de um ator produz efeito sem que
`AuthorizeActionUseCase` tenha autorizado, para o alvo que o seu command declara, o ator que o
command carrega** — provado sobre a pasta `use_cases/` inteira, com as dez exclusões nomeadas do
ADR 0.0.0020 —, e nenhuma chamada direta a um use case afetado, nem à fachada, cria um
`platform_admin` ou um `owner` fora do tenant do ator. As faixas HTTP ficam byte-idênticas.

## 3. Contexto e premissas

### Contexto
- **Onde identity autoriza hoje** (medido em `develop` c753a52): cada rota autenticada chama
  `guard.authorize`/`guard.authorize_all` e só então o use case (`router.py`); nenhum use case
  recebe ator (ADR 2.4.0003 §1).
- **A brecha é real para quem chama o use case direto.** `CreateUserUseCase.execute` e
  `InviteUserUseCase.execute` tiram o papel do command e aceitam `Role.PLATFORM_ADMIN` com
  `tenant_id=None` (`create_user.py` › `CreateUserUseCase.execute`). A regra "não se concede o que
  não se detém" mora em `dependencies.py` › `required_permissions_for_role`.
- **`InviteUserUseCase` serve dois requisitos** (ADR 0.0.0020 §Inventory): `POST /users/invitations`
  (conjunto composto, tenant do ator) e `POST /restaurants/{id}/owners` (`manage_platform`, papel
  literal `owner`, tenant do path).
- **`AuthorizeActionUseCase` já tem dois consumidores de fora da application** — o `IdentityGuard`
  e a `IdentityAccessFacade` —, os dois por `authorize_at_boundary` (issue #47, ADR 0.0.0016).
- **O resíduo da fachada, medido.** `IdentityFacade.provision_account` recebe `tenant_id: str` (não
  opcional) e o passa como `RestaurantId`; com `role="platform_admin"` o `User` recusa
  (`user.py` › `User.__post_init__`, `PlatformAdminTenantError`). Logo a fachada **não** cria
  `platform_admin` hoje — o ADR 0.0.0020 §Inventory descreve o use case, que aceita
  `tenant_id=None`, não a fachada; ela cria, sim, `owner`, `manager` ou `hr` em qualquer tenant
  existente. O único consumidor (gateway de staff) passa o literal `"employee"`.

### Premissas
- Nenhum driver não-HTTP de identity existe hoje: nenhum use case de identity é construído fora do
  `composition_root.py`.
- O custo extra por requisição é o do ADR 0.0.0020 §Consequences (leituras por chave em rotas
  administrativas). Aceito, não medido (#78).

### Dependências
- `3.7-application-authorization` (forma de referência; `done`).
- `2.2`/`2.4`: `AuthorizeActionUseCase`, `authorize_at_boundary`, `IdentityGuard`.
- `2.6`: unidade de trabalho de identity (o `InviteOwnerUseCase` escreve duas vezes).
- Issue #170 (fechada): `_invitation.deliver_invitation`, que o novo use case reusa.

## 4. Contratos

### Introduzidos
- **Port `ActionAuthorizer`** (`port-out`, `application/ports/out/action_authorizer.py`):
  ```python
  class ActionAuthorizer(Protocol):
      def execute(self, command: AuthorizeActionCommand) -> AuthorizedActor: ...
  ```
  `AuthorizeActionUseCase` o cumpre estruturalmente; nenhum adapter novo.
- **`required_permissions_for_role(target_role: Role) -> frozenset[Permission]`** no mesmo módulo
  (mesma assinatura e corpo de hoje; `dependencies.py` passa a importá-la).
- **`authorize_requirement`** (`use_cases/authorize_action.py`):
  ```python
  def authorize_requirement(
      authorizer: ActionAuthorizer,
      actor_id: UserId,
      permissions: frozenset[Permission],
      *,
      tenant_id: RestaurantId | None,
      unit_ids: Sequence[UnitId] = (),
  ) -> AuthorizedActor: ...
  ```
  Um pedido por `(permissão, unidade)`, permissões em `sorted` por fora, unidades por dentro na
  ordem dada, **sem deduplicar** (como a borda faz hoje); sem unidade, um pedido com
  `unit_id=None` por permissão. Cada pedido passa por
  `authorize_at_boundary` (que passa a aceitar `ActionAuthorizer`). Devolve o primeiro
  `AuthorizedActor`.
- **Campo `actor_id: UserId`**, primeiro, sem default, em `ProvisionRestaurantCommand`,
  `CreateUnitCommand`, `CreateUserCommand`, `InviteUserCommand` e `InviteOwnerCommand`.
- **Parâmetro `authorizer: ActionAuthorizer`**, último do construtor, nos cinco use cases.
- **`InviteOwnerUseCase` / `InviteOwnerCommand(actor_id, email, tenant_id: RestaurantId)`** —
  result `UserResult`; sem `role` (literal `Role.OWNER` dentro), sem `unit_ids`. Depois da
  autorização, a mesma sequência que `InviteUserUseCase` percorre hoje com `role=OWNER` e sem
  unidades: unicidade global do e-mail (`EmailAlreadyRegisteredError`), restaurante existente
  (`RestaurantNotFoundError`), construção do `User`, unidade de trabalho (`users.add` + token),
  envio por `deliver_invitation` (`InvitationNotSentError`).
- **`RoleNotProvisionableError(IdentityApplicationError)`** (`application/errors.py`) — papel
  conhecido que a fachada não provisiona (D5); mapeado a 422 no adapter HTTP de identity, como o
  `InvalidRoleError`, embora nenhuma rota o alcance.

### Modificados
- `IdentityFacade.provision_account`: papel conhecido diferente de `"employee"` levanta
  `RoleNotProvisionableError` antes de qualquer porta e antes da conversão do e-mail (D5); papel
  desconhecido segue com `InvalidRoleError`. Assinatura inalterada.
- `IdentityGuard.authorize_all`: mesma assinatura e mesmas chamadas, agora por
  `authorize_requirement`.

### Consumidos
- `AuthorizeActionUseCase` (2.2) e `authorize_at_boundary` (ADR 0.0.0016) — a decisão não muda.
- `_invitation.deliver_invitation`/`invitation_message`/`setup_link` (issue #170).

## 5. Invariantes e regras

**R1 — Quem age por um ator autoriza.** Os cinco use cases da matriz de R3. Os demais use cases de
`use_cases/` só ficam fora por uma entrada **nomeada**, com motivo, na tabela de exclusões (a do
ADR 0.0.0020 §Inventory): `authenticate_user`, `refresh_session`, `revoke_session`,
`request_password_reset`, `set_password_with_token` (a credencial é a autoridade),
`authorize_action` (é a decisão), `provision_account`, `send_invitation`, `revoke_all_sessions`,
`get_account_role` (só a fachada os chama; o consumidor autoriza — ADR 3.5.0001 §1). Módulo
novo na pasta entra numa das duas listas ou a suíte reprova.

**R2 — A autorização é a primeira instrução de `execute`.** Descontado o docstring, a primeira
instrução é **uma** chamada `authorize_requirement(self._authorizer, <p>.actor_id, <permissões>,
tenant_id=…[, unit_ids=…])`, sem nenhuma condição, leitura, geração de id ou checagem pura antes, e
sem outra chamada a `authorize_requirement` ou a `self._authorizer` no corpo. A ordem de checagens
que os ADRs 0.0.0014 §1, 0.0.0018 §2 e o concept 2.2 §5.7 fixam (nome, depois unicidade global do
e-mail, depois o resto) vale **depois** dela, inalterada.

**R3 — O requisito é o do command, por inteiro** (igual ao que a borda declara hoje):

| Use case | Permissões | `tenant_id` | `unit_ids` |
|---|---|---|---|
| `provision_restaurant` | `{MANAGE_PLATFORM}` | `None` (o tenant nasce junto) | — |
| `create_unit` | `{MANAGE_TENANT}` | `command.restaurant_id` | — |
| `create_user` | `required_permissions_for_role(command.role)` | `command.tenant_id` | `command.unit_ids` |
| `invite_user` | `required_permissions_for_role(command.role)` | `command.tenant_id` | `command.unit_ids` |
| `invite_owner` | `{MANAGE_PLATFORM}` | `command.tenant_id` | — |

O tenant é **confirmado**, não derivado (ADR 0.0.0005 cl. 1; ADR 3.7.0001 §3). Em `invite_owner`
a borda omite o tenant e o use case o nomeia: para `platform_admin` o passo 3 de
`AuthorizeActionUseCase` não se aplica, e para qualquer outro papel o passo 2 (RBAC) nega antes —
mesma resposta nos dois lugares.

**R4 — O `AuthorizedActor` devolvido não é lido pelos use cases.** O use case opera sobre o
command.

**R5 — As recusas saem pelas traduções de `authorize_at_boundary`.** Ator inexistente →
`InvalidAccessTokenError`; unidade inexistente → `UnitNotVisibleError`; toda outra exceção sobe
crua. O use case não captura nada.

**R6 — Sem ator, sem command.** `actor_id` é obrigatório; quem não o informa recebe `TypeError` na
construção. Não é `repr=False`: é identificador, não credencial, e já é o que o log de 401/403
registra (issue #26).

**R7 — A borda continua igual.** Mesmas chamadas ao guard, na mesma ordem, antes do use case; o
router passa `actor_id=actor.claims.subject`.

**R8 — Nenhum caminho direto emite `platform_admin` nem `owner` fora do tenant do ator.** Pelos
cinco use cases, porque nenhum papel detém `manage_users` **e** `manage_platform` (ADR 2.4.0003
§2b), agora dentro do requisito do use case; pela fachada, porque ela só aceita `employee` (D5).
Os dois únicos emissores de `owner` sem `manage_tenant` continuam sendo os dois de plataforma
(`provision_restaurant`, `invite_owner`), com papel literal e `manage_platform` exigido.

**Modelo de ameaça (ADR 3.7.0001 §Threat model).** R1–R8 garantem "autorizado", não "autêntico":
um driver em processo que forje o `actor_id` de um `platform_admin` passa. Fica com #75.

## 6. Casos de erro e exceções

| Situação | Comportamento |
|---|---|
| Autorizador nega (qualquer pedido do requisito) | a exceção sobe (R5); nenhuma chamada a repositório, hasher, emissor de token, gerador de id, relógio, unidade de trabalho ou `EmailSender` |
| `actor_id` inexistente | `InvalidAccessTokenError` (R5); nenhum efeito |
| Unidade pedida inexistente, chamada direta, por ator que passa o RBAC | `UnitNotVisibleError` (R5) — antes, `UnitNotFoundError` do use case |
| `IdentityFacade.provision_account` com papel conhecido ≠ `employee` (inclusive com e-mail inválido) | `RoleNotProvisionableError`, antes de qualquer porta |
| `invite_owner` em restaurante inexistente, por `platform_admin` | `RestaurantNotFoundError` (404, igual a hoje) |
| Via HTTP, qualquer caso | status e corpo **inalterados**: a borda autoriza o mesmo requisito antes |

**Matriz da cadeia real (CA06)** — ator de A (ou `platform_admin`), command endereçado ao tenant
B, sem unidades. Deriva da ordem dos passos de `AuthorizeActionUseCase` (ator, RBAC, tenant,
exigência de unidade, visibilidade) e de `sorted` sobre os valores de `Permission`
(`manage_job_functions` < `manage_platform` < `manage_staff` < `manage_tenant` < `manage_users`):
o primeiro pedido que falha decide.

| Use case (alvo) | `owner` A | `manager` A | `hr` A | `employee` A | `platform_admin` |
|---|---|---|---|---|---|
| `provision_restaurant` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | concede (controle) |
| `invite_owner` (B) | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | concede (controle) |
| `create_unit` (B) | `TenantNotVisibleError` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` |
| `create_user`/`invite_user`, `role=owner`, tenant B | `TenantNotVisibleError` | `TenantNotVisibleError` | `TenantNotVisibleError` | `PermissionDeniedError` | `PermissionDeniedError` |
| `create_user`/`invite_user`, `role=platform_admin`, `tenant_id=None` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` | `PermissionDeniedError` |

`manager`/`hr` de A recebem `TenantNotVisibleError` ao criar `owner` em B porque detêm
`manage_job_functions`, o primeiro pedido em ordem, e caem no passo 3. Controles positivos: o
`owner` de B cria unidade e usuário (`owner`) em B; o `manager` de A cria `employee` em A numa
unidade de que é membro; o `platform_admin` provisiona restaurante e convida dono em B.

Uma exceção nova (`RoleNotProvisionableError`, D5), com entrada no mapa de status de identity;
nenhuma faixa existente muda.

## 7. Decisões técnicas relevantes

> Triagem pela skill `evidence-resolution`: D1–D4 são **C** (organização interna, sem efeito
> visível ao usuário) e D5 é **P** (o que a fachada passa a aceitar é capacidade de produto que
> staff consome), delegado pelo sponsor. A base é o próprio projeto; nenhuma fonte externa.
> ADR desta Stage: [2.7.0001](../../adr/2_7_0001-identity-authorizes-through-a-narrow-port.md).

### D1 — O ator é `actor_id: UserId`
```
[decision:C] 2.7-D1 — tipo do ator no command de identity
Escolha: actor_id: UserId · Alternativas: Actor = object opaco (staff); AccessPrincipal da fachada (user_id + tenant_id); dataclass nova Actor · Degrau (C): 1
Base: commands.py › AuthorizeActionCommand ("actor_id: UserId") — identity já nomeia o ator assim na própria application; ADR 0.0.0020 §Decision 2 (não o AuthenticatedActor do HTTP)
Verificado: ver §7 do technical (evidence-verifier, Checkpoint A)
Configuração candidata: nenhuma · Reversível: sim (DTO interno)
```
Staff usa `object` porque não pode nomear tipo de identity; identity pode. `AccessPrincipal` traria
o tenant do ator, convite a derivar o tenant em vez de confirmá-lo (R3).

### D2 — Port estreito `ActionAuthorizer`, cumprido por `AuthorizeActionUseCase`
```
[decision:C] 2.7-D2 — dependência dos use cases: port estreito × AuthorizeActionUseCase direto
Escolha: Protocol ActionAuthorizer em application/ports/out/ · Alternativas: depender da classe AuthorizeActionUseCase · Degrau (C): 1
Base: ADR 0.0.0020 §Decision 5 "LAYOUT §5 has the use case depend on an interface … A direct dependency has to justify the deviation"; LAYOUT §5 "O use case depende da interface, não da implementação concreta"
Verificado: ver §7 do technical (evidence-verifier, Checkpoint A)
Configuração candidata: nenhuma · Reversível: sim
```
**Divergência declarada do LAYOUT §5:** o port é de saída e quem o cumpre não é um adapter, é um
use case do próprio BC. Não há adapter a escrever porque a decisão é de identity (ADR 0.0.0020
§Decision 5); o port existe para que o use case dependa de interface e para que o teste negue com
um dublê.

### D3 — As traduções de vazamento valem dentro do use case, numa cópia só
```
[decision:C] 2.7-D3 — authorize_at_boundary dentro do use case × execute cru
Escolha: authorize_requirement, que passa cada pedido por authorize_at_boundary; IdentityGuard.authorize_all delega a ela · Alternativas: chamar execute cru (as recusas viram UserNotFoundError/UnitNotFoundError); traduzir só na borda · Degrau (C): 2
Base: ADR 0.0.0016 §Decision 2 (uma cópia de cada regra de vazamento); ADR 2.4.0001 §5 (fechamento do oráculo de enumeração); ADR 2.2.0002 (fail-closed)
Verificado: ver §7 do technical (evidence-verifier, Checkpoint A)
Configuração candidata: nenhuma · Reversível: sim
```
Com a tradução, o use case responde ao driver o mesmo que a borda responderia: se um dia a borda
deixar de autorizar uma rota, o 404 de unidade inexistente não reabre o oráculo. Pelo HTTP é
inobservável (a borda nega antes). A expansão permissão × unidade, que hoje mora só em
`IdentityGuard.authorize_all`, passa a ter uma casa — a borda e os use cases chamam a mesma função.
O docstring de `authorize_at_boundary` ("para um chamador de fora de identity") é reescrito: o
chamador passa a ser quem age por um ator, de fora ou de dentro.

### D4 — O convite de dono é um use case próprio
```
[decision:C] 2.7-D4 — entrada do convite de dono pela plataforma
Escolha: InviteOwnerUseCase + InviteOwnerCommand · Alternativas: InviteUserUseCase aceitando dois commands e escolhendo o requisito pelo tipo do command · Degrau (C): 1 e 5
Base: LAYOUT §7 "Um use case por arquivo"; LAYOUT §5 / ADR 0.0.0006 (execute(<Command>)); ADR 0.0.0020 §Inventory "A separate use case and a separate command are both acceptable"
Verificado: ver §7 do technical (evidence-verifier, Checkpoint A)
Configuração candidata: nenhuma · Reversível: sim
```
Com dois commands, `execute` teria um requisito por tipo, e a forma "primeira instrução = uma
chamada" (R2) viraria um despacho condicional — justamente o que a varredura AST recusa. O custo é
uma quinta cópia do passo de emitir o token de convite, que o ADR 0.0.0018 já declarou para as
quatro anteriores (§13).

### D5 — A fachada só provisiona `employee`
```
[decision] P delegado — fechar o resíduo: IdentityFacade.provision_account recusa papel ≠ "employee" (Recomendada); alternativa: reafirmar o resíduo e deixá-lo à disciplina do gateway, motivo: é o fechamento que o próprio ADR 0.0.0020 §Inventory aponta como o mais barato que mantém a fachada sem autorização; o único consumidor já passa "employee"; sem ele, a fachada continuaria criando owner/manager/hr em qualquer tenant (§3), e o critério do sponsor (esqueleto escalável, não o atalho que exige refazer) pede a regra na fachada, não no chamador.
```
- **Onde:** na fachada, onde o papel chega como texto e a fachada decide o que serve — não em
  `ProvisionAccountUseCase`, cujo command é de identity e serve qualquer papel. **O resíduo do use
  case continua** e é declarado (§13, ADR 2.7.0001 §Consequences): o que deixa de ser disciplina
  é o alcance — CA14 trava que os quatro use cases facade-only só são importados, em `src/`, pela
  fachada e pelo `composition_root.py`.
- **Ordem:** a checagem do papel é a primeira instrução de `provision_account`, antes da
  conversão do e-mail.
- **Erro:** `RoleNotProvisionableError`, na raiz de **aplicação** (ADR 3.9.0001): o papel é
  válido no domínio; é a entrada da fachada que não o aceita. Reusar `InvalidRoleError` (domínio,
  "papel desconhecido") mudaria o significado dele. Mapeado a 422 por coerência com o
  `InvalidRoleError`; staff não o traduz e nenhum caminho HTTP o alcança, porque o gateway passa
  `"employee"`.
- **Reverso:** um consumidor futuro que precise de outro papel pela fachada reclassifica esta
  entrada e o ADR 0.0.0020 §Inventory.

### D6 — A borda continua autorizando
R7. ADR 0.0.0020 §Decision 4; ADR 3.7.0001 §6.

Os ramos `is_platform_admin` de `create_user`/`invite_user` (rejeição de `platform_admin` com
unidades antes do `UnitRepository`) ficam: com o requisito dentro do use case, nenhum ator real os
alcança — nenhum papel detém `manage_users` e `manage_platform` —, mas eles são a ordem de
checagem do concept 2.2 §5.7 e continuam alcançáveis com o autorizador dublê. Removê-los mudaria
a regra de um use case por um efeito de outro mecanismo; ficam como defesa em profundidade,
declarada no docstring.

### D7 — Dublês do autorizador
- `DenyingActionAuthorizer` — levanta **a mesma instância** sentinela e registra o command.
- `RecordingActionAuthorizer` — registra cada `AuthorizeActionCommand` e devolve um
  `AuthorizedActor` **infiel** (ator, tenant e unidade que nenhum teste semeia; R4).
- Os dois em `tests/fakes/features/identity/stub_action_authorizers.py`, declarados dublês (não
  implementações do port), como `stub_access_guards.py` de staff.
- Um espião de port genérico (registra toda chamada de método) mede "nenhum efeito" (CA03) sem
  depender de contadores que cada fake tem ou não tem.

## 8. Integrações

### Internas
- **`composition_root.py`**: `authorizer=authorize_action` nos cinco — a mesma instância de
  `IdentityGuard` e de `IdentityAccessFacade`; `identity_invite_owner` novo no contêiner.
- **`router.py`**: `actor_id=actor.claims.subject` nos cinco commands; a rota de dono passa a
  `_get_invite_owner`/`InviteOwnerUseCase`.
- **staff**: só docstrings (`identity_gateway.py`, `local_identity_gateway.py`); o gateway já
  passa `"employee"`.

### Externas
- Nenhuma.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Use case novo de identity entra sem autorizar | M | A | CA01 (pasta = afetados ∪ exclusões nomeadas) |
| Autorização condicional ou depois de checagem | M | A | CA05 (forma AST de todo `execute` afetado) |
| Requisito errado (permissão, tenant, unidade) | M | A | CA04 contra uma transcrição literal de R3, independente do código |
| `InviteUserUseCase` passa a negar a rota de dono antes de o dono ter entrada própria | A | A | ordem das Tasks: `InviteOwnerUseCase` antes da adoção em `invite_user` |
| Faixa HTTP muda | B | A | CA08 (`tests/e2e/` intocado e verde no CI) |
| Duas cópias da expansão permissão × unidade divergem | B | A | D3 — uma função; CA09 |
| Autorizador diferente no grafo | B | A | CA07 (identidade de objeto) |

## 11. Critérios de aceitação

- [ ] **CA01** — **Totalidade:** o conjunto de módulos de `use_cases/` (sem `_`-prefixados) é
      exatamente a união disjunta dos cinco afetados de R3 e das dez exclusões nomeadas de R1; cada
      exclusão tem motivo escrito na suíte. Todo afetado tem no construtor `authorizer` anotado
      `ActionAuthorizer`; nenhuma exclusão o tem.
- [ ] **CA02** — Os cinco commands têm `actor_id` como **primeiro** campo, sem default; construir
      sem ele dá `TypeError`.
- [ ] **CA03** — Com o autorizador que nega, cada afetado, chamado com command válido sobre dados
      semeados, levanta **a própria** sentinela (`is`) e não faz nenhuma chamada a nenhum outro port
      (repositórios, hasher, emissor de token, gerador de id, relógio, unidade de trabalho,
      `EmailSender`), medido por espião. O conjunto espionado é **igual** ao dos parâmetros do
      construtor menos `authorizer` e os escalares (`invitation_ttl`, `base_url`) — conferido por
      `inspect.signature`; a sentinela não é `UserNotFoundError`/`UnitNotFoundError`.
- [ ] **CA04** — **Requisito exato:** num caminho feliz com o autorizador que registra, a sequência
      de `AuthorizeActionCommand` é exatamente a de R3 (permissões em `sorted`, × unidades na ordem
      do command), com `actor_id` do command — conferida contra uma transcrição literal de R3 na
      suíte, não contra a tabela de cenários. Inclui um cenário discriminante: `create_user` com
      `role=owner` e `unit_ids=(U2, U1, U2)` produz 12 pedidos nessa ordem, sem deduplicar.
- [ ] **CA05** — **Forma:** por AST, em cada afetado, descontado o docstring, a primeira instrução de
      `execute` é a chamada de R2 com os argumentos de R3, e não há outra chamada a
      `authorize_requirement` nem a `self._authorizer` no corpo.
- [ ] **CA06** — **Cadeia real por papel** (`AuthorizeActionUseCase` sobre repositórios em memória,
      tenants A e B): cada célula da **matriz da cadeia real** de §6 — afetado × papel do ator,
      com o papel alvo `owner` em tenant B e a chamada direta com `role=platform_admin` — dá o
      tipo exato da célula e nenhum efeito; os controles positivos de §6 passam.
- [ ] **CA07** — No grafo de `wire_dependencies`, os cinco afetados têm `_authorizer is
      deps.identity_authorize_action`, a mesma instância do guard.
- [ ] **CA08** — Faixas HTTP inalteradas: `git diff origin/develop -- tests/e2e` vazio e a suíte e2e
      verde no CI.
- [ ] **CA09** — `required_permissions_for_role` é **definida** só em
      `application/ports/out/action_authorizer.py`; `dependencies.py` a importa de lá e
      `IdentityGuard.authorize_all` delega a `authorize_requirement` (sem laço próprio) — por AST.
- [ ] **CA10** — `IdentityFacade.provision_account` com `owner`, `manager`, `hr` e
      `platform_admin` levanta `RoleNotProvisionableError` sem efeito, inclusive com e-mail
      inválido; papel desconhecido segue `InvalidRoleError`; com `employee`, segue igual.
- [ ] **CA11** — As frases que esta Stage torna falsas deixam de existir (`git grep -F` vazio
      para cada uma, no arquivo indicado):
      `facade.py` › "Se identity deve seguir staff é decisão aberta";
      `get_account_role.py` › "se isso muda é a issue #115";
      `provision_restaurant.py` › "A autorização fica na borda";
      `create_user.py` › "acontece **antes** de qualquer consulta ao `UnitRepository`" (reescrita
      para dizer que a autorização vem antes e essa ordem vale depois dela);
      `authorize_action.py` › "Autoriza para um chamador **de fora** de identity";
      `router.py` › "a rota roda o" (docstring da rota de dono);
      `dependencies.py` › "seria alcançado com unidades não-visíveis";
      `identity_gateway.py` e `local_identity_gateway.py` › "identity não autoriza na application";
      `tenancy-and-access.md` › "decisão aberta para o BC inteiro". Os ADRs 2.4.0003, 0.0.0014,
      0.0.0018, 3.5.0001 e 0.0.0020 ganham nota datada append-only.
- [ ] **CA12** — Recusa traduzida (R5): pela cadeia real, `actor_id` inexistente →
      `InvalidAccessTokenError` e unidade inexistente → `UnitNotVisibleError`, sem efeito.
- [ ] **CA13** — `make check` verde no CI do PR; cobertura ≥ 90% por arquivo de `src/` tocado.
- [ ] **CA14** — Os módulos facade-only (`provision_account`, `send_invitation`,
      `revoke_all_sessions`, `get_account_role`) só são importados, em `src/`, por
      `features/identity/application/facade.py` e `composition_root.py` (varredura AST).
- [ ] **CA15** — Paridade do convite de dono: `InviteOwnerUseCase` produz o mesmo efeito, o mesmo
      result e as mesmas exceções que `InviteUserUseCase` com `role=OWNER` e sem unidades, inclusive
      na combinação e-mail repetido + restaurante inexistente (`EmailAlreadyRegisteredError`) e na
      falha de envio (`InvitationNotSentError`, conta e token comitados).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido? (não há)
- [x] Decisões com alternativa real descartada têm ADR escrito? (2.7.0001)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.7; #170 fechada)
- [x] Stage cabe em ~3–12 Tasks? (9 previstas)
- [x] Riscos críticos têm mitigação plausível?
- [x] Nenhum critério depende de mudar faixa HTTP?

## 13. Questões em aberto

Nenhuma bloqueante. Ficam como `[finding]` na §7 do technical:

- **O resíduo de `ProvisionAccountUseCase`**: chamado direto, ainda cria `platform_admin` ou
  `owner` em qualquer tenant. Guardado por CA14 (só a fachada o alcança), não pela regra; o
  primeiro chamador novo reabre a decisão (ADR 0.0.0020 §Inventory).
- **Cinco cópias da emissão do token de convite** (`invite_user`, `invite_owner`,
  `provision_restaurant`, `provision_account`, `request_password_reset`). Extrair exige não
  esconder a escrita da regra 10 do `check_layout` (que conta escrita por atributo de
  repositório). Candidata: issue nova.
- **#75 e #76 alargadas a identity** (ADR 0.0.0020 §Consequences): continua pendente registrar
  nas duas; não é desta Stage editá-las.

## 14. Referências

- [`../../roadmap.md`](../../roadmap.md) — Stage `2.7-identity-application-authorization`
- Issues #184, #115; ADR desta Stage: [2.7.0001](../../adr/2_7_0001-identity-authorizes-through-a-narrow-port.md)
- ADRs consumidos: [0.0.0020](../../adr/0_0_0020-identity-use-cases-authorize-their-own-target.md),
  3.7.0001, 4.3.0002, 2.4.0003, 2.4.0001, 2.2.0002, 0.0.0005, 0.0.0006, 0.0.0014, 0.0.0016,
  0.0.0018, 3.5.0001
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §5, §7
- Concept de referência: [`3.7`](../3.7-application-authorization/concept.md)

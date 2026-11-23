---
title: Concept — Gestão do vínculo de login do registro
description: Definição do que será feito nesta Stage e por quê, com decisões técnicas relevantes
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, login-link-management, vinculo, login, desvincular, trocar, conta-existente, staff, identity]
status: done
created_at: 2026-11-22
updated_at: 2026-11-22
stage_id: 3.10-login-link-management
stage_title: Gestão do vínculo de login do registro
step_id: 3
step_title: Equipe da unidade
depends_on: [3.8-termination-access-scope, 2.7-identity-application-authorization]
---

# Concept — Stage 3.10 — Gestão do vínculo de login do registro

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Forks P delegados.** O sponsor delegou as bifurcações de produto desta Stage à
> opção recomendada (despacho da orquestração de 2026-11-22, critério de desempate:
> esqueleto escalável com implementação mínima). Cada uma está em §7 como
> `[decision] P delegado — <opção>, motivo` e nos ADRs 3.10.0001 e 3.10.0002. As
> disposições do Checkpoint A estão em §13.

## 1. Escopo

### Dentro do escopo
- **Três transições novas do vínculo de login de um registro**, cada uma um use case
  de staff com rota própria:
  - **R18 — vincular conta existente**: liga ao registro sem login uma conta que já
    existe no restaurante, nomeada pelo e-mail;
  - **R19 — trocar o login**: substitui o login vinculado por outra conta existente,
    numa escrita só;
  - **R20 — desvincular**: retira o vínculo do registro.
- **Ponto único da regra de fim de vínculo** (ADR 3.8.0001 decisão 5), extraído de
  `deactivate_employee.py` para um módulo auxiliar de `use_cases/`; R13, R19 e R20
  passam por ele. A regra 10 de `scripts/check_layout.py` (ADR 2.6.0002 §5) passa a
  enxergar a revogação feita pelo auxiliar.
- **Escritas condicionais no `EmployeeRepository`**, na forma de `link_login`
  (ADR 0.0.0010): `unlink_login` (L-UNLINK), `relink_login` (L-RELINK) e
  `deactivate` (L-DEACT), todas condicionadas ao estado do vínculo que o use case
  leu (login e, onde decide a revogação, o estado ativo).
- **R13 passa a gravar o desligamento pela escrita condicional**, o que fecha o
  entrelace "desligamento × vínculo na ordem inversa" (ADR 0.0.0010 › "The reverse
  order of the termination race is not closed").
- **Um login por unidade:** vincular e trocar recusam a conta que já está em outro
  registro da mesma unidade (workforce §3.1 › "um por unidade").
- **Identity — consulta somente leitura atrás da fachada:** use case facade-only
  `FindAccountByEmailUseCase` e `IdentityFacade.find_account_by_email`, que devolvem
  id, tenant, unidades e se a conta alcança todas as unidades do tenant. Entra no
  inventário facade-only da 2.7 (ADR 0.0.0020 › "A new consumer of any facade-only
  use case has to be classified").
- **Lei nova do `IdentityGateway`**: `find_login_by_email` (L-IG6), com contrato
  fake ≡ real.
- **HTTP**: três rotas no router de staff, um schema de request, quatro entradas novas
  no mapa de status de staff.
- **Testes**: unit com fakes, contrato fake ≡ Postgres das três leis novas do
  repositório, contrato fake ≡ real da L-IG6, conduta com duas conexões para os
  entrelaces de escrita do vínculo, e2e contra Postgres.
- **Docs**: nota datada em `docs/domain/staff/workforce.md` §3.8; notas
  *append-only* nos ADRs 3.5.0002, 3.5.0004, 3.8.0001, 0.0.0010 e 2.6.0002.

### Fora do escopo (explicitamente)
- Criar login novo (R17, Stage 3.5) e reemitir o link de definição de senha.
- Desativar conta (`User.is_active`) e mudar o papel de uma conta.
- Criar ou remover *membership* de unidade em identity (§5 R4).
- "Minha escala" e qualquer superfície de scheduling (4.5).
- Unit of Work entre staff e identity, e Unit of Work em staff (ADR 2.6.0002 §2).
- Escrita própria da coluna `active` (`update` segue gravando o estado — §6.1).
- Completar perfil no primeiro acesso.

### Divergência declarada em relação ao PIPELINE
- **PIPELINE §4.2 #4 (entrega num único BC):** a Stage entrega em staff **e** em
  identity (um use case de leitura e um método da fachada), como a 3.5 e a 3.8. A
  parte de identity é a consulta que só staff consome e não tem superfície própria;
  partir a Stage criaria uma consulta sem consumidor (PIPELINE §4.2 #3). Já
  declarada no bloco do roadmap.

### Vínculo com o roadmap
Step 3 — Equipe da unidade. Bloco `roadmap.md` §Stage 3.10 (issue #218, nascida da
#107): o finding do concept 3.5 §10 ("Vincular login existente e desvincular/trocar
login de um registro"), os dois findings de staff do technical 3.8 §7 e o anexo da
auditoria do PR #103 (comentário na #107). A 4.5 depende desta Stage.

## 2. Objetivo da Stage

Ao fechar a Stage, o gerente vincula a um registro a conta que a pessoa já tem no
restaurante (o gerente ou dono que também trabalha na escala), troca um login
vinculado por engano e desvincula um registro, sempre dentro do restaurante e da
unidade do registro; toda transição que encerra um vínculo ativo corta o acesso pela
mesma regra do desligamento, e nenhuma escrita do vínculo ou do desligamento decide
sobre um estado que mudou depois da leitura.

## 3. Contexto e premissas

### Contexto
- **O vínculo hoje só nasce por R17**, que sempre cria conta nova com papel
  `employee` (ADR 3.5.0002). Quem já tem conta (gerente, dono) recebe 409
  (`LoginEmailAlreadyInUseError`) e não alcança "minha escala"
  (concept 3.5 §10).
- **Recuperação ausente** (concept 3.5 §6.4): conta órfã depois de falha de staff,
  e-mail digitado errado, registro vinculado por engano que R15 não remove
  (ADR 0.0.0013).
- **A regra de fim de vínculo é de "o vínculo ativo de um registro termina"**, não
  só de R13 (ADR 3.8.0001 decisão 5); hoje mora inline em `deactivate_employee.py`
  (`_grants_the_login_access`).
- **O vínculo tem escrita própria e condicional** (`link_login`, L-LINK,
  ADR 0.0.0010 decisões 1–3): trava a linha, reaplica as guardas do domínio sobre o
  gravado e grava só `user_id`; `update` ignora o `user_id` da entidade.
- **Entrelace na ordem inversa** (ADR 0.0.0010 §Negative; anexo na #107): um R13 que
  leu o registro sem vínculo e grava depois de um R17 deixa o registro desligado e
  vinculado, sem revogar nada.
- **A corrida de dois desligamentos do mesmo login na mesma unidade** (ADR 3.8.0001
  `### Negative`) tem como dona "the Stage that implements 'link an existing login'".
- **O ator vai no command e o use case autoriza o próprio alvo** (ADR 3.7.0001); R17
  autoriza `manage_staff` e depois `manage_users` sobre a unidade.
- **A fachada não autoriza** (ADR 3.5.0001 §1); use case que só ela chama é exclusão
  nomeada do inventário (ADR 0.0.0020; teste
  `tests/unit/features/identity/application/test_use_cases_authorize.py` ›
  `_EXCLUSOES` e `_FACADE_ONLY`).
- **Regra 10 de `check_layout.py`** (ADR 2.6.0002 §5): use case com duas escritas fora
  de unidade de trabalho reprova, salvo entrada nomeada em `MULTI_WRITE_ALLOWLIST`
  (hoje `CreateLoginForEmployeeUseCase` e `DeactivateEmployeeUseCase`). O varredor
  só enxerga escrita feita por `self.<atributo>.<método>`.

### Premissas
- `User.tenant_id` é `None` **só** para `platform_admin`, que não tem membership
  (ADR 2.1.0002; `user.py` › `User`; `PlatformAdminMembershipError`).
- **O dono nasce sem membership** (`provision_restaurant.py` e `invite_owner.py`
  gravam o dono com nenhuma unidade) e enxerga todas as unidades do tenant pelo
  *bypass* de escopo (`user.py` › `bypasses_unit_scope`, `can_view_unit`).
- O e-mail de conta é único na plataforma (`uq_users_email`; kickoff #2).
- `manage_staff` e `manage_users` são detidas por `owner`, `manager` e `hr`
  (`role.py` › `_ROLE_PERMISSIONS`); `employee` não detém nenhuma.
- Nenhuma rota de identity lista contas. `EmployeeResponse` mostra o `user_id` de
  registros já vinculados, mas não há como obter o id de uma conta sem registro.
- `UserRepository.list_memberships` "não precisa filtrar" por usuário (docstring do
  port, decisão 3): quem casa usuário e unidade é o consumidor.

### Dependências
- `3.8-termination-access-scope`: regra de fim de vínculo e L-IG5.
- `2.7-identity-application-authorization`: inventário facade-only como propriedade.
- `3.7-application-authorization` (transitiva): `AccessGuard` e ator no command.
- `3.11-job-function-unit-enablement` (mergeada): referência de forma recente.

## 4. Contratos

### Introduzidos

**Domínio de staff** (`features/staff/domain/`)
- `Employee.assert_link_state(user_id: UserId | None, *, was_active: bool) -> None` —
  vínculo gravado diferente de `user_id` ⇒ `EmployeeLoginChangedError`; registro lido
  desligado (`was_active=False`) e gravado ativo (recontratado no meio) ⇒
  `EmployeeLoginChangedError`. Lido ativo e gravado desligado **não** recusa: quem
  desligou no meio já passou pela regra de fim de vínculo.
- `Employee.unlink_login(expected: UserId, *, was_active: bool) -> Employee` — sem
  vínculo ⇒ `EmployeeHasNoLoginError`; depois `assert_link_state(expected,
  was_active=was_active)`; devolve o registro com `user_id=None`. Vale para registro
  desligado.
- `Employee.deactivate_as_read(expected: UserId | None, *, was_active: bool) ->
  Employee` — `assert_link_state(expected, was_active=was_active)`, depois
  `deactivate()` (idempotente no valor).
- `Employee.relink_login(expected: UserId, user_id: UserId) -> Employee` — sem
  vínculo ⇒ `EmployeeHasNoLoginError`; desligado ⇒ `TerminatedEmployeeLoginError`;
  vínculo diferente de `expected` ⇒ `EmployeeLoginChangedError`; devolve o registro
  com o login novo. Precedência na ordem listada.
- Erros de domínio (`StaffError`), 409: `EmployeeHasNoLoginError(employee_id)`;
  `EmployeeLoginChangedError(employee_id)`.

**Port `EmployeeRepository`** (`port-out`), endereço de três partes, todas
"trava a linha, reaplica a guarda do domínio no gravado, grava uma coluna"
(ADR 0.0.0010 decisão 2):
```python
def unlink_login(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId,
                 *, expected_user_id: UserId, expected_active: bool) -> None: ...   # L-UNLINK
def relink_login(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId,
                 *, expected_user_id: UserId, user_id: UserId) -> None: ...          # L-RELINK
def deactivate(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId,
               *, expected_user_id: UserId | None, expected_active: bool) -> None: ...  # L-DEACT
```
- **L-UNLINK:** inexistente no endereço ⇒ `EmployeeNotFoundError`; depois
  `Employee.unlink_login(expected_user_id, was_active=expected_active)` sobre o
  gravado; grava só `user_id = NULL`.
- **L-RELINK:** inexistente ⇒ `EmployeeNotFoundError`; depois
  `Employee.relink_login(expected_user_id, user_id)` sobre o gravado; grava só
  `user_id`. O estado ativo esperado é implícito (o domínio recusa desligado).
- **L-DEACT:** inexistente ⇒ `EmployeeNotFoundError`; depois
  `Employee.deactivate_as_read(expected_user_id, was_active=expected_active)` sobre o
  gravado; grava só `active = false`. Idempotente no valor: dois R13 concorrentes no
  mesmo registro, com o mesmo login, respondem os dois 200.
- Em qualquer erro, nada é gravado; nenhum outro campo muda.
- O `expected_active` existe porque a decisão de revogar (R2) depende de o registro
  estar ativo: sem ele, uma recontratação entre a leitura e a escrita faria R13 ou
  R20 encerrar um vínculo **ativo** sem passar pela regra. Só essa direção recusa.

**Port `IdentityGateway`** (`port-out`), lei nova:
```python
@dataclass(frozen=True)
class ExistingLogin:
    user_id: UserId
    tenant_id: TenantId | None       # None: conta fora de restaurante (platform_admin)
    unit_ids: frozenset[UnitId]      # unidades de que a conta é membro
    every_unit: bool                 # a conta alcança todas as unidades do tenant

def find_login_by_email(self, email: str) -> ExistingLogin | None: ...   # L-IG6
```
- **L-IG6:** devolve a conta cujo e-mail é `email` (na forma que identity normaliza),
  em **qualquer** tenant, com o tenant, as unidades de que **ela** é membro e se ela
  alcança todas as unidades do tenant sem membership (sempre falso para conta sem
  tenant); nenhuma conta ⇒ `None`. E-mail
  malformado ⇒ `InvalidLoginEmailError` (a mesma tradução de L-IG2). Qualquer outra
  falha sobe crua, mesma instância. Não responde papel: staff não nomeia o
  vocabulário de papéis (ADR 3.8.0001 Alt. F).

**Identity** (`features/identity/application/`)
- `FindAccountByEmailCommand(email: Email)`; `AccountSummaryResult(user_id: UserId,
  tenant_id: RestaurantId | None, unit_ids: tuple[UnitId, ...], sees_every_unit: bool)`.
- `FindAccountByEmailUseCase(users: UserRepository).execute(command) ->
  AccountSummaryResult | None` — só leitura, facade-only, não autoriza; `unit_ids`
  filtra as memberships pelo `user_id` da conta; `sees_every_unit` é
  `User.bypasses_unit_scope()` de conta **com** tenant (o `platform_admin`, sem tenant,
  devolve falso: não há tenant cujas unidades alcançar); a regra de visibilidade fica
  em identity.
- `IdentityFacade.find_account_by_email(email: str) -> AccountSummary | None`, com
  `AccountSummary(user_id: str, tenant_id: str | None, unit_ids: tuple[str, ...],
  sees_every_unit: bool)` em primitivos; `InvalidEmailError` sobe sem tradução
  (propriedade 2 da fachada).

**Application de staff** (`features/staff/application/`)
- Commands (com `actor`, `tenant_id`, `unit_id`, `employee_id`):
  `LinkExistingLoginCommand(..., email: str)`, `RelinkLoginCommand(..., email: str)`,
  `UnlinkLoginCommand(...)`. Result: `EmployeeResult` (já existente).
- Use cases (`port-in`): `LinkExistingLoginUseCase`, `RelinkLoginUseCase`,
  `UnlinkLoginUseCase`, cada um com `EmployeeRepository`, `IdentityGateway` e
  `AccessGuard`.
- Erros de application: `LoginAccountNotFoundError` (`StaffApplicationError`, 404);
  `LoginAlreadyLinkedInUnitError(employee_id)` (`StaffError` declarado em
  `application/errors.py`, como `LoginEmailAlreadyInUseError` — regra que consulta
  outros registros, não transição do agregado; 409).
- Módulo auxiliar `use_cases/_login_link.py` (não é use case):
  - `end_active_link(employees, gateway, employee) -> None` — **o ponto único** da
    regra do ADR 3.8.0001 (decisões 1 e 2), movido de `deactivate_employee.py`;
  - `resolve_linkable_login(employees, gateway, email, employee) -> UserId` — consulta
    a conta; se ela é o login atual do registro, devolve-o sem mais checagens (só R19
    alcança: em R18 o registro não tem login); senão aplica a elegibilidade (R4) e "um
    por unidade" (R10).
- `scripts/check_layout.py`: tabela nomeada de auxiliares que escrevem fora do BC
  (`end_active_link` → revogação em identity), contada pela regra 10 como escrita do
  use case que o chama; `MULTI_WRITE_ALLOWLIST` ganha `RelinkLoginUseCase` e
  `UnlinkLoginUseCase`, citando ADR 2.6.0002 §2 e ADR 3.10.0001.

**HTTP de staff**

| # | Método | Caminho | Use case | Status |
|---|---|---|---|---|
| R18 | `POST` | `/units/{unit_id}/employees/{employee_id}/login-link` | `link_existing_login` | 200 |
| R19 | `PUT` | `/units/{unit_id}/employees/{employee_id}/login-link` | `relink_login` | 200 |
| R20 | `DELETE` | `/units/{unit_id}/employees/{employee_id}/login-link` | `unlink_login` | 200 |

- `ExistingLoginRequest(email: str)` para R18 e R19; resposta `EmployeeResponse`.
- Cada rota autoriza `manage_staff` e depois `manage_users` sobre a unidade do path,
  como R17.

### Consumidos
- `EmployeeRepository.find_by_id`, `list_by_unit`, `link_login` (L-LINK).
- `IdentityGateway.is_employee_login` (L-IG5) e `revoke_login_sessions` (L-IG4).
- `AccessGuard` (L-AG1…L-AG4) e `PERMISSION_MANAGE_STAFF`/`PERMISSION_MANAGE_USERS`.
- `UserRepository.find_credentials_by_email` e `list_memberships`;
  `User.bypasses_unit_scope` (identity).
- Mapa de status de staff (3.4, 3.9) e as varreduras de totalidade de staff e
  identity.

## 5. Invariantes e regras

- **R1 — o vínculo só muda por escrita condicional.** Toda transição grava pelo port
  com o estado do vínculo que o use case leu como esperado; o gravado diferente ⇒
  `EmployeeLoginChangedError` e nada é gravado (R18 usa `link_login`, cuja condição
  é "sem vínculo e ativo"). Fecha a classe de defeito da #68 e da #108 para as
  transições novas.
- **R2 — fim de vínculo ativo passa pelo ponto único.** R13 (desligar), R19 (trocar)
  e R20 (desvincular) chamam `end_active_link` com o registro lido — em R19, com o
  login **antigo** —, **antes** da escrita (ADR 3.5.0003 §2). A regra é a do ADR
  3.8.0001 decisão 1: registro ativo **e** com login **e** nenhum outro registro
  ativo da mesma unidade com o mesmo login **e** login de funcionário ⇒ revoga as
  sessões. Nenhum use case chama `revoke_login_sessions` ou `is_employee_login` fora
  desse módulo.
- **R3 — desligamento condicional ao estado lido.** R13 grava por L-DEACT com o
  `user_id` e o estado ativo que leu. Um vínculo criado, trocado ou desfeito, ou uma
  recontratação, entre a leitura e a escrita faz R13 responder 409 sem gravar o
  desligamento; a nova tentativa lê o estado novo e aplica R2. Outro desligamento
  concorrente do mesmo registro, com o mesmo login, não recusa (idempotente).
- **R4 — elegibilidade da conta (R18 e R19).** A conta nomeada pelo e-mail é
  elegível se e só se existe, pertence ao **tenant do registro** e **alcança a
  unidade do registro** — é membro dela, ou alcança todas as unidades do tenant
  (o dono, pela regra de visibilidade de identity). Conta inexistente, de outro
  tenant, `platform_admin` (sem tenant) ou que não alcança a unidade ⇒ **o mesmo**
  `LoginAccountNotFoundError`, com a mesma mensagem: nenhuma resposta distingue "não
  existe" de "existe fora do seu alcance". O papel não entra na regra.
- **R5 — quem pode.** R18, R19 e R20 exigem `manage_staff` **e** `manage_users`
  sobre a unidade do registro, nessa ordem, antes de qualquer leitura (como R17,
  ADR 3.5.0001/3.7.0001). O ator pode vincular a própria conta.
- **R6 — guardas locais antes de identity.** R18: `assert_can_link_login` (vinculado
  ⇒ 409, depois desligado ⇒ 409) antes de consultar a conta. R19: sem vínculo ⇒ 409,
  depois desligado ⇒ 409, antes de consultar a conta. E-mail malformado só é
  detectado por identity, então chega depois dessas guardas.
- **R7 — ordem das checagens** — autorização antes de qualquer outra instrução (a forma da Stage 3.7), em cada transição:
  - **R18:** autorizar (staff, users) → `find_by_id` (404) → guardas de vínculo →
    consulta da conta → elegibilidade (404) → um por unidade (409) → `link_login`
    (L-LINK) → result.
  - **R19:** autorizar → `find_by_id` → guardas (sem vínculo, desligado) → consulta
    da conta → **se a conta é o login atual, devolve o registro sem escrever nem
    revogar** (antes da elegibilidade: o login já é do registro) → elegibilidade →
    um por unidade → `end_active_link` com o login antigo → `relink_login`
    (L-RELINK) → result.
  - **R20:** autorizar → `find_by_id` → sem vínculo ⇒ 409 → `end_active_link` →
    `unlink_login` (L-UNLINK) → result.
  - **R13:** autorizar → `find_by_id` → `end_active_link` → `deactivate` (L-DEACT,
    esperado = o lido) → result.
- **R8 — desvincular vale para registro desligado.** O vínculo de um desligado é
  história, mas desvinculá-lo é o caminho para remover (R15) um registro vinculado
  por engano. Como o registro não está ativo, R2 não revoga nada.
- **R9 — vincular e trocar recusam registro desligado.** "Desligado não recebe
  login" (concept 3.5 §5.5; workforce §3.8) vale para a conta existente também.
- **R10 — um login por unidade.** R18 e R19 recusam com
  `LoginAlreadyLinkedInUnitError` a conta que já está vinculada a **outro** registro
  da mesma unidade, ativo ou desligado (workforce §3.1 › "um por unidade";
  ADR 3.1.0001 iii). Registros de
  outras unidades não contam. A checagem lê a unidade antes da escrita; dois
  vínculos concorrentes da mesma conta na mesma unidade ainda podem passar (§6.1).

## 6. Casos de erro e exceções

| Situação | Erro | Status |
|---|---|---|
| Ator sem `manage_staff` ou sem `manage_users` na unidade; unidade de outro tenant ou inexistente | exceção do guard, crua (L-AG2) | 403 |
| Registro inexistente no endereço (tenant + unidade), inclusive registro de outra unidade | `EmployeeNotFoundError` | 404 |
| R18 em registro já vinculado | `EmployeeAlreadyHasLoginError` | 409 |
| R18/R19 em registro desligado | `TerminatedEmployeeLoginError` | 409 |
| R19/R20 em registro sem vínculo | `EmployeeHasNoLoginError` | 409 |
| Login gravado mudou entre a leitura e a escrita (R13, R19, R20), ou o registro lido desligado foi recontratado (R13, R20) | `EmployeeLoginChangedError` | 409 |
| R19 sob concorrência: registro desligado ou desvinculado entre a leitura e a escrita | `TerminatedEmployeeLoginError` / `EmployeeHasNoLoginError` (precedência de L-RELINK) | 409 |
| R20 sob concorrência: registro desvinculado entre a leitura e a escrita | `EmployeeHasNoLoginError` | 409 |
| R18/R19: nenhuma conta elegível com o e-mail (inexistente, outro tenant, `platform_admin`, não alcança a unidade) | `LoginAccountNotFoundError` | 404 |
| R18/R19: a conta já está em outro registro da unidade | `LoginAlreadyLinkedInUnitError` | 409 |
| E-mail malformado | `InvalidLoginEmailError` (L-IG6) | 422 |
| Falha de identity na consulta, na verificação de papel ou na revogação | sobe crua; nada é gravado | 500 |
| Id de unidade ou registro malformado no path | `InvalidIdentifierError` da borda (ADR 3.6.0002), antes de autorizar | 422 |

### 6.1 Limites declarados (não fechados)
- **Dois vínculos concorrentes da mesma conta na mesma unidade.** R10 lê a unidade e
  depois grava em outra linha; dois R18/R19 simultâneos da mesma conta em dois
  registros da unidade podem passar os dois. Só esse duplo entrelace produz dois
  registros da unidade com o mesmo login, e só sobre ele volta a corrida do ADR
  3.8.0001 › "Concurrent termination of two same-unit records of one login" (dois
  fins de vínculo concorrentes, nenhum revoga; as sessões não alcançam nada por
  registros desligados ou desvinculados). Fechar de vez pede uma transação de staff
  que segure leitura e escrita (lock por `user_id`) — D8, com issue própria.
- **`update` segue gravando `active`** (ADR 3.3.0006, "última escrita vence"): uma
  edição (R07) que leu o registro antes de uma recontratação e grava depois devolve
  o estado antigo. Com um vínculo no meio, o registro pode terminar desligado e
  vinculado sem revogação. É a classe de defeito de `update` sobre o estado, anterior
  a esta Stage; fechá-la é dar a `active` escrita própria, como `user_id` — finding.
- **Revogação antes da escrita que depois é recusada ou falha.** Como em R13 desde a
  3.5 (ADR 3.5.0003 §2), R13, R19 e R20 podem revogar e depois receber 409 do port
  (estado mudou) ou falhar na escrita: a revogação fica persistida em identity, a
  pessoa loga de novo, e o registro fica como estava. Revogar a mais custa um novo
  login; é o lado seguro do mesmo trade do ADR 3.5.0003 §2.
- **Conta antiga de um e-mail errado continua existindo** em identity depois de R19
  ou R20 — desativar conta é non-goal (ADR 3.8.0001 decisão 4).
- **Membership não é criada.** Gerente, RH ou funcionário sem membership na unidade
  do registro não é vinculável a ele até existir gestão de membership em identity.

## 7. Decisões técnicas relevantes

### D1 — Trocar é operação própria
- **O quê:** três operações (R18, R19, R20), não duas.
- **Por quê:** R19 valida a conta nova **antes** de encerrar o vínculo antigo e grava
  a troca numa escrita só; "desvincular + vincular" pelo cliente deixa o registro
  sem login quando a segunda chamada falha (conta não elegível, e-mail errado).
- **ADR:** [3.10.0001](../../adr/3_10_0001-login-link-transitions-by-conditional-write.md) §1.
- `[decision] P delegado — trocar como operação própria (R19), motivo: valida antes de encerrar e grava numa escrita só, sem estado intermediário observável; o custo é um use case e uma lei a mais, que reaproveitam o ponto único e a forma de L-LINK.`

### D2 — A conta é nomeada pelo e-mail
- **O quê:** R18 e R19 recebem `email`; identity resolve a conta.
- **Por quê:** é como o gerente conhece a pessoa e como R17 já nomeia a conta;
  nenhuma rota dá o id de uma conta que ainda não está em registro; e o request de
  staff continua sem `user_id` (varredura `_CAMPOS_PROIBIDOS_EM_REQUEST` de
  `test_http_schemas.py`, cuja razão — "quem gera o `user_id` é identity" — segue
  valendo).
- **ADR:** [3.10.0002](../../adr/3_10_0002-existing-account-eligibility-by-email.md) §1.
- `[decision] P delegado — e-mail, motivo: o gerente não tem como obter pela API o id de uma conta que ainda não está em registro, e o e-mail é o identificador que R17 já usa; o oráculo de existência fica coberto pela recusa uniforme de R4.`

### D3 — Elegibilidade: tenant e alcance da unidade, recusa uniforme
- **O quê:** R4.
- `[decision:C] D3a — as recusas da conta (inexistente, outro tenant, platform_admin, fora da unidade) têm erro e mensagem iguais? Escolha: iguais (LoginAccountNotFoundError, 404) · Alternativas: erros distintos por causa · Degrau (C): 2 · Base: ADR 3.4.0007 §4 (registro de outra unidade/tenant é "não encontrado"; nenhum erro confirma a existência do que o chamador não pode endereçar) · Verificado: não verificado (§4.2) — fonte interna, citação conferida pelo revisor de conformidade do Checkpoint A · Configuração candidata: nenhuma · Reversível: sim.`
- `[decision:C] D3b — status da conta não elegível. Escolha: 404, StaffApplicationError · Alternativas: 409; 422 · Degrau (C): 1 · Base: JobFunctionNotFoundError, referência de corpo inexistente no tenant, é 404 sob a raiz de aplicação (error_handlers.py › STAFF_ERROR_STATUS; ADR 3.9.0001 "recurso endereçado inexistente") · Verificado: não verificado (§4.2) — fonte interna · Configuração candidata: nenhuma · Reversível: sim.`
- `[decision] P delegado — a conta precisa alcançar a unidade do registro, por membership ou pelo alcance de todas as unidades que identity dá ao dono, e o vínculo não cria membership, motivo: o dono nasce sem membership e enxerga o tenant inteiro (provision_restaurant.py, invite_owner.py, user.py › can_view_unit), então exigir membership excluiria todo dono do caso imediato do roadmap; a regra de alcance vem de identity como fato (sees_every_unit), sem papel em staff, e criar membership seria escrita em identity com regras próprias (ADR 2.1.0001). (Revisada no Checkpoint A, §13 A-1.)`
- `[decision:C] D3c — a consulta da fachada devolve o papel? Escolha: não; devolve id, tenant, unidades e sees_every_unit · Alternativas: devolver também o papel, como o bloco do roadmap sugere ("tenant, papel e unidades") · Degrau (C): 1 · Base: ADR 3.8.0001 Alt. F (o papel fica na borda); platform_admin é identificado por tenant None (ADR 2.1.0002); o alcance do dono chega como fato de visibilidade, não como papel · Verificado: não verificado (§4.2) · Configuração candidata: nenhuma · Reversível: sim (aditivo).`

### D4 — Quem pode
- **O quê:** R5.
- **ADR:** [3.10.0002](../../adr/3_10_0002-existing-account-eligibility-by-email.md) §5.
- `[decision] P delegado — manage_staff e manage_users sobre a unidade nas três transições, sem exigência extra para conta de papel acima de employee e com autovínculo permitido, motivo: o vínculo não concede permissão (o papel da conta não muda), só associa a conta a um registro que o ator já administra; o autovínculo é o caso imediato do roadmap (gerente ou dono que trabalha na escala); a regra é a mesma de R17, que já é a operação de gestão de login.`

### D5 — Forma da escrita
- **O quê:** R1 e as três leis de §4.
- `[decision:C] D5 — forma da escrita de desvincular/trocar/desligar. Escolha: um método por transição, que trava a linha, reaplica a guarda do domínio sobre o gravado e grava uma coluna, com o esperado (login e, onde decide a revogação, estado ativo) lido pelo use case · Alternativas: UPDATE … WHERE user_id = :esperado sem lock; um método só com user_id anulável; esperado enviado pelo cliente · Degrau (C): 1 · Base: ADR 0.0.0010 Alt. A (diagnóstico depois da escrita reporta erro errado; guardas reescritas em SQL) e Alt. B › "each gets its own method" · Verificado: não verificado (§4.2) — fonte interna · Configuração candidata: nenhuma · Reversível: sim.`
- A intenção de R19 ("o registro passa a ser desta conta") e de R20 ("o registro
  fica sem login") vale sobre qualquer vínculo vigente; o esperado protege a decisão
  de revogação, que foi tomada sobre o estado lido. R18 continua estrita (cria
  vínculo só onde não há), como R17 (ADR 0.0.0010 §Consequences).
- **Supersessão:** `relink_login` e `unlink_login` são escritores novos de `user_id`
  num registro existente. Superam, em parte, o ADR 3.5.0004 §2 ("set once", só por
  `Employee.link_login`) e a decisão 3 do ADR 0.0.0010 ("once the record exists no
  write path other than `link_login` can set one"): o vínculo continua tendo **só**
  escritas próprias e condicionais, agora quatro (`link_login`, `relink_login`,
  `unlink_login`, além do `add` do registro novo). Notas *append-only* nos dois ADRs.

### D6 — Ponto único da regra de fim de vínculo
- **O quê:** `_login_link.end_active_link`, chamado por R13, R19 e R20.
- **Por quê:** ADR 3.8.0001 decisão 5; technical 3.8 §7 › "extrair a regra (unidade +
  papel) para um ponto único quando o segundo caminho nascer".
- **Trava:** varredura de AST sobre `use_cases/` — `revoke_login_sessions` e
  `is_employee_login` só aparecem no módulo auxiliar; todo use case que chama
  `deactivate`, `relink_login` ou `unlink_login` **sobre o atributo tipado
  `EmployeeRepository`** chama `end_active_link` antes, no mesmo método. Mais, por
  use case, um teste unit com fakes que registram a sequência de chamadas e provam
  que a regra recebeu o registro lido (em R19, com o login antigo) antes da escrita.
- **Regra 10:** o varredor de `check_layout.py` ganha uma tabela nomeada de auxiliares
  que escrevem fora do BC; a chamada a `end_active_link` conta como a escrita em
  identity do use case que a faz. Sem isso a entrada de `DeactivateEmployeeUseCase`
  na allowlist ficaria morta (o script reprova) e R19/R20 nasceriam invisíveis à
  regra. Nota *append-only* no ADR 2.6.0002 (que enumera duas travessias).
- `[decision:C] D6 — onde mora o ponto único. Escolha: módulo auxiliar com prefixo _ em use_cases/ (função), com a regra 10 ensinada a vê-lo · Alternativas: serviço de domínio; classe injetada pelo composition root (o varredor também não a enxergaria sem mudança) · Degrau (C): 1 · Base: precedente _unit_enablement.py (staff, Stage 3.11) e _invitation.py (identity); a regra consulta dois ports, então não é domínio puro · Verificado: não verificado (§4.2) · Configuração candidata: nenhuma · Reversível: sim.`

### D7 — R13 confere o estado do vínculo na escrita
- **O quê:** R3 e L-DEACT.
- **ADR:** [3.10.0001](../../adr/3_10_0001-login-link-transitions-by-conditional-write.md) §4.
- `[decision:C] D7 — o desligamento reconfere o vínculo sob o lock da linha? Escolha: sim, pela escrita condicional L-DEACT (login e estado ativo lidos), recusando com 409 sem gravar · Alternativas: manter declarado (ADR 0.0.0010 §Negative); revogar depois de gravar (ADR 3.8.0001 Alt. H) · Degrau (C): 1 · Base: concept 3.5 §5.5 e workforce §3.8 ("registro desligado recusa criar login") como regra sobre o estado gravado; a recusa vem antes de gravar o desligamento, e o que pode já estar persistido é só uma revogação (o lado seguro, como numa falha de escrita hoje), não o "desligado com sessão viva" que ADR 3.5.0003 §2 evita · Verificado: não verificado (§4.2) — fonte interna · Configuração candidata: nenhuma · Reversível: sim.`
- O desligamento passa a gravar só `active`, em vez do agregado inteiro lido antes.

### D8 — Um login por unidade, e o resíduo da corrida
- **O quê:** R10 e §6.1.
- `[decision] P delegado — vincular e trocar recusam a conta que já está em outro registro da mesma unidade, motivo: é a regra canônica do doc de domínio (workforce §3.1 "um por unidade"; ADR 3.1.0001 iii), e ela tira da API o caminho que produziria a corrida do ADR 3.8.0001, que esta Stage herdou como dona. (Revisada no Checkpoint A, §13 A-3.)`
- `[decision:C] D8 — fechar a corrida de dois fins de vínculo do mesmo login na mesma unidade com lock por user_id, ou com unicidade no banco, ou declarar o resíduo? Escolha: recusa em aplicação (R10) e resíduo declarado só para dois vínculos concorrentes da mesma conta na unidade, com issue própria para o lock · Alternativas: lock por user_id (exige transação de staff que segure a leitura da unidade, a consulta a identity e a escrita — staff não tem Unit of Work, ADR 2.6.0002 §2); índice único parcial (tenant_id, unit_id, user_id) em migration · Degrau (C): 4 · Base: ADR 3.8.0001 › `### Negative` › "A Unit of Work alone does not close it", com o dono nomeado como a Stage que implementa "link an existing login": esta Stage fecha o caminho que tornaria a corrida produzível e deixa o lock para quando staff tiver transação própria; o índice único reprovaria os arranjos do caso (a) dentro da unidade nas suítes da 3.8 (UPDATE direto) e tornaria morta a condição de unidade do ADR 3.8.0001, sem precisar disso para fechar a API · Verificado: não verificado (§4.2) · Configuração candidata: índice único parcial, ou lock por user_id quando staff tiver Unit of Work · Reversível: sim.`
- O "Owner" do ADR 3.8.0001 `### Negative` é superado em parte (nota *append-only*):
  o caminho de produção fecha aqui; o resíduo vai para a issue aberta no fechamento
  desta Stage.

### D9 — Rotas
- `[decision:C] D9 — forma das rotas. Escolha: sub-recurso login-link do registro, POST/PUT/DELETE, 200 com EmployeeResponse · Alternativas: PUT /login (ao lado do POST /login de R17, que cria conta); 201 em R18; 204 em R20 · Degrau (C): 1 · Base: R13/R14 (transições do registro) respondem 200 com o registro; R17 ocupa /login com a criação de conta · Verificado: não verificado (§4.2) · Configuração candidata: nenhuma · Reversível: sim (pré-piloto).`

### D10 — A consulta de identity lê pelo método de credenciais
- **O quê:** `FindAccountByEmailUseCase` usa `find_credentials_by_email` e descarta o
  hash, e `list_memberships` **filtrado pelo `user_id` da conta** para as unidades
  (o port não garante o filtro — decisão 3 do seu docstring).
- `[decision:C] D10 — porta da consulta por e-mail. Escolha: reaproveitar find_credentials_by_email (o hash não sai do use case; UserCredentials.password_hash tem repr=False) · Alternativas: método novo UserRepository.find_by_email com fake, adapter e contrato · Degrau (C): 4 · Base: nenhuma mudança de port em identity enquanto a #211 edita identity em paralelo; o método novo é aditivo depois · Verificado: não verificado (§4.2) · Configuração candidata: find_by_email quando um segundo consumidor aparecer · Reversível: sim.`

## 8. Integrações

### Internas (com outras Stages/módulos)
- **identity:** fachada (`find_account_by_email`, novo; `account_role` e
  `revoke_all_sessions`, existentes) pela aresta única
  `staff.adapters.out.identity.* -> identity.application.facade` (ADR 3.5.0001); o
  `AccessGuard` pela fachada de acesso.
- **scheduling:** nenhuma mudança; `get_my_schedule` (4.5) alcança a conta vinculada
  porque lê os registros pelo `user_id`.

### Externas
- Nenhuma.

## 9. Modelo de dados

Sem mudança de schema e sem migration: as três escritas gravam colunas que já
existem (`employees.user_id`, `employees.active`).

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Uma transição nova encerra vínculo sem passar pela regra (revoga demais ou de menos) | M | A | ponto único + varredura de AST pelo receptor tipado + unit de sequência por use case (D6); suíte parametrizada por condição × chamador |
| Oráculo: distinguir conta inexistente de conta de outro tenant | M | A | R4 recusa uniforme; teste compara status e corpo dos casos |
| R13 condicional quebra o desligamento existente (critérios da 3.5/3.8) | B | A | as suítes de R13 seguem verdes; conduta com duas conexões |
| Adapter de L-RELINK/L-UNLINK sem lock passa no contrato sequencial | M | A | conduta com duas conexões para as três leis (CA10) |
| Regra 10 cega ao auxiliar | A | M | tabela nomeada no varredor + teste do script (D6) |
| Conflito de linhas com #206/#211 (mapa de erros, router, fachada) | A | B | mudanças aditivas; rebase de quem mergear depois |

## 11. Critérios de aceitação

- [x] **CA1** R18 vincula a um registro ativo sem login a conta existente do mesmo
  tenant que alcança a unidade: gerente membro da unidade, funcionário membro, e o
  **dono sem membership** (pelo alcance de todas as unidades), inclusive a conta do
  próprio ator; só `user_id` muda (unit; e2e com o dono e com um gerente).
- [x] **CA2** R18 e R19 recusam com o **mesmo** 404 e o **mesmo** corpo: e-mail sem
  conta, conta de outro tenant, conta `platform_admin` e conta do tenant que não
  alcança a unidade; nada é gravado e nenhuma sessão é revogada (unit parametrizado
  sobre R18 × R19 × os quatro casos; e2e: outro tenant e `platform_admin` em R18 e em
  R19).
- [x] **CA3** R18, R19 e R20 autorizam `manage_staff` e depois `manage_users` sobre a
  unidade do command, antes de qualquer leitura; negação em qualquer das duas não
  deixa efeito (varredura de autorização de staff).
- [x] **CA4** Regra de fim de vínculo por chamador: suíte parametrizada sobre R13,
  R19 e R20 × {revoga (registro ativo, único da unidade com o login, login de
  funcionário); não revoga com outro registro ativo da unidade com o login; não
  revoga com login de outro papel; não revoga com login desconhecido; não revoga com
  registro desligado (R13 repetido, R20 de desligado)}; em R19 a regra é aplicada ao
  login **antigo**; R19 com o login atual não escreve nem revoga e não consulta
  elegibilidade nem R10 (o login já é do registro) (unit; e2e com `POST /auth/refresh` do login antigo em R19).
- [x] **CA5** R20 desvincula registro ativo e desligado; depois de R20, R15 remove o
  registro (unit e e2e).
- [x] **CA6** Guardas e precedência de §6, antes de consultar identity (unit, com o
  fake registrando chamadas): R18 em vinculado e desligado ⇒ `EmployeeAlreadyHasLogin`;
  R18 em desligado sem vínculo ⇒ `TerminatedEmployeeLogin`; R19 em desligado e sem
  vínculo ⇒ `EmployeeHasNoLogin`; R19 em desligado vinculado ⇒ `TerminatedEmployeeLogin`;
  R20 sem vínculo ⇒ `EmployeeHasNoLogin`; R18 em vinculado com e-mail malformado ⇒ 409
  (a guarda vence o 422); R18/R19 com e-mail malformado ⇒ 422 na borda.
- [x] **CA7** Contrato fake ≡ Postgres de L-UNLINK, L-RELINK e L-DEACT, com um corpo
  de teste só: login esperado divergente ⇒ `EmployeeLoginChangedError` (as três);
  lido desligado e gravado ativo ⇒ `EmployeeLoginChangedError` (L-UNLINK, L-DEACT);
  lido ativo e gravado desligado ⇒ L-DEACT sucede sem efeito; L-RELINK sobre gravado
  desligado ⇒ `TerminatedEmployeeLoginError` e sobre gravado sem vínculo ⇒
  `EmployeeHasNoLoginError`; L-UNLINK sobre gravado sem vínculo ⇒
  `EmployeeHasNoLoginError`; endereço de outra unidade/tenant ⇒
  `EmployeeNotFoundError`; só a coluna da lei muda; nada é gravado em erro.
- [x] **CA8** Contrato fake ≡ real de L-IG6: conta conhecida devolve id, tenant,
  unidades de que **ela** é membro e `every_unit`; dono ⇒ `every_unit` verdadeiro sem
  unidades; `platform_admin` ⇒ tenant `None` e `every_unit` falso; desconhecida ⇒
  `None`; e-mail com espaço e maiúsculas encontra a conta
  (normalização de identity); malformado ⇒ `InvalidLoginEmailError`; outra falha sobe
  crua na mesma instância.
- [x] **CA9** Ponto único (DoD): varredura de AST prova que `revoke_login_sessions` e
  `is_employee_login` só são chamados em `_login_link.py` e que todo use case que
  chama `deactivate`, `relink_login` ou `unlink_login` do repositório (receptor
  tipado `EmployeeRepository`) chama `end_active_link` antes; o teste do script prova
  que a regra 10 conta a chamada ao auxiliar; a suíte de R13 da 3.5/3.8 segue verde.
- [x] **CA10** Conduta com duas conexões (Postgres), uma por lei: L-DEACT — R13 que
  leu o registro sem vínculo grava depois de um `link_login` concorrente ⇒
  `EmployeeLoginChangedError`, registro **ativo e vinculado**; L-RELINK — dois R19
  concorrentes sobre o mesmo login lido, o segundo ⇒ `EmployeeLoginChangedError` e o
  gravado é o do primeiro; L-UNLINK — desvincular concorrente a um `relink_login` ⇒
  `EmployeeLoginChangedError`, gravado = o login novo.
- [x] **CA11** Identity: `find_account_by_email` devolve id, tenant, unidades da conta
  (filtradas pelo `user_id`) e `sees_every_unit` em primitivos, `None` para e-mail
  sem conta; `find_account_by_email` entra em `_EXCLUSOES` e `_FACADE_ONLY` do
  inventário da 2.7 e só a fachada e o composition root o importam.
- [x] **CA12** R10: R18 e R19 recusam com 409 a conta já vinculada a outro registro da
  mesma unidade (ativo ou desligado) e aceitam a conta vinculada a registro de outra
  unidade (unit; e2e para R18).
- [x] **CA13** Varreduras de totalidade verdes: mapa de erros de staff, pasta de use
  cases × composition root, `router.routes` × overrides e tabelas de rota, DTOs.
- [x] **CA14** e2e contra Postgres percorre R18 → R19 → R20 → R15 com um gerente real
  e cobre o DoD em **cada** rota: R18, R19 e R20 com unidade fora do alcance do ator
  ⇒ 403, e com registro de outra unidade no endereço ⇒ 404; R18 e R19 com conta de
  outro tenant e com `platform_admin` ⇒ 404 (CA2).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida?
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido? (não há externa)
- [x] Decisões com alternativa real descartada têm ADR escrito? (3.10.0001, 3.10.0002)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (`check_stage_deps` OK)
- [x] Stage cabe em ~3–12 Tasks? (12)
- [x] Riscos críticos têm mitigação plausível?
- [x] As perguntas do bloco do roadmap foram respondidas? (membership D3; quem pode
  D4; forma da escrita D5; corrida D8; ordem inversa D7; paralelismo com a 4.4: a 4.4
  já mergeou)

## 13. Disposições do Checkpoint A (2026-11-22)

Três revisores de contexto zerado: conformidade, domínio/testabilidade e o
`decision-reviewer` da skill `evidence-resolution`. Disposição de cada achado:

- **A-1 (blocker, domínio F1; conformidade F4; decision-reviewer D3) — o dono nunca
  seria vinculável.** `corrigido`: R4 passa a aceitar a conta que alcança todas as
  unidades (`sees_every_unit`, de `User.bypasses_unit_scope`); D3 P revisado; CA1 e
  CA8 cobrem o dono sem membership.
- **A-2 (major, domínio F2) — `update` grava `active`; recontratação entre leitura e
  escrita deixa R13/R20 encerrar vínculo ativo sem a regra.** `corrigido` em parte:
  L-UNLINK e L-DEACT condicionam também ao estado ativo lido (§4, R3, CA7). A
  sequência que passa por `update` (edição velha sobre recontratação) é anterior à
  Stage e fica `escalado` como limite declarado (§6.1) com finding.
- **A-3 (major, conformidade F3; decision-reviewer D8 ×2) — D8 lia ao contrário a
  fonte que fazia desta Stage a dona da corrida, e o ADR 3.1.0001 iii/workforce §3.1
  dizem "um por unidade".** `corrigido`: R10 (um login por unidade) fecha o caminho
  pela API; D8 reescrito com a base correta; supersessão parcial do "Owner" do ADR
  3.8.0001 declarada; resíduo com issue própria.
- **A-4 (major, conformidade F1) — ADR 3.5.0004 §2 e ADR 0.0.0010 decisão 3
  contrariados sem supersessão.** `corrigido`: D5 › Supersessão; notas nos dois ADRs.
- **A-5 (major, conformidade F2) — a regra 10 do `check_layout` perderia a travessia
  de R13 (allowlist morta) e não veria R19/R20.** `corrigido`: D6 › Regra 10; contrato
  do script em §4; CA9; nota no ADR 2.6.0002.
- **A-6 (major, domínio F3) — nenhum teste prova o lock de L-RELINK/L-UNLINK.**
  `corrigido`: CA10 com uma conduta por lei.
- **A-7 (major, domínio F4) — varredura de AST ambígua por nome.** `corrigido`: D6 e
  CA9 fixam o receptor tipado; unit de sequência por use case.
- **A-8 (minor, domínio F5) — R19 com o próprio login responderia 404.**
  `corrigido`: R7 compara antes da elegibilidade; CA4.
- **A-9 (minor, domínio F6) — critérios faltando (precedência de R19, R10, 422 e
  precedência sobre ele, normalização do e-mail).** `corrigido`: CA6, CA8, CA12.
- **A-10 (minor, domínio F7) — CA4 com representante estreito.** `corrigido`: CA4
  parametrizado por condição × chamador.
- **A-11 (minor, domínio F8; conformidade F5) — "fora do alcance" ambíguo e e2e do
  DoD não amarrado a cada rota.** `corrigido`: CA14.
- **A-12 (decision-reviewer D10) — `list_memberships` não garante filtro por
  usuário.** `corrigido`: §4 Identity e D10 filtram pelo `user_id`; CA11.
- **A-14 a A-19 (rodada 2, revisor único de re-verificação), todas `corrigido`.**
  A-14 (major): o auxiliar não tinha onde parar no login atual de R19 — §4
  `resolve_linkable_login` devolve o login atual sem checagens; exceção no ADR
  3.10.0002 §3. A-15: L-DEACT tornava 409 o duplo desligamento concorrente —
  `deactivate_as_read` só recusa login trocado ou "lido desligado, gravado ativo" (R3,
  §4, CA7). A-16: §6 e CA7 prometiam `EmployeeLoginChangedError` onde L-RELINK/L-UNLINK
  levantam outros 409 — linhas e CA7 reescritos. A-17: revogação de R13 seguida de 409
  não declarada — §6.1, D7 e ADR 3.10.0001 §Negative. A-18: `every_unit` do
  `platform_admin` indefinido — falso para conta sem tenant (L-IG6, CA8). A-19:
  `LoginAlreadyLinkedInUnitError` passa para `application/errors.py`; o ADR 3.10.0002
  dizia "sixth" facade-only (é o quinto).
- **A-13 (decision-reviewer D2) — `EmployeeResponse` já expõe `user_id` de registro
  vinculado.** `corrigido` no texto (premissas, D2); não muda a escolha: a conta-alvo
  de R18 ainda não está em registro.

## 14. Referências

- [`../../overview.md`](../../overview.md) §3; [`../../roadmap.md`](../../roadmap.md) §Stage 3.10
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) §3.1, §3.8
- Concept 3.5 §5.5, §6.4, §10; technical 3.8 §7; concept 3.8 D7
- ADRs 3.10.0001, 3.10.0002; 0.0.0010, 0.0.0013, 0.0.0020, 2.1.0001, 2.1.0002, 2.6.0002,
  2.7.0001, 3.1.0001, 3.3.0006, 3.4.0007, 3.5.0001, 3.5.0002, 3.5.0003, 3.5.0004,
  3.7.0001, 3.8.0001, 3.9.0001
- Issues #218, #107, #68, #108

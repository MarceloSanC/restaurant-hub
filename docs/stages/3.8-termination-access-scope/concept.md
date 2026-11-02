---
title: Concept — Desligamento corta só o acesso que o registro concede
description: Definição do que será feito nesta Stage e por quê, com decisões técnicas relevantes
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, termination-access-scope, desligamento, revogacao, sessoes, is_active, identity-gateway, staff, identity]
status: done
created_at: 2026-10-19
updated_at: 2026-11-01
stage_id: 3.8-termination-access-scope
stage_title: Desligamento corta só o acesso que o registro concede
step_id: 3
step_title: Equipe da unidade
depends_on: [3.5-employee-login-link]
---

# Concept — Stage 3.8 — Desligamento corta só o acesso que o registro concede

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **R13 (`DeactivateEmployeeUseCase`) passa a revogar as sessões do login
  vinculado só quando o registro é a fonte do acesso**: o registro está ativo, a
  conta tem papel `employee` **e** nenhum outro registro **ativo da mesma
  unidade** aponta para ela
  ([ADR 3.8.0001](../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md)).
- **Staff:** lei nova **L-IG5** no `IdentityGateway` (`is_employee_login`), com
  as duas implementações (fake e `LocalIdentityGateway`) e o contrato fake × real.
  O "outro registro ativo da unidade" sai de `EmployeeRepository.list_by_unit`
  (L-E6), **sem método novo** no repositório.
- **Identity:** uma consulta **somente-leitura** atrás da fachada —
  `GetAccountRoleCommand`, `AccountRoleResult`, `GetAccountRoleUseCase` e
  `IdentityFacade.account_role` — e o wiring no `composition_root`.
- **Registro da decisão:** ADR 3.8.0001 (supersessão parcial do ADR 3.5.0003 §1
  e da metade "decidir se o desligamento a chama" do §5), com nota datada no
  3.5.0003 e no workforce §3.8; docstrings que ficariam falsas atualizadas
  (§8).
- **Testes que travam os casos (a) e (b) da issue #60**, em unit (fakes), em
  contrato e em e2e contra Postgres. Os testes de R13 da 3.5 são **rearranjados**
  (o login passa a ser provisionado pelo fake); nenhuma asserção de
  comportamento deles some sem substituta. **Uma expectativa é invertida:**
  `test_desligar_duas_vezes_um_vinculado_revoga_duas_vezes_sem_erro` assere
  duas revogações e passa a asserir uma (D3); a substituta é o CA12.

### Fora do escopo (explicitamente)

- **Vincular / desvincular login existente** (concept 3.5 §10). Os casos (a) e
  (b) só são produzíveis hoje por arranjo direto no banco.
- **`User.is_active` / desativação de conta.** A 3.8 só decide que o desligamento
  **nunca** a chama (ADR 3.8.0001 §4); criá-la continua com o gatilho do ADR
  3.5.0003 §5.
- **Olhar registros de outras unidades** (sponsor, §13 Q4) e **revogação por
  escopo de unidade** (ADR 3.8.0001 Alt. C e D).
- **R15** (`DeleteEmployeeUseCase`) — inalterado.
- **Unit of Work** (#46).

### Divergências declaradas em relação ao PIPELINE

- **PIPELINE §4.2 #1(b) e #4 (fatia vertical em um BC; sem deliverables em mais
  de um BC).** A Stage entrega em staff e acrescenta uma consulta somente-leitura
  em identity. **Autorizada pelo sponsor** (§13 Q3). O custo evitado é um ciclo
  de PR a mais para um use case sem consumidor até a Stage seguinte — o mesmo
  argumento da 3.5 (concept 3.5 §13 Q6).
- **Mais uma expansão de camada para trás no BC staff.** A 3.8 altera o use case
  R13 (3.2) e o port `IdentityGateway` (3.5). A série já é `[finding]` da 3.6 para
  a retrospectiva do Step 3; esta entra nela, declarada.

### Vínculo com o roadmap

Step 3 — Equipe da unidade. A 3.5 entregou "criar login para o funcionário" e o
corte de acesso no desligamento; a 3.8 corrige o alcance desse corte **antes**
de a primeira conta ter mais de um vínculo ou um vínculo de papel diferente de
`employee` (condição de disparo da issue #60). Promovida da issue #60 pelo
critério de PIPELINE §4.5 (contrato de port novo + trade-off que pede ADR).

## 2. Objetivo da Stage

Ao fechar a Stage, desligar um registro de funcionário corta as sessões do login
vinculado **se e somente se** o registro estava ativo, o login é de papel
`employee` e não há outro registro ativo da mesma unidade apontando para ele — e
isso está travado por teste nos cenários da issue #60 e no de um registro só.

## 3. Contexto e premissas

### Contexto

- Hoje (ADR 3.5.0003 §1) R13 revoga **todas** as sessões do login sempre que o
  registro tem `user_id`. Caminho: `deactivate_employee.py` →
  `IdentityGateway.revoke_login_sessions` → `IdentityFacade.revoke_all_sessions`
  → `RevokeAllSessionsUseCase`.
- A premissa daquele ADR — toda conta vinculada é `employee` com um registro —
  deixa de valer com "vincular login existente": **(a)** conta `employee` com
  dois registros (workforce §3.1, §3.8; ADR 3.1.0001 iii); **(b)** login de
  gerente/dono vinculado a um registro de escala (concept 3.5 §4, §10).
- **Revogar não tranca ninguém do lado de fora:** a conta permanece e a pessoa
  pode logar de novo (ADR 3.5.0003 §3). O custo de uma revogação indevida é uma
  sessão interrompida e um login a mais — é o que torna aceitáveis os casos
  residuais (§10).
- Issue #60 pede a decisão em ADR, testes que travem (a) e (b), e decidir
  **junto** o acoplamento com `is_active`.

### Premissas

- **O papel da conta é fixo** (`User.role`, "papel fixo de acesso"): não muda
  entre a consulta e a revogação.
- **Conta desconhecida não tem sessão** a revogar: `is_employee_login` responder
  `False` para ela não deixa sessão viva.
- **Um login só alcança registros do próprio tenant** porque R17 provisiona no
  tenant do registro e a cópia não carrega `user_id`. Não há guarda que imponha
  isso a um vínculo futuro — vira `[finding]` para "vincular login existente".

### Dependências

- `3.5-employee-login-link`: `IdentityGateway` (L-IG1…L-IG4), `IdentityFacade`,
  `RevokeAllSessionsUseCase`, `Employee.user_id`, R13 revogando antes de gravar,
  e2e CA24.
- `3.2`/`3.3`/`3.4`: `EmployeeRepository.list_by_unit` (L-E6, só ativos por
  default) e `find_by_id`, fake e Postgres.
- `2.2`/`2.3`: `UserRepository.find_by_id`.

## 4. Contratos

### Introduzidos

- **`IdentityGateway.is_employee_login`** (`port-out`, staff)

  ```python
  def is_employee_login(self, user_id: UserId) -> bool: ...
  ```

  **L-IG5** — `True` se e somente se identity conhece o login **e** o papel dele
  é o de funcionário. Login desconhecido ⇒ `False`, não erro. Qualquer outra
  falha sobe **crua** (mesma instância), pelo raciocínio de L-IG2 — devolver
  `False` numa falha seria *fail-open* (o desligamento gravaria com sessão viva).
  Não recebe nem devolve vocabulário de identity.

- **`IdentityFacade.account_role`** (fachada, identity)

  ```python
  def account_role(self, user_id: str) -> str | None: ...
  ```

  Primitivos, como toda a fachada: o valor do papel (`Role.value`) ou `None`
  para conta desconhecida. Não traduz exceção nem autoriza (ADR 3.5.0001).

- **`GetAccountRoleUseCase`** (use case, identity) —
  `execute(GetAccountRoleCommand) -> AccountRoleResult | None`, sobre
  `UserRepository.find_by_id`; só leitura. Forma `command → result` do ADR
  0.0.0006; é o **primeiro** use case a devolver `Result | None` — espelha
  `UserRepository.find_by_id -> User | None`, porque "não existe" aqui não é
  erro (L-IG5).
  - `GetAccountRoleCommand(user_id: UserId)` em `dtos/commands.py` (o nome
    `*Command` para consulta segue `AuthorizeActionCommand`).
  - `AccountRoleResult(role: Role)` em `dtos/results.py` — o enum, como
    `UserResult.role` e `AuthorizedActor.role`; a conversão para `str` é da
    fachada (propriedade 1 do `facade.py`).

### Consumidos

- **`IdentityGateway.revoke_login_sessions`** (L-IG4) — 3.5, inalterado.
- **`EmployeeRepository.find_by_id` / `list_by_unit` / `update`** — inalterados.
- **`UserRepository.find_by_id`** — 2.2/2.3.
- **`IdentityFacade`** — 3.5 (ganha a quarta operação).

## 5. Invariantes e regras

1. **Regra de revogação do R13** (ADR 3.8.0001 §1). Com `u = employee.user_id`:
   revoga se e somente se `employee.active` **e** `u is not None` **e** nenhum
   registro de `list_by_unit(tenant, unit)` (só ativos) tem `user_id == u` e id
   diferente de `employee.id` **e** `is_employee_login(u)`.
2. **Ordem** (ADR 3.8.0001 §2): `find_by_id` → `list_by_unit` →
   `is_employee_login` → `revoke_login_sessions` → `update`. Cada passo só roda
   se o anterior pedir: registro já desligado ou sem login ⇒ nenhuma das três
   chamadas; outro registro ativo do login na unidade ⇒ nenhuma chamada ao
   gateway; papel ≠ `employee` ⇒ nenhuma revogação.
3. **Tudo antes da escrita** (ADR 3.5.0003 §2, mantido): falha em qualquer uma
   das três chamadas deixa o registro **ativo** e a requisição falha inteira.
4. **Desligar de novo um desligado** não toca identity (o `update` idempotente da
   3.2 continua).
5. **O desligamento nunca desativa a conta** (ADR 3.8.0001 §4). Não tem critério
   de aceite próprio: a desativação ainda não existe; o que se trava é a ausência
   de qualquer chamada além das três de §5.2.
6. **A conta permanece** e o `user_id` permanece no registro (ADR 3.5.0003 §3).
7. **Fronteira:** staff continua sem nomear `Role`/`Permission` (varredura do
   CA07 da 3.5, herdada do CA12 da 3.4); o literal `"employee"` continua só no
   `LocalIdentityGateway`. A aresta staff → identity continua sendo **uma**.

## 6. Casos de erro e exceções

| Cenário | Comportamento |
|---|---|
| Registro inexistente no endereço | `EmployeeNotFoundError` (404); só `find_by_id` é chamado |
| `list_by_unit` falha (banco) | Sobe; nada gravado |
| `is_employee_login` falha (identity) | Sobe **crua** (L-IG5); nada gravado |
| `is_employee_login` com login desconhecido | `False` ⇒ sem revogação; desligamento grava |
| `revoke_login_sessions` falha | Sobe crua (como hoje); nada gravado |
| Desligar registro já desligado | Nenhuma chamada nova; `update` idempotente como hoje |
| Nova tentativa depois de falha na escrita | Registro ainda ativo ⇒ regra roda de novo, revoga de novo (L-IG4) |

Nenhuma exceção nova; o mapa `STAFF_ERROR_STATUS` não muda.

## 7. Decisões técnicas relevantes

### D1 — Revogar só quando o registro é a fonte do acesso
- **O quê:** a regra §5.1.
- **Por quê:** cobre (b) e (a) dentro da unidade; "só último vínculo", "nunca
  revogar" e "por escopo" deixam um dos casos aberto ou custam uma Stage de
  identity.
- **Fonte:** sponsor, §13 Q1; issue #60 §Incerteza.
- **ADR:** 3.8.0001 §1, Alt. A, B, D.

### D2 — "Outro registro ativo" só na mesma unidade, via `list_by_unit`
- **O quê:** a checagem lê `list_by_unit(tenant, unit)`; nenhum método novo no
  repositório.
- **Por quê:** o sponsor manteve literal o workforce §3.1 ("nenhuma operação de
  staff atravessa unidades implicitamente"). Na unidade, `list_by_unit` já
  devolve só ativos (L-E6) e já tem as duas implementações sob contrato; um
  método dedicado repetiria a lei sem ganho.
- **Fonte:** sponsor, §13 Q4; `employee_repository.py` (L-E6).
- **ADR:** 3.8.0001 §1, Alt. C.

### D3 — Só registro ativo dispara a regra
- **O quê:** `employee.active` é a primeira condição.
- **Por quê:** a conta permanece e a pessoa pode ter logado de novo depois do
  primeiro desligamento; um duplo clique não deve derrubar essas sessões. A nova
  tentativa depois de falha continua segura (revogar vem antes de gravar).
- **Fonte:** achado do Checkpoint A (domínio #2); ADR 3.5.0003 §2–§3.
- **ADR:** 3.8.0001 §1.

### D4 — Cada BC responde pelo fato que detém; a política fica no R13
- **O quê:** staff lê a unidade e pergunta "conta `employee`?" ao gateway; a
  decisão de revogar é do use case.
- **Por quê:** a regra do papel dentro da revogação de identity esconderia uma
  política de staff numa operação "idempotente e total" (L-IG4).
- **Fonte:** ADR 3.8.0001 §3, Alt. E.

### D5 — O port devolve booleano, não o papel
- **O quê:** `is_employee_login -> bool`; o literal `"employee"` fica no adapter.
- **Por quê:** mantém `Role` fora de staff (CA07 da 3.5 / CA12 da 3.4).
- **Fonte:** ADR 3.8.0001 Alt. F; `local_identity_gateway.py` (`_EMPLOYEE_ROLE`).

### D6 — Desligar nunca desativa a conta
- **O quê:** quando a desativação de conta existir, é ato separado de identity.
- **Fonte:** sponsor, §13 Q2.
- **ADR:** 3.8.0001 §4, Alt. G.

### D7 — A corrida entre dois desligamentos simultâneos fica declarada, não fechada
- **O quê:** sem re-checagem depois da escrita.
- **Por quê:** fechar a corrida reintroduz o sucesso parcial escondido atrás de
  500 que o ADR 3.5.0003 §2 existe para evitar; o caso não é produzível hoje e,
  quando ocorrer, as sessões vivas não alcançam nada (o registro está
  desligado).
- **Fonte:** `[decision:C]`, degrau 4 (reversível).
- **Dono:** a Stage que implementar "vincular login existente" — a que torna o
  caso produzível —, com lock por `user_id`. Uma unidade de trabalho sozinha não
  fecha (*write skew* sob `READ COMMITTED`), e a 2.6 (#46) deixa
  `deactivate_employee` fora da unidade. *Corrigido em 2026-11-01 (auditoria da
  Stage, F5 — technical §7): a versão anterior apontava a #46.*
- **ADR:** 3.8.0001 Alt. H, §Negative.

### D8 — Sem `gate_mode: batch`
- **O quê:** `strict` — mexe num port com contrato e numa regra de acesso.

## 8. Integrações

### Internas
- **identity ← staff:** a mesma aresta da 3.5 (`staff.adapters.out.identity.*
  → identity.application.facade`), sem par novo no `.importlinter`.
- **composition_root:** constrói `GetAccountRoleUseCase` sobre o mesmo
  `UserRepository` das rotas de identity e o passa à fachada (um grafo, não dois).
- **Docstrings e doc que ficariam falsos, atualizados nesta Stage:**
  `deactivate_employee.py` (módulo), `identity_gateway.py` ("três operações",
  "quatro leis"), `facade.py` ("três use cases", "três operações"),
  `revoke_all_sessions.py` (módulo), `staff/application/errors.py`
  (`EmployeeHasLoginError`: "desligar (R13), que revoga as sessões"),
  `composition_root.py` (comentário "Os três use cases da fachada"),
  `tests/contract/features/staff/test_identity_gateway_laws.py` (docstring "As
  quatro leis"), `docs/domain/staff/workforce.md` §3.8 (nota datada).

### Externas
- Nenhuma.

## 9. Modelo de dados

Sem mudança de schema, migration ou índice.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Fake e real divergirem em L-IG5 (desconhecido, cada papel, falha) | M | A | Contrato fake × real, papéis parametrizados, arranjo de falha nos dois lados |
| Uma condição sumir num refactor e a suíte continuar verde | M | A | Unit por cenário + mutação real (CA21) |
| Filtro por `user_id` sumir (qualquer outro ativo bloquear a revogação) | M | A | CA09: outro ativo com **outro** login e sem login na unidade ⇒ revoga |
| e2e passar por reuso de refresh, não pela revogação | A | A | e2e apresenta sempre o refresh **rotacionado** (CA16–CA18) |
| e2e não alcançar (a)/(b) sem a rota de vínculo | A | M | Arranjo por `UPDATE` direto, declarado no teste e no ADR |
| **Residual:** caso (a) entre unidades revoga | — | B | Aceito pelo sponsor (§13 Q4); custa um login |
| **Residual:** corrida entre dois desligamentos da mesma unidade | B | B | Declarada (D7); fecha a Stage de "vincular login existente", com lock por `user_id` (não a #46 — F5, technical §7) |
| Conflito de `roadmap.md` com a 4.2 em paralelo | A | B | Rebase em `origin/develop` antes do push |

## 11. Critérios de aceitação

### Identity
- [x] **CA01** — `GetAccountRoleUseCase` devolve `AccountRoleResult(role=r)`
  para uma conta de cada um dos **cinco** papéis (parametrizado sobre `Role`) e
  `None` para id desconhecido; não altera o repositório.
- [x] **CA02** — `IdentityFacade.account_role(user_id)` delega convertendo
  `str` → `UserId` e devolve o valor ou `None`; uma exceção do repositório
  atravessa a fachada como é (mesma instância).

### Staff — port e contrato
- [x] **CA03** — L-IG5 no contrato (fake **e** real, mesmo corpo): login
  provisionado por `provision_employee_login` ⇒ `True`; login de cada papel
  diferente de `employee` (`owner`, `manager`, `hr`, `platform_admin`,
  parametrizado) ⇒ `False`; id desconhecido ⇒ `False`, sem exceção; falha da
  consulta em identity ⇒ sobe a **mesma instância**.
- [x] **CA04** — "L-IG5" está no docstring do `IdentityGateway` (o teste
  parametrizado de lei documentada a inclui).

### Staff — use case (fakes)
- [x] **CA05** — Registro ativo, login `employee`, único na unidade: a ordem no
  ledger único é `employees.find_by_id` → `employees.list_by_unit` →
  `gateway.is_employee_login` → `gateway.revoke_login_sessions` →
  `employees.update`.
- [x] **CA06** — Caso (a): outro registro **ativo** da mesma unidade com o mesmo
  login ⇒ **nenhuma** chamada ao gateway; o registro é gravado desligado.
- [x] **CA07** — O outro registro da unidade com o mesmo login está desligado ⇒
  revoga.
- [x] **CA08** — O outro registro ativo com o mesmo login está em **outra
  unidade** ⇒ revoga (decisão §13 Q4 travada).
- [x] **CA09** — A unidade tem outros registros ativos com **outro** login e
  **sem** login ⇒ revoga (o filtro é por `user_id`).
- [x] **CA10** — Caso (b): login de papel ≠ `employee`, registro único ⇒
  `is_employee_login` chamado, **sem** revogação; registro gravado desligado.
- [x] **CA11** — Login desconhecido de identity ⇒ sem revogação; registro gravado.
- [x] **CA12** — Registro já desligado, com login ⇒ nenhuma das três chamadas;
  `employees.update` como hoje.
- [x] **CA13** — Falha em `list_by_unit`, em `is_employee_login` ou em
  `revoke_login_sessions` sobe (mesma instância) e deixa o registro **ativo**
  (nenhum `employees.update`).
- [x] **CA14** — Registro sem login: só `find_by_id` e `update`.
- [x] **CA15** — Registro inexistente: só `find_by_id` (nenhuma chamada nova).

### Fluxo (e2e contra Postgres)
- [x] **CA16** — Caso (a): login `employee` criado por R17 no registro A; o
  registro B, da **mesma** unidade, recebe o mesmo `user_id` por `UPDATE`
  direto; o funcionário loga. Desligar A ⇒ `POST /auth/refresh` responde **200**;
  com o refresh **rotacionado** dessa resposta, desligar B ⇒ o refresh seguinte
  responde **401**.
- [x] **CA17** — Caso (a) entre unidades: B está em **outra** unidade; desligar A
  ⇒ o refresh responde **401** (Q4 travada de ponta a ponta).
- [x] **CA18** — Caso (b): o gerente do cenário (logado) tem o `user_id` posto
  num registro de escala por `UPDATE` direto; desligar o registro ⇒ o refresh do
  gerente responde **200** e, com o access novo, listar funcionários da unidade
  responde **200**.
- [x] **CA19** — CA24 da 3.5 continua passando **sem edição**.

### Documentação e gates
- [x] **CA20** — ADR 3.8.0001 `accepted`; ADR 3.5.0003 com `## Supersessão
  parcial` datada (corpo intocado, `updated_at` bumpado); nota datada no
  workforce §3.8; as docstrings de §8 não afirmam mais revogação incondicional
  nem "três operações".
- [x] **CA21** — Mutação real, cada uma derruba ao menos um teste (saída colada):
  remover a checagem da unidade; remover `is_employee_login`; remover a guarda
  `employee.active`; trocar o literal de papel comparado no adapter; ignorar o
  `user_id` no filtro da unidade.
- [x] **CA22** — `make check` verde; cobertura ≥ 90% em cada arquivo de `src/`
  tocado; `lint-imports` sem par novo em `bc-independence`.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido? (não há)
- [x] Decisões com alternativa real descartada têm ADR escrito? (3.8.0001)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.5 done)
- [x] Stage cabe em ~3–12 Tasks? (estimativa: 6)
- [x] Riscos críticos têm mitigação plausível?
- [x] Os casos (a) e (b) da issue #60 têm, cada um, critério unit **e** e2e?
  (CA06/CA16, CA10/CA18)

## 13. Questões em aberto

Todas decididas pelo sponsor em 2026-10-19.

### Q1 — Em que caso o desligamento revoga as sessões? — **DECIDIDA**
**Papel `employee` + último vínculo ativo** (contra "só último vínculo" e "nunca
revogar"). ADR 3.8.0001 §1.

### Q2 — O desligamento chama a desativação de conta quando ela existir? — **DECIDIDA**
**Nunca** (contra "mesma condição da revogação" e "deixar para o Step 4"). ADR
3.8.0001 §4. Levada ao sponsor como P depois do Checkpoint A (conformidade #1),
que contestou fechá-la por evidência.

### Q3 — A 3.8 pode entregar nos dois BCs? — **DECIDIDA**
**Sim**, na própria Stage (contra "issue de identity antes"). §1 Divergências.

### Q4 — "Outro registro ativo" olha outras unidades do tenant? — **DECIDIDA**
**Só a mesma unidade** (contra "exceção ao workforce §3.1"). Consequência
aceita: caso (a) entre unidades revoga e custa um login. ADR 3.8.0001 §1, Alt. C.

## 14. Referências

- [`../../roadmap.md`](../../roadmap.md) — Stage `3.8-termination-access-scope`
- [ADR 3.8.0001](../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md)
- [ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md),
  [3.5.0001](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md),
  [3.5.0004](../../adr/3_5_0004-user-id-as-nullable-opaque-column.md),
  [0.0.0006](../../adr/0_0_0006-primary-ports-are-the-use-case-classes.md)
- [`../3.5-employee-login-link/concept.md`](../3.5-employee-login-link/concept.md) §4, §10, §13 Q6, CA07
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) §3.1, §3.8, §3.8
- Issue #60

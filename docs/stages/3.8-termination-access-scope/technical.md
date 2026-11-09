---
title: Technical — Desligamento corta só o acesso que o registro concede
description: Plano de execução da Stage 3.8 — 6 Tasks (1 Task = 1 commit) que tornam a revogação de sessões do R13 condicional ao registro ser a fonte do acesso, com uma consulta somente-leitura nova na fachada de identity e a lei L-IG5 no gateway de staff
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem arquivos, critério de aceite e comando de verificação; consultar a §7 para o que aconteceu de fato
keywords: [technical, plano de execução, termination-access-scope, desligamento, revogacao, identity-gateway, facade, staff, identity]
status: done
created_at: 2026-10-19
updated_at: 2026-11-01
stage_id: 3.8-termination-access-scope
stage_title: Desligamento corta só o acesso que o registro concede
step_id: 3
step_title: Equipe da unidade
depends_on: [3.5-employee-login-link]
concept_ref: ./concept.md
issue_id: 60
branch: feat/60-3-7-termination-access-scope
tasks_count: 6
---

# Technical — Stage 3.8 — Desligamento corta só o acesso que o registro concede

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro a §1, em especial **"As totalidades ditam o recorte"**.
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Re-hidratar a Task e as §4/§5/§11 do [`concept.md`](./concept.md) antes de
>    implementar — nunca de memória.
> 4. Baseline: **`make check` verde antes de todo commit**, além dos checks da Task.
> 5. Commit: `<type>(<scope>): <descrição> [3.7/task-NN]` + `Refs #60`.
> 6. O que não estiver previsto em §1–§6 ou no concept: pausar, perguntar com
>    opções e recomendação, registrar na §7.

## 1. Contexto e estratégia de execução

### Resumo

R13 deixa de revogar incondicionalmente. Identity ganha uma consulta de leitura
(`GetAccountRoleUseCase` → `IdentityFacade.account_role`); o `IdentityGateway`
de staff ganha `is_employee_login` (L-IG5) com contrato fake × real; o use case
lê a unidade com `list_by_unit` e só revoga quando o registro está ativo, é o
único ativo do login na unidade e o login é `employee`. E2e trava os casos (a),
(a) entre unidades e (b) contra Postgres.

### Estratégia

Inside-out (skill `task-ordering-hex`): identity (DTO + use case) → fachada e
wiring → port + implementações + contrato → use case → e2e → doc de domínio.
Cada Task deixa o build verde: o use case novo de identity nasce sem consumidor
por um commit (T01) e é ligado na T02; o método novo do port só passa a ser
chamado na T04.

### As totalidades ditam o recorte

Varreduras que reprovam mudança incremental, e a Task que leva a entrada:

| Varredura | Onde | Task |
|---|---|---|
| `_TOTAL_DE_DTOS = 25` (todo DTO de identity é `frozen`) | `tests/unit/features/identity/application/test_dtos.py` | T01 (→ 27) |
| `_RESULT_CLASSES` (dataclasses de `results.py` = tupla exata; varredura de segredo/entidade) | `test_dtos.py` › `_RESULT_CLASSES`, `test_nenhum_result_expoe_senha_hash_ou_entidade`, `test_modulo_de_results_declara_exatamente_os_esperados` | T01 |
| Gate 8: cada classe de `results.py` construída em exatamente 1 sítio | `scripts/check_layout.py` regra 8 | T01 (o use case é o sítio) |
| Toda construção de `IdentityFacade(...)` (posicional) | `composition_root.py`, `tests/contract/features/staff/conftest.py`, `tests/unit/features/identity/application/test_facade.py` (2×) | T02 |
| Identidade dos colaboradores da fachada × deps | `tests/unit/features/staff/adapters/test_composition_root_staff.py` › `test_ca07_o_gateway_de_identity_e_o_local_sobre_a_fachada_das_rotas` | T02 |
| Estrutura do `Protocol`: `LocalIdentityGateway` e o fake passados como `IdentityGateway` (mypy) | `composition_root.py`, contrato, unit | T03 (port + duas implementações juntos) |
| Lei documentada no port, parametrizada | `test_identity_gateway_laws.py::test_a_lei_esta_documentada_no_port` | T03 |
| Nenhum `if` sobre implementação no corpo do contrato | `test_no_implementation_branching.py` | T03 (arranjos no holder) |
| Ordem exata de `store.calls` nos testes de R13 | `test_employee_lifecycle.py` | T04 |

**Exceção declarada ao critério 4 de Task atômica (PIPELINE §4.3):** a T03 cria
o método no port **e** nas duas implementações. Com `Protocol` estrutural, um
port com método que o `LocalIdentityGateway` não tem reprova o mypy no
`composition_root`; o fake é exigido pelo contrato (que roda o mesmo corpo nos
dois). É a mesma mudança propagada, não escopo (precedente: 3.5).

### Pré-condições
- Stage `3.5-employee-login-link` `done` e mergeada (✔ `develop` em `2c71615`).
- Postgres da worktree no ar (porta 5436) e `DATABASE_URL` no `.env` dela.

### Premissas técnicas
- `InMemoryUserRepository.add(user, hash, memberships)` semeia contas de
  qualquer papel; `Role` tem 5 membros (`role.py`); `UserId` de identity é
  `NewType` de `str` (sem validação na conversão).
- O fake `InMemoryIdentityGateway` tem `mirror` para ledger único com o store.
- O `cenario` do e2e de staff tem duas unidades e um gerente membro das duas.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                   (T02)
├── features/identity/application/
│   ├── dtos/{commands,results}.py                        (T01)
│   ├── use_cases/get_account_role.py                     (T01, novo)
│   ├── use_cases/revoke_all_sessions.py                  (T02, docstring)
│   └── facade.py                                         (T02)
└── features/staff/
    ├── application/ports/out/identity_gateway.py         (T03)
    ├── application/use_cases/deactivate_employee.py      (T04)
    ├── application/errors.py                             (T04, docstring)
    └── adapters/out/identity/local_identity_gateway.py   (T03)
tests/
├── unit/features/identity/application/{test_get_account_role,test_dtos,test_facade}.py
├── unit/features/staff/adapters/test_composition_root_staff.py
├── unit/features/staff/application/test_employee_lifecycle.py
├── fakes/features/staff/in_memory_identity_gateway.py
├── contract/features/staff/{conftest,test_identity_gateway_laws}.py
└── e2e/features/staff/test_employee_login_flow.py
docs/domain/staff/workforce.md                            (T06)
```

## 2. Tasks

### Task 01 — Identity: `GetAccountRoleUseCase` e seus DTOs

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/get_account_role.py`
  - `tests/unit/features/identity/application/test_get_account_role.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/dtos/commands.py` (`GetAccountRoleCommand(user_id: UserId)`, frozen)
  - `src/restaurant_hub/features/identity/application/dtos/results.py` (`AccountRoleResult(role: Role)`, frozen)
  - `tests/unit/features/identity/application/test_dtos.py` (`_TOTAL_DE_DTOS` 25 → 27, comentário da série; `AccountRoleResult` em `_RESULT_CLASSES` e no docstring de `test_modulo_de_results_declara_exatamente_os_esperados`)
- **O que fazer:** use case `GetAccountRoleUseCase(users: UserRepository)` com
  `execute(command) -> AccountRoleResult | None`: `users.find_by_id`; `None` se
  ausente, senão `AccountRoleResult(role=user.role)`. Docstring do módulo: nasce
  para a fachada (ADR 3.8.0001 §3), só leitura, "não existe" não é erro.
- **Critério de aceite:** CA01 — parametrizado sobre os 5 membros de `Role`
  (platform_admin com `tenant_id=None`); id desconhecido ⇒ `None`; o repositório
  fake não muda (contas e memberships iguais antes/depois); exceção do
  repositório em `find_by_id` sobe na mesma instância.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_get_account_role.py tests/unit/features/identity/application/test_dtos.py -q
  make check
  ```
- **Commit sugerido:** `feat(identity): consulta do papel da conta para a fachada [3.7/task-01]`

---

### Task 02 — Identity: `IdentityFacade.account_role` e wiring

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/facade.py` (4º colaborador `get_account_role`; método `account_role(user_id: str) -> str | None`, devolve `result.role.value`; docstrings "três" → "quatro")
  - `src/restaurant_hub/composition_root.py` (constrói `GetAccountRoleUseCase(users=users)`; comentário "Os três use cases da fachada")
  - `src/restaurant_hub/features/identity/application/use_cases/revoke_all_sessions.py` (docstring do módulo: **o consumidor decide quando chamar** — ver ADR 3.8.0001; redação válida antes e depois da T04)
  - `tests/unit/features/identity/application/test_facade.py` (espião do 4º use case para a delegação e o `None`; e, em `_fachada_real`, um `InMemoryUserRepository` armado em `find_by_id` para provar que a exceção **do repositório** atravessa use case e fachada na mesma instância)
  - `tests/contract/features/staff/conftest.py` (`_gateway_real` constrói a fachada com o 4º use case — sem lei nova ainda)
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py` (o use case da fachada usa o **mesmo** `users` das rotas de identity)
- **Detalhes técnicos:** o novo colaborador entra como **último** parâmetro do
  construtor, para não reordenar os posicionais existentes; `__all__` da fachada
  não muda.
- **Critério de aceite:** CA02; identidade do `users` asserida no composition root.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_facade.py tests/unit/features/staff/adapters/test_composition_root_staff.py -q
  make check
  ```
- **Commit sugerido:** `feat(identity): expor o papel da conta na fachada [3.7/task-02]`
- **Nota:** 6 arquivos — a mesma mudança de assinatura propagada (ver §1).

---

### Task 03 — Staff: lei L-IG5 `is_employee_login` no port, nas duas implementações e no contrato

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/ports/out/identity_gateway.py` (método + L-IG5 no docstring; "três operações"/"quatro leis" → quatro/cinco)
  - `src/restaurant_hub/features/staff/adapters/out/identity/local_identity_gateway.py` (`account_role(str(user_id)) == _EMPLOYEE_ROLE`; nada de `try`)
  - `tests/fakes/features/staff/in_memory_identity_gateway.py` (`other_role_logins: set[UserId]`, `fail_role_query_with: Exception | None`; `True` sse em `logins` e fora de `other_role_logins`; `record("is_employee_login(...)")`). O arranjo de "login de outro papel" no fake grava o id **em `logins` e em `other_role_logins`** — é `other_role_logins` que decide o `False`, não a ausência (senão o caso colapsa no "desconhecido" e remover a checagem não derruba teste)
  - `tests/contract/features/staff/conftest.py` (holder ganha **arranjos** `login_de_outro_papel(papel: str) -> UserId` e `consulta_de_papel_falha(exc)`; real: semeia `User` do papel em `users` e subclasse de `InMemoryUserRepository` armável; fake: ledger/knob; `login_role_of` do fake passa a responder pelo ledger de outro papel)
  - `tests/contract/features/staff/test_identity_gateway_laws.py` (testes L-IG5; `"L-IG5"` na parametrização de lei documentada; docstring do módulo "cinco leis")
- **Detalhes técnicos:** o papel do arranjo é passado como **valor** (`"owner"`,
  `"manager"`, `"hr"`, `"platform_admin"`), nunca `Role` — o corpo de contrato é
  de staff. No real, `platform_admin` nasce com `tenant_id=None`. Falha da
  consulta: a mesma instância sobe nos dois lados (`is`).
- **Critério de aceite:** CA03, CA04; `test_no_implementation_branching.py`
  verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/staff/test_identity_gateway_laws.py tests/contract/features/staff/test_no_implementation_branching.py -q
  make check
  ```
- **Commit sugerido:** `feat(staff): lei L-IG5 — consultar se o login é de funcionário [3.7/task-03]`
- **Nota:** port + duas implementações no mesmo commit — exceção declarada na §1.

---

### Task 04 — Staff: R13 revoga só quando o registro é a fonte do acesso

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/use_cases/deactivate_employee.py` (regra concept §5.1–§5.2; docstrings)
  - `src/restaurant_hub/features/staff/application/errors.py` (docstring de `EmployeeHasLoginError`)
  - `tests/unit/features/staff/application/test_employee_lifecycle.py` (rearranjo + CA05–CA15)
- **O que fazer:**
  ```
  employee = find_by_id(...)            # 404 como hoje
  if employee.active and employee.user_id is not None and self._is_source_of_access(employee):
      gateway.revoke_login_sessions(employee.user_id)
  update(employee.deactivate())
  ```
  `_is_source_of_access`: nenhum `other` em `list_by_unit(tenant, unit)` com
  `other.user_id == employee.user_id and other.id != employee.id`, **e só então**
  `gateway.is_employee_login(user_id)` (curto-circuito: D4 do concept).
- **Detalhes técnicos (testes):**
  - `_fakes_com_login()` passa a obter o `user_id` de
    `gateway.provision_employee_login(...)` do **mesmo** fake que o use case
    recebe; o login entra como `employee` pelo ledger.
  - `test_desligar_duas_vezes_um_vinculado_revoga_duas_vezes_sem_erro` vira
    "desligar duas vezes revoga uma vez" (expectativa invertida — concept §1).
  - Falha em `list_by_unit`: subclasse local de `InMemoryEmployeeRepository`
    sobre o **mesmo** `fakes.store` (preserva o ledger e o holder); falha em
    `is_employee_login`: `fail_role_query_with`; em `revoke_login_sessions`: a
    subclasse `_GatewayQueFalha` que já existe.
  - Os outros registros dos cenários (mesma unidade, outra unidade, sem login,
    outro login, desligado) são semeados por `fakes.employees.add`/`update`.
- **Critério de aceite:** CA05–CA15.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff/application/test_employee_lifecycle.py -q
  make check
  ```
- **Commit sugerido:** `fix(staff): desligar revoga só o acesso que o registro concede [3.7/task-04]`

---

### Task 05 — E2e: casos (a), (a) entre unidades e (b) contra Postgres

- **Arquivos a modificar:**
  - `tests/e2e/features/staff/test_employee_login_flow.py` (três testes novos; helpers do módulo reaproveitados; CA24 intocado)
- **O que fazer:**
  - CA16: R17 (canal `link`) no registro A da unidade A; criar B na **mesma**
    unidade; `UPDATE employees SET user_id = :u WHERE id = :b`; definir senha e
    logar; desligar A ⇒ refresh 200 (guardar o token **rotacionado**); desligar
    B ⇒ refresh com o rotacionado 401.
  - CA17: B na unidade B; desligar A ⇒ refresh 401.
  - CA18: `SELECT id FROM users WHERE email = <e-mail do gerente do cenario>`;
    criar registro, `UPDATE` com esse `user_id`; desligar ⇒ refresh do gerente
    200 e listar funcionários da unidade com o access novo 200.
- **Critério de aceite:** CA16–CA19 (CA24 da 3.5 passa sem edição).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/e2e/features/staff/test_employee_login_flow.py -q
  make check
  ```
- **Commit sugerido:** `test(staff): travar no e2e o desligamento de login compartilhado e de gerente [3.7/task-05]`

---

### Task 06 — Doc de domínio: nota datada no workforce §3.8

- **Arquivos a modificar:**
  - `docs/domain/staff/workforce.md` (nota `> **Nota (2026-10-19)**` em §3.8 ajustando o bullet "Desligar corta o acesso"; `updated_at`)
- **Critério de aceite:** CA20 (parte do doc de domínio); `make docs-check` verde.
- **Comando de verificação:**
  ```bash
  make docs-check
  make check
  ```
- **Commit sugerido:** `docs(staff): registrar no workforce a revogação condicional do desligamento [3.7/task-06]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/3.8-termination-access-scope/technical.md
```

Cobertura por arquivo (CA22): conferir no `term-missing` cada arquivo de `src/`
tocado — `get_account_role.py`, `dtos/commands.py`, `dtos/results.py`,
`facade.py`, `composition_root.py`, `identity_gateway.py`,
`local_identity_gateway.py`, `deactivate_employee.py`. Lista derivável por
`git diff --name-only origin/develop...HEAD -- src/`.

### Mutações reais (CA21)

Aplicar uma por vez, rodar o alvo, reverter (`git checkout -- <arquivo>`); a saída
de cada uma vai para o relatório final (§4 da auditoria de testes).

| # | Mutação | Arquivo | Deve cair |
|---|---|---|---|
| M1 | remover a checagem da unidade (`_is_source_of_access` só consulta o gateway) | `deactivate_employee.py` | CA06 |
| M2 | remover `is_employee_login` (só a checagem da unidade) | `deactivate_employee.py` | CA10, CA11 |
| M3 | remover a guarda `employee.active` | `deactivate_employee.py` | CA12 |
| M4 | trocar `_EMPLOYEE_ROLE` comparado por `"manager"` | `local_identity_gateway.py` | CA03 (real) |
| M5 | ignorar `user_id` no filtro (qualquer outro ativo bloqueia) | `deactivate_employee.py` | CA09 |

### Verificações funcionais
- [ ] CA16–CA18 verdes contra o Postgres da worktree (o e2e é a superfície de
      runtime; o bloco §0 do relatório reproduz pela API).
- [ ] CA19: `git diff origin/develop...HEAD -- tests/e2e/features/staff/test_employee_login_flow.py`
      não toca as funções `test_ca24_*`.
- [ ] CA21: M1–M5 derrubam ao menos um teste cada.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Checkpoints A, B e C com achados dispostos; auditoria de testes por subagente
- [ ] Commit final `stage 3.7: complete`
- [ ] `roadmap.md`: Stage `done`, `updated_at` e `last_reviewed_at`
- [ ] ADR 3.8.0001 `accepted`
- [ ] `concept.md` sem retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
T01 ─► T02 ─► T03 ─► T04 ─► T05
T06 (independente; por último)
```

T03 depende da T02 porque o `LocalIdentityGateway` chama `account_role`.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Postgres compartilhado com a worktree da 4.2 | A worktree tem Postgres próprio (5436); nunca rodar e2e em paralelo com `make check` |
| Avast trava com o volume de processos do `make check` | Um `make check` por Task, nunca em paralelo |
| Gerente do `cenario` sem e-mail exposto no fixture | Ler o e-mail do docstring/código do `cenario`; se não for estável, criar o gerente no próprio teste por `POST /users` |

## 6. Referências

- [`./concept.md`](./concept.md)
- [ADR 3.8.0001](../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md)
- [`../../roadmap.md`](../../roadmap.md)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md)
- Skills: `hex-arch-python`, `pytest-with-fakes`, `composition-root`, `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-10-19 — [decision] Fase 3A — "outro registro ativo" só na unidade, via `list_by_unit` — Claude (Opus 5.5) com o sponsor
**Contexto:** o concept v1 previa uma lei nova no repositório (L-E8, `exists_other_active_with_login`) atravessando unidades do tenant. O Checkpoint A (conformidade #3) mostrou que isso abria exceção à regra de workforce §3.1, que é decisão de domínio.
**Pergunta:** a checagem olha outras unidades?
**Opções:**
- A — exceção ao workforce §3.1 (tenant-wide, L-E8)
- B — só a mesma unidade ✅ escolhida pelo sponsor
**Decisão:** B (concept §13 Q4).
**Razão:** mantém §3.1 literal; o custo (caso (a) entre unidades revoga) é um login a mais. Consequência técnica: sem método novo no repositório — a checagem lê `list_by_unit` (L-E6, só ativos), que já tem contrato fake × Postgres. Some a questão do índice.

### 2026-10-19 — [decision] Fase 3A — guarda `employee.active` antes da regra — Claude (Opus 5.5)
**Contexto:** Checkpoint A (domínio #2): reavaliar a regra ao desligar de novo um desligado derrubaria sessões que a pessoa abriu depois do primeiro desligamento (a conta permanece).
**Decisão:** só registro ativo dispara a regra (concept D3, ADR 3.8.0001 §1). A nova tentativa depois de falha na gravação continua segura — o registro segue ativo; travado por `test_nova_tentativa_depois_de_falha_na_gravacao_revoga_de_novo`.
**Razão:** ADR 3.5.0003 §3 (a conta permanece) + intenção do sponsor (D6).

### 2026-10-19 — [decision] Fase 3A — corrida entre dois desligamentos simultâneos fica declarada — Claude (Opus 5.5)
**Contexto:** dois R13 concorrentes sobre dois registros da mesma unidade do mesmo login podem, cada um, ver o outro ativo — nenhum revoga.
**Opções:**
- A — re-checar depois da escrita e revogar se preciso
- B — declarar como residual ✅
**Decisão:** B — `[decision:C]`, degrau 4.
**Razão:** A reintroduz o sucesso parcial atrás de 500 que o ADR 3.5.0003 §2 evita e, com a guarda `active`, a nova tentativa não revogaria. O caso não é produzível hoje e as sessões vivas não alcançam nada (registro desligado). ADR 3.8.0001 Alt. H.

### 2026-10-19 — [deviation] Task 04 — teste extra de nova tentativa — Claude (Opus 5.5)
`test_nova_tentativa_depois_de_falha_na_gravacao_revoga_de_novo` não estava na lista CA05–CA15; cobre a última linha da tabela do concept §6. Mesmo arquivo da Task, sem contrato novo.

### 2026-10-19 — [deviation] Checkpoint C — duas docstrings fora da lista do concept §8 — Claude (Opus 5.5)
`employee.py` (`TerminatedEmployeeLoginError`) e o comentário do mapa em `error_handlers.py` diziam "desligar cortou" sem qualificar. No bloco T01–T03 marquei como refutado (falam do **registro**); o revisor do bloco T04–T06 mostrou que a leitura pós-3.8 sugere corte incondicional — disposição revertida para corrigido (`[3.7/task-04-fix]`).

### 2026-10-19 — [finding] staff — "vincular login existente" precisa checar o tenant do `User` — Claude (Opus 5.5)
**Contexto:** `is_employee_login` não recebe tenant; hoje um login só alcança registros do próprio tenant porque R17 provisiona no tenant do registro e a cópia não carrega `user_id`. Não há guarda que imponha isso a um vínculo futuro (`employees.user_id` sem FK — ADR 3.5.0004).
**Direção sugerida:** a operação de vínculo recusa `User` de outro tenant (e `platform_admin`).
**Stage candidata:** a que implementar "vincular login existente" (concept 3.5 §10; `4.3-scheduling-application` ou Stage de gestão de acesso anterior).

### 2026-10-19 — [finding] staff — toda operação que encerra um vínculo ativo herda a regra — Claude (Opus 5.5)
**Contexto:** ADR 3.8.0001 §5: hoje R13 é o único caminho que encerra o vínculo ativo de um registro. "Desvincular" / "trocar login" criarão outro.
**Direção sugerida:** extrair a regra (unidade + papel) para um ponto único quando o segundo caminho nascer, em vez de duplicar.
**Stage candidata:** a mesma do finding anterior.

### 2026-10-19 — [finding] shared — corrida de desligamentos concorrentes reforça a #46 — Claude (Opus 5.5)
**Contexto:** ver o `[decision]` da corrida acima.
**Direção sugerida:** a Unit of Work da #46, ou um lock por `user_id` na Stage de vínculo, fecha o caso.
**Stage candidata:** issue #46.

### 2026-10-19 — [deviation] Auditoria de testes — dois e2e extras — Claude (Opus 5.5)
O auditor independente (11 mutações reais, nenhuma sobrevivente) marcou "não satisfeito" em dois itens: a guarda `active` só era pega no unit, e nenhum teste fixava na borda o 500 de uma falha antes da escrita — lacuna **herdada da 3.5** para a revogação. `[3.7/task-05-extra]` acrescenta os dois e2e (o de 500 parametrizado na consulta de papel e na revogação); a re-auditoria confirmou M3 morrendo também no e2e e o 500 vindo da falha injetada (Mc1–Mc3).

### 2026-10-19 — [decision] Checkpoints — disposição dos achados — Claude (Opus 5.5)
- **A** (concept): rodada 1 com duas lentes — 13 de domínio/testabilidade e 14 de conformidade; três viraram perguntas P ao sponsor (Q2, Q3, Q4) e o resto foi corrigido; rodada 2 de re-verificação: 14 resolvidos, 3 parciais e 3 contradições novas, todos corrigidos antes do `conceptual approved`.
- **B** (technical): 1 major (`_RESULT_CLASSES` na T01, deixaria o build vermelho) e 4 minor — corrigidos antes do `technical approved`.
- **C** bloco T01–T03: 1 major (a fachada podia devolver o `Role` StrEnum sem teste notar — mutação medida sobrevivendo) e 1 minor (docstrings afirmando a regra antes da T04) — `[3.7/task-02-fix]`, `[3.7/task-03-fix]`.
- **C** bloco T04–T06: 0 blocker/major, 12 de 12 mutações mortas; 4 minor/nit corrigidos — `[3.7/task-04-fix]`, `[3.7/task-05-fix]`, `[3.7/task-06-fix]`.

### 2026-10-21 — [deviation] auditoria da Stage (`stage-audit`, agente Opus de contexto zerado) — Claude Opus 5.5 (auditor)

Veredito: **aprovada com findings**, sem bloqueante depois da fase de aplicação. Gates no HEAD
`4c5ef92` (era `fe3daca` antes do rebase de 2026-11-01), antes das correções: `make check` EXIT=0 (4196 passed, cobertura total 99,96%, os 12
arquivos de `src/` tocados em 100%), `check_layout` sem violação, `lint-imports` com 10 contratos
mantidos e o `.importlinter` intocado. As correções são commits `[3.7/--]`: fora de Task, depois
do `stage 3.7: complete`. Cada uma passou por `make check` EXIT=0 antes de ser gravada.

**CA21 refeito pelo auditor.** As mutações rodaram numa cópia do HEAD (`git archive`). O alvo
foram o unit de R13, o contrato do gateway, o unit da fachada e do use case e o composition root:
188 testes, com a linha de base verde.
- M1 (sem a checagem da unidade) derruba 1 teste (`test_ca06…`). M2 (sem `is_employee_login`)
  derruba 4 (`ca05`, `ca10`, `ca11`, `ca13[is_employee_login]`). M3 (sem a guarda `active`)
  derruba 1 (`ca12`). M4 (o literal comparado vira `"manager"`) derruba 2 (`l_ig5` real: o
  provisionado e o `manager`). M5 (o filtro ignora `user_id`) derruba 1 (`ca09`).
- Dez mutações extras, todas mortas: `include_inactive=True` (`ca07`); sem `other.id !=
  employee.id` (10 testes); a fachada devolve o `Role` (6); o use case devolve papel constante
  (8); o adapter *fail-open* (1); o adapter aceita qualquer papel conhecido (4); aceita
  `employee` ou `hr` (1); o papel é consultado antes da unidade (3); gravar antes de revogar (3);
  conta desconhecida vira erro (3).
- No e2e contra o Postgres da worktree (21 testes), M1 derruba o CA16. M2 derruba o CA18 e o 500
  da consulta de papel. M3 derruba o desligamento repetido. Voltar à regra da 3.5 (revogar sempre)
  derruba 4. O CA17 passa com a regra da 3.5, como o docstring dele declara.

Disposições:
- **F1 (bloqueante de fechamento):** os 22 CAs do concept §11 estavam com a caixa aberta, e todos
  tinham evidência. Foram marcados `[x]`.
- **F2 (non-blocker):** `InMemoryIdentityGateway` era o único fake de port sem `_conforms`. Por
  isso `make typecheck` não conferia o fake contra o `IdentityGateway`, embora a tabela "As
  totalidades" (§1) dissesse "(mypy)". Medido numa cópia: com `is_employee_login -> str` no fake,
  o mypy passa sem a linha e reprova com ela. Corrigido em `8c8f5e7` (era `5cd2c40`).
- **F3 (nit):** o docstring da classe `IdentityGateway` listava três operações. O de
  `test_desligado_recusa_login_na_guarda_e_no_link_login` dizia "desligar cortou" sem qualificar;
  é o gêmeo do texto que o `[3.7/task-04-fix]` corrigiu em `employee.py`. Corrigidos em `1139fd0` (era `8dacc75`).
- **F4 (non-blocker):** a saída das mutações do CA21 não estava registrada em lugar nenhum, e o
  PR só afirmava "11 mutações, nenhuma sobrevivente". Ficou registrada acima e no comentário do
  veredito no PR #69.
- **F5 (non-blocker, rastro):** o `[finding] shared` acima, o ADR 3.8.0001 (Alt. H e §Negative) e
  o concept §10 dão a #46 como quem fecha a corrida de D7. Isso não se sustenta, por dois
  motivos. (1) Com o isolamento padrão (`READ COMMITTED`; `SERIALIZABLE` foi recusado no ADR
  3.3.0006 Alt. C), uma unidade de trabalho não fecha a corrida. Cada desligamento lê como ativa
  a linha do outro e grava uma linha diferente — é *write skew*. Fecha um lock por `user_id`, ou
  `SELECT … FOR UPDATE` sobre os registros do login na unidade. (2) A Stage 2.6 (#46, PR #70)
  deixa `deactivate_employee` fora da unidade (ADR 2.6.0002 §2 e §4, no PR). **Direção
  corrigida:** quem fecha é a Stage que implementar "vincular login existente", com lock por
  `user_id`. É ela que torna o caso produzível. A #46 deixa de ser candidata. Pela CONVENTIONS
  §3.2, a correção pós-Fase 4 é registrada aqui. O texto do ADR e do concept §10 se alinha no
  retrabalho de renumeração para 3.8, que já toca os dois arquivos.

### 2026-11-01 — [deviation] renumeração 3.7 → 3.8 e rebase sobre #70 e #71 — Claude Opus 5.5 (implementador do retrabalho)
**Contexto:** esta Stage foi executada como `3.7` em paralelo à #49, que promoveu a mesma `3.7` (`3.7-application-authorization`, PR #71). Decisão do orquestrador (2026-10-21, por delegação do sponsor): o #71 fica com 3.7, este PR vira **3.8**; ordem de merge #70 → #71 → #69.
**O que mudou:**
- Rebase sobre `origin/develop` em `1d1953d` (#70 e #71 mergeados). Conflitos: `docs/roadmap.md` (três commits — grafo, tabela de Steps, tabela de Stages, bloco do Step 3: as duas Stages preservadas lado a lado) e `tests/unit/features/staff/application/test_employee_lifecycle.py` (a versão desta Stage, mais o `actor`/`guard` da 3.7). Os hashes citados acima mudaram: `fe3daca` → `4c5ef92`, `5cd2c40` → `8c8f5e7`, `8dacc75` → `1139fd0`, `809f0e3` → `00b5c9a`. Na auditoria de 2026-11-01, um segundo rebase, sobre `44be5ef` (#80, #83 e #88), trouxe o conflito só na Tabela de Issues do roadmap (a linha da #60 sai; a #61 `done` e a #82 do `develop` ficam) e tirou da história o par de commits do handoff de sessão (adição e remoção do mesmo arquivo temporário); os hashes deste arquivo são os de depois desse rebase.
- Renumeração (`git mv`): pasta `docs/stages/3.8-termination-access-scope/`, ADR `3_8_0001-termination-revokes-only-access-the-record-grants.md` (`adr_id`, `context_stage`), frontmatter e corpo do concept e deste technical, roadmap, nota do workforce §3.8, nota de supersessão no ADR 3.5.0003, docstrings e testes que citavam a Stage. O ADR 3.7.0001 do #71 e as citações a ele ficaram intactos. Os sufixos dos commits já gravados continuam `[3.7/...]` (história não reescrita) e são citados assim neste arquivo; os commits do retrabalho usam `[3.8/--]`.
- **Fora da janela §7, só renumeração:** `check_technical_postexec` é *fail-open* aqui, porque o commit reservado de aprovação se chama `stage 3.7: technical approved` (`b3ddae6`) e o arquivo mudou de pasta. Conferido à mão contra `b3ddae6:docs/stages/3.7-termination-access-scope/technical.md`: fora de `BEGIN..END` mudam só oito linhas (`description`, `stage_id`, título, duas citações ao ADR, o comando de verificação, o checklist do ADR e o link do ADR), todas `3.7` → `3.8`. Nenhuma mudança de plano.
- Roadmap: a aresta do grafo vai na mesma linha da 3.7 (técnica do #71); o bloco desloca o Step 4 em +48 e a tabela de Stages em +1, e as 178 citações por linha que o #71 remapeou pelo mesmo ponto de inserção andaram o mesmo tanto. O deslocamento herdado do #70 (+65) fica com a #79.

### 2026-11-01 — [deviation] integração com a autorização da application (#71) e com a regra 10 (#70) — Claude Opus 5.5 (implementador do retrabalho)
- Os testes que constroem `DeactivateEmployeeUseCase` passam o `guard` e o `actor`. Teste novo `test_recusa_do_guard_nao_chama_list_by_unit_nem_is_employee_login`: com o registro no caminho em que as duas consultas desta Stage aconteceriam, a recusa sobe crua (mesma instância), sem chamada ao repositório nem ao gateway, e o registro continua ativo.
- A montagem por reflexão da 3.7 (`test_use_cases_authorize.py`, reusada pela cadeia real do CA14) desligava um registro cujo login o fake não conhecia — com L-IG5, "desconhecido" ⇒ não revoga, e o CA07 dela ficou vermelho. O fake ganhou o gancho `seed_employee_login` (gêmeo de `seed_login_of_other_role`, não registra em `calls`); o cenário de `create_login_for_employee` passou a achar o login pelo `user_id` do registro, não por ser o único do ledger.
- Docstrings de "quem autoriza cada operação" no port e no adapter do `IdentityGateway` incluem `is_employee_login` (chamado por `deactivate_employee`, sob `manage_staff`).
- Regra 10 do `check_layout` (2.6): `is_employee_login` classificado como **leitura** — fora de `GATEWAY_WRITE_METHODS`; o pino de totalidade dos métodos dos gateways e o teste do classificador acompanham.

### 2026-11-01 — [decision] F5 aplicado ao ADR e ao concept — Claude Opus 5.5 (implementador do retrabalho)
O ADR 3.8.0001 (Alt. H e §Negative) e o concept (D7 e §10) dão como dono da corrida de D7 a Stage que implementar "vincular login existente", com lock por `user_id`; a #46 deixa de ser citada como quem fecha. A correção é datada no próprio texto. O `[finding] shared` acima fica como registro histórico, corrigido pela disposição F5. Nenhum fork P surgiu no retrabalho.

<!-- END: post-execution -->

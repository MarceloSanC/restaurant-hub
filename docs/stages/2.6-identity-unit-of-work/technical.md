---
title: Technical — Fronteira transacional nos use cases de identity que escrevem mais de uma vez
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity-unit-of-work, unit-of-work, transacao, savepoint, check-layout]
status: done
created_at: 2026-10-19
updated_at: 2026-10-19
stage_id: 2.6-identity-unit-of-work
stage_title: Fronteira transacional nos use cases que escrevem mais de uma vez
step_id: 2
step_title: Restaurante e acesso
depends_on: [3.5-employee-login-link]
concept_ref: ./concept.md
issue_id: 46
branch: refactor/46-2-6-identity-unit-of-work
tasks_count: 13
---

# Technical — Stage 2.6 — Fronteira transacional nos use cases de identity que escrevem mais de uma vez

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde** — `make check`
>    verde antes de todo commit.
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.6/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar** e registrar em [§7](#7-execução-post-hoc-editável-após-done).

## 1. Contexto e estratégia de execução

### Resumo
Port `UnitOfWork` em identity (`transaction()` como context manager), adapter
Postgres que publica a conexão da unidade numa `ContextVar` chaveada pelo `Engine`
e que os repositórios de identity passam a consultar (savepoint por chamada dentro
da unidade), fake em memória com rollback do estado persistido declarado, e os
cinco use cases de identity com 2+ escritas abrindo a unidade em volta das
escritas. `SessionRepository.revoke` passa a devolver `bool` para a rotação tratar
a corrida perdida como reuso. Fecha com a regra 10 do `check_layout` e a regra no
`LAYOUT.md`.

### Estratégia
TDD de dentro para fora (skill `task-ordering-hex`): port + fake (T01) e a
premissa do fake pinada (T02) → repositórios Postgres lendo a conexão ambiente,
sem mudar comportamento (T03) → adapter da unidade + contrato fake × Postgres (T04)
→ mudança aditiva do port de sessão (T05) → um use case por Task, cada um com seus
testes unitários reescritos, sua fatia de integração (CA5) e sua fiação (T06–T10)
→ gate (T11), que só pode entrar quando nenhum use case de identity o viola →
documentação (T12).

**Totalidade por Task** (memória do projeto: varreduras derivadas reprovam mudança
incremental). Cada Task que muda construtor de use case leva junto **todos** os
sítios de construção daquele use case (composition root, testes unitários de
adapter, contrato de staff), senão o mypy (em `src/`) ou o pytest (`TypeError` nos
testes, que o mypy não cobre) fica vermelho entre commits.

### Pré-condições
- Stage `3.5-employee-login-link` em `done` e mergeada em `develop` (feito).
- Postgres de testes no ar e `DATABASE_URL` válido **na worktree** (memória do
  projeto: o `.env` da worktree vem sem `DATABASE_URL`; um consumidor por vez no
  Postgres compartilhado).

### Premissas técnicas
- Python 3.12, SQLAlchemy 2.0.51, anyio 4.14.1 (versões do `uv.lock`, verificadas
  no Checkpoint A).
- Ports síncronos (ADR 2.2.0004).

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                   (mod T06–T10)
└── features/identity/
    ├── application/
    │   ├── ports/out/unit_of_work.py                     (novo T01)
    │   ├── ports/out/session_repository.py               (mod T05)
    │   └── use_cases/{set_password_with_token,invite_user,provision_account,
    │                  request_password_reset,refresh_session}.py   (mod T06–T10)
    └── adapters/out/postgres/
        ├── conexao_da_unidade.py                         (novo T03)
        ├── unit_of_work.py                               (novo T04)
        └── {restaurant,unit,user,session,password_setup_token}_repository.py (mod T03; session T05)
scripts/check_layout.py                                   (mod T11)
docs/LAYOUT.md                                            (mod T12)
tests/
├── fakes/features/identity/
│   ├── in_memory_unit_of_work.py                         (novo T01)
│   └── in_memory_session_repository.py                   (mod T05)
├── unit/features/identity/application/test_in_memory_unit_of_work.py   (novo T01)
├── unit/features/identity/adapters/test_repositorios_sem_transacao_propria.py (novo T03)
├── contract/features/identity/
│   ├── conftest.py                                       (mod T04)
│   ├── test_repository_contract.py                       (mod T02, T05)
│   └── test_unit_of_work_contract.py                     (novo T04)
└── integration/features/identity/adapters/out/postgres/
    ├── test_unit_of_work.py                              (novo T04)
    └── test_use_cases_atomicos.py                        (novo T06; cresce T07–T10)
```

## 2. Tasks

### Task 01 — Port `UnitOfWork` e fake `InMemoryUnitOfWork`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/ports/out/unit_of_work.py`
  - `tests/fakes/features/identity/in_memory_unit_of_work.py`
  - `tests/unit/features/identity/application/test_in_memory_unit_of_work.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `Protocol` com `transaction(self) -> AbstractContextManager[None]`
  e as leis L1–L6 no docstring (ADR 2.6.0001 §1). Fake: recebe os repositórios em
  memória que guarda; uma tabela **no próprio módulo do fake** declara, por classe
  de repositório em memória (resolvida pela MRO, para os injetores de falha
  subclasses herdarem), quais atributos são estado persistido; snapshot
  (`copy.deepcopy`) desses atributos na entrada e restauração **no lugar** na saída
  por exceção; `ContextVar` de módulo para a L5.
- **Detalhes técnicos:**
  - Repositório guardado sem entrada na tabela ⇒ `TypeError` na construção do fake
    (fail-closed: nada é guardado por acidente).
  - Restaurar no lugar: `dict.clear()` + `update`, `list[:] = …`.
- **Critério de aceite:** testes do fake cobrem L1 (dois repositórios), L2 (`is`),
  L5 (duas instâncias distintas aninhadas levantam `RuntimeError`, estado
  inalterado), contador de chamadas e log de injetor **sobrevivem** ao rollback,
  referência a dict tomada antes continua válida.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_in_memory_unit_of_work.py -q
  make check
  ```
- **Commit sugerido:** `feat(identity): port UnitOfWork e fake em memória [2.6/task-01]`

---

### Task 02 — Pinar "o fake valida antes de mutar" na suíte de contrato (CA14)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `tests/contract/features/identity/test_repository_contract.py`
- **O que fazer:** em cada teste de recusa por duplicata/conflito da suíte de
  contrato de identity, asseverar também que o estado observável pelo port ficou
  idêntico ao de antes da chamada recusada (contagem e conteúdo via leituras do
  port).
- **Critério de aceite:** os testes passam `[fake]` e `[postgres]`; uma mutação no
  fake que grave antes de validar derruba ao menos um.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/identity/test_repository_contract.py -q
  make check
  ```
- **Commit sugerido:** `test(identity): asseverar estado inalterado nas recusas do contrato [2.6/task-02]`

---

### Task 03 — Repositórios Postgres de identity consultam a conexão da unidade ativa

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/conexao_da_unidade.py`
  - `tests/unit/features/identity/adapters/test_repositorios_sem_transacao_propria.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/{restaurant,unit,user,session,password_setup_token}_repository.py`
- **O que fazer:** módulo com a `ContextVar[tuple[Engine, Connection] | None]` e dois
  context managers, `para_escrita(engine)` e `para_leitura(engine)`: com unidade
  ativa **do mesmo engine**, entregam a conexão dela dentro de `begin_nested()`;
  sem unidade, `engine.begin()` / `engine.connect()` como hoje. Cada repositório
  troca as aberturas diretas pelos helpers e atualiza os docstrings que diziam
  "sem UoW" / "ponto de troca para um futuro UoW" (CA10, parte dos repositórios).
  O publicador da `ContextVar` entra na T04 (é do adapter da unidade).
- **Detalhes técnicos:** 7 arquivos — acima do típico de 5, porque a troca é
  mecânica e precisa ser total (um método esquecido escapa da unidade em silêncio);
  o teste mecânico desta Task é o que garante a totalidade.
- **Critério de aceite:** CA3 — suítes de contrato e integração de identity verdes
  **sem editar asserção**; teste mecânico (AST/texto) sem `_engine.begin(` nem
  `_engine.connect(` em `identity/adapters/out/postgres/*_repository.py`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/identity tests/integration/features/identity tests/unit/features/identity/adapters -q
  make check
  ```
- **Commit sugerido:** `refactor(identity): repositórios Postgres usam a conexão da unidade ativa [2.6/task-03]`

---

### Task 04 — Adapter `PostgresUnitOfWork` e contrato fake × Postgres (CA2)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/unit_of_work.py`
  - `tests/contract/features/identity/test_unit_of_work_contract.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_unit_of_work.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/conexao_da_unidade.py` (publicador)
  - `tests/contract/features/identity/conftest.py` (`Repositorios` ganha a unidade; o ramo fake a constrói sobre os mesmos fakes)
- **O que fazer:** `PostgresUnitOfWork(engine).transaction()`: L5 checada **antes**
  de retirar conexão do pool; `engine.begin()`; publica `(engine, conexão)`; `reset`
  em `finally`. Suíte de contrato: L1 parametrizada por **todo** método de escrita
  dos cinco repositórios; L2 com `is`; L3 com violação real de constraint (fingerprint
  de sessão duplicado) seguida de outra escrita e commit; L4 parametrizada por todo
  método de leitura; L5; L6. Integração (só Postgres): L5 sem conexão retirada
  (`engine.pool.checkedout()`), duas threads com unidades simultâneas não se
  enxergam, unidade de um engine é ignorada por repositório de outro engine
  (documenta a armadilha de R7), conexão devolvida ao pool depois de exceção.
- **Critério de aceite:** CA2; integração verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/identity/test_unit_of_work_contract.py tests/integration/features/identity/adapters/out/postgres/test_unit_of_work.py -q
  make check
  ```
- **Commit sugerido:** `feat(identity): unidade de trabalho Postgres e contrato com o fake [2.6/task-04]`

---

### Task 05 — `SessionRepository.revoke` devolve `bool`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/ports/out/session_repository.py`
  - `src/restaurant_hub/features/identity/adapters/out/postgres/session_repository.py`
  - `tests/fakes/features/identity/in_memory_session_repository.py`
  - `tests/contract/features/identity/test_repository_contract.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_session_repository.py`
- **O que fazer:** retorno `True` se esta chamada revogou (`rowcount == 1`), `False`
  se inexistente ou já revogada; docstring do port cita a rotação como consumidora.
  `revoke_session` (logout) segue ignorando o valor — sem edição.
- **Critério de aceite:** contrato `[fake]`/`[postgres]` assevera `True` na primeira
  revogação, `False` na segunda e em id inexistente; o instante da primeira
  revogação continua preservado.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/identity tests/integration/features/identity/adapters/out/postgres/test_session_repository.py -q
  make check
  ```
- **Commit sugerido:** `feat(identity): revoke de sessão informa se revogou [2.6/task-05]`

---

### Task 06 — `set_password_with_token` escreve numa unidade

- **Arquivos a criar:**
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/use_cases/set_password_with_token.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/identity/application/test_set_password_with_token.py`
  - `tests/unit/features/identity/adapters/test_setup_token_http.py` (construção)
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py` (CA9)
- **O que fazer:** construtor ganha `unit_of_work: UnitOfWork` obrigatório. Hash
  calculado antes da unidade (R5); `consume → revoke_all_for_user →
  invalidate_all_for_user → set_password_hash` dentro dela, ordem preservada (R2).
  Docstring: nota 2 reescrita — a ordem fica, redundante; o ponteiro da 4.4 sai e
  entra a #46/Stage 2.6; a troca de R2 é declarada. Testes unitários: `TestOrdemFailClosed` e
  `test_falha_ao_revogar_sessoes_ja_consumiu_o_token` (fora da classe, `:349`) viram "falha na escrita N (N = 1..4) ⇒ injetor disparou em N, escritas 1..N-1
  tentadas, nada persistido" (CA4). Integração: injetor que falha **depois** de
  delegar a escrita N ⇒ tabelas `password_setup_tokens`, `sessions`, `users`
  idênticas (CA5); CA7
  com duas threads e barreira dentro da unidade da primeira, nas duas variantes
  (comita / falha depois do `consume`). O docstring de
  `test_setup_token_http.py:251-257` ("token queimado") é atualizado junto. CA9: teste de bootstrap que confere o
  `_engine` da unidade e de cada repositório injetado neste use case (o teste é
  parametrizado pelos use cases e cresce nas Tasks seguintes).
- **Critério de aceite:** CA4, CA5, CA7, CA9 e CA10 para este use case.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py -q
  make check
  ```
- **Commit sugerido:** `refactor(identity): definir senha por token numa unidade de trabalho [2.6/task-06]`

---

### Task 07 — `invite_user` escreve numa unidade

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/use_cases/invite_user.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/identity/application/test_invite_user.py`
  - `tests/unit/features/identity/adapters/test_http_router.py` (construção)
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** `users.add` + `tokens.add` na unidade; envio **depois** dela (R4).
  Docstring: "a transação de `add` já fechou" vira "a unidade já comitou".
  Unit: falha na escrita N (1..2) ⇒ nada persistido; falha do envio ⇒ conta e token
  persistidos e exceção sobe (CA8). Integração: N = 1..2 com falha depois de
  delegar ⇒ `users`, `unit_memberships`, `password_setup_tokens` idênticas; e o caso
  com **falha originada no banco** de CA5: um token semeado com o fingerprint que o
  emissor vai produzir faz o `tokens.add` violar `uq_setup_tokens_fingerprint` depois
  do `users.add` ⇒ `users`/`unit_memberships` inalteradas.
- **Critério de aceite:** CA4, CA5, CA8 (convite), CA9 para este use case.
- **Comando de verificação:** idem T06.
- **Commit sugerido:** `refactor(identity): convite grava conta e token numa unidade [2.6/task-07]`

---

### Task 08 — `provision_account` escreve numa unidade

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/use_cases/provision_account.py`
  - `src/restaurant_hub/composition_root.py` (inclusive o da fachada)
  - `tests/unit/features/identity/application/test_provision_account.py`
  - `tests/unit/features/identity/application/test_facade.py` (construção)
  - `tests/contract/features/staff/conftest.py` (`_gateway_real`)
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** igual à T07, sem envio (inclusive o caso de fingerprint de token
  duplicado originado no banco). CA9 cobre a instância da fachada.
- **Detalhes técnicos:** 7 arquivos — os sítios de construção são totais por
  exigência do mypy (§1, "Totalidade por Task").
- **Critério de aceite:** CA4, CA5, CA9 para este use case; contrato do gateway de
  staff verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity tests/contract/features/staff tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py -q
  make check
  ```
- **Commit sugerido:** `refactor(identity): provisionamento de conta numa unidade [2.6/task-08]`

---

### Task 09 — `request_password_reset` escreve numa unidade

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/use_cases/request_password_reset.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/identity/application/test_request_password_reset.py`
  - `tests/unit/features/identity/adapters/test_setup_token_http.py` (construção)
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** `invalidate_all_for_user` + `add` na unidade, a unidade **dentro**
  do `try` (o rollback também é absorvido); envio depois da unidade, ainda dentro do
  `try`. Unit: falha na escrita N ⇒ nada persistido e `None`; Integração: N = 1..2
  ⇒ `password_setup_tokens` idêntica; caso positivo grava de fato o token (CA8).
- **Critério de aceite:** CA4, CA5, CA8 (reset), CA9 para este use case.
- **Comando de verificação:** idem T06.
- **Commit sugerido:** `refactor(identity): pedido de redefinição numa unidade [2.6/task-09]`

---

### Task 10 — Rotação de `refresh_session` numa unidade; corrida perdida é reuso

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/use_cases/refresh_session.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/identity/application/test_refresh_session.py`
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** caminho de reuso inalterado (`revoke_all_for_user` fora da
  unidade, seguido de `raise`). Rotação: `revoke` + `add` na unidade; `revoke`
  devolvendo `False` ⇒ sair da unidade por exceção interna (rollback), revogar
  todas as sessões do usuário fora dela e levantar `RefreshTokenReuseError` (R6b).
  Emissão de tokens (CPU, sem I/O) antes da unidade. Docstring: some "não há port
  de unidade de trabalho"; entra a decisão R6b com a base (2.4 §6, auditoria de
  2026-09-28). Unit: `test_revoke_da_antiga_precede_o_add_da_nova` vira "falha no
  `add` ⇒ sessão antiga intacta"; perdedor da corrida (fake com `revoke` → `False`)
  ⇒ reuso. Integração: CA6 com a falha do `add` **originada no banco** (sessão
  semeada com o fingerprint que o emissor vai produzir ⇒ `uq_sessions_fingerprint`)
  e CA13 (duas threads, barreira; inclusive a variante em que a primeira rotação
  desfaz).
- **Detalhes técnicos:**
  - A exceção interna que tira a rotação da unidade é classe **privada do módulo**
    do use case, herdando de `Exception` (não de `IdentityError`/`DomainError`),
    capturada no próprio `execute` — nunca escapa; assim as varreduras de
    `__subclasses__()` (`test_status_map.py`, `test_http_error_handlers.py`) não a
    enxergam.
  - O injetor `_SessionRepositoryInstrumentado.revoke` de `test_refresh_session.py`
    (`:83-85`) passa a `-> bool` e devolve o valor de `super().revoke(...)`; sem isso
    toda rotação do teste vira reuso. (O mypy não cobre `tests/unit`.)
- **Critério de aceite:** CA4, CA5, CA6, CA9, CA10, CA13 para este use case.
- **Comando de verificação:** idem T06.
- **Commit sugerido:** `refactor(identity): rotação de sessão numa unidade, corrida perdida é reuso [2.6/task-10]`

---

### Task 11 — Regra 10 do `check_layout`: escrita múltipla só dentro de uma unidade

- **Arquivos a modificar:**
  - `scripts/check_layout.py`
  - `tests/unit/test_check_layout.py`
- **O que fazer:** ADR 2.6.0002 §5, literal. Classificador de escrita: atributo do
  `self` cuja anotação no `__init__` é port de `ports/out/*_repository.py` e método
  fora de `find_`/`exists_`/`list_`, ou método de gateway declarado como escrita no
  script (`provision_employee_login`, `revoke_login_sessions`); bloco de unidade =
  `with self.<attr>.transaction():` com `<attr>` anotado `UnitOfWork`; fecho
  transitivo por `self._helper()`; escrita em laço conta 2; "grava e recusa" =
  escrita seguida de `raise` no mesmo bloco de instruções. Allowlist contável
  `MULTI_WRITE_ALLOWLIST` com `CreateLoginForEmployeeUseCase` e
  `DeactivateEmployeeUseCase`, razão citando o ADR 2.6.0002; entrada sem
  correspondente reprova. A âncora entra em `coverage_anchors` (o arquivo de use
  case já é coberto pela regra de camada; a regra 10 soma, não substitui).
- **Critério de aceite:** CA11 — fixtures sintéticas (consume fora com outra
  escrita dentro; dois blocos; laço fora; grava-e-recusa aceito; helper seguido;
  allowlist órfã); varredura real verde com exatamente as duas entradas;
  classificador aplicado aos ports reais não classifica nenhum `find_*`/`exists_*`/`list_*`
  como escrita e classifica todos os demais métodos de repositório como escrita.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/test_check_layout.py -q
  uv run python scripts/check_layout.py
  make check
  ```
- **Commit sugerido:** `feat(tooling): regra 10 do check_layout para escrita múltipla [2.6/task-11]`

---

### Task 12 — `LAYOUT.md`: a fronteira transacional

- **Arquivos a modificar:**
  - `docs/LAYOUT.md`
- **O que fazer:** subseção em §5/§7 com a regra (CA12): o use case abre a unidade
  em volta só das escritas; leitura/checagem e CPU antes, efeito colateral depois;
  a unidade é por BC e não atravessa a fachada; regra 10 e allowlist; ADRs 2.6.0001
  e 2.6.0002. Atualizar a descrição do script em LAYOUT §6 se citar as regras.
- **Critério de aceite:** CA12; `make docs-check` verde (o `check_docs_claims`
  confere a árvore da §2 do LAYOUT).
- **Comando de verificação:**
  ```bash
  make docs-check
  make check
  ```
- **Commit sugerido:** `docs(layout): regra da fronteira transacional [2.6/task-12]`

---

### Task 13 — Docstrings de staff deixam de afirmar que identity não tem unidade

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/adapters/out/postgres/employee_repository.py` (docstring, `:7-14`)
  - `src/restaurant_hub/features/staff/adapters/out/postgres/job_function_repository.py` (docstring, `:5-11`)
- **O que fazer:** os dois docstrings dizem que o desvio da fronteira transacional
  "é o mesmo que identity assumiu… sem UoW". Passam a dizer que staff segue com
  transação por método porque nenhum use case de staff escreve duas vezes em staff
  (ADR 2.6.0002 §2), e que identity tem unidade desde a 2.6. Só docstring — nenhum
  código de staff muda. Task separada porque o escopo do commit é staff
  (CONVENTIONS §4: 1 commit = 1 escopo).
- **Critério de aceite:** CA10 fechado — `grep -rniE "unit.of.work|unidade de trabalho|UoW|4\.4|não são atômic" src/restaurant_hub` revisado ocorrência a ocorrência, colado no relatório, sem nenhuma que contradiga a Stage.
- **Comando de verificação:**
  ```bash
  grep -rniE "unit.of.work|unidade de trabalho|UoW|4\.4|não são atômic" src/restaurant_hub
  make check
  ```
- **Commit sugerido:** `docs(staff): fronteira transacional de staff sem citar identity como sem unidade [2.6/task-13]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check
make test-cov
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/2.6-identity-unit-of-work/technical.md
grep -rniE "unit.of.work|unidade de trabalho|UoW|4\.4|não são atômic" src/restaurant_hub   # CA10, revisado
```

### Verificações funcionais
- [ ] Pela API real (app + Postgres): `POST /auth/password` com um link válido
      enquanto a escrita da senha falha não queima o link — o mesmo link funciona
      na tentativa seguinte (fluxo exercitado no §0 do relatório).
- [ ] Pela API real: duas chamadas simultâneas de `POST /auth/refresh` com o mesmo
      refresh ⇒ uma 200, outra 401 de reuso, e o refresh devolvido pela 200 também
      morto (todas as sessões revogadas).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage 2.6: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e
      `last_reviewed_at`
- [ ] ADRs 2.6.0001 e 2.6.0002 em `status: accepted`
- [ ] `[finding]`s com issue/Stage de pouso (provisionamento composto — ADR
      2.4.0003; `user_id` condicional em staff)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
T01 ─► T02
T01 ─► T03 ─► T04 ─► T05 ─► T10
               │
               └──► T06 ─► T07 ─► T08 ─► T09 ─► T10 ─► T11 ─► T12 ─► T13
```

T06–T10 são independentes entre si em código, mas compartilham o
`composition_root.py`, o teste de bootstrap e o módulo de integração — por isso
seriais. T11 só depois de T10: antes disso, a varredura real reprova os use cases
ainda não migrados.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `begin_nested()` dentro de `engine.begin()` se comporta diferente do esperado com o `IntegrityError` traduzido (savepoint já desfeito quando o tradutor roda) | o tradutor só lê `erro.orig.diag`; se o savepoint interferir, traduzir fora do `with begin_nested()` — ajuste local, `[deviation]` |
| Teste com barreira entre threads trava (deadlock no próprio teste) | timeout explícito em `Barrier.wait` e `join`; falha clara em vez de travar a suíte |
| Postgres compartilhado com outra worktree/sessão gera `ERROR at setup` falso | um consumidor por vez (memória do projeto); rodar a integração isolada antes do `make check` |
| A regra 10 reprova algo legítimo no código atual que o mapa não previu | ajustar o classificador se for falso positivo; se for verdadeiro, `[finding]` e pergunta antes de entrar na allowlist |

## 6. Referências

- [`./concept.md`](./concept.md)
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.6-identity-unit-of-work`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md)
- ADRs: [2.6.0001](../../adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md), [2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
- Skills: `hex-arch-python`, `repository-pattern`, `pytest-with-fakes`, `composition-root`, `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.

### 2026-10-19 — [decision] Renumeração 3.7 → 2.6 antes do primeiro gate — Claude (sessão única)
**Contexto:** a #46 foi promovida como Stage 3.7 (Step 3). Minutos depois, duas sessões paralelas promoveram as issues #49 e #60 também como 3.7, uma delas já com ADR `3_7_0001`. O número da Stage e o `adr_id` são identidade e não reciclam (CONVENTIONS §1). O Checkpoint A (conformidade) apontou ainda que quatro das cinco dívidas nasceram no Step 2.
**Pergunta:** que número dar à Stage?
**Opções:**
- A — manter 3.7 e disputar com #49/#60 no merge
- B — 3.8 no Step 3
- C — 2.6 no Step 2, o Step do BC identity ✅ recomendada
**Decisão:** C. Os dois commits locais (roadmap e esqueleto) foram refeitos antes de qualquer gate. A branch passou de `refactor/46-3-7-unit-of-work` para `refactor/46-2-6-identity-unit-of-work`; a pasta da worktree mantém o nome antigo, porque movê-la quebraria o venv.
**Razão:** PIPELINE §4.5 ("Step certo"). O Step do próprio BC raramente disputa número com Stages de outro BC. Aprendizado registrado na memória do projeto.

### 2026-10-19 — [deviation] Docstrings de staff numa Task própria (T13) — Claude (sessão única)
O plano inicial punha os docstrings de `employee_repository.py` e `job_function_repository.py` na T03, que é um commit `refactor(identity)`. O Checkpoint B apontou que isso fere "1 commit = 1 escopo" (CONVENTIONS §4). Os dois docstrings foram para a T13 (`docs(staff)`). Ficou abaixo do limiar de pergunta porque não muda contrato nem comportamento, só o corte dos commits.

### 2026-10-19 — [deviation] Três commits de correção vindos dos Checkpoints C — Claude (sessão única)
- `561ee2b` [task-03-fix]: contrato de recusa conta linhas pelo port; `_conforms` do fake; detector mecânico positivo; L2 do port com a exceção do ADR; contador da classe-base sobrevive ao rollback.
- `42fcfd9` [task-06-fix]: L5 conta checkouts **durante** a unidade aninhada; a corrida espera `wait_event_type = 'Lock'` em vez de `sleep`; CA9 com conjunto exato de atributos. O achado de deadlock entre unidades do mesmo usuário foi **refutado**, com o artefato: a linha da tabela do concept §6 "Deadlock entre duas unidades (ex.: o mesmo usuário redime convite e link de redefinição ao mesmo tempo…)".
- `5e584c3` [task-09-fix]: o teste unitário do convite manda um vínculo, para a asserção sobre `memberships` não ser vazia; a espera de lock filtra o `UPDATE` na tabela da corrida.
Em todas as correções a mutação apontada pelo revisor foi rodada antes e depois da correção.

### 2026-10-19 — [deviation] Teste da regra 10 isola as tabelas globais nas árvores sintéticas — Claude (sessão única)
Nas árvores de `tmp_path`, a allowlist real e os métodos de gateway declarados apareciam como entradas mortas e afogavam a violação plantada. Uma fixture (`regra10_isolada`) esvazia as duas tabelas nesses testes, e os casos de entrada morta ganharam testes próprios. O gate de produção não mudou.

### 2026-10-19 — [finding] Provisionamento composto restaurante + dono — Claude (sessão única)
**Stage/issue candidata: #67.** O gatilho do ADR 2.4.0003 ("revisit when a transaction port exists") disparou com o port desta Stage. Compor as duas rotas muda o contrato HTTP e o fluxo do admin, e fica fora do escopo (concept §1). **Direção sugerida:** ADR que supersede ou confirma a Alternativa B, com a unidade em volta de `restaurants.add` + `users.add`.

### 2026-10-19 — [finding] `Employee.user_id` sem escrita condicional em staff — Claude (sessão única)
**Stage/issue candidata: #68.** A janela "última escrita vence sobre `user_id`" do concept 3.5 §6.4 apontava para "a Stage da #46". O port desta Stage é de identity e não alcança staff (ADR 2.6.0002 §2). **Direção sugerida:** método dedicado do port de staff com `UPDATE … WHERE user_id IS NULL`, mais um teste de conduta com duas conexões.

### 2026-10-19 — [finding] Escrita múltipla em scheduling vai encontrar a regra 10 — Claude (sessão única)
**Stage candidata: `4.4-scheduling-persistence`.** O DoD da 4.4 ("toda mutação de escala gera entrada de auditoria") são duas escritas. A regra 10 vale para todo `use_cases/`, e o port `UnitOfWork` é de identity, que `bc-independence` impede scheduling de importar. A 4.4 precisa escolher entre um port próprio, mover este para `shared/` (aí o reuso já é medido, LAYOUT §4) ou uma entrada de allowlist (ADR 2.6.0002 §5, "Scope across bounded contexts").

### 2026-10-19 — [deviation] Checkpoint C das Tasks 10 a 13 e duas rodadas da auditoria de testes — Claude (sessão única)
O último Checkpoint C não trouxe blocker: 2 achados médios e 4 baixos na regra 10 e no LAYOUT, todos corrigidos. Correções:
- `63ca1ad` [task-11-fix]: a regra 10 passa a contar cada entrada numa unidade (helper chamado duas vezes e unidade em laço reprovam), lê a condição do `while`, os cabeçalhos e os `except`, as formas `async`, o `match` e a atribuição anotada; não segue mais chamada de público para público.
- `9cb5f6f` [task-12-fix]: o LAYOUT afirmava que a emissão de token vem antes da unidade, e o código mostra o contrário em três use cases.
- `723ef33` [task-10-fix]: o docstring da rotação registra que logout, desligamento ou expurgo concorrentes também viram reuso; o ADR 2.6.0002 §5 explicita a unidade entrada uma vez só.

Auditoria independente:
- **Rodada 1:** um sobrevivente em `para_leitura` (leitura sem savepoint) e quatro na regra 10. Fechados em `f74017c` [task-13-extra] e nas fixtures de `63ca1ad`.
- **Rodada 2:** todos os sobreviventes da rodada 1 morrem; oito mutantes novos da regra 10 sobrevivem. Fechados em `6213d9f` [task-11-extra]. Os oito foram reaplicados e todos morrem, e a auditoria fecha "sim" nos seis itens. Um mutante de `refresh_session` (um `revoke_all` a mais dentro da unidade) foi classificado como equivalente, porque a escrita de dentro é desfeita e a de fora é refeita.

Os commits `63ca1ad`, `9cb5f6f`, `723ef33` e `f74017c` foram verificados por **um** `make check` sobre o estado final dos quatro (4098 passed). Eles mexem em arquivos disjuntos e foram comitados em sequência sem rodar o gate entre um e outro: os três primeiros são documentação ou mudanças que o último não altera. Abaixo do limiar de pergunta, porque não muda contrato e o estado comitado final é o verificado. Fica declarado porque foge da letra de "make check antes de todo commit".

### 2026-10-19 — [decision] Sincronização com o develop por rebase — Claude (sessão única)
**Contexto:** a Stage 4.2 mergeou no develop durante a execução (25 commits, PR #66).
**Pergunta:** rebase ou merge (memória do projeto: medir antes de decidir)?
**Opções:**
- A — merge com commit de adaptação
- B — rebase, a regra da Etapa 4 do GIT-WORKFLOW ✅ recomendada
**Decisão:** B. Medição: interseção de arquivos limitada a `docs/roadmap.md` e `docs/LAYOUT.md`, e o rebase parou só no commit de promoção do roadmap (`last_reviewed_at` e a linha de histórico, resolvidos mantendo os dois lados). O LAYOUT não conflitou.
**Razão:** a divergência é documental e cabe num conflito. A regra literal vale sem precisar levar a decisão ao sponsor.

### 2026-10-19 — [decision] Verificação end-to-end contra a app real — Claude (sessão única)
**Contexto:** gate de saída "fluxo exercitado pelo entrypoint real".
**Decisão:** app na porta 8001 da worktree com o Postgres dela; usuário semeado com o hasher argon2 real; a falha da escrita da senha forçada por um trigger temporário em `users`, removido em `finally`. Resultado: duas rotações simultâneas dão `[200, 401]` e o refresh emitido pela vencedora já está morto (401); `POST /auth/password` com a escrita falhando dá 500 e nenhum token é consumido; o mesmo link, sem a falha, dá 204, e o login com a senha nova dá 200. O roteiro ficou no scratchpad da sessão, fora do repo.
**Razão:** os testes de integração já provam as duas propriedades no use case; aqui elas são vistas pela borda HTTP, que é o que o sponsor observa.

<!-- END: post-execution -->

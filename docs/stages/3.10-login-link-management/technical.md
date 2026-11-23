---
title: Technical — Gestão do vínculo de login do registro
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, login-link-management]
status: done
created_at: 2026-11-22
updated_at: 2026-11-22
stage_id: 3.10-login-link-management
stage_title: Gestão do vínculo de login do registro
step_id: 3
step_title: Equipe da unidade
depends_on: [3.8-termination-access-scope, 2.7-identity-application-authorization]
concept_ref: ./concept.md
issue_id: 218
branch: feat/218-3-10-login-link-management
tasks_count: 12
---

# Technical — Stage 3.10 — Gestão do vínculo de login do registro

> **Como usar este documento:** executar as Tasks em ordem (§2), 1 Task = 1 commit
> `<type>(<scope>): <descrição> [3.10/task-NN]` (CONVENTIONS §4). Algo fora de §1–§6 ou do
> [`concept.md`](./concept.md) → registrar em §7. A verificação de cada Task roda só os
> testes dela; o `make check` completo roda só nos pontos do plano de gates.

## 1. Contexto e estratégia de execução

### Resumo
Três transições do vínculo de login (R18 vincular conta existente, R19 trocar, R20
desvincular), três escritas condicionais novas no `EmployeeRepository` (L-UNLINK,
L-RELINK, L-DEACT) com contrato fake ≡ Postgres e conduta com duas conexões, R13
regravado pela escrita condicional, o ponto único da regra de fim de vínculo
(`_login_link.end_active_link`) com a regra 10 de `check_layout.py` ensinada a vê-lo, a
consulta facade-only de identity (`find_account_by_email`) e a lei L-IG6 do gateway, a
elegibilidade e "um login por unidade" (`resolve_linkable_login`), três rotas HTTP, e2e
e notas datadas nos docs.

### Estratégia
**Inside-out** (skill `task-ordering-hex`): domínio → port com fake, adapter e contrato →
identity (consulta e fachada) → gateway → ponto único e R13 → regras de application →
use cases → HTTP → e2e → docs. **Totalidades primeiro**: cada Task leva a sua entrada
em toda varredura que a observa, para o build ficar verde entre commits. Mapa das
varreduras disparadas (de `grep -rlE "__subclasses__|router\.routes|glob\(|getmembers|vars\(" tests/`):

| Arquivo novo ou alterado | Varreduras que dispara | Task |
|---|---|---|
| erros de domínio novos | `tests/unit/features/staff/domain/test_exceptions.py`, `tests/unit/features/staff/adapters/test_http_error_handlers.py`, `tests/unit/test_status_map.py`, `tests/e2e/features/staff/test_staff_status_bands.py` (`INALCANCAVEIS_POR_HTTP` até a rota existir) | 01 |
| métodos novos do port de funcionário | `tests/contract/features/staff/test_no_implementation_branching.py`, `tests/unit/features/staff/application/test_staff_repository_fakes.py`, `tests/unit/test_check_layout.py` (`test_regra10_o_classificador_bate_com_os_ports_reais`) | 02 |
| use case facade-only de identity | `tests/unit/features/identity/application/test_use_cases_authorize.py` (`_EXCLUSOES`, `_FACADE_ONLY`), `tests/unit/features/identity/application/test_dtos.py`, `tests/unit/features/identity/adapters/test_composition_root_identity.py` | 03 |
| lei nova do gateway | `tests/contract/features/staff/test_identity_gateway_laws.py` (`test_a_lei_esta_documentada_no_port`), `tests/unit/features/staff/test_bc_independence.py`, `tests/unit/test_check_layout.py` (`test_regra10_todo_metodo_dos_gateways_declarados_esta_classificado`) | 04 |
| auxiliar `_login_link.py`, regra 10 | `tests/unit/test_check_layout.py`, `tests/unit/features/staff/application/test_use_cases_authorize.py` (pasta sem `_`) | 05 |
| erros de application novos | `tests/unit/features/staff/application/test_errors.py`, `tests/unit/features/staff/adapters/test_http_error_handlers.py`, `tests/unit/test_status_map.py`, `tests/e2e/features/staff/test_staff_status_bands.py` | 06 |
| use cases e commands novos | `tests/unit/features/staff/application/test_use_cases_authorize.py` (`CENARIOS`), `tests/unit/features/staff/application/test_application_guards.py`, `tests/unit/features/staff/application/test_dtos.py`, `tests/unit/features/staff/adapters/test_composition_root_staff.py`; R19/R20 também `tests/unit/test_check_layout.py` (`test_regra10_a_allowlist_nao_cresceu`) | 07, 08, 09 |
| rotas e schema | `tests/unit/features/staff/adapters/test_http_boundary_sweeps.py`, `test_http_dependencies.py`, `test_http_path_addresses_the_record.py`, `test_http_schemas.py`, `test_http_router_lifecycle_and_copy.py` (`vars(schemas)`), `test_http_router_job_functions.py` (`vars(router_module)`), `tests/e2e/features/staff/test_staff_authorization.py`, `tests/e2e/test_deny_by_default.py`, `tests/e2e/features/staff/test_staff_status_bands.py` (`CENARIOS_POR_EXCECAO`, `_TOTAL_DE_CAMPOS_ESCALARES`) | 10 |

### Pré-condições
- `check_stage_deps 3.10-login-link-management` OK (3.8, 2.7, #178).
- Postgres local é compartilhado por várias sessões: localmente rodam só testes unit e
  de contrato **em memória** (`-k "not postgres"` nos contratos); integração, conduta e
  e2e rodam no `lint-and-test` do GitHub Actions (orquestração autônoma, ADR 0.0.0008).

### Premissas técnicas
- Python 3.12, SQLAlchemy 2 Core; o adapter Postgres de funcionário já tem o padrão
  "trava a linha, reconstrói, aplica o domínio, grava uma coluna" em `link_login`.
- Sem migration (concept §9).

### Plano de gates

| # | Depois da Task | Motivo |
|---|---|---|
| 1 | Task 04 | Contratos lidos por outro BC e pelo composition root: o port de funcionário com adapter Postgres e conduta (T02), a fachada de identity e o seu wiring (T03), a lei nova do gateway (T04). Quebra aqui invalidaria todos os use cases seguintes, e o contrato e a conduta Postgres só rodam no Actions |
| 2 | Task 07 | Primeira Task que alimenta as totalidades de use case (contêiner do composition root, matriz de autorização, guardas de application, DTOs) que T08 e T09 replicam; cobre também a mudança no script de gate da regra 10 e na suíte de R13 (T05) |
| 3 | saída (Task 12) | gate de saída (§3) |

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py
├── features/identity/application/
│   ├── dtos/{commands,results}.py
│   ├── facade.py
│   └── use_cases/find_account_by_email.py            (novo)
└── features/staff/
    ├── domain/{entities/employee.py,exceptions/errors.py}
    ├── application/
    │   ├── errors.py; dtos/commands.py
    │   ├── ports/out/{employee_repository,identity_gateway}.py
    │   └── use_cases/{_login_link,link_existing_login,relink_login,unlink_login}.py (novos)
    │       └── deactivate_employee.py
    └── adapters/
        ├── inbound/http/{router,schemas,error_handlers}.py
        └── out/{identity/local_identity_gateway.py,postgres/employee_repository.py}
scripts/check_layout.py
tests/ (unit, contract, integration, e2e, fakes — por Task)
```

## 2. Tasks

### Task 01 — Domínio: transições do vínculo e erros novos

- **Arquivos a criar:** `tests/unit/features/staff/domain/test_employee_login_link.py`
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/domain/entities/employee.py`;
  `src/restaurant_hub/features/staff/domain/exceptions/errors.py`;
  `src/restaurant_hub/features/staff/adapters/inbound/http/error_handlers.py`;
  as contagens das varreduras de erro, se houver (`test_http_error_handlers.py`);
  `tests/e2e/features/staff/test_staff_status_bands.py` (as duas classes em
  `INALCANCAVEIS_POR_HTTP`, motivo "rota nasce na Task 10").
- **O que fazer:** `Employee.assert_link_state(user_id, *, was_active)`,
  `unlink_login(expected, *, was_active)`, `relink_login(expected, user_id)`,
  `deactivate_as_read(expected, *, was_active)` (concept §4); `EmployeeHasNoLoginError`
  e `EmployeeLoginChangedError` (`StaffError`) com entrada 409 no mapa.
- **Detalhes técnicos:** precedências do concept §4; `relink_login` também passa pela
  validação de `user_id` não vazio de `__post_init__`; transições devolvem nova instância.
- **Critério de aceite:** um teste por ramo e por precedência (sem vínculo × mudou ×
  desligado; lido desligado/gravado ativo recusa; lido ativo/gravado desligado não
  recusa); varreduras de erro verdes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff/domain tests/unit/features/staff/adapters/test_http_error_handlers.py tests/unit/test_status_map.py -q --no-cov
  ```
  (a varredura e2e de status roda no Actions)
- **Commit sugerido:** `feat(staff): transições de desvincular, trocar e desligar conforme o lido no registro [3.10/task-01]`

---

### Task 02 — Port: L-UNLINK, L-RELINK e L-DEACT com fake, adapter, contrato e conduta

- **Exceção declarada ao critério 4 de Task atômica (PIPELINE §4.3):** port, fake e
  adapter Postgres na mesma Task. Os três métodos repetem a forma de `link_login`
  (trava, reconstrói, aplica a transição do domínio, grava uma coluna), e a suíte de
  contrato é parametrizada sobre `("fake", "postgres")`: separar o adapter deixaria o
  `lint-and-test` vermelho entre commits.
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/application/ports/out/employee_repository.py`;
  `tests/fakes/features/staff/in_memory_employee_repository.py` (e o store, se a
  escrita morar lá); `src/restaurant_hub/features/staff/adapters/out/postgres/employee_repository.py`;
  `tests/contract/features/staff/test_employee_repository_laws.py`;
  `tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py`;
  `tests/unit/features/staff/application/test_staff_repository_fakes.py` (uma entrada
  por método público do port); `tests/unit/test_check_layout.py` (classificador da
  regra 10: os três métodos são escrita).
- **Acima de 5 arquivos, por totalidade:** as duas varreduras do port são reprovadas
  por método novo.
- **O que fazer:** os três métodos com docstrings normativas (leis do concept §4); fake
  aplica a transição do domínio ao gravado; adapter com `SELECT … FOR UPDATE` no
  endereço de três partes, reconstrução sob o lock, transição, `UPDATE` de uma coluna.
  Contrato: todos os casos de CA7. Conduta com duas conexões, uma por lei (CA10).
- **Critério de aceite:** CA7 e CA10; varreduras do port verdes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/staff -k "not postgres" tests/unit/features/staff/application/test_staff_repository_fakes.py tests/unit/test_check_layout.py -q --no-cov
  ```
  (os ramos `postgres` do contrato e a conduta rodam no Actions, ponto 1)
- **Commit sugerido:** `feat(staff): escritas condicionais de desvincular, trocar e desligar no repositório [3.10/task-02]`

---

### Task 03 — Identity: consulta facade-only da conta por e-mail

- **Arquivos a criar:** `src/restaurant_hub/features/identity/application/use_cases/find_account_by_email.py`;
  `tests/unit/features/identity/application/test_find_account_by_email.py`
- **Arquivos a modificar:** `src/restaurant_hub/features/identity/application/dtos/commands.py`
  e `dtos/results.py` (aditivo); `src/restaurant_hub/features/identity/application/facade.py`
  (aditivo: parâmetro, método, `AccountSummary`, `__all__`); `src/restaurant_hub/composition_root.py`;
  `tests/unit/features/identity/application/test_use_cases_authorize.py` (`_EXCLUSOES`,
  `_FACADE_ONLY`); `tests/unit/features/identity/application/test_facade.py`;
  `tests/contract/features/staff/conftest.py` (constrói a fachada);
  `tests/unit/features/identity/application/test_dtos.py` (`_TOTAL_DE_DTOS`,
  `_RESULT_CLASSES`).
- **Acima de 5 arquivos, por totalidade:** o construtor da fachada é chamado em três
  lugares e o inventário facade-only é varredura; separar deixaria um vermelho.
- **O que fazer:** `FindAccountByEmailUseCase(users)` (concept §4 Identity): e-mail →
  `find_credentials_by_email` → `None` ou `AccountSummaryResult` com memberships
  filtradas pelo `user_id` e `sees_every_unit = tenant is not None and
  user.bypasses_unit_scope()`; `IdentityFacade.find_account_by_email` em primitivos.
- **Critério de aceite:** CA11; dono sem membership ⇒ `sees_every_unit` verdadeiro;
  `platform_admin` ⇒ tenant `None`, falso; membership de terceiro devolvida pelo
  repositório não entra; e-mail malformado sobe `InvalidEmailError`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application tests/unit/features/identity/adapters/test_composition_root_identity.py tests/contract/features/staff -k "not postgres" -q --no-cov
  ```
- **Commit sugerido:** `feat(identity): consulta da conta por e-mail na fachada [3.10/task-03]`

---

### Task 04 — Gateway: lei L-IG6 `find_login_by_email`

- **Exceção declarada ao critério 4:** port e adapter juntos — um método e um adapter que
  só converte primitivos e traduz `InvalidEmailError` (L-IG2), como na Stage 3.8.
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/application/ports/out/identity_gateway.py`;
  `src/restaurant_hub/features/staff/adapters/out/identity/local_identity_gateway.py`;
  `tests/fakes/features/staff/in_memory_identity_gateway.py`;
  `tests/contract/features/staff/test_identity_gateway_laws.py` (e o conftest, se o
  arranjo precisar); `tests/unit/test_check_layout.py` (o pino dos métodos do
  `IdentityGateway` ganha `find_login_by_email` como leitura, fora de
  `GATEWAY_WRITE_METHODS`).
- **O que fazer:** `ExistingLogin` e `find_login_by_email` (concept §4); o fake responde
  dos seus registros (provisionados e de outros papéis, com e-mail, tenant, unidades e
  alcance); L-IG6 na docstring do módulo.
- **Critério de aceite:** CA8 com um corpo de teste só, contra as duas implementações.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/staff/test_identity_gateway_laws.py tests/unit/features/staff/test_bc_independence.py tests/unit/test_check_layout.py -q --no-cov
  ```
- **Ponto 1 do plano de gates:** esperar o `lint-and-test` verde no commit desta Task.
- **Commit sugerido:** `feat(staff): consulta de login existente por e-mail no gateway de identity [3.10/task-04]`

---

### Task 05 — Ponto único da regra de fim de vínculo; R13 pela escrita condicional

- **Arquivos a criar:** `src/restaurant_hub/features/staff/application/use_cases/_login_link.py`;
  `tests/unit/features/staff/application/test_login_link_single_point.py`
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/application/use_cases/deactivate_employee.py`;
  `scripts/check_layout.py`; `tests/unit/test_check_layout.py`; as suítes de R13 que
  observam `update` (`tests/unit/features/staff/application/test_employee_lifecycle.py`
  e vizinhas, só o necessário).
- **Acima de 5 arquivos, por totalidade:** o script de gate e o seu teste andam juntos,
  e a suíte de R13 observa a escrita trocada.
- **O que fazer:** mover `_grants_the_login_access` e a chamada de revogação para
  `end_active_link(employees, gateway, employee)`; R13 = autorizar → ler →
  `end_active_link` → `employees.deactivate(..., expected_user_id=lido,
  expected_active=lido)`. Regra 10: tabela nomeada de auxiliares que escrevem fora do BC
  (`end_active_link`), contada como escrita do use case que a chama. Varredura de AST do
  ponto único (CA9: receptor tipado `EmployeeRepository`).
- **Critério de aceite:** CA9; a suíte de R13 das Stages 3.5/3.8 verde; regra 10 conta a
  chamada e a entrada de `DeactivateEmployeeUseCase` segue viva.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff/application tests/unit/test_check_layout.py -q --no-cov
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `refactor(staff): extrair a regra de fim de vínculo para um ponto único [3.10/task-05]`

---

### Task 06 — Application: elegibilidade da conta e um login por unidade

- **Arquivos a criar:** `tests/unit/features/staff/application/test_resolve_linkable_login.py`
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/application/errors.py`;
  `src/restaurant_hub/features/staff/application/use_cases/_login_link.py`;
  `src/restaurant_hub/features/staff/adapters/inbound/http/error_handlers.py`;
  `tests/e2e/features/staff/test_staff_status_bands.py` (as duas classes em
  `INALCANCAVEIS_POR_HTTP`, motivo "rota nasce na Task 10").
- **O que fazer:** `LoginAccountNotFoundError` (`StaffApplicationError`, 404) e
  `LoginAlreadyLinkedInUnitError` (`StaffError` declarado no módulo de erros de application; status 409);
  `resolve_linkable_login(employees, gateway, email, employee)` (concept §4, R4, R10).
- **Critério de aceite:** recusa uniforme (mesma classe e mensagem) nos quatro casos de
  CA2; dono sem membership aceito; conta atual devolvida sem checagens; R10 sobre ativo e
  desligado da mesma unidade, ignorando outra unidade e o próprio registro.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff/application/test_resolve_linkable_login.py tests/unit/features/staff/application/test_errors.py tests/unit/features/staff/adapters/test_http_error_handlers.py tests/unit/test_status_map.py -q --no-cov
  ```
- **Commit sugerido:** `feat(staff): elegibilidade da conta existente e um login por unidade [3.10/task-06]`

---

### Task 07 — Use case R18: vincular conta existente

- **Arquivos a criar:** `src/restaurant_hub/features/staff/application/use_cases/link_existing_login.py`;
  `tests/unit/features/staff/application/test_link_existing_login.py`
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/application/dtos/commands.py`;
  `src/restaurant_hub/composition_root.py`; as varreduras de use case
  (`test_use_cases_authorize.py`, `test_application_guards.py`, `test_dtos.py`,
  `test_composition_root_staff.py`).
- **Acima de 5 arquivos, por totalidade:** quatro varreduras de use case.
- **O que fazer:** `LinkExistingLoginCommand`, `LinkExistingLoginUseCase` na ordem R7.
- **Critério de aceite:** CA1 (unit), CA3, CA6 (parte R18), CA12 (R18); matriz de
  autorização com os dois alvos.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff -q --no-cov
  ```
- **Ponto 2 do plano de gates:** esperar o `lint-and-test` verde no commit desta Task.
- **Commit sugerido:** `feat(staff): vincular conta existente a um registro [3.10/task-07]`

---

### Task 08 — Use case R20: desvincular

- **Arquivos a criar:** `src/restaurant_hub/features/staff/application/use_cases/unlink_login.py`;
  `tests/unit/features/staff/application/test_unlink_login.py`
- **Arquivos a modificar:** `dtos/commands.py`; `composition_root.py`; `scripts/check_layout.py`
  (`MULTI_WRITE_ALLOWLIST`); `tests/unit/test_check_layout.py`
  (`test_regra10_a_allowlist_nao_cresceu`); as varreduras de use case.
- **Acima de 5 arquivos, por totalidade** (as de T07 mais a allowlist da regra 10).
- **O que fazer:** `UnlinkLoginCommand`, `UnlinkLoginUseCase` na ordem R7.
- **Critério de aceite:** CA4 (R20), CA5 (unit), CA6 (R20); entrada viva na allowlist.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff tests/unit/test_check_layout.py -q --no-cov
  ```
- **Commit sugerido:** `feat(staff): desvincular o login de um registro [3.10/task-08]`

---

### Task 09 — Use case R19: trocar o login

- **Arquivos a criar:** `src/restaurant_hub/features/staff/application/use_cases/relink_login.py`;
  `tests/unit/features/staff/application/test_relink_login.py`
- **Arquivos a modificar:** `dtos/commands.py`; `composition_root.py`; `scripts/check_layout.py`;
  `tests/unit/test_check_layout.py`; as varreduras de use case; `test_login_link_single_point.py` (suíte parametrizada de
  CA4 sobre os três chamadores, agora completos).
- **Acima de 5 arquivos, por totalidade** (as de T08).
- **O que fazer:** `RelinkLoginCommand`, `RelinkLoginUseCase` na ordem R7.
- **Critério de aceite:** CA2 (unit, R18 × R19), CA4 completo, CA6 (R19), CA12 (R19).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff tests/unit/test_check_layout.py -q --no-cov
  ```
- **Commit sugerido:** `feat(staff): trocar o login vinculado a um registro [3.10/task-09]`

---

### Task 10 — HTTP: rotas R18, R19 e R20

- **Arquivos a criar:** `tests/unit/features/staff/adapters/test_http_router_login_link.py`
- **Arquivos a modificar:** `src/restaurant_hub/features/staff/adapters/inbound/http/router.py`;
  `schemas.py` (`ExistingLoginRequest`); `src/restaurant_hub/composition_root.py`
  (`build_http_wiring`); as tabelas de rota das varreduras HTTP de staff (unit) e
  `tests/e2e/features/staff/test_staff_authorization.py`/`tests/e2e/test_deny_by_default.py`;
  `tests/e2e/features/staff/test_staff_status_bands.py` (`_TOTAL_DE_CAMPOS_ESCALARES` com
  o `email` de R18 e R19; `EmployeeHasNoLoginError`, `LoginAccountNotFoundError` e
  `LoginAlreadyLinkedInUnitError` passam de `INALCANCAVEIS_POR_HTTP` a
  `CENARIOS_POR_EXCECAO`; `EmployeeLoginChangedError` fica inalcançável por HTTP
  sequencial — só uma corrida entre requisições o produz, e a conduta de T02 o cobre).
- **Acima de 5 arquivos, por totalidade:** as tabelas de rota das varreduras HTTP.
- **O que fazer:** três rotas no padrão de R17 (validar ids → autorizar `manage_staff` e
  `manage_users` → um use case → `EmployeeResponse`).
- **Critério de aceite:** CA13; CA6 na borda (R18/R19 com e-mail malformado ⇒ 422, unit do
  router); a ordem validar → autorizar travada como nas demais rotas.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff/adapters -q --no-cov
  ```
- **Commit sugerido:** `feat(staff): rotas de vincular, trocar e desvincular o login [3.10/task-10]`

---

### Task 11 — e2e contra Postgres

- **Arquivos a criar:** `tests/e2e/features/staff/test_login_link_management.py`
- **O que fazer:** CA14 (percurso R18 → R19 → R20 → R15 com gerente; dono sem membership
  vinculado; 403/404 do DoD por rota; outro tenant e `platform_admin` em R18 e R19), CA4
  e2e (`POST /auth/refresh` do login antigo depois de R19), CA12 e2e.
- **Comando de verificação:** roda no `lint-and-test` do Actions (Postgres compartilhado
  localmente); localmente `uv run ruff check` e `uv run mypy` no arquivo.
- **Commit sugerido:** `test(staff): e2e da gestão do vínculo de login [3.10/task-11]`

---

### Task 12 — Docs: workforce e notas nos ADRs

- **Arquivos a modificar:** `docs/domain/staff/workforce.md` §3.8 (nota datada);
  notas *append-only* em `docs/adr/3_5_0002-*.md`, `3_5_0004-*.md`, `3_8_0001-*.md`,
  `0_0_0010-*.md`, `2_6_0002-*.md`.
- **Acima de 5 arquivos:** notas mecânicas de supersessão, uma por ADR, que o concept
  §1 lista.
- **Comando de verificação:**
  ```bash
  make docs-check
  ```
- **Ponto 3 do plano de gates (saída).**
- **Commit sugerido:** `docs(staff): registrar a gestão do vínculo no workforce e nos ADRs [3.10/task-12]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check        # cumprido pelo lint-and-test do Actions no head do PR
uv run python scripts/check_technical_postexec.py docs/stages/3.10-login-link-management/technical.md
```

### Verificações funcionais
- [ ] R18 → R19 → R20 → R15 pela API, com gerente real (e2e).
- [ ] As três recusas do DoD em cada rota (e2e).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch, em cada ponto do plano de gates
- [ ] Commit final `stage 3.10: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at` e `last_reviewed_at`
- [ ] ADRs novos em `status: accepted`
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
T01 ─► T02 ─► T05 ─► T06 ─► T07 ─► T08 ─► T09 ─► T10 ─► T11 ─► T12
T03 ─► T04 ─┘
```
T03 e T04 independem de T01/T02; T05 depende de T02 (L-DEACT); T06 de T04 (L-IG6).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Rebase com #206/#211 (mapa de erros, router, fachada, contagens) | resolver somando os dois lados; contagens das varreduras de erro recalculadas |
| Conduta com duas conexões instável no Actions | usar o helper de entrelaçamento existente (`_entrelacar`) e a espera de backend bloqueado do arquivo |
| Suíte de R13 da 3.5/3.8 acoplada a `update` | ajustar só o arranjo, nunca o oráculo; `[deviation]` em §7 |

## 6. Referências

- [`./concept.md`](./concept.md)
- [`../../roadmap.md`](../../roadmap.md) §Stage 3.10; [`../../PIPELINE.md`](../../PIPELINE.md) §4.3, §9.6
- ADRs 3.10.0001, 3.10.0002, 0.0.0010, 2.6.0002, 3.8.0001
- Skills: hex-arch-python, ddd-tactical-patterns, repository-pattern, pytest-with-fakes,
  fastapi-thin-adapter, composition-root, task-ordering-hex

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-11-22 — [decision] Checkpoint B — Claude (Opus 5.5)
**Contexto:** revisão do technical por subagente de contexto zerado (matriz de
rastreabilidade, caminhos, Task atômica, plano de gates e varreduras), em duas rodadas.
**Pergunta:** disposição de cada achado.
**Opções:**
- A — corrigir no technical antes do commit `technical approved` ✅ recomendada
- B — refutar com artefato
**Decisão:** A, para todos — `corrigido` antes do commit `stage 3.10: technical approved`;
a rodada 2 confirmou os oito.
**Razão:** B1 (blocker) — a regra 10 de `tests/unit/test_check_layout.py` fixa os métodos
de escrita do port e os métodos do `IdentityGateway`: T02 e T04 levam o arquivo. B2
(blocker) — `test_staff_status_bands.py` exige cenário ou inalcançável para cada erro do
mapa: T01/T06 marcam inalcançável até T10, que move três para cenário e mantém
`EmployeeLoginChangedError` inalcançável por HTTP sequencial. B3 (blocker) — T10 atualiza
`_TOTAL_DE_CAMPOS_ESCALARES`. M1 — arquivos das varreduras listados nas Tasks (T02, T03,
T08, T09). M2 — "acima de 5 arquivos" declarado em T02, T05, T07–T10. M3 — o 422 de borda
de CA6 entra no critério de T10. M4 — mapa da §1 completo.


### 2026-11-23 — [deviation] Task 01 — contagem do mapa na varredura e2e — Claude (Opus 5.5)
**Contexto:** o `lint-and-test` do commit da Task 01 reprovou `test_staff_status_bands.py::test_toda_excecao_alcancavel_do_mapa_tem_cenario_e2e`: o mapa ganhou duas entradas e `_TOTAL_DE_ENTRADAS_DO_MAPA` ficou na contagem antiga. A Task tinha posto as classes em `INALCANCAVEIS_POR_HTTP`, mas não a cardinalidade.
**Razão:** commit `a112ea8` `[3.10/task-01-fix]`, antes da Task seguinte ter rodado no Actions. Ajuste de contagem, sem mudança de comportamento.

### 2026-11-23 — [deviation] Dois rebases sobre develop — Claude (Opus 5.5)
**Contexto:** o PR ficou em conflito duas vezes com develop (o GitHub não roda workflow em PR em conflito). Primeiro rebase: #206 (mapa de erros de staff com 26 entradas, `JobFunctionEnablementChangedError`) e #201. Segundo: #232 (consulta facade-only `get_unit_timezone`, DTOs de identity 28→30), #211, #225, #199, #210.
**Razão:** resolvido somando os dois lados: `_TOTAL_DE_ERROS_DE_STAFF` e `_TOTAL_DE_ENTRADAS_DO_MAPA` 26 + 4 = 30; `_TOTAL_DE_DTOS` de identity 30 + 2 = 32; o inventário facade-only com `get_unit_timezone` **e** `find_account_by_email`; os comandos e resultados de identity lado a lado; os blocos de conduta da #206/#225 e desta Stage em seções próprias. O rebase deixou um import fora da ordem do ruff na conduta, corrigido em `2cc077c` `[3.10/task-02-fix]`. Nenhuma migration nesta Stage: develop termina na `0007_units_timezone` (#232) e a cadeia não muda.

### 2026-11-23 — [decision] Checkpoint C, bloco T01–T04 — Claude (Opus 5.5)
**Contexto:** revisor de contexto zerado sobre o diff das Tasks 01–04: nenhum achado de contrato ou comportamento; três menores.
**Pergunta:** disposição de cada achado.
**Opções:**
- A — corrigir com commit `-fix` ✅ recomendada
- B — aceitar com registro
**Decisão:** m1 (identificadores `gravado`/`novo` em código de produção) `corrigido` em `dccfbda`; m2 (o fake não tratava o e-mail de conta semeada como em uso) `corrigido` em `923b783`, com caso novo de contrato; m3 (a conduta usa `UPDATE` cru como escritor concorrente, e não `relink_login`/`link_login`) aceito.
**Razão:** m3 prova a mesma propriedade — a escrita da Stage relê o gravado sob o lock e recusa —, e o revisor confirma que tirar o `FOR UPDATE` derruba o teste; usar a operação do port como escritor concorrente exigiria expor a conexão do adapter só para o teste.

### 2026-11-23 — [decision] Checkpoint C, bloco T05–T07 — Claude (Opus 5.5)
**Contexto:** revisor de contexto zerado sobre as Tasks 05–07: dois achados médios e três baixos, todos de cobertura ou de trava.
**Pergunta:** disposição de cada achado.
**Opções:**
- A — corrigir com commit `-fix` ✅ recomendada
- B — escalar como finding
**Decisão:** F1 (a varredura do ponto único não via as transições da entidade, e `update(employee.deactivate())` passaria) `corrigido` em `aa4afd3`; F2 (mutante `expected_active=True` sobrevivia) `corrigido` em `aa4afd3` com o entrelace de recontratação no use case; F4 (cláusula `other.id != employee.id` de R10 sem teste) `corrigido` em `8a1204d`; F3 (a tabela `HELPER_WRITES` da regra 10 é manual) escalado como finding, issue #243; F5 (a trava de ordem compara só linhas) coberto pela suíte CA4 parametrizada sobre R13, R19 e R20 (`f925748`), que pega em runtime a regra pulada ou aplicada ao registro errado.
**Razão:** F3 é melhoria do script de gate com escopo próprio; os demais cabem na Stage.

### 2026-11-23 — [decision] Checkpoint C, bloco T08–T10 — Claude (Opus 5.5)
**Contexto:** revisor de contexto zerado sobre as Tasks 08–10: um achado alto, um médio, um baixo.
**Pergunta:** disposição de cada achado.
**Opções:**
- A — corrigir com commit `-fix` ✅ recomendada
- B — refutar com artefato
**Decisão:** F1 (os campos novos de `Recursos` com default vazio montavam `.../employees//login-link` nos recursos fictícios e no CA13, e o 404 viria do roteador) `corrigido` em `bcc9f66`, sem default; F2 (as guardas de R19/R20 repetidas entre use case e entidade) `corrigido` em `1b7539e` com `assert_can_relink_login`/`assert_can_unlink_login` como casa única, na forma de R18; F3 (efeito de CA11 de PUT/DELETE só conferia a unidade) `corrigido` em `bcc9f66` com efeitos próprios.
**Razão:** os três mudam cobertura ou o dono da regra.

### 2026-11-23 — [measurement] Verificação das citações de D3a, D3b, D5, D7 e D10 do concept — Claude (Opus 5.5)
**Contexto:** a regra decidida com o gate de registros de decisão (PR #235) não aceita `não verificado (§4.2)` em decisão de concept aprovado que entra em port, contrato ou regra de tenant. O concept desta Stage está aprovado (`status: done`), então o resultado fica aqui, por decisão.
**Medição:** `evidence-verifier` de contexto zerado, lendo a fonte bruta de cada citação:
- **D3a** (recusa uniforme): ADR 3.4.0007 §Decision 4 — **sustenta** ("No error confirms the existence of a record the caller may not address").
- **D3b** (404, raiz de aplicação): `error_handlers.py` › `STAFF_ERROR_STATUS` e `application/errors.py` › `JobFunctionNotFoundError(StaffApplicationError)` — **sustenta**.
- **D5** (forma da escrita): **parcial→corrigido**. O trecho de ADR 0.0.0010 Alt. A está em `Cons`, e o motivo da rejeição é outro: "rung 1 — the adapter's own `update` already decides under `FOR UPDATE` before writing … the same form keeps one place for the guards". O de Alt. B ("each gets its own method") é o motivo de rejeitar B, descrevendo a forma escolhida. A decisão se mantém pelo mesmo degrau 1 com a base corrigida: a forma ratificada é "decidir sob `FOR UPDATE` com as guardas do domínio numa casa só, um método por escrita do vínculo".
- **D7** (desligamento confere o vínculo): a regra "registro desligado recusa criar login" (concept 3.5 §5.5; workforce §3.8) **sustenta**. O motivo atribuído ao ADR 3.5.0003 §2 é **parcial→corrigido**: o texto é "writing and then failing to revoke would return an error to the client with the termination already persisted — partial success hidden behind a 500. The order that never hides partial success is revoke → write". A recusa de L-DEACT não grava o desligamento, então não é esse sucesso parcial; a decisão se mantém.
- **D10** (porta da consulta): `UserCredentials.password_hash` com `repr=False`, `find_credentials_by_email` e `list_memberships` existem, e o docstring do port diz que `list_memberships` "não precisa filtrar" — **sustenta**.
**Razão:** nenhuma decisão muda; as duas bases parciais ficam corrigidas aqui, com o trecho literal.

### 2026-11-23 — [measurement] Auditoria de testes — Claude (Opus 5.5)
**Contexto:** gate explícito do PROMPT, por subagente que não escreveu os testes, em duas rodadas.
**Medição:** rodada 1 — itens 1, 2, 4, 5 e 6 satisfeitos com lacunas: falha da **revogação** sem teste em R13/R19/R20 (e um teste de R20 com nome que dizia revogação e testava a consulta de papel), falha de identity dentro da regra em R19, e2e de R20 sobre desligado seguido de R15, e2e de CA2 em R19 sem conferir o login exato; item 3 incompleto. Extra `d5ddcb4` `[3.10/task-13-extra]` fecha as quatro lacunas. Mutação real (`mutate310.py`, cada arquivo restaurado depois; `uv run pytest tests/unit/features/staff/application tests/unit/features/staff/domain tests/unit/features/identity/application tests/contract/features/staff -k "not postgres" -q --no-cov -x`): **21 mutantes, 21 mortos** — 7 em `resolve_linkable_login` (atalho do login atual, tenant, `every_unit` com `and` e ignorado, R10 só ativos, R10 contando o próprio, sem R10), 4 em `end_active_link` (guarda `active`, `shared`, `shared` contando o próprio, revogar sem papel), 3 em `assert_link_state` (sem comparar login, sem a cláusula de recontratação, direção invertida), 1 em `deactivate_as_read`, 4 nos use cases (regra depois da escrita em R19, `expected_active` fixo em R20 e R13, `expected_user_id=None` em R13), 2 em `find_account_by_email` (sem filtro por usuário, `sees_every_unit` sem tenant). Exemplo: `RL5 R10 so ativos: MORTO | FAILED …test_link_existing_login.py::test_ca12_conta_ja_em_outro_registro_da_unidade_e_409_sem_gravar || 1 failed, 562 passed`. Rodada 2 — os seis itens "sim".
**Razão:** o SQL do adapter Postgres não entrou na mutação local (o Postgres é compartilhado); fica coberto pelo contrato `[postgres]` e pela conduta, no Actions.

### 2026-11-23 — [measurement] Plano de gates — Claude (Opus 5.5)
**Contexto:** os pontos do plano cumpridos pelo `lint-and-test` do Actions (orquestração autônoma).
**Medição:** ponto 1 (Task 04 e os seus `-fix`) — run 45104981152, `completed success`, sobre `544f98e` (antes do segundo rebase). Ponto 2 (Task 07) — run 45106386922, `completed success`, sobre `12a84bb`. Ponto 3 (saída) — o run do commit `stage 3.10: complete`, citado no PR.
**Razão:** os hashes dos pontos 1 e 2 mudaram no rebase sobre develop; o veredito vale para o conteúdo das Tasks, que o rebase só somou com develop.

### 2026-11-23 — [finding] staff — resíduo da corrida de fim de vínculo na unidade — Claude (Opus 5.5)
**Contexto:** concept §6.1, D8; ADR 3.10.0001 §6. Um login por unidade fecha o caminho pela API, mas dois vínculos concorrentes da mesma conta em dois registros da unidade ainda podem passar.
**Direção sugerida:** lock por `user_id` numa transação de staff, ou índice único parcial `(tenant_id, unit_id, user_id)`.
**Stage candidata:** issue #241.

### 2026-11-23 — [finding] staff — `update` grava o estado ativo a partir de leitura velha — Claude (Opus 5.5)
**Contexto:** concept §6.1; ADR 3.10.0001 Alt. H. Edição lida antes de uma recontratação devolve o registro a desligado; com um vínculo no meio, termina desligado e vinculado sem a regra.
**Direção sugerida:** escrita própria de `active` (L-REACT), como `user_id`.
**Stage candidata:** issue #242.

### 2026-11-23 — [finding] shared — a tabela `HELPER_WRITES` da regra 10 é manual — Claude (Opus 5.5)
**Contexto:** Checkpoint C, bloco T05–T07, F3.
**Direção sugerida:** derivar a tabela das funções de `use_cases/` que escrevem por parâmetro.
**Stage candidata:** issue #243.

### 2026-11-23 — [finding] identity — consulta de conta por e-mail lê o hash que descarta — Claude (Opus 5.5)
**Contexto:** concept D10: `FindAccountByEmailUseCase` usa `find_credentials_by_email` para não mudar o port de usuários enquanto a #211 editava identity.
**Direção sugerida:** `UserRepository.find_by_email`, com fake, adapter e contrato, quando aparecer o segundo consumidor de leitura por e-mail.
**Stage candidata:** a próxima Stage que toque `features/identity/application/ports/out/user_repository.py`.

### 2026-11-23 — [deviation] Errata dos hashes da §7 depois do rebase da auditoria — Claude (Opus 5.5, auditor)
**Contexto:** a auditoria do PR #230 rebaseou a branch sobre develop três vezes: #238 e #240 (conflito só nas linhas da Tabela de Issues do roadmap, com #246 somada às #241–#243) e #239 (issue #207). No segundo, dois conflitos de teste resolvidos somando os lados: na conduta (`test_staff_conduct.py`), o bloco da #207 e o desta Stage, ambos anexados no fim, ficam em seções próprias (o da #207 primeiro); em `test_use_cases_authorize.py`, `_DE_DOIS_ALVOS` reúne `delete_job_function` e `rename_job_function` da #207 com `link_existing_login`, `relink_login` e `unlink_login`, em ordem; o terceiro (#249) foi limpo. Os hashes curtos citados acima já eram de antes do segundo rebase do implementador e nenhum é ancestral do HEAD (`git merge-base --is-ancestor` falso para os doze).
**Razão:** mapeamento pela mensagem do commit, antigo → novo: `a112ea8` → `fa866da6` (task-01-fix); `dccfbda` → `67906198` (task-02-fix, nomes em inglês); `2cc077c` → `ddc76eaa` (task-02-fix, imports da conduta); `923b783` e `544f98e` → `052cb9a9` (task-04-fix; `544f98e` é o head do run 45104981152 do ponto 1); `12a84bb` → `351a1b77` (task-07, head do run 45106386922 do ponto 2); `aa4afd3` → `d7afa031` (task-05-fix); `8a1204d` → `10b97714` (task-06-fix); `f925748` → `15221e4c` (task-09); `1b7539e` → `78d57e8e` (task-09-fix); `bcc9f66` → `6304fd44` (task-10-fix); `d5ddcb4` → `b5589055` (task-13-extra). Os runs dos pontos 1 e 2 continuam valendo para o conteúdo (conferidos pela mensagem do head: `lint-and-test` `success` nos dois); o único run vermelho da branch é o da Task 01, consertado pelo `-fix` antes da Task 02 (entrada acima).

### 2026-11-23 — [decision:C] Auditoria — o `Verificado:` dos registros do concept aprovado — Claude (Opus 5.5, auditor)
**Contexto:** o concept foi aprovado (`498a5480` `stage 3.10: conceptual approved`, antes dos rebases `183d847c`) com os nove `[decision:C]` em `Verificado: não verificado (§4.2)`, e vários entram em port ou regra de segurança/tenant (D3a, D3c, D5, D7, D8, D9 no contrato OpenAPI, D10). A regra (`evidence-resolution` §5; `stage-audit` Fase C item 9) diz que, nessas classes, o concept não se aprova assim. O `evidence-verifier` rodou depois, na execução (entrada `[measurement]` acima), para D3a, D3b, D5, D7 e D10.
**Pergunta:** a verificação tardia registrada na §7 satisfaz a regra, ou os campos do concept têm de ser reescritos?
**Opções:**
- A — a verificação conta pela §7, completada pela auditoria para os registros que faltavam; os campos do concept ficam como foram aprovados ✅ recomendada
- B — reescrever os campos `Verificado:` no concept com o resultado
- C — regressão `done → draft` do concept e nova aprovação
**Decisão:** A. Escolha: A · Alternativas: B; C · Degrau (C): 1 · Base: CONVENTIONS §5 (concept `done` é registro histórico; a §7 é a única parte editável depois do `done`, §3.4) e o docstring de `scripts/check_decision_records.py` › "O corte" ("Reescrevê-los com um valor do vocabulário seria afirmar hoje uma verificação que ninguém fez" — aqui ela foi feita, mas depois da aprovação, e o campo afirmaria um momento falso) · Verificado: não verificado (§4.2) — decisão de processo, fora das quatro classes · Configuração candidata: nenhuma · Reversível: sim.
**Razão:** o que a regra protege é que nenhuma decisão de port ou de segurança chegue ao merge sem a citação conferida na fonte bruta; isso está cumprido antes do merge (a entrada acima e a seguinte). O que não se repõe é o momento: a aprovação do Checkpoint A foi dada sem o verificador, e isso fica registrado aqui como achado corrigido, não apagado. O gate de forma (`check_decision_records.py`, #212) entrou em develop depois da aprovação e aceita o termo; reescrever o concept (B) passaria no gate e violaria a CONVENTIONS, e a regressão (C) desfaria a aprovação de uma Stage já executada sem mudar nenhuma decisão.

### 2026-11-23 — [measurement] Auditoria — verificação das citações de D3c, D6, D8 e D9 — Claude (Opus 5.5, auditor)
**Contexto:** os quatro registros `[decision:C]` do concept que a execução não verificou; D3c entra no port do gateway (L-IG6) e na fachada, D8 numa regra de segurança (quem recebe login, corrida de revogação), D9 no contrato OpenAPI; D6 é a casa da regra de revogação.
**Medição:** `evidence-verifier` de contexto zerado, lendo a fonte bruta:
- **D3c** (a consulta não devolve papel) — **sustenta**: ADR 3.8.0001 › Alternative F, "the boolean keeps the vocabulary at the edge; widening it later is additive"; ADR 2.1.0002 › Decision, "`None` is valid **iff** `role == Role.PLATFORM_ADMIN`", e `User.link_to_unit` recusa `platform_admin` com `PlatformAdminMembershipError`.
- **D6** (auxiliar `_` em `use_cases/`) — **sustenta**: `_unit_enablement.py` ("Módulo privado (prefixo `_`, ...): não é use case", recebe `AccessGuard`) e `_invitation.py` ("não é um use case — não entra no wiring e não tem `execute`", `deliver_invitation` recebe `EmailSender`).
- **D8** — o dono da corrida **sustenta** (ADR 3.8.0001 › `### Negative`, "Owner: the Stage that implements "link an existing login" … with a lock per `user_id` … A Unit of Work alone does not close it"; ADR 2.6.0002 §2, "Staff: no unit, and no transaction across BCs"). A base do fork P de R10 é **parcial→corrigido**: workforce §3.1 e ADR 3.1.0001 (iii) dizem "pode ter vários registros de funcionário (um por unidade)" como parêntese descritivo de uma frase sobre cópia entre unidades, não como invariante, e o próprio ADR 3.8.0001 tratava dois registros da unidade com um login como caso possível. A recusa de R10 é regra **nova** desta Stage, fixada pelo fork P delegado (D8) e registrada na nota de 2026-11-23 do workforce §3.8, com o parêntese do §3.1 como apoio — não "a regra canônica". A decisão se mantém: o motivo que a sustenta é fechar pela API o caminho que tornaria produzível a corrida de que a Stage é dona.
- **D9** (sub-recurso `login-link`, 200 com `EmployeeResponse`) — **sustenta**: R13 (`/termination`) e R14 (`/rehire`) são `@router.post(..., response_model=EmployeeResponse)` sem `status_code` (200); as três rotas novas seguem a forma. R17 (`/login`) responde 201 com `EmployeeLoginResponse`: serve de precedente só para o path do sub-recurso.
**Razão:** com esta entrada e a `[measurement]` da execução, os nove registros do concept têm a citação conferida; nenhuma decisão muda.

### 2026-11-23 — [measurement] Auditoria — mutação do DoD de acesso — Claude (Opus 5.5, auditor)
**Contexto:** a Stage decide quem ganha login sobre qual registro. A auditoria aplicou, uma por vez e restaurando, as mutações que o DoD proíbe, e pôs `_login_link.py` no escopo do job `mutation-access-modules` (`70e342e6`; antes dos rebases sobre a #239 e a #249, `e078b80a`).
**Medição:** local, `uv run pytest tests/unit/features/staff tests/unit/test_check_layout.py tests/contract/features/staff -k "not postgres" -q --no-cov -x` — **10 mutantes, 10 mortos**: M1 sem a checagem de tenant da conta, M2 `platform_admin` aceito, M3 sem o alcance da unidade (os três por `test_http_router_login_link.py::test_ca2_as_recusas_da_conta_tem_o_mesmo_404_e_o_mesmo_corpo[POST]`); M4a/M4b R20/R19 sem `end_active_link` (`test_login_link_single_point.py::test_toda_escrita_que_encerra_vinculo_vem_depois_do_ponto_unico`); M4c R13 sem o ponto único; M5a R13 gravando por `update(employee.deactivate())` (`test_employee_lifecycle.py::test_ca05_registro_unico_de_funcionario_revoga_antes_de_gravar_na_ordem`); M5b fake e M5c domínio de L-DEACT sem conferir o vínculo (`test_r13_que_leu_sem_vinculo_e_recusado_por_um_vinculo_concorrente`); M6 sem um login por unidade (`test_r18_conta_ja_em_outro_registro_da_unidade_e_409`). Adapter Postgres, em PRs descartáveis fechados e apagados: #250 (L-DEACT grava com `stored.deactivate()`, sem conferir) — `lint-and-test` vermelho, `5 failed`: `test_l_deact_lido_desligado_e_gravado_ativo_e_recusado[postgres]`, `test_l_deact_login_gravado_diferente_do_lido_e_recusado[postgres-vinculado_no_meio|trocado_no_meio|desvinculado_no_meio]` e a conduta `[l_deact_vinculo_concorrente]`; #251 (`_transition_under_lock` sem `FOR UPDATE`) — `5 failed`: as três condutas de CA10 (`[l_deact_vinculo_concorrente]`, `[l_relink_troca_concorrente]`, `[l_unlink_troca_concorrente]`) e as duas da issue #68, o que confirma a refutação de m3 do Checkpoint C (T01–T04). Job `mutation-access-modules` (run 45116013369, `workflow_dispatch` sobre `e078b80a`): **324 mutantes, 1 sobrevivente** — `x_resolve_linkable_login__mutmut_13`, `LoginAccountNotFoundError(None)` no lugar do e-mail (as mensagens seguiam iguais entre si). Morto por `test_a_recusa_cita_o_email_enviado` (`56690f57`; aplicado à mão, derruba só esse teste). Nova corrida (run 45120785756 sobre `da72445e`): **324 mutantes, 0 sobreviventes**. A corrida intermediária (run 45119178721) reprovou na suíte do código original: a trava nova do ponto único (entrada seguinte) lia as cópias `x_end_active_link__mutmut_*` do módulo mutado como revogação fora do ponto único — corrigido em `da72445e`.
**Razão:** cada transição que o DoD cerca derruba teste quando a cerca some, nas três camadas em que ela mora (use case, domínio, adapter).

### 2026-11-23 — [decision] Auditoria — a regra 10 diante do auxiliar que revoga — Claude (Opus 5.5, auditor)
**Contexto:** `end_active_link` revoga sessões (`revoke_login_sessions`, de `GATEWAY_WRITE_METHODS`) de dentro de uma função de módulo, e a regra 10 só enxerga escrita por `self.<atributo>.<método>`; a Stage pôs a função em `HELPER_WRITES` e deixou a derivação da tabela para a #243. A auditoria mediu, com `scripts/check_layout.py --src` sobre cópias de `src/`: (1) tirar `RelinkLoginUseCase` da `MULTI_WRITE_ALLOWLIST` reprova ("2 escritas e estas fora de unidade: end_active_link() (linha 94), self._employees.relink_login (linha 95)"), e o mesmo vale para cada chamador; (2) um use case **novo** que chama `end_active_link` e grava em staff, fora da allowlist, **reprova** (fail-closed); (3) um auxiliar **novo**, fora da tabela, que recebe o gateway e revoga **passa** na regra 10. No caminho que revoga sessões, (3) já é recusado pela varredura de AST do ponto único quando o auxiliar mora em outro módulo (`test_revogacao_e_consulta_de_papel_so_no_ponto_unico` reprovou o `_sneaky.py` sintético); sobrava uma segunda função **dentro** de `_login_link.py`.
**Pergunta:** fechar o ponto cego no escopo ou segurar o fechamento até a #243?
**Opções:**
- A — fechar no escopo o caminho da revogação: as duas chamadas exclusivas só no corpo de `end_active_link`, com controle negativo; a derivação geral da tabela (escrita de repositório por parâmetro, outros métodos do gateway) segue na #243 ✅ recomendada
- B — bloquear o merge até a #243
**Decisão:** A, em `fb5d3b75` (`test_no_modulo_do_ponto_unico_so_end_active_link_revoga`; a segunda função sintética no módulo reprovou).
**Razão:** com a trava nova, toda revogação de sessão em `use_cases/` de staff passa por `end_active_link`, que a regra 10 conta em cada chamador; o que fica para a #243 não alcança sessões (escrita de repositório por parâmetro num auxiliar, que hoje não existe), e o teste-guarda de identity do PR #245 (`test_setup_token_issuance_rule10.py`) é precedente de forma para ela.

<!-- END: post-execution -->

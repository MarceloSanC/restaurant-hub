---
title: Technical — Vínculo de login do funcionário
description: Plano de execução da Stage 3.5 — 12 Tasks (1 Task = 1 commit) que levam o registro de funcionário a carregar um login criado pelo gerente e completado pelo próprio funcionário, atravessando a fronteira staff→identity por fachada + gateway
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem arquivos, critério de aceite e comando de verificação; consultar a §7 para o que aconteceu de fato
keywords: [technical, plano de execução, employee-login-link, identity-gateway, facade, setup-link, user_id, staff, identity]
status: done
created_at: 2026-09-13
updated_at: 2026-09-13
stage_id: 3.5-employee-login-link
stage_title: Vínculo de login do funcionário
step_id: 3
step_title: Equipe da unidade
depends_on: [3.6-staff-http]
concept_ref: ./concept.md
issue_id: 51
branch: feat/51-3-5-employee-login-link
tasks_count: 12
---

# Technical — Stage 3.5 — Vínculo de login do funcionário

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução) —
>    em especial **"As totalidades da 3.6 ditam o recorte"**.
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação. **Re-hidratar** a Task e a §4/§5 do
>    [`concept.md`](./concept.md) antes de implementar — nunca de memória.
> 4. **Não avançar para a próxima Task sem verificação verde** — o baseline é
>    `make check` (a suíte **inteira**) verde antes de **todo** commit, além
>    dos checks da Task.
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.5/task-NN]`, rodapé `Refs #51`,
>    **subject ≤ 100 caracteres** (`scripts/check_commit_msg.py`).
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 3.5: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/51-3-5-employee-login-link`. Não há sub-PRs internos.

## 1. Contexto e estratégia de execução

### Resumo

Acrescentar ao registro de funcionário um vínculo opcional com um login de
identity, criado pelo gerente por uma rota nova de staff (R17) e completado
pelo próprio funcionário por um link de primeiro acesso — entregue por e-mail
ou devolvido ao gerente —, com o desligamento revogando as sessões desse login
e a remoção recusando registro vinculado. A travessia entre os dois BCs nasce
na forma canônica que o ADR 3.5.0001 fixa: **fachada** em identity (`Open Host
Service`, tipos primitivos), **gateway** em `staff/adapters/out/identity/`,
**um** par nomeado de `ignore_imports`.

### Estratégia

**As totalidades da 3.6 ditam o recorte.** Diferente da 3.6 — cujas varreduras
de totalidade nasceram na Task de wiring, depois de todo o código —, aqui elas
**já existem** e derivam o domínio do código a cada `make check`:

| Varredura (arquivo:linha hoje) | O que deriva | Consequência para o recorte |
|---|---|---|
| `test_http_error_handlers.py:71-84` `test_ca17_o_mapa_e_total_sobre_staff_error` | `StaffError.__subclasses__` | toda exceção nova de staff entra **no mesmo commit** que a sua entrada em `STAFF_ERROR_STATUS` — por isso as **cinco exceções e o mapa são a Task 01**, antes do domínio que as levanta |
| `test_staff_status_bands.py:540-555` `CENARIOS_POR_EXCECAO \| INALCANCAVEIS_POR_HTTP == entradas do mapa` | as chaves do mapa | as cinco entram em `INALCANCAVEIS_POR_HTTP` na Task 01 (é **verdade**: R17 não existe) e migram para `CENARIOS_POR_EXCECAO` na Task 11, quando passam a ser alcançáveis |
| `test_composition_root_staff.py:136-151` `test_ca18_a_lista_deste_teste_cobre_a_pasta_de_use_cases_inteira` | `use_cases/*.py` (só `__init__` excluído) ↔ lista literal ↔ contêiner | `_results.py` exige excluir módulos `_`-prefixados (Task 03); **um use case novo só pode nascer no commit que o põe no contêiner** — e o contêiner só tem gateway a partir da Task 09 |
| `composition_root.py:601` constrói `DeactivateEmployeeUseCase(employees=...)`; `test_http_router_job_functions.py:163-190` constrói use cases por reflexão com `disponiveis = {employees, job_functions, id_generator}` | assinatura dos construtores | mudar a assinatura de `Deactivate` quebra `create_app()` (todo e2e) e as cinco `Ambiente` dos testes de router — logo o gateway precisa estar **wired antes** (Task 09) e a mudança de assinatura vai **junto** com o seu wiring e com `disponiveis["gateway"]` (Task 10) |
| `test_composition_root_staff.py:963-1041` provedores `_get_*` ↔ overrides (17) ↔ rotas (16); `test_staff_authorization.py:364-374` `set(ROTAS) == rotas registradas`; `test_http_boundary_sweeps.py` `_INVOCACOES` total sobre `router.routes`, `_TOTAL_DE_AUTORIZACOES = 17`, `_TOTAL_DE_CAMPOS_ESCALARES = 13`; `test_http_path_addresses_the_record.py:82-88` toda rota com `{unit_id}` | `router.routes` | a rota **nasce no mesmo commit** que o seu override, a sua declaração `INVOCACOES`, a sua entrada em `ROTAS` e as cardinalidades novas (Task 11) |
| `tests/contract/features/staff/test_no_implementation_branching.py:103` `glob("test_*laws*.py") == _MODULOS_DE_LEI`, mais os quatro guardas de AST sobre cada módulo de lei (todo teste recebe a fixture de implementações; nenhum corpo toca `request`/`param`/`getfixturevalue`; nenhum literal de implementação) | a pasta de contrato | a suíte de leis do gateway (Task 04) entra na lista **e** sob os guardas no mesmo commit — a fixture parametrizada mora no `conftest.py` e o guarda "recebe a fixture" é generalizado por módulo (`repos` para os repositórios, `gateway` para o port novo) |
| `tests/unit/features/identity/application/test_dtos.py:214` `_TOTAL_DE_DTOS = 21` (igualdade exata sobre seis módulos) e `:264` `vars(results) == _RESULT_CLASSES` (literal de 5) | os DTOs de identity | os três commands e o result novos (Task 07) entram nas duas listas no mesmo commit |

Cada Task é **verde sozinha** — é o critério #1 de PIPELINE §4.3 levado a sério
contra gates que já existem. O preço é que **sete Tasks ultrapassam ~5
arquivos** (01, 03, 05, 07, 09, 10, 11 — cada uma declara a exceção no
próprio item): em todas o excesso é **a mesma mudança propagada pelos testes
que a medem**, não trabalho de natureza diferente. A contagem do concept §12
("cinco") foi feita antes de o Checkpoint B mapear as totalidades; a diferença
é de forma, não de escopo, e fica registrada em §7 na execução.

**Duas frentes, inside-out, e a ordem entre elas é a exceção declarada ao
default da skill `task-ordering-hex`:**

1. **Staff sem identity (Tasks 01–05):** erros + mapa → domínio → result/mapper →
   port + fake + leis → persistência. Ao fim da Task 05 o BC tem `user_id`
   ponta a ponta na persistência e o port com a sua segunda implementação —
   mas **nenhum use case novo** ainda (ver a tabela: ele só pode nascer com o
   gateway wired).
2. **Identity (Tasks 06–08):** a regra do VO `Email`, os três use cases + helper,
   a fachada. É a exceção ao default *"adapter real depois do fake"*: o adapter
   de staff (Task 09) depende de código que **não existe** em identity. Cada
   Task de identity é verificada pela suíte inteira de identity (CA16).
3. **A costura (Tasks 09–12):** gateway + aresta + wiring do gateway → use cases
   do ciclo de vida com o seu wiring → borda HTTP com override, declarações e
   cardinalidades → e2e do fluxo.

**Um campo, um mapper (Task 03 antes de qualquer consumidor).** `EmployeeResult`
ganha `user_id` (com default `None`, espelhando `Employee.user_id` — sem o
default, sete construções diretas em seis módulos de teste quebrariam) e os 11
sítios colapsam num mapper **antes** de o use case novo existir. O default é
seguro **porque** CA06 proíbe construção direta em `use_cases/`: quem passa pelo
mapper nunca esquece o campo.

**As leis do port nascem como suíte de contrato (Task 04), parametrizada só
sobre o fake; a Task 09 acrescenta o parâmetro real** (ADR 3.3.0007).

**Escopo estrito por Task.** Só os arquivos listados. Nenhuma Task pode crescer
sem entrada em §7; a 13ª Task reabre o corte do concept §13 Q6.

### Pré-condições

- Stage `3.6-staff-http` `done` e mergeada (PR #44) — `develop` em `bd7757b`.
- `concept.md` desta Stage em `status: done` (commit `8e9d86a`).
- Postgres real disponível para integração/contrato/e2e (ADR 2.3.0001); as
  fixtures de `tests/conftest.py` já provisionam o banco da worktree.
- `uv sync --extra dev` executado; receita Windows da memória
  `make-on-windows-recipe` (PowerShell, `PATH += msys64` **append**,
  `UV_SYSTEM_CERTS=1`).

### Premissas técnicas (medidas no Checkpoint B)

- Python 3.12, FastAPI 0.111+, SQLAlchemy 2 Core, Alembic, Pydantic v2,
  import-linter 2.13 (wildcard `*` em `ignore_imports` casa nome de módulo).
- `Employee` e `EmployeeResult` são `frozen`; `EmployeeResult` **não tem nenhum
  campo com default** hoje; a cópia constrói campo a campo
  (`copy_employee_to_unit.py:71`).
- Contagens transcritas que esta Stage desloca: `STAFF_ERROR_STATUS` 18 → 23
  (`test_http_error_handlers.py:33`; `test_staff_status_bands.py:530`);
  `test_composition_root_staff.py` 16 use cases / 17 overrides / 16 rotas /
  10 de identity → 17 / 18 / 17 / 10; `test_staff_authorization.py`
  16/12/10/32/48 e `_TOTAL_DE_ROTAS_COM_ENTRADA = 10` → 17/13/11/34/51 e 11;
  `test_staff_status_bands.py` `_TOTAL_DE_CAMPOS_ESCALARES = 13` → 15
  (`email`, `delivery` são folhas string do corpo); `test_http_boundary_sweeps.py`
  `_TOTAL_DE_CAMPOS_ESCALARES = 13` → 15 e `_TOTAL_DE_AUTORIZACOES = 17` → 19
  (AST de `.authorize(` nos handlers; R17 tem duas); `test_application_guards.py`
  `_USE_CASES_ESPERADOS = 16` → 17 e `permitidos` de tipos de retorno ganha
  `EmployeeLoginResult`; `test_dtos.py` `_DTOS_ESPERADOS = 14 + 2 + 2` →
  `15 + 2 + 3` e `_COMMANDS_DE_REGISTRO_EXISTENTE_ESPERADOS = 10` → 11.
- `RecordingEmailSender(fail_with=...)` já existe (2.5) — é o knob de falha do
  lado real de L-IG2.
- A regex de `Email` aceita `\x00`; `users.email` é `TEXT`; **nenhum** teste de
  identity usa NUL em e-mail hoje (`grep -rn "x00" tests/*/features/identity` →
  vazio) — a regra nova não quebra nada existente.
- `definir-senha` aparece em **dois** módulos de `src/`: `invite_user.py:209` e
  `request_password_reset.py:147`; **nenhum** teste hoje assere o formato do
  link (só `"token=" in body`).
- `test_http_boundary_sweeps.py:150-181` deriva `_INVOCACOES` dos módulos
  `test_http_router_*` (dict `INVOCACOES`); `test_application_guards.py:39-44`
  e (após a Task 03) `test_composition_root_staff.py` excluem módulos
  `_`-prefixados da pasta de use cases.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                   (T09, T10, T11)
├── shared/infrastructure/config/settings.py              (T09)
├── features/identity/
│   ├── domain/value_objects/email.py                     (T06)
│   └── application/
│       ├── facade.py                                     (T08) NOVO
│       ├── dtos/{commands,results}.py                    (T07)
│       └── use_cases/
│           ├── _invitation.py                            (T07) NOVO
│           ├── provision_account.py                      (T07) NOVO
│           ├── send_invitation.py                        (T07) NOVO
│           ├── revoke_all_sessions.py                    (T07) NOVO
│           ├── invite_user.py                            (T07: import + _enviar_convite delega)
│           └── request_password_reset.py                 (T07: import + linha do link)
└── features/staff/
    ├── domain/
    │   ├── exceptions/errors.py                          (T01)
    │   ├── value_objects/identifiers.py                  (T02)
    │   └── entities/employee.py                          (T02)
    ├── application/
    │   ├── errors.py                                     (T01)
    │   ├── dtos/{commands,results}.py                    (T03, T10)
    │   ├── ports/out/identity_gateway.py                 (T04) NOVO
    │   └── use_cases/
    │       ├── _results.py                               (T03) NOVO
    │       ├── <11 use cases que devolvem funcionário>   (T03)
    │       ├── create_login_for_employee.py              (T10) NOVO
    │       └── deactivate_employee.py, delete_employee.py (T10)
    └── adapters/
        ├── in/http/error_handlers.py                     (T01)
        ├── out/postgres/{tables,mappers}.py              (T05)
        ├── out/identity/{__init__,local_identity_gateway}.py  (T09) NOVO
        └── in/http/{schemas,dependencies,router}.py      (T11)
migrations/versions/0004_employees_user_id.py             (T05) NOVO
.importlinter                                             (T09)
tests/
├── fakes/features/staff/in_memory_identity_gateway.py    (T04) NOVO
├── unit/features/staff/…                                  (T01–T05, T10, T11)
├── unit/features/staff/test_bc_independence.py           (T09)
├── unit/features/identity/…                               (T06–T08, T09)
├── unit/shared/test_settings.py                          (T09)
├── contract/features/staff/test_identity_gateway_laws.py (T04, T09) NOVO
├── integration/features/staff/adapters/out/postgres/…    (T05)
└── e2e/features/staff/{test_staff_status_bands (T01, T11), test_staff_authorization (T11), test_employee_login_flow (T12) NOVO}.py
    e2e/features/identity/test_status_bands.py            (T12)
```

## 2. Tasks

> Faixa saudável: **3–12 Tasks por Stage**. Esta Stage tem **12** — no teto,
> sem margem (concept §12). Se a execução revelar a 13ª, **parar** e reabrir o
> corte de §13 Q6 do concept (identity vira Stage própria), não dividir staff.

### Task 01 — As cinco exceções de login e as suas entradas no mapa de status

- **Arquivos a modificar (7 — exceção declarada: a totalidade de
  `STAFF_ERROR_STATUS` obriga exceção e entrada a nascerem juntas, e a
  partição do e2e obriga a declaração de inalcançabilidade no mesmo commit):**
  - `src/restaurant_hub/features/staff/domain/exceptions/errors.py`
  - `src/restaurant_hub/features/staff/application/errors.py`
  - `src/restaurant_hub/features/staff/adapters/in/http/error_handlers.py`
  - `tests/unit/features/staff/domain/test_exceptions.py`
  - `tests/unit/features/staff/application/test_errors.py`
  - `tests/unit/features/staff/adapters/test_http_error_handlers.py`
  - `tests/e2e/features/staff/test_staff_status_bands.py`
- **O que fazer:** no domínio, `EmployeeAlreadyHasLoginError(StaffError)` e
  `TerminatedEmployeeLoginError(StaffError)` (docstrings citam ADR 3.5.0004 §2
  e concept §5.5). Na application, `LoginEmailAlreadyInUseError(StaffError)`
  (mensagem cita **só** o e-mail enviado), `InvalidLoginEmailError(StaffError)`,
  `EmployeeHasLoginError(StaffError)` (mensagem: o registro tem login e a
  remoção é recusada — desligue-o; docstring cita ADR 3.5.0003 §1b e a
  irmandade com `EmployeeInUseError`). Em `error_handlers.py`, cinco entradas
  (409: `EmployeeAlreadyHasLoginError`, `TerminatedEmployeeLoginError`,
  `LoginEmailAlreadyInUseError`, `EmployeeHasLoginError`; 422:
  `InvalidLoginEmailError`), cada uma com o comentário de faixa do padrão do
  módulo. Testes: `test_exceptions.py`/`test_errors.py` asserem herança só de
  `StaffError` (não `NotFoundError`); `test_http_error_handlers.py` passa a
  `_TOTAL_DE_ERROS_DE_STAFF = 23` (11 do domínio, 12 da aplicação) e a tabela
  par a par de CA18 ganha as cinco; `test_staff_status_bands.py`:
  `_TOTAL_DE_ENTRADAS_DO_MAPA = 23` e as cinco em `INALCANCAVEIS_POR_HTTP` com
  comentário datado *"inalcançáveis até a Task 11 desta Stage criar R17 e a
  guarda de R15; migram para `CENARIOS_POR_EXCECAO` lá"*.
- **Critério de aceite (CA20 unitária; §5.11):** `test_ca17_o_mapa_e_total_sobre_staff_error`
  verde com 23; par a par verde; `test_toda_excecao_alcancavel_do_mapa_tem_cenario_e2e`
  verde com a partição atualizada; nenhum produtor das exceções existe ainda
  (grep `raise EmployeeHasLoginError` em `src/` → vazio — a Task é declaração).
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff -q
  uv run pytest tests/e2e/features/staff/test_staff_status_bands.py -q -k "cenario_e2e or alcancavel"
  make check
  ```
- **Commit sugerido:** `feat(staff): cinco exceções de login e as suas entradas no mapa de status [3.5/task-01]`

---

### Task 02 — Domínio de staff: `UserId`, `user_id`, `link_login` e as guardas

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/domain/value_objects/identifiers.py`
  - `src/restaurant_hub/features/staff/domain/entities/employee.py`
  - `tests/unit/features/staff/domain/test_employee.py`
  - `tests/unit/features/staff/domain/test_identifiers.py`
- **O que fazer:** `UserId = NewType("UserId", str)` (docstring: id do login em
  identity, opaco, tipado por staff; a semântica **não** restringe o papel do
  `User` — concept §4). Em `Employee`: campo `user_id: UserId | None = None`
  (**depois** de `active`); `__post_init__` recusa `user_id` presente e
  vazio/só-whitespace com `InvalidIdentifierError("login do funcionário")`;
  `assert_can_link_login()` levanta `EmployeeAlreadyHasLoginError` se
  `user_id is not None` e, **depois**, `TerminatedEmployeeLoginError` se `not
  active`; `link_login(user_id) -> Employee` chama `assert_can_link_login()` e
  devolve `dataclasses.replace(self, user_id=user_id)`. Docstring de `Employee`
  ganha o campo com a frase "a cópia não o carrega — a construção campo a campo
  do clone nunca o nomeia (ADR 3.2.0003, 3.5.0004 §5)".
- **Critério de aceite (CA01):** sem `user_id` ⇒ `None`; `UserId("")` e
  `UserId("  ")` ⇒ `InvalidIdentifierError` (direto e via `link_login`);
  `link_login(uid)` devolve instância nova com `user_id == uid` e os demais
  campos iguais; `assert_can_link_login` **e** `link_login` direto levantam
  `EmployeeAlreadyHasLoginError` para vinculado e `TerminatedEmployeeLoginError`
  para desligado; desligado **e** vinculado ⇒ `EmployeeAlreadyHasLoginError`
  (precedência, teste dedicado); `deactivate()` de vinculado mantém `user_id`;
  `test_identifiers.py` lista `UserId` entre os NewTypes.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/domain -q
  uv run mypy src/restaurant_hub/features/staff/domain
  make check
  ```
- **Commit sugerido:** `feat(staff): vínculo de login no registro de funcionário com as duas guardas [3.5/task-02]`

---

### Task 03 — `EmployeeResult.user_id` e o mapper único (11 sítios → 1)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/_results.py`
- **Arquivos a modificar (16 — exceção declarada: um campo atravessa 11 sítios
  de construção com a mesma mudança mecânica, e dois testes de totalidade
  precisam aprender a ignorar o módulo `_`-prefixado):**
  - `src/restaurant_hub/features/staff/application/dtos/results.py`
  - os 11 use cases que constroem `EmployeeResult`: `assign_job_functions.py`,
    `change_workload_profile.py`, `copy_employee_to_unit.py`, `create_employee.py`,
    `deactivate_employee.py`, `declare_shift_preference.py`, `list_employees.py`,
    `reactivate_employee.py`, `register_unavailability.py`,
    `remove_unavailability.py`, `rename_employee.py`
  - `tests/unit/features/staff/application/test_dtos.py`
  - `tests/unit/features/staff/application/test_copy_employee_to_unit.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **O que fazer:** `EmployeeResult` ganha `user_id: UserId | None = None` como
  **último** campo (docstring: o vínculo; `None` = sem login; default espelha a
  entidade e é seguro porque CA06 proíbe construção direta em `use_cases/`).
  `_results.py` expõe `employee_result(employee: Employee) -> EmployeeResult`,
  a **única** função que constrói o DTO (docstring cita Gate 8 da #45 e concept
  D6). Os 11 use cases trocam a construção inline pela chamada. Em `test_dtos.py`,
  **substituir** `test_nenhum_result_carrega_vinculo_de_login` por: `EmployeeResult`
  tem `user_id`; igualdade por valor com `user_id` divergente ⇒ `!=`; varredura
  por AST de `application/use_cases/*.py` (excluído `_results.py`) sem `Call` a
  `EmployeeResult` e com `_TOTAL_DE_CONSUMIDORES_DO_MAPPER = 11` módulos
  importando `employee_result` (a Task 10 sobe para 12); `_DTOS_ESPERADOS`
  inalterado nesta Task (nenhum DTO novo). Em `test_copy_employee_to_unit.py`, o
  teste "a cópia não carrega vínculo" passa de vacuoso a real: origem com
  `user_id` (via `link_login`) ⇒ clone com `user_id is None` e origem relida
  mantém o seu (CA04). Em `test_composition_root_staff.py`,
  `test_ca18_a_lista_deste_teste_cobre_a_pasta_de_use_cases_inteira` passa a
  excluir módulos `_`-prefixados (mesma forma de `test_application_guards.py:39-44`).
- **Detalhes técnicos:** o mapper preenche **todos** os campos a partir da
  entidade; nenhum use case passa `user_id` à mão. `copy_employee_to_unit.py`
  continua construindo o clone campo a campo **sem** nomear `user_id` (trava de
  CA04).
- **Critério de aceite (CA04, CA06):** suíte de `tests/unit/features/staff`
  verde (nenhum comportamento muda); `grep -rn --include="*.py" "EmployeeResult("
  src/restaurant_hub/features/staff/application/use_cases/` devolve **só**
  `_results.py`.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff -q
  uv run mypy src/restaurant_hub/features/staff/application
  make check
  ```
- **Commit sugerido:** `refactor(staff): EmployeeResult.user_id e mapper único nos use cases de funcionário [3.5/task-03]`

---

### Task 04 — Port `IdentityGateway`, fake e leis (contrato só sobre o fake)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/ports/out/identity_gateway.py`
  - `tests/fakes/features/staff/in_memory_identity_gateway.py`
  - `tests/contract/features/staff/test_identity_gateway_laws.py`
- **Arquivos a modificar:**
  - `tests/contract/features/staff/conftest.py`
  - `tests/contract/features/staff/test_no_implementation_branching.py`
- **O que fazer:** o módulo do port com `LoginDelivery(StrEnum)` (`EMAIL`,
  `LINK`), `ProvisionedLogin` (`user_id: UserId`, `setup_link: str =
  field(repr=False)`), `IdentityGateway(Protocol)` com
  `provision_employee_login(*, email, tenant_id, unit_id, delivery)`,
  `send_login_invitation(*, email, setup_link)`, `revoke_login_sessions(user_id)`
  e as leis L-IG1…L-IG4 como texto normativo (concept §4 — copiar a redação).
  O fake: ledger `logins: dict[UserId, tuple[str, TenantId, UnitId]]` com
  `user_id` novo por chamada (`login-1`, `login-2`…), `setup_link`
  determinístico por login, `calls: list[str]` no formato de `InMemoryAccessGuard`,
  knobs `used_emails: set[str]`, `invalid_emails: set[str]`, `raw_error:
  Exception | None` (levantado por `provision_employee_login`), `fail_send_with:
  Exception | None` (levantado por `send_login_invitation`), `revoked:
  list[UserId]`. **A suíte de contrato nasce sob os guardas de
  `test_no_implementation_branching.py`** (o glob `test_*laws*.py` a alcança no
  mesmo commit): a fixture parametrizada **`gateway`** mora no `conftest.py` de
  contrato — `IMPLEMENTACOES_DO_GATEWAY = ("fake",)` (constante própria, ao
  lado da dos repositórios; a Task 09 acrescenta `"real"`) — e devolve um
  holder `GatewaySobContrato` com o gateway, duas funções de observação —
  `login_role_of(user_id) -> str | None` (fake devolve `None`) e
  `token_redeems(user_id, setup_link) -> bool` — e **quatro funções de
  arranjo** que cada lado implementa do seu jeito, para que o **mesmo corpo**
  induza os cenários de L-IG2 sem ramificar: `email_ja_usado(email)` (fake:
  `used_emails`; real: semeia um `User` com esse e-mail no repositório fake de
  identity), `email_invalido()` (devolve um valor que o lado recusa — fake:
  entra em `invalid_emails`; real: `"sem-arroba"`), `unidade_inexistente()` /
  `unidade_de_outro_tenant()` / `tenant_inexistente()` (fake: `raw_error` com a
  exceção-sentinela correspondente; real: ids que a fachada não encontra) e
  `envio_falha(exc)` (fake: `fail_send_with`; real: o `RecordingEmailSender` do
  grafo com `fail_with`). O corpo chama o arranjo e assere o efeito — padrão do
  `conftest.py` da 3.3. Em `test_no_implementation_branching.py`: o módulo novo
  entra em `_MODULOS_DE_LEI`; a lista vira mapa módulo → nome da fixture
  (`"repos"` para os dois de repositório, `"gateway"` para o novo) e os dois
  guardas que hoje hardcodam `"repos"` — "todo teste recebe a fixture" (`:188`)
  e "nenhum corpo inspeciona o tipo do repositório" (`:179`) — leem o nome do
  mapa; o guarda de literais ganha `"real"` ao lado de `"fake"`/`"postgres"`.
  É generalização do guarda pelo seu próprio princípio (nenhuma ramificação por
  implementação), não afrouxamento: os três módulos ficam sob as mesmas quatro
  asserções.
- **Detalhes técnicos:** L-IG1 no fake = `user_id` novo a cada chamada + ledger
  `(email, tenant, unit)` + `token_redeems` verdadeiro só para o par certo; a
  metade "papel employee" é asserida só quando `login_role_of` devolve algo.
  L-IG2 = duas traduções (`used_emails` ⇒ `LoginEmailAlreadyInUseError`;
  `invalid_emails` ⇒ `InvalidLoginEmailError`) e "sobe cru" (`raw_error` ⇒ a
  **mesma instância** sobe de `provision_employee_login`; `fail_send_with` idem
  de `send_login_invitation`). L-IG3 = `dataclasses.fields(ProvisionedLogin)`
  `setup_link.repr is False` e `repr(...)` sem o link. L-IG4 = duas chamadas
  seguidas e id desconhecido sem erro.
- **Critério de aceite (CA02, CA05 parcial, CA08 lado fake):** um teste por
  lei, nomeado pela lei, **todos recebendo `gateway`**; `mypy tests/fakes/`
  verifica o fake contra o `Protocol`; `uv run pytest tests/contract/features/staff -q`
  verde — inclusive `test_no_implementation_branching.py` com três módulos na
  lista e o glob batendo; as duas suítes de repositório continuam intactas.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/contract/features/staff -q
  uv run mypy src/restaurant_hub/features/staff/application tests/fakes/
  make check
  ```
- **Commit sugerido:** `feat(staff): port IdentityGateway com quatro leis e fake in-memory [3.5/task-04]`

---

### Task 05 — Persistência: coluna `user_id`, mappers e migration `0004`

- **Arquivos a criar:**
  - `migrations/versions/0004_employees_user_id.py`
- **Arquivos a modificar (7 — exceção declarada: um campo atravessa tabela,
  mapper e migration, e as três suítes que os provam):**
  - `src/restaurant_hub/features/staff/adapters/out/postgres/tables.py`
  - `src/restaurant_hub/features/staff/adapters/out/postgres/mappers.py`
  - `tests/unit/features/staff/adapters/test_tables.py`
  - `tests/unit/features/staff/adapters/test_mappers.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_schema.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_employee_repository.py`
  - `tests/contract/features/staff/test_employee_repository_laws.py`
- **O que fazer:** `Column("user_id", Text, nullable=True)` em `employees`, com
  comentário citando ADR 3.5.0004 (sem FK — ADR 3.3.0002; sem UNIQUE —
  workforce §3.7; sem índice — ADR 3.3.0005). `employee_to_row` escreve
  `user_id`; `row_to_employee` passa `user_id=UserId(row.user_id) if
  row.user_id is not None else None` **pelo construtor**. Migration `0004`
  escrita à mão no padrão da `0003` (docstring de registro histórico;
  `revision="0004"`, `down_revision="0003"`; `upgrade` = `add_column`;
  `downgrade` = `drop_column`). `employee_repository.py` **não muda**:
  `_COLUNAS_IMUTAVEIS` não inclui `user_id` e `mutaveis` já deriva do mapper.
- **Critério de aceite (CA19):** round-trip `add` ⇒ `None`; `update` após
  `link_login` ⇒ relido igual; contrato de `EmployeeRepository` com `user_id` no
  snapshot "nenhum outro campo mudou", verde no fake e no Postgres;
  `test_schema.py` assere coluna anulável, sem FK, sem unique, sem índice sobre
  `user_id` (`inspect(engine)`); migration sobe e desce contra o banco real;
  `test_tables.py` conta 8 colunas em `employees` e nenhuma constraint nova.
- **Comando de verificação:**
  ```powershell
  uv run alembic -c migrations/alembic.ini upgrade head
  uv run pytest tests/unit/features/staff/adapters/test_tables.py tests/unit/features/staff/adapters/test_mappers.py tests/integration/features/staff tests/contract/features/staff -q
  make check
  ```
- **Commit sugerido:** `feat(staff): coluna user_id em employees com mappers e migration 0004 [3.5/task-05]`

---

### Task 06 — Identity domínio: `Email` recusa o byte NUL

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/domain/value_objects/email.py`
  - `tests/unit/features/identity/domain/test_email.py`
- **O que fazer:** em `Email.__post_init__`, **antes** da regex, `if "\x00" in
  self.value: raise InvalidEmailError(self.value)` com comentário que cita a
  medição (a regex aceita NUL; o `psycopg` o recusa client-side ⇒ 500 em
  `POST /users`, `/users/invitations`, `/auth/login`), o precedente ADR 3.4.0003
  e o concept 3.5 D8. Nada mais muda no VO.
- **Critério de aceite (CA31, metade unitária):** `Email("fulano\x00@cantina.com")`
  e `Email("\x00")` levantam `InvalidEmailError`; os testes existentes do VO
  continuam verdes; a suíte inteira de identity continua verde.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/identity tests/contract/features/identity tests/integration/features/identity -q
  make check
  ```
- **Commit sugerido:** `fix(identity): recusar o byte NUL no VO Email antes que alcance o banco [3.5/task-06]`

---

### Task 07 — Identity application: helper de convite e três use cases novos

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/_invitation.py`
  - `src/restaurant_hub/features/identity/application/use_cases/provision_account.py`
  - `src/restaurant_hub/features/identity/application/use_cases/send_invitation.py`
  - `src/restaurant_hub/features/identity/application/use_cases/revoke_all_sessions.py`
  - `tests/unit/features/identity/application/test_provision_account.py`
  - `tests/unit/features/identity/application/test_send_invitation.py`
  - `tests/unit/features/identity/application/test_revoke_all_sessions.py`
- **Arquivos a modificar (13 no total — exceção declarada: três use cases
  pequenos da mesma camada e escopo, mais o helper que dois módulos existentes
  passam a chamar, um pino e a totalidade de DTOs de identity):**
  - `src/restaurant_hub/features/identity/application/dtos/commands.py`
  - `src/restaurant_hub/features/identity/application/dtos/results.py`
  - `src/restaurant_hub/features/identity/application/use_cases/invite_user.py`
  - `src/restaurant_hub/features/identity/application/use_cases/request_password_reset.py`
  - `tests/unit/features/identity/adapters/test_http_dependencies.py`
  - `tests/unit/features/identity/application/test_dtos.py`
- **O que fazer:** `_invitation.py` com `setup_link(base_url: str, token_value:
  str) -> str` (formato `{base_url.rstrip('/')}/definir-senha?token={token}`) e
  `invitation_message(to: str, link: str) -> EmailMessage` (assunto e corpo
  **idênticos** aos de `InviteUserUseCase._enviar_convite`). `invite_user.py`:
  o import e o corpo de `_enviar_convite` passa a delegar
  (`self._email_sender.send(invitation_message(destinatario, setup_link(self._base_url,
  valor_do_token)))`); `request_password_reset.py`: o import e a linha 147 —
  **nada mais** nos dois módulos (construtores, ordem e testes intactos).
  Commands: `ProvisionAccountCommand(email: Email, role: Role, tenant_id,
  unit_ids, handed_over: bool)`, `SendInvitationCommand(email: Email, setup_link:
  str = field(repr=False))`, `RevokeAllSessionsCommand(user_id)`. Result:
  `ProvisionedAccountResult(user: UserResult, setup_link: str = field(repr=False))`.
  `ProvisionAccountUseCase(users, restaurants, units, hasher, tokens,
  token_issuer, id_generator, clock, invitation_ttl, handover_ttl, base_url)` —
  ordem de checagens de `InviteUserUseCase` **verbatim** (unicidade →
  `platform_admin` **com** `unit_ids` → restaurante → construir → unidades),
  `unusable_hash`, token `INVITATION` com `expires_at = now + (handover_ttl if
  handed_over else invitation_ttl)`, **sem** `EmailSender`; devolve o link.
  `SendInvitationUseCase(email_sender)` envia `invitation_message`; a falha
  propaga. `RevokeAllSessionsUseCase(sessions, clock)` chama
  `revoke_all_for_user(user_id, clock.now())`. O pino em
  `test_http_dependencies.py`: `required_permissions_for_role(Role.EMPLOYEE) ==
  frozenset({Permission.MANAGE_USERS})`, mensagem de falha nomeando R17 e o
  concept 3.5 §5.3. Em `tests/unit/features/identity/application/test_dtos.py`:
  `_TOTAL_DE_DTOS = 21 → 25` (três commands + um result) e `ProvisionedAccountResult`
  em `_RESULT_CLASSES` (a varredura de segredo daquele módulo olha nomes e
  tipos-folha — `setup_link: str` e `user: UserResult` passam; o `repr=False`
  é exigência **desta** Stage, asserida em CA05/CA15, não daquela varredura).
- **Detalhes técnicos:** `_link_units` é **duplicado** em `provision_account.py`
  (terceira cópia — declarada no concept §10; não extrair aqui). Docstring do
  módulo `provision_account.py` declara o carve-out da regra 1 da 2.5
  (ADR 3.5.0002 §Status). **Byte-identidade (CA16, M5 do Checkpoint B):** os
  testes existentes só asserem `"token=" in body`; por isso
  `test_send_invitation.py` ganha um teste que transcreve o literal
  `f"{base}/definir-senha?token={valor}"` e o compara com `setup_link(...)`, e
  `test_provision_account.py` assere que o link devolvido casa esse literal;
  em `test_request_password_reset.py`/`test_invite_user.py` **nada muda** —
  o que os protege é o literal transcrito no teste do helper.
- **Critério de aceite (CA15, CA16, CA17, pino de CA10):** provision — hash
  gravado ≠ `hasher.dummy_hash()` e dois provisionamentos gravam hashes
  distintos; token `INVITATION` com `expires_at` = `now + invitation_ttl` para
  `handed_over=False` e `now + handover_ttl` para `True` (TTLs distintos no
  teste); sender **não** chamado; o link casa o literal e o `<valor>` casa o
  fingerprint gravado; teste de precedência da 2.5 replicado. Send — uma
  mensagem, corpo contém o link, assunto da 2.5, falha propaga. Revoke —
  `revoke_all_for_user(user_id, now)`; id desconhecido não levanta. CA16 —
  suíte inteira de identity verde sem alteração dos testes existentes. CA17 —
  `grep -rn --include="*.py" "definir-senha" src/` devolve **só** `_invitation.py`.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/identity tests/contract/features/identity tests/integration/features/identity tests/e2e/features/identity -q
  grep -rn --include="*.py" "definir-senha" src/
  make check
  ```
- **Commit sugerido:** `feat(identity): provisionar conta pendente, enviar convite e revogar sessões [3.5/task-07]`

---

### Task 08 — Identity: a fachada in-process

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/facade.py`
  - `tests/unit/features/identity/application/test_facade.py`
- **O que fazer:** `ProvisionedAccount(user_id: str, setup_link: str =
  field(repr=False))` e `IdentityFacade(provision_account, send_invitation,
  revoke_all_sessions)` com `provision_account(*, email, role, tenant_id,
  unit_ids, handed_over) -> ProvisionedAccount`, `send_invitation(*, email,
  setup_link)`, `revoke_all_sessions(user_id)`. Converte primitivos
  (`Email(email)`, `Role.from_string(role)`, `RestaurantId`, `UnitId`), **não**
  captura nada. Re-exporta no módulo `EmailAlreadyRegisteredError` e
  `InvalidEmailError` (`__all__`). Docstring do módulo: *Open Host Service*,
  ADR 3.5.0001 §1, "não autoriza — o chamador autoriza (#49)", e a regra de que
  **só** este módulo é importável por outro BC (LAYOUT §3 após esta Stage).
- **Critério de aceite (CA18):** conversões corretas (asserção sobre o command
  que chega ao use case-dublê); `handed_over` repassado; use case que levanta ⇒
  a **mesma instância** sobe; `facade.EmailAlreadyRegisteredError is
  errors.EmailAlreadyRegisteredError` e idem `InvalidEmailError`; `lint-imports`
  verde.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/identity/application/test_facade.py -q
  uv run lint-imports
  make check
  ```
- **Commit sugerido:** `feat(identity): fachada in-process para consumidores de outros bounded contexts [3.5/task-08]`

---

### Task 09 — Gateway de staff, a única aresta e o seu wiring

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/out/identity/__init__.py`
  - `src/restaurant_hub/features/staff/adapters/out/identity/local_identity_gateway.py`
- **Arquivos a modificar (9, mais 2 a criar — exceção declarada: o adapter nasce com a aresta
  que o autoriza, o contrato que o prova e o wiring que o instancia — sem o
  wiring, o gateway seria código sem consumidor no `composition_root` e a Task
  10 não teria com o que construir os use cases; sem a aresta, `lint-imports`
  reprova o próprio adapter):**
  - `.importlinter`
  - `src/restaurant_hub/composition_root.py`
  - `src/restaurant_hub/shared/infrastructure/config/settings.py`
  - `tests/unit/features/staff/test_bc_independence.py`
  - `tests/contract/features/staff/conftest.py`
  - `tests/contract/features/staff/test_identity_gateway_laws.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
  - `tests/unit/shared/test_settings.py`
- **O que fazer:** `LocalIdentityGateway(facade: IdentityFacade)`:
  `provision_employee_login` → `facade.provision_account(email=email,
  role="employee", tenant_id=str(tenant_id), unit_ids=(str(unit_id),),
  handed_over=(delivery is LoginDelivery.LINK))`, traduzindo **exatamente**
  `EmailAlreadyRegisteredError → LoginEmailAlreadyInUseError(email)` e
  `InvalidEmailError → InvalidLoginEmailError(email)` (`raise ... from exc`),
  tudo o mais repassado; `send_login_invitation` → `facade.send_invitation`
  **sem** `try/except`; `revoke_login_sessions` → `facade.revoke_all_sessions`.
  O **único** import de identity é `from restaurant_hub.features.identity.application.facade
  import ...`. `.importlinter`: em `bc-independence`, `ignore_imports =
  restaurant_hub.features.staff.adapters.out.identity.* ->
  restaurant_hub.features.identity.application.facade` e
  `unmatched_ignore_imports_alerting = error`, com comentário sobre a forma da
  aresta (ADR 3.5.0001 §3). `test_bc_independence.py`: assere a **lista exata**
  e o alerting; a varredura por AST exige que o único módulo de staff que
  importa `restaurant_hub.features.identity` esteja em `adapters/out/identity/`
  e nomeie só `.application.facade`; asserção nova de que o gateway passa o
  literal `"employee"`; a varredura de `Role`/`Permission` continua. No
  `conftest.py` de contrato, `IMPLEMENTACOES_DO_GATEWAY = ("fake", "real")`: o real é
  `LocalIdentityGateway(IdentityFacade(...))` sobre `InMemoryUserRepository`,
  `InMemoryRestaurantRepository`, `InMemoryUnitRepository`, `FakePasswordHasher`,
  `InMemoryPasswordSetupTokenRepository`, `FakeSetupTokenIssuer`,
  `InMemorySessionRepository`, `RecordingEmailSender`, `FakeIdGenerator`,
  `FakeClock`, com restaurante e unidade semeados; `login_role_of` lê o `User`
  do repositório fake; `token_redeems` lê o token pelo fingerprint; as quatro
  funções de arranjo do holder são implementadas do lado real com dados
  (usuário semeado, unidade inexistente/de outro tenant, tenant inexistente,
  `RecordingEmailSender(fail_with=...)`). **Wiring:**
  `Settings.handover_link_ttl_hours: int = 168`; no composition root
  `handover_ttl = timedelta(hours=...)`, `ProvisionAccountUseCase(...)`,
  `SendInvitationUseCase(sender)`, `RevokeAllSessionsUseCase(sessions, clock)`
  sobre os **mesmos** repositórios/`sender`/`clock`, `IdentityFacade(...)`, e o
  campo **`staff_identity_gateway: IdentityGateway`** no contêiner (anotado com
  o port, como `staff_access_guard`; nasce **sem consumidor** até a Task 10 — o
  precedente é a 3.3/3.4, e a docstring do bloco diz isso). Testes de wiring:
  `test_composition_root_staff.py` — o campo é `LocalIdentityGateway` sobre uma
  `IdentityFacade` cujos use cases usam o mesmo `Engine`/`EmailSender`/`Clock`
  das rotas de identity (identidade de objeto); a varredura "só o composition
  root instancia adapters" cobre `adapters/out/identity/` (o import plantado
  ganha um segundo caso); `test_composition_root_identity.py` — os dois TTLs de
  provisão vêm da configuração com valores **distintos**; `test_settings.py` —
  o campo novo com default 168.
- **Critério de aceite (CA07, CA08, CA21 parcial, CA32 wiring):** `lint-imports`
  verde; `test_bc_independence` verde; um import plantado de
  `identity.application.use_cases` no gateway reprova `lint-imports` (verificar
  uma vez e registrar em §7); contrato verde nos dois lados — L-IG1 real: `User`
  com `role == "employee"`, tenant e exatamente a membership da unidade; cada
  `setup_link` redime o **seu** `user_id`; L-IG2: as duas traduções e as três
  cruas (`UnitNotFoundError` com unidade inexistente; `CrossTenantError` com
  unidade de outro tenant; `RestaurantNotFoundError` com tenant inexistente)
  sobem como a mesma instância; `RecordingEmailSender(fail_with=...)` sobe cru
  por `send_login_invitation`; L-IG4 nas duas.
- **Comando de verificação:**
  ```powershell
  uv run lint-imports
  uv run pytest tests/unit/features/staff/test_bc_independence.py tests/contract/features/staff/test_identity_gateway_laws.py tests/unit/features/staff/adapters/test_composition_root_staff.py tests/unit/features/identity/adapters/test_composition_root_identity.py tests/unit/shared/test_settings.py -q
  make check
  ```
- **Commit sugerido:** `feat(staff): gateway local para identity pela fachada, aresta única e wiring [3.5/task-09]`

---

### Task 10 — Use cases do ciclo de vida, com o seu wiring

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/create_login_for_employee.py`
  - `tests/unit/features/staff/application/test_create_login_for_employee.py`
- **Arquivos a modificar (15 — exceção declarada: a mudança de assinatura de
  `DeactivateEmployeeUseCase` propaga para o composition root e para os seis
  testes que o constroem direto ou por reflexão, e o módulo novo só pode
  existir no commit que o põe no contêiner — tudo é a **mesma** mudança
  medida em vários lugares):**
  - `src/restaurant_hub/features/staff/application/dtos/commands.py`
  - `src/restaurant_hub/features/staff/application/dtos/results.py`
  - `src/restaurant_hub/features/staff/application/use_cases/deactivate_employee.py`
  - `src/restaurant_hub/features/staff/application/use_cases/delete_employee.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/staff/application/test_employee_lifecycle.py`
  - `tests/unit/features/staff/application/test_delete_employee.py`
  - `tests/unit/features/staff/application/test_staff_flow.py`
  - `tests/unit/features/staff/application/test_copy_employee_to_unit.py`
  - `tests/unit/features/staff/application/test_dtos.py`
  - `tests/unit/features/staff/application/test_application_guards.py`
  - `tests/unit/features/staff/adapters/test_http_router_job_functions.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **O que fazer:** `CreateLoginForEmployeeCommand(tenant_id, unit_id,
  employee_id, email: str, delivery: LoginDelivery)` e `EmployeeLoginResult(employee:
  EmployeeResult, setup_link: str | None = field(repr=False))`.
  `CreateLoginForEmployeeUseCase(employees, gateway)` na ordem de concept §5.4:
  `find_by_id` (404) → `employee.assert_can_link_login()` →
  `gateway.provision_employee_login(email=..., tenant_id=..., unit_id=...,
  delivery=command.delivery)` → `employees.update(employee.link_login(user_id))`
  → se `EMAIL`: `gateway.send_login_invitation(email, setup_link)` e result com
  `setup_link=None`; se `LINK`: result com o link; `employee=employee_result(linked)`.
  `DeactivateEmployeeUseCase(employees, gateway)`: após `find_by_id`, se
  `user_id` ⇒ `gateway.revoke_login_sessions(user_id)` **antes** de `update`.
  `DeleteEmployeeUseCase` **não** ganha o gateway; após `find_by_id`, se
  `user_id` ⇒ `EmployeeHasLoginError` **antes** de `delete`. Composition root:
  `staff_create_login_for_employee=CreateLoginForEmployeeUseCase(employees=staff_employees,
  gateway=staff_identity_gateway)` e `DeactivateEmployeeUseCase(employees=...,
  gateway=staff_identity_gateway)` (a mesma instância) — **sem override** ainda
  (não há provedor no router; "nasce sem consumidor", como os 16 da 3.3). Testes:
  `test_composition_root_staff.py` — `_TOTAL_DE_USE_CASES = 17`, o módulo na
  lista, `Deactivate` e `CreateLogin` compartilham a instância do gateway
  (identidade de objeto), `Delete` e `Reactivate` **não** têm parâmetro `gateway`
  (`inspect.signature`); `test_application_guards.py` — `_USE_CASES_ESPERADOS =
  17`, o módulo na lista literal, `EmployeeLoginResult` em `permitidos`;
  `test_http_router_job_functions.py` — `disponiveis["gateway"] =
  InMemoryIdentityGateway()` na reflexão de `overrides_de_use_case`;
  `test_dtos.py` — `_DTOS_ESPERADOS = 15 + 2 + 3`, os dois DTOs novos em
  `_TODOS_OS_DTOS`, o command novo em `_COMMANDS_DE_REGISTRO_EXISTENTE`
  (`…_ESPERADOS = 11`) **e no dict `argumentos` de
  `test_construir_sem_a_unidade_e_type_error` (`email`, `delivery`, senão
  `KeyError`)**, `_TOTAL_DE_CONSUMIDORES_DO_MAPPER = 12`,
  `EmployeeLoginResult.setup_link.repr is False` e `repr(result)` sem o link,
  e a **varredura por AST de `features/staff/`** de que nenhuma `raise` recebe
  argumento chamado `setup_link` (nem variável derivada dele) — CA05 completo;
  `test_employee_lifecycle.py`, `test_delete_employee.py`, `test_staff_flow.py`,
  `test_copy_employee_to_unit.py` — construção de `DeactivateEmployeeUseCase(employees,
  gateway)` e os cenários novos de CA11.
- **Detalhes técnicos:** o use case novo **não** loga nem formata o link em
  nenhuma mensagem (L-IG3). Docstrings citam a ordem como **contrato** e o
  porquê de cada posição (concept §5.4, §5.6; ADR 3.5.0002 §4; ADR 3.5.0003
  §1/§1b/§2).
- **Critério de aceite (CA03, CA05, CA09, CA11, CA21 parcial, CA30):**
  parametrizado sobre os dois canais: `user_id` gravado igual ao provisionado;
  `delivery` repassado ao gateway; `EMAIL` ⇒ uma chamada `send_login_invitation`
  com o link e `setup_link is None`; `LINK` ⇒ zero envios e `setup_link` igual
  ao provisionado. Guardas antes de identity: vinculado ou desligado ⇒ zero
  `provision_employee_login` em `gateway.calls`, nada gravado; `used_emails`
  ⇒ `LoginEmailAlreadyInUseError` e registro relido `user_id is None`. Gravar
  antes de entregar: `fail_send_with` ⇒ mesma instância sobe **e** registro
  relido tem `user_id`; em `calls`, `employees.update` precede
  `send_login_invitation`. R13: vinculado ⇒ `revoke_login_sessions` em
  `gateway.calls` antes de `employees.update` em `store.calls`; sem `user_id` ⇒
  zero chamadas; gateway que levanta ⇒ registro continua ativo. R15: vinculado
  (ativo **ou** desligado) ⇒ `EmployeeHasLoginError`, zero `employees.delete`
  em `store.calls`, registro relido existe; sem `user_id` ⇒ removido (suíte da
  3.2 verde). Os cinco módulos de router e o de sweeps continuam verdes com
  `disponiveis["gateway"]`.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff tests/unit/test_bootstrap.py -q
  uv run mypy src/restaurant_hub
  make check
  ```
- **Commit sugerido:** `feat(staff): criar login do funcionário; desligar revoga; remover recusa vinculado [3.5/task-10]`

---

### Task 11 — Borda HTTP: R17, `manage_users`, override, declarações e cardinalidades

- **Arquivos a criar:**
  - `tests/unit/features/staff/adapters/test_http_router_login.py`
- **Arquivos a modificar (11, mais 1 a criar — exceção declarada: uma rota só pode nascer com o
  seu override e com a sua entrada em **todas** as varreduras derivadas de
  `router.routes` — unitárias e e2e —, senão `make check` fica vermelho no
  commit que a cria; a alternativa, editar as varreduras em commit anterior,
  as deixaria vermelhas antes):**
  - `src/restaurant_hub/features/staff/adapters/in/http/schemas.py`
  - `src/restaurant_hub/features/staff/adapters/in/http/dependencies.py`
  - `src/restaurant_hub/features/staff/adapters/in/http/router.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/staff/adapters/test_http_schemas.py`
  - `tests/unit/features/staff/adapters/test_http_dependencies.py`
  - `tests/unit/features/staff/adapters/test_http_boundary_sweeps.py`
  - `tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
  - `tests/e2e/features/staff/test_staff_authorization.py`
  - `tests/e2e/features/staff/test_staff_status_bands.py`
- **O que fazer:** `CreateLoginRequest(email: str, delivery: Literal["email",
  "link"])` (sem default) e `EmployeeLoginResponse(employee: EmployeeResponse,
  setup_link: str | None)`; `EmployeeResponse.user_id: str | None` preenchido em
  `from_result`. `dependencies.py`: `PERMISSION_MANAGE_USERS: Final =
  "manage_users"` e `MANAGE_USERS_IN_UNIT_ACCESS = AccessRequirement(permission=...,
  names_unit=True)`. `router.py`: R17 `POST /units/{unit_id}/employees/{employee_id}/login`
  → 201, provedor `_get_create_login_for_employee`, ordem autenticar →
  `validate_identifier` (os dois ids) → `guard.authorize(actor,
  MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=...)` → `guard.authorize(actor,
  MANAGE_USERS_IN_UNIT_ACCESS.permission, unit_id=...)` → command com
  `tenant_id=scope.tenant_id`, `LoginDelivery(payload.delivery)` →
  `EmployeeLoginResponse`. Composition root: o override
  `staff_router_module._get_create_login_for_employee`. Testes unitários:
  `test_http_router_login.py` declara `INVOCACOES` para R17 (corpo válido
  `{"email": "novo@x.com", "delivery": "link"}`, sucesso 201) — é o que faz as
  varreduras de `test_http_boundary_sweeps.py` alcançarem a rota — e cobre
  CA10; `test_http_schemas.py` (comentário da lista negra: "o vínculo entrou na
  3.5 — `user_id` continua proibido **no request** porque nunca vem do
  cliente"; `CreateLoginRequest` sem default; `EmployeeResponse.user_id`);
  `test_http_dependencies.py` (o requisito novo); `test_http_boundary_sweeps.py`
  (`_TOTAL_DE_CAMPOS_ESCALARES = 15`, `_TOTAL_DE_AUTORIZACOES = 19`;
  `test_toda_autorizacao_do_router_nomeia_um_requisito_declarado` passa a
  reconhecer o requisito novo; `_VALORES_ADVERSARIAIS` ganha
  `"nul\x00@dentro.com"` **e `_ADVERSARIAIS_RECUSADOS_PELO_VALIDADOR` também**
  — `validate_identifier` recusa qualquer string com NUL (`dependencies.py:110`),
  e sem a segunda entrada a transcrição do validador (`:1333`) e o eixo de path
  (`:1254`) reprovam; aqui só se prova "sem 500", o 422 é de T06/T12; a
  derivação de CA13 — rotas cujo `response_model` é ou embute
  `EmployeeResponse`, contagem 12); `test_http_path_addresses_the_record.py`
  (`_resultado_para` reconhece `EmployeeLoginResult`; a cláusula de
  autorizações adicionais aceita alvo **igual ao `unit_id` do path** — hoje só
  aceita identificador de unidade do corpo, escrita para R16);
  `test_composition_root_staff.py` (`_TOTAL_DE_OVERRIDES_DE_STAFF = 18`,
  `_TOTAL_DE_ROTAS_DE_STAFF = 17`). E2e: `test_staff_authorization.py` — entrada
  de R17 em `ROTAS` (corpo válido com e-mail **único por célula** via o sufixo
  do `Cenario`; `efeito` lendo `["employee"]["unit_id"]`), cardinalidades
  17/13/11/34/51, `_TOTAL_DE_ROTAS_COM_ENTRADA = 11`; `test_staff_status_bands.py`
  — as cinco exceções saem de `INALCANCAVEIS_POR_HTTP` e entram em
  `CENARIOS_POR_EXCECAO` com o seu cenário mínimo (segundo R17 ⇒ já-vinculado;
  R17 em desligado; R17 com e-mail do `manager` ⇒ em uso; R17 com e-mail sem
  `@` ⇒ inválido; R15 em vinculado ⇒ tem login), `_TOTAL_DE_CAMPOS_ESCALARES = 15`,
  `_VALORES_ADVERSARIAIS` ganha `"nul\x00@dentro.com"`.
- **Detalhes técnicos:** o e-mail **não** passa por `validate_identifier`
  (concept §5.7). A ordem das duas autorizações e a ausência da segunda quando a
  primeira nega são asseridas com o dublê que registra chamadas (CA10). A rota
  **não** loga nem repete o `setup_link`.
- **Critério de aceite (CA10, CA12, CA13 unitária, CA20 e2e das faixas, CA21):**
  `test_http_router_login.py`: 201 nos dois canais com `employee.user_id`
  preenchido e `setup_link` conforme o canal; duas autorizações na ordem, alvo
  `unit_id=<path>` nas duas (string exata), zero `manage_users` quando
  `manage_staff` nega; 409/422 por exceção do use case-dublê; corpo `{}` e
  `delivery="xpto"` ⇒ 422 do framework. Varreduras unitárias verdes com R17
  (fixture de invocação total); matriz e2e verde com 17 rotas e os cinco
  papéis; faixas novas alcançadas pelo HTTP real em `test_staff_status_bands.py`.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters tests/e2e/features/staff/test_staff_authorization.py tests/e2e/features/staff/test_staff_status_bands.py -q
  uv run mypy src/restaurant_hub/features/staff
  make check
  ```
- **Commit sugerido:** `feat(staff): rota de criação de login do funcionário com dupla permissão [3.5/task-11]`

---

### Task 12 — e2e do fluxo: os dois canais, desligamento, recusas, cópia e NUL

- **Arquivos a criar:**
  - `tests/e2e/features/staff/test_employee_login_flow.py`
- **Arquivos a modificar:**
  - `tests/e2e/features/identity/test_status_bands.py`
- **O que fazer:** o módulo novo, com `RecordingEmailSender` costurado em
  `create_app(..., email_sender=)` como no e2e de identity e `caplog` capturando
  a app: **CA22** (canal `email` com `manager`: 201, `user_id`, `setup_link:
  null`, link do sender → `POST /auth/password` → `POST /auth/login` do
  funcionário devolve tokens → o `employee` recebe 403 em R06); **CA23** (canal
  `link`: 201 com `setup_link`, zero e-mails, o link do corpo define a senha e o
  login funciona; antes disso, `POST /auth/login` falha com `_SENTINELA_DUMMY` e
  com senha qualquer); **CA14** (o **valor do token** só aparece onde deve —
  nem em nenhuma coluna das cinco tabelas de staff por consulta direta, nem em
  `caplog`); **CA24** (R13 ⇒ refresh 401, access ainda aceito, login funciona,
  R14 não altera; R15 em vinculado ativo e desligado ⇒ 409 `EmployeeHasLoginError`,
  registro em `?include_inactive=true`, refresh intacto); **CA25** (corpos
  asseridos: segundo R17 ⇒ 409 `EmployeeAlreadyHasLoginError` para `{mesmo
  e-mail, novo}`; e-mail do `manager` ⇒ 409 `LoginEmailAlreadyInUseError` com
  `detail` contendo só o e-mail; desligado ⇒ 409 `TerminatedEmployeeLoginError`;
  unidade A com `employee_id` de B ⇒ 404); **CA26** (cópia de vinculado ⇒ clone
  `user_id: null`, origem mantém); **CA30** pelo HTTP real (`fail_with` no
  sender ⇒ 500 e R06 mostra `user_id`); **CA13** e2e (registro vinculado lido
  por R06 e por cada rota de escrita de REMP traz o `user_id`); **CA32** (o
  token do canal `link` tem `expires_at - issued_at` = handover, o do `email` =
  invitation — lidos de `password_setup_tokens`); **CA31** e2e (R17 com
  `"nul\x00@dentro.com"` ⇒ 422). `tests/e2e/features/identity/test_status_bands.py`:
  um caso — `POST /users/invitations` com e-mail contendo NUL ⇒ 422 (docstring
  documenta que era 500).
- **Critério de aceite (CA13, CA14, CA22–CA26, CA30–CA32):** todos os testes
  acima verdes contra Postgres real.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/e2e -q
  make check
  ```
- **Commit sugerido:** `test(staff): e2e do login do funcionário pelos dois canais, desligamento e recusas [3.5/task-12]`

---

**Fechamento (off-task, `[3.5/--]`, um commit por escopo):** `docs(staff)` —
`docs/domain/staff/workforce.md` §3.8 (nota datada), `docs/LAYOUT.md` §2/§3
(fachada e regra da travessia), `docs/CONVENTIONS.md` §5 (terceira forma
não-destrutiva), `docs/overview.md` §3 (nota datada), `docs/adr/3_4_0001-*.md`
(nota datada de supersessão parcial), `docs/stages/2.5-email-invite/technical.md`
§7 (entrada datada), comentário na issue #47; depois `docs(roadmap)` no
commit `stage 3.5: complete`.

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 3.5: complete` e ser mergeada em `develop`. **Regra de evidência:**
> gate só conta com a saída literal do comando colada no relatório.

### Verificações automatizadas

```powershell
make check                                             # lint + mypy + layout + lint-imports + lock + docs-check + testes com gate 90
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing   # cobertura por arquivo tocado (≥ 90 em cada)
uv run lint-imports                                    # bc-independence com o par único
grep -rn --include="*.py" "definir-senha" src/         # só _invitation.py (CA17)
grep -rn --include="*.py" "EmployeeResult(" src/restaurant_hub/features/staff/application/use_cases/   # só _results.py (CA06)
python scripts/check_technical_postexec.py docs/stages/3.5-employee-login-link/technical.md
python scripts/check_adr_bounded_context.py
```

### Verificações funcionais

- [ ] **Canal `email` pelo entrypoint real:** `manager` autenticado cria
      funcionário e login (`delivery="email"`); o link sai do sender; o
      funcionário define a senha e autentica; `GET /units/{u}/employees` do
      gerente mostra `user_id` no registro (CA22, CA13).
- [ ] **Canal `link`:** o link volta na resposta 201, nenhum e-mail sai, o
      funcionário define a senha por ele e autentica (CA23).
- [ ] **Desligamento e remoção:** R13 corta o refresh; login de novo funciona;
      R15 em vinculado ⇒ 409 (CA24).
- [ ] **Cópia:** clone sem `user_id` (CA26).
- [ ] **Recusas com corpo** (CA25) e **NUL** (CA31) pelo HTTP real.
- [ ] **Prova por mutação** CA28 (a)–(h): editar → `make test` → reverter;
      saída colada no relatório.
- [ ] **Auditoria de testes** por subagente independente (PROMPT §Auditoria):
      seis itens "sim".

### Checklist de fechamento da Stage

- [ ] Todas as 12 Tasks commitadas, cada uma com seu check verde e `make
      check` verde antes do commit
- [ ] Checkpoints A (3 rodadas, feito), B (2 rodadas) e C executados, com
      **todos** os achados dispostos (`corrigido`/`refutado` com
      artefato/`escalado`)
- [ ] Cobertura ≥ 90% global **e** em cada arquivo de `src/` tocado
- [ ] `check_technical_postexec.py` verde; §7 reflete o que aconteceu
- [ ] Findings escalados com Stage candidata (concept §10 + §7 daqui)
- [ ] Docs de fechamento (`[3.5/--]`) commitados: `workforce.md` §3.8,
      `overview.md` §3, `LAYOUT.md` §2/§3, `CONVENTIONS.md` §5, nota no
      ADR 3.4.0001, §7 da 2.5, comentário na #47
- [ ] `roadmap.md`: Stage 3.5 `done`, nota datada de reconciliação (as cinco
      divergências do concept §1), `updated_at` e `last_reviewed_at`
- [ ] ADRs 3.5.0001–0004 em `accepted`
- [ ] `concept.md` sem retoque retrospectivo pendente
- [ ] Commit `stage 3.5: complete`; `git fetch` + `git rebase origin/develop`;
      push; PR contra `develop` com título
      `feat(staff): stage 3.5 — vínculo de login do funcionário`, label de
      auditoria em `review` preservado

## 4. Ordem de dependência entre Tasks

```
T01 (erros+mapa) ─► T02 (domínio) ─► T03 (result/mapper) ─► T04 (port+fake) ─► T05 (persistência)
                                                                                      │
T06 (Email NUL) ─► T07 (tijolos identity) ─► T08 (fachada) ──────────────────────────┼─► T09 (gateway+aresta+wiring)
                                                                                      │            │
                                                                                      └────────────┴─► T10 (use cases+wiring) ─► T11 (HTTP+override+cardinalidades) ─► T12 (e2e)
```

- **T01 antes de T02:** a entidade levanta exceções que só podem existir com a
  sua entrada no mapa (totalidade).
- **T03 antes de T10:** o use case novo já chama `employee_result`.
- **T04 antes de T09:** port antes do adapter (PIPELINE §4.3 #4).
- **T05 pode preceder ou seguir T06–T08** (frentes independentes); a ordem
  listada mantém staff inteiro antes de identity para que cada `make check`
  meça um BC de cada vez.
- **T08 antes de T09:** o gateway importa a fachada.
- **T09 antes de T10:** os use cases só podem ser construídos no composition
  root com o gateway já instanciado.
- **T10 antes de T11:** o override precisa do use case no contêiner; a rota
  precisa do use case.
- **T11 antes de T12:** o e2e do fluxo sobe a app real com R17.
- **T06 é independente de tudo** e poderia ser o primeiro commit; fica após T05
  para que os commits de identity sejam contíguos (escopo `identity`).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Uma varredura de totalidade não listada aqui ficar vermelha entre Tasks (o Checkpoint B mapeou as de §1; pode haver outra) | Se a correção cabe na Task corrente e é mecânica (contagem/lista), incluir e registrar `[deviation]` em §7 com o arquivo; se exige reordenar Tasks, **parar** e perguntar |
| A 13ª Task aparecer | **Parar**; não dividir staff — reabrir o corte do concept §13 Q6 via `AskUserQuestion` |
| `test_staff_authorization.py` precisar de e-mail único por célula e o `Cenario` não expor sufixo | Acrescentar o sufixo ao `Cenario` no `conftest.py` de e2e — arquivo fora da lista de T11; registrar `[deviation]` |
| `test_http_path_addresses_the_record.py` não aceitar a segunda autorização sobre o mesmo alvo sem reescrever a cláusula de R16 | A cláusula passa a aceitar "alvo adicional ∈ {identificadores de unidade do corpo} ∪ {`unit_id` do path}"; se a reescrita mudar a semântica de R16, **parar** e perguntar |
| `EmployeeResult.user_id` com default `None` deixar um sítio esquecido devolver `None` | CA06 (AST: nenhuma construção direta em `use_cases/`) é a trava; CA13 e2e mede a consequência |
| `ProvisionAccountUseCase` duplicar `_link_units` e o `ruff` reclamar | Não há regra de duplicação no ruff configurado; se aparecer, `# noqa` **não** — declarar em §7 e manter (consolidação é finding) |
| `unmatched_ignore_imports_alerting = error` reprovar por sintaxe de versão | import-linter 2.13 suporta; se não, remover a linha (default já é `error`) e registrar em §7 |
| `handover_ttl` e `invitation_ttl` iguais no teste deixarem a mutação `if handed_over` viva | CA15 e CA32 exigem valores **distintos** — a disciplina de `test_ttls_do_token_de_setup_vem_da_configuracao` |
| Postgres da worktree ocupado por container órfão de Stage anterior (memória `worktree-cleanup-leaves-containers`) | `docker ps` antes do primeiro teste de integração; derrubar o órfão |
| `mutmut` para as provas por mutação | As provas de CA28 são **manuais** (editar → `make test` → reverter), como na 3.6; `mutmut` só em container Linux e é do gate M2 da #45, não desta Stage |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (§4 contratos e leis,
  §5 invariantes, §11 critérios CA01–CA32, §13 decisões)
- [`../../overview.md`](../../overview.md) §3
- [`../../roadmap.md`](../../roadmap.md) — bloco 3.5
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 (commits), §3.4 (§7)
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §5, §6, §8
- ADRs desta Stage: [`../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md`](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md),
  [`3_5_0002`](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md),
  [`3_5_0003`](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md),
  [`3_5_0004`](../../adr/3_5_0004-user-id-as-nullable-opaque-column.md)
- ADRs consumidos: 2.5.0002, 2.5.0004, 3.2.0003, 3.2.0006, 3.3.0002, 3.3.0005,
  3.3.0006, 3.3.0007, 3.4.0001, 3.4.0002, 3.4.0003, 3.6.0002
- Stage irmã de forma: [`../3.6-staff-http/technical.md`](../3.6-staff-http/technical.md)
  (varreduras derivadas, catálogo de invocação, cardinalidades transcritas)
- Skills: `task-ordering-hex`, `hex-arch-python`, `composition-root`,
  `pytest-with-fakes`, `repository-pattern`, `fastapi-thin-adapter`,
  `stage-audit` (§"Lei universal, representante estreito")
- Issue **#51**; #45 (Gate 8), #46, #47, #49

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão (via `AskUserQuestion` ou equivalente).
> Apenas após a decisão, registre a entrada abaixo. Na dúvida sobre
> se algo é "pequeno o suficiente para decidir sozinho", **pergunte**.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap a tratar em **próxima Stage**; inclui direção sugerida e
  Stage candidata.
- `[deviation]` — ajuste pequeno vs. o plano original.

<!-- END: post-execution -->

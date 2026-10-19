---
title: Technical — Autorização na camada application de staff
description: Plano de execução da Stage 3.7, lista ordenada de Tasks (1 Task = 1 commit) para que os 17 use cases de staff autorizem o alvo do próprio command pelo AccessGuard injetado
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, application-authorization, staff, access-guard]
status: done
created_at: 2026-10-19
updated_at: 2026-10-19
stage_id: 3.7-application-authorization
stage_title: Autorização na camada application de staff
step_id: 3
step_title: Equipe da unidade
depends_on: [3.5-employee-login-link]
concept_ref: ./concept.md
issue_id: 49
branch: refactor/49-3-7-application-authorization
tasks_count: 7
---

# Technical — Stage 3.7 — Autorização na camada application de staff

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde** — baseline
>    inegociável: `make check` verde antes de todo commit.
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.7/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar** e registrar em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>
> **Stage = 1 branch:** `refactor/49-3-7-application-authorization`. O tipo
> `refactor` é o da issue de origem (#49): nenhuma rota, status ou dado muda.

## 1. Contexto e estratégia de execução

### Resumo
Os 17 use cases de staff passam a receber `guard: AccessGuard` por construtor e a
abrir `execute` com a(s) chamada(s) `self._guard.authorize(...)` sobre o alvo do
próprio command (concept R2/R3); todo command e query ganha `actor` como primeiro
campo; o vocabulário de permissão migra para o módulo do port; o
`composition_root` injeta o mesmo guard das rotas; o router passa `actor=actor`
e continua autorizando. Quatro suítes novas travam a propriedade: guard que nega
⇒ nenhum efeito (CA03/CA06), alvos exatos (CA05), escopo infiel ignorado (CA07),
forma de todo `execute` (CA15), totalidade da pasta (CA01/CA04), mesmo guard no
grafo (CA08) e cadeia real de identity (CA14).

### Estratégia
**Inside-out por camada no contrato, por agregado na adoção** (skill
`task-ordering-hex`), com uma restrição que manda no corte: **toda Task deixa
`make check` verde** (memória do projeto: as varreduras de totalidade reprovam
mudança incremental se a Task não leva a sua entrada nelas).

1. **Task 01** — o que os use cases vão consumir e os dublês: vocabulário no port
   e `stub_access_guards.py`. Nada consome ainda.
2. **Task 02** — o ator entra em todo command e query, e o router o passa. Os use
   cases ainda o ignoram: verde por construção. É a única Task que toca todos os
   DTOs, então a varredura de forma deles (CA02) nasce aqui, completa.
3. **Tasks 03–06** — os use cases adotam o guard **por grupo** (catálogo;
   funcionário básico; perfil; ciclo de vida, cópia e login). Cada Task leva junto
   o wiring do seu grupo no `composition_root`, as asserções de sequência de
   chamadas dos testes de borda que o grupo muda, os testes de regra de negócio
   do grupo (agora com `PermissiveAccessGuard`) e as suas entradas na tabela de
   cenários de `test_use_cases_authorize.py` (CA03/CA05/CA07). A tabela cresce
   por Task; **a cobrança de totalidade contra a pasta só nasce na Task 07**, quando
   a tabela está completa.
4. **Task 07** — as varreduras que só fecham com os 17: CA01, CA04, CA08, CA15,
   CA14 (cadeia real) e as docstrings de CA12 que ainda restam.

**Exceção declarada ao critério "≤ 5 arquivos" (PIPELINE §4.3 #2)** nas Tasks
02–06: é a mesma mudança mecânica propagada por suítes que constroem commands e
use cases (≈200 chamadas a `execute` em 15 arquivos de teste). Separá-la por
arquivo deixaria commits vermelhos.

### Pré-condições
- Stages `3.4`, `3.5`, `3.6` em `done` e mergeadas em `develop` (sim).
- Worktree com Postgres próprio (porta 5435) e `DATABASE_URL` no `.env` — a suíte
  e2e roda dentro de `make check`.

### Premissas técnicas
- Python 3.12, `uv sync --extra dev`; `make` via PowerShell com msys64 **anexado**
  ao PATH e `UV_SYSTEM_CERTS=1` (memória do projeto).

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                         (M) 03–06
└── features/staff/
    ├── application/
    │   ├── ports/out/access_guard.py                           (M) 01, 07
    │   ├── ports/out/identity_gateway.py                       (M) 06 — só docstring
    │   ├── dtos/commands.py, dtos/queries.py                   (M) 02
    │   └── use_cases/*.py (17)                                 (M) 03–06
    └── adapters/
        ├── inbound/http/dependencies.py                        (M) 01
        ├── inbound/http/router.py                              (M) 02
        └── out/identity/local_identity_gateway.py              (M) 06 — só docstring
tests/
├── fakes/features/staff/stub_access_guards.py                  (C) 01
├── unit/features/staff/application/
│   ├── test_stub_access_guards.py                              (C) 01
│   ├── test_use_cases_authorize.py                             (C) 03, (M) 04–07
│   ├── test_dtos.py                                            (M) 02
│   └── test_*.py de regra de negócio (15)                      (M) 02–06
└── unit/features/staff/adapters/
    ├── test_http_dependencies.py                               (M) 01
    ├── test_http_router_*.py, test_http_path_addresses_the_record.py (M) 03–06
    ├── test_composition_root_staff.py                          (M) 07
    └── test_application_authorization_chain.py                 (C) 07
```

`tests/e2e/` **não aparece** — CA09.

## 2. Tasks

> 7 Tasks — faixa saudável (3–12).

### Task 01 — Vocabulário de permissão no port e dublês do guard

- **Arquivos a criar:**
  - `tests/fakes/features/staff/stub_access_guards.py`
  - `tests/unit/features/staff/application/test_stub_access_guards.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/ports/out/access_guard.py`
  - `src/restaurant_hub/features/staff/adapters/inbound/http/dependencies.py`
  - `tests/unit/features/staff/adapters/test_http_dependencies.py`
- **O que fazer:**
  - Mover `PERMISSION_MANAGE_STAFF`, `PERMISSION_MANAGE_JOB_FUNCTIONS`,
    `PERMISSION_MANAGE_USERS` (com o comentário que os acompanha) para
    `access_guard.py`; `dependencies.py` passa a importá-los do port (os nomes
    continuam atributos do módulo da borda).
  - `stub_access_guards.py`:
    - `TEST_ACTOR` — objeto opaco usado como `actor` pelas suítes de regra de
      negócio (um `FakeActor` com tenant, para que a suíte também sirva ao
      `InMemoryAccessGuard`).
    - `DenyingAccessGuard` — `authorize` registra `(permission, tenant_id,
      unit_id)` em `calls` e levanta **sempre a mesma instância** `denial`;
      `authenticate` devolve `TEST_ACTOR`.
    - `PermissiveAccessGuard` — registra igual; recusa (com a sua sentinela)
      pedido com `tenant_id is None`; concede o resto e devolve
      `AuthorizedScope(tenant_id=INFIDEL_TENANT, unit_id=INFIDEL_UNIT)` — valores
      que nenhum teste semeia (concept D7).
    - Linhas `_conforms: AccessGuard = ...` para os dois (gate de `mypy` sobre
      `tests/fakes/`).
- **Detalhes técnicos:** docstring do módulo declara os dois como dublês
  **infiéis**, fora da suíte de lei (precedente: `adversarial_access_guard.py`).
- **Critério de aceite:**
  - `test_stub_access_guards.py`: o que nega levanta `is guard.denial` em toda
    chamada e registra o pedido; o permissivo registra, recusa `tenant_id=None` e
    devolve o escopo infiel.
  - `test_http_dependencies.py`: as três constantes de `dependencies` **são** as do
    port (`is`), e os valores seguem os de hoje.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/application/test_stub_access_guards.py tests/unit/features/staff/adapters/test_http_dependencies.py -q
  make check
  ```
- **Commit sugerido:** `feat(staff): trazer o vocabulário de permissão para o port e criar os dublês do guard [3.7/task-01]`

---

### Task 02 — O ator entra em todo command e query

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/dtos/commands.py` (15 commands)
  - `src/restaurant_hub/features/staff/application/dtos/queries.py` (2 queries)
  - `src/restaurant_hub/features/staff/adapters/inbound/http/router.py` (17 handlers: `actor=actor`)
  - `tests/unit/features/staff/application/test_dtos.py`
  - os 14 demais arquivos de `tests/unit/features/staff/application/` que constroem
    command/query (lista no §1, mapa medido em 2026-10-19)
- **O que fazer:** acrescentar `actor: Actor = field(repr=False)` como **primeiro**
  campo de cada DTO (docstring do módulo explica por quê — concept R6);
  `router.py` passa `actor=actor` em cada construção; os testes passam
  `actor=TEST_ACTOR` — inclusive o dicionário `argumentos` de
  `test_construir_sem_a_unidade_e_type_error` (`test_dtos.py:574-587`), que monta
  kwargs por reflexão dos campos e daria `KeyError` sem `"actor"`. Use cases
  **não mudam**.
- **Detalhes técnicos:** varredura derivada dos módulos `commands`/`queries` (sem
  lista): primeiro campo é `actor`, sem default, `repr=False`; `repr` de uma
  instância com ator sentinela não contém o `repr` do sentinela (CA02).
- **Critério de aceite:** CA02 verde; nenhuma outra asserção muda de valor.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/application/test_dtos.py -q
  make check
  ```
- **Commit sugerido:** `refactor(staff): levar o ator em todo command e query de staff [3.7/task-02]`

---

### Task 03 — O catálogo de funções autoriza na application

- **Arquivos a criar:**
  - `tests/unit/features/staff/application/test_use_cases_authorize.py`
- **Arquivos a modificar:**
  - `use_cases/{create,list,rename,delete}_job_function(s).py`
  - `src/restaurant_hub/composition_root.py` (4 construções ganham `guard=`)
  - `tests/unit/features/staff/adapters/test_http_router_job_functions.py`
    (`overrides_de_use_case(fakes)` passa a `overrides_de_use_case(fakes, guard)`
    e o `Ambiente` chama com **`self.guard`** — um `InMemoryAccessGuard` novo
    recusaria o ator, que só é reconhecido pela instância que o emitiu
    (`in_memory_access_guard.py:161`); sequência exata da linha ~403)
  - `src/restaurant_hub/features/staff/application/ports/out/access_guard.py` —
    §"Onde este port mora" (CA12): `authorize` passa a ter use case como
    consumidor nesta Task, e o texto que diz o contrário sai junto
  - `tests/unit/features/staff/application/{test_job_function_use_cases,test_delete_job_function,test_invalid_name_never_reaches_the_port,test_staff_flow,test_employee_lifecycle}.py`
- **O que fazer:** cada use case recebe `guard: AccessGuard` e abre `execute`
  — **como primeira instrução depois do docstring** (R2; em `create_job_function`
  isso põe a autorização antes da geração do id e da construção da entidade) —
  com `self._guard.authorize(command.actor, PERMISSION_MANAGE_JOB_FUNCTIONS,
  tenant_id=command.tenant_id)` (o parâmetro de `list_job_functions` é `query`).
  A suíte nova nasce com uma tabela `CENARIOS` (nome do módulo → montagem do use
  case sobre fakes semeados + command válido + alvos esperados) e três testes
  parametrizados por ela: CA03 (guard que nega ⇒ `is denial`, `store.calls`,
  `gateway.calls` e `id_generator.generated` sem crescimento depois da
  semeadura), CA05 (sequência exata de `PermissiveAccessGuard.calls`) e CA07
  (result e releitura pelo port carregam o tenant do command, apesar do escopo
  infiel). Entram os 4 do catálogo.
- **Detalhes técnicos:** os testes de regra de negócio passam
  `PermissiveAccessGuard()`; o ambiente de borda injeta **o mesmo**
  `InMemoryAccessGuard` do ambiente (os grants já usam o tenant nomeado, que é o
  que o use case pede). A expectativa de sequência passa a listar a chamada da
  rota (tenant `None`) **e** a do use case (tenant nomeado).
- **Critério de aceite:** CA03/CA05/CA07 verdes para os 4; o §"Onde este port
  mora" não afirma mais que o router é o único consumidor; suítes existentes
  verdes sem mudança de valor esperado além das sequências de chamada.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff -q
  make check
  ```
- **Commit sugerido:** `feat(staff): autorizar o catálogo de funções na camada application [3.7/task-03]`

---

### Task 04 — Criar, listar, renomear e remover funcionário autorizam

- **Arquivos a modificar:**
  - `use_cases/{create_employee,list_employees,rename_employee,delete_employee}.py`
  - `composition_root.py` (4 construções)
  - `tests/unit/features/staff/application/test_use_cases_authorize.py` (+4 cenários)
  - `tests/unit/features/staff/adapters/test_http_router_employees.py` (sequência exata da listagem, linha ~270)
  - `tests/unit/features/staff/application/{test_create_employee,test_list_employees,test_delete_employee,test_employee_edit_use_cases,test_invalid_name_never_reaches_the_port,test_employee_lifecycle,test_staff_flow,test_terminated_employee_edits,test_copy_employee_to_unit}.py`
- **O que fazer:** igual à Task 03, com `PERMISSION_MANAGE_STAFF`,
  `tenant_id=command.tenant_id, unit_id=command.unit_id`.
- **Critério de aceite:** CA03/CA05/CA07 verdes para os 8 até aqui.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q` ; `make check`
- **Commit sugerido:** `feat(staff): autorizar criação, listagem, renomeação e remoção de funcionário [3.7/task-04]`

---

### Task 05 — As edições de perfil autorizam

- **Arquivos a modificar:**
  - `use_cases/{assign_job_functions,change_workload_profile,declare_shift_preference,register_unavailability,remove_unavailability}.py`
  - `composition_root.py` (5 construções)
  - `tests/unit/features/staff/application/test_use_cases_authorize.py` (+5 cenários)
  - `tests/unit/features/staff/adapters/test_http_router_employee_profile.py` (se houver sequência exata)
  - `tests/unit/features/staff/application/{test_assign_job_functions,test_employee_edit_use_cases,test_unavailability_use_cases,test_terminated_employee_edits,test_staff_flow,test_copy_employee_to_unit}.py`
- **O que fazer:** igual à Task 04.
- **Critério de aceite:** CA03/CA05/CA07 verdes para os 13 até aqui.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q` ; `make check`
- **Commit sugerido:** `feat(staff): autorizar as edições de perfil do funcionário [3.7/task-05]`

---

### Task 06 — Ciclo de vida, cópia e login autorizam (os dois de dois alvos)

- **Arquivos a modificar:**
  - `use_cases/{deactivate_employee,reactivate_employee,copy_employee_to_unit,create_login_for_employee}.py`
    (docstring de `create_login_for_employee` deixa de dizer *"não autoriza"* — CA12)
  - `application/ports/out/identity_gateway.py` e
    `adapters/out/identity/local_identity_gateway.py` — só docstring (CA12)
  - `composition_root.py` (4 construções)
  - `tests/unit/features/staff/application/test_use_cases_authorize.py` (+4 cenários; CA06)
  - `tests/unit/features/staff/adapters/{test_http_router_lifecycle_and_copy,test_http_router_login}.py`
    (`AmbienteComGateway` monta `CreateLoginForEmployeeUseCase(...)` à mão: passa
    `guard=self.guard`; sequências exatas de cópia ~174 e login ~270)
  - `tests/unit/features/staff/application/{test_employee_lifecycle,test_delete_employee,test_copy_employee_to_unit,test_create_login_for_employee,test_terminated_employee_edits,test_staff_flow}.py`
- **O que fazer:** `deactivate`/`reactivate` como a Task 04; `copy` autoriza
  `unit_id` e **depois** `target_unit_id`; `create_login` autoriza
  `PERMISSION_MANAGE_STAFF` e **depois** `PERMISSION_MANAGE_USERS` sobre a
  unidade — nos dois, as duas chamadas são as **primeiras instruções** de
  `execute` (R2), antes de qualquer outra. CA06:
  `InMemoryAccessGuard` concedendo só o primeiro alvo ⇒ a sentinela de
  autorização sobe e nada cresce.
- **Critério de aceite:** CA03/CA05/CA06/CA07 verdes para os 17; as três frases de
  CA12 desses arquivos não existem mais.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q` ; `make check`
- **Commit sugerido:** `feat(staff): autorizar ciclo de vida, cópia e login nos dois alvos [3.7/task-06]`

---

### Task 07 — Totalidade, forma e cadeia real

- **Arquivos a criar:**
  - `tests/unit/features/staff/adapters/test_application_authorization_chain.py`
- **Arquivos a modificar:**
  - `tests/unit/features/staff/application/test_use_cases_authorize.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **O que fazer:**
  - CA04: `set(CENARIOS) == módulos da pasta use_cases/` (sem `_`-prefixados).
  - CA01: todo `*UseCase` da pasta tem `guard` no construtor anotado `AccessGuard`.
  - CA15: AST de todo `execute` da pasta — descontado o docstring, as primeiras
    instruções são exatamente as chamadas da matriz R3 (receptor = primeiro
    parâmetro; permissão = `Name` de uma constante `PERMISSION_*` do port, nunca
    literal `str`; `tenant_id=<p>.tenant_id`; `unit_id=<p>.<campo>` quando a matriz
    o pede), e nenhuma outra chamada a `authorize` no corpo. A matriz esperada é
    a mesma tabela de CA05 — uma fonte.
  - CA08: no grafo de `wire_dependencies`, `deps.<uc>._guard is
    deps.staff_access_guard` para os 17.
  - CA14: `_IdentityAccessGuard(IdentityGuard(FakeTokenIssuer(),
    AuthorizeActionUseCase(InMemoryUserRepository, InMemoryUnitRepository)))` com
    tenants A e B, uma unidade em cada, usuários `owner`/`manager`/`hr`/`employee`
    de A (membros da unidade de A) e um `platform_admin`; para todo cenário de
    `CENARIOS` re-endereçado para B: negado com exceção de identity, sem
    crescimento de `store.calls`/`gateway.calls`/gerador; controle positivo com o
    `owner` de B.
- **Critério de aceite:** CA01, CA04, CA08, CA14, CA15 verdes; mutação manual de
  um `execute` (autorização condicional, ou uma linha antes) reprova CA15.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff -q
  make check
  ```
- **Commit sugerido:** `test(staff): travar a autorização da application sobre a pasta inteira e a cadeia real [3.7/task-07]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```powershell
make check
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/3.7-application-authorization/technical.md
git diff --exit-code --stat origin/develop -- tests/e2e      # vazio (CA09)
git diff --exit-code origin/develop -- tests/unit/features/staff/adapters/test_http_boundary_sweeps.py   # vazio: 19 autorizações intactas (CA10)
git grep -nE '= "manage_' -- src/restaurant_hub/features/staff   # só access_guard.py (CA11)
git grep -n "(#49)" -- src/restaurant_hub/features/staff   # só as menções à fachada de identity (CA12, 2ª metade)
# CA13 — limite por arquivo, não a média:
uv run coverage report --fail-under=90 --include="$(git diff --name-only origin/develop -- src/ | tr '
' ',')"
```

### Matriz CA → Task

| CA | Onde | Check |
|---|---|---|
| CA01 | 07 | varredura de construtor sobre a pasta |
| CA02 | 02 | varredura de campos dos DTOs |
| CA03 | 03–06 | `CENARIOS` × guard que nega |
| CA04 | 07 | `set(CENARIOS)` == pasta |
| CA05 | 03–06 | sequência exata do guard permissivo |
| CA06 | 06 | `InMemoryAccessGuard` concedendo só o 1º alvo |
| CA07 | 03–06 | result + releitura com escopo infiel |
| CA08 | 07 | identidade do guard no grafo real |
| CA09 | gate | `git diff` de `tests/e2e` vazio + `make check` |
| CA10 | gate | `test_http_boundary_sweeps.py` intocado e verde |
| CA11 | 07 (AST) + gate (grep) | permissão por constante |
| CA12 | 03 (port), 06 (use case e gateways), gate (grep) | frases ausentes / menções a identity mantidas |
| CA13 | gate | `make check` + `coverage report --fail-under=90` por arquivo |
| CA14 | 07 | cadeia real × todo papel |
| CA15 | 07 | AST de todo `execute` |

### Verificações funcionais
- [ ] Fluxo real pela API (app subida contra o Postgres da worktree): gerente cria
      função e funcionário, lista, copia; ator de outra unidade recebe 403 — com os
      mesmos status de antes.
- [ ] Um driver em processo (script de verificação, fora do repo) chamando um use
      case de `wire_dependencies` com ator de outro tenant é negado sem efeito.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage 3.7: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at` e `last_reviewed_at`
- [ ] ADR 3.7.0001 em `accepted`
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07
```
03–06 são independentes entre si no código, mas compartilham
`test_use_cases_authorize.py`, `composition_root.py` e `test_staff_flow.py`; a
ordem linear evita conflito. 07 exige os 17.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Uma suíte de borda monta use case fora do ambiente refletido e quebra ao ganhar `guard` | injetar o guard do próprio ambiente; registrar `[deviation]` |
| CA15 rígido demais para um `execute` com forma legítima diferente | ajustar o use case à forma (é a regra R2), nunca relaxar a varredura sem `[decision]` |
| `make check` lento/travando (Avast) | serializar; nunca rodar e2e em paralelo com `make check` |
| CA14 exige identity em memória que falta (ex.: `list_memberships`) | usar o fake existente; se faltar operação, registrar `[finding]` e cobrir CA14 por integração com Postgres |

## 6. Referências

- [`./concept.md`](./concept.md)
- [`../../roadmap.md`](../../roadmap.md) §Stage 3.7
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4
- ADR [`3.7.0001`](../../adr/3_7_0001-every-staff-use-case-authorizes-its-own-target.md)
- Skills: `hex-arch-python`, `composition-root`, `pytest-with-fakes`,
  `fastapi-thin-adapter`, `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

<!-- END: post-execution -->

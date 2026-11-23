---
title: Technical — API do editor e consulta de escala
description: Plano de execução da Stage 4.5, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, scheduling-http]
status: done
created_at: 2026-11-23
updated_at: 2026-11-23
stage_id: 4.5-scheduling-http
stage_title: API do editor e consulta de escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.4-scheduling-persistence, 3.10-login-link-management]
concept_ref: ./concept.md
issue_id: 254
branch: feat/254-4-5-scheduling-http
tasks_count: 10
---

# Technical — Stage 4.5 — API do editor e consulta de escala

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.** A
>    verificação da Task roda só os testes dela; o `make check` completo
>    roda só nos pontos do [plano de gates](#plano-de-gates).
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [4.5/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, decidir pelo protocolo da sessão e registrar a decisão em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done).
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 4.5: complete`, com o `roadmap.md` e as marcas do doc de domínio da CA13.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/254-4-5-scheduling-http`. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

A borda HTTP de scheduling: sete rotas (S1–S7 do concept §4.1) sobre os sete use cases da 4.3,
com schemas Pydantic só em `adapters/inbound/http/schemas.py`, o mapa de erros sobre as duas raízes
do BC (concept §6, ADR 4.5.0002) e o requisito de acesso por rota. Antes, as permissões de escala
entram no enum e no mapa de papéis de identity (ADR 4.5.0001), o port `AccessGuard` de scheduling
ganha `authenticate` e o tenant opcional, e nasce o adapter `LocalAccessGuard` de scheduling sobre a
fachada de acesso (ADR 4.5.0003). O `DemandResult` ganha `function_enabled_in_unit` (D-ORPHAN). O
composition root monta os sete use cases e o guard e remove os três campos provisórios da 4.4. O e2e
contra Postgres prova o fluxo do DoD, a matriz papel × rota e as faixas.

### Estratégia

Inside-out (skill `task-ordering-hex`): identity (vocabulário) → port de scheduling e o fake → adapter
de saída → DTO de application → borda (mapa de erros, schemas/dependências, router com testes de
borda sobre fakes) → wiring → e2e. Cada Task leva a entrada dela nas varreduras de totalidade:

| Varredura | Arquivo de teste | Alimentada por |
|---|---|---|
| vocabulário e mapa de papéis | `tests/unit/features/identity/domain/test_role_permission.py`, `test_rbac_additivity.py` | Task 01 |
| quem cria quem e o pino de R17 | `tests/unit/features/identity/adapters/test_http_dependencies.py` | Task 01 |
| leis do guard (fake) | `tests/unit/features/scheduling/application/test_access_guard_laws.py` | Task 02 |
| use cases autorizam primeiro | `tests/unit/features/scheduling/application/test_use_cases_authorize.py` | Task 02 (port) |
| pares do `bc-independence` (lista exata, nos dois BCs) e vocabulário/arestas de scheduling (rglob no BC) | `tests/unit/features/scheduling/test_bc_independence.py`, `tests/unit/features/staff/test_bc_independence.py` | Tasks 03, 05, 06 |
| alcance dos use cases facade-only de identity (rglob em `src/`) | `tests/unit/features/identity/application/test_use_cases_authorize.py` | Task 03 |
| marcadores de pacote, sítio de construção de result, charter do composition root, imports por camada | `tests/unit/test_check_layout.py` | Tasks 03, 04, 05, 07 |
| inventário congelado do wiring (routers, registradores, partição das rotas) | `tests/unit/features/staff/adapters/test_composition_root_staff.py` | Task 07 |
| escopo da mutação (`only_mutate` × arquivos citados) | `tests/unit/test_mutation_scope.py` | Task 03 |
| DTOs de scheduling | `tests/unit/features/scheduling/application/test_dtos.py` | Task 04 |
| erros × mapa de status, handler nas duas raízes | `tests/unit/test_status_map.py` | Task 05 |
| `router.routes` × invocações e requisitos | `tests/unit/features/scheduling/adapters/test_http_router.py` | Task 06 |
| use cases × contêiner, `_get_*` × overrides | `tests/unit/features/scheduling/adapters/test_composition_root_scheduling.py` | Task 07 |
| rotas não públicas negam (401/403) e respostas sem segredo | `tests/e2e/test_deny_by_default.py`, `tests/e2e/test_credential_responses_are_not_stored.py` | Task 07 (CI) |

### Pré-condições

- Stages `4.4-scheduling-persistence` e `3.10-login-link-management` `done` e mergeadas em develop
  (`check_stage_deps 4.5-scheduling-http` OK).
- Concept `done` (commit `stage 4.5: conceptual approved`).

### Premissas técnicas

- Sem migration. O Postgres local é compartilhado entre sessões: localmente rodam só unit e contract
  em memória; integração e e2e rodam no `lint-and-test` do GitHub Actions do PR #261.
- FastAPI 0.139 (o `app.routes` não lista as rotas de router incluído — o e2e enumera pelo OpenAPI,
  como `test_deny_by_default.py`).

### Plano de gates

> Depois de quais Tasks o `make check` completo precisa estar verde.
> **Orçamento: 1 a 3 pontos por Stage, o de saída incluído.** Nas demais
> Tasks o comando de verificação roda só os testes da Task. Ponto no
> meio da Stage precisa de motivo concreto; do 4º ponto em diante, de
> justificativa por ponto. Regra completa (onde pôr um ponto, varreduras
> de totalidade, como o ponto é cumprido sob orquestração):
> [`PIPELINE.md`](../../PIPELINE.md) §9.6.

| # | Depois da Task | Motivo |
|---|---|---|
| 1 | Task 03 | Fecha o grupo que muda contrato lido por outro BC e por outra camada: o enum e o mapa de papéis de identity (Task 01, que mexe na matriz congelada e no pino de R17), o port `AccessGuard` de scheduling (Task 02, lido pelos sete use cases) e o `.importlinter` com o par novo (Task 03, configuração de ferramenta). Uma quebra aqui invalidaria todas as Tasks da borda |
| 2 | Task 07 | Composition root e primeira vez que as rotas de scheduling existem na app: as varreduras globais (`test_status_map.py`, `test_deny_by_default.py`, `test_credential_responses_are_not_stored.py`) e a integração da 4.4 passam a ver o BC; o e2e das Tasks 08–10 depende do wiring certo |
| 3 | saída | gate de saída (§3) |

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                  (Task 07)
└── features/
    ├── identity/
    │   ├── application/facade.py                        (docstring, Task 01)
    │   └── domain/value_objects/{permission,role}.py    (Task 01)
    └── scheduling/
        ├── application/
        │   ├── ports/out/access_guard.py                (Task 02)
        │   ├── dtos/results.py                          (Task 04)
        │   └── use_cases/{get_calendar,get_schedule,evaluate_schedule,publish_schedule}.py (Task 04)
        └── adapters/
            ├── inbound/__init__.py, inbound/http/{__init__,error_handlers,dependencies,schemas,router}.py
            └── out/identity/{__init__,local_access_guard}.py
tests/
├── fakes/features/scheduling/in_memory_access_guard.py   (Task 02)
├── unit/features/scheduling/adapters/{test_local_access_guard,test_http_error_handlers,
│        test_http_dependencies,test_http_schemas,test_http_router,http_support}.py
├── unit/features/identity/... (Task 01)
└── e2e/features/scheduling/{__init__,conftest,test_scheduling_flow,
         test_scheduling_authorization,test_scheduling_status_bands}.py
```

## 2. Tasks

### Task 01 — permissões de escala no enum e no mapa de papéis de identity

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/domain/value_objects/permission.py`
  - `src/restaurant_hub/features/identity/domain/value_objects/role.py`
  - `src/restaurant_hub/features/identity/application/facade.py` (só docstring, propriedade 3)
  - `tests/unit/features/identity/domain/test_role_permission.py`
  - `tests/unit/features/identity/adapters/test_http_dependencies.py`
  - `tests/e2e/test_deny_by_default.py` (só a docstring de `token_sem_permissao`, que diz que o
    `employee` não detém permissão nenhuma)
- **O que fazer:** acrescentar `VIEW_SCHEDULE`, `MANAGE_SCHEDULE`, `VIEW_OWN_SCHEDULE` e
  `MANAGE_SCHEDULE_SETTINGS` a `Permission`; `MANAGE_SCHEDULE_SETTINGS` em
  `TENANT_WIDE_PERMISSIONS`; mapa de papéis da §4.4 do concept; reescrever o comentário de
  `_ROLE_PERMISSIONS` (`manager` e `hr` coincidem em identity e staff e divergem na escala; `hr` lê e
  vê a própria). Docstring do módulo de permissão cita as duas tenant-wide.
- **Detalhes técnicos:**
  - `test_permission_e_conjunto_fechado` e `test_conteudo_exato_do_mapa_por_papel` com os conjuntos
    novos; `test_employee_nao_tem_capacidade_de_gestao` passa a afirmar "só `view_own_schedule`" e
    nenhuma `manage_*`; teste novo: subconjunto de escala por papel (CA11) e `hr` sem
    `manage_schedule`; `TENANT_WIDE_PERMISSIONS == {manage_job_functions, manage_schedule_settings}`.
  - `test_http_dependencies.py`: a fixture derivada (`required_permissions_for_role` por papel) com os
    conjuntos novos; a matriz congelada ganha baseline datada 2026-11-23 (`hr` sem `manager`), com o
    comentário do D-CREATE; o pino de R17 vira a propriedade de CA15 (todo papel com `manage_staff` e
    `manage_users` detém `required_permissions_for_role(EMPLOYEE)`), com caso plantado que a reprova.
  - `test_rbac_additivity.py` não muda (baseline congelada antes da 3.4; crescer é permitido).
- **Critério de aceite:** CA11 e CA15 cobertos por teste; nenhuma outra decisão de acesso de identity
  muda (a matriz falha se mudar).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/identity -q --no-cov
  ```
- **Commit sugerido:** `feat(identity): conceder as permissões de escala no mapa de papéis [4.5/task-01]`

---

### Task 02 — o port `AccessGuard` de scheduling ganha `authenticate` e o tenant opcional

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/application/ports/out/access_guard.py`
  - `tests/fakes/features/scheduling/in_memory_access_guard.py`
  - `tests/unit/features/scheduling/application/test_access_guard_laws.py`
- **O que fazer:** `authenticate(request: object) -> Actor` e `authorize(..., tenant_id: str | None =
  None, unit_id: str)`; docstring reescrita (não é mais "só `authorize`"; L-SG2 vale para o tenant
  pedido; L-SG5: tenant omitido ⇒ o do ator, ator sem tenant negado). O fake ganha `authenticate`
  (emite/resolve o ator a partir de um objeto de pedido: um `Mapping` com o cabeçalho
  `authorization: "Bearer <user_id>"` ou um pedido do Starlette com esse cabeçalho; sem cabeçalho ou
  sujeito desconhecido levanta a sentinela de autenticação, `authentication_error`) e a resolução do
  tenant omitido.
- **Detalhes técnicos:** os use cases não mudam (continuam nomeando o tenant). A conformidade do fake
  ao port é cobrada por `_conforms: AccessGuard = InMemoryAccessGuard()` (mypy em `tests/fakes` no
  pre-commit) e pelas leis. `test_no_implementation_branching.py` **não** entra: ele cobre só os
  ports de dados e trunca o Postgres compartilhado.
- **Critério de aceite:** leis L-SG1–L-SG5 provadas contra o fake, inclusive o tenant omitido com ator
  sem tenant negado e o escopo com o tenant do ator; `authenticate` sem credencial levanta a sentinela.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/scheduling -q --no-cov
  ```
- **Commit sugerido:** `feat(scheduling): dar ao port do guard autenticação e tenant do ator [4.5/task-02]`

---

### Task 03 — adapter `LocalAccessGuard` de scheduling sobre a fachada de acesso

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/adapters/out/identity/__init__.py`
  - `src/restaurant_hub/features/scheduling/adapters/out/identity/local_access_guard.py`
  - `tests/unit/features/scheduling/adapters/test_local_access_guard.py` (leis contra o adapter com
    dublê da fachada, e a **cadeia real**: `LocalAccessGuard(IdentityAccessFacade(AuthorizeActionUseCase`
    sobre os repositórios em memória de identity`))` × as três permissões do port × papéis × membro e
    não membro × tenant omitido — o que pega constante do port divergente do enum da Task 01, como
    `test_application_authorization_chain.py` de staff)
- **Arquivos a modificar:**
  - `.importlinter` (par `restaurant_hub.features.scheduling.adapters.out.identity.* ->
    restaurant_hub.features.identity.application.facade`)
  - `tests/unit/features/scheduling/test_bc_independence.py` (a segunda aresta, nomeada:
    `adapters/out/identity/` importa **só** `identity.application.facade`, ao lado de
    `adapters/out/staff/` → só `staff.application.facade`; o detector reprova import de vizinho fora
    dessas duas pastas, com caso plantado para cada aresta e para o import fora delas; o docstring
    deixa de dizer "identity continua sem aresta") e `tests/unit/features/staff/test_bc_independence.py`
    (lista exata dos pares)
  - `pyproject.toml` (`only_mutate` ganha o adapter: ele decide o tenant — L-SG2/L-SG5 — como o de
    staff, que já está lá) e `tests/unit/test_mutation_scope.py`, que trava o conjunto exato
    (`_MODULOS_DE_ACESSO`)
- **O que fazer:** o adapter recebe `IdentityAccessFacade` e o chamável `authenticate_request`;
  `authenticate` repassa sem capturar; `authorize` confere o tipo do ator (`AccessPrincipal`, senão
  `TypeError` — defeito de wiring), resolve o tenant omitido pelo `principal.tenant_id`, delega à
  fachada com a unidade, e na volta: ator sem tenant ⇒ `PermissionDeniedError` (L-SG2/L-SG5, como o
  L-AG3 de staff); escopo = (tenant **pedido ou resolvido**, unidade pedida, `principal.user_id`).
  Nenhum `try/except` (L-SG1).
- **Detalhes técnicos:** exceção de 8 arquivos declarada (PIPELINE §4.3 critério 2): o par do
  `.importlinter` é travado por lista exata em dois testes, e o `only_mutate` por teste de escopo; os
  três entram juntos ou o commit fica vermelho.
- **Critério de aceite:** CA12 — L-SG1–L-SG5 contra o adapter com dublê da fachada (mesmos eixos da
  suíte do fake), conformidade de forma do dublê com a fachada real, e o par novo como única aresta
  nova (`lint-imports` verde).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/scheduling/adapters/test_local_access_guard.py tests/unit/features/scheduling/test_bc_independence.py tests/unit/features/staff/test_bc_independence.py tests/unit/test_mutation_scope.py tests/unit/features/identity/application/test_use_cases_authorize.py tests/unit/test_check_layout.py -q --no-cov
  uv run lint-imports
  ```
  **Ponto 1 do plano de gates** (`lint-and-test` do PR verde no commit desta Task).
- **Commit sugerido:** `feat(scheduling): adapter do guard de escala sobre a fachada de acesso [4.5/task-03]`

---

### Task 04 — a demanda diz se a função vale na unidade (`function_enabled_in_unit`)

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/application/dtos/results.py`
  - `src/restaurant_hub/features/scheduling/application/use_cases/{get_calendar,get_schedule,evaluate_schedule,publish_schedule}.py`
  - `tests/unit/features/scheduling/application/test_read_use_cases.py`
  - `tests/unit/features/scheduling/application/test_evaluate_and_publish.py`
  - `tests/unit/features/scheduling/application/test_dtos.py` (chama os dois mapeadores)
- **O que fazer:** `DemandResult.function_enabled_in_unit: bool`; os mapeadores
  (`to_schedule_result`, `to_calendar_result`) recebem o conjunto de funções habilitadas como
  parâmetro **obrigatório e keyword-only** (sem default: um chamador esquecido não compila nem roda) e
  o repassam até `_to_demand_result`; os quatro use cases passam `view.unit_function_ids`; o calendário
  chama `load_staff(..., with_unit_functions=True)`.
- **Detalhes técnicos:** exceção de 8 arquivos declarada (repasse mecânico de um argumento por quatro
  chamadores e os testes dos mapeadores). `test_dtos.py` tem caso `True`/`False` no nível do mapeador.
- **Critério de aceite:** em `get_schedule`, `evaluate`, `publish` e `get_calendar`, demanda de função
  habilitada sai `True` e a de função não habilitada sai `False` (com mutação: trocar a pertença por
  constante derruba os dois casos).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/scheduling/application tests/unit/test_check_layout.py -q --no-cov
  ```
- **Commit sugerido:** `feat(scheduling): sinalizar na demanda a função que não vale na unidade [4.5/task-04]`

---

### Task 05 — dependências, schemas e mapa de erros da borda

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/adapters/inbound/__init__.py`
  - `src/restaurant_hub/features/scheduling/adapters/inbound/http/__init__.py`
  - `src/restaurant_hub/features/scheduling/adapters/inbound/http/dependencies.py`
  - `src/restaurant_hub/features/scheduling/adapters/inbound/http/schemas.py`
  - `src/restaurant_hub/features/scheduling/adapters/inbound/http/error_handlers.py`
  - `tests/unit/features/scheduling/adapters/test_http_dependencies.py`
  - `tests/unit/features/scheduling/adapters/test_http_schemas.py`
  - `tests/unit/features/scheduling/adapters/test_http_error_handlers.py`
- **O que fazer:**
  - `dependencies.py`: `get_access_guard` (chave de override que levanta se chamada),
    `authenticated_actor` (Depends), `SchedulingAccessGuard`/`CurrentActor`, `AccessRequirement` e os
    três requisitos (ler, gerenciar, própria — todos `names_unit=True`), `validate_identifier`
    (vazio, só-espaço, NUL ⇒ `InvalidIdentifierError` de scheduling), `validate_creation_id` (UUID
    canônico: `str(UUID(raw)) == raw`), `validate_day` e `validate_instant` (anos 2..9998 ⇒
    `InvalidScheduleRequestError`).
  - `schemas.py`: requests (criação, avaliação, publicação, as 11 variantes de operação com `op` e
    `extra="forbid"`, aceite com `key`; `max_length=500` nas listas), responses (§4.2 do concept), e
    os conversores puros: operação → DTO de application (com as validações de id, quantidade
    ≤ 2147483647 e instantes), aceite → `ViolationAcknowledgement` (texto → `Decimal` finito, senão
    `InvalidScheduleRequestError`; `PolicyKind` desconhecida ⇒ idem), result → response.
  - `error_handlers.py`: `SCHEDULING_ERROR_STATUS` (o único `dict` do módulo com chaves de exceção)
    com os 35 pares da §6 do concept; `resolve_status` pelo MRO; `error_code(exc)` (snake_case do nome
    da classe sem `Error`); `build_error_response` com `detail`, `type="scheduling_error"`, `code` e os
    campos de estado da §4.3 do concept (violações pela `ViolationResponse` de `schemas.py` — uma
    forma só para a violação na resposta de sucesso e no corpo de erro);
    `register_scheduling_error_handlers(app)` sobre as duas raízes. Sem entrada 401/403;
    comentários por faixa com o porquê das classificações não óbvias; os cinco inalcançáveis marcados.
- **Detalhes técnicos:** exceção de 8 arquivos declarada (PIPELINE §4.3 critério 2): a pasta
  `adapters/inbound/` e o mapa têm de nascer no mesmo commit, porque
  `test_status_map.py::test_bc_sem_mapa_de_status_tambem_nao_tem_borda_http` reprova BC com
  `adapters/inbound/` e sem `error_handlers.py`, e o mapa usa a `ViolationResponse` dos schemas, que
  usam os validadores das dependências. Nenhum request com `tenant_id`/`restaurant_id`/`user_id`
  (varredura de `model_fields`, CA9); instantes de saída sem offset; decimais de saída como texto.
- **Critério de aceite:** conversores com caso feliz e cada recusa da §6 (id, UUID, quantidade,
  decimal, política desconhecida, dia/instante extremo); CA9 por varredura; CA4
  (`test_status_map.py` passa a ver scheduling em `_COM_BORDA_HTTP`, com totalidade e handler nas
  duas raízes); teste par a par dos 35 status; lista exata dos `code`; corpos com estado (versão e
  vizinha, violações, ids de alocação e contagem, função, id em uso).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/scheduling/adapters tests/unit/features/scheduling/test_bc_independence.py tests/unit/test_status_map.py tests/unit/test_check_layout.py -q --no-cov
  ```
- **Commit sugerido:** `feat(scheduling): schemas, dependências e mapa de erros da borda de escala [4.5/task-05]`

---

### Task 06 — as sete rotas

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/adapters/inbound/http/router.py`
  - `tests/unit/features/scheduling/adapters/http_support.py` (o `Ambiente`: app FastAPI com o
    router, os handlers de scheduling e os compartilhados, use cases reais sobre os fakes, guard fake)
  - `tests/unit/features/scheduling/adapters/test_http_router.py`
- **O que fazer:** S1–S7 (§4.1 do concept), cada rota: validar identificadores e dias → 
  `guard.authorize(actor, <permissão>, unit_id=unit)` → command/query com `actor`,
  `tenant_id=scope.tenant_id`, unidade do path → **um** use case → response. Provedores `_get_*` que
  levantam se chamados.
- **Detalhes técnicos:** nenhuma rota lê `scope.unit_id` (varredura AST, CA9); `INVOCACOES` declara o
  corpo e a query válidos de cada rota e a totalidade é cobrada contra `router.routes`.
- **Critério de aceite:** caminho feliz de cada rota; CA14 (espião: permissão e unidade por rota, sem
  `tenant_id`; guard negando ⇒ use case não chamado); CA7 sem chamada a `authorize`; CA5 da vizinha
  (dublê de use case que levanta `ScheduleVersionConflictError(changed_neighbour_id=...)` ⇒ 409 com o
  corpo); CA8 (offset ⇒ 422 de scheduling; resposta sem offset).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/scheduling/adapters tests/unit/features/scheduling/test_bc_independence.py -q --no-cov
  ```
- **Commit sugerido:** `feat(scheduling): rotas do editor, do calendário e de minha escala [4.5/task-06]`

---

### Task 07 — wiring: sete use cases e o guard; os campos provisórios saem

- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/scheduling/adapters/test_composition_root_scheduling.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py` (o inventário congelado do
    wiring: três routers e três registradores, e a partição das rotas montadas subtrai também os pares
    do router de scheduling)
  - `docs/LAYOUT.md` (§6: a exceção provisória vira nota de que a 4.5 a removeu)
- **O que fazer:** `scheduling_access_guard = LocalAccessGuard(access=<a mesma IdentityAccessFacade
  sobre o mesmo authorize_action>, authenticate_request=guard.authenticate_principal)`; os sete use
  cases (`scheduling_create_schedule`, …) sobre os adapters Postgres, `LocalStaffReadAdapter`,
  `clock`, `id_generator` e o guard; campo `scheduling_access_guard` (anotado com o port); remover os
  três campos; `build_http_wiring` registra o router, o registrador de handlers e os oito overrides
  (`get_access_guard` + sete `_get_*`).
- **Detalhes técnicos:** o teste de composition root troca as travas da 4.4 por: contêiner com os sete
  use cases e o guard (e sem os três campos); cada use case sobre os adapters certos e o mesmo
  `Engine`; o guard sobre o mesmo `AuthorizeActionUseCase` e o mesmo `IdentityGuard` de identity e
  de staff; todo `_get_*` do router com override; só o composition root importa os adapters.
- **Detalhes de tamanho:** 4 arquivos, dentro do critério.
- **Premissa do gate 2 que muda** (`tests/e2e/test_deny_by_default.py`): depois da Task 01 nenhum papel
  do restaurante tem conjunto vazio, e a perna do 403 para S7 passa a negar pela unidade `"x"`
  inexistente (unidade invisível), não pela permissão. A docstring de `token_sem_permissao` (Task 01)
  diz isso; a permissão de S7 é provada pela CA14 (espião) e pela CA2 (matriz).
- **Critério de aceite:** CA10.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/scheduling tests/unit/test_status_map.py tests/unit/test_bootstrap.py tests/unit/test_check_layout.py tests/unit/features/identity/adapters/test_composition_root_identity.py tests/unit/features/staff/adapters/test_composition_root_staff.py -q --no-cov
  ```
  **Ponto 2 do plano de gates** (`lint-and-test` do PR verde no commit desta Task: integração e
  e2e, inclusive `test_deny_by_default.py`, passam a ver as rotas de scheduling).
- **Commit sugerido:** `feat(scheduling): montar os use cases de escala e retirar os campos provisórios [4.5/task-07]`

---

### Task 08 — e2e do fluxo do editor e de "minha escala"

- **Arquivos a criar:**
  - `tests/e2e/features/scheduling/__init__.py`
  - `tests/e2e/features/scheduling/conftest.py` (cenário pela API: restaurante, unidade, função
    habilitada, gerente, funcionários com login por R17)
  - `tests/e2e/features/scheduling/test_scheduling_flow.py`
- **O que fazer:** CA1 (criar → avaliar → 422 `unacknowledged_violations` → publicar com aceites →
  200 com `version` = 1 + operações efetivas → funcionário lê só os próprios turnos em S7); CA3
  (outro registro na mesma faixa não aparece; registro alocado, desligado e com novo login ⇒
  `shifts: []`); CA5 da própria escala (duas publicações sobre a mesma versão ⇒ 409 com
  `changed_neighbour_id: null` e versões diferentes); CA6 (409 `job_function_not_enabled_in_unit`;
  `true`/`false` em S2 e S5 depois de staff estreitar a função).
- **Comando de verificação:** roda no CI (`lint-and-test`); localmente só `ruff` e `mypy` nos
  arquivos (Postgres compartilhado).
- **Commit sugerido:** `test(scheduling): e2e do fluxo do editor e de minha escala [4.5/task-08]`

---

### Task 09 — e2e da matriz de autorização

- **Arquivos a criar:** `tests/e2e/features/scheduling/test_scheduling_authorization.py`
- **O que fazer:** CA2 — oito atores (owner, manager membro, manager não membro, hr membro, employee
  membro, employee não membro, dono de outro tenant, platform_admin) × S1–S7; permitido ⇒ status de
  sucesso; negado ⇒ 403 com o corpo constante de identity. Rotas de escrita com cenário próprio por
  caso; rotas de leitura sobre um cenário só por módulo (finding da 3.6 sobre o custo).
- **Comando de verificação:** CI.
- **Commit sugerido:** `test(scheduling): e2e da matriz papel por rota da escala [4.5/task-09]`

---

### Task 10 — e2e das faixas de status

- **Arquivos a criar:** `tests/e2e/features/scheduling/test_scheduling_status_bands.py`
- **O que fazer:** cada faixa (404, 409, 422) alcançável pela API real com o discriminador
  `scheduling_error` e o `code`; um cenário por erro alcançável da §6 (a lista dos inalcançáveis
  declarada e cobrada: todo erro do mapa ou tem cenário ou está na lista); CA7 e CA8 pela API (NUL e
  só-espaço no path, id de criação não UUID, quantidade acima do `INTEGER`, decimal malformado, dia e
  instante extremos, offset) — nenhum 500.
- **Comando de verificação:** CI. **Ponto 3 (saída).**
- **Commit sugerido:** `test(scheduling): e2e das faixas de status da escala [4.5/task-10]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check                # no lint-and-test do PR #261 (orquestração: Postgres compartilhado)
python scripts/check_technical_postexec.py docs/stages/4.5-scheduling-http/technical.md
make docs-check           # check_doc_frontmatter reprova marca "Lacuna para o concept da Stage 4.5" aberta com a Stage done
grep -n "Stage 4.5\|(4.5)\|a 4.5" docs/domain/scheduling/shift-scheduling.md   # CA13: cada ocorrência fechada ("fechada pela Stage 4.5") ou reendereçada (#258, #259, 4.6, 4.8)
```

### Verificações funcionais
- [ ] e2e do DoD verde no CI (CA1), com a matriz (CA2) e as faixas (CA4, CA7, CA8).
- [ ] Corrida de mutação disparada (`gh workflow run audit-gate.yml --ref feat/254-4-5-scheduling-http`)
      com o adapter do guard no `only_mutate`, e o resultado na §7.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch, em cada ponto do plano de gates
- [ ] Commit final `stage 4.5: complete` aplicado, com o roadmap e as marcas do doc de domínio (CA13)
- [ ] ADRs novos em `status: accepted`
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 ─► Task 02 ─► Task 03 ───────────────────► Task 07 ─► Task 08 ─► Task 09 ─► Task 10
                 └──► Task 04 ─► Task 05 ─► Task 06 ─┘
```

A Task 06 precisa do port com `authenticate` (02), do campo novo do DTO (04) e da borda (05); a 07
precisa do adapter (03) e do router (06).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| A síntese de corpo do `test_deny_by_default.py` não passa na validação das rotas novas (união por `op`, datas) | Corpo à mão em `_CORPOS_SOB_MEDIDA`, nunca relaxar a asserção (`[deviation]` na §7) |
| e2e vermelho só no CI (sem Postgres local) | Reproduzir o cenário na suíte unitária de borda, corrigir com `-fix`, reenviar |
| Corrida com a #217 no `pyproject.toml`/`test_mutation_scope.py` | Mudanças aditivas; resolver no rebase |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../roadmap.md`](../../roadmap.md) — §Stage 4.5
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §5, §6
- ADRs: 4.5.0001, 4.5.0002, 4.5.0003; 3.4.0002, 3.6.0001, 3.6.0002, 3.6.0003, 0.0.0016, 4.3.0002
- Skills: `fastapi-thin-adapter`, `hex-arch-python`, `pytest-with-fakes`, `task-ordering-hex`,
  `composition-root`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4** — exceto as disposições dos
> Checkpoints A (gravada na Fase 3A, com este arquivo ainda esqueleto) e
> B (na Fase 3B), formato abaixo. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.
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
  Inclui pergunta, opções, decisão, razão.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original; corpo
  diz o que mudou e por que ficou abaixo do threshold de perguntar.
- `[measurement]` — evidência que o plano manda colar aqui (tempo do
  ponta a ponta, saída de mutação obrigatória, prova manual, execução
  real, auditoria de testes), sem decisão nem desvio. Corpo:
  **Contexto:** que critério/Task pede a evidência; **Medição:** comando,
  ambiente e saída bruta; **Razão:** o que a evidência prova.

Vocabulário fechado (CONVENTIONS §3.4): `decision` (ou `decision:E` /
`decision:C`, skill `evidence-resolution` §5), `finding`, `deviation`,
`measurement`. Outra tag no cabeçalho de entrada é recusada por
`scripts/check_technical_postexec.py`.

**Disposições dos Checkpoints** (CONVENTIONS §3.4): uma entrada
`[decision]` por checkpoint — e por bloco no C —, gravada no commit que
fecha o checkpoint (A → `conceptual approved`; B → `technical approved`;
C → o `-fix` do bloco ou o commit seguinte). Sem as do A e do B, technical
`done` é recusado pelo script.

```markdown
### YYYY-MM-DD — [decision] Checkpoint A — disposições — <Autor>
**Contexto:** rodada <n> de 3; revisores: <lentes>.
- **A1** (<severidade>, <lente>) <achado em 1 linha> → corrigido (<hash ou marca do commit>)
- **A2** (…) … → refutado — artefato: <trecho de teste, código ou saída, colado>
- **A3** (…) … → escalado (<pergunta P, HALT ou issue>)
```

Checkpoint sem achado grava a entrada mesmo assim ("nenhum achado material").
O cabeçalho do C é `Checkpoint C (bloco Tasks NN–MM)`.

### 2026-11-23 — [decision] Checkpoint A — disposições — Claude (Opus 5.5)
**Contexto:** rodada 1 com dois revisores de contexto zerado (conformidade; domínio/testabilidade) e
o `decision-reviewer` da `evidence-resolution` §4.3; rodada 2 de re-verificação das correções (um
revisor). Antes deles, dois `evidence-verifier` conferiram as citações dos sete registros
`[decision:E|C]` (D-ERR-409 e D-IDS voltaram `parcial` e foram corrigidos; os demais, `sustenta`).
Todas as correções entram no commit `stage 4.5: conceptual approved`.
- **A1** (major, ambos) CA1 exigia "versão 2"; a versão soma 1 por operação efetiva → corrigido (CA1: 1 + operações efetivas)
- **A2** (major, domínio) a matriz e2e não prova a autorização da rota (o use case nega igual) → corrigido (§5 inv. 4; CA14, teste de borda com espião)
- **A3** (major, ambos + decision-reviewer) quatro `Duplicate*` em 409 contra o ADR 3.4.0002 §4 → corrigido (422; faixas reescritas na §6, D-ERR-BANDS e ADR 4.5.0002)
- **A4** (major, domínio) o pino de R17 e a docstring da fachada quebram sem critério → corrigido (CA15, propriedade; divergência 1; nota no ADR 2.7.0001)
- **A5** (major, domínio) CA6 passava sem a mudança do calendário → corrigido (CA6 exige `true` e `false` em S2 e S5)
- **A6** (major, domínio + decision-reviewer) `MissingStaffRecordsError` sem saída para o cliente e vindo também das leituras → corrigido (§6, risco na §10, consequência no ADR 4.5.0002; #194 pré-requisito de produção)
- **A7** (major, domínio) CA2 sem `platform_admin` → corrigido
- **A8** (major, domínio) CA3 vácuo → corrigido (alocado no recorte, desligado, novo login)
- **A9** (major, conformidade) D-DEACT sem errata do ADR 3.5.0003 §5 → corrigido (nota datada no ADR; issue #259)
- **A10** (major, conformidade + decision-reviewer) protocolo da borda declarado no adapter de entrada, contra LAYOUT §5 e o precedente de staff → corrigido (o port de scheduling ganha `authenticate` e tenant opcional, lei L-SG5; D-GUARD, ADR 4.5.0003; divergência 2)
- **A11** (major, decision-reviewer) D-CREATE quebra o princípio da matriz congelada e o comentário de `role.py` → corrigido (consequência declarada em D-CREATE e no ADR 4.5.0001; comentário de `role.py` reescrito na Task de identity; destaque no PR)
- **A12** (major, decision-reviewer) D-CONFIG: tenant-wide é inócuo só para o dono, alargar não é aditivo, a 4.8 muda o port → corrigido (D-CONFIG e ADR 4.5.0001 reescritos; consequência para a 4.8 declarada)
- **A13** (major, decision-reviewer) D-OWN: o funcionário não descobre a própria unidade → corrigido (limite declarado; #258 pré-requisito do piloto com funcionários; risco na §10)
- **A14** (minor, domínio) CA5 "o lote reenviado passa" não é propriedade → corrigido (§6 e CA5: reenvio pode voltar 422; asserção sobre o corpo do 409)
- **A15** (minor, domínio) tipo do decimal do aceite ambíguo → corrigido (`str` + conversor da borda)
- **A16** (minor, domínio) partes do CA7 intestáveis → corrigido (path só-espaço/NUL; corpo; as duas operações de quantidade)
- **A17** (minor, domínio) forma da `key` do aceite subespecificada → corrigido (eco exato, campos anuláveis)
- **A18** (minor, domínio) regra de faixas incoerente (404 × 422 para referência no corpo) → corrigido (outro agregado = 404; valor interno = 422)
- **A19** (minor, ambos) CA13 não objetivo e marca do §4 ("e-mail como efeito") sem destino → corrigido (CA13 lista linhas e marcas; D-EMAIL)
- **A20** (minor, conformidade) `view_own_schedule` para `hr`/`manager`/`owner` sem nota nos ADRs 3.4.0006 e 4.1.0004 → corrigido (notas datadas)
- **A21** (minor, conformidade) premissa (b) de D-OWNALL parcialmente falsa → corrigido (reescrita: rotas de identity × R17 pela fachada)
- **A22** (minor, conformidade) regra de corpo "nenhum registro que o pedido não nomeou" larga demais → corrigido ("nenhum registro invisível")
- **A23** (minor, conformidade) dia extremo produz 500 → corrigido (§6 e CA7; na rodada 2, estendido aos limites de faixa, que estouram em `operational_day_of`)
- **A24** (minor, conformidade) corpo de S1 não especificado → corrigido (§4.2)
- **A25** (minor, decision-reviewer) teto de 500 do lote sem medição → corrigido (declarado como premissa não medida em D-BATCH; reversível)
- **A26** (contrato, rodada 2) a extensão do port contradiz o ADR 4.3.0002 §Decision 1 sem nota → corrigido (nota datada no ADR 4.3.0002; docstring do port reescrita na Task que o estende)
- **A27** (minor, rodada 2) marcas do corpo do doc de domínio que citam a 4.5 faltavam no CA13 (§3.5, §3.9, §3.10.2, nota de §6) → corrigido

### 2026-11-23 — [decision] Checkpoint B — disposições — Claude (Opus 5.5)
**Contexto:** rodada 1 com um revisor de contexto zerado (matriz de rastreabilidade, LAYOUT, Task
atômica, plano de gates contra o PIPELINE §9.6). Correções no commit `stage 4.5: technical approved`.
- **B1** (major) Task 07 deixaria vermelho o inventário congelado do wiring em `test_composition_root_staff.py` → corrigido (arquivo na Task 07; varredura na tabela da §1)
- **B2** (major) Task 04 quebraria `test_dtos.py`, que chama os mapeadores → corrigido (arquivo na Task 04, parâmetro obrigatório keyword-only, caso no nível do mapeador; exceção de 8 arquivos)
- **B3** (major) CA12 parcial: a fachada real não era exercitada em unit → corrigido (Task 03 ganha o teste da cadeia real adapter → fachada → `AuthorizeActionUseCase` sobre fakes de identity)
- **B4** (major) o comando da Task 02 truncava o Postgres compartilhado via `test_no_implementation_branching.py`, que nem cobre o guard → corrigido (fora do comando e da tabela; conformidade do fake por `_conforms` e pelas leis)
- **B5** (minor) varreduras alimentadas fora dos comandos (`test_bc_independence.py` de scheduling nas Tasks 05/06; `test_check_layout.py` nas 03/04/05/07; alcance facade-only na 03) → corrigido
- **B6** (minor) Task 03 descrevia por baixo a mudança no `test_bc_independence.py` de scheduling e o "se" do `test_mutation_scope.py` → corrigido (segunda aresta nomeada com casos plantados; conjunto exato afirmado)
- **B7** (minor) a premissa de `token_sem_permissao` muda de verdade (S7 nega pela unidade, não pela permissão) → corrigido (premissa declarada na Task 07; permissão de S7 provada por CA14 e CA2)
- **B8** (minor) CA13 sem check objetivo → corrigido (passo 7 do "Como usar" e verificação na §3)

### 2026-11-23 — [deviation] Task 01 — teste de ordem de `authorize_requirement` fora da lista — Claude (Opus 5.5)
**Contexto:** `tests/unit/features/identity/application/test_authorize_requirement.py` (CA04 da 2.7) usava `required_permissions_for_role(Role.OWNER)` como insumo de um cenário sobre a **ordem** dos pedidos, e o conjunto do `owner` cresceu com as permissões de escala.
**Razão:** o insumo virou o conjunto fixo das quatro permissões que o cenário sempre teve; a asserção (permissões por fora, unidades na ordem dada, sem deduplicar) não mudou. Ajuste mecânico abaixo do limiar de pergunta; o arquivo entrou no commit da Task 01.

### 2026-11-23 — [measurement] Ponto 1 do plano de gates (Task 03) — Claude (Opus 5.5)
**Contexto:** plano de gates da §1, ponto 1, depois da Task 03; orquestração autônoma — o ponto é o `lint-and-test` do Actions no commit da Task.
**Medição:** o primeiro push das Tasks 01–03 não disparou o CI: o PR estava em conflito com `develop` (a #243 mergeou e mexeu na tabela de issues do roadmap). Rebase simples sobre `origin/develop` (`2bc397ad`), conflito do roadmap resolvido mantendo as três linhas (#258, #259, #260), `push --force-with-lease`. Hashes depois do rebase: Task 01 `7887bf79`, Task 02 `b7577217`, Task 03 `2ba7116e`. Run `ci` 45134080325, job `lint-and-test` **success** sobre `2ba7116e` — https://github.com/MarceloSanC/restaurant-hub/actions/runs/45134080325/job/137556047846
**Razão:** o ponto 1 fecha o grupo que muda contrato lido por outro BC e por outra camada (enum e mapa de papéis, port do guard, `.importlinter`) antes de a borda ser escrita sobre ele.

### 2026-11-23 — [decision] Checkpoint C (bloco Tasks 01–03) — disposições — Claude (Opus 5.5)
**Contexto:** rodada 1, um revisor de contexto zerado sobre `744ddb69..2ba7116e`, com as skills `fastapi-thin-adapter`, `hex-arch-python`, `pytest-with-fakes` e `composition-root`; seis mutações aplicadas à mão no adapter (três mortas, três sobreviventes). Correções no commit `[4.5/task-03-fix]`.
- **C1** (minor) a mensagem da `PermissionDeniedError` do ator sem tenant e a do `TypeError` de wiring sobreviviam à mutação → corrigido (asserção de papel e permissão na mensagem; `match="object"`, como em staff)
- **C2** (minor) trocar `TenantId(target_tenant_id)` por `TenantId(actor_tenant_id)` sobrevivia (os dublês sempre igualavam os dois) → corrigido (caso com `grant.actor_tenant_id` diferente do tenant pedido; o escopo traz o pedido)
- **C3** (minor) a suíte do fake não cobria o tenant `""` explícito com o alvo do ator concedido (só a unidade vazia) → corrigido (caso `("", u1)` na parametrização de alvo vazio)
- Pergunta fixa ("regra que já existe em outro lugar / no dono errado?"): nenhum achado — a resolução do tenant omitido repete a de staff por decisão (ADR 4.5.0003 §Decision 2).

### 2026-11-23 — [decision] Checkpoint C (bloco Tasks 04–06) — disposições — Claude (Opus 5.5)
**Contexto:** rodada 1, um revisor de contexto zerado sobre `2ba7116e..5a332c32` (src e tests), com as skills `fastapi-thin-adapter`, `hex-arch-python`, `pytest-with-fakes` e `task-ordering-hex`; onze mutações aplicadas e revertidas (seis sobreviventes). Correções em `[4.5/task-05-fix]` (conversor) e `[4.5/task-06-fix]` (testes de rota, esta entrada).
- **C4** (importante) medida gigante no aceite (`"1E+1000000"`) com a `key` casando passava pelo conversor e estourava `decimal.Overflow` na subtração de `_publish._covers` → 500 → corrigido (`to_decimal` recusa mais de 15 dígitos inteiros ou de 12 decimais com `InvalidScheduleRequestError`; teste de conversor e de rota)
- **C5** (cobertura) apagar `check_acknowledgement_identifiers` da rota S4 ficava verde → corrigido (teste de rota: NUL na `key` do aceite ⇒ 422 `invalid_identifier` sem `authorize`)
- **C6** (cobertura) o mapeamento campo a campo de `to_operation` não era travado (`counts_toward_workload`, `counts`, `break_minutes` fixos sobreviviam) → corrigido (comparação campo a campo por variante, valores não default e o intervalo nulo da alocação)
- **C7** (cobertura) o recorte de S5 e o `limit` de S6 não eram travados → corrigido (recorte com `first_day < last_day`; `limit=1` sobre duas escalas e `limit=53` ⇒ 422)
- **C8** (nit) `_not_wired` duplicado no pacote e `validate_identifier` copiado de staff → refutado — artefato: `grep -n "def _not_wired" src/restaurant_hub/features/staff/adapters/inbound/http/*.py` devolve `dependencies.py:180` e `router.py:193` — a forma é a do precedente de staff, e o validador de identificador é por BC (ADR 3.6.0002; nenhum módulo de scheduling importa staff). A outra metade do nit — o teto de anos protege aritmética de domínio e mora só na borda — vira o `[finding]` abaixo.

### 2026-11-23 — [finding] Teto de anos de dia e instante só na borda HTTP — Claude (Opus 5.5)
**Contexto:** `validate_day`/`validate_instant` (anos 2 a 9998) impedem o `OverflowError` das somas de `timedelta` do domínio (período, vizinhas, `operational_day_of`), mas só para quem chega pela borda HTTP (D-IDS/concept §6). Um driver que não seja HTTP — o job de notificação da 4.6, o auto-fill do Step 5 — chamaria os use cases sem o teto.
**Direção sugerida:** levar o teto para `require_day` (`application/use_cases/_inputs.py`) e para o `TimeRange`/`SchedulePeriod`, com `InvalidScheduleRequestError`/`InvalidTimeRangeError`, quando nascer o primeiro driver fora do HTTP. **Stage candidata:** `4.6-schedule-notifications` (primeiro driver não HTTP do BC).

### 2026-11-23 — [measurement] Ponto 2 do plano de gates (Task 07) — Claude (Opus 5.5)
**Contexto:** plano de gates da §1, ponto 2, depois do wiring (Task 07). Antes do push, rebase simples sobre `origin/develop` (`88c3ff9d`: #217, #242, #243 mergeadas), sem conflito; `check_layout.py` (regra 10 derivada, #243) e `lint-imports` (12 contratos) verdes localmente. Hashes depois do rebase: Tasks 01–07 `8e9feb70`, `00262ea6`, `99eaaf6d`, `aee915fb`, `e81b176b`, `928ad174`, `f5a0157a`; fixes `72f34ea2`, `61a65f98`, `9ad8bd23`.
**Medição:** run `ci` 45138602830, job `lint-and-test` **success** sobre `f5a0157a` — https://github.com/MarceloSanC/restaurant-hub/actions/runs/45138602830/job/137570771955 (inclui `test_deny_by_default.py` e `test_credential_responses_are_not_stored.py` vendo as sete rotas de scheduling, e a integração da 4.4 sem os campos provisórios).
**Razão:** o ponto 2 confirma o composition root e as varreduras globais antes dos e2e das Tasks 08–10.

### 2026-11-23 — [measurement] Auditoria de testes (subagente independente), rodada 1 — Claude (Opus 5.5)
**Contexto:** gate "Auditoria de Testes" do PROMPT de sessão única, por subagente que não escreveu os testes, sobre o código e os testes das Tasks 01–07 e os e2e das Tasks 08–10 (lidos, não executados: Postgres compartilhado).
**Medição:** 1666 testes unitários verdes; 27 mutações reais aplicadas e restauradas (sha256 conferido), **22 mortas e 5 sobreviventes**:
- guard (`LocalAccessGuard.authorize`): 5/5 mortas (tenant `or`, negação do ator sem tenant, tenant do escopo, checagem de tipo);
- router (ordem validar → autorizar, permissão da rota, tenant omitido): 6/6 mortas;
- mapa de erros: 6/7 — sobreviveu `resolve_status` com fallback 422 → 500;
- conversores: 5/9 — sobreviveram as três fronteiras de `to_decimal` (`>`/`>=`, `<`/`<=`, `value != 0`) e `DemandResponse.function_enabled_in_unit` constante (só o e2e da CA6 a matava); a ordenação dos dias na `key` da resposta é equivalente (o domínio entrega os dias ordenados).
Respostas ao questionário: (1) CA1–CA15 com teste nomeado, CA13 é fechamento documental; (2) casos da §6 com teste, menos o corpo fora do schema pela rota e o `schedule_id` só-espaço; (3) acima; (4) leis no fake e no adapter (dublês + cadeia real); (5) e2e conferidos contra rotas e regras de staff, sem divergência; (6) faixas par a par e por e2e.
**Razão:** as lacunas viram a Task 11 extra (testes) e um `-fix` da Task 05: a docstring de `to_decimal` prometia 15 dígitos inteiros e o código aceitava 16; o limite passou a contar dígitos inteiros e casas decimais sem contexto decimal (o `normalize()` de `1E+1000000` estoura o contexto).

### 2026-11-23 — [decision] Checkpoint C (bloco Tasks 07–10) — disposições — Claude (Opus 5.5)
**Contexto:** rodada 1, um revisor de contexto zerado sobre o commit da Task 07 (`f5a0157a`), os e2e das Tasks 08–10 (ainda não commitados na revisão) e o diff de `to_decimal` da auditoria de testes, com as skills `composition-root`, `fastapi-thin-adapter` e `pytest-with-fakes`. O revisor rodou 1770 testes unitários e conferiu passo a passo os e2e contra as rotas e regras de staff e identity: nenhuma falha esperada. Correções nos commits das Tasks 08–10 (antes do primeiro commit deles), em `[4.5/task-05-fix]` e em `[4.5/task-11-extra]` (esta entrada).
- **C9** (minor, contrato) o teto de casas decimais de `to_decimal` recusaria medida que o próprio servidor emite (carga contratada com muitas casas em staff), travando o aceite, e não evitava 500 nenhum (underflow não é armadilha) → corrigido (fica só o teto de 15 dígitos inteiros, contado por `adjusted()` sem contexto decimal; teste com a medida de 13 casas aceita e com `1E-1000030`)
- **C10** (minor) faltava `tests/e2e/features/scheduling/__init__.py` (o conftest carregava duas vezes) → corrigido (Task 08)
- **C11** (minor) os três arquivos e2e sem `pytestmark = pytest.mark.e2e` → corrigido (Tasks 08–10)
- **C12** (minor) a matriz CA2 contava as rotas contra si mesma → corrigido (Task 09: total sobre `router.routes`)
- **C13** (minor) a Task 10 pedia limite de faixa extremo, quantidade por `change_demand_quantity` e id só-espaço no corpo pela API → corrigido (Task 10)
- **C14** (minor) a Task 09 pedia um cenário por módulo para as rotas de leitura → desvio registrado abaixo
- Pergunta fixa: a fachada de acesso de scheduling é uma instância nova sobre o **mesmo** `AuthorizeActionUseCase` (sem estado) — refutado como achado: artefato `composition_root.py` › `scheduling_access_guard = SchedulingLocalAccessGuard(access=IdentityAccessFacade(authorize_action=authorize_action), …)`, a mesma forma do guard de staff, e `test_o_guard_decide_sobre_o_mesmo_authorize_action_…` trava o `authorize_action` e o `IdentityGuard` por identidade.

### 2026-11-23 — [deviation] Task 09 — um cenário por caso na matriz e2e — Claude (Opus 5.5)
**Contexto:** a Task 09 previa as rotas de leitura sobre um cenário só por módulo (finding de custo da 3.6). A matriz monta o cenário inteiro em cada um dos 56 casos.
**Razão:** o `truncar_tudo` das fixtures de e2e é por teste (`app_e2e`), e um cenário de módulo exigiria um segundo regime de fixture só para esta suíte; as rotas de escrita precisam de cenário próprio de todo jeito. O custo fica no CI (medido no run do ponto 3, abaixo), sem afetar o isolamento.

### 2026-11-23 — [decision] Task 11 extra — o que a auditoria de testes pediu — Claude (Opus 5.5)
**Contexto:** a auditoria (entrada `[measurement]` acima) deixou 5 sobreviventes e 3 lacunas de teste.
**Decisão:** testes acrescentados: fronteiras de `to_decimal` (aceita 15 dígitos inteiros e qualquer casa; recusa 16 e o expoente gigante); `DemandResponse` com `function_enabled_in_unit` falso; demanda órfã `false` em S2 e S5 pela rota sobre os fakes; fallback 422 do `resolve_status` nas duas raízes; corpo fora do schema (op desconhecida, lote de 501) ⇒ 422 com o corpo constante `validation_error`; sem credencial e corpo inválido ⇒ 401; `schedule_id` só-espaço no path; a trava de CA9 sem depender do nome `scope`; piso de `_TOTAIS_MINIMOS["scheduling"]` em 35. A ordenação dos dias na `key` da resposta é mutante equivalente (o domínio entrega os dias ordenados) e não ganhou teste.
**Razão:** cada teste mata um sobrevivente ou fecha uma lacuna nomeada pela auditoria; a rodada 2 da auditoria re-executa as mutações.

<!-- END: post-execution -->
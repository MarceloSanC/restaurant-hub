---
title: Concept — API de equipe (borda HTTP)
description: Definição do que será feito nesta Stage e por quê, com decisões técnicas relevantes
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, staff-http, fastapi, router, schemas, rbac, error-handler, e2e]
status: done
created_at: 2026-08-18
updated_at: 2026-08-31
stage_id: 3.6-staff-http
stage_title: API de equipe (borda HTTP)
step_id: 3
step_title: Equipe da unidade
depends_on: [3.4-staff-access-scope]
---

# Concept — Stage 3.6 — API de equipe (borda HTTP)

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Status (apenas dois estados).** `draft` desde a criação; `done` após o gate
> humano. Regressão `done → draft` é permitida quando a Fase 3B revela gap
> material aqui.

> **A bifurcação F1 foi decidida pelo sponsor em 2026-08-18 (§13).** Ela era de
> contrato e de alcance: medido contra o código real, **nenhuma das 16 rotas era
> alcançável por nenhum papel**, porque o router de staff não tinha como nomear o
> tenant alvo que `AuthorizeActionUseCase` exige. A decisão está no
> **[ADR 0.0.0005](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)**,
> global e transversal: o tenant vem do token e é resolvido no `composition_root`;
> o inventário de rotas **permanece sem tenant no path — agora por regra, não por
> omissão**. Nenhuma assinatura de port muda.
>
> **Numeração de critério é estável.** A resolução de F1 **acrescentou** um
> critério no fim da §11 (**CA36**, pulando o 35 — ver a nota da §11); não
> renumerou nenhum, exatamente como esta seção
> prometia. A regra existe porque a renumeração feita no corte da Stage 3.4
> quebrou os ponteiros de dois ADRs `accepted` (`## Errata` do ADR 3.4.0001) — e
> esta Stage é justamente a que conserta o estrago.

## 1. Escopo

### Dentro do escopo

- **Adapter de entrada HTTP do BC staff** — `features/staff/adapters/in/http/`
  com `router.py`, `schemas.py`, `dependencies.py` e `error_handlers.py`, no
  mesmo desenho da Stage 2.4 (adapter fino; Pydantic só no boundary; um handler
  por raiz de BC).
- **As 16 rotas** do inventário ratificado no bloco 3.6 do `roadmap.md`
  (§4.1) — quatro de função de trabalho e doze de funcionário —, uma por use
  case já wired.
- **Enforcement de acesso por `Depends`, nunca middleware** (ADR 2.4.0003): cada
  rota declara a permissão exigida e o alvo, e delega a decisão ao port
  `AccessGuard` da Stage 3.4.
- **Endereçamento do registro pelo path, nunca pelo escopo devolvido** — o
  router não lê `AuthorizedScope.unit_id` (§5.4, ADR 3.6.0001). Fecha o finding
  mais perigoso herdado da 3.4.
- **Validação de identificador na borda** — todo `id` que chega pela
  requisição — **path, query ou corpo** — é rejeitado quando vazio,
  só-whitespace ou contendo o byte NUL, **antes** de qualquer chamada de
  autorização (§5.14, ADR 3.6.0002). Fecha o segundo finding herdado.
- **Conversão de `weekly_hours` na borda** — `Decimal("abc")` levanta
  `decimal.InvalidOperation`, que **não** é `StaffError` e viraria 500; a borda
  converte e traduz para `InvalidWeeklyHoursError` (§6.3, ADR 3.6.0003).
- **Resolução do tenant no `composition_root`** — o tradutor preenche o
  `tenant_id` a partir do ator autenticado quando a rota não o nomeia, e o
  significado de `tenant_id=None` passa a estar **escrito no docstring do port**,
  valendo para as **duas** implementações (§5.3, §7 D9, ADR 0.0.0005). É o que
  torna as 16 rotas alcançáveis.
- **Mapa exceção → status HTTP do BC staff**, total e verificado par a par,
  honrando `UnavailabilityNotFoundError` = 422 (§6.1, ADR 3.4.0002).
- **Schemas de boundary que preservam as garantias do domínio** — união
  discriminada para o perfil de jornada, `weekly_hours` como string, datetimes
  ingênuos, conjuntos ordenados na saída (§4.2, ADR 3.6.0003).
- **Wiring de dois routers**: `HttpWiring` deixa de assumir um único router e um
  único registrador de handlers; `composition_root` ganha 17 overrides
  (16 use cases + o guard) e `app.py` registra as duas superfícies (§7 D5).
- **Testes e2e** (`tests/e2e/features/staff/`) contra app real e Postgres real,
  cobrindo o fluxo feliz do DoD, o isolamento entre unidades, o acesso negado e
  as faixas de status.
- **Reconciliação dos ponteiros de CA dos ADRs pré-corte** (3.4.0001, 3.4.0002,
  3.4.0004) — o quinto finding herdado, §7 D6.

### Fora do escopo (explicitamente)

- **Paginação** das duas listagens — ADR 3.4.0004, consumido como decidido; a
  regex `_ORDER_BY` de `test_staff_conduct.py` › `_ORDER_BY` continua correta e o antídoto
  segue escalado junto com a paginação.
- **Guarda de duplicidade na cópia** — ADR 3.4.0005, consumido como decidido.
- **Leitura de funcionário por id** — `non_goals` do bloco 3.6 do roadmap; a
  avaliação que a issue #43 pede está em §7 D7, com a consequência declarada.
- **Vínculo de login do funcionário** (`user_id`, `IdentityGateway`) — Stage 3.5.
- **Qualquer noção de escala, demanda ou alocação** — Step 4.
- **Frontend** e qualquer decisão de UX (confirmação de cópia, seletor de
  unidade).
- **Controle otimista de concorrência** — ADR 3.3.0006, segue aberto; "última
  escrita vence" continua sendo o comportamento.
- **Byte NUL em nomes de `identity`** (`Restaurant`/`Unit`/`User`) — outro BC;
  `[finding]` em §10.
- **Busca ampla de funcionário no restaurante inteiro** — operação separada, com
  permissão própria (`non_goals` da 3.4).

### Reconciliação do bloco 3.6 do roadmap

O bloco `3.6-staff-http` foi escrito **depois** do corte e com os achados em
mãos, e por isso se sustenta em quase tudo. Três eixos precisam de nota datada no
fechamento da Stage:

1. **`arquivos_a_modificar` está incompleto em dois itens**, e a decisão de F1 os
   fixou: entram `features/staff/application/ports/out/access_guard.py` (docstring
   do contrato — **não** a assinatura, que já declara
   `tenant_id: str | None = None`) e `tests/fakes/features/staff/in_memory_access_guard.py`,
   porque a lei do tenant resolvido vale para as **duas** implementações do port.
2. **`contratos_introduzidos` está incompleto** — além dos schemas e do mapa
   `STAFF_ERROR_STATUS`, a Stage introduz o **validador de identificador de
   borda** (ADR 3.6.0002) e o **conversor de `weekly_hours`** (ADR 3.6.0003), os
   dois contratos porque definem o status de classes inteiras de entradas que
   hoje terminam em 500 (§4, §6.3).
3. **`definition_of_done` tem dois itens e a Stage tem 16 rotas.** Os dois itens
   continuam corretos e continuam sendo o DoD; a §11 os detalha em critérios
   parametrizados sobre o domínio enumerado, sem substituí-los.

### Vínculo com o roadmap

Esta Stage fecha o **Step 3 — Equipe da unidade** do lado da superfície. As
Stages 3.1 (domínio), 3.2 (use cases), 3.3 (persistência) e 3.4 (acesso e
escopo) entregaram um BC completo que **nada no boot da aplicação alcança**: o
próprio `composition_root.py` declara que os 16 use cases e o `staff_access_guard`
"nascem sem consumidor", e que o consumidor é esta Stage. É aqui que o Step 3
passa a ser exercitável pelo entrypoint real, que é o critério do DoD.

## 2. Objetivo da Stage

Ao final desta Stage, os 16 use cases de equipe são alcançáveis por HTTP sob
enforcement de acesso composto no boundary, de modo que um gerente autenticado
cadastra função e funcionário pela API real, um funcionário de outra unidade
permanece invisível e inalcançável, e nenhum conteúdo de requisição — corpo,
path ou query — produz 500.

## 3. Contexto e premissas

### Contexto

**O BC staff é surdo-mudo hoje, e a Stage 3.4 mediu isso no gate de saída:**
`features/staff/adapters/in/` não existe, `build_http_wiring` devolve o router de
identity por identidade de objeto, e os 16 use cases mais o `AccessGuard` seguem
sem consumidor. Falta o adapter de entrada — e com ele três coisas que só a borda
pode fazer:

1. **Origem do escopo.** Todo command/query de staff carrega `tenant_id`
   (ADR 3.2.0002) e, desde a 3.4, os dez que atuam sobre registro existente
   carregam também `unit_id` (ADR 3.4.0007). Nenhuma camada de staff sabe de onde
   esses valores vêm. Vêm do ator autorizado e do endereço da requisição, e é a
   borda que os extrai. **O tenant vem do token e é resolvido no
   `composition_root`** — regra transversal do ADR 0.0.0005, §5.3.
2. **Construção dos value objects.** Os commands chegam com `WorkloadProfile`,
   `ShiftPreference` e `UnavailabilityPeriod` **já construídos**; a Stage 3.2 §6
   declarou explicitamente que os erros de construção "não são alcançáveis por
   nenhum caminho de use case" e que existem para que a borda saiba que precisa
   mapeá-los.
3. **Classificação HTTP dos erros.** O `application/errors.py` de staff diz, no
   docstring, que "o pior caso não-ajustado é 422; a Stage 3.4 refina para
   404/409 registrando handlers, **sem tocar nesta camada**". A MRO
   `… → StaffError → NotFoundError → DomainError` foi desenhada para que o
   handler daqui ganhe dos genéricos de `shared`.

**A Stage irmã é a 2.4.** O BC identity resolveu os mesmos quatro problemas e o
código está no repo (`features/identity/adapters/in/http/`). Esta Stage
**replica o desenho**, não o reinventa — e onde diverge, diverge por razão
nomeada (§7).

**Os dois buracos de acesso que o Checkpoint A da 3.4 encontrou já estão
fechados** — e é por isso que esta Stage pode existir sem reabri-los:

- **Exfiltração intra-tenant.** A unidade entrou no **endereço** do funcionário
  até a assinatura do port (ADR 3.4.0007): quem não sabe a unidade não consegue
  formar a chamada, e o registro alheio responde `EmployeeNotFoundError`,
  indistinguível de id inexistente. Um gerente da unidade A que enderece
  `PUT /units/A/employees/{id-de-B}/…` recebe **404**, não o registro de B.
- **Recurso tenant-wide para papel unit-scoped.** `MANAGE_JOB_FUNCTIONS` entrou
  em `TENANT_WIDE_PERMISSIONS` (ADR 3.4.0008), então o passo 4 de
  `AuthorizeActionUseCase` dispensa a exigência de unidade **por permissão**, e
  `manager`/`hr` alcançam as quatro rotas de catálogo.

### Premissas

- **Os handlers genéricos de `shared` continuam registrados** e continuam sendo
  rede de segurança, não caminho principal.
- **O handler de identity é registrado sobre a app inteira**
  (`@app.exception_handler(IdentityError)`, `error_handlers.py` › `register_identity_error_handlers`), e
  Starlette resolve por `type(exc).__mro__`. Logo um `IdentityError` levantado
  dentro de uma rota de **staff** já sai com o corpo constante de identity, sem
  nada novo. É o que sustenta §5.8.
- **Nenhuma exceção herda das duas raízes** (`IdentityError` e `StaffError`) — a
  competição de handlers por MRO só é determinística sob essa condição
  (ADR 3.4.0002 §Consequences).
- **Não há `Unit` nem `UnitMembership` em staff, e não haverá.** O contrato
  `bc-independence` segue **sem nenhum `ignore_imports`**, e há teste que lê o
  `.importlinter` para provar (`tests/unit/features/staff/test_bc_independence.py`).
- **`create_engine` não abre conexão**, então registrar um segundo router não
  muda o comportamento de boot.
- **A cadeia de setup do e2e é alcançável só por rotas reais**: `platform_admin`
  semeado pelo repositório → `POST /restaurants` → `POST /restaurants/{id}/owners`
  → `POST /restaurants/{id}/units` → `POST /users` com `unit_ids` (que cria a
  `UnitMembership`). Nenhuma rota falta, e o padrão está em
  `tests/e2e/features/identity/conftest.py`.
- **Postgres real é exigido pelos testes e2e** (ADR 2.3.0001), e `truncar_tudo`
  já limpa as tabelas de staff.

### Dependências

- `3.4-staff-access-scope`: o port `AccessGuard` com as leis L-AG1…L-AG4, o DTO
  `AuthorizedScope`, o tradutor `_IdentityAccessGuard` no composition root, as
  duas permissões de staff, `TENANT_WIDE_PERMISSIONS`, a unidade na assinatura
  do port, `DayPeriod.from_string` e a recusa do byte NUL no domínio.
- `3.3-staff-persistence`: os dois repositórios Postgres, o wiring dos 16 use
  cases e a lei `L-ORD` (ADR 3.3.0003), que torna a resposta das duas rotas `GET`
  determinística sem esta Stage ordenar nada.
- `3.2-staff-application`: os 16 use cases, os DTOs e a hierarquia de erros com a
  MRO desenhada para o handler daqui.
- `3.1-staff-domain`: as entidades e os value objects que a borda constrói.
- `2.4-identity-http`: `IdentityGuard`, `error_handlers.py`, `HttpWiring` e o
  padrão de `dependency_overrides`.
- `2.2-identity-application`: `AuthorizeActionUseCase` e os dois eixos
  fail-closed (ADR 2.2.0002).

## 4. Contratos

### Introduzidos

- **Schemas Pydantic de request/response** (`adapters/in/http/schemas.py`) —
  boundary only. Inventário em §4.2.

- **Mapa `STAFF_ERROR_STATUS`** (`adapters/in/http/error_handlers.py`) —
  `dict[type[StaffError], int]` **total** (18 entradas), com resolução por
  `__mro__` e default 422, mais `resolve_status` e `build_error_response`
  espelhando os de identity (§6.1, ADR 3.4.0002).

- **Validador de identificador de borda** (`adapters/in/http/dependencies.py`) —
  função única que recebe o valor cru de um identificador vindo da requisição —
  **path, query ou corpo** — e devolve a string validada, levantando
  `InvalidIdentifierError` (erro de **domínio** de staff, já existente) quando o
  valor é vazio, só-whitespace ou contém o byte NUL. É contrato porque fixa o
  status de uma classe inteira de entradas e porque a **ordem** faz parte dele:
  roda **antes** de qualquer chamada de autorização (ADR 3.6.0002).

- **Conversor de `weekly_hours`** (`adapters/in/http/schemas.py` ou
  `router.py`) — texto → `Decimal`, traduzindo `decimal.InvalidOperation` para
  `InvalidWeeklyHoursError`. Espelha em forma o `DayPeriod.from_string`, e
  existe pela mesma razão: sem ele, `"abc"` levanta um `ArithmeticError` que
  nenhum handler alcança (ADR 3.6.0003 §Decision 2).

- **Declaração de requisito de acesso por rota** (`adapters/in/http/dependencies.py`) —
  o par (permissão exigida, alvo) de cada rota, como **valor** (`"manage_staff"`,
  `"manage_job_functions"`), nunca como enum importado de identity.

### Consumidos

- **Os 16 use cases de staff** — declarados na Stage 3.2, wired na 3.3.
- **`AccessGuard` / `AuthorizedScope` / L-AG1…L-AG4** — Stage 3.4. Alcançados por
  `dependency_overrides`; o router recebe o **port**, não a implementação.
- **`L-ORD`** — lei de ordem total dos dois ports (ADR 3.3.0003). Consumida, não
  estendida.
- **`register_error_handlers` genérico de `shared`** — rede de segurança.
- **O handler de `IdentityError`** — registrado sobre a app pela 2.4; é ele que
  responde 401 e 403 nas rotas de staff (§5.8).

### 4.1 Inventário de rotas

Prefixo `/api/v1`. **Não há rota pública em staff.** O inventário abaixo é o do
bloco 3.6 do `roadmap.md` — consumido, não re-derivado.

**Função de trabalho** — recurso **tenant-scoped** (`workforce.md` §3.2).
Permissão `manage_job_functions`; alvo: **tenant, sem unidade** (a permissão está
em `TENANT_WIDE_PERMISSIONS`, ADR 3.4.0008).

| # | Método | Rota | Use case | Sucesso |
|---|---|---|---|---|
| R01 | `POST` | `/job-functions` | `create_job_function` | 201 |
| R02 | `GET` | `/job-functions` | `list_job_functions` | 200 |
| R03 | `PATCH` | `/job-functions/{job_function_id}` | `rename_job_function` | 200 |
| R04 | `DELETE` | `/job-functions/{job_function_id}` | `delete_job_function` | 204 |

**Funcionário** — recurso **unit-scoped**; a unidade vem do **path** e é sempre
alvo de autorização. Permissão `manage_staff`; alvo: **tenant + unidade do path**.

| # | Método | Rota (sob `/units/{unit_id}/employees`) | Use case | Sucesso |
|---|---|---|---|---|
| R05 | `POST` | `` (raiz) | `create_employee` | 201 |
| R06 | `GET` | `?include_inactive=` | `list_employees` | 200 |
| R07 | `PATCH` | `/{employee_id}` | `rename_employee` | 200 |
| R08 | `PUT` | `/{employee_id}/job-functions` | `assign_job_functions` | 200 |
| R09 | `PUT` | `/{employee_id}/workload-profile` | `change_workload_profile` | 200 |
| R10 | `PUT` | `/{employee_id}/shift-preference` | `declare_shift_preference` | 200 |
| R11 | `POST` | `/{employee_id}/unavailabilities` | `register_unavailability` | 200 |
| R12 | `DELETE` | `/{employee_id}/unavailabilities?start=&end=` | `remove_unavailability` | 200 |
| R13 | `POST` | `/{employee_id}/termination` | `deactivate_employee` | 200 |
| R14 | `POST` | `/{employee_id}/rehire` | `reactivate_employee` | 200 |
| R15 | `DELETE` | `/{employee_id}` | `delete_employee` | 204 |
| R16 | `POST` | `/{employee_id}/copies` | `copy_employee_to_unit` | 201 |

> **A ausência do tenant no path é regra, não omissão** — cláusula (2) do
> ADR 0.0.0005, detalhada em §5.3: `staff` não é dona do restaurante como recurso,
> e nenhum ator de staff age fora do próprio tenant.

> **Os identificadores R01…R16 são o domínio enumerado** de todo critério de §11
> que fala de "todas as rotas". Existem para que uma lei universal não seja
> travada num representante (skill `stage-audit` §"Lei universal, representante
> estreito"). Subconjuntos usados adiante: **RJF** = R01…R04; **REMP** =
> R05…R16; **RID** = as rotas com identificador em path ou query (R03, R04,
> R05…R16 — todas menos R01 e R02).

Quatro escolhas de forma valem justificativa, e nenhuma é cosmética:

- **`PUT` para substituição, `POST` para acréscimo.** `assign_job_functions` é
  **substituição** do conjunto (`commands.py`: "não é acréscimo") e
  `declare_shift_preference` com `null` **limpa** — as duas são idempotentes e
  são `PUT`. `register_unavailability` acrescenta um item e é `POST`.
- **`DELETE` com query params para a indisponibilidade.** O período é removido
  **por igualdade de valor**, não por id — ele não tem identidade
  (`UnavailabilityPeriod` é value object). Query params expressam isso sem
  exigir corpo num `DELETE`.
- **`termination`/`rehire` como sub-recursos `POST`.** São as duas transições
  nomeadas do ciclo de vida (ADR 3.2.0006), não edições de campo. Um
  `PATCH {"active": false}` faria a transição parecer atribuição de atributo —
  exatamente a leitura que o ADR 3.2.0007 recusa.
- **R11 devolve 200, não 201.** O período não é recurso endereçável: não ganha
  URL própria, e um 201 sem `Location` prometeria uma que não existe. A resposta
  é o funcionário resultante, como em toda escrita (§5.12).

### 4.2 Inventário de schemas

**Requests** — nenhum tem `tenant_id`, e a ausência é a defesa: o tenant vem do
ator, nunca do corpo (ADR 2.4.0003 §4). Nenhum tem `unit_id` de corpo, exceto o
`target_unit_id` da cópia, que é escolha legítima do usuário e por isso é
**autorizado** (§5.6).

| Schema | Campos |
|---|---|
| `CreateJobFunctionRequest` | `name: str` |
| `RenameJobFunctionRequest` | `name: str` |
| `CreateEmployeeRequest` | `name: str`, `workload_profile: WorkloadProfilePayload`, `job_function_ids: list[str]`, `shift_preference: list[str] \| None = None` |
| `RenameEmployeeRequest` | `name: str` |
| `AssignJobFunctionsRequest` | `job_function_ids: list[str]` |
| `ChangeWorkloadProfileRequest` | `workload_profile: WorkloadProfilePayload` |
| `DeclareShiftPreferenceRequest` | `shift_preference: list[str] \| None` — **sem default** |
| `RegisterUnavailabilityRequest` | `start: datetime`, `end: datetime` |
| `CopyEmployeeRequest` | `target_unit_id: str` |

`WorkloadProfilePayload` é uma **união discriminada** por `type`:
`{"type": "fixed", "weekly_hours": "40.0"}` ou `{"type": "on_demand"}`.

**`DeclareShiftPreferenceRequest.shift_preference` não tem default**, espelhando
o command: ali `None` significa "**limpe** a preferência", não "não mexa". Com
default, um corpo `{}` limparia a preferência em silêncio.

**Responses:**

| Schema | Campos |
|---|---|
| `JobFunctionResponse` | `id`, `tenant_id`, `name` |
| `EmployeeResponse` | `id`, `tenant_id`, `unit_id`, `name`, `workload_profile`, `shift_preference: list[str] \| None`, `job_function_ids: list[str]`, `unavailabilities: list[UnavailabilityPayload]`, `active: bool` |

As propriedades de serialização e o porquê de cada uma estão no **ADR 3.6.0003**;
em resumo: os **dois** campos derivados de `frozenset` saem **ordenados**, cada
um com chave nomeada — `job_function_ids` pelo próprio id, `shift_preference` pela
**ordem de declaração do enum `DayPeriod`** (manhã, tarde, noite, madrugada), que
é a sequência que a língua ubíqua já carrega e que a ordem alfabética
embaralharia; `weekly_hours` viaja como **string** e é convertido por um
conversor de borda que traduz o erro de parsing; `start`/`end` viajam
**ingênuos** (sem offset); e o perfil de jornada viaja como **união
discriminada**.

### 4.3 O que **não** aparece em nenhum schema

- **Nenhum DTO de application é usado como schema**, e nenhum schema entra num
  use case (LAYOUT §7; skill `fastapi-thin-adapter`).
- **Nenhuma entidade de domínio na resposta** — `EmployeeResponse` é montado a
  partir de `EmployeeResult`, não de `Employee`. A propriedade é verificável como
  **ausência de import**: `router.py` e `schemas.py` de staff não importam nada
  de `staff.domain.entities` (CA05).
- **Nenhum campo de vínculo de login** (`user_id`) — hoje vacuamente verdadeiro;
  a Stage 3.5 acrescenta o campo, e a restrição fica declarada.
- **Nenhum campo derivado de `AuthorizedScope.unit_id`** — §5.4.

## 5. Invariantes e regras

**5.1 — Nenhuma rota de staff é pública.** Todas as 16 exigem Bearer válido, e a
autenticação acontece como **dependência** (`Depends`), não como chamada no corpo
da rota: o FastAPI resolve dependências antes de **validar o corpo contra o
schema**, então uma requisição sem credencial recebe 401 mesmo com corpo que não
casa o schema — caso contrário o 422 chegaria primeiro e um cliente sem
credencial passaria a sondar a forma do payload.

> **Limite medido, e declarado em vez de prometido.** A propriedade vale para
> corpo **JSON válido e fora do schema**. Para corpo **sintaticamente inválido**
> ela não vale: o FastAPI desserializa (`await request.json()`) **antes** de
> resolver dependências, então um `JSONDecodeError` vira `RequestValidationError`
> → 422 sem que o guard rode. Medido nesta Stage contra FastAPI real. O
> vazamento é nulo — a resposta só diz "o seu JSON não parseia", que o cliente já
> sabe —, mas a frase original prometia mais do que o framework entrega, e
> prometer a mais num invariante de acesso é como o próximo leitor conclui coisa
> errada.

**5.2 — A decisão de acesso não acontece em staff.** O adapter declara o
requisito (permissão + alvo) e delega ao port. Não há tabela de papéis, mapa de
permissões nem lógica de bypass em `features/staff/`, e nenhum módulo do BC
nomeia `Role` ou `Permission` de identity.

**5.3 — O `tenant_id` de todo command/query vem do escopo autorizado, nunca do
corpo nem do path — e a rota não o nomeia, porque não tem como e não deve.**

O tenant vem do **token**, e é resolvido no `composition_root`: o tradutor
preenche `tenant_id` a partir do ator autenticado quando o chamador não o nomeia.
`AuthorizedScope.tenant_id` continua sendo o único valor que o router lê, e nunca
é vazio (L-AG3). Consequência: **ação cross-tenant é inexprimível a partir de
staff** — não existe entrada pela qual um cliente nomeie outro restaurante.

A regra que decide isso não é local desta Stage — é o **ADR 0.0.0005**, global, em
três cláusulas: (1) o tenant que decide acesso sempre deriva do token, e um tenant
que chega na requisição é **declaração confirmada contra** ele, nunca a fonte;
(2) ele aparece no path **só quando** o BC **é dono do tenant como recurso
endereçável**, ou quando o ator pode agir fora do próprio tenant; (3) onde vem do
token, é resolvido numa **camada confiável única**, cujo lugar segue a **opacidade
do ator**.

É a cláusula (2) que explica a diferença entre os dois BCs, e ela é
**estrutural**: `identity` **é dona** de `Restaurant` — cria, endereça e aninha
unidades e owners sob ele —, enquanto `staff` **não pode** sê-lo, porque
`bc-independence` proíbe importar qualquer coisa de identity e o restaurante lhe
chega como string opaca. Não é preferência de estilo; é o contrato de
independência entre BCs. Por isso o inventário de §4.1 fica como está.

E é a cláusula (3) que explica por que a resolução mora em lugares diferentes: o
router de `identity` lê `ator.claims.tenant_id` direto, e está certo — o token é
dela e o ator não lhe é opaco; em `staff` o port declara `Actor = object`
justamente para que staff **não** leia atributo de ator, então o único lugar
possível é o `composition_root`.

**A checagem não é vácua.** O tenant viaja claim do token → guard → passo 3 de
`AuthorizeActionUseCase`, que o compara com o tenant do usuário **carregado do
banco**: um token cujo tenant não corresponde mais ao usuário gravado é negado.

**A lei vale para as duas implementações do port.** O fake resolve o tenant do
ator do mesmo modo, e a suíte parametriza sobre os dois casos — tenant nomeado e
tenant omitido — nos dois lados. Cobrar as duas implementações com conjuntos de
valores diferentes é o sinal de alerta mais forte da família "lei universal,
representante estreito", e foi exatamente assim que a Stage 3.4 vazou duas
mutações.

**5.4 — O `unit_id` de todo command é o da URL, já autorizado; o router não lê
`AuthorizedScope.unit_id`.**

**O mecanismo real, medido** (`authorize_action.py` › `AuthorizeActionUseCase.execute`
— `scope_unit_id=command.unit_id`; `composition_root.py`, o tradutor repassa):
o escopo devolvido **ecoa a unidade pedida**. Logo `unit_id is None` acontece
**exatamente quando o chamador omitiu a unidade** — e não por papel. Um `owner`
que declara a unidade A recebe `unit_id="A"` como qualquer outro papel; o bypass
do `owner` age no **passo 5** (visibilidade), não no valor devolvido.

> **Correção registrada.** A versão anterior desta regra dizia que um `owner`
> exercendo `manage_staff` **sobre a unidade A** voltava com `None`. É falso, e
> foi refutado por probe no Checkpoint A. O docstring do port está certo — ele
> qualifica *"**sem** declarar unidade"* —, e foi o concept que perdeu o
> qualificador ao resumi-lo. Fica escrito porque a regra continua valendo, mas
> **por outras três razões**, e uma justificativa falsa envelhece pior que
> nenhuma.

**As três razões pelas quais o router mesmo assim não lê o campo:**

1. **Nenhuma lei do port garante o eco.** L-AG1…L-AG4 falam de exceção crua,
   tenant não-vazio e uma autorização por alvo; **nenhuma** delas obriga
   `AuthorizedScope.unit_id` a ser igual ao `unit_id` pedido. Hoje as duas
   implementações ecoam — e é coincidência de implementação, não contrato. Ler o
   campo acopla o router a um comportamento que o port não promete e que uma
   terceira implementação pode não ter.
2. **Em R16 há dois escopos, e "o escopo" deixa de ser expressão bem-formada.**
   A cópia autoriza origem e destino (§5.6): qualquer código que fale de "o
   `unit_id` autorizado" ali está a uma linha de trocar um pelo outro.
3. **A inferência "None ⇒ tenant-wide" continua errada**, agora por um caminho
   diferente do que se supunha: `None` diz que **a chamada** não nomeou unidade,
   e não que a **ação** seja tenant-wide. Nas quatro rotas de catálogo as duas
   coisas coincidem; numa rota futura que esqueça de passar a unidade, não
   coincidem — e o erro é silencioso, porque nada falha, só o alcance fica maior
   que o da rota.

O endereço do registro é, portanto, sempre o do path, que o guard acabou de
autorizar. Ver ADR 3.6.0001, CA14 (estrutural) e CA15 (comportamental, com
dublê **adversarial** — ver a nota da §11 sobre por que o fake sancionado não
serve para este critério).

**5.5 — A construção de value object acontece no router, não no schema.** É o que
faz um período malformado levantar erro **de domínio** (`StaffError` → mapa de
status desta Stage) em vez de `RequestValidationError` do FastAPI, que segue
outro caminho e outro formato de corpo. A regra é herdada, literal, do docstring
do `router.py` de identity (Stage 2.4, mergeada).

**5.6 — A unidade destino da cópia é autorizada como alvo, exatamente como a de
origem.** R16 faz **duas** chamadas ao guard: uma com o `unit_id` do path
(origem) e outra com o `target_unit_id` do corpo (destino) — é L-AG4 aplicada,
não otimizada. Consequências, todas desejadas e **indistinguíveis entre si**:
destino de outro tenant ⇒ `TenantNotVisibleError` → 403 de corpo constante;
destino inexistente ⇒ `UnitNotFoundError`, convertido pelo guard de identity em
`UnitNotVisibleError` → 403; destino que o ator não enxerga ⇒ 403.

**5.7 — Cópia repetida para o mesmo destino continua sendo limite declarado.**
Homônimos são legítimos por decisão de domínio, então "já existe alguém com esse
nome no destino" **não é** sinal de cópia duplicada (ADR 3.4.0005).

**5.8 — O corpo das faixas 401 e 403 é constante**, herdado do handler de
identity, que está registrado sobre a **app** e é alcançado por MRO
independentemente de qual router levantou. O que sustenta a herança não é
coincidência: são L-AG1 e L-AG2, que proíbem o tradutor do `AccessGuard` de
traduzir a exceção. **Staff não registra entrada 401/403 no seu mapa.**

**5.9 — O mapa exceção → status de staff é total, e a totalidade é teste.** O
teste enumera recursivamente as subclasses concretas de `StaffError` (excluída a
raiz) e exige entrada **própria** para cada uma; e assere o **par classe→status**,
não apenas que a faixa foi alcançada (ADR 3.4.0002 §3 e §3b).

**5.10 — Nenhum caminho de rota devolve 500 por conteúdo de requisição** —
corpo, path ou query. Os dois erros de concorrência do Postgres (`40P01`
deadlock, `40001` serialization) continuam subindo crus, **e isso é declarado**:
são falhas transitórias de infraestrutura, e 500 é a resposta correta para elas.

**5.11 — A ordem das duas listagens é a do port** (`L-ORD`), e esta Stage não a
reordena nem a fatia. Sem `LIMIT`/`OFFSET`, a regex `_ORDER_BY` de
`test_staff_conduct.py` › `_ORDER_BY` continua correta (ADR 3.4.0004).

**5.12 — Toda resposta de escrita devolve o estado resultante**, exceto as duas
remoções definitivas (R04, R15), que devolvem 204. Com o endereço de unidade
fechado pela 3.4, essa devolução **não** é mais sonda de leitura do tenant: o
registro de outra unidade não é endereçável, e responde 404.

**5.13 — Matriz papel × staff, agora inteiramente ancorada** (ADR 3.4.0006 §1–§2,
ADR 3.4.0008, `role.py` — **não** `workforce.md` §4; ver a nota abaixo):

| Papel | Permissões de staff | Alcance |
|---|---|---|
| `owner` | `manage_staff`, `manage_job_functions` | tenant inteiro (bypassa memberships) |
| `manager` | `manage_staff`, `manage_job_functions` | unidades das quais é membro; catálogo, tenant inteiro |
| `hr` | idênticas às de `manager` | idêntico ao de `manager` — **`hr` ≡ `manager` dentro de staff** (ADR 3.4.0006 §1) |
| `employee` | nenhuma | **nada**: 403 nas 16 rotas |
| `platform_admin` | nenhuma | **nada**: 403 nas 16 rotas (detém só `manage_platform`) |

> A divergência hr × manager **existe**, e é de **família de operação**, não de
> alcance: RH mexe no cadastro, escala é do gerente e do dono. Ela se materializa
> no Step 4, sob a restrição para frente vinculante do ADR 3.4.0006 §3 — *a Stage
> 4.x não pode conceder a `hr` nenhuma permissão sobre a escala*. **Dentro desta
> Stage, `hr` e `manager` são indistinguíveis, e isso é a decisão, não uma
> omissão** — por isso CA12 exige que os dois papéis sejam exercitados nas mesmas
> rotas com o mesmo resultado.
>
> **Por que `workforce.md` §4 NÃO é âncora desta linha, e o que fazer com isso.**
> Aquela seção ainda diz *"é NO STAFF que hr diverge do manager — visibilidade e
> permissões de equipe são o único eixo de divergência"*, e registra a lacuna
> como endereçada *"ao concept da 3.4"*. O ADR 3.4.0006 **fechou** a lacuna em
> sentido oposto ao que a frase sugere (mesmas permissões, mesmo alcance; a
> divergência mudou de eixo), e `workforce.md` não foi reconciliado — `grep
> 3.4.0006 docs/domain/staff/workforce.md` não retorna nada, ao contrário do que
> a §3.2 do mesmo doc faz para o ADR 3.2.0005. Citá-lo como âncora seria afirmar
> conformidade que ele não dá. Fica como `[finding]` (§10); reconciliar doc de
> domínio ratificado não é escopo de uma Stage de borda HTTP.

**5.14 — Todo identificador vindo da requisição — path, query OU corpo — é
validado na borda antes de qualquer chamada de autorização**: vazio,
só-whitespace ou contendo o byte NUL ⇒ `InvalidIdentifierError` → 422.

**O corpo faz parte da regra, e a primeira versão desta Stage o esquecera.** Três
identificadores chegam pelo corpo — `CopyEmployeeRequest.target_unit_id` e os
`job_function_ids` de `CreateEmployeeRequest` e `AssignJobFunctionsRequest` — e os
três vão direto ao banco: o primeiro para `units.find_by_id` **dentro de
identity** (é o segundo alvo de autorização de R16, §5.6), os outros dois para
`find_all_by_ids` do repositório de funções, **antes** da construção da entidade.
`Employee.__post_init__` valida `id`, `tenant_id`, `unit_id`, `name` e a
não-vacuidade do conjunto — **nenhum elemento** de `job_function_ids`. Restringir
a validação a path/query deixaria `{"job_function_ids": ["\x00"]}` produzindo o
mesmo 500 que a Stage existe para fechar.

**A ordem é parte da regra**, e é esta: **autenticar → validar identificador →
autorizar**. Autenticar primeiro é §5.1; validar antes de autorizar é o que
impede um valor cru de alcançar `units.find_by_id`, porque `psycopg` recusa o NUL
**client-side** com `DataError` — que não é `IntegrityError` (o tradutor da 3.3
nunca é chamado), não é `StaffError` e não é `IdentityError` (nenhum handler o
alcança) — e vira 500. A correção de domínio da 3.4 não alcança este caminho,
porque identificador não passa por entidade nenhuma (`identifiers.py`: "este
módulo não tem lógica de runtime"). Ver ADR 3.6.0002.

> **O que a medição mostrou sobre os três valores rejeitados.** Só o **byte NUL**
> produz 500 hoje: `""` e `"   "` serializam normalmente, não casam nenhuma
> linha, e terminam em 404 (funcionário/função) ou 403 (unidade, via a conversão
> `UnitNotFoundError → UnitNotVisibleError`). Rejeitá-los na borda continua certo
> — identificador em branco é o balde de falso isolamento que
> `InvalidIdentifierError` nomeia, e uma consulta com chave sem sentido é ruído
> que esconde defeito de cliente —, mas o **motivo** é esse, e não "senão vira
> 500". A justificativa errada foi corrigida aqui e em §6.3.

**5.15 — `DayPeriod.from_string` é o único conversor de período do dia na
borda.** `DayPeriod("xpto")` levanta `ValueError`, que não é `StaffError` e vira
500; `from_string` levanta `InvalidDayPeriodError`, que é `StaffError` e está no
mapa (422). A regra vale para **todo** ponto de construção — hoje R05 e R10 — e é
verificável como ausência: nenhum módulo do adapter chama `DayPeriod(...)`
diretamente.

**5.16 — Pydantic vive só no boundary.** Nenhum schema atravessa para dentro de
um use case, nenhum DTO de application é usado como schema, e nenhuma entidade de
domínio aparece numa resposta (§4.3).

## 6. Casos de erro e exceções

### 6.1 Mapa de status — erros do BC staff

Um handler único registrado sobre `StaffError`, resolvendo o status pelo `__mro__`
(ADR 3.4.0002). São **18** entradas: as 18 subclasses concretas de hoje — **9** no
domínio e **9** na application; `StaffError` é a raiz, não entrada.

| Faixa | Exceções | Razão da faixa |
|---|---|---|
| **404** | `JobFunctionNotFoundError`, `EmployeeNotFoundError` | recurso endereçável ausente **no tenant do ator** (e, para funcionário, **na unidade do endereço**). São os dois que herdam de `NotFoundError`, nessa ordem de MRO, exatamente para isto |
| **409** | `JobFunctionNameAlreadyExistsError`, `JobFunctionAlreadyExistsError`, `EmployeeAlreadyExistsError`, `JobFunctionInUseError`, `EmployeeInUseError` | conflito com estado **já gravado**: ou a chave existe, ou uma referência existente impede a remoção |
| **422** | `InvalidNameError`, `InvalidIdentifierError`, `InvalidWeeklyHoursError`, `InvalidDayPeriodError`, `EmptyShiftPreferenceError`, `EmptyJobFunctionsError`, `InvalidUnavailabilityPeriodError`, `OverlappingUnavailabilityError`, `UnavailabilityNotFoundError`, `EmployeeRelocationError`, `SameUnitCopyError` | invariante violada **pelo conteúdo enviado** |

Cinco entradas exigem justificativa individual, porque em todas há leitura
alternativa plausível. **Quatro** são as que o ADR 3.4.0002 §4 nomeia como *"the
four classifications that had a plausible alternative"* —
`UnavailabilityNotFoundError`, `OverlappingUnavailabilityError`,
`SameUnitCopyError` e `EmployeeRelocationError` (esta última no parágrafo
seguinte). A quinta, o par `InUse` = 409, sai da **definição de faixa** do mesmo
§4 (*"the band is conflict with already-stored state"*), não da lista de quatro.
Todas são consumidas aqui, não re-decididas:

- **`UnavailabilityNotFoundError` é 422, não 404** — o período é um **valor
  dentro do agregado**, não um recurso endereçável; o funcionário existe e foi
  encontrado. A classe herda **só** de `StaffError` precisamente para que a MRO
  não a leve ao 404.
- **`OverlappingUnavailabilityError` é 422, não 409** — invariante do agregado
  violada pelo período **que o cliente enviou**, não colisão de chave gravada.
- **`JobFunctionInUseError` / `EmployeeInUseError` são 409, não 422** — o payload
  está correto; o que impede a operação é **outro registro**.
- **`SameUnitCopyError` é 422, não 409** — nada está em conflito: o cliente
  nomeou a origem como destino.

**`EmployeeInUseError` continua sem produtor em v1** (nasce com o Step 4) e mesmo
assim tem entrada própria — totalidade é sobre a hierarquia, não sobre o que é
alcançável hoje. **`EmployeeRelocationError` é inalcançável por HTTP nesta
Stage**, porque nenhuma rota permite enviar `unit_id` num `update`: tem entrada
por totalidade, e a inalcançabilidade fica registrada para que ninguém escreva um
e2e esperando produzi-la.

### 6.2 Erros que **não** chegam ao handler de staff

| Cenário | Exceção | Status | Quem responde |
|---|---|---|---|
| Sem header / esquema errado / token inválido ou expirado | `InvalidAccessTokenError` | 401 corpo constante + `WWW-Authenticate: Bearer` | handler de identity |
| Papel não concede a permissão | `PermissionDeniedError` | 403 corpo constante | handler de identity |
| Ator de tenant não declarou o tenant alvo | `TenantScopeRequiredError` | 403 | handler de identity — **inalcançável pelas rotas de staff** desde o ADR 0.0.0005: o tradutor sempre resolve o tenant. Fica na tabela porque continua sendo o comportamento do guard, e porque CA36 assere que nenhuma das 16 rotas o produz |
| Tenant alvo ≠ tenant do ator; unidade alvo de outro tenant | `TenantNotVisibleError` | 403 | handler de identity |
| Ator escopado sem unidade declarada, em permissão não tenant-wide | `UnitScopeRequiredError` | 403 | handler de identity |
| Unidade inexistente **ou** não visível | `UnitNotVisibleError` | 403 | guard converte, handler de identity |
| Ator sem tenant alcançando o tradutor | `PermissionDeniedError` (L-AG3) | 403 | handler de identity |
| Corpo malformado (tipo errado, campo faltando, JSON inválido) | `RequestValidationError` | 422 corpo constante | handler de `shared` |

**Consequência declarada:** um 403 de staff é indistinguível de um 403 de
identity, no status e no corpo. É a propriedade desejada, e é o que L-AG1/L-AG2
compram.

### 6.3 O que hoje viraria 500, e o que esta Stage faz com cada um

Todas as linhas abaixo foram **medidas** no Checkpoint A (probes contra
`psycopg`, `Decimal`, FastAPI/Starlette e a cadeia de autorização real), e duas
delas contradiziam a primeira versão desta tabela.

| Origem | Sem esta Stage | Nesta Stage |
|---|---|---|
| Nome com byte NUL no **corpo** | 500 (`psycopg.DataError`, recusa client-side) | já **rejeitado no domínio** pela 3.4 — `InvalidNameError` → 422; aqui só se prova que a borda o alcança e o classifica (CA22) |
| Byte NUL em **id de path, query ou corpo** (inclui `target_unit_id` e cada elemento de `job_function_ids`) | **500** — `DataError` não é `IntegrityError`, `StaffError` nem `IdentityError`; nenhum handler o alcança | **rejeitado na borda** — `InvalidIdentifierError` → 422 (§5.14, ADR 3.6.0002) |
| Id **vazio ou só-whitespace** em query ou corpo | **não é 500** — 404 (função/funcionário) ou 403 (unidade, pela conversão que fecha o oráculo) | rejeitado na borda por higiene declarada, não por risco de 500 (§5.14) |
| Id **vazio** em segmento de **path** | 404/405 do roteador — o segmento não casa a rota e o handler nunca roda | inalterado; declarado aqui para que ninguém escreva critério exigindo 422 (ver CA20) |
| Período do dia desconhecido (`DayPeriod("xpto")` → `ValueError`) | 500 | `DayPeriod.from_string` → `InvalidDayPeriodError` → 422 (§5.15) |
| Carga semanal **não-numérica** (`"abc"`, `""`, `"40,5"`) | **500** — `Decimal(...)` levanta `decimal.InvalidOperation`, que é `ArithmeticError`, **não** `StaffError` | conversor de borda traduz para `InvalidWeeklyHoursError` → 422 (ADR 3.6.0003 §Decision 2) |
| Carga semanal **não-finita** (`"NaN"`, `"Infinity"`) | já 422 — o `Decimal` constrói e `FixedSchedule.__post_init__` recusa | inalterado |
| Deadlock (`40P01`) / falha de serialização (`40001`) | 500 | **segue 500, declarado em §5.10** |

> **Um limite que a medição expôs e esta Stage NÃO fecha:** `Decimal("  40  ")`
> constrói `Decimal("40")` — o espaço é aparado em silêncio. Aparar é
> normalização silenciosa, que o ADR 2.3.0005 recusa; recusar é uma restrição a
> mais no contrato de entrada. A decisão fica com a Fase 3B, e o registro existe
> para que ela não passe despercebida.

## 7. Decisões técnicas relevantes

### D1 — O router endereça o registro pelo path e nunca lê `AuthorizedScope.unit_id`

- **O quê:** o `unit_id` de todo command vem do path (já autorizado); o
  `tenant_id` vem de `AuthorizedScope.tenant_id`; o campo
  `AuthorizedScope.unit_id` **não é lido por nenhuma rota**.
- **Por quê:** o escopo **ecoa** a unidade pedida
  (`authorize_action.py` › `AuthorizeActionUseCase.execute` — `scope_unit_id=command.unit_id`), então `None` diz
  apenas que **a chamada** omitiu a unidade — nunca que a **ação** é tenant-wide,
  e nunca por papel. Ler o campo (a) depende de um eco que **nenhuma lei do port
  promete**, (b) fica ambíguo em R16, onde há dois escopos, e (c) mantém viva a
  inferência "None ⇒ tenant-wide", correta hoje só por coincidência entre dois
  fatos independentes. Como o path já carrega a unidade e o guard já a autorizou,
  a informação existe sem inferência: a decisão elimina a pergunta em vez de a
  responder. Detalhe e a correção do mecanismo em §5.4.
- **Alternativa real descartada:** acrescentar ao `AuthorizedScope` a permissão
  exercida (ou um discriminador de tipo de escopo), que é o caminho que a §7 do
  `technical.md` da 3.4 nomeia como o caro — muda um port mergeado e obriga as
  **duas** implementações a acompanhar, para uma informação que o router já tem.
- **Fonte:** `access_guard.py` (docstring de `AuthorizedScope.unit_id`);
  `docs/stages/3.4-staff-access-scope/technical.md` §7, `[finding]` de 2026-08-18;
  `authorize_action.py` › `AuthorizeActionUseCase.execute` (`bypasses_unit_scope`); `user.py` › `_UNIT_SCOPE_BYPASS_ROLES`.
- **ADR:** [`../../adr/3_6_0001-path-addresses-the-record-not-the-authorized-scope.md`](../../adr/3_6_0001-path-addresses-the-record-not-the-authorized-scope.md)

### D2 — Identificadores de path, query e corpo são validados na borda, antes de autorizar

- **O quê:** um validador único do adapter rejeita id vazio, só-whitespace ou com
  byte NUL, levantando `InvalidIdentifierError` (422) **antes** de qualquer
  chamada de autorização ou ao use case. O domínio é **todo identificador da
  requisição**, incluindo os três que chegam pelo corpo (§5.14).
- **Por quê:** `EmployeeId`/`JobFunctionId`/`UnitId`/`TenantId` são `NewType`
  **sem validação de runtime**, por decisão explícita da 3.1. Um id de path nunca
  passa por entidade — vai direto para `find_by_id`. E o primeiro `find_by_id`
  que um `unit_id` de path encontra é o de **identity**, dentro do passo 5 de
  `AuthorizeActionUseCase`: por isso validar depois do guard não fecha nada.
- **Alternativa real descartada:** restringir o path param no Pydantic
  (`constr(min_length=1)` ou `Path(...)` com padrão). Produziria
  `RequestValidationError` → 422 com **outro corpo**, criando duas formas de 422
  na mesma API para a mesma classe de defeito, e contrariando a regra herdada de
  que a conversão de texto acontece no router para que a falha seja erro de
  domínio.
- **Fonte:** `staff/domain/value_objects/identifiers.py` (docstring);
  `authorize_action.py` passo 5; `router.py` de identity (docstring do módulo);
  issue #43 finding nº 2.
- **ADR:** [`../../adr/3_6_0002-boundary-identifier-validation.md`](../../adr/3_6_0002-boundary-identifier-validation.md)

### D3 — A representação no fio preserva as garantias do domínio

- **O quê:** união discriminada por `type` para o perfil de jornada;
  `weekly_hours` como **string**, convertida na borda com tradução do erro de
  parsing; `start`/`end` **ingênuos**; `job_function_ids` **e**
  `shift_preference` **ordenados** na saída (os **dois** campos derivados de
  `frozenset`, cada um com chave de ordenação nomeada).
- **Por quê:** são a mesma decisão aplicada várias vezes — o boundary não pode
  desfazer uma propriedade que o domínio ou a persistência garantem.
  Achatar a união em campos opcionais devolveria à borda o estado inválido que a
  união eliminou; serializar `Decimal` como número JSON entregaria o valor a um
  float e perderia a **escala** que a 3.3 provou sobreviver ao round-trip;
  anexar `Z` a um wall-clock o transformaria em outro instante (ADR 3.1.0005); e
  serializar um `frozenset` sem ordenar faria duas execuções produzirem corpos
  diferentes para o mesmo registro.
- **Fonte:** `workload_profile.py` (docstring do módulo); `unavailability_period.py`;
  `results.py` (*"a ordem não é do domínio"*); ADR 2.3.0005 (nada de normalização
  silenciosa); Stage 3.3 CA17.
- **ADR:** [`../../adr/3_6_0003-wire-representation-preserves-domain-guarantees.md`](../../adr/3_6_0003-wire-representation-preserves-domain-guarantees.md)

### D4 — Um handler único sobre `StaffError`, com mapa total resolvido por MRO

- **O quê:** replicar o desenho do `error_handlers.py` de identity para staff, no
  arquivo da feature, com totalidade **e** mapeamento par a par por teste.
- **Por quê:** decisão já tomada e ratificada; esta Stage a **executa**.
- **Fonte / ADR:** [`../../adr/3_4_0002-staff-http-error-status-mapping.md`](../../adr/3_4_0002-staff-http-error-status-mapping.md)
  (`accepted`, decidido na 3.4, executado aqui).

### D5 — `HttpWiring` passa a carregar coleções

- **O quê:** `router` → `routers`, `register_error_handlers` → coleção de
  registradores; `dependency_overrides` continua sendo um mapa único (as chaves
  são funções distintas por BC). `app.py` itera as coleções.
- **Por quê:** dois BCs registram superfície HTTP. Manter o campo singular
  obrigaria staff a pendurar o router dentro do de identity — o que faria uma
  feature conhecer a outra —, ou obrigaria `app.py` a conhecer features,
  quebrando a supressão estreita de `shared-independence` do `.importlinter`.
- **Nota:** a mudança é sobre o **router**. A propriedade de corpo constante
  401/403 **não** depende dela: o handler de identity é registrado sobre a app e
  alcançado por MRO (§3 Premissas).
- **Fonte:** `composition_root.py` (`HttpWiring`, `build_http_wiring`);
  `shared/infrastructure/http/app.py` (docstring do módulo); LAYOUT §6, §7.
- **Sem ADR, e a razão não é "não há alternativa".** Há três formas defensáveis —
  campos plurais (a escolhida), uma **lista de `HttpWiring`** (um por BC, com
  `build_http_wiring` devolvendo a coleção), e o router de staff pendurado no de
  identity. A terceira é estruturalmente proibida (faria uma feature conhecer a
  outra); as duas primeiras são equivalentes em consequência e **nenhuma
  atravessa a fronteira do composition root** — nem contrato de port, nem URL,
  nem comportamento observável. ADR existe para decisão cuja alternativa
  descartada alguém precisará entender depois; esta não é.

### D6 — Os ponteiros de CA dos ADRs pré-corte são reconciliados por errata, aqui

- **O quê:** varredura dos ADRs `3_4_0001`, `3_4_0002`, `3_4_0004` e `3_4_0005`
  atrás de ponteiros defasados pela renumeração do corte, e correção por seção
  `## Errata` — **sem** alterar nenhuma frase de `Decision`, `Alternatives` ou
  `Consequences`. Resultado da varredura:

  | ADR | Ponteiro | Situação | Disposição |
  |---|---|---|---|
  | 3.4.0001 | `## Trade-offs`: *"the per-role, per-route tests of concept CA10–CA12"* | os testes migraram para esta Stage; o intervalo é da numeração pré-corte | **errata** apontando para **CA09–CA12** deste concept (os quatro parametrizados sobre papel × rota) |
  | 3.4.0002 | `## Context`: *"17 concrete error classes … this Stage adds `InvalidDayPeriodError`, for 18"* | a 3.4 **já** acrescentou `InvalidDayPeriodError`; o domínio tem **9** concretas, não 8 | **errata** de contagem/atribuição; o total **18** e a decisão seguem inalterados |
  | 3.4.0004 | `## Consequences`: *"an acceptance criterion of this Stage (CA35)"* | "this Stage" virou a 3.6 no corte; `CA35` é da numeração pré-corte | **errata** apontando para **CA31** deste concept |
  | 3.4.0004 / 3.4.0005 | `## References`: *"no commit `d878060`, … §11 (CA32, CA35)"* / *"§5.6-5.7 e §11"* | **corretos** — estão ancorados no commit e no arquivo daquele commit | nenhuma; a âncora por commit é o que os salva |

- **Por quê:** é o quinto finding herdado, e a lição embutida nele é a regra de
  numeração declarada no aviso do topo: ponteiro para critério só é estável se a
  numeração for, ou se a citação carregar a âncora (commit + arquivo).
- **Fonte:** `docs/stages/3.4-staff-access-scope/technical.md` §7, `[finding]` de
  2026-08-18 (*"ponteiros de CA do ADR 3.4.0001 defasados"*); issue #43 finding nº 5.
- **Sem ADR:** errata é correção de ponteiro, não decisão.

### D7 — Não nasce leitura de funcionário por id, e o custo está declarado

- **O quê:** as 16 rotas do inventário e nenhuma a mais. Não há
  `GET /units/{unit_id}/employees/{employee_id}`.
- **Avaliação (o que a issue #43 pede):** a borda **não precisa dela** para o
  DoD. O que a tornaria necessária era a hipótese de que "ler um registro" fosse
  a única forma de escopar por unidade — e essa hipótese morreu na 3.4, quando a
  unidade entrou na assinatura do port: o escopo passou a ser resolvido pelo
  **endereço**, não por uma leitura prévia. Para o cliente, `GET` da unidade
  (R06) devolve a coleção completa (sem paginação, ADR 3.4.0004), então a leitura
  individual é derivável no cliente sem rota nova.
- **Custo declarado:** um cliente que só tem o `employee_id` precisa listar a
  unidade para achá-lo. É desconforto de UI, não de segurança, e vira `[finding]`
  (§10) em vez de rota inventada fora do inventário ratificado.
- **Fonte:** `roadmap.md` bloco 3.6 (`non_goals`: *"leitura de funcionario por
  id"*); ADR 3.4.0007; issue #43 finding nº 4.

### D9 — O tenant vem do token e é resolvido no `composition_root`

- **O quê:** o tradutor `_IdentityAccessGuard` preenche `tenant_id` a partir do
  ator autenticado quando a rota não o nomeia; o significado de `tenant_id=None`
  entra no docstring do port; o fake resolve igual, e a lei é cobrada nas duas
  implementações. **Nenhuma assinatura muda** — `access_guard.py` já declara
  `tenant_id: str | None = None`.
- **Por quê:** é a aplicação, nesta Stage, de uma regra que vale para o projeto
  inteiro — *o tenant aparece no caminho se e somente se é o recurso endereçado
  ou o ator pode agir fora do próprio tenant*. Sem ela, as 16 rotas eram
  inalcançáveis por todos os papéis (medição em §13).
- **Alternativas reais descartadas, com fonte:** entregar o tenant ao router pelo
  port (rejeitada por ASVS V4.1.1 — regra de acesso num único *trusted service
  layer* — e por mover a identidade de **resultado** da decisão para **insumo**
  dela); e pôr o tenant no path das 16 rotas (rejeitada por Hardy 1988 —
  designação sem autoridade não é capability — e por OWASP API1:2023, que trata
  path como entrada do cliente, logo somaria 16 rotas à superfície de BOLA sem
  ganho medível).
- **Decisão do sponsor**, 2026-08-18, após pesquisa de fontes primárias conduzida
  pela sessão mestra.
- **ADR:** [`../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md`](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
  — **global** (`bounded_context: transversal`), porque a regra governa também o
  `identity` já mergeado e todo BC futuro. Traz o **gatilho de reabertura** (se
  um usuário atravessar tenants, ou se `platform_admin` alcançar rotas de staff,
  o confused deputy passa a ser instanciável) e os **limites que não remove** (a
  checagem de unidade e de registro segue obrigatória em toda rota; a cópia, com
  dois alvos, é onde ela é mais frágil).

### D8 — Sem `gate_mode: batch`

O bloco 3.6 declara `gate_mode: strict`. Esta Stage escreve a superfície de
autorização de um BC inteiro — nada aqui é fundação já validada.

## 8. Integrações

### Internas

- **`features/identity`** — alcançada **só** pelo tradutor no composition root.
  Nenhum módulo de `features/staff/` a importa, e o contrato `bc-independence`
  continua sem `ignore_imports` (CA07).
- **`composition_root.py`** — carrega o router e o registrador de handlers de
  staff por `importlib` (o pacote `in` é keyword — LAYOUT §8) e acrescenta 17
  entradas ao mapa de overrides (16 use cases + `staff_access_guard`).
- **`shared/infrastructure/http/app.py`** — registra os dois routers e os dois
  registradores de handlers; continua sem conhecer feature nenhuma.

### Externas

Nenhuma. O único I/O é o Postgres já integrado pela 3.3, alcançado pelos use
cases e pelo `UnitRepository` de identity dentro do guard.

## 9. Modelo de dados

Não aplicável — esta Stage não cria nem altera tabela, coluna ou migration.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| A resolução do tenant no tradutor não valer para as **duas** implementações do port, deixando o fake e a produção cobertos por conjuntos diferentes | M | **A** | §5.3 + ADR 0.0.0005 §Decision; a lei é parametrizada sobre tenant nomeado × tenant omitido nos dois lados. É o sinal de alerta que vazou duas mutações na 3.4 |
| Alcance das 16 rotas regredir sem ninguém notar (era o estado medido antes do ADR 0.0.0005) | B | **A** | CA10 com ator `manager` real, nunca `owner`, sobre R01…R16; CA36 assere que nenhuma rota produz `TenantScopeRequiredError` |
| Ler `AuthorizedScope.unit_id` acopla o router a um eco que **nenhuma lei do port promete**, e em R16 (dois escopos) troca origem por destino | M | **A** | §5.4 + ADR 3.6.0001; CA14 (ausência de leitura, estrutural) e CA15 (comportamento, com dublê **adversarial** que devolve escopo divergente — o fake sancionado ecoa e não refutaria nada) |
| Um identificador escapar da validação numa rota nova **ou num campo de corpo** | **A** | M | CA20 parametrizado sobre RID (derivado do router) **e** sobre os campos de id dos schemas (derivados por introspecção), com os valores adversariais aplicáveis a cada eixo |
| A orientação origem→destino de R16 ser invertida no router sem que nada falhe | M | **A** | CA34 — cópia feliz A→B assere **em qual unidade** o clone caiu; sem ele, a inversão sobrevive a CA11, CA13, CA16 e CA25 |
| Mapa de status incompleto após erro novo em Stage futura | M | M | Totalidade + par classe→status por teste (§5.9, CA17 e CA18) |
| Lei universal travada num representante estreito (16 rotas × 5 papéis × 2 permissões multiplicam o risco) | **A** | M | Todo critério de §11 com quantificador nomeia o domínio enumerado (R01…R16, RJF, REMP, RID, os campos de id dos schemas, os 5 papéis, as 18 exceções) e é parametrizado sobre ele; CA33 exige a prova por mutação nas **quatro** leis mais críticas. Caso extremo tratado em separado: CA15, cujo domínio tem **um só valor observável** no sistema e exige dublê fabricado |
| 16 rotas + schemas + handlers + wiring + e2e estourarem a faixa de 3–12 Tasks | M | M | Agrupamento por recurso e por camada; com F1 fechada o recorte mede **11** (§12), dentro da faixa. A Fase 3B confirma antes de tudo |
| `weekly_hours` como string quebrar cliente que espera número | B | B | Declarado no contrato e no ADR 3.6.0003; não há cliente ainda (frontend é Step futuro) |

### `[finding]` a escalar

- **`[finding]` — paginação das listagens de staff**, junto com o antídoto de uma
  linha da regex `_ORDER_BY` (ADR 3.4.0004). **Stage candidata:** a primeira que
  precise de listagem paginada — candidata natural `4.x` ou uma Stage dedicada de
  API.
- **`[finding]` — leitura de funcionário por id** (§7 D7), no eixo de
  conveniência de cliente. **Stage candidata:** a primeira Stage de frontend do
  Step 3, que é quem terá o caso de uso em mãos.
- **`[finding]` — o byte NUL também escapa em identity.** `Restaurant`, `Unit` e
  `User` aceitam nome com `\x00`, e lá também viraria 500. **Stage candidata:**
  `6.x-hardening` ou a próxima Stage que toque `features/identity/domain`.
- **`[finding]` — cópia repetida sem sinal na borda** (ADR 3.4.0005) permanece
  aberto no eixo de **UX**. **Stage candidata:** a primeira Stage de frontend do
  Step 3.
- **`[finding]` — o tradutor do `AccessGuard` mora no composition root**
  (ADR 3.4.0001). Quando a 3.5 trouxer o `IdentityGateway`, reavaliar mover os
  dois para `features/staff/adapters/out/identity/`. **Stage candidata:**
  `3.5-employee-login-link`.
- **`[finding]` — dois resíduos em `identity` que o ADR 0.0.0005 nomeia e não
  corrige.** (a) O docstring de `create_unit` (`router.py` › `create_unit`) justifica o
  `restaurant_id` do path pelo seu **efeito de autorização**, que é o argumento
  **fraco** — e é o mesmo com que o ADR rejeita a Alternativa C em staff; o
  argumento que sustenta a rota é o outro (o path endereça sub-recurso de um
  recurso que identity possui, e a autorização vem de carona). (b) A resolução do
  tenant em `POST /users` e `POST /users/invitations` vive no router, o que a
  cláusula (3) cobre, mas que nenhum doc de identity declara. Direção sugerida:
  uma frase em cada docstring apontando o ADR. **Stage candidata:** a próxima que
  toque `features/identity/adapters/in/http`. Não é escopo de uma Stage cuja
  camada-alvo é `staff`.
- **`[finding]` — `workforce.md` §4 não foi reconciliado com o ADR 3.4.0006.** O
  doc de domínio ainda diz que *"é NO STAFF que hr diverge do manager"* e aponta
  a lacuna para *"o concept da 3.4"*, quando o ADR já a fechou com `hr` ≡
  `manager` **dentro** de staff e a divergência realocada para família de
  operação no Step 4. Direção sugerida: nota datada em `workforce.md` §4 no
  padrão que a §3.2 do mesmo doc já usa para o ADR 3.2.0005. **Stage candidata:**
  a primeira Stage do Step 4 que toque a matriz de acesso — que é quando a
  divergência vira comportamento e a frase passa a poder induzir a erro.
- **`[finding]` herdado da 3.4 e NÃO tratado aqui — `CONVENTIONS` §Idioma diverge
  da suíte de testes inteira.** A §7 do `technical.md` da 3.4 o registra e ele
  próprio conclui: *"não é escopo de Stage; vira issue de documentação"*.
  Registrado aqui para que a contagem de findings herdados feche, com a
  disposição explícita: **fora do escopo desta Stage**, vira issue.
- **`[finding]` — `Decimal("  40  ")` apara espaço em silêncio** (§6.3). Contraria
  o espírito do ADR 2.3.0005, e a decisão (recusar ou aceitar) pertence ao
  conversor de borda. **Stage candidata:** esta, na Fase 3B — registrado como
  finding só se a 3B decidir deixá-lo aberto.

## 11. Critérios de aceitação

> **Regra desta lista:** todo critério com quantificador ("todas", "nenhuma",
> "qualquer") **nomeia o domínio enumerado** e é travado por teste
> **parametrizado sobre ele** — não sobre um representante. Os domínios são
> R01…R16 (§4.1), os subconjuntos RJF/REMP/RID, **os campos de id dos schemas de
> request** (`target_unit_id` e cada elemento de `job_function_ids`), os cinco
> papéis de §5.13, as duas permissões e as 18 exceções de §6.1. Onde o domínio é
> derivável do código, o teste **deriva** (varre `router.routes`, enumera
> `StaffError.__subclasses__`, introspecciona `model_fields`) em vez de repetir
> uma lista escrita à mão, para que rota, campo ou erro novo entre na varredura
> sem ninguém lembrar.
>
> **E onde o domínio quantificado tem um só valor observável no sistema, o
> segundo é fabricado** — é o caso de CA15, cuja nota ao fim desta seção explica
> por que um dublê fiel ao comportamento real não refuta nada.

### Rotas e contrato

- [x] **CA01** — As 16 rotas de §4.1 existem sob `/api/v1`, com o método e o
      status de sucesso da tabela, e cada uma chama **exatamente um** use case.
      Teste parametrizado sobre R01…R16.
- [x] **CA02** — **Nenhum campo de request influencia o tenant efetivo.** Duas
      metades, porque a primeira sozinha é representante estreito: (a) o teste
      varre `model_fields` de **todos** os `*Request` do módulo (derivados por
      introspecção) e falha se aparecer `tenant_id` **ou qualquer alias plausível**
      — `restaurant_id`, `tenant`, `restaurant` —; (b) varredura do `router.py`
      provando que o `tenant_id` de **todo** command/query construído vem de
      `AuthorizedScope.tenant_id`, e de nenhuma outra origem. Sem (b), um campo
      `restaurant_id` no corpo consumido pelo router passaria pela lista negra.
- [x] **CA03** — `PUT /shift-preference` com `{"shift_preference": null}` limpa a
      preferência; corpo `{}` recebe 422 (campo obrigatório, sem default).
- [x] **CA04** — `weekly_hours` sobrevive ao round-trip HTTP em **valor e
      escala** (`"22.50"` volta `"22.50"`); `start`/`end` voltam sem offset e um
      envio com `Z` recebe 422 (`InvalidUnavailabilityPeriodError`), não é
      convertido em silêncio; e os **dois** campos derivados de `frozenset` —
      `job_function_ids` e `shift_preference` — saem na ordem declarada.
      **A asserção é `corpo[campo] == sorted(esperado, key=<a chave declarada>)`,
      não a igualdade entre duas execuções**: a iteração de `frozenset` é
      determinística **dentro de um processo** (o `PYTHONHASHSEED` é sorteado por
      processo), então "duas execuções produzem o mesmo corpo" é verdade com ou
      sem `sorted()` e não mata a mutação. Medido no Checkpoint A.
- [x] **CA05** — `router.py` e `schemas.py` de staff **não importam nenhum
      símbolo** de `staff.domain.entities`, e nenhum use case recebe um schema
      Pydantic. Verificado por varredura de **imports** (decidível), não de
      anotações.
- [x] **CA06** — O perfil de jornada é união discriminada no fio:
      `{"type":"on_demand","weekly_hours":"40"}` e `{"type":"fixed"}` recebem 422;
      os dois payloads válidos criam o VO correspondente.

### Acesso — o eixo de segurança

- [x] **CA07** — Nenhum módulo em `features/staff/` importa `features.identity`
      nem nomeia `Role`/`Permission`; `lint-imports` verde e o contrato
      `bc-independence` continua **sem nenhum `ignore_imports`** (o teste da 3.4
      que lê o `.importlinter` continua passando).
- [x] **CA08** — Toda rota de staff **sem** Bearer recebe 401 com corpo constante
      e header `WWW-Authenticate: Bearer`. Teste **enumera as rotas do router**
      (derivadas de `router.routes`), não uma amostra — R01…R16.
- [x] **CA09** — `employee` e `platform_admin` recebem **403** nas **16** rotas,
      com o corpo constante de identity. Teste parametrizado sobre o produto
      `{employee, platform_admin} × R01…R16` — 32 casos, não dois.
- [x] **CA10** — `manager` **alcança** as 16 rotas na sua própria unidade e no
      catálogo do seu tenant: teste parametrizado sobre R01…R16 com ator
      `manager` real, exigindo que **nenhuma** resposta seja 401/403. *(Era o
      critério que a F1 reprovava; com o ADR 0.0.0005 ele passa a ser o teste de
      não-regressão do alcance.)*
- [x] **CA11** — `owner` alcança as 16 rotas, inclusive as de unidade da qual
      **não é membro** (bypass por papel), e o efeito recai sobre a unidade do
      **path** — não sobre nenhuma outra. Parametrizado sobre REMP.
- [x] **CA12** — `hr` e `manager` produzem resultado **idêntico** em todas as 16
      rotas, sobre o mesmo estado: teste parametrizado sobre R01…R16 que assere a
      igualdade de status entre os dois papéis. *(Trava a decisão `hr ≡ manager`
      do ADR 3.4.0006 §1 como propriedade, não como comentário.)*
- [x] **CA13** — Isolamento entre unidades, nos **dois** endereços possíveis e
      com os **dois** status corretos — que são diferentes, e confundi-los faz
      metade da parametrização reprovar:
      - **404** quando o ator endereça pela **própria** unidade A o
        `employee_id` de um funcionário de B (`find_by_id(tenant, A, id)` não
        casa) — parametrizado sobre as rotas de REMP com `employee_id`;
      - **403** quando o ator endereça pela unidade **B**, da qual não é membro
        (o guard nega no eixo de visibilidade), e o mesmo 403 responde à unidade
        **inexistente** — indistinguíveis, por desenho.
- [x] **CA14** — **Nenhum handler de rota lê `AuthorizedScope.unit_id`.**
      Verificado estruturalmente (varredura por AST do módulo do router: nenhum
      acesso ao atributo `unit_id` sobre o objeto devolvido pelo guard). É
      **defesa em profundidade, não a trava**: `getattr(scope, "unit_id")`,
      `astuple(scope)` ou `asdict(scope)["unit_id"]` a contornam. A trava é CA15.
- [x] **CA15** — Para **toda** rota de REMP, a unidade que chega ao use case é a
      do **path**, e o teste usa um dublê **adversarial** do port — um que
      devolve `AuthorizedScope` com `unit_id` **diferente** do pedido (e outro
      com `None`). *(Ver a nota abaixo: o fake sancionado e o tradutor de
      produção **ecoam** a unidade pedida, então nenhum dos dois é capaz de
      refutar este critério.)*
- [x] **CA16** — R16 chama o guard **duas vezes**, com alvos distintos (unidade
      de origem e unidade destino), e as três recusas do destino — outro tenant,
      inexistente, não visível — produzem **o mesmo** status e **o mesmo** corpo,
      sem gravar nada. Inclui o caso "a **origem** não é visível", que mata a
      mutação "remover a primeira chamada".

### Erros

- [x] **CA17** — O mapa `STAFF_ERROR_STATUS` é **total**: o teste enumera
      recursivamente as subclasses concretas de `StaffError` (excluída a raiz) e
      exige entrada **própria** para cada uma. Classe nova sem entrada **reprova**.
- [x] **CA18** — O mapa é verificado **par a par** (classe → status), em teste
      parametrizado sobre as **18** entradas de §6.1. *(Trocar duas entradas
      dentro de faixas já exercitadas sobreviveria a um teste só de faixas.)*
- [x] **CA19** — Cada uma das três faixas de §6.1 é exercitada por ao menos um
      teste que chega pelo **HTTP real**, não por chamada direta ao handler; e
      `UnavailabilityNotFoundError` responde **422**, com teste que falha se
      alguém a fizer herdar de `NotFoundError`.
- [x] **CA20** — Identificador inválido recebe **422**, sobre o domínio enumerado
      por eixo — e os eixos têm **valores diferentes**, porque o roteador
      intercepta um deles:
      - **path** (rotas de RID, derivadas de `router.routes`): produto
        `RID × {"   ", "\x00"}`. Inclui `GET /units/%00/employees`, que sem esta
        Stage produz 500 dentro de identity. **`""` fica de fora deste eixo por
        medição:** um segmento vazio não casa `[^/]+`, e Starlette responde
        404/405 sem que o handler rode (§6.3). Exigi-lo aqui produziria célula
        vermelha irredutível — e critério de segurança que não fecha é critério
        que alguém relaxa.
      - **query**: produto `{parâmetros de query com id} × {"", "   ", "\x00"}`.
      - **corpo**: produto `{target_unit_id, cada elemento de job_function_ids}
        × {"", "   ", "\x00"}`, com os campos **derivados por introspecção** dos
        schemas (`*_id`/`*_ids`), não listados à mão — para que campo novo entre
        na varredura sem ninguém lembrar.
- [x] **CA21** — A validação de identificador roda **antes de autorizar**, e a
      prova é a **ausência de chamada**: com o dublê do port que registra
      chamadas (`InMemoryAccessGuard.calls`), uma requisição com identificador
      inválido não produz **nenhuma entrada `authorize(`** em `calls`. *(A
      asserção é sobre `authorize`, **não** `calls == []`: o fake registra também
      `authenticate`, que §5.1 exige que rode primeiro e que não toca
      identificador nenhum. Exigir `calls == []` obrigaria a validar antes de
      autenticar, e aí uma requisição sem Bearer com id inválido receberia 422 em
      vez de 401 — a sondagem que §5.1 existe para impedir.)*
- [x] **CA22** — Nome contendo `\x00` recebe **422** pelo HTTP real em **todas**
      as rotas que aceitam nome — R01, R03, R05 e R07 —, não só nas duas de
      criação. *(A rejeição já é do domínio desde a 3.4; aqui prova-se que a
      borda a alcança e a classifica em cada caminho que a produz.)*
- [x] **CA23** — Período do dia desconhecido recebe 422, não 500, em R05 e R10; e
      **nenhum** módulo do adapter chama `DayPeriod(...)` diretamente (varredura
      de AST — §5.15).
- [x] **CA24** — **Nenhum campo escalar de request devolve 500** para o conjunto
      adversarial da 3.3 (aspas, acento, emoji com ZWJ, `\n`, 1000 caracteres,
      `\x00`) mais os valores numéricos degenerados (`"abc"`, `""`, `"40,5"`,
      `"NaN"`, `"Infinity"`, `"-1"`, `"0"`). **O domínio é enumerado por
      introspecção**, não pela expressão vaga "rotas que aceitem texto livre":
      todos os campos escalares de todos os `*Request`, mais os parâmetros de
      query — o que inclui `weekly_hours`, por onde escapou o 500 do
      `decimal.InvalidOperation`, e os períodos de `shift_preference`. *(Era o
      único critério desta §11 sem domínio enumerado, e foi por essa fresta que o
      Checkpoint A entrou.)*

### Fluxo e isolamento (DoD do roadmap e da issue #43)

- [x] **CA25** — e2e feliz pelo entrypoint real, com ator **`manager`** (não
      `owner`): autentica, cria função customizada, cria funcionário com jornada
      fixa e preferência, registra indisponibilidade e lista a unidade — tudo
      pela API, contra Postgres real.
- [x] **CA26** — Funcionário criado na unidade A **não aparece** em
      `GET /units/B/employees`, mesmo para ator que enxerga as duas unidades.
- [x] **CA27** — Desligado some da listagem default e reaparece com
      `include_inactive=true`; a recontratação o devolve à listagem default.
- [x] **CA28** — A ordem da listagem é a de `L-ORD` e é estável entre execuções.
- [x] **CA29** — Acesso negado coberto pelo e2e real: um ator `employee`
      autenticado recebe 403 ao tentar criar função e ao tentar listar
      funcionários — pela API, não por unit test.

### Wiring e gates

- [x] **CA30** — `create_app()` registra **os dois** routers e **os dois**
      registradores de handlers; as rotas de identity continuam respondendo
      exatamente como antes (nenhuma regressão de path, status ou corpo), e o
      mapa de overrides tem as 17 entradas de staff.
- [x] **CA31** — Nenhuma suíte já mergeada regride: as suítes de contrato e a de
      conduta continuam verdes **sem alteração da regex `_ORDER_BY`**
      (consequência do ADR 3.4.0004). *(É o critério que o ADR 3.4.0004
      `## Consequences` cita — ver a errata de §7 D6.)*
- [x] **CA32** — `make check` verde (inclui `lint-imports`, `layout-check`,
      `docs-check`, mypy strict) e cobertura ≥ 90% em **cada** arquivo
      novo/tocado da Stage.
- [x] **CA33** — **Prova por mutação** das quatro leis mais críticas desta Stage,
      com a saída colada no relatório: (a) trocar o `unit_id` do path por
      `scope.unit_id` derruba CA15 — *e o critério só é verdadeiro com o dublê
      adversarial; com o fake sancionado a mutação sobrevive, porque ele ecoa*;
      (b) condicionar a validação de identificador a um único eixo (só path, ou
      só `employee_id`) derruba CA20; (c) trocar duas entradas do mapa dentro da
      mesma faixa derruba CA18; (d) inverter origem e destino em R16 derruba
      CA34. Mutação que não derruba nenhum teste é cobertura insuficiente
      **comprovada**, não estilo.
- [x] **CA34** — **A cópia cai na unidade certa.** Cópia bem-sucedida de A para B
      por ator que enxerga as duas: o clone aparece em `GET /units/B/employees`,
      **não** em A; o original permanece em A, inalterado; e o `id` do clone
      difere do original. *(Critério acrescentado no Checkpoint A: a inversão
      origem↔destino no router — `unit_id=<destino>`, `target_unit_id=<path>` —
      sobrevive a CA11, CA13, CA16 e CA25, porque nenhum deles exercita uma cópia
      que dá certo e olha **onde** ela caiu. O use case nomeia a inversão como
      reabertura da exfiltração que o ADR 3.4.0007 fecha.)*
- [x] **CA36** — **Nenhuma das 16 rotas produz `TenantScopeRequiredError`**, para
      **nenhum** dos papéis que detêm permissão de staff (`owner`, `manager`,
      `hr`): teste parametrizado sobre `{owner, manager, hr} × R01…R16` que falha
      se qualquer resposta trouxer o 403 daquele erro. **E a lei do tenant
      resolvido é cobrada nas duas implementações do port** — produção e fake —,
      parametrizada sobre tenant **nomeado** e tenant **omitido**, para que as
      duas não fiquem cobertas por conjuntos de valores diferentes.
      *(Critério acrescentado ao fim da lista com a decisão de F1, sem renumerar
      nenhum critério anterior — a disciplina que o aviso do topo declara.)*

> **Por que o número 35 é pulado.** `CA35` já aparece **neste arquivo**, na tabela
> de §7 D6, como o critério da numeração **pré-corte** que a errata do ADR 3.4.0004
> aposenta. Reusá-lo faria `grep -n "CA35" docs/stages/3.6-staff-http/concept.md`
> devolver dois referentes incompatíveis no mesmo documento — exatamente a classe
> de ambiguidade que esta Stage existe, em parte, para consertar. Número de
> critério é identidade: não recicla, nem quando o referente antigo mora só numa
> citação histórica.

> **Nota sobre CA21 — por que a asserção é sobre `authorize`, e não sobre o
> status.** A ordem "validar antes de autorizar" não é observável pelo status: um
> 422 na resposta é compatível tanto com "validou antes" quanto com "o guard
> rodou, passou, e a validação veio depois". O que a regra protege é o segundo
> caso — nenhum valor não validado pode alcançar `units.find_by_id` dentro de
> identity —, e a única forma de travá-lo é asserir o **efeito colateral
> ausente**. `authenticate` fica **fora** da asserção porque §5.1 exige que ele
> rode primeiro e porque ele não toca identificador nenhum.
>
> **Nota sobre CA15 — por que o fake sancionado não serve, e por que isso é a
> regra e não a exceção.** As duas implementações do port em produção e em teste
> (`_IdentityAccessGuard` e `InMemoryAccessGuard`) **ecoam** a unidade pedida no
> escopo devolvido, porque `AuthorizeActionUseCase` faz
> `scope_unit_id=command.unit_id`. Um teste escrito com qualquer uma delas é
> **incapaz** de distinguir "o router usou o path" de "o router usou o escopo" —
> os dois valores são o mesmo objeto. A lei de §5.4 fala de **independência**, e
> independência só se prova fazendo as duas fontes discordarem. Por isso CA15
> exige um dublê que **contradiz de propósito** as duas implementações, e o
> concept diz isso em vez de deixar o executor descobrir na hora: um dublê fiel
> aqui produziria cobertura de 100% sobre uma propriedade nunca exercida — a
> família "lei universal, representante estreito" na sua forma mais enganosa,
> porque aqui o domínio quantificado tem **um único valor observável** e é
> preciso fabricar o segundo.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — sim (§4:
      schemas, mapa de status, validador de identificador, declaração de
      requisito por rota).
- [x] Toda decisão em §7 tem fonte rastreável? — sim.
- [x] Toda integração externa tem contrato definido? — não há integração externa
      (§8).
- [x] Decisões com alternativa real descartada têm ADR escrito? — sim
      (3.6.0001–3.6.0003; as três de borda já decididas são 3.4.0002/0004/0005).
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — sim, a
      `3.4-staff-access-scope` está `done` e mergeada (PR #42).
- [x] Stage cabe em ~3–12 Tasks? — **sim, 11**, agora que F1 está fechada e o
      recorte é mensurável. Decomposição: (1) schemas + conversores de borda
      (`weekly_hours`, `DayPeriod`, perfil discriminado); (2) `error_handlers.py`
      — mapa total, `resolve_status`, `build_error_response`; (3)
      `dependencies.py` — validador de identificador, declaração de requisito por
      rota, provedor de ator; (4) **tenant resolvido no tradutor** — docstring do
      port, `_IdentityAccessGuard`, fake, lei nas duas implementações; (5) rotas
      de catálogo (RJF); (6) CRUD de funcionário (R05, R06, R07, R15); (7)
      perfil/preferência/indisponibilidade (R08–R12); (8) ciclo de vida + cópia
      (R13, R14, R16, com CA34); (9) wiring — `HttpWiring` em coleções,
      `composition_root` com 17 overrides, `app.py` com os dois routers e
      identity provada intacta; (10) e2e do DoD; (11) matriz papel × rota e
      acesso negado pela API real.
      **Duas consolidações contra a estimativa anterior de 12–13**, e as duas são
      substantivas, não contábeis: as provas de mutação e as varreduras por AST
      deixam de ser Task própria e viram **check** da Task que cria o módulo que
      elas varrem (é onde o PIPELINE as põe); e o wiring das duas peças —
      coleções e registro em `app.py` — é **uma** mudança lógica com dois checks,
      não duas. A resolução do tenant (4) é Task porque toca outra camada
      (composition root + port + fake) e precisa aterrissar **antes** de qualquer
      rota funcionar. Margem de 1 até o teto saudável e de 3 até o alarme de
      `≥ 14` de CONVENTIONS §6; se a Fase 3B medir acima de 12, o sinal é
      subdividir o inventário de rotas — não cortar de novo, porque esta Stage
      **já é** o produto de um corte.
- [x] Riscos críticos têm mitigação plausível? — sim, **todos**: com a F1 fechada
      pelo ADR 0.0.0005, não sobrou risco sem mitigação na tabela de §10.
- [x] Os cinco findings herdados da issue #43 estão tratados? — sim: nº 1 em
      §5.4/D1, nº 2 em §5.14/D2, nº 3 em §5.15, nº 4 em D7, nº 5 em D6. **O
      quarto `[finding]` da §7 da 3.4** (CONVENTIONS §Idioma × a suíte de testes)
      não está entre os cinco da issue e não é escopo desta Stage; a disposição
      está declarada em §10.
- [x] **As 16 rotas são alcançáveis pelos papéis do DoD?** — **sim**, desde o
      ADR 0.0.0005; travado por CA10 e CA36.
- [x] Todo critério com quantificador nomeia o domínio enumerado? — sim (nota no
      topo da §11).

## 13. Questões em aberto

> **Nenhuma em aberto.** A única bifurcação material desta Stage — F1 — foi
> decidida pelo sponsor em **2026-08-18**. A seção fica como registro: o problema
> medido, a decisão, e as duas correções que a pesquisa de fontes fez no
> enunciado original. Apagá-la esconderia que o inventário de rotas **é uma
> decisão sustentada**, e não uma omissão que passou.

### F1 — De onde o router de staff tira o tenant alvo que a autorização exige? — **DECIDIDA**

**A medição que abriu a bifurcação.** `AuthorizeActionUseCase` tem um passo 3
(`_assert_tenant_scope`) que **nega qualquer ator de tenant que não declare o
tenant alvo**: `if command.tenant_id is None: raise TenantScopeRequiredError`.
Probe rodado na Fase 3A, com `manager` real e as duas permissões de staff:

```
manage_staff          RAISED TenantScopeRequiredError  ação de papel 'manager' exige declarar o tenant alvo
manage_job_functions  RAISED TenantScopeRequiredError  ação de papel 'manager' exige declarar o tenant alvo
```

O inventário ratificado no `roadmap.md` não tem tenant em nenhuma URL, o ator é
**opaco** por decisão do port (`Actor = object`), e o tenant só aparece **depois**,
no `AuthorizedScope`. Com o código de então, **as 16 rotas devolviam 403 para
todos os papéis** e o DoD era inalcançável.

**A decisão (sponsor, 2026-08-18):** opção **A** — o tradutor no
`composition_root` preenche o `tenant_id` a partir do ator autenticado quando a
rota não o nomeia. **Sem mudança de assinatura**: `access_guard.py` › `AccessGuard.authorize` já declara
`tenant_id: str | None = None`. O inventário de rotas **permanece sem tenant no
path**, agora por regra e não por omissão. Registrada no **ADR 0.0.0005**
(global, `bounded_context: transversal`), com as três alternativas, os
trade-offs ancorados em seis fontes primárias, o gatilho de reabertura e os
limites que a decisão **não** remove. Aplicação nesta Stage: §5.3, §7 D9, CA10 e
CA36.

**As duas correções que a pesquisa fez no enunciado desta seção** — registradas
porque um fork bem decidido a partir de premissa errada continua sendo sorte:

- **"Significado permissivo" estava invertido.** A primeira redação objetava que
  resolver o tenant no tradutor seria dar sentido **permissivo** a um parâmetro de
  acesso ausente — o padrão que já mordeu este projeto duas vezes. É o **oposto**:
  fazer `tenant_id=None` significar "o tenant do próprio ator" torna a ação
  cross-tenant **inexprimível** a partir de staff, a leitura mais restritiva das
  três. A objeção que resta é menor: muda a semântica documentada de um port
  fechado — e por isso ela vai para o docstring do port, não para o costume.
- **A intuição de que o path seria "mais seguro" não tem fonte, e a literatura
  aponta ao contrário.** Hardy (1988) prescreve que designação e autoridade viajem
  **juntas**; um `restaurant_id` no path é designação **sem** autoridade, e cria a
  obrigação de checagem que ele critica. OWASP API1:2023 trata path como entrada
  do cliente igual a corpo e query, então pôr o tenant lá **somaria** 16 rotas à
  superfície de BOLA. E o argumento de "consistência com `identity`" é fraco
  porque a diferença entre os dois BCs é **principiada**: lá o `platform_admin`
  age fora de qualquer tenant e o restaurante *é* o recurso.

## 14. Referências

- [`../../overview.md`](../../overview.md) §3, §6, §9
- [`../../roadmap.md`](../../roadmap.md) — bloco Stage 3.6 (inventário de rotas,
  insumos decididos) e a nota datada do corte no bloco 3.4
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) — §3.1,
  §3.2, §3.6, §3.7, §4
- [`../3.4-staff-access-scope/concept.md`](../3.4-staff-access-scope/concept.md)
  §4, §5, §13 (fronteira com esta Stage) e
  [`technical.md`](../3.4-staff-access-scope/technical.md) §7 (os quatro
  `[finding]` herdados)
- [`../3.2-staff-application/concept.md`](../3.2-staff-application/concept.md)
  §4, §5, §6, §10
- [`../3.3-staff-persistence/technical.md`](../3.3-staff-persistence/technical.md)
  §7 (regex `_ORDER_BY`, tradução de integridade por operação)
- [`../2.4-identity-http/concept.md`](../2.4-identity-http/concept.md) e
  [`technical.md`](../2.4-identity-http/technical.md) — a Stage irmã, cujo
  desenho esta replica
- **Rascunho pré-corte**, consumido criticamente: commit `d878060`,
  `docs/stages/3.4-staff-http/concept.md` §4.1–4.3, §6 e §11
- ADRs desta Stage: 3.6.0001, 3.6.0002, 3.6.0003
- **ADR global decidido nesta Stage: 0.0.0005** — o tenant vem do token, salvo
  quando é o recurso ou o ator age fora do próprio tenant (regra transversal;
  governa `identity` e todo BC futuro)
- ADRs de borda decididos na 3.4 e **executados aqui**: 3.4.0002, 3.4.0004,
  3.4.0005
- ADRs consumidos: 2.1.0001, 2.2.0002, 2.3.0001, 2.3.0003, 2.3.0005, 2.4.0001,
  **2.4.0003**, 3.1.0004, 3.1.0005, 3.1.0006, 3.2.0002, 3.2.0003, 3.2.0006,
  3.2.0007, 3.3.0003, 3.3.0006, 3.4.0001, 3.4.0003, 3.4.0006, 3.4.0007,
  **3.4.0008**
- **Issue #43** (esta Stage); decisão do sponsor sobre a F1 em 2026-08-18
- Fontes primárias de segurança/multi-tenancy: `## References` do ADR 0.0.0005;
  ponteiro em [`../../overview.md`](../../overview.md) §10
- Skills: `fastapi-thin-adapter`, `composition-root`, `hex-arch-python`,
  `stage-audit` (§"Lei universal, representante estreito")

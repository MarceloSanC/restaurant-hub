---
title: Concept — API de equipe
description: Definição do que será feito nesta Stage e por quê, com decisões técnicas relevantes
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, staff-http, fastapi, router, schemas, rbac, depends, e2e, error-handlers, guard, copia, paginacao]
status: draft
created_at: 2026-08-12
updated_at: 2026-08-12
stage_id: 3.4-staff-http
stage_title: API de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [3.3-staff-persistence]
---

# Concept — Stage 3.4 — API de equipe

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task) e critérios de atomicidade, ver
> [`PIPELINE.md`](../../PIPELINE.md) §4.
>
> **Status (apenas dois estados).** `draft` desde a criação; `done` após
> o gate humano. Regressão `done → draft` é **permitida** quando a
> Fase 3B (Technical) revela gap material aqui — neste caso, commit
> `chore(concept): revert to draft — revision-from-technical: <motivo>`.
> O Passo 8 do runbook (início da Fase 4) exige `concept.status == done`
> **e** `technical.status == done` simultaneamente.

> **⚠ Este concept está `draft` com TRÊS bifurcações materiais abertas
> (§13 — F1, F2, F3).** Todas afetam **contrato** e **segurança**, e todas
> convergem no mesmo ponto: **o vocabulário de permissões de staff vive no
> domínio de identity**, e mexer nele é expansão de camada-alvo para um
> segundo bounded context. O detalhe de cada bifurcação vai na **mensagem de
> handoff** à sessão mestra, no formato rico — não neste arquivo, que só as
> nomeia e ancora. As seções abaixo estão escritas até a fronteira do que as
> fontes sustentam; o que depende das bifurcações está **nomeado como
> dependente**, nunca preenchido por chute.

## 1. Escopo

### Dentro do escopo

- **Adapter de entrada HTTP do BC staff** — `features/staff/adapters/in/http/`
  com `router.py`, `schemas.py`, `dependencies.py` e `error_handlers.py`, no
  mesmo desenho da 2.4 (adapter fino; Pydantic só no boundary; um handler
  por raiz de BC).
- **16 rotas para os 16 use cases** já wired na 3.3 (§4.1) — quatro de função
  de trabalho e doze de funcionário.
- **Enforcement de RBAC por `Depends`, nunca middleware** (ADR 2.4.0003):
  cada rota declara a permissão exigida e o alvo (tenant/unidade) e delega a
  decisão ao `AuthorizeActionUseCase` de identity.
- **Port `AccessGuard` próprio do BC staff** e o seu adapter **montado no
  composition root**, para que staff alcance a autorização de identity **sem
  nenhum import entre features e sem nenhuma supressão** no `.importlinter`
  (§7 D1, ADR 3.4.0001).
- **Mapa exceção → status HTTP do BC staff**, total e testado por par
  classe→status, honrando `UnavailabilityNotFoundError` = 422 (§6, ADR 3.4.0002).
- **Validação da unidade destino da cópia** contra o tenant do ator — o
  finding nº 1 herdado da 3.2 (§5.6, §7 D3).
- **Validação de identificador na borda** — todo `id` de path/query é rejeitado
  quando vazio ou contendo o byte NUL, antes de qualquer consulta (§5.14, §7 D10).
- **Wiring**: os 16 use cases e o guard passam a ter consumidor;
  `HttpWiring` deixa de assumir um único router/registrador de handlers.
- **Testes e2e** (`tests/e2e/features/staff/`) contra app real + Postgres real,
  cobrindo o fluxo feliz do DoD, o acesso negado e as faixas de status.
- **Expansão declarada de camada-alvo para o domínio da 3.1** (§7 D4/D5,
  ADR 3.4.0003): rejeição do byte NUL em nome e `DayPeriod.from_string`. As
  duas existem porque **a borda não tem como produzir o erro certo sem elas** —
  hoje virariam 500.
- **Expansão de camada-alvo para o domínio de `identity`** — **dependente das
  três bifurcações** (§13). Nenhuma delas é resolvível sem tocar
  `features/identity/domain/value_objects/{role,permission}.py`, e a
  assimetria com D4 (que recusa tocar identity pelo byte NUL) está tratada em
  §13.

### Fora do escopo (explicitamente)

- **Paginação** das duas listagens (§7 D6, ADR 3.4.0004) — escalada com Stage
  candidata.
- **Guarda de duplicidade na cópia** para o mesmo destino (§5.7, §7 D7,
  ADR 3.4.0005) — segue limite declarado.
- **Vínculo de login do funcionário** (`user_id`, `IdentityGateway`) — Stage 3.5.
- **Qualquer noção de escala, demanda, alocação** — Step 4.
- **Frontend** e qualquer decisão de UX (confirmação de cópia, seletor de
  unidade).
- **Controle otimista de concorrência** — escalado pela 3.3 (ADR 3.3.0006),
  segue aberto; "última escrita vence" continua sendo o comportamento.
- **Correção do byte NUL em identity** (`Restaurant`/`Unit`/`User`) — outro BC;
  `[finding]` em §10.
- **Rota de seed de `platform_admin`** e qualquer ação de plataforma — o BC
  staff não tem ação de plataforma.

### Reconciliação do bloco 3.4 do roadmap

O bloco `3.4-staff-http` do `roadmap.md` fica desatualizado em **cinco** eixos.
Todos entram na nota datada do bloco, no fechamento da Stage, no mesmo padrão
das notas da 2.3, 2.4, 3.2 e 3.3:

1. **`contratos_introduzidos: []` não se sustenta** — a Stage introduz o port
   `AccessGuard`, o DTO `AuthorizedScope`, os schemas do boundary e o mapa
   `STAFF_ERROR_STATUS` (§4).
2. **`non_goals: []` não se sustenta** — são oito (§1).
3. **`arquivos_a_criar` incompleto** — faltam `dependencies.py`,
   `error_handlers.py` e `application/ports/out/access_guard.py`.
4. **`camada_alvo: adapters/in/http` expandida** — para
   `application/ports/out` (o port), para `domain` da 3.1 (D4/D5) e,
   **dependendo de F1/F2/F3**, para `features/identity/domain`.
5. **`complexidade_estimada: S` está errado** — a Stage é **M**.

E **duas** afirmações de outras fontes ficam falsas com esta Stage, e a mesma
nota datada as corrige:

- `roadmap.md` §Stage 3.3: *"contrato consumido pela 3.4, **cuja paginação usa
  `(name, id)` como cursor**"* — a 3.4 não pagina (D6). O cursor fica
  **preparado**, não consumido.
- `3.3-staff-persistence/technical.md` §7 (2026-08-12): *"a paginação da 3.4
  acrescenta `LIMIT`/`OFFSET`"* — idem; o antídoto da regex segue escalado com
  a paginação, não aplicado aqui.

### Vínculo com o roadmap

Esta Stage fecha o **Step 3 — Equipe da unidade** do lado da superfície: as
Stages 3.1 (domínio), 3.2 (use cases) e 3.3 (persistência) entregaram um BC
completo que **nada no boot da aplicação alcança** — o próprio
`composition_root.py` declara que os 16 campos de staff "nascem sem consumidor"
e que o consumidor é a 3.4. É esta Stage que torna o Step 3 exercitável pelo
entrypoint real, que é o critério do DoD (`roadmap.md` §Stage 3.4).

## 2. Objetivo da Stage

Ao final desta Stage, os 16 use cases de equipe são alcançáveis por HTTP sob
enforcement de acesso composto no boundary, de modo que um gerente autenticado
cadastra função e funcionário pela API real e um ator sem permissão recebe 403
sem que nenhum caminho devolva 500.

## 3. Contexto e premissas

### Contexto

**O BC staff é surdo-mudo hoje.** Domínio, use cases e persistência existem e
estão testados; `wire_dependencies()` monta os 16 use cases sobre os
repositórios Postgres. Falta o adapter de entrada — e com ele três coisas que
só a borda pode fazer:

1. **Origem do escopo.** Todo command/query de staff carrega `tenant_id`
   (ADR 3.2.0002), e nenhuma camada de staff sabe de onde ele vem. Vem do
   **ator autorizado**, e é a borda que o extrai.
2. **Coerência unidade ↔ tenant.** A entidade `Employee` declara literalmente
   que "a consistência `unit_id` ↔ `tenant_id` é **premissa da borda**"
   (`employee.py`, docstring). `Unit` é agregado de identity e staff não o
   importa (`bc-independence`) — logo a única forma de honrar a premissa é
   perguntar a identity.
3. **Construção dos value objects.** Os commands chegam com `WorkloadProfile`,
   `ShiftPreference` e `UnavailabilityPeriod` **já construídos**; a 3.2 §6
   declarou explicitamente que os erros de construção "não são alcançáveis por
   nenhum caminho de use case" e que existem "para que a 3.4 saiba que precisa
   mapeá-los".

**O escopo de unidade foi explicitamente alocado a esta Stage.** ADR 3.2.0002
§Neutral: *"Restricting a manager to their own units is an **authorization**
decision, and it belongs to Stage 3.4 with `authorize_action` — collapsing it
into the repository would duplicate the RBAC rule in two places that can
diverge."* Isto **não é** bifurcação: é requisito ancorado. O que é bifurcação
é o **mecanismo**, porque nenhum dos mecanismos possíveis cabe dentro desta
Stage sem emendar Stage fechada (F2).

**A Stage irmã é a 2.4.** O BC identity resolveu os mesmos quatro problemas e o
código está no repo. Esta Stage **replica o desenho**, não o reinventa — e onde
diverge, diverge por razão nomeada (§7).

**A ordem de herança dos erros de staff foi desenhada para esta Stage.** O
`application/errors.py` de staff diz, no docstring: "o pior caso não-ajustado é
422; a Stage 3.4 refina para 404/409 registrando handlers, **sem tocar nesta
camada**". A MRO `… → StaffError → NotFoundError → DomainError` é o que faz o
handler daqui ganhar dos genéricos de `shared` (ADR 2.4.0001, mesma mecânica).

### Premissas

- **Os handlers genéricos de `shared` continuam registrados** e continuam sendo
  rede de segurança, não caminho principal.
- **O handler de identity é registrado sobre a app inteira**, não sobre um
  router — `@app.exception_handler(IdentityError)` — e Starlette resolve por
  `type(exc).__mro__`. Logo um `IdentityError` levantado dentro de uma rota de
  **staff** já sai com o corpo constante de identity, sem nada novo. Verificado
  em `identity/adapters/in/http/error_handlers.py:171-176`.
- **Não há `Unit` nem `UnitMembership` em staff, e não haverá.**
- **`create_engine` não abre conexão**, então registrar o router de staff não
  muda o comportamento de boot.
- **A cadeia de setup do e2e é alcançável só por rotas reais**:
  `platform_admin` semeado → `POST /restaurants` → `POST /restaurants/{id}/owners`
  → `POST /restaurants/{id}/units` → `POST /users` com `unit_ids` (que **cria a
  `UnitMembership`**). Nenhuma rota falta.
- **Postgres real é exigido pelos testes de integração/e2e** (ADR 2.3.0001), e
  `truncar_tudo` já limpa as tabelas de staff.

### Dependências

- `3.3-staff-persistence`: os dois repositórios Postgres, o wiring dos 16 use
  cases e a lei `L-ORD` (ADR 3.3.0003), que torna a resposta das duas rotas
  `GET` determinística sem esta Stage ordenar nada.
- `3.2-staff-application`: os 16 use cases, os DTOs, a hierarquia de erros com a
  MRO desenhada para o handler daqui, e os quatro `[finding]` escalados.
- `3.1-staff-domain`: as entidades e os value objects que a borda constrói.
- `2.4-identity-http`: `IdentityGuard`, `error_handlers.py`, `HttpWiring` e o
  padrão de `dependency_overrides`.
- `2.2-identity-application`: `AuthorizeActionUseCase` e os dois eixos
  fail-closed (ADR 2.2.0002).

## 4. Contratos

### Introduzidos

- **`AccessGuard`** (`port-out` do BC staff —
  `features/staff/application/ports/out/access_guard.py`)

  ```python
  Actor = object  # credencial já verificada; staff não a interpreta

  @dataclass(frozen=True)
  class AuthorizedScope:
      tenant_id: TenantId          # nunca None — ver a lei L-AG3
      unit_id: UnitId | None

  class AccessGuard(Protocol):
      def authenticate(self, request: object) -> Actor: ...
      def authorize(
          self,
          actor: Actor,
          permission: str,
          *,
          tenant_id: str | None = None,
          unit_id: str | None = None,
      ) -> AuthorizedScope: ...
  ```

  `AuthorizedScope` vive no mesmo módulo do port. **Identificadores atravessam
  a fronteira entre BCs como strings opacas** — regra literal do
  `identifiers.py` de staff e do contrato `bc-independence`.

  **Leis do port** (valem para o adapter real e para qualquer fake; sem elas
  uma segunda implementação satisfaz o tipo e destrói as propriedades de
  segurança sem reprovar nada):

  - **L-AG1 —** `authenticate` levanta quando não há credencial válida, e a
    exceção levantada **sai crua** pelo port: o adapter de staff **não** a
    traduz. É o que faz a faixa 401 de staff ser byte-idêntica à de identity.
  - **L-AG2 —** `authorize` levanta quando o ator não pode agir sobre o alvo, e
    a exceção **sai crua** pela mesma razão (faixa 403 de corpo constante).
  - **L-AG3 —** `authorize` **nunca** devolve `AuthorizedScope` com
    `tenant_id` vazio ou ausente. Um ator sem tenant (hoje só
    `platform_admin`) é **negado**, não coagido para `""` — identificador vazio
    é o balde de falso isolamento que `InvalidIdentifierError` nomeia.
  - **L-AG4 —** `authorize` é chamado **uma vez por alvo**; autorizar um alvo
    não autoriza outro (mesma regra do `authorize_all` de identity).

  > **O nome da permissão é `str` no port, e isso é deliberado.** O
  > vocabulário fechado de permissões vive em identity; staff nomeia o
  > requisito e não conhece o mapa papel→permissão. Qual é o conjunto exato de
  > nomes **depende de F1** (§13).

- **`AuthorizedScope`** (`dto` de staff) — ver acima.

- **Schemas Pydantic de request/response** (`adapters/in/http/schemas.py`) —
  boundary only. Inventário em §4.2.

- **Mapa `STAFF_ERROR_STATUS`** (`adapters/in/http/error_handlers.py`) —
  `dict[type[StaffError], int]` total, com resolução por `__mro__` e totalidade
  garantida por teste (§6, ADR 3.4.0002).

### Modificados

**Extensões aditivas** (nada que era válido deixa de ser):

- **`HttpWiring`** (`composition_root.py`) — hoje carrega **um** router e **um**
  registrador de handlers; passa a carregar **coleções** (§7 D8).
- **`DayPeriod`** — ganha `from_string` e o erro novo
  `InvalidDayPeriodError(StaffError)` (§7 D5).

**Restrição de contrato** (valor antes aceito passa a ser recusado — declarado
como tal, não maquiado de aditivo):

- **`Employee.name` / `JobFunction.name`** — passam a rejeitar nome contendo o
  byte NUL (§7 D4, ADR 3.4.0003).

### Consumidos

- **Os 16 use cases de staff** — declarados na Stage `3.2-staff-application`,
  wired na `3.3-staff-persistence`.
- **`IdentityGuard`** — declarado na Stage `2.4-identity-http`, alcançado **só**
  pelo adapter montado no composition root (§7 D1).
- **`L-ORD`** — lei de ordem total dos dois ports (ADR 3.3.0003). Consumida,
  não estendida (§7 D6).
- **`register_error_handlers` genérico de `shared`** — rede de segurança.

### 4.1 Inventário de rotas

Prefixo `/api/v1`. Todas autenticadas — **não há rota pública em staff**.

A coluna **"Papéis que devem passar"** registra o que a `workforce.md` §4
(status `accepted`) já sustenta: `owner`, `manager` e `hr` gerenciam a equipe;
`employee` **não enxerga nada de staff**; `platform_admin` não tem acesso de
restaurante. **O nome da permissão exigida e a divergência hr × manager
dependem de F1**, e o alvo de autorização das quatro primeiras rotas depende de
**F3** — por isso as duas colunas restantes não estão preenchidas: preenchê-las
por chute é exatamente o que o protocolo de bifurcação proíbe.

**Função de trabalho** (recurso **tenant-scoped** — `workforce.md` §3.2; o
tenant vem do ator, nunca do corpo):

| Método | Rota | Use case | Papéis que devem passar | Sucesso |
|---|---|---|---|---|
| `POST` | `/job-functions` | `create_job_function` | owner, manager, hr | 201 |
| `GET` | `/job-functions` | `list_job_functions` | owner, manager, hr | 200 |
| `PATCH` | `/job-functions/{job_function_id}` | `rename_job_function` | owner, manager, hr | 200 |
| `DELETE` | `/job-functions/{job_function_id}` | `delete_job_function` | owner, manager, hr | 204 |

> **⚠ F3 — estas quatro rotas são hoje inalcançáveis por `manager` e `hr`.**
> Um recurso tenant-scoped não tem unidade alvo, e `authorize_action.py:81-83`
> nega **qualquer** ator que não faça bypass de unidade quando `unit_id is None`
> (`_UNIT_SCOPE_BYPASS_ROLES = {OWNER, PLATFORM_ADMIN}`). Como o DoD exige
> *"gerente cria função customizada"*, a Stage não fecha sem resolver isto.
> Ver §13 F3.

**Funcionário** (recurso **unit-scoped**; a unidade vem do **path**, o tenant do
ator):

| Método | Rota | Use case | Papéis que devem passar | Sucesso |
|---|---|---|---|---|
| `POST` | `/units/{unit_id}/employees` | `create_employee` | owner, manager, hr | 201 |
| `GET` | `/units/{unit_id}/employees?include_inactive=` | `list_employees` | owner, manager, hr | 200 |
| `PATCH` | `/units/{unit_id}/employees/{employee_id}` | `rename_employee` | owner, manager, hr | 200 |
| `PUT` | `/units/{unit_id}/employees/{employee_id}/job-functions` | `assign_job_functions` | owner, manager, hr | 200 |
| `PUT` | `/units/{unit_id}/employees/{employee_id}/workload-profile` | `change_workload_profile` | owner, manager, hr | 200 |
| `PUT` | `/units/{unit_id}/employees/{employee_id}/shift-preference` | `declare_shift_preference` | owner, manager, hr | 200 |
| `POST` | `/units/{unit_id}/employees/{employee_id}/unavailabilities` | `register_unavailability` | owner, manager, hr | 200 |
| `DELETE` | `/units/{unit_id}/employees/{employee_id}/unavailabilities?start=&end=` | `remove_unavailability` | owner, manager, hr | 200 |
| `POST` | `/units/{unit_id}/employees/{employee_id}/termination` | `deactivate_employee` | owner, manager, hr | 200 |
| `POST` | `/units/{unit_id}/employees/{employee_id}/rehire` | `reactivate_employee` | owner, manager, hr | 200 |
| `DELETE` | `/units/{unit_id}/employees/{employee_id}` | `delete_employee` | owner, manager, hr | 204 |
| `POST` | `/units/{unit_id}/employees/{employee_id}/copies` | `copy_employee_to_unit` | owner, manager, hr | 201 |

Três escolhas de forma valem justificativa, e nenhuma é cosmética:

- **`PUT` para substituição, `POST` para acréscimo.** `assign_job_functions` é
  **substituição** do conjunto (commands.py: "não é acréscimo"), e
  `declare_shift_preference` com `null` **limpa** — as duas são idempotentes e
  são `PUT`. `register_unavailability` acrescenta um item e é `POST`.
- **`DELETE` com query params para a indisponibilidade.** O período é removido
  **por igualdade de valor**, não por id — ele não tem identidade. Query params
  expressam isso sem exigir corpo num `DELETE`.
- **`termination`/`rehire` como sub-recursos `POST`.** São as duas transições
  nomeadas do ciclo de vida (ADR 3.2.0006), não edições de campo. Um
  `PATCH {"active": false}` faria a transição parecer atribuição de atributo —
  exatamente a leitura que o ADR 3.2.0007 recusa.

**O aninhamento sob `/units/{unit_id}` dá alvo ao eixo de visibilidade**, mas
**não** verifica que o funcionário pertence àquela unidade. É o buraco de F2, e
está descrito em §13.

### 4.2 Inventário de schemas

**Requests** — nenhum tem `tenant_id`, e a ausência é a defesa: o tenant vem do
ator. Nenhum tem `unit_id` de corpo, exceto o `target_unit_id` da cópia, que é
escolha legítima do usuário e por isso é **autorizado** (§5.6).

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

`WorkloadProfilePayload` é uma união discriminada por `type`:
`{"type": "fixed", "weekly_hours": "40.0"}` ou `{"type": "on_demand"}`. A
discriminação existe no wire porque existe no domínio: a união
`FixedSchedule | OnDemand` foi desenhada para tornar "sob demanda com carga"
irrepresentável, e achatar os dois num objeto de campos opcionais devolveria à
borda o estado inválido que o domínio eliminou.

**`DeclareShiftPreferenceRequest.shift_preference` não tem default**, espelhando
o command: ali `None` significa "**limpe** a preferência", não "não mexa". Com
default, um corpo `{}` limparia a preferência em silêncio.

**Responses:**

| Schema | Campos |
|---|---|
| `JobFunctionResponse` | `id`, `tenant_id`, `name` |
| `EmployeeResponse` | `id`, `tenant_id`, `unit_id`, `name`, `workload_profile`, `shift_preference: list[str] \| None`, `job_function_ids: list[str]`, `unavailabilities: list[UnavailabilityPayload]`, `active: bool` |

- **`job_function_ids` sai como lista ordenada.** O `EmployeeResult` o entrega
  como `frozenset`, e results.py diz que "ordenar para exibição é do adapter da
  3.4". Sem ordenar, a resposta variaria entre execuções.
- **`weekly_hours` viaja como string.** A 3.3 provou que valor **e escala**
  sobrevivem ao round-trip (CA17); serializar como número JSON entregaria o
  valor a um float e perderia a escala no cliente.
- **`start`/`end` viajam ingênuos (sem offset).** São wall-clock do fuso da
  unidade (ADR 3.1.0005); anexar `Z` os transformaria em outro instante.

### 4.3 O que **não** aparece em nenhum schema

- **Nenhum DTO de application é usado como schema**, e nenhum schema entra num
  use case (LAYOUT §7; skill `fastapi-thin-adapter`).
- **Nenhuma entidade de domínio na resposta** — `EmployeeResponse` é montado a
  partir de `EmployeeResult`, não de `Employee`. A propriedade é verificável
  como **ausência de import**: `router.py` e `schemas.py` de staff não importam
  nada de `staff.domain.entities` (CA3).
- **Nenhum campo de vínculo de login** (`user_id`) — hoje vacuamente
  verdadeiro; a 3.5 acrescenta o campo e a restrição fica declarada.

## 5. Invariantes e regras

**5.1 — Nenhuma rota de staff é pública.** Toda rota exige Bearer válido.

**5.2 — A decisão de acesso não acontece em staff.** O adapter declara o
requisito (permissão + alvo) e delega. Não há tabela de papéis, mapa de
permissões nem lógica de bypass em `features/staff/`. Espelha `dependencies.py`
de identity e o ADR 2.4.0003 §1, e **é verificável por teste** (CA13).

**5.3 — O `tenant_id` de todo command/query vem do `AuthorizedScope`, nunca do
corpo nem do path.** Um `tenant_id` aceito do cliente é vetor de escalada
cross-tenant (ADR 2.4.0003 §4). E ele **nunca é vazio** (L-AG3).

**5.4 — O `unit_id` das rotas de funcionário vem do path e é sempre alvo de
autorização.** Um path param nomeia o recurso e é resolvido contra o banco
(`AuthorizeActionUseCase` faz `units.find_by_id`), ao contrário de um campo de
corpo, que é afirmação não verificada do cliente. **Autorizar o `unit_id` do
path não prova que o funcionário do path pertence a ele** — ver F2.

**5.5 — A construção de value object acontece no router, não no schema.** É o
que faz um período malformado levantar erro **de domínio** (`StaffError` → mapa
de status desta Stage) em vez de `RequestValidationError` do FastAPI, que segue
outro caminho e outro formato de corpo.

**5.6 — A unidade destino da cópia é autorizada como alvo, exatamente como a de
origem.** A rota de cópia faz **duas** chamadas ao guard: uma com `unit_id` da
unidade do path (origem) e outra com `target_unit_id` do corpo (destino).
Fecha o finding nº 1 sem que staff conheça `Unit`. Consequências, todas
desejadas e **indistinguíveis entre si**:

- destino de **outro tenant** ⇒ `TenantNotVisibleError` → 403 de corpo constante;
- destino **inexistente** ⇒ `UnitNotFoundError`, convertido pelo guard em
  `UnitNotVisibleError` → 403;
- destino que o ator **não enxerga** ⇒ `UnitNotVisibleError` → 403.

**5.7 — Cópia repetida para o mesmo destino continua sendo limite declarado.**
Homônimos são legítimos por decisão de domínio (`employee.py`), então "já existe
alguém com esse nome na unidade destino" **não é** sinal de cópia duplicada.
Ver §7 D7 e ADR 3.4.0005.

**5.8 — O corpo das faixas 401 e 403 é constante**, herdado do handler de
identity, que está registrado sobre a **app** e é alcançado por MRO
independentemente de qual router levantou. O que sustenta a herança não é a
coincidência: são L-AG1 e L-AG2, que proíbem o adapter do `AccessGuard` de
traduzir a exceção. Staff **não** registra entrada 401/403 no seu mapa.

**5.9 — O mapa exceção → status de staff é total, e a totalidade é teste.** O
teste enumera recursivamente as subclasses concretas de `StaffError`
(excluindo a raiz) e exige entrada **própria** para cada uma; e asserta o
**par classe→status**, não apenas que a faixa foi alcançada (ADR 3.4.0002).

**5.10 — Nenhum caminho de rota devolve 500 por conteúdo de requisição** —
corpo, path ou query. Os dois erros de concorrência do Postgres (`40P01`
deadlock, `40001` serialization) continuam subindo crus, **e isso é declarado**:
são falhas transitórias de infraestrutura, e 500 é a resposta correta para elas.

**5.11 — A ordem das duas listagens é a do port** (`L-ORD`), e esta Stage não a
reordena nem a fatia. Sem `LIMIT`/`OFFSET`, a regex `_ORDER_BY` de
`test_staff_conduct.py:194` continua correta — ver §7 D6.

**5.12 — Toda resposta de escrita devolve o estado resultante**, exceto as duas
remoções definitivas, que devolvem 204. **Consequência de segurança:** enquanto
F2 estiver aberta, essa devolução transforma qualquer rota de mutação numa
sonda de leitura de todo o tenant — está tratado em F2, não aqui.

**5.13 — Matriz papel × staff (a parte ancorada).** De `workforce.md` §4:

| Papel | No BC staff |
|---|---|
| `owner` | gerencia a equipe; **bypassa** memberships (enxerga todas as unidades do tenant) |
| `manager` | gerencia a equipe das unidades das quais é membro |
| `hr` | gerencia a equipe; **diverge de `manager`** — e o **eixo da divergência é ratificado**: `workforce.md` §4 diz que "visibilidade e permissões de equipe são o **único** eixo de divergência". O que fica aberto é o **grau** (quais operações, e se hr enxerga o tenant inteiro) — **F1** |
| `employee` | **nada**: nenhuma das 16 rotas |
| `platform_admin` | **nada**: acesso de plataforma não é acesso de restaurante |

**5.14 — Todo identificador vindo de path ou query é validado na borda** antes
de qualquer consulta: vazio, só-whitespace ou contendo o byte NUL ⇒
`InvalidIdentifierError` → 422. Sem esta regra, `GET /units/%00/employees`
chega a `units.find_by_id("\x00")` **dentro de identity** e produz
`psycopg.DataError` → 500 — um caminho que a correção de domínio de D4 não
alcança, porque identificador não passa por entidade nenhuma
(`identifiers.py`: "este módulo não tem lógica de runtime").

## 6. Casos de erro e exceções

### 6.1 Mapa de status — erros do BC staff

Um handler único registrado sobre `StaffError`, resolvendo o status pelo
`__mro__` (ADR 3.4.0002). São **18** entradas: 17 subclasses concretas hoje
(8 no domínio + 9 na application; `StaffError` é a raiz, não entrada) mais
`InvalidDayPeriodError`.

| Faixa | Exceções | Razão da faixa |
|---|---|---|
| **404** | `JobFunctionNotFoundError`, `EmployeeNotFoundError` | recurso endereçável ausente **no tenant do ator**. São os dois que herdam de `NotFoundError`, nessa ordem de MRO, exatamente para isto |
| **409** | `JobFunctionNameAlreadyExistsError`, `JobFunctionAlreadyExistsError`, `EmployeeAlreadyExistsError`, `JobFunctionInUseError`, `EmployeeInUseError` | conflito com estado **já gravado**: ou a chave existe, ou uma referência existente impede a remoção |
| **422** | `InvalidNameError`, `InvalidIdentifierError`, `InvalidWeeklyHoursError`, `EmptyShiftPreferenceError`, `EmptyJobFunctionsError`, `InvalidUnavailabilityPeriodError`, `InvalidDayPeriodError`, `OverlappingUnavailabilityError`, `UnavailabilityNotFoundError`, `EmployeeRelocationError`, `SameUnitCopyError` | invariante violada **pelo conteúdo enviado** |

Quatro entradas exigem justificativa individual, porque em todas há leitura
alternativa plausível:

- **`UnavailabilityNotFoundError` é 422, não 404** — decisão da 3.2, e o porquê
  é estrutural: o período é um **valor dentro do agregado**, não um recurso
  endereçável. O funcionário existe e foi encontrado. A classe herda **só** de
  `StaffError` precisamente para que a MRO não a leve ao 404.
- **`OverlappingUnavailabilityError` é 422, não 409** — invariante do agregado
  violada pelo período **que o cliente enviou**, não colisão de chave gravada.
- **`JobFunctionInUseError` / `EmployeeInUseError` são 409, não 422** — o
  payload está correto; o que impede a operação é **outro registro**.
- **`SameUnitCopyError` é 422, não 409** — nada está em conflito: o cliente
  nomeou a origem como destino.

**`EmployeeInUseError` continua sem produtor em v1** (nasce com o Step 4) e
mesmo assim tem entrada própria. **`EmployeeRelocationError` é inalcançável por
HTTP nesta Stage**, porque nenhuma rota permite enviar `unit_id` num `update` —
tem entrada por totalidade, e a inalcançabilidade é registrada para que ninguém
escreva um e2e esperando produzi-la.

### 6.2 Erros que **não** chegam ao handler de staff

| Cenário | Exceção | Status | Quem responde |
|---|---|---|---|
| Sem header / esquema errado / token inválido ou expirado | `InvalidAccessTokenError` | 401 corpo constante | handler de identity |
| Papel não concede a permissão | `PermissionDeniedError` | 403 corpo constante | handler de identity |
| Ator de tenant não declarou tenant alvo | `TenantScopeRequiredError` | 403 | handler de identity |
| Tenant alvo ≠ tenant do ator; unidade alvo de outro tenant | `TenantNotVisibleError` | 403 | handler de identity |
| Ator escopado sem unidade declarada | `UnitScopeRequiredError` | 403 | handler de identity |
| Unidade inexistente **ou** não visível | `UnitNotVisibleError` | 403 | guard converte, handler de identity |
| Corpo malformado (tipo errado, campo faltando) | `RequestValidationError` | 422 corpo constante | handler de `shared` |

**Consequência declarada:** um 403 de staff é indistinguível de um 403 de
identity, no status e no corpo. É a propriedade desejada.

### 6.3 O que hoje viraria 500, e o que esta Stage faz com cada um

| Origem | Hoje | Nesta Stage |
|---|---|---|
| Nome com byte NUL no **corpo** (`psycopg.DataError`, recusa client-side, sem sqlstate e com `constraint_name` nulo) | 500 | **rejeitado no domínio** — `InvalidNameError` → 422 (D4) |
| Byte NUL ou vazio num **id de path/query** (não passa por entidade; atinge identity antes de staff) | 500 | **rejeitado na borda** — `InvalidIdentifierError` → 422 (§5.14, D10) |
| Período do dia desconhecido (`DayPeriod("xpto")` → `ValueError`) | 500 | `DayPeriod.from_string` → `InvalidDayPeriodError` → 422 (D5) |
| Ator sem tenant alcançando o adapter do guard | coerção silenciosa para `""` | **negado** pelo adapter (L-AG3) |
| Deadlock (`40P01`) / falha de serialização (`40001`) | 500 | **segue 500, declarado em §5.10** |

## 7. Decisões técnicas relevantes

### D1 — O tradutor entre staff e identity é montado no composition root, sem supressão no `.importlinter`

- **O quê:** staff declara `AccessGuard` (port-out, vocabulário próprio,
  identificadores como `str` opaca, leis L-AG1…L-AG4). A **implementação** é
  montada em `composition_root.py`, que já importa os dois BCs por desenho. O
  router recebe o port por `dependency_overrides`. **Nenhum módulo de
  `features/staff/` importa `features/identity/`**, e o contrato
  `bc-independence` permanece **absoluto**.
- **Por quê:** a alternativa (adapter em `features/staff/adapters/out/identity/`
  com `ignore_imports`) foi a primeira escolha e **caiu na medição**: o objeto
  a embrulhar, `IdentityGuard`, vive em `adapters/in/http/`, e `in` é keyword
  Python — `from …adapters.in.http… import IdentityGuard` é **SyntaxError**. O
  composition root já convive com isso (`identity_guard: Any` mais `importlib`).
  Logo o adapter em staff **não conseguiria sequer anotar** o objeto que
  embrulha, e ainda assim precisaria de supressão para `Permission`,
  `RestaurantId` e `UnitId` — **três pares**, não um. A promessa "um par, uma
  direção" era falsa, e sem ela a alternativa perde o que a justificava.
- **Custo declarado:** o composition root ganha ~30 linhas com comportamento
  (tradução de vocabulário), o que não é wiring puro. É o preço de manter
  `bc-independence` sem exceção — e é reversível: mover a classe para
  `features/staff/adapters/out/identity/` na 3.5, quando o `IdentityGateway`
  chegar, é um movimento de arquivo mais a supressão que se decidir pagar
  **então**, com o consumidor real na mão.
- **Fonte:** `composition_root.py:24-27` e `:185-188` (a keyword `in` e o
  `Any`); `.importlinter` (`bc-independence`); LAYOUT §1, §5, §6; roadmap
  §Stage 3.5.
- **ADR:** [`../../adr/3_4_0001-staff-owned-access-guard-port.md`](../../adr/3_4_0001-staff-owned-access-guard-port.md)

> **Por que o port fica em `application/ports/out/` e não dentro do adapter
> HTTP:** o consumidor **desta** Stage é o router, o que por si só sugeriria
> colocá-lo em `adapters/in/http/`. A colocação em `ports/out/` antecipa a 3.5,
> cujo `IdentityGateway` é consumido por **use case** — e cuja pasta o roadmap
> já nomeia. É o critério de escalabilidade progressiva, não LAYOUT §5, que
> decide aqui; a alternativa está registrada no ADR.

### D2 — Um handler único sobre `StaffError`, com mapa total resolvido por MRO

- **O quê:** replicar o desenho do `error_handlers.py` de identity para staff,
  no arquivo da feature, com totalidade **e mapeamento par a par** por teste.
- **Por quê:** a hierarquia de erros de staff foi construída para isto — o
  `application/errors.py` diz que "a Stage 3.4 refina para 404/409 registrando
  handlers, sem tocar nesta camada", e a MRO existe para que o handler daqui
  ganhe do genérico. `shared` não pode referenciar classes de feature (LAYOUT §7).
- **Fonte:** `application/errors.py` de staff; ADR 2.4.0001;
  `error_handlers.py` de identity.
- **ADR:** [`../../adr/3_4_0002-staff-http-error-status-mapping.md`](../../adr/3_4_0002-staff-http-error-status-mapping.md)

### D3 — A unidade destino da cópia é autorizada, não validada

- **O quê:** a rota de cópia chama o guard duas vezes (origem e destino).
- **Por quê:** é o **único** caminho que fecha o finding nº 1 sem que staff
  conheça `Unit`, e reaproveita quatro propriedades já provadas em identity:
  resolução da unidade contra o banco, comparação de tenant, eixo de
  visibilidade e a conversão `UnitNotFoundError → UnitNotVisibleError`, que
  impede o destino inexistente de virar oráculo de enumeração.
- **Fonte:** `[finding]` da 3.2 §10; ADR 3.2.0003; `authorize_action.py` passos
  3 e 5; `dependencies.py` de identity; `employee.py`.
- **Sem ADR próprio:** aplicação direta do mecanismo do ADR 2.4.0003 §3 a um
  segundo BC; não há alternativa real que staff possa implementar.

### D4 — O byte NUL é rejeitado no domínio, não tratado na borda

- **O quê:** `Employee` e `JobFunction` rejeitam nome contendo `\x00`, com
  `InvalidNameError`. Expansão declarada de camada-alvo para o domínio da 3.1.
- **Por quê:** `DataError` **não** é `IntegrityError`, então o tradutor da 3.3
  nunca é chamado; a recusa é **client-side**, sem sqlstate e com
  `constraint_name` nulo. Rejeitar no domínio é o único conserto que faz fake e
  real concordarem **por construção** — e é o que permite a suíte de lei
  exercitar o caso.
- **Escopo mínimo e deliberado: só o NUL.** A 3.3 mediu que todo o resto do
  conjunto adversarial faz round-trip verbatim nos dois lados; alargar seria
  normalização silenciosa contra o ADR 2.3.0005.
- **Limite honesto:** cobre **nome**, não identificador. O vetor de path/query
  é fechado por D10, não por aqui.
- **Fonte:** `[finding]` da 3.3 §7 (2026-08-11); issue #40 finding nº 3.
- **ADR:** [`../../adr/3_4_0003-reject-nul-byte-in-staff-domain-names.md`](../../adr/3_4_0003-reject-nul-byte-in-staff-domain-names.md)

### D5 — `DayPeriod` ganha `from_string`, espelhando `Role.from_string`

- **O quê:** conversão texto → `DayPeriod` com erro de domínio
  (`InvalidDayPeriodError`), no domínio da 3.1.
- **Por quê:** §5.5 exige conversão no router para que a falha seja erro de
  domínio; `DayPeriod` é `StrEnum` sem conversor, e `DayPeriod("xpto")` levanta
  `ValueError`, que não é `StaffError` e vira 500.
- **Fonte:** `role.py` de identity; router de identity; 3.2 §6.
- **Sem ADR próprio:** entra no ADR 3.4.0003 como decisão irmã — a única outra
  opção (validar o enum no schema Pydantic) contraria a regra §5.5, herdada e
  fora de disputa.

### D6 — Esta Stage **não** introduz paginação

- **O quê:** as duas rotas `GET` devolvem a coleção inteira, na ordem do port.
- **Por quê:** paginar exigiria **estender os dois ports da 3.2 e os dois
  adapters da 3.3** com parâmetros de cursor — emendar contrato de duas Stages
  fechadas, que é o defeito que a publicação antecipada de `L-ORD` e de
  `EmployeeInUseError` existe para evitar. O DoD do bloco 3.4 é sobre cadastro e
  isolamento entre unidades, não sobre volume, e a Stage já absorveu um port,
  um tradutor e uma expansão de domínio.

  > **Argumento explicitamente NÃO usado:** `contratos_introduzidos: []` no
  > bloco 3.4. Este concept demonstra em §1 que o campo não descreve a Stage;
  > usá-lo como prova aqui e refutá-lo lá seria contraditório.
- **Consequência positiva imediata:** sem `LIMIT`/`OFFSET`, a regex `_ORDER_BY`
  de `test_staff_conduct.py:194` **continua correta** e o antídoto registrado na
  §7 da 3.3 não precisa ser aplicado. Fica escalado junto com a paginação —
  quem a acrescentar aplica os dois no mesmo commit.
- **Fonte:** `docs/roadmap.md` §Stage 3.4 (DoD, `complexidade_estimada`);
  ADR 3.3.0003; `[finding]` da 3.3 §7 (2026-08-12). As duas afirmações
  contrárias (roadmap §3.3 e o finding) são corrigidas pela nota datada — §1.
- **ADR:** [`../../adr/3_4_0004-no-pagination-in-staff-http.md`](../../adr/3_4_0004-no-pagination-in-staff-http.md)

### D7 — Cópia repetida segue limite declarado; a borda não a guarda nem a sinaliza

- **O quê:** nenhuma guarda de duplicidade **e nenhum campo informativo** na
  rota de cópia. O limite é declarado em §5.7; a rota devolve 201 com o registro
  novo, cujo `id` difere do original.
- **Por quê, nas duas metades do finding.** O finding da 3.2 pede
  *"confirmação **/ feedback de que já existe registro homônimo na unidade
  destino**"* — duas coisas, e as duas são recusadas por razões diferentes:
  - **Guarda/confirmação:** a única heurística disponível é o nome, e ela é
    **falsa por construção** — o domínio declara homônimos legítimos, então
    recusar (ou pedir confirmação) rejeitaria cadastros válidos e ainda poria
    regra de negócio no adapter.
  - **Feedback informativo** (um campo do tipo `homonyms_in_target: N` no corpo
    do 201, sem recusar nada): **avaliado e rejeitado** — exigiria uma consulta
    extra à listagem do destino a cada cópia, para produzir um número que o
    cliente obtém sozinho com um `GET`, e que **não significa o que parece**
    (homônimo ≠ duplicata). Um campo cujo nome sugere "você já copiou isto" e
    cujo valor mede outra coisa é pior que a ausência dele.
- **Consequência assumida:** o finding é fechado **abaixo do que pedia**, e
  isso está dito, não maquiado. O eixo de UX é escalado (§10).
- **Fonte:** `[finding]` da 3.2 §10 (citado por inteiro no ADR); ADR 3.2.0003;
  `employee.py`; skill `fastapi-thin-adapter`.
- **ADR:** [`../../adr/3_4_0005-repeated-copy-remains-a-declared-limit.md`](../../adr/3_4_0005-repeated-copy-remains-a-declared-limit.md)

### D8 — `HttpWiring` passa a carregar coleções

- **O quê:** `router` → `routers`, `register_error_handlers` → coleção de
  registradores; `dependency_overrides` continua sendo um mapa único (as chaves
  são funções distintas por BC).
- **Por quê:** dois BCs registram superfície HTTP. Manter o campo singular
  obrigaria staff a pendurar o router dentro do de identity, ou obrigaria
  `app.py` a conhecer features, quebrando a supressão estreita de
  `shared-independence`.
- **Nota:** a mudança é sobre o **router**. A propriedade de corpo constante
  401/403 **não** depende dela — o handler de identity é registrado sobre a app
  e alcançado por MRO (§3 Premissas).
- **Sem ADR:** extensão aditiva de forma, sem alternativa real defensável.

### D9 — Sem `gate_mode: batch`

O bloco 3.4 declara `gate_mode: strict`. Esta Stage toca autorização, mapa de
status e domínio já mergeado — nada aqui é fundação validada.

### D10 — Identificadores de path e query são validados na borda

- **O quê:** um conversor único do adapter rejeita id vazio, só-whitespace ou
  com byte NUL, levantando `InvalidIdentifierError` (422), antes de qualquer
  chamada ao guard ou ao use case.
- **Por quê:** `EmployeeId`/`JobFunctionId`/`UnitId`/`TenantId` são `NewType`
  **sem validação de runtime**, por decisão explícita da 3.1
  (`identifiers.py`: "a validação de não-vazio é imposta nas entidades, não
  aqui"). Um id de path nunca passa por entidade — vai direto para
  `find_by_id`. Logo `GET /units/%00/employees` atinge `units.find_by_id` **em
  identity** e produz 500, e a correção de domínio de D4 não o alcança.
- **Fonte:** `staff/domain/value_objects/identifiers.py` (docstring);
  `authorize_action.py:129`; §5.10.
- **Sem ADR:** não há alternativa real — validar no `NewType` é impossível, e
  validar em cada rota é a mesma regra escrita 16 vezes.

## 8. Integrações

### Internas

- **`features/identity`** — alcançada **só** pelo composition root (D1).
  Nenhum módulo de `features/staff/` a importa.
- **`composition_root.py`** — monta o tradutor do `AccessGuard` sobre o
  `IdentityGuard` já construído (mesmo objeto, não um segundo grafo), carrega o
  router e o registrador de handlers de staff por `importlib` (o pacote `in` é
  keyword — LAYOUT §8) e acrescenta 17 entradas ao mapa de overrides.
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
| **F2 não resolvida vira exfiltração intra-tenant**: `PATCH /units/A/employees/{id-de-B}` devolve o registro inteiro de B, e `…/copies` com destino A **clona** B para dentro da unidade do atacante | A | **A** | Bifurcação aberta em §13; a Stage não entra em Fase 4 sem ela fechada. CA9 é escrito para falhar enquanto o buraco existir |
| **F3 não resolvida torna o DoD inalcançável**: `manager` recebe 403 nas 4 rotas de função | **A** | **A** | Bifurcação aberta em §13; CA29 é escrito com ator `manager` real, nunca `owner` |
| F1 arrastar mudança no domínio de identity sem que a expansão seja declarada | A | M | §1 e §13 declaram a expansão como consequência conhecida das três bifurcações, com ADR e reconciliação de roadmap exigidos |
| Mapa de status incompleto após erro novo em Stage futura | M | M | Totalidade + par classe→status por teste (§5.9, CA21 e CA22) |
| Mudança no domínio da 3.1 (byte NUL) quebrar suíte já mergeada sem que o desvio de camada seja notado | M | M | Task dedicada, expansão declarada em §1 e no ADR 3.4.0003 |
| 16 rotas + guard + handlers + e2e estourarem a faixa de 3–12 Tasks | M | M | Agrupamento por recurso: funções e funcionário viram blocos, não uma Task por rota |
| `complexidade_estimada: S` do roadmap ficar falso | A | B | Já declarado em §1: a Stage é **M** |

### `[finding]` a escalar

- **`[finding]` — paginação das listagens de staff** (D6), junto com o antídoto
  de uma linha da regex `_ORDER_BY`. **Stage candidata:** a primeira Stage que
  precise de listagem paginada — candidata natural `4.x` ou uma Stage dedicada
  de API.
- **`[finding]` — o byte NUL também escapa em identity.** `Restaurant`, `Unit` e
  `User` aceitam nome com `\x00` e lá também viraria 500 (D10 fecha só o vetor
  de **id**, não o de **nome** de identity). **Stage candidata:**
  `6.x-hardening` ou a próxima Stage que toque `features/identity/domain`.
- **`[finding]` — o gatilho do ADR 2.4.0003 §Consequences segue NÃO disparado.**
  Ele fala de um adapter que **contorna** a composição chamando
  `CreateUserUseCase` diretamente; um segundo router HTTP que **aplica** a
  composição não é esse caso, e staff não cria usuário. Registrado para o
  primeiro adapter **não-HTTP** (CLI/worker). **Stage candidata:** a Stage que o
  introduzir, ou `6.x-hardening`.
- **`[finding]` — cópia repetida sem sinal na borda** (D7) permanece aberto no
  eixo de **UX**. **Stage candidata:** a primeira Stage de frontend do Step 3.
- **`[finding]` — o tradutor do `AccessGuard` mora no composition root** (D1).
  Quando a 3.5 trouxer o `IdentityGateway`, reavaliar mover os dois para
  `features/staff/adapters/out/identity/` com a supressão que se decidir pagar.
  **Stage candidata:** `3.5-employee-login-link`.

## 11. Critérios de aceitação

### Rotas e contrato

- [ ] **CA1** — As 16 rotas de §4.1 existem, respondem no prefixo `/api/v1` e
      cada uma chama **exatamente um** use case.
- [ ] **CA2** — Nenhum schema de request tem campo `tenant_id`; teste varre
      `model_fields` de **todos** os `*Request` e falha se algum aparecer.
- [ ] **CA3** — `router.py` e `schemas.py` de staff **não importam nenhum
      símbolo** de `staff.domain.entities`, e nenhum use case recebe um schema
      Pydantic. Verificado por varredura de **imports** (decidível), não de
      anotações.
- [ ] **CA4** — `job_function_ids` sai ordenado; duas execuções com o mesmo
      registro produzem corpos byte-idênticos.
- [ ] **CA5** — `weekly_hours` sobrevive ao round-trip HTTP em **valor e
      escala**: `"22.50"` enviado volta `"22.50"`.
- [ ] **CA6** — `start`/`end` voltam sem offset; um envio com `Z` recebe 422
      (`InvalidUnavailabilityPeriodError`), não é silenciosamente convertido.
- [ ] **CA7** — `PUT /shift-preference` com `{"shift_preference": null}` limpa
      a preferência; corpo `{}` recebe 422 (campo obrigatório).

### Acesso

- [ ] **CA8** — Toda rota de staff sem Bearer recebe 401 com corpo constante e
      header `WWW-Authenticate: Bearer`; teste **enumera as rotas do router**,
      não uma amostra.
- [ ] **CA9** — *(dependente de F2)* Um ator escopado à unidade A não consegue
      **ler nem mutar** funcionário da unidade B por nenhuma das 12 rotas de
      funcionário, **e não consegue copiá-lo para A**; teste enumera as rotas.
- [ ] **CA10** — `employee` recebe 403 em **todas** as 16 rotas.
- [ ] **CA11** — `platform_admin` recebe 403 em **todas** as 16 rotas.
- [ ] **CA12** — *(dependente de F1 e F3)* A matriz de §5.13 é verificada rota a
      rota com atores reais de cada papel, incluindo a divergência hr × manager.
- [ ] **CA13** — Nenhum módulo em `features/staff/` importa `features.identity`
      nem nomeia `Role`/`Permission`; teste de varredura + `lint-imports` verde.
- [ ] **CA14** — O contrato `bc-independence` do `.importlinter` continua **sem
      nenhum `ignore_imports`**; teste lê o arquivo e falha se a lista existir.
- [ ] **CA15** — O `AccessGuard` é exercitado com uma **segunda implementação**
      (fake) e as leis L-AG1…L-AG4 são testadas contra ela: exceção que sai crua,
      recusa de `tenant_id` ausente, uma autorização por alvo.

### Cópia (finding nº 1)

- [ ] **CA16** — Cópia com `target_unit_id` de **outro tenant** recebe 403 com
      corpo constante, e **nada é gravado**.
- [ ] **CA17** — Cópia com `target_unit_id` **inexistente** recebe 403 — o
      **mesmo** status e o **mesmo** corpo do caso anterior e do caso "existe e
      o ator não a enxerga". Os três são indistinguíveis.
- [ ] **CA18** — Cópia cuja **unidade de origem** o ator não enxerga recebe 403.
      *(Mata a mutação "remover a primeira chamada de `authorize`", que
      sobreviveria a CA16/CA17.)*
- [ ] **CA19** — Cópia para unidade válida do mesmo tenant devolve 201, com `id`
      **diferente** do original e `unit_id` = destino; o registro de origem
      permanece inalterado.
- [ ] **CA20** — Cópia para a própria unidade de origem recebe 422
      (`SameUnitCopyError`).

### Erros

- [ ] **CA21** — O mapa `STAFF_ERROR_STATUS` é **total**: teste enumera
      recursivamente as subclasses concretas de `StaffError` (excluída a raiz) e
      exige entrada própria para cada uma. Classe nova sem entrada **reprova**.
- [ ] **CA22** — O mapa é verificado **par a par** (classe → status), em teste
      parametrizado sobre a tabela de §6.1. *(Trocar duas entradas dentro de
      faixas já exercitadas sobreviveria a um teste só de faixas.)*
- [ ] **CA23** — Cada faixa de §6.1 é exercitada por ao menos um teste que chega
      pelo HTTP real, não por chamada direta ao handler.
- [ ] **CA24** — `UnavailabilityNotFoundError` responde **422**, e há teste que
      falha se alguém a fizer herdar de `NotFoundError`.
- [ ] **CA25** — Nome contendo `\x00` recebe **422** em `POST /job-functions` e
      em `POST /units/{id}/employees` — **e** a suíte de lei dos ports passa a
      exercitar o caso, com fake e Postgres concordando.
- [ ] **CA26** — Período do dia desconhecido recebe 422, não 500.
- [ ] **CA27** — Id de **path/query** vazio ou com `\x00` recebe 422 em todas as
      rotas que têm parâmetro de id — incluindo `GET /units/%00/employees`, que
      hoje produz 500 dentro de identity.
- [ ] **CA28** — Varredura: nenhuma rota **que aceite texto livre** devolve 500
      para o conjunto adversarial da 3.3 (aspas, acento, emoji com ZWJ, `\n`,
      1000 caracteres, `\x00`). As rotas sem texto livre são cobertas por CA27.

### Fluxo e isolamento (DoD da issue #40)

- [ ] **CA29** — e2e feliz pelo entrypoint real, com ator **`manager`** (não
      `owner`): autentica, cria função customizada, cria funcionário com jornada
      fixa e preferência, registra indisponibilidade e lista a unidade — tudo
      pela API, contra Postgres real.
- [ ] **CA30** — Funcionário criado na unidade A **não aparece** em
      `GET /units/B/employees`.
- [ ] **CA31** — Desligado some da listagem default e reaparece com
      `include_inactive=true`; a recontratação o devolve à listagem default.
- [ ] **CA32** — A ordem da listagem é a de `L-ORD` e é estável entre execuções.

### Gates

- [ ] **CA33** — `make check` verde (inclui `lint-imports`, `layout-check`,
      `docs-check`, mypy strict).
- [ ] **CA34** — Cobertura ≥ 90% em **cada** arquivo novo/tocado da Stage.
- [ ] **CA35** — Nenhuma suíte já mergeada regride: as suítes de contrato e a de
      conduta continuam verdes **sem alteração da regex `_ORDER_BY`**
      (consequência de D6).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — sim (§4:
      `AccessGuard` com `Actor`, `AuthorizedScope` e as quatro leis; schemas;
      mapa de status).
- [x] Toda decisão em §7 tem fonte rastreável? — sim.
- [x] Toda integração externa tem contrato definido? — não há integração
      externa (§8).
- [x] Decisões com alternativa real descartada têm ADR escrito? — sim
      (3.4.0001–3.4.0005).
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — sim.
- [ ] Stage cabe em ~3–12 Tasks? — **provável 9–11**, **não confirmável**
      enquanto F1/F2/F3 estiverem abertas: as três podem acrescentar Tasks em
      `features/identity/domain` e em `features/staff/application`.
- [x] Riscos críticos têm mitigação plausível? — sim, exceto os três que são as
      próprias bifurcações.
- [ ] **A matriz papel × operação está fixada?** — **parcialmente** (§5.13); o
      eixo hr × manager e o nome da permissão são **F1**.
- [ ] **O escopo de unidade das rotas de funcionário é enforçável?** — **não**
      (F2).
- [ ] **As rotas tenant-scoped são alcançáveis pelos papéis do DoD?** — **não**
      (F3).
- [x] O `complexidade_estimada: S` do roadmap foi conferido? — sim, e está
      **errado**; reconciliação declarada em §1.

## 13. Questões em aberto

> Três bifurcações materiais. Todas afetam contrato e segurança; o **detalhe
> rico de cada uma vai na mensagem de handoff à sessão mestra**, não neste
> arquivo — aqui ficam o enunciado e a âncora. **Enquanto estiverem abertas
> este concept permanece `draft`** e a Stage não entra em Fase 3B.
>
> **O que as três têm em comum:** o vocabulário de permissões e o eixo de
> visibilidade vivem em `features/identity/domain`. Qualquer resolução implica
> **expansão de camada-alvo para um segundo bounded context** — maior que a
> expansão do byte NUL (D4), e assimétrica com ela, já que D4 recusa tocar
> identity. A assimetria é deliberada e está declarada: D4 tem conserto
> alternativo dentro do BC de staff, e estas três não têm.

### F1 — Qual é a divergência hr × manager, e onde vive a permissão de staff?

**O que as fontes JÁ fixam** (e este concept registra em §5.13): `owner`
gerencia com bypass de unidade; `manager` gerencia as unidades das quais é
membro; `employee` não enxerga nada de staff; `platform_admin` não tem acesso
de restaurante — `workforce.md` §4, status `accepted`.

**O eixo da divergência também já está fixado:** `workforce.md` §4 diz que, para
o `hr`, *"é NO STAFF que hr diverge do manager — **visibilidade e permissões de
equipe são o único eixo de divergência**"*. Não se procura um eixo novo.

**O que fica aberto é o GRAU**, e a própria `workforce.md` §4 o endereça a este
concept: *"o **detalhe da divergência hr × manager** (quais operações de staff
cada um pode — hr vê tudo do tenant? só cadastro, sem jornada?) não está fixado
em fonte ratificada **além de 'divergem na visibilidade e nas permissões de
staff'** — o concept da 3.4 fixa a matriz exata."* Somado a isso, o
**locus** da permissão: `Role.MANAGER` e `Role.HR` detêm hoje **exatamente** o
mesmo conjunto (`{MANAGE_USERS}`), e o único `Permission` de restaurante
disponível é `MANAGE_USERS` — então a divergência é **inexprimível** sem tocar
`features/identity/domain/value_objects/{role,permission}.py`. O
`permission.py` prevê a extensão ("as Stages/BCs seguintes estendem o
vocabulário"), mas prever não é decidir.

### F2 — Como a borda impede que um ator da unidade A alcance funcionário da unidade B?

**O requisito NÃO está em aberto** — ADR 3.2.0002 §Neutral aloca explicitamente
o escopo de unidade a esta Stage, e `workforce.md` §3.1 ratifica a invariante
("nenhuma operação de staff atravessa unidades implicitamente"). **O mecanismo
está.**

O `unit_id` do path é autorizado **contra o ator**, não **contra o
funcionário**. Nenhum command que atua sobre **registro existente** carrega
`unit_id` (os que carregam são `CreateEmployeeCommand`, cujo `unit_id` vem do
path e é gravado, e `CopyEmployeeToUnitCommand.target_unit_id`), e não existe
use case de leitura por id entre os 16. Logo um gerente da unidade A alcança
`{id-de-funcionário-da-unidade-B}` do mesmo tenant em **10 rotas de mutação**
mais a cópia. Duas consequências, ambas piores que "mutação indevida":

- **Leitura.** Toda rota de mutação devolve `EmployeeResponse` completo (§5.12),
  então um `PATCH` com o mesmo nome é uma sonda idempotente que devolve
  `unit_id`, jornada, preferência e indisponibilidades de qualquer funcionário
  do tenant.
- **Exfiltração.** `POST /units/A/employees/{id-de-B}/copies` com destino A
  **clona** o registro de B para dentro da unidade do atacante — as duas
  chamadas de §5.6 passam, porque ele enxerga A duas vezes.

Os mecanismos possíveis (acrescentar `unit_id` aos commands; criar use case de
leitura por id; escopar `find_by_id` por unidade) **todos emendam Stage
fechada**, e é essa conta que a mestra precisa levar ao sponsor.

### F3 — Como um recurso tenant-scoped é autorizado para um papel unit-scoped?

As quatro rotas de função de trabalho não têm unidade alvo — a função é
**tenant-scoped** por regra canônica (`workforce.md` §3.2), e aninhá-la sob uma
unidade seria mentir sobre o modelo. Mas `authorize_action.py:81-83` nega
qualquer ator que não faça bypass de unidade quando `unit_id is None`, e
`_UNIT_SCOPE_BYPASS_ROLES = {OWNER, PLATFORM_ADMIN}` (`user.py:45`). Resultado:
**só `owner` alcança as quatro rotas**, e o DoD do roadmap exige *"gerente cria
função customizada"*.

A regra que nega é deliberada e correta em identity — "omitir a unidade não
pode ser caminho de escalada" (ADR 2.2.0002). O que falta é como um recurso
legitimamente tenant-wide convive com ela. **Esta bifurcação não foi declarada
na primeira versão deste concept; entrou pelo Checkpoint A**, encontrada
independentemente pelos dois revisores.

## 14. Referências

- [`../../overview.md`](../../overview.md) §3, §6, §9
- [`../../roadmap.md`](../../roadmap.md) — blocos Stage 3.3, 3.4 e 3.5
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) — §3.1,
  §3.2, §3.7, **§4 (a matriz ancorada e a lacuna hr × manager)**
- [`../3.2-staff-application/concept.md`](../3.2-staff-application/concept.md)
  §4, §5, §6, §10
- [`../3.3-staff-persistence/technical.md`](../3.3-staff-persistence/technical.md)
  §7 (byte NUL, regex `_ORDER_BY`, tradução por operação)
- [`../2.4-identity-http/concept.md`](../2.4-identity-http/concept.md) e
  [`technical.md`](../2.4-identity-http/technical.md) — a Stage irmã
- ADRs consumidos: 2.1.0001, 2.2.0002, 2.3.0001, 2.3.0003, 2.3.0005, 2.4.0001,
  2.4.0002, **2.4.0003**, 3.1.0001, 3.1.0002, 3.1.0004, 3.1.0005, 3.1.0006,
  **3.2.0002** (§Neutral — o escopo de unidade é desta Stage), 3.2.0003,
  3.2.0004, 3.2.0005, 3.2.0006, 3.2.0007, 3.3.0002, 3.3.0003, 3.3.0004,
  3.3.0006, 3.3.0007
- ADRs desta Stage: [`../../adr/`](../../adr/) — prefixo `3_4_`
- Skills: `fastapi-thin-adapter`, `composition-root`, `hex-arch-python`,
  `import-linter-rules`

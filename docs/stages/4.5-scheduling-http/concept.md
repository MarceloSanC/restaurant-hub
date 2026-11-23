---
title: Concept — API do editor e consulta de escala
description: Borda HTTP do BC scheduling — rotas do editor, do calendário, das escalas anteriores e de "minha escala", o mapa de erros com as faixas, as permissões de escala em identity e o wiring que aposenta os campos provisórios da 4.4
when-use: Consultar ao iniciar a Fase 3B (technical) da Stage 4.5; antes de mexer nas rotas, nos schemas ou no mapa de erros de scheduling; antes de estender o mapa de papéis com permissão de escala
keywords: [concept, scheduling-http, scheduling, borda http, router, schemas, mapa de erros, permissões, minha escala, calendário, aceite de warn, publicar]
status: done
created_at: 2026-11-23
updated_at: 2026-11-23
stage_id: 4.5-scheduling-http
stage_title: API do editor e consulta de escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.4-scheduling-persistence, 3.10-login-link-management]
---

# Concept — Stage 4.5 — API do editor e consulta de escala

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **Rotas de scheduling** em `features/scheduling/adapters/inbound/http/` (router, schemas,
  dependências, mapa de erros), uma por use case da 4.3 — sete: criar a escala do período, ler a
  escala vigente com as violações, avaliar um lote ao vivo, publicar um lote com os aceites de
  `warn`, calendário de um recorte (dia/semana/mês), escalas anteriores e "minha escala" (§4.1).
- **Mapa de erros de scheduling** sobre as duas raízes do BC (`SchedulingError`,
  `SchedulingApplicationError`), com as faixas 404/409/422 e os corpos das recusas que carregam
  estado — inclusive o conflito com a vizinha que mudou (`changed_neighbour_id`, issue #199) e a
  função não habilitada na unidade (issue #209) (§6, ADR 4.5.0002).
- **As permissões de escala em identity**: os três valores que o port já usa (`view_schedule`,
  `manage_schedule`, `view_own_schedule`) viram membros de `Permission` e entram no mapa de
  papéis; a permissão tenant-wide da configuração de escala (`manage_schedule_settings`) nasce
  gravada para a 4.8 consumir (ADR 4.5.0001).
- **O adapter do `AccessGuard` de scheduling** em `features/scheduling/adapters/out/identity/`,
  sobre a fachada de acesso de identity, e o par nomeado scheduling → identity no contrato
  `bc-independence` (roadmap › nota de fechamento da 4.4, "A 4.5 herda").
- **Wiring** no composition root: os sete use cases sobre o guard novo, e a **remoção** dos três
  campos provisórios da 4.4 (`scheduling_schedules`, `scheduling_settings`,
  `scheduling_staff_read`; LAYOUT §6 › "Exceção provisória ao item 5").
- **Sinalização da demanda órfã** (função que deixou de valer na unidade depois de gravada,
  ADR 4.3.0005): cada demanda nas respostas diz se a função vale hoje na unidade (§7 D-ORPHAN).
- **e2e contra Postgres**: o fluxo do DoD, a matriz de autorização papel × rota e o oráculo de
  faixas.

### Fora do escopo (explicitamente)

- Editar a configuração de escala (calendário e validação) — Stage 4.8. Esta Stage só **grava** a
  permissão que a 4.8 consome; nenhuma rota a exige ainda.
- Notificação (4.6), imagem (4.7), auto-fill (Step 5), frontend.
- Trilha de auditoria exposta por rota (nenhum use case a lê).
- Rota que compõe "minha escala" de várias unidades numa chamada, e a rota que diz ao login as
  próprias unidades (§7 D-OWN; issue #258).
- Desativação de conta em identity (ADR 3.5.0003 §5) — §7 D-DEACT; issue #259.
- Notificação por e-mail e a permissão dela: o e-mail é efeito da publicação, sem permissão própria (§7 D-EMAIL); a 4.6 o implementa.
- Migration: nenhuma tabela muda.
- Texto humano de cada violação: a borda devolve códigos e medidas (§7 D-TEXT).

### Divergências declaradas

1. **Entrega em identity** (PIPELINE §4.2 #4, "sem deliverables em mais de um BC"): o enum
   `Permission`, o mapa de papéis e `TENANT_WIDE_PERMISSIONS`, com os testes deles. Expansão
   autorizada pelo sponsor (ADR 3.4.0006 §5) e prevista para esta Stage (ADR 4.1.0004
   §Implementation notes, "Lands in Stage 4.5 (role map entries in
   `features/identity/domain/value_objects/{permission, role}.py`"), como a 3.10 declarou a sua. A
   docstring da fachada de identity (`facade.py`, propriedade 3) muda junto: o argumento de que
   `provision_account` pode pular `required_permissions_for_role` porque criar `employee` exige só
   `manage_users` deixa de ser literal, e passa a valer pela propriedade que o pino de R17 trava
   (§7 D-OWNALL, CA15).
2. **Toque em application de scheduling** (PIPELINE §4.2 #1, camada-alvo), em dois pontos:
   - o `DemandResult` ganha um campo (`function_enabled_in_unit`) e o calendário passa a ler as
     funções habilitadas da unidade (§7 D-ORPHAN). Sem ele a borda não tem como sinalizar a demanda
     órfã, e a informação já é lida pelos use cases do editor (`load_staff(...,
     with_unit_functions=True)` em `run_batch`);
   - o port `AccessGuard` de scheduling ganha `authenticate(request)` e o `tenant_id` opcional
     (omitido = o tenant do ator), a forma do port de staff (§7 D-GUARD). A borda precisa autenticar
     e não conhece o tenant; os use cases continuam passando o tenant nomeado.
3. **Roadmap `arquivos_a_modificar` cita a app factory**; ela não muda: `create_app` itera o
   `HttpWiring` desde a 3.6 e registra o terceiro router sem conhecer o BC.

### Vínculo com o roadmap

Quinta Stage do **Step 4 — Escala manual publicável** (`roadmap.md` §Stage 4.5). É a primeira
superfície de runtime do BC: depois dela o gerente monta e publica a escala pela API e o
funcionário consulta a própria. Destrava a 4.6, a 4.7, a 4.8, a 6.1 e a 7.2.

## 2. Objetivo da Stage

Ao fim da Stage, a API real (Postgres) deixa o gerente montar a demanda, alocar, ver as violações
que o lote introduz, aceitar os avisos e publicar, e deixa o funcionário ler só a própria escala —
com cada rota autorizada por papel e por unidade, e toda recusa de scheduling respondendo com
status e corpo do mapa do BC.

## 3. Contexto e premissas

### Contexto

- A 4.3 entregou os sete use cases (cada um autoriza o próprio alvo — ADR 4.3.0002), os DTOs e os
  erros; a 4.4, os adapters Postgres, o adapter de staff e os três campos provisórios.
- O port `AccessGuard` de scheduling só tem `authorize(actor, permission, *, tenant_id, unit_id)`;
  "a autenticação é da borda (4.5)" (`access_guard.py` › docstring do módulo). Os valores das
  permissões já existem como `str` no port; o membro do enum e o mapa de papéis são desta Stage
  (ADR 4.3.0002 §Decision 2).
- O padrão de borda é o de staff (Stage 3.6) e de identity: router fino, Pydantic só na borda, ator
  do token, autenticar → validar → autorizar, autorização dentro do use case com a borda como
  defesa em profundidade (ADR 3.7.0001), 401/403 de identity com corpo constante (ADR 2.4.0001),
  mapa exaustivo por BC (ADR 3.9.0001), validação de identificador na borda (ADR 3.6.0002),
  instantes de parede sem offset (ADR 3.6.0003).

### Premissas

- O token carrega o sujeito e o tenant, não as unidades do ator
  (`IdentityGuard.authenticate_principal` › `AccessPrincipal(user_id, tenant_id)`).
- Identity responde 403 com corpo constante para unidade invisível e permissão negada
  (`authorize_at_boundary`, ADR 2.4.0001 §5); a borda de scheduling não traduz.
- O id da escala é UUID do servidor (`Uuid4Generator`); os de faixa, demanda e alocação vêm do
  cliente (ADR 4.3.0004).

### Dependências

- `4.4-scheduling-persistence`: adapters Postgres e `LocalStaffReadAdapter`; os três campos
  provisórios a remover.
- `3.10-login-link-management`: o vínculo de login que `list_members_of_user` lê para "minha
  escala" (D-EMP da 4.4: o funcionário vê a escala vigente).
- `4.3-scheduling-application` (transitiva): use cases, DTOs, erros e o port do guard.

## 4. Contratos

### Introduzidos

#### 4.1 Rotas (prefixo `/api/v1`; tenant do token, unidade no path)

| # | Método e caminho | Use case | Permissão | Sucesso |
|---|---|---|---|---|
| S1 | `POST /units/{unit_id}/schedules` | `create_schedule` | `manage_schedule` | 201, resumo |
| S2 | `GET /units/{unit_id}/schedules/{schedule_id}` | `get_schedule` | `view_schedule` | 200, escala + violações |
| S3 | `POST /units/{unit_id}/schedules/{schedule_id}/evaluations` | `evaluate_schedule` | `manage_schedule` | 200, avaliação |
| S4 | `POST /units/{unit_id}/schedules/{schedule_id}/publications` | `publish_schedule` | `manage_schedule` | 200, escala vigente |
| S5 | `GET /units/{unit_id}/calendar?first_day&last_day` | `get_calendar` | `view_schedule` | 200, calendário |
| S6 | `GET /units/{unit_id}/schedules?before&limit=10` | `list_past_schedules` | `view_schedule` | 200, lista de resumos |
| S7 | `GET /units/{unit_id}/my-schedule?first_day&last_day` | `get_my_schedule` | `view_own_schedule` | 200, turnos do ator |

S3 e S4 são `POST` sobre sub-recurso de ação e respondem **200**: a avaliação não cria nada, e a
publicação grava uma nova versão da mesma escala, sem URL própria (precedente: o registro de
indisponibilidade de staff, 200 e não 201). O resumo de S1 traz `schedule_id`, e S2 é o endereço
dele.

#### 4.2 Schemas (Pydantic, só em `schemas.py`)

- **Criação (S1)**: `{first_day}` (dia, `YYYY-MM-DD`). O `schedule_id` é do servidor e nenhum
  campo do request o aceita; campo desconhecido no request de topo é ignorado, como em staff.
- **Operação do lote** — união discriminada por `op`, uma variante por operação da 4.3
  (`enable_band`, `reschedule_band`, `redeclare_band_break`, `disable_band`, `declare_demand`,
  `change_demand_quantity`, `withdraw_demand`, `assign_employee`, `unassign_employee`,
  `declare_workload_counting`, `declare_allocation_break`), cada variante com `extra="forbid"`
  (precedente: as variantes aninhadas do perfil de jornada, errata do ADR 3.6.0003); os requests de
  topo seguem permissivos, como os de staff.
- **Lote**: `{expected_version, operations}` (S3) e `{expected_version, operations,
  acknowledgements}` (S4); até **500** operações e 500 aceites (§7 D-BATCH).
- **Aceite**: `{key: {policy, employee_id, demand_id, operational_days, assignment_ids}, observed,
  limit}` — a gerente devolve a `key` e a medida que viu (ADR 4.3.0001; concept 4.3 §5.7).
  `employee_id` e `demand_id` são anuláveis (a sobre-cobertura não tem registro; as políticas
  agregadas não têm demanda). O cliente **ecoa a `key` como a recebeu**: `operational_days` é
  comparado como tupla ordenada e a borda não reordena nem deduplica; `assignment_ids` é conjunto.
  `observed` e `limit` viajam como **texto** (campo `str` no schema), e o conversor da borda recusa o
  que não é número finito com `InvalidScheduleRequestError` (422, corpo de scheduling).
- **Violação na resposta**: `{policy, mode, employee_id, demand_id, operational_days,
  assignment_ids, observed, limit, key}`; `observed`/`limit` como texto decimal (precedente
  `weekly_hours`, ADR 3.6.0003 §Decision 2); `key` é a identidade de aceite (ADR 4.2.0002), que nas
  políticas agregadas não carrega alocações.
- **Escala**: `{summary: {schedule_id, unit_id, first_day, last_day, version}, bands: [{band_id,
  schedule_id, operational_day, start, end, break_minutes, demands: [{demand_id, job_function_id,
  job_function_name, function_enabled_in_unit, quantity, assignments: [{assignment_id,
  employee_id, display_name, counts_toward_workload, function_exception, break_minutes,
  worked_minutes}]}]}], violations}`.
- **Avaliação**: `{schedule: <Escala>, blocking, warnings}`.
- **Calendário**: `{first_day, last_day, schedules: [<resumo>], bands}`.
- **Minha escala**: `{first_day, last_day, shifts: [{schedule_id, band_id, assignment_id,
  employee_id, operational_day, start, end, job_function_id, job_function_name,
  worked_minutes}]}`.
- **Tempo**: dias em ISO `YYYY-MM-DD`; limites de faixa em ISO **sem offset**
  (`2026-12-07T08:00:00`), wall-clock da unidade (§7 D-TIME).

#### 4.3 Corpo de erro de scheduling

`{"detail": <mensagem>, "type": "scheduling_error", "code": <código>, ...}` — `code` é o nome da
classe em snake_case sem o sufixo `Error` (`schedule_version_conflict`), e os erros com estado
acrescentam campos (ADR 4.5.0002):

| Erro | Campos a mais |
|---|---|
| `ScheduleVersionConflictError` | `expected_version`, `current_version`, `changed_neighbour_id` (`null` quando a própria escala mudou) |
| `BlockingViolationsError`, `UnacknowledgedViolationsError` | `violations` (forma da §4.2) |
| `InactiveAllocationsInUseError`, `MissingStaffRecordsError` | `assignment_ids`, `count` |
| `JobFunctionNotEnabledInUnitError` | `job_function_id` |
| `IdentifierInUseError` | `id_type`, `value` |

#### 4.4 Permissões em identity (ADR 4.5.0001)

`Permission` ganha `VIEW_SCHEDULE`, `MANAGE_SCHEDULE`, `VIEW_OWN_SCHEDULE` (unit-scoped) e
`MANAGE_SCHEDULE_SETTINGS` (tenant-wide, em `TENANT_WIDE_PERMISSIONS`). Mapa de papéis, só o
acréscimo:

| Papel | + permissões de escala |
|---|---|
| `owner` | `view_schedule`, `manage_schedule`, `view_own_schedule`, `manage_schedule_settings` |
| `manager` | `view_schedule`, `manage_schedule`, `view_own_schedule` |
| `hr` | `view_schedule`, `view_own_schedule` |
| `employee` | `view_own_schedule` |
| `platform_admin` | — |

#### 4.5 O port do guard estendido e o adapter dele

- **Port** (`application/ports/out/access_guard.py`), na forma do port de staff (ADR 3.7.0001):
  - `authenticate(request: object) -> Actor` — novo; a autenticação é da borda, e o port a expõe
    para que a borda dependa dele e não de um protocolo próprio (LAYOUT §5);
  - `authorize(actor, permission, *, tenant_id: str | None = None, unit_id: str) ->
    AuthorizedScope` — o `tenant_id` passa a opcional: omitido, é o tenant do ator (ADR 0.0.0005
    cláusula 3). A unidade continua obrigatória. Lei nova **L-SG5**: com o tenant omitido, o escopo
    traz o tenant do ator; ator sem tenant é negado (nunca `""`). L-SG1 a L-SG4 ficam.
  - Os use cases não mudam: continuam passando o tenant nomeado.
- **Adapter** `features/scheduling/adapters/out/identity/local_access_guard.py` ›
  `LocalAccessGuard(access: IdentityAccessFacade, authenticate_request: Callable[[object],
  AccessPrincipal])`, sobre a fachada de acesso, como o de staff (ADR 0.0.0016).
- **Borda** `features/scheduling/adapters/inbound/http/dependencies.py` › `get_access_guard`
  (chave de override), `authenticated_actor`, os requisitos por rota, `validate_identifier` e
  `validate_creation_id`.

### Consumidos

- Use cases, DTOs e erros de scheduling (4.3); `AccessGuard`, `AuthorizedScope` e os três valores de
  permissão (`access_guard.py`, 4.3).
- `IdentityAccessFacade`, `AccessPrincipal`, `PermissionDeniedError` (`identity.application.facade`,
  issue #47); `IdentityGuard.authenticate_principal` (injetado pelo composition root).
- Adapters Postgres de scheduling e `LocalStaffReadAdapter` (4.4).

## 5. Invariantes e regras

1. **Tenant do token.** Nenhum schema aceita `tenant_id` ou alias, e todo command/query recebe o
   `tenant_id` de `AuthorizedScope.tenant_id` da autorização da borda (ADR 0.0.0005).
2. **Unidade do path.** A rota nunca lê `AuthorizedScope.unit_id` (ADR 3.6.0001): a unidade do
   command é a do path validado.
3. **Ordem autenticar → validar → autorizar → use case.** Autenticação por `Depends`; nenhum
   identificador cru chega ao guard (ADR 3.6.0002).
4. **Duas autorizações, a mesma decisão.** A borda autoriza a permissão da rota na unidade do path; o
   use case autoriza de novo com o ator (ADR 4.3.0002). A da rota é provada por teste de borda com
   dublê espião do guard (permissão e unidade pedidas por rota; o use case não é chamado quando o
   guard nega — CA14), porque na matriz e2e a do use case devolveria o mesmo 403; os testes da 4.3
   provam a do use case, e a matriz e2e prova a decisão de ponta a ponta.
5. **O "eu" de "minha escala" é o sujeito do token**; nenhum campo de pedido nomeia usuário,
   registro ou login (ADR 4.3.0002 §4).
6. **Mapa total**: toda subclasse concreta das duas raízes de scheduling tem status próprio no mapa
   (Gate 3, `tests/unit/test_status_map.py`), e o handler é registrado nas duas raízes (ADR
   3.9.0001 §4).
7. **401/403 são de identity, byte-idênticos**: scheduling não registra entrada 401/403 nem traduz
   exceção de identity (L-SG1).
8. **Nenhum provedor da borda entrega port de dados** a uma rota: os três campos provisórios saem do
   contêiner, e o teste de composition root de scheduling passa a cobrar os sete use cases e o guard.
9. **Instantes de parede sem offset**, nos dois sentidos; valor com offset é recusado (422), nunca
   convertido (ADR 3.6.0003 §Decision 3).
10. **Ids de criação em UUID canônico** (texto minúsculo com hífens); ids de referência e de path
    recusam vazio, só-espaço e NUL (422 de scheduling).

## 6. Casos de erro e exceções

Faixas por classe (ADR 4.5.0002; definição das faixas do ADR 3.4.0002 §4: 404 = recurso ausente no
endereço — a escala do path e, como `JobFunctionNotFoundError` de staff, o registro ou a função de
**outro agregado** que o corpo nomeia; 409 = conflito com estado gravado — chave já tomada no banco,
referência que impede remoção, estado de outro agregado no caminho; 422 = pedido ou conteúdo que viola
invariante, inclusive o **valor interno** da escala que o lote nomeia e não existe e a invariante do
agregado que o próprio lote quebra, como `OverlappingUnavailabilityError` em staff):

| Status | Erros |
|---|---|
| 404 | `ScheduleNotFoundError`, `StaffMemberNotFoundError`, `JobFunctionNotFoundError` |
| 409 | `ScheduleVersionConflictError`, `SchedulePeriodTakenError`, `IdentifierInUseError`, `InactiveStaffMemberError`, `JobFunctionNotEnabledInUnitError`, `InactiveAllocationsInUseError`, `MissingStaffRecordsError`, `ShiftBandInUseError`, `ShiftDemandInUseError` |
| 422 | `BlockingViolationsError`, `UnacknowledgedViolationsError`, `InvalidScheduleRequestError`, `InvalidIdentifierError`, `InvalidTimeRangeError`, `InvalidWeekdayError`, `InvalidDayCutoffError`, `InvalidSchedulePeriodError`, `InvalidDemandQuantityError`, `InvalidScheduleVersionError`, `InvalidAssignmentBreakError`, `DuplicateEntityIdError`, `DuplicateShiftBandError`, `DuplicateShiftDemandError`, `DuplicateAssignmentError`, `DuplicateAssignmentInBandError`, `ShiftBandNotFoundError`, `ShiftBandDayChangeError`, `TimeRangeOutsidePeriodError`, `ShiftDemandNotFoundError`, `AssignmentNotFoundError`, `InvalidValidationConfigError`, `InvalidEvaluationInputError` |

- **Recusa otimista** (`ScheduleVersionConflictError`, 409): `changed_neighbour_id == null` — a
  própria escala mudou; o cliente relê (S2) e refaz o lote. `changed_neighbour_id != null` — uma
  vizinha mudou e a escala editada não (`expected_version == current_version`); o cliente **reenvia o
  mesmo lote** sobre a mesma versão, e a nova avaliação enxerga a vizinha atual — o reenvio pode
  voltar 422 com violações novas de fronteira, ou com um aceite que já não cobre a medida que cresceu
  (ADR 4.4.0005 §Decision 3).
- **Bloqueio × aceite** (422): `code` distingue `blocking_violations` (só desfazer resolve) de
  `unacknowledged_violations` (reenviar com os aceites das `violations` do corpo).
- **Função não habilitada** (409, `job_function_not_enabled_in_unit`, com `job_function_id`): o lote
  declara demanda ou aumenta `N` de função que não vale na unidade; reduzir, retirar e mover passam
  (D1, ADR 4.3.0005).
- **Registro ausente** (409, `missing_staff_records`, com `assignment_ids`): staff não devolve um
  alocado (fail-closed, ADR 4.3.0003 §3). Sai também das leituras (S2 roda `run_batch` sobre a escala
  e as vizinhas; S5 lê os alocados do recorte) e trava a edição da escala e das vizinhas, porque o
  lote que desalocaria recusa antes de aplicar. Nenhuma ação do cliente resolve: o reparo é da issue
  #194, que tem de fechar antes de a edição ir a produção (nota de fechamento da 4.4 no roadmap; §10).
- **Mesma chave duas vezes no agregado** (422: `duplicate_shift_band`, `duplicate_shift_demand`,
  `duplicate_assignment`, `duplicate_assignment_in_band`): o lote é aplicado em memória (ADR
  4.3.0001 §1), e a faixa repetida, a demanda repetida e a pessoa duas vezes na faixa são invariantes
  do agregado que o conteúdo do lote quebra, como `OverlappingUnavailabilityError` em staff (ADR
  3.4.0002 §4).
- **Mesmo id de criação duas vezes no lote** (422, `duplicate_entity_id`): é conteúdo do pedido; o id
  que já existe na escala ou na vizinha é recusado antes, com `IdentifierInUseError` (409,
  `check_creation_ids`).
- **Identificador inválido** (422, `invalid_identifier`): só-espaço ou NUL no path; vazio, só-espaço
  ou NUL nos ids do corpo; id de criação fora do UUID canônico. Antes de autorizar. (Segmento de path
  vazio não chega à rota — o Starlette responde 404/405, limite medido do ADR 3.6.0002.)
- **Dia ou instante extremo** (422, `invalid_schedule_request`): dia fora de
  `0002-01-01`..`9998-12-31` em `first_day`, `last_day` ou `before`, e limite de faixa (`start`/`end`
  de `enable_band` e `reschedule_band`) fora dos mesmos anos. O período (7 dias), as vizinhas (±1 dia)
  e o dia operacional de um instante antes do corte (`OperationalCalendar.operational_day_of`, −1 dia)
  somam `timedelta`, e perto de `date.min`/`date.max` isso levanta `OverflowError` → 500.
- **Quantidade acima de 2.147.483.647** em `declare_demand` ou `change_demand_quantity` (422,
  `invalid_schedule_request`): o `INTEGER` do Postgres recusaria com `DataError` → 500 (finding do
  concept 4.4 §10).
- **Decimal malformado no aceite** (`observed`/`limit` não finito ou não numérico) → 422
  `invalid_schedule_request`, nunca 500 (o campo é `str` no schema; o conversor é da borda).
- **Corpo fora do schema** (tipo errado, `op` desconhecida, lote acima de 500) → 422 do framework,
  corpo constante `validation_error` (handler compartilhado).
- **Inalcançáveis por HTTP nesta Stage** (entrada por totalidade): `InvalidWeekdayError`,
  `InvalidDayCutoffError`, `InvalidValidationConfigError` (a configuração é da 4.8);
  `InvalidEvaluationInputError` e `InvalidScheduleVersionError` (insumo montado pelo use case,
  versão lida do banco).

## 7. Decisões técnicas relevantes

Os forks P foram delegados pelo sponsor à sessão (orquestração de 2026-11-23); cada um traz "P
delegado — opção, motivo". Critérios do sponsor: esqueleto escalável com implementação mínima;
fail-closed em regra de acesso.

### D-PERM — nomes, mapa de papéis e salvar = editar

- **O quê:** os três valores do port viram membros de `Permission`; `manage_schedule` cobre editar,
  avaliar, aceitar `warn` e publicar (sob F1 publicar é salvar — ADR 4.1.0001); mapa da §4.4.
- **Por quê:** ADR 4.1.0004 §Decision 1–4 fixa as três famílias e quem detém cada uma; o concept 4.3
  (divergência 9, D-PERM) já fixou os valores e "salvar = editar".
- **Fonte:** ADR 4.1.0004; ADR 4.3.0002 §Decision 2; domínio §4.
- **ADR:** [4.5.0001](../../adr/4_5_0001-scheduling-permissions-in-the-identity-role-map.md)

### D-OWNALL — `view_own_schedule` para todo papel do restaurante

- **O quê:** `owner`, `manager`, `hr` e `employee` detêm `view_own_schedule`.
- **Por quê:** [decision] P delegado — dar a todos os papéis do restaurante, motivo: (a) gerente e
  dono que trabalham na escala ganharam vínculo na 3.10 justamente para ver "minha escala"
  (roadmap §Stage 3.10 › "Descrição humana"); (b) "não se concede o que não se detém"
  (`required_permissions_for_role`) exige que quem cria `employee` detenha a permissão dele: sem
  isso, a criação e o convite de identity (`/users`, `/users/invitations`) negariam `employee` a
  `manager`, `hr` e `owner`. O login de funcionário de staff (R17) passa pela fachada
  (`provision_account`), que não aplica a regra (ADR 2.7.0001 §Decision 5) — ali o risco é o oposto,
  provisionar uma permissão que o criador não detém, e o pino de R17 passa a ser a propriedade "todo
  papel com `manage_staff` e `manage_users` detém o que `employee` detém" (CA15).
- **ADR:** 4.5.0001.

### D-CONFIG — a permissão da configuração tenant-wide

- **O quê:** `manage_schedule_settings`, tenant-wide (`TENANT_WIDE_PERMISSIONS`), só `owner`.
  Gravada agora, sem rota; a 4.8 a consome e estende o guard com alvo "tenant inteiro".
- **Por quê:** [decision] P delegado — só `owner`, motivo: fail-closed; a configuração vale para
  todas as unidades e o gerente só enxerga as suas (ADR 2.1.0001 eixo B), então concedê-la a ele
  deixaria um gerente mudar a regra de unidades que não vê — e, sendo tenant-wide, alargá-la a ele
  daria justamente esse alcance; por isso alargar exige decisão nova do sponsor, não é aditivo
  automático. Enquanto só o `owner` a detém, a entrada em `TENANT_WIDE_PERMISSIONS` não muda a
  decisão de acesso (o dono já dispensa a unidade, ADR 3.4.0008); ela classifica o **alvo** (o
  restaurante), que é o critério do conjunto. O roadmap pede que a 4.5 decida e grave (`roadmap.md`
  §Stage 4.8 › `contratos_consumidos`).
- **Consequência para a 4.8 (declarada):** o port do guard de scheduling exige unidade; a 4.8 o
  estende com alvo "restaurante inteiro" (mudança de port de application, como a desta Stage em
  D-GUARD). Quem **lê** a configuração e se a flag "sempre notificar" da 4.6 fica sob a mesma
  permissão são da 4.8 (candidata para a leitura: `view_schedule`).
- **ADR:** 4.5.0001.

### D-CREATE — `hr` deixa de criar `manager`

- **O quê:** com `manage_schedule` no `manager` e não no `hr`, a regra "não se concede o que não se
  detém" passa a negar a `hr` criar ou convidar `manager`. A matriz congelada de quem cria quem
  (`test_matriz_de_quem_cria_quem_nao_regride`) ganha baseline nova datada; nada mais muda nela.
- **Por quê:** [decision] P delegado — aceitar a consequência, motivo: fail-closed; a alternativa
  (excluir as permissões de escala da regra) deixaria o RH criar quem mexe na escala, contra a
  decisão do sponsor "apenas o gerente ou dono pode mexer na escala" (ADR 3.4.0006 §1, mantida pelo
  ADR 4.1.0004 §Decision 2).
- **O que isto quebra, declarado:** o princípio da matriz congelada ("crescer o vocabulário só pode
  tornar a exigência mais estrita, e mais estrita sobre permissões que o próprio criador ganhou no
  mesmo ato é neutro") deixa de valer pela primeira vez — o `hr` não ganha `manage_schedule`. O
  comentário de `role.py` (`manager` e `hr` "coincidem em identity") é reescrito: coincidem nas
  permissões de identity e de staff, e divergem na escala. O overview (RH como variante de gerente)
  segue verdadeiro. O PR leva a decisão em destaque para o sponsor.
- **ADR:** 4.5.0001.

### D-ERR — mapa de erros e corpos

- **O quê:** faixas da §6; corpo da §4.3, com `code` e os campos de estado; 409 na recusa otimista,
  com `changed_neighbour_id`.
- **ADR:** [4.5.0002](../../adr/4_5_0002-scheduling-error-map-and-refusal-bodies.md)

```
[decision:E] D-ERR-409 — status da recusa otimista (versão da escala ou da vizinha)
Escolha: 409 Conflict, corpo com expected_version, current_version e changed_neighbour_id · Alternativas: 412 Precondition Failed; 422
Base: RFC 9110 §15.5.10 "The 409 (Conflict) status code indicates that the request could not be completed due to a conflict with the current state of the target resource." (o mesmo §15.5.10 dá o exemplo de versionamento: "the origin server might use a 409") · RFC 9110 §15.5.13 (412 é de condição em campo de header; a versão aqui vai no corpo)
Verificado: parcial→corrigido (evidence-verifier, 2026-11-23: trecho da RFC 9110 trocado pelo literal)
Configuração candidata: nenhuma · Reversível: não (contrato OpenAPI consumido pelo cliente)
```

```
[decision:C] D-ERR-BANDS — faixa de cada erro de scheduling
Escolha: a definição de faixas de staff — 404 recurso ausente no endereço ou de outro agregado que o corpo nomeia (como JobFunctionNotFoundError de staff), 409 conflito com estado gravado, 422 conteúdo que viola invariante, inclusive valor interno ausente e invariante do agregado que o lote quebra (tabela da §6) · Alternativas: violação bloqueante e aceite pendente em 409; os Duplicate* do agregado em 409 · Degrau (C): 1
Base: ADR 3.4.0002 §4 (definição das faixas, consumida por STAFF_ERROR_STATUS em staff/adapters/inbound/http/error_handlers.py; "OverlappingUnavailabilityError is 422, not 409. It is an aggregate invariant violated by the period the client sent")
Verificado: parcial→corrigido (evidence-verifier sustentou a definição; o Checkpoint A apontou que a tabela punha quatro Duplicate* em 409 contra ela, e eles foram para 422)
Configuração candidata: nenhuma · Reversível: não (contrato OpenAPI)
```

```
[decision:C] D-ERR-CODE — como o cliente distingue recusas da mesma faixa
Escolha: campo code (nome da classe em snake_case sem "Error") no corpo de scheduling, ao lado de type="scheduling_error" · Alternativas: só detail (texto); status distinto por recusa · Degrau (C): 4
Base: ADR 3.6.0002 (discriminador type no corpo de erro de staff); staff/adapters/inbound/http/error_handlers.py › STAFF_ERROR_TYPE
Verificado: sustenta (evidence-verifier, 2026-11-23)
Configuração candidata: nenhuma · Reversível: não (contrato OpenAPI)
```

### D-TIME — forma dos dois regimes de tempo na borda

```
[decision:C] D-TIME — forma dos instantes de faixa e dos dias na borda HTTP
Escolha: limites de faixa em ISO 8601 sem offset (wall-clock da unidade); valor com offset recusado com 422 pelo domínio, nunca convertido; dias em YYYY-MM-DD; nenhum instante absoluto exposto (a trilha não tem rota) · Alternativas: dia + hora local separados; instante UTC com offset · Degrau (C): 1
Base: ADR 3.6.0003 §Decision 3 "start and end travel without offset. A value carrying Z or an offset is parsed as tz-aware and rejected" · ADR 4.1.0007 (instantes ingênuos de minuto inteiro)
Verificado: sustenta (evidence-verifier, 2026-11-23)
Configuração candidata: nenhuma · Reversível: não (contrato OpenAPI)
```

### D-IDS — validação de identificador e ids de criação

```
[decision:C] D-IDS — validação dos identificadores na borda de scheduling
Escolha: path, query e ids de referência do corpo recusam vazio, só-espaço e NUL (InvalidIdentifierError de scheduling, 422) antes de autorizar; ids de criação (band_id de enable_band, demand_id de declare_demand, assignment_id de assign_employee) exigem UUID canônico · Alternativas: validar só o NUL; aceitar qualquer texto como id de criação · Degrau (C): 1
Base: ADR 3.6.0002 (validador de identificador na borda, ordem validar → autorizar) · ADR 4.3.0004 §Negative "Clients must generate good ids (UUID canonical format at the boundary — finding 4.5)" (o finding aponta; a regra é decidida aqui) · concept 4.4 §10 (NUL e INTEGER: valores que o fake aceita e o Postgres recusa)
Verificado: parcial→corrigido (evidence-verifier, 2026-11-23: o trecho do ADR 4.3.0004 citado por inteiro e lido como finding)
Configuração candidata: nenhuma · Reversível: sim (afrouxar é aditivo)
```

### D-QTY — teto da quantidade

```
[decision:E] D-QTY — teto da quantidade-alvo da demanda na borda
Escolha: recusar quantity > 2147483647 com InvalidScheduleRequestError (422) · Alternativas: deixar o Postgres recusar (500); teto de negócio arbitrário
Base: PostgreSQL docs §8.1.1 Integer Types — integer "-2147483648 to +2147483647" · scheduling/adapters/out/postgres/tables.py (coluna quantity Integer)
Verificado: sustenta (evidence-verifier, 2026-11-23)
Configuração candidata: nenhuma · Reversível: sim
```

### D-BATCH — teto do lote

```
[decision:C] D-BATCH — tamanho máximo do lote e dos aceites
Escolha: até 500 operações e 500 aceites por requisição (422 do framework acima disso) · Alternativas: sem teto · Degrau (C): 2
Base: ADR 2.2.0002 (fail-closed) · premissa não medida: uma semana de escala de uma unidade cabe com folga (7 dias × faixas × funções × pessoas); o custo de 500 operações não foi medido (ADR 4.3.0001: "acceptable at pilot volume")
Verificado: sustenta (evidence-verifier, 2026-11-23)
Configuração candidata: teto por configuração · Reversível: sim
```

### D-GUARD — o port do guard ganha `authenticate` e tenant opcional; sem promoção a `shared/`

- **O quê:** o port de scheduling passa à forma do de staff (§4.5): `authenticate` e o `tenant_id`
  opcional (o do ator), com a unidade ainda obrigatória e a lei L-SG5; o adapter de saída
  `LocalAccessGuard` o implementa sobre a fachada de acesso (ADR 0.0.0016), e a borda depende do port
  (LAYOUT §5 — ports de saída moram em `application/ports/out/`). O `AccessGuard` **não** é promovido
  a `shared/`.
- **Por quê:** a borda precisa autenticar e não conhece o tenant; o precedente de staff resolve as duas
  no port de application (ADR 3.7.0001; `staff/application/ports/out/access_guard.py` ›
  `authenticate`), e um protocolo declarado no adapter de entrada seria forma nova sem regra no
  LAYOUT. A promoção a `shared/` continua recusada: os dois ports diferem (unidade obrigatória e o
  sujeito no escopo em scheduling; unidade opcional e sem sujeito em staff) — dois contratos, não um
  reutilizado (LAYOUT §4); o ADR 4.3.0002 escolheu o port por BC.
- **ADR:** [4.5.0003](../../adr/4_5_0003-scheduling-http-edge-shape.md)

### D-OWN — "minha escala" por unidade

- **O quê:** S7 responde por unidade; compor as unidades do ator numa chamada e a rota que lista as
  unidades do próprio login ficam para uma issue nova.
- **Por quê:** [decision] P delegado — rota por unidade, motivo: o token não carrega as unidades
  (`AccessPrincipal`), e compô-las exige uma leitura nova na fachada de identity (inventário
  facade-only, ADR 0.0.0020) ou uma leitura de staff por login atravessando unidades (D-USERID da
  4.4) — duas entregas fora da borda. A rota por unidade é a primitiva que a composta reusa. A
  divergência 10 do concept 4.3 fica reendereçada à issue #258.
- **Limite declarado:** nenhuma rota devolve hoje ao login as próprias unidades; o funcionário real só
  chama S7 com o `unit_id` obtido por fora (do gerente, ou do cliente que a #258 vai servir). O DoD
  vale pela API com a unidade conhecida; para o piloto com funcionários, a #258 é pré-requisito, como
  a #194 é para a edição.
- **ADR:** 4.5.0003.

### D-ORPHAN — sinalizar a demanda órfã

- **O quê:** `DemandResult` ganha `function_enabled_in_unit: bool`; os mapeadores o preenchem com as
  funções habilitadas da unidade que o use case já leu (editor), e o calendário passa a lê-las
  (`with_unit_functions=True`). A borda o expõe em toda demanda.
- **Por quê:** [decision] P delegado — campo por demanda, motivo: a demanda órfã "fica, não bloqueia
  edição alheia e aparece como demanda descoberta" (roadmap, nota de 2026-11-23); só o servidor sabe
  a habilitação no instante da leitura, e o cliente cruzando com a rota de funções de staff faria duas
  leituras sem atomicidade e exigiria `manage_job_functions` de quem só lê a escala. A alternativa
  (uma violação nova) exigiria política no avaliador (camada de domínio, Stage 4.2).
- **ADR:** 4.5.0003.

### D-TEXT — texto das violações e UX do lote

- **O quê:** a borda devolve `policy`, `mode`, sujeito, dias e medida; não monta frase. A API é por
  lote; "publicar acumulado × gravar a cada ação" é escolha do cliente (lote de um). A divergência
  de intervalo, a marca `function_exception` e o D3 (desalocar inativos no mesmo lote) ficam
  expressos pelos campos e pelas operações existentes.
- **Por quê:** a `Violation` não tem texto por desenho (concept 4.2 §5.12, "a mensagem é da borda"),
  e o projeto não tem frontend nem i18n; um texto em PT no servidor seria a primeira string de UI da
  API. Código + medida é o contrato que o cliente traduz. D-SAVE (concept 4.3) já faz a forma servir
  as duas UX.
- **ADR:** 4.5.0003.

### D-DEACT — desativação de conta (ADR 3.5.0003 §5)

- **O quê:** a Stage não cria desativação de conta. "Minha escala" lê só registros **ativos**
  vinculados ao login (`get_my_schedule` › `if m.active`), então o desligado autentica e recebe
  vazio; o e2e trava isso (CA3).
- **Por quê:** [decision] P delegado — não desativar aqui e abrir issue de identity, motivo: o
  sponsor recusou desativar a conta no desligamento (ADR 3.5.0003 Alt. B; ADR 3.8.0001 Alt. G) e quer
  que a pessoa veja a própria informação depois; o corte é estrutural pelo registro (ADR 3.5.0003 §3,
  "self-service goes through the employee record, which is `active=False`"). Uma migration de
  identity sai do recorte da Stage. O ADR 3.5.0003 §5 ganha nota datada registrando o adiamento e o
  novo dono, a issue #259, onde está a decisão que falta em identity.

### D-EMAIL — e-mail como efeito, sem permissão própria

- **O quê:** a notificação da 4.6 é efeito de `publish_schedule`, sob `manage_schedule`; não ganha
  permissão própria. Fecha o último item da lacuna do doc de domínio §4 ("e-mail como efeito sem
  permissão própria").
- **Por quê:** o roadmap a põe como "hook de notificação" em `publish_schedule` (§Stage 4.6 ›
  `arquivos_a_modificar`), e o doc de domínio §3.8 diz que o e-mail "é **efeito** da publicação, não
  parte do agregado"; quem publica já decide. A flag "sempre notificar" é configuração do restaurante
  (4.6/4.8, D-CONFIG).

### Notas datadas nos ADRs que esta Stage estende

ADR 3.4.0006 §3 e ADR 4.1.0004 §Decision 4 (`view_own_schedule` também para `hr`, `manager` e
`owner`), ADR 3.5.0003 §5 (D-DEACT, #259), ADR 2.7.0001 §Decision 5 (o argumento de
`provision_account` passa a valer pela propriedade de CA15) e ADR 4.3.0002 §Decision 1 (o port ganha
`authenticate` e o tenant opcional; L-SG2 vale para o tenant pedido, L-SG5 para o omitido) ganham nota
datada no commit `conceptual approved`. A docstring do port (`access_guard.py`) é reescrita na Task
que o estende.

## 8. Integrações

### Internas

- **identity**: fachada de acesso (`IdentityAccessFacade`) e `authenticate_principal`; enum e mapa de
  papéis.
- **staff**: rotas de staff usadas pelo e2e para semear função, funcionário e login (R17).
- **Stages seguintes**: a 4.8 consome `manage_schedule_settings` e o router; a 4.6 e a 4.7 penduram
  rotas no mesmo router.

### Externas

- Nenhuma.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Matriz e2e cara (finding da 3.6: 162 casos, ~3 min) | M | M | Matriz papel × rota com 7 rotas e um cenário semeado por teste só onde há escrita |
| Permissão nova muda quem cria quem em identity | A | A | D-CREATE explícito; matriz congelada com baseline datada; pino de R17 reescrito como propriedade |
| Campo provisório removido quebra teste da 4.4 | A | B | A Task do wiring reescreve `test_composition_root_scheduling.py` no mesmo commit |
| Mensagem com carga horária dispara a regra 11 do `check_layout` | B | B | Nenhum módulo de exceção muda; mensagens novas ficam no adapter |
| Corpo de recusa vaza registro invisível | B | A | Nenhum campo nomeia registro inativo ou ausente — só ids de alocação (ADR 4.3.0001 §5); `employee_id` de violação só de registro ativo, que o editor já vê |
| Registro removido em staff trava leitura e edição da escala e das vizinhas (`missing_staff_records`) | M | A | Sem ação de cliente; a #194 tem de fechar antes de a edição ir a produção (pré-requisito declarado, como na nota da 4.4) |
| Funcionário não descobre a própria unidade | A | M | #258 pré-requisito do piloto com funcionários (D-OWN) |

## 11. Critérios de aceitação

- [ ] **CA1 (DoD).** e2e contra Postgres: o gerente cria a escala, avalia um lote com demanda e
      alocações e vê as violações introduzidas, publica sem aceite e recebe 422
      `unacknowledged_violations`, publica com os aceites e recebe 200 com a `version` igual a 1 + o
      número de operações efetivas do lote (cada mutação soma 1, ADR 4.1.0001 §2), e o funcionário com
      login lê em S7 só os próprios turnos.
- [ ] **CA2.** Matriz e2e papel × rota (S1–S7) para `owner`, `manager` membro, `manager` não membro,
      `hr` membro, `employee` membro, `employee` não membro, dono de outro tenant e `platform_admin`:
      permitido onde a §4.4 concede, 403 de identity com corpo constante no resto.
- [ ] **CA3.** "Minha escala" de um funcionário não traz turno de outro registro alocado na mesma
      faixa; um registro **alocado no recorte** e depois desligado, com novo login (o desligamento
      revoga as sessões), recebe 200 com `shifts: []`.
- [ ] **CA4.** Toda subclasse das duas raízes de scheduling tem entrada no mapa com o status da §6, e
      o handler está registrado nas duas raízes (`test_status_map.py` com scheduling em
      `_COM_BORDA_HTTP`).
- [ ] **CA5.** Recusa otimista: 409 com `expected_version` e `current_version` diferentes e
      `changed_neighbour_id: null` quando a própria escala mudou (e2e, duas publicações sobre a mesma
      versão); 409 com `changed_neighbour_id` e as duas versões iguais quando a vizinha mudou (teste de
      borda com dublê de use case que levanta o erro; o entrelace real é provado pelo teste de conduta
      da 4.4).
- [ ] **CA6.** `JobFunctionNotEnabledInUnitError` responde 409 com `job_function_id`; em S2 e em S5, a
      demanda de função habilitada vem com `function_enabled_in_unit: true` e a gravada antes de staff
      estreitar a função vem com `false` (e2e).
- [ ] **CA7.** Só-espaço ou NUL no `unit_id`/`schedule_id` do path, vazio/só-espaço/NUL nos ids do
      corpo e id de criação fora do UUID canônico respondem 422 `invalid_identifier` sem chamada a
      `authorize`; quantidade acima do `INTEGER` em `declare_demand` e em `change_demand_quantity`,
      decimal malformado no aceite, dia extremo e limite de faixa extremo respondem 422 de
      scheduling, nunca 500.
- [ ] **CA8.** Limite de faixa com offset (`Z`) responde 422 de scheduling; a resposta não tem offset.
- [ ] **CA9.** Nenhum schema de request tem `tenant_id`, `restaurant_id` ou `user_id`; nenhuma rota lê
      `AuthorizedScope.unit_id`.
- [ ] **CA10.** O composition root não tem os três campos provisórios; os sete use cases e o guard
      estão montados sobre os adapters Postgres e a fachada de acesso, e todo `_get_*` do router tem
      override.
- [ ] **CA11.** Mapa de papéis com o conteúdo exato da §4.4; `TENANT_WIDE_PERMISSIONS` =
      {`manage_job_functions`, `manage_schedule_settings`}; quem-cria-quem muda só em `hr` →
      `manager`.
- [ ] **CA12.** O adapter do guard e o fake cumprem L-SG1 a L-SG5 (unit, o adapter sobre a fachada
      real com dublê do authorizer), e o par scheduling → identity é o único import novo entre BCs
      (`bc-independence`).
- [ ] **CA13.** No fechamento da Stage, com a marca canônica: as linhas da tabela de lacunas do doc de
      domínio §6 endereçadas à 4.5 — "4.3/4.5" (UX do lote), "4.3" (unidades do ator → #258), "4.4 /
      4.5" (status e corpo da recusa; forma na borda), "4.5" (nomes, salvar × editar, config
      tenant-wide, promoção do guard, comentário de `role.py`), "4.5" (#209) — e as marcas do corpo:
      §4 (lacuna da 4.5, inclusive "e-mail como efeito"), §3.3 (nota de 2026-11-23, #209), §3.5
      ("e **4.5** (status/corpo da recusa)"), §3.9 (a persistida "da 4.4/4.5" e a forma na borda),
      §3.10.2 ("a 4.5 é o segundo consumidor … e decide"), a nota de §6 sobre a divergência de
      intervalo ("perguntar ao editor … é da borda") e a nota de 2026-11-02 de §6 ("a 4.5 compõe as
      unidades" → #258).
- [ ] **CA14.** Teste de borda por rota (S1–S7) com dublê espião do guard: a rota pede a permissão da
      §4.1 na unidade do path, sem `tenant_id`; com o guard negando, o use case não é chamado.
- [ ] **CA15.** Teste de propriedade em identity: todo papel que detém `manage_staff` e `manage_users`
      detém `required_permissions_for_role(EMPLOYEE)` (substitui o pino de R17 de igualdade).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida?
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido? (não há)
- [x] Decisões com alternativa real descartada têm ADR escrito? (4.5.0001–0003)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)?
- [x] Stage cabe em ~3–12 Tasks?
- [x] Riscos críticos têm mitigação plausível?
- [x] As heranças da 4.4 (guard, par do `bc-independence`, wiring, campos provisórios, forma dos
      instantes, NUL e `INTEGER`), da #199 e da #209 têm destino nesta Stage?

## 13. Questões em aberto

Nenhuma crítica. Reendereçadas a issues novas: "minha escala" composta e as unidades do próprio
login (D-OWN); desativação de conta no gatilho do ADR 3.5.0003 §5 (D-DEACT).

## 14. Referências

- [`../../roadmap.md`](../../roadmap.md) — §Stage 4.5; notas de 2026-11-16, 2026-11-22 e 2026-11-23
- [`../../domain/scheduling/shift-scheduling.md`](../../domain/scheduling/shift-scheduling.md) — §3.7, §3.9, §4, §6
- Concepts 3.6, 4.3, 4.4; ADRs 0.0.0005, 0.0.0016, 2.4.0001, 3.4.0002, 3.6.0002, 3.6.0003, 3.9.0001,
  4.1.0004, 4.3.0001, 4.3.0002, 4.3.0004, 4.3.0005, 4.4.0005
- ADRs desta Stage: 4.5.0001, 4.5.0002, 4.5.0003
- RFC 9110 §15.5.10 e §15.5.13; PostgreSQL docs §8.1.1

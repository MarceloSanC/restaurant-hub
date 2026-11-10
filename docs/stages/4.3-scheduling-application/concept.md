---
title: Concept — Use cases da escala
description: A camada application do BC scheduling — sete use cases (criar, avaliar, publicar, ler a escala, calendário, escalas anteriores, minha escala), o protocolo de publicação com aceite consciente sobre o antes × depois da avaliação, a autorização em cada use case e os quatro ports de saída que a 4.4 implementa
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; antes de acrescentar use case, operação de edição, port ou regra de aceite no BC scheduling; quando a 4.4 (persistência), a 4.5 (HTTP), a 4.6 (e-mail) ou o Step 5 consumirem estes contratos
keywords: [concept, scheduling-application, use-case, publicar, avaliar, aceite-consciente, violacao-introduzida, lote-de-operacoes, versao, concorrencia-otimista, trilha-de-auditoria, staff-read-port, access-guard, minha-escala, calendario, escalas-anteriores, reconciliacao-na-leitura]
status: done
created_at: 2026-10-21
updated_at: 2026-11-01
stage_id: 4.3-scheduling-application
stage_title: Use cases da escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.2-validation-policies]
---

# Concept — Stage 4.3 — Use cases da escala

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e as decisões que fecham as
> lacunas endereçadas a ela. O plano executável fica no [`technical.md`](./technical.md).
>
> **Base teórica obrigatória:** este concept **aplica** a teoria de
> [`shift-scheduling.md`](../../domain/scheduling/shift-scheduling.md) (`accepted`) e os ADRs
> 4.1.0001–4.1.0012 e 4.2.0001–4.2.0002 — consome, não reabre. O agregado é o da Stage 4.1
> ([`concept.md`](../4.1-scheduling-domain/concept.md)); o avaliador é o da 4.2
> ([`concept.md`](../4.2-validation-policies/concept.md)).
>
> **Lacunas que chegam a esta Stage** (doc §6; §7 dos technicals da 4.1 e da 4.2; §7 do technical
> da 3.7 e os dois findings anexados à issue #72): unidade de salvamento; protocolo do aceite;
> re-pergunta quando a medida piora; em que escala se grava o aceite da virada; completude do
> quadro no insumo; DTO próprio e consulta em lote do `StaffReadPort`; staff como provedor
> (fachada × use cases); ator → registros ("minha escala"); calendário sobre várias escalas;
> mudança de dia de início/corte com escalas existentes; limpar ou não as alocações futuras no
> desligamento; Stage em que staff passa a consultar o port reverso; instante de fora do domínio
> (`operational_day_of`); `change_demand_quantity` com o mesmo N; violação induzida por mudança de
> staff; o padrão do ADR 3.7.0001 em scheduling. Todas fecham em §7. **Três** eram de produto (D1,
> D3; D2 re-triada para convenção) e foram respondidas por delegação do sponsor, ratificadas em
> 2026-11-01; as demais foram resolvidas por evidência interna ou convenção (skill
> `evidence-resolution`), com o degrau registrado.

## 1. Escopo

### Dentro do escopo

- **Sete use cases** (os ports primários — LAYOUT §5, ADR 0.0.0006), um por arquivo em
  `features/scheduling/application/use_cases/`:
  - `create_schedule` — cria a escala de uma unidade para um período alinhado ao calendário do
    restaurante (fotografado na criação);
  - `evaluate_schedule` — aplica, em memória, um lote de operações de edição e devolve a escala
    resultante com as violações, separando as **introduzidas** pela mudança (a avaliação ao vivo);
  - `publish_schedule` — o mesmo lote, com a versão vista pelo editor e os aceites: recusa o que
    introduz `block`, pede aceite do que introduz `warn`, e grava (salvar = publicar);
  - `get_schedule` — a escala vigente com as violações atuais (a tela do editor e a leitura do RH);
  - `get_calendar` — as faixas de um recorte de dias (dia/semana/mês), através das escalas que ele
    cruza;
  - `list_past_schedules` — as escalas anteriores a um dia, como referência;
  - `get_my_schedule` — as alocações do próprio ator numa unidade.
- **O protocolo de publicação** (§5.5–§5.10): lote de operações nomeadas aplicado atomicamente,
  avaliação antes × depois, violação introduzida, aceite por `key` + medida, no-op, trilha.
- **Quatro ports de saída** em `application/ports/out/`: `ScheduleRepository`,
  `ScheduleConfigRepository`, `StaffReadPort` e `AccessGuard` (de scheduling — divergência 2), com
  as leis nas docstrings.
- **DTOs** (`dtos/{commands,queries,results}.py`), com os mapeadores de result num sítio só
  (`scripts/check_layout.py` regras 7 e 8).
- **Erros da application** (`application/errors.py`), filhos de `SchedulingError`.
- **Contrato de pureza** `scheduling-application-purity` no `.importlinter` — previsto desde a
  4.1 para "o primeiro use case".
- **Fakes** dos quatro ports em `tests/fakes/features/scheduling/`, **suítes de lei** dos ports
  de dados em `tests/contract/features/scheduling/` (só o fake roda nesta Stage; a 4.4 acrescenta
  o adapter real à parametrização — precedente 3.5) e testes unitários dos use cases com fakes.
- **No-op de `change_demand_quantity` no domínio** (D2): duas linhas em `Schedule`, com errata
  datada no concept da 4.1.

### Fora do escopo (explicitamente)

- **Persistência** (tabelas, migration, mapper, a trilha de auditoria no banco, a checagem de
  versão em SQL), o **adapter** do `StaffReadPort` (e a fachada de staff que ele consumir) e o
  **wiring** no `composition_root` — Stage 4.4.
- **HTTP** — rotas, schemas, status das recusas, o texto de cada violação, o membro das
  permissões no enum de identity e o mapa de papéis, a autenticação — Stage 4.5.
- **E-mail** (4.6), **imagem** (4.7), **auto-preenchimento** (Step 5).
- **Editar a configuração do restaurante** (validação, dia de início, corte): nenhum bloco do
  roadmap lista o use case de escrita — [finding] para a 4.5 (§13). A 4.3 só **lê** a
  configuração.
- **O port de fuso da unidade** (ADR 4.1.0005): nenhum use case desta Stage precisa do "agora" da
  unidade (§7 D-NOW) — nasce com o primeiro consumidor.
- **A guarda de remoção definitiva** (port de consulta reverso em staff, ADR 4.1.0006 §3) — 4.4
  (§7 D-REVERSE).
- **Página de histórico de funcionários**, cópia de escala anterior, troca de turno — evolução
  (doc §5).

### Vínculo com o roadmap

Terceira Stage do **Step 4 — Escala manual publicável**: entrega a parte "editar demanda e
alocações com avaliação ao vivo, aceitar warn, publicar, consultar" do resultado de negócio, sem
I/O real. Ver `roadmap.md` §"Stage 4.3 — `4.3-scheduling-application`" e `overview.md` §3
("Validações parametrizáveis… Avisos ao vivo… o editor corrige ou aceita conscientemente";
"salvar = publicar"; "funcionário com login consulta a própria escala"; "Fácil visualização das
escalas anteriores ao montar a nova").

### Divergências declaradas em relação ao bloco 4.3 do roadmap

1. **Use cases.** O bloco lista `{create_schedule, update_demand, assign_employee,
   evaluate_schedule, publish_schedule, get_calendar, list_past_schedules, get_my_schedule, ...}`.
   Sob salvar = publicar (ADR 4.1.0001 §1) não há "publicar" separado de "editar": as 11 mutações
   do agregado viram **operações** de um lote que `evaluate_schedule` avalia e
   `publish_schedule` grava (§7 D-SAVE). Entra `get_schedule` (a leitura da escala com versão e
   violações, que o editor precisa para editar). `update_demand` e `assign_employee` não existem
   como use case: são as operações `DeclareDemand`/`ChangeDemandQuantity`/`WithdrawDemand` e
   `AssignEmployee`/`UnassignEmployee`.
2. **Contratos introduzidos.** Além dos três ports do bloco, entra o `AccessGuard` **de
   scheduling** (§7 D-AUTH): a application autoriza o próprio alvo, como a 3.7 fez em staff.
3. **`arquivos_a_modificar` deixa de ser `[]`:** `.importlinter` (contrato de pureza da
   application), `tests/unit/test_status_map.py` (piso de contagem dos erros do BC),
   `tests/unit/test_check_layout.py` (a igualdade exata das escritas de repositório da regra 10
   ganha `ScheduleRepository.add`/`save`), o domínio da
   4.1 (D2: `schedule.py` e o teste da lei de no-op), a errata datada no concept da 4.1, a nota
   datada no doc de domínio (D1) e o roadmap.

### Divergências declaradas em relação ao doc de domínio e aos ADRs

4. **Invariantes de §3.5, §3.6.6, §3.6.7 e §3.6.8 valem para o que a escala introduz** — confirmado
   (§7 D1): a violação induzida por mudança em staff (férias/indisponibilidade lançada, função
   retirada, carga contratada editada, recontratação que faz reaparecer alocações antigas — e com
   elas excedente sem aceite na trilha) aparece
   ao vivo e não trava edição alheia a ela. A nota datada da 4.2 no doc (§6) já o antecipava; a
   desta Stage registra a decisão. A **segunda fonte** da mesma classe — uma configuração de
   validação alterada depois — recebe o mesmo tratamento (pré-existente, mostrada, nunca
   bloqueante numa mudança que não a introduziu), e é requisito declarado para a Stage que criar a
   edição da configuração.
5. **ADR 4.1.0005, Implementation notes** ("a read port in scheduling (4.3)"): o port de fuso
   **não** nasce aqui (§7 D-NOW). A forma dele e a Stage da coluna `Unit.timezone` continuam
   abertas, com o primeiro consumidor.
6. **ADR 4.1.0006 §3** previa a guarda reversa "the Stage that wires it is a concept gap
   (4.3/4.4)": fica na **4.4** (§7 D-REVERSE).
7. **ADR 3.7.0001 §3** ("the returned `AuthorizedScope` is not read by any use case") é adotado
   para o **endereço**: o use case opera no alvo do command, não no escopo. A divergência é que
   esta Stage **lê** do escopo o `user_id` (o "quem" da trilha e o "eu" de "minha escala") — não
   como endereço, mas como o sujeito autenticado que o ADR 0.0.0005 manda derivar do token. O
   modelo de ameaça do 3.7.0001 continua valendo: o guard não autentica o ator, logo "ninguém
   nomeia usuário alheio" vale hoje só para o driver HTTP; o resto é [finding] da Stage que criar
   o primeiro driver não-HTTP (o mesmo finding da 3.7).
8. **Concept 4.1 §5.16 / CA11b** enumerava **quatro** mutações idempotentes; passa a **cinco**
   (§7 D2), com errata datada no concept da 4.1 (precedente: errata datada em concept `done`,
   `docs/stages/3.2-staff-application/concept.md`).
9. **ADR 4.1.0004 › "Permission names (VIEW_SCHEDULE, MANAGE_SCHEDULE, VIEW_OWN_SCHEDULE, …)"** — *"Permission names (`VIEW_SCHEDULE`, `MANAGE_SCHEDULE`,
   `VIEW_OWN_SCHEDULE`, …), whether "save" and "edit" are one permission, and whether the
   tenant-wide validation configuration needs its own permission are gaps for the Stage 4.5
   concept"* — e o doc §3.10.2/§4 (promoção do `AccessGuard` na 4.5). Esta Stage fixa os **valores**
   das três permissões e "salvar = editar = `manage_schedule`" porque os use cases autorizam desde o
   primeiro commit (finding 2 da issue #72, ADR 3.7.0001); o membro do enum, o mapa de papéis e a
   permissão da configuração continuam da 4.5. Renomear é barato (três constantes).
10. **Doc §3.7:705** (*"minha escala" cobre **todos** os registros do ator, cada um na sua
    unidade*): o use case responde **por unidade**; a 4.5 compõe as unidades do ator. A fonte das
    unidades é a lista de vínculos (memberships) do ator em identity, entregue à borda pelo
    token/sessão — e vínculo de acesso não implica registro na unidade (o use case devolve vazio
    onde não há registro). Requisito declarado para a 4.5.
11. **Doc §3.5:394** (*"Toda mutação gera entrada de auditoria com quem/quando e incrementa a
    versão"*) e DoD da 4.4: cada operação efetiva incrementa a versão e é registrada, em ordem, na
    `ScheduleChange` com quem/quando; a **granularidade de armazenamento** (uma linha por operação ou
    por lote) continua lacuna da 4.4 (doc §6).
12. **ADR 4.1.0001 › "the server refuses the mutation and returns the current state"** (*"the server refuses the mutation and returns the current state"*):
    `ScheduleVersionConflictError` carrega a versão atual; o "estado atual" chega pela releitura
    (`get_schedule`) que o cliente faz — a 4.5 decide se o corpo do 409 já a inclui.
13. **ADR 4.2.0001 › "evaluated against the employee record's functions at evaluation time" / doc §3.6.7** (a marca `function_exception` como "registro do aceite"): nesta
    Stage a marca significa "função não detida **no ato de alocar**" e nasce mesmo com a política
    desabilitada (§7 D-FEXC); o **aceite** é o que vai em `ScheduleChange.acknowledged`. Marca não
    implica aceite — aviso à 4.5/8.1.

## 2. Objetivo da Stage

Ao final, sem I/O real, um gerente pode — pela application do BC scheduling, com fakes nos ports
— criar a escala da semana, editar faixas, demandas e alocações num lote avaliado ao vivo, ter
recusada a mudança que introduz violação `block`, publicar com aceite consciente a que introduz
`warn`, e ler a escala, o calendário e as escalas anteriores; o funcionário lê as próprias
alocações — tudo autorizado pelo próprio use case e sem nenhum registro inativo à vista.

## 3. Contexto e premissas

### Contexto

- **Salvar = publicar** (ADR 4.1.0001 §1): cada gravação é a escala vigente. **`block` recusa a
  mutação; `warn` é aceito no ato de salvar**, e o aceite é auditado.
- **Concorrência otimista por versão** (ADR 4.1.0001 §2): toda mutação carrega a versão vista;
  escala mudada ⇒ recusa e o cliente recarrega ou cancela. O contador vive no domínio (ADR
  4.1.0009 Decision 3); a coluna e a comparação atômica são da 4.4. **Limite declarado:** a versão
  protege só a escala mutada; duas publicações simultâneas em semanas adjacentes podem gravar, cada
  uma contra o estado antigo da outra, uma violação de fronteira que nenhuma viu (write skew) — a
  próxima avaliação de qualquer das duas a mostra ao vivo; mitigação forte é [finding] 4.4.
- **O avaliador descreve, não recusa** (concept 4.2 §5.1): quem recusa e quem pergunta é esta
  Stage, comparando as violações **antes × depois** pela `key` (ADR 4.2.0002 §5).
- **Reconciliação na leitura** (ADR 4.1.0006): nada é escrito em scheduling quando staff desliga
  alguém; toda leitura consulta o estado atual pelo `StaffReadPort` e omite o inativo — nem as
  alocações passadas dele aparecem.
- **BCs independentes** (LAYOUT §3; contrato `bc-independence`): scheduling não importa staff nem
  identity; lê staff por port próprio, com adapter na 4.4 sobre uma fachada de staff que **não
  autoriza** (ADR 3.5.0001: o chamador autoriza) — finding 1 da issue #72 (§7 D-STAFFPORT).
- **Fail-closed na application** (ADR 3.7.0001, `done` desde a Stage 3.7): o use case autoriza o
  alvo que o command declara antes de qualquer outra instrução. Esta Stage reaplica o padrão em
  scheduling desde o primeiro commit, com port próprio (§7 D-AUTH) — finding 2 da issue #72.
- **Unidade de trabalho** (ADR 2.6.0002): só identity tem unit; a regra 10 do `check_layout`
  exige unit de todo use case que escreve duas vezes. Nenhum use case desta Stage escreve duas
  vezes: estado e trilha vão numa escrita só do repositório (§7 D-AUDIT).

### Premissas

- Volume do piloto (ASSUM-4/5): uma unidade, dezenas de registros, 7 dias — avaliar a escala
  inteira duas vezes por lote é aceitável; nada é indexado.
- A configuração é do tenant (ADR 4.1.0003); um tenant que nunca a gravou usa os defaults de
  domínio (`OperationalCalendar.default()`, `ValidationConfig.default()`).
- O cliente (4.5) envia os dias como `date` e os limites de faixa em wall-clock ingênuo da
  unidade (precedente ADR 3.6.0003: valor com offset é recusado, não convertido).
- O cliente gera os ids das entidades internas que cria num lote (§7 D-IDS) e os valida na borda
  (ADR 3.6.0002).

### Dependências

- `4.2-validation-policies` (`done`, PR #66): `evaluate`, `EvaluationContext`, `Violation`/
  `ViolationKey`, `ValidationConfig`/`PolicyKind`/`EnforcementMode`, `EmployeeFacts`/
  `UnavailabilityWindow`.
- `4.1-scheduling-domain` (`done`, PR #63): `Schedule` e as 11 mutações, `TimeRange`,
  `OperationalCalendar`, `SchedulePeriod`, `DemandQuantity`, ids, `SchedulingError` e as 22
  exceções.
- `shared/application/ports/out`: `Clock`, `IdGenerator`.

## 4. Contratos

### Introduzidos

Todos em `features/scheduling/application/`. Nomes em inglês; valores de string em minúsculas.

#### Port `AccessGuard` (`ports/out/access_guard.py`)

`Actor = object` (credencial verificada, opaca para scheduling).
Permissões como `str`: `PERMISSION_VIEW_SCHEDULE = "view_schedule"` (ler),
`PERMISSION_MANAGE_SCHEDULE = "manage_schedule"` (criar/avaliar/publicar),
`PERMISSION_VIEW_OWN_SCHEDULE = "view_own_schedule"` (minha escala).
`AuthorizedScope(frozen)`: `tenant_id: TenantId`, `unit_id: UnitId`, `user_id: str` (o sujeito
autenticado — id de login em identity).
`AccessGuard(Protocol)`: `authorize(actor, permission, *, tenant_id: str, unit_id: str) ->
AuthorizedScope` — os dois alvos são **obrigatórios**: toda permissão de scheduling é por
unidade (ADR 4.1.0004 §1, "all unit-scoped").

Leis (docstring do port, provadas contra o fake):
- **L-SG1** — a recusa sai crua (o tipo da exceção não é fixado — vocabulário do outro BC).
- **L-SG2** — tenant confirmado: o escopo traz o `tenant_id` e o `unit_id` pedidos, nunca vazios;
  ator de outro tenant ou sem tenant é negado.
- **L-SG3** — uma autorização por alvo: autorizar uma unidade não autoriza outra, nem uma
  permissão autoriza outra.
- **L-SG4** — o sujeito vem do token: `user_id` é o do ator autenticado, nunca vazio, nunca
  tirado do pedido.

#### Port `StaffReadPort` (`ports/out/staff_read_port.py`)

`StaffMember(frozen)` — DTO próprio de scheduling (doc §3.10.1): `employee_id`, `unit_id`,
`display_name`, `active: bool`, `job_function_ids: frozenset[JobFunctionId]`,
`contracted_weekly_hours: Decimal | None` (None = sob demanda),
`unavailabilities: tuple[UnavailabilityWindow, ...]`.
`JobFunctionEntry(frozen)`: `job_function_id`, `name`.
`StaffReadPort(Protocol)`:
- `list_active_members(tenant_id, unit_id) -> tuple[StaffMember, ...]`
- `list_members(tenant_id, unit_id, employee_ids: frozenset[EmployeeId]) -> tuple[StaffMember, ...]`
- `list_members_of_user(tenant_id, unit_id, user_id: str) -> tuple[StaffMember, ...]`
- `list_job_functions(tenant_id) -> tuple[JobFunctionEntry, ...]`

Leis (suíte de contrato): **L-ST1** endereço (nunca registro de outra unidade/tenant); **L-ST2**
quadro completo (`list_active_members` = todos os ativos da unidade, só eles); **L-ST3** lote (um
`StaffMember` por id pedido que é da unidade, ativo ou não; id desconhecido/de outra unidade
omitido); **L-ST4** vínculo de login (`list_members_of_user` = registros da unidade vinculados ao
`user_id`, ativos ou não, só eles); **L-ST5** catálogo (todas as funções do tenant, só elas).
Sem ordem garantida (o use case ordena).

#### Port `ScheduleRepository` (`ports/out/schedule_repository.py`)

`ScheduleChange(frozen)` — o registro de uma mudança (a entrada da trilha, 4.4):
`author_user_id: str` (quem = `AuthorizedScope.user_id`), `occurred_at: datetime` (quando =
`Clock.now()`), `previous_version: int | None` (None na criação), `operations:
tuple[ScheduleOperation, ...]` (o quê: as operações **efetivas**, em ordem), `acknowledged:
tuple[Violation, ...]` (as `warn` introduzidas e aceitas).
`ScheduleRepository(Protocol)`:
- `add(schedule, change) -> None`
- `save(schedule, expected_version: int, change) -> None`
- `find_by_id(tenant_id, unit_id, schedule_id) -> Schedule | None`
- `list_in_range(tenant_id, unit_id, first_day: date, last_day: date) -> tuple[Schedule, ...]`
- `list_ending_before(tenant_id, unit_id, before: date, limit: int) -> tuple[Schedule, ...]`

Leis (a 4.4 as implementa em Postgres): **L-SC1** `add` é inserção (id de escala já gravado ⇒
`IdentifierInUseError`); **L-SC2** dias disjuntos (`add` cujo período cruza dia de outra escala do
mesmo (tenant, unidade) ⇒ `SchedulePeriodTakenError` — impõe a invariante 4 da 4.1; atômica no
adapter; limite de concorrência declarado — ADR 3.2.0001); **L-SC3** estado e trilha juntos
(atômicos; o fake os grava juntos e os expõe para leitura); **L-SC4** `save` otimista
(inexistente ⇒ `ScheduleNotFoundError`; versão gravada ≠ `expected_version` ⇒
`ScheduleVersionConflictError` com a atual; id interno novo já usado por **outra** escala do mesmo
(tenant, unidade) ⇒ `IdentifierInUseError`; ordem endereço → versão → ids); **L-SC5** endereço de
três partes (outro tenant/unidade ⇒ None, e nunca aparece em listagem); **L-SC6** recorte
(`list_in_range` = as escalas que cruzam [first_day, last_day], por first_day); **L-SC7**
anteriores (`list_ending_before` = last_day < before, da mais recente, ≤ limit); **L-SC8**
fidelidade (lido == gravado, campo a campo, inclusive a versão).

#### Port `ScheduleConfigRepository` (`ports/out/schedule_config_repository.py`)

`SchedulingSettings(frozen)`: `calendar: OperationalCalendar`, `validation: ValidationConfig`.
`find_settings(tenant_id) -> SchedulingSettings | None`. **L-CF1**: devolve a config gravada do
tenant, ou None (nunca a de outro tenant); os defaults são do use case, num sítio só (§5.12).

#### DTOs (`dtos/`)

**Operações** (`dtos/commands.py`) — uma por mutação do agregado; `ScheduleOperation` é a união:
`EnableBand(band_id, time_range: TimeRange)`; `RescheduleBand(band_id, start, end: datetime)`;
`RedeclareBandBreak(band_id, break_minutes)`; `DisableBand(band_id)`;
`DeclareDemand(demand_id, band_id, job_function_id, quantity: DemandQuantity)`;
`ChangeDemandQuantity(demand_id, quantity)`; `WithdrawDemand(demand_id)`;
`AssignEmployee(assignment_id, demand_id, employee_id, counts_toward_workload=True)`;
`UnassignEmployee(assignment_id)`; `DeclareWorkloadCounting(assignment_id, counts)`;
`DeclareAllocationBreak(assignment_id, break_minutes: int | None)`. Os ids de criação (`band_id`
de `EnableBand`, `demand_id` de `DeclareDemand`, `assignment_id` de `AssignEmployee`) vêm do
cliente (§7 D-IDS). `function_exception` **não** é campo de `AssignEmployee`: é derivado (§5.8).

**Commands e queries** — ator como 1º campo (`field(repr=False)`) + endereço (tenant_id,
unit_id[, schedule_id]):
`CreateScheduleCommand(actor, tenant_id, unit_id, first_day: date)`;
`PublishScheduleCommand(actor, tenant_id, unit_id, schedule_id, expected_version: int, operations,
acknowledgements: tuple[ViolationAcknowledgement, ...] = ())`;
`ViolationAcknowledgement(key: ViolationKey, observed: Decimal, limit: Decimal)` (a medida
**que a gerente viu**, com o limite dela — §5.7);
`EvaluateScheduleQuery(actor, tenant_id, unit_id, schedule_id, expected_version: int, operations)`;
`GetScheduleQuery(actor, tenant_id, unit_id, schedule_id)`;
`GetCalendarQuery(actor, tenant_id, unit_id, first_day, last_day)`;
`ListPastSchedulesQuery(actor, tenant_id, unit_id, before: date, limit: int = 10)`;
`GetMyScheduleQuery(actor, tenant_id, unit_id, first_day, last_day)`.

**Results** (`dtos/results.py`, cada classe num sítio só): `ScheduleSummaryResult`,
`AssignmentResult`, `DemandResult` (só alocações de ativos), `BandResult`, `ScheduleResult`
(com `violations`), `EvaluationResult(schedule, blocking, warnings)` (blocking/warnings = as
**introduzidas**), `CalendarResult`, `MyShiftResult`, `MyScheduleResult`. `Violation`,
`ViolationKey`, `TimeRange`, `DemandQuantity` trafegam por licença do LAYOUT §7 (VOs imutáveis);
nenhum DTO carrega entidade.

#### Use cases (`use_cases/`)

| Use case | Entrada → saída | Permissão (alvo) |
|---|---|---|
| `CreateScheduleUseCase` | CreateScheduleCommand → ScheduleSummaryResult | manage_schedule (tenant, unidade) |
| `EvaluateScheduleUseCase` | EvaluateScheduleQuery → EvaluationResult | manage_schedule (tenant, unidade) |
| `PublishScheduleUseCase` | PublishScheduleCommand → ScheduleResult | manage_schedule (tenant, unidade) |
| `GetScheduleUseCase` | GetScheduleQuery → ScheduleResult | view_schedule (tenant, unidade) |
| `GetCalendarUseCase` | GetCalendarQuery → CalendarResult | view_schedule (tenant, unidade) |
| `ListPastSchedulesUseCase` | ListPastSchedulesQuery → tuple[ScheduleSummaryResult, ...] | view_schedule (tenant, unidade) |
| `GetMyScheduleUseCase` | GetMyScheduleQuery → MyScheduleResult | view_own_schedule (tenant, unidade) |

Avaliar e publicar compartilham o protocolo num módulo privado (`use_cases/_publish.py`,
precedente `identity/application/use_cases/_invitation.py`); a montagem do insumo (config com
default, vizinhas, quadro de staff) fica em `use_cases/_inputs.py`.

#### Erros (`application/errors.py`, filhos de `SchedulingError`)

`ScheduleNotFoundError` (também `NotFoundError`), `ScheduleVersionConflictError` (carrega a versão
atual), `SchedulePeriodTakenError`, `IdentifierInUseError`, `BlockingViolationsError` (carrega as
violações), `UnacknowledgedViolationsError` (carrega as pendentes), `StaffMemberNotFoundError`
(também `NotFoundError`), `InactiveStaffMemberError`, `JobFunctionNotFoundError` (também
`NotFoundError`), `InactiveAllocationsInUseError` (D3 — carrega os ids das alocações),
`MissingStaffRecordsError` (registro alocado que staff não devolve — carrega os ids das
alocações, §5.12), `InvalidScheduleRequestError`. Doze; o piso de `test_status_map.py` sobe de 22
para 34.

### Consumidos

Domínio 4.1 e 4.2 (os erros de domínio sobem sem embrulho, §5.11); `Clock` e `IdGenerator` de
shared; dados de staff por `StaffReadPort`; sujeito e decisão de acesso por `AccessGuard` (os dois
implementados fora de scheduling — 4.4 o adapter, o composition root o tradutor).

## 5. Invariantes e regras

1. **Autorização primeiro** (§7 D-AUTH): a 1ª instrução de todo `execute` é
   `self._guard.authorize(command.actor, <permissão>, tenant_id=command.tenant_id,
   unit_id=command.unit_id)`; nenhum port tocado, nenhum id gerado, nenhum relógio lido, nenhuma
   validação de pedido antes da decisão. O escopo **não** é fonte de endereço (o use case opera no
   endereço do command); do escopo lê só o `user_id`, e só onde precisa dele (trilha, minha
   escala).
2. **Endereço de três partes** (ADR 3.4.0007): escala de outra unidade/tenant é não encontrada.
3. **Criar**: período de 7 dias a partir de `first_day`, alinhado ao calendário **atual** do
   tenant (recusa o desalinhado com `InvalidSchedulePeriodError`, do domínio); nasce vazia, versão
   1, com o calendário fotografado; dia já coberto por outra escala da unidade ⇒
   `SchedulePeriodTakenError` (use case **e** L-SC2); grava com `ScheduleChange` sem operações
   (`previous_version=None`).
4. **Versão**: avaliar e publicar recusam com `ScheduleVersionConflictError` quando
   `expected_version` ≠ a carregada; `save` recusa de novo se a gravada mudou (L-SC4);
   sobrescrever não é oferecido.
5. **Lote atômico**: operações aplicadas em ordem sobre a escala carregada, em memória; a 1ª que
   falha recusa o lote com o erro dela, nada gravado. Só o estado **final** é avaliado (estado
   intermediário inválido nunca é gravado nem visto). Lote vazio é permitido (equivale a um
   refresh com checagem de versão).
6. **Violação introduzida**: avalia antes (carregada) e depois (final), com as mesmas vizinhas,
   fatos e config. O **desvio** de uma violação é `observed − limit`, **com sinal** (cada lado com o
   próprio `limit`). Uma violação do depois é introduzida sse (a) a `key` não está no antes, ou (b)
   está e o desvio **trocou de sinal** ou o |desvio| **cresceu** — vale para toda política (nas de
   medida constante, como `function_mismatch`, reduz-se a "só por `key`"; na carga em `both`, a
   troca de sinal pega subcarga que vira sobrecarga; na divergência de intervalo, o intervalo
   declarado que se afasta mais do da faixa). **Sobre-cobertura** (cuja `key` inclui as alocações)
   casa por (política, demanda): introduzida sse não havia sobre-cobertura dessa demanda no antes,
   ou entrou alocação fora do conjunto do antes, ou o excedente cresceu — desalocar um excedente
   sem chegar a N não re-pergunta nem recusa. Pré-existentes (de qualquer origem —
   mudança em staff (D1) ou config alterada) são mostradas e nunca recusam nem pedem aceite numa
   mudança que não as introduziu.
7. **Recusar ou pedir aceite** (só publish): `block` introduzida ⇒ `BlockingViolationsError`
   (todas as introduzidas `block`); senão `warn` introduzida sem aceite ⇒
   `UnacknowledgedViolationsError` (as pendentes). Um `ViolationAcknowledgement(key, observed,
   limit)` cobre a `warn` introduzida de mesma `key` cujo desvio não é pior que o aceito: mesmo
   sinal e |observed − limit| da violação ≤ |ack.observed − ack.limit| — o desvio do aceite é
   calculado com o **limite que a gerente viu**, então reduzir N ou mudar a carga depois de avaliar
   re-pergunta. Aceite que não cobre nada é ignorado; `block` é checado antes de `warn`.
   `evaluate` não recusa: devolve as introduzidas em `blocking`/`warnings`.
8. **Alocar**: o registro precisa ser da unidade e **ativo** (`StaffMemberNotFoundError` se staff
   não o devolve; `InactiveStaffMemberError` se desligado). `function_exception = True` sse a
   função da demanda não é detida pelo registro **no ato de alocar**, independente de a política
   estar habilitada ou do modo (§7 D-FEXC) — com `function_mismatch` em `block` a mudança é
   recusada na publicação. `DeclareDemand` de função fora do catálogo do tenant ⇒
   `JobFunctionNotFoundError`.
9. **Alocação invisível × remoção** (§7 D3): `DisableBand`/`WithdrawDemand` sobre faixa/demanda
   com **ao menos uma** alocação e **nenhuma** de registro ativo ⇒ `InactiveAllocationsInUseError` com a
   contagem e os ids dessas alocações (sem nome nem id do registro); com ao menos uma alocação de
   ativo, a recusa é a do domínio (`ShiftBandInUseError`/`ShiftDemandInUseError`), porque essa a
   gerente vê. Desalocar por id (`UnassignEmployee`) no mesmo lote destrava.
10. **No-op** (§7 D-NOOP, D2): operação cujo resultado é a própria escala (`is`) não entra na
    trilha nem conta na versão; lote sem operação efetiva não grava (publish devolve a escala
    vigente).
11. **Erros de domínio sobem como são** (§7 D-ERRWRAP).
12. **Insumo completo** (§7 D-ROSTER): fatos do quadro ativo inteiro (`list_active_members`) +
    `list_members` para os alocados (escala + vizinhas) e os alvos de `AssignEmployee`, unidos por
    `employee_id` (o de `list_members` prevalece — é a leitura mais específica); registro alocado
    que staff **não** devolve NÃO vira inativo: o use case recusa fail-closed com
    `MissingStaffRecordsError`, carregando os ids das alocações afetadas (sem id de registro),
    antes de avaliar — em toda leitura e escrita que toque a escala (avaliar, publicar, ler a
    escala, calendário); "minha escala" só lê registros que staff devolveu. A recusa contamina as
    vizinhas (que entram no insumo) e não tem caminho de reparo na 4.3 — o estado é inalcançável
    depois da guarda reversa da 4.4, salvo a corrida declarada (finding 4.4: guarda check-then-act
    entre BCs e use case de reparo). A config é `find_settings(tenant)` ou os defaults, num sítio
    só. **Limite declarado:** ler uma escala passada usa o quadro ativo de **hoje** (registro
    contratado depois aparece como subcarga em `both`) — a escala mostra o estado atual, por
    desenho (ADR 4.1.0006).
13. **Vizinhas** (ADR 4.2.0002 §1): a anterior e a seguinte são as escalas da unidade cujo período
    termina no dia antes do primeiro / começa no dia depois do último (`list_in_range` sobre esses
    dois dias).
14. **Reconciliação na leitura** (ADR 4.1.0006 §2): nenhum result traz alocação de registro
    inativo (o ausente é recusado, §5.12); o nome de exibição é o do estado atual de staff; função
    fora do catálogo sai com nome `None`.
15. **Instantes de fora do domínio** (§7 D-NOW): os limites de `RescheduleBand` são validados
    ingênuos e de minuto inteiro (construindo um `TimeRange`, `InvalidTimeRangeError`) antes de
    qualquer `operational_day_of` — fecha o achado M4 da 4.1; todo dia em query/command é `date`,
    não `datetime` (`InvalidScheduleRequestError`).
16. **Calendário** (§7 D-CAL): recorte com first_day ≤ last_day e até 42 dias; resumo das escalas
    que cruzam + as faixas cujo dia operacional (pelo calendário fotografado de cada escala) cai no
    recorte.
17. **Escalas anteriores** (§7 D-PAST): last_day < before, mais recente primeiro, 1 ≤ limit ≤ 52.
18. **Minha escala** (§7 D-OWN): registros **ativos** da unidade vinculados ao `user_id` do
    escopo; alocações cujo dia operacional cai no recorte (até 42 dias); registro inativo não tem
    "minha escala".
19. **Uma escrita por use case** (§7 D-AUDIT): create → `add`; publish → `save` (ou nenhuma, no
    lote sem efeito); estado e trilha atômicos no port (L-SC3); sem unit of work (regra 10 do
    `check_layout`, ADR 2.6.0002 §5).
20. **Ordem determinística dos results**: faixas por (início, id); demandas por (função, id);
    alocações por (nome, id); turnos de "minha escala" por (início, id da alocação); escalas por
    first_day; violações na ordem do avaliador.
21. **Ids de criação** (§7 D-IDS): o id criado por `EnableBand`/`DeclareDemand`/`AssignEmployee`
    que já existe, do mesmo tipo, na escala carregada ou numa vizinha ⇒ `IdentifierInUseError`,
    antes de aplicar o lote; repetido dentro do próprio lote ⇒ a recusa do domínio
    (`DuplicateEntityIdError`); em escala não vizinha da unidade ⇒ `save` recusa (L-SC4).

## 6. Casos de erro e exceções

| Condição | Erro | Onde |
|---|---|---|
| guard nega | a exceção do guard, crua (L-SG1) | todo use case, 1ª instrução |
| dia `datetime`, recorte invertido ou > 42 dias, `limit` fora de [1, 52] | `InvalidScheduleRequestError` | queries de leitura, create |
| escala inexistente no endereço | `ScheduleNotFoundError` | evaluate, publish, get |
| `expected_version` ≠ carregada (ou gravada, no `save`) | `ScheduleVersionConflictError` | evaluate, publish |
| `first_day` desalinhado | `InvalidSchedulePeriodError` (domínio) | create |
| dia já coberto | `SchedulePeriodTakenError` | create (e L-SC2) |
| id de criação já usado | `IdentifierInUseError` | evaluate, publish (e L-SC1/L-SC4) |
| alvo de `AssignEmployee` ausente / desligado | `StaffMemberNotFoundError` / `InactiveStaffMemberError` | por operação |
| função de `DeclareDemand` fora do catálogo | `JobFunctionNotFoundError` | por operação |
| limites de `RescheduleBand` com fuso/segundos | `InvalidTimeRangeError` (domínio) | por operação |
| faixa/demanda presa só por alocação de desligado | `InactiveAllocationsInUseError` | por operação |
| recusa estrutural de uma operação | erro de domínio, cru | por operação |
| registro alocado que staff não devolve | `MissingStaffRecordsError` | evaluate, publish, get, calendário |
| `block` introduzida | `BlockingViolationsError` | publish |
| `warn` introduzida sem aceite | `UnacknowledgedViolationsError` | publish |

Ordem: autorização → validação do pedido → carga (não encontrada → versão) → ids de criação →
leitura de staff e recusa do ausente (`MissingStaffRecordsError`; no calendário, um ausente em
qualquer escala do recorte recusa o recorte inteiro) → operações em ordem (por operação: pré-checagens de staff/catálogo/instante/D3, depois o domínio) →
avaliação → `block` → `warn` → `save`. Violação de política não é exceção em evaluate e nas
leituras: é dado.

## 7. Decisões técnicas relevantes

> Registro no formato da skill `evidence-resolution` §5. As citações load-bearing foram conferidas
> por agente independente na sessão de 2026-10-21 (19 sustenta, 1 parcial, já incorporada) e as
> decisões revalidadas contra o `develop` de 2026-11-01 (Stages 2.6, 3.7 e 3.8 mergeadas).

### D1 — Violação induzida por mudança em staff · P (delegado; ratificado 2026-11-01)

- **Escolha:** (a) **mostrar e corrigir.** Staff não muda; a escala vigente pode conter a violação
  (inclusive `block` de indisponibilidade) até a gerente desalocar; os invariantes do doc §3.5,
  §3.6.6, §3.6.7 e §3.6.8 valem para o que a **escala** introduz. As origens nomeadas: férias/
  indisponibilidade lançada, função retirada, carga contratada editada (a `workload_policy` a lê)
  e recontratação (alocações antigas reaparecem, ADR 4.1.0006).
- **Alternativa descartada:** (b) guarda em staff recusando `register_unavailability`/
  `assign_job_functions` sobre turno alocado — contradiz ADR 3.4.0006 (indisponibilidade é
  `cadastro` editado pelo RH), não cobre carga nem recontratação, e é impraticável sobre o
  desligado invisível.
- **Consequência:** nota datada no doc de domínio (§6) com as quatro origens. ADR 4.3.0003.

### D2 — `change_demand_quantity` com o mesmo N · C (re-triada de P; ratificado 2026-11-01)

- **Escolha:** no **domínio** — `Schedule.change_demand_quantity` devolve `self` quando a
  quantidade pedida é a corrente (comparação antes de tudo); a 4.3 detecta as cinco mutações sem
  efeito por identidade.
- **Alternativa descartada:** no use case (cada consumidor repete a comparação).
- **Degrau:** 1 — ADR 4.1.0009 Decision 3 enuncia o no-op como regra geral; a enumeração de quatro
  do concept 4.1 §5.16 é sub-inclusiva (finding do technical 4.1 §7). Errata datada no CA11b da
  4.1. ADR 4.3.0001.

### D3 — Faixa presa só por alocação de desligado · P (delegado; ratificado 2026-11-01)

- **Escolha:** (b) **recusar revelando contagem + ids das alocações** de registros não ativos (sem
  nomes), para a gerente desalocá-las num ato explícito no mesmo lote (gravado na trilha como
  dela); confirmação na UX da 4.5. Estendida a `WithdrawDemand` (mesmo beco, mesma guarda §5.21 da
  4.1 — C, degrau 1).
- **Alternativas descartadas:** (a) recusa opaca — beco sem saída, o desligado é invisível (F7);
  (c) remover junto — **excluída por evidência**: reintroduz a cascata recusada em Q1 do concept
  4.1 e desarma a guarda L-E5 sem ato da gerente.
- **Tensão registrada:** ids de alocação são surrogates opacos, não dado do funcionário — leitura
  defensável de F7. ADR 4.3.0001.

### Decisões C/E (degrau e fonte)

- **D-AUTH (C, degrau 1+2)** — todo use case recebe por construtor um `AccessGuard` **de
  scheduling** e autoriza o alvo do command antes de qualquer instrução; ator 1º campo
  (`repr=False`). **Revalidado contra o ADR 3.7.0001 em `develop`:** o padrão é reaplicado **por
  BC**, não promovido a ADR transversal nem a port em `shared/` — o port de staff fala o
  vocabulário de staff (`authenticate`, permissões de staff, escopo sem sujeito), o contrato
  `bc-independence` proíbe importá-lo, e o de scheduling precisa do `user_id` no escopo. Uma regra
  transversal fica para quando um terceiro BC a repetir (finding). ADR 4.3.0002.
- **D-PERM (C, degrau 1)** — `view_schedule`, `manage_schedule`, `view_own_schedule` como `str` no
  módulo do port; o enum de identity e o mapa de papéis entram na 4.5 (ADR 4.1.0004 Decision:
  "Permission names … are gaps for the Stage 4.5 concept").
- **D-OWN (C, degrau 2)** — o `AuthorizedScope` carrega o `user_id` do sujeito (L-SG4);
  `get_my_schedule` autoriza `view_own_schedule` em (tenant, unidade) e lê
  `list_members_of_user(tenant, unidade, user_id)`, descartando inativos; N unidades = a 4.5
  consulta por unidade. Rejeitado: autorizar sem unidade (contradiz ADR 4.1.0004 §1); a query
  carregar `user_id` (ADR 0.0.0005 cláusula 1).
- **D-SAVE (C, degrau 4)** — publicar aplica 1..N operações nomeadas, atomicamente, com uma
  checagem de versão, uma avaliação antes × depois e os aceites; `evaluate` é o mesmo sem gravar.
  A UX "publicar edições acumuladas × gravar a cada ação" fica para a 4.5 (a forma serve as duas).
  ADR 4.3.0001.
- **D-IDS (C, degrau 5 + necessidade técnica)** — ids de criação vêm do cliente; unicidade por
  (tenant, unidade) (quem gerencia a unidade lê todas as escalas dela, logo a recusa não é
  oráculo); sem isso a `key` de uma violação por alocação não casa entre avaliar e publicar. ADR
  4.3.0004. Finding 4.5: formato UUID canônico na borda.
- **D-ACK (E)** — §5.6–§5.7. Base: doc §3.5; §3.6.8; ADR 4.2.0002 Consequences; concept 4.2
  §5.8–§5.9. ADR 4.3.0001.
- **D-VIRADA (C, degrau 1)** — o aceite da violação da virada é gravado na trilha da escala cuja
  mutação a introduziu; como ela aparece com a mesma `key` dos dois lados (ADR 4.2.0002 Decision
  1), editar a vizinha depois não a re-pergunta. Nada a codificar além de §5.6.
- **D-ROSTER (C)** — §5.12. Base: concept 4.2 §5.4; ADR 4.1.0006 §2; ADR 4.2.0002 Alt D. A
  recusa do ausente sai com erro próprio da application (com os ids das alocações, como a D3) em
  vez do `InvalidEvaluationInputError` cru, para que calendário e leitura recusem igual e a 4.5
  tenha o que mostrar. ADR 4.3.0003.
- **D-STAFFPORT (C)** — quatro leituras em lote, todas com unidade no endereço exceto o catálogo
  (do tenant); DTO próprio; sem listagem tenant-wide de registro. **Finding 1 da issue #72:** o
  adapter (4.4) lê staff por **fachada que não autoriza** (ADR 3.5.0001 — o chamador autoriza), e
  não pelos use cases de staff (que exigiriam um ator de staff e autorizariam com permissão de
  staff uma leitura que scheduling já autorizou). ADR 4.3.0003.
- **D-AUDIT (C, degrau 5; revalidado contra ADR 2.6.0002)** — `add`/`save` recebem
  `ScheduleChange`; o adapter grava estado + trilha numa transação; cada use case faz **uma**
  escrita, logo a regra 10 não exige unit e scheduling não precisa de port de unit. N operações
  efetivas = N versões, todas listadas na `ScheduleChange`; a granularidade de armazenamento é da
  4.4 (divergência 11). ADR 4.3.0004.
- **D-LINK (C, degrau 1 — fora da 4.3)** — os findings de "vincular login existente" (concept 3.5
  §13, linhas 1009–1019; technical 3.8 §7: checar o tenant do `User`, regra de fim de vínculo)
  nomeiam a 4.3 *"ou uma Stage de gestão de acesso anterior a ela"*. Ficam **fora**: são escrita em
  staff + identity (outro BC e outra camada que a `camada_alvo: application` de scheduling), e
  `get_my_schedule` já os alcança sem mudança no dia em que o vínculo existir (lê
  `list_members_of_user`). Candidata: Stage de gestão de acesso (staff + identity) antes da 4.5,
  que é onde "minha escala" ganha superfície (§13).
- **D-NOW (C, degrau 5)** — §5.15; nenhum use case recebe instante absoluto nem o "agora" da
  unidade. Base: 4.1 technical §7 [finding]; ADR 4.1.0005 Implementation notes.
- **D-CAL (C, degrau 5)** — recorte de até 42 dias (grade de mês de 6 semanas). Base: doc §3.7.
- **D-TERM (E)** — não limpar alocações futuras no desligamento. Base: ADR 4.1.0006 Decision 1 e 4
  ("default: do not clear"); ADR 3.8.0001 não muda isso (corta só acesso).
- **D-FEXC (E)** — §5.8. Base: ADR 4.1.0003 (f); ADR 4.2.0001 Decision 2.
- **D-CONFIG (C)** — mudança de dia de início/corte vale só para escalas criadas depois (a escala
  fotografa o calendário, ADR 4.1.0009 Decision 4); sem migração; inalcançável na 4.3 (não há
  escrita de config) — requisito para a Stage da edição da config (finding).
- **D-REVERSE (C)** — staff passa a consultar o port reverso na **4.4** (dona da consulta e do
  wiring); até lá registro removido vira "ausente" (fail-closed). Base: ADR 4.1.0006
  Implementation notes.
- **D-PAST (C)** — §5.17. Base: overview §3.
- **D-NOOP (C)** — §5.10. Base: ADR 4.1.0009 Decision 3; 4.1 technical §7 [finding].
- **D-ERRWRAP (C, degrau 1)** — erro de domínio de uma operação sobe como está; o lote inteiro é
  recusado. Base: docstring de `staff/application/errors.py`.

## 8. Integrações

### Internas (com outras Stages/módulos)

- **4.4:** implementa `ScheduleRepository` (tabelas, versão atômica, unicidade de ids internos por
  unidade, trilha a partir de `ScheduleChange`), `ScheduleConfigRepository`, o adapter do
  `StaffReadPort` (fachada de staff que não autoriza), o tradutor do `AccessGuard` no composition
  root; acrescenta os adapters reais às suítes de contrato; liga a guarda reversa de staff
  (D-REVERSE); decide escopo e índice do `user_id` (ADR 3.5.0004 Alt C); mitigação do write skew de
  fronteira.
- **4.5:** rotas por use case; status das recusas (corpo de `BlockingViolationsError`/
  `UnacknowledgedViolationsError` = as violações; o de `ScheduleVersionConflictError` = a versão
  atual; o de `InactiveAllocationsInUseError` = contagem + ids); texto das violações; permissões e
  mapa de papéis em identity; autenticação; UX de publicar; formato UUID dos ids de criação; a
  desativação de conta que a 1ª permissão de auto-serviço exige (ADR 3.5.0003 §5).
- **4.6:** e-mail é efeito de publish depois do `save`; um lote = uma publicação.
- **Step 5:** "aplicar" do auto-fill pode ser um lote de `AssignEmployee` por este protocolo.
- **staff/identity:** nenhuma integração de código — só ports.

### Externas

Nenhuma.

## 9. Modelo de dados

Sem schema (persistência é da 4.4). Fluxo de `publish_schedule`: command → authorize
(manage_schedule, tenant, unidade) → escopo (`user_id`) → `find_by_id` → versão →
`find_settings` (ou defaults) → `list_in_range` (vizinhas) → ids de criação →
`list_active_members` + `list_members` + `list_job_functions` → aplica operações → avalia antes ×
depois → introduzidas → `BlockingViolationsError` | `UnacknowledgedViolationsError` |
`save(escala, versão vista, ScheduleChange)` → `ScheduleResult` (nova versão).

## 10. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Use case novo esquece de autorizar, ou autoriza depois de ler | teste de propriedade sobre a pasta `use_cases/` (guard que nega ⇒ nenhum port tocado; AST: 1ª instrução é o `authorize`) — CA03 |
| Aceite não casa entre avaliar e publicar | ids do cliente (D-IDS) + teste de fluxo avaliar → publicar com a `key` devolvida — CA22 |
| Desalocar excedente re-pergunta ou recusa | regra de sobre-cobertura por (política, demanda) — CA09 |
| Fato de staff faltando vira "inativo" em silêncio | recusa fail-closed com os ids — CA16 |
| Vizinhas não carregadas (perde descanso/sobreposição de fronteira) | CA25 |
| Use case lê escala de outra unidade | endereço de três partes — CA26 |
| Faixa impossível de desabilitar | D3 — CA14 |
| Fake diverge do adapter real | suítes de lei parametrizáveis; a 4.4 acrescenta o real — CA21 |
| Write skew entre semanas adjacentes | limite declarado; a próxima avaliação mostra; finding 4.4 |
| `view_own_schedule` exigir unidade | declarado para a 4.5 (consulta por unidade) |

## 11. Critérios de aceitação

- [x] **CA01 — criar:** escala nasce vazia, versão 1, com o calendário do tenant (ou o default)
      fotografado; `first_day` desalinhado ⇒ `InvalidSchedulePeriodError`; dia já coberto ⇒
      `SchedulePeriodTakenError`; grava uma `ScheduleChange` sem operações `[teste]`.
- [x] **CA02 — versão:** `expected_version` ≠ carregada ⇒ `ScheduleVersionConflictError`
      (carregando a versão atual) em avaliar e em publicar, sem gravar; o fake recusa `save` com
      versão vencida (L-SC4) `[teste]`.
- [x] **CA03 — autorização é a 1ª instrução, por use case:** com guard que nega, todo use case da
      pasta levanta a sentinela (`is`) sem tocar port, relógio ou gerador; com guard permissivo, a
      sequência de `authorize` é (permissão, tenant, unidade) do command; a 1ª instrução de todo
      `execute` é o `authorize` (AST); a pasta inteira está coberta `[teste]`.
- [x] **CA04 — lote atômico:** a 1ª operação que falha recusa o lote com o erro dela e nada é
      gravado; estado intermediário com `block` que some no final não recusa; lote vazio é
      aceito sem gravar `[teste]`.
- [x] **CA05 — avaliar:** devolve a escala resultante com todas as violações e as **introduzidas**
      separadas em `blocking`/`warnings`, sem gravar `[teste]`.
- [x] **CA06 — publicar recusa `block` introduzida** com `BlockingViolationsError` (todas as
      `block` introduzidas), sem gravar, antes de olhar os `warn`; `function_mismatch` em `block`
      recusa a alocação de função não detida `[teste]`.
- [x] **CA07 — publicar pede aceite de `warn` introduzida** (`UnacknowledgedViolationsError`) e,
      com o aceite, grava; a `ScheduleChange` traz autor (`user_id` do escopo), instante do
      `Clock`, versão anterior, operações efetivas e as violações aceitas `[teste]`.
- [x] **CA08 — aceite e medida:** aceite com desvio menor que o atual não cobre (re-pergunta
      quando a medida piora); aceite reenviado depois de reduzir N (mesmo `observed`, `limit`
      menor) não cobre; carga em `both` que troca subcarga por sobrecarga é introduzida e um aceite
      de subcarga não a cobre; aceite de `key` diferente é ignorado `[teste]`.
- [x] **CA09 — sobre-cobertura:** desalocar excedente sem chegar a N não re-pergunta; aumentar o
      excedente ou trocar a alocação excedente re-pergunta `[teste]`.
- [x] **CA10 — pré-existente não trava:** violação já presente antes (p.ex. induzida por staff,
      D1) aparece em `violations` e não recusa nem pede aceite numa mudança que não a introduziu
      `[teste]`.
- [x] **CA11 — alocar:** registro ausente ⇒ `StaffMemberNotFoundError`; desligado ⇒
      `InactiveStaffMemberError`; `function_exception` nasce `True` sse o registro não detém a
      função, com a política desabilitada inclusive; função fora do catálogo em `DeclareDemand` ⇒
      `JobFunctionNotFoundError` `[teste]`.
- [x] **CA12 — no-op:** as cinco idempotentes (inclusive `change_demand_quantity` com o mesmo N,
      no domínio) não contam versão nem entram na trilha; lote sem efeito não grava `[teste]`.
- [x] **CA13 — reconciliação na leitura:** nenhum result (escala, calendário, minha escala) traz
      alocação de registro inativo ou ausente; nome do estado atual `[teste]`.
- [x] **CA14 — D3:** desabilitar faixa / retirar demanda presa só por alocação de desligado ⇒
      `InactiveAllocationsInUseError` com contagem e ids de alocação (e sem o id do registro);
      desalocá-las no mesmo lote destrava; com alocação de ativo, a recusa é a do domínio; faixa
      sem alocação é desabilitada normalmente `[teste]`.
- [x] **CA15 — calendário** sobre duas escalas, só as faixas do recorte, recorte > 42 dias ou
      invertido ⇒ `InvalidScheduleRequestError` `[teste]`.
- [x] **CA16 — fail-closed:** registro alocado (na escala ou numa vizinha) que staff não devolve ⇒
      `MissingStaffRecordsError` com os ids das alocações em avaliar, publicar, ler a escala e
      calendário `[teste]`.
- [x] **CA17 — minha escala:** só as alocações dos registros ativos do `user_id` do escopo, na
      unidade, no recorte; sem registro ativo ⇒ vazia; recorte invertido ou > 42 dias ⇒
      `InvalidScheduleRequestError` `[teste]`.
- [x] **CA18 — escalas anteriores:** last_day < before, mais recente primeiro, até `limit`;
      `limit` fora de [1, 52] ⇒ `InvalidScheduleRequestError` `[teste]`.
- [x] **CA19 — instante de fora:** `RescheduleBand` com limite tz-aware ou com segundos ⇒
      `InvalidTimeRangeError` antes de `operational_day_of`; dia `datetime` em query ou no
      `CreateScheduleCommand` ⇒ `InvalidScheduleRequestError` `[teste]`.
- [x] **CA20 — erros de domínio sobem crus** (mesma instância de tipo de domínio, sem embrulho)
      `[teste]`.
- [x] **CA21 — suítes de lei dos ports** (`StaffReadPort`, `ScheduleRepository`,
      `ScheduleConfigRepository`, `AccessGuard`) verdes contra os fakes `[teste]`.
- [x] **CA22 — fluxo editar → avaliar → aceitar `warn` → publicar** com fakes: a `key` devolvida
      por avaliar casa no publicar pelos ids do cliente; id de criação já usado na escala ou numa
      vizinha ⇒ `IdentifierInUseError`; repetido no próprio lote ⇒ `DuplicateEntityIdError`
      `[teste]`.
- [x] **CA23 — contrato de pureza** `scheduling-application-purity` no `.importlinter`, verde
      `[import-linter]`.
- [x] **CA24 — `make check` verde** (Actions do PR) e cobertura ≥ 90% por arquivo da Stage.
- [x] **CA25 — vizinhas e virada:** a anterior e a seguinte adjacentes entram no insumo; uma
      violação de fronteira (descanso entre o último dia de A e o primeiro de B) introduzida ao
      editar B é perguntada, e editar A depois não a pergunta de novo `[teste]`.
- [x] **CA26 — endereço:** escala de outra unidade ou tenant ⇒ `ScheduleNotFoundError` em ler,
      avaliar e publicar, sem gravar; a config de outro tenant não é lida; sem config gravada,
      valem os defaults `[teste]`.
- [x] **CA27 — results determinísticos:** faixas, demandas, alocações e turnos na ordem de §5.20;
      função fora do catálogo sai com nome `None` `[teste]`.

## 12. Checklist de validação interna

- [x] Contratos com assinatura (§4).
- [x] Decisões com fonte e degrau; forks P com resposta registrada (§7).
- [x] ADRs 4.3.0001–4.3.0004 escritos, `accepted`.
- [x] Dependência 4.2 `done`.
- [x] Cabe em 3–12 Tasks (estimativa: 12 — a conferir na Fase 3B).
- [x] Riscos com mitigação (§10).
- [x] Findings 4.1/4.2/3.7 e os da issue #72 endereçados (§7); os de 3.5/3.8 que nomeiam a 4.3
      "ou Stage anterior" decididos fora (D-LINK).

## 13. Questões em aberto

Nenhuma bloqueante. Findings com Stage candidata:

- edição da config de validação/calendário: o resultado do Step 4 promete "bloquear/avisar
  configurável" (roadmap, Step 4) e nenhum bloco tem o use case de escrita — a 4.5 é só borda
  HTTP, e a permissão da config tenant-wide é lacuna dela (ADR 4.1.0004 › "Permission names (VIEW_SCHEDULE, MANAGE_SCHEDULE, VIEW_OWN_SCHEDULE, …)"). Candidata: alargar a
  4.5 ou Stage própria antes do fechamento do Step 4. Requisitos: violação pré-existente por config
  alterada; mudar o dia de início deixa 1–6 dias sem escala possível (períodos de 7 dias alinhados
  e disjuntos) e corte mais tarde cria janela sem período;
- vincular login existente a registro (concept 3.5 §13; technical 3.8 §7 — tenant do `User`,
  fim de vínculo) — D-LINK: Stage de gestão de acesso antes da 4.5;
- registro ausente (recusa sem reparo, contamina vizinhas): use case de reparo e a corrida da
  guarda reversa check-then-act entre BCs (4.4);
- formato UUID canônico dos ids de criação na borda (4.5);
- desativação de conta na 1ª permissão de auto-serviço (4.5/identity, ADR 3.5.0003 §5);
- guarda reversa `has_allocations_for`/`has_demands_for` e mitigação do write skew (4.4);
- índice/escopo de `find_by_user_id` em staff (4.4);
- rótulo/contagem de exceção de função (4.5/8.1);
- autenticação de ator fora da borda HTTP (Stage do 1º driver não-HTTP, como na 3.7);
- regra "todo use case autoriza o próprio alvo" como ADR transversal quando o 3º BC a repetir.

## 14. Referências

overview §3/§5/§6; roadmap Stage 4.3 e blocos 4.4–4.6; `shift-scheduling.md` §3.1/§3.4/§3.5/
§3.7/§3.9/§3.10/§4/§6; concept 4.1 §5/§8 e technical §7; concept 4.2 §5/§8 e technical §7;
concept/technical 3.7; ADRs 0.0.0005, 0.0.0006, 2.2.0002, 2.6.0002, 3.4.0001, 3.4.0006, 3.4.0007,
3.5.0001, 3.5.0003, 3.5.0004, 3.6.0001, 3.6.0002, 3.7.0001, 3.8.0001, 4.1.0001, 4.1.0003, 4.1.0004,
4.1.0005, 4.1.0006, 4.1.0009, 4.2.0001, 4.2.0002; ADRs desta Stage 4.3.0001–4.3.0004.

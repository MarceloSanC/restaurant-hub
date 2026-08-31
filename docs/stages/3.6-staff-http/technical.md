---
title: Technical — API de equipe (borda HTTP)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, staff-http, fastapi, router, schemas, rbac, error-handler, e2e]
status: done
created_at: 2026-08-18
updated_at: 2026-08-29
stage_id: 3.6-staff-http
stage_title: API de equipe (borda HTTP)
step_id: 3
step_title: Equipe da unidade
depends_on: [3.4-staff-access-scope]
concept_ref: ./concept.md
issue_id: 43
branch: feat/43-3-6-staff-http
tasks_count: 12
---

# Technical — Stage 3.6 — API de equipe (borda HTTP)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite e comando de
>    verificação **executável em PowerShell**.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<escopo>): <descrição> [3.6/task-NN]`, com `Refs #43` no rodapé.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
>    perguntar com opções e recomendação, e registrar em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done). Nunca propagar em silêncio.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 3.6: complete` e atualizar `roadmap.md`.

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage dá superfície HTTP ao BC `staff`, que hoje é surdo-mudo: os 16 use
cases e o `staff_access_guard` estão montados no `composition_root` e **nada no
boot os alcança**. Constrói-se, de dentro para fora: (a) a resolução do tenant no
tradutor do port — sem a qual as 16 rotas são inalcançáveis por todos os papéis
(ADR 0.0.0005) —; (b) as três peças do adapter testáveis sem app montada (schemas
e conversores, mapa de status, validador de identificador); (c) o `router.py` em
três fatias por recurso; (d) o wiring de dois routers; (e) os e2e contra app real
e Postgres real. Nenhuma camada de `application` ou `domain` de staff é tocada:
esta Stage **consome** contratos fechados nas Stages 3.1–3.4.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`), com três correntes de dependência
e uma decisão de desenho de suíte que atravessa o plano inteiro:

1. **A fundação de acesso antes de qualquer rota** (Task 01). A resolução do
   tenant toca `composition_root`, o docstring do port e o fake — três lugares
   fora do adapter — e é o que torna as rotas alcançáveis. Fazê-la depois
   produziria Tasks de rota cujos testes nascem vermelhos por razão alheia à Task.
2. **As peças sem app antes das peças com app** (02 → 03 → 04 → 05…08).
   `schemas.py`, `error_handlers.py` e `dependencies.py` são independentes entre
   si e testáveis isoladamente; cada uma vira um commit pequeno cujo diagnóstico
   é local. O `router.py` é o primeiro módulo que precisa das três.
3. **O adapter antes do wiring** (05…08 → 09). Enquanto o router não é
   registrado, a app de produção continua exatamente como está — e a
   não-regressão de identity (CA30/CA31) fica isolada num único commit, em vez
   de diluída em oito.

**A decisão de desenho de suíte que sustenta o resto: as varreduras nascem com o
domínio derivado do código, e por isso crescem sozinhas.** A Task 05 cria um
módulo de varreduras (`test_http_boundary_sweeps.py`) cujos `parametrize` **não
listam rotas nem campos à mão**: derivam de `router.routes`, de
`StaffError.__subclasses__` e de `model_fields` dos schemas. Consequência
operacional, e é a razão de o módulo nascer cedo em vez de tarde: uma rota
acrescentada na Task 07 que esqueça o validador de identificador **reprova a
própria Task 07**, sem ninguém lembrar de estender teste nenhum. É a resposta
direta ao conceito *"lei universal, representante estreito"* da skill
`stage-audit`, num terreno que multiplica representantes (16 rotas × 5 papéis ×
2 permissões): o domínio quantificado nunca é lista literal escrita por quem está
com pressa.

**O caso extremo tem plano próprio: o dublê adversarial do CA15.** A lei de §5.4
("a unidade que chega ao use case é a do **path**") fala de independência entre
duas fontes, e as **duas** implementações existentes do port — o tradutor de
produção e o `InMemoryAccessGuard` — **ecoam** a unidade pedida
(`authorize_action.py:113`, `scope_unit_id=command.unit_id`). Com qualquer uma
delas, "o router usou o path" e "o router usou o escopo" são o **mesmo objeto**:
a mutação sobrevive e a cobertura fecha em 100%. O domínio quantificado tem, no
sistema inteiro, **um único valor observável** — então o segundo é **fabricado**.
A Task 06 cria `tests/fakes/features/staff/adversarial_access_guard.py`, um
terceiro implementador do `AccessGuard` que devolve `AuthorizedScope` com
`unit_id` **diferente** do pedido (e, num segundo modo, `None`), documentado no
docstring como contradizendo as outras duas **de propósito**. Ele nasce na Task
06 (a primeira com rota de funcionário) e a suíte que o usa é parametrizada sobre
**REMP derivado de `router.routes`**, de modo que R08…R16 entram na trava assim
que são escritas, nas Tasks 07 e 08.

### Decisões que esta Fase 3B fechou

O concept §10 delegou explicitamente uma decisão à Fase 3B, e o ADR 3.6.0001
deixou uma forma em aberto. As duas ficam registradas aqui, e não num comentário
de diff, porque as duas mudam o que a borda aceita ou o que uma suíte prova.

- **D-3B1 — `weekly_hours` com espaço em volta é recusada, não aparada.**
  `Decimal("  40  ")` constrói `Decimal("40")`: o espaço some em silêncio. O
  conversor de borda recusa qualquer valor cuja forma crua difira da forma sem
  espaços em volta, levantando `InvalidWeeklyHoursError` (422). **Âncora:**
  ADR 2.3.0005 (nada de normalização silenciosa) e a cláusula 6 do ADR 3.6.0002
  (*"nothing else is normalised, trimmed or rewritten"*), que já governa o
  validador de identificador do **mesmo pacote** — `dependencies.py` (Task 04) e
  `schemas.py` (Task 02) são módulos distintos sob `adapters/in/http/`, e é a
  política do pacote que precisa ser uma só. Aceitar o trim daria duas políticas
  opostas para espaço em branco dentro de um adapter só, e a divergência seria
  invisível. Isto **fecha** o `[finding]` do concept §10 — ele
  não é escalado. Travado por critério de aceite da Task 02.
- **D-3B2 — o dublê adversarial mora em `tests/fakes/`, não inline no teste.**
  O ADR 3.6.0001 §Decision 5 exige que ele seja *"documented as contradicting
  both implementations on purpose"*; um módulo nomeado carrega docstring, e
  `make typecheck` (`mypy src/ tests/fakes/`) põe a linha
  `_conforms: AccessGuard = AdversarialAccessGuard()` sob gate. Inline, a
  conformidade com o `Protocol` ficaria fora do alcance do type-checker — que é
  exatamente a borda que produziu o blocker do Checkpoint B da 3.4.

### Pré-condições

**Válidas para TODA Task deste plano, sem exceção** — não são checklist de
abertura de Stage:

- **Postgres de pé, e sem caminho de skip** (ADR 2.3.0001). `make check` chama
  `test-gate`, que roda `pytest tests/` **inteiro** — inclusive `integration/`,
  `contract/[postgres]` e `e2e/`. Sem banco, **toda** Task falha, e a falha não é
  da Task. Subir e esperar prontidão é o primeiro comando de qualquer Task:
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  ```
  **Conferir de qual worktree é o container** antes de confiar no verde: um
  Postgres órfão de Stage anterior retém a porta e a suíte passa a testar infra
  alheia (`docker ps` + a `DATABASE_URL` do `.env`).
- Stage `3.4-staff-access-scope` em `done` e **mergeada** (PR #42); as demais
  dependências do concept §3 idem.
- `git status --porcelain` limpo no início e no fim de cada Task.
- Branch `feat/43-3-6-staff-http`. A errata dos ADRs pré-corte (concept §7 D6) já
  está aplicada nesta branch pelo commit `6aeb0bd`, **antes** da Task 01.

### Premissas técnicas

- Python 3.12, `uv`; `make check` = `lint` + `typecheck` + `layout-check` +
  `import-check` + `lock-check` + `docs-check` + `test-gate`.
- **`make typecheck` é `mypy src/ tests/fakes/` — e o alcance é propriedade desta
  Stage, não trivia.** `tests/unit/`, `tests/integration/`, `tests/contract/` e
  `tests/e2e/` **não** são type-checked. Foi essa borda que produziu o blocker do
  Checkpoint B da 3.4 (31 call sites invisíveis ao mypy). Toda Task que muda
  assinatura ou forma de objeto compartilhado lista, no seu corpo, **os arquivos
  de teste fora do alcance do mypy** — quem os quebrar só descobre no `pytest`.
- Cobertura com `branch = true` e `fail_under = 90`.
- **Nenhuma dependência nova** no `pyproject.toml`: FastAPI, Pydantic v2 e httpx
  estão no projeto desde a 2.4. **Nenhuma migration, nenhuma tabela** (concept §9).
- O pacote de entrada se chama `in` (keyword Python): o `composition_root` o
  alcança por `importlib`, e os testes de rota fazem o mesmo (LAYOUT §8).

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                    (M) 01, 09
├── shared/infrastructure/http/app.py                      (M) 09
└── features/staff/
    ├── application/ports/out/access_guard.py              (M) 01  — só docstring
    └── adapters/in/http/                                  (N)
        ├── __init__.py                                    (N) 02
        ├── schemas.py                                     (N) 02
        ├── error_handlers.py                              (N) 03
        ├── dependencies.py                                (N) 04
        └── router.py                                      (N) 05 · (M) 06, 07, 08
tests/
├── fakes/features/staff/
│   ├── in_memory_access_guard.py                          (M) 01
│   └── adversarial_access_guard.py                        (N) 06
├── unit/features/staff/
│   ├── application/test_access_guard_laws.py              (M) 01
│   └── adapters/
│       ├── test_composition_root_staff.py                 (M) 01, 02, 09
│       ├── test_http_schemas.py                           (N) 02
│       ├── test_http_error_handlers.py                    (N) 03
│       ├── test_http_dependencies.py                      (N) 04
│       ├── test_http_boundary_sweeps.py                   (N) 05
│       ├── test_http_router_job_functions.py              (N) 05
│       ├── test_http_router_employees.py                  (N) 06
│       ├── test_http_path_addresses_the_record.py         (N) 06
│       ├── test_http_router_employee_profile.py           (N) 07
│       └── test_http_router_lifecycle_and_copy.py         (N) 08
└── e2e/features/staff/                                    (N)
    ├── __init__.py + conftest.py                          (N) 10
    ├── test_staff_flow.py                                 (N) 10
    ├── test_staff_authorization.py                        (N) 11
    └── test_staff_status_bands.py                         (N) 12
```

## 2. Tasks

> Faixa saudável: **3–12 Tasks** (CONVENTIONS §6). Este plano mede **12** — o
> concept §12 estimava 11, e a diferença é uma só, nomeada: a matriz de acesso e
> as faixas de status pela API real, que uma primeira versão deste plano juntava
> num commit, são **dois assuntos** (quem pode alcançar × como o erro é
> classificado) e ~140 casos e2e contra Postgres real. Viraram as Tasks 11 e 12.
> **A subdivisão NÃO tocou o inventário de rotas**, que continua reservado para o
> caso de a execução estourar 12: esta Stage já é o produto de um corte (nota do
> bloco 3.4 do `roadmap.md`).

### Task 01 — o tenant vem do token, resolvido nas duas implementações do port

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/ports/out/access_guard.py`
  - `src/restaurant_hub/composition_root.py`
  - `tests/fakes/features/staff/in_memory_access_guard.py`
  - `tests/unit/features/staff/application/test_access_guard_laws.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:** efetivar o ADR 0.0.0005 na fronteira de staff. **Nenhuma
  assinatura muda** — `authorize` já declara `tenant_id: str | None = None`; o que
  muda é que `None` ganha significado documentado (*"o tenant do próprio ator"*) e
  que as **duas** implementações passam a resolvê-lo do ator antes de decidir.
  1. **Docstring do port:** no parâmetro `tenant_id` de `authorize` e no atributo
     `AuthorizedScope.tenant_id`, declarar que a ausência significa "o tenant do
     ator autenticado", com ponteiro para o ADR 0.0.0005 (três cláusulas). Não
     tocar em L-AG1…L-AG4 nem no texto de `AuthorizedScope.unit_id`, que a §5.4 do
     concept já mediu como correto.
  2. **`_IdentityAccessGuard.authorize`:** quando o chamador não nomeia
     `tenant_id`, preencher com o tenant do ator autenticado **antes de delegar ao
     `IdentityGuard`** (`composition_root.py:258-263` — quem monta o
     `AuthorizeActionCommand` é o guard de identity, não o tradutor). L-AG3
     continua imposta **depois**, como está: ator sem tenant é **negado**, jamais
     coagido para `""`.
  3. **`InMemoryAccessGuard.authorize`:** resolver o tenant do `FakeActor` pela
     mesma regra **antes** de consultar `grants`, de modo que uma concessão feita
     com o tenant nomeado seja alcançada por uma chamada que o omite. L-AG4 segue
     valendo: alvo é a tripla resolvida, e um alvo concedido não concede outro.
  4. **As duas suítes de lei** ganham o mesmo eixo `tenant nomeado × tenant
     omitido`, em produto com os `_ALVOS` que já existem, nos **dois** lados.
- **Detalhes técnicos:**
  - No tradutor, o ator é `Actor = object` na assinatura do port, mas dentro do
    `composition_root` ele é o `AuthenticatedActor` de identity: a leitura de
    `claims.tenant_id` acontece **aqui**, que é o *trusted layer* que a cláusula 3
    do ADR 0.0.0005 nomeia para um port que mantém o ator opaco. Staff continua
    sem ler atributo de ator.
  - **`platform_admin` com tenant omitido continua negado — mas pela matriz RBAC,
    não por L-AG3, e a distinção é a diferença entre teste e teatro.**
    `role.py:54` dá a `PLATFORM_ADMIN` apenas `MANAGE_PLATFORM`, então ele é
    recusado no **passo 2** de `AuthorizeActionUseCase`, antes de o tradutor
    chegar ao `if not actor_tenant_id`. É exatamente por isso que a suíte mergeada
    monta o pior caso com `_SpyIdentityGuard` — identity **autorizou** e devolveu
    ator sem tenant (`test_composition_root_staff.py:485-492`). **O eixo novo
    ("tenant omitido") tem de usar o mesmo spy**: sem ele o verde vem da
    permissão ausente, e a lei fica sem trava enquanto a suíte parece cobri-la.
  - **Como o tradutor lê o tenant do ator sob `Actor = object` e mypy strict.** O
    ator é o `AuthenticatedActor` de identity, que mora sob o pacote `in` (keyword
    Python) e **não é alcançável por import estático** — `actor.claims.tenant_id`
    é erro de tipo em `strict`. O caminho já usado neste módulo para o mesmo
    problema é o campo `identity_guard: Any` do contêiner, com `noqa: ANN401` e
    docstring explicando a medição (LAYOUT §8): a leitura acontece por uma
    variável intermediária anotada, **sem** `cast` de conveniência e **sem**
    mudar a assinatura do port. Se durante a execução aparecer forma melhor, é
    `[decision]` na §7 — **não** pedido de escopo extra no meio da Task.
  - **Cobrar as duas implementações com conjuntos de valores diferentes é o sinal
    de alerta mais forte da família "lei universal, representante estreito"** e foi
    como a 3.4 vazou duas mutações: o `parametrize` das duas suítes tem de ser
    **comparável linha a linha**.
  - **Fora do alcance do `make typecheck`** (`mypy src/ tests/fakes/`), e portanto
    só o `pytest` os pega: `tests/unit/features/staff/application/test_access_guard_laws.py`
    e `tests/unit/features/staff/adapters/test_composition_root_staff.py`.
- **Critério de aceite:**
  - Com `tenant_id` omitido, `authorize` devolve escopo cujo `tenant_id` é o do
    ator, nas **duas** implementações, e o resultado é **igual** ao da chamada que
    nomeia o mesmo tenant.
  - Ator sem tenant continua **negado** com tenant omitido **e** com tenant
    nomeado (L-AG3 preservada nos dois eixos, nas duas implementações).
  - O docstring do port declara o significado de `tenant_id=None` e cita o
    ADR 0.0.0005.
  - `test_composition_root_staff.py` e `test_access_guard_laws.py` têm o mesmo
    eixo `nomeado × omitido` — verificável comparando os `parametrize`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  uv run pytest tests/unit/features/staff/application/test_access_guard_laws.py tests/unit/features/staff/adapters/test_composition_root_staff.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): resolver o tenant do ator nas duas implementacoes do AccessGuard [3.6/task-01]`

---

### Task 02 — schemas de boundary e os conversores da borda

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/in/__init__.py`
  - `src/restaurant_hub/features/staff/adapters/in/http/__init__.py`
  - `src/restaurant_hub/features/staff/adapters/in/http/schemas.py`
  - `tests/unit/features/staff/adapters/test_http_schemas.py`
- **Arquivos a modificar:**
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **O que fazer:** os 9 requests e os 2 responses do concept §4.2, mais os
  conversores que a borda possui (ADR 3.6.0003).
  1. **Requests** exatamente como a tabela de §4.2. `WorkloadProfilePayload` é
     **união discriminada por `type`** (`fixed` com `weekly_hours: str`,
     `on_demand` sem ele). `DeclareShiftPreferenceRequest.shift_preference`
     **sem default** — com default, um corpo `{}` limparia a preferência em
     silêncio. **Nenhum request tem `tenant_id`** nem alias dele.
  2. **Responses** `JobFunctionResponse` e `EmployeeResponse`, montados a partir
     de `JobFunctionResult`/`EmployeeResult` — **nunca** de entidade de domínio.
     Os **dois** campos derivados de `frozenset` saem ordenados, cada um com chave
     nomeada: `job_function_ids` pelo próprio id; `shift_preference` pela **ordem
     de declaração do enum `DayPeriod`**.
  3. **Conversor de `weekly_hours`** (texto → `Decimal`) que captura
     `decimal.InvalidOperation` e levanta `InvalidWeeklyHoursError`; e que, por
     **D-3B1**, recusa valor com espaço em volta em vez de aparar.
  4. `start`/`end` viajam **ingênuos**: um valor com `Z` ou offset é parsado como
     tz-aware e recusado por `UnavailabilityPeriod` (422), **não** convertido.
  5. Em `test_composition_root_staff.py`, **retirar apenas** a asserção
     `not (_SRC / "features" / "staff" / "adapters" / "in").exists()` do
     `test_ca21_...`, que esta Task torna falsa por construção, **preservando** as
     outras duas (o wiring ainda devolve o router de identity, e nenhuma rota de
     staff está registrada) — elas só saem na Task 09. Renomear o teste para o que
     ele passa a provar.
- **Detalhes técnicos:**
  - Pydantic **só aqui** (LAYOUT §7; skill `fastapi-thin-adapter`). Nenhum schema
    entra em use case; nenhum DTO de application é usado como schema.
  - A conversão texto → value object acontece no **router** (Task 05+), não no
    schema: é o que faz a falha ser erro de **domínio** e não
    `RequestValidationError`, que tem outro corpo (regra herdada do `router.py` de
    identity). Os conversores desta Task são funções puras que o router chama.
  - `weekly_hours` viaja como **string** nos dois sentidos, preservando a escala
    que a 3.3 provou sobreviver ao round-trip.
- **Critério de aceite:**
  - Varredura de `model_fields` de **todos** os `*Request` do módulo (derivados por
    introspecção, não listados) não encontra `tenant_id` nem os aliases
    `restaurant_id`, `tenant`, `restaurant` — **CA02(a)**.
  - **A mesma varredura recusa `user_id` e `employee_user_id`**, e a razão é
    diferente da anterior: não é sobre tenant, é sobre o `non_goal` **vínculo de
    login**, que a Stage 3.5 vai acrescentar. O concept §4.3 é honesto ao chamar a
    ausência de *"hoje vacuamente verdadeiro"*; só vira **trava** se o nome
    estiver na lista negra, e é este item que a converte de declaração em check.
  - `{"type":"on_demand","weekly_hours":"40"}` e `{"type":"fixed"}` são recusados;
    os dois payloads válidos produzem o VO correspondente — **CA06**.
  - `"22.50"` sobrevive em **valor e escala**; os dois campos de conjunto saem
    iguais a `sorted(esperado, key=<chave declarada>)` — **a asserção é contra a
    lista esperada, não entre duas execuções** (iteração de `frozenset` é
    determinística dentro de um processo, então a comparação entre execuções
    passaria com ou sem `sorted` e não mataria a mutação) — **CA04**.
  - `"abc"`, `""`, `"40,5"` → `InvalidWeeklyHoursError`; `"  40  "` também
    (**D-3B1**); `"NaN"`/`"Infinity"` continuam recusados por
    `FixedSchedule.__post_init__`.
  - Nenhum módulo do pacote `adapters/in/http` importa símbolo de
    `staff.domain.entities` — varredura de **imports** sobre os módulos que o
    pacote **contém** (derivada, portanto cresce com as Tasks seguintes) —
    **CA05**.
  - `make check` verde: o pacote `in/` nasce sem quebrar `layout-check` nem
    `lint-imports`.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/test_http_schemas.py tests/unit/features/staff/adapters/test_composition_root_staff.py -v
  uv run mypy src/ tests/fakes/
  uv run python scripts/check_layout.py; uv run lint-imports
  make check
  ```
- **Commit:** `feat(staff): schemas de boundary e conversores da borda HTTP [3.6/task-02]`

---

### Task 03 — mapa total de status e handler único de `StaffError`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/in/http/error_handlers.py`
  - `tests/unit/features/staff/adapters/test_http_error_handlers.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** replicar o desenho do `error_handlers.py` de identity, no
  arquivo da feature de staff (ADR 3.4.0002, decidido na 3.4 e **executado aqui**):
  `STAFF_ERROR_STATUS: dict[type[StaffError], int]` **total**, com as **18**
  entradas do concept §6.1; `resolve_status` percorrendo o `__mro__` com default
  422; `build_error_response`; e `register_staff_error_handlers(app)` registrando
  **um** handler sobre `StaffError`.
- **Detalhes técnicos:**
  - **Staff não registra entrada 401 nem 403.** As duas faixas são de identity,
    cujo handler está registrado sobre a **app** e é alcançado por MRO (concept
    §5.8). Uma entrada 401/403 aqui criaria uma segunda faixa distinguível.
  - As cinco classificações que têm leitura alternativa plausível são **consumidas
    do ADR 3.4.0002 §4, não re-decididas**: `UnavailabilityNotFoundError` = 422
    (herda **só** de `StaffError`, precisamente para que a MRO não a leve ao 404),
    `OverlappingUnavailabilityError` = 422, `SameUnitCopyError` = 422,
    `EmployeeRelocationError` = 422, e o par `InUse` = 409.
  - `EmployeeInUseError` continua **sem produtor** em v1 e `EmployeeRelocationError`
    é **inalcançável por HTTP** nesta Stage: têm entrada por **totalidade**, e a
    inalcançabilidade fica no docstring para que ninguém escreva e2e esperando
    produzi-las.
  - **`build_error_response` emite um discriminador de corpo próprio
    (`"type": "staff_error"`), e ele é infraestrutura de teste, não enfeite.**
    Na faixa 422 esta app tem **duas** origens: um erro de staff e o
    `RequestValidationError` do framework, que o handler compartilhado renderiza
    com corpo **constante** — `{"detail": "requisição inválida", "type":
    "validation_error"}`, em
    `shared/infrastructure/http/error_handlers.py:37`. O ADR 3.6.0002, ao
    rejeitar a Alternativa A, já nomeava a diferença: *"a **different body
    shape**"*, *"dois formatos **distinguíveis** para a mesma classe de
    defeito"*. É esse discriminador que as varreduras da Task 05 asserem — sem
    ele, um 422 do framework satisfaz um critério de segurança de staff.
- **Critério de aceite:**
  - **CA17** — o teste enumera **recursivamente** as subclasses concretas de
    `StaffError` (raiz excluída) e exige entrada **própria** para cada uma; classe
    nova sem entrada **reprova**.
  - **CA18** — verificação **par a par** classe→status, parametrizada sobre as 18
    entradas. *(Trocar duas entradas dentro de uma faixa já exercitada sobreviveria
    a um teste que só olha faixas.)*
  - Teste dedicado falha se alguém fizer `UnavailabilityNotFoundError` herdar de
    `NotFoundError` (metade estrutural de **CA19**; a metade pelo HTTP real é da
    Task 11).
  - **Prova por mutação (metade (c) de CA33), com a saída colada no relatório:**
    trocar duas entradas dentro da **mesma** faixa e exigir vermelho.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/test_http_error_handlers.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): mapa total de status e handler unico de StaffError [3.6/task-03]`

---

### Task 04 — validador de identificador, requisito de acesso por rota e provedor de ator

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/in/http/dependencies.py`
  - `tests/unit/features/staff/adapters/test_http_dependencies.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** as três peças que o router consome (ADR 3.6.0002):
  1. **Validador único de identificador** — recebe o valor cru de um identificador
     vindo da requisição (path, query **ou** corpo) e devolve a string validada,
     levantando `InvalidIdentifierError` quando é **vazio**, **só-whitespace** ou
     contém o **byte NUL**. Nada além disso é normalizado, aparado ou reescrito.
  2. **Declaração de requisito de acesso por rota** — o par (permissão, alvo)
     como **valor** (`"manage_staff"`, `"manage_job_functions"`), jamais como enum
     importado de identity, mais o formato de `Depends` que o router usa. Não há
     tabela de papéis nem lógica de bypass neste arquivo.
  3. **Provedor de ator** — `Depends` que chama `AccessGuard.authenticate`, para
     que a autenticação aconteça **antes** da validação do corpo contra o schema
     (concept §5.1: `Depends`, nunca middleware — ADR 2.4.0003).
  4. **Helper de introspecção de campos de id** (`*_id` / `*_ids`) sobre os
     schemas de request, usado pelas varreduras da Task 05 — para que campo novo
     entre na varredura sem ninguém lembrar.
- **Detalhes técnicos:**
  - **A ordem é contrato, não detalhe: autenticar → validar → autorizar.** Validar
    antes de autorizar é o que impede um valor cru de alcançar `units.find_by_id`
    **dentro de identity** (passo 5 de `AuthorizeActionUseCase`), onde `psycopg`
    recusa o NUL client-side com `DataError` — que não é `IntegrityError`, não é
    `StaffError` e não é `IdentityError`, e portanto vira **500**.
  - **Não dobrar o tenant neste validador.** O tenant nunca chega pela requisição
    (concept §5.3).
  - O docstring do módulo tem de explicar por que a validação é de adapter e não
    de domínio (`NewType` não tem gancho de runtime; um id nunca passa por
    entidade) — sem isso, um refactor futuro a "limpa" (ADR 3.6.0002
    §Consequences).
  - **Limite medido, e declarado para não virar critério impossível:** id **vazio**
    em segmento de **path** não casa `[^/]+`, e Starlette responde 404/405 sem que
    o handler rode. É por isso que o eixo de path exclui `""`.
- **Critério de aceite:**
  - O validador rejeita `""`, `"   "` e `"\x00"` com `InvalidIdentifierError`, e
    aceita **verbatim** o conjunto adversarial da 3.3 (acento, ZWJ, aspas, `\n`,
    1000 caracteres) — a restrição não cresceu.
  - O helper de introspecção devolve, para os schemas de request, exatamente
    `target_unit_id` e os elementos de `job_function_ids` — derivado, não listado.
  - Nenhum módulo de `features/staff/` importa `features.identity` nem nomeia
    `Role`/`Permission`: `lint-imports` verde e `test_bc_independence.py`
    continua passando **sem nenhum `ignore_imports`** — **CA07**.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/test_http_dependencies.py tests/unit/features/staff/test_bc_independence.py -v
  uv run lint-imports; uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): validador de identificador e requisito de acesso da borda [3.6/task-04]`

---

### Task 05 — as quatro rotas de catálogo (RJF) e as varreduras derivadas de rota

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/in/http/router.py`
  - `tests/unit/features/staff/adapters/test_http_router_job_functions.py`
  - `tests/unit/features/staff/adapters/test_http_boundary_sweeps.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  1. **O `router.py`** com os provedores `_get_*` (chaves do
     `dependency_overrides`, que levantam se chamados de verdade — o padrão de
     identity) e as **quatro** rotas de RJF do concept §4.1: `POST /job-functions`
     (201), `GET /job-functions` (200), `PATCH /job-functions/{job_function_id}`
     (200), `DELETE /job-functions/{job_function_id}` (204). Permissão
     `"manage_job_functions"`; alvo **tenant, sem unidade**.
  2. **Os testes de rota** com app mínima montada sobre o `InMemoryAccessGuard` e
     os fakes de repositório (o padrão de `test_http_router.py` de identity):
     caminho feliz, erro de domínio e o mapeamento de status pelo handler.
  3. **A fixture de invocação, e a totalidade dela — sem isto as varreduras do
     item 4 ficam verdes sem trava nenhuma.** Um `_INVOCACOES: dict[<chave de
     rota>, Invocacao]` que dá, **por rota**, um corpo e uma query **válidos**.
     Travada por **totalidade derivada**, no mesmo padrão que CA17 aplica às
     exceções:
     ```
     assert set(_INVOCACOES) == {chave(rota) for rota in router.routes}
     ```
     Chave faltando **reprova** — é o que obriga a Task que escreve uma rota nova
     a declarar como invocá-la, em vez de deixá-la entrar muda na varredura.
  4. **O módulo de varreduras** — o coração da estratégia. **Nenhum `parametrize`
     lista rota ou campo à mão:**
     - **CA01** — as rotas de `router.routes` batem, uma a uma, com a tabela de
       §4.1 em método e status de sucesso, e cada uma chama **exatamente um** use
       case.
     - **CA02(b)** — varredura do `router.py` provando que o `tenant_id` de **todo**
       command/query construído vem de `AuthorizedScope.tenant_id` e de nenhuma
       outra origem. *(Sem esta metade, um campo `restaurant_id` de corpo consumido
       pelo router passaria pela lista negra de CA02(a).)*
     - **CA14** — varredura por **AST** do módulo do router: nenhum acesso ao
       atributo `unit_id` **sobre o objeto devolvido pelo guard**. Procurar o
       atributo na expressão do escopo, **não** a string `unit_id` no arquivo —
       parâmetros de path se chamam legitimamente `unit_id`. Declarar no docstring
       que isto é **defesa em profundidade, não a trava**: `getattr`, `astuple` e
       `asdict` a contornam; a trava é CA15 (Task 06).
     - **CA20** — identificador inválido → 422 **com o corpo de erro de staff**,
       com o domínio enumerado **por eixo** e valores **diferentes** por eixo:
       **path** = `RID × {"   ", "\x00"}` (RID derivado de `router.routes`; `""`
       fora, por medição); **query** = `{params de query com id} × {"", "   ",
       "\x00"}`; **corpo** = `{campos de id derivados por introspecção} × {"",
       "   ", "\x00"}`. **Cada caso invoca a rota pelo `_INVOCACOES`** — corpo e
       query válidos, só o identificador sob teste corrompido — e assere
       `type == "staff_error"`, **nunca só o status**.
     - **CA21** — a validação roda **antes de autorizar**, provada pela **ausência
       de chamada**: com `InMemoryAccessGuard.calls`, uma requisição com
       identificador inválido não produz **nenhuma** entrada `authorize(`. A
       asserção é sobre `authorize`, **não** `calls == []` — o fake registra também
       `authenticate`, que §5.1 exige que rode primeiro.
     - **CA23** — nenhum módulo do adapter chama `DayPeriod(...)` diretamente (AST).
     - **CA24** — nenhum campo escalar de request nem parâmetro de query devolve
       500 para o conjunto adversarial da 3.3 mais os numéricos degenerados
       (`"abc"`, `""`, `"40,5"`, `"NaN"`, `"Infinity"`, `"-1"`, `"0"`), com o
       domínio **derivado por introspecção** e a invocação vinda do `_INVOCACOES`.
       Onde o valor degenerado é recusado, a asserção inclui o **corpo de staff**.
     - **CA05** — a varredura de imports da Task 02, agora alcançando `router.py`
       por já estar no pacote.
- **Detalhes técnicos:**
  - **Todas as varreduras derivam o domínio do código.** É o que faz uma rota
    escrita nas Tasks 06/07/08 entrar automaticamente na trava, e é a razão de este
    módulo nascer com 4 rotas em vez de 16.
  - **Por que a fixture de invocação é pré-requisito da estratégia, e não
    conforto.** Das 14 rotas de RID, **oito têm corpo obrigatório** (R05, R08,
    R09, R10, R11, R13, R14, R16) e R12 exige `start`/`end` na query. Invocada sem
    corpo válido, qualquer uma delas responde **422 pelo `RequestValidationError`
    do framework** — ou seja, uma varredura que assere só `status == 422` fica
    **verde mesmo com o validador de identificador ausente**: a rota nova da
    Task 07 não reprovaria a si mesma, e a mutação (b) de CA33 sobreviveria no
    eixo de path. **Duas defesas, e as duas são necessárias:** invocar sempre
    pelo `_INVOCACOES` (para que o 422 do framework não apareça) e asserir o
    **discriminador de corpo** de staff (para que, se aparecer, não conte).
  - O `unit_id` das rotas de RJF é **ausente** por desenho: `manage_job_functions`
    está em `TENANT_WIDE_PERMISSIONS` (ADR 3.4.0008), e o passo 4 de
    `AuthorizeActionUseCase` dispensa a unidade **por permissão**.
  - **CA08 (401 com corpo constante) não cabe aqui**, e a razão é medida: o fake
    levanta a sua própria sentinela, que **não** é `IdentityError` e não tem
    handler. A propriedade depende do handler de identity registrado sobre a app,
    e por isso vive no e2e (Task 11).
- **Critério de aceite:**
  - CA01, CA02(b), CA14, CA20, CA21, CA23, CA24 e CA05 verdes sobre o domínio
    **derivado**; as quatro rotas de RJF com caminho feliz e faixas de erro
    cobertos.
  - **`set(_INVOCACOES) == {chave(r) for r in router.routes}`** — a totalidade da
    fixture é asserção, não convenção.
  - **Nenhuma asserção de CA20/CA23/CA24 é status-only:** cada uma exige o corpo
    de erro de staff (`type`/`detail` de `build_error_response`).
  - **Prova por mutação (metade (b) de CA33), com a saída colada:** condicionar a
    validação de identificador a um único eixo (só path, ou só `employee_id`) e
    exigir vermelho em CA20. **Se a mutação ficar verde, a causa mais provável é
    invocação sem corpo válido** — o falso verde que a fixture existe para fechar
    —, e isso é blocker, não ajuste.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/test_http_router_job_functions.py tests/unit/features/staff/adapters/test_http_boundary_sweeps.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): rotas de catalogo de funcao e varreduras de borda [3.6/task-05]`

---

### Task 06 — CRUD de funcionário e o dublê adversarial que trava o endereçamento

- **Arquivos a criar:**
  - `tests/fakes/features/staff/adversarial_access_guard.py`
  - `tests/unit/features/staff/adapters/test_http_router_employees.py`
  - `tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/adapters/in/http/router.py`
- **O que fazer:**
  1. **As quatro rotas de CRUD** sob `/units/{unit_id}/employees`: `POST` (R05,
     201), `GET` com `include_inactive` (R06, 200), `PATCH /{employee_id}` (R07,
     200), `DELETE /{employee_id}` (R15, 204). Permissão `"manage_staff"`; alvo
     **tenant + unidade do path**.
  2. **O dublê adversarial** (D-3B2): implementação do `AccessGuard` que devolve
     `AuthorizedScope` cujo `unit_id` é **diferente** do pedido, e um segundo modo
     que devolve `None`. Docstring declarando que ele **contradiz de propósito** o
     tradutor de produção e o `InMemoryAccessGuard`, e por quê — os dois **ecoam**
     a unidade pedida, então nenhum deles é capaz de refutar a lei. Fechar com
     `_conforms: AccessGuard = AdversarialAccessGuard()` para pôr a conformidade
     sob `make typecheck`.
  3. **A suíte de CA15**: para **toda** rota de REMP — domínio **derivado de
     `router.routes`**, não listado —, a unidade que chega ao use case é a do
     **path**, com o dublê nos **dois** modos.
- **Detalhes técnicos:**
  - **A chamada ao guard e a construção do command leem a MESMA variável** — o
    parâmetro de path. Dois nomes para um valor é como este defeito volta
    (ADR 3.6.0001 §Implementation notes).
  - Com a suíte parametrizada sobre `router.routes`, as rotas das Tasks 07 e 08
    entram na trava sem edição de teste; se uma delas ler o escopo, é a **própria**
    Task que fica vermelha.
  - **Fora do alcance do `make typecheck`:** os dois módulos novos de
    `tests/unit/...` (o dublê, em `tests/fakes/`, **é** alcançado).
- **Critério de aceite:**
  - **CA15** — com o dublê nos dois modos, o `unit_id` do command é o do path para
    **toda** rota de REMP existente no momento da execução.
  - R05/R06/R07/R15 com caminho feliz, listagem default sem desligado, e
    `EmployeeNotFoundError` → 404 quando o id não casa a unidade do endereço.
  - **Prova por mutação (metade (a) de CA33), com a saída colada:** trocar o
    `unit_id` do path por `scope.unit_id` e exigir vermelho — **e registrar que,
    com o fake sancionado, a mesma mutação fica verde**, que é a razão de o dublê
    existir.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/test_http_router_employees.py tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py tests/unit/features/staff/adapters/test_http_boundary_sweeps.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): rotas de CRUD de funcionario e dublê adversarial do escopo [3.6/task-06]`

---

### Task 07 — perfil de jornada, preferência de turno e indisponibilidades

- **Arquivos a criar:**
  - `tests/unit/features/staff/adapters/test_http_router_employee_profile.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/adapters/in/http/router.py`
- **O que fazer:** as cinco rotas restantes de edição — `PUT /{id}/job-functions`
  (R08), `PUT /{id}/workload-profile` (R09), `PUT /{id}/shift-preference` (R10),
  `POST /{id}/unavailabilities` (R11, **200**), `DELETE /{id}/unavailabilities`
  com `start`/`end` em query (R12) —, com a construção dos value objects
  acontecendo **no router** (concept §5.5).
- **Detalhes técnicos:**
  - `PUT` para substituição e `POST` para acréscimo: `assign_job_functions`
    **substitui** o conjunto e `declare_shift_preference` com `null` **limpa** — as
    duas idempotentes; `register_unavailability` acrescenta.
  - **R11 devolve 200, não 201**: o período não é recurso endereçável, não ganha
    URL própria, e um 201 sem `Location` prometeria uma que não existe.
  - **R12 remove por igualdade de valor**, não por id (`UnavailabilityPeriod` é
    value object sem identidade) — daí os query params, que também entram no eixo
    de query de CA20 automaticamente.
  - `DayPeriod.from_string` é o **único** conversor de período do dia (concept
    §5.15); `DayPeriod(...)` direto levanta `ValueError` e vira 500. A varredura de
    AST de CA23 (Task 05) já cobre este arquivo.
- **Critério de aceite:**
  - **CA03** — `{"shift_preference": null}` limpa a preferência; corpo `{}` recebe
    422 (campo obrigatório, sem default).
  - Período do dia desconhecido → 422 em R05 **e** R10 (parte de **CA23**).
  - `start`/`end` com `Z` → 422 (`InvalidUnavailabilityPeriodError`), sem conversão
    silenciosa; período sobreposto → 422; período inexistente em R12 → **422**
    (`UnavailabilityNotFoundError`), **não** 404.
  - As varreduras da Task 05 e a CA15 da Task 06 **continuam verdes com o domínio
    ampliado**, e a única edição de teste permitida é **acrescentar a chave das
    cinco rotas novas ao `_INVOCACOES`** — que a asserção de totalidade cobra, e
    que é o ponto em que esta Task declara como as suas rotas são invocadas com
    corpo/query válidos. É este item que prova que a estratégia de domínio
    derivado funciona: sem o validador, as rotas de R08–R12 reprovam **aqui**.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/ -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): rotas de perfil, preferencia e indisponibilidade [3.6/task-07]`

---

### Task 08 — ciclo de vida e cópia, com a orientação origem→destino travada

- **Arquivos a criar:**
  - `tests/unit/features/staff/adapters/test_http_router_lifecycle_and_copy.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/adapters/in/http/router.py`
- **O que fazer:** as três últimas rotas — `POST /{id}/termination` (R13),
  `POST /{id}/rehire` (R14) e `POST /{id}/copies` (R16, 201) —, fechando as 16.
- **Detalhes técnicos:**
  - `termination`/`rehire` são **sub-recursos `POST`** porque são as duas
    transições nomeadas do ciclo de vida (ADR 3.2.0006), não edição de campo. Um
    `PATCH {"active": false}` faria a transição parecer atribuição de atributo —
    a leitura que o ADR 3.2.0007 recusa.
  - **R16 chama o guard DUAS vezes**, com alvos distintos: `unit_id` do path
    (origem) e `target_unit_id` do corpo (destino). É L-AG4 aplicada, **não
    otimizada** — reusar o escopo da origem para alcançar o destino é escalada de
    escopo.
  - O `target_unit_id` do corpo passa pelo **validador de identificador** antes de
    qualquer autorização: ele é o segundo alvo, e vai para `units.find_by_id`
    **dentro de identity**.
  - As três recusas do destino — outro tenant, inexistente, não visível — produzem
    **o mesmo** status e **o mesmo** corpo, por desenho.
- **Critério de aceite:**
  - **CA16** — duas chamadas ao guard com alvos distintos; as três recusas do
    destino indistinguíveis e **sem gravar nada**; e o caso "a **origem** não é
    visível", que mata a mutação "remover a primeira chamada".
  - **CA34 (metade unitária)** — no command de R16, `unit_id` é o do **path** e
    `target_unit_id` é o do **corpo**. *(A metade que olha **onde a cópia caiu** é
    e2e, na Task 10.)*
  - As varreduras da Task 05 e a CA15 da Task 06 cobrem agora **R01…R16** — CA01
    fecha o inventário completo, e `_INVOCACOES` fecha em 16 chaves pela asserção
    de totalidade.
  - **Prova por mutação (metade (d) de CA33), com a saída colada:** inverter origem
    e destino em R16 e exigir vermelho.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/unit/features/staff/adapters/ -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit:** `feat(staff): rotas de ciclo de vida e copia de funcionario [3.6/task-08]`

---

### Task 09 — `HttpWiring` em coleções, 17 overrides e os dois routers na app

- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
  - `src/restaurant_hub/shared/infrastructure/http/app.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:**
  1. `HttpWiring.router` → `routers`, e `register_error_handlers` → **coleção** de
     registradores. `dependency_overrides` continua **mapa único** (as chaves são
     funções distintas por BC).
  2. `build_http_wiring` carrega `router` e `error_handlers` de staff por
     `importlib` (o pacote `in` é keyword — LAYOUT §8) e acrescenta **17**
     overrides: os 16 use cases mais o `staff_access_guard`.
  3. `app.py` **itera** as coleções. Continua sem conhecer feature nenhuma.
  4. Em `test_composition_root_staff.py`, aposentar o que restou do
     `test_ca21_...` (o wiring já não devolve só o router de identity) e pôr no
     lugar as asserções de **CA30**.
- **Detalhes técnicos:**
  - **Esta é a Task que muda a forma de um objeto compartilhado.** Call sites de
    `build_http_wiring`/`HttpWiring` medidos hoje: `app.py` (em `src/`, **coberto**
    pelo mypy) e `tests/unit/features/staff/adapters/test_composition_root_staff.py`
    (linhas 615–622) — **fora** do alcance de `make typecheck`, e portanto só o
    `pytest` os pega. Nenhum outro arquivo em `tests/` referencia os dois nomes.
  - **Sem ADR, e a razão não é "não há alternativa"** (concept §7 D5): campos
    plurais e uma **lista de `HttpWiring`** são equivalentes em consequência e
    nenhuma das duas atravessa a fronteira do composition root; a terceira forma
    (staff pendurado no router de identity) é estruturalmente proibida.
  - `create_engine` não abre conexão, então registrar um segundo router **não**
    muda o comportamento de boot.
- **Critério de aceite:**
  - **CA30** — `create_app()` registra **os dois** routers e **os dois**
    registradores; o mapa de overrides tem as **17** entradas de staff; e as rotas
    de identity continuam respondendo exatamente como antes (nenhuma regressão de
    path, status ou corpo).
  - **CA31** — nenhuma suíte já mergeada regride, e **sem alteração da regex
    `_ORDER_BY`** de `tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py:194`
    (consequência do ADR 3.4.0004): `git diff` sobre esse arquivo tem de vir vazio.
  - A app sobe: `uv run uvicorn restaurant_hub.main:app` inicia com as duas
    superfícies montadas.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/ -q
  uv run mypy src/ tests/fakes/
  git diff --name-only -- tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py
  make check
  ```
- **Commit:** `feat(staff): registrar o router de staff e HttpWiring em colecoes [3.6/task-09]`

---

### Task 10 — e2e do DoD: fluxo feliz, isolamento entre unidades e a cópia que cai certo

- **Arquivos a criar:**
  - `tests/e2e/features/staff/__init__.py`
  - `tests/e2e/features/staff/conftest.py`
  - `tests/e2e/features/staff/test_staff_flow.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** o e2e contra **app real e Postgres real**, com a cadeia de setup
  alcançada **só por rotas reais**: `platform_admin` semeado pelo repositório →
  `POST /restaurants` → `POST /restaurants/{id}/owners` →
  `POST /restaurants/{id}/units` → `POST /users` com `unit_ids` (que cria a
  `UnitMembership`). O padrão está em `tests/e2e/features/identity/conftest.py`.
- **Detalhes técnicos:**
  - **O ator do fluxo feliz é `manager`, não `owner`** — é a exigência explícita de
    CA25, e é o que faz o teste medir alcance real em vez do bypass do dono.
  - `truncar_tudo` já limpa as tabelas de staff; o `TRUNCATE` roda **antes** do
    teste, para que o estado de uma falha fique disponível para diagnóstico.
- **Critério de aceite:**
  - **CA25** — `manager` autentica, cria função customizada, cria funcionário com
    jornada fixa e preferência, registra indisponibilidade e lista a unidade, tudo
    pela API.
  - **CA26** — funcionário criado na unidade A **não aparece** em
    `GET /units/B/employees`, mesmo para ator que enxerga as duas.
  - **CA27** — desligado some da listagem default e reaparece com
    `include_inactive=true`; a recontratação o devolve à listagem default.
  - **CA28** — a ordem da listagem é a de `L-ORD` e é estável entre execuções.
  - **CA34** — cópia bem-sucedida A→B: o clone aparece em `GET /units/B/employees`
    e **não** em A; o original permanece em A, inalterado; o `id` do clone difere
    do original. *(Sem este critério, a inversão origem↔destino sobrevive a CA11,
    CA13, CA16 e CA25 — nenhum deles exercita uma cópia que dá certo e olha **onde**
    ela caiu.)*
  - **CA04 pelo HTTP real** — `weekly_hours` `"22.50"` volta `"22.50"`;
    `start`/`end` voltam sem offset; os dois campos de conjunto voltam ordenados.
- **Comando de verificação:**
  ```powershell
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  uv run pytest tests/e2e/features/staff/test_staff_flow.py -v
  make check
  ```
- **Commit:** `test(staff): e2e do fluxo de equipe, isolamento e copia [3.6/task-10]`

---

### Task 11 — matriz papel × rota e acesso negado pela API real

- **Arquivos a criar:**
  - `tests/e2e/features/staff/test_staff_authorization.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** o eixo de **quem alcança o quê**, pelo entrypoint real,
  **sempre parametrizado sobre o domínio enumerado** — as rotas derivadas de
  `router.routes` e os cinco papéis do concept §5.13.
- **Detalhes técnicos:**
  - Cada critério abaixo é um produto cartesiano explícito, não uma amostra. É o
    ponto em que esta Stage multiplica representantes (16 rotas × 5 papéis × 2
    permissões), e é onde o conceito *"lei universal, representante estreito"*
    cobra o preço.
  - `hr` ≡ `manager` **dentro** de staff (ADR 3.4.0006 §1) é decisão, não omissão:
    CA12 a trava como propriedade, não como comentário.
  - **Por que esta Task não carrega também as faixas de status.** São dois
    assuntos — *quem pode alcançar* e *como o erro é classificado* — e só os
    produtos desta Task somam ~100 casos e2e contra Postgres real. Para calibrar:
    a suíte e2e inteira de identity, mergeada, tem 1498 linhas em 5 arquivos.
    Juntá-las produziria um commit que nenhum revisor lê e cujo vermelho não diz
    qual dos dois assuntos quebrou.
- **Critério de aceite:**
  - **CA08** — toda rota **sem** Bearer recebe 401 com corpo constante e
    `WWW-Authenticate: Bearer`; o teste **enumera** `router.routes`, não uma
    amostra.
  - **CA09** — `employee` e `platform_admin` recebem **403** nas 16 rotas: produto
    `{employee, platform_admin} × R01…R16` = **32 casos**, não dois.
  - **CA10** — `manager` real **alcança** as 16 rotas na sua unidade e no catálogo
    do seu tenant: **nenhuma** resposta é 401/403. *(É o teste de não-regressão do
    alcance que o ADR 0.0.0005 comprou.)*
  - **CA11** — `owner` alcança as 16, inclusive em unidade da qual **não é
    membro**, e o efeito recai sobre a unidade do **path**. Parametrizado sobre
    REMP.
  - **CA12** — `hr` e `manager` produzem status **idêntico** nas 16 rotas, sobre o
    mesmo estado.
  - **CA13** — isolamento nos **dois** endereços e com os **dois** status corretos:
    **404** ao endereçar pela própria unidade A o `employee_id` de B; **403** ao
    endereçar pela unidade B, da qual não é membro — e o mesmo 403 para unidade
    **inexistente**, indistinguíveis por desenho.
  - **CA36** — **nenhuma** das 16 rotas produz `TenantScopeRequiredError`, para
    **nenhum** dos papéis que detêm permissão de staff: produto
    `{owner, manager, hr} × R01…R16`.
  - **CA29** — ator `employee` autenticado recebe 403 ao criar função e ao listar
    funcionários, **pela API**, não por unit test.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/e2e/features/staff/test_staff_authorization.py -v
  make check
  ```
- **Commit:** `test(staff): matriz papel x rota e acesso negado pela API real [3.6/task-11]`

---

### Task 12 — faixas de status pela API real

- **Arquivos a criar:**
  - `tests/e2e/features/staff/test_staff_status_bands.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** o eixo de **como o erro é classificado**, pelo HTTP real — as
  três faixas do concept §6.1, o NUL em nome, e a metade e2e de CA24. É o espelho
  de `tests/e2e/features/identity/test_status_bands.py`, que já existe mergeado.
- **Detalhes técnicos:**
  - **"Pelo HTTP real" é o ponto do critério**, e não redundância com a Task 03:
    ali o mapa é verificado par a par contra o dicionário; aqui prova-se que a
    exceção **atravessa** o handler registrado, com o corpo que
    `build_error_response` monta.
  - **O domínio de CA22 é derivado, não listado.** As rotas que aceitam nome saem
    do helper de introspecção da Task 04 — schemas cujo `model_fields` contém
    `name` —, exatamente como o eixo de corpo de CA20 deriva os `*_id`. Listar
    "R01, R03, R05, R07" deixaria uma quinta rota que aceite nome escapar em
    silêncio, no documento cuja tese é derivar.
  - As asserções incluem o **corpo** de staff (`type`/`detail`), nunca só o
    status — mesma razão da Task 05.
- **Critério de aceite:**
  - **CA19** — cada uma das três faixas de §6.1 exercitada pelo **HTTP real**
    (não por chamada direta ao handler), e `UnavailabilityNotFoundError`
    respondendo **422**.
  - **CA22** — nome contendo `\x00` recebe 422 pelo HTTP real em **todas** as
    rotas que aceitam nome, **domínio derivado por introspecção** — não só nas
    duas de criação.
  - **CA24 (metade e2e)** — nenhum campo escalar de request nem parâmetro de
    query devolve 500 pela API real, sobre o conjunto adversarial e os numéricos
    degenerados.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/e2e/features/staff/test_staff_status_bands.py -v
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
  make check
  ```
- **Commit:** `test(staff): faixas de status do BC staff pela API real [3.6/task-12]`

## 2.1 Matriz de rastreabilidade

**Regra:** nada órfão nos dois sentidos — todo critério, ADR de fundação e finding
herdado tem ao menos uma Task que o entrega, e nenhuma Task existe sem item que a
justifique.

### Critérios de aceite do concept §11 → Task

| Critério | Task(s) | Onde o check acontece |
|---|---|---|
| CA01 — as 16 rotas, método e status de sucesso, um use case por rota | **05** (derivado) → fecha em **08** | `test_http_boundary_sweeps.py`, parametrizado sobre `router.routes` |
| CA02 — nenhum campo de request influencia o tenant (metades **a** e **b**) | **02** (a) + **05** (b) | varredura de `model_fields`; varredura do `router.py` |
| CA03 — `shift_preference: null` limpa; corpo `{}` recebe 422 | **07** | `test_http_router_employee_profile.py` |
| CA04 — round-trip de escala, datetimes ingênuos e os **dois** campos ordenados | **02** (unit) + **10** (HTTP real) | asserção contra `sorted(esperado, key=…)`, nunca entre execuções |
| CA05 — sem import de `domain.entities`; nenhum schema em use case | **02** (derivado sobre o pacote) | varredura de **imports** dos módulos do pacote |
| CA06 — união discriminada do perfil de jornada | **02** | `test_http_schemas.py` |
| CA07 — `bc-independence` sem `ignore_imports`; sem `Role`/`Permission` | **04** + todas (via `make check`) | `test_bc_independence.py` + `lint-imports` |
| CA08 — 401 com corpo constante e `WWW-Authenticate` em **todas** as rotas | **11** | e2e, domínio derivado de `router.routes` |
| CA09 — `employee` e `platform_admin` → 403 nas 16 (32 casos) | **11** | `test_staff_authorization.py` |
| CA10 — `manager` alcança as 16 (nenhum 401/403) | **11** (habilitado pela **01**) | idem |
| CA11 — `owner` alcança as 16, e o efeito recai na unidade do path | **11** | idem, parametrizado sobre REMP |
| CA12 — `hr` ≡ `manager` nas 16 | **11** | igualdade de status entre os dois papéis |
| CA13 — isolamento nos dois endereços, com 404 **e** 403 | **11** | idem |
| CA14 — nenhum handler lê `AuthorizedScope.unit_id` (AST) | **05** | `test_http_boundary_sweeps.py` |
| CA15 — a unidade do use case é a do **path**, com **dublê adversarial** | **06** (domínio derivado; cresce em 07/08) | `test_http_path_addresses_the_record.py` + `adversarial_access_guard.py` |
| CA16 — R16 chama o guard duas vezes; três recusas indistinguíveis | **08** | `test_http_router_lifecycle_and_copy.py` |
| CA17 — mapa **total** por enumeração recursiva de subclasses | **03** | `test_http_error_handlers.py` |
| CA18 — verificação **par a par** classe→status (18 entradas) | **03** | idem |
| CA19 — as três faixas pelo HTTP real; `UnavailabilityNotFound` = 422 | **12** (+ guarda de MRO na **03**) | `test_staff_status_bands.py` |
| CA20 — identificador inválido → 422, três eixos com valores diferentes | **04** (validador) + **05** (varredura derivada) | `test_http_dependencies.py` + sweeps |
| CA21 — validar **antes** de autorizar, provado por ausência de `authorize(` | **05** | sweeps, sobre `InMemoryAccessGuard.calls` |
| CA22 — `\x00` em nome → 422 em **todas** as rotas que aceitam nome (derivadas) | **12** | `test_staff_status_bands.py` |
| CA23 — período do dia desconhecido → 422; nenhum `DayPeriod(...)` direto | **05** (AST) + **07** (comportamento) | sweeps + testes de rota |
| CA24 — nenhum campo escalar devolve 500 (domínio por introspecção) | **05** (unit) + **12** (e2e) | sweeps + e2e |
| CA25 — e2e feliz com ator **`manager`** | **10** | `test_staff_flow.py` |
| CA26 — funcionário de A não aparece em `GET /units/B/employees` | **10** | idem |
| CA27 — desligado some da default e volta com `include_inactive` | **10** | idem |
| CA28 — ordem de `L-ORD`, estável entre execuções | **10** | idem |
| CA29 — `employee` recebe 403 pela API real | **11** | `test_staff_authorization.py` |
| CA30 — dois routers, dois registradores, 17 overrides, identity intacta | **09** | `test_composition_root_staff.py` |
| CA31 — nenhuma suíte mergeada regride; regex `_ORDER_BY` intocada | **09** + §3 | `pytest tests/` + `git diff` do arquivo |
| CA32 — `make check` verde e cobertura ≥ 90% por arquivo | **todas** + §3 | comando de verificação de cada Task |
| CA33 — prova por **mutação** das quatro leis mais críticas | (a) **06** · (b) **05** · (c) **03** · (d) **08** | saída colada no relatório final |
| CA34 — a cópia cai na unidade certa | **08** (unit) + **10** (e2e) | command + `GET /units/B/employees` |
| CA36 — nenhuma rota produz `TenantScopeRequiredError`; lei nas duas implementações | **11** (rotas) + **01** (as duas implementações) | e2e `{owner,manager,hr} × R01…R16` + as duas suítes de lei |

> **A fixture `_INVOCACOES` não é critério do concept, e mesmo assim é gate.** Ela
> é a **pré-condição de validade** de CA20, CA22, CA23 e CA24: sem corpo/query
> válidos por rota, os quatro ficam verdes contra o 422 do `RequestValidationError`
> em vez do erro de staff. A totalidade dela (`set(_INVOCACOES)` == chaves de
> `router.routes`) é o mesmo mecanismo que CA17 aplica às exceções — e removê-la
> porque "uma rota nova não tem chave" é o mesmo movimento que relaxar CA17 porque
> "um erro novo não tem entrada": **blocker**, não ajuste.

> **CA35 não existe** — foi aposentado por errata (concept §7 D6 e a nota ao fim da
> §11). Número de critério é identidade e **não recicla**. Uma linha para ele nesta
> matriz seria a ambiguidade que esta Stage existe, em parte, para consertar.

### ADRs de fundação → Task que os efetiva

| ADR | O que decide | Task(s) |
|---|---|---|
| **0.0.0005** (global) | o tenant vem do token; resolução no `composition_root`; a lei vale nas **duas** implementações | **01** (cláusulas 1 e 3) · **11** (CA10/CA36 provam o alcance) · cláusula 2 = o inventário de §4.1, entregue por **05**–**08** |
| **3.6.0001** | §1–§3 o path endereça o registro; §4 trava estrutural (AST) | **05** (CA14) |
| | §4 trava comportamental + §5 **dublê adversarial obrigatório** | **06** (CA15) |
| | §Implementation notes: guard e command leem a **mesma** variável | **06**, **07**, **08** |
| **3.6.0002** | §1–§2 validador único, três valores rejeitados | **04** |
| | §3–§4 ordem autenticar→validar→autorizar, provada por ausência | **05** (CA21) |
| | §5 cobertura enumerada por eixo, com valores distintos por eixo | **05** (CA20) |
| | §6 nada além dos três é normalizado | **04** + **02** (D-3B1 aplica a mesma regra a `weekly_hours`) |
| **3.6.0003** | §Decision 1 união discriminada; 2 conversor de `weekly_hours`; 3 datetimes ingênuos; 4 os **dois** campos ordenados | **02** |
| | §Decision 5 CA04 assere contra a lista esperada, não entre execuções | **02** + **10** |
| **3.4.0002** (decidido na 3.4, **executado aqui**) | handler único, mapa total por MRO, par a par, `UnavailabilityNotFound` = 422, 409 só para estado gravado | **03** (+ **12** para o HTTP real) |
| **3.4.0004** (idem) | sem paginação; `L-ORD` intocada; regex `_ORDER_BY` sem antídoto | **09** (CA31) + **10** (CA28) — **nenhuma Task acrescenta `LIMIT`/`OFFSET`** |
| **3.4.0005** (idem) | cópia repetida = limite declarado, sem guarda e sem campo informativo | **nenhuma Task** — consumido como decidido; §5 registra o risco de alguém "consertá-lo" |
| **3.4.0001** | tradutor no composition root, sem `try/except` (L-AG1/L-AG2) | **01** (preservado ao mexer no tradutor) |
| **3.4.0006** | `hr` ≡ `manager` dentro de staff | **11** (CA12) |
| **3.4.0007** | a unidade no endereço do funcionário | **06**, **07**, **08** (path) + **11** (CA13) |
| **3.4.0008** | permissão tenant-wide dispensa escopo de unidade | **05** (alvo sem unidade em RJF) + **11** (CA10) |
| **2.4.0003** | autorização por `Depends`, nunca middleware | **04** + todas as Tasks de rota |
| **2.3.0005** | nada de normalização silenciosa | **02** (D-3B1) + **04** |
| **2.3.0001** | testes de integração/e2e exigem Postgres real, sem skip | **Pré-condições** (toda Task) + **10**, **11** |
| **3.3.0003** (`L-ORD`) | ordem total como lei de port | **10** (CA28) — consumida, não estendida |

### Findings herdados (issue #43 e §7 da 3.4) → disposição

| # | Finding | Disposição |
|---|---|---|
| 1 | `AuthorizedScope.unit_id is None` **não** é "tenant-wide" | **Tasks 05 (CA14) e 06 (CA15)**, sob ADR 3.6.0001 |
| 2 | identificador com NUL/vazio vira **500 dentro de identity** | **Tasks 04 e 05**, sob ADR 3.6.0002 |
| 3 | `DayPeriod.from_string` sem produtor em produção | **Tasks 05 (AST) e 07 (comportamento)** |
| 4 | leitura de funcionário por id | **avaliada e recusada** (concept §7 D7): `non_goals` do roadmap; segue como `[finding]` do concept §10 para a primeira Stage de frontend. **Nenhuma Task** |
| 5 | ponteiros de CA dos ADRs pré-corte defasados | **já entregue nesta branch** pelo commit `6aeb0bd`, antes da Task 01 (concept §7 D6) |
| — | `CONVENTIONS` §Idioma × a suíte de testes | **fora do escopo** desta Stage, por decisão registrada no concept §10; vira issue de documentação. **Nenhuma Task** |

### `non_goals` do roadmap → nenhuma Task, e a verificação de que não vazaram

| `non_goal` | Como se prova que não vazou |
|---|---|
| paginação | nenhuma Task acrescenta `LIMIT`/`OFFSET`; CA31 exige a regex `_ORDER_BY` **intocada**, e o `git diff` do arquivo entra no gate da Task 09 |
| guarda de duplicidade na cópia | Task 08 não tem critério sobre nome repetido no destino; homônimos são legítimos (ADR 3.4.0005) |
| leitura de funcionário por id | CA01 fecha o inventário em **16** rotas derivadas de `router.routes`; uma 17ª reprova |
| vínculo de login (`user_id`, `IdentityGateway`) | `user_id` e `employee_user_id` entram na **lista negra** de CA02(a) na Task 02 — sem isso a varredura só reprovaria os aliases de tenant, e a célula seria vazia (o concept §4.3 chama a ausência de *"hoje vacuamente verdadeiro"*; é a Task 02 que a converte em trava). Nenhum port novo nasce |

> **Se algum destes se mostrar necessário durante a Fase 4, é `[finding]` na §7 —
> não Task.** Escopo estrito (PIPELINE §4.3): tocar arquivo fora da lista da Task
> exige **parar e perguntar**.

## 3. Gate de saída da Stage

### Verificações automatizadas

```powershell
$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
docker compose up -d postgres          # sem skip (ADR 2.3.0001)
do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
make check                             # lint + typecheck + layout + import + lock + docs + test-gate
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
uv run python scripts/check_technical_postexec.py docs/stages/3.6-staff-http/technical.md
git diff --name-only (git merge-base origin/develop HEAD) HEAD -- src/   # cobertura por arquivo tocado
```

### Verificações funcionais

- [ ] **A app sobe com as duas superfícies** — `uv run uvicorn restaurant_hub.main:app`
      inicia; `GET /docs` lista as 16 rotas de staff sob `/api/v1` **e** as de
      identity.
- [ ] **O fluxo do DoD roda pelo entrypoint real** — `manager` cria função e
      funcionário pela API contra Postgres real (CA25).
- [ ] **Com o container parado, o e2e FALHA** (não pula) — a prova de que o gate
      de banco real não tem caminho de skip.
- [ ] **Nenhuma migration nova** — `git diff --name-only origin/develop..HEAD -- migrations/`
      vazio.
- [ ] **A regex `_ORDER_BY` não foi tocada** —
      `git diff --name-only origin/develop..HEAD -- tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py`
      vazio (CA31 / ADR 3.4.0004).
- [ ] **O inventário fecha em 16** — nenhuma rota a mais, nenhuma a menos (CA01).

### Checklist de fechamento da Stage

- [ ] Todas as **12** Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥ 90% global **e** em cada arquivo de `src/` tocado
- [ ] **As quatro provas por mutação de CA33 executadas de verdade**, com a saída
      colada — inclusive o registro de que a mutação (a) **sobrevive** ao fake
      sancionado e só morre com o dublê adversarial
- [ ] **Nenhuma varredura da faixa 422 é status-only** — cada asserção de
      CA20/CA22/CA23/CA24 exige o corpo de erro de **staff**, e não o corpo
      constante do `RequestValidationError`. `grep` por asserção de status sem
      asserção de corpo nos módulos de varredura e nos e2e de faixa
- [ ] **`set(_INVOCACOES)` cobre as 16 rotas** pela asserção de totalidade
      derivada, não por inspeção
- [ ] Auditoria de Testes com todos os itens "sim"
- [ ] Checkpoints A, B e C executados, com todos os achados dispostos
- [ ] §7 deste documento reflete a execução real
- [ ] `[finding]` escalados têm Stage candidata (os do concept §10, menos o de
      `Decimal("  40  ")`, que **D-3B1 fechou**)
- [ ] Commit final `stage 3.6: complete` aplicado
- [ ] `roadmap.md` atualizado: `3.6-staff-http` em `status: done`, `updated_at` e
      `last_reviewed_at` na data do merge
- [ ] ADRs `0_0_0005`, `3_6_0001`–`3_6_0003` seguem em `status: accepted`
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (tenant no token: port + tradutor + fake + as duas suítes de lei)
   │
   ├──► Task 02 (schemas + conversores)  ─┐
   ├──► Task 03 (mapa de status)          ├──► Task 05 (RJF + varreduras derivadas)
   └──► Task 04 (validador + requisito)  ─┘         │
                                                    ├──► Task 06 (CRUD + dublê adversarial)
                                                    │        │
                                                    │        ├──► Task 07 (perfil/preferência/indisp.)
                                                    │        └──► Task 08 (ciclo de vida + cópia)
                                                    │                 │
                                                    └─────────────────┴──► Task 09 (wiring)
                                                                              │
                                                                              ├──► Task 10 (e2e do DoD)
                                                                              ├──► Task 11 (papel × rota)
                                                                              └──► Task 12 (faixas de status)
```

- **01 → tudo:** sem o tenant resolvido, nenhuma rota é alcançável por nenhum
  papel — foi a medição que abriu a F1 (concept §13).
- **02, 03 e 04 são mutuamente independentes.** A ordem entre elas é de leitura (do
  que viaja no fio, para como o erro é classificado, para o que a borda recusa),
  não de compilação. **02 vem primeiro por um motivo mecânico:** é a Task que cria
  o pacote `adapters/in/`, e portanto a que precisa ajustar a asserção de ausência
  em `test_composition_root_staff.py`.
- **04 → 05:** o router consome o validador e a declaração de requisito. Critério 4
  de Task Atômica (não misturar criação de port com o seu adapter) não é violado —
  o port `AccessGuard` é da 3.4 e esta Stage só o **consome**.
- **05 → 06 → 07/08:** o `router.py` cresce por fatia de recurso, e as varreduras
  derivadas da 05 mais a CA15 da 06 passam a valer sobre cada rota nova **sem
  edição de teste**. É o que faz uma Task de rota reprovar a si mesma.
- **08 → 09:** o wiring registra o router **completo**; registrá-lo antes faria a
  não-regressão de identity ser medida contra alvo móvel.
- **09 → 10/11/12:** os e2e exigem a app real com as duas superfícies montadas.
- **10 → 11 e 12:** o `conftest.py` de e2e de staff (cadeia de setup por rotas
  reais, papéis semeados) nasce na 10 e as outras duas o consomem.
- **11 e 12 são independentes entre si** e poderiam trocar de ordem. Ficam
  separadas porque são **assuntos** distintos — *quem alcança* × *como o erro é
  classificado* —, cada uma com o seu arquivo, e porque juntas somariam ~140 casos
  e2e contra Postgres real num único commit. **Esta é a única subdivisão que este
  plano fez em relação à estimativa de 11 do concept, e ela não toca o inventário
  de rotas** — que continua reservado para o caso de a execução estourar 12.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| **Varredura da faixa 422 asserindo só o status.** 8 das 14 rotas de RID têm corpo obrigatório e R12 exige query: invocadas sem carga válida, respondem 422 pelo `RequestValidationError` **sem que o validador rode**, e a varredura fica verde sem trava | **Achado de Checkpoint C, não estilo** — é falso verde da família "lei universal, representante estreito", agora no eixo da *origem* do status. Duas defesas obrigatórias: invocar pelo `_INVOCACOES` (totalidade derivada) e asserir o discriminador de corpo `"staff_error"`. O argumento já estava escrito no ADR 3.6.0002 (*"a different body shape"*) e não fora aplicado ao próprio teste |
| Uma rota nova entrar na varredura **sem** chave no `_INVOCACOES`, e o executor "consertar" removendo a asserção de totalidade | A totalidade é o que obriga a Task da rota nova a declarar como invocá-la. Removê-la é o mesmo movimento que relaxar CA17 quando um erro novo não tem entrada no mapa — **blocker**, e a §2.1 registra o paralelo |
| A suíte de CA15 ser escrita com o `InMemoryAccessGuard` "porque já existe" | **Blocker, não ajuste.** Os dois implementadores ecoam a unidade pedida; a mutação (a) de CA33 fica verde e a cobertura fecha em 100%. O gate da Task 06 exige a mutação executada **de verdade**, com a saída colada, e o registro de que ela sobrevive ao fake |
| Um `parametrize` ser escrito como lista literal de rotas "para ir mais rápido" | O domínio é **derivado** (`router.routes`, `model_fields`, `__subclasses__`) por decisão de §1. Lista literal é achado do Checkpoint C, não estilo: é a forma exata da falha que a 3.4 vazou três vezes |
| `make check` verde com Postgres de outra worktree ocupando a porta | `docker ps` + `DATABASE_URL` **antes** de confiar no verde. Container órfão foi a causa de uma Stage testar contra infra alheia |
| A Task 09 quebrar call sites que o mypy não vê | Os dois estão medidos e nomeados na Task (`app.py`, coberto; `test_composition_root_staff.py`, **não** coberto). Se aparecer um terceiro, é achado sobre este plano — registrar, não emendar em silêncio |
| Alguém "consertar" a cópia repetida acrescentando guarda por nome | ADR 3.4.0005 é decisão consumida: homônimos são legítimos. Guarda por nome é **escopo vazado**, e a Task 08 não tem critério que a peça |
| Tentação de acrescentar `GET /units/{u}/employees/{id}` ao fechar o e2e | `non_goals` do roadmap + concept §7 D7. CA01 deriva de `router.routes`: a 17ª rota reprova a própria Task |
| O router ler `scope.unit_id` por `getattr`/`astuple`, contornando a AST | CA14 é declaradamente **defesa em profundidade**; a trava é CA15 com o dublê. Se a AST for a única evidência apresentada, o gate não fecha |
| A validação de identificador ser posta **depois** do guard "porque o status é o mesmo" | CA21 assere a **ausência** de `authorize(` em `calls` — o status não distingue as duas ordens, e é por isso que a asserção é sobre o efeito colateral |
| R16 inverter origem e destino sem que nada falhe | CA34 nas duas metades (command na 08, unidade de destino na 10) + a mutação (d) de CA33 |
| A Stage estourar 12 Tasks durante a execução | **PARAR e devolver proposta.** A subdivisão de e2e **já foi usada** (Tasks 11 e 12); o próximo sinal é subdividir o inventário de rotas (Tasks 06–08), **não** cortar a Stage de novo: ela já é produto de um corte |
| O eixo novo de Task 01 ("tenant omitido") ficar verde pela matriz RBAC em vez de pela lei | `platform_admin` é negado no **passo 2** por não deter permissão de staff (`role.py:54`), antes de L-AG3. O cenário tem de usar `_SpyIdentityGuard` — identity **autorizou** e devolveu ator sem tenant —, como a suíte mergeada já faz (`test_composition_root_staff.py:485-492`) |
| `user_id` entrar num schema na 3.5 sem que nada reclame | A lista negra de CA02(a) inclui `user_id` e `employee_user_id` desde a Task 02. Sem isso a célula do `non_goal` seria declaração, não trava |
| `weekly_hours` como string quebrar cliente que espera número | Declarado no contrato e no ADR 3.6.0003; não há cliente (frontend é Step futuro) |

## 6. Referências

- [`./concept.md`](./concept.md) — §4.1 inventário de rotas (R01…R16, RJF, REMP,
  RID), §4.2 schemas, §5 invariantes, §6 mapa de erro, §7 decisões, §11 critérios
- [`../../roadmap.md`](../../roadmap.md) — bloco `3.6-staff-http` (inventário,
  `non_goals`, `gate_mode: strict`, `skills_hint`)
- [`../../LAYOUT.md`](../../LAYOUT.md) — §3 direção de import, §6 composition root,
  §7 Pydantic só no boundary, §8 o pacote `in`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — §4 commits, §6 tamanhos
- [`../2.4-identity-http/technical.md`](../2.4-identity-http/technical.md) — a
  Stage irmã, cujo desenho este plano replica
- **ADRs desta Stage:** [`3.6.0001`](../../adr/3_6_0001-path-addresses-the-record-not-the-authorized-scope.md),
  [`3.6.0002`](../../adr/3_6_0002-boundary-identifier-validation.md),
  [`3.6.0003`](../../adr/3_6_0003-wire-representation-preserves-domain-guarantees.md)
- **ADR global:** [`0.0.0005`](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
  — o tenant vem do token (três cláusulas, gatilho de reabertura)
- **ADRs decididos na 3.4 e executados aqui:** 3.4.0002, 3.4.0004, 3.4.0005
- **ADRs herdados que governam:** 3.4.0001, 3.4.0006, 3.4.0007, 3.4.0008, 2.4.0003,
  2.3.0001, 2.3.0005, 3.3.0003
- **Skills:** `fastapi-thin-adapter`, `composition-root`, `task-ordering-hex`,
  `hex-arch-python`, `stage-audit` (§"Lei universal, representante estreito")
- **Issue [#43](https://github.com/MarceloSanC/restaurant-hub/issues/43)**

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`** — alterações fora dos marcadores `BEGIN/END: post-execution`
> são rejeitadas via `scripts/check_technical_postexec.py`. O frontmatter
> `updated_at` **não muda** com edições aqui — cada entrada carrega data + autor.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4 algo não
> previsto no Concept ou neste Technical, **pause** e levante a pergunta com 2–4
> opções e uma recomendada + razão. Apenas após a decisão, registre a entrada.

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
- `[finding]` — gap a tratar em **próxima Stage**; inclui direção sugerida e Stage
  candidata.
- `[deviation]` — ajuste pequeno vs. o plano original.

### 2026-08-29 - [decision] adapters/in/http/schemas.py (Task 02) - Marcelo

**Contexto:** o ADR 3.6.0003 se contradiz. O `## Implementation notes` diz
*"**Do not add `extra="forbid"` to the request models**... Diverging here would
create two behaviours for the same class of request across the API"*; o **mesmo
ADR**, `## Decision` 1 - e o concept CA06, que o cita - exige que
`{"type":"on_demand","weekly_hours":"40"}` receba **422**. Sem `forbid`, o
Pydantic ignora o campo e a resposta e **200**: metade da `Decision` 1 e
inalcançável. Medido por mutação no Checkpoint C - trocar `forbid` por `ignore`
derruba CA06.

**Pergunta:** aceitar a instrução literal (e deixar CA06 sem trava) ou estreitar
o alcance dela ao nível em que o dano que ela nomeia se realiza?

**Opções:**
- A - Seguir a instrução literal: nenhum `extra="forbid"`, e CA06 vira critério
  sem teste possível. Reprova o próprio ADR que a instrução serve.
- B - `extra="forbid"` em **todos** os schemas, de topo e aninhados. Realiza
  exatamente o dano que a instrução nomeia: um `tenant_id` enviado no corpo
  passaria a receber 422 em vez de ser desarmado em silêncio, e a borda de staff
  divergiria da de identity na mesma classe de request.
- C - `extra="forbid"` **só** nas duas variantes aninhadas da união de perfil de
  jornada, mantendo o `ignore` default nos nove `*Request` de topo. ✅ recomendada

**Decisão:** C.

**Razão:** o campo extra que a instrução protege e o campo **desconhecido** do
request - e o desarme dele continua intacto: verificado em runtime que
`CreateEmployeeRequest(..., tenant_id="ATACANTE")` descarta o campo em silêncio,
como os requests de identity. Já o `weekly_hours` dentro de
`{"type": "on_demand"}` não e campo desconhecido a desarmar: e **o estado
inválido** que a união discriminada existe para tornar irrepresentável, e
Decision 1 lhe atribui 422 nominalmente. Ignorá-lo entregaria ao cliente uma
jornada diferente da que ele pediu.

**Registro no ADR:** a instrução foi estreitada para *"top-level request
models"* por **errata** no ADR 3.6.0003 (`## Errata`, 2026-08-29), com o alcance
do `forbid` medido e declarado. Sem esse registro, quem lesse o ADR ao pe da
letra removeria o `forbid` e derrubaria CA06 sem entender por que.

### 2026-08-29 - [decision] test_http_boundary_sweeps.py (Task 05) - Marcelo

**Contexto:** o plano descreve `_INVOCACOES` como um mapa **dentro** do módulo de
varreduras. Escrito assim, toda Task que acrescenta rota (06, 07, 08) teria de
editar `test_http_boundary_sweeps.py` para declarar a invocação da rota nova —
arquivo que **não esta** na lista de nenhuma delas. A Task 06 é o caso agudo: ela
acrescenta quatro rotas, o seu comando de verificação roda as varreduras, e a
asserção de totalidade (`set(_INVOCACOES) == {chave(r) for r in router.routes}`)
ficaria vermelha sem a edição — isto é, o gate "não avancar sem verificação
verde" seria insatisfazível dentro do escopo declarado.

**Pergunta:** onde a declaração de invocação de cada rota deve morar?

**Opções:**
- A - Mapa literal no módulo de varreduras, editado por cada Task de rota. Fiel a
  letra do plano, mas põe cada Task para tocar arquivo fora da sua lista.
- B - Uma invocação **derivada** da rota (corpo montado por introspecção do
  schema). Elimina a declaração — e com ela a trava: a fixture existe justamente
  para que a Task **declare** como a rota é invocada, e um corpo gerado seria uma
  segunda implementação do schema, capaz de concordar com um router errado.
- C - Cada módulo `test_http_router_*` exporta o seu próprio `INVOCACOES`, e o
  módulo de varreduras os **colhe do pacote** por `pkgutil`. ✅ recomendada

**Decisão:** C.

**Razão:** é a mesma disciplina de "derivar o domínio do código" que a §1 do
plano usa para `router.routes`, `StaffError.__subclasses__` e `model_fields`,
aplicada ao arranjo dos testes. A propriedade que a fixture protege fica
**idêntica** — a asserção de totalidade é preservada literalmente, e rota sem
declaração continua reprovando —, mas a declaração passa a morar no arquivo da
Task que escreveu a rota, que é onde o plano já diz que ela pertence
conceitualmente ("obriga a Task que escreve uma rota nova a declarar como
invocá-la"). Efeito colateral desejado: as Tasks 06, 07 e 08 deixam de precisar
tocar o módulo de varreduras, e as suas listas de arquivos ficam corretas como
escritas.

**Mesma forma, mesma razão, para o wiring de use case.** `Ambiente` monta os
`dependency_overrides` por reflexão sobre os provedores `_get_*` do router (a
anotação de retorno nomeia a classe do use case; os 16 construtores pedem apenas
`employees`, `job_functions` e `id_generator`). Sem isso, cada Task de rota teria
de editar o ambiente de teste pelo mesmo motivo — e pela mesma via.

### 2026-08-29 - [deviation] test_http_boundary_sweeps.py (Task 05) - Marcelo

**Contexto:** o eixo de **path** de CA20 exige enviar `"   "` e `"\x00"` num
segmento de URL. Medido: `httpx` **recusa montar** a URL com o caractere cru
(`InvalidURL: Invalid non-printable ASCII character ... at position 22`), então o
teste falharia no cliente antes de alcançar a rota.

**Ajuste:** os parâmetros de path são percent-encoded (`urllib.parse.quote`) antes
de montar a URL. Não é contorno de teste: é como o caso chega em produção — o
concept nomeia literalmente `GET /units/%00/employees`, e um cliente HTTP não tem
outra forma de por um NUL num path. O Starlette decodifica antes de entregar o
parâmetro ao handler, que é exatamente o caminho que o validador fecha. Nenhum
critério muda; o que muda é a forma de exercita-lo, e ela ficou **mais** fiel.

### 2026-08-29 - [deviation] test_http_router_job_functions.py (Task 05) - Marcelo

**Contexto:** a app minima dos testes de rota registrava apenas
`register_staff_error_handlers`. Com isso o 422 do `RequestValidationError` sai
com o corpo **default** do FastAPI, que não tem a chave `type` — e asserir
`type == "staff_error"` passava por `KeyError` evitado, não por diferença de
origem.

**Ajuste:** o ambiente passa a registrar também o `register_error_handlers` de
`shared`, na mesma ordem que `create_app` usa (genéricos primeiro, de feature
depois). E' o que da ao ambiente as **duas** origens de 422 que a app real tem, e
portanto o que torna o discriminador de corpo uma trava de verdade em vez de uma
asserção sobre ausência de chave.

### 2026-08-29 - [decision] test_http_boundary_sweeps.py (Task 06) - Marcelo

**Contexto:** com as quatro rotas de funcionário, o eixo de **path** de CA24
passou a incluir `unit_id`, e onze casos ficaram vermelhos. A causa não é defeito
do router: para um `unit_id` de **formato válido** que o ator não tem concedido,
o `InMemoryAccessGuard` levanta a sua própria sentinela, que não é `StaffError`
nem `IdentityError` e não tem handler na app minima dos testes unitários.

**Pergunta:** o que CA24 deve exigir quando o identificador de path é o **alvo de
autorização**?

**Opções:**
- A - Manter a exigência de resposta HTTP com status < 500. Obrigaria a conceder
  no fake toda unidade do conjunto adversarial, isto é, a montar o cenário para
  que a asserção passe — e o que passaria a ser medido seria a montagem.
- B - Tirar `unit_id` do eixo de CA24. Perde cobertura real: é justamente o
  parâmetro por onde o NUL produzia 500 **dentro de identity**.
- C - Reconhecer os **dois** desfechos legítimos por espécie de parâmetro, e
  asserir a **identidade** do objeto levantado quando o desfecho é a recusa do
  guard. ✅ recomendada

**Decisão:** C.

**Razão — e a razão é erro de categoria, não afrouxamento.** Os parâmetros de
path deste inventário são de duas espécies. `job_function_id` e `employee_id`
entram num command e a resposta é HTTP: ali a asserção continua sendo sobre o
**status**, intacta. `unit_id` é o **alvo de autorização**: um valor bem-formado
que o ator não tem concedido **passa** pelo validador de identificador — ele é
bem-formado, e a peça que recusaria é outra — e é negado pelo **guard**. Exigir
422 ali mede a peça errada: o validador não tem por que recusar um identificador
válido, e quem nega é a autorização.

**Correção de 2026-08-29, medida pelo Checkpoint C.** A primeira redação desta
entrada dizia que a asserção nova era *"estritamente mais forte que a antiga"*.
**E' falso, e foi refutado por contra-teste.** O enunciado honesto é outro, e
tem três partes:

1. **A antiga era insatisfazível na espécie `unit_id`** — contra um router
   **correto**, a sentinela escapa, não ha resposta nenhuma, e onze casos ficavam
   vermelhos sem defeito algum. Isso não é forca, é falso positivo.
2. **A nova pega tradução-em-exceção**: `exc is guard.authorization_error` exige
   identidade de objeto, e um adapter que capturasse e relancasse um erro **novo
   do mesmo tipo** falha aqui. *(Medido: a asserção de status também ficaria
   vermelha nesse caso, porque a exceção continua escapando e não ha resposta —
   então a identidade **não discrimina** neste contra-teste.)*
3. **A tradução-em-resposta era a fresta, e ficou aberta até agora.** Capturar a
   recusa e devolver `HTTPException(403)` sobrevivia: sem exceção, o teste caia
   no ramo de status, e `403 < 500` aceitava exatamente a tradução que o
   docstring dizia proibir. Medido pelo Checkpoint C: **447/447 e 1611/1611
   verdes** com a tradução viva.

**O que se fez a respeito, no mesmo commit desta correção:** para a espécie
`unit_id` com valor bem-formado e unidade **não concedida**, o teste passou a
exigir que a sentinela **tenha** escapado (`pytest.fail` no ramo sem exceção).
Com isso o conjunto-vermelho da nova deixa de ser subconjunto do da antiga: ela
cobre as **duas** traduções que L-AG2 proíbe, e a antiga cobria uma só. Provado
por mutação — o CT2 aplicado ao router derruba **11** casos, contra 447/447
verdes antes.

**O que continua fora do alcance deste ambiente, e por isso não é prometido
aqui:** a **forma HTTP** da recusa em produção — o 403 de corpo constante do
handler de identity. Essa é CA09/CA11, na Task 11, com a app real montada.

**Precedente no próprio plano.** A Task 05 já declara o mesmo limite para CA08 —
*"o fake levanta a sua própria sentinela, que **não** é `IdentityError` e não tem
handler. A propriedade depende do handler de identity registrado sobre a app, e
por isso vive no e2e (Task 11)"*. Em produção a recusa é 403 de corpo constante,
e é a Task 11 que a mede.

### 2026-08-29 - [deviation] escopo da Task 06 - Marcelo

**Contexto:** a Task 06 declara `Arquivos a modificar: router.py`. Com as quatro
rotas novas, `test_http_boundary_sweeps.py` e
`test_http_router_job_functions.py` — **ambos da Task 05** — ficaram com 16
falhas, e nenhuma delas é defeito do router: cinco pela lista literal
`_INVENTARIO_DE_ROTAS` ter quatro entradas contra oito rotas, e onze pelo erro de
categoria de CA24 registrado na entrada acima. Sem toca-los, o gate "não avancar
sem verificação verde" é insatisfazível dentro do escopo declarado — e o comando
de verificação da própria Task 06 roda o módulo de varreduras.

**Ajuste, autorizado explicitamente antes de ser feito:** a Task 06 tocou os dois
arquivos para (i) dobrar o status de sucesso do §4.1 **dentro** da declaração
`INVOCACOES` de cada módulo de rota, aposentando `_INVENTARIO_DE_ROTAS`, e (ii)
aplicar a correção do CA24. A alternativa — estender a lista literal a cada Task
— foi recusada pelo eixo que esta Stage inteira defende: uma lista que cada Task
futura precisa **lembrar** de estender reinstala a familia *"lei universal,
representante estreito"* no próprio instrumento que existe para mata-la.

**O que NÃO se perdeu, e a verificação disso.** A transcrição do §4.1 continua
**manual** (o campo `sucesso`, escrito por quem leu a tabela do concept) e não
derivada de `rota.status_code` — derivar provaria só que o código concorda
consigo mesmo. A totalidade continua sendo o que trava o inventário: uma rota
plantada sem declaração reprova **quatro** testes, entre eles os dois de
totalidade. Verificado por mutação real, com a saida no relatório da Task.

**Precedente no plano:** a Task 07 já sanciona a edição analoga — *"a única edição
de teste permitida é acrescentar a chave das cinco rotas novas ao
`_INVOCACOES`"*. A permissão existia; faltava na Task 06. Com a mudança (i), as
Tasks 07 e 08 deixam de precisar dela: as suas declarações moram nos seus
próprios módulos.

### 2026-08-29 - [decision] test_http_boundary_sweeps.py (Task 07) - Marcelo

**Contexto:** com R09 e R11, o eixo de corpo de CA24 passou a incluir campos que
o **framework** parseia (`start`/`end` são `datetime`) e um campo escalar
**aninhado** (`weekly_hours`, dentro da união de perfil de jornada). Dois
problemas apareceram de uma vez: 22 casos vermelhos exigindo corpo de staff onde
a recusa é legitimamente de forma, e o campo que o próprio concept nomeia como
*"por onde escapou o 500 do `decimal.InvalidOperation`"* ficando **fora** do
domínio, porque a varredura só olhava o primeiro nível.

**Pergunta:** a asserção sobre a **origem** do 422 vale para todo campo escalar?

**Opções:**
- A - Sim, e ajustar as invocações para que `start`/`end` nunca recebam lixo.
  Tira do domínio justamente os valores que CA24 existe para varrer.
- B - Não, e largar a asserção de origem no eixo de corpo inteiro. Perde a trava
  que distingue "o domínio recusou o conteudo" de "o framework recusou a forma" —
  que é a razão de o discriminador existir.
- C - Classificar por **quem parseia o campo**: `str` no schema chega intacto ao
  router e a recusa é de staff; `datetime`/`bool` são parseados pelo framework
  antes do handler, e ali `validation_error` é a resposta correta. ✅ recomendada

**Decisão:** C, mais a descida até o campo aninhado.

**Razão:** é o **mesmo** erro de categoria que a entrada do CA24/path já
registrou para `unit_id`, na sua forma de corpo. Exigir corpo de staff num campo
que staff nunca chega a ver seria exigir que ele assumisse uma recusa que não é
dele; e o caso em que staff **é** responsável por um `datetime` — o valor
bem-formado com `Z`, que `UnavailabilityPeriod` recusa — continua exigido, com
corpo de staff, em teste dedicado no módulo de rota.

**A classificação tem guarda própria.** `_quem_parseia` decide se a exigência do
corpo se aplica; um bug que a fizesse devolver sempre `"framework"` desligaria
essa metade de CA24 em silêncio. Há teste exigindo que as **duas** espécies
existam no domínio varrido, e outro exigindo que `("workload_profile",
"weekly_hours")` esteja entre os caminhos — a lição do guarda tautologico do eixo
de corpo, aplicada antes de o revisor precisar apontar.

### 2026-08-29 - [deviation] escopo da Task 07 - Marcelo

**Contexto:** o Checkpoint C do bloco 2 abriu três achados que pedem edição de
`test_http_boundary_sweeps.py` (arquivo da Task 05), e a coordenação autorizou
absorvê-los aqui:

- **F3** - CA21 estava travado **só** no eixo de path. Medido: mover a validação
  dos ids do **corpo** para depois de `guard.authorize` em `create_employee`
  deixava a suíte inteira verde. O ADR 3.6.0002 §3 enuncia a ordem para *"path,
  query string, or body"*, e o corpo é onde o valor cru chega mais longe — cada
  elemento de `job_function_ids` vai para `find_all_by_ids` antes da entidade.
  CA21 passou a ser parametrizado também sobre `_CASOS_DE_CORPO`; a mutação agora
  derruba 3 casos.
- **F4** - o guarda do eixo de corpo era tautologia (os dois lados derivavam do
  mesmo helper, então esvaziá-lo deixava o teste verde). Passou a exigir
  `_CASOS_DE_CORPO` sem condicional. *(Fechado no commit de F1.)*
- **F5** - o eixo de **query** não existia nem como ausência declarada, embora
  CA24 o nomeie e R06/R12 tenham query desde a Task 06. Foi criado, com a mesma
  distinção de responsabilidade da entrada acima; e a ausência do eixo de query de
  **CA20** — nenhum parâmetro de query é identificador hoje — ficou **declarada**
  por teste que fica vermelho no dia em que um `*_id` chegar por query.

**Razão de estarem aqui e não numa Task própria:** os três são sobre eixos que
esta Task é a primeira a povoar de verdade (corpo com id, query com parâmetro), e
separá-los produziria um commit que só faz sentido lido junto deste.

### 2026-08-29 - [deviation] escopo da Task 08 - Marcelo

**Contexto — e este NÃO teve autorização previa; esta registrado para ser
revertido barato se a coordenação discordar.** R16 é a única rota do BC que
autoriza **dois** alvos, e o segundo chega pelo **corpo**. Duas premissas das
varreduras foram escritas quando toda rota tinha exatamente um alvo, e ficaram
vermelhas contra um router correto (12 casos):

1. **CA24, eixo de corpo** — `target_unit_id` é alvo de autorização, então um
   valor bem-formado não concedido é negado pelo **guard**, cru, e não ha
   resposta HTTP. E' literalmente a mesma espécie que o eixo de path já trata
   para `unit_id`, e a correção é a mesma: a espécie do identificador decide a
   asserção, e a exigência de que a sentinela **escape** fecha a
   tradução-em-resposta também aqui.
2. **CA15, alvos do guard** — o teste exigia que **toda** autorização nomeasse a
   unidade do path. R16 autoriza origem **e** destino, e a segunda chamada é
   L-AG4 aplicada (o próprio CA16 a exige). A asserção passou a ser: a
   **primeira** autorização é a da origem — que é o que a lei nomeia — e todo
   alvo adicional tem de vir do corpo **declarado** da invocação, de modo que uma
   autorização sobre alvo não declarado continue reprovando.

**Por que não é afrouxamento:** nenhuma das duas remove exigência; as duas
trocam uma exigência **impossível para a rota correta** por outra que distingue o
caso legítimo do defeito. E as duas ganharam guarda própria contra colapso
silencioso — `test_os_alvos_de_autorização_são_exatamente_os_de_hoje` declara
quais identificadores são alvo de acesso, e a asserção de alvo adicional cobra a
declaração no corpo.

**Por que segui sem perguntar, tendo parado antes:** a classe já foi decidida
duas vezes nesta Stage — a coordenação autorizou editar as varreduras para
acomodar rotas novas (opção A) e para absorver F3/F5 na Task 07. Este é o mesmo
arquivo, pela mesma razão (rota nova revela premissa da varredura), e parar de
novo custaria uma terceira ida e volta sobre a mesma questão já respondida. Fica
declarado como **decisão minha**, e não como autorização recebida.

**Nota de método, aprendida na hora:** uma das reversões de mutação usou como
âncora uma linha que aparece em **12** rotas, e a reversão falhou deixando o
router sem a segunda chamada do guard. Detectado por inspeção antes do commit.
Âncora de reversão tem de ser tão única quanto a de aplicação — e a conferência
pós-mutação não é zelo, é o que separa medir de estragar.

### 2026-08-29 — [decision] test_composition_root_staff.py (Task 09) — Marcelo

**Contexto:** CA30 pede que as rotas fiquem montadas **na app**, e a primeira
redação do teste varria `app.routes` atrás de `APIRoute`. Medido: nesta versão do
FastAPI um router incluído vira um `_IncludedRouter` **opaco**, sem `.routes`, e
a varredura devolve **zero** `APIRoute` — a asserção `all(...)` sobre o prefixo
passava por vacuidade, e só a contagem denunciou.

**Decisão:** ler os pares `(método, path)` do **esquema OpenAPI** da app.

**Razão:** é o que o cliente enxerga, é estável entre versões do framework, e não
depende da representação interna de roteamento — que acabou de mudar debaixo do
teste. A alternativa (descer recursivamente em `_IncludedRouter`) acopla a suíte a
um detalhe privado do FastAPI, e foi esse acoplamento que produziu o falso verde.

**Registro do quase-erro, porque ele é o ponto:** a asserção vacuamente verde
existiu por alguns minutos e teria passado no gate. O que a pegou foi a
**cardinalidade declarada** (`_TOTAL_DE_ROTAS_DE_STAFF == 16`) — a mesma
disciplina de piso que CA17 usa para as exceções. Varredura sem contagem esperada
é varredura que não sabe quando está vazia.

### 2026-08-29 — [finding] CA08 observável a partir da Task 09 — Marcelo

**O que se viu:** com os dois registradores montados, uma rota de staff sem
Bearer responde, na app **real**, `401` com o corpo constante de identity —
`{"detail": "não autenticado", "type": "unauthorized"}`. É a propriedade que a
Task 05 declarou impossível de medir no ambiente unitário (o fake levanta a sua
própria sentinela, que não é `IdentityError` e não tem handler).

**Direção:** a Task 11 é a dona de CA08/CA09 e deve travá-la sobre o domínio
derivado de `router.routes`, com o ator ausente e os dois papéis sem permissão.
Registrado aqui porque a **primeira evidência** apareceu nesta Task, e uma
propriedade vista e não anotada é uma que ninguém procura depois.

### 2026-08-29 — [decision] tests/e2e/features/staff/conftest.py (Task 10) — Marcelo

**Contexto:** o cenário e2e precisa de restaurante, duas unidades e atores. Havia
o atalho de semeá-los pelos repositórios, como a suíte de identity faz com o
`platform_admin`.

**Decisão:** provisionar tudo **pela API de identity**, e semear apenas o
`platform_admin`.

**Razão:** semear pouparia meia dúzia de chamadas e apagaria justamente a
propriedade que esta Stage introduziu. O token que staff recebe precisa ser um
token **emitido pela aplicação**, com as claims que ela de fato coloca nele —
porque é da claim que o tenant sai (ADR 0.0.0005), e um usuário semeado com
tenant escrito à mão provaria que o teste sabe montar o objeto, não que a cadeia
funciona. O `platform_admin` continua semeado pela razão que a suíte de identity
já documenta: **nenhuma rota o cria**, e a raiz de confiança nasce fora da API.

**Consequência medida:** o `manager` é membro das **duas** unidades de propósito.
Com um manager de uma unidade só, CA26 passaria por falta de visibilidade em vez
de por isolamento — o registro é por unidade (ADR 3.4.0007), e é isso que o
critério mede. Um cenário que confunde as duas causas mede a errada.

### 2026-08-29 — [decision] test_staff_authorization.py (Task 11) — Marcelo

**Contexto:** CA36 pede que **nenhuma** das 16 rotas produza
`TenantScopeRequiredError` para `{owner, manager, hr}`. Medido contra a app real:
esse erro responde **403 com o corpo constante de identity** (concept §6.2), que é
byte-idêntico ao 403 de `PermissionDeniedError` e ao de `UnitNotVisibleError` — por
desenho, e é o oráculo que L-AG1/L-AG2 fecham. Não há, pela API, como distinguir a
espécie do 403.

**Pergunta:** como se assere "não produz `TenantScopeRequiredError`" num critério
que é, por construção, invisível na resposta?

**Opções:**
- A — inspecionar a exceção por dentro (monkeypatch no tradutor, ou um spy no
  `AuthorizeActionUseCase`), afirmando a espécie do erro.
- B — asserir o **contrapositivo observável**: para os três papéis que detêm as
  permissões de staff, nenhuma das 16 rotas responde 403 de espécie alguma. ✅
  recomendada

**Decisão:** B — e, com ela, CA10, CA11 (primeira metade) e CA36 passam a ser
provados pela **mesma** parametrização de 48 casos,
`test_ca10_ca11_ca36_papel_com_permissao_alcanca_a_rota`.

**Razão:** a opção A mediria o interior de uma peça de identity a partir de um teste
de staff, e é exatamente o acoplamento que o `Actor = object` do port existe para
impedir; ela ainda ficaria verde se a rota respondesse 403 por outra razão. E o
contrapositivo não é um enfraquecimento: CA10 já enuncia, literalmente, *"nenhuma
resposta é 401/403"* para o `manager`, então a asserção de CA36 na linha do manager
**é** a de CA10 — três parametrizações separadas repetiriam a mesma requisição três
vezes e triplicariam o custo sem acrescentar nenhuma refutação. A asserção efetiva é
mais forte que a do critério: exige o **status de sucesso declarado**, não apenas a
ausência de 401/403, porque um 404 aqui significaria que a rota respondeu sem
alcançar registro nenhum.

**Medido:** removendo `Permission.MANAGE_STAFF` de `Role.HR`, 12 das 48 células
reprovam (`...[<rota de REMP>-hr]`), junto com as 12 de CA12 — a mutação que a
opção A teria deixado passar em CA36 se o spy só observasse a espécie do erro.

### 2026-08-29 — [decision] test_staff_authorization.py (Task 11) — Marcelo

**Contexto:** CA12 exige que `hr` e `manager` produzam status idêntico nas 16 rotas
*"sobre o mesmo estado"*. Onze das dezesseis **escrevem**: invocar a mesma rota duas
vezes sobre os mesmos registros faria o segundo ator encontrar o efeito do primeiro
(apagar duas vezes é 204 e depois 404), e a igualdade reprovaria por causa da ordem,
não do papel.

**Pergunta:** "o mesmo estado" é o mesmo **registro** ou o mesmo **arranjo**?

**Opções:**
- A — invocar, truncar o banco, reprovisionar e invocar de novo com o outro ator.
- B — montar dois conjuntos **isomorfos** — mesma unidade, mesmas formas, nomes
  distintos por sufixo —, um por ator. ✅ recomendada

**Decisão:** B.

**Razão:** A custaria uma reprovisionamento completo (com argon2) por caso, e não
compraria nada: o que o ADR 3.4.0006 §1 nega é divergência **por papel**, e ela é
observável em qualquer par de estados isomorfos. A asserção é dupla de propósito —
igualdade **mais** o status de sucesso declarado —, porque a igualdade sozinha ficaria
verde se os dois papéis fossem negados juntos: dois 403 também são iguais.

### 2026-08-29 — [finding] custo da matriz e2e — Marcelo

**O que se viu:** `test_staff_authorization.py` são **162 casos** contra Postgres
real e levam **2m55s**, porque cada célula reprovisiona o cenário inteiro pela API
(restaurante, duas unidades e de dois a quatro atores, com argon2 de verdade em cada
um). É o preço que o próprio plano da Task 11 antecipou ao dizer que *"só os produtos
desta Task somam ~100 casos e2e"*, e o isolamento por caso é o que faz cada célula
medir a rota, e não o resíduo da anterior.

**Direção:** se a suíte crescer mais um eixo (o Step 4 acrescenta escala), vale medir
um cenário de escopo `module` para os eixos **read-only** — CA08 já não toca o banco —
mantendo o escopo por caso nos eixos que escrevem. Não fazer agora: trocar isolamento
por tempo antes de haver o segundo consumidor é otimizar contra um número que ainda
vai mudar. Stage candidata: a primeira da 4.x que acrescentar e2e de acesso.

### 2026-08-29 — [decision] test_composition_root_staff.py (higiene do Checkpoint C) — Marcelo

**Contexto:** o Checkpoint C do bloco 09–10 levantou três varreduras deste arquivo
que ficavam verdes por acidente. As três foram endurecidas juntas porque as três são
o mesmo assunto — *como se sabe o que a app publica e o que o wiring conecta*.

**Pergunta (a única que era fork):** a partição staff/identity valia o custo de sair
do contrato dos routers, ou a heurística de substring devia ficar com a razão
registrada?

**Opções:**
- A — manter `"/job-functions" in path or "/units/" in path` e registrar que a
  falha seria ruidosa, não silenciosa.
- B — derivar a partição de `router.routes` de cada BC, com o prefixo da app. ✅
  recomendada

**Decisão:** B, e as outras duas correções sem fork:

1. **Partição pelo contrato** (`_pares_do_router`). A heurística funcionava por
   **um caractere**: a rota de identity é `POST /restaurants/{id}/units`, sem barra
   final, e por isso não casava `"/units/"`. Custo real da alternativa B: uma função
   de seis linhas — desproporcional era continuar com a heurística.
2. **Inventário de identity literal** (`_ROTAS_DE_IDENTITY`, dez pares transcritos).
   `len(de_identity) == 10` deixava passar a troca de um path por outro. A
   expectativa é transcrita e não colhida do router: colhê-la faria os dois lados
   virem da mesma fonte.
3. **Varredura de provedores nos dois módulos** (`_provedores_de`). A anterior
   varria `vars(router)` por `_get_*` e **acrescentava `get_access_guard` à mão**,
   porque ele mora em `dependencies.py`; um provedor novo naquele módulo escaparia
   e voltaria a ser `RuntimeError` no primeiro request. O filtro por `__module__` é
   necessário: `dependencies.py` importa `get_args` e `get_origin` de `typing`, e
   os dois casam o prefixo.

**Medido, plantando `get_identity_gateway()` em `dependencies.py` sem override:**
a varredura nova reprova —
`test_ca30_o_mapa_de_overrides_cobre_todo_provedor_do_router_de_staff`,
*"provedor de staff sem override no wiring: ['get_identity_gateway']"*. A regra
**antiga**, calculada sobre a mesma mutação, devolveu `total: 17` e
`sem override: []`: ela não via o provedor novo. Mutação revertida; `git diff` de
`src/` limpo.

### 2026-08-29 — [finding] `PATCH /job-functions/{id}` com NUL no nome devolve 500 — Marcelo

**O que se viu, medindo CA22 pela API real (Task 12, em curso):** das quatro rotas
que aceitam nome — derivadas por introspecção, e são exatamente R01, R03, R05 e R07
—, **R03 não responde 422**. A exceção escapa sem handler:

```
router.py:308: in rename_job_function
rename_job_function.py:47: in execute
    homonima = self._job_functions.find_by_name(command.tenant_id, command.name)
sqlalchemy.exc.DataError: (psycopg.DataError) PostgreSQL text fields cannot contain NUL (0x00) bytes
[parameters: {'tenant_id_1': '...', 'name_1': 'Ana\x00Souza'}]
```

`DataError` não é `IntegrityError` (o tradutor da 3.3 nunca é chamado), não é
`StaffError` e não é `IdentityError` — nenhum handler o alcança, e o resultado é
**500**. É a primeira linha da tabela do concept §6.3, que esta Stage declara
fechada: *"Nome com byte NUL no corpo | sem esta Stage: 500 | nesta Stage: já
rejeitado no domínio pela 3.4"*. A afirmação é **refutada por medição** para R03.

**Por que só R03.** A ordem interna dos quatro use cases difere, e a diferença é
exatamente esta:

| Rota | Ordem | Quem vê o nome primeiro |
|---|---|---|
| R01 `create_job_function` | constrói a entidade (1) → `find_by_name` (2) | o **domínio** ⇒ 422 |
| R03 `rename_job_function` | `find_by_id` (1) → **`find_by_name`** (2) → `rename` (3) | o **banco** ⇒ 500 |
| R05 `create_employee` | constrói a entidade | o **domínio** ⇒ 422 |
| R07 `rename_employee` | `find_by_id` → `employee.rename` | o **domínio** ⇒ 422 |

A sonda de unicidade de R03 leva o nome cru ao Postgres **antes** de o domínio o
ver. Nenhuma suíte mergeada o pega: os testes de use case usam o fake, que aceita o
NUL, e a suíte de integração de `job_function_repository` nunca renomeia para um
nome com NUL.

**Consequência para esta Stage:** CA22 e a metade e2e de CA24 **não fecham** com o
código como está. Os dois casos vermelhos são
`test_ca22_nome_com_byte_nul_recebe_422_de_staff[PATCH-/job-functions/{job_function_id}]`
e `test_ca24_nenhum_campo_escalar_do_corpo_devolve_500[PATCH-/job-functions/{job_function_id}-name]`;
os outros 23 casos do módulo passam.

**Escalado, não decidido** — a correção fica fora da lista de arquivos da Task 12
(*"Arquivos a modificar: nenhum"*), e a escolha de **onde** ela mora é decisão de
fronteira, não detalhe:

- **A — reordenar `RenameJobFunctionUseCase`**: mover `job_function.rename(...)`
  para antes da sonda de unicidade. Três linhas, na camada onde a ordem já é
  contrato declarado (o docstring do use case chama a ordem de "o contrato"), e
  vale para qualquer adapter de entrada. Toca uma Stage mergeada (3.2).
- **B — validar nome na borda HTTP**, como se faz com identificador. Fica dentro da
  camada-alvo desta Stage, mas duplica no adapter uma regra de domínio, e o
  ADR 3.6.0002 limitou de propósito a validação de borda a **identificadores**.
- **C — aceitar e adiar**: narrar CA22 para as rotas que hoje alcançam o domínio, e
  abrir issue. Relaxa um critério de segurança que a Stage escreveu para não ser
  relaxado.

### 2026-08-30 — [decision] rename_job_function.py (fork da Task 12) — Marcelo

**Contexto:** o fork escalado na entrada anterior. Antes de decidir, o defeito foi
**re-medido com o fake, sem banco**: renomear para `""`, `"   "` **ou**
`"Ana\x00Souza"` dispara `job_functions.find_by_name` nos três casos, antes do
`InvalidNameError` — conduta observada
`['job_functions.find_by_id', 'job_functions.find_by_name']`. **Não é defeito de
NUL nem de Postgres**: é desvio de ordem, e o NUL é só a espécie em que a consulta
inútil vira 500 em vez de consulta inútil.

**Pergunta:** onde mora a correção — e a ordem declarada em §5.16 da 3.2 pode ser
emendada?

**Opções:**
- A — reordenar `RenameJobFunctionUseCase`: transição do domínio antes do
  `find_by_name`. ✅ recomendada
- B — validar nome na borda HTTP, como se faz com identificador.
- C — estreitar CA22 para as rotas que hoje alcançam o domínio.

**Decisão:** A, registrada em
[ADR 3.6.0004](../../adr/3_6_0004-cheapest-local-check-first-in-rename-job-function.md).

**Razão:** a **lei já estava escrita** e só um dos dois use cases a obedecia. A
nota que fecha a tabela de §5.16 enuncia o princípio — *"a checagem mais barata
que possa falhar sozinha vem primeiro"* — e justifica `create_job_function`
exatamente assim. A **linha** da tabela, porém, declarava para o rename a ordem
inversa: tabela e princípio discordavam, e **o princípio governa** (a linha é a
aplicação; a nota é a razão que a produziu). A linha foi emendada por **errata
datada** no concept da 3.2, apontando o ADR — não reescrita em silêncio —, e passa
a ter a mesma forma de `rename_employee`, que já obedecia o princípio.

**Por que a emenda não muda nada observável:** o par *(nome inválido, conflito de
nome)* **não é construível** — nenhum nome gravado pode ser inválido, porque o
domínio o recusa na construção **e na reidratação** (`__post_init__`,
ADR 3.4.0003; *Regra 1* do mapper da 3.3), logo `find_by_name` sobre nome inválido
nunca teria o que encontrar. O par duplo que a coluna da tabela declara é
**NotFound + conflito**, e continua intacto: `find_by_id` permanece em (1).

**B e C rejeitadas com fonte:** o ADR 3.4.0003 **já rejeitou** tratar este defeito
na borda (sua *Alternative A*), e o ADR 3.6.0002 confina validação de borda a
**identificadores** — B duplicaria regra de domínio no adapter. C é a
*Alternative D* (não fazer nada) do mesmo 3.4.0003, rejeitada por violar um CA
declarado.

**Expansão de camada declarada:** a camada-alvo da Stage é `adapters/in/http`, e
esta correção é `application` da 3.2 mais uma emenda ao concept da 3.2. O
precedente é o ADR 3.4.0003, que fez o mesmo sobre o domínio da 3.1.

**Medido:** com o fix, `test_staff_status_bands.py` passa de `2 failed, 23 passed`
para **25 passed** — os dois vermelhos eram
`test_ca22_...[PATCH-/job-functions/{job_function_id}]` e
`test_ca24_...[PATCH-/job-functions/{job_function_id}-name]`.

### 2026-08-30 — [decision] test_invalid_name_never_reaches_the_port.py (off-task) — Marcelo

**Contexto:** o defeito acima é da família *"lei universal, representante
estreito"* (skill `stage-audit`): a lei valia para todo use case que recebe nome,
e o único teste que a travava — `test_criar_com_nome_vazio_nao_toca_o_port`, cuja
docstring diz que a asserção sobre `calls` **é o ponto** — existia só para
`create_job_function`. Corrigir o rename sem quantificar a lei deixaria o próximo
desvio nascer do mesmo jeito.

**Pergunta:** travar a lei sobre quais use cases?

**Opções:**
- A — acrescentar um teste espelho para `rename_job_function`. Fecha o caso de
  hoje e reinstala o representante estreito, agora com dois representantes.
- B — teste parametrizado sobre o produto `use case × nome inválido`, com o
  domínio dos use cases **derivado** dos commands que carregam `name`. ✅
  recomendada

**Decisão:** B — `create_job_function`, `rename_job_function` e `rename_employee`
× `""`, `"   "`, `"Ana\x00Souza"` (9 casos), com a conduta permitida **transcrita
de §5.16** (não lida do código: expectativa derivada da implementação concorda com
qualquer implementação).

**`create_employee` é exceção documentada e NÃO entra.** §5.16 declara que ele
resolve as funções (port) **antes** de construir a entidade, e a nota explica por
quê: a falha real é referencial, e `JobFunctionNotFoundError` deve vencer o nome
vazio. Asserir a lei sobre ele contradiria o concept. A exclusão está nomeada no
próprio teste e travada por uma guarda de domínio: os commands com campo `name` são
derivados por introspecção, e a asserção é `cobertos | {excetuado} == derivados` —
um quinto command com nome fica **vermelho** até ser classificado.

**Medido (o teste morde):** contra o código **antes** do fix, `3 failed, 7 passed`
— exatamente as três parametrizações de `RenameJobFunctionCommand`, com
`assert ['job_functions.find_by_id', 'job_functions.find_by_name'] == ['job_functions.find_by_id']`.
Depois do fix, `10 passed`.

### 2026-08-30 — [decision] test_http_boundary_sweeps.py (off-task, gêmeo latente) — Marcelo

**Contexto:** ao escrever `_schema_do_corpo` da Task 12, a exclusão de `"return"`
apareceu como necessária — o `response_model` de toda rota de escrita também é um
`BaseModel`, e `EmployeeResponse` tem campo `name`. A versão **mergeada** do mesmo
helper, em `test_http_boundary_sweeps.py`, varre `__annotations__` **sem** excluir
`return`: para rota sem corpo ela devolve o modelo de **resposta**.

**Pergunta:** corrigir agora, sendo hoje inofensivo, ou registrar como `[finding]`?

**Opções:**
- A — `[finding]` para a próxima Stage. O defeito é latente: os dois chamadores
  filtram por `invocacao.body is None` antes de chamar, então nenhuma varredura
  erra hoje.
- B — corrigir e travar com teste direto. ✅ recomendada

**Decisão:** B. *"Inofensivo por acidente do chamador"* é o estado em que um helper
espera pelo terceiro chamador — e o terceiro chamador seria a rota que a Stage 4.x
acrescentar. O teste novo
(`test_o_schema_do_corpo_ignora_a_anotacao_de_retorno`) assere a **equivalência**
entre "a invocação declara corpo" e "o helper acha schema de corpo", sobre as duas
fontes independentes (`_INVOCACOES` declarado à mão pelas Tasks de rota × anotações
do handler), com a contagem de rotas sem corpo asserida junto — equivalência sobre
conjunto vazio é verdadeira.

**Medido:** removendo as duas linhas `if nome == "return": continue`, o teste novo
reprova — *"('DELETE', '/units/{unit_id}/employees/{employee_id}/unavailabilities')
não tem corpo, mas o helper devolveu `EmployeeResponse` — provavelmente o
`response_model`"*. Mutação revertida pelo `replace` inverso; `git status
--porcelain` conferido.

### 2026-08-30 — [finding] o technical da 3.2 ainda declara a ordem antiga — Marcelo

**O que se viu:** a errata de 2026-08-30 corrigiu a linha de `rename_job_function`
no **concept** da 3.2 (§5.16). O `technical.md` da 3.2 repete a mesma ordem em
prosa — *"(1) `find_by_id` ausente ⇒ `JobFunctionNotFoundError`; (2) `find_by_name`
**ignorando a própria função**…"*, na descrição da Task 07 —, e essa seção está
**congelada** por `scripts/check_technical_postexec.py` (só a §7 é editável após
`status: done`).

**Por que não foi corrigido aqui:** a hierarquia de fontes é Concept > Technical, e
o concept — a fonte superior — está correto e datado. Editar o technical fora da §7
faria o gate de post-execution da 3.2 reprovar, e o mecanismo de errata para
technical congelado não existe hoje.

**Direção:** ou (a) uma entrada `[finding]` na §7 do technical da 3.2 apontando o
ADR 3.6.0004 — o único lugar editável daquele doc —, ou (b) estender a disciplina
de errata a technicals congelados, com o script reconhecendo um bloco de errata.
Preferir (a): é barato, cabe no mecanismo que já existe, e não mexe no gate. Stage
candidata: a primeira que reabrir a 3.2 por qualquer motivo.

> **Fechamento parcial — 2026-08-31.** A direção (a) **já foi executada nesta
> mesma branch**, e não pela "primeira Stage que reabrir a 3.2": o commit
> `7909c37`, imediatamente posterior ao commit que escreveu esta entrada,
> acrescentou +51 linhas à §7 do `technical.md` da 3.2 — um `[finding]` datado
> que transcreve a ordem antiga da Task 07, registra a ordem em vigor
> (`find_by_id`, transição, `find_by_name`, `update`) e aponta o ADR 3.6.0004 e a
> errata da §5.16 do concept. **Só a direção (b) segue aberta:** o freeze de
> `scripts/check_technical_postexec.py` continua sem forma de errata para as
> seções §1–§6 de um technical congelado, então a linha 663 daquele doc segue
> declarando a ordem antiga e o único lugar onde a correção pode morar é a §7.
> A nota existe porque, sem ela, quem lê esta entrada hoje conclui que **nada**
> foi feito — e a direção deferida some junto com a metade que já foi cumprida.

### 2026-08-30 — [finding] terceira expansão de camada para trás no BC staff — Marcelo

**O que se viu:** três Stages seguidas do BC staff alcançaram para trás uma camada
já mergeada — a 3.2 sobre o domínio da 3.1, a 3.4 sobre o domínio da 3.1
(ADR 3.4.0003), e agora a 3.6 sobre a application da 3.2 (ADR 3.6.0004). As três
foram declaradas, nenhuma foi silenciosa, e as três tiveram a mesma causa: uma
propriedade que só é **observável** na camada de fora, escrita numa camada de
dentro que não tinha como medi-la.

**Direção:** não é sinal de indisciplina, é sinal de que a fronteira do gate está
no lugar errado. Vale medir, ao fim do Step 3, se as Stages de camada interna
deveriam nascer com uma trava do tipo *"lei quantificada sobre o domínio derivado"*
— que é a forma que as três correções acabaram tomando — em vez de um representante
por caso. Stage candidata: retrospectiva do Step 3, ou a primeira Stage de domínio
do Step 4.

### 2026-08-30 — [decision] auditoria independente — os seis achados e o que fechou cada um — Marcelo

**Contexto:** uma auditoria independente aplicou ~25 mutações sobre a Stage já
verde (2791 passed, cobertura 99,94%, arquivos da Stage a 100%). **Três
sobreviveram**, todas sobre linhas com cobertura de linha **e de ramo** em 100%.
Nenhuma era defeito vivo; as três eram buraco de suíte, e quatro dos seis achados
são instâncias do mesmo conceito — *"lei universal, representante estreito"*
(skill `stage-audit`).

**Pergunta:** cada achado se sustenta contra os docs, e qual é a correção que
fecha o **domínio quantificado** em vez de acrescentar mais um representante?

**Decisão e prova, achado a achado.** Cada um fechou com a mutação que sobrevivia
sendo **reaplicada** contra a suíte corrigida, e o teste nominal que reprovou está
registrado. Cada mutação foi revertida e `git status --porcelain` conferido
depois — pelo `replace` inverso em cinco das seis; a exceção está na entrada
`[deviation]` abaixo.

- **F1 (BLOCKER) — "autenticar antes de validar o corpo" travada em 1 rota de 9.**
  §5.1 vale para **toda** rota com corpo ou query obrigatórios; havia um único
  teste, escrito à mão, sobre `POST /api/v1/job-functions`. CA08 não alcança a lei
  porque invoca as 16 rotas com a entrada **válida** da declaração — o 422 do
  framework nunca compete com o 401. Fechado com `ROTAS_COM_ENTRADA`, derivado do
  router (`body_field`; `dependant.query_params` obrigatórios), cardinalidade
  **10** asserida, em duas metades: a guarda anti-vácuo prova que a entrada
  degradada produz 422 com credencial válida, e a lei prova 401 com o corpo de
  identity sem ela. *Mutação `actor: CurrentActor` → `request: Request` +
  `guard.authenticate(request)` aplicada em `create_employee` **e** em
  `remove_unavailability`: reprova as duas células nominais de
  `test_a_autenticacao_roda_antes_da_validacao_da_entrada_em_toda_rota`, com CA08
  seguindo verde nas 16.*

- **F2 (MAJOR) — `EmptyShiftPreferenceError` nunca era produzida por HTTP.** CA19
  cobra as três **faixas**, e o domínio quantificado de "a exceção atravessa o
  fio" é o **mapa**: quinze das dezoito entradas não tinham caminho HTTP. Fechado
  o eixo inteiro — `CENARIOS_POR_EXCECAO` com 14 cenários e2e (um por exceção
  alcançável), status vindo de `STAFF_ERROR_STATUS` e trecho da mensagem
  transcrito à mão, mais `INALCANCAVEIS_POR_HTTP` com as 4 sem caminho de
  requisição; a totalidade `cenários ∪ inalcançáveis == mapa` reprova exceção nova
  sem cenário. Custo medido: ~15 s, dentro do orçamento da suíte e2e. *Mutação
  `if periodos is None` → `if not periodos` (`router.py`, `_to_shift_preference`)
  reprova
  `test_cada_excecao_alcancavel_atravessa_o_http_real[EmptyShiftPreferenceError]`,
  com 200 e `"shift_preference": null` no corpo — a preferência declarada apagada
  em silêncio.*

- **F3 (MAJOR, latente) — a disjunção "tenant vazio **ou** ausente" com um só
  representante, do lado do argumento.** É **reincidência** de `L-AG3`: `5d69846`
  enumerou `ausente`/`vazio` no `actor_tenant_id` — o tenant que identity
  **devolve** —, e o mesmo par no tenant que o chamador **pede** nunca tinha sido
  enumerado. As duas implementações do port escrevem a mesma cláusula e ficavam
  cobertas pelo mesmo conjunto incompleto. `_TENANT_NA_CHAMADA` ganha `""` e
  `_TENANT_RESOLVIDO` carrega o alvo esperado por valor do eixo, com cardinalidade
  **3** asserida nos dois arquivos. *Mutação `tenant_id if tenant_id is not None
  else …` → `tenant_id or …`, aplicada em `composition_root.py` **e** em
  `in_memory_access_guard.py`, reprova seis células:
  `test_o_tenant_da_chamada_decide_o_que_chega_a_identity[*-tenant-vazio]`,
  `test_o_tenant_da_chamada_decide_o_alvo_consultado[*-tenant-vazio]` e
  `test_o_tenant_vazio_nomeado_nao_e_reescrito_para_o_do_ator[*]`.* Continua
  latente porque nenhuma rota de staff nomeia tenant (ADR 0.0.0005 cláusula 2) — o
  risco é o primeiro consumidor novo do port.

- **F4 (MINOR) — o domínio de CA24 excluía elementos de lista, e o critério nomeia
  um deles.** CA24 diz *"todos os campos escalares … o que inclui `weekly_hours` …
  e os períodos de `shift_preference`"*, e `_escalares` devolvia `[]` para `list`
  nos dois arquivos que compartilham o helper. Um passo de caminho passa a ser
  `str | int`; `_elemento_de` desce por `list[str] | None` para que o elemento
  continue classificado como de **staff**. Domínio de corpo cresce de **10** para
  **13** pares (rota, caminho), com a cardinalidade asserida. Sem defeito vivo: os
  13 valores adversariais em cada caminho novo respondem 422/404, nenhum 500.
  *Remover a descida por lista reprova
  `test_a_varredura_de_ca24_alcanca_os_dois_campos_que_o_criterio_nomeia` e
  `test_os_elementos_de_lista_sao_do_lado_de_staff_no_dominio_de_ca24`, nos dois
  arquivos.*

- **F5 (MINOR) — `AccessRequirement.names_unit` declarado e nunca lido.** Escolhida
  a **varredura estrutural** em vez de replumbar produção: a declaração é cobrada
  contra a chamada ao guard nos dois sentidos (`True` obriga `unit_id=`, `False`
  proíbe), e ler o campo num teste é o que o torna carga real. Três guardas em
  volta — toda autorização nomeia um `AccessRequirement` declarado (cardinalidade
  **17**: 16 rotas mais a segunda chamada de R16), os dois valores de `names_unit`
  são exercitados e todo requisito declarado é usado, e um caso plantado por
  sentido prova que a extração enxerga os dois. *Mutações: remover `unit_id=` de
  `list_employees` e acrescentá-lo a `create_job_function` reprovam, as duas,
  `test_o_names_unit_declarado_decide_se_a_rota_nomeia_unidade_ao_guard`.*

- **F6 — declaração faltando.** `JobFunctionAlreadyExistsError` e
  `EmployeeAlreadyExistsError` ganharam em `error_handlers.py` a linha de
  declaração que `EmployeeInUseError` e `EmployeeRelocationError` já tinham: o id é
  UUID gerado dentro do use case, nunca enviado pelo cliente, e produzi-las por
  HTTP exigiria dois UUID4 iguais. Quem cobra a ausência agora é a totalidade de
  F2, e não mais só o comentário.

**Razão de o conjunto ter fechado assim:** em nenhum dos seis a correção foi
acrescentar um representante. Em todos, o domínio quantificado foi **derivado por
introspecção** e a sua **cardinalidade asserida na mesma prova** — que é a defesa
contra a varredura que esvazia sem ninguém perceber, a lição da Task 09.

### 2026-08-30 — [deviation] reversão de mutação por `git checkout-index` — Marcelo

**O que se fez:** a reversão da mutação de F1 (`router.py`, duas rotas, quatro
trechos com âncoras distintas) foi feita com `git checkout-index -f` em vez do
`replace` inverso que a disciplina desta Stage exige. As outras cinco reversões
seguiram a regra.

**Por que é aceitável neste caso, e mesmo assim fica registrado:** o risco que a
regra protege é descartar trabalho não commitado junto com a mutação. Aqui
`router.py` estava **limpo** antes da mutação — a mudança de F2 nesse arquivo já
estava commitada — e `git status --porcelain` foi conferido depois, mostrando
apenas o arquivo de teste. O registro existe porque a regra é boa e a exceção não
deve virar hábito: com quatro âncoras, o `replace` inverso teria sido mais
trabalhoso e igualmente correto.

### 2026-08-30 — [finding] F1 e F3 podem ter gêmeos em `identity` — Marcelo

**O que se viu:** a auditoria **não mediu** se as duas leis têm gêmeos do outro
lado da fronteira. Nenhuma mutação foi aplicada em `identity` para (a) a ordem
`Depends`-antes-do-corpo nas rotas de identity e (b) a cláusula de resolução de
tenant do lado de identity, que lê `ator.claims.tenant_id` direto (concept §5.3).

**Por que não foi tratado aqui:** é BC alheio. Mexer nas suítes de identity a
partir da Stage 3.6 seria expansão de escopo para fora do BC da Stage — mais larga
que as três expansões de camada já registradas na entrada anterior, que ao menos
ficaram dentro de `features/staff/`.

**Direção:** aplicar as duas mutações contra a suíte de identity e, se
sobreviverem, quantificar as leis sobre o domínio derivado das rotas de identity —
a mesma forma que F1 e F3 tomaram aqui. O sinal de alerta a procurar é o mesmo: lei
escrita com quantificador, teste com um representante. Stage candidata: a primeira
do Step 5 que reabrir a borda HTTP de identity, ou a retrospectiva do Step 3.

### 2026-08-31 — [decision] CA33 — as quatro provas por mutação, com a saída colada — Marcelo

**Contexto:** CA33 exige *"prova por mutação das quatro leis mais críticas desta
Stage, com a saída colada"*, e o checklist de §3 repete a exigência incluindo o
registro de que a mutação (a) **sobrevive** ao fake sancionado. Até aqui as saídas
existiam apenas em relatórios de sessão — fora do repositório, e portanto
**inconferíveis por quem revisa o PR**. As quatro foram reexecutadas contra a
árvore de `6202196`, com o Postgres real de pé.

**Pergunta:** colar a saída onde? — e a resposta não é livre: o único lugar
editável deste doc após `status: done` é esta §7.

**Opções:**
- A — deixar a saída no relatório da sessão de auditoria e citá-la aqui
- B — colar a saída **literal** aqui, com o teste nominal que reprovou ✅ recomendada

**Decisão:** B

**Razão:** saída que vive fora do repositório não é evidência para quem lê o PR; é
testemunho. CA33 fala em *"com a saída colada"*, e o revisor precisa poder conferir
o par mutação→morte sem reexecutar nada.

**Disciplina comum às quatro:** cada mutação foi aplicada por `replace` de âncora
**única** (contagem `== 1` asserida antes da escrita; arquivo lido e reescrito em
UTF-8 com `newline=""`, para não trocar o CRLF), **conferida no arquivo** depois de
aplicada, e revertida pelo **`replace` inverso** — nunca `git checkout --` —, com
`git status --porcelain` **vazio** conferido após cada reversão.

#### (a) o router endereça pelo path e não lê `scope.unit_id` — CA15

A lei tem **duas** mutações, e a segunda é a que carrega o contraste que CA33
nomeia. A primeira é a forma literal do enunciado; a segunda é a forma que CA14 não
enxerga, e é ela que isola o poder de refutação do dublê adversarial.

**(a1) forma literal — `router.py:366`, rota R05:**
`unit_id=UnitId(unidade)` → `unit_id=UnitId(scope.unit_id)`.

Contra as suítes do **fake sancionado** (todo `tests/unit/features/staff/adapters`
menos o arquivo do dublê adversarial):

```
FAILED tests/unit/features/staff/adapters/test_http_boundary_sweeps.py::test_ca14_nenhum_handler_le_o_unit_id_do_escopo_autorizado
1 failed, 743 passed in 28.02s
```

Morreu — mas em **CA14**, a varredura **estrutural** por AST, que o concept declara
ser *"defesa em profundidade, não a trava"*. Nenhum dos 743 testes de comportamento
notou. A mensagem foi `Left contains one more item: 'create_employee:366'`.

**(a2) forma que evade CA14 — mesma linha, `getattr(scope, "unit_id")`:** é o
bypass que o próprio texto de CA14 nomeia.

Contra as suítes do fake sancionado — **sobrevive inteira**, CA14 inclusive:

```
744 passed in 25.27s
```

Contra a suíte e2e, que roda o **tradutor de produção** (`_IdentityAccessGuard`)
contra Postgres real — **sobrevive**:

```
233 passed in 372.33s (0:06:12)
```

Contra o **dublê adversarial** — morre:

```
FAILED tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py::test_ca15_a_unidade_do_use_case_e_a_do_path[escopo-com-unidade-divergente-POST /units/{unit_id}/employees]
FAILED tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py::test_ca15_a_unidade_do_use_case_e_a_do_path[escopo-sem-unidade-POST /units/{unit_id}/employees]
2 failed, 36 passed in 2.36s
```

```
E       AssertionError: assert None == 'unit-DO-PATH'
E        +  where None = CreateEmployeeCommand(tenant_id='rest-1', unit_id=None, ...).unit_id
```

**O que a medição fecha:** 977 testes de comportamento (744 unitários + 233 e2e)
passam sobre um router que manda a escrita para a unidade do **escopo**. A única
coisa que refuta a lei é o dublê que contradiz de propósito — exatamente a razão
pela qual o concept manda fabricá-lo, e não uma preferência de estilo.

#### (b) validação de identificador removida de **uma** rota — CA20

`router.py`, rota R06 (`GET /units/{unit_id}/employees` — a que CA20 nomeia como
`GET /units/%00/employees`): `unidade = validate_identifier(unit_id, entity=_UNIT)`
→ `unidade = unit_id`.

```
FAILED tests/unit/features/staff/adapters/test_http_boundary_sweeps.py::test_ca20_identificador_invalido_em_path_recebe_422_de_staff[GET/units/{unit_id}/employees-unit_id-0]
FAILED tests/unit/features/staff/adapters/test_http_boundary_sweeps.py::test_ca20_identificador_invalido_em_path_recebe_422_de_staff[GET/units/{unit_id}/employees-unit_id-1]
FAILED tests/unit/features/staff/adapters/test_http_boundary_sweeps.py::test_ca21_a_validacao_roda_antes_de_autorizar[GET/units/{unit_id}/employees-unit_id-0]
FAILED tests/unit/features/staff/adapters/test_http_boundary_sweeps.py::test_ca21_a_validacao_roda_antes_de_autorizar[GET/units/{unit_id}/employees-unit_id-1]
4 failed, 778 passed in 28.92s
```

**Quatro mortes, e o par importa:** CA20 pega o status errado e **CA21** pega a
**ordem** — o identificador não validado alcançou `authorize`, e o fake sancionado
levantou `FakeAuthorizationRejected` em vez de a borda recusar antes. Só a rota
mutada reprovou: a varredura é derivada de `router.routes`, então a mutação de
**uma** rota mata exatamente as células daquela rota, nos **dois** valores do eixo
de path (`"   "` e `"\x00"`).

#### (c) duas entradas trocadas no mapa de status — CA18

`error_handlers.py`: `JobFunctionNotFoundError: HTTP_NOT_FOUND` ↔
`JobFunctionNameAlreadyExistsError: HTTP_CONFLICT`. As **duas faixas seguem
exercitadas** depois da troca (`EmployeeNotFoundError` continua 404; os quatro
`Conflict` restantes continuam 409) — que é a condição que CA18 enuncia entre
parênteses: um teste só de faixas sobreviveria.

```
FAILED tests/unit/features/staff/adapters/test_http_error_handlers.py::test_ca18_status_de_cada_excecao[excecao0-404]
FAILED tests/unit/features/staff/adapters/test_http_error_handlers.py::test_ca18_status_de_cada_excecao[excecao2-409]
FAILED tests/unit/features/staff/adapters/test_http_error_handlers.py::test_o_discriminador_e_o_mesmo_nas_tres_faixas[excecao0-404]
FAILED tests/unit/features/staff/adapters/test_http_error_handlers.py::test_o_discriminador_e_o_mesmo_nas_tres_faixas[excecao2-409]
FAILED tests/unit/features/staff/adapters/test_http_router_employees.py::test_funcao_inexistente_no_tenant_recebe_erro_de_staff
FAILED tests/unit/features/staff/adapters/test_http_router_job_functions.py::test_funcao_inexistente_recebe_404_com_o_corpo_de_staff
FAILED tests/unit/features/staff/adapters/test_http_router_job_functions.py::test_nome_repetido_recebe_409_com_o_corpo_de_staff
7 failed, 775 passed in 30.77s
```

Pelo HTTP real:

```
FAILED tests/e2e/features/staff/test_staff_status_bands.py::test_ca19_cada_faixa_e_alcancavel_pelo_http_real[404]
1 failed, 43 passed in 67.03s (0:01:07)
```

**Uma observação que a medição acrescenta ao enunciado de CA18:** CA19 — o teste
*de faixa* — também reprovou, mas **por acidente do representante**: o cenário que
ele usa para a faixa 404 é justamente `JobFunctionNotFound`, uma das duas classes
trocadas. Uma troca entre duas classes que não fossem representantes de faixa o
deixaria verde. Quem mata a troca **por construção**, e não por sorte de fixture, é
a parametrização par a par de CA18 — que é exatamente o que o critério afirma.

#### (d) origem↔destino invertidas em R16 — CA34

`router.py`, `CopyEmployeeToUnitCommand`: `unit_id=UnitId(unidade)` /
`target_unit_id=UnitId(destino)` → `unit_id=UnitId(destino)` /
`target_unit_id=UnitId(unidade)`.

```
FAILED tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py::test_ca15_a_unidade_do_use_case_e_a_do_path[escopo-com-unidade-divergente-POST /units/{unit_id}/employees/{employee_id}/copies]
FAILED tests/unit/features/staff/adapters/test_http_path_addresses_the_record.py::test_ca15_a_unidade_do_use_case_e_a_do_path[escopo-sem-unidade-POST /units/{unit_id}/employees/{employee_id}/copies]
FAILED tests/unit/features/staff/adapters/test_http_router_lifecycle_and_copy.py::test_ca16_a_copia_chama_o_guard_duas_vezes_com_alvos_distintos
FAILED tests/unit/features/staff/adapters/test_http_router_lifecycle_and_copy.py::test_ca34_o_command_carrega_a_origem_no_path_e_o_destino_no_corpo
4 failed, 778 passed in 29.81s
```

Pelo HTTP real, contra Postgres:

```
E       assert 404 == <HTTPStatus.CREATED: 201>
FAILED tests/e2e/features/staff/test_staff_flow.py::test_ca34_a_copia_cai_na_unidade_de_destino_e_o_original_fica
1 failed, 5 passed in 11.03s
```

**Três leis distintas morrem juntas, e nenhuma é redundante:** CA34 pega **onde a
cópia caiu**, CA16 pega que a **primeira** autorização deixou de ser a da origem, e
CA15 pega que a unidade que endereça o registro deixou de ser a do path — a mesma
inversão vista dos três ângulos que o concept separa de propósito. O e2e devolve
404 porque a leitura passa a acontecer na unidade de destino, onde o funcionário
não existe: a exfiltração que o ADR 3.4.0007 fecha, com o sinal invertido.

**O que as quatro juntas medem, e o que não medem.** Medem que as quatro leis mais
críticas desta Stage têm teste que morre quando a lei é quebrada — o enunciado de
CA33, e nada além. **Não** medem as leis gêmeas em `identity`: isso segue como o
`[finding]` de 2026-08-30 desta mesma §7.

### 2026-08-31 — [deviation] quatro commits `[3.6/--]` sem entrada nesta §7 — Marcelo

**O que se viu:** a Fase 4 desta Stage produziu **25** commits `[3.6/--]` — muito
acima da frequência saudável de 0–2 que CONVENTIONS §4(a) declara, e o número em si
já é o `[finding]` da entrada de 2026-08-30 sobre a fronteira do gate. A §7 registra
a maioria deles (as entradas de 2026-08-29/30, e o lote de `ef1e375` e `5fd982c`),
mas **quatro** ficaram sem nenhuma: `a783aeb`, `047fde1`, `9951acd` e `20d75c7`.

**O rastro existe — só não está onde CONVENTIONS §3.4 o põe.** Os quatro têm corpo
de commit longo, com a medição e a justificativa do off-task. O que falta é a
entrada nesta seção, que é o lugar que a convenção nomeia para quem audita o plano
sem percorrer o `git log`. Agregados aqui, cada um com o que mudou de fato:

- **`a783aeb`** — renomeia as **quatro** constantes públicas de `dependencies.py`
  para inglês (CONVENTIONS §1) e dá aos dois requisitos o sufixo `_ACCESS`. O
  sufixo não é decoração: sem ele, `MANAGE_JOB_FUNCTIONS` importado na borda de
  staff teria o **mesmo nome** que o membro `Permission.MANAGE_JOB_FUNCTIONS` de
  identity — o símbolo que CA07 proíbe staff de importar —, e um leitor do router
  concluiria a coisa errada sobre a fronteira entre os dois bounded contexts.
  Nenhum comportamento muda. Feito antes das Tasks 05–08 porque elas importam
  esses nomes nas 16 rotas, e o rename fica caro depois.
- **`047fde1`** — reescreve o docstring do dublê adversarial, e é **correção
  substantiva, não redação**: a razão do `MODO_SEM_UNIDADE` estava **invertida**. O
  texto afirmava que o modo mata a variante `scope.unit_id or path`; medido por
  mutação isolada por modo, essa variante **sobrevive** ao modo sem-unidade (`None`
  é falsy e o `or` cai de volta no path) e morre no modo divergente. O que
  justifica o segundo modo é **realismo** — `None` é a forma que a produção
  devolve para o `owner` — e não poder de refutação. Um docstring que atribui
  morte de mutação onde a medição não achou é pior que nenhum: convida a próxima
  Stage a confiar numa cobertura que não existe.
- **`9951acd`** — remove o byte NUL cru gravado neste `technical.md` pelo colapso
  de escape de um heredoc, e normaliza o fim de linha na mesma passada. As duas
  coisas são a **mesma** cadeia causal: com o NUL, o git tratava o arquivo como
  **binário**, `grep` respondia *"Binary file matches"* em vez de linhas — quebrando
  o idioma de verificação que o próprio concept §11 prescreve — e a normalização
  de fim de linha era pulada, o que fez `2d3aa81` registrar 1310/1240 linhas para
  um delta real de ~110, escondendo a mudança revisável do plano.
- **`20d75c7`** — reacentua as 25 linhas de prosa que `a35c080` deixou para trás
  dentro dos marcadores. Só acentuação: 25 linhas trocadas por 25, nenhuma fora dos
  marcadores.

**Por que ficam como `[deviation]` e não como `[finding]`:** os quatro são ajustes
pequenos, já aplicados e já verdes, contra o plano original — a definição da tag. O
que sobra para tratar adiante não é nenhum deles em particular, e sim a densidade de
off-task, que já está registrada como `[finding]` em 2026-08-30.

### 2026-08-31 — [finding] segunda instância de "definido mas não plugado" — Marcelo

**O que se viu:** `identifier_fields` e `IdentifierField` vivem em
`features/staff/adapters/in/http/dependencies.py:201-242`, e
`grep -rn "identifier_fields(" src/` **excluída a definição devolve 0**. Os únicos
consumidores são três módulos de teste
(`test_http_boundary_sweeps.py`, `test_http_dependencies.py`,
`test_http_path_addresses_the_record.py`). A produção valida identificador de corpo
**à mão, rota a rota** — `validate_identifier(payload.target_unit_id, …)` em R16,
`_job_function_ids(...)` em R05/R07.

**É a segunda instância do mesmo padrão nesta Stage.** A primeira foi
`AccessRequirement.names_unit`, registrada no comentário que abre a varredura de
`test_http_boundary_sweeps.py` e fechada em `b9ea8ce` com a mesma saída: quem lê o
campo é o teste, e ler é o que impede declaração e chamada de divergirem.

**Por que é defensável, e por que mesmo assim fica registrado:** derivar o domínio
por introspecção é o que faz um campo de identificador novo entrar na varredura de
CA20 sem que ninguém lembre de estender um teste — é exatamente a disciplina que a
§11 prescreve, e apagar a função esvaziaria o eixo de corpo de CA20 **em silêncio**.
O que fica anotado é a forma: **infraestrutura de teste morando em `src/`**, sob
`make check` e sob cobertura, mas sem chamador de produção. Uma instância é
pragmatismo; duas na mesma Stage é padrão.

**Direção:** ou (a) plugar as duas no router — `identifier_fields` passaria a
alimentar a validação de corpo, e `names_unit` a decisão de passar `unit_id=` ao
guard —, o que mexe nas 17 chamadas ao guard e nas rotas com corpo por um ganho que
as varreduras já entregam; ou (b) manter as duas em `src/` e **declarar** a ausência
de chamador no próprio docstring, para que ninguém as leia como plumbing esquecido
nem as apague por parecerem código morto. (b) já foi aplicada nesta branch em
`19a58cf`, e é a preferida enquanto forem duas. O gatilho para reabrir (a) é a
terceira instância, ou a primeira divergência medida entre a validação à mão de duas
rotas. Stage candidata: a primeira que acrescentar rota com corpo ao BC staff, ou a
retrospectiva do Step 3.

<!-- END: post-execution -->

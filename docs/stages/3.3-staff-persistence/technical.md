---
title: Technical — Persistência de equipe
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, staff-persistence, postgres, sqlalchemy-core, alembic, contract-tests, colacao, isolamento, concorrencia]
status: draft
created_at: 2026-08-10
updated_at: 2026-08-10
stage_id: 3.3-staff-persistence
stage_title: Persistência de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [3.2-staff-application]
concept_ref: ./concept.md
issue_id: 38
branch: feat/38-3-3-staff-persistence
tasks_count: 10
---

# Technical — Stage 3.3 — Persistência de equipe

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.3/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 3.3: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/38-3-3-staff-persistence`. Não há sub-PRs internos.

## 1. Contexto e estratégia de execução

### Resumo

Implementar em PostgreSQL os dois ports-out publicados pela Stage 3.2 —
`JobFunctionRepository` e `EmployeeRepository` — de modo que o comportamento seja
**indistinguível** do par de fakes para as **doze** leis nomeadas (L-JF1…L-JF5,
L-E1…L-E7) **mais a lei nova `L-ORD`**. Entram: as cinco tabelas em SQLAlchemy 2
Core com `staff_metadata` próprio, a migration `0003_staff.py` escrita à mão, os
mappers puros que reidratam pelo construtor, o tradutor de `IntegrityError`
**parametrizado pela operação**, os dois adapters, a **promoção** (não cópia) das
duas suítes de lei da 3.2 para `tests/contract/features/staff/` parametrizadas
sobre `["fake", "postgres"]`, os testes de integração do que só o banco decide
(migration, constraints, tipos, colação, isolamento, bloqueio) e o wiring dos 16
use cases de staff no composition root.

### Estratégia

**Inside-out na direção do fluxo de dependência** (skill `task-ordering-hex`),
com a exceção declarada da linha "Schema / data migration" da própria skill: o
schema vem **primeiro**, porque é ele a fonte das constraints que o tradutor
nomeia e que os adapters traduzem. O `domain` e a `application` deste BC já estão
`done` (3.1/3.2), então esta é uma Stage de **adapter sobre BC consolidado** — a
ordem natural da skill para esse caso é "contrato sobre o port existente →
adapter → wiring", e é o que as Tasks 04→10 fazem.

A ordem resolve seis restrições simultâneas:

1. **Cada commit deixa `make check` verde**, e o gate inclui cobertura global
   ≥ 90%. Consequência dura: **nenhum arquivo de `src/` é commitado sem os testes
   que o cobrem**, sempre na mesma Task.
2. **A lei antes da implementação.** `L-ORD` é declarada no port, obedecida pelo
   fake e travada por teste na **Task 04**, antes de existir uma linha de SQL que
   a implemente (Tasks 06/07). O caminho inverso — escrever o `ORDER BY` e depois
   descobrir qual lei ele cumpre — é como se chega a uma lei que descreve o
   adapter em vez de governá-lo.
3. **A promoção do contrato é cirúrgica e vem cedo, em duas Tasks.** Ver a
   subseção dedicada abaixo — é a decisão de ordenação mais consequente do plano.
4. **Postgres real é pré-condição de execução, não de uma Task.** Desde a Task 02
   a suíte exige banco no ar e **falha alto** quando ele não está (ADR 2.3.0001):
   não há caminho de skip, aqui nem no CI. Todo comando de verificação abaixo
   assume `docker compose up -d postgres`.
5. **Conduta separada de resultado.** Os três invariantes que o concept mediu
   empiricamente — dupla semântica da mesma FK, leitura rasgada sob
   `READ COMMITTED`, deadlock por reescrita cega das filhas — ganham **Task
   própria** (Task 08), com testes que os **reproduzem**. Eles são o finding
   herdado nº 4 ("a suíte travava resultado, não conduta") e, por construção,
   nenhuma asserção sobre estado final os distingue de sua ausência.
6. **Exceções declaradas ao critério de ≤ 5 arquivos** (PIPELINE §4.3, critério
   2): Tasks **02, 04 e 09** passam de cinco. Em todas, o excedente é mecânico
   (`__init__.py` de cadeia de pacote) ou é a **mesma** mudança lógica vista nas
   duas pontas obrigatórias (a lei `L-ORD` na declaração, na implementação de
   referência e no teste que a trava). Nenhuma delas mistura escopos
   independentes, que é o que o critério protege.

### A promoção do contrato, em duas Tasks — e por quê

O `git mv` das duas suítes é a mudança mais arriscada da Stage e a mais fácil de
subestimar: são **46 testes**, **45 assinaturas** que deixam de ser
`def test_…() -> None` para receber a fixture, **49 call-sites** de
`staff_repositories()` e dos três helpers (`_com_funcao_gravada`,
`_com_funcoes_gravadas`, `_com_funcionario_gravado`), mais o holder novo. Ela é
partida em **Task 05** (mover + reassinar, ainda só sobre o fake) e **Task 09**
(acrescentar o parâmetro `postgres`), pela razão que segue:

- **A Task 05 é, por construção, um no-op comportamental.** Os mesmos 46 testes,
  as mesmas asserções, a mesma implementação por trás (`fake`). Se o `make check`
  ficar vermelho ali, a causa é **a mecânica do movimento** — e só ela.
- **A Task 09 é, por construção, o único lugar onde uma lei pode reprovar.** Nada
  de estrutural muda: uma string entra em `params`. Se o `make check` ficar
  vermelho ali, a causa é **divergência fake↔adapter** — e só ela.
- Fundi-las poria um diff mecânico de ~400 linhas no mesmo commit que exercita os
  adapters pela primeira vez, e um vermelho seria ambíguo entre as duas causas.
  Ambiguidade em commit de gate é exatamente o que o `git bisect` existe para
  evitar; produzi-la de propósito seria trabalhar contra a ferramenta.

Nas duas Tasks, o `make check` fica verde **no próprio commit**:
na 05 porque a fixture tem um só parâmetro (`fake`) e o comportamento é o mesmo
de antes do movimento; na 09 porque os dois adapters já existem e já foram
verificados lei a lei contra o banco real nas Tasks 06/07.

### Decisões de detalhe fechadas neste plano

Duas lacunas de detalhe apareceram ao mapear o concept em Tasks. Nenhuma muda
contrato, fronteira ou critério de aceite — ficam registradas aqui, e não em §7,
porque são decisões **de plano** e não de execução:

1. **O teste `test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port`
   passa a receber `repos` mesmo sem usá-lo.** É o único dos 46 que não constrói
   sujeito — assere sobre o `__doc__` do `Protocol`. Sem a fixture ele rodaria
   **uma** vez, e CA1 ("cada teste roda duas vezes") deixaria de valer
   literalmente no `--collect-only`. Ruff não seleciona `ARG`, então argumento
   não usado não é violação de lint; e `mypy` não alcança `tests/contract/`
   (`make typecheck` roda `mypy src/ tests/fakes/`). Custo zero, CA1 literal.
2. **CA10b parte 1 assere sobre o texto SQL efetivamente emitido.** O concept
   ilustra a asserção como `str(stmt.compile(dialect=postgresql.dialect()))`.
   Obter o mesmo texto pelo evento `before_cursor_execute` do `Engine` é
   **estritamente mais forte** (assere o SQL que o adapter mandou, não um
   statement reconstruído pelo teste) e não obriga o adapter a expor os
   statements como atributo de módulo só para ser testável. A substância de
   CA10b — a asserção é sobre a **cláusula**, nunca sobre o resultado — fica
   intacta. As duas formas são aceitas pelo critério de aceite da Task 08.

### Pré-condições

- Stage `3.2-staff-application` em `done` e **mergeada** em `develop` (PR #36).
- Issue **#38** OPEN; branch `feat/38-3-3-staff-persistence` a partir de `develop`.
- Docker rodando; `docker compose up -d postgres` sobe `postgres:16-alpine`.
- `.env` da worktree define a `DATABASE_URL`/`POSTGRES_PORT` desta worktree —
  **não presumir 5432** (worktrees paralelas usam portas próprias; concept §3).
- `.venv` instalado (`make setup`).

### Premissas técnicas

- Python 3.12, SQLAlchemy 2 **Core** (sem ORM declarativo), Alembic configurado,
  `migrations/versions/` já com `0001_identity_initial` e `0002_password_setup_tokens`
  — o número livre é **`0003`** (concept D10).
- Os markers `unit`, `integration` e `contract` já existem no `pyproject.toml`.
- Cobertura com `branch = true` e `fail_under = 90` **global**; `migrations/` está
  em `omit`, logo a migration não conta para o gate — quem a exercita é a fixture
  `engine`, que recria o schema (`downgrade base` + `upgrade head`) a cada sessão
  de pytest.
- `make typecheck` roda `mypy src/ tests/fakes/`: os fakes **são** type-checked e
  cada um declara `_conforms: <Port> = <Fake>(...)`. `tests/contract/` e
  `tests/integration/` **não** são.
- `ruff` seleciona `E,F,I,B,UP,SIM,RUF,ANN,PL,TID` — **não** seleciona `ARG`.
- `.importlinter`: a supressão existente é o par
  `shared.infrastructure.http.app -> composition_root` — **uma aresta, não
  específica de identity**. O wiring de staff (Task 10) **não** exige supressão
  nova. `bc-independence` compara `features.identity` × `features.staff`, e o
  `composition_root` não pertence a nenhum dos dois.
- `docs/LAYOUT.md` §2 **já** declara `tests/unit/features/<feature>/adapters/`,
  `tests/integration/features/<feature>/adapters/out/postgres/` e
  `tests/contract/features/<feature>/`. Esta Stage **não** precisa alterar o LAYOUT.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                   (M — Task 10)
└── features/staff/
    ├── application/ports/out/
    │   ├── job_function_repository.py                    (M — Task 04, só docstring)
    │   └── employee_repository.py                        (M — Task 04, só docstring)
    └── adapters/out/postgres/                            (novo — Tasks 01, 03, 06, 07)
        ├── __init__.py
        ├── tables.py                                     (Task 01)
        ├── mappers.py                                    (Task 03)
        ├── integrity_errors.py                           (Task 03)
        ├── job_function_repository.py                    (Task 06)
        └── employee_repository.py                        (Task 07)

migrations/
├── env.py                                                (M — Task 02)
└── versions/0003_staff.py                                (novo — Task 02)

tests/
├── conftest.py                                           (M — Task 02)
├── unit/features/staff/
│   ├── adapters/                                         (novo — Tasks 01, 03, 10)
│   │   ├── test_tables.py, test_mappers.py, test_integrity_errors.py
│   │   └── test_composition_root_staff.py
│   └── application/test_{job_function,employee}_repository_laws.py  (M — Task 04; MOVIDOS — Task 05)
├── integration/
│   ├── test_migration.py                                 (M — Task 02)
│   └── features/staff/adapters/out/postgres/             (novo — Tasks 02, 06, 07, 08)
│       ├── test_schema.py, test_job_function_repository.py,
│       └── test_employee_repository.py, test_staff_conduct.py
├── contract/features/staff/                              (novo — Tasks 05, 09)
│   ├── __init__.py, conftest.py
│   ├── test_no_implementation_branching.py
│   └── test_{job_function,employee}_repository_laws.py   (git mv — Task 05)
└── fakes/features/staff/
    ├── in_memory_job_function_repository.py              (M — Task 04)
    └── in_memory_employee_repository.py                  (M — Task 04)

docs/stages/3.2-staff-application/concept.md              (M — Task 04, nota datada)
docs/roadmap.md                                           (M — fechamento, commit `[3.3/--]`)
```

> O `roadmap.md` **não pertence a Task nenhuma**: é atualizado no fechamento da
> Stage, num commit off-task `docs(roadmap): ... [3.3/--]` (CONVENTIONS §4(a)),
> carregando a nota datada de reconciliação em cinco eixos do concept D10.

## 2. Tasks

> Faixa saudável: **3–12 Tasks por Stage** (CONVENTIONS §6). São **10**.

### Task 01 — schema do BC staff em SQLAlchemy Core

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/out/__init__.py`
  - `src/restaurant_hub/features/staff/adapters/out/postgres/__init__.py`
  - `src/restaurant_hub/features/staff/adapters/out/postgres/tables.py`
  - `tests/unit/features/staff/adapters/__init__.py`
  - `tests/unit/features/staff/adapters/test_tables.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** descrever as **cinco** tabelas do concept §9 num `MetaData`
  próprio (`staff_metadata`), em Core, com **toda constraint nomeada**.
- **Detalhes técnicos:** exatamente a tabela do concept §9, já exercitada contra
  Postgres real no probe de 2026-08-10. O que não pode escapar:
  - `uq_job_functions_id_tenant` e `uq_employees_id_tenant` são **âncoras
    obrigatórias** das FKs compostas — sem elas a migration da Task 02 nem roda.
  - `employee_job_functions` carrega `tenant_id NOT NULL` e **duas** FKs
    compostas: `→ employees(id, tenant_id)` **CASCADE** e
    `→ job_functions(id, tenant_id)` **RESTRICT**. Uma só deixaria o outro lado
    livre (concept §5.8; ADR 3.3.0001).
  - `employee_unavailabilities` e `employee_shift_preferences` **não** carregam
    `tenant_id` — a coluna existe onde ancora um cerco, e ali não ancora nenhum
    (D2; precedente `sessions`).
  - **Nenhuma FK para `restaurants`/`units` de identity** (D1, ADR 3.3.0002):
    `tenant_id` e `unit_id` são `Text NOT NULL` opacos.
  - `weekly_hours` é `NUMERIC` **sem precisão declarada** — `NUMERIC(5,2)`
    arredonda em silêncio (medido: `22.555 → 22.56`), corrompendo dado contra a
    disciplina verbatim do projeto. Tipo é contrato, não detalhe.
  - Instantes em `TIMESTAMP` **WITHOUT TIME ZONE** (o oposto de identity —
    `UnavailabilityPeriod` rejeita tz-aware, ADR 3.1.0005). Texto em `TEXT`,
    nunca `CHAR(n)` (padding quebraria o round-trip verbatim).
  - Cinco `CHECK`: `ck_employees_workload_kind_known`,
    `ck_employees_workload_iff_hours`, `ck_employees_weekly_hours_positive`,
    `ck_employee_unavailabilities_period` (`start_at < end_at`),
    `ck_employee_shift_preferences_period_known`. Os valores aceitos por
    `workload_kind` e por `period` são **derivados** dos tipos de domínio
    (`DayPeriod`), não repetidos à mão — duas listas divergem no dia em que uma
    delas crescer (precedente `tables.py` de identity com `Role`).
  - Três índices e só três (D5, ADR 3.3.0005): `uq_job_functions_tenant_name`
    (que já serve `find_by_name` e `list_by_tenant`), `ix_employees_tenant_unit`,
    `ix_employee_job_functions_function(job_function_id, tenant_id)` — este
    último não é otimização: sem ele o `RESTRICT` varre a tabela inteira a cada
    remoção de função.
- **Critério de aceite:** teste unitário (sem banco) assere o conjunto das cinco
  tabelas em `staff_metadata`, os nomes de **todas** as constraints, que
  `employee_job_functions` tem **duas** FKs compostas com `ondelete` `CASCADE` e
  `RESTRICT` respectivamente, que as duas filhas sem cerco **não** têm coluna
  `tenant_id`, que `weekly_hours` é `Numeric` **sem** `precision`/`scale`, e que
  nenhuma FK aponta para tabela fora de `staff_metadata`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/adapters/test_tables.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): descrever schema do BC em sqlalchemy core [3.3/task-01]`

---

### Task 02 — migration `0003_staff`, metadatas combinados, limpeza compartilhada e integração de schema

- **Arquivos a criar:**
  - `migrations/versions/0003_staff.py`
  - `tests/integration/features/staff/__init__.py`
  - `tests/integration/features/staff/adapters/__init__.py`
  - `tests/integration/features/staff/adapters/out/__init__.py`
  - `tests/integration/features/staff/adapters/out/postgres/__init__.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_schema.py`
- **Arquivos a modificar:**
  - `migrations/env.py` (`target_metadata = [identity_metadata, staff_metadata]`)
  - `tests/conftest.py` (`TABELAS_EM_ORDEM_DE_LIMPEZA`)
  - `tests/integration/test_migration.py`
- **O que fazer:** materializar o schema da Task 01 no banco e travar, contra o
  catálogo do Postgres, o que só o banco pode confirmar.
- **Detalhes técnicos:**
  - `revision = "0003"`, `down_revision = "0002"`. **`0002` já foi consumido** por
    `password_setup_tokens` (Stage 2.5); o roadmap ainda diz `0002_staff.py` e é
    reconciliado por nota datada no fechamento (D10).
  - `downgrade()` derruba na ordem inversa das dependências de FK (as três filhas,
    depois `employees`, depois `job_functions`).
  - `migrations/env.py:39-41` **manda** combinar os metadatas quando o 2º BC
    chegar — é literalmente o comentário do arquivo. Trocar um pelo outro faria o
    autogenerate propor drop das tabelas de identity.
  - `TABELAS_EM_ORDEM_DE_LIMPEZA` ganha as cinco tabelas de staff, **filhas antes
    das mães**, mantendo a **fonte única** compartilhada por integração e
    contrato (o docstring do arquivo explica por que duas listas divergiriam).
  - `tests/integration/test_migration.py` passa a asserir também as cinco tabelas
    de staff após `upgrade` e a ausência delas após `downgrade base` (CA13).
  - `test_schema.py` consulta **`pg_constraint` E `pg_indexes`** (CA14): os nomes
    esperados; os **dois índices não-únicos**, que não aparecem em `pg_constraint`
    e por isso escapariam de uma consulta só; o `confdeltype` de cada FK (`r` para
    a de função, `c` para as três de filha); e os **tipos** de coluna via
    `information_schema.columns` — em especial `weekly_hours` como `numeric` com
    `numeric_precision IS NULL`. Assere também que **nenhuma** FK de staff aponta
    para tabela de identity (ADR 3.3.0002 verificado no catálogo, não só no
    `MetaData`).
  - `test_schema.py` cobre CA15 por `INSERT` direto: jornada `fixed` sem horas;
    `on_demand` **com** horas; `weekly_hours <= 0`; período com `start >= end`;
    `period` desconhecido — todos recusados pelo banco.
- **Critério de aceite:** CA13, CA14, CA15 e CA21 — `alembic upgrade head` seguido
  de `downgrade base` deixa o banco sem nenhuma tabela de staff e o `upgrade`
  seguinte funciona; o catálogo confirma nomes, `confdeltype`, os dois índices
  não-únicos e `weekly_hours numeric` sem precisão; as cinco linhas ilegais são
  recusadas; e **com o container parado a suíte falha** com a mensagem acionável
  da fixture `engine` — nunca pula, nunca fica verde.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run alembic upgrade head; uv run alembic downgrade base; uv run alembic upgrade head
  uv run pytest tests/integration -v
  docker compose stop postgres; uv run pytest tests/integration; docker compose start postgres
  make check
  ```
- **Commit sugerido:** `feat(staff): migration do schema de staff e limpeza compartilhada [3.3/task-02]`
  > **Exceção declarada ao critério de ≤ 5 arquivos:** são 9, dos quais **4 são
  > `__init__.py` vazios** da cadeia de pacote. O conteúdo é uma única mudança
  > lógica — o schema existindo no banco e sendo verificável.

---

### Task 03 — mappers puros e tradutor de integridade por operação

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/out/postgres/mappers.py`
  - `src/restaurant_hub/features/staff/adapters/out/postgres/integrity_errors.py`
  - `tests/unit/features/staff/adapters/test_mappers.py`
  - `tests/unit/features/staff/adapters/test_integrity_errors.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** a conversão linha↔entidade e a tradução de `IntegrityError`
  para os erros de aplicação da 3.2 — as duas peças puras, testáveis sem banco,
  que os adapters das Tasks 06/07 consomem.
- **Detalhes técnicos:**
  - **Reidratação passa pelo construtor** (§5.11): `FixedSchedule`/`OnDemand` →
    `ShiftPreference` → `UnavailabilityPeriod` → `Employee(...)`. **Proibido**
    `object.__setattr__`, `__new__` ou `dataclasses.fields`. É esta regra — e só
    ela — que impõe as três invariantes que o schema não consegue impor (§5.19);
    linha corrompida **levanta ao ser lida**.
  - **O mapper NÃO normaliza fuso** (§5.12) — é o **oposto** da Regra 2 do mapper
    de identity, e a inversão é deliberada: `UnavailabilityPeriod` **rejeita**
    tz-aware (ADR 3.1.0005), então devolver aware daqui faria a reidratação
    levantar `InvalidUnavailabilityPeriodError` sobre dado válido. Escrever
    `.astimezone(UTC)` aqui por analogia com identity é o erro mais provável desta
    Task, e o teste assere `tzinfo is None` explicitamente.
  - **Sem linha em `employee_shift_preferences` ⇒ `shift_preference = None`**;
    linha(s) ⇒ `ShiftPreference(frozenset(...))`, que nunca é vazia (ADR 3.1.0004).
  - `integrity_errors.py` expõe, em **inglês** (D4; CONVENTIONS §1 — são API de
    módulo, não identificadores locais):
    `ConstraintMap = Mapping[str, Callable[[str], Exception]]`,
    `translate(error, constraint_map, detail) -> Exception` e os **quatro** mapas
    nomeados `ON_INSERT_JOB_FUNCTION`, `ON_UPDATE_JOB_FUNCTION`,
    `ON_DELETE_JOB_FUNCTION`, `ON_WRITE_EMPLOYEE`.
  - **O mapa é por operação porque a constraint sozinha é ambígua** (§5.14,
    ADR 3.3.0004): `fk_employee_job_functions_job_function` é violada tanto por
    `INSERT` de vínculo com função inexistente (⇒ `JobFunctionNotFoundError`,
    L-E4) quanto por `DELETE` da função referenciada (⇒ `JobFunctionInUseError`,
    L-JF3), com o **mesmo** `diag.constraint_name` e o mesmo sqlstate `23503`.
  - `translate` **devolve** (não levanta), como o `traduzir` de identity: o
    `raise ... from erro` fica no repositório, onde preserva `__cause__`.
  - **Constraint ausente do mapa da operação sobe intacta** — o próprio erro é
    devolvido. Isso vale para as **três** FKs de filha para pai, para as PKs das
    três filhas, para as cinco CHECK e para qualquer constraint desconhecida
    (concept §6, lista completa). Traduzi-las produziria um 4xx plausível
    escondendo um bug do mapper.
  - Extração do nome por `diag.constraint_name`, **nunca** por texto de mensagem
    (mesma função utilitária de identity, reescrita aqui com nome em inglês).
- **Critério de aceite:** CA15b e a metade unitária de CA8b — testes sem banco
  cobrem o round-trip de `JobFunction` e de `Employee` (incluindo `OnDemand` sem
  horas, `shift_preference` ausente e presente, e períodos), a preservação de
  `tzinfo is None`, **cada** entrada de **cada** um dos quatro mapas, e os casos
  não traduzidos. Em especial: um `IntegrityError` cujo `constraint_name` é
  `fk_employee_job_functions_job_function` devolve `JobFunctionNotFoundError` sob
  `ON_WRITE_EMPLOYEE` e `JobFunctionInUseError` sob `ON_DELETE_JOB_FUNCTION` — um
  mapa global não conseguiria as duas.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/adapters/ -v
  make check
  ```
- **Commit sugerido:** `feat(staff): mappers de persistência e tradução de integridade por operação [3.3/task-03]`

---

### Task 04 — `L-ORD`: a lei nos ports, nos fakes, nas suítes e a âncora reconciliada

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/ports/out/job_function_repository.py`
  - `src/restaurant_hub/features/staff/application/ports/out/employee_repository.py`
  - `tests/fakes/features/staff/in_memory_job_function_repository.py`
  - `tests/fakes/features/staff/in_memory_employee_repository.py`
  - `tests/unit/features/staff/application/test_job_function_repository_laws.py`
  - `tests/unit/features/staff/application/test_employee_repository_laws.py`
  - `docs/stages/3.2-staff-application/concept.md` (nota datada de acréscimo)
- **O que fazer:** acrescentar a **décima terceira** lei — ordem total,
  determinística e independente de ambiente — nas três pontas em que ela precisa
  existir para ser verificável: a **declaração** (docstring do port), a
  **implementação de referência** (o fake) e o **teste** que a trava.
- **Detalhes técnicos:**
  - **Texto da lei** (§5.13, ADR 3.3.0003), nas docstrings dos dois ports:
    listagens (`list_by_tenant`, `list_by_unit`, `find_all_by_ids`) ordenam por
    `name` e desempatam por `id`, byte a byte; a reidratação de
    `unavailabilities` ordena por `start`. `shift_preference` e
    `job_function_ids` são `frozenset` — **sem ordem, sem lei**.
  - **A âncora é reconciliada nas duas pontas** (D11): as docstrings de módulo
    hoje dizem que cada método "cita a lei nomeada do **concept §4**" (da 3.2);
    passam a dizer "concept §4 da 3.2 **+ `L-ORD` (ADR 3.3.0003, Stage 3.3)**", e
    o concept da 3.2 recebe **nota datada** de acréscimo. Sem isso a lei existe no
    código e não existe na fonte que o código nomeia — referência pendurada.
  - **Fake de função:** `list_by_tenant` e `find_all_by_ids` passam a devolver
    `sorted(..., key=lambda f: (f.name, f.id))`.
  - **Fake de funcionário:** `list_by_unit` idem; e **`find_by_id`/`list_by_unit`
    passam a devolver o agregado com `unavailabilities` ordenadas por `start`**.
    Atenção: o fake guarda a entidade inteira e `add_unavailability` **não**
    ordena, então sem isto o fake reprovaria CA11 enquanto o Postgres passaria —
    divergência na direção contrária à habitual. A reordenação usa
    `dataclasses.replace`, que passa pelo `__post_init__` como uma construção
    direta passaria.
  - `sorted()` do Python sobre `str` é comparação por **codepoint**, e o probe
    mediu que ela **coincide exatamente** com `ORDER BY … COLLATE "C"` — é essa
    coincidência que permite um corpo de teste só para as duas implementações.
  - **Testes novos** nas duas suítes (ainda em `tests/unit/`, movidas na Task 05),
    nomeados com a lei: `test_l_ord_*`. Cobrem CA10 (dado adversarial: nome
    acentuado, case misto, espaço à direita, **dois homônimos de ids diferentes**
    — sem homônimos o desempate por `id` é inalcançável e a metade da lei que a
    paginação da 3.4 usa fica não travada) e CA11 (períodos inseridos fora de
    ordem cronológica reidratam ordenados).
  - **CA12 é travado por teste**, não por revisão: um teste assere `"L-ORD"` e a
    citação da nova âncora nos `__doc__` dos dois módulos de port — mesma forma
    do `test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port`
    que já existe.
  - **A "Nota deliberada" de `test_employee_repository_laws.py:317-322` sai neste
    commit.** Ela declara que a ordem "NÃO é travada por teste, e isso não é
    esquecimento" — vira **falsa** na linha em que o primeiro `test_l_ord_*`
    entra. Deixá-la seria a Stage afirmar duas coisas contraditórias sobre o
    próprio código (CA4).
- **Critério de aceite:** CA11, CA12 e a metade `[fake]` de CA10 — os testes
  `test_l_ord_*` passam contra o fake; as docstrings dos dois ports declaram
  `L-ORD` e citam a âncora nova; o concept da 3.2 tem a nota datada; a nota
  deliberada não existe mais; `make typecheck` (que alcança `tests/fakes/`) limpo.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/ -v -k "l_ord or documentada"
  uv run pytest tests/unit/features/staff/ -v
  make check
  ```
- **Commit sugerido:** `feat(staff): lei de ordem total nos ports de staff e nos fakes [3.3/task-04]`
  > **Exceção declarada ao critério 4 de Task Atômica** (não misturar port com
  > implementação do port): o fake **é** implementação do port. A exceção é a
  > mesma da Task 02 da Stage 2.3 e pela mesma razão mecânica — declarar uma lei
  > no `Protocol` sem o fake obedecê-la deixaria a implementação de referência em
  > violação do próprio contrato por um commit inteiro, e o teste que a trava
  > falharia. O que o critério 4 protege de verdade — desenhar port e
  > implementação **de produção** no mesmo fôlego — segue respeitado: os adapters
  > reais só aparecem nas Tasks 06 e 07.
  >
  > **Exceção declarada ao critério de ≤ 5 arquivos:** são 7, e os 7 são a mesma
  > mudança lógica (uma lei nova) vista na declaração, na implementação de
  > referência, no teste e na fonte que a âncora cita.

---

### Task 05 — promoção das suítes de lei para `tests/contract/` (movimento e reassinatura)

- **Arquivos a criar:**
  - `tests/contract/features/staff/__init__.py`
  - `tests/contract/features/staff/conftest.py`
  - `tests/contract/features/staff/test_no_implementation_branching.py`
- **Arquivos a modificar (via `git mv`):**
  - `tests/unit/features/staff/application/test_job_function_repository_laws.py`
    → `tests/contract/features/staff/test_job_function_repository_laws.py`
  - `tests/unit/features/staff/application/test_employee_repository_laws.py`
    → `tests/contract/features/staff/test_employee_repository_laws.py`
- **O que fazer:** **mover** (nunca copiar — ADR 3.3.0007) as duas suítes para o
  contrato e reassinar todos os testes sobre uma fixture, **ainda com um só
  parâmetro** (`fake`). Comportamentalmente é um no-op: mesmas asserções, mesma
  implementação por trás.
- **Detalhes técnicos:**
  - Usar **`git mv`**, não criar-e-apagar: a suíte é o entregável de maior valor
    herdado da 3.2 e perder a linhagem dela no `git log --follow` é perder o
    histórico de por que cada lei existe.
  - `conftest.py` define
    `@dataclass(frozen=True) class RepositoriosDeStaff: job_functions: JobFunctionRepository; employees: EmployeeRepository`
    e a fixture `repos` com `params=["fake"]` (o `"postgres"` entra na Task 09).
    **`StaffFakes` não serve**: ele tipa `store: InMemoryStaffStore`, que o par
    real não tem — daí o holder novo (D7). O modelo é
    `tests/contract/features/identity/conftest.py` (holder `Repositorios`).
  - **Os dois repositórios vêm num pacote só**, pela razão do conftest de
    identity: L-JF3 e L-E4 falam de dados que vivem no **outro** agregado, e um
    par sobre stores/bancos diferentes as satisfaria **vacuamente**.
  - `pytestmark = pytest.mark.unit` → `pytest.mark.contract` nos dois módulos.
  - **A reassinatura, com números:** 45 das 46 funções passam de
    `def test_…() -> None` para `def test_…(repos: RepositoriosDeStaff) -> None`;
    os **três** helpers (`_com_funcao_gravada`, `_com_funcoes_gravadas`,
    `_com_funcionario_gravado`) passam a receber `repos` e deixam de construir o
    par; e os **49** call-sites de `staff_repositories()` e dos helpers passam a
    usar `repos`. Os **nomes** e as **asserções** dos testes **não mudam** — é
    isso que preserva o pareamento lei a lei.
  - O 46º teste
    (`test_l_e5_employee_in_use_error_existe_e_a_lei_esta_documentada_no_port`)
    **também recebe `repos`**, ainda que não o use — ver §1 "Decisões de detalhe".
  - **Nada de instrumentação fake-only entra no contrato**: nenhum dos 46 usa
    `store.calls` (verificado por grep), que é o critério da CA16 de identity.
  - `test_no_implementation_branching.py` implementa **CA2 por AST**: parseia os
    dois módulos de contrato e assere que nenhum corpo de teste referencia
    `request`, `param`, os literais `"fake"`/`"postgres"`, ou usa `isinstance`
    sobre um repositório. Grep aqui dá falso positivo (a palavra aparece em
    comprehension e em docstring); AST não dá.
- **Critério de aceite:** CA2 e CA4 — os 46 testes (mais os `test_l_ord_*` da
  Task 04) coletam sob `tests/contract/features/staff/` com o marker `contract`;
  `tests/unit/features/staff/application/` continua **verde** e sem import
  quebrado; nenhum teste de lei permanece em `tests/unit/`; o teste de AST passa;
  a contagem total de testes da suíte **não diminui**.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run pytest tests/contract/features/staff/ -v
  uv run pytest tests/unit/features/staff/ -v
  uv run pytest tests/ --collect-only -q | Select-String "laws" | Measure-Object -Line
  make check
  ```
- **Commit sugerido:** `test(staff): promover as suítes de lei para tests/contract [3.3/task-05]`

---

### Task 06 — `PostgresJobFunctionRepository` e sua integração

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/out/postgres/job_function_repository.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_job_function_repository.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** o primeiro dos dois adapters, implementando L-JF1…L-JF5 e a
  metade de `L-ORD` que lhe cabe.
- **Detalhes técnicos:**
  - Forma de identity, não a da folha da skill (D8): módulo plano,
    `__init__(self, engine: Engine)`, `with engine.begin()` por método público,
    sem Unit of Work. O núcleo de cada método opera sobre `Connection`, que é o
    ponto de troca para um futuro UoW.
  - `add`: `INSERT` **puro**, sem `ON CONFLICT` (§5.2) — upsert é exatamente a
    dívida que a 2.3 pagou (ADR 2.3.0003). Traduz com `ON_INSERT_JOB_FUNCTION`.
  - `update`: `UPDATE … WHERE id = :id AND tenant_id = :t`, com `rowcount == 0` ⇒
    `JobFunctionNotFoundError`. **`tenant_id` nunca entra no `SET`** (§5.3), só no
    `WHERE`. Traduz com `ON_UPDATE_JOB_FUNCTION` (conflito de nome ⇒
    `JobFunctionNameAlreadyExistsError`; renomear para o próprio nome **não** é
    conflito, e o índice único resolve isso sozinho).
  - `delete`: o lookup por `(tenant_id, id)` vem **antes** — `rowcount == 0` ⇒
    `JobFunctionNotFoundError`, **nunca** `JobFunctionInUseError`, que confirmaria
    a existência do registro alheio. Referência ⇒ FK `RESTRICT` traduzida com
    `ON_DELETE_JOB_FUNCTION` ⇒ `JobFunctionInUseError`. As guardas e a escrita
    rodam na **mesma** transação (§5.4) — senão a ordem é decorativa sob
    concorrência.
  - Unicidade de nome **verbatim e por tenant**: sem `lower()`, sem `btrim`, sem
    `ILIKE` — nem no `find_by_name`, nem na guarda (§5.6). Normalizar "parece
    certo" e é o erro mais fácil de cometer aqui.
  - `list_by_tenant` e `find_all_by_ids` levam
    `ORDER BY name COLLATE "C", id COLLATE "C"` — **as duas colunas**, porque o
    `COLLATE` liga-se ao operando à esquerda e um `id` sem colação explícita volta
    a depender da colação do banco, justamente no termo que a paginação da 3.4
    usa como cursor (§5.13).
  - `find_all_by_ids` com conjunto **vazio** devolve `()` sem ir ao banco ou com
    `IN ()` seguro — L-JF4 exige que não levante.
- **Critério de aceite:** os testes de integração cobrem L-JF1…L-JF5 contra o
  banco real — id duplicado (mesmo tenant **e** outro tenant), nome duplicado
  verbatim no tenant, as quatro variantes de CA9 aceitas ao lado do original,
  `update`/`delete` de função ausente no tenant, remoção de função referenciada
  por funcionário **desligado** levantando `JobFunctionInUseError` com a função
  ainda legível (CA7), e as listagens em ordem. Cobertura do arquivo novo ≥ 90%
  no `term-missing`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run pytest tests/integration/features/staff/ -v
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing | Select-String "job_function_repository"
  make check
  ```
- **Commit sugerido:** `feat(staff): repositório postgres de função de trabalho [3.3/task-06]`

---

### Task 07 — `PostgresEmployeeRepository` e sua integração

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/adapters/out/postgres/employee_repository.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_employee_repository.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** o adapter com regra de verdade — agregado de quatro tabelas,
  ordem de checagem normativa, escrita das filhas por diferença e leitura sob
  snapshot único.
- **Detalhes técnicos:**
  - **Ordem em `add`: L-E1 precede L-E4** (§5.5). Isso exige um
    `SELECT 1 FROM employees WHERE id = :id` **explícito antes** da pré-checagem
    referencial: a ordem natural do SQL é a inversa (a colisão de id só apareceria
    no `INSERT`), e uma entrada que viola as duas leis responderia
    `JobFunctionNotFoundError` onde o fake responde `EmployeeAlreadyExistsError`.
    **Nenhum dos 46 testes herdados discrimina esse caso** — por isso ele é
    invariante declarada, e o teste dedicado (CA5b) entra na Task 09, no contrato,
    onde vale para as duas implementações.
  - **Ordem em `update`:** lookup por `(tenant_id, id)` com
    `SELECT unit_id … FOR UPDATE` → comparação de `unit_id`
    (`EmployeeRelocationError`, intra-tenant) → pré-checagem do conjunto de
    funções (`JobFunctionNotFoundError`). Tudo na **mesma** transação da escrita.
    O `FOR UPDATE` serializa duas edições concorrentes do mesmo registro (§5.4).
  - **As filhas são escritas por diferença, nunca por reescrita cega** (§5.20):
    apagar todos os vínculos e reinseri-los tocaria linhas que não mudaram e
    inverteria a ordem de lock em relação a um `delete_job_function` concorrente —
    medido, isso produz `40P01 DeadlockDetected`, que é `OperationalError` e
    **escapa do tradutor**, virando 500 na 3.4. Apagar só os removidos e inserir
    só os acrescentados.
  - **`find_by_id` e `list_by_unit` leem sob `REPEATABLE READ`** (§5.18): montam o
    `Employee` a partir de quatro tabelas em statements separados, e sob
    `READ COMMITTED` cada statement pega snapshot novo — medido, produz agregado
    misto ou funcionário sem funções, que a §5.11 faz levantar
    `EmptyJobFunctionsError` num caminho que o port (`-> Employee | None`) não
    prevê.
  - **L-E4 reporta a menor id ausente, deterministicamente** (§5.15): a
    pré-checagem itera `sorted(job_function_ids)`; o backstop (a corrida que a FK
    pega) renderiza o **conjunto** com `sorted()`. Sem isso,
    `test_l_e4_reporta_a_id_ausente_de_forma_deterministica` (que exige `"f97"`)
    falharia de forma **intermitente** contra `[postgres]`, por `PYTHONHASHSEED`.
  - `list_by_unit` **filtra `active` no SQL**, não em Python (§5.17). Hoje as duas
    formas são indistinguíveis por teste; é restrição de implementação declarada,
    porque a 3.4 acrescenta `LIMIT`/`OFFSET` e filtro em Python depois do fetch
    pagina errado. `ORDER BY name COLLATE "C", id COLLATE "C"`;
    `unavailabilities` reidratam com `ORDER BY start_at`.
  - `exists_by_job_function`:
    `SELECT EXISTS(SELECT 1 FROM employee_job_functions WHERE tenant_id = :t AND job_function_id = :f)`
    — **sem join, sem filtro de `active`** (§5.16, L-E7).
  - `delete`: `rowcount == 0` ⇒ `EmployeeNotFoundError`; as filhas somem por
    `CASCADE`. `EmployeeInUseError` **não tem produtor em v1** — entra no Step 4.
  - Escritas traduzem com `ON_WRITE_EMPLOYEE`.
- **Critério de aceite:** os testes de integração cobrem L-E1…L-E7 contra o banco
  real, mais **CA16** (linhas gravadas por SQL direto que violem as **três**
  invariantes não impostas pelo schema — funcionário sem função, nome
  vazio/whitespace, dois períodos sobrepostos — fazem `find_by_id` **levantar**
  `EmptyJobFunctionsError`/`InvalidNameError`/`OverlappingUnavailabilityError`, e
  não devolver entidade inválida) e **CA17** (round-trip preserva `Decimal` em
  notação posicional — valor **e** escala, `22.50` volta `22.50` — e `datetime`
  ingênuo com microssegundos e `tzinfo is None`). Cobertura do arquivo novo ≥ 90%.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run pytest tests/integration/features/staff/ -v
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing | Select-String "employee_repository"
  make check
  ```
- **Commit sugerido:** `feat(staff): repositório postgres de funcionário [3.3/task-07]`

---

### Task 08 — conduta e concorrência: os três invariantes medidos

- **Arquivos a criar:**
  - `tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** reproduzir, como teste, os três comportamentos que o concept
  mediu no probe e que **nenhuma asserção sobre estado final distingue de sua
  ausência**. É a Task que fecha o finding herdado nº 4 ("a suíte travava
  resultado, não conduta"). Se a Task 07 estiver correta, ela nasce verde; se
  qualquer das três peças (transação, `FOR UPDATE`, `REPEATABLE READ`) tiver sido
  omitida, é **aqui** que aparece — em nenhum outro lugar aparece.
- **Detalhes técnicos:**
  - **CA6b — o `FOR UPDATE` existe.** Duas conexões: com o `update` de A em curso
    e **não commitado**, o `update` do **mesmo** registro por B **bloqueia** até o
    commit de A. Implementar com `lock_timeout` curto ou thread com timeout, e
    asserir o bloqueio (não o resultado final, que é idêntico com e sem lock).
  - **CA17b — a leitura não é rasgada.** Com uma escrita concorrente commitando
    **entre** os statements da leitura, `find_by_id` devolve um agregado
    **consistente**: nunca pai antigo com filha nova, nunca funcionário sem
    funções. O ponto de entrelace precisa ser forçado (evento
    `after_cursor_execute` ou barreira entre statements) — sem forçá-lo o teste
    passa por sorte e não prova nada.
  - **Deadlock por reescrita cega (§5.20).** Um `update` que **não** mexe no
    conjunto de funções, concorrente com um `delete_job_function` de outra função,
    **não** levanta `40P01`. O teste é a regressão que impede a "simplificação"
    futura de trocar a escrita por diferença por `DELETE`-tudo-`INSERT`-tudo —
    que passa em todos os outros testes.
  - **CA8b — os dois lados da mesma constraint, contra o banco.** Um `INSERT` de
    vínculo que chegue à FK **sem** passar pela pré-checagem produz
    `IntegrityError` cujo `constraint_name` é
    `fk_employee_job_functions_job_function`; `translate(erro, ON_WRITE_EMPLOYEE, …)`
    devolve `JobFunctionNotFoundError` — **não** `JobFunctionInUseError`. É a
    contrapartida real da metade unitária da Task 03: aqui o erro vem do Postgres,
    não de um `IntegrityError` construído no teste.
  - **CA8c — o discriminador de conduta.** A mensagem do caminho comum cita a
    **menor** id ausente (`"f97"` com `{f97, f99}`, estável entre execuções); a do
    backstop cita o **conjunto** `sorted()`. Essa diferença é a **única** evidência
    observável de qual das duas camadas de guarda respondeu — sem ela, um adapter
    sem pré-checagem nenhuma passaria em tudo mais.
  - **CA10b — a cláusula de colação existe.** Duas partes:
    1. **Sobre o SQL:** o texto compilado de **cada uma das três** listagens
       contém `COLLATE "C"` nos **dois** termos do `ORDER BY`. Aceita-se obter o
       texto do statement efetivamente emitido (`before_cursor_execute`) ou de
       `str(stmt.compile(dialect=postgresql.dialect()))` — ver §1 "Decisões de
       detalhe". **É esta parte, e só ela, que reprova a omissão**: medido, em
       `postgres:16-alpine` (musl) `ORDER BY name` e `ORDER BY name COLLATE "C"`
       produzem saída **idêntica** para qualquer dado, inclusive o adversarial de
       CA10. Uma asserção sobre resultado passaria hoje e sempre, e explodiria no
       primeiro cluster glibc/ICU.
    2. **Controle positivo, sobre o banco:** o mesmo `ORDER BY` com
       `COLLATE "und-x-icu"` **diverge** do `sorted()` do Python
       (`Álvaro < ana < Ana < Zeus`) — prova que a escolha de colação tem efeito
       semântico e que a cláusula não é ruído.
- **Critério de aceite:** CA6b, CA8b (metade de integração), CA8c, CA10b e CA17b
  — cada um com teste dedicado que **reproduz** o comportamento, e não apenas
  observa o estado final. Nenhum destes testes depende de ordenação de
  agendamento do SO para passar (sem `sleep` como sincronização).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run pytest tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py -v
  uv run pytest tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py -v --count 3
  make check
  ```
  > Se o plugin `pytest-repeat` não estiver disponível, repetir a invocação três
  > vezes à mão: o objetivo é flagrar flakiness de teste de concorrência **antes**
  > de ele entrar no gate, não instalar dependência nova.
- **Commit sugerido:** `test(staff): travar conduta de bloqueio, isolamento e colação [3.3/task-08]`

---

### Task 09 — o contrato passa a rodar contra Postgres

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `tests/contract/features/staff/conftest.py`
  - `tests/contract/features/staff/test_job_function_repository_laws.py`
  - `tests/contract/features/staff/test_employee_repository_laws.py`
- **O que fazer:** a Task que **cobra o objetivo da Stage**. A fixture ganha o
  parâmetro `postgres`, e os 46 + N testes de lei passam a rodar duas vezes cada.
  Uma divergência fake↔adapter aparece como **o mesmo teste verde em `[fake]` e
  vermelho em `[postgres]`** — que é exatamente o sintoma que a 2.3 não teve e
  pagou caro por não ter.
- **Detalhes técnicos:**
  - `params=["fake", "postgres"]`. No ramo `postgres`: `engine` vem de
    `request.getfixturevalue("engine")` (a fixture de `tests/conftest.py`, que
    **falha alto** sem banco — o contrato herda a exigência do ADR 2.3.0001),
    seguido de `truncar_tudo(engine)` e da construção dos dois adapters sobre o
    **mesmo** `Engine`. Idêntico ao conftest de identity.
  - **Testes acrescentados** (que precisam das duas implementações para ter
    sentido):
    - **CA5b** — `add` de funcionário com id **já gravado** e conjunto de funções
      **inexistente** levanta `EmployeeAlreadyExistsError`, não
      `JobFunctionNotFoundError` (§5.5). É o caso que nenhum dos 46 herdados
      discrimina.
    - **CA10** — as três listagens devolvem a **mesma sequência** nas duas
      implementações, com dado adversarial (nome acentuado, case misto, espaço à
      direita, dois homônimos de ids diferentes), e essa sequência é igual ao
      `sorted()` do Python com desempate por `id`.
    - **CA11** — períodos fora de ordem cronológica reidratam ordenados nas duas
      implementações.
    (Os `test_l_ord_*` da Task 04 já estão nos arquivos; aqui eles ganham o
    segundo parâmetro. CA5, CA6, CA7, CA8 e CA9 são **testes herdados** que só
    agora viram prova sobre o adapter real — não precisam de teste novo.)
  - Nenhum corpo de teste ramifica por implementação; o teste de AST da Task 05
    continua verde (CA2).
  - **Se algum teste reprovar em `[postgres]`, a correção é no adapter, não no
    teste.** A lei é o contrato publicado pela 3.2 e não se relaxa por conveniência
    de implementação (§5.1). Se a lei em si parecer errada, é regressão de concept
    — **PARAR** e perguntar.
- **Critério de aceite:** CA1, CA3, CA5, CA5b, CA6, CA7, CA8, CA9, CA10 e CA11 —
  `pytest --collect-only -q` mostra **cada** teste de lei duas vezes (`[fake]` e
  `[postgres]`); as **doze** leis mais `L-ORD` têm teste com o nome da lei no
  identificador, e todos passam nos dois parâmetros; nenhum teste de lei
  permanece em `tests/unit/`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run pytest tests/contract/features/staff/ -v
  uv run pytest tests/contract/features/staff/ --collect-only -q
  uv run pytest tests/contract/features/staff/ -v -k "postgres"
  make check
  ```
- **Commit sugerido:** `test(staff): parametrizar o contrato de staff sobre o postgres real [3.3/task-09]`

---

### Task 10 — wiring dos repositórios e dos 16 use cases no composition root

- **Arquivos a criar:**
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
- **O que fazer:** montar os dois repositórios e os **16** use cases de staff no
  único ponto de wiring, expostos em `ApplicationDependencies` como campos
  `staff_*`.
- **Detalhes técnicos:**
  - Duas fontes fecham a alternativa "wire só os repositórios" (D9): o bloco 3.3
    do roadmap lista `composition_root.py` em `arquivos_a_modificar`, e o
    docstring de `ApplicationDependencies` é explícito — "expõe **use cases**, não
    repositórios". Não há fork a registrar em ADR.
  - Os 16 use cases são os de
    `features/staff/application/use_cases/`: `assign_job_functions`,
    `change_workload_profile`, `copy_employee_to_unit`, `create_employee`,
    `create_job_function`, `deactivate_employee`, `declare_shift_preference`,
    `delete_employee`, `delete_job_function`, `list_employees`,
    `list_job_functions`, `reactivate_employee`, `register_unavailability`,
    `remove_unavailability`, `rename_employee`, `rename_job_function`.
  - **Sem singleton global** e sem `Engine` novo: reusar o `engine` já construído
    em `wire_dependencies`, como os repositórios de identity fazem.
  - **`.importlinter` não muda.** A supressão existente é a aresta
    `shared.infrastructure.http.app -> composition_root`, que não é específica de
    identity; e `bc-independence` compara `features.identity` × `features.staff`,
    dos quais o composition root não faz parte. Se `make import-check` reprovar,
    **PARAR** e reportar — seria sinal de que a premissa está errada, não convite
    a alargar supressão.
  - **Custo declarado, e o teste sabe disso:** são 16 campos públicos sem
    consumidor até a 3.4. CA18 prova que estão **montados sobre os adapters
    Postgres**, não que estão exercitados.
- **Critério de aceite:** CA18 — `wire_dependencies()` devolve os 16 use cases de
  staff, cada um com o repositório injetado sendo instância do adapter Postgres
  (não de fake), e um teste mecânico verifica que **nenhum módulo fora de
  `composition_root.py`** importa `features.staff.adapters.out.postgres` (espelho
  do `test_composition_root_identity.py`). `make import-check` verde.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  uv run pytest tests/unit/features/staff/adapters/test_composition_root_staff.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): wiring dos repositórios e use cases de staff no composition root [3.3/task-10]`

---

## 2.1 Matriz de rastreabilidade

**Regra:** nada órfão nos dois sentidos — todo critério/lei/ADR tem ao menos uma
Task que o entrega, e nenhuma Task existe sem item que a justifique.

### Critérios de aceite do concept §11 → Task

| Critério | Task(s) | Onde o check acontece |
|---|---|---|
| CA1 — suítes em `tests/contract/`, cada teste roda duas vezes | 05, **09** | `--collect-only -q` mostra `[fake]` e `[postgres]` |
| CA2 — nenhum corpo ramifica por implementação (por AST) | **05** | `test_no_implementation_branching.py` |
| CA3 — 12 leis + `L-ORD` com o nome no identificador, verdes nos dois params | 04, **09** | `pytest -v` das duas suítes |
| CA4 — unit verde após a remoção; "Nota deliberada" removida | 04 (nota), **05** (remoção) | `pytest tests/unit/features/staff/` |
| CA5 — `add` com id gravado em **outro tenant** é erro | 06, 07, **09** | teste herdado L-JF1/L-E1 agora em `[postgres]` |
| CA5b — id gravado **e** funções inexistentes ⇒ `EmployeeAlreadyExistsError` | 07 (ordem no adapter), **09** (teste) | contrato, nos dois params |
| CA6 — `update` com tenant alheio **e** unidade divergente ⇒ `NotFound` | 07, **09** | teste herdado L-E3 agora em `[postgres]` |
| CA6b — *(conduta)* `FOR UPDATE` bloqueia a 2ª conexão | **08** | `test_staff_conduct.py` |
| CA7 — `delete` de função referenciada por **desligado** ⇒ `InUse` | **06**, 09 | integração + contrato |
| CA8 — função de outro tenant ⇒ `JobFunctionNotFoundError`, nada gravado | 07, **09** | integração + contrato |
| CA8b — a mesma FK, os dois significados | **03** (unit), **08** (integração) | `test_integrity_errors.py` + conduta |
| CA8c — *(conduta)* menor id × conjunto `sorted()` | **08** | `test_staff_conduct.py` |
| CA9 — quatro variantes verbatim aceitas | **06**, 09 | integração + contrato parametrizado |
| CA10 — mesma sequência nas duas implementações, = `sorted()` | 04 (fake), **09** (contrato) | contrato |
| CA10b — *(conduta)* `COLLATE "C"` no SQL + controle `und-x-icu` | **08** | `test_staff_conduct.py` |
| CA11 — períodos reidratam por `start_at` nas duas | 04 (fake), **09** (contrato) | contrato |
| CA12 — docstrings declaram `L-ORD` + âncora; nota datada na 3.2 | **04** | teste sobre `__doc__` |
| CA13 — `upgrade`/`downgrade`/`upgrade` limpos | **02** | `test_migration.py` |
| CA14 — `pg_constraint` **e** `pg_indexes`, `confdeltype`, tipos | **02** | `test_schema.py` |
| CA15 — `INSERT` direto ilegal recusado pelo banco | **02** | `test_schema.py` |
| CA15b — constraint não mapeada sobe intacta; FKs de filha não traduzidas | **03** | `test_integrity_errors.py` |
| CA16 — as três invariantes que o schema não impõe **levantam ao ler** | **07** | integração de funcionário |
| CA17 — round-trip de `Decimal` (valor e escala) e `datetime` ingênuo | **07** | integração de funcionário |
| CA17b — *(isolamento)* leitura consistente sob escrita concorrente | **08** | `test_staff_conduct.py` |
| CA18 — 16 use cases montados sobre os adapters reais; nada instancia fora | **10** | `test_composition_root_staff.py` |
| CA19 — `make check` verde (import-check e layout-check inclusos) | **todas** + §3 | comando de verificação de cada Task |
| CA20 — cobertura ≥ 90% em **cada** arquivo novo do adapter | 01, 03, **06**, **07** + §3 | `--cov-report=term-missing` lido arquivo a arquivo |
| CA21 — nenhum teste pula por falta de banco | **02** + §3 | container parado ⇒ suíte **falha** |

### As treze leis → Task que as entrega

| Lei | Declarada | Implementada (Postgres) | Provada nos dois params |
|---|---|---|---|
| L-JF1 `add` é inserção | 3.2 | **06** | **09** |
| L-JF2 `update` é `UPDATE` | 3.2 | **06** | **09** |
| L-JF3 remoção guardada | 3.2 | **06** (FK `RESTRICT` + `ON_DELETE_JOB_FUNCTION`) | **09** |
| L-JF4 `find_all_by_ids` não levanta | 3.2 | **06** | **09** |
| L-JF5 `list_by_tenant` | 3.2 | **06** | **09** |
| L-E1 `add` é inserção, id global | 3.2 | **07** (`SELECT` explícito antes de L-E4) | **09** |
| L-E2 `update` é `UPDATE` | 3.2 | **07** | **09** |
| L-E3 localização imutável | 3.2 | **07** (após o lookup `FOR UPDATE`) | **09** |
| L-E4 validade referencial | 3.2 | **03** (tradutor) + **07** (pré-checagem) + **08** (conduta) | **09** |
| L-E5 remoção guardada | 3.2 | **07** | **09** |
| L-E6 listagem por unidade | 3.2 | **07** (`active` no SQL) | **09** |
| L-E7 referência a função | 3.2 | **07** (`EXISTS`, sem join, sem `active`) | **09** |
| **`L-ORD`** ordem total | **04** (ports + fake + nota na 3.2) | **06** e **07** (`COLLATE "C"`, `start_at`) | **08** (a cláusula) + **09** (a sequência) |

### ADRs desta Stage → Task que os efetiva

| ADR | Task(s) |
|---|---|
| **3.3.0001** — `tenant_id` só onde há cerco; FKs compostas | **01** (schema), **02** (catálogo confirma) |
| **3.3.0002** — nenhuma FK atravessa bounded context | **01**, **02** (`pg_constraint` não mostra alvo em identity) |
| **3.3.0003** — ordem total com `COLLATE "C"` como lei de port | **04**, **06**, **07**, **08**, **09** |
| **3.3.0004** — tradução por constraint **e** por operação | **03**, **06**, **07**, **08** |
| **3.3.0005** — três índices pelo acesso medido; RLS rejeitada | **01** (índices), **02** (`pg_indexes`; nenhuma policy) |
| **3.3.0006** — atomicidade nas duas pontas, sem lock otimista | **07** (transação + `FOR UPDATE` + filhas por diferença + `REPEATABLE READ`), **08** (as provas) |
| **3.3.0007** — suítes de lei **promovidas**, não copiadas | **05** (`git mv`), **09** (parametrização) |

### Decisões sem ADR (D8–D11) → Task

| Decisão | Task |
|---|---|
| **D8** — forma do adapter: a de identity, módulos planos | **06**, **07** |
| **D9** — composition root expõe os 16 use cases | **10** |
| **D10** — nota datada de reconciliação do bloco 3.3 do roadmap | fechamento, commit off-task `[3.3/--]` |
| **D11** — âncora de `L-ORD` reconciliada nas duas pontas | **04** |

## 3. Gate de saída da Stage

### Verificações automatizadas

```powershell
$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
docker compose up -d postgres          # o gate exige banco real (ADR 2.3.0001)
make check                             # lint + typecheck + layout + import + lock + docs + testes com cobertura
uv run alembic upgrade head; uv run alembic downgrade base; uv run alembic upgrade head
uv run python scripts/check_technical_postexec.py docs/stages/3.3-staff-persistence/technical.md
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
uv run pytest tests/contract/features/staff/ --collect-only -q
```

### Verificações funcionais

- [ ] Migration aplica **e reverte** contra Postgres real, com saída colada.
- [ ] Os dois repositórios exercitados contra o banco real — é o e2e possível
      desta Stage (a API de staff só existe na 3.4).
- [ ] Suíte de contrato verde contra **as duas** implementações, com o
      `--collect-only` mostrando `[fake]` e `[postgres]` para cada teste de lei.
- [ ] Com o container de Postgres parado, a suíte **falha** — nunca fica verde
      por ter pulado (CA21).
- [ ] `wire_dependencies()` executado de verdade (não só importado) devolvendo os
      16 use cases de staff montados sobre os adapters Postgres.

### Checklist de fechamento da Stage

- [ ] Todas as 10 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch, **com Postgres no ar**
- [ ] Cobertura ≥ 90% em cada arquivo tocado (não só na média global) — CA20
- [ ] Auditoria de testes com todos os itens "sim", incluindo **mutação real** no
      mapper (a normalização de fuso), na ordem de checagem do `update` e no
      `ORDER BY`
- [ ] §7 reflete a execução real
- [ ] `roadmap.md` atualizado em commit `[3.3/--]`: Stage `done`, datas e a **nota
      datada de reconciliação em cinco eixos** (D10 — migration `0003`,
      `arquivos_a_modificar`, `contratos_introduzidos`, `complexidade_estimada`
      `S`→`M`, `non_goals`)
- [ ] ADRs 3.3.0001–3.3.0007 em `status: accepted`
- [ ] Os quatro `[finding]` escalados (três para a 3.4, um para a 6.3) com Stage
      candidata identificada
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

Lista de arestas — deliberadamente **não** um diagrama ASCII, cuja arte é fácil de
desalinhar e passar a afirmar uma ordem que ninguém quis:

| Task | Depende de | Por quê |
|---|---|---|
| 01 `tables.py` | — | fonte única do schema; tudo mais o consome |
| 02 migration + env + limpeza | 01 | a migration materializa o `MetaData` da 01 |
| 03 mappers + tradutor | 01 | nomes de coluna e de constraint. **NÃO depende de 02** — os testes são unitários, sem banco |
| 04 `L-ORD` | — | **independente**; toca só `application` (docstring), fakes e as suítes de lei |
| 05 promoção (mover) | 04 | move as suítes **depois** de elas já terem os testes de `L-ORD` e sem a nota deliberada |
| 06 adapter de função | 02, 03 | precisa do schema no banco (02) e de mappers/tradutor (03) |
| 07 adapter de funcionário | 02, 03 | idem |
| 08 conduta e concorrência | 06, 07 | reproduz comportamento dos **dois** adapters |
| 09 contrato em `[postgres]` | 05, 06, 07 | precisa da suíte movida (05) e das duas implementações |
| 10 composition root | 06, 07 | liga os adapters reais aos 16 use cases |

Pontos que costumam ser lidos errado:

- **04 não depende de 01–03.** É a única Task que não toca persistência: declara a
  lei, corrige o fake e trava por teste. Poderia ser a Task 01; fica em 4º porque
  o schema é a fonte das constraints e vir primeiro reduz retrabalho, não porque
  haja dependência.
- **05 vem antes de 06/07 de propósito.** A promoção é o movimento arriscado, e
  isolá-lo num commit em que o comportamento é comprovadamente idêntico é o que
  torna um vermelho diagnosticável (§1).
- **09 é o único lugar onde uma lei pode reprovar.** Nada estrutural muda ali;
  uma string entra em `params`.
- **03 não depende de 02.** Mapper e tradutor são testados sem banco; só 06/07
  juntam as duas linhas.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| A reassinatura dos 49 call-sites da Task 05 quebrar testes por engano de refatoração | A Task 05 é comportamentalmente um no-op: qualquer vermelho ali é da mecânica. Comparar a contagem de testes coletados antes e depois (`--collect-only`) — ela **não pode** diminuir |
| Uma lei reprovar em `[postgres]` na Task 09 | Corrigir o **adapter**, nunca o teste (§5.1). Se a lei em si parecer errada, é regressão de concept: **PARAR** e perguntar |
| Teste de concorrência (Task 08) ficar flaky no CI | Sincronizar por evento/lock explícito, **nunca** por `sleep`; rodar 3× localmente antes de commitar. Se persistir, marcar `slow` **não** resolve (o gate roda tudo) — reformular a sincronização |
| `COLLATE "C"` ser esquecido e nenhum resultado reprovar (a imagem é musl, onde a colação default **já é** byte-order) | CA10b parte 1 assere sobre o **SQL**, que é a única asserção capaz de reprovar a omissão nesta imagem; a parte 2 (`und-x-icu`) é o controle positivo |
| Cobertura < 90% em arquivo de adapter por ramo de erro difícil de forçar | Forçar a violação por `INSERT` direto no teste de integração; se sobrar ramo genuinamente inalcançável, justificar por escrito no relatório (nunca `# pragma: no cover` silencioso) |
| `REPEATABLE READ` produzir `40001` (falha de serialização) em teste concorrente | `40001` é `OperationalError` e é comportamento esperado sob contenção — o teste deve asserir consistência da leitura, não ausência de retry. O mapeamento HTTP está escalado para a 3.4 |
| `make import-check` reprovar na Task 10 | **PARAR e reportar.** A premissa é que a supressão existente basta; alargá-la por conta própria trocaria um gate por uma exceção silenciosa |
| Mapper normalizar o `datetime` para UTC por analogia com identity | §5.12 explícita na Task 03 + teste de `tzinfo is None`; é o erro mais provável desta Stage e por isso tem asserção dedicada |
| Migration `0003` colidir com numeração futura de outra branch | Numeração conferida contra `migrations/versions/` no início da Task 02; conflito de `down_revision` é resolvido no rebase antes do PR |

## 6. Referências

- [`./concept.md`](./concept.md) — §5 invariantes, §9 schema já exercitado no
  probe de 2026-08-10, §11 critérios de aceite
- [`../3.2-staff-application/concept.md`](../3.2-staff-application/concept.md) —
  §4, as doze leis (fonte que `L-ORD` acrescenta, D11)
- [`../2.3-identity-persistence/technical.md`](../2.3-identity-persistence/technical.md)
  — precedente de forma das Tasks de persistência
- [`../../roadmap.md`](../../roadmap.md) — bloco `3.3-staff-persistence`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — §1 idioma, §4 commits, §6 tamanhos
- [`../../LAYOUT.md`](../../LAYOUT.md) — §2 estrutura, §3 dependências, §6 exceção
  do composition root
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `3_3_`) — 0001…0007
- Skills aplicáveis: `repository-pattern`, `pytest-with-fakes`, `composition-root`,
  `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
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

### YYYY-MM-DD — [tag] <Task NN ou escopo> — <Autor>
<!-- preencher quando aplicável; remover este placeholder se vazio -->

<!-- END: post-execution -->

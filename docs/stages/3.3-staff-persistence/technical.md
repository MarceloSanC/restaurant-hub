---
title: Technical — Persistência de equipe
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, staff-persistence, postgres, sqlalchemy-core, alembic, contract-tests, colacao, isolamento, concorrencia]
status: done
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
   assume o bloco de subida **com espera de prontidão** das Pré-condições — o
   `docker compose up -d` sozinho retorna antes de o banco aceitar conexão.
5. **Conduta separada de resultado.** Os três invariantes que o concept mediu
   empiricamente — dupla semântica da mesma FK, leitura rasgada sob
   `READ COMMITTED`, deadlock por reescrita cega das filhas — ganham **Task
   própria** (Task 08), com testes que os **reproduzem**. Eles são o finding
   herdado nº 4 ("a suíte travava resultado, não conduta") e, por construção,
   nenhuma asserção sobre estado final os distingue de sua ausência.
6. **Exceções declaradas ao critério de ≤ 5 arquivos** (PIPELINE §4.3, critério
   2): **só as Tasks 02 (9 arquivos) e 04 (7)** passam de cinco. Na 02 o
   excedente é mecânico — 4 dos 9 são `__init__.py` vazios de cadeia de pacote;
   na 04 os 7 são a **mesma** mudança lógica (a lei `L-ORD`) vista na
   declaração, na implementação de referência, no teste que a trava e na fonte
   que a âncora cita. Nenhuma das duas mistura escopos independentes, que é o
   que o critério protege. As demais ficam dentro do limite — inclusive a 05
   (5, contando os 2 movidos) e a 09 (3).

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
   intacta. As duas formas são aceitas pelo critério de aceite da Task 08, e a
   reconciliação com o texto literal do concept está registrada como
   `[decision]` datada na [§7](#7-execução-post-hoc-editável-após-done) —
   com a razão de por que ela **não** regride o concept.

### Pré-condições

- Stage `3.2-staff-application` em `done` e **mergeada** em `develop` (PR #36).
- Issue **#38** OPEN; branch `feat/38-3-3-staff-persistence` a partir de `develop`.
- Docker rodando. **Subir o banco e esperar a prontidão** — `docker compose up -d`
  (e `start`) retornam **antes** de o Postgres aceitar conexão, e a fixture
  `engine` usa `connect_timeout: 5`: sem a espera, a suíte falha com a mensagem
  de "Postgres não está acessível" tendo o container **no ar**, que é o
  diagnóstico errado. Bloco canônico, usado em todos os comandos desta Stage:
  ```powershell
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  ```
- **Esta worktree não tem `.env`** — só `.env.example`. Consequência **medida**,
  não suposição: `Settings()` cai no default embutido de `settings.py:42`
  (`postgresql+psycopg://user:pass@localhost:5432/restaurant_hub`), e a suíte
  roda contra o banco de `localhost:5432`. O concept §3 registra exatamente isso
  como premissa, e esta Stage **não** a muda. Se em algum momento passar a haver
  `.env` nesta worktree (ou se outra worktree paralela estiver de pé), conferir a
  porta antes de rodar — **não presumir 5432 nem presumir o default**.
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
    `ck_employee_shift_preferences_period_known`.
  - **Os valores de `period` são derivados do domínio; os de `workload_kind`
    NÃO têm de onde ser derivados, e por isso nascem aqui — com dono.** A
    distinção é material e foi verificada, não presumida:
    - `period` vem de `DayPeriod`, que é `StrEnum`
      (`morning`/`afternoon`/`night`/`overnight`). Derivar
      (`tuple(p.value for p in DayPeriod)`) é o precedente literal de
      `_ROLE_VALUES`/`_PURPOSE_IN_LIST` no `tables.py` de identity: repetir a
      lista criaria duas fontes que divergem no dia em que um período novo
      entrar, e a divergência só apareceria como `IntegrityError` em produção.
    - `workload_kind` **não tem fonte**: `WorkloadProfile = FixedSchedule | OnDemand`
      é união de dois dataclasses **sem string discriminadora** — medido,
      `grep -rn "on_demand\|\"fixed\"" src/ tests/fakes/` dá **zero
      ocorrências**. Os literais `"fixed"` e `"on_demand"` existem hoje só na
      **prosa** do concept (§9, linha do probe "barra `fixed` sem horas e
      `on_demand` com horas"). Esta Task é onde eles passam a existir em código.
    - **Fonte única, e é `tables.py`:** constantes de módulo **públicas**
      `WORKLOAD_KIND_FIXED = "fixed"`, `WORKLOAD_KIND_ON_DEMAND = "on_demand"` e
      `WORKLOAD_KINDS = (WORKLOAD_KIND_FIXED, WORKLOAD_KIND_ON_DEMAND)`.
      Públicas — sem underscore — porque, ao contrário de `_ROLE_VALUES`, elas
      atravessam módulo: a `CHECK` as consome aqui e o `mappers.py` da Task 03 as
      consome para escolher entre `FixedSchedule` e `OnDemand` nas duas
      direções. Literal de string repetido no mapper é a mesma dívida de duas
      fontes, só que dentro do mesmo pacote.
    - **Isto não é decisão nova de formato persistido** — os dois valores já
      estavam fixados pelo concept §9 e exercitados no probe contra o banco
      real. O que a Task faz é dar-lhes **dono em código** em vez de deixá-los
      escritos à mão em três lugares (`CHECK`, mapper de leitura, mapper de
      escrita). Se algum dia um terceiro perfil entrar em `WorkloadProfile`, o
      lugar de acrescentá-lo é aqui, e a `CHECK` acompanha por construção.
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
  nenhuma FK aponta para tabela fora de `staff_metadata`. Assere também que
  `WORKLOAD_KINDS == ("fixed", "on_demand")` e que os valores de `period` na
  `CHECK` são **exatamente** `tuple(p.value for p in DayPeriod)` — esta segunda
  asserção é a que reprova o dia em que um período novo entrar no enum sem
  entrar no schema, que é o defeito que a derivação existe para impedir.
  **CA20, parte desta Task:** `tables.py` aparece com **≥ 90%** no
  `term-missing` — o `fail_under` do `pyproject.toml` é **global** e não reprova
  arquivo individual (concept CA20).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/adapters/test_tables.py -v
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing | Select-String "staff.*tables"
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
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  uv run alembic upgrade head; uv run alembic downgrade base; uv run alembic upgrade head
  uv run pytest tests/integration -v
  # CA21 — com o banco fora do ar a suíte FALHA (nunca pula, nunca fica verde)
  docker compose stop postgres
  uv run pytest tests/integration
  docker compose start postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  make check
  ```
  > A espera de prontidão **depois** do `start` não é zelo: `docker compose start`
  > retorna assim que o container está rodando, e o Postgres ainda leva alguns
  > segundos para aceitar conexão. Sem ela, o `make check` seguinte falha com a
  > mensagem de "Postgres não está acessível" (`connect_timeout: 5`) e o
  > executor lê "quebrei a Task 02" onde o fato é "não esperei o banco" — falso
  > vermelho é tão caro quanto falso verde, porque manda corrigir o que não está
  > quebrado.
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
  - **O mapper consome `WORKLOAD_KIND_FIXED`/`WORKLOAD_KIND_ON_DEMAND` de
    `tables.py`** (Task 01) nas duas direções — leitura e escrita. Repetir os
    literais `"fixed"`/`"on_demand"` aqui recriaria a segunda fonte que a Task
    01 existe para eliminar, e a divergência só apareceria como violação de
    `ck_employees_workload_kind_known` em produção.
- **Critério de aceite:** CA15b e a metade unitária de CA8b — testes sem banco
  cobrem o round-trip de `JobFunction` e de `Employee` (incluindo `OnDemand` sem
  horas, `shift_preference` ausente e presente, e períodos), a preservação de
  `tzinfo is None`, **cada** entrada de **cada** um dos quatro mapas, e os casos
  não traduzidos. Em especial: um `IntegrityError` cujo `constraint_name` é
  `fk_employee_job_functions_job_function` devolve `JobFunctionNotFoundError` sob
  `ON_WRITE_EMPLOYEE` e `JobFunctionInUseError` sob `ON_DELETE_JOB_FUNCTION` — um
  mapa global não conseguiria as duas.
  **CA20, parte desta Task:** `mappers.py` **e** `integrity_errors.py` aparecem
  com **≥ 90%** cada no `term-missing`, lidos arquivo a arquivo — a média global
  do `fail_under` não substitui (gate míope, concept CA20).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/adapters/ -v
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing | Select-String "staff.*(mappers|integrity_errors)"
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
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
  - **Deadlock por reescrita cega (§5.20) — o terceiro invariante medido.** Um
    `update` que **não** mexe no conjunto de funções, concorrente com um
    `delete_job_function`, **não** levanta `40P01` e **não** é derrubado. É a
    regressão que impede a "simplificação" futura de trocar a escrita por
    diferença por `DELETE`-tudo-`INSERT`-tudo — que passa em **todos** os outros
    testes desta Stage, inclusive nos de lei, porque o estado final é o mesmo.
    - **Cenário:** funcionário `E` com o conjunto `{F1, F2}`. Conexão A executa
      `employees.update(E)` com o **mesmo** conjunto `{F1, F2}`; conexão B
      executa `job_functions.delete(tenant, F2)`.
    - **Por que a reescrita cega deadlockaria:** ao reinserir os vínculos, A
      pega `FOR KEY SHARE` nas linhas de `job_functions` de `F1` e `F2`;
      B já segurava lock exclusivo na linha de `F2` e precisa varrer
      `employee_job_functions` pelo `RESTRICT`. Ordem de lock invertida ⇒
      `40P01`, e `40P01` é `OperationalError`, **não** `IntegrityError` — escapa
      do tradutor e viraria 500 na 3.4. Por diferença, A não toca vínculo nenhum
      e portanto não pega lock nenhum em `job_functions`.
    - **Sincronização nomeada, sem `sleep`:** `threading.Barrier(2)` liberada
      depois que **cada** lado abriu a transação e tomou o seu primeiro lock,
      mais `SET lock_timeout = '2s'` nas **duas** conexões. A barreira dá o
      entrelace determinístico (é a ordem de aquisição, não o relógio, que
      produz o deadlock); o `lock_timeout` converte um bloqueio indefinido em
      falha rápida e legível, em vez de a suíte pendurar.
    - **Asserção:** o `update` de A **completa** — nem `DeadlockDetected`, nem
      `OperationalError`, nem timeout. O que B recebe (`JobFunctionInUseError`,
      pelo `RESTRICT`) é consequência esperada e não é o objeto do teste.
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
- **Critério de aceite:** CA6b, CA8b (metade de integração), CA8c, CA10b, CA17b
  **e a regressão de deadlock da §5.20** — **seis** testes dedicados, cada um
  **reproduzindo** o comportamento e não apenas observando o estado final.
  > **A §5.20 está no critério de propósito, e não só no corpo da Task.** Ela é
  > o terceiro dos três invariantes que o concept mediu, e é o único que **não
  > tem CA numerado no concept §11** — está declarado como invariante (§5.20) e
  > na tabela de findings herdados (linha "3. Concorrência"), não como critério.
  > Um executor que satisfizesse o critério ao pé da letra sem esta linha
  > **pularia** exatamente a regressão que protege a escrita por diferença, que
  > é a peça mais fácil de "simplificar" depois porque nenhum outro teste a
  > distingue. Ver a [§7](#7-execução-post-hoc-editável-após-done) para a razão
  > de fechá-la aqui em vez de regredir o concept para criar um CA novo.
  - **Nenhum dos seis usa `sleep` como sincronização**, e cada um nomeia o seu
    mecanismo: `lock_timeout` curto (CA6b), entrelace forçado por
    `after_cursor_execute` (CA17b), `threading.Barrier(2)` + `lock_timeout`
    (deadlock). Teste de concorrência sincronizado por relógio é teste que passa
    por sorte — e que, quando falha no CI, é lido como flakiness em vez de como
    o achado que é.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
| **3.3.0006** — atomicidade nas duas pontas, sem lock otimista | **07** (transação + `FOR UPDATE` + filhas por diferença + `REPEATABLE READ`), **08** (as provas — CA6b, CA17b **e a regressão de deadlock da §5.20**, esta última sem CA numerado no concept e por isso listada explicitamente no critério da Task 08 e na §3) |
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
do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
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
- [ ] **Regressão de deadlock (§5.20) verde**, com a saída colada: um `update`
      que não mexe no conjunto de funções, concorrente com um
      `delete_job_function`, **não** levanta `40P01`. É o único dos três
      invariantes medidos sem CA numerado no concept §11, e por isso é o que
      some se ninguém o listar aqui.
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

> **Nota sobre as duas entradas abaixo.** Elas nascem na **Fase 3B**, não na
> Fase 4, e isso é deliberado: as duas reconciliam este technical com o
> `concept.md` já `done`, e a §7 é a **única** região que continua editável
> depois de `status: done` (`scripts/check_technical_postexec.py`). Registrá-las
> aqui é o que as mantém legíveis para quem executar e para quem auditar; num
> parágrafo de §1 elas seriam congeladas junto com o resto e sumiriam do lugar
> onde a auditoria olha.

### 2026-08-10 — [decision] CA10b — o normativo é o objeto da asserção, não o mecanismo — Claude

**Contexto:** o concept §11 escreve CA10b parte 1 como "asserção sobre
`str(stmt.compile(dialect=postgresql.dialect()))`". O plano da Task 08 aceita
**também** obter o mesmo texto pelo evento `before_cursor_execute` do `Engine`.
É alargamento do texto **literal** de um critério de aceite de um artefato
`done`, e por isso não passa em silêncio.

**Pergunta:** isto é gap material — que exigiria regredir o concept a `draft`
(CONVENTIONS §3.2) — ou refinamento de detalhe?

**Opções:**
- A — Regredir o concept: `chore(concept): revert to draft — revision-from-technical: …`
  + correção + novo `stage 3.3: conceptual approved`.
- B — Estreitar o plano ao texto literal, exigindo que o adapter exponha os
  statements como builders de módulo só para serem compiláveis pelo teste.
- C — Registrar a reconciliação aqui, mantendo o concept `done`. ✅ recomendada

**Decisão:** C.

**Razão:** o critério de regressão do fluxo é explícito — regride **apenas** o
que muda **contrato**, **fronteira da Stage** ou **critério de aceite**;
"refinamento de detalhe que não muda contrato **NÃO** regride". O que CA10b
normatiza, e a razão inteira de ela existir, é o **objeto** da asserção: a
cláusula `COLLATE "C"` no SQL, **nunca** o resultado — porque nesta imagem
(musl) nenhum resultado distingue a presença da ausência do `COLLATE`. Esse
objeto fica intacto; o que varia é **como** o teste obtém o texto do SQL, que é
mecânica de teste. A alternativa aceita é ainda **mais forte** que a literal:
assere o SQL que o adapter realmente emitiu, não um statement reconstruído pelo
teste. A opção B foi rejeitada porque deixaria a **forma do adapter** ser
ditada por uma escolha de mecanismo de teste — a cauda balançando o cachorro. A
opção A foi rejeitada por custo desproporcional (dois commits reservados + nova
aprovação) e, pior, por precedente: se refinamento de mecanismo de teste
regride o concept, a regressão deixa de sinalizar gap material e vira ruído de
processo. **Limite honesto:** quem ler CA10b no concept e o teste no código verá
mecanismos diferentes; é esta entrada que os concilia, e ela cita "CA10b"
literalmente para ser encontrável por grep.

### 2026-08-10 — [decision] §5.20 entra no critério da Task 08 sem virar CA no concept — Claude

**Contexto:** o concept mediu **três** invariantes de concorrência no probe.
Dois viraram critério numerado — CA6b (o `FOR UPDATE` bloqueia) e CA17b (a
leitura não é rasgada). O terceiro — **deadlock por reescrita cega das
filhas** — ficou declarado como **invariante** (§5.20) e como linha da tabela de
findings herdados ("3. Concorrência"), mas **sem CA numerado** em §11.

**Pergunta:** criar o CA no concept (regressão) ou fechar a lacuna no technical?

**Opções:**
- A — Regredir o concept e acrescentar "CA17c" a §11.
- B — Listar a §5.20 explicitamente no critério de aceite da Task 08 e na §3
  do technical, com o mecanismo de sincronização nomeado. ✅ recomendada

**Decisão:** B.

**Razão:** a §5.20 **já é normativa** no concept — invariante numerada, com a
medição do probe por trás ("`40P01` derruba o `update` legítimo; `40P01` é
`OperationalError`, não `IntegrityError`"). Não falta regra no concept; faltava
**check** no technical, e check é território do technical. O defeito real era
meu: a §1 prometia "os três invariantes ganham Task própria com testes que os
reproduzem" e o critério de aceite da Task 08 listava só cinco itens, todos
CA — um executor literal pularia justamente a regressão que protege a escrita
por diferença, que é a peça mais fácil de "simplificar" depois porque **nenhum
outro teste a distingue** (o estado final é idêntico). Corrigido no lugar certo:
o critério da Task 08 agora nomeia a §5.20 como sexto item, com
`threading.Barrier(2)` + `lock_timeout` como sincronização, e a §3 traz a linha
com exigência de saída colada.

### 2026-08-10 — [decision] Task 03 — `mappers.py` de staff também nasce em inglês — Claude

**Contexto:** o plano e o concept (D4, ADR 3.3.0004) mandam **inglês** apenas
para `integrity_errors.py`, com a razão de que aqueles seis nomes são API de
módulo. Nada foi dito sobre `mappers.py`, e o precedente vizinho — o
`mappers.py` de identity — está inteiro em **português**
(`linha_para_usuario`, `sessao_para_linha`, `_para_utc`).

**Pergunta:** as funções de `mappers.py` de staff nascem em PT (simetria com o
arquivo homólogo de identity) ou em EN (CONVENTIONS §1 + a razão de D4)?

**Opções:**
- A — PT, por simetria com o `mappers.py` de identity, que é o arquivo que
  qualquer leitor vai comparar lado a lado.
- B — EN, aplicando a `mappers.py` a mesma razão que D4 aplica a
  `integrity_errors.py`. ✅ recomendada

**Decisão:** B.

**Razão:** o argumento de D4 não é sobre *aquele* arquivo, é sobre a **classe**:
CONVENTIONS §1 é literal ("todo código-fonte… classes, funções, métodos"), e a
§7 do technical da 3.2 já registrou `[finding]` cuja direção declarada é
"renomear os locais em PT de **todo** o BC staff para inglês". Estes nomes são
API de módulo — os adapters das Tasks 06/07 os importam —, exatamente o critério
que D4 usa para separar "API" de "identificador local". Nascer em PT criaria, no
mesmo commit, dívida que uma varredura já agendada teria de desfazer, e deixaria
o BC staff com dois idiomas em dois arquivos vizinhos do **mesmo** pacote
(`integrity_errors.py` em EN, `mappers.py` em PT), que é pior que qualquer das
duas escolhas consistentes. A opção A foi rejeitada porque a simetria que ela
compra é com o módulo que a própria D4 declara ser **a dívida**, não o padrão.
**Limite honesto:** quem ler os dois `mappers.py` lado a lado verá idiomas
diferentes; a razão está no docstring do módulo de staff e nesta entrada, e a
divergência é a mesma já aceita para `integrity_errors.py`.

### 2026-08-10 — [deviation] os comandos de Alembic da Task 02 e da §3 exigem `-c migrations/alembic.ini` — Claude

**Contexto:** o comando de verificação da Task 02 (linha 390) e o do gate de
saída §3 (linha 1058) estão escritos como
`uv run alembic upgrade head; uv run alembic downgrade base; uv run alembic upgrade head`.
Executados literalmente na raiz do repo, os três **falham**:

```
FAILED: No 'script_location' key found in configuration.
EXIT=255
```

O `alembic.ini` deste projeto não fica na raiz — vive em `migrations/`, e o
`Makefile:74-79` já documenta a consequência (`make migrate` é
`uv run alembic -c migrations/alembic.ini upgrade head`). O comando correto,
verificado nesta execução, é:

```powershell
uv run alembic -c migrations/alembic.ini upgrade head
uv run alembic -c migrations/alembic.ini downgrade base
uv run alembic -c migrations/alembic.ini upgrade head
```

Saída da execução real, na Task 02:
`Running upgrade 0002 -> 0003` → `Running downgrade 0003 -> 0002 … 0001 -> ` →
`Running upgrade -> 0001 … 0002 -> 0003`, `EXIT=0`.

**O que mudou vs. o plano:** nada de implementação — só a **forma de invocar**
o comando de verificação. A migration em si foi exercitada nos dois sentidos, e
continua sendo exercitada a cada sessão de pytest pela fixture `engine`
(`_recriar_schema` faz `downgrade base` + `upgrade head` usando o
`_ALEMBIC_INI` correto), que é o caminho que os testes de CA13 percorrem.

**Por que a correção está aqui e não nas linhas 390/1058:** as duas ficam
**fora** dos marcadores `post-execution`, e o `technical.md` está `status: done`
com a Stage ainda não mergeada. Verificado, não presumido — a edição foi
tentada e recusada:

```
docs\stages\3.3-staff-persistence\technical.md: status=done mas há mudanças
fora dos marcadores post-execution (baseline: 4ed4eb14 `stage technical approved`):
  replace: baseline[1057:1058] (lines 1058-1058) vs current[1057:1058]
2 erro(s) em 1 arquivo(s).  EXIT=1
```

Corrigir ali exigiria regredir o technical a `draft`, o que o critério de
regressão não autoriza: não muda contrato, fronteira nem critério de aceite —
é erro de transcrição de um comando. **Quem for executar o gate de saída da §3
deve usar a forma com `-c` colada acima**, e esta entrada existe para que a
divergência seja encontrável por grep (`script_location`, `-c
migrations/alembic.ini`) em vez de virar um vermelho lido como "quebrei a
migration".

### 2026-08-10 — [deviation] Task 04 — homônimos são irrepresentáveis no port de função — Claude

**Contexto:** o plano da Task 04 e o CA10 (Task 09) exigem dado adversarial com
"**dois homônimos de ids diferentes**" nas **três** listagens
(`list_by_tenant`, `find_all_by_ids`, `list_by_unit`), porque sem eles o
desempate por `id` — o termo que a paginação da 3.4 usa como **cursor** — nunca
é exercitado. O ADR 3.3.0003 repete a exigência em "Implementation notes".

**O que foi encontrado, ao executar:** nas duas listagens de
`JobFunctionRepository` isso é **irrepresentável**. L-JF1 declara unicidade de
nome **por tenant**, imposta pelo fake (`_guard_name`) e, na 3.3, pelo índice
`uq_job_functions_tenant_name`; e as duas listagens são tenant-scoped
(`list_by_tenant(tenant_id)` e `find_all_by_ids(tenant_id, …)`). Não há como
semear dois homônimos alcançáveis pela mesma chamada — a tentativa levanta
`JobFunctionNameAlreadyExistsError`, que é o comportamento correto e já travado
por `test_l_jf1_add_com_nome_ja_usado_no_tenant_e_erro_e_nao_altera_o_registro`.
Medido: o primeiro rascunho da Task 04 seguia o plano ao pé da letra e falhou
exatamente aí.

**O que mudou vs. o plano:** o dado adversarial de
`test_job_function_repository_laws.py` tem nome acentuado, case misto e espaço à
direita, **sem** o par de homônimos. O desempate por `id` continua sendo lei (o
`ORDER BY` leva os dois termos) e é travado nos dois lugares onde **é**
alcançável:

1. **`test_employee_repository_laws.py`** — nome de funcionário **não é único**
   por declaração (concept 3.1 §5.2), então `list_by_unit` recebe `"Ana"` em
   `e2` e `e9` e o teste assere a sequência inteira. É a listagem que a 3.4
   pagina.
2. **CA10b parte 1, Task 08** — a asserção sobre o **SQL compilado**, única
   capaz de reprovar a omissão da cláusula nesta imagem (musl, cuja colação
   default já é byte-order). Vale para as **três** listagens, inclusive as duas
   de função.

**Por que ficou abaixo do threshold de perguntar:** não muda contrato, fronteira
nem critério — a lei é a mesma e continua verificada; o que muda é **por qual
dado** uma de suas metades é alcançada em um dos dois arquivos. A alternativa
seria relaxar L-JF1 no dado de teste, isto é, quebrar uma lei para testar outra.

**Consequência para quem executar a Task 09:** ao reler CA10 ("as três listagens
… com dado adversarial … dois homônimos de ids diferentes"), **não** procurar o
par de homônimos nas duas listagens de função — ele não existe e não pode
existir. A explicação está também no docstring de `_com_funcoes_adversariais`,
mas é esta entrada que a torna encontrável a partir do critério.

### 2026-08-10 — [decision] Task 09 — o critério ganha um teste de que `[postgres]` não é o fake — Claude

**Contexto:** achado do Checkpoint C sobre a fixture `repos` da Task 05,
**reproduzido**: trocando o corpo da fixture por um `return` incondicional do
par in-memory, os testes de lei rodam `[fake]` **e** `[postgres]` — 122
execuções — todos contra o **fake**, e a suíte reporta verde. A guarda que
escrevi (`raise AssertionError` para parâmetro desconhecido) protege contra o
ramo **ausente**, não contra o ramo **errado**.

**Pergunta:** isto é gap material do critério da Task 09, ou basta a revisão?

**Opções:**
- A — Deixar como está: nenhum critério pede a verificação, e "o ramo constrói o
  adapter certo" é evidente na leitura do conftest.
- B — Acrescentar ao critério de aceite da Task 09 um teste que assere que o par
  de `[postgres]` **não** é o par in-memory. ✅ recomendada

**Decisão:** B, a ser implementado na Task 09.

**Razão:** é o risco central desta Stage, e o único que anula o entregável
inteiro em silêncio. A Stage existe para provar `fake ≡ real`; uma fixture que
devolve o fake nos dois ramos transforma a prova em duas execuções da mesma
implementação — e o sintoma é o **melhor** resultado possível (tudo verde, com o
`--collect-only` mostrando `[fake]` e `[postgres]` para cada teste), que é
precisamente por que ninguém investigaria. Nenhum critério de §11 o alcança:
CA1 conta as execuções, CA2 proíbe ramificação **no corpo do teste** e CA3 pede
as leis verdes nos dois params — todos satisfeitos pelo defeito.

**Forma acordada:** um teste **fora** dos dois módulos de lei (para não violar
CA2, que proíbe o corpo de teste de lei conhecer a implementação), asserindo
sobre o par de `[postgres]` que ele não é `InMemory*` — por exemplo, que carrega
um `Engine`. É barato, e é a asserção de **conduta** correspondente ao que a
Task 08 faz pelo `COLLATE`: travar o mecanismo, não só o resultado.

**Onde isto foi registrado:** o critério da Task 09 vive em §2, **fora** dos
marcadores `post-execution`, e o `check_technical_postexec.py` recusa edições
ali enquanto a Stage não mergeou (verificado nesta execução — ver a entrada do
comando de Alembic acima). Esta entrada **é** a extensão do critério; quem
executar a Task 09 deve lê-la junto com o critério de §2.

**Como foi implementado (Task 09, 2026-08-11).** Em
`tests/contract/features/staff/test_no_implementation_branching.py` — módulo
fora das duas suítes de lei, como a decisão previa —, e em **dois** testes, não
um, porque medindo apareceram **duas** formas independentes de falhar:

- `test_o_par_postgres_nao_e_o_par_in_memory` — parametrização indireta força o
  ramo `postgres` e assere o tipo concreto dos dois repositórios. Mata a mutação
  "a fixture devolve o fake nos dois ramos".
- `test_a_suite_de_contrato_roda_sobre_as_duas_implementacoes` — assere que
  `IMPLEMENTACOES` (constante nomeada nova, de onde `params` passa a ser lido)
  contém os dois ids. **É necessário porque o primeiro sozinho não basta:** a
  parametrização indireta força o ramo independentemente do que a fixture
  declare, então com `"postgres"` removido de `IMPLEMENTACOES` aquele teste
  continuaria verde enquanto a suíte inteira voltava a rodar contra uma
  implementação só. Medido por `--collect-only`: a mutação derruba a coleta de
  **126 para 68** testes, e o único vermelho é o próprio guarda (`1 failed, 67
  passed`) — **nenhum** outro teste do repositório reclama. (Uma versão anterior
  desta entrada dizia "126 para 67", confundindo a contagem **coletada** com a
  de **aprovados**; corrigido no commit `[3.3/task-08-fix]` com medição fresca.)

**A lista de "arquivos a modificar" da Task 09 diverge do executado nas duas
pontas** (conferido com `git show --stat` do commit `a7af30f`):

| Arquivo | Plano §2 | Executado |
|---|---|---|
| `conftest.py` | listado | tocado |
| `test_employee_repository_laws.py` | listado | tocado (CA5b) |
| `test_job_function_repository_laws.py` | listado | **não tocado** |
| `test_no_implementation_branching.py` | **não listado** | tocado |

A segunda ponta é esta decisão (o módulo fora das suítes de lei). A primeira é
que o plano previa acréscimos de CA10 nos **dois** módulos de lei, e no de função
não havia o que acrescentar: `test_l_ord_list_by_tenant_ordena_por_nome_byte_a_byte`
e `test_l_ord_find_all_by_ids_ordena_igual_e_nao_herda_a_ordem_do_pedido` já
existiam desde a Task 04, com o dado adversarial, e o que a Task 09 lhes dá é o
segundo parâmetro da fixture — que vem do `conftest.py`, sem tocar o arquivo. O
módulo **é** exercitado contra o Postgres; ele só não precisou de edição.

### 2026-08-11 — [deviation] Task 06 — escrita por um executor e commitada por outro — Claude

**Contexto:** os dois arquivos da Task 06 foram escritos por uma sessão de
execução que foi **interrompida antes do commit**. A sessão seguinte os
encontrou como arquivos não rastreados na worktree, auditou-os contra a Task 06
e o concept, e os commitou **sem alterar uma linha** — a auditoria não encontrou
critério descoberto, resíduo de trabalho interrompido nem código fora do escopo
da Task. O único ponto examinado e descartado foi a formulação do docstring
sobre delegação a privados, corrigida depois pelo Checkpoint C (F2, commit
`[3.3/task-06-fix]`).

**Razão de registrar:** o histórico do git atribui o conteúdo a quem commitou, e
nada mais na Stage documenta a troca de mãos. Não muda contrato, comportamento
nem critério — mas é fato de procedência que a auditoria de saída não teria como
reconstruir a partir dos artefatos, e "quem escreveu não é quem revisou" é
justamente a circunstância em que uma auto-aprovação passaria despercebida. O
Checkpoint C do bloco 3 testou essa hipótese de forma independente (verificou o
SQL emitido, mediu o isolamento contra o banco e conferiu a escrita por
diferença) e ela não se sustentou.

### 2026-08-11 — [finding] Task 07 — o `except IntegrityError` do adapter de funcionário não tem teste que passe por ele — Claude

**Contexto:** a Task 07 fechou com **96%** de cobertura em
`employee_repository.py` (critério: ≥ 90%). As linhas descobertas, medidas, são
**143, 159 e 539–541**:

| Linha | O que é |
|---|---|
| 143 | `raise translate(…)` de `add` |
| 159 | `raise translate(…)` de `update` |
| 539 | `if constraint_name(erro) == "fk_employee_job_functions_job_function"` |
| 540 | `return str(sorted(employee.job_function_ids))` — o ramo do **conjunto** |
| 541 | `return employee.id` — o ramo do **id** |

Ou seja: `_detalhe_do_conflito` está descoberto **por inteiro**, os **dois**
ramos. (Uma versão anterior desta entrada dizia "o ramo que escolhe o conjunto
em vez do id", o que fazia crer que o outro estava coberto — corrigido pelo
Checkpoint C do bloco 3, que mediu as linhas.)

Não é descuido de suíte — é consequência de o adapter estar **certo**. As
guardas explícitas (`_guard_id_livre` para L-E1, `_guard_job_functions` para
L-E4) respondem antes de qualquer constraint ser alcançada, e as constraints que
sobram (`pk_employees`, `uq_employees_id_tenant`,
`fk_employee_job_functions_job_function`) só são atingíveis quando o estado muda
**entre** a guarda e a escrita — isto é, sob concorrência. Um teste sequencial
não tem como chegar lá; e um adapter que **removesse** as guardas passaria em
todos os testes de lei da Task 07, respondendo os mesmos erros pela via do
tradutor.

**Direção sugerida:** a Task 08 já leva CA8b e CA8c, que exercitam
`ON_WRITE_EMPLOYEE` e as duas formas de mensagem. Mas o texto de CA8b as
descreve chamando `translate(erro, ON_WRITE_EMPLOYEE, …)` sobre uma
`IntegrityError` obtida do Postgres — **fora** do adapter. Satisfeito ao pé da
letra, ele deixa o `except` de `add`/`update` e o `_detalhe_do_conflito` inteiro
sem nenhum teste que passe por eles. Quem executar a Task 08 deve fazer os
testes entrarem pelo **método público** (`repositorio.add(...)` /
`repositorio.update(...)`), forçando o entrelace com o mesmo mecanismo já
previsto ali para CA17b (`after_cursor_execute` entre a pré-checagem e a
escrita, mudando o estado no meio). É a corrida real, é o único caminho que
prova que a cadeia guarda → tradução → erro tipado está ligada de ponta a ponta,
e é o que impede que a 3.4 receba um `IntegrityError` cru onde o contrato
promete erro tipado.

**Aritmética do que fecha o quê** — importa porque **um** teste não basta:

- `add` com corrida na **FK** (`fk_employee_job_functions_job_function`) fecha
  143, 539 e 540 — e deixa **159 e 541** abertos.
- `add` com corrida na **identidade** (`pk_employees` / `uq_employees_id_tenant`
  — outra transação insere o mesmo id entre `_guard_id_livre` e o `INSERT`)
  fecha 143, 539 e **541**.
- `update` com corrida na **FK** fecha **159**, 539 e 540. (`update` não escreve
  `id` nem `tenant_id`, então a identidade não é alcançável por ele; 541 só vem
  pelo `add`.)

**Duas** corridas zeram o arquivo: `add` na identidade + `update` na FK. É
também a combinação que exercita as **duas** entradas de `ON_WRITE_EMPLOYEE` com
significados diferentes, que é a razão de o mapa ser por operação.

**Stage candidata:** esta mesma (Task 08). Não é dívida para depois — é uma
linha a mais no escopo já planejado da Task seguinte.

**Fechado na Task 08 (2026-08-11).** As duas corridas previstas na aritmética
acima entraram como testes que passam pelo **método público**:
`test_ca8c_o_backstop_de_l_e4_responde_pelo_metodo_publico_e_cita_o_conjunto`
(`update`, corrida na FK) e
`test_o_backstop_de_identidade_responde_pelo_metodo_publico_e_cita_a_id`
(`add`, corrida na identidade). `employee_repository.py` foi de **96% para
100%** — as linhas 143, 159 e 539–541 estão cobertas. E a mutação que troca
`ON_WRITE_EMPLOYEE` por um mapa global, que sobrevivia às Tasks 06/07 inteiras,
agora reprova (ver a tabela mutação→resultado no corpo do commit da Task 08).

### 2026-08-11 — [deviation] Task 08 — a §5.20 ganha um segundo teste, determinístico e sobre a pegada de lock — Claude

> **Esta entrada foi reescrita em 2026-08-11 (commit `[3.3/task-08-fix]`) porque
> a versão original afirmava um resultado de medição que é falso.** Ela dizia que
> o teste prescrito, sob o mutante, "**passou** — 11/11 na suíte de conduta", e
> concluía que não havia ancoragem de barreira capaz de matá-lo. As duas coisas
> estão erradas, e o erro tem causa identificável: a medição foi feita com o
> gatilho da barreira **antigo** (`"FOR UPDATE"`), o gatilho foi então reancorado
> em `"FROM employee_job_functions"`, e a conclusão antiga foi gravada sem
> **remedir**. O próprio commit da Task 08 já se contradizia — a tabela do corpo
> registrava "as duas regressões reprovam" enquanto o docstring dizia o oposto.
> É o padrão "não afirmar conformidade sem verificar", desta vez sobre uma
> medição própria e não sobre um arquivo alheio. Apontado pelo Checkpoint C.

**Contexto:** o plano prescreve, para a regressão da §5.20, `threading.Barrier(2)`
+ `lock_timeout` nas duas conexões, com a asserção "o `update` de A **completa**".
Implementado assim, e medido por mutação em duas variantes da reescrita cega
(uma que mantém a leitura dos vínculos e zera a diferença; outra que apaga tudo e
reinsere sem ler), com o gatilho de barreira que está no artefato:

| | contra os mutantes | limpo |
|---|---|---|
| teste prescrito (deadlock) | **154 de 160** reprovam (~96%) | 25/25 passam |
| teste acrescentado (pegada de lock) | **50 de 50** reprovam | 25/25 passam |
| suíte de conduta inteira | 2 failed, 9 passed (nas duas variantes) | 11 passed (×9) |

**O teste prescrito mata o mutante.** A conclusão original estava errada.

**O que continua verdade, e é o motivo do teste adicional.** Duas coisas:

1. **O critério literal do plano não é o que mata.** Das 154 reprovações,
   **todas** caem na asserção sobre B, nenhuma em A (classificado pelo número de
   linha do `AssertionError`, não por texto). Logo `resultados["a"] is None` — a
   asserção que o plano nomeia — **passa** sob o mutante: o deadlock elege B como
   vítima. Quem reprova é B voltar `40P01 DeadlockDetected` no lugar do
   `JobFunctionInUseError`, e o plano descreve exatamente essa asserção como
   "consequência esperada e não é o objeto do teste". Um enxugamento futuro
   apagaria a linha **com autoridade do plano** e deixaria o teste decorativo. A
   linha está marcada como load-bearing no código.
2. **O teste prescrito tem cauda de escalonamento; o outro não.** As 6
   sobreviventes em 160 são o caso em que B completa a varredura do `RESTRICT`
   antes de A tomar os locks das linhas de vínculo: sem inversão, sem deadlock.
   Não é ajustável por sincronização — a barreira já está no ponto certo —,
   porque o **sintoma** depende de escalonamento. A **causa** não: a reescrita
   cega toma `FOR KEY SHARE` em `job_functions` num `update` que não mexeu no
   conjunto, sempre. Daí o segundo teste medir a causa: 50/50, sem cauda.

**O que foi feito:** o teste prescrito **permanece**, e entrou ao lado dele
`test_regressao_5_20_update_sem_mudanca_no_conjunto_nao_segura_lock_em_job_functions`,
que mede a causa. Com a transação do `update` aberta e não commitada (entrelace
no seu último statement), outra conexão tenta remover a função:

- por diferença ⇒ `JobFunctionInUseError` (`23503`), a resposta de negócio do
  `RESTRICT`;
- por reescrita cega ⇒ bloqueio no lock indevido e `lock_timeout` (`55P03`), um
  `OperationalError` que escapa do tradutor e vira 500 na 3.4.

Sem thread, sem barreira e sem relógio — um evento entre statements.

**Razão de ficar abaixo do threshold de perguntar:** não muda contrato, critério
de aceite nem escopo — é um teste **a mais** sobre a mesma invariante, não a
troca de um instrumento por outro. A §5.20 continua travada pelo teste que o
plano prescreve, na forma que o plano prescreve.

### 2026-08-11 — [finding] fake ≢ real fora do alcance do contrato: nome com byte NUL — Claude

**Contexto:** achado pela auditoria de testes independente e reproduzido aqui. Um
nome de função contendo `\x00` é **aceito pelo fake** e **recusado no caminho do
Postgres**. Medido nesta worktree, com o mesmo `JobFunction` pelos dois
repositórios:

| Entrada | fake | Postgres |
|---|---|---|
| `"a\x00b"` | grava verbatim | `sqlalchemy.exc.DataError` |
| aspas, acento, emoji com ZWJ, `\n`, 1000 caracteres | grava verbatim | grava verbatim |

**Só o NUL diverge** — o resto do dado adversarial faz round-trip perfeito nos
dois lados, o que é um resultado positivo para a disciplina verbatim.

**Uma precisão em relação ao relatório da auditoria:** ela registra `sqlstate`
`22021`. Medido aqui, o `sqlstate` é **`None`**, e a mensagem é `psycopg.DataError:
PostgreSQL text fields cannot contain NUL (0x00) bytes`. A diferença importa: a
recusa é do **driver, client-side**, antes de o statement chegar ao servidor —
não há código de erro de servidor para mapear, e `constraint_name` também é
`None`. Qualquer tratamento futuro tem de casar por **tipo de exceção**, não por
sqlstate.

**Por que escapa de tudo que esta Stage construiu:** `DataError` não é
`IntegrityError`, então `translate` nunca é chamado e o erro sobe cru. E a lista
de "erros que sobem crus" do concept §6 nomeia só `40P01` e `40001` — este não
está lá. O contrato também não o alcança: a suíte de lei não exercita nome com
NUL, e se exercitasse **reprovaria em `[postgres]`**, porque a divergência é real.

**Direção sugerida**, em ordem de preferência:

1. **Rejeitar no domínio.** `JobFunction`/`Employee` já recusam nome vazio; um
   nome com caractere de controle é igualmente indefensável como dado de
   negócio, e recusá-lo em `__post_init__` faz o fake e o real concordarem **por
   construção** — que é o único conserto que fecha a divergência em vez de
   documentá-la. Custo: é mudança de domínio (3.1), não de persistência.
2. Mapear `DataError` para erro tipado na borda HTTP, junto de `40P01`/`40001`.
   Fecha o 500, mas mantém fake e real discordando sobre o que é gravável.

**Stage candidata:** `3.4-staff-http` — é lá que hoje isto viraria **500**, e é
lá que o mapeamento dos outros erros crus já está escalado. Se a opção 1 for a
escolhida, ela precede e torna a 2 desnecessária.

### 2026-08-11 — [finding] o escopo de CA17 é notação posicional, não round-trip verbatim de `Decimal` — Claude

**Contexto:** a auditoria observou que `Decimal("1E+2")` volta do banco como
`Decimal("100")` — valor igual, **representação** diferente. Não é gap: CA17 foi
escrito de propósito sobre **notação posicional** (`22.50` volta `22.50`, valor e
escala), porque é ali que a perda silenciosa acontece — uma `NUMERIC(5,2)`
arredondaria `22.555` e `0.001`, e a igualdade de `Decimal` não pegaria a
mudança de escala.

**Registrado para que ninguém leia CA17 como garantia maior do que é.** O que a
Stage garante é que valor e escala sobrevivem ao round-trip em notação
posicional; **não** que a representação exponencial sobreviva como tal. O
Postgres normaliza `1E+2` para `100` na coluna `NUMERIC`, e as duas são o mesmo
número — `FixedSchedule` aceita qualquer `Decimal` finito positivo e não atribui
significado à forma. Sem ação nesta Stage; a nota existe para o dia em que
alguém escrever um teste esperando `str(...) == "1E+2"` e concluir que o mapper
está errado.

<!-- END: post-execution -->

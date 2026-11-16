---
title: Technical — Persistência da escala
description: Plano de execução da Stage 4.4 — leis refinadas, esquema, migration, mappers, os dois repositórios Postgres de scheduling, a fachada de leitura de staff, o adapter do StaffReadPort, as suítes de contrato contra o real e o wiring
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem arquivos, critério de aceite e comando de verificação
keywords: [technical, plano de execução, scheduling-persistence, postgres, migration, contrato, trilha, fachada]
status: done
created_at: 2026-11-16
updated_at: 2026-11-16
stage_id: 4.4-scheduling-persistence
stage_title: Persistência da escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.3-scheduling-application]
concept_ref: ./concept.md
issue_id: 189
branch: feat/189-4-4-scheduling-persistence
tasks_count: 11
---

# Technical — Stage 4.4 — Persistência da escala

> **Como usar:** ler §1, executar as Tasks de §2 em ordem (1 Task = 1 commit, marca
> `[4.4/task-NN]`), validar §3 ao final. Algo não previsto em §1–§6 ou no
> [`concept.md`](./concept.md) vai para a §7.

## 1. Contexto e estratégia de execução

### Resumo

Os três ports de dados da 4.3 ganham adapter real: `ScheduleRepository` e
`ScheduleConfigRepository` em Postgres (SQLAlchemy Core) e `StaffReadPort` sobre uma fachada de
leitura de staff. As suítes de lei passam a rodar contra `fake` e `postgres`, e o composition
root monta os três.

### Estratégia

Ordem de **Stage só de adapter sobre BC consolidado** (skill `task-ordering-hex`, exceção
"adapter-only": contrato sobre o port existente → adapter → wiring), precedida pelo acerto das
leis:

1. **Leis primeiro** (Task 01): o texto do port, o fake e a suíte ficam do jeito que o adapter
   vai ter de cumprir. Roda inteira sem banco.
2. **Esquema antes da migration, migration antes dos repositórios** (Tasks 02–03).
3. **Mappers e tradutor puros** (Task 04), testáveis sem banco.
4. **Repositórios**, cada um já entrando na parametrização do contrato (Tasks 05–07).
5. **Lado de staff**: fachada (Task 08), depois o adapter com a aresta (Task 09).
6. **Wiring e o fluxo ponta a ponta** (Task 10). **Documentação** (Task 11).

**Onde cada coisa roda** (orquestração autônoma, ADR 0.0.0008): localmente, só o que não toca
banco — `ruff check`, `ruff format --check` (em toda Task, mesmo onde o comando da Task não
o repete), `mypy`, `check_layout`, `lint-imports`, os scripts do `docs-check` e
`pytest -k "not postgres"` nas pastas de unit e de contrato. Integração, contrato `[postgres]` e
o `make check` completo rodam no GitHub Actions do PR, aberto em draft no primeiro push e
empurrado a cada Task. Uma Task com teste de banco só é dada por verde com o run do Actions do
commit dela.

### Pré-condições

- `4.3-scheduling-application` `done` e mergeada (`check_stage_deps` verde).
- Concept desta Stage `done`; ADRs 4.4.0001 a 4.4.0004 `accepted`.

### Premissas técnicas

- PostgreSQL 16 no CI (`postgres:16-alpine`); SQLAlchemy 2.0.51, Alembic 1.18.5, psycopg 3.3.4.
- O schema de teste vem da migration (`tests/conftest.py` › `_recriar_schema`), então a
  extensão `btree_gist` criada por ela vale para a suíte.
- `develop` termina na migration `0004`; a `0005` é da Stage 3.11 (PR #188).

### Varreduras de totalidade que esta Stage dispara

| Varredura | O que cobra | Task que leva a entrada |
|---|---|---|
| `tests/unit/features/scheduling/test_bc_independence.py` | nenhum módulo de scheduling importa vizinho; nenhum `ignore_imports` toca scheduling | 09 (passa a "exatamente o gateway, só a fachada") |
| `tests/unit/features/staff/test_bc_independence.py` | lista exata de pares do `bc-independence` | 09 |
| `.importlinter` › `unmatched_ignore_imports_alerting = error` | par sem import correspondente é erro | 09 (par, adapter e testes no mesmo commit) |
| `scripts/check_layout.py` regra 9 | `__init__.py` só com docstring | 02, 09 (pacotes novos vazios) |
| `scripts/check_layout.py` regra 6 | composition root só com dataclass e as duas funções | 10 (só campos e instâncias) |
| `tests/unit/features/*/adapters/test_composition_root_*.py` | só o composition root importa adapters de cada BC | 10 (o de scheduling nasce) |
| `tests/conftest.py` › `TABELAS_EM_ORDEM_DE_LIMPEZA` | fonte única da limpeza | 03 |
| `tests/integration/test_migration.py` | tabelas criadas; `downgrade` | 03 |
| `scripts/check_doc_frontmatter.py` regra 8 | lacunas × Stage `done` | commit `stage 4.4: complete` (doc de domínio e roadmap juntos) |

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                  (modificado)
└── features/
    ├── scheduling/
    │   ├── application/ports/out/schedule_repository.py (docstring)
    │   └── adapters/out/
    │       ├── __init__.py
    │       ├── postgres/{__init__,tables,mappers,integrity_errors,
    │       │             schedule_repository,schedule_config_repository}.py
    │       └── staff/{__init__,local_staff_read_adapter}.py
    └── staff/application/facade.py
migrations/{env.py, versions/0006_scheduling.py}
tests/
├── conftest.py                                           (lista de limpeza)
├── fakes/features/scheduling/in_memory_schedule_repository.py (alinhado)
├── contract/features/scheduling/{conftest,support,test_schedule_repository_laws,
│                                 test_no_implementation_branching}.py
├── unit/features/scheduling/adapters/{__init__,test_tables,test_mappers,test_integrity_errors,
│                                      test_local_staff_read_adapter,
│                                      test_composition_root_scheduling}.py
├── unit/features/staff/application/test_facade.py
├── unit/features/{staff,scheduling}/test_bc_independence.py (modificados)
└── integration/
    ├── test_migration.py                                 (modificado)
    └── features/scheduling/adapters/out/postgres/{test_schema,test_schedule_config_repository,
        test_schedule_repository,test_schedule_conduct,test_scheduling_flow}.py
```

## 2. Tasks

### Task 01 — leis refinadas: port, fake e suíte

- **Arquivos a criar:** `tests/contract/features/scheduling/support.py`
- **Arquivos a modificar:**
  `src/restaurant_hub/features/scheduling/application/ports/out/schedule_repository.py`
  (docstring), `tests/fakes/features/scheduling/in_memory_schedule_repository.py`,
  `tests/contract/features/scheduling/test_schedule_repository_laws.py`,
  `tests/contract/features/scheduling/conftest.py`
- **O que fazer:** escrever no docstring do port as leis refinadas do concept §4 (ordem do
  `add`; id interno no `add`; relato canônico do id; período e calendário da criação;
  `occurred_at` aware). Alinhar o fake: relato do id por tipo (faixa → demanda → alocação) e
  menor id por codepoint entre todas as outras escalas da unidade. Na suíte: `_QUANDO` aware em
  UTC e os casos de CA01 (a) a (d). `support.py` traz a projeção do agregado em primitivos
  (`project(schedule)`), usada pela suíte e pela integração. No conftest, `staff_member` ganha
  o parâmetro de função e `dani` (tenant `t2`) passa a deter `garcom`.
- **Detalhes técnicos:** nenhuma assinatura muda. A projeção devolve só tipos primitivos e
  tuplas, nos três níveis, na ordem das tuplas do agregado.
- **Critério de aceite:** CA01 (a)–(d) verdes contra o fake; toda a suíte de unit e de contrato
  de scheduling continua verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/scheduling tests/unit/features/scheduling -q
  uv run mypy src/ tests/fakes/ && uv run ruff check src/ tests/ && uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(scheduling): leis refinadas do ScheduleRepository no port, no fake e na suíte [4.4/task-01]`

---

### Task 02 — esquema do BC scheduling em SQLAlchemy Core

- **Arquivos a criar:** `src/restaurant_hub/features/scheduling/adapters/out/__init__.py`,
  `.../adapters/out/postgres/__init__.py`, `.../adapters/out/postgres/tables.py`,
  `tests/unit/features/scheduling/adapters/__init__.py`,
  `tests/unit/features/scheduling/adapters/test_tables.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `scheduling_metadata` e as seis tabelas do concept §9, com toda constraint
  nomeada (`pk_`, `uq_`, `fk_`, `ck_`, `ex_`, `ix_`). Listas das `CHECK` derivadas dos enums do
  domínio (`Weekday`, `EnforcementMode`, `WorkloadDirection`). A exclusion constraint com
  `func.daterange(first_day, first_day + days)`.
- **Detalhes técnicos:** nomes das colunas de política de `scheduling_settings` derivados dos
  campos `PolicyRule` de `ValidationConfig` (`<campo>_enabled`, `<campo>_mode`), expostos por
  uma constante do módulo que o mapper reusa.
- **Critério de aceite:** CA08 — seis tabelas; toda constraint nomeada; tipos de §5.12; nenhuma
  FK para fora do metadata; o DDL da exclusion constraint compilado com `postgresql.dialect()`
  é o SQL de D-DISJOINT; `scheduling_settings` toda `NOT NULL`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/adapters/test_tables.py -q
  uv run mypy src/ && uv run ruff check src/ tests/ && uv run python scripts/check_layout.py && uv run lint-imports
  ```
- **Commit sugerido:** `feat(scheduling): esquema Postgres da escala, da trilha e da configuração [4.4/task-02]`

---

### Task 03 — migration `0006_scheduling`, metadata combinado e schema migrado

- **Arquivos a criar:** `migrations/versions/0006_scheduling.py`,
  `tests/integration/features/scheduling/__init__.py` e os `__init__.py` até
  `adapters/out/postgres/`, `tests/integration/features/scheduling/adapters/out/postgres/test_schema.py`
- **Arquivos a modificar:** `migrations/env.py`, `tests/conftest.py`,
  `tests/integration/test_migration.py`
- **O que fazer:** migration escrita à mão (`revision` `"0006"`, `down_revision` `"0004"`):
  `CREATE EXTENSION IF NOT EXISTS btree_gist`, as seis tabelas, o índice. `downgrade` remove as
  tabelas, não a extensão. `env.py` soma `scheduling_metadata`. A lista de limpeza ganha as
  seis tabelas. `test_migration.py`: as seis tabelas e a extensão (`pg_extension`) existem
  depois do `upgrade`; o `downgrade` até `"0004"` remove as seis, deixa as de staff e **deixa
  a extensão**. `test_schema.py`: CA09 (garantias por `INSERT` direto e bordas de
  cada `CHECK`) e CA10 (nomes de constraint e índice do banco = os de `tables.py`).
- **Detalhes técnicos:** **mais de 5 arquivos por causa dos `__init__.py` de pacote de teste**;
  é uma mudança só. Os testes de banco só rodam no Actions.
- **Critério de aceite:** CA09, CA10; a suíte inteira continua verde no Actions (a fixture
  `engine` recria o schema com a migration nova).
- **Comando de verificação:**
  ```bash
  uv run alembic -c migrations/alembic.ini upgrade 0004:0006 --sql   # DDL offline, sem banco
  uv run ruff check migrations/ tests/ && uv run mypy src/
  # Actions: tests/integration/test_migration.py e .../scheduling/.../test_schema.py
  ```
- **Commit sugerido:** `feat(scheduling): migration 0006 com as tabelas de scheduling [4.4/task-03]`

---

### Task 04 — mappers puros, codec da trilha e tradutor de integridade

- **Arquivos a criar:** `.../adapters/out/postgres/mappers.py`,
  `.../adapters/out/postgres/integrity_errors.py`,
  `tests/unit/features/scheduling/adapters/test_mappers.py`,
  `tests/unit/features/scheduling/adapters/test_integrity_errors.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** funções puras: agregado → linhas (raiz, faixas, demandas, alocações, com
  `position`); linhas → agregado (pelos construtores); linha → `SchedulingSettings`;
  `ScheduleChange` + escala → linha da trilha; linha da trilha → `ScheduleChange`. Formato JSON
  do concept §5.6, com a regra da marca `function_exception`. `integrity_errors.py`:
  `constraint_name`, `translate` e o mapa `ON_ADD_SCHEDULE`, com **duas** entradas:
  `pk_schedules` → `IdentifierInUseError("ScheduleId", …)` e
  `ex_schedules_unit_days_disjoint` → `SchedulePeriodTakenError`. A âncora
  `uq_schedules_tenant_unit_id` fica fora: a PK responde antes dela pela mesma colisão.
- **Critério de aceite:** CA05 (a)–(c); CA12 (metade unit: round-trip por projeção e linha
  corrompida que levanta); CA13 (metade unit: um caso por política, limites distintos); CA07
  (metade unit: o mapa do `add` traduz as duas e só elas; o resto sobe intacto).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/adapters -q
  uv run mypy src/ && uv run ruff check src/ tests/ && uv run python scripts/check_layout.py && uv run lint-imports
  ```
- **Commit sugerido:** `feat(scheduling): mappers, codec da trilha e tradutor de integridade [4.4/task-04]`

---

### Task 05 — `PostgresScheduleConfigRepository` e o contrato de L-CF1

- **Arquivos a criar:** `.../adapters/out/postgres/schedule_config_repository.py`,
  `tests/integration/features/scheduling/adapters/out/postgres/test_schedule_config_repository.py`,
  `tests/contract/features/scheduling/test_no_implementation_branching.py`
- **Arquivos a modificar:** `tests/contract/features/scheduling/conftest.py`,
  `tests/contract/features/scheduling/support.py`
- **O que fazer:** `find_settings(tenant_id)`: um `SELECT` pela PK, reidratação pelo mapper.
  No conftest, **uma tupla de implementações por fixture** (`CONFIG_IMPLEMENTATIONS`,
  `SCHEDULE_IMPLEMENTATIONS`, `STAFF_READ_IMPLEMENTATIONS`); nesta Task só a de `config_world`
  ganha `"postgres"` (trunca, semeia a linha por `support.seed_settings`). A guarda AST nasce
  aqui, na forma da de staff: módulo de lei → fixture; todo teste recebe a fixture; nenhum
  corpo inspeciona a implementação; a lista de módulos cobre a pasta; e, para cada fixture
  **já promovida**, a tupla é `{"fake", "postgres"}` e o ramo `postgres` entrega o adapter
  concreto. As Tasks 06 e 09 promovem as outras duas e acrescentam o seu caso.
- **Critério de aceite:** CA02; CA04 (para `config_world`); CA13 (metade integração: linha não-default lida campo a campo;
  tenant sem linha; corte com segundos levanta a exceção de domínio).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/scheduling -q -k "not postgres"
  uv run mypy src/ && uv run ruff check src/ tests/ && uv run python scripts/check_layout.py && uv run lint-imports
  # Actions: contrato [postgres] de L-CF1 e a integração do repositório
  ```
- **Commit sugerido:** `feat(scheduling): repositório Postgres da configuração de escala [4.4/task-05]`

---

### Task 06 — `PostgresScheduleRepository` e o contrato de L-SC1 a L-SC8

- **Arquivos a criar:** `.../adapters/out/postgres/schedule_repository.py`,
  `tests/integration/features/scheduling/adapters/out/postgres/test_schedule_repository.py`,
  `tests/unit/features/scheduling/adapters/test_schedule_repository_static.py`
- **Arquivos a modificar:** `tests/contract/features/scheduling/conftest.py`,
  `tests/contract/features/scheduling/support.py`,
  `tests/contract/features/scheduling/test_no_implementation_branching.py`
- **O que fazer:** o protocolo de escrita do concept §5.2–§5.5 (lock da unidade, checagens na
  ordem da lei, raiz, reescrita das filhas, linha da trilha) e as três leituras em snapshot
  único. Ramo `postgres` de `schedule_repo` e de `trail_of` (`support.read_trail`), e o caso de
  `schedule_repo` na guarda AST. `test_schedule_repository_static.py` (sem banco): o módulo do
  repositório não tem `UPDATE` nem `DELETE` sobre `schedule_changes`, e os statements das
  checagens compilam para o dialeto Postgres.
- **Detalhes técnicos:** a chave do lock sai de uma função do módulo, usada por `add` e `save`.
  O menor id em conflito é calculado em Python sobre os ids devolvidos pela consulta.
- **Critério de aceite:** CA01, CA04 (para `schedule_repo`); CA05 (integração: uma linha por
  escrita, `seq` 1, 2, 3); CA06 (recusas não gravam; falha no `INSERT` da trilha desfaz `add` e
  `save`; varredura estática); CA12 (integração).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/scheduling tests/unit/features/scheduling -q -k "not postgres"
  uv run mypy src/ && uv run ruff check src/ tests/ && uv run python scripts/check_layout.py && uv run lint-imports
  # Actions: contrato [postgres] de L-SC e a integração do repositório
  ```
- **Commit sugerido:** `feat(scheduling): repositório Postgres da escala com a trilha na mesma transação [4.4/task-06]`

---

### Task 07 — conduta: concorrência e snapshot único

- **Arquivos a criar:**
  `tests/integration/features/scheduling/adapters/out/postgres/test_schedule_conduct.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** os quatro cenários de CA07 com intercalação determinística (gancho de
  evento do SQLAlchemy que para o escritor A depois de um comando escolhido; consulta a
  `pg_locks` até B aparecer esperando; liberação) e CA11 nas três leituras (gancho que comita
  um `save` por outra conexão entre o `SELECT` da raiz e o das filhas).
- **Detalhes técnicos:** threads com `Event` e tempo-limite; o teste falha, em vez de travar,
  se B não aparecer esperando.
- **Critério de aceite:** CA07, CA11 verdes no Actions.
- **Comando de verificação:**
  ```bash
  uv run ruff check tests/ && uv run mypy src/
  # Actions: .../test_schedule_conduct.py
  ```
- **Commit sugerido:** `test(scheduling): conduta concorrente e snapshot único do repositório de escala [4.4/task-07]`

---

### Task 08 — fachada de leitura de staff

- **Arquivos a criar:** `src/restaurant_hub/features/staff/application/facade.py`,
  `tests/unit/features/staff/application/test_facade.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `StaffRecord`, `StaffFunction` e `StaffReadFacade` (concept §4), sobre
  `EmployeeRepository.list_by_unit` e `JobFunctionRepository.list_by_tenant`.
- **Critério de aceite:** CA14.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff -q
  uv run mypy src/ && uv run ruff check src/ tests/ && uv run python scripts/check_layout.py && uv run lint-imports
  ```
- **Commit sugerido:** `feat(staff): fachada de leitura de staff para outros bounded contexts [4.4/task-08]`

---

### Task 09 — `LocalStaffReadAdapter`, a aresta scheduling → staff e o contrato de L-ST

- **Arquivos a criar:** `.../scheduling/adapters/out/staff/__init__.py`,
  `.../scheduling/adapters/out/staff/local_staff_read_adapter.py`,
  `tests/unit/features/scheduling/adapters/test_local_staff_read_adapter.py`
- **Arquivos a modificar:** `.importlinter`,
  `tests/unit/features/staff/test_bc_independence.py`,
  `tests/unit/features/scheduling/test_bc_independence.py`,
  `tests/contract/features/scheduling/conftest.py`,
  `tests/contract/features/scheduling/test_no_implementation_branching.py`
- **O que fazer:** o adapter traduz `StaffRecord`/`StaffFunction` para
  `StaffMember`/`JobFunctionEntry`. Segundo par no `bc-independence`. Os dois testes de
  independência passam a asserir a lista exata dos dois pares e a forma da aresta de scheduling
  (só `adapters/out/staff/` importa staff, e só a fachada). Ramo `postgres` da fixture `mundo`:
  repositórios Postgres de staff semeados pelos ports (função → registro → vínculo de login →
  desligamento), fachada, adapter; e o caso de `mundo` na guarda AST (o ramo `postgres` entrega
  um `LocalStaffReadAdapter`).
- **Detalhes técnicos:** par, adapter e testes no mesmo commit
  (`unmatched_ignore_imports_alerting = error`). **Mais de 5 arquivos**: é a mesma mudança
  propagada às duas varreduras.
- **Critério de aceite:** CA03, CA04 (para `mundo`), CA15.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling tests/unit/features/staff tests/contract/features/scheduling -q -k "not postgres"
  uv run lint-imports && uv run python scripts/check_layout.py && uv run mypy src/ && uv run ruff check src/ tests/
  # Actions: contrato [postgres] de L-ST
  ```
- **Commit sugerido:** `feat(scheduling): adapter local do StaffReadPort sobre a fachada de staff [4.4/task-09]`

---

### Task 10 — wiring no composition root e o fluxo sobre os adapters reais

- **Arquivos a criar:**
  `tests/unit/features/scheduling/adapters/test_composition_root_scheduling.py`,
  `tests/integration/features/scheduling/adapters/out/postgres/test_scheduling_flow.py`
- **Arquivos a modificar:** `src/restaurant_hub/composition_root.py`, `docs/LAYOUT.md`
- **O que fazer:** montar os dois repositórios de scheduling sobre o `engine`, a
  `StaffReadFacade` sobre `staff_employees`/`staff_job_functions` e o `LocalStaffReadAdapter`;
  três campos no contêiner, com o comentário de bloco que os declara provisórios. Nota datada
  em LAYOUT §6, que `test_composition_root_scheduling.py` confere (os três nomes de campo
  aparecem na seção). O teste de fluxo monta os use cases da 4.3 com o guard fake sobre os
  adapters reais.
- **Detalhes técnicos:** a mudança no composition root fica num bloco próprio (imports, campos,
  montagem), para não cruzar com a Stage 2.7.
- **Critério de aceite:** CA16, CA17, CA19 (a nota do LAYOUT §6).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit -q -k "composition_root or bootstrap"
  uv run python scripts/check_layout.py && uv run lint-imports && uv run mypy src/ && uv run ruff check src/ tests/
  uv run python scripts/check_docs_claims.py
  # Actions: .../test_scheduling_flow.py
  ```
- **Commit sugerido:** `feat(scheduling): wiring dos adapters de scheduling no composition root [4.4/task-10]`

---

### Task 11 — documentação: erratas, issues no roadmap e nota de herança

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:** `docs/adr/4_1_0006-*.md`, `docs/adr/4_3_0003-*.md`,
  `docs/adr/3_5_0004-*.md` (banner de errata), `docs/roadmap.md` (linhas das issues #194, #198
  e #199 na Tabela de Issues; nota de fechamento no bloco 4.4 com o que a 4.5 herda)
- **O que fazer:** erratas datadas apontando para o ADR 4.4.0004 e a issue #194. A marca
  canônica das lacunas no doc de domínio e o `done` do roadmap **não** entram aqui: vão juntos
  no commit `stage 4.4: complete`, porque o gate de lacunas cobra os dois sentidos.
- **Critério de aceite:** CA19 (a parte que não depende do `done`).
- **Comando de verificação:**
  ```bash
  uv run python scripts/check_adr_code_citations.py && uv run python scripts/check_doc_frontmatter.py
  uv run python scripts/check_roadmap_citations.py && uv run python scripts/check_domain_citations.py
  ```
- **Commit sugerido:** `docs(scheduling): erratas e donos do que saiu da persistência da escala [4.4/task-11]`

## 2.1 Matriz de rastreabilidade

| Critério | Task(s) | Check objetivo |
|---|---|---|
| CA01 | 01 (fake), 06 (real) | suíte `test_schedule_repository_laws.py` `[fake]` local e `[postgres]` no Actions |
| CA02 | 05 | suíte L-CF1 `[postgres]` no Actions |
| CA03 | 09 | suíte L-ST `[postgres]` no Actions |
| CA04 | 05, 06, 09 (uma fixture por Task) | `test_no_implementation_branching.py` |
| CA05 | 04 (codec), 06 (linha por escrita) | `test_mappers.py`; `test_schedule_repository.py` |
| CA06 | 06 | `test_schedule_repository.py` (recusas, falha na trilha); `test_schedule_repository_static.py` (varredura) |
| CA07 | 04 (mapa), 07 (corridas) | `test_integrity_errors.py`; `test_schedule_conduct.py` |
| CA08 | 02 | `test_tables.py` |
| CA09 | 03 | `test_schema.py` |
| CA10 | 03 | `test_migration.py` (tabelas, extensão, `downgrade`), `test_schema.py` (nomes) |
| CA11 | 07 | `test_schedule_conduct.py` |
| CA12 | 04 (unit), 06 (integração) | `test_mappers.py`; `test_schedule_repository.py` |
| CA13 | 02, 04, 05 | `test_tables.py`; `test_mappers.py`; `test_schedule_config_repository.py` |
| CA14 | 08 | `test_facade.py` |
| CA15 | 09 | `test_local_staff_read_adapter.py`; os dois `test_bc_independence.py`; `lint-imports` |
| CA16 | 10 | `test_composition_root_scheduling.py` |
| CA17 | 10 | `test_scheduling_flow.py` |
| CA18 | todas | run do Actions do head; linha de cada arquivo no relatório de cobertura do run |
| CA19 | 10 (LAYOUT §6), 11, commit `complete` | `test_composition_root_scheduling.py`; scripts do `docs-check` |

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
make check        # no run do Actions do head do PR (orquestração autônoma)
uv run python scripts/check_technical_postexec.py docs/stages/4.4-scheduling-persistence/technical.md
```

### Verificações funcionais

- [ ] As três suítes de lei verdes com `[fake]` e `[postgres]` no run do Actions.
- [ ] `test_scheduling_flow.py` verde: criar → publicar com aceite → ler, contra Postgres, com
      uma linha de trilha por escrita.
- [ ] Cobertura ≥ 90% em cada arquivo de `src/` tocado: a linha de cada um no
      `coverage report --include="src/*"` do run do head (`gh run view --log`), colada no
      relatório final. Arquivos: os seis de `scheduling/adapters/out/`, `staff/application/facade.py`
      e `composition_root.py`.

### Checklist de fechamento da Stage

- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no run do head
- [ ] Auditoria de testes por subagente independente, com mutação real
- [ ] Commit final `stage 4.4: complete` (roadmap `done` + lacunas do doc de domínio)
- [ ] ADRs 4.4.0001 a 4.4.0004 em `accepted`
- [ ] §7 reflete a execução; `[finding]` com candidata

## 4. Ordem de dependência entre Tasks

```
01 ─► 04 ─► 05 ─► 06 ─► 07
02 ─► 03 ─► 05
02 ─► 04
08 ─► 09
05 ─► 06 ─► 09 ─► 10 ─► 11
```

A ordem numérica é a ordem de execução. A 01 cria `support.py` (a projeção), que a 04 usa nos
testes de mapper e a 05 e a 06 estendem. A 05 cria as tuplas de implementações e a guarda AST;
a 06 e a 09 editam o mesmo conftest e a mesma guarda, nessa ordem.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| SQL que só falha no Actions | DDL offline (`alembic upgrade --sql`) e statements compilados em teste unitário antes do push; iterar pelo log do run |
| Extensão `btree_gist` recusada no Postgres do CI | tabela de dias (ADR 4.4.0001, Alternative B), com `[decision]` na §7 |
| Teste de corrida instável no runner | tempo-limite generoso e falha explícita; se seguir instável, `[finding]` com a medição e o teste marcado `slow` |
| Teste da 4.3 que dependia do relato de id por ordem de inserção do fake | ajustar o teste na Task 01, com `[deviation]` |
| Conflito de merge com a 3.11 ou a 2.7 antes do PR | rebase em `origin/develop`; `down_revision` aponta para o head que existir |

## 6. Referências

- [`./concept.md`](./concept.md)
- [`../../roadmap.md`](../../roadmap.md), [`../../CONVENTIONS.md`](../../CONVENTIONS.md),
  [`../../LAYOUT.md`](../../LAYOUT.md)
- ADRs desta Stage: 4.4.0001 a 4.4.0004
- Precedentes de forma: [`../3.3-staff-persistence/technical.md`](../3.3-staff-persistence/technical.md),
  [`../2.3-identity-persistence/technical.md`](../2.3-identity-persistence/technical.md)
- Skills aplicáveis: `repository-pattern`, `composition-root`, `pytest-with-fakes`,
  `task-ordering-hex`, `hex-arch-python`, `import-linter-rules`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

<!-- END: post-execution -->

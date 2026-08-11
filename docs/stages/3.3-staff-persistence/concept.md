---
title: Concept — Persistência de equipe
description: Definição do que será feito nesta Stage e por quê, com decisões técnicas relevantes
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, staff-persistence, postgres, repositorio, mapper, migration, contrato, tenant, ordenacao, colacao, concorrencia, indice, isolamento]
status: done
created_at: 2026-08-10
updated_at: 2026-08-10
stage_id: 3.3-staff-persistence
stage_title: Persistência de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [3.2-staff-application]
---

# Concept — Stage 3.3 — Persistência de equipe

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **Schema PostgreSQL do BC staff** em SQLAlchemy 2 **Core**
  (`features/staff/adapters/out/postgres/tables.py`), com `staff_metadata`
  próprio — cinco tabelas: `job_functions`, `employees`,
  `employee_job_functions`, `employee_unavailabilities`,
  `employee_shift_preferences`.
- **Migration** `migrations/versions/0003_staff.py`, escrita à mão, mais a
  combinação dos dois `MetaData` em `migrations/env.py`.
- **Mappers puros** domínio↔linha (`mappers.py`), reidratando **sempre pelo
  construtor** das entidades `frozen` da 3.1.
- **Tradutor de `IntegrityError`** (`integrity_errors.py`), por
  `diag.constraint_name` e **por operação** — nunca por texto de mensagem.
- **Os dois adapters** `PostgresJobFunctionRepository` e
  `PostgresEmployeeRepository`, implementando as doze leis publicadas pela 3.2.
- **Ordem total das listagens e da reidratação** (`L-ORD`) — finding herdado
  nº 1 —, fixada como lei do port: vale para o adapter **e** para o fake.
- **Promoção das duas suítes de lei** da 3.2 para `tests/contract/features/staff/`,
  parametrizadas sobre o par real e o par de fakes, com asserções de **conduta**
  (finding herdado nº 4), não só de resultado.
- **Testes de integração** contra Postgres real, para o que é exclusivo do banco
  (migration up/down, constraints, colação, tipos, isolamento).
- **Wiring** no `composition_root.py`: os dois repositórios e os 16 use cases de
  staff.

### Fora do escopo (explicitamente)

- **HTTP, RBAC e paginação** — Stage 3.4. Esta Stage entrega a ordem **total** de
  que a paginação depende; não entrega a paginação.
- **Vínculo de login do funcionário** — Stage 3.5.
- **Qualquer mudança de comportamento dos use cases da 3.2.** Esta Stage
  implementa a fronteira publicada, não a redefine. As únicas edições em
  `application/` são **docstrings** de port (a lei `L-ORD`) — nenhuma assinatura,
  nenhum corpo de use case. A reconciliação da âncora dessas docstrings está em D11.
- **Controle otimista de concorrência (lost update).** Fica declarado como limite
  honesto e escalado — ver §7 D6 e ADR 3.3.0006.
- **Row-level security nativa** (`CREATE POLICY`) — avaliada e rejeitada nesta
  Stage (ADR 3.3.0005), como já fora para identity (ADR 2.3.0002).
- **Unit of Work / port de transação.** A fronteira transacional continua sendo
  a de identity: `Engine` injetado, transação por chamada (2.3 §7 Decisão 6).
- **Alocação/escala** (Step 4) — é ela que passará a produzir `EmployeeInUseError`.
- **Reconciliação de órfãos cross-BC** (funcionário apontando para unidade que
  identity apagou) — consequência declarada de D1, escalada em §10.

### Vínculo com o roadmap

Terceira Stage do Step 3 (`3.3-staff-persistence`, camada-alvo
`adapters/out/postgres`). O Step 3 entrega "equipe da unidade"; a 3.1 deu o
domínio, a 3.2 deu os use cases e os dois ports-out, e esta Stage é a que faz o
sistema **lembrar** — sem ela, o Step 3 é uma máquina de estados sem memória. O
`definition_of_done` do bloco é "integração + contrato verdes contra Postgres", e
a 3.4 consome os dois adapters já montados no composition root. O bloco é
reconciliado por nota datada em cinco eixos (D10).

## 2. Objetivo da Stage

Ao fim desta Stage, os dois ports-out de staff têm implementação PostgreSQL cujo
comportamento é **indistinguível** do par de fakes da 3.2 para as doze leis
nomeadas — provado pela mesma suíte rodando contra as duas implementações.

## 3. Contexto e premissas

### Contexto

A 3.2 publicou dois `Protocol` cujas **docstrings são especificação**: doze leis
nomeadas (L-JF1…L-JF5, L-E1…L-E7), com ordem de checagem normativa e escopo de
tenant na assinatura (ADR 3.2.0002). Ela também entregou, como entregável de
primeira classe, o **par acoplado de fakes** sobre `InMemoryStaffStore` com o
holder `StaffFakes`, anotado com os `Protocol` exatamente para que esta Stage o
parametrize contra os adapters reais.

O precedente direto é a Stage **2.3-identity-persistence**, que pagou uma dívida
que esta Stage não pode repetir: os fakes de identity faziam **upsert
silencioso** onde a chave primária do Postgres rejeita, e a divergência só
apareceu quando o teste de contrato existiu (ADR 2.3.0003). A 3.2 nasceu já com
as leis escritas para evitar isso — mas leis escritas contra um único
implementador ainda são leis não verificadas.

**Quatro** findings foram escalados **para esta Stage** e são tratados aqui: os
três da issue #38 (ordenação estável, indexação sob escopo de tenant, controle de
concorrência) e o quarto, que vive na §7 do `technical.md` da 3.2 e que a issue
não varreu: **"a suíte travava resultado, não conduta"** (2026-08-09, Stage
candidata `3.3-staff-persistence`). Ele importa aqui exatamente pelo motivo que
descreve: quando o fake e o adapter levantam **o mesmo tipo de erro** para a mesma
lei, uma asserção sobre o erro e o estado final é satisfeita por qualquer
arquitetura — inclusive uma sem guarda nenhuma no adapter. Ver §5.20 e os
critérios de conduta em §11.

### Premissas

- **A consistência `unit_id` ↔ `tenant_id` é premissa da borda**, não desta
  camada (concept 3.2 §3): staff trata os dois como identificadores opacos e não
  conhece `Unit` (que é de identity). Quem valida que a unidade pertence ao
  tenant do ator é a 3.4.
- **Volume v1 é pequeno**: dezenas a centenas de funcionários por unidade,
  dezenas de funções por restaurante. As decisões de índice (§7 D5) valem sob
  essa premissa e trazem gatilho explícito de revisão.
- O Postgres de desenvolvimento e o do CI são a **mesma imagem**,
  `postgres:16-alpine` (`docker-compose.yml`, `.github/workflows/ci.yml`).
  Consequência medida e load-bearing: em musl libc a colação "default" se comporta
  como **byte-order**, e por isso um teste de ordenação **não** distingue, nessa
  imagem, um `ORDER BY` com e sem `COLLATE "C"` — ver §9 e CA10b.
- `Settings.database_url` **tem** default embutido
  (`postgresql+psycopg://user:pass@localhost:5432/restaurant_hub`,
  `settings.py:42`), sobrescrito pelo `.env` da worktree. Sem `.env`, a suíte roda
  contra o banco default — o que é exatamente o risco que o docstring da fixture
  `engine` descreve para worktrees paralelas. Esta Stage **não** muda isso; a
  premissa fica registrada para que ninguém a leia ao contrário.

### Dependências

- `3.2-staff-application` (**done**, PR #36 mergeado): os dois ports-out, os nove
  erros de aplicação, os 16 use cases, os DTOs e o par de fakes com `StaffFakes`.
- `3.1-staff-domain` (via 3.2): entidades `frozen` e VOs, incluindo
  `UnavailabilityPeriod` com instantes **ingênuos** (ADR 3.1.0005) e a união
  `WorkloadProfile`.
- `2.3-identity-persistence` (**done**): não é dependência formal, mas é o
  precedente de forma — `tables.py`/`mappers.py`/`integrity_errors.py`, o
  `Engine` injetado, o gate sem skip (ADR 2.3.0001) e as fixtures `engine` /
  `truncar_tudo` em `tests/conftest.py`, compartilhadas por integração e
  contrato.

## 4. Contratos

### Introduzidos

- **`PostgresJobFunctionRepository`** (`adapter-out`) — implementa
  `JobFunctionRepository`. Construtor `(engine: Engine)`.
- **`PostgresEmployeeRepository`** (`adapter-out`) — implementa
  `EmployeeRepository`. Construtor `(engine: Engine)`.
- **`staff_metadata`** (`schema`) — `MetaData` próprio do BC, fonte única do
  schema, consumido pela migration e pelos repositórios.
- **`translate(error, constraint_map, detail)`** (`função de adapter`) — tradutor
  de `IntegrityError` **parametrizado pela operação**; ver §7 D4 e ADR 3.3.0004.
- **`RepositoriosDeStaff`** (`fixture holder` de teste) — o par tipado pelos dois
  `Protocol`, parametrizado `["fake", "postgres"]`; ver §7 D7 e ADR 3.3.0007.
- **`L-ORD`** (`lei de port`, **acrescentada** às doze) — ordem total das
  listagens e da reidratação; ver §5.13 e D11.

```python
# integrity_errors.py — nomes em INGLÊS (CONVENTIONS §1); ver D4 sobre a
# divergência deliberada em relação ao `traduzir` de identity.
ConstraintMap = Mapping[str, Callable[[str], Exception]]

def translate(error: IntegrityError, constraint_map: ConstraintMap, detail: str) -> Exception: ...

# mapas nomeados, um por operação — a mesma constraint significa coisas
# diferentes conforme o que se estava fazendo (§5.14, ADR 3.3.0004)
ON_INSERT_JOB_FUNCTION: ConstraintMap
ON_UPDATE_JOB_FUNCTION: ConstraintMap
ON_DELETE_JOB_FUNCTION: ConstraintMap
ON_WRITE_EMPLOYEE: ConstraintMap
```

### Consumidos

- **`JobFunctionRepository`**, **`EmployeeRepository`** (`port-out`) — Stage 3.2.
- **`Employee`**, **`JobFunction`**, `WorkloadProfile`, `ShiftPreference`,
  `DayPeriod`, `UnavailabilityPeriod` — Stage 3.1.
- **Os nove erros de aplicação** de `features/staff/application/errors.py` — 3.2.
- **`StaffFakes` / `staff_repositories()`** — 3.2, parametrizados aqui.
- **`build_engine`**, `Settings`, `Uuid4Generator` — shared/infrastructure.
- **`engine`, `database_url`, `truncar_tudo`** — `tests/conftest.py` (2.3).

## 5. Invariantes e regras

1. **As doze leis valem verbatim.** Nenhuma é relaxada, reinterpretada ou
   condicionada à implementação. A prova é a suíte de contrato (§11).
2. **`add` é inserção; `update` é `UPDATE`** — nunca upsert (L-JF1/L-JF2/L-E1/L-E2;
   ADR 2.3.0003). No adapter: `INSERT` puro (sem `ON CONFLICT`) e
   `UPDATE … WHERE id = :id AND tenant_id = :t` com `rowcount == 0` ⇒ `*NotFoundError`.
3. **`tenant_id` nunca é atualizável.** Nenhum `UPDATE` o inclui no `SET`; ele só
   aparece no `WHERE`.
4. **Ordem de checagem normativa, dentro de uma transação.** O lookup por
   `(tenant_id, id)` vem **antes** de qualquer outra guarda, e todas as guardas
   de uma operação de escrita rodam na **mesma** transação da escrita — senão a
   ordem é decorativa sob concorrência. Em `EmployeeRepository.update` o lookup é
   `SELECT unit_id … FOR UPDATE`, o que serializa duas edições concorrentes do
   mesmo registro.
5. **Em `add` de funcionário, L-E1 precede L-E4.** A colisão **global** de id é
   verificada antes da validade referencial do conjunto de funções, replicando a
   ordem do fake (`in_memory_employee_repository.py:41-43`). No adapter isso exige
   um `SELECT 1 FROM employees WHERE id = :id` explícito **antes** da pré-checagem
   referencial: a ordem natural do SQL é a inversa (a colisão de id só apareceria
   no `INSERT`), e uma entrada que viola as duas leis responderia
   `JobFunctionNotFoundError` onde o fake responde `EmployeeAlreadyExistsError`.
   Nenhum dos 46 testes de lei existentes discrimina esse caso — por isso ele vira
   invariante declarada e critério de aceite (CA5b), e não descoberta de execução.
6. **Unicidade de nome de função é verbatim e por tenant** — índice único
   `(tenant_id, name)`, sem `lower()`, sem `btrim`, sem `ILIKE` (workforce §3.2;
   ADR 2.3.0005). Verificado no probe.
7. **Colisão de id é global; colisão de nome é por tenant.** O id é a chave
   primária (escopo global, sem `tenant_id`), exatamente como L-JF1/L-E1 declaram.
8. **Ligação cross-tenant é irrepresentável.** `employee_job_functions` carrega
   `tenant_id NOT NULL` e **duas** FKs compostas — para `employees(id, tenant_id)`
   e para `job_functions(id, tenant_id)`. Uma só deixaria o outro lado livre, que
   é metade do cerco e nenhuma garantia (precedente literal de `unit_memberships`,
   ADR 2.3.0002). Verificado no probe.
9. **Remoção de função é guardada pelo banco.** `ON DELETE RESTRICT` na FK de
   `employee_job_functions` para `job_functions`, contando funcionário **ativo e
   inativo** (a tabela de vínculo não conhece o estado). Verificado no probe.
10. **Os filhos do agregado somem com o agregado.** `ON DELETE CASCADE` nas três
    tabelas-filhas de `employees`. Verificado no probe.
11. **A reidratação passa pelo construtor.** Nada de `object.__setattr__`,
    `__new__` ou `dataclasses.fields`: linha corrompida **levanta ao ser lida**,
    em vez de reintroduzir entidade inválida no sistema (precedente: mapper de
    identity, Regra 1). É esta regra — e **só** ela — que impõe as três
    invariantes que o schema não consegue impor (§5.19).
12. **Instantes de indisponibilidade são `TIMESTAMP` SEM fuso, e o mapper NÃO
    normaliza.** É o **oposto** da Regra 2 do mapper de identity, e a inversão é
    deliberada: `UnavailabilityPeriod` **rejeita** tz-aware na construção
    (ADR 3.1.0005 — wall-clock do fuso da unidade). Devolver aware daqui faria a
    reidratação levantar `InvalidUnavailabilityPeriodError` sobre um dado válido.
13. **`L-ORD` — ordem total, determinística e independente de ambiente.**
    - **Listagens** (`list_by_tenant`, `list_by_unit`, `find_all_by_ids`):
      `ORDER BY name COLLATE "C", id COLLATE "C"`. `name` é a chave de negócio;
      `id` é o desempate que torna a ordem **total** (nome não é único —
      homônimos são legítimos). **As duas colunas levam `COLLATE "C"`**: o
      `COLLATE` liga-se ao operando à esquerda, e um `id` sem colação explícita
      volta a depender da colação do banco — justamente no termo que a paginação
      da 3.4 usa como cursor.
    - **Reidratação de `unavailabilities`** (`find_by_id` e `list_by_unit`, os
      dois métodos de `EmployeeRepository` que montam agregado):
      `ORDER BY start_at` — total por funcionário, porque períodos do mesmo
      registro não se sobrepõem, logo o `start` é único.
    - **`shift_preference` e `job_function_ids`** são `frozenset`: sem ordem, sem
      lei.
    - A lei vale para o **fake também** — ele passa a ordenar igual, e é a única
      forma de a suíte de contrato ter um corpo só (ADR 3.3.0003).
14. **A tradução de `IntegrityError` é por nome de constraint E por operação.**
    Provado no probe: `fk_employee_job_functions_job_function` é violada tanto por
    `INSERT` de vínculo com função inexistente (⇒ `JobFunctionNotFoundError`,
    L-E4) quanto por `DELETE` da função referenciada (⇒ `JobFunctionInUseError`,
    L-JF3), com o **mesmo** `diag.constraint_name` e o mesmo `sqlstate` 23503.
    Um mapa global por nome — o de identity — responderia errado em metade dos
    casos.
15. **A id ausente reportada por L-E4 é determinística.** A pré-checagem itera
    `sorted(job_function_ids)` e reporta a **menor** id ausente em ordem
    lexicográfica; o backstop renderiza o conjunto com `sorted()`. Sem isto,
    `frozenset` itera em ordem dependente de `PYTHONHASHSEED` e o teste
    `test_l_e4_reporta_a_id_ausente_de_forma_deterministica` (que exige `"f97"`)
    falharia **de forma intermitente** contra `[postgres]`. O fake já o faz
    (`in_memory_employee_repository.py:126`); a lei o torna exigível do adapter.
16. **`exists_by_job_function` é tenant-wide e ignora estado** (L-E7):
    `SELECT EXISTS(SELECT 1 FROM employee_job_functions WHERE tenant_id = :t AND
    job_function_id = :f)` — sem join, sem filtro de `active`.
17. **`list_by_unit` filtra `active` no SQL**, não em Python. Hoje as duas formas
    são **indistinguíveis por teste** (o resultado é o mesmo), e isso é declarado:
    é restrição de implementação, não invariante observável nesta Stage. Ela existe
    porque a 3.4 acrescentará `LIMIT`/`OFFSET`, e um filtro em Python depois do
    fetch pagina errado. Vira observável — e testável — na 3.4.
18. **A leitura de agregado multi-tabela usa `REPEATABLE READ`.** `find_by_id` e
    `list_by_unit` montam o `Employee` a partir de quatro tabelas em statements
    separados; sob `READ COMMITTED` (default) cada statement pega um snapshot novo,
    e uma escrita concorrente que comite no meio produz uma entidade que **nunca
    existiu** — ou, com um `delete` concorrente, um funcionário sem nenhuma função,
    que a §5.11 faz levantar `EmptyJobFunctionsError` num caminho que o port
    (`find_by_id -> Employee | None`) não prevê. Medido: sob `REPEATABLE READ` o
    problema desaparece. A atomicidade fechada por esta Stage é, portanto, das
    **duas** pontas: escrita transacional e leitura sob snapshot único.
19. **Três invariantes da entidade o schema NÃO impõe, e o limite é declarado:**
    conjunto de funções não-vazio (`EmptyJobFunctionsError`), não-sobreposição de
    períodos (`OverlappingUnavailabilityError`) e nome não-vazio
    (`InvalidNameError`). Nenhuma é representável como constraint sem trigger ou
    `EXCLUDE` com extensão, e todas são impostas pelo `__post_init__` das
    entidades. Consequência aceita e coberta por CA16: uma linha gravada por SQL
    direto que as viole **levanta ao ser lida**, em vez de virar entidade inválida
    em circulação.
20. **A escrita das tabelas-filhas em `update` é por diferença, não por
    reescrita cega.** Apagar todos os vínculos e reinseri-los tocaria linhas que
    não mudaram e inverteria a ordem de lock em relação a um
    `delete_job_function` concorrente: medido, isso produz `DeadlockDetected`
    (`40P01`) que derruba o `update` legítimo — e `40P01` é `OperationalError`,
    **não** `IntegrityError`, logo escapa do tradutor e viraria 500 na 3.4.
    Apagando só os removidos e inserindo só os acrescentados, um `update` que não
    mexe no conjunto não toca a função sendo removida.

### Onde cada finding herdado é fechado — e o limite honesto de cada um

| Finding herdado | O que esta Stage garante | Limite honesto que permanece |
|---|---|---|
| **1. Ordenação estável** | Ordem **total** e independente de locale nas três listagens (duas colunas com `COLLATE "C"`) e na reidratação dos períodos, como lei do port, valendo para fake e real | A ordem é por **codepoint**, não linguística: `"Álvaro"` vem depois de `"Zeus"`. Ordenação para exibição é decisão de apresentação (3.4+) |
| **2. Indexação sob tenant** | Índices decididos por padrão de acesso medido, com o `UNIQUE (tenant_id, name)` já servindo `find_by_name` e `list_by_tenant`; RLS avaliada e rejeitada | Sem índice ordenado de cobertura: a ordenação é `sort` em memória do Postgres. Gatilho de revisão declarado (D5) |
| **3. Concorrência** | Escrita: guardas e escrita numa transação só, `FOR UPDATE` no lookup do `update`, filhas por diferença. Leitura: `REPEATABLE READ` nos agregados multi-tabela | **Lost update permanece**: duas edições que leram o mesmo estado ainda terminam com a última vencendo. Deadlock genuíno (dois atores disputando **a mesma** função) sobe como `OperationalError` |
| **4. Conduta, não só resultado** | Cada guarda de duas camadas tem um discriminador **observável** de qual camada respondeu — a forma da mensagem de L-E4 (id exato = pré-checagem; conjunto = FK) e o teste de bloqueio de duas conexões para o `FOR UPDATE` | Não há mutação automatizada no pipeline; a conduta é travada por asserção explícita, não por mutation testing |

## 6. Casos de erro e exceções

Nenhuma exceção **nova** é introduzida: esta Stage passa a **produzir por outro
caminho** erros que a 3.2 já declarou.

| Cenário no banco | Constraint / condição | Exceção | Lei |
|---|---|---|---|
| `INSERT` de função com id já gravado (qualquer tenant) | `pk_job_functions`, `uq_job_functions_id_tenant` | `JobFunctionAlreadyExistsError` | L-JF1 |
| `INSERT`/`UPDATE` de função com nome já usado no tenant (verbatim) | `uq_job_functions_tenant_name` | `JobFunctionNameAlreadyExistsError` | L-JF1/L-JF2 |
| `UPDATE`/`DELETE` de função ausente no tenant | `rowcount == 0` | `JobFunctionNotFoundError` | L-JF2/L-JF3 |
| `DELETE` de função referenciada por algum funcionário | `fk_employee_job_functions_job_function` (RESTRICT) | `JobFunctionInUseError` | L-JF3 |
| `INSERT` de funcionário com id já gravado | `SELECT` prévio (§5.5); backstop `pk_employees`, `uq_employees_id_tenant` | `EmployeeAlreadyExistsError` | L-E1 |
| `UPDATE` de funcionário ausente no tenant | lookup vazio | `EmployeeNotFoundError` | L-E2 |
| `UPDATE` com `unit_id` divergente, **mesmo tenant** | lookup traz outro `unit_id` | `EmployeeRelocationError` | L-E3 |
| `add`/`update` de funcionário com função ausente no tenant | pré-checagem na transação; backstop `fk_employee_job_functions_job_function` | `JobFunctionNotFoundError` | L-E4 |
| `DELETE` de funcionário ausente no tenant | `rowcount == 0` | `EmployeeNotFoundError` | L-E5 |
| `DELETE` de funcionário referenciado por outro agregado | — | `EmployeeInUseError` | L-E5 — **sem produtor em v1**, entra no Step 4 |

**O que NÃO é traduzido, deliberadamente** (precedente 2.3 §7 Decisão 7) — lista
completa, conferida contra §9: as três FKs de filha para pai
(`fk_employee_job_functions_employee`, `fk_employee_unavailabilities_employee`,
`fk_employee_shift_preferences_employee`); as PKs das três filhas; e as cinco
CHECK (`ck_employees_workload_kind_known`, `ck_employees_workload_iff_hours`,
`ck_employees_weekly_hours_positive`, `ck_employee_unavailabilities_period`,
`ck_employee_shift_preferences_period_known`). Todas só são alcançáveis por **bug
do mapper** ou corrupção — as invariantes correspondentes já são impostas pelo
`__post_init__` das entidades. Vesti-las de erro de negócio produziria um 4xx
plausível escondendo o defeito. Constraint **desconhecida** também sobe intacta,
e CA15b trava isso.

**Erros que não são `IntegrityError` e sobem crus:** `DeadlockDetected` (`40P01`)
e falhas de serialização (`40001`) são `OperationalError` e não passam pelo
tradutor. A §5.20 torna o caso raro; o mapeamento HTTP (retry ou 503) é da 3.4 e
está escalado em §10.

**Sobre o `detalhe` da `JobFunctionNotFoundError` de L-E4 — e por que a forma da
mensagem é contrato, não prosa.** No caminho comum a pré-checagem transacional
identifica a **menor** id ausente (§5.15) e a mensagem cita **essa id**. No
backstop (a corrida que a FK pega), o Postgres não diz qual id faltou por via
estruturada, e parsing de mensagem é proibido: a mensagem cita então o **conjunto
pedido**, renderizado com `sorted()`. A diferença entre as duas formas é o
**discriminador de conduta** do finding nº 4: ela é a única evidência observável
de qual das duas camadas de guarda respondeu.

## 7. Decisões técnicas relevantes

### D1 — Sem chave estrangeira atravessando bounded context
- **O quê:** `employees.tenant_id` e `employees.unit_id` **não** têm FK para
  `restaurants`/`units` de identity. Continuam `Text NOT NULL`, opacos.
- **Por quê:** cada BC descreve o seu schema num `MetaData` próprio, e o
  comentário de `migrations/env.py:39-41` manda **combinar** os metadatas; os
  identificadores de staff são declarados como strings opacas que atravessam a
  fronteira entre BCs (`domain/value_objects/identifiers.py`); e o contrato
  `[importlinter:contract:bc-independence]` existe para que staff não dependa de
  identity. Uma FK física amarraria as duas tabelas ao mesmo banco para sempre e
  faria a suíte de contrato precisar semear identity para testar staff — o que a
  tornaria dependente de outro BC para provar o próprio.
- **Limite honesto:** o banco não impede um funcionário apontando para unidade
  inexistente, e apagar uma unidade em identity deixa órfãos. Quem valida na
  escrita é a 3.4; a reconciliação operacional está escalada em §10.
- **Fonte:** `migrations/env.py:39-41`; `identifiers.py`; `.importlinter:223`;
  concept 3.2 §3.
- **ADR:** [`3_3_0002`](../../adr/3_3_0002-no-cross-bounded-context-foreign-keys.md)

### D2 — `tenant_id` só onde ligação cross-tenant é representável
- **O quê:** `job_functions`, `employees` e `employee_job_functions` carregam
  `tenant_id NOT NULL`. `employee_unavailabilities` e
  `employee_shift_preferences` **não** carregam.
- **Por quê:** é o critério da ADR 2.3.0002, aplicado ao mesmo teste: a coluna
  existe onde ela ancora um cerco. Em `employee_job_functions` a ligação
  cross-tenant **é** representável (funcionário de A com função de B), e as duas
  FKs compostas a tornam impossível. Nas outras duas filhas a única referência é
  o próprio `employee_id`: uma coluna de tenant ali seria denormalização sem
  cerco a ancorar — a mesma razão pela qual `sessions` não a tem.
- **Fonte:** ADR 2.3.0002; probe §9.
- **ADR:** [`3_3_0001`](../../adr/3_3_0001-staff-schema-tenant-scoping-and-composite-fk-cerco.md)

### D3 — Ordem total com colação `"C"` nas duas colunas, fixada como lei do port
- **O quê:** `ORDER BY name COLLATE "C", id COLLATE "C"` nas listagens;
  `ORDER BY start_at` na reidratação dos períodos; a lei entra nas docstrings dos
  ports e o **fake é corrigido** para obedecê-la.
- **Por quê:** a ordem precisa ser (a) **total**, senão a paginação da 3.4
  duplica e omite linhas; e (b) **idêntica entre fake e real**, senão a suíte de
  contrato — o entregável desta Stage — não pode ter corpo único. `COLLATE "C"` é
  byte-order, existe em toda instalação e **coincide exatamente** com o
  `sorted()` do Python (medido). O `COLLATE` liga-se ao operando à esquerda, então
  omiti-lo no `id` deixaria o desempate — o cursor da paginação — sob a colação do
  banco: medido, num cluster com colação linguística
  `('Maria','_z') < ('Maria','0') < ('Maria','a') < ('Maria','B')`, contra o
  `sorted()` do Python que dá `'0' < 'B' < '_z' < 'a'`.
- **Fonte:** `[finding]` da 3.2 (technical §7, 2026-08-09); issue #38; probe §9.
- **ADR:** [`3_3_0003`](../../adr/3_3_0003-total-ordering-with-c-collation-as-port-law.md)

### D4 — Tradução de integridade por constraint **e por operação**, com API em inglês
- **O quê:** `translate` recebe o mapa da operação; o módulo exporta mapas
  nomeados (`ON_INSERT_JOB_FUNCTION`, `ON_UPDATE_JOB_FUNCTION`,
  `ON_DELETE_JOB_FUNCTION`, `ON_WRITE_EMPLOYEE`). Diferente de identity, **uma**
  FK é traduzida.
- **Por quê (forma):** duas razões, ambas medidas. (i) A mesma constraint tem dois
  significados de negócio conforme a operação — provado no probe —, e o mapa
  global de identity não os distingue. (ii) A lei L-E4 **exige** a tradução dessa
  FK: sem ela a corrida vira `IntegrityError` cru, que a 3.4 converteria em 500,
  e a docstring do port diz isso com todas as letras. A regra de identity ("FK
  sobe crua") continua valendo para as FKs que só um bug alcança.
- **Por quê (idioma):** os nomes são em **inglês**, divergindo do `traduzir` de
  `integrity_errors.py` de identity. CONVENTIONS §1 é literal — "todo código-fonte
  deve ser escrito em inglês… classes, funções, métodos, variáveis, parâmetros,
  **constantes**" —, e a §7 do technical da 3.2 já registrou `[finding]`
  "idioma de identificadores locais em `src/`", com direção "renomear os locais em
  PT de **todo** o BC staff para inglês". Estes seis nomes são **API de módulo**,
  não locais: adicioná-los em PT aprofundaria uma dívida já reconhecida. A
  divergência em relação a identity é declarada aqui para que a varredura futura
  a trate como dívida **daquele** módulo, não como padrão a replicar.
- **Fonte:** docstring de `EmployeeRepository.add` (L-E4); concept 2.3 §7
  Decisão 7; CONVENTIONS §1; technical 3.2 §7 (2026-08-08); probe §9.
- **ADR:** [`3_3_0004`](../../adr/3_3_0004-per-operation-integrity-error-translation.md)

### D5 — Índices pelo padrão de acesso medido; RLS rejeitada
- **O quê:** `UNIQUE (tenant_id, name)` em `job_functions` (serve também
  `find_by_name` e `list_by_tenant`); índice `(tenant_id, unit_id)` em
  `employees`; índice `(job_function_id, tenant_id)` em
  `employee_job_functions`. **Não** entram: índice `(tenant_id, id)` redundante
  com a PK, índice ordenado de cobertura, e RLS.
- **Por quê:** `find_by_id(tenant_id, id)` resolve pela PK e devolve no máximo
  uma linha — um índice composto sobre `(tenant_id, id)` custaria escrita e
  espaço para filtrar zero linha a mais. O índice de `employee_job_functions` não
  é otimização: sem ele o `RESTRICT` da FK varre a tabela inteira a cada remoção
  de função. O índice ordenado de cobertura foi rejeitado porque congelaria a
  escolha de colação **no schema**, tornando uma mudança de ordenação uma
  migration em vez de uma linha de SQL — caro justamente onde a decisão é a mais
  provável de mudar. RLS foi rejeitada porque não há papel de banco por tenant
  nem GUC de sessão, o pool é compartilhado, e a política tornaria um `WHERE`
  esquecido **invisível** — o oposto do que se quer de um gate.
- **Gatilho de revisão declarado:** listagem de unidade passando de ~10⁴ linhas,
  ou a paginação da 3.4 aparecendo em plano com `Sort` custoso.
- **Fonte:** finding da 3.2 (concept §10); ADR 3.2.0002; ADR 2.3.0002 (Alternativa
  sobre RLS).
- **ADR:** [`3_3_0005`](../../adr/3_3_0005-tenant-scoped-indexing-without-row-level-security.md)

### D6 — Atomicidade nas duas pontas; controle otimista não
- **O quê:** cada método público de escrita abre uma transação (`engine.begin()`)
  que contém as guardas **e** a escrita; `update` de funcionário faz o lookup com
  `FOR UPDATE` e reescreve as filhas **por diferença** (§5.20). As leituras que
  montam agregado multi-tabela usam `REPEATABLE READ` (§5.18). Não entra coluna
  `version`, nem `If-Match`. "Última escrita vence" permanece.
- **Por quê:** proteger de *lost update* exige que um token de versão **saia** no
  `find_by_id` e **volte** no `update` — isto é, mudar a entidade da 3.1 e a
  assinatura do port da 3.2, que é non-goal explícito da issue #38. Fazer o
  `SELECT` de versão dentro da própria transação de escrita não protege de nada:
  é a mesma leitura. O que **é** desta camada — nenhum estado parcial escrito,
  nenhuma leitura de agregado rasgada, guardas não contornáveis por interleaving —
  está fechado, e as três peças (transação, `FOR UPDATE`, `REPEATABLE READ`) são
  necessárias: sem a terceira, medimos uma leitura devolvendo um `Employee` que
  nunca existiu.
- **Escalado:** o controle otimista precisa de superfície de contrato com o
  cliente; **Stage candidata: `3.4-staff-http`** (ETag/`If-Match`), com a coluna
  de versão entrando junto.
- **Fonte:** concept 3.2 §5.17 e §10; ADR 2.2.0004; concept 2.3 §7 Decisão 6;
  medições de §9.
- **ADR:** [`3_3_0006`](../../adr/3_3_0006-transactional-atomicity-without-optimistic-locking.md)

### D7 — As suítes de lei são **promovidas** para `tests/contract/`, não copiadas
- **O quê:** `tests/unit/features/staff/application/test_{job_function,employee}_repository_laws.py`
  **movem** (`git mv`) para `tests/contract/features/staff/`, trocam
  `pytest.mark.unit` por `pytest.mark.contract`, e passam a receber uma fixture
  `repos` parametrizada `["fake", "postgres"]`. Um holder
  `RepositoriosDeStaff(job_functions, employees)` é criado no `conftest.py` de
  contrato — `StaffFakes` **não** serve, porque tipa `store: InMemoryStaffStore`,
  que o par real não tem.
- **O tamanho real da mudança, declarado:** os **nomes** e as **asserções** dos 46
  testes não mudam — é isso que preserva o pareamento lei a lei. Mas 45 das 46
  funções são hoje `def test_…() -> None` e constroem o sujeito **no corpo**, em
  **49** call-sites de `staff_repositories()` e dos helpers que devolvem
  `StaffFakes` (medido: 26 + 23, excluídas as linhas `def`): toda assinatura e
  toda linha de construção mudam, e os helpers são re-tipados.
  Além disso, `L-ORD` **acrescenta** testes (as asserções de listagem existentes
  usam **conjuntos** de propósito), e a "Nota deliberada" que hoje declara a ordem
  como não-travada (`test_employee_repository_laws.py:317-322`) fica falsa e sai
  no mesmo commit.
- **Por quê:** a skill `pytest-with-fakes` é literal — "don't duplicate contract
  tests inside unit (defeats the point: the contract is single)" — e o precedente
  de identity (`tests/contract/features/identity/`, holder `Repositorios`,
  `params=["fake","postgres"]`) é exatamente esta forma. Copiar produziria duas
  suítes que divergem no dia em que só uma for editada. Nenhum dos 46 usa
  `store.calls` (verificado por grep), que é a instrumentação fake-only excluída do
  contrato pelo mesmo critério da CA16 de identity.
- **Fonte:** skill `pytest-with-fakes` §Structure/§DON'T;
  `tests/contract/features/identity/conftest.py`; docstring de `StaffFakes`.
- **ADR:** [`3_3_0007`](../../adr/3_3_0007-port-law-suites-promoted-to-contract-tests.md)

### D8 — Forma do adapter: a de identity, não a da folha da skill
- **O quê:** módulos planos em `adapters/out/postgres/` — `tables.py`,
  `mappers.py`, `integrity_errors.py`, `job_function_repository.py`,
  `employee_repository.py` — e não os subpacotes `repositories/`, `tables/`,
  `mappers/` do exemplo da skill `repository-pattern`. `Engine` no construtor,
  transação por chamada, sem Unit of Work.
- **Por quê:** a skill descreve o **padrão**; identity já o instanciou neste
  repositório, e duas formas para o mesmo padrão em BCs vizinhos é custo de
  leitura sem ganho. Não há ADR porque não há alternativa em aberto: o ponto
  substantivo da skill ("a transação não é implícita dentro do repositório") já foi
  decidido e documentado pela 2.3 (§7 Decisão 6), e o núcleo de cada método opera
  sobre `Connection`, que é o ponto de troca para um futuro UoW.
- **Fonte:** `features/identity/adapters/out/postgres/`; concept 2.3 §7
  Decisão 6; skill `repository-pattern`.

### D9 — O composition root passa a expor os 16 use cases de staff
- **O quê:** `wire_dependencies` constrói os dois repositórios e os **16 use
  cases** de staff, expostos em `ApplicationDependencies` como campos `staff_*`.
  Um teste mecânico espelhando o de identity acompanha.
- **Por quê:** duas fontes fecham a alternativa. (i) O bloco 3.3 do roadmap lista
  `composition_root.py` em `arquivos_a_modificar` — não tocá-lo contradiz uma
  fonte mais alta na hierarquia. (ii) O docstring de `ApplicationDependencies`
  é explícito: "expõe **use cases**, não repositórios". Wire "só os repositórios"
  exigiria campos de repositório no contêiner, contradizendo-o. Não há, portanto,
  fork real a registrar em ADR: as duas alternativas são refutadas por artefatos
  já aceitos. Com os use cases prontos, a 3.4 vira Stage de adapter puro: router,
  schemas e overrides.
- **Custo declarado:** 16 campos públicos sem consumidor até a 3.4, e CA18 prova
  que estão montados sobre os adapters reais, não que estão exercitados.
- **Fonte:** `docs/roadmap.md` bloco 3.3 (`arquivos_a_modificar`); docstring de
  `composition_root.ApplicationDependencies`; skill `composition-root`.

### D10 — Expansão declarada do bloco do roadmap, em cinco eixos
- **O quê:** nota datada sob o bloco 3.3, no padrão de 1.1/1.2/2.1/2.2/2.3/3.2,
  reconciliando:
  1. **Migration:** `0002_staff.py` → **`0003_staff.py`** (0002 foi consumido por
     `password_setup_tokens`, Stage 2.5).
  2. **`arquivos_a_modificar`:** além de `composition_root.py`, entram
     `migrations/env.py`, `tests/conftest.py`, as duas docstrings de port de
     `features/staff/application/ports/out/`, os dois fakes de
     `tests/fakes/features/staff/` e as duas suítes de lei movidas.
  3. **`contratos_introduzidos: []`:** entram a lei `L-ORD` e o holder de contrato.
  4. **`complexidade_estimada: S` → `M`.** Cinco tabelas, migration à mão, dois
     adapters, mappers, tradutor por operação, lei nova de port, promoção de 46
     testes e wiring de 16 use cases não é `S`; a 3.2, com 16 use cases, é `M`.
     Deixar `S` faria o gate de tamanho de PIPELINE §4.2 avaliar outra Stage.
  5. **`non_goals: []`:** são seis (§1), dois deles substantivos — RLS rejeitada e
     lock otimista escalado.
- **Por quê:** silenciar faria o roadmap afirmar um recorte que a execução
  contradiz — e afirmar um número de migration que colidiria com a existente.
- **Fonte:** `ls migrations/versions/`; `docs/roadmap.md` bloco 3.3;
  concept 2.3 §7 Decisão 9; PIPELINE §4.2.

### D11 — A âncora de `L-ORD` é reconciliada nas duas pontas
- **O quê:** as docstrings de módulo dos dois ports dizem hoje que cada método
  "cita a lei nomeada do **concept §4**" (da 3.2). Ao acrescentar `L-ORD` elas
  passam a citar "concept §4 da 3.2 **+ `L-ORD` (ADR 3.3.0003, Stage 3.3)**", e o
  concept da 3.2 recebe **nota datada** de acréscimo — mesma forma que D10 aplica
  ao roadmap.
- **Por quê:** sem isso a lei existe no código e não existe na fonte que o código
  nomeia — referência pendurada, e o defeito de "afirmar sobre outro arquivo o que
  ele não diz". `L-ORD` **acrescenta**, não emenda: nenhuma das doze muda, e o
  non-goal da issue (não redefinir comportamento de use case) é respeitado, mas a
  âncora precisa existir para que o respeito seja verificável.
- **Fonte:** `job_function_repository.py:4`, `employee_repository.py:4`;
  `docs/stages/3.2-staff-application/concept.md` §4; CONVENTIONS §3.4 (revisões
  posteriores ao fechamento vão para seção datada).

## 8. Integrações

### Internas

- **`features/staff/application`** — consumida (ports, erros, entidades). Tocada
  **apenas** em docstring (lei `L-ORD`, D11); o contrato
  `[importlinter:contract:staff-application-purity]` continua verde porque nada de
  `adapters`/`sqlalchemy` entra lá.
- **`composition_root.py`** — passa a importar `features.staff.adapters`, do mesmo
  jeito que já importa `features.identity.adapters`; a exceção estreita de
  LAYOUT §6 já cobre o par `shared → composition_root`.
- **`migrations/env.py`** — `target_metadata` vira
  `[identity_metadata, staff_metadata]`, como o próprio comentário do arquivo
  instrui.
- **`tests/conftest.py`** — `TABELAS_EM_ORDEM_DE_LIMPEZA` ganha as cinco tabelas
  de staff (filhas antes das mães), mantendo a fonte **única** compartilhada por
  integração e contrato.
- **Stage 3.4** — consome os use cases já montados e a ordem total como base da
  paginação.

### Externas

- **PostgreSQL** `postgres:16-alpine`, via `psycopg` 3 e URL
  `postgresql+psycopg://`. Exigido de verdade: sem banco no ar a suíte **falha**,
  nunca pula (ADR 2.3.0001).

## 9. Modelo de dados

```mermaid
erDiagram
  JOB_FUNCTIONS ||--o{ EMPLOYEE_JOB_FUNCTIONS : "RESTRICT"
  EMPLOYEES ||--o{ EMPLOYEE_JOB_FUNCTIONS : "CASCADE"
  EMPLOYEES ||--o{ EMPLOYEE_UNAVAILABILITIES : "CASCADE"
  EMPLOYEES ||--o{ EMPLOYEE_SHIFT_PREFERENCES : "CASCADE"
```

**Tipos de coluna são contrato, não detalhe** — em especial `weekly_hours`, que é
`NUMERIC` **sem precisão declarada**: `FixedSchedule` aceita qualquer `Decimal`
finito positivo, e uma `NUMERIC(5,2)` — escolha natural para "horas semanais" —
arredonda em silêncio (`22.555 → 22.56`, `0.001 → 0.00`, medido), corrompendo dado
contra a disciplina verbatim do projeto.

| Tabela | Colunas (tipo) | Chaves, constraints e índices |
|---|---|---|
| `job_functions` | `id TEXT`, `tenant_id TEXT`, `name TEXT` — todas `NOT NULL` | `pk_job_functions(id)`; `uq_job_functions_tenant_name(tenant_id, name)`; `uq_job_functions_id_tenant(id, tenant_id)` — **âncora obrigatória** da FK composta |
| `employees` | `id TEXT`, `tenant_id TEXT`, `unit_id TEXT`, `name TEXT`, `workload_kind TEXT`, `active BOOLEAN` — `NOT NULL`; `weekly_hours NUMERIC` **NULL** | `pk_employees(id)`; `uq_employees_id_tenant(id, tenant_id)`; `ck_employees_workload_kind_known`; `ck_employees_workload_iff_hours`; `ck_employees_weekly_hours_positive`; `ix_employees_tenant_unit(tenant_id, unit_id)` |
| `employee_job_functions` | `employee_id TEXT`, `job_function_id TEXT`, `tenant_id TEXT` — `NOT NULL` | `pk_employee_job_functions(employee_id, job_function_id)`; `fk_..._employee → employees(id, tenant_id)` **CASCADE**; `fk_..._job_function → job_functions(id, tenant_id)` **RESTRICT**; `ix_employee_job_functions_function(job_function_id, tenant_id)` |
| `employee_unavailabilities` | `employee_id TEXT`, `start_at TIMESTAMP WITHOUT TIME ZONE`, `end_at TIMESTAMP WITHOUT TIME ZONE` — `NOT NULL` | `pk_employee_unavailabilities(employee_id, start_at)`; `fk_..._employee` **CASCADE**; `ck_employee_unavailabilities_period(start_at < end_at)` |
| `employee_shift_preferences` | `employee_id TEXT`, `period TEXT` — `NOT NULL` | `pk_employee_shift_preferences(employee_id, period)`; `fk_..._employee` **CASCADE**; `ck_employee_shift_preferences_period_known`. **Sem linha = `None`**; preferência declarada nunca é vazia (ADR 3.1.0004) |

**Por que tabelas-filhas e não JSONB.** As leis L-JF3 e L-E4 dependem de uma FK
real: é o `RESTRICT` que recusa apagar função referenciada, e é a FK que pega a
corrida de L-E4. Um `jsonb` com os ids não é referenciável — as duas leis
voltariam a ser check-then-act, exatamente o que a 3.2 escapou.

### Probe contra PostgreSQL real (2026-08-10)

Executado antes de aprovar o schema, no padrão do §9 da 2.3, contra
`postgres:16-alpine`.

| Probe | Resultado |
|---|---|
| `INSERT` de vínculo com função de outro tenant | `23503`, `constraint_name='fk_employee_job_functions_job_function'` — cerco composto funciona |
| `DELETE` de função referenciada | `23503`, **mesmo** `constraint_name` — confirma D4 |
| Nome duplicado no tenant | `23505`, `uq_job_functions_tenant_name` |
| Id duplicado (mesmo tenant e outro tenant) | `23505`, `pk_job_functions` / `pk_employees` |
| `'cozinheiro '` ao lado de `'Cozinheiro'` no mesmo tenant | aceito — unicidade verbatim |
| `DELETE` do funcionário | filhas removidas por CASCADE (0 linhas restantes) |
| `ORDER BY name COLLATE "C", id COLLATE "C"` × `sorted()` do Python | **idênticos** |
| **Colação default desta imagem** | `pg_database.datcollate` **diz** `en_US.utf8`, mas o cluster é musl libc e `pg_collation` não tem `en_US.utf8`: o comportamento é **byte-order**. O rótulo não é evidência do comportamento — daí CA10b |
| Colações ICU disponíveis | `und-x-icu` e `pt-BR-x-icu` existem e **divergem** de `C` (`Álvaro < ana < Ana < Zeus`), o que dá um controle positivo para provar que o `COLLATE "C"` é load-bearing |
| Desempate sem `COLLATE` no `id`, em coluna com colação ICU | `('Maria','_z') < ('Maria','0') < ('Maria','a') < ('Maria','B')` — diverge do `sorted()` do Python. Confirma §5.13 |
| `NUMERIC` (sem precisão) × `Decimal` | round-trip exato, escala preservada. `NUMERIC(5,2)` **arredonda em silêncio** |
| `TIMESTAMP` sem fuso × `datetime` ingênuo | round-trip exato com microssegundos, `tzinfo=None` |
| CHECK iff de jornada | barra `fixed` sem horas **e** `on_demand` com horas |
| Leitura multi-statement sob `READ COMMITTED` × escrita concorrente | devolve agregado **misto** (pai antigo + filha nova) e, com `delete` concorrente, funcionário **sem funções** ⇒ `EmptyJobFunctionsError`. Sob `REPEATABLE READ`, leitura consistente. Confirma §5.18 |
| `update` com reescrita cega das filhas × `delete_job_function` concorrente | `40P01 DeadlockDetected` derruba o `update` legítimo; `40P01` é `OperationalError`, não `IntegrityError`. Confirma §5.20 |
| Nome vazio/whitespace, conjunto de funções vazio, períodos sobrepostos | **aceitos** pelo schema — confirma o limite declarado em §5.19 |

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Adapter e fake divergirem numa lei — a dívida que a 2.3 pagou | M | A | Suíte de lei **única**, promovida para `tests/contract/` e parametrizada; divergência aparece como o mesmo teste verde em `[fake]` e vermelho em `[postgres]` |
| O `COLLATE "C"` ser esquecido e nenhum teste reprovar (a imagem é musl, onde a colação default **já é** byte-order) | **A** | A | CA10b parte 1: asserção sobre o **SQL compilado** do adapter — a única que reprova a omissão, porque nesta imagem nenhum resultado a distingue. A parte 2 (`und-x-icu`) é o controle positivo de que a colação importa |
| Tradução de erro responder o erro errado por a constraint ser a mesma | M | A | Mapa de constraints **por operação** (D4) + CA8b/CA7 cobrindo os **dois** lados da mesma constraint |
| Guarda existir só numa camada e o teste não distinguir (finding nº 4) | M | A | Discriminador de conduta na forma da mensagem de L-E4 (CA8c) e teste de bloqueio de duas conexões para o `FOR UPDATE` (CA6b) |
| Reidratação furar invariante de entidade (o caminho que a 3.1 apontou como mais provável) | M | A | Mapper reidrata só pelo construtor; CA16 cobre as **três** invariantes que o schema não impõe |
| Mapper normalizar o `datetime` para UTC por analogia com identity | M | A | §5.12 explícita + CA17 (`tzinfo is None`) |
| `NUMERIC(p,s)` arredondar em silêncio | M | A | Tipo declarado em §9 + CA14 verificando **tipo**, não só nome de constraint |
| Escopo crescer com os 16 use cases no composition root | M | B | Uma Task só, mecânica, com teste espelhando o de identity (D9) |
| Migration `0002_staff.py` do roadmap colidir com a existente | A | M | Numeração conferida (`0003`) e reconciliada por nota datada (D10) |
| A promoção das suítes ser subestimada como `git mv` | M | M | D7 declara o tamanho real (49 call-sites, 45 assinaturas, testes novos de `L-ORD`, nota deliberada removida) |

### `[finding]` escalados por esta Stage

- **`[finding]` para a `3.4-staff-http` — controle otimista de concorrência.**
  Precisa de token de versão atravessando a borda (ETag/`If-Match`), o que só faz
  sentido onde há cliente. A coluna `version` entra junto, na mesma migration da
  3.4. **Stage candidata: `3.4-staff-http`.**
- **`[finding]` para a `3.4-staff-http` — ordenação linguística para exibição.**
  `L-ORD` fixa ordem por codepoint, correta para paginação e incorreta para
  apresentação em PT (`"Álvaro"` depois de `"Zeus"`). Se a borda quiser ordem
  linguística, é decisão de apresentação — ordenar no cliente ou expor parâmetro
  de ordenação —, **sem** mexer na lei do port, que é o cursor da paginação.
  **Stage candidata: `3.4-staff-http`.**
- **`[finding]` para a `3.4-staff-http` — mapeamento HTTP de `40P01`/`40001`.**
  Deadlock e falha de serialização são `OperationalError`, não passam pelo
  tradutor de integridade e hoje virariam 500. A borda precisa decidir entre
  retry idempotente e 503 explícito. **Stage candidata: `3.4-staff-http`.**
- **`[finding]` para o Step 6 (`6.3-ops-baseline`) — reconciliação de órfãos
  cross-BC.** Consequência declarada de D1/ADR 3.3.0002: apagar unidade ou
  restaurante em identity deixa linhas de staff apontando para o nada, sem cascade
  e sem erro. Nenhuma Stage atual é dona disso; a baseline de operação é o momento
  mais barato para adotá-lo (query de reconciliação + alerta).
  **Stage candidata: `6.3-ops-baseline`.**

> Os `[finding]` acima são a **lista canônica** desta Stage — inclusive os que
> nascem no corpo de um ADR, que de outro modo não são varridos pelo pipeline
> (regra herdada do concept 3.2 §10).

## 11. Critérios de aceitação

### Contrato — a prova de fake ≡ real

- [ ] **CA1.** As duas suítes de lei vivem em `tests/contract/features/staff/`,
      marcadas `pytest.mark.contract`, e **cada** teste roda duas vezes
      (`[fake]`, `[postgres]`) — verificável em `pytest --collect-only -q`.
- [ ] **CA2.** Nenhum corpo de teste de contrato ramifica por implementação. A
      verificação é por **AST** (nenhum `if`/`assert` que alcance o parâmetro da
      fixture), não por grep — grep dá falso positivo em comprehension.
- [ ] **CA3.** As doze leis **e `L-ORD`** têm teste com o nome da lei no
      identificador, e todos passam nos dois parâmetros. Nenhum teste de lei
      permanece em `tests/unit/`.
- [ ] **CA4.** `tests/unit/features/staff/application/` continua verde após a
      remoção das duas suítes (nenhum teste órfão, nenhum import quebrado), e a
      "Nota deliberada" sobre ordem não-travada foi removida.

### Leis específicas do banco

- [ ] **CA5.** `add` com id já gravado **em outro tenant** levanta
      `*AlreadyExistsError` nas duas implementações (colisão global de id).
- [ ] **CA5b.** `add` de funcionário com id **já gravado** e conjunto de funções
      **inexistente** levanta `EmployeeAlreadyExistsError` — não
      `JobFunctionNotFoundError` — nas duas implementações (§5.5).
- [ ] **CA6.** `update` de funcionário com `tenant_id` alheio **e** `unit_id`
      divergente levanta `EmployeeNotFoundError` — nunca `EmployeeRelocationError`.
- [ ] **CA6b.** *(conduta)* Duas conexões: com o `update` de A em curso e não
      commitado, o `update` do **mesmo** registro por B **bloqueia** até o commit
      de A. Prova que o `FOR UPDATE` existe — o resultado final sozinho não o
      distingue de sua ausência.
- [ ] **CA7.** `delete` de função referenciada por funcionário **desligado**
      levanta `JobFunctionInUseError` e a função continua legível.
- [ ] **CA8.** `add`/`update` de funcionário com função de outro tenant levanta
      `JobFunctionNotFoundError`, e **nada** é gravado (releitura confirma).
- [ ] **CA8b.** *(o outro lado da mesma constraint)* Um `INSERT` de vínculo que
      chegue à FK **sem** passar pela pré-checagem produz `IntegrityError` cujo
      `constraint_name` é `fk_employee_job_functions_job_function`, e
      `translate(erro, ON_WRITE_EMPLOYEE, …)` devolve `JobFunctionNotFoundError`
      — **não** `JobFunctionInUseError`. Um mapa global falha aqui.
- [ ] **CA8c.** *(conduta)* A mensagem do caminho comum cita a **menor** id
      ausente (`"f97"` com `{f97, f99}`, estável entre execuções); a do backstop
      cita o conjunto `sorted()`. É a evidência de qual camada respondeu (§5.15,
      finding nº 4).
- [ ] **CA9.** As quatro variantes verbatim (`"cozinheiro "`, `"Cozinheiro "`,
      `"COZINHEIRO"`, `" Cozinheiro"`) são aceitas ao lado de `"Cozinheiro"` no
      mesmo tenant.

### `L-ORD`

- [ ] **CA10.** `list_by_tenant`, `list_by_unit` e `find_all_by_ids` devolvem a
      mesma sequência nas duas implementações, com dado que inclui **nome
      acentuado, case misto, espaço à direita e dois homônimos de ids diferentes**
      — e essa sequência é igual a `sorted()` do Python com desempate por `id`.
- [ ] **CA10b.** *(prova de que a cláusula existe — asserção de conduta, não de
      resultado)* Duas partes, e a primeira é a que reprova a omissão:
      1. **Sobre o SQL do adapter:** o statement compilado de cada uma das três
         listagens contém `COLLATE "C"` nos **dois** termos do `ORDER BY`
         (asserção sobre `str(stmt.compile(dialect=postgresql.dialect()))`).
         Nenhuma asserção sobre o **resultado** consegue reprovar a omissão nesta
         imagem: medido, em `postgres:16-alpine` (musl) `ORDER BY name` e
         `ORDER BY name COLLATE "C"` produzem saída **idêntica** para qualquer
         dado, inclusive o adversarial de CA10.
      2. **Controle positivo, sobre o banco:** o mesmo `ORDER BY` com
         `COLLATE "und-x-icu"` **diverge** do `sorted()` do Python — prova que a
         escolha de colação tem efeito semântico e que a cláusula não é ruído.
      Sem a parte 1, esquecer o `COLLATE "C"` passa despercebido nesta imagem,
      hoje e sempre, e explode no primeiro cluster glibc/ICU.
- [ ] **CA11.** Períodos inseridos fora de ordem cronológica reidratam ordenados
      por `start_at`, nas duas implementações.
- [ ] **CA12.** As docstrings dos dois ports declaram `L-ORD` **e** citam a nova
      âncora (D11); o concept da 3.2 tem a nota datada de acréscimo.

### Integração (exclusivo do banco real)

- [ ] **CA13.** `alembic upgrade head` seguido de `downgrade base` deixa o banco
      sem nenhuma tabela de staff, e o `upgrade` seguinte funciona
      (espelho de `test_migration.py`).
- [ ] **CA14.** Consulta a `pg_constraint` **e** `pg_indexes` confirma: os nomes
      esperados de constraint; os **dois índices não-únicos**
      (`ix_employees_tenant_unit`, `ix_employee_job_functions_function`), que não
      aparecem em `pg_constraint`; o `confdeltype` de cada FK (`r` para a de
      função, `c` para as três de filha); e os **tipos** de coluna — em especial
      `weekly_hours` como `numeric` **sem** precisão.
- [ ] **CA15.** Um `INSERT` direto de linha ilegal (jornada `fixed` sem horas;
      `on_demand` com horas; período com `start >= end`; `period` desconhecido) é
      recusado pelo banco.
- [ ] **CA15b.** Uma `IntegrityError` de constraint **não mapeada** sobe intacta
      (`translate` devolve o próprio erro), e as três FKs de filha para pai não
      são traduzidas. Sem isto, "traduzir tudo" volta sem ninguém notar.
- [ ] **CA16.** Linhas gravadas por SQL direto que violem as **três** invariantes
      não impostas pelo schema (§5.19) — funcionário sem nenhuma função; nome
      vazio/whitespace; dois períodos sobrepostos — fazem `find_by_id`
      **levantar** (`EmptyJobFunctionsError`, `InvalidNameError`,
      `OverlappingUnavailabilityError`), e não devolver entidade inválida.
- [ ] **CA17.** Round-trip preserva `Decimal` em notação posicional (valor **e**
      escala: `22.50` volta `22.50`) e `datetime` ingênuo (microssegundos
      inclusive, `tzinfo is None`).
- [ ] **CA17b.** *(isolamento)* Com uma escrita concorrente commitando entre os
      statements da leitura, `find_by_id` devolve um agregado **consistente** —
      nunca pai antigo com filha nova, nunca funcionário sem funções (§5.18).

### Wiring e gates

- [ ] **CA18.** `wire_dependencies()` devolve os 16 use cases de staff montados
      sobre os adapters Postgres, e nenhum módulo fora do composition root
      instancia adapter de staff (teste mecânico espelhando o de identity).
- [ ] **CA19.** `make check` verde — incluindo `import-check` (os contratos
      `[importlinter:contract:staff-application-purity]` e
      `[importlinter:contract:bc-independence]` continuam verdes) e `layout-check`.
- [ ] **CA20.** Cobertura ≥ 90% em **cada** arquivo novo de
      `features/staff/adapters/out/postgres/`, medida por
      `uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing` e
      lida arquivo a arquivo (o `fail_under = 90` do `pyproject.toml` é **global**
      e não reprova arquivo individual).
- [ ] **CA21.** Nenhum teste desta Stage pula por falta de banco — a fixture
      falha alto (ADR 2.3.0001).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4.
- [x] Toda decisão em §7 tem fonte rastreável? — cada D*N* cita arquivo:linha, ADR ou medição.
- [x] Toda integração externa tem contrato definido? — §8 (Postgres/psycopg/URL/imagem).
- [x] Decisões com **fork real em aberto** têm ADR escrito? — sete (3.3.0001…3.3.0007). D8 e D9 não têm ADR **de propósito**: a alternativa de cada uma é refutada por artefato já aceito (concept 2.3 §7 Decisão 6; o docstring de `ApplicationDependencies` e o `arquivos_a_modificar` do bloco 3.3), logo não há fork a registrar — a justificativa fica na própria decisão. D10 e D11 são reconciliações declaradas, não decisões com alternativa.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 3.2 `done`, PR #36 mergeado.
- [x] Stage cabe em ~3–12 Tasks? — estimativa de **9–10**, com a promoção do contrato reprecificada (D7): schema+migration+env+conftest; mappers; tradutor; adapter de função; adapter de funcionário; `L-ORD` nos ports, no concept da 3.2 e nos fakes; promoção e parametrização das suítes; testes novos de `L-ORD` e de conduta; integração (constraints/tipos/isolamento/colação); wiring.
- [x] Riscos críticos têm mitigação plausível? — §10.
- [x] **Os quatro findings herdados foram tratados, cada um com garantia e limite explícitos?** — tabela ao fim de §5 + D3/D5/D6 + §5.15/§5.20 e CA6b/CA8b/CA8c.
- [x] **O schema foi exercitado contra Postgres real antes da aprovação?** — §9, probe de 2026-08-10, incluindo os controles negativos (isolamento, deadlock, colação ICU, `NUMERIC(5,2)`).
- [x] **Todo `[finding]` escalado por ADR desta Stage tem linha em §10?** — sim, incluindo o do Step 6, que nasce no ADR 3.3.0002.

## 13. Referências

- [`../../roadmap.md`](../../roadmap.md) — bloco `3.3-staff-persistence`
- [`../3.2-staff-application/concept.md`](../3.2-staff-application/concept.md) — as doze leis (§4), garantia regra a regra (§5), findings (§10)
- [`../3.2-staff-application/technical.md`](../3.2-staff-application/technical.md) — §7, `[finding]` da ordenação e o de conduta
- [`../2.3-identity-persistence/concept.md`](../2.3-identity-persistence/concept.md) — precedente de forma
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) — §3.1, §3.2, §3.3, §3.5, §3.6, §3.7
- ADRs desta Stage: `3_3_0001` … `3_3_0007`
- ADRs herdados: 2.3.0001–2.3.0005; 3.1.0001–3.1.0006; 3.2.0001–3.2.0007
- Skills: `repository-pattern`, `pytest-with-fakes`, `composition-root`

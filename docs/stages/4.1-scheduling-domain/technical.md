---
title: Technical — Domínio da escala
description: Plano de execução da Stage 4.1 — 11 Tasks ordenadas (1 Task = 1 commit) para o núcleo de domínio do BC scheduling
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, scheduling-domain, escala, faixa, dia-operacional, horario-de-corte, demanda, alocacao, agregado, intervalo-declarado, vaga-unica-por-faixa, versao]
status: draft
created_at: 2026-09-27
updated_at: 2026-09-27
stage_id: 4.1-scheduling-domain
stage_title: Domínio da escala
step_id: 4
step_title: Escala manual publicável
depends_on: [3.1-staff-domain]
concept_ref: ./concept.md
issue_id: 55
branch: feat/55-4-1-scheduling-domain
tasks_count: 11
---

# Technical — Stage 4.1 — Domínio da escala

> **Como usar (code assistant):** ler §1; executar as Tasks em ordem (§2), 1 Task
> = 1 commit; `make check` verde **antes** de todo commit; registrar desvios em
> §7. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<tipo>(<escopo>): <descrição> [4.1/task-NN]`, escopo **`scheduling`**, subject
> **≤ 100 caracteres** (`scripts/check_commit_msg.py` 74 —
> `MAX_SUBJECT_LEN = 100`), rodapé `Refs #55`.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/55-4-1-scheduling-domain`. Não há sub-PRs internos.

## 1. Contexto e estratégia de execução

### Resumo
Primeiro código do BC `scheduling` — camada `domain` pura, sem I/O. Entrega o
agregado **`Schedule`** (raiz única, ADR 4.1.0009) com as três entidades internas
`ShiftBand` / `ShiftDemand` / `Assignment` alcançadas só pela raiz, os seis VOs
`TimeRange` / `Weekday` / `DayCutoff` / `OperationalCalendar` / `SchedulePeriod` /
`DemandQuantity`, os oito identificadores tipados **próprios do BC**, a hierarquia
`SchedulingError(DomainError)` com **20** subclasses, as **11 mutações** e as **8
leituras** enumeradas no concept §4, e as invariantes estruturais 1–23 do concept
§5 garantidas **por construção em todos os caminhos** (inclusive a reidratação da
4.4) e provadas por testes unitários sem I/O. Ativa também o enforcement
estrutural: contrato `scheduling-domain-purity` no `.importlinter` (espelho de
`staff-domain-purity`, linhas 197–217), inclusão de
`restaurant_hub.features.scheduling` no contrato `bc-independence` (linhas
223–228) e os pacotes-placeholder `features/scheduling/{application,adapters}/`
exigidos por `scripts/check_layout.py` (`REQUIRED_FEATURE_DIRS`, linha 130). Ver
[`concept.md`](./concept.md).

### Estratégia

**TDD inside-out, folhas primeiro** (skill `task-ordering-hex`). A Stage é
**domain-only**, então só o passo 1 da ordem default da skill se aplica; dentro
dele a ordem é a da **dependência de import**, que é também a ordem em que uma
invariante passa a ser verificável:

1. **Tasks 01–02 — chão.** Scaffold + identificadores + contratos de import, e
   depois as 20 exceções. Nada valida nada antes de existir a exceção que a
   recusa nomeia: escrever um VO antes da hierarquia forçaria `ValueError` cru e
   um refactor no commit seguinte.
2. **Tasks 03–05 — VOs de tempo.** `TimeRange` (o sítio único de horas), depois
   `Weekday`/`DayCutoff` (a geometria do dia operacional), depois
   `SchedulePeriod` + `OperationalCalendar` (que **produz** e **alinha** períodos,
   logo depende dos dois anteriores).
3. **Tasks 06–08 — entidades-folha, de dentro para fora.** `DemandQuantity` +
   `Assignment`; `ShiftDemand` (que agrega alocações); `ShiftBand` (que agrega
   demandas e é o **único** nível que vê `nominal_minutes` **e** as alocações ao
   mesmo tempo — daí o intervalo efetivo, a divergência, o limite superior do
   intervalo da alocação e a **uma vaga por registro na faixa** viverem lá).
4. **Tasks 09–11 — a raiz.** Construção + invariantes do agregado + as 8 leituras
   (Task 09); as 9 mutações estruturais e a lei da versão (Task 10); as 2 mutações
   de intervalo, a cláusula de no-op e o fechamento das restrições de
   `reschedule_band` (Task 11).

**O que fica verde a cada commit.** Cada Task cria o(s) módulo(s) **junto com os
seus testes unitários** no mesmo commit e deixa `make check` verde (inclui ruff,
mypy strict, `check_layout.py`, import-linter, lock-check, docs-check e o
test-gate de cobertura ≥ 90%). Nenhuma Task importa código que uma Task posterior
cria: nada antes da Task 09 importa `Schedule`, e é exatamente por isso que a
**linha de corte** declarada no concept §12 (Tasks 01–08 numa Stage, 09–11 na
seguinte) seria viável — mas a medição fechou em **11**, dentro do teto de 12, e a
Stage **não** é cortada.

### Totalidades derivadas que cada Task tem de alimentar

Desde a 3.6 este repo usa **varreduras derivadas** em vez de testes sobre um
representante: o teste enumera um conjunto (o módulo, a superfície pública, a
tabela do concept) e falha quando o conjunto cresce sem a sua asserção. O
precedente concreto é
`tests/unit/features/identity/domain/test_exceptions.py` 45–56, que varre
`vars(identity_errors)` e não uma lista fixa. Consequência dura para esta Stage:
**uma Task que acrescenta membro a um conjunto varrido e não atualiza a varredura
deixa `make check` vermelho entre commits.** As cinco varreduras desta Stage, e
quem as alimenta:

| Varredura (arquivo de teste) | Conjunto derivado | Nasce em | Cresce em |
|---|---|---|---|
| `test_exceptions.py` — mapa de erros | `vars(errors)`: toda exceção do módulo é `SchedulingError`; conjunto público == 20 + raiz (CA17) | 02 | **nenhuma** (as 20 nascem completas na 02) |
| `test_schedule_mutations.py` — lei da versão | as mutações públicas de `Schedule` que devolvem `Schedule` (CA11) | 10 (9 mutações) | **11** (passa a 11) |
| `test_schedule_mutations.py` — matriz (método × exceção) da §6 | o produto declarado na tabela §6 do concept (CA12) | 09 (linhas de `band`/`locate_*`) | **10**, **11** |
| `test_schedule.py` — superfície de leitura | as 8 leituras de §4 devolvem imutável; nenhum outro membro devolve minutos trabalhados (CA15, CA16) | 09 | **nenhuma** (as 8 nascem completas na 09) |
| `test_identifiers.py` + os testes de entidade — 8 identificadores | os 8 tipos × cada entidade que os carrega (CA22) | 06 | **07**, **08**, **09** |

Regra operacional: a Task que cresce um conjunto atualiza a varredura **no mesmo
commit**. Onde a varredura é sobre a superfície pública de `Schedule`, a lista
esperada vive num único sítio do arquivo de teste (constante no topo), para que
crescer signifique editar uma linha, não caçar asserções.

### Pré-condições
- `3.1-staff-domain` em `done` e mergeada em `develop` (dependência de
  **ordenação**; nenhum import atravessa — contrato `bc-independence`).
- Concept desta Stage em `status: done` (commit `stage 4.1: conceptual approved`,
  `b9582fb`).
- ADRs `4_1_0001`–`4_1_0012` em `status: accepted`.
- Branch `feat/55-4-1-scheduling-domain` ativa; `.venv` instalado (`make setup`).

### Premissas técnicas
- Python 3.12 (`StrEnum`, `NewType`, `dataclasses`, `datetime`/`date`/`time`).
- Domínio importa **só** stdlib + `shared/domain` (LAYOUT §3): `SchedulingError`
  herda de `restaurant_hub.shared.domain.exceptions.base.DomainError`. **Nenhum
  import de `features.staff` nem de `features.identity`**.
- Padrão de entidade herdado da 2.1/3.1: `@dataclass(frozen=True, eq=False)`,
  igualdade e `hash` por id (`__eq__` devolve `NotImplemented` para tipo alheio),
  transições via `dataclasses.replace` **revalidadas** pelo `__post_init__`.
- Todo `datetime`/`time` desta Stage é **ingênuo** (wall-clock da unidade,
  ADR 4.1.0005); tz-aware é recusado na construção. Precedente de forma:
  `src/restaurant_hub/features/staff/domain/value_objects/unavailability_period.py`
  31–32 (o par `start`/`end` como `datetime` cru) e 34–36 (tz-aware verificado
  **antes** de comparar, para que `start < end` só rode naive vs. naive).
- Validação de coleção é **par a par sobre a coleção inteira**, no
  `__post_init__`. Precedente literal:
  `src/restaurant_hub/features/staff/domain/entities/employee.py` 93–98 (loop
  `enumerate` + fatia `[indice + 1:]`, com o comentário que cita a reidratação).
- Aritmética de horas em **minutos inteiros** — nunca `float`, nunca `Decimal`
  (ADR 4.1.0007).
- `make check` = `lint typecheck layout-check import-check lock-check docs-check
  test-gate` (`Makefile` 85). No Windows roda por PowerShell:
  `$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check`. Os
  blocos abaixo trazem os comandos diretos (`uv run …`), que rodam em qualquer
  shell; onde aparece `make check`, aplicar o prefixo acima.
- **Nenhum arquivo em `domain/services/`** — `LAYOUT.md` 38 marca o diretório
  como `[planejado]` e `scripts/check_docs_claims.py` reprova caminho anotado que
  já existe. A contagem de horas mora no `TimeRange` (concept §1, §7).

### Estrutura de pastas afetada

```
src/restaurant_hub/features/scheduling/
├── __init__.py
├── application/__init__.py            # placeholder vazio (REQUIRED_FEATURE_DIRS)
├── adapters/__init__.py               # placeholder vazio (idem)
└── domain/
    ├── __init__.py
    ├── entities/{__init__,assignment,shift_demand,shift_band,schedule}.py
    ├── value_objects/{__init__,identifiers,time_range,operational_calendar,
    │                  schedule_period,demand_quantity}.py
    └── exceptions/{__init__,errors}.py
tests/unit/features/scheduling/
├── __init__.py
└── domain/{__init__,test_identifiers,test_exceptions,test_time_range,
             test_operational_calendar,test_schedule_period,test_demand_quantity,
             test_assignment,test_shift_demand,test_shift_band,test_schedule,
             test_schedule_mutations,test_schedule_policies,
             test_schedule_breaks}.py
.importlinter                          # + scheduling-domain-purity; + scheduling em bc-independence
```

## 2. Tasks

> **11 Tasks** (medição do concept §12, confirmada nesta Fase 3B). `__init__.py`
> são **vazios** (import por caminho absoluto, LAYOUT §7) — sem docstring, para
> não criar linha não coberta. Escopo do commit = `scheduling` (ASCII/kebab).
> Baseline de **toda** Task: `make check` verde, incluindo o test-gate de
> cobertura ≥ 90%.

### Task 01 — Scaffold da feature, identificadores tipados e contratos de import

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/__init__.py` (vazio)
  - `src/restaurant_hub/features/scheduling/application/__init__.py` (vazio, placeholder)
  - `src/restaurant_hub/features/scheduling/adapters/__init__.py` (vazio, placeholder)
  - `src/restaurant_hub/features/scheduling/domain/__init__.py` (vazio)
  - `src/restaurant_hub/features/scheduling/domain/entities/__init__.py` (vazio)
  - `src/restaurant_hub/features/scheduling/domain/value_objects/__init__.py` (vazio)
  - `src/restaurant_hub/features/scheduling/domain/exceptions/__init__.py` (vazio)
  - `src/restaurant_hub/features/scheduling/domain/value_objects/identifiers.py`
  - `tests/unit/features/scheduling/__init__.py` (vazio)
  - `tests/unit/features/scheduling/domain/__init__.py` (vazio)
  - `tests/unit/features/scheduling/domain/test_identifiers.py`
- **Arquivos a modificar:** `.importlinter`
- **O que fazer:** criar a árvore de pacotes da feature `scheduling`, incluindo os
  placeholders vazios `application/` e `adapters/` exigidos por
  `scripts/check_layout.py` (`REQUIRED_FEATURE_DIRS`, linha 130). Em
  `identifiers.py`, definir os **8** `NewType` sobre `str` **próprios do BC**
  (concept §4, §7): `ScheduleId`, `ShiftBandId`, `ShiftDemandId`, `AssignmentId`,
  `TenantId`, `UnitId`, `EmployeeId`, `JobFunctionId`. Em `.importlinter`:
  1. acrescentar o contrato `scheduling-domain-purity`, espelho literal de
     `staff-domain-purity` (linhas 197–217): `type = forbidden`,
     `source_modules = restaurant_hub.features.scheduling.domain`,
     `forbidden_modules` = `restaurant_hub.features.scheduling.application`,
     `restaurant_hub.features.scheduling.adapters`,
     `restaurant_hub.shared.application`,
     `restaurant_hub.shared.infrastructure` e os frameworks/boundary (`fastapi`,
     `starlette`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg`, `pydantic`,
     `pydantic_settings`, `httpx`, `argon2`, `jwt`). **Não** proibir
     `restaurant_hub.features` (auto-proibiria imports internos de scheduling) nem
     `restaurant_hub.shared.domain` (dependência legítima: `SchedulingError`
     herda de `DomainError`);
  2. acrescentar `restaurant_hub.features.scheduling` ao contrato
     `bc-independence` (linhas 223–228, hoje só `identity` e `staff`) e atualizar
     o `name` do contrato para citar os três BCs.
- **Detalhes técnicos:** `identifiers.py` **sem lógica de runtime** (padrão 3.1:
  a recusa de vazio/só-whitespace é imposta **nas entidades** — Tasks 06–09). O
  teste afirma o passthrough do `NewType` (`ScheduleId("s1") == "s1"`) e que os
  **8** nomes existem no módulo — é o ponto de partida da varredura de CA22.
  **Não** criar contrato de pureza para `scheduling.application`: a camada é
  placeholder vazio e o contrato nasce na 4.3, com o primeiro use case (precedente
  3.1, que só ativou os dois movimentos declarados no concept).
- **Critério de aceite:** `make check` verde — `check_layout.py` reconhece os 3
  diretórios obrigatórios da feature nova; import-linter lista
  `scheduling-domain-purity` e `bc-independence` como **KEPT** (a contagem de
  contratos sobe de 9 para 10); `test_identifiers.py` passa com os 8 nomes.
  **Fecha (parcial):** CA18 (o lado dos contratos e do layout). **Abre:** CA22.
- **Nota de atomicidade (exceção consciente, PIPELINE §4.3):** a Task estoura o
  guia de ≤ 5 arquivos (11 criados + `.importlinter`) por ser o **scaffold** da
  feature — 10 dos 11 são `__init__.py` **vazios** (0 statements); o conteúdo
  lógico é só `identifiers.py` + os dois movimentos no `.importlinter`, mínimos e
  atados ao scaffold para manter o commit não-vazio e `make check` verde. Mesma
  exceção declarada na Task 01 da 2.1 e da 3.1.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_identifiers.py -v
  uv run python scripts/check_layout.py
  uv run lint-imports
  make check
  ```
- **Commit sugerido:** `feat(scheduling): criar scaffold, identificadores e contratos de import [4.1/task-01]`

---

### Task 02 — Hierarquia de exceções do BC (20 subclasses + raiz)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/exceptions/errors.py`
  - `tests/unit/features/scheduling/domain/test_exceptions.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** definir `SchedulingError(DomainError)` (importando
  `DomainError` de `restaurant_hub.shared.domain.exceptions.base`) e as **20**
  subclasses enumeradas no concept §4: `InvalidIdentifierError`,
  `InvalidTimeRangeError`, `InvalidWeekdayError`, `InvalidDayCutoffError`,
  `InvalidSchedulePeriodError`, `InvalidDemandQuantityError`,
  `InvalidScheduleVersionError`, `InvalidAssignmentBreakError`,
  `DuplicateEntityIdError`, `DuplicateShiftBandError`, `ShiftBandNotFoundError`,
  `ShiftBandInUseError`, `ShiftBandDayChangeError`, `TimeRangeOutsidePeriodError`,
  `DuplicateShiftDemandError`, `ShiftDemandNotFoundError`,
  `ShiftDemandInUseError`, `DuplicateAssignmentError`,
  `DuplicateAssignmentInBandError`, `AssignmentNotFoundError`. Cada uma com
  docstring PT curta; construtor pode receber um valor de contexto e montar a
  mensagem PT (padrão `errors.py` de identity/staff).
  **`DuplicateEntityIdError` recebe um `reason`/nome de tipo de id**, porque a
  invariante 15 o exige para nomear qual coleção quebrou (concept §5.15).
  **`InvalidSchedulePeriodError` recebe um `reason`**, porque a §6 a usa para dois
  cenários distintos (teto de `days` e desalinhamento).
- **Detalhes técnicos:** a raiz é **`SchedulingError`**; nenhuma subclasse herda
  de `Exception` puro nem de `DomainError` direto — é exatamente o engano que a
  varredura pega. Sem estado além da mensagem e do valor de contexto. **Todas as
  20 nascem aqui**, ainda sem consumidor, para que a varredura do mapa de erros
  seja totalidade desde o primeiro commit e nenhuma Task posterior tenha de
  crescê-la.
- **Critério de aceite:** `test_exceptions.py` cobre — `SchedulingError` é
  `DomainError`; teste **parametrizado** sobre as 20 afirmando
  `issubclass(..., SchedulingError)`; **varredura derivada** `vars(errors)` no
  molde de `tests/unit/features/identity/domain/test_exceptions.py` 45–56 (nenhuma
  exceção definida no módulo escapa de `SchedulingError`); o conjunto público do
  módulo é **exatamente** as 20 + a raiz (21); e a mensagem é preservada ao
  levantar (`pytest.raises(..., match=...)`) nas que recebem contexto.
  **Fecha:** **CA17**.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_exceptions.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/exceptions/errors.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar hierarquia de exceções do BC [4.1/task-02]`

---

### Task 03 — `TimeRange`: instantes ingênuos, intervalo declarado e sítio único de horas

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/time_range.py`
  - `tests/unit/features/scheduling/domain/test_time_range.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True)` `TimeRange` com `start: datetime`,
  `end: datetime` e `break_minutes: int = 0`, exatamente a assinatura do concept
  §4. No `__post_init__`, recusar com `InvalidTimeRangeError`: tz-aware em `start`
  ou `end`; `second`/`microsecond` não zero em qualquer dos dois; `start >= end`;
  duração nominal > 24h; `break_minutes < 0`; `break_minutes >= nominal_minutes`.
  Implementar `nominal_minutes` (`@property`),
  `worked_minutes(break_minutes: int | None = None)`, `hours_key`
  (`(start, end)`), `overlaps(other)` e os dois construtores derivados
  `with_break` e `with_bounds`.
- **Detalhes técnicos:**
  - **ordem das checagens:** tz-aware **antes** de comparar `start`/`end`
    (precedente `unavailability_period.py` 34–36), e `nominal_minutes` só é
    calculado depois de o par ser válido — sem isso a validação do
    `break_minutes` roda sobre duração negativa.
  - `worked_minutes` é **método**, não `@property` (mudança declarada no concept
    §4): sem argumento devolve as horas da própria faixa; com argumento, aplica o
    **intervalo efetivo** da alocação. É o **sítio único** de `horas(a)` —
    nenhuma outra expressão aritmética de horas nasce nesta Stage.
  - `overlaps` é `start_A < end_B and start_B < end_A` (semi-aberto): adjacentes
    **não** se sobrepõem.
  - `with_bounds(start, end)` **preserva** `break_minutes` — é o que torna
    "reagendar não muda o intervalo" estrutural, e não uma checagem
    (ADR 4.1.0011; concept §7, restrição 3 de `reschedule_band`).
  - minutos **inteiros** em toda a aritmética; nada de `float`/`Decimal`.
- **Critério de aceite:** `test_time_range.py` cobre — os **6 defeitos** de CA1
  (um cenário inválido por teste, para não fixar precedência entre validações
  coincidentes) e a **lista fechada de aceites-limite** de CA1 (24h exatas;
  `break_minutes = 0`; `break_minutes = nominal_minutes - 1`; faixa que cruza a
  meia-noite civil; faixa que cruza o corte); CA2 (negativo e
  `== nominal_minutes` recusados; `0` e `nominal_minutes - 1` aceitos;
  `worked_minutes() == nominal_minutes - break_minutes` nos três aceitos, **e**
  `worked_minutes(k)` com `k` explícito devolvendo `nominal_minutes - k`); CA3
  (tabela-verdade de `overlaps`: parcial, contenção total, identidade e
  **adjacência não sobrepõe**, com simetria `a.overlaps(b) == b.overlaps(a)` nos
  4 casos, e a faixa que cruza a meia-noite sem tratamento especial). Mais:
  `with_bounds` preserva `break_minutes`, `with_break` o troca, e a igualdade é
  **por valor** (contribui para CA15).
  **Fecha:** **CA1, CA2, CA3**.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_time_range.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/value_objects/time_range.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar TimeRange com intervalo e sítio único de horas [4.1/task-03]`

---

### Task 04 — `Weekday` e `DayCutoff`: a geometria do dia operacional

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/operational_calendar.py`
  - `tests/unit/features/scheduling/domain/test_operational_calendar.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** no módulo `operational_calendar.py`, definir `Weekday`
  (`StrEnum` fechado dos 7 dias, `MONDAY`…`SUNDAY`) com `from_date(day: date)`
  (via `isoweekday()`) e `from_string(value: str)` levantando
  `InvalidWeekdayError`; e `DayCutoff` (`@dataclass(frozen=True)`) com `at: time`,
  recusando tz-aware e `second`/`microsecond` não zero com
  `InvalidDayCutoffError`, e implementando
  `operational_day_of(instant: datetime) -> date` como `instant.date() - 1 dia`
  se `instant.time() < at`, senão `instant.date()`.
- **Detalhes técnicos:**
  - **`at` não tem teto** — decisão do sponsor de 2026-09-27 (Q5), confirmação do
    ADR 4.1.0002 §2. **Não** inventar limite trabalhista (concept §7 "Corte do dia
    sem teto"; `overview.md` 110).
  - `from_string` converte texto em erro **de domínio**, nunca `ValueError` cru do
    `StrEnum` — espelho de `DayPeriod.from_string` de staff
    (`staff/domain/value_objects/shift_preference.py` 33).
  - a co-locação dos três tipos do calendário num módulo só é decisão do concept
    §7 ("`Weekday` e `DayCutoff` co-locados"), precedente da 3.1 (`DayPeriod`
    dentro de `shift_preference.py`).
  - **nenhum default de campo** aqui: `DayCutoff.at` não tem valor default e
    `Weekday` não ganha "dia default" — os dois defaults de configuração vivem
    **só** em `OperationalCalendar.default()`, criado na Task 05 (concept §7
    "Defaults do calendário num único sítio"). Violar isto quebra o gate de CA7.
- **Critério de aceite:** `test_operational_calendar.py` cobre — CA6 (o conjunto é
  exatamente os 7 nomes **e** os 7 valores; `from_date` bate com `isoweekday()`
  nos 7 dias; texto fora do conjunto → `InvalidWeekdayError`); CA4 (os 3 casos do
  corte `05:00` — antes → dia anterior, **exatamente no corte** → mesmo dia,
  depois → mesmo dia; corte `00:00` coincide com o dia civil; **corte `23:00` e o
  jantar de sexta 22:00 com dia operacional quinta** — o caso que reprova a
  implementação ingênua "sempre o dia civil"); CA7 no lado das recusas (`time`
  tz-aware e com `second`/`microsecond` não zero → `InvalidDayCutoffError`); e CA5
  no lado do VO (a faixa `22:00–06:00` com corte `05:00` tem dia operacional o do
  `start`). Igualdade por valor (CA15).
  **Fecha:** **CA4, CA6**. **Parcial:** CA5, CA7.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_operational_calendar.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/value_objects/operational_calendar.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar Weekday e DayCutoff do dia operacional [4.1/task-04]`

---

### Task 05 — `SchedulePeriod` e `OperationalCalendar`: teto, alinhamento e defaults

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/schedule_period.py`
  - `tests/unit/features/scheduling/domain/test_schedule_period.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/operational_calendar.py`
  - `tests/unit/features/scheduling/domain/test_operational_calendar.py`
- **O que fazer:** (a) criar `SchedulePeriod` (`frozen`) com `first_day: date` e
  `days: int = 7`, recusando `days < 1` e `days > 31` com
  `InvalidSchedulePeriodError`, e expondo `last_day`, `operational_days`
  (`tuple[date, ...]`, os `days` dias em ordem) e `contains(operational_day)`.
  (b) acrescentar `OperationalCalendar` ao módulo do calendário: `frozen`, com
  `week_start: Weekday` e `day_cutoff: DayCutoff`, mais `default()`
  (`MONDAY` + `05:00`), `operational_day_of` (delega ao corte),
  `period_starting_on(first_day, days=7)` (recusa `first_day` que não cai no
  `week_start`, com `InvalidSchedulePeriodError(reason="desalinhado")`) e
  `is_aligned(period)` (`Weekday.from_date(period.first_day) == week_start`).
- **Detalhes técnicos:**
  - o teto **31** é o maior mês civil, logo o maior período que a evolução
    "quinzena/mês" (ADR 4.1.0002 §1) precisa admitir; **`days == 7` não é
    invariante** — é o default da fábrica (concept §5.2, §7 "Teto declarado").
  - `is_aligned` existe como método público porque a Task 09 a chama no
    `Schedule.__post_init__` — é o que torna `week_start` dado **vivo** no
    agregado e faz a lei valer na reidratação da 4.4.
  - `OperationalCalendar.default()` é o **único** sítio de `MONDAY` e `05:00` no
    `src/` do BC. Nenhum campo do calendário tem default de dataclass.
- **Critério de aceite:** CA8 inteiro (`days < 1` e `days > 31` →
  `InvalidSchedulePeriodError`; `days = 1` e `days = 31` aceitos;
  `last_day == first_day + 6` com `days = 7`; `operational_days` com `days`
  elementos, em ordem, sem repetição; `contains` verdadeiro nos 7 dias e falso no
  anterior ao primeiro e no seguinte ao último; `period_starting_on` com dia
  inicial diferente do `week_start` → `InvalidSchedulePeriodError`); CA7 no lado
  positivo (`default()` é `MONDAY` + `05:00`) **e o gate de sítio único**, com o
  comando literal do concept §11 devolvendo **exatamente** as linhas de
  `OperationalCalendar.default()` (escopo: só `src/` do BC; fora do escopo os
  testes, as docstrings e a definição dos 7 membros do `StrEnum`); e `is_aligned`
  verdadeiro/falso nos dois sentidos.
  **Fecha:** **CA7, CA8**.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_schedule_period.py tests/unit/features/scheduling/domain/test_operational_calendar.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/value_objects/
  rg -n --glob 'src/restaurant_hub/features/scheduling/**/*.py' -e 'time\(\s*5\s*,\s*0' -e '"05:00"' -e 'Weekday\.MONDAY'
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar SchedulePeriod e OperationalCalendar [4.1/task-05]`

---

### Task 06 — `DemandQuantity` e a entidade `Assignment` (as três marcas)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/demand_quantity.py`
  - `src/restaurant_hub/features/scheduling/domain/entities/assignment.py`
  - `tests/unit/features/scheduling/domain/test_demand_quantity.py`
  - `tests/unit/features/scheduling/domain/test_assignment.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** (a) `DemandQuantity` (`frozen`) com `value: int >= 0`,
  recusando negativo com `InvalidDemandQuantityError`. (b) `Assignment`
  (`@dataclass(frozen=True, eq=False)`) com `id: AssignmentId`,
  `employee_id: EmployeeId`, `counts_toward_workload: bool = True`,
  `function_exception: bool = False` e `break_minutes: int | None = None`; no
  `__post_init__`, ids não-vazios (`InvalidIdentifierError`) e, se
  `break_minutes` foi dado, `>= 0` (`InvalidAssignmentBreakError`); igualdade e
  `hash` por `id`; transições `declare_workload_counting(counts)` e
  `declare_break(break_minutes | None)`, ambas via `dataclasses.replace`.
- **Detalhes técnicos:**
  - **o limite superior do `break_minutes` da alocação NÃO vive aqui** — só a
    faixa conhece `nominal_minutes`, e a checagem
    `break_minutes < nominal_minutes` é da Task 08 (concept §4 `Assignment`,
    §5.6). Aqui só o piso.
  - `None` em `declare_break` **limpa** a declaração e volta a herdar o intervalo
    da faixa (ADR 4.1.0011).
  - **nenhuma mutação para `function_exception`** — ausência por **atribuição** (a
    pergunta é lacuna da 4.2, ADR 4.1.0003 (f)), não por irrevogabilidade (concept
    §5.13, §7). Não inventar `declare_function_exception`.
  - `DemandQuantity` é VO e não `int` cru: sem ele a validação se espalharia por
    `declare_demand`, `change_demand_quantity` e pela reidratação (concept §7).
  - não-vazio = ao menos um caractere não-whitespace (predicado `.strip()`, padrão
    identity/staff).
- **Critério de aceite:** CA9 (`-1` → `InvalidDemandQuantityError`; `0` e
  positivos aceitos); CA14 no lado dos defaults e das transições da entidade
  (default `True`/`False`/`None`; `declare_workload_counting` alterna;
  `declare_break` declara **e** limpa com `None`); `break_minutes = -1` →
  `InvalidAssignmentBreakError`; CA22 para `AssignmentId` e `EmployeeId` (`""` e
  `"   "`); CA15 no que cabe (`Assignment` é frozen — atribuição direta levanta
  `FrozenInstanceError`; compara por id — duas instâncias de id igual e conteúdo
  diferente são iguais e têm o mesmo `hash`; `DemandQuantity` compara por valor).
  **Fecha:** **CA9**. **Parcial:** CA14, CA15, CA22.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_demand_quantity.py tests/unit/features/scheduling/domain/test_assignment.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar DemandQuantity e a entidade Assignment [4.1/task-06]`

---

### Task 07 — A entidade `ShiftDemand` (a demanda de uma função e as suas alocações)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/entities/shift_demand.py`
  - `tests/unit/features/scheduling/domain/test_shift_demand.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `ShiftDemand` (`@dataclass(frozen=True, eq=False)`) com
  `id: ShiftDemandId`, `job_function_id: JobFunctionId`,
  `quantity: DemandQuantity` e `assignments: tuple[Assignment, ...] = ()`. No
  `__post_init__`: ids não-vazios (`InvalidIdentifierError`); `employee_id`
  distinto **par a par** entre as alocações (`DuplicateAssignmentError`); ids de
  alocação distintos **par a par** (`DuplicateEntityIdError`, com o nome do tipo
  no `reason`). Expor `allocated` (`len(assignments)`), `with_quantity`,
  `with_assignment` e `without_assignment(assignment_id)`.
- **Detalhes técnicos:**
  - as duas checagens de duplicidade são **par a par sobre a coleção inteira**, no
    molde de `employee.py` 93–98 — não só entre pares consecutivos. É a lição do
    Checkpoint C da 3.1 (`3.1-staff-domain/technical.md` §7, 2026-07-29).
  - `with_*` devolvem nova instância e passam de novo pelo `__post_init__` (via
    `dataclasses.replace`), logo `with_assignment` de um `employee_id` repetido
    levanta `DuplicateAssignmentError` **sem** checagem própria.
  - `without_assignment` de id inexistente é **no-op silencioso** neste nível: a
    `AssignmentNotFoundError` é responsabilidade da **raiz** (`unassign`, Task
    10), que é quem localiza. Não duplicar a recusa aqui.
- **Critério de aceite:** construção com o mesmo `employee_id` duas vezes →
  `DuplicateAssignmentError`, e com dois `AssignmentId` iguais →
  `DuplicateEntityIdError`, **cada um provado com o par não consecutivo em coleção
  de 3**; `allocated` conta; `with_quantity`/`with_assignment`/
  `without_assignment` devolvem nova instância com a original intacta;
  `assignments` é `tuple` (nunca `list`); CA22 para `ShiftDemandId` e
  `JobFunctionId`; frozen + identidade por id.
  **Parcial:** CA10, CA15, CA22.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_shift_demand.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/entities/shift_demand.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar a entidade ShiftDemand [4.1/task-07]`

---

### Task 08 — A entidade `ShiftBand`: intervalo efetivo, divergência e uma vaga por registro

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/entities/shift_band.py`
  - `tests/unit/features/scheduling/domain/test_shift_band.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `ShiftBand` (`@dataclass(frozen=True, eq=False)`) com
  `id: ShiftBandId`, `time_range: TimeRange` e
  `demands: tuple[ShiftDemand, ...] = ()`. No `__post_init__`, as checagens do
  concept §4: id não-vazio; `job_function_id` distinto par a par entre as demandas
  (`DuplicateShiftDemandError`); ids de demanda distintos par a par
  (`DuplicateEntityIdError`); **toda** alocação com `break_minutes` declarado
  satisfaz `break_minutes < time_range.nominal_minutes`
  (`InvalidAssignmentBreakError`); e `employee_id` distinto par a par entre
  **todas** as alocações de **todas** as demandas da faixa
  (`DuplicateAssignmentInBandError`). Expor `assignment_count`,
  `effective_break_of(assignment)`, `has_break_divergence(assignment)`,
  `rescheduled_to(start, end)`, `with_band_break`, `with_demand`, `with_demands` e
  `without_demand(demand_id)`.
- **Detalhes técnicos:**
  - a faixa é o **único** nível que vê `nominal_minutes` **e** as alocações ao
    mesmo tempo — daí o teto do intervalo da alocação (ADR 4.1.0011) e a vaga
    única por registro (ADR 4.1.0012) viverem aqui e não na demanda.
  - `effective_break_of` = `assignment.break_minutes` se declarado, senão
    `time_range.break_minutes`. `has_break_divergence` é **derivado** —
    `break_minutes` declarado **e** diferente do da faixa; **nunca** campo
    armazenado (concept §5.13; ADR 4.1.0011).
  - `rescheduled_to` usa `time_range.with_bounds`, que **preserva**
    `break_minutes` — a preservação do intervalo no reagendamento é estrutural.
  - a varredura de `employee_id` é **entre demandas**, não dentro de cada uma (a
    de dentro é a `DuplicateAssignmentError` da Task 07): as duas linhas da §6 são
    **disjuntas por nível**, e o teste tem de provar **qual** sai em cada caso.
  - `rescheduled_to`/`with_*` revalidam pelo `__post_init__`, logo encurtar a
    faixa abaixo de um intervalo já declarado (da faixa → `InvalidTimeRangeError`
    dentro do `TimeRange`; de uma alocação → `InvalidAssignmentBreakError` aqui) é
    recusado **sem** checagem extra.
- **Critério de aceite:** as quatro recusas da construção, cada uma com o par
  **não consecutivo** em coleção de 3 (`DuplicateShiftDemandError`;
  `DuplicateEntityIdError`; `InvalidAssignmentBreakError` com
  `break_minutes >= nominal_minutes`; `DuplicateAssignmentInBandError` com o mesmo
  `employee_id` em alocações de **duas demandas distintas** — o caminho da
  reidratação da 4.4, que nenhuma mutação atravessa); `effective_break_of` devolve
  o da alocação quando declarado e o da faixa quando não; `has_break_divergence`
  verdadeiro só no primeiro caso e **falso** quando o declarado é **igual** ao da
  faixa; `rescheduled_to` preserva `break_minutes`, demandas e alocações;
  `assignment_count` soma as alocações de todas as demandas; CA22 para
  `ShiftBandId`; frozen + identidade por id; `demands` é `tuple`.
  **Fecha:** CA25 no lado da **reidratação**. **Parcial:** CA10, CA15, CA22, CA23.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_shift_band.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/entities/shift_band.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar a entidade ShiftBand com intervalo efetivo [4.1/task-08]`

---

### Task 09 — A raiz `Schedule`: invariantes do agregado e as 8 leituras

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/entities/schedule.py`
  - `tests/unit/features/scheduling/domain/test_schedule.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `Schedule` (`@dataclass(frozen=True, eq=False)`) com `id`,
  `tenant_id`, `unit_id`, `period: SchedulePeriod`,
  `calendar: OperationalCalendar`, `bands: tuple[ShiftBand, ...] = ()` e
  `version: int = 1`. No `__post_init__`, as checagens do concept §4: ids
  não-vazios; `version >= 1` (`InvalidScheduleVersionError`);
  `calendar.is_aligned(period)` (`InvalidSchedulePeriodError`); `(start, end)`
  distinto par a par entre as faixas (`DuplicateShiftBandError` — a chave **não**
  inclui o intervalo); toda faixa começa num dia operacional do período
  (`TimeRangeOutsidePeriodError`); ids internos únicos no agregado inteiro, par a
  par **por tipo** (`DuplicateEntityIdError`) — incluindo os ids de demanda e de
  alocação **entre** faixas e demandas distintas, que nenhum nível inferior vê.
  Implementar as **8 leituras**: `band`, `locate_demand`, `locate_assignment`,
  `bands_of`, `operational_day_of`, `worked_minutes_of`,
  `effective_break_minutes_of`, `has_break_divergence`.
- **Detalhes técnicos:**
  - **nenhuma mutação nesta Task** — a raiz nasce imutável e legível; as 11
    mutações vêm nas Tasks 10 e 11. É o que mantém esta Task testável e o commit
    pequeno.
  - `worked_minutes_of` **delega** ao sítio único:
    `band.time_range.worked_minutes(band.effective_break_of(assignment))`. Nenhuma
    aritmética de horas nova.
  - `bands_of(operational_day)` filtra por
    `calendar.operational_day_of(band.time_range.start) == operational_day` —
    **dia operacional, não civil**.
  - as leituras `band` / `locate_demand` / `locate_assignment` /
    `worked_minutes_of` / `effective_break_minutes_of` / `has_break_divergence`
    levantam `ShiftBandNotFoundError` / `ShiftDemandNotFoundError` /
    `AssignmentNotFoundError` conforme a §6 — são as primeiras linhas da matriz de
    CA12, e nascem com a constante de parametrização no topo do arquivo de teste.
  - toda leitura devolve `tuple` ou valor imutável — **nunca** a coleção interna,
    nunca `list`/`dict`/`set`.
- **Critério de aceite:**
  - **CA10 inteiro** — duas faixas de `(start, end)` igual →
    `DuplicateShiftBandError`; faixa fora do período →
    `TimeRangeOutsidePeriodError`; `version = 0` →
    `InvalidScheduleVersionError`; `period.first_day` fora do `week_start`
    fotografado → `InvalidSchedulePeriodError`; dois `ShiftBandId` iguais, dois
    `ShiftDemandId` iguais em **faixas distintas** e dois `AssignmentId` iguais em
    **demandas distintas** → `DuplicateEntityIdError`, cada um em coleção de 3 com
    o par **não consecutivo**.
  - **CA24** — `bands_of` agrupa pelo dia operacional (a faixa de sábado
    `02:00–06:00` com corte `05:00` aparece em `bands_of(sexta)` e **não** em
    `bands_of(sábado)`); `locate_demand` devolve o par correto e
    `locate_assignment` a tripla correta, em agregado com 2 faixas e 2 demandas
    por faixa. **Mais** — refinamento desta Fase 3B, não mudança de contrato:
    `operational_day_of(band)` é a **oitava** leitura e o concept §11 não lhe dá
    critério próprio (só a varredura de imutabilidade de CA15 a alcança), então
    esta Task a exercita diretamente, com a mesma faixa de sábado `02:00–06:00`
    devolvendo **sexta**. Sem isso, a mutação "devolver o dia civil em
    `operational_day_of`" sobreviveria enquanto `bands_of` estivesse verde.
  - **CA16** — `worked_minutes_of` devolve `nominal_minutes − intervalo efetivo`;
    id inexistente → `AssignmentNotFoundError`; e **varredura derivada**: nenhum
    outro membro público de `Schedule`/`ShiftBand`/`ShiftDemand`/`Assignment`
    devolve minutos trabalhados (`effective_break_minutes_of` devolve minutos de
    **intervalo**, e é a única outra leitura em minutos).
  - **CA15 fecha** — as 4 entidades frozen e por id, os 6 VOs por valor, e a
    varredura sobre as **8 leituras** enumeradas (cada uma devolve `tuple`/valor
    imutável), iterando a lista do concept §4 e não um representante.
  - **CA22 fecha** — `ScheduleId`, `TenantId` e `UnitId` com `""` e `"   "`,
    somando aos 5 já cobertos nas Tasks 06–08: os **8** tipos, em **cada**
    entidade que os carrega.
  - **CA12 (parcial)** — as linhas de `band`/`locate_demand`/`locate_assignment`
    e das três leituras em minutos/divergência.
  **Fecha:** **CA10, CA15, CA16, CA22, CA24**. **Parcial:** CA12, CA23.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_schedule.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/entities/schedule.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar a raiz Schedule com invariantes e leituras [4.1/task-09]`

---

### Task 10 — As 9 mutações estruturais da raiz e a lei da versão

- **Arquivos a criar:**
  - `tests/unit/features/scheduling/domain/test_schedule_mutations.py`
  - `tests/unit/features/scheduling/domain/test_schedule_policies.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/domain/entities/schedule.py`
- **O que fazer:** acrescentar à raiz as **9 mutações estruturais** do concept §4,
  cada uma devolvendo **nova instância** com `version + 1`: `enable_band`,
  `reschedule_band`, `disable_band`, `declare_demand`, `change_demand_quantity`,
  `withdraw_demand`, `assign`, `unassign`, `declare_workload_counting`. Todas
  reconstroem a árvore por `dataclasses.replace` e são **revalidadas** pelo
  `__post_init__` da raiz e das internas.
- **Detalhes técnicos:**
  - **`enable_band`** recebe o `ShiftBandId` de fora (geração de id é da
    application — `IdGenerator`, concept §3); colisão de `(start, end)` →
    `DuplicateShiftBandError`; início fora dos dias operacionais →
    `TimeRangeOutsidePeriodError`. **Aceita** a faixa que começa no último dia
    operacional e termina depois dele (ADR 4.1.0008 §3).
  - **`reschedule_band`** recebe `start`/`end` (nunca um `TimeRange` — a restrição
    3 do concept §7 é **estrutural**, por assinatura) e usa
    `ShiftBand.rescheduled_to`: preserva ids, demandas, alocações e o intervalo da
    faixa. Recusa destino em **outro dia operacional**
    (`ShiftBandDayChangeError`), fora do período (`TimeRangeOutsidePeriodError`) e
    colidindo com o par de **outra** faixa (`DuplicateShiftBandError` — a
    comparação **exclui a própria faixa**, senão o reagendamento nunca passaria).
  - **`disable_band`** e **`withdraw_demand`** **recusam** enquanto houver
    alocação dependente (`ShiftBandInUseError` / `ShiftDemandInUseError`) e **não
    cascateiam** (decisão do sponsor Q1). **Sem** alocação, removem sem cerimônia
    — `disable_band` descarta as demandas contidas junto.
  - **`assign`** recebe `assignment_id`, `demand_id`, `employee_id` e as duas
    marcas por keyword; levanta `DuplicateAssignmentError` se o registro já ocupa
    vaga **desta** demanda e `DuplicateAssignmentInBandError` se ocupa vaga de
    **outra** demanda da **mesma** faixa (§5.23). Faixas **distintas** seguem
    aceitas.
  - **`change_demand_quantity`** **não** recusa `N` abaixo do número de alocados —
    `N` é alvo, não teto (ADR 4.1.0003 (g)); a sobre-cobertura é política da 4.2.
  - **a cláusula de no-op NÃO entra aqui** — é da Task 11, junto com as outras
    três mutações idempotentes, para que a regra nasça num sítio só.
- **Critério de aceite:**
  - **CA11 (parcial, 9 de 11)** — teste parametrizado sobre as 9, cada uma
    devolvendo nova instância com `version == anterior + 1` e deixando a original
    **intacta**; a lista esperada é a constante no topo do arquivo (a varredura
    que a Task 11 cresce para 11).
  - **CA12 (parcial)** — as linhas da matriz §6 que estes métodos ocupam: os de
    `ShiftBandNotFoundError` desta Task (`reschedule_band`, `disable_band`,
    `declare_demand`), os 3 de `ShiftDemandNotFoundError`
    (`change_demand_quantity`, `withdraw_demand`, `assign`), os de
    `AssignmentNotFoundError` (`unassign`, `declare_workload_counting`), os **2**
    caminhos de `TimeRangeOutsidePeriodError`, os **2** de
    `DuplicateShiftBandError`, `DuplicateShiftDemandError` em `declare_demand`, e
    `DuplicateAssignmentError` + `DuplicateAssignmentInBandError` em `assign`.
  - **CA20** — `disable_band` com alocação → `ShiftBandInUseError`;
    `withdraw_demand` com alocação → `ShiftDemandInUseError`; `disable_band` numa
    faixa com demandas e **sem** alocação **passa**, e as demandas saem com ela
    (`locate_demand` do id removido → `ShiftDemandNotFoundError`);
    `withdraw_demand` numa demanda de `N > 0` sem alocados **passa**.
  - **CA21 (parcial)** — `reschedule_band` de `16h–00h` para `17h–01h` preserva
    ids, demandas, alocações e `break_minutes` (comparação de **conteúdo**, não só
    do id); outro dia operacional → `ShiftBandDayChangeError`; fora do período →
    `TimeRangeOutsidePeriodError`; colisão com outra faixa →
    `DuplicateShiftBandError`.
  - **CA25 fecha** — em faixa `16h–00h` de sexta com demanda de cozinheiro e de
    atendente: `assign` da Ana à primeira passa, o segundo `assign` da **mesma**
    Ana à segunda levanta `DuplicateAssignmentInBandError`, a versão **não**
    incrementa e o agregado anterior fica intacto; o segundo `assign` **na mesma**
    demanda continua levantando `DuplicateAssignmentError` (prova de que as duas
    linhas da §6 são disjuntas); o estado resultante é a consequência declarada —
    cozinheiro com `allocated == 1` e atendente com `allocated == 0`, a segunda
    vaga **descoberta**; e o **positivo**: a mesma Ana em faixas **distintas** da
    mesma sexta (`16h–00h` e `18h–23h`, parcialmente sobrepostas) é **aceita**,
    com `assignment_count == 1` em cada faixa e nenhuma exceção.
  - **CA13 inteiro** (`test_schedule_policies.py`) — as **8** situações da lista
    fechada de §5.18 **salvam**: (1) mesmo registro em duas faixas distintas
    sobrepostas da **mesma** função; (2) mesmo registro em **funções diferentes**,
    em faixas distintas parcialmente sobrepostas; (3) alocação em faixa que cobre
    indisponibilidade; (4) **descanso abaixo de 11h** (faixa até 23:00 de segunda
    + faixa a partir de 06:00 de terça, mesma pessoa); (5) soma acima de 10h no
    dia; (6) acima de 44h na semana; (7) acima da carga contratada; (8) função não
    detida e alocados acima de `N`, inclusive `change_demand_quantity` reduzindo
    `N` abaixo do número de alocados. Para (3), (7) e o lado "carga" de (8) a
    asserção é de **superfície**, com o rótulo honesto do concept §11 — "o
    agregado não tem campo nem port que expresse indisponibilidade, carga
    contratada ou conjunto de funções do registro", derivada do conjunto público
    de §4 — **mais** o aceite do estado que as representa.
  - **CA5 fecha** — `enable_band` aceita a faixa que começa no último dia
    operacional do período e **termina depois** dele.
- **Nota de atomicidade:** 3 arquivos (1 modificado + 2 criados), dentro do guia.
  Os dois arquivos de teste são separados porque `test_schedule_policies.py` prova
  **ausência de recusa** (8 cenários) e `test_schedule_mutations.py` prova a lei da
  versão e a matriz de erro — misturá-los faria um arquivo de leitura difícil e
  duas varreduras no mesmo sítio.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/test_schedule_mutations.py tests/unit/features/scheduling/domain/test_schedule_policies.py -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/domain/entities/schedule.py
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar as 9 mutações estruturais e a lei da versão [4.1/task-10]`

---

### Task 11 — As 2 mutações de intervalo, a cláusula de no-op e o fecho de `reschedule_band`

- **Arquivos a criar:**
  - `tests/unit/features/scheduling/domain/test_schedule_breaks.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/domain/entities/schedule.py`
  - `tests/unit/features/scheduling/domain/test_schedule_mutations.py`
- **O que fazer:** (a) acrescentar as **2 mutações de intervalo**:
  `redeclare_band_break(band_id, break_minutes)` (verbo próprio — muda as horas de
  **todos** os alocados sem intervalo próprio; valor fora de
  `0 <= break < nominal_minutes` → `InvalidTimeRangeError`, vindo do `TimeRange`)
  e `declare_allocation_break(assignment_id, break_minutes | None)` (`None` volta
  a **herdar** o da faixa; fora dos limites → `InvalidAssignmentBreakError`, vindo
  do `ShiftBand`). (b) aplicar a **cláusula de no-op** (invariante 16) às **4**
  mutações idempotentes de valor: `reschedule_band` para o próprio
  `(start, end)`, `redeclare_band_break` para o próprio intervalo,
  `declare_workload_counting` e `declare_allocation_break` para o valor corrente —
  todas devolvem **`self`**, sem incrementar `version` e sem levantar erro de
  duplicidade. (c) crescer a varredura da lei da versão de 9 para **11** e a
  matriz de CA12 com as linhas de `redeclare_band_break` (5º método de
  `ShiftBandNotFoundError`) e de `declare_allocation_break`
  (`AssignmentNotFoundError`).
- **Detalhes técnicos:**
  - o no-op é **comparação de valor** contra o estado corrente **antes** de
    reconstruir — e no caso de `reschedule_band` a comparação tem de vir **antes**
    da checagem de duplicidade, senão o no-op vira `DuplicateShiftBandError`
    espúrio (concept §5.16).
  - o no-op devolve **`self`** (a mesma instância, não uma equivalente): o teste
    afirma `resultado is original`.
  - `redeclare_band_break` usa `ShiftBand.with_band_break`; a revalidação da faixa
    recusa o intervalo `>= nominal_minutes` **sem** checagem própria na raiz.
  - nenhuma mutação para `function_exception` nasce aqui (concept §5.13, §7).
- **Critério de aceite:**
  - **CA23 fecha** — em faixa `16h–00h` com `break_minutes = 0`: a alocação do
    cozinheiro com `break_minutes = 60` tem `effective_break_minutes_of == 60`,
    `worked_minutes_of == 420` e `has_break_divergence is True`; a do atendente
    sem declaração tem `effective_break_minutes_of == 0`,
    `worked_minutes_of == 480` e `has_break_divergence is False` (**7h e 8h na
    mesma faixa**, o cenário do sponsor); `declare_allocation_break(a, None)`
    volta a herdar e **zera** a divergência; `break_minutes` negativo ou
    `>= nominal_minutes` → `InvalidAssignmentBreakError`; e **duas faixas
    `16h–00h` com intervalos 0 e 60 no mesmo dia → `DuplicateShiftBandError`** (a
    chave é `(start, end)`).
  - **CA11b** — as 4 mutações idempotentes devolvem `self`, com `version`
    **inalterada** e **sem** `DuplicateShiftBandError`.
  - **CA11 fecha** — a varredura parametrizada passa a cobrir as **11** mutações.
  - **CA12 fecha** — a matriz (método × exceção) da §6 está inteira: 5 métodos de
    `ShiftBandNotFoundError`, 4 de `ShiftDemandNotFoundError`, 7 de
    `AssignmentNotFoundError`, os 2 de `TimeRangeOutsidePeriodError`, os 2 de
    `DuplicateShiftBandError`, `DuplicateShiftDemandError`,
    `DuplicateAssignmentError`, `DuplicateAssignmentInBandError`, e as **três**
    linhas de `InvalidTimeRangeError` (incluindo a de `redeclare_band_break`).
    Nenhuma célula da tabela sem asserção.
  - **CA21 fecha** — **encurtar a faixa abaixo de um intervalo já declarado**: da
    faixa → `InvalidTimeRangeError`; de uma alocação →
    `InvalidAssignmentBreakError`.
  - **CA14 fecha** — a asserção de **ausência** na superfície pública da v1:
    nenhum método público altera `function_exception` numa alocação existente,
    verificada sobre o conjunto público **final** de `Schedule`/`Assignment`,
    rotulada como **estado da v1** (não irrevogabilidade).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling/domain/ -v
  uv run mypy --strict src/restaurant_hub/features/scheduling/
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
  make check
  ```
- **Commit sugerido:** `feat(scheduling): adicionar as mutações de intervalo e a cláusula de no-op [4.1/task-11]`

---

### Validação interna das Tasks (5 critérios de Task Atômica, PIPELINE §4.3)

| Task | Commitável limpa | ≤ 5 arquivos | Checks objetivos | Não mistura port + adapter | Ordem respeita dependências |
|---|---|---|---|---|---|
| 01 | sim (`make check` verde) | **12 — exceção declarada** (10 `__init__.py` vazios; conteúdo lógico = `identifiers.py` + 2 movimentos no `.importlinter`); precedente 2.1/3.1 | sim (import-linter KEPT, `check_layout.py`, teste dos 8 nomes) | N/A (Stage domain-only; nenhum port nasce aqui) | raiz da árvore |
| 02 | sim | 2 | sim (parametrização + varredura `vars`) | N/A | depende só de `shared/domain` |
| 03 | sim | 2 | sim (6 defeitos + 5 aceites-limite + tabela-verdade) | N/A | depende de 02 (`InvalidTimeRangeError`) |
| 04 | sim | 2 | sim (7 dias, 5 cenários de corte) | N/A | depende de 02 |
| 05 | sim | 4 (2 criados + 2 modificados) | sim (teto, alinhamento, **gate de grep** de CA7) | N/A | depende de 04 (`Weekday`/`DayCutoff`) |
| 06 | sim | 4 | sim (defaults, transições, CA22 parcial) | N/A | depende de 01, 02 |
| 07 | sim | 2 | sim (par não consecutivo em coleção de 3) | N/A | depende de 06 (`Assignment`, `DemandQuantity`) |
| 08 | sim | 2 | sim (4 recusas, intervalo efetivo, divergência) | N/A | depende de 03, 07 |
| 09 | sim | 2 | sim (CA10 inteiro + 3 varreduras) | N/A | depende de 05, 08 |
| 10 | sim | 3 (1 modificado + 2 criados) | sim (9 mutações, matriz, CA13, CA20) | N/A | depende de 09 |
| 11 | sim | 3 (1 criado + 2 modificados) | sim (no-op `is self`, matriz fecha) | N/A | depende de 10 |

Nenhuma Task falha os 5 critérios. A **única** exceção ao guia de ≤ 5 arquivos é
a Task 01, declarada no corpo da Task com o mesmo argumento aceito nas Tasks 01
da 2.1 e da 3.1 (scaffold de feature; 10 arquivos de 0 statements). O critério
"não mistura criação de port com adapter do mesmo port" é **vacuosamente
satisfeito**: a Stage é `domain`-only e nenhum `Protocol` de port nasce nela (os
placeholders `application/`/`adapters/` são `__init__.py` vazios).

### Matriz de rastreabilidade (concept §11 → Tasks)

| CA | Critério (resumo) | Task(s) — **negrito fecha** | Check objetivo |
|---|---|---|---|
| CA1 | `TimeRange` recusa os 6 defeitos; 5 aceites-limite explícitos | **03** | `test_time_range.py` |
| CA2 | intervalo declarado da faixa: limites e `worked_minutes` | **03** | `test_time_range.py` |
| CA3 | `overlaps` semi-aberto, adjacência não sobrepõe, simetria | **03** | `test_time_range.py` |
| CA4 | dia operacional nos 3 casos + corte `00:00` + **corte `23:00`** | **04** | `test_operational_calendar.py` |
| CA5 | faixa além do corte aceita; faixa que termina após o período aceita | 04, **10** | `test_operational_calendar.py`, `test_schedule_mutations.py` |
| CA6 | `Weekday`: nomes **e** valores; `from_date`; `from_string` erra | **04** | `test_operational_calendar.py` |
| CA7 | `DayCutoff` recusa tz-aware/sub-minuto; `default()`; **gate de sítio único** | 04, **05** | `test_operational_calendar.py` + o `rg` do concept §11 |
| CA8 | `SchedulePeriod`: `1..31`, `last_day`, `operational_days`, `contains`, fábrica | **05** | `test_schedule_period.py` |
| CA9 | `DemandQuantity` recusa `-1`; `0` e positivos aceitos | **06** | `test_demand_quantity.py` |
| CA10 | invariantes valem na **construção direta** (reidratação), par não consecutivo | 07, 08, **09** | `test_shift_demand.py`, `test_shift_band.py`, `test_schedule.py` |
| CA11 | cada uma das **11** mutações devolve nova instância com `version + 1` | 10, **11** | `test_schedule_mutations.py` (varredura) |
| CA11b | cláusula de no-op nas 4 mutações idempotentes devolve `self` | **11** | `test_schedule_breaks.py` |
| CA12 | matriz (método × exceção) da §6 inteira | 09, 10, **11** | `test_schedule.py`, `test_schedule_mutations.py` |
| CA13 | as **8** situações de política **salvam** (com rótulo de superfície em 3) | **10** | `test_schedule_policies.py` |
| CA14 | as três marcas: defaults, gravação, alternância, limpeza, **ausência** de mutação de `function_exception` | 06, **11** | `test_assignment.py`, `test_schedule_breaks.py` |
| CA15 | 4 entidades frozen + por id; 6 VOs por valor; **8 leituras** imutáveis | 03–08, **09** | testes de cada arquivo + varredura em `test_schedule.py` |
| CA16 | sítio de horas único; nenhum outro membro devolve minutos trabalhados | **09** | `test_schedule.py` (varredura) |
| CA17 | **20** exceções + raiz; conjunto público exato | **02** | `test_exceptions.py` (varredura `vars`) |
| CA18 | domínio puro `[gate]`: contratos, layout, nada em `domain/services/` | 01 (+ todas via `make check`) | import-linter + `check_layout.py` + `check_docs_claims.py` |
| CA19 | cobertura ≥ 90% por arquivo `src/` tocado `[gate]` | todas | test-gate do `make check` + `--cov-report=term-missing` |
| CA20 | as duas guardas de remoção **e** o caso sem alocação | **10** | `test_schedule_mutations.py` |
| CA21 | reagendamento preservador e as **5** restrições | 10, **11** | `test_schedule_mutations.py`, `test_schedule_breaks.py` |
| CA22 | os **8** identificadores recusam `""` e `"   "`, em cada entidade | 06, 07, 08, **09** | `test_assignment.py` … `test_schedule.py` |
| CA23 | intervalo nos dois níveis, divergência, chave `(start, end)` | 08, 09, **11** | `test_shift_band.py`, `test_schedule_breaks.py` |
| CA24 | leituras da raiz no caminho positivo (`bands_of` pelo dia operacional) | **09** | `test_schedule.py` |
| CA25 | uma vaga por registro na faixa, nos dois sentidos | 08, **10** | `test_shift_band.py`, `test_schedule_mutations.py` |

**Nenhum critério órfão:** os **26** itens do concept §11 (CA1–CA25 + CA11b) têm
Task que os fecha. **Nenhuma Task sem âncora:** cada uma das 11 fecha ou avança ao
menos um CA.

**Contratos do concept §4 → Task:**

| Contrato | Task |
|---|---|
| os 8 identificadores (`ScheduleId` … `JobFunctionId`) | 01 |
| `SchedulingError` + 20 subclasses | 02 |
| `TimeRange` (`nominal_minutes`, `worked_minutes`, `hours_key`, `overlaps`, `with_break`, `with_bounds`) | 03 |
| `Weekday`, `DayCutoff` | 04 |
| `SchedulePeriod`, `OperationalCalendar` | 05 |
| `DemandQuantity`, `Assignment` (3 marcas, 2 transições) | 06 |
| `ShiftDemand` | 07 |
| `ShiftBand` (intervalo efetivo, divergência, `rescheduled_to`) | 08 |
| `Schedule` — construção, invariantes e as **8 leituras** | 09 |
| `Schedule` — 9 mutações estruturais | 10 |
| `Schedule` — 2 mutações de intervalo + cláusula de no-op | 11 |
| consumido: `DomainError` (`shared/domain`) | 02 |
| enforcement: `scheduling-domain-purity`, `scheduling` em `bc-independence`, placeholders | 01 |

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
# Windows: $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
make check                                                                # lint+mypy+layout+import-linter+lock+docs+test-gate
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing   # cobertura por arquivo >= 90%
uv run lint-imports                                                       # 10 contratos KEPT, 0 broken
uv run python scripts/check_layout.py
uv run python scripts/check_docs_claims.py
uv run python scripts/check_technical_postexec.py "docs/stages/4.1-scheduling-domain/technical.md"
rg -n --glob 'src/restaurant_hub/features/scheduling/**/*.py' -e 'time\(\s*5\s*,\s*0' -e '"05:00"' -e 'Weekday\.MONDAY'
rg -n 'features\.(staff|identity)' src/restaurant_hub/features/scheduling/   # deve devolver nada
```

### Verificações funcionais
- [ ] A Stage é **domínio puro** (sem runtime: sem API, CLI ou job). A verificação
      "end-to-end" se satisfaz pelos **testes unitários exercitando as
      invariantes** — dia operacional pelo corte, faixa além do corte, período
      alinhado e limitado, unicidade `(start, end)`, contenção no período, ids
      internos únicos par a par, guardas de remoção, reagendamento preservador,
      intervalo nos dois níveis com divergência derivada, uma vaga por registro na
      faixa, lei da versão e cláusula de no-op. **Não inventar e2e inexistente**
      (precedente 2.1/3.1).
- [ ] As **8** situações de política **salvam** (CA13) — a prova de que nenhuma
      delas virou invariante estrutural por descuido, e de que o modo `warn` da
      4.2 continua possível.
- [ ] `src/restaurant_hub/features/scheduling/domain/services/` **não existe** — o
      `[planejado]` de `LAYOUT.md` 38 continua verdadeiro.

### Checklist de fechamento da Stage
- [ ] Todas as **11** Tasks commitadas, cada uma com `make check` verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥ 90% em cada arquivo `src/` tocado (`term-missing`)
- [ ] Auditoria de testes (subagente independente) com todos os itens "sim"
- [ ] Commit final `stage 4.1: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at`/`last_reviewed_at`,
      linha no §Histórico, e **nota datada** reconciliando as **8 divergências**
      declaradas no concept §1 (`arquivos_a_modificar` deixa de ser `[]`; as 4
      frentes novas de `arquivos_a_criar`; a 4ª entidade; a descrição humana
      superada pelo ADR 4.1.0001; `contratos_introduzidos` e
      `contratos_consumidos`; `depends_on`)
- [ ] **Nota datada em `docs/domain/scheduling/shift-scheduling.md` §2**
      registrando a glosa EN `ShiftBand` para "faixas de funcionamento"
      (divergência 8 do concept §1 — pendência declarada; precedente: a
      reconciliação de `workforce.md` com o gate da 3.x)
- [ ] ADRs `4_1_0007`–`4_1_0012` em `status: accepted` (os `0001`–`0006` já são
      `accepted` desde o gate do Step 4)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (scaffold + identifiers + importlinter)
   └─► Task 02 (20 exceções + raiz)
          ├─► Task 03 (TimeRange)                 [InvalidTimeRangeError]
          ├─► Task 04 (Weekday + DayCutoff)       [InvalidWeekdayError, InvalidDayCutoffError]
          │      └─► Task 05 (SchedulePeriod + OperationalCalendar)
          └─► Task 06 (DemandQuantity + Assignment)
                 └─► Task 07 (ShiftDemand)
                        └─► Task 08 (ShiftBand)   [+ Task 03: TimeRange]
Task 05 + Task 08 ─► Task 09 (Schedule: construção, invariantes, 8 leituras)
                        └─► Task 10 (9 mutações estruturais + lei da versão)
                               └─► Task 11 (2 mutações de intervalo + no-op + fecho de reschedule)
```

Dependências **não óbvias**, explicitadas: a Task 08 depende da **03** (usa
`TimeRange.nominal_minutes` para o teto do intervalo da alocação e `with_bounds`
em `rescheduled_to`) além da **07**; a Task 09 depende da **05**
(`calendar.is_aligned(period)` no `__post_init__`) além da **08**; a Task 11
depende da **10** porque a cláusula de no-op se aplica a `reschedule_band` e a
`declare_workload_counting`, criadas lá. Nada antes da Task 09 importa
`Schedule` — é o que torna viável a linha de corte 01–08 / 09–11 do concept §12,
**não exercida** (a medição fechou em 11, dentro do teto de 12).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Contrato `bc-independence` acusar violação inesperada ao entrar o 3º BC (import transitivo) | investigar a cadeia com `lint-imports --verbose`; import legítimo **via `shared`** não é proibido pelo contrato `independence` — corrigir só import direto entre `features`; registrar `[deviation]` em §7 |
| `scheduling-domain-purity` falhar por pacote externo ausente na lista `forbidden` | remover do contrato o pacote não instalado (mantendo os presentes), como previsto na 2.1/3.1; registrar `[deviation]` |
| `check_layout.py` reclamar de feature sem `application/`/`adapters/` | garantir os `__init__.py` placeholders da Task 01 (`REQUIRED_FEATURE_DIRS`, linha 130) |
| Varredura derivada ficar **defasada** entre commits (`make check` vermelho na Task 10/11) | a Task que cresce o conjunto atualiza a varredura **no mesmo commit** (§1, tabela de totalidades); a lista esperada vive numa constante única no topo do arquivo de teste |
| Teste fixar **precedência** entre validações coincidentes do `__post_init__` (comportamento não especificado — finding da 2.1) | um cenário inválido por teste; nunca construir um objeto que viole duas invariantes ao mesmo tempo |
| Duplicidade provada só com par **consecutivo** (a mutação "loop restrito a pares vizinhos" sobrevive) | **toda** checagem par a par é provada com par **não consecutivo** em coleção de 3 — lição do Checkpoint C da 3.1 (`3.1-staff-domain/technical.md` §7, 2026-07-29) |
| No-op de `reschedule_band` virar `DuplicateShiftBandError` espúrio | comparação de valor **antes** da checagem de duplicidade, e a checagem **exclui a própria faixa** (concept §5.16, §5.22); o teste afirma `resultado is original` |
| Aritmética de horas duplicada num segundo sítio (a fórmula reescrita em `Schedule` ou em `ShiftBand`) | CA16 é **varredura** sobre o conjunto público das 4 classes; `worked_minutes_of` **delega** a `TimeRange.worked_minutes` |
| Cobertura < 90% em `__init__.py` vazio | `__init__.py` sem statements = 100%; **não** adicionar docstring que crie linha não coberta |
| Task 10 crescer além do saudável (9 mutações num commit) | se na execução o diff passar do que um review absorve, quebrar em 10a (`enable_band`/`reschedule_band`/`disable_band`) e 10b (demanda + alocação), registrando `[deviation]` em §7 — a lei da versão fica na 10b e a varredura cresce nos dois commits; `tasks_count` sobe para 12, ainda no teto |
| Confundir `DuplicateAssignmentError` com `DuplicateAssignmentInBandError` na implementação (recusa certa, exceção errada) | as duas checagens vivem em **níveis distintos** (`ShiftDemand` × `ShiftBand`); o teste de CA25 afirma **qual** sai em cada caso |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo e divergências (§1), contratos (§4),
  invariantes (§5), mapa de erros (§6), decisões (§7), integrações (§8), riscos
  (§10), critérios (§11), medição de Tasks e linha de corte (§12).
- [`../../domain/scheduling/shift-scheduling.md`](../../domain/scheduling/shift-scheduling.md)
  — teoria canônica (`accepted`), vocabulário.
- ADRs desta Stage: [`../../adr/`](../../adr/), prefixo `4_1_` — `0001` (salvar =
  publicar + concorrência), `0002` (período, dia operacional, horas + errata),
  `0003` (oito políticas e as duas marcas), `0004` (hr lê), `0005` (fuso em
  identity), `0006` (reconciliação na leitura), `0007` (forma do `TimeRange`),
  `0008` (faixa além do corte), `0009` (raiz do agregado), `0010` (faixa
  habilitada e cardinalidade da demanda), `0011` (intervalo na faixa **e** na
  alocação), `0012` (uma vaga por registro em cada faixa).
- [`../../LAYOUT.md`](../../LAYOUT.md) §2 (linha 38 — `services/` `[planejado]`),
  §3, §7; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §4.
- `.importlinter` — `staff-domain-purity` (197–217) e `bc-independence`
  (223–228), os dois espelhos desta Stage; `scripts/check_layout.py` 130
  (`REQUIRED_FEATURE_DIRS`); `scripts/check_commit_msg.py` 74
  (`MAX_SUBJECT_LEN = 100`); `Makefile` 85 (alvo `check`).
- Precedente vivo: [`../3.1-staff-domain/technical.md`](../3.1-staff-domain/technical.md)
  (mesma camada `domain`; estrutura de Tasks, contratos de import, placeholders, e
  a §7 com a validação par a par e a idempotência de transição).
- Precedentes de código:
  `src/restaurant_hub/features/staff/domain/value_objects/unavailability_period.py`
  31–36 (par de `datetime` ingênuos; tz-aware antes de comparar);
  `src/restaurant_hub/features/staff/domain/entities/employee.py` 93–98 (loop par
  a par sobre a coleção inteira);
  `tests/unit/features/identity/domain/test_exceptions.py` 45–56 (varredura
  derivada com `vars(...)`).
- Skills: `task-ordering-hex`, `ddd-tactical-patterns`, `hex-arch-python`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`** — alterações fora dos marcadores `BEGIN/END: post-execution`
> são rejeitadas via `scripts/check_technical_postexec.py`. O frontmatter
> `updated_at` **não muda** com edições aqui — cada entrada carrega data + autor.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4 algo não
> previsto no Concept ou neste Technical, **pause** e levante a pergunta para o
> humano com 2–4 opções e uma marcada como **recomendada** + razão. Apenas após a
> decisão, registre a entrada. Na dúvida sobre se algo é "pequeno o suficiente",
> **pergunte**.

- `[decision]` — algo não previsto foi decidido (pergunta + opções + razão).
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo inclui
  "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

<!-- END: post-execution -->

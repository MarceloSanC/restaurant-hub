---
title: Technical — Domínio de equipe
description: Plano de execução da Stage 3.1 — lista ordenada de Tasks (1 Task = 1 commit) para o domínio do BC staff
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, staff-domain, equipe, funcionario, funcao, jornada, indisponibilidade]
status: done
created_at: 2026-07-27
updated_at: 2026-07-29
stage_id: 3.1-staff-domain
stage_title: Domínio de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [2.5-email-invite]
concept_ref: ./concept.md
issue_id: 32
branch: feat/32-3-1-staff-domain
tasks_count: 7
---

# Technical — Stage 3.1 — Domínio de equipe

> **Como usar (code assistant):** ler §1; executar Tasks em ordem (§2), 1 Task =
> 1 commit; `make check` verde antes de todo commit; registrar desvios em §7.
> Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(<scope>): <descrição> [3.1/task-NN]`, escopo `staff`.

## 1. Contexto e estratégia de execução

### Resumo
Primeiro código do BC `staff` (camada `domain` pura, sem I/O). Modela
`Employee`/`JobFunction` (entidades **frozen**, duas raízes de agregado que se
referenciam só por id), os VOs `FixedSchedule`/`OnDemand` (união
`WorkloadProfile`), `DayPeriod`/`ShiftPreference`, `UnavailabilityPeriod` e os
identificadores tipados próprios do BC, com a hierarquia
`StaffError(DomainError)` e as invariantes canônicas do workforce garantidas
**por construção** e por testes unitários sem I/O. Ativa também o enforcement
estrutural: contrato de pureza de `staff.domain` e contrato de **independência**
entre os BCs `identity` × `staff` no `.importlinter`, mais os
pacotes-placeholder `features/staff/{application,adapters}/` exigidos por
`scripts/check_layout.py`. Ver [`concept.md`](./concept.md).

### Estratégia
**Inside-out (TDD), bottom-up** (skill `task-ordering-hex`): a Stage é
**domain-only**, então só o passo 1 da ordem default da skill se aplica —
dentro dele, tipos-folha primeiro (identificadores, exceções, VOs), depois as
entidades que os compõem (`JobFunction`, por fim `Employee`, que agrega os VOs
todos). Cada Task cria o(s) módulo(s) **junto com seus testes unitários** no
mesmo commit e deixa `make check` verde. Não há application/adapters/wiring
nesta Stage (Stages 3.2–3.4); os placeholders da Task 01 existem só para o
`check_layout.py`. A ordem respeita as dependências de import: `Employee`
(Task 07) depende de identificadores, exceções, `WorkloadProfile`,
`ShiftPreference` e `UnavailabilityPeriod` — todos criados antes; **não**
depende de `JobFunction` (referência só por `JobFunctionId`).

### Pré-condições
- `2.5-email-invite` em `done` e mergeada em `develop` (roadmap: Stages de
  backend do Step 2 fechadas).
- Concept desta Stage em `status: done` (commit `stage 3.1: conceptual
  approved`).
- Branch `feat/32-3-1-staff-domain` ativa; `.venv` instalado (`make setup`).

### Premissas técnicas
- Python 3.12 (`StrEnum`, `NewType`, `dataclasses`, `Decimal`).
- Domínio importa **só** stdlib + `shared/domain` (LAYOUT §3); `StaffError`
  herda de `shared.domain.exceptions.base.DomainError`. **Nenhum import de
  `features.identity`** (contrato de independência, Task 01).
- Datetimes de indisponibilidade são **ingênuos** (sem tzinfo) — ADR 3.1.0005;
  tz-aware é rejeitado na construção.
- `make check` = ruff + mypy strict + `check_layout.py` + import-linter +
  lock-check + docs-check + test-gate (cobertura ≥ 90%). Rodar via PowerShell:
  `$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check`.
- Padrão de entidade da 2.1: `@dataclass(frozen=True, eq=False)`, igualdade e
  hash por id (`__eq__` devolve `NotImplemented` para tipo alheio), transições
  via `dataclasses.replace` revalidadas pelo `__post_init__`.

### Estrutura de pastas afetada

```
src/restaurant_hub/features/staff/
├── __init__.py
├── application/__init__.py          # placeholder vazio (check_layout REQUIRED_FEATURE_DIRS)
├── adapters/__init__.py             # placeholder vazio (idem)
└── domain/
    ├── __init__.py
    ├── entities/{__init__,employee,job_function}.py
    ├── value_objects/{__init__,identifiers,workload_profile,
    │                  shift_preference,unavailability_period}.py
    └── exceptions/{__init__,errors}.py
tests/unit/features/staff/
├── __init__.py
└── domain/{__init__,test_identifiers,test_exceptions,test_workload_profile,
             test_shift_preference,test_unavailability_period,
             test_job_function,test_employee}.py
.importlinter                        # + pureza staff.domain + independence identity×staff
```

## 2. Tasks

> 7 Tasks. `__init__.py` são vazios (import por caminho absoluto, LAYOUT §7).
> Escopo do commit = `staff` (ASCII/kebab). Baseline de toda Task: `make check`
> verde (inclui test-gate de cobertura ≥ 90%).

### Task 01 — Scaffold da feature, identificadores tipados e contratos import-linter

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/application/__init__.py` (vazio, placeholder)
  - `src/restaurant_hub/features/staff/adapters/__init__.py` (vazio, placeholder)
  - `src/restaurant_hub/features/staff/domain/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/domain/entities/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/domain/value_objects/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/domain/exceptions/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/domain/value_objects/identifiers.py`
  - `tests/unit/features/staff/__init__.py` (vazio)
  - `tests/unit/features/staff/domain/__init__.py` (vazio)
  - `tests/unit/features/staff/domain/test_identifiers.py`
- **Arquivos a modificar:** `.importlinter`
- **O que fazer:** criar a árvore de pacotes da feature `staff` (incluindo os
  placeholders vazios `application/` e `adapters/`, exigidos por
  `check_layout.py` — `REQUIRED_FEATURE_DIRS`). Em `identifiers.py`, definir
  `EmployeeId`, `JobFunctionId`, `TenantId`, `UnitId` como `NewType(..., str)`
  **próprios do BC** (concept §7 — não importar tipos de identity; ids
  atravessam a fronteira como strings opacas). Em `.importlinter`:
  1. adicionar contrato `staff-domain-purity` (`type = forbidden`,
     `source_modules = restaurant_hub.features.staff.domain`) espelhando o
     `identity-domain-purity`: proibir
     `restaurant_hub.features.staff.application`,
     `restaurant_hub.features.staff.adapters`,
     `restaurant_hub.shared.application`,
     `restaurant_hub.shared.infrastructure` e os frameworks/boundary
     (`fastapi`, `starlette`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg`,
     `pydantic`, `pydantic_settings`, `httpx`, `argon2`, `jwt`). **Não**
     proibir `restaurant_hub.features` (auto-proibiria imports internos de
     staff) nem `restaurant_hub.shared.domain` (dependência legítima:
     `StaffError` herda de `DomainError`);
  2. ativar o contrato de **independência entre BCs** planejado no cabeçalho
     do arquivo ("quando o 2º BC existir"): `type = independence` com
     `modules = restaurant_hub.features.identity` e
     `restaurant_hub.features.staff`;
  3. atualizar o comentário de cabeçalho do `.importlinter` (a nota
     "independence — quando o 2º BC existir" deixa de ser futura).
- **Detalhes técnicos:** `NewType` sobre `str`; sem lógica de runtime em
  `identifiers.py` (a validação de não-vazio é imposta **nas entidades**,
  concept §4 — Tasks 06/07). O teste cobre o módulo importando e afirmando o
  passthrough do `NewType` (`EmployeeId("e1") == "e1"`) e que os quatro nomes
  existem.
- **Critério de aceite:** `make check` verde (layout-check reconhece os 3
  diretórios da feature; import-linter aceita e mantém os 2 contratos novos —
  saída lista os contratos como KEPT); `test_identifiers.py` passa.
- **Nota de atomicidade (exceção consciente, PIPELINE §4.3):** a Task estoura o
  guia de ≤ 5 arquivos (11 criados + `.importlinter`) por ser o scaffold da
  feature — 9 são `__init__.py` **vazios** (0 statements); o conteúdo lógico é
  só `identifiers.py` + os contratos de import (mínimos e atados ao scaffold
  para manter o commit não-vazio e `make check` verde). Mesma exceção declarada
  na Task 01 da 2.1.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): criar scaffold, identificadores e contratos de import [3.1/task-01]`

---

### Task 02 — Exceções de domínio do BC staff

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/domain/exceptions/errors.py`
  - `tests/unit/features/staff/domain/test_exceptions.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** definir `StaffError(DomainError)` (base do BC, importando
  `DomainError` de `restaurant_hub.shared.domain.exceptions.base`) e as 8
  subclasses do concept §4/§6: `InvalidIdentifierError`, `InvalidNameError`,
  `InvalidWeeklyHoursError`, `EmptyShiftPreferenceError`,
  `EmptyJobFunctionsError`, `InvalidUnavailabilityPeriodError`,
  `OverlappingUnavailabilityError`, `UnavailabilityNotFoundError`. Cada uma com
  docstring PT curta; construtor pode aceitar um valor de contexto e montar a
  mensagem PT (padrão `errors.py` de identity).
- **Detalhes técnicos:** hierarquia — todas subclasses de `StaffError`, que é
  subclasse de `DomainError` (o error handler HTTP da 2.4 converte a hierarquia
  em 4xx; aqui só se garante a herança). Sem estado além da mensagem.
- **Critério de aceite:** `test_exceptions.py` cobre: `StaffError` é
  `DomainError`; **cada** subclasse é `StaffError`; a mensagem é preservada ao
  levantar (`pytest.raises(..., match=...)`).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): adicionar exceções de domínio [3.1/task-02]`

---

### Task 03 — VOs de perfil de jornada (`FixedSchedule` / `OnDemand` / `WorkloadProfile`)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/domain/value_objects/workload_profile.py`
  - `tests/unit/features/staff/domain/test_workload_profile.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True)` `FixedSchedule` com
  `weekly_hours: Decimal`; no `__post_init__`, rejeitar não-positivo, NaN e
  infinito com `InvalidWeeklyHoursError` (aceitar fracionário, ex.:
  `Decimal("22.5")`). `@dataclass(frozen=True)` `OnDemand` **sem campos**
  (docstring: não carrega carga nem valor monetário — kickoff #11). Type alias
  `WorkloadProfile = FixedSchedule | OnDemand` no mesmo módulo.
- **Detalhes técnicos:** validação de finitude via `Decimal.is_finite()`
  (cobre NaN, sNaN e ±Infinity) **antes** da comparação `> 0` (comparar NaN
  levanta `InvalidOperation` — ordem importa); "exatamente um perfil" é
  garantia **estática** da união de tipos (mypy strict), não checagem de
  runtime (concept §11). VOs frozen ⇒ igualdade por valor e hasháveis.
- **Critério de aceite:** `test_workload_profile.py` cobre: carga positiva
  inteira e fracionária aceita; `0`, negativo, `Decimal("NaN")` e
  `Decimal("Infinity")` rejeitados com `InvalidWeeklyHoursError`; `OnDemand`
  não expõe carga nem campo monetário (ex.: `dataclasses.fields(OnDemand) ==
  ()`); igualdade por valor dos dois VOs.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): adicionar perfil de jornada fixa e sob demanda [3.1/task-03]`

---

### Task 04 — VOs `DayPeriod` e `ShiftPreference`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/domain/value_objects/shift_preference.py`
  - `tests/unit/features/staff/domain/test_shift_preference.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** no mesmo módulo (ver §7, decisão de colocação):
  `DayPeriod(StrEnum)` fechado = `{MORNING, AFTERNOON, NIGHT, OVERNIGHT}` com
  docstring glosando o vocabulário PT (manhã, tarde, noite, madrugada —
  kickoff #6; mitigação do risco `OVERNIGHT` = madrugada, concept §10).
  `@dataclass(frozen=True)` `ShiftPreference` com
  `periods: frozenset[DayPeriod]`; no `__post_init__`, conjunto vazio →
  `EmptyShiftPreferenceError` (ADR 3.1.0004).
- **Detalhes técnicos:** enum com 4 membros exatos (teste de conjunto
  fechado); `ShiftPreference` aceita qualquer subconjunto não-vazio (1 a 4
  períodos). A semântica "None = sem preferência" vive no `Employee`
  (Task 07), não aqui.
- **Critério de aceite:** `test_shift_preference.py` cobre: os 4 membros e só
  eles; construção com 1, 2 e 4 períodos aceita; conjunto vazio →
  `EmptyShiftPreferenceError`; igualdade por valor (mesmo conjunto ⇒ igual);
  hashável.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): adicionar DayPeriod e ShiftPreference [3.1/task-04]`

---

### Task 05 — VO `UnavailabilityPeriod` (intervalo semi-aberto, naive)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/domain/value_objects/unavailability_period.py`
  - `tests/unit/features/staff/domain/test_unavailability_period.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True)` `UnavailabilityPeriod` com
  `start: datetime` e `end: datetime`. No `__post_init__`: qualquer um dos dois
  com `tzinfo is not None` → `InvalidUnavailabilityPeriodError`
  (ADR 3.1.0005 — wall-clock do fuso da unidade, fixado em docstring);
  `start >= end` → `InvalidUnavailabilityPeriodError`. Método
  `overlaps(self, other: "UnavailabilityPeriod") -> bool` com a semântica
  semi-aberta `[start, end)`: `self.start < other.end and other.start <
  self.end` — adjacentes (fim == início) **não** conflitam.
- **Detalhes técnicos:** validar tz-aware **antes** de comparar `start < end`
  (comparação naive×naive é sempre segura por construção). Frozen ⇒ igualdade
  por valor e hashável (a remoção por valor na Task 07 depende disso).
- **Critério de aceite:** `test_unavailability_period.py` cobre: construção
  válida; `start == end` e `start > end` rejeitados; tz-aware em `start`, em
  `end` e em ambos rejeitado; **tabela-verdade do `overlaps`** — sobreposição
  parcial (dos dois lados), continência total, idênticos, disjuntos e
  **adjacentes (não sobrepõem)**, incluindo a simetria (`a.overlaps(b) ==
  b.overlaps(a)`); igualdade por valor.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): adicionar UnavailabilityPeriod semiaberto [3.1/task-05]`

---

### Task 06 — Entidade `JobFunction` (função customizável com ciclo de vida)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/domain/entities/job_function.py`
  - `tests/unit/features/staff/domain/test_job_function.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True, eq=False)` `JobFunction` com
  `id: JobFunctionId`, `tenant_id: TenantId`, `name: str`,
  `active: bool = True`. `__post_init__` valida: `id`/`tenant_id` não-vazios
  (predicado `.strip()` — vazio ou só-whitespace → `InvalidIdentifierError`);
  `name` idem → `InvalidNameError`, armazenado **verbatim** (sem trim/case —
  ADR 3.1.0002). Igualdade/hash por id (`__eq__` devolve `NotImplemented` para
  tipo alheio; `__hash__` por id). Métodos de transição devolvendo **nova
  instância** via `dataclasses.replace` (revalidada pelo `__post_init__`):
  `rename(name) -> JobFunction`, `deactivate() -> JobFunction`
  (`active=False`), `reactivate() -> JobFunction` (`active=True`) —
  ADR 3.1.0003.
- **Detalhes técnicos:** escopo **tenant** (função é do restaurante, não da
  unidade — workforce §3.2); unicidade de nome no tenant e bloqueio de
  atribuição de função inativa são **declarados** mas impostos na 3.2/3.3
  (concept §5.3/§5.10) — nada disso é validado aqui. `deactivate`/`reactivate`
  são idempotentes no valor (não levantam erro se já no estado-alvo).
- **Critério de aceite:** `test_job_function.py` cobre: construção válida
  (`active=True` default); `id`/`tenant_id` vazio **e** só-whitespace →
  `InvalidIdentifierError` (cada campo); `name` vazio/só-whitespace →
  `InvalidNameError` na construção **e** no `rename`; `name` preservado
  verbatim (`"  Cozinheiro "` inalterado) na construção e no `rename`;
  `deactivate()`/`reactivate()` alternam `active` devolvendo nova instância
  (original imutado); atribuição direta de atributo falha
  (`FrozenInstanceError`); igualdade por id (mesmo id ⇒ igual com `name`
  diferente; id diferente ⇒ diferente; hash consistente).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): adicionar entidade JobFunction com ciclo de vida [3.1/task-06]`

---

### Task 07 — Entidade `Employee` (agregado com jornada, preferência, funções e indisponibilidades)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/domain/entities/employee.py`
  - `tests/unit/features/staff/domain/test_employee.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True, eq=False)` `Employee` com
  `id: EmployeeId`, `tenant_id: TenantId`, `unit_id: UnitId`, `name: str`,
  `workload_profile: WorkloadProfile`,
  `shift_preference: ShiftPreference | None`,
  `job_function_ids: frozenset[JobFunctionId]`,
  `unavailabilities: tuple[UnavailabilityPeriod, ...] = ()`. `__post_init__`
  valida, em **todos** os caminhos de construção (inclusive reidratação futura
  da 3.3): ids não-vazios (`InvalidIdentifierError`), `name` não-vazio
  verbatim (`InvalidNameError`), `job_function_ids` não-vazio
  (`EmptyJobFunctionsError` — ADR 3.1.0006) e **não-sobreposição par a par**
  da coleção inicial de indisponibilidades
  (`OverlappingUnavailabilityError`). Igualdade/hash por id (padrão Task 06).
  Métodos de transição via `dataclasses.replace` (nova instância revalidada):
  - `rename(name) -> Employee`;
  - `assign_job_functions(ids: frozenset[JobFunctionId]) -> Employee` —
    substitui o conjunto; vazio → `EmptyJobFunctionsError`;
  - `change_workload_profile(profile: WorkloadProfile) -> Employee`;
  - `declare_shift_preference(preference: ShiftPreference | None) -> Employee`
    — `None` limpa a preferência;
  - `add_unavailability(period: UnavailabilityPeriod) -> Employee` — valida
    contra **todos** os existentes com `overlaps`; conflito →
    `OverlappingUnavailabilityError`; adjacente é aceito;
  - `remove_unavailability(period: UnavailabilityPeriod) -> Employee` —
    remoção por igualdade de valor; inexistente →
    `UnavailabilityNotFoundError`.
- **Detalhes técnicos:** `Employee` **não** importa `JobFunction` (referência
  entre agregados só por id — concept §5.11); validade referencial e bloqueio
  de função inativa são enforcement da 3.2/3.3. A consistência
  `unit_id` ↔ `tenant_id` é premissa da borda (concept §3) — aqui ambos são
  opacos não-vazios. **Precedência entre validações coincidentes do
  `__post_init__` não é especificada** (finding herdado da 2.1) — os testes
  não devem fixar qual exceção vence quando duas invariantes são violadas ao
  mesmo tempo.
- **Critério de aceite:** `test_employee.py` cobre: construção válida com cada
  perfil (`FixedSchedule` e `OnDemand`), com `shift_preference=None` e com
  preferência declarada **em ambos os perfis**; cada id vazio/só-whitespace →
  `InvalidIdentifierError`; `name` inválido → `InvalidNameError`
  (construção e `rename`; verbatim preservado); `job_function_ids` vazio →
  `EmptyJobFunctionsError` na construção **e** em `assign_job_functions`, com
  1 e com N funções aceitos; construção com coleção inicial **sobreposta** →
  `OverlappingUnavailabilityError` (caminho de reidratação) e com períodos
  adjacentes aceita; `add_unavailability` rejeita sobreposição
  (parcial/total), aceita adjacente e devolve nova instância (original
  imutado); `remove_unavailability` remove por valor e inexistente →
  `UnavailabilityNotFoundError`; `declare_shift_preference(pref)` **declara**
  a preferência (não-None) e **substitui** uma preferência existente por
  outra; `declare_shift_preference(None)` limpa;
  `change_workload_profile` troca fixa↔sob demanda; frozen
  (`FrozenInstanceError` em atribuição direta); igualdade por id.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(staff): adicionar entidade Employee com invariantes [3.1/task-07]`

---

### Matriz de rastreabilidade (concept §4/§11 → Tasks)

**Critérios de aceite do concept §11:**

| # | Critério (resumo) | Task(s) | Check objetivo |
|---|---|---|---|
| 1 | `FixedSchedule` aceita carga positiva/fracionária; rejeita ≤ 0, NaN, infinito | 03 | `test_workload_profile.py` |
| 2 | `OnDemand` sem carga/campo monetário; união garantida por mypy strict | 03 | `test_workload_profile.py` + mypy no `make check` |
| 3 | `ShiftPreference` rejeita vazio, aceita subconjuntos; `Employee` aceita `None` e ambos os perfis declaram | 04, 07 | `test_shift_preference.py`, `test_employee.py` |
| 4 | `UnavailabilityPeriod` rejeita `start >= end` e tz-aware; tabela-verdade semi-aberta do `overlaps` | 05 | `test_unavailability_period.py` |
| 5 | `add_unavailability` rejeita sobreposição/aceita adjacente; construção sobreposta rejeitada; `remove` inexistente erra | 07 | `test_employee.py` |
| 6 | Cada identificador vazio/só-whitespace → `InvalidIdentifierError` | 06, 07 | `test_job_function.py`, `test_employee.py` |
| 7 | `deactivate`/`reactivate` alternam; nomes inválidos rejeitados, válidos verbatim (construção e `rename`) | 06, 07 | `test_job_function.py`, `test_employee.py` |
| 8 | Entidades: identidade + frozen + transição devolve nova instância; VOs por valor | 03–07 | testes de igualdade/frozen em cada arquivo |
| 9 | Exceções herdam de `StaffError` → `DomainError` | 02 | `test_exceptions.py` |
| 10 | Domínio sem I/O/frameworks/outros BCs; contratos novos no import-linter | 01 (+ todas via `make check`) | import-linter + `check_layout.py` |
| 11 | Cobertura ≥ 90% por arquivo `src/` tocado | todas | test-gate do `make check` + term-missing no gate de saída |
| 12 | Conjunto de funções vazio rejeitado (construção e `assign_job_functions`); 1 e N aceitos | 07 | `test_employee.py` |

**Contratos do concept §4:**

| Contrato | Task |
|---|---|
| `EmployeeId`, `JobFunctionId`, `TenantId`, `UnitId` | 01 |
| Exceções `StaffError` + 8 subclasses | 02 |
| `FixedSchedule`, `OnDemand`, `WorkloadProfile` | 03 |
| `DayPeriod`, `ShiftPreference` | 04 |
| `UnavailabilityPeriod` (+ `overlaps`) | 05 |
| `JobFunction` (+ `rename`/`deactivate`/`reactivate`) | 06 |
| `Employee` (+ 6 métodos de transição) | 07 |
| Consumido: `DomainError` (shared) | 02 |

Nenhuma Task sem âncora no concept; nenhum critério/contrato órfão.

## 3. Gate de saída da Stage

### Verificações automatizadas
```powershell
$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
make check                                                   # lint+mypy+layout+import-linter+lock+docs+test-gate
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing  # cobertura por arquivo ≥ 90%
uv run python scripts/check_technical_postexec.py "docs/stages/3.1-staff-domain/technical.md"
```

### Verificações funcionais
- [ ] Stage é **domínio puro** (sem runtime: sem API/CLI/job). A verificação
      "end-to-end" se satisfaz pelos **testes unitários exercitando as
      invariantes** (perfil exclusivo, carga positiva, preferência não-vazia,
      não-sobreposição semi-aberta em construção e em `add_unavailability`,
      conjunto de funções ≥ 1, nomes verbatim, ciclo de vida da função) — não
      há entrypoint a rodar. Não inventar e2e inexistente (precedente 2.1).

### Checklist de fechamento da Stage
- [ ] Todas as 7 Tasks commitadas, cada uma com `make check` verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥ 90% em cada arquivo `src/` tocado (term-missing)
- [ ] Auditoria de testes (subagente independente) com todos os itens "sim"
- [ ] Commit final `stage 3.1: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at`/`last_reviewed_at`,
      linha no §Histórico, e **nota datada** reconciliando o file-scope do
      bloco 3.1 (`.importlinter`/placeholders/`identifiers.py`/
      `arquivos_a_modificar: []` — expansão declarada no concept §7, mesmo
      padrão da 2.1)
- [ ] ADRs `3_1_0001`–`3_1_0006` em `status: accepted`
- [ ] `concept.md` não precisa retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (scaffold+identifiers+importlinter)
   └─► Task 02 (exceptions)
          ├─► Task 03 (FixedSchedule/OnDemand)      [usa InvalidWeeklyHoursError]
          ├─► Task 04 (DayPeriod/ShiftPreference)   [usa EmptyShiftPreferenceError]
          ├─► Task 05 (UnavailabilityPeriod)        [usa InvalidUnavailabilityPeriodError]
          └─► Task 06 (JobFunction)                 [usa identifiers + InvalidIdentifierError/InvalidNameError]
Task 03,04,05 ─► Task 07 (Employee)  [usa identifiers, exceções e os 3 VOs;
                                      NÃO depende da Task 06 — referência a
                                      JobFunction é só por id]
```

Task 06 antes da 07 por convenção (entidade mais simples primeiro), não por
dependência de import.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Contrato `independence` acusar violação inesperada (import transitivo entre BCs) | investigar a cadeia com `lint-imports --show-timings`; se for import legítimo via `shared`, o contrato independence não o proíbe — corrigir só import direto entre features; registrar `[deviation]` em §7 |
| import-linter falhar por pacote externo ausente na lista forbidden | remover o pacote não instalado (mantendo os presentes), como previsto na 2.1; registrar `[deviation]` §7 |
| `check_layout.py` reclamar de feature sem `application/`/`adapters/` | garantir os `__init__.py` placeholders (Task 01) |
| Comparação `Decimal("NaN") > 0` levantar `InvalidOperation` no `__post_init__` | validar `is_finite()` **antes** da comparação (ordem já fixada na Task 03) |
| Cobertura < 90% em `__init__.py` vazio | `__init__.py` sem statements = 100%; não adicionar docstring que crie linha não-coberta |
| Testes fixarem precedência de validações coincidentes do `__post_init__` (comportamento não especificado — finding 2.1) | testar cada invariante isoladamente (um cenário inválido por teste) |

## 6. Referências

- [`./concept.md`](./concept.md) — contratos (§4), invariantes (§5), casos de
  erro (§6), decisões (§7), critérios (§11).
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) —
  teoria canônica (accepted).
- ADRs: [`3_1_0001`](../../adr/3_1_0001-workforce-gate-modeling-decisions.md),
  [`3_1_0002`](../../adr/3_1_0002-minimal-employee-record-attributes.md),
  [`3_1_0003`](../../adr/3_1_0003-job-function-lifecycle-soft-state.md),
  [`3_1_0004`](../../adr/3_1_0004-shift-preference-scope-and-cardinality.md),
  [`3_1_0005`](../../adr/3_1_0005-naive-wall-clock-unavailability-datetimes.md),
  [`3_1_0006`](../../adr/3_1_0006-employee-function-set-cardinality.md).
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7;
  [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §1, §4.
- Precedente: [`../2.1-identity-domain/technical.md`](../2.1-identity-domain/technical.md)
  (estrutura de Tasks de camada domain, contratos import-linter, placeholders).
- Skills: `ddd-tactical-patterns`, `hex-arch-python`, `task-ordering-hex`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão. Apenas após a decisão, registre a entrada.
> Na dúvida sobre se algo é "pequeno o suficiente", **pergunte**.

- `[decision]` — algo não previsto foi decidido (pergunta + opções + razão),
  ou detalhe trivial reversível-barato decidido na autoria/execução.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-07-29 — [decision] Task 04 — colocação de `DayPeriod` — Claude (autor do technical, Fase 3B)
**Contexto:** o concept §4 declara `DayPeriod` como contrato próprio, mas o
file-scope do roadmap só lista `{workload_profile,shift_preference,unavailability_period}.py`.
**Pergunta:** módulo próprio (`day_period.py`) ou co-locado em `shift_preference.py`?
**Opções:**
- A — módulo próprio, 1 VO por arquivo (padrão Role/Permission da 2.1)
- B — co-locado em `shift_preference.py` ✅ recomendada
**Decisão:** B.
**Razão:** `DayPeriod` só existe como elemento de `ShiftPreference` nesta
Stage; co-locar mantém o file-scope do roadmap literal (menos uma expansão a
reconciliar) sem custo de import — trivial e reversível (mover módulo depois
não muda contrato). Nenhum consumidor externo até o Step 5.

### 2026-07-29 — [decision] Task 06 — transições repetidas de `JobFunction` são idempotentes — Claude (autor do technical, Fase 3B)
**Contexto:** o ADR 3.1.0003 delega explicitamente: "idempotency or error on
repeated transition is a technical.md detail".
**Pergunta:** `deactivate()` sobre função já inativa (e `reactivate()` sobre
ativa) devolve instância equivalente ou levanta erro?
**Opções:**
- A — levantar erro de estado (ex.: `InvalidLifecycleTransitionError`)
- B — idempotente no valor: devolve instância com o estado-alvo, sem erro ✅ recomendada
**Decisão:** B.
**Razão:** o concept §4/§6 não declara exceção de ciclo de vida (a opção A
exigiria contrato novo → regressão de concept); idempotência é o comportamento
seguro para retry/reidratação e reversível barato — endurecer para erro depois
é evolução aditiva na 3.2 se um use case precisar distinguir.

### 2026-07-29 — [decision] Checkpoint B — disposição dos 3 findings minor — Sessão mestra + Claude (autor, Fase 3B)
**Contexto:** o revisor de contexto zerado do Checkpoint B **aprovou** o
technical com 3 findings minor, cuja disposição é registrada aqui antes do
commit reservado `stage 3.1: technical approved`.
**Disposições:**
- **F1** (§7 pré-preenchida na Fase 3B: legenda estendida + 2 entradas
  datadas de autoria) — **aceito**. Disposição do Checkpoint B: entradas de
  autoria da Fase 3B aceitas explicitamente pela sessão mestra — conteúdo
  transparente e auditável; legenda estendida mantida. Conteúdo não movido.
- **F2** (critério de aceite da Task 07 não exercitava
  `declare_shift_preference` com valor não-None — mutação "devolver sempre
  None" sobreviveria) — **corrigido**: cenário "declara a preferência
  (não-None) e substitui uma preferência existente por outra" adicionado ao
  critério de aceite da Task 07.
- **F3** (frontmatter ainda `status: draft`) — **corrigido**: flip para
  `done` (com `updated_at: 2026-07-29`) aplicado no commit reservado
  `stage 3.1: technical approved`, forma do gate no precedente da Stage
  (commit `8929ef8` do concept: o commit reservado carrega exatamente o flip).

<!-- END: post-execution -->

---
title: Technical — Use cases de equipe
description: Plano de execução da Stage 3.2 — 13 Tasks ordenadas (1 Task = 1 commit) para a camada application do BC staff, incluindo o ajuste de ciclo de vida das duas entidades da 3.1
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, staff-application, use-case, port-out, dto, fakes, leis-do-port, ciclo-de-vida]
status: done
created_at: 2026-08-08
updated_at: 2026-08-08
stage_id: 3.2-staff-application
stage_title: Use cases de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [3.1-staff-domain]
concept_ref: ./concept.md
issue_id: 35
branch: feat/35-3-2-staff-application
tasks_count: 13
---

# Technical — Stage 3.2 — Use cases de equipe

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(staff): <descrição em PT-BR> [3.2/task-NN]` + `Refs #35`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 3.2: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/35-3-2-staff-application` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

Camada `application` do BC `staff`: dois ports-out (`Protocol`) com **doze leis
nomeadas** (L-JF1…L-JF5, L-E1…L-E7), os DTOs de fronteira (14 commands, 2
queries, 2 results), nove erros de aplicação ancorados em `StaffError`, e os
**16 use cases** de função de trabalho, funcionário (CRUD + edição + ciclo de
vida) e cópia entre unidades. Nenhum I/O: tudo é exercitado por um **par
acoplado de fakes sobre um store único**, incluindo um fluxo ponta-a-ponta que
cruza duas unidades do mesmo tenant. A Stage também **modifica o domínio já
mergeado da 3.1** — `JobFunction` perde `active`/`deactivate()`/`reactivate()`
(ADR 3.2.0005) e `Employee` ganha `active` com as duas transições
(ADR 3.2.0006) — expansão de camada-alvo declarada no concept §1/§7. O contrato
`staff-application-purity` do import-linter entra junto, para que "application
não importa adapters" seja provado por gate e não por convenção.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`), com três restrições próprias
desta Stage:

1. **A forma final das entidades vem primeiro.** As Tasks 01 e 02 mudam o
   domínio da 3.1. Todo o resto da Stage (DTOs, results, fakes, use cases,
   leis L-JF3/L-E6/L-E7) depende de `JobFunction` **sem** estado e de
   `Employee` **com** estado. Fazê-las por último obrigaria a reescrever
   metade dos testes da Stage; fazê-las primeiro custa dois commits pequenos e
   isolados, cada um com os seus testes ajustados no mesmo commit.
2. **Gate de cobertura global (`fail_under = 90`) por commit.** Um commit que
   adicione arquivo de `src/` sem nada que o importe derruba a média e reprova
   o próprio commit. Por isso toda Task fecha um ciclo completo — código +
   teste que o exercita.
3. **Port e fake no mesmo commit (Task 05).** A `task-ordering-hex` admite as
   duas formas — "port out (`Protocol`) + use case + in-memory fake … **same
   commit or consecutive Tasks**" — e aqui a escolha é o mesmo commit por uma
   razão específica: a **conformidade fake↔`Protocol`** só tem gate quando os
   dois existem juntos (`_conforms: <Port> = <Fake>(…)` checado pelo
   `mypy src/ tests/fakes/`). Um commit só com os dois `Protocol` publicaria uma
   fronteira sem nenhuma verificação de que ela é implementável — e é
   exatamente essa fronteira que a 3.3 herda. **Não é argumento de cobertura:**
   módulo de `Protocol` com corpo `...` mede 100% no import (os 10 ports de
   identity somam 68 statements a 100%), e dois módulos a 0% não moveriam a
   média global. A regra dura que continua valendo — *não misturar port com o
   **adapter real** do port* — é respeitada: os adapters reais são da 3.3.

Ordem e razão:

1. **Domínio da 3.1 ajustado** (Tasks 01–02) — a forma das entidades é
   pré-requisito de tudo.
2. **Erros + contrato de pureza** (Task 03) — folha do grafo; todo o resto os
   levanta, e o contrato do import-linter precisa existir antes do primeiro
   módulo da camada.
3. **DTOs** (Task 04) — fronteira de dados; os results são o alvo das asserções
   "campo a campo" de §11.
4. **Ports + par de fakes** (Task 05) e **as doze leis** (Task 06). O par de
   fakes **não é detalhe de teste**: é a fixture que a 3.3 parametriza no teste
   de contrato (concept §4), e é o único lugar onde L-JF3 e L-E4 — que falam de
   dados do **outro** agregado — são verificáveis. Por isso as leis ganham
   Task própria, revisável isolada do commit que cria os fakes.
5. **Use cases** (Tasks 07–13), agrupados por família e por transição, do mais
   simples ao mais composto, cada grupo com a sua matriz de erros e o seu
   cenário de precedência (§5.16 do concept).
6. **Cópia + fluxo ponta-a-ponta + guardas mecânicas** (Task 13), que só fazem
   sentido com os 15 use cases anteriores no lugar.

### Desvios declarados vs. o agrupamento previsto no concept §12

O concept §12 estimou 13 Tasks com um agrupamento indicativo. Este plano
mantém **as mesmas 13 Tasks** e as mesmas fronteiras de escopo, com dois
remanejamentos declarados aqui para não decidir em silêncio:

- **Ports migraram para a Task dos fakes** (concept: Tasks 5 e 6 separadas;
  aqui: Task 05 = ports + store + dois fakes). Razão: a conformidade
  fake↔`Protocol`, que é o **único gate** sobre a fronteira que a 3.3 vai
  implementar, só existe quando os dois estão no mesmo commit (ver §Estratégia,
  item 3). A `task-ordering-hex` admite as duas formas, e esta é a que deixa o
  commit verificado.
- **As doze leis viraram Task própria** (concept: dentro da Task dos fakes).
  Razão: é o entregável que a 3.3 herda como especificação executável; um
  commit dedicado torna a revisão da suíte de leis independente da revisão da
  estrutura dos fakes. Total inalterado.
- **A reconciliação do `roadmap.md`** (concept §7, quatro eixos) fica no commit
  final `stage 3.2: complete`, como na 2.2 — não é Task numerada. Ver §3.

A **folga** que o concept §10 reservava (fundir DTOs + ports numa Task) **não
foi usada** e permanece disponível se alguma Task precisar ser quebrada durante
a execução. **Corte já indicado, se a Task 13 estourar na execução:** 13a =
`copy_employee_to_unit` + o seu teste; 13b = fluxo ponta-a-ponta + guardas
mecânicas. O corte custa a **14ª** Task (alarme de CONVENTIONS §6), então só se
paga se a Task 13 se mostrar de fato indivisível em revisão — não por
antecipação.

### Sinal de tamanho (CONVENTIONS §6) — visto e pesado

Este documento cruza o sinal de alarme de `technical.md` (~15 páginas; faixa
saudável 3–10). Registrado aqui pelo mesmo motivo que o concept registrou o
dele: para que a próxima leitura saiba que o sinal **foi visto**, e não
ignorado. A densidade não vem de escopo inchado — o sinal que mede recorte é o
de **Tasks**, e ele está em **13**, abaixo do alarme (≥ 14). Ela vem de três
fontes que o Checkpoint A e o B exigiram explicitamente: um critério de aceite
**por lei nomeada** do port (doze), a **matriz de rastreabilidade** completa, e
os **oito** cenários de precedência nomeados um a um. Encurtar qualquer um dos
três devolveria o defeito que eles existem para impedir (fake que vira upsert
em silêncio; critério órfão; reordenação silenciosa de checagem).

### Pré-condições

- Stage `3.1-staff-domain` em `done` e mergeada em `develop` (PR #33).
- `concept.md` desta Stage em `status: done` (gate `stage 3.2: conceptual
  approved`).
- Issue #35 OPEN; branch `feat/35-3-2-staff-application`.
- `.venv` instalado (`make setup` / `uv sync --extra dev`).

### Premissas técnicas

- Python 3.12, mypy `strict`, ruff com `ANN` e `PL`.
- **`make typecheck` já roda `mypy src/ tests/fakes/`** (decisão da 2.2, Task
  04) — logo a conformidade dos fakes novos com os `Protocol` novos tem gate
  desde o primeiro commit, via a linha `_conforms: <Port> = <Fake>(...)` em
  escopo de módulo de cada fake.
- **`Protocol` no estilo vigente no repo:** docstring + `...`. Corpo `...` não
  conta como statement para o coverage (verificado na 2.2), então o módulo de
  port mede 100% assim que é importado.
- Fakes vivem em `tests/fakes/features/staff/` (LAYOUT §2 + skill
  `pytest-with-fakes`), nunca duplicados dentro de `tests/unit/`.
- **O mapeamento `Employee` → `EmployeeResult` (e `JobFunction` →
  `JobFunctionResult`) é montado *inline* em cada use case** — precedente
  literal da 2.2 (`use_cases/create_unit.py`, onde o result é construído no
  próprio `execute`). **Não existe `dtos/mappers.py` nesta camada** e nenhuma
  Task o cria: os 11 use cases que devolvem `EmployeeResult` repetem a
  construção de propósito. Extrair um mapper compartilhado é decisão da 3.3/3.4
  (quando houver um segundo produtor do mesmo result, o adapter), não desta
  Stage — antecipá-la criaria um módulo sem âncora no concept §4, que lista
  DTOs e use cases e nenhum mapper. Se durante a execução a repetição doer,
  **perguntar** antes de criar o módulo: é arquivo fora do plano (escopo
  estrito).
- **Não existe gate automático de cobertura *por arquivo*** neste repo:
  `pyproject.toml` fixa apenas `fail_under = 90` **global**, aplicado pelo
  `test-gate` dentro do `make check`. O limiar por arquivo desta Stage é
  **verificação manual** da tabela do `--cov-report=term-missing` no gate de
  saída (§3) — não é algo que o `make check` reprova sozinho, e por isso
  precisa ser conferido a olho, com as linhas coladas no relatório.
- **Nenhum wiring no `composition_root`**: não há implementação concreta dos
  ports nesta Stage (concept §1 — fora de escopo).
- Código em **inglês**; docstrings, comentários e nomes de teste em PT-BR, como
  na 3.1 e na 2.2.
- Conversão canônica de id: `JobFunctionId(str(id_generator.next_id()))` e
  `EmployeeId(str(id_generator.next_id()))` (concept §5.3). Nenhum use case
  chama `uuid4()`.
- Nenhum use case recebe `Clock` (concept §7).
- **Três erros do concept §6 são inalcançáveis a partir de qualquer use case
  desta Stage** — `InvalidWeeklyHoursError`, `EmptyShiftPreferenceError` e
  `InvalidUnavailabilityPeriodError`. Eles nascem no `__post_init__` do VO, e o
  command já chega com o VO **construído**: quem os encontra é o chamador (hoje
  o próprio teste ao montar o command; na 3.4, o adapter HTTP). É o terceiro
  bloco da §6 do concept ("levantados **antes** do use case"). **Nenhuma Task
  escreve teste de use case esperando-os** — um `pytest.raises` em volta de
  `execute()` para qualquer um dos três nunca dispara, porque a exceção já
  aconteceu na linha que montou o argumento. Mapeá-los para HTTP é da 3.4.

### Exceções declaradas aos critérios de Task Atômica (PIPELINE §4.3)

- **Critério 4 (não misturar port com adapter): respeitado, não excepcionado.**
  A Task 05 emparelha port + **fake**, e fake não é adapter (não há tecnologia
  externa). Os adapters reais são da 3.3.
- **Critério 2 (≤ 5 arquivos): excepcionado na Task 05 (9 arquivos).** Razão: os
  dois ports, os dois fakes, o store compartilhado e os `__init__.py` de pacote
  formam **uma** unidade indivisível — o par acoplado só existe inteiro
  (concept §4), e separar produziria commit sem cobertura e sem gate de
  conformidade. Mesmo formato e mesma contagem da Task 04 da 2.2. Todas as
  demais Tasks ficam em ≤ 5 arquivos.

### Estrutura de pastas afetada

```
src/restaurant_hub/features/staff/
├── domain/entities/
│   ├── job_function.py            # MODIFICADO — perde active/deactivate/reactivate
│   └── employee.py                # MODIFICADO — ganha active/deactivate/reactivate
└── application/
    ├── errors.py
    ├── dtos/
    │   ├── commands.py
    │   ├── queries.py
    │   └── results.py
    ├── ports/out/
    │   ├── job_function_repository.py
    │   └── employee_repository.py
    └── use_cases/
        ├── create_job_function.py      ├── create_employee.py
        ├── rename_job_function.py      ├── rename_employee.py
        ├── delete_job_function.py      ├── assign_job_functions.py
        ├── list_job_functions.py       ├── change_workload_profile.py
        │                               ├── declare_shift_preference.py
        │                               ├── register_unavailability.py
        │                               ├── remove_unavailability.py
        │                               ├── deactivate_employee.py
        │                               ├── reactivate_employee.py
        │                               ├── delete_employee.py
        │                               ├── copy_employee_to_unit.py
        │                               └── list_employees.py

tests/
├── fakes/features/staff/
│   ├── in_memory_staff_store.py                  # store único (par acoplado)
│   ├── in_memory_job_function_repository.py
│   └── in_memory_employee_repository.py
├── unit/features/staff/domain/
│   ├── test_job_function.py       # MODIFICADO
│   └── test_employee.py           # MODIFICADO
└── unit/features/staff/application/
    ├── test_errors.py                        ├── test_create_employee.py
    ├── test_dtos.py                          ├── test_list_employees.py
    ├── test_staff_repository_fakes.py        ├── test_employee_edit_use_cases.py
    ├── test_job_function_repository_laws.py  ├── test_assign_job_functions.py
    ├── test_employee_repository_laws.py      ├── test_unavailability_use_cases.py
    ├── test_job_function_use_cases.py        ├── test_employee_lifecycle.py
    ├── test_delete_job_function.py           ├── test_delete_employee.py
    │                                         ├── test_copy_employee_to_unit.py
    │                                         ├── test_staff_flow.py
    │                                         └── test_application_guards.py

.importlinter                       # MODIFICADO — contrato staff-application-purity
```

## 2. Tasks

> Faixa saudável: **3–12 Tasks por Stage**. ≥ 14 = Stage grande demais.
> Esta Stage fecha em **13** — acima da faixa e **abaixo do alarme**, como o
> concept §10/§12 previu e pesou.

### Task 01 — `JobFunction` perde o ciclo de vida (domínio da 3.1)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/domain/entities/job_function.py`
  - `tests/unit/features/staff/domain/test_job_function.py`
- **O que fazer:**
  Remover da entidade o campo `active` e os métodos `deactivate()` e
  `reactivate()`, junto com os testes que os exercitam. Atualizar as docstrings
  que afirmam o contrário (ADR 3.2.0005 supersede o 3.1.0003).
- **Detalhes técnicos:**
  - A entidade fica com `id`, `tenant_id`, `name` — `__post_init__`, `rename`,
    `__eq__` e `__hash__` inalterados.
  - **Docstring do módulo:** hoje diz "o bloqueio de atribuição de função
    inativa são declarados aqui e impostos na application/persistência" — a
    segunda metade deixa de existir; sobra a unicidade de nome no tenant
    (imposta na 3.2, §5.5) e a **remoção guardada** (§5.9).
  - **Docstring da classe:** hoje diz "com ciclo de vida soft (ADR 3.1.0003)";
    passa a citar o ADR 3.2.0005 e a dizer que a função **não tem estado** —
    função sem atribuição é inerte.
  - Nos testes: remover `test_deactivate_devolve_nova_instancia_inativa`,
    `test_reactivate_devolve_nova_instancia_ativa`,
    `test_transicoes_repetidas_sao_idempotentes_no_valor`; remover o parâmetro
    `active` do helper `_funcao`; ajustar
    `test_cria_funcao_valida_com_active_default` (vira
    `test_cria_funcao_valida`, sem asserção de estado) e
    `test_entidade_e_imutavel` (atribuir a `name`, não a `active`).
- **Critério de aceite:**
  - Concept **§11/Gates**: `grep` limpo por `active`, `deactivate` e
    `reactivate` nos dois arquivos — **nenhum teste órfão** referenciando os
    métodos removidos.
  - A suíte de domínio da 3.1 continua verde; cobertura de
    `job_function.py` em 100%.
  - `make check` verde (o gate global de cobertura não regride).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/domain/ -v
  Select-String -Path src/restaurant_hub/features/staff/domain/entities/job_function.py, tests/unit/features/staff/domain/test_job_function.py -Pattern "active|deactivate|reactivate"   # nenhuma linha
  make check
  ```
- **Commit sugerido:** `refactor(staff): remover ciclo de vida da função de trabalho [3.2/task-01]`

---

### Task 02 — `Employee` ganha estado de desligamento (domínio da 3.1)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/domain/entities/employee.py`
  - `tests/unit/features/staff/domain/test_employee.py`
- **O que fazer:**
  Acrescentar `active: bool = True` e as transições `deactivate()` /
  `reactivate()`, com testes no mesmo commit (ADR 3.2.0006).
- **Detalhes técnicos:**
  - `active: bool = True` é o **último** campo do dataclass (depois de
    `unavailabilities`, que já tem default) — ordem exigida pelo dataclass e
    aditiva para todos os call-sites da 3.1.
  - `deactivate()` / `reactivate()` devolvem nova instância via
    `dataclasses.replace(self, active=False|True)`, **idempotentes no valor**
    (repetir não é erro) — mesma forma que a 3.1 fixara para a função.
  - `__post_init__` **não** ganha validação nova: booleano não tem estado
    inválido.
  - **Docstring do módulo:** remover "bloqueio de função inativa são
    enforcement da 3.2/3.3" (a regra deixou de existir — ADR 3.2.0005) e
    acrescentar que a validade referencial do conjunto continua sendo
    enforcement da 3.2/3.3.
  - **Docstring da classe:** documentar `active` — registro desligado
    **sobrevive** com toda a história, some da listagem default e continua
    contando como referência para a guarda de remoção de função.
- **Critério de aceite:**
  - `Employee` construído sem `active` nasce `active=True`.
  - `deactivate()` devolve instância com `active=False` e **não** muta a
    original; `reactivate()` idem para `True`.
  - Repetir `deactivate()` sobre já-desligado (e `reactivate()` sobre já-ativo)
    **não levanta** e preserva o valor.
  - Nenhum outro campo muda nas duas transições (comparação campo a campo).
  - A entidade continua imutável (`FrozenInstanceError` ao atribuir `active`).
  - Suíte de domínio da 3.1 verde; `employee.py` em 100%.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/domain/test_employee.py -v
  uv run pytest tests/ --cov=src/restaurant_hub/features/staff --cov-report=term-missing
  make check
  ```
- **Commit sugerido:** `feat(staff): dar estado de desligamento ao funcionário [3.2/task-02]`

---

### Task 03 — erros de aplicação + contrato `staff-application-purity`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/errors.py`
  - `tests/unit/features/staff/application/__init__.py` (vazio)
  - `tests/unit/features/staff/application/test_errors.py`
- **Arquivos a modificar:**
  - `.importlinter` (contrato novo `staff-application-purity`)
- **O que fazer:**
  Criar os **nove** erros de aplicação do concept §4, todos subclasses de
  `StaffError`; os dois de "não encontrado" herdam também de `NotFoundError`,
  **nesta ordem**. Instalar o contrato de pureza da camada no import-linter,
  espelhando `identity-application-purity`.
- **Detalhes técnicos:**
  - Classes, na ordem do concept §4: `JobFunctionNotFoundError`,
    `EmployeeNotFoundError`, `JobFunctionNameAlreadyExistsError`,
    `JobFunctionAlreadyExistsError`, `EmployeeAlreadyExistsError`,
    `JobFunctionInUseError`, `EmployeeInUseError`, `EmployeeRelocationError`,
    `SameUnitCopyError`.
  - Os dois de not-found: `class JobFunctionNotFoundError(StaffError,
    NotFoundError)` — `StaffError` **primeiro** (concept §4: o handler da raiz
    do BC precisa ganhar do genérico no lookup por MRO do Starlette).
  - Cada erro monta a mensagem no `__init__`, citando o recurso ou a regra
    violada, como os do domínio 3.1. `EmployeeRelocationError` cita a `unit_id`
    gravada e a enviada — é erro **intra-tenant** (concept §4/L-E3: com tenant
    divergente o erro é `EmployeeNotFoundError`), então a mensagem **não** cita
    `tenant_id`; `SameUnitCopyError` cita a unidade.
  - `EmployeeInUseError` nasce **sem produtor** em v1 (lei L-E5) — a docstring
    diz isso explicitamente e nomeia o Step 4 como quem passa a produzi-la.
  - Contrato `[importlinter:contract:staff-application-purity]`, tipo
    `forbidden`, `source_modules = restaurant_hub.features.staff.application`,
    `forbidden_modules =` `restaurant_hub.features.staff.adapters`,
    `restaurant_hub.shared.infrastructure`, `fastapi`, `starlette`, `uvicorn`,
    `sqlalchemy`, `alembic`, `psycopg`, `pydantic`, `pydantic_settings`,
    `httpx`, `argon2`, `jwt` — **aditivo**: nenhum contrato existente é
    afrouxado. Comentário acima do bloco explicando o que **não** é proibido e
    por quê (mesma forma do contrato de identity).
- **Critério de aceite:**
  - Teste por **introspecção** do módulo (espelho de
    `tests/unit/features/identity/application/test_errors.py`): toda classe
    declarada é `BaseException`, `StaffError` e `DomainError`; a lista de nomes
    é **fixada literalmente** (os nove), para que classe nova ou removida force
    revisão consciente.
  - **Ordem na MRO** dos dois not-found, asserida por **índice** (não por
    `issubclass`, que passa nas duas ordens):
    `X.__mro__.index(StaffError) < X.__mro__.index(NotFoundError) <
    X.__mro__.index(DomainError)`.
  - **Nenhum** dos sete erros de duplicidade/uso/realocação/cópia é
    `NotFoundError` (`not issubclass(cls, NotFoundError)`).
  - `UnavailabilityNotFoundError` (domínio 3.1) **não** é `NotFoundError` —
    teste explícito de que os 422 são decisão e não esquecimento.
  - **Cada** erro é instanciado e a mensagem assertada (executa o `__init__`;
    sem isso `errors.py` fica abaixo do limiar por arquivo que a Stage se
    impõe em §3 — conferência manual, não gate automático).
  - `lint-imports` reporta `staff-application-purity` como **KEPT** e nenhum
    contrato quebrado.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_errors.py -v
  uv run lint-imports
  make check
  ```
- **Commit sugerido:** `feat(staff): erros de aplicação e contrato de pureza da camada [3.2/task-03]`

---

### Task 04 — DTOs de fronteira: commands, queries e results

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/dtos/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/application/dtos/commands.py`
  - `src/restaurant_hub/features/staff/application/dtos/queries.py`
  - `src/restaurant_hub/features/staff/application/dtos/results.py`
  - `tests/unit/features/staff/application/test_dtos.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar os **14 commands**, as **2 queries** e os **2 results** do concept §4,
  todos `@dataclass(frozen=True)` — igualdade por valor, o que os torna o alvo
  correto das asserções "não mudou" de §11.
- **Detalhes técnicos:**
  - Campos **exatamente** como as tabelas do concept §4. Em especial:
    `CreateEmployeeCommand(tenant_id, unit_id, name, workload_profile,
    job_function_ids, shift_preference=None)`;
    `ListEmployeesQuery(tenant_id, unit_id, include_inactive=False)`;
    `EmployeeResult(id, tenant_id, unit_id, name, workload_profile,
    shift_preference, job_function_ids, unavailabilities, active)`.
  - **Nenhum identificador novo** é introduzido: os ids são os `NewType` da
    3.1 (`domain/value_objects/identifiers.py`).
  - VOs de domínio (`WorkloadProfile`, `ShiftPreference`,
    `UnavailabilityPeriod`) são usados diretamente nos campos — permitido por
    LAYOUT §7. **Entidades não aparecem em nenhum DTO.**
  - `job_function_ids` é `frozenset[JobFunctionId]` (sem ordem — ADR 3.1.0006);
    `unavailabilities` é `tuple[UnavailabilityPeriod, ...]`.
- **Critério de aceite:**
  - Teste constrói **cada** command, query e result; afirma imutabilidade
    (`dataclasses.FrozenInstanceError` ao atribuir) e os defaults
    (`shift_preference=None`, `include_inactive=False`).
  - **Igualdade por valor**: duas instâncias de `EmployeeResult` com os mesmos
    campos são `==`; divergir em **um** campo as torna `!=` (é a asserção que
    §11 usa para "nenhum outro campo mudou").
  - Concept §11/Cópia: `dataclasses.fields(EmployeeResult)` **não** contém
    nenhum campo de vínculo de login (`user_id` ou equivalente) — guarda para a
    3.5 — e **contém** `active`.
  - Nenhum campo de result é anotado com `Employee` ou `JobFunction`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_dtos.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit sugerido:** `feat(staff): DTOs de comando, consulta e resultado da camada de aplicação [3.2/task-04]`

---

### Task 05 — ports-out + par acoplado de fakes sobre store único

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/ports/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/application/ports/out/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/application/ports/out/job_function_repository.py`
  - `src/restaurant_hub/features/staff/application/ports/out/employee_repository.py`
  - `tests/fakes/features/staff/__init__.py` (vazio)
  - `tests/fakes/features/staff/in_memory_staff_store.py`
  - `tests/fakes/features/staff/in_memory_job_function_repository.py`
  - `tests/fakes/features/staff/in_memory_employee_repository.py`
  - `tests/unit/features/staff/application/test_staff_repository_fakes.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar os dois `Protocol` do concept §4 — com **cada lei nomeada na docstring
  do método** — e o **par acoplado** de fakes: um `InMemoryStaffStore` único
  injetado na construção, do qual cada fake é uma **visão**. Esta Task entrega
  a **fixture que a 3.3 parametriza** no teste de contrato; tratar como
  entregável de primeira classe, não como andaime de teste.
- **Detalhes técnicos:**
  - `JobFunctionRepository`: `add`, `update`, `delete`, `find_by_id`,
    `find_by_name`, `find_all_by_ids`, `list_by_tenant` — assinaturas
    **verbatim** do concept §4, todas escopadas por `tenant_id` exceto a
    unicidade de id de `add` (escopo **global**, deliberado — quadro do
    concept §4).
  - `EmployeeRepository`: `add`, `update`, `delete`, `find_by_id`,
    `list_by_unit(..., *, include_inactive: bool = False)`,
    `exists_by_job_function`.
  - **A docstring de cada método cita a lei que o governa** (L-JF1…L-E7) e o
    erro que levanta. Esse texto é a especificação que a 3.3 implementa em
    Postgres — escrevê-lo aqui é o que evita a retroação de contrato que a
    2.2→2.3 pagou (ADR 2.3.0003).
  - `InMemoryStaffStore`: `job_functions: dict[JobFunctionId, JobFunction]` e
    `employees: dict[EmployeeId, Employee]` **planos** (sem aninhamento por
    tenant — o filtro por `tenant_id` é comparação de campo, espelhando o
    `WHERE tenant_id = …` da 3.3, e é o que permite a colisão **global** de id
    de L-JF1/L-E1). Guarda também `calls: list[str]`, o registro das chamadas
    recebidas, usado pelos critérios "não tocou o port".
  - Os dois fakes recebem o store no construtor
    (`InMemoryJobFunctionRepository(store)`); **um par construído sobre stores
    diferentes é erro de teste, não configuração válida**. Um helper
    `staff_repositories()` constrói o par sobre um store novo e é a **única**
    forma usada nos testes da Stage. Ele devolve **os três** objetos — os dois
    fakes **e o store** — num holder `frozen`
    (`StaffFakes(store, job_functions, employees)`), e não um par. Holder e
    helper vivem em `in_memory_staff_store.py`, junto do store que constroem —
    não é arquivo novo. Os critérios
    "não tocou o port" (Task 07) asseriram `store.calls`, e sem o store no
    retorno o teste só o alcançaria por atributo de um dos fakes — acoplando a
    suíte à representação interna do fake, exatamente o que a
    `pytest-with-fakes` manda evitar. O holder também é o formato que a 3.3
    parametriza no teste de contrato.
  - **Ordem de checagem, normativa (concept §4/L-E3 e §5.4):** todo método que
    recebe `tenant_id` resolve **primeiro** o lookup por `(tenant_id, id)` —
    ausente ⇒ `*NotFoundError` — e só **depois** avalia qualquer outra guarda
    (divergência de `unit_id` em L-E3, referências em L-JF3/L-E5, conjunto de
    funções em L-E4, nome em L-JF1/L-JF2). Invertê-la faz o port responder um
    erro que **confirma a existência de registro de outro tenant**, violando a
    regra normativa de §5.4. `EmployeeRelocationError` é, portanto, um erro
    **intra-tenant**: só alcançável quando o registro foi encontrado no tenant
    pedido e a unidade diverge.
  - As doze leis são implementadas **aqui**; os testes que as travam são a
    Task 06.
  - Cada módulo de fake declara, em escopo de módulo,
    `_conforms: <Port> = <Fake>(InMemoryStaffStore())` — sem isso a
    conformidade fake↔`Protocol` seria decorativa.
- **Critério de aceite:**
  - Round-trip de cada fake: `add` seguido de `find_by_id` (com o `tenant_id`
    certo) devolve o agregado gravado; `find_by_id` com id inexistente devolve
    `None`.
  - O helper devolve store + dois fakes que enxergam **o mesmo** store: uma
    função gravada pelo fake de função é visível para a guarda do fake de
    funcionário (checagem básica de L-E4) e vice-versa (L-JF3); e
    `fakes.store.calls` é alcançável **sem** tocar em atributo de fake.
  - `mypy src/ tests/fakes/` verde — e **validar empiricamente uma vez**:
    remover um método de um fake, confirmar que o mypy acusa
    `missing following protocol member`, restaurar.
  - Os dois módulos de port medem 100% de cobertura (corpo `...` não conta).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_staff_repository_fakes.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit sugerido:** `feat(staff): ports-out de equipe e par de fakes sobre store único [3.2/task-05]`

---

### Task 06 — as doze leis dos ports travadas contra os fakes

- **Arquivos a criar:**
  - `tests/unit/features/staff/application/test_job_function_repository_laws.py`
  - `tests/unit/features/staff/application/test_employee_repository_laws.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Uma suíte por port cobrindo **cada uma das doze leis** com teste direto
  contra o fake, mais o teste dedicado de escopo de tenant por port. Sem
  isto, um fake que vire upsert em silêncio passa verde — o defeito histórico
  do BC identity (ADR 2.3.0003).
- **Detalhes técnicos:**
  - Nomear cada teste pela lei (`test_l_jf1_add_com_id_ja_gravado_...`), para
    que a 3.3 possa parear o teste de contrato lei a lei.
  - Toda construção usa o helper `staff_repositories()` da Task 05, que devolve
    o holder `StaffFakes(store, job_functions, employees)` — nenhum teste da
    Stage instancia fake diretamente nem alcança o store por atributo de fake.
- **Critério de aceite** (um por linha de §11/"Leis dos ports"):
  - **L-JF1:** `add` com id já gravado ⇒ `JobFunctionAlreadyExistsError`,
    **inclusive quando o id gravado está em outro tenant**; `add` com nome já
    usado **no mesmo tenant** ⇒ `JobFunctionNameAlreadyExistsError`; nos dois
    casos a releitura por `find_by_id` devolve os **campos antigos**.
  - **L-JF2:** `update` de função inexistente **no tenant** ⇒
    `JobFunctionNotFoundError` **e nada é gravado** (`find_by_id` continua
    `None`, `list_by_tenant` não cresce); `update` renomeando para o **próprio
    nome** é aceito; para o nome de **outra** ⇒
    `JobFunctionNameAlreadyExistsError`.
  - **L-JF3:** `delete` de função **referenciada** ⇒ `JobFunctionInUseError` e
    a função continua legível; vale também quando o único referenciador está
    **inativo**; `delete` de inexistente no tenant ⇒
    `JobFunctionNotFoundError`.
  - **L-JF4 / L-JF5:** `find_all_by_ids` devolve **só as encontradas** e não
    levanta erro para ids ausentes; `list_by_tenant` devolve **todas** as do
    tenant e **nenhuma** de outro.
  - **L-E1 / L-E2:** `add` com id já gravado ⇒ `EmployeeAlreadyExistsError`
    (inclusive id de outro tenant); `update` de inexistente no tenant ⇒
    `EmployeeNotFoundError` **e nada é gravado**.
  - **L-E3:** `update` cujo `unit_id` diverge do gravado, **no mesmo tenant**,
    ⇒ `EmployeeRelocationError`, e a releitura devolve o registro **na unidade
    original, com os campos antigos**. **Teste irmão obrigatório, da ordem de
    checagem:** `update` com `tenant_id` **de outro tenant** ⇒
    `EmployeeNotFoundError`, **não** `EmployeeRelocationError` — inclusive
    quando a `unit_id` enviada também diverge da gravada, que é o cenário em
    que uma implementação que checasse a unidade primeiro vazaria a existência
    do registro alheio (concept §5.4 vence a L-E3; ver o quadro de L-E3 no
    concept §4).
  - **L-E4:** `add`/`update` cujo conjunto contém id de função inexistente no
    tenant (**ou existente em outro tenant**) ⇒ `JobFunctionNotFoundError` e
    nada é gravado.
  - **L-E5:** `delete` de inexistente no tenant ⇒ `EmployeeNotFoundError`;
    `delete` de existente **remove** (`find_by_id` ⇒ `None`); e um teste
    declara que `EmployeeInUseError` **existe, é instanciável e tem mensagem**,
    com a lei documentada no `Protocol` para o Step 4 preencher.
  - **L-E6 / L-E7:** `list_by_unit` devolve só a unidade pedida, **só ativos**
    por default, e inclui inativos com `include_inactive=True`;
    `exists_by_job_function` é `True` para referência em **qualquer** unidade
    do tenant e para referenciador **inativo**, e `False` para referência de
    **outro** tenant.
  - **Escopo de tenant (teste dedicado por port):** registro criado no tenant A
    não é encontrado, listado, atualizado nem removido usando `tenant_id` do
    tenant B — o erro é `*NotFoundError` e **nunca** uma exceção que confirme a
    existência do registro alheio (nem `InUse`, nem `AlreadyExists`, nem
    `EmployeeRelocationError`). Este critério e o de L-E3 acima são a **mesma**
    regra vista dos dois lados; nenhuma entrada tem dois erros obrigatórios.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_job_function_repository_laws.py tests/unit/features/staff/application/test_employee_repository_laws.py -v
  make check
  ```
- **Commit sugerido:** `test(staff): travar as doze leis dos ports de equipe contra os fakes [3.2/task-06]`

---

### Task 07 — use cases de função: criar, renomear e listar

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/__init__.py` (vazio)
  - `src/restaurant_hub/features/staff/application/use_cases/create_job_function.py`
  - `src/restaurant_hub/features/staff/application/use_cases/rename_job_function.py`
  - `src/restaurant_hub/features/staff/application/use_cases/list_job_functions.py`
  - `tests/unit/features/staff/application/test_job_function_use_cases.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Três use cases da família de função, na forma
  `<Nome>UseCase(deps…).execute(command) -> result`, **um por arquivo**
  (LAYOUT §7).
- **Detalhes técnicos:**
  - `CreateJobFunctionUseCase(job_functions, id_generator)`. Ordem
    obrigatória (concept §5.16): (1) construir a entidade — o nome vazio é
    rejeitado pelo domínio, **sem tocar o port**; (2) `find_by_name` ⇒
    `JobFunctionNameAlreadyExistsError`; (3) `add`. O id sai da conversão
    canônica e é **descartado** no payload inválido — decisão declarada do
    concept §5.16, não desperdício acidental.
  - `RenameJobFunctionUseCase(job_functions)`. Ordem: (1) `find_by_id` ausente
    ⇒ `JobFunctionNotFoundError`; (2) `find_by_name` **ignorando a própria
    função** ⇒ conflito; (3) `rename`; (4) `update`.
  - `ListJobFunctionsUseCase(job_functions)` ⇒
    `tuple[JobFunctionResult, ...]` por `list_by_tenant`.
  - Erros de domínio da 3.1 **não são reembrulhados** (§5.15).
- **Critério de aceite:**
  - `create_job_function` grava o nome **verbatim** (releitura pelo port
    devolve exatamente o enviado); segundo `create` com o **mesmo nome no mesmo
    tenant** ⇒ `JobFunctionNameAlreadyExistsError`; o mesmo nome **em outro
    tenant** é aceito; `"cozinheiro "` e `"Cozinheiro"` são nomes **distintos**
    e ambos são aceitos (unicidade verbatim — workforce §3.2).
  - `create_job_function` com nome vazio/só-whitespace ⇒ `InvalidNameError`
    **sem tocar o port**: `fakes.store.calls` fica **vazio** (nem `find_by_name`, nem
    `add`).
  - `rename_job_function` para o **próprio nome atual** é aceito e a releitura
    devolve o nome; para o nome de **outra** função do tenant ⇒
    `JobFunctionNameAlreadyExistsError` e a releitura devolve o **nome antigo**.
  - **Precedência (§5.16, par duplo):** renomear função **inexistente** para
    nome **já usado** ⇒ vence `JobFunctionNotFoundError`.
  - Função de **outro tenant** ⇒ `JobFunctionNotFoundError` (§5.4).
  - `list_job_functions` devolve **todas** as do tenant e **nenhuma** de outro.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_job_function_use_cases.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): use cases de criação, renomeação e listagem de função [3.2/task-07]`

---

### Task 08 — use case `delete_job_function` (guarda de remoção)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/delete_job_function.py`
  - `tests/unit/features/staff/application/test_delete_job_function.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  O use case que impõe a segunda regra cross-agregado delegada pela 3.1
  (concept §5.9): remoção definitiva só quando **nenhuma** referência existe.
- **Detalhes técnicos:**
  - `DeleteJobFunctionUseCase(job_functions, employees)` ⇒ `None`.
  - Ordem obrigatória (§5.16): (1) `find_by_id` ausente ⇒
    `JobFunctionNotFoundError`; (2) `employees.exists_by_job_function` ⇒
    `JobFunctionInUseError`; (3) `job_functions.delete`.
  - A consulta de referência é **tenant-wide** por construção (concept §4 — a
    função é tenant-scoped) e conta registros **ativos e inativos**.
- **Critério de aceite:**
  - Remove função **sem referências**: releitura pelo port ⇒ `None`.
  - Com **um** funcionário referenciando, em **qualquer** unidade do tenant e
    **ativo ou inativo** ⇒ `JobFunctionInUseError`, e a função **continua
    legível** pelo port.
  - **Precedência (§5.16, par duplo):** função do tenant A, **referenciada**,
    apagada com `tenant_id` do B ⇒ vence `JobFunctionNotFoundError` — o erro
    não pode confirmar que ela existe *nem* que está em uso (§5.4).
  - Referência existente em **outro tenant** não bloqueia a remoção.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_delete_job_function.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): use case de remoção guardada de função de trabalho [3.2/task-08]`

---

### Task 09 — use cases de funcionário: criar e listar por unidade

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/create_employee.py`
  - `src/restaurant_hub/features/staff/application/use_cases/list_employees.py`
  - `tests/unit/features/staff/application/test_create_employee.py`
  - `tests/unit/features/staff/application/test_list_employees.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criação do registro com validade referencial do conjunto de funções
  (terceira regra cross-agregado delegada — §5.8) e listagem escopada por
  unidade (L-E6).
- **Detalhes técnicos:**
  - `CreateEmployeeUseCase(employees, job_functions, id_generator)`. Ordem
    obrigatória (§5.16): (1) `job_functions.find_all_by_ids` — qualquer id
    **não devolvido** ⇒ `JobFunctionNotFoundError`; (2) construir o `Employee`
    (nome, conjunto não-vazio, ids) com `active=True`; (3) `employees.add`.
    A resolução vem **antes** da construção de propósito: construir primeiro
    esconderia a causa referencial atrás de um `InvalidNameError`.
  - Conjunto **vazio** no command: `find_all_by_ids(frozenset())` devolve
    vazio, nada falta, e o `EmptyJobFunctionsError` do domínio sobe na
    construção — sem reembrulho.
  - `ListEmployeesUseCase(employees)` ⇒ `tuple[EmployeeResult, ...]` por
    `list_by_unit(tenant_id, unit_id, include_inactive=query.include_inactive)`.
    **Não existe** listagem tenant-wide de funcionário.
- **Critério de aceite:**
  - `create_employee` grava o registro com o conjunto pedido e `active=True`;
    o id do result é exatamente `str(uuid)` do `FakeIdGenerator`; **a releitura
    pelo port devolve o registro gravado**.
  - Função **inexistente no tenant** (ou existente em **outro** tenant) ⇒
    `JobFunctionNotFoundError` e **nada é gravado**.
  - Conjunto **vazio** ⇒ `EmptyJobFunctionsError` (domínio).
  - **Precedência (§5.16, par duplo):** nome vazio **e** função inexistente ⇒
    vence `JobFunctionNotFoundError`.
  - **Não-vazamento entre unidades:** `list_employees(tenant, unidade A)` não
    devolve registro da unidade B, e vice-versa.
  - Listagem com `tenant_id` de outro tenant devolve vazio (não vaza).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_create_employee.py tests/unit/features/staff/application/test_list_employees.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): use cases de criação e listagem de funcionário [3.2/task-09]`

---

### Task 10 — edição do funcionário: nome, jornada e preferência

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/rename_employee.py`
  - `src/restaurant_hub/features/staff/application/use_cases/change_workload_profile.py`
  - `src/restaurant_hub/features/staff/application/use_cases/declare_shift_preference.py`
  - `tests/unit/features/staff/application/test_employee_edit_use_cases.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Três use cases granulares espelhando as transições do agregado
  (ADR 3.2.0004), todos no ciclo **carregar → transicionar → gravar o agregado
  inteiro**.
- **Detalhes técnicos:**
  - Todos com a forma `(employees)` no construtor e ordem: (1) `find_by_id`
    ausente ⇒ `EmployeeNotFoundError`; (2) transição do domínio; (3) `update`.
  - `declare_shift_preference` aceita `shift_preference=None` — que **significa
    "limpe a preferência"**, não "não mexa" (ADR 3.2.0004).
  - Nenhum deles altera `tenant_id`/`unit_id` (§5.12; o `Employee` da 3.1 nem
    expõe transição para isso).
- **Critério de aceite:**
  - `rename_employee` troca o nome (verbatim), **a releitura pelo port devolve
    o nome novo**, e **nenhum outro campo muda** — comparação **campo a campo**
    sobre o `EmployeeResult` (frozen, igualdade por valor), nunca
    `assert employee == employee` (que compara só por id).
  - `change_workload_profile` troca `FixedSchedule` ↔ `OnDemand` nos dois
    sentidos; result **e** releitura devolvem o estado novo.
  - `declare_shift_preference` grava preferência não-`None` **e** limpa com
    `None`; result e releitura confirmam os dois casos.
  - Os três com id inexistente **ou de outro tenant** ⇒ `EmployeeNotFoundError`
    e nada é gravado.
  - **Precedência (§5.16, par duplo):** funcionário inexistente **e** nome
    vazio ⇒ vence `EmployeeNotFoundError`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_employee_edit_use_cases.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): use cases de renomeação, jornada e preferência do funcionário [3.2/task-10]`

---

### Task 11 — atribuição de funções e indisponibilidades

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/assign_job_functions.py`
  - `src/restaurant_hub/features/staff/application/use_cases/register_unavailability.py`
  - `src/restaurant_hub/features/staff/application/use_cases/remove_unavailability.py`
  - `tests/unit/features/staff/application/test_assign_job_functions.py`
  - `tests/unit/features/staff/application/test_unavailability_use_cases.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  O use case que reimpõe a validade referencial numa edição (§5.8) e os dois
  que mexem na coleção de indisponibilidades do agregado.
- **Detalhes técnicos:**
  - `AssignJobFunctionsUseCase(employees, job_functions)`. Ordem: (1)
    `employees.find_by_id` ausente ⇒ `EmployeeNotFoundError`; (2)
    `job_functions.find_all_by_ids` — ausência ⇒ `JobFunctionNotFoundError`;
    (3) `assign_job_functions` (o conjunto **substitui**, não acumula);
    (4) `update`.
  - `RegisterUnavailabilityUseCase(employees)`: (1) carregar; (2)
    `add_unavailability` ⇒ `OverlappingUnavailabilityError` do domínio;
    (3) `update`.
  - `RemoveUnavailabilityUseCase(employees)`: (1) carregar; (2)
    `remove_unavailability` (por **valor**) ⇒ `UnavailabilityNotFoundError`;
    (3) `update`.
  - Os erros do domínio sobem **sem reembrulho** (§5.15).
- **Critério de aceite:**
  - `assign_job_functions` **substitui** o conjunto (a releitura devolve o
    conjunto novo, não a união); id inexistente no tenant ⇒
    `JobFunctionNotFoundError` e **nada é gravado**.
  - `register_unavailability` acrescenta o período (releitura confirma);
    período **sobreposto** ⇒ `OverlappingUnavailabilityError` e **nada é
    gravado** (releitura devolve a coleção antiga); período **adjacente**
    (fim == início) é **aceito**.
  - `remove_unavailability` remove por valor (releitura confirma); período
    inexistente no registro ⇒ `UnavailabilityNotFoundError` e nada é gravado.
  - Os três com funcionário inexistente/de outro tenant ⇒
    `EmployeeNotFoundError`.
  - **Precedência (§5.16, três pares duplos):** inexistente **+** função
    inexistente ⇒ `EmployeeNotFoundError`; inexistente **+** período sobreposto
    ⇒ `EmployeeNotFoundError`; inexistente **+** período ausente ⇒
    `EmployeeNotFoundError`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_assign_job_functions.py tests/unit/features/staff/application/test_unavailability_use_cases.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): use cases de atribuição de funções e de indisponibilidade [3.2/task-11]`

---

### Task 12 — ciclo de vida e remoção definitiva do funcionário

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/deactivate_employee.py`
  - `src/restaurant_hub/features/staff/application/use_cases/reactivate_employee.py`
  - `src/restaurant_hub/features/staff/application/use_cases/delete_employee.py`
  - `tests/unit/features/staff/application/test_employee_lifecycle.py`
  - `tests/unit/features/staff/application/test_delete_employee.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Desligamento, recontratação e remoção definitiva guardada (ADR 3.2.0006). É a
  Task que prova a propriedade central da decisão do sponsor: **o desligado
  sobrevive** — some da lista, mas não some do sistema.
- **Detalhes técnicos:**
  - `DeactivateEmployeeUseCase(employees)` / `ReactivateEmployeeUseCase(employees)`:
    carregar ⇒ `EmployeeNotFoundError`; transição (**idempotente no valor**);
    `update`.
  - `DeleteEmployeeUseCase(employees)` ⇒ `None`. Ordem: (1) carregar ⇒
    `EmployeeNotFoundError`; (2) `employees.delete`. **Só isso.**
  - **A guarda de referências da L-E5 é do port, não do use case.** O concept
    §5.16 lista "(2) guarda de referências" na precedência de `delete_employee`
    porque descreve a **sequência observável** da operação — mas quem a impõe é
    o `delete` do repositório (no fake, por construção; na 3.3, pela FK
    `RESTRICT`), como acontece com L-JF3 do lado da função. **Não escrever no
    use case um `if` que levante `EmployeeInUseError`**: em v1 nada referencia o
    registro de funcionário, então esse ramo seria **morto** — e, com
    `branch = true` na cobertura, o próximo a passar por aqui o "resolve" com um
    `# pragma: no cover`, que é como um ramo inalcançável vira dívida
    permanente. O use case chama `delete` e deixa o erro do port subir; quando o
    Step 4 criar o produtor, o use case **não muda**.
  - O desligamento **não é datado** (o campo é booleano — ADR 3.2.0006);
    nenhum `Clock` é injetado.
- **Critério de aceite:**
  - `deactivate_employee` põe `active=False`, `reactivate_employee` põe
    `active=True`; ambos **idempotentes no valor** (repetir não é erro); a
    releitura pelo port confirma; e **nenhum outro campo muda** (comparação
    campo a campo do result).
  - **O desligado sobrevive e some da lista:** depois de `deactivate`,
    `list_employees(tenant, unidade)` **não** o devolve;
    `list_employees(…, include_inactive=True)` **devolve**; `find_by_id`
    continua achando; e o registro **continua bloqueando** a remoção das suas
    funções (`JobFunctionInUseError` via `delete_job_function`).
  - `delete_employee` remove definitivamente: releitura ⇒ `None`, e o registro
    some das **duas** listagens (default e `include_inactive=True`).
  - Registro inexistente **ou de outro tenant** ⇒ `EmployeeNotFoundError`.
  - **Ausência de produtor de `EmployeeInUseError` em v1** fixada como critério:
    teste que percorre os cenários construíveis de `delete_employee` (ativo,
    inativo, com funções, com indisponibilidades) e afirma que **nenhum** a
    levanta — a classe existe pelo contrato do Step 4, não por engano. O use
    case **não** tem ramo que a levante (ver Detalhes técnicos): o teste fixa
    a ausência do produtor, não cobre um `if` morto.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_employee_lifecycle.py tests/unit/features/staff/application/test_delete_employee.py -v
  make check
  ```
- **Commit sugerido:** `feat(staff): use cases de desligamento, recontratação e remoção de funcionário [3.2/task-12]`

---

### Task 13 — cópia entre unidades, fluxo ponta-a-ponta e guardas mecânicas

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/use_cases/copy_employee_to_unit.py`
  - `tests/unit/features/staff/application/test_copy_employee_to_unit.py`
  - `tests/unit/features/staff/application/test_staff_flow.py`
  - `tests/unit/features/staff/application/test_application_guards.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  O use case do DoD do roadmap (cópia que duplica sem vazar), o fluxo
  ponta-a-ponta com os 16 use cases reais sobre a mesma bateria de fakes, e as
  guardas mecânicas que só fazem sentido com o pacote `use_cases` completo.
- **Detalhes técnicos:**
  - `CopyEmployeeToUnitUseCase(employees, id_generator)` — **não** consome
    `JobFunctionRepository` (concept §4: a única razão seria checar o estado das
    funções, que deixou de existir; a corrida é fechada pela lei L-E4 do `add`).
  - Ordem (§5.16): (1) `find_by_id` da origem ⇒ `EmployeeNotFoundError`;
    (2) `target_unit_id == employee.unit_id` ⇒ `SameUnitCopyError`;
    (3) construir a cópia — id **novo** pela conversão canônica, `unit_id` =
    destino, **mesmo** `tenant_id`, e nome, perfil, preferência, conjunto de
    funções, indisponibilidades **e `active`** duplicados; (4) `add`.
  - **Guardas mecânicas** (`test_application_guards.py`), por introspecção do
    pacote `use_cases` e dos dataclasses de result.
- **Critério de aceite:**
  - **Cópia (DoD do roadmap):** registro novo com **id novo**, `unit_id` =
    destino e mesmo `tenant_id`, replicando nome, perfil, preferência, conjunto
    de funções, indisponibilidades e `active`. A **origem permanece
    inalterada** — verificado **relendo a origem pelo port** e comparando o
    `EmployeeResult` campo a campo com um snapshot tirado **antes** da cópia.
  - **Independência estrutural:** editar a cópia (renomear, acrescentar
    indisponibilidade, desligar) e reler a **origem** ⇒ campos da origem
    inalterados; e vice-versa. O teste **muta e relê** — nunca compara campos
    logo após a cópia.
  - `EmployeeResult` da cópia **não contém nenhum campo de vínculo de login**
    (guarda para a 3.5).
  - `target_unit_id` == unidade de origem ⇒ `SameUnitCopyError` e **nada é
    gravado**.
  - **Limite declarado (§5.11):** copiar **duas vezes** para o mesmo destino
    produz **dois** registros na unidade destino, com ids distintos — teste que
    **fixa o comportamento como decisão**, para que ninguém o "conserte" sem
    revisitar o `[finding]` da 3.4.
  - **Precedência (§5.16, par duplo):** origem **de outro tenant** e
    `target_unit_id` igual à unidade **real** da origem ⇒ vence
    `EmployeeNotFoundError`, e a resposta não revela que o registro existe em
    outro tenant.
  - **Fluxo ponta-a-ponta com fakes, sem I/O e sem mocks:** criar função →
    criar funcionário na unidade A → definir jornada e preferência → registrar
    indisponibilidade → copiar para a unidade B → desligar o da unidade A →
    listar A e B (A **vazia** por default, A com **um** registro em
    `include_inactive=True`, B com **um** registro) → tentar apagar a função ⇒
    `JobFunctionInUseError`. Nenhuma escrita direta nos fakes fora dos use
    cases.
  - **Guarda mecânica 1 (ADR 3.2.0005):** **não existe** use case, command,
    campo de result nem parâmetro de query de ativação/desativação de **função**
    — teste que inspeciona o pacote `use_cases`, os commands/queries e o
    `JobFunctionResult`.
  - **Guarda mecânica 2 (CLAUDE.md nota 6):** **nenhum** use case devolve
    `Employee` ou `JobFunction` — teste que inspeciona as anotações de retorno
    de `execute` de todos os 16 use cases.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/ -v
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
  make check
  ```
- **Commit sugerido:** `feat(staff): use case de cópia entre unidades e fluxo ponta-a-ponta [3.2/task-13]`

---

### Matriz de rastreabilidade

**Regra:** todo critério de aceite do concept §11 e todo contrato/lei do
concept §4 tem ao menos uma Task que o entrega; e nenhuma Task existe sem
âncora no concept.

#### Leis dos ports (concept §4 e §11/"Leis dos ports") — 12 leis, 12 âncoras

| Lei | Onde é **implementada** | Onde é **travada por teste** |
|---|---|---|
| L-JF1 — `add` é inserção (id global + nome no tenant) | Task 05 | **Task 06** |
| L-JF2 — `update` não é upsert; nome ignorando a própria | Task 05 | **Task 06** |
| L-JF3 — `delete` guardado por referência (ativo ou inativo) | Task 05 | **Task 06** (+ Task 08 pelo use case) |
| L-JF4 — `find_all_by_ids` devolve só as encontradas | Task 05 | **Task 06** |
| L-JF5 — `list_by_tenant` devolve todas, sem flag de estado | Task 05 | **Task 06** |
| L-E1 — `add` é inserção (id global) | Task 05 | **Task 06** |
| L-E2 — `update` não é upsert; grava o agregado inteiro | Task 05 | **Task 06** |
| L-E3 — localização imutável, **intra-tenant** (`EmployeeRelocationError`) + ordem de checagem `(tenant_id, id)` antes de `unit_id` | Task 05 | **Task 06** (lei + teste irmão de tenant alheio) |
| L-E4 — validade referencial do conjunto no `add`/`update` | Task 05 | **Task 06** (+ Tasks 09/11/13 pelo uso) |
| L-E5 — `delete` guardado; `EmployeeInUseError` sem produtor em v1 | Task 05 | **Task 06** (+ Task 12) |
| L-E6 — `list_by_unit` exige unidade; só ativos por default | Task 05 | **Task 06** (+ Tasks 09/12) |
| L-E7 — `exists_by_job_function` tenant-wide, ativos e inativos | Task 05 | **Task 06** (+ Task 08) |

**Nenhuma das doze leis fica sem Task.**

#### Contratos introduzidos (concept §4)

| Contrato | Task |
|---|---|
| `JobFunctionRepository` (`Protocol`) | 05 |
| `EmployeeRepository` (`Protocol`) | 05 |
| Par acoplado de fakes sobre `InMemoryStaffStore` (fixture herdada pela 3.3) | 05 |
| 14 commands + 2 queries + 2 results (`frozen`) | 04 |
| 9 erros de aplicação (`errors.py`) | 03 |
| `Employee.active` + `deactivate()`/`reactivate()` | 02 |
| Remoção de `JobFunction.active`/`deactivate()`/`reactivate()` | 01 |
| Contrato `staff-application-purity` (`.importlinter`) | 03 |
| `CreateJobFunctionUseCase` / `RenameJobFunctionUseCase` / `ListJobFunctionsUseCase` | 07 |
| `DeleteJobFunctionUseCase` | 08 |
| `CreateEmployeeUseCase` / `ListEmployeesUseCase` | 09 |
| `RenameEmployeeUseCase` / `ChangeWorkloadProfileUseCase` / `DeclareShiftPreferenceUseCase` | 10 |
| `AssignJobFunctionsUseCase` / `RegisterUnavailabilityUseCase` / `RemoveUnavailabilityUseCase` | 11 |
| `DeactivateEmployeeUseCase` / `ReactivateEmployeeUseCase` / `DeleteEmployeeUseCase` | 12 |
| `CopyEmployeeToUnitUseCase` | 13 |

#### Critérios de aceite do concept §11

| Bloco / critério | Task |
|---|---|
| **Erros** — introspecção + lista literal de nomes | 03 |
| **Erros** — nenhum de duplicidade/uso herda `NotFoundError` | 03 |
| **Erros** — ordem na MRO por **índice** | 03 |
| **Erros** — `UnavailabilityNotFoundError` não é `NotFoundError` | 03 |
| **Erros** — cada erro instanciado produz mensagem | 03 |
| **Função** — `create` verbatim, conflito no tenant, aceito em outro tenant, case/espaço distintos | 07 |
| **Função** — nome vazio ⇒ `InvalidNameError` **sem tocar o port** | 07 |
| **Função** — `rename` para o próprio nome / para o de outra, com releitura | 07 |
| **Função** — `delete` sem referência remove; com referência (qualquer unidade, ativo ou inativo) ⇒ `JobFunctionInUseError` | 08 |
| **Função** — guarda mecânica: não existe ativação/desativação de função | 13 |
| **Funcionário** — `create` com `active=True`, função ausente, conjunto vazio, nome vazio, releitura | 09 |
| **Funcionário** — `rename` verbatim + comparação campo a campo | 10 |
| **Funcionário** — `assign` substitui o conjunto; id ausente não grava | 11 |
| **Funcionário** — `change_workload_profile` e `declare_shift_preference` (inclusive limpar com `None`) | 10 |
| **Funcionário** — `register`/`remove` de indisponibilidade (sobreposto, adjacente, ausente) | 11 |
| **Funcionário** — ciclo de vida idempotente, releitura, nenhum outro campo muda | 12 |
| **Funcionário** — o desligado sobrevive, some da lista default, bloqueia remoção da função | 12 |
| **Funcionário** — `delete` remove definitivamente; outro tenant ⇒ `EmployeeNotFoundError` | 12 |
| **Cópia** — DoD do roadmap (id novo, destino, mesmo tenant, replica tudo, origem intacta por releitura) | 13 |
| **Cópia** — independência estrutural (muta e relê, nos dois sentidos) | 13 |
| **Cópia** — nenhum campo de vínculo de login no `EmployeeResult` | 13 (+ 04, sobre o dataclass) |
| **Cópia** — `SameUnitCopyError` e nada gravado | 13 |
| **Cópia** — limite declarado: copiar duas vezes cria dois registros | 13 |
| **Escopo** — escopo de tenant por port, teste dedicado | 06 |
| **Escopo** — não-vazamento entre unidades na listagem | 09 (+ 13 no fluxo) |
| **Escopo** — precedência testada nos **oito** pares duplos de §5.16 | 07 (rename função), 08 (delete função), 09 (create funcionário), 10 (rename funcionário), 11 (assign, register, remove — três), 13 (cópia) |
| **Escopo** — fluxo ponta-a-ponta com fakes | 13 |
| **Escopo** — nenhum use case devolve `Employee`/`JobFunction` | 13 |
| **Gates** — `make check` verde incl. `staff-application-purity` (gate automático) e cobertura ≥ 90% por arquivo tocado (conferência manual do `term-missing`) | 03 (contrato) + **todas** (`make check` por Task) + §3 (conferência por arquivo) |
| **Gates** — suíte da 3.1 verde após as duas mudanças; `grep` limpo | 01 + 02 |

#### Findings escalados do concept §10 (nenhum é entregável desta Stage)

Os quatro `[finding]` (dois para a 3.4, dois para a 3.3) **não** geram Task:
são declarações para as Stages seguintes. São recopiados na §7 durante a
execução apenas se algo novo surgir; a lista canônica vive no concept §10.

## 3. Gate de saída da Stage

### Verificações automatizadas

```powershell
$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
make check
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
uv run lint-imports
uv run python scripts/check_technical_postexec.py "docs/stages/3.2-staff-application/technical.md"
git diff --name-only (git merge-base origin/develop HEAD) HEAD -- src/
```

### Verificações funcionais

- [ ] Fluxo ponta-a-ponta (Task 13) verde: função → funcionário na unidade A →
      jornada e preferência → indisponibilidade → cópia para B → desligamento
      em A → listagens de A e B → remoção da função bloqueada. Com os 16 use
      cases reais sobre a mesma bateria de fakes.
- [ ] **Não há superfície de runtime nesta Stage** (a API é da 3.4, a
      persistência é da 3.3): a verificação end-to-end é o teste de fluxo
      acima, e isso deve ser **dito explicitamente** no relatório em vez de
      simular um e2e HTTP que não existe.
- [ ] Cobertura ≥ 90% **em cada arquivo tocado** de `src/` — incluindo os dois
      arquivos de `domain/entities/` modificados nas Tasks 01–02 —, lida **a
      olho** na tabela do `--cov-report=term-missing`. **Não é gate automático:**
      o `test-gate` do `make check` só aplica `fail_under = 90` **global**, e a
      média global esconde arquivo míope. As linhas relevantes do
      `term-missing` vão **coladas** no relatório final; arquivo abaixo do
      limiar ⇒ cobrir ou justificar por escrito.
- [ ] `lint-imports` reporta `staff-application-purity` como **KEPT**.

### Checklist de fechamento da Stage

- [ ] Todas as 13 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Auditoria de testes por subagente independente, com **mutação real** nas
      funções críticas (`delete_job_function`, `create_employee`,
      `copy_employee_to_unit` e os guards dos fakes que impõem L-E3/L-E4)
- [ ] Commit final `stage 3.2: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at`/`last_reviewed_at` de
      hoje, linha no §Histórico, e a **nota de reconciliação em quatro eixos**
      do bloco 3.2 (concept §7): `camada_alvo` expandido (a Stage também toca
      `features/staff/domain/entities/`), `arquivos_a_modificar` deixa de ser
      vazio (`.importlinter`, as duas entidades e
      `tests/unit/features/staff/domain/test_job_function.py`),
      `contratos_introduzidos` ganha DTOs + erros + `Employee.active`, e
      `contratos_consumidos` ganha `IdGenerator` e `DomainError`/`NotFoundError`
- [ ] ADRs 3.2.0001–3.2.0006 em `status: accepted`; 3.1.0003 em `superseded`
      (já aplicado no gate conceitual)
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (JobFunction sem estado) ─┐
Task 02 (Employee com estado) ────┴─► Task 03 (erros + importlinter)
                                          │
                                          ├─► Task 04 (DTOs)
                                          │        │
                                          └────────┴─► Task 05 (ports + fakes)
                                                            │
                                                            ├─► Task 06 (12 leis)
                                                            │
                                                            ├─► Task 07 (função: create/rename/list)
                                                            │        └─► Task 08 (função: delete)
                                                            │
                                                            └─► Task 09 (funcionário: create/list)
                                                                     ├─► Task 10 (rename/jornada/preferência)
                                                                     ├─► Task 11 (assign + indisponibilidades)
                                                                     └─► Task 12 (ciclo de vida + delete)
                                                                              │
                                                                              ▼
                                                                     Task 13 (cópia + fluxo + guardas)
```

- **Tasks 01 e 02 vêm primeiro e são independentes entre si** — mas ambas
  precedem tudo, porque a forma final das entidades é insumo de DTOs, fakes e
  use cases. Fazê-las depois obrigaria a reescrever os testes da Stage.
- **Task 05 depende de 03** por import real: os fakes **levantam** os erros de
  `application/errors.py` (é o que torna L-JF1/L-E1/L-E3/L-E4 verificáveis).
  **Não depende de 04 por import** — ports e fakes falam em **entidades** de
  domínio, nunca em DTOs; quem monta result é o use case (Tasks 07–13). A
  ordem 04 → 05 é de **coesão de leitura** (a fronteira de dados antes da
  fronteira de I/O) e pode ser invertida sem retrabalho.
- **Task 06 depende só de 05** (não toca use case) — pode ser lida como o
  "contrato executável" dos ports, isolada do resto.
- **Task 08 depende de 07** apenas por coesão de pacote e pela fixture de
  função criada lá; a dependência dura é com 05.
- **Task 12 depende de 09** (precisa de `list_employees` para provar que o
  desligado some da lista) **e de 08** (para provar que o desligado continua
  bloqueando a remoção da função).
- **Task 13 depende de todas** — o fluxo ponta-a-ponta e as guardas mecânicas
  inspecionam o pacote `use_cases` completo.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Cobertura global cai abaixo de 90% num commit intermediário (arquivo de `src/` sem teste que o importe) | A ordem já emparelha código e teste em toda Task; se ainda assim cair, fundir a Task com a seguinte que a cobre — registrar `[deviation]` em §7 |
| Task 05 (9 arquivos) ficar grande demais para revisar | Usar a **folga declarada** do concept §10 ao contrário: extrair o `InMemoryStaffStore` + `__init__` para uma Task 05a e deixar ports + fakes na 05b (total 14 = alarme → só com autorização; preferir manter 13) |
| Remover `JobFunction.active` quebrar algo fora dos testes de domínio | Verificado antes de planejar: `grep` por `JobFunction`/`.active` em `src/` não encontra referência fora de `features/staff/domain/` — a mudança é fechada nos dois arquivos da Task 01 |
| Fake e futuro adapter divergirem nas guardas (o buraco que a 2.3 retroagiu) | Doze leis nomeadas na docstring do `Protocol` (Task 05) + suíte dedicada (Task 06); `mypy src/ tests/fakes/` dá gate estático à conformidade |
| Par de fakes ser construído sobre stores diferentes num teste (L-JF3/L-E4 passariam vacuamente) | Helper único `staff_repositories()` devolvendo o holder `StaffFakes(store, job_functions, employees)` como forma canônica; nenhum teste da Stage instancia fake diretamente |
| Precedência de checagens implementada fora de ordem sem que nenhum teste caia | Oito cenários de par duplo com o erro esperado nomeado (§5.16), distribuídos pelas Tasks 07–13, e mutação real na auditoria |
| `frozenset`/`tuple` em dataclass gerar atrito de igualdade nos testes "campo a campo" | Results são `frozen` com igualdade por valor (Task 04 fixa isso por teste); a comparação é sobre o `EmployeeResult`, nunca sobre `Employee` (que compara só por id) |
| `PLR0913` do ruff em construtor de use case com muitas dependências | Nenhum use case desta Stage passa de 3 dependências; se aparecer, seguir o precedente da 2.2 (`noqa` local justificado) e registrar `[decision]` em §7 |

## 6. Referências

- [`./concept.md`](./concept.md) — contratos (§4, com as 12 leis), invariantes e
  precedência (§5), casos de erro (§6), findings (§10), critérios de aceite
  (§11).
- ADRs desta Stage: [`../../adr/3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md`](../../adr/3_2_0001-cross-aggregate-guards-in-use-case-and-port-law.md),
  [`../../adr/3_2_0002-tenant-scoped-repository-signatures.md`](../../adr/3_2_0002-tenant-scoped-repository-signatures.md),
  [`../../adr/3_2_0003-copy-employee-full-duplication.md`](../../adr/3_2_0003-copy-employee-full-duplication.md),
  [`../../adr/3_2_0004-granular-use-cases-over-partial-update.md`](../../adr/3_2_0004-granular-use-cases-over-partial-update.md),
  [`../../adr/3_2_0005-job-function-has-no-lifecycle-state.md`](../../adr/3_2_0005-job-function-has-no-lifecycle-state.md),
  [`../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md`](../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md)
- ADRs consumidos: 3.1.0001, 3.1.0002, 3.1.0004, 3.1.0005, 3.1.0006; 2.2.0003,
  2.2.0004, 2.3.0003, 2.3.0005. **Superseded:** 3.1.0003 → 3.2.0005.
- [`../3.1-staff-domain/technical.md`](../3.1-staff-domain/technical.md) §7 —
  a `[decision]` sobre `deactivate`/`reactivate` idempotentes da `JobFunction`
  **deixa de valer** com a Task 01.
- [`../2.2-identity-application/technical.md`](../2.2-identity-application/technical.md)
  — precedente de plano de camada application (port + fake no mesmo commit,
  `_conforms`, teste-espelho de erros).
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) §3.1,
  §3.2, §3.6, §3.7.
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §5, §7;
  [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §1, §4, §6; `.importlinter`.
- Skills: `task-ordering-hex`, `pytest-with-fakes`, `hex-arch-python`,
  `import-linter-rules` (Task 03).

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

---

### 2026-08-08 — [decision] tests/fakes/features/staff (Task 05) — executor

**Contexto:** o plano da Task 05 fixa que o holder `StaffFakes` e o helper
`staff_repositories()` vivem em `in_memory_staff_store.py`, "junto do store que
constroem". O que o plano não previu é que isso fecha um **ciclo de import**: os
dois fakes importam `InMemoryStaffStore` deste módulo (precisam dele no
construtor e na linha `_conforms`), então um import de topo dos fakes dentro do
módulo do store seria circular. O `PLC0415` do ruff (`import` should be at the
top-level) reprova o import local que resolve o ciclo.

**Pergunta:** onde ficam holder e helper, já que o plano os quer no módulo do
store e o import de topo é impossível?

**Opções:**
- A — mover holder e helper para um quarto arquivo (`staff_fakes.py`), quebrando
  o ciclo sem `noqa`, mas contrariando a alocação explícita do plano e criando
  arquivo fora da lista da Task.
- B — manter no módulo do store, com import **local** dentro de
  `staff_repositories()` e `# noqa: PLC0415` justificado inline. ✅ recomendada

**Decisão:** B

**Razão:** a alocação é decisão declarada do plano ("não é arquivo novo"), e o
ciclo é acidente de mecânica de import, não sinal de desenho errado — o holder
em si **não** depende dos fakes: é anotado com os dois `Protocol`, que é
justamente o que o torna reusável pela 3.3. O `noqa` local justificado é o
precedente que o próprio technical §5 já previa para o caso análogo do
`PLR0913`. Reversível barato: se a 3.3 preferir um módulo separado para o
holder, mover é um `git mv` sem mudança de contrato.

---

### 2026-08-08 — [finding] idioma de identificadores locais em `src/` — executor

**Contexto:** o Checkpoint C do bloco 3 apontou identificadores locais em
**português** dentro de `src/` — `homonima` e `renomeada`
(`rename_job_function.py`), `encontradas` e `ausentes` (`create_employee.py`) —
contra a regra de idioma de [`CONVENTIONS.md`](../../CONVENTIONS.md) §1 (*código
em inglês; PT só em docstrings, comentários e nomes de teste*). O precedente do
BC identity usa inglês nos locais.

**Por que não foi corrigido nesta Stage:** não é defeito introduzido aqui. A
Stage 3.1 **já mergeou** com o mesmo padrão (`indice`, `periodo`, `restantes`,
`existente` em `employee.py`), então corrigir só os quatro nomes desta Stage
deixaria o BC `staff` internamente incoerente — meio arquivo em cada idioma —
sem fechar a regra. A correção honesta é uma varredura do BC inteiro, que é
**escopo transversal** e não cabe no recorte desta Stage (nenhuma Task o
prevê, e mexer em `employee.py` por isso violaria o escopo estrito).

**Direção sugerida:** issue pós-Stage (branch `refactor/<issue>-...`, formato
pós-Stage de GIT-WORKFLOW §Branches) que renomeie os locais em PT de **todo** o
BC `staff` para inglês, num commit só, sem mudança de comportamento — o
`make check` verde é o gate suficiente, já que nenhum dos nomes atravessa
fronteira de módulo. Vale conferir no mesmo passo se `scripts/check_layout.py`
ou o ruff conseguem impedir a reintrodução, para não depender de revisão humana.

**Stage candidata:** nenhuma — é **pós-Stage** (chore/refactor transversal ao BC
`staff`), a ser aberto como issue própria após o merge do PR desta Stage.
Registrado aqui, e não só no relatório do checkpoint, porque finding que vive
fora da §7 não é varrido pelo pipeline.

---

### 2026-08-08 — [deviation] assinatura de `EmployeeRelocationError` — executor

**O que mudou vs. o plano:** a Task 03 descreve a mensagem do erro citando "a
`unit_id` gravada e a enviada" — dois parâmetros. A implementação recebe
**três**: `(employee_id, stored_unit_id, requested_unit_id)`.

**Por que ficou abaixo do limiar de perguntar:** o acréscimo é o `employee_id`,
que os outros **oito** erros do módulo já citam — a mensagem sem ele seria a
única do arquivo que não diz de qual registro fala, e um log de relocalização
sem o id é inútil para diagnóstico. Não muda contrato (o erro não é capturado
por assinatura em lugar nenhum), não muda tipo nem hierarquia, e a regra que o
plano de fato fixava — **não citar `tenant_id`**, porque é erro intra-tenant —
foi respeitada e está travada por teste
(`test_erro_de_relocalizacao_cita_as_duas_unidades_e_nao_o_tenant`).

---

### 2026-08-09 — [decision] o desligado é editável, e editar não reativa — sponsor

**Contexto:** a auditoria de testes independente aplicou 26 mutações à camada e
**onze** sobreviveram, apesar de 100% de cobertura de linha **e de desvio**.
Nove delas eram a mesma ausência: **nenhum teste da Stage jamais exercitou uma
operação de edição sobre um registro desligado**, porque todas as fixtures de
edição criavam `active=True`. Consequência: cada um dos seis use cases de edição
podia trocar o `active` preservado por um `active=True` fixo sem falhar; dois
podiam embutir `.reactivate()` e **ressuscitar o desligado em silêncio**; e a
leitura **oposta** (recusar a edição com um `raise`) também passava verde.

Este último ponto é o diagnóstico: a suíte não distinguia duas especificações
**contraditórias**, o que significa que o comportamento nunca esteve
especificado — apenas acontecia. Era gap de **concept**, não de teste: o
concept descrevia as seis operações (ADR 3.2.0004) e as duas transições
(ADR 3.2.0006) como features independentes e nunca dizia como interagem.

**Pergunta:** o que acontece quando uma das seis operações de edição é chamada
sobre um funcionário já desligado?

**Opções:**
- A — totalmente editável; nenhuma operação toca `active` ✅ recomendada
- B — desligado é somente leitura (erro novo nas seis operações)
- C — granular: identificação editável, dados de escala bloqueados

**Decisão:** A (**sponsor, 2026-08-09**, via sessão mestra)

**Razão:** corrigir o cadastro de quem saiu não é o mesmo ato que recontratá-lo,
e o sistema não deve obrigar um para conseguir o outro. A regra é
**ortogonalidade**, e é por isso que é barata: não custa guarda de estado, erro
novo nem ramo condicional. (B) faria a correção de um acento custar duas
transições que **mentem** sobre o que aconteceu; (C) é mais fiel à realidade,
mas cada operação precisaria de regra e teste próprios — e migrar de (A) para
(C) depois é **acréscimo**, não retrabalho, então (A) não fecha porta.

**Consequências no artefato:** concept regredido a `draft` e re-aprovado
(CONVENTIONS §3.2) com a regra em §5.7-bis e o critério de aceite em §11;
**ADR 3.2.0007** criado; Task extra `[3.2/task-14-extra]` com o teste por
operação. **Nenhuma mudança em `src/`** — a implementação já correspondia à
decisão; o que faltava era a propriedade estar travada.

---

### 2026-08-09 — [finding] a suíte travava resultado, não conduta — executor

**Contexto:** o Checkpoint C do bloco 3 provou que **quatro guardas
cross-agregado** podiam ser removidas do código de produção sem derrubar
nenhum dos 341 testes de então. O caso extremo: substituir o corpo inteiro do
`DeleteJobFunctionUseCase.execute` por uma única chamada a `delete` deixava a
suíte verde — a dependência `employees` era, para os testes, código morto, o
que esvaziava a razão de existir da Task 08.

**Causa comum:** o par de fakes impõe as leis dos ports por conta própria e
levanta **o mesmo tipo de erro** que o use case levantaria. Uma asserção sobre
o erro e o estado final é, portanto, satisfeita pelas **duas** arquiteturas —
com e sem guarda no use case. A tabela ao final do concept §5 declara duas
camadas de enforcement com limites honestos diferentes; sem observar a
**conduta**, só uma delas tinha teste.

**Direção aplicada nesta Stage:** os caminhos de rejeição passaram a asserir
`store.calls` — que a escrita **nem foi tentada** —, e as ordens de checagem
que o resultado não discrimina passaram a asserir que a guarda seguinte **nem
foi consultada**. Cobertos nos commits `e12ae5b`, `08b1a30` e `eae34e3`, e
aplicado preventivamente nas Tasks 10–13.

**Direção sugerida para as próximas Stages:** onde um fake impõe a mesma regra
que o use case, o teste do use case precisa de uma asserção de **conduta** — o
resultado sozinho não distingue as camadas. Vale imediatamente para a 3.3
(adapters reais impondo as mesmas leis) e para a 3.4 (o adapter HTTP não pode
ser o único a ter teste de uma regra que o use case também impõe).
**Stage candidata: `3.3-staff-persistence`.**

---

### 2026-08-09 — [decision] disposição dos achados dos Checkpoints C — executor

Registro consolidado das três revisões por agente independente sobre o diff
acumulado, para que a auditoria de PR não precise reconstruí-las do histórico.
Todos os achados foram **corrigidos**; nenhum foi refutado ou descartado.

| Bloco | Achado | Sev. | Disposição |
|---|---|---|---|
| 1 (Tasks 01–03) | partição 404 × não-404 dos erros era amostra, não partição — um 10º erro escaparia da checagem | minor | corrigido — `062b5cf` |
| 1 | `EmployeeRelocationError` com três parâmetros vs. dois no plano | minor | `[deviation]` acima |
| 1 | posição de `active` como último campo é provada por asserção vacuamente verdadeira | minor | sem ação (risco ≈ 0; todos os call-sites são keyword) |
| 2 (Tasks 04–06) | `_TODOS_OS_DTOS` literal — um 19º command sem `frozen` escaparia de três guardas | major | corrigido — `5155479` |
| 2 | `find_by_name` sem teste positivo: `.strip().lower()` passava verde | major | corrigido — `491a219` |
| 2 | `store.calls` sustentava critérios "sem tocar o port" com só 2 de 13 métodos travados | major | corrigido — `02da785` |
| 2 | docstring de `_tipos_folha` divergia da implementação | minor | corrigido — `5155479` |
| 2 | guarda estrutural rodava só nos 2 results, mas a docstring de `commands.py` prometia mais | minor | corrigido — `5155479` |
| 2 | ordem normativa inobservável em `JobFunctionRepository.update` | minor | corrigido — nota inline em `02da785` |
| 3 (Tasks 07–09) | quatro guardas cross-agregado removíveis sem quebrar teste | major | `[finding]` acima; corrigido em `e12ae5b`, `08b1a30`, `eae34e3` |
| 3 | docstring superdeclarava o alcance de um teste de tenant | minor | corrigido — `08b1a30` |
| 3 | um teste de criação sem releitura pelo port | minor | corrigido — `eae34e3` |
| 3 | identificadores locais em PT em `src/` | minor | `[finding]` acima — pós-Stage |

**Nota de método, para a próxima Stage:** os três blocos convergem no mesmo
defeito de raciocínio — **listas literais e representantes estreitos**. Uma
tupla de DTOs que ninguém confronta com o módulo, uma partição de erros que
ninguém prova completa, um `calls` que ninguém prova presente, uma fixture que
só cria `active=True`. Em todos, a cobertura era 100% e a mutação sobrevivia. O
antídoto que funcionou foi sempre o mesmo: **confrontar a lista com a fonte da
verdade por introspecção**, e asserir a propriedade em vez do caso.

---

### 2026-08-09 — [decision] disposição dos achados da auditoria de testes independente — executor

Companheira da tabela dos Checkpoints C acima, para a **outra** revisão
independente: a auditoria de testes por subagente (exigida pelo checklist de
§3), que aplicou **26 mutações** à camada e encontrou **11 sobreviventes**
apesar de 100% de cobertura de linha **e de desvio**. Os quatro achados e sua
disposição:

| Achado | Sev. | O que era | Disposição |
|---|---|---|---|
| F-01 | **blocker** | nenhum teste jamais exercitou edição sobre registro **desligado** (todas as fixtures criavam `active=True`) — 9 mutações sobreviviam, duas delas ressuscitando o desligado em silêncio | gap de **concept**, não de teste → decisão do sponsor + **ADR 3.2.0007** + `[3.2/task-14-extra]` — `194f36a` (entrada acima) |
| F-02 | major | o docstring do fake declara a ordem das três guardas do `update` (existência → unidade → conjunto) como contrato, mas inverter L-E3 ↔ L-E4 não derrubava nada: nenhum cenário fazia as duas falharem juntas | corrigido — `5ffc80b`; o docstring foi **mantido** (não relaxado) porque a 3.3 herda o método como especificação executável: lá um adapter que ordenasse ao contrário responderia erro sobre o **catálogo** a uma tentativa de relocalização do **registro** |
| F-03 | major | `InvalidIdentifierError` declarado no concept §6 e em três blocos `Raises:` com **zero** ocorrências nos testes da camada | corrigido — `5ffc80b`; travado nos três caminhos, cada um pela sua **conduta**, que é o que os distingue (`create_job_function` falha sem tocar o port; `create_employee`, depois de resolver as funções; `copy_employee_to_unit`, depois de carregar a origem) |
| F-04 | minor | a determinância de `sorted(ausentes)[0]` na mensagem de erro não estava travada — um `[-1]` passava, e como `frozenset` não tem ordem a mensagem mudaria entre execuções | corrigido — `5ffc80b`; travada nos **três** produtores (use case de criação, de atribuição e a guarda do fake) |

**Mutação → resultado após os dois commits:** MU-01/02/03/04/21/24 (`active=True`
fixo nos seis use cases de edição) morrem; MU-05b/05c (`.reactivate()` embutido)
morrem; MU-05 (leitura oposta, `raise`) morre; MU-08 (inverter L-E3 ↔ L-E4 no
fake) morre; MU-11 (`sorted(...)[0]` → `[-1]`) morre. **MU-09/MU-10 (ordem das
listagens) sobrevivem de propósito** — ver o `[finding]` seguinte.

---

### 2026-08-09 — [finding] ordenação estável das listagens de staff — auditoria da Stage

**Contexto:** `list_by_unit` (lei L-E6) e `list_by_tenant` (lei L-JF5) **não
declaram ordem**, e nenhum teste da Stage a fixa. A omissão é **deliberada e
correta nesta camada**: travar a ordem contra os fakes quebraria o reuso desta
suíte como teste de contrato contra o Postgres na 3.3, onde um `SELECT` sem
`ORDER BY` não garante ordem nenhuma. Por isso as mutações MU-09/MU-10 da
auditoria de testes **sobrevivem de propósito**, e o commit `5ffc80b` registrou
a nota no corpo.

**Por que vira `[finding]` mesmo assim:** a decisão vivia só no corpo de um
commit e no corpo do PR. Em Postgres, `SELECT` sem `ORDER BY` devolve ordem
**instável entre planos** (mudança de estatística, index scan × seq scan,
paralelismo), e a Stage **3.4 vai paginar** essa listagem — paginação sobre
ordem instável **duplica e omite linhas** entre páginas, com a suíte verde e sem
erro em lugar nenhum. Não é defeito desta camada; é uma decisão que **precisa
existir** na camada que tem o `ORDER BY`.

**Direção sugerida:** a 3.3 define uma **ordenação determinística** para as duas
listagens (candidato natural: chave de negócio + `id` como desempate, para que a
ordem seja **total** e não só estável em campo não-único), fixa-a como lei do
port — passando a valer para o fake e para o adapter real — e cobre-a nos testes
de contrato. Feito isso, MU-09/MU-10 passam a morrer legitimamente. **É
pré-requisito da paginação da 3.4**, e é mais barato antes do `ORDER BY` existir
do que depois de a borda ter paginado sobre ele.

**Stage candidata:** `3.3-staff-persistence`.

**Nota de forma:** o concept §10 declara sua lista de `[finding]` como "a lista
canônica desta Stage", e este é o **quinto**. Ele entra aqui, e não lá, porque a
Fase 4 já fechou: CONVENTIONS §3.2 encaminha explicitamente as revisões
posteriores ao início da execução para a §3.4 — isto é, para esta seção — "sem
mudar status", e a §7 é varrida pelo pipeline pelo mesmo critério que a §10
(o que não é varrido é finding que vive só no corpo de um ADR ou de um commit,
que era exatamente o caso deste antes desta entrada). Regredir o concept a
`draft` para acrescentar uma linha de escalonamento pós-execução seria cerimônia
sem ganho de rastreabilidade.

---

### 2026-08-09 — [decision] Fase de aplicação da auditoria da Stage (skill `stage-audit`) — Sessão mestra + Claude (subagente de aplicação)

**Contexto:** a auditoria read-only da Stage 3.2 (PR #36) **aprovou sem
bloqueantes**, com 4 findings, e validou **item a item, com evidência própria**,
todos os critérios do concept §11 e todos os itens do checklist de §3 deste
technical. Gates reproduzidos pela auditoria: `make check` **exit 0**;
**1511 passed**; cobertura **99.91% global** e **100% nos 28 arquivos** de `src/`
tocados pela Stage; `lint-imports` **9 kept / 0 broken** (incluindo o contrato
novo `staff-application-purity`); `check_technical_postexec.py` OK;
`make docs-check` **exit 0**. Esta entrada é o registro da fase de aplicação
(commits `[3.2/--]`).

**Disposição dos 4 findings:**

| # | Finding | Disposição |
|---|---|---|
| F1 | `workforce.md` (doc de domínio `accepted`, **acima** dos concepts) ainda declarava aberta a lacuna do ciclo de vida da **função** (§3.2 e §6) — fechada duas vezes e em direções opostas — e **não mencionava** o ciclo de vida do **funcionário**, que virou regra canônica | corrigido — lacuna de §3.2 fechada com nota datada apontando o ADR 3.2.0005; ciclo de vida do funcionário acrescentado a §3.1 (ADRs 3.2.0006/3.2.0007); §1, §6, §7 e frontmatter (`updated_at`, `references`) alinhados |
| F2 | ordenação das listagens não declarada, decisão viva só no corpo do PR/commit — pré-requisito da paginação da 3.4 | escalado — `[finding]` acima, Stage candidata `3.3-staff-persistence` |
| F3 | o commit `5ffc80b` (`[3.2/task-15-extra]`) não tinha entrada na §7, enquanto o `[3.2/task-14-extra]` tinha | corrigido — `[decision]` "disposição dos achados da auditoria de testes independente" acima |
| F4 | caixas do concept §11 e do checklist de §3 por marcar, apesar de validadas | tratado — ver abaixo |

**Decisão sobre as caixinhas do §3:** o flip literal `[ ]`→`[x]` do §3 fica
**adiado para pós-merge** — o freeze do `status: done` (CONVENTIONS §3.4,
`scripts/check_technical_postexec.py`) rejeita edição fora da janela §7 enquanto
a Stage não mergeia. Mesmo tratamento da Stage 3.1 (§7 do
`3.1-staff-domain/technical.md`, entrada de 2026-07-29). A validação de cada
item vive nesta entrada e no comentário de veredito do PR #36; as caixinhas do
concept §11 (sem freeze programático) foram marcadas no mesmo lote de commits
desta entrada.

**Verificações funcionais e checklist de fechamento de §3 — validados pela
auditoria:** fluxo ponta-a-ponta da Task 13 verde com os 16 use cases reais
sobre a mesma bateria de fakes; ausência de superfície de runtime declarada
explicitamente (a API é da 3.4, a persistência é da 3.3); cobertura ≥ 90% **em
cada arquivo tocado** (todos em 100%, incluindo as duas entidades de
`domain/entities/` modificadas nas Tasks 01–02); `staff-application-purity`
**KEPT**; as 13 Tasks commitadas com seu check; commit `stage 3.2: complete`
aplicado; `roadmap.md` com a Stage `done`, datas de hoje, linha no §Histórico e a
nota de reconciliação em quatro eixos; ADRs 3.2.0001–3.2.0007 em
`status: accepted` e 3.1.0003 em `superseded`. O único item do checklist que a
auditoria **reabriu** foi o último ("`concept.md` não precisa de retoque
retrospectivo"): o retoque necessário não era do concept, e sim do doc de
domínio acima dele — F1.

**Observação sem ação nesta Stage:** `scripts/check_commit_msg.py` aceita só
`[N.M/task-NN]` e `[N.M/--]` (regex `task-\d{2}`), sem reconhecer os sufixos
`-fix` e `-extra` que a prática usa desde a 2.5/3.1 e que esta Stage usou em oito
commits. Já coberto pela issue [#34](https://github.com/MarceloSanC/restaurant-hub/issues/34)
(aberta pela auditoria da 3.1), estendida por comentário para incluir `-extra`.

<!-- END: post-execution -->

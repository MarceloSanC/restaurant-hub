---
title: Technical — Use cases da escala
description: Plano de execução da Stage 4.3 — doze Tasks inside-out (no-op no domínio, erros, quatro ports com fakes e leis, DTOs, insumo, protocolo de publicação, sete use cases, propriedade de autorização), cada uma com o seu commit verde
when-use: Consultar durante a Fase 4 desta Stage; cada Task tem arquivos, critério de aceite e comando de verificação
keywords: [technical, plano de execução, scheduling-application, use-case, publicar, aceite, staff-read-port, access-guard]
status: done
created_at: 2026-11-01
updated_at: 2026-11-01
stage_id: 4.3-scheduling-application
stage_title: Use cases da escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.2-validation-policies]
concept_ref: ./concept.md
issue_id: 72
branch: feat/72-4-3-scheduling-application
tasks_count: 12
---

# Technical — Stage 4.3 — Use cases da escala

> **Como usar:** executar as Tasks em ordem; 1 Task = 1 commit
> `<type>(scheduling): <descrição> [4.3/task-NN]` (CONVENTIONS §4). Sob orquestração autônoma
> (PROMPT-stage-single-session §REGRA DE PR), checks locais focados e `make check` no Actions do
> PR. Decisão não prevista → `[decision]` na §7.
>
> **Verificação padrão de toda Task com `src/`** (além da específica): `uv run pytest <testes da
> Task>`, `uv run python scripts/check_layout.py`, `uv run lint-imports`,
> `uv run mypy src tests/fakes`, `uv run ruff check` + `ruff format --check` nos arquivos tocados.
> Todo `__init__.py` novo leva só docstring (regra 9).

## 1. Contexto e estratégia de execução

### Resumo

Camada `application` do BC scheduling: `errors.py`, quatro ports de saída (`AccessGuard`,
`StaffReadPort`, `ScheduleRepository`, `ScheduleConfigRepository`) com fakes e suítes de lei, os
DTOs, dois módulos privados (`_inputs.py` — insumo; `_publish.py` — protocolo de publicação) e sete
use cases. Mais o no-op de `change_demand_quantity` no domínio (D2) e as notas datadas (D1/D2).

### Estratégia

Inside-out (skill `task-ordering-hex`): domínio → erros → ports + fakes (cada port com o seu fake e
a sua lei no mesmo commit, sem adapter — a 4.4 o traz) → DTOs → insumo e protocolo (funções puras
sobre os ports) → use cases → a propriedade transversal sobre a pasta `use_cases/` por último
(totalidade: com ela antes, cada use case novo deixaria o build vermelho entre commits). Cada use
case nasce com o seu teste de autorização local; a varredura da Task 12 trava a pasta.

### Pré-condições

- 4.2 `done` e mergeada (PR #66); concept 4.3 `done` (ef290b6).

### Premissas técnicas

- Python 3.12, mypy strict sobre `src/` e `tests/fakes/`; testes unitários e de contrato sem banco
  (só fakes nesta Stage — nenhum adapter real).

### Estrutura de pastas afetada

```
src/restaurant_hub/features/scheduling/
├── domain/entities/schedule.py                      (D2)
└── application/
    ├── errors.py
    ├── dtos/{__init__,commands,queries,results}.py
    ├── ports/__init__.py, ports/out/{__init__,access_guard,staff_read_port,
    │                                  schedule_repository,schedule_config_repository}.py
    └── use_cases/{__init__,_inputs,_publish,create_schedule,evaluate_schedule,publish_schedule,
                   get_schedule,get_calendar,list_past_schedules,get_my_schedule}.py
tests/
├── fakes/features/scheduling/{__init__,in_memory_access_guard,in_memory_staff_read,
│                              in_memory_schedule_repository,in_memory_schedule_config_repository}.py
├── contract/features/scheduling/{__init__,test_staff_read_port_laws,test_schedule_repository_laws}.py
└── unit/features/scheduling/application/{__init__,test_*.py}
```

## 2. Tasks

### Task 01 — No-op de `change_demand_quantity` no domínio (D2)

- **Arquivos:** `src/.../domain/entities/schedule.py`;
  `tests/unit/features/scheduling/domain/test_schedule_breaks.py`;
  `docs/stages/4.1-scheduling-domain/concept.md` (errata datada no CA11b);
  `docs/roadmap.md` (nota de reconciliação da 4.1, linha editada **no lugar**, sem deslocar linhas).
- **Descrição:** `change_demand_quantity` devolve `self` quando `quantity == demanda.quantity`,
  antes de qualquer outra coisa; docstring da raiz passa a "cinco"; `_NO_OPS` ganha o caso e o
  teste da lei vira `test_as_cinco_idempotentes_...` com `len == 5`.
- **Aceite:** CA12 (parte de domínio).
- **Verificação:** `uv run pytest tests/unit/features/scheduling/domain -q`; ruff; mypy.

### Task 02 — Erros da application e contrato de pureza

- **Arquivos:** `src/.../application/errors.py`; `.importlinter`
  (`scheduling-application-purity`); `tests/unit/test_status_map.py` (piso 22 → 34);
  `tests/unit/features/scheduling/application/{__init__,test_errors}.py`.
- **Descrição:** as 12 exceções do concept §4 (filhas de `SchedulingError`; três também
  `NotFoundError`, nessa ordem de MRO); as que carregam estado o expõem como atributo
  (`current_version`, `violations`, `assignment_ids`). Contrato de pureza espelhando o de staff.
- **Aceite:** CA23; hierarquia testada (varredura do módulo: toda classe herda de
  `SchedulingError`; os três `NotFoundError`).
- **Verificação:** pytest dos dois testes; `uv run lint-imports`; mypy.

### Task 03 — Port `AccessGuard` de scheduling, fake e leis

- **Arquivos:** `src/.../application/ports/{__init__,out/__init__,out/access_guard}.py`;
  `tests/fakes/features/scheduling/{__init__,in_memory_access_guard}.py`;
  `tests/unit/features/scheduling/application/test_access_guard_laws.py`.
- **Descrição:** `Actor`, três permissões, `AuthorizedScope(tenant_id, unit_id, user_id)`,
  `AccessGuard.authorize(actor, permission, *, tenant_id, unit_id)`; leis L-SG1–L-SG4 na
  docstring. Fake com `grants` por tripla exata, `FakeActor(id, tenant_id, user_id)`, sentinela de
  recusa e `calls` com o alvo; linha `_conforms`.
- **Aceite:** CA21 (guard).
- **Verificação:** pytest do teste de leis; mypy `src tests/fakes`.

### Task 04 — Port `StaffReadPort`, fake e suíte de lei

- **Arquivos:** `src/.../application/ports/out/staff_read_port.py`;
  `tests/fakes/features/scheduling/in_memory_staff_read.py`;
  `tests/contract/features/scheduling/{__init__,test_staff_read_port_laws}.py`.
- **Descrição:** `StaffMember`, `JobFunctionEntry`, quatro leituras; fake semeável (registros com
  unidade, tenant, ativo, `user_id`; catálogo por tenant) com registro de chamadas; suíte L-ST1–L-ST5
  parametrizada por fixture de implementação (só o fake; a 4.4 acrescenta o real).
- **Aceite:** CA21 (staff).
- **Verificação:** pytest da suíte; mypy.

### Task 05 — DTOs: operações, commands, queries e results

- **Arquivos:** `src/.../application/dtos/{__init__,commands,queries,results}.py`;
  `tests/unit/features/scheduling/application/test_dtos.py`.
- **Descrição:** as 11 operações + `ScheduleOperation` (união) + `ViolationAcknowledgement(key,
  observed, limit)` + 2 commands; 5 queries; os 9 results com mapeadores **no mesmo arquivo**, um
  sítio por classe (regra 8): `to_schedule_summary_result`, `to_schedule_result`,
  `to_evaluation_result`, `to_calendar_result`, `to_my_schedule_result` (os aninhados construídos
  por funções privadas únicas). Os mapeadores recebem o agregado + um índice de staff
  (`Mapping[EmployeeId, StaffMember]`) + nomes de função e filtram alocações de não-ativos (§5.14)
  e ordenam (§5.20). Todo DTO `frozen`, sem método (regra 7); ator `repr=False`.
- **Aceite:** CA13/CA27 (nos mapeadores); regra 7/8 verdes.
- **Verificação:** pytest `test_dtos.py`; `uv run python scripts/check_layout.py`; mypy.

### Task 06 — `ScheduleRepository` e `ScheduleConfigRepository`, fakes e suíte de lei

- **Arquivos:** `src/.../application/ports/out/{schedule_repository,schedule_config_repository}.py`;
  `tests/fakes/features/scheduling/{in_memory_schedule_repository,in_memory_schedule_config_repository}.py`;
  `tests/contract/features/scheduling/{test_schedule_repository_laws,test_schedule_config_repository_laws}.py`;
  `tests/unit/test_check_layout.py` (igualdade das escritas da regra 10 + `ScheduleRepository.add/save`).
- **Descrição:** `ScheduleChange`, cinco métodos, leis L-SC1–L-SC8 e L-CF1 nas docstrings; o fake
  grava estado e `ScheduleChange` juntos (`changes_of(schedule_id)`), impõe L-SC1/2/4 com os erros
  da Task 02 e registra chamadas (`calls`) para os testes de "nada gravado"; o fake de config
  também registra `calls`. **`ScheduleChange` e `SchedulingSettings` não definem método algum**
  (nem `__post_init__`): a regra 10 classifica como escrita todo método não-leitura de classe em
  `*_repository.py`, e a igualdade de `test_check_layout.py` reprovaria. Suíte L-CF1 em arquivo
  próprio (config do tenant; `None` sem config; nunca a de outro tenant).
- **Aceite:** CA21 (repositórios); CA02 (parte do `save`).
- **Verificação:** pytest da suíte + `tests/unit/test_check_layout.py`; check_layout; mypy.

### Task 07 — Insumo (`_inputs.py`) e `create_schedule`

- **Arquivos:** `src/.../application/use_cases/{__init__,_inputs,create_schedule}.py`;
  `tests/unit/features/scheduling/application/{conftest,test_create_schedule}.py`.
- **Descrição:** `_inputs`: `settings_of` (config ou defaults — sítio único), `require_day`/
  `require_range` (`InvalidScheduleRequestError`), `neighbours_of`, `load_staff` (união por
  `employee_id`, `MissingStaffRecordsError` para alocados ausentes) e `facts_of`. `conftest.py` com
  o cenário semeado (fakes + relógio fixo + ids). Create conforme §5.3.
- **Aceite:** CA01, CA19 (create), CA26 (defaults/config).
- **Verificação:** pytest dos testes de application; mypy; check_layout.

### Task 08 — Protocolo de publicação (`_publish.py`)

- **Arquivos:** `src/.../application/use_cases/_publish.py`;
  `tests/unit/features/scheduling/application/test_publish_protocol.py`.
- **Descrição:** `check_creation_ids`, `apply_operations` (pré-checagens por operação: alvo de
  `AssignEmployee`, catálogo, `TimeRange` de `RescheduleBand`, D3; `function_exception` derivado;
  efetivas por identidade), `introduced(before, after)` (desvio com sinal; sobre-cobertura por
  demanda), `pending(introduced_warns, acks)`.
- **Aceite:** CA04 (parte), CA08, CA09, CA10, CA11, CA12, CA14, CA19 (reschedule), CA20,
  CA22 (ids).
- **Verificação:** pytest; mypy.

### Task 09 — `evaluate_schedule` e `publish_schedule`

- **Arquivos:** `src/.../application/use_cases/{evaluate_schedule,publish_schedule}.py`;
  `tests/unit/features/scheduling/application/{test_evaluate_and_publish,test_schedule_flow}.py`.
- **Descrição:** fluxo do concept §9; publish grava uma `ScheduleChange` (autor do escopo, `Clock`,
  versão anterior, efetivas, aceitas) ou nada no lote sem efeito.
- **Aceite:** CA02, CA04, CA05, CA06, CA07, CA10 (publish grava sobre `block` pré-existente e a
  mostra em `violations`), CA12 (lote só de no-ops ⇒ nenhum `save`; lote misto ⇒ trilha e versão
  sem os no-ops), CA16, CA22, CA25, CA26.
- **Verificação:** pytest; mypy; check_layout (regra 10: uma escrita).

### Task 10 — Leituras: `get_schedule`, `get_calendar`, `list_past_schedules`

- **Arquivos:** `src/.../application/use_cases/{get_schedule,get_calendar,list_past_schedules}.py`;
  `tests/unit/features/scheduling/application/test_read_use_cases.py`.
- **Aceite:** CA13, CA15, CA16 (get, calendário), CA18, CA19 (`datetime` em `first_day`/
  `last_day`/`before`), CA26 (get), CA27.
- **Verificação:** pytest; mypy.

### Task 11 — `get_my_schedule`

- **Arquivos:** `src/.../application/use_cases/get_my_schedule.py`;
  `tests/unit/features/scheduling/application/test_get_my_schedule.py`.
- **Aceite:** CA17, CA19 (`datetime` no recorte).
- **Verificação:** pytest; mypy.

### Task 12 — Propriedade de autorização sobre a pasta e nota datada D1

- **Arquivos:** `tests/unit/features/scheduling/application/test_use_cases_authorize.py`;
  `docs/domain/scheduling/shift-scheduling.md` (nota datada D1, no fim da §6, sem deslocar
  citações por linha existentes).
- **Descrição:** tabela por módulo da pasta (montagem por nome de parâmetro do construtor); guard
  que nega ⇒ sentinela `is` e nenhum `calls` novo em fake, relógio ou gerador; guard permissivo ⇒
  `authorize` exatamente (permissão, tenant, unidade) do command; AST: 1ª instrução do `execute`
  (descontado o docstring) é `self._guard.authorize(...)` com permissão constante do port, na forma
  da tabela — `Assign` a um nome (o escopo) **só** em `create_schedule`, `publish_schedule` e
  `get_my_schedule`, e esse nome só é lido como `.user_id`; `Expr` nos outros quatro; tabela ==
  pasta. Relógio espião local (subclasse de `FakeClock` que conta `now()`) prova "nenhum relógio
  lido" sob guard que nega. Guard adversarial local (escopo com tenant/unidade inventados) prova
  que leitura e efeito caem no endereço do command (§5.1). Varredura das anotações de retorno de
  `execute`: nenhum use case devolve entidade do domínio (LAYOUT §7).
- **Aceite:** CA03.
- **Verificação:** pytest; ruff.

## 3. Gate de saída da Stage

### Verificações automatizadas
- `make check` verde no Actions do PR (lint, mypy, layout, import-linter, docs-check, testes, cobertura).
- Cobertura ≥ 90% por arquivo da Stage (`pytest --cov=src/restaurant_hub/features/scheduling --cov-report=term-missing`).
- `python scripts/check_technical_postexec.py docs/stages/4.3-scheduling-application/technical.md`.

### Verificações funcionais
- Sem superfície de runtime (HTTP é 4.5; adapters são 4.4): o fluxo editar → avaliar → aceitar →
  publicar → ler roda pelo teste de fluxo com fakes (Task 09).

### Checklist de fechamento da Stage
- [ ] Checkpoints A/B/C e Auditoria de Testes com achados dispostos.
- [ ] §7 reflete a execução; findings com Stage candidata.
- [ ] `roadmap.md`: 4.3 `done`, `updated_at`/`last_reviewed_at`.
- [ ] `HANDOFF-SESSION-2026-10-21.md` removido antes do PR.

## 4. Ordem de dependência entre Tasks

01 → 02 → 03 → 04 → 05 (usa `Actor` de 03 e `StaffMember` de 04) → 06 (usa `ScheduleOperation` de
05 e erros de 02) → 07 → 08 → 09 → 10 → 11 → 12.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Regra 8 (um sítio por result) quebra com results aninhados | funções privadas `_to_*` únicas em `results.py` |
| Regra 10 conta `save` dentro de helper | escrita só no `execute` (nunca em `_publish`/`_inputs`) |
| Task 12 acha use case que lê porta antes de autorizar | corrigir o use case (`task-12-fix`) |

## 6. Referências

concept 4.3; ADRs 4.3.0001–4.3.0004; skills `pytest-with-fakes`, `task-ordering-hex`,
`hex-arch-python`; staff 3.7 (`test_use_cases_authorize.py`, `in_memory_access_guard.py`).

## 7. Execução (post-hoc, editável após done)

<!-- BEGIN: post-execution -->

### 2026-11-01 — [decision] Fase 3A — retomada do handoff e forks P delegados — Claude (orquestração autônoma)
**Contexto:** a Fase 3A foi refeita a partir do `HANDOFF-SESSION-2026-10-21.md` (rascunho do concept, 20 registros E/C, D1–D3) sobre o `develop` de 2026-11-01, que já trazia as Stages 2.6, 3.7 e 3.8.
**Pergunta:** D1 (violação induzida por staff), D2 (`change_demand_quantity` com o mesmo N), D3 (faixa presa só por desligado); revalidar C(1) AccessGuard próprio e C(4) sem unit of work.
**Opções:**
- D1 (a) mostrar e corrigir ✅ recomendada · (b) guarda em staff
- D2 (b) no-op no domínio ✅ recomendada · (a) no use case
- D3 (b) recusar com contagem + ids de alocação ✅ recomendada · (a) recusa opaca · (c) remover junto (excluída por evidência)
**Decisão:** as três recomendadas — **P delegado** pelo sponsor ao orquestrador e ratificado em 2026-11-01. C(1) mantida e reaplicada **por BC** contra o ADR 3.7.0001 já em `develop` (ADR 4.3.0002); C(4) mantida contra o ADR 2.6.0002 §5 (uma escrita por use case, regra 10 sem unit — ADR 4.3.0004).
**Razão:** concept §7 e ADRs 4.3.0001–4.3.0004.

### 2026-11-01 — [decision] Checkpoint A — aceite carrega o limite visto; desvio com sinal; ausente com erro próprio — Claude
**Contexto:** os dois revisores do Checkpoint A mostraram que o aceite `(key, observed)` não pegava piora pelo `limit` (reduzir N depois de avaliar) e que `|observed − limit|` deixava passar subcarga que vira sobrecarga em `both`; e que o registro ausente era incoerente entre leituras.
**Pergunta:** como casar o aceite e como comparar a medida.
**Opções:**
- A — aceite só com `observed`, magnitude sem sinal
- B — aceite com `(key, observed, limit)`; desvio com sinal; troca de sinal ou magnitude maior = introduzida ✅ recomendada
**Decisão:** B, e `MissingStaffRecordsError` com os ids das alocações em toda leitura/escrita que toca a escala.
**Razão:** fecha o finding de sobre-cobertura da 4.2 e o contra-exemplo de `both`; concept §5.6, §5.7, §5.12 corrigidos antes do `conceptual approved`.

### 2026-11-01 — [deviation] Task 05 — conftest dos testes da application antecipado — Claude
**Contexto:** os testes de DTO da Task 05 precisavam dos construtores de escala e de registro; o technical listava o `conftest.py` na Task 07.
**Razão:** o `conftest.py` nasceu na Task 05 só com construtores e cresceu na 06/07 (fakes de repositório, relógio que conta leituras). Nenhum arquivo de `src/` fora da lista.

### 2026-11-01 — [deviation] Task 08 — `test_inputs.py` e `load_for_edit` — Claude
**Contexto:** o Checkpoint C do bloco 2 pediu os limites de `require_range`/`require_limit` testados nas bordas; o teste foi para `tests/unit/.../application/test_inputs.py` (arquivo não listado). Na Task 09, a carga com checagem de versão (`load_for_edit`) entrou em `_publish.py`, compartilhada por avaliar e publicar.
**Razão:** mesmo escopo da Task; sem novo contrato.

### 2026-11-01 — [deviation] Task 12-fix — identificadores locais da application em inglês — Claude
**Contexto:** o Checkpoint C do bloco 3 apontou variáveis locais em português no código novo de `src/`, contra CONVENTIONS §1 "Idioma do código".
**Razão:** renomeadas por token (docstrings e comentários intactos), commit `refactor(scheduling)` sem mudança de comportamento. Os nomes de teste seguem o estilo PT já estabelecido no repo.

### 2026-11-01 — [deviation] Tasks extras da auditoria de testes marcadas `task-12-extra` — Claude (auditoria de contexto limpo)
**Contexto:** as rodadas da auditoria de testes (5, com mutação real) entraram em três commits `test(scheduling)` marcados `[4.3/task-12-extra]` — `396b61b` (lacunas da rodada 1), `51916e8` (registro inativo alocado) e `bb27217` (sobreviventes das rodadas 3 e 4). CONVENTIONS §4(a) "Marca de Task", regra 2, pede numeração acima do `tasks_count` (`task-13-extra`, `task-14-extra`…) e uma Task extra por rodada, com a justificativa nesta §7.
**Razão:** registro retroativo da justificativa (só testes, nenhuma mudança em `src/`, todos na pasta `tests/unit/features/scheduling/application/`). As marcas ficam como estão — regra 5 (o histórico não se reescreve; o hook não confere o `NN`).

### 2026-11-01 — [finding] Idioma do código — variáveis locais em português no domínio já mergeado — Claude
**Contexto:** `src/restaurant_hub/features/scheduling/domain/entities/schedule.py` (4.1, mergeado) usa locais em PT (`faixa`, `demanda`, `alocacao`…), contra CONVENTIONS §1. Esta Stage corrigiu só o código novo.
**Direção sugerida:** varredura de renomeação por token no domínio de scheduling (e staff, se houver), sem mudança de comportamento. **Stage candidata:** issue avulsa de refactor (scheduling).

### 2026-11-01 — [finding] Edição da configuração do restaurante sem dono no roadmap — Claude
**Contexto:** o Step 4 promete "bloquear/avisar configurável", a 4.3 só lê a config e a 4.5 é só borda HTTP; a permissão da config tenant-wide é lacuna da 4.5 (ADR 4.1.0004:79).
**Direção sugerida:** use case de escrita da config + método de escrita no port, com os requisitos do concept §13 (violação pré-existente por config alterada; 1–6 dias sem escala ao mudar o dia de início; janela sem período ao atrasar o corte). **Stage candidata:** alargar a 4.5 ou Stage própria antes do fechamento do Step 4.

### 2026-11-01 — [finding] Vincular login existente a registro — Claude
**Contexto:** concept 3.5 §13 e technical 3.8 §7 nomeiam a 4.3 "ou uma Stage de gestão de acesso anterior". Decidido fora (D-LINK): escrita em staff + identity.
**Direção sugerida:** Stage de gestão de acesso (staff + identity), com a checagem do tenant do `User` e a regra de fim de vínculo. **Stage candidata:** antes da 4.5. `get_my_schedule` os alcança sem mudança.

### 2026-11-01 — [finding] Persistência — guarda reversa, write skew e reparo do ausente — Claude
**Contexto:** registro removido em staff faz a escala (e as vizinhas) recusar com `MissingStaffRecordsError`; a guarda reversa é check-then-act entre BCs; publicações simultâneas em semanas adjacentes podem gravar violação de fronteira (write skew).
**Direção sugerida:** `has_allocations_for`/`has_demands_for` em staff, use case de reparo do ausente, mitigação do write skew; o 1º `find_by_user_id` decide escopo e índice (ADR 3.5.0004 Alt C); granularidade da trilha a partir de `ScheduleChange`. **Stage candidata:** 4.4.

### 2026-11-01 — [finding] Borda HTTP — formato dos ids e corpo das recusas — Claude
**Contexto:** ids de criação vêm do cliente (ADR 4.3.0004); `ScheduleVersionConflictError` carrega só a versão; `function_exception` não implica aceite.
**Direção sugerida:** UUID canônico na borda; corpo do 409 (versão ou estado); corpos de `BlockingViolationsError`/`UnacknowledgedViolationsError`/`InactiveAllocationsInUseError`; rótulo da marca de exceção; desativação de conta na 1ª permissão de auto-serviço (ADR 3.5.0003 §5); "minha escala" composta por unidade a partir dos vínculos do token. **Stage candidata:** 4.5.

### 2026-11-01 — [finding] Regra "todo use case autoriza o próprio alvo" transversal — Claude
**Contexto:** aplicada em staff (ADR 3.7.0001) e scheduling (ADR 4.3.0002) com ports de forma distinta; o ator não é autenticado fora da borda HTTP (mesmo modelo de ameaça).
**Direção sugerida:** ADR transversal quando o 3º BC a repetir; autenticação de ator no 1º driver não-HTTP. **Stage candidata:** a do 3º BC / a do 1º driver não-HTTP.

### 2026-11-01 — [finding] Suíte de contrato do `ScheduleRepository` lê a trilha por API do fake — Claude
**Contexto:** a fixture `trail_of` do conftest só sabe ler a trilha do fake (`changes_of`).
**Direção sugerida:** a 4.4 acrescenta ao conftest o leitor da tabela de auditoria do adapter Postgres junto com o `params`. **Stage candidata:** 4.4.

<!-- END: post-execution -->

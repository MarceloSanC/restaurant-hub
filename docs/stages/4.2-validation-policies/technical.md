---
title: Technical — Políticas de validação configuráveis
description: Plano de execução da Stage 4.2 — dez Tasks inside-out (exceções, config, VOs, insumo, nove políticas, avaliador), cada uma com o seu commit verde
when-use: Consultar durante a Fase 4 desta Stage; cada Task tem arquivos, critério de aceite e comando de verificação
keywords: [technical, plano de execução, validation-policies, avaliador, politica, violacao]
status: done
created_at: 2026-10-18
updated_at: 2026-10-18
stage_id: 4.2-validation-policies
stage_title: Políticas de validação configuráveis
step_id: 4
step_title: Escala manual publicável
depends_on: [4.1-scheduling-domain]
concept_ref: ./concept.md
issue_id: 64
branch: feat/64-4-2-validation-policies
tasks_count: 10
---

# Technical — Stage 4.2 — Políticas de validação configuráveis

> **Como usar:** ler §1; executar as Tasks em ordem (1 Task = 1 commit,
> `<type>(scheduling): <desc> [4.2/task-NN]` + `Refs #64`); não avançar sem verificação verde;
> o não previsto vai para §7 conforme o RUNBOOK Passo 8.

## 1. Contexto e estratégia de execução

### Resumo
Domínio puro em `features/scheduling/domain/`: dois `StrEnum` + regra + config com os defaults
legais (`value_objects/validation_config.py`), a `Violation` com `key`
(`value_objects/violation.py`), os fatos de staff por dados (`value_objects/employee_facts.py`),
o insumo do serviço com a projeção de alocações (`services/validation/context.py`), o protocolo,
nove políticas e o avaliador (`services/validation/`). Duas exceções novas em `errors.py`.

### Estratégia
**Inside-out dentro da camada `domain`** (skill `task-ordering-hex`, exceção "Stage de camada
única"): exceções → VOs → insumo + protocolo → políticas (das geométricas às agregadas) →
avaliador com o registro. Cada Task traz os testes no mesmo commit.

**Totalidades que ditam o corte** (`grep` feito na Fase 3B; memória "totalidades ditam o corte"):
- `tests/unit/features/scheduling/domain/test_exceptions.py` afirma **igualdade** do conjunto de
  exceções do módulo com uma lista fixa (`_AS_VINTE`, `_TOTAL_DE_EXCECOES = 20`) e cobra cada uma
  numa tabela de mensagem → as duas exceções novas nascem **juntas** na Task 01, com as entradas.
  `tests/unit/test_status_map.py` tem o piso `_TOTAIS_MINIMOS["scheduling"] = 20` (`>=`): sobe para
  22 na mesma Task, para o piso continuar medindo.
- `scripts/check_docs_claims.py` reprova caminho anotado `[planejado]` que já existe →
  `docs/LAYOUT.md` §2 (`services/ … [planejado]`) muda **na Task que cria o diretório** (04); e
  `tests/unit/test_check_docs_claims.py` trava por **igualdade** o conjunto de planejados do
  LAYOUT real (`_PLANEJADOS_DO_LAYOUT_REAL`, hoje `{…/domain/services}`) → vira `frozenset()` na
  mesma Task, com os comentários/docstrings que citam `services/` como planejado.
- `scripts/check_layout.py` regra 9: `__init__.py` novos só com docstring.
- `test_operational_calendar.py` varre o pacote por `time(5, 0)` e `Weekday.MONDAY`;
  `test_bc_independence.py` varre os imports **e os identificadores** (nomes, atributos, `def`,
  argumentos, keywords) contra o vocabulário de staff (`UnavailabilityPeriod`, `FixedSchedule`,
  `OnDemand`, `WorkloadProfile`, `DayPeriod` …) — esses nomes só em docstring.
- Ruff `PL` (PLR0911, máx. 6 `return`): `rule_for` não pode ser um `match` com 9 `return`; usa
  um mapeamento montado no método.
- Hook `commit-msg`: subject ≤ 100 caracteres.
- `vars(Schedule)` (`test_schedule.py`, `test_schedule_mutations.py`) e o total de mutações de
  `test_schedule_breaks.py`: **nenhuma** mutação nova na raiz (concept §1 Fora do escopo).
- O registro `DEFAULT_POLICIES` só nasce na Task 10, com o teste de totalidade × `PolicyKind`;
  antes dela as políticas são testadas direto, sem registro.

### Pré-condições
- Stage `4.1-scheduling-domain` `done` e mergeada (PR #63, `9380963`).
- Worktree com Postgres próprio (porta 5434, `DATABASE_URL` no `.env` da worktree) para o
  `make check` — a Stage não toca banco, mas a suíte sim.

### Premissas técnicas
- Python 3.12, `mypy --strict`; `Decimal` e `datetime` da stdlib.
- Cenários de teste das políticas montados por um módulo compartilhado
  `tests/unit/features/scheduling/domain/services/validation/scenario.py` (builders de `Schedule`
  com uma demanda por faixa, `EmployeeFacts` e `ValidationConfig`), importado como
  `tests.unit...` — precedente de import entre módulos de `tests/` em
  `tests/contract/features/identity/conftest.py`.

### Estrutura de pastas afetada

```
src/restaurant_hub/features/scheduling/domain/
├── exceptions/errors.py                      (mod)
├── value_objects/{validation_config,violation,employee_facts}.py
└── services/__init__.py
    └── validation/{__init__,context,policy_protocol,overlap_policy,unavailability_policy,
                    rest_between_shifts_policy,max_hours_policy,workload_policy,
                    function_mismatch_policy,over_coverage_policy,break_divergence_policy,
                    evaluator}.py
tests/unit/features/scheduling/domain/
├── test_exceptions.py                        (mod)
├── test_{validation_config,violation,employee_facts}.py
└── services/__init__.py
    └── validation/{__init__,scenario}.py + test_*.py
tests/unit/test_status_map.py                 (mod)
docs/LAYOUT.md                                (mod)
```

## 2. Tasks

### Task 01 — exceções da validação

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/domain/exceptions/errors.py`
  - `tests/unit/features/scheduling/domain/test_exceptions.py`
  - `tests/unit/test_status_map.py`
- **O que fazer:** acrescentar `InvalidValidationConfigError(reason)` e
  `InvalidEvaluationInputError(reason)`, filhas de `SchedulingError`, mensagens
  `"configuração de validação inválida: {reason}"` e `"insumo de avaliação inválido: {reason}"`.
  Atualizar a lista fechada, o total (22) e a tabela `_COM_CONTEXTO` do teste do BC (e os
  docstrings que dizem "20"); subir `_TOTAIS_MINIMOS["scheduling"]` para 22 com a data.
- **Critério de aceite:** CA14 — igualdade do conjunto com 22 + raiz; cada nova com mensagem
  testada; piso do repositório em 22.
- **Verificação:** `uv run pytest tests/unit/features/scheduling/domain/test_exceptions.py tests/unit/test_status_map.py -q` + `make check`
- **Commit:** `feat(scheduling): adicionar as exceções de configuração e de insumo da validação [4.2/task-01]`

---

### Task 02 — `ValidationConfig` e os enums

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/validation_config.py`
  - `tests/unit/features/scheduling/domain/test_validation_config.py`
- **O que fazer:** `PolicyKind` (9, na ordem do concept §4), `EnforcementMode`,
  `WorkloadDirection` (`StrEnum`, só os membros — conversão de texto é da 4.4/4.5), `PolicyRule`,
  `ValidationConfig` (concept §4) com `__post_init__` (§5.3), `default()` (§5.2) e `rule_for`
  (mapeamento `PolicyKind → PolicyRule` montado no método, um `return`; `UNAVAILABILITY` →
  `PolicyRule(True, BLOCK)` fixo).
- **Critério de aceite:** CA1 (inclusive a varredura AST de 660/600/2640 sobre o pacote, com
  anti-vácuo), CA2; valores dos enums travados por nome; `rule_for` total sobre o enum.
- **Verificação:** `uv run pytest tests/unit/features/scheduling/domain/test_validation_config.py -q` + `make check`
- **Commit:** `feat(scheduling): adicionar a configuração de validação com os defaults legais [4.2/task-02]`

---

### Task 03 — `Violation` e `EmployeeFacts`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/value_objects/violation.py`
  - `src/restaurant_hub/features/scheduling/domain/value_objects/employee_facts.py`
  - `tests/unit/features/scheduling/domain/test_violation.py`
  - `tests/unit/features/scheduling/domain/test_employee_facts.py`
- **O que fazer:** `Violation` + `ViolationKey` (`NamedTuple`) com `key` conforme concept §5.8:
  a coluna "na `key`?" vira um `frozenset[PolicyKind]` de políticas por alocação no módulo. Sem
  `__post_init__`: quem constrói é sempre uma política, e a forma de cada uma (dias distintos e
  ordenados, sujeito) é travada nos testes dela (CA11).
  `UnavailabilityWindow` (naive, `start < end`) e `EmployeeFacts` (concept §4; `contracted_weekly_hours`
  finito > 0 quando presente) com as recusas de §6.
- **Critério de aceite:** CA11 (forma da `key` por política, `operational_days`), linhas de §6
  sobre `UnavailabilityWindow` e carga de CA10.
- **Verificação:** `uv run pytest tests/unit/features/scheduling/domain/test_violation.py tests/unit/features/scheduling/domain/test_employee_facts.py -q` + `make check`
- **Commit:** `feat(scheduling): adicionar a violação com identidade e os fatos de staff por dados [4.2/task-03]`

---

### Task 04 — insumo do avaliador e protocolo

- **Arquivos a criar:**
  - `src/restaurant_hub/features/scheduling/domain/services/__init__.py`
  - `src/restaurant_hub/features/scheduling/domain/services/validation/__init__.py`
  - `src/restaurant_hub/features/scheduling/domain/services/validation/context.py`
  - `src/restaurant_hub/features/scheduling/domain/services/validation/policy_protocol.py`
  - `tests/unit/features/scheduling/domain/services/__init__.py`
  - `tests/unit/features/scheduling/domain/services/validation/__init__.py`
  - `tests/unit/features/scheduling/domain/services/validation/scenario.py`
  - `tests/unit/features/scheduling/domain/services/validation/test_evaluation_context.py`
- **Arquivos a modificar:** `docs/LAYOUT.md` (§2: `services/` sem `[planejado]`) e
  `tests/unit/test_check_docs_claims.py` (`_PLANEJADOS_DO_LAYOUT_REAL = frozenset()` e os
  textos que citam `services/` como planejado).
- **O que fazer:** `AllocationView` (frozen: `assignment_id`, `employee_id`, `demand_id`,
  `job_function_id`, `band_id`, `time_range`, `operational_day`, `worked_minutes`,
  `effective_break_minutes`, `band_break_minutes`, `counts_toward_workload`, `break_divergence`,
  `schedule_id`, `in_evaluated: bool`) construída pelas leituras públicas da raiz (sem aritmética
  de horas aqui: `worked_minutes_of`). `EvaluationContext` (concept §4) com as validações de §5.4
  e as leituras `facts_of(employee_id)`, `allocations` (ativos, avaliada), `all_allocations`
  (ativos, avaliada + vizinhas), `active_facts`. `ValidationPolicy` (`Protocol`, concept §4).
  `scenario.py` com os builders.
- **Detalhes:** 10 arquivos, acima da faixa de 5 — exceção declarada: quatro são `__init__.py`
  (só docstring) e `LAYOUT.md` + `test_check_docs_claims.py` são as duas entradas de totalidade
  da mesma mudança (criar `services/`). `operational_days` das políticas de semana é
  `schedule.period.operational_days` (os 7 dias, com ou sem alocação).
- **Critério de aceite:** CA9 (fato faltando recusado; inativo fora de `allocations` e
  `all_allocations`), CA10 (todas as linhas de §6 sobre vizinhas, ids, facts, período ≠ 7).
- **Verificação:** `uv run pytest tests/unit/features/scheduling/domain/services -q` + `uv run python scripts/check_docs_claims.py` + `make check`
- **Commit:** `feat(scheduling): adicionar o insumo do avaliador e o protocolo de política [4.2/task-04]`

---

### Task 05 — sobreposição e indisponibilidade

- **Arquivos a criar:**
  - `src/.../services/validation/overlap_policy.py`
  - `src/.../services/validation/unavailability_policy.py`
  - `tests/.../services/validation/test_overlap_policy.py`
  - `tests/.../services/validation/test_unavailability_policy.py`
- **O que fazer:** `OverlapPolicy` (pares de `all_allocations` do mesmo registro, com ≥ 1
  `in_evaluated`, `time_range.overlaps`; medida = minutos da interseção) e
  `UnavailabilityPolicy` (alocações da avaliada × janelas do registro; medida = minutos dentro das
  janelas unidas, exatos em `Decimal(µs) / 60_000_000`).
- **Critério de aceite:** CA3, CA4 (overlap contra anterior e seguinte; indisponibilidade ignora
  vizinha), CA11 (o par; a alocação), CA16 (interseção do overlap; janelas sobrepostas unidas;
  janela com segundos).
- **Verificação:** `uv run pytest tests/unit/features/scheduling/domain/services/validation -q` + `make check`
- **Commit:** `feat(scheduling): adicionar as políticas de sobreposição e de indisponibilidade [4.2/task-05]`

---

### Task 06 — descanso entre jornadas

- **Arquivos a criar:** `src/.../rest_between_shifts_policy.py`, `tests/.../test_rest_between_shifts_policy.py`
- **O que fazer:** concept §5.7 (rest) com `all_allocations`; reporta o par se algum dos dois
  dias é da avaliada; `assignment_ids` = as alocações de `max(end)` de dᵢ e `min(start)` de dⱼ.
- **Critério de aceite:** CA3, CA4, CA5 (a parte do descanso: `max(end)`/`min(start)`, dia
  vazio, lacuna no mesmo dia, negativo, descanso 0 no corte), CA11 (`assignment_ids` fora da
  `key`), CA16 (medida).
- **Verificação:** idem Task 05.
- **Commit:** `feat(scheduling): adicionar a política de descanso entre jornadas [4.2/task-06]`

---

### Task 07 — tetos diário e semanal

- **Arquivos a criar:** `src/.../max_hours_policy.py`, `tests/.../test_max_hours_policy.py`
- **O que fazer:** `DailyCapPolicy` e `WeeklyCapPolicy` sobre `allocations` (só a avaliada).
- **Critério de aceite:** CA3 (igual ao teto não viola), CA4 (dia da vizinha ignorado), CA5 (a
  parte do teto: contíguas que atravessam o corte dão 8h + 8h sem violar), CA11, CA16, CA17
  (faixas distintas sobrepostas somam por alocação).
- **Verificação:** idem.
- **Commit:** `feat(scheduling): adicionar as políticas de teto diário e semanal [4.2/task-07]`

---

### Task 08 — carga contratada

- **Arquivos a criar:** `src/.../workload_policy.py`, `tests/.../test_workload_policy.py`
- **O que fazer:** `WorkloadPolicy` sobre `active_facts` de jornada fixa; soma das alocações da
  avaliada com `counts_toward_workload`; `excess`/`both`; `Decimal` exato.
- **Critério de aceite:** CA3, CA4 (alocação da vizinha fora da soma), CA6 (todos os itens),
  CA11 (as que contam, vazio possível), CA16 (medida com carga 22,5h).
- **Verificação:** idem.
- **Commit:** `feat(scheduling): adicionar a política de carga contratada [4.2/task-08]`

---

### Task 09 — função não detida, sobre-cobertura e divergência de intervalo

- **Arquivos a criar:** `src/.../{function_mismatch,over_coverage,break_divergence}_policy.py` e os
  três testes.
- **O que fazer:** concept §5.7 para as três; a sobre-cobertura percorre as demandas da avaliada
  e conta só alocações de registro ativo.
- **Detalhes:** 6 arquivos — três políticas por alocação de uma linha de lógica cada, irmãs na
  forma; separá-las não daria commit mais revisável.
- **Critério de aceite:** CA3, CA4 (vizinha cuja alocação violaria é ignorada pelas três), CA7
  (Ana e Bruno; `function_exception` ignorada), CA8, CA11 (sobre-cobertura com o conjunto na
  `key`; as outras duas por alocação), CA16 (`N = 0`; 1/0; intervalo da alocação / da faixa).
- **Verificação:** idem.
- **Commit:** `feat(scheduling): adicionar as políticas de função, cobertura e intervalo [4.2/task-09]`

---

### Task 10 — avaliador e registro

- **Arquivos a criar:** `src/.../evaluator.py`, `tests/.../test_evaluator.py`
- **O que fazer:** `DEFAULT_POLICIES` (uma por `PolicyKind`, ordem do enum), `Evaluation`,
  `evaluate` (concept §5.10–§5.11): chama só as habilitadas, ordena, devolve.
- **Critério de aceite:** CA12, CA13 (totalidade registro × enum × campos de `ValidationConfig`
  via `dataclasses.fields`), CA9 (inativo ausente de toda violação de uma escala com as nove
  situações), CA4 (avaliação com as duas vizinhas).
- **Verificação:** `uv run pytest tests/unit/features/scheduling -q` + `make check`
- **Commit:** `feat(scheduling): adicionar o avaliador com o registro das nove políticas [4.2/task-10]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/4.2-validation-policies/technical.md
```
CA15: no `term-missing`, conferir **≥ 90% em cada arquivo** de `domain/services/validation/` e
nos três `value_objects` novos (o `fail_under` é agregado).

### Verificações funcionais
- [ ] Script de ponta a ponta com objetos de domínio reais (sem fakes): semana com as nove
      situações + vizinha anterior → `evaluate` devolve as violações esperadas, `blocking`/`warnings`.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas com check verde; `make check` verde
- [ ] Nota datada em `shift-scheduling.md` §6 (lacunas da 4.2 fechadas; divergência 5) e no
      roadmap (bloco 4.2); Stage `done` com `updated_at`/`last_reviewed_at`
- [ ] ADRs 4.2.0001–0002 `accepted`
- [ ] §7 com os `[finding]` herdados do concept: os quatro da 4.3 (§8), etiqueta "exceção" e
      vaga multifunção (4.5), cobertura com `N = 0` e contagem de exceções (8.1)
- [ ] Commit `stage 4.2: complete`

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10
```
05–09 dependem só de 04 (e entre si não); a ordem linear é por revisão (geométricas → agregadas).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `mypy` não aceitar o `Protocol` com `kind` como property em classes com atributo de classe | `kind` como `@property` em cada política |
| Ruff PLR0912/PLR0915 (ramos/instruções) em `EvaluationContext.__post_init__` ou numa política | Extrair helpers privados por regra |
| Varredura AST de CA1 pegar `600`/`660` legítimos em outro contexto do pacote | Restringir o detector a `int` literal em chamada/atribuição de campo de `ValidationConfig`, registrando `[decision]` |
| Fronteiras `>` × `≥` mal escolhidas | Testes de fronteira de cada política (CA3) e mutação real na auditoria |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs [4.2.0001](../../adr/4_2_0001-function-mismatch-follows-current-staff-record.md),
  [4.2.0002](../../adr/4_2_0002-evaluator-input-and-violation-identity.md)
- [`../../domain/scheduling/shift-scheduling.md`](../../domain/scheduling/shift-scheduling.md) §3.6
- [`../../LAYOUT.md`](../../LAYOUT.md), [`../../CONVENTIONS.md`](../../CONVENTIONS.md)
- Skills: `ddd-tactical-patterns`, `hex-arch-python`, `task-ordering-hex`, `pytest-with-fakes`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após `status: done`** —
> alterações fora dos marcadores `BEGIN/END: post-execution` são rejeitadas por
> `scripts/check_technical_postexec.py`. Cada entrada carrega data + autor.

### 2026-10-19 — [deviation] Task 04, arquivo de totalidade fora da lista do concept — Claude Opus 5.5 (executor)

A divergência 3 do concept §1 lista os arquivos a modificar e não inclui
`tests/unit/test_check_docs_claims.py`, que trava por igualdade o conjunto de caminhos
`[planejado]` do LAYOUT (`_PLANEJADOS_DO_LAYOUT_REAL`). Achado blocker do Checkpoint B, corrigido no
plano antes da aprovação (Task 04); o concept (`done`) não regride porque a lista de arquivos não é
contrato, fronteira nem critério de aceite. O conjunto passa a `frozenset()`: `domain/services/` era
o último caminho anotado.

### 2026-10-19 — [deviation] Checkpoint C do bloco 1 (Tasks 01–03) — Claude Opus 5.5 (executor)

Sem blocker; disposições (correções no commit `[4.2/task-03-fix]`):
- **#1 major, corrigido:** `EmployeeFacts.unavailabilities` tinha default `()` — esquecer as janelas
  calaria a política `block` fixa. O campo ficou obrigatório (o concept §4 já o declarava sem default).
- **#2, corrigido:** a config aceitava `bool` e `float` como minutos; agora `type(valor) is int`.
- **#3, corrigido:** a varredura AST do CA1 via só literal; passa a calcular aritmética de literais
  (`11 * 60`), com teste do próprio detector.
- **#4 e #5, corrigidos:** teste de `demand_id` na `key`; mensagens das duas exceções cobradas com o
  prefixo.
- **#6, refutado com artefato:** identificadores locais em português no `src`. A 4.1, mergeada e
  auditada, usa o mesmo idioma interno — `schedule.py` 88 `def _repetidos(`, 133 `for faixa in
  self.bands:` —, e os nomes **públicos** (classes, campos, métodos, enums) desta Stage estão em
  inglês. Seguir a vizinhança do BC; a regra de idioma não é reaberta aqui.
- **#7, aceito para o fechamento:** o CA11 é marcado pelos testes das políticas (Tasks 05–09), não
  pela Task 03.

### 2026-10-19 — [deviation] Checkpoint C do bloco 2 (Tasks 04–06) — Claude Opus 5.5 (executor)

Sem blocker; todos **corrigidos** no commit `[4.2/task-06-fix]`, só em testes (nenhum defeito no
`src`):
- **#1 major:** nenhum cenário começava antes do corte (05:00), e o mutante "dia civil no lugar do
  dia operacional" sobrevivia. Entraram a projeção com faixa às 02:00 de terça (dia de segunda) e
  dois testes de descanso que cruzam o corte. Na Task 06, o executor já tinha pegado dois testes de
  fronteira que passavam à toa pelo mesmo motivo (terça 02:59 e 03:00 ainda são segunda) e os
  reescrevera antes do commit.
- **#2 major:** os três `sorted` (dias do descanso, janelas, dias da sobreposição) sobreviviam à
  remoção, porque todo cenário era inserido em ordem. Entrou um teste fora de ordem por política.
- **#3 major:** a união das janelas não travava o "fim corrente = o maior"; entrou a janela depois
  de uma contida.
- **#4–#8:** modo do descanso vindo da config; a projeção conferida também no segundo registro e nos
  ids; a vizinha interna e o período ≠ 7 nos dois lados; `match` específico; `EmployeeId` no lugar do
  `type: ignore`.

### 2026-10-19 — [deviation] Checkpoint C do bloco 3 (Tasks 08–10) — Claude Opus 5.5 (executor)

Sem violação de contrato; os três achados foram **corrigidos** no commit `[4.2/task-10-fix]`, só em
testes. O diff revisado (`82e84de..46f668f`) não incluía a Task 07, que passou à auditoria de testes.
- **#1:** o dia operacional da sobre-cobertura (a única política que o calcula pela faixa, e não pela
  projeção) não era travado: entrou uma faixa às 02:00 de quinta, do dia de quarta.
- **#2:** três componentes da chave de ordenação (registro, demanda, alocações) sobreviviam à
  remoção, porque a emissão natural já coincidia com a ordem. Os testes novos têm emissão
  **inversa** à ordem esperada. Mutação real nesta sessão: remover cada componente reprova
  `test_evaluator.py` (`1 failed`), e o dia civil no lugar do operacional reprova
  `test_over_coverage_policy.py`; `src` restaurado e conferido por `git status`.
- **#3:** comentário do cenário das nove situações corrigido (930 min, não 13h).

### 2026-10-19 — [deviation] auditoria de testes, rodada 1 — Claude Opus 5.5 (executor)

Auditor independente (agente que não escreveu os testes), 59 mutantes reais, cada um revertido com
`git checkout`: **53 mortos, 1 equivalente** (M56: `warnings` como "não block", com o enum de dois
valores), **5 sobreviventes**. Três estavam na Task 07, que não tinha passado por revisão de código
(o diff do Checkpoint C do bloco 3 começava depois dela):
- M58: o teto diário configurado nunca era exercitado (só o default);
- M13: o modo do teto semanal vindo da config não era testado;
- M12, M55, M49, M54: sem cenário com **dois** registros, a soma semanal, a carga, as janelas e as
  funções podiam ser lidas do registro errado (o primeiro dos fatos) com a suíte verde.

Também: nada travava a ausência de texto livre na `Violation` (§5.12), e o descanso negativo junto
com a sobreposição só aparecia contra uma vizinha. Os 8 testes propostos entraram no commit
`[4.2/task-10-extra]`; a rodada 2 re-executa os sobreviventes.

### 2026-10-19 — [deviation] auditoria de testes, rodada 2 — Claude Opus 5.5 (executor)

Mesmo auditor. Os 5 sobreviventes da rodada 1 **morreram** (M12, M13, M49, M54, M55, M58); M56
segue equivalente. Dos 16 mutantes novos (N01–N16), 3 sobreviveram:
- N01: o teto diário podia levar alocações de **outro** registro em `assignment_ids`;
- N03: idem na carga;
- N05: a carga calculada via `float` passava, porque o único caso fracionário (22,5h) é
  representável em binário — o teste travava o caso, não a propriedade "Decimal exato".
Os três testes propostos entraram no commit `[4.2/task-10-extra2]` (22,33h = 1339,80 min exatos).

### 2026-10-19 — [deviation] auditoria de testes, rodada 3 — Claude Opus 5.5 (executor)

Mesmo auditor; os sobreviventes da rodada 2 (N01, N03, N04, N05, N15) foram re-executados e
**morreram**. Dos 11 mutantes novos (R01–R11), 3 sobreviveram:
- R07: a medida da sobre-cobertura só era travada com **um** excedente (`N + 1` passava);
- R08/R09: o "pula dias sem alocação" do descanso não era travado **atravessando a vizinha**.
Os testes entraram no commit `[4.2/task-10-extra3]`. A expectativa proposta para R08/R09 (72h)
estava errada: sexta 16h até segunda 08h são **64h** (3840 min), e o teste afirma o valor
recalculado — o código estava certo.

### 2026-10-19 — [deviation] auditoria de testes, rodada 4 — Claude Opus 5.5 (executor)

R07–R09 re-executados: **mortos**. Dos 10 mutantes novos (S01–S10), 2 sobreviveram:
- S01: o dia operacional das alocações da vizinha podia ser calculado pelo calendário da escala
  **avaliada** — o calendário é fotografado por escala (ADR 4.1.0009), e nenhum teste usava cortes
  diferentes;
- S03: o teto diário com "dia = data do início" passava, porque nenhuma faixa do teto começava entre
  a meia-noite e o corte.
Os dois testes entraram no commit `[4.2/task-10-extra4]`, com as contas conferidas (660 min na
segunda; 150 min de descanso de 05:30 a 08:00).

### 2026-10-19 — [decision] auditoria de testes encerrada na rodada 5 — Claude Opus 5.5 (executor)

S01/S03 re-executados: **mortos**. Rodada 5: 13 mutantes novos (T01–T13), 12 mortos; T02 (checar
fato faltando antes de fato repetido) é **equivalente** — as duas recusam com
`InvalidEvaluationInputError`, só o `reason` muda num insumo com os dois defeitos, e o concept não
fixa a ordem. Total: **109 mutantes em cinco rodadas**, restando só M56 e T02, ambos equivalentes;
os seis itens do questionário satisfeitos. Uma vez o driver de mutação quebrou ao decodificar a saída
do pytest e deixou `context.py` mutado: restaurado com `git checkout` antes de qualquer commit (o
commit da rodada 4 é anterior à quebra), e o driver passou a reverter num `try/finally`.

### 2026-10-19 — [decision] fechamento documental sem deslocar citações — Claude Opus 5.5 (fechamento)

Opções: (a) nota datada dentro do bloco 4.2 do roadmap e em cada seção do doc de domínio, como os
fechamentos até a 3.6; (b) linha no histórico do roadmap e nota única no fim do §6 do doc, depois da
da 4.1. **Escolhida (b)**, o precedente da 4.1: (a) deslocaria as linhas do roadmap a partir da 1335
e do doc a partir da 1092, que o doc de domínio, os ADRs 4.1.x e o concept da 4.1 citam por número.
Medido antes da edição: nenhuma citação aponta para as linhas que (b) desloca.

### 2026-10-19 — [finding] protocolo de aceite: re-pergunta quando a medida piora — Claude Opus 5.5 (executor)

A `key` das políticas agregadas não muda com a medida (concept §5.8). Na **sobre-cobertura** isso não
basta: reduzir `N` sobre excedente já aceito cria alocações excedentes sem aceite, contra o
invariante do doc §3.6.8. **Direção sugerida:** o protocolo da 4.3 compara também a medida
(`observed` mais distante de `limit` = pior, nas políticas ordinais de §5.9) e re-pergunta quando
piora; nas demais agregadas, a regra é escolha dela. **Stage candidata:** 4.3.

### 2026-10-19 — [finding] violação induzida por mudança de staff — Claude Opus 5.5 (executor)

Férias lançadas ou função retirada em staff, depois da alocação, aparecem como violação ao vivo
(inclusive `block`), sem mutação de escala que as introduza; os invariantes do doc §3.5, §3.6.6 e
§3.6.7 só valem para o que a escala introduz (concept §1, divergência 5). **Pergunta P** para o
sponsor no concept da 4.3: guarda em staff (recusar a indisponibilidade ou a retirada de função
sobre turno alocado, pelo port de consulta reverso do ADR 4.1.0006) × mostrar e deixar a gerente
corrigir. **Stage candidata:** 4.3 (com staff, se a guarda for escolhida).

### 2026-10-19 — [finding] aceite da violação da virada e completude do quadro — Claude Opus 5.5 (executor)

(1) A violação entre o domingo da anterior e a segunda da avaliada aparece, com a mesma `key`,
avaliando qualquer uma das duas (concept §5.6): o protocolo precisa decidir em qual escala o aceite é
gravado. (2) O avaliador recusa fato faltando de **alocado**, mas não detecta um registro fixo ativo
**sem** alocação ausente do insumo; em `both`, a falta dele some em silêncio. **Direção sugerida:**
o use case monta os fatos do quadro ativo inteiro pelo `StaffReadPort`, com teste de contrato.
**Stage candidata:** 4.3.

### 2026-10-19 — [finding] etiqueta "exceção", vaga multifunção e grandezas do hub — Claude Opus 5.5 (executor)

(1) Com a função não detida seguindo o cadastro atual (ADR 4.2.0001), a marca `function_exception`
não é a etiqueta: a 4.5 decide de onde a etiqueta vem, inclusive com a política **desabilitada**,
quando não há violação viva. (2) "Uma pessoa, duas funções, um turno" como cobertura cheia (ADR
4.1.0012 Decision 6) não muda nenhuma política e fica para a apresentação da vaga. **Stage
candidata:** 4.5. (3) Cobertura como razão com `N = 0` e a contagem de exceções de função são
grandezas do hub. **Stage candidata:** 8.1.

### 2026-10-19 — [deviation] auditoria da Stage (`stage-audit`, agente Opus de contexto zerado) — Claude Opus 5.5 (executor)

Veredito: "não pronta" por dois bloqueantes, com os gates numéricos verdes (`make check` EXIT=0,
4129 passed, 100% por arquivo novo). Disposições, todas **corrigidas** no commit
`fix(scheduling): ... [4.2/--]` (fora de Task: correção de auditoria depois do `stage 4.2:
complete`) e no commit de docs seguinte:
- **F1 (bloqueante):** os 17 CAs do concept §11 estavam com a caixa aberta, embora com evidência.
  Marcados `[x]` — o CA12 só depois do F2.
- **F2 (bloqueante, major):** modo, `enabled` e direção em **texto cru** falhavam aberto. Um StrEnum
  é `==` ao texto mas não `is`, e um `"block"` vindo do banco (reidratação da 4.4) sumia de
  `blocking` e de `warnings`. `PolicyRule` passa a exigir `bool` e `EnforcementMode`, e
  `ValidationConfig` exige `PolicyRule` nos oito campos e `WorkloadDirection`, todos com
  `InvalidValidationConfigError` nomeando o campo e com teste.
- **F3 (minor):** a verificação funcional do §3 ("semana com as nove situações + vizinha anterior")
  não estava registrada. Coberta por `test_evaluator.py` (as nove políticas, as duas vizinhas, o
  inativo, a virada) e por um roteiro com objetos reais rodado nesta sessão sobre o HEAD da Stage:
  `7 violações — 2 block, 5 warn` (sobreposição 300/0 e indisponibilidade 240/0 em `block`;
  descanso 300/660, teto diário 780/600, carga 1260/600, função 1/0 e sobre-cobertura 2/1 em `warn`).
- **F4 (minor):** "a mesma `key` dos dois lados da virada" ganhou teste (avalia W com `next` e N com
  `previous` e compara os conjuntos de `key`).
- **F5 (minor):** o limite da varredura do CA1 (não vê `timedelta(hours=11)` nem `Decimal("660")`)
  ficou declarado no docstring do teste.
- **F6 (minor):** `EmployeeFacts` recusa carga que não é `Decimal`, e `UnavailabilityWindow` recusa
  `date` sem hora — com `InvalidEvaluationInputError`, não `AttributeError`.
- **F7 (observação):** os `type: ignore[arg-type]` dos testes são do idioma `**{lado: vizinha}` ou
  de entrada deliberadamente malformada; sem ação.

<!-- END: post-execution -->

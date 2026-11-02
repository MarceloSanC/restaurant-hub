---
title: Technical — Hierarquia de exceções sem protocolo HTTP
description: Plano de execução da Stage 3.9 — ApplicationError e raízes de aplicação por BC, migração por significado, fim de NotFoundError, regra 11 do check_layout e supersessão do ADR 2.2.0003
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, error-hierarchy, application-error, status-map, check-layout]
status: done
created_at: 2026-11-02
updated_at: 2026-11-02
stage_id: 3.9-error-hierarchy
stage_title: Hierarquia de exceções sem protocolo HTTP
step_id: 3
step_title: Equipe da unidade
depends_on: [3.6-staff-http, 4.3-scheduling-application]
concept_ref: ./concept.md
issue_id: 48
branch: refactor/48-3-9-error-hierarchy
tasks_count: 8
---

# Technical — Stage 3.9 — Hierarquia de exceções sem protocolo HTTP

> **Como usar este documento:** executar as Tasks em ordem (§2), 1 Task = 1 commit
> `<type>(<scope>): <descrição> [3.9/task-NN]` (CONVENTIONS §4). Algo fora de §1–§6 ou do
> [`concept.md`](./concept.md) → registrar em §7.

## 1. Contexto e estratégia de execução

### Resumo
Recriar `ApplicationError` em `shared/application/errors.py`; dar a cada BC uma raiz de
aplicação; mover para ela os erros de aplicação que não nomeiam regra de negócio (concept §4:
14 de identity, 4 de staff, 6 de scheduling), tirando a herança dupla com `NotFoundError`;
registrar o handler de identity e o de staff nas duas raízes; apagar `NotFoundError` e o handler
genérico 404; generalizar o Gate 3 para raízes do BC; criar a regra 11 de `check_layout.py`;
registrar a supersessão nos ADRs e emendar `LAYOUT.md`.

### Estratégia
**Totalidades primeiro** (memória do projeto: varreduras derivadas reprovam mudança
incremental). Cada Task leva a sua entrada em toda varredura que a observa, para que o build
fique verde entre commits:
- `check_dead_shared.py` exige consumidor para todo nome público de `shared/application` — por
  isso `ApplicationError` nasce (T01) junto com a primeira raiz que a consome (identity), e
  `NotFoundError` só sai (T05) depois que a última subclasse dela migrou (T04).
- O Gate 3 (`test_status_map.py`) é generalizado para "raízes do BC" em T01, antes de qualquer
  raiz de aplicação ter subclasse; o teste de raiz única (CA2) só entra em T05, quando ninguém
  mais herda de duas raízes.
- A regra 11 (T06) só entra depois que todos os módulos que ela varre foram reescritos (T02–T05),
  cada BC no seu commit.

Ordem: shared+identity (raiz) → identity → staff → scheduling → shared (remoção) → tooling →
ADRs → LAYOUT.

### Pré-condições
- `python scripts/check_stage_deps.py 3.9-error-hierarchy` verde (conferido na Fase 3A).
- Postgres da worktree (`docker compose up -d --wait postgres`) para os testes de contrato e e2e
  afetados.

### Premissas técnicas
- `make check` completo roda só no GitHub Actions (orquestração autônoma); local: ruff,
  `mypy src tests/fakes`, `scripts/check_layout.py`, `scripts/check_dead_shared.py`,
  `lint-imports`, `make docs-check` e os testes afetados.
- Starlette escolhe o handler pelo primeiro tipo do `__mro__` que estiver registrado (concept §3).

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── shared/
│   ├── application/errors.py                     (novo — ApplicationError)
│   ├── domain/exceptions/base.py                 (NotFoundError sai; docstring)
│   └── infrastructure/http/{error_handlers.py,app.py}
└── features/{identity,staff,scheduling}/
    ├── application/errors.py                     (raiz de aplicação + migração)
    ├── domain/exceptions/errors.py               (docstrings)
    └── adapters/inbound/http/error_handlers.py   (identity, staff: duas raízes)
scripts/check_layout.py                           (regra 11)
tests/unit/{test_status_map.py,test_check_layout.py,test_check_dead_shared.py,shared/}
```

## 2. Tasks

### Task 01 — `ApplicationError` e a raiz de aplicação de identity; Gate 3 por raízes

- **Arquivos a criar:**
  - `src/restaurant_hub/shared/application/errors.py`
  - `tests/unit/shared/test_application_errors.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/errors.py` (só a classe-raiz nova)
  - `src/restaurant_hub/features/identity/adapters/inbound/http/error_handlers.py`
  - `tests/unit/test_status_map.py`
  - `tests/unit/test_check_dead_shared.py`
  - `tests/unit/features/identity/application/test_errors.py` (o conjunto de nomes do módulo
    ganha `IdentityApplicationError`; o teste de raiz passa a excluir a raiz)
- **Justificativa do tamanho/escopo (7 arquivos, `shared` + a raiz de identity):** o Gate 7
  (`check_dead_shared.py`) reprova `ApplicationError` sem consumidor no mesmo commit, e o
  primeiro consumidor é a raiz de identity; a raiz exige o handler registrado (teste de
  registro por raiz) — totalidade derivada dita o corte. O escopo do commit é `shared`, cujo
  contrato a Task introduz; a parte de identity é o consumidor mínimo.
- **O que fazer:**
  - `ApplicationError(Exception)` com docstring sem vocabulário de protocolo (regra 11 de
    amanhã): "falha de caso de uso que não é violação de regra de negócio" e o critério do ADR
    3.9.0001 §3.
  - `IdentityApplicationError(ApplicationError)` em `identity/application/errors.py`, ainda sem
    subclasse.
  - Handler de identity: tipo do mapa e das funções aceita `IdentityError |
    IdentityApplicationError`; `register_identity_error_handlers` registra a mesma função nas
    duas raízes; `_nome_da_classe` dá nome curto para as duas (D5).
  - `test_status_map.py`: `_raizes_de_erro(bc)` devolve a raiz de domínio (exatamente uma
    subclasse direta de `DomainError` no módulo de domínio) e a de aplicação (no máximo uma
    subclasse direta de `ApplicationError` no módulo de aplicação, asserção de unicidade); a
    varredura desce das raízes; o teste de pertinência passa a "descende de uma raiz do BC";
    teste novo `test_todo_bc_com_borda_registra_handler_em_cada_raiz` — monta `FastAPI()`, chama
    a função `register_*` do módulo de handlers (descoberta pela forma, não pelo nome do BC) e
    asserta que cada raiz é chave de `app.exception_handlers`; violador plantado: registro que
    omite uma raiz reprova (função `_raizes_sem_handler` isolada, como `_sem_entrada`).
  - `test_check_dead_shared.py`: `ApplicationError` entra em `_NOMES_PUBLICOS_DE_SHARED`.
  - `test_application_errors.py`: `ApplicationError` é `Exception` e **não** é `DomainError`.
- **Critério de aceite:** CA3 (parte shared), CA4 (registro por raiz); faixas inalteradas.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/test_status_map.py tests/unit/shared tests/unit/test_check_dead_shared.py tests/unit/features/identity -q
  uv run python scripts/check_dead_shared.py && uv run python scripts/check_layout.py && uv run lint-imports
  ```
- **Commit sugerido:** `feat(shared): recriar ApplicationError com a raiz de aplicação de identity [3.9/task-01]`

---

### Task 02 — identity: 14 erros para a raiz de aplicação

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/errors.py`
  - `src/restaurant_hub/features/identity/domain/exceptions/errors.py` (docstrings)
  - `src/restaurant_hub/features/identity/adapters/inbound/http/error_handlers.py` (docstring)
  - `tests/unit/features/identity/application/test_errors.py`
  - `tests/unit/features/identity/adapters/test_http_error_handlers.py`
  - `tests/unit/features/identity/adapters/test_integrity_errors.py`
- **O que fazer:** os 14 erros do concept §4 passam a herdar só de `IdentityApplicationError`
  (os três `*NotFoundError` perdem `NotFoundError`); docstrings de módulo e de classe sem
  `HTTP`/`handler`/`MRO`/número de status (a classificação de status é descrita no adapter); a
  docstring do módulo de handlers deixa de falar em ordem de MRO e de `NotFoundError`.
  Testes: partição por **igualdade de conjuntos** (CA3) — lista de domínio ∪ lista de aplicação
  = classes do módulo, interseção vazia, cada uma sob a raiz da sua lista; a enumeração do
  handler desce das duas raízes; teste novo de **corpo exato** por faixa para toda subclasse
  concreta das duas raízes (CA8); `isinstance(traduzido, IdentityError)` vira pertinência às
  duas raízes (nunca removida). Remover **todo** import e toda asserção de `NotFoundError`
  dos arquivos de teste da Task (inclusive as negativas, que deixariam de compilar na T05).
- **Critério de aceite:** CA3/CA8 para identity; oráculos de §5.6 do concept verdes sem edição.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity tests/unit/test_status_map.py tests/contract/features/identity tests/e2e/features/identity -q
  uv run mypy src tests/fakes
  ```
- **Commit sugerido:** `refactor(identity): mover os erros que não são regra de negócio para a raiz de aplicação [3.9/task-02]`

---

### Task 03 — staff: raiz de aplicação, 4 erros, handler nas duas raízes

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/errors.py`
  - `src/restaurant_hub/features/staff/domain/exceptions/errors.py` (docstrings)
  - `src/restaurant_hub/features/staff/adapters/inbound/http/error_handlers.py`
  - `tests/unit/features/staff/application/test_errors.py`
  - `tests/unit/features/staff/adapters/test_http_error_handlers.py`
  - `tests/unit/features/staff/adapters/test_integrity_errors.py`
  - `tests/contract/features/staff/test_identity_gateway_laws.py` (negar as duas raízes)
  - os sítios `pytest.raises(StaffError)` cujo erro migra, ajustados mecanicamente para
    `(StaffError, StaffApplicationError)` mantendo a asserção de tipo exato que segue:
    `tests/contract/features/staff/test_employee_repository_laws.py` (`EmployeeNotFoundError`);
    em `tests/unit/features/staff/application/`: `test_assign_job_functions.py`,
    `test_copy_employee_to_unit.py`, `test_create_employee.py`, `test_delete_employee.py`,
    `test_delete_job_function.py`, `test_employee_edit_use_cases.py`,
    `test_employee_lifecycle.py`, `test_job_function_use_cases.py`,
    `test_unavailability_use_cases.py`. Ficam como estão os sítios cujo erro permanece no
    domínio (`EmployeeRelocationError` na lei; a asserção negativa de `test_create_employee.py`).
  - `tests/unit/features/staff/domain/test_exceptions.py` (import de `NotFoundError`)
- **O que fazer:** `StaffApplicationError(ApplicationError)`; os 4 erros do concept §4 herdam
  dela; handler registrado nas duas raízes com o mesmo `"type": "staff_error"`; mapa tipado
  pelas duas raízes (23 entradas, sem as raízes); docstrings sem protocolo; a docstring e os
  comentários do módulo de handlers de staff deixam de falar em rede de segurança de
  `NotFoundError`, MRO e herança de `NotFoundError`; testes de handler descem das duas raízes,
  travam o corpo exato (CA8) e o registro nas duas raízes. Remover todo import e toda asserção
  de `NotFoundError` dos testes de staff (inclusive `test_ca19_os_dois_erros_de_404_herdam_de_not_found_error`,
  que vira asserção de raiz de aplicação).
- **Justificativa do tamanho (> 5 arquivos):** os sítios `pytest.raises` são a mesma mudança
  lógica (a raiz do erro migrado) e não podem ficar para outro commit sem deixar a suíte
  vermelha — é a totalidade derivada que dita o corte.
- **Critério de aceite:** CA3/CA8 para staff; `test_staff_status_bands.py` e
  `test_staff_authorization.py` verdes sem edição.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff tests/unit/test_status_map.py tests/contract/features/staff tests/e2e/features/staff -q
  uv run mypy src tests/fakes
  ```
- **Commit sugerido:** `refactor(staff): dar raiz de aplicação aos erros de lookup e de colisão de id [3.9/task-03]`

---

### Task 04 — scheduling: raiz de aplicação e 6 erros

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/scheduling/application/errors.py`
  - `src/restaurant_hub/features/scheduling/domain/exceptions/errors.py` (docstrings)
  - `tests/unit/features/scheduling/application/test_errors.py`
- **O que fazer:** `SchedulingApplicationError(ApplicationError)`; os 6 do concept §4 herdam
  dela (os três `*NotFoundError` sem `NotFoundError`); `ScheduleVersionConflictError` e os
  demais 5 seguem em `SchedulingError`; docstrings sem protocolo; teste de partição por
  igualdade de conjuntos; remover todo import e toda asserção de `NotFoundError` do teste.
- **Critério de aceite:** CA3 para scheduling; testes de scheduling verdes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/scheduling tests/unit/test_status_map.py -q
  ```
- **Commit sugerido:** `refactor(scheduling): dar raiz de aplicação aos erros que não são regra da escala [3.9/task-04]`

---

### Task 05 — `NotFoundError` e o handler genérico 404 saem; raiz única travada

- **Arquivos a modificar:**
  - `src/restaurant_hub/shared/domain/exceptions/base.py`
  - `src/restaurant_hub/shared/infrastructure/http/error_handlers.py`
  - `src/restaurant_hub/shared/infrastructure/http/app.py` (docstrings)
  - `tests/unit/shared/test_exceptions.py`
  - `tests/e2e/test_app_smoke.py` (sonda 404 sai; a 422 fica)
  - `tests/unit/test_check_dead_shared.py` (`NotFoundError` sai da lista)
  - `tests/unit/test_status_map.py` (teste de raiz única, CA2, com violadores plantados)
  - `.importlinter` (comentários que justificam dependências com "os erros herdam de
    DomainError/NotFoundError")
- **Justificativa do tamanho (8 arquivos):** apagar uma classe pública de `shared` exige, no
  mesmo commit, toda referência a ela (handler, smoke, Gate 7, contagem do módulo) e a trava
  que a impede de voltar (CA2) — totalidade derivada.
- **Pré-check:** `grep -rnw NotFoundError src tests` só acusa os arquivos desta Task.
- **O que fazer:** apagar `NotFoundError` e o handler; reescrever a docstring de `base.py` sem
  `HTTP`/`handler`/número de status/"status" (CA5) — `DomainError` como "violação de regra de
  negócio" e o ponteiro para `ApplicationError`; `test_exceptions.py` passa a contar exatamente
  `{"DomainError"}` no módulo; teste de raiz única com dois violadores plantados (duas raízes;
  `ApplicationError` direto) via função isolada.
- **Critério de aceite:** CA2, CA5; `check_dead_shared.py` verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit tests/e2e/test_app_smoke.py -q
  uv run python scripts/check_dead_shared.py && uv run lint-imports
  grep -rnw NotFoundError src tests                                   # vazio
  grep -n -i "status" src/restaurant_hub/shared/domain/exceptions/base.py   # vazio
  ```
- **Commit sugerido:** `refactor(shared): remover NotFoundError e o handler genérico de 404 [3.9/task-05]`

---

### Task 06 — regra 11 de `check_layout.py`: a hierarquia não fala de protocolo

- **Arquivos a modificar:**
  - `scripts/check_layout.py`
  - `tests/unit/test_check_layout.py`
- **O que fazer:** `check_error_hierarchy_protocol(src_root)` varre os arquivos cujo caminho
  casa `/domain/exceptions/` ou termina em `/application/errors.py` (âncoras de cobertura
  derivadas, como as demais) e reprova linha com `\bHTTP\b`, `FastAPI`, `Starlette`,
  `\bhandlers?\b`, `\bMRO\b`/`__mro__`, ou `\b[45]\d\d\b`, em qualquer lugar do texto (código,
  docstring, comentário), sem distinção de caixa para as palavras. Ligada em `main()`.
  Testes: `src/` real verde; um violador plantado **por termo** reprova (parametrizado); caso
  negativo — número que não é status (`2.3.0003`, `R13`, `600`) e palavra fora do vocabulário
  (`status`, `borda`) não reprovam; arquivo fora das âncoras (ex.: `domain/value_objects/x.py`)
  não é varrido.
- **Critério de aceite:** CA6.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/test_check_layout.py -q && uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(tooling): reprovar vocabulário de protocolo nos módulos de exceção [3.9/task-06]`

---

### Task 07 — ADRs: supersessão do 2.2.0003 e parciais

- **Arquivos a modificar:**
  - `docs/adr/2_2_0003-application-errors-in-identity-hierarchy.md` (`status: superseded`,
    `superseded_by: "3.9.0001"`, banner no `## Status`, `updated_at`)
  - `docs/adr/2_3_0003-add-is-insertion-not-upsert.md`, `docs/adr/2_4_0001-http-error-status-mapping.md`,
    `docs/adr/3_4_0002-staff-http-error-status-mapping.md` — seção `## Supersessão parcial`
    append-only, nota datada citando a cláusula e apontando o ADR 3.9.0001; `updated_at`.
- **Critério de aceite:** CA1; `make docs-check` verde.
- **Comando de verificação:**
  ```bash
  make docs-check
  grep -c '^status: superseded' docs/adr/2_2_0003-*.md                 # 1
  grep -c '^superseded_by: "3.9.0001"' docs/adr/2_2_0003-*.md          # 1
  grep -c '^## Supersessão parcial' docs/adr/2_3_0003-*.md docs/adr/2_4_0001-*.md docs/adr/3_4_0002-*.md   # >= 1 cada, com nota 2026-11-02
  ```
- **Commit sugerido:** `docs(adr): registrar a supersessão do ADR 2.2.0003 pelo 3.9.0001 [3.9/task-07]`

---

### Task 08 — `LAYOUT.md`

- **Arquivos a modificar:** `docs/LAYOUT.md`
- **O que fazer:** §2 (comentários de `shared/domain/` e `shared/application/`), §3 (Application
  "Pode importar de" inclui `shared/application/errors.py`), §4 (exemplo `NotFoundError` sai;
  parágrafo de `ApplicationError` ganha nota datada de retorno pela 3.9 com consumidor medido).
- **Critério de aceite:** CA9; `check_docs_claims.py` verde.
- **Comando de verificação:**
  ```bash
  make docs-check
  grep -n 'shared/application/errors.py' docs/LAYOUT.md    # acha a linha de §3 (Application)
  grep -n 'NotFoundError' docs/LAYOUT.md                   # só na nota datada de §4
  ```
- **Commit sugerido:** `docs(layout): registrar ApplicationError em shared/application [3.9/task-08]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check                                    # no GitHub Actions (orquestração autônoma)
uv run python scripts/check_technical_postexec.py docs/stages/3.9-error-hierarchy/technical.md
git diff origin/develop --stat -- tests/e2e/features/identity/test_status_bands.py tests/e2e/features/identity/test_suppressed_cause_log.py tests/e2e/features/identity/test_auth_flow.py tests/e2e/features/identity/test_authorization.py tests/e2e/features/staff/test_staff_status_bands.py tests/e2e/features/staff/test_staff_authorization.py tests/unit/features/identity/adapters/test_http_suppressed_cause_log.py   # vazio (CA7)
grep -n -i "status" src/restaurant_hub/shared/domain/exceptions/base.py   # vazio (CA5)
```

### Verificações funcionais
- [ ] Pela API real: 401 de token inválido numa rota de staff e de identity (corpo constante +
  `WWW-Authenticate`), 404 de recurso inexistente com `"type"` do BC — idênticos a `develop`.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no Actions do head do PR
- [ ] Commit final `stage 3.9: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at` e `last_reviewed_at`
- [ ] ADR 3.9.0001 `accepted`
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
T01 ─► T02 ─► T03 ─► T04 ─► T05 ─► T06
                                    T07 ─► T08   (docs; depois de T05 por citarem o estado final)
```

T02–T04 dependem da raiz de aplicação e do Gate 3 por raízes (T01); T05 só depois da última
subclasse de `NotFoundError` migrar (T04); T06 só depois de todo módulo varrido estar limpo.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Algum oráculo e2e muda de resultado | Parar: a Stage é neutra em comportamento; investigar o handler antes de qualquer edição de teste |
| `mypy` recusa o mapa tipado pela união das raízes | `dict[type[Exception], int]` com a função de resolução tipada pela união; registrar `[decision]` |
| Regra 11 com falso positivo em módulo legítimo | Estreitar o padrão (não criar allowlist), com caso negativo no teste |

## 6. Referências

- [`./concept.md`](./concept.md); [ADR 3.9.0001](../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md)
- [`../../roadmap.md`](../../roadmap.md) §Stage 3.9; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4
- Skills: `hex-arch-python`, `fastapi-thin-adapter`, `pytest-with-fakes`, `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-11-02 — [decision] Fase 3A — nenhuma bifurcação P; forks fechados por convenção — Claude (Opus 5.5)
**Contexto:** a Stage é neutra em comportamento observável. Os forks (onde mora `ApplicationError`, critério de raiz, raiz de aplicação por BC, destino de `NotFoundError`, rede genérica, escopo do detector) são de organização interna.
**Decisão:** todos `[decision:C]`, registrados no concept §7 (D1–D6) e no ADR 3.9.0001. Nenhum foi devolvido ao sponsor.
**Razão:** skill `evidence-resolution` §1 — nenhum muda regra de domínio, escopo ou algo visível ao usuário do piloto.

### 2026-11-02 — [decision] Checkpoint A — critério de raiz restrito à camada de aplicação, com precedência por fonte de produto — Claude (Opus 5.5)
**Contexto:** o revisor de domínio mostrou que o critério do ADR, aplicado ao pé da letra, classificava como aplicação análogos que ficam no domínio (`ShiftBandNotFoundError`, `DuplicateEntityIdError`, `InvalidEvaluationInputError`) e que `ScheduleVersionConflictError` (regra canônica de concorrência, decisão do sponsor F8) estava do lado errado.
**Decisão:** o critério classifica só o que a camada de aplicação levanta; erro levantado por objeto de domínio é domínio por construção; o ramo de domínio exige fonte de **produto**. `ScheduleVersionConflictError` fica no domínio (scheduling: 6 + 6, não 7 + 5). `[decision:C]`, degrau 1 (shift-scheduling.md, "Regra canônica — concorrência").
**Razão:** sem o escopo e a precedência o ADR não serviria de guia ao criar erro novo, que é o `when-use` dele.

### 2026-11-02 — [decision] Checkpoint C — a regra 11 não usa `\b` — Claude (Opus 5.5)
**Contexto:** o revisor do bloco T06–T08 mostrou que `\bHTTP\b`/`\bhandlers?\b` deixavam passar as grafias idiomáticas compostas com `_` ou CamelCase (`exception_handler`, `HTTPException`, `Http404`, `HTTP_404_NOT_FOUND`), além de "method-resolution order" por extenso — termos que o ADR 3.9.0001 §6 proíbe.
**Decisão:** fronteiras por lookaround que não tratam `_` como letra, alternativas por extenso (PT e EN) e um plantado por grafia; o technical (Task 06) citava o regex antigo, o ADR vence. `[decision:C]`, degrau 1.
**Razão:** o detector existe para pegar a forma como a inversão realmente é escrita.

### 2026-11-02 — [decision] Auditoria de testes — sem e2e novo para o log do 401 em rota de staff — Claude (Opus 5.5)
**Contexto:** a auditoria (rodada 1) notou que a linha de log da causa suprimida é assertada em e2e só por rotas de identity; numa rota de staff, só o status/corpo/cabeçalho (`test_ca08_toda_rota_sem_bearer_recebe_401`).
**Decisão:** não acrescentar. O handler de staff não participa: o 401 sai do handler de identity, o mesmo objeto registrado nas duas raízes (`test_o_registrador_instala_o_mesmo_handler_nas_duas_raizes`), e a rota não muda o caminho do log. `[decision:C]`, degrau 5.
**Razão:** o risco que o teste cobriria já está travado por identidade de objeto; o e2e seria duplicação.

### 2026-11-02 — [deviation] Task 01 — `test_errors.py` de identity entrou na Task — Claude (Opus 5.5)
Apontado pelo Checkpoint B (A1) antes da aprovação: a raiz nova entrava na varredura do módulo e reprovava dois testes. Já está na lista da Task 01 do technical aprovado; registrado aqui porque a T01 ficou com 7 arquivos e escopo `shared` com o consumidor mínimo em identity.

### 2026-11-02 — [deviation] Task 05 — o grep "`NotFoundError` vazio" vale para código, não para prosa — Claude (Opus 5.5)
`grep -rnw NotFoundError src tests` não sai vazio: sobram o padrão `*NotFoundError` (família de classes) em `staff/application/ports/out/job_function_repository.py`, um comentário de `tests/unit/features/scheduling/domain/test_schedule.py`, a docstring do oráculo `tests/e2e/features/staff/test_staff_status_bands.py` (intocável, CA7) e as notas históricas que dizem que a classe saiu. Nenhum import nem referência de código à classe.

### 2026-11-02 — [deviation] Checkpoint C / auditoria — testes da auditoria dobrados no `task-06-fix` — Claude (Opus 5.5)
Os dois testes que a auditoria (rodada 1) propôs para os sobreviventes M10a (caixa) e M11 (regra fora do `main()`) entraram no mesmo commit que corrigiu o regex (`[3.9/task-06-fix]`), porque exercitam o mesmo trecho. As extras puras da auditoria são `[3.9/task-09-extra]` (CA5 por teste) e `[3.9/task-10-extra]` (M18, base única).

### 2026-11-02 — [finding] Regra 11 — número de 400 a 599 que não é status reprova — Claude (Opus 5.5)
**Contexto:** `[45]\d\d` sem letra/dígito/ponto colado reprova também uma quantidade ("480 minutos", "art. 482") num módulo de erro.
**Direção sugerida:** quando acontecer, estreitar o padrão (ex.: exigir contexto de status), nunca allowlist; o limite está documentado no comentário do regex.
**Stage candidata:** `4.5-scheduling-http` (primeira que tende a escrever mensagens de erro com cargas horárias perto do mapa de status).

### 2026-11-02 — [finding] Scheduling ganha a raiz de aplicação sem handler — Claude (Opus 5.5)
**Contexto:** `SchedulingApplicationError` existe e não há rede genérica para `ApplicationError` (ADR 3.9.0001 §5). Hoje é inalcançável: scheduling não tem `adapters/inbound/`.
**Direção sugerida:** o handler de scheduling registra sobre as duas raízes; `test_todo_bc_com_borda_registra_handler_em_cada_raiz` e o Gate 3 já reprovam o contrário assim que a pasta da borda existir.
**Stage candidata:** `4.5-scheduling-http`.

### 2026-11-02 — [decision] Disposição dos checkpoints — Claude (Opus 5.5)
- **Checkpoint A** (2 revisores): domínio F1–F8 e conformidade F1–F6 — todos corrigidos no commit `stage 3.9: conceptual approved`.
- **Checkpoint B**: A1–A6 corrigidos no commit `stage 3.9: technical approved`.
- **Checkpoint C, T01–T05**: sem achado material; m1 → `[3.9/task-02-fix]`, cosméticos de staff → `[3.9/task-03-fix]`, m2/m3 → `[3.9/task-05-fix]`.
- **Checkpoint C, T06–T08**: R11-1/R11-2 → `[3.9/task-06-fix]`; ADR-1 a ADR-4 → `[3.9/task-07-fix]`; R11-3 → `[finding]` acima.
- **Auditoria de testes**: 3 rodadas; sobreviventes M10a, M11 (rodada 1) e M18 (rodada 2) mortos; rodada 3 com os seis itens "sim".

<!-- END: post-execution -->

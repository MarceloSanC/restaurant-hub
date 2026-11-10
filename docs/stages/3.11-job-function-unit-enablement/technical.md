---
title: Technical — Habilitação de função de trabalho por unidade
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, job-function-unit-enablement]
status: done
created_at: 2026-11-09
updated_at: 2026-11-09
stage_id: 3.11-job-function-unit-enablement
stage_title: Habilitação de função de trabalho por unidade
step_id: 3
step_title: Equipe da unidade
depends_on: [3.7-application-authorization, 3.9-error-hierarchy]
concept_ref: ./concept.md
issue_id: 41
branch: feat/41-job-function-unit-enablement
tasks_count: 9
---

# Technical — Stage 3.11 — Habilitação de função de trabalho por unidade

> **Como usar este documento:** executar as Tasks em ordem (§2), 1 Task = 1 commit
> `<type>(<scope>): <descrição> [3.11/task-NN]` (CONVENTIONS §4). Algo fora de §1–§6 ou do
> [`concept.md`](./concept.md) → registrar em §7.

## 1. Contexto e estratégia de execução

### Resumo
`UnitEnablement` no domínio e em `JobFunction`; persistência da habilitação (coluna +
tabela de vínculo, migration `0005`); leis novas e revisadas dos dois ports com o
contrato fake ≡ Postgres; criação/listagem/alteração de unidades na application com a
autorização de R4/R5; a invariante funcionário × unidade em criar, atribuir e copiar;
três mudanças na borda HTTP; notas datadas nos docs de hierarquia superior.

### Estratégia
**Inside-out** (skill `task-ordering-hex`): domínio → schema → ports com fake e adapter →
use cases → HTTP → docs. **Totalidades primeiro** (memória do projeto): cada Task leva a
sua entrada em toda varredura que a observa — mapa de erros (`error_handlers.py`, em T01 e
T07), pasta de use cases × composition root (T06), `router.routes` (T08), campos de DTO ×
schema (T05/T08) —, para o build ficar verde entre commits.

**Exceção declarada ao PIPELINE §4.3 #4 (port e adapter na mesma Task) em T03 e T04:** a
suíte de contrato tem **um** corpo para o fake e o Postgres (ADR 3.3.0007) e roda no CI
contra os dois; uma lei nova no port sem o adapter deixaria o CI vermelho entre commits.
As duas Tasks passam de 5 arquivos pela mesma razão.

**Exceção declarada ao limite de 5 arquivos em T05–T08 (Checkpoint B):** as varreduras
de totalidade do BC fixam listas e contagens à mão — `_TOTAL_DE_ERROS_DE_STAFF` e
`_STATUS_ESPERADO` (`test_http_error_handlers.py`), `_USE_CASES_ESPERADOS`
(`test_application_guards.py`), `CENARIOS`/`_MATRIZ_R3`/`_DE_DOIS_ALVOS`
(`test_use_cases_authorize.py`), `_USE_CASES_DE_STAFF`/`_TOTAL_DE_USE_CASES`/
`_TOTAL_DE_ROTAS_DE_STAFF`/`_TOTAL_DE_OVERRIDES_DE_STAFF`
(`test_composition_root_staff.py`), `_INVOCACOES`/`_TOTAL_DE_AUTORIZACOES`/
`_TOTAL_DE_CAMPOS_ESCALARES` (`test_http_boundary_sweeps.py`) e a tabela de rotas do
e2e de autorização. Cada Task leva a sua entrada nelas, ou o commit fica vermelho; o
excesso de arquivos é esse, não escopo.

**Helper privado em `use_cases/`.** `_unit_enablement.py` segue o precedente de
`scheduling/application/use_cases/_inputs.py` e `_publish.py`: código compartilhado por
use cases, fora da varredura "um arquivo por use case" (que ignora módulos com `_`).

### Pré-condições
- `python scripts/check_stage_deps.py 3.11-job-function-unit-enablement` verde.
- Head do Alembic em develop = `0004` (conferido); a nova é `0005`.

### Premissas técnicas
- Orquestração autônoma: localmente só checks focados — `pytest` unit e contrato em
  memória de staff (`-k fake` / sem Postgres), `ruff`, `mypy`, `scripts/check_layout.py`,
  `lint-imports`, `make docs-check`. `make check`, integração e e2e rodam no Actions
  (Postgres compartilhado).

### Estrutura de pastas afetada

```
src/restaurant_hub/features/staff/
├── domain/value_objects/unit_enablement.py          (novo)
├── domain/{entities/job_function.py, exceptions/errors.py}
├── application/use_cases/{_unit_enablement.py, set_job_function_units.py} (novos)
├── application/{dtos/*, errors.py, ports/out/*, use_cases/*}
└── adapters/{out/postgres/*, inbound/http/*}
migrations/versions/0005_job_function_units.py       (novo)
tests/{unit,contract,integration,e2e,fakes}/…/staff/
```

## 2. Tasks

### Task 01 — Domínio: `UnitEnablement` e o campo em `JobFunction`

- **Arquivos a criar:** `src/restaurant_hub/features/staff/domain/value_objects/unit_enablement.py`;
  `tests/unit/features/staff/domain/test_unit_enablement.py`
- **Arquivos a modificar:** `domain/entities/job_function.py`; `domain/exceptions/errors.py`;
  `adapters/inbound/http/error_handlers.py` (entrada 422 — totalidade do mapa);
  `tests/unit/features/staff/domain/test_job_function.py`;
  `tests/unit/features/staff/adapters/test_http_error_handlers.py` (24 entradas)
- **O que fazer:** VO frozen com `all_units`/`unit_ids`, `everywhere()`, `only(ids)`,
  `covers(unit_id)`; `__post_init__` impõe R2 (todas ⇔ conjunto vazio; conjunto sem id em
  branco) com `InvalidUnitEnablementError` (`StaffError`). `JobFunction.unit_enablement`
  com default `everywhere()` (concept D8), `is_enabled_in`, `with_enablement`.
- **Critério de aceite:** CA9a no domínio; `with_enablement` devolve nova instância
  revalidada; igualdade da função continua por identidade.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/staff -q
  uv run mypy src tests/fakes && uv run ruff check src tests
  ```
- **Commit sugerido:** `feat(staff): habilitação por unidade no domínio da função [3.11/task-01]`

---

### Task 02 — Persistência: schema e migration `0005`

- **Arquivos a criar:** `migrations/versions/0005_job_function_units.py`
- **Arquivos a modificar:** `adapters/out/postgres/tables.py`;
  `tests/integration/test_migration.py`;
  `tests/integration/features/staff/adapters/out/postgres/test_schema.py`;
  `tests/unit/features/staff/adapters/test_tables.py`
- **O que fazer:** coluna `enabled_in_all_units BOOLEAN NOT NULL DEFAULT true`; tabela
  `job_function_units (job_function_id, tenant_id, unit_id)`, PK `(job_function_id,
  unit_id)`, FK composta `(job_function_id, tenant_id)` → `job_functions (id, tenant_id)`
  `ON DELETE CASCADE`, índice `(tenant_id, unit_id)`. Migration escrita à mão; downgrade
  remove só o que ela criou.
- **Critério de aceite:** CA4 (linha anterior à migration fica com `enabled_in_all_units
  = true` e sem vínculo); downgrade da `0005` testado.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff/adapters/test_tables.py -q`
  (integração no CI).
- **Commit sugerido:** `feat(staff): tabela de habilitação de função por unidade [3.11/task-02]`

---

### Task 03 — `JobFunctionRepository`: L-JF1′, L-JF3′, L-JF4/5, L-JF6, L-JF7

- **Arquivos a modificar:** `application/ports/out/job_function_repository.py`;
  `tests/fakes/features/staff/in_memory_job_function_repository.py`;
  `adapters/out/postgres/{mappers.py,job_function_repository.py}`;
  `tests/contract/features/staff/test_job_function_repository_laws.py`;
  `tests/unit/features/staff/adapters/test_mappers.py`
- **O que fazer:** docstrings de lei (L-JF1′ grava a habilitação; L-JF3′ leva junto;
  L-JF4/5 reidratam; **L-JF6** `list_by_unit`; **L-JF7** `update_enablement`; L-JF2
  inalterada). Fake e Postgres; o adapter grava flag + vínculos na mesma transação e
  reidrata por consulta de vínculos; `list_by_unit` = flag verdadeira **ou** vínculo da
  unidade, ordem `L-ORD`.
- **Critério de aceite:** CA3 e CA8 (fake e Postgres, um corpo); CA9b (mapper recusa linha
  incoerente).
- **Comando de verificação:** `uv run pytest tests/contract/features/staff -q -k fake` +
  `tests/unit/features/staff/adapters/test_mappers.py`.
- **Commit sugerido:** `feat(staff): leis de habilitação no repositório de funções [3.11/task-03]`

---

### Task 04 — `EmployeeRepository`: L-E8

- **Arquivos a modificar:** `application/ports/out/employee_repository.py`;
  `tests/fakes/features/staff/in_memory_employee_repository.py`;
  `adapters/out/postgres/employee_repository.py`;
  `tests/contract/features/staff/test_employee_repository_laws.py`
- **O que fazer:** `units_referencing_job_function(tenant_id, job_function_id) ->
  frozenset[UnitId]` — ativos e inativos, tenant alheio vazio.
- **Critério de aceite:** CA8 (L-E8), inclusive registro desligado e isolamento de tenant.
- **Comando de verificação:** `uv run pytest tests/contract/features/staff -q -k fake`.
- **Commit sugerido:** `feat(staff): unidades que referenciam uma função no repositório de funcionários [3.11/task-04]`

---

### Task 05 — Application (e a borda da criação): criar e listar com unidades

- **Arquivos a criar:** `application/use_cases/_unit_enablement.py`
- **Arquivos a modificar:** `application/dtos/{commands,queries,results}.py`;
  `application/ports/out/access_guard.py` (`PERMISSION_MANAGE_TENANT`);
  `application/use_cases/{create_job_function,list_job_functions}.py`;
  `adapters/inbound/http/{schemas,router}.py` (só `unit_ids` na criação e
  `all_units`/`unit_ids` na resposta — Checkpoint B: sem isso o gerente do e2e fica 403
  entre T05 e T08);
  `tests/unit/features/staff/application/{test_job_function_use_cases,test_use_cases_authorize,test_dtos}.py`
  (vocabulário de permissões passa a incluir `manage_tenant`; criar em unidades vira
  multi-alvo em `_DE_DOIS_ALVOS`);
  `tests/unit/features/staff/adapters/{test_http_schemas,test_http_router_job_functions}.py`;
  `tests/e2e/features/staff/` (atores gerente/hr que criam função passam `unit_ids`)
- **O que fazer:** `unit_ids` no command (None = todas), `unit_id` na query, `all_units`/
  `unit_ids` no result. Helper privado que autoriza uma habilitação (R4) e a diferença
  entre duas (R5). Ordem de R8.
- **Critério de aceite:** CA1/CA2 em unit (guard stub registra chamadas em ordem
  `sorted`); "todas" sem `manage_tenant` sobe crua.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q`.
- **Commit sugerido:** `feat(staff): criar e listar funções por unidade [3.11/task-05]`

---

### Task 06 — Application: `SetJobFunctionUnitsUseCase`

- **Arquivos a criar:** `application/use_cases/set_job_function_units.py`;
  `tests/unit/features/staff/application/test_set_job_function_units.py`
- **Arquivos a modificar:** `application/dtos/commands.py`; `application/errors.py`
  (docstring de `JobFunctionInUseError` cobre o estreitamento); `composition_root.py`
  (totalidade da pasta de use cases);
  `tests/unit/features/staff/application/{test_application_guards,test_use_cases_authorize}.py`
  (18 use cases; a leitura entre autorizações é a exceção declarada do ADR 3.11.0001 e
  entra na matriz como tal); `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **O que fazer:** R5 + R8 (tenant → existência → diferença → transição → guarda L-E8 →
  `update_enablement`).
- **Critério de aceite:** CA7 completo em unit.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q`.
- **Commit sugerido:** `feat(staff): alterar as unidades de uma função [3.11/task-06]`

---

### Task 07 — Application: invariante funcionário × unidade (ADR 3.11.0002)

- **Arquivos a modificar:** `application/errors.py` (`JobFunctionNotEnabledInUnitError`);
  `adapters/inbound/http/error_handlers.py` (entrada `409`);
  `application/use_cases/{create_employee,assign_job_functions,copy_employee_to_unit}.py`;
  `composition_root.py` (repositório de funções na cópia);
  `tests/unit/features/staff/application/{test_create_employee,test_assign_job_functions,test_copy_employee_to_unit}.py`;
  `tests/unit/features/staff/adapters/test_http_error_handlers.py` (25 entradas)
- **O que fazer:** checagem após a referencial (R8); cópia com ordem própria (R8) e
  `JobFunctionRepository` injetado; erro nomeia a menor id (R10).
- **Critério de aceite:** CA5 e CA6 em unit.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q`.
- **Commit sugerido:** `feat(staff): funcionário só detém função habilitada na sua unidade [3.11/task-07]`

---

### Task 08 — HTTP: corpo, resposta e duas rotas

- **Arquivos a modificar:** `adapters/inbound/http/{dependencies,schemas,router}.py`;
  `composition_root.py` (override da rota nova);
  `tests/unit/features/staff/adapters/{test_http_router_job_functions,test_http_boundary_sweeps,test_composition_root_staff,test_http_schemas,test_http_dependencies}.py`
  (`_INVOCACOES`, `_TOTAL_DE_AUTORIZACOES`, `_TOTAL_DE_CAMPOS_ESCALARES`,
  `_TOTAL_DE_ROTAS_DE_STAFF`, `_TOTAL_DE_OVERRIDES_DE_STAFF`);
  `tests/e2e/features/staff/test_staff_authorization.py` (tabela de rotas) e e2e de
  CA1/CA2/CA5
- **O que fazer:** `SetJobFunctionUnitsRequest`; `GET /units/{unit_id}/job-functions` com
  `MANAGE_JOB_FUNCTIONS_IN_UNIT_ACCESS`; `PUT /job-functions/{job_function_id}/units`.
  Identificadores validados antes do guard (ADR 3.6.0002).
- **Critério de aceite:** CA1, CA2, CA3 (403), CA5, CA10, CA11 pela borda.
- **Comando de verificação:** `uv run pytest tests/unit/features/staff -q` (e2e no CI).
- **Commit sugerido:** `feat(staff): rotas de habilitação de função por unidade [3.11/task-08]`

---

### Task 09 — Docs: notas datadas

- **Arquivos a modificar:** `docs/overview.md` §3; `docs/domain/staff/workforce.md` §3.2 e
  §3.7 (+ `references`); `docs/domain/scheduling/shift-scheduling.md` (a frase "não
  decidida" sobre a #41). As erratas dos ADRs 3.2.0003, 3.4.0006 e 3.7.0001 já
  entraram no commit `stage 3.11: conceptual approved`.
- **Critério de aceite:** `make docs-check` verde; notas sem marca de lacuna aberta.
- **Comando de verificação:** `make docs-check`.
- **Commit sugerido:** `docs(staff): registrar a habilitação de função por unidade [3.11/task-09]`

## 3. Gate de saída da Stage

### Verificações automatizadas
- CI `lint-and-test` verde no head do PR (make check, integração, e2e, coverage ≥ 90%).
- `python scripts/check_technical_postexec.py docs/stages/3.11-job-function-unit-enablement/technical.md`.

### Verificações funcionais
- [ ] e2e: gerente cria função para a sua unidade e ela só aparece nela (CA1).
- [ ] e2e: cópia para unidade sem a função habilitada é 409 (CA5).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] Commit final `stage 3.11: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at`/`last_reviewed_at`
- [ ] ADRs novos em `accepted`

## 4. Ordem de dependência entre Tasks

```
T01 ─► T02 ─► T03 ─► T04 ─► T05 ─► T06 ─► T07 ─► T08 ─► T09
```
T03 depende de T02 (colunas); T06 usa o helper de T05 e a L-E8 de T04; T08 consome T05–T07.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Varredura não listada aqui fica vermelha | levar a entrada para a Task que a quebrou e registrar `[deviation]` |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs 3.11.0001 e 3.11.0002
- Skills: hex-arch-python, ddd-tactical-patterns, pytest-with-fakes, repository-pattern,
  fastapi-thin-adapter, composition-root, task-ordering-hex

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

<!-- END: post-execution -->

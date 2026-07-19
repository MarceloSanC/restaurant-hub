---
title: Technical — Stage 2.3 — Persistência de identity
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity-persistence, postgres, sqlalchemy-core, alembic, contract-tests, ci-gate]
status: done
created_at: 2026-07-19
updated_at: 2026-07-19
stage_id: 2.3-identity-persistence
stage_title: Persistência de identity
step_id: 2
step_title: Identidade, acesso e multi-tenancy
depends_on: [2.2-identity-application]
concept_ref: ./concept.md
issue_id: 22
branch: feat/22-2-3-identity-persistence
tasks_count: 12
---

# Technical — Stage 2.3 — Persistência de identity

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.3/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`, registrar a
>    decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 2.3: complete` e atualizar `roadmap.md`.

## 1. Contexto e estratégia de execução

### Resumo

Implementar os quatro repositórios Postgres dos ports-out publicados pela Stage 2.2,
com o schema em SQLAlchemy 2 Core, a migration inicial do projeto, mappers que
reidratam pelo construtor, testes de integração contra Postgres real e testes de
contrato que provam `fake ≡ real`. Junto vêm três correções que a Stage não pode
evitar: o driver Postgres (inexistente no `pyproject.toml`), a divergência de upsert
dos quatro fakes e o gate de CI, que hoje não tem banco.

### Estratégia

**Inside-out, na direção do fluxo de dependência** (skill `task-ordering-hex`), com
uma inversão deliberada no começo: a infraestrutura de teste vem **antes** dos
adapters, porque sem banco acessível nenhum adapter é verificável.

A ordem resolve quatro restrições simultâneas:

1. **Cada commit deixa `make check` verde.** Como o gate inclui cobertura ≥ 90%
   global, um adapter nunca é commitado antes dos seus testes — os dois entram na
   mesma Task, sempre.
2. **Port e adapter do mesmo port nunca na mesma Task** (PIPELINE §4.3), com **uma
   exceção declarada** na Task 02 — ver a justificativa lá.
3. **O CI ganha banco ANTES que o primeiro teste de integração exista.** Por isso a
   Task 06 (service de Postgres no `ci.yml`) vem **antes** da Task 07 (fixtures de
   integração), e não o contrário: a 06 não depende da 07, e inverter a ordem faria o
   push da 07 levar ao runner uma suíte que exige banco num CI que ainda não o tem —
   vermelho pelo exato motivo que esta Stage existe para corrigir.
4. **Mudanças repo-wide vêm primeiro e com escopo próprio.** As Tasks 01 e 06 não são
   do BC `identity` (tocam `pyproject`/`.importlinter` e o workflow de CI) e por isso
   carregam escopo de commit próprio — CONVENTIONS §4(a) exige o menor recorte que
   faz sentido sozinho, e "identity" seria desonesto para elas.
5. **Exceções declaradas ao critério de ≤ 5 arquivos** (PIPELINE §4.3, critério 2):
   Tasks **01, 04, 07 e 11** passam de 5. Em todas, o excedente é mecânico —
   `__init__.py` vazios, ou arquivos de configuração que a mesma mudança lógica
   obriga a tocar em conjunto (o `.importlinter` exige dependência nova no mesmo
   commit; o `.env.example` acompanha o `settings.py`). Nenhuma delas mistura escopos
   independentes, que é o que o critério protege.

As Tasks 09–10 são o núcleo; a **Task 11** (contrato) é a que cobra o objetivo da
Stage.

### Pré-condições

- Stage `2.2-identity-application` em `done` e **mergeada** em `develop`
  (`461d38a stage 2.2: complete`).
- Docker rodando; `docker compose up -d postgres` sobe `postgres:16-alpine`.
- `.env` da worktree define `POSTGRES_PORT` (5433 nesta worktree — worktrees
  paralelas usam portas próprias; **não presumir 5432**).
- `.venv` instalado (`make setup`).

### Premissas técnicas

- Python 3.12, SQLAlchemy 2 Core (sem ORM declarativo), Alembic já configurado
  (`alembic.ini` + `migrations/env.py`), `migrations/versions/` vazio.
- Os markers `integration` e `contract` já existem no `pyproject.toml`.
- Cobertura com `branch = true` e `fail_under = 90` (herdado da 2.2); `migrations/`
  está em `omit`.
- `make typecheck` roda `mypy src/ tests/fakes/` — **os fakes são type-checked**, e
  cada um declara `_conforms: <Port> = <Fake>()`. Isso acopla mecanicamente port e
  fake: mudar a assinatura de um Protocol sem atualizar o fake **quebra o gate no
  mesmo commit**. É a razão da exceção declarada na Task 02.
- `.env` é gitignored: as Tasks o ajustam localmente, mas quem entra no commit é o
  `.env.example`.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                          (M — Task 12)
├── features/identity/
│   ├── application/
│   │   ├── errors.py                            (M — Task 02)
│   │   └── ports/out/session_repository.py      (M — Task 02)
│   └── adapters/out/postgres/                   (novo — Tasks 04, 08, 09, 10)
│       ├── __init__.py
│       ├── tables.py
│       ├── mappers.py
│       ├── integrity_errors.py
│       ├── restaurant_repository.py
│       ├── unit_repository.py
│       ├── user_repository.py
│       └── session_repository.py
└── shared/infrastructure/
    ├── config/settings.py                       (M — Task 01)
    └── database/connection.py                   (M — Task 12)

migrations/
├── env.py                                       (M — Task 05)
└── versions/0001_identity_initial.py            (novo — Task 05)

tests/
├── conftest.py                                  (M — Task 07)
├── unit/
│   ├── shared/test_settings.py                  (M — Task 01)
│   ├── test_ci_workflow.py                      (M — Task 06)
│   ├── test_bootstrap.py                        (M — Task 12)
│   └── features/identity/
│       ├── adapters/                            (novo — Tasks 04, 08, 12)
│       ├── application/test_errors.py           (M — Task 02)
│       ├── application/test_repository_fakes.py (M — Task 03)
│       └── application/test_session_repository_fake.py (M — Task 02)
├── integration/                                 (novo — Tasks 07, 09, 10)
├── contract/features/identity/                  (novo — Task 11)
└── fakes/features/identity/                     (M — Tasks 02, 03)

.github/workflows/ci.yml                         (M — Task 06)
pyproject.toml / uv.lock / .env.example          (M — Task 01)
.importlinter                                    (M — Tasks 01, 12)
docs/LAYOUT.md                                   (M — Task 04)
docs/runbooks/validate-ci-gate.md                (M — Task 06)
docs/roadmap.md                                  (M — no fechamento, commit `[2.3/--]`)
```

> O `roadmap.md` **não pertence a Task nenhuma**: é atualizado no fechamento da Stage,
> num commit off-task `docs(roadmap): ... [2.3/--]` (CONVENTIONS §4(a)).

## 2. Tasks

### Task 01 — driver Postgres e esquema de URL

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `pyproject.toml` (dep `psycopg[binary]>=3.2`)
  - `uv.lock` (regenerado)
  - `.importlinter` (`psycopg` nas 4 listas de `forbidden_modules`)
  - `src/restaurant_hub/shared/infrastructure/config/settings.py` (default da URL)
  - `.env.example`
  - `tests/unit/shared/test_settings.py`
- **O que fazer:** o projeto declara SQLAlchemy mas **nenhum DBAPI** — verificado por
  `find_spec`: nem `psycopg` nem `psycopg2` presentes. Adicionar `psycopg[binary]` e
  migrar a URL para `postgresql+psycopg://` (concept §7 Decisão 8).
- **Detalhes técnicos:**
  - O cabeçalho do `.importlinter` **exige** que dependência nova entre nas listas de
    pureza no mesmo commit (4 listas com pacotes externos).
  - **`tests/unit/shared/test_settings.py:26` faz
    `assert settings.database_url.startswith("postgresql://")`** e passa a falhar com
    o esquema novo. Ajustar para `postgresql+psycopg://`. Sem isso a Task fica
    vermelha — e o `make check` de uma Task posterior é que acusaria.
  - `.env` local também muda, mas é gitignored (não entra no commit).
- **Critério de aceite:** `uv run python -c "import psycopg"` funciona;
  `make check` verde; nenhuma camada de domínio/aplicação importa `psycopg`.
- **Comando de verificação:**
  ```bash
  uv run python -c "import psycopg; print(psycopg.__version__)"
  uv run pytest tests/unit/shared/test_settings.py -v
  make check
  ```
- **Commit sugerido:** `build(tooling): declarar driver psycopg e fixar esquema da URL [2.3/task-01]`
  > Escopo `tooling`, não `identity`: nenhum arquivo desta Task pertence ao BC — são
  > dependências, contratos de import e configuração repo-wide (precedente no
  > CONVENTIONS §4(a): `fix(tooling): restaurar make check no scaffold limpo`).

---

### Task 02 — erros de chave duplicada, `purge_expired` no port e fake de sessão

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/errors.py`
  - `src/restaurant_hub/features/identity/application/ports/out/session_repository.py`
  - `tests/fakes/features/identity/in_memory_session_repository.py`
  - `tests/unit/features/identity/application/test_errors.py`
  - `tests/unit/features/identity/application/test_session_repository_fake.py`
- **O que fazer:** acrescentar os cinco erros de `IdentityError` que tornam "chave já
  gravada" idêntica no fake e no real (ADR 2.3.0003), declarar `purge_expired` no port
  de sessão (ADR 2.3.0004) e implementá-lo no fake de sessão, que também passa a
  rejeitar id e fingerprint duplicados.
- **Detalhes técnicos:**
  - `RestaurantAlreadyExistsError`, `UnitAlreadyExistsError`, `UserAlreadyExistsError`,
    `SessionAlreadyExistsError`, `SessionFingerprintAlreadyExistsError` — todos
    `IdentityError`, mensagens no padrão dos `*NotFoundError` existentes.
  - `purge_expired(self, before: datetime) -> int`, docstring fixando o predicado
    **`expires_at <= before`** (fronteira inclusiva, alinhada ao half-open de
    `is_active` — concept I9).
  - **Exceção declarada ao critério 4 de Task Atômica** (não misturar port com
    adapter do port): o fake **é** implementação do port, mas
    `tests/fakes/.../in_memory_session_repository.py:60` declara
    `_conforms: SessionRepository = InMemorySessionRepository()` e o `make typecheck`
    roda `mypy src/ tests/fakes/`. Declarar `purge_expired` no `Protocol` sem
    implementá-lo no fake **quebra o próprio check desta Task**. O acoplamento é
    mecânico e verificado, não conveniência. O que o critério 4 protege de verdade —
    desenhar port e implementação **de produção** no mesmo fôlego — segue respeitado:
    o adapter real de sessão só aparece na Task 10.
- **Critério de aceite:** cada erro novo é `IdentityError` **e** `DomainError`, e
  nenhum é `NotFoundError`; o fake de sessão implementa `purge_expired` com a
  fronteira inclusiva e rejeita id e fingerprint duplicados com erros distintos.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/ -v
  make typecheck && make check
  ```
- **Commit sugerido:** `feat(identity): erros de chave duplicada e expurgo no port de sessão [2.3/task-02]`

---

### Task 03 — os outros três fakes deixam de ser upsert

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `tests/fakes/features/identity/in_memory_restaurant_repository.py`
  - `tests/fakes/features/identity/in_memory_unit_repository.py`
  - `tests/fakes/features/identity/in_memory_user_repository.py`
  - `tests/unit/features/identity/application/test_repository_fakes.py`
- **O que fazer:** os três fakes restantes gravam com `dict[chave] = valor` (ou
  `extend`) e sobrescrevem em silêncio o que a PK do Postgres rejeita. Fazer cada
  `add` rejeitar chave já existente.
- **Detalhes técnicos:**
  - `InMemoryUserRepository.add`: checar `user.id in self.users` **antes** da checagem
    de e-mail — a ordem importa, id duplicado não é conflito de e-mail.
  - Vínculos duplicados também passam a ser rejeitados (a tabela real tem PK
    composta); a 2.2 já deduplica `unit_ids` no use case, então nenhum caminho de
    produção regride.
  - **Inverter** `test_regravar_o_mesmo_usuario_nao_e_conflito_de_email` — o teste
    afirmava o oposto do docstring do próprio port ("É inserção, não upsert").
    Renomear e registrar no docstring por que a expectativa virou.
  - Registrar em §7 a lista **real** de testes da 2.2 que precisaram mudar.
- **Critério de aceite:** os quatro fakes (com o de sessão da Task 02) levantam o
  `*AlreadyExistsError` esperado; a suíte inteira da 2.2 volta a passar;
  `mypy src/ tests/fakes/` limpo.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/ -v
  make check
  ```
- **Commit sugerido:** `fix(identity): fakes de repositório passam a rejeitar chave duplicada [2.3/task-03]`

---

### Task 04 — schema em SQLAlchemy Core

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/__init__.py`
  - `src/restaurant_hub/features/identity/adapters/out/postgres/__init__.py`
  - `src/restaurant_hub/features/identity/adapters/out/postgres/tables.py`
  - `tests/unit/features/identity/adapters/__init__.py`
  - `tests/unit/features/identity/adapters/test_tables.py`
- **Arquivos a modificar:**
  - `docs/LAYOUT.md` (§2 — declarar `tests/unit/features/<feature>/adapters/`)
- **O que fazer:** descrever as cinco tabelas do concept §9 como um `MetaData` em
  **Core** (sem ORM declarativo — regra de stack do CLAUDE.md), com **toda constraint
  nomeada**.
- **Detalhes técnicos:** exatamente o §9 do concept, já validado empiricamente contra
  Postgres 16 antes da aprovação. O que não pode escapar:
  - `uq_units_id_restaurant` e `uq_users_id_tenant` são **âncoras obrigatórias** das
    FKs compostas — sem elas a migration nem roda.
  - `unit_memberships` tem `tenant_id` **NOT NULL** e **duas** FKs compostas.
  - `users`: `role` NOT NULL + `ck_users_role_known` +
    `ck_users_tenant_iff_platform_admin` + `ck_users_email_normalized` +
    `uq_users_email`.
  - `sessions` **não** tem `tenant_id`; tem `uq_sessions_fingerprint` e índices em
    `user_id` e `expires_at`.
  - Texto em `TEXT` (nunca `CHAR(n)`, que faria padding e quebraria o round-trip
    verbatim); tempo em `TIMESTAMP WITH TIME ZONE` sem precisão reduzida.
  - `docs/LAYOUT.md` §2 hoje declara, sob `tests/unit/features/<feature>/`, apenas
    `domain/` e `application/`. Acrescentar `adapters/` na árvore — mesmo movimento
    (e mesma justificativa) que a Stage 2.2 fez ao acrescentar `tests/fakes/shared/`:
    CLAUDE.md nota 1 proíbe criar arquivo fora do LAYOUT sem justificativa, então a
    declaração entra no commit que cria o diretório.
- **Critério de aceite:** teste unitário (sem banco) assere o conjunto de tabelas, os
  nomes de constraint, e que `sessions` não tem coluna de tenant nem de valor de token.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_tables.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): descrever schema do BC em sqlalchemy core [2.3/task-04]`

---

### Task 05 — migration inicial + `target_metadata` do Alembic

- **Arquivos a criar:**
  - `migrations/versions/0001_identity_initial.py`
- **Arquivos a modificar:**
  - `migrations/env.py` (`target_metadata = identity_metadata`)
- **O que fazer:** primeira migration do projeto, com `upgrade()` **e** `downgrade()`
  funcionais.
- **Detalhes técnicos:**
  - `down_revision = None`; `revision = "0001"`.
  - `downgrade()` derruba na ordem inversa das dependências de FK.
  - `migrations/` está em `omit` da cobertura, então a migration não conta para o
    gate — quem a valida de verdade é a Task 07 (aplicar/reverter contra o banco).
- **Critério de aceite:** `alembic upgrade head` cria as cinco tabelas em banco limpo
  e `alembic downgrade base` as remove sem erro.
- **Comando de verificação:**
  ```bash
  docker compose up -d postgres
  uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head
  make check
  ```
- **Commit sugerido:** `feat(identity): migration inicial do schema de identity [2.3/task-05]`

---

### Task 06 — service de Postgres no CI + invariante do workflow + runbook

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `.github/workflows/ci.yml`
  - `tests/unit/test_ci_workflow.py`
  - `docs/runbooks/validate-ci-gate.md`
- **O que fazer:** o gate do runner ganha banco **antes** de existir o primeiro teste
  que precisa dele, e a exigência passa a ser protegida por teste (concept CA18, I12).
- **Detalhes técnicos:**
  - `ci.yml`: `services: postgres` (`postgres:16-alpine`, `--health-cmd pg_isready
    --health-retries 10`) + `DATABASE_URL` via `env:` do job. **Não** acrescentar
    argumento ao `make check` — invariante I3 da Stage 1.2: política de CI viaja por
    `env:`, nunca por linha de comando, senão o argumento de transitividade do
    runbook deixa de valer.
  - `test_ci_workflow.py`: asserir que o job de gate declara o service **e** a
    `DATABASE_URL`, além do `fetch-depth: 0` e do `make check` literal já cobertos.
    Ajustar a nota de escopo do módulo, que hoje diz cobrir "só invariantes cuja
    quebra é silenciosa", para incluir também "requisitos de ambiente dos quais o
    veredito do gate depende".
  - `validate-ci-gate.md`: nova §Class para a classe "teste de integração falha", com
    a **precondição de ambiente** escrita ao lado do patch — a §Maintenance do runbook
    exige exatamente isso quando o gate endurece, e exige atualizar `updated_at`.
  - Esta Task **não depende** da 07: as asserções são sobre o conteúdo do `ci.yml`, e
    subir um service que ainda ninguém usa é inócuo.
- **Critério de aceite:** CA18 — remover o service, a `DATABASE_URL` ou o `make check`
  literal do `ci.yml` faz `pytest tests/unit/test_ci_workflow.py` reprovar.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/test_ci_workflow.py -v
  make check
  ```
- **Commit sugerido:** `ci(gate): exigir postgres real no job de gate do CI [2.3/task-06]`
  > Escopo `gate`, não `identity`: o workflow e o runbook são infraestrutura do gate,
  > não do BC. O runbook viaja junto porque documenta literalmente esta mudança e a
  > §Maintenance o exige na mesma Stage.

---

### Task 07 — infraestrutura de teste com banco real

- **Arquivos a criar:**
  - `tests/integration/conftest.py`
  - `tests/integration/test_migration.py`
  - a cadeia de `__init__.py` até
    `tests/integration/features/identity/adapters/out/postgres/`
    (os níveis que ainda não existirem)
- **Arquivos a modificar:**
  - `tests/conftest.py` (remover a fixture `test_engine`, SQLite, herdada do template)
- **O que fazer:** dar à suíte um banco de verdade, **sem caminho de skip**
  (ADR 2.3.0001). O CI já tem o service desde a Task 06, então este é o primeiro
  commit em que a suíte exige banco — e o runner já sabe servi-lo.
- **Detalhes técnicos:**
  - Fixture session-scoped que resolve a `DATABASE_URL`, conecta e **falha alto** com
    mensagem acionável ("suba o Postgres com `make docker-up`") se não conectar.
    **Nunca** `pytest.skip`; não existe variável que desligue a exigência.
  - O schema do banco de teste é criado aplicando a **migration** (não
    `metadata.create_all`), para que a migration seja exercitada a cada execução.
  - Isolamento entre testes por `TRUNCATE ... CASCADE`.
  - `test_migration.py` assere **o conjunto de tabelas** após `upgrade` (CA1) e que
    `downgrade base` as remove — o comando da Task 05 só olhava exit code.
  - A fixture `test_engine` removida não é usada por teste nenhum (verificado:
    `grep -rn "test_engine" tests/` só encontra a definição).
- **Critério de aceite:** CA1; com Postgres no ar `pytest tests/integration` passa;
  com o container derrubado a suíte **falha** com a mensagem acionável (nunca
  skip, nunca verde).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration -v
  docker compose stop postgres && uv run pytest tests/integration; docker compose start postgres
  make check
  ```
- **Commit sugerido:** `test(identity): fixtures de integração contra postgres real [2.3/task-07]`

---

### Task 08 — mappers e tradução de erro de integridade

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/mappers.py`
  - `src/restaurant_hub/features/identity/adapters/out/postgres/integrity_errors.py`
  - `tests/unit/features/identity/adapters/test_mappers.py`
  - `tests/unit/features/identity/adapters/test_integrity_errors.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** conversão linha↔entidade e a tradução de `IntegrityError` para a
  hierarquia `IdentityError`.
- **Detalhes técnicos:**
  - **Reidratação passa pelo construtor** (concept I1): `Role.from_string(...)` →
    `Email(...)` → `User(...)`. **Proibido** `object.__setattr__`, `__new__` ou
    qualquer atalho — é a proteção que a auditoria da 2.1 pediu explicitamente.
  - Ordem de validação fixada no concept §6; linha corrompida levanta a exceção
    nomeada naquela linha da tabela.
  - Datetimes: `.astimezone(UTC)` na leitura (concept I10) — o psycopg devolve no
    fuso da sessão, não em UTC (verificado empiricamente contra o banco).
  - `integrity_errors.py`: mapa **nome-de-constraint → exceção**. Só constraints de
    negócio. FK **não** é traduzida (concept §7 Decisão 7) — a função devolve o erro
    original, e há teste que fixa isso (CA20/I11), para que a exceção deliberada não
    vire omissão silenciosa.
  - Nome `integrity_errors.py` (não `errors.py`) para não colidir conceitualmente com
    `application/errors.py`, que é a hierarquia — este é o tradutor.
- **Critério de aceite:** CA20 e a metade unitária de CA15 — testes sem banco cobrem
  o round-trip de cada entidade, a normalização de fuso, cada entrada do mapa **e** o
  caso não traduzido (FK sobe como `IntegrityError`).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/ -v
  make check
  ```
- **Commit sugerido:** `feat(identity): mappers de persistência e tradução de erro de integridade [2.3/task-08]`

---

### Task 09 — repositórios de restaurante e unidade

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/restaurant_repository.py`
  - `src/restaurant_hub/features/identity/adapters/out/postgres/unit_repository.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_restaurant_repository.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_unit_repository.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** os dois repositórios mais simples, estabelecendo o padrão que os
  outros dois seguem.
- **Detalhes técnicos:** construtor recebe `Engine`; cada método público abre
  `with engine.begin()` (concept §7 Decisão 6). `add` traduz violação de PK para o
  `*AlreadyExistsError` correspondente; `find_by_id` devolve `None` quando não há linha.
- **Critério de aceite:** CA2 (round-trip **campo a campo**, `"  Cantina  "` com
  espaços preservados), CA3 (parte de restaurante e unidade), CA6 (parte de
  restaurante e unidade).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/identity/adapters/out/postgres/ -v
  make check
  ```
- **Commit sugerido:** `feat(identity): repositórios postgres de restaurante e unidade [2.3/task-09]`

---

### Task 10 — repositórios de usuário e sessão

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/postgres/user_repository.py`
  - `src/restaurant_hub/features/identity/adapters/out/postgres/session_repository.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_user_repository.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_session_repository.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** os dois repositórios com regra de verdade — escrita transacional de
  usuário + credencial + vínculos, e a semântica normativa de sessão.
- **Detalhes técnicos:**
  - `UserRepository.add` grava as três coisas numa **única** `engine.begin()`
    (docstring do port). `find_by_id` **não** seleciona `password_hash`;
    `find_credentials_by_email` devolve `UserCredentials` numa ida só.
  - `list_memberships` filtra por `user_id` — conforme, mas a visibilidade **não pode
    depender** disso (concept I4; a 2.2 permite adapter permissivo).
  - `SessionRepository.find_by_fingerprint` **não filtra** revogada nem expirada (I6);
    `revoke` usa `WHERE revoked_at IS NULL` para preservar o instante da **primeira**
    revogação (I7); id inexistente é no-op; `purge_expired` deleta por
    `expires_at <= before` e devolve `rowcount`.
- **Critério de aceite:** CA3 (parte de usuário e sessão), CA4, CA5, CA6 (parte de
  usuário e sessão, incluindo fingerprint duplicado), CA7, CA8, CA9, CA10, CA11,
  CA12, CA13, CA14, CA15 (parte de integração).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/identity/adapters/out/postgres/ -v
  make check
  ```
- **Commit sugerido:** `feat(identity): repositórios postgres de usuário e sessão [2.3/task-10]`

---

### Task 11 — testes de contrato: fake ≡ real

- **Arquivos a criar:**
  - `tests/contract/features/__init__.py` + `tests/contract/features/identity/__init__.py`
  - `tests/contract/features/identity/conftest.py`
  - `tests/contract/features/identity/test_restaurant_and_unit_contract.py`
  - `tests/contract/features/identity/test_user_repository_contract.py`
  - `tests/contract/features/identity/test_session_repository_contract.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** a Task que cobra o objetivo da Stage — **o mesmo corpo de teste**
  rodando contra o fake e contra o adapter Postgres, parametrizado por fixture
  (`pytest-with-fakes` §contract).
- **Detalhes técnicos:**
  - Fixture parametrizada devolvendo as duas implementações; o corpo do teste **não
    sabe** qual está usando.
  - Cobrir **todos os métodos dos quatro ports**. Ficam fora, explicitamente, os
    ganchos que só existem no fake e não pertencem ao port: `seed_membership`,
    `list_all_memberships`, `leak_foreign_memberships`, `find_calls` (CA16).
  - Coleções de vínculos comparadas como **conjunto** — ordenação não faz parte do
    contrato (o fake devolve ordem de inserção; SQL sem `ORDER BY` não garante ordem).
  - Datetimes: asserir `tzinfo` além do instante.
  - **Exceção declarada ao critério 2** (≤ 5 arquivos): são 6, sendo 2 `__init__.py`
    vazios; o conteúdo é uma única mudança lógica (a suíte de contrato) e quebrá-la
    por arquivo separaria testes que compartilham a mesma fixture.
- **Critério de aceite:** CA16; toda divergência conhecida do concept §7 Decisão 3
  tem teste que a teria pegado.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract -v
  make check
  ```
- **Commit sugerido:** `test(identity): testes de contrato provando fake equivalente ao real [2.3/task-11]`

---

### Task 12 — wiring no composition root

- **Arquivos a criar:**
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
  - `src/restaurant_hub/shared/infrastructure/database/connection.py`
  - `.importlinter`
  - `tests/unit/test_bootstrap.py`
- **O que fazer:** montar os quatro repositórios no único ponto de wiring, fixar o
  fuso da sessão no `Engine` e liberar a exceção de import que o wiring cria.
- **Detalhes técnicos:**
  - `ApplicationDependencies` ganha os quatro repositórios; `wire_dependencies`
    constrói o `Engine` e injeta. Nenhum singleton global; nada instanciado fora daqui.
  - `build_engine` passa `connect_args={"options": "-c timezone=UTC"}` (concept
    Decisão 6 — cinto e suspensório com o `.astimezone(UTC)` do mapper).
  - **`.importlinter` precisa de `ignore_imports` no contrato `shared-independence`.**
    Hoje `shared/infrastructure/http/app.py:22` já importa `composition_root`; quando
    o composition_root passar a importar `features.identity.adapters.out.postgres`, a
    cadeia `shared → composition_root → features` viola o contrato e `make
    import-check` fica **vermelho**. O próprio cabeçalho do `.importlinter` previu
    isto: *"a cadeia shared/infrastructure/http/app → composition_root →
    features.adapters exigirá `ignore_imports` no contrato shared-nao-importa-features
    … hoje o composition_root não importa features, então não há supressão."* É a
    exceção já declarada em LAYOUT §6, agora efetivada — com comentário no arquivo
    apontando para lá.
  - `tests/unit/test_bootstrap.py` já chama `wire_dependencies()` e passa a exercitar
    o `ApplicationDependencies` com quatro campos; ajustar o que for necessário. A
    LAYOUT §2 nomeia esse arquivo como o teste do composition root "sem feature", e é
    por isso que as asserções **específicas de identity** (CA17) ficam no arquivo novo
    sob `adapters/`, declarado no LAYOUT pela Task 04 — o bootstrap continua sendo o
    teste agnóstico de feature.
- **Critério de aceite:** CA17 — `wire_dependencies()` devolve os quatro repositórios,
  e um teste mecânico verifica que nenhum módulo fora de `composition_root.py` importa
  `features.identity.adapters.out.postgres`. `make import-check` verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_composition_root_identity.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): wiring dos repositórios postgres no composition root [2.3/task-12]`

---

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
docker compose up -d postgres          # o gate exige banco real (ADR 2.3.0001)
make check                             # lint + typecheck + layout + import + lock + docs + testes com cobertura
uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head
uv run python scripts/check_technical_postexec.py docs/stages/2.3-identity-persistence/technical.md
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
```

### Verificações funcionais

- [ ] Migration aplica **e reverte** contra Postgres real, com saída colada.
- [ ] Os quatro repositórios exercitados contra o banco real (é o e2e possível desta
      Stage — a API só existe na 2.4).
- [ ] Suíte de contrato verde contra **as duas** implementações.
- [ ] Com o container de Postgres parado, a suíte **falha** — nunca fica verde por
      ter pulado.
- [ ] **CA19** — um teste de integração deliberadamente quebrado derruba o CI, com
      link do run colado. É demonstração pontual de gate, não teste regressivo: quem
      protege I12 daqui em diante é o `test_ci_workflow.py` da Task 06 (CA18).

### Checklist de fechamento da Stage

- [ ] Todas as 12 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch, **com Postgres no ar**
- [ ] Cobertura ≥ 90% em cada arquivo tocado (não só na média global)
- [ ] Auditoria de testes com todos os itens "sim", incluindo mutação real no mapper
      e no filtro de tenant
- [ ] §7 reflete a execução real (incluindo a lista de testes da 2.2 que mudaram)
- [ ] `roadmap.md` atualizado em commit `[2.3/--]`: Stage `done`, datas, nota datada
      de reconciliação — **incluindo a correção da descrição humana** sobre
      `tenant_id` em todas as tabelas (concept §7 Decisão 9)
- [ ] ADRs 2.3.0001–2.3.0005 em `status: accepted`
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

Lista de arestas (uma linha por dependência real — deliberadamente **não** um
diagrama ASCII, cuja arte é fácil de desalinhar e passar a afirmar uma ordem que
ninguém quis):

| Task | Depende de | Por quê |
|---|---|---|
| 01 driver + URL | — | precede tudo que conecta: sem DBAPI não há conexão |
| 02 erros + port + fake de sessão | — | camada application pura |
| 03 três fakes restantes | 02 | usa os erros que a 02 declara |
| 04 tables | 01 | `sqlalchemy` já estava, mas o schema só é exercitável com driver |
| 05 migration | 04 | a migration materializa o `MetaData` da 04 |
| 06 CI + runbook | — | **independente**; vem cedo de propósito (§1 restrição 3) |
| 07 fixtures de integração | 05, 06 | cria o schema aplicando a migration (05); e o CI já precisa saber servir banco (06) |
| 08 mappers | 02, 04 | nomes de erro (02) e de coluna (04). **NÃO depende de 07** — seus testes são unitários, sem banco |
| 09 repos restaurante/unidade | 07, 08 | precisa de fixtures e mappers |
| 10 repos usuário/sessão | 07, 08 | idem |
| 11 contrato | 03, 09, 10 | precisa das duas implementações (fakes corrigidos + adapters reais) |
| 12 composition root | 09, 10 | liga os adapters; exige a supressão de import |

Pontos que costumam ser lidos errado:

- **07 depende de 05, não o contrário.** As fixtures criam o schema aplicando a
  migration, então a migration precisa existir antes.
- **06 antes de 07 é deliberado.** A 06 não depende de nada; colocá-la depois faria o
  push da 07 levar ao runner uma suíte que exige banco num CI sem service.
- **08 não depende de 07.** Mappers são testados sem banco; só 09/10 juntam as duas
  linhas.
- **02 antes de 03** por coesão dos erros — 03 usa o que 02 declara.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `psycopg[binary]` sem wheel para a plataforma | cair para `psycopg2-binary` e reverter o esquema da URL; registrar `[deviation]` em §7 |
| Cobertura < 90% em arquivo de adapter por ramo de erro difícil de forçar | forçar a violação por `INSERT` direto no teste de integração; se sobrar ramo genuinamente inalcançável, justificar por escrito no relatório (nunca `# pragma: no cover` silencioso) |
| `TRUNCATE` entre testes ficar lento | trocar por transação com rollback por teste; a fixture já isola a decisão num só lugar |
| Service de Postgres no CI subir mais devagar que o job | `--health-cmd pg_isready --health-retries 10` no service (o runner espera o health check) |
| Ajuste dos fakes quebrar mais testes da 2.2 que o previsto | são mudanças mecânicas de expectativa; se algum teste revelar **regra** e não expectativa, parar e registrar — pode indicar que o port precisa de revisão |
| `ignore_imports` da Task 12 mascarar violação real | a supressão é a mais estreita possível (só o par `composition_root → features.identity.adapters`), com comentário apontando para LAYOUT §6; o teste mecânico de CA17 cobre o que a supressão deixa de cobrir |

## 6. Referências

- [`./concept.md`](./concept.md) — §5 invariantes, §9 schema já validado
  empiricamente, §11 critérios de aceite
- [`../../roadmap.md`](../../roadmap.md) — bloco `2.3-identity-persistence`, ROADMAP-3
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- [`../../LAYOUT.md`](../../LAYOUT.md) — §2 estrutura, §3 dependências, §6 exceção do
  composition root
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `2_3_`)
- [`../../runbooks/validate-ci-gate.md`](../../runbooks/validate-ci-gate.md) —
  §Maintenance (exige extensão nesta Stage)
- Skills aplicáveis: `repository-pattern`, `composition-root`, `pytest-with-fakes`,
  `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. Apenas esta seção é editável após
> `status: done` (enquanto a Stage não mergeou). Modo autônomo (ADR 0.0.0004):
> decisões reversíveis-baratas são registradas aqui como `[decision]` sem pergunta.

<!-- END: post-execution -->

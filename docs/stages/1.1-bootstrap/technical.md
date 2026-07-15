---
title: Technical — Bootstrap do projeto
description: Plano de execução da Stage 1.1 — Makefile Windows-nativo, uv.lock versionado com lock-check, suite de testes do kernel shared, gate de cobertura ativo, import-linter e docs corrigidos
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, bootstrap, makefile, uv, import-linter, coverage]
status: done
created_at: 2026-07-14
updated_at: 2026-07-14
stage_id: 1.1-bootstrap
stage_title: Bootstrap do projeto
step_id: 1
step_title: Fundação do repositório
depends_on: []
concept_ref: ./concept.md
issue_id: 1
branch: feat/1-1-1-bootstrap
tasks_count: 8
---

# Technical — Stage 1.1 — Bootstrap do projeto

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [1.1/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 1.1: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/1-1-1-bootstrap` (ver `CONVENTIONS.md` §4).

## 1. Contexto e estratégia de execução

### Resumo

Automatizar e completar o scaffolding no Windows nativo: Makefile com
receitas shell-agnostic e `uv sync` (lock versionado + `uv lock --check`),
casa dupla do `UV_SYSTEM_CERTS`, suite de testes do kernel `shared/` +
bootstrap para viabilizar o gate de cobertura ≥ 90% dentro do
`make check`, import-linter espelhando LAYOUT §3 (no que é expressável),
e correção de README/runbook/roadmap. Detalhes e porquês:
[`concept.md`](./concept.md).

### Estratégia

Stage de **fundação** (camada-alvo `bootstrap`) — a ordem default da
skill `task-ordering-hex` (TDD inside-out por camada de domínio) não se
aplica; a ordem escolhida é **destravar → testar → apertar → documentar**,
mantendo `make check` verde em todo commit:

1. Base de tooling primeiro (Makefile portável + lock) — destrava tudo.
2. Config de env (settings) — independente, cedo para valer nas
   verificações seguintes.
3. Testes do kernel `shared/` **antes** de ligar o gate de cobertura
   (senão o gate nasce vermelho e quebra a regra do build verde).
4. Só então o flip do `--cov` no `check` (Task 05) e o import-linter
   (Task 06).
5. Docs e roadmap por último (documentam o estado final real).

### Pré-condições

- Issue #1 OPEN; branch `feat/1-1-1-bootstrap` ativa; concept `done`.
- **Setup de máquina (uma vez, antes da Task 01 — não gera commit):**
  1. `C:\msys64\usr\bin` no **PATH do usuário Windows** (append/última
     posição — decisão ADR 1.1.0001; nunca prepend).
  2. `UV_SYSTEM_CERTS=1` como **variável de ambiente do usuário**.
  3. Verificações: `make --version` → GNU Make 4.4.1;
     `Get-Command git` → `C:\Program Files\Git\cmd\git.exe` (o git do
     MSYS2 NÃO pode ganhar).

### Premissas técnicas

- Python 3.12 (`.python-version`), uv instalado.
- `make check` fecha verde hoje com a receita manual (baseline da issue).
- Cobertura atual: 33% (69/103 statements descobertos) — módulos listados
  no concept §5.

### Estrutura de pastas afetada

```
Makefile
pyproject.toml
uv.lock                          (novo, versionado)
.importlinter                    (novo)
.pre-commit-config.yaml
.gitignore
.claude/settings.json            (novo)
.claude/settings.local.json      (sai do rastreamento)
scripts/clean.py                 (novo)
README.md
docs/runbooks/validate-ci-gate.md
docs/LAYOUT.md
docs/roadmap.md
tests/
├── unit/shared/                 (novo)
└── e2e/test_app_smoke.py        (novo)
```

## 2. Tasks

### Task 01 — Makefile Windows-nativo + uv sync + lock-check

- **Arquivos a criar:**
  - `scripts/clean.py`
  - `uv.lock` (gerado por `make setup`; o arquivo untracked existente
    será sobrescrito pela geração e versionado aqui)
- **Arquivos a modificar:**
  - `Makefile`
- **O que fazer:**
  Reescrever as receitas do Makefile sem construtos POSIX:
  - `setup`: `uv sync --extra dev` + `uv run pre-commit install
    --install-hooks --hook-type pre-commit --hook-type commit-msg`
    (incondicional — o arquivo de config existe no repo) + mensagens via
    `@echo` simples.
  - `install`: `uv sync --extra dev`.
  - `help`: linhas `@echo` sem cores/`printf` (texto ASCII simples, sem
    parênteses, para portabilidade cmd/sh).
  - `clean`: delega para `uv run python scripts/clean.py` (remove
    `__pycache__`, `*.egg-info`, `.pytest_cache`, `.mypy_cache`,
    `.ruff_cache`, `dist/`, `build/`, `htmlcov/`, `.coverage`,
    `coverage.xml`, `tree.txt` — mesma lista da receita atual).
  - `worktree`: validação de `BRANCH` via `ifndef BRANCH` +
    `$(error ...)` (sintaxe de make puro, sem shell).
  - `test-cov`: mensagem final via `@echo`.
  - Novo alvo `lock-check`: `uv lock --check`.
  - `check` passa a: `lint typecheck layout-check lock-check docs-check
    test` (cobertura entra na Task 05).
  Rodar `make setup` para gerar o `uv.lock` e versionar o lock.
- **Detalhes técnicos:**
  - `scripts/clean.py`: stdlib puro (`pathlib`, `shutil`), idempotente,
    imprime o que removeu; precisa passar `ruff` (mypy cobre só `src/`).
  - Não usar `$(shell ...)` com comandos POSIX; não usar `if [ ... ]`.
- **Critério de aceite:**
  - `Select-String -Path Makefile -Pattern 'if \[ |find |rm -rf|printf'`
    retorna vazio.
  - `make setup` roda verde em PowerShell comum; `uv.lock` existe e está
    versionado; `make lock-check` verde; `make check` verde.
- **Comando de verificação:**
  ```powershell
  make setup
  make lock-check
  make check
  Select-String -Path Makefile -Pattern 'if \[ |find |rm -rf|printf'   # vazio
  ```
- **Commit sugerido:** `build(tooling): tornar Makefile Windows-nativo com uv sync e lock-check [1.1/task-01]`

---

### Task 02 — Casa do UV_SYSTEM_CERTS e untrack do settings.local.json

- **Arquivos a criar:**
  - `.claude/settings.json`
- **Arquivos a modificar:**
  - `.gitignore`
  - `.claude/settings.local.json` (remoção do rastreamento via
    `git rm --cached` — o arquivo permanece no disco)
- **O que fazer:**
  Criar `.claude/settings.json` com `env.UV_SYSTEM_CERTS = "1"` (e migrar
  a permissão compartilhável `Bash(git mv *)` se fizer sentido mantê-la
  como config de projeto); `git rm --cached .claude/settings.local.json`;
  adicionar `.claude/settings.local.json` ao `.gitignore` (seção IDEs) —
  conforme concept §6.
- **Detalhes técnicos:**
  - A variável de ambiente do usuário Windows já foi gravada no setup de
    máquina (pré-condição §1) — esta Task cobre a metade versionada.
- **Critério de aceite:**
  - `git ls-files .claude/settings.local.json` retorna vazio;
    `.claude/settings.json` rastreado com o env; `make check` verde.
- **Comando de verificação:**
  ```powershell
  git ls-files .claude/settings.local.json    # vazio
  git ls-files .claude/settings.json          # presente
  make check
  ```
- **Commit sugerido:** `chore(tooling): mover UV_SYSTEM_CERTS para settings versionado [1.1/task-02]`

---

### Task 03 — Testes unit do kernel shared (domain + ports + clock/uuid)

- **Arquivos a criar:**
  - `tests/unit/shared/__init__.py`
  - `tests/unit/shared/test_pagination.py`
  - `tests/unit/shared/test_exceptions.py`
  - `tests/unit/shared/test_clock_and_id_generator.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Testes unitários (sem I/O) para: `shared/domain/value_objects/
  pagination.py` (construção, validações/invariantes, propriedades
  derivadas), `shared/domain/exceptions/base.py` (hierarquia e
  mensagens), `shared/infrastructure/clock/system_clock.py` e
  `shared/infrastructure/uuid_generator/uuid4_generator.py` (satisfazem
  os Protocols `Clock`/`IdGenerator` de `shared/application/ports/out/` e
  retornam valores do tipo/forma esperados).
- **Detalhes técnicos:**
  - Ler cada módulo antes de testar — cobrir todas as branches (a
    auditoria de testes vai aplicar mutação real).
  - Marcar com `@pytest.mark.unit` conforme markers do pyproject.
- **Critério de aceite:**
  - Módulos listados com 100% no `--cov-report=term-missing`;
    `make check` verde.
- **Comando de verificação:**
  ```powershell
  # --cov-fail-under=0 anula o fail_under global do pyproject NESTA inspeção
  # parcial (o gate global só liga na Task 05, após a suite completa)
  uv run pytest tests/unit/shared/ -v --cov=src/restaurant_hub --cov-report=term-missing --cov-fail-under=0
  make check
  ```
- **Commit sugerido:** `test(shared): cobrir pagination, exceptions, clock e id generator [1.1/task-03]`

---

### Task 04 — Testes de infra restante + e2e da app factory

- **Arquivos a criar:**
  - `tests/unit/shared/test_settings.py`
  - `tests/unit/shared/test_database_and_logging.py`
  - `tests/unit/test_bootstrap.py`
  - `tests/e2e/test_app_smoke.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Cobrir o restante do kernel: `shared/infrastructure/config/settings.py`
  (defaults, leitura de env), `shared/infrastructure/database/
  connection.py` (criação de engine com config de teste),
  `shared/infrastructure/logging/config.py` (configuração aplica nível/
  formato), `composition_root.py` + `main.py` (wiring monta e o módulo
  `main` expõe `app`), e e2e de smoke da app factory usando a fixture
  `client` existente (`create_app` responde em rota conhecida —
  healthcheck ou 404 bem-formado — exercitando `http/app.py`,
  `error_handlers.py` e `middlewares.py`).
- **Detalhes técnicos:**
  - Ler cada módulo antes de escrever os testes; e2e usa `ASGITransport`
    (sem porta TCP).
  - Se algum handler/middleware tiver branch inatingível sem feature
    real, exercitar via requisição sintética que dispare o handler.
- **Critério de aceite:**
  - Cobertura global ≥ 90% (`uv run pytest tests/ --cov=src/restaurant_hub`
    passa com `fail_under = 90`); `make check` verde.
- **Comando de verificação:**
  ```powershell
  uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
  make check
  ```
- **Commit sugerido:** `test(shared): cobrir settings, database, logging, bootstrap e smoke e2e da app [1.1/task-04]`

---

### Task 05 — Ativar gate de cobertura no make check

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `Makefile`
- **O que fazer:**
  Novo alvo `test-gate`: `uv run pytest tests/ --cov=src/restaurant_hub
  --cov-report=term-missing` (dispara o `fail_under = 90` do pyproject).
  `check` passa a: `lint typecheck layout-check lock-check docs-check
  test-gate`. `make test`/`test-fast` permanecem sem cov (loop rápido —
  concept §6).
- **Critério de aceite:**
  - `make check` verde **com** o gate ativo; remover temporariamente um
    teste faz `make check` falhar (prova de que o gate morde — aplicar,
    observar, reverter; sem commitar o estado quebrado).
- **Comando de verificação:**
  ```powershell
  make check
  # prova do gate (aplicar -> observar exit != 0 -> reverter):
  git mv tests/e2e/test_app_smoke.py tests/e2e/test_app_smoke.py.bak; make check; git mv tests/e2e/test_app_smoke.py.bak tests/e2e/test_app_smoke.py
  ```
- **Commit sugerido:** `build(tooling): ativar gate de cobertura no make check [1.1/task-05]`

---

### Task 06 — import-linter: dependência, contratos e gates

- **Arquivos a criar:**
  - `.importlinter`
- **Arquivos a modificar:**
  - `pyproject.toml` (dep dev `import-linter`)
  - `uv.lock` (regenerado no mesmo commit — CONVENTIONS §5)
  - `Makefile` (alvo `import-check`: `uv run lint-imports`; entra no
    `check` junto de `layout-check`)
  - `.pre-commit-config.yaml` (hook local `lint-imports`,
    `language: system`, `pass_filenames: false`, **`entry: uv run
    lint-imports`** — com `language: system` o pre-commit executa no PATH
    do shell, sem venv; `lint-imports` puro não seria encontrado)
- **O que fazer:**
  Contratos espelhando LAYOUT §3 **no que é expressável hoje** (concept §4):
  - `layers` em `restaurant_hub.shared`: `infrastructure` → `application`
    → `domain`.
  - `forbidden`: `shared.domain` não importa `shared.application`,
    `shared.infrastructure`, `features`, `fastapi`, `sqlalchemy`,
    `pydantic`, `pydantic_settings`.
  - `forbidden`: `shared.application` não importa `shared.infrastructure`,
    `features`, `fastapi`, `sqlalchemy`, `pydantic`, `pydantic_settings`
    (allow-list do LAYOUT §3: application só importa domain e ports).
  - `forbidden`: `restaurant_hub.shared` não importa
    `restaurant_hub.features`.
  - Comentários no arquivo com as **condições de ativação** dos contratos
    futuros: `independence` entre BCs (quando o 2º BC existir), layers
    por feature (quando a 1ª feature existir), e a exceção declarada do
    `composition_root` (LAYOUT §6) com `ignore_imports` se o grafo real
    exigir.
- **Detalhes técnicos:**
  - `include_external_packages = True` para os contratos forbidden de
    frameworks.
  - Se `lint-imports` tropeçar em pacote `ports/in/` futuro (keyword
    Python), registrar em §7 e anotar no contrato — hoje não existe `in/`
    no grafo.
- **Critério de aceite:**
  - `uv run lint-imports` verde; violação sintética (import de
    `shared.infrastructure` dentro de `shared/domain/`) é detectada
    (aplicar → observar falha → reverter); `make check` verde;
    `uv run pre-commit run lint-imports --all-files` verde.
- **Comando de verificação:**
  ```powershell
  uv run lint-imports
  make check
  uv run pre-commit run lint-imports --all-files
  ```
- **Commit sugerido:** `build(tooling): adicionar import-linter com contratos do LAYOUT [1.1/task-06]`

---

### Task 07 — Corrigir README, runbook validate-ci-gate e LAYOUT (árvore de testes)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `README.md`
  - `docs/runbooks/validate-ci-gate.md`
  - `docs/LAYOUT.md`
- **O que fazer:**
  - README: caminho "Host nativo (Windows)" de primeira classe — setup de
    máquina (PATH do make com a ressalva append/`Get-Command git`,
    `UV_SYSTEM_CERTS` no env do usuário), `make setup`, regeneração do
    `tree.txt` (`uv run python scripts/regen_tree.py`); devcontainer/WSL
    permanecem como opções; remover a exigência "ambiente POSIX".
  - Runbook: atualizar Prerequisites (remover "POSIX shell only");
    §Purpose com a cadeia real do `check` (inclui `lock-check`,
    `import-check`, `test-gate` e os 3 scripts do `docs-check`);
    adicionar classes novas conforme §Maintenance do próprio runbook:
    lock drift (`uv lock --check` falha com dep mudada sem regenerar o
    lock) e import-linter (violação sintética de camada); atualizar a
    Classe 7 (coverage agora dispara dentro do `make check`).
  - LAYOUT §2: documentar a árvore de testes do kernel compartilhado e do
    bootstrap criada nas Tasks 03–04 — `tests/unit/shared/` (espelha
    `src/restaurant_hub/shared/`), `tests/unit/test_bootstrap.py` e
    `tests/e2e/test_app_smoke.py` (smoke da app factory, sem feature) —
    para os caminhos criados pela Stage baterem com a fonte da verdade.
- **Critério de aceite:**
  - Verificação mecânica: `Select-String -Pattern 'POSIX-only|POSIX \('`
    em README + runbook retorna vazio (as strings prescritivas atuais
    somem); as classes novas do runbook têm patch/comando/fingerprint/
    revert; LAYOUT §2 contém `tests/unit/shared/`; `make check` verde.
- **Comando de verificação:**
  ```powershell
  make check
  Select-String -Path README.md, docs/runbooks/validate-ci-gate.md -Pattern 'POSIX-only|POSIX \('   # vazio
  Select-String -Path docs/LAYOUT.md -Pattern 'tests/unit/shared'                                   # presente
  ```
- **Commit sugerido:** `docs(tooling): corrigir README, runbook e LAYOUT para o ambiente real [1.1/task-07]`

---

### Task 08 — Gerar tree.txt e corrigir bloco da Stage 1.1 no roadmap

- **Arquivos a criar:** nenhum (tree.txt é gerado, gitignorado)
- **Arquivos a modificar:**
  - `docs/roadmap.md`
- **O que fazer:**
  - Rodar `uv run python scripts/regen_tree.py` e conferir que `tree.txt`
    existe e reflete o repo.
  - Corrigir o bloco da Stage 1.1 no roadmap: remover
    `features/orders/` de `arquivos_a_modificar` (letra morta),
    `complexidade_estimada: S → M`, `arquivos_a_criar`/
    `arquivos_a_modificar` refletindo o escopo real executado (Makefile,
    uv.lock, .importlinter, settings, testes, docs). **Não** mudar
    `status` aqui (o flip para `done` é do commit `stage 1.1: complete`).
- **Critério de aceite:**
  - `Test-Path tree.txt` = True; bloco 1.1 sem `features/orders/`;
    `make check` verde (docs-check inclusive).
- **Comando de verificação:**
  ```powershell
  uv run python scripts/regen_tree.py
  Test-Path tree.txt
  Select-String -Path docs/roadmap.md -Pattern 'features/orders'   # vazio
  make check
  ```
- **Commit sugerido:** `docs(roadmap): corrigir bloco da stage 1.1 para o escopo real [1.1/task-08]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 1.1: complete` e ser mergeada em `develop`.

### Verificações automatizadas

```powershell
make check                 # lint + typecheck + layout + import-linter + lock-check + docs-check + testes com cov >= 90
make test                  # suite completa sem cov (loop rápido)
uv run pre-commit run --all-files
python scripts/check_technical_postexec.py "docs/stages/1.1-bootstrap/technical.md"
```

### Verificações funcionais

- [ ] `make setup && make check && make test` verdes em **PowerShell
      comum** (fora do Claude Code) — DoD do roadmap + concept §8.
- [ ] Hook `commit-msg` validado: commits de Task passaram pelo hook, e
      um subject inválido é rejeitado (teste manual, sem commitar).
- [ ] `Get-Command git` → Git for Windows (o git do MSYS2 não ganhou).
- [ ] `tree.txt` presente e atual.
- [ ] Cobertura ≥ 90% **por arquivo tocado de `src/`** (term-missing).

### Checklist de fechamento da Stage

- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage 1.1: complete` aplicado
- [ ] PR aberto contra `develop` (merge é do usuário)
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at` e
      `last_reviewed_at` de hoje
- [ ] ADRs 1.1.0001 e 1.1.0002 em `status: accepted`
- [ ] Runbook `validate-ci-gate.md` estendido (novas classes de gate)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

Ordem listada = ordem de execução. Não-óbvios:

```
Task 01 ─► Task 02 ─► Task 03 ─► Task 04 ─► Task 05 ─► Task 06 ─► Task 07 ─► Task 08
   │                     └────────────┴─── suite verde é pré-requisito do flip (05)
   └── uv.lock precisa existir antes de lock-check entrar no check
```

- Task 05 (flip do `--cov`) **não pode** vir antes de 03+04 — quebraria o
  invariante "todo commit deixa `make check` verde".
- Task 06 regenera `uv.lock` no mesmo commit da dep nova (CONVENTIONS §5).
- Task 07 documenta gates que só existem após 05/06.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Cobertura < 90% mesmo após Tasks 03–04 (branch inatingível em módulo do scaffold) | Exercitar via teste sintético; se genuinamente inatingível, `# pragma: no cover` pontual com justificativa em §7 (`[deviation]`) — nunca `omit` de módulo inteiro |
| `uv lock --check` mudar de semântica entre versões do uv | Fallback equivalente: `uv sync --locked` como passo do gate; registrar em §7 |
| import-linter conflita com o grafo real (cadeia app → composition_root) | `ignore_imports` pontual com comentário citando LAYOUT §6 (exceção declarada); registrar em §7 |
| Hook `lint-imports` lento no pre-commit | Manter no pre-commit (repo pequeno); se > 5s, mover para estágio `pre-push` com registro em §7 |
| `@echo` com texto especial quebra no cmd.exe | Texto de help em ASCII simples sem parênteses/aspas; validar `make help` no PowerShell |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../roadmap.md`](../../roadmap.md) — bloco 1.1
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4/§5 — commits, lock
- ADRs: [`../../adr/1_1_0001-windows-native-dev-environment.md`](../../adr/1_1_0001-windows-native-dev-environment.md),
  [`../../adr/1_1_0002-observational-pr-gates.md`](../../adr/1_1_0002-observational-pr-gates.md)
- Skills aplicáveis: `hex-arch-python`, `import-linter-rules`
- [import-linter — docs](https://import-linter.readthedocs.io/)
- [uv — lock e sync](https://docs.astral.sh/uv/concepts/projects/sync/)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.

### 2026-07-14 — [decision] Fase 4 (modo de gate) — Marcelo + Claude
**Contexto:** o roadmap declara `gate_mode: strict` (revisão humana de
diff antes de cada commit) para a 1.1.
**Pergunta:** conduzir a execução com pausa por Task, autônoma com
Checkpoint C, ou pausa só nas Tasks de risco?
**Opções:**
- A — Strict literal (8 pausas)
- B — Autônomo + Checkpoint C a cada 2–3 Tasks + auditoria de testes ✅ recomendada
- C — Pausa só nas Tasks de risco (01, 05, 06)
**Decisão:** B (respondida via `AskUserQuestion`, 2026-07-14).
**Razão:** decisões materiais já validadas pelo usuário nas perguntas da
Fase 3A; escopo é tooling; a revisão humana acontece no PR, e o olhar
externo por bloco fica com o Checkpoint C.

### 2026-07-14 — [deviation] Task 01 (scripts/clean.py) — Claude
**Contexto:** a receita antiga do `clean` (`find .`) varria o repositório
inteiro, incluindo `.venv/` e `.git/`; o novo `scripts/clean.py` pula
esses dois diretórios (`SKIP_DIRS`).
**Razão:** remover `__pycache__` de dentro do `.venv` é inócuo (o venv é
recriável e os caches são regenerados) e a varredura completa é lenta; o
comportamento visível de `make clean` para artefatos do projeto é o
mesmo. Abaixo do threshold de pergunta por ser escolha local
trivialmente reversível; registrado após achado do Checkpoint C (bloco
01–03).

### 2026-07-14 — [finding] Drift de versão entre hooks pre-commit e deps do projeto — Claude
**Contexto:** o hook `ruff` do pre-commit está pinado em `v0.6.9`
enquanto o projeto resolve `ruff>=0.6` para a versão mais recente. Na
execução, o hook aprovou commits que o `make lint` rejeitou (regras
`PLC0415`/`ANN101` divergem entre versões) — dois commits precisaram de
fix (`a6dcd35`). O mesmo risco existe para o hook `mirrors-mypy`.
**Direção sugerida:** alinhar o rev do hook à versão real da dep (ou
trocar por hook local `uv run ruff`, como o `lint-imports`).
**Stage/issue candidata:** issue avulsa de tooling pós-Stage (criação da
issue via `gh` ficou pendente de aprovação do usuário nesta sessão —
corpo proposto no relatório final da Stage).

### 2026-07-14 — [finding] Falta .gitattributes (normalização de EOL) — Claude
**Contexto:** todo commit emite "LF will be replaced by CRLF"
(`core.autocrlf=true`, sem `.gitattributes`); combinado com o `git.exe`
do MSYS2 no PATH, já produziu churn fantasma de ~2900 linhas em teste
anterior (ADR 1.1.0001). Fora do escopo da 1.1 por decisão do concept
(§1 Fora do escopo).
**Direção sugerida:** `.gitattributes` com política explícita de EOL +
renormalização em PR dedicado.
**Stage/issue candidata:** issue avulsa de repo pós-Stage (criação
pendente de aprovação do usuário — corpo proposto no relatório final).

<!-- END: post-execution -->

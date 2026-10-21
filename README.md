# Restaurant Hub

> SaaS modular de gestão de restaurantes — escala, estoque, pedidos e hub de análise

---

## Documentação

| Documento | Descrição |
|-----------|-----------|
| [docs/LAYOUT.md](docs/LAYOUT.md) | Convenções de arquitetura — leia antes de codar |
| [docs/GIT-WORKFLOW.md](docs/GIT-WORKFLOW.md) | Fluxo de versionamento e CI/CD |
| [docs/PIPELINE.md](docs/PIPELINE.md) | Pipeline conceitual (Step → Stage → Task, fases, gates) |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Convenções de frontmatter, branches, commits, versionamento |
| [CLAUDE.md](CLAUDE.md) | Contexto para agentes de IA |
| [docs/](docs/) | Documentação técnica (LAYOUT, GIT-WORKFLOW, PIPELINE, CONVENTIONS, runbook de Stage, ADRs) |

---

## Setup local

Caminho padrão deste projeto: **host nativo no Windows** (PowerShell, sem
Docker) — decisão registrada no [ADR 1.1.0001](docs/adr/1_1_0001-windows-native-dev-environment.md).
Devcontainer e Docker Compose seguem suportados como opções.

### Caminho A — Host nativo (padrão; Windows, Linux ou macOS)

Pré-requisitos: Python 3.12+, [uv](https://docs.astral.sh/uv/) e GNU Make 4+.

**Setup de máquina no Windows (uma vez):**

1. **`make` no PATH do usuário.** Qualquer GNU Make 4+ serve (ezwinports via
   `winget install ezwinports.make`, ou o do MSYS2). Se usar o do MSYS2,
   adicione `C:\msys64\usr\bin` ao PATH do usuário **no final (append,
   nunca prepend)** — esse diretório carrega um `git.exe` próprio que NÃO
   pode ganhar do Git for Windows (ADR 1.1.0001; antes do `.gitattributes`
   da issue #8, a troca causava churn fantasma de CRLF no `git diff`).
   Depois confira:
   ```powershell
   make --version      # GNU Make 4.x
   Get-Command git     # deve resolver para C:\Program Files\Git\cmd\git.exe
   ```
2. **`UV_SYSTEM_CERTS=1` no ambiente do usuário** (sem isso o `uv` falha
   TLS ao alcançar o PyPI nesta configuração de máquina):
   ```powershell
   [Environment]::SetEnvironmentVariable("UV_SYSTEM_CERTS", "1", "User")
   ```
   Sessões do Claude Code já herdam a variável de `.claude/settings.json`
   (versionado).

**Setup do projeto:**

```powershell
git clone <repo-url>
cd restaurant-hub

make setup                            # uv sync (gera/usa uv.lock) + hooks pre-commit e commit-msg
Copy-Item .env.example .env           # ajuste credenciais locais
uv run python scripts/regen_tree.py   # gera tree.txt (contexto para agentes; gitignorado)
make check                            # gate completo — deve fechar verde
```

As receitas do Makefile são shell-agnostic (funcionam sob `sh` ou
`cmd.exe`) — não há dependência de ambiente POSIX.

### Caminho B — Devcontainer (VS Code dentro do container)

Pré-requisitos: [Docker](https://docs.docker.com/get-docker/) +
[Docker Compose v2.24+](https://docs.docker.com/compose/install/) +
extensão **Dev Containers** do VS Code.

1. Abra a pasta do projeto no VS Code.
2. `Ctrl+Shift+P` → `Dev Containers: Reopen in Container`.
3. VS Code sobe o `docker-compose.yml`, abre o IDE dentro da stage `builder` do Dockerfile (com `uv`, `ruff`, `mypy`, `pytest` já instalados) e roda `make setup` automaticamente via `postCreateCommand`.
4. Use o terminal integrado para os comandos abaixo (`make check`, `make run`, etc.).

### Caminho C — Docker Compose direto (sem devcontainer)

```bash
make docker-build            # builda a stage `builder` com toolchain de dev
make docker-up               # sobe `app` (e `postgres` se o init-project habilitou)
make docker-shell            # bash dentro do container, para rodar `make check`, `make test`
make docker-down             # derruba a stack
```

---

## Comandos principais

| Comando | O que faz |
|---------|-----------|
| `make setup` | `uv sync --extra dev` (gera/usa `uv.lock`) + instala hooks `pre-commit` e `commit-msg` |
| `make install` | Reinstala dependências (após mudança no `pyproject.toml`) |
| `make run` | Sobe o servidor de desenvolvimento com hot-reload |
| `make migrate` | Aplica migrations pendentes (`alembic upgrade head`) |
| `make check` | Gate completo: lint + typecheck + layout + import-linter + lock + docs + testes com cobertura ≥ 90% |
| `make lint` | Roda `ruff check` — apenas reporta |
| `make fmt` | Roda `ruff format` + `ruff check --fix` |
| `make typecheck` | Roda `mypy` |
| `make layout-check` | Valida regras de dependência (`scripts/check_layout.py`) |
| `make import-check` | Valida contratos de import (`.importlinter` espelha `docs/LAYOUT.md` §3) |
| `make lock-check` | Falha se `uv.lock` divergiu do `pyproject.toml` |
| `make docs-check` | Valida docs de Stage, issues e ADRs |
| `make test` | Roda todos os testes (sem cobertura — loop rápido) |
| `make test-gate` | Suite com gate de cobertura ≥ 90% (usado pelo `check`) |
| `make test-cov` | Testes com relatório de cobertura em HTML |
| `make clean` | Remove artefatos de build, cache e arquivos gerados (`scripts/clean.py`) |
| `make docker-build` | Builda a stage `builder` (devcontainer/CI) — tag `:dev` |
| `make docker-build-prod` | Builda a stage `runtime` (deploy) — tag `:prod` |
| `make docker-up` | Sobe a stack do `docker-compose.yml` em background |
| `make docker-down` | Derruba a stack do `docker-compose.yml` |
| `make docker-run` | Sobe a app em foreground (logs no terminal) |
| `make docker-shell` | Abre bash dentro do container `app` |

---

## Estrutura do código

```
src/restaurant_hub/
├── main.py                  # Entrypoint: inicia uvicorn
├── composition_root.py      # Único lugar que instancia dependências concretas
├── features/                # Vertical slices — um diretório por bounded context (vazio no template)
│   └── <feature>/           # Cada feature do seu projeto (ex.: payments, inventory)
│       ├── domain/          # Entidades, value objects, serviços de domínio, exceções
│       │   ├── entities/
│       │   ├── value_objects/
│       │   ├── services/
│       │   └── exceptions/
│       ├── application/     # Use cases, DTOs, ports (interfaces)
│       │   ├── use_cases/
│       │   ├── dtos/
│       │   └── ports/
│       │       ├── in/      # Ports primários (driving) — atenção: 'in' é keyword Python
│       │       └── out/     # Ports secundários (driven)
│       └── adapters/        # Implementações concretas dos ports
│           ├── in/
│           │   └── http/    # Router FastAPI
│           └── out/
│               └── postgres/ # Repositório SQLAlchemy
└── shared/                  # Preocupações transversais reutilizáveis
    ├── domain/              # Exceções base, value objects genéricos
    ├── application/         # Ports compartilhados (Clock, IdGenerator)
    └── infrastructure/      # Implementações de infraestrutura (DB, HTTP, config, logging)
```

---

## Convenções

- **Arquitetura:** Vertical slices + Ports & Adapters. Veja [docs/LAYOUT.md](docs/LAYOUT.md).
- **Branches:** `feat/<num-issue>-<N-M>-<slug>`, `fix/<num-issue>-<N-M>-<slug>`, `docs/<desc>` — `N.M` é o id da Stage (ver `docs/GIT-WORKFLOW.md` e `docs/CONVENTIONS.md` §4)
- **Commits:** Conventional Commits — `feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- **Testes:** Cada camada tem sua suite — `unit/`, `integration/`, `contract/`, `e2e/`
- **Imports:** Sempre absolutos. Nunca importe de `infrastructure` dentro de `domain`.

---

## CI

O CI (`.github/workflows/ci.yml`) tem dois jobs: `lint-and-test` instala com
`uv sync --extra dev` e roda **exatamente** `make check` — o mesmo gate
local: lint, typecheck, layout-check, import-check, lock-check, docs-check e
testes com cobertura ≥ 90% (`fail_under` no `pyproject.toml`) — e
`guard-main-source` bloqueia PRs para `main` que não venham de
`develop`/`hotfix/*` (ver [ADR 1.1.0002](docs/adr/1_1_0002-observational-pr-gates.md)).

Para rodar localmente o mesmo check do CI:

```bash
make check
```

Para provar classe a classe que cada erro é rejeitado pelo gate, ver
[docs/runbooks/validate-ci-gate.md](docs/runbooks/validate-ci-gate.md).

# =============================================================================
# Makefile — Restaurant Hub
# =============================================================================
# Uso: make <target>
# Requer: uv instalado (https://docs.astral.sh/uv/)
#
# Receitas shell-agnostic (ADR 1.1.0001): cada receita é um comando único
# portável, que funciona tanto sob sh quanto sob cmd.exe (Windows nativo).
# Sem condicionais/varreduras/remoções de shell POSIX inline — lógica
# condicional vive em scripts Python (ex.: scripts/clean.py).

.DEFAULT_GOAL := help
.PHONY: help setup install run migrate check lint fmt typecheck layout-check import-check lock-check docs-check test test-fast test-cov test-gate clean worktree docker-build docker-build-prod docker-up docker-down docker-run docker-shell

# Tag das imagens Docker. Mesmo nome usado em docker-compose.yml `image:` para
# reusar o cache de layer (`make docker-build` e `make docker-up` produzem a
# mesma imagem).
DOCKER_IMAGE := restaurant_hub-app

# ---------------------------------------------------------------------------
# help — lista todos os targets disponíveis
# ---------------------------------------------------------------------------
help:
	@echo Restaurant Hub - comandos disponiveis
	@echo   make setup            Cria .venv via uv sync, gera uv.lock e instala hooks
	@echo   make install          Reinstala dependencias apos mudar pyproject.toml
	@echo   make run              Sobe o servidor de desenvolvimento com hot-reload
	@echo   make migrate          Aplica migrations pendentes - alembic upgrade head
	@echo   make check            Gate completo - lint + types + layout + lock + docs + testes com cobertura
	@echo   make test-gate        Suite com gate de cobertura 90 - usado pelo check
	@echo   make lint             Roda ruff check - apenas reporta
	@echo   make fmt              Formata o codigo com ruff format + ruff check --fix
	@echo   make typecheck        Roda mypy strict
	@echo   make layout-check     Valida regras de dependencia - scripts/check_layout.py
	@echo   make import-check     Valida contratos de import - import-linter
	@echo   make lock-check       Confere que uv.lock esta sincronizado com pyproject.toml
	@echo   make docs-check       Valida docs de stage, issues, ADRs e harness
	@echo   make test             Roda todos os testes
	@echo   make test-fast        Roda testes pulando os marcados como slow
	@echo   make test-cov         Testes com relatorio de cobertura HTML + gate 90
	@echo   make clean            Remove artefatos de build, cache e arquivos gerados
	@echo   make worktree BRANCH=tipo/num-slug   Cria worktree paralela pronta para uso
	@echo   make docker-build     Builda a stage builder - tag dev
	@echo   make docker-build-prod  Builda a stage runtime - tag prod
	@echo   make docker-up        Sobe a stack em background
	@echo   make docker-down      Derruba a stack do docker-compose
	@echo   make docker-run       Sobe a app em foreground - logs no terminal
	@echo   make docker-shell     Abre bash dentro do container app

# ---------------------------------------------------------------------------
# setup — primeira vez: cria o ambiente, gera o lock e instala hooks
# ---------------------------------------------------------------------------
setup:
	uv sync --extra dev
	uv run pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg
	@echo Ambiente pronto. Hooks pre-commit e commit-msg instalados.
	@echo Copie e ajuste as variaveis de ambiente: .env.example para .env

# ---------------------------------------------------------------------------
# install — atualiza dependências sem recriar o venv
# ---------------------------------------------------------------------------
install:
	uv sync --extra dev

# ---------------------------------------------------------------------------
# run — servidor de desenvolvimento
# ---------------------------------------------------------------------------
run:
	uv run uvicorn restaurant_hub.main:app --reload --host 0.0.0.0 --port 8000

# ---------------------------------------------------------------------------
# migrate — aplica todas as migrations pendentes
#
# O `-c` é obrigatório: o alembic.ini deste projeto vive em migrations/, e o
# alembic só procura por `alembic.ini` no diretório corrente. Sem a flag o alvo
# falha com "No 'script_location' key found in configuration" (Stage 2.3).
# ---------------------------------------------------------------------------
migrate:
	uv run alembic -c migrations/alembic.ini upgrade head

# ---------------------------------------------------------------------------
# check — gate completo, bloqueante no CI (lint + types + layout + lock + docs
# + testes com gate de cobertura >= 90, via fail_under do pyproject.toml)
# ---------------------------------------------------------------------------
check: lint typecheck layout-check import-check lock-check docs-check test-gate

# ---------------------------------------------------------------------------
# lint — verifica estilo e regras sem modificar arquivos
# ---------------------------------------------------------------------------
lint:
	uv run ruff check src/ tests/ scripts/ .claude/hooks/

# ---------------------------------------------------------------------------
# fmt — formata e corrige automaticamente o que for possível
# ---------------------------------------------------------------------------
fmt:
	uv run ruff format src/ tests/ scripts/ .claude/hooks/
	uv run ruff check --fix src/ tests/ scripts/ .claude/hooks/

# ---------------------------------------------------------------------------
# typecheck — checagem estática de tipos
#
# Inclui tests/fakes/ (desde a Stage 2.2): os fakes implementam os ports por
# tipagem estrutural, e cada módulo declara `_conforms: <Port> = <Fake>()`. Sem
# checar essa pasta, a conformidade fake↔Protocol não teria gate nenhum — o
# pyproject fixa `files = ["src"]`, então uma anotação dentro de um teste some
# em runtime e nunca é verificada. Como os fakes são a especificação que os
# adapters reais (2.3/2.4) reimplementam, a divergência seria herdada em silêncio.
# ---------------------------------------------------------------------------
typecheck:
	uv run mypy src/ tests/fakes/

# ---------------------------------------------------------------------------
# layout-check — valida as regras de arquitetura que NÃO são arestas de import
# (docs/LAYOUT.md §3, §6, §7 + issue #45).
#
# São dois scripts porque são duas perguntas. `check_layout.py` classifica cada
# arquivo de src/ numa regra e a aplica; `check_dead_shared.py` procura o
# oposto — o símbolo de `shared/` que NENHUM arquivo alcança. Código morto é a
# única violação de arquitetura que se caracteriza pela **ausência** de import,
# então nem o import-linter nem a varredura por camada podem enxergá-la.
# ---------------------------------------------------------------------------
layout-check:
	uv run python scripts/check_layout.py
	uv run python scripts/check_dead_shared.py

# ---------------------------------------------------------------------------
# import-check — valida contratos de import (.importlinter espelha LAYOUT §3)
# ---------------------------------------------------------------------------
import-check:
	uv run lint-imports

# ---------------------------------------------------------------------------
# lock-check — falha se o uv.lock divergiu do pyproject.toml (CONVENTIONS §5)
# ---------------------------------------------------------------------------
lock-check:
	uv lock --check

# ---------------------------------------------------------------------------
# docs-check — valida (1) que technical.md `done` só mudou dentro da §7
# post-execution desde o gate da Fase 3B (CONVENTIONS §3.4), (2) que toda
# Stage tem issue correspondente no backlog do GitHub (best-effort — pula
# se `gh` não está autenticado), (3) o bounded_context dos ADRs, (4) que a
# árvore de pastas do LAYOUT §2 descreve o repositório que existe, (5) o
# frontmatter de skills/subagentes em `.claude/` — o Claude Code não reporta
# YAML inválido nem descrição truncada (issue #56) —, (6) que toda pasta de
# Stage tem as dependências fechadas: `done` no roadmap e `stage N.M: complete`
# no histórico, com o número derivado do stage_id (issue #12, ADR 0.0.0009) — e
# (7) que doc cita o roadmap por âncora (`§Stage N.M › "Rótulo"`), nunca por
# número de linha, e que toda âncora resolve (issue #79, ADR 0.0.0011).
#
# O (4) é o único que compara documento com sistema de arquivos, e é por isso
# que ele existe: a §2 não ilustra, ela **instrui** — `CLAUDE.md` manda
# consultá-la antes de criar qualquer arquivo. Uma linha falsa ali é uma
# instrução errada que nenhum compilador corrige (issue #45, Gate 5).
# ---------------------------------------------------------------------------
docs-check:
	uv run python scripts/check_technical_postexec.py
	uv run python scripts/check_stage_issue.py
	uv run python scripts/check_adr_bounded_context.py
	uv run python scripts/check_docs_claims.py
	uv run python scripts/check_harness.py
	uv run python scripts/check_stage_deps.py
	uv run python scripts/check_roadmap_citations.py

# ---------------------------------------------------------------------------
# test — roda toda a suite de testes (sem cobertura — loop rápido local)
# ---------------------------------------------------------------------------
test:
	uv run pytest tests/ -v

# ---------------------------------------------------------------------------
# test-gate — suite com cobertura; falha se < 90% (fail_under do pyproject)
# ---------------------------------------------------------------------------
test-gate:
	uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing

# ---------------------------------------------------------------------------
# test-fast — pula testes marcados como slow (CI rápido / loop local)
# ---------------------------------------------------------------------------
test-fast:
	uv run pytest tests/ -v -m "not slow"

# ---------------------------------------------------------------------------
# test-cov — testes com relatório de cobertura em HTML (gate ≥ 90% via pyproject)
# ---------------------------------------------------------------------------
test-cov:
	uv run pytest tests/ --cov=src/restaurant_hub --cov-report=html --cov-report=term-missing
	@echo Relatorio gerado em: htmlcov/index.html

# ---------------------------------------------------------------------------
# worktree — cria worktree git pronta pra implementação (issue → branch →
# venv → VS Code). Uso:
#     make worktree BRANCH=feat/42-add-google-login
#     make worktree BRANCH=fix/57-timeout BASE=develop
#     make worktree BRANCH=feat/42-add-google-login ARGS='--no-setup --no-vscode'
# Detalhes e flags: `python scripts/worktree-new.py --help`.
# ---------------------------------------------------------------------------
worktree:
ifndef BRANCH
	$(error Uso: make worktree BRANCH=tipo/num-slug [BASE=develop ou main] [ARGS='...'])
endif
	uv run python scripts/worktree-new.py $(BRANCH) $(if $(BASE),--base $(BASE),) $(ARGS)

# ---------------------------------------------------------------------------
# docker-build — builda a stage 'builder' (devcontainer e CI)
# ---------------------------------------------------------------------------
docker-build:
	docker build --target builder -t $(DOCKER_IMAGE):dev .

# ---------------------------------------------------------------------------
# docker-build-prod — builda a stage 'runtime' (deploy)
# ---------------------------------------------------------------------------
docker-build-prod:
	docker build --target runtime -t $(DOCKER_IMAGE):prod .

# ---------------------------------------------------------------------------
# docker-up — sobe a stack inteira em background
# ---------------------------------------------------------------------------
docker-up:
	docker compose up -d

# ---------------------------------------------------------------------------
# docker-down — derruba a stack
# ---------------------------------------------------------------------------
docker-down:
	docker compose down

# ---------------------------------------------------------------------------
# docker-run — roda a app em foreground (com logs no terminal)
# ---------------------------------------------------------------------------
docker-run:
	docker compose up app

# ---------------------------------------------------------------------------
# docker-shell — abre bash dentro do container app
# ---------------------------------------------------------------------------
docker-shell:
	docker compose exec app bash

# ---------------------------------------------------------------------------
# clean — remove artefatos gerados (lógica em scripts/clean.py)
# ---------------------------------------------------------------------------
clean:
	uv run python scripts/clean.py

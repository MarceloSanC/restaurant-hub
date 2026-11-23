# syntax=docker/dockerfile:1.7

# Multi-stage Dockerfile do template whaka-dev-project-template.
#
# Stages:
#   - `builder` (default em dev): contem build tools + dev deps (ruff, mypy,
#     pytest) + tooling de devcontainer (git, make, curl). Usado pelo
#     .devcontainer/devcontainer.json e pelo CI.
#   - `runtime` (deploy): imagem slim sem build tools nem dev deps. Apenas
#     libpq5 (cliente postgres) + venv com deps de producao.
#
# As duas stages instalam EXATAMENTE as versoes do `uv.lock` (issue #244):
# `uv sync --locked` falha o build se o lock estiver fora de sincronia com o
# `pyproject.toml` — a mesma checagem do gate `lock-check` (`uv lock --check`).
# Nao trocar por `uv pip install` do pyproject: ele resolve as faixas no
# momento do build e a imagem sai com versoes que o CI nao testou.
# `tests/unit/test_dockerfile.py` trava essa forma.
#
# Build manual:
#   docker build --target builder -t <projeto>:dev .   # devcontainer/CI
#   docker build --target runtime -t <projeto>:prod .  # deploy
#
# Por padrao o docker-compose.yml usa `target: builder` (dev). Em deploy real
# substitua para `runtime` ou faca o build direto da stage.

# =============================================================================
# Base comum: python slim + libpq5 + uv
# =============================================================================
FROM python:3.12-slim AS base

# UV_PYTHON_DOWNLOADS=0: o venv usa o Python da imagem base; se ele nao
# satisfizer o `requires-python`, o build falha em vez de baixar outro.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:${PATH}"

# libpq5 (cliente postgres compilado) — precisa em runtime tambem para
# psycopg/asyncpg falarem com Postgres.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# uv: gerenciador de pacotes oficial deste template (ver CLAUDE.md). Versao
# fixada, como recomenda a doc do uv ("Using uv in Docker"): o `--locked`
# depende de como o uv le o lock, e `latest` muda isso sem commit.
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /uvx /usr/local/bin/

WORKDIR /app

# =============================================================================
# Stage builder — devcontainer e CI
# =============================================================================
FROM base AS builder

# Build deps (compiladores para wheels nativas) + tooling de devcontainer.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        git \
        make \
    && rm -rf /var/lib/apt/lists/*

# Cache de deps em duas camadas (doc do uv, "Intermediate layers"): primeiro
# so as dependencias, a partir de pyproject + lock; depois o projeto, com o
# src. Quando so o codigo muda, a camada das dependencias e reusada. O cache
# do uv fica num cache mount do BuildKit, fora da imagem.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra dev --no-install-project
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --extra dev

# Resto do codigo. No devcontainer, docker-compose substitui /app via bind
# mount do host, entao o COPY aqui so importa para CI ou execucoes isoladas.
COPY . .

EXPOSE 8000
CMD ["uvicorn", "restaurant_hub.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# Stage runtime — deploy (sem dev deps, sem build tools)
# =============================================================================
FROM base AS runtime

# Usuario nao-root para reduzir blast radius em caso de invasao do container.
RUN groupadd --system app && \
    useradd --system --gid app --no-create-home --shell /bin/bash app

# Install prod-only em venv proprio do runtime: sem a extra `dev` e com
# `--no-dev` (grupos de dependencia), para que ruff/mypy/pytest nao vazem
# para producao. Nao reusa o venv do builder. `--no-editable`: o pacote vai
# instalado no venv, sem apontar para /app/src.
COPY --chown=app:app pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --no-install-project
COPY --chown=app:app src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

USER app

EXPOSE 8000
CMD ["uvicorn", "restaurant_hub.main:app", "--host", "0.0.0.0", "--port", "8000"]

---
title: Runbook — Setup do repositório no GitHub (1x por projeto)
description: Procedimento único de configuração do repositório — branches base, branch protection, environments, workflows de CI/CD e templates de issue/PR
when-use: Uma vez ao criar o repositório do projeto destino, ou ao revisar/auditar proteção de branches e environments; não é consulta de fluxo diário
keywords: [runbook, setup, github, branch-protection, environments, ci-cd, templates]
runbook_id: github-repo-setup
triggers:
  - Repositório novo criado a partir do template
  - Revisão/auditoria das regras de proteção de branch ou environments
estimated_duration: 30min
---

# Runbook — Setup do repositório no GitHub (1x por projeto)

> Runbook em **português** (mesma exceção do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../RUNBOOK-STAGE-LIFECYCLE.md)).
> Extraído do `GIT-WORKFLOW.md` §Setup inicial: o fluxo operacional
> diário continua lá; aqui fica só o que se configura **uma vez por
> projeto**. Os **Gates de PR** (fonte única) permanecem em
> [`GIT-WORKFLOW.md`](../GIT-WORKFLOW.md#gates-de-pr-fonte-única).

## Branches base

```bash
git branch -M main                    # renomear master pra main (se necessário)
git push -u origin main
git checkout -b develop
git push -u origin develop
```

Configurar `develop` como branch padrão no GitHub (Settings → Branches → Default branch).

## Branch protection rules (Settings → Branches)

Aplicar **identicamente** em `main` e `develop`:

- ✅ Require a pull request before merging
- ✅ Require approvals: **1**
- ✅ Dismiss stale pull request approvals when new commits are pushed
- ✅ Require status checks to pass before merging
  - `test` (CI)
  - `coverage` (≥ 90%)
- ✅ Require branches to be up to date before merging
- ✅ Require conversation resolution before merging
- ❌ Do not allow bypassing the above settings
- ✅ Restrict who can force push (admin only)
- ✅ Restrict who can delete branches (admin only)

## GitHub Environments (Settings → Environments)

**Environment: `development`**
- Sem required reviewers
- Deploy automático ao fazer merge em `develop`
- Secrets: `DATABASE_URL`, `API_KEY`, etc. (valores de dev)

**Environment: `production`**
- Required reviewers: **todos os membros do time** (aprovação manual)
- Wait timer: 0 (sem delay)
- Secrets: valores de produção (instância de DB diferente, chaves reais)
- Deploy automático ao fazer merge em `main`, após aprovação

## Workflows de CI/CD

Estrutura em `.github/workflows/`:

```
.github/workflows/
├── ci.yml           # Roda em todo PR e push: lint + test + coverage
├── deploy-dev.yml   # Roda em push para develop (automático)
└── deploy-prod.yml  # Roda em push para main (com aprovação)
```

## Issue e PR templates

Criar em `.github/`:

```
ISSUE_TEMPLATE/
├── feature.md       # Features novas
├── bug.md           # Bug reports
└── chore.md         # Manutenção

PULL_REQUEST_TEMPLATE.md
```

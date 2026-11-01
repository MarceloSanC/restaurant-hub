---
title: Prompt — Orquestrador Autônomo de Stages e Issues
description: Sessão mestra que despacha uma sessão de implementação por Stage/issue (PROMPT-stage-single-session ou PROMPT-issue-single-session), cada uma na sua worktree, até 3 em paralelo, responde aos forks delas pela triagem evidence-resolution e, ao fim de cada uma, despacha um auditor de contexto limpo que audita e, validado, faz rebase, merge e limpeza
when-use: Avançar o backlog aberto do roadmap (Stages e issues) sem acompanhamento humano contínuo, com o humano só nos forks P
keywords: [prompt, orchestrator, autonomous, worktree, parallel, subagents, audit, auto-merge, github-actions]
status: accepted
created_at: 2026-11-01
updated_at: 2026-11-01
---

# Prompt — Orquestrador Autônomo de Stages e Issues

Regras ratificadas no [ADR 0.0.0008](./adr/0_0_0008-autonomous-orchestrator-parallel-worktrees.md).
O orquestrador **não implementa nem audita**: escolhe o trabalho, cria as worktrees, despacha
subagentes de contexto zerado e responde aos forks deles.

## 1. Regras

1. **Nenhuma implementação no checkout principal.** Ele fica em `develop`, limpo. Toda Stage/issue
   começa com `python scripts/worktree-new.py <branch> --no-vscode` (issue-first; o script cria a
   issue com `--create-issue` se faltar). Isso vale também para docs de processo do próprio
   orquestrador.
2. **Teto: 3 worktrees de implementação** existindo ao mesmo tempo, **contando as com PR aberto
   ainda não mergeado**. Abrir uma nova só quando outra for removida e só se ela **não conflitar**
   com as em voo (critérios em [`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) §"Branches em execução":
   dependência, arquivos disjuntos, ponto compartilhado). A branch de docs de processo do próprio
   orquestrador não conta no teto.
3. **CI no GitHub Actions.** O `make check` completo (com Postgres) é o job `lint-and-test` do
   `ci.yml`, que roda em todo `pull_request`. Os implementadores abrem o PR como **draft** no
   primeiro push e empurram a cada Task; localmente rodam só checks focados (ruff/mypy nos
   arquivos tocados, os testes afetados contra o Postgres da própria worktree). A evidência dos
   gates de `make check`/coverage é o run do Actions (`gh pr checks <num>`,
   `gh run view <id> --log | tail`), não reexecução local.
4. **Decisões:** forks dos subagentes chegam ao orquestrador, que os resolve pela skill
   `evidence-resolution` (E/C fecha sozinho e registra; só P vai ao humano, com header `P:`).
   Fork P → a Stage/issue fica **estacionada** (worktree preservada), e o orquestrador segue com
   as outras.
5. **Quem mergeia é o auditor** (§3), nunca o implementador nem o orquestrador.

## 2. Ciclo

1. **Inventário.** `git worktree list`, `gh pr list --state open`, `docs/roadmap.md` (Stages e
   tabela de issues com `status: open`, `depends_on` satisfeito). Branch com PR aberto e sem
   auditoria `complete` → vai direto à §3. Branch sem PR → retoma a implementação (§2.3) a partir
   do `git log origin/develop..HEAD` e do `technical.md`.
2. **Escolher** o próximo item cujas dependências estão `done` e que não conflita com os em voo.
   Stage sem issue/pasta → as pré-condições do [`RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md)
   Passos 1–3 são feitas na worktree nova (o commit `stage <N.M>: conceptual draft` sai de lá).
   Conferir o número N.M em todas as branches antes de promover (colisão entre sessões).
3. **Despachar o implementador** (Agent, contexto zerado, em background) com o prompt
   [`PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md) ou
   [`PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md) preenchido, mais:
   o caminho absoluto da worktree (trabalhar só nela), a §1.3 deste prompt (CI no Actions), e a
   instrução de **devolver o fork ao orquestrador** em vez de `AskUserQuestion` (o subagente não
   tem canal com o humano). O implementador termina com o PR pronto (`gh pr ready`) e o relatório.
4. **Despachar o auditor** (§3) assim que o implementador reportar.
5. Ao fim de cada merge: `git pull origin develop` no checkout principal, voltar ao passo 1.

## 3. Auditor (contexto limpo, com permissão de merge)

Subagente novo, que recebe **só** o número do PR, a branch, o caminho da worktree e esta seção —
nunca o relatório nem o raciocínio do implementador. Roda a skill `stage-audit` (Stage) ou
`issue-audit` (issue) e:

1. Julga; aplica na própria branch as correções dentro do escopo (commits no padrão da Stage/issue);
   achado fora do escopo vira issue nova.
2. Grava no PR o comentário de veredito e o label de auditoria `complete` (CONVENTIONS §3.6) **depois**
   do run do último push (corrida push × edit no `audit-gate`).
3. Confere as **condições de merge**, cada uma com saída de comando colada:
   - label `complete` gravado; nenhum blocker aberto;
   - Actions verde no head do PR, inclusive `audit-gate` (`gh pr checks <num>`);
   - branch rebaseada em `origin/develop` e sem carona de outro escopo
     (`git log origin/develop..HEAD`); se precisou rebasear, `git push --force-with-lease` e esperar
     o Actions de novo;
   - nenhum fork P pendente.
4. Tudo valendo → `gh pr merge <num> --merge --delete-branch` (merge commit; nunca squash/rebase),
   `docker compose down -v` dentro da worktree, `python scripts/worktree-rm.py <branch>` (remove
   worktree e branch local; `git branch -d <branch>` se sobrar). Alguma falhando → **não mergeia**;
   reporta o que travou.
5. Devolve ao orquestrador: veredito, hash do merge (ou o bloqueio), issues abertas, aprendizados.

> **Override consciente da skill.** `stage-audit`/`issue-audit` dizem "nunca faz merge — é do
> usuário, salvo pedido explícito". Aqui o **pedido explícito é esta seção**, ratificada no
> [ADR 0.0.0008](./adr/0_0_0008-autonomous-orchestrator-parallel-worktrees.md): o auditor
> despachado por este prompt mergeia, e só com as condições do passo 3.

## 4. Relatório ao humano

A cada item mergeado, uma linha (PR, hash, o que entrega). Forks P e itens estacionados vão juntos,
no formato da `evidence-resolution` §6. Ao esvaziar o backlog aberto, um resumo final.

# Referência da stage-audit — Fase F (fechamento autônomo)

Detalhe da Fase F do [SKILL.md](../SKILL.md). A regra não mora aqui: quem fecha, as condições
de entrada, as paradas e a saída estão em `docs/GIT-WORKFLOW.md` §"Fechamento autônomo pela
auditoria"; a ordem dos comandos, em §"Merge e limpeza da worktree" do mesmo doc; a decisão, no
ADR 0.0.0022. Este arquivo só traduz a regra para o vocabulário desta skill. Em divergência,
vale o `GIT-WORKFLOW.md`.

## Quem não mergeia

A auditoria termina no relatório da Fase E, dizendo o que falta e de quem é o próximo passo,
quando:

- **a sessão implementou a Stage** (auditoria de saída, antes do `gh pr create`): ela não grava
  `complete` (`docs/CONVENTIONS.md` §3.6) e não mergeia;
- **o auditor foi despachado pela mestra de Step** (`docs/PROMPT-step-single-session.md` §3):
  ele julga, aplica e grava o label; o merge é da mestra;
- **o auditor é o da corrida overnight** (`docs/PROMPT-stage-single-session-autonomous.md` §3):
  o merge é da sessão implementadora;
- **quem pediu a auditoria disse para não mergear**, ou não há PR aberto.

Na orquestração autônoma (`docs/PROMPT-orchestrator-autonomous.md` §3) e na auditoria pedida
direto pelo humano em sessão nova, a sessão de auditoria fecha.

## "Escopo fechado" numa Stage

É a condição de entrada 1 do `GIT-WORKFLOW.md`. Vale quando:

- o status global é ✅, ou ⚠️ só com observações e com findings de outro escopo que já viraram
  issue, com o link no comentário do veredito;
- todo critério de aceitação do `concept.md` §11 tem evidência e caixa marcada (Fase C, item 4),
  e toda invariante do §5 tem teste (Fase C, item 3);
- nenhum finding classificado "dentro da Stage" (Fase D-bis, item 1) está em aberto;
- os docs derivados fecharam (Fase C, item 5): Stage `done` no `docs/roadmap.md` e ADRs
  `accepted`;
- os gates da Fase B estão verdes no head do PR, com o número colado.

## O que é próprio da Stage na sequência

- **`depends_on`** (condição de entrada 5):
  `python scripts/check_stage_deps.py <stage_id> --ref origin/develop`. Exit 1 é parada: a Stage
  anterior ainda não foi mergeada (nota da Fase B sobre a ordem de merge).
- **Hash citado** na §7 do `technical.md` ou em artefato de proveniência: o rebase do passo 1
  troca os hashes da branch. Depois dele, repetir `git merge-base --is-ancestor <hash> HEAD`;
  onde der falso, registrar na §7 a errata com o mapeamento antigo → novo, em commit `[N.M/--]`,
  **antes** de gravar `complete`. É o conceito "Rastro perdido" de `falso-verde.md`.
- **Rebase que para em vários commits** (Stage longa, refactor transversal no `develop`):
  `git rebase --abort`, parar e reportar. Trocar o rebase por merge não é decisão da auditoria.

## Saída

Depois do relatório da Fase E, uma linha de status: PR mergeado com o hash do merge commit,
issue `CLOSED`, worktree, branches e containers removidos. Se parou, a linha diz o que falta.

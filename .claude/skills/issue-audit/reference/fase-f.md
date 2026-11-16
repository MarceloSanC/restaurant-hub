# Referência da issue-audit — Fase F (fechamento autônomo)

Detalhe da Fase F do [SKILL.md](../SKILL.md). A regra não mora aqui: quem fecha, as condições
de entrada, as paradas e a saída estão em `docs/GIT-WORKFLOW.md` §"Fechamento autônomo pela
auditoria"; a ordem dos comandos, em §"Merge e limpeza da worktree" do mesmo doc; a decisão, no
ADR 0.0.0022. Este arquivo só traduz a regra para o vocabulário desta skill. Em divergência,
vale o `GIT-WORKFLOW.md`.

## Quem não mergeia

A auditoria termina no relatório da Fase E, dizendo o que falta e de quem é o próximo passo,
quando:

- **a sessão implementou a issue** (auditoria de saída, antes do `gh pr create`): ela não grava
  `complete` (`docs/CONVENTIONS.md` §3.6) e não mergeia;
- **quem pediu a auditoria disse para não mergear**, ou não há PR aberto.

Na orquestração autônoma (`docs/PROMPT-orchestrator-autonomous.md` §3) e na auditoria pedida
direto pelo humano em sessão nova, a sessão de auditoria fecha.

## "Escopo fechado" numa issue

É a condição de entrada 1 do `GIT-WORKFLOW.md`. Vale quando:

- o status global é ✅, ou ⚠️ só com observações, achados "NÃO-ISSUE" e achados "ISSUE SEPARADA"
  que já viraram issue, com o link no comentário do veredito;
- todo `## Critério de aceitação` do corpo da issue tem evidência (Fase C, item 3), com o
  quantificador honrado (Fase C, item 4);
- nenhum achado classificado "DENTRO desta issue" (Fase D-bis, item 1) está em aberto;
- a linha da issue está `done` na Tabela de Issues do `docs/roadmap.md` (Fase C, item 6);
- os gates da Fase B estão verdes no head do PR, com o número colado.

## O que é próprio da issue na sequência

- **"Depende de"** (condição de entrada 5): cada issue ou Stage listada no corpo da issue e na
  linha dela no roadmap já está mergeada em `develop`.
- **`Closes #<num>` no corpo do PR:** sem ele o merge não fecha a issue. Conferir antes do
  merge; depois, `gh issue view <num> --json state` tem de dar `CLOSED`.
- **Grupo de issues ou épico:** cada PR fecha por si, na ordem de dependência (Fase D-bis,
  item 7). O seguinte só começa depois da verificação do passo 7 do anterior, e recomeça do
  passo 1, porque o `develop` andou.

## Saída

Depois do relatório da Fase E, uma linha de status: PR mergeado com o hash do merge commit,
issue `CLOSED`, worktree, branches e containers removidos. Se parou, a linha diz o que falta.

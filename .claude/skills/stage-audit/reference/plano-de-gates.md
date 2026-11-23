# Referência da stage-audit — plano de gates

Detalhe do item 7 da Fase C do [SKILL.md](../SKILL.md#fase-c--cruzar-implementação--docs) e
do item 7 da Fase C da [`issue-audit`](../../issue-audit/SKILL.md#fase-c--cruzar-implementação--corpo-da-issue).
A regra não mora aqui: orçamento, onde cabe um ponto, justificativa do 4º ponto, como o ponto é
cumprido, ponto vermelho, issue avulsa e transição estão em
[`docs/PIPELINE.md` §9.6](../../../../docs/PIPELINE.md#96-plano-de-gates) (ADR 0.0.0021). Este
arquivo só diz **como o auditor confere**. Em divergência, vale o PIPELINE.

Sumário: [1. Corte](#1-a-stage-precisa-de-plano-corte) ·
[2. Forma](#2-a-forma-do-plano) · [3. Cumprimento](#3-o-cumprimento-de-cada-ponto) ·
[4. Classificação](#4-classificação) · [Issue avulsa](#issue-avulsa)

## 1. A Stage precisa de plano? (corte)

**Stage: o corte é mecânico.** `scripts/check_gate_plan.py` (issue #201, no `make docs-check`)
isenta só as pastas da lista fechada `LEGACY_STAGES` (as 23 de `docs/stages/` em 2026-11-22,
travadas por teste) e o technical em `draft`. Pasta fora da lista, com technical aprovado, deve
o plano: com o `docs-check` verde, o corte e a forma já estão conferidos. A data de nascimento
abaixo sobra para a issue avulsa (que não tem pasta) e para a evidência de uma divergência.

A transição do §9.6 fala da branch que **nasce** depois do merge do ADR 0.0.0021. O nascimento é
a menor data de autor entre os commits da branch, que o rebase preserva. A comparação é em
segundos desde a época (`%at`/`%ct`), não em texto ISO: commit feito com outro fuso (devcontainer
em UTC) inverte a comparação de strings.

```bash
nasc=$(git log --format=%at origin/develop..HEAD | sort -n | head -1)   # nascimento da branch
corte=$(git log -1 --format=%ct 13ad533)   # merge do PR #192 (ADR 0.0.0021): 2026-11-16T17:23:40-03:00
[ "$nasc" -gt "$corte" ] && echo "plano exigido" || echo "transição"
```

- **Nascimento anterior ao merge** → Stage da transição: sem plano, e nenhum é exigido (nem no
  gate de saída, nem aqui). Vai ao relatório como observação, com as duas datas. A 2.7, a 3.11 e
  a 4.4 caem aqui (`stage N.M: conceptual draft` em 2026-11-09, 2026-11-09 e
  2026-11-16T16:17), e com elas todas as que estavam em `docs/stages/` em 2026-11-22 (a 4.4
  era a mais nova).
- **Nascimento posterior** → plano exigido.
- **Plano presente numa Stage da transição** → audita-se como os outros: não era exigido, mas o
  que foi escrito foi prometido.
- Auditoria depois do merge (`origin/develop..HEAD` vazio): trocar o intervalo por
  `<merge>^1..<merge>^2`.

**Limites do corte.** A data de autor muda com `git commit --amend --reset-author`,
`git rebase --ignore-date` (ou `--reset-author-date`) e com um squash que reescreve todos os
commits; e a branch criada antes do merge mas com o primeiro commit depois tem a data posterior,
embora a worktree dela tenha nascido sem o §9.6. Nos quatro casos o erro vai para o lado de
**cobrar** o plano, nunca para o de dispensá-lo. Se o relatório, a §7 ou o reflog mostram que a
execução começou antes do merge, vale a transição, registrada como observação com a evidência.

Não servem de corte a ancestralidade (`git merge-base --is-ancestor 13ad533 <commit>`) nem a
presença da seção: depois de um rebase em `develop` toda branch antiga descende do merge (o
`stage 4.4: technical approved`, `4821fba`, desce), e a seção ausente é justamente o que se
procura.

## 2. A forma do plano

Ler a tabela "Plano de gates" da §1 do `technical.md` e conferir contra o §9.6, "Por Stage":
quantos pontos, se o de saída está entre eles, se cada ponto do 4º em diante traz a
justificativa no plano ou um `[deviation]` na §7. "Por segurança" não justifica.

Quem confere a forma é `scripts/check_gate_plan.py`, no `make docs-check` (título na §1,
cabeçalho do template, pontos numerados, células preenchidas, ponto de saída, "por segurança"
recusado do 4º em diante): com ele verde, o auditor só lê se o motivo de cada ponto é concreto e
confere o cumprimento (seção 3). Ponto posto no lugar errado (fora dos grupos de "Onde pôr um ponto no
meio da Stage") é julgamento da Fase D-bis, não contagem.

## 3. O cumprimento de cada ponto

O §9.6 ("Como um ponto é cumprido") diz o que vale como evidência. Para cada linha da tabela:

1. **O commit do ponto:** o último commit da Task, o `fix` dela incluído.
   ```bash
   git log --format='%H %s' origin/develop..HEAD | grep -F '[N.M/task-NN'
   ```
2. **A evidência sob orquestração:** o job `lint-and-test` verde no run cujo head é esse commit.
   ```bash
   gh run list --commit <sha> --workflow ci.yml --limit 200 --json databaseId,conclusion,event
   gh run view <id> --json jobs --jq '.jobs[] | select(.name=="lint-and-test") | .conclusion'
   ```
3. **A evidência no modo manual:** o relatório do executor (PROMPT-stage, §5 do relatório:
   por ponto, a Task e as últimas linhas da saída com o exit code) ou um `[measurement]` na §7.
   Ponto sem nenhum dos dois não tem evidência.
4. **O ponto de saída** é o run do head do PR, já conferido na Fase B.
5. **Rebase depois do ponto:** o hash do ponto sumiu da branch, mas o run continua. Listar os
   runs da branch (o `--limit` importa: o padrão do `gh` é 20) e achar o da Task pela mensagem
   do commit, que a API ainda serve para o hash reescrito:
   ```bash
   gh run list --branch <branch> --workflow ci.yml --limit 200 --json headSha,conclusion
   gh api repos/{owner}/{repo}/commits/<headSha> --jq .commit.message
   ```
6. **Ponto vermelho:** o commit seguinte ao do ponto é o `[N.M/task-NN-fix]` da mesma Task,
   antes do primeiro commit da Task seguinte (§9.6, "Ponto vermelho"). Sob orquestração, run
   vermelho **entre** pontos segue a mesma regra (§9.6, "Como um ponto é cumprido"): a lista do
   item 5 mostra os `failure`, e cada um precisa do conserto antes da Task seguinte.
7. **Espera fora do plano:** ponto que o relatório ou a §7 citam e a tabela não tem precisa do
   `[deviation]` com a justificativa.

## 4. Classificação

- **non-blocker, dentro da Stage:** plano ausente numa Stage posterior ao corte; ponto além do
  3º sem justificativa; ponto sem evidência; ponto vermelho sem o `fix` antes da Task seguinte.
  O gate de saída verde ainda cobre o código; o que falta é o rastro. A fase de aplicação o
  repõe: `[deviation]` na §7 com o run achado, ou com o motivo de não haver; no plano ausente,
  o `[deviation]` lista os pontos em que o executor de fato esperou, com os runs. Como todo
  finding dentro da Stage, trava a Fase F até ser reposto ([fase-f.md](fase-f.md), "Escopo
  fechado"). Plano ausente ou estourado é também o gatilho de reavaliação da issue #201: citá-la
  no veredito se ainda estiver aberta.
- **blocker:** o ponto de saída vermelho (regra da Fase B).

## Issue avulsa

O §9.6, "Issue avulsa", vale com quatro trocas:

- **Corte:** o mesmo comando do item 1, na branch da issue.
- **Onde está o plano:** no corpo do PR, onde o §9.6 o põe (seção "Plano de gates" do
  template). O auditor lê só ali (`gh pr view <num> --json body`); conversa e relatório do
  executor não contam. Corpo sem o plano, numa branch posterior ao corte, é finding
  **non-blocker, dentro da própria issue**, como o plano ausente da Stage (seção 4): o gate
  de saída verde cobre o código, falta o rastro. O conserto é editar o corpo do PR com as
  sub-tasks e os pontos em que o executor de fato esperou, com os runs (um só, o de saída, se
  não esperou em outro). Como todo finding dentro da própria issue, trava a Fase F até o corpo
  ser editado.
- **Ponto extra:** um ponto além do de saída precisa do `[deviation]` no corpo do PR, não na §7
  (issue não tem `technical.md`).
- **Commit do ponto:** a marca é `[#<num>/task-NN`; a evidência segue a seção 3.

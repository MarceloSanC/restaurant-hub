# Referência da stage-audit — disposições dos Checkpoints

Detalhe do item 8 da Fase C do [SKILL.md](../SKILL.md#fase-c--cruzar-implementação--docs). A
regra não mora aqui: onde e quando cada checkpoint grava a disposição está em
[`docs/CONVENTIONS.md` §3.4](../../../../docs/CONVENTIONS.md#34-seção-pós-execução-do-technicalmd-7-do-template)
e no `PROMPT-stage-single-session.md` (§"Revisão por agentes independentes"), com o formato no
template `stage-technical.md` §7. Este arquivo só diz **como o auditor confere**. Em
divergência, vale a CONVENTIONS.

## 1. Corte

A regra vale para a Stage aberta depois do merge da issue #210. As anteriores, a 3.10 inclusa,
estão em `LEGACY_CHECKPOINT_STAGES` no `scripts/check_technical_postexec.py`: nelas a ausência
da entrada é **observação**, não finding (a 3.11 registrou a dela como `[finding]`). Entrada
presente numa Stage do corte se audita como as outras: não era exigida, mas o que foi escrito
foi afirmado.

Fora do corte, a checagem 3 do script (rodado na Fase B) já garante que as entradas do A e do
B **existem** no technical `done`. Sobra ao auditor o momento, o C e o conteúdo.

Stage conduzida pelo RUNBOOK multi-sessão não tem revisor de contexto zerado: as entradas do A
e do B registram os gates humanos dos Passos 5 e 7 (o que pediram, ou aprovação sem ajuste), e
não há C. Confira o momento delas como no fluxo de sessão única.

## 2. O que conferir

1. **As entradas.** Uma por checkpoint, e uma por bloco no C:
   ```bash
   grep -nE '^#{3,4} .*\[decision[^]]*\].*Checkpoint [ABC]' docs/stages/<N.M>-<slug>/technical.md
   ```
   Os blocos do C saem do relatório ou da cadência (a cada 2–3 Tasks; um só se a Stage tem
   ≤ 4 Tasks). Bloco sem entrada é finding, mesmo sem nenhum `-fix`: "nenhum achado
   material" também se grava.
2. **O momento.** A entrada tem de estar no commit que fechou o checkpoint, não só no
   fechamento da Stage — é isso que a faz sobreviver à troca de sessão.
   ```bash
   git log --format='%H %s' origin/develop..HEAD | grep -F 'stage <N.M>: conceptual approved'
   git show <sha>:docs/stages/<N.M>-<slug>/technical.md | grep -n 'Checkpoint A'   # idem B no `technical approved`
   git log --format='%h %s' -S'Checkpoint C (bloco Tasks <NN>' -- docs/stages/<N.M>-<slug>/technical.md
   ```
   Com regressão de concept há dois `conceptual approved`: vale o último. O commit que
   introduz a entrada de um bloco do C é o `-fix` do bloco ou o commit logo depois da última
   Task dele.
3. **Cada achado com disposição.** Uma linha por achado, com `corrigido`, `refutado` ou
   `escalado`:
   - `corrigido`: o hash é ancestral do HEAD (`git merge-base --is-ancestor`) ou a marca do
     commit está no `git log` da branch; todo `[N.M/task-NN-fix]` de checkpoint aparece em
     alguma entrada do C.
   - `refutado`: traz o **artefato colado** (trecho de teste, código ou saída), não prosa; no
     blocker, cita a validação do 2º revisor.
   - `escalado`: aponta a pergunta P, o HALT ou a issue (`gh issue view <n>` existe).
4. **A refutação se sustenta.** Escolha 1–2 `refutado` (todo blocker refutado entra) e leia o
   artefato contra o achado: ele prova o que a refutação diz? É a conferência que a issue #210
   tornou possível — não a transforme em contagem de linhas.

## 3. Classificação

- **blocker:** entrada do A ou do B ausente fora do corte (a checagem 3 reprova: regra da
  Fase B); refutação cujo artefato não sustenta, quando o achado reaberto é blocker pelo
  próprio mérito (viola I\*, contradiz D\*).
- **non-blocker, dentro da Stage:** bloco do C sem entrada; achado sem disposição; `refutado`
  só em prosa; `corrigido` com hash que não está na branch; refutação que não se sustenta de
  achado não blocker. A fase de aplicação repõe com o que o relatório, os commits `-fix` e a
  §7 mostram, numa entrada `[deviation]` que diz de onde veio; o que não dá para repor vira
  achado reaberto. Trava a Fase F até ser reposto ([fase-f.md](fase-f.md), "Escopo fechado").
- **observação:** entrada gravada depois do commit que fechou o checkpoint (o conteúdo vale,
  o momento não se repõe): citar os dois hashes; ausência numa Stage do corte.

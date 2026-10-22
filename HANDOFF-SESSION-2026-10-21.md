# >>> ESTA BRANCH: docs/12-stage-placeholders <<<

> **REMOVER este arquivo antes de abrir o PR / fazer merge.**

issue #12 — INCOMPLETA (9 commits, ..3d0b6c0, SEM fechamento). O executor morreu (429) commitando a revisão do ADR 0.0.0007.
Falta: auditoria de testes do PROMPT-issue §; conferir gates (make check); commit de fechamento do roadmap (#12 open→done, datas 2026-10-21); depois auditar e PR.
Entregou: validador de dependência de Stage por stage_id em scripts/ + ligado no docs-check; tabela das formas do identificador em CONVENTIONS; glosa nos PROMPT-*; ADR da decisão.

---

# HANDOFF — sessão de orquestração Linux → Windows (2026-10-21)

> **Arquivo temporário.** Remover antes de abrir o PR desta branch. Mesmo conteúdo global
> em todas as branches desta leva; o bloco "ESTA BRANCH" no fim é específico.

## O que foi esta sessão

Uma sessão orquestradora (Claude Code, Linux) rodou várias Stages/issues do restaurant-hub em
paralelo, cada uma na sua **worktree** (`../restaurant-hub-worktrees/<slug>`), cada worktree com
**Postgres próprio** (porta do `.env` da worktree; contorno manual da #58 — `DATABASE_URL`
acrescentada à mão). O sponsor delegou as decisões da corrida ao orquestrador (modo autônomo):
E/C resolvidos por um agente `evidence-resolution`; os P o orquestrador decidia.

`develop` na base = `b2e1c68`. Baseline `make check` neste ambiente Linux: 4147 passed, cobertura
99,96%, ~5 min sem concorrência.

**A sessão foi interrompida por limite de sessão da API (HTTP 429, reseta 22:20 America/Sao_Paulo)
— vários agentes morreram no meio. O scratchpad foi zerado depois: rascunhos de corpo de PR,
registros de decisão e o rascunho do concept da 4.3 que viviam só lá SE PERDERAM. Os commits de
cada branch estão intactos.** Ao continuar no Windows: cada worktree tem o próprio Postgres; rode
`make check` da raiz da worktree; o `.env` precisa de `DATABASE_URL` coerente com a `POSTGRES_PORT`.

## Prompts canônicos do fluxo
- Stage: `docs/PROMPT-stage-single-session.md`. Issue avulsa: `docs/PROMPT-issue-single-session.md`.
- Auditoria: skill `stage-audit` (Stage) / `issue-audit` (issue). Decisão por evidência: skill
  `evidence-resolution` (triagem E/C/P; só P vai ao humano; hook `triage_gate` exige header `P:`).
- Git: skill `git-versioning-pointer`. O hook `git_guard` recusa criar/trocar branch no checkout
  principal (sempre em `develop`); worktree só por `python scripts/worktree-new.py <branch> --no-vscode`.

## Estado de cada frente (todas empurradas para origin por esta sessão)

ISSUES AVULSAS (o prompt de issue NÃO abre PR — o PR é passo humano/sessão seguinte; auditoria roda antes):
- **#6** chore/6-wire-logging-at-boot — PRONTA (6 commits, fechamento 72de0c1; make check 4153, 100%). Auditoria issue-audit NÃO concluída (morreu no 429).
- **#7** chore/7-align-pre-commit-hooks — PRONTA (6 commits, ..490ca78; 4156). Auditoria não concluída.
- **#8** chore/8-gitattributes-eol-policy — PRONTA (5 commits, ..76bfdeb; 4156). Auditoria não concluída.
- **#34** docs/34-task-fix-suffix-convention — PRONTA (9 commits, ..f3c3cb0; 4231) + 1 commit WIP de auditoria (edição dos PROMPT docs). Auditoria não concluída.
- **#37** docs/37-workforce-adr-sweep — PRONTA (10 commits, ..2b58f18; 4147). Auditoria não concluída.
- **#58** chore/58-worktree-database-url — PRONTA (8 commits, ..686c262; 4236). Auditoria não concluída.
- **#61** fix/61-cache-control-no-store — PROVAVELMENTE PRONTA (7 commits, fechamento 3b464c8), mas o executor morreu antes do relatório final — gates NÃO reconferidos. Verificar make check/cov + auditar.
- **#12** docs/12-stage-placeholders — INCOMPLETA (9 commits, ..3d0b6c0, SEM fechamento). Executor morreu commitando a revisão do ADR 0.0.0007. Falta: auditoria de testes, gates, commit de fechamento do roadmap.

STAGE:
- **Stage 4.3** feat/72-4-3-scheduling-application (issue #72) — Fase 3A. Só o esqueleto está commitado (1f7a0f8 "stage 4.3: conceptual draft"). O rascunho do concept e os 20 registros E/C viviam no scratchpad e SE PERDERAM. 3 decisões P pendentes (D1–D3, abaixo). Decisões C de peso já tomadas pelo executor (ver bloco da branch). Falta tudo: decidir D1–D3, escrever concept + ~4 ADRs (4.3.0001–4), Checkpoint A, technical (~12 Tasks), Checkpoint B, execução, auditoria de testes, gates, PR.

PRs EM VOO (já tinham PR aberto contra develop; auditados nesta sessão):
- **#70** refactor/46-2-6-identity-unit-of-work (Stage 2.6) — issue-audit completo em 2026-10-19 (label `complete`); stage-audit desta sessão morreu no 429. HEAD c32be94, pushed, CI verde. 1º da fila de merge.
- **#71** refactor/49-3-7-application-authorization (Stage 3.7 autorização) — stage-audit em curso quando morreu; 3 commits de auditoria + 1 WIP (nota da 3.7 no roadmap) empurrados por esta sessão. 2º da fila. FICA com o número 3.7.
- **#69** feat/60-3-7-termination-access-scope (Stage 3.7 desligamento) — stage-audit APROVADA-COM-FINDINGS (HEAD 809f0e3, label complete, CI verde). 3º da fila. PRECISA DE RETRABALHO: renumerar 3.7→3.8 (colisão com #71) e rebasear sobre #70+#71.

## Decisões do orquestrador (por delegação do sponsor, 2026-10-21)
- Colisão de número: **#71 fica 3.7; #69 vira 3.8** (renumerar pasta docs/stages, ADR 3_7_0001→3_8_0001, roadmap, workforce §3.8, ~25 arquivos).
- Ordem de merge: **#70 → #71 → #69**. Cada um rebaseado sobre develop atualizado antes do seu merge.
- Modo de merge do projeto: `gh pr merge --merge` (NUNCA squash/rebase); merge só com auditoria `complete` + CI verde. NUNCA em main.

## Roteiro do retrabalho da 3.8 (#69), após merges de #70 e #71
1. rebase sobre develop; renumerar 3.7→3.8 em tudo (Stage, ADR, roadmap, workforce §3.8, ADR 3.5.0003 nota) + títulos do PR.
2. integrar com #71: testes que constroem `DeactivateEmployeeUseCase(employees, gateway)` passam a precisar do `guard`; teste novo "recusa do guard não chama list_by_unit nem is_employee_login"; docstring "quem autoriza cada operação" (#71) inclui `is_employee_login`.
3. F5: alinhar ADR (Alt. H, §Negative) e concept §10 — dono da corrida D7 = Stage "vincular login existente" (lock por user_id), NÃO a #46.
4. `check_technical_postexec` fica fail-open sem o commit "stage 3.8: technical approved" → conferir à mão.
5. roadmap updated_at/last_reviewed_at; re-auditar o delta (os scripts de mutação do auditor estavam em scratchpad/audit69_tools e se perderam — refazer).

## Decisões pendentes da Stage 4.3 (D1–D3) — recomendação do executor
- **D1 [P]** staff lança férias/indisponibilidade ou retira função de registro já alocado: (a) escala mostra a violação ao vivo e a gerente corrige [nada muda em staff] × (b) guarda em staff recusa. Recomendação do executor: **(a)** (coerente com reconciliação-na-leitura e ADR 4.1.0004). (O orquestrador inclinava-se a (a).)
- **D2 [P]** `change_demand_quantity` com o mesmo N (no-op sem versão/auditoria): (a) no use case 4.3 × (b) no domínio (`Schedule` devolve self; alinha ADR 4.1.0009 Decision 3). Recomendação: **(b)**.
- **D3 [P]** gerente desabilita faixa cuja única alocação é de desligado (invisível por reconciliação-na-leitura): (a) recusar como hoje × (b) recusar devolvendo os ids das alocações de desligado p/ a gerente desalocar no mesmo lote × (c) remover junto. Recomendação: **(b)**.

## Pendências de roadmap
- Tabela de Issues mostra **#10, #16, #56** como `open`, mas estão FECHADAS no GitHub (sincronizar). Obs: a #16 está closed mas o defeito que ela descrevia persiste (`scripts/check_stage_issue.py:70` busca state e não usa) — avaliar reabrir.

## Findings levantados pelos executores (candidatos a issue nova — decidir)
- #6: Alembic `disable_existing_loggers=True` cega loggers na suíte → anexar à #26; reset de senha não loga falha → #26; uvicorn access log → 6.3; LOG_LEVEL inválido → 6.2; .env.example erra sobre DEBUG.
- #7: make check não confere formatação; make lint/fmt não cobre migrations/; also_copy do mutmut sem guard (job noturno continue-on-error); PIPELINE §3.4 afirma falso que pre-commit roda pytest.
- #8: VS Code cria CRLF no Windows (.editorconfig+extensão / .vscode versionado / README).
- #34: hook aceita Stage como escopo; scripts/ fora do mypy e da cobertura.
- #37: 4 ADRs com YAML de frontmatter inválido (1_2_0001, 2_3_0001, 3_5_0003, 3_5_0004); sem guard mecânico p/ docs/domain/**.
- #58: porta presa por Postgres órfão (worktree-rm não faz compose down); make migrate/run sem a guarda; migrations/env.py ignora URL do chamador; job noturno de mutação morre na coleta (.claude/ fora do also_copy).
- #69 (auditor): gate docs-check "Stage done com CA aberto" (4ª recorrência); meta-teste `_conforms` em todo fake de port.

## Mitigação já aplicada nesta sessão
- Os hooks git compartilhados apontavam para o venv da worktree feat-60; `make setup` no checkout principal religou-os para `/home/marcelo/Code/restaurant-hub/.venv`.

---

# >>> EXECUTOR DA #12 — progresso detalhado (append 2026-10-21, não apagar) <<<

O executor da #12 NÃO morreu no ADR: a revisão do ADR 0.0.0007 foi commitada (`3d0b6c0`) e
o executor seguiu. Estado real abaixo. Working tree limpo; nada pendente de `git add`.

## Commits da #12 (origin/develop..HEAD, ordem cronológica)
- `4d3d512` docs(adr): decidir a checagem por script [#12/task-01]
- `adc1e6e` chore(tooling): validador check_stage_deps por stage_id + testes [#12/task-02]
- `474fe1c` chore(tooling): ligar no docs-check [#12/task-03]
- `53c0ecc` docs(conventions): tabela das formas do identificador §1 [#12/task-04]
- `5c29a0b` docs(pipeline): glosa nos PROMPT-* + chamada do validador [#12/task-05]
- `328df9d` docs(pipeline): dependência e verificação do runbook pela forma certa [#12/task-06]
- `694db05` fix(tooling): exigir dependência MERGEADA + fail-closed [#12/task-02-fix]
- `e424332` test(tooling): sobreviventes da auditoria (44 mutações mortas) [#12/task-06-extra]
- `3d0b6c0` docs(adr): rever ADR 0.0.0007 após revisão de completude [#12/task-01-fix]

## Decomposição entregue (7 sub-tasks + 3 extras de fix/cobertura)
Padronizar os placeholders de Stage que viram comando (stage_id com slug × número). Entregue:
1. ADR 0.0.0007 (fork C: vale um validador; resolvido pela evidência — issue-first já é mecânico,
   a prosa errou duas vezes no PR #11).
2. `scripts/check_stage_deps.py` + `tests/unit/test_check_stage_deps.py` (114 testes). Recebe o
   stage_id, deriva o número do commit reservado; confere, por dependência: linha na Tabela de
   Stages, número único, status `done`, e `stage N.M: complete` MERGEADO numa branch de integração
   (origin/develop, develop, origin/main, main — as mesmas do check_technical_postexec). Dependência
   de issue (`#N`) conferida pela Tabela de Issues. Alvo = stage_id (número nu recusado, exit 2).
   Sem argumento = docs-check sobre toda pasta. Sem histórico: alvo explícito → exit 2; docs-check →
   status + WARN (força do ADR 1.2.0001: make check local não exige histórico completo).
3. Ligado no `docs-check` (Makefile) + Class 5c no `validate-ci-gate.md` (§Maintenance).
4. CONVENTIONS §1 "Identificador da Stage": tabela stage_id/número/N-M/N_M/adr_id + issue.
5. Glosa em PROMPT-stage/autonomous/step/issue: `<N.M>` é número; `<dep>` é stage_id;
   `<slug-do-adr>` separado de `<slug>` (a substituição ingênua gerava adr com slug da Stage).
6. RUNBOOK: pré-req chama o validador; verificação de roadmap casa a LINHA da Stage pelo stage_id
   (`$N\.$M.*done` casava 2 linhas e ficava verde com a Stage em review); verificação de branch
   pelo nome inteiro (`$N-$M` casava branch de outra Stage).

## FALTA para fechar a #12 (ordem)
1. **Auditoria de Testes do PROMPT-issue §** (6 itens, por escrito) — a cobertura já foi exercida
   por 44 mutações reais mortas (log em scratchpad `tools/mutate2.py`); falta redigir as respostas.
2. **Gates de saída:** `make check` verde (o último rodou em 474fe1c, EXIT=0, 4210 passed, cov
   99.96% — rodar de novo após os commits de fix); coverage ≥90% no diff (check_stage_deps 99%).
3. **Comentar [finding]s na issue #12** (lista abaixo) antes de fechar.
4. **Commit de fechamento:** `docs/roadmap.md` linha #12 open→done + `updated_at`/`last_reviewed_at`
   = 2026-10-21; `git commit -m "chore(roadmap): fechar issue #12 ... Refs #12"`.
5. **REMOVER este HANDOFF** antes do PR.
6. Relatório + recomendação de PR. NÃO abrir PR / merge (regra do prompt).

## Decisões ([decision], para o corpo do PR)
- D1 (C): vale o validador; recebe stage_id, deriva o número. Ancorado em check_stage_issue (gate
  irmão), F4/F-C do PR #11, verificação do runbook verde-falsa. Reversível.
- Fechada = MERGEADA em branch de integração (não HEAD) — revisão de completude mostrou que HEAD
  deixa passar branch empilhada, contra RUNBOOK/PIPELINE/GIT-WORKFLOW. A versão HEAD virou a
  Alternativa C rejeitada no ADR (nenhuma versão chegou ao develop).
- Fonte do depends_on/status = Tabela de Stages (não frontmatter: template em 3A).

## Achados ([finding], comentar na issue #12 — NÃO abrir issue nova, orquestrador decide)
- F1: o caminho de ADR `N_M_NNNN-<slug>.md` ainda usa `<slug>` no doc dono (CONVENTIONS §1 L98/108),
  no PIPELINE (L132/337), no template `stage-concept.md` (L89/102) e na skill stage-audit (L180).
  A glosa `<slug-do-adr>` só entrou nos PROMPT-* e no RUNBOOK; quem preenche o template segue sujeito
  à colisão. Fora do escopo mínimo desta issue (6 sub-tasks); classe do problema, candidata a
  follow-up de docs.
- F2: RUNBOOK Passo 1 usa `$issue` antes de defini-lo (Passo 2 define). Bug pré-existente de doc.
- F3: `validate-ci-gate.md` §Purpose listava 3 scripts do docs-check; o Makefile tem 6 — corrigido
  nesta issue (task-03), mas check_docs_claims/check_harness tinham entrado sem atualizar o runbook.

## Revisão de completude (decision-reviewer) — já tratada
Rodou e apontou: (a) HEAD deixa passar branch empilhada → corrigido (fechada=mergeada, task-02-fix);
(b) exit 2 em clone raso feria "make check local sem histórico" → corrigido (docs-check degrada p/
WARN, alvo explícito mantém exit 2); (c) fail-closed escapava por traceback (git ausente, roadmap
não-UTF-8) → corrigido p/ exit 2; (d) dependência de issue `#N` virava erro de forma → agora
conferida na Tabela de Issues. Resto = ajustes de texto, aplicados ou registrados como finding.

## Auditoria de testes independente — já tratada
Subagente adversarial achou 2 verdes-falsos sobreviventes (alvo não-primeiro S10; dependência
aberta antes de fechada M1) + fail-closed furado. Todos cobertos no task-06-extra; re-mutação de
44 mutantes (incl. os 2) = 44 mortos. Script e testes restaurados byte a byte (git status limpo).

## Pré-condições (todas verdes no início)
Working tree limpo; branch docs/12-stage-placeholders; issue #12 OPEN; linha #12 no roadmap `open`;
sem depends_on. Nenhuma contradição com fonte superior. Nenhuma bifurcação P (só E/C, resolvidas).

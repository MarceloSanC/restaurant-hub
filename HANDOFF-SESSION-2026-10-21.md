# >>> ESTA BRANCH: docs/37-workforce-adr-sweep <<<

> **REMOVER este arquivo antes de abrir o PR / fazer merge.**

issue #37 — PRONTA (10 commits, ..2b58f18; make check 4147). Zero lacunas abertas com ADR accepted (eram 4). references de 8→26 ADRs.
Falta: auditar, rebasear, PR `docs(staff): issue #37 — varrer workforce.md contra os ADRs 3.1.x, 3.2.x e 3.4.x`.
Conflito com #69: só a linha `updated_at` do frontmatter do workforce.md (manter a mais recente); o §3.8 ficou byte-idêntico ao develop.

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

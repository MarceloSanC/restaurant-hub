# >>> ESTA BRANCH: refactor/46-2-6-identity-unit-of-work <<<

> **REMOVER este arquivo antes de abrir o PR / fazer merge.**

PR #70 (Stage 2.6). HEAD c32be94 já pushed, 0 commits locais extras. issue-audit `complete` de 2026-10-19; o stage-audit desta sessão morreu no 429 (não concluiu, mas não achou nada pendente).
1º DA FILA DE MERGE (#70 → #71 → #69). Antes de mergear: rebasear sobre origin/develop, CI verde, label complete → `gh pr merge 70 --merge`.
REMOVER este arquivo de handoff antes do merge (senão vai para develop).

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

## Auditoria do PR #70 (Stage 2.6-identity-unit-of-work) — CONCLUÍDA (2026-10-21, auditor Opus)

**Veredito: aprovada com findings, sem bloqueante.** Tudo aplicado e no remoto; label `audit-status` = `complete`; `mergeStateStatus: CLEAN`; CI `lint-and-test` verde no HEAD `c32be94`. NÃO foi feito merge (é passo da fila do orquestrador). A auditoria está FECHADA — não falta nada; o que segue é registro.

### Commits de fix empurrados (push feito, `dfa2410..c32be94`)
- `d136914` test(identity): cobrir os sobreviventes da auditoria da Stage no contrato da unidade [2.6/--]
- `c32be94` docs(identity): marcar os CAs da 2.6 e registrar a auditoria da Stage [2.6/--]

### Gates verificados
- `make check` EXIT=0 em `dfa2410` (4342 passed, cov 99,96%), em `d136914` (4345) e em `c32be94` (4345). 100% de linha/ramo em todo arquivo novo. import-linter 10 kept. check_layout regra 10 verde. check_technical_postexec OK. roadmap 2.6 `done`. ADRs 2.6.0001/0002 `accepted`.
- Postgres da worktree na 5442; baseline sincronizado com `uv sync --extra dev`.

### Findings (todos non-blocker, dentro da Stage) — corrigidos no PR
- F1: 14 CAs do concept §11 com caixa aberta (com evidência) → marcados em `c32be94`.
- F2: §7 citava 8 hashes de antes do rebase (561ee2b, 42fcfd9, 5e584c3, 63ca1ad, 9cb5f6f, 723ef33, f74017c, 6213d9f), inexistentes na branch → trocados pelos reais (437f240, 4e95686, 3491e4a, 234e1e7, 4965609, 6cc0632, c6fc507, 1876351) em `c32be94`.
- F3: `dfa2410` (`[2.6/--]`) sem entrada na §7 → registrado em `c32be94`.
- F4: 3 mutantes sobreviventes no contrato da unidade (`test_unit_of_work_contract.py`): apagar linha de `_ESCRITAS`/`_LEITURAS` ficava verde (1223/1225 passed); L5 não provava "nenhum estado publicado" (925 passed) → `d136914` deriva a totalidade das tabelas dos ports de `ports/out/*_repository.py` e acrescenta L5 com a externa desfeita depois da recusa. Mortos.

### Verificação pela borda HTTP (uvicorn real, Postgres, argon2/emissor reais) — refeita
- 2× POST /auth/refresh simultâneos: `[200,401]` em 12/12 nesta branch (vencedora morta); develop `b2e1c68` deu `[200,200]` em 11/12.
- POST /auth/password com escrita falhando (trigger temp): 500, token NÃO consumido; sem falha: 204 e login 200. Develop: token consumido, retentativa 401.
- Mutações dirigidas (cópia descartável): 8 mortas desde o início (savepoint, retorno do revoke, L5-após-checkout, publicação não desfeita, conexão não chaveada pelo engine, unidade sobre outro engine, consume fora da unidade, fake grava antes de validar).

### Observações registradas no comentário do veredito (sem ação nesta Stage)
- `# type: ignore` inertes em testes (mypy só cobre src/ e tests/fakes/).
- Corpo do ADR 2.6.0002 §5 editado após `accepted` (`6cc0632`, pré-merge, declarado na §7) — CONVENTIONS não abre exceção explícita; merece esclarecimento. [classe: doc/convenção — orquestrador decide se abre issue]
- Regra 10 tem pontos cegos não declarados no ADR: anotação não-nome (`X | None`, `Optional[X]`), atributo vindo de expressão, `posonlyargs`. Nada ocorre hoje. [classe: tooling — issue separada possível]
- Nota do roadmap diz "7 commits de correção"; são 8. Não corrigido (cosmético; evita tocar frontmatter com #71/#69 na fila).

### ALERTA para a fila de merge (#70 → #71 → #69) — após rebaixar sobre develop já com #70
- #69 adiciona `IdentityGateway.is_employee_login` (LEITURA): o teste `test_regra10_todo_metodo_dos_gateways_declarados_esta_classificado` (pinado em `tests/unit/test_check_layout.py`) fixa o conjunto EXATO de métodos de `IdentityGateway` → ficará VERMELHO até `is_employee_login` ser acrescentado à asserção. Não é bug de #70; é o pino de totalidade funcionando.
- #69 e #71 mexem em `deactivate_employee.py` / `create_login_for_employee.py`, ambos na `MULTI_WRITE_ALLOWLIST` da regra 10 (ADR 2.6.0002 §2). Entrada de allowlist que deixe de violar também reprova — reconferir a regra 10 após cada rebase.

### Artefatos de auditoria (scratchpad, fora do repo)
`/tmp/claude-1000/-home-marcelo-Code-restaurant-hub/d9052cc8-6c1a-4aeb-8f85-45b87c5bf93d/scratchpad/audit70/` — logs de make check, mutate.py (mutações), e2e_audit.py (verificação HTTP), comentario_veredito.md, pr70_body_after.md.

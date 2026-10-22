# >>> ESTA BRANCH: refactor/49-3-7-application-authorization <<<

> **REMOVER este arquivo antes de abrir o PR / fazer merge.**

PR #71 (Stage 3.7 autorização na application). FICA com o número 3.7. 3 commits de auditoria (06e164e, bd67851, 0686dd6) + 1 commit WIP (nota do roadmap, preservado antes deste handoff), empurrados agora.
2º DA FILA DE MERGE. stage-audit NÃO concluído (429) — retomar a auditoria no Windows antes de mergear; conferir label `complete` e CI verde.
REMOVER este arquivo de handoff antes do merge.

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

# Auditoria do PR #71 (Stage 3.7-application-authorization) — progresso do auditor (2026-10-21)

**Veredito formado: APROVADA COM FINDINGS, nenhum bloqueante.** A passada read-only (Fases A–D-bis) terminou; os fixes dos findings já estão commitados na branch. O que falta é só a aplicação no lado do GitHub (corpo do PR, comentário do veredito, label) — ver "O QUE FALTA".

## Gates medidos (verdes), HEAD auditado e commits de fix
- Branch antes dos meus fixes estava em `21ba10e` (`docs(roadmap): manter as citações … [3.7/--]`). Fixes aplicados nesta sessão, cada um com `make check` EXIT=0 verde antes do commit (logs em `/tmp/.../scratchpad/audit71/make_check_{A,B,C,D}.log`):
  - `06e164e` docs(staff): contar as três permissões nos docstrings do vocabulário [3.7/--]  (F5)
  - `bd67851` docs(staff): marcar os CAs da 3.7 e registrar a auditoria da Stage [3.7/--]  (F1 + F2 + F3 + registro da auditoria na §7 do technical, com V1/V2 e as 12 mutações)
  - `0686dd6` docs(scheduling): manter a citação do doc de domínio ao AuthorizedScope de staff [3.7/--]  (F6)
  - `942e22e` docs(scheduling): … nota da 3.7 no roadmap [3.7/--]  (F3 roadmap — **minha edição WIP, preservada pelo orquestrador**; conteúdo confere com o que eu tinha editado: file-scope cita stub único + 178 citações, "+307 testes", updated_at 2026-10-21; contagem de linhas do roadmap intacta, Step 4+ idêntico)
- `make check` no HEAD da branch (antes dos fixes e re-rodado após cada fix): **4454 passed** (4147 do develop + 307 da Stage), cobertura total **99,96%**, **100% em cada um dos 25 arquivos de `src/` tocados** (`coverage report --fail-under=90 --include=<arquivos do diff>` → 863 stmts, 0 miss, exit 0). mypy strict OK (216 arquivos); ruff OK; `check_layout`/`check_dead_shared` OK; import-linter **10 contratos mantidos** (bc-independence staff↔identity com zero ignore_imports); `check_technical_postexec` OK; `check_stage_issue` OK (issue #49); `check_docs_claims` OK; `check_harness` 0 achados. Lock sincronizado.
- Baseline de contagem confirmada: develop coleta 3913 testes antes do merge da 4.2, 4147 após (b2e1c68); branch coleta 4454 (+307).
- ADR 3.7.0001 em `status: accepted`. Supersessões parciais datadas em 3.2.0002, 3.4.0001 §4 e 3.6.0004, e errata no concept 3.2 §5.16 — todas conferidas contra o texto citado (as citações batem literalmente).
- CA09/CA10/CA11/CA12 pelos comandos do technical §3: `git diff origin/develop -- tests/e2e` vazio; `test_http_boundary_sweeps.py` intocado; `git grep '= "manage_'` em staff só acha `access_guard.py`; as três frases que a Stage deveria remover não existem mais; os dois `(#49)` restantes são só do lado de identity (legítimos).

## Verificações funcionais do §3 (rodadas pelo auditor FORA do repo, sobre cópias da árvore + Postgres da worktree :5443)
Script salvo em `/tmp/.../scratchpad/audit71/test_zz_audit71_functional.py` (NÃO versionar).
- **V1 (API real, app de produção):** gerente cria função (201), cria funcionário (201), lista (200), copia (201); gerente só da unidade A → 403 ao listar B e 403 ao copiar p/ B; dono de outro tenant → 403 ao listar A e 200 (lista vazia) no próprio catálogo. **Os mesmos status rodando sobre o develop** (regressão zero).
- **V2 (driver em processo sobre `wire_dependencies`, atores emitidos pela app via login+authenticate reais):** dono de outro tenant recusado com `TenantNotVisibleError` ao listar/criar funcionário/criar função/copiar/criar login; gerente só de A recusado com `UnitNotVisibleError` ao listar B e copiar p/ B; contagens de A, B e catálogo iguais antes/depois; controle positivo (dono de A cria função pelo driver) passa. No develop V2 nem compila (commands sem `actor`) — é a capacidade nova da Stage.

## Mutações do auditor (12, todas mortas pela suíte unitária de staff; nº de testes que cada uma mata)
cópia autoriza origem 2× =4 · ordem login invertida =4 · autorização condicional =1 (só CA15) · checagem pura antes da autz =1 (só CA15) · lê o escopo devolvido =17 · traduz a exceção do guard =9 · omite unidade =6 · omite tenant no catálogo =11 · permissão errada =32 · outro guard no composition_root =1 (só CA08) · ator trocado por object() =38 · leitura da origem entre as 2 autz da cópia =2. Nenhuma sobreviveu.

## Findings (todos NÃO bloqueantes; disposição aplicada)
- **F1** 15 CAs do concept §11 com caixa aberta, todos com evidência → marcados `[x]` em `bd67851`.
- **F2** hashes `6cc72e0`/`12b895a`/`706753b` citados na §7 do technical não existem (reescritos pelo rebase) → trocados pela tag do commit (`[3.7/task-03-fix]` etc.) em `bd67851`.
- **F3** commit do remapeamento de 178 citações sem entrada na §7, e nota do roadmap omitia os 7 docs + repetia nome de dublê previsto → entrada nova na §7 + nota do roadmap corrigida (`bd67851` + `942e22e`).
- **F4** verificações funcionais do §3 não registradas → rodadas (V1/V2 acima) e registradas na §7 (`bd67851`).
- **F5** docstrings do vocabulário diziam "duas permissões/dois valores" (port e borda), hoje são 3 → corrigido em `06e164e` (contagem de linhas do port preservada).
- **F6** `shift-scheduling.md` citava `access_guard.py` 90–109, deslocado p/ 108–127 pelo bloco de constantes → remapeado em `0686dd6`.
- **Observações sem ação:** 3 `type: ignore` novos em tests/unit repetem idioma de test_dtos (inertes — typecheck só cobre src/ e tests/fakes); test_application_authorization_chain importa CENARIOS/_montar de outro módulo de teste (acoplamento deliberado, uma fonte só); ADR 3.7.0001 cita em EN entre aspas o princípio que o 3.6.0004 escreve em PT (mesmo sentido).

## Classificação de escopo dos findings (D-bis #1)
Todos F1–F6 são **dentro da Stage** (documentação/rastreabilidade da própria 3.7) e foram corrigidos. Nenhum vira issue separada. Os `[finding]` da §7 do technical (autenticidade do ator fora da borda HTTP; validação de identificador fora da borda; staff como provedor do StaffReadPort/4.3; padrão 3.7.0001 em scheduling/4.3; ponteiros (#49) de identity; custo da dupla autz/6.3) são **issues pós-Stage** já com Stage candidata nomeada — orquestrador decide se abre; NÃO abri nenhuma.
- **[P] nenhum fork de produto nesta auditoria** — todos os forks da Stage são C/E (o comportamento visível ao usuário não muda; §6 do concept).

## O QUE FALTA (fase de aplicação da stage-audit — só lado GitHub, nada de código)
1. **Corpo do PR #71**: marcar o checklist — `concept.md não precisa de retoque retrospectivo` deve ficar `[x]` (os CAs foram marcados, não é retoque de conteúdo); `Runbooks` fica `[ ]` (n/a). Opcional: acrescentar 1 linha no "Decisões e achados" citando a auditoria.
2. **Trocar o label de auditoria** no corpo do PR de `> **Auditoria:** \`review\`` para `> **Auditoria:** \`complete\`` (CONVENTIONS §3.6; o check `audit-status` fica verde). NÃO editar à mão em outra sessão — é a sessão de auditoria que grava.
3. **Publicar comentário do veredito** no PR #71: `VERDICT: aprovada-com-findings`; gates numéricos (4454 passed, 99,96%, 100% por arquivo, 10 contratos, ADR accepted); F1–F6 com disposição e hash; V1/V2; 12 mutações mortas; findings pós-Stage listados (sem abrir issue).
4. **Push** dos commits `06e164e bd67851 0686dd6 942e22e` (+ handoff) para `origin/refactor/49-3-7-application-authorization`. **SEM rebase** (o rebase é da fila de merge #70→#71→#69, do orquestrador). **NUNCA merge.**
5. Rascunho do comentário do veredito ainda não escrito em arquivo; reconstituir desta seção.

## Riscos/notas para quem retomar
- Rate limit possível até 22:20 America/Sao_Paulo.
- A fila de merge é #70→#71→#69; após #70 esta branch rebaseia (conflitos esperados em composition_root.py e roadmap.md) — é passo do orquestrador, não do auditor.
- Colisão de número com #69 (também "3.7"): decidido que #71 fica com 3.7 e #69 vira 3.8 no rebase — não é achado desta auditoria.
- Postgres da worktree: `localhost:5443`, container `refactor-49-3-7-application-authorization-postgres-1`, DATABASE_URL no `.env` da worktree.
- Scratchpad do auditor: `/tmp/claude-1000/-home-marcelo-Code-restaurant-hub/<uuid>/scratchpad/audit71/` (logs de make check, scripts de mutação e de verificação de citações, cópias base/branch da árvore).

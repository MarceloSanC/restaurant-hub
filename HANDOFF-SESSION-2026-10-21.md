# >>> ESTA BRANCH: feat/72-4-3-scheduling-application <<<

> **REMOVER este arquivo antes de abrir o PR / fazer merge.**

Stage 4.3 (issue #72) — Fase 3A. SÓ o esqueleto está commitado (1f7a0f8). O rascunho do concept e os 20 registros E/C viviam no scratchpad e SE PERDERAM com o reset — refazer a Fase 3A a partir da issue #72 e das decisões abaixo.
DECISÕES C JÁ TOMADAS pelo executor (reversíveis; revalidar no Checkpoint A): (1) todo use case autoriza o próprio alvo, AccessGuard próprio de scheduling (precedente ADR 3.7.0001, sem depender do #71); (2) publicar = lote atômico de 1..N operações nomeadas, 1 checagem de versão, avaliação antes×depois; UX publicar-acumulado×gravar-a-cada-ação fica p/ 4.5; (3) ids das entidades criadas vêm do cliente, unicidade por unidade (no Checkpoint A, olhar isolamento de tenant: lookups sempre escopados, PK composta na 4.4); (4) estado+trilha numa única escrita do repo (sem unit of work, sem depender do #70); (5) "minha escala" por unidade, autorizada com view_own_schedule; (6) registro alocado que staff não devolve = fail-closed.
DECISÕES P PENDENTES: D1, D2, D3 (texto e recomendações no bloco global). Decidir antes de gravar o concept.
Falta: decidir D1–D3, escrever concept + ~4 ADRs (4.3.0001–4), Checkpoint A (2 revisores), technical (~12 Tasks; se >13 parar — alarme CONVENTIONS §6), Checkpoint B, execução, auditoria de testes (subagente independente + mutação real), gates, abrir PR.
Findings herdados p/ a 4.3 nas §7 das 4.1/4.2 (ver corpo da issue #72).

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

# Triagem por evidência — decisões D1–D3 da Stage 4.3 (agente evidence-resolution, 2026-10-21)

> Lote dos três pedidos que o executor da 4.3 marcou como [P]. Re-triados por evidência
> (skill `evidence-resolution`). Evidência interna conferida na fonte bruta; `decision-reviewer`
> despachado (19 achados, abaixo incorporados); `evidence-verifier` já rodara no executor
> (19 sustenta, 1 parcial). Caminhos relativos à raiz da worktree
> `feat-72-4-3-scheduling-application`.

## Resumo das classes finais
- **D1** (violação induzida por mudança de staff): **P** — confirmada. Recomendação: **(a) mostrar e corrigir**.
- **D2** (`change_demand_quantity` com o mesmo N): **C** — **re-triada de P para C** (nada observável difere entre as opções; não há preferência de produto a exercer). Decidida pelo agente: **(b) estender o no-op ao domínio**, degrau 1.
- **D3** (desabilitar faixa travada só por alocação de desligado invisível): **P** — confirmada. Recomendação: **(b) erro que revela ids das alocações de desligados para desalocação explícita**. **(c) excluída por evidência**.

---

## D1 — violação induzida por mudança em staff · **P** · recomendação (a)

**Classe:** P. A escolha final (guarda que recusa × avisar e deixar corrigir) é apetite de produto
(bloquear × avisar — skill §1), e o próprio doc/ADR já a nomeiam pergunta P para a 4.3
(`docs/domain/scheduling/shift-scheduling.md:1184-1186`; ADR 4.2.0002:110-113; ADR 4.2.0001:86-87;
concept 4.2 divergência 5, `docs/stages/4.2-validation-policies/concept.md:114-126`).

**Opções**
- **(a) mostrar e corrigir:** staff não muda; a escala vigente pode conter a violação (até um bloco
  de indisponibilidade) até a gerente desalocar; os invariantes do doc §3.5/§3.6.6/§3.6.7 passam a
  valer só para o que a **escala** introduz (nota datada já antecipada em `shift-scheduling.md:1181-1186`).
  A 4.3 não muda; o protocolo de publicação já só recusa/pede aceite do que a mutação introduz.
- **(b) guarda em staff:** staff passa a recusar `register_unavailability`/`assign_job_functions`
  sobre turno alocado, por port de consulta reverso (mecanismo do ADR 4.1.0006 §3), numa Stage de
  staff ou na 4.4; o RH só lança férias/retira função depois de a gerente desalocar; a 4.3 não muda.

**Evidência que restringe (conferida na fonte bruta)**
1. **(b) contradiz a divisão cadastro × escala do sponsor.** ADR 3.4.0006:57-59: *"contracted
   workload, shift preference and **unavailability are `cadastro`** … and that hr edits them"*.
   Sob (b), a edição de cadastro pelo RH (férias/indisponibilidade/funções) passaria a depender de
   a gerente editar a escala antes — inverte o ADR.
2. **(b) não cobre todas as origens de violação vinda de staff.** Além de férias e função retirada,
   há **mais duas** que (b) não guarda (reviewer, major):
   - **carga contratada** editada pelo RH: a `workload_policy` a lê
     (`src/restaurant_hub/features/scheduling/domain/services/validation/workload_policy.py:51-58`)
     e é configurável, inclusive `block` (concept 4.1 §5.18, `docs/stages/4.1-scheduling-domain/concept.md:817-818`);
   - **recontratação** faz as alocações antigas (nunca limpas) reaparecerem — p.ex. como
     sobre-cobertura depois de a gerente recobrir a demanda que se lia como descoberta
     (ADR 4.1.0006:199-201). Logo a leitura "os invariantes valem para o que a escala introduz"
     é **necessária nas duas opções** — (b) não a dispensa.
3. **(b) num registro desligado é impraticável.** O desligado continua editável e invisível, com
   alocações futuras nunca limpas (`workforce.md:124-128`; ADR 4.1.0006:86-87, :106-107); sob (b) a
   guarda recusaria ao RH editar a indisponibilidade/funções do desligado e ninguém veria o que
   desalocar — o impasse do D3 reproduzido dentro de staff.
4. **(b) não reusa a guarda que staff já tem.** `workforce.md:168-172` e ADR 4.1.0006:100-102: a
   guarda reversa existente é sobre remover a **função do catálogo** (`JobFunctionInUseError`), não
   sobre retirar a função de um registro; e um corte "só futuras" precisaria do "agora" no fuso da
   unidade, que staff não tem (sem `Clock` — `deactivate_employee.py:11`; port de fuso do ADR
   4.1.0005 ainda inexistente — `shift-scheduling.md:779-781`).
5. **(a) é coerente com o já ratificado:** reconciliação na leitura "como um refresh F5"
   (ADR 4.1.0006 Decision 1); o próprio motivo da leitura do RH é ver se as férias colidem com
   alocação (ADR 4.1.0004 Context:44-45, Alt A:89-90, Positive:115; `shift-scheduling.md:894`);
   ADR 4.2.0001 ("Bruno … starts violating") pressupõe staff que aceita a mudança.

**E/C do mesmo lote já decididos:** D2 (C, abaixo). **Recomendação: (a)**, forte. Nota ao decisor:
qualquer que seja a escolha, a nota datada do doc (hoje só nomeia férias e função) deve incluir as
**duas origens extras**: edição de carga e recontratação.

---

## D2 — `change_demand_quantity` com o mesmo N · **C** (re-triada de P) · decisão (b)

**Re-triagem:** o executor (e o finding 4.1) rotularam **P**. **Overturn para C:** o comportamento
**observável é idêntico** nas duas opções (sem versão nova, sem entrada de auditoria) — não há
preferência de produto a exercer; a diferença é só onde mora a comparação (skill §1: P exige algo
que o piloto percebe). O finding chamou "P" por tocar a enumeração fechada de quatro do concept 4.1,
mas isso é coerência de convenção interna, que o agente fecha.

```
[decision:C] D2 — change_demand_quantity com o N corrente: no-op no use case × no domínio
Escolha: no domínio — Schedule.change_demand_quantity devolve `self` quando a quantidade pedida
  é a corrente (comparação antes de tudo, como as outras 4 mutações de valor); a 4.3 passa a
  detectar as cinco mutações sem efeito por identidade (resultado `is` a escala de entrada).
Alternativas: (a) no use case — a 4.3 compara N pedido × corrente só para esta operação e não
  chama a mutação; cada consumidor futuro (Step 5) repete a comparação.
Degrau (C): 1 — coerência com o ratificado: ADR 4.1.0009 Decision 3 enuncia o no-op como regra
  GERAL ("A mutation called with the value it already holds returns self, leaving the version
  untouched — without that clause an optimistic check in 4.4 would make another editor lose work
  over a no-op", docs/adr/4_1_0009-...:75-78); a enumeração de quatro do concept 4.1 §5.16
  (docs/stages/4.1-scheduling-domain/concept.md:793-797) é sabidamente sub-inclusiva (o finding
  que a aponta é de 2026-09-27, Checkpoint C). O princípio governa o representante — mesmo padrão
  do ADR 3.6.0004 ("the law is pinned over the whole domain, not over a representative").
Base: ADR 4.1.0009:75-78; concept 4.1 §5.16:793-797 (lista 4, omite change_demand_quantity — a
  única outra mutação de valor das 11); código schedule.py:221-226 (sem comparação);
  DemandQuantity é frozen e compara por valor; finding technical 4.1:1512-1524.
Configuração candidata: nenhuma · Reversível: sim.
```

**Custo declarado (expansão de camada para trás, precedente ADR 3.6.0004 / 3.4.0003):** tocar a
4.1 (done) — 2 linhas no domínio + 1 teste, e **errata datada** em CA11b
(`docs/stages/4.1-scheduling-domain/concept.md:1406-1410`, de 4→5), no teste
`test_as_quatro_idempotentes_sao_mutacoes_da_lei_da_versao`
(`tests/unit/features/scheduling/domain/test_schedule_breaks.py:236-239`, `len==4`→5 e renomear),
na docstring de `schedule.py:35-39` e nas contagens do technical 4.1 (:983-984, :1089) + ADR novo
da 4.3. PIPELINE.md:664-665 pede TODO/Stage de correção para retoque de concept done; precedente de
errata datada em concept done: `docs/stages/3.2-staff-application/concept.md:650`. A nota de
reconciliação da 4.1 no roadmap hoje aponta a direção (a) (`docs/roadmap.md:1309-1311`); se (b) for
executado, atualizar essa linha e declarar a divergência (bloco 4.3 tem `arquivos_a_modificar: []`,
`docs/roadmap.md:1351`).

**Fallback aceitável:** se a Stage preferir não expandir para trás, (a) entrega o **mesmo
comportamento** dentro da 4.3 (o use case detecta o no-op desta operação por comparação de N, e as
outras quatro por identidade — mecanismo misto). (b) é a recomendação por uniformizar o domínio e
poupar cada consumidor futuro.

**Limite que nenhuma das opções cobre (reviewer 1d, minor):** um lote de efeito líquido nulo
(N→N+1→N na mesma submissão) sobe a versão 2× e grava 2 entradas; é questão de net-effect de lote,
fora do escopo de D2.

---

## D3 — faixa travada só por alocação de desligado invisível · **P** · recomendação (b)

**Classe:** P. O cerne (remover automático × revelar e desalocar explícito × recusar opaco) é fluxo
visível ao gerente **e** toca guardas ratificadas (L-E5, F7, Q1) — exatamente o caso que sobe ao
decisor com dossiê.

**Opções**
- **(a) recusar como hoje:** `ShiftBandInUseError`/`ShiftDemandInUseError` sem ids (schedule.py:206,232);
  a faixa fica presa e o gerente não vê alocação alguma (F7) nem entende por quê — dead-end declarado.
- **(b) erro novo na application** dizendo que as alocações que travam são de desligados (**sem
  nomes**) e devolvendo os **ids das alocações**, para a gerente desalocá-las num ato explícito no
  mesmo lote (gravado na trilha como dela); confirmação na UX da 4.5.
- **(c) remover junto automaticamente**, com registro na trilha.

**Evidência que restringe (conferida na fonte bruta)**
1. **(c) está excluída por evidência.** Reintroduz a cascata que o sponsor recusou em Q1
   (*"Recusa, desaloque primeiro (Recomendada)"*, concept 4.1 §13:1631-1637) e remove sem a "trilha
   de intenção" que Q1 exigia; e auto-remover a última alocação desarma a guarda L-E5 sem ato da
   gerente — o sponsor respondeu *"Manter a guarda"* à sub-pergunta (ADR 4.1.0006 sub-question
   alternative, :167-172; Positive/Negative). concept 4.1:1303 admite a cascata só *"como use case
   da 4.3 — nunca como batch no domínio"*, mas a resposta de Q1 é o passo explícito, não o automático.
2. **(a) é dead-end:** o desligado é invisível em toda tela (ADR 4.1.0006:81-89), então o gerente
   não tem o que desalocar e a faixa fica presa sem explicação útil.
3. **(b) preserva o ratificado:** mantém a guarda (gerente desaloca explicitamente, Q1), grava o ato
   como dela (trilha de intenção), e revela só **existência/contagem + ids de alocação** (opacos,
   AssignmentId surrogate — **não** dado do funcionário), o que é a leitura defensável de F7 ("o
   perfil/informação **dele** não aparece"): é metadado operacional para destravar, não exibição da
   pessoa. (b) e (c) tiram igualmente a alocação do estado vivo (vira trilha) — não discriminam por aí
   (reviewer D3-4); o que discrimina é silencioso-automático × explícito-auditado.

**Tensão a sinalizar ao decisor:** se o produto considerar que até expor contagem+ids de alocações de
desligados fere F7, a saída é (b) sem ids (só "há N alocações de registros inativos travando; use a
página de histórico/recontrate para resolver") — mas isso reabre o dead-end. O equilíbrio recomendado
é (b) com ids de alocação (sem nomes).

**Saída existente sob (a), via staff (reviewer D3-6):** recontratar → a alocação fica visível →
desalocar → desligar de novo (ADR 4.1.0006:49-50, :199-201). Mostra que (a) não é impasse
permanente, mas o custo é absurdo para o gerente — reforça (b).

**Contexto do lote já fixado:** não limpar futuras no desligamento (ADR 4.1.0006 §4); registro
ausente de staff ⇒ avaliador recusa (fail-closed, ADR 4.2.0002 §3); guarda reversa de remoção
definitiva entra com a persistência (4.4).

**E/C do lote já decididos:** D2 (C). **Recomendação: (b)**; (c) excluída por evidência; (a) inadequada.

---

# ANEXO — Fase 3A da Stage 4.3 (executor, 2026-10-21)

> Conteúdo reconstruído de contexto após o reset do scratchpad (os arquivos
> `scratchpad/stage-4.3/{concept-draft,decision-records,state}.md` se perderam).
> Worktree limpa em `1f7a0f8` (stage 4.3: conceptual draft); nada commitado além do esqueleto.
> Verificação independente feita antes do reset: um `evidence-verifier` conferiu as 20 citações
> load-bearing contra o texto bruto (19 sustenta, 1 parcial — invariante do doc §3.5 restrito pela
> nota da 4.2 em shift-scheduling.md:1181-1186, já incorporado); um `decision-reviewer` conferiu a
> completude (19 achados, 18 corrigidos nos registros abaixo, 1 virou o fork P D3).

## A. Estado das decisões C de peso (o orquestrador pode reverter)

- **D-AUTH** — todo use case autoriza o próprio alvo, com um `AccessGuard` **de scheduling** (port
  próprio em `application/ports/out/`), antes de qualquer outra instrução; ator como 1º campo de
  todo command/query (`repr=False`). Precedente do ADR 3.7.0001 (PR #71), **sem** depender dele.
- **D-SAVE** — publicar = um lote atômico de 1..N operações nomeadas (as 11 mutações do agregado),
  com uma checagem de versão e avaliação antes × depois. UX "publicar edições acumuladas × gravar a
  cada ação" fica para a 4.5.
- **D-IDS** — os ids das entidades criadas no lote vêm do cliente, com unicidade **por (tenant,
  unidade)**; o use case confere contra a escala carregada e as vizinhas antes de avaliar. Sem isso
  o aceite por `key` não casa entre avaliar e publicar.
- **D-AUDIT** — estado e trilha gravados numa única escrita do repositório (`add`/`save` recebem
  `ScheduleChange`): sem unit of work, sem dependência do PR #70.
- **D-OWN** — "minha escala" é **por unidade**, autorizada com `view_own_schedule` no escopo
  (tenant, unidade); descarta registros inativos.
- **D-ROSTER** — registro alocado que staff não devolve é **fail-closed** (não vira inativo): o
  avaliador recusa (`InvalidEvaluationInputError`); a guarda reversa da 4.4 impede o estado.

## B. O que falta (retomar aqui)

1. Incorporar D1–D3 (respostas do orquestrador) ao concept.
2. Gravar `docs/stages/4.3-scheduling-application/concept.md` (rascunho na §D) + 4 ADRs
   (`4_3_0001` protocolo de publicação/aceite; `4_3_0002` AccessGuard próprio da application;
   `4_3_0003` StaffReadPort+DTO e insumo fail-closed; `4_3_0004` lote com ids do cliente/escrita
   única), todos `bounded_context: scheduling`, `status: accepted`.
3. **Checkpoint A** (2 subagentes de contexto zerado: conformidade + domínio/testabilidade).
4. Commit `stage 4.3: conceptual approved`.
5. Technical (~12 Tasks, ordem inside-out da skill `task-ordering-hex`) + verificação de gap (uma
   passada) + **Checkpoint B** (matriz de rastreabilidade) + commit `stage 4.3: technical approved`.
6. Execução por Task; Checkpoint C a cada 2–3 Tasks; auditoria de testes (subagente + mutação
   real); gates de saída com evidência colada; commit `stage 4.3: complete`; PR.

## C. 20 registros de decisão E/C (formato da skill `evidence-resolution` §5)

Repositório (worktree): /home/marcelo/Code/restaurant-hub-worktrees/feat-72-4-3-scheduling-application

Use cases: `create_schedule`, `evaluate_schedule`, `publish_schedule`, `get_schedule`,
`get_calendar`, `list_past_schedules`, `get_my_schedule`.
Ports de saída: `ScheduleRepository`, `ScheduleConfigRepository`, `StaffReadPort`, `AccessGuard`
(de scheduling). Clock e IdGenerator de shared.

(As decisões abaixo já refletem as correções da revisão independente — ver §E.)

- **[decision:C] D-AUTH** — onde roda a autorização dos use cases. Escolha: todo use case recebe
  por construtor um `AccessGuard` próprio de scheduling e autoriza o alvo declarado no command
  antes de qualquer instrução; ator como 1º campo (`repr=False`). Alternativas: autorizar só na
  borda HTTP (4.5); decorator. Degrau 2 (fail-closed). Base: LAYOUT §5; ADR 2.2.0002; ADR 3.7.0001
  (PR #71, precedente, sem dependência de código); concept 3.7 §13 ("a 4.3 ... decidir lá se adota o
  padrão ... desde o primeiro commit"). Reversível: sim (caro de retrofit).

- **[decision:C] D-PERM** — nomes das permissões. Escolha: `"view_schedule"` (ler),
  `"manage_schedule"` (criar/avaliar/publicar), `"view_own_schedule"` (própria), como `str` no
  módulo do port; o enum de identity e o mapa de papéis entram na 4.5. Degrau 1. Base: ADR 4.1.0004
  Decision (três famílias; "Permission names ... are gaps for the Stage 4.5 concept"). Reversível:
  sim.

- **[decision:C] D-OWN** — como "minha escala" descobre os registros do ator. Escolha (corrigida):
  o `AuthorizedScope` carrega o `user_id` do sujeito autenticado (lei do port, nunca vazio);
  `get_my_schedule` autoriza `view_own_schedule` em (tenant, **unidade**) — passa pelo passo 5 de
  visibilidade de identity — e lê `StaffReadPort.list_members_of_user(tenant, unidade, user_id)`,
  descartando inativos; "minha escala" de N unidades = a 4.5 consulta por unidade. Alternativas:
  autorizar sem unidade (rejeitada — contradiz ADR 4.1.0004 §1 "all unit-scoped" e ADR 3.4.0008 Alt
  D); a query carregar `user_id`. Degrau 2 (o alvo deriva do token; nenhum chamador nomeia usuário
  alheio). Base: ADR 0.0.0005 cláusula 1; doc §3.7; ADR 4.1.0004 §1. Reversível: sim.

- **[decision:C] D-SAVE** — unidade de salvamento. Escolha: `publish_schedule` aplica 1..N operações
  nomeadas, atomicamente, com uma checagem de versão, uma avaliação antes × depois e os aceites;
  `evaluate_schedule` é o mesmo sem gravar. Degrau 4 (a forma serve as duas UX; a escolha percebida
  pelo piloto fica para a 4.5). Base: doc §3.5 lacuna "4.3/4.5 — unidade de salvamento"; ADR
  4.1.0001 §2 (F8). Reversível: sim.

- **[decision:C] D-IDS** — ids das entidades internas criadas no lote. Escolha: vêm do cliente
  (string opaca, formato validado na borda — ADR 3.6.0002); unicidade **por (tenant, unidade)** (quem
  gerencia a unidade lê todas as escalas dela, logo a recusa não é oráculo; entre unidades/tenants
  é permitido); o use case confere os ids criados contra a escala carregada **e as vizinhas** antes
  de avaliar → `IdentifierInUseError` (o mesmo tipo do repositório). Alternativas: id do servidor +
  referências locais do lote (rejeitada — a `key` por alocação, ADR 4.2.0002 Decision 5, não casaria
  entre avaliar e publicar); ids determinísticos. Degrau 5 + necessidade técnica. Reversível:
  parcialmente. Finding 4.5: formato UUID canônico dos ids de criação na borda (o validador do ADR
  3.6.0002 só barra vazio/espaço/NUL).

- **[decision:E] D-ACK** — protocolo do aceite consciente. Escolha: "introduzida pela mudança" =
  violação do depois cuja `key` não está no antes, **ou** está com medida pior (|observed − limit|
  maior) numa política **ordinal** (descanso, tetos, carga, sobre-cobertura, sobreposição,
  indisponibilidade — concept 4.2 §5.9); `block` introduzida recusa; `warn` introduzida exige
  aceite `(key, observed)` cuja medida não seja melhor; `function_mismatch` e `break_divergence` só
  por `key`. **Sobre-cobertura:** introduzida sse não havia sobre-cobertura da demanda no antes, ou
  entrou alocação fora do conjunto do antes, ou o excedente cresceu — desalocar um excedente sem
  chegar a N não re-pergunta nem recusa (Alt C do ADR 4.2.0002; custo declarado em D6 do concept
  4.2). Pré-existentes (de qualquer origem) são mostradas e nunca travam uma edição que não as
  introduziu. Base: doc §3.5 invariante; §3.6.8; ADR 4.2.0002 Consequences; concept 4.2 §5.8-§5.9.
  Reversível: sim.

- **[decision:C] D-VIRADA** — em que escala se grava o aceite da violação da virada. Escolha: na
  trilha da escala cuja mutação a introduziu; como aparece com a mesma `key` dos dois lados (ADR
  4.2.0002 Decision 1), editar a vizinha depois não a re-pergunta. Degrau 1. Reversível: sim.

- **[decision:C] D-ROSTER** — completude dos fatos de staff no insumo. Escolha (corrigida): o use
  case monta os fatos com `list_active_members(tenant, unidade)` (quadro ativo inteiro) e
  `list_members(tenant, unidade, ids)` para os alocados (escala + vizinhas) e os alvos de
  `AssignEmployee`; registro alocado que staff **não** devolve NÃO vira inativo (seria a Alt D
  rejeitada do ADR 4.2.0002): o avaliador recusa fail-closed; leituras sem avaliação omitem o que não
  sabem nomear; a guarda reversa da 4.4 impede o estado. Teste de contrato do port (só o fake na
  4.3). Base: concept 4.2 §5.4; 4.2 technical §7 [finding]; ADR 4.1.0006 §2; ADR 4.2.0002 Alt D.
  Reversível: sim.

- **[decision:C] D-STAFFPORT** — forma do StaffReadPort. Escolha (corrigida): quatro leituras em
  lote, **todas com unidade no endereço** — `list_active_members(tenant, unidade)`,
  `list_members(tenant, unidade, ids)`, `list_members_of_user(tenant, unidade, user_id)`,
  `list_job_functions(tenant)`; DTO `StaffMember` de scheduling (id, unidade, nome, ativo, funções,
  carga `Decimal | None`, janelas). Sem listagem tenant-wide de registro (preserva a lei de staff
  employee_repository.py:33-36). O adapter (4.4) lê staff por fachada que **não autoriza** (o
  chamador autoriza). Consequência para a 4.4: o 1º `find_by_user_id` decide escopo e índice (ADR
  3.5.0004 Alt C). Base: doc §3.10.1; ADR 4.1.0006 §4; ADR 3.4.0007; LAYOUT §3; concept 3.7 §13.
  Reversível: sim.

- **[decision:C] D-AUDIT** — escala e trilha numa escrita só. Escolha: `ScheduleRepository.add/save`
  recebem `ScheduleChange` (quem=`user_id` do escopo; quando=`Clock.now()`; operações efetivas em
  ordem; violações aceitas; versão anterior); o adapter (4.4) grava estado+trilha numa transação;
  cada use case de escrita faz uma escrita só → dispensa unit of work. N operações do lote = N
  versões, 1 entrada. Degrau 5. Base: ADR 4.1.0001 §1; roadmap 4.4 DoD; ADR 2.6.0002 Decision 5 (PR
  #70). Reversível: sim.

- **[decision:C] D-NOW** — instantes de fora do domínio e o fuso. Escolha: nenhum use case da 4.3
  recebe instante absoluto nem o "agora" da unidade; queries recebem dias como `date` (recusando
  `datetime`); os limites de `RescheduleBand` são validados ingênuos e de minuto inteiro (pela
  construção de um `TimeRange`) antes de qualquer `operational_day_of` — fecha o achado M4 da 4.1; o
  port de fuso (ADR 4.1.0005) nasce com o 1º consumidor do "agora". Degrau 5. Base: 4.1 technical §7
  [finding]; ADR 4.1.0005 Implementation notes; overview §3. Reversível: sim.

- **[decision:C] D-CAL** — calendário sobre vários períodos. Escolha: `get_calendar(unidade,
  primeiro_dia, último_dia)` devolve o resumo das escalas que cruzam o recorte e as faixas cujo dia
  operacional cai nele, com alocações de ativos; recorte de até 42 dias (grade de mês de 6 semanas;
  sem fonte — degrau 5, racional declarado). Base: doc §3.7. Reversível: sim.

- **[decision:E] D-TERM** — limpar alocações futuras no desligamento. Escolha: não limpar. Base: ADR
  4.1.0006 Decision 1 e Decision 4 ("default: do not clear"). Reversível: sim.

- **[decision:C→P] D-INVISIBLE** — ESCALADO como fork P **D3** (ver §B do handoff-base e o bloco de
  needs-decision). A proposta inicial (remover automaticamente a alocação do invisível) foi derrubada
  pelo revisor: apaga o que o ADR 4.1.0006 manda preservar, reintroduz a cascata recusada em Q1 e
  desarma a guarda L-E5. Sem resposta: nada de remoção automática.

- **[decision:E] D-FEXC** — quando a alocação nasce com `function_exception`. Escolha (corrigida):
  `True` sse, no ato de alocar, a função da demanda não é detida pelo registro — **independente** de
  a política estar habilitada ou do modo (o sinal "visível na escala" do ADR 4.1.0003 (f) sobrevive à
  política desabilitada; o ADR 4.2.0001 §2 deixa o rótulo/contagem para 4.5/8.1). Com
  `function_mismatch` em `block`, a mudança é recusada na publicação. Base: ADR 4.1.0003 (f); ADR
  4.2.0001 Decision 2. Reversível: sim.

- **[decision:C] D-CONFIG** — mudança de dia de início/corte com escalas existentes. Escolha: vale só
  para períodos criados depois (a escala fotografa o calendário); sem migração na v1; criar escala
  sobre dia já coberto é recusado (dias disjuntos). Inalcançável na 4.3 (não há escrita de config).
  Consequências declaradas: trocar o dia de início deixa até 6 dias sem escala possível; corte mais
  tarde cria janela sem período — requisito para a Stage que criar a edição da config (finding).
  Base: ADR 4.1.0009 Decision 4; concept 4.1 §5 invariante 4. Reversível: sim.

- **[decision:C] D-REVERSE** — Stage em que staff consulta o port reverso. Escolha: **4.4** (dona da
  consulta e do wiring); a 4.3 não cria fachada/método sem consumidor; até lá registro removido vira
  "ausente" (fail-closed, D-ROSTER). Base: ADR 4.1.0006 Implementation notes. Reversível: sim.

- **[decision:C] D-PAST** — escalas anteriores. Escolha: `list_past_schedules(unidade, antes_de,
  limite)` — último dia < `antes_de`, mais recente primeiro, `1 ≤ limite ≤ 52`. Base: overview §3.
  Reversível: sim.

- **[decision:C] D-NOOP** — operação sem efeito no lote. Escolha: operação que não muda nada (as
  quatro mutações idempotentes devolvem `self`; `ChangeDemandQuantity` com o mesmo N — fork P **D2**)
  não entra na trilha nem conta na versão; lote sem operação efetiva não grava. Base: ADR 4.1.0009
  Decision 3; 4.1 technical §7 [finding]. Reversível: sim.

- **[decision:C] D-ERRWRAP** — erro de domínio de uma operação do lote. Escolha: sobe como está (sem
  embrulho); o lote inteiro é recusado e nada é gravado. Base: docstring de
  `staff/application/errors.py`. Reversível: sim.

## D. Rascunho COMPLETO do concept (pronto para gravar em docs/stages/4.3-scheduling-application/concept.md, faltando só D1/D2/D3 em §7)

<!-- CONCEPT-DRAFT-BEGIN -->
---
title: Concept — Use cases da escala
description: A camada application do BC scheduling — sete use cases (criar, avaliar, publicar, ler a escala, calendário, escalas anteriores, minha escala), o protocolo de publicação com aceite consciente sobre o antes × depois da avaliação, a autorização em cada use case e os quatro ports de saída que a 4.4 implementa
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; antes de acrescentar use case, operação de edição, port ou regra de aceite no BC scheduling; quando a 4.4 (persistência), a 4.5 (HTTP), a 4.6 (e-mail) ou o Step 5 consumirem estes contratos
keywords: [concept, scheduling-application, use-case, publicar, avaliar, aceite-consciente, violacao-introduzida, lote-de-operacoes, versao, concorrencia-otimista, trilha-de-auditoria, staff-read-port, access-guard, minha-escala, calendario, escalas-anteriores, reconciliacao-na-leitura]
status: draft
created_at: 2026-10-21
updated_at: 2026-10-21
stage_id: 4.3-scheduling-application
stage_title: Use cases da escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.2-validation-policies]
---

# Concept — Stage 4.3 — Use cases da escala

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e as decisões que fecham as
> lacunas endereçadas a ela. O plano executável fica no [`technical.md`](./technical.md).
>
> **Base teórica obrigatória:** este concept **aplica** a teoria de
> [`shift-scheduling.md`](../../domain/scheduling/shift-scheduling.md) (`accepted`) e os ADRs
> 4.1.0001–4.1.0012 e 4.2.0001–4.2.0002 — consome, não reabre. O agregado é o da Stage 4.1
> ([`concept.md`](../4.1-scheduling-domain/concept.md)); o avaliador é o da 4.2
> ([`concept.md`](../4.2-validation-policies/concept.md)).
>
> **Lacunas que chegam a esta Stage** (doc §6, tabela consolidada; §7 dos technicals da 4.1 e da
> 4.2; §13 do concept 3.7, em voo): unidade de salvamento; protocolo do aceite; identidade da
> violação para o aceite (fechada pela 4.2, consumida aqui); re-pergunta quando a medida piora; em
> que escala se grava o aceite da virada; completude do quadro no insumo; DTO próprio e consulta
> em lote do `StaffReadPort`; ator → registros ("minha escala"); calendário sobre várias escalas;
> mudança de dia de início/corte com escalas existentes; limpar ou não as alocações futuras no
> desligamento; Stage em que staff passa a consultar o port reverso; instante de fora do domínio
> (`operational_day_of`); `change_demand_quantity` com o mesmo N; violação induzida por mudança de
> staff; autorização na application (3.7). Todas fecham em §7. **Três** eram de produto e foram
> respondidas pelo orquestrador, por delegação do sponsor (§7 D1, D2, D3); as demais foram
> resolvidas por evidência interna ou convenção (skill `evidence-resolution`), com o degrau
> registrado.

## 1. Escopo

### Dentro do escopo

- **Sete use cases** (os ports primários — LAYOUT §5, ADR 0.0.0006), um por arquivo em
  `features/scheduling/application/use_cases/`:
  - `create_schedule` — cria a escala de uma unidade para um período alinhado ao calendário do
    restaurante (fotografado na criação);
  - `evaluate_schedule` — aplica, em memória, um lote de operações de edição e devolve a escala
    resultante com as violações, separando as **introduzidas** pela mudança (a avaliação ao vivo);
  - `publish_schedule` — o mesmo lote, com a versão vista pelo editor e os aceites: recusa o que
    introduz `block`, pede aceite do que introduz `warn`, e grava (salvar = publicar);
  - `get_schedule` — a escala vigente com as violações atuais (a tela do editor e a leitura do RH);
  - `get_calendar` — as faixas de um recorte de dias (dia/semana/mês), através das escalas que ele
    cruza;
  - `list_past_schedules` — as escalas anteriores a um dia, como referência;
  - `get_my_schedule` — as alocações do próprio ator, nas unidades em que tem registro.
- **O protocolo de publicação** (§5.5–§5.10): lote de operações nomeadas aplicado atomicamente,
  avaliação antes × depois, violação introduzida, aceite por `key` + medida, no-op, trilha.
- **Quatro ports de saída** em `application/ports/out/`: `ScheduleRepository`,
  `ScheduleConfigRepository`, `StaffReadPort` e `AccessGuard` (este, de scheduling — §1
  Divergências 2), com as leis nas docstrings.
- **DTOs** (`dtos/{commands,queries,results}.py`), com os mapeadores de result num sítio só
  (`scripts/check_layout.py` regras 7 e 8).
- **Erros da application** (`application/errors.py`), filhos de `SchedulingError`.
- **Contrato de pureza** `scheduling-application-purity` no `.importlinter` — previsto desde a
  4.1 para "o primeiro use case".
- **Fakes** dos quatro ports em `tests/fakes/features/scheduling/`, **suítes de lei** dos ports
  de dados em `tests/contract/features/scheduling/` (só o fake roda nesta Stage; a 4.4 acrescenta
  o adapter real à parametrização — precedente 3.5) e testes unitários dos use cases com fakes.

### Fora do escopo (explicitamente)

- **Persistência** (tabelas, migration, mapper, a trilha de auditoria no banco, a checagem de
  versão em SQL), o **adapter** do `StaffReadPort` (e a fachada de staff que ele consumir) e o
  **wiring** no `composition_root` — Stage 4.4.
- **HTTP** — rotas, schemas, status das recusas, o texto de cada violação, o membro das
  permissões no enum de identity e o mapa de papéis, o `authenticate` do guard — Stage 4.5.
- **E-mail** (4.6), **imagem** (4.7), **auto-preenchimento** (Step 5).
- **Editar a configuração do restaurante** (validação, dia de início, corte): nenhum bloco do
  roadmap lista o use case de escrita — [finding] para a 4.5 (§13). A 4.3 só **lê** a
  configuração.
- **O port de fuso da unidade** (ADR 4.1.0005): nenhum use case desta Stage precisa do "agora" da
  unidade (§7 D-NOW) — nasce com o primeiro consumidor.
- **A guarda de remoção definitiva** (port de consulta reverso em staff, ADR 4.1.0006 §3) — 4.4
  (§7 D-REVERSE).
- **Página de histórico de funcionários**, cópia de escala anterior, troca de turno — evolução
  (doc §5).

### Vínculo com o roadmap

Terceira Stage do **Step 4 — Escala manual publicável**: entrega a parte "editar demanda e
alocações com avaliação ao vivo, aceitar warn, publicar, consultar" do resultado de negócio, sem
I/O real. Ver `roadmap.md` §"Stage 4.3 — `4.3-scheduling-application`" e `overview.md` §3
("Validações parametrizáveis… Avisos ao vivo… o editor corrige ou aceita conscientemente";
"salvar = publicar"; "funcionário com login consulta a própria escala"; "Fácil visualização das
escalas anteriores ao montar a nova").

### Divergências declaradas em relação ao bloco 4.3 do roadmap

1. **Use cases.** O bloco lista `{create_schedule, update_demand, assign_employee,
   evaluate_schedule, publish_schedule, get_calendar, list_past_schedules, get_my_schedule, ...}`.
   Sob salvar = publicar (ADR 4.1.0001 §1) não há "publicar" separado de "editar": as 11 mutações
   do agregado viram **operações** de um lote que `evaluate_schedule` avalia e
   `publish_schedule` grava (§7 D-SAVE). Entra `get_schedule` (a leitura da escala com versão e
   violações, que o editor precisa para editar). `update_demand` e `assign_employee` não existem
   como use case: são as operações `DeclareDemand`/`ChangeDemandQuantity`/`WithdrawDemand` e
   `AssignEmployee`/`UnassignEmployee`.
2. **Contratos introduzidos.** Além dos três ports do bloco, entra o `AccessGuard` **de
   scheduling** (§7 D-AUTH): a application autoriza o próprio alvo, como a 3.7 fez em staff.
3. **`arquivos_a_modificar` deixa de ser `[]`:** `.importlinter` (contrato de pureza da
   application), `tests/unit/test_status_map.py` (piso de contagem dos erros do BC) e, no
   fechamento, a nota datada no doc de domínio e o roadmap.

### Divergências declaradas em relação ao doc de domínio e aos ADRs

4. **Invariantes de §3.5, §3.6.6 e §3.6.7 valem para o que a escala introduz** — confirmado (§7
   D1): a violação induzida por mudança em staff aparece ao vivo e não trava edição alheia a ela.
   A nota datada da 4.2 no doc (§6) já o antecipava; a desta Stage registra a decisão. A **segunda
   fonte** da mesma classe — uma configuração de validação alterada depois — recebe o mesmo
   tratamento (pré-existente, mostrada, nunca bloqueante numa mudança que não a introduziu), e é
   requisito declarado para a Stage que criar a edição da configuração.
5. **ADR 4.1.0005, Implementation notes** ("a read port in scheduling (4.3)"): o port de fuso
   **não** nasce aqui (§7 D-NOW). A forma dele (pelo `AuthorizedScope` ou por um port próprio) e a
   Stage da coluna `Unit.timezone` continuam abertas, com o primeiro consumidor.
6. **ADR 4.1.0006 §3** previa a guarda reversa "the Stage that wires it is a concept gap
   (4.3/4.4)": fica na **4.4** (§7 D-REVERSE).
7. **ADR 3.7.0001 §3** ("the returned `AuthorizedScope` is not read by any use case") é adotado
   para o **endereço**: o use case opera no alvo do command, não no escopo. A divergência é que
   esta Stage **lê** do escopo o `user_id` (o "quem" da trilha e o "eu" de "minha escala") — não
   como endereço, mas como o sujeito autenticado que o ADR 0.0.0005 manda derivar do token. O
   modelo de ameaça do 3.7.0001 continua valendo: o guard não autentica o ator, logo "ninguém
   nomeia usuário alheio" e "nega sozinha para qualquer driver" valem hoje só para o driver HTTP;
   o resto é [finding] da Stage que criar o primeiro driver não-HTTP.

## 2. Objetivo da Stage

Ao final, sem I/O real, um gerente pode — pela application do BC scheduling, com fakes nos ports
— criar a escala da semana, editar faixas, demandas e alocações num lote avaliado ao vivo, ter
recusada a mudança que introduz violação `block`, publicar com aceite consciente a que introduz
`warn`, e ler a escala, o calendário e as escalas anteriores; o funcionário lê as próprias
alocações — tudo autorizado pelo próprio use case e sem nenhum registro inativo à vista.

## 3. Contexto e premissas

### Contexto

- **Salvar = publicar** (ADR 4.1.0001 §1): cada gravação é a escala vigente. **`block` recusa a
  mutação; `warn` é aceito no ato de salvar**, e o aceite é auditado.
- **Concorrência otimista por versão** (ADR 4.1.0001 §2): toda mutação carrega a versão vista;
  escala mudada ⇒ recusa e o cliente recarrega ou cancela. O contador vive no domínio (ADR
  4.1.0009 Decision 3); a coluna e a comparação atômica são da 4.4. **Limite declarado:** a versão
  protege só a escala mutada; duas publicações simultâneas em semanas adjacentes podem gravar, cada
  uma contra o estado antigo da outra, uma violação de fronteira que nenhuma viu (write skew) — a
  próxima avaliação de qualquer das duas a mostra ao vivo; mitigação forte é [finding] 4.4.
- **O avaliador descreve, não recusa** (concept 4.2 §5.1): quem recusa e quem pergunta é esta
  Stage, comparando as violações **antes × depois** pela `key` (ADR 4.2.0002 §5).
- **Reconciliação na leitura** (ADR 4.1.0006): nada é escrito em scheduling quando staff desliga
  alguém; toda leitura consulta o estado atual pelo `StaffReadPort` e omite o inativo — nem as
  alocações passadas dele aparecem.
- **BCs independentes** (LAYOUT §3; `bc-independence`): scheduling não importa staff nem
  identity; lê staff por port próprio, com adapter na 4.4 sobre uma fachada de staff que **não
  autoriza** (ADR 3.5.0001; o chamador autoriza).
- **Fail-closed na application** (3.7, em voo — ADR 3.7.0001, PR #71): o use case autoriza o
  alvo que o command declara antes de qualquer outra instrução. Esta Stage segue o mesmo desenho
  **sem depender** do PR: o port é de scheduling e as âncoras são as já mergeadas (LAYOUT §5, ADR
  2.2.0002, ADR 0.0.0005).

### Premissas

- Volume do piloto (ASSUM-4/5): uma unidade, dezenas de registros, 7 dias — avaliar a escala
  inteira duas vezes por operação de lote é aceitável; nada é indexado.
- A configuração é do tenant (ADR 4.1.0003); um tenant que nunca a gravou usa os defaults de
  domínio (`OperationalCalendar.default()`, `ValidationConfig.default()`).
- O cliente (4.5) envia os dias como `date` e os limites de faixa em wall-clock ingênuo da
  unidade (precedente ADR 3.6.0003: valor com offset é recusado, não convertido).
- O cliente gera os ids das entidades internas que cria num lote (§7 D-IDS) e os valida na borda
  (ADR 3.6.0002).

### Dependências

- `4.2-validation-policies` (`done`, PR #66): `evaluate`, `EvaluationContext`, `Violation`/
  `ViolationKey`, `ValidationConfig`/`PolicyKind`/`EnforcementMode`, `EmployeeFacts`/
  `UnavailabilityWindow`.
- `4.1-scheduling-domain` (`done`, PR #63): `Schedule` e as 11 mutações, `TimeRange`,
  `OperationalCalendar`, `SchedulePeriod`, `DemandQuantity`, ids, `SchedulingError` e as 22
  exceções.
- `shared/application/ports/out`: `Clock`, `IdGenerator`.

## 4. Contratos

### Introduzidos

Todos em `features/scheduling/application/`. Nomes em inglês; valores de string em minúsculas.

#### Port `AccessGuard` (`port-out`, `ports/out/access_guard.py`)

Actor = object (credencial verificada, opaca para scheduling).
Permissões como `str`: `PERMISSION_VIEW_SCHEDULE = "view_schedule"` (ler),
`PERMISSION_MANAGE_SCHEDULE = "manage_schedule"` (criar/avaliar/publicar),
`PERMISSION_VIEW_OWN_SCHEDULE = "view_own_schedule"` (minha escala).
`AuthorizedScope(frozen)`: `tenant_id: TenantId`, `unit_id: UnitId | None`, `user_id: str` (o
sujeito autenticado — id de login em identity).
`AccessGuard(Protocol)`: `authorize(actor, permission, *, tenant_id: str, unit_id: str | None =
None) -> AuthorizedScope`.

Leis (docstring do port, provadas contra o fake):
- **L-SG1** — a recusa sai crua (o tipo da exceção não é fixado — vocabulário do outro BC).
- **L-SG2** — tenant confirmado: o escopo tem o `tenant_id` pedido, nunca vazio; ator de outro
  tenant ou sem tenant é negado.
- **L-SG3** — uma autorização por alvo: autorizar uma unidade não autoriza outra.
- **L-SG4** — o sujeito vem do token: `user_id` é o do ator autenticado, nunca vazio, nunca
  tirado do pedido.

#### Port `StaffReadPort` (`port-out`, `ports/out/staff_read_port.py`)

`StaffMember(frozen)` — DTO próprio de scheduling (doc §3.10.1): `employee_id`, `unit_id`,
`display_name`, `active: bool`, `job_function_ids: frozenset[JobFunctionId]`,
`contracted_weekly_hours: Decimal | None` (None = sob demanda),
`unavailabilities: tuple[UnavailabilityWindow, ...]`.
`JobFunctionEntry(frozen)`: `job_function_id`, `name`.
`StaffReadPort(Protocol)`:
- `list_active_members(tenant_id, unit_id) -> tuple[StaffMember, ...]`
- `list_members(tenant_id, unit_id, employee_ids: frozenset[EmployeeId]) -> tuple[StaffMember, ...]`
- `list_members_of_user(tenant_id, unit_id, user_id: str) -> tuple[StaffMember, ...]`
- `list_job_functions(tenant_id) -> tuple[JobFunctionEntry, ...]`

Leis (contrato): L-ST1 endereço (nunca registro de outra unidade/tenant); L-ST2 quadro completo
(`list_active_members` = todos os ativos da unidade, só eles); L-ST3 lote (um `StaffMember` por id
que é da unidade, ativo ou não; id desconhecido/de outra unidade omitido); L-ST4 vínculo de login
(`list_members_of_user` = registros da unidade vinculados ao user_id, ativos ou não, só eles);
L-ST5 valores (carga `Decimal` finito >0 ou None; janelas `UnavailabilityWindow`; nome verbatim);
L-ST6 catálogo (todas as funções do tenant, só elas). Sem ordem garantida (o use case ordena).

#### Port `ScheduleRepository` (`port-out`, `ports/out/schedule_repository.py`)

`ScheduleChange(frozen)` — o registro de uma mudança (a entrada da trilha, 4.4): `author_user_id:
str` (quem = AuthorizedScope.user_id), `occurred_at: datetime` (quando = Clock.now()),
`previous_version: int | None` (None na criação), `operations: tuple[ScheduleOperation, ...]` (o
quê: operações efetivas, em ordem), `acknowledged: tuple[Violation, ...]` (os warn introduzidos e
aceitos).
`ScheduleRepository(Protocol)`:
- `add(schedule, change) -> None`
- `save(schedule, expected_version: int, change) -> None`
- `find_by_id(tenant_id, unit_id, schedule_id) -> Schedule | None`
- `list_in_range(tenant_id, unit_id, first_day: date, last_day: date) -> tuple[Schedule, ...]`
- `list_ending_before(tenant_id, unit_id, before: date, limit: int) -> tuple[Schedule, ...]`

Leis (a 4.4 as implementa em Postgres): L-SC1 `add` inserção (id de escala já gravado ⇒
`IdentifierInUseError`); L-SC2 dias disjuntos (`add` cujo período cruza dia de outra escala do
mesmo (tenant,unidade) ⇒ `SchedulePeriodTakenError` — impõe a invariante 4 da 4.1; atômica no
adapter, não índice único em first_day; limite de concorrência declarado — ADR 3.2.0001); L-SC3
estado e trilha juntos (atômicos); L-SC4 `save` otimista (inexistente ⇒ `ScheduleNotFoundError`;
versão ≠ `expected_version` ⇒ `ScheduleVersionConflictError` com a atual; id interno novo já usado
por outra escala ⇒ `IdentifierInUseError`; ordem endereço→versão→ids); L-SC5 endereço de três
partes (outro tenant/unidade ⇒ None); L-SC6 recorte (`list_in_range` = escalas que cruzam
[first_day,last_day], por first_day); L-SC7 anteriores (`list_ending_before` = last_day<before, da
mais recente, ≤ limit); L-SC8 fidelidade (lido == gravado; trilha observável na ordem).

#### Port `ScheduleConfigRepository` (`port-out`, `ports/out/schedule_config_repository.py`)

`SchedulingSettings(frozen)`: `calendar: OperationalCalendar`, `validation: ValidationConfig`.
`find_settings(tenant_id) -> SchedulingSettings | None`. L-CF1: devolve a config gravada do
tenant, ou None (nunca a de outro tenant); os defaults são do use case, num sítio só (§5.12).

#### DTOs (`dtos/`)

**Operações** (`dtos/commands.py`) — uma por mutação do agregado; `ScheduleOperation` é a união:
`EnableBand(band_id, time_range: TimeRange)`; `RescheduleBand(band_id, start, end: datetime)`;
`RedeclareBandBreak(band_id, break_minutes)`; `DisableBand(band_id)`;
`DeclareDemand(demand_id, band_id, job_function_id, quantity: DemandQuantity)`;
`ChangeDemandQuantity(demand_id, quantity)`; `WithdrawDemand(demand_id)`;
`AssignEmployee(assignment_id, demand_id, employee_id, counts_toward_workload=True)`;
`UnassignEmployee(assignment_id)`; `DeclareWorkloadCounting(assignment_id, counts)`;
`DeclareAllocationBreak(assignment_id, break_minutes: int | None)`. Os ids de criação (band_id de
EnableBand, demand_id de DeclareDemand, assignment_id de AssignEmployee) vêm do cliente (§7 D-IDS).

**Commands e queries** — ator como 1º campo (`field(repr=False)`) + endereço (tenant_id,
unit_id[, schedule_id]):
`CreateScheduleCommand(actor, tenant_id, unit_id, first_day: date)`;
`PublishScheduleCommand(actor, tenant_id, unit_id, schedule_id, expected_version: int, operations,
acknowledgements: tuple[ViolationAcknowledgement, ...] = ())`;
`ViolationAcknowledgement(key: ViolationKey, observed: Decimal)`;
`EvaluateScheduleQuery(actor, tenant_id, unit_id, schedule_id, expected_version: int, operations)`;
`GetScheduleQuery(actor, tenant_id, unit_id, schedule_id)`;
`GetCalendarQuery(actor, tenant_id, unit_id, first_day, last_day)`;
`ListPastSchedulesQuery(actor, tenant_id, unit_id, before: date, limit: int = 10)`;
`GetMyScheduleQuery(actor, tenant_id, unit_id, first_day, last_day)`.

**Results** (`dtos/results.py`, cada classe num sítio só): `ScheduleSummaryResult`,
`AssignmentResult`, `DemandResult` (só alocações de ativos), `BandResult`, `ScheduleResult`
(com `violations`), `EvaluationResult(schedule, blocking, warnings)` (blocking/warnings = as
**introduzidas**), `CalendarResult`, `MyShiftResult`, `MyScheduleResult`. `Violation`,
`ViolationKey`, `TimeRange`, `DemandQuantity`, `Weekday` trafegam por licença do LAYOUT §7; nenhum
DTO carrega entidade.

#### Use cases (`use_cases/`)

| Use case | Entrada → saída | Permissão (alvo) |
|---|---|---|
| `CreateScheduleUseCase` | CreateScheduleCommand → ScheduleSummaryResult | manage_schedule (tenant, unidade) |
| `EvaluateScheduleUseCase` | EvaluateScheduleQuery → EvaluationResult | manage_schedule (tenant, unidade) |
| `PublishScheduleUseCase` | PublishScheduleCommand → ScheduleResult | manage_schedule (tenant, unidade) |
| `GetScheduleUseCase` | GetScheduleQuery → ScheduleResult | view_schedule (tenant, unidade) |
| `GetCalendarUseCase` | GetCalendarQuery → CalendarResult | view_schedule (tenant, unidade) |
| `ListPastSchedulesUseCase` | ListPastSchedulesQuery → tuple[ScheduleSummaryResult, ...] | view_schedule (tenant, unidade) |
| `GetMyScheduleUseCase` | GetMyScheduleQuery → MyScheduleResult | view_own_schedule (tenant, unidade) |

Avaliar e publicar compartilham o protocolo num módulo privado (`use_cases/_publish.py`,
precedente `_invitation.py`); a montagem do insumo também.

#### Erros (`application/errors.py`, filhos de `SchedulingError`)

`ScheduleNotFoundError` (NotFoundError), `ScheduleVersionConflictError` (carrega a atual),
`SchedulePeriodTakenError`, `IdentifierInUseError`, `BlockingViolationsError` (carrega as
violações), `UnacknowledgedViolationsError` (carrega as pendentes), `StaffMemberNotFoundError`
(NotFoundError), `InactiveStaffMemberError`, `JobFunctionNotFoundError` (NotFoundError),
`InvalidScheduleRequestError`.

### Consumidos

Domínio 4.1 e 4.2 (os erros de domínio sobem sem embrulho, §5.11); `Clock` e `IdGenerator` de
shared; dados de staff por `StaffReadPort`; sujeito e decisão de acesso por `AccessGuard` (os dois
implementados fora de scheduling, 4.4/4.5).

## 5. Invariantes e regras

1. **Autorização primeiro** (§7 D-AUTH): 1ª instrução de todo `execute` é
   `self._guard.authorize(command.actor, <permissão>, tenant_id=..., unit_id=...)`; nenhum port
   tocado, nenhum id gerado, nenhum relógio lido, nenhuma validação de pedido antes da decisão. O
   escopo **não** é fonte de endereço (o use case opera no endereço do command); do escopo lê só o
   `user_id`.
2. **Endereço de três partes** (ADR 3.4.0007): escala de outra unidade/tenant é não encontrada.
3. **Criar**: período de 7 dias a partir de `first_day`, alinhado ao calendário **atual** do
   tenant (recusa o desalinhado com `InvalidSchedulePeriodError`); nasce vazia, versão 1, com o
   calendário fotografado; dia já coberto ⇒ `SchedulePeriodTakenError` (use case + L-SC2);
   `ScheduleChange` sem operações (previous_version=None).
4. **Versão**: avaliar e publicar recusam com `ScheduleVersionConflictError` quando
   `expected_version` ≠ carregada; `save` recusa de novo se a gravada mudou (L-SC4); sobrescrever
   não é oferecido.
5. **Lote atômico**: operações aplicadas em ordem sobre a escala carregada, em memória; a 1ª que
   falha recusa o lote com o erro dela, nada gravado. Só o estado **final** é avaliado (estado
   intermediário inválido nunca é gravado nem visto).
6. **Violação introduzida**: avalia antes (carregada) e depois (final), com as mesmas vizinhas,
   fatos e config. Introduzida sse (a) `key` não está no antes, ou (b) está, a política é
   **ordinal** (descanso, tetos, carga, sobre-cobertura, sobreposição, indisponibilidade — 4.2
   §5.9) e |observed−limit| cresceu. `function_mismatch` e `break_divergence` só por `key`.
   **Sobre-cobertura:** introduzida sse não havia sobre-cobertura da demanda no antes, entrou
   alocação fora do conjunto do antes, ou o excedente cresceu — desalocar um excedente sem chegar a
   N não re-pergunta nem recusa. Pré-existentes (de qualquer origem — mudança em staff D1, ou
   config alterada) são mostradas e nunca recusam nem pedem aceite numa mudança que não as
   introduziu.
7. **Recusar ou pedir aceite** (só publish): `block` introduzida ⇒ `BlockingViolationsError`;
   senão `warn` introduzida sem aceite ⇒ `UnacknowledgedViolationsError` (pendentes). Um
   `ViolationAcknowledgement` cobre a `warn` de mesma `key` cuja medida não é pior; aceite que não
   cobre nada é ignorado; ordem `block` antes de `warn`. `evaluate` não recusa: devolve as mesmas
   em blocking/warnings.
8. **Alocar**: registro da unidade e **ativo** (`StaffMemberNotFoundError` inexistente/de outra
   unidade; `InactiveStaffMemberError` desligado). `function_exception = True` sse a função da
   demanda não é detida pelo registro **no ato de alocar**, independente de a política estar
   habilitada ou do modo (§7 D-FEXC) — com `function_mismatch` em `block` a mudança é recusada na
   publicação.
9. **Alocação invisível × remoção** — ver §7 D3 (resposta do orquestrador).
10. **No-op** (§7 D-NOOP/D2): operação que não muda nada não entra na trilha nem conta na versão;
    lote sem operação efetiva não grava.
11. **Erros de domínio sobem como são** (§7 D-ERRWRAP).
12. **Insumo completo** (§7 D-ROSTER): fatos do quadro ativo inteiro (`list_active_members`) +
    `list_members` para os alocados (escala+vizinhas) e os alvos de `AssignEmployee`; registro
    alocado que staff **não** devolve NÃO vira inativo — o avaliador recusa fail-closed (Alt D
    rejeitada do ADR 4.2.0002); a config é `find_settings(tenant)` ou os defaults, num sítio só.
13. **Vizinhas** (ADR 4.2.0002 §1): a anterior e a seguinte são as da unidade cujo período cruza o
    dia antes do primeiro e depois do último (`list_in_range`); adjacentes pela partição dos dias.
14. **Reconciliação na leitura** (ADR 4.1.0006 §2): nenhum result traz alocação de registro
    inativo/ausente; nome de exibição do estado atual de staff.
15. **Instantes de fora do domínio** (§7 D-NOW): limites de `RescheduleBand` validados ingênuos e
    de minuto inteiro (pelo `TimeRange`) antes de qualquer `operational_day_of` — fecha M4 da 4.1;
    todo dia em query/command é `date`, não `datetime` (`InvalidScheduleRequestError`).
16. **Calendário** (§7 D-CAL): recorte com first_day ≤ last_day e até 42 dias; resumo das escalas
    que cruzam + as faixas cujo dia operacional (calendário fotografado de cada escala) cai no
    recorte, ordenadas por (dia, início, band_id).
17. **Escalas anteriores** (§7 D-PAST): last_day < before, mais recente primeiro, 1 ≤ limit ≤ 52.
18. **Minha escala** (§7 D-OWN): registros **ativos** vinculados ao user_id do escopo na unidade;
    alocações cujo dia cai no recorte (teto 42 dias), por (início, unit_id, assignment_id);
    registro inativo não tem "minha escala".
19. **Uma escrita por use case** (§7 D-AUDIT): create → add; publish → save (ou nenhuma, no lote
    sem efeito); estado e trilha atômicos no port (L-SC3); sem unit of work.
20. **Ordem determinística dos results**: faixas por (dia, início, id); demandas por (função, id);
    alocações por (nome, id); violações na ordem do avaliador.

## 6. Casos de erro e exceções

Na ordem em que podem ocorrer: recusa do guard (crua, L-SG1) → `InvalidScheduleRequestError`
(dia datetime; recorte invertido/>42; limit fora de [1,52]) → `ScheduleNotFoundError` →
`ScheduleVersionConflictError` → `InvalidSchedulePeriodError` (domínio, desalinhado) →
`SchedulePeriodTakenError` → erro de domínio da operação (cru) → `InvalidTimeRangeError` (limites
com fuso/segundos) → `StaffMemberNotFoundError` → `InactiveStaffMemberError` →
`JobFunctionNotFoundError` → `BlockingViolationsError` → `UnacknowledgedViolationsError` →
`IdentifierInUseError`. Violação de política não é exceção em evaluate/leituras: é dado.

## 7. Decisões técnicas relevantes

> Registro no formato da skill `evidence-resolution` §5. Âncoras internas (conferidas por agente
> independente). As decisões E/C detalhadas estão na §C deste handoff; aqui ficam os forks P.

### D1 — Violação induzida por mudança em staff (P — orquestrador, 2026-10-21)
- **O quê:** <PENDENTE — resposta do orquestrador; recomendação do executor: (a) mostrar ao vivo e
  a gerente corrige>.

### D2 — `change_demand_quantity` com o mesmo N (P — orquestrador, 2026-10-21)
- **O quê:** <PENDENTE; recomendação: (b) no domínio, alinhando ADR 4.1.0009 Decision 3>.

### D3 — Desabilitar faixa cuja única alocação é de desligado invisível (P — orquestrador, 2026-10-21)
- **O quê:** <PENDENTE; recomendação: (b) recusar devolvendo os ids das alocações de desligado para
  a gerente desalocar no mesmo lote, sem nomes>.

(As decisões C — D-AUTH, D-PERM, D-OWN, D-SAVE, D-IDS, D-ACK, D-VIRADA, D-ROSTER, D-STAFFPORT,
D-AUDIT, D-NOW, D-CAL, D-TERM, D-FEXC, D-CONFIG, D-REVERSE, D-PAST, D-NOOP, D-ERRWRAP — entram aqui
com fonte e degrau, do §C deste handoff. Cada decisão com alternativa real descartada vira ADR:
4.3.0001 publicação/aceite; 4.3.0002 AccessGuard da application; 4.3.0003 StaffReadPort e insumo
fail-closed; 4.3.0004 lote com ids do cliente e escrita única.)

## 8. Integrações

- **4.4:** implementa `ScheduleRepository` (tabelas, versão atômica, ids internos, trilha a partir
  de `ScheduleChange`), `ScheduleConfigRepository`, o adapter do `StaffReadPort` (fachada de staff
  que não autoriza), os tradutores do `AccessGuard` no composition root; acrescenta os adapters
  reais às suítes de contrato; liga a guarda reversa de staff (D-REVERSE); o 1º `find_by_user_id`
  decide escopo e índice do user_id (ADR 3.5.0004 Alt C); mitigação do write skew de fronteira.
- **4.5:** rotas por use case; status das recusas (corpo de `BlockingViolationsError`/
  `UnacknowledgedViolationsError` = as violações; o de `ScheduleVersionConflictError` = a versão
  atual); texto das violações; permissões e mapa de papéis em identity (com `view_own_schedule`
  autorizável por unidade); `authenticate`; UX de publicar; formato UUID canônico dos ids de
  criação na borda; a desativação de conta que a 1ª permissão de auto-serviço exige (ADR 3.5.0003
  §5).
- **4.6:** e-mail é efeito de publish depois do save; um lote = uma publicação.
- **Step 5:** "aplicar" do auto-fill pode ser um lote de `AssignEmployee` por este protocolo.
- **staff/identity:** nenhuma integração de código — só ports.

## 9. Modelo de dados

Fluxo (sequência) de `publish_schedule`: comando → authorize(manage_schedule, tenant, unidade) →
escopo (user_id) → find_by_id + list_in_range (vizinhas) → list_active_members + list_members (+
catálogo) → aplica operações, avalia antes × depois, introduzidas → BlockingViolationsError |
UnacknowledgedViolationsError | save(escala, versão vista, ScheduleChange) → ScheduleResult (nova
versão). Fluxo da application, não schema (persistência é da 4.4).

## 10. Riscos e mitigações

(ver §10 do rascunho: autorizar antes de ler — propriedade sobre a pasta + teste estrutural;
aceite que não casa — ids do cliente + e2e avaliar→publicar; re-pergunta na piora da
sobre-cobertura; fato faltando — fail-closed; faixa impossível de desabilitar — D3; fake × real —
contrato; write skew — limite declarado; permissão de "minha escala" exigir unidade — declarado
para a 4.5.)

## 11. Critérios de aceitação

CA1 criar alinhado + recusa do desalinhado + dia já coberto; CA2 versão (conflito em avaliar e
publicar); CA3 autorização é a 1ª instrução (teste estrutural + guard que nega ⇒ nenhum port
tocado), por use case × permissão; CA4 lote atômico (1ª falha recusa tudo); CA5 avaliar devolve as
introduzidas (block/warn) sem gravar; CA6 publicar recusa block introduzida; CA7 publicar pede
aceite de warn introduzida e grava com o aceite; CA8 aceite não casa por medida melhor; CA9
sobre-cobertura: desalocar excedente sem chegar a N não re-pergunta, aumentar re-pergunta; CA10
alocar inativo/de outra unidade recusa; CA11 function_exception nasce pela não-detenção
(independente da config); CA12 no-op (as 5 idempotentes, inclusive change_demand_quantity) sem
versão/trilha; CA13 reconciliação na leitura (nenhum result com inativo/ausente); CA14 D3; CA15
calendário sobre várias escalas; CA16 fato faltando recusado (fail-closed); CA17 minha escala só do
ator, por unidade, sem inativo; CA18 escalas anteriores; CA19 instante de fora validado antes do
dia operacional; CA20 erros de domínio sobem crus; CA21 suítes de contrato dos ports (fake);
CA22 e2e avaliar→publicar com aceite casando pelos ids do cliente; CA23 contrato de pureza
`scheduling-application-purity`; CA24 `make check` verde + cobertura ≥ 90% por arquivo da Stage.

## 12. Checklist de validação interna

(todas "sim" ao fechar: contratos com assinatura; decisões com fonte; ADRs escritos; 4.2 done;
3–12 Tasks; riscos mitigados; findings 4.1/4.2/3.7 endereçados).

## 13. Questões em aberto

Nenhuma bloqueante após D1–D3. Findings com Stage candidata: edição da config de validação/
calendário (4.5 ou Stage própria) + requisito da mudança de dia-início/corte; formato UUID dos ids
na borda (4.5); desativação de conta na 1ª permissão de auto-serviço (4.5/identity, ADR 3.5.0003
§5); guarda reversa `has_allocations_for`/`has_demands_for` e mitigação do write skew (4.4);
índice/escopo de `find_by_user_id` (4.4); rótulo/contagem de exceção de função (4.5/8.1);
autenticação de ator fora da borda HTTP (Stage do 1º driver não-HTTP).

## 14. Referências

overview §3/§5/§6; roadmap Stage 4.3 e blocos 4.4–4.6; shift-scheduling.md §3.1/§3.4/§3.5/§3.7/
§3.9/§3.10/§4/§6; concept 4.1 §5/§8 e technical §7; concept 4.2 §5/§8 e technical §7; ADRs
0.0.0005, 0.0.0006, 2.2.0002, 3.4.0001, 3.4.0007, 3.5.0001, 3.5.0003, 3.5.0004, 3.6.0001, 3.6.0002,
4.1.0001, 4.1.0003, 4.1.0004, 4.1.0005, 4.1.0006, 4.1.0009, 4.2.0001, 4.2.0002; em voo 3.7.0001 (PR
#71), 2.6.0002 (PR #70).

<!-- CONCEPT-DRAFT-END -->

## E. Disposição dos 19 achados do decision-reviewer independente (todos já refletidos na §C)

1. D-OWN (major) CORRIGIDO: "própria" é unit-scoped; autoriza (tenant, unidade), passa pela
   visibilidade; nada entra em TENANT_WIDE_PERMISSIONS.
2. D-STAFFPORT (major) CORRIGIDO: `list_members_of_user(tenant, unidade, user_id)` — por unidade;
   consequência de índice/escopo para a 4.4 declarada (ADR 3.5.0004 Alt C).
3. D-ROSTER (major) CORRIGIDO: ausente NÃO vira inativo (Alt D rejeitada do ADR 4.2.0002); avaliador
   recusa fail-closed; guarda reversa é requisito da 4.4.
4. D-ACK (major) CORRIGIDO: sobre-cobertura casa por (política, demanda); desalocar excedente sem
   chegar a N não re-pergunta nem recusa.
5. D-IDS (major) CORRIGIDO: o use case confere os ids criados contra escala + vizinhas antes de
   avaliar → mesmo `IdentifierInUseError`.
6. D-IDS (major) CORRIGIDO: unicidade por (tenant, unidade) — não é oráculo; validador da borda não
   basta → finding 4.5 (UUID canônico).
7. D-INVISIBLE (major) ESCALADO como P D3.
8. D-CONFIG (major) CORRIGIDO (declarado): fotografia + só futuros; consequências e inalcançabilidade
   na 4.3 declaradas; requisito para a Stage da edição da config.
9. D-CONFIG (minor) CORRIGIDO: L-SC2 atômica na 4.4 (exclusão por intervalo de dias) + limite de
   concorrência declarado (ADR 3.2.0001).
10. write skew entre semanas adjacentes (minor) CORRIGIDO: limite declarado + finding 4.4.
11. violação induzida por mudança de config (minor) CORRIGIDO: 2ª origem isenta declarada + finding
    para a Stage da edição da config.
12. D-ACK pré-julgando D1 (minor) CORRIGIDO: redação neutra ("pré-existentes, de qualquer origem").
13. escopo como fonte do sujeito (minor) CORRIGIDO: divergência declarada do ADR 3.7.0001 §3 (escopo
    não é fonte de endereço; é a única fonte do sujeito) + modelo de ameaça (ator forjado em processo
    — só driver HTTP é coberto hoje).
14. ADR 3.5.0003 §5 (minor) CORRIGIDO: finding 4.5 (desativação de conta com a 1ª permissão de
    auto-serviço); get_my_schedule descarta inativo.
15. RH sem violações (minor) CORRIGIDO: get_schedule (família ler) traz as violações vivas.
16. D-FEXC (minor) CORRIGIDO: marca independente da config (preserva o sinal visível).
17. função removida (minor) CORRIGIDO: nome `None` nas leituras; `function_mismatch` ao vivo; guarda
    `has_demands_for` → finding 4.4.
18. granularidade da trilha (minor) CORRIGIDO: `ScheduleChange` entrega cada operação; a 4.4 decide a
    forma; N operações = N versões, 1 entrada.
19. teto de 42 dias (minor) CORRIGIDO: racional declarado (grade de mês de 6 semanas).

> Cobertura do reviewer: parou a leitura a pedido; não leu concept/technical 4.1 e 4.2, concept 3.7,
> LAYOUT, overview, ADRs 0.0.0005/0.0.0006/2.2.0002/2.6.0001/3.4.0001/3.4.0007/3.5.0001/3.6.0001 nem
> check_layout.py; leu 3.7.0001 e 2.6.0002 dos worktrees locais refactor-49/refactor-46 (confirmar que
> batem com origin). D-NOW/D-PAST/D-NOOP/D-TERM/D-ERRWRAP só parcialmente cruzados.

---

## DECISÃO DO ORQUESTRADOR sobre D1/D3 (2026-10-21, por delegação do sponsor — revogável pelo sponsor)

Com base na triagem por evidência (apêndice acima) e nas recomendações do agente evidence-resolution:

- **D1 → (a) mostrar e corrigir.** Nada muda em staff. A escala vigente pode conter a violação (inclusive `block` de indisponibilidade) até a gerente desalocar; os invariantes do doc §3.5/§3.6.6/§3.6.7 passam a valer só para o que a ESCALA introduz (nota datada). A nota datada do doc de domínio deve incluir, além de férias e função, a **edição de carga** (workload_policy) e a **recontratação** (ADR 4.1.0006) como origens da violação pré-existente.
- **D2 → (b) no-op no domínio** (já fechada como C pela evidência; `Schedule.change_demand_quantity` devolve `self` com o mesmo N; errata no concept 4.1 §5.16 + ADR da 4.3).
- **D3 → (b) recusar revelando contagem + ids das alocações de desligados** (sem nomes), para desalocação explícita no mesmo lote, auditada como ato da gerente; UX na 4.5. (c) auto-remover está EXCLUÍDA por evidência (reintroduz a cascata recusada em Q1 e desarma L-E5). Se o produto julgar que expor ids fere F7, reavaliar — mas (b)-sem-ids reabre o beco sem saída.

Essas três decisões fecham a §7 do concept-draft (§D acima). Próximo passo no Windows: gravar o concept com elas, Checkpoint A, technical, execução.

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

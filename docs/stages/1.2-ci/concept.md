---
title: Concept — Stage 1.2 — CI no GitHub Actions
description: Validar o pipeline de CI ponta-a-ponta no GitHub Actions e devolver ao caminho de PR a checagem de delta que o clone raso desligava em silêncio
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, ci, github-actions, gate, make-check, fetch-depth, clone-raso, freeze-secao-7, guard-main-source]
status: done
created_at: 2026-07-16
updated_at: 2026-07-16
stage_id: 1.2-ci
stage_title: CI no GitHub Actions
step_id: 1
step_title: Fundação do repositório
depends_on: [1.1-bootstrap]
---

# Concept — Stage 1.2 — CI no GitHub Actions

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **Validar o pipeline de CI ponta-a-ponta** com PR descartável real contra
  `develop`: erro intencional → CI vermelho; revertido → CI verde em < 5min
  (DoD do roadmap). O erro intencional é escolhido para exercitar **o gate que
  esta Stage conserta**, não um gate qualquer (§6 Decisão 2).
- **Devolver ao caminho de PR a checagem de delta que ele promete fazer.**
  O clone raso default do `actions/checkout` (`fetch-depth: 1`) esconde o
  commit-baseline `stage N.M: technical approved`, e a checagem 2 do
  `check_technical_postexec.py` — o freeze da §7 (CONVENTIONS §3.4) — é pulada
  em silêncio. O gate nunca disparou no runner, justamente na única janela em
  que ele existe para proteger: Stage `done` e ainda **não** mergeada, que é
  exatamente o que um PR de Stage é.
- **Exercitar o `guard-main-source`**, único job de `ci.yml` que nunca executou
  uma vez na história do repositório (fica SKIPPED em todo PR para `develop`).
- **Verdade do workflow:** o nome do step passa a listar a cadeia de targets
  que `make check` realmente roda.
- **Estender `docs/runbooks/validate-ci-gate.md`** — dever explícito da
  §Maintenance do runbook para toda Stage que endurece o gate de CI.

### Fora do escopo (explicitamente)

- **Deploy/CD** — Step 6 (non-goal do roadmap).
- **Cache de dependências** — otimização posterior (non-goal do roadmap).
- **Higiene de runner-minutes do `ci.yml`** — `concurrency` (cancelar runs
  redundantes) e `timeout-minutes` (teto por job; o default do GitHub é 360min).
  Mesma classe de otimização do non-goal "cache"; ambos viram um `[finding]`
  único. Nenhum é necessário para o DoD.
- **Levar o gate issue-first (`check_stage_issue.py`) para o caminho de PR**
  (plugar `GH_TOKEN` no `ci.yml`). Recusado por três razões estruturais — o gate
  é **repo-global** (uma Stage alheia em 3A reprovaria todo PR do repo), seu
  veredito dependeria de rede, e a cobertura já existe na varredura semanal
  ([`stage-issue-audit.yml`](../../../.github/workflows/stage-issue-audit.yml),
  com `GH_TOKEN` e `permissions: issues: read`). O cabeçalho daquele workflow
  **corrobora** o split, mas não é a razão da recusa e não prova que a ausência
  de token no `ci.yml` tenha sido deliberada. Ver §6 Decisão 1.
- **Promover `ruff format --check` a target de `make check`** — o hook
  `pre-commit` roda `ruff-format` e `make check` não; os dois gates locais
  discordam. É mudança do **gate local** (território da 1.1), não da ativação do
  CI; vira `[finding]`.
- **`mypy` sobre `scripts/`** (`make typecheck` roda só `mypy src/`) — `[finding]`.
- **Tornar qualquer check *Required*** — impossível no plano atual (repo privado
  em GitHub Free, sem branch protection — ADR 1.1.0002).
- **Issues #7 (drift de hooks) e #8 (`.gitattributes`)** — findings da 1.1 que
  ficaram em issues próprias; nenhum foi escalado para esta Stage.

### Vínculo com o roadmap

Fecha o Step 1 ("Fundação do repositório"), cujo resultado de negócio é
"projeto pronto para receber features com gates de qualidade automáticos
(lint, types, testes, layout) **locais e no GitHub**". A 1.1 entregou o lado
local; esta Stage valida o lado GitHub — e a palavra que carrega peso é
**automáticos**: um gate que se pula sozinho no runner não é automático.

## 2. Objetivo da Stage

O caminho de PR do CI passa a executar de fato a checagem de delta que ele
promete — sem checagem que se pula em silêncio — e essa equivalência está
demonstrada por um PR real, com o mesmo erro intencional passando antes da
correção e reprovando depois.

## 3. Contexto e premissas

### Contexto

O `ci.yml` veio do boilerplate e **já está verde** no runner Ubuntu: os PRs #4,
#5 e #11 rodaram `lint-and-test` com sucesso em ~22–33s. Esta Stage **não é
"consertar o CI que quebrou"** — o CI não quebrou. É validar o que nunca foi
validado e fechar o único ponto onde o runner faz menos do que diz fazer.

O CI do repositório tem um **padrão de duas metades**, declarado no cabeçalho de
[`stage-issue-audit.yml`](../../../.github/workflows/stage-issue-audit.yml):

1. **Caminho de PR** — rápido e determinístico, **sem rede no veredito**: valida
   o *delta da branch*. É `ci.yml`. (O runner *usa* rede para funcionar — PyPI,
   actions; o que ele não faz é **decidir** com base nela — I1.)
2. **Varredura agendada** — completa, **com rede** (`GH_TOKEN`), semanal, fora
   do caminho crítico: pega drift pós-merge. É `stage-issue-audit.yml`.

O defeito está **dentro da metade 1**: ela promete validar o delta da branch e,
no runner, **não valida** — porque o checkout é raso.

Verificação empírica local (Stage sintética `9.9`, `status: done` e **não
mergeada** — a única forma em que o freeze deve disparar; o mesmo patch fora dos
marcadores presente nos dois lados):

```
# A) histórico completo — simula fetch-depth: 0
$ python scripts/check_technical_postexec.py docs/stages/9.9-synthetic/technical.md
docs/stages/9.9-synthetic/technical.md: status=done mas há mudanças fora dos
marcadores post-execution (baseline: 9761ea38 `stage technical approved`):
  replace: baseline[4:5] (lines 5-5) vs current[4:5] (lines 5-5)
EXIT=1                                       # ← freeze dispara

# B) clone raso do MESMO commit — simula fetch-depth: 1
$ git clone --depth 1 --branch synth file://<repo> ab-shallow
$ git log --oneline | wc -l
1
$ grep -n "ERRO INTENCIONAL" docs/stages/9.9-synthetic/technical.md
5:# Technical — 9.9 ERRO INTENCIONAL FORA DA JANELA     # ← o patch ESTÁ lá
$ python scripts/check_technical_postexec.py docs/stages/9.9-synthetic/technical.md
OK — 1 arquivo(s) validado(s).
EXIT=0                                       # ← passa em silêncio
```

`_approved_commit_for()` procura o subject `stage N.M: technical approved`, não
o encontra no clone raso, retorna `None` → checagem 2 pulada. O próprio docstring
do script lista "clone raso" como limitação conhecida — o que faltou foi notar
que **o CI é um clone raso**.

> **O que este experimento prova e o que não prova.** Prova o **mecanismo**
> (raso ⇒ baseline invisível ⇒ verde) numa Stage `done` e não-mergeada. **Não**
> prova o ambiente: um evento `pull_request` faz checkout de `refs/pull/N/merge`,
> não de um clone local, e `_stage_is_merged()` precisa resolver `origin/develop`
> lá. Por isso o comportamento **no runner** não é assumido — é medido na Task de
> validação, com o mesmo erro intencional rodando antes e depois da correção
> (§6 Decisão 2). Uma Stage já mergeada (ex.: `1.1-bootstrap`) **não serve** de
> cobaia: ela é pulada nos dois mundos, por merge (I5).

### Premissas

- `actions/checkout@v4` com `fetch-depth: 0` traz histórico completo **e** as
  refs `refs/remotes/origin/*` — necessário para `_stage_is_merged()` resolver
  `origin/develop`. **Medida na Task de validação, não assumida.**
- Um evento `pull_request` faz checkout do merge ref, cujo histórico contém os
  commits da branch — logo o commit de aprovação é alcançável com histórico
  completo. **Idem: medida.**

### Dependências

- `1.1-bootstrap`: entrega o `make check` com a cadeia completa
  (`lint typecheck layout-check import-check lock-check docs-check test-gate`),
  o gate de cobertura `fail_under = 90` e o runbook `validate-ci-gate.md` que
  esta Stage estende. **Mergeada** em `develop` (`a0bf730 stage 1.1: complete`).

## 4. Invariantes e regras

- **I1 — Nenhum *veredito* do caminho de PR depende de serviço externo.** O
  runner **já** depende de rede para *poder* rodar (`actions/checkout`,
  `setup-python`, `setup-uv`, `uv sync` contra o PyPI): um outage de PyPI já
  reprova PR hoje. O invariante não é "sem rede" — é que nenhuma checagem pode
  **decidir aprovar ou reprovar** com base em alcançar um serviço externo.
  Validação cujo veredito precisa de rede vive na varredura agendada
  (`stage-issue-audit.yml`).
- **I2 — Degradação de checagem é legítima só quando decidida ou semântica;
  nunca quando é acidente do ambiente.** Três casos distintos:
  - **decidida** — a checagem não pertence ao veredito do PR e sua cobertura
    real vive na varredura agendada (`check_stage_issue.py` → WARN no runner).
    Legítima; a cobertura existe, só não é aqui.
  - **semântica** — a regra não se aplica ao caso (Stage em 3A/3B ainda não tem
    baseline). Legítima; não há o que checar.
  - **acidental** — a checagem pertence ao PR, se aplica ao caso, e o ambiente
    a impede em silêncio (clone raso escondendo a baseline). **Defeito** — é
    o que esta Stage conserta.
  "Determinístico" nunca pode significar "pulou por acidente e passou".
- **I3 — O step do CI roda literalmente `make check`.** Sem argumentos extras
  na linha de comando: é isso que sustenta o argumento de transitividade do
  `validate-ci-gate.md` (todo erro que reprova localmente reprova no runner).
- **I4 — Dev local sem `gh` continua destravado.** O `make check` local não pode
  exigir `gh` instalado (contrato best-effort do `check_stage_issue.py`).
- **I5 — O freeze da §7 vale só na janela de execução.** Stage `done` e não
  mergeada → enforce. Stage mergeada ou ainda em 3A/3B → não enforce
  (CONVENTIONS §3.4). Corolário: com histórico completo, `None` volta a
  significar apenas "ainda não aprovada".

## 5. Casos de erro e exceções

| Cenário | Comportamento esperado |
|---|---|
| PR de Stage `done` não-mergeada, edição **dentro** dos marcadores da §7 | CI verde |
| PR de Stage `done` não-mergeada, edição **fora** dos marcadores da §7 | **CI vermelho** (freeze — o gate que esta Stage reativa) |
| PR de Stage ainda em 3A/3B (sem commit `technical approved`) | CI verde — sem baseline por razão legítima (I5) |
| PR tocando `technical.md` de Stage **já mergeada** | CI verde — freeze não vale pós-merge (I5) |
| CI, API do GitHub fora do ar | **Não afeta o veredito do PR** (I1): `check_stage_issue.py` já sai em WARN por falta de `gh` autenticado |
| Local, sem `gh` instalado | WARN, `make check` passa (I4) |
| Local, **com `gh` autenticado**, alguma Stage do repo em 3A com `issue_id` placeholder | `make check` **vermelho** — inclusive para quem não mexeu naquela Stage (gate repo-global; §6 Decisão 1, razão 1). É o estado desta branch hoje; some quando a 3B preenche `issue_id: 9` |
| PR para `main` vindo de branch que não é `develop`/`hotfix/*` | `guard-main-source` **vermelho** |
| PR para `main` vindo de `develop` ou `hotfix/*` | `guard-main-source` verde |
| Push para `develop`/`main` (evento sem PR) | `guard-main-source` SKIPPED; `lint-and-test` roda |

## 6. Decisões técnicas relevantes

### Decisão 1 — Não levar o gate issue-first ao caminho de PR

- **O quê:** **não** plugar `GH_TOKEN` no `ci.yml`. O WARN do
  `check_stage_issue.py` no runner de PR permanece; a cobertura real do
  issue-first continua na varredura agendada.
- **Por quê (três razões estruturais, em ordem de peso):**
  1. **O gate é repo-global, não escopado ao PR.** `discover_technicals()`
     (`check_stage_issue.py` › `discover_technicals`) varre `docs/stages/*/technical.md` —
     **todas** as Stages, independente do que o PR toca. Qualquer Stage em 3A
     com `issue_id` placeholder reprovaria **todo PR do repo**. Isto não é
     hipótese: é o estado desta branch agora — `make check` local está vermelho
     por causa de `docs/stages/1.2-ci/technical.md` (`issue_id: 0`, template
     commitado em `316b88e`). Plugar o token exportaria esse vermelho para todo
     PR aberto durante qualquer 3A alheia.
  2. **O veredito dependeria de rede (I1).** `issue_exists()`
     (`check_stage_issue.py` › `issue_exists`) devolve o mesmo `False` para "a API
     respondeu: não existe" e para "não alcancei a API" (returncode != 0,
     timeout, `OSError`). Um outage reprovaria o PR **acusando um `issue_id`
     válido** — mensagem enganosa, que treina o time a re-rodar vermelho sem ler.
  3. **A cobertura já existe.** `stage-issue-audit.yml` roda a varredura completa
     semanalmente com `GH_TOKEN` e `permissions: issues: read`. O ganho de plugar
     o token seria detectar um `issue_id` errado até ~6 dias antes; o custo são
     (1) e (2).
- **Corroboração (não é a razão principal — e não é inequívoca):** o cabeçalho de
  `stage-issue-audit.yml` › comentário de cabeçalho descreve um split de duas metades e dá a razão do
  posicionamento, *ipsis litteris*:
  > "O docs-check de PR/local valida só o delta da branch (rápido e
  > determinístico). Esta varredura completa agendada é a segunda metade do
  > padrão: pega drift pós-merge (issue apagada/transferida depois que a stage
  > entrou) e qualquer stage que tenha entrado por caminho não validado — fora do
  > caminho crítico de PR, onde flakiness de rede não bloqueia ninguém."

  **Ressalva honesta:** a frase "o docs-check de PR/local valida só o delta da
  branch" é **imprecisa** — descreve bem o `check_technical_postexec.py` (que só
  *enforce* na janela de execução da Stage, ou seja, o delta), mas não o
  `check_stage_issue.py`, que varre tudo. E o docstring do script
  (`check_stage_issue.py` › docstring do módulo, "Best-effort") diz que "em CI com `gh` autenticado (…) funciona
  normalmente" — o que é verdade do CI agendado, mas pode ser lido como
  expectativa de token no PR. Logo o cabeçalho **corrobora** o split sem
  **provar** que a ausência de token no `ci.yml` foi deliberada. A decisão se
  sustenta em (1)–(3), que não dependem dessa leitura. A imprecisão do cabeçalho
  vira `[finding]`.
- **Fonte:** `scripts/check_stage_issue.py` › `issue_exists` e `discover_technicals`;
  `.github/workflows/stage-issue-audit.yml` › comentário de cabeçalho, `permissions`, `jobs.full-scan.steps` "check_stage_issue (todas as stages, com rede)"; `make check` local
  vermelho nesta branch (evidência em §3 da execução).
- **ADR:** [`../../adr/1_2_0001-deterministic-pr-path-gates.md`](../../adr/1_2_0001-deterministic-pr-path-gates.md)

### Decisão 2 — `fetch-depth: 0`, e prova A/B do mesmo erro intencional

- **O quê:** `actions/checkout` com `fetch-depth: 0` no job `lint-and-test`, e a
  validação do DoD feita com um erro intencional que **exercita o freeze da §7**
  (edição fora dos marcadores), rodado no PR descartável **antes** e **depois**
  da correção.
- **Por quê:** o freeze é git-only — não faz rede, então não colide com I1; ele
  pertence ao caminho de PR e simplesmente não estava funcionando lá. A
  alternativa "flag exija-baseline" seria *errada*: uma Stage em 3A/3B
  legitimamente não tem commit `technical approved`, e a flag não distinguiria
  "ainda não aprovada" de "o clone raso escondeu a aprovação" — reprovaria a
  primeira. Trazer o histórico **remove a ambiguidade na origem** (I5). A prova
  A/B existe porque o experimento local demonstra o mecanismo, não o ambiente: só
  um run real mostra o mesmo patch passando com `fetch-depth: 1` e reprovando com
  `fetch-depth: 0`. Um erro de lint **não serviria** — `make` para no primeiro
  prereq que falha e `lint` é o 1º da cadeia, então `docs-check` (6º) nunca
  rodaria: o run ficaria vermelho sem tocar no gate que a Stage conserta.
- **Custo:** clone completo por run (~1s hoje, 53 commits); cresce com a
  história e é reversível para um fetch dirigido se um dia doer.
- **Fonte:** `scripts/check_technical_postexec.py` › docstring "Limitações conhecidas" (limitações declaradas) e
  `_approved_commit_for`; `Makefile` › `check:` (ordem da cadeia); CONVENTIONS §3.4; verificação
  empírica em §3.
- **ADR:** mesma ADR 1.2.0001.

### Decisão 3 — Exercitar `guard-main-source` com PR **draft** para `main`

- **O quê:** abrir um segundo PR descartável contra `main`, a partir de branch
  que não é `develop`/`hotfix/*`, **como draft**, observar o job vermelho e
  fechar sem mergear.
- **Por quê:** é o único job do `ci.yml` que nunca rodou — todo PR do repo teve
  base `develop`, onde ele fica SKIPPED. Um gate que nunca executou é um gate que
  o projeto *acredita* ter. O DoD não exige, mas o objetivo declarado ("validar o
  pipeline") exige, e custa um PR de ~30s. **Draft é o controle real**: o GitHub
  recusa merge de PR em draft mecanicamente, enquanto "não aprovar" não protege
  nada neste repo (sem branch protection — ADR 1.1.0002 — check vermelho deixa o
  PR `UNSTABLE`, não `BLOCKED`). PR para `main` é o único caminho que alcança
  produção (GIT-WORKFLOW §Princípios #5), então a mitigação precisa ser mecânica.
- **Fonte:** `.github/workflows/ci.yml` › `jobs.guard-main-source.if` (`if: base.ref == 'main'`);
  `gh run list` — nenhuma execução de `guard-main-source` no histórico.

## 7. Integrações

### Internas

- `Makefile` (target `check`): o CI é consumidor remoto dessa cadeia; a Stage
  **não altera a cadeia** — só garante que ela roda inteira no runner.
- `scripts/check_technical_postexec.py`: consumidor do histórico git; **não é
  modificado** — o conserto é no ambiente que o script já documenta como
  requisito.
- `docs/runbooks/validate-ci-gate.md`: dever de manutenção (§Maintenance).
- `.github/workflows/stage-issue-audit.yml`: a outra metade do split (§6
  Decisão 1); **não é modificado**.

### Externas

- **GitHub Actions** — runner `ubuntu-latest`; contrato: `actions/checkout@v4`
  (parâmetro `fetch-depth`), `actions/setup-python@v5`, `astral-sh/setup-uv@v3`.

## 8. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| `fetch-depth: 0` não resolve `origin/develop` no evento `pull_request`, e o freeze continua morto | M | A | Prova A/B no PR descartável: o mesmo patch tem de passar antes e reprovar depois. Sem os dois runs, a Stage não fecha |
| `fetch-depth: 0` encarece o checkout com o tempo | B | B | 53 commits hoje; reversível para fetch dirigido |
| Freeze reativado reprova o **próprio** PR desta Stage | M | B | É o gate funcionando: após o commit `technical approved`, só a §7 é editada |
| PR descartável para `main` ser mergeado por engano | B | A | Aberto como **draft** (GitHub recusa merge de draft — controle mecânico, não disciplina) e fechado na mesma Task |
| PR descartável cortado da branch da Stage exibe todo o diff `develop..stage` | A | B | Descartável e draft; fechado imediatamente após a evidência |

## 9. Critérios de aceitação

- [ ] **CA1** — `ci.yml` passa a usar `actions/checkout@v4` com `fetch-depth: 0`
      no job `lint-and-test`.
- [ ] **CA2 (prova A/B — entregável da Stage)** — no PR descartável, uma edição
      **fora** dos marcadores da §7 de um `technical.md` `done` e não-mergeado:
      (a) **passa** no CI com `fetch-depth: 1` (evidência do buraco no runner) e
      (b) **reprova** com `fetch-depth: 0` (evidência do conserto). Sem os dois
      runs colados, o CA não conta.
      - **Pré-condição de ordem (não é opcional):** o freeze só tem alvo elegível
        depois que **esta** Stage produzir seu commit `stage 1.2: technical
        approved` e `technical.md` estiver `done` — hoje o repo não tem nenhuma
        Stage `done` e não-mergeada, então a varredura roda sobre zero alvos e
        ficaria verde pelo motivo errado. Logo: 3B fecha → CA1 → PR descartável.
      - **Isolamento da variável:** a branch descartável nasce da branch da Stage,
        já com `fetch-depth: 0`. Os dois runs são dois pushes na **mesma** branch
        descartável, diferindo **só** na linha do checkout: push 1 = patch +
        `fetch-depth: 1` (revertido de propósito) → espera-se verde; push 2 =
        restaura `fetch-depth: 0`, mesmo patch → espera-se vermelho.
- [ ] **CA3 (DoD do roadmap)** — revertido o erro intencional, o CI fica
      **verde em < 5min**; o PR é fechado sem merge.
- [ ] **CA4** — o step do CI roda literalmente `make check` (I3) e seu nome lista
      a cadeia real de targets.
- [ ] **CA5** — `guard-main-source` observado **vermelho** em PR draft real para
      `main` vindo de branch não-`develop`/`hotfix/*`. **A observação e o
      `gh pr close` acontecem na mesma Task** — o PR não sobrevive à Task que o
      abriu.
- [ ] **CA6** — `docs/runbooks/validate-ci-gate.md` estendido conforme sua
      §Maintenance: as citações literais do nome antigo do step (§Purpose e
      §Verification) alinhadas, e a classe do freeze §7 documentada com a
      condição de ambiente (histórico completo) que ela exige no runner.
- [ ] **CA7** — `make check` local verde **nos dois modos**: com `gh` autenticado
      (exige `issue_id: 9` real no `technical.md` — hoje vermelho, ver §5) e sem
      `gh` no PATH (I4). Um só dos dois não basta.

## 10. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — **a Stage não
      introduz contrato** (bate com `contratos_introduzidos: []` do roadmap):
      não há mudança de código-fonte, só de configuração de workflow e docs.
- [x] Toda decisão em §6 tem fonte rastreável? — sim (arquivo:linha, cabeçalho
      do workflow, docstring do script, verificação empírica, `gh run list`).
- [x] Toda integração externa tem contrato definido? — sim (§7: actions pinadas
      e o parâmetro usado).
- [x] Decisões com alternativa real descartada têm ADR escrito? — sim: ADR
      1.2.0001 cobre a Decisão 1 (levar o gate ao PR — rejeitada) e a Decisão 2
      (flag exija-baseline e fetch dirigido — rejeitadas). A Decisão 3 é rigor de
      validação, sem alternativa arquitetural.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — sim,
      `1.1-bootstrap` `done` **e mergeada**.
- [x] Stage cabe em ~3–12 Tasks? — sim, 5 Tasks previstas.
- [x] Riscos críticos têm mitigação plausível? — sim (§8).
- [x] **A Stage evita inventar trabalho?** — sim: o CI já está verde e isso é
      declarado em §3; o único conserto é um `fetch-depth` cuja ausência foi
      verificada empiricamente. O que **parecia** o achado maior (gate issue-first
      "morto" no CI) foi investigado e **recusado** — levá-lo ao PR reprovaria
      todo PR do repo durante qualquer 3A alheia, e a cobertura já existe na
      varredura semanal (§6 Decisão 1). A Stage não "conserta" o que não está
      quebrado.

## 11. Referências

- [`../../roadmap.md`](../../roadmap.md) — Stage `1.2-ci` e Step 1
- [`../../runbooks/validate-ci-gate.md`](../../runbooks/validate-ci-gate.md) — validação classe a classe
- [`../../adr/1_2_0001-deterministic-pr-path-gates.md`](../../adr/1_2_0001-deterministic-pr-path-gates.md)
- [`../../adr/1_1_0002-observational-pr-gates.md`](../../adr/1_1_0002-observational-pr-gates.md) — gates observacionais no GitHub Free
- [`../../../.github/workflows/stage-issue-audit.yml`](../../../.github/workflows/stage-issue-audit.yml) — a metade agendada do split
- [`../1.1-bootstrap/technical.md`](../1.1-bootstrap/technical.md) §7 — findings da 1.1 (#7, #8): nenhum escalado para cá

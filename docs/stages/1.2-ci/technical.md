---
title: Technical — Stage 1.2 — CI no GitHub Actions
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, ci, fetch-depth, guard-main-source, validate-ci-gate]
status: done
created_at: 2026-07-16
updated_at: 2026-07-16
stage_id: 1.2-ci
stage_title: CI no GitHub Actions
step_id: 1
step_title: Fundação do repositório
depends_on: [1.1-bootstrap]
concept_ref: ./concept.md
issue_id: 9
branch: feat/9-1-2-ci
tasks_count: 5
---

# Technical — Stage 1.2 — CI no GitHub Actions

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. **Não avançar para próxima Task sem verificação verde.**
> 4. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage).

## 1. Contexto e estratégia de execução

### Resumo

A Stage muda **uma linha de comportamento** no `.github/workflows/ci.yml`
(`fetch-depth: 0` no `actions/checkout`) e depois **gasta a maior parte do
esforço provando** que essa linha faz o que diz — porque o valor da Stage não é
a linha, é a evidência de que o gate do runner finalmente roda. Nenhum arquivo de
`src/` ou `scripts/` é tocado.

O defeito: a checagem 2 do `check_technical_postexec.py` (freeze da §7,
CONVENTIONS §3.4) procura o commit-baseline `stage N.M: technical approved` via
`git log`. O clone raso default (`fetch-depth: 1`) o esconde,
`_approved_commit_for()` devolve `None`, e a checagem é pulada em silêncio — no
runner, sempre.

### Estratégia

**Consertar primeiro, depois provar A/B com o mesmo patch.** O experimento local
do concept §3 prova o *mecanismo* (raso ⇒ baseline invisível), mas não o
*ambiente* do runner (`pull_request` faz checkout de `refs/pull/N/merge`; e
`_stage_is_merged()` precisa resolver `origin/develop` lá). Só um par de runs
reais isola isso.

Ordem e razão:

1. **Task 01** entrega o conserto (`fetch-depth: 0`) — precisa vir antes da
   validação, senão não há o que validar.
2. **Task 02** alinha o nome do step — **a Task 03 consome esse nome** (o runbook
   o cita *verbatim*), então 02 vem obrigatoriamente antes de 03.
3. **Task 03** estende o runbook — inclui a classe que a Task 04 exercita, então
   vem antes dela (o runbook é o roteiro, não o relatório).
4. **Task 04** roda a prova A/B no PR descartável e cola a evidência.
5. **Task 05** exercita o `guard-main-source`.

**Pré-condição de ordem crítica (concept §9 CA2):** a Task 04 só tem alvo
elegível depois que **esta** Stage tiver seu commit `stage 1.2: technical
approved` e `technical.md` em `status: done` — hoje o repo não tem nenhuma Stage
`done` e não-mergeada, então a varredura rodaria sobre zero alvos e ficaria verde
pelo motivo errado. Como esse commit é o gate da própria Fase 3B, a condição está
satisfeita quando a Fase 4 começa.

### Pré-condições

- Stage `1.1-bootstrap` em `done` **e mergeada** em `develop`
  (`a0bf730 stage 1.1: complete`) — verificado.
- `gh` autenticado (necessário para abrir/fechar os PRs descartáveis e ler runs).
- `make check` verde localmente. **Atenção:** ficou vermelho durante a Fase 3A
  porque `docs/stages/1.2-ci/technical.md` era o template com `issue_id: 0` e o
  `check_stage_issue.py` é repo-global (concept §5 e §6 Decisão 1). O
  `issue_id: 9` deste frontmatter fecha isso.

### Premissas técnicas (medidas na Task 04, não assumidas)

- `actions/checkout@v4` com `fetch-depth: 0` cria `refs/remotes/origin/*` — logo
  `_stage_is_merged()` resolve `origin/develop`.
- No evento `pull_request`, o histórico do merge ref alcança os commits da
  branch — logo `_approved_commit_for()` acha o `technical approved`.

### Estrutura de pastas afetada

```
.github/workflows/
└── ci.yml                       # fetch-depth: 0 + nome do step
docs/
├── runbooks/validate-ci-gate.md # §Purpose, §Verification, classe do freeze
├── adr/1_2_0001-…               # criado na Fase 3A
├── stages/1.2-ci/               # concept + technical (+ §7)
└── roadmap.md                   # bloco da Stage + §Histórico (gate de saída)
```

Nenhum arquivo de `src/` ou `scripts/` é tocado — logo não há arquivo de Stage
sujeito ao gate de cobertura **por arquivo**. O gate global (`fail_under = 90`)
continua valendo e é verificado por `make check`.

## 2. Tasks

### Task 01 — `fetch-depth: 0` no checkout do `lint-and-test`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `.github/workflows/ci.yml`
- **O que fazer:** trocar `- uses: actions/checkout@v4` (job `lint-and-test`)
  pela mesma action **com `with: fetch-depth: 0`**, e comentar *por quê* — a
  checagem 2 do `check_technical_postexec.py` precisa enxergar o commit
  `stage N.M: technical approved` e a ref `origin/develop`; sem isso ela se pula
  em silêncio. O comentário aponta para o ADR 1.2.0001.
- **Detalhes técnicos:**
  - **Não** tocar no `guard-main-source` (não faz checkout).
  - **Não** tocar no `stage-issue-audit.yml`: o comentário dele já explica que
    clone raso basta lá (descoberta por glob, não consulta git).
  - Não adicionar `concurrency`, `timeout-minutes`, cache ou `GH_TOKEN` — todos
    fora do escopo (concept §1).
- **Critério de aceite:** `ci.yml` declara `fetch-depth: 0` no job
  `lint-and-test`; o step de gate continua sendo literalmente `make check` (I3).
- **Comando de verificação:**
  ```bash
  grep -n -A3 "actions/checkout" .github/workflows/ci.yml
  grep -n "run: make check" .github/workflows/ci.yml
  ```
- **Commit sugerido:** `ci(shared): trazer historico completo no checkout do gate [1.2/task-01]`

---

### Task 02 — Nome do step reflete a cadeia real de `make check`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `.github/workflows/ci.yml`
- **O que fazer:** o step diz `Run gate completo (lint + typecheck + layout-check
  + tests)`, mas `make check` roda **sete** targets (`Makefile:81`):
  `lint typecheck layout-check import-check lock-check docs-check test-gate`. O
  nome omite `import-check`, `lock-check`, `docs-check` e o gate de cobertura —
  todos entregues pela Stage 1.1. Alinhar o nome à cadeia real.
- **Detalhes técnicos:** só o campo `name:` muda; o `run: make check` fica
  intocado (I3).
- **Critério de aceite:** o nome do step lista a cadeia de `Makefile:81` **e** o
  `run:` continua sendo literalmente `make check` (I3 — esta é a única Task que
  edita o step, então é ela quem tem de guardar as duas metades do CA4).
- **Comando de verificação** (binário, exit code — não inspeção visual):
  ```bash
  grep -q "name: Run gate completo (lint + typecheck + layout-check + import-check + lock-check + docs-check + test-gate)" .github/workflows/ci.yml \
    && grep -qE "^\s+run: make check$" .github/workflows/ci.yml \
    && echo "CA4 OK (nome + I3)"
  ```
- **Commit sugerido:** `docs(ci): alinhar nome do step a cadeia real do make check [1.2/task-02]`

---

### Task 03 — Estender `validate-ci-gate.md` (dever da §Maintenance)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `docs/runbooks/validate-ci-gate.md`
- **O que fazer:** três edições, todas exigidas pela §Maintenance do próprio
  runbook (que manda estender na mesma Stage que endurece o gate):
  1. **§Purpose e §Verification** citam o nome antigo do step *verbatim* (`:25` e
     `:337`). Alinhar ao nome da Task 02 — senão o runbook aponta para um step
     que não existe.
  2. **§Class 5** ganha a sub-classe do **freeze §7 (diff vs baseline)** com a
     **pré-condição de ambiente** que ela agora tem no runner: histórico completo
     (`fetch-depth: 0`) **e** alvo elegível (Stage `done` e não-mergeada). Hoje o
     runbook só roteia a Classe 5 pela checagem **estrutural** (marcador
     quebrado), que roda mesmo em clone raso — por isso o buraco passou.
  3. **§Troubleshooting** ganha a linha do sintoma: "checagem 2 não acusa edição
     fora dos marcadores **no CI**" → causa: clone raso → resolução:
     `fetch-depth: 0` (ADR 1.2.0001).
- **Detalhes técnicos:**
  - Manter a forma de quatro partes das classes (patch / command / expected
    output / revert).
  - Atualizar `updated_at` do frontmatter e referenciar a Stage 1.2 no corpo da
    subseção nova (exigência literal da §Maintenance).
  - O runbook é escrito **em inglês** (regra do próprio doc).
- **Critério de aceite:** nenhuma ocorrência do nome antigo do step; o nome citado
  no runbook **casa com o `ci.yml` real**; a classe do freeze documenta a
  pré-condição de histórico completo; `updated_at` atualizado.
- **Comando de verificação** (o casamento é o que importa — só conferir a ausência
  do nome antigo passaria mesmo se o novo estivesse errado):
  ```bash
  ! grep -rq "layout-check + tests" docs/runbooks/validate-ci-gate.md \
    && NAME=$(grep -oP '(?<=- name: )Run gate.*' .github/workflows/ci.yml) \
    && grep -qF "$NAME" docs/runbooks/validate-ci-gate.md \
    && grep -q "fetch-depth" docs/runbooks/validate-ci-gate.md \
    && echo "CA6 OK (nome casa com ci.yml + classe do freeze documentada)"
  ```
- **Commit sugerido:** `docs(runbook): cobrir a classe do freeze da secao 7 no validate-ci-gate [1.2/task-03]`

---

### Task 04 — Prova A/B no PR descartável (CA2 + CA3 — entregável da Stage)

- **Arquivos a criar:** nenhum no repo (a branch descartável **não** é mergeada)
- **Arquivos a modificar:**
  - `docs/stages/1.2-ci/technical.md` (**apenas §7**, entre os marcadores)
- **O que fazer:** provar no runner que a Task 01 muda o veredito, com o **mesmo
  patch** dos dois lados:
  1. Criar branch descartável a partir de `feat/9-1-2-ci` (ex.:
     `test/9-ci-gate-probe`) e abrir PR **draft** contra `develop`.
  2. **Run A (buraco):** commitar (a) o erro intencional — uma edição **fora**
     dos marcadores da §7 de `docs/stages/1.2-ci/technical.md` — e (b) a
     reversão de `fetch-depth: 0` → `1`. Esperado: **CI verde** (o gate não vê a
     violação). Colar link e resultado do run.
  3. **Run B (conserto):** um segundo push que **só** restaura `fetch-depth: 0`,
     mantendo o mesmo erro intencional. Esperado: **CI vermelho**, com a
     mensagem `status=done mas há mudanças fora dos marcadores post-execution`.
     Colar link + trecho do log.
  4. **Run C (DoD):** reverter o erro intencional. Esperado: **CI verde em
     < 5min**. Colar duração.
  5. `gh pr close` **sem merge** + apagar a branch remota.
  6. Registrar em §7 a evidência com os três links.
- **Detalhes técnicos:**
  - **Definição de "verde"/"vermelho" nesta Task:** refere-se ao run do workflow
    **`ci.yml`** (`gh run list --workflow=ci.yml`), **não** ao agregado de checks
    do PR. O `audit-gate` fica **vermelho nos três runs, por design** — o corpo do
    PR descartável não tem `> **Auditoria:** \`complete\``, e é isso que aquele
    workflow existe para sinalizar. **Não** editar o corpo para contorná-lo:
    gravar `complete` à mão sem auditoria burla o gate (CONVENTIONS §3.6). Ele é
    constante nos três runs, logo não interfere no isolamento A/B.
  - A branch descartável nasce da branch da Stage, então já tem `fetch-depth: 0`
    — por isso o Run A precisa do commit de reversão explícito. **A única
    diferença entre A e B é a linha do checkout** (concept §9 CA2).
  - Colar, junto de cada link, o `git rev-parse origin/develop` do momento — se
    `develop` avançar entre A e B, o merge ref muda e a variável deixa de estar
    isolada. Custo ~zero, fecha a única variável não-controlada restante.
  - Workflows de `pull_request` rodam **do merge ref**, então a mudança de
    `ci.yml` na branch descartável vale para o próprio run.
  - O erro intencional **precisa** ser a violação do freeze: um erro de lint
    reprovaria em `lint` (1º da cadeia) e `docs-check` (6º) nunca rodaria — o run
    ficaria vermelho sem tocar no gate que a Stage conserta.
  - **Nunca** commitar o erro intencional na branch da Stage.
- **Critério de aceite:** três runs observados (verde / vermelho / verde < 5min),
  com links colados; PR fechado sem merge; branch remota apagada; `git status`
  limpo na branch da Stage.
- **Comando de verificação:**
  ```bash
  gh pr view <num> --json state,mergedAt   # state=CLOSED, mergedAt=null
  gh run list --branch test/9-ci-gate-probe --workflow=ci.yml
  git status --short                       # limpo
  ```
- **Commit sugerido:** `docs(shared): registrar prova A/B do gate no runner [1.2/task-04]`
  (escopo = BC, **nunca** a Stage — CONVENTIONS §4(a); a tag `[1.2/task-04]` já
  carrega a Stage)

---

### Task 05 — Exercitar o `guard-main-source` (CA5)

- **Arquivos a criar:** nenhum no repo
- **Arquivos a modificar:**
  - `docs/stages/1.2-ci/technical.md` (**apenas §7**)
- **O que fazer:** o `guard-main-source` nunca executou — todo PR do repo teve
  base `develop`, onde ele fica SKIPPED (`if: base.ref == 'main'`). Abrir um PR
  **draft** contra `main` a partir de branch descartável que **não** é
  `develop`/`hotfix/*`, observar o job **vermelho**, e fechar.
- **Detalhes técnicos:**
  - **Draft é o controle de segurança** e é mecânico: o GitHub recusa merge de PR
    em draft. Sem branch protection (ADR 1.1.0002), "não aprovar" não protege
    nada — e `main` é o único caminho para produção (GIT-WORKFLOW §Princípios #5).
  - **A observação e o `gh pr close` acontecem nesta mesma Task** (concept §9
    CA5): o PR não sobrevive à Task que o abriu.
  - A branch pode ser trivial (um commit vazio) — o alvo é o `if:`, não o diff.
- **Critério de aceite:** run do job `guard-main-source` observado com conclusão
  **failure** e a mensagem `PRs para main só são aceitos de 'develop' ou
  'hotfix/*'`; PR fechado sem merge; branch apagada. Evidência em §7.
- **Comando de verificação:**
  ```bash
  gh run view <run-id> --json jobs --jq '.jobs[] | {name,conclusion}'
  gh pr view <num> --json state,mergedAt,isDraft
  ```
- **Commit sugerido:** `docs(shared): registrar validacao do guard-main-source [1.2/task-05]`

---

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
make check                                                    # verde, com gh autenticado
python scripts/check_technical_postexec.py docs/stages/1.2-ci/technical.md
```

E o modo **sem `gh`** (I4 / CA7) — o `make check` não pode exigir `gh`. O filtro
**deriva o diretório do binário resolvido** (não assume o layout do instalador) e
**falha alto** se o `gh` sobreviver ao filtro — senão o próprio gate de saída
vira o defeito que esta Stage conserta: passar verde sem ter rodado o que diz:

```powershell
$ghDir = Split-Path (Get-Command gh).Source
$env:PATH = ($env:PATH.Split(';') | Where-Object { $_ -and $_.TrimEnd('\') -ne $ghDir.TrimEnd('\') }) -join ';'
if (Get-Command gh -ErrorAction SilentlyContinue) { throw "gh ainda no PATH — o modo I4 NAO foi exercido" }
make check   # esperado: WARN de check_stage_issue.py + exit 0
```

**Evidência positiva obrigatória:** a saída tem de conter
`check_stage_issue: WARN — `gh` não disponível` — é a prova de que o modo rodou.
Verde sem esse WARN = o filtro não pegou; o gate não conta.

### Verificações funcionais

> **"Verde"/"vermelho" abaixo = conclusão do run do workflow `ci.yml`**, não o
> agregado de checks do PR. Nos PRs descartáveis o `audit-gate` fica vermelho por
> design (sem label de auditoria) e **não** participa da prova — nem deve ser
> contornado (CONVENTIONS §3.6).

- [ ] **CA2** — Run A verde (`fetch-depth: 1`) e Run B vermelho (`fetch-depth: 0`)
      com o mesmo patch, links colados.
- [ ] **CA3 (DoD)** — Run C do `ci.yml` verde em < 5min; PR descartável fechado
      sem merge.
- [ ] **CA5** — `guard-main-source` observado vermelho; PR draft fechado.
- [ ] Nenhuma branch descartável sobrevive à Stage.

### Checklist de fechamento da Stage

- [ ] Todas as 5 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch (com e sem `gh`)
- [ ] §7 reflete a execução real (evidências dos runs)
- [ ] `roadmap.md`: Stage `1.2-ci` → `done`, `updated_at`/`last_reviewed_at` de
      hoje, **e a linha na tabela §Histórico** (padrão da 1.1, que registrou
      "concluída + bloco corrigido" numa linha)
- [ ] ADR 1.2.0001 em `status: accepted`
- [ ] Commit final `stage 1.2: complete`
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (fetch-depth: 0) ─────────────────────┬─► Task 04 (prova A/B)
Task 02 (nome do step) ─► Task 03 (runbook) ──┘

Task 05 (guard-main-source) — independente das demais
```

- **Task 03 depende de 02** (aresta obrigatória): o runbook cita o nome do step
  *verbatim*, então editá-lo antes da Task 02 gravaria um nome que ainda não
  existe — e o check da Task 03 (`grep` do nome antigo vazio) passaria assim
  mesmo, deixando o erro invisível até o review. Por isso o check da Task 03
  **casa o nome contra o `ci.yml`**, em vez de só conferir a ausência do antigo.
- Task 04 depende de **01** (não há o que provar sem o conserto), de **02** (o
  run A/B já mostra o step com o nome novo) e de **03** (o runbook é o roteiro da
  validação, não o relatório dela).
- Task 04 depende ainda do commit `stage 1.2: technical approved` existir — é o
  gate desta Fase 3B, logo satisfeito ao entrar na Fase 4.
- Task 05 não depende de nenhuma: o `guard-main-source` não faz checkout.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Run B fica **verde** (a correção não funciona no runner) | A tese do concept caiu — **não** forçar. Investigar se `origin/develop` resolve no merge ref (step de debug temporário na branch descartável); se `fetch-depth: 0` não bastar, registrar `[finding]`, reverter a Task 01 e **HALT** — a Stage perdeu o entregável |
| Run A fica **vermelho** (falso positivo na prova) | O vermelho veio de outro target: ler o log e conferir se parou em `lint`/`typecheck`. Ajustar o patch para tocar **só** o freeze |
| PR descartável não pode ser aberto (API do GitHub 503) | Não é defeito do repo — re-tentar; GraphQL costuma responder quando a REST v3 cai. Não dar HALT por 503 transitório |
| Freeze reativado reprova o **próprio** PR da Stage | É o gate funcionando: depois do commit `technical approved`, editar **só** a §7 |
| PR draft para `main` sobrevive à Task 05 | Fechar imediatamente; se `gh pr close` falhar, fechar pela UI antes de seguir |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../roadmap.md`](../../roadmap.md) — bloco `1.2-ci`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §3.4 (freeze §7), §4 (commits)
- [`../../adr/1_2_0001-deterministic-pr-path-gates.md`](../../adr/1_2_0001-deterministic-pr-path-gates.md)
- [`../../runbooks/validate-ci-gate.md`](../../runbooks/validate-ci-gate.md)
- Skills aplicáveis: `git-versioning-pointer` (`skills_hint` da Stage)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.

### 2026-07-16 — [decision] Task 04 — prova A/B do gate no runner (CA2 + CA3) — Claude

**Contexto:** o entregável da Stage é a evidência de que `fetch-depth: 0` faz o
freeze da §7 disparar **no runner** — o experimento local do concept §3 prova só
o mecanismo. Executada no PR descartável **draft**
[#13](https://github.com/MarceloSanC/restaurant-hub/pull/13) (branch
`test/9-ci-gate-probe`, base `develop`), fechado sem merge (`state: CLOSED`,
`mergedAt: null`, `isDraft: true`) e branch apagada.

**Resultado — o mesmo patch (edição fora dos marcadores da §7: a linha de título
do technical), nos três runs:**

| Run | checkout | patch | run | duração | resultado |
|---|---|---|---|---|---|
| **A** | `fetch-depth: 1` | erro presente | [29546150438](https://github.com/MarceloSanC/restaurant-hub/actions/runs/29546150438) | 25s | **success** |
| **B** | `fetch-depth: 0` | erro presente (idêntico) | [29546221053](https://github.com/MarceloSanC/restaurant-hub/actions/runs/29546221053) | 21s | **failure** |
| **C** | `fetch-depth: 0` | erro revertido | [29546311519](https://github.com/MarceloSanC/restaurant-hub/actions/runs/29546311519) | **28s** | **success** |

Run A (o buraco) — o gate **rodou e aprovou** a violação:
```
OK — 2 arquivo(s) validado(s).
check_stage_issue: WARN — `gh` não disponível ou não autenticado; verificação programática pulada (best-effort).
```

Run B (o conserto) — mesmo patch, só o checkout mudou:
```
/home/runner/work/restaurant-hub/restaurant-hub/docs/stages/1.2-ci/technical.md: status=done mas há mudanças fora dos marcadores post-execution (baseline: 6af53211 `stage technical approved`):
  replace: baseline[19:20] (lines 20-20) vs current[19:20] (lines 20-20)
2 erro(s) em 2 arquivo(s).
make: *** [Makefile:127: docs-check] Error 1
##[error]Process completed with exit code 2.
```

**As duas premissas do §1 ficam MEDIDAS, não assumidas:** o Run B encontrou a
baseline `6af53211` (logo `fetch-depth: 0` dá histórico completo no merge ref de
um evento `pull_request`) **e** enforçou em vez de cair em fail-open (logo
`_stage_is_merged()` resolveu `origin/develop` e concluiu "não mergeada").

**Isolamento da variável:** `origin/develop` ficou em `6c36c51b` durante A e B —
o merge ref não mudou entre os dois runs.

**Ressalva de honestidade sobre "só uma linha muda":** o diff A→B tem **3**
linhas, não 1 — o `sed` que trocou o `fetch-depth` acertou também duas linhas de
**comentário** que citavam o valor. Só uma é funcional (`fetch-depth:`); as
outras duas são texto de comentário, sem efeito no runner. A afirmação do concept
§9 CA2 ("diferindo só na linha do checkout") vale para o **comportamento**, não
para a contagem literal de linhas do diff.

**Nota sobre o `audit-gate`:** ficou vermelho nos três runs, por design (o PR
descartável não tem o label de auditoria). Constante nos três, logo não interfere
no isolamento; **não** foi contornado (CONVENTIONS §3.6 proíbe gravar `complete`
à mão).

### 2026-07-16 — [decision] Task 05 — `guard-main-source` exercitado pela 1ª vez (CA5) — Claude

**Contexto:** o `guard-main-source` nunca executou na história do repo — todo PR
até hoje teve base `develop`, onde ele fica SKIPPED (`if: base.ref == 'main'`).
Um gate que nunca rodou é um gate que o projeto *acredita* ter.

**Execução:** PR descartável **draft** [#14](https://github.com/MarceloSanC/restaurant-hub/pull/14)
(branch `test/9-guard-main-probe`, commit vazio, base **`main`**), fechado **na
mesma Task que o abriu** (`state: CLOSED`, `mergedAt: null`, `isDraft: true`) e
branch apagada.

**Resultado** — [run 29546481401](https://github.com/MarceloSanC/restaurant-hub/actions/runs/29546481401):

| job | conclusão |
|---|---|
| `guard-main-source` | **failure** ✅ (esperado) |
| `lint-and-test` | success |

```
PRs para main só são aceitos de 'develop' ou 'hotfix/*'. Origem: test/9-guard-main-probe
##[error]Process completed with exit code 1.
```

**Controle de segurança:** draft, porque é mecânico — o GitHub recusa merge de PR
em draft. Sem branch protection (ADR 1.1.0002), "não aprovar" não seguraria nada,
e PR para `main` é o único caminho que alcança produção (GIT-WORKFLOW §Princípios
#5). Excede o DoD do roadmap conscientemente: o DoD pede um PR de teste, e o
objetivo declarado da Stage ("validar o pipeline") pede que o único job nunca
observado seja observado.

### 2026-07-16 — [deviation] Task 03 — o runbook afirmava prova que ainda não existia — Claude

**Contexto:** achado do Checkpoint C (bloco 01–03). A §Class 5b e a §Maintenance
do `validate-ci-gate.md` foram escritas afirmando, **no passado**, que a Stage
"closed the environment half with an A/B pair of real runs" — mas a Task 04 ainda
não tinha rodado.
**Razão:** era a própria classe de defeito que a Stage conserta (declarar fechado
sem ter olhado), transposta de gate para doc — e nenhum gate mecânico pega
asserção de doc contra realidade. Corrigido em `f284fe0`: a classe voltou ao modo
roteiro e aponta a evidência para esta §7, onde ela de fato entrou. Ajuste
in-scope da própria Task 03, abaixo do threshold de decisão.

### 2026-07-16 — [finding] `check_stage_issue.py` é repo-global: qualquer Stage em 3A deixa o `make check` local vermelho para todo mundo — Claude

**Contexto:** `discover_technicals()` (`check_stage_issue.py:114-123`) varre
`docs/stages/*/technical.md` — todas as Stages, independente do que se está
mexendo. Enquanto o `technical.md` desta Stage foi o template (`issue_id: 0`,
commit `316b88e`), o `make check` **local** ficou vermelho para qualquer dev com
`gh` autenticado, inclusive quem não tocou na 1.2. Some ao preencher o
`issue_id` real, mas repete a cada 3A.
**Direção sugerida:** escopar a varredura ao delta do PR/branch, **ou** tratar
`issue_id: 0`/`status: draft` como "Stage ainda em 3A" e pular. É também o
argumento nº 1 da Decisão 1 do concept (por que não levar o gate ao caminho de
PR): plugar `GH_TOKEN` exportaria esse vermelho para todo PR do repo.
**Stage/issue candidata:** issue avulsa de tooling.

### 2026-07-16 — [finding] `check_stage_issue.py` aprova issue **fechada** — Claude

**Contexto:** o script pede `--json number,state` (`:70`) mas só compara `number`
(`:79`) — `state` é campo morto. Um `issue_id` apontando para issue `CLOSED`
(ou para a issue errada, que por acaso exista) satisfaz o gate issue-first.
Verificado: `docs/stages/1.1-bootstrap/technical.md` → issue #1 está `CLOSED` e o
gate diz `OK`.
**Direção sugerida:** decidir explicitamente se `CLOSED` reprova (provavelmente
sim durante a execução da Stage; não após o merge) e usar o `state` que já é
buscado. Afeta a metade agendada (`stage-issue-audit.yml`), que é quem enforça.
**Stage/issue candidata:** mesma issue de tooling do finding acima.

### 2026-07-16 — [finding] Higiene de runner-minutes do `ci.yml`: sem `concurrency` e sem `timeout-minutes` — Claude

**Contexto:** avaliado e **recusado** na Fase 3A por ser a mesma classe do
non-goal "cache de dependências" (concept §1). Sem `concurrency`, pushes
sucessivos deixam runs redundantes vivos; sem `timeout-minutes`, um job travado
herda o default de **360 min**.
**Direção sugerida:** `concurrency` agrupado por workflow+ref com
`cancel-in-progress` **só para PR** (cancelar run de push em `develop` perderia
o registro por merge), e `timeout-minutes` ~10.
**Stage/issue candidata:** issue avulsa de CI, pós-Stage.

### 2026-07-16 — [finding] Os dois gates locais discordam: `pre-commit` roda `ruff-format`, `make check` não — Claude

**Contexto:** `.pre-commit-config.yaml` tem o hook `ruff-format`, mas
`make check` (`Makefile:81`) não tem target de formatação — o `fmt` *aplica*,
não *checa*. Código commitado com `--no-verify`, ou por quem não instalou os
hooks, passa no CI desformatado. O `validate-ci-gate.md` §Class 2 já antecipa a
promoção (`ruff format --check`) como hardening futuro.
**Direção sugerida:** adicionar `fmt-check` à cadeia do `check` e promover a
§Class 2 do runbook. É mudança do **gate local** (território da 1.1), não da
ativação do CI — por isso fora do escopo desta Stage.
**Stage/issue candidata:** issue avulsa de tooling (parente da #7, drift de hooks).

### 2026-07-16 — [finding] `mypy` não cobre `scripts/` — Claude

**Contexto:** `make typecheck` roda `mypy src/` (`Makefile:100`); `ruff` cobre
`scripts/` mas o type-checker não. Os scripts de `scripts/` **são os gates** do
projeto (`check_layout`, `check_technical_postexec`, `check_stage_issue`,
`check_commit_msg`) e não têm nem tipos checados nem cobertura medida
(`--cov=src/restaurant_hub` no `Makefile:141`; a entrada `*/scripts/*` do `omit`
em `pyproject.toml:91` é redundante com `source = ["src"]`).
**Direção sugerida:** estender `mypy` a `scripts/`; avaliar testes para os
validadores.
**Stage/issue candidata:** issue avulsa de tooling.

### 2026-07-16 — [finding] O cabeçalho do `stage-issue-audit.yml` descreve um docs-check delta-scoped que não existe — Claude

**Contexto:** o cabeçalho diz "o docs-check de PR/local valida **só o delta da
branch**". Isso descreve bem o `check_technical_postexec.py` (que só *enforce* na
janela de execução da Stage), mas **não** o `check_stage_issue.py`, que varre
todas as Stages por glob. A imprecisão fez a primeira passada da Fase 3A desta
Stage ler o split como inequivocamente deliberado — o Checkpoint A refutou, e o
concept §6 Decisão 1 foi reancorado em argumentos estruturais.
**Direção sugerida:** corrigir o cabeçalho para dizer qual checagem é
delta-scoped e qual é repo-global.
**Stage/issue candidata:** junto da issue de tooling do `check_stage_issue`.

### 2026-07-16 — [finding] `CONVENTIONS.md` §3.4 afirma que o `check_technical_postexec.py` roda no pre-commit — não roda — Claude

**Contexto:** achado do Checkpoint B. O `.pre-commit-config.yaml` tem só
`ruff-format`, `ruff`, `mypy`, `check-commit-msg` e `lint-imports`. O
`check_technical_postexec.py` roda **só** via `make docs-check` (e, portanto, no
CI). Drift de doc pré-existente, da mesma classe que esta Stage cataloga:
documento afirmando garantia que o mecanismo não dá.
**Direção sugerida:** corrigir o texto de §3.4 **ou** adicionar o hook (decidir
qual dos dois é a intenção).
**Stage/issue candidata:** issue avulsa de docs/tooling.

### 2026-07-16 — [finding] `audit-gate` não tem carve-out para PR descartável/draft — Claude

**Contexto:** achado do Checkpoint B. O `audit-gate.yml` dispara em todo
`pull_request` sem filtro de base nem de draft, então ficou vermelho nos 5 runs
dos dois PRs descartáveis desta Stage (#13, #14) — corretamente, do ponto de
vista dele, mas ruidosamente. O risco real não é o ruído: é que a saída óbvia
para "deixar verde" é gravar `> **Auditoria:** complete` à mão, que CONVENTIONS
§3.6 proíbe. O plano da Task 04 fixou por escrito que "verde" se refere ao run do
`ci.yml`, não ao agregado de checks do PR — mas isso é disciplina, não mecanismo.
**Direção sugerida:** avaliar `if: github.event.pull_request.draft == false` no
`audit-gate` (PR em draft é, por definição, trabalho não pronto para auditoria).
**Stage/issue candidata:** issue avulsa de CI, junto do finding de higiene.

### 2026-07-16 — [finding] Precedente de escopo de commit violando CONVENTIONS §4(a) — Claude

**Contexto:** achado do Checkpoint B. CONVENTIONS §4(a) manda escopo = bounded
context e marca com ❌ o padrão "Stage como escopo"
(`❌ feat(stage-2.3): ...`). O commit `5d0e069 docs(stage-1-1): registrar
findings...` (Stage 1.1, mergeado) usa exatamente o padrão proibido, e o hook
`check_commit_msg.py` não o pega (o regex aceita qualquer `[a-z0-9._-]+`). Esta
Stage corrigiu o próprio plano (usa `docs(shared)`), mas o precedente segue no
histórico.
**Direção sugerida:** decidir se §4(a) vale (então o hook deveria recusar escopo
que casa `stage[-_.]?\d`) ou se precisa de errata. Regra sem gate mecânico
regride — foi o que aconteceu.
**Stage/issue candidata:** issue avulsa de tooling (hook `check_commit_msg`).

<!-- END: post-execution -->

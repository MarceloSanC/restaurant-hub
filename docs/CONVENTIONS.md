# Conventions

Regras prescritivas. Não são sugestões.

Hierarquia conceitual (Step → Stage → Task) e fluxo de fases vivem em
[`PIPELINE.md`](./PIPELINE.md). Este documento fixa
nomes, frontmatter, status, branches, commits, versionamento e tamanhos.

---

## 0. Mapa de autoridade (fonte única por classe de regra)

Cada classe de regra tem **um doc dono** — a definição completa vive só
nele; os demais docs apenas apontam. Encontrou eco extenso divergente?
O dono vence; corrija o eco.

| Classe de regra | Doc dono (editar LÁ) |
|---|---|
| Nomenclatura, frontmatter, status, formato de branch/commit/título de PR, tamanhos | `CONVENTIONS.md` (este doc) |
| Fluxo git operacional, gates de PR, hotfix/release, comportamento bloqueante | [`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) |
| Hierarquia Step/Stage/Task, atomicidade, fases e gates conceituais, litmus issue×Stage, exceções | [`PIPELINE.md`](./PIPELINE.md) |
| Checklists operacionais de gate (concept / technical / saída da Stage) | [`RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md) Passos 5/7/10 |
| Arquitetura e regras de import | [`LAYOUT.md`](./LAYOUT.md) |
| Procedimento de auditoria e falsos verdes | skills `stage-audit` / `issue-audit` |

**Regra do eco:** citar uma regra fora do doc dono é permitido como
**1 frase + ponteiro** (a regra acionável fica no ponto de uso); o texto
normativo completo vive só na casa dona. A conformidade é garantida em
review; um guard mecânico opcional (`scripts/check_docs_pointers.py`, a
criar) pode complementá-la.

---

## 1. Nomenclatura

### Arquivos e pastas

| Item | Padrão | Exemplo |
|---|---|---|
| Pasta de Stage | `N.M-<kebab-slug>` (Step.Stage, sem zero-padding) | `1.1-bootstrap`, `2.3-s3-source`, `15.2-multi-tenant` |
| Concept de Stage | `concept.md` (fixo, dentro da pasta da Stage) | `docs/stages/1.2-domain-model/concept.md` |
| Technical de Stage | `technical.md` (fixo) | `docs/stages/1.2-domain-model/technical.md` |
| ADR de Stage | `N_M_NNNN-<kebab-slug>.md` em `docs/adr/` (`N.M` herda da Stage; `NNNN` 4 dígitos, sequencial **dentro do prefixo `N_M`** — o prefixo no nome do arquivo é o separador, não há subpasta por Stage) | `docs/adr/2_3_0001-stream-vs-batch.md` |
| ADR global | `0_0_NNNN-<kebab-slug>.md` em `docs/adr/` (`N.M` fixo em `0.0`; `NNNN` 4 dígitos, sequencial dentro do prefixo `0_0`) | `docs/adr/0_0_0001-hexagonal-from-day-one.md` |
| Runbook | `<kebab-slug>.md` | `docs/runbooks/local-dev-setup.md` |
| Audit report | `<kebab-slug>.md` em `docs/audits/<bc>/` (aninhado por BC; cross-cutting na raiz da categoria) | `docs/audits/billing/revenue-mismatch.md` |
| Domain knowledge | `<subdomain>.md` em `docs/domain/<bc>/` (espelha `features/<bc>/`) | `docs/domain/billing/invoicing.md` |
| Overview / Roadmap | fixos na raiz de `docs/` | `docs/overview.md`, `docs/roadmap.md` |

### Idioma do código

**Todo código-fonte deve ser escrito em inglês.** Esta regra aplica-se a:

- Nomes de arquivos e pastas de código (`.py`, `.sql`, `.yaml` de configuração interna)
- Classes, funções, métodos, variáveis, parâmetros, constantes
- Campos de DTO, modelos Pydantic, entidades de domínio
- Valores de enum internos (exceto enums que espelham valores de um sistema externo)
- Nomes de tabelas, colunas e índices do banco de dados (nossas tabelas)
- Nomes de módulos e pacotes Python

**Exceção estrita** — valores de string que identificam dados de um sistema
externo replicado (status, tipos, nomes de colunas de schemas espelhados em
queries SQL e mappers) podem preservar o idioma/grafia original da fonte.

Comentários e docstrings permanecem em português (conforme §4 de commits/PR).

### Slugs de Stage

- **Kebab-case, em inglês**, mesmo que o conteúdo seja em português.
- Curto (2–4 palavras). Descreve o **resultado**, não a atividade.
- O **número `N.M`** é prefixo da pasta/branch, **não conta como palavra
  do slug**.
- Bom: `1.1-bootstrap`, `2.3-s3-source-adapter`, `4.1-tenant-context`.
- Ruim: `1.1-fazer-setup`, `2.3-implementar-s3`, `4.1-mexer-no-tenant`.

### Numeração

- **Step:** identificador **numérico**, sequencial, sem zero-padding. Não
  recicla — Step 4 cancelado fica vago, Step 5 continua sendo Step 5.
  **Cresce indefinidamente.** Cada Step tem um **escopo temático claro**
  (ex.: "autenticação", "chat conversacional"; ver
  [`PIPELINE.md`](./PIPELINE.md) §4.1). **Nunca use letra** para um Step —
  a **única** exceção é `X`.
- **`X` — bucket de escopo órfão/futuro.** Trabalho **já definido** como
  Stage futura, mas cujo **Step-lar ainda não foi criado/planejado**, fica
  em stand-by sob `X` (ex.: `X.4-openai-gateway`). É o estado
  **pré-identidade**. **Migração obrigatória:** quando o Step que comporta o
  escopo for planejado, o item migra para lá **com o número desse Step** (se
  o escopo se manteve) — ou se desdobra em mais Stages, podendo virar um Step
  inteiro. Ganhar um número = achou seu Step. `X` é rótulo fixo, nunca
  renumerado (número = identidade, não posição).
- **Ordem de implementação = `depends_on`, não o número.** Como o número é
  identidade e não posição, a sequência cronológica real de implementação é
  dada pelo `depends_on` de cada Stage/issue — não pela ordem dos números.
- **Stage:** `N.M` dentro do Step `N`. Não recicla.
- **Task:** `task-NN` dentro do `technical.md` da Stage, zero-padded
  (`task-01`, `task-02`).
- **ADR de Stage:** nome do arquivo `N_M_NNNN-<slug-do-adr>.md` em `docs/adr/`;
  `adr_id` no frontmatter `N.M.NNNN`. `N.M` herda da Stage; `NNNN` é
  sequencial **dentro do prefixo `N_M`** (4 dígitos, não recicla) — o
  prefixo no filename é o separador namespace, **não há subpasta por
  Stage**. Cross-ref usa `adr_id` completo (ex.: `2.3.0001`) — sem
  ambiguidade entre Stages.
- **ADR global:** ADRs tomados antes ou fora do escopo de uma Stage
  específica (ex.: decisão fundacional de arquitetura). Vivem na
  mesma pasta `docs/adr/` (Stage e global coexistem; o prefixo
  `N_M` no filename basta para distinguir). Usam `N.M = 0.0` fixo —
  nome do arquivo `0_0_NNNN-<slug-do-adr>.md`; `adr_id: 0.0.NNNN`. `NNNN`
  sequencial dentro do prefixo `0_0`.

### Identificador da Stage — `stage_id` × número

A Stage tem **um** identificador, o `stage_id` (`N.M-<slug>`), e formas **derivadas** dele.
Cada superfície exige uma forma, e elas **não se trocam**: um placeholder que vira comando
com a forma errada não casa nada (HALT falso) ou casa a coisa errada (verde falso) — os dois
já aconteceram (issue #12).

| Forma | Exemplo | Onde se usa |
|---|---|---|
| `stage_id` — `N.M-<slug>` | `1.1-bootstrap` | `depends_on` (roadmap e frontmatter), coluna `Stage` do `roadmap.md`, campo `stage_id`, pasta `docs/stages/` |
| número — `N.M` | `1.1` | commits reservados (`stage 1.1: complete`, §4(b)), tag de Task (`[1.1/task-01]`, §4(a)), título de PR (`stage 1.1 —`, §4(c)) |
| `N-M` | `1-1` | branch da Stage (`feat/<num-issue>-1-1-bootstrap`, §4) |
| `N_M` | `1_1` | prefixo do arquivo de ADR (`1_1_0001-<slug-do-adr>.md`) — o slug ali é **do ADR**, não da Stage |
| `N.M.NNNN` | `1.1.0001` | `adr_id` (§2) |

A **issue** da Stage (`#<num-issue>`) não deriva do `stage_id`: liga-se a ele pelo `issue_id`
do `technical.md`. Na *Tabela de Issues* do roadmap, `Depende de` lista issues — inclusive de
Stage (`#43` é a `3.6-staff-http`, a pasta cujo `technical.md` tem `issue_id: 43`).

- **Conversão:** o número é o prefixo do `stage_id` até o primeiro hífen
  (`1.1-bootstrap` → `1.1`). O inverso exige o roadmap: o número não carrega o slug.
- **Placeholder que vira comando diz a forma** no ponto de uso: `<N.M>` é sempre o número;
  `<dep>` é um item de `depends_on`, logo um `stage_id`; o slug de ADR é `<slug-do-adr>`, para
  não colidir com o `<slug>` da Stage quando as variáveis de um prompt são substituídas.
- **A checagem de dependência não converte à mão:** `python scripts/check_stage_deps.py
  <stage_id>` recebe o `stage_id` e confere cada dependência — `done` no roadmap e
  `stage N.M: complete` no histórico (`--ref origin/develop` para "mergeado em develop").
  Roda também no `make docs-check`, sobre toda pasta de Stage
  ([ADR 0.0.0009](./adr/0_0_0009-stage-dependency-check-derives-the-number.md)).

---

## 2. Frontmatter

Todo doc tem frontmatter YAML no topo. Campos comuns + campos por tipo.

### Campos comuns (obrigatórios em todo doc)

```yaml
---
title: string                    # título humano em português
description: string              # 1 frase, o que este doc é
when-use: string                 # quando consultar este doc (para Claude e humanos)
keywords: [list, of, strings]    # termos para busca/grep
status: <enum por tipo de doc — ver §3>      # concept/technical: draft | done | archived
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
---
```

### Campos adicionais por tipo

**`overview.md`:**
```yaml
project_name: string
stakeholders: [list]
```

**`roadmap.md`:**
```yaml
last_reviewed_at: YYYY-MM-DD     # forçado a atualizar ao fechar Stage
```

**`concept.md` e `technical.md` (de Stage):**
```yaml
stage_id: N.M-<slug>             # bate com o nome da pasta
stage_title: string              # título humano da Stage
step_id: N                       # Step que contém esta Stage
step_title: string               # título humano do Step
depends_on: [list of stage_ids]  # vazio se nenhuma
```

**`technical.md` (adicional):**
```yaml
concept_ref: ./concept.md        # caminho relativo
issue_id: integer                # número da issue do GitHub (ex: 42)
branch: feat/<num-issue>-<N-M>-<slug>   # ex: feat/42-2-3-s3-source-adapter
tasks_count: integer             # quantas Tasks tem
```

**ADRs:**
```yaml
adr_id: N.M.NNNN                 # Stage: 2.3.0001 — N.M herda da Stage; Global: 0.0.NNNN
decision: string                 # 1 frase resumindo a decisão
status: proposed | accepted | superseded | deprecated
superseded_by: N.M.NNNN          # ex: 2.3.0002 — apenas se status=superseded
context_stage: N.M-<slug>        # Stage em que a decisão foi tomada (mesmo para ADRs globais)
bounded_context: <bc>            # BC ao qual a decisão pertence — ver regra abaixo
```

**Regra de `bounded_context` (obrigatório em todo ADR):** o valor **deve
pertencer ao conjunto de `bounded_context` que o `roadmap.md` declara** —
**não se inventa um BC novo no ADR**. ADR de Stage herda o BC da sua
`context_stage` (o BC dessa Stage no roadmap); ADR **global** (`0_0_*` /
`1_1_*`) usa `transversal`. Esse campo torna "ADRs do mesmo BC" um `grep`
determinístico (etapa de carga de contexto do fluxo de Stage) em vez de
julgamento em prosa. Gate mecânico: `scripts/check_adr_bounded_context.py`
(em `make docs-check`) exige o campo e valida o valor contra o conjunto
extraído do roadmap.

**Frontmatter YAML e `adr_id`** ([ADR 0.0.0015](./adr/0_0_0015-adr-and-domain-frontmatter-are-machine-validated.md),
issue #102): o bloco entre `---` tem de passar no `yaml.safe_load` — valor que
começa com crase ou contém `: ` vai entre aspas simples (``decision: '`Port` ganha…'``).
O `adr_id` é texto `N.M.NNNN`, igual ao prefixo `N_M_NNNN` do nome do arquivo e
**único** entre os ADRs: sessões paralelas que escolhem o mesmo número não
conflitam no git (os slugs diferem), então o número livre se confere em todas as
branches abertas, e o choque se resolve renumerando o ADR mais novo. Nos docs de
`docs/domain/`, o mesmo gate exige que `references` e links relativos resolvam,
que todo ADR linkado no corpo esteja no `references` e que nenhuma "Lacuna para o
concept da Stage N.M" fique aberta com a Stage `done`. Gate mecânico:
`scripts/check_doc_frontmatter.py` (em `make docs-check`).

**Runbooks:**
```yaml
runbook_id: kebab-slug
triggers: [list of strings]      # quando rodar este runbook
estimated_duration: string       # ex.: "15min"
```

---

## 3. Status — máquina de estados

### 3.1 `concept.md` e `technical.md` — máquina simplificada (dois estados)

```
draft ◄──────► done ──────► archived
```

- **`draft`**: rascunho, desde a criação. Não pode ser usado como input
  para o gate da fase seguinte enquanto não estiver `done`.
- **`done`**: aceito no gate humano. Pode **regredir para `draft`**
  quando uma fase posterior (tipicamente Fase 3B revisando o concept,
  ou Fase 4 revisando o technical antes do início da execução) revela
  gap material — ver §3.2.
- **`archived`**: foi `done`, mas a Stage foi descartada/recortada e o
  artefato saiu do plano vivo. Mantido por histórico (ver §5).

Por que dois estados: na prática os estados intermediários
(`in_progress`, `review`) não eram usados — o gate humano flipa direto
`draft → done` no commit reservado. Manter máquina enxuta reduz fricção
sem perder rastreabilidade (git log carrega a transição).

### 3.2 Regressão `done → draft`

Permitida (e esperada) quando o trabalho de uma fase posterior revela
gap material em um artefato já `done`. O caso típico é a Fase 3B
revelando lacuna no Concept aprovado.

Procedimento:

1. Reabrir o artefato. Mudar `status` de volta para `draft`. Atualizar
   `updated_at`.
2. Commit reservado de regressão (não segue Conventional Commits no
   título; segue a forma fixa):
   ```
   chore(concept): revert to draft — revision-from-technical: <motivo curto>

   Refs #<num-issue>
   ```
   Variantes: `chore(technical): revert to draft — revision-from-execution: <motivo>`.
3. Aplicar a correção, re-rodar o gate da fase, novo commit reservado
   de aprovação (ex.: `stage N.M: conceptual approved`).

**Invariante de início da Fase 4 (execução):** `concept.status == done`
**e** `technical.status == done` simultaneamente. Se qualquer um regredir
para `draft`, a Fase 4 trava até ambos voltarem a `done` (Passo 8 do
[`RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md)).

Regressões depois de iniciada a Fase 4 caem em §3.4 (seção pós-execução
do technical) — sem mudar status; usar `[decision]`/`[finding]`/`[deviation]`
ou loop reverso completo.

### 3.3 Outros artefatos — máquina ampliada

Demais artefatos versionados (overview, roadmap) usam o conjunto
ampliado quando faz sentido — em prática:

- **`overview.md`:** `draft → done`. `in_progress`/`review` opcionais.
- **`roadmap.md`:** permanece `in_progress` da Stage `1.1-bootstrap` até
  o projeto encerrar (não há `done` para o roadmap inteiro; o que vai a
  `done` são as Stages dentro dele).
- **ADRs:** máquina própria — `proposed | accepted | superseded | deprecated`.
- **Runbooks, skills:** máquinas próprias documentadas em PIPELINE §13
  (skills) e em seus templates (runbooks).

### 3.4 Seção pós-execução do `technical.md` (§7 do template)

A seção §7 ("Execução — post-hoc") do `technical.md` é **a única parte
editável após `status: done`** — **enquanto a Stage está em execução**,
isto é, **antes de a branch da Stage mergear** em `develop`/`main`. O
objetivo do freeze é impedir que a execução reescreva o plano aprovado
sem rastro; desvios vão para a §7, onde são revisados.

**Depois do merge**, o `technical.md` vira **doc de referência mutável**:
alinhá-lo à realidade (ex.: renomear identificadores que mudaram no
código, padronizar tags) é legítimo e dispensa cerimônia — o plano
original aprovado permanece no git. Regras durante a janela de execução:

- Delimitada por marcadores `<!-- BEGIN: post-execution -->` e
  `<!-- END: post-execution -->`. Qualquer diff fora desses marcadores
  em um `technical.md` com `status: done` **cuja Stage ainda não mergeou**
  é rejeitado pelo script `scripts/check_technical_postexec.py` (rodado
  no `make docs-check`, dentro do `make check`, e no Passo 10 do
  runbook). A detecção de merge usa
  ancestralidade do commit `stage N.M: technical approved` em relação a
  `develop`/`main`; Stage mergeada → checagem pulada.
- **`updated_at` do frontmatter não muda** com edições nessa seção. O
  metadado por entrada (data + autor no header) é o audit trail.
- **Regra de pergunta antes da nota:** ao encontrar durante a Fase 4
  algo **material** não previsto em outras seções do `technical.md`, no
  `concept.md` ou em ADRs (afeta contrato, fronteira, critério de aceite
  ou modelo de dados), **pausar a execução**, levantar a pergunta para o
  humano com 2–4 opções e uma marcada como **recomendada** + razão (via
  `AskUserQuestion` ou equivalente), e só então registrar a entrada.
  **Exceção (decisão barata sem âncora):** uma escolha local
  **trivialmente reversível** que não se ancora num princípio
  (concept/ADR/skill) é decidida pela IA **sem pergunta** e registrada
  como `[decision]` — o registro existe para a auditoria pegar um
  alinhamento errado barato, não para pedir aprovação.
- Entradas seguem três categorias: `[decision]` (decisão tomada durante
  a execução), `[finding]` (gap a tratar em próxima Stage), `[deviation]`
  (ajuste pequeno aplicado em relação ao plano). **Tags sempre em inglês**
  (são identificadores, como código — §1); o corpo da entrada é em PT.
  Formato detalhado no template `stage-technical.md` §7.
- **Durante a execução** (Stage não mergeada), mudar algo em §1–§6 do
  `technical.md` após `done` exige regressão para `draft` (§3.2). Nunca
  editar §1–§6 silenciosamente nessa janela. Pós-merge a restrição não
  se aplica (doc de referência mutável).

### 3.5 Diagrama legado (mantido para overview/roadmap)

```
draft ──────► in_progress ──────► review ──────► done
  │                │                  │             │
  └─► archived ◄───┴──────────────────┴─────────────┘
```

### 3.6 Label de status de auditoria no PR (gate `audit-gate`)

O corpo de todo PR carrega **uma linha canônica** que declara o estado da
auditoria do fluxo single-session — a máquina de estados que o workflow
`audit-gate` (CI) lê para **sinalizar se a auditoria aconteceu** (fecha o
handoff antes lembrado por humano). É uma máquina **distinta** da de status
de doc (§3.1/§3.5), embora reuse os rótulos `review`/`complete`:

```
> **Auditoria:** `review`
```

Enum (fonte única — todo outro doc/prompt/skill **aponta** para cá, não
redefine):

| Valor | Significado | Check `audit-status` |
|---|---|---|
| `draft` | implementação em andamento (WIP) | **vermelho** |
| `review` | pronto, aguardando auditoria | **vermelho** |
| `complete` | auditoria realizada (`stage-audit`/`issue-audit`) | **verde** |

> ⚠️ **Vermelho ≠ merge bloqueado.** Branch protection não está disponível
> (repo **privado** em GitHub **Free** — ver [`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
> §Gates de PR), então **nenhum check é *Required***: um PR com `audit-status`
> vermelho fica `mergeStateStatus: UNSTABLE`, **não** `BLOCKED`, e `gh pr merge`
> passa assim mesmo. O label **sinaliza**; quem segura o merge de uma entrega não
> auditada é **disciplina humana/do agente**, não o GitHub. Ao migrar para repo
> público ou Pro, tornar `audit-status` *Required* e atualizar esta nota.

- **Default do template** ([`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md)):
  `review`. Os prompts single-session **preservam** o label; **não** o
  editam à mão.
- **Só a sessão de auditoria** grava `complete` (fase de aplicação de
  `stage-audit`/`issue-audit`), junto do comentário do veredito no PR.
  Gravar `complete` à mão sem auditoria burla o gate.
- **Gate `audit-gate`** ([`.github/workflows/audit-gate.yml`](../.github/workflows/audit-gate.yml)):
  extrai o valor da linha canônica e passa **iff** `complete` — *fail
  closed* (ausente/inválido → falha). Lê **só** essa linha, então as
  palavras `draft`/`review`/`complete` podem aparecer livremente na prosa
  do corpo sem falsear o gate.

### Exceção — docs estruturais do template

Os documentos estruturais do template — `PIPELINE.md`, `CONVENTIONS.md`,
`LAYOUT.md`, `GIT-WORKFLOW.md`, `RUNBOOK-STAGE-LIFECYCLE.md` (todos em
`docs/`), `README.md` (raiz e boilerplate) e `CLAUDE.md` — são
**exceção** ao frontmatter padrão de §2: **não carregam
`created_at`/`updated_at`/`status`**. Justificativa:

- São contratos do template, não artefatos versionados por Stage.
- Mudam pouco e por motivos amplos (revisão estrutural, refactor de
  pipeline); o histórico fica no git, sem necessidade de máquina de
  estado.
- Frontmatter em docs que mudam pouco tende a ficar stale (`updated_at`
  esquecido); melhor ausente do que mentindo.

A mesma exceção vale para `SKILL.md` (justificada em PIPELINE §13 —
lifecycle expresso por `metadata.status`).

### Mapeamento gate ↔ commit ↔ status

| Gate aprovado | Commit (mensagem reservada) | Status do artefato |
|---|---|---|
| Overview | `docs(overview): approved` | `overview.md → done` |
| Roadmap | `docs(roadmap): approved` | `roadmap.md → in_progress` (vive até o projeto acabar) |
| Concept da Stage (Fase 3A) | `stage N.M: conceptual approved` | `concept.md → done` |
| Concept regredido (3B revelou gap) | `chore(concept): revert to draft — revision-from-technical: <motivo>` | `concept.md → draft` |
| Technical da Stage (Fase 3B) | `stage N.M: technical approved` | `technical.md → done` |
| Technical regredido (4 revelou gap antes da execução) | `chore(technical): revert to draft — revision-from-execution: <motivo>` | `technical.md → draft` |
| Stage completa (Fase 4) | `stage N.M: complete` | Stage N.M no roadmap → `done` |

**Regras:**
- **Pré-requisito de Fase 3A (bloqueante):** a Stage só pode iniciar a
  Fase 3A (criar `concept.md` em qualquer estado, inclusive `draft`)
  **se já existir uma issue correspondente no backlog do GitHub**,
  verificável via `gh issue view <num>`. Sem issue: parar e criar a
  issue antes de qualquer artefato. O `issue_id` registrado no
  frontmatter do `technical.md` é o ponto de verificação programática
  (ver `scripts/check_stage_issue.py` em `make docs-check`).
  Issue-first é princípio bloqueante ([`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
  §Princípios fundamentais #1).
- `concept.md` só pode estar `done` se passou no checklist de validação
  interno (§12 do template).
- `technical.md` pode entrar em `draft` a qualquer momento — não precisa
  esperar `concept.md` estar `done`. **Mas** o gate da Fase 3B
  (`stage N.M: technical approved`) exige `concept.status == done` no
  momento da aprovação.
- Fase 4 só pode iniciar (Passo 8 do runbook) com `concept.status == done`
  **e** `technical.status == done` simultaneamente.
- Stage só pode ser marcada `done` no `roadmap.md` se `concept.md` e
  `technical.md` estão `done` **e** o gate de saída da Stage foi cumprido
  (§3 do `technical.md`).

---

## 4. Branches e commits

### Branches

**Uma Stage = uma issue + um branch.** O branch carrega todos os
commits da Stage, do `conceptual draft` ao `complete`, e abre PR contra
`develop` quando a Stage termina (premissa
[`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)).
**Não há sub-PRs internos da Stage.**

Formato: `<tipo>/<num-issue>-<N-M>-<slug>` — `N.M` em kebab (Stage 2.3
vira `2-3`). Tipo segue GIT-WORKFLOW (`feat` para Stage nova, `fix`
para correção via Stage, `refactor`, etc.; em geral `feat`).

```
develop
├── feat/42-1-1-bootstrap            # Issue #42, Stage 1.1
├── feat/57-1-2-domain-model         # Issue #57, Stage 1.2
├── feat/89-2-3-s3-source-adapter    # Issue #89, Stage 2.3
└── docs/<change-desc>               # mudanças só de docs, fora de Stage
```

**Revisões pós-Stage** (branches criadas depois que o PR da Stage foi
mergeado) voltam ao formato **genérico** definido em
[`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) §Branches —
`<tipo>/<num-issue>-<slug>`, **sem `<N-M>`**. O `<N-M>` identifica a
execução da Stage; depois que ela fechou, o trabalho passa a ser
bug/chore/doc normal, com nova issue própria. Rastreabilidade fica no
`Refs #<num-issue>` do commit, não no nome da branch.

Promoção de `develop` para `main` ocorre na release (ver GIT-WORKFLOW).

### Commits

Há **duas classes** de mensagens de commit:

#### (a) Commits de Task — Conventional Commits + `[N.M/task-NN]` + `Refs #<issue>`

```
<tipo>(<escopo>): <descrição imperativa em português> [N.M/task-NN]

- <bullet 1: o que mudou e por quê — 1 frase>
- <bullet 2: outro aspecto da mesma mudança lógica>
- <bullet 3+: opcional, conforme a complexidade da Task>

Refs #<num-issue>
```

Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`,
`style`, `build`, `ci` (lista espelhada em `ALLOWED_TYPES` de
`scripts/check_commit_msg.py` — o hook é o gate; mudou lá, atualizar aqui).

**Escopo mínimo (regra de ouro):** o `<escopo>` é o **menor recorte
que ainda faz sentido sozinho** — feature/módulo/bounded context da
mudança, **NÃO** o nome da Stage. Quanto mais estreito, melhor.
**Escopo em ASCII/kebab** (mesmo critério de slug de branch: ver §1)
para não exigir acentos no terminal; descrição é livre em PT-BR
acentuado:

- ✅ `feat(ingestion): adicionar S3 source adapter` — escopo é o BC
  `ingestion`, descrição em PT.
- ✅ `fix(payment.retry): limitar backoff exponencial em 30s` —
  escopo pode ser sub-módulo (`payment.retry`) quando isso desambigua.
- ❌ `feat(stage-2.3): adicionar S3 source adapter` — Stage não é escopo.
- ❌ `chore(repo): um monte de fixes` — escopo amplo demais; quebrar
  em vários commits com escopos mínimos diferentes.

Se a mudança realmente toca vários escopos independentes (cross-cut),
quebre em **vários commits** — um por escopo. "Sou preguiçoso, deixa
tudo num commit só" é red flag.

**Body em bullet points, sempre (≥ 1 bullet).** O body explica **o
quê** e **por quê** em itens de 1 frase. Listas longas (>8 bullets)
sinalizam Task grande demais; agrupar ou quebrar. Permitido omitir
body **apenas** em commits triviais e auto-explicativos (rename
puro, ajuste de typo) — e mesmo assim com `Refs` no rodapé.

Subject e body em **português** (ver [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)
§Princípios fundamentais #3); escopo permanece em ASCII/kebab;
`Refs #<num-issue>` no rodapé.

Exemplos (rodapé `Refs #89` em todos):

```
feat(ingestion): adicionar S3 source adapter [2.3/task-01]

- Implementar IngestionSource port adapter usando aioboto3
- Streamar objetos multipart em chunks de 8MB para limitar RSS
- Mapear erros do client S3 para IngestionError preservando causa

Refs #89
```

```
test(ingestion): cobrir happy path do adapter S3 [2.3/task-02]

- Fake do aiobotocore client devolvendo objeto de 3 partes
- Assertar que chunks chegam ordenados e concatenação bate com input
- Cobrir mapeamento credenciais ausentes → IngestionError

Refs #89
```

```
docs(roadmap): marcar stage 2.3 como done [2.3/--]

- Mudar status da stage 2.3-s3-source-adapter para done
- Atualizar last_reviewed_at no frontmatter do roadmap

Refs #89
```

**Um commit por Task.** Se uma Task precisou de mais de um commit, ela
estava grande demais — fica como lição para a próxima.

##### Marca de Task — gramática e sufixos `-fix`/`-extra`

A marca fecha o subject, depois de **um espaço**: `[<dono>/<posição>]`.
É a gramática que o hook `commit-msg` valida — `TAG_PATTERN` de
`scripts/check_commit_msg.py` (o hook é o gate; mudou lá, atualizar aqui).

| Dono | Forma | Branch |
|---|---|---|
| Stage | `N.M` — o **número** da Stage (`4.1`), não o `stage_id` (`4.1-scheduling-domain`) | de Stage |
| Issue avulsa | `#<num>` — o número da issue (`#34`) | de issue avulsa ([`PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md)) |

| Posição | O commit… | Exemplo |
|---|---|---|
| `task-NN` | entrega a Task `NN` do plano (`technical.md` §2; na issue avulsa, a sub-task `NN` da decomposição) | `[2.3/task-01]`, `[#34/task-02]` |
| `task-NN-fix` | **corrige** a Task `NN`, já commitada — achado de Checkpoint C ou regressão mid-stage de erro local | `[3.1/task-04-fix]`, `[#34/task-02-fix]` |
| `task-NN-extra` | entrega uma Task **acrescentada** durante a execução, fora do plano — tipicamente o teste que a auditoria de testes pediu | `[3.2/task-14-extra]`, `[#34/task-06-extra]` |
| `--` | não pertence a Task nenhuma (off-task, subseção seguinte) | `[2.3/--]`, `[#34/--]` |

Toda posição vale para os dois donos.

Regras:

1. **Correção não reusa a marca da Task.** O commit que corrige a Task
   `NN` leva `task-NN-fix`, nunca `[N.M/task-NN]` de novo: reusada, a
   marca fica ambígua com o commit canônico da Task (F1 do Checkpoint C
   da Stage 3.1, na §7 do
   [`technical.md`](./stages/3.1-staff-domain/technical.md) dela). Mais
   de uma correção da mesma Task repete `task-NN-fix`; o subject as
   distingue.
2. **Task extra continua a numeração, não reabre o plano.** O `NN` de
   `-extra` segue o do plano: com `tasks_count: 13`, as Tasks extras são
   `task-14-extra`, `task-15-extra`… Elas não mudam o `tasks_count` nem
   as §1–§6 do `technical.md`; a justificativa vai numa entrada da §7
   (§3.4) — na issue avulsa, no corpo do PR. Cada rodada da auditoria de
   testes que pede teste novo é uma Task extra nova (o próximo `NN`), não
   um ordinal.
3. **`-fix` corrige, `-extra` acrescenta.** Decide a origem: achado de
   revisão (Checkpoint C) ou regressão sobre a entrega de uma Task →
   `-fix`, mesmo quando a correção é só de teste; lacuna que a auditoria
   de testes encontrou → Task extra.
4. **Opcional para o hook, malformada nunca.** O hook aceita subject sem
   marca — a obrigação de marcar todo commit do branch da Stage é desta
   seção e do review, não dele. O que ele recusa é o subject que
   **termina em `]`** sem terminar numa marca da gramática; até a issue
   #34, a descrição engolia a marca malformada e o commit passava sem
   validação. Descrição que precisa terminar em colchetes recebe a marca
   depois deles ou é reescrita.
   - ❌ `[4.1/tsk-3]`, `[41/--]`, `[4.1/task-03-fix2]`, `[4.1-scheduling-domain/--]`
5. **O histórico não se reescreve.** Commits anteriores a esta gramática
   com ordinal (`-fix2`, `-extra2`…) ou com `-extra` sobre o número de
   uma Task do plano ficam como estão — aceitos sem ação retroativa, como
   o F1 da 3.1. Escrito hoje, o ordinal o hook recusa; o `NN` da Task
   extra ele não confere (não conhece o `tasks_count`) — fica com o review.

##### Tag `[N.M/--]` — commit no branch da Stage que não pertence a uma Task

`[N.M/--]` (dois hífens) é o **placeholder de off-task**: marca commits
feitos no branch da Stage que **não fazem parte** de uma das Tasks
numeradas em `technical.md` §2. Usar quando:

- **Atualização de roadmap/overview** ao fechar a Stage:
  `docs(roadmap): marcar stage 2.3 como done [2.3/--]`
- **Hotfix dentro do branch da Stage** para destravar `make check`/CI
  antes da próxima Task (ex.: arquivo do template fora do escopo da
  Stage que quebrou após upgrade de dep):
  `fix(tooling): restaurar make check no scaffold limpo [1.1/--]`
- **Reordenação puramente mecânica** que não cabe em Task (ex.:
  renomear arquivo já incluído numa Task anterior):
  `chore(repo): renomear helpers/io.py para helpers/files.py [2.1/--]`

Regras do `[N.M/--]`:

1. **Tipo, escopo e `Refs #<issue>` continuam obrigatórios** — só a
   posição da Task vira `--`. Não é "vale-tudo".
2. **Justificativa no body, sempre.** Diga **por que** isto não foi uma
   Task formal (urgência, escopo cruzado, descoberta pós-`approved`).
   Um `[N.M/--]` sem justificativa é red flag — provavelmente devia
   ter sido uma Task ou uma regressão do `technical.md` (§3.2).
3. **Não substitui regressão.** Se o gap exige reescrita do
   `concept.md`/`technical.md` §1–§6, usar `chore(concept|technical):
   revert to draft — ...` (§3.2), **não** um `[N.M/--]`.
4. **Não é commit reservado de gate.** Para os gates fixos use as
   mensagens reservadas de §4(b) (`stage N.M: ... approved`, etc.).
5. **Frequência saudável: 0–2 por Stage.** Três ou mais é sinal de
   Stage mal recortada — escopo escapou do `technical.md`.

#### (b) Commits reservados de gate — texto fixo, não seguem Conventional Commits

Marcam aprovação de fase no branch. No branch de uma Stage, carregam
`Refs #<num-issue>` no rodapé:

```
stage N.M: conceptual draft

Refs #<num-issue>
```

Variantes (mesma estrutura):
- `stage N.M: conceptual approved`
- `stage N.M: technical draft`
- `stage N.M: technical approved`
- `stage N.M: complete`

Variantes **de regressão** (status `done → draft` em concept ou technical;
ver §3.2). Não seguem Conventional Commits no título; texto fixo:

- `chore(concept): revert to draft — revision-from-technical: <motivo curto>`
- `chore(technical): revert to draft — revision-from-execution: <motivo curto>`

Carregam `Refs #<num-issue>` no rodapé. Após reaplicar a correção,
seguir o gate normal da fase (`stage N.M: conceptual approved` ou
`stage N.M: technical approved`).

Para overview/roadmap (PRs fora do fluxo de Stage; podem não ter issue
associada — nesse caso, dispensam `Refs #`):

```
docs(overview): approved
docs(roadmap): approved
```

Mensagens reservadas são as únicas que **não** precisam de referência
`[N.M/task-NN]` no título. Qualquer outra mudança no branch da Stage é
commit de Task (classe a).

**Exceção — bootstrap:** durante o procedimento de inicialização de
projeto (`RUNBOOK-INIT-PROJECT.md`) ou adoção em legado
(`RUNBOOK-ADOPT-EXISTING.md`), as mensagens reservadas de overview/roadmap
carregam um sufixo de contexto identificando qual projeto/modo gerou o
commit:

```
docs(overview): approved [projects/<projeto-slug>]
docs(roadmap):  approved [projects/<projeto-slug>]
docs(overview): approved [projects/<projeto-slug>] (adoption)
docs(roadmap):  approved [projects/<projeto-slug>] (adoption)
```

Sufixos só aparecem em commits de bootstrap (cwd no template, antes do
projeto destino estar inicializado). No projeto destino as mensagens
reservadas voltam ao formato fixo (sem sufixo).

#### (c) Título de PR — Conventional Commits + identificador na descrição

O título do PR segue Conventional Commits em português, com **escopo
obrigatório** e o identificador da Stage/issue na descrição, após um
travessão `—`. Dois formatos, conforme a origem do branch:

- **PR de Stage:** `<tipo>(<escopo>): stage N.M — <descrição>`
  - ✅ `feat(billing): stage 12.10 — relatório de inadimplência`
- **PR de branch** (pós-Stage ou issue avulsa): `<tipo>(<escopo>): issue #<num> — <descrição>`
  - ✅ `fix(tooling): issue #53 — corrigir gate do pre-commit`

O `<escopo>` é o **BC/módulo** da mudança (mesma regra de escopo mínimo
da classe (a) — ASCII/kebab), **nunca** a Stage:

- ❌ `feat(stage-12.10): relatório de inadimplência` — Stage não é escopo.
- ❌ `feat: stage 12.10 — relatório de inadimplência` — escopo ausente.

O número da Stage (`stage N.M`) ou da issue (`issue #<num>`) vai na
**descrição**, depois do `—`, nunca no escopo. Não há validação
programática de título de PR (diferente do subject de commit, que passa
pelo hook `commit-msg`); a conformidade é garantida no code review.
Detalhes operacionais e exemplos `gh pr create`:
[`GIT-WORKFLOW.md`](./GIT-WORKFLOW.md) §Pull Requests.

---

## 5. Versionamento de docs

Docs vivem no git, então o histórico é o versionamento. Mas:

- **Concept/Technical — revisão leve via regressão:** se uma decisão
  mudou enquanto a Stage ainda está em andamento (Fase 3B revelou gap
  no concept; Fase 4 ainda não começou e o technical precisa de ajuste),
  use a **regressão `done → draft`** (§3.2). O git log carrega a
  transição via os commits reservados; não há cópia paralela.
- **Concept/Technical — revisão pesada por arquivamento:** se a Stage
  foi recortada/redirecionada e o artefato anterior não representa mais
  o plano vivo, **mover o atual** para
  `concept.archived-YYYY-MM-DD.md` (idem para `technical.archived-...`),
  marcar `status: archived` no movido, e criar novo. Aplicação
  **manual** pelo dev que detectar a mudança.
- **§7 do `technical.md` (post-execution) é exceção:** editável após
  `status: done` sem regressão nem arquivamento. Ver §3.4.
- **O *corpo da decisão* de um ADR `accepted` não é editado destrutivamente.**
  O corpo (Context / Decision / Alternatives / Consequences) é registro
  histórico — preserva o "porquê decidimos X no tempo T". Reescrevê-lo apaga
  história e é **proibido**. Há **três** formas **não-destrutivas** de manter
  um ADR honesto sem reescrever o corpo — e uma **terceira** para o caso
  intermediário (introduzida na Stage 3.5, ADR 3.5.0001 §Status):
  - **A decisão mudou** → criar **novo ADR** com `superseded_by` apontando
    para o antigo; o antigo passa a `superseded`.
  - **A decisão se mantém no todo, mas uma cláusula de uma seção foi
    substituída por ADR posterior** (supersessão **parcial**) → o ADR novo
    declara em `## Status` o que supera; o ADR antigo permanece `accepted` e
    ganha uma seção **`## Supersessão parcial`** *append-only*, com nota datada
    (`**YYYY-MM-DD — <cláusula> superada por ADR X.Y.ZZZZ.**`) que **cita** a
    cláusula e aponta o ADR novo, **sem editar o corpo**. Bumpa `updated_at`.
    Não é errata (errata corrige ponteiro/fato sem mudar conteúdo de decisão) e
    não é `superseded` (o resto da decisão continua valendo).
  - **A decisão se mantém, mas uma premissa/fato declarado se revelou
    incorreto** (sem mudança de conteúdo de decisão) → adicionar um **banner de
    errata** *append-only* no topo do
    ADR (logo após o título), no formato
    `> ⚠️ **Errata (YYYY-MM-DD):** <fato corrigido> — ver <auditoria/ADR>`,
    **sem editar o corpo**. A errata **não** muda `status` (a decisão continua
    válida) e bumpa apenas `updated_at`. Serve para **impedir que um
    leitor/decisão futura tome a premissa errada como verdade** — preservando
    o registro original (marcado), não o apagando. Se a premissa corrigida
    **derruba** a decisão, então não é errata: é `superseded` (caso acima).
- **Roadmap pode ser editado livremente**, mas `updated_at` e
  `last_reviewed_at` devem refletir a realidade.
- **Citação ao roadmap — por âncora, nunca por número de linha**
  ([ADR 0.0.0012](./adr/0_0_0012-cite-the-roadmap-by-stable-anchor.md), issue #79).
  O roadmap cresce no meio — cada issue nova entra na Tabela de Issues, acima de
  todos os blocos de Step — e uma citação `` `roadmap.md` <linha> `` passa a apontar
  para outro conteúdo no PR seguinte, sem erro em lugar algum. A forma é seção +
  rótulo:
  - **Seção:** `§Stage N.M`, `§Step N` ou `§"<título de seção do roadmap>"`
    (ex.: `§"Tabela de Stages"`, `§"Lacunas conhecidas"`).
  - **Rótulo** (opcional, depois de ` › `, vários separados por vírgula):
    `"<texto em negrito>"` (`"Descrição humana"`, `"Resultado de negócio"`,
    `"ROADMAP-3"`), `` `<literal>` `` (chave do YAML como `` `definition_of_done` ``,
    célula `` `4.1-scheduling-domain` ``, aresta `` `S31 --> S41` ``),
    `nota AAAA-MM-DD` (nota datada da seção) ou `#N` (linha da Tabela de Issues).
  - **Exemplo:** `` `roadmap.md` §Stage 4.1 › "Descrição humana", `definition_of_done`;
    §Step 4 › nota 2026-09-14 ``. Âncoras de seções diferentes separam-se por `;`.
  - **Gate:** `scripts/check_roadmap_citations.py` (no `make docs-check`) reprova
    número de linha depois de uma referência ao roadmap e âncora cuja seção ou
    rótulo não existe — renomear seção ou rótulo do roadmap exige atualizar quem
    cita. Fora do gate: o próprio roadmap e a §7 dos `technical.md`, que é registro
    histórico (remapeamentos passados contados por número ficam como estão).
- **Lockfile de dependências (`uv.lock`):** **versionado** por padrão
  (este template gera aplicações; lock garante reprodutibilidade
  dev/CI/prod e segurança via SBOM). O `scripts/init-project.py` roda
  `make setup` antes do primeiro commit, então o `uv.lock` gerado
  entra no commit inicial. Quem mexer em `pyproject.toml` regenera o
  lock no **mesmo commit** que altera a dep — sem PRs separados de
  "lock-only". Se o projeto algum dia virar biblioteca publicada em
  PyPI, mover `uv.lock` para `.gitignore` (decisão consciente, não
  default). Recomendação espelha [docs oficiais do uv](https://docs.astral.sh/uv/concepts/projects/sync/#checking-the-lockfile).

---

## 6. Tamanhos saudáveis

| Artefato | Tamanho saudável | Sinal de alarme |
|---|---|---|
| `overview.md` | 1–3 páginas | >5 páginas: ninguém lê. |
| `roadmap.md` | 1 página + tabelas com células de **1–2 linhas + ponteiro** | Célula narrativa (história/supersessão inline): mover para ADR/stage docs/§Histórico — o histórico tem casa própria. |
| `concept.md` (por Stage) | 2–5 páginas | >8 páginas: Stage grande demais, dividir. |
| `technical.md` (por Stage) | 3–10 páginas | >15 páginas: Stage grande demais. |
| Stages por Step | 1–8 | ≥ 10: reexaminar o recorte — Step temático coeso pode crescer por acreção, mas conferir se não virou guarda-chuva de temas distintos. |
| Tasks por Stage | 3–12 | ≥ 14: quebrar a Stage. |
| ADR | 1–2 páginas | >3 páginas: decisão grande demais, dividir em ADRs menores. |

Faixas são guia, não barreira rígida. Ultrapassar é sinal para
re-examinar, não para abortar.
---
title: Git Workflow Padrão
description: Fluxo de versionamento e CI/CD prescritivo para projetos colaborativos
when-use: Consultar antes de qualquer mudança de código. Todos os membros do time devem seguir este fluxo.
keywords: [git, github, workflow, ci-cd, pr, code-review, deploy]
status: done
created_at: 2026-05-12
updated_at: 2026-11-02
---

# Git Workflow Padrão

Fluxo de versionamento e CI/CD para projetos colaborativos. Garante rastreabilidade, qualidade de código, e deploy seguro.

## Princípios fundamentais

1. **Issue-first**: nenhuma alteração começa sem card de issue. O título da issue origina o nome da branch.
2. **Gates bloqueantes**: coverage ≥ 90%, CI verde, aprovação obrigatória. Não pula-se etapa.
3. **Português em commits/PRs/issues; inglês em branches e código**:
   mensagens de commit (subject + body), títulos e corpos de issue,
   títulos e corpos de PR, comentários de code review — todos em
   **português**. Conventional Commits sim, mas com a descrição em PT
   (`feat(auth): adicionar login com Google`). **Nomes de branch em
   inglês** (slug kebab-case, ver [`./CONVENTIONS.md`](./CONVENTIONS.md)
   §1), pois entram em URLs, tabs de IDE e referências de Stage onde
   identificadores estáveis ASCII evitam fricção. Identificadores
   técnicos de código também em inglês.
4. **GitHub CLI (`gh`) preferencial**: usar quando disponível. Fallback para `git` puro se necessário.
5. **Sem deploy manual**: produção só via merge em `main`. Dev só via merge em `develop`. SSH em prod é proibido.
6. **Merge commit preserva história**: NUNCA squash, NUNCA rebase no merge. Branches trazem toda sua contexto.
7. **Até duas branches em execução, cada uma na sua worktree**: no
   máximo **duas** branches ainda sem PR aberto ao mesmo tempo, e só se
   **não conflitam** (critérios em §"Branches em execução"). **Toda**
   implementação roda numa worktree própria criada por
   `scripts/worktree-new.py`; o **checkout principal fica sempre em
   `develop`, limpo** — nunca se cria nem se troca de branch nele (o hook
   `.claude/hooks/git_guard.py` recusa). Ver §"Branches em execução" para
   critérios, comando, limpeza e o procedimento de PR parcial.
   **Na orquestração autônoma** ([ADR 0.0.0008](./adr/0_0_0008-autonomous-orchestrator-parallel-worktrees.md))
   o teto é outro: **três worktrees de implementação**, contando as com
   PR aberto ainda não mergeado (§"Branches em execução").

---

## Setup inicial (1x por projeto)

Procedimento completo — branches base, branch protection, environments,
workflows de CI/CD e templates de issue/PR — no runbook
[`runbooks/github-repo-setup.md`](./runbooks/github-repo-setup.md).
Aqui permanecem apenas o alias operacional e os **Gates de PR** (fonte
única, referenciada por PIPELINE e CLAUDE.md).

### Aliases recomendados

`git sync` atualiza `main` localmente em um passo (fetch com prune, checkout, fast-forward). Útil logo após merge de release. Hotfix não precisa dele: o `scripts/worktree-new.py` já sai de `origin/main`. Depois de usar, volte o checkout principal para `develop` — ele fica sempre em `develop` (§"Branches em execução").

```bash
git config --local alias.sync '!git fetch --prune origin && git checkout main && git pull --ff-only origin main'
```

- **`--local`** (default no bootstrap): só vale neste repo. Se quiser o alias em todos os seus repos, troque por `--global`.
- **`--ff-only`** garante que o pull falha se houver merge necessário — segurança contra reescrever histórico de `main` por engano.
- **`fetch --prune`** remove refs locais de branches já deletadas no remoto, evitando lixo em `git branch -r`.

> Projetos criados por `scripts/init-project.py` já vêm com esse alias configurado em escopo local.

Uso:

```bash
git sync               # atualiza main local, sai checkado em main
```

### Gates de PR (fonte única)

Todo PR (incluindo PRs de Stage) precisa passar nos gates abaixo antes do
merge. Esta é a **fonte única** dos gates — [`./PIPELINE.md`](./PIPELINE.md) §9.5 e CLAUDE.md
referenciam esta seção em vez de duplicar a lista:

- **CI verde:** workflow `ci.yml` (lint + typecheck + layout-check +
  tests) deve passar.
- **Coverage ≥ 90%:** materializado em `pyproject.toml`
  `[tool.coverage.report] fail_under = 90`; o pytest falha sozinho se a
  cobertura cair abaixo.
- **+1 aprovação:** code review obrigatório (`Require approvals: 1`).
  **Exceção — corrida autônoma:** numa corrida overnight autorizada pelo
  [ADR 0.0.0004](./adr/0_0_0004-autonomous-overnight-mode.md) (`status:
  accepted` **e** a Stage dentro do recorte em "Authorized runs"), a
  aprovação humana é substituída por **auditoria de contexto limpo**
  (`stage-audit` por sessão fresca, que grava o label `complete` —
  CONVENTIONS §3.6).
  **Exceção — orquestração de Step:** na sessão mestra do
  [`PROMPT-step-single-session.md`](./PROMPT-step-single-session.md)
  ([ADR 0.0.0007](./adr/0_0_0007-step-orchestrator-self-merges.md)), a
  aprovação humana também é substituída pela auditoria de contexto limpo:
  a mestra mergeia sozinha quando valem as condições de §3.4 daquele
  prompt (label `complete` gravado pelo auditor, sem blocker, CI verde,
  branch atualizada, nenhum fork P/HALT pendente).
  **Exceção — orquestração autônoma:** com o
  [`PROMPT-orchestrator-autonomous.md`](./PROMPT-orchestrator-autonomous.md)
  ([ADR 0.0.0008](./adr/0_0_0008-autonomous-orchestrator-parallel-worktrees.md)),
  quem mergeia é o **auditor de contexto limpo** que auditou o PR, e só
  quando valem as condições de merge da §3 daquele prompt (label
  `complete`, sem blocker, Actions verde no head inclusive `audit-gate`,
  branch rebaseada sem carona, nenhum fork P pendente).
  Fora dessas três exceções, a aprovação continua obrigatória. Elas são
  **registradas no dono**, como manda CONVENTIONS §0 — sem isso os ADRs
  seriam letra morta.
- **Branch atualizada:** PR precisa estar à frente da base (`Require
  branches to be up to date`).
- **Conversas resolvidas:** todos os comentários do code review devem
  ter status "Resolved".
- **Merge commit obrigatório:** **NUNCA** squash/rebase no merge —
  preserva historicidade auditável (sequência de commits da Stage no
  branch fica visível em `git log --first-parent develop`).

Mudar qualquer um desses números (ex: coverage de 90 → 80, aprovações de
1 → 2) exige edição desta seção como ponto único — os ponteiros não
precisam mudar.

> **Estes gates são hoje OBSERVACIONAIS, não mecânicos.** Branch
> protection não está disponível (repo **privado** em GitHub **Free**):
> `gh api repos/:owner/:repo/branches/develop/protection` → **403
> "Upgrade to GitHub Pro or make this repository public"**. Consequência
> concreta: um PR com check **vermelho** fica `mergeStateStatus:
> UNSTABLE`, **não** `BLOCKED` — e `gh pr merge` passa assim mesmo. Isso
> vale inclusive para o `audit-gate` (o próprio
> [`audit-gate.yml`](../.github/workflows/audit-gate.yml) admite: "ou
> aceite como gate observacional"). **O que segura o merge é disciplina,
> não o GitHub.** Ao migrar para repo público ou GitHub Pro, ativar os
> gates como Required Status Checks e atualizar esta nota.

Para confirmar, classe a classe, que cada check rodado por `make check`
realmente falha com exit ≠ 0 (e portanto o CI rejeita o estado quebrado
antes do merge), ver o runbook
[`runbooks/validate-ci-gate.md`](./runbooks/validate-ci-gate.md).

---

## Nomes e convenções

### Branches

```
main                                # produção
develop                             # desenvolvimento (default)
├── feat/<num-issue>-<desc>        # feature nova
├── fix/<num-issue>-<desc>         # bug fix
├── refactor/<num-issue>-<desc>    # refatoração
├── docs/<num-issue>-<desc>        # doc de um issue
└── docs/<desc>                    # só documentação geral
```

**Exemplos válidos:**
- `feat/42-add-google-login`
- `fix/57-fix-payments-api-timeout`
- `refactor/89-extract-shipping-service`
- `docs/update-readme-q2`

**Regra:** min. 3 chars após tipo, máx. 50 chars total. Kebab-case, sem acentos.

**Stages do pipeline:** branches de Stage seguem o formato especializado `<tipo>/<num-issue>-<N-M>-<slug>` (ex.: `feat/42-1-1-bootstrap`, `feat/89-2-3-s3-source-adapter`). `N.M` é o id da Stage. Ver [`./CONVENTIONS.md`](./CONVENTIONS.md) §4.

**Revisões pós-Stage:** correções/melhorias criadas **depois que o PR da Stage já foi mergeado** voltam ao formato **genérico** acima — **sem `<N-M>`**. Tipo segue a natureza da mudança (`fix`, `chore`, `docs`, `refactor`), e a branch sai de uma **nova issue**.

- ✅ `fix/103-fix-s3-credentials-error` (correção pós-Stage 2.3, nova issue #103)
- ✅ `docs/107-document-post-stage-branch-pattern` (doc pós-Stage, nova issue #107)
- ❌ `fix/103-2-3-fix-s3-credentials-error` (`<N-M>` não pertence — a Stage 2.3 já fechou)

O `<N-M>` no nome identifica a **execução da Stage**; depois que ela fechou, o trabalho passa a ser bug/chore/doc normal e a rastreabilidade fica no `Refs #<num-issue>` do commit. Ver §"Defeito descoberto após merge para main" e [`./CONVENTIONS.md`](./CONVENTIONS.md) §4.

### Commits

**Formato:**
```
<tipo>(<escopo>): <descrição imperativa em português>

- <detalhe 1>
- <detalhe 2>

Refs #<num-issue>
```

**Tipos:**
| Tipo | Quando |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `refactor` | Refatoração (sem mudança de comportamento) |
| `test` | Adicionar/ajustar testes |
| `docs` | Documentação |
| `style` | Formatação (sem mudança lógica) |
| `perf` | Melhoria de performance |
| `chore` | Manutenção geral |
| `ci` | Mudanças em CI/CD |
| `build` | Mudanças em build/deps |

**Exemplos prontos:**

```
feat(auth): adicionar login com Google

- Integrar OAuth 2.0 com authlib
- Criar endpoint POST /auth/google/callback
- Adicionar campo google_id ao User
- Persistir tokens em user_sessions

Refs #42
```

```
fix(payment): corrigir timeout na API de pagamentos

- Aumentar timeout de 5s para 30s
- Adicionar retry com backoff exponencial (3 tentativas)
- Logar tentativas falhadas com nível WARNING

Refs #57
```

**Regra:** 1 commit = 1 mudança lógica. Se fez 5 coisas, 5 commits.

### Pull Requests

**Título:** Conventional Commits em português (ver §Princípios
fundamentais #3), com **escopo obrigatório** e o identificador da
Stage/issue na descrição, após um travessão `—`. Dois formatos:

- **PR de Stage:** `<tipo>(<escopo>): stage N.M — <descrição>`
  - ex.: `feat(billing): stage 12.10 — relatório de inadimplência`
- **PR de branch (pós-Stage / issue avulsa):** `<tipo>(<escopo>): issue #<num> — <descrição>`
  - ex.: `fix(tooling): issue #53 — corrigir gate do pre-commit`

Em ambos o `<escopo>` é o BC/módulo da mudança (ASCII/kebab), **nunca**
a Stage — mesma regra de escopo mínimo dos commits (CONVENTIONS §4(a)).
O número da Stage/issue vai na descrição, depois do `—`, não no escopo.
Não há gate de CI sobre o título de PR; a conformidade é garantida no
code review. Detalhes e exemplos: CONVENTIONS §4(c).

**Corpo:** o template é **fonte única** em [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) — carregado automaticamente pelo GitHub ao abrir o PR (e por `gh pr create` sem `--body`). **Não duplicar aqui** (a duplicata é o que faz os dois divergirem ao longo do tempo). Seções: `Closes #`, `## Resumo`, `## Tipo`, `## Checklist (Stage)` — inclui **roadmap sincronizado no próprio PR** (Stage `todo→done` ou issue avulsa `open→closed`) e `make check`/coverage — e `## Como testar`.

---

## Fluxo de trabalho (etapas)

### Etapa 1: Criar issue

**Antes de criar, buscar duplicata:** rodar `gh issue list --search "<termos do escopo>"` (use `--state all` se suspeitar que já foi resolvido) e conferir se não existe issue com o **mesmo escopo** — ou cujo escopo **comporta** este trabalho. Se houver, reaproveitar em vez de abrir card concorrente; só criar nova quando nenhuma encaixa. (Issue duplicada fragmenta a rastreabilidade do `Refs #`/`Closes #`.)

**Decidir a forma — issue avulsa ou Stage?** Aplique o litmus de [`PIPELINE.md`](./PIPELINE.md) §4.5 ("o corpo já é o concept, ou pede um concept?"): **issue avulsa** quando o concept+technical cabem no corpo (fix/docs/chore, escopo objetivo, poucas tasks); **Stage** (concept+technical próprios, mesmo enxutos) quando o trabalho **carrega um conceito** — precisa definir modelo/invariante/contrato, tem decisão que merece ADR, ou o corpo não segura o escopo. Na dúvida, comece avulsa e **promova** se ao escrever o corpo você se pegar redigindo um mini-concept.

**Registrar melhoria futura como issue.** Toda melhoria/gap identificado que **não entra no escopo atual** deve virar **issue** — não ficar só num docstring, comentário de código ou `[finding]` em `technical.md`/`concept.md` (registro solto tem risco de esquecimento permanente; a issue é o que garante que o ponto volta à pauta). Se a melhoria ainda é **abstrata/incerta** (não se sabe se será mesmo necessária):

- marque a incerteza **explicitamente no corpo** — uma seção `## Incerteza` descrevendo o que ainda não se sabe — e, opcionalmente, a label `status: speculative`;
- declare o **momento previsto** de reavaliação: uma **condição de disparo** (ex.: "quando surgir o 3º consumidor deste helper", "quando o domínio modelar `<condição futura>`"). Momento previsto ≠ compromisso de data;
- **não** descreva a solução proposta como definitiva. Registre-a como **ponto de partida** e deixe explícito que **deve ser reavaliada no momento da implementação** — premissas e contexto podem ter mudado.

Descrever claramente:
- **Contexto:** por que estamos fazendo isso?
- **Critérios de aceite:** comportamento esperado (checklist)
- **Tarefas técnicas:** passos de implementação (se conhecidos)

Exemplo:
```markdown
## Contexto
Usuários de Google querem autenticação automática via Google Account.

## Critérios de aceite
- [ ] Usuário pode clicar em "Login com Google" na página de login
- [ ] Após autenticação, é redirecionado para dashboard
- [ ] Seus dados de Google (nome, email) são salvos automaticamente
- [ ] Coverage ≥ 90% nos testes de auth

## Tarefas técnicas
- [ ] Setup OAuth app no Google Cloud
- [ ] Integrar biblioteca authlib
- [ ] Criar model GoogleUser
- [ ] Implementar callback endpoint
```

Criar com (título e corpo em português):
```bash
gh issue create --title "feat: adicionar login com Google" --body "..."
```

### Etapa 2: Criar branch

Criar a branch **numa worktree própria**, a partir do título da issue (slug **em inglês**, ver
§Princípios fundamentais #3). O script sai de `origin/develop` atualizado (`origin/main` para
`hotfix/...`); o checkout principal não muda de branch (§"Branches em execução"):
```bash
python scripts/worktree-new.py feat/42-add-google-login --no-vscode   # agente
make worktree BRANCH=feat/42-add-google-login                         # humano (abre o VS Code)
```

**Gate:** dentro da worktree, `git branch --show-current` mostra o nome correto.

### Etapa 3: Implementar (loop)

1. **Sempre verificar branch antes de codificar:**
   ```bash
   git branch --show-current
   ```
   Se for `develop`/`main`, voltar para Etapa 2.

2. **Implementar incrementalmente, em escopo mínimo:**
   - Escrever código
   - Rodar testes: `pytest` ou `pnpm test`
   - Rodar lint: `ruff check` / `biome check`
   - Commitar com **escopo mínimo**: 1 commit = 1 mudança lógica
     numa única feature/módulo/BC. Se tocou em 3 escopos diferentes,
     são 3 commits. Subject e body em **português** (ver §Princípios
     fundamentais #3); body em bullet points (≥ 1 bullet). Padrão
     detalhado em [`./CONVENTIONS.md`](./CONVENTIONS.md) §4(a).
   - O hook `commit-msg` (instalado pelo `make setup` do checkout
     principal, §"Hooks do git") valida o
     subject contra o padrão antes de aceitar o commit. Se rejeitar,
     ler a mensagem e ajustar — não tem como "passar por cima".

3. **Verificar coverage:**
   ```bash
   pytest --cov
   ```
   Mínimo: **90%** no código novo/alterado.

**Gates antes de sair desta etapa:**
- [ ] Critérios de aceite da issue atendidos
- [ ] Testes passando
- [ ] Coverage ≥ 90%
- [ ] Lint sem erros
- [ ] Working tree limpo (`git status` limpo)

Se qualquer falhar: **PARAR** e corrigir antes de prosseguir.

### Etapa 4: Push e abrir PR

**Sincronize sempre antes do push.** `git fetch` + `git rebase origin/<base>`
— não só quando houver carona de outro escopo. Rebasear na base **atualizada**
mantém as implementações sequenciais e resolve **cedo** o conflito recorrente
de `roadmap.md` (várias Stages/issues editam a mesma tabela), em vez de ele
estourar no merge.

**Antes do push, conferir base remota.** O branch precisa carregar
apenas commits do escopo dele — nada de "carona" de outro escopo (fix
solto, ajuste de bootstrap, commit de outra Stage). Listar commits que
o branch adiciona sobre a base:

```bash
git fetch --prune origin
git log --oneline origin/<base>..HEAD       # <base> = develop (feat/fix/refactor) ou main (hotfix)
git log --oneline origin/main..HEAD         # sanity check broader: tudo no branch que main ainda não tem
```

Para a Stage `feat/42-add-google-login`, `<base>` é `develop`. Para um
`hotfix/99-...`, é `main`.

- **Saída esperada:** só os commits do branch (Conventional + tags
  `[N.M/...]` se for Stage; reserved gate commits se aplicável).
- **Se aparecer commit fora do escopo** (ex.: `fix: sync boilerplate
  fixes` sem `Refs #` e sem tag): rebasear em `origin/<base>` para
  mover esses commits para fora do branch, ou movê-los para um PR
  próprio. Não empurre carona junto da Stage.

```bash
git rebase origin/<base>                    # sync sempre; obrigatório se houver carona
```

Quando o `git log origin/<base>..HEAD` mostrar só commits do escopo:

```bash
git push -u origin feat/42-add-google-login
```

Abrir PR contra `develop` (não main; título em português, com escopo +
identificador da issue na descrição — ver §Pull Requests / CONVENTIONS §4(c)):
```bash
gh pr create --base develop --title "feat(auth): issue #42 — adicionar login com Google" --body "..."
```

**Gates:**
- [ ] `git log origin/<base>..HEAD` mostra **apenas** commits do escopo do branch
- [ ] PR aberto e link disponível

### Etapa 5: Review + CI

Verificar status:
```bash
gh pr checks      # CI
gh pr view        # comentários e aprovações
```

**Se CI falhou:** voltar para Etapa 3, corrigir e fazer novo commit.

**Se faltam aprovações:** aguardar review de outro dev. Não mergear sem aprovação.

**Se há comentários:** responder e fazer commits adicionais se necessário.

**Gates:**
- [ ] CI verde (todos os checks passando)
- [ ] ≥ 1 aprovação de outro dev
- [ ] Sem comentários não-resolvidos

### Etapa 6: Merge

Toda branch vive numa worktree (§"Branches em execução"), então o merge
segue §"Merge e limpeza da worktree", passos 1–4: rebase e CI verde,
base reconferida **depois** do CI (`develop` anda durante a espera) e
`gh pr merge <num> --merge` do checkout principal — merge commit, NUNCA
squash/rebase, e **sem** `--delete-branch`, que não apaga a remota com a
branch presa a uma worktree.

**Gate:** PR mergeado em develop.

### Etapa 7: Cleanup

§"Merge e limpeza da worktree", passos 4–7: `git pull` no principal,
o banco da worktree, `worktree-rm.py <branch> --delete-remote` (que
derruba esse banco) e a verificação (remota, local, worktree, containers
e hooks).

Verificar também:
- [ ] Issue fechada automaticamente
- [ ] Deploy em dev disparado (verificar em GitHub Actions)
- [ ] Card no project board movido para "Done"

---

## Release (deploy em produção)

Quando a equipe decide promover `develop` para `main`:

1. Criar PR de release (título e corpo em português):
   ```bash
   gh pr create --base main --head develop --title "release: 2026-05-12" --body "Inclui PRs #42, #57, #89"
   ```

2. Listar PRs incluídos:
   ```bash
   gh pr list --base develop --state merged --limit 30
   ```

3. Obter aprovação + CI verde (mesmo gate de qualidade).

4. Merge commit em main:
   ```bash
   gh pr merge <num> --merge
   ```

5. Workflow de `deploy-prod` dispara automaticamente.

6. Aprovadores clicam em "Review deployments" no GitHub Actions e aprovam.

7. Deploy executa (automático após aprovação).

**Pré-requisitos de release:**
- [ ] Todas as PRs em develop estão verdes há ≥ 2 horas
- [ ] Migrations foram testadas em dev
- [ ] Backup automático do banco de produção confirmado
- [ ] Rollback plan documentado (se houver migrations)

---

## Branches em execução

**Regra (Princípios fundamentais #7):** até **duas** branches em
execução (ainda sem PR aberto), **cada uma na sua worktree**, e o
checkout principal sempre livre em `develop`. Branch com PR aberto
aguardando review não conta no teto de duas, mas continua contando no
critério de conflito abaixo. O limite existe porque paralelismo sem
isolamento costuma:

- misturar commits dos escopos via working tree não-limpo
  (`git stash` muitas vezes vira `git stash drop` errado);
- gerar PRs simultâneos disputando o mesmo gate humano de review;
- esconder progresso real — branch antiga vai ficando esquecida
  enquanto a "urgente" cresce e nunca volta.

A worktree resolve o primeiro; o teto de duas e o critério de conflito
resolvem os outros dois.

**Orquestração autônoma** ([ADR 0.0.0008](./adr/0_0_0008-autonomous-orchestrator-parallel-worktrees.md),
[`PROMPT-orchestrator-autonomous.md`](./PROMPT-orchestrator-autonomous.md)):
o teto passa a ser de **três worktrees de implementação existindo ao
mesmo tempo**, contando as com PR aberto ainda não mergeado (cada uma
segura uma sessão viva — o teto é de custo). Uma nova só abre quando
outra é removida pelo auditor, e só se não conflitar com as em voo
(critérios abaixo). A branch de docs de processo do próprio orquestrador
não conta.

**Duas branches só voam juntas se não conflitam** — todas as condições:

- nenhuma depende da outra (roadmap "Depende de", issue, ou uma consome
  contrato que a outra cria);
- os arquivos a criar/modificar (corpo da issue / `technical.md`) são
  disjuntos;
- nenhuma das duas mexe em ponto compartilhado: port/contrato público,
  schema persistido ou migration Alembic, `.importlinter`,
  `pyproject.toml`/`uv.lock`, `composition_root.py`.

A exceção é a tabela de issues/Stages do `docs/roadmap.md`, que quase
toda branch toca: o conflito de linha se resolve no rebase antes do push
(§Etapa 4), não impede o paralelismo.

Conferência mecânica antes de abrir o PR da segunda (interseção vazia,
fora `docs/roadmap.md`, = ok):

```bash
comm -12 <(git diff --name-only origin/develop...A | sort) \
         <(git diff --name-only origin/develop...B | sort)
```

### Criar a worktree (sempre pelo script)

```bash
python scripts/worktree-new.py feat/42-2-3-s3-adapter --no-vscode   # agente
make worktree BRANCH=feat/42-add-google-login                        # humano (abre o VS Code)
```

`git checkout -b`/`git switch -c` no checkout principal e
`git worktree add` manual são recusados pelo hook `git_guard`: o script
é o único caminho, porque é ele que valida o nome e a issue e isola
portas. Dentro de uma worktree, os comandos de branch passam normalmente.

O script, num único comando:

- valida o nome da branch contra CONVENTIONS.md §4;
- confere que a issue existe no GitHub (`gh issue view`);
- cria a worktree em `../<repo>-worktrees/<branch>/` saindo de
  `origin/<base>` (auto: `develop`, ou `main` para `hotfix/...`);
- copia `.env`/`.env.local` do checkout principal;
- **gera portas livres no `.env` da worktree** (`APP_PORT`,
  `POSTGRES_PORT`, `REDIS_PORT`) para o devcontainer/docker compose da
  paralela não brigar com o da principal por bind no host, e **leva a
  `DATABASE_URL` para a mesma `POSTGRES_PORT`** (acrescentada se faltar; só
  com host `localhost`/`127.0.0.1`/`::1` — o host `postgres` fala na porta do
  contêiner e fica como está). Livre quer dizer: fora do `.env` das worktrees
  registradas, sem container que a publique (de pé ou parado) e sem nada
  ocupando-a no host (bind de teste) — issue #84, §"Banco e containers da
  worktree";
- roda `uv sync --extra dev` (o venv da worktree) e **não** toca nos hooks
  do git (§"Hooks do git", logo abaixo);
- abre uma nova janela do VS Code na worktree.

Flags úteis (passar via `ARGS='...'`):

- `--create-issue --issue-title "feat: ..."` — cria a issue antes
  (substitui o `<num>` por placeholder `-`, ex.: `feat/-add-foo`).
- `--no-setup` (pula o `uv sync`) / `--no-vscode` / `--no-env` /
  `--no-port-assign` — opt-outs.
- `--base main` — força base remota (default já cuida de hotfix).

#### Hooks do git

Fonte única da regra; o prompt do orquestrador, o `CLAUDE.md`, o README e a
skill `git-versioning-pointer` apontam para cá. Os hooks `pre-commit` e `commit-msg` moram no diretório comum do
repositório (`git rev-parse --git-common-dir`), **um só para todas as
worktrees**, e o `pre-commit install` grava neles o caminho absoluto do
python que o rodou (`INSTALL_PYTHON`). Instalados de dentro de uma
worktree, passavam a depender do venv dela; removida a worktree, o
commit de todas as outras quebrava (issue #100).

- **Só o checkout principal instala os hooks**, porque ele nunca é
  removido. Quem instala é o `scripts/install_hooks.py`, chamado pelo
  `make setup`: no principal, roda o `pre-commit install` com o `.venv`
  dele; numa worktree, não toca nos hooks e sai com 1 se o python deles
  não existir mais, dizendo como religar.
- **Um venv serve a todas as worktrees.** Esse python roda só o framework
  do pre-commit. Cada hook do `.pre-commit-config.yaml` chama `uv run`, que
  usa o venv da worktree que commita, então o `make setup` dentro de uma
  worktree é inofensivo, e o `worktree-new.py` faz só o `uv sync`.
- **O `worktree-rm.py` religa** (passo 5 dele): se um hook apontava para
  dentro da worktree que saiu, ou para um python que não existe mais,
  roda o `install_hooks.py` no principal. Esse é o estado de quem rodou
  `pre-commit install` à mão numa worktree, ou de antes da #100.
- **Religar à mão:** no checkout principal,
  `uv run python scripts/install_hooks.py`. Nunca rode `pre-commit install`
  dentro de uma worktree.

#### Por que o devcontainer não conflita entre worktrees

O `docker-compose.yml` do template foi desenhado para ser
**worktree-safe**:

- **Sem `container_name:` fixos.** O Compose usa o `--project-name`
  (= nome da pasta da worktree) como prefixo automático, gerando
  nomes únicos por worktree: `sandbox-test-app-1` na principal vs.
  `feat-1-foo-app-1` na paralela. Definir `container_name:` quebra
  esse mecanismo, então o template intencionalmente omite.
- **Portas do host parametrizadas.** As linhas de `ports:` usam
  `${APP_PORT:-8000}:8000`, `${POSTGRES_PORT:-5432}:5432`,
  `${REDIS_PORT:-6379}:6379`. O default preserva o comportamento de
  uma única worktree, e o `worktree-new.py` sobrescreve via `.env` na
  paralela. O lado *dentro* do container continua sempre 8000/5432/6379
  — só o lado do host muda.

Se adicionar um serviço novo ao compose com porta exposta no host
(ex.: mailhog), inclua a variável correspondente em `PORT_DEFAULTS`
dentro de `scripts/worktree-new.py` para entrar na rotação de
auto-atribuição. Se a app ler uma URL dele, a chave da URL vai em
`URL_PORT_KEYS` (a porta da URL acompanha) e o default dela, o do
`Settings`, em `URL_DEFAULTS` — sem ele, a worktree cujo `.env` copiado
não traz a chave fica no default, na porta do checkout principal, e a
issue #58 se repete nesse serviço. A guarda
(`scripts/database_url_guard.py`) confere só a `DATABASE_URL`.

#### Banco e containers da worktree

Cada worktree tem o **seu** Postgres, publicado na `POSTGRES_PORT` do
`.env` dela. O script já escreve a `DATABASE_URL` nessa porta (issue #58),
e a guarda `scripts/database_url_guard.py` **recusa** a URL que, com host
loopback, não aponta para a porta que o compose do checkout publica — a
`POSTGRES_PORT` do ambiente ou do `.env` da raiz, ou 5432 sem ela. Três
pontos a aplicam, com a mesma mensagem: a fixture `database_url`
(`tests/conftest.py`), antes de conectar, porque a fixture `engine` recria
o schema e derrubaria o banco de outra frente; o `make migrate`, antes do
Alembic; e o `make run`, antes do uvicorn (issue #85). O `Settings` lê o
`.env` do diretório corrente, então `pytest` e `make` rodam da raiz da
worktree. O `make run` sobe na `APP_PORT` do checkout (8000 sem ela), a
mesma em que o compose publicaria a app. Cabe a quem usa a worktree subir e derrubar esse banco:

- **Ao abrir a worktree:** `docker compose up -d --wait postgres` dentro
  dela, antes do primeiro `pytest`. O `worktree-new.py` não entrega porta
  que esteja no `.env` de outra worktree, que um container publique (de pé
  ou parado — o `start` a toma de volta) ou que o bind de teste ache
  ocupada no host (issue #84). Com o **Docker parado**, ele avisa: a sonda
  vê o que está de pé, mas as portas dos containers parados não foram
  conferidas. Se mesmo assim o `up` falhar com a porta ocupada, liberar a
  porta, ou trocar `POSTGRES_PORT` e `DATABASE_URL` juntas; nunca rodar a
  suíte contra o que responde nela — a guarda confere portas, não de quem
  é o banco.
- **Ao remover a worktree:** o `worktree-rm.py` derruba o projeto compose
  dela — o `docker compose down -v`: containers, volumes (o banco) e redes,
  achados pelo rótulo `com.docker.compose.project` = nome da pasta, então
  vale sem o arquivo do compose e com a pasta já apagada. Com o **Docker
  parado**, ele avisa e segue: o projeto fica órfão até o Docker voltar.
- **Órfãos:** `make worktree-orphans` (do checkout principal) lista os
  projetos compose de worktrees que não existem mais — `working_dir`
  dentro de `../<repo>-worktrees/`, ou só volume/rede com nome de pasta de
  branch — e `make worktree-orphans ARGS=--prune` os derruba. Sai com 1 se
  o Docker estiver parado (nada foi conferido). O projeto do checkout
  principal nunca entra; o `worktree-rm.py` recusa a branch dele.

Quando o PR daquela worktree mergear, a remoção segue a sequência de
§"Merge e limpeza da worktree", logo abaixo.

Detalhes e todas as flags: `python scripts/worktree-new.py --help` e
`python scripts/worktree-rm.py --help`.

### Merge e limpeza da worktree

Sequência canônica para mergear um PR cuja branch vive numa worktree —
humano, mestra de Step ou auditor da orquestração autônoma. Os prompts
apontam para cá; não copiam os passos. Cada passo existe por uma falha
medida (issue #81):

- `gh pr merge --delete-branch` mergeia, mas **não apaga a branch
  remota** quando a branch local está presa a uma worktree — rodado de
  dentro dela (`fatal: 'develop' is already used by worktree`) ou do
  checkout principal. Por isso o merge vai sem a flag e a remota sai
  num passo próprio.
- `git branch -d` só apaga a branch já mergeada no `develop` local (ou
  no upstream dela): antes do `git pull` no principal ela sobra.
- `develop` anda durante a espera do CI: a conferência de "não está
  atrás" feita antes do CI não vale no merge.
- O `audit-gate` dispara em `edited`, mas o GitHub **não roda workflow
  de `pull_request` em PR com conflito de merge** ("Workflows will not
  run on `pull_request` activity if the pull request has a merge
  conflict" — [docs do GitHub, evento `pull_request`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)).
  Editar o corpo de um PR em conflito com `develop` não gera run.

**1. Sincronizar (na worktree).** Rebase em `origin/develop` e push
(§Etapa 4); esperar o Actions do head.

```bash
git fetch --prune origin
git rebase origin/develop
git push --force-with-lease
gh pr checks <num> --watch
```

**2. Gravar a auditoria `complete`** (só a sessão de auditoria —
CONVENTIONS §3.6) **com a branch já sem conflito**, depois do run do
último push. A edição do corpo dispara um run novo do `audit-gate`;
conferir que ele apareceu e ficou verde:

```bash
gh run list --workflow audit-gate.yml --branch <branch> --limit 2   # run novo, posterior à edição
gh pr checks <num>
```

Sem run novo depois da edição, o PR está em conflito (`gh pr view <num>
--json mergeable` → `CONFLICTING`): volte ao passo 1 — o push do rebase
(`synchronize`) relê o corpo já `complete`. Não use `gh run rerun`: ele
reaproveita o payload do evento original, com o corpo antigo. Commit
vazio (`git commit --allow-empty`) só como último recurso, com marca
`--` da Stage/issue.

**3. Reconferir a base logo antes do merge** — depois do CI verde, não
antes:

```bash
git fetch origin
git rev-list --count HEAD..origin/develop   # tem de ser 0; senão volte ao passo 1
```

**4. Mergear do checkout principal**, com merge commit e **sem**
`--delete-branch`:

```bash
gh pr merge <num> --merge                   # nunca --squash/--rebase
git pull origin develop                     # no principal: traz o merge, para o branch -d do passo 6
```

**5. O banco da worktree** (§"Banco e containers da worktree") sai no
passo 6: o `worktree-rm.py` derruba o projeto compose dela (containers,
volumes e redes). O `docker compose down -v` dentro da worktree, antes,
continua válido e só antecipa isso. Se o `worktree-rm.py` avisar que o
Docker está parado, rodar depois, com o Docker de pé:

```bash
make worktree-orphans ARGS=--prune          # no checkout principal
```

**6. Remover worktree, branch local e branch remota (do principal):**

```bash
python scripts/worktree-rm.py <branch> --delete-remote
```

O script acha a worktree pela branch checada nela (pasta com slug
divergente não exige `--path`), confere sync, remove a worktree, faz
`git branch -d`, `git push origin --delete` e `git remote prune origin`.
`--dry-run` mostra o que faria; `--force` pula o check de sync e usa
`branch -D`.

**7. Verificar** — cada linha com saída vazia, menos a dos órfãos e a dos hooks:

```bash
git ls-remote --heads origin <branch>       # remota apagada
git branch --list <branch>                  # local apagada
git worktree list | grep <pasta-da-worktree>
docker ps -a --filter name=<pasta-da-worktree>
make worktree-orphans                       # "Nenhum projeto compose órfão de worktree."
grep INSTALL_PYTHON .git/hooks/pre-commit   # tem de apontar para o .venv do principal
```

O `worktree-rm.py` já religa o hook que apontava para a worktree
removida (§"Hooks do git"). Se o `grep` ainda mostrar outro venv, ou o
script sair com 2, religar no principal com
`uv run python scripts/install_hooks.py`.

### Quando precisar trocar de escopo no meio (com PR parcial)

**Só fazer isso quando o usuário pedir explicitamente.** Não é
proatividade — é exceção justificada (bloqueio externo, prioridade
mudou, descobriu trabalho urgente que precede o atual).

Procedimento:

1. **Estabilizar a branch atual.** Working tree limpo, todos os
   commits prontos seguindo o padrão de §Commits (1 commit = 1
   mudança lógica, escopo mínimo, body em bullets).
2. **Conferir base remota** — `git log origin/<base>..HEAD` mostra
   só commits do escopo da branch (ver Etapa 4). Rebasear em
   `origin/<base>` se houver carona.
3. **Abrir PR parcial** com título prefixado (português):
   ```bash
   gh pr create --base develop --draft --title "feat(auth): issue #42 — adicionar login com Google (parcial — checkpoint)" --body "..."
   ```
   - Usar `--draft` para sinalizar que não está pronto para review.
   - No corpo, listar **o que já está pronto** e **o que falta**
     (checklist com `[x]` / `[ ]`). Se for Stage, citar quais Tasks
     do `technical.md` já estão fechadas.
   - Não pedir review ainda. PR draft existe para travar a posição
     do trabalho, não para consumir tempo de revisor.
4. **Criar a branch nova na sua própria worktree** (a parcial fica
   parada na dela, intacta):
   ```bash
   python scripts/worktree-new.py feat/<num-issue>-<N-M>-<slug> --no-vscode   # a nova
   ```
5. **Implementar a nova branch ao fim** — PR contra `develop`,
   review, merge normal.
6. **Voltar para a branch parcial** (na worktree dela). Sair do
   `draft`, completar trabalho restante, novos commits seguindo escopo
   mínimo:
   ```bash
   cd ../<repo>-worktrees/<branch-parcial>
   git merge origin/develop         # absorver o que entrou
   # ... continuar implementação ...
   gh pr ready                      # tira do draft, pede review
   ```
7. **Merge da branch parcial normal** — mesmo gate de PR de §Gates
   de PR.

**Importante:**

- **PR parcial não passa para review enquanto draft.** Manter draft
  até a branch estar completa (todos os critérios de aceite da
  issue atendidos).
- **PR parcial não dispensa gates.** Quando sair do draft, mesmos
  gates: CI verde, coverage ≥ 90%, 1 aprovação, sem comentários
  abertos.
- **Não usar isso como rotina.** Se acontecer mais de 1 vez por
  mês, o problema está no recorte das Stages/issues — escopo maior
  do que o necessário. Discutir em retro.

---

## Hotfix (bug urgente em produção)

Branch sai de `main`, não de `develop`:

```bash
python scripts/worktree-new.py hotfix/99-fix-critical-checkout-error --no-vscode   # base = origin/main
```

Implementar com **mesmo rigor** (testes, coverage, lint).

Abrir PR contra `main` (título em português; branch em inglês):
```bash
gh pr create --base main --title "fix(checkout): issue #99 — erro crítico no checkout" --body "..."
```

Review acelerado mas **NUNCA pulado**.

Após merge em main, fazer back-merge em develop:
```bash
git checkout develop && git pull
git merge main
git push
```

Isso garante que o fix não se perde em próximas releases.

---

## Defeito descoberto após merge para main

Cenário: PR passou no review, foi mergeado, está em produção, e
descobre-se um bug. **Não reescrever histórico.**

- **Urgente** (afeta produção ou bloqueia usuários): seguir o fluxo de
  Hotfix acima.
- **Não-urgente** (pode aguardar próxima release): abrir nova issue
  (`fix: ...`) e tratar como bug normal — branch a partir de `develop`
  no formato **genérico** `fix/<num-issue>-<slug>` (sem `<N-M>`, mesmo
  se a Stage de origem era `N.M`; ver §Branches → "Revisões pós-Stage"),
  PR contra `develop`, release subsequente carrega o fix para `main`.

Em ambos os casos: documentar na issue **o que escapou** e **como
deveria ter sido detectado no review**. Lições alimentam o checklist de
PR review.

---

## Como revisar código (code review)

Quando revisor:

1. **Ler issue e PR**: entender contexto e critérios de aceite.

2. **Conferir mudanças:**
   - [ ] Código resolve o problema descrito?
   - [ ] Mudanças batem com título/descrição do PR?
   - [ ] Testes cobrem cenários positivos **e negativos**?
   - [ ] Coverage é ≥ 90%?

3. **Apontar problemas:**
   - **Bloqueante:** quebra funcionalidade, introduz bug, security issue
   - **Não-bloqueante (nit):** estilo, clareza, performance, debt técnico

4. **Sugerir:**
   ```bash
   gh pr review <num> --approve           # aprovar
   gh pr review <num> --request-changes   # pedir mudanças
   gh pr comment <num> --body "comentário"  # comentar
   ```

Exemplo de feedback construtivo:
> "A lógica está correta, mas o nome `tmp_user` é vago. Sugerir `validated_user` ou `user_after_oauth`. Nit."

---

## Comportamento bloqueante (regra absoluta)

**PARE** se detectar qualquer um desses cenários:

- Tentativa de push direto em `main` ou `develop`
- Tentativa de merge **sem** CI verde
- Tentativa de merge **sem** ≥ 1 aprovação — **exceto** em corrida autônoma
  autorizada pelo ADR 0.0.0004, na orquestração de Step (ADR 0.0.0007) ou
  na orquestração autônoma (ADR 0.0.0008),
  onde a aprovação é substituída por auditoria de contexto limpo (ver
  §Gates de PR, o ponto único)
- Coverage < 90% em código novo
- Branch errada para a operação (ex: `feat/x` em vez de branch de feature)
- Squash ou rebase no merge (deve ser merge commit)
- Working tree com mudanças não commitadas em momento crítico
- Push de branch com carona de outro escopo: `git log origin/<base>..HEAD` mostra commits que não pertencem ao escopo declarado do branch (ver Etapa 4)
- Mensagem de commit fora do padrão Conventional Commits **em português** (descrição em PT, escopo em snake/kebab ASCII) ou sem `Refs #<num-issue>` no rodapé quando há issue associada
- Nome de branch **fora de inglês ASCII kebab-case** (ex.: `feat/42-adicionar-login` ou `feat/42-Add-Login` — deve ser `feat/42-add-google-login`; ver §Princípios fundamentais #3 e [`./CONVENTIONS.md`](./CONVENTIONS.md) §1)
- Branch criada ou trocada **no checkout principal**, terceira branch em execução, ou duas branches em execução que **conflitam** (critérios em §"Branches em execução"). Exceções: usuário pediu **explicitamente** o fluxo de PR parcial (§"Branches em execução" → §Quando precisar trocar de escopo no meio); na orquestração autônoma (ADR 0.0.0008) o teto é de **três** worktrees de implementação, contando as com PR aberto — bloqueia a **quarta**
- Body de commit de Task sem bullets, ou commit agrupando vários escopos diferentes (deve quebrar em commits separados por escopo mínimo)
- Iniciar uma Stage (criar branch da Stage, pasta `docs/stages/N.M-<slug>/`, ou rodar prompt da Fase 3A) **sem que a issue correspondente já exista** no backlog do GitHub. Verificação: `gh issue view <num>` deve retornar a issue. Issue-first é Princípio fundamental #1; sem issue verificável, parar e criar a issue primeiro (ver [`./RUNBOOK-STAGE-LIFECYCLE.md`](./RUNBOOK-STAGE-LIFECYCLE.md) Passo 1 + `scripts/check_stage_issue.py` em `make docs-check`)

**Ação:** Explicar o problema, sugerir correção, e exigir confirmação explícita se insistir:

> "⚠️ Coverage é 73%, mínimo é 90%. Para prosseguir mesmo assim, confirme: **confirmo prosseguir**"

---

## Quick reference

```bash
# Issues (título e corpo em português)
gh issue create --title "feat: ..." --body "..."
gh issue list --assignee @me
gh issue view <num>

# Branches (slug em inglês) e commits (subject + body em português; Refs no rodapé)
python scripts/worktree-new.py feat/42-short-slug-in-english --no-vscode   # nunca checkout -b no principal
git add .
git commit -m "feat(escopo): descrição curta em português

- bullet 1
- bullet 2

Refs #42"

# Antes do push (conferir base remota — Etapa 4)
git fetch --prune origin
git log --oneline origin/develop..HEAD     # ou origin/main..HEAD em hotfix
git rebase origin/develop                  # se houver carona de outro escopo

# PRs
gh pr create --base develop --title "..." --body "..."
gh pr checks                    # status do CI
gh pr view                      # detalhes
gh pr review --approve          # aprovar
gh pr merge <num> --merge        # merge commit, do principal; sem --delete-branch (§Merge e limpeza da worktree)

# Deploy
git sync                                 # atualiza main local
gh pr create --base main --head develop  # criar release PR

# Cleanup (após o merge — sequência completa em §Merge e limpeza da worktree)
git pull origin develop                                  # no principal, ANTES do worktree-rm
python scripts/worktree-rm.py <branch> --delete-remote   # compose + worktree + branches + prune
make worktree-orphans                                    # compose de worktree que já saiu
```

---

## Materiais complementares

- [GitHub Docs: About branches](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-branches)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Docs: Branch protection rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/managing-a-branch-protection-rule)
---
title: Concept — Bootstrap do projeto
description: Validar e completar o scaffolding do template no Windows nativo — gates locais verdes e reprodutíveis (make setup/check/test), lock versionado, import-linter, cobertura ativa e docs corrigidos
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, bootstrap, makefile, windows, uv, import-linter, coverage, pre-commit]
status: done
created_at: 2026-07-14
updated_at: 2026-07-14
stage_id: 1.1-bootstrap
stage_title: Bootstrap do projeto
step_id: 1
step_title: Fundação do repositório
depends_on: []
---

# Concept — Stage 1.1 — Bootstrap do projeto

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task) e critérios de atomicidade, ver
> [`PIPELINE.md`](../../PIPELINE.md) §4.

## 1. Escopo

### Dentro do escopo

- **Makefile Windows-nativo:** receitas sem dependência de shell POSIX
  (lógica condicional movida para comandos diretos ou scripts Python);
  `make setup` passa a usar `uv sync --extra dev` (gera/atualiza `uv.lock`
  e instala o pacote editável — elimina a divergência local × CI); alvo de
  teste do gate (`make check`) roda `pytest --cov` para o `fail_under = 90`
  do `pyproject.toml` disparar de fato.
- **`make` alcançável:** `C:\msys64\usr\bin` entra no **PATH global do
  usuário** (decisão do sponsor, 2026-07-14), com a ressalva documentada de
  ordem (o `git.exe` do MSYS2 não pode ganhar do Git for Windows).
- **`uv.lock` gerado e versionado** (política já prevista em CONVENTIONS §5).
- **Casa fixa do `UV_SYSTEM_CERTS=1`:** dupla — (a) `.claude/settings.json`
  **versionado** (cobre sessões Claude Code) e (b) **variável de ambiente do
  usuário Windows** (cobre `make`/`uv` em PowerShell comum; aplicada no mesmo
  ato de setup de máquina que o PATH). `.claude/settings.local.json` sai do
  rastreamento do git (`git rm --cached`) e entra no `.gitignore` (é override
  de máquina).
- **import-linter:** dependência dev + contratos espelhando
  [`LAYOUT.md`](../../LAYOUT.md) §3, rodando em `make check`, no pre-commit
  e no CI (o CI executa `make check`, logo herda o gate). **Coexiste** com
  `scripts/check_layout.py` (defesa em profundidade — ver §6).
- **Gate de cobertura ≥ 90% efetivamente executado** em `make check`
  (local e CI). Medição atual do scaffold: **~33%** — a ativação do gate
  exige uma **suite de testes dedicada ao kernel `shared/`** (pagination,
  clock, uuid_generator, settings, database/connection, logging,
  http/app + error_handlers + middlewares) e ao bootstrap
  (`composition_root`, `main`), antes de ligar o `--cov` no `check`.
- **Sincronização do `uv.lock` verificada mecanicamente:** `make check`
  ganha passo `uv lock --check` (falha se o lock diverge do
  `pyproject.toml`) — local e CI herdam o mesmo gate.
- **`tree.txt` gerado** por `scripts/regen_tree.py` (permanece
  **gitignorado** — decisão do template mantida; regeneração local
  documentada no setup).
- **Hooks `pre-commit` e `commit-msg` instalados e validados no Windows.**
- **Docs corrigidos:** `README.md` e
  [`docs/runbooks/validate-ci-gate.md`](../../runbooks/validate-ci-gate.md)
  deixam de prescrever devcontainer/WSL como único caminho no Windows
  (o host nativo vira caminho suportado de primeira classe; devcontainer
  continua como opção).
- **Bloco da Stage 1.1 no [`roadmap.md`](../../roadmap.md) corrigido:**
  remove `features/orders/` (a feature-exemplo já não existe — letra
  morta), complexidade `S → M`, arquivos a criar/modificar refletindo o
  escopo real.
- **Dois ADRs em `accepted`:** ambiente de desenvolvimento Windows-nativo
  (revoga a premissa POSIX-only do template) e gates de PR observacionais
  (GitHub Free em repo privado não tem branch protection).

### Fora do escopo (explicitamente)

- Features de negócio (Step 2 em diante).
- CI no GitHub Actions além do que `make check` já cobre — a validação
  ponta-a-ponta do pipeline é a Stage `1.2-ci`.
- CD / deploy (Step 6).
- Branch protection paga (upgrade de plano GitHub) — o ADR registra o
  estado observacional.
- `.gitattributes` / normalização de fim de linha — risco conhecido
  (churn CRLF), mas fora do critério de aceite da issue; se necessário,
  vira `[finding]` para Stage/issue futura.

### Vínculo com o roadmap

Primeira Stage do Step 1 (Fundação do repositório): "repo com scaffolding
hexagonal, gates locais e CI verdes". Esta Stage entrega os **gates
locais**; a `1.2-ci` valida o pipeline no GitHub Actions. Fonte:
[`roadmap.md`](../../roadmap.md) §Stage 1.1 e issue
[#1](https://github.com/MarceloSanC/restaurant-hub/issues/1).

## 2. Objetivo da Stage

Ao fechar esta Stage, `make setup && make check && make test` fecham
verdes no Windows nativo de forma **reprodutível e automatizada** — sem
receita manual de PATH/env — com lockfile versionado, enforcement
estrutural completo (ruff + mypy + check_layout + import-linter +
docs-check) e gate de cobertura ≥ 90% disparando de verdade.

## 3. Contexto e premissas

### Contexto

O scaffolding veio do `whaka-dev-project-template`, que assumia ambiente
POSIX (runbook validate-ci-gate: "make is POSIX-only by project
decision"). Este projeto roda **100% em Windows nativo** (decisão do
sponsor). A análise de prontidão (issue #1 + comentário de 2026-07-12)
provou que `make check` fecha verde com uma receita manual: MSYS2 make no
PATH, `UV_SYSTEM_CERTS=1` e `uv sync --extra dev`. O problema não é "make
não funciona no Windows" — é que **nada disso está automatizado nem
documentado**, e quatro gates prescritos pelos docs não existem de fato
(lock versionado, import-linter, cobertura ativa, receitas portáveis).

### Premissas

- MSYS2 com GNU Make 4.4.1 já instalado em `C:\msys64` (validado).
- `gh` autenticado na conta com acesso ao repo (validado nesta sessão).
- GitHub Free + repo privado: branch protection indisponível (gates de PR
  observacionais — ADR 1.1.0002).
- A receita manual validada em 2026-07-12 continua reproduzível
  (`make check` EXIT=0).

### Dependências

Nenhuma (`depends_on: []`).

## 4. Invariantes e regras

- **Local e CI executam o mesmo gate de qualidade de código:** ambos
  rodam `make check` na íntegra. Assimetrias conhecidas e aceitas:
  `check_stage_issue.py` é best-effort (pula sem `gh` autenticado — caso
  do runner), e o CI carrega checks de **processo** adicionais
  (`guard-main-source`, `audit-gate`) que não são gates de qualidade de
  código.
- **`make check` é a soma de todos os gates bloqueantes de código:**
  lint, typecheck, layout (check_layout **e** import-linter), lock-check
  (`uv lock --check`), docs-check e testes **com cobertura**
  (`fail_under = 90`).
- **`uv.lock` versionado e sincronizado:** quem muda `pyproject.toml`
  regenera o lock no mesmo commit (CONVENTIONS §5); o drift é pego
  mecanicamente pelo `uv lock --check` do `make check`.
- **Receitas do Makefile não dependem de shell POSIX** — nenhum
  `if [ -f ]`, `find`, `rm -rf` ou `printf` inline; portabilidade via
  comandos únicos ou scripts Python. Verificável por inspeção mecânica
  (grep dos construtos proibidos no Makefile).
- **Toda regra de LAYOUT.md §3 expressável como contrato de import tem
  contrato import-linter correspondente** (skill `import-linter-rules`).
  Regras de LAYOUT não-expressáveis como contrato de import (wiring só no
  composition_root; "exceto via port") permanecem com `check_layout.py` +
  revisão manual; contratos que dependem de estrutura futura (ex.:
  `independence` entre BCs quando o 2º BC existir) ficam **anotados no
  arquivo de contratos** com a condição de ativação.

## 5. Casos de erro e exceções

- **Cobertura do scaffold < 90% ao ativar `--cov`:** medição real atual =
  **33%** (69 de 103 statements descobertos), concentrada no kernel
  `shared/` (`pagination.py`, `logging/config.py`,
  `database/connection.py`, ports `clock`/`id_generator`,
  `system_clock.py`, `uuid4_generator.py`, `http/*`, `settings.py`) e no
  bootstrap (`composition_root.py`, `main.py`). Comportamento esperado:
  escrever a suite de testes desses módulos (unit + e2e da app factory)
  **antes** de ligar o `--cov` no `check` — não abaixar o `fail_under`,
  não usar `omit` para esconder código de produção.
- **import-linter incompatível com o grafo atual** (ex.: diretório `in/`
  é keyword Python; pacotes de features ainda vazios): ajustar a forma dos
  contratos (contratos aplicáveis ao que existe hoje + preparados para
  features futuras), nunca desabilitar o gate.
- **`git.exe` do MSYS2 ganhando do Git for Windows no PATH:** falha
  conhecida (churn CRLF fantasma de ~2900 linhas em teste anterior). A
  documentação de setup exige verificação `Get-Command git` após alterar
  o PATH.
- **Hooks não instalam/rodam no Windows:** validar `pre-commit` e
  `commit-msg` com commit real; se `language: system` falhar por python
  fora do venv, corrigir a configuração do hook.

## 6. Decisões técnicas relevantes

> **Critério de ADR nesta Stage:** ganham ADR as duas decisões
> **caras/irreversíveis de reverter** (ambiente de desenvolvimento da
> máquina; postura de enforcement dos gates de PR). As demais decisões
> abaixo tiveram alternativas reais, mas são **reversíveis-baratas**
> (troca de alvo de Makefile, local de config): ficam registradas aqui
> com fonte rastreável (pergunta respondida via `AskUserQuestion` em
> 2026-07-14), sem ADR próprio — reclassificá-las depois custa um ADR
> novo, não uma migração.

### Ambiente de desenvolvimento Windows-nativo (revoga POSIX-only)
- **O quê:** Windows nativo (PowerShell + MSYS2 make no PATH global do
  usuário + uv com `UV_SYSTEM_CERTS`) é o ambiente de desenvolvimento
  suportado de primeira classe; receitas do Makefile ficam
  shell-agnostic; devcontainer/WSL viram opção, não requisito.
- **Por quê:** o projeto roda 100% em Windows nativo; a premissa
  POSIX-only do template forçava fricção (devcontainer) sem ganho.
- **Fonte:** issue #1 (corpo + comentário 2026-07-12); pergunta
  respondida na sessão 2026-07-14 (opção "PATH global do usuário").
- **ADR:** [`../../adr/1_1_0001-windows-native-dev-environment.md`](../../adr/1_1_0001-windows-native-dev-environment.md)

### Gates de PR observacionais (GitHub Free)
- **O quê:** os gates de PR do GIT-WORKFLOW (CI verde, +1 aprovação,
  merge commit) permanecem prescritos, mas **não são impostos** por
  branch protection (indisponível em repo privado no plano Free); o
  enforcement é por disciplina + checks de CI (`guard-main-source`,
  `audit-gate`).
- **Por quê:** custo de upgrade não se justifica para dev solo no piloto;
  a restrição precisa ficar registrada para não virar falsa premissa.
- **Fonte:** issue #1; `.github/workflows/ci.yml` (job guard-main-source).
- **ADR:** [`../../adr/1_1_0002-observational-pr-gates.md`](../../adr/1_1_0002-observational-pr-gates.md)

### `make setup` usa `uv sync --extra dev`
- **O quê:** substituir `uv pip install -e ".[dev]"` por
  `uv sync --extra dev` no setup (gera `uv.lock`, instala o pacote
  editável, alinha com o CI, que já usa `uv sync`).
- **Por quê:** local e CI divergiam exatamente aqui; `uv run` sem sync
  monta venv sem o pacote (`ModuleNotFoundError`).
- **Fonte:** issue #1 (comentário — itens novos de escopo).

### Gate de cobertura roda dentro de `make check`
- **O quê:** o passo de testes do `make check` roda `pytest --cov`
  (dispara `fail_under = 90`); `make test`/`make test-fast` continuam sem
  cov para o loop rápido local.
- **Por quê:** gate que depende de lembrar de rodar outro alvo não é
  gate; CI herda automaticamente porque executa `make check`.
- **Fonte:** pergunta respondida na sessão 2026-07-14 (alternativas
  CI-only e alvo separado descartadas).

### import-linter coexiste com `check_layout.py`
- **O quê:** import-linter entra como gate de contratos de import
  (layers/forbidden/independence espelhando LAYOUT §3);
  `check_layout.py` permanece cobrindo o que o linter não vê (diretórios
  obrigatórios por feature, regras por caminho de arquivo).
- **Por quê:** redundância parcial aceita como defesa em profundidade; a
  remoção do script custaria cobertura estrutural real.
- **Fonte:** pergunta respondida na sessão 2026-07-14; skill
  `import-linter-rules`.

### `UV_SYSTEM_CERTS` com casa dupla (settings versionado + env do usuário)
- **O quê:** criar `.claude/settings.json` (compartilhado, versionado)
  com o env `UV_SYSTEM_CERTS=1` **e** gravar a mesma variável no
  ambiente do usuário Windows (mesmo ato de setup de máquina que o PATH
  do make); remover `.claude/settings.local.json` do rastreamento e
  adicioná-lo ao `.gitignore`.
- **Por quê:** `*.local.json` é override de máquina por convenção do
  Claude Code; o settings versionado cobre sessões Claude, mas **não**
  um PowerShell comum — sem a variável no ambiente do usuário, `make
  setup` fora do Claude falharia TLS (a falha exata que motivou a
  variável).
- **Fonte:** pergunta respondida na sessão 2026-07-14; issue #1
  (comentário); achado do Checkpoint A (gap do shell comum).

### `tree.txt` permanece gitignorado
- **O quê:** manter a decisão do template (`.gitignore` já lista
  `tree.txt`; `make clean` o remove); o arquivo é gerado localmente por
  `scripts/regen_tree.py` e a regeneração entra na documentação de setup.
- **Por quê:** artefato derivado do filesystem — versionar duplicaria o
  estado do repo e geraria churn em todo PR.
- **Fonte:** `.gitignore` (template); roadmap §Stage 1.1 exige apenas
  "tree.txt gerado".

## 7. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Cobertura do scaffold < 90% ao ativar `--cov` (medição atual: 33%) | A | M | Task dedicada: suite de testes do kernel `shared/` + bootstrap (lista de módulos em §5) escrita e verde **antes** de ligar o `--cov` no `check` |
| PATH global do usuário faz `git.exe` do MSYS2 sombrear o Git for Windows | M | A | Posição no PATH (user PATH avaliado após system PATH); verificação `Get-Command git` documentada; nunca prepend |
| import-linter não lida com o layout atual (pacote `in/`, features vazias) | M | M | Contratos limitados ao expressável hoje (§4); condições de ativação futuras anotadas no arquivo de contratos |
| `make`/`uv` rodado fora do Claude Code sem `UV_SYSTEM_CERTS` | M | M | Casa dupla da variável (settings versionado + env do usuário Windows) — ver §6 |
| Hook `commit-msg` (`language: system`) não acha python no Windows | B | M | Validar com commit real durante a execução; ajustar `entry`/`language` se falhar |
| `uv sync` re-resolver dependências e mudar versões vs. ambiente validado | B | B | Lock commitado na própria Stage; `make check` verde após sync é critério de aceite; drift futuro pego por `uv lock --check` |

## 8. Critérios de aceitação

- [ ] `make setup && make check && make test` verdes na máquina local
      (Windows nativo), em PowerShell comum (fora do Claude Code) — DoD
      do roadmap.
- [ ] Receitas do `Makefile` sem construtos POSIX — verificação mecânica:
      grep por `if [ `, `find `, `rm -rf`, `printf` no Makefile retorna
      vazio.
- [ ] `make setup` gera o `uv.lock`; lock versionado; `make check` inclui
      `uv lock --check` (drift de lock falha o gate).
- [ ] import-linter instalado, com contratos cobrindo toda regra de
      `docs/LAYOUT.md` §3 expressável como contrato de import (regras
      futuras/não-expressáveis anotadas no arquivo de contratos), rodando
      em `make check`, no pre-commit e no CI (via `make check`).
- [ ] Gate de cobertura ≥ 90% efetivamente executado em `make check` e
      **verde** (inclui a suite nova do kernel `shared/` + bootstrap).
- [ ] `tree.txt` gerado por `scripts/regen_tree.py`.
- [ ] Hooks `pre-commit` e `commit-msg` instalados e validados no Windows
      (commit real passando pelo hook).
- [ ] ADR 1.1.0001 (ambiente Windows-nativo) em `accepted`.
- [ ] ADR 1.1.0002 (gates de PR observacionais) em `accepted`.
- [ ] `README.md` e `docs/runbooks/validate-ci-gate.md` corrigidos (não
      prescrevem mais devcontainer/WSL como único caminho).
- [ ] Bloco da Stage 1.1 no `docs/roadmap.md` corrigido (sem
      `features/orders/`, complexidade M, escopo real).
- [ ] `.claude/settings.json` versionado com `UV_SYSTEM_CERTS`; variável
      também no ambiente do usuário Windows; `settings.local.json` fora
      do git.

## 9. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — Sim
      (Stage não introduz contratos de código; `contratos_introduzidos: []`
      no roadmap).
- [x] Toda decisão em §6 tem fonte rastreável? — Sim (issue #1, perguntas
      respondidas em 2026-07-14, docs citados).
- [x] Toda integração externa tem contrato definido? — Sim (não há
      integração externa nesta Stage).
- [x] Decisões com alternativa real descartada têm ADR escrito? — Sim
      para as decisões **caras/irreversíveis** (1.1.0001 e 1.1.0002); as
      decisões reversíveis-baratas de §6 ficam sem ADR por critério
      explícito (ver preâmbulo do §6) — reclassificação futura custa um
      ADR novo, não migração.
- [x] Dependências de Stages anteriores estão satisfeitas? — Sim
      (`depends_on: []`).
- [x] Stage cabe em ~3–12 Tasks? — Sim (estimativa: 8–10 Tasks).
- [x] Riscos críticos têm mitigação plausível? — Sim (§7).
- [x] O gate novo (cobertura em `make check`) nasce verde? — Planejado,
      não garantido a priori: medição atual é 33%, e a ativação do gate é
      **condicionada** (§5) à suite nova do kernel `shared/` + bootstrap
      estar verde antes de ligar o `--cov` no `check`. O critério de
      aceite correspondente (§8) exige o gate ativo **e** verde.

## 10. Referências

- [`../../overview.md`](../../overview.md) §6 (restrições técnicas)
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.1-bootstrap` e `1.2-ci`
- Issue [#1](https://github.com/MarceloSanC/restaurant-hub/issues/1)
  (corpo + comentário de achados de ambiente, 2026-07-12)
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `1_1_`)
- Skills: `hex-arch-python`, `import-linter-rules`
- [uv — lockfile e sync](https://docs.astral.sh/uv/concepts/projects/sync/)
- [import-linter — contract types](https://import-linter.readthedocs.io/)

---
name: stage-audit
description: Auditoria SEGURA (read-only) de uma Stage do pipeline antes do PR — confere se o que foi implementado bate com `concept.md`/`technical.md`, se os gates passam e se há gaps/findings bloqueantes. Invocar quando o usuário pedir "auditar stage N.M", "auditoria da stage", "valida stage", "stage X está pronta para PR?", "tem gap na stage?", "tudo verde para abrir PR?", "confere se o stage X fechou", ou ao revisar uma stage de outra sessão. Triggers em PT. Skill de PROCEDIMENTO + GUARDRAIL — codifica o varredor mecânico (quais scripts rodar, quais arquivos cruzar) e protege contra o falso verde do checklist (anti-viés — a auditoria que só marca caixinhas perde o achado que importa). Lean toward triggering — custo de auditar é baixo, custo de mergear stage com gap silencioso é alto. A SAÍDA não é só relatório de gate — sempre produz, em linguagem clara (jargão glosado entre parênteses) e com lente de valor + design escalável/responsabilidade — (1) overview e conceitos, (2) tasks→arquivos (links)→o que entrega, (3) gates garantidos 100%, (4) decisões de arquitetura, (5) findings por escopo, (6) aprendizados→skills. Disparada por "Audite stage N.M" / "auditar stage N.M".
metadata:
  status: accepted
  applies_when:
    camada_alvo: [any]
    invoked_at: [pre-pr, pre-merge, stage-review]
---

# Stage Audit (read-only)

Procedimento para **auditar uma Stage** depois que ela é declarada
`done` localmente e antes de abrir/mergear o PR. Combina três coisas:

1. **Varredor mecânico** — comandos e cruzamentos que se repetem em
   toda auditoria (descoberta de arquivos, scripts de gate, mapeamento
   de invariantes → testes).
2. **Pointer** — para cada item, aponta o trecho exato dos docs do
   próprio projeto que define o critério (concept §11, technical §3,
   PIPELINE §9.5, etc.). Não duplica regra — só te leva lá.
3. **Guardrail anti-viés** — instruções explícitas para que o agente
   **não termine** a auditoria apenas porque o checklist deu verde.
   Auditoria que vira "marcar caixinhas" é pior que nenhuma.

> **Julgamento read-only; aplicação é fase separada.** A **passada de
> auditoria** (Fases A–D-bis) é read-only por design — o anti-viés depende
> de o auditor formar o veredito **sem a mão no conserto** (senão racionaliza
> o próprio verde). Terminado o julgamento, a **fase de aplicação** empurra
> os fixes para o **PR existente** (push na branch + atualiza o corpo e o
> checklist do PR), **completa as caixinhas que a auditoria validou** e
> **registra a auditoria no PR** — obrigatório, não opcional: (1) comentário
> com o veredito (status global + gates numéricos + fixes aplicados com
> hash) e (2) o label de auditoria do corpo (linha `> **Auditoria:** ...`,
> CONVENTIONS §3.6) gravado como **`complete`** — o comentário do veredito é
> quem cita a data e o veredito. O workflow `audit-gate` (CI) falha enquanto o
> status não for `complete`. Auditoria sem marca no PR **não existe** para quem
> decide o merge.
>
> ⚠️ **Você é o freio, não o penúltimo freio.** O `audit-gate` **sinaliza**, mas
> **não trava** o merge: repo privado em GitHub Free não permite branch
> protection, então nenhum check é *Required* — PR com check vermelho fica
> `UNSTABLE`, não `BLOCKED`, e `gh pr merge` passa assim mesmo (GIT-WORKFLOW
> §Gates de PR). Não grave `complete` contando que "se algo escapar, o CI pega".
> Não pega.
>
> **Nunca faz merge** — é do usuário, salvo pedido explícito. Branch alheia:
> `git show` para ler; checkout + push para aplicar.

---

## Quando usar

- Usuário pede explicitamente ("audita stage 4.1", "valida stage X",
  "stage Y está pronto para PR?", "tem gap?").
- Antes de abrir PR de uma Stage (gate de saída da Fase 4, antes do
  `gh pr create`).
- Antes de fazer `gh pr merge` em PR de Stage (auditoria do reviewer).
- Ao retomar uma Stage que ficou parada — confirmar se o que está
  marcado `done` está mesmo `done`.
- Auditar Stage em **branch alheia** sem trocar working tree: use
  `git show <branch>:<path>` em vez de `Read` direto (e
  `git diff origin/<base>...<branch> --name-only` para o inventário).

**NÃO usar para:**
- Revisão de PR comum (não-Stage) — usar skill `review` ou code review
  manual.
- Auditoria de segurança — usar `security-review`.
- Verificar feature funcionando no navegador — usar `verify` ou `run`.

---

## Workflow

### Fase A — Carregar contexto (sem julgar ainda)

1. Ler **`docs/stages/<N.M>-<slug>/concept.md`** inteiro. Pontos-chave
   a anotar: §1 (escopo dentro/fora), §4 (contratos), §5 (invariantes
   I1..IN), §6 (casos de erro C1..CN), §7 (decisões D1..DN),
   §11 (critérios de aceitação A1..AN), §13 (questões em aberto Q1..QN).
2. Ler **`docs/stages/<N.M>-<slug>/technical.md`** inteiro. Pontos-chave:
   §1 (estratégia, estrutura de pastas), §2 (Tasks), §3 (gate de saída +
   mapping invariante↔teste), §7 (post-execution `[decision]`/`[finding]`/`[deviation]`/`[measurement]`).
3. Identificar **`camada_alvo`** no frontmatter — muda o checklist da
   Fase D (mono-layer domain ≠ vertical-slice multi).
4. Ler docs referenciados apenas **sob demanda** (ex.: `LAYOUT.md` §3
   se há dúvida sobre regra de import; `PIPELINE.md` §4.2/4.3 se há
   dúvida sobre atomicidade da Stage; `GIT-WORKFLOW.md` §Gates de PR).

### Fase B — Rodar varredores mecânicos (paralelo quando possível)

Todos read-only. Salvar saída para mapear contra concept/technical.

```bash
# Estado do branch (sanity)
git status
git log --oneline origin/$(base)..HEAD     # base = develop (ou main em hotfix)

# Scripts de gate do projeto (vivem em scripts/)
uv run python scripts/check_layout.py
uv run python scripts/check_technical_postexec.py docs/stages/<N.M>-<slug>/technical.md

# Testes + coverage da Stage
uv run pytest tests/unit/features/<bc>/<camada>/ -v \
  --cov=src/myproject/features/<bc>/<camada> \
  --cov-report=term-missing --cov-fail-under=90

# Gate completo (mesmo que CI vai rodar)
make check
```

**Capturar números, não impressões:** "143 passed, 100% coverage" é
evidência; "está tudo verde" não é.

**Antes de declarar `make check` verde, ler o target literal no
`Makefile`** — confirmar que cada gate declarado em config (`fail_under`
do `pyproject`, `import-linter`, `mypy --strict`, `bandit`, `safety`)
está mesmo invocado por algum comando do alvo `check`. Configuração que
nenhum comando dispara é decoração — conceito ["Gate inerte ou míope"](reference/falso-verde.md#gate-inerte-ou-míope).
E **quando um gate falha, achar qual falhou primeiro na cadeia**: o de
baixo pode nunca ter rodado, e a causa reportada não ser a causa real.

**Toda saída colada pelo autor como estado do "antes" tem de ser
reproduzida a partir da base** — nunca da working tree (conceito
["Evidência de árvore suja"](reference/falso-verde.md#evidência-de-árvore-suja)):

```bash
# arquivo alegado como pré-existente e quebrado é adição pura desta branch?
git log --diff-filter=A -- <path>
# reproduzir o "antes" a partir da base, sem untracked contaminando
git archive origin/<base> | tar -x -C <tmp> && cd <tmp> && <comando do gate>
```

**Hashes citados:** para cada hash da §7 e de artefato de proveniência,
`git merge-base --is-ancestor <hash> HEAD`; falso é ["Rastro perdido"](reference/falso-verde.md#rastro-perdido).

**Nota — pré-requisito de Stage anterior.** Stage atual pode declarar
a anterior como pré-requisito. Pré-requisito real é "mergeada em
`develop`", não "status `done` no roadmap local". Conferir com
`git log develop --oneline | head`. Se a anterior ainda não foi mergeada,
sinalizar ao usuário — não é blocker da auditoria atual, é blocker da
**ordem de merge**.

### Fase C — Cruzar implementação ↔ docs

1. **Listar arquivos novos/modificados** vs §technical §1 (estrutura
   de pastas). Comando: `git diff --name-only origin/<base>..HEAD`.
   Comparar com `arquivos_a_criar` / `arquivos_a_modificar` declarados
   no roadmap.md para a Stage.
2. **Ler cada arquivo de implementação** (parallel batches via Read).
   Comparar contra:
   - Contratos de concept §4 (assinaturas batem?)
   - Invariantes de concept §5 (`__post_init__` valida o que se prometeu?)
   - Decisões de concept §7 (a implementação segue D1..DN ou
     contradiz silenciosamente?)
   - Detalhes técnicos da Task em technical §2 (o "Detalhes técnicos"
     foi seguido?)
   - **Invariantes negativas** (`I*` com forma "X NÃO está em Y",
     ex.: "DTO não vaza PII raw", "domain não importa adapters") —
     `assert isinstance(...)` ou type-check cobrem presença, não ausência.
     Rodar `Grep` ativo (`pattern: "<X>"`, `path: <Y>/`) e exigir
     **0 matches**. Ver conceito ["Verificação assimétrica"](reference/falso-verde.md#verificação-assimétrica).
3. **Mapear invariantes → testes**. Para cada `IN` em concept §5,
   localizar o teste que cobre (technical §3 já tem a tabela
   "mapping invariantes ↔ testes" — confirmar que existe e roda).
   Se faltar teste para uma invariante, é **finding**.
4. **Mapear critérios de aceitação (A1..AN) → evidência**. Cada `AN`
   tem que ter um comando ou inspeção que prova. São **dois** findings
   distintos: `[x]` sem evidência (marcado no escuro) e `[ ]` **com**
   evidência (o fechamento não marcou). O segundo escapou em duas Stages
   seguidas, com o critério provado e a caixa aberta: 3.5 (`b52f472`, issue
   #59) e 4.1 (`35c752d`). Conferir com
   `grep -c '^- \[ \] \*\*CA' docs/stages/<N.M>-<slug>/concept.md`, que deve
   dar **0** ao fechar. Na fase de aplicação, marcar as caixas validadas.
5. **Verificar atualização de docs derivados** (gate clássico):
   - **5.a `docs/roadmap.md`:**
     - Status da Stage na tabela §"Stages" atualizado para `done`?
     - Frontmatter `updated_at` e `last_reviewed_at` na data do merge?
     - (Se aplicável) Step que contém a Stage avançou de `not_started`
       para `in_progress`?
   - **5.b ADRs derivados (se a Stage declarou D* com ADR formal):**
     - Para cada D* em concept §7 que diz `ADR: sim` (ou cita
       `docs/adr/N_M_NNNN-<slug-do-adr>.md`), abrir o arquivo do ADR e
       confirmar **`status: accepted`** no frontmatter (não
       `draft`/`proposed`).
     - ADR novo em `draft` ao merge = blocker — a decisão precisa
       fechar antes da Stage fechar (CONVENTIONS §3).
6. **Verificar §7 post-execution do technical.md.** Se há `[decision]`,
   `[finding]` ou `[deviation]` na execução, foi registrado? Se o histórico
   git mostra commits `[N.M/--]` ou `[N.M/task-NN-extra]` (off-task),
   `§7` deveria ter a entrada justificando.

### Fase D — Judgment (a parte que NÃO se mecaniza)

Por camada-alvo, conferir o que muda. Os itens abaixo são **piso**, não
teto — sempre faça Fase D-bis (anti-viés) antes de fechar.

**Regra de aplicação:** para Stage **vertical-slice ou multi-layer**,
aplicar **todas** as sub-seções cujas camadas a Stage inclui (frontmatter
`camada_alvo` ou `arquivos_a_criar` do roadmap). Para Stage
**mono-layer**, aplicar só a sub-seção da camada-alvo.

**Se `camada_alvo` inclui `domain`:**
- Imports de `domain/` só de stdlib + outros `domain/` (LAYOUT §3 +
  hex-arch-python skill). `check_layout.py` cobre o estrutural;
  faltar checar imports de tipos pesados (`pydantic`, `sqlalchemy`,
  `fastapi`) — costuma vazar via type-hint só pra dataclass.
- `@dataclass(frozen=True)` em VOs, `eq=False` + `__eq__`/`__hash__`
  por id em entidades (ddd-tactical-patterns skill).
- Exceções herdam de `myproject.shared.domain.exceptions.base.DomainError` para
  o error handler HTTP futuro tratar como 422.
- `__init__.py` vazios (ou só docstring placeholder — verificar
  invariante literal vs espírito; ver conceito ["Literal ≠ espírito"](reference/falso-verde.md#literal--espírito)).

**Se `camada_alvo` inclui `application`:**
- Use case recebe e devolve DTO — **nunca** entidade de domínio
  (LAYOUT §7 "Regras de ouro").
- Ports são `Protocol` em `application/ports/{in,out}/`.
- Use case testado com **fake** do port (pytest-with-fakes skill),
  não mock.
- **DTOs em `application/dtos/` são `@dataclass(frozen=True)` —
  `pydantic.BaseModel` só na fronteira `adapters/inbound/http`** (LAYOUT
  §7). Pydantic em DTO da application = boundary leak.

**Se `camada_alvo` inclui `adapters/out`:**
- Adapter implementa o Protocol (repository-pattern skill).
- **Contract test** existe e roda contra fake E real
  (`tests/contract/`).
- Mapper domain↔ORM existe e é puro (sem I/O).
- **Padrão async/threading:** se a Stage (ou Stage anterior do mesmo
  BC) declarou padrão de concorrência (ex.: D* "todo método `async`
  delega para `_sync` via `asyncio.to_thread`", ou "usar `AsyncEngine`
  fim a fim"), ler **1 método como amostra** e confirmar que segue.
  Inconsistência entre métodos do mesmo adapter = finding.
- **Carga de recursos externos** (arquivos `.sql`, templates, fixtures,
  schemas): conferir que usa **`importlib.resources.files(...)`** (ou
  equivalente robusto a wheel/editable install), **não**
  `Path(__file__).parent / "..."`. O segundo quebra em pacote instalado.

**Se `camada_alvo` inclui `adapters/inbound/http`:**
- Router fino — sem regra de negócio (fastapi-thin-adapter skill).
- Pydantic só na fronteira; converte DTO → schema.
- Exceções de domínio mapeadas para status HTTP coerentes —
  **bidirecionalmente**: se concept §6 declarou tabela `erro → status`,
  conferir que (a) **cada linha** da tabela tem um `except` correspondente
  no router e (b) **cada `except` no router** aparece na tabela. Integration
  test deveria cobrir cada status code declarado.

**Se `camada_alvo` inclui `adapters/inbound/scheduler`:**
- **Gated por flag** em `Settings` (default `False` — não arranca em
  CI/dev sem opt-in). Composition root constrói sempre; lifespan decide
  se chama `start()`.
- `start()` / `shutdown()` **idempotentes** — segunda chamada não
  duplica jobs nem quebra.
- **Cron string validada cedo** no startup (`CronTrigger.from_crontab(...)`
  levanta `ValueError`) — preferível a job falhar silenciosamente.
- **Warning explícito quando lista de unidades/jobs está vazia** —
  silêncio aqui esconde misconfig (scheduler rodando sem nada
  registrado).
- Erros do use case **capturados dentro do job runner** com log `ERROR`
  — uma exceção não tratada não pode matar o scheduler nem os outros
  jobs.

**Se a Stage toca `composition_root`:**
- Wiring no único arquivo permitido (`composition_root.py` —
  composition-root skill).
- Adapter real **substitui** a fake do use case.

### Fase D-bis — Anti-viés (obrigatório antes de fechar)

> **Esta seção existe porque checklist verde não significa Stage boa.**
> Skills criam falsos verdes ao fazer o agente confundir "rodei o
> procedimento" com "auditei substantivamente". Estes prompts forçam
> uma segunda passada que **não está na lista**.

1. **Disciplina de escopo.** Para cada finding/melhoria, classificar
   POR ESCOPO **antes** de recomendar — e **não** parquear como
   "futuro" um gap que é da própria Stage só porque o roadmap já diz
   `done` ou porque o §7/§13 oferece uma saída fácil:
   - **Dentro da Stage** (concept §1 "dentro" ou critério de aceitação
     A*) → corrigir antes do PR (ou virar Task, se ainda há ciclo). É a
     fatia que a Stage prometeu; follow-up que mexeria nas **mesmas
     linhas** é fragmentação, não cuidado.
   - **Q\* deferida-por-design** (concept §13) → só se a resposta
     provisória **não** dizia "fazer se trivial"; senão é
     [Literal ≠ espírito](reference/falso-verde.md#literal--espírito) (a Q* virou desculpa).
   - **Issue pós-Stage separada** → capacidade/dependência/módulo novo;
     **buscar o backlog antes** de abrir card (`gh issue list --search`;
     git-versioning-pointer §Criar issue) para não fragmentar.
   O teste é o **escopo** (concept §1 + A*), não o **status**. Ver
   conceito ["Escopo empurrado pra frente"](reference/falso-verde.md#escopo-empurrado-pra-frente).
2. **Pergunta meta:** "Se eu soubesse que o agente que fechou esta
   Stage tem **histórico de mergear com bug**, o que eu olharia?" —
   Liste 2-3 itens **específicos desta Stage** e confira pelo menos
   um. Itens triviais (`make check` passou? coverage ≥ 90%?) **não
   contam** — eles já foram checados na Fase B. O alvo aqui é
   substância: defaults coerentes (ex.: "os defaults de config formam
   uma combinação válida?"), invariantes de negócio que o teste não
   cobre (ex.: "o use case retorna o quê em input vazio — é o esperado
   ou um silent default que mascara erro?"), comportamento sob entrada
   degenerada (ex.: "use case retorna o que se a lista vier vazia?").
3. **Caça ao silencioso:** Procure no diff novo por:
   - `# TODO`, `# FIXME`, `# XXX`, `pass  # noqa`
   - `pytest.skip`, `xfail`, `@pytest.mark.skip`
   - **Silenciadores de type-checker:** `# type: ignore`,
     `cast(`, `: Any` em ponto sensível (boundary de adapter,
     conversão de DTO/entidade, retorno de função pública)
   - **Silenciadores de linter:** `# noqa`, `# noqa: <code>`
   Cada ocorrência pede 1 linha justificando (em commit, comentário
   ou §6/§7 do concept). Ausência de justificativa = finding. Ver
   conceito ["Rastro perdido"](reference/falso-verde.md#rastro-perdido).
4. **Caça ao não-previsto:** Procure por arquivos/funções/classes
   **fora** do que `arquivos_a_criar` do roadmap previu. Pode ser
   refactor legítimo — pode ser escopo escapando.
5. **Caça à decisão escondida:** Procure por `if`/`match` no código
   novo cujo critério **não** aparece em concept §6 (casos de erro)
   ou §7 (decisões). Decisão de comportamento sem rastro = finding.
   - **Sub-bullet — cross-check de uso ativo (dead-config check):**
     para validators/hooks/handlers/middlewares novos, encontrar
     **≥ 1 call-site fora do próprio teste**. Coverage 100% em
     validator só prova que o teste unitário dele roda — pode estar
     definido e nunca plugado no pipeline real. Comando útil:
     `Grep "<nome_do_validator>"` no projeto inteiro, excluindo o
     próprio arquivo de teste. Ver conceito ["Definido mas não plugado"](reference/falso-verde.md#definido-mas-não-plugado-dead-config).
   - **Sub-bullet — ramo testado × ramo de produção:** se o código novo
     ramifica por **knob de config** (`if settings.x`, `match backend`…),
     abrir a **fonte de configuração real** (`Settings`/`.env.example`/
     composition root) e ler o valor declarado para produção. Se o teste
     instancia o adapter direto (pegando o **default do construtor**) e
     esse default **diverge** do valor de produção, o comportamento novo
     está provado no ramo errado. Exigir o valor de produção no teste (ou
     parametrizar nos dois ramos). Ver conceito ["Verificação assimétrica"](reference/falso-verde.md#verificação-assimétrica).
6. **Caça ao teste preguiçoso:** abra 2-3 arquivos de teste no
   diff novo e leia os asserts. Sinais de preguiça (cada um = finding):
   - `assert result is not None` / `assert len(x) > 0` sem cobrir
     o valor concreto.
   - `assert isinstance(x, T)` usado como prova de comportamento
     (prova tipo, não comportamento).
   - `mock.assert_called()` sem `assert_called_with(...)` específico
     (prova que chamou, não com o quê).
   - Cenário rotulado "happy path" mas asserts só sobre presença de
     campos, não sobre valores numéricos calculados.
   - Teste de erro com `pytest.raises(Exception)` genérico em vez do
     tipo específico do contrato.
7. **Pense diferente do shape do checklist:** se a Stage é
   `mono-layer domain`, o checklist é curto; isso **não significa**
   que a auditoria é curta. Em mono-layer, o risco se concentra
   na modelagem — gaste mais tempo lendo as entidades/VOs do que
   rodando scripts.
8. **Se a auditoria fechou em < 5 minutos** sem ler nenhum arquivo
   de implementação inteiro, provavelmente está rasa. Volte e leia
   pelo menos os arquivos centrais da camada-alvo.
9. **Se delegou a sub-agente** (Explore, general-purpose) para
   carregar contexto ou checar itens em batch: o relatório dele
   precisa trazer **2-3 trechos de código verbatim** (não só
   veredito A/I/C) das partes críticas — Protocol assinaturas,
   mappers de boundary, §7 post-execution, validators de invariante.
   Leia esses trechos à mão e confirme. Sem isso, "rodei < 5 min"
   só foi **terceirizado**, não evitado (conceito ["Delegação cega"](reference/falso-verde.md#delegação-cega)).
   Se o prompt do sub-agente não pediu verbatim, re-prompt antes de
   fechar.
10. **Caça à regra fora do dono.** O import-linter só prova que o
    import é **permitido** — não que a regra mora no **dono** dela.
    Para cada regra de negócio nova no diff (predicado de elegibilidade,
    validação, política de emissão, tradução de erro), perguntar **onde
    mora** e **quantas vezes existe**:
    - **Duplicada?** `Grep` no predicado/constante central. A mesma
      regra em fake **e** adapter, ou em dois slices = finding — sobe
      para o domínio e ambos consomem.
    - **Camada errada?** Decisão que muda resultado de negócio vivendo
      em `adapters/` ou `application/` pertence a `domain/`.
    - **Atravessando BC?** Um BC consumindo detalhe interno de outro
      (tipo concreto, nome de coluna, tabela) em vez de port/Protocol
      público = finding.
    - **Sem dono?** Exceção, VO de identidade ou tradutor de erro criado
      num slice e usado por outros: fica no slice dono; `shared/` só se
      não há dono (LAYOUT §4).
    Ver conceito ["Estrutural ≠ semântico"](reference/falso-verde.md#estrutural--semântico).

### Fase E — Relatório (explicação do valor entregue + gate)

> **A saída tem DUAS funções no mesmo documento, sempre as duas:**
> **explicar em linguagem clara o que a Stage entregou de valor**
> (seções 1-4) e **registrar o gate + findings** (seções 5-6). Não
> escolha uma — quem dispara "Audite stage N.M" recebe as seis seções.
> Toda a varredura das Fases A-D-bis **alimenta** estas seções; ela não
> é a saída.

**Regras transversais (valem para TODAS as seções):**
- **Linguagem clara.** Escreva para quem não acompanhou a implementação.
  Cada termo técnico/jargão ganha glosa curta entre parênteses na
  primeira aparição — ex.: "invariante (regra que o objeto garante
  sempre verdadeira)", "port (interface que a aplicação declara e um
  adapter implementa)".
- **Lente de valor + design (o foco do usuário).** Em cada seção,
  responda implicitamente: *o que isto entrega de valor de fato?* e
  *foi projetado como módulo escalável e de responsabilidade bem
  definida — ou não?* Aponte onde o design ajuda e onde acumula dívida.
- **Listas, não tabelas, nas seções 1-4.** As tabelas (invariante↔teste,
  critério↔evidência) ficam na seção 3.
- **Fato, não impressão.** Toda afirmação de "existe/funciona" aponta
  `arquivo:linha`, comando+resultado numérico, ou teste. Links markdown
  clicáveis nos arquivos (seção 2).

**Template do relatório:** copiar o esqueleto de
[reference/relatorio-fase-e.md](reference/relatorio-fase-e.md) (status global, as seis
seções — com os 4 filtros da seção 6 — e a conclusão) e preencher.

**Regra de classificação:**
- **blocker** — viola invariante I*, contradiz decisão D*, faz teste
  falhar, ou faz script de gate falhar.
- **non-blocker** — desvio do plano sem impacto funcional, sugestão
  de melhoria, falsa positiva conhecida (`__init__.py` com docstring
  é exemplo).
- **observação** — info que o reviewer humano deve saber mas não
  exige ação (ex.: coverage de arquivo de Stage anterior está em 0%).

---

## Conceitos de falso verde (anti-checklist)

O catálogo mora em [reference/falso-verde.md](reference/falso-verde.md): cada conceito
com sintoma, **Pergunta** e **Tratamento**, a tabela de casos históricos e a regra de
como o catálogo cresce. As fases acima citam o conceito pelo nome no ponto de uso; os
que nenhuma fase cita só valem para quem leu o arquivo — **ler o catálogo inteiro antes
de fechar a Fase D-bis**.

- [Escopo empurrado pra frente](reference/falso-verde.md#escopo-empurrado-pra-frente)
- [Literal ≠ espírito](reference/falso-verde.md#literal--espírito)
- [Verificação assimétrica](reference/falso-verde.md#verificação-assimétrica)
- [Evidência de árvore suja](reference/falso-verde.md#evidência-de-árvore-suja)
- [Gate inerte ou míope](reference/falso-verde.md#gate-inerte-ou-míope)
- [Definido mas não plugado (dead-config)](reference/falso-verde.md#definido-mas-não-plugado-dead-config)
- [Estrutural ≠ semântico](reference/falso-verde.md#estrutural--semântico)
- [Solução complexa onde cabia a simples (concern capturado)](reference/falso-verde.md#solução-complexa-onde-cabia-a-simples-concern-capturado)
- [Rastro perdido](reference/falso-verde.md#rastro-perdido)
- [Delegação cega](reference/falso-verde.md#delegação-cega)
- [Lei universal, representante estreito](reference/falso-verde.md#lei-universal-representante-estreito)
- [Falso vermelho ambiental](reference/falso-verde.md#falso-vermelho-ambiental)
- [Casos históricos (rastreabilidade do loop recursivo)](reference/falso-verde.md#casos-históricos-rastreabilidade-do-loop-recursivo)

---

## Anti-padrões a evitar

Os **Conceitos de falso verde** acima são a lista de anti-padrões de
*conteúdo* (✅ sem evidência → Verificação assimétrica; `make check` verde
tomado como auditoria → Gate inerte; gap da própria Stage parqueado como
"futuro" → Escopo empurrado pra frente). Não há por que repeti-los aqui.

Sobram só os anti-padrões de **procedimento** (não são conceito de falso
verde — são regra de execução, já ancorada acima):
- **Não editar código na passada de julgamento** — ela é read-only (anti-viés);
  a correção vai para a **fase de aplicação** separada, que empurra os fixes
  para o PR (ver callout no topo). Merge nunca — é do usuário.
- **Não usar o checklist da Fase D como única fonte** — ele é incompleto
  por definição (cada Stage tem shape novo); a Fase D-bis existe por isso.
- **Não auditar sem ter lido `concept.md` inteiro** — é a única fonte que
  cobre o "porquê" (Fase A #1). Sem ele vira inspeção sem âncora.

---

## Mapa rápido (onde está cada critério)

A tabela "procura por... → está em" (seções do `concept.md`/`technical.md`, docs de
convenção e scripts validadores) mora em
[reference/mapa-rapido.md](reference/mapa-rapido.md).

---

## Skills relacionadas (consultar quando o caso aparecer)

- `git-versioning-pointer` — antes de qualquer operação git/GitHub
  pós-auditoria (push, PR, merge).
- `didatic-explanation` — antes de escrever o relatório da Fase E: a
  "linguagem clara" das seções 1–6 segue as regras dela.
- `hex-arch-python` — para julgar imports/camadas no diff.
- `ddd-tactical-patterns` — para julgar Entity vs VO, agregados.
- `pytest-with-fakes` — para julgar se teste de application usa fake
  vs mock.
- `repository-pattern` — para julgar adapter de persistência.
- `fastapi-thin-adapter` — para julgar router HTTP.
- `composition-root` — para julgar wiring.
- `import-linter-rules` — para julgar contratos do import-linter
  quando a Stage muda regras de dependência.
- `task-ordering-hex` — para julgar ordem das Tasks (inside-out vs
  vertical-slice).
- `skill-builder` — quando esta skill falhar em prevenir um falso
  verde, atualizar a seção "Conceitos de falso verde" (refinar
  conceito existente; só criar novo se padrão genuinamente novo).

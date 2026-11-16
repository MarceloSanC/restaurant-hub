---
name: issue-audit
description: "Auditoria de uma issue (ou grupo de issues) antes do PR/merge (julga read-only; escopo fechado → mergeia, Fase F) — confere se o que foi implementado bate com o CORPO da issue no GitHub (## Escopo + ## Critério de aceitação), se os gates passam, e classifica achados POR ESCOPO (dentro da própria issue, issue separada, ou não-issue). Invocar quando o usuário pedir \"auditar issue #N\", \"auditoria da issue\", \"valida issue\", \"issue X está pronta pra PR?\", \"tem gap na issue?\", \"essas issues entregaram o que prometeram?\", \"audita o épico\", \"confere se a #N fechou de verdade\", ou ao revisar uma issue de outra sessão/branch. Aceita uma issue ou uma lista. Triggers em PT. Skill de PROCEDIMENTO + GUARDRAIL — codifica o varredor mecânico (gh issue view, scripts de gate, cruzamento critério↔evidência) e protege contra dois falsos verdes específicos de issue: (a) marcar critério ✅ sem evidência, e (b) empurrar refino DENTRO do escopo para \"melhoria futura\" só porque a issue parece fechada. Lean toward triggering — custo de auditar é baixo, custo de fechar issue com gap silencioso (ou de fragmentar escopo em cards concorrentes) é alto. A SAÍDA não é só relatório de gate — sempre produz, em linguagem clara (jargão glosado entre parênteses) e com lente de valor + design escalável/responsabilidade: (1) conceitos principais, (2) tasks→arquivos (links)→o que entrega, (3) gates garantidos 100%, (4) decisões de arquitetura, (5) findings por escopo, (6) aprendizados→skills. Disparada por \"Audite issue #N\" / \"audita a #N\"."
metadata:
  status: accepted
  applies_when:
    camada_alvo: [any]
    invoked_at: [pre-pr, pre-merge, issue-review, epic-review]
---

# Issue Audit

Procedimento para **auditar uma issue** (ou um **grupo de issues** /
épico) antes de abrir/mergear o PR, ou ao revisar o que outra sessão
entregou. É a irmã da skill `stage-audit`, adaptada para o contexto de
**issue avulsa** — que **não tem `concept.md`/`technical.md`**: a fonte
da verdade é o **corpo da issue no GitHub** (`## Escopo` +
`## Critério de aceitação`) cruzado com o git.

Combina quatro coisas:

1. **Varredor mecânico** — comandos que se repetem em toda auditoria
   (`gh issue view`, descoberta de commits/arquivos, scripts de gate).
2. **Pointer** — para cada item, aponta onde está o critério: o corpo
   da issue, `docs/LAYOUT.md`, `docs/GIT-WORKFLOW.md`, ADR citado. Não
   duplica regra — leva lá.
3. **Guardrail anti-viés** — força uma segunda passada que não está no
   checklist, porque verde de checklist ≠ issue bem entregue.
4. **Disciplina de escopo** — para cada achado/melhoria, classificar
   POR ESCOPO antes de recomendar: **dentro desta issue**, **issue
   separada**, ou **não-issue**. Esta é a parte que mais escapa.

> **Julgamento read-only; aplicação é fase separada.** A **passada de
> auditoria** é read-only por design (anti-viés: o veredito se forma sem a
> mão no conserto). Terminado o julgamento, a **fase de aplicação** empurra
> os fixes para o **PR existente** (push + atualiza corpo/checklist),
> completa as caixinhas validadas e **registra a auditoria no PR** —
> obrigatório, não opcional: (1) comentário com o veredito (status global +
> gates numéricos + fixes aplicados com hash) e (2) o label de auditoria do
> corpo (linha `> **Auditoria:** ...`, CONVENTIONS §3.6) gravado como
> **`complete`** — o comentário do veredito é quem cita a data e o veredito.
> O workflow `audit-gate` (CI) falha enquanto o status não for `complete`.
> Auditoria sem marca no PR **não existe** para quem decide o merge.
>
> ⚠️ **Você é o freio, não o penúltimo freio.** O `audit-gate` **sinaliza**, mas
> **não trava** o merge: repo privado em GitHub Free não permite branch
> protection, então nenhum check é *Required* — PR com check vermelho fica
> `UNSTABLE`, não `BLOCKED`, e `gh pr merge` passa assim mesmo (GIT-WORKFLOW
> §Gates de PR). Não grave `complete` contando que "se algo escapar, o CI pega".
> Não pega.
>
> **Escopo fechado e nada pendente → fecha o PR sozinha, sem pedir OK** (Fase F);
> sobrou algo → não mergeia e reporta o que falta. Branch alheia: `git show`
> para ler; checkout + push para aplicar.

---

## Quando usar

- Usuário pede explicitamente ("audita issue #68", "valida a #N",
  "a issue X está pronta pra PR?", "tem gap?", "audita o épico #M").
- Antes de abrir PR que fecha uma issue (gate de saída, antes do
  `gh pr create`).
- Antes de `gh pr merge` de um PR com `Closes #N` (auditoria do reviewer).
- Ao retomar uma issue parada — confirmar se o que parece entregue
  está mesmo entregue (e se o `done` do roadmap reflete a realidade).
- **Grupo de issues / épico:** auditar N issues correlatas de uma vez,
  conferindo também a **fronteira entre elas** (escopo de uma vazou
  para o card da outra? dependência entre elas respeitada?).
- Auditar issue em **branch alheia** sem trocar working tree: use
  `git show <branch>:<path>` em vez de `Read` direto, e
  `git diff origin/<base>...<branch> --name-only` para o inventário.
  (Read-only + `git show` evita decidir sobre estado errado da árvore
  quando há *flip* de checkout no meio da sessão.)

**NÃO usar para:**
- Auditar uma **Stage** do pipeline (tem `concept.md`/`technical.md`,
  invariantes I*, ADRs) — usar `stage-audit`.
- Revisão de PR comum sem issue associada — usar `review`/code review.
- Auditoria de segurança — usar `security-review`.
- Verificar feature no navegador — usar `verify`/`run`.

---

## Workflow

### Fase A — Carregar contexto (a issue é a fonte da verdade)

1. **Ler o corpo da issue inteiro** no GitHub — **não** o título da
   tabela do roadmap, **não** a memória:
   ```bash
   gh issue view <num> --json number,title,body,state,labels
   ```
   Anotar, em ordem de prioridade de auditoria:
   - **`## Escopo`** — o que está dentro/fora. É o contrato do que
     deveria ter sido feito.
   - **`## Critério de aceitação`** — os checkboxes `- [ ]`. Cada um
     vira uma linha do mapeamento critério↔evidência (Fase C).
   - **`## Problema`** — o porquê; ajuda a julgar se a solução ataca a
     causa ou só o sintoma.
   - **`## Referências`** — arquivos/pontos de toque citados; viram o
     inventário esperado de arquivos tocados.
2. **Estado da issue vs roadmap vs branch** (registrar, não bloquear):
   - `state` no GitHub (`OPEN`/`CLOSED`).
   - Status na tabela do `docs/roadmap.md` (`open`/`done`).
   - Branch mergeada em `develop`?
   - **Divergência é normal pré-merge** (roadmap pode marcar `done`
     antes do merge; GitHub fica `OPEN` até o PR fechar). Mas o status
     do roadmap é **indício, não verdade** — a verdade é git + código +
     critério de aceitação. Não deixe um `done` no roadmap encurtar a
     auditoria.
3. **Grupo de issues / épico:** se o alvo é mais de uma issue, listar
   todas e suas relações antes de julgar qualquer uma:
   ```bash
   gh issue view <epico> --json body          # sub-issues listadas no corpo
   gh issue list --search "<termo do épico>" --state all
   ```
   Anotar dependências declaradas (issue B depende de A done?) e
   possíveis sobreposições de escopo entre os cards.
4. **Mapear commits → tasks da issue.** Issue avulsa usa tag
   `[#<num>/task-NN]` (ou `[#<num>/--]` para off-task) no commit:
   ```bash
   git log --grep="#<num>" --oneline
   git log --oneline origin/<base>..HEAD       # se a branch é a da issue
   ```
   Cada commit deveria entregar uma fatia coerente do `## Escopo`.
5. Ler docs referenciados **sob demanda** (LAYOUT §3 se há dúvida de
   import; GIT-WORKFLOW §Gates de PR; ADR citado no corpo da issue).

### Fase B — Varredores mecânicos (read-only; capturar números)

```bash
# Sanity do branch
git status
git log --oneline origin/<base>..HEAD     # base = develop (ou main em hotfix)
                                           # carona de outro escopo? (GIT-WORKFLOW §Etapa 4)

# Inventário de arquivos da issue
git diff --name-only origin/<base>..HEAD

# Scripts de gate do projeto (vivem em scripts/)
uv run python scripts/check_layout.py

# Gate completo (o mesmo que a CI roda)
make check

# Coverage focada nos arquivos tocados pela issue (não a média global)
uv run pytest <testes da issue> \
  --cov=<paths tocados> --cov-report=term-missing
```

**Capturar números, não impressões:** "1779 passed, 98.15% coverage"
é evidência; "tudo verde" não é.

**Antes de declarar `make check` verde, ler o target no `Makefile`** —
confirmar que cada gate declarado em config (`fail_under`, `import-linter`,
`mypy --strict`, `bandit`) é mesmo invocado. Config que nenhum comando
dispara é decoração (conceito ["Gate inerte ou míope"](reference/falso-verde.md#gate-inerte-ou-míope)). E **quando um gate
falha, achar o gate que falhou primeiro** na cadeia: o de baixo pode nunca
ter rodado (variante *míope*).

**Toda saída que o autor colou como estado do "antes" tem de ser
reproduzida a partir da base** — não da working tree (conceito ["Evidência
de árvore suja"](reference/falso-verde.md#evidência-de-árvore-suja)):

```bash
# arquivo alegado como pré-existente e quebrado é adição pura desta branch?
git log --diff-filter=A -- <path>
# reproduzir o "antes" a partir da base, sem untracked contaminando
git archive origin/<base> | tar -x -C <tmp> && cd <tmp> && <comando do gate>
```

### Fase C — Cruzar implementação ↔ corpo da issue

1. **Arquivos tocados vs `## Escopo`/`## Referências`.** Os pontos de
   toque citados foram mexidos? Apareceu arquivo **fora** do escopo
   declarado (pode ser legítimo — pode ser escopo escapando)?
2. **Ler cada arquivo de implementação** (batches via Read) e comparar
   contra **cada bullet do `## Escopo`**. Um bullet de escopo sem
   código correspondente = finding.
3. **Mapear cada `## Critério de aceitação` → evidência.** Para cada
   `- [ ]`/`- [x]`:
   - **Marcado `[x]`** precisa de comando/arquivo:linha/teste que
     prova. ✅ sem evidência citada = finding (conceito
     ["Verificação assimétrica"](reference/falso-verde.md#verificação-assimétrica)).
   - **Não marcado `[ ]`** mas o escopo foi entregue = atualizar a
     issue (observação, não blocker).
4. **Literalidade do quantificador do critério (aprendizado-chave).**
   Ler a **palavra exata** do critério e exigir que a cobertura bata
   com ela:
   - "testes cobrindo o handler **GLOBAL**" ≠ testar a *função de
     registro* isolada num app-sonda. "Global" = ativo na app real
     (`create_app()`/composition boot). Se só há teste-sonda, falta o
     teste da **fiação** — finding.
   - "**qualquer** rota com exceção retorna X" ≠ uma rota. "todos os
     BCs" ≠ um BC. O teste tem que honrar o quantificador.
5. **Dead-config / dead-code check (aprendizado-chave).** Para cada
   peça nova ou tocada (handler, middleware, config loader, validator,
   função de boot), achar **≥ 1 call-site real fora do próprio teste**:
   ```
   Grep "<nome>"   # no projeto inteiro, excluindo o arquivo de teste
   ```
   Coverage 100% num módulo só prova que o **teste dele** roda — pode
   estar definido e **nunca plugado** no pipeline real (ex.: um helper
   criado mas nunca registrado no composition root, ou um validator com
   teste verde que nunca foi ligado ao router). Definido-sem-chamador =
   finding.
6. **Docs derivados.** `docs/roadmap.md`: status da issue na tabela e
   frontmatter (`updated_at`/`last_reviewed_at`) coerentes? (Issue
   **não** tem `§7 post-execution` — isso é de Stage; não cobrar aqui.)

### Fase D — Judgment por tipo de mudança (não se mecaniza)

Issues tocam as mesmas camadas das Stages; aplicar a sub-seção de cada
camada que a issue inclui (olhar os arquivos do diff). Piso, não teto.

- **`domain`:** imports só de stdlib + `domain/`; VOs `frozen=True`;
  exceções herdam de `DomainError`. (hex-arch-python, ddd-tactical-patterns)
- **`application`:** use case recebe/devolve **DTO**, nunca entidade;
  ports são `Protocol`; testado com **fake**, não mock; DTO é
  `@dataclass(frozen=True)` (pydantic só na fronteira HTTP). (pytest-with-fakes)
- **`adapters/out`:** implementa o Protocol; **contract test** fake+real;
  mapper puro; padrão async/threading consistente entre métodos; carga
  de recurso externo via `importlib.resources`, não `Path(__file__)`.
  (repository-pattern)
- **`adapters/inbound/http`:** router fino, sem regra de negócio; pydantic só
  na fronteira; **mapeamento erro→status bidirecional** (cada erro
  declarado tem `except`; cada `except` aparece no contrato). (fastapi-thin-adapter)
- **`adapters/inbound/scheduler`:** gated por flag (default `False`);
  `start`/`shutdown` idempotentes; cron validado cedo; warning quando
  lista vazia; erro do job capturado dentro do runner.
- **`composition_root`:** wiring no único arquivo permitido; adapter
  real substitui a fake. (composition-root)
- **`shared/infrastructure/http` (transversal, comum em issue de infra):**
  handler/middleware **registrado** no boot (não só definido); resposta
  de erro **sanitizada** (sem SQL/driver/segredo/stack ao cliente);
  detalhe interno só no **log**; ordem de middleware correta (ex.:
  catch-all interno ao CORS para a resposta de erro manter headers).

### Fase D-bis — Anti-viés (obrigatório antes de fechar)

> Existe porque checklist verde não significa issue bem entregue.
> Estes prompts forçam uma segunda passada que **não está na lista**.

1. **Disciplina de escopo (o anti-viés central desta skill).** Para
   **cada** achado/melhoria, classifique POR ESCOPO **antes** de
   recomendar — e **não** decida "é melhoria futura" só porque a issue
   parece fechada/`done`. O teste é o escopo, não o status:
   - **DENTRO desta issue** se: toca o **mesmo entregável / as mesmas
     linhas** que a issue criou, **ou** um `## Critério de aceitação`
     literal exige (ex.: o critério diz "handler global", e o que falta
     é justamente o teste da fiação global). → recomendar **implementar
     na própria branch da issue**, não num follow-up. Follow-up que
     mexeria nas mesmas linhas é fragmentação.
   - **ISSUE SEPARADA** se: é **capacidade nova / dependência nova /
     outro módulo** (ex.: trocar o *formato* do log para JSON é
     transporte, distinto do *mapeamento* de erro). Antes de propor o
     card, **buscar no backlog** (`gh issue list --search ... --state all`)
     e, se houver sub-issue aberta cujo escopo comporta, **anexar nela**
     em vez de abrir card concorrente (GIT-WORKFLOW §Etapa 1 +
     git-versioning-pointer §Criar issue). **Se a melhoria é separada
     mas ainda abstrata/incerta** (não se sabe se vai mesmo precisar) **e
     não se auto-anuncia** (esquecê-la geraria bug/dívida silenciosa, não
     um erro barulhento): ainda assim **registre como issue** — finding
     solto em docstring/`technical.md` tem risco de esquecimento
     permanente. Marque a incerteza explícita no corpo (`## Incerteza` +
     label `status: speculative`), declare o **momento previsto** (data
     *ou* condição de disparo, ex.: quando o domínio modelar
     `<condição futura>`) e **não crave a solução** como definitiva — é
     ponto de partida a reavaliar na implementação. Regra completa em
     GIT-WORKFLOW §Etapa 1.
   - **NÃO-ISSUE** se: é YAGNI **e se auto-anuncia sem custo** quando
     precisar (ex.: handler para uma exceção que nada levanta hoje; o
     catch-all já dá fallback seguro — esquecê-lo não custa nada, reaparece
     sozinho). Registrar a observação e seguir — não poluir o backlog com
     card especulativo. *Discriminador vs. ISSUE SEPARADA especulativa:* a
     melhoria **se auto-anuncia sem custo** (NÃO-ISSUE) ou é **incerta mas
     silenciosa / com risco de esquecer** (vira issue especulativa)?
   > Conceito de falso verde associado: **["Escopo empurrado pra frente"](reference/falso-verde.md#escopo-empurrado-pra-frente)**
   > — adiar um refino que é da própria issue como se fosse futuro.
2. **Pergunta meta:** "Se eu soubesse que quem fechou esta issue tem
   histórico de mergear com bug, o que eu olharia?" — liste 2-3 itens
   **específicos desta issue** e cheque ≥ 1. Itens triviais (`make check`
   passou? coverage ≥ 90%?) **não contam** — já foram na Fase B.
3. **A solução ataca a causa do `## Problema`, ou só o sintoma?** Reler
   o `## Problema` e confirmar que o `## Escopo` entregue o neutraliza
   de verdade (não um caso particular dele).
4. **Caça ao silencioso:** no diff novo, procure `# TODO`/`FIXME`/`XXX`,
   `pytest.skip`/`xfail`, `# type: ignore`/`cast(`/`: Any` em boundary,
   `# noqa`. Cada um pede 1 linha de justificativa (commit/comentário).
   Sem justificativa = finding (conceito ["Rastro perdido"](reference/falso-verde.md#rastro-perdido)).
5. **Caça ao teste preguiçoso:** abra 2-3 testes do diff e leia os
   asserts. Sinais (cada um = finding): `assert x is not None` sem o
   valor concreto; `isinstance` como prova de comportamento;
   `mock.assert_called()` sem `_with(...)`; "happy path" que só checa
   presença de campo, não valor; `pytest.raises(Exception)` genérico
   em vez do tipo do contrato.
6. **Caça ao não-previsto:** arquivos/funções fora do `## Escopo`/
   `## Referências`. Refactor legítimo ou escopo escapando?
   Se é coeso com o `## Por quê` mas fora do `## O quê` e já está
   executado e verde, o tratamento não é só "issue separada": **editar o
   corpo da issue** (seção "Escopo ampliado na execução", com o porquê e
   os hashes) para que o card volte a ser a fonte da verdade do que a
   branch fechou — e registrar que refactor desse porte abre issue própria
   antes do commit.
7. **Grupo de issues — fronteira entre cards:** o trabalho de uma issue
   vazou para a branch/PR de outra? Há `Refs #`/`Closes #` apontando
   para o card errado? Dependência declarada (B depende de A) foi
   respeitada na ordem de merge?
8. **Se fechou em < 5 min** sem ler nenhum arquivo de implementação
   inteiro, está rasa — volte e leia os arquivos centrais.
9. **Se delegou a sub-agente:** exija no relatório **2-3 trechos
   verbatim** das partes críticas (assinaturas, boundary, registro no
   boot). Leia à mão. Sem verbatim, "rodei rápido" só foi terceirizado
   (conceito ["Delegação cega"](reference/falso-verde.md#delegação-cega)).

### Fase E — Relatório (explicação do valor entregue + gate)

> **A saída tem DUAS funções no mesmo documento, sempre as duas:**
> **explicar em linguagem clara o que a issue entregou de valor**
> (seções 1-4) e **registrar o gate + findings** (seções 5-6). Não
> escolha uma — quem dispara "Audite issue #N" recebe as seis seções.
> Toda a varredura das Fases A-D-bis **alimenta** estas seções; ela não
> é a saída.

**Regras transversais (valem para TODAS as seções):**
- **Linguagem clara.** Escreva para quem não acompanhou a implementação.
  Cada termo técnico/jargão ganha uma glosa curta entre parênteses na
  primeira aparição — ex.: "value object (objeto imutável, comparado
  pelo valor e não por um id)", "port (interface que a aplicação
  declara e um adapter implementa)".
- **Lente de valor + design (o foco do usuário).** Em cada seção,
  responda implicitamente: *o que isto entrega de valor de fato?* e
  *foi projetado como módulo escalável e de responsabilidade bem
  definida — ou não?* Aponte explicitamente onde o design ajuda e onde
  acumula dívida.
- **Listas, não tabelas, nas seções 1-4.** A única tabela é a de
  critério↔evidência (seção 3).
- **Fato, não impressão.** Toda afirmação de "existe/funciona" aponta
  `arquivo:linha`, comando+resultado numérico, ou teste. Use links
  markdown clicáveis nos arquivos (seção 2).

**Template do relatório:** copiar o esqueleto de
[reference/relatorio-fase-e.md](reference/relatorio-fase-e.md) (status global, as seis
seções — com os 4 filtros da seção 6 — e a conclusão) e preencher.

**Classificação:**
- **blocker** — não atende um `## Critério de aceitação`, contradiz o
  `## Escopo`, faz teste/gate falhar, ou vaza detalhe interno ao cliente.
- **non-blocker** — desvio sem impacto funcional, refino dentro do
  escopo que dá pra fazer agora, doc derivado desatualizado.
- **observação** — info que o reviewer deve saber sem ação obrigatória
  (ex.: GitHub `OPEN` enquanto roadmap `done` — esperado pré-merge).

### Fase F — Fechamento autônomo (sincronizar → merge → limpeza)

Depois da fase de aplicação, **sem pedir OK**, a sessão de auditoria fecha o PR quando fechou
**todo** o escopo. Quem fecha, condições de entrada e paradas: fonte única em
`docs/GIT-WORKFLOW.md` §"Fechamento autônomo pela auditoria". A ordem dos comandos é a de
§"Merge e limpeza da worktree": o `complete` vem **depois** do run do último push, e a limpeza
leva a worktree, as branches e os containers dela. Antes do primeiro comando, invocar
`git-versioning-pointer` e ler [reference/fase-f.md](reference/fase-f.md): o que "escopo
fechado" quer dizer numa issue, quem **não** mergeia (a sessão que implementou a issue) e a
saída.

---

## Conceitos de falso verde (anti-checklist)

O catálogo mora em [reference/falso-verde.md](reference/falso-verde.md): cada conceito
com sintoma, **Pergunta** e **Tratamento**, a tabela de casos históricos e a regra de
como o catálogo cresce. As fases acima citam o conceito pelo nome no ponto de uso; os
que nenhuma fase cita só valem para quem leu o arquivo — **ler o catálogo inteiro antes
de fechar a Fase D-bis**.

- [Escopo empurrado pra frente](reference/falso-verde.md#escopo-empurrado-pra-frente)
- [Verificação assimétrica](reference/falso-verde.md#verificação-assimétrica)
- [Evidência de árvore suja](reference/falso-verde.md#evidência-de-árvore-suja)
- [Definido mas não plugado (dead-config)](reference/falso-verde.md#definido-mas-não-plugado-dead-config)
- [Gate inerte ou míope](reference/falso-verde.md#gate-inerte-ou-míope)
- [Sintoma ≠ causa](reference/falso-verde.md#sintoma--causa)
- [Solução complexa onde cabia a simples (concern capturado)](reference/falso-verde.md#solução-complexa-onde-cabia-a-simples-concern-capturado)
- [Rastro perdido](reference/falso-verde.md#rastro-perdido)
- [Delegação cega](reference/falso-verde.md#delegação-cega)
- [Falso vermelho ambiental](reference/falso-verde.md#falso-vermelho-ambiental)
- [Casos históricos (rastreabilidade do loop recursivo)](reference/falso-verde.md#casos-históricos-rastreabilidade-do-loop-recursivo)

---

## Anti-padrões a evitar

Os **Conceitos de falso verde** acima são a lista de anti-padrões de
*conteúdo* (✅ sem evidência → Verificação assimétrica; `make check` verde
tomado como auditoria → Gate inerte; empurrar refino da própria issue →
Escopo empurrado pra frente; follow-up sem buscar backlog → tratamento do
mesmo conceito). Não há por que repeti-los aqui.

Sobram só os anti-padrões de **procedimento** (não são conceito de falso
verde — são regra de execução, já ancorada acima):
- **Não editar código na passada de julgamento** — read-only (anti-viés); a
  correção vai para a **fase de aplicação** separada, que empurra os fixes
  para o PR (ver callout no topo). Merge só na Fase F, com o escopo fechado.
- **Não auditar sem ler o corpo da issue inteiro** — é a única fonte do
  "porquê" e do contrato (Fase A #1). Sem ele vira inspeção sem âncora.

---

## Mapa rápido (onde está cada critério)

| Procura por... | Está em |
|---|---|
| Escopo da issue (dentro/fora) | corpo da issue → `## Escopo` |
| Critérios de aceitação | corpo da issue → `## Critério de aceitação` (checkboxes) |
| Problema/causa que a issue ataca | corpo da issue → `## Problema` |
| Pontos de toque esperados | corpo da issue → `## Referências` |
| Estado real da issue | `gh issue view <num> --json state` |
| Commits da issue | `git log --grep="#<num>"` (tag `[#<num>/task-NN]`) |
| Carona de outro escopo | `git log --oneline origin/<base>..HEAD` |
| Regras de import / layers | `docs/LAYOUT.md` §3 + `hex-arch-python` skill |
| Gates de PR (CI verde, ≥90%, aprovação) | `docs/GIT-WORKFLOW.md` §Gates de PR |
| Fechamento do PR pela auditoria (Fase F) | `docs/GIT-WORKFLOW.md` §"Fechamento autônomo pela auditoria" + §"Merge e limpeza da worktree" |
| Convenção de commit/branch/PR de issue avulsa | `docs/CONVENTIONS.md` §4 + `git-versioning-pointer` |
| Buscar issue duplicada antes de criar follow-up | `git-versioning-pointer` §Criar issue + GIT-WORKFLOW §Etapa 1 |
| Validador estrutural | `scripts/check_layout.py` |

---

## Skills relacionadas

- `stage-audit` — a irmã desta skill, para **Stages** do pipeline
  (com `concept.md`/`technical.md`/invariantes/ADRs). Muitos conceitos
  de falso verde são compartilhados.
- `git-versioning-pointer` — antes de qualquer git/GitHub pós-auditoria
  (push, PR, merge da Fase F, abrir issue de follow-up).
- `didatic-explanation` — antes de escrever o relatório da Fase E: a
  "linguagem clara" das seções 1–6 segue as regras dela.
- `hex-arch-python`, `ddd-tactical-patterns`, `pytest-with-fakes`,
  `repository-pattern`, `fastapi-thin-adapter`, `composition-root` —
  para julgar o diff por camada na Fase D.
- `skill-builder` — quando esta skill falhar em prevenir um falso
  verde, refinar a seção "Conceitos de falso verde" (conceito existente
  primeiro; conceito novo só se padrão genuinamente novo).

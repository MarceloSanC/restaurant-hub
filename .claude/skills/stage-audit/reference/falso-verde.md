# Referência da stage-audit — catálogo de falsos verdes

Catálogo citado pelo [SKILL.md](../SKILL.md), que aponta cada conceito pelo nome no
ponto de uso. "Fase B", "Fase D-bis #N" e "D-bis #N" neste arquivo são seções do
`SKILL.md`.

## Sumário

- [Escopo empurrado pra frente](#escopo-empurrado-pra-frente)
- [Literal ≠ espírito](#literal--espírito)
- [Verificação assimétrica](#verificação-assimétrica)
- [Evidência de árvore suja](#evidência-de-árvore-suja)
- [Gate inerte ou míope](#gate-inerte-ou-míope)
- [Definido mas não plugado (dead-config)](#definido-mas-não-plugado-dead-config)
- [Estrutural ≠ semântico](#estrutural--semântico)
- [Solução complexa onde cabia a simples (concern capturado)](#solução-complexa-onde-cabia-a-simples-concern-capturado)
- [Rastro perdido](#rastro-perdido)
- [Delegação cega](#delegação-cega)
- [Lei universal, representante estreito](#lei-universal-representante-estreito)
- [Falso vermelho ambiental](#falso-vermelho-ambiental)
- [Casos históricos (rastreabilidade do loop recursivo)](#casos-históricos-rastreabilidade-do-loop-recursivo)

## Conceitos de falso verde (anti-checklist)

> Esta seção é **conceitos**, não exemplos numerados. Por quê:
> exemplo vira pattern-match — agente acha "limpo" só porque nenhum
> caso bate exatamente. Conceito força raciocínio: "qual destes
> padrões está acontecendo aqui?"
>
> Quando aparecer falso verde novo, primeiro perguntar **qual
> conceito existente cobre**. Só criar conceito novo se for padrão
> genuinamente novo. Casos individuais entram na tabela de
> rastreabilidade no fim.

### Escopo empurrado pra frente

Um gap que é da **própria Stage** (concept §1 "dentro", critério A*, ou
uma Q* cuja resposta provisória dizia "fazer se trivial") é parqueado
como "issue futura"/Q*/§7 porque a Stage **parece** fechada (`done` no
roadmap, §7 já escrito, muitos commits). O status — ou o escape-hatch
do §7/§13 — vira desculpa para não terminar o escopo.

- Sintoma: "isso fica pra depois" sobre algo que mexeria nas **mesmas
  linhas** que a Stage criou, ou que um critério A* exige na letra.
- O oposto também é falso verde: **inflar** a Stage puxando para ela
  capacidade que é de outra (aí o certo é issue pós-Stage separada).

**Pergunta:** "este achado é da fatia que esta Stage prometeu, ou é
capacidade/módulo novo?"

**Tratamento:** classificar por escopo (D-bis #1), não por status.
Dentro → corrigir/Task antes do PR. Fora → issue pós-Stage (buscar
backlog antes). Roadmap `done` não encurta a auditoria nem move o gap
para "futuro".

### Literal ≠ espírito

Regra escrita não captura a intenção real. Acontece quando:
- Docs/invariantes copiados entre Stages (concept §I, ADR herdado)
  ficam fora de sincronia com o código que evoluiu.
- Código tecnicamente atende a invariante mas não o espírito (ex.:
  `__init__.py` com docstring "vazio até Stage X" — literalmente
  não-vazio, mas `Stmts: 0` no coverage).
- Question Q* marcada "não trava" deixa de ser implementada quando
  a resposta provisória dizia "fazer se trivial".

**Pergunta:** "esta regra ainda descreve o que a Stage realmente quer?"

**Tratamento:** se regra **strict demais** (gate cobre, código viola,
ADR justifica) → finding non-blocker, alinhar regra com o gate
real. Se **strict de menos** (gate cego, intenção burlada) → blocker.
Para divergência §I vs gate estrutural: ver se ADR justifica
relaxamento; se sim, §I errado; se não, decisão escondida (D-bis #5).

### Verificação assimétrica

Confundir presença com ausência, execução com asserção, **ou o ramo
testado com o ramo que roda em produção**. O check prova um lado, a
auditoria assume o outro.

- `assert "field_hash" in dto` prova **presença do hash**, não
  **ausência do raw** — afirmações independentes.
- Coverage 100% prova **linha executada**, não **resultado
  verificado** (`def test_foo(): foo()` sem assert tem coverage cheio).
- Teste que instancia o adapter **direto** pega o **default do
  construtor**; produção o monta pelo composition root, que lê a
  **config real**. Quando os dois divergem, o teste prova um ramo real,
  verde e honesto — que **não é o que roda**.

**Pergunta:** "este check prova o que eu queria, ou só a contrapositiva
— e prova no **ramo que produção executa**?"

**Tratamento:** para invariante negativa ("X NÃO em Y"), rodar
`Grep "<X>"` em Y/ e exigir **0 matches**. `check_layout.py` cobre
algumas estruturais (LAYOUT §3) mas **não** as específicas da Stage.
Para coverage alto, abrir 2-3 arquivos de teste e ler asserts
(Fase D-bis #6). **Quando a Stage estende um enum** consumido por
classificação em conjuntos (frozensets, whitelists, mapas de família —
ex.: permissões por papel, tipos de turno por regra de escala): `Grep`
pelo nome do enum nos **consumidores que o particionam** e conferir que
cada valor novo caiu em exatamente uma família — o teste do emissor
prova a **emissão** do valor, não a **classificação** dele. **Quando o
código ramifica por knob de config:** exigir que o teste do
comportamento novo use o valor **declarado para produção**, não o
default do construtor (D-bis #5).

### Evidência de árvore suja

Saída colada como prova do estado de **outra** árvore (a base, o "antes"),
mas produzida na working tree local — que já tem o fix aplicado e arquivos
*untracked*. Não é "Rastro perdido": aqui **há** registro, plausível e
específico — e **falso**, verificável em um comando.

- "Rodei o gate em `develop`: 3 arquivos falham" — mas um dos 3 é **adição
  pura desta branch** e nunca existiu na base.
- A conclusão pode até estar certa (o gate *estava* quebrado) e a **causa
  declarada, errada** — a base falhava por outro motivo, a montante.

**Pergunta:** "esta saída foi reproduzida **a partir da base**, ou de uma
árvore que já contém o trabalho?"

**Tratamento:** para todo arquivo alegado como *pré-existente e quebrado*,
`git log --diff-filter=A -- <path>` (ou `git cat-file -e origin/<base>:<path>`):
adição pura ⇒ evidência falsa. Reproduzir o "antes" a partir da base limpa:
`git archive origin/<base> | tar -x -C <tmp>`.

### Gate inerte ou míope

Config declara o gate, mas nada o invoca (**inerte**); ou invoca de
forma global e mascara comportamento granular (**míope**).

- Inerte: `[tool.coverage.report] fail_under = 90` no pyproject mas
  `make check` roda `pytest` sem `--cov`. Gate decorativo.
- Míope: `fail_under = 90` global passa, mas arquivo individual da
  Stage está em 75% porque outros puxam a média.

Mesmo padrão para `import-linter`, `bandit`, `safety`, `mypy --strict` —
config existe, falta invocação ou granularidade.

**Pergunta:** "qual comando real exercita este gate, e em que
granularidade?"

**Tratamento:** ler o target do Makefile (ou job do CI) e confirmar
invocação. Para coverage, rodar
`pytest --cov=src/myproject/features/<bc>/<camada>` focado. Gate
inerte é **blocker** (configuração que ninguém roda é decoração).

### Definido mas não plugado (dead-config)

Módulo/handler/validator/middleware existe, tem coverage, mas **nenhum
call-site real** fora do próprio teste — nunca entra no pipeline. Parente
do "Gate inerte", mas do lado do código: a peça roda no teste unitário e
**não** no fluxo de produção.

- Validator/guard com teste verde mas nunca registrado no router/app.
- Config loader (ex.: `configure_logging`) definido e jamais chamado no
  boot/composition root.

**Pergunta:** "qual linha de produção **chama/registra** isto?"

**Tratamento:** `Grep "<nome>"` no projeto inteiro **excluindo** o arquivo
de teste; exigir **≥ 1 call-site real**. Zero = finding. Codificado no
sub-bullet de uso ativo (D-bis #5). Coverage 100% num módulo prova que o
**teste dele** roda, não que o **pipeline** o usa.

### Estrutural ≠ semântico

Tipo/assinatura/import bate com o que o concept pediu, mas a intenção
semântica (instância compartilhada, decisão consciente, comportamento)
ficou perdida.

- D* "X compartilhado entre A e B" → ambos têm `engine: Engine` no
  construtor (estrutural OK), mas composition root injeta duas
  instâncias diferentes (semântica quebrada).
- Use case implementa `IPort` (tipo OK), mas comportamento contradiz
  o contrato do Protocol em casos não testados.
- Import permitido pelo import-linter (estrutural OK), mas a regra
  mora fora do dono: duplicada entre fake e adapter, decisão de negócio
  no adapter, BC lendo detalhe interno de outro (Fase D-bis #10).

**Pergunta:** "este tipo/assinatura prova o comportamento que o
concept prometeu, ou só a forma?"

**Tratamento:** para cada D* do tipo "X compartilhado", abrir
`composition_root.py` e **contar instanciações** de X (`Grep` por
`create_engine(`, `httpx.AsyncClient(`, etc.) — exatamente 1
esperada, com o mesmo handle injetado em ambos os callers.

### Solução complexa onde cabia a simples (concern capturado)

A especificação cria caso especial/tipo/regra nova para tratar **local**
um sintoma cujo tratamento direto seria uma solução **geral ou a
montante** — tipicamente um concern **compartilhado** (isolamento por
tenant, fuso/corte do dia operacional, calendário de feriados,
identidade, auditoria) capturado dentro de um BC. Passa em §4.2 (um BC
só, coeso, atômico), nas "fronteiras" e na rastreabilidade — invisível
ao enforcement estrutural.

- Sintoma: **tipo/regra/nuance nova** + o **mesmo problema recorre** em
  outros consumidores do dado (ex.: o corte das 05:00 reimplementado
  num slice em vez de vir do VO `OperationalCalendar`).

**Pergunta:** "há solução mais direta/geral, ou estou remendando local um
concern compartilhado?"

**Tratamento:** a geral é o conserto; a local vira **piso declarado +
issue**, nunca solução silenciosa. Blocker se a captura corrompe a
semântica para outros consumidores; senão non-blocker + issue
transversal (buscar backlog antes). É o espelho, no eixo de design, de
"Escopo empurrado pra frente".

### Rastro perdido

Decisão tomada (off-task, silenciador, refactor inesperado, doc
parcialmente atualizado) sem registro onde o reviewer iria procurar.

- Commit `[N.M/task-NN-extra]` ou `[N.M/--]` sem entrada `[deviation]`
  em technical §7 (CONVENTIONS §3.4).
- `# type: ignore`, `cast(...)`, `: Any`, `# noqa` em ponto sensível
  (boundary de adapter, mapper DTO↔entidade, retorno público) sem
  justificativa próxima.
- `roadmap.md` table atualizado mas frontmatter (`updated_at`,
  `last_reviewed_at`) esquecido — ou inverso.
- Branch com commit de outro escopo (`fix:` solto, `chore: bump`)
  pegando carona no PR da Stage.
- Hash citado na §7 ou em artefato de proveniência que não é ancestral
  do HEAD (`git merge-base --is-ancestor`), típico depois de rebase:
  exige errata com o mapeamento antigo → novo.

**Pergunta:** "se o reviewer abrir só este arquivo/commit, ele
entende por que esta linha/commit está aqui?"

**Tratamento:** non-blocker em geral, corrigir antes do PR. Blocker
se padrão repetido em ≥3 lugares no mesmo arquivo, ou se for carona
de escopo (pedir rebase — GIT-WORKFLOW §Etapa 4).

### Delegação cega

Sub-agente (Explore, general-purpose) ou ferramenta devolve OK em
batch, e o auditor lê só o resumo.

- Sub-agente alucina referência (`arquivo:linha` que não confere)
  ou afirma "Protocol X bate" sem ter lido o arquivo inteiro.
- Tabela A/I/C com 30 itens marcados OK vira ✅ no relatório sem
  verificação amostral.

**Pergunta:** "o resumo cita 2-3 trechos verbatim, ou só veredito?"

**Tratamento:** quando delegar, exigir no prompt que o relatório
traga **2-3 trechos literais** das partes críticas (Protocol
assinaturas, mappers de boundary, §7 post-execution, validators de
invariante negativa). Ler à mão e conferir. Se não pediu verbatim,
re-prompt antes de fechar. Codificado em Fase D-bis #9.

### Lei universal, representante estreito

A lei — do concept, de um ADR ou da docstring do port — fala de um
**conjunto**: traz quantificador explícito (*"**nunca**"*, *"**todo**"*,
*"**qualquer**"*, *"em **todos** os caminhos"*) ou implícito por disjunção
(*"vazio **ou** ausente"*, *"uma vez **por alvo**"*). O teste que a trava fixa
**um** representante do domínio quantificado. A suíte fica verde, a cobertura de
linha **e de branch** fecha em 100%, e a lei está provada só para o
representante — o resto do conjunto está **descoberto com aparência de coberto**.

Não confundir com **Verificação assimétrica**: lá o assert prova o outro lado
(presença ≠ ausência) ou não prova nada (execução sem asserção). Aqui a asserção
é correta e real; o que está estreito é o **domínio** sobre o qual ela roda.
Coverage não vê a diferença — por isso este conceito precisa existir separado.

**Pergunta de caça:** *"a lei fala de um conjunto — o teste percorre o conjunto,
ou um representante dele?"*

**Sinal de alerta forte:** as **duas implementações de um mesmo port** (fake e
real/produção) cobradas por conjuntos de valores **diferentes**. Foi a assimetria
que denunciou o caso da 3.4: a mesma lei já era parametrizada sobre os dois
valores no lado do fake e sobre um só no tradutor de produção — e é a
implementação de **produção** que costuma ficar com o conjunto menor, porque a
suíte do fake nasce junto da lei e a de produção nasce junto do wiring.
Diff mental lei a lei: comparar os `parametrize` das duas suítes.

**Procedimento:**

1. Ler a lei e **enumerar o domínio de cada quantificador** — quais valores de
   tenant, quais permissões, quais alvos, quais caminhos de construção. O
   enunciado normalmente já traz a enumeração: a disjunção *"vazio ou ausente"*
   **é** o domínio escrito por extenso.
2. **Parametrizar sobre o domínio enumerado** (produto cartesiano quando há dois
   eixos), nas **duas** implementações do port — não só na que falhou.
3. Onde fixar um representante for deliberado, **mutar a guarda para
   condicioná-la a esse representante** e **exigir vermelho**: `if not x` →
   `if x is None`; `deny(...)` → `if permission != "<a permissão do teste>"`.
   Suíte verde depois da mutação ⇒ a lei **não** está travada — é achado, não
   estilo. Registrar a mutação e o número de testes que ela mata.
4. Não aceitar cobertura como substituto: nos três casos abaixo a cobertura de
   linha e de branch já era 100% **antes** da correção, e a mutação matava
   **zero** testes.

**As três instâncias da Stage 3.4** — a mesma falha em três eixos, todas achadas
**de fora** (Checkpoint C e auditoria de testes), nenhuma pela suíte:

| Lei | Quantificador | Representante fixado | Mutação que ficava verde | Correção |
|---|---|---|---|---|
| L-AG3 | *"tenant vazio **ou** ausente"* | só `None` na suíte do tradutor (o fake já cobria os dois) | `if not actor_tenant_id` → `if actor_tenant_id is None` | `5d69846` — `parametrize` `ausente`/`vazio` |
| L-AG2 / L-AG3 | *"`authorize` **nunca** devolve escopo sem tenant"* (sobre **todas** as permissões) | só `"manage_staff"` codificado | guarda condicionada a `permission != "manage_job_functions"` | `d0fafe0` — `_ALVOS` nas duas implementações; L-AG3 vira produto cartesiano 2 tenants × 2 permissões |
| L-AG4 | *"uma autorização **por alvo**"* | um só alvo (permissão + unidade) | mesma mutação por permissão | `d0fafe0` — eixos de alvo (tenant e permissão) acrescentados aos ramos de **recusa**, que eram onde a permissão tenant-wide nunca entrava |

---

---

### Falso vermelho ambiental

O **espelho** dos falsos verdes: gate vermelho local atribuído à branch
quando a causa é o ambiente (típico: `.venv` de worktree dessincronizado
— mypy/lint-imports falham em arquivo **intocado**). Custo invertido:
finding falso + investigação na branch errada.

- Sintoma: `make check` falha em arquivo que a branch não tocou; deps
  "sumidas" (`sqlalchemy`, `lint-imports`) num worktree criado antes de
  a base avançar.

**Pergunta:** "o arquivo do erro mudou nesta branch, e o CI da base está
verde?" (`git diff origin/<base> -- <arquivo>` vazio + CI verde ⇒
ambiente, não branch.)

**Tratamento:** `uv sync --extra dev` e re-rodar o gate; só então julgar.
Registrar como **observação**, nunca como finding da branch. Codificado na
checagem barata da Fase B.

---

### Casos históricos (rastreabilidade do loop recursivo)

Cada linha é um falso verde já observado, mapeado ao conceito que o
cobre. Cresce sem inflar a seção conceitual.

| Caso | Conceito | Onde aconteceu |
|---|---|---|
| L-AG3 travada só em `tenant_id=None`; a lei diz "vazio **ou** ausente" | Lei universal, representante estreito | Stage 3.4 / PR #42 — fix `5d69846` |
| L-AG2/L-AG3/L-AG4 travadas só em `"manage_staff"`; as leis valem para **toda** permissão e **todo** alvo | Lei universal, representante estreito | Stage 3.4 / PR #42 — fix `d0fafe0` |
| Fake e tradutor de produção do mesmo port cobrados por conjuntos de valores diferentes (a assimetria que denunciou as duas linhas acima) | Lei universal, representante estreito (sinal de alerta) | Stage 3.4 / PR #42 |
| Teste prova o comportamento no default do construtor enquanto a config de produção declara outro valor | Verificação assimétrica | classe importada do financial-forecasting (#65) |
| Valor novo de enum entra no emissor e no teste dele, mas fica fora das famílias que particionam o enum | Verificação assimétrica | classe importada do financial-forecasting (#65) |
| Regra no lugar errado com import legal (duplicada em fake e adapter, decisão de negócio no adapter, BC lendo interno de outro) | Estrutural ≠ semântico | classe importada do financial-forecasting (#65) |
| Critério A* exige teste numa perna onde o comportamento é **inatingível por construção** — pergunta-guia: "esta perna CONSEGUE exibir o comportamento?" | Literal ≠ espírito | classe importada do financial-forecasting (#65); errata em §7 em vez de retocar o concept |

Quando esta skill falhar (auditoria deu verde, reviewer/CI/produção
pegou algo): **primeiro perguntar qual conceito existente ficou cego**.
Se um conceito deixou o gap passar, **reformule esse conceito** para
cobrir a classe — a tabela de casos é **rastreabilidade, não o mecanismo
de crescimento**. Só adicione caso (ou conceito novo) quando o padrão é
genuinamente novo e **não** força refino de um conceito existente. A
skill deve ficar mais **afiada**, não mais **longa**.

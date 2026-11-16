# Referência da issue-audit — catálogo de falsos verdes

Catálogo citado pelo [SKILL.md](../SKILL.md), que aponta cada conceito pelo nome no
ponto de uso. "Fase B", "Fase D-bis #N" e "D-bis #N" neste arquivo são seções do
`SKILL.md`.

## Sumário

- [Escopo empurrado pra frente](#escopo-empurrado-pra-frente)
- [Verificação assimétrica](#verificação-assimétrica)
- [Evidência de árvore suja](#evidência-de-árvore-suja)
- [Definido mas não plugado (dead-config)](#definido-mas-não-plugado-dead-config)
- [Gate inerte ou míope](#gate-inerte-ou-míope)
- [Sintoma ≠ causa](#sintoma--causa)
- [Solução complexa onde cabia a simples (concern capturado)](#solução-complexa-onde-cabia-a-simples-concern-capturado)
- [Rastro perdido](#rastro-perdido)
- [Delegação cega](#delegação-cega)
- [Falso vermelho ambiental](#falso-vermelho-ambiental)
- [Casos históricos (rastreabilidade do loop recursivo)](#casos-históricos-rastreabilidade-do-loop-recursivo)

## Conceitos de falso verde (anti-checklist)

> Conceitos, não exemplos numerados: exemplo vira pattern-match (agente
> acha "limpo" porque nenhum caso bate exato). Quando aparecer falso
> verde novo, primeiro perguntar **qual conceito existente cobre**; só
> criar conceito novo se for padrão genuinamente novo.

### Escopo empurrado pra frente
Um refino que é **da própria issue** é parqueado como "melhoria futura"
porque a issue parece fechada (`done` no roadmap, muitos commits, etc.).
O status vira desculpa para não terminar o escopo.
- Sintoma: "isso fica pra um follow-up" sobre algo que mexeria nas
  **mesmas linhas** que a issue criou, ou que um critério literal exige.
- **Pergunta:** "este achado toca o mesmo entregável desta issue, ou é
  capacidade/módulo/dependência nova?" Mesmo entregável → é desta issue.
- **Tratamento:** classificar por escopo (Fase D-bis #1), não por
  status. Dentro → propor implementar na branch da issue. Separada →
  buscar backlog antes de abrir card (evita fragmentação). Não-issue →
  só observação.

### Verificação assimétrica
Confundir presença com ausência, ou execução com asserção; ou cobrir
*a peça* e assumir *a fiação*.
- ✅ marcado sem evidência citada; teste-sonda da função de registro
  tomado como prova do "handler **global**" (a fiação no boot fica sem
  teste); `assert <campo seguro> in dto` "provando" ausência do dado
  bruto.
- **Pergunta:** "este check prova o critério, ou só a contrapositiva /
  só a peça isolada?"
- **Tratamento:** para "global/qualquer/todos", exigir teste pela app
  real (`create_app()`/boot). Para invariante negativa, `Grep` ativo
  com **0 matches**. Para coverage alto, ler 2-3 asserts (D-bis #5).
- **Sub-caso — válvula sem contagem:** um detector cobra cada entrada de
  uma allowlist/anotação/exclusão **nos dois sentidos** (presente/ausente,
  viva/morta) e ainda assim pode ser silenciado pelo **crescimento do
  conjunto** — anotar dez caminhos como `[planejado]`, acrescentar um
  segundo `--ignore`. Pergunta: "qual asserção fixa o **conjunto**, não só
  cada entrada?" Sem ela, a válvula é allowlist sem não-crescimento.

### Evidência de árvore suja
Saída colada como prova do estado de **outra** árvore (a base, o "antes"),
mas produzida na working tree local — que tem arquivos *untracked* e o fix
já aplicado. Diferente de "Rastro perdido": aqui **há** registro, plausível
e específico — e **falso**, verificável em um comando.
- Ex.: "rodei o gate em `develop`, 3 arquivos falham" — mas um dos 3 é
  **adição pura desta branch** e nunca existiu na base; a falha real da base
  era outra, a montante.
- **Pergunta:** "esta saída foi reproduzida **a partir da base**, ou de uma
  árvore que já contém o trabalho?"
- **Tratamento:** para todo arquivo alegado como *pré-existente e quebrado*,
  `git log --diff-filter=A -- <path>` (ou `git cat-file -e <base>:<path>`) —
  se é adição pura, a evidência é falsa. Reproduzir a partir da base de
  verdade: `git archive <base> | tar -x -C <tmp>`.

### Definido mas não plugado (dead-config)
Módulo/handler/validator existe, tem coverage, mas **nenhum call-site
real** fora do teste — nunca entra no pipeline.
- Ex.: um helper criado mas nunca chamado no boot; validator com teste
  unitário verde mas nunca registrado no router.
- **Pergunta:** "qual linha de produção **chama** isto?"
- **Tratamento:** `Grep "<nome>"` no projeto excluindo o teste; exigir
  ≥ 1 call-site real. Zero = finding.

### Gate inerte ou míope
Config declara o gate mas nada invoca (**inerte**); ou invoca global e
mascara o granular (**míope**: média ≥ 90% com arquivo da issue em 70%).
- **Pergunta:** "qual comando real exercita este gate, e em que
  granularidade?"
- **Tratamento:** ler o target do Makefile/CI; rodar coverage focada
  nos arquivos da issue. Gate inerte = blocker (config que ninguém roda
  é decoração).

### Sintoma ≠ causa
O `## Escopo` entregue cobre um caso particular do `## Problema`, não a
causa. O critério passa para o exemplo testado, mas o problema real
reaparece por outra porta.
- **Pergunta:** "se eu trocar o input do exemplo por um vizinho, o
  problema volta?"
- **Tratamento:** reler `## Problema`, conferir que a solução é geral
  (ex.: catch-all para **qualquer** Exception, não só a do bug que
  originou a issue).

### Solução complexa onde cabia a simples (concern capturado)
O `## Escopo` cria caso especial/tipo/regra nova para tratar **local** um
sintoma cujo tratamento direto seria **geral ou a montante** — um concern
**compartilhado** (isolamento por tenant, fuso/corte do dia operacional,
calendário, identidade) resolvido dentro de um consumidor só. Na issue
avulsa isso escapa mais fácil que na Stage: não há `concept.md` — a
especificação inteira é o corpo da issue, e o card pequeno e coeso
*parece* bem escopado justamente por ser pequeno.
- Sintoma: **tipo/regra/nuance nova** + o **mesmo problema recorre** em
  outros consumidores do mesmo dado.
- **Pergunta:** "há solução mais direta/geral, ou esta issue está remendando
  local um concern compartilhado?"
- **Tratamento:** a geral é o conserto; a local vira **piso declarado +
  issue transversal** (buscar backlog antes de abrir), nunca solução
  silenciosa. Blocker se a captura corrompe a semântica para outros
  consumidores; senão non-blocker. Distinto de "Sintoma ≠ causa": lá a
  solução é estreita demais **para o próprio problema da issue**; aqui ela
  resolve o problema da issue e **erra a camada**.

### Rastro perdido
Decisão (off-task, silenciador, refactor, doc parcial) sem registro
onde o reviewer procuraria.
- `[#<num>/--]` sem justificativa no body; `# type: ignore`/`# noqa`
  em boundary sem 1 linha de motivo; roadmap table atualizado mas
  frontmatter esquecido (ou inverso); commit de outro escopo de carona
  na branch da issue.
- **Tratamento:** non-blocker em geral (corrigir antes do PR); blocker
  se carona de escopo (pedir rebase — GIT-WORKFLOW §Etapa 4) ou padrão
  repetido em ≥ 3 lugares.

### Delegação cega
Sub-agente devolve OK em batch e o auditor lê só o resumo.
- **Pergunta:** "o resumo cita 2-3 trechos verbatim, ou só veredito?"
- **Tratamento:** exigir verbatim das partes críticas; ler à mão;
  re-prompt se não pediu. (D-bis #9)

### Falso vermelho ambiental
O **espelho** dos falsos verdes: gate vermelho local atribuído à branch
quando a causa é o ambiente (típico: `.venv` de worktree dessincronizado
— mypy/lint-imports falham em arquivo **intocado**). Custo invertido:
finding falso + investigação na branch errada.
- **Pergunta:** "o arquivo do erro mudou nesta branch, e o CI da base está
  verde?" (`git diff origin/<base> -- <arquivo>` vazio + CI verde ⇒
  ambiente, não branch.)
- **Tratamento:** `uv sync --extra dev` e re-rodar o gate; só então julgar.
  Registrar como **observação**, nunca como finding da branch.

---

### Casos históricos (rastreabilidade do loop recursivo)

| Caso | Conceito | Onde aconteceu |
|---|---|---|
| `[planejado]` do LAYOUT §2 e `--ignore` do mutmut cobrados por entrada, nunca pelo conjunto | Verificação assimétrica (válvula sem contagem) | #45, PR #50 — F1/F2 |
| Rename `adapters/in → inbound` + import hygiene entregues fora do `## O quê` | Caça ao não-previsto → escopo ampliado na execução | #45, PR #50 — F6 |
| 629 `ERROR` em integration/e2e: container Postgres da worktree morreu **durante** o `test-gate` (`Exited (255)`) | Falso vermelho ambiental | #45, PR #50 — F11 |
| `only_mutate` com caminho morto após rename: mutmut filtra por `fnmatch` e **exclui o módulo em silêncio**, reportando "N/N" sobre 3 de 4 arquivos | Gate inerte ou míope | #45, PR #50 — `02ac4e5` |

Quando esta skill falhar (auditoria deu verde, reviewer/CI/produção
pegou algo): **primeiro perguntar qual conceito existente cobre**.
Adicionar caso novo na tabela. Só criar conceito novo se for padrão
genuinamente novo.

---
title: Technical — API do editor e consulta de escala
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, scheduling-http]
status: draft
created_at: 2026-11-23
updated_at: 2026-11-23
stage_id: 4.5-scheduling-http
stage_title: API do editor e consulta de escala
step_id: 4
step_title: Escala manual publicável
depends_on: [4.4-scheduling-persistence, 3.10-login-link-management]
concept_ref: ./concept.md
issue_id: 254
branch: feat/254-4-5-scheduling-http
tasks_count: 0
---

# Technical — Stage N.M — <Título da Stage>

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.** A
>    verificação da Task roda só os testes dela; o `make check` completo
>    roda só nos pontos do [plano de gates](#plano-de-gates).
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [N.M/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage N.M: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/<num-issue>-<N-M>-<slug>` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo
<1 parágrafo. O que vamos construir nesta Stage, em termos técnicos.>

### Estratégia
<Como vamos construir. Bottom-up? Top-down? Spike primeiro? Mock
dependências externas? Ordem das Tasks e razão.>

### Pré-condições
- <ex.: Stage `<stage_id>` em `done` e mergeada em develop>
- <ex.: migration X aplicada localmente>
- <ex.: variáveis de ambiente conforme `.env.example`>

### Premissas técnicas
- <ex.: Python 3.12+, pyproject já existe>
- <ex.: redis local rodando em porta 6379>

### Plano de gates

> Depois de quais Tasks o `make check` completo precisa estar verde.
> **Orçamento: 1 a 3 pontos por Stage, o de saída incluído.** Nas demais
> Tasks o comando de verificação roda só os testes da Task. Ponto no
> meio da Stage precisa de motivo concreto; do 4º ponto em diante, de
> justificativa por ponto. Regra completa (onde pôr um ponto, varreduras
> de totalidade, como o ponto é cumprido sob orquestração):
> [`PIPELINE.md`](../../PIPELINE.md) §9.6.

| # | Depois da Task | Motivo |
|---|---|---|
| 1 | <Task NN, ou "saída"> | <quebra que este ponto pega e por que esperar o próximo sairia caro; no de saída: "gate de saída (§3)"> |

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── <camada-alvo>/
│   └── <novos arquivos>
tests/
└── <pasta>/
    └── <novos arquivos>
```

## 2. Tasks

> Faixa saudável: **3–12 Tasks por Stage**. ≥ 14 = Stage provavelmente
> está grande demais; reabrir Fase 3A para dividir.

### Task 01 — <descrição curta>

- **Arquivos a criar:**
  - `src/restaurant_hub/<camada>/<arquivo>.py`
  - `tests/<pasta>/test_<arquivo>.py`
- **Arquivos a modificar:**
  - <caminho ou "nenhum">
- **O que fazer:**
  <Prosa direta descrevendo a mudança material. Sem código completo;
  apenas indicações como "criar Protocol com método `X(arg: A) -> B`".>
- **Detalhes técnicos:**
  - <interface esperada, comportamento esperado, exceções>
- **Critério de aceite:**
  - <ex.: testes em `tests/.../test_<arquivo>.py` cobrem happy path e erro>
- **Comando de verificação** (só os testes da Task: os que ela escreve
  ou altera, mais as varreduras de totalidade que os arquivos dela
  alimentam; `make check` apenas se a Task está no plano de gates):
  ```bash
  pytest tests/<pasta>/test_<arquivo>.py -q --no-cov
  ```
- **Commit sugerido:** `feat(<scope>): <description> [N.M/task-01]`

---

### Task 02 — <descrição curta>

- **Arquivos a criar:** <...>
- **Arquivos a modificar:** <...>
- **O que fazer:** <...>
- **Detalhes técnicos:** <...>
- **Critério de aceite:** <...>
- **Comando de verificação:**
  ```bash
  <comando>
  ```
- **Commit sugerido:** `<type>(<scope>): <description> [N.M/task-02]`

---

<Repetir Tasks.>

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage N.M: complete` e ser mergeada em `develop`.

### Verificações automatizadas
```bash
make check                # gate completo: o último ponto do plano de gates
<outros comandos específicos da Stage>
```

### Verificações funcionais
- [ ] <comportamento end-to-end que precisa funcionar — ex.: "rodar `python -m restaurant_hub.cli ingest sample.csv` produz N registros no banco">
- [ ] <outro>

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch, em cada ponto do plano de gates
- [ ] Commit final `stage N.M: complete` aplicado
- [ ] Branch mergeado em `develop`
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e
      `last_reviewed_at` no mesmo merge (ou em PR de docs imediato)
- [ ] ADRs novos (se houve) em `status: accepted`
- [ ] Runbooks operacionais criados se aplicável
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
      (se precisa, abrir TODO ou nova Stage de correção)

## 4. Ordem de dependência entre Tasks

<Texto ou lista mostrando quais Tasks dependem de quais. Por padrão a
ordem listada em §2 já respeita dependências; explicitar aqui só os
casos não óbvios.>

```
Task 01 ─► Task 02 ─► Task 04
              │
              └──► Task 03
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| <ex.: lib X não suporta caso Y> | <ex.: cair para lib Z, ADR registrando> |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md)
- [`../../roadmap.md`](../../roadmap.md)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs desta Stage: [`../../adr/`](../../adr/) (filtrar por prefixo `N_M_`)
- Skills aplicáveis: <ids de `skills/`>
- Docs externos: <links>

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4** — exceto as disposições dos
> Checkpoints A (gravada na Fase 3A, com este arquivo ainda esqueleto) e
> B (na Fase 3B), formato abaixo. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão (via `AskUserQuestion` ou equivalente).
> Apenas após a decisão, registre a entrada abaixo. Na dúvida sobre
> se algo é "pequeno o suficiente para decidir sozinho", **pergunte**.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
  Inclui pergunta, opções, decisão, razão.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original; corpo
  diz o que mudou e por que ficou abaixo do threshold de perguntar.
- `[measurement]` — evidência que o plano manda colar aqui (tempo do
  ponta a ponta, saída de mutação obrigatória, prova manual, execução
  real, auditoria de testes), sem decisão nem desvio. Corpo:
  **Contexto:** que critério/Task pede a evidência; **Medição:** comando,
  ambiente e saída bruta; **Razão:** o que a evidência prova.

Vocabulário fechado (CONVENTIONS §3.4): `decision` (ou `decision:E` /
`decision:C`, skill `evidence-resolution` §5), `finding`, `deviation`,
`measurement`. Outra tag no cabeçalho de entrada é recusada por
`scripts/check_technical_postexec.py`.

**Disposições dos Checkpoints** (CONVENTIONS §3.4): uma entrada
`[decision]` por checkpoint — e por bloco no C —, gravada no commit que
fecha o checkpoint (A → `conceptual approved`; B → `technical approved`;
C → o `-fix` do bloco ou o commit seguinte). Sem as do A e do B, technical
`done` é recusado pelo script.

```markdown
### YYYY-MM-DD — [decision] Checkpoint A — disposições — <Autor>
**Contexto:** rodada <n> de 3; revisores: <lentes>.
- **A1** (<severidade>, <lente>) <achado em 1 linha> → corrigido (<hash ou marca do commit>)
- **A2** (…) … → refutado — artefato: <trecho de teste, código ou saída, colado>
- **A3** (…) … → escalado (<pergunta P, HALT ou issue>)
```

Checkpoint sem achado grava a entrada mesmo assim ("nenhum achado material").
O cabeçalho do C é `Checkpoint C (bloco Tasks NN–MM)`.

### 2026-11-23 — [decision] Checkpoint A — disposições — Claude (Opus 5.5)
**Contexto:** rodada 1 com dois revisores de contexto zerado (conformidade; domínio/testabilidade) e
o `decision-reviewer` da `evidence-resolution` §4.3; rodada 2 de re-verificação das correções (um
revisor). Antes deles, dois `evidence-verifier` conferiram as citações dos sete registros
`[decision:E|C]` (D-ERR-409 e D-IDS voltaram `parcial` e foram corrigidos; os demais, `sustenta`).
Todas as correções entram no commit `stage 4.5: conceptual approved`.
- **A1** (major, ambos) CA1 exigia "versão 2"; a versão soma 1 por operação efetiva → corrigido (CA1: 1 + operações efetivas)
- **A2** (major, domínio) a matriz e2e não prova a autorização da rota (o use case nega igual) → corrigido (§5 inv. 4; CA14, teste de borda com espião)
- **A3** (major, ambos + decision-reviewer) quatro `Duplicate*` em 409 contra o ADR 3.4.0002 §4 → corrigido (422; faixas reescritas na §6, D-ERR-BANDS e ADR 4.5.0002)
- **A4** (major, domínio) o pino de R17 e a docstring da fachada quebram sem critério → corrigido (CA15, propriedade; divergência 1; nota no ADR 2.7.0001)
- **A5** (major, domínio) CA6 passava sem a mudança do calendário → corrigido (CA6 exige `true` e `false` em S2 e S5)
- **A6** (major, domínio + decision-reviewer) `MissingStaffRecordsError` sem saída para o cliente e vindo também das leituras → corrigido (§6, risco na §10, consequência no ADR 4.5.0002; #194 pré-requisito de produção)
- **A7** (major, domínio) CA2 sem `platform_admin` → corrigido
- **A8** (major, domínio) CA3 vácuo → corrigido (alocado no recorte, desligado, novo login)
- **A9** (major, conformidade) D-DEACT sem errata do ADR 3.5.0003 §5 → corrigido (nota datada no ADR; issue #259)
- **A10** (major, conformidade + decision-reviewer) protocolo da borda declarado no adapter de entrada, contra LAYOUT §5 e o precedente de staff → corrigido (o port de scheduling ganha `authenticate` e tenant opcional, lei L-SG5; D-GUARD, ADR 4.5.0003; divergência 2)
- **A11** (major, decision-reviewer) D-CREATE quebra o princípio da matriz congelada e o comentário de `role.py` → corrigido (consequência declarada em D-CREATE e no ADR 4.5.0001; comentário de `role.py` reescrito na Task de identity; destaque no PR)
- **A12** (major, decision-reviewer) D-CONFIG: tenant-wide é inócuo só para o dono, alargar não é aditivo, a 4.8 muda o port → corrigido (D-CONFIG e ADR 4.5.0001 reescritos; consequência para a 4.8 declarada)
- **A13** (major, decision-reviewer) D-OWN: o funcionário não descobre a própria unidade → corrigido (limite declarado; #258 pré-requisito do piloto com funcionários; risco na §10)
- **A14** (minor, domínio) CA5 "o lote reenviado passa" não é propriedade → corrigido (§6 e CA5: reenvio pode voltar 422; asserção sobre o corpo do 409)
- **A15** (minor, domínio) tipo do decimal do aceite ambíguo → corrigido (`str` + conversor da borda)
- **A16** (minor, domínio) partes do CA7 intestáveis → corrigido (path só-espaço/NUL; corpo; as duas operações de quantidade)
- **A17** (minor, domínio) forma da `key` do aceite subespecificada → corrigido (eco exato, campos anuláveis)
- **A18** (minor, domínio) regra de faixas incoerente (404 × 422 para referência no corpo) → corrigido (outro agregado = 404; valor interno = 422)
- **A19** (minor, ambos) CA13 não objetivo e marca do §4 ("e-mail como efeito") sem destino → corrigido (CA13 lista linhas e marcas; D-EMAIL)
- **A20** (minor, conformidade) `view_own_schedule` para `hr`/`manager`/`owner` sem nota nos ADRs 3.4.0006 e 4.1.0004 → corrigido (notas datadas)
- **A21** (minor, conformidade) premissa (b) de D-OWNALL parcialmente falsa → corrigido (reescrita: rotas de identity × R17 pela fachada)
- **A22** (minor, conformidade) regra de corpo "nenhum registro que o pedido não nomeou" larga demais → corrigido ("nenhum registro invisível")
- **A23** (minor, conformidade) dia extremo produz 500 → corrigido (§6 e CA7; na rodada 2, estendido aos limites de faixa, que estouram em `operational_day_of`)
- **A24** (minor, conformidade) corpo de S1 não especificado → corrigido (§4.2)
- **A25** (minor, decision-reviewer) teto de 500 do lote sem medição → corrigido (declarado como premissa não medida em D-BATCH; reversível)
- **A26** (contrato, rodada 2) a extensão do port contradiz o ADR 4.3.0002 §Decision 1 sem nota → corrigido (nota datada no ADR 4.3.0002; docstring do port reescrita na Task que o estende)
- **A27** (minor, rodada 2) marcas do corpo do doc de domínio que citam a 4.5 faltavam no CA13 (§3.5, §3.9, §3.10.2, nota de §6) → corrigido

<!-- END: post-execution -->
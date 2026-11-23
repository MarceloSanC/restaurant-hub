---
title: Technical — Gestão do vínculo de login do registro
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, login-link-management]
status: draft
created_at: 2026-11-22
updated_at: 2026-11-22
stage_id: 3.10-login-link-management
stage_title: Gestão do vínculo de login do registro
step_id: 3
step_title: Equipe da unidade
depends_on: [3.8-termination-access-scope, 2.7-identity-application-authorization]
concept_ref: ./concept.md
issue_id: 218
branch: feat/218-3-10-login-link-management
tasks_count: 0
---

# Technical — Stage 3.10 — Gestão do vínculo de login do registro

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
> `feat/218-3-10-login-link-management` (ver `CONVENTIONS.md` §4). Não há
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

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
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
### 2026-11-22 — [tag] escopo — Autor
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

### 2026-11-22 — [tag] <Task NN ou escopo> — <Autor>
<!-- preencher quando aplicável; remover este placeholder se vazio -->

<!-- END: post-execution -->
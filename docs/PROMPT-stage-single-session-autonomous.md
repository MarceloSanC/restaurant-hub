---
title: Prompt — Execução de Stage em Sessão Única (variante AUTÔNOMA overnight)
description: Override do PROMPT-stage-single-session para corrida autônoma overnight, onde o agente fecha e mergeia a Stage sem gate humano, com auditoria de contexto-limpo (stage-audit + label audit-gate) no lugar da aprovação
when-use: Apenas em corrida autônoma overnight autorizada pelo ADR 0.0.0004 (status accepted + recorte de stages registrado no ADR). Fora de corrida autorizada, usar o prompt canônico.
keywords: [prompt, stage, autonomous, overnight, auto-merge, adr-0004, audit-gate]
status: done
created_at: 2026-07-12
updated_at: 2026-07-16
---

# Prompt — Execução de Stage em Sessão Única (variante AUTÔNOMA)

Esta é uma **camada de override** sobre [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md).
Tudo no prompt canônico continua valendo **exceto** o que esta página redefine.
Autorizada e governada pelo [ADR 0.0.0004](./adr/0_0_0004-autonomous-overnight-mode.md).

> **Pré-condição absoluta:** o ADR 0.0.0004 está `accepted` **e** a Stage-alvo está dentro do
> recorte registrado na seção "Authorized runs" do ADR. Se qualquer uma falhar, **PARE** —
> esta variante não se aplica; volte ao prompt canônico.

> `status: done` desde a autorização da primeira corrida (2026-07-16, recorte `1.2`→`3.5`).

> **Pausa por Step, quando a autorização a impuser.** A entrada em "Authorized runs" pode
> condicionar a corrida a **parar na fronteira de cada Step** (é o caso do recorte
> `1.2`→`3.5`: pausa após a `2.5` e após a `3.5`). Onde houver pausa, a Stage seguinte
> **não começa** — feche a corrida com o resumo do Step e aguarde o humano. Dentro do Step,
> as Stages encadeiam sem pausa, como esta variante descreve.

---

## O que MUDA em relação ao prompt canônico

### 1. Protocolo de pergunta → decisão autônoma

O prompt canônico manda **PARAR e perguntar** (`AskUserQuestion`) em várias lacunas —
bifurcações materiais da Fase 3A, escopo estrito violado, regressão mid-stage, achados
`escalado` dos Checkpoints, além da **pausa opcional de gate humano** antes da Fase 4 e do
"apresentar diff ao humano antes do commit" da Fase 4. Nesta variante, **a fase de perguntas
já aconteceu** (rodada inicial, antes da corrida). A partir daqui, **NÃO pergunte** — a pausa
opcional não existe e o commit não espera revisão de diff. Em vez disso:

- **Lacuna/decisão reversível ou barata** → decida você mesmo seguindo a política de decisão
  autônoma (ADR 0.0.0004, Decision #4): (a) liste explicitamente as opções,
  (b) pesquise os trade-offs de cada uma com **referência concreta** — nunca afirme sem base,
  (c) avalie o **ganho real** vs o **custo real** de implementação (não superestime o custo),
  (d) prefira a solução **mais simples** que já entrega boa parte do desejado, não prejudica o
  crescimento do sistema e é **fácil de trocar** depois. Registre a decisão não-trivial num
  **ADR** (`docs/adr/<N>_<M>_NNNN-<slug>.md`, `templates/adr.md`, `status: accepted`,
  frontmatter completo com `bounded_context` — CONVENTIONS §2) com opções, trade-offs e
  reversibilidade. Decisão trivial segue como no canônico: `[decision]` na §7.
- **HALT-and-park** (pare a Stage e, como a cadeia é dependente, a corrida) **apenas** em:
  - contradição com fonte de hierarquia superior (Overview > Roadmap > Concept > Technical),
  - contrato externo **irreversível** e ambíguo (formato persistido, contrato público de API,
    schema de migration),
  - gate objetivo que **não fecha** depois de tentativa honesta de correção,
  - merge tecnicamente bloqueado (branch protection exigindo aprovação) — não burlar.
  Ao dar HALT: deixe a working tree estável, escreva o motivo em `§7` do technical e num
  resumo claro, e **não** force progresso.

Regra de ouro: ADR resolve **escolha de design**; HALT resolve **contradição/irreversível**.
Nunca use ADR para enterrar uma contradição que deveria parar a corrida.

Os achados de Checkpoint que o canônico manda escalar via `AskUserQuestion` seguem o mesmo
mapa: reversível/barato → decisão autônoma (com ADR se não-trivial); contradição ou
irreversível ambíguo → HALT. A regra do artefato colado para `refutado` continua intacta.

### 2. Serviços externos e efeitos colaterais

- **Nada sai da máquina** durante a corrida além de operações git/GitHub (`push`, `gh`).
- Adapters de e-mail e integrações de terceiros rodam contra **fakes/captura local** —
  nunca enviar e-mail real nem chamar API externa ao vivo unattended (evita rate-limit,
  rede e efeito colateral irreversível travarem ou sujarem a corrida).
- Testes de integração usam os serviços do **docker-compose local** (postgres); o que
  depender de serviço externo real roda contra fakes/fixtures.

### 3. Fechamento, PR e merge — o merge AGORA É VOCÊ QUEM FAZ

O canônico já manda você fazer o commit final `stage <N.M>: complete`, atualizar o
`roadmap.md` e **abrir o PR** — tudo isso continua igual, incluindo a regra de rebase da
Etapa 4 do GIT-WORKFLOW e o checklist honesto (só marcar o que você validou). O que esta
seção **substitui** é o "Você NÃO faz merge" da §REGRA DE PR.

Depois de **todos** os gates de saída verdes (idênticos ao canônico, com evidência colada)
e do **PR aberto** com o label de auditoria em `review` preservado:

1. **Auditoria de contexto-limpo ANTES do merge** (substitui a aprovação humana): a Stage é
   auditada por uma sessão/subagente de **contexto fresco** rodando a skill `stage-audit` —
   que recebe só os caminhos dos artefatos, nunca o seu histórico nem o seu raciocínio.
   Se a auditoria apontar **blocker**, corrija e re-audite; só prossiga com auditoria sem
   blocker. É a **sessão de auditoria** (não você) quem completa o checklist do PR e grava
   o label `> **Auditoria:** complete` + comentário de veredito (CONVENTIONS §3.6). **Nunca**
   grave `complete` você mesmo.

   **Cap de 2 re-auditorias.** Blocker que sobrevive à **3ª** rodada → **HALT**, não 4ª
   tentativa. Sem cap, esta é a única etapa do fluxo com re-rolagem infinita — e é justamente
   a que substitui o humano, então re-rolar até passar é *audit-shopping*: você acaba
   selecionando o auditor que não viu o problema. (Os Checkpoints A/B/C já têm cap de 3 no
   canônico, preservado na §"O que NÃO muda".)

   > **O `audit-gate` do CI NÃO bloqueia o merge** — repo privado em GitHub Free não permite
   > branch protection, então nenhum check é *Required*: um PR com check vermelho fica
   > `UNSTABLE`, não `BLOCKED`, e `gh pr merge` passa assim mesmo (ADR 0.0.0004 §Context;
   > GIT-WORKFLOW §Gates de PR). O label `complete` **sinaliza**, não trava. Quem impede o
   > merge de uma Stage não auditada é **você** — não conte com a plataforma para isso.
2. Esperar CI verde (`gh pr checks <num> --watch`). Check vermelho → corrigir e re-passar
   pelo passo 1 se a correção tocar código/docs auditados.
3. Mergear com **merge commit** (NUNCA squash/rebase — GIT-WORKFLOW §Gates):
   ```bash
   gh pr merge <num> --merge --delete-branch
   ```
   Se o merge for recusado por branch protection (aprovação obrigatória), **HALT** — não
   burlar nem se auto-aprovar.
4. Cleanup e sync para a próxima Stage:
   ```bash
   git checkout develop && git pull origin develop && git remote prune origin
   ```
5. **Nunca** force-push em `develop`/`main`; **nunca** reescrever história já mergeada.

> O que torna o auto-merge seguro é a **auditoria imparcial** (passo 1) somada aos **gates
> objetivos** — que falham de verdade, com exit ≠ 0. O `audit-gate` **não** é a terceira perna:
> ele apenas **sinaliza** (não trava — ver acima). Pular qualquer um dos dois quebra a
> justificativa do ADR 0.0.0004, e **ninguém além de você** vai perceber.

### 4. Pré-condição de dependência endurecida

Onde o canônico verifica `depends_on` com `status: done` no `roadmap.md`, esta variante
exige **mergeado em `develop`** (a cadeia avança por merge, não por status):

```powershell
git fetch origin
# para cada dependência, o commit "stage <dep>: complete" deve estar em origin/develop
git log origin/develop --oneline | Select-String "stage <dep>: complete"
```

O padrão inclui `: complete` de propósito: `Select-String "stage <dep>"` casaria também
`conceptual approved`/`technical approved` (ou qualquer commit parcial da Stage que tenha
chegado a `develop` por PR parcial), dando verde para dependência que **não fechou**.

`done` no roadmap sem merge = pré-condição falhou → HALT (a Stage anterior não fechou de
verdade).

---

## O que NÃO muda (continua valendo do prompt canônico)

- Carregar contexto antes de agir; invocar `git-versioning-pointer` antes de operação git.
- Pré-condições bloqueantes (working tree limpo, branch correta, issue OPEN, estrutura da
  Stage) — com o `depends_on` endurecido da §4 acima.
- Fases 3A (Concept) e 3B (Technical), critérios de Task Atômica, 3–12 Tasks (≥ 14 = HALT,
  não ADR).
- Escopo estrito por Task (a resolução da violação muda — §1 — mas a detecção não);
  §7 post-execution (`[decision]`/`[finding]`/`[deviation]`); arquivo de estado no scratchpad.
- **Checkpoints A/B/C** (revisores independentes de contexto zerado, prompt adversarial,
  cap de 3 rodadas, disposição explícita de todo achado) e **Auditoria de Testes por
  subagente independente** (loop até todos "sim", com mutação real nas funções críticas) —
  gates explícitos, não pular.
- **Gates de saída com regra de evidência**: saída literal colada ou o gate não conta —
  `make check`, coverage ≥ 90% por arquivo tocado, `check_technical_postexec.py`,
  verificação end-to-end, roadmap atualizado, ADRs `accepted`.
- Relatório final no formato do canônico (o merge entra como item extra da seção de PR).
- Hierarquia de contradições e o dever de não silenciá-las.

---

## Related

- Base canônica: [`./PROMPT-stage-single-session.md`](./PROMPT-stage-single-session.md)
- Governança: [`./adr/0_0_0004-autonomous-overnight-mode.md`](./adr/0_0_0004-autonomous-overnight-mode.md)
- Label de auditoria / gate de CI: [`./CONVENTIONS.md`](./CONVENTIONS.md) §3.6 + [`.github/workflows/audit-gate.yml`](../.github/workflows/audit-gate.yml)
- Auditoria: `.claude/skills/stage-audit/SKILL.md`
- Git: [`./GIT-WORKFLOW.md`](./GIT-WORKFLOW.md)

---
name: evidence-resolution
description: "Triagem e resolução autônoma de forks de decisão por evidência verificada — invocar ANTES de perguntar qualquer coisa ao humano (AskUserQuestion, lista de opções com (Recomendada), \"a ratificar\") e sempre que um fork de concept/technical/doc de domínio/ADR/finding depender de legislação (CLT, LGPD), segurança (OWASP, RFC), comportamento de biblioteca (FastAPI, SQLAlchemy, Pydantic, PyJWT, argon2) ou convenção de método. Triggers (PT/EN) — \"fork\", \"bifurcação\", \"a ratificar\", \"qual convenção\", \"o que a lei diz\", \"o que a doc da lib diz\", \"sem fonte primária\", \"which convention\", \"is this secure\". O agente fecha E (evidência decide) e C (convenção sem vencedor) sozinho; só P (preferência de produto/negócio) chega ao humano. O hook `triage_gate` recusa AskUserQuestion sem header `P:`."
metadata:
  status: draft
  applies_when:
    camada_alvo: [any]
---

# Evidence Resolution

Perguntas de **informação** se resolvem com evidência; só perguntas de **preferência** são do
decisor (a "base de decisão" de Howard 1988 separa alternativas, informação e preferências).
O que a CLT manda, o que o OWASP recomenda ou o que o SQLAlchemy faz na versão travada no
`uv.lock` tem resposta verificável — devolver isso ao humano é custo sem ganho. Já regra de
negócio do restaurante, escopo e prioridade são dele.

## 1. Triagem — uma linha por pergunta, antes de qualquer outra coisa

| Classe | Quem fecha | Sinais |
|---|---|---|
| **P** preferência | humano | regra de negócio ou de produto (quem pode o quê no RBAC, o que o gerente/funcionário vê, texto e fluxo percebidos pelo piloto); muda escopo, "fora do escopo" ou premissa do [`overview.md`](../../../docs/overview.md) §3–§4; prioridade, prazo, custo de infra/hospedagem; default de validação configurável quando a lei dá uma faixa e escolher o ponto é apetite do negócio (bloquear × avisar); ação externa irreversível (merge em `main`, e-mail real, gastar dinheiro, publicar) |
| **E** evidência decide | agente | existe resposta verificável: texto de lei (Planalto), requisito de segurança (OWASP ASVS/Cheat Sheet, RFC), semântica HTTP (RFC 9110), comportamento documentado ou no código da lib na versão pinada, propriedade de algoritmo |
| **C** convenção | agente | ≥2 opções defensáveis e a evidência não elege vencedora (nome de campo de API, forma de paginação, formato de erro, organização interna) |

Mudanças de classe (são as únicas):
- **E/C vira P** se a evidência verificada for conflitante **e** as opções mudarem uma regra do
  doc de domínio (`docs/domain/**`) ou um critério de aceite já ratificado — sobe com o dossiê
  (§5), não como pergunta aberta.
- **C vira P** quando a escolha fica **visível ao usuário do piloto** (texto de tela/e-mail,
  passo a mais no fluxo, default que ele percebe). Convenção interna continua C.
- Irreversível/caro (port, schema persistido, contrato OpenAPI consumido pelo frontend) **não** é
  P por si: exige §4.2 e §4.3.

## 2. Evidência — interna primeiro, externa só para lacunas

1. **Análise interna (você, sem web).** Leia o doc de domínio, os ADRs, o concept/technical e o
   código envolvidos procurando o que eles já decidem ou contradizem: ADR que já fechou a questão,
   regra de domínio que invalida a proposta, fato do código que a torna inócua. No eval de origem
   (financial-forecasting#96) foi daí que saíram os achados mais baratos.
2. **Pesquisa externa só para o que faltar.** Fonte já citada no projeto com localizador
   (`overview.md` §10, `## References` dos ADRs, §7 do doc de domínio) não se repesquisa — vai
   direto ao §4.2 conferir o trecho. As lacunas vão num lote a **um** `evidence-researcher` (o
   protocolo de fontes é o system prompt dele; não colar brief) com só: perguntas, opções,
   caminhos do projeto e a lista do que já está citado. **Sem** sua inclinação (viés de
   confirmação). Lote > ~6 perguntas → dividir por tema, em paralelo.
3. Fato sobre o **nosso sistema** (o que a API devolve hoje, quantas linhas uma consulta toca, o
   que o Postgres faz com a constraint) é medição, não bibliografia: rode o teste, a consulta ou o
   endpoint e cite a saída.

## 3. Decisão

- **E:** a opção que a evidência verificada sustenta.
- **C:** o **primeiro degrau que discrimina**:
  1. já ratificado no projeto (overview, ADR, doc de domínio, skill) — coerência entre Stages;
  2. fork que toca autenticação, isolamento de tenant ou dado pessoal → a opção **fail-closed**
     (nega por padrão; ADR 2.2.0002) e de menor exposição (LGPD, overview §6);
  3. a convenção oficial da stack — doc/default da lib na versão do `uv.lock`, RFC, PEP;
  4. a mais reversível, que não fecha evolução (overview §6 "sem restringir evolução futura":
     esqueleto modular com implementação mínima, não o atalho que exige refazer a forma depois);
  5. a mais simples.
- Alternativa que plausivelmente muda o comportamento em outro cenário (outro restaurante, outra
  convenção coletiva, escala maior) → registrar como **configuração ou estratégia plugável
  candidata** no ADR (overview §7), não implementar agora.
  Alternativa que não muda nada → só "Alternativas descartadas" no ADR.

## 4. Verificação — antes de gravar

1. **Toda citação load-bearing tem fonte bruta conferida:** lei no texto consolidado do Planalto
   (artigo/parágrafo/inciso e a redação vigente, não a de MP caducada), RFC/ASVS pelo número da
   seção, lib pelo `arquivo:linha` do código na tag da versão pinada (`gh api`/`curl` do raw, não
   o resumo do WebFetch). Uma chamada por comando, sem laço/`cd`/`&&`. Citação que não se confirma
   sai, nunca fica.
2. Decisão que entra num **port**, num **schema persistido**, no **contrato OpenAPI** ou numa
   **regra de segurança/tenant**: despachar um `evidence-verifier` por lote de até 6 itens (mais
   itens → verificadores em paralelo) com só `{afirmação, trecho literal, localizador, fonte}`
   por item; ele lê a fonte bruta e responde `sustenta | parcial | não sustenta`. Verificação por perguntas independentes da resposta
   original reduz alucinação (Chain-of-Verification, Dhuliawala et al. 2024). "Não sustenta" →
   volta ao §3 sem aquela evidência. "Fonte inacessível" (PDF escaneado, paywall) não sustenta
   decisão **E**: troque a fonte ou decida como **C** pela escada, sem ela. "Não conferido"
   (teto de turnos) volta num lote novo.
3. **Completude** (decisões do item 2): despachar um `decision-reviewer` com os registros
   `[decision]` e os caminhos do doc/código; ele responde só "o que isto ignora ou contradiz no
   projeto?". Verificar citação não pega omissão — no eval de origem, a decisão citada com rigor
   deixou passar um caso que o próprio doc do projeto descrevia.
4. `[SEM-FONTE-PRIMÁRIA]` é aceitável só em **C**, declarando o degrau que decidiu; em **E** é
   lacuna → reclassificar como C (se houver opções defensáveis) ou HALT de sourcing
   (PROMPT-step §1: regra load-bearing sem fonte primária).

## 5. Registro — decisão sai decidida

Nada de "a ratificar". Gravar onde o processo já registra (ADR §Alternativas, §7 do technical,
doc de domínio) neste formato — é por ele que o humano audita, sem ser interrompido:

```
[decision:E|C] <id> — <pergunta em 1 linha>
Escolha: <opção> · Alternativas: <…> · Degrau (C): <1–5>
Base: <fonte, localizador> "<trecho ≤2 frases>" · <pkg@versão arquivo:linha: default=…>
Verificado: sustenta | parcial→corrigido | não verificado (§4.2)
Configuração candidata: <alternativa> | nenhuma · Reversível: sim | não (motivo)
```

## 6. Pergunta ao humano — só P

- Resolver antes todos os E/C do mesmo lote; a pergunta P chega com eles como contexto decidido.
- `AskUserQuestion`: todo `header` começa com `P:` e cabe em 12 caracteres (ex.: `P:Escopo`,
  `P:RBAC`). Fork listado em texto no fim do turno leva `[P]` na linha. O hook
  `.claude/hooks/triage_gate.py` bloqueia o que vier sem marca.
- Formato da pergunta: PROMPT-step §2 "Anatomia da pergunta ao humano". Havendo resultado
  executável, a pergunta vem ancorada nele (bloco "Valide você" do relatório): saída bruta +
  passos para reproduzir + o que cada opção muda no resultado.

## Gotchas

- **Pesquisar não basta.** No projeto de origem (#78, set/2026) o agente citou a fonte com rigor e
  ainda assim devolveu 11 convenções para ratificação humana: sem regra de quem decide, pesquisa
  boa não reduz perguntas. Classifique pelos sinais da tabela do §1, não por semelhança com casos
  anteriores.
- **Aqui, a maioria dos forks é P — e está certo.** Das 13 bifurcações do kickoff de
  identity/staff (jul/2026), 11 eram regra de produto (papel, visibilidade, quem cria o tenant) e
  só a sessão revogável e a janela de revogação eram convenção de segurança. A skill não existe
  para zerar perguntas; existe para que só as de produto cheguem.
- **Resumo ≠ fonte.** O WebFetch é resumido por modelo auxiliar e já afirmou o contrário do texto
  bruto. Fato load-bearing → ler a fonte bruta (texto do Planalto, `.md`/`.txt` da RFC, código da
  lib na versão pinada).
- **CLT não é comportamento fixo** (overview §6): a lei sustenta o **default** e os limites de
  uma validação configurável — E decide o que a lei diz; P decide se o restaurante bloqueia ou só
  avisa.

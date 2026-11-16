# Referência da issue-audit — template do relatório (Fase E)

Esqueleto que a Fase E do [SKILL.md](../SKILL.md) manda copiar e preencher. As regras
transversais (linguagem clara, lente de valor + design, listas nas seções 1-4, fato e
não impressão) e a regra de classificação dos findings ficam no `SKILL.md`.

```markdown
## Auditoria — Issue #<num> (<título curto>)   [ou: Issues #<a>, #<b>, ...]

### Status global: ✅ APROVADA SEM BLOQUEANTES | ⚠️ APROVADA COM FINDINGS | ❌ BLOQUEADA
Estado: GitHub <OPEN/CLOSED> · roadmap <open/done> · branch <mergeada?/em PR #N>

### 1. Conceitos principais
<breve descrição dos conceitos que a issue define/usa (do `## Escopo` e
`## Problema`). O que cada conceito existe para resolver. Jargão glosado
entre (). 2-5 bullets.>

### 2. Tasks → arquivos → o que entrega (lista, não tabela)
- **task-NN — <nome>**: mexeu em [arquivo](caminho), [arquivo](caminho)
  — entrega de fato: <o que passou a existir/funcionar, em linguagem clara>.
- ...

### 3. Gates de saída — o que a issue garante 100% que existe e funciona
Gate: <comando> → <resultado numérico>   (ex.: `make check` → 1779 passed, 98% cov)

| Critério de aceitação (corpo da issue) | Status | Evidência (arquivo:linha / comando→resultado / teste) |
|---|---|---|
| <texto do checkbox> | ✅/⚠️/❌ | <prova concreta> |

### 4. Decisões que impactam arquitetura / conceito / projeto
- <decisão> — impacto: <…>; valor de design vs dívida: <…>.

### 5. Findings / melhorias (classificados POR ESCOPO)
**F<N> — <título>** (blocker | non-blocker | observação)
- Contexto: <fato> · Onde: <arquivo:linha> · Por que importa: <consequência>
- Escopo: **dentro da #<num>** | **issue separada** | **não-issue**
- Recomendação: <proposta — não execute, proponha>

### 6. Aprendizados → skills
<algum padrão novo (falso verde, decisão recorrente, jargão mal
explicado) que vale virar/atualizar conceito numa skill? Qual skill e
qual conceito. Se nada novo: dizer "nada novo" explicitamente.

Antes de propor a atualização, responda os 4 filtros — proposta que
reprova em qualquer um NÃO entra:
1. **Classe ou caso?** O aprendizado descreve uma CLASSE que recorre
   (conceito) ou só este episódio (história)? História não entra —
   skill fica afiada, não longa.
2. **Canal de consumo real:** quem vai LER isto e quando? Regra
   acionável de skill em `skills_hint` vira pergunta adversarial
   obrigatória no Checkpoint C (consumo mecânico); texto que só o
   autor leria é advisory — se o único canal é advisory, avalie se o
   ganho justifica.
3. **O viés generaliza?** Toda regra enviesa a atenção do revisor —
   esse é o propósito. Formulada como conceito, o viés cobre a classe;
   formulada como caso, faz o revisor caçar UM bug específico e cega
   para o resto.
4. **Já mora em outro mecanismo?** Se o conceito já vive no
   questionário de auditoria, num script de gate ou noutra skill,
   duplicar alonga sem afiar — aponte o mecanismo existente em vez de
   copiar.>

### Conclusão
<2-4 linhas: que valor a issue entregou, quão bem modularizada
(escalável/responsabilidade), pronta pra PR/merge? o que falta? o que é
da issue vs futuro?>
```

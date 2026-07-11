<!--
Título: siga o mesmo padrão da issue.
  PR de Stage:  feat: stage N.M — <título humano>
  PR de fix:    fix(<scope>): <descrição>
Ver docs/CONVENTIONS.md §4 e docs/GIT-WORKFLOW.md.
-->

Closes #<num-issue>

> **Auditoria:** `review`
>
> Label de status do gate `audit-gate` (CI) — CONVENTIONS §3.6. `review` =
> aguardando auditoria (**merge bloqueado**); `complete` = auditada
> (**liberado**). A sessão de auditoria (`stage-audit` para Stage,
> `issue-audit` para issue avulsa) grava `complete` ao validar — **não edite
> à mão**.

## Resumo

<!-- 1–2 frases sobre o que mudou e por quê. -->

## Tipo

- [ ] Stage do pipeline (N.M)
- [ ] Fix (bug)
- [ ] Refactor
- [ ] Docs
- [ ] Chore

## Checklist (Stage)

<!-- Marque os itens aplicáveis. Para não-Stage, ignore os irrelevantes. -->

- [ ] Todas as Tasks do `technical.md` implementadas (1 Task = 1 commit)
- [ ] `make check` verde localmente (lint + typecheck + layout-check + test)
- [ ] Coverage ≥ 90% no código novo (via `pyproject.toml [tool.coverage.report]`)
- [ ] `roadmap.md` sincronizado **neste PR**: Stage marcada `done` (`todo→done`) — ou, em PR de issue avulsa, o item `open→closed` — + `updated_at`/`last_reviewed_at` no frontmatter (para o roadmap não defasar do GitHub ao mergear)
- [ ] ADRs novos (se houve) em `status: accepted`
- [ ] Runbooks operacionais criados se aplicável
- [ ] `concept.md` não precisa de retoque retrospectivo

## Como testar

```bash
make check
```

<!-- Se houver passos extras (migrations, fixtures), liste aqui. -->

# Referência da stage-audit — mapa rápido

Tabela de consulta citada pelo [SKILL.md](../SKILL.md): onde mora cada critério que
a auditoria cruza.

## Mapa rápido (onde está cada critério)

| Procura por... | Está em |
|---|---|
| Critérios de aceitação da Stage (A1..AN) | `concept.md` §11 |
| Invariantes (I1..IN) | `concept.md` §5 |
| Casos de erro/exceção (C1..CN) | `concept.md` §6 |
| Decisões técnicas (D1..DN) | `concept.md` §7 |
| Questões em aberto (Q1..QN) | `concept.md` §13 |
| Gate de saída + mapping invariante↔teste | `technical.md` §3 |
| Tasks executadas | `technical.md` §2 |
| §7 post-execution (`[decision]`/`[finding]`/`[deviation]`/`[measurement]`) | `technical.md` §7 |
| Regras de import / layers | `docs/LAYOUT.md` §3 + `hex-arch-python` skill |
| Atomicidade da Stage | `docs/PIPELINE.md` §4.2 / §4.3 |
| Gates de PR (CI verde, ≥90%, aprovação) | `docs/GIT-WORKFLOW.md` §Gates de PR |
| Convenção de commit/branch/PR | `docs/CONVENTIONS.md` §4 + `git-versioning-pointer` skill |
| §7 post-exec — formato e regra | `docs/CONVENTIONS.md` §3.4 |
| Status de Stage (`draft`/`approved`/`done`) | `docs/CONVENTIONS.md` §3 |
| `arquivos_a_criar` declarados | `docs/roadmap.md` §"Stage N.M" (bloco YAML) |
| Validador estrutural | `scripts/check_layout.py` |
| Validador §7 post-exec | `scripts/check_technical_postexec.py` |
| Validador "Stage exige issue" | `scripts/check_stage_issue.py` |

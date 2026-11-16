---
title: ADR 0.0.0022 — The clean-context audit session closes the PR it validated, in any flow, and a Step boundary does not wait for the human
description: Architecture Decision Record
when-use: Reference before merging an audited PR without human approval, before changing Phase F of stage-audit/issue-audit or who merges an audited PR, or when asking whether the end of a Step still waits for the human
keywords: [adr, process, audit, auto-merge, stage-audit, issue-audit, audit-gate, step, pause, git]
status: accepted
created_at: 2026-11-16
updated_at: 2026-11-16
adr_id: "0.0.0022"
decision: For a PR against develop of a stage or a standalone issue, the clean-context audit (stage-audit/issue-audit run by a session that did not implement the PR) substitutes the human approval in every flow, and that audit session closes the PR itself in Phase F of the skill (sync, complete label, merge commit, worktree and branch cleanup) once the entry conditions hold; a Step boundary is no longer a gate, and the human review of the whole bounded context becomes asynchronous.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0022 — The clean-context audit session closes the PR it validated, in any flow

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — recorded by issue #164. The adoption itself was decided before this ADR: issue #65
lists it as items 8 and 10 of its block B and records that every item of that block was approved
by the sponsor (Marcelo) on 2026-10-19. This ADR registers the decision, the two points the port
had to settle (§"Decisions taken while porting") and the extension of the approval exception.

The number was checked free on `develop`, on every remote branch and in every open worktree on
2026-11-16 (`0.0.0021` is taken by issue #163, PR #192).

**Partially supersedes ADR 0.0.0004** (it stays `accepted`; it gets an append-only dated note,
CONVENTIONS §5): the sentence of its §Context that leaves the merge with the user outside an
authorized run. ADRs 0.0.0007 and 0.0.0008 are not superseded: §Decision 2 below keeps the merger
each of them names.

## Context

`docs/GIT-WORKFLOW.md` §Gates de PR owns the "+1 approval" rule. Before this ADR it carried three
exceptions, each tied to one flow:

- [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md): an overnight run authorized per stage
  range; the implementer session merges after a clean-context audit.
- [ADR 0.0.0007](./0_0_0007-step-orchestrator-self-merges.md): the Step master session merges
  after the re-audit.
- [ADR 0.0.0008](./0_0_0008-autonomous-orchestrator-parallel-worktrees.md): in the autonomous
  orchestration, the dispatched clean-context auditor merges.

Outside those flows — the standard two-session flow of `docs/PIPELINE.md` §11.1, where a human
opens a fresh session and asks for the audit — the audit session stopped at the `complete` label
and the human merged. The skills said so (`stage-audit` and `issue-audit`: "Nunca faz merge — é do
usuário, salvo pedido explícito"), and the two orchestration prompts each carried a callout
("Override consciente da skill") to get around that sentence. The same act, a merge after a
validated clean-context audit, was allowed or forbidden depending on which prompt had started the
session.

Forces:

- **The merge-time OK carries no decision.** Product and business judgment reaches the human
  through **P** forks (skill `evidence-resolution`), before or during the work, as ADR 0.0.0007
  §Context already argued for the Step flow. What is left at merge time is checking objective
  conditions.
- **The merge sequence already has a single source.** `GIT-WORKFLOW.md` §"Merge e limpeza da
  worktree" (issue #81) fixes the order and states the failure behind each step, including that
  `gh pr merge --delete-branch` leaves the remote branch behind when the branch is checked out in a
  worktree, and that the `complete` label is written only after the run of the last push, with the
  PR free of conflict.
- **The origin of this port orders the steps differently.** In the `financial-forecasting` repo
  (its issue #173, commit `2ca905db`) the audit writes `complete` *before* the push, and the local
  `develop` is updated with `--ff-only` *after* the worktree is removed. Issue #164 copied that
  order and, in the same body, asked for the clash with this repo's sequence to be resolved.
- **A pause at each Step boundary was once agreed.** ADR 0.0.0004 records it under "Authorized
  runs" as a condition of the `1.2` → `3.5` run (2026-07-16): stop after stage `2.5` and after
  `3.5` so the sponsor reviews the whole bounded context. Both stages are merged
  (`stage 2.5: complete`, `stage 3.5: complete` on `develop`). ADR 0.0.0008 (2026-11-01) picks any
  open stage or issue whose dependencies are done, across Steps, and has no pause. Item 10 of issue
  #65 ("Step orchestration without waiting for the human at the merge") was approved after that
  pause was agreed, and nothing recorded what became of it.
- **There is still no mechanical backstop.** `gh api repos/{owner}/{repo}/branches/develop/protection`
  returns **404 "Branch not protected"** (measured 2026-11-16). The 403 quoted by ADR 0.0.0004
  (private repo on GitHub Free) no longer applies: `gh repo view --json visibility` returns
  `PUBLIC`. Protection is now available and not configured; whether to configure it is issue #195.
  Until then a red `audit-gate` does not block `gh pr merge`, and the conditions below are enforced
  by the session's discipline.

## Decision

1. **Scope and substitution.** For a PR **against `develop`** of a stage or of a standalone issue,
   the human approval is substituted by a **clean-context audit** in every flow, not only in the
   three flows above. Clean-context means: the session or subagent that runs `stage-audit` /
   `issue-audit` did not implement the PR and did not receive the implementer's reasoning.
2. **Who closes.** The audit session closes the PR itself, in **Phase F** of the skill, without
   asking for an OK. Two flows keep the merger their ADR already names, and there the audit ends
   at the `complete` label: the Step master session (ADR 0.0.0007) and the implementer of an
   authorized overnight run (ADR 0.0.0004). In the autonomous orchestration (ADR 0.0.0008) the
   dispatched auditor *is* the audit session, so Phase F is what that ADR's §Decision 4 already
   describes. An explicit instruction from whoever asked for the audit not to merge always wins.
3. **Entry conditions.** Phase F runs only when all of these hold, each checked by command output:
   the verdict has no blocker and no open finding inside the scope of the stage/issue; every
   acceptance criterion is met with evidence; every out-of-scope finding is filed as an issue and
   linked in the verdict; the worktree is clean and pushed; the branch carries no foreign-scope
   commit; the PR is not a draft, its checklist is complete, no review conversation is unresolved;
   the dependencies are merged in `develop`; no P fork or HALT is pending. Any condition failing →
   no merge; the session reports what is missing. Stopping is not a failure; merging with something
   pending is.
4. **Sequence.** The single source stays `GIT-WORKFLOW.md` §"Merge e limpeza da worktree"; the
   skills point to it and copy no order. The owning doc of the entry conditions is the same file,
   §"Fechamento autônomo pela auditoria". In that sequence the `complete` label is written after
   the run of the last push (D1 below), the merge is a merge commit from the main checkout without
   `--delete-branch`, the local `develop` is updated with `git pull --ff-only` before the worktree
   is removed, and `worktree-rm.py <branch> --delete-remote` removes the worktree, both branches
   and the worktree's compose project (containers, volumes, networks).
5. **A Step boundary is not a gate.** Neither the merge of the last stage of a Step nor the start
   of a stage of the next Step waits for the human. The human review of the whole bounded context
   becomes **asynchronous and informational**: it is fed by the Step report of
   `PROMPT-step-single-session.md` or by the per-item report of the orchestrator, and a defect found
   in it becomes a post-stage revision (new issue, generic branch), as ADR 0.0.0007 §Decision 4
   already does for the stage report. A pause exists only when the sponsor declares it for a
   specific run — the way the "Authorized runs" entry of ADR 0.0.0004 did for `1.2` → `3.5`. It
   is opt-in per run, never the default (D2 below).
6. **What does not change.** Only the audit session writes `complete` (CONVENTIONS §3.6). A
   session that implemented a PR and then "audits" it gets no exception: it neither writes the
   label nor merges. Every objective gate stays (CI green, coverage, branch up to date, merge
   commit). PRs against `main` (release, hotfix) keep the human approval. A merge refused by the
   session's permissions, or by branch protection once it exists, stops the closing: the session
   reports and never edits the permission configuration or works around the refusal.
7. The exception is registered in the owning doc, `GIT-WORKFLOW.md` §Gates de PR (CONVENTIONS §0);
   skills and prompts carry pointers.

### Decisions taken while porting

Record format of the skill `evidence-resolution` §5.

```
[decision:C] D1 — the `complete` label: written before the push (origin repo) or after the run of the last push (this repo)?
Escolha: after the run of the last push, with the PR free of conflict · Alternativas: before the push · Degrau (C): 1
Base: docs/GIT-WORKFLOW.md §"Merge e limpeza da worktree", passo 2 "com a branch já sem conflito, depois do run do último push" · .github/workflows/audit-gate.yml lê `github.event.pull_request.body` (o corpo do payload do evento, não o corpo atual)
Verificado: não se aplica o §4.2 (decisão de processo; não entra em port, schema, contrato OpenAPI nem regra de segurança)
Configuração candidata: nenhuma · Reversível: sim
```

Both orders leave `audit-status` green when run without racing, so evidence does not elect one:
it is a convention, and the first rung of the ladder decides — the sequence already ratified in
this project (issue #81), which three prompts point to. It also has two properties the other order
lacks: the label is written over a head whose `lint-and-test` has already run, and the verdict
comment cites the hashes that survive the rebase.

```
[decision] P delegado — D2: o que acontece com a pausa humana no fim de cada Step
Escolha: (A) a pausa deixa de ser gate; a revisão do BC inteiro vira assíncrona e informativa; pausa só quando o sponsor a declara para uma corrida
Alternativas: (B) manter a pausa como gate padrão na fronteira do Step · (C) eliminar a pausa, inclusive a declarada por corrida
Motivo: é a opção que não exige mecanismo novo (o formato de "Authorized runs" do ADR 0.0.0004 já sabe declarar a pausa) e não fecha a porta para o sponsor voltar a pedi-la; a orquestração do ADR 0.0.0008 já roda sem pausa, atravessando Steps
Reversível: sim (a pausa volta com uma linha na autorização da corrida ou com um ADR novo)
```

D2 is a **P** fork (it changes when the sponsor looks at the product). The sponsor delegates P
forks to the recommended option during the autonomous orchestration, on the condition that each
one is recorded and listed in the report so that he can revert it; this is that record.

## Alternatives considered

### Alternative A — Keep the merge with the human outside the three flows (status quo)
- **Pros:** human eyes on every merge that no orchestrator started.
- **Cons:** the same validated audit merges or waits depending on the prompt that started the
  session; the skills keep a sentence that two prompts must override.
- **Why rejected:** the sponsor approved the autonomous closing (issue #65, item 8).

### Alternative B — Amend ADR 0.0.0004 with a wider authorization instead of a new ADR
- **Pros:** no new ADR.
- **Cons:** ADR 0.0.0004 governs one flow (the implementer merges, decisions without questions,
  authorization per stage range); stretching it would rewrite an accepted body.
- **Why rejected:** CONVENTIONS §5 forbids editing the body of an accepted ADR; a new ADR plus a
  dated note keeps the history of both.

### Alternative C — Keep the Step-boundary pause as the default gate (D2, option B)
- **Pros:** bounds compounding error per bounded context, the reason ADR 0.0.0004 gave for it.
- **Cons:** needs a mechanism the orchestrator does not have (detect the boundary, park every
  stage of the next Step); stops a backlog that today runs stages of several Steps side by side.
- **Why rejected:** see D2. The bound on compounding error now comes from the per-PR audit.

### Alternative D — Remove the pause for good, including the per-run one (D2, option C)
- **Pros:** one rule, no exception to remember.
- **Cons:** throws away an option that costs nothing to keep.
- **Why rejected:** the sponsor's criterion is a scalable skeleton with a minimal implementation.

### Alternative E — The order of the origin repo: `complete` before the push
- **Why rejected:** see D1.

## Consequences

### Positive
- One rule for who merges an audited PR; the "override" callouts of the two orchestration prompts
  are no longer needed.
- A stage or issue audited by hand ("Audite stage N.M") ends merged and cleaned, with the worktree,
  both branches and the worktree's Postgres gone.

### Negative
- In every flow the audit session now both writes `complete` and merges: a lapse in that single
  session reaches `develop` without a second look. Mitigated, not eliminated, by the entry
  conditions being objective and checked by command output.
- Asking for an audit now ends in a merge when everything holds. Whoever wants only the verdict
  has to say so.
- A modeling mistake in an early stage of a Step may only be noticed by the human several stages
  later, since no boundary stops the run.
- As in ADRs 0.0.0004, 0.0.0007 and 0.0.0008, the conditions are honor-system while `develop` has
  no branch protection (issue #195).

### Neutral / trade-offs accepted
- The Step master (ADR 0.0.0007) and the overnight implementer (ADR 0.0.0004) keep merging in
  their flows; unifying the merger was not asked for.

## References

- Issue #164; issue #65 (block B, items 8 and 10); issue #81 (merge and cleanup sequence); issue
  #195 (branch protection now that the repo is public)
- `docs/GIT-WORKFLOW.md` §Gates de PR, §"Merge e limpeza da worktree", §"Fechamento autônomo pela
  auditoria", §Comportamento bloqueante
- `.claude/skills/stage-audit/SKILL.md`, `.claude/skills/issue-audit/SKILL.md` (Phase F)
- `docs/PROMPT-step-single-session.md`, `docs/PROMPT-stage-single-session-autonomous.md`,
  `docs/PROMPT-orchestrator-autonomous.md`, `docs/PIPELINE.md` §11.1
- `docs/CONVENTIONS.md` §0, §3.6, §5; `.github/workflows/audit-gate.yml`
- [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md),
  [ADR 0.0.0007](./0_0_0007-step-orchestrator-self-merges.md),
  [ADR 0.0.0008](./0_0_0008-autonomous-orchestrator-parallel-worktrees.md)
- Origin: `financial-forecasting` issue #173 (commits `2ca905db`, `4570184a`, `d3ad2def`,
  `1ab9e3ea`) and commits `eea7c822`, `b5b68b61`

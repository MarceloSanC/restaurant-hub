---
title: ADR 0.0.0007 — The Step orchestrator self-merges each stage after a validated clean-context audit
description: Architecture Decision Record
when-use: Reference before running docs/PROMPT-step-single-session.md, when auditing a stage merged by the Step orchestrator, or before changing who merges stage PRs inside a Step
keywords: [adr, process, step, orchestrator, auto-merge, stage-audit, audit-gate, git]
status: accepted
created_at: 2026-10-19
updated_at: 2026-10-19
adr_id: "0.0.0007"
decision: In the Step master session (docs/PROMPT-step-single-session.md) the orchestrator merges each stage PR and cleans its worktree without waiting for human approval, once the clean-context re-audit validated the stage and the merge conditions of §3.4 hold; the human report becomes informational.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0007 — The Step orchestrator self-merges each stage after a validated clean-context audit

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided by Marcelo on 2026-10-19.

## Context

`docs/PROMPT-step-single-session.md` §3.5 required a human **OK on the stage report** before the orchestrator ran `gh pr merge`. That made every stage of a Step wait on the human even when the clean-context audit (`stage-audit` in a fresh subagent), the findings treatment and the re-audit had already validated it, and every objective gate was green.

Business and product judgment already reaches the human through another path: **P** forks are escalated by §2 (via the `evidence-resolution` triage) before or during the stage, not at merge time. The merge-time OK added latency without adding a decision the human had not already taken.

`docs/GIT-WORKFLOW.md` §Gates de PR owns the "+1 approval" rule; its only exception so far was the autonomous overnight run of [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md), authorized per stage range. There is still no mechanical backstop: branch protection is unavailable on this private GitHub Free repo, so `audit-gate` signals without blocking (ADR 0.0.0004 §Context).

## Decision

1. In the Step master session, the **orchestrator self-merges** each stage PR (merge commit), removes the worktree and its compose containers, syncs `develop` and starts the next stage — **without waiting for human approval**.
2. The human approval is **substituted by the clean-context audit**, exactly as in ADR 0.0.0004 §Decision 2: the audit label `complete` and the verdict comment are written by the auditor/re-auditor subagent, never by the orchestrator or the executor.
3. The merge happens **only** when all merge conditions of the prompt's §3.4 hold: label `complete`; no open blocker; CI green on the PR head (including `audit-gate`); branch ahead of `origin/develop` with no foreign-scope commits; no pending P fork or HALT. Any failing condition → HALT-and-park and a report to the human.
4. The stage report (prompt §3.5) becomes **informational**: delivered after the merge, not a gate. A defect the human finds afterwards becomes a post-stage revision (new issue, generic branch).
5. The exception is registered in the owning doc, `GIT-WORKFLOW.md` §Gates de PR (CONVENTIONS §0), with echoes in §Comportamento bloqueante and `PIPELINE.md` §11.1.

Unlike ADR 0.0.0004, this authorization is **not per stage range**: it applies to every Step run with this prompt. The stage-level prompts are unchanged — the executor subagent still opens the PR and never merges.

## Alternatives considered

### Alternative A — Keep the human OK on the report (status quo)
- **Pros:** human eyes on every merge.
- **Cons:** each stage blocks on the human even after a validated audit; the Step does not advance unattended.
- **Why rejected:** the sponsor chose to remove that wait; product decisions still reach the human through P forks.

### Alternative B — Reuse ADR 0.0.0004 with a new authorized range
- **Pros:** no new ADR.
- **Cons:** ADR 0.0.0004 governs a different flow (one implementer session per stage, `PROMPT-stage-single-session-autonomous.md`) and requires re-authorizing each range; it explicitly leaves `4.x` onward unauthorized.
- **Why rejected:** the Step orchestrator keeps the human in the loop for P forks, which is what made ADR 0.0.0004 cautious about judgment-heavy stages; a dedicated rule is clearer than stretching that one.

## Consequences

### Positive
- A Step advances stage by stage without idle waits on merge approval.
- The auditor keeps no hand on the merge (anti-bias preserved); the merger (orchestrator) cannot write the label.

### Negative
- A silent bug that passes audit and gates reaches `develop` without human review and propagates to the following stages until found.
- The audit gate remains honor-system on this plan: the orchestrator's discipline in checking §3.4 is the brake. Re-evaluate if the repo moves to a plan with branch protection.

## References

- `docs/PROMPT-step-single-session.md` §3.4–§3.5
- `docs/GIT-WORKFLOW.md` §Gates de PR, §Comportamento bloqueante
- `docs/PIPELINE.md` §11.1
- `docs/CONVENTIONS.md` §0, §3.6
- [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md)
- `.claude/skills/stage-audit/SKILL.md`

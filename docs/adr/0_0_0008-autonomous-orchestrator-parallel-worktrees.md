---
title: ADR 0.0.0008 — An autonomous orchestrator runs stages and issues in up to three worktrees, and the clean-context auditor merges
description: Architecture Decision Record
when-use: Reference before running docs/PROMPT-orchestrator-autonomous.md, when auditing a PR merged by an orchestrated auditor, or before changing the parallel-worktree cap or who merges orchestrated PRs
keywords: [adr, process, orchestrator, autonomous, worktree, parallel, auditor, auto-merge, github-actions, git]
status: accepted
created_at: 2026-11-01
updated_at: 2026-11-01
adr_id: "0.0.0008"
decision: An orchestrator session dispatches one fresh implementer session per stage or issue (PROMPT-stage-single-session / PROMPT-issue-single-session), each in its own worktree, at most three worktrees at once; the full CI gate runs on GitHub Actions; when the implementation ends, a fresh clean-context auditor audits the PR and, if it validates, rebases, merges and cleans up the branch and worktree.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0008 — An autonomous orchestrator runs stages and issues in up to three worktrees, and the clean-context auditor merges

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided by Marcelo on 2026-11-01.

## Context

[ADR 0.0.0007](./0_0_0007-step-orchestrator-self-merges.md) lets the Step master session merge each stage after a clean-context re-audit, but it runs one stage at a time inside one Step and the master itself merges. The sponsor wants the open backlog (stages **and** standalone issues) to advance unattended and in parallel, with the master acting only as a dispatcher and decision point.

Three constraints shaped the rules:

- **Cost.** Each in-flight worktree is a live implementer session (or an auditor session) burning tokens; parallelism needs a hard cap.
- **Local machine.** `make check` spawns hundreds of processes (Avast freezes the PC, see memory notes), and parallel worktrees sharing one local Postgres produce false `ERROR at setup`/deadlocks. GitHub Actions already runs the exact `make check` with its own Postgres service on every `pull_request` (`.github/workflows/ci.yml`, ADR 2.3.0001), so the authoritative full gate can live there.
- **Merge latency.** Waiting for the master to collect each audit and then merge serializes the pipeline; the auditor already holds the clean-context judgment and the PR state.

## Decision

1. **Orchestrator.** A master session ([`PROMPT-orchestrator-autonomous.md`](../PROMPT-orchestrator-autonomous.md)) writes no implementation. It picks the next open stages/issues from `docs/roadmap.md`, creates each worktree with `scripts/worktree-new.py` (never on the main checkout, which stays on `develop`), and dispatches a fresh implementer subagent with the filled-in `PROMPT-stage-single-session.md` or `PROMPT-issue-single-session.md`. It answers the implementers' forks itself through the `evidence-resolution` triage; only **P** forks reach the human.
2. **Cap: three worktrees.** At most **three** implementation worktrees exist at once, counting those whose PR is open but not merged. A new one opens only when one is removed, and only if it does not conflict with those in flight (criteria in `GIT-WORKFLOW.md` §"Branches em execução"). The orchestrator's own process-doc branch is not an implementation worktree.
3. **CI on GitHub Actions.** The implementer opens the PR as a **draft** at its first push so every push runs the full `make check` on Actions; locally it runs only focused checks (ruff/mypy on touched files, the affected tests against the worktree's own Postgres). Exit-gate evidence for `make check`/coverage is the Actions run (`gh pr checks`, `gh run view --log`), not a local rerun. The implementer marks the PR ready when its exit gates hold.
4. **The auditor merges.** When the implementer reports, the orchestrator dispatches a **fresh** auditor subagent (`stage-audit` / `issue-audit`). The auditor judges, applies in-scope fixes on the branch, writes the audit verdict comment and the `complete` label, and — only if the merge conditions hold (label `complete`; no open blocker; Actions green on the PR head, including `audit-gate`; branch rebased on `origin/develop` with no foreign-scope commits; no pending P fork) — merges with a merge commit (`gh pr merge --merge --delete-branch`), runs `docker compose down -v` in the worktree, `python scripts/worktree-rm.py <branch>`, and deletes the local branch. Any failing condition → no merge; the auditor reports and the orchestrator parks the item.
5. The approval exception is registered in the owning doc, `GIT-WORKFLOW.md` §Gates de PR (CONVENTIONS §0); the prompts carry pointers.

## Alternatives considered

### Alternative A — The orchestrator merges (as in ADR 0.0.0007)
- **Pros:** keeps the judge (auditor) separate from the actor (merger); the label writer cannot merge.
- **Cons:** the master must hold every PR state in its context and serializes merges behind its own turns.
- **Why rejected:** the sponsor chose to give the merge to the clean-context auditor. The anti-bias property that matters — the implementer never judges its own work — is preserved.

### Alternative B — Keep the full `make check` local before every commit
- **Pros:** red never reaches the remote.
- **Cons:** with three worktrees, local process churn freezes the machine and the shared Postgres yields false failures.
- **Why rejected:** Actions runs the same `make check` with an isolated Postgres; drafts keep red runs off reviewers.

### Alternative C — No cap, or the old cap of two branches without PR
- **Pros:** more throughput / continuity with the manual rule.
- **Cons:** unbounded token spend; the old rule ignores PR-open branches that still hold a worktree and an auditor session.
- **Why rejected:** the sponsor fixed three worktrees as the cost ceiling.

## Consequences

### Positive
- The backlog advances unattended, three items at a time, with the human only on P forks.
- The local machine runs only focused checks; the gate of record is reproducible on Actions.

### Negative
- The auditor both writes `complete` and merges: a lapse in that single session reaches `develop` without a second look. Mitigated by the merge conditions being objective (Actions green, `audit-gate`) and checked by command output, not judgment.
- A red Actions run is found after the push rather than before the commit; fixes land as extra commits on the draft.
- As in ADR 0.0.0004/0.0.0007, there is no branch protection on this plan: the merge conditions are honor-system.

## References

- `docs/PROMPT-orchestrator-autonomous.md`
- `docs/PROMPT-stage-single-session.md` §REGRA DE PR, `docs/PROMPT-issue-single-session.md` §REGRA DE PR
- `docs/GIT-WORKFLOW.md` §Princípios fundamentais #7, §Gates de PR, §Branches em execução
- `docs/PIPELINE.md` §11.1
- `.github/workflows/ci.yml`, `.github/workflows/audit-gate.yml`
- [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md), [ADR 0.0.0007](./0_0_0007-step-orchestrator-self-merges.md)

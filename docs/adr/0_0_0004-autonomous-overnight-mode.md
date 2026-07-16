---
title: ADR 0.0.0004 — Autonomous overnight stage execution mode
description: Architecture Decision Record
when-use: Reference before authorizing an autonomous overnight run, when auditing a stage executed in autonomous mode, or before changing the autonomous-run rules
keywords: [adr, process, autonomous, overnight, git, auto-merge, stage-audit, audit-gate]
status: proposed
created_at: 2026-07-12
updated_at: 2026-07-12
adr_id: "0.0.0004"
decision: Define an autonomous overnight stage-execution mode where the agent self-merges stage PRs, with a clean-context audit (stage-audit + audit-gate label) substituting the human approval gate; each run must be explicitly authorized by flipping this ADR to accepted with the stage range recorded.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0004 — Autonomous overnight stage execution mode

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`proposed`

**This ADR defines the mechanics but authorizes no run.** A run only exists when a human flips this ADR to `accepted` **and** records the authorized stage range and date in the "Authorized runs" section below. The autonomous prompt variant refuses to start while this ADR is not `accepted`.

### Authorized runs

_None yet. Format: `<stage range> — authorized by <who> on <YYYY-MM-DD>`._

## Context

Some stretches of the roadmap are plumbing and well-specified modeling whose decisions are already taken or documented (roadmap, overview, LAYOUT, skills). For those stretches, an unattended overnight run following `docs/PROMPT-stage-single-session.md` — one stage per session, chained — is viable, **if** each stage can be merged without waiting for a human, because the stage chain is dependency-ordered: stage N+1's real prerequisite is "N **merged** into `develop`", not "N marked done in the roadmap".

Two written rules conflict with unattended self-merge:

- `docs/PROMPT-stage-single-session.md` §"REGRA DE PR": the implementing session opens the PR but **never merges** — the merge belongs to the user.
- `docs/GIT-WORKFLOW.md` §"Comportamento bloqueante" lists "merge without ≥ 1 approval" as an absolute stop.

This repo also has an **audit signal** the flow must compose with: the `audit-gate` CI workflow goes red while the PR's audit label (CONVENTIONS §3.6) is not `complete`, and only the audit session (running `stage-audit`/`issue-audit`) may write `complete`. It **signals** the audit state; it **cannot block** the merge on this plan — see the Forces below.

Forces:

- Per-stage merge is load-bearing for the chain to advance overnight.
- An unattended run that papers over a real contradiction is worse than one that stops.
- **There is no mechanical backstop today, and this is decisive.** Branch protection is
  unavailable on this repo (**private** repo on GitHub **Free**):
  `gh api repos/:owner/:repo/branches/develop/protection` → **403 "Upgrade to GitHub Pro or make
  this repository public"** (verified 2026-07-12). Therefore **no check can be a Required Status
  Check** — including `audit-gate`, which the workflow itself declares observational
  (`.github/workflows/audit-gate.yml:15-17`). A PR whose check is **red** shows
  `mergeStateStatus: UNSTABLE`, **not** `BLOCKED`, and `gh pr merge` succeeds anyway. Whatever
  replaces the human gate is therefore enforced by the agent's discipline, not by the platform.
  Re-verify this when authorizing a run — the answer changes if the repo goes public or to Pro.

## Decision

For explicitly authorized overnight runs only:

1. **The agent self-merges** stage PRs into `develop` without waiting for a human approval. This overrides the prompt's "the merge is the user's" rule and the GIT-WORKFLOW "merge needs approval" stop, **for the authorized run only**.
2. The **human approval gate is substituted by a clean-context audit**: each stage is audited by a fresh-context session/subagent running the `stage-audit` skill, which never shares the implementer's context. Findings are triaged; blockers are fixed and re-audited before the merge. The audit session writes the audit label `complete` + verdict comment on the PR (CONVENTIONS §3.6), which is what unlocks the `audit-gate` CI check — the label is **never** written by the implementer.
3. **All objective gates remain mandatory and unchanged**: `make check` green, coverage ≥ 90% on the stage's touched files, `check_technical_postexec.py`, the test-audit loop with real mutations, checkpoints A/B/C with disposed findings, issue-first, conventional commits with `Refs #`.
4. **Decisions taken outside the initial question round** follow the autonomous decision policy: enumerate options, research trade-offs against concrete references (no unfounded claims), weigh real gain vs real (not overestimated) implementation cost, prefer the simplest swappable solution that does not constrain growth — and record each non-trivial decision as an ADR (`status: accepted`).
5. **HALT-and-park** (stop the run, record why, leave the tree stable): contradiction with a higher-hierarchy source (Overview > Roadmap > Concept > Technical), an irreversible external contract that is ambiguous, any gate that cannot go green after an honest fix attempt, or a merge technically blocked by branch protection.
6. **Git safety**: never force-push; never rewrite merged history of `develop`/`main`. Rebasing the agent's own in-flight branch onto `origin/develop` to drop unrelated commits (GIT-WORKFLOW Etapa 4) is allowed and is not "rewriting old history".
7. **External side effects**: nothing leaves the machine overnight besides git/GitHub operations. E-mail and any third-party integrations run against fakes/local capture; integration tests use the local docker-compose services (postgres), never live external APIs.

## Alternatives considered

### Alternative A — Agent opens PR, human merges each stage
- **Description:** keep the written rule; agent stops at a green PR, human merges in the morning.
- **Pros:** honors the documented process literally; human eyes on every merge.
- **Cons:** the dependency chain advances ~1 stage/day — defeats the overnight goal entirely.
- **Why rejected:** incompatible with an unattended multi-stage chain.

### Alternative B — Same actor implements and audits
- **Description:** the implementing session also runs the audit and writes the `complete` label.
- **Pros:** simpler, no fresh-context orchestration.
- **Cons:** context bias — the auditor inherits the implementer's blind spots; CONVENTIONS §3.6 explicitly forbids the implementer writing `complete`.
- **Why rejected:** removes the impartiality that justifies substituting human review, and burns the audit-gate's meaning.

### Alternative C — Do nothing / status quo (fully manual)
- **Description:** run every stage manually with the human gate.
- **Pros:** maximum control.
- **Cons:** no autonomous throughput on well-specified plumbing stages.
- **Why rejected:** the human's time is better spent on judgment-heavy stages (e.g. the auto-fill algorithm, deploy decisions).

## Consequences

### Positive
- Authorized stretches of the chain can run unattended; the human reviews afterward and stays in the loop for judgment-heavy stages.
- The audit is **written down and impartial by construction** (fresh context, separate label, never written by the implementer), and the objective gates (`make check`, coverage, real mutation) *do* fail hard on their own — those are the teeth.
- `stage-audit` and future sessions read this ADR and will **not** flag self-merge as a blocking violation for an authorized run. The exception is registered in the **owning** doc — `GIT-WORKFLOW.md` §Gates de PR (CONVENTIONS §0: "o dono vence") — so the ADR is actually in force, not letra morta.

### Negative
- A silent bug merged in an early stage propagates down the chain until an audit or gate catches it. Mitigated by per-stage clean-context audit + objective gates, not eliminated.
- Deviates from two written rules; the deviation is scoped and recorded here, but it is still a deviation.
- **The audit gate is honor-system, not machine-enforced — say it plainly.** `audit-gate` is
  observational on this plan (see Context): it goes red and the PR stays mergeable. So the
  substitute for human approval is: objective gates that *do* fail hard, plus the agent's
  discipline in actually running the impartial audit and not writing its own `complete`. **A human
  authorizing a run is accepting that**, not accepting a mechanical guarantee. If that trade is
  unacceptable for a given stretch, do not authorize it — or move the repo to a plan where branch
  protection makes `audit-gate` a Required Status Check, and revisit this ADR.

### Neutral / trade-offs accepted
- The run may HALT partway (contradiction, gate, ambiguity, blocked merge) and wait for a human, rather than force progress.

## Implementation notes

- Per-stage loop: issue + branch + `docs/stages/<N.M>-<slug>/` → implementer session runs the autonomous prompt variant → fresh-context auditor runs `stage-audit` and writes the label → CI green → merge (merge commit) → sync → next stage.
- The autonomous prompt variant lives at `docs/PROMPT-stage-single-session-autonomous.md`.
- Authorizing a run = flip `status` to `accepted` + fill "Authorized runs" + verify branch-protection state on `develop`.

## References

- Related: `docs/PROMPT-stage-single-session.md`, `docs/GIT-WORKFLOW.md` §Gates / §Comportamento bloqueante, `docs/CONVENTIONS.md` §3.6, `.github/workflows/audit-gate.yml`, `.claude/skills/stage-audit/SKILL.md`.
- Origin: adapted from the `financial-forecasting` repo's ADR 0.0.0050 (autonomous overnight mode), adjusted to this repo's audit-gate label flow and stack.

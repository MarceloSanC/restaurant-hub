---
title: ADR 1.1.0002 — PR gates are observational on GitHub Free (no branch protection)
description: Architecture Decision Record
when-use: Reference when questioning why merges are not mechanically blocked, before configuring branch protection, or when evaluating a GitHub plan upgrade
keywords: [adr, github, branch-protection, pr-gates, ci, github-free]
status: accepted
created_at: 2026-07-14
updated_at: 2026-07-14
adr_id: 1.1.0002
decision: Keep the GIT-WORKFLOW PR gates (green CI, coverage, approval, merge commit) as prescribed discipline enforced by convention and CI checks, accepting that GitHub Free on a private repository cannot mechanically block merges via branch protection
context_stage: 1.1-bootstrap
bounded_context: transversal
---

# ADR 1.1.0002 — PR gates are observational on GitHub Free

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

`docs/GIT-WORKFLOW.md` §Gates de PR prescribes blocking gates for every
PR: green CI, coverage ≥ 90%, +1 approval, branch up to date, resolved
conversations, merge commit only. The template's setup runbook
(`docs/runbooks/github-repo-setup.md`) assumes these are materialized as
**branch protection rules**.

Reality of this repository:

- The repo is **private** and the account is on the **GitHub Free**
  plan. Branch protection rules (and rulesets that block) are not
  enforced on private repos under Free — they require Pro/Team.
- The project is developed **solo** (overview §6): the "+1 approval"
  gate has no second human anyway; review happens via the audit session
  (`stage-audit`/`issue-audit`) and the `audit-gate` CI workflow.
- CI-side guards already exist: `guard-main-source` (ci.yml) fails PRs
  to `main` that don't come from `develop`/`hotfix/*`; `audit-gate.yml`
  fails while the PR's audit label is not `complete`.

## Decision

Accept that the PR gates are **observational** (not mechanically
enforced by GitHub) while the repo stays private on the Free plan:

1. The gates remain **prescribed** — GIT-WORKFLOW is unchanged as the
   process contract; skipping a gate is a process violation even though
   GitHub won't physically block it.
2. Enforcement is delegated to **discipline + CI checks that fail
   loudly**: `ci.yml` (make check), `guard-main-source`, `audit-gate`.
   A red check on a merged PR is visible and auditable after the fact.
3. If the repo ever moves to a paid plan (or goes public), configuring
   branch protection per `github-repo-setup.md` becomes a mandatory
   chore — tracked as a trigger condition, not a date.

## Alternatives considered

### Alternative A — Upgrade to GitHub Pro/Team now
- **Description:** pay for the plan that enforces branch protection.
- **Pros:** real mechanical blocking; no reliance on discipline.
- **Cons:** recurring cost for a solo pilot project; the main gate it
  would enforce (+1 human approval) has no second human to satisfy it.
- **Why rejected:** cost without matching benefit at this stage
  (issue #1; overview §6 — minimize infrastructure cost).

### Alternative B — Make the repo public to get free branch protection
- **Description:** public repos on Free do get branch protection.
- **Pros:** free mechanical enforcement.
- **Cons:** the codebase is a commercial SaaS being built for a pilot
  customer; publishing it is a business decision far beyond tooling.
- **Why rejected:** exposes commercial code to solve a tooling gap.

### Alternative C — Do nothing / leave it undocumented
- **Why rejected:** the docs (GIT-WORKFLOW, github-repo-setup runbook)
  read as if merges are mechanically blocked; a future contributor (or
  AI session) would assume a safety net that does not exist. The gap
  must be recorded.

## Consequences

### Positive
- The real enforcement level is documented; no false sense of a safety
  net.
- CI checks still make every gate violation **visible** (red X on the
  PR), preserving auditability.
- Zero recurring cost.

### Negative
- A hasty `gh pr merge` can physically land a red PR on `develop`/`main`.
  Mitigation is procedural: GIT-WORKFLOW §Comportamento bloqueante and
  the audit-session protocol.

### Neutral / trade-offs accepted
- "+1 approval" is satisfied by the audit session (independent context)
  rather than a second human, for as long as development is solo.

## Implementation notes

- No repo settings change is possible or needed now; this ADR is the
  record.
- Trigger to revisit: plan upgrade, going public, or a second developer
  joining — then run `docs/runbooks/github-repo-setup.md` §branch
  protection and mark this ADR superseded if the enforcement model
  changes.

## References

- Related ADRs: [ADR 1.1.0001](./1_1_0001-windows-native-dev-environment.md)
- GIT-WORKFLOW gates: `docs/GIT-WORKFLOW.md` §Gates de PR (fonte única)
- CI guards: `.github/workflows/ci.yml` (`guard-main-source`),
  `.github/workflows/audit-gate.yml`
- GitHub docs — branch protection availability:
  https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- Issue: [#1](https://github.com/MarceloSanC/restaurant-hub/issues/1)

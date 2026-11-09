---
title: 'ADR 1.2.0001 — Deterministic PR-path gates: no network, and no silent degradation either'
description: Architecture Decision Record
when-use: Reference before adding a gate to `make check` that talks to a network service or reads git history, or when a CI gate turns out to be silently skipping on the runner
keywords: [adr, ci, gate, pr-path, determinism, fail-open, fetch-depth, shallow-clone, github-actions, scheduled-scan]
status: accepted
created_at: 2026-07-16
updated_at: 2026-11-09
adr_id: "1.2.0001"
decision: The PR path stays network-free (network validation lives in the scheduled scan), and a check that belongs on the PR path must be given what it needs to actually run — determinism is never bought by letting a check skip itself.
context_stage: 1.2-ci
bounded_context: shared
---

# ADR 1.2.0001 — Deterministic PR-path gates: no network, and no silent degradation either

> ⚠️ **Errata (2026-11-09):** §Consequences › *Neutral / trade-offs accepted* — the first bullet (`scripts/` outside coverage measurement and outside `mypy`, `make typecheck` running `mypy src/` only) no longer holds: since issue #91 `make typecheck` runs `mypy src/ tests/fakes/ scripts/ .claude/hooks/`, `[tool.coverage.run] source` includes `scripts` and `.claude/hooks`, and `make test-gate` holds `src/` and the tooling to `fail_under` in separate `coverage report --include` runs. The decision (network-free, non-degrading PR path) is unchanged — ver issue #91 / PR #140

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

The project's quality gate is a single chain, `make check`
(`lint typecheck layout-check import-check lock-check docs-check test-gate`), and
`.github/workflows/ci.yml` runs it literally. `docs/runbooks/validate-ci-gate.md`
§Purpose leans on that literalness for its central claim — the **transitivity
argument**: if every error class fails `make check` locally, every class fails it
on the runner.

The repo's CI is built as **two halves**. The scheduled half is
`.github/workflows/stage-issue-audit.yml`, whose header states the pattern
verbatim:

> "O docs-check de PR/local valida só o delta da branch (rápido e determinístico).
> Esta varredura completa agendada é a segunda metade do padrão: pega drift
> pós-merge (issue apagada/transferida depois que a stage entrou) e qualquer stage
> que tenha entrado por caminho não validado — fora do caminho crítico de PR, onde
> flakiness de rede não bloqueia ninguém."

That header **corroborates** a split — networked full scan placed off the PR
critical path, weekly, with `GH_TOKEN` and `permissions: issues: read` — but it is
**not decisive evidence** that the absent token in `ci.yml` was deliberate, and
this ADR does not pretend otherwise. Its first sentence is imprecise: "valida só o
delta da branch" describes `check_technical_postexec.py` (which only *enforces*
inside a stage's execution window) but not `check_stage_issue.py`, which globs
every stage. And `check_stage_issue.py:19-22` says the script "funciona normalmente"
in CI with an authenticated `gh` — true of the scheduled workflow, but readable as
an expectation of a token on PRs too. The decision below rests on structural facts,
not on this reading.

Stage 1.2 audited both halves and found two checks that look identical from
`ci.yml` — each prints something and exits 0 — and are **not** the same thing:

1. **`check_stage_issue.py`'s WARN on the PR runner should stay.** Not because a
   comment says so, but because the check is repo-global
   (`discover_technicals()`, `:114-123`, globs `docs/stages/*/technical.md`), so
   enforcing it on PRs would red every PR in the repo whenever any stage sits in
   phase 3A with a placeholder `issue_id` — the literal state of this stage's own
   branch while it was written. And its verdict would depend on the network:
   `issue_exists()` (`:66-81`) returns the same `False` for "the API answered: no
   such issue" and "I could not reach the API". The weekly scan already covers the
   case, without either cost.
2. **`check_technical_postexec.py` check 2 (§7 freeze, CONVENTIONS §3.4) is
   genuinely broken on the PR path — and it is the check that belongs there.** It
   finds its baseline commit `stage N.M: technical approved` via `git log`.
   `actions/checkout@v4` defaults to `fetch-depth: 1`, so the runner's clone holds
   one commit, the baseline is invisible, `_approved_commit_for()` returns `None`,
   and check 2 is skipped. Verified empirically (concept §3) on a synthetic stage
   that is `done` and **not merged** — the only state in which the freeze should
   fire: with full history the same out-of-window patch exits **1**; in a
   `--depth 1` clone of the same commit it exits **0**. The script's docstring
   lists "clone raso" as a known limitation; what nobody noticed is that **CI is a
   shallow clone**.

The asymmetry is the point. Check 1 is fail-open **by decision**, with its coverage
relocated to the scheduled scan. Check 2 is fail-open **by accident**, with its
coverage relocated to nowhere.

Forces:

- **Network on the PR path is rejected already**, with a written reason. Any
  proposal to add it must beat that reason, not ignore it.
- **A skipped check is not a neutral check.** It reports green because it did not
  look — a false negative wearing a checkmark. "Deterministic" must not come to
  mean "reliably skips".
- **Fail-open has a legitimate cause that never goes away.** A stage still in
  phase 3A/3B genuinely has no `technical approved` commit yet. Any fix must keep
  telling that apart from "the environment hid the baseline".
- **Local `make check` must not require `gh` or full history** — a contributor
  running the tests is not blocked by tooling they do not have.

## Decision

**Two rules, one principle.**

1. **No PR-path check decides on the network.** The PR runner is already
   network-dependent to *function* (`checkout`, `setup-python`, `setup-uv`,
   `uv sync` against PyPI — a PyPI outage reds a PR today). The rule is narrower
   and about **verdicts**: no check may approve or reject based on reaching an
   external service. Validation whose verdict needs the network belongs in the
   scheduled scan. `check_stage_issue.py` therefore keeps its WARN on the PR
   runner — it still *executes* there (it is inside `make docs-check`, and locally,
   with `gh`, it is useful), but its **enforcement** lives in the weekly scan.
2. **A check whose verdict the PR path can give must actually give it.** The §7
   freeze needs git history, not a network; it belongs on the PR path. So `ci.yml`
   checks out with `fetch-depth: 0`. Fixed **at the cause**, not managed with a
   flag: restoring the history makes `None` mean only "not approved yet" again, so
   the legitimate skip survives and the accidental one disappears.

The principle joining them: **a check may degrade only when the degradation is
decided or semantic — never when it is an accident of the environment.**

| Degradation | Example | Verdict |
|---|---|---|
| **Decided** — the check does not belong to the PR verdict; its coverage lives elsewhere | `check_stage_issue.py` warns on the runner; the weekly scan enforces | legitimate |
| **Semantic** — the rule does not apply to this case | a stage in 3A/3B has no `technical approved` baseline yet | legitimate |
| **Accidental** — the check belongs here, applies here, and the environment silently stops it | shallow clone hides the baseline | **defect** |

Corollary for future gates: before adding anything to `make check` that reads git
history, ask what it sees under `fetch-depth: 1`; before adding anything whose
**verdict** opens a socket, it goes to the scheduled scan or it does not go in.

## Alternatives considered

### Alternative A — Wire `GH_TOKEN` into `ci.yml` and enforce issue-first on every PR
- **Description:** add `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` plus
  `permissions: issues: read` to the `make check` step, making
  `check_stage_issue.py` live on the PR path.
- **Pros:** GIT-WORKFLOW Princípio #1 enforced at PR time; a bogus `issue_id`
  caught in minutes instead of up to a week.
- **Cons, in order of weight:** (1) the gate is **repo-global** —
  `discover_technicals()` globs `docs/stages/*/technical.md`, so one stage sitting
  in phase 3A with a placeholder `issue_id` reds *every unrelated PR* in the repo.
  This is not hypothetical: it is the state of this stage's own branch as written
  (`make check` red locally on `issue_id: 0`), and it would recur on every stage's
  3A. (2) The verdict would depend on the network: `check_stage_issue.py:66-81`
  returns the same `False` for "the API answered: no such issue" and "I could not
  reach the API", so an outage reds the PR while blaming a valid issue number.
  (3) The weekly scan already covers the case.
- **Why rejected:** cons (1) and (2) are structural and proven; the gain is ~6 days
  of detection latency on a failure the scheduled scan already catches. Note the
  honest bookkeeping: "imports network flakiness into the critical path" is a
  *marginal* cost, not a new boundary — the runner already needs PyPI to run at
  all. The decisive argument is the repo-global blast radius, not network purity.
  Flaky gates train people to re-run red checks without reading them, which is how
  a real failure gets waved through.

### Alternative B — Add a "require baseline" flag to `check_technical_postexec.py`
- **Description:** mirror the shape of A: an env-var/flag that makes "no baseline
  found" a hard failure in CI.
- **Pros:** no change to checkout; the gate reports when it cannot do its job.
- **Cons:** it cannot work. "No baseline" is *legitimate* for a stage in 3A/3B —
  the approval commit does not exist yet. The flag cannot distinguish that from
  "the shallow clone hid it", so it would red every PR of every stage that has not
  reached phase 3B. Managing an ambiguity that can be deleted instead.
- **Why rejected:** treats a removable environmental defect as a permanent
  semantic one.

### Alternative C — Do nothing / status quo
- **Description:** leave `fetch-depth: 1`; record the skipped freeze as a finding.
- **Pros:** zero cost; CI stays as fast as it is today.
- **Cons:** the §7 freeze (CONVENTIONS §3.4) stays unenforced precisely in the
  window it exists for — a stage `done` and not yet merged, which is what every
  stage PR is. Note the precise claim: `validate-ci-gate.md` is **silent** about
  this sub-check, not wrong. Its Class 5 routes through the *structural* check
  (`:191` — "break a marker … regardless of whether `gh` is available"), which does
  run under a shallow clone, and it names the check-2 skip as "by design" (`:187`)
  for a stage in 3A/3B. So the transitivity argument holds for what the runbook
  covers and simply does not reach the diff-vs-baseline sub-check. This stage
  extends it to reach it. Stage 1.2's charter is "activate and validate the CI
  pipeline"; deferring the one defect it exists to find would orphan it, since no
  later stage has a reason to look here.
- **Why rejected:** it is the status quo this stage was created to end.

### Alternative D — Targeted fetch of the approval commit instead of full history
- **Description:** keep the shallow clone and fetch only what check 2 needs (e.g.
  `git fetch --deepen` until the approval commit appears, or fetch `origin/develop`
  separately).
- **Pros:** keeps checkout cheap as the repo grows; addresses the same cause.
- **Cons:** the depth needed is not knowable in advance (it depends on how far back
  the approval commit sits), so it becomes a loop with a heuristic bound —
  machinery whose failure mode is *silently not deep enough*, i.e. the exact bug
  being fixed, now harder to see.
- **Why rejected:** premature. At 53 commits the full clone costs ~1s. Reconsider
  when checkout time actually shows up in the run; the swap is one line and this
  ADR is the place to revisit.

## Consequences

### Positive

- The §7 freeze runs on the runner for the first time, in the window it was
  designed for, extending the runbook's transitivity argument to a sub-check it
  never reached.
- The reason `check_stage_issue.py` warns on the PR runner stops being tribal
  knowledge in a workflow comment. The next agent auditing `ci.yml` finds the
  repo-global blast radius written down, instead of reaching for `GH_TOKEN` — a
  failure mode already observed once, in this stage's own first review pass, which
  is why this ADR exists.
- Gives future gates a decision rule (network → scheduled; history → PR path with
  history) instead of a case-by-case argument.

### Negative

- `fetch-depth: 0` clones the full history on every run. Negligible today (53
  commits); it grows with the repo, and the mitigation (Alternative D) is deferred,
  not free.
- The freeze now fires on stage PRs — including this stage's own. Editing a
  `technical.md` outside the §7 markers after the approval commit reds the PR. That
  is the gate working, but it is friction that did not exist before, and the failure
  message points at line ranges rather than at the rule.
- Issue-first remains unenforced at PR time. A stage PR with a wrong `issue_id`
  merges clean and is only caught by the Monday scan. Accepted deliberately (I1),
  but it is a real hole, not a solved problem.

### Neutral / trade-offs accepted

- `scripts/` sits outside coverage measurement (`[tool.coverage.run] source =
  ["src"]`, and `Makefile` runs `--cov=src/restaurant_hub` — the `omit` entry for
  `*/scripts/*` is redundant with `source`) and outside `mypy` (`make typecheck`
  runs `mypy src/` only). These validators are guarded by the runbook's class-by-
  class procedure rather than by types or coverage. Unchanged by this ADR; recorded
  as a finding.
- `check_stage_issue.py` keeps conflating "not found" with "unreachable". Harmless
  while it runs only in the scheduled scan (a red Monday scan is read by a human),
  and it is the reason Alternative A is not merely "a token away". Recorded as a
  finding against the scheduled half.

## Implementation notes

- Only `.github/workflows/ci.yml` changes: `actions/checkout@v4` gains
  `fetch-depth: 0`. No script is modified; the fix is environmental, and the script
  already documents full history as its requirement.
- `_stage_is_merged()` needs `origin/develop` to resolve; `fetch-depth: 0` fetches
  all branches, which is what creates `refs/remotes/origin/*`. Both this and the
  merge-ref history of a `pull_request` event are **verified by an A/B run** in the
  stage (same intentional patch: green under `fetch-depth: 1`, red under
  `fetch-depth: 0`), not assumed.
- Per `validate-ci-gate.md` §Maintenance, this hardening extends that runbook in the
  same stage — including the environment precondition (full history) that the §7
  class now depends on when it runs on the runner.

## References

- Related ADRs: [`1_1_0002-observational-pr-gates.md`](./1_1_0002-observational-pr-gates.md)
  (why no check here is *Required*: private repo on GitHub Free — this ADR makes a
  gate honest, not blocking); [`0_0_0004-autonomous-overnight-mode.md`](./0_0_0004-autonomous-overnight-mode.md)
  (leans on objective gates that "do fail hard on their own" — this ADR makes one of
  them actually do that).
- Sources: `.github/workflows/stage-issue-audit.yml` (header — origin of the split),
  `.github/workflows/ci.yml`, `scripts/check_technical_postexec.py` (§Limitações
  conhecidas), `scripts/check_stage_issue.py`, `docs/runbooks/validate-ci-gate.md`
  §Purpose, `docs/CONVENTIONS.md` §3.4, `docs/GIT-WORKFLOW.md` §Princípios
  fundamentais #1.
- Stage: `docs/stages/1.2-ci/concept.md` §6 Decisões 1 e 2.

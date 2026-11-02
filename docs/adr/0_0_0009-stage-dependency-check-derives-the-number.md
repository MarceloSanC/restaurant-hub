---
title: ADR 0.0.0009 — The Stage dependency check is a script that takes the stage_id and derives the commit number
description: Architecture Decision Record
when-use: Reference before checking whether a Stage's dependencies are closed, before writing a command that turns a depends_on value into a commit subject, or before changing what make docs-check enforces about Stage order
keywords: [adr, process, pipeline, depends_on, stage_id, reserved-commit, docs-check, placeholder, prompt, integration-branch]
status: accepted
created_at: 2026-11-01
updated_at: 2026-10-21
adr_id: "0.0.0009"
decision: The dependency pre-condition of a Stage (every Stage it depends on is done in the roadmap and its reserved `stage N.M: complete` commit is merged into an integration branch; every issue it depends on is done in the issue table) is checked by scripts/check_stage_deps.py, which takes the stage_id and derives the number itself; make docs-check runs it over every Stage folder.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0009 — The Stage dependency check is a script that takes the stage_id

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #12, whose scope asked for exactly this call: *"avaliar se vale um validador em
`scripts/` … decidir por ADR ou registrar como não-vale-a-pena"*.

**Revised before merge, in the same PR.** The first version checked the history of `HEAD`. A
zero-context completeness review showed that this lets a branch stacked on an unmerged
dependency pass — the state the project's order rules forbid (fact 4) — and the default became
the integration branches (Alternative C records the rejected version). No version of this ADR
reached `develop` before the revision.

## Context

A Stage has one identifier and several derived forms (CONVENTIONS §1, "Identificador da Stage").
Two of them meet in the dependency check:

- `depends_on` — in the roadmap's *Tabela de Stages* and in the concept/technical frontmatter —
  carries the **`stage_id` with its slug**: `1.1-bootstrap`.
- the reserved closing commit carries **only the number**: `stage 1.1: complete`
  (CONVENTIONS §4(b); `scripts/check_commit_msg.py` accepts `^stage \d+\.\d+: complete$`).

Every surface that checks "are this Stage's dependencies closed?" does it by hand, in prose. The
canonical prompt's pre-condition 5 and the runbook's prerequisites read the roadmap status; the
autonomous variant §4 converts each `stage_id` into the number and greps the history
(`git log origin/develop --oneline | Select-String "stage <N.M>: complete"`); the Step prompt
asserts "`depends_on` mergeado em develop" with no command at all.

Facts that weigh on the decision:

1. **The three-line prose check has already failed twice.** The clean-context audit of PR #11
   found F4 — the pattern `stage <dep>` also matched `conceptual draft`/`technical approved`, a
   green for a dependency that had not closed — and F-C — substituting the `stage_id` from
   `depends_on` gives `stage 1.1-bootstrap: complete`, which matches nothing: a false HALT on the
   first dependency of any autonomous run. Both were fixed by rewording the prose. Prose cannot be
   tested, so the next rewording can break it again without anything noticing.
2. **The same class lives in the verification commands.** Measured on `develop` (`b2e1c68`): the
   runbook's `Select-String "$N\.$M.*done"` matches **two** roadmap lines per done Stage (its row
   and the history line). With Stage 3.5's row set to `review` in a copy, it still matches — through
   the issue #59 row, which mentions "Stage 3.5" and is `done`. A green for a Stage that is not done.
3. **The sibling pre-condition is already mechanical.** Issue-first is checked by
   `scripts/check_stage_issue.py`, wired into `make docs-check` (CONVENTIONS §3, GIT-WORKFLOW
   §Comportamento bloqueante). "Dependencies done before the Stage starts" is the other half of
   the same RUNBOOK prerequisite list and had no check at all.
4. **Closed means merged.** The RUNBOOK's prerequisites read "Stage anterior (se houver) já
   mergeada"; PIPELINE's principles read "Linearidade estrita. Sem paralelismo entre Stages";
   GIT-WORKFLOW §"Branches em execução" lets two branches run together only if "nenhuma depende da
   outra (roadmap 'Depende de' …)", and a branch whose PR is open "continua contando no critério de
   conflito". A Stage branch opened on top of an unmerged dependency breaks all three. Today only
   discipline catches it — in this very run, the orchestrator checks it by hand for every front.
5. **Constraints a new gate must respect** (ADR 1.2.0001). No verdict decided on the network; a
   check that reads git history must actually see it on the runner (`ci.yml` checks out with
   `fetch-depth: 0`, and `tests/unit/test_ci_workflow.py` fails if that changes); no silent
   degradation on the PR path; and the force *"Local `make check` must not require `gh` or full
   history"*. `check_technical_postexec.py` already decides "merged" against `origin/develop`,
   `develop`, `origin/main`, `main` on the PR path. Stage 1.2 §7 adds one more: a repo-global
   check must not turn every PR red because of a *legitimate* state somewhere in the repo.
6. **History replay.** For each of the 14 Stage folders that have dependencies, reading the
   roadmap **as it was** at the commit that created the folder, every dependency's
   `stage N.M: complete` commit is an ancestor of that commit. The replay sees history as merged:
   the 4.1 branch was rebased after the 3.5 merge (4.1 technical §7), and its `depends_on` had been
   corrected from `3.5-employee-login-link` to `3.1-staff-domain` (`4deca3c`) just before its
   skeleton (`2e4b3b0`) — so even before the rebase no folder existed with an open dependency.

## Decision

1. **`scripts/check_stage_deps.py` takes the `stage_id` — never the number — and derives the
   number itself** (prefix up to the first hyphen: `1.1-bootstrap` → `1.1`). Given a bare number
   it refuses with an explanation (exit 2). This removes the hand conversion from every caller:
   the prompts pass the `stage_id` they already hold.
2. **The roadmap's *Tabela de Stages* is the source** of `depends_on` and status: it exists for
   Stages that have no folder yet (a Stage being opened) and the canonical pre-condition already
   reads it. Columns are located by header name, not position.
3. **A Stage dependency is closed when** it has a row in the table, its number identifies only that
   row (otherwise `stage N.M: complete` cannot say which Stage closed), its status is `done`, and a
   commit whose subject is **exactly** `stage <N.M>: complete` is reachable from an integration
   branch — `origin/develop`, `develop`, `origin/main`, `main`, whichever resolve, the same list as
   `check_technical_postexec.py` (fact 5). Exact subject: `conceptual approved` and
   `stage 11.1: complete` never satisfy `1.1`.
4. **An issue dependency (`#N`) is closed when** its row in the *Tabela de Issues* is `done` — the
   rule PROMPT-issue's pre-condition 5 already applies. An issue that is not in that table is a
   violation that points to the right form: a Stage's issue is written as the Stage's `stage_id`.
5. **`make docs-check` runs it with no arguments** over every Stage folder in `docs/stages/`. A
   folder only exists after the skeleton commit, which is only legitimate once its dependencies
   merged; so there is no legitimate state in which a folder reds unrelated PRs, and an issue
   dependency in the Stage table is checked, not reported as a malformed row.
6. **Without history** — shallow clone, no integration branch, git that does not run — an explicit
   target (the pre-condition of whoever is about to open a Stage) exits **2**: no verdict, never a
   green. With no target (`docs-check`), the status is still checked and the commit check becomes a
   WARN, honouring fact 5's force for local runs; on the runner the history is there by the
   `ci.yml` invariant the unit test guards.
7. **`--ref` (repeatable) replaces the integration branches** with explicit refs, all of which must
   resolve. **Fail closed** (exit 2) when the verdict cannot be given: roadmap missing or
   unreadable, section or columns missing, an explicit ref that does not resolve. Exit 1 is
   reserved for violations — an open dependency or a roadmap row the script cannot trust.

## Alternatives considered

### Alternative A — Gloss only: write the conversion rule at every point of use
- **Description:** keep the prose checks; state once (CONVENTIONS §1) and at each use that
  `<N.M>` is the number and `depends_on` holds the `stage_id`.
- **Pros:** no new code; this issue writes those glosses anyway.
- **Cons:** the check stays untestable, and it has already been wrong in both directions (F4 false
  green, F-C false HALT); the order rule stays enforced by discipline only (fact 4).
- **Why rejected:** the glosses are necessary — they are how a reader learns which form a surface
  wants — but they are not sufficient for a check that decides whether work may start.

### Alternative B — On-demand script, not wired into `docs-check`
- **Description:** the same script, called only by the prompts' pre-conditions.
- **Pros:** zero risk to anyone's `make check`.
- **Cons:** enforcement again depends on someone remembering to run it — the gap fact 3 points at.
- **Why rejected:** wiring it costs one Makefile line, and fact 6 shows no legitimate opening in
  this repository would have turned it red.

### Alternative C — Check the history of `HEAD` ("what this branch carries")
- **Description:** the first version of this ADR: a dependency's `complete` commit only needs to be
  reachable from the branch being checked; `--ref origin/develop` on demand for "merged".
- **Pros:** the verdict does not depend on how fresh the local remote-tracking refs are.
- **Cons:** a branch stacked on a dependency whose PR is still open passes — exactly what fact 4's
  three rules forbid; the strict check would again depend on someone passing the flag.
- **Why rejected:** it enforces a weaker rule than the one the project wrote down. The freshness
  cost of the integration branches is local only (the runner fetches everything) and errs red:
  a stale ref or roadmap gives a false red until `git fetch`/`git pull`, never a false green.

### Alternative D — Read `depends_on` from the Stage's frontmatter
- **Description:** use `depends_on` in `technical.md`/`concept.md` instead of the roadmap row.
- **Pros:** the field sits next to the folder being checked.
- **Cons:** during phase 3A the frontmatter is still the template (`depends_on: []`), which would
  pass vacuously; and a Stage being opened has no frontmatter yet.
- **Why rejected:** the roadmap is where order is planned (CONVENTIONS §1 "Ordem de implementação
  = `depends_on`") and the only source that exists before the folder does.

### Alternative E — Fail closed in a shallow clone, `docs-check` included
- **Description:** exit 2 whenever the history is missing, with or without a target.
- **Pros:** the gate could never go green without looking, whatever the runner does.
- **Cons:** a local `make check` would require full history, against ADR 1.2.0001's force (fact 5),
  while the runner's history is already guaranteed by `fetch-depth: 0` and its unit test.
- **Why rejected:** the strictness belongs where a verdict is requested — the explicit target —
  and the always-on run keeps checking what it can (the status) and says what it skipped.

### Alternative F — Do nothing / status quo
Leaves fact 1 and fact 2 standing: a prose check that has already failed both ways, and a
verification command that is green for a Stage that is not done.

## Consequences

### Positive

- The stage_id → number conversion lives in one tested place; every caller passes the `stage_id`.
- Opening a Stage before its dependencies merged turns `make check` red on that branch at the
  first run — stacked branches included — instead of relying on whoever opened it.
- A roadmap that says `done` without the reserved commit merged — or the reverse — surfaces on the
  first Stage that depends on it.

### Negative

- One more script in `make docs-check`, and one more gate that needs full history and the
  integration branches on the runner (already requirements of `check_technical_postexec.py`
  check 2; `ci.yml` has `fetch-depth: 0`).
- Locally, the verdict follows the freshness of the remote-tracking refs and of the working-tree
  roadmap (status is read from the working tree, commits from the refs): stale ones give a false
  red until `git fetch`/`git pull`. Never a false green.
- A reverted `stage N.M: complete` commit still counts as present (its subject stays in the
  history). The status check covers it only when the revert also restores the roadmap row — true
  when the row was flipped in the closing commit, as the canonical prompt does, not when it was
  flipped in a separate `docs(roadmap)` commit, which RUNBOOK Passo 10 and the CONVENTIONS §4(a)
  example also allow.

### Neutral / trade-offs accepted

- The other copies of `depends_on` — the concept/technical frontmatter and the YAML block of some
  Stages in the roadmap — are not cross-checked against the table; a divergence goes unnoticed.
- An issue dependency is checked by its status only: there is no standard closing commit for an
  issue to look for in the history.
- The environment half on the runner is the same as Class 5b's of `validate-ci-gate.md` (full
  history and `origin/develop`), closed in Stage 1.2 by an A/B pair of real runs and guarded by
  `tests/unit/test_ci_workflow.py`; no separate pair of runs was made for this check.
- The names of the reserved commit and of the `stage_id` do not change (issue #12 non-goal).

## Implementation notes

- `scripts/check_stage_deps.py`, unit tests in `tests/unit/test_check_stage_deps.py` (git access
  injected; no test reads this repository's history, so the shallow mutation job is unaffected).
- `Makefile` `docs-check`; `docs/runbooks/validate-ci-gate.md` §Class 5c (the runbook's
  §Maintenance requires extending it when the gate hardens).
- Callers, after `git fetch origin`: `PROMPT-stage-single-session.md` pre-condition 5,
  `PROMPT-stage-single-session-autonomous.md` §4, `PROMPT-step-single-session.md` §"Abertura de
  cada Stage", `RUNBOOK-STAGE-LIFECYCLE.md` prerequisites.

## References

- Issue #12; PR #11 (findings F4 and F-C of its clean-context audit).
- [ADR 1.2.0001](./1_2_0001-deterministic-pr-path-gates.md) — deterministic PR-path gates.
- [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md) — the autonomous variant whose §4 this replaces.
- `docs/CONVENTIONS.md` §1 (identifier forms), §3 (issue-first is programmatic), §4(b) (reserved commits).
- `docs/GIT-WORKFLOW.md` §"Branches em execução"; `docs/PIPELINE.md` "Linearidade estrita";
  `docs/RUNBOOK-STAGE-LIFECYCLE.md` §Pré-requisitos.
- `docs/stages/1.2-ci/technical.md` §7 — finding "`check_stage_issue.py` é repo-global";
  `docs/stages/4.1-scheduling-domain/technical.md` §7 — the rebase after the 3.5 merge.

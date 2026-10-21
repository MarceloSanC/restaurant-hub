---
title: ADR 0.0.0007 — The Stage dependency check is a script that takes the stage_id and derives the commit number
description: Architecture Decision Record
when-use: Reference before checking whether a Stage's dependencies are closed, before writing a command that turns a depends_on value into a commit subject, or before changing what make docs-check enforces about Stage order
keywords: [adr, process, pipeline, depends_on, stage_id, reserved-commit, docs-check, placeholder, prompt]
status: accepted
created_at: 2026-10-21
updated_at: 2026-10-21
adr_id: "0.0.0007"
decision: The dependency pre-condition of a Stage (every Stage in depends_on is done in the roadmap and its reserved `stage N.M: complete` commit is in the history) is checked by scripts/check_stage_deps.py, which takes the stage_id and derives the number itself; make docs-check runs it over every Stage folder against HEAD, and `--ref origin/develop` gives the merged-in-develop variant on demand.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0007 — The Stage dependency check is a script that takes the stage_id

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

Decided in issue #12, whose scope asked for exactly this call: *"avaliar se vale um validador em
`scripts/` … decidir por ADR ou registrar como não-vale-a-pena"*.

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
   the same RUNBOOK prerequisite list and has no check at all.
4. **The order rule is not only the roadmap's.** GIT-WORKFLOW §"Branches em execução" lets two
   branches run in parallel only if "nenhuma depende da outra (roadmap 'Depende de' …)"; a Stage
   branch opened while its dependency is unfinished violates it. Today only discipline catches
   that — in this very run, the orchestrator checks it by hand for every front.
5. **Constraints a new gate must respect.** ADR 1.2.0001: no verdict decided on the network, and a
   check that reads git history must actually see it (`ci.yml` checks out with `fetch-depth: 0`);
   no silent degradation. Stage 1.2 §7 (finding on `check_stage_issue.py`): a repo-global check
   must not turn every PR red because of a *legitimate* transient state somewhere in the repo.
6. **History replay.** For each of the 14 Stage folders that have dependencies, the
   dependency's `stage N.M: complete` commit is an ancestor of the commit that created the folder.
   The rule the script enforces has held at every Stage start in this repository.

## Decision

1. **`scripts/check_stage_deps.py` takes the `stage_id` — never the number — and derives the
   number itself** (prefix up to the first hyphen: `1.1-bootstrap` → `1.1`). Given a bare number
   it refuses with an explanation (exit 2). This removes the hand conversion from every caller:
   the prompts pass the `stage_id` they already hold.
2. **The roadmap's *Tabela de Stages* is the single source** of `depends_on` and status: it
   exists for Stages that have no folder yet (a Stage being opened) and the canonical
   pre-condition already reads it. Columns are located by header name, not position.
3. **For each dependency the script requires:** a row in the table; a number that identifies only
   one row (otherwise `stage N.M: complete` cannot say which Stage closed); status `done`; and a
   commit whose subject is **exactly** `stage <N.M>: complete` reachable from `--ref` (exact
   subject, so `conceptual approved` and `stage 11.1: complete` never satisfy `1.1`).
4. **`make docs-check` runs it with no arguments**: the targets are the Stage folders in
   `docs/stages/` and the ref is `HEAD` — "what this branch carries", which is the canonical rule
   (deps done before the Stage opens) and is deterministic. A folder only exists after the skeleton
   commit, which is only legitimate once its dependencies closed; so, unlike the 3A placeholder of
   `check_stage_issue.py`, there is no legitimate state in which a folder reds unrelated PRs.
5. **`--ref origin/develop` is the merged-in-develop variant**, run on demand after `git fetch`
   where "closed" means "merged": the autonomous variant §4 and the Step master opening a Stage.
6. **Fail closed** (exit 2) when the verdict cannot be given: roadmap, section or columns missing,
   unresolvable ref, or a shallow clone (the reserved commits are simply not there — ADR 1.2.0001).

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
- **Why rejected:** the cost of wiring it is one Makefile line, and fact 6 shows the rule has never
  been legitimately broken here.

### Alternative C — `docs-check` against `origin/develop`
- **Description:** make the always-on check demand that every dependency is already merged.
- **Pros:** matches the autonomous variant's stricter rule and GIT-WORKFLOW's parallel rule.
- **Cons:** the verdict would depend on how fresh the local remote-tracking ref is — a dependency
  merged on GitHub but not yet fetched reds `make check` until `git fetch`. That is an
  environment-dependent verdict, which ADR 1.2.0001 rejects for the PR path.
- **Why rejected:** `HEAD` is deterministic; the stricter semantic stays available on demand (5).

### Alternative D — Read `depends_on` from the Stage's frontmatter
- **Description:** use `depends_on` in `technical.md`/`concept.md` instead of the roadmap row.
- **Pros:** the field sits next to the folder being checked.
- **Cons:** during phase 3A the frontmatter is still the template (`depends_on: []`), which would
  pass vacuously; and a Stage being opened has no frontmatter yet.
- **Why rejected:** the roadmap is where order is planned (CONVENTIONS §1 "Ordem de implementação
  = `depends_on`") and the only source that exists before the folder does.

### Alternative E — Do nothing / status quo
Leaves fact 1 and fact 2 standing: a prose check that has already failed both ways, and a
verification command that is green for a Stage that is not done.

## Consequences

### Positive

- The stage_id → number conversion lives in one tested place; every caller passes the `stage_id`.
- Opening a Stage before its dependencies closed turns `make check` red on that branch at the
  first run, instead of relying on whoever opened it.
- A roadmap that says `done` without the reserved commit — or the reverse — surfaces on the first
  Stage that depends on it.

### Negative

- One more script in `make docs-check`, and one more gate that needs full git history (already a
  requirement of `check_technical_postexec.py` check 2; `ci.yml` has `fetch-depth: 0`).
- A reverted `stage N.M: complete` commit still counts as present (its subject stays in the
  history). The status check covers it because the closing commit is the one that flips the
  roadmap row, so reverting it restores the row — unless the row is then edited back by hand.

### Neutral / trade-offs accepted

- With the default `HEAD`, a branch stacked on a dependency that is complete but not yet merged
  passes `docs-check`; only `--ref origin/develop` catches it. Accepted: stacking on a finished
  branch is a deliberate act, and the strict check is one flag away for the flows that require it.
- Issue dependencies (`#N` in the *Tabela de Issues*) are out of the script: checking them needs
  GitHub (network — ADR 1.2.0001) or the issue table's status, and they are glossed in the issue
  prompt instead.
- The names of the reserved commit and of the `stage_id` do not change (issue #12 non-goal).

## Implementation notes

- `scripts/check_stage_deps.py`, unit tests in `tests/unit/test_check_stage_deps.py` (git access
  injected; no test reads this repository's history, so the shallow mutation job is unaffected).
- `Makefile` `docs-check`; `docs/runbooks/validate-ci-gate.md` §Class 5 (the runbook's
  §Maintenance requires extending it when the gate hardens).
- Callers: `PROMPT-stage-single-session.md` pre-condition 5, `PROMPT-stage-single-session-autonomous.md`
  §4, `PROMPT-step-single-session.md` §"Abertura de cada Stage", `RUNBOOK-STAGE-LIFECYCLE.md`.

## References

- Issue #12; PR #11 (findings F4 and F-C of its clean-context audit).
- [ADR 1.2.0001](./1_2_0001-deterministic-pr-path-gates.md) — deterministic PR-path gates.
- [ADR 0.0.0004](./0_0_0004-autonomous-overnight-mode.md) — the autonomous variant whose §4 this replaces.
- `docs/CONVENTIONS.md` §1 (identifier forms), §3 (issue-first is programmatic), §4(b) (reserved commits).
- `docs/GIT-WORKFLOW.md` §"Branches em execução" (parallel branches must not depend on each other).
- `docs/stages/1.2-ci/technical.md` §7 — finding "`check_stage_issue.py` é repo-global".

---
title: ADR 0.0.0021 — A planned budget of 1 to 3 full gates per Stage replaces the full gate before every commit
description: Architecture Decision Record
when-use: Reference when writing the gate plan of a technical.md (Fase 3B), deciding what to run before a Task commit, adding a fourth full-gate point to a Stage, placing a gate point in a Stage that feeds a totality sweep, or before re-introducing a full gate on every commit or Task
keywords: [adr, process, gates, make-check, gate-plan, budget, totality-sweep, github-actions, docs-check, issue-163]
status: accepted
created_at: 2026-11-16
updated_at: 2026-11-16
adr_id: "0.0.0021"
decision: 'Each Task runs only its own tests (the test files it wrote or changed plus the totality sweeps its files feed) and the pre-commit hooks; the full `make check` must be green only at the 1 to 3 points per Stage that the gate plan in §1 of the technical.md names, the exit gate included, and a 4th point needs a written justification or becomes a `[deviation]`. A point is met by a local run or, under the orchestrator, by the Actions run of that commit. check_docs_pointers.py rejects the retired rule in the normative docs.'
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0021 — A planned budget of 1 to 3 full gates per Stage replaces the full gate before every commit

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — issue #163, item 7 of issue #65, approved by the sponsor on 2026-10-19.

Ported from the financial-forecasting repo (FF), which retired the same rule in its issues #110 and #185: FF decision record `0.0.0059` ("A planned budget of 1–3 full gates per Stage instead of a gate on every Task"), FF commits `93377c5d`, `1dd3c863`, `ef4349ed` and `6558cd0b`.

Does not change [ADR 0.0.0008](./0_0_0008-autonomous-orchestrator-parallel-worktrees.md): Decision 6 below says how a gate point is met under it.

## Context

`docs/PROMPT-stage-single-session.md` (Fase 4, step 5) set a baseline for every Task: the full `make check` green before the commit. `docs/RUNBOOK-STAGE-LIFECYCLE.md` Passo 9 ran `make check` before each Task commit, and `docs/PROMPT-step-single-session.md` repeated the rule in its phase table.

Three facts made the rule cost more than it returned:

- **Local cost.** On the Windows dev machine `make check` spawns hundreds of processes and the antivirus freezes the PC. Sessions that share one local Postgres get false `ERROR at setup` and deadlocks when two of them run the suite at once. A 12-Task Stage paid the full gate 12 times or more.
- **The rule was already not practiced in one mode.** ADR 0.0.0008 moved the full gate to GitHub Actions for orchestrated runs: the implementer runs focused checks locally and reads the verdict from the PR's run. The manual mode still carried the per-commit rule, so the prompt held a rule and an exception that swallowed it.
- **A fixed rule cannot tell a risky Task from a routine one.** The executor can, when it writes the plan: it knows which Tasks change a contract another bounded context reads, which ones edit gate configuration, and which ones only add a pure function and its unit tests.

FF met the same cost and replaced the rule with a planned budget. Two things differ here. This repo never had FF's intermediate tiers (`check-task`, `check-block`), so there is nothing to demote. And this repo has two things FF's decision did not have to deal with: the Actions mode of ADR 0.0.0008, and the totality sweeps.

**The totality sweeps are the conflict this ADR has to resolve.** Since Stage 3.6 the suite holds tests that derive a set from the code and compare it with a transcribed list:

- every subclass of a bounded context's error root × the HTTP status map (`test_status_map.py`, `test_http_error_handlers.py`);
- every module in a `use_cases/` folder × the composition-root container (`test_composition_root_staff.py`, `test_application_guards.py`);
- `router.routes` × the authorization overrides and the route tables (`test_composition_root_staff.py`, `test_http_boundary_sweeps.py`);
- the DTO modules × their field tables (`test_dtos.py`).

These tests reject any incremental change: a new error, use case, route or DTO without its entry turns red a test file that the Task neither wrote nor changed. Under the retired rule the full gate of each commit showed it. If a Task runs only the tests it wrote or changed, nothing shows it until the next full gate.

## Decision

1. **Per Task: only the Task's own tests.** Before each Task commit the executor runs the test files the Task wrote or changed, plus the totality sweeps its files feed (item 5), with `pytest <files> -q --no-cov`. The pre-commit hooks (ruff-format, ruff, mypy, import-linter) run on the commit as before. A red test blocks the commit. Another focused check (for example `check_layout.py` after creating a file in a new folder) is allowed when the Task has a concrete reason for it. It is not a routine step.
2. **A gate plan in the technical.md.** In Fase 3B the author writes a "Plano de gates" in §1 of the technical.md: a table of the Tasks after which the full `make check` must be green, with the reason for each. The technical gate (RUNBOOK Passo 7, Checkpoint B in the single-session prompt) reviews it.
3. **Budget: 1 to 3 points per Stage, the exit gate included.** The exit gate (RUNBOOK Passo 10) is always one of them. A 4th or later point needs a justification written in the plan: the concrete break that point catches, and why the next planned point would catch it too late. "To be safe" is not a justification. When the need shows up during execution, the extra point is recorded as a `[deviation]` in §7 with the same justification.
4. **Where a mid-Stage point goes.** Right after the last Task of a group whose break would invalidate the Tasks that follow. The groups are: a change to a port or contract read by another bounded context or layer; a change to `shared/` or to the composition root; a change to dependencies, tool configuration, gate scripts, a shared `conftest.py` or a migration; and the first Task that feeds a totality (item 5c). The author orders the Tasks so that these changes cluster and one point covers them. A Stage with none of them needs only the exit gate.
5. **Totality sweeps.**
   - (a) **Planned red stays forbidden.** A Task still carries, in the same commit, its entry in every totality its files feed: the new error goes with its line in the status map, the new use case with the container, the new route with its override and route-table rows. `docs/PIPELINE.md` §4.3 criterion 1 ("commitável de forma limpa") is unchanged. What this ADR accepts is accidental red between two points, not red by design.
   - (b) **The sweep is one of the Task's own tests.** The test files of the totalities a Task feeds go in that Task's verification command, next to the tests it wrote. Fase 3B maps them before cutting the Tasks. So the rejection of an incremental change is still seen at the commit, by a focused `pytest` and not by the full gate.
   - (c) **A totality is a reason to place a point.** A sweep the plan failed to map is red outside the Task's own tests, and every later Task of the same kind repeats the miss. When two or more Tasks feed the same totality, the first of them is a candidate mid-Stage point: the full gate there confirms the map before the pattern is replicated. The plan spends the budget on the totality whose miss would cost the most Tasks to redo.
6. **How a point is met.** A point is met when `make check` exits 0 on the commit of the point's Task. In the manual mode that is a local run. Under the orchestrator (ADR 0.0.0008, unchanged) it is the `lint-and-test` job green on the Actions run whose head is that commit, with no local `make check`. Under the orchestrator the implementer keeps pushing after every Task and Actions runs on every push, at no local cost. The budget counts the points where the executor must hold for the verdict before it starts the next Task. Between points it does not wait. A red run that shows up between points is fixed before the next Task, like any red gate.
7. **A red point** is fixed with a `fix(<scope>): ... [N.M/task-NN-fix]` commit before the next Task.
8. **Standalone issues** follow the same rule. An issue has no technical.md, so the plan is listed with the sub-tasks. The default is one point, the exit. An extra point that shows up during execution goes in the PR body as a `[deviation]`.
9. **`make check` stays the only verdict**, literally what CI runs ([ADR 2.3.0001](./2_3_0001-integration-tests-require-real-postgres.md)). The exit gates of a Stage are unchanged.
10. **Drift guard.** `scripts/check_docs_pointers.py`, wired in `make docs-check`, rejects the retired rule (the full gate tied to every commit or Task) in the normative docs, and fails if the two homes of the new rule lose their heading: `docs/PIPELINE.md` §9.6 and the "Plano de gates" slot of `docs/templates/stage-technical.md`.
11. **Transition.** The rule applies to Stages and issues whose branch is opened after this ADR merges into `develop`. Stages in flight at the merge (2.7, 3.11 and 4.4) finish under the prompt they started with: their technical.md has no gate plan and none is required of them.

The operational rules have a single source, `docs/PIPELINE.md` §9.6. `docs/CONVENTIONS.md` §0 makes PIPELINE the owner of phases and conceptual gates. The RUNBOOK, the prompts and the template point to it.

## Alternatives considered

### Alternative A — Keep the full gate before every commit (status quo)
- **Pros:** every commit is green on the whole suite; `git bisect` never lands on a commit that is red elsewhere.
- **Cons:** the local cost in Context, paid once per Task, on checks that rarely find anything new.
- **Why rejected:** ADR 0.0.0008 already rejected it for orchestrated runs (its Alternative B). Keeping it only in the manual mode keeps two regimes and a prompt whose exception is the common case.

### Alternative B — A fixed cadence (the full gate every N Tasks)
- **Pros:** no judgement needed, trivially checkable.
- **Cons:** spends the same budget on a Stage of pure functions as on one that rewires the composition root.
- **Why rejected:** placing the points by judgement, written down and reviewed, spends the budget where the risk is.

### Alternative C — Only the exit gate, never a mid-Stage point
- **Pros:** the cheapest possible plan.
- **Cons:** when a Task changes a contract that later Tasks build on, finding the break at the exit means several Tasks to redo.
- **Why rejected:** rejected as the rule, kept as the default for a Stage with none of the triggers of Decision 4.

### Alternative D — Let a totality stay red between two points
- **Description:** drop the "carry your entry" rule; a Task adds the error and a later Task adds the map line.
- **Pros:** smaller Tasks, pure inside-out order.
- **Cons:** a full gate inside the window is red by design, and a red by design cannot be told from a red by bug without reading the log. No point could be placed in the window, and under the orchestrator every push in it would be a red run.
- **Why rejected:** it trades a visible cost (a bigger Task) for an invisible one (gates that say nothing).

### Alternative E — Port FF's intermediate tiers (`check-task` per slice, `check-block` per block)
- **Pros:** a cheaper gate than `make check` between points.
- **Cons:** two more targets to keep equal to CI; FF itself stopped requiring them in the decision this ADR ports.
- **Why rejected:** the Task's own tests plus the mapped sweeps cover the same ground with no new target.

### Alternative F — Under the orchestrator, push only at the gate points
- **Pros:** the number of Actions runs equals the number of points.
- **Cons:** changes ADR 0.0.0008 item 3 (draft at the first push, a push per Task) and throws away verdicts that cost nothing locally.
- **Why rejected:** the scarce resource is the local machine and the time spent waiting, not Actions runs. The budget counts waits.

## Decision records

```
[decision:C] D1 — Which doc owns the operational rule of the gate plan?
Escolha: docs/PIPELINE.md §9.6 · Alternativas: a new RUNBOOK section (as in FF); the PROMPT-stage itself · Degrau (C): 1
Base: docs/CONVENTIONS.md §0, table "Classe de regra": "Hierarquia Step/Stage/Task, atomicidade, fases e gates conceituais" belongs to PIPELINE.md; the RUNBOOK owns only the gate checklists (Passos 5/7/10)
Verificado: não verificado (§4.2) — not a port, schema, OpenAPI contract or security rule
Configuração candidata: nenhuma · Reversível: sim
```

```
[decision:C] D2 — How is a gate point met when the full gate runs only on Actions?
Escolha: the Actions run of the point's commit meets it; pushes stay per Task; the budget counts waits · Alternativas: push only at the points (Alternative F); require a local run at the points · Degrau (C): 1
Base: ADR 0.0.0008 Decision 3: "Exit-gate evidence for `make check`/coverage is the Actions run"
Verificado: não verificado (§4.2) — same reason
Configuração candidata: nenhuma · Reversível: sim
```

```
[decision:C] D3 — Totality sweeps reject incremental change; per-Task tests would not run them
Escolha: the Task carries its entry and runs the mapped sweeps as its own tests; the first Task feeding a repeated totality is a candidate point · Alternativas: allow a red window closed by a point (Alternative D); a point after every Task that feeds a totality (breaks the budget) · Degrau (C): 1
Base: docs/PIPELINE.md §4.3 criterion 1: "Ser **commitável de forma limpa** (estado consistente entre commits)"
Verificado: não verificado (§4.2) — same reason
Configuração candidata: nenhuma · Reversível: sim
```

```
[decision:C] D4 — Where does the drift guard live?
Escolha: a new scripts/check_docs_pointers.py holding a table of retired phrasings and a table of required headings · Alternativas: a rule inside check_docs_claims.py (it checks the LAYOUT tree, another question); inside check_harness.py (being edited by issue #162) · Degrau (C): 1
Base: docs/CONVENTIONS.md §0, "Regra do eco", which already names `scripts/check_docs_pointers.py` as the mechanical guard to create; it is also the name of the FF script
Verificado: não verificado (§4.2) — same reason
Configuração candidata: nenhuma · Reversível: sim
```

`[decision] P delegado — adopt the gate budget as specified in issue #163, motivo: the sponsor approved item 7 of issue #65 on 2026-10-19; the adoption is not a fork. No other P fork came up.`

## Consequences

### Positive
- A Stage pays 1 to 3 full gates, not one per Task. In the manual mode the machine and the shared Postgres carry the full suite at most three times per Stage.
- The manual and the orchestrated modes follow one rule. They differ only in where the point's verdict comes from.
- The plan makes the risk assessment visible and reviewable at the technical gate.
- The totality sweeps stay a per-commit check, at the cost of a few focused test files.

### Negative
- A commit between two points can be red outside its own tests: a mypy error in a module that imports the changed one, a test in a bounded context the Task did not touch, a totality the plan failed to map. The next point catches it, and the fix may need a bisect over more commits than before. This trade is accepted on purpose.
- Commit-level green now means "the Task's own tests and the pre-commit hooks passed". `git bisect` on a feature branch may land on commits that are red elsewhere. The points, the exit gate and the merge are still green on the whole suite.
- The quality of the plan depends on the author's judgement. The budget cap and the justification rule make a bad plan visible. They do not prevent one.

### Neutral / trade-offs accepted
- No gate checks that a technical.md has a gate plan or that the plan has 1 to 3 points: the technical gate reviews it. A mechanical check would need a cut-off for the Stages approved before this ADR.
- The audit skills (`stage-audit`, `issue-audit`) do not yet read the gate plan. They are being reorganized by issue #162, so the change is left as a follow-up.

## References

- Issue #163; issue #65 (item 7).
- FF decision record `0.0.0059` and FF commits `93377c5d`, `1dd3c863`, `ef4349ed`, `6558cd0b` (financial-forecasting repo, issues #110 and #185): the origin.
- [ADR 0.0.0008](./0_0_0008-autonomous-orchestrator-parallel-worktrees.md): the full gate on Actions for orchestrated runs.
- [ADR 2.3.0001](./2_3_0001-integration-tests-require-real-postgres.md): the CI job runs literally `make check`.
- `docs/PIPELINE.md` §9.6: the operational single source. §4.3: the atomic-Task criteria.
- `docs/templates/stage-technical.md` §1 "Plano de gates".
- `scripts/check_docs_pointers.py`, `tests/unit/test_check_docs_pointers.py`.

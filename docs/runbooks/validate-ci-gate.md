---
title: Runbook — Validate the CI gate per error class
description: Step-by-step procedure to prove that each error class is rejected by the local `make check` gate (which is exactly what the CI workflow runs)
when-use: After hardening the CI gate (a new tool joins the chain); when auditing that the existing CI gate still rejects each error class; after an incident where a regression slipped past the gate
keywords: [runbook, ci, gate, validation, make-check, lint, fmt-check, typecheck, layout-check, import-check, lock-check, docs-check, test, coverage, fetch-depth, freeze-secao-7, depends-on]
status: accepted
created_at: 2026-06-23
updated_at: 2026-11-09
runbook_id: validate-ci-gate
triggers:
  - Hardening of the CI gate (new tool joining the chain — e.g., bandit, import-linter)
  - Audit of the existing CI gate per error class
  - Incident — a PR was merged despite broken X; validate the gate still works
estimated_duration: ~20min
---

# Runbook — Validate the CI gate per error class

> Runbooks are written and consumed in **English**. They describe operational procedures executed by humans or agents.

> This file is a **worked-example instance** of [`docs/templates/runbook.md`](../templates/runbook.md). It ships in the project template so that a new project starts with one fully fleshed-out runbook. Replace `restaurant_hub` with your package name and adjust the placeholder Stage path (`docs/stages/N.M-<slug>/technical.md`) to a real Stage once you have one.

## Purpose

Prove, **class by class**, that each error class enforced by the local `make check` gate produces a non-zero exit code, so the CI step `Run gate completo (lint + fmt-check + typecheck + layout-check + import-check + lock-check + docs-check + test-gate)` in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (which runs literally `make check`) rejects the broken state before merge.

The argument is transitive: if every class fails `make check` locally, every class fails `make check` on the runner. This runbook documents the local demonstration that closes that transitivity argument.

> **The transitivity argument has one precondition, and it is not free** (added in Stage 1.2 — [ADR 1.2.0001](../adr/1_2_0001-deterministic-pr-path-gates.md)). It holds only for checks whose inputs exist identically in both environments. A check that reads **git history** does *not* qualify under the runner's default shallow clone: `actions/checkout` defaults to `fetch-depth: 1`, which hides the baseline commit and makes such a check skip itself and **exit 0 — green because it did not look**. Stage 1.2 found exactly that in check 2 of `check_technical_postexec.py` and fixed it with `fetch-depth: 0` in `ci.yml`. When adding a class below, ask what its inputs look like on the runner before assuming transitivity carries it. See §Class 5b.

In this project, `make check` expands to the following target chain (see [`Makefile`](../../Makefile)):

```
check: lint fmt-check typecheck layout-check import-check lock-check docs-check test-gate
```

where `fmt-check` runs `ruff format --check` (formatting is checked, never applied — issue #99), `import-check` runs `lint-imports` (import-linter contracts in
[`.importlinter`](../../.importlinter)), `lock-check` runs `uv lock --check`
(lockfile drift), `test-gate` runs pytest with `--cov` over `src/`, `scripts/` and
`.claude/hooks/` and then one `coverage report` per part (the `fail_under = 90`
coverage gate fires inside `make check`, for each part — issue #91), and
`make docs-check` expands to:

```
docs-check:
	uv run python scripts/check_technical_postexec.py
	uv run python scripts/check_stage_issue.py
	uv run python scripts/check_adr_bounded_context.py
	uv run python scripts/check_docs_claims.py
	uv run python scripts/check_harness.py
	uv run python scripts/check_stage_deps.py
```

## Triggers

When to execute this runbook:
- A new gate is added to `make check` (audit the addition).
- Periodically, after major dependency upgrades (ruff, mypy, pytest), to confirm fingerprints still match.
- After an incident where a regression slipped past the gate (validate that the class involved still fails — or extend the gate to cover it).

## Prerequisites

- [ ] Working tree clean (`git status` empty).
- [ ] `make check` green on the current branch **before** starting (baseline).
- [ ] `.venv` installed and current (`make setup`).
- [ ] **PostgreSQL running** (`make docker-up`) — since Stage 2.3 the test gate
      requires a real database and does not skip without one (Class 10).
- [ ] Any environment with GNU Make 4+ — native Windows (PowerShell) included.
      Makefile recipes are shell-agnostic by project decision
      ([ADR 1.1.0001](../adr/1_1_0001-windows-native-dev-environment.md));
      the devcontainer remains a supported option, not a requirement.

## Procedure

For each class below: apply the patch, run the command, capture the output, compare with the expected fingerprint, **revert the patch**, confirm `git status` is clean before moving to the next class.

> **Rule:** never commit a broken-on-purpose patch. Apply → exercise → revert → next.

### Class 1 — `lint` (ruff check)

**Patch** (apply to `src/restaurant_hub/__init__.py`):
```python
import os  # broken-on-purpose: F401 unused-import
```

**Command:**
```bash
uv run ruff check src/restaurant_hub/__init__.py
```

**Expected output (fingerprint):**
```
src/restaurant_hub/__init__.py:N:1: F401 [*] `os` imported but unused
Found 1 error.
```
Exit code: **1**.

**Revert:**
```bash
git restore src/restaurant_hub/__init__.py
```

> **`migrations/` is in scope** (issue #99). `lint`, `fmt` and `fmt-check` name the same directories — every versioned `.py`, `migrations/` included — and `tests/unit/test_ci_workflow.py` fails if a versioned `.py` falls outside them. The same patch appended to `migrations/env.py` fails `make check` at the `lint` step (`F401`, plus `E402` because it lands after module code).

---

### Class 2 — `fmt-check` (ruff format --check)

> **Blocking since issue #99.** `fmt-check` runs right after `lint` in the `make check` chain and only *checks* formatting (`ruff format --check`); the `fmt` target is the one that *applies* it (`ruff format` + `ruff check --fix`). Before #99 only the `ruff-format` pre-commit hook formatted code, so a commit made with `--no-verify` (or from a worktree without the hook) reached the runner unformatted and passed. `tests/unit/test_ci_workflow.py` fails if `fmt-check` leaves the chain or loses `--check`. Freshly generated Alembic revisions already pass it: the post-write hook in `migrations/alembic.ini` formats them (guarded by `tests/unit/test_alembic_revision_template.py`).

**Patch** (apply to `src/restaurant_hub/__init__.py`):
```python
x=1  # broken-on-purpose: formatter wants `x = 1`
```

**Command:**
```bash
uv run ruff format --check src/restaurant_hub/__init__.py
```

**Expected output (fingerprint):**
```
Would reformat: src/restaurant_hub/__init__.py
1 file would be reformatted
```
Exit code: **1**.

Through the gate (`make check`, measured in issue #99), `lint` passes — `x=1` is not a lint error — and the chain stops at `fmt-check` before reaching `typecheck`:
```
Would reformat: src/restaurant_hub/__init__.py
1 file would be reformatted, N files already formatted
make: *** [Makefile:N: fmt-check] Error 1
```

**Revert:**
```bash
git restore src/restaurant_hub/__init__.py
```

---

### Class 3 — `typecheck` (mypy --strict)

**Patch** (apply to `src/restaurant_hub/__init__.py`):
```python
def add(a, b):  # broken-on-purpose: no type annotations under --strict
    return a + b
```

**Command:**
```bash
uv run mypy src/restaurant_hub/__init__.py
```

**Expected output (fingerprint):**
```
src/restaurant_hub/__init__.py:N: error: Function is missing a type annotation  [no-untyped-def]
Found 1 error in 1 file (checked 1 source file)
```
Exit code: **1**.

**Revert:**
```bash
git restore src/restaurant_hub/__init__.py
```

> Since issue #91 `make typecheck` runs `mypy src/ tests/fakes/ scripts/ .claude/hooks/`, so the same patch appended to a script (e.g. `scripts/clean.py`) fails the gate as well — measured: `uv run mypy src/ tests/fakes/ scripts/ .claude/hooks/` → `scripts\clean.py:67: error: Function is missing a type annotation  [no-untyped-def]`, exit **1**. `tests/unit/test_ci_workflow.py` keeps every versioned `.py` outside `tests/` (except `tests/fakes/`) and `migrations/` inside the target.

---

### Class 4 — `layout-check` (`scripts/check_layout.py`)

The script enforces the dependency rules from [`LAYOUT.md`](../LAYOUT.md) §3: `domain/` may only import from stdlib and other `domain/` modules — never from `infrastructure/`.

**Patch** (create a new file):
```bash
cat > src/restaurant_hub/shared/domain/_temp_violation.py <<'EOF'
"""Broken-on-purpose: domain importing infrastructure (LAYOUT.md §3 violation)."""
from restaurant_hub.shared.infrastructure.config.settings import Settings  # noqa
EOF
```

**Command:**
```bash
uv run python scripts/check_layout.py
```

**Expected output (fingerprint):** an error from `check_layout.py` mentioning the offending file and the layer violation. In this template the message takes the form:
```
VIOLAÇÃO: restaurant_hub/shared/domain/_temp_violation.py importa 'restaurant_hub.shared.infrastructure.config.settings' (proibido para camada 'domain')
```
The exact wording is implementation-specific; the script must surface (a) the offending file and (b) the rule violated. Exit code: **1**.

**Revert:**
```bash
rm src/restaurant_hub/shared/domain/_temp_violation.py
```

---

### Class 5 — `docs-check` (`check_technical_postexec.py` + `check_stage_issue.py` + `check_adr_bounded_context.py`)

`make docs-check` runs its scripts in sequence (§Purpose); the first to exit non-zero fails the gate. This class covers three of them; `check_stage_deps.py` has its own class (§Class 5c).

1. **`check_technical_postexec.py`** enforces, on every `technical.md`:
   - **Structural (always):** exactly one `<!-- BEGIN: post-execution -->` marker and exactly one `<!-- END: post-execution -->` marker, with END after BEGIN.
   - **Diff vs baseline (only when `status: done` and the Stage has a reserved `stage N.M: technical approved` commit):** content outside the markers must match that approved baseline. If no approval commit exists in history (Stage still in 3A/3B, or no Stage yet), check 2 is skipped by design.
2. **`check_stage_issue.py`** requires every Stage `technical.md` to carry a valid `issue_id` that resolves via `gh issue view`. It is **best-effort**: if `gh` is not installed or not authenticated it prints WARN and returns 0, so it is not a reliable local trigger without `gh`.
3. **`check_adr_bounded_context.py`** requires every ADR to carry a `bounded_context` whose value belongs to the set declared in the roadmap (`transversal` for global `0_0_*`/`1_1_*` ADRs).

The **structural check** of `check_technical_postexec.py` is the most direct, environment-independent trigger — break a marker and the script flags it regardless of file status and regardless of whether `gh` is available.

> **Note (template placeholder):** a fresh template has no `docs/stages/N.M-<slug>/technical.md` yet, so there is nothing to break until your first Stage exists. Substitute a real Stage path below once you have one (e.g. `docs/stages/1.1-bootstrap/technical.md`). If you want to confirm the script wiring before any Stage exists, run `uv run python scripts/check_technical_postexec.py` against a hand-made `technical.md` derived from [`docs/templates/`](../templates/) and break a marker in that.

**Patch:** comment out the `END: post-execution` marker in a Stage's `technical.md` (last marker line near the end of the file). Example: replace `<!-- END: post-execution -->` with `<!-- broken END -->` in `docs/stages/N.M-<slug>/technical.md`.

**Command:**
```bash
uv run python scripts/check_technical_postexec.py
```

**Expected output (fingerprint):**
```
docs/stages/N.M-<slug>/technical.md: marcadores de §7 inválidos — esperava 1 BEGIN e 1 END, encontrei 1 BEGIN e 0 END.
```
Exit code: **1**.

**Revert:**
```bash
git restore docs/stages/N.M-<slug>/technical.md
```

---

### Class 5b — `docs-check` / §7 freeze (`check_technical_postexec.py` **check 2**)

> Added in **Stage 1.2** ([ADR 1.2.0001](../adr/1_2_0001-deterministic-pr-path-gates.md)). Class 5 above exercises the **structural** check, which is environment-independent. Check 2 — the diff-vs-baseline that actually enforces the §7 freeze (CONVENTIONS §3.4) — is a different animal: **its input is git history**, and it was silently skipped on every CI run until Stage 1.2. It needs its own class.

**This class has two preconditions.** Neither is optional; if either is missing, the check exits 0 and the class proves nothing:

1. **Full git history.** Check 2 locates the baseline via `git log --format=%H%x09%s -- <path>` looking for the subject `stage N.M: technical approved`, and calls `git merge-base --is-ancestor <baseline> origin/develop` to decide whether the Stage already merged. Under a shallow clone both fail open (`_approved_commit_for()` → `None`; no integration ref resolves). On the runner this means **`fetch-depth: 0` in [`ci.yml`](../../.github/workflows/ci.yml)** — the default `fetch-depth: 1` disables this class entirely.
2. **An eligible target.** The freeze only bites for a Stage that is `status: done` **and not yet merged** (CONVENTIONS §3.4 — the execution window). A Stage in 3A/3B has no baseline (legitimately skipped), and a **merged** Stage is skipped by `_stage_is_merged()`. So you cannot exercise this class against `1.1-bootstrap` or any other merged Stage: it is skipped in *both* worlds and the A/B proves nothing.

**Patch** (apply to a `technical.md` that is `done` and not merged — the Stage currently in flight): edit any line **outside** the `BEGIN/END: post-execution` markers, e.g. change the `# Technical — …` title line.

**Command:**
```bash
uv run python scripts/check_technical_postexec.py docs/stages/N.M-<slug>/technical.md
```

**Expected output (fingerprint):**
```
docs/stages/N.M-<slug>/technical.md: status=done mas há mudanças fora dos marcadores post-execution (baseline: 9761ea38 `stage technical approved`):
  replace: baseline[4:5] (lines 5-5) vs current[4:5] (lines 5-5)
```
Exit code: **1**.

**Local proof that the environment — not the patch — is the variable** (Stage 1.2; same patch on both sides, synthetic Stage `done` and not merged):

| Clone | `git log` sees baseline? | Result |
|---|---|---|
| full history (simulates `fetch-depth: 0`) | yes | **exit 1** — freeze fires |
| `git clone --depth 1` (simulates `fetch-depth: 1`) | no | **exit 0** — passes silently |

The table says *simulates* on purpose: `fetch-depth` is an `actions/checkout` input, and this demonstration never ran the action. It closes the mechanism, not the environment.

**Revert:**
```bash
git restore docs/stages/N.M-<slug>/technical.md
```

> **Local exit codes do not close this class.** Unlike Classes 1–9, the local demonstration proves only the *mechanism*; the runner's `pull_request` event checks out `refs/pull/N/merge`, not a local clone. The environment half is closed only by an **A/B pair of real runs** on a throwaway PR — the same patch, green under `fetch-depth: 1` and red under `fetch-depth: 0`. The recorded evidence (run links) lives in §7 of [`docs/stages/1.2-ci/technical.md`](../stages/1.2-ci/technical.md). Re-do that pair if `ci.yml`'s checkout, or the baseline-lookup logic, ever changes.

---

### Class 5c — `docs-check` / Stage dependency pre-condition (`check_stage_deps.py`)

> Added in **issue #12** ([ADR 0.0.0009](../adr/0_0_0009-stage-dependency-check-derives-the-number.md)). For every Stage folder in `docs/stages/`, each Stage listed under `Depende de` in its row of the roadmap's *Tabela de Stages* must be `done` there **and** have its reserved commit `stage N.M: complete` merged into an integration branch (`origin/develop`, `develop`, `origin/main`, `main` — whichever resolve, the same ones `check_technical_postexec.py` uses); a commit reachable only from `HEAD` (a branch stacked on an unmerged dependency) does not count. An issue dependency (`#N`) must be `done` in the *Tabela de Issues*, on exactly one row. The script takes the `stage_id` and derives the number itself (`1.1-bootstrap` → `stage 1.1: complete`) — the conversion that, done by hand, produced both a false green and a false HALT (PR #11).

**Environment precondition — git history.** The input is git history, as in Class 5b, but a shallow clone never makes this check silently green. With an explicit target (`check_stage_deps.py <stage_id>`, the pre-condition of whoever opens a Stage) a shallow clone, no resolvable integration branch or a git that does not run exits **2** (fail closed). Without a target (the `docs-check` call) the roadmap status is still checked and the missing history becomes a `WARN` on stdout — the local `make check` must not require full history (ADR 1.2.0001). In CI the history exists: `fetch-depth: 0` in [`ci.yml`](../../.github/workflows/ci.yml), locked by `tests/unit/test_ci_workflow.py`, is what lets the commit half give a verdict. So the environment half needs no A/B pair of runs: a shallow CI checkout would show the `WARN` line in the log, never a false green on the commit half.

**Patch:** in `docs/roadmap.md`, *Tabela de Stages*, change the `Status` of a Stage that some Stage folder depends on from `done` to `review` — e.g. the `1.1-bootstrap` row, on which the `1.2-ci` folder depends.

**Command:**
```bash
uv run python scripts/check_stage_deps.py
```

**Expected output (fingerprint):**
```
check_stage_deps: FALHA — 1 violação(ões):
  1.2-ci → 1.1-bootstrap: status `review` na Tabela de Stages (esperado `done`)
```
Exit code: **1** (followed by a two-line explanation of the number on stderr).

A second, patch-free trigger for the conversion itself: `uv run python scripts/check_stage_deps.py 1.2` exits **2** — the target is the `stage_id`, never the bare number.

**Revert:**
```bash
git restore docs/roadmap.md
```

---

### Class 6 — `test` (pytest)

**Patch:** edit [`tests/test_smoke.py`](../../tests/test_smoke.py), changing the bootstrap smoke test so it fails. The shipped test only asserts that `import restaurant_hub` succeeds; force a failure by adding a failing assertion to its body, e.g.:
```python
def test_package_imports() -> None:
    """Marcador: se a coleta do pytest chegou aqui, o import top-level passou."""
    assert False  # broken-on-purpose
```

**Command:**
```bash
uv run pytest tests/test_smoke.py -v
```

**Expected output (fingerprint):**
```
FAILED tests/test_smoke.py::test_package_imports - assert False
```
Exit code: **1**.

**Revert:**
```bash
git restore tests/test_smoke.py
```

---

### Class 7 — `coverage` (`make test-gate`, fail_under inside `make check`)

The coverage gate is configured in [`pyproject.toml`](../../pyproject.toml) `[tool.coverage.report] fail_under = 90` and fires inside `make check` via the `test-gate` target: one pytest run with `--cov` over `src/restaurant_hub`, `scripts/` and `.claude/hooks/`, then `coverage report --include="src/*"` and `coverage report --include="scripts/*,.claude/hooks/*"` (issue #91). Each part is held to the threshold on its own, so tooling below 90 % cannot hide behind `src/`, nor the reverse. A coverage drop below 90 % in either part causes a non-zero exit, which fails the gate.

**Patch** (drop a tested block — move the shared-kernel unit tests out of the collection root temporarily so coverage falls):
```powershell
Move-Item tests/unit/shared $env:TEMP/_shared_tests_bak
```

**Command:**
```bash
make test-gate
```

**Expected output (fingerprint):**
```
FAIL Required test coverage of 90.0% not reached. Total coverage: N%
```
Exit code: non-zero (pytest coverage failure; observed 54.37% when exercised in Stage 1.1).

**Revert:**
```powershell
Move-Item $env:TEMP/_shared_tests_bak tests/unit/shared
```

When the suite total still clears 90 % but one part does not, pytest passes and the failing `coverage report` prints instead:
```
Coverage failure: total of N is less than fail-under=90
```

> The `90` threshold must match `fail_under` in `pyproject.toml`. If the project raises or lowers the coverage gate, update the fingerprint in this class. Note: removing a single small test file may not drop coverage below 90 % — the patch must remove a block large enough to cross the threshold.

---

### Class 8 — `import-check` (import-linter contracts)

[`.importlinter`](../../.importlinter) mirrors the import rules of [`LAYOUT.md`](../LAYOUT.md) §3 (layers of `shared`, domain/application purity, shared not importing features). `make import-check` runs `lint-imports`; the same check runs as a pre-commit hook.

**Patch** (create a new file):
```powershell
Set-Content -Path src/restaurant_hub/shared/domain/_temp_violation.py -Value 'from restaurant_hub.shared.infrastructure.config.settings import Settings  # noqa: F401'
```

**Command:**
```bash
uv run lint-imports
```

**Expected output (fingerprint):**
```
restaurant_hub.shared.domain is not allowed to import restaurant_hub.shared.infrastructure:
-   restaurant_hub.shared.domain._temp_violation -> restaurant_hub.shared.infrastructure.config.settings (l.1)
Contracts: 2 kept, 2 broken.
```
Exit code: **1**. Note: this single patch breaks **two** contracts at once —
`shared-layers` (layers) and `domain-purity` (forbidden, which also reports
the transitive chain to `pydantic_settings`) — so the summary line says
`2 broken`, not `1 broken`.

**Revert:**
```powershell
Remove-Item src/restaurant_hub/shared/domain/_temp_violation.py
```

---

### Class 9 — `lock-check` (uv.lock drift)

`make lock-check` runs `uv lock --check`, which fails when `uv.lock` no longer matches `pyproject.toml` (a dependency was added/changed without regenerating the lock in the same commit — CONVENTIONS §5).

**Patch:** add a throwaway dependency to `pyproject.toml` `[project] dependencies` (e.g. `"six>=1.0"`) **without** running `uv lock`/`uv sync`.

**Command:**
```bash
make lock-check
```

**Expected output (fingerprint):**
```
Resolved N packages in Xms
error: The lockfile at `uv.lock` needs to be updated, but `--check` was provided.
```
Exit code: **1**.

**Revert:**
```bash
git restore pyproject.toml
```

---

### Class 10 — `integration` (real PostgreSQL required by the test gate)

Added in **Stage 2.3** ([ADR 2.3.0001](../adr/2_3_0001-integration-tests-require-real-postgres.md)). From that Stage on, `make check` → `test-gate` runs integration tests that exercise the Postgres adapters against a **real database**. They do **not** skip when the database is unreachable — they fail loudly, and there is deliberately no environment variable that turns the requirement off.

> **Environment precondition — read before trusting this class.** Unlike Classes 1–4 and 6–9, whose inputs are identical on a laptop and on the runner, this class needs a **service that must exist in both environments**. Locally it comes from `docker-compose.yml` (`make docker-up`); on the runner it comes from the `services: postgres` block in [`ci.yml`](../../.github/workflows/ci.yml). The local exit code below therefore does **not**, on its own, close the transitivity argument for this class — the runner half is closed by `tests/unit/test_ci_workflow.py`, which asserts that the gate job declares both the service and `DATABASE_URL`, so deleting either turns `make check` red *locally*. This is the same lesson as Class 5b, generalised: **a class whose inputs differ between environments needs its environment half verified separately, not assumed.**

**Patch A — database absent** (proves the suite fails instead of skipping):
```bash
docker compose stop postgres
```

**Command:**
```bash
uv run pytest tests/integration -q
```

**Expected output (fingerprint):** a hard failure naming the unreachable database and telling the operator how to fix it — never `s` (skipped) and never a green summary:
```
… Postgres não está acessível em postgresql+psycopg://…
… Suba o banco com `make docker-up`. Os testes de integração desta Stage não se pulam (ADR 2.3.0001).
```
Exit code: **non-zero**.

**Revert:**
```bash
docker compose start postgres
```

**Patch B — service removed from CI** (proves the runner half is guarded):
```bash
# delete the `services:` block (or the `DATABASE_URL` under `env:`) from
# .github/workflows/ci.yml
```

**Command:**
```bash
uv run pytest tests/unit/test_ci_workflow.py -q
```

**Expected output (fingerprint):**
```
o job de gate precisa de um service `postgres`: … Ver ADR 2.3.0001.
```
Exit code: **1**.

**Revert:**
```bash
git restore .github/workflows/ci.yml
```

---

## Verification (cumulative)

After exercising all ten classes individually, run the full gate **without any patch** to confirm baseline is green (with Postgres up — see Class 10):

```bash
git status              # must be clean
make check              # must exit 0
```

If `make check` is green and each class individually produced a non-zero exit code, the transitivity argument is closed **for every class whose inputs are identical on the runner**: the CI step `Run gate completo (lint + fmt-check + typecheck + layout-check + import-check + lock-check + docs-check + test-gate)` runs exactly `make check`, so every such class fails on the runner as well.

**Class 5b is the exception that proves the rule** — its input is git history, which the runner does *not* reproduce by default. Its local demonstration does **not** transfer on its own; it transfers only because `ci.yml` pins `fetch-depth: 0`. If that line is ever removed, Class 5b goes green on the runner without anyone noticing, and this §Verification silently overstates what it proved.

**Class 5c reads git history too, but fails the other way**: without `fetch-depth: 0` it exits **2** on the runner (shallow clone detected), so the same removal turns every PR red instead of hiding anything.

## Rollback

If a patch was committed by accident:

1. **Inspect the diff:**
   ```bash
   git show HEAD
   ```
2. **Revert the commit (preferable; preserves history):**
   ```bash
   git revert HEAD
   ```
3. **If the commit was the most recent and not yet pushed**, alternative: drop it:
   ```bash
   git reset --soft HEAD~1   # keep changes staged
   git restore --staged .    # unstage
   git restore .             # discard
   ```

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| The patch triggers an error in a *different* class than expected (e.g., the type-error patch is also flagged by lint). | Patch is too broad; multiple linters react. | Use the minimal patch listed in this runbook; do not improvise broader patches. |
| `make check` fails on baseline (before any patch). | Working tree drift, or a previous patch was not reverted. | `git status` first; `git restore .` to discard any leftover changes; re-run `make check`. |
| `check_technical_postexec.py` does not flag an edit **outside** the markers in a `status: done` file. | Expected when the Stage has no reserved `stage N.M: technical approved` commit in history: check 2 is scoped to the execution window, so without that baseline only the structural check runs. | Exercise Class 5 via the **structural** check (break a marker — see §Procedure Class 5 above), which fires regardless of status. |
| Check 2 does not flag an out-of-markers edit **on the runner**, though it flags it locally. | The clone is shallow: `actions/checkout` defaults to `fetch-depth: 1`, so the baseline commit and `origin/develop` are invisible and check 2 fails open (exit 0). Fixed in Stage 1.2. | Confirm `ci.yml` still pins `fetch-depth: 0` on the `lint-and-test` checkout (ADR 1.2.0001). If it was dropped, the class is disabled repo-wide and silently — see §Class 5b. |
| Check 2 is skipped even with full history. | The target Stage is already **merged** (`_stage_is_merged()` → skip: the freeze only covers the execution window) or is still in 3A/3B (no baseline yet). | Expected. Use a Stage that is `done` and not merged — see §Class 5b precondition 2. |
| `check_stage_issue.py` prints `WARN — gh não disponível` and returns 0. | `gh` is not installed or not authenticated. | Expected locally without `gh`. To exercise this sub-check, install `gh` and run `gh auth login`; otherwise rely on the `check_technical_postexec.py` structural break as the Class 5 trigger. |
| Class 6 patch flagged by `ruff` (lint) before reaching `pytest`. | If `make check` runs `lint` first and exits on it, you won't see `pytest` fail. | Run `uv run pytest tests/test_smoke.py -v` directly (as listed in this runbook) instead of the full `make check`. |
| Fingerprint differs from the runbook (different line number, slightly different wording). | Tool was upgraded; line numbers shift as files evolve. | Match on **rule code** (`F401`, `[no-untyped-def]`, etc.) and **exit code**, not on the exact line number. Update the runbook if a fingerprint drifts materially. |

## Maintenance

When a future Stage **hardens** the CI gate, this runbook MUST be extended in the same Stage. Examples:

- **New tool joins `make check`** (e.g., `bandit`, `safety`, `pip-audit`): add a new §Class N section in §Procedure, in the order in which `make check` runs it, with the four-part shape (patch / command / expected output / revert). (Done in Stage 1.1 for `import-check` — §Class 8 — and `lock-check` — §Class 9.)
- **A check's inputs differ between laptop and runner** (git history, network, filesystem layout): the class needs its **environment precondition** written next to the patch, and its local exit code does **not** close the transitivity argument on its own — say so explicitly, and close the environment half with real runs whose links are recorded in the Stage's §7. (Added in Stage 1.2 for the §7 freeze — §Class 5b — whose input is git history and which required `fetch-depth: 0` in `ci.yml`.) The generalisation worth remembering: **a class this runbook cannot trigger locally is not automatically a class the CI enforces** — verify, do not assume.
- **`scripts/check_layout.py` and `import-linter` coexist** by decision of Stage 1.1 (concept §6 — defense in depth): §Class 4 exercises the script, §Class 8 the contracts. If one ever replaces the other, merge the two classes.
- **`fmt-check` promoted to a blocking target**: done in issue #99 — §Class 2 and the chain in §Purpose updated. A new directory with Python joins `lint`, `fmt` and `fmt-check` together (`tests/unit/test_ci_workflow.py` enforces it).
- **Coverage gate** (`fail_under` in `pyproject.toml`): if the threshold or coverage tool changes, update §Class 7's command and fingerprint accordingly.

- **A gate requires an external service** (database, cache, broker): the class needs
  its **environment precondition** stated next to the patch *and* a mechanical guard
  that the service is declared in `ci.yml` — the local exit code alone cannot close
  the transitivity argument. (Done in Stage 2.3 for PostgreSQL — §Class 10 — guarded
  by `tests/unit/test_ci_workflow.py`.)

Update `updated_at` in the frontmatter and reference the hardening Stage in the body of the new subsection.

## Related

- CI workflow: [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- Local gate definition: [`../../Makefile`](../../Makefile) (target `check`)
- Coverage gate config: [`../../pyproject.toml`](../../pyproject.toml) (`[tool.coverage.report]`)
- Layer rules: [`../LAYOUT.md`](../LAYOUT.md) §3
- PR gates: [`../GIT-WORKFLOW.md`](../GIT-WORKFLOW.md) §Gates
- Runbook template: [`../templates/runbook.md`](../templates/runbook.md)
- Validators: [`../../scripts/check_layout.py`](../../scripts/check_layout.py), [`../../scripts/check_technical_postexec.py`](../../scripts/check_technical_postexec.py), [`../../scripts/check_stage_issue.py`](../../scripts/check_stage_issue.py), [`../../scripts/check_stage_deps.py`](../../scripts/check_stage_deps.py)

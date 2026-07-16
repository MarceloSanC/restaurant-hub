---
title: Runbook — Validate the CI gate per error class
description: Step-by-step procedure to prove that each error class is rejected by the local `make check` gate (which is exactly what the CI workflow runs)
when-use: After hardening the CI gate (a new tool joins the chain); when auditing that the existing CI gate still rejects each error class; after an incident where a regression slipped past the gate
keywords: [runbook, ci, gate, validation, make-check, lint, fmt-check, typecheck, layout-check, import-check, lock-check, docs-check, test, coverage]
status: accepted
created_at: 2026-06-23
updated_at: 2026-07-14
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

Prove, **class by class**, that each error class enforced by the local `make check` gate produces a non-zero exit code, so the CI step `Run gate completo (lint + typecheck + layout-check + tests)` in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (which runs literally `make check`) rejects the broken state before merge.

The argument is transitive: if every class fails `make check` locally, every class fails `make check` on the runner. This runbook documents the local demonstration that closes that transitivity argument.

In this project, `make check` expands to the following target chain (see [`Makefile`](../../Makefile)):

```
check: lint typecheck layout-check import-check lock-check docs-check test-gate
```

where `import-check` runs `lint-imports` (import-linter contracts in
[`.importlinter`](../../.importlinter)), `lock-check` runs `uv lock --check`
(lockfile drift), `test-gate` runs pytest with `--cov` (the `fail_under = 90`
coverage gate fires inside `make check`), and `make docs-check` expands to:

```
docs-check:
	uv run python scripts/check_technical_postexec.py
	uv run python scripts/check_stage_issue.py
	uv run python scripts/check_adr_bounded_context.py
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

---

### Class 2 — `fmt-check` (ruff format --check)

> **Note:** unlike `lint`/`typecheck`/etc., the formatter check is **not** a standalone target in this template's `make check` chain — the `fmt` target *applies* formatting (`ruff format` + `ruff check --fix`) rather than checking it. The class is kept here because `ruff format --check` is the canonical way to prove the formatter rejects unformatted code, and a project that promotes formatting to a blocking gate (adding `ruff format --check` to `check`) should validate it with exactly this patch. Exercise it directly via the command below.

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

`make docs-check` runs three scripts in sequence; the first to exit non-zero fails the gate.

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

The coverage gate is configured in [`pyproject.toml`](../../pyproject.toml) `[tool.coverage.report] fail_under = 90` and fires inside `make check` via the `test-gate` target (pytest with `--cov`). A coverage drop below 90 % causes a non-zero exit, which fails the gate.

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

## Verification (cumulative)

After exercising all nine classes individually, run the full gate **without any patch** to confirm baseline is green:

```bash
git status              # must be clean
make check              # must exit 0
```

If `make check` is green and each class individually produced a non-zero exit code, the transitivity argument is closed: the CI step `Run gate completo (lint + typecheck + layout-check + tests)` runs exactly `make check`, so every class fails on the runner as well.

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
| `check_stage_issue.py` prints `WARN — gh não disponível` and returns 0. | `gh` is not installed or not authenticated. | Expected locally without `gh`. To exercise this sub-check, install `gh` and run `gh auth login`; otherwise rely on the `check_technical_postexec.py` structural break as the Class 5 trigger. |
| Class 6 patch flagged by `ruff` (lint) before reaching `pytest`. | If `make check` runs `lint` first and exits on it, you won't see `pytest` fail. | Run `uv run pytest tests/test_smoke.py -v` directly (as listed in this runbook) instead of the full `make check`. |
| Fingerprint differs from the runbook (different line number, slightly different wording). | Tool was upgraded; line numbers shift as files evolve. | Match on **rule code** (`F401`, `[no-untyped-def]`, etc.) and **exit code**, not on the exact line number. Update the runbook if a fingerprint drifts materially. |

## Maintenance

When a future Stage **hardens** the CI gate, this runbook MUST be extended in the same Stage. Examples:

- **New tool joins `make check`** (e.g., `bandit`, `safety`, `pip-audit`): add a new §Class N section in §Procedure, in the order in which `make check` runs it, with the four-part shape (patch / command / expected output / revert). (Done in Stage 1.1 for `import-check` — §Class 8 — and `lock-check` — §Class 9.)
- **`scripts/check_layout.py` and `import-linter` coexist** by decision of Stage 1.1 (concept §6 — defense in depth): §Class 4 exercises the script, §Class 8 the contracts. If one ever replaces the other, merge the two classes.
- **`fmt-check` promoted to a blocking target** (adding `ruff format --check` to `check`): upgrade the note in §Class 2 and add the target to the chain documented in §Purpose.
- **Coverage gate** (`fail_under` in `pyproject.toml`): if the threshold or coverage tool changes, update §Class 7's command and fingerprint accordingly.

Update `updated_at` in the frontmatter and reference the hardening Stage in the body of the new subsection.

## Related

- CI workflow: [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- Local gate definition: [`../../Makefile`](../../Makefile) (target `check`)
- Coverage gate config: [`../../pyproject.toml`](../../pyproject.toml) (`[tool.coverage.report]`)
- Layer rules: [`../LAYOUT.md`](../LAYOUT.md) §3
- PR gates: [`../GIT-WORKFLOW.md`](../GIT-WORKFLOW.md) §Gates
- Runbook template: [`../templates/runbook.md`](../templates/runbook.md)
- Validators: [`../../scripts/check_layout.py`](../../scripts/check_layout.py), [`../../scripts/check_technical_postexec.py`](../../scripts/check_technical_postexec.py), [`../../scripts/check_stage_issue.py`](../../scripts/check_stage_issue.py)

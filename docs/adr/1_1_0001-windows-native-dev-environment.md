---
title: ADR 1.1.0001 — Windows-native development environment (revokes the template's POSIX-only assumption)
description: Architecture Decision Record
when-use: Reference whenever revisiting how the local dev environment works on Windows, before changing Makefile recipes, or when onboarding a new machine
keywords: [adr, windows, make, msys2, uv, makefile, posix, dev-environment]
status: accepted
created_at: 2026-07-14
updated_at: 2026-07-15
adr_id: 1.1.0001
decision: Support Windows-native development as the first-class environment — GNU Make (MSYS2) reachable via the user's global PATH, uv with UV_SYSTEM_CERTS in versioned Claude settings, and shell-agnostic Makefile recipes — revoking the template's POSIX-only assumption
context_stage: 1.1-bootstrap
bounded_context: transversal
---

# ADR 1.1.0001 — Windows-native development environment

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

The scaffolding comes from `whaka-dev-project-template`, which declared
`make` POSIX-only: the README and `docs/runbooks/validate-ci-gate.md`
prescribed devcontainer or WSL as the only supported paths on Windows.
This project, however, is developed **100% on native Windows**
(sponsor's decision — solo development on a Windows 11 machine).

Facts established during the readiness analysis (issue #1, comment of
2026-07-12):

- GNU Make 4.4.1 is installed at `C:\msys64\usr\bin\make.exe` but is
  **not on the PATH** — an older Make 3.81 (GnuWin32, 2006) also exists
  on disk and must not be picked up.
- With `C:\msys64\usr\bin` on the PATH, `sh.exe` becomes available and
  the POSIX recipes run unmodified; without it, Make falls back to
  `cmd.exe` and recipes using `printf`, `find`, `rm -rf`, `if [ -f ]`
  break.
- `uv` cannot reach PyPI on this machine without `UV_SYSTEM_CERTS=1`
  (`invalid peer certificate: UnknownIssuer`); `UV_NATIVE_TLS` is
  deprecated.

One additional fact was established **after** that comment, in a working
session of 2026-07-12 (recorded in the project's session memory, not in
the issue): MSYS2 ships its **own `git.exe`**, and when
`C:\msys64\usr\bin` is resolved *before* Git for Windows — as the issue
comment originally suggested via prepend — `git diff` reports ~2900
phantom CRLF lines across 29 untouched files. PATH ordering is therefore
load-bearing, and this ADR **revises the comment's prepend suggestion to
append/last position**.
- Git Bash is not viable as the driving shell: the MSYS2 `sh` loses
  `TEMP`/`TMP` and `uv` fails with `Acesso negado (os error 5)`.
- `make check` **has closed green (EXIT=0)** on native Windows with the
  manual recipe (PATH + `UV_SYSTEM_CERTS` + `uv sync --extra dev`) — the
  problem is that nothing of it was automated or documented.

## Decision

Windows-native development is the supported first-class environment:

1. **`make` reachability:** `C:\msys64\usr\bin` is added to the **user's
   global PATH** (user choice, 2026-07-14), positioned so that Git for
   Windows keeps winning the `git` resolution (user PATH entries are
   evaluated after system PATH, where Git for Windows lives). Setup docs
   require verifying `Get-Command git` after the change.
2. **Shell-agnostic Makefile recipes:** recipes must not depend on a
   POSIX shell — conditional logic moves to Python helpers or single
   direct commands, so the Makefile keeps working even under the
   `cmd.exe` fallback.
3. **`UV_SYSTEM_CERTS=1`** has a dual home: the **versioned**
   `.claude/settings.json` (covers Claude Code sessions) and the
   **user's Windows environment variables** (covers `make`/`uv` in a
   plain PowerShell, set in the same machine-setup act as the PATH);
   `.claude/settings.local.json` is untracked (machine-level override,
   per Claude Code convention).
4. **Devcontainer and WSL remain supported options**, no longer the
   prescribed path. README and `validate-ci-gate.md` are corrected
   accordingly.

## Alternatives considered

### Alternative A — Keep POSIX-only (devcontainer/WSL required on Windows)
- **Description:** keep the template's stance; develop inside the
  devcontainer.
- **Pros:** zero Makefile changes; environment identical to CI.
- **Cons:** permanent friction for the daily solo workflow (IDE inside
  container, Docker always running); contradicts how the project is
  actually developed; the native path is already proven green.
- **Why rejected:** the sponsor develops on native Windows; forcing a
  container adds cost without adding correctness.

### Alternative B — Document a per-session PATH append (no global change)
- **Description:** README/runbook instruct
  `$env:PATH += ";C:\msys64\usr\bin"` per session.
- **Pros:** no global machine mutation; ordering risk minimized (append).
- **Cons:** every new terminal needs the incantation; `make` stays
  unreachable for tools that spawn their own shells; easy to forget.
- **Why rejected:** user decision (2026-07-14) — prefer solving it once
  globally.

### Alternative C — Wrapper script (`scripts/dev.ps1`) injecting PATH/env
- **Description:** a PowerShell wrapper that sets PATH + env and forwards
  to `make`.
- **Pros:** self-contained, versioned.
- **Cons:** forks the documented `make <target>` interface; one more
  moving part to maintain.
- **Why rejected:** user decision (2026-07-14); the global PATH makes the
  documented interface work as-is.

### Alternative D — Do nothing / status quo
- **Why rejected:** `make` is unreachable out of the box; the DoD of
  Stage 1.1 (`make setup && make check && make test` green) is impossible
  without an environment decision.

## Consequences

### Positive
- The documented commands (`make setup`, `make check`, `make test`) work
  in any new PowerShell session with no incantation.
- Local and CI run the same gate (`make check`), with recipes that no
  longer silently depend on which shell Make found.
- The TLS fix for `uv` has a versioned home; new sessions and new clones
  do not rediscover the failure.

### Negative
- A global machine mutation (user PATH) lives outside the repo — it must
  be documented (README + this ADR) because a fresh machine will not have
  it.
- MSYS2's `git.exe` permanently coexists on the PATH; the ordering
  guarantee relies on Windows evaluating system PATH first. The
  `Get-Command git` check is the guard.

### Neutral / trade-offs accepted
- The GNU Make **provider** is not pinned to MSYS2 (audit note,
  2026-07-15): on the sponsor's machine the WinGet `ezwinports.make`
  (also GNU Make 4.4.1) shadows MSYS2's make on the user PATH, and
  `make check` stays green. The load-bearing invariants are "*some*
  GNU Make 4.4+ reachable on the PATH" and "`git` resolving to Git for
  Windows" — not which provider answers `make`. README §Setup already
  documents both providers as valid.
- The devcontainer path may drift (it is no longer exercised daily);
  accepted — CI on `ubuntu-latest` remains the portable-environment
  check.
- `UV_SYSTEM_CERTS=1` in versioned settings is machine-motivated but
  harmless where unneeded (it only switches uv to the OS trust store).

## Implementation notes

- Makefile: `setup` switches to `uv sync --extra dev`; conditional
  logic (pre-commit presence check, `clean` file sweeps) moves to Python
  helpers or direct commands; recipes reduced to single-command lines.
- The user PATH change is applied once via
  `[Environment]::SetEnvironmentVariable("Path", ..., "User")` —
  **append**, never prepend.
- README gains a "Windows nativo" setup path; `validate-ci-gate.md`
  Prerequisites drops the "POSIX shell only" line.

## References

- Related ADRs: [ADR 1.1.0002](./1_1_0002-observational-pr-gates.md)
  (the other template-assumption correction of Stage 1.1)
- Issue: [#1](https://github.com/MarceloSanC/restaurant-hub/issues/1)
  (body + environment-findings comment, 2026-07-12)
- uv TLS: https://docs.astral.sh/uv/reference/settings/#native-tls

---
title: ADR 4.1.0001 — Every saved change is the live schedule (no server-side draft, no immutable published versions), with optimistic concurrency by schedule version
description: Architecture Decision Record
when-use: Reference before modeling schedule state (draft vs published), before designing how block/warn violations interact with saving, before implementing concurrent-edit handling for the schedule, or when Stage 4.6 (notifications) and Step 5 (auto-fill) need to know what "publish" means
keywords: [adr, scheduling, publish, live-schedule, draft, versioning, audit-log, block, warn, acknowledge, optimistic-concurrency, conflict, domain-gate]
status: accepted
created_at: 2026-09-13
updated_at: 2026-09-13
adr_id: 4.1.0001
decision: Every persisted mutation of a schedule is the live schedule that employees, the image, the timeclock and the hub see — there is no server-side draft and no immutable published version; a block violation refuses the mutation itself, a warn violation is acknowledged in the same save; concurrent edits are handled by an optimistic check on a schedule version counter with reload-or-cancel on conflict and no server-side overwrite.
context_stage: 4.1-scheduling-domain
bounded_context: scheduling
---

# ADR 4.1.0001 — Every saved change is the live schedule

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

This decision was taken at the **domain gate of Step 4** (2026-09-13) while synthesizing
[`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md), per
[`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1–§2. It consolidates two
forks of the gate triage (F1 — publication model; F8 — concurrent editing) because the second
depends on the state model chosen by the first. Both were decided by the **human sponsor**
(Marcelo, 2026-09-13).

The ratified sources pulled in two directions:

- `overview.md` §3 (line 44) fixes **"salvar = publicar"**, and the glossary (line 137) defines
  *publicar* as "salvar a escala tornando-a visível". Overview outranks roadmap.
- `roadmap.md` describes the editor flow as "editar → avaliar → aceitar violações warn → publicar"
  (Stages 4.3/4.5, lines 1447, 1514), and Stage 5.2 (line 1608) says the auto-fill "grava
  alocações como **rascunho de edição**", with the non-goal "aplicar+publicar num passo só"
  (line 1625). Those phrases presuppose a working copy that is not yet visible.

The triage's recommended option was a **draft + explicit publish with numbered immutable
versions** (the version would serve audit, "affected employees" diffs for e-mail, the printed
image, the timeclock's "what applied that day", and optimistic concurrency). The concept was put
to the sponsor with three options.

For concurrency, the staff precedent is **"last write wins"**
([ADR 3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md) lines 91–98),
and the roadmap records optimistic concurrency as "aberto, sem Stage candidata" (lines 820–824).
The schedule is the first aggregate with dozens of mutations per session and more than one
legitimate editor (owner and manager), so the precedent could not simply be inherited.

## Decision

### 1. Every saved change is the live schedule (F1)

Sponsor, verbatim: *"toda alteracao salva é a escala vigente, simple e direto"*.

- There is **no draft on the server** and **no published version separate from the schedule
  being edited**. Each persisted mutation (demand, assignment, acknowledgement) is the schedule
  the employee consults, the image renders, the timeclock reconciles and the hub reads.
- A **`block` violation refuses the mutation itself**. The live schedule is never in an invalid
  state, and the editor cannot pass through an invalid state while rearranging.
- A **`warn` violation is presented and acknowledged in the act of saving**. The conscious
  acknowledgement (`overview.md` line 43) is part of the mutation, and it is audited (who
  acknowledged what, when). The roadmap's "editar → avaliar → aceitar warn → publicar" reads as:
  evaluate live, then save **with** the acknowledgement of the warnings the change introduces.
- **"Version" is not an immutable snapshot.** The history of the schedule is the **audit log**
  that Stage 4.4 creates ("histórico de edições — quem alterou o quê e quando", `roadmap.md`
  1473, 1490). The only "version" that exists is the concurrency counter of §2.
- `overview.md` "salvar = publicar" stays **literal** — no reconciliation note is needed there.

### 2. Concurrency: optimistic check on the schedule version, reload-or-cancel (F8)

Sponsor, verbatim: *"Ao clicar em publicar precisa conferir se foi atualizada, se foi, aparece
mensagem se deseja atualizar e perder o trabalho ou nao (cancelar= nao publica mas nao perde o
trabalho caso ele queira printar a tela pore xemplo)"*.

- Every mutation carries the **schedule version** the editor saw. If the schedule changed since,
  the server **refuses** the mutation and returns the current state.
- The client offers **"atualizar"** (discard what is on screen and reload) or **"cancelar"**
  (keep what is on screen, **unsaved**, so the editor can note it down and redo it).
- **Overwriting someone else's work is not offered by the server.** The editor reloads and redoes.
- Candidate Stages: **4.4** (version column + check in persistence) and **4.5** (status/body of
  the refusal). This closes the roadmap gap "controle otimista — sem Stage candidata".

## Alternatives considered

### Alternative A — Draft + explicit publish with numbered immutable versions (triage's recommendation)
- **Description:** a persisted working copy per period, a "last published version" that is
  immutable; publish is one click without approval; `block` prevents publishing, not editing.
- **Pros:** the version object serves four consumers at once (audit, e-mail diff of affected
  employees, image "of the published", timeclock "what applied that day") and gives optimistic
  concurrency for free.
- **Cons:** a second state the reader must understand ("saved" ≠ "published"); a versions table
  and a separate publish use case; the employee may see a stale schedule while the manager
  rearranges.
- **Why rejected:** **the sponsor rejected it.** The literal reading of the overview is what the
  product owner wants: simple and direct. Recorded here so the recommendation is not later read
  back as the decision.

### Alternative B — Client-only draft; the server receives the whole schedule on publish
- **Description:** no server-side edit state; a stateless live-evaluation endpoint.
- **Pros:** smallest backend.
- **Cons:** closing the tab loses work; Step 5 has nowhere to store a proposal; two editors are
  undetectable.
- **Why rejected:** loses work on any disconnection; blocks Step 5 and concurrency handling.

### Alternative C — Last write wins (staff precedent, ADR 3.3.0006)
- **Description:** no version check; the second editor silently overwrites the first.
- **Pros:** zero cost.
- **Cons:** a wrong schedule is published without anyone knowing; corrupts data before a later
  fix can be applied.
- **Why rejected:** the sponsor asked for the check ("precisa conferir se foi atualizada").

### Alternative D — Pessimistic lock ("schedule being edited by Ana")
- **Description:** a lease with expiry and UI for taking over.
- **Pros:** no conflicts at save time.
- **Cons:** stale locks when a tab is left open; lease/expiry/UI machinery; frustrates the owner
  who wants to adjust while the manager's tab is open.
- **Why rejected:** heavier than the observed need (rare conflicts in the pilot).

### Alternative E — Server-side "overwrite anyway" on conflict
- **Description:** the conflict dialog offers a third button that forces the editor's version.
- **Pros:** fewer redo steps for the editor.
- **Cons:** reintroduces silent loss of the other editor's work behind one click.
- **Why rejected:** the sponsor's two options are reload or cancel; overwrite was not asked for
  and contradicts the purpose of the check.

### Do nothing / status quo
Not applicable: the state model decides where the acknowledgement lives, what "affected" means
for e-mail, what the audit log records and how Step 5 applies a proposal. Leaving it open pushes
the fork into four Stage concepts.

## Consequences

### Positive
- One state to understand: what is saved is what everybody sees. Matches the overview literally.
- The live schedule is never invalid (`block` refuses the mutation); the Step 5 rule "proposal is
  born without block violations" (`roadmap.md` 1596) reuses the same semantics.
- No silent overwrite between editors; the fix is one column, one check and one refusal status.

### Negative
- **E-mail per mutation.** Without grouping, a two-mutation fix sends two e-mails. Grouping /
  debounce is a **gap for the Stage 4.6 concept** (the sponsor did not decide it).
- **Roadmap 5.2 tension.** "grava alocações como rascunho de edição" and the non-goal
  "aplicar+publicar num passo só" presuppose a draft that does not exist. Recorded as a **roadmap
  scope gap for the Step 5 domain gate**: either "apply" publishes directly (respecting `block`),
  or Step 5 defines its own notion of proposal. Not resolved here.
- The timeclock's "what applied that day" (Step 7) has no version snapshot to read; the source is
  the audit log (4.4). The 7.2 concept decides, with 4.4 informed.
- An employee may see the schedule change under them; the 4.4 concept decides what they see.

### Neutral / trade-offs accepted
- The acknowledgement protocol (submit with acknowledgements previously shown by live evaluation
  vs. the server returning warnings for confirmation) is a 4.3 concept gap.
- The identity of a violation for acknowledgement purposes (does an acknowledgement survive a
  change to the assignment that caused it?) is a 4.2/4.3 concept gap.

## Implementation notes

- Lands in Stage 4.3 (use cases: mutations carry the acknowledgement and the seen version), 4.4
  (audit log; version column; check) and 4.5 (refusal status/body). The theory lives in
  [`shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.5.
- The audit log is the first in the system (staff has no `Clock` and no timestamps —
  [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md) 155–157); whatever 4.4
  decides becomes precedent.

## References

- Related ADRs: [ADR 3.3.0006](./3_3_0006-transactional-atomicity-without-optimistic-locking.md)
  (last write wins in staff; optimistic control escalated); [ADR 3.2.0006](./3_2_0006-employee-lifecycle-and-guarded-deletion.md)
  (no `Clock`/timestamps in staff); [ADR 0.0.0003](./0_0_0003-formalize-domain-and-audits-doc-categories.md)
  (domain-doc category); [ADR 4.1.0003](./4_1_0003-v1-validation-policy-set-defaults-and-modes.md)
  (block/warn policy set).
- [`overview.md`](../overview.md) — §3 line 43 ("o editor corrige ou aceita conscientemente"),
  line 44 ("salvar = publicar"), line 38 (audit trail); §9 line 137 (*publicar*).
- [`roadmap.md`](../roadmap.md) — Stage 4.3 (1447), 4.4 (1473, 1490), 4.5 (1514); Stage 5.2
  (1608, 1625); Step 5 (1596); optimistic control gap (820–824).
- [`docs/domain/scheduling/shift-scheduling.md`](../domain/scheduling/shift-scheduling.md) §3.5,
  §3.8, §3.10.3, §6.
- `src/restaurant_hub/shared/application/ports/out/clock.py` line 17 (absolute "when").
- Process: [`PROMPT-step-single-session.md`](../PROMPT-step-single-session.md) §1–§2; sponsor
  decisions F1 and F8 on 2026-09-13 (session record `gate-decisions.md`).
- External: none — this is a product decision; no labour-law source constrains the publication
  model.

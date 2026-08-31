---
title: ADR 0.0.0006 — Primary ports are the use case classes themselves; there is no ports/in/ directory
description: Architecture Decision Record
when-use: Reference before creating an application/ports/in/ directory, before writing a Protocol whose only implementation is one of our own use cases, or when reconciling the canonical Ports & Adapters vocabulary with this repository's layout
keywords: [adr, hexagonal, ports, driving-ports, primary-ports, use-case, layout, protocol, dead-code]
status: accepted
created_at: 2026-08-31
updated_at: 2026-08-31
adr_id: "0.0.0006"
decision: The driving (primary) port of this project is the use case class itself, exposing execute(<Command>) -> <Result>; no application/ports/in/ directory is created, and docs/LAYOUT.md stops promising one.
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0006 — Primary ports are the use case classes

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

`docs/LAYOUT.md` §2 has drawn `application/ports/in/` in its folder tree since the
Stage 1.1 bootstrap, described in §5 as *"ports primários / driving"*, with an
example (`Create<Entity>Port`). Six Stages later — two bounded contexts, 26 use
cases, one HTTP adapter in production — the directory **has never existed** in
either context.

Two facts make the gap more than a stale line in a document.

1. **The document is the instruction for where the next file goes.** LAYOUT §2 is
   what a Stage reads before creating anything (`CLAUDE.md`: *"antes de criar
   qualquer arquivo novo, verifique onde ele se encaixa no docs/LAYOUT.md"*). A
   path that is drawn but does not exist is not an imprecision — it is a wrong
   instruction that no compiler will correct.
2. **Two whole sections of the document existed only to work around it.** `in` is
   a Python keyword, so `from ...application.ports.in.x import Y` is a
   `SyntaxError`. LAYOUT §5 carried a "Nota sobre o diretório `in`" with three
   workarounds, and §8 repeated them. That is a page of documentation written to
   explain how to import from a package nobody had.

The question this ADR settles is not "should we finally create it?" — it is
whether the canonical Ports & Adapters vocabulary implies a *directory* here at
all.

It does not, and the code already answers it. Every adapter in the repository
calls its use case directly:

```python
def create_unit(
    payload: CreateUnitRequest,
    use_case: Annotated[CreateUnitUseCase, Depends(_get_create_unit)],
) -> UnitResponse:
```

`CreateUnitUseCase` **is** the driving port: it is the boundary the outside world
is allowed to touch, it names the operation, and it accepts a command DTO and
returns a result DTO — never a domain entity (LAYOUT §7). The composition root
injects the instance; the adapter never imports a concrete implementation of
anything.

## Decision

**The driving port of this project is the use case class**, with its
`execute(<Command>) -> <Result>` signature. It lives in
`application/use_cases/`, one per file.

**No `application/ports/in/` directory is created**, and `docs/LAYOUT.md` stops
promising one: the path leaves the §2 tree, and §5 states the rule in place of
the old subsection.

**The driven side is unchanged.** `application/ports/out/` remains exactly as it
is — `Protocol` per external need, implemented by adapters and by fakes. The
asymmetry is the decision: outbound needs abstraction, inbound does not.

**`adapters/in/` stays.** It is a real, occupied directory (identity's HTTP
boundary lives there), and the keyword workaround it needs is genuine. Only the
`ports/in/` half of the keyword discussion goes away with this ADR.

## Alternatives considered

### Alternative A — create `ports/in/` and a `Protocol` per use case
- **Description:** for each of the 26 use cases, a `Protocol` in
  `application/ports/in/` that the use case implements and the adapter depends on.
- **Pros:** literal fidelity to the textbook diagram; the adapter would depend on
  an interface rather than on a class name.
- **Cons:** 26 interfaces with exactly one implementation each, all written by us,
  to decouple our code from our code. No consumer would use them as a variation
  point — there is no second implementation of `CreateUnitUseCase` and no
  requirement suggesting one. And every one of them would be unreachable by static
  import (the `in` keyword), so the adapter would need `importlib` or an
  `__init__.py` re-export — the latter now forbidden by rule 9 of
  `check_layout.py`. The cost is a package the language cannot address, bought for
  an indirection nobody consumes.
- **Why rejected:** it is abstraction with a measured consumer count of zero — the
  same defect that put `Pagination` in `shared/` for six Stages (issue #45,
  Gate 7). Ports & Adapters asks that the application not depend on the outside;
  it does not ask that the application be wrapped in interfaces addressed to
  itself.

### Alternative B — rename the directory to `ports/inbound/` and populate it
- **Pros:** removes the keyword problem while keeping the canonical shape.
- **Cons:** solves the *spelling* of a directory whose *content* is the actual
  question. Every argument in A survives the rename.
- **Why rejected:** renaming does not make 26 single-implementation Protocols
  worth writing. (The parallel rename of `adapters/in/` → `adapters/inbound/` is a
  separate matter, and it is about a directory that has real content.)

### Alternative C — leave the line in the tree, annotated as planned
- **Pros:** zero edits; the new `[planejado]` annotation of
  `scripts/check_docs_claims.py` would accept it.
- **Cons:** the annotation means *"we intend to build this"*, and we do not. Using
  it to silence a gate over a path we have decided against would corrupt the one
  escape hatch the gate has — and the next reader would take the promise at face
  value.
- **Why rejected:** the annotation is for deferred intent, not for retracted
  intent. What is retracted gets deleted.

## Consequences

### Positive
- LAYOUT §2 stops asserting a path that does not exist, which is what
  `scripts/check_docs_claims.py` (Gate 5) now enforces mechanically.
- The keyword-workaround material shrinks to the single case where it is real
  (`adapters/in/`).
- The rule is now stated where the question is asked: someone about to write a
  one-implementation `Protocol` for a use case finds the answer in §5.

### Negative
- The repository diverges from diagrams that show a symmetric `ports/in` +
  `ports/out` pair. Anyone arriving from that literature has to read §5 to find
  out why — which is exactly what §5 and this ADR are for.
- If a second driving adapter ever appears (a CLI, a worker), it will depend on
  the use case class directly, same as HTTP. That is intended; should a real need
  for inbound variation appear, this ADR is superseded rather than worked around.

### Neutral / trade-offs accepted
- `application/ports/` now has a single child (`out/`). The extra level is kept:
  flattening it to `application/out_ports/` would rename eleven modules and every
  import of them, for cosmetics.

## Implementation notes

- `domain/services/` **stays** in the §2 tree, marked `[planejado]`. It is a real
  hexagonal slot with deferred intent (no domain service exists yet in either
  context), which is the case the annotation was built for — as opposed to
  `ports/in/`, which is retracted.
- The gate enforces both directions: a drawn path that does not exist fails, and a
  `[planejado]` path that already exists fails too. So `domain/services/` must
  lose the annotation in the same commit that creates the first domain service.

## References
- `docs/LAYOUT.md` §2 (tree), §5 (Ports), §7 (golden rules)
- `scripts/check_docs_claims.py` — Gate 5 of issue #45
- `scripts/check_layout.py` rule 9 — package markers carry no code, which closes
  the `__init__.py` re-export workaround of the old §5
- Issue #45 — architecture gates invisible to import contracts
- `src/restaurant_hub/features/identity/adapters/in/http/router.py` — the driving
  adapters, each calling its use case class directly

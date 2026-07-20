---
title: ADR 2.5.0001 — EmailSender port lives in shared, not in the identity feature
description: Architecture Decision Record
when-use: Reference when adding a second consumer of EmailSender (stage 4.6), when adding a real e-mail adapter, or when deciding where a new cross-feature port belongs
keywords: [adr, email, port, shared, layout, identity, notification]
status: accepted
created_at: 2026-07-20
updated_at: 2026-07-20
adr_id: "2.5.0001"
decision: The EmailSender port and its EmailMessage DTO live in shared/application/ports/out, with the ConsoleSender adapter in shared/infrastructure/email, because the second consumer (stage 4.6 schedule notifications) is already named in the roadmap and the signature is describable without any invitation vocabulary.
context_stage: 2.5-email-invite
bounded_context: identity
---

# ADR 2.5.0001 — EmailSender port lives in shared, not in the identity feature

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted`

## Context

Stage 2.5 is the first stage that sends anything out of the process. Two written
sources point in opposite directions, and issue #27 explicitly refuses to treat
this as an automatic win for either:

- `docs/roadmap.md` §Stage 2.5 places the port at
  `shared/application/ports/email_sender.py`, and §Stage 4.6 (schedule publication
  notification) declares `EmailSender (2.5)` under `contratos_consumidos`.
- `docs/LAYOUT.md` §4 states the opposite heuristic for the doubtful case: *"in
  case of doubt, start in the feature. Move to shared only when the second feature
  needs the same code."*

The LAYOUT rule exists to prevent a premature abstraction shaped by a single
consumer — an interface that claims to be general but silently encodes one
caller's assumptions. Issue #27 supplies the practical test: **can the port's
signature be described without saying "invitation"?** If not, it is an identity
port with a big name.

## Decision

`EmailSender` and `EmailMessage` live in
`src/restaurant_hub/shared/application/ports/out/email_sender.py`; the
`ConsoleSender` adapter lives in `src/restaurant_hub/shared/infrastructure/email/`.

> **Path note.** The roadmap writes `shared/application/ports/email_sender.py`,
> without the `out/` segment. The `out/` subdirectory is used here because it is
> the established convention in this tree (`shared/application/ports/out/clock.py`,
> `id_generator.py`) and because LAYOUT §5 separates driving from driven ports.
> This is a naming divergence from the roadmap, declared as divergence #5 in
> `concept.md` §1 rather than applied silently.

```python
@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body_text: str


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...
```

Three facts carry the decision:

1. **The second consumer is named, not imagined.** Stage 4.6 is in the roadmap
   with `EmailSender (2.5)` as a consumed contract. "Premature" means *no
   identified second consumer*; that is not the case here.
2. **The signature passes the genericity test.** Recipient, subject and body —
   nothing about invitations, tokens, users or tenants.
3. **The layer rule enforces the genericity mechanically.** `shared/application`
   may not import from `features/` (LAYOUT §3), so `to` is a plain `str` and
   **cannot** become identity's `Email` value object. Any future attempt to leak
   invitation vocabulary into this port fails import-linter, not code review.

## Alternatives considered

### Alternative A — Start in `features/identity/application/ports/out/`, move at 4.6
- **Description:** follow LAYOUT §4 literally; relocate the port when scheduling needs it.
- **Pros:** obeys the heuristic verbatim; zero risk of a wrong shared abstraction.
- **Cons:** the move itself is not free — at 4.6 the `scheduling` feature would
  either import from `features/identity` (a cross-feature import that LAYOUT
  forbids) or force a relocation commit touching identity's use cases, adapters and
  the composition root, in a stage whose subject is schedule publication. The
  refactor lands in the stage least equipped to review it.
- **Why rejected:** the heuristic's premise (unknown second consumer) is false here.

### Alternative B — Shared port, but with a richer message model (templates, HTML, attachments)
- **Description:** anticipate 4.6 with a template id + variables contract.
- **Pros:** would spare a later signature change if 4.6 wants templating.
- **Cons:** exactly the premature abstraction LAYOUT §4 warns about — shaped by a
  guess about 4.6, not by 4.6. The roadmap's own non-goal for 2.5 is "no elaborate
  e-mail templates".
- **Why rejected:** speculative generality; adding a field later is cheap.

### Alternative C — Duplicate a small sender per feature
- **Description:** identity and scheduling each own a sender.
- **Pros:** no coupling at all.
- **Cons:** two provider configurations, two adapters to swap when the provider
  changes, two places for a credential to be wired wrongly.
- **Why rejected:** e-mail delivery is textbook cross-cutting infrastructure —
  the same category as `Clock` and `IdGenerator`, which already live in `shared/`.

## Consequences

### Positive
- Stage 4.6 consumes the port with no relocation and no cross-feature import.
- The provider swap (console → Resend, ADR-worthy in 6.2) is one adapter in one place.
- The layer rule keeps the port honest without depending on reviewer vigilance.

### Negative
- Establishes a precedent for placing a port in `shared/` before the second
  consumer exists **in code**. The precedent is narrow on purpose: it requires a
  named consumer in the roadmap **and** a signature free of the first consumer's
  vocabulary. A port failing either test goes into the feature.

### Neutral / trade-offs accepted
- The recipient is a `str`, so identity converts `Email.value` at the call site.
  That conversion is the visible price of genericity, and it is one line.

## References
- `docs/LAYOUT.md` §3 (dependency direction), §4 (feature vs shared)
- `docs/roadmap.md` §Stage 2.5, §Stage 4.6
- GitHub issue #27, "Decisão a tomar nesta Stage"
- `docs/stages/2.5-email-invite/concept.md` §7 D1
</content>

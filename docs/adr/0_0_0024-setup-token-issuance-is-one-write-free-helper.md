---
title: ADR 0.0.0024 — Setup-token issuance is one write-free application helper; each use case keeps its own write
description: Architecture Decision Record
when-use: Reference before adding a sixth use case that issues a password-setup token, before changing `_invitation.issue_setup_token`, before moving a repository write of a use case into a module-level helper, or when deciding whether a repeated step across use cases becomes a helper, a service with its own port, or stays copied
keywords: [adr, identity, setup-token, invitation, password-reset, helper, extraction, unit-of-work, check-layout, rule-10, duplication, issue-205]
status: accepted
created_at: 2026-11-23
updated_at: 2026-11-23
adr_id: "0.0.0024"
decision: "The password-setup token issuance step (issue through `SetupTokenIssuer`, build the `PasswordSetupToken` record with fingerprint, `issued_at` and `expires_at`, build the setup link) has a single definition, `features/identity/application/use_cases/_invitation.py::issue_setup_token`, which receives only non-writing ports (`SetupTokenIssuer`, `IdGenerator`) and the caller's purpose, `now`, TTL and base URL, and returns the record plus the link without writing. The five issuing use cases call it and keep `self._tokens.add(record)` in their own body, inside their unit of work, where `check_layout` rule 10 counts it; a test fails if any function of `_invitation.py` takes a repository parameter."
context_stage: 0.0-global
bounded_context: transversal
---

# ADR 0.0.0024 — Setup-token issuance is one write-free application helper

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese.

## Status

`accepted` — decided in issue #205 (standalone issue, hence the `0.0` prefix — CONVENTIONS §1,
"ADR global" — and `bounded_context: transversal`, as for ADR 0.0.0018, whose deferred extraction
this closes). The issue frames the form as a fork; the sponsor delegated P forks to the
implementing session, which takes the recommended option:

```
[decision] P delegado — Opção A (helper de application sem escrita), motivo: é o esqueleto
escalável com implementação mínima — uma definição só do cálculo, sem port novo nem regra nova
no check_layout, e a escrita fica no corpo do use case, onde a regra 10 a conta.
```

The number was checked free on `develop`, on every remote branch and in every open worktree on
2026-11-23 (`0.0.0023` is taken by the in-flight issue #207 branch).

**Closes the deferral in [ADR 0.0.0018](./0_0_0018-restaurant-owner-is-provisioned-by-invitation.md)
› Negative** (*"extracting it is left to the change that makes the copies diverge or adds a
fifth"*): the fifth copy arrived with `InviteOwnerUseCase` (Stage 2.7, ADR 2.7.0001). 0.0.0018
receives an append-only dated note.

## Context

- **The five copies (measured on `develop` at `fb3c7b7`).** `InviteUserUseCase`,
  `InviteOwnerUseCase`, `ProvisionRestaurantUseCase`, `ProvisionAccountUseCase` and
  `RequestPasswordResetUseCase` each had a private `_issue_token` with the same body:
  `now = clock.now()`, `issued = token_issuer.issue()`, then
  `tokens.add(PasswordSetupToken(id=SetupTokenId(str(id_generator.next_id())), user_id, purpose,
  token_fingerprint=issued.fingerprint, issued_at=now, expires_at=now + ttl))`, returning
  `issued.value`, which the caller turned into `setup_link(base_url, value)`. The link format was
  already single (`_invitation.setup_link`, Stage 3.5).
- **What diverges is not the calculation.** The purpose (`INVITATION` in the four invitations,
  `PASSWORD_RESET` in the reset), the TTL (`invitation_ttl`; `handover_ttl` when
  `ProvisionAccountCommand.handed_over`; `reset_ttl`), where `now` comes from (the reset uses the
  same instant to `invalidate_all_for_user` first), where the link goes (invitation e-mail through
  `deliver_invitation`, the reset e-mail with its own text and absorbed failure, or the
  `ProvisionedAccountResult.setup_link` returned to the facade) and the other writes in the unit.
  Every divergence is either a parameter of the step or outside it.
- **The constraint (issue #205).** `scripts/check_layout.py` rule 10 (ADR 2.6.0002 §5) counts a
  write as a call on a constructor-annotated repository attribute of the use case, following the
  class's own private methods. ADR 2.6.0002 §5 › "Known blind spots, declared" lists *"a
  repository handed to a module-level function"*. A helper that received `tokens` and called
  `tokens.add` would take the token write out of the rule's reach in all five use cases: moving
  `users.add` back out of the unit would then leave the suite green and atomicity lost.
- **The ordering constraints.** The use cases that act for an actor authorize as their first
  instruction (ADR 0.0.0020 §Decision 3, pinned by an AST test); `ProvisionAccountUseCase` refuses
  roles outside `PROVISIONABLE_ROLES` first (issue #211). The issuance happens inside the unit of
  work, long after both, so the extraction moves nothing ahead of them.

## Decision

1. **One definition of the calculation.** `_invitation.issue_setup_token(token_issuer,
   id_generator, *, user_id, purpose, now, ttl, base_url) -> SetupTokenIssuance` calls
   `token_issuer.issue()` once, then `id_generator.next_id()` once (the order of the copies), and
   returns `SetupTokenIssuance(record, link)`: the `PasswordSetupToken` to persist and
   `setup_link(base_url, issued.value)`. The plain token value leaves the function only inside the
   link; `link` is `repr=False` for the same reason as `IssuedSetupToken.value`.
   [decision:C] rung 4.
2. **The helper does not write; the use case does.** Each of the five keeps
   `self._tokens.add(issuance.record)` in `execute` (or, in the reset, in its private
   `_issue_token`, which rule 10 follows), inside the same unit as before. The purpose, the TTL and
   `now` are chosen by the caller and passed in: the helper decides nothing about access, channel
   or lifetime, so it does not join the mutation run's `only_mutate` scope. **What leaves that
   scope, declared:** `provision_account.py` is in `only_mutate` (issue #211); the record
   construction it held — including `expires_at = now + ttl` of the in-hand link, whose lifetime
   ADR 3.5.0002 §3b ties to the channel — now lives in `_invitation.py`, outside the run.
   The **choice** of TTL by channel (`handover_ttl if handed_over else invitation_ttl`) stays in
   `provision_account.py` and is still mutated; the arithmetic is pinned by exact-record
   assertions on the helper and on all five issuers (`test_setup_token_issuance.py`). The entry
   criterion recorded in `tests/unit/test_mutation_scope.py` is the role refusal, which did not
   move.
3. **The guard is a test, scoped to this helper.** `test_setup_token_issuance_rule10.py` fails if
   any function in `_invitation.py` takes a parameter whose annotation names a repository port
   anywhere — `X`, `mod.X`, `"X"`, `X | None`, `Optional[X]`, `*args`/`**kwargs` included — (the
   set derived from `ports/out/*_repository.py`, as rule 10 derives it), each form proven against
   a planted module; and, on a copy of `src/` with the unit of each issuer turned into
   `if True:`, asserts that rule 10 flags all five, naming `self._tokens.add`.

```
[decision:C] #205-1 — Forma da extração da emissão do token de definição de senha
Escolha: helper de application sem escrita (`issue_setup_token`), gravação no use case · Alternativas: serviço com port próprio que grava; manter as cinco cópias · Degrau (C): 4
Base: ADR 2.6.0002 §5 "Known blind spots, declared" "a repository handed to a module-level function" · ADR 0.0.0018 Negative "extracting it is left to the change that makes the copies diverge or adds a fifth" · scripts/check_layout.py `_Varredor` (só `self.<atributo>` com tipo de repositório e métodos `self._x` conta como escrita)
Verificado: sustenta — evidence-verifier, 2026-11-23, seis itens (ADR 2.6.0002 §5, ADR 0.0.0018 Negative, regra 10 do check_layout, `_invitation.py` sem repositório, escrita dos cinco dentro da unidade e primeira instrução intacta, ADR 0.0.0006)
Configuração candidata: nenhuma · Reversível: sim (helper interno da camada, sem port nem formato persistido)
```

## Alternatives considered

### Alternative A — Write-free application helper (chosen)
- **Pros:** one definition of the calculation; no new port, no change to `check_layout`, no
  constructor change in any use case (the composition root is untouched); the write stays where
  rule 10 sees it; the plain value is confined to the link.
- **Cons:** each use case still writes `self._tokens.add(issuance.record)` and passes six
  arguments — five two-line call sites instead of one call that also writes.

### Alternative B — A service with its own port that issues and persists
- **Description:** an `SetupTokenService` (out port + implementation) injected into the five use
  cases, owning `tokens.add`.
- **Pros:** each call site is one line.
- **Cons:** the token write moves into a collaborator rule 10 does not inspect — the declared blind
  spot of ADR 2.6.0002 §5, now holding the second write of every issuing unit — or the rule must
  learn to follow the service; and it is an interface with exactly one implementation, written by
  us, to decouple our code from our code (the reasoning ADR 0.0.0006 applies to primary ports);
  five constructors and the composition root change.
- **Why rejected:** buys a shorter call site with the one property the issue protects.

### Alternative C — Keep the five copies
- **Pros:** no change.
- **Cons:** ADR 0.0.0018 set the fifth copy as the trigger, and it arrived; a sixth issuer (owner
  self-signup in Step 13, a reissue route) would copy the body again, and a change to the record
  (a new column, another derivation) would have to land five times in step.
- **Why rejected:** the divergence the deferral waited for did not happen in the calculation — it
  is all parameter.

### Alternative D — Extend rule 10 to follow repositories handed to module-level functions
- **Description:** close the blind spot in `check_layout` instead of keeping helpers write-free.
- **Pros:** a general guard for every BC.
- **Cons:** module-level helpers that take a repository already exist and read
  (`features/scheduling/application/use_cases/_inputs.py`, `_publish.py`), and in-flight work
  adds helpers in `use_cases/` that write through a port parameter (the staff `_login_link.py` of
  Stage 3.10); the rule change is a decision about ADR 2.6.0002 §5 for every BC, larger than this
  issue, and would collide with the Stage 3.10 edits to the same script.
- **Why rejected:** out of scope; recorded as a candidate, not done. The guard here is the narrow
  one the issue needs.

## Consequences

### Positive
- The issuance step has one definition with direct tests (`test_setup_token_issuance.py`): the
  record built from the parameters, the call order, the link identical to `setup_link`, the
  fingerprint of the link's token equal to the stored one (with the fake and with
  `Sha256SetupTokenIssuer`), and the link hidden from `repr`.
- The observable effect of the step in the five use cases is pinned by one parametrized test that
  passed before the extraction and after it, unchanged.
- Rule 10 still counts every write of the five issuers, and a test proves it by removing each unit.

### Negative
- The guard covers `_invitation.py` only. A new module-level helper elsewhere that receives a
  repository and writes is still invisible to rule 10 (ADR 2.6.0002 §5's declared blind spot).
- Five call sites of six named arguments; a sixth issuer copies the call, not the body.
- **The helper is the calculation, not the whole issuance policy.** ADR 2.5.0002 §Decision 5
  makes a new token invalidate the user's outstanding tokens of the same purpose. That
  invalidation is a write, so under this decision it can never live in the helper: today only the
  reset needs it (`invalidate_all_for_user` before the add, with the same `now`), because the four
  invitations create the account and there is nothing outstanding. A future issuer for an
  existing account — a link-reissue route, which the roadmap already names as the trigger of
  issue #82 — must call the invalidation itself,
  in its own unit, before `issue_setup_token`; copying an invitation's call would skip it.

### Neutral / trade-offs accepted
- The link of the four e-mail flows is now built inside the unit of work instead of after it; it
  is a pure string concatenation with no I/O and no failure mode, so nothing observable moves.

## References
- Issue #205; issue #184 / PR #187 (Stage 2.7, where the fifth copy was declared)
- [ADR 0.0.0018](./0_0_0018-restaurant-owner-is-provisioned-by-invitation.md) › Negative
- [ADR 2.6.0002](./2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md) §5
- [ADR 2.7.0001](./2_7_0001-identity-authorizes-through-a-narrow-port.md) §Decision 4
- [ADR 0.0.0020](./0_0_0020-identity-use-cases-authorize-their-own-target.md) §Decision 3
- [ADR 0.0.0006](./0_0_0006-primary-ports-are-the-use-case-classes.md)
- `src/restaurant_hub/features/identity/application/use_cases/_invitation.py`,
  `scripts/check_layout.py` (rule 10, `_Varredor`),
  `tests/unit/features/identity/application/test_setup_token_issuance.py`,
  `tests/unit/features/identity/application/test_setup_token_issuance_rule10.py`

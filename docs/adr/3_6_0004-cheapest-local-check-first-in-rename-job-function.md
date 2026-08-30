---
title: ADR 3.6.0004 — RenameJobFunctionUseCase validates the new name in the domain before probing name uniqueness, and the §5.16 table row is amended by errata to match the principle that closes it
description: Architecture Decision Record
when-use: Reference when a use case's declared check order conflicts with the principle that justifies the table, when an invalid value reaches a repository before the domain sees it, or before amending an ordering declared in a merged concept
keywords: [adr, application, ordering, precedence, nul-byte, dataerror, 500, staff, layer-expansion, errata, universal-law]
status: accepted
created_at: 2026-08-30
updated_at: 2026-08-30
adr_id: 3.6.0004
decision: RenameJobFunctionUseCase performs the domain transition (which validates the name) before find_by_name, so an invalid name never reaches the repository; concept 3.2 §5.16's row for rename_job_function is amended by dated errata, because the principle stated in the note that closes the table governs over the row it contradicts
context_stage: 3.6-staff-http
bounded_context: staff
---

# ADR 3.6.0004 — The cheapest local check comes first, in `rename_job_function` too

## Status

`accepted`

## Context

### The defect, measured through the real API

Stage 3.6's Task 12 exercises CA22 — *"a name containing `\x00` receives 422
through the real HTTP path, on **every** route that accepts a name, the domain
derived by introspection"*. Four routes qualify. Three answer 422. One answers
**500**:

```
router.py:308: in rename_job_function
rename_job_function.py:47: in execute
    homonima = self._job_functions.find_by_name(command.tenant_id, command.name)
sqlalchemy.exc.DataError: (psycopg.DataError) PostgreSQL text fields cannot
contain NUL (0x00) bytes
[parameters: {'tenant_id_1': '...', 'name_1': 'Ana\x00Souza'}]
```

`find_by_name(tenant, name)` ran **before** `job_function.rename(name)`, so the
raw name reached psycopg. `DataError` is **not** an `IntegrityError`, so Stage
3.3's per-operation translator (ADR 3.3.0004) is never invoked; it is not a
`StaffError`, so ADR 3.4.0002's handler does not see it; it is not an
`IdentityError` either. No handler reaches it, and the answer is 500 — refuting,
for this route, the line of concept 3.6 §6.3 that this Stage declares closed
(*"name with a NUL byte in the body — already rejected in the domain by 3.4"*).

### It is not a NUL defect, and it is not a Postgres defect

Measured with the in-memory fake, no database involved: renaming to `""`, to
`"   "` **or** to `"Ana\x00Souza"` triggers `job_functions.find_by_name` in all
three cases, before `InvalidNameError` is raised. The observed conduct was
`['job_functions.find_by_id', 'job_functions.find_by_name']` for each of the
three. The NUL is merely the species in which the useless query escalates into a
500 instead of staying a useless query.

### The law already exists, in writing — and only one of the two use cases obeys it

`create_job_function.py` builds the entity first, with the comment *"(1)
Construção: o domínio rejeita o nome vazio aqui, antes do port"*, and
`test_criar_com_nome_vazio_nao_toca_o_port` pins it with
`assert fakes.store.calls == []` — whose docstring states that the assertion on
`calls` **is the point**, because without it the test would pass even with a
useless `find_by_name` in front. That test existed for `create_job_function`
**only**.

This is the defect family *"universal law, narrow representative"* already
catalogued in `.claude/skills/stage-audit/SKILL.md`: the rule is stated for the
whole domain, the test pins one case, and every other case drifts silently. It is
why the deviation survived Stage 3.2 (unit tests use the fake, which accepts the
NUL), Stage 3.3 (the repository integration suite never renames to a NUL name)
and Stage 3.4 (which fixed the domain, and correctly recorded that the fix does
not reach identifiers — but nobody checked the *order* in which the domain is
consulted).

### The tension this ADR has to record honestly

Concept 3.2 §5.16 **declares** the current order for `rename_job_function`:
*"(1) carregar; (2) `find_by_name` (ignorando a própria) → conflito; (3)
transição; (4) `update`"*. Reordering therefore amends a table in a **merged**
concept, and that is not a free move.

But the note that **closes that same table** states the principle:

> *a checagem mais barata que possa falhar sozinha vem primeiro*

and justifies `create_job_function` by exactly that reasoning — the name check is
local, costs no I/O, and is the only precondition, so validating first avoids a
useless query. Applied to `rename_job_function`, that principle yields the
**opposite** of the row. The row and the principle disagree.

**The principle governs, and the row is what gets amended.** The note is the part
of §5.16 that carries the reason; the rows are its application. When an
application contradicts the reason that produced it, the application is the
error — otherwise the note is decorative and the next use case inherits the
inconsistency by copying a neighbour.

### Why the amendment changes nothing observable

The row's column *"par duplo construível"* answers **sim** for
`rename_job_function`, but the pair it names is **NotFound + conflict** —
*"renomear função **inexistente** para um nome **já usado**: vence `NotFound`"*.
That pair is untouched: `find_by_id` remains step (1), and the precedence it
protects (the response must not confirm that a name exists to someone who asked
with an id that is not theirs) is unchanged.

The pair the reordering *could* have disturbed — **invalid name + name
conflict** — is **not constructible**:

- `find_by_name(tenant, name)` can only return a `JobFunction`, and every
  `JobFunction` is validated in `__post_init__` (non-empty name, no NUL).
- Validation runs on **every** construction path, including rehydration from the
  database: ADR 3.4.0003's implementation note requires `__post_init__`
  precisely so the rule is an invariant and not an input filter, and the staff
  mapper's *Regra 1* (*"reidratar SEMPRE pelo construtor"*) forbids
  `object.__setattr__` / `__new__` shortcuts, so a corrupted row **raises on
  read** rather than returning an invalid entity.
- Therefore no stored name can be invalid, and a lookup by an invalid name can
  never match. The conflict branch is unreachable whenever the name check would
  have failed.

So no reachable scenario changes which error wins. The only behavioural
difference is that an invalid name stops touching the port — and the 500
disappears.

## Decision

1. **`RenameJobFunctionUseCase.execute` performs the domain transition before
   the uniqueness probe.** The order becomes: (1) `find_by_id` → `NotFound`;
   (2) `job_function.rename(name)` → `InvalidNameError`; (3) `find_by_name` →
   conflict; (4) `update`. This is the same shape `rename_employee` already has.

2. **Concept 3.2 §5.16's row for `rename_job_function` is amended by dated
   errata**, in place, pointing at this ADR. The row is corrected, not silently
   rewritten: the previous text and the reason for the change stay visible, the
   same discipline the errata blocks of ADR 3.4.0001/0002/0004 apply to accepted
   ADRs (CONVENTIONS §5).

3. **The law is pinned over the whole domain, not over a representative.** A
   parametrised test asserts *"an invalid name reaches no port call that carries
   it"* over the product `use case × invalid name` — `create_job_function`,
   `rename_job_function`, `rename_employee` × `""`, `"   "`, `"Ana\x00Souza"` —
   with the domain of use cases **derived** from the commands that carry a
   `name` field, so a fifth one cannot enter unclassified.

4. **`create_employee` is a documented exception and is excluded by name.**
   §5.16 declares its order as *"(1) resolver o conjunto de funções → ausência;
   (2) construir o `Employee`; (3) `add`"*, and the closing note justifies the
   inversion: the entity **cannot** be built without the resolved set, and
   building first would produce an `InvalidNameError` for a request whose real
   failure is **referential**, hiding the cause the manager needs to read.
   Asserting the law over it would contradict the concept. The exclusion and its
   reason are recorded in the test itself, and the derived-domain guard forces
   any future name-carrying command to be classified as covered or excluded.

5. **Declared target-layer expansion.** This Stage's layer is
   `adapters/in/http`; clause 1 edits `application` code owned by Stage 3.2, and
   clause 2 edits Stage 3.2's concept. The precedent is ADR 3.4.0003, which
   performed the same manoeuvre — a later Stage amending an earlier one's merged
   layer — on Stage 3.1's domain, for the same defect class and with the same
   argument: no fix inside the declared layer reaches the property that matters.
   Declared here and in `technical.md` §7.

## Alternatives considered

### Alternative A — validate the name at the HTTP boundary

- **Description:** extend the Stage's boundary validator to names, as it already
  does for identifiers, rejecting empty/whitespace/NUL before the use case runs.
- **Pros:** stays strictly inside this Stage's declared target layer; no merged
  Stage is touched.
- **Cons:** it duplicates a **domain** rule in the adapter. ADR 3.4.0003 already
  evaluated and **rejected** boundary handling for this exact defect (its
  *Alternative A*), on the grounds that it documents the divergence instead of
  removing it and leaves fake and real disagreeing. ADR 3.6.0002 then confined
  boundary validation to **identifiers**, and gave the reason: identifiers have
  no runtime hook and never pass through an entity — neither is true of names,
  which do pass through `__post_init__`. It would also leave the useless
  `find_by_name` for every other entry adapter, since the fix would live in one
  adapter rather than in the operation.
- **Why rejected:** the 500 is a symptom of an ordering defect in the
  application, and fixing it at the boundary treats the symptom in the wrong
  layer, against two ADRs that already ruled on this ground.

### Alternative B — narrow CA22 to the routes that reach the domain today

- **Description:** restate the acceptance criterion as "the routes that
  currently validate in the domain", open an issue for the rest.
- **Cons:** it is ADR 3.4.0003's *Alternative D* (do nothing) in new clothes,
  rejected there because it violates a stated acceptance criterion. CA22 was
  written with a **derived** domain precisely so that no route could be quietly
  excluded; narrowing it by hand reinstates the literal list the derivation
  exists to retire, and relaxes a security criterion written not to be relaxed.
- **Why rejected:** a criterion that is relaxed the first time it fails is not a
  criterion.

### Alternative C — translate `DataError` in the staff error handler

- **Description:** map `sqlalchemy.exc.DataError` to 422 next to the raw
  `40P01`/`40001` cases.
- **Cons:** identical to ADR 3.4.0003's *Alternative A* and rejected for the same
  reasons, plus one more: it would leave the two other invalid names (`""`,
  `"   "`) still issuing a pointless query, since they never raise `DataError` at
  all. It fixes the species and misses the defect.
- **Why rejected:** it would hide the ordering defect behind a handler and make
  the remaining half invisible.

### Alternative D — keep the order and drop the uniqueness probe

- **Description:** rely on the port law L-JF2 (the `update` guard) for the
  conflict, removing `find_by_name` from the use case entirely.
- **Cons:** `test_renomear_para_o_nome_de_outra_funcao_e_conflito_sem_tentar_gravar`
  exists to forbid exactly this: the write must **not be attempted**, and its
  docstring says the test would pass without the probe because the port raises
  the same error type from `update`. Concept 3.2 §5.5 places the check in the use
  case on purpose.
- **Why rejected:** it trades a declared two-layer enforcement for a smaller
  diff.

## Consequences

### Positive

- `PATCH /job-functions/{id}` with a NUL in the name answers **422** with staff's
  body, closing CA22 and the e2e half of CA24 without narrowing either.
- Two of the four name-accepting routes no longer issue a repository query for a
  payload already known to be invalid.
- The law stops depending on one representative: the product test would have
  caught this deviation in Stage 3.2, and will catch the next one.
- `rename_job_function` and `rename_employee` now have the **same** declared
  shape, so the next `rename_*` has an unambiguous neighbour to copy.

### Negative

- **A merged concept's declared ordering is amended.** The cost is real: someone
  reading concept 3.2 offline, from a pre-2026-08-30 checkout, will read the old
  row. The errata is the mitigation, and it is the same mitigation this
  repository already accepts for accepted ADRs.
- **Target-layer expansion**, again — the third time a staff Stage reaches back
  into an earlier one. It is declared, not silent, but the frequency is itself a
  signal, recorded as a `[finding]` in `technical.md` §7.

### Neutral / trade-offs accepted

- The uuid-discard argument that §5.16 makes for `create_job_function` has no
  analogue here: `rename` allocates no identifier, so the reordering has no cost
  at all on the success path — one extra object construction that was going to
  happen anyway, moved two lines up.
- Identity's `rename`-shaped use cases are not audited by this ADR. Out of
  bounded context, and left to whichever Stage owns identity next.

## Implementation notes

- The transition is bound to `renomeada` at step (2) and written at step (4); the
  intermediate `find_by_name` must keep using `command.name`, not
  `renomeada.name` — they are equal, and reading it from the command keeps the
  probe's argument visibly the *requested* name.
- The docstring of the use case previously cited §5.16 to justify the **old**
  order. It is updated in the same commit; a docstring that cites a document to
  defend a shape it no longer has is worse than no docstring.
- The parametrised law lives in
  `tests/unit/features/staff/application/test_invalid_name_never_reaches_the_port.py`,
  and its per-use-case "permitted conduct" is transcribed from §5.16 rather than
  read off the code — expectations derived from the implementation agree with any
  implementation.

## References
- `docs/stages/3.2-staff-application/concept.md` §5.16 — the precedence table,
  its closing note (*"a checagem mais barata que possa falhar sozinha vem
  primeiro"*), and the 2026-08-30 errata this ADR authorises
- `src/restaurant_hub/features/staff/application/use_cases/rename_job_function.py`
- `src/restaurant_hub/features/staff/application/use_cases/create_job_function.py`
  — the module docstring stating the principle
- `src/restaurant_hub/features/staff/domain/entities/job_function.py`
  — `__post_init__` (non-constructibility of an invalid stored name)
- `src/restaurant_hub/features/staff/adapters/out/postgres/mappers.py` — *Regra 1*
  (rehydration always through the constructor)
- `docs/stages/3.6-staff-http/concept.md` CA22, CA24, §6.3
- `docs/stages/3.6-staff-http/technical.md` §7 — the 2026-08-29 `[finding]` that
  measured the 500 and escalated the fork this ADR resolves
- ADR 3.4.0003 (NUL rejected in the domain; precedent for layer expansion and
  source of the rejected boundary alternative), ADR 3.6.0002 (boundary validation
  confined to identifiers), ADR 3.4.0002 (status map), ADR 3.3.0004 (per-operation
  integrity translation), ADR 3.2.0005 (precedent for a later Stage amending an
  earlier one's decision)
- `.claude/skills/stage-audit/SKILL.md` — the *"universal law, narrow
  representative"* defect family

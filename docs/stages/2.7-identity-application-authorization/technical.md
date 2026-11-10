---
title: Technical — Autorização na camada application de identity
description: Plano de execução da Stage 2.7, lista ordenada de Tasks (1 Task = 1 commit) para que os use cases de identity que agem por um ator autorizem o próprio alvo por um port estreito, o convite de dono ganhe use case próprio e a fachada só provisione employee
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity-application-authorization, identity, action-authorizer]
status: done
created_at: 2026-11-09
updated_at: 2026-11-09
stage_id: 2.7-identity-application-authorization
stage_title: Autorização na camada application de identity
step_id: 2
step_title: Restaurante e acesso
depends_on: [3.7-application-authorization]
concept_ref: ./concept.md
issue_id: 184
branch: feat/184-2-7-identity-application-authorization
tasks_count: 10
---

# Technical — Stage 2.7 — Autorização na camada application de identity

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.** Sob orquestração autônoma
>    (PROMPT-stage-single-session §REGRA DE PR), localmente só checks focados — pytest unit de
>    identity e staff, ruff, mypy, `check_layout`, `lint-imports`, `make docs-check` —; o
>    `make check` completo (integração e e2e contra Postgres) roda no GitHub Actions do PR.
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.7/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar** e registrar em [§7 Execução](#7-execução-post-hoc-editável-após-done).

## 1. Contexto e estratégia de execução

### Resumo
Os use cases de identity que agem por um ator (`provision_restaurant`, `create_unit`,
`create_user`, `invite_user` e o novo `invite_owner`) recebem `authorizer: ActionAuthorizer` e
abrem `execute` com uma chamada a `authorize_requirement` (concept R2/R3). Os commands ganham
`actor_id`. `required_permissions_for_role` desce para o módulo do port; a borda delega a
expansão à mesma função. A rota de dono passa a `InviteOwnerUseCase`. A fachada recusa papel que
não seja `employee` com `RoleNotProvisionableError`. Suítes novas travam a propriedade (concept
§11).

### Estratégia
**Inside-out, um grupo de use cases por Task** (skill `task-ordering-hex`), com a restrição que
manda no corte: **toda Task deixa o build verde**, inclusive as varreduras de totalidade
(`_COM_UNIDADE` do composition root, `test_provedor_nao_conectado_falha_alto`, mapa de erros,
escopo de mutação). Cada Task leva a sua entrada nelas.

1. **Task 01** — o que os use cases vão consumir: port, vocabulário, `authorize_requirement`, a
   delegação da borda, os dublês e o escopo de mutação. Nada de use case ainda.
2. **Task 02** — `actor_id` nos quatro commands e o router o passa; use cases o ignoram.
3. **Task 03** — `InviteOwnerUseCase` nasce autorizando, e a rota de dono passa a ele. **Precisa
   vir antes** de `invite_user` autorizar: senão a rota de dono (ator `platform_admin`) seria
   negada pelo requisito composto (concept §10).
4. **Tasks 04–05** — os dois de plataforma e unidade (04); os dois de usuário (05). Cada uma
   acrescenta os seus cenários em `test_use_cases_authorize.py` (CA03/CA04).
5. **Task 06** — as varreduras que só fecham com os cinco: totalidade (CA01), forma AST (CA05),
   identidade do autorizador no grafo (CA07) e alcance dos facade-only (CA14).
6. **Task 07** — cadeia real por papel (CA06, CA12).
7. **Task 08** — a fachada só provisiona `employee` (D5, CA10).
8. **Tasks 09–10** — documentação: identity e ADRs (09); staff (10).

**Exceção declarada ao "≤ 5 arquivos" (PIPELINE §4.3 #2)** nas Tasks 01–05 e 09. Nas 02–05 é a
mesma mudança mecânica propagada pelas suítes que constroem commands e use cases; na 01, mover
`required_permissions_for_role` arrasta os dois importadores (`dependencies.py`, `router.py`) e o
escopo de mutação (`pyproject.toml` + a lista exata que o cobra); na 09, são cinco notas
append-only de uma linha de assunto só. Separar deixaria commits vermelhos ou notas órfãs.

### Pré-condições
- `3.7-application-authorization` `done` (sim; `check_stage_deps` OK).
- Postgres compartilhado: integração e e2e **não** rodam localmente; o CI do PR é a evidência.

### Premissas técnicas
- Python 3.12, `uv sync --extra dev`; `make` pelo Git Bash com MSYS2.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                            (M) 03, 04, 05
└── features/identity/
    ├── application/
    │   ├── ports/out/action_authorizer.py                         (C) 01
    │   ├── use_cases/authorize_action.py                          (M) 01
    │   ├── use_cases/invite_owner.py                              (C) 03
    │   ├── use_cases/{provision_restaurant,create_unit}.py        (M) 04
    │   ├── use_cases/{create_user,invite_user}.py                 (M) 05
    │   ├── use_cases/get_account_role.py                          (M) 09 — só docstring
    │   ├── dtos/commands.py                                       (M) 02, 03
    │   ├── errors.py                                              (M) 08
    │   └── facade.py                                              (M) 08
    └── adapters/inbound/http/
        ├── dependencies.py                                        (M) 01, 05
        ├── router.py                                              (M) 01, 02, 03
        └── error_handlers.py                                      (M) 08
src/restaurant_hub/features/staff/
    ├── application/ports/out/identity_gateway.py                  (M) 10 — só docstring
    └── adapters/out/identity/local_identity_gateway.py            (M) 10 — só docstring
pyproject.toml                                                     (M) 01 — only_mutate
tests/
├── fakes/features/identity/stub_action_authorizers.py            (C) 01
├── unit/test_mutation_scope.py                                    (M) 01
├── unit/features/identity/application/
│   ├── test_authorize_requirement.py                              (C) 01
│   ├── test_use_cases_authorize.py                                (C) 03, (M) 04–06
│   ├── test_invite_owner.py                                       (C) 03
│   ├── test_dtos.py                                               (M) 02
│   ├── test_{provision_restaurant,create_unit,create_user,invite_user,identity_flow}.py (M) 02, 04, 05
│   ├── test_errors.py                                             (M) 08
│   ├── test_application_authorization_chain.py                    (C) 07
│   └── test_facade.py                                             (M) 08
├── unit/features/identity/adapters/
│   ├── test_http_dependencies.py                                  (M) 01
│   ├── test_http_router.py                                        (M) 03, 04, 05
│   └── test_composition_root_identity.py                          (M) 03, 06
└── integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py (M) 02, 04, 05
docs/adr/{2_4_0003,0_0_0014,0_0_0018,3_5_0001,0_0_0020}-*.md           (M) 09 — nota append-only
docs/domain/identity/tenancy-and-access.md                         (M) 09
```

`tests/e2e/` **não aparece** — CA08.

## 2. Tasks

> 10 Tasks — faixa saudável (3–12).

### Task 01 — Port `ActionAuthorizer`, `authorize_requirement` e os dublês

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/ports/out/action_authorizer.py`
  - `tests/fakes/features/identity/stub_action_authorizers.py`
  - `tests/unit/features/identity/application/test_authorize_requirement.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  - `src/restaurant_hub/features/identity/adapters/inbound/http/dependencies.py`
  - `src/restaurant_hub/features/identity/adapters/inbound/http/router.py` (importa
    `required_permissions_for_role` do port: com `mypy --strict`, sem reexport implícito, o
    import via `dependencies` reprovaria)
  - `tests/unit/features/identity/adapters/test_http_dependencies.py`
  - `pyproject.toml` (`[tool.mutmut] only_mutate`) e `tests/unit/test_mutation_scope.py`
- **O que fazer:**
  - Port: `ActionAuthorizer` (Protocol, `execute(AuthorizeActionCommand) -> AuthorizedActor`) e
    `required_permissions_for_role` (corpo e docstring movidos de `dependencies.py`).
  - `authorize_requirement` (concept §4) ao lado de `authorize_at_boundary`; esta passa a tipar o
    primeiro parâmetro como `ActionAuthorizer` e o docstring deixa de dizer "chamador de fora de
    identity" (CA11).
  - `dependencies.py`: reexporta explicitamente `required_permissions_for_role` do port
    (`import … as required_permissions_for_role`), de onde os testes de borda o leem; `router.py`
    importa do port; `IdentityGuard.authorize_all` vira uma chamada a
    `authorize_requirement(self._authorize_action, actor.claims.subject, …)`.
  - Dublês: `DenyingActionAuthorizer` (sentinela `AuthorizationDenied` própria, **mesma
    instância**, registra o command) e `RecordingActionAuthorizer` (registra, devolve
    `AuthorizedActor` infiel); `_conforms: ActionAuthorizer = …` para os dois.
  - Escopo de mutação: o módulo novo entra em `only_mutate` e em `_MODULOS_DE_ACESSO`, com a
    justificativa ao lado (a regra "não se concede o que não se detém").
- **Critério de aceite:**
  - `test_authorize_requirement.py`: expansão em `sorted` × unidades na ordem, sem deduplicar
    (12 pedidos para `owner` × `(U2, U1, U2)`); um pedido com `unit_id=None` por permissão sem
    unidades; primeira recusa interrompe; `UserNotFoundError` → `InvalidAccessTokenError`,
    `UnitNotFoundError` → `UnitNotVisibleError` (com o autorizador real sobre fakes); devolve o
    primeiro `AuthorizedActor`.
  - `test_http_dependencies.py`: por AST, `dependencies.py` importa
    `required_permissions_for_role` do port e não a define; `authorize_all` não tem laço próprio
    (CA09). Os testes de `authorize_all` existentes seguem verdes sem mudança de valor.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity tests/unit/test_mutation_scope.py -q
  uv run ruff check src tests && uv run mypy src tests/fakes && uv run python scripts/check_layout.py && uv run lint-imports
  ```
- **Commit sugerido:** `feat(identity): criar o port do autorizador e a expansão única do requisito [2.7/task-01]`

---

### Task 02 — O ator entra nos quatro commands

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/dtos/commands.py`
  - `src/restaurant_hub/features/identity/adapters/inbound/http/router.py` (quatro rotas:
    `actor_id=actor.claims.subject`; a rota de dono também)
  - `tests/unit/features/identity/application/{test_dtos,test_provision_restaurant,test_create_unit,test_create_user,test_invite_user,test_identity_flow}.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** `actor_id: UserId` como **primeiro** campo de `ProvisionRestaurantCommand`,
  `CreateUnitCommand`, `CreateUserCommand` e `InviteUserCommand`, sem default; os testes passam um
  ator. Use cases **não mudam**.
- **Critério de aceite:** CA02 para os quatro (varredura em `test_dtos.py`: primeiro campo,
  sem default, `TypeError` sem ele); nenhuma outra asserção muda de valor.
- **Comando de verificação:** `uv run pytest tests/unit/features/identity -q` + ruff/mypy.
- **Commit sugerido:** `refactor(identity): levar o ator nos commands dos use cases que agem por ele [2.7/task-02]`

---

### Task 03 — O convite de dono ganha use case próprio, autorizando desde o nascimento

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/invite_owner.py`
  - `tests/unit/features/identity/application/test_invite_owner.py`
  - `tests/unit/features/identity/application/test_use_cases_authorize.py`
- **Arquivos a modificar:**
  - `application/dtos/commands.py` (`InviteOwnerCommand`)
  - `adapters/inbound/http/router.py` (`_get_invite_owner`; rota de dono roda `InviteOwnerUseCase`;
    docstring da rota deixa de dizer que roda `InviteUserUseCase` — CA11)
  - `src/restaurant_hub/composition_root.py` (`identity_invite_owner` no contêiner e no override)
  - `tests/unit/features/identity/adapters/test_http_router.py` (`_Ambiente` monta o novo use case
    com `authorizer=` o mesmo `AuthorizeActionUseCase` do guard; lista de `_get_*`)
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py` (`_COM_UNIDADE`:
    `invite_owner`; `test_wire_dependencies_monta_os_use_cases`)
  - `tests/unit/features/identity/application/test_dtos.py` (CA02 inclui `InviteOwnerCommand`;
    `_TOTAL_DE_DTOS` 27→28, com o comentário de histórico)
- **O que fazer:** use case conforme concept §4 (sequência de `InviteUserUseCase` com
  `role=OWNER`, sem unidades; construtor com `# noqa: PLR0913 — grafo de dependências`, como os
  irmãos); primeira instrução
  `authorize_requirement(self._authorizer, command.actor_id, frozenset({Permission.MANAGE_PLATFORM}), tenant_id=command.tenant_id)`.
  `test_use_cases_authorize.py` nasce com a tabela `CENARIOS` (módulo → montagem com espiões
  sobre fakes semeados + command válido), a transcrição literal `_MATRIZ_R3` e três testes
  parametrizados: CA03 (nega ⇒ sentinela `is`, espiões sem chamada, conjunto espionado =
  parâmetros do construtor menos `authorizer` e escalares), CA04 (sequência exata contra
  `_MATRIZ_R3`) e result/efeito com o autorizador que registra.
- **Critério de aceite:** CA15 (paridade com `InviteUserUseCase` `role=OWNER`, incluindo e-mail
  repetido + restaurante inexistente → `EmailAlreadyRegisteredError`, e falha de envio →
  `InvitationNotSentError` com conta e token comitados); CA03/CA04 para `invite_owner`; testes de
  borda da rota de dono verdes sem mudança de status.
- **Comando de verificação:** `uv run pytest tests/unit/features/identity -q` + ruff/mypy/check_layout.
- **Commit sugerido:** `feat(identity): dar ao convite de dono pela plataforma um use case que autoriza o próprio alvo [2.7/task-03]`

---

### Task 04 — Provisionamento de restaurante e criação de unidade autorizam

- **Arquivos a modificar:**
  - `use_cases/{provision_restaurant,create_unit}.py` (docstring de `provision_restaurant` deixa
    de dizer "A autorização fica na borda" — CA11)
  - `composition_root.py` (2 construções)
  - `tests/unit/features/identity/application/{test_provision_restaurant,test_create_unit,test_identity_flow,test_use_cases_authorize}.py`
  - `tests/unit/features/identity/adapters/test_http_router.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** `authorizer: ActionAuthorizer` como último parâmetro; primeira instrução de
  `execute` conforme R3. Testes de regra de negócio usam `RecordingActionAuthorizer`; integração
  usa o `AuthorizeActionUseCase` real com um `platform_admin` semeado ou o dublê (decidir pelo
  menor desvio; registrar em §7).
- **Critério de aceite:** CA03/CA04 para os dois; suítes existentes verdes.
- **Comando de verificação:** `uv run pytest tests/unit/features/identity -q` + ruff/mypy.
- **Commit sugerido:** `feat(identity): autorizar o provisionamento de restaurante e a criação de unidade [2.7/task-04]`

---

### Task 05 — Criação e convite de usuário autorizam o requisito composto

- **Arquivos a modificar:**
  - `use_cases/{create_user,invite_user}.py` (docstrings de módulo: a ordem de checagens vale
    depois da autorização; os ramos `is_platform_admin` ficam como defesa em profundidade —
    concept D6; CA11)
  - `adapters/inbound/http/dependencies.py` (docstring de `authorize_all`: "seria alcançado com
    unidades não-visíveis" — CA11)
  - `composition_root.py` (2 construções)
  - `tests/unit/features/identity/application/{test_create_user,test_invite_user,test_identity_flow,test_use_cases_authorize}.py`
  - `tests/unit/features/identity/adapters/test_http_router.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_use_cases_atomicos.py`
- **O que fazer:** primeira instrução
  `authorize_requirement(self._authorizer, command.actor_id, required_permissions_for_role(command.role), tenant_id=command.tenant_id, unit_ids=command.unit_ids)`.
  `CreateUserUseCase.__init__` passa a 6 parâmetros: `# noqa: PLR0913 — grafo de dependências`.
- **Critério de aceite:** CA03/CA04 para os cinco (inclui o cenário discriminante de 12 pedidos).
- **Comando de verificação:** `uv run pytest tests/unit/features/identity -q` + ruff/mypy.
- **Commit sugerido:** `feat(identity): autorizar a criação e o convite de usuário pelo requisito composto [2.7/task-05]`

---

### Task 06 — Totalidade, forma e grafo

- **Arquivos a modificar:**
  - `tests/unit/features/identity/application/test_use_cases_authorize.py`
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
- **O que fazer:**
  - CA01: `set(CENARIOS) | set(_EXCLUSOES) == módulos de use_cases/` (sem `_`), disjuntos;
    `_EXCLUSOES` é um dict módulo → motivo (as dez do ADR 0.0.0020); `authorizer: ActionAuthorizer`
    no construtor de todo afetado e de nenhuma exclusão.
  - CA05: AST de todo `execute` afetado — descontado o docstring, a primeira instrução é
    `Expr(Call(Name('authorize_requirement'), [self._authorizer, <p>.actor_id, <perms>], tenant_id=…[, unit_ids=…]))`
    com os argumentos da `_MATRIZ_R3`; nenhuma outra chamada a `authorize_requirement` ou a
    `self._authorizer` no corpo.
  - CA07: `deps.identity_<uc>._authorizer is deps.identity_authorize_action` para os cinco.
  - CA14: varredura AST de `src/`: só `facade.py` e `composition_root.py` importam os módulos
    facade-only.
- **Critério de aceite:** CA01, CA05, CA07, CA14 verdes; mutação manual (linha antes da
  autorização; autorização condicional) reprova CA05 — colado em §7.
- **Comando de verificação:** `uv run pytest tests/unit/features/identity -q`.
- **Commit sugerido:** `test(identity): travar a autorização sobre a pasta de use cases, a forma e o grafo [2.7/task-06]`

---

### Task 07 — Cadeia real por papel

- **Arquivos a criar:**
  - `tests/unit/features/identity/application/test_application_authorization_chain.py`
- **O que fazer:** `AuthorizeActionUseCase` real sobre `InMemoryUserRepository`/
  `InMemoryUnitRepository` com tenants A e B; cada célula da matriz da cadeia real (concept §6) dá
  o tipo exato e nenhum efeito; controles positivos; CA12 (ator inexistente →
  `InvalidAccessTokenError`; unidade inexistente → `UnitNotVisibleError`).
- **Critério de aceite:** CA06 e CA12 verdes.
- **Comando de verificação:** `uv run pytest tests/unit/features/identity -q`.
- **Commit sugerido:** `test(identity): provar pela cadeia real que nenhum papel cria platform_admin nem dono em tenant alheio [2.7/task-07]`

---

### Task 08 — A fachada só provisiona `employee`

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/errors.py` (`RoleNotProvisionableError`)
  - `src/restaurant_hub/features/identity/application/facade.py` (checagem como primeira
    instrução de `provision_account`; docstring da propriedade 3 — CA11)
  - `src/restaurant_hub/features/identity/adapters/inbound/http/error_handlers.py` (entrada do mapa, status 422)
  - `tests/unit/features/identity/application/test_facade.py`
  - `tests/unit/features/identity/application/test_errors.py` (conjunto exato de nomes e
    `_DE_APLICACAO`; `test_http_error_handlers.py` e `tests/unit/test_status_map.py` derivam do mapa)
- **Critério de aceite:** CA10.
- **Comando de verificação:** `uv run pytest tests/unit/features/identity tests/unit/features/staff -q`.
- **Commit sugerido:** `feat(identity): restringir a fachada ao provisionamento de funcionário [2.7/task-08]`

---

### Task 09 — Documentação de identity e notas nos ADRs

- **Arquivos a modificar:**
  - `docs/adr/{2_4_0003,0_0_0014,0_0_0018,3_5_0001,0_0_0020}-*.md` (nota datada append-only)
  - `docs/domain/identity/tenancy-and-access.md`
  - `src/restaurant_hub/features/identity/application/use_cases/get_account_role.py` (docstring)
- **Critério de aceite:** CA11 (as frases listadas não existem); `make docs-check` verde.
- **Comando de verificação:** `make docs-check` + `git grep -F` de cada frase de CA11.
- **Commit sugerido:** `docs(identity): registrar a autorização na application de identity nos ADRs e no doc de domínio [2.7/task-09]`

---

### Task 10 — Docstrings de staff

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/ports/out/identity_gateway.py`
  - `src/restaurant_hub/features/staff/adapters/out/identity/local_identity_gateway.py`
- **Critério de aceite:** CA11 nos dois.
- **Comando de verificação:**
  ```bash
  uv run ruff check src && git grep -F "identity não autoriza na application" -- src/restaurant_hub/features/staff   # vazio
  uv run pytest tests/unit/features/staff -q
  ```
- **Commit sugerido:** `docs(staff): atualizar o que o gateway de identity diz sobre a autorização de identity [2.7/task-10]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
# CI do PR (lint-and-test): make check completo, com integração e e2e
python scripts/check_technical_postexec.py docs/stages/2.7-identity-application-authorization/technical.md
git diff --exit-code --stat origin/develop -- tests/e2e          # CA08
git grep -n "def required_permissions_for_role" -- src             # CA09: só o port
uv run coverage report --fail-under=90 --include="<arquivos de src/ tocados>"   # CA13
```

### Matriz CA → Task

| CA | Onde | Check |
|---|---|---|
| CA01 | 06 | pasta = afetados ∪ exclusões nomeadas |
| CA02 | 02, 03 | varredura dos campos dos commands |
| CA03 | 03–05 | `CENARIOS` × autorizador que nega, espiões |
| CA04 | 01 (expansão), 03–05 | sequência exata contra `_MATRIZ_R3` |
| CA05 | 06 | AST de todo `execute` afetado |
| CA06 | 07 | cadeia real × matriz de §6 |
| CA07 | 06 | identidade do autorizador no grafo |
| CA08 | gate | `tests/e2e` intocado + CI verde |
| CA09 | 01 | AST de `dependencies.py` |
| CA10 | 08 | fachada × papéis |
| CA11 | 01, 03, 04, 05, 08, 09, 10 | `git grep -F` das frases |
| CA12 | 07 | traduções pela cadeia real |
| CA13 | gate | CI + cobertura por arquivo |
| CA14 | 06 | AST de imports em `src/` |
| CA15 | 03 | paridade com `InviteUserUseCase` |

### Verificações funcionais
- [ ] Driver em processo sobre `wire_dependencies` (fora do repo): `owner` de A tentando
      `identity_create_user` com `role=platform_admin` e com `owner` em B é negado sem efeito.
- [ ] Faixas HTTP: e2e de identity verde no CI (inalterado).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] CI do PR verde
- [ ] Commit final `stage 2.7: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at` e `last_reviewed_at`
- [ ] ADR 2.7.0001 em `accepted`
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10
```
03 antes de 05 é obrigatório (rota de dono). 04 e 05 compartilham `test_use_cases_authorize.py`,
`composition_root.py` e `test_http_router.py`; a ordem linear evita conflito. 06 exige os cinco.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Teste de integração monta use case fora dos fakes e quebra ao ganhar `authorizer` | passar o `AuthorizeActionUseCase` real sobre os repositórios Postgres com ator semeado; registrar `[deviation]` |
| CA05 rígido para uma forma legítima | ajustar o use case à forma (R2), nunca relaxar a varredura sem `[decision]` |
| Integração/e2e só verificáveis no CI | empurrar cedo e acompanhar o run; não rodar localmente (Postgres compartilhado) |

## 6. Referências

- [`./concept.md`](./concept.md); ADR [2.7.0001](../../adr/2_7_0001-identity-authorizes-through-a-narrow-port.md)
- [`../../roadmap.md`](../../roadmap.md) §Stage 2.7; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4
- Technical de referência: [`3.7`](../3.7-application-authorization/technical.md)
- Skills: `hex-arch-python`, `composition-root`, `pytest-with-fakes`, `fastapi-thin-adapter`,
  `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-11-09 — [deviation] Task 01 — a borda não reexporta `required_permissions_for_role` — Claude
**Contexto:** a Task 01 mandava `dependencies.py` reexportar a função do port (`import … as …`), e o CA09 do concept diz que `dependencies.py` "a importa de lá".
**Razão:** o ruff do projeto recusa o alias redundante (PLC0414) e o `mypy --strict` recusa o reexport implícito; e `dependencies.py` não usa a função. Quem a usa (`router.py`) e os testes de borda (`test_http_dependencies.py`) passaram a importá-la do port. O CA09 fica cumprido no que importa — uma definição só, no port, e a borda sem cópia (teste AST) —, sem a parte "dependencies importa". O docstring do port, que dizia "a borda a reexporta", foi corrigido no `[2.7/task-01-fix]` (Checkpoint C do bloco 01–03).

### 2026-11-09 — [decision] Task 04 — a integração usa o dublê que concede, não o autorizador real — Claude
**Contexto:** a Task 04 deixava para a execução escolher, em `test_use_cases_atomicos.py`, entre o `AuthorizeActionUseCase` real sobre os repositórios Postgres (com um ator semeado) e o dublê.
**Pergunta:** qual autorizador as suítes de atomicidade recebem?
**Opções:**
- A — o real, com `platform_admin`/`owner` semeados em cada cenário
- B — `RecordingActionAuthorizer` ✅ recomendada
**Decisão:** B
**Razão:** as suítes medem a atomicidade das escritas (falha na N-ésima escrita ⇒ banco inalterado), não o acesso; o real exigiria semear um ator em cada uma e acrescentaria leituras ao registro de escritas que elas conferem. O acesso pela cadeia real está na suíte unitária da Task 07 e, pelo HTTP com Postgres, no e2e (a borda e o use case decidem sobre o mesmo `AuthorizeActionUseCase`). Reversível e barato, sem âncora de princípio — registrado por isso.

### 2026-11-09 — [measurement] Task 06 — mutações manuais que o CA05 reprova — Claude
**Contexto:** o critério de aceite da Task 06 pede a prova de que a forma AST reprova uma linha antes da autorização e uma autorização condicional.
**Medição:** em `create_unit.py`, `if command.name: pass` inserido antes da chamada a `authorize_requirement`; `uv run pytest tests/unit/features/identity -q` → `FAILED …test_use_cases_authorize.py::test_a_primeira_instrucao_de_execute_e_a_autorizacao_de_r3[create_unit]` — `1 failed, 1126 passed`; arquivo restaurado por `git checkout`. A autorização condicional (`if …: authorize_requirement(...)`) cai na mesma asserção, porque a primeira instrução deixa de ser um `ast.Expr` de chamada (`assert isinstance(primeira, ast.Expr)`).
**Razão:** prova que o CA05 enxerga a ordem e a incondicionalidade, não só a presença da chamada.

### 2026-11-09 — [deviation] Task 06 (fix) — import relativo na varredura de alcance e docstring da rota de usuário — Claude
Checkpoint C do bloco 04–06: (1) a varredura do CA14 só via import absoluto; `from .provision_account import …` passaria em silêncio. Passou a resolver os dois idiomas relativos, com um teste de controle. (2) O docstring de `router.py` › `create_user` ainda dizia que, sem a autorização da borda, o use case seria alcançado com unidade não-visível — falso desde a Task 05; reescrito como o de `authorize_all`. Commit `[2.7/task-06-fix]`.

<!-- END: post-execution -->

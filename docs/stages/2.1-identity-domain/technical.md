---
title: Technical — Domínio de tenancy e acesso
description: Plano de execução da Stage 2.1 — lista ordenada de Tasks (1 Task = 1 commit) para o domínio do BC identity
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity-domain, tenancy, rbac]
status: done
created_at: 2026-07-17
updated_at: 2026-07-17
stage_id: 2.1-identity-domain
stage_title: Domínio de tenancy e acesso
step_id: 2
step_title: Restaurante e acesso
depends_on: [1.2-ci]
concept_ref: ./concept.md
issue_id: 17
branch: feat/17-2-1-identity-domain
tasks_count: 7
---

# Technical — Stage 2.1 — Domínio de tenancy e acesso

> **Como usar (code assistant):** ler §1; executar Tasks em ordem (§2), 1 Task =
> 1 commit; `make check` verde antes de todo commit; registrar desvios em §7.

## 1. Contexto e estratégia de execução

### Resumo
Primeiro código de domínio do projeto (BC `identity`, camada `domain` pura, sem
I/O). Modela `Restaurant`/`Unit`/`User` (entities), `Email`/`Role`/`Permission`/
`UnitMembership` (VOs) e as exceções do BC, com as invariantes de isolamento
(tenancy) e RBAC cobertas por testes unitários. Ver [`concept.md`](./concept.md).

### Estratégia
**Inside-out (TDD), bottom-up** (skill `task-ordering-hex`): tipos-folha primeiro
(identifiers, exceptions, VOs simples), depois entidades que os compõem, por fim o
`User` que amarra tenancy + RBAC + visibilidade. Cada commit deixa `make check`
verde. A ordem respeita as dependências de import: `User` (Task 07) depende de
`Email`, `Role`, `Permission`, `Unit`, `UnitMembership` e das exceções — todos
criados antes.

### Pré-condições
- `1.2-ci` em `done` e **mergeada** em `develop` (verificado: commit
  `stage 1.2: complete` em `origin/develop`).
- Concept desta Stage em `status: done` (commit `stage 2.1: conceptual approved`).
- `.venv` da worktree instalado (`make setup` já rodado no bootstrap da worktree).

### Premissas técnicas
- Python 3.12 (`StrEnum`, `NewType`).
- Domínio importa **só** stdlib + `shared/domain` (LAYOUT §3); `IdentityError`
  herda de `shared.domain.exceptions.base.DomainError`.
- `make check` = ruff + mypy strict + `check_layout.py` + import-linter +
  lock-check + docs-check + test-gate (cobertura ≥ 90%). Rodar via PowerShell:
  `$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check`.

### Estrutura de pastas afetada

```
src/restaurant_hub/features/identity/
├── __init__.py
├── application/__init__.py          # placeholder vazio (check_layout REQUIRED_FEATURE_DIRS)
├── adapters/__init__.py             # placeholder vazio (idem)
└── domain/
    ├── __init__.py
    ├── entities/{__init__,restaurant,unit,user}.py
    ├── value_objects/{__init__,identifiers,email,permission,role,unit_membership}.py
    └── exceptions/{__init__,errors}.py
tests/unit/features/identity/
├── __init__.py
└── domain/{__init__,test_identifiers,test_exceptions,test_email,
             test_role_permission,test_restaurant,test_unit,
             test_unit_membership,test_user,test_visibility}.py
.importlinter                        # + contrato forbidden identity.domain
```

## 2. Tasks

> 7 Tasks. `__init__.py` são vazios (import por caminho absoluto, LAYOUT §7).
> Escopo do commit = `identity` (ASCII/kebab).

### Task 01 — Scaffold da feature, identificadores tipados e contrato import-linter

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/__init__.py` (vazio)
  - `src/restaurant_hub/features/identity/application/__init__.py` (vazio, placeholder)
  - `src/restaurant_hub/features/identity/adapters/__init__.py` (vazio, placeholder)
  - `src/restaurant_hub/features/identity/domain/__init__.py` (vazio)
  - `src/restaurant_hub/features/identity/domain/entities/__init__.py` (vazio)
  - `src/restaurant_hub/features/identity/domain/value_objects/__init__.py` (vazio)
  - `src/restaurant_hub/features/identity/domain/exceptions/__init__.py` (vazio)
  - `src/restaurant_hub/features/identity/domain/value_objects/identifiers.py`
  - `tests/unit/features/identity/__init__.py` (vazio)
  - `tests/unit/features/identity/domain/__init__.py` (vazio)
  - `tests/unit/features/identity/domain/test_identifiers.py`
- **Arquivos a modificar:** `.importlinter`
- **O que fazer:** criar a árvore de pacotes da feature `identity` (incluindo os
  placeholders vazios `application/` e `adapters/`, exigidos por
  `check_layout.py`). Em `identifiers.py`, definir `RestaurantId`, `UnitId`,
  `UserId` como `NewType(..., str)`. Em `.importlinter`, adicionar um contrato
  `type = forbidden` com `source_modules = restaurant_hub.features.identity.domain`
  e `forbidden_modules` = frameworks/boundary (`fastapi`, `starlette`, `uvicorn`,
  `sqlalchemy`, `alembic`, `pydantic`, `pydantic_settings`, `httpx`) +
  `restaurant_hub.shared.application` + `restaurant_hub.shared.infrastructure`.
  **Não** proibir `restaurant_hub.features` (auto-proibiria imports internos de
  identity) nem `restaurant_hub.shared.domain` (dependência legítima).
- **Detalhes técnicos:** `NewType` sobre `str`; sem lógica de runtime. O teste
  cobre o módulo importando e afirmando que `RestaurantId("r1") == "r1"` (NewType
  devolve o próprio valor) e que os três nomes existem.
- **Critério de aceite:** `make check` verde (layout-check reconhece os 3
  diretórios; import-linter aceita o novo contrato); `test_identifiers.py` passa.
- **Nota de atomicidade (exceção consciente, PIPELINE §4.3):** esta Task estoura o
  guia de ≤5 arquivos (11 criados + `.importlinter`) por ser o scaffold da 1ª
  feature — 8 são `__init__.py` **vazios** (0 statements); o conteúdo lógico
  não-trivial é só `identifiers.py` + o contrato de import (ambos mínimos e
  atados ao scaffold para manter o commit não-vazio e `make check` verde). Exceção
  de scaffold mecânico, declarada. Subject ASCII segue a prática do repo (histórico
  de commits sem acento no subject).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): criar scaffold, identificadores e contrato de import [2.1/task-01]`

---

### Task 02 — Exceções de domínio do BC identity

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/domain/exceptions/errors.py`
  - `tests/unit/features/identity/domain/test_exceptions.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** definir `IdentityError(DomainError)` (base do BC, importando
  `DomainError` de `restaurant_hub.shared.domain.exceptions.base`) e as subclasses:
  `InvalidEmailError`, `InvalidRoleError`, `MissingTenantError`,
  `PlatformAdminTenantError`, `PlatformAdminMembershipError`, `CrossTenantError`.
  Cada uma com docstring PT curta; construtor pode aceitar um valor de contexto e
  montar a mensagem PT (ex.: `InvalidRoleError(value)` → `"papel inválido: <value>"`).
- **Detalhes técnicos:** hierarquia — todas subclasses de `IdentityError`, que é
  subclasse de `DomainError`. Sem estado além da mensagem.
- **Critério de aceite:** `test_exceptions.py` cobre: `IdentityError` é
  `DomainError`; cada subclasse é `IdentityError`; a mensagem é preservada ao
  levantar (`pytest.raises(..., match=...)`).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): adicionar excecoes de dominio [2.1/task-02]`

---

### Task 03 — Value object `Email`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/domain/value_objects/email.py`
  - `tests/unit/features/identity/domain/test_email.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True)` `Email` com `value: str`. No
  `__post_init__`: normalizar (`value.strip().lower()`) via
  `object.__setattr__(self, "value", normalizado)` e validar formato pragmático
  (`^[^@\s]+@[^@\s]+\.[^@\s]+$`). Inválido → `InvalidEmailError(value)`.
- **Detalhes técnicos:** normaliza antes de validar; frozen ⇒ igualdade estrutural
  e hashável (útil para dedup lógica). Não implementa RFC 5322 (concept §7).
- **Critério de aceite:** `test_email.py` cobre: normalização (`"  A@B.COM " → "a@b.com"`);
  igualdade por valor após normalização; rejeição de malformados (sem `@`, sem
  ponto no domínio, com espaço interno, vazio) com `InvalidEmailError`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): adicionar value object Email [2.1/task-03]`

---

### Task 04 — Value objects `Permission` e `Role` + mapeamento RBAC

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/domain/value_objects/permission.py`
  - `src/restaurant_hub/features/identity/domain/value_objects/role.py`
  - `tests/unit/features/identity/domain/test_role_permission.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `Permission(StrEnum)` = `{MANAGE_PLATFORM, MANAGE_TENANT,
  MANAGE_USERS}`. `Role(StrEnum)` = `{PLATFORM_ADMIN, OWNER, MANAGER, HR,
  EMPLOYEE}` com valores `"platform_admin"` etc. `Role.from_string(value) -> Role`
  (parse defensivo → `InvalidRoleError`). Mapa module-level
  `_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]]` **total** conforme
  concept §5.6; `Role.permissions` (property) devolve `_ROLE_PERMISSIONS[self]`.
- **Detalhes técnicos:** o mapa deve ter entrada para **todos** os 5 papéis
  (guardar por teste de exaustividade iterando `Role`); `employee` → `frozenset()`.
  Mapa concreto: platform_admin→{MANAGE_PLATFORM}; owner→{MANAGE_TENANT,
  MANAGE_USERS}; manager→{MANAGE_USERS}; hr→{MANAGE_USERS}; employee→{}.
- **Critério de aceite:** `test_role_permission.py` cobre: conjunto fechado dos 5
  papéis; `from_string` válido e `InvalidRoleError` no desconhecido; **conteúdo
  exato** do mapa por papel; exaustividade (todo `Role` tem entrada); separação
  plataforma×restaurante (platform_admin sem `MANAGE_TENANT`/`MANAGE_USERS`; nenhum
  papel de restaurante com `MANAGE_PLATFORM`); igualdade por valor do enum.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): adicionar Role, Permission e mapa RBAC [2.1/task-04]`

---

### Task 05 — Entidades `Restaurant` e `Unit`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/domain/entities/restaurant.py`
  - `src/restaurant_hub/features/identity/domain/entities/unit.py`
  - `tests/unit/features/identity/domain/test_restaurant.py`
  - `tests/unit/features/identity/domain/test_unit.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `Restaurant` (`id: RestaurantId`, `name: str`) e `Unit`
  (`id: UnitId`, `restaurant_id: RestaurantId`, `name: str`). Ambas com igualdade
  por identidade (`__eq__`/`__hash__` por `id`, `@dataclass(eq=False)`), validação
  de `name` não-vazio no `__post_init__` (→ `ValueError` — dado estrutural, não
  regra de negócio) e property `tenant_id -> RestaurantId` (`Restaurant.tenant_id`
  = `self.id`; `Unit.tenant_id` = `self.restaurant_id`).
- **Detalhes técnicos:** entidades comparam por id (skill DDD); dois `Restaurant`
  com mesmo id são iguais mesmo com `name` diferente. `name` vazio/whitespace →
  `ValueError` (validação de campo estrutural, sem exceção de domínio dedicada —
  não é invariante de negócio da Stage).
- **Critério de aceite:** testes cobrem: construção válida; igualdade por id
  (mesmo id ⇒ igual; id diferente ⇒ diferente); `tenant_id` correto; `name` vazio
  → `ValueError`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): adicionar entidades Restaurant e Unit [2.1/task-05]`

---

### Task 06 — Value object `UnitMembership`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/domain/value_objects/unit_membership.py`
  - `tests/unit/features/identity/domain/test_unit_membership.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True)` `UnitMembership` com `user_id: UserId`
  e `unit_id: UnitId`. Esqueleto mínimo (concept §7 / ADR 2.1.0001) — **sem** papel
  por unidade. Igualdade estrutural (frozen dá de graça).
- **Detalhes técnicos:** VO puro, sem validação além dos tipos; é criado por
  `User.link_to_unit` (Task 07), que impõe as invariantes de tenancy. `user_id`
  existe para o filtro de visibilidade da Task 07.
- **Critério de aceite:** `test_unit_membership.py` cobre: construção; igualdade
  por valor (mesmos `user_id`+`unit_id` ⇒ igual; diferente ⇒ diferente);
  hashável.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): adicionar value object UnitMembership [2.1/task-06]`

---

### Task 07 — Entidade `User` (tenancy + RBAC + visibilidade)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/domain/entities/user.py`
  - `tests/unit/features/identity/domain/test_user.py`
  - `tests/unit/features/identity/domain/test_visibility.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `User` (`id: UserId`, `email: Email`, `role: Role`,
  `tenant_id: RestaurantId | None`), `@dataclass(eq=False)` com igualdade por id.
  `__post_init__` impõe a invariante condicional de tenancy (ADR 2.1.0002):
  platform_admin com `tenant_id` → `PlatformAdminTenantError`; não-plataforma sem
  `tenant_id` → `MissingTenantError`. Métodos:
  - `has_permission(p: Permission) -> bool` → `p in self.role.permissions`.
  - `bypasses_unit_scope() -> bool` → `self.role in (Role.OWNER, Role.PLATFORM_ADMIN)`.
  - `link_to_unit(unit: Unit) -> UnitMembership` → platform_admin →
    `PlatformAdminMembershipError`; `self.tenant_id != unit.tenant_id` →
    `CrossTenantError`; senão `UnitMembership(self.id, unit.id)`.
  - `can_view_unit(unit: Unit, memberships: Iterable[UnitMembership]) -> bool` →
    platform_admin → `True` (short-circuit **antes** de comparar tenant, pois
    `tenant_id` é `None`); `self.tenant_id != unit.tenant_id` → `False`;
    `bypasses_unit_scope()` (owner) → `True`; senão `any(m.user_id == self.id and
    m.unit_id == unit.id for m in memberships)`.
- **Detalhes técnicos:** ordem das checagens em `can_view_unit` é crítica
  (platform_admin primeiro). O filtro de membership casa `user_id` **e** `unit_id`
  (Checkpoint A M1 — membership de outro usuário não concede acesso). `Iterable`
  de `collections.abc`.
- **Critério de aceite:** `test_user.py` cobre: construção válida (cada papel);
  `MissingTenantError`; `PlatformAdminTenantError`; platform_admin com
  `tenant_id=None` válido; `has_permission` por papel; igualdade por id.
  `test_visibility.py` cobre: `link_to_unit` sucesso + `CrossTenantError` +
  `PlatformAdminMembershipError`; `can_view_unit` — owner bypass, platform_admin vê
  qualquer unidade, employee/manager/hr só via membership própria, **membership de
  outro usuário não concede**, cross-tenant sempre `False`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"; make check
  ```
- **Commit sugerido:** `feat(identity): adicionar entidade User com invariantes [2.1/task-07]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```powershell
$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
make check                                                   # lint+mypy+layout+import-linter+lock+docs+test-gate
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing  # cobertura por arquivo ≥ 90%
uv run python scripts/check_technical_postexec.py "docs/stages/2.1-identity-domain/technical.md"
```

### Verificações funcionais
- [ ] Stage é **domínio puro** (sem runtime: sem API/CLI/job). A verificação
      "end-to-end" se satisfaz pelos **testes unitários exercitando as invariantes**
      de negócio (isolamento de tenant, papel inválido, e-mail inválido,
      platform_admin sem tenant, escopo de visibilidade) — não há entrypoint a
      rodar. Não inventar e2e inexistente.

### Checklist de fechamento da Stage
- [ ] Todas as 7 Tasks commitadas, cada uma com `make check` verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥ 90% em cada arquivo `src/` tocado (term-missing)
- [ ] Auditoria de testes (subagente independente) com todos os itens "sim"
- [ ] Commit final `stage 2.1: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at`/`last_reviewed_at`
      2026-07-17, linha no §Histórico, e **nota datada** reconciliando o bloco 2.1
      (file-scope `.importlinter`/placeholders; `contratos_introduzidos`/
      `_consumidos`)
- [ ] ADRs `2_1_0001`, `2_1_0002` em `status: accepted`
- [ ] `concept.md` não precisa retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (scaffold+identifiers+importlinter)
   ├─► Task 02 (exceptions) ─► Task 03 (Email)
   │                        ─► Task 04 (Role+Permission)   [usa InvalidRoleError]
   ├─► Task 05 (Restaurant+Unit)                           [usa identifiers]
   └─► Task 06 (UnitMembership)                            [usa identifiers]
Task 03,04,05,06 ─► Task 07 (User)   [usa Email,Role,Permission,Unit,UnitMembership,exceptions]
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| import-linter falha por pacote externo não instalado no forbidden | remover o pacote não instalado da lista (mantendo os presentes); registrar `[deviation]` §7 |
| `check_layout.py` reclama de feature sem `application/`/`adapters/` | garantir os `__init__.py` placeholders (Task 01) |
| Cobertura < 90% num arquivo `__init__` vazio | `__init__.py` sem statements = 100%; não adicionar docstring que crie linha não-coberta |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito e invariantes.
- ADRs: [`../../adr/2_1_0001-identity-aggregates-and-membership.md`](../../adr/2_1_0001-identity-aggregates-and-membership.md),
  [`../../adr/2_1_0002-platform-admin-without-tenant.md`](../../adr/2_1_0002-platform-admin-without-tenant.md)
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §1, §4.
- Skills: `ddd-tactical-patterns`, `hex-arch-python`, `task-ordering-hex`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. Apenas esta seção é editável após
> `status: done` (enquanto a Stage não mergeou). Modo autônomo (ADR 0.0.0004):
> decisões reversíveis-baratas são registradas aqui como `[decision]` sem pergunta.

### 2026-07-18 — [decision] Task 01 — contrato import-linter e pacotes-placeholder — Claude (autônomo)
**Contexto:** identity é a 1ª feature-slice do repo. `scripts/check_layout.py`
(`REQUIRED_FEATURE_DIRS`) exige `domain/`, `application/` e `adapters/` em toda
feature, e o `.importlinter` marcava contratos de feature como "ativar quando a 1ª
feature existir". O bloco do roadmap 2.1 declara `arquivos_a_modificar: []`.
**Pergunta:** instalar agora o contrato de pureza de `identity.domain` (e os
pacotes-placeholder), ou adiar para a 2.2 quando a camada application existir?
**Opções:**
- A — adiar tudo para a 2.2, mantendo o file-scope do roadmap literal
- B — instalar o contrato `forbidden` de `identity.domain` + placeholders agora ✅ recomendada
**Decisão:** B.
**Razão:** `check_layout.py` **obriga** os placeholders (sem eles o gate falha), então
o file-scope já se expande de qualquer modo; e a Stage de domínio é o lugar natural
para instalar a pureza do domínio. O import-linter é mais estrito que o
`check_layout.py` (pega `starlette`/`httpx`/`alembic`, que o AST-checker não lista).
Reversível barato. O contrato é **puramente aditivo** — nenhum contrato existente foi
afrouxado (verificado no diff; `lint-imports` reporta 5 contratos KEPT). Independence
entre BCs e layers-por-feature seguem adiados (2º BC / camada application). O bloco do
roadmap foi reconciliado com nota datada no fechamento, no padrão das notas 1.1/1.2.

### 2026-07-18 — [deviation] Tasks 05/07 — entidades imutáveis (`frozen=True`) — Claude (autônomo)
**Contexto:** o technical especificava `@dataclass(eq=False)` para `Restaurant`,
`Unit` e `User`. A revisão independente do bloco final demonstrou empiricamente que,
com campos públicos mutáveis, a invariante de tenancy era furável **após** a
construção: `emp.role = Role.PLATFORM_ADMIN` transformava um employee com tenant em
admin de plataforma e passava a enxergar unidade de outro tenant.
**Razão:** a skill `ddd-tactical-patterns` exige invariante imposta no construtor
**e** nos métodos que mutam estado, e "entidade nunca exposta em estado inválido".
Como esta Stage não tem operação de mutação, `frozen=True` é a forma mínima que fecha
o buraco; mudança de estado legítima passa a ser `dataclasses.replace`, que reexecuta
`__post_init__` e revalida. Fecha também o caminho silencioso de reidratação por
atribuição no mapper da Stage 2.3. Abaixo do limiar de regressão do technical: não
muda contrato, fronteira nem critério de aceite — endurece a implementação deles.

### 2026-07-18 — [deviation] Task 05 — `InvalidNameError`/`InvalidIdentifierError` no lugar de `ValueError` — Claude (autônomo)
**Contexto:** o technical (Task 05) mandava levantar `ValueError` para nome vazio,
tratando-o como "dado estrutural, não regra de negócio". A auditoria de testes
verificou o handler já registrado em `shared/infrastructure/http/error_handlers.py`:
ele captura `NotFoundError` (404) e `DomainError` (422); um `ValueError` escapa dos
dois e vira **500**. A auditoria seguinte encontrou ainda que identificador vazio
(`id`/`tenant_id` = `""`) era aceito, criando um balde de falso isolamento no qual
todos os "sem tenant" se enxergariam.
**Razão:** o concept §6 fecha com "todas subclasses de `IdentityError` → `DomainError`";
manter `ValueError` contradiz isso e planta um 500 na 2.4. Foram criadas
`InvalidNameError` e `InvalidIdentifierError`, ambas `IdentityError`. **Nota de
precisão para a auditoria:** o concept §6 **não enumera** estes dois cenários (a
validação de `name` nasceu no technical, não no concept) — optei por registrar o
desvio aqui em vez de regredir o concept, por proporcionalidade; a divergência fica
visível para a auditoria de contexto limpo decidir se merece retoque do concept.

### 2026-07-18 — [deviation] Tasks 05/07 — `__eq__` devolve `NotImplemented` — Claude (autônomo)
**Contexto:** a implementação original devolvia `False` para tipo alheio, o que
impede o Python de consultar o `__eq__` refletido do outro operando.
**Razão:** quebra a comparação simétrica e faz `mock.ANY` falhar de forma não-óbvia —
padrão comum nos testes de use case (2.2) e de mapper (2.3). Correção de protocolo,
sem efeito sobre `set`/`dict` (o `__hash__` por id foi mantido).

### 2026-07-18 — [finding] `name` não é normalizado nas entidades — Claude (autônomo)
**Contexto:** `Email` normaliza (trim + lowercase) e guarda o valor normalizado; já
`Restaurant.name`/`Unit.name` **validam** com `.strip()` mas **armazenam o valor cru**
(`Restaurant(name="  Cantina  ").name == "  Cantina  "`). Nada no concept exige
normalizar `name`, então ficou fora do escopo desta Stage.
**Direção sugerida:** decidir na persistência se `name` é normalizado na escrita
(afeta unicidade e ordenação por nome).
**Stage candidata:** `2.3-identity-persistence`.

### 2026-07-18 — [finding] precedência entre validações do `__post_init__` não é especificada — Claude (autônomo)
**Contexto:** quando `id` vazio e `tenant_id` ausente coincidem, a exceção levantada
depende da ordem das checagens no `__post_init__` (hoje: `InvalidIdentifierError`).
O concept §6 mapeia cenário→exceção mas não fixa precedência quando dois cenários
coincidem. Mutação que reordena as checagens sobrevive à suíte — é comportamento
**não especificado**, não falso verde (ambas são `IdentityError` → mesmo 4xx na 2.4).
**Direção sugerida:** se a API precisar de mensagem determinística por campo, fixar a
precedência no concept e cobrir por teste.
**Stage candidata:** `2.4-identity-http`.

### 2026-07-18 — [deviation] datas dos artefatos — Claude (autônomo)
**Contexto:** `concept.md`, `technical.md` e os dois ADRs carregam
`created_at/updated_at: 2026-07-17` (data informada no kickoff da corrida); a execução
atravessou a virada do dia e a Stage fechou em **2026-07-18**, data usada no
`roadmap.md` e nesta §7. O `technical.md` §1–§6 está congelado enquanto a Stage não
mergeia (`check_technical_postexec.py`), então a data não foi reescrita
retroativamente — o registro honesto fica aqui.

<!-- END: post-execution -->

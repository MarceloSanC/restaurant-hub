---
title: Technical — Use cases de tenancy e acesso
description: Plano de execução da Stage 2.2 — lista ordenada de Tasks (1 Task = 1 commit) para a camada application do BC identity
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity-application, use-case, port-out, dto, fakes]
status: done
created_at: 2026-07-18
updated_at: 2026-07-18
stage_id: 2.2-identity-application
stage_title: Use cases de tenancy e acesso
step_id: 2
step_title: Restaurante e acesso
depends_on: [2.1-identity-domain]
concept_ref: ./concept.md
issue_id: 20
branch: feat/20-2-2-identity-application
tasks_count: 11
---

# Technical — Stage 2.2 — Use cases de tenancy e acesso

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(identity): <descrição em PT-BR> [2.2/task-NN]` + `Refs #20`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`, registrar em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done). Em modo autônomo
>    (ADR 0.0.0004) decisões reversíveis-baratas são registradas como
>    `[decision]` sem pergunta.
> 7. Ao fim da última Task, validar [§3 Gate de saída](#3-gate-de-saída-da-stage),
>    fazer commit `stage 2.2: complete` e atualizar `roadmap.md`.

## 1. Contexto e estratégia de execução

### Resumo

Camada `application` do BC `identity`: seis ports-out (`Protocol`), os DTOs de
fronteira, uma hierarquia de erros de aplicação ancorada em `IdentityError`, e os
cinco use cases (`create_restaurant`, `create_unit`, `create_user`,
`authenticate_user`, `authorize_action`). Nenhum I/O: tudo é exercitado por fakes
in-memory dos ports, incluindo um teste de fluxo ponta-a-ponta. O contrato de
import-linter da camada é instalado junto, para que a regra "application não
importa adapters" seja provada por gate e não por convenção.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`), com uma restrição a mais imposta
pelo gate deste repo: `make check` roda `test-gate`, que aplica
`fail_under = 90` **global**. Um commit que adicione arquivos de `src/` sem
nenhum teste que os importe derruba a média e **reprova o próprio commit**. Por
isso cada Task fecha um ciclo completo — código + teste que o exercita — e nenhum
port é commitado sem o fake e o teste que o cobrem.

Ordem e razão:

1. **Erros primeiro** (Task 01): todo o resto os levanta; são folha do grafo.
2. **DTOs** (Tasks 02–03), separados em "base" (identificadores, commands,
   results) e "sessão/token/credencial", porque os segundos carregam
   comportamento (`Session.is_active`) e merecem teste próprio.
3. **Ports + fakes juntos, por grupo** (Tasks 04–06). Emparelhar port e fake no
   mesmo commit é **deliberado** e está dentro da exceção que a
   `task-ordering-hex` admite: um fake **não é um adapter** (não há tecnologia
   externa), e sem ele o `Protocol` recém-criado ficaria sem cobertura,
   reprovando o gate. A regra dura que continua valendo — *não misturar port com
   o adapter real do port* — é respeitada: os adapters reais são 2.3 e 2.4.
4. **Use cases** (Tasks 07–10), um por Task, do mais simples ao mais composto,
   cada um com a sua matriz de casos de erro.
5. **Fluxo ponta-a-ponta + invariantes de segredo** (Task 11), que só faz sentido
   quando os cinco use cases existem.

### Pré-condições

- Stage `2.1-identity-domain` em `done` e mergeada em `develop` (commit
  `stage 2.1: complete`, verificado em `git log origin/develop`).
- `concept.md` desta Stage em `status: done`.
- `.venv` instalado na worktree (`make setup` / `uv sync --extra dev`).

### Premissas técnicas

- Python 3.12, mypy `strict`, ruff com `ANN` (type hints obrigatórios) e `PL`.
- **Protocol no estilo já vigente no repo: docstring + `...`**, como
  `shared/application/ports/out/clock.py`. Verificado por execução: `...` em corpo
  de função **não conta como statement** para o coverage (`clock.py` e
  `id_generator.py` medem 4 stmts / 0 miss / 100%), então não há linha não-coberta
  a evitar e não existe motivo para divergir do padrão existente. (mypy `strict`
  aceita tanto o corpo só-docstring quanto `...` em `Protocol`.)
- **`make typecheck` passa a cobrir `tests/fakes/` além de `src/`** (Task 04). Sem
  isso, a conformidade fake↔`Protocol` **não tem gate nenhum**: `pyproject.toml`
  fixa `files = ["src"]` e o Makefile roda `mypy src/`, de modo que uma anotação
  como `repo: UserRepository = InMemoryUserRepository()` dentro de um teste é
  descartada em runtime e nunca checada estaticamente. Como os fakes são a
  especificação que a 2.3 vai implementar, essa é a diferença entre mitigar e
  apenas afirmar que se mitiga (concept §10, linha "Fake e futuro adapter
  divergirem").
- Fakes vivem em `tests/fakes/` (LAYOUT §2 + skill `pytest-with-fakes`), nunca
  duplicados dentro de `tests/unit/`. `tests/fakes/shared/` **não existe** na
  árvore de LAYOUT §2 e é acrescentado lá na Task 05 (os ports `Clock`/
  `IdGenerator` são compartilhados, então os seus fakes não cabem sob
  `features/<feature>/`).
- Código em **inglês**; docstrings e comentários em PT-BR, como na 2.1.

### Exceções declaradas aos critérios de Task Atômica (PIPELINE §4.3)

- **Critério 4 (não misturar port com adapter): respeitado, não excepcionado.**
  Tasks 04–06 emparelham port + **fake**, e fake não é adapter — a skill
  `task-ordering-hex` prescreve literalmente "port out (`Protocol`) + use case +
  in-memory fake … same commit". Os adapters reais são 2.3/2.4.
- **Critério 2 (≤ 5 arquivos): excepcionado nas Tasks 01 (8 arquivos), 04 (9) e
  05 (9).** Razão: o gate de cobertura global obriga a commitar port e fake
  juntos; na Task 01 o excesso é quase todo `__init__.py` vazio de pacote; e as
  Tasks 04/05 carregam ainda um arquivo de configuração cada (`Makefile` e
  `docs/LAYOUT.md`) que existe justamente para dar gate ao que a Task cria. As
  demais Tasks ficam em ≤ 4.

### Estrutura de pastas afetada

```
src/restaurant_hub/features/identity/application/
├── errors.py
├── dtos/
│   ├── identifiers.py        # PasswordHash, SessionId
│   ├── commands.py
│   ├── results.py
│   ├── credentials.py        # UserCredentials
│   ├── tokens.py             # IssuedRefreshToken, AccessTokenClaims
│   └── session.py            # Session
├── ports/out/
│   ├── restaurant_repository.py
│   ├── unit_repository.py
│   ├── user_repository.py
│   ├── password_hasher.py
│   ├── token_issuer.py
│   └── session_repository.py
└── use_cases/
    ├── create_restaurant.py
    ├── create_unit.py
    ├── create_user.py
    ├── authenticate_user.py
    └── authorize_action.py

tests/
├── fakes/
│   ├── shared/
│   │   ├── fake_clock.py
│   │   └── fake_id_generator.py
│   └── features/identity/
│       ├── in_memory_restaurant_repository.py
│       ├── in_memory_unit_repository.py
│       ├── in_memory_user_repository.py
│       ├── in_memory_session_repository.py
│       ├── fake_password_hasher.py
│       └── fake_token_issuer.py
└── unit/features/identity/application/
    ├── test_errors.py
    ├── test_dtos.py
    ├── test_session_dto.py
    ├── test_repository_fakes.py
    ├── test_security_fakes.py
    ├── test_session_repository_fake.py
    ├── test_create_restaurant.py
    ├── test_create_unit.py
    ├── test_create_user.py
    ├── test_authenticate_user.py
    ├── test_authorize_action.py
    └── test_identity_flow.py

.importlinter                 # contrato novo: pureza da camada application
```

## 2. Tasks

### Task 01 — erros de aplicação + esqueleto de pacotes + contrato de import

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/errors.py`
  - `src/restaurant_hub/features/identity/application/{dtos,ports,ports/out,use_cases}/__init__.py` (vazios)
  - `tests/unit/features/identity/application/__init__.py` (vazio)
  - `tests/unit/features/identity/application/test_errors.py`
- **Arquivos a modificar:**
  - `.importlinter` (contrato novo `identity-application-purity`)
- **O que fazer:**
  Criar as dez exceções de aplicação do concept §6, todas subclasses de
  `IdentityError`; as três de "não encontrado" herdam também de `NotFoundError`,
  **nesta ordem** (`class RestaurantNotFoundError(IdentityError, NotFoundError)`).
  Adicionar ao `.importlinter` um contrato `forbidden` proibindo
  `features.identity.application` de importar `features.identity.adapters`,
  `shared.infrastructure`, `fastapi`, `starlette`, `uvicorn`, `sqlalchemy`,
  `alembic`, `pydantic`, `pydantic_settings`, `httpx` — espelhando o contrato de
  domínio que a 2.1 instalou.
- **Detalhes técnicos:**
  - Classes: `EmailAlreadyRegisteredError`, `InvalidCredentialsError`,
    `PermissionDeniedError`, `TenantScopeRequiredError`, `TenantNotVisibleError`,
    `UnitScopeRequiredError`, `UnitNotVisibleError`, `RestaurantNotFoundError`,
    `UnitNotFoundError`, `UserNotFoundError`.
  - Cada uma monta a mensagem no `__init__`, como as do domínio 2.1.
  - `InvalidCredentialsError` recebe **nenhum** parâmetro identificador e usa
    mensagem fixa que **não** distingue e-mail inexistente de senha errada
    (concept §5.14).
  - O contrato novo é **aditivo**: nenhum contrato existente pode ser afrouxado.
- **Critério de aceite:**
  - Concept **CA13**: teste percorre todas as classes do módulo e afirma
    `issubclass(cls, IdentityError)` e `issubclass(cls, DomainError)`; para as três
    de not-found, `issubclass(cls, NotFoundError)` e a MRO com `NotFoundError`
    antes de `DomainError`.
  - **Cada erro é instanciado e a mensagem assertada** — `issubclass` sozinho não
    executa `__init__` e deixaria `errors.py` em ~70% neste commit, abaixo do
    limiar por arquivo que a própria Stage se impõe em §3. É o mesmo padrão do
    `tests/unit/features/identity/domain/test_exceptions.py` da 2.1.
  - `InvalidCredentialsError` tem mensagem que **não** cita e-mail nem senha
    (assertado literalmente — concept §5.14).
  - `lint-imports` reporta o contrato novo como `KEPT` e nenhum contrato quebrado.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_errors.py -v
  uv run lint-imports
  make check
  ```
- **Commit sugerido:** `feat(identity): erros de aplicação e contrato de pureza da camada [2.2/task-01]`

---

### Task 02 — DTOs base: identificadores, commands e results

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/dtos/identifiers.py`
  - `src/restaurant_hub/features/identity/application/dtos/commands.py`
  - `src/restaurant_hub/features/identity/application/dtos/results.py`
  - `tests/unit/features/identity/application/test_dtos.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar `PasswordHash` e `SessionId` (`NewType` sobre `str`), os cinco commands e
  os cinco results do concept §4, todos `@dataclass(frozen=True)`.
- **Detalhes técnicos:**
  - Campos exatamente como a tabela do concept §4 — em especial
    `AuthorizeActionCommand(actor_id, permission, tenant_id=None, unit_id=None)` e
    `AuthorizedActor(user_id, role, actor_tenant_id, scope_tenant_id, scope_unit_id)`.
  - `CreateUserCommand.unit_ids: Sequence[UnitId] = ()`.
  - VOs de domínio (`Email`, `Role`, `Permission`) são usados diretamente nos
    campos — permitido por LAYOUT §7.
  - Nenhum result carrega senha, `PasswordHash` ou entidade.
- **Critério de aceite:**
  - Teste constrói cada command e result, afirma imutabilidade
    (`dataclasses.FrozenInstanceError` ao atribuir) e os defaults.
  - Concept **CA14**: teste afirma, via `dataclasses.fields`, que nenhum result
    tem campo de senha ou `PasswordHash`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_dtos.py -v
  uv run mypy src/
  make check
  ```
- **Commit sugerido:** `feat(identity): DTOs de comando e resultado da camada de aplicação [2.2/task-02]`

---

### Task 03 — DTOs de credencial, token e sessão

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/dtos/credentials.py`
  - `src/restaurant_hub/features/identity/application/dtos/tokens.py`
  - `src/restaurant_hub/features/identity/application/dtos/session.py`
  - `tests/unit/features/identity/application/test_session_dto.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar `UserCredentials`, `IssuedRefreshToken`, `AccessTokenClaims` e `Session`,
  todos `frozen`. `Session` expõe **apenas** o predicado puro `is_active(now)`.
- **Detalhes técnicos:**
  - `Session(id, user_id, refresh_token_fingerprint, issued_at, expires_at, revoked_at=None)`.
  - `is_active(now)` ⇒ `self.revoked_at is None and now < self.expires_at`
    (**half-open**: em `now == expires_at` já expirou — concept §5.10).
  - `Session` **não** tem método de revogação (concept §7.1): revogar é operação
    de port.
  - `AccessTokenClaims` inclui `session_id` (concept §4).
- **Critério de aceite:**
  - Teste cobre `is_active` nos quatro casos: ativa; expirada por
    `now > expires_at`; **fronteira exata `now == expires_at` ⇒ False**; revogada
    (`revoked_at` preenchido) mesmo dentro do prazo.
  - Teste afirma que `Session` não expõe método de revogação.
  - **O teste constrói também `UserCredentials`, `IssuedRefreshToken` e
    `AccessTokenClaims`** (uma asserção de campos cada). Sem isso, os dois módulos
    nascem a 0% e este commit fica a ~92% global — a margem mais apertada da Stage.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_session_dto.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): DTOs de credencial, token e sessão [2.2/task-03]`

---

### Task 04 — ports de repositório + fakes in-memory

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/ports/out/restaurant_repository.py`
  - `src/restaurant_hub/features/identity/application/ports/out/unit_repository.py`
  - `src/restaurant_hub/features/identity/application/ports/out/user_repository.py`
  - `tests/fakes/features/identity/{__init__.py,in_memory_restaurant_repository.py,in_memory_unit_repository.py,in_memory_user_repository.py}`
  - `tests/unit/features/identity/application/test_repository_fakes.py`
- **Arquivos a modificar:**
  - `Makefile` (alvo `typecheck` passa a incluir `tests/fakes/`)
- **O que fazer:**
  Criar os três `Protocol` do concept §4 e os fakes in-memory correspondentes,
  guardando estado em `dict`.
- **Detalhes técnicos:**
  - `UserRepository.add(user, password_hash, memberships=())` grava usuário,
    credencial e vínculos numa operação só.
  - `exists_by_email` é **global** — o fake não escopa por tenant.
  - `find_credentials_by_email` devolve `UserCredentials | None`.
  - `list_memberships(user_id) -> tuple[UnitMembership, ...]`.
  - O fake de `UserRepository` expõe um gancho de teste para **devolver vínculo de
    outro usuário** (concept §5.13 / CA12) — p.ex. `seed_membership(membership)`
    que não valida dono.
  - Os fakes de repositório contam chamadas de leitura, para os critérios que
    exigem "zero chamadas ao `UnitRepository`" (CA4).
  - **Conformidade fake↔`Protocol` precisa de gate estático, não de anotação.**
    Cada módulo de fake declara, em escopo de módulo, uma variável tipada pelo port
    (`_conforms: UserRepository = InMemoryUserRepository()` ou equivalente), e o
    alvo `typecheck` do Makefile passa a rodar
    `uv run mypy src/ tests/fakes/`. Sem essa mudança no Makefile a checagem é
    **decorativa**: `pyproject.toml` fixa `files = ["src"]`, a anotação some em
    runtime, e seis fakes podem divergir dos seis ports com `make check` verde.
- **Critério de aceite:**
  - Round-trip de cada fake: `add` seguido de `find_by_id` devolve o agregado.
  - `exists_by_email` verdadeiro para e-mail de **outro** tenant.
  - `find_by_id` devolve `None` para id inexistente.
  - `list_memberships` devolve o que foi gravado, na ordem de inserção.
  - **`make typecheck` falha se um fake divergir do `Protocol`** — validar
    empiricamente uma vez: remover um método do fake, confirmar que `mypy` acusa,
    restaurar.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_repository_fakes.py -v
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit sugerido:** `feat(identity): ports de repositório e fakes in-memory [2.2/task-04]`

---

### Task 05 — ports de segurança + fakes (inclui fakes compartilhados)

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/ports/out/password_hasher.py`
  - `src/restaurant_hub/features/identity/application/ports/out/token_issuer.py`
  - `tests/fakes/features/identity/{fake_password_hasher.py,fake_token_issuer.py}`
  - `tests/fakes/shared/{__init__.py,fake_clock.py,fake_id_generator.py}`
  - `tests/unit/features/identity/application/test_security_fakes.py`
- **Arquivos a modificar:**
  - `docs/LAYOUT.md` §2 — acrescentar `shared/` à árvore de `tests/fakes/`
    (hoje ela só prevê `features/<feature>/`, e os fakes de `Clock`/`IdGenerator`
    são de ports compartilhados). Registrar `[decision]` em §7.
- **O que fazer:**
  Criar `PasswordHasher` (com `dummy_hash`) e `TokenIssuer` (com a lei do
  fingerprint), os fakes correspondentes, e os fakes dos ports compartilhados
  `Clock` e `IdGenerator`.
- **Detalhes técnicos:**
  - `FakePasswordHasher`: `hash(p)` devolve `PasswordHash(f"hashed::{p}")`;
    `verify(p, h)` compara com o esperado e **nunca levanta** (hash malformado ⇒
    `False`); `dummy_hash()` devolve um hash constante contra o qual `verify`
    sempre falha. Conta chamadas de `verify` (necessário para CA7).
  - `FakeTokenIssuer`: `fingerprint(v)` é função determinística de `v` (p.ex.
    `f"fp::{v}"`), e `issue_refresh_token()` devolve
    `IssuedRefreshToken(value=v, fingerprint=self.fingerprint(v))` — a **lei do
    port** do concept §4 é honrada por construção. `issue_access_token(claims)`
    devolve string determinística derivada das claims.
  - `FakeClock(now)` com `now()` fixo e `advance(delta)` para testes de expiração.
  - `FakeIdGenerator` devolve UUIDs pré-determinados em sequência.
- **Critério de aceite:**
  - Teste afirma a lei do `TokenIssuer`: para `t = issuer.issue_refresh_token()`,
    `issuer.fingerprint(t.value) == t.fingerprint`.
  - Teste afirma que `verify` devolve `False` (sem levantar) para hash malformado,
    e que `verify(qualquer, dummy_hash())` é `False`.
  - Conformidade estrutural dos fakes com os `Protocol`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_security_fakes.py -v
  uv run mypy src/
  make check
  ```
- **Commit sugerido:** `feat(identity): ports de senha e token com fakes determinísticos [2.2/task-05]`

---

### Task 06 — port de sessão + fake com semântica normativa

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/ports/out/session_repository.py`
  - `tests/fakes/features/identity/in_memory_session_repository.py`
  - `tests/unit/features/identity/application/test_session_repository_fake.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar o `SessionRepository` do concept §4 e o fake que honra a **semântica
  normativa** — a parte mais fácil de implementar errado e a que a 2.3 vai copiar.
- **Detalhes técnicos:**
  - `find_by_fingerprint` **não filtra**: devolve sessão revogada **e** expirada.
  - `revoke(session_id, revoked_at)`: se já revogada, **no-op preservando o
    `revoked_at` original**; id inexistente não levanta.
  - `revoke_all_for_user(user_id, revoked_at)`: mesma regra, para todas as sessões
    do usuário.
  - Como `Session` é `frozen`, o fake atualiza por `dataclasses.replace`.
- **Critério de aceite:**
  - Concept **CA16** inteiro: `find_by_fingerprint` devolve revogada e expirada;
    revogar duas vezes preserva o primeiro `revoked_at`; `revoke` e
    `revoke_all_for_user` com id inexistente não levantam;
    `revoke_all_for_user` revoga **todas** as sessões do usuário e **nenhuma** de
    outro usuário.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_session_repository_fake.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): port de sessão revogável e fake in-memory [2.2/task-06]`

---

### Task 07 — use cases `create_restaurant` e `create_unit`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/create_restaurant.py`
  - `src/restaurant_hub/features/identity/application/use_cases/create_unit.py`
  - `tests/unit/features/identity/application/test_create_restaurant.py`
  - `tests/unit/features/identity/application/test_create_unit.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Dois use cases de criação, ambos gerando id pela conversão canônica
  `RestaurantId(str(id_generator.next_id()))` (concept §5.3).
- **Detalhes técnicos:**
  - `CreateRestaurantUseCase(restaurants, id_generator).execute(cmd) -> RestaurantResult`.
    Constrói `Restaurant(id=..., name=cmd.name)` — a validação de nome vazio é do
    domínio e **sobe sem reembrulho**.
  - `CreateUnitUseCase(units, restaurants, id_generator).execute(cmd) -> UnitResult`.
    Resolve o restaurante primeiro; ausente ⇒ `RestaurantNotFoundError`.
- **Critério de aceite:**
  - Concept **CA1**: id do result é exatamente `str(uuid)` do fake, e o
    restaurante está no repositório.
  - Concept **CA2**: unidade criada sob restaurante existente; restaurante
    inexistente ⇒ `RestaurantNotFoundError`, **sem** gravar nada no
    `UnitRepository`.
  - Nome vazio propaga `InvalidNameError` (do domínio) nos dois use cases.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_create_restaurant.py tests/unit/features/identity/application/test_create_unit.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): use cases de criação de restaurante e unidade [2.2/task-07]`

---

### Task 08 — use case `create_user`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/create_user.py`
  - `tests/unit/features/identity/application/test_create_user.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Use case de criação de usuário com hash de senha e vínculos de unidade,
  seguindo a **precedência fixa** do concept §5.7.
- **Detalhes técnicos:**
  Construtor: `CreateUserUseCase(users, restaurants, units, hasher, id_generator)`.
  O id sai da conversão canônica `UserId(str(id_generator.next_id()))`
  (concept §5.3), como nos use cases da Task 07.

  Ordem obrigatória de `execute`:
  1. `exists_by_email(cmd.email)` ⇒ `EmailAlreadyRegisteredError`;
  2. se `cmd.role is Role.PLATFORM_ADMIN` e `cmd.unit_ids` não vazio ⇒
     `PlatformAdminMembershipError` **antes de qualquer consulta ao
     `UnitRepository`** (não vazar existência de unidade);
  3. se `cmd.role is not Role.PLATFORM_ADMIN`:
     `restaurants.find_by_id(cmd.tenant_id)` ausente ⇒ `RestaurantNotFoundError`;
  4. construir `User(...)` — invariantes de tenancy da 2.1 sobem sem reembrulho;
  5. deduplicar `cmd.unit_ids` preservando ordem; para cada uma,
     `units.find_by_id` (ausente ⇒ `UnitNotFoundError`) e `user.link_to_unit(unit)`
     (que impõe `CrossTenantError`);
  6. `hasher.hash(cmd.plain_password)` e `users.add(user, password_hash, memberships)`.
  - `tenant_id` de `platform_admin` chega como `None`; o passo 3 é pulado.
- **Critério de aceite:**
  - Concept **CA3**: repositório recebe `PasswordHash`, nunca a senha; e-mail
    duplicado em **outro** tenant ⇒ `EmailAlreadyRegisteredError`, inclusive
    diferindo só por caixa (`Owner@X.com` após `owner@x.com`).
  - Concept **CA4**: `platform_admin` criado com `tenant_id is None`;
    `platform_admin` com `unit_ids` ⇒ `PlatformAdminMembershipError` **e o fake de
    `UnitRepository` registra zero chamadas**.
  - Concept **CA5**: um `UnitMembership` por unidade, `unit_ids` duplicados
    deduplicados; unidade de outro tenant ⇒ `CrossTenantError`.
  - Papel de restaurante sem restaurante existente ⇒ `RestaurantNotFoundError`.
  - **Unidade inexistente em `unit_ids` ⇒ `UnitNotFoundError`** — caminho
    normativo de §6 que nenhum outro critério exercita.
  - `user.id` é exatamente `str(uuid)` do `FakeIdGenerator`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_create_user.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): use case de criação de usuário com vínculos de unidade [2.2/task-08]`

---

### Task 09 — use case `authenticate_user`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/authenticate_user.py`
  - `tests/unit/features/identity/application/test_authenticate_user.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Autenticação por e-mail/senha que emite o par de tokens e **persiste a sessão**.
- **Detalhes técnicos:**
  - Construtor:
    `(users, sessions, hasher, token_issuer, id_generator, clock, access_token_ttl, refresh_token_ttl)`.
  - Fluxo: `find_credentials_by_email`; se `None`, executar
    `hasher.verify(cmd.plain_password, hasher.dummy_hash())` e levantar
    `InvalidCredentialsError` (concept §5.14 — o `verify` é obrigatório, não
    decorativo); se presente, `hasher.verify(plain, creds.password_hash)`; falso ⇒
    **a mesma** `InvalidCredentialsError`.
  - Sucesso: `now = clock.now()`;
    `session_id = SessionId(str(id_generator.next_id()))`;
    `issued = token_issuer.issue_refresh_token()`; montar `AccessTokenClaims` com
    `session_id` e `expires_at = now + access_token_ttl`;
    `access = token_issuer.issue_access_token(claims)`; montar
    `Session(id=session_id, user_id=..., refresh_token_fingerprint=issued.fingerprint,
    issued_at=now, expires_at=now + refresh_token_ttl)`; `sessions.add(session)`;
    devolver `AuthenticationResult` com `issued.value` como `refresh_token`,
    `access_token_expires_at = now + access_token_ttl` e
    **`refresh_token_expires_at = now + refresh_token_ttl`** (mesmo instante do
    `session.expires_at` — campo de contrato do concept §4 que precisa ser
    populado explicitamente, sob pena de a 2.4 consumir valor errado).
  - **Nenhuma sessão é persistida em caminho de falha.**
- **Critério de aceite:**
  - Concept **CA6**: sessão persistida está ativa em `clock.now()`;
    `session.refresh_token_fingerprint == issuer.fingerprint(result.refresh_token)`;
    `session.expires_at == now + refresh_token_ttl`;
    `result.access_token_expires_at == now + access_token_ttl`;
    `result.refresh_token_expires_at == session.expires_at`.
  - Concept **CA7**: e-mail inexistente e senha errada levantam a **mesma**
    `InvalidCredentialsError` (mesmo tipo **e** mesma mensagem); nenhum dos dois
    persiste sessão; no caminho de e-mail inexistente o contador de `verify` do
    fake é **1**.
  - Concept **CA15**: nenhuma `Session` recebida pelo fake contém `issued.value`
    em qualquer campo.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_authenticate_user.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): use case de autenticação com sessão persistida [2.2/task-09]`

---

### Task 10 — use case `authorize_action`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  - `tests/unit/features/identity/application/test_authorize_action.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  O guard de acesso, implementando **exatamente** a ordem normativa do concept
  §5.6. Esta é a Task de maior risco da Stage: a ordem das checagens é contrato.
- **Detalhes técnicos:**
  Ordem obrigatória de `execute` (`AuthorizeActionUseCase(users, units)`):
  1. `users.find_by_id(cmd.actor_id)` ausente ⇒ `UserNotFoundError`;
  2. `user.has_permission(cmd.permission)` falso ⇒ `PermissionDeniedError`;
  3. se `user.role is not Role.PLATFORM_ADMIN`: `cmd.tenant_id is None` ⇒
     `TenantScopeRequiredError`; `cmd.tenant_id != user.tenant_id` ⇒
     `TenantNotVisibleError`;
  4. `cmd.unit_id is None` e `not user.bypasses_unit_scope()` ⇒
     `UnitScopeRequiredError`;
  5. se `cmd.unit_id is not None`: `units.find_by_id` ausente ⇒
     `UnitNotFoundError`; se `cmd.tenant_id is not None` e
     `unit.tenant_id != cmd.tenant_id` ⇒ `TenantNotVisibleError`; então
     `user.can_view_unit(unit, users.list_memberships(user.id))` falso ⇒
     `UnitNotVisibleError`.
  - Sucesso ⇒
    `AuthorizedActor(user.id, user.role, user.tenant_id, cmd.tenant_id, cmd.unit_id)`.
  - **Não** reimplementar nada de `can_view_unit`; **não** filtrar o resultado de
    `list_memberships` (concept §5.13).
  - `list_memberships` só é chamado no passo 5.
- **Critério de aceite:**
  - Concept **CA8** (autorização feliz), **CA9** (RBAC × visibilidade +
    precedência), **CA10** (as quatro negativas de escopo, com o command completo
    de cada uma), **CA11** (`platform_admin`: bypass + `PermissionDeniedError` +
    coerência do par alvo), **CA12** (vínculo de outro usuário não concede
    visibilidade).
  - Teste de precedência dedicado: ator que falha em duas checagens recebe o erro
    da checagem mais alta.
  - **Ator inexistente ⇒ `UserNotFoundError`** e **unidade alvo inexistente ⇒
    `UnitNotFoundError`** — dois caminhos normativos de §6 que nenhum CA
    exercita por si só.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_authorize_action.py -v
  make check
  ```
- **Commit sugerido:** `feat(identity): use case de autorização em eixos ortogonais [2.2/task-10]`

---

### Task 11 — fluxo ponta-a-ponta com fakes

- **Arquivos a criar:**
  - `tests/unit/features/identity/application/test_identity_flow.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Teste que encadeia os **cinco use cases reais** sobre a mesma bateria de fakes,
  reproduzindo o caminho de negócio completo — a verificação end-to-end possível
  nesta Stage (não há runtime HTTP até a 2.4).
- **Detalhes técnicos:**
  - Sequência: `create_restaurant` → `create_unit` → `create_user` (um `owner` e um
    `manager` vinculado à unidade) → `authenticate_user` (com a senha usada na
    criação) → `authorize_action` (usando a permissão da tabela §4 do concept).
  - Os fakes são compartilhados entre os use cases, como o composition root fará
    na 2.4 — nenhum estado é injetado à mão entre etapas.
  - Incluir a variante negativa no mesmo fluxo: o `manager` autenticado tentando
    ação sobre a unidade à qual **não** está vinculado ⇒ `UnitNotVisibleError`.
- **Critério de aceite:**
  - Concept **CA18**: o fluxo passa sem nenhuma escrita direta nos fakes fora dos
    use cases.
  - A credencial criada em `create_user` autentica de fato em `authenticate_user`
    (prova que `hash`/`verify` casam através do port).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/ -v
  make check
  ```
- **Commit sugerido:** `test(identity): fluxo ponta-a-ponta de tenancy e acesso com fakes [2.2/task-11]`

---

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
make check
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
uv run python scripts/check_technical_postexec.py "docs/stages/2.2-identity-application/technical.md"
git diff --name-only $(git merge-base origin/develop HEAD) HEAD -- src/
```

### Verificações funcionais

- [ ] Fluxo ponta-a-ponta (Task 11) verde: restaurante → unidade → usuário →
      autenticação → autorização, com os cinco use cases reais sobre fakes.
- [ ] **Não há superfície de runtime nesta Stage** (a API é da 2.4): a verificação
      end-to-end é o teste de fluxo acima, e isso deve ser dito explicitamente no
      relatório em vez de simular um e2e HTTP que não existe.
- [ ] Cobertura ≥ 90% **em cada arquivo tocado** de `src/`, medida por
      `--cov-report=term-missing`.

### Checklist de fechamento da Stage

- [ ] Todas as 11 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Auditoria de testes por subagente independente, com **mutação real** nas
      funções críticas (`authorize_action`, `authenticate_user`, `create_user`)
- [ ] Commit final `stage 2.2: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `done`, `updated_at`/`last_reviewed_at` de
      hoje, linha no §Histórico, e a **nota de reconciliação** dos blocos
      2.2/2.3/2.4 (concept §7.8)
- [ ] ADRs 2.2.0001–2.2.0004 em `status: accepted`
- [ ] `concept.md` não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

```
Task 01 (erros)
   ├─► Task 02 (DTOs base) ─────┐
   └─► Task 03 (DTOs sessão) ───┼─► Task 04 (ports repo + fakes) ──┐
                                ├─► Task 05 (ports segurança)      │
                                └─► Task 06 (port sessão)          │
                                                                   ▼
                          Task 07 (create_restaurant / create_unit)
                          Task 08 (create_user)
                          Task 09 (authenticate_user)
                          Task 10 (authorize_action)
                                          │
                                          ▼
                                  Task 11 (fluxo e2e)
```

- Tasks 02 e 03 dependem de 01 apenas por coesão de pacote (os DTOs não levantam
  erros); podem ser lidas na ordem escrita sem retrabalho.
- **Task 04 depende de 03**: `UserRepository.find_credentials_by_email` devolve
  `UserCredentials | None`, criado em `dtos/credentials.py` na Task 03.
- Task 05 depende de 03 (`AccessTokenClaims`, `IssuedRefreshToken`).
- Task 06 depende de 03 (`Session`).
- Tasks 07–10 dependem de 02 + do grupo de ports/fakes que consomem:
  07 e 08 de 04–05; 09 de 04–06; 10 de 04.
- Task 11 depende de todas.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Cobertura global cai abaixo de 90% num commit intermediário (arquivo de `src/` sem teste que o importe) | A ordem das Tasks já emparelha código e teste; se ainda assim cair, fundir a Task com a seguinte que a cobre — registrar `[deviation]` em §7 |
| `mypy src/ tests/fakes/` acusar erro em código de teste pré-existente | O escopo novo é só `tests/fakes/`, criado nesta Stage; se algo fora dele quebrar, restringir o alvo a `tests/fakes/` e registrar `[deviation]` em §7 |
| `NewType` sobre `str` gerar atrito ao converter `UUID` | Conversão canônica única `str(uuid)` fixada no concept §5.3; centralizar num helper local se repetir demais |
| Ordem das checagens de `authorize_action` implementada errada | Ordem é contrato (concept §5.6), com teste de precedência dedicado + mutação real na auditoria |
| Fake divergir da semântica normativa do port de sessão | Task 06 testa a semântica explicitamente (CA16), e ela é a especificação que a 2.3 implementa |

## 6. Referências

- [`./concept.md`](./concept.md) — contratos, invariantes, critérios de aceite.
- ADRs desta Stage: [`../../adr/2_2_0001-revocable-refresh-session-port.md`](../../adr/2_2_0001-revocable-refresh-session-port.md),
  [`../../adr/2_2_0002-authorization-two-axes-fail-closed.md`](../../adr/2_2_0002-authorization-two-axes-fail-closed.md),
  [`../../adr/2_2_0003-application-errors-in-identity-hierarchy.md`](../../adr/2_2_0003-application-errors-in-identity-hierarchy.md),
  [`../../adr/2_2_0004-synchronous-port-signatures.md`](../../adr/2_2_0004-synchronous-port-signatures.md)
- ADRs consumidos: 2.1.0001, 2.1.0002, 0.0.0004.
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §5, §7; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §1, §4.
- Skills: `pytest-with-fakes`, `task-ordering-hex`, `hex-arch-python`,
  `import-linter-rules` (Task 01).

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. Apenas esta seção é editável após
> `status: done` (enquanto a Stage não mergeou). Modo autônomo (ADR 0.0.0004):
> decisões reversíveis-baratas são registradas aqui como `[decision]` sem pergunta.

### 2026-07-19 — [decision] Task 04 — `make typecheck` passa a cobrir `tests/fakes/` — Claude (autônomo)
**Contexto:** o Checkpoint B provou por execução que a conformidade fake↔`Protocol`
**não tinha gate nenhum**: `pyproject.toml` fixa `files = ["src"]` e o Makefile
rodava `mypy src/`, então uma anotação como `repo: UserRepository =
InMemoryUserRepository()` dentro de um teste some em runtime e nunca é checada.
Um fake com método faltando passava em todos os gates.
**Pergunta:** deixar a conformidade como convenção, ou estender o alvo `typecheck`?
**Opções:**
- A — manter `mypy src/`, confiando na revisão
- B — `mypy src/ tests/fakes/` + `_conforms: <Port> = <Fake>()` em cada fake ✅ recomendada
**Decisão:** B.
**Razão:** os fakes são a especificação que a 2.3 vai reimplementar (concept §10
mitiga o risco "fake e adapter divergirem" com "os fakes já são escritos contra o
`Protocol`" — afirmação que sem gate não se sustentava). Verificado por mutação:
renomear `find_by_id` num fake produz `missing following protocol member`.
`mypy src/ tests/fakes/` está limpo hoje (80 arquivos), então a mudança não
importa dívida pré-existente — `mypy src/ tests/` traria 8 erros e foi evitado.

### 2026-07-19 — [decision] Task 05 — `tests/fakes/shared/` acrescentado ao LAYOUT §2 — Claude (autônomo)
**Contexto:** LAYOUT §2 previa `tests/fakes/` contendo apenas `features/<feature>/`.
Os fakes de `Clock` e `IdGenerator` são de ports **compartilhados** e não cabem
sob nenhuma feature.
**Decisão:** acrescentar `shared/` à árvore do LAYOUT §2, no mesmo commit que criou
os arquivos.
**Razão:** CLAUDE.md nota 1 proíbe criar arquivo fora do LAYOUT sem justificativa;
a alternativa (duplicar os fakes dentro de cada feature) contraria a regra de
fonte única da skill `pytest-with-fakes`. Mudança puramente aditiva no doc.

### 2026-07-19 — [decision] Task 09 — `# noqa: PLR0913` no construtor do `AuthenticateUserUseCase` — Claude (autônomo)
**Contexto:** o construtor recebe 8 parâmetros (4 ports + `IdGenerator` + `Clock` +
2 TTLs) e o ruff reprova acima de 5.
**Opções:**
- A — agrupar dependências num objeto-parâmetro
- B — `noqa` local com justificativa ✅ recomendada
**Decisão:** B.
**Razão:** PLR0913 existe para pegar função que faz coisas demais; aqui o
construtor é a **costura de injeção de dependência**, montada uma vez pelo
composition root. Agrupar esconderia o grafo de dependências que o hexagonal quer
explícito, e os TTLs injetados são exigência do concept §7.6 (a camada
`application` não pode ler `Settings`). O Checkpoint C confirmou que o `noqa` é
load-bearing e não mascara defeito.

### 2026-07-19 — [decision] pós-auditoria — `branch = true` na cobertura — Claude (autônomo)
**Contexto:** a auditoria de testes apontou que a métrica era de **linha**, então
uma condição composta contava como coberta assim que a linha executasse uma vez.
`authorize_action` tem 20 branches, e é exatamente num guard de autorização que o
ramo não exercitado é o buraco.
**Decisão:** ativar `branch = true` em `[tool.coverage.run]`.
**Razão:** verificado antes de fixar — com branch coverage a camada `application`
permanece **100%** (76 branches), então o gate não foi afrouxado para caber; o
projeto ganha a métrica mais estrita de graça. Aplica-se a todo o repo, o que é
desejável.

### 2026-07-19 — [deviation] concept §4/§6 listam erros inalcançáveis a partir do use case — Claude (autônomo)
**Contexto:** o concept §4 lista `InvalidIdentifierError` entre os erros de
`CreateUnitUseCase`, e §6 lista `InvalidEmailError`/`InvalidRoleError`. A
auditoria observou que nenhum dos três é alcançável **de dentro** de um use case:
`Email` e `Role` são construídos pelo chamador ao montar o command, e o
identificador vem do `IdGenerator`. Eles continuam corretos como erros do **BC**
(a 2.4 vai encontrá-los ao converter a requisição), mas não como erros levantados
por estes use cases.
**Razão:** é imprecisão de tabela, não de contrato nem de comportamento — nenhum
critério de aceite muda. Registro aqui em vez de regredir o concept, por
proporcionalidade e seguindo o precedente da 2.1 (`[deviation]` sobre `ValueError`).
A divergência fica visível para a auditoria de contexto limpo decidir se merece
retoque.

### 2026-07-19 — [deviation] datas dos artefatos — Claude (autônomo)
**Contexto:** `concept.md`, `technical.md` e os quatro ADRs carregam
`created_at/updated_at: 2026-07-18` (data em que foram escritos); a execução
atravessou a virada do dia e a Stage fechou em **2026-07-19**, data usada no
`roadmap.md` e nestas entradas.
**Razão:** o `technical.md` §1–§6 fica congelado enquanto a Stage não mergeia
(`check_technical_postexec.py`), então a data não foi reescrita retroativamente —
o registro honesto fica aqui. Mesma situação que a 2.1 registrou.

### 2026-07-19 — [finding] use case de refresh/rotação de sessão não existe — Claude (autônomo)
**Contexto:** o `SessionRepository` nasce com `find_by_fingerprint`, `revoke` e
`revoke_all_for_user`, mas esta Stage não entrega o use case que os orquestra —
o recorte da Stage cobre cinco use cases, e refresh não é um deles. Os três
métodos estão cobertos por teste contra o fake (CA16), então a semântica está
especificada; falta o consumidor de produção.
**Direção sugerida:** criar `application/use_cases/refresh_session.py` junto do
endpoint `POST /auth/refresh`. Fluxo: `find_by_fingerprint` → `is_active(now)` →
`revoke` a antiga → `add` a nova. O bloco 2.4 do `roadmap.md` **não** lista esse
arquivo em `arquivos_a_criar` e precisa ser reconciliado.
**Stage candidata:** `2.4-identity-http`.

### 2026-07-19 — [finding] bootstrap de tenant não é autorizável pelo mapa RBAC atual — Claude (autônomo)
**Contexto:** o mapa da 2.1 dá ao `platform_admin` apenas `MANAGE_PLATFORM`, e
`MANAGE_USERS` só existe em papéis internos ao tenant. Logo, **ninguém consegue
criar o primeiro `owner`** de um restaurante recém-criado, e o DoD da 2.4
("admin cria tenant→unidade→usuário") fica inalcançável sem uma saída explícita.
**Direção sugerida:** a tabela permissão↔ação do concept §4 já propõe rotas de
bootstrap gated por `MANAGE_PLATFORM`, sem tocar no domínio. A alternativa —
conceder `MANAGE_TENANT`/`MANAGE_USERS` ao `platform_admin` — é mudança de
domínio e exigiria ADR próprio, além de contrariar o princípio "acesso de
plataforma não é acesso de restaurante" (concept 2.1 §5).
**Stage candidata:** `2.4-identity-http`.

### 2026-07-19 — [finding] `UnitMembershipRepository` dedicado quando houver consulta inversa — Claude (autônomo)
**Contexto:** `list_memberships(user_id)` vive no `UserRepository` (concept §7.4),
porque toda consulta desta Stage é "os vínculos deste usuário".
**Direção sugerida:** quando o Step 3 precisar de "quais usuários desta unidade",
o port dedicado passa a ser o desenho certo. Mover o método é refatoração
mecânica (um port, um fake, um adapter).
**Stage candidata:** `3.2-staff-application`.

### 2026-07-19 — [finding] `employee` não tem permissão alguma, logo nunca é autorizado — Claude (autônomo)
**Contexto:** `Role.EMPLOYEE → frozenset()` no mapa da 2.1, então todo command de
funcionário para no eixo RBAC. É consequência correta do modelo, não defeito —
mas significa que endpoints voltados ao funcionário responderão 403 sempre.
**Direção sugerida:** a Stage que introduzir auto-serviço de funcionário (ver a
própria escala, marcar preferência) precisará de uma permissão para isso.
**Stage candidata:** `3.5-employee-login-link` ou a Stage de auto-serviço do Step 4.

### 2026-07-19 — [finding] `hr` não tem ação tenant-wide — Claude (autônomo)
**Contexto:** `_UNIT_SCOPE_BYPASS_ROLES` = `{OWNER, PLATFORM_ADMIN}`, então `hr`
é escopado por unidade como o `manager` e, pelo passo 4 de §5.6, precisa nomear
uma unidade em toda ação. O comentário de `role.py` diz que "`manager` e `hr`
coincidem em identity e divergem no eixo de visibilidade" — divergência que hoje
não existe no código.
**Direção sugerida:** se `hr` ganhar atribuição tenant-wide (folha por
restaurante, por exemplo), ou ele entra em `_UNIT_SCOPE_BYPASS_ROLES` ou o
comentário deve ser corrigido.
**Stage candidata:** a primeira Stage que der atribuição própria ao `hr`.

### 2026-07-19 — [finding] cenário "tenant removido" não é modelável — Claude (autônomo)
**Contexto:** não existe exclusão de restaurante, unidade ou usuário em lugar
nenhum do sistema, então "usuário cujo restaurante sumiu" não tem como acontecer
hoje. `authenticate_user` não consulta o `RestaurantRepository`.
**Direção sugerida:** quando houver exclusão (ou desativação), decidir se o login
verifica a existência/estado do tenant e se as sessões do tenant são revogadas em
lote — o port já suporta via `revoke_all_for_user`.
**Stage candidata:** a Stage que introduzir desativação de tenant/usuário.

### 2026-07-19 — [finding] limpeza de sessões expiradas — Claude (autônomo)
**Contexto:** cada login grava uma linha de sessão; nada as remove. Em produção a
tabela cresce indefinidamente.
**Direção sugerida:** política de expurgo (job periódico ou índice com TTL) na
Stage que cria a tabela.
**Stage candidata:** `2.3-identity-persistence`.

<!-- END: post-execution -->

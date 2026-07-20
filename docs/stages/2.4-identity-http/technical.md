---
title: Technical — Stage 2.4 — API de tenancy, usuários e auth
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity-http, fastapi, jwt, argon2, rbac, refresh-rotation, e2e]
status: done
created_at: 2026-07-19
updated_at: 2026-07-19
stage_id: 2.4-identity-http
stage_title: API de tenancy, usuários e auth
step_id: 2
step_title: Identidade, acesso e multi-tenancy
depends_on: [2.3-identity-persistence]
concept_ref: ./concept.md
issue_id: 24
branch: feat/24-2-4-identity-http
tasks_count: 12
---

# Technical — Stage 2.4 — API de tenancy, usuários e auth

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite, comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.4/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`, registrar em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done).
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage).

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage liga o BC `identity` ao mundo. Constrói, de dentro para fora: os dois
adapters de segurança que faltavam (argon2, JWT), os dois use cases de ciclo de
vida de sessão (rotação com detecção de reuso, e logout), e então a camada HTTP
completa — schemas Pydantic, mapa exceção→status, guard de autenticação/autorização
e as 7 rotas — fechando com wiring no composition root e testes e2e contra Postgres
real pelo entrypoint FastAPI.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`): cada Task deixa o build verde e
nenhuma depende de código que ainda não existe. A ordem é ditada por três correntes
de dependência:

1. **Configuração antes de tudo** (Task 01): os adapters de segurança leem
   `Settings`; criá-los antes deixaria parâmetro hard-coded que a Task seguinte
   teria de arrancar.
2. **Port antes do adapter, adapter antes do consumidor** (02 → 03/04 → 05): o
   `TokenIssuer` ganha `decode_access_token` **antes** de haver implementação, e o
   fake é atualizado no mesmo commit — sem isso, `make typecheck` (que roda sobre
   `tests/fakes/`) quebra entre Tasks.
3. **Aplicação antes do adapter de entrada** (06 → 07…11): o router chama use
   cases; use cases não conhecem HTTP.

A camada HTTP é fatiada em quatro Tasks (07 schemas, 08 erros, 09 guard, 10/11
rotas) porque as três primeiras são independentes entre si e testáveis **sem** app
montada — o que mantém cada commit pequeno e o diagnóstico local quando algo
quebra. A Task 10 é a primeira que monta a app de verdade; por isso ela, e não a
11, carrega o wiring.

**A Task 12 (e2e) é o gate de saída da Stage**, não um extra: o DoD da issue #24
exige o fluxo exercitado pelo entrypoint real, e é a única Task que prova que o
wiring do composition root está correto.

### Pré-condições

- Stages `2.1`, `2.2` e `2.3` em `done` e **mergeadas** em `develop` (verificado:
  `stage 2.1|2.2|2.3: complete` presentes em `origin/develop`).
- Postgres da worktree no ar (`docker compose up -d postgres`, porta 5433) e
  `DATABASE_URL` do `.env` apontando para ela — os testes de integração e e2e
  **não se pulam** (ADR 2.3.0001).
- `git status --porcelain` limpo no início e no fim de cada Task.

### Premissas técnicas

- Python 3.12, `uv` como gerenciador; `make check` = lint + typecheck + layout +
  import-linter + lock-check + docs-check + test-gate.
- `mypy --strict` roda sobre `src/` **e** `tests/fakes/`.
- Cobertura com `branch = true` e `fail_under = 90`.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                          (M)
├── features/identity/
│   ├── application/
│   │   ├── errors.py                            (M) +3 erros
│   │   ├── dtos/commands.py                     (M) +2 commands
│   │   ├── ports/out/token_issuer.py            (M) +decode_access_token
│   │   └── use_cases/{refresh_session,revoke_session}.py   (N)
│   └── adapters/
│       ├── in/http/{schemas,error_handlers,dependencies,router}.py  (N)
│       └── out/security/{argon2_hasher,jwt_issuer}.py              (N)
└── shared/infrastructure/
    ├── config/settings.py                       (M) +4 campos
    └── http/app.py                              (M) registra router+handlers
tests/
├── unit/features/identity/adapters/test_{argon2_hasher,jwt_issuer,http_schemas,http_error_handlers,http_dependencies}.py  (N)
├── unit/features/identity/application/test_{refresh_session,revoke_session}.py  (N)
├── contract/features/identity/test_security_contract.py  (N)
├── e2e/features/identity/test_{auth_flow,tenancy_flow,authorization}.py  (N)
└── fakes/features/identity/fake_token_issuer.py  (M)
```

## 2. Tasks

### Task 01 — dependências de segurança e configuração de token

- **Arquivos a modificar:**
  - `pyproject.toml` (deps `argon2-cffi`, `pyjwt`)
  - `uv.lock` (via `uv lock`)
  - `.importlinter` (adicionar `argon2`, `jwt` às listas `forbidden_modules` dos
    quatro contratos de pureza)
  - `src/restaurant_hub/shared/infrastructure/config/settings.py`
  - `.env.example`
  - `tests/unit/shared/test_settings.py`
- **O que fazer:** declarar as duas dependências de runtime e os quatro campos de
  configuração de token. O `.importlinter` tem regra própria declarada no seu
  cabeçalho — "Dependência nova no pyproject => adicionar aqui no mesmo commit";
  cumpri-la aqui evita que domínio/aplicação passem a poder importar cripto sem
  que nenhum gate reclame.
- **Detalhes técnicos:**
  - `Settings`: `jwt_secret_key: str = "dev-insecure-change-me"`,
    `jwt_algorithm: str = "HS256"`, `access_token_ttl_minutes: int = 15`,
    `refresh_token_ttl_days: int = 14`. Docstrings citando concept §5 regra 12 e
    o `[finding]` do fail-fast (§10).
  - `.env.example` ganha as quatro chaves com comentário sobre o segredo de dev.
  - **Exceção declarada ao "≤ 5 arquivos" (PIPELINE §4.3):** são 6, porque
    `pyproject.toml` + `uv.lock` são um par mecânico (o lock é gerado, não
    editado, e `uv lock --check` reprova se forem separados) e `.env.example` é
    o espelho documental obrigatório de `settings.py`. Separar produziria commits
    que não passam no próprio gate.
- **Critério de aceite:** os quatro campos têm default e são sobrescrevíveis por
  variável de ambiente (teste); `uv lock --check` verde; os quatro contratos do
  import-linter listam `argon2` e `jwt`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/test_settings.py -v
  uv run lint-imports && uv lock --check && make check
  ```
- **Commit:** `feat(config): declarar dependências e configuração de token [2.4/task-01]`

---

### Task 02 — `decode_access_token` no port, erros de token e fake conforme

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/application/ports/out/token_issuer.py`
  - `src/restaurant_hub/features/identity/application/errors.py`
  - `src/restaurant_hub/features/identity/application/dtos/commands.py`
  - `tests/fakes/features/identity/fake_token_issuer.py`
  - `tests/unit/features/identity/application/test_security_fakes.py`
- **O que fazer:** estender o port com `decode_access_token(token: str) ->
  AccessTokenClaims` (ADR 2.4.0002); criar `InvalidAccessTokenError`,
  `InvalidRefreshTokenError` e `RefreshTokenReuseError` (herdando de
  `IdentityError`, ADR 2.2.0003); criar `RefreshSessionCommand` e
  `RevokeSessionCommand`. Atualizar o fake **no mesmo commit** — o `_conforms:
  TokenIssuer = FakeTokenIssuer()` do fake é checado por `mypy` e quebraria.
- **Detalhes técnicos:**
  - Contrato do port: verifica assinatura **e** expiração; qualquer falha levanta
    `InvalidAccessTokenError`; nunca devolve claims não verificadas. **Não existe**
    variante "decode sem verificar".
  - As três exceções têm mensagem **genérica**, sem eco do token nem da causa
    (concept §5 regra 10).
  - No fake, `decode_access_token` inverte `issue_access_token` simetricamente e
    levanta `InvalidAccessTokenError` para valor não emitido por ele.
- **Critério de aceite:** o fake satisfaz o Protocol estendido sob `mypy --strict`;
  round-trip `decode(issue(claims)) == claims` testado; token desconhecido levanta.
- **Comando de verificação:**
  ```bash
  uv run mypy src/ tests/fakes/
  uv run pytest tests/unit/features/identity/application/ -v
  ```
- **Commit:** `feat(identity): estender TokenIssuer com decodificação verificada [2.4/task-02]`

---

### Task 03 — adapter `Argon2PasswordHasher`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/security/__init__.py`
  - `src/restaurant_hub/features/identity/adapters/out/security/argon2_hasher.py`
  - `tests/unit/features/identity/adapters/test_argon2_hasher.py`
- **O que fazer:** implementar `PasswordHasher` com `argon2-cffi` (argon2id,
  parâmetros default da lib — ADR 2.4.0004).
- **Detalhes técnicos:**
  - **Lei 1:** `verify` captura `VerifyMismatchError`, `InvalidHashError` e
    `VerificationError` e devolve `False`. Vazar transformaria "senha errada" em
    500.
  - **Lei 2:** `dummy_hash()` devolve hash **válido** de uma sentinela fixa, com os
    mesmos parâmetros de custo, computado **uma vez por instância** (não por
    chamada — recomputar dobraria o custo do caminho de falha e recriaria o sinal
    de tempo pelo outro lado).
  - **Sem `_conforms` no módulo de produção.** O padrão `_conforms: <Port> =
    <Impl>()` existe **só em `tests/fakes/`** — nenhum adapter Postgres o usa, e
    por três razões que valem aqui: (a) instanciar adapter fora do
    `composition_root` contraria LAYOUT §6, que o próprio `composition_root.py`
    reafirma no docstring; (b) a Lei 2 manda computar `dummy_hash()` no
    `__init__`, então uma instância em nível de módulo faria **todo import** —
    inclusive a coleta do pytest — pagar um argon2id completo; (c) a conformidade
    com o `Protocol` é asserida pelos **testes**, como já se faz com os
    repositórios. A anotação de conformidade vai no teste da Task, não no
    adapter.
- **Critério de aceite:** `hash`/`verify` round-trip; `verify` devolve `False`
  (sem levantar) para hash vazio, malformado e de outro algoritmo (`$2b$...`);
  `dummy_hash()` é aceito pelo parser do argon2 e `verify` contra ele é sempre
  `False`; dois `hash()` da mesma senha diferem (salt por hash). **CA8.**
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_argon2_hasher.py -v --durations=5
  uv run mypy src/
  ```
- **Commit:** `feat(identity): implementar hasher argon2id [2.4/task-03]`

---

### Task 04 — adapter `JwtTokenIssuer`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/out/security/jwt_issuer.py`
  - `tests/unit/features/identity/adapters/test_jwt_issuer.py`
- **O que fazer:** implementar `TokenIssuer` com `PyJWT` (HS256) e
  `secrets`/`hashlib` para o refresh (ADR 2.4.0004).
- **Detalhes técnicos:**
  - `issue_access_token`: claims `sub`, `role`, `tenant_id`, `sid`, `exp`.
  - `decode_access_token`: `jwt.decode(..., algorithms=[self._algorithm])` —
    **allowlist explícita**, que é o que fecha confusão de algoritmo / `alg=none`
    (RFC 8725 §3.1). Captura `PyJWTError` (raiz) e `KeyError`/`ValueError` de claim
    ausente ou inválida, e levanta `InvalidAccessTokenError`.
  - `issue_refresh_token`: `secrets.token_urlsafe(32)`; fingerprint derivado
    chamando `self.fingerprint(value)` — **não** repetindo a fórmula (é a lei do
    port; duplicar é o defeito que ela existe para impedir).
  - `fingerprint`: `hashlib.sha256(value.encode()).hexdigest()`.
  - **Sem `_conforms` no módulo de produção** — mesma razão da Task 03, agravada
    aqui: `JwtTokenIssuer` recebe segredo e algoritmo de `Settings`, então uma
    instância em nível de módulo exigiria **hard-codar um segredo** no código de
    produção, que é exatamente o que a Task 01 existe para evitar. A conformidade
    com o `Protocol` é asserida no teste.
- **Critério de aceite:** round-trip de claims preservando `subject`, `role`,
  `tenant_id` (inclusive `None`) e `session_id`; token expirado levanta; assinatura
  adulterada levanta; token assinado com **outro** segredo levanta; token com
  `alg` trocado levanta; `fingerprint(t.value) == t.fingerprint`; dois refresh
  consecutivos diferem. **CA3, CA9.**
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_jwt_issuer.py -v
  uv run mypy src/
  ```
- **Commit:** `feat(identity): implementar emissor de token JWT [2.4/task-04]`

---

### Task 05 — testes de contrato dos ports de segurança (fake ≡ real)

- **Arquivos a criar:**
  - `tests/contract/features/identity/test_security_contract.py`
- **O que fazer:** rodar **o mesmo corpo de teste** contra o fake e contra o
  adapter real, parametrizado por fixture — o padrão que
  `tests/contract/features/identity/test_repository_contract.py` já estabeleceu
  para os repositórios.
- **Detalhes técnicos:** as leis testadas são as do port, não a implementação:
  - `PasswordHasher`: round-trip; `verify` nunca levanta (varredura de entradas
    degeneradas); `dummy_hash()` sempre falha em `verify`.
  - `TokenIssuer`: `fingerprint(t.value) == t.fingerprint`; round-trip de claims;
    token forjado/desconhecido levanta `InvalidAccessTokenError`.
- **Critério de aceite:** cada lei roda nas duas implementações; um fake que
  divergisse do real reprova. **CA8, CA9.**
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/identity/ -v
  ```
- **Commit:** `test(identity): contrato dos ports de segurança fake vs real [2.4/task-05]`

---

### Task 06 — use cases de sessão: rotação com detecção de reuso, e logout

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/use_cases/refresh_session.py`
  - `src/restaurant_hub/features/identity/application/use_cases/revoke_session.py`
  - `tests/unit/features/identity/application/test_refresh_session.py`
  - `tests/unit/features/identity/application/test_revoke_session.py`
- **O que fazer:** implementar a sequência normativa do concept §5 regra 5
  (rotação) e a regra 6 (logout idempotente).
- **Detalhes técnicos:**
  - **A ordem dos passos é contrato.** Em especial, o passo 3 (revogada → reuso →
    `revoke_all_for_user`) vem **antes** do passo 4 (expirada). Invertê-los faria
    um token revogado *e* expirado passar por simples expiração, deixando as
    demais sessões vivas — o caso do token roubado e guardado.
  - TTLs injetados (`timedelta`), nunca literais.
  - `revoke_session`: fingerprint → `find_by_fingerprint` → se `None`, **retorna
    sem erro**; senão `revoke(session.id, now)`. Nunca levanta.
  - Nenhum uso de `str(exc)` que ecoe o token.
- **Critério de aceite:** testes com fakes cobrindo — rotação feliz (sessão antiga
  revogada **e** nova gravada); refresh desconhecido → `InvalidRefreshTokenError`;
  refresh expirado → `InvalidRefreshTokenError`; refresh revogado →
  `revoke_all_for_user` chamado + `RefreshTokenReuseError`; **precedência**:
  revogado *e* expirado → reuso, não expiração; usuário sumido →
  `InvalidRefreshTokenError`; logout idempotente (desconhecido, já revogado,
  expirado → todos sem erro). **CA4, CA5, CA6, CA7, CA23.**
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_refresh_session.py tests/unit/features/identity/application/test_revoke_session.py -v
  uv run lint-imports
  ```
- **Commit:** `feat(identity): rotacionar e revogar sessão de refresh [2.4/task-06]`

---

### Task 07 — schemas Pydantic do boundary

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/in/__init__.py`
  - `src/restaurant_hub/features/identity/adapters/in/http/__init__.py`
  - `src/restaurant_hub/features/identity/adapters/in/http/schemas.py`
  - `tests/unit/features/identity/adapters/test_http_schemas.py`
- **O que fazer:** os schemas de request/response do concept §4. Pydantic vive
  **só aqui**.
- **Detalhes técnicos:**
  - Campos de credencial em request (`password`, `refresh_token`) são `SecretStr`.
  - Nenhum response carrega senha, hash ou fingerprint.
  - `CreateUserRequest` **não tem** campo `tenant_id` — a ausência é a defesa
    (concept §5 regra 3); se existisse, alguém acabaria por lê-lo.
  - Conversão texto→VO (`Email`, `Role.from_string`) **não** acontece no schema:
    fica no router, para que a falha seja erro de domínio (422 pelo mapa) e não
    `RequestValidationError` — mantendo o mapa de §6 como fonte única.
  - **Política de campo extra: manter o default do Pydantic v2 (`ignore`). NÃO
    usar `extra="forbid"`.** Endurecer o boundary parece a escolha segura e aqui
    quebraria CA13, que exige `201` quando o corpo tenta informar um `tenant_id`
    alheio — com `forbid` viraria 422, e a defesa deixaria de ser demonstrável.
    A defesa real é a **ausência do campo** no schema somada à derivação do
    tenant a partir do ator: o valor enviado é descartado, que é precisamente o
    que CA13 verifica.
- **Critério de aceite:** varredura de `model_fields` de todo schema `*Response`
  contra a lista negra (`password`, `senha`, `hash`, `password_hash`,
  `fingerprint`, `secret`) — de modo que schema novo entra na varredura sozinho;
  `repr` de request com senha não revela o valor. **CA17.**
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_http_schemas.py -v
  ```
- **Commit:** `feat(identity): schemas HTTP do bounded context identity [2.4/task-07]`

---

### Task 08 — mapa exceção → status HTTP

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/in/http/error_handlers.py`
  - `tests/unit/features/identity/adapters/test_http_error_handlers.py`
- **O que fazer:** o dicionário `tipo -> status` do concept §6, o handler único
  sobre `IdentityError` que o resolve por `__mro__`, e
  `register_identity_error_handlers(app)` (ADR 2.4.0001).
- **Detalhes técnicos:**
  - **401 e 403 devolvem `detail`/`type` constantes por faixa** — a mensagem da
    exceção **não** vai para o corpo (concept §5 regra 10). 404/409/422 mantêm
    `str(exc)`.
  - 401 acompanha `WWW-Authenticate: Bearer`.
  - Mora na feature, não em `shared` — `shared` não pode importar de features.
- **Critério de aceite:**
  - **Teste de totalidade:** enumera recursivamente as subclasses de
    `IdentityError` e exige entrada **própria** (não herdada) para cada uma;
    falha se alguma faltar. Assere também um piso de contagem (27) como tripwire
    contra `__subclasses__` encolhendo por módulo não importado. **CA16.**

    **A enumeração DEVE filtrar por `cls.__module__.startswith("restaurant_hub.")`.**
    Sem o filtro o teste se auto-reprova, e de forma determinística:
    `__subclasses__()` é registro global e vivo, e a subclasse-cobaia definida
    para o teste de MRO (item seguinte) passa a ser enumerada pela totalidade no
    mesmo processo pytest — sem entrada própria no mapa, porque é de teste. O
    piso 27 não protege (a contagem viraria 28 e passaria); quem reprova é a
    exigência de entrada própria. Quem executar sem o filtro vai encontrar a
    falha e provavelmente **afrouxar a totalidade** para fazer passar — matando
    justamente o gate de CA16.
  - Resolução por MRO testada com uma exceção só herdando (definida no módulo de
    teste, e por isso excluída pelo filtro acima).
  - Corpos de 401 e de 403 idênticos entre exceções diferentes da mesma faixa.
    **CA26.**
  - **Header:** resposta 401 traz `WWW-Authenticate: Bearer`; 403 **não** traz.
    Check objetivo aqui, e não só nos Detalhes — é onde a implementação está.
    **CA10 (parte de header), CA21 (idem).**
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_http_error_handlers.py -v
  ```
- **Commit:** `feat(identity): mapear erros do BC identity para status HTTP [2.4/task-08]`

---

### Task 09 — guard de autenticação e composição de autorização

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/in/http/dependencies.py`
  - `tests/unit/features/identity/adapters/test_http_dependencies.py`
- **O que fazer:** a dependência FastAPI que extrai o Bearer, decodifica via
  `TokenIssuer` e compõe as chamadas a `AuthorizeActionUseCase` (concept §5 regras
  2, 4, 4b; ADR 2.4.0003).
- **Detalhes técnicos:**
  - Header ausente, esquema não-Bearer, token malformado/expirado →
    `InvalidAccessTokenError` (401).
  - **Duas conversões que fecham vazamento de informação** (concept §6):
    `UserNotFoundError` (ator sumiu) → `InvalidAccessTokenError` (401);
    `UnitNotFoundError` (vinda do guard) → `UnitNotVisibleError` (403).
  - Helper de permissões exigidas: `{MANAGE_USERS} ∪ role_alvo.permissions`,
    derivado do mapa da 2.1 — **sem segunda tabela**.
  - Autoriza uma vez por permissão exigida × unidade requisitada; lista vazia →
    uma chamada com `unit_id=None`.
  - Nenhuma regra de acesso é avaliada aqui: só declaração de requisito e
    delegação.
- **Critério de aceite:** testes com fakes cobrindo os quatro caminhos de 401
  (**CA10**, **CA21**), a conversão de `UnitNotFoundError` (**CA22**), a derivação
  do conjunto de permissões para cada um dos 5 papéis alvo, e a chamada por
  unidade. Um teste assere que o guard **não** contém tabela de papéis própria
  (deriva de `Role.permissions`).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_http_dependencies.py -v
  uv run lint-imports
  ```
- **Commit:** `feat(identity): guard de autenticação e composição de autorização [2.4/task-09]`

---

### Task 10 — rotas de autenticação e wiring da aplicação

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/adapters/in/http/router.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
  - `src/restaurant_hub/shared/infrastructure/http/app.py`
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
  - `tests/e2e/test_app_smoke.py`
- **O que fazer:** as três rotas de `/auth` e o wiring completo. É a primeira Task
  em que a app sobe com a feature registrada.
- **Detalhes técnicos:**
  - `composition_root`: `ApplicationDependencies` passa a expor **use cases**, com
    os repositórios recuando para dentro deles (é o que o docstring do arquivo já
    antecipava). Instancia os dois adapters de segurança com `Settings`.
  - Carrega o módulo do router por `importlib` — `in` é keyword Python, então
    import estático é erro de sintaxe (LAYOUT §8) — e expõe **três** coisas, não
    duas: o `APIRouter`, o registrador de handlers, e o **mapa de
    `dependency_overrides`** (`dict[Callable, Callable]`, das funções provedoras
    `_get_*` definidas em `router.py` para os use cases montados).

    **O mapa é a peça que faz o resto fechar.** As chaves dos overrides são
    objetos-função que vivem dentro de `router.py`; se o composition root não os
    entregar, `app.py` precisa importar o módulo do router para alcançá-los — e
    aí `shared` passa a importar feature, quebrando a supressão estreita do
    `.importlinter` que a §7.6 do concept existe para preservar (o único par
    suprimido é `shared...http.app -> composition_root`). O template de `app.py`
    (linha ~68) descreve o padrão com `app.dependency_overrides[...]`; o que muda
    é **quem monta o dicionário**.
  - `app.py` só aplica o que recebe: `include_router`, `register_handlers`,
    `dependency_overrides.update(mapa)`. Continua sem conhecer a feature.
  - Rotas: `POST /auth/login` (200), `/auth/refresh` (200), `/auth/logout` (204),
    todas públicas — a autoridade do refresh é a posse do token.
- **Critério de aceite:** `create_app()` sobe com as rotas registradas em
  `/api/v1`; smoke e2e passa.

  **O teste mecânico de composition root é ESTENDIDO, não apenas mantido
  verde.** Hoje ele é cego para os adapters desta Stage:
  `test_composition_root_identity.py` fixa
  `_MODULO_DE_ADAPTERS = "restaurant_hub.features.identity.adapters.out.postgres"`,
  de modo que `adapters.out.security` (Tasks 03/04) e `adapters.in.http` não são
  varridos. Como está, a Stage cria dois adapters de produção novos e a única
  guarda mecânica contra instanciação fora do composition root não os enxerga —
  "continua passando" seria trivialmente verdade e completamente vazio. A Task
  amplia o prefixo para `restaurant_hub.features.identity.adapters` e assere que
  a varredura **de fato alcança** os módulos novos (teste negativo: um import
  proibido plantado reprova).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/e2e/test_app_smoke.py tests/unit/features/identity/adapters/test_composition_root_identity.py -v
  uv run lint-imports && uv run python scripts/check_layout.py
  ```
- **Commit:** `feat(identity): rotas de autenticação e wiring da aplicação [2.4/task-10]`

---

### Task 11 — rotas de tenancy

- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/adapters/in/http/router.py`
  - `tests/unit/features/identity/adapters/test_http_router.py` (criar)
- **O que fazer:** as quatro rotas de criação: `POST /restaurants`,
  `POST /restaurants/{id}/owners`, `POST /restaurants/{id}/units`, `POST /users`.
- **Detalhes técnicos:**
  - `/restaurants` e `/restaurants/{id}/owners` exigem `manage_platform`;
    `/units` exige `manage_tenant`; `/users` exige o conjunto composto da Task 09.
  - **Origem do tenant** (concept §5 regra 3): `/users` usa
    `AuthorizedActor.actor_tenant_id`; `/restaurants/{id}/owners` usa o `{id}` do
    **path** — o ator é `platform_admin` e o seu `actor_tenant_id` é
    necessariamente `None`.
  - `/restaurants/{id}/owners` fixa `role=Role.OWNER` **no código**, nunca do
    request — é o que garante que nenhuma rota emite `platform_admin`.
  - Conversão texto→VO (`Email`, `Role.from_string`) aqui, para que a falha vire
    422 pelo mapa.
- **Critério de aceite:** testes de router (use cases fake) cobrindo, **por
  cenário nomeado** — "caminhos autorizado e negado" é vago demais para servir de
  gate:
  - `/restaurants`: `platform_admin` → 201; `owner` → 403. **CA11.**
  - `/restaurants/{id}/units`: `owner` do tenant → 201; `owner` de **outro**
    tenant → 403; `manager` → 403; `platform_admin` → 403. **CA12.**
  - `/restaurants/{id}/owners`: `platform_admin` → 201 com o tenant do **path**;
    `{id}` inexistente → 404; `owner` → 403. **CA24.**
  - `/users`: `owner` → 201 com o tenant do **ator**, inclusive quando o corpo
    envia outro `tenant_id` (**CA13**); `manager` pedindo `role=owner` → 403
    (**CA14**); `manager` com unidade não visível → 403 e com unidade visível →
    201 (**CA15**); `role="platform_admin"` por qualquer ator → 403 (**CA20**).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/ -v
  uv run mypy src/
  ```
- **Commit:** `feat(identity): rotas de tenancy com enforcement de RBAC [2.4/task-11]`

---

### Task 12 — testes e2e pelo entrypoint real

- **Arquivos a criar:**
  - `tests/e2e/features/identity/__init__.py`
  - `tests/e2e/features/identity/conftest.py`
  - `tests/e2e/features/identity/test_auth_flow.py`
  - `tests/e2e/features/identity/test_tenancy_flow.py`
  - `tests/e2e/features/identity/test_authorization.py`
  - `tests/e2e/features/identity/test_status_bands.py`
- **O que fazer:** exercitar a app FastAPI real contra Postgres real. **Este é o
  gate de saída da Stage** — o DoD da issue #24 exige o fluxo pelo entrypoint, não
  por teste de use case.
- **Detalhes técnicos:**
  - `conftest`: app montada com `Settings` de teste; `platform_admin` semeado
    **direto pelo repositório** (nenhuma rota o cria — concept §5 regra 8);
    `TRUNCATE` entre testes reusando `truncar_tudo` de `tests/conftest.py`.
  - Adapters de segurança **reais** (argon2, JWT) — é o que prova o wiring.
  - `test_auth_flow`: login feliz; as duas falhas 401 com corpo idêntico;
    rotação; reuso do refresh rotacionado revogando as demais sessões; logout e o
    replay pós-logout.

    **Asserção de persistência (CA1, metade destrutiva):** após o login, o teste
    lê a linha de `sessions` no Postgres e assere que
    `refresh_token_fingerprint` **não contém** o valor do refresh devolvido no
    corpo, e que é igual a `issuer.fingerprint(valor)`. É a única asserção que
    impede uma regressão de persistir o token cru, e só um e2e com banco real
    consegue fazê-la.
  - `test_tenancy_flow`: a cadeia completa de CA18. **Mais o caminho destrutivo
    de CA24:** `POST /restaurants/{id-inexistente}/owners` devolve 404 **e**
    nenhuma linha nova aparece em `users` (contagem antes/depois).
  - `test_authorization`: os 403; a indistinguibilidade de CA22 (três cenários,
    corpo byte a byte); a constância de corpo de CA26; o 401 de ator removido
    (CA21); TTL configurável (CA25); **`POST /users` com `role="platform_admin"`
    por `owner` e por `platform_admin`, ambos 403 (CA20)**; `POST /users` cujo
    corpo tenta informar `tenant_id` de outro tenant → 201 com o tenant do ator
    (CA13); `POST /restaurants/{id}/units` por `owner` de **outro** tenant → 403
    (CA12).
  - `test_status_bands`: **teste parametrizado sobre as cinco faixas**
    (401/403/404/409/422), cada uma com um cenário real pela API, aserindo o
    status devolvido. O `parametrize` enumera as cinco faixas explicitamente, de
    modo que uma faixa sem cenário deixa o teste incompleto e falha. Cenário de
    409: criar dois usuários com o mesmo e-mail. Cenário de 422: `role` inválido.
    **CA16b** — sem este arquivo, CA16b não é entregue por Task alguma.
- **Critério de aceite:** **CA1, CA2, CA4, CA5, CA6, CA7, CA10, CA11, CA12,
  CA13, CA14, CA15, CA16b, CA18, CA20, CA21, CA22, CA23, CA24, CA25, CA26**
  verdes contra Postgres real.

  **Sobre CA2 — a metade que importa não é entregue aqui, e isso é declarado, não
  esquecido.** CA2 exige (a) corpo idêntico nas duas falhas e (b) que o login com
  e-mail inexistente verifique contra `dummy_hash()`. Esta Task entrega **só
  (a)**: ela roda com adapters reais, onde não existe fake espião para contar
  chamadas — a asserção (b) é estruturalmente impossível aqui. A metade (b) já
  está coberta, e permanece na suíte, por teste herdado da Stage 2.2:
  `tests/unit/features/identity/application/test_authenticate_user.py`, que
  assere `hasher.verify_args == [(senha, hasher.dummy_hash())]`. A Task
  **confirma que esse teste continua verde** e cita o caminho; marcar CA2 verde
  tendo checado só o corpo seria falso verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/e2e/ -v
  make check
  ```
- **Commit:** `test(identity): fluxo ponta a ponta pelo entrypoint FastAPI [2.4/task-12]`

## 3. Gate de saída da Stage

### Matriz de rastreabilidade (critério de aceite → Task)

> **A matriz é derivada dos "Critério de aceite" das Tasks, não o contrário.** Se
> um CA aparecer aqui e não no corpo da Task, ele é órfão e a matriz está
> mentindo — que é o modo exato pelo qual um gate de saída fica verde com buraco
> dentro.

| CA | Tasks | Onde o check objetivo está |
|---|---|---|
| CA1 | 12 (10 entrega o wiring de que 12 depende) | 12 — asserção de que `sessions` guarda fingerprint, não o valor |
| CA2 | 12 (+2.2) | 12 — corpo idêntico; a metade do espião vem de `test_authenticate_user.py` da 2.2, citada na Task 12 |
| CA3 | 04 | 04 — round-trip de claims, expirado, adulterado |
| CA4, CA5, CA6 | 06, 12 | 06 — precedência revogado-antes-de-expirado |
| CA7, CA23 | 06, 12 | 06 — logout idempotente; 12 — replay pós-logout |
| CA8 | 03, 05 | 03 — as duas leis; 05 — mesmas leis no fake |
| CA9 | 04, 05 | 04 — lei do fingerprint; 05 — idem no fake |
| CA10 | 08, 09, 12 | 09 — 4 caminhos de 401; 08 — o header |
| CA11, CA12 | 11, 12 | 11 — cenários nomeados por rota |
| CA13 | 07, 11, 12 | 11 — cenário nomeado; 07 fixa a política de `extra` de que CA13 depende |
| CA14, CA15 | 11, 12 | 11 — cenários nomeados por rota |
| CA16 | 08 | 08 — totalidade com filtro de módulo |
| CA16b | **12** | 12 — `test_status_bands.py`, parametrizado sobre as 5 faixas |
| CA17 | 07 | 07 — varredura de `model_fields` |
| CA18 | 12 | 12 — `test_tenancy_flow` |
| CA19 | gate de saída | `make check` + cobertura por arquivo |
| CA20 | 11, 12 | 11 e 12 — `role="platform_admin"` por cada ator |
| CA21 | 08, 09, 12 | 09 — conversão `UserNotFoundError`→401; 08 — o header |
| CA22 | 09, 12 | 09 — conversão `UnitNotFoundError`→403; 12 — 3 cenários byte a byte |
| CA24 | 11, 12 | 11 — 404 do path; 12 — nenhuma linha gravada |
| CA25 | 12 | 12 — TTL alterado reflete na resposta |
| CA26 | 08, 12 | 08 — corpos constantes por faixa |

### Verificações automatizadas
```bash
make check
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
uv run python scripts/check_technical_postexec.py "docs/stages/2.4-identity-http/technical.md"
```

### Verificações funcionais
- [ ] A cadeia de CA18 roda ponta a ponta pelo app FastAPI real contra Postgres.
- [ ] `uvicorn restaurant_hub.main:app` sobe e `/docs` lista as 7 rotas.
- [ ] Um login real emite um JWT que o guard aceita, e uma ação sem permissão
      devolve 403.

### Checklist de fechamento da Stage
- [ ] Todas as 12 Tasks commitadas, cada uma com check verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥ 90% em cada arquivo tocado
- [ ] Checkpoints A/B/C executados com achados dispostos
- [ ] §7 reflete a execução real
- [ ] `[finding]` com Stage candidata identificada
- [ ] ADRs 2.4.0001–2.4.0004 em `status: accepted`

## 4. Ordem de dependência entre Tasks

```
01 (config) ─► 03 (argon2) ─┐
            └► 04 (jwt) ────┼─► 05 (contrato)
02 (port+erros) ────────────┘        │
   │                                 │
   └► 06 (use cases sessão) ─────────┤
07 (schemas) ──┐                     │
08 (erros HTTP)├─► 10 (auth+wiring) ─► 11 (tenancy) ─► 12 (e2e)
09 (guard) ────┘
```

07, 08 e 09 são independentes entre si e poderiam ir em qualquer ordem; a listada
vai do mais simples ao mais acoplado. 09 depende de 02 (erros) e do
`AuthorizeActionUseCase` da 2.2.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `argon2-cffi` sem wheel para a plataforma (exige compilador) | Fixar `argon2-cffi-bindings` explicitamente; em último caso trocar para `bcrypt` — ROADMAP-4 admite, e o port isola a troca em um arquivo |
| Custo do argon2 torna e2e lento demais | Reduzir parâmetros **apenas nas Settings de teste**, nunca no adapter; registrar em §7 |
| `importlib` do router não resolve em runtime de teste | Alternativa em LAYOUT §5 Opção 3 (alias no `__init__.py` do pacote pai) |
| Totalidade via `__subclasses__` não enxerga classe de módulo não importado | Piso de contagem no teste (Task 08) + import explícito dos dois módulos de erro |

## 6. Referências

- [`./concept.md`](./concept.md)
- [`../../roadmap.md`](../../roadmap.md) — bloco `2.4-identity-http`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md), [`../../LAYOUT.md`](../../LAYOUT.md)
- ADRs desta Stage: `2_4_0001` … `2_4_0004`
- Skills aplicáveis: `fastapi-thin-adapter`, `composition-root`,
  `pytest-with-fakes`, `hex-arch-python`, `task-ordering-hex`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. Apenas esta seção é editável após
> `status: done`.

### 2026-07-19 — [deviation] Task 01/04 — segredo JWT default abaixo do mínimo da RFC 7518 — Claude (autônomo)
**Contexto:** o `jwt_secret_key` default nasceu como `dev-insecure-change-me`
(21 bytes). Ao escrever os testes do adapter JWT, o PyJWT emitiu
`InsecureKeyLengthWarning`: HS256 usa a chave como chave HMAC-SHA256, e a
RFC 7518 §3.2 exige ao menos o tamanho do digest (32 bytes).
**Desvio:** o default foi alongado para 39 caracteres, seguindo obviamente
inseguro — que é a propriedade desejada —, e o teste passou a fixar o piso de
tamanho. Os segredos de teste também subiram para ≥ 32 bytes.
**Razão para não ter perguntado:** ajuste in-scope revelado por um aviso da
própria biblioteca, sem mudança de contrato. Um default curto ensinaria o formato
errado a quem copiasse o `.env.example` e trocasse só as palavras.

### 2026-07-19 — [deviation] Task 03/04 — mypy do pre-commit é mais estrito que o do `make check` — Claude (autônomo)
**Contexto:** `make typecheck` roda `mypy src/ tests/fakes/` e passava, mas o
hook de pre-commit — que roda sobre o **conjunto estreito de arquivos alterados**
— reprovou `argon2_hasher.py` e `jwt_issuer.py` com `no-any-return`. Com poucos
arquivos no comando, o mypy não resolve os stubs de `argon2`/`jwt` e as funções
das libs voltam como `Any`.
**Desvio:** os dois adapters passaram a construir o retorno explicitamente
(`verify` monta o `bool`; `issue_access_token` usa local anotado) em vez de
repassar o valor da lib.
**Razão:** repassar faria o type-checker **acreditar** em vez de verificar. O
ajuste satisfaz os dois gates e é mais honesto que o código original.

### 2026-07-19 — [decision] Task 06 — `revoke` antes de `add` na rotação — Claude (autônomo)
**Contexto:** não há port de unidade de trabalho, então revogar a sessão antiga e
gravar a nova são transações separadas. A ordem entre elas é escolha.
**Opções:**
- A — `add` novo, depois `revoke` antigo: se o `revoke` falhar, dois refresh
  válidos coexistem.
- B — `revoke` antigo, depois `add` novo ✅ escolhida: se o `add` falhar, o
  cliente fica com um token morto e o retry dispara detecção de reuso.
**Decisão:** B.
**Razão:** num sistema com detecção de reuso, dois refresh válidos ao mesmo tempo
é o pior dos dois estados — é exatamente o cenário que a detecção existe para
tratar como incidente. B erra para o lado seguro. Declarado no concept §6.

### 2026-07-20 — [deviation] Task 11 — o guard virou dependência FastAPI, como o concept já mandava — Claude (autônomo)
**Contexto:** o Checkpoint C do segundo bloco mostrou que uma requisição **sem
credencial** com corpo malformado recebia 422 (validação do Pydantic) enquanto
com corpo válido recebia 401 — deixando um cliente sem credencial nenhuma sondar
o schema dos endpoints protegidos.
**Desvio:** a autenticação, que estava sendo chamada no **corpo** de cada rota,
passou a ser um `Depends`. O FastAPI resolve dependências antes de validar o
corpo, então os dois casos passaram a devolver 401 indistinguível.
**Razão:** não é só correção de vazamento — o concept §7.5 já declarava "guard
como `Depends`, não middleware", e a implementação original o contrariava sem
dizer. O desvio foi **em relação ao código**, não ao plano.

### 2026-07-20 — [deviation] Task 12 — a lista de aceite da Task 12 sobredeclara CA6 — Claude (autônomo)
**Contexto:** o Checkpoint C do terceiro bloco apontou que o "Critério de aceite"
da Task 12 lista **CA6** (precedência revogado-antes-de-expirado) entre os CAs
verdes "contra Postgres real". Nenhum teste e2e faz um refresh expirar: a app
real não tem relógio injetável, e forjar expiração exigiria manipular a linha do
banco — o que testaria o SQL, não a precedência.
**Desvio:** CA6 fica coberto **apenas** pela Task 06
(`test_precedencia_revogado_vence_expirado`, com `FakeClock`), que é onde a
matriz de rastreabilidade da §3 corretamente o aloca. A lista da Task 12 é que
estava inflada.
**Razão para registrar em vez de corrigir o texto:** §1–§6 do technical são
imutáveis após `status: done` (`check_technical_postexec.py`), e a matriz da §3
— que é a fonte usada no gate — já estava certa. Registrar aqui é o mecanismo
previsto para exatamente este caso.

### 2026-07-20 — [deviation] Task 12 — cenário de 422 nas faixas usa papel inválido, não e-mail malformado — Claude (autônomo)
**Contexto:** a Task 12 especifica "Cenário de 422: `role` inválido"; a primeira
implementação usou e-mail malformado em `POST /auth/login`.
**Desvio:** corrigido para papel inválido em rota **autenticada**, como
especificado.
**Razão:** com o cenário público, a faixa 422 era exercitada apenas por
`Email(...)`, e `Role.from_string` — a outra conversão texto→VO do router — não
tinha exercício e2e nenhum. O desvio deixava um caminho de conversão sem
cobertura de ponta a ponta.

### 2026-07-20 — [finding] Rota de desativação/demissão de usuário — Claude (autônomo)
**Stage candidata: `3.5-employee-login-link`** (a primeira que mexe no ciclo de
vida de uma pessoa), ou uma Stage dedicada de gestão de usuários.
**Contexto:** a decisão do sponsor descreve "demissão/logout cortam o refresh na
hora e o access em até 15 minutos". O logout foi entregue; a **demissão não tem
rota**. `SessionRepository.revoke_all_for_user` só tem chamador na detecção de
reuso, `User` não tem `is_active`, e os ports-out não têm update nem delete.
**Direção sugerida:** `is_active` em `User` + rota de desativação que chama
`revoke_all_for_user`. Enquanto não existir, a janela de corte por demissão não é
de 15 minutos — é indefinida. Declarado no concept §1 e §13.

### 2026-07-20 — [finding] Teto absoluto de vida de sessão e causa da revogação — Claude (autônomo)
**Stage candidata: uma Stage de endurecimento de sessão no Step 6**, junto do job
de `purge_expired`. Os dois itens mexem em `Session` e valem uma migration só.
**Contexto:** (a) a rotação renova `expires_at` a cada uso, sem teto — um cliente
que rotacione dentro do TTL mantém sessão indefinidamente (a RFC 6819 §5.2.2.3
trata rotação como complemento de um tempo de vida absoluto, não substituto);
(b) há um único `revoked_at` para logout, rotação e incidente, então reapresentar
um token que saiu por logout conta como reuso e derruba as demais sessões do
usuário — comportamento aceito, declarado e fixado por teste (CA23), mas que uma
coluna de causa resolveria.

### 2026-07-20 — [finding] Fail-fast de segredo default em produção — Claude (autônomo)
**Stage candidata: `6.2-deploy-pipeline`.**
**Contexto:** `jwt_secret_key` tem default de desenvolvimento e nada impede subir
em produção com ele. A checagem não foi feita aqui porque a suíte roda com
`debug=false` (default de `Settings`) e a checagem quebraria os testes em vez da
produção. Um gate de configuração de boot é o lugar certo.

### 2026-07-20 — [finding] Guard de escalada vive no boundary, e um segundo adapter de entrada não o herdaria — Claude (autônomo)
**Stage candidata: a primeira que introduza um segundo adapter de entrada**
(CLI, worker, console administrativo).
**Contexto:** "não se concede o que não se detém" é composto no adapter HTTP
(ADR 2.4.0003). Um futuro adapter que chame `CreateUserUseCase` direto **não**
herda a proteção. Aceito hoje porque HTTP é o único adapter de entrada; registrado
para não depender de memória quando isso mudar. Está nas Consequences do
ADR 2.4.0003 e repetido aqui para rastreabilidade.

### 2026-07-20 — [finding] Atomicidade da rotação e do provisionamento — Claude (autônomo)
**Stage candidata: `4.4-scheduling-persistence`** (a primeira com escrita
multi-agregado provável).
**Contexto:** não há port de unidade de trabalho. `revoke` + `add` da rotação são
transações separadas (concept §6), e o provisionamento restaurante+owner só não é
composto porque foi deliberadamente partido em duas rotas (ADR 2.4.0003,
Alternative B). Um port de UoW resolveria os dois.

### 2026-07-20 — [decision] Divergências declaradas em relação ao bloco do roadmap — Claude (autônomo)
**Contexto:** o bloco `2.4-identity-http` do `roadmap.md` traz
`contratos_introduzidos: []` e `camada_alvo: adapters/in/http`, e nenhum dos dois
se sustentou.
**Decisão:** declarar as divergências no concept §1 ("Vínculo com o roadmap") e
registrá-las aqui, deixando a **nota datada no `roadmap.md`** para o commit de
fechamento da Stage — que é o padrão que a 2.2 e a 2.3 estabeleceram.
**Razão:** a Stage introduziu a extensão aditiva `TokenIssuer.decode_access_token`,
dois commands, dois use cases, três erros de aplicação e dois adapters de
segurança; e criou arquivos em `application/use_cases/` e `adapters/out/security/`,
além da camada declarada. Silenciar seria repetir o defeito que as duas Stages
anteriores corrigiram com nota.

<!-- END: post-execution -->

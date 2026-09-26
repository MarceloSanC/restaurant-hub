---
title: Technical — Convite por e-mail e definição de senha
description: Plano de execução da Stage 2.5, com 13 Tasks ordenadas de dentro para fora (port → fake → use case → adapter → boundary → wiring)
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, email-invite, token, senha, reset, identity]
status: done
created_at: 2026-07-20
updated_at: 2026-07-20
stage_id: 2.5-email-invite
stage_title: Convite por e-mail e definição de senha
step_id: 2
step_title: Restaurante e acesso
depends_on: [2.4-identity-http]
concept_ref: ./concept.md
issue_id: 27
branch: feat/27-2-5-email-invite
tasks_count: 13
---

# Technical — Stage 2.5 — Convite por e-mail e definição de senha

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. **Não avançar sem verificação verde.** `make check` antes de todo commit.
> 4. Mensagem de commit: `<type>(<scope>): <descrição> [2.5/task-NN]` + `Refs #27`.
> 5. Ao fim, validar [§3](#3-gate-de-saída-da-stage), incluindo a matriz de
>    rastreabilidade.

## 1. Contexto e estratégia de execução

### Resumo

Fatia vertical do convite e da recuperação de acesso. Introduz um port
compartilhado de e-mail, um mecanismo próprio de token de uso único (ports +
tabela + adapters), três use cases, três rotas e o wiring. O detalhamento
conceitual — contratos, invariantes, casos de erro — está no
[`concept.md`](./concept.md) e **não é repetido aqui**; este documento diz em que
ordem construir e como verificar cada pedaço.

### A restrição que molda a ordem das Tasks

`make check` roda `mypy src/ tests/fakes/` (Makefile, alvo `typecheck`), e o
projeto mantém asserções explícitas de conformidade nos fakes
(`_conforms: UserRepository = InMemoryUserRepository()`), além de anotar os
construtores de use case com os tipos de port. **Consequência dura: acrescentar um
método a um `Protocol` já implementado deixa o build vermelho até que o adapter
real e o fake também o implementem.** Não há como separar "declarar o método" de
"implementá-lo" em dois commits verdes.

Por isso, as três extensões de port desta Stage —
`PasswordHasher.unusable_hash`, `UserRepository.set_password_hash` — viajam **na
mesma Task** que o adapter real e o fake correspondentes (T05, T06). Isso **não**
viola a regra de atomicidade "não misturar criação de port com criação do adapter
desse port" (PIPELINE §4.3): a regra mira a criação de um **port novo**, cujo
desenho deve ser fixado antes de existir implementação que o distorça. Um método
acrescentado a um port existente é uma mudança só, e fatiá-la produz um commit que
não compila.

Pelo mesmo motivo, `InvalidSetupTokenError` nasce na **mesma** Task que a sua
entrada no mapa de status HTTP: o teste de totalidade do mapa
(`test_o_mapa_e_total_sobre_identity_error`) falha para qualquer subclasse de
`IdentityError` sem entrada própria.

Os dois ports **novos** (`SetupTokenIssuer`, `PasswordSetupTokenRepository`)
seguem a regra normal — declarados em T04, implementados em T07 e T08.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`), em quatro ondas:

1. **Contratos compartilhados** (T01–T02): o port de e-mail e o seu primeiro
   adapter — a decisão arquitetural da Stage (ADR 2.5.0001).
2. **Vocabulário e contratos de identity** (T03–T06): DTOs, commands, erro +
   mapeamento, os dois ports novos com os seus fakes, e as duas extensões de port
   com as suas implementações.
3. **Persistência e emissão** (T07–T08): os adapters dos ports novos.
4. **Use cases e boundary** (T09–T13): a lógica, as rotas e o wiring.

### Sobre o número de Tasks

São **13**, uma acima da faixa saudável de 3–12 (CONVENTIONS §6) e abaixo do
limiar de alarme (≥ 14). A causa é declarada e não é escopo inflado: a restrição
de `mypy` acima obriga a fatiar por *unidade que compila*, não por *camada*, o
que transforma três mudanças de port em três Tasks completas em vez de uma. A
alternativa — juntar tudo — produziria commits de 8–10 arquivos, que é a
patologia que a faixa existe para evitar.

### Pré-condições

- Stage `2.4-identity-http` `done` e mergeada em `develop`.
- Postgres local no ar (`feat-27-2-5-email-invite-postgres-1`) — ADR 2.3.0001.
- `concept.md` em `status: done`.
- Ambiente: `$env:PATH += ";C:\msys64\usr\bin"`, `$env:UV_SYSTEM_CERTS = "1"`.

### Premissas técnicas

- Python 3.12: `secrets` e `hashlib` da stdlib bastam para o issuer — **nenhuma
  dependência nova** é adicionada nesta Stage.
- Alembic já configurado com `target_metadata = identity_metadata` (2.3); a
  `0001` usa `revision = "0001"`, `down_revision = None`.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                       (M)
├── shared/
│   ├── application/ports/out/email_sender.py                 (+)
│   └── infrastructure/
│       ├── email/console_sender.py                           (+)
│       ├── config/settings.py                                (M)
│       └── http/error_handlers.py                            (M)
└── features/identity/
    ├── application/
    │   ├── dtos/{setup_tokens,identifiers,commands}.py       (+/M)
    │   ├── errors.py                                         (M)
    │   ├── ports/out/{setup_token_issuer,
    │   │              password_setup_token_repository}.py    (+)
    │   ├── ports/out/{user_repository,password_hasher}.py    (M)
    │   └── use_cases/{invite_user,set_password_with_token,
    │                  request_password_reset}.py             (+)
    └── adapters/
        ├── out/security/{setup_token_issuer,argon2_hasher}.py (+/M)
        ├── out/postgres/{tables,mappers,user_repository,
        │                 password_setup_token_repository}.py  (+/M)
        └── in/http/{schemas,router,error_handlers}.py         (M)
migrations/versions/0002_password_setup_tokens.py             (+)
.env.example                                                  (M)
tests/{unit,contract,integration,e2e,fakes}/...               (+/M)
```

## 2. Tasks

### Task 01 — port compartilhado `EmailSender`

- **Arquivos a criar:**
  - `src/restaurant_hub/shared/application/ports/out/email_sender.py`
  - `tests/fakes/shared/recording_email_sender.py`
  - `tests/unit/shared/test_email_sender_port.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** declarar `EmailMessage` (frozen: `to`, `subject`, `body_text`) e
  o `Protocol` `EmailSender` com `send(message) -> None` (concept §4). Criar o fake
  `RecordingEmailSender`, que acumula as mensagens em `sent` e aceita ser
  configurado para levantar (necessário para os testes da regra 8).
- **Detalhes técnicos:** o docstring explica por que o port vive em `shared`
  (ADR 2.5.0001) e por que `to` é `str` — `shared/application` não importa de
  `features/`, e é essa restrição que mantém o port genérico. O fake declara
  `_conforms: EmailSender = RecordingEmailSender()`, como os demais fakes do projeto.
- **Critério de aceite:** **CA1** — teste assere
  `{f.name for f in dataclasses.fields(EmailMessage)} == {"to","subject","body_text"}`;
  o fake registra na ordem e levanta quando configurado.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/test_email_sender_port.py -v
  uv run python scripts/check_layout.py && uv run lint-imports
  ```
- **Commit sugerido:** `feat(shared): port compartilhado de envio de e-mail [2.5/task-01]`

---

### Task 02 — adapter `ConsoleSender`

- **Arquivos a criar:**
  - `src/restaurant_hub/shared/infrastructure/email/__init__.py`
  - `src/restaurant_hub/shared/infrastructure/email/console_sender.py`
  - `tests/unit/shared/test_console_sender.py`
  - `tests/contract/shared/test_email_sender_contract.py` (+ `__init__.py` se faltar)
- **Arquivos a modificar:** nenhum
- **O que fazer:** `ConsoleSender` recebe um `TextIO` **injetado** (default
  `sys.stdout`) e escreve destinatário, assunto e corpo em texto puro.
- **Detalhes técnicos:** a saída é injetada, e não capturada por `capsys`, para que
  o teste não dependa de estado global do processo — mas o caminho do default
  também é exercitado, senão a linha fica descoberta (CA18). O teste de contrato
  fica em `tests/contract/shared/` e não na raiz de `tests/contract/`: LAYOUT §2
  só sanciona `features/<feature>/`, e `tests/unit/` e `tests/fakes/` já têm o
  irmão `shared/`. O docstring registra que este adapter **imprime o corpo**,
  portanto imprime o token — desejado em desenvolvimento e inaceitável em produção.
- **Critério de aceite:** **CA2** — a saída injetada contém os três campos; o teste
  de contrato roda a mesma bateria contra `RecordingEmailSender` e `ConsoleSender`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/test_console_sender.py tests/contract/shared -v
  ```
- **Commit sugerido:** `feat(shared): adapter de e-mail para console [2.5/task-02]`

---

### Task 03 — vocabulário do token: DTOs, commands, erro e mapeamento HTTP

- **Arquivos a criar:**
  - `src/restaurant_hub/features/identity/application/dtos/setup_tokens.py`
  - `tests/unit/features/identity/application/test_setup_token_dtos.py`
- **Arquivos a modificar:**
  - `.../application/dtos/identifiers.py` (+`SetupTokenId`)
  - `.../application/dtos/commands.py` (+3 commands)
  - `.../application/errors.py` (+`InvalidSetupTokenError`)
  - `.../adapters/in/http/error_handlers.py` (+entrada 401)
  - `tests/unit/features/identity/adapters/test_http_error_handlers.py`
- **O que fazer:** `SetupTokenPurpose`, `IssuedSetupToken` (`value` com
  `repr=False`), `PasswordSetupToken` com `is_usable(now)`; os commands
  `InviteUserCommand`, `SetPasswordWithTokenCommand` (**sem** `user_id`) e
  `RequestPasswordResetCommand`; o erro com mensagem **constante**; e a entrada
  `InvalidSetupTokenError: HTTP_UNAUTHORIZED` no mapa.
- **Detalhes técnicos:** 7 arquivos, acima do usual, e a razão é mecânica: o teste
  `test_o_mapa_e_total_sobre_identity_error` falha para qualquer subclasse sem
  entrada própria, então criar o erro sem mapeá-lo deixa a suíte vermelha. Os dois
  são uma mudança só. `is_usable` é half-open (`now < expires_at`).
  `SetPasswordWithTokenCommand` tem `token` e `plain_password`, ambos `repr=False`,
  e o docstring diz que a ausência de `user_id` é a defesa (regra 10).
- **Critério de aceite:** **CA4** (`is_usable` falso em `now == expires_at` e com
  `consumed_at` preenchido); **CA11b parte 1** (nenhum campo de
  `SetPasswordWithTokenCommand` identifica usuário); **CA14 parte "mensagem
  constante"** (duas construções produzem a mesma string, sem valor/fingerprint);
  o teste de totalidade do mapa volta a passar e o novo erro cai no corpo
  constante da faixa 401.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity -v
  uv run mypy src/ tests/fakes/
  ```
- **Commit sugerido:** `feat(identity): DTOs, comandos e erro do token de definicao de senha [2.5/task-03]`

---

### Task 04 — os dois ports novos e os seus fakes

- **Arquivos a criar:**
  - `.../application/ports/out/setup_token_issuer.py`
  - `.../application/ports/out/password_setup_token_repository.py`
  - `tests/fakes/features/identity/fake_setup_token_issuer.py`
  - `tests/fakes/features/identity/in_memory_password_setup_token_repository.py`
  - `tests/unit/features/identity/application/test_setup_token_fakes.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** declarar os dois `Protocol` (concept §4) e os seus fakes.
- **Detalhes técnicos:** port e **fake** na mesma Task, port e **adapter real** em
  Tasks distintas (T07, T08) — é o fake que torna o port verificável, e o projeto
  já pareia os dois (skill `pytest-with-fakes`). Os docstrings carregam a semântica
  normativa, como os da 2.2/2.3: `find_by_fingerprint` **não filtra**; `consume`
  devolve `bool` e o booleano **é** o contrato de uso único (o fake também precisa
  ser condicional, senão diverge do Postgres); `invalidate_all_for_user` escopa por
  `purpose` quando ele é dado e **não** escopa quando é `None`.
- **Critério de aceite:** **CA5 (lado fake)** — `consume` devolve `True` e depois
  `False`; `invalidate_all_for_user` com e sem `purpose` afeta os conjuntos
  corretos; `find_by_fingerprint` devolve token consumido e expirado sem filtrar.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_setup_token_fakes.py -v
  uv run mypy src/ tests/fakes/
  ```
- **Commit sugerido:** `feat(identity): ports e fakes do token de definicao de senha [2.5/task-04]`

---

### Task 05 — `unusable_hash`: port, adapter argon2 e fake

- **Arquivos a modificar:**
  - `.../application/ports/out/password_hasher.py` (+`unusable_hash`)
  - `.../adapters/out/security/argon2_hasher.py`
  - `tests/fakes/features/identity/fake_password_hasher.py`
  - `tests/contract/features/identity/test_security_contract.py`
- **Arquivos a criar:** nenhum
- **O que fazer:** acrescentar o método ao port com as duas leis, e implementá-lo
  no adapter (`self._backend.hash(secrets.token_urlsafe(32))`, material descartado)
  e no fake (aleatório por chamada, rejeitado pelo `verify` do fake).
- **Detalhes técnicos:** os três arquivos viajam juntos por obrigação de `mypy`
  (§1). O docstring do port declara as leis e **por que este método não é
  `dummy_hash()`** — ADR 2.5.0004. O `unusable_hash` é **aleatório por chamada**,
  ao contrário do dummy, que é computado uma vez no construtor de propósito.
- **Critério de aceite:** **CA6b** — no fake **e** no adapter argon2:
  `verify(p, unusable_hash())` é `False` para uma lista de senhas que inclui
  **explicitamente** `_SENTINELA_DUMMY`; duas chamadas devolvem valores diferentes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/identity/test_security_contract.py -v
  uv run mypy src/ tests/fakes/
  ```
- **Commit sugerido:** `feat(identity): hash inutilizavel para conta ainda nao ativada [2.5/task-05]`

---

### Task 06 — `set_password_hash`: port, adapter Postgres e fake

- **Arquivos a modificar:**
  - `.../application/ports/out/user_repository.py` (+`set_password_hash`)
  - `.../adapters/out/postgres/user_repository.py`
  - `tests/fakes/features/identity/in_memory_user_repository.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_user_repository.py`
- **Arquivos a criar:** nenhum
- **O que fazer:** o método no port (levanta `UserNotFoundError`; é `UPDATE`, não
  upsert), no adapter (`UPDATE users SET password_hash = ... WHERE id = ...`,
  `rowcount == 0` → `UserNotFoundError`) e no fake.
- **Detalhes técnicos:** os três viajam juntos pela mesma razão de §1. Não cria
  linha, não altera e-mail, papel nem tenant.
- **Critério de aceite:** integração — grava e relê o hash novo; usuário
  inexistente levanta `UserNotFoundError` e **nada** é gravado; o fake tem o mesmo
  comportamento nos dois cenários.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/identity -v
  uv run mypy src/ tests/fakes/
  ```
- **Commit sugerido:** `feat(identity): troca de hash de senha no repositorio de usuarios [2.5/task-06]`

---

### Task 07 — adapter `Sha256SetupTokenIssuer`

- **Arquivos a criar:**
  - `.../adapters/out/security/setup_token_issuer.py`
  - `tests/unit/features/identity/adapters/test_setup_token_issuer.py`
- **Arquivos a modificar:**
  - `tests/contract/features/identity/test_security_contract.py`
- **O que fazer:** valor com `secrets.token_urlsafe(32)`, fingerprint com
  `hashlib.sha256(value.encode()).hexdigest()`.
- **Detalhes técnicos:** SHA-256 puro é adequado — a entrada tem ~256 bits de
  entropia, então não há espaço de busca a proteger (mesma escolha do fingerprint
  de refresh da 2.4). O docstring registra isso, para que ninguém "conserte"
  trocando por um KDF caro numa rota pública.
- **Critério de aceite:** **CA3** — a lei `fingerprint(t.value) == t.fingerprint`
  vale no teste de contrato para o fake **e** para o adapter; dois `issue()`
  devolvem valores distintos; o fingerprint é determinístico para o mesmo valor.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters/test_setup_token_issuer.py tests/contract/features/identity -v
  ```
- **Commit sugerido:** `feat(identity): emissor de token de definicao de senha [2.5/task-07]`

---

### Task 08 — persistência: tabela, migration e repositório de tokens

- **Arquivos a criar:**
  - `migrations/versions/0002_password_setup_tokens.py`
  - `.../adapters/out/postgres/password_setup_token_repository.py`
  - `tests/integration/features/identity/adapters/out/postgres/test_password_setup_token_repository.py`
- **Arquivos a modificar:**
  - `.../adapters/out/postgres/tables.py`
  - `.../adapters/out/postgres/mappers.py`
- **O que fazer:** a tabela conforme concept §9 (todas as constraints
  **nomeadas**), a migration `0002` com `revision = "0002"` e
  `down_revision = "0001"`, o mapper linha↔DTO e o repositório.
- **Detalhes técnicos:** `consume` é
  `UPDATE ... SET consumed_at = :now WHERE id = :id AND consumed_at IS NULL`, com
  retorno `rowcount == 1` — **nunca** `SELECT` seguido de `UPDATE`, que passaria
  nos testes sequenciais e perderia a corrida em produção.
  `invalidate_all_for_user` acrescenta `AND purpose = :purpose` quando `purpose`
  não é `None`, e `AND consumed_at IS NULL` sempre (não reescreve instante de
  consumo já gravado). `purge_expired` usa `expires_at <= before`, inclusive, como
  o de sessões.
- **Critério de aceite:** **CA5 (lado Postgres)**, **CA9b**, **CA16**. Round-trip
  preservando microssegundos e fuso; `consume` `True` depois `False`; **teste de
  concorrência** com duas conexões/transações simultâneas em que exatamente uma
  devolve `True`; `invalidate_all_for_user` com e sem `purpose`; unicidade do
  fingerprint levanta; paridade do schema com `identity_metadata` após
  `alembic upgrade head`.
- **Comando de verificação:**
  ```bash
  uv run alembic upgrade head
  uv run pytest tests/integration/features/identity -v
  ```
- **Commit sugerido:** `feat(identity): persistencia dos tokens de definicao de senha [2.5/task-08]`

---

### Task 09 — `InviteUserUseCase`

- **Arquivos a criar:**
  - `.../application/use_cases/invite_user.py`
  - `tests/unit/features/identity/application/test_invite_user.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** checa a unicidade do e-mail, cria o `User` com
  `hasher.unusable_hash()`, persiste, emite o token (`purpose=INVITATION`),
  persiste-o, compõe a mensagem com o link e envia. Devolve `UserResult`.
- **Detalhes técnicos:** recebe `users`, `restaurants`, `units`, `hasher`,
  `tokens`, `token_issuer`, `email_sender`, `id_generator`, `clock`,
  `invitation_ttl: timedelta` e `base_url: str`. A resolução de unidades e a
  invariante de tenancy reaproveitam a mecânica de `CreateUserUseCase` — **não
  reimplementar** o isolamento de tenant; `User.link_to_unit` já o impõe. A falha
  do `EmailSender` **propaga** (regra 13). Não chama `invalidate_all_for_user`: um
  usuário recém-criado não tem token anterior, e o segundo convite ao mesmo e-mail
  nunca chega aqui (409).
- **Critério de aceite:** **CA6** — usuário criado com hash inutilizável; o
  repositório de tokens guardou **apenas** o fingerprint (asserção sobre os campos
  persistidos); exatamente **uma** mensagem enviada, cujo `body_text` contém o
  valor do token e cujo `to` é o e-mail do convidado; `EmailAlreadyRegisteredError`
  quando o e-mail já existe, **sem** emitir token nem enviar mensagem; falha do
  sender propaga.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_invite_user.py -v
  ```
- **Commit sugerido:** `feat(identity): use case de convite de usuario [2.5/task-09]`

---

### Task 10 — `SetPasswordWithTokenUseCase`

- **Arquivos a criar:**
  - `.../application/use_cases/set_password_with_token.py`
  - `tests/unit/features/identity/application/test_set_password_with_token.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** implementar exatamente a ordem da regra 5:
  `fingerprint` → `find_by_fingerprint` → `is_usable` → `consume` →
  `revoke_all_for_user` → `invalidate_all_for_user` (**sem** `purpose`) →
  `set_password_hash`. Toda falha de token vira `InvalidSetupTokenError`.
- **Detalhes técnicos:** `UserNotFoundError` de `set_password_hash` é
  **convertido** em `InvalidSetupTokenError` (regra 16). Não devolve nada — regra 14.
- **Critério de aceite:** **CA8** — o hash gravado pertence ao `user_id` **do
  token**, `revoke_all_for_user` foi chamado para esse usuário, e um convite ainda
  vigente do mesmo usuário fica invalidado (asserção sobre o repositório de
  tokens, cobrindo a invalidação **sem escopo de propósito**).
  **CA8b** — com `set_password_hash` configurado para levantar, o token já está
  consumido **e** as sessões já foram revogadas.
  **CA9** — o mesmo token duas vezes falha na segunda, **e** o hash gravado
  continua sendo o da primeira redenção (a segunda não escreve).
  **CA10** e **CA11b parte 2** — token expirado, desconhecido e de usuário
  inexistente levantam a **mesma** exceção, com a **mesma** mensagem.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_set_password_with_token.py -v
  ```
- **Commit sugerido:** `feat(identity): use case de definicao de senha por token [2.5/task-10]`

---

### Task 11 — `RequestPasswordResetUseCase`

- **Arquivos a criar:**
  - `.../application/use_cases/request_password_reset.py`
  - `tests/unit/features/identity/application/test_request_password_reset.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** busca as credenciais pelo e-mail; se não existir, **retorna sem
  fazer nada**. Se existir, invalida os resets anteriores (escopado por
  `PASSWORD_RESET`), emite e persiste o token novo e envia a mensagem —
  **absorvendo** qualquer exceção do `EmailSender` (regra 8).
- **Detalhes técnicos:** o use case **não** levanta em nenhum dos dois caminhos e
  **não** devolve nada que distinga os casos. A absorção da falha do sender é
  deliberada, e o docstring explica por quê: sem ela, 500 significaria
  "cadastrado" e 202 significaria "não cadastrado".
- **Critério de aceite:** **CA12 (nível de aplicação)** — o retorno é idêntico
  (`None`) nos três cenários e o caminho "não cadastrado" **não toca** no
  repositório de tokens nem no sender.
  **CA12b** — com um sender que sempre levanta, o retorno não muda.
  **CA13** — dois pedidos de reset para o mesmo usuário deixam vivo apenas o
  segundo token; um pedido de reset **não** invalida um convite pendente do mesmo
  usuário (asserção direta sobre o repositório).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/application/test_request_password_reset.py -v
  ```
- **Commit sugerido:** `feat(identity): use case de pedido de redefinicao de senha [2.5/task-11]`

---

### Task 12 — boundary HTTP: schemas, rotas e corpo constante de validação

- **Arquivos a criar:**
  - `tests/unit/features/identity/adapters/test_setup_token_http.py`
- **Arquivos a modificar:**
  - `.../adapters/in/http/schemas.py`
  - `.../adapters/in/http/router.py`
  - `src/restaurant_hub/shared/infrastructure/http/error_handlers.py`
  - `tests/unit/features/identity/adapters/test_http_schemas.py`
- **O que fazer:** três rotas —
  `POST /users/invitations` (autenticada, 201, devolve `UserResponse`),
  `POST /auth/password-reset-requests` (pública, **202**, corpo constante),
  `POST /auth/password` (pública, **204**). Registrar o handler de
  `RequestValidationError` com corpo constante.
- **Detalhes técnicos:** os campos de credencial dos requests são `SecretStr`.
  A rota de convite reusa `required_permissions_for_role` + `guard.authorize_all`
  **exatamente** como `POST /users` — não inventar autorização nova. Nenhum schema
  de resposta ganha campo de token. O handler de validação vai em
  `shared/infrastructure/http` porque vale para a app inteira; `app.py` já chama
  `register_error_handlers`. Se algum teste da 2.4 asserir o corpo default do 422,
  ajustá-lo e registrar `[deviation]`.
- **Critério de aceite:** **CA7** — um `manager` recebe **403** ao convidar um
  `owner`; o convite de um `manager` para unidade que ele não enxerga recebe 403;
  o `tenant_id` do usuário criado é o do **ator**, e o schema de request não tem o
  campo. **CA10 (HTTP)** — token desconhecido, expirado e de usuário inexistente
  produzem respostas idênticas em status, corpo **e cabeçalhos**.
  **CA14** — a varredura enumerativa existente de `*Response` é estendida e
  continua verde. **CA14b** — corpo malformado na rota de definição de senha
  devolve 422 cujo corpo **não contém** a string do token.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/identity/adapters tests/e2e -v
  ```
- **Commit sugerido:** `feat(identity): rotas de convite, reset e definicao de senha [2.5/task-12]`

---

### Task 13 — configuração, wiring e verificação end-to-end

- **Arquivos a criar:**
  - `tests/e2e/features/identity/test_invitation_flow.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
  - `src/restaurant_hub/shared/infrastructure/config/settings.py`
  - `.env.example`
  - `tests/unit/shared/test_settings.py`
  - `tests/unit/features/identity/adapters/test_composition_root_identity.py`
- **O que fazer:** acrescentar a `Settings` `app_base_url`, `email_from`,
  `invitation_token_ttl_hours` e `password_reset_token_ttl_minutes`; instanciar
  `ConsoleSender`, `Sha256SetupTokenIssuer` e o repositório de tokens; montar os
  três use cases e registrar os `dependency_overrides` novos.
- **Detalhes técnicos:** os TTLs viram `timedelta` no composition root, como os de
  token de sessão. No e2e o `EmailSender` é substituído por `RecordingEmailSender`
  via `dependency_overrides` — **nada sai da máquina** (ADR 0.0.0004 §7).
- **Critério de aceite:** **CA15** — e2e do fluxo inteiro: `platform_admin` cria
  restaurante e owner → owner convida → mensagem capturada → token extraído do
  corpo → `POST /auth/password` (204) → login com a senha nova devolve par de
  tokens. **CA11** — o login falhava antes da definição. **CA6c** — login com
  `"dummy-password-that-never-authenticates"` antes da ativação devolve 401.
  **CA12** — as respostas do reset são idênticas em status, corpo e cabeçalhos nos
  três cenários (cadastrado ativo, cadastrado não ativado, não cadastrado).
  **CA17** — o teste mecânico do composition root é estendido e continua verde;
  os defaults de `Settings` permitem iniciar sem `.env`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/e2e -v
  make check
  ```
- **Commit sugerido:** `feat(identity): wiring do fluxo de convite e verificacao e2e [2.5/task-13]`

## 3. Gate de saída da Stage

### Matriz de rastreabilidade (critério de aceite → Task)

Critério órfão é o modo exato pelo qual um gate de saída fica verde com buraco
dentro. A matriz é conferida antes do commit de fechamento.

| CA | Task(s) |
|---|---|
| CA1 | T01 |
| CA2 | T02 |
| CA3 | T07 |
| CA4 | T03 |
| CA5 | T04 (fake) + T08 (Postgres) |
| CA6 | T09 |
| CA6b | T05 |
| CA6c | T13 |
| CA7 | T12 |
| CA8 | T10 |
| CA8b | T10 |
| CA9 | T10 |
| CA9b | T08 |
| CA10 | T10 (aplicação) + T12 (HTTP) |
| CA11 | T13 |
| CA11b | T03 (forma do command) + T10 (comportamento) |
| CA12 | T11 (aplicação) + T13 (HTTP, três cenários) |
| CA12b | T11 |
| CA13 | T11 |
| CA14 | T03 (mensagem constante) + T12 (varredura de schemas) |
| CA14b | T12 |
| CA15 | T13 |
| CA16 | T08 |
| CA17 | T13 |
| CA18 | **gate de saída** (abaixo) — não pertence a Task nenhuma |

### Verificações automatizadas
```bash
make check
uv run pytest tests/
# CA18 — cobertura por arquivo tocado, não só a média global
git diff --name-only $(git merge-base origin/develop HEAD) HEAD -- src/
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/2.5-email-invite/technical.md
```

### Verificações funcionais
- [ ] Fluxo completo exercitado pela app HTTP real (CA15).
- [ ] Login com a sentinela do adapter falha para convidado não ativado (CA6c).
- [ ] Reset responde igual nos três cenários (CA12).
- [ ] Replay do token falha, inclusive concorrente contra Postgres (CA9, CA9b).

### Checklist de fechamento da Stage
- [ ] Todas as 13 Tasks commitadas com check verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥ 90% em **cada** arquivo tocado de `src/` (CA18)
- [ ] Matriz de rastreabilidade acima sem órfãos
- [ ] Checkpoints A/B/C com todos os achados dispostos
- [ ] Auditoria de testes com todos os itens "sim"
- [ ] §7 preenchida com o que realmente aconteceu
- [ ] ADRs `2_5_0001`–`2_5_0004` em `status: accepted`
- [ ] `roadmap.md` atualizado (Stage `done` + nota das divergências do concept §1)

## 4. Ordem de dependência entre Tasks

```
T01 ─► T02
 │
 └──────────────┐
T03 ─► T04 ─────┼─► T09 ─┐
 │      │       │        │
 │      ├─► T07 ┘        ├─► T12 ─► T13
 │      └─► T08 ─────────┤
 ├─► T05 ────────────────┤
 └─► T06 ────────────► T10, T11 ─┘
```

- T03 é a base de vocabulário: tudo depois dele o consome.
- T04 declara os ports novos e os fakes; T07/T08 são os adapters reais.
- T05 (`unusable_hash`) é pré-requisito de T09; T06 (`set_password_hash`) é
  pré-requisito de T10.
- T09–T11 (use cases) precisam dos fakes de T04 e das extensões de T05/T06.
- T12 precisa dos use cases; T13 precisa de tudo.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Teste de concorrência do `consume` intermitente no Windows | Duas conexões explícitas com transação manual e barreira de thread; se ainda oscilar, emitir os dois `UPDATE` condicionais na mesma janela e assertar a soma dos `rowcount` — nunca relaxando o critério |
| Migration `0002` conflita com o estado do banco local | `alembic downgrade base && alembic upgrade head` na base de teste |
| Handler de `RequestValidationError` quebra testes da 2.4 que asseram o corpo do 422 | Ajustar os testes: o corpo constante é a decisão (D6); registrar `[deviation]` |
| Cobertura do `ConsoleSender` abaixo de 90% por causa do default `sys.stdout` | Exercitar também o caminho do default |
| `InviteUserUseCase` duplica a mecânica de `CreateUserUseCase` | Aceitável nesta Stage; se a duplicação passar de trivial, extrair um método compartilhado e registrar `[deviation]` |
| Uma extensão de port derruba `mypy` por implementação faltante em outro ponto | É o modo de falha previsto em §1 — a correção é trazer o arquivo faltante para a **mesma** Task, nunca criar um commit vermelho |

## 6. Referências

- [`./concept.md`](./concept.md) — contratos, invariantes, casos de erro, CAs
- [`../../adr/2_5_0001-email-sender-in-shared.md`](../../adr/2_5_0001-email-sender-in-shared.md)
- [`../../adr/2_5_0002-dedicated-single-use-setup-token.md`](../../adr/2_5_0002-dedicated-single-use-setup-token.md)
- [`../../adr/2_5_0003-password-change-revokes-sessions.md`](../../adr/2_5_0003-password-change-revokes-sessions.md)
- [`../../adr/2_5_0004-unusable-hash-for-pending-accounts.md`](../../adr/2_5_0004-unusable-hash-for-pending-accounts.md)
- Skills aplicáveis: `task-ordering-hex`, `fastapi-thin-adapter`,
  `composition-root`, `pytest-with-fakes`, `repository-pattern`, `hex-arch-python`

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`** — alterações fora dos marcadores são rejeitadas por
> `scripts/check_technical_postexec.py`.

### 2026-07-20 — [decision] Fase 3B — 13 Tasks em vez de 12 — Claude (autônomo)
**Contexto:** o plano fechou com 13 Tasks, uma acima da faixa saudável de 3–12
(CONVENTIONS §6) e abaixo do limiar de alarme (≥ 14).
**Pergunta:** juntar Tasks para caber na faixa, ou declarar o excedente?
**Opções:**
- A — juntar, produzindo commits de 8–10 arquivos
- B — declarar as 13 e explicar a causa ✅ recomendada
**Decisão:** B
**Razão:** `make check` roda `mypy src/ tests/fakes/` e o projeto mantém asserções
de conformidade nos fakes, de modo que acrescentar um método a um `Protocol` já
implementado deixa o build vermelho até o adapter real **e** o fake implementarem.
Isso obriga a fatiar por *unidade que compila*, não por camada, e transforma três
mudanças de port em três Tasks completas. Juntar produziria exatamente a
patologia (commit gigante) que a faixa existe para evitar.

### 2026-07-20 — [decision] Task 03 — erro e mapeamento HTTP na mesma Task — Claude (autônomo)
**Contexto:** `InvalidSetupTokenError` nasceu na Task 03; o mapeamento para 401
estava planejado para a Task 12.
**Razão:** `test_o_mapa_e_total_sobre_identity_error` falha para qualquer subclasse
de `IdentityError` sem entrada própria no mapa. Criar o erro sem mapeá-lo deixaria
a suíte vermelha da Task 03 até a 12 — nove commits. São uma mudança só, e viajaram
juntas (7 arquivos, acima do usual, declarado na Task).

### 2026-07-20 — [decision] Task 05 — `unusable_hash()` em vez de `dummy_hash()` — Claude (autônomo)
**Contexto:** o concept original mandava gravar `hasher.dummy_hash()` como
credencial da conta convidada. O **Checkpoint A** (dois revisores independentes,
achado *blocker* em ambos) mostrou que `dummy_hash()` é o hash de
`_SENTINELA_DUMMY = "dummy-password-that-never-authenticates"`, um literal do
repositório: `verify(sentinela, dummy_hash())` devolve `True`.
**Decisão:** introduzir `PasswordHasher.unusable_hash()`, aleatório por chamada,
derivado de `secrets` dentro do adapter. Registrado no **ADR 2.5.0004**.
**Razão:** persistido, o dummy seria uma senha válida para **toda** conta
convidada ainda não ativada, publicada no código-fonte — tomada de conta completa
antes de a vítima abrir o e-mail. O concept foi corrigido antes do commit
`conceptual approved`; nenhuma linha chegou a ser escrita com o defeito.

### 2026-07-20 — [decision] Task 11 — a absorção envolve o caminho inteiro — Claude (autônomo)
**Contexto:** a primeira implementação de `request_password_reset` protegia com
`try/except` **apenas** a chamada ao `EmailSender`. O **Checkpoint C do segundo
bloco** apontou que a emissão e a gravação do token ficavam de fora.
**Decisão:** o `try/except Exception` envolve emissão **e** envio.
**Razão:** a regra 8 do concept é sobre o **efeito colateral assimétrico**, não
sobre a classe `EmailSender`. Gravar o token também só acontece para e-mail
cadastrado, então bastava o banco recusar escrita — réplica somente-leitura, disco
cheio, deadlock, timeout — para o cadastrado dar 500 e o desconhecido dar 202:
enumeração completa de contas pelo status, sem medir tempo. Coberto por
`TestFalhaDeEscritaTambemEAbsorvida`.

### 2026-07-20 — [decision] Task 13-fix — `EmailSender` vira costura do composition root — Claude (autônomo)
**Contexto:** o e2e trocava o sender montando um **segundo** grafo de dependências
e sobrescrevendo `_email_sender`, atributo privado do use case.
**Decisão:** `wire_dependencies(..., email_sender=None)` e
`create_app(..., email_sender=None)`.
**Razão:** escolher a implementação de um port é literalmente o trabalho do
composition root, então o parâmetro é uma costura legítima e não um atalho de
teste. A versão anterior funcionava por acidente (dependia de os dois grafos terem
exatamente as mesmas chaves de override) e deixava um `Engine` pendurado por teste.

### 2026-07-20 — [deviation] Task 13-fix — `email_from` removido de `Settings` — Claude (autônomo)
Foi acrescentado na Task 13 e removido no mesmo bloco: `ConsoleSender` não tem
remetente e `EmailMessage` não tem campo para ele (a CA1 fixa os três campos do DTO
justamente para o port não crescer por antecipação). Um campo de configuração sem
leitor é pior que ausência — quem o define no `.env` recebe silêncio. Entra na 6.2
junto com o adapter que vai lê-lo.

### 2026-07-20 — [deviation] Tasks 03/08 — guardas enumerativas existentes atualizadas — Claude (autônomo)
Quatro testes-guarda de Stages anteriores precisaram ser estendidos, e nenhum
estava na lista de arquivos das Tasks: `test_dtos.py` (varredura de `frozen` —
`setup_tokens` **não estava** na tupla de módulos, então o número fechava por
acidente), `test_errors.py` (lista de exceções), `test_tables.py` (conjunto de
tabelas) e `test_composition_root_identity.py` (prefixo da varredura de adapters).
São exatamente as guardas que existem para forçar revisão consciente; atualizá-las
é o comportamento desejado, não desvio de escopo.

### 2026-07-20 — [deviation] CA7 verificada em dois níveis — Claude (autônomo)
O technical atribuía a CA7 (autorização do convite) à Task 12. O Checkpoint C do
terceiro bloco mostrou que a cobertura ficara só no e2e, e que todos os convites de
lá passam `unit_ids: []` — de modo que a autorização **por unidade** não era
exercitada. Os testes foram para `test_http_router.py`, no par negativo + positivo.
Mutação real confirmou que o negativo sozinho é falso verde: removendo
`unit_ids=unit_ids`, quem falha é o teste positivo.

### 2026-07-20 — [finding] Adapter Resend real + credencial — Claude (autônomo)
O provedor está decidido (kickoff #7), mas o ADR 0.0.0004 §Decision 7 proíbe
chamada externa nesta corrida e a API key é do sponsor. Entregue `ConsoleSender`,
que satisfaz o DoD. **Stage candidata: `6.2-deploy-pipeline`.** Direção sugerida:
adapter HTTP sobre a API da Resend, com `email_from` voltando a `Settings` junto —
e sem imprimir o corpo em log, ao contrário do `ConsoleSender`.

### 2026-07-20 — [finding] Oráculo de tempo no pedido de redefinição — Claude (autônomo)
Status, corpo e cabeçalhos são idênticos (CA12, provado no e2e), mas o caminho
"e-mail cadastrado" grava e envia, enquanto o "não cadastrado" retorna na hora. A
diferença é medível. Fechá-la exige envio assíncrono (fila), que é decisão de
infraestrutura. **Stage candidata: Step 6** (hardening/deploy).

### 2026-07-20 — [finding] Rate limiting das rotas públicas — Claude (autônomo)
`/auth/password-reset-requests` e `/auth/password` não têm limite. A primeira é
vetor de mail-bomb contra um endereço cadastrado; a segunda admite força bruta
sobre o espaço de tokens — mitigada pelos 256 bits de entropia e pelo TTL curto,
não eliminada. **Stage candidata: Step 6.**

### 2026-07-20 — [finding] Oráculo de existência global de conta no 409 do convite — Claude (autônomo)
`EmailAlreadyRegisteredError` (409) revela, a qualquer `manager`, que um e-mail
existe **em algum tenant** — a unicidade é global por decisão de kickoff #2. É
herdado da 2.4 (`POST /users` faz o mesmo, e `error_handlers.py` declara a
aceitação por escrito); a rota de convite herda em vez de divergir, porque duas
semânticas de conflito seriam piores. **Agravante novo:** uma sondagem
bem-sucedida agora também dispara e-mail ao endereço sondado. **Stage candidata:
Step 6** (hardening).

### 2026-07-20 — [finding] Rota autenticada de reenvio de convite — Claude (autônomo)
Não existe: reconvidar responde 409, então só o próprio convidado consegue um link
novo, pela rota pública de redefinição. Um administrador não consegue reenviar.
**Stage candidata:** a que tratar de gestão de usuários (Step 6 ou a Stage de
administração).

### 2026-07-20 — [finding] Docstring de `dummy_hash()` continua afirmando o que é falso — Claude (autônomo)
O port diz "`verify` sempre falha", e isso não vale para `_SENTINELA_DUMMY`. Esta
Stage deixou de depender da afirmação (ADR 2.5.0004) e a corrigiu **no ponto de
uso**, mas o texto do port segue convidando o próximo leitor ao mesmo erro. Direção
sugerida: reescrever a lei 2 como "nenhuma senha **que não seja a semente**
verifica" e acrescentar o parâmetro nominal ao teste de contrato do dummy, como já
foi feito para `unusable_hash`. **Stage candidata: Step 6.**

### 2026-07-20 — [finding] Atomicidade dos quatro passos da redefinição — Claude (autônomo)
`set_password_with_token` faz quatro escritas sem transação abrangente. A ordenação
fail-closed (regra 5) garante que toda falha parcial deixa a conta *mais fechada*,
e é o que torna a ausência de unidade de trabalho aceitável — não o que a resolve.
Reforça o `[finding]` de atomicidade já escalado pela 2.4. **Stage candidata:
`4.4`** (unit of work), como a 2.4 indicou.

### 2026-07-20 — [finding] Estado explícito de "conta não ativada" — Claude (autônomo)
Hoje é implícito: o hash é inutilizável. Uma coluna própria permitiria listar
convites pendentes — e criaria o sinal de enumeração que hoje não existe. **Stage
candidata:** a que precisar da listagem.

### 2026-07-20 — [decision] Auditoria independente aprovou condicionada a duas adições de teste — Claude (autônomo)
A auditoria confirmou o código de produção correto e apontou duas lacunas **de
gate**, não de comportamento. Ambas fechadas sem tocar em produção.

1. **Origem da entropia de `unusable_hash()`** — `test_unusable_hash_deriva_de_secrets_a_cada_chamada`
   (`tests/unit/.../test_argon2_hasher.py`). Os testes de contrato só observavam o
   *resultado*, e o resultado não distingue nada: o salt por hash do argon2 já faz
   duas chamadas com a mesma pré-imagem devolverem strings diferentes, então a lei
   "muda a cada chamada" passava com qualquer implementação. A prova do auditor:
   trocar `secrets.token_urlsafe(32)` por um literal deixava a suíte inteira verde
   (reproduzido: 892 passed com o novo teste deselecionado) — e é o mesmo bypass da
   ADR 2.5.0004. O novo teste assere a **propriedade** via `monkeypatch` no
   `secrets` do módulo: pré-imagem pedida a `secrets`, com ≥32 bytes, **duas vezes**
   em duas chamadas. Trava a origem, não uma lista de literais proibidos — o teste
   antigo parametrizava quatro strings e qualquer quinta escapava.
2. **Asserção vácua em metade da parametrização** — `test_rotas_novas_sao_publicas`
   virou `test_definir_senha_e_publica` + `test_pedir_redefinicao_e_publica`. O
   `!= 401 or rota == "/auth/password"` era trivialmente verdadeiro para um dos dois
   params. A correção assere o **204/202 do caminho feliz sem `Authorization`**: o
   401 é ambíguo por natureza (é também a resposta legítima a token inválido), então
   só a requisição que deveria ter sucesso separa "rota exige login" de "token não
   serve".

### `[decision]` — primeira rodada de auditoria de testes (registro que faltava)

Achado F2 da auditoria de Stage (PR #28): a §7 documentava só a auditoria
independente, deixando sem rastro a **primeira** rodada, cujos seis achados foram
fechados em `6f08227`, `71ce25a` e `61d86a2`. Registro aqui porque a §7 é o registro
permanente — o corpo do PR não é.

O achado principal daquela rodada é o mais instrutivo da Stage: mutar
`except Exception` para `except RuntimeError` em `request_password_reset` matava
**zero** testes, com a linha marcada a **100% de cobertura**. Todas as injeções de
falha dos testes eram `RuntimeError`, então a linha executava sempre e a **largura**
do `except` nunca era exercitada. Fechado com `FalhaDeProvedor(Exception)` cobrindo
os dois lados (sender e repositório); a auditoria independente reaplicou a mutação e
confirmou que agora morre em dois testes.

Os outros cinco achados da rodada: a corrida perdida do `consume` não era asserida no
use case, e as duas rotas não tinham teste provando o 500 real. Todos com commit
dedicado.

**Lição, e ela vale além desta Stage:** cobertura de linha mede **execução**, não
**verificação**. Um `except`, um `if` ou uma parametrização podem estar a 100% com
apenas um representante estreito da categoria sendo exercitado. A mesma classe
reapareceu duas vezes nesta Stage — no `except`, e depois em `unusable_hash()`, onde
o teste travava a lista de senhas conhecidas em vez da origem da entropia.

### 2026-09-26 — [finding] regra 1 do concept ganhou um carve-out declarado na Stage 3.5 — Claude (autônomo)
**Contexto:** a regra 1 do concept da 2.5 ("o valor do token existe entre a emissão e o corpo
do e-mail, e em nenhum outro lugar") passou a ter **uma** exceção nomeada: o
`ProvisionedAccountResult` de `ProvisionAccountUseCase` (identity) carrega o `setup_link`
(`repr=False`) para que o gateway de staff possa entregá-lo **em mãos** pela rota R17 no canal
`link` — ao gestor que acabou de provar `manage_staff` e `manage_users` sobre a unidade. O
convite por e-mail da 2.5 (`InviteUserUseCase`) e o reset **não mudaram**; a composição do link
e da mensagem passou a viver em `use_cases/_invitation.py`, byte-idêntica.
**Razão:** decisão do sponsor (concept 3.5 §13 Q1) e
[ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §Status;
o carve-out é do tamanho de um result, com a contenção (`repr=False`, nenhuma exceção o carrega,
só o canal `link` o expõe) asserida por teste na 3.5 (CA05, CA14).

<!-- END: post-execution -->

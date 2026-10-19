# LAYOUT.md — Convenções de Arquitetura

Este documento é a fonte da verdade sobre como o código está organizado e quais regras de
dependência devem ser seguidas. **Leia antes de criar qualquer arquivo.**

---

## 1. Visão Geral

A arquitetura combina dois padrões complementares:

**Vertical Slices (Feature-based):** cada funcionalidade de negócio vive em seu próprio
diretório (`features/<feature>/`), contendo todas as camadas necessárias — desde a entidade
de domínio até o controller HTTP. Isso maximiza a coesão: tudo relacionado a um bounded
context fica em `features/<feature>/`.

**Ports & Adapters (Hexagonal) dentro de cada slice:** o interior de cada feature é dividido
em camadas com regras rígidas de dependência. O domínio não sabe nada sobre o mundo externo;
a aplicação orquestra via interfaces (ports); os adapters conectam ao mundo real.

**Shared (Preocupações Transversais):** código genuinamente reutilizável entre features fica
em `shared/`. Tudo que é específico de uma feature fica na feature.

---

## 2. Estrutura de Pastas

```
src/restaurant_hub/
├── main.py                         # Entrypoint ASGI
├── composition_root.py             # Única wiring point — instancia dependências concretas
│
├── features/                       # Um diretório por bounded context / vertical slice
│   └── <feature>/                  # Placeholder: cada feature do seu projeto
│       ├── domain/                 # Núcleo — zero dependências externas
│       │   ├── entities/           # Objetos com identidade
│       │   ├── value_objects/      # Objetos imutáveis sem identidade
│       │   ├── services/           # Serviços de domínio (lógica que não cabe em entidade)
│       │   └── exceptions/         # Exceções de domínio
│       │
│       ├── application/            # Orquestração — depende apenas de domain + ports
│       │   ├── use_cases/          # Um arquivo por use case (create_order.py, cancel_order.py) — são os ports primários
│       │   ├── dtos/               # Objetos de transferência (commands, queries, results)
│       │   ├── facade.py           # (opcional) Open Host Service: o único módulo deste BC importável por outro BC (§3)
│       │   └── ports/              # Interfaces (Protocols Python)
│       │       └── out/            # Ports secundários / driven
│       │
│       └── adapters/               # Implementações concretas dos ports
│           ├── inbound/            # Adapters primários (HTTP, CLI, workers)
│           │   └── http/           # Router FastAPI, schemas Pydantic de request/response
│           └── out/                # Adapters secundários (banco, email, APIs externas)
│               ├── postgres/       # Repositório SQLAlchemy, mappers
│               └── identity/       # Gateway para outro BC: implementa um port daqui sobre a fachada de lá (§3)
│
└── shared/                         # Código transversal — usado por múltiplas features
    ├── domain/                     # Exceções base do sistema (DomainError, NotFoundError)
    ├── application/                # Ports compartilhados (Clock, IdGenerator)
    └── infrastructure/             # Implementações de infraestrutura
        ├── config/                 # Settings (pydantic-settings)
        ├── database/               # Engine SQLAlchemy, sessões
        ├── http/                   # FastAPI app factory, middlewares, error handlers
        ├── logging/                # Configuração de logging estruturado
        ├── clock/                  # SystemClock (implementa shared Clock port)
        └── uuid_generator/         # Uuid4Generator (implementa shared IdGenerator port)

tests/
├── unit/                           # Testes sem I/O — rápidos, sem fixtures de banco
│   ├── features/<feature>/
│   │   ├── domain/                 # Testam entidades, value objects, serviços
│   │   ├── application/            # Testam use cases com fakes
│   │   └── adapters/               # Parte do adapter testável SEM I/O (schema declarado, mappers puros, wiring)
│   ├── shared/                     # tests/unit/shared/ — kernel compartilhado (espelha src/restaurant_hub/shared/)
│   └── test_bootstrap.py           # Testa composition_root + entrypoint main (sem feature)
├── integration/                    # Testam adapters reais contra banco/serviços
│   └── features/<feature>/adapters/out/postgres/
├── contract/                       # Validam que fake e implementação real respeitam o contrato
│   └── features/<feature>/
├── e2e/                            # Sobem a app completa via HTTP
│   ├── features/<feature>/
│   └── test_app_smoke.py           # Smoke da app factory (middlewares + error handlers, sem feature)
└── fakes/                          # Implementações fake dos ports para uso em testes
    ├── shared/                     # Fakes dos ports compartilhados (Clock, IdGenerator)
    └── features/<feature>/
        └── in_memory_<entity>_repository.py

migrations/
├── alembic.ini
├── env.py
└── versions/                       # Arquivos gerados pelo alembic revision
```

---

## 3. Camadas e Regras de Dependência

A regra fundamental: **as dependências apontam para dentro** (em direção ao domínio),
nunca para fora.

```
adapters  →  application  →  domain
               ↑
           shared/application/ports
               ↑
           shared/infrastructure  (apenas via composition_root)
```

### Domain

- **Pode importar de:** apenas stdlib Python e outros módulos dentro de `domain/`
- **Nunca pode importar de:** `application/`, `adapters/`, `shared/infrastructure/`, FastAPI, SQLAlchemy
- **Contém:** entidades, value objects, serviços de domínio, exceções de domínio

### Application

- **Pode importar de:** `domain/`, `shared/domain/`, `shared/application/ports/`
- **Nunca pode importar de:** `adapters/`, `shared/infrastructure/`
- **Contém:** use cases, DTOs (commands, queries, results), ports (Protocols)

### Adapters

- **Pode importar de:** `application/` (ports e DTOs), `domain/` (entidades para mappers)
- **Nunca pode importar de:** outros adapters da mesma feature (exceto via port)
- **Contém:** implementações concretas dos ports (repositórios, controllers HTTP)

### Travessia entre bounded contexts (desde a Stage 3.5)

Bounded contexts são **independentes** (contrato `bc-independence` do import-linter):
nenhum módulo de `features/<a>/` importa `features/<b>/`. A única exceção tem forma fixa
([ADR 3.5.0001](./adr/3_5_0001-cross-bc-facade-and-gateway-edge.md)):

- o BC **fornecedor** expõe um *Open Host Service* in-process em
  `features/<b>/application/facade.py` — assinaturas em **primitivos**, conversão para
  value objects por dentro, exceções próprias **sem tradução**, re-exportando as que o
  consumidor precisa capturar; a fachada **não autoriza**;
- o BC **consumidor** implementa o seu port-out num **gateway** em
  `features/<a>/adapters/out/<b>/`, que importa **só** `features.<b>.application.facade`
  e traduz as exceções para o vocabulário do próprio BC;
- a aresta é **nomeada** no `.importlinter`, um par por travessia
  (`features.<a>.adapters.out.<b>.* -> features.<b>.application.facade`, com
  `unmatched_ignore_imports_alerting = error`), e um teste assere a **lista exata** — uma
  segunda aresta entra por decisão, nunca por deriva.

O que a fachada **não** substitui: o tradutor de autenticação/autorização de identity
continua no `composition_root` (ADR 3.4.0001 §3; ADR 3.5.0001 §5), porque o guard é
construído por um módulo do adapter de entrada e chega ao contêiner como dependência
resolvida, não como import de outro BC.

### Shared

- `shared/domain/` — mesmas regras de `domain/`
- `shared/application/` — mesmas regras de `application/`
- `shared/infrastructure/` — pode usar qualquer lib externa; é instanciado no composition_root

> **Trocar uma dependência operacional** (provedor LLM, banco, scheduler)
> sem quebrar o port nem perder o rastro de decisão: ver
> [`operational-evolution-policy.md`](./operational-evolution-policy.md)
> (3 invariantes de neutralidade do port + ADR com `supersedes`).

---

## 4. Features vs Shared

**Coloque em `features/<nome>/`** quando:
- A lógica é específica de um bounded context (ex: cálculo de desconto de pedidos)
- A entidade tem identidade própria naquele contexto (ex: `Payment`, `Customer`)
- O port é consumido apenas por aquela feature

**Coloque em `shared/`** quando:
- É genuinamente reutilizado por 2+ features (ex: `Clock`, `IdGenerator`, `EmailSender`)
- É infraestrutura cross-cutting (ex: configuração, logging, factory do FastAPI)
- É uma abstração de domínio agnóstica (ex: `DomainError`, `NotFoundError`)

**Regra prática:** em caso de dúvida, comece na feature. Mova para shared apenas quando
a segunda feature precisar do mesmo código.

**E "reutilizado" é medido, não previsto.** `Pagination` e `ApplicationError`
entraram aqui pelo template e passaram seis Stages sem um único consumidor —
`Pagination` levantando `ValueError` cru, que não é `DomainError` e, alcançado
pelo HTTP, produziria 500. Os dois foram removidos na issue #45, e
`scripts/check_dead_shared.py` (alvo `layout-check`) reprova o nome público de
`shared/domain/` ou `shared/application/` que não tem uso em `src/`. Promoção
para `shared/` sem consumidor não é abstração prematura só em teoria: é código
que ninguém exercita, num pacote que todas as features leem.

---

## 5. Portas (Ports)

Ports são interfaces Python (`Protocol`) que definem contratos entre camadas.

### Ports Primários / Driving — são as classes de use case

São acionados por atores externos (HTTP, CLI, mensageria) e definem o que a aplicação
**aceita** como entrada. **Não há `ports/in/`**: o port primário deste projeto é a
própria classe de use case, com o seu `execute(<Command>) -> <Result>`. O adapter de
entrada recebe a instância por injeção (`Depends`) e a chama.

Um `Protocol` separado por use case seria uma interface com exatamente uma
implementação, escrita por nós, para desacoplar código nosso de código nosso — e
nenhum consumidor a usaria como ponto de variação. O que precisa ser abstrato é o que
o use case **consome**, e isso são os ports de saída. Ver **ADR 0.0.0006**.

### Ports Secundários / Driven (`ports/out/`)

São implementados por adapters externos. Definem o que a aplicação **precisa** do mundo
externo. O use case depende da interface, não da implementação concreta.

Exemplo: `<Entity>Repository` — contrato que o use case usa para persistir uma entidade.

---

### A fronteira transacional (desde a Stage 2.6)

Use case que escreve **mais de uma vez** numa requisição escreve dentro de uma
**unidade de trabalho** — um port de saída como os outros, injetado pelo
composition root ([ADR 2.6.0001](./adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md),
[ADR 2.6.0002](./adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)):

- **Quem abre a unidade é o use case**, com `with self._unit_of_work.transaction():`
  em volta **só** das escritas que precisam ser atômicas. Leitura e checagem que
  decidem se haverá escrita vêm antes; trabalho de CPU (hash de senha, emissão de
  token) vem antes; efeito colateral que não se desfaz (e-mail) vem **depois** do
  commit. Escrita que precisa comitar mesmo quando o use case recusa (a revogação
  em massa do reuso de refresh) fica fora, seguida do `raise`.
- **A unidade é de um bounded context e não atravessa a fachada.** Hoje só
  identity tem uma (`features/identity/application/ports/out/unit_of_work.py`);
  staff escreve uma vez por requisição em staff, e as travessias staff → identity
  seguem ordenadas, com as janelas declaradas (ADR 4.1.0006 Alt. A). O port fica
  na feature até um segundo BC precisar dele (§4).
- **O adapter não muda o construtor dos repositórios**: eles pedem a conexão a
  `conexao_da_unidade` e recebem a da unidade ativa do **mesmo** engine, num
  savepoint por chamada — por isso repositório e unidade precisam do mesmo
  `Engine` no composition root.
- **`scripts/check_layout.py` regra 10** reprova o use case com duas ou mais
  escritas que não estejam todas dentro de **um** bloco de unidade (escrita em
  laço conta duas; só o "grava e recusa" é tolerado fora). Exceções vivem numa
  allowlist contável, como a do charter (regra 6) — hoje, as duas travessias de
  staff para identity.

## 6. Composition Root

`composition_root.py` é o **único ponto de wiring** da aplicação. Ele:

1. Lê a configuração via `Settings`
2. Instancia dependências de infraestrutura (engine, clock, id generator)
3. Instancia repositórios concretos (ex: `PostgresPaymentRepository`)
4. Injeta tudo nos use cases
5. Expõe os use cases montados para o restante da aplicação

**O charter, como regra mecânica (issue #45, `check_layout.py` regra 6).** O
módulo só pode conter classes `@dataclass` (os contêineres), as duas funções de
wiring — `wire_dependencies` e `build_http_wiring` — e **nenhum `raise`**: quem
monta o grafo não recusa pedido. O que hoje foge disso (`_IdentityAccessGuard`
e o seu helper `_tenant_id_do_ator`) está em allowlist **contável** no script,
cada entrada citando a issue que a remove (#47); entrada nova reprova até ser
justificada, e entrada que já não corresponde a nada em `src/` reprova também.

**Por que isso importa:**
- Mantém o domínio e a application totalmente desacoplados de implementações concretas
- Facilita trocar uma implementação (ex: Postgres → DynamoDB) sem tocar em nenhuma regra de negócio
- Torna o grafo de dependências explícito e auditável em um único arquivo

```python
# composition_root.py — exemplo de uso
deps = wire_dependencies()
app.dependency_overrides[get_create_order_use_case] = lambda: deps.create_order
```

**Fronteira aceita — `shared/infrastructure` ↔ `composition_root`.** O arquivo
`shared/infrastructure/http/app.py` (factory do FastAPI) importa
`composition_root`, que por sua vez importa adapters de features para fazer o
wiring. Isso parece quebrar a regra "shared não importa de features", mas é
exceção declarada: composition_root é o **único** ponto onde o caminho indireto
`shared → composition_root → features.adapters` é permitido. O
`scripts/check_layout.py` não detecta esse caminho indireto (limitação
documentada no script) — depende de revisão manual no gate de saída da Stage.

---

## 7. Regras de Ouro

- **Domain tem zero I/O.** Nenhuma entidade ou value object chama banco, rede ou arquivo.
- **Use cases retornam DTOs, não entidades.** Entidades de domínio (com identidade, mutáveis) não vazam para fora da camada application. **Value objects** imutáveis de domínio (ex: `Money`) **podem** trafegar em DTOs — são valores puros sem identidade, indistinguíveis de tipos primitivos do ponto de vista do consumidor.
- **Um use case por arquivo.** `create_order.py`, não `order_use_cases.py`.
- **Adapters implementam ports.** `PostgresPaymentRepository` satisfaz `PaymentRepository` Protocol.
- **Fakes implementam os mesmos ports.** `InMemoryPaymentRepository` satisfaz `PaymentRepository` Protocol.
- **Testes unitários usam fakes.** Nenhum teste unitário toca banco ou rede.
- **Tests de contrato validam a equivalência.** A fake e a implementação real devem passar nos mesmos testes.
- **O tenant que decide acesso vem do token.** Um tenant na requisição é declaração **confirmada contra** ele, nunca a fonte; só aparece no path quando o BC é dono do tenant como recurso endereçável, ou o ator pode agir fora do próprio tenant. Texto normativo (três cláusulas), fontes e gatilho de reabertura: [ADR 0.0.0005](./adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md).
- **Imports sempre absolutos.** Nunca `from ..domain import` — use o caminho completo.
- **Nenhum import circular.** Se você precisar, é sinal de que a camada está errada.
- **Shared não importa de features.** O fluxo é sempre: features → shared, nunca o contrário.


---
title: Concept — Acesso e escopo de equipe
description: Definição do que será feito nesta Stage e por quê, com decisões técnicas relevantes
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, staff, acesso, permissao, rbac, escopo-unidade, tenant-wide, access-guard, port, byte-nul]
status: draft
created_at: 2026-08-12
updated_at: 2026-08-12
stage_id: 3.4-staff-access-scope
stage_title: Acesso e escopo de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [3.3-staff-persistence]
---

# Concept — Stage 3.4 — Acesso e escopo de equipe

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task) e critérios de atomicidade, ver
> [`PIPELINE.md`](../../PIPELINE.md) §4.
>
> **Status (apenas dois estados).** `draft` desde a criação; `done` após
> o gate humano. Regressão `done → draft` é **permitida** quando a
> Fase 3B (Technical) revela gap material aqui — neste caso, commit
> `chore(concept): revert to draft — revision-from-technical: <motivo>`.

> **Esta Stage nasceu de um corte.** Ela era `3.4-staff-http` — "expor por HTTP
> os 16 use cases de equipe". Com as três decisões do sponsor de 2026-08-12 e os
> achados do Checkpoint A, o plano mediu **14 Tasks**, o limiar de "Stage grande
> demais" de [`CONVENTIONS.md`](../../CONVENTIONS.md) §6. O corte foi aprovado e
> caiu na fronteira entre **emendar Stage fechada** e **escrever superfície
> nova**: esta Stage é a fundação (6 Tasks) e **não expõe nenhuma rota**; a borda
> HTTP é a Stage **3.6** (8 Tasks), que depende desta. Ver §13 e a nota datada do
> bloco 3.4 no [`roadmap.md`](../../roadmap.md).

## 1. Escopo

### Dentro do escopo

- **Vocabulário de acesso de equipe em identity** — `MANAGE_STAFF` e
  `MANAGE_JOB_FUNCTIONS` em `Permission`, as entradas correspondentes no mapa
  de papéis, e o conjunto `TENANT_WIDE_PERMISSIONS` (§7 D4/D5).
- **Dispensa da exigência de unidade para permissão tenant-wide** — a condição
  do passo 4 de `AuthorizeActionUseCase` (§7 D5).
- **A unidade no endereço do funcionário** — assinatura de
  `EmployeeRepository.find_by_id`/`delete`, os dez commands que atuam sobre
  registro existente, os doze use cases, os fakes, os dois adapters Postgres e
  a suíte de contrato (§7 D3).
- **Port `AccessGuard` do BC staff** com as suas quatro leis, o fake que as
  satisfaz, e o tradutor sobre `IdentityGuard` montado no composition root
  (§7 D1).
- **Duas correções no domínio da 3.1** que a borda não tem como fazer sozinha:
  rejeição do byte NUL em nome e `DayPeriod.from_string` com
  `InvalidDayPeriodError` (§7 D2).

**Expansões de camada-alvo, todas declaradas:**

| Camada tocada | Stage de origem | Autorização |
|---|---|---|
| `features/identity/domain` + `application` | 2.1 / 2.2 / 2.4 | **sponsor, 2026-08-12** — *"não há problema em tocar o módulo de acesso; isso irá acontecer ao longo do desenvolvimento quando forem surgindo mais features"* |
| `features/staff/application` (port, commands, use cases, fakes) | 3.2 | decisão do sponsor sobre o escopo de unidade (ADR 3.4.0007) |
| `features/staff/adapters/out/postgres` + `tests/contract` | 3.3 | idem |
| `features/staff/domain` | 3.1 | `[finding]` da 3.3 escalado para cá (ADR 3.4.0003) |

> **A assimetria aparente entre estas expansões e a recusa de tocar identity
> pelo byte NUL é deliberada.** A recusa não é uma regra sobre identity — é a
> regra de **preferir o conserto local quando ele existe**. Para o byte NUL em
> nome de funcionário existe conserto dentro de staff; para o vocabulário de
> permissões, não: ele só existe em identity.

### Fora do escopo (explicitamente)

- **Toda a superfície HTTP de equipe** — router, schemas Pydantic, handlers de
  erro, mapa de status e testes e2e. É a **Stage 3.6**, que depende desta.
  Nenhuma rota nasce aqui, e é isso que torna esta Stage segura de mergear:
  ela fecha dois buracos **antes** de existir superfície que os exponha.
- **Paginação** das listagens — decidida (não entra) no ADR 3.4.0004, que
  governa a 3.6.
- **Busca ampla de funcionário no restaurante inteiro** — o sponsor descreveu o
  caso (ao cadastrar alguém novo, procurar entre os já cadastrados de todas as
  unidades, *"se ele tiver a permissão de ver todos os funcionários de todas as
  unidades"*). É **operação separada, com permissão própria**, e não existe
  hoje. **Não pode ser obtida afrouxando a busca desta Stage.** `[finding]` §10.
- **Habilitação de função de trabalho por unidade** — issue **#41**, fatia
  vertical nas quatro camadas. Nada dela aqui; o que esta Stage entrega é o
  **alicerce** dela (§7 D5).
- **Permissão de `hr` sobre a escala** — a divergência hr × manager
  materializa-se no **Step 4**. Restrição para frente (§5.2), não escopo daqui.
- **Vínculo de login do funcionário** (`user_id`) — Stage 3.5.
- **Controle otimista de concorrência** — escalado pela 3.3 (ADR 3.3.0006),
  segue aberto.
- **Leitura de funcionário por id** — o mecanismo escolhido para o escopo de
  unidade foi a assinatura, não um use case de leitura; a rota que uma tela vai
  querer segue inexistente. `[finding]` §10.

### Reconciliação do bloco 3.4 do roadmap

O bloco fica desatualizado em **seis** eixos, todos na nota datada:

1. **A Stage deixou de ser a API de equipe** — foi cortada, e o slug mudou de
   `staff-http` para `staff-access-scope`. A borda é a 3.6.
2. **`contratos_introduzidos: []` não se sustenta** — o port `AccessGuard`, o
   DTO `AuthorizedScope`, duas permissões e `TENANT_WIDE_PERMISSIONS`.
3. **`non_goals: []` não se sustenta** — são oito (§1).
4. **`arquivos_a_criar` incorreto** — `{router,schemas}.py` e
   `tests/e2e/features/staff/` são da 3.6; aqui nascem
   `application/ports/out/access_guard.py` e os testes de lei do port.
5. **`camada_alvo: adapters/in/http` errado** — as camadas reais estão na
   tabela de §1.
6. **`complexidade_estimada: S` errado** — a Stage é **M**.

E **três** afirmações de outras fontes ficam falsas, e a mesma nota as corrige:
(a) `roadmap.md` §Stage 3.3 (*"contrato consumido pela 3.4, cuja paginação usa
`(name, id)` como cursor"*); (b) a `[finding]` de 2026-08-12 na §7 do
`technical.md` da 3.3 (*"a paginação da 3.4 acrescenta `LIMIT`/`OFFSET`"*) —
nenhuma das duas Stages pagina, o cursor fica **preparado**, não consumido
(ADR 3.4.0004); e (c) o **ADR 3.3.0006** §Consequences, que aloca a coluna de
versão do controle otimista à *"migration da 3.4-staff-http"* — esta Stage não
cria migration nenhuma (§9), e o controle otimista segue aberto.

> **Os findings escalados continuam dizendo "Stage candidata: `3.4-staff-http`"**
> — na **§10 do `concept.md` da 3.2** e na **§7 do `technical.md` da 3.3**, ambas
> seladas. Não as reescrevo: são registro histórico, verdadeiro quando escrito.
> A tradução — quais findings vieram para cá e quais foram para a 3.6 — está na
> nota datada do roadmap, que é o lugar canônico de reconciliação.

### Vínculo com o roadmap

O Step 3 tem um BC completo (3.1 domínio, 3.2 use cases, 3.3 persistência) que
**nada no boot da aplicação alcança** — o `composition_root.py` declara que os
16 campos de staff "nascem sem consumidor". Esta Stage não fecha essa lacuna;
ela constrói o que faltava para que a 3.6 possa fechá-la **sem publicar dois
defeitos de acesso** que só apareceram quando a borda foi desenhada.

## 2. Objetivo da Stage

Ao final desta Stage, o BC staff tem um vocabulário de acesso próprio e um
escopo de unidade imposto por assinatura, de modo que nenhuma superfície futura
consiga alcançar funcionário de outra unidade nem gerir o catálogo sem
permissão — e nada disso depende de o adapter de entrada lembrar de verificar.

## 3. Contexto e premissas

### Contexto

**Esta Stage existe porque a borda descobriu o que faltava.** O concept original
da `3.4-staff-http` desenhou as 16 rotas e, ao fazê-lo, encontrou três coisas
que a borda **não pode resolver sozinha** — duas delas achadas
independentemente pelos dois revisores do Checkpoint A:

1. **`manager` e `hr` não alcançariam o catálogo.** A função de trabalho é
   tenant-scoped (`workforce.md` §3.2), então as rotas de catálogo não têm
   unidade a declarar — e `authorize_action.py:81-83` nega quem não faz bypass
   quando `unit_id is None`. Só `owner` passaria, contra o DoD.
2. **O escopo de unidade não era enforçável na borda.** As rotas seriam
   aninhadas sob `/units/{unit_id}`, mas o `unit_id` do path é autorizado
   **contra o ator**, não **contra o registro**: como o lookup é
   `(tenant_id, employee_id)`, um gerente da unidade A alcança qualquer
   funcionário do mesmo restaurante. E como toda mutação devolveria o cadastro
   inteiro, o buraco não era só de escrita — era **sonda de leitura** e
   **exfiltração por cópia**.
3. **Não havia permissão de staff.** `Role.MANAGER` e `Role.HR` detêm
   exatamente `{MANAGE_USERS}`, que é sobre **conta de login**.

**O requisito do escopo de unidade já era ancorado.** ADR 3.2.0002 §Neutral:
*"Restricting a manager to their own units is an **authorization** decision, and
it belongs to Stage 3.4 with `authorize_action`."* O que o sponsor decidiu em
2026-08-12 foi o **mecanismo** — a unidade entra na assinatura.

**A Stage irmã de referência é a 2.4.** O BC identity resolveu autenticação,
autorização e composição no boundary, e o código está no repo. Onde esta Stage
toca identity, ela estende o desenho de lá; não o reinventa.

### Premissas

- **O `platform_admin` não tem acesso a staff** — detém só `MANAGE_PLATFORM`, e
  "acesso de plataforma não é acesso de restaurante" (concept 2.1 §5 regra 7).
- **Não há `Unit` nem `UnitMembership` em staff, e não haverá.** Toda pergunta
  sobre unidade é delegada a identity pelo port `AccessGuard`.
- **A suíte de lei dos dois ports já é teste de contrato** rodando contra fake e
  Postgres (ADR 3.3.0007) — é o veículo pelo qual a lei de unidade e a rejeição
  do byte NUL passam a valer nos dois lados por construção.
- **Postgres real é exigido pelos testes de integração** (ADR 2.3.0001).
- **`create_engine` não abre conexão**, então montar o tradutor do guard no
  composition root não muda o comportamento de boot.

### Dependências

- `3.3-staff-persistence`: os dois repositórios Postgres, o wiring dos 16 use
  cases, as suítes de contrato promovidas e a lei `L-ORD`.
- `3.2-staff-application`: os ports, os DTOs, os 16 use cases e os fakes — todos
  emendados aqui.
- `3.1-staff-domain`: as entidades e os value objects, dois deles emendados.
- `2.4-identity-http`: `IdentityGuard` e o padrão de composição no boundary.
- `2.2-identity-application`: `AuthorizeActionUseCase` e os dois eixos
  fail-closed (ADR 2.2.0002).
- `2.1-identity-domain`: `Permission`, `Role` e `_ROLE_PERMISSIONS`.

## 4. Contratos

### Introduzidos

- **`AccessGuard`** (`port-out` do BC staff —
  `features/staff/application/ports/out/access_guard.py`)

  ```python
  Actor = object  # credencial já verificada; staff não a interpreta

  @dataclass(frozen=True)
  class AuthorizedScope:
      tenant_id: TenantId          # nunca None — lei L-AG3
      unit_id: UnitId | None

  class AccessGuard(Protocol):
      def authenticate(self, request: object) -> Actor: ...
      def authorize(
          self,
          actor: Actor,
          permission: str,
          *,
          tenant_id: str | None = None,
          unit_id: str | None = None,
      ) -> AuthorizedScope: ...
  ```

  **Identificadores atravessam a fronteira entre BCs como strings opacas** —
  regra literal do `identifiers.py` de staff e do contrato `bc-independence`.
  O nome da permissão é `str` porque o vocabulário fechado vive em identity;
  os dois nomes que o Step 3 usa são `"manage_staff"` e
  `"manage_job_functions"`.

  **Leis do port** — sem elas uma segunda implementação satisfaz o tipo e
  destrói as propriedades de segurança sem falhar nenhum type check:

  - **L-AG1 —** `authenticate` levanta quando não há credencial válida, e a
    exceção **sai crua**: o tradutor não a traduz. É o que fará a faixa 401 da
    3.6 ser byte-idêntica à de identity.
  - **L-AG2 —** `authorize` levanta quando o ator não pode agir sobre o alvo, e
    a exceção **sai crua**, pela mesma razão (403 de corpo constante).
  - **L-AG3 —** `authorize` **nunca** devolve `AuthorizedScope` com `tenant_id`
    vazio ou ausente. Ator sem tenant é **negado**, não coagido para `""`:
    `TenantId` é `NewType` sem validação de runtime, então
    `TenantId(actor_tenant_id or "")` compilaria, passaria mypy strict e
    produziria consultas de tenant vazio — o balde de falso isolamento que
    `InvalidIdentifierError` nomeia.
  - **L-AG4 —** `authorize` é chamado **uma vez por alvo**; autorizar um alvo
    não autoriza outro.

- **`AuthorizedScope`** (`dto` de staff) — no mesmo módulo do port.

- **`Permission.MANAGE_STAFF`** e **`Permission.MANAGE_JOB_FUNCTIONS`**
  (identity) — ver §5.1.

- **`TENANT_WIDE_PERMISSIONS`** (identity) — `frozenset[Permission]` com as
  permissões cujo alvo é o restaurante e não a unidade. Hoje, um membro.

### Modificados

**Extensões aditivas** (nada que era válido deixa de ser):

- **`_ROLE_PERMISSIONS`** (identity) — `OWNER`, `MANAGER` e `HR` ganham as duas
  permissões novas; `EMPLOYEE` e `PLATFORM_ADMIN` não ganham nada.
- **`AuthorizeActionUseCase`** (identity) — o passo 4 passa a dispensar a
  exigência de unidade para permissão tenant-wide. Aditivo no sentido estrito:
  **nenhuma chamada hoje autorizada passa a ser negada**.
- **`DayPeriod`** — ganha `from_string` e o erro novo
  `InvalidDayPeriodError(StaffError)`.

**Restrição de assinatura** (chamadas hoje válidas deixam de compilar — §7 D3,
ADR 3.4.0007):

- **`EmployeeRepository.find_by_id` / `.delete`** — passam a receber
  `(tenant_id, unit_id, employee_id)`. É **lei do port**, não filtro de SQL,
  para que o fake carregue a mesma regra e a suíte de contrato prove os dois
  lados com um corpo só.
- **Os dez commands que atuam sobre registro existente** ganham `unit_id`:
  renomear, atribuir funções, trocar jornada, declarar preferência, registrar e
  remover indisponibilidade, desligar, recontratar, remover, e copiar (a
  unidade de **origem**; `target_unit_id` já existia). `CreateEmployeeCommand`
  já o carregava; as duas queries não mudam.
- **`L-E2`, `L-E3`, `L-E5`** — reescritas sobre o endereço de três partes.

**Restrição de contrato de domínio** (valor antes aceito passa a ser recusado):

- **`Employee.name` / `JobFunction.name`** — passam a rejeitar nome contendo o
  byte NUL, com `InvalidNameError` (§7 D2).

### Consumidos

- **Os 16 use cases de staff**, os dois ports e as suítes de contrato — todos
  declarados nas Stages 3.2 e 3.3.
- **`IdentityGuard`** — declarado na 2.4, alcançado **só** pelo tradutor montado
  no composition root.
- **`L-ORD`** (ADR 3.3.0003) — consumida, não estendida.

### Consumidor desta Stage

Nenhum, dentro dela. O port `AccessGuard`, as permissões e a lei de unidade
nascem **sem superfície que os exercite pelo entrypoint real** — quem os
exercita é a **Stage 3.6**. O custo está declarado: os critérios de §11 provam
que estão corretos e ligados, **não** que estão em uso por uma rota. É o mesmo
custo que a 3.3 assumiu ao wirar os 16 use cases sem adapter de entrada, e pela
mesma razão: a alternativa é uma Stage que entrega superfície sobre fundação
não provada.

## 5. Invariantes e regras

**5.1 — Matriz papel × staff.** `workforce.md` §4 mais a decisão do sponsor de
2026-08-12 (ADR 3.4.0006):

| Papel | Permissões de staff | Alcance |
|---|---|---|
| `owner` | `MANAGE_STAFF`, `MANAGE_JOB_FUNCTIONS` | todas as unidades do tenant (**bypassa** memberships) |
| `manager` | `MANAGE_STAFF`, `MANAGE_JOB_FUNCTIONS` | as unidades das quais é membro |
| `hr` | `MANAGE_STAFF`, `MANAGE_JOB_FUNCTIONS` — **as mesmas do `manager`** | as unidades das quais é membro — **sem alcance extra** |
| `employee` | nenhuma | — |
| `platform_admin` | nenhuma | — |

**Em staff, `hr` e `manager` são equivalentes.** O sponsor definiu o eixo da
divergência como **família de operação**, não alcance — *"RH pode mexer nos
cadastros dos funcionários (cadastrar, desativar, editar etc). Apenas o gerente
ou dono pode mexer na escala."* E confirmou que **jornada contratada,
preferência de turno e indisponibilidade são cadastro** (fatos contratuais e
pessoais do funcionário), logo o RH mexe nelas. Todas as operações do BC staff
são cadastro.

**5.2 — Restrição para frente, vinculante:** a **Stage 4.x não pode conceder a
`hr` nenhuma permissão sobre a escala.** É nisso, e só nisso, que a divergência
consiste. Registrada aqui e no ADR 3.4.0006 §3 — o arquivo que quem estender o
mapa de papéis vai ler.

> **O alcance cross-unidade do RH foi explicitamente NÃO concedido.** Era a
> opção recomendada quando a bifurcação foi devolvida ao sponsor; ele não a
> tomou. Registrado para que a recomendação não seja lida depois como decisão.

**5.3 — São duas permissões, e elas divergem no eixo de unidade.**
`MANAGE_JOB_FUNCTIONS` é **tenant-wide**: o catálogo pertence ao restaurante
(`workforce.md` §3.2) e não pode exigir unidade alvo. `MANAGE_STAFF` é
**unit-scoped**: o registro de funcionário tem de exigir. Uma permissão só não
pode ser as duas coisas.

**5.4 — A dispensa de unidade é por permissão, nunca por papel.** Um ator só
escapa da exigência quando a **permissão** que ele exerce está em
`TENANT_WIDE_PERMISSIONS`. `manager` continua unit-scoped para todo o resto,
inclusive `MANAGE_STAFF`. É o que impede a dispensa de virar bypass: o raio de
explosão de um engano fica em **uma capacidade**, não em um ator.

**5.5 — Os passos 3 e 5 do guard não mudam.** Escopo de tenant continua
valendo, e visibilidade de unidade continua rodando sempre que uma unidade
**é** declarada. A dispensa remove uma *exigência de nomear unidade*; não
remove nenhuma checagem.

**5.6 — A unidade faz parte do endereço do funcionário, até o port.** O lookup
é `(tenant_id, unit_id, employee_id)` — na assinatura, não só no `WHERE`
(ADR 3.4.0007). Consequências, todas verificáveis:

- Registro de **outra unidade do mesmo tenant** é **não encontrado**, pela mesma
  regra que já valia para outro tenant: nenhum erro confirma a existência de
  registro que o chamador não pode endereçar (concept 3.2 §5.4).
- Quem não sabe a unidade **não consegue formar a chamada**. É a propriedade que
  fez o escopo de tenant do ADR 3.2.0002 valer: omissão não é caminho.
- Os dois vetores que o Checkpoint A encontrou — sonda de leitura por rota de
  mutação e exfiltração por cópia — **não alcançam** registro de outra unidade,
  e fecham **antes** de existir rota.

**5.7 — A busca ampla continua não existindo, e não pode nascer daqui.**
Procurar entre funcionários de todas as unidades é operação separada, com
permissão própria — nunca esta busca com o filtro afrouxado.

**5.8 — A decisão de acesso não acontece em staff.** O port declara o requisito
(permissão + alvo) e delega. Não há tabela de papéis, mapa de permissões nem
lógica de bypass em `features/staff/`. Espelha `dependencies.py` de identity e
o ADR 2.4.0003 §1, e é verificável por teste (CA12).

**5.9 — `bc-independence` continua absoluto.** Nenhum módulo de
`features/staff/` importa `features/identity/`; o tradutor mora no composition
root, que já importa os dois BCs por desenho. Zero `ignore_imports`.

**5.10 — O byte NUL é recusado no domínio, e só ele.** Não se rejeitam acentos,
emoji com ZWJ, `\n`, aspas nem strings longas — a 3.3 mediu e todos fazem
round-trip verbatim nos dois lados. Alargar seria normalização silenciosa por
outro nome, contra o ADR 2.3.0005.

**5.11 — Nenhuma regressão de comportamento observável em identity.** As duas
permissões novas não são detidas por nenhum papel que já existisse com elas, e a
dispensa só afeta permissão que esteja no conjunto. A suíte de identity passa
sem alteração de asserção — se alguma precisar mudar, é sinal de que a mudança
não foi aditiva, e isso é achado, não ajuste (CA20).

## 6. Casos de erro e exceções

Esta Stage **não** define mapa de status HTTP — isso é da 3.6 (ADR 3.4.0002).
O que ela muda no comportamento de erro:

| Cenário | Antes | Depois | Camada |
|---|---|---|---|
| Nome com byte NUL | fake grava; Postgres levanta `psycopg.DataError` (recusa **client-side**, sem sqlstate, `constraint_name` nulo) | `InvalidNameError` na construção, nos **dois** lados | domínio (3.1) |
| Período do dia desconhecido | `DayPeriod("xpto")` → `ValueError` (não é `StaffError`) | `InvalidDayPeriodError` | domínio (3.1) |
| Funcionário de **outra unidade** do mesmo tenant | encontrado e operado | `EmployeeNotFoundError` | port + application |
| Ator sem tenant alcançando o tradutor | coerção silenciosa para `""` | **negado** (L-AG3) | adapter do guard |
| Ator unit-scoped exercendo permissão tenant-wide sem unidade | `UnitScopeRequiredError` | autorizado (§5.4) | identity application |

**`EmployeeRelocationError` sobrevive como lei, com gatilho mais estreito.** Com
a unidade no lookup, os use cases recarregam da mesma unidade em que escrevem,
então a relocalização deixa de ser alcançável por eles. A lei permanece porque
um segundo adapter poderia tentá-la.

**Os erros de concorrência do Postgres (`40P01`, `40001`) continuam subindo
crus**, e isso é declarado: são falhas transitórias de infraestrutura. Quem
decide o que a borda faz com eles é a 3.6.

## 7. Decisões técnicas relevantes

### D1 — Port `AccessGuard` de staff, com tradutor no composition root

- **O quê:** staff declara o port (vocabulário próprio, identificadores como
  `str` opaca, quatro leis); a implementação é montada em
  `composition_root.py`, que já importa os dois BCs.
- **Por quê:** a alternativa (adapter em `features/staff/adapters/out/identity/`
  com `ignore_imports`) caiu na medição — `IdentityGuard` vive sob o pacote
  `in`, que é keyword Python, então o adapter não conseguiria sequer anotar o
  objeto que embrulha, e a supressão seriam **três** pares, não um. O
  composition root mantém `bc-independence` **sem nenhuma supressão**.
- **Fonte:** `composition_root.py:24-27` e `:185-188`; `.importlinter`;
  LAYOUT §1, §6; roadmap §Stage 3.5.
- **ADR:** [`../../adr/3_4_0001-staff-owned-access-guard-port.md`](../../adr/3_4_0001-staff-owned-access-guard-port.md)

### D2 — Byte NUL rejeitado no domínio; `DayPeriod` ganha `from_string`

- **O quê:** `Employee`/`JobFunction` recusam nome com `\x00`
  (`InvalidNameError`); `DayPeriod.from_string` levanta `InvalidDayPeriodError`.
- **Por quê:** `DataError` **não** é `IntegrityError`, então o tradutor da 3.3
  nunca é chamado; a recusa é client-side, sem sqlstate. Rejeitar no domínio é o
  único conserto que faz fake e real concordarem **por construção**, e é o que
  permite a suíte de lei exercitar o caso. `DayPeriod` é o mesmo padrão do
  `Role.from_string` de identity, e sem ele a 3.6 teria um 500 por texto de
  requisição.
- **Fonte:** `[finding]` da 3.3 §7 (2026-08-11), com a tabela de medição.
- **ADR:** [`../../adr/3_4_0003-reject-nul-byte-in-staff-domain-names.md`](../../adr/3_4_0003-reject-nul-byte-in-staff-domain-names.md)

### D3 — A unidade entra no endereço do funcionário, na assinatura

- **O quê:** `find_by_id`/`delete` passam a `(tenant_id, unit_id, employee_id)`;
  dez commands ganham `unit_id`; fakes, adapters e suíte de contrato
  reconciliados.
- **Por quê:** o requisito era ancorado (ADR 3.2.0002 §Neutral); o Checkpoint A
  mostrou que a borda sozinha não o alcança. Na assinatura e não no SQL porque
  filtrar só no adapter deixaria o fake aceitando o que o real recusa — a
  divergência fake ≢ real que este Step já pagou uma vez (byte NUL), agora sobre
  um invariante de **segurança**.
- **Fonte:** decisão do sponsor, 2026-08-12; achados S2/C2 do Checkpoint A;
  `workforce.md` §3.1.
- **ADR:** [`../../adr/3_4_0007-unit-enters-the-employee-address.md`](../../adr/3_4_0007-unit-enters-the-employee-address.md)

### D4 — Duas permissões de staff em identity, e `hr` ≡ `manager` aqui

- **O quê:** `MANAGE_STAFF` e `MANAGE_JOB_FUNCTIONS`, ambas para `OWNER`,
  `MANAGER` e `HR`.
- **Por quê:** o sponsor reenquadrou o eixo da divergência de **alcance** para
  **família de operação**. Não se reusou `MANAGE_USERS`, que é sobre conta de
  login: soldá-la à gestão de equipe faria conceder uma implicar a outra, em
  silêncio.
- **Fonte:** decisão do sponsor, 2026-08-12; `workforce.md` §4; kickoff #10;
  `permission.py` ("as Stages/BCs seguintes estendem o vocabulário").
- **ADR:** [`../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md`](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md)

### D5 — Permissão tenant-wide dispensa a exigência de unidade

- **O quê:** `TENANT_WIDE_PERMISSIONS`, consultado pelo passo 4 do
  `AuthorizeActionUseCase`. Hoje, um membro.
- **Por quê:** a função é tenant-scoped por regra canônica, então o catálogo não
  tem unidade a declarar, e sem isto só `owner` o gerencia. Manter a função
  tenant-scoped e nomear a exceção numa permissão é a única saída que não mente
  sobre o modelo nem dissolve o eixo de unidade. Pôr `manager`/`hr` em
  `_UNIT_SCOPE_BYPASS_ROLES` daria alcance tenant-wide sobre **todas** as
  permissões, inclusive `MANAGE_STAFF`.
- **É o alicerce da issue #41**, que precisa de "gerir o catálogo" como
  capacidade de primeira classe para depois distinguir "minha unidade × todas".
- **Fonte:** decisão do sponsor, 2026-08-12; `authorize_action.py` passo 4;
  `user.py:45`; achados C1/S1 do Checkpoint A.
- **ADR:** [`../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md`](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md)

### D6 — O corte, e por que a fronteira caiu aqui

- **O quê:** a Stage entrega fundação e **nenhuma rota**; a borda é a 3.6.
- **Por quê:** com as decisões do sponsor incorporadas, o plano mediu 14 Tasks —
  o limiar de CONVENTIONS §6. A fronteira separa **emendar Stage fechada** de
  **escrever superfície nova**: tudo que toca 3.1, 3.2, 3.3 e identity fica de um
  lado; o adapter de entrada, do outro. O ganho decisivo é de sequência — os dois
  buracos de acesso fecham **antes** de existir rota que os exponha, e não há
  Stage intermediária publicando API furada.
- **Fonte:** CONVENTIONS §6; contagem em §13; aprovação do sponsor via sessão
  mestra, 2026-08-12.
- **Sem ADR:** decisão de processo (tamanho de Stage), não de arquitetura; o
  lugar canônico é a nota datada do roadmap, e é lá que está.

### D7 — Sem `gate_mode: batch`

O bloco declara `gate_mode: strict`. Esta Stage toca o guard fail-closed de
autorização, o vocabulário de permissões e assinaturas de port já mergeadas —
nada aqui é fundação validada.

## 8. Integrações

### Internas

- **`features/identity`** — o vocabulário de permissões e o passo 4 do guard são
  editados aqui; em runtime, alcançada **só** pelo tradutor no composition root.
- **`composition_root.py`** — monta o tradutor sobre o `IdentityGuard` já
  construído (mesmo objeto, não um segundo grafo).
- **`tests/contract/features/staff/`** — as suítes promovidas pela 3.3 ganham a
  lei de unidade e o caso do byte NUL, e continuam rodando nos dois lados.

### Externas

Nenhuma.

## 9. Modelo de dados

Não aplicável — esta Stage não cria nem altera tabela, coluna ou migration. O
schema é o da 3.3 (migration `0003_staff`); a lei de unidade é imposta na
consulta, não na estrutura.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Mexer no passo 4 do guard fail-closed afrouxar acesso além do pretendido | M | **A** | Dispensa por permissão, nunca por papel; CA6 fixa o conteúdo de `TENANT_WIDE_PERMISSIONS` e CA7 prova que `MANAGE_STAFF` não está nele |
| Emendar 3.2 e 3.3 quebrar suíte de contrato mergeada e o dano passar como "ajuste de assinatura" | A | **A** | Tasks separadas por camada (contrato antes de adapters), com a suíte rodando nos dois lados; CA9 falha enquanto o buraco de unidade existir |
| A fundação nascer sem consumidor e um defeito só aparecer na 3.6 | **A** | M | Declarado em §4; os CAs provam ligação (fake ≡ real, wiring montado), e a 3.6 é a Stage seguinte, não um horizonte distante |
| Mudança no domínio da 3.1 quebrar suíte mergeada sem que o desvio de camada seja notado | M | M | Task dedicada, expansão declarada em §1 e no ADR 3.4.0003 |
| Step 4 conceder à `hr` permissão de escala, dissolvendo a divergência | M | M | Restrição para frente em §5.2 **e** no ADR 3.4.0006 §3 |
| Regressão silenciosa em identity (a suíte de lá passa por acidente) | B | A | CA20 exige que a suíte de identity passe **sem alteração de asserção** |

### `[finding]` a escalar

- **`[finding]` — busca ampla de funcionário no restaurante inteiro**, com
  permissão própria (sponsor, 2026-08-12). **Não** pode ser obtida afrouxando a
  busca desta Stage. **Stage candidata:** issue **#41** ou a primeira Stage de
  frontend que precise do fluxo.
- **`[finding]` — leitura de funcionário por id** (`GET .../employees/{id}`) não
  existe: o mecanismo escolhido foi a assinatura, não o use case de leitura.
  **Stage candidata:** `3.6-staff-http` ou a primeira Stage de frontend.
- **`[finding]` — o byte NUL também escapa em identity.** `Restaurant`, `Unit` e
  `User` aceitam nome com `\x00`. Fora do BC desta Stage. **Stage candidata:**
  `6.x-hardening` ou a próxima Stage que toque `features/identity/domain`.
- **`[finding]` — identificador de path/query com NUL ou vazio** vira 500 dentro
  de identity (`units.find_by_id("\x00")`), e a correção de domínio de D2 não o
  alcança: identificador não passa por entidade (`identifiers.py` — "este módulo
  não tem lógica de runtime"). Precisa de validação **na borda**. **Stage
  candidata: `3.6-staff-http`**, que é onde nasce a borda.
- **`[finding]` — o texto de ADR 3.2.0002 §Neutral vira histórico**: a lacuna
  que ele registrou é fechada por mecanismo que ele não previu. Sem ação de
  código; a nota entra na reconciliação do roadmap. **Stage candidata:** esta.
- **`[finding]` — o tradutor do `AccessGuard` mora no composition root.** Quando
  a 3.5 trouxer o `IdentityGateway`, reavaliar mover os dois para
  `features/staff/adapters/out/identity/`. **Stage candidata:**
  `3.5-employee-login-link`.
- **`[finding]` — paginação e o antídoto da regex `_ORDER_BY`** (ADR 3.4.0004).
  **Stage candidata:** a primeira Stage que precise de listagem paginada.

## 11. Critérios de aceitação

### Permissões e autorização

- [ ] **CA1** — `MANAGE_STAFF` e `MANAGE_JOB_FUNCTIONS` existem em `Permission`
      e o mapa de papéis continua **total** (teste já existente da 2.1 passa).
- [ ] **CA2** — `owner`, `manager` e `hr` detêm **as duas**; `employee` e
      `platform_admin` **nenhuma**. Teste parametrizado sobre os cinco papéis.
- [ ] **CA3** — `hr` e `manager` têm conjuntos de permissão de staff
      **idênticos**; teste que falha se alguém os separar sem ADR (é a
      equivalência de §5.1, e é o que é verdade hoje).
- [ ] **CA4** — Ator unit-scoped exercendo `MANAGE_JOB_FUNCTIONS` **sem**
      declarar unidade é **autorizado**.
- [ ] **CA5** — Ator unit-scoped exercendo `MANAGE_STAFF` **sem** declarar
      unidade continua recebendo `UnitScopeRequiredError`.
- [ ] **CA6** — `TENANT_WIDE_PERMISSIONS` contém **exatamente**
      `{MANAGE_JOB_FUNCTIONS}`; teste com lista esperada explícita.
- [ ] **CA7** — `MANAGE_STAFF` **não** está em `TENANT_WIDE_PERMISSIONS`.
      *(Mata a mutação que daria alcance cross-unidade sobre registros.)*
- [ ] **CA8** — Os passos 3 e 5 do guard seguem inalterados: ator de outro
      tenant é negado, e unidade não visível é negada, também para permissão
      tenant-wide.

### Escopo de unidade

- [ ] **CA9** — Registro criado na unidade A **não é encontrado** com `unit_id`
      da B, em `find_by_id` e em `delete` — e o erro é `EmployeeNotFoundError`,
      nunca um que confirme a existência.
- [ ] **CA10** — A suíte de **contrato** prova CA9 nos **dois** lados (fake e
      Postgres) com um corpo de teste só.
- [ ] **CA11** — Os dez commands carregam `unit_id`, e os doze use cases o
      repassam ao port; teste que falha se algum voltar a resolver por
      `(tenant, id)`.

### Port `AccessGuard`

- [ ] **CA12** — Nenhum módulo em `features/staff/` importa `features.identity`
      nem nomeia `Role`/`Permission`; varredura + `lint-imports` verde.
- [ ] **CA13** — O contrato `bc-independence` continua **sem nenhum
      `ignore_imports`**; teste lê o `.importlinter` e falha se a lista existir.
- [ ] **CA14** — As leis L-AG1…L-AG4 são testadas contra uma **segunda
      implementação** (fake): exceção que sai crua, recusa de `tenant_id`
      ausente, uma autorização por alvo.
- [ ] **CA15** — O tradutor é montado no composition root sobre o **mesmo**
      `IdentityGuard` de identity, e o teste mecânico de composition root de
      staff continua verde.

### Domínio

- [ ] **CA16** — Nome contendo `\x00` é rejeitado com `InvalidNameError` em
      `Employee` e em `JobFunction`, em **todos** os caminhos de construção,
      inclusive a reidratação do mapper.
- [ ] **CA17** — A suíte de lei dos ports passa a exercitar o nome com NUL, e
      **fake e Postgres concordam** — a asserção que hoje reprovaria em
      `[postgres]` passa nos dois.
- [ ] **CA18** — Acentos, emoji com ZWJ, `\n`, aspas e 1000 caracteres
      **continuam aceitos** e fazem round-trip verbatim. *(Prova que a
      restrição é do tamanho da divergência, não maior.)*
- [ ] **CA19** — `DayPeriod.from_string("xpto")` levanta
      `InvalidDayPeriodError`, que é `StaffError`.

### Não-regressão

- [ ] **CA20** — A suíte de identity passa **sem alteração de asserção**. Se
      alguma precisar mudar, a mudança não foi aditiva — é achado, não ajuste.
- [ ] **CA21** — Nenhuma rota HTTP nasce nesta Stage: o repo continua sem
      `features/staff/adapters/in/`, e o router de identity é o único
      registrado.

### Gates

- [ ] **CA22** — `make check` verde (inclui `lint-imports`, `layout-check`,
      `docs-check`, mypy strict).
- [ ] **CA23** — Cobertura ≥ 90% em **cada** arquivo novo/tocado da Stage.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — sim (§4:
      `AccessGuard` com `Actor`, `AuthorizedScope` e as quatro leis; as duas
      permissões; `TENANT_WIDE_PERMISSIONS`).
- [x] Toda decisão em §7 tem fonte rastreável? — sim.
- [x] Toda integração externa tem contrato definido? — não há (§8).
- [x] Decisões com alternativa real descartada têm ADR escrito? — sim
      (3.4.0001, 0003, 0006, 0007, 0008 governam esta Stage; 0002, 0004 e 0005
      governam a 3.6 — §13).
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — sim.
- [x] **Stage cabe em ~3–12 Tasks? — sim, 6** (§13).
- [x] Riscos críticos têm mitigação plausível? — sim (§10).
- [x] A matriz papel × operação está fixada? — sim (§5.1, ADR 3.4.0006).
- [x] O escopo de unidade é enforçável por assinatura? — sim (§5.6,
      ADR 3.4.0007).
- [x] Recurso tenant-scoped é alcançável por papel unit-scoped? — sim (§5.4,
      ADR 3.4.0008).
- [x] A Stage entrega valor sozinha, sem a 3.6? — sim: fecha dois defeitos de
      acesso e uma divergência fake ≢ real, todos hoje presentes no código
      mergeado. Não entrega **funcionalidade de usuário**, e isso está declarado
      em §4 ("consumidor desta Stage").

## 13. Questões em aberto

**Nenhuma.** As três bifurcações foram decididas pelo sponsor em 2026-08-12
(ADRs 3.4.0006, 3.4.0007 e 3.4.0008) e o corte de tamanho foi aprovado.

### As 6 Tasks desta Stage

| # | Task | Camada |
|---|---|---|
| 1 | Permissões, `TENANT_WIDE_PERMISSIONS`, mapa de papéis e a condição do passo 4 | identity domain + application |
| 2 | Unidade no port `EmployeeRepository` + dez commands + fakes | staff application (3.2) |
| 3 | Os doze use cases reconciliados com a assinatura nova | staff application (3.2) |
| 4 | Adapters Postgres + suíte de contrato sob a lei de unidade | staff adapters/out (3.3) |
| 5 | Byte NUL, `DayPeriod.from_string`, `InvalidDayPeriodError` | staff domain (3.1) |
| 6 | Port `AccessGuard` + leis + fake + tradutor no composition root | staff application + composition root |

### Fronteira com a Stage 3.6

A **3.6-staff-http** recebe as 8 Tasks restantes do plano original: schemas,
handlers de erro e mapa de status, as 16 rotas, o wiring de `HttpWiring` em
coleções, e os e2e. O desenho já feito não se perde:

- **Três ADRs já `accepted` governam a 3.6**, e **não migram**: `context_stage`
  registra a Stage em que a decisão foi **tomada** (CONVENTIONS §2), e as três
  foram tomadas aqui.

  | ADR | O que decide | Governa |
  |---|---|---|
  | **3.4.0002** | handler único sobre `StaffError`, mapa total por MRO, par classe→status, `UnavailabilityNotFoundError` = 422 | 3.6 |
  | **3.4.0004** | sem paginação; `L-ORD` fica cursor preparado; antídoto da regex escalado junto | 3.6 |
  | **3.4.0005** | cópia repetida segue limite declarado; nem guarda nem campo informativo | 3.6 |

- **O inventário de rotas e de schemas** está no bloco 3.6 do `roadmap.md` em
  forma compacta, e o rascunho completo está no commit **`d878060`**
  (`docs/stages/3.4-staff-http/concept.md` §4.1–4.3), citado no bloco para que a
  Fase 3A da 3.6 não o re-derive.

- **Dois findings desta §10 são endereçados à 3.6**: o identificador de
  path/query com NUL, e a leitura de funcionário por id.

**A numeração 3.6 vindo depois da 3.5 é legal e intencional.** CONVENTIONS §1:
número é **identidade**, não posição — *"ordem de implementação = `depends_on`,
não o número"*. A 3.5 passa a depender da **3.6**, porque o vínculo de login
acrescenta rota ao router de staff, que só existe lá.

## 14. Referências

- [`../../overview.md`](../../overview.md) §3, §6, §9
- [`../../roadmap.md`](../../roadmap.md) — blocos Stage 3.4 (com a nota datada
  do corte), 3.5 e **3.6**
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) — §3.1,
  §3.2, §4
- [`../3.2-staff-application/concept.md`](../3.2-staff-application/concept.md)
  §4 (leis dos ports), §5.4, §6, §10
- [`../3.3-staff-persistence/technical.md`](../3.3-staff-persistence/technical.md)
  §7 (byte NUL, regex `_ORDER_BY`)
- [`../2.4-identity-http/concept.md`](../2.4-identity-http/concept.md) — a Stage
  que construiu o guard que esta estende
- ADRs consumidos: 2.1.0001, 2.2.0002, 2.3.0001, 2.3.0003, 2.3.0005, 2.4.0001,
  **2.4.0003**, 3.1.0001, 3.1.0002, 3.1.0006, **3.2.0002** (§Neutral),
  3.2.0003, 3.2.0006, 3.2.0007, 3.3.0002, 3.3.0003, 3.3.0004, 3.3.0006,
  **3.3.0007**
- ADRs desta Stage: 3.4.0001, 3.4.0003, 3.4.0006, 3.4.0007, 3.4.0008 —
  mais 3.4.0002, 3.4.0004 e 3.4.0005, decididos aqui e **executados na 3.6**
- **Issue #40** (esta Stage) e **issue #41** (habilitação de função por unidade)
- Skills: `hex-arch-python`, `composition-root`, `repository-pattern`,
  `pytest-with-fakes`, `import-linter-rules`

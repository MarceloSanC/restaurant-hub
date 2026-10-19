---
title: Concept — Autorização na camada application de staff
description: Todo use case de staff passa a autorizar, pelo AccessGuard injetado, o alvo do próprio command antes de qualquer outra instrução — a application deixa de depender da borda HTTP para negar, e a borda vira defesa em profundidade
when-use: Consultar ao iniciar a Fase 3B desta Stage; revisar antes de executar, e antes de acrescentar use case ou command em staff
keywords: [concept, application-authorization, staff, access-guard, fail-closed, defense-in-depth, use-case]
status: done
created_at: 2026-10-19
updated_at: 2026-10-19
stage_id: 3.7-application-authorization
stage_title: Autorização na camada application de staff
step_id: 3
step_title: Equipe da unidade
depends_on: [3.5-employee-login-link]
---

# Concept — Stage 3.7 — Autorização na camada application de staff

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Origem.** Issue [#49](https://github.com/MarceloSanC/restaurant-hub/issues/49),
> promovida a Stage em 2026-10-19 pelo litmus de [`PIPELINE.md`](../../PIPELINE.md)
> §4.5: o corpo pedia um ADR (a forma), tocava os 17 use cases e exigia uma
> propriedade sobre a camada inteira — o corpo pedia um concept.

## 1. Escopo

### Dentro do escopo
- Os **17** use cases de `features/staff/application/use_cases/` recebem o port
  `AccessGuard` por construtor e autorizam, **antes de qualquer outra
  instrução** de `execute`, o alvo que o próprio command declara.
- Todo command e query de staff ganha o campo `actor` (credencial opaca,
  `Actor = object`), primeiro campo, sem default, fora do `repr`.
- O vocabulário de permissão (`PERMISSION_MANAGE_STAFF`,
  `PERMISSION_MANAGE_JOB_FUNCTIONS`, `PERMISSION_MANAGE_USERS`) migra de
  `adapters/inbound/http/dependencies.py` para o módulo do port
  (`application/ports/out/access_guard.py`); a borda passa a importá-lo de lá.
- Os dois consumidores se ajustam: `composition_root.py` injeta o **mesmo**
  `staff_access_guard` em cada use case; `router.py` passa `actor=actor` em cada
  command e **continua** autorizando como hoje.
- Os testes unitários de borda (`tests/unit/features/staff/adapters/`) montam os
  use cases por reflexão do construtor: passam a injetar o **mesmo**
  `InMemoryAccessGuard` do ambiente, e as asserções de sequência exata de
  chamadas ao guard passam a incluir as chamadas do use case. **`tests/e2e/` não
  muda** (CA09).
- Dois dublês de teste novos (guard que sempre nega; guard que concede, registra
  e devolve escopo **infiel**) e as suítes de propriedade, estrutural e de cadeia
  real (§11).
- Documentação que esta decisão torna falsa ou incompleta: docstrings de staff
  que dizem "o use case não autoriza / a borda autoriza"; seção *append-only*
  `## Supersessão parcial` nos ADRs 3.2.0002, 3.4.0001 e 3.6.0004; errata datada
  na tabela de precedência do concept 3.2 §5.16.

### Fora do escopo (explicitamente)
- **Remover o guard da borda HTTP** — ele continua, agora como defesa em
  profundidade (não-objetivo da #49).
- **Mudar as quatro leis do port** (L-AG1..L-AG4), o vocabulário `str` da
  permissão ou a matriz de papéis (não-objetivo da #49).
- **Estender o `AccessGuard` a identity** — `AuthorizeActionUseCase` e a fachada
  de identity são outro caso (não-objetivo da #49; ADR 3.5.0001 §1 segue
  verdadeiro do lado de identity).
- **Mover o tradutor de acesso** `_IdentityAccessGuard` para fora do
  `composition_root` — issue #47.
- **Autenticação independente de driver**, ator de sistema, verificação de que o
  ator foi emitido por `authenticate` e validação de identificador na
  application: nenhum driver não-HTTP existe hoje; ficam como `[finding]` (§13).
- Qualquer mudança de status HTTP, de corpo de erro ou de rota.

### Vínculo com o roadmap
Step 3 — Equipe da unidade. A Stage fecha o débito que o ADR 3.4.0001 §4 deixou
declarado (*"LAYOUT §5 … ainda não é literalmente verdade aqui"*) — para
`authorize` — e o que a #49 mediu: o isolamento de tenant de staff era disciplina
do adapter HTTP. Bloco em [`roadmap.md`](../../roadmap.md) §Stage 3.7.

## 2. Objetivo da Stage

Ao fechar, **nenhum use case de staff produz efeito algum sem que o
`AccessGuard` tenha autorizado, para o alvo que o seu command declara, o ator que
o command carrega** — propriedade provada sobre a pasta `use_cases/` inteira,
pela forma de cada `execute` e pela cadeia real de identity, com as faixas de
erro HTTP byte-idênticas às de hoje.

## 3. Contexto e premissas

### Contexto
- **O port já existe e já carrega as leis** (Stage 3.4, ADR 3.4.0001): staff
  declara `AccessGuard.authenticate/authorize` no seu vocabulário; o tradutor de
  produção mora no `composition_root` (`_IdentityAccessGuard`) e delega ao
  `IdentityGuard`, que monta o command de `AuthorizeActionUseCase`.
- **O único consumidor do port é o router** (Stage 3.6): cada handler autentica
  (`Depends`), valida identificadores, chama `guard.authorize(...)` e só então o
  use case, tirando o `tenant_id` do `AuthorizedScope` devolvido (ADR 0.0.0005).
  `grep -rln "AccessGuard" src/restaurant_hub/features/staff/application/use_cases`
  hoje: vazio.
- **A unidade do registro vem do path**, nunca do escopo (ADR 3.6.0001); o
  escopo apenas ecoa a unidade pedida (`authorize_action.py:113`).
- **Medido: com `tenant_id` nomeado, ator de outro tenant é negado** — pela
  primeira checagem que se aplica a ele: passo 2 (RBAC, `PermissionDeniedError`
  — `employee` e `platform_admin` param aqui para as permissões de staff,
  `role.py:54,77`), passo 3 (`_assert_tenant_scope`, `TenantNotVisibleError` —
  `owner`/`manager`/`hr` de outro tenant, `authorize_action.py:116-128`) e, para
  ator sem tenant que passasse, L-AG3 no tradutor (`composition_root.py:356-363`).
  É isso que permite ao use case **confirmar** o tenant do command em vez de
  derivá-lo.
- **Medido: as duas autorizações (borda e use case) recebem o mesmo pedido** no
  caminho HTTP — a borda omite o tenant e o tradutor o resolve do ator
  (`composition_root.py:347`); o use case nomeia o tenant do escopo devolvido,
  que é o mesmo valor. Toda negação acontece na borda antes; nenhuma faixa muda.

### Premissas
- Um request HTTP de staff passa a custar duas autorizações; cada uma é
  `users.find_by_id` e, quando há unidade, `units.find_by_id` mais
  `users.list_memberships` (`authorize_action.py:80,142,153`) — leituras por
  chave. Aceitável na escala do piloto (overview §6); não medido sob carga.
- Nenhum driver não-HTTP de staff existe hoje (`grep -rn "UseCase(" src/` fora do
  `composition_root`: vazio).

### Dependências
- `3.4-staff-access-scope`: `AccessGuard`, `AuthorizedScope`, leis L-AG1..L-AG4,
  `InMemoryAccessGuard` e a suíte `test_access_guard_laws.py`.
- `3.6-staff-http`: router, `AccessRequirement`, as varreduras de borda (19
  autorizações, CA21 da ordem validar→autorizar), o `AdversarialAccessGuard` e a
  matriz e2e de autorização.
- `3.5-employee-login-link`: o 17º use case (`create_login_for_employee`) e o
  `IdentityGateway`, efeito do outro lado da fronteira.

## 4. Contratos

### Introduzidos
- **Campo `actor`** (`dto`) em todo command e query de staff
  (`application/dtos/commands.py`, `queries.py` — 17 DTOs):
  ```python
  @dataclass(frozen=True)
  class ListEmployeesQuery:
      actor: Actor = field(repr=False)   # primeiro campo, sem default
      tenant_id: TenantId
      unit_id: UnitId
      include_inactive: bool = False
  ```
- **Parâmetro `guard: AccessGuard`** no construtor de cada um dos 17 use cases
  (port primário = a própria classe, ADR 0.0.0006 — `execute(<Command>)` não muda
  de forma).
- **Vocabulário de permissão no módulo do port** (`port-out`):
  `PERMISSION_MANAGE_STAFF = "manage_staff"`,
  `PERMISSION_MANAGE_JOB_FUNCTIONS = "manage_job_functions"`,
  `PERMISSION_MANAGE_USERS = "manage_users"` — `Final`, valores, jamais enum de
  identity; nomes inalterados.

### Consumidos
- **`AccessGuard.authorize`** com as leis L-AG1..L-AG4 — Stage 3.4. Esta Stage
  **não** muda o port além de acolher o vocabulário.
- **ADR 0.0.0005** — cláusula 1 (tenant da requisição é declaração confirmada),
  agora também na application.
- **`IdentityGateway`** (3.5) e **`EmployeeRepository`/`JobFunctionRepository`**
  (3.2–3.4) — inalterados; passam a ser alcançados **só depois** da autorização.

## 5. Invariantes e regras

**R1 — Todo use case autoriza.** Os 17, sem exceção. A incerteza da #49 ("todos
ou só os que atravessam tenant/unidade?") resolve em *todos*: todo command de
staff carrega `tenant_id`, logo todo use case atravessa a linha de tenant; o
ônus de justificar exceção por escrito (posto pela #49) não é cumprido por
nenhum.

**R2 — A autorização precede toda outra instrução de `execute`.** O corpo de
`execute` começa pelo bloco de autorização — uma chamada por alvo — sem nenhum
comando, condição ou checagem antes dele. Nenhuma porta (leitura de repositório,
gerador de id, gateway) e nenhuma checagem pura: quem é negado não aprende nada,
nem sobre os dados nem sobre a forma do pedido. Use case de **dois alvos**
autoriza os dois antes da primeira porta. A ordem das checagens de negócio entre
si (concept 3.2 §5.16, ADR 3.6.0004) vale **depois** do bloco, inalterada
(errata datada no 3.2 §5.16).

**R3 — O alvo autorizado é o alvo do command, por inteiro.** O use case passa ao
guard o `actor` do command (ou query) que recebeu, uma constante `PERMISSION_*`
do port, o `tenant_id` do command **nomeado** e, quando o command endereça
unidade, o `unit_id` do command.
O tenant é **confirmado**, não derivado (ADR 0.0.0005 cláusula 1). Matriz
(idêntica à que a borda declara em `dependencies.py`):

| Use case | Permissão | `tenant_id` | `unit_id` |
|---|---|---|---|
| `create_job_function`, `list_job_functions`, `rename_job_function`, `delete_job_function` | `manage_job_functions` | do command | — (tenant-wide, ADR 3.4.0008) |
| `create_employee`, `list_employees`, `rename_employee`, `delete_employee`, `assign_job_functions`, `change_workload_profile`, `declare_shift_preference`, `register_unavailability`, `remove_unavailability`, `deactivate_employee`, `reactivate_employee` | `manage_staff` | do command | do command |
| `copy_employee_to_unit` | `manage_staff` ×2 | do command | `unit_id` (origem), **depois** `target_unit_id` (destino) — L-AG4 |
| `create_login_for_employee` | `manage_staff`, **depois** `manage_users` | do command | do command |

**R4 — O `AuthorizedScope` devolvido não é lido pela application** — nem o
tenant, nem a unidade. O guard confirma; não fornece endereço. É o gêmeo, na
application, do ADR 3.6.0001 — uma fonte de endereço (o command), uma autoridade
(o guard).

**R5 — As exceções do guard sobem cruas.** O use case não captura nem traduz o
que `authorize` levanta (L-AG2): a faixa 403 continua sendo a de identity.

**R6 — Sem ator, sem pedido.** `actor` é campo obrigatório, primeiro, sem
default: quem não o informa não forma o command. `repr=False`, porque staff não
sabe o que a credencial opaca imprime e o command alcança traceback e log.
**Limite declarado:** `Actor = object`, então `actor=None` constrói — e é o
guard quem o recusa (§6).

**R7 — A borda continua igual.** O router mantém as 19 chamadas a `authorize`,
a ordem autenticar → validar → autorizar, e tira o `tenant_id` do command do
`AuthorizedScope` (único lugar onde o tenant do token chega à borda).

**Modelo de ameaça (ADR 3.7.0001 §Threat model).** R1–R6 garantem que nenhum
use case produz efeito sem que o guard autorize **o ator que recebeu**. Não
garantem que o ator seja **autêntico**: isso é de `authenticate`, chamado pelo
driver. A cadeia de produção (tradutor → `IdentityGuard.authorize`, que lê
`actor.claims.subject`) não verifica que o ator veio de `authenticate`
(o fake verifica); um driver em processo que forje um `AuthenticatedActor`
passaria. Inalcançável hoje — o router é a única fonte de ator — e registrado
como `[finding]` para a Stage que criar o primeiro driver não-HTTP.

## 6. Casos de erro e exceções

| Situação | Comportamento |
|---|---|
| Guard nega o (primeiro) alvo | a exceção do guard sobe **crua** (R5); nenhuma chamada a repositório, gateway ou gerador de id |
| Guard nega o **segundo** alvo (cópia: destino; login: `manage_users`) | idem — nenhum efeito, porque os dois alvos são autorizados antes da primeira porta (R2) |
| Command com `tenant_id` de outro tenant que o do ator (produção) | negado na primeira checagem aplicável: `PermissionDeniedError` (`employee`, `platform_admin`), `TenantNotVisibleError` (`owner`/`manager`/`hr`); nenhum efeito |
| Guard que devolve escopo com tenant **e** unidade divergentes dos pedidos | o use case opera sobre o tenant e a unidade do **command** (R4) |
| Construir command sem `actor` | `TypeError` na construção (campo sem default) |
| `actor=None` ou objeto que não é ator (driver não-HTTP) | recusado pelo guard: no fake, a sentinela de L-AG2; em produção, `AttributeError` cru do `IdentityGuard` (adapter de entrada de identity, que lê `actor.claims.subject`) — fail-closed, mas não tipado (finding) |
| Identificador cru (`"\x00"`) vindo de driver não-HTTP | a application não valida identificador (ADR 3.6.0002 é da borda); o `unit_id` chega a `units.find_by_id` em identity → `DataError` — fail-closed, não tipado (finding) |
| Via HTTP, qualquer caso acima | **status e corpo inalterados**: a borda valida e autoriza o mesmo alvo antes, então toda recusa acontece nela antes de alcançar o use case |

Nenhuma exceção nova; nenhum handler novo; `STAFF_ERROR_STATUS` inalterado.

## 7. Decisões técnicas relevantes

> Triagem pela skill `evidence-resolution`: os forks desta Stage são de
> **convenção** (C) ou **evidência interna** (E). Nenhum é de preferência de
> produto (P) — o comportamento visível ao usuário do piloto não muda (§6, última
> linha). Por isso a Fase 3A não fez pergunta ao sponsor.

### D1 — Guard injetado por construtor em cada use case
```
[decision:C] D1 — guard por construtor × decorator/serviço de aplicação
Escolha: construtor · Alternativas: wrapper autorizador por use case; wrapper genérico com tabela · Degrau (C): 1 e 2
Base: #49 §Critério de pronto "Todo use case de escrita e leitura escopada recebe o guard por construtor"; fail-closed — o use case cru não existe sem guard
Configuração candidata: nenhuma · Reversível: sim (forma interna da application)
```
- **ADR:** [`3.7.0001`](../../adr/3_7_0001-every-staff-use-case-authorizes-its-own-target.md) §1, alt. A.

### D2 — O ator viaja dentro do command
```
[decision:C] D2 — ator no command × segundo parâmetro de execute
Escolha: campo `actor` no command · Alternativas: execute(command, actor) · Degrau (C): 1
Base: LAYOUT §5 "o port primário … é a própria classe de use case, com o seu `execute(<Command>) -> <Result>`"; ADR 0.0.0006 §Decision
Configuração candidata: nenhuma · Reversível: sim
```
- **ADR:** 3.7.0001 §2, alt. B. Supera em parte o ADR 3.2.0002 (Context: *"its
  use cases deliberately take no actor"*) — nota datada lá.

### D3 — Tenant confirmado, não derivado; `AuthorizedScope` não lido
```
[decision:C] D3 — tenant do command confirmado pelo guard × tenant derivado do escopo
Escolha: nomear `tenant_id=command.tenant_id` e operar sobre o command · Alternativas: tirar tenant_id dos commands e ler scope.tenant_id; omitir o tenant como a borda faz · Degrau (C): 1
Base: ADR 0.0.0005 cl. 1 "a declaration confirmed against the token"; ADR 3.2.0002 (commands escopados); ADR 3.6.0001 (endereço ≠ escopo); medição authorize_action.py:85-86,116-128
Configuração candidata: nenhuma · Reversível: sim
```
- **ADR:** 3.7.0001 §3, alts. C e G. A alt. G responde às razões com que o ADR
  0.0.0005 rejeitou nomear o tenant (alts. B e C de lá): elas eram sobre a
  borda HTTP; na application o tenant do command **é** entrada de todo driver
  não-HTTP, e confirmá-lo é a única checagem que esse driver encontra.

### D4 — Autorizar antes de toda outra instrução; todos os alvos antes da primeira porta
- **O quê:** R2.
- **Por quê:** "não produz efeito" (#49) só é propriedade se nada acontece antes
  da decisão; ler antes abriria oráculo de existência, validar antes abriria
  oráculo de forma. A ordem que o ADR 3.6.0004 fixa ordena checagens de negócio
  entre si, e vale depois do bloco de autorização.
- **Fonte:** #49 §Critério de pronto ("levanta e não produz efeito"); degrau 2
  (fail-closed).
- **ADR:** 3.7.0001 §4.

### D5 — Vocabulário de permissão no módulo do port
- **O quê:** as três constantes `PERMISSION_*` migram para `access_guard.py`, com
  os mesmos nomes; `dependencies.py` as importa (o nome continua disponível no
  módulo da borda, de onde os testes de borda o leem).
- **Por quê:** o use case precisa dos valores, e application não importa adapter
  (LAYOUT §3). O docstring do port já cita os valores.
- **Fonte:** LAYOUT §3; `dependencies.py:92-98`.
- **ADR:** 3.7.0001 §5.

### D6 — A borda continua autorizando
- **O quê:** R7; nenhum handler muda além de passar `actor=actor`.
- **Fonte:** #49 §Não-objetivos.
- **ADR:** 3.7.0001 §6, alt. E.

### D7 — Dublês: um que sempre nega, um que concede e devolve escopo infiel
- **O quê:**
  - `DenyingAccessGuard` — levanta **a mesma instância** sentinela a cada
    `authorize` e registra o pedido.
  - `PermissiveAccessGuard` — concede todo pedido que **nomeia** o tenant
    (tenant `None` é recusado: a application sempre nomeia, R3), registra o
    pedido como `(permission, tenant_id, unit_id)` e devolve um escopo
    **deliberadamente infiel** — tenant e unidade que não existem em nenhum
    teste. Usado em toda a suíte de regras de negócio dos use cases, ele faz
    qualquer leitura do escopo (R4) desviar a escrita para um endereço
    inexistente e reprovar o teste que relê pelo port.
  - O `InMemoryAccessGuard` da 3.4 continua sendo a **segunda implementação das
    leis**; os dois novos são dublês **declarados infiéis** (precedente: o
    `AdversarialAccessGuard` da 3.6) e não entram na suíte de lei — o texto do
    port *"um fake que não resolva o tenant do ator não cumpre este port"* vale
    para implementações, e nenhum dos dois se apresenta como uma.
- **Por quê:** os ≈200 testes de regra de negócio dos use cases testam regra de
  negócio, não acesso; a propriedade de acesso vive em suítes próprias (CA03–CA08,
  CA14–CA15).
- **Fonte:** skill `pytest-with-fakes` (fake por port de saída; contrato só para
  implementações do port).

## 8. Integrações

### Internas
- **`composition_root.py`**: passa `guard=staff_access_guard` aos 17 use cases —
  a **mesma** instância que as rotas recebem.
- **`adapters/inbound/http/router.py`**: cada handler acrescenta `actor=actor` ao
  command; o resto do handler não muda.
- **identity** (via `_IdentityAccessGuard`): recebe agora chamadas com `tenant_id`
  nomeado — caminho já coberto pela suíte do tradutor (eixo nomeado × omitido do
  ADR 0.0.0005) e, nesta Stage, pela cadeia real (CA14).

### Externas
- Nenhuma.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| A propriedade trava 17 representantes e um use case novo entra sem guard | M | A | CA04 (lista da suíte = pasta) e CA01/CA15 (derivados da pasta) |
| Autorização condicional ou depois de checagem pura passa pelo representante | M | A | CA15 — forma de todo `execute` por AST, não por representante |
| Use case autoriza o alvo **errado** ou com a permissão errada | M | A | CA05 trava a sequência exata; CA15 exige constante `PERMISSION_*` |
| Guard que não confirma o tenant nomeado deixaria passar command de outro tenant | M | A | CA14 — cadeia real de identity, todo papel × todo use case |
| Use case lê o escopo em vez do command | B | A | CA07 — escopo infiel em tenant **e** unidade, na suíte inteira |
| A faixa HTTP muda sem ninguém perceber | B | A | CA09: `tests/e2e/` inalterado e verde |
| Credencial do ator vaza em log/traceback pelo `repr` do command | B | M | R6 (`repr=False`) + CA02 |
| Custo de 2 autorizações por request | A | B | aceito e declarado (ADR 3.7.0001 §Consequences) |
| Ator forjado ou cru vindo de driver não-HTTP | B (hoje inalcançável) | A | modelo de ameaça escrito; finding com Stage candidata |

## 11. Critérios de aceitação

- [ ] **CA01** — Todo use case da pasta `use_cases/` (derivado, não listado) tem
      no construtor um parâmetro `guard` anotado `AccessGuard`.
- [ ] **CA02** — Todo command e query de staff tem `actor` como **primeiro**
      campo, sem default e com `repr=False`; o `repr` de um command não contém o
      `repr` do ator.
- [ ] **CA03** — Com um guard que **sempre nega**, cada um dos 17 use cases,
      chamado com um command válido sobre dados semeados, levanta **a própria
      instância** sentinela do guard (`is`) e, **medido a partir do instante
      depois da semeadura**, não acrescenta nenhuma entrada ao registro de
      chamadas do store de repositórios nem ao do gateway, e não consome nenhum id
      do gerador.
- [ ] **CA04** — A lista de use cases da suíte de CA03 é igual ao conjunto de
      módulos da pasta `use_cases/` (sem `_`-prefixados): use case novo entra
      coberto ou reprova.
- [ ] **CA05** — Para cada use case, num caminho feliz com o guard que concede e
      registra, a sequência de `authorize` é **exatamente** a da matriz R3
      (permissão, `tenant_id` do command, `unit_id` do command; cópia: origem e
      depois destino; login: `manage_staff` e depois `manage_users`).
- [ ] **CA06** — Nos dois use cases de dois alvos, negar **só o segundo** alvo
      produz a exceção do guard e nenhum efeito (mesma medição de CA03).
- [ ] **CA07** — Com o guard que devolve escopo infiel (tenant e unidade
      divergentes), cada use case que escreve ou devolve registro opera sobre o
      tenant e a unidade do **command**: o result e a releitura pelo port carregam
      os do command.
- [ ] **CA08** — No grafo real (`wire_dependencies`), os 17 use cases recebem a
      **mesma** instância `deps.staff_access_guard` (identidade de objeto).
- [ ] **CA09** — Faixas HTTP inalteradas: `git diff origin/develop -- tests/e2e`
      vazio e a suíte e2e verde em `make check`.
- [ ] **CA10** — A borda continua autorizando: a varredura de 19 autorizações do
      router (`test_http_boundary_sweeps.py`) passa sem mudar a cardinalidade.
- [ ] **CA11** — Os valores `"manage_staff"`, `"manage_job_functions"` e
      `"manage_users"` são **atribuídos** em `src/restaurant_hub/features/staff/`
      só em `application/ports/out/access_guard.py`
      (`grep -rnE '= "manage_' src/restaurant_hub/features/staff` devolve só esse
      arquivo), e nenhuma chamada a `authorize` em `application/use_cases/`
      recebe a permissão como literal `str` (verificado pelo AST de CA15;
      docstrings e comentários não contam).
- [ ] **CA12** — As frases que esta Stage torna falsas deixam de existir:
      `create_login_for_employee.py` *"não autoriza (a rota autoriza, duas
      vezes)"*; `identity_gateway.py` *"Quem responde pela autorização do ato é a
      borda"*; `local_identity_gateway.py` *"Quem responde pela autorização é a
      rota R17"*; e o §"Onde este port mora" de `access_guard.py` diz que
      `authorize` é consumido pelos use cases e `authenticate` segue só na borda.
      As menções a *"a fachada de identity não autoriza (#49)"* continuam — são
      verdade do lado de identity.
- [ ] **CA13** — `make check` verde; cobertura ≥ 90% por arquivo de `src/`
      tocado.
- [ ] **CA14** — **Cadeia real:** com o `_IdentityAccessGuard` de produção sobre
      `IdentityGuard` → `AuthorizeActionUseCase` e repositórios de identity em
      memória, para **todo** use case × **todo** papel (`owner`, `manager`, `hr`,
      `employee` do tenant A; `platform_admin`), um command que nomeia o tenant B
      (com registros semeados em B) é negado com a exceção de identity e nenhum
      efeito; controle positivo: o `owner` de B executa o mesmo command.
- [ ] **CA15** — **Forma de todo `execute`**, por AST sobre a pasta: ignorado o
      docstring inicial, as primeiras instruções são exatamente as chamadas
      `self._guard.authorize(<p>.actor, PERMISSION_<…>, tenant_id=<p>.tenant_id[, unit_id=<p>.<campo de unidade>])`
      da matriz R3 — `<p>` é o primeiro parâmetro de `execute` (`command` ou
      `query`) —, sem instrução, condição ou atribuição antes delas, e não há
      outra chamada a `authorize` no corpo.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido? (não há)
- [x] Decisões com alternativa real descartada têm ADR escrito? (3.7.0001)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.4, 3.5, 3.6)
- [x] Stage cabe em ~3–12 Tasks? (7 previstas)
- [x] Riscos críticos têm mitigação plausível?
- [x] Nenhum critério depende de mudar status HTTP, lei do port ou identity?

## 13. Questões em aberto

Nenhuma bloqueante. Ficam como `[finding]` na §7 do technical, com Stage
candidata:

- **Autenticidade do ator fora da borda HTTP** — ator de sistema/delegado,
  `authenticate` independente de driver (hoje recebe a requisição HTTP e tem só a
  borda como consumidor) e o tradutor de produção honrando "ator que este guard
  não emitiu é negado". Candidata: a primeira Stage que criar worker/CLI sobre
  staff (Step 4/5).
- **Validação de identificador na application** para drivers não-HTTP (ADR
  3.6.0002 vale só na borda). Mesma candidata.
- **staff como provedor de scheduling** — o domínio de scheduling lê staff por um
  port de leitura (`docs/domain/scheduling/shift-scheduling.md`) com adapter
  local nas Stages 4.3/4.4. Se a leitura passar pelos use cases de staff, o
  consumidor precisa de um ator; se passar por uma fachada de leitura, decidir lá
  quem autoriza (o padrão 3.5.0001 diz "o chamador"). Candidata: 4.3.
- **A mesma pergunta em scheduling** — a 4.3 (`scheduling-application`) nasce com
  use cases; decidir lá se adota o padrão do ADR 3.7.0001 desde o primeiro commit.
- **Ponteiros `(#49)` em identity** (`facade.py` §3, ADR 3.5.0001 §1) continuam
  verdadeiros do lado de identity, mas apontam para uma issue que deixou identity
  fora de escopo. Candidata: a próxima Stage que tocar a fachada.

## 14. Referências

- [`../../roadmap.md`](../../roadmap.md) — Stage `3.7-application-authorization`
- Issue [#49](https://github.com/MarceloSanC/restaurant-hub/issues/49)
- ADR desta Stage: [`3.7.0001`](../../adr/3_7_0001-every-staff-use-case-authorizes-its-own-target.md)
- ADRs consumidos: 0.0.0005, 0.0.0006, 2.4.0003, 3.2.0002, 3.4.0001, 3.4.0008,
  3.5.0001, 3.6.0001, 3.6.0002, 3.6.0004
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §5
- Concepts: [`3.2`](../3.2-staff-application/concept.md) §5.16,
  [`3.4`](../3.4-staff-access-scope/concept.md),
  [`3.6`](../3.6-staff-http/concept.md),
  [`3.5`](../3.5-employee-login-link/concept.md)

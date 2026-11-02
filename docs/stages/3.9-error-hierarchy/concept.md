---
title: Concept — Hierarquia de exceções sem protocolo HTTP
description: Tirar o HTTP da hierarquia de exceções — uma raiz por significado, status só pelo mapa do adapter, ApplicationError de volta, detector de protocolo nos módulos de erro
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar; referência ao criar erro novo em qualquer BC
keywords: [concept, error-hierarchy, domain-error, application-error, not-found, mro, status-map, handler, dependency-rule]
status: done
created_at: 2026-11-02
updated_at: 2026-11-02
stage_id: 3.9-error-hierarchy
stage_title: Hierarquia de exceções sem protocolo HTTP
step_id: 3
step_title: Equipe da unidade
depends_on: [3.6-staff-http, 4.3-scheduling-application]
---

# Concept — Stage 3.9 — Hierarquia de exceções sem protocolo HTTP

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo
- `ApplicationError` recriada em `shared/application/errors.py`, com uma raiz de aplicação por
  BC (`IdentityApplicationError`, `StaffApplicationError`, `SchedulingApplicationError`).
- Reclassificação, pelo critério do ADR 3.9.0001 §3, dos erros de `application/errors.py` dos
  **três** BCs (identity, staff, scheduling): os que não nomeiam regra de negócio mudam de raiz
  (tabela em §4).
- Fim da herança dupla `(<BC>Error, NotFoundError)` — oito classes — e remoção de
  `NotFoundError` e do handler genérico 404 de `shared/infrastructure/http/error_handlers.py`.
- Handlers de identity e staff registrados sobre as **duas** raízes do BC, com o mapa
  exaustivo chaveado pelas duas; corpo, cabeçalho, faixa e linha de log idênticos.
- Gate 3 (`tests/unit/test_status_map.py`) generalizado para "raízes do BC" e acrescido de
  duas propriedades: nenhuma classe com duas raízes; toda raiz de BC com borda HTTP tem handler.
- Detector de protocolo: regra nova em `scripts/check_layout.py` sobre os módulos que definem a
  hierarquia, e reescrita das docstrings/comentários que hoje a violam.
- Docstrings de registro em `shared/infrastructure/http/app.py` que citam `NotFoundError` e a
  ordem das MROs (ficariam falsas).
- Supersessão do ADR 2.2.0003; supersessão parcial datada nos ADRs 2.3.0003, 2.4.0001 e
  3.4.0002; `docs/LAYOUT.md` §2–§4 atualizado (inclusive a lista "Pode importar de" da camada
  Application em §3).

### Fora do escopo (explicitamente)
- Mudar status, corpo, cabeçalho ou log de qualquer resposta (issue #48, Não-objetivos).
- As conversões do guard que fecham oráculo de enumeração (ADR 2.4.0001 §5) — o guard continua
  convertendo `UserNotFoundError` → 401 e `UnitNotFoundError` → 403, sem alteração.
- Mapa de status e borda HTTP de scheduling (Stage 4.5): scheduling ganha a raiz de aplicação,
  não handler.
- Vocabulário de protocolo fora dos módulos de erro (ex.: o comentário de
  `identity/domain/value_objects/email.py` que cita um 500 histórico) — a regra mira a
  hierarquia de exceções, que é o objeto da issue (decisão D6).
- Docs históricos (concepts/technicals de Stages fechadas) que citam `NotFoundError` ou a regra
  antiga: são registro do tempo deles.

### Vínculo com o roadmap
Stage promovida da issue #48 (`roadmap.md` §Stage 3.9 › "Descrição humana"). Contribui para o
Step 3 pela via transversal: a hierarquia de erro que staff, identity e scheduling compartilham
passa a respeitar a Dependency Rule de LAYOUT §3, antes de a Stage 4.5 escrever o terceiro mapa
de status sobre ela.

## 2. Objetivo da Stage

Ao fechar, toda classe de erro do sistema tem **exatamente uma** raiz escolhida pelo que ela
significa (regra de negócio → `DomainError`; falha de atendimento que não é regra →
`ApplicationError`), o status HTTP sai **só** do mapa do adapter de cada BC, e nenhum módulo da
hierarquia menciona protocolo — com as respostas da API byte-idênticas às de antes.

## 3. Contexto e premissas

### Contexto
- ADR 2.2.0003 (Stage 2.2) pôs todo erro de aplicação de identity sob `IdentityError` porque
  `ApplicationError` não tinha handler, e ordenou `(IdentityError, NotFoundError)` para o lookup
  do Starlette alcançar o 404 antes do 422. Staff (3.2) e scheduling (4.3) copiaram o arranjo.
- ADR 2.4.0001 e 3.4.0002 passaram o status para um **mapa explícito por BC**, resolvido por um
  handler único registrado na raiz do BC; a #45 (Gate 3) tornou a totalidade do mapa um teste em
  todos os BCs. Desde então a ordem das bases não decide status algum: o handler do BC vence o
  lookup e lê o mapa.
- A #45 (Gate 7) removeu `ApplicationError` (sem consumidor) e criou `check_dead_shared.py`.
- A #26 fez o handler de identity logar a causa suprimida dos 401/403 — a linha usa o nome
  **curto** da classe para erros do BC (`_nome_da_classe`), e o qualificado para os de fora.

### Premissas
- O lookup de handler do Starlette na versão travada percorre `type(exc).__mro__` e usa o
  primeiro tipo registrado — fato já assumido e testado pelos ADRs 2.4.0001/3.4.0002 e pelos
  e2e de faixa; esta Stage depende dele só para afirmar que registrar o handler nas duas raízes
  alcança toda subclasse.
- Nenhum código de `src/` captura uma raiz de BC (`except IdentityError` etc.) — medido por
  grep em 2026-11-02: só os handlers a referenciam.

### Dependências
- `3.6-staff-http`: mapa e handler de staff (ADR 3.4.0002), discriminador `"staff_error"`.
- `4.3-scheduling-application`: `features/scheduling/application/errors.py` (12 erros).
- Issue #45 (Tabela de Issues, `done`): Gate 3 (`test_status_map.py`) e Gate 7
  (`check_dead_shared.py`).
- Stage 2.4 (identity HTTP, ADR 2.4.0001) e issue #26 (log da causa suprimida), já em develop.

## 4. Contratos

### Introduzidos
- **`ApplicationError`** (classe base, `shared/application/errors.py`) — falha de caso de uso
  que não é violação de regra de negócio. Herda de `Exception`, **não** de `DomainError`.
- **`IdentityApplicationError`**, **`StaffApplicationError`**, **`SchedulingApplicationError`**
  (raízes de aplicação, cada uma em `features/<bc>/application/errors.py`, subclasse direta de
  `ApplicationError`).
- **Gate de raiz única** (teste): toda exceção definida nos módulos de erro de um BC descende de
  exatamente uma raiz do BC (`DomainError` xor `ApplicationError`), e nenhuma classe concreta
  lista mais de uma base.
- **Regra 11 de `check_layout.py`** — "a hierarquia de exceções não fala de protocolo".

### Reclassificação (o que muda de raiz)

| BC | Passa a `<BC>ApplicationError` | Fica no domínio (`<BC>Error`) |
|---|---|---|
| identity | `InvalidCredentialsError`, `InvalidAccessTokenError`, `InvalidRefreshTokenError`, `RefreshTokenReuseError`, `InvalidSetupTokenError` (autenticação); `RestaurantNotFoundError`, `UnitNotFoundError`, `UserNotFoundError` (lookup); `RestaurantAlreadyExistsError`, `UnitAlreadyExistsError`, `UserAlreadyExistsError`, `UnitMembershipAlreadyExistsError`, `SessionAlreadyExistsError`, `SessionFingerprintAlreadyExistsError` (colisão de identificador) — **14** | `EmailAlreadyRegisteredError` (kickoff #2), `PermissionDeniedError`, `TenantScopeRequiredError`, `TenantNotVisibleError`, `UnitScopeRequiredError`, `UnitNotVisibleError` (ADR 2.2.0002) — **6** |
| staff | `JobFunctionNotFoundError`, `EmployeeNotFoundError` (lookup); `JobFunctionAlreadyExistsError`, `EmployeeAlreadyExistsError` (colisão de id) — **4** | `JobFunctionNameAlreadyExistsError`, `JobFunctionInUseError`, `EmployeeInUseError`, `EmployeeRelocationError`, `SameUnitCopyError`, `LoginEmailAlreadyInUseError`, `InvalidLoginEmailError`, `EmployeeHasLoginError` — **8** |
| scheduling | `ScheduleNotFoundError`, `StaffMemberNotFoundError`, `JobFunctionNotFoundError` (lookup); `IdentifierInUseError` (colisão de id do cliente, ADR 4.3.0004); `InvalidScheduleRequestError` (pedido malformado); `MissingStaffRecordsError` (insumo de outro BC incompleto) — **6** | `SchedulePeriodTakenError` (escalas da unidade não se sobrepõem), `ScheduleVersionConflictError` (regra canônica de concorrência, decisão do sponsor F8 / ADR 4.1.0001), `BlockingViolationsError`, `UnacknowledgedViolationsError`, `InactiveStaffMemberError`, `InactiveAllocationsInUseError` — **6** |

Os erros de `domain/exceptions/errors.py` dos três BCs não mudam de raiz, **por construção**
(ADR 3.9.0001 §3): são levantados por objetos de domínio, guardam a consistência do próprio
modelo, e o domínio não pode depender de `shared/application`. Por isso os análogos aparentes
ficam no domínio — `ShiftBandNotFoundError`, `ShiftDemandNotFoundError`,
`AssignmentNotFoundError` e `UnavailabilityNotFoundError` (elemento ausente **dentro** de um
agregado já carregado), `DuplicateEntityIdError` (id interno repetido no agregado),
`InvalidEvaluationInputError` (insumo do serviço de domínio) — enquanto
`ScheduleNotFoundError`/`IdentifierInUseError`/`MissingStaffRecordsError`, levantados pela
camada de aplicação sobre o armazenamento ou sobre outro BC, migram.

**Precedência** (ADR 3.9.0001 §3): regra só registrada como decisão técnica de desenho
(inserção-não-upsert do ADR 2.3.0003, detecção de reuso de sessão do ADR 2.2.0001, ids do
cliente do ADR 4.3.0004, a relação de vínculo da invariante #15 da 2.2) não basta para o ramo
de domínio; ele exige fonte de **produto** (doc de domínio, kickoff, decisão do sponsor, ADR de
regra de produto).

### Consumidos
- **Mapas `IDENTITY_ERROR_STATUS` e `STAFF_ERROR_STATUS`** e os handlers únicos — ADR 2.4.0001
  (Stage 2.4) e ADR 3.4.0002 (Stage 3.6). Mudam de chave (duas raízes), não de valor.
- **Gate 3** (`tests/unit/test_status_map.py`) e **Gate 7** (`scripts/check_dead_shared.py`) —
  issue #45.
- **Corpos e log**: corpos constantes 401/403 + `WWW-Authenticate: Bearer` (ADR 2.4.0001 §4);
  `"type": "identity_error"` e `"type": "staff_error"`; linha de log da #26.

## 5. Invariantes e regras

1. **Raiz única, do próprio BC.** Cada BC tem exatamente uma raiz de domínio (subclasse direta
   de `DomainError` em `domain/exceptions/errors.py`) e no máximo uma raiz de aplicação
   (subclasse direta de `ApplicationError` em `application/errors.py`). Toda outra classe de
   exceção definida nos módulos de erro do BC tem **uma** base e descende de exatamente **uma
   das raízes do próprio BC** — não de `ApplicationError`/`DomainError` direto, nem da raiz de
   outro BC.
2. **Critério de raiz** (ADR 3.9.0001 §3): domínio quando nomeia regra que o negócio enuncia;
   aplicação quando o caso de uso não pôde ser atendido por motivo que não é regra
   (recurso endereçado inexistente, credencial que não autentica, identificador técnico que
   colide, versão concorrente, pedido/insumo malformado ou incompleto). A partição de §4 é
   travada por lista explícita no `test_errors.py` de cada BC.
3. **Status só pelo mapa.** Toda subclasse concreta das raízes de um BC com borda HTTP tem
   entrada **própria** no mapa; as raízes não são chave (o oráculo de staff conta 23 entradas);
   todo BC com borda registra o seu handler sobre **cada** raiz.
4. **Sem rede genérica para `ApplicationError`.** `shared` registra `DomainError → 422` e
   `RequestValidationError → 422`; nada para `ApplicationError` (ADR 3.9.0001 §5).
5. **Sem protocolo na hierarquia.** Nenhum dos módulos do item 1 contém, em código, docstring ou
   comentário, os termos `HTTP`, `FastAPI`, `Starlette`, `handler`, `MRO`/`__mro__` ou número de
   status `4xx`/`5xx` (regra 11).
6. **Comportamento observável idêntico.** Os arquivos de oráculo não são editados e passam:
   `tests/e2e/features/identity/test_status_bands.py`,
   `tests/e2e/features/identity/test_suppressed_cause_log.py`,
   `tests/e2e/features/identity/test_auth_flow.py`,
   `tests/e2e/features/identity/test_authorization.py`,
   `tests/e2e/features/staff/test_staff_status_bands.py`,
   `tests/e2e/features/staff/test_staff_authorization.py` e
   `tests/unit/features/identity/adapters/test_http_suppressed_cause_log.py`. Como os e2e de
   faixa assertam só o status, o **corpo** é travado por teste novo: para toda subclasse
   concreta das duas raízes de identity e de staff, a resposta do handler tem o corpo exato da
   faixa (404/409/422: `{"detail": str(exc), "type": "identity_error"|"staff_error"}`;
   401/403 de identity: corpo constante, `WWW-Authenticate: Bearer` só no 401).

## 6. Casos de erro e exceções

| Cenário | Comportamento esperado |
|---|---|
| Erro de identity migrado na faixa 401/403 (ex.: token inválido numa rota de staff, L-AG1) | Handler de identity (registrado na raiz de aplicação) responde 401 com corpo constante e `WWW-Authenticate: Bearer`, e loga a causa com o nome curto da classe — idêntico a antes |
| `*NotFoundError` migrado de identity/staff | 404 com `{"detail": str(exc), "type": "identity_error"}` ou `"staff_error"`, como antes (vinha do mapa, não do handler genérico) |
| Guard converte `UserNotFoundError`/`UnitNotFoundError` | Inalterado: 401/403 (ADR 2.4.0001 §5) |
| Classe nova sem entrada no mapa, sob qualquer das raízes | Gate 3 reprova (já reprovava sob a raiz de domínio; passa a reprovar sob a de aplicação) |
| Classe nova com duas bases, ou fora das raízes do BC | Gate de raiz única reprova |
| BC com borda HTTP que registra handler só numa raiz | Teste de registro reprova |
| Módulo de erro que volta a citar status/framework | Regra 11 de `check_layout.py` reprova |
| `ApplicationError` sem consumidor (BC removendo a raiz) | `check_dead_shared.py` reprova |

## 7. Decisões técnicas relevantes

Não identifiquei bifurcação **P** (preferência de produto): a Stage é neutra em comportamento
observável e todas as escolhas abaixo são de organização interna, fechadas por evidência
interna ou convenção (skill `evidence-resolution`).

### D1 — Onde mora `ApplicationError`
- **O quê:** `shared/application/errors.py`, sem herdar de `DomainError`.
- **Por quê:** conceito de aplicação na camada de aplicação; `shared-layers` já ordena
  `application` acima de `domain`.
- **Fonte:** `[decision:C]` degrau 1 — `.importlinter` contrato `shared-layers` (application
  acima de domain em `shared`) e nenhum `*-application-purity` proíbe
  `restaurant_hub.shared.application`. O texto de LAYOUT §3 ("Pode importar de: ...
  `shared/application/ports/`") é **emendado** pela Stage para nomear também
  `shared/application/errors.py`.
- **ADR:** [3.9.0001](../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md) §1, Alt. C.

### D2 — Critério de classificação e partição
- **O quê:** critério por significado (ADR 3.9.0001 §3) e a tabela de §4.
- **Por quê:** a issue pede migrar só o que **não** é violação de regra de negócio; classificar
  pela camada do módulo (Alt. B do ADR) reproduziria o erro no sentido inverso.
- **Fonte:** `[decision:C]` degrau 1 — issue #48 "Critério de pronto"; ADR 2.2.0002 (RBAC é regra
  de produto); workforce §3.2/§6; shift-scheduling (escalas da unidade não se sobrepõem).
- **Divergência declarada com a issue:** o corpo da #48 cita `EmailAlreadyRegisteredError` como
  "unicidade de persistência". Fica no domínio: a unicidade **global** do e-mail é decisão de
  produto (kickoff #2, citada no próprio docstring e no ADR 2.4.0001 §4), e a tradução dela em
  staff (`LoginEmailAlreadyInUseError`) também fica — classificar uma e não a outra quebraria a
  simetria que L-IG2 estabelece. `SessionAlreadyExistsError` e `InvalidAccessTokenError`, os
  outros dois exemplos da issue, migram.
- **`ScheduleVersionConflictError` fica no domínio:** a concorrência otimista da escala é
  "Regra canônica" do doc de domínio, decisão do sponsor (F8 — ADR 4.1.0001), com a invariante
  "nenhuma mutação é aplicada sobre uma versão que o editor não viu" — fonte de produto.
- **ADR:** 3.9.0001 §3, Alt. B.

### D3 — Uma raiz de aplicação por BC, handler nas duas raízes
- **O quê:** `<BC>ApplicationError(ApplicationError)` em cada `application/errors.py`; o handler
  único de identity e o de staff passam a ser registrados nas duas raízes do BC.
- **Por quê:** mantém o handler do BC como o único que decide status/corpo/log — sem ele, um erro
  migrado cairia fora de qualquer handler. O tipo do mapa passa a aceitar as duas raízes.
- **Fonte:** `[decision:C]` degrau 1 — ADR 2.4.0001 §2 e ADR 3.4.0002 (um handler por BC);
  degrau 4 (a raiz por BC preserva "o que este BC pode levantar" como dois tipos nomeados).
- **ADR:** 3.9.0001 §2 e §4.

### D4 — `NotFoundError` sai; sem rede genérica para `ApplicationError`
- **O quê:** remover `NotFoundError` e o handler genérico 404; não registrar handler genérico
  para `ApplicationError`.
- **Por quê:** sem subclasse, `NotFoundError` é código morto (LAYOUT §4). Uma rede genérica
  responderia em silêncio por um BC que esqueceu de registrar a raiz — o que os gates de §5.3
  tornam inalcançável e a rede só esconderia.
- **Fonte:** `[decision:C]` degrau 1 — LAYOUT §4 ("reutilizado é medido") e a motivação da #48
  ("o mapa é estritamente melhor porque falha alto").
- **Consequência em teste:** o smoke `tests/e2e/test_app_smoke.py` perde a sonda
  `NotFoundError → 404` (o handler que ela testava deixa de existir); a sonda
  `DomainError → 422` fica. Não é oráculo de faixa da #48.
- **ADR:** 3.9.0001 §5, Alt. D e E.

### D5 — Os handlers tratam as duas raízes como uma
- **O quê:** o handler de identity aplica corpo constante, `WWW-Authenticate` e log da causa a
  qualquer erro das duas raízes, e `_nome_da_classe` usa o nome curto para as duas; staff usa
  `"type": "staff_error"` para as duas.
- **Por quê:** é o que mantém a linha de log da #26 e os corpos byte-idênticos.
- **Fonte:** `[decision:C]` degrau 1 — issue #48 critério "faixas byte-idênticas"; issue #26.

### D6 — Escopo do detector
- **O quê:** a regra 11 varre os módulos que **definem** a hierarquia (lista de §5.1), em código,
  docstring e comentário, com o vocabulário de §5.5. Não varre o resto de `domain/`.
- **Por quê:** é o objeto da issue ("hierarquia de exceções de domínio"); os módulos de erro de
  aplicação entram porque passam a hospedar a segunda raiz e também são círculo interno.
  "borda" e "status" ficam fora do vocabulário: têm usos legítimos no domínio (bordas
  inclusivas de período; status de escala).
- **Fonte:** `[decision:C]` degrau 4/5 — issue #48 critério 4; medição por grep (2026-11-02):
  as ocorrências estão em `shared/domain/exceptions/base.py` e nos `errors.py` de domínio e
  aplicação dos três BCs.
- **Divergência declarada com a issue:** a #48 manda verificar "pelo detector de 'protocolo no
  domínio' da #45" — esse detector **nunca existiu** (a #45 não o entregou); a regra 11 é
  criada aqui. E o critério "sem menção a HTTP, status ou framework" é lido com "status" como
  **número de status** (`4xx`/`5xx`): a palavra "status" fica fora do vocabulário porque tem uso
  legítimo no domínio (status de escala), e `base.py` não a contém depois da reescrita.
- **ADR:** 3.9.0001 §6.

## 8. Integrações

### Internas (com outras Stages/módulos)
- **identity ↔ staff (L-AG1/L-AG2):** `InvalidAccessTokenError` e `PermissionDeniedError` sobem
  crus do `AccessGuard` nas rotas de staff e chegam ao handler de identity registrado na app.
  O primeiro muda de raiz; o handler de identity passa a estar registrado também na raiz de
  aplicação, então a resposta continua a mesma.
- **Gateway de staff** (`local_identity_gateway.py`) captura `EmailAlreadyRegisteredError` e
  `InvalidEmailError` pelo nome da classe — nenhum dos dois muda de raiz.
- **Stage 4.5** (futura): escreverá o mapa de scheduling sobre as duas raízes já prontas.

### Externas
- Nenhuma.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Erro migrado sem handler responde 500 | M | A | Handler nas duas raízes (D3) + teste de registro por raiz + e2e de faixa intocados |
| Linha de log da #26 muda (nome qualificado em vez de curto) | M | M | D5; testes de log (unit e e2e) intocados |
| Teste que usa `pytest.raises(StaffError)` para erro migrado deixa de casar | A | B | Ajuste mecânico nas Tasks de migração; a asserção de tipo exato que segue cada `raises` fica |
| Asserção "nada escapa da hierarquia" (`isinstance(x, IdentityError/StaffError)` em `test_integrity_errors.py`; `not isinstance(causa, StaffError)` na lei do gateway) apagada ou enfraquecida | M | M | Reescrever como pertinência às **duas** raízes do BC (`(StaffError, StaffApplicationError)`), nunca remover; a lei do gateway nega as duas raízes de staff |
| Detector com falso positivo em número de 3 dígitos | B | B | Vocabulário restrito a `4xx`/`5xx` com fronteira de palavra; violador plantado e caso negativo no teste |
| Contagem mínima do Gate 3 encolher ao trocar a raiz | M | M | Varredura desce das duas raízes; `_TOTAIS_MINIMOS` re-medido na Task |

## 11. Critérios de aceitação

- [x] **CA1** — ADR 3.9.0001 `accepted` com `supersedes: "2.2.0003"`; ADR 2.2.0003 em
  `superseded` com `superseded_by: "3.9.0001"`; seção `## Supersessão parcial` datada nos ADRs
  2.3.0003, 2.4.0001 e 3.4.0002.
- [x] **CA2** — Raiz única do próprio BC (§5.1): teste em `test_status_map.py` que deriva, por
  BC, exatamente uma raiz de domínio e no máximo uma de aplicação, e exige que toda outra
  exceção dos módulos de erro tenha uma base e descenda de exatamente uma raiz **do BC**; com
  violadores plantados (classe com duas raízes; classe sob `ApplicationError` direto).
- [x] **CA3** — `ApplicationError` existe em `shared/application/errors.py`, tem raiz de
  aplicação em cada um dos três BCs, e a partição de §4 é travada por teste de **igualdade de
  conjuntos** por BC (`test_errors.py`): lista de domínio ∪ lista de aplicação = classes
  definidas no módulo, interseção vazia, cada classe sob a raiz da sua lista.
  `check_dead_shared.py` verde com `ApplicationError` entre os nomes vivos.
- [x] **CA4** — Gate 3 generalizado: totalidade, ausência de órfã e faixa 4xx sobre as subclasses
  das **duas** raízes; teste novo: todo BC com borda registra handler em cada raiz.
- [x] **CA5** — `NotFoundError` e o handler genérico 404 removidos; `shared/domain/exceptions/base.py`
  verde na regra 11 (sem `HTTP`, `FastAPI`, `Starlette`, `handler`, `MRO`, número `4xx`/`5xx`)
  e sem a palavra "status" (conferido por grep no gate de saída).
- [x] **CA6** — Regra 11 de `check_layout.py` verde sobre `src/` e vermelha contra violador
  plantado (um por termo do vocabulário), com caso negativo (número/termo fora do vocabulário).
- [x] **CA7** — Os sete arquivos de oráculo de §5.6 sem diff na branch
  (`git diff origin/develop -- <arquivos>` vazio) e verdes no CI.
- [x] **CA8** — Corpo exato por faixa travado para toda subclasse concreta das duas raízes de
  identity e de staff (§5.6, teste novo).
- [x] **CA9** — `docs/LAYOUT.md` reflete `ApplicationError` em `shared/application` (§2, §4 e a
  lista "Pode importar de" de Application em §3) e a saída de `NotFoundError`.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida?
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido (interface, formato, auth)? — não há
- [x] Decisões com alternativa real descartada têm ADR escrito? — ADR 3.9.0001
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — `check_stage_deps.py` OK
- [x] Stage cabe em ~3–12 Tasks? — estimativa: 7
- [x] Riscos críticos têm mitigação plausível?
- [x] A partição de §4 cobre os 44 erros de aplicação dos três BCs (20 + 12 + 12 = 14+6 + 4+8 + 6+6)?

## 13. Questões em aberto

Nenhuma.

## 14. Referências

- [`../../overview.md`](../../overview.md) — vínculo geral
- [`../../roadmap.md`](../../roadmap.md) — §Stage 3.9
- [ADR 3.9.0001](../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md); ADRs 2.2.0002,
  2.2.0003, 2.3.0003, 2.4.0001, 3.4.0002, 4.1.0001, 4.3.0004
- Issue #48; issue #45 (Gates 3 e 7); issue #26
- Robert C. Martin, *Clean Architecture* (2017), cap. 22 — a Dependency Rule

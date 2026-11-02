---
title: Domínio identity/tenancy-and-access — restaurante, acesso e credenciais (teoria canônica)
description: Camada teórica do subdomínio tenancy-and-access do BC identity — fundamentos, língua ubíqua, regras canônicas e invariantes de isolamento de tenant, papéis fixos e permissões, vínculo usuário↔unidade, autorização, provisionamento, sessões, convite e definição de senha, e fronteiras com staff e scheduling. Backfill que consolida o que os ADRs accepted já decidiram (issue #30)
when-use: Consultar antes de escrever o concept.md de qualquer Stage que toque o BC identity (tenancy, papéis, permissões, membership, login, sessão, convite, senha) ou que consuma o acesso de identity a partir de outro BC; é a base que os concepts consomem em vez de re-derivar dos ADRs 2.x
keywords: [domain, identity, tenancy, tenant, restaurante, unidade, usuario, conta, rbac, papel, permissao, membership, vinculo, visibilidade, bypass, tenant-wide, autorizacao, fail-closed, provisionamento, platform-admin, sessao, refresh, rotacao, reuso, logout, convite, conta-pendente, token-de-setup, definicao-de-senha, redefinicao, enumeracao, unidade-de-trabalho, fachada, lingua-ubiqua]
status: accepted
created_at: 2026-11-02
updated_at: 2026-11-02
bounded_context: identity
subdomain: tenancy-and-access
references:
  - ../staff/workforce.md
  - ../scheduling/shift-scheduling.md
  - ../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md
  - ../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md
  - ../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md
  - ../../adr/2_1_0001-identity-aggregates-and-membership.md
  - ../../adr/2_1_0002-platform-admin-without-tenant.md
  - ../../adr/2_2_0001-revocable-refresh-session-port.md
  - ../../adr/2_2_0002-authorization-two-axes-fail-closed.md
  - ../../adr/2_2_0003-application-errors-in-identity-hierarchy.md
  - ../../adr/2_2_0004-synchronous-port-signatures.md
  - ../../adr/2_3_0001-integration-tests-require-real-postgres.md
  - ../../adr/2_3_0002-identity-schema-tenant-and-constraints.md
  - ../../adr/2_3_0003-add-is-insertion-not-upsert.md
  - ../../adr/2_3_0004-session-retention-and-purge.md
  - ../../adr/2_3_0005-names-persisted-verbatim.md
  - ../../adr/2_4_0001-http-error-status-mapping.md
  - ../../adr/2_4_0002-decode-extends-token-issuer.md
  - ../../adr/2_4_0003-authorization-composition-at-boundary.md
  - ../../adr/2_4_0004-security-adapter-parameters.md
  - ../../adr/2_5_0001-email-sender-in-shared.md
  - ../../adr/2_5_0002-dedicated-single-use-setup-token.md
  - ../../adr/2_5_0003-password-change-revokes-sessions.md
  - ../../adr/2_5_0004-unusable-hash-for-pending-accounts.md
  - ../../adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md
  - ../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md
  - ../../adr/3_4_0001-staff-owned-access-guard-port.md
  - ../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md
  - ../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md
  - ../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md
  - ../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md
  - ../../adr/3_5_0003-termination-revokes-sessions-account-remains.md
  - ../../adr/3_7_0001-every-staff-use-case-authorizes-its-own-target.md
  - ../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md
  - ../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md
  - ../../adr/4_1_0004-hr-reads-schedules-in-member-units.md
  - ../../adr/4_1_0005-unit-timezone-owned-by-identity.md
---

# Domínio identity/tenancy-and-access — restaurante, acesso e credenciais

> **Camada teórica** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este doc fixa o *o quê* e o *porquê* do subdomínio — conceitos, regras canônicas, invariantes e
> língua ubíqua. **Não é spec de implementação**: schemas, tabelas, endpoints e edge cases vivem no
> `technical.md` + código de cada Stage. Onde os insumos ratificados não fixam uma regra, o ponto é
> registrado como **lacuna declarada** (§5) — nunca decidido aqui.
>
> **Backfill (issue #30).** O ADR 0.0.0003 previa este doc como a primeira instância de
> `docs/domain/`, o gate de domínio do Step 2. O Step 2 foi executado sem ele (Stages 2.1–2.6
> `done`), e a teoria ficou espalhada no `overview.md`, nos ADRs 2.x e nos concepts das Stages.
> Este doc **consolida** o que já foi ratificado — toda regra abaixo cita a sua fonte, nenhuma é
> nova. O que a consolidação achou de contraditório ou desatualizado nas fontes está em §7, não
> reconciliado em silêncio.

---

## 1. Propósito e escopo

O subdomínio **tenancy-and-access** cobre a teoria de **quem existe** no sistema e **o que cada um
alcança**:

- o **restaurante** como tenant e o **isolamento** entre tenants;
- a **unidade** como filial do restaurante;
- o **usuário** (conta de acesso) e o seu **papel fixo**, com o conjunto de **permissões** que o
  papel concede (eixo A);
- o **vínculo usuário↔unidade** e a **visibilidade** de unidade que ele produz (eixo B);
- a **autorização**: a ordem normativa das checagens, a composição na borda e de onde vem o tenant;
- o **provisionamento**: quem cria restaurante, dono, unidade e usuário;
- as **credenciais**: login, sessão revogável, rotação e reuso de refresh, logout;
- a **conta pendente**: convite, link de definição de senha, redefinição e o que definir a senha
  revoga;
- a **atomicidade** das escritas de identity e as **fronteiras** com staff e scheduling.

É a base que os `concept.md` de qualquer Stage futura de identity consomem — e que staff
([`workforce.md`](../staff/workforce.md) §3.8, §4) e scheduling
([`shift-scheduling.md`](../scheduling/shift-scheduling.md) §3.10.2, §4) leem como insumo.

**Fora do escopo deste subdomínio** (fronteiras negativas ratificadas):

- **Função de trabalho** (cozinheiro, atendente…) — é do BC `staff`, customizável por restaurante.
  **Papel ≠ função** (`overview.md` §9 Glossário; [`workforce.md`](../staff/workforce.md) §2).
- **O registro de funcionário** e o seu ciclo de vida (desligamento, recontratação) — `staff`. Este
  doc fixa só o que identity faz quando staff a aciona (§3.9).
- **Auto-cadastro do dono e cobrança** — Step 13 (`roadmap.md` §"Tabela de Steps").
  O provisionamento v1 é ato de plataforma (§3.5).
- **Escala** — permissões de escala são do BC `scheduling`, que estende o vocabulário de
  permissões de identity ([ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md);
  [`shift-scheduling.md`](../scheduling/shift-scheduling.md) §4).

---

## 2. Língua ubíqua

| Termo | Definição |
|---|---|
| **Restaurante** (tenant) | Cliente da plataforma, isolado dos demais (`overview.md` §9, "Tenant"). O restaurante **é** o tenant: a sua identidade é o `tenant_id` de tudo o que lhe pertence; não existe entidade `Tenant` separada ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision). |
| **Unidade** | Filial de um restaurante. Pertence a exatamente um restaurante, que é o seu tenant ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision). "Unidades não compartilham funcionários (não se enxergam)" (`overview.md` §3). |
| **Usuário** (conta) | Conta de acesso de uma pessoa: e-mail de login, papel fixo e tenant. Distinto do **registro de funcionário** de staff — uma pessoa tem no máximo uma conta e pode ter vários registros ([`workforce.md`](../staff/workforce.md) §3.1). |
| **Papel** (de acesso) | Um de **cinco** valores fixos: `platform_admin`, `owner` (dono), `manager` (gerente), `hr` (RH), `employee` (funcionário) (`overview.md` §3 "RBAC"; concept 2.1 §5 regra 5). Não é customizável. |
| **Permissão** | Capacidade que um papel concede (eixo A). O mapa papel → permissões é fixo e total (concept 2.1 §5 regra 6). "Ver o tenant inteiro" **não** é permissão — é bypass do eixo B (concept 2.1 §7). |
| **Vínculo** (membership) | Ligação mínima usuário↔unidade, sem papel por unidade ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision). É o que dá visibilidade de unidade aos papéis escopados. |
| **Visibilidade** | Quais unidades um usuário enxerga (eixo B). Ortogonal às permissões ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision). |
| **Bypass de unidade** | `owner` e `platform_admin` enxergam todo o seu escopo sem vínculo; `manager`, `hr` e `employee` só as unidades vinculadas (concept 2.1 §5 regra 4). |
| **Permissão tenant-wide** | Permissão cujo alvo é o restaurante, não a unidade; dispensa nomear unidade. Conjunto enumerado, hoje só `manage_job_functions` ([ADR 3.4.0008](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md) §1). |
| **Admin de plataforma** | `platform_admin`: gerencia acessos e tenants (`overview.md` §3), vive **fora de qualquer tenant** ([ADR 2.1.0002](../../adr/2_1_0002-platform-admin-without-tenant.md)). |
| **Provisionar** | Criar o restaurante com o seu primeiro dono (ato de plataforma — [ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md)); por extensão, criar a conta pendente de um funcionário ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §3). |
| **Sessão** | Registro revogável de um login, guardado pela impressão (fingerprint) do refresh token, nunca pelo valor ([ADR 2.2.0001](../../adr/2_2_0001-revocable-refresh-session-port.md) §Decision). |
| **Access token** | Credencial curta e assinada que carrega usuário, papel, tenant e sessão (concept 2.4; `AccessTokenClaims`). Não é revogável antes de expirar ([ADR 2.5.0003](../../adr/2_5_0003-password-change-revokes-sessions.md) §Decision). |
| **Refresh token** | Credencial opaca que renova o par; **rotaciona** a cada uso ([ADR 2.2.0001](../../adr/2_2_0001-revocable-refresh-session-port.md) §Decision). |
| **Reuso** | Reapresentação de um refresh cuja sessão já foi revogada — sinal de roubo; derruba todas as sessões do usuário (concept 2.4 §5 regra 5). |
| **Token de setup** | Token dedicado, de uso único e com propósito (convite ou redefinição), que só serve para **definir a senha** ([ADR 2.5.0002](../../adr/2_5_0002-dedicated-single-use-setup-token.md)). |
| **Conta pendente** | Conta criada sem senha utilizável (hash inutilizável), que só se torna usável pelo link de definição de senha ([ADR 2.5.0004](../../adr/2_5_0004-unusable-hash-for-pending-accounts.md); [ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §1). |
| **Link entregue em mãos** | O mesmo link de definição de senha do convite, devolvido uma vez ao gestor para entrega física, com prazo próprio ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §2, §3b). Não há senha provisória. |
| **Fachada de identity** | Serviço in-process com tipos primitivos, única porta por onde outro BC alcança identity ([ADR 3.5.0001](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md) §1, §4). |

> **Linguagem de produto × modelo.** O sponsor descreveu o acesso em três níveis —
> **ouro/prata/bronze**. Isso é linguagem de produto, não o modelo: ouro ≈ `owner`,
> prata ≈ `manager`/`hr` (escopados por atribuição), bronze ≈ `employee`; `platform_admin` fica
> fora dos três. O modelo segue com os cinco papéis (decisões de kickoff de 2026-07-19, registradas
> na memória do projeto e citadas em [`workforce.md`](../staff/workforce.md) §4 e
> [`shift-scheduling.md`](../scheduling/shift-scheduling.md) §4 como "kickoff #9/#10").

---

## 3. Conceitos e regras canônicas

### 3.1 Restaurante, unidade e isolamento de tenant

**Regras canônicas:**

- **Três agregados, ligados só por id.** `Restaurant`, `Unit` e `User` são raízes de agregado
  separadas; `Unit.restaurant_id` e `User.tenant_id` são ids, nunca referência de objeto
  ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision).
- **O tenant da unidade é o seu restaurante.** Toda linha de identity (e dos BCs seguintes) que
  pertence a um restaurante carrega o seu id como `tenant_id`; o isolamento é **row-level** num
  único banco na v1 (`roadmap.md` §"Premissas adotadas no Roadmap" › ROADMAP-3).
- **Todo usuário de papel de restaurante tem tenant; só o `platform_admin` não tem.** `tenant_id`
  ausente ⇔ papel `platform_admin` — a exceção explícita e única às regras de isolamento; não
  existe "tenant plataforma" fabricado
  ([ADR 2.1.0002](../../adr/2_1_0002-platform-admin-without-tenant.md) §Decision; concept 2.1 §5
  regras 1–2). Tenant em branco é ausência de tenant, não um tenant
  (`src/restaurant_hub/features/identity/domain/entities/user.py`, `User.__post_init__`).
- **Vínculo só dentro do tenant.** Um usuário só se vincula a unidade do próprio tenant, e o
  `platform_admin` não se vincula a unidade nenhuma (`User.link_to_unit`;
  [ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision). O vínculo
  entre tenants é **irrepresentável**, não só desencorajado: a persistência ancora o vínculo no
  tenant dos dois lados ([ADR 2.3.0002](../../adr/2_3_0002-identity-schema-tenant-and-constraints.md)
  §Decision 1).
- **Nenhum usuário de tenant enxerga unidade de outro tenant**, qualquer que seja o papel
  (concept 2.1 §5 regra 4).
- **A sessão alcança o tenant pelo usuário.** Sessão não carrega tenant próprio; a fonte da verdade
  é o tenant do usuário ([ADR 2.3.0002](../../adr/2_3_0002-identity-schema-tenant-and-constraints.md)
  §Decision 3).
- **Nomes são dados livres, gravados verbatim.** Nome de restaurante e de unidade não pode ser
  vazio (domínio) e é persistido byte a byte, sem normalização nem unicidade
  ([ADR 2.3.0005](../../adr/2_3_0005-names-persisted-verbatim.md) §Decision).

### 3.2 Papéis fixos e permissões (eixo A)

**Regras canônicas:**

- **Conjunto fechado de cinco papéis**; nenhum outro valor é papel (concept 2.1 §5 regra 5;
  `overview.md` §3 "RBAC").
- **O mapa papel → permissões é fixo, total e mora no domínio** — todo papel tem entrada, ainda que
  vazia; `has_permission(p)` ⇔ `p` está no conjunto do papel (concept 2.1 §5 regra 6). A
  totalidade é guardada por teste (`role.py`, docstring do módulo).
- **Acesso de plataforma ≠ acesso de restaurante.** O `platform_admin` detém **só**
  `manage_platform`, e nenhum papel de restaurante detém `manage_platform` (concept 2.1 §5 regra
  7; [ADR 2.1.0002](../../adr/2_1_0002-platform-admin-without-tenant.md) §Decision).
- **As permissões crescem por BC, por decisão.** O vocabulário nasceu com três capacidades de
  identity e foi estendido por staff com `manage_staff` e `manage_job_functions`
  ([ADR 3.4.0006](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md) §Decision);
  scheduling estende com três famílias unit-scoped — ler, gerenciar, própria
  ([ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md) §Decision), ainda não
  presentes no mapa de identity (§5).

**Matriz vigente** (`src/restaurant_hub/features/identity/domain/value_objects/role.py`,
`_ROLE_PERMISSIONS`, em `develop` em 2026-11-02):

| Papel | `manage_platform` | `manage_tenant` | `manage_users` | `manage_staff` | `manage_job_functions` |
|---|---|---|---|---|---|
| `platform_admin` | ✔ | | | | |
| `owner` | | ✔ | ✔ | ✔ | ✔ |
| `manager` | | | ✔ | ✔ | ✔ |
| `hr` | | | ✔ | ✔ | ✔ |
| `employee` | | | | | |

- **`manager` e `hr` coincidem em identity e em staff.** A divergência entre eles é de **família de
  operação** e mora na escala: o RH mexe no cadastro e **lê** a escala das unidades de que é
  membro; mexer na escala é do gerente e do dono
  ([ADR 3.4.0006](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md) §Decision, com
  errata; [ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md) §Decision).
- **`employee` tem permissões vazias** na v1: autentica, mas não alcança nada até existir a
  primeira permissão de autoatendimento ("minha escala") (concept 2.1 §5 regra 6;
  [ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md) §Decision 3).
- **Negar acesso é regra de negócio.** As negações de autorização são erros de **domínio** de
  identity — quem pode fazer o quê é regra de produto
  ([ADR 3.9.0001](../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md) §Decision 3, que
  supera o [ADR 2.2.0003](../../adr/2_2_0003-application-errors-in-identity-hierarchy.md)).

### 3.3 Vínculo usuário↔unidade e visibilidade (eixo B)

**Regras canônicas:**

- **O vínculo é mínimo**: usuário + unidade, sem papel por unidade; o papel é **único no tenant**
  ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision). Papel por
  unidade é evolução prevista que cabe como atributo do vínculo sem refazer a forma (concept 2.1
  §7 "Fronteiras de agregado e esqueleto de membership").
- **Os dois eixos são ortogonais** — o papel diz o que se faz; o vínculo diz onde
  ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) §Decision).
- **Quem enxerga qual unidade** (concept 2.1 §5 regra 4; `User.can_view_unit`):
  - `platform_admin` — qualquer unidade, resolvido antes de qualquer comparação de tenant;
  - usuário de tenant — **nunca** unidade de outro tenant;
  - `owner` — todas as unidades do próprio tenant, sem vínculo;
  - `manager`, `hr`, `employee` — só as unidades para as quais existe **vínculo do próprio
    usuário**: o vínculo de outro usuário do mesmo tenant não concede nada.
- **A visibilidade não confia no filtro do repositório.** O domínio casa usuário **e** unidade no
  vínculo; um repositório que devolvesse vínculo alheio não concederia visibilidade (concept 2.2
  §5 regra 13).
- **Vínculo é relação, não multiconjunto**: unidades repetidas no pedido viram um vínculo só
  (concept 2.2 §5 regra 15).
- **O vínculo nasce com a conta.** Na v1 os vínculos de um usuário são fixados quando ele é criado
  (`POST /users`, convite, login de funcionário); não existe operação de acrescentar, retirar ou
  trocar vínculo depois (lacuna, §5).

### 3.4 Autorização

**Ordem normativa, falha fechada.** Uma única autorização avalia, nesta ordem, e **levanta** uma
exceção distinta na primeira checagem que falha — nunca devolve um booleano que o chamador possa
esquecer de checar ([ADR 2.2.0002](../../adr/2_2_0002-authorization-two-axes-fail-closed.md)
§Decision; concept 2.2 §5 regras 6 e 8):

1. **O ator existe.**
2. **Eixo A** — o papel do ator concede a permissão.
3. **Escopo de tenant** — para quem não é `platform_admin`, o tenant alvo é **obrigatório** e tem de
   ser o do ator. É obrigação, não filtro: omitir o tenant alvo é negado.
4. **Exigência de unidade** — sem unidade alvo, só passa quem bypassa o escopo de unidade **ou**
   exerce uma permissão tenant-wide
   ([ADR 3.4.0008](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md) §2). Fecha
   a escalada por omissão: um gerente não ganha alcance de tenant por deixar de nomear a unidade.
5. **Eixo B** — com unidade alvo, ela existe, pertence ao tenant alvo (coerência que vale também
   para o `platform_admin`) e o ator a enxerga.

A ordem é contrato: um ator que falha em várias checagens recebe o erro da primeira, e há teste que
quebra se ela for reordenada ([ADR 2.2.0002](../../adr/2_2_0002-authorization-two-axes-fail-closed.md)
§Decision). A autorização devolve o ator **e o escopo que acabou de validar**, para que nenhum
chamador re-derive o alvo da requisição (idem).

**A dispensa de unidade é por permissão, nunca por papel.** Entrar no conjunto tenant-wide é ato
deliberado, com teste de lista explícita; `manage_staff` fica fora de propósito — registro de
funcionário mora numa unidade
([ADR 3.4.0008](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md) §3, §5). A
dispensa retira a *exigência de nomear* a unidade; não retira checagem nenhuma (idem, §4).

**Composição na borda de identity.** O adapter declara quais permissões a ação exige e o escopo
alvo, e delega **toda** decisão à autorização acima — sem tabela de papéis própria, sem bypass
próprio ([ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) §1). Os use
cases de identity **não** recebem ator nem autorizam: a autorização de identity mora na borda HTTP
([ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) §4) —
ao contrário de staff, onde todo use case autoriza o próprio alvo
([ADR 3.7.0001](../../adr/3_7_0001-every-staff-use-case-authorizes-its-own-target.md)). Se identity
deve seguir staff é decisão aberta para o BC inteiro (issue #115; §5).

**"Não se concede o que não se detém" — nas rotas de tenant.** Criar ou convidar um usuário de
papel `P` exige do ator `manage_users` **mais todas as permissões de `P`**, derivado do mapa de
papéis, uma autorização por permissão e **uma por unidade pedida**
([ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) §2, §3; concept 2.5
§5 regra 12). Daí: o dono cria qualquer papel de restaurante; gerente e RH criam gerente, RH e
funcionário, mas não dono; ninguém cria `platform_admin` por essa rota. **Não é propriedade
universal do sistema**: vale para essas rotas (ADR 2.4.0003 §2).

**De onde vem o tenant** ([ADR 0.0.0005](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
§Decision, cláusulas 1–3, transversal):

- O tenant que decide o acesso **sempre deriva do token**; tenant que chega na requisição é
  declaração conferida contra ele, nunca fonte.
- O tenant aparece no caminho da requisição **só** quando o BC é dono do restaurante como recurso
  endereçável (identity é; staff e scheduling não) ou quando o ator age fora do próprio tenant
  (`platform_admin`).
- O tenant do usuário criado **nunca** vem do corpo: nas rotas de tenant é o do ator; na rota de
  plataforma é o restaurante do caminho, resolvido contra o banco
  ([ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) §4).
- A checagem não é vazia: o tenant do token é comparado com o do usuário **carregado do banco**
  ([ADR 0.0.0005](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
  §Decision, último parágrafo).

**Respostas que não viram oráculo** ([ADR 2.4.0001](../../adr/2_4_0001-http-error-status-mapping.md)
§Decision 4–6, mantidas pelo ADR 3.9.0001): negações de autenticação e de autorização respondem com
corpo constante por faixa; ator cujo usuário sumiu é credencial inválida; unidade inexistente,
para quem não a enxerga, é o mesmo "não visível" de unidade alheia — "ausente" e "não é sua" têm de
ser a mesma resposta. **Exceção declarada e aceita:** a unicidade global de e-mail é checada antes
do escopo, então um ator de tenant pode saber que um endereço já existe em algum lugar (sem tenant,
id nem papel do dono) — fechar isso exigiria rever a unicidade global (idem, §4).

### 3.5 Provisionamento: quem cria o quê

**Regras canônicas:**

- **Só a plataforma cria restaurante, e o restaurante nasce com dono.** O `platform_admin` cria o
  restaurante **e** o seu primeiro `owner` num único ato atômico; nenhum caminho cria restaurante
  sem dono; o papel emitido é o literal `owner`, fixado no use case, nunca lido da requisição
  ([ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md)
  §1–§2). Sem isso o restaurante nasceria inoperável, porque o `platform_admin` não detém
  permissão de restaurante ([ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md)
  §5).
- **Acrescentar dono a restaurante existente** é rota de plataforma separada — suporte quando os
  donos perdem o acesso, e recuperação dos restaurantes criados antes do provisionamento composto
  ([ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) §3).
- **São duas, e só duas, as rotas que emitem papel sem a composição de §3.4**, ambas exigindo
  `manage_platform` e ambas emitindo o literal `owner` (idem, §3; supersessão parcial no
  [ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md)). Rota nova que emita
  papel fora da composição exige ADR próprio dizendo qual garantia gasta (ADR 2.4.0003 §5).
- **Nenhuma rota emite `platform_admin`.** É essa a garantia real — não "a composição o proíbe"; o
  primeiro `platform_admin` é semeado fora da API, como raiz de confiança
  ([ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) §2, §2b; concept 2.4
  §5 regra 8).
- **O dono cria e gerencia as unidades** do seu restaurante (`manage_tenant`); o caminho endereça o
  restaurante como recurso de identity
  ([ADR 0.0.0005](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
  §Decision, tabela de rotas).
- **Usuários de restaurante** são criados com senha (`POST /users`) ou convidados como conta
  pendente (§3.7), pela composição de §3.4. O **login de funcionário** é criado a partir do
  registro de staff, sempre como conta pendente de papel `employee`
  ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §1).
- **O dono provisionado recebe senha, não convite** — a forma da credencial que a rota de
  plataforma já tinha ([ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md)
  §5). Que a plataforma conheça a senha inicial do dono é lacuna aberta (issue #114; §5).

### 3.6 Login, sessão e janela de revogação

**Regras canônicas:**

- **E-mail é único globalmente**, não por tenant; a conta pertence a um tenant. Como o e-mail é
  normalizado (espaços nas pontas e caixa) no domínio, a unicidade não distingue maiúsculas
  (concept 2.2 §5 regra 4; `domain/value_objects/email.py`). É regra de **produto**
  ([ADR 3.9.0001](../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md) §Decision 3).
  Consequência: o login pede só e-mail e senha — o tenant sai da conta
  (`AuthenticateUserCommand`, `application/dtos/commands.py`).
- **O login não revela se o e-mail existe.** E-mail inexistente e senha errada dão a mesma falha e
  nenhuma sessão, e o caminho do e-mail inexistente paga o mesmo custo de hash, para que o tempo
  não vire oráculo (concept 2.2 §5 regra 14).
- **A senha em claro nunca é persistida nem devolvida** (concept 2.2 §5 regra 9). O algoritmo é
  argon2id (`roadmap.md` §"Premissas adotadas no Roadmap" › ROADMAP-4;
  [ADR 2.4.0004](../../adr/2_4_0004-security-adapter-parameters.md), com as fontes OWASP em
  `## References`).
- **Todo login abre exatamente uma sessão revogável.** A sessão guarda só a impressão do refresh
  token; vale do instante de emissão até a expiração, em intervalo semiaberto — no instante da
  expiração ela já expirou ([ADR 2.2.0001](../../adr/2_2_0001-revocable-refresh-session-port.md)
  §Decision; concept 2.2 §5 regras 10–11).
- **Revogar preserva o primeiro instante.** Revogar de novo é inócuo e não sobrescreve quando a
  sessão foi revogada — a perícia de um reuso depende disso (ADR 2.2.0001 §Decision).
- **Rotação com detecção de reuso.** Cada refresh revoga a sessão antiga e abre a nova; refresh de
  sessão **já revogada** é reuso e derruba **todas as sessões do usuário** — "família" é,
  literalmente, todas as sessões, porque a sessão não guarda linhagem nem causa de revogação. A
  checagem de revogada vem **antes** da de expirada: o token roubado e guardado é exatamente o
  revogado e expirado (concept 2.4 §5 regra 5; ADR 2.2.0001 §Decision). Rotação concorrente
  perdida também é reuso, falha fechada
  ([ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
  §1b).
- **Logout é idempotente e silencioso** — refresh desconhecido, expirado ou já revogado responde
  igual, para não virar oráculo de validade. Efeito declarado: reapresentar no refresh um token que
  saiu por logout conta como reuso (concept 2.4 §5 regra 6).
- **A janela de revogação é a vida do access token.** Revogar corta o refresh na hora; o access token
  já emitido vale até expirar — 15 minutos por padrão, configurável. Foi aceito pelo sponsor em
  2026-07-19 como a latência de revogação do sistema, sem introspecção por requisição
  ([ADR 2.5.0003](../../adr/2_5_0003-password-change-revokes-sessions.md) §Decision;
  [ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md) §Decision 3).
- **Prazos são configuração, não literal**: access, refresh, convite, redefinição e link entregue
  em mãos (concept 2.4 §5 regra 12; concept 2.5 §5 regra 15;
  [ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §3b).
  Os valores padrão vivem em `Settings`, não aqui.
- **Sessão expirada é expurgável; a retenção é decisão de quem chama** — o expurgo nunca toca sessão
  ainda válida, revogada ou não, e o limite é o mesmo semiaberto da expiração
  ([ADR 2.3.0004](../../adr/2_3_0004-session-retention-and-purge.md) §Decision).

### 3.7 Conta pendente, convite e definição de senha

**Regras canônicas:**

- **Conta pendente não tem senha utilizável.** Ela nasce com um hash aleatório sem pré-imagem
  conhecida — nunca com o hash de um literal do repositório, que viraria senha válida de todo convite
  pendente. Tentar logar nela é indistinguível de senha errada
  ([ADR 2.5.0004](../../adr/2_5_0004-unusable-hash-for-pending-accounts.md) §Decision; concept 2.5
  §5 regra 9).
- **O token de setup é dedicado, persistido só por impressão, de uso único e com propósito**
  (convite × redefinição). O uso único é uma transição atômica condicional: o segundo uso perde
  ([ADR 2.5.0002](../../adr/2_5_0002-dedicated-single-use-setup-token.md) §1–§3).
- **Emitir invalida só os do mesmo propósito; redimir invalida todos.** Reconvidar deixa um convite
  vivo e repedir redefinição deixa uma redefinição viva; uma redefinição pública **não** mata um
  convite pendente — senão qualquer um derrubaria o convite de qualquer vítima em loop
  ([ADR 2.5.0002](../../adr/2_5_0002-dedicated-single-use-setup-token.md) §5).
- **O alvo vem só do token.** Quem define a senha é o usuário que o servidor gravou no token; nem o
  pedido nem o corpo nomeiam usuário (concept 2.5 §5 regra 10).
- **Definir a senha expulsa o acesso anterior:** revoga todas as sessões do usuário e invalida todos
  os seus outros tokens de setup, de qualquer propósito
  ([ADR 2.5.0003](../../adr/2_5_0003-password-change-revokes-sessions.md) §Decision). As quatro
  escritas (consumir, revogar, invalidar, gravar a senha) são atômicas desde a Stage 2.6
  ([ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
  §1); consumir vem primeiro, porque é ele que decide a corrida (§7, achado C3).
- **Definir a senha não autentica** — sem par de tokens na resposta, para o link não virar
  credencial de sessão (concept 2.5 §5 regra 14).
- **Toda falha de token é a mesma falha**: desconhecido, expirado, já consumido ou de usuário
  removido — inclusive este último, para não confirmar que a string era um token genuíno (concept
  2.5 §5 regra 16).
- **O pedido de redefinição é indistinguível**: e-mail cadastrado ou não produz a mesma resposta, e
  falha de envio nesse caminho é absorvida, senão o erro do provedor enumeraria contas. No convite,
  ao contrário, a falha de envio **propaga** — o ator autenticado precisa saber que o convite não
  saiu, e o caminho de recuperação é a redefinição (concept 2.5 §5 regras 7, 8, 13).
- **O segredo nunca sai por API, log ou URL de redirect** no convite por e-mail; o único lugar onde
  ele aparece é a mensagem (concept 2.5 §5 regra 1). **Exceção deliberada:** no login de
  funcionário com entrega em mãos, o link volta **uma vez** na resposta ao ator que acabou de ser
  autorizado com `manage_staff` e `manage_users` na unidade, e nunca mais
  ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §2,
  §5).
- **Não existe senha provisória.** O gestor escolhe o canal (e-mail ou em mãos), não a credencial;
  a troca "obrigatória" é estrutural, porque o segredo entregue só define senha
  ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) §1–§2).
  O link em mãos tem janela própria e mais longa que a do convite por e-mail (idem, §3b).
- **Provisionar e entregar são atos separados** em identity, para que staff grave o vínculo do
  registro entre os dois; o formato do link é de identity — staff nunca o conhece (idem, §3–§4).
- **O envio de e-mail é port compartilhado**, genérico (destinatário, assunto, corpo), sem
  vocabulário de convite ([ADR 2.5.0001](../../adr/2_5_0001-email-sender-in-shared.md) §Decision).

### 3.8 Atomicidade das escritas de identity

- **O que precisa ser atômico roda numa unidade de trabalho de identity**, aberta pelo use case em
  volta **só** das escritas — leituras, checagens e hash antes; efeitos irreversíveis depois
  ([ADR 2.6.0001](../../adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md) §1–§2).
  Os cinco use cases que escrevem mais de uma vez — definir senha, convidar, provisionar conta,
  pedir redefinição e a rotação de refresh — mais o provisionamento de restaurante com dono
  ([ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
  §1; [ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md)
  §1).
- **E-mail sai depois do commit** — rollback não "desenvia" e-mail
  ([ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
  §3).
- **Não há transação entre bounded contexts.** As travessias staff → identity (criar login,
  desligar) mantêm ordem e janelas declaradas; a conta órfã em identity quando a gravação de staff
  falha continua janela declarada (idem, §2).
- **Inserir não é sobrescrever.** Gravar uma chave que já existe é colisão, não atualização; e
  impressão de refresh repetida é sinal de reuso, distinto de colisão de id
  ([ADR 2.3.0003](../../adr/2_3_0003-add-is-insertion-not-upsert.md) §Decision 1–3).

### 3.9 Fronteiras com os outros BCs

- **Uma porta só: a fachada.** Outro BC alcança identity só pela fachada in-process, com tipos
  primitivos, que **não autoriza** e repassa os erros de identity sem traduzir; é o padrão de toda
  travessia in-process futura
  ([ADR 3.5.0001](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md) §1–§4). Em `develop`
  em 2026-11-02 a fachada oferece provisionar conta, enviar convite, revogar todas as sessões e
  consultar o papel de uma conta (`application/facade.py`).
- **A guarda de acesso de staff** é port do próprio staff, montado no composition root sobre a
  autorização de identity ([ADR 3.4.0001](../../adr/3_4_0001-staff-owned-access-guard-port.md)
  §Decision, com supersessão parcial pelo ADR 3.5.0001 §5); levá-la para fora do composition root é
  a issue #47 (§5).
- **Desligar no staff não desativa a conta.** O desligamento revoga as sessões do login **só**
  quando o registro é a fonte do acesso — registro ativo, sem outro registro ativo da mesma unidade
  com o mesmo login, e login de papel `employee`; a conta continua existindo e autenticando
  ([ADR 3.8.0001](../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md)
  §1–§4, que supera em parte o
  [ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md)). Desativar
  conta, quando existir, será ato separado de identity, nunca consequência do desligamento (ADR
  3.8.0001 §4).
- **O fuso da unidade é de identity** — `Unit.timezone`, chave IANA, padrão `America/Sao_Paulo`,
  lido por port pelos outros BCs
  ([ADR 4.1.0005](../../adr/4_1_0005-unit-timezone-owned-by-identity.md) §Decision). Ainda não
  existe no `Unit` (§5).
- **Staff e scheduling estendem o vocabulário de permissões** por decisão registrada em ADR (§3.2);
  a teoria de quem faz o quê **dentro** deles vive nos seus docs
  ([`workforce.md`](../staff/workforce.md) §4; [`shift-scheduling.md`](../scheduling/shift-scheduling.md)
  §4).

---

## 4. Particularidades por papel — visão consolidada

| Papel | Em identity |
|---|---|
| **admin de plataforma** | Sem tenant, sem vínculo. Só `manage_platform`: provisiona restaurante com dono e acrescenta dono a restaurante existente. Enxerga qualquer unidade (bypass), mas não detém permissão de restaurante. Não é criável pela API ([ADR 2.1.0002](../../adr/2_1_0002-platform-admin-without-tenant.md); [ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md); [ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) §2b). |
| **dono (owner)** | Todas as unidades do tenant, sem vínculo. Cria unidades (`manage_tenant`) e usuários de qualquer papel de restaurante, inclusive outro dono (§3.4). |
| **gerente (manager)** | Só as unidades de que é membro. Cria e convida gerente, RH e funcionário nessas unidades; não cria dono ([ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) §2). |
| **RH (hr)** | Idêntico ao gerente em identity; diverge só na escala ([ADR 3.4.0006](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md); [ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md)). |
| **funcionário (employee)** | Só as unidades de que é membro; permissões vazias — autentica e não alcança nada na v1. A primeira permissão de autoatendimento é "minha escala" (Step 4) ([ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md) §3, §5). |

---

## 5. Lacunas declaradas

Pontos em que os insumos ratificados **não fixam** a regra. Nenhum é decidido aqui; cada um tem a
sua âncora de origem.

- **Credencial inicial do dono** — a plataforma escolhe a senha do dono provisionado e nada obriga a
  troca. Convite, troca obrigatória ou senha mantida é decisão P do sponsor — issue #114
  ([ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md),
  Alternativa E e Consequências).
- **Autorização dentro dos use cases de identity** — hoje só na borda HTTP; um segundo driver (CLI,
  job, console) não herdaria a checagem. Decisão para o BC inteiro — issue #115
  ([ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) §4).
- **Gestão de vínculo depois da criação** — acrescentar, retirar ou trocar unidade de um usuário,
  e vincular login existente a registro de staff (o gerente ou dono que também trabalha na escala)
  — issue #107; a regra de fim de vínculo a aplicar é a do
  [ADR 3.8.0001](../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md) §5.
- **Usuário de papel escopado sem vínculo** — nada exige que gerente, RH ou funcionário nasça com
  ao menos uma unidade; criado assim, ele não enxerga nada. Nenhuma fonte decide se isso é
  permitido (concept 2.2 §5 regra 7 não o trata).
- **Desativação de conta** — não existe; o gatilho é a primeira permissão de autoatendimento do
  `employee`, e a Stage que a conceder (ou uma de identity imediatamente antes) acrescenta a
  desativação ([ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md)
  §5). Hoje o mapa de papéis de identity ainda não concede nenhuma permissão de escala.
- **Permissões de escala no mapa de identity** — as três famílias decididas pelo
  [ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md) ainda não estão em
  `Permission`/`_ROLE_PERMISSIONS`; os nomes e o mapa são da borda HTTP de scheduling
  ([`shift-scheduling.md`](../scheduling/shift-scheduling.md) §4).
- **Fuso da unidade** — `Unit.timezone` decidido e ainda inexistente; em que Stage entra é lacuna
  de escopo do roadmap ([ADR 4.1.0005](../../adr/4_1_0005-unit-timezone-owned-by-identity.md);
  `roadmap.md` §Step 4 › nota 2026-09-14, item (a)).
- **Distinguir a causa da revogação** — logout reapresentado conta como reuso porque a sessão não
  guarda causa nem linhagem; distinguir exige campo novo (concept 2.4 §5 regra 6).
- **Link perdido sem e-mail** — para quem não tem e-mail, link em mãos perdido ou vencido é beco sem
  saída declarado; o reenvio seguro depende de identity distinguir conta pendente de ativa
  ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md),
  §Negative).
- **Conta órfã de identity** quando a gravação de staff falha depois de provisionar o login —
  janela declarada; a recuperação depende de "vincular login existente"
  ([ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
  §2; issue #107).
- **Trilha de auditoria das alterações de acesso** — o `overview.md` §3 ("RBAC") a lista no escopo
  da fundação; nenhum ADR ou Stage de identity a modelou.
- **Guarda de acesso fora do composition root** — expor autenticação/autorização de identity por
  uma fachada de acesso — issue #47
  ([ADR 3.5.0001](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md) §5).
- **Agendamento do expurgo de sessões** e **recusa no boot de segredo de desenvolvimento** —
  escalados para o deploy (Step 6)
  ([ADR 2.3.0004](../../adr/2_3_0004-session-retention-and-purge.md) §Decision;
  [ADR 2.4.0004](../../adr/2_4_0004-security-adapter-parameters.md) §Decision).

---

## 6. Evoluções previstas (não-escopo v1)

Registradas para que o modelo v1 não as bloqueie:

- **Papel por unidade** — como atributo do vínculo, sem refazer a forma
  ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md); concept 2.1 §7).
- **Auto-cadastro do dono e cobrança** — Step 13; tende a tornar a rota de plataforma secundária
  (issue #114, §Incerteza).
- **Introspecção do access token por requisição** — a sessão já viaja nas claims para que ela entre
  sem remodelar o port (concept 2.4 §5 regra 13).
- **Assinatura assimétrica do access token** e **verificador separado do emissor** — quando surgir
  um segundo verificador
  ([ADR 2.4.0004](../../adr/2_4_0004-security-adapter-parameters.md);
  [ADR 2.4.0002](../../adr/2_4_0002-decode-extends-token-issuer.md)).
- **Ports assíncronos** — só com necessidade medida; migração mecânica e localizada
  ([ADR 2.2.0004](../../adr/2_2_0004-synchronous-port-signatures.md) §Decision).

---

## 7. Registro da consolidação (2026-11-02)

**Decisão de status.** Este doc nasce `accepted` sem rodada própria de ratificação: ele só consolida
regras que ADRs `accepted` e concepts de Stages `done` já decidiram, e o sponsor delegou ao
orquestrador as decisões de produto da issue #30. Nenhuma regra sem fonte entrou; o que faltava
virou lacuna (§5).

**Achados — contradições e desatualizações nas fontes** (registrados na issue #30, não corrigidos
aqui, porque o texto de ADR e de concept não se edita por este doc):

- **C1 — numeração das decisões de kickoff diverge entre as fontes.** O concept 2.1 cita "kickoff
  #4" para "papel fixo → conjunto de permissões" (§7) e o concept 2.2 cita "kickoff #1" para o
  refresh persistido; o registro do kickoff na memória do projeto numera o refresh como #4 e o
  vínculo como #1, e é essa numeração que `workforce.md`, `shift-scheduling.md` e o ADR 3.5.0003
  (#13) seguem. A lista do kickoff não vive no repositório, então o número não é âncora estável.
  Este doc não cita kickoff por número; cita o concept ou o ADR que registrou a decisão.
- **C2 — comentário do mapa de papéis desatualizado.** `role.py` diz que a Stage 4.x "não pode
  conceder a `hr` nenhuma permissão sobre a escala" (ADR 3.4.0006 §3), restrição superada em parte
  pelo [ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md): `hr` recebe a
  leitura. É o arquivo que quem estender o mapa lê.
- **C3 — ADR 2.5.0003 justifica a ordem pela ausência de transação, que deixou de ser verdade.** O
  §Decision diz que não há unidade de trabalho cobrindo as quatro escritas; desde o
  [ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md)
  §1 há, e a troca foi declarada no código (falha parcial agora desfaz também a revogação; a ordem
  ficou redundante, não errada — docstring de `set_password_with_token.py`), mas o ADR 2.5.0003 não
  ganhou nota de supersessão parcial. A regra (definir senha revoga sessões e tokens) continua
  valendo.
- **C4 — a fachada de identity ainda aponta para a #49** como a razão de não autorizar, quando a
  decisão vigente é o ADR 0.0.0014 §4 / issue #115 — já rastreado pela issue #77.

---

## 8. Referências

### Âncoras internas (fontes ratificadas — passo 1 da barra de fontes)

- [`overview.md`](../../overview.md) — §3 Escopo ("Fundação SaaS multi-tenant", "RBAC", login
  opcional), §9 Glossário ("Tenant", "Função"), §10 Referências (fontes de segurança e
  multi-tenancy da borda, consumidas pelo ADR 0.0.0005).
- [`roadmap.md`](../../roadmap.md) — §Step 2 (Stages 2.1–2.6), §"Premissas adotadas no Roadmap"
  (ROADMAP-3 tenancy row-level, ROADMAP-4 JWT + argon2), §Step 4 › nota 2026-09-14 (lacuna do fuso).
- Concepts das Stages `done` de identity: `docs/stages/2.1-identity-domain/concept.md` §5, §7;
  `docs/stages/2.2-identity-application/concept.md` §5; `docs/stages/2.4-identity-http/concept.md`
  §5; `docs/stages/2.5-email-invite/concept.md` §5.
- [`workforce.md`](../staff/workforce.md) — §3.8 (fronteira staff↔identity), §4 (RBAC no staff).
- [`shift-scheduling.md`](../scheduling/shift-scheduling.md) — §3.10.2 (fronteira com identity),
  §4 (RBAC na escala).
- [ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md) — contrato da
  categoria `domain/` que este doc instancia.
- [ADR 0.0.0005](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md) — o
  tenant vem do token, salvo quando o BC é dono do recurso (§3.4).
- [ADR 0.0.0014](../../adr/0_0_0014-restaurant-provisioning-creates-its-owner-in-one-unit.md) —
  restaurante e dono provisionados numa unidade de trabalho; duas rotas emitem `owner` (§3.5).
- [ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) — três agregados,
  vínculo mínimo, dois eixos (§3.1–§3.3).
- [ADR 2.1.0002](../../adr/2_1_0002-platform-admin-without-tenant.md) — `platform_admin` sem
  tenant (§3.1).
- [ADR 2.2.0001](../../adr/2_2_0001-revocable-refresh-session-port.md) — sessão revogável por
  impressão, busca não filtrante (§3.6).
- [ADR 2.2.0002](../../adr/2_2_0002-authorization-two-axes-fail-closed.md) — ordem normativa da
  autorização, falha fechada (§3.4).
- [ADR 2.2.0003](../../adr/2_2_0003-application-errors-in-identity-hierarchy.md) — `superseded`
  pelo ADR 3.9.0001; citado só como antecessor (§3.2).
- [ADR 2.2.0004](../../adr/2_2_0004-synchronous-port-signatures.md) — ports síncronos (§6).
- [ADR 2.3.0001](../../adr/2_3_0001-integration-tests-require-real-postgres.md) — técnico
  (integração contra Postgres real); listado para completar o inventário de ADRs de identity, sem
  regra de domínio.
- [ADR 2.3.0002](../../adr/2_3_0002-identity-schema-tenant-and-constraints.md) — vínculo entre
  tenants irrepresentável; sessão sem tenant próprio (§3.1).
- [ADR 2.3.0003](../../adr/2_3_0003-add-is-insertion-not-upsert.md) — inserir não é sobrescrever
  (§3.8).
- [ADR 2.3.0004](../../adr/2_3_0004-session-retention-and-purge.md) — expurgo de sessões
  expiradas (§3.6).
- [ADR 2.3.0005](../../adr/2_3_0005-names-persisted-verbatim.md) — nomes verbatim (§3.1).
- [ADR 2.4.0001](../../adr/2_4_0001-http-error-status-mapping.md) — respostas que não viram
  oráculo; unicidade global de e-mail como sinal aceito (§3.4).
- [ADR 2.4.0002](../../adr/2_4_0002-decode-extends-token-issuer.md) — emissor e verificador no
  mesmo port (§6).
- [ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) — composição na
  borda, "não se concede o que não se detém", nenhuma rota emite `platform_admin` (§3.4, §3.5).
- [ADR 2.4.0004](../../adr/2_4_0004-security-adapter-parameters.md) — argon2id, JWT HS256, refresh
  de 256 bits; fontes OWASP no `## References` (§3.6).
- [ADR 2.5.0001](../../adr/2_5_0001-email-sender-in-shared.md) — port de e-mail compartilhado
  (§3.7).
- [ADR 2.5.0002](../../adr/2_5_0002-dedicated-single-use-setup-token.md) — token de setup dedicado,
  de uso único, por propósito (§3.7).
- [ADR 2.5.0003](../../adr/2_5_0003-password-change-revokes-sessions.md) — definir senha revoga
  sessões e tokens (§3.7; achado C3).
- [ADR 2.5.0004](../../adr/2_5_0004-unusable-hash-for-pending-accounts.md) — hash inutilizável na
  conta pendente (§3.7).
- [ADR 2.6.0001](../../adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md) — unidade
  de trabalho de identity (§3.8).
- [ADR 2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md) —
  escopo da unidade, sem transação entre BCs, e-mail depois do commit, rotação perdida é reuso
  (§3.6, §3.8).
- [ADR 3.4.0001](../../adr/3_4_0001-staff-owned-access-guard-port.md) — guarda de acesso de staff
  sobre a autorização de identity (§3.9).
- [ADR 3.4.0006](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md) — permissões de
  staff; hr ≡ manager no staff (§3.2).
- [ADR 3.4.0008](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md) —
  permissões tenant-wide (§3.4).
- [ADR 3.5.0001](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md) — fachada de identity
  (§3.9).
- [ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md) —
  conta pendente e link entregue em mãos (§3.5, §3.7).
- [ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md) — a conta
  permanece; desativação adiada com gatilho (§3.6, §5).
- [ADR 3.7.0001](../../adr/3_7_0001-every-staff-use-case-authorizes-its-own-target.md) — staff
  autoriza dentro do use case; identity não (§3.4).
- [ADR 3.8.0001](../../adr/3_8_0001-termination-revokes-only-access-the-record-grants.md) — o
  desligamento revoga só o acesso que o registro concede (§3.9).
- [ADR 3.9.0001](../../adr/3_9_0001-error-roots-by-meaning-status-by-map.md) — negação de acesso e
  unicidade global de e-mail são erros de domínio (§3.2, §3.6).
- [ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md) — famílias de permissão
  de escala; hr lê (§3.2).
- [ADR 4.1.0005](../../adr/4_1_0005-unit-timezone-owned-by-identity.md) — fuso da unidade em
  identity (§3.9, §5).

### Fontes primárias externas

Nenhuma fonte nova entrou neste doc. As fontes primárias de segurança (OWASP Password Storage e
JSON Web Token Cheat Sheets, RFC 8725, RFC 6819, RFC 6750) e de multi-tenancy da borda (Hardy,
OWASP API1:2023, OWASP ASVS, Azure, AWS, Auth0) vivem no `## References` dos ADRs 2.4.0001, 2.4.0004 e
0.0.0005, e em `overview.md` §10 — citadas por ponteiro, não copiadas.

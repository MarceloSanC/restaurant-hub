---
title: Domínio staff/workforce — equipe da unidade (teoria canônica)
description: Camada teórica do subdomínio workforce do BC staff — fundamentos, língua ubíqua, regras canônicas e invariantes de funcionário, função, jornada, preferência, indisponibilidade, cópia entre unidades e fronteira com identity
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 3 (3.1–3.5) ou de qualquer Stage futura que toque o BC staff; é a base que os concepts consomem em vez de re-derivar
keywords: [domain, staff, workforce, funcionario, funcao, jornada, sob-demanda, intermitente, preferencia-turno, indisponibilidade, copia-unidade, identity-gateway, lingua-ubiqua, ciclo-de-vida, desligamento, recontratacao]
status: accepted
created_at: 2026-07-23
updated_at: 2026-10-19
bounded_context: staff
subdomain: workforce
references:
  - ../../adr/3_1_0001-workforce-gate-modeling-decisions.md
  - ../../adr/3_2_0005-job-function-has-no-lifecycle-state.md
  - ../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md
  - ../../adr/3_2_0007-terminated-employee-remains-editable.md
  - ../../adr/2_1_0001-identity-aggregates-and-membership.md
  - ../../adr/2_3_0005-names-persisted-verbatim.md
  - ../../adr/2_5_0002-dedicated-single-use-setup-token.md
  - ../../adr/2_5_0004-unusable-hash-for-pending-accounts.md
---

# Domínio staff/workforce — equipe da unidade

> **Camada teórica** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este doc fixa o *o quê* e o *porquê* do subdomínio — conceitos, regras canônicas, invariantes e
> língua ubíqua. **Não é spec de implementação**: schemas, tabelas, endpoints e edge cases vivem no
> `technical.md` + código de cada Stage. Onde os insumos ratificados não fixam uma regra, o ponto é
> registrado como **lacuna para o concept da Stage** — nunca decidido aqui.

---

## 1. Propósito e escopo

O subdomínio **workforce** cobre a teoria da **equipe da unidade** de um restaurante (tenant):

- o **registro de funcionário** por unidade, seu **ciclo de vida** (desligamento, recontratação e
  remoção definitiva) e sua relação com a **pessoa** (login/User de identity);
- a **função de trabalho** customizável por restaurante;
- o **perfil de jornada** (fixa × sob demanda) e a **carga semanal contratada**;
- a **preferência de turno** por períodos nomeados do dia;
- os períodos de **indisponibilidade**;
- a **cópia de funcionário entre unidades** do mesmo restaurante;
- a **fronteira com identity** (login opcional criado pelo gerente).

É a base que os `concept.md` das Stages 3.1–3.5 consomem — e que os Steps 4 (scheduling) e 5
(auto-preenchimento) leem como insumo (a carga contratada, a preferência e a indisponibilidade são
os dados que a escala valida e a justiça distributiva persegue).

**Fora do escopo deste subdomínio** (fronteiras negativas ratificadas):

- **Escala, demanda, vaga, alocação** — pertencem ao BC `scheduling` (Step 4). Roadmap 3.2
  `non_goals` ("noção de escala/demanda é Step 4").
- **Dinheiro / folha / valorização de horas** — fora da v1 do produto inteiro. Overview §3 "Fora do
  escopo"; kickoff #11.
- **Regras trabalhistas como validação** (descanso entre jornadas, tetos de horas, antecedência de
  convocação) — são **validações configuráveis por restaurante** no domínio de scheduling
  (Stage 4.2); a teoria correspondente pertence ao doc de domínio do gate do Step 4. Overview §6.
  O staff sustenta os **dados** que essas validações leem (carga, indisponibilidade), não o
  comportamento.
- **Funcionário consultando a própria escala** — Step 4. Roadmap 3.5 `non_goals`.

---

## 2. Língua ubíqua

Termos ratificados por pesquisa de mercado (overview §9 Glossário; fontes setoriais de §10 —
válidas para **nome**, não para regra) e pelas decisões de kickoff:

| Termo | Definição |
|---|---|
| **Funcionário** (registro) | Cadastro de uma pessoa como membro da equipe de **uma unidade**. É o objeto que o staff gerencia; distinto da **pessoa** (ver §3.1). |
| **Função** | Papel de **trabalho** (cozinheiro, atendente, faxineiro...), **100% customizável por restaurante** — nada pré-determinado. A demanda da escala (Step 4) é definida por função. Overview §3, §9. |
| **Papel** (de acesso) | Conceito de **identity**, não de staff: conjunto **fechado e fixo** de 5 papéis RBAC (dono, gerente, RH, funcionário, admin de plataforma). **Função ≠ Papel**: função é trabalho e é customizável; papel é acesso e é fixo. Overview §3 (RBAC), §9. |
| **Jornada fixa** | Perfil de carga com **carga horária semanal contratada** (determinada). Overview §3, §9; kickoff #5. |
| **Sob demanda** | Perfil de carga de quem atua **quando acionado** — extra, gerente, dono. Overview §3, §9. |
| **Intermitente** | Designa **apenas o contrato CLT específico** (art. 443 §3º). **"Sob demanda" ≠ "intermitente"** — ver §3.4. Overview §9. |
| **Extra** | Pessoa sob demanda acionada para cobrir turno / reforçar a equipe (freelancer de diária — termo consagrado no setor). Overview §9. |
| **Turno** | Faixa de horário demandada/trabalhada num dia (ex.: 16h–00h). Conceito consumido aqui só como *preferência nomeada*; a faixa concreta pertence a scheduling. Overview §9. |
| **Períodos nomeados do dia** | manhã / tarde / noite / madrugada — o vocabulário da preferência de turno. Kickoff #6. |
| **Setor** | Área da operação (cozinha, salão, bar, caixa...); preferido a "praça". Termo **ratificado no glossário, mas fora da v1 do staff** — nenhuma feature o exige (ver §5). Overview §9. |
| **Indisponibilidade** | Período em que o funcionário não pode ser escalado (férias, atestados na v1). Overview §3. |
| **Demanda / Vaga** | Necessidade de N pessoas de uma função num turno de um dia — **pertence a scheduling**; listado aqui só para delimitar a fronteira. Overview §9. |
| **Tenant** | Um restaurante cliente da plataforma, isolado dos demais; unidades pertencem ao tenant. Overview §9. |

---

## 3. Conceitos e regras canônicas

### 3.1 Pessoa × registro de funcionário

**Regra canônica:** o **registro de funcionário é por unidade**; a **pessoa (login/User) é global**.

- O e-mail/User é único e global na plataforma (kickoff #2); o registro de
  funcionário existe no escopo de **uma unidade** de um tenant.
- **Unidades não compartilham funcionários** — não se enxergam; o cadastro pode ser **copiado**
  para outra unidade (ver §3.7). Overview §3.
- A **mesma pessoa pode ter vários registros de funcionário** (um por unidade), todos apontando
  para o **mesmo User** — compatível com o vínculo user↔unidade n:n `UnitMembership`
  ([ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md));
  [ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md) (decisão iii).
- O vínculo do registro com um login (`user_id`) é **opcional** e é uma **decisão explícita por
  registro** (ver §3.8). Overview §3; roadmap 3.5.
- Staff persiste sob isolamento **row-level por `tenant_id`** num único Postgres (ROADMAP-3) —
  invariante de tenancy herdado da fundação, não regra própria deste subdomínio.

**Invariantes:**
- Um registro de funcionário pertence a exatamente **uma unidade** de exatamente **um tenant**.
- Nenhuma operação de staff atravessa unidades implicitamente — só a cópia explícita (§3.7).

**Ciclo de vida do registro** (decidido pelo **sponsor** na Stage 3.2 —
[ADR 3.2.0006](../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md) e
[ADR 3.2.0007](../../adr/3_2_0007-terminated-employee-remains-editable.md); 2026-08-08/09):

- O registro carrega um **estado ativo × inativo**, com duas transições explícitas —
  **desligamento** (sai da equipe) e **recontratação** (volta). Ambas são **idempotentes no
  valor**: repetir a transição já vigente não é erro.
- **O desligado não é inerte:** desligar **retira o registro da listagem da unidade por
  default** (a listagem só o devolve sob pedido explícito de incluir inativos). Sem esse estado,
  quem saiu continuaria aparecendo no seletor de escala do Step 4 e seria escalável.
- **O histórico sobrevive ao desligamento** — o registro continua legível por id, continua
  referenciando suas funções e **continua bloqueando a remoção delas** (§3.2). É o que o hub de
  análise lê (previsto × realizado por unidade).
- **A remoção definitiva existe e é guardada**, para o cadastro criado por engano: só é aceita
  na ausência de referências ao registro. Desligamento e remoção são atos **distintos** — um
  preserva a história, o outro a apaga.
- **O desligado permanece editável, e nenhuma edição o reativa** (ADR 3.2.0007): corrigir o
  cadastro de quem saiu não é o mesmo ato que recontratá-lo, e o sistema não obriga um para
  conseguir o outro. A reativação é **explícita** e só acontece pela transição de recontratação.

> **Nota (2026-09-14) — gate do Step 4:** o registro **desligado some de todas as telas de escala**
> (escala vigente, calendário, "minha escala", escalas anteriores, imagem, e-mail) — inclusive as
> suas alocações passadas. Nada é escrito em scheduling no desligamento: staff só marca o estado, e
> toda leitura de scheduling **reconcilia na leitura** consultando o estado atual do registro. O
> histórico continua no banco ("o histórico sobrevive" vale para os dados) e volta a ser visível
> com a **página de histórico de funcionários** (evolução prevista). A guarda de remoção definitiva
> é mantida por um port de consulta reverso, sem foreign key entre BCs. Decisão do sponsor —
> [ADR 4.1.0006](../../adr/4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md);
> teoria em `docs/domain/scheduling/shift-scheduling.md` §3.4.

**Invariantes:**
- Todo registro está em exatamente um dos dois estados; nasce **ativo**.
- Nenhuma operação de edição do registro altera o estado — só as duas transições o alteram.
- Remoção definitiva é recusada enquanto houver referência ao registro.

> **Lacuna para o concept da Stage 3.1:** os **atributos cadastrais mínimos** do registro
> (nome, contato, o que identifica o registro dentro da unidade) não estão enumerados em nenhuma
> fonte ratificada — o concept da 3.1 os fixa. Vale a regra transversal de dados livres persistidos
> **verbatim**, sem normalização silenciosa ([ADR 2.3.0005](../../adr/2_3_0005-names-persisted-verbatim.md)).

### 3.2 Função de trabalho (JobFunction)

**O que é:** o papel de trabalho que o restaurante define para sua operação. **Nada é
pré-determinado** — o gerente cria as funções que a operação dele usa. Overview §3, §9.

**Regras canônicas:**
- **Escopo: o restaurante (tenant), não a unidade.** Overview §3 ("customizável por
  restaurante"). Consequência estrutural: a cópia de funcionário entre unidades (§3.7)
  permanece coerente — a função referenciada existe na unidade destino sem recriação.
- **Atributos mínimos:** nome. A "parametrização" de função citada no
  overview §3 (demanda por função × faixa) é definição da demanda da escala e pertence a
  **scheduling**, não a staff.
- **Nome único no restaurante, persistido verbatim** — sem normalização silenciosa (trim/case
  aplicados às escondidas); a unicidade é sobre o valor tal como o usuário digitou
  ([ADR 2.3.0005](../../adr/2_3_0005-names-persisted-verbatim.md)).
- **Setor NÃO é atributo da função na v1** — termo ratificado no glossário sem feature que o
  exija (overview §9; ver §5).

**Ciclo de vida:** a função **não tem estado** — nem ativo/inativo, nem transições de
ativação/desativação. Função que ninguém usa é **inerte** e simplesmente permanece no catálogo;
quem não a quer mais **a remove**. A **remoção é o único caminho de saída** e é **guardada**:
recusada enquanto **qualquer** funcionário do tenant a referenciar — **inclusive um funcionário
desligado** (§3.1), porque o registro dele sobrevive ao desligamento.

**Invariantes:**
- Nome de função é único dentro do tenant (comparação verbatim).
- A função não carrega estado de ciclo de vida.
- Remoção de função referenciada por qualquer funcionário do tenant (ativo ou desligado) é
  recusada.

> **Lacuna fechada (2026-08-09) —
> [ADR 3.2.0005](../../adr/3_2_0005-job-function-has-no-lifecycle-state.md):** o **ciclo de vida
> da função** era lacuna aberta deste doc ("há alternativa real: soft-state × hard-delete") e foi
> fechado **duas vezes**, em direções opostas. A Stage 3.1 a fechou com estado soft
> ativo/inativo ([ADR 3.1.0003](../../adr/3_1_0003-job-function-lifecycle-soft-state.md)); a
> Stage 3.2 — a que pagaria a conta desse estado — devolveu a questão ao **sponsor**, que
> decidiu em 2026-08-08 pela **ausência de ciclo de vida** (regra canônica acima). O ADR 3.2.0005
> **supersede** o 3.1.0003, cujo corpo fica preservado como registro histórico
> (`status: superseded`). A **remoção guardada** é a única parte do 3.1.0003 que sobreviveu, com
> racional próprio restated no 3.2.0005.

### 3.3 Perfil de jornada: fixa × sob demanda

**Regra canônica:** todo funcionário tem exatamente **um perfil de jornada**, de dois tipos
(overview §3, §9; roadmap 3.1):

**(a) Jornada fixa** — carga horária determinada.

- A carga é **UMA carga semanal contratada, em horas** (número positivo) por funcionário.
  Kickoff #5; [ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md) (decisão ii).
- **Semântica única do número** (ADR 3.1.0001, decisão ii): o mesmo valor é lido de duas formas por consumidores
  distintos —
  1. **base da validação de carga** configurável do restaurante (Stage 4.2, `workload_policy`);
  2. **alvo de justiça distributiva** do auto-preenchimento (Step 5).
- O **teto de horas NÃO é dado do staff**: é política de validação configurável do restaurante
  (Stage 4.2, `max_hours_policy` — política **distinta** da de carga). Staff guarda a carga
  contratada; scheduling configura o teto (ADR 3.1.0001, decisão ii).

**(b) Sob demanda** — atuação quando acionado; cobre **extra, gerente e dono** que entram na
operação. Overview §3, §9.

- A atuação de quem é sob demanda classifica-se **apenas** como **"conta ou não para a carga
  contratada"** — uma classificação, **sem valor monetário** (fora da v1; ver §5). Kickoff #11;
  overview §3 "Fora do escopo". Decisão já resolvida no kickoff — este doc a honra, não a reabre.

> **Nota (2026-09-13) — gate do Step 4:** a classificação "conta ou não para a carga contratada"
> é atributo da **alocação** (Step 4), declarada pelo editor, com default "conta" — não da
> atuação do sob demanda em si. Ela existe na alocação de qualquer perfil, mas só a política de
> carga do **jornada fixa** a lê; o sob demanda **não tem carga** (invariante abaixo), logo para
> ele a marca não tem efeito de validação. Decisão do sponsor —
> [ADR 4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (d);
> teoria em `docs/domain/scheduling/shift-scheduling.md` §3.4.

**Invariantes:**
- Perfil de jornada é exclusivo: fixa **ou** sob demanda, nunca ambos, nunca nenhum.
- Jornada fixa exige carga semanal contratada > 0 (horas).
- Perfil sob demanda **não** carrega carga contratada nem valor monetário.

> **Lacuna para o concept da Stage 3.1:** as fontes prendem a **preferência de turno** à jornada
> fixa (kickoff #5: "carga = horas/semana + preferência de turno"), mas o overview §3 lista a
> preferência junto do perfil de jornada em geral — se o funcionário **sob demanda** também declara
> preferência de turno não está fixado. O concept da 3.1 decide.

### 3.4 Fronteira terminológica — o contrato intermitente da CLT

**O produto NÃO modela o contrato legal de trabalho intermitente.** Os perfis de jornada do §3.3
são **operacionais** (como a pessoa atua na escala), não jurídicos (que contrato ela assinou). O
glossário separa de propósito: *"'Intermitente' designa apenas o contrato CLT específico"*
(overview §9).

A fronteira, com a fonte primária verificada (Planalto, 2026-07-23):

- **CLT, art. 443, § 3º** (incluído pela Lei nº 13.467/2017): *"Considera-se como intermitente o
  contrato de trabalho no qual a prestação de serviços, com subordinação, não é contínua, ocorrendo
  com alternância de períodos de prestação de serviços e de inatividade, determinados em horas, dias
  ou meses, independentemente do tipo de atividade do empregado e do empregador, exceto para os
  aeronautas, regidos por legislação própria."*
- **CLT, art. 452-A** (incluído pela Lei nº 13.467/2017): o contrato intermitente é **escrito, com
  valor da hora**; a convocação exige pelo menos **três dias corridos** de antecedência (§ 1º —
  corridos, não úteis); o empregado responde em **um dia útil**, e o silêncio presume recusa (§ 2º);
  o período de inatividade **não** é tempo à disposição (§ 5º).
- A **MP 808/2017 caducou** em 23/04/2018 (Ato Declaratório CN nº 22/2018): suas redações
  alternativas (ex.: resposta em 24h; arts. 452-B a 452-H) **não vigem**. Redação vigente = Lei
  13.467/2017.

**Consequências para o domínio:**

- Um funcionário **sob demanda** no produto **pode ou não** ter contrato intermitente na vida real
  — o produto não sabe nem precisa saber na v1. Colar a base legal do intermitente sobre o perfil
  sob demanda seria um erro de modelagem — o glossário (overview §9) separa os dois vocabulários
  de propósito.
- Se o restaurante adota o contrato intermitente, as regras dele (ex.: antecedência de convocação
  do art. 452-A § 1º) entram como **validação configurável por restaurante** no scheduling
  (overview §6 — CLT não é hard-coded; a fonte sustenta o *default* e os limites, nunca
  comportamento imutável). A teoria dessas validações pertence ao **doc de domínio de scheduling**
  (gate do Step 4), não a este doc (overview §6).

### 3.5 Preferência de turno

**Regra canônica:** a preferência de turno do funcionário é expressa em **períodos nomeados do
dia** — **manhã, tarde, noite, madrugada**. Kickoff #6.

- **As fronteiras horárias dos períodos NÃO pertencem ao staff.** O BC staff guarda **só o período
  nomeado**; o mapeamento período → faixas de horário concretas é responsabilidade do
  **scheduling** (Step 4), onde vive a configuração por restaurante. Âncoras: roadmap 3.2
  `non_goals` ("noção de escala/demanda é Step 4"); overview §6 (configuração por restaurante vive
  em scheduling).
- Consumidores: o auto-preenchimento respeita a preferência (overview §3 — "respeita carga,
  preferência de turno e indisponibilidade").

**Invariante:**
- Preferência assume valores apenas do conjunto fechado {manhã, tarde, noite, madrugada}.

> **Lacuna para o concept da Stage 3.1:** a **cardinalidade** da preferência (um período por
> funcionário ou vários?) não está fixada em fonte ratificada — o concept decide.

### 3.6 Indisponibilidade

**O que é:** período em que o funcionário não pode ser escalado. Na v1 cobre **férias e
atestados** (overview §3) — casos absolutos, não recorrentes.

**Regras canônicas:**
- **Granularidade DATA-HORA** ([ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md),
  decisão i — sponsor, 2026-07-23): um período de
  indisponibilidade é um intervalo **instante-início → instante-fim**; **dia inteiro é caso
  particular** (00:00 → 00:00 do dia seguinte). Racional: é a forma geral que o Step 4 consome sem
  conversão (validação alocação × indisponibilidade) e atende ao critério de escalabilidade
  progressiva; a UI pode começar oferecendo só dias inteiros.
- **Invariante de não-sobreposição por funcionário** (roadmap, Stage 3.1 — descrição humana:
  "indisponibilidades não sobrepostas"): dois períodos de
  indisponibilidade do **mesmo funcionário** não se sobrepõem. **Definição de sobreposição:** os
  intervalos são **semi-abertos** `[início, fim)` — dois intervalos se sobrepõem sse
  `início_A < fim_B` **e** `início_B < fim_A`. Consequência: períodos **adjacentes** (fim de um ==
  início do outro) **não** se sobrepõem — terminar às 14:00 e começar às 14:00 é válido. Semântica
  semi-aberta ratificada no ADR 3.1.0001 (decisão i).
- **Interpretação temporal: no fuso da unidade.** O fuso é configurável por unidade (overview §6);
  os instantes de indisponibilidade de um funcionário são interpretados no fuso da unidade do seu
  registro.
- **Recorrência fora da v1**: o overview §3 delimita o caso de uso a períodos absolutos
  (férias, atestados); recorrência ("toda segunda de manhã") é **evolução aditiva** (ver §5) — o
  modelo de intervalo instante→instante não a bloqueia.

**Invariantes:**
- `início < fim` (intervalo não vazio).
- Períodos do mesmo funcionário não se sobrepõem (definição semi-aberta acima).

### 3.7 Cópia de funcionário entre unidades

**Regra canônica:** copiar um funcionário para outra unidade do mesmo restaurante **duplica o
registro** — não compartilha, não vincula, não vaza. Overview §3 ("o cadastro pode ser copiado
para outra unidade"); roadmap 3.2 (DoD: "cópia entre unidades duplica cadastro sem vazar dados
entre unidades").

- Após a cópia, os dois registros são **independentes**: alterar um não altera o outro.
- **A cópia NÃO carrega o `user_id`** — o vínculo com login é decisão explícita **por registro**
  (Stage 3.5); a mesma pessoa pode acabar com vários registros apontando para o mesmo User via
  vínculos explícitos, nunca por arrasto da cópia.
  [ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md) (decisão iii).
- As **funções tenant-scoped** (§3.2) tornam a cópia coerente: a função referenciada já existe no
  restaurante inteiro — não é preciso recriá-la na unidade destino (overview §3; ver §3.2).
- A cópia é sempre **dentro do mesmo tenant** (unidades do mesmo restaurante) — decorre do
  isolamento de tenant (§3.1); não existe cópia cross-tenant.

### 3.8 Fronteira com identity — login opcional do funcionário

O staff **consome** identity; a teoria de identity (agregados, membership, tokens) vive nos ADRs
do BC identity e **não é reescrita aqui** — este doc só fixa a fronteira.

**Regras canônicas:**
- **Login é opcional** e criado pelo gerente ("criar login para este funcionário"). Overview §3;
  roadmap 3.5.
- **Criar login significa**: criar User com papel **employee** no tenant + vínculo à unidade
  (membership) + gravar o `user_id` no registro de funcionário — via port `IdentityGateway`
  (in-process). O vínculo é escopo da **Stage 3.5**, não da 3.1. Roadmap 3.5;
  [ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) (membership;
  `link_to_unit` barra platform_admin e cross-tenant).
- **Dois caminhos, o gerente escolhe por funcionário**: (a) **convite por e-mail** ou (b) **senha
  provisória entregue em mãos, com troca obrigatória** no primeiro acesso. Overview §3; decisão
  derivada do kickoff.
- **Conta pendente de senha usa hash inutilizável** (`unusable_hash`, nunca hash de literal do
  repositório) e a senha só é definida via **token de setup dedicado e de uso único** — teoria em
  [ADR 2.5.0004](../../adr/2_5_0004-unusable-hash-for-pending-accounts.md) e
  [ADR 2.5.0002](../../adr/2_5_0002-dedicated-single-use-setup-token.md); referenciada, não
  duplicada.

> **Nota (2026-09-26): reconciliação pós-execução da Stage 3.5.** O que a Stage fixou onde as
> regras acima ainda falavam por antecipação:
>
> - **O caminho (b) não é "senha provisória com troca obrigatória": é o mesmo link de
>   definição de senha do convite, entregue em mãos** (impresso, QR, mensagem) com prazo
>   próprio e mais longo (`handover_link_ttl_hours`, 168h contra 72h do e-mail) — o gestor
>   nunca conhece nem transporta a senha da pessoa
>   ([ADR 3.5.0002](../../adr/3_5_0002-pending-account-and-setup-link-as-in-hand-credential.md)).
>   Link perdido é recuperado pelo pedido público de redefinição de senha, como qualquer convite.
> - **"Via port `IdentityGateway`" passou a ter forma:** identity expõe uma **fachada** in-process
>   e o gateway de staff a consome — a única aresta entre os dois bounded contexts, nomeada no
>   contrato de import ([ADR 3.5.0001](../../adr/3_5_0001-cross-bc-facade-and-gateway-edge.md)).
>   Criar o login exige **`manage_staff` e `manage_users`** sobre a unidade do registro.
> - **Desligar corta o acesso; remover recusa o vinculado.** O desligamento revoga as sessões
>   vivas do login **antes** de gravar; a conta continua existindo e continua podendo autenticar
>   (o que ela alcança é decisão da autorização). Um registro com login **não é removido** —
>   desliga-se primeiro; não há "desvincular" em v1
>   ([ADR 3.5.0003](../../adr/3_5_0003-termination-revokes-sessions-account-remains.md)).
> - **O `user_id` é coluna anulável e opaca** em `employees`, sem FK, `UNIQUE` ou índice; a
>   cópia entre unidades **não o carrega** (§3.7)
>   ([ADR 3.5.0004](../../adr/3_5_0004-user-id-as-nullable-opaque-column.md)).
>
> **Nota (2026-10-19): alcance do corte no desligamento (Stage 3.7).** O bullet "Desligar corta
> o acesso" acima vale quando o registro é o único ativo do login na unidade. Desde a Stage 3.7 o
> desligamento revoga as sessões **só quando o registro é a fonte do acesso**:
>
> - o registro desligado **estava ativo** (desligar de novo não derruba sessões abertas depois);
> - **nenhum outro registro ativo da mesma unidade** aponta para o login — se houver, é ele que
>   ainda concede o acesso. Só a unidade: a regra de §3.1 ("nenhuma operação de staff atravessa
>   unidades implicitamente") foi mantida literal, e a pessoa com registro em outra unidade loga
>   de novo;
> - o login é **de funcionário** — gerente ou dono vinculado a um registro de escala tira a
>   autoridade do papel, não do registro, e não perde as sessões.
>
> O desligamento **nunca** desativa a conta, nem quando a desativação de conta existir
> ([ADR 3.7.0001](../../adr/3_7_0001-termination-revokes-only-access-the-record-grants.md)).

---

## 4. Particularidades por caso de uso — visão RBAC

Quem faz o quê no staff (papéis de **acesso** de identity aplicados a este subdomínio):

| Papel | No subdomínio workforce |
|---|---|
| **dono (owner)** | Gerencia a equipe; visibilidade **bypassa** memberships (enxerga todas as unidades do tenant). ADR 2.1.0001 (eixo B); kickoff #9. |
| **gerente (manager)** | Gerencia a equipe das unidades das quais é membro (escopado às memberships). Roadmap 3.4 (RBAC "gerente/RH/dono da unidade"). |
| **RH (hr)** | Em identity, coincide com o gerente (mesmo MANAGE_USERS); **é NO STAFF que hr diverge do manager** — visibilidade e permissões de equipe são o único eixo de divergência. Kickoff #10; `src/restaurant_hub/features/identity/domain/value_objects/role.py` (manager e hr com o mesmo `MANAGE_USERS` em identity). *(Nota 2026-09-13: a divergência real é na **escala**, não no staff — dentro do staff hr ≡ manager ([ADR 3.4.0006](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md)); na escala, hr **lê** nas unidades de que é membro e não gerencia ([ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md)).)* |
| **funcionário (employee)** | Papel fixo, tenant-scoped, com **permissões vazias** — na v1 **não enxerga nada de staff**; o único caso de uso futuro é consultar a própria escala (Step 4, fora deste subdomínio — roadmap 3.5 `non_goals`). Âncoras das permissões vazias: `Role.EMPLOYEE: frozenset()` em `src/restaurant_hub/features/identity/domain/value_objects/role.py` (Stage 2.1, merged); mapeamento bronze do kickoff ("hoje só consulta"). |
| **admin de plataforma** | Fora do tenant; bypass de visibilidade é da fundação (ADR 2.1.0001), sem particularidade de staff. |

> **Lacuna para o concept da Stage 3.4:** o **detalhe da divergência hr × manager** (quais
> operações de staff cada um pode — hr vê tudo do tenant? só cadastro, sem jornada?) não está
> fixado em fonte ratificada além de "divergem na visibilidade e nas permissões de staff" — o
> concept da 3.4 fixa a matriz exata.

---

## 5. Evoluções previstas (não-escopo v1)

Registradas para que o modelo v1 não as bloqueie; **nenhuma entra sem revisão consciente** dos
documentos que as excluíram:

- **Recorrência de indisponibilidade** ("toda segunda de manhã") — evolução aditiva sobre o
  intervalo instante→instante. Overview §3; ADR 3.1.0001 (trade-off aceito).
- **Setor** como atributo (de função ou funcionário) — termo já ratificado no glossário
  (overview §9), sem feature que o exija na v1.
- **Papel-por-unidade** — o membership v1 é VO minimal sem papel por unidade (ADR 2.1.0001);
  refinamento futuro do RBAC.
- **Valor monetário do período extra** — a classificação "conta ou não para a carga" fica; dinheiro
  só entra com **revisão consciente do overview** (que hoje o exclui em §3 "Fora do escopo").
  Kickoff #11.

---

## 6. Registro das decisões do gate (2026-07-23)

Decisões tomadas no gate de domínio do Step 3, cada uma com sua âncora durável no repo:

**Com alternativa real descartada — registradas no
[ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md):**

- **(i)** Indisponibilidade em intervalos **data-hora** com semântica **semi-aberta** `[início, fim)`;
  dia inteiro é caso particular; adjacentes não conflitam (decisão do sponsor).
- **(ii)** **UMA** carga semanal contratada (horas) por funcionário de jornada fixa; o teto de horas é
  política de validação do scheduling (`max_hours_policy`, distinta de `workload_policy`).
- **(iii)** Cópia de funcionário entre unidades **não carrega** o vínculo `user_id`; vínculo é decisão
  explícita por registro (Stage 3.5).

**Derivações ancoradas (sem alternativa real — decididas pelos docs):**

- Fronteiras horárias dos períodos nomeados pertencem ao **scheduling** — roadmap 3.2 `non_goals`;
  overview §6.
- Função de trabalho com escopo de **tenant** — overview §3 ("customizável por restaurante").
- Atributos mínimos da função: nome verbatim único — ADR 2.3.0005; overview §3
  (parametrização é da demanda da escala). Ciclo de vida (ativo/inativo × remoção) era **lacuna**
  para o concept da 3.1/3.2 (§3.2) — **fechada em 2026-08-09** pelo
  [ADR 3.2.0005](../../adr/3_2_0005-job-function-has-no-lifecycle-state.md): a função **não tem
  estado**, e a remoção guardada é o único caminho de saída.
- Recorrência de indisponibilidade **fora da v1** — overview §3 (períodos absolutos: férias/atestados).
- Interpretação temporal no **fuso da unidade** — overview §6.
- CLT entra **só como fronteira terminológica**; teoria de validação trabalhista é do gate do Step 4 —
  overview §9 e §6.
- Período extra = **classificação sem dinheiro** — kickoff #11; overview §3 "Fora do escopo".
- Backfill do doc de domínio de **identity** — issue #30, sem bloquear o Step 3.

---

## 7. Referências

### Âncoras internas (fontes ratificadas — passo 1 da barra de fontes)

- [`overview.md`](../../overview.md) — §3 Escopo (equipe, login opcional, cópia, indisponibilidade,
  fora-do-escopo), §6 Restrições (CLT não hard-coded; fuso por unidade), §9 Glossário (língua
  ubíqua), §10 Referências (fontes setoriais de terminologia).
- [`roadmap.md`](../../roadmap.md) — bloco "Step 3 — Equipe da unidade", Stages 3.1–3.5
  (contratos, DoD, non_goals); ROADMAP-1 (BCs); ROADMAP-3 (tenancy row-level).
- [ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md) — contrato da
  categoria `domain/` que este doc instancia.
- [ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) — agregados de
  identity, `UnitMembership`, eixos de visibilidade.
- [ADR 2.3.0005](../../adr/2_3_0005-names-persisted-verbatim.md) — dados livres persistidos
  verbatim (nome de função).
- [ADR 2.5.0002](../../adr/2_5_0002-dedicated-single-use-setup-token.md) — token de setup dedicado
  e de uso único.
- [ADR 2.5.0004](../../adr/2_5_0004-unusable-hash-for-pending-accounts.md) — `unusable_hash` para
  conta pendente.
- Decisões de kickoff ratificadas (memória do projeto, 2026-07-16/19): #5 (carga fixa =
  horas/semana + preferência), #6 (períodos nomeados), #10 (hr = variante; diverge no staff), #11
  (extra sem dinheiro), derivada (dois caminhos de login).
- [ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md) — as três decisões de
  modelagem com alternativa real do gate de domínio do Step 3 (2026-07-23); as demais decisões do
  gate são derivações ancoradas — ver §6.
- [ADR 3.2.0005](../../adr/3_2_0005-job-function-has-no-lifecycle-state.md) — função de trabalho
  **sem** ciclo de vida; remoção guardada como único caminho de saída (§3.2). Supersede o
  [ADR 3.1.0003](../../adr/3_1_0003-job-function-lifecycle-soft-state.md) (`superseded`).
- [ADR 3.2.0006](../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md) — ciclo de vida do
  **registro de funcionário**: estado ativo/inativo com desligamento e recontratação, mais remoção
  definitiva guardada (§3.1).
- [ADR 3.2.0007](../../adr/3_2_0007-terminated-employee-remains-editable.md) — o registro desligado
  permanece editável e nenhuma edição o reativa (§3.1).

### Fontes primárias — legislação trabalhista (fronteira terminológica, §3.4)

> BRASIL. **Decreto-Lei nº 5.452, de 1º de maio de 1943** (Consolidação das Leis do Trabalho),
> arts. 443, *caput* e § 3º, e 452-A, com redação dada pela **Lei nº 13.467, de 13 de julho de 2017**
> (Reforma Trabalhista). Texto consolidado. Brasília: Presidência da República. Disponível em:
> https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em: 23 jul. 2026.
>
> BRASIL. **Lei nº 13.467, de 13 de julho de 2017**. Altera a Consolidação das Leis do Trabalho
> (CLT). Disponível em: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13467.htm.
> Acesso em: 23 jul. 2026.
>
> (Nota: a MP nº 808/2017, que alterava temporariamente o art. 452-A e criava os arts. 452-B a
> 452-H, teve vigência encerrada em 23/04/2018 — Ato Declaratório CN nº 22/2018 — e não integra o
> direito vigente.)

### Fontes setoriais (sustentam terminologia, não regra — overview §10)

Factorial HR, Shifton, Goomer, EPOC, GastronoMundo, Saipos, tio.digital, Fecomercio — listadas em
[`overview.md`](../../overview.md) §10 (pesquisa de terminologia, jul/2026).

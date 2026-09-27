---
title: Domínio scheduling/shift-scheduling — escala manual publicável (teoria canônica)
description: Camada teórica do subdomínio shift-scheduling do BC scheduling — fundamentos, língua ubíqua, regras canônicas, fórmulas e invariantes de escala, semana, dia operacional, faixa/turno, demanda, alocação, escala vigente (salvar = publicar), validações parametrizáveis (com defaults e limites ancorados em fonte primária), consulta, efeitos da publicação e fronteiras com staff, identity, timeclock e hub
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 4 (4.1–4.7) ou de qualquer Stage futura que toque a escala manual do BC scheduling; é a base que os concepts consomem em vez de re-derivar. O auto-preenchimento (Step 5) e o ponto (Step 7) têm docs de domínio próprios
keywords: [domain, scheduling, shift-scheduling, escala, semana, dia-operacional, horario-de-corte, faixa, turno, intervalo, demanda, vaga, alocacao, excecao-de-funcao, sobre-cobertura, reconciliacao-na-leitura, desligamento, escala-vigente, publicacao, auditoria, versao, concorrencia, validacao, block, warn, aceite-consciente, sobreposicao, interjornada, teto-de-horas, carga-contratada, conta-para-a-carga, indisponibilidade, calendario, minha-escala, notificacao, imagem, fuso-horario, clt, lingua-ubiqua]
status: accepted
created_at: 2026-09-13
updated_at: 2026-09-26
bounded_context: scheduling
subdomain: shift-scheduling
references:
  - ../staff/workforce.md
  - ../../adr/4_1_0001-every-saved-change-is-the-live-schedule.md
  - ../../adr/4_1_0002-weekly-period-operational-day-and-allocation-hours.md
  - ../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md
  - ../../adr/4_1_0004-hr-reads-schedules-in-member-units.md
  - ../../adr/4_1_0005-unit-timezone-owned-by-identity.md
  - ../../adr/4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md
  - ../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md
  - ../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md
  - ../../adr/2_2_0002-authorization-two-axes-fail-closed.md
  - ../../adr/2_5_0001-email-sender-in-shared.md
  - ../../adr/3_1_0001-workforce-gate-modeling-decisions.md
  - ../../adr/3_1_0002-minimal-employee-record-attributes.md
  - ../../adr/3_1_0004-shift-preference-scope-and-cardinality.md
  - ../../adr/3_1_0005-naive-wall-clock-unavailability-datetimes.md
  - ../../adr/3_1_0006-employee-function-set-cardinality.md
  - ../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md
  - ../../adr/3_3_0002-no-cross-bounded-context-foreign-keys.md
  - ../../adr/3_3_0006-transactional-atomicity-without-optimistic-locking.md
  - ../../adr/3_4_0001-staff-owned-access-guard-port.md
  - ../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md
  - ../../adr/3_4_0007-unit-enters-the-employee-address.md
  - ../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md
---

# Domínio scheduling/shift-scheduling — escala manual publicável

> **Camada teórica** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este doc fixa o *o quê* e o *porquê* do subdomínio — conceitos, regras canônicas com fórmula,
> invariantes e língua ubíqua. **Não é spec de implementação**: entidades, schemas, tabelas,
> endpoints, DTOs e edge cases vivem no `concept.md`/`technical.md` + código de cada Stage. Onde
> os insumos ratificados não fixam uma regra, o ponto é **lacuna para o concept da Stage**
> (consolidado em §6) — nunca decidido aqui. Onde havia mais de uma convenção legítima, a regra
> foi levada ao **sponsor**: as decisões de 2026-09-13 (F1–F6, F8), de 2026-09-14 (F7, remoção
> definitiva, F9) e de 2026-09-26 (F10, sobre-cobertura) estão aplicadas no corpo e registradas
> em §6 e nos ADRs 4.1.0001–4.1.0006.
> Nenhum `FORK` permanece aberto.
>
> **Regra trabalhista não vira comportamento fixo** (`overview.md` §6, linha 110): toda fonte
> legal citada abaixo sustenta o **default e os limites** de uma validação **configurável por
> restaurante** — nunca um comportamento hard-coded. A convenção coletiva (CCT) da base
> territorial de cada restaurante **não é embutida** no produto: o restaurante ajusta os
> parâmetros.
>
> `status: accepted` — gate de domínio do Step 4 (issue #52) cumprido. Revisão cética aplicada,
> decisões do sponsor incorporadas (2026-09-13, 2026-09-14 e 2026-09-26) e doc **ratificado pelo
> sponsor em 2026-09-14**, com a política de sobre-cobertura acrescentada em 2026-09-26.

---

## 1. Propósito e escopo

O subdomínio **shift-scheduling** cobre a teoria da **escala manual publicável** de uma unidade
de restaurante — o quadro que hoje vive em planilha e que o Step 4 aposenta (`roadmap.md`
linha 1178): a **escala** de uma unidade para uma **semana** de início configurável (§3.1); o
**dia operacional** e as **faixas/turnos** com intervalo declarado (§3.2); a **demanda por função
× faixa** (§3.3); a **alocação** com a classificação "conta para a carga" (§3.4); a **escala
vigente** — toda alteração salva é a escala que o funcionário vê — com auditoria e versão para
concorrência (§3.5); as **validações parametrizáveis** em modo `block`/`warn` com aceite
consciente (§3.6); a **consulta** (§3.7); os **efeitos da publicação** — e-mail e imagem (§3.8);
o **tempo** (§3.9); e as **fronteiras** com `staff`, `identity`, `timeclock` e `hub` (§3.10) — incluindo como o **desligamento** em staff
é reconciliado **na leitura** (§3.4). É a base que os `concept.md` das Stages 4.1–4.7 consomem.

**Fora do escopo deste subdomínio** (fronteiras negativas ratificadas):

- **Auto-preenchimento e justiça distributiva** — Step 5, subdomínio próprio do mesmo BC
  (`roadmap.md` 1270, 1322, 1758; ADR 0.0.0003 254–255). Este doc só fixa o que o Step 5
  **reutiliza** (§3.10.5).
- **Ponto / previsto × realizado** — Step 7 (BC `timeclock`); só o que a escala vigente
  **expõe** (§3.10.3). **Métricas do hub** — Step 8; só as **grandezas** nomeadas (§3.10.4).
- **Dinheiro / folha / valorização de horas extras / banco de horas formal** — fora da v1
  (`overview.md` 56; kickoff #11; `workforce.md` §3.3(b)).
- **Solicitação de troca de turno pelo funcionário** — fora da v1 (`overview.md` 57).
- **Cadastro do funcionário, função, jornada, preferência e indisponibilidade** — BC `staff`
  ([`workforce.md`](../staff/workforce.md)). Scheduling **lê** esses dados; não os define.

---

## 2. Língua ubíqua

Termos ratificados pelo glossário (`overview.md` §9, linhas 129–140 — fontes setoriais de §10,
válidas para **nome**, não para regra), pelo roadmap (Step 4), pelo `workforce.md` e pelas
decisões do sponsor de 2026-09-13. A **glosa EN** é o identificador que o roadmap 4.1/4.2 já
nomeia (`roadmap.md` 1259–1264, 1285–1290); onde não nomeia, a glosa é **proposta deste gate**
(†), como a glosa fixa `DayPeriod` de staff (`shift_preference.py` 18–24).

| Termo PT (código EN) | Definição | Âncora |
|---|---|---|
| **Escala** (`Schedule`) | Quadro de quem trabalha em quais dias/turnos, de **uma unidade**, para **uma semana**. | `overview.md` 129; unidade: derivação (§3.1) |
| **Período da escala** (`SchedulePeriod`) | Os 7 dias operacionais que uma escala cobre, a partir do **dia de início configurado**. Quinzena/mês são evolução. | `overview.md` 40, 129; `roadmap.md` 1252; sponsor 2026-09-13 (F2 — ADR 4.1.0002) |
| **Dia de início da semana** (`week start day` †) | Dia da semana, configurável por restaurante, em que começam o período da escala e a semana de apuração; fim = início + 6. | sponsor 2026-09-13 (F2) |
| **Horário de corte** (`day cutoff` †) | Hora do relógio, configurável por restaurante, em que começa o dia operacional; **default 05:00**. | sponsor 2026-09-13 (F2); racional do default: CLT art. 73 § 2º |
| **Dia operacional** (`operational day` †) | Janela de 24h a partir do horário de corte. Uma faixa pertence ao dia operacional em que **começa** — "sexta 18h–sábado 02h" é **um dia só** (sexta). Teto diário, semana de apuração e descanso entre jornadas usam o dia operacional, não o civil. | sponsor 2026-09-13 (F2) |
| **Semana de apuração** (`accounting week` †) | Os 7 dias operacionais a partir do dia de início, sobre os quais se somam horas para o teto semanal e a carga. Na v1 coincide com o período da escala; os conceitos ficam distintos para a evolução. | sponsor 2026-09-13 (F2) |
| **Faixa / turno** (`TimeRange`) | Faixa de horário demandada/trabalhada num dia (ex.: 16h–00h); semântica `[início, fim)`; pode cruzar a meia-noite e pertence ao **dia operacional em que começa**; carrega um **intervalo declarado**. Habilitada livremente pelo gerente, por dia. | `overview.md` 40, 130; `workforce.md` §2; semântica: ADR 3.1.0001 52–54 |
| **Faixas de funcionamento** | As faixas **habilitadas por dia** na escala — a expressão do overview ao descrever o calendário. Não é horário comercial da unidade (conceito inexistente no produto). | `overview.md` 45 ⇔ 40 ("habilitam-se faixas de horário livres") |
| **Intervalo declarado** (`break` †) | Minutos de intervalo dentro da faixa, declarados pelo editor; **default 0**. | sponsor 2026-09-13 (F3 — ADR 4.1.0002); CLT art. 71 § 2º |
| **Horas de uma alocação** (`hours(a)` †) | `duração nominal − intervalo declarado`. Regra **única** para políticas e hub. | sponsor 2026-09-13 (F3); `overview.md` 45 |
| **Demanda / vaga** (`ShiftDemand`, `DemandQuantity`) | Necessidade de **N** pessoas de **uma função** numa **faixa** de **um dia**; N ≥ 0. Uma **vaga** é uma unidade da demanda. | `overview.md` 133; `roadmap.md` 1252 |
| **Função** (`job_function_id`) | Papel de trabalho customizável por restaurante. **Conceito de staff**, consumido aqui **por id**. | `overview.md` 132; `workforce.md` §3.2 |
| **Alocação** (`Assignment`) | Ato de designar um **funcionário** (registro de staff, por id) para **uma vaga**. | `roadmap.md` 1252, 1259 |
| **Exceção de função** (`function_exception` †) | Marca **da alocação** gravada quando o editor aceita conscientemente alocar um registro numa demanda de função que ele **não detém** ("como um extra na escala"); visível na escala; **não altera o cadastro** em staff. | sponsor 2026-09-14 (F9 — ADR 4.1.0003 (f)) |
| **Reconciliação na leitura** (`reconcile on read` †) | Toda leitura de scheduling consulta o **estado atual** do registro em staff (via `StaffReadPort`); um registro **inativo** (desligado) não aparece em tela alguma — nem as suas alocações passadas — até a página de histórico de funcionários (evolução). Nada é escrito em scheduling no desligamento. | sponsor 2026-09-14 (F7 — ADR 4.1.0006) |
| **Conta para a carga** (`counts_toward_workload` †) | Classificação booleana **da alocação**, declarada pelo editor, **default "conta"**; "não conta" marca o período extra (sem dinheiro). Só a política de carga a lê. | sponsor 2026-09-13 (F4 (d) — ADR 4.1.0003); kickoff #11 |
| **Cobertura** (`coverage` †) | Alocados ÷ demandados; `< 100%` = **vaga descoberta**; `> 100%` = **alocação excedente** — ambos estados legítimos (§3.6.8). | `overview.md` 45; `roadmap.md` 1440, 1480 |
| **Escala vigente / publicar** (`publish`) | **Toda alteração salva é a escala vigente** — a que o funcionário, a imagem, o ponto e o hub veem. Sem rascunho no servidor, sem versão publicada separada. | `overview.md` 43, 136 (literal); sponsor 2026-09-13 (F1 — ADR 4.1.0001) |
| **Versão da escala** (`schedule version` †) | Contador que toda mutação incrementa; serve ao **controle otimista**. **Não** é foto imutável. | sponsor 2026-09-13 (F8 — ADR 4.1.0001) |
| **Trilha de auditoria** (`audit log` †) | **Quem alterou o quê e quando** — toda mutação gera entrada. É o **histórico** da escala. | `overview.md` 38; `roadmap.md` 1330, 1347 |
| **Política de validação** (`ValidationPolicy`) | Estratégia **plugável** de domínio que devolve **violações**; **parametrizável por restaurante**. | `overview.md` 42, 114; `roadmap.md` 1278, 1290 |
| **Configuração de validação** (`ValidationConfig`) | Por **restaurante (tenant)**: políticas habilitadas, parâmetros e **modo** de cada uma. | `roadmap.md` 1290, 1296, 1330 |
| **Violação** (`Violation`) | Resultado de uma política: política, sujeito (registro/alocação) e **modo**. | `roadmap.md` 1278, 1290 |
| **Modo `block` / `warn`** | `block`: **recusa a mutação** que a criaria. `warn`: aviso, salvo mediante **aceite consciente** no ato de salvar. | `overview.md` 42; `roadmap.md` 1278, 1294; forma sob F1: ADR 4.1.0001 |
| **Aceite consciente** (`acknowledge` †) | Ato **auditado** do editor que aceita um `warn` ao salvar. | `overview.md` 42, 38 |
| **Avaliação ao vivo** (`evaluate`) | Reavaliação das políticas **a cada mudança**, devolvendo violações para a UI. | `overview.md` 42; `roadmap.md` 1278, 1304 |
| **Calendário** (`get_calendar`) | Visão dia/semana/mês com mini-cards sobre as faixas habilitadas. **Read model de scheduling**, exibido na aba escala do hub. | `overview.md` 45; `roadmap.md` 1304, 1311, 1356 |
| **"Minha escala"** (`get_my_schedule`) | A escala vigente vista pelo funcionário logado: **só as próprias alocações**. | `overview.md` 43, 92; `roadmap.md` 1356 |
| **Escala anterior** (`list_past_schedules`) | Escala de período encerrado, **visualizável como referência**. | `overview.md` 46; `roadmap.md` 1217, 1311 |
| **Extra** | Pessoa sob demanda acionada para cobrir turno; na escala, uma **alocação de registro sob demanda**. | `overview.md` 135 |
| **Tenant / unidade** | Restaurante cliente, isolado; unidades pertencem ao tenant e **não se enxergam**. | `overview.md` 37, 140 |

---

## 3. Conceitos e regras canônicas

### 3.1 Escala: unidade, semana, identidade e ciclo

**Regra canônica:** a escala é o **quadro de quem trabalha em quais dias/turnos** de **uma
unidade** para **uma semana** cujo dia de início é configurável (`overview.md` 129; sponsor
2026-09-13).

- **Por unidade.** Nenhuma frase ratificada o diz literalmente, mas é a única leitura compatível
  com: unidades **não compartilham funcionários** e **não se enxergam** (`overview.md` 37); o
  registro de funcionário pertence a uma unidade (`workforce.md` §3.1); o hub agrega **por
  unidade** e na "Unidade Geral" (`overview.md` 45). Derivação (§6).
- **Período = semana com dia de início configurável** — decisão do sponsor, 2026-09-13
  ([ADR 4.1.0002](../../adr/4_1_0002-weekly-period-operational-day-and-allocation-hours.md)):
  *"incio e fim da semana sao configuraveis"*. O período é a sequência de **7 dias operacionais**
  (§3.2) a partir do dia de início configurado por restaurante (fim = início + 6); **default:
  segunda-feira** (derivação ancorada — ISO 8601 via `isoweekday()` e Decreto 10.854/2021
  art. 158 § 4º, §7). O overview
  ("período configurável, default semanal" — 40, 129) fica honrado: na v1 configura-se o **dia de
  início**; quinzena/mês são **evolução** que a forma "intervalo contíguo de dias operacionais"
  não bloqueia (§5).
- **Isolamento de tenant**: row-level `tenant_id` num único Postgres (ROADMAP-3, `roadmap.md`
  1727) — invariante herdado da fundação.
- **Identidade**: `(tenant, unidade, período)`. O roadmap lista `Schedule`, `ShiftDemand` e
  `Assignment` como entidades da 4.1 (`roadmap.md` 1264) sem nomear a raiz; que `Schedule` seja
  a **raiz do agregado** é proposta do gate (†), a confirmar na 4.1.
- **Ciclo**: criada para um período → editada (demanda, alocações) — e **cada edição salva já é
  a escala vigente** (§3.5). Não há estado de rascunho.
- **Escala anterior como referência** (`overview.md` 46; `roadmap.md` 1217). Visualizar ≠
  copiar: copiar como ponto de partida é evolução (§5).

**Invariantes:**
- O período é não vazio, contíguo e alinhado ao dia de início configurado (7 dias operacionais).
- Toda escala pertence a exatamente **uma unidade** de exatamente **um tenant**.
- **As escalas de uma mesma unidade não se sobrepõem no tempo** — derivação de "quadro de quem
  trabalha em quais dias" (`overview.md` 129): dois quadros para o mesmo dia tornariam a alocação
  ambígua. Proposta do gate (§6); com períodos alinhados ao dia de início, decorre da forma.
- Toda alocação está **dentro do período** da escala (`roadmap.md` 1252).

> **Lacuna para o concept da Stage 4.3:** o que acontece com escalas existentes quando o
> restaurante **muda o dia de início** (ou o horário de corte — §3.2): só períodos futuros? e um
> período em curso?

### 3.2 Dia operacional e faixa / turno por dia

**Regra canônica — dia operacional** (decisão do sponsor, 2026-09-13, ADR 4.1.0002): o dia da
escala é uma **janela de 24h que começa no horário de corte** configurável por restaurante.
Sponsor: *"horario de fim do dia pode ser configurado tambem (por exemplo, jornada até as 2h da
manha conta no mesmo dia anterior, começou sexta as 18h e acabou sabado as 2h conta como um dia
só)"*. **Default do corte: 05:00** (sponsor: *"05:00 (Recomendada)"*) — racional: fim do período
noturno da CLT (art. 73 § 2º: "entre as 22 horas de um dia e as 5 horas do dia seguinte"); é só o
default, sem força de regra.

- Uma faixa (e a alocação sobre ela) pertence ao **dia operacional em que começa**. Com corte
  05:00, sex 18h–sáb 02h é **um dia só: sexta** — para demanda, calendário, teto diário (§3.6.3)
  e ancoragem na semana de apuração (§3.6.4). O exemplo ratificado "qua = 1 cozinheiro 16h–00h"
  (`overview.md` 40) é compatível com qualquer corte ≤ 16h.
- Cruzar a meia-noite civil **não é caso especial** para sobreposição nem descanso — são
  comparações entre instantes (§3.9).

**Regra canônica — faixa:** a **faixa (turno)** é a faixa de horário demandada/trabalhada num
dia (`overview.md` 130). Por dia, o gerente **habilita faixas livres** — sem catálogo fixo
(`overview.md` 40); são as "faixas de funcionamento" do calendário (`overview.md` 45; §2). A faixa
concreta **pertence a scheduling**; staff só conhece os **períodos nomeados** (`workforce.md` §2,
§3.5).

- **Semântica semi-aberta `[início, fim)`** — a mesma da indisponibilidade de staff, ratificada
  pelo sponsor em 2026-07-23: half-open *"is what scheduling assumes when crossing unavailability
  with shifts (e.g. the glossary's 16h–00h shift)"* (ADR 3.1.0001 52–54; 93–94; `workforce.md`
  §3.6). Faixas **adjacentes** não se sobrepõem; o instante `fim` não é trabalhado.
- **Intervalo declarado** (sponsor, F3 — ADR 4.1.0002): minutos, **default 0**, declarado pelo
  editor; só a contagem de horas (§3.6.10) o lê na v1. Uma política de intrajornada (CLT art. 71)
  torna-se possível porque o intervalo existe — evolução (§3.6.9).
- **Mapa período nomeado → faixas concretas.** `workforce.md` §3.5 delega ao scheduling o
  mapeamento manhã/tarde/noite/madrugada → horas, "onde vive a configuração por restaurante". É
  configuração **sem default legal** (o noturno 22h–5h do art. 73 § 2º é definição para
  remuneração, não turno operacional). Nenhuma política 4.2 depende dele; o único consumidor
  ratificado é o Step 5.

> **Lacuna de escopo do roadmap (registrada; a mestra decide a Stage dona):** nenhum bloco 4.x
> (`roadmap.md` 1244–1428) lista o mapa período nomeado → faixas, embora `workforce.md` §3.5 o
> delegue ao "scheduling (Step 4)". Proposta: dona = a que primeiro o consumir (5.1).

**Invariantes:**
- `início < fim` (faixa não vazia); `0 ≤ intervalo < duração nominal` (alocação de zero horas
  não é trabalho — derivação da regra de contagem).
- Sobreposição segue **sempre** a definição semi-aberta:
  `A ∩ B ≠ ∅ ⇔ início_A < fim_B ∧ início_B < fim_A`.
- A faixa pertence ao **dia operacional** (no fuso da unidade) do seu `início`.

> **Lacuna para o concept da Stage 4.1:** (a) a **forma interna** do `TimeRange` — par de
> instantes wall-clock × `(dia, hora_início, hora_fim)` — desde que preserve as invariantes e a
> comparação direta com a indisponibilidade (ADR 3.1.0001 52–53; ADR 3.1.0005 44–46); (b) a
> **faixa que ultrapassa o corte seguinte** (ex.: 22h–06h com corte 05:00) — proibir, dividir, ou
> permitir e atribuir ao dia operacional de início.

### 3.3 Demanda por função × faixa

**Regra canônica:** a **demanda** é a necessidade de **N pessoas de uma função numa faixa de um
dia** (`overview.md` 133; `roadmap.md` 1252), definida **por função**; funções são 100%
customizáveis (`overview.md` 40, 132). A "parametrização de função" do overview §3 é **definição
da demanda** e pertence a scheduling (`workforce.md` §3.2).

- **Quantidade ≥ 0** (`roadmap.md` 1252). Demanda `0` = "faixa habilitada sem demanda dessa
  função" — estado válido.
- **Função referenciada por id** (string opaca), nunca por import (`roadmap.md` 1266;
  `.importlinter` 219–228; §3.10). Função é escopo do **tenant** (`workforce.md` §3.2): qualquer
  função pode ser demandada em qualquer unidade. Habilitação por unidade é a issue #41, não
  decidida (`roadmap.md` 766; ADR 3.4.0008 88–92).
- **Cobertura** = `alocados ÷ N`. Cobertura **< 100% é estado legítimo** da escala vigente
  ("vagas não preenchíveis", "vagas descobertas" — `roadmap.md` 1440, 1480; `overview.md` 45).
  **`N` é alvo, não teto:** cobertura **> 100%** também é legítima — a alocação excedente é
  permitida com aviso e aceite consciente (política de sobre-cobertura, §3.6.8; decisão do
  sponsor, 2026-09-26).
- **Remoção de função referenciada por demanda.** A guarda de staff conta **só referências de
  funcionário** (`workforce.md` §3.2); uma demanda **não** a protege hoje. O mecanismo decidido
  para a guarda de funcionário — port de consulta reverso em staff, implementado fora de staff
  sobre uma query de scheduling (ADR 4.1.0006) — **generaliza** para a função demandada
  (`JobFunctionInUseError`); em que Stage staff passa a consultá-lo é lacuna (§6).

**Invariantes:** `N ≥ 0`; uma demanda referencia exatamente **uma função** do tenant e **uma
faixa** de **um dia** do período.

> **Lacuna para o concept da Stage 4.1: cardinalidade** — no máximo uma demanda por
> `(dia, faixa, função)`, ou duas da mesma função em faixas parcialmente sobrepostas? (A
> **sobre-cobertura** deixou de ser lacuna: é política de validação — §3.6.8.)

### 3.4 Alocação

**Regra canônica:** a **alocação** designa um **funcionário** para **uma vaga** (`roadmap.md`
1213, 1220). Quem pode ser alocado é definido pelos dados de staff, lidos por id e por dados —
nunca por import (§3.10).

**Elegibilidade:**

1. **Registro ativo da unidade da escala.** Só **ativos** aparecem no seletor — e em qualquer
   outra leitura (reconciliação na leitura, abaixo); o desligado some (`workforce.md` §3.1;
   ADR 3.2.0006 40–41); recontratação explícita é o único caminho de volta (ADR 3.2.0007
   122–124).
2. **Mesma unidade.** "Unidades não compartilham funcionários" (`overview.md` 37); o endereço do
   funcionário é `(tenant, unidade, id)` e o lookup **exige** a unidade como lei do port
   (ADR 3.4.0007 57–64; `staff/application/ports/out/employee_repository.py` 38–41). Alocar
   registro de outra unidade é **erro estrutural**, não política.
3. **Função da demanda: detida, ou exceção de função aceita.** O registro "casa vagas de
   **qualquer** das suas funções" (ADR 3.1.0006 48–49, 83 — sponsor 2026-07-28); o conjunto é
   não-vazio justamente para o Step 4 não tratar "sem função" (ADR 3.1.0006 69–73). Alocar a uma
   demanda de função **não detida** não é recusa estrutural: é a política **"função não detida"**
   (§3.6.7) — decisão do sponsor, 2026-09-14 (F9 — ADR 4.1.0003 (f)): aviso, aceite consciente e
   alocação gravada como **exceção de função**, sem tocar o cadastro. O auto-fill (Step 5) nunca
   cria exceção.
4. **Dentro do período** da escala (`roadmap.md` 1252).
5. **Não sobre indisponibilidade** — bloqueio não parametrizável (§3.6.6).

**Classificação "conta para a carga contratada"** — decisão do sponsor, 2026-09-13 (F4 (d) —
[ADR 4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md)): **vive na
alocação**, é **declarada pelo editor**, **default "conta"**; "não conta" marca o período extra
(kickoff #11: "período extra como classificação … sem dinheiro"). Existe na alocação de
**qualquer perfil**, mas **só a política de carga (§3.6.5) a lê** — quem é sob demanda não tem
carga (`workforce.md` §3.3). Sem valor monetário (`overview.md` 56). `workforce.md` §3.3(b)
descrevia a classificação como "atuação de quem é sob demanda"; recebe nota datada **neste PR**.

**Alocação e ciclo de vida do funcionário (staff) — reconciliação na leitura.** Decisão do
sponsor, 2026-09-14 (F7 —
[ADR 4.1.0006](../../adr/4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md)):
*"nao deveria mudar um parametro no banco dizendo que aquela conta nao esta mais ativa, e em
qualquer proxima requisicao que envolver o dado, ja busca do banco com essa informacao atualizada
(assim como um refresh F5)"*. E, sobre o que aparece (sub-pergunta da remoção): *"Manter a guarda,
mas por enquanto o perfil ou qualquer informacao dele nao aparece mais em qualquer tela, no futuro
quando for prioridade criamos a pagina de consultar historico de funcionarios, que ai sim vai ser
possivel buscar as informacoes historicas daquela conta."* A regra de produto de 2026-09-13
("dados dele que estavam em escala … devem ser desativados … ficam os registros históricos")
realiza-se assim:

- **Staff só marca `active=False`** (transição já existente — ADR 3.2.0006). **Nenhuma escrita em
  scheduling** no desligamento: sem evento, sem despachante, sem outbox, sem port-gancho.
- **Toda leitura de scheduling consulta o estado atual do registro** via `StaffReadPort`
  (roadmap 4.3) e trata o registro inativo: ele **não aparece em tela alguma** — escala vigente,
  calendário, "minha escala", escalas anteriores, imagem (4.7), e-mail (4.6) — **nem as suas
  alocações passadas**. Os dados permanecem no banco (nada é apagado); a **página de histórico
  de funcionários** (evolução, §5) reabre o acesso a eles.
- **Limites declarados da v1** (registrados, não escondidos): (1) a demanda que o inativo cobria
  lê-se como **descoberta** — a gerente repõe; (2) previsto × realizado (Step 7), "escalas
  anteriores" e o hub (Step 8) **não** mostram inativos até a página de histórico — lacuna de
  escopo para os gates dos Steps 7/8; (3) o desligamento **não gera entrada de auditoria na
  escala** (a auditoria do ato é do staff); (4) a **recontratação** (ADR 3.2.0006) faz as
  alocações antigas — inclusive futuras — **reaparecerem**: limpar ou não as alocações futuras no
  momento do desligamento é lacuna do concept da 4.3 (o sponsor não pediu limpeza; default: não
  limpar); (5) a regra vale para **toda** leitura, presente e futura — custo por leitura,
  mitigável por consulta em lote ao `StaffReadPort` (lacuna 4.3/4.4).
- **Remoção definitiva — guarda L-E5 mantida** (`EmployeeInUseError`; "o Step 4 (alocação) é
  quem os preenche" — `docs/stages/3.2-staff-application/concept.md` 301–308; ADR 3.2.0006
  177–178): apagar só passa se **nenhuma** alocação — nem histórica — referenciar o registro.
  Mecanismo: **port de consulta reverso em staff** ("este registro é referenciado?"),
  implementado **fora de staff** por um adapter/tradutor sobre uma query de scheduling
  (`has_allocations_for(tenant, unidade, registro)`) — a forma do `AccessGuard`
  (ADR 3.4.0001, conforme revista pela issue #47: a localização exata do tradutor é do
  `technical.md` da 4.4, não deste doc); **sem foreign key** entre BCs (cumpre o Alt C do
  ADR 3.3.0002); generaliza
  para a função demandada (§3.3). Os ADRs 3.2.0006 e 3.4.0002, que assumiam uma FK, ganham
  errata **neste PR**.
- **Pesquisa de arquitetura (2026-09-13)**, pedida pelo sponsor para F7: as alternativas A
  (evento na mesma transação), B (evento de domínio in-process pós-commit — a **recomendada**
  pela pesquisa), C (port-gancho direto) e E (FK/trigger) foram **descartadas pelo sponsor** pela
  simplicidade da reconciliação na leitura ("como um refresh F5"); registro completo no
  ADR 4.1.0006.
- **"Conta desativada"**: a Stage 3.5 (`draft`, outra sessão) decidiu que o desligamento
  **revoga sessões e a conta permanece**; com F7 = leitura, nada muda para a 3.5. Este doc **não
  decide sobre a conta**.

**Invariantes:** uma alocação referencia **um funcionário** (id de staff) e **uma demanda** da
mesma escala; o mesmo funcionário **não ocupa duas vagas da mesma demanda**; o alocado é da
**mesma unidade**; a alocação está **dentro do período**; carrega "conta para a carga"
(booleana, default verdadeiro, sem dinheiro) e "exceção de função" (booleana, default falso —
verdadeira só por aceite consciente); **nenhuma leitura de scheduling exibe um registro
inativo** nem as suas alocações.

### 3.5 Escala vigente, auditoria e concorrência

**Regra canônica — toda alteração salva é a escala vigente.** Decisão do sponsor, 2026-09-13
([ADR 4.1.0001](../../adr/4_1_0001-every-saved-change-is-the-live-schedule.md)): *"toda
alteracao salva é a escala vigente, simple e direto"*. `overview.md` 43 e 136 ("salvar =
publicar"; "publicar: salvar a escala tornando-a visível") ficam **literais**:

- **Não há rascunho no servidor** nem "versão publicada" separada. Cada mutação persistida
  (demanda, alocação, aceite) é a escala que o funcionário consulta (`overview.md` 43), a imagem
  renderiza (`roadmap.md` 1405, 1422), o ponto concilia (1560, 1575, 1630) e o hub lê (1663).
- **`block` recusa a própria mutação** — a escala vigente nunca fica inválida; não se "passa
  por" um estado inválido ao rearranjar.
- **`warn` é apresentado e aceito no ato de salvar** — o aceite consciente (`overview.md` 42) é
  parte da mutação. O fluxo "editar → avaliar → aceitar warn → publicar" do roadmap (1304, 1320,
  1332) lê-se como: avaliar ao vivo, e salvar **com** o aceite dos avisos que a mudança introduz.
- **Quem/quando** de cada mutação (`roadmap.md` 1252): o ator autenticado e o instante absoluto
  do `Clock` compartilhado ("timestamp atual com timezone (UTC recomendado)" —
  `shared/application/ports/out/clock.py` 17). Staff não tem `Clock` nem carimbos (ADR 3.2.0006
  155–157): o Step 4 é o **primeiro** lugar com auditoria — o que a 4.4 decidir vira precedente.
- **O histórico é a trilha de auditoria** — "trilha de auditoria das alterações" (`overview.md`
  38); "histórico e auditoria" (`overview.md` 91); "histórico de edições — quem alterou o quê e
  quando"; "toda mutação de escala gera entrada de auditoria" (`roadmap.md` 1330, 1347). O aceite
  de `warn` altera o que a escala reporta — entra na trilha (derivação de `overview.md` 38 + 42).
  O **desligamento não é mutação da escala** (reconciliação na leitura, §3.4) — não gera entrada.

**Regra canônica — concorrência: controle otimista por versão, sem sobrescrita no servidor.**
Decisão do sponsor, 2026-09-13 (F8 — ADR 4.1.0001): *"Ao clicar em publicar precisa conferir se
foi atualizada, se foi, aparece mensagem se deseja atualizar e perder o trabalho ou nao
(cancelar= nao publica mas nao perde o trabalho caso ele queira printar a tela pore xemplo)"*.

- Toda mutação carrega a **versão da escala** que o editor viu; se a escala mudou, o servidor
  **recusa** e devolve o estado atual.
- O cliente oferece **"atualizar"** (descartar o que está na tela e recarregar) ou **"cancelar"**
  (manter o que está na tela, **sem salvar**). **Sobrescrever o trabalho alheio não é oferecido
  pelo servidor.**
- Fecha a lacuna do roadmap (816–820: controle otimista "sem Stage candidata") e supera, para a
  escala, o "last write wins" de staff (ADR 3.3.0006 91–98). Stages: **4.4** (versão + checagem)
  e **4.5** (status/corpo da recusa).

**Invariantes:**
- A escala vigente **nunca contém violação `block`** (mesma semântica que o Step 5 reutiliza —
  `roadmap.md` 1453).
- Toda violação `warn` presente na escala vigente foi **aceita conscientemente** por um ator, e o
  aceite está na trilha.
- Toda mutação gera entrada de auditoria com quem/quando e incrementa a versão da escala.
- Nenhuma mutação é aplicada sobre uma versão que o editor não viu.

> **Lacuna para o concept da Stage 4.3/4.5 — unidade de salvamento:** uma **operação por
> requisição** (alocar, desalocar, mudar demanda) ou um **lote de edições** salvo de uma vez? A
> resposta F8 do sponsor ("ao clicar em publicar", "perder o trabalho", "printar a tela")
> pressupõe edições acumuladas no cliente e um clique; este doc descreve a mutação como unidade.
> A escolha afeta onde vive o aceite de `warn`, o incremento da versão, o agrupamento do e-mail
> (4.6) e a granularidade da auditoria (4.4). A teoria vale para as duas formas.

**Tensões registradas (não resolvidas aqui):** (a) **roadmap 5.2** — "grava alocações como
rascunho de edição" (1426) e o non-goal "aplicar+publicar num passo só" (1443) pressupõem um
rascunho que não existe: **lacuna de escopo do roadmap para o gate do Step 5** (o "aplicar" do
auto-fill publica direto, respeitando `block`, ou o Step 5 cria a sua noção de proposta); (b)
**e-mail por mutação** — sem agrupador, cada alteração salva dispararia um e-mail (§3.8).

> **Lacuna para o concept da Stage 4.3:** o **protocolo do aceite** — mutação submetida já com o
> aceite dos avisos exibidos pela avaliação ao vivo, ou servidor devolve os avisos para
> confirmação e a mutação é reenviada com o aceite.

> **Lacuna para o concept da Stage 4.2/4.3:** a **identidade de uma violação** para fins de
> aceite (política + sujeito + faixa?) — se o aceite sobrevive a uma mudança na alocação que a
> originou.

> **Lacuna para o concept da Stage 4.4:** granularidade da auditoria (por mutação; snapshot ×
> diff), **retenção** (LGPD básica — `overview.md` 109) e o que o funcionário vê quando uma
> alocação dele muda.

### 3.6 Validações parametrizáveis

#### 3.6.0 Modelo comum

**Regra canônica:** validações **parametrizáveis por restaurante**, em **modo bloquear ou
avisar**, com **avisos ao vivo**; "o editor corrige ou aceita conscientemente" (`overview.md`
42). São **estratégias plugáveis de domínio** (`overview.md` 114; `roadmap.md` 1278), cada uma com
modo `block`/`warn`, orquestradas por um **avaliador** que "aplica só políticas habilitadas na
config do restaurante e distingue block × warn" (`roadmap.md` 1278, 1294).

- **CLT não é hard-coded** (`overview.md` 110): cada fonte legal sustenta o **default** e os
  **limites** de um parâmetro; a **CCT** pode alterar o valor (CF art. 7º XIII — "facultada a
  compensação de horários e a redução da jornada, mediante acordo ou convenção coletiva"; CLT
  art. 611-A, I–III). O produto **não embute CCT alguma**.
- **Configuração por tenant**, persistida (`roadmap.md` 1296, 1330): por política — habilitada?,
  modo, parâmetros.
- **Sujeito de toda política é o registro de funcionário (por unidade)** — derivação de
  "unidades não compartilham funcionários (não se enxergam)" (`overview.md` 37) e do piloto com
  uma unidade (ASSUM-4, `overview.md` 69). **Limite declarado da v1:** a **mesma pessoa** copiada
  para duas unidades (N registros → mesmo `User`, `workforce.md` §3.1) tem horas e descansos
  avaliados **por registro**, não somados — embora os limites legais (CF 7º XIII; CLT 58, 59, 66)
  sejam do empregado perante o empregador. Avaliar a **pessoa** entre unidades é **evolução**
  (§5), condicionada ao vínculo `user_id` (3.5).
- **Insumo além da escala corrente.** O descanso entre jornadas cruza o período (última
  alocação da escala anterior × primeira desta): o avaliador recebe as **alocações vizinhas**
  do registro — derivação necessária da fórmula.
- **`block` × `warn`**: `block` recusa a mutação; `warn` é salvo com aceite (§3.5). O Step 5
  reutiliza `block` (`roadmap.md` 1453).
- **Conjunto v1, defaults e modos — decisão do sponsor, 2026-09-13**
  ([ADR 4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md)): *"Confirmar
  a tabela (Recomendada)"*. O sponsor a tratou como **uma** decisão; o ADR enumera as
  sub-decisões (a)–(e) só para rastreabilidade. As políticas que as fontes sustentam mas o
  roadmap 4.2 não lista (§3.6.9) ficam como **evolução** — o que também resolve o "etc." de
  `overview.md` 42 × a lista fechada de `roadmap.md` 1278/1285 (ex-HALT H4: escopo, não
  contradição; o roadmap recebe nota no fechamento). A sétima linha — **função não detida** — entrou
  em 2026-09-14 (F9, ADR 4.1.0003 (f)) e a oitava — **sobre-cobertura da demanda** — em
  2026-09-26 (F10, ADR 4.1.0003 (g)).

| Política | O que valida (fórmula) | Default de valor (fonte) | Modo default | Configurável |
|---|---|---|---|---|
| Sobreposição (§3.6.1) | mesmo registro, `início_A < fim_B ∧ início_B < fim_A` | — (impossibilidade física) | **block** | modo |
| Alocação × indisponibilidade (§3.6.6) | sobreposição com período de indisponibilidade do registro | — | **block fixo** | nada |
| Descanso entre jornadas (§3.6.2) | `início da 1ª alocação do dia operacional seguinte com alocação − fim da última alocação do dia operacional anterior < mínimo` | **11h** — CLT art. 66 | **warn** | valor ≥ 0, modo |
| Teto diário (§3.6.3) | `Σ horas(alocações do dia operacional) > teto` | **10h** — CLT art. 58 (8h) + art. 59 (2h; § 2º "limite máximo de dez horas diárias") | **warn** (art. 61) | valor, modo |
| Teto semanal (§3.6.4) | `Σ horas(semana de apuração) > teto` | **44h** — CF art. 7º XIII | **warn** | valor, modo |
| Carga contratada, só jornada fixa (§3.6.5) | `Σ horas(alocações que contam) − carga > tolerância` | tolerância **0h**; direção **excesso** | **warn** | tolerância, direção, modo |
| Função não detida (§3.6.7) | `função(demanda) ∉ funções(registro)` | — (regra de produto; sponsor 2026-09-14) | **warn** — aceite grava a alocação como **exceção de função** | modo (`block`) |
| Sobre-cobertura da demanda (§3.6.8) | `alocados(demanda) > N` | — (regra de produto; sponsor 2026-09-26) | **warn** — aceite grava a alocação excedente | modo (`block`) |

> **Lacuna para o concept da Stage 4.2:** forma da `Violation` (campos), ordem de avaliação e se
> a indisponibilidade (§3.6.6) entra no avaliador com modo fixo ou é checada no use case.

#### 3.6.1 Sobreposição de alocações (`overlap_policy`)

- **O que valida:** o mesmo registro com duas alocações cujas faixas se sobrepõem:
  `viola ⇔ início_A < fim_B ∧ início_B < fim_A` (semi-aberto; adjacentes **não** violam —
  `workforce.md` §3.6; ADR 3.1.0001 47–54). Aplica-se também entre a escala corrente e as
  vizinhas.
- **Default (sponsor, F4):** habilitada, **`block`** — impossibilidade física, não regra
  trabalhista; sem fonte legal nem parâmetro de valor. **Configurável:** só o modo (tolerar
  sobreposição deliberada de troca "na porta").

**Invariante:** a definição de sobreposição é **a mesma** em toda a v1 (faixa × faixa, alocação
× alocação, alocação × indisponibilidade).

#### 3.6.2 Descanso entre jornadas — interjornada (`rest_between_shifts_policy`)

- **O que valida (F2 — dia operacional):** para cada registro, tomados os dias operacionais com
  alocação em ordem, e para cada par consecutivo-com-alocação `(d_i, d_j)`:
  `descanso = início(primeira alocação de d_j) − fim(última alocação de d_i)`;
  `viola ⇔ descanso < mínimo`. Cruza a fronteira do período (§3.6.0).
- **Limite declarado da v1 (sem fonte que o feche):** a CLT art. 66 fala em "jornadas", não em
  dias; o produto **não** identifica onde uma jornada termina e outra começa dentro do mesmo dia
  operacional. Lacunas entre alocações do **mesmo** dia operacional (jornada partida, ex.:
  08h–12h e 22h–02h, 10h de lacuna) são **intervalo dentro da jornada** e pertencem a uma
  política de **intrajornada** — evolução (§3.6.9). Consequência explícita: esse exemplo **não
  gera aviso na v1**. Alocações **contíguas** (11h–15h e 15h–19h) são jornada contínua e nunca
  geram aviso.
- **Default e limites (fonte primária):** **11 horas**. CLT, art. 66 — *"Entre 2 (duas)
  jornadas de trabalho haverá um período mínimo de 11 (onze) horas consecutivas para
  descanso."* (redação original; Planalto, https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm;
  acesso em 13 set. 2026).
- **Configurável:** valor (horas, **livre ≥ 0**) e modo. **Se a CCT pode reduzir as 11h não está
  fixado em fonte primária** (HALT H5) — o piso legal é informado, não imposto.
- **Modo default (sponsor, F4): `warn`** — a consequência legal do descumprimento é
  **remuneratória**, não nulidade da escala. Âncora geral: **OJ 355 da SBDI-1 do TST** — *"O
  desrespeito ao intervalo mínimo interjornadas previsto no art. 66 da CLT acarreta, por
  analogia, os mesmos efeitos previstos no § 4º do art. 71 da CLT e na Súmula nº 110 do TST,
  devendo-se pagar a integralidade das horas que foram subtraídas do intervalo, acrescidas do
  respectivo adicional"* (transcrita no acórdão TST-RR-1009-03.2014.5.12.0016 — §7). A Súmula 110
  trata do regime de revezamento e do intervalo de **35h** (24h + 11h) após o repouso semanal —
  composição que só faz sentido com uma política de DSR (§3.6.9). E o overview prevê "aceita
  conscientemente".

> **HALT H5 — regra sem fonte primária (registrado; nada a escalar enquanto o parâmetro for
> livre):** CLT art. 611-A lista o que a CCT pode dispor "entre outros" (não cita o interjornada);
> art. 611-B não o protege expressamente, e seu parágrafo único diz que "regras sobre duração do
> trabalho e intervalos não são consideradas como normas de saúde, higiene e segurança". Sem
> decidir: parâmetro livre + default 11h. Escalar só se o sponsor quiser impor piso 11h.

#### 3.6.3 Teto de horas por dia (`max_hours_policy`, eixo dia)

- **O que valida:** `horas_dia(f, d) = Σ horas(a)` para toda alocação `a` de `f` cuja faixa
  **pertence ao dia operacional `d`** (§3.2); `viola ⇔ horas_dia > teto_dia`; `horas(a)` por
  §3.6.10.
- **Default e limites (fonte primária):** **10 horas** = 8h normais + até 2h extras. CLT, art.
  58, *caput* — *"A duração normal do trabalho, para os empregados em qualquer atividade privada,
  não excederá de 8 (oito) horas diárias, desde que não seja fixado expressamente outro
  limite."*; art. 59, *caput* (Lei 13.467/2017) — *"A duração diária do trabalho poderá ser
  acrescida de horas extras, em número não excedente de duas, por acordo individual, convenção
  coletiva ou acordo coletivo de trabalho."*; art. 59, § 2º — *"… nem seja ultrapassado o limite
  máximo de dez horas diárias."* (Planalto, URL acima). Regimes com outro teto: **12h** no 12x36
  (art. 59-A) e até 12h por necessidade imperiosa (art. 61, § 2º) — por isso é parâmetro; a
  ressalva do art. 58 é a porta legal.
- **Configurável:** valor e modo. **Modo default (sponsor, F4): `warn`** — a própria lei prevê
  hipóteses acima de 10h (art. 61).

#### 3.6.4 Teto de horas por semana (`max_hours_policy`, eixo semana)

- **O que valida:** `horas_semana(f, s) = Σ horas(a)` para toda alocação `a` de `f` cujo dia
  operacional pertence à semana de apuração `s` (7 dias operacionais a partir do dia de início —
  F2); `viola ⇔ horas_semana > teto_semana`.
- **Default e limites (fonte primária):** **44 horas**. CF, art. 7º, XIII — *"duração do
  trabalho normal não superior a oito horas diárias e quarenta e quatro semanais, facultada a
  compensação de horários e a redução da jornada, mediante acordo ou convenção coletiva de
  trabalho;"* (Planalto, https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm;
  acesso em 13 set. 2026). A CLT art. 58 só fixa o diário; o semanal está na CF. A CCT pode
  **reduzir** (40h, 36h — CLT art. 611-A, I).
- **Compensação / banco de horas** (CLT art. 59, §§ 2º, 5º, 6º — mês, 6 meses, ano): **fora da
  v1** (`overview.md` 56); a v1 apura por **semana estrita** e o excesso vira `warn` aceito.
- **Configurável:** valor e modo. **Modo default (sponsor, F4): `warn`**.

#### 3.6.5 Carga contratada (`workload_policy`)

- **O que valida:** para registro de **jornada fixa**, `horas_conta(f, s) = Σ horas(a)` das
  alocações de `f` na semana `s` com "conta para a carga" (§3.4); `desvio = horas_conta −
  carga_contratada`; `viola ⇔ desvio > tolerância` (direção **excesso**, default) ou
  `⇔ |desvio| > tolerância` (direção **ambos**).
- **Insumo:** a carga semanal contratada — **uma** carga, horas/semana, `> 0`, fracionária
  (`workforce.md` §3.3(a); ADR 3.1.0001 (ii)), lida **por dados** via `StaffReadPort`
  (`roadmap.md` 1292). Sob demanda **não tem carga** — a política **não se aplica**.
- **Distinta do teto de horas** (ADR 3.1.0001 57–61; `workforce.md` §3.3(a), §6). A carga
  **nunca** é validada contra 44h como piso: cargas menores existem (CLT art. 58-A — tempo
  parcial até 30h, ou 26h + 6h).
- **Default (sponsor, F4):** tolerância **0h**; direção **excesso**; modo **`warn`**; alocação
  **conta** por default. Sem fonte legal para a direção — decisão de produto. **Configurável:**
  tolerância, direção, modo.

#### 3.6.6 Alocação × indisponibilidade (bloqueio não parametrizável)

- **O que valida:** `viola ⇔ início_aloc < fim_indisp ∧ início_indisp < fim_aloc` (semi-aberto —
  `workforce.md` §3.6; ADR 3.1.0001 47–54). A indisponibilidade chega **sem conversão**:
  wall-clock no fuso da unidade do registro (ADR 3.1.0005 41–46), o mesmo regime das faixas.
- **Modo: `block`, não configurável** (confirmado na tabela de F4). Indisponibilidade é "período
  em que o funcionário não pode ser escalado" (`workforce.md` §2); "hard blocking is
  unavailability's job", em oposição à preferência, sinal soft do Step 5 (ADR 3.1.0004 111–112);
  a cópia entre unidades carrega indisponibilidades porque descartá-las *"produces, in the target
  unit, a record that is schedulable during the employee's own vacation"* (ADR 3.2.0003
  104–107). Regra do produto (`overview.md` 39), não trabalhista.
- **Não é uma das quatro do roadmap 4.2** — o sponsor a confirmou na tabela de F4 (§3.6.0).
  Onde vive (avaliador com modo fixo × use case) é lacuna da 4.2.

**Invariante:** a escala vigente nunca contém alocação sobre indisponibilidade.

#### 3.6.7 Função não detida — exceção de função (`function_mismatch_policy` †)

Decisão do sponsor, 2026-09-14 (F9 — [ADR 4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md)
(f)): *"Nao permite alocar no primeiro momento, mas aparece "pop-up" (custom) que nao possui o
cargo daquela conta registrado apra aquele horario, e pergunta se deseja adicionar mesmo assim.
(nao muda a escala padrao, fica com uma excessao, como um extra na escala)"*.

- **O que valida:** alocar um registro numa demanda cuja função ele **não detém** —
  `viola ⇔ função(demanda) ∉ funções(registro)`, com as funções lidas de staff via
  `StaffReadPort` (§3.10.1).
- **Comportamento:** a alocação **não é gravada de imediato**; o editor vê o aviso ("não tem a
  função X registrada para este horário — adicionar mesmo assim?"); o **aceite consciente**
  (§3.5) grava a alocação **marcada como exceção de função** — visível na escala, "como um
  extra". O **cadastro não muda**: as funções do registro em staff ficam como estão.
- **Modo default: `warn`**; configurável para **`block`** por restaurante (mesmo protocolo das
  demais). Sem fonte legal — regra de produto.
- **Auto-preenchimento (Step 5) nunca cria exceção**: continua casando só por função
  (ADR 3.1.0006); a exceção é sempre manual.
- A marca é atributo da alocação, irmã de "conta para a carga" (§3.4).

**Invariante:** toda alocação cuja função não é detida pelo registro carrega a marca de exceção
de função e um aceite na trilha (ou foi recusada, se o modo for `block`).

> **Lacuna para o concept da Stage 4.2:** se a exceção é **reavaliada** quando o cadastro muda
> depois (o registro ganha a função → a marca cai? perde a função de uma alocação comum → vira
> violação?); e a forma da marca na `Violation`/aceite (identidade — §3.5).

#### 3.6.8 Sobre-cobertura da demanda (`over_coverage_policy` †)

Decisão do sponsor, 2026-09-26 (F10 — [ADR 4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md)
(g)): *"Permite com aviso"*.

- **O que valida:** alocar além do que a demanda pede — `viola ⇔ alocados(demanda) > N`.
- **N é alvo, não teto:** a alocação excedente **é permitida**; o editor vê o aviso
  ("demanda de N já coberta") e o **aceite consciente** (§3.5) grava a alocação. Cobertura
  acima de 100% é, portanto, estado legítimo e **visível** da escala vigente — simétrica à
  cobertura abaixo de 100% (§3.3), que o overview já trata como normal.
- **Modo default: `warn`**; configurável para **`block`** por restaurante (mesmo protocolo das
  demais) — com `block`, alocar o excedente exige aumentar `N` antes. Sem fonte legal: regra de
  produto (cobertura é conceito do produto, não da CLT).
- **Auto-preenchimento (Step 5) não sobre-cobre**: preenche até `N` (a proposta respeita a
  demanda); o excedente é sempre manual.

**Invariante:** nenhuma alocação excedente existe na escala vigente sem um aceite na trilha
(ou foi recusada, se o modo for `block`).

> **Lacuna para o concept da Stage 4.2:** se o aviso conta o excedente por **demanda** ou por
> `(dia, faixa, função)` quando a cardinalidade da 4.1 admitir duas demandas da mesma função em
> faixas sobrepostas (§3.3); e se reduzir `N` depois reabre a violação nas alocações já aceitas.

#### 3.6.9 Políticas sustentadas pelas fontes e deixadas como evolução

Decisão do sponsor, 2026-09-13 (F4 — ADR 4.1.0003): **nenhuma entra na v1**. Registradas com a
fonte verificada para que a evolução seja barata (uma estratégia nova no mesmo protocolo). Se
alguma entrar, continua valendo `overview.md` §6: habilitável e com modo configurável — o
"inegociável" abaixo é o piso legal, não um `block` fixo.

| Política candidata | O que validaria | Default sustentado pela fonte | Fonte primária (acesso em 13 set. 2026) | Observação |
|---|---|---|---|---|
| **Descanso semanal (DSR)** | ausência de 24h consecutivas de folga em cada janela de 7 dias | 24h/semana; piso **inegociável** por CCT | CLT art. 67, *caput* — *"Será assegurado a todo empregado um descanso semanal de 24 (vinte e quatro) horas consecutivas, o qual … deverá coincidir com o domingo, no todo ou em parte."*; Lei 605/1949 art. 1º; CLT art. 611-B, IX | Janela cruza períodos. A escala vigente/impressa é o "quadro sujeito à fiscalização" do art. 67 p.u. |
| **Domingo de folga a cada N semanas** | N semanas seguidas sem folga em domingo | N = 3 **se** restaurante for "comércio em geral" (**não verificado** — H3) | Lei 10.101/2000, art. 6º, p.u. (Lei 11.603/2007) — *"O repouso semanal remunerado deverá coincidir, pelo menos uma vez no período máximo de três semanas, com o domingo…"* | Sem enquadramento verificado, default seguro = **desligada**. |
| **Intervalo intrajornada** | faixa > 6h sem intervalo declarado ≥ mínimo; 4h–6h sem 15 min; lacunas entre alocações do mesmo dia operacional (§3.6.2) | 1h (> 6h); 15 min (4h–6h); piso negociável **30 min** | CLT art. 71, *caput* e § 1º; art. 611-A, III — *"intervalo intrajornada, respeitado o limite mínimo de trinta minutos para jornadas superiores a seis horas;"* | Viável porque a faixa **declara** o intervalo (F3). |
| **Regime 12x36** | teto diário 12h e descanso 36h para quem está no regime | por funcionário/instrumento escrito | CLT art. 59-A (Lei 13.467/2017); Súmula 444 do TST (pré-reforma, mais restritiva) | Exige atributo de regime que **staff não tem**. |
| **Compensação / banco de horas** | teto semanal como média numa janela | mês / 6 meses / ano | CLT art. 59, §§ 2º, 5º, 6º | **Fora da v1** (`overview.md` 56). |
| **Antecedência de convocação (intermitente)** | intermitente alocado com < 3 dias corridos de antecedência | 3 dias corridos (§ 1º) | CLT art. 452-A (verificada em `workforce.md` §3.4; `overview.md` 150–153) | `overview.md` 110: "se o restaurante adotar"; **o produto não sabe quem é intermitente** (`workforce.md` §3.4). |

> **HALT H3 — premissa não verificada em fonte primária (registrado; nada a escalar):** que
> restaurantes constam do Anexo IV da **Portaria MTP 671/2021** (permissão permanente para
> domingos/feriados — Decreto 10.854/2021, art. 154 § 4º) e que restaurante é "comércio em geral"
> para a Lei 10.101 art. 6º. O texto da Portaria não foi obtido (URL do DOU devolve HTTP 404/403;
> compilada em gov.br "Conteúdo Restrito"); a única evidência é **histórica** (Decreto
> 27.048/1949, item "Hotéis e similares (restaurantes…)", **revogado** pelo Decreto 10.854/2021
> art. 187, I). Nenhuma política v1 depende disso; o produto não valida permissão administrativa.
> Vira pergunta ao sponsor só se "domingo a cada N semanas" entrar.

#### 3.6.10 Contagem de horas — regra única

**Regra canônica** (decisão do sponsor, 2026-09-13, F3 — ADR 4.1.0002: *"Menos intervalo
declarado (Recomendada)"*): `horas(a) = (fim − início) − intervalo_declarado`, com o intervalo
em minutos, default 0 (§3.2). Racional: CLT art. 71, § 2º — *"Os intervalos de descanso não serão
computados na duração do trabalho."* Quem não declara intervalo tem a hora nominal; quem declara
tem o número da lei.

- **Uma** definição, consumida por **todas** as políticas que somam (§3.6.3–§3.6.5) e pelo hub
  ("horas contratadas × escaladas × cumpridas" — `overview.md` 45; `roadmap.md` 1683).
- **Dia de uma alocação** = dia operacional do **início** da faixa (§3.2).
- **Sobreposição e descanso são geométricos** — instantes, nunca horas contadas. A contagem é
  **sem dinheiro** (`overview.md` 56).
- **Hora ficta noturna** (CLT art. 73 § 1º: *"A hora do trabalho noturno será computada como de
  52 minutos e 30 segundos."*; § 2º: 22h–5h; § 4º: horários mistos) é **evolução**: flag por
  restaurante **na mesma função** (§5). Quando entrar: cinco noites 22h–05h somam 35h nominais ou
  40h fictas.

### 3.7 Consulta: calendário, escalas anteriores e "minha escala"

**Calendário dia/semana/mês.** `overview.md` 45 o descreve como "visão principal" do **Hub (aba
escala)**, "com mini-cards de funcionários sobre as faixas de funcionamento" (= faixas
habilitadas, §2); `roadmap.md` 1304, 1311 e 1317 o colocam como **use case e endpoint de
scheduling** (`get_calendar`); o Step 8 o lê via `SchedulingReadPort` sobre "dados publicados por
scheduling" (`roadmap.md` 1683, 1697–1704). Leitura reconciliada (§6): **o calendário é read
model de scheduling**; o hub é **consumidor** (`overview.md` 114). O nome dos mini-cards vem de
staff (ADR 3.1.0002 30–31). Sob F1 o calendário mostra sempre a escala vigente; sob F7, **sem
registros inativos** — toda leitura reconcilia com staff (§3.4; ADR 4.1.0006).

**Escalas anteriores.** `overview.md` 46; `roadmap.md` 1217; `list_past_schedules` (1272). É
**leitura**; copiar é evolução (§5). Alocações de registros hoje inativos **não aparecem** (limite
declarado de F7 — §3.4) até a página de histórico de funcionários.

**"Minha escala".** "Funcionário com login consulta a própria escala" (`overview.md` 43, 92);
"RBAC: funcionário só vê a própria" (`roadmap.md` 1356); `get_my_schedule` (1272):

- O funcionário vê a escala **vigente** e **apenas as próprias alocações** — leitura decidida
  pela mestra sobre os docs (âncora: "funcionário só vê a própria"). A **visão da unidade
  inteira** ("quem trabalha comigo") é **evolução** (§5). **Assimetria assumida como escolha:**
  a imagem (4.7) mostra a unidade inteira, mas é **divulgação manual** pelo gerente
  (`overview.md` 43) — não altera o que o login expõe.
- Resolução "ator → registro(s)" pelo vínculo `user_id` da 3.5 (`workforce.md` §3.1, §3.8), da
  qual a 4.1 **depende** (`roadmap.md` 123); no código mergeado o registro **ainda não tem
  `user_id`** (`employee.py` 66–74). A mesma pessoa pode ter **N registros em N unidades**
  (ADR 3.1.0001 (iii)): "minha escala" cobre **todos** os registros do ator, cada um na sua
  unidade.
- O papel `employee` tem **permissões vazias** (`role.py` 77); "a Stage que introduzir
  auto-serviço precisará de uma permissão" (ADR 2.2.0002 231–234). Ver §4.
- Um registro **inativo** não tem "minha escala": a leitura reconcilia com staff e devolve vazio
  para ele (a conta de login, se existir, é assunto da 3.5).

> **Lacuna para o concept da Stage 4.3:** o que o calendário devolve quando o recorte pedido
> (mês) abrange várias escalas; e **como** scheduling descobre os `employee_id` do ator (o tenant
> vem do token — ADR 0.0.0005; o `employee_id` não) sem importar staff nem identity.

### 3.8 Efeitos da publicação: notificação e imagem

**E-mail (Stage 4.6).** "E-mail opcional a cada atualização (opção 'sempre notificar alterações
na escala')" (`overview.md` 43); "opção **por restaurante** … → publicação dispara e-mail aos
funcionários afetados com e-mail cadastrado (reuso do EmailSender de 2.5)" (`roadmap.md` 1380,
1356).

- **Opção por restaurante (tenant)** — ratificado; por unidade/funcionário é evolução (§5).
- **Só registros ativos** são "afetados" (reconciliação na leitura — §3.4).
- **"Com e-mail cadastrado" = registro com `user_id` vinculado**: staff **não guarda contato**;
  "schedule-publication e-mails (Step 4) go to the login e-mail" (ADR 3.1.0002 32–35). Sem login,
  sem e-mail — vê a imagem divulgada (`overview.md` 92).
- **Port**: `EmailSender.send(EmailMessage(to, subject, body_text))` em
  `shared/application/ports/out/` — "The second consumer is named, not imagined. Stage 4.6"
  (ADR 2.5.0001 69; 110). Resend; ConsoleSender em dev (kickoff #7; ASSUM-3). Outros canais:
  fora (`roadmap.md` 1397).
- O e-mail é **efeito** da publicação, não parte do agregado ("hook de notificação" em
  `publish_schedule`, `roadmap.md` 1390). O roadmap não diz o que acontece quando o envio falha.

> **Lacuna para o concept da Stage 4.6:** (a) **agrupamento/debounce** — sob F1 cada alteração
> salva é uma publicação; sem agrupador, um ajuste de duas mutações gera dois e-mails; (b)
> **"afetados"** (todos da escala × só quem teve alocação alterada desde o último envio); (c) se
> a **falha de envio** desfaz ou não a mutação; (d) conteúdo do e-mail e onde a flag persiste.

**Imagem/tabela (Stage 4.7).** "Imagem/tabela gerada **sob demanda** (botão gerar/imprimir) para
divulgação manual" (`overview.md` 43); da **escala vigente** do período (`roadmap.md` 1405,
1383); port `ScheduleRenderer` (1373–1379); **formato e biblioteca em ADR na 4.7** (1720); envio
automático é non-goal (1385); sem registros inativos (§3.4). Sob a CLT art. 67 p.u., a escala
vigente/impressa é o "quadro sujeito à fiscalização" (premissa, ver H3).

### 3.9 Tempo: fuso da unidade, wall-clock, instantes de auditoria

- **Fuso horário configurável por unidade** (`overview.md` 101): **chave IANA** (`Area/Location`,
  ex.: `America/Sao_Paulo`) validada pela biblioteca padrão (PEP 615; `zoneinfo`: "`key` must be
  in the form of a relative, normalized POSIX path"). Dado de **configuração da unidade**, não de
  domínio de scheduling.
- **Dono do fuso: `Unit` em identity** — decisão do sponsor, 2026-09-13
  ([ADR 4.1.0005](../../adr/4_1_0005-unit-timezone-owned-by-identity.md)): *"Unit em identity +
  port (Recomendada)"*. `Unit.timezone`, chave IANA, default `America/Sao_Paulo`; scheduling — e
  depois timeclock e hub — **leem por port**. Resolve o ex-HALT H2: `overview.md` 101 e
  ADR 3.1.0005 28–31 ("The unit's timezone lives in configuration outside staff") ratificam o
  fuso por unidade, mas `Unit` no código só tem id, restaurante e nome (`unit.py` 32–34).
- **Faixas e alocações são wall-clock da unidade** — "16h–00h" é fato **local** (`overview.md`
  130), o mesmo regime da indisponibilidade de staff (ADR 3.1.0005 41–46), o que permite cruzar
  alocação × indisponibilidade **sem conversão** (ADR 3.1.0001 52–53). "Consumers MUST NOT
  compare staff datetimes with aware datetimes without converting first" (ADR 3.1.0005 84–85).
  A **representação** é lacuna da 4.1 (§3.2); este doc fixa só a semântica.
- **Conversão wall-clock → instante absoluto** só quando um consumidor precisa (e-mail, ponto,
  hub entre unidades), por quem **conhece o fuso** — "scheduling validations in Step 4"
  (ADR 3.1.0005 44–46), agora com o fuso lido de identity. Cópia entre unidades de fusos
  distintos mantém a leitura wall-clock (ADR 3.2.0003 177–183).
- **O "quando" da auditoria é instante absoluto** (UTC, `Clock.now()`). **Dois regimes
  coexistem** no agregado: faixas em wall-clock, carimbos em UTC — precedente no banco
  (ADR 3.3.0001 159–164; ADR 3.1.0005).
- **Horário de verão.** O Brasil não tem — Decreto 9.772/2019, art. 1º: *"Fica encerrada a hora
  de verão no território nacional."* — o que sustenta a premissa sem fonte do ADR 3.1.0005 87–88.
  Horários **ambíguos/inexistentes** (PEP 495 `fold`) só para unidades fora do Brasil — evolução
  (§5), absorvida pela chave IANA.

**Invariantes:** faixas, alocações e indisponibilidades comparam-se **no mesmo regime**
(wall-clock da unidade da escala — que é o da unidade do registro, §3.4), sem conversão; carimbos
de auditoria são instantes absolutos (UTC).

> **Lacuna de escopo do roadmap (registrada; a mestra anota no fechamento):** em que Stage entra
> a coluna `Unit.timezone` — **4.4** (primeira migration do Step 4) ou **issue avulsa de
> identity** antes da 4.3 (que precisa do port).

> **Lacuna para o concept da Stage 4.4/4.5:** representação persistida dos dois regimes e a forma
> na borda HTTP (precedente ADR 3.6.0003 §Decision: wall-clock sem offset; valor com offset
> recusado, não convertido).

### 3.10 Fronteiras

Scheduling **consome** staff e identity e **é consumido** por timeclock e hub. BCs se comunicam
**por ports**, com identificadores como **strings opacas** — nunca por import direto
(`identifiers.py` 5–7; `.importlinter` 219–228 — contrato `bc-independence`; ADR 3.3.0002
31–35). `EmployeeId`/`JobFunctionId` "de staff" no roadmap 4.1 (`roadmap.md` 1266) lê-se como
**emitidos por staff**; scheduling declara os seus — importar os de staff é violação medida
(ADR 3.4.0001 106–113). O contrato `bc-independence` hoje lista só `identity` e `staff`
(`.importlinter` 226–228); incluir `scheduling` é tarefa do `technical.md` da 4.1.

#### 3.10.1 Staff — dados consumidos (por id e por dados, sem import)

Nível de conceito: o que scheduling lê, onde staff o define (`origin/develop` `95fba00`, base deste PR) e o que faz com ele.
A forma exata (tipos, DTO do port) é do concept da 4.3.

| Conceito de staff | Natureza | Onde staff o define | Uso em scheduling |
|---|---|---|---|
| Identificadores (funcionário, função, tenant, unidade) | strings opacas tipadas por staff | `staff/domain/value_objects/identifiers.py` | referência por id; **não importar** — scheduling tipa os seus |
| Registro de funcionário (nome, unidade, perfil, funções, indisponibilidades, ativo) | entidade | `staff/domain/entities/employee.py` | elegibilidade (§3.4); nome de exibição; **sem `user_id`** hoje (3.5 `draft`) |
| Carga semanal contratada | um número, horas/semana, `> 0`, fracionário | `workload_profile.py` (`FixedSchedule`) | base da `workload_policy` (§3.6.5) |
| Perfil sob demanda | ausência de carga | idem (`OnDemand`) | `workload_policy` não se aplica; alocação = uso de extra (§3.10.4) |
| Períodos nomeados do dia | enum fechado (4 valores) | `shift_preference.py` (`DayPeriod`) | mapa período → faixas (§3.2; consumidor Step 5) |
| Preferência de turno | conjunto de períodos ou nenhum | idem (`ShiftPreference`) | **não é insumo de validação** — sinal soft do Step 5 (ADR 3.1.0004 111–112) |
| Funções do funcionário | conjunto não-vazio de ids | `employee.py` | política "função não detida" (§3.6.7); sem "função primária" |
| Função de trabalho | catálogo tenant-wide, sem estado | `staff/domain/entities/job_function.py` | nome para exibição da demanda |
| Indisponibilidade | intervalos wall-clock semi-abertos | `unavailability_period.py` | bloqueio (§3.6.6) **sem conversão** |
| Estado do registro | ativo × desligado | `employee.py` | **toda leitura** filtra inativos — reconciliação na leitura (§3.4; ADR 4.1.0006) |
| Leitura por id / listagem | endereço `(tenant, unidade[, id])`; sem busca tenant-wide | `staff/application/ports/out/employee_repository.py`; ADR 3.4.0007 | tudo o que o `StaffReadPort` pede é por unidade |

- **Ports**: dados de staff via port-out **`StaffReadPort`** (4.3), adapter local (4.4)
  (`roadmap.md` 1304, 1312, 1318, 1338). DTO **próprio de scheduling** (o `EmployeeResult` de
  staff carrega VOs de staff) — lacuna 4.3. Onde o adapter mora (`adapters/out/staff/` do roadmap
  × tradutor no composition root, ADR 3.4.0001 101–118) é do `technical.md` da 4.4 — a 3.5
  (`draft`) enfrenta a mesma forma antes.
- **Desligamento**: reconciliado na leitura — **nenhum crossing de escrita** staff → scheduling
  (ADR 4.1.0006). **Remoção definitiva**: port de consulta reverso **em staff**, implementado
  fora de staff (adapter/tradutor — localização é do `technical.md` da 4.4, ver #47) sobre uma
  query de scheduling (`has_allocations_for`) — o único crossing scheduling ← staff, na forma do
  ADR 3.4.0001; generaliza para função demandada (§3.3, §3.4).
- **Reconciliação de órfãos** cross-BC (unidade apagada) é operação do Step 6, não constraint
  (`docs/stages/3.3-staff-persistence/concept.md` 691–696).

#### 3.10.2 Identity — papéis, permissões, tenant, unidade e fuso

- **Papéis e permissões**: §4. Scheduling **estende o vocabulário** de `Permission`
  (`permission.py` 8–9) — expansão **autorizada** pelo sponsor (ADR 3.4.0006 §5).
- **Fuso da unidade**: `Unit.timezone`, lido por port (§3.9; ADR 4.1.0005). **E-mail do
  funcionário** = `User.email` via `user_id` (§3.8).
- **Tenant vem do token, nunca do path** — scheduling não é dono do tenant como recurso
  (ADR 0.0.0005 134–148, 159). **A unidade entra no endereço da escala** (§3.1), como no registro
  de funcionário (ADR 3.4.0007 57–70; ADR 0.0.0005 280–287); o router **nunca** infere escopo de
  `AuthorizedScope.unit_id` (ADR 3.6.0001; `access_guard.py` 90–109).
- **Guarda de acesso**: port **próprio do BC** com tradutor no composition root (ADR 3.4.0001
  59–64). Promover a `shared/` foi adiado porque "scheduling does not exist" (128–135) — a 4.5 é
  o **segundo consumidor** (LAYOUT §4) e decide.
- **Ordem normativa de autorização** (RBAC → tenant → unidade salvo bypass/tenant-wide →
  visibilidade; falha fechada): ADR 2.2.0002 60–78; ADR 3.4.0008 56–71.

#### 3.10.3 Timeclock (Step 7) — o que a escala vigente expõe

- O Step 7 consome "dados de alocação da escala (por DTO, sem import de entidade de scheduling)"
  via "port de leitura de scheduling" (`roadmap.md` 1614, 1669); concilia previsto × realizado
  por alocação (1560; `overview.md` 44, 137).
- A escala é o **previsto**; o ponto é **outra obrigação legal** — CLT art. 74, § 2º ("permitida
  a pré-assinalação do período de repouso") e § 4º ("registro de ponto por exceção à jornada
  regular") mostram o previsto como **insumo** do ponto.
- **O que a escala vigente expõe, por alocação**: registro (id), função (id), faixa em
  wall-clock da unidade (com o fuso para conversão — §3.9), dia operacional, unidade e tenant.
  Sob F1 não há "versão da publicação": o ponto lê a escala vigente; se o Step 7 precisar de "o
  que valia naquele dia", a fonte é a trilha de auditoria (4.4) — decisão do concept da 7.2, com
  a 4.4 avisada. Forma exata → 7.2. **Registros inativos não são expostos** (limite (2) de F7,
  §3.4) até a página de histórico de funcionários — lacuna de escopo para o gate do Step 7.

#### 3.10.4 Hub (Step 8) — grandezas que a escala produz

Via `SchedulingReadPort` (`roadmap.md` 1697–1704), por unidade e "Unidade Geral" (`overview.md`
45). Este doc **nomeia**; cálculo e read model são da 8.1: **cobertura da demanda**
(`alocados ÷ demandados`); **horas escaladas** por registro (`Σ horas(a)`, §3.6.10 — o mesmo
número das políticas); **horas contratadas** (carga de staff) e **cumpridas** (Step 7); **uso de
extras** = alocações de registros **sob demanda** (`overview.md` 135). As alocações de jornada
fixa marcadas "não conta" (§3.4) são **grandeza separada** — nenhuma fonte as equipara a
"extra"; nome e cálculo são lacuna do Step 8. Alocações com **exceção de função** (§3.6.7) são
outra grandeza nomeável pelo hub (lacuna do Step 8). **Registros inativos não entram** nas
leituras do hub até a página de histórico (limite (2) de F7 — lacuna de escopo para o gate do
Step 8).

#### 3.10.5 Auto-preenchimento (Step 5) — o que reutiliza

Entidades da 4.1 e políticas da 4.2 ("proposta nasce sem violações block", `roadmap.md` 1453); a
**preferência de turno** e o **mapa período → faixas** são insumos do Step 5 (ADR 3.1.0004
109–112). O auto-fill casa **só por função** — nunca cria exceção de função (§3.6.7) — e
preenche até `N`: **não sobre-cobre** (§3.6.8). A tensão
"rascunho de edição" × F1 está em §3.5.

---

## 4. Particularidades por caso de uso — visão RBAC

Quem faz o quê na escala (papéis de **acesso** de identity — conjunto fechado de 5, `role.py`
18–25; **função ≠ papel**, `workforce.md` §2). Três **famílias** de capacidade, todas
**unit-scoped**: **ler** (escala vigente + calendário da unidade), **gerenciar** (editar demanda
e alocações, aceitar avisos, salvar) e **própria** ("minha escala").

| Papel | Na escala |
|---|---|
| **dono (owner)** | **Lê e gerencia** a escala de **qualquer unidade** do tenant — visibilidade bypassa memberships (`user.py` 45; ADR 2.1.0001 eixo B; kickoff #9). Sponsor: "Apenas o gerente ou dono pode mexer na escala" (ADR 3.4.0006 §1). |
| **gerente (manager)** | **Lê e gerencia** a escala das **unidades de que é membro** (kickoff #9; ADR 3.4.0006 §1). |
| **RH (hr)** | **Lê** a escala vigente e o calendário **das unidades de que é membro**; **não edita, não aceita avisos, não salva** — decisão do sponsor, 2026-09-13 ([ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md)): *"Sim — leitura nas suas unidades"*. Supera **em parte** o ADR 3.4.0006 §3 ("must not grant `hr` any permission over the schedule"), que ganha errata datada neste PR: "mexer" continua vedado; "ler" é concedido (ex.: conferir se as férias cadastradas colidem com alocações). RH mexe no **cadastro** (ADR 3.4.0006 §1), que a escala **lê**. |
| **funcionário (employee)** | **Consulta a própria escala** (§3.7). Hoje permissões **vazias** (`role.py` 77); a Stage 4.x que expuser "minha escala" **cria a permissão** (ADR 2.2.0002 231–234; kickoff "bronze … hoje só consulta"). Não lê a escala da unidade, não edita; troca de turno é fora da v1. |
| **admin de plataforma** | Fora do tenant; só `MANAGE_PLATFORM` (ADR 2.2.0002 47–49; ADR 2.1.0002). **Sem permissão de escala.** |

**Regras derivadas:**

- **Toda leitura — família `ler`, família `própria`, calendário, imagem — filtra registros
  inativos** (reconciliação na leitura, §3.4; ADR 4.1.0006); a página de histórico de
  funcionários (evolução) terá a sua própria permissão quando existir.
- **Aceitar um aviso e salvar são atos de quem gerencia** (`overview.md` 42): manager e owner —
  inclusive o aceite da exceção de função (§3.6.7).
- **Permissões de escala são unit-scoped** — a escala é da unidade (§3.1); dispensa de unidade
  é **por permissão** (`TENANT_WIDE_PERMISSIONS`), só para alvos do restaurante (ADR 3.4.0008
  67–71, 79–83; `permission.py` 32–44). Nenhuma permissão de escala entra nesse conjunto.
  **Exceção a examinar na 4.4/4.5:** a **configuração** (validação; dia de início; corte) é por
  **tenant** — capacidade tenant-wide (precedente `MANAGE_JOB_FUNCTIONS`); única candidata.
- **Uma permissão por família de operação** (ADR 3.4.0006 §1, §4 — famílias `cadastro` ×
  `escala`), declarada por rota no adapter HTTP, que mapeia endpoint → conjunto de permissões
  exigidas (ADR 2.4.0003 §Decision 1). **Nomes** são lacuna da 4.5.
- **Reconciliações aplicadas neste PR**: `overview.md` §5 linha 91 ("Gerente / RH … Montar/ajustar
  escala") ganha nota datada — RH **consulta**; montar/ajustar é gerente/dono (ADR 3.4.0006 +
  4.1.0004); `workforce.md` §4 ("é NO STAFF que hr diverge do manager") ganha nota datada — a
  divergência é na **escala** (hr lê, não gerencia), como o finding da 3.6
  (`docs/stages/3.6-staff-http/concept.md` 926–933) pedia.

> **Lacuna para o concept da Stage 4.5:** nomes das permissões; se "salvar" e "editar" são a
> mesma permissão (sob F1 tendem a ser); se a configuração exige permissão própria (tenant-wide);
> e-mail como efeito sem permissão própria; promoção do `AccessGuard` a `shared/` (§3.10.2).

---

## 5. Evoluções previstas (não-escopo v1)

Registradas para que o modelo v1 não as bloqueie; **nenhuma entra sem revisão consciente**:

- **Período quinzenal/mensal** (CLT art. 67 p.u. nomeia "escala de revezamento, mensalmente
  organizada") ou "quadro mensal" derivado para impressão — a forma "intervalo contíguo de dias
  operacionais" e a distinção período × semana de apuração (§2) deixam a porta aberta.
- **Hora ficta noturna** (CLT art. 73 § 1º) — flag por restaurante em `horas(a)` (§3.6.10).
- **Políticas deixadas fora da v1** (§3.6.9): DSR; domingo a cada N semanas; intrajornada (agora
  viável); compensação/banco de horas; antecedência de convocação de intermitente.
- **Políticas por pessoa entre unidades** — exige `user_id` (3.5) e avaliador que some registros
  (§3.6.0).
- **Regime 12x36 / perfis de política por funcionário** (CLT art. 59-A); **CCT como parâmetro
  nomeado** — hoje cada valor é editado individualmente.
- **Página de histórico de funcionários** — reabre o acesso às alocações (passadas e futuras)
  de registros inativos, hoje invisíveis em toda tela (F7, §3.4); é também o que devolve
  inativos ao previsto × realizado (Step 7) e ao hub (Step 8). Sponsor: "no futuro quando for
  prioridade".
- **Copiar escala anterior / template de demanda recorrente** (`overview.md` 46 só ratifica
  visualizar).
- **Visão da unidade inteira para o funcionário** — v1 é só as próprias alocações (§3.7).
- **Flag de notificação por unidade/funcionário; canais além de e-mail; envio automático da
  imagem** (`roadmap.md` 1397, 1424). **Troca de turno pelo funcionário** (`overview.md` 57).
- **Feriados por unidade** (nacionais por lei federal; locais até 4 — Decreto 10.854/2021 art.
  153 p.u.; CLT art. 70) — nenhuma política v1 depende; lista não pesquisada; dona = a Stage que
  introduzir feriado como conceito.
- **Mapa período nomeado → faixas** — consumidor Step 5 (§3.2). **DST** (PEP 495 `fold`) — só
  fora do Brasil. **Habilitação de função por unidade** (issue #41). **Setor** (`overview.md` §9).
  **Papel-por-unidade** (ADR 2.1.0001).

---

## 6. Registro das decisões do gate (2026-09-13, 2026-09-14 e 2026-09-26)

### Com alternativa real — decididas pelo sponsor (ADRs 4.1.0001–4.1.0006)

Cada fork foi uma pergunta no formato do `PROMPT-step-single-session.md` §2 (triagem
`forks-triage.md` da sessão do gate). A decisão virou ADR, como o gate do Step 3 fez com
`3_1_0001`; a resposta literal do sponsor está citada em cada ADR e o doc está na forma
afirmativa.

- **F1 — Modelo de publicação** + **F8 — Concorrência** →
  [ADR 4.1.0001](../../adr/4_1_0001-every-saved-change-is-the-live-schedule.md): toda alteração
  salva é a escala vigente (sem rascunho no servidor, sem versão publicada imutável); `block`
  recusa a mutação; `warn` aceito ao salvar; controle otimista por versão com
  recarregar-ou-cancelar, sem sobrescrita no servidor. Resolve overview 43/136 × roadmap
  1304/1371 (ex-HALT T1) a favor do overview literal; roadmap 5.2 (1465, 1482) vira lacuna de
  escopo para o gate do Step 5. §3.5.
- **F2 — Período, dia de início, dia operacional e corte** + **F3 — Contagem de horas** →
  [ADR 4.1.0002](../../adr/4_1_0002-weekly-period-operational-day-and-allocation-hours.md): semana
  com dia de início configurável; dia operacional a partir do corte (default 05:00); faixa
  pertence ao dia operacional em que começa; `horas(a) = nominal − intervalo declarado`. §3.1,
  §3.2, §3.6.10.
- **F4 — Políticas v1** → [ADR 4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md):
  a tabela de políticas (§3.6.0) — seis confirmadas em 2026-09-13 como **uma** decisão; o ADR
  enumera (a) conjunto, (b) defaults de valor, (c) defaults de modo, (d) "conta para a carga" na
  alocação com default "conta", (e) sujeito = registro por unidade — para rastreabilidade, não
  porque foram cinco perguntas. Absorve o ex-HALT H4. §3.4, §3.6.
- **F9 — Função não detida** (2026-09-14) → ADR 4.1.0003 (f): sétima política — aviso, aceite
  consciente, alocação gravada como **exceção de função** sem tocar o cadastro; `warn` default,
  `block` configurável; auto-fill nunca cria exceção. Substitui a recusa estrutural do rascunho.
  §3.4, §3.6.7.
- **F10 — Sobre-cobertura da demanda** (2026-09-26) → ADR 4.1.0003 (g): oitava política —
  `N` é **alvo**, não teto; alocar além de `N` é **permitido com aviso** e aceite consciente,
  `warn` default e `block` configurável; o auto-fill não sobre-cobre. Fecha a lacuna (b) que o
  rascunho deixava para o concept da 4.1. §3.3, §3.6.8.
- **F5 — RH lê a escala** → [ADR 4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md):
  `hr` recebe leitura unit-scoped; sem escrita; supera em parte o ADR 3.4.0006 §3 (errata).
  Resolve o ex-HALT T2 (overview §5 × ADR 3.4.0006) com nota no overview. §4.
- **F6 — Dono do fuso** → [ADR 4.1.0005](../../adr/4_1_0005-unit-timezone-owned-by-identity.md):
  `Unit.timezone` em identity, chave IANA, default `America/Sao_Paulo`, lido por port. Resolve o
  ex-HALT H2; a Stage da coluna é lacuna de escopo do roadmap. §3.9.

- **F7 — Desligamento × escala** + **sub-pergunta da remoção definitiva** (2026-09-14) →
  [ADR 4.1.0006](../../adr/4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md):
  **reconciliação na leitura** — staff marca `active=False`, nenhuma escrita em scheduling, toda
  leitura consulta o estado atual e omite o inativo (nem alocações passadas) até a página de
  histórico de funcionários; guarda L-E5 mantida por **port de consulta reverso** em staff
  (tradutor fora de staff, localização do technical da 4.4; sem FK). A pesquisa de arquitetura pedida pelo sponsor recomendou o evento
  in-process pós-commit; o sponsor escolheu a reconciliação na leitura pela simplicidade ("como um
  refresh F5") e as alternativas A/B/C/E ficaram registradas como descartadas. Absorve o ex-HALT
  H1; os cinco limites declarados estão em §3.4. Erratas nos ADRs 3.2.0006 e 3.4.0002 e nota no
  `workforce.md` §3.1 **neste PR**. §3.3, §3.4, §3.7, §3.10.

### Pendentes

Nenhum fork aberto após 2026-09-26. Doc ratificado pelo sponsor em 2026-09-14 (`status: accepted`);
F10 (sobre-cobertura) decidida em 2026-09-26, durante o tratamento dos findings da auditoria.

### HALTs — disposição

| HALT | Natureza | Disposição |
|---|---|---|
| H1 — guarda cross-BC: FK (ADR 3.2.0006, 3.4.0002) × sem FK (ADR 3.3.0002) | fork real | → F7 decidida (ADR 4.1.0006): sem FK; port de consulta reverso em staff, tradutor fora de staff; desligamento reconciliado na leitura. Erratas nos ADRs 3.2.0006 e 3.4.0002 **neste PR**; ADR 3.3.0002 Alt C cumprido. |
| H2 — fuso por unidade sem dono no código | fork real | → F6 (ADR 4.1.0005). Stage da coluna: lacuna de escopo do roadmap. |
| H3 — Portaria MTP 671 / "comércio em geral" não verificados | premissa sem fonte | registrado (§3.6.9); não load-bearing; vira pergunta só se "domingo a cada N" entrar. |
| H4 — lista de políticas: overview "etc." × roadmap 4.2 fechado em quatro | escopo, não contradição | → dentro de F4 (ADR 4.1.0003): oito na v1 (as quatro do bloco 4.2 — com o teto contado em dia e em semana — + alocação × indisponibilidade + função não detida + sobre-cobertura); DSR/intrajornada/12x36 evolução. Roadmap 4.2 recebe nota no fechamento. |
| H5 — CCT pode reduzir as 11h? | regra sem fonte | registrado (§3.6.2); parâmetro livre + default 11h; escalar só se o sponsor quiser piso. |
| T1 — "salvar = publicar" (overview) × rascunho/aceitar-depois-publicar (roadmap) | contradição overview × roadmap | → F1 decidida a favor do overview literal (ADR 4.1.0001); roadmap 5.2 → gate do Step 5. |
| T2 — overview §5 "Gerente / RH montam escala" × ADR 3.4.0006 | fonte superior anterior × decisão posterior | → F5 (ADR 4.1.0004); nota no overview §5 e errata no ADR 3.4.0006 **neste PR**. |
| T3 — `workforce.md` §4 "é NO STAFF que hr diverge" × ADR 3.4.0006 | já decidido (2026-08-12) | nota datada no `workforce.md` §4 **neste PR**. |
| T9 — `workforce.md` §3.3(b) "atuação de quem é sob demanda…" × kickoff #11 / F4 (d) | já decidido (kickoff) + sponsor | nota datada no `workforce.md` §3.3(b) **neste PR**. |

### Derivações ancoradas (sem alternativa real — decididas pelos docs)

- **Escala por unidade** — `overview.md` 37, 45; `workforce.md` §3.1. §3.1.
- **Default do dia de início da semana: segunda-feira** — ISO 8601 via `date.isoweekday()` e
  Decreto 10.854/2021 art. 158 § 4º (§7); ambas sustentam **default**, não obrigação, e o dia
  segue configurável (F2). §3.1.
- **Escalas da mesma unidade não se sobrepõem** — derivação de `overview.md` 129; **proposta do
  gate**; com F2 decorre da forma. §3.1.
- **`Schedule` como raiz do agregado** — proposta do gate (†). §3.1.
- **Período × semana de apuração são conceitos distintos que coincidem na v1** — critério de
  escalabilidade progressiva. §2.
- **Semântica semi-aberta `[início, fim)`** — ADR 3.1.0001 52–54, 93–94. §3.2.
- **"Faixas de funcionamento" = faixas habilitadas por dia** — `overview.md` 45 ⇔ 40. §2.
- **`0 ≤ intervalo < duração nominal`** — derivação da regra de contagem. §3.2.
- **Demanda ≥ 0; cobertura < 100% legítima** — `roadmap.md` 1252, 1440, 1480. Cobertura > 100%
  é decisão do sponsor (F10, §3.6.8). §3.3.
- **Elegibilidade**: ativo + mesma unidade + dentro do período + função detida ou exceção
  aceita (F9) — `workforce.md` §3.1; `overview.md` 37; ADR 3.4.0007; `roadmap.md` 1252. §3.4.
- **A demanda coberta por um registro inativo lê-se como descoberta** — limite (1) declarado de
  F7 (reconciliação na leitura). §3.4.
- **Alocação × indisponibilidade é `block` fixo** — `workforce.md` §2, §3.6; ADR 3.1.0004
  111–112; ADR 3.2.0003 104–107; confirmado em F4. §3.6.6.
- **Sujeito das políticas = registro por unidade** — `overview.md` 37; ASSUM-4; limite declarado
  + evolução. §3.6.0.
- **Interjornada entre dias operacionais; lacunas no mesmo dia = intrajornada (evolução)** —
  limite declarado, sem fonte que fixe o limiar. §3.6.2.
- **Preferência de turno não é insumo de validação** — ADR 3.1.0004 111–112. §3.10.1.
- **`workload_policy` ≠ `max_hours_policy`; carga nunca contra 44h** — ADR 3.1.0001 57–61; CLT
  58-A. §3.6.5.
- **Avaliador recebe alocações vizinhas** — derivação da fórmula. §3.6.0.
- **Regra única de contagem** — `overview.md` 45; qual regra: F3. §3.6.10.
- **Aceite de `warn` é auditado; a escala vigente nunca contém `block`** — `overview.md` 38, 42;
  `roadmap.md` 1453. §3.5.
- **Auditoria em instante absoluto (UTC); faixas em wall-clock** — `clock.py` 17; ADR 3.1.0005.
  **Fuso = chave IANA**; Brasil sem DST (Decreto 9.772/2019). §3.9.
- **Calendário é read model de scheduling; hub consome** — `roadmap.md` 1304–1356, 1697–1704;
  `overview.md` 114. §3.7.
- **"Minha escala" = vigente, só as próprias alocações, todos os registros do ator** —
  `roadmap.md` 1356 ("funcionário só vê a própria"); `overview.md` 43, 92; `workforce.md` §3.1.
  A alternativa (visão da unidade inteira) existe, mas o roadmap já a exclui — por isso é
  derivação, não fork; fica em §5 como evolução; imagem = divulgação manual (assimetria
  assumida). §3.7.
- **Flag de notificação por restaurante; destinatário = e-mail de login** — `roadmap.md` 1380;
  ADR 3.1.0002 32–35. §3.8.
- **"Uso de extras" = alocações de sob demanda** — `overview.md` 135; "não conta" de jornada fixa
  é grandeza separada (Step 8). §3.10.4.
- **Copiar escala anterior; antecedência de intermitente** — evolução (`overview.md` 46;
  `workforce.md` §3.4). §5.
- **Três famílias de permissão (ler / gerenciar / própria), unit-scoped; `employee` precisa de
  permissão nova** — ADR 3.4.0006 §1/§4; ADR 2.2.0002 231–234; ADR 3.4.0008; F5. §4.
- **Scheduling tipa os seus ids; `StaffReadPort` pede `(tenant, unidade[, id])`** —
  `identifiers.py` 5–7; ADR 3.4.0007. §3.10.
- **Glosa PT ↔ EN** fixada em §2 (roadmap 4.1/4.2; os demais † como proposta).

### Lacunas para o concept de cada Stage (consolidado)

| Stage dona | Lacuna (§) |
|---|---|
| **4.1** | forma interna do `TimeRange`; faixa que ultrapassa o corte seguinte (§3.2) |
| **4.1** | cardinalidade da demanda por `(dia, faixa, função)` (§3.3) |
| **4.1** | `Schedule` como raiz do agregado — confirmar (§3.1) |
| **4.1 (technical)** | incluir `scheduling` em `bc-independence` (§3.10) |
| **4.2** | forma da `Violation`, ordem de avaliação, onde vive a indisponibilidade (§3.6.0) |
| **4.2** | exceção de função × mudança posterior do cadastro; forma da marca na `Violation`/aceite (§3.6.7) |
| **4.2** | sobre-cobertura: contagem por demanda × por `(dia, faixa, função)`; reduzir `N` reabre a violação aceita? (§3.6.8) |
| **4.3/4.5** | unidade de salvamento — uma operação por requisição × lote de edições (§3.5) |
| **4.2/4.3** | identidade da violação para fins de aceite (§3.5) |
| **4.3** | protocolo do aceite de `warn` na mutação (§3.5) |
| **4.3** | mudança do dia de início / corte com escalas existentes (§3.1) |
| **4.3** | calendário sobre recortes com várias escalas; resolução ator → `employee_id` (§3.7) |
| **4.3** | DTO próprio do `StaffReadPort` (§3.10.1) |
| **4.3** | limpar ou não as alocações futuras no desligamento — a recontratação as reexibe (limite (4) de F7, §3.4) |
| **4.3 / 4.4** | consulta em lote ao `StaffReadPort` para a reconciliação na leitura (custo por leitura — limite (5) de F7, §3.4) |
| **4.3 / 4.4** | Stage em que staff passa a consultar o port de consulta reverso — funcionário e função demandada (§3.3, §3.4) |
| **4.4** | granularidade e retenção da auditoria; o que o funcionário vê quando muda (§3.5) |
| **4.4 / 4.5** | versão da escala + checagem otimista (4.4); status/corpo da recusa (4.5) (§3.5) |
| **4.4 / 4.5** | representação persistida dos dois regimes de tempo; forma na borda HTTP (§3.9) |
| **4.4 (technical)** | localização do adapter cross-BC (§3.10.1) |
| **4.5** | nomes das permissões; salvar × editar; config tenant-wide; promoção do `AccessGuard` (§4); atualizar o comentário de `role.py` 50–52 ("nenhuma permissão sobre a escala", superado pela errata do ADR 3.4.0006) junto com o mapa de papéis |
| **4.6** | agrupamento/debounce; "afetados"; falha de envio; conteúdo; onde a flag persiste (§3.8) |
| **4.7** | formato e biblioteca da imagem — delegado pelo roadmap 1759 (§3.8) |
| **7.2 / 8.1** | contratos de leitura; "o que valia naquele dia" via auditoria (§3.10.3); grandezas "não conta" e "exceção de função" (§3.10.4) |
| **sem Stage (roadmap)** | gates dos Steps 7/8: registros inativos invisíveis até a página de histórico de funcionários (limite (2) de F7, §3.4) |
| **sem Stage (roadmap)** | mapa período nomeado → faixas (proposta: 5.1) (§3.2) |
| **sem Stage (roadmap)** | em que Stage entra `Unit.timezone` (4.4 × issue de identity) (§3.9) |
| **sem Stage (roadmap)** | roadmap 5.2 "rascunho de edição" / non-goal "aplicar+publicar" × F1 — gate do Step 5 (§3.5) |
| **sem Stage (roadmap)** | feriados por unidade (§5) |

---

## 7. Referências

### Âncoras internas (fontes ratificadas — passo 1 da barra de fontes)

- [`overview.md`](../../overview.md) — §3 (37–46, 56–57, 69), §5 (91–92), §6 (101, 109–110),
  §7 (114), §9 (129–140), §10 (150–153; bloco do Step 4 acrescentado neste PR).
- [`roadmap.md`](../../roadmap.md) — Step 4 (1215–1428); Step 5 (1434–1482); Step 7 (1571–1614);
  Step 8 (1644–1665); tabela de Stages (123); ROADMAP-1/3/6 (1725–1730); 1719–1720; 816–820.
- [`workforce.md`](../staff/workforce.md) — §1, §2, §3.1–§3.6, §3.8, §4, §6, §7. Citado por seção
  porque ganha notas datadas neste PR.
- ADRs do gate: [4.1.0001](../../adr/4_1_0001-every-saved-change-is-the-live-schedule.md) (F1+F8) ·
  [4.1.0002](../../adr/4_1_0002-weekly-period-operational-day-and-allocation-hours.md) (F2+corte+F3) ·
  [4.1.0003](../../adr/4_1_0003-v1-validation-policy-set-defaults-and-modes.md) (F4) ·
  [4.1.0004](../../adr/4_1_0004-hr-reads-schedules-in-member-units.md) (F5) ·
  [4.1.0005](../../adr/4_1_0005-unit-timezone-owned-by-identity.md) (F6) ·
  [4.1.0006](../../adr/4_1_0006-termination-reconciled-on-read-and-guarded-delete-by-reverse-port.md)
  (F7 + remoção definitiva; F9 vive no 4.1.0003 (f)).
- [ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md) — categoria
  `domain/`. [ADR 0.0.0005](../../adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)
  — tenant do token; unidade no endereço (134–148, 159, 280–287).
- [ADR 2.1.0001](../../adr/2_1_0001-identity-aggregates-and-membership.md) — memberships e
  visibilidade. [ADR 2.2.0002](../../adr/2_2_0002-authorization-two-axes-fail-closed.md) — ordem de
  autorização (60–78); `employee` sem permissão (231–234); `platform_admin` (47–49).
  [ADR 2.4.0003](../../adr/2_4_0003-authorization-composition-at-boundary.md) — conjunto de
  permissões exigidas por rota (§Decision 1). [ADR 2.5.0001](../../adr/2_5_0001-email-sender-in-shared.md)
  — `EmailSender` em `shared`; 4.6 como segundo consumidor (69, 110).
- [ADR 3.1.0001](../../adr/3_1_0001-workforce-gate-modeling-decisions.md) — semi-aberto (i); carga
  única, teto em scheduling (ii); cópia sem `user_id` (iii). [ADR 3.1.0002](../../adr/3_1_0002-minimal-employee-record-attributes.md)
  — nome de exibição; e-mail de publicação ao login (30–35). [ADR 3.1.0004](../../adr/3_1_0004-shift-preference-scope-and-cardinality.md)
  — preferência é sinal soft (109–112). [ADR 3.1.0005](../../adr/3_1_0005-naive-wall-clock-unavailability-datetimes.md)
  — wall-clock; fuso fora de staff (28–31); conversão pelo consumidor (41–46, 84–88).
  [ADR 3.1.0006](../../adr/3_1_0006-employee-function-set-cardinality.md) — casa vagas de qualquer
  função (48–50, 69–73, 83).
- [ADR 3.2.0003](../../adr/3_2_0003-copy-employee-full-duplication.md) — cópia carrega
  indisponibilidades (104–107); wall-clock entre fusos (177–183). [ADR 3.2.0006](../../adr/3_2_0006-employee-lifecycle-and-guarded-deletion.md)
  — desligado sai do seletor (40–41); histórico (42–43); sem `Clock` (155–157); "FK" (177–178;
  errata 2026-09-14).
  [ADR 3.2.0007](../../adr/3_2_0007-terminated-employee-remains-editable.md) — recontratação
  explícita (122–124).
- [ADR 3.3.0001](../../adr/3_3_0001-staff-schema-tenant-scoping-and-composite-fk-cerco.md) — regimes
  de tempo no banco (159–164). [ADR 3.3.0002](../../adr/3_3_0002-no-cross-bounded-context-foreign-keys.md)
  — sem FK entre BCs (57–63; 94–101). [ADR 3.3.0006](../../adr/3_3_0006-transactional-atomicity-without-optimistic-locking.md)
  — last write wins; controle otimista escalado (91–98).
- [ADR 3.4.0001](../../adr/3_4_0001-staff-owned-access-guard-port.md) — port de acesso próprio
  (59–64); `ignore_imports` rejeitado (101–118); promoção a `shared` adiada (128–135).
  [ADR 3.4.0002](../../adr/3_4_0002-staff-http-error-status-mapping.md) — `EmployeeInUseError`
  (112–113; errata 2026-09-14). [ADR 3.4.0006](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md) —
  sponsor 2026-08-12 (§1); restrição sobre `hr` (§3 — errata 2026-09-13); famílias (§4); expansão
  de identity autorizada (§5); citado por seção porque ganha errata neste PR.
  [ADR 3.4.0007](../../adr/3_4_0007-unit-enters-the-employee-address.md) — unidade no endereço
  (57–70, 95–101). [ADR 3.4.0008](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md)
  — dispensa por permissão (56–71, 79–83); issue #41 (88–92).
- [ADR 3.6.0001](../../adr/3_6_0001-path-addresses-the-record-not-the-authorized-scope.md) — o path
  endereça o registro. [ADR 3.6.0003](../../adr/3_6_0003-wire-representation-preserves-domain-guarantees.md)
  — forma na borda (precedente para a 4.5).
- `docs/stages/3.1-staff-domain/concept.md` 63–65, 376–381; `docs/stages/3.2-staff-application/
  concept.md` 301–308, 725; `docs/stages/3.3-staff-persistence/concept.md` 691–696;
  `docs/stages/3.6-staff-http/concept.md` 926–933.
- Código mergeado (`origin/develop` `95fba00`): `features/identity/domain/value_objects/{role,permission}.py`;
  `features/identity/domain/entities/{user,unit}.py`; `features/staff/domain/value_objects/
  {identifiers,workload_profile,shift_preference,unavailability_period}.py`;
  `features/staff/domain/entities/{employee,job_function}.py`; `features/staff/application/
  ports/out/{employee_repository,access_guard}.py`; `shared/application/ports/out/{clock,
  email_sender}.py`; `.importlinter` (219–228).
- Decisões de kickoff (memória do projeto, 2026-07-16/19; `workforce.md` §7): #5, #7, #9, #10,
  #11, #13.
- Decisões do sponsor de 2026-09-13 (F1–F6, F8, corte 05:00) e de 2026-09-14 (F7, remoção
  definitiva, F9) e de 2026-09-26 (sobre-cobertura) — registro literal em `gate-decisions.md` da
  sessão do gate (e citado verbatim nos ADRs 4.1.0001–4.1.0006, que são a fonte durável); a pesquisa de
  arquitetura de F7 em `f7-architecture-research.md` (fontes primárias citadas no ADR 4.1.0006);
  citadas nos ADRs 4.1.0001–4.1.0006 e em §6.

### Fontes primárias — legislação trabalhista (sustentam defaults e limites de §3.6; verificadas no Planalto por download direto em 2026-09-13)

> BRASIL. **Constituição da República Federativa do Brasil de 1988**, art. 7º, incisos XIII e XV.
> Texto consolidado. Brasília: Presidência da República. Disponível em:
> https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm. Acesso em: 13 set. 2026.
>
> BRASIL. **Decreto-Lei nº 5.452, de 1º de maio de 1943** (Consolidação das Leis do Trabalho),
> arts. 58, *caput* (redação original); 58-A, *caput* (Lei nº 13.467/2017); 59, *caput* (Lei nº
> 13.467/2017), § 2º (MP nº 2.164-41/2001), §§ 5º e 6º (Lei nº 13.467/2017); 59-A (Lei nº
> 13.467/2017); 61, § 2º; 66 (redação original, nunca alterada); 67 e 68 (redação original — a
> redação da MP nº 905/2019 teve vigência encerrada); 70 (Decreto-Lei nº 229/1967); 71, *caput* e
> §§ 1º–2º (redação original); 73, §§ 1º, 2º e 4º (Decreto-Lei nº 9.666/1946); 74, §§ 2º e 4º
> (Lei nº 13.874/2019); 611-A, *caput* e incisos I–III, e 611-B, inciso IX e parágrafo único
> (Lei nº 13.467/2017). Texto consolidado. Brasília: Presidência da República. Disponível em:
> https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em: 13 set. 2026.
>
> BRASIL. **Lei nº 605, de 5 de janeiro de 1949**. Repouso semanal remunerado e o pagamento de
> salário nos dias feriados civis e religiosos, art. 1º (redação original; as alterações da MP nº
> 905/2019 tiveram vigência encerrada). Disponível em:
> https://www.planalto.gov.br/ccivil_03/leis/l0605.htm. Acesso em: 13 set. 2026.
>
> BRASIL. **Lei nº 10.101, de 19 de dezembro de 2000**, art. 6º, *caput* e parágrafo único, com
> redação dada pela **Lei nº 11.603, de 5 de dezembro de 2007** (a revogação pela MP nº 905/2019
> teve vigência encerrada). Disponível em: https://www.planalto.gov.br/ccivil_03/leis/l10101.htm.
> Acesso em: 13 set. 2026.
>
> BRASIL. **Decreto nº 10.854, de 10 de novembro de 2021**, arts. 153, parágrafo único; 154, §§ 2º
> e 4º; 158, § 4º — *"Considera-se semana, para fins de pagamento de remuneração, o período de
> segunda-feira a domingo que antecede o dia determinado como repouso semanal remunerado."*
> (definição para remuneração do RSR, não para calendário de escala — sustenta só a segunda-feira
> como **default** de dia de início, que o sponsor deixou configurável); e 187, I (revoga o
> Decreto nº 27.048/1949). Disponível em:
> https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/decreto/D10854.htm. Acesso em: 13 set.
> 2026.
>
> BRASIL. **Decreto nº 27.048, de 12 de agosto de 1949** (REVOGADO pelo Decreto nº 10.854/2021),
> relação anexa ao art. 7º, item "Hotéis e similares (restaurantes, pensões, bares, cafés…)".
> Citado **apenas como evidência histórica** (HALT H3). Disponível em:
> https://www.planalto.gov.br/ccivil_03/decreto/1930-1949/d27048.htm. Acesso em: 13 set. 2026.
>
> BRASIL. **Decreto nº 9.772, de 25 de abril de 2019**. Encerra a hora de verão no território
> nacional, art. 1º. Disponível em:
> https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/decreto/D9772.htm. Acesso em: 13 set.
> 2026.
>
> (Notas de vigência lidas no consolidado do Planalto: a **MP nº 905/2019** alterou os arts. 67,
> 68 e 70 da CLT — não o 66 —, a Lei 605/1949 e os arts. 6º–6º-B da Lei 10.101/2000; foi revogada
> pela **MP nº 955/2020**, que também teve vigência encerrada — as redações anteriores voltaram a
> viger. A **MP nº 808/2017** consta como "Vigência encerrada".)

### Fontes primárias — ato infralegal NÃO VERIFICADO (HALT H3)

> BRASIL. Ministério do Trabalho e Previdência. **Portaria MTP nº 671, de 8 de novembro de 2021**,
> Anexo IV (atividades autorizadas em caráter permanente ao trabalho aos domingos e feriados —
> art. 154, § 4º, do Decreto nº 10.854/2021). DOU 11/11/2021, Seção 1, p. 217. URL indicada:
> https://www.in.gov.br/en/web/dou/-/portaria-mtp-n-671-de-8-de-novembro-de-2021-361085816 —
> **devolve HTTP 404 em 13 set. 2026 e 403 em 14 set. 2026** (a URL pode estar errada; a versão compilada em gov.br
> devolve "Conteúdo Restrito"). **Conteúdo não obtido; não sustenta regra neste doc.**

### Fontes primárias — jurisprudência (TST; texto confirmado em acórdão do backend oficial, não na página canônica de súmulas)

> BRASIL. Tribunal Superior do Trabalho. **Orientação Jurisprudencial nº 355 da SBDI-1** ("O
> desrespeito ao intervalo mínimo interjornadas previsto no art. 66 da CLT acarreta, por analogia,
> os mesmos efeitos previstos no § 4º do art. 71 da CLT e na Súmula nº 110 do TST, devendo-se
> pagar a integralidade das horas que foram subtraídas do intervalo, acrescidas do respectivo
> adicional") e **Súmula nº 110** ("No regime de revezamento, as horas trabalhadas em seguida ao
> repouso semanal de 24 horas, com prejuízo do intervalo mínimo de 11 horas consecutivas para
> descanso entre jornadas, devem ser remuneradas como extraordinárias…"). Ambas transcritas no
> acórdão **TST-RR-1009-03.2014.5.12.0016** (3ª Turma, Rel. Min. Mauricio Godinho Delgado,
> Brasília, 17/08/2016), que cita como precedente o RR-587-39.2011.5.09.0041 (4ª Turma, DEJT
> 29/08/2014 — "O referido entendimento pode ser também aplicado aos demais empregados regidos
> pela CLT"). Disponível em:
> https://jurisprudencia-backend2.tst.jus.br/rest/documentos/714434b5f87efd0dcf3f5eb4171a6706.
> Acesso em: 13 set. 2026. (Verificação deste gate: o documento nessa URL é o acórdão
> RR-1009-03.2014.5.12.0016, não o RR-587-39, como constava no levantamento externo da sessão.)
>
> BRASIL. Tribunal Superior do Trabalho. **Súmula nº 444** (12x36 "em caráter excepcional …
> ajustada exclusivamente mediante acordo coletivo de trabalho ou convenção coletiva"). Transcrita
> no acórdão TST-RR-29800-32.2009.5.17.0011 (26/11/2014). Disponível em:
> https://jurisprudencia-backend2.tst.jus.br/rest/documentos/6f4e26b667217defc1c7671a8f88e5da.
> Acesso em: 13 set. 2026. (Anterior à Lei nº 13.467/2017, que no art. 59-A admite o regime por
> acordo individual escrito — citada com essa ressalva.)

### Fontes primárias — método: calendário e fuso horário (documentação oficial / PEP / IANA; verificadas em 2026-09-13)

> PYTHON SOFTWARE FOUNDATION. **datetime — Basic date and time types**: `date.isoweekday()`
> ("Monday is 1 and Sunday is 7"), `date.isocalendar()` ("a week starts on a Monday and ends on
> a Sunday"). The Python Standard Library, Python 3. Disponível em:
> https://docs.python.org/3/library/datetime.html. Acesso em: 13 set. 2026. (Âncora para a
> convenção ISO 8601; a norma ISO em si é paga e não foi consultada. Sustenta a segunda-feira
> como **default** — o dia de início é configurável, F2.)
>
> PYTHON SOFTWARE FOUNDATION. **zoneinfo — IANA time zone support**. The Python Standard Library,
> Python 3. Disponível em: https://docs.python.org/3/library/zoneinfo.html. Acesso em: 13 set.
> 2026.
>
> GANSSLE, Paul. **PEP 615 – Support for the IANA Time Zone Database in the Standard Library**.
> Python Enhancement Proposals, 2020 (Final; Python 3.9). Disponível em:
> https://peps.python.org/pep-0615/. Acesso em: 13 set. 2026.
>
> BELOPOLSKY, Alexander; PETERS, Tim. **PEP 495 – Local Time Disambiguation**. Python Enhancement
> Proposals, 2015 (Final; Python 3.6). Disponível em: https://peps.python.org/pep-0495/. Acesso
> em: 13 set. 2026.
>
> IANA — INTERNET ASSIGNED NUMBERS AUTHORITY. **Time Zone Database** (tz / zoneinfo), tzdata
> 2026d (2026-09-11). Disponível em: https://www.iana.org/time-zones. Acesso em: 13 set. 2026.

### Fontes setoriais (sustentam terminologia, não regra — overview §10)

Factorial HR, Shifton, Goomer, EPOC, GastronoMundo, Saipos, tio.digital, Fecomercio — listadas em
[`overview.md`](../../overview.md) §10 (pesquisa de terminologia, jul/2026). Nenhuma regra deste
doc se apoia nelas.

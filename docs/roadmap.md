---
title: Roadmap — restaurant-hub
description: Divisão do restaurant-hub em Steps (entregas de negócio) e Stages (unidades técnicas atômicas) — do bootstrap ao hub v1, com backlog de módulos futuros
when-use: Consultar antes de iniciar nova Stage; atualizar ao fechar qualquer Stage
keywords: [roadmap, steps, stages, planejamento, escala, saas, restaurantes]
status: in_progress
created_at: 2026-07-10
updated_at: 2026-11-02
last_reviewed_at: 2026-11-02
---

# Roadmap — restaurant-hub

> **Hierarquia (ver [`PIPELINE.md`](./PIPELINE.md) §4):**
> - **Step:** entrega de negócio. Sem restrição arquitetural. Agrupa Stages.
>   Vive apenas neste documento.
> - **Stage:** unidade atômica de ciclo concept→technical→execução. 1 camada
>   do hexagonal **ou** 1 fatia vertical, 1 DoD testável, 1 bounded context,
>   complexidade ≤ M. Tem pasta `docs/stages/N.M-<slug>/` e branch
>   `feat/<num-issue>-<N-M>-<slug>` (ver `CONVENTIONS.md` §4).
> - **Task:** 1 commit. Vive no `technical.md` da Stage.
>
> **Regra de atualização:** ao marcar uma Stage como `done`, atualizar
> `updated_at` e `last_reviewed_at` no mesmo merge (ou em PR de docs
> imediato). Não opcional.
>
> **Escopo deste roadmap:** governa o **repositório backend**. O frontend
> (`restaurant-hub-frontend`) tem roadmap próprio espelhando os mesmos Steps
> de produto (ver ROADMAP-2). Um Step de produto só é `done` quando backend
> **e** frontend correspondentes entregam.

## Visão geral

```mermaid
graph LR
  subgraph Step1[Step 1 — Fundação]
    S11[1.1-bootstrap] --> S12[1.2-ci]
  end
  subgraph Step2[Step 2 — Restaurante e acesso]
    S21[2.1-identity-domain] --> S22[2.2-identity-application]
    S22 --> S23[2.3-identity-persistence]
    S23 --> S24[2.4-identity-http]
    S24 --> S25[2.5-email-invite]
    S26[2.6-identity-unit-of-work]
  end
  subgraph Step3[Step 3 — Equipe]
    S31[3.1-staff-domain] --> S32[3.2-staff-application]
    S32 --> S33[3.3-staff-persistence]
    S33 --> S34[3.4-staff-access-scope]
    S34 --> S36[3.6-staff-http]
    S36 --> S35[3.5-employee-login-link] --> S37[3.7-application-authorization] & S38[3.8-termination-access-scope]
    S36 --> S39[3.9-error-hierarchy]
  end
  subgraph Step4[Step 4 — Escala manual]
    S41[4.1-scheduling-domain] --> S42[4.2-validation-policies]
    S42 --> S43[4.3-scheduling-application]
    S43 --> S44[4.4-scheduling-persistence]
    S44 --> S45[4.5-scheduling-http]
    S45 --> S46[4.6-schedule-notifications]
    S45 --> S47[4.7-schedule-image]
  end
  subgraph Step5[Step 5 — Auto-preenchimento]
    S51[5.1-autofill-domain] --> S52[5.2-autofill-delivery]
  end
  subgraph Step6[Step 6 — Implantação piloto]
    S61[6.1-hosting-study] --> S62[6.2-deploy-pipeline]
    S62 --> S63[6.3-ops-baseline]
  end
  subgraph Step7[Step 7 — Ponto Control iD]
    S71[7.1-controlid-spike] --> S72[7.2-timeclock-domain]
    S72 --> S73[7.3-controlid-adapter]
    S73 --> S74[7.4-timeclock-delivery]
  end
  subgraph Step8[Step 8 — Hub v1]
    S81[8.1-hub-read-models] --> S82[8.2-hub-http]
  end
  S12 --> S21
  S25 --> S31
  S35 --> S26
  S31 --> S41
  S47 --> S51
  S45 --> S61
  S12 --> S71
  S45 --> S72
  S74 --> S81
  S52 --> S81
  S43 --> S39
```

## Tabela de Steps

| ID | Step | Resultado de negócio | Status | Stages |
|---|---|---|---|---|
| 1 | Fundação do repositório | Repo com scaffolding hexagonal, gates locais e CI verdes | done | 1.1 → 1.2 |
| 2 | Restaurante e acesso | Restaurante (tenant) e unidades existem no sistema; pessoas entram com papel certo (dono/gerente/RH/funcionário + admin plataforma) | in_progress | 2.1 → 2.6 |
| 3 | Equipe da unidade | Gerente cadastra funções customizadas e funcionários com jornada (fixa/sob demanda), preferências e indisponibilidades | in_progress | 3.1 → 3.9 |
| 4 | Escala manual publicável | Gerente monta, valida e publica a escala; funcionário consulta; planilha/papel aposentados | in_progress | 4.1 → 4.7 |
| 5 | Auto-preenchimento | Escala se monta sozinha respeitando regras e justiça distributiva; gerente só ajusta | not_started | 5.1 → 5.2 |
| 6 | Implantação piloto | Sistema no ar para o restaurante piloto usar no dia a dia | not_started | 6.1 → 6.3 |
| 7 | Ponto (Control iD) | Previsto × realizado visível sem conferência manual | not_started | 7.1 → 7.4 |
| 8 | Hub v1 | Diretores analisam a operação (cobertura, cumprimento, extras) por unidade e na Unidade Geral | not_started | 8.1 → 8.2 |
| 9 | Estoque de insumos | Entrada por NF, baixa por fechamento × ficha técnica, alertas de reposição | not_started | a decompor |
| 10 | Integração Eyemobile | Fechamento de caixa entra sozinho no sistema | not_started | a decompor |
| 11 | Pedidos em mesa | Cliente pede por tablet na mesa ou QR code | not_started | a decompor |
| 12 | Delivery | Entregadores e rotas gerenciados | not_started | a decompor |
| 13 | Auto-cadastro e cobrança | Dono se cadastra, paga e usa sem intervenção do admin | not_started | a decompor |

**Legenda de status (Step):** `not_started`, `in_progress`, `blocked`, `done`, `deprecated`.

## Tabela de Stages

| Stage | Título | Camada-alvo | Status | Depende de |
|---|---|---|---|---|
| `1.1-bootstrap` | Bootstrap do projeto | bootstrap | done | — |
| `1.2-ci` | CI no GitHub Actions | bootstrap | done | `1.1-bootstrap` |
| `2.1-identity-domain` | Domínio de tenancy e acesso | domain | done | `1.2-ci` |
| `2.2-identity-application` | Use cases de tenancy e acesso | application | done | `2.1-identity-domain` |
| `2.3-identity-persistence` | Persistência de identity | adapters/out/postgres | done | `2.2-identity-application` |
| `2.4-identity-http` | API de tenancy, usuários e auth | adapters/inbound/http | done | `2.3-identity-persistence` |
| `2.5-email-invite` | Convite por e-mail | vertical (identity) | done | `2.4-identity-http` |
| `2.6-identity-unit-of-work` | Fronteira transacional nos use cases de identity que escrevem mais de uma vez | application + adapters/out/postgres + tooling | done | `3.5-employee-login-link` |
| `3.1-staff-domain` | Domínio de equipe | domain | done | `2.5-email-invite` |
| `3.2-staff-application` | Use cases de equipe | application | done | `3.1-staff-domain` |
| `3.3-staff-persistence` | Persistência de staff | adapters/out/postgres | done | `3.2-staff-application` |
| `3.4-staff-access-scope` | Acesso e escopo de equipe | identity (domain+application) + staff (domain, application, adapters/out) | done | `3.3-staff-persistence` |
| `3.6-staff-http` | API de equipe | adapters/inbound/http | done | `3.4-staff-access-scope` |
| `3.5-employee-login-link` | Criar login para funcionário | vertical (staff) + identity (domain, application) | done | `3.6-staff-http` |
| `3.7-application-authorization` | Autorização na camada application de staff | application | done | `3.5-employee-login-link` |
| `3.8-termination-access-scope` | Desligamento corta só o acesso que o registro concede | vertical (staff) + identity (application, fachada) | done | `3.5-employee-login-link` |
| `3.9-error-hierarchy` | Hierarquia de exceções sem protocolo HTTP | shared (domain + application) + identity/staff/scheduling (application, adapters/inbound/http) | done | `3.6-staff-http`, `4.3-scheduling-application`, #45 |
| `4.1-scheduling-domain` | Domínio da escala | domain | done | `3.1-staff-domain` |
| `4.2-validation-policies` | Políticas de validação configuráveis | domain | done | `4.1-scheduling-domain` |
| `4.3-scheduling-application` | Use cases da escala | application | done | `4.2-validation-policies` |
| `4.4-scheduling-persistence` | Persistência da escala + auditoria | adapters/out/postgres | draft | `4.3-scheduling-application` |
| `4.5-scheduling-http` | API do editor e consulta de escala | adapters/inbound/http | draft | `4.4-scheduling-persistence` |
| `4.6-schedule-notifications` | Notificação de publicação por e-mail | vertical (scheduling) | draft | `4.5-scheduling-http` |
| `4.7-schedule-image` | Imagem/tabela da escala sob demanda | vertical (scheduling) | draft | `4.5-scheduling-http` |
| `5.1-autofill-domain` | Algoritmo de auto-preenchimento | domain | draft | `4.7-schedule-image` |
| `5.2-autofill-delivery` | Preview e aplicação do auto-fill | vertical (scheduling) | draft | `5.1-autofill-domain` |
| `6.1-hosting-study` | Estudo de hospedagem (ADR) | bootstrap | draft | `4.5-scheduling-http` |
| `6.2-deploy-pipeline` | CD para development/production | bootstrap | draft | `6.1-hosting-study` |
| `6.3-ops-baseline` | Backup, healthcheck e runbook | shared/infrastructure | draft | `6.2-deploy-pipeline` |
| `7.1-controlid-spike` | Spike API Control iD (ASSUM-1) | bootstrap | draft | `1.2-ci` |
| `7.2-timeclock-domain` | Domínio de ponto e conciliação | domain | draft | `7.1-controlid-spike`, `4.5-scheduling-http` |
| `7.3-controlid-adapter` | Adapter Control iD | adapters/out/controlid | draft | `7.2-timeclock-domain` |
| `7.4-timeclock-delivery` | Relatório previsto × realizado | vertical (timeclock) | draft | `7.3-controlid-adapter` |
| `8.1-hub-read-models` | Read models do hub | application | draft | `7.4-timeclock-delivery`, `5.2-autofill-delivery` |
| `8.2-hub-http` | API dos painéis + Unidade Geral | adapters/inbound/http | draft | `8.1-hub-read-models` |

**Legenda de status (Stage):** `draft`, `in_progress`, `review`, `done`, `archived`.

## Tabela de Issues

Issues **avulsas** — trabalho cujo concept+technical cabem no corpo da issue (fix, docs,
chore), sem pasta de Stage. O litmus está em [`PIPELINE.md`](./PIPELINE.md) §4.5: se o corpo
vira um mini-concept, **promova a Stage**. Issue de Stage não entra aqui — vive na Tabela de
Stages, e seu número fica no `issue_id` do `technical.md`.

| Issue | Título | BC | Camada-alvo | Status | Depende de |
|---|---|---|---|---|---|
| [#2](https://github.com/MarceloSanC/restaurant-hub/issues/2) | Adaptar fluxo de Step (prompt, ADR e gates) ao restaurant-hub | shared | docs + scripts | done | — |
| [#6](https://github.com/MarceloSanC/restaurant-hub/issues/6) | Plugar `configure_logging` no boot da aplicação | shared | shared/infrastructure + bootstrap | done | — |
| [#7](https://github.com/MarceloSanC/restaurant-hub/issues/7) | Alinhar hook mirrors-mypy e prevenir drift de versão dos hooks pre-commit | shared | tooling | done | — |
| [#8](https://github.com/MarceloSanC/restaurant-hub/issues/8) | Definir política de fim de linha com `.gitattributes` e renormalizar | shared | repo | done | — |
| [#10](https://github.com/MarceloSanC/restaurant-hub/issues/10) | Ativar modo autônomo para as stages 1.2→3.5 (ADR 0.0.0004 accepted) | shared | docs | done | — |
| [#12](https://github.com/MarceloSanC/restaurant-hub/issues/12) | Padronizar placeholders de Stage que viram comando (stage_id × número) | shared | docs + tooling | done | — |
| [#16](https://github.com/MarceloSanC/restaurant-hub/issues/16) | `check_stage_issue.py` aprova issue CLOSED (busca state mas não usa) | shared | tooling | done | — |
| [#26](https://github.com/MarceloSanC/restaurant-hub/issues/26) | Registrar no log a causa suprimida dos 401/403 | identity | adapters/inbound/http | done | #6 |
| [#29](https://github.com/MarceloSanC/restaurant-hub/issues/29) | Doc de domínio do BC staff — gate do Step 3 | staff | docs | done | — |
| [#30](https://github.com/MarceloSanC/restaurant-hub/issues/30) | Backfill do doc de domínio de identity — pendência do gate do Step 2 | identity | docs | done | — |
| [#34](https://github.com/MarceloSanC/restaurant-hub/issues/34) | Promover o sufixo `[N.M/task-NN-fix]` de commits de correção de checkpoint a convenção | shared | docs + tooling | done | — |
| [#37](https://github.com/MarceloSanC/restaurant-hub/issues/37) | Varrer `workforce.md` contra os ADRs 3.1.x — três lacunas declaradas abertas já foram fechadas | staff | docs | done | — |
| [#41](https://github.com/MarceloSanC/restaurant-hub/issues/41) | Habilitação de função de trabalho por unidade (função segue do restaurante; gerente cria para a sua unidade, alcance extra-unidade para todas) | staff | domain + application + adapters/out | open | `3.4-staff-access-scope` |
| [#45](https://github.com/MarceloSanC/restaurant-hub/issues/45) | Gates para as violações de arquitetura invisíveis aos contratos de import | shared | tooling + tests | done | — |
| [#47](https://github.com/MarceloSanC/restaurant-hub/issues/47) | Mover o tradutor de acesso do composition root para `adapters/out/identity` | staff | adapters/out + composition_root | done | #43, #45 |
| [#52](https://github.com/MarceloSanC/restaurant-hub/issues/52) | Doc de domínio do BC scheduling — gate do Step 4 | scheduling | docs | done | — |
| [#56](https://github.com/MarceloSanC/restaurant-hub/issues/56) | Harness: triagem por evidência, subagentes de pesquisa, guard de worktree e validação de skills | shared | tooling + docs | done | — |
| [#58](https://github.com/MarceloSanC/restaurant-hub/issues/58) | `worktree-new.py` não reescreve `DATABASE_URL` — integração da worktree roda contra o Postgres do checkout principal | shared | tooling + docs | done | — |
| [#59](https://github.com/MarceloSanC/restaurant-hub/issues/59) | Fechar os achados documentais da auditoria pós-merge da Stage 3.5 | staff | docs | done | #51 |
| [#61](https://github.com/MarceloSanC/restaurant-hub/issues/61) | `Cache-Control: no-store` nas respostas que carregam token ou link de definição de senha | shared | adapters/inbound/http | done | — |
| [#65](https://github.com/MarceloSanC/restaurant-hub/issues/65) | Trazer do financial-forecasting o harness posterior à #56 | shared | tooling + docs | open | #56 |
| [#67](https://github.com/MarceloSanC/restaurant-hub/issues/67) | Compor o provisionamento restaurante + dono numa unidade de trabalho (gatilho do ADR 2.4.0003) | identity | application + adapters/inbound/http | done | `2.6-identity-unit-of-work` |
| [#68](https://github.com/MarceloSanC/restaurant-hub/issues/68) | Edição concorrente do registro não pode apagar o vínculo de login (`user_id` condicional) | staff | application + adapters/out | done | — |
| [#75](https://github.com/MarceloSanC/restaurant-hub/issues/75) | Negar na application de staff ator que o guard não emitiu (drivers fora da borda HTTP) | staff | application | open | `3.7-application-authorization` |
| [#76](https://github.com/MarceloSanC/restaurant-hub/issues/76) | Validar identificador fora da borda HTTP antes de autorizar | staff | application | open | `3.7-application-authorization` |
| [#77](https://github.com/MarceloSanC/restaurant-hub/issues/77) | Trocar o ponteiro `(#49)` da fachada de identity e do ADR 3.5.0001 pelo ADR 3.7.0001 | identity | docs + application (fachada) | done | `3.7-application-authorization` |
| [#78](https://github.com/MarceloSanC/restaurant-hub/issues/78) | Medir sob carga o custo da dupla autorização de staff (borda + use case) | staff | ops (medição) | blocked | `6.3-ops-baseline` |
| [#79](https://github.com/MarceloSanC/restaurant-hub/issues/79) | Citar o roadmap por âncora estável em vez de número de linha (gate no `docs-check`) | shared | docs + tooling | done | — |
| [#81](https://github.com/MarceloSanC/restaurant-hub/issues/81) | Merge do auditor de dentro da worktree não apaga a branch remota | shared | docs + tooling | done | — |
| [#82](https://github.com/MarceloSanC/restaurant-hub/issues/82) | Tripwire para campo de credencial em resposta que nasça sem a marca `x-credential` (especulativa; disparo: rota de reemissão do link ou primeiro frontend do Step 3) | shared | tests (e2e) | open | #61 |
| [#84](https://github.com/MarceloSanC/restaurant-hub/issues/84) | Worktree nova pode herdar a porta de um Postgres órfão | shared | tooling | done | #58 |
| [#85](https://github.com/MarceloSanC/restaurant-hub/issues/85) | `make migrate` e `make run` sem a guarda da `DATABASE_URL` da worktree | shared | tooling | done | #58 |
| [#86](https://github.com/MarceloSanC/restaurant-hub/issues/86) | `migrations/env.py` ignora a `sqlalchemy.url` passada pelo chamador | shared | migrations + tests | done | #58 |
| [#87](https://github.com/MarceloSanC/restaurant-hub/issues/87) | Mutação noturna morre na coleta — `.claude/` fora do `also_copy` | shared | tooling + ci | done | — |
| [#90](https://github.com/MarceloSanC/restaurant-hub/issues/90) | Hook `commit-msg` aceita a Stage como escopo de commit | shared | tooling | done | — |
| [#91](https://github.com/MarceloSanC/restaurant-hub/issues/91) | `scripts/` fora do `mypy --strict` e do gate de cobertura | shared | tooling | open | — |
| [#93](https://github.com/MarceloSanC/restaurant-hub/issues/93) | Política de fim de linha do editor — VS Code grava CRLF em arquivo novo (especulativa; disparo: aviso no uso diário ou primeiro colaborador externo) | shared | repo | open | #8 |
| [#97](https://github.com/MarceloSanC/restaurant-hub/issues/97) | Nenhum teste trava a ligação dos validadores de docs no target `docs-check` do `Makefile` | shared | tooling + tests | open | #12 |
| [#98](https://github.com/MarceloSanC/restaurant-hub/issues/98) | Passo 1 do RUNBOOK usa `$issue` antes de defini-la | shared | docs | open | — |
| [#99](https://github.com/MarceloSanC/restaurant-hub/issues/99) | `make check` sem conferência de formatação e lint fora de `migrations/` | shared | tooling | done | #7 |
| [#100](https://github.com/MarceloSanC/restaurant-hub/issues/100) | Hooks do git compartilhados apontam para o venv de uma worktree — `worktree-rm` quebra os commits das demais | shared | tooling | done | #7 |
| [#102](https://github.com/MarceloSanC/restaurant-hub/issues/102) | Frontmatter YAML e `references` dos docs de ADR e de domínio sem validação no `docs-check` | shared | tooling | done | — |
| [#105](https://github.com/MarceloSanC/restaurant-hub/issues/105) | Identificadores locais do domínio de scheduling em inglês | scheduling | domain | done | — |
| [#106](https://github.com/MarceloSanC/restaurant-hub/issues/106) | Edição da configuração de validação e calendário do restaurante sem dono no roadmap | scheduling | application | open | `4.3-scheduling-application` |
| [#107](https://github.com/MarceloSanC/restaurant-hub/issues/107) | Vincular login existente a registro de funcionário | staff | application + identity (fachada) | open | — |
| [#108](https://github.com/MarceloSanC/restaurant-hub/issues/108) | Remoção concorrente com R17 não pode apagar registro já vinculado (conta órfã) | staff | application + adapters/out | done | #68 |
| [#114](https://github.com/MarceloSanC/restaurant-hub/issues/114) | Provisionar o dono do restaurante por convite em vez de senha escolhida pela plataforma | identity | application + adapters/inbound/http | open | #67 |
| [#115](https://github.com/MarceloSanC/restaurant-hub/issues/115) | Autorizar o próprio alvo nos use cases de identity (formato da 3.7) | identity | application | open | #67 |
| [#116](https://github.com/MarceloSanC/restaurant-hub/issues/116) | Citações por número de linha a `docs/domain/**` sem gate; válvula de `references` do `shift-scheduling.md` depende delas | shared | tooling | open | #102 |
| [#117](https://github.com/MarceloSanC/restaurant-hub/issues/117) | Tabela consolidada de lacunas do `shift-scheduling.md` §6 sem guarda, com linhas de Stages `done` | scheduling | docs | open | #102 |
| [#127](https://github.com/MarceloSanC/restaurant-hub/issues/127) | Comentário de `role.py` ainda proíbe toda permissão de escala ao `hr` — superado pelo ADR 4.1.0004 | identity | domain (comentário) | open | #30 |
| [#128](https://github.com/MarceloSanC/restaurant-hub/issues/128) | ADR 2.5.0002 §5 descreve um reconvite que o concept 2.5 recusa com 409 | identity | docs | open | #30 |
| [#129](https://github.com/MarceloSanC/restaurant-hub/issues/129) | Numeração das decisões de kickoff diverge entre ADRs, concepts e código | shared | docs | open | #30 |
| [#132](https://github.com/MarceloSanC/restaurant-hub/issues/132) | Workers do mutmut disputam o mesmo Postgres — mortes falsas na corrida de mutação | shared | tooling + ci | open | #87 |
| [#134](https://github.com/MarceloSanC/restaurant-hub/issues/134) | Identificadores locais em português na application de scheduling (`_UM_DIA`) | scheduling | application + adapters | open | #105 |
| [#135](https://github.com/MarceloSanC/restaurant-hub/issues/135) | Identificadores em português na application e nos adapters de staff | staff | application + adapters | open | #105 |
| [#136](https://github.com/MarceloSanC/restaurant-hub/issues/136) | Identificadores em português no BC identity | identity | todas as camadas | open | #105 |
| [#137](https://github.com/MarceloSanC/restaurant-hub/issues/137) | Identificadores em português no kernel compartilhado | shared | infrastructure | open | #105 |

**Legenda de status (issue):** `open`, `blocked`, `placeholder`, `done`. Vocabulário ditado pelo
consumidor desta tabela, [`PROMPT-issue-single-session.md`](./PROMPT-issue-single-session.md):
`placeholder` = marcador de backlog sem DoD (não implementar direto); `blocked` = dependência
externa não resolvida; `done` é o estado final que o prompt grava ao fechar (§DoD).

---

## Detalhamento por Step

### Step 1 — Fundação do repositório

- **Resultado de negócio:** projeto pronto para receber features com gates de qualidade automáticos (lint, types, testes, layout) locais e no GitHub.
- **Depende de:** —
- **Tamanho estimado:** S–M

#### Stage 1.1 — `1.1-bootstrap`

**Descrição humana:** validar e completar o scaffolding copiado do template no **Windows nativo**: `make setup`/`check`/`test` verdes e reprodutíveis (Makefile shell-agnostic, `uv.lock` versionado com lock-check), pre-commit ativo, import-linter refletindo LAYOUT.md, gate de cobertura ≥ 90% ativo (com suite de testes do kernel `shared/`), tree.txt gerado e docs corrigidos. Sem regra de negócio. Ver `docs/stages/1.1-bootstrap/`.

```yaml
stage_id: 1.1-bootstrap
bounded_context: shared
camada_alvo: bootstrap
arquivos_a_criar:
  - uv.lock (gerado por make setup; versionado)
  - tree.txt (gerado por scripts/regen_tree.py; gitignorado)
  - .importlinter (contratos espelhando LAYOUT §3)
  - .claude/settings.json (env compartilhado; settings.local.json sai do git)
  - scripts/clean.py (lógica do make clean, shell-agnostic)
  - tests/unit/shared/ + tests/unit/test_bootstrap.py + tests/e2e/test_app_smoke.py
  - docs/adr/1_1_0001 (ambiente Windows-nativo) e 1_1_0002 (gates de PR observacionais)
arquivos_a_modificar:
  - Makefile (receitas shell-agnostic; uv sync; test-gate com cobertura; import/lock-check)
  - pyproject.toml (dep import-linter)
  - .pre-commit-config.yaml (hook lint-imports)
  - .gitignore (settings.local.json)
  - README.md, docs/runbooks/validate-ci-gate.md, docs/LAYOUT.md (ambiente real)
  - docs/roadmap.md (este bloco) + docs/stages/1.1-bootstrap/ (artefatos do próprio ciclo)
contratos_introduzidos: []
contratos_consumidos: []
definition_of_done:
  - "`make setup && make check && make test` verdes na máquina local (Windows nativo)"
non_goals:
  - features de negócio
  - CI no GitHub (Stage 1.2)
complexidade_estimada: M
gate_mode: strict
skills_hint: [hex-arch-python, import-linter-rules]
```

> Nota (2026-07-14): bloco corrigido durante a execução da Stage (issue #1) —
> a feature-exemplo de pedidos do boilerplate, citada originalmente em
> `arquivos_a_modificar`, não existia no bootstrap (letra morta) e o escopo
> real reavaliou a complexidade de S para M.

#### Stage 1.2 — `1.2-ci`

**Descrição humana:** ativar e validar o pipeline de CI vindo do boilerplate no GitHub Actions (lint + types + testes em PR e push para main/develop), corrigindo o que quebrar; validação ponta-a-ponta com PR de teste.

```yaml
stage_id: 1.2-ci
bounded_context: shared
camada_alvo: bootstrap
arquivos_a_criar:
  - docs/adr/1_2_0001-deterministic-pr-path-gates.md
  - docs/stages/1.2-ci/ (artefatos do próprio ciclo)
arquivos_a_modificar:
  - .github/workflows/ci.yml (ajustes para o repo real)
  - docs/runbooks/validate-ci-gate.md (dever da §Maintenance do próprio runbook)
  - docs/roadmap.md (este bloco)
definition_of_done:
  - "PR de teste com erro intencional falha no CI; revertido, CI verde em <5min"
contratos_introduzidos: []
contratos_consumidos: []
non_goals:
  - deploy/CD (Step 6)
  - cache de dependências (otimização posterior)
complexidade_estimada: S
gate_mode: strict
skills_hint: [git-versioning-pointer]
```

> Nota (2026-07-16): bloco corrigido durante a execução da Stage (issue #9) —
> `arquivos_a_criar`/`arquivos_a_modificar` citavam só o `ci.yml` e omitiam os
> caminhos que a própria Stage necessariamente toca: a §Maintenance do
> `docs/runbooks/validate-ci-gate.md` obriga toda Stage que endurece o gate de CI
> a estender o runbook na mesma Stage, a Fase 3A produziu um ADR, e os artefatos
> da Stage + este bloco também são tocados (mesmo padrão declarado no bloco da
> 1.1). `contratos_introduzidos: []` e `complexidade_estimada: S` seguem válidos:
> 5 Tasks, nenhuma mudança de código-fonte (`src/`/`scripts/`). As fronteiras que
> a Fase 3A avaliou e recusou (higiene de runner-minutes; levar o gate
> issue-first ao caminho de PR) ficam registradas no `concept.md` §1 "Fora do
> escopo" e no ADR 1.2.0001 — **não** foram acrescentadas aos `non_goals` daqui,
> para não fazer o Roadmap citar como norma uma decisão do Concept que ele
> governa.

---

### Step 2 — Restaurante e acesso (BC `identity`)

- **Resultado de negócio:** o restaurante piloto e sua unidade existem no sistema; dono, gerente, RH e funcionários entram com login e enxergam apenas o que o papel permite; admin de plataforma (Marcelo) cria/gerencia tenants.
- **Depende de:** Step 1.
- **Tamanho estimado:** M

#### Stage 2.1 — `2.1-identity-domain`

**Descrição humana:** modelar tenancy e acesso — Restaurante (tenant), Unidade, Usuário, papéis fixos de acesso (platform_admin, owner, manager, hr, employee) e permissões; invariantes de isolamento entre tenants e de vínculo usuário↔unidades.

```yaml
stage_id: 2.1-identity-domain
bounded_context: identity
camada_alvo: domain
arquivos_a_criar:
  - features/identity/domain/entities/{restaurant,unit,user}.py
  - features/identity/domain/value_objects/{email,role,permission}.py
  - features/identity/domain/exceptions/
  - tests/unit/features/identity/domain/
arquivos_a_modificar: []
contratos_introduzidos:
  - Restaurant, Unit, User (entities)
  - Email, Role, Permission (value-objects)
definition_of_done:
  - "invariantes de tenancy e RBAC cobertas por testes unitários verdes (sem I/O)"
contratos_consumidos: []
non_goals:
  - persistência, HTTP, hash de senha (camadas seguintes)
  - funções de trabalho customizáveis (BC staff — Step 3)
complexidade_estimada: M
gate_mode: strict
skills_hint: [ddd-tactical-patterns, hex-arch-python]
```

> Nota (2026-07-18): bloco corrigido durante a execução da Stage (issue #17) —
> o recorte real tocou mais do que o bloco previa, em dois eixos. **File-scope:**
> por ser a 1ª feature-slice do repo, `scripts/check_layout.py`
> (`REQUIRED_FEATURE_DIRS`) exige os três diretórios da feature, então entraram
> `features/identity/{application,adapters}/__init__.py` como pacotes-placeholder
> vazios; e o `.importlinter` foi **modificado** (contrato aditivo
> `identity-domain-purity`, espelhando LAYOUT §3 como o `domain-purity` já fazia
> para `shared.domain`) — logo `arquivos_a_modificar: []` não se sustentou.
> **Contratos:** além de `Restaurant/Unit/User` e `Email/Role/Permission`, a Stage
> introduziu os identificadores tipados (`RestaurantId/UnitId/UserId`), o VO
> `UnitMembership` (esqueleto do vínculo user↔unit — kickoff #1, já citado na
> descrição humana) e a hierarquia de exceções do BC (`IdentityError` + 7
> subclasses); e **consome** `DomainError` de `shared/domain` (1.1), contra
> `contratos_consumidos: []`. `complexidade_estimada: M` e `gate_mode: strict`
> seguem válidos (7 Tasks + 4 commits de correção de revisão). As decisões de
> modelagem estão nos ADRs 2.1.0001 (agregados e membership) e 2.1.0002
> (`platform_admin` sem tenant); os desvios de execução, na §7 do `technical.md`.

#### Stage 2.2 — `2.2-identity-application`

**Descrição humana:** use cases de criação de tenant/unidade/usuário, autenticação (login) e autorização (checagem de permissão por papel), com ports de repositório, hasher de senha e emissor de token; testes com fakes.

```yaml
stage_id: 2.2-identity-application
bounded_context: identity
camada_alvo: application
arquivos_a_criar:
  - features/identity/application/use_cases/{create_restaurant,create_unit,create_user,authenticate_user,authorize_action}.py
  - features/identity/application/ports/out/{restaurant_repository,unit_repository,user_repository,password_hasher,token_issuer}.py
  - features/identity/application/dtos/
  - tests/unit/features/identity/application/ + tests/fakes/features/identity/
arquivos_a_modificar: []
contratos_introduzidos:
  - RestaurantRepository, UnitRepository, UserRepository, PasswordHasher, TokenIssuer (ports-out)
  - commands/results DTOs de identity
contratos_consumidos:
  - entities/VOs de 2.1
definition_of_done:
  - "use cases de tenancy/auth passam com fakes; nenhuma import de adapters"
non_goals:
  - convite por e-mail (2.5)
  - adapters reais (2.3/2.4)
complexidade_estimada: M
gate_mode: strict
skills_hint: [pytest-with-fakes, task-ordering-hex, hex-arch-python]
```

> Nota (2026-07-19): bloco corrigido durante a execução da Stage (issue #20) —
> o recorte real extrapolou o bloco em três eixos, todos **aditivos**.
> **Contratos:** entrou um sexto port-out, `SessionRepository`, exigido pela
> decisão de kickoff #1 (refresh persistido e rotacionado, para que logout e
> demissão cortem acesso de verdade); a issue #20 autoriza explicitamente
> modelá-lo e registrá-lo em ADR (2.2.0001). Junto dele vieram os DTOs
> `Session`/`IssuedRefreshToken`/`AccessTokenClaims`/`UserCredentials`, e
> `PasswordHasher` ganhou `dummy_hash()` (defesa contra enumeração de contas por
> tempo de resposta — ADR 2.2.0003 e concept §5.14). **File-scope:**
> `arquivos_a_modificar: []` não se sustentou — o `.importlinter` recebeu o
> contrato aditivo `identity-application-purity` (espelhando LAYOUT §3 como a 2.1
> fez para o domínio), o `Makefile` passou a rodar `mypy` também sobre
> `tests/fakes/` (sem isso a conformidade fake↔`Protocol` não tinha gate algum),
> `docs/LAYOUT.md` §2 passou a prever `tests/fakes/shared/`, e `pyproject.toml`
> ativou `branch = true` na cobertura. **Consequências para as Stages seguintes,
> ainda não refletidas nos blocos 2.3 e 2.4:** a 2.3 precisa implementar
> `session_repository.py` + a tabela de sessões (e uma política de expurgo das
> expiradas); a 2.4 precisa de `application/use_cases/refresh_session.py` — o
> endpoint de refresh já está alocado lá, mas o arquivo do use case não. Ambos
> registrados como `[finding]` na §7 do `technical.md` da 2.2.

#### Stage 2.3 — `2.3-identity-persistence`

**Descrição humana:** repositórios PostgreSQL de identity (com `tenant_id` nas tabelas em que ele é dado — ROADMAP-3; `sessions` é a exceção deliberada e alcança o tenant por `user_id`, ADR 2.3.0002), mappers, migrations iniciais e testes de integração + contrato (fake ≡ real).

```yaml
stage_id: 2.3-identity-persistence
bounded_context: identity
camada_alvo: adapters/out/postgres
arquivos_a_criar:
  - features/identity/adapters/out/postgres/{restaurant_repository,unit_repository,user_repository,mappers,tables}.py
  - migrations/versions/0001_identity_initial.py
  - tests/integration/features/identity/ + tests/contract/features/identity/
arquivos_a_modificar:
  - composition_root.py (wiring dos repositórios)
contratos_introduzidos: []
contratos_consumidos:
  - ports-out de 2.2
definition_of_done:
  - "testes de integração e de contrato verdes contra Postgres real (docker)"
non_goals:
  - row-level security nativa do Postgres (avaliar em ADR futuro se necessário)
complexidade_estimada: M
gate_mode: strict
skills_hint: [repository-pattern, composition-root, pytest-with-fakes]
```

> **Nota (2026-07-19): bloco corrigido durante a execução da Stage (issue #22)** —
> file-scope e contratos reais.
>
> - **`tenant_id` NÃO fica em todas as tabelas — a descrição humana acima foi corrigida.**
>   `sessions` não recebe a coluna: o DTO `Session` não carrega tenant, então ela seria
>   inatingível pelo port e impossível para o fake; e, como o tenant de um `platform_admin`
>   é nulo, a FK composta sobre ela seria MATCH SIMPLE — desligada justamente no caso que
>   deveria proteger. O isolamento de sessão chega por `user_id`. Decisão validada
>   empiricamente contra Postgres 16 (com controle negativo) — ADR 2.3.0002.
> - **Sessão persistida (reconciliação pendente do ADR 2.2.0001).** O bloco não citava
>   `session_repository.py` nem a tabela `sessions`; ambos existem, como consequência
>   direta do 6º port introduzido na 2.2. O ADR 2.2.0001 §Consequences já previa esta
>   reconciliação.
> - **Arquivos não previstos:** `integrity_errors.py` (tradução de violação de constraint
>   por `diag.constraint_name`, sem parsing de mensagem), a infra do Alembic
>   (`migrations/env.py`, `alembic.ini`, `script.py.mako`), e ajustes em
>   `shared/infrastructure/{config/settings,database/connection}.py` + `pyproject.toml`
>   (driver `psycopg`).
> - **`contratos_introduzidos: []` ficou desatualizado:** a Stage estendeu os ports-out de
>   2.2 com os erros de chave duplicada (`restaurant/unit/user/session_repository`,
>   `errors.py`, `credentials.py`) — extensão aditiva, não contraditória.
> - **`.github/workflows/ci.yml` alterado:** o job de gate passou a exigir Postgres real
>   (ADR 2.3.0001) — sem isso os testes de integração passariam por ausência.
> - **5 ADRs novos:** 2.3.0001 (integração exige Postgres real), 2.3.0002 (schema, tenant e
>   constraints), 2.3.0003 (`add` é inserção, não upsert), 2.3.0004 (retenção e purge de
>   sessão), 2.3.0005 (nomes persistidos verbatim).
> - `complexidade_estimada: M` e `gate_mode: strict` seguem válidos (12 Tasks + commits de
>   correção de revisão e de auditoria). Os desvios de execução estão na §7 do
>   `technical.md`.

#### Stage 2.4 — `2.4-identity-http`

**Descrição humana:** endpoints FastAPI de auth (login/refresh) e CRUD de tenants/unidades/usuários com enforcement de RBAC via dependência (`Depends`, não middleware — ver nota); adapters de PasswordHasher (**argon2**, ADR 2.4.0004) e TokenIssuer (JWT); e2e feliz + acesso negado.

```yaml
stage_id: 2.4-identity-http
bounded_context: identity
camada_alvo: adapters/in/http
arquivos_a_criar:
  - features/identity/adapters/in/http/{router,schemas,dependencies}.py
  - features/identity/adapters/out/security/{argon2_hasher,jwt_issuer}.py
  - tests/e2e/features/identity/
arquivos_a_modificar:
  - composition_root.py, shared/infrastructure/http/app.py (registrar router e middleware de auth)
contratos_introduzidos: []
contratos_consumidos:
  - use cases/ports de 2.2
definition_of_done:
  - "e2e: admin cria tenant→unidade→usuário; login emite JWT; ação sem permissão retorna 403"
non_goals:
  - convite por e-mail (2.5), reset de senha (entra com 2.5)
complexidade_estimada: M
gate_mode: strict
skills_hint: [fastapi-thin-adapter, composition-root]
```

> **Nota (2026-07-20): bloco corrigido durante a execução da Stage (issue #24)** —
> file-scope e contratos reais.
>
> - **`contratos_introduzidos: []` ficou desatualizado:** a Stage **estendeu** o port
>   `TokenIssuer` com `decode_access_token` (ADR 2.4.0002) — extensão aditiva, decidida
>   aqui porque decodificar é a operação inversa de emitir e pertence ao mesmo port.
> - **Dois use cases novos na camada application, não previstos no bloco:**
>   `refresh_session.py` (rotação) e `revoke_session.py` (logout). O ADR 2.2.0001 já
>   alocava a rotação a esta Stage; o bloco não refletia.
> - **Arquivos não previstos:** `adapters/in/http/error_handlers.py` (mapa exceção →
>   status, ADR 2.4.0001), campos de token em `shared/infrastructure/config/settings.py`,
>   `.importlinter` (contrato da nova camada), `.env.example` e `pyproject.toml`
>   (`argon2-cffi`, `pyjwt`).
> - **Testes além do previsto:** o bloco citava só `tests/e2e/features/identity/`; a Stage
>   entregou também `tests/contract/features/identity/test_security_contract.py`, provando
>   fake ≡ real para `PasswordHasher` e `TokenIssuer` — o mesmo padrão que a 2.3 usou para
>   os repositórios.
> - **`bcrypt` não entrou — a descrição humana acima foi corrigida.** O bloco dizia
>   "argon2/bcrypt"; a escolha foi **argon2** (ADR 2.4.0004), sem alternativa
>   implementada — trocar é um adapter.
> - **Não há middleware de auth — a descrição humana acima foi corrigida.** O bloco previa
>   "registrar router e middleware de auth"; o enforcement é uma **dependência**
>   (`Depends`), não middleware. `Depends` roda por rota com o contrato explícito na
>   assinatura, enquanto middleware roda para tudo e precisaria de lista de exceções para
>   as rotas públicas de auth — lista que silenciosamente deixa rota nova desprotegida.
>   ADR 2.4.0003.
> - **4 ADRs novos:** 2.4.0001 (mapa de status HTTP), 2.4.0002 (`decode` estende
>   `TokenIssuer`), 2.4.0003 (composição de autorização no boundary), 2.4.0004 (parâmetros
>   do adapter de segurança).
> - **Decisões do sponsor de 2026-07-19 aplicadas aqui:** só `platform_admin` cria
>   restaurante (o `owner` cria unidades; auto-cadastro segue no Step 13) e a janela de
>   revogação fecha por **TTL curto de access token, configurável** — sem introspecção por
>   request, com `session_id` já nos claims para permiti-la depois.
> - `complexidade_estimada: M` e `gate_mode: strict` seguem válidos (12 Tasks + commits de
>   correção de revisão e de auditoria). Os desvios de execução estão na §7 do
>   `technical.md`.

#### Stage 2.5 — `2.5-email-invite`

**Descrição humana:** fatia vertical do convite: port compartilhado `EmailSender` + `ConsoleSender` (o adapter free-tier da ROADMAP-5 **não** entrou — ver nota) + use cases de convite, definição de senha por token e pedido de reset + endpoints; cobre também reset de senha (mesmo mecanismo de token). Inclui persistência do token (uso único).

```yaml
stage_id: 2.5-email-invite
bounded_context: identity
camada_alvo: vertical (application + adapters, BC identity)
arquivos_a_criar:
  - shared/application/ports/email_sender.py
  - shared/infrastructure/email/{smtp_or_api_sender,console_sender}.py
  - features/identity/application/use_cases/{invite_user,set_password_with_token}.py
  - features/identity/adapters/in/http/ (rotas de convite/definir senha)
  - tests (unit com fake, e2e do fluxo de convite)
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos:
  - EmailSender (port-out compartilhado)
contratos_consumidos:
  - UserRepository/TokenIssuer de 2.2
definition_of_done:
  - "fluxo: convite gera e-mail (ConsoleSender em dev) com link; token define senha; login funciona"
non_goals:
  - templates de e-mail elaborados; provedor definitivo (troca é 1 adapter)
complexidade_estimada: M
gate_mode: strict
skills_hint: [task-ordering-hex, fastapi-thin-adapter, composition-root]
```

> **Nota (2026-07-20): bloco corrigido durante a execução da Stage (issue #27)** —
> as cinco divergências abaixo estão declaradas no concept §1 e reconciliadas aqui.
>
> - **Persistência entrou no escopo.** O bloco não lista tabela, migration nem
>   `adapters/out`. O DoD ("token define a senha") somado à exigência de **uso único**
>   é inalcançável sem estado no servidor — a alternativa stateless foi examinada e
>   rejeitada no ADR 2.5.0002. Entraram `password_setup_tokens`, a migration `0002` e
>   o adapter Postgres.
> - **Três use cases, não dois.** Além de `invite_user` e `set_password_with_token`,
>   entrou `request_password_reset`: o pedido de reset é **público** e o convite é
>   autenticado, então precisam de caminhos de entrada distintos.
> - **`smtp_or_api_sender` não foi entregue — a descrição humana acima foi corrigida.**
>   A issue #27 autorizou explicitamente fechar o DoD com `ConsoleSender`. O adapter
>   real (Resend, kickoff #7 / ASSUM-3) é `[finding]` para a **6.2**.
> - **`TokenIssuer` não é consumido**, contra o que `contratos_consumidos` diz. O token
>   de convite/reset tem ciclo de vida próprio (uso único, prazo curto, canal fora de
>   banda) e ganhou mecanismo separado — ADR 2.5.0002. Reusar token de sessão como
>   token de convite seria vulnerabilidade, não economia.
> - **O port ficou em `shared/application/ports/out/`**, não em
>   `shared/application/ports/`: `out/` é a convenção vigente (`clock.py`,
>   `id_generator.py`) e LAYOUT §5 separa ports primários de secundários.
> - **`EmailSender` nasceu em `shared/`** (ADR 2.5.0001), decidindo a tensão que a issue
>   #27 levantou entre o roadmap e o LAYOUT §4: a regra do LAYOUT existe contra
>   abstração **prematura**, e prematuro é o que não tem segundo consumidor
>   identificado — a 4.6 já o nomeia em `contratos_consumidos`.
> - **4 ADRs novos:** 2.5.0001 (`EmailSender` em shared), 2.5.0002 (token de setup
>   dedicado e de uso único), 2.5.0003 (definir senha revoga todas as sessões),
>   2.5.0004 (`unusable_hash` para conta pendente).
> - **Achado de segurança fechado antes de virar código:** o plano original gravava
>   `dummy_hash()` na conta convidada — que é o hash de um literal do repositório, ou
>   seja, **bypass de autenticação** para qualquer convidado não ativado. Pego por dois
>   revisores no Checkpoint A; corrigido com `unusable_hash()` (ADR 2.5.0004).
> - `complexidade_estimada: M` e `gate_mode: strict` seguem válidos (13 Tasks + commits
>   de correção de revisão e de auditoria).

#### Stage 2.6 — `2.6-identity-unit-of-work`

**Descrição humana:** promovida da issue #46 em 2026-10-19 (o corpo da issue virou mini-concept:
port novo e trade-off com ADR — PIPELINE §4.5). Os use cases **de identity** que escrevem mais de
uma vez numa requisição passam a fazê-lo numa unidade atômica: falha na N-ésima escrita deixa o
banco como estava. Fecha os `[finding]` de atomicidade da rotação de sessão (2.4) e do órfão
dentro de identity (3.5), corrige o ponteiro órfão para a 4.4 e acrescenta o gate que impede a
regressão. Travessias entre BCs (staff ↔ identity) ficam ordenadas, como na 3.5. Depende da 3.5
(`provision_account` e a fachada vêm dela). Ver `docs/stages/2.6-identity-unit-of-work/`.

```yaml
stage_id: 2.6-identity-unit-of-work
bounded_context: identity
camada_alvo: application + adapters/out/postgres + tooling (divergência declarada no concept §1)
arquivos_a_criar:
  - features/identity/application/ports/out/unit_of_work.py
  - features/identity/adapters/out/postgres/unit_of_work.py (+ helper de conexão da unidade)
  - tests/fakes/features/identity/in_memory_unit_of_work.py
  - contrato fake × Postgres do UoW + integração por use case
arquivos_a_modificar:
  - repositórios Postgres de identity (conexão da unidade ativa) + SessionRepository.revoke -> bool
  - os cinco use cases de identity com 2+ escritas + composition_root.py
  - tests/contract/features/staff/conftest.py (fixture do gateway real)
  - scripts/check_layout.py (regra 10)
  - docs/LAYOUT.md (fronteira transacional)
contratos_introduzidos:
  - UnitOfWork (port-out de identity)
  - regra 10 do check_layout (escrita múltipla só dentro de uma unidade)
contratos_modificados:
  - SessionRepository.revoke devolve bool (aditivo)
contratos_consumidos:
  - ports de repositório de identity (2.2/2.5); IdentityFacade (3.5)
definition_of_done:
  - "integração: falha na N-ésima escrita de cada um dos cinco use cases deixa o banco inalterado"
  - "fake e Postgres do UoW passam na mesma suíte de contrato"
non_goals:
  - locking otimista (ADR 3.3.0006)
  - mudar a ordem fail-closed de set_password_with_token
  - ports assíncronos (ADR 2.2.0004)
  - transação atravessando bounded contexts
  - provisionamento composto restaurante + dono (ADR 2.4.0003 Alt. B)
complexidade_estimada: M
gate_mode: strict
skills_hint: [hex-arch-python, repository-pattern, pytest-with-fakes, composition-root, task-ordering-hex]
```

> **Nota (2026-10-19): reconciliação pós-execução da Stage 2.6** (issue #46; concept, technical e
> §7 em `docs/stages/2.6-identity-unit-of-work/`; ADRs 2.6.0001 e 2.6.0002). O bloco acima foi
> escrito na promoção e se sustentou; o que a execução acrescentou:
>
> - **`SessionRepository.revoke` passou a devolver `bool`** (contratos_modificados, já no bloco): a
>   rotação concorrente perdida vira reuso. Realiza o desfecho que o concept 2.4 §6 descrevia e
>   que a auditoria de 2026-09-28 mediu como quebrado (dois refresh vivos em 11 de 12 corridas).
> - **13 Tasks** e não 12: os docstrings de staff numa Task própria. Mais 7 commits de correção ou
>   cobertura vindos de quatro Checkpoints C e de duas rodadas de auditoria de testes com mutação
>   real.
> - **Findings com pouso:** #67 (provisionamento composto restaurante + dono), #68 (`user_id`
>   condicional em staff) e a regra 10 encontrando a dupla escrita da 4.4 (§7 do technical).
> - **Renumeração:** promovida como 3.7, renumerada para 2.6 antes do primeiro gate — o número
>   colidia com as Stages paralelas das #49 e #60.

---

### Step 3 — Equipe da unidade (BC `staff`)

- **Resultado de negócio:** gerente cadastra funções 100% customizadas (ex.: cozinheiro, atendente, faxineiro), funcionários com jornada fixa ou sob demanda, preferência de turno e períodos de indisponibilidade; pode copiar funcionário para outra unidade e criar login para ele.
- **Depende de:** Step 2.
- **Tamanho estimado:** M

#### Stage 3.1 — `3.1-staff-domain`

**Descrição humana:** modelar Funcionário, Função (customizável por restaurante), perfil de jornada (fixa com carga; sob demanda tipo extra/gerente/dono), preferência de turno e Indisponibilidade (períodos); invariantes (ex.: indisponibilidades não sobrepostas).

```yaml
stage_id: 3.1-staff-domain
bounded_context: staff
camada_alvo: domain
arquivos_a_criar:
  - features/staff/domain/entities/{employee,job_function}.py
  - features/staff/domain/value_objects/{workload_profile,shift_preference,unavailability_period}.py
  - features/staff/domain/exceptions/
  - tests/unit/features/staff/domain/
arquivos_a_modificar: []
contratos_introduzidos:
  - Employee, JobFunction (entities); WorkloadProfile, ShiftPreference, UnavailabilityPeriod (value-objects)
contratos_consumidos: []
definition_of_done:
  - "invariantes de jornada e indisponibilidade cobertas por testes unitários verdes"
non_goals:
  - vínculo com login/usuário (3.5); persistência/HTTP
complexidade_estimada: M
gate_mode: strict
skills_hint: [ddd-tactical-patterns, hex-arch-python]
```

> **Nota (2026-07-29): bloco corrigido durante a execução da Stage (issue #32)** —
> o recorte real expandiu o bloco em dois eixos, ambos declarados no concept §7
> (mesmo padrão da 2.1). **File-scope:** `arquivos_a_modificar: []` não se
> sustentou — o `.importlinter` foi **modificado** (contratos aditivos
> `staff-domain-purity` e `bc-independence` identity × staff, este último
> planejado no cabeçalho do arquivo desde a 1.1); e entraram
> `features/staff/domain/value_objects/identifiers.py` (identificadores tipados
> próprios do BC) e os placeholders `features/staff/{application,adapters}/__init__.py`
> vazios (exigidos por `scripts/check_layout.py` — `REQUIRED_FEATURE_DIRS`).
> **Contratos:** além de `Employee`/`JobFunction` e
> `WorkloadProfile`/`ShiftPreference`/`UnavailabilityPeriod`, a Stage introduziu
> `DayPeriod` (StrEnum fechado, co-locado em `shift_preference.py` — decisão na
> §7 do technical), os identificadores `EmployeeId`/`JobFunctionId`/`TenantId`/`UnitId`
> e a hierarquia de exceções do BC (`StaffError` + 8 subclasses, incl.
> `UnavailabilityNotFoundError`); e **consome** `DomainError` de `shared/domain`,
> contra `contratos_consumidos: []`. `complexidade_estimada: M` e
> `gate_mode: strict` seguem válidos (7 Tasks + 3 commits de correção de
> checkpoint). As decisões de modelagem estão nos ADRs 3.1.0001–3.1.0006; os
> desvios de execução, na §7 do `technical.md`.

#### Stage 3.2 — `3.2-staff-application`

**Descrição humana:** use cases CRUD de função e funcionário, definição de jornada/preferência, registro de indisponibilidade e cópia de funcionário para outra unidade (sem compartilhamento); ports e testes com fakes.

```yaml
stage_id: 3.2-staff-application
bounded_context: staff
camada_alvo: application
arquivos_a_criar:
  - features/staff/application/use_cases/{create_job_function,create_employee,update_workload,register_unavailability,copy_employee_to_unit,...}.py
  - features/staff/application/ports/out/{employee_repository,job_function_repository}.py
  - features/staff/application/dtos/ + tests com fakes
arquivos_a_modificar: []
contratos_introduzidos:
  - EmployeeRepository, JobFunctionRepository (ports-out)
contratos_consumidos:
  - entities/VOs de 3.1
definition_of_done:
  - "use cases verdes com fakes; cópia entre unidades duplica cadastro sem vazar dados entre unidades"
non_goals:
  - noção de escala/demanda (Step 4)
complexidade_estimada: M
gate_mode: strict
skills_hint: [pytest-with-fakes, task-ordering-hex]
```

> **Nota (2026-08-09): bloco corrigido durante a execução da Stage (issue #35)** —
> o recorte real expandiu o bloco em **quatro** eixos, todos declarados no
> concept §7 (mesmo padrão datado da 2.1 e da 3.1).
> **Camada-alvo:** `camada_alvo: application` não se sustentou sozinho — a Stage
> também **modificou o domínio já mergeado da 3.1**, por decisão do sponsor de
> 2026-08-08: `JobFunction` **perdeu** `active`/`deactivate()`/`reactivate()`
> (ADR 3.2.0005, que supersede o 3.1.0003) e `Employee` **ganhou**
> `active: bool = True` com as duas transições (ADR 3.2.0006). É expansão de
> camada-alvo, feita aqui de propósito para a 3.3 nascer com a coluna e sem
> migration.
> **File-scope:** `arquivos_a_modificar: []` não se sustentou — entraram o
> `.importlinter` (contrato aditivo `staff-application-purity`), as duas
> entidades da 3.1 e os seus dois arquivos de teste.
> **Contratos introduzidos:** além dos dois ports-out, a Stage introduziu os
> **DTOs** (14 commands, 2 queries, 2 results), os **nove erros de aplicação**
> do BC (`application/errors.py`), os **16 use cases**, o campo `Employee.active`
> com as suas transições e — como entregável de primeira classe, não andaime —
> o **par acoplado de fakes** sobre `InMemoryStaffStore` com o holder
> `StaffFakes`, que é a fixture que a 3.3 parametriza no teste de contrato.
> **Contratos consumidos:** além de entities/VOs da 3.1, a Stage consome
> `IdGenerator` (`shared/application`) e `DomainError`/`NotFoundError`
> (`shared/domain`).
> `complexidade_estimada: M` e `gate_mode: strict` seguem válidos (13 Tasks
> planejadas + 2 Tasks extras de teste vindas da auditoria + 7 commits de
> correção de checkpoint). As decisões estão nos ADRs 3.2.0001–3.2.0007 — o
> **3.2.0007** foi acrescentado durante a execução, quando a auditoria de testes
> independente revelou que a interação entre editar e desligar nunca fora
> especificada; os desvios de execução, na §7 do `technical.md`.

#### Stage 3.3 — `3.3-staff-persistence`

**Descrição humana:** repositórios PostgreSQL de staff, mappers, migration e testes de integração + contrato.

```yaml
stage_id: 3.3-staff-persistence
bounded_context: staff
camada_alvo: adapters/out/postgres
arquivos_a_criar:
  - features/staff/adapters/out/postgres/
  - migrations/versions/0002_staff.py
  - tests/integration + tests/contract de staff
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos: []
contratos_consumidos:
  - ports-out de 3.2
definition_of_done:
  - "integração + contrato verdes contra Postgres"
non_goals: []
complexidade_estimada: S
gate_mode: strict
skills_hint: [repository-pattern]
```

> **Nota (2026-08-11): bloco corrigido durante a execução da Stage (issue #38)** —
> o recorte real expandiu o bloco em **cinco** eixos, todos declarados no
> concept §7 D10 (mesmo padrão datado da 2.1, 3.1 e 3.2).
> **Migration:** `migrations/versions/0002_staff.py` → **`0003_staff.py`**. O
> número `0002` foi consumido por `password_setup_tokens` na Stage 2.5, e manter
> o bloco como estava faria o roadmap afirmar um número que colidiria com a
> migration existente.
> **File-scope:** `arquivos_a_criar` era genérico demais e `arquivos_a_modificar`
> listava só `composition_root.py`. O real: criou `features/staff/adapters/out/postgres/`
> (`tables.py`, `mappers.py`, `integrity_errors.py` e os dois repositórios),
> `migrations/versions/0003_staff.py`, `tests/integration/features/staff/`,
> `tests/contract/features/staff/` e `tests/unit/features/staff/adapters/`, mais
> os **sete ADRs**; modificou `composition_root.py`, `migrations/env.py`
> (combinação dos dois `MetaData`), `tests/conftest.py` (ordem de limpeza
> compartilhada), `tests/integration/test_migration.py`, as **duas docstrings de
> port** de `features/staff/application/ports/out/` (`L-ORD`), os **dois fakes**
> de `tests/fakes/features/staff/` (que passaram a ordenar) e o
> `concept.md` da **3.2** (nota datada de acréscimo da âncora — D11). E
> **moveu** as duas suítes de lei de `tests/unit/features/staff/application/`
> para `tests/contract/features/staff/` (`git mv`, ADR 3.3.0007) — o roadmap não
> previa remoção de arquivo.
> **Contratos introduzidos:** `[]` não se sustentou. A Stage introduz a lei
> **`L-ORD`** (ADR 3.3.0003), que **estende os dois ports da 3.2** com ordem
> total determinística e independente de ambiente, valendo para as duas
> implementações; mais o holder `RepositoriosDeStaff` da suíte de contrato. É
> contrato consumido pela 3.4, cuja paginação usa `(name, id)` como cursor.
> **`complexidade_estimada: S` → `M`.** Não se sustentou, e por margem larga:
> **10 Tasks** planejadas e executadas, mais **8 commits de correção** vindos dos
> Checkpoints C e da auditoria de testes independente. Cinco tabelas, migration à
> mão, dois adapters, mappers, tradutor de integridade por operação, lei nova de
> port, promoção de 46 testes de lei e wiring de 16 use cases não é `S` — a 3.2,
> com 16 use cases, é `M`. Deixar `S` faria o gate de tamanho de PIPELINE §4.2
> avaliar outra Stage.
> **`non_goals: []` → oito** (concept §1), dois deles substantivos: **RLS
> avaliada e rejeitada** (ADR 3.3.0005) e **controle otimista de concorrência
> escalado** (ADR 3.3.0006, que fecha atomicidade das duas pontas mas deixa
> *lost update* declarado como limite).
> As decisões estão nos **ADRs 3.3.0001–3.3.0007**; os desvios de execução, na §7
> do `technical.md` — incluindo os quatro `[finding]` escalados e a correção de
> uma medição própria que a §7 afirmava e que não se sustentou na re-medição.

#### Stage 3.4 — `3.4-staff-access-scope`

**Descrição humana:** fundação de acesso e escopo do BC staff — duas permissões de equipe em identity (com dispensa de unidade para a de catálogo), a unidade entrando no endereço do funcionário até a assinatura do port, o port `AccessGuard` de staff, e duas correções de domínio que a borda não faz sozinha. **Não expõe nenhuma rota**; a API de equipe é a Stage 3.6.

```yaml
stage_id: 3.4-staff-access-scope
bounded_context: staff
camada_alvo: identity (domain + application) + staff (domain, application, adapters/out)
arquivos_a_criar:
  - features/staff/application/ports/out/access_guard.py (port + AuthorizedScope + leis L-AG1..L-AG4)
  - tests de lei do port (fake) e testes das permissoes/dispensa em identity
arquivos_a_modificar:
  - features/identity/domain/value_objects/{permission,role}.py (2 permissoes + TENANT_WIDE_PERMISSIONS)
  - features/identity/application/use_cases/authorize_action.py (passo 4)
  - features/staff/application/ports/out/employee_repository.py (unidade na assinatura)
  - features/staff/application/dtos/commands.py (10 commands ganham unit_id)
  - features/staff/application/use_cases/*.py (12 use cases)
  - features/staff/adapters/out/postgres/employee_repository.py + fakes + tests/contract/features/staff/
  - features/staff/domain/entities/{employee,job_function}.py (byte NUL)
  - features/staff/domain/value_objects/shift_preference.py (DayPeriod.from_string)
  - features/staff/domain/exceptions/errors.py (InvalidDayPeriodError)
  - composition_root.py (tradutor do AccessGuard)
contratos_introduzidos:
  - AccessGuard (port-out de staff) + AuthorizedScope (dto) + leis L-AG1..L-AG4
  - Permission.MANAGE_STAFF, Permission.MANAGE_JOB_FUNCTIONS, TENANT_WIDE_PERMISSIONS (identity)
contratos_consumidos:
  - ports/use cases de 3.2; suites de contrato de 3.3; IdentityGuard de 2.4; AuthorizeActionUseCase de 2.2
definition_of_done:
  - "a suite de contrato prova a lei de unidade nos dois lados (fake e Postgres) com um corpo de teste so"
  - "gerente e RH detem MANAGE_STAFF e MANAGE_JOB_FUNCTIONS; employee e platform_admin nao detem nenhuma"
  - "ator unit-scoped exerce MANAGE_JOB_FUNCTIONS sem declarar unidade; com MANAGE_STAFF continua negado"
  - "as leis L-AG1..L-AG4 do AccessGuard sao testadas contra uma segunda implementacao (fake), e bc-independence segue sem nenhum ignore_imports"
  - "nome com byte NUL rejeitado no dominio, com fake e Postgres concordando; nenhuma assercao de DECISAO DE ACESSO de identity muda, e as fixtures de fechamento de vocabulario acompanham o conjunto que cresceu com aditividade provada (CA20 refinado em 2026-08-17)"
  - "make check verde; nenhuma rota HTTP nasce nesta Stage"
non_goals:
  - toda a superficie HTTP de equipe (router, schemas, handlers, e2e) — Stage 3.6
  - paginacao das listagens (ADR 3.4.0004, governa a 3.6)
  - busca ampla de funcionario no restaurante inteiro (operacao separada, permissao propria)
  - habilitacao de funcao de trabalho por unidade (issue #41)
  - permissao de hr sobre a escala (Step 4 — restricao para frente do ADR 3.4.0006)
  - vinculo de login do funcionario (3.5)
  - controle otimista de concorrencia (ADR 3.3.0006, segue aberto)
  - leitura de funcionario por id (finding para a 3.6)
complexidade_estimada: M
gate_mode: strict
skills_hint: [hex-arch-python, composition-root, repository-pattern, pytest-with-fakes, import-linter-rules]
```

> **Nota (2026-08-12): a Stage foi CORTADA em duas durante a Fase 3A (issue #40).**
> O bloco acima substitui integralmente o anterior, que descrevia a API de equipe.
>
> - **O corte e a razão.** A Stage era `3.4-staff-http` — "expor por HTTP os 16 use
>   cases de equipe", `complexidade_estimada: S`. Com as três decisões do sponsor de
>   2026-08-12 (forks F1/F2/F3) e os achados do Checkpoint A, o plano mediu **14
>   Tasks** — o limiar de "Stage grande demais" de [`CONVENTIONS.md`](./CONVENTIONS.md)
>   §6 ("≥ 14 = declare e PARE"). **7 das 14 Tasks não estavam no bloco original**:
>   nasceram das decisões e dos achados, não de inflação de plano.
> - **Onde a fronteira caiu, e por quê.** Entre **emendar Stage fechada** e
>   **escrever superfície nova**: tudo que toca 3.1, 3.2, 3.3 e identity ficou na 3.4
>   (6 Tasks); o adapter de entrada foi para a **3.6** (8 Tasks). O argumento decisivo
>   é de sequência — os **dois buracos de acesso** que o Checkpoint A encontrou
>   (exfiltração intra-tenant por cópia e sonda de leitura por rota de mutação; e o
>   DoD inalcançável porque `manager`/`hr` não passavam no eixo de unidade) fecham
>   **antes de existir qualquer rota que os exponha**. Não há Stage intermediária
>   publicando API furada.
> - **3.6 antes de 3.5 é legal e intencional.** CONVENTIONS §1 Numeração: Stage é
>   `N.M`, **numérico e sem letra** (por isso não `3.4a`/`3.4b`), e **não recicla** —
>   3.5 já existe, então o próximo livre do Step 3 é 3.6. A mesma seção resolve a
>   ordem: *"ordem de implementação = `depends_on`, não o número"*. A **3.5 passou a
>   depender da 3.6**, porque o vínculo de login acrescenta rota ao router de staff,
>   que só existe lá.
> - **As cinco desatualizações do bloco original**, todas corrigidas acima:
>   `contratos_introduzidos: []` (a Stage introduz port, DTO, duas permissões e o
>   conjunto tenant-wide), `non_goals: []` (são oito), `arquivos_a_criar`
>   (`{router,schemas}.py` e `tests/e2e/` são da 3.6), `camada_alvo`
>   (`adapters/in/http` era o alvo da Stage antiga; a nova toca quatro camadas em dois
>   BCs) e `complexidade_estimada` (`S` → `M`).
> - **Expansão de camada-alvo para `features/identity`, autorizada pelo sponsor**
>   (*"não há problema em tocar o módulo de acesso; isso irá acontecer ao longo do
>   desenvolvimento quando forem surgindo mais features"*): duas permissões, o
>   conjunto `TENANT_WIDE_PERMISSIONS`, o mapa de papéis e a condição do passo 4 de
>   `AuthorizeActionUseCase`.
> - **Três afirmações de outras fontes ficam falsas e são corrigidas aqui.** (a) A
>   nota da Stage 3.3 neste roadmap diz *"contrato consumido pela 3.4, cuja paginação
>   usa `(name, id)` como cursor"*; (b) a `[finding]` de 2026-08-12 na §7 do
>   `technical.md` da 3.3 diz *"a paginação da 3.4 acrescenta `LIMIT`/`OFFSET`"* —
>   **nem a 3.4 nem a 3.6 paginam** (ADR 3.4.0004), o cursor fica **preparado**, não
>   consumido, e o antídoto da regex `_ORDER_BY` segue escalado com a paginação; e
>   (c) o **ADR 3.3.0006** §Consequences diz que a coluna de versão do controle
>   otimista entra *"in Stage `3.4-staff-http`'s migration"* — **falso nas duas
>   metades**: a 3.4 não cria migration nenhuma (bloco acima) e o controle otimista
>   **segue aberto**, sem Stage candidata definida. O ADR não é reescrito (está
>   `accepted`); a correção vive aqui.
> - **Os findings escalados de outras Stages seguem dizendo "Stage candidata:
>   `3.4-staff-http`", e não foram reescritos** — estão na **§10 do `concept.md` da
>   3.2** e na **§7 do `technical.md` da 3.3**, seções seladas, verdadeiras quando
>   escritas. A tradução: o finding do **byte NUL** veio para a 3.4; os de
>   **`target_unit_id` da cópia**, **cópia repetida** e **regex `_ORDER_BY`** são da
>   **3.6**.
> - **8 ADRs, todos `accepted`, todos com `context_stage: 3.4-staff-access-scope`**
>   (o campo registra a Stage em que a decisão foi **tomada** — CONVENTIONS §2 — e ADR
>   `accepted` não migra). **Cinco governam a 3.4**: 3.4.0001 (port `AccessGuard` com
>   tradutor no composition root, mantendo `bc-independence` sem supressão), 3.4.0003
>   (byte NUL no domínio + `DayPeriod.from_string`), 3.4.0006 (duas permissões e
>   `hr` ≡ `manager` em staff, com restrição para frente sobre o Step 4), 3.4.0007 (a
>   unidade na assinatura do port) e 3.4.0008 (permissão tenant-wide). **Três governam
>   a 3.6** e trazem o aviso no corpo: 3.4.0002 (mapa de status), 3.4.0004 (sem
>   paginação), 3.4.0005 (cópia repetida como limite declarado).
> - **Nota (2026-08-17): o 5º bullet do `definition_of_done` acima foi reescrito
>   junto com o CA20 do concept.** A Fase 3B mediu que duas asserções de
>   `tests/unit/features/identity/domain/test_role_permission.py` mudam
>   necessariamente — a linha 27 assere o conjunto **exato** dos valores do enum
>   `Permission`, e as linhas 66–78 o conjunto **exato** de permissões por papel.
>   A redação anterior (*"suite de identity passa sem alteracao de assercao"*) tem
>   **falso positivo para teste de fechamento**, que existe justamente para exigir
>   atualização consciente quando o conjunto cresce legitimamente (o mecanismo que
>   o ADR 3.4.0008 §5 pede). O DoD passa a exigir o que sempre quis: nenhuma
>   asserção de **decisão de acesso** muda, e a aditividade das fixtures de
>   fechamento é **provada**, não afirmada. **O conjunto de comportamentos
>   protegidos é o mesmo** — mudou a formulação. Registro do achado: nota datada
>   sob o CA20 do [`concept.md`](./stages/3.4-staff-access-scope/concept.md) §11.
> - **O rascunho completo da borda** (inventário das 16 rotas, schemas de request e
>   response, mapa de status e critérios de aceite) está no commit **`d878060`**, em
>   `docs/stages/3.4-staff-http/concept.md` §4.1–4.3 — para que a Fase 3A da 3.6 não o
>   re-derive.

> **Nota (2026-08-18): reconciliação pós-execução da Stage 3.4.** A nota do corte
> acima é de 2026-08-12 e foi conferida linha a linha contra o executado —
> **continua fiel**, inclusive nas cinco desatualizações que ela mesma corrigiu.
> O que segue é o que **só a execução** podia dizer.
>
> - **O bloco se sustentou.** `arquivos_a_criar`, `arquivos_a_modificar`,
>   `contratos_introduzidos`, `contratos_consumidos`, `non_goals` e
>   `complexidade_estimada: M` foram medidos contra o diff e **valem como
>   escritos** — é a primeira Stage do Step 3 em que o bloco não precisou de
>   correção estrutural, e o motivo é que ele foi reescrito **depois** do
>   Checkpoint A, com os achados em mãos. **6 Tasks** planejadas e executadas,
>   mais **5 commits** de `fix`/`extra` vindos do Checkpoint C e da auditoria de
>   testes independente. File-scope real: **22 arquivos de `src/`** —
>   `composition_root.py`, três de `features/identity/` (as duas permissões, o
>   mapa de papéis e o passo 4) e dezoito de `features/staff/` (os dez commands,
>   os dez use cases, os dois ports, o adapter Postgres, as duas entidades,
>   `shift_preference.py` e `errors.py`).
> - **O valor da Stage, em uma frase:** um gerente da unidade A **deixou de
>   conseguir** ler, editar e clonar o funcionário da unidade B informando a
>   própria unidade. A unidade entrou no **endereço** do funcionário até a
>   assinatura do port (ADR 3.4.0007), então quem não sabe a unidade **não
>   consegue formar a chamada** — e o registro alheio responde
>   `EmployeeNotFoundError`, indistinguível de id inexistente. O revisor construiu
>   um cenário de ataque do zero e o provou nos **dois** parâmetros da suíte de
>   contrato (`[fake]` e `[postgres]`), com um corpo de teste só.
> - **`arquivos_a_criar` cresceu em testes, não em código.** Além do port e das
>   suítes previstas, nasceram `tests/unit/features/staff/test_bc_independence.py`
>   (varredura por AST do BC inteiro + leitura do `.importlinter`, que é o que
>   torna "zero `ignore_imports`" uma propriedade **medida** e não uma promessa) e
>   `tests/unit/features/identity/domain/test_rbac_additivity.py` (a prova
>   mecânica da metade "obrigatório" do CA20).
> - **CA20: as fixtures de fechamento de vocabulário são TRÊS, não duas.** A
>   terceira é
>   `test_http_dependencies.py::test_conjunto_de_permissoes_exigidas_por_papel_alvo`,
>   e ela é **derivada** do mapa de papéis (`dependencies.py:97`), logo cresce
>   sozinha quando o vocabulário cresce. **O 5º bullet do `definition_of_done`
>   acima continua verdadeiro** — ele fala da *categoria*, sem contagem, e foi por
>   isso que esta Stage **não** precisou de regressão do concept; a decisão e as
>   quatro medições que a sustentam estão na §7 do `technical.md`. A metade
>   **proibida** do critério (asserção de decisão de acesso) permanece intacta,
>   provada por igualdade em `test_matriz_de_quem_cria_quem_nao_regride`.
> - **A auditoria de testes independente encontrou 2 mutações sobreviventes** em
>   arquivos com 100% de cobertura de linha e branch, e as duas são da mesma
>   família — **lei universal travada num representante estreito**: (a) L-AG3
>   estava codificada sobre `manage_staff` nas duas implementações do port, então
>   condicionar a recusa à outra permissão deixava a suíte verde e um
>   `AuthorizedScope` de tenant vazio sair do guard; (b) a mesma estreiteza valia
>   para os ramos de **recusa** de L-AG2 e L-AG4, que nunca rodavam com a permissão
>   tenant-wide. Fechadas parametrizando as duas suítes sobre os **dois** alvos,
>   com prova de mutação antes e depois. Antes disso o Checkpoint C já havia pego a
>   mesma família num eixo diferente (L-AG3 testada só com tenant `None`, nunca com
>   string vazia).
> - **A auditoria também pegou a docstring do port afirmando o que o código não
>   faz:** `AuthorizedScope.unit_id is None` **não** significa "ação tenant-wide" —
>   `owner` e `platform_admin` fazem bypass de escopo de unidade **por papel**
>   (kickoff #9, ADR 2.1.0001, `workforce.md` §4), então `owner` + `manage_staff`
>   sem unidade também volta com `None`. **O código está certo e a prosa mentia:**
>   apertar o tradutor contradiria decisão ratificada. Corrigida a docstring e
>   travado o caso do `owner` por teste.
> - **Errata no ADR 3.4.0001** (o ADR segue `accepted`; ver a sua seção
>   `## Errata`): duas citações de `CA14` para a propriedade "zero
>   `ignore_imports`" eram **CA13**, e o ponteiro `composition_root.py:185-188`
>   passou a `:300-305`. O erro entrou no commit do corte, que renumerou os
>   critérios do concept sem reconciliar os ponteiros do ADR.
> - **Quatro `[finding]` novos escalados**, todos com Stage candidata na §7 do
>   `technical.md`: (1) **3.6** — o router **não pode** inferir "tenant-wide" de
>   `unit_id is None`, sob pena de tratar ação de funcionário de um `owner` como
>   não-escopada; (2) **3.6** — `DayPeriod.from_string` nasceu **sem produtor** em
>   produção, e o parser HTTP é o produtor natural (usá-lo, e não `DayPeriod(...)`
>   direto, que reintroduziria `ValueError` fora da faixa 422); (3) **3.6** —
>   varrer os ADRs 3.4.0002/0004/0005 atrás de intervalos de CA herdados da
>   numeração anterior ao corte, e reconciliar o `## Trade-offs` do 3.4.0001, cujos
>   `CA10–CA12` apontam para testes que migraram para a 3.6; (4) **issue futura** —
>   `CONVENTIONS.md` §Idioma manda inglês para identificadores e a suíte inteira
>   usa PT em nomes de `parametrize`; é divergência regra × prática, não defeito de
>   Stage.
> - **Nenhuma rota nasceu (CA21), e nenhuma migration.** Verificado no gate de
>   saída: `features/staff/adapters/in/` não existe, `build_http_wiring` devolve o
>   router **de identity** por identidade de objeto, as 10 rotas registradas não
>   endereçam recurso de staff, e `git diff -- migrations/` é vazio. Os 16 use
>   cases e o `AccessGuard` seguem **sem consumidor** — custo declarado no concept
>   §4, que a 3.6 consome.

#### Stage 3.6 — `3.6-staff-http`

**Descrição humana:** a borda HTTP do BC staff — 16 rotas para os 16 use cases (4 de catálogo de função, 12 de funcionário), schemas Pydantic só no boundary, handler único de erro com mapa de status total, wiring de dois routers, e e2e cobrindo fluxo feliz, isolamento entre unidades e acesso negado. É a segunda metade da Stage 3.4 original (ver a nota do bloco 3.4).

```yaml
stage_id: 3.6-staff-http
bounded_context: staff
camada_alvo: adapters/in/http
depends_on: [3.4-staff-access-scope]
arquivos_a_criar:
  - features/staff/adapters/in/http/{router,schemas,dependencies,error_handlers}.py
  - tests/e2e/features/staff/
arquivos_a_modificar:
  - composition_root.py (HttpWiring em colecoes + 17 overrides)
  - shared/infrastructure/http/app.py (registrar os dois routers e os dois registradores)
contratos_introduzidos:
  - schemas de request/response do boundary; mapa STAFF_ERROR_STATUS
contratos_consumidos:
  - os 16 use cases de 3.2; o port AccessGuard de 3.4; L-ORD de 3.3
definition_of_done:
  - "e2e: gerente cria funcao custom e funcionario com jornada; funcionario de outra unidade nao aparece"
  - "acesso negado coberto por teste (papel sem permissao -> 403)"
non_goals:
  - paginacao (ADR 3.4.0004)
  - guarda de duplicidade na copia (ADR 3.4.0005)
  - leitura de funcionario por id
  - vinculo de login do funcionario (3.5)
complexidade_estimada: M
gate_mode: strict
skills_hint: [fastapi-thin-adapter, composition-root]
```

> **Insumos já decididos — a Fase 3A da 3.6 consome, não re-deriva.**
>
> - **Três ADRs `accepted`** já governam esta Stage: **3.4.0002** (handler único
>   sobre `StaffError`, mapa total resolvido por MRO, verificação par a par
>   classe→status, `UnavailabilityNotFoundError` = **422** e não 404, 409 reservado a
>   conflito com estado gravado), **3.4.0004** (sem paginação; `L-ORD` fica cursor
>   preparado; o antídoto de uma linha da regex `_ORDER_BY` de
>   `test_staff_conduct.py:194` é aplicado por quem acrescentar `LIMIT`/`OFFSET`) e
>   **3.4.0005** (cópia repetida segue limite declarado — nem guarda por nome, que
>   recusaria homônimos legítimos, nem campo informativo, que mediria homonímia
>   enquanto o nome sugere duplicata).
> - **Inventário de rotas** (16, uma por use case): `POST|GET /job-functions`,
>   `PATCH|DELETE /job-functions/{id}` — permissão `MANAGE_JOB_FUNCTIONS`, alvo
>   tenant, **sem unidade**; e sob `/units/{unit_id}/employees` — `POST` (criar),
>   `GET` (listar, com `include_inactive`), `PATCH /{id}` (renomear),
>   `PUT /{id}/job-functions`, `PUT /{id}/workload-profile`,
>   `PUT /{id}/shift-preference`, `POST|DELETE /{id}/unavailabilities`,
>   `POST /{id}/termination`, `POST /{id}/rehire`, `DELETE /{id}`,
>   `POST /{id}/copies` — permissão `MANAGE_STAFF`, alvo tenant + unidade do path
>   (a cópia autoriza **também** a unidade destino do corpo).
> - **O rascunho completo** — inventário de schemas, mapa de status entrada a
>   entrada, e 35 critérios de aceite — está no commit **`d878060`**, em
>   `docs/stages/3.4-staff-http/concept.md` §4.1–4.3, §6 e §11.
> - **Dois `[finding]` endereçados a esta Stage** pela 3.4: identificador de
>   path/query com byte NUL ou vazio vira **500 dentro de identity** e precisa de
>   validação **na borda** — a correção de domínio da 3.4 não o alcança, porque
>   identificador não passa por entidade; e a **leitura de funcionário por id**, que
>   não existe porque o escopo de unidade foi resolvido por assinatura e não por use
>   case de leitura.
> - **`AuthorizedScope.unit_id is None` NÃO significa "tenant-wide"** — o router
>   **não pode** inferir escopo a partir dele: `owner` e `platform_admin` fazem
>   bypass de escopo por **papel** (kickoff #9, ADR 2.1.0001), então `owner` +
>   `manage_staff` sobre uma unidade também volta `None`; inferir trataria ação de
>   funcionário de um `owner` como não-escopada, **e o erro é silencioso** (não há
>   exceção, só alcance a mais). É o mais perigoso desta lista.
> - **`DayPeriod.from_string` nasceu sem produtor em produção** (3.4, Task 02) — o
>   parser HTTP desta Stage é o produtor natural: usar `from_string` (que levanta
>   `InvalidDayPeriodError`, um `StaffError`, mapeável a 422) e **não**
>   `DayPeriod(...)` direto, que reintroduziria `ValueError` fora da faixa mapeada.
> - **Varrer os ADRs `3_4_0002`/`0004`/`0005` atrás de intervalos de CA defasados**
>   pela renumeração de critérios feita no corte da Stage 3.4 — o mesmo defeito que
>   gerou a `## Errata` do ADR 3.4.0001 —, e reconciliar os ponteiros antes de
>   consumi-los na Fase 3A.

> **Nota (2026-08-30): reconciliação pós-execução da Stage 3.6.** O bloco e a nota
> de insumos acima foram conferidos contra o executado — **continuam fiéis**, e os
> três eixos que o bloco precisava corrigir já estavam medidos antes da execução,
> na §1 do [`concept.md`](./stages/3.6-staff-http/concept.md) ("Reconciliação do
> bloco 3.6 do roadmap"): `arquivos_a_modificar` incompleto (entram o docstring do
> port `access_guard.py` e o fake `in_memory_access_guard.py`, porque a lei do
> tenant resolvido vale para as **duas** implementações), `contratos_introduzidos`
> incompleto (entram o **validador de identificador de borda** e o **conversor de
> `weekly_hours`**, que definem o status de classes inteiras de entrada que antes
> terminavam em 500) e o `definition_of_done` de dois itens, que continua correto e
> continua sendo o DoD — a §11 do concept o detalha em critérios parametrizados
> sobre domínio enumerado, sem substituí-lo. O que segue é o que **só a execução**
> podia dizer.
>
> - **O que a Stage entregou.** As **16 rotas** de staff sob `/api/v1` — quatro de
>   catálogo de função de trabalho e doze de funcionário —, servidas pela mesma app
>   que já servia as **10 de identity**: o esquema OpenAPI publica **26 operações**.
>   Cada rota declara a permissão exigida e o alvo e delega a decisão ao port
>   `AccessGuard` da 3.4 por `Depends`, nunca por middleware; o registro é
>   endereçado pelo **path**, e o router **nunca lê** `AuthorizedScope.unit_id`
>   (ADR 3.6.0001 — era o finding mais perigoso herdado da 3.4). O mapa
>   `STAFF_ERROR_STATUS` é **total** sobre as exceções do BC e resolvido por MRO
>   (ADR 3.4.0002), e todo identificador que chega por **path, query ou corpo** é
>   recusado na borda quando vazio, só-whitespace ou com byte NUL — **depois de
>   autenticar e antes de qualquer chamada de autorização** (ADR 3.6.0002).
>   **12 Tasks**, uma por commit, mais **30 commits** de concept/technical/ADR,
>   correção de Checkpoint e fechamento de auditoria.
> - **File-scope real: 10 arquivos de `src/`** — os quatro do adapter novo
>   (`router.py`, `schemas.py`, `dependencies.py`, `error_handlers.py`) e dois
>   `__init__.py`, mais `composition_root.py` (`HttpWiring` em coleções e 17
>   overrides), `shared/infrastructure/http/app.py` (os dois routers e os dois
>   registradores), o docstring do port `access_guard.py` e
>   `rename_job_function.py`. **Fora de `src/` o bloco não previa dois docs
>   estruturais** que a Stage tocou: `docs/LAYOUT.md` (a regra do tenant nas Regras
>   de Ouro) e `docs/overview.md` §10 (as fontes primárias do ADR 0.0.0005) — os
>   dois pela mesma decisão. **Nenhuma migration**, como o bloco previa.
> - **Cinco ADRs `accepted`, todos com `context_stage: 3.6-staff-http`.** Quatro de
>   Stage: **3.6.0001** (o path endereça o registro, e o escopo autorizado nunca é
>   lido), **3.6.0002** (validação de identificador na borda), **3.6.0003** (a
>   representação no fio preserva as garantias do domínio — união discriminada,
>   `weekly_hours` como string, datetimes ingênuos, conjuntos ordenados na saída) e
>   **3.6.0004** (a checagem local mais barata primeiro, no rename de função). E um
>   **global**, nascido aqui:
>   **[ADR 0.0.0005](./adr/0_0_0005-tenant-comes-from-the-token-unless-it-is-the-resource.md)**,
>   `bounded_context: transversal` — **o tenant que decide acesso vem do token**, e
>   um tenant na requisição é declaração *confirmada contra* ele, nunca a fonte. Ele
>   fecha o fork F1, e o fork existia porque, medido contra o código real,
>   **nenhuma das 16 rotas era alcançável por nenhum papel**: o router de staff não
>   tinha como nomear o tenant que `AuthorizeActionUseCase` exige. O inventário de
>   rotas segue sem tenant no path — agora **por regra, não por omissão**, e nenhuma
>   assinatura de port mudou.
> - **Expansão de camada declarada, e é a terceira para trás no BC staff.** A
>   camada-alvo é `adapters/in/http`, mas o ADR 3.6.0004 emendou a **`application`
>   da 3.2**: `RenameJobFunctionUseCase` passou a fazer a transição de domínio
>   **antes** de sondar a unicidade do nome, com **errata datada** na linha
>   `rename_job_function` da tabela §5.16 do
>   [`concept.md` da 3.2](./stages/3.2-staff-application/concept.md) — emendada,
>   não reescrita em silêncio. O sintoma apareceu pela API real (nome com byte NUL
>   em `PATCH /job-functions/{id}` chegava cru ao psycopg: `DataError`, que não é
>   `IntegrityError` nem `StaffError` e não tem handler ⇒ **500**), e a re-medição
>   com o fake provou que **não era defeito de NUL**, e sim desvio de ordem — `""` e
>   `"   "` também tocavam o port. A lei já estava escrita na nota que fecha aquela
>   tabela (*"a checagem mais barata que possa falhar sozinha vem primeiro"*) e só
>   um dos dois use cases a obedecia. Com **3.2→3.1, 3.4→3.1 e agora 3.6→3.2**, são
>   três Stages seguidas alcançando para trás — todas declaradas, nenhuma silenciosa,
>   e todas pela mesma causa: propriedade só **observável** na camada de fora,
>   escrita numa camada de dentro que não tinha como medi-la. A §7 do
>   `technical.md` registra isso como `[finding]` para a retrospectiva do Step 3.
> - **A auditoria independente aplicou ~25 mutações e três sobreviveram** — as três
>   sobre linhas com **100% de cobertura de linha e de ramo**, e nenhuma era defeito
>   vivo: as três eram buraco de suíte. (a) A lei *autenticar antes de validar a
>   entrada* vale para toda rota com corpo ou query obrigatórios e estava travada em
>   **1 rota de 9**, por um teste escrito à mão. (b) `EmptyShiftPreferenceError`
>   **não tinha caminho HTTP** — quinze das dezoito entradas do mapa não tinham —, e
>   apagar em silêncio a preferência declarada devolvia 200. (c) A disjunção *tenant
>   vazio ou ausente* no **argumento de entrada** do guard, **reincidência de
>   `L-AG3`**: a 3.4 enumerou o par no tenant que identity devolve, e nunca no que o
>   chamador pede. As três foram fechadas quantificando a lei sobre o domínio
>   **derivado por introspecção**, com a **cardinalidade asserida na mesma prova**, e
>   **as três morrem** sob a mutação que antes sobrevivia — verificado, mutação a
>   mutação. Outros três achados menores fecharam junto (elementos de lista fora do
>   domínio de CA24, `AccessRequirement.names_unit` declarado e nunca lido, duas
>   declarações faltando no handler).
> - **Números finais:** `make check` verde, **2895 testes**, cobertura **99,94%**,
>   arquivos da Stage a **100%**.
> - **Findings escalados — onde já havia issue, o número foi apontado.** O tradutor
>   do `AccessGuard` no composition root (concept §10) já tem casa: issue
>   [#47](https://github.com/MarceloSanC/restaurant-hub/issues/47), e não foi
>   duplicado. O resíduo de `workforce.md` §4 × ADR 3.4.0006 é da **mesma varredura**
>   da issue [#37](https://github.com/MarceloSanC/restaurant-hub/issues/37), cujo
>   escopo hoje diz `3_1_*`/`3_2_*` e precisa admitir `3_4_*`. Os demais seguem só
>   com Stage candidata:
>   - **O `technical.md` da 3.2 ainda declara a ordem antiga do rename** (Task 07,
>     em prosa), e a seção está **congelada** por
>     `scripts/check_technical_postexec.py`. A direção (a) **já foi executada nesta
>     Stage** — há `[finding]` datado na §7 daquele technical, o único trecho
>     editável, apontando o ADR 3.6.0004. O que fica aberto é (b): **o freeze não
>     tem forma de errata**. Não é Stage — é mudança na regra do script +
>     `CONVENTIONS` §3.4, a abrir como **issue própria**; sem issue hoje.
>   - **Os buracos de F1 e F3 podem ter gêmeos em `identity`, e isso NÃO foi
>     medido.** Nenhuma mutação foi aplicada lá para (a) a ordem
>     `Depends`-antes-do-corpo nas rotas de identity nem (b) a cláusula que lê
>     `ator.claims.tenant_id` direto. Não tratado aqui por ser **BC alheio** —
>     expansão mais larga que as três de camada acima, que ao menos ficaram dentro
>     de `features/staff/`. Stage candidata: a primeira do Step 5 que reabrir a
>     borda HTTP de identity, ou a retrospectiva do Step 3.
>   - **Dois resíduos em `identity/adapters/in/http` que o ADR 0.0.0005 nomeia e não
>     corrige:** o docstring de `create_unit` justifica o `restaurant_id` do path
>     pelo **efeito de autorização**, que é o argumento fraco — o mesmo com que o
>     ADR rejeita a alternativa análoga em staff —, e a resolução do tenant em
>     `POST /users` e `POST /users/invitations` vive no router sem que nenhum doc de
>     identity o declare. Uma frase apontando o ADR em cada docstring resolve. Stage
>     candidata: a próxima que toque `features/identity/adapters/in/http`.
>   - **A terceira expansão de camada para trás** (bullet acima) — retrospectiva do
>     Step 3, ou a primeira Stage de domínio do Step 4.
>   - **Custo da matriz e2e:** `test_staff_authorization.py` são **162 casos** contra
>     Postgres real, em **2m55s**, porque cada célula reprovisiona o cenário inteiro
>     pela API. Se a suíte ganhar mais um eixo, medir um cenário de escopo `module`
>     para os eixos read-only, mantendo isolamento por caso onde há escrita. Stage
>     candidata: a primeira da 4.x que acrescentar e2e de acesso.
>   - **Herdados que continuam abertos** (concept §10): paginação das listagens, com
>     o antídoto de uma linha da regex `_ORDER_BY` (ADR 3.4.0004); leitura de
>     funcionário por id e sinal de cópia repetida na borda (ADR 3.4.0005), os dois
>     no eixo de cliente/UX — primeira Stage de frontend do Step 3; byte NUL em
>     nomes de `identity` (`Restaurant`/`Unit`/`User`), que lá também vira 500; e
>     `CONVENTIONS` §Idioma × a suíte inteira em PT, que a 3.4 já concluiu **não ser
>     escopo de Stage** — vira issue de documentação, ainda não aberta.
> - **O Step 3 não fecha aqui.** Os 16 use cases e o `AccessGuard` deixaram de
>   nascer sem consumidor — o BC passou a ser exercitável pelo entrypoint real,
>   que é o critério do DoD —, mas a **3.5** (vínculo de login do funcionário) segue
>   `draft` e depende desta Stage, e o Step só é `done` com a contraparte de
>   frontend (regra do §Escopo deste roadmap).

#### Stage 3.5 — `3.5-employee-login-link`

**Descrição humana:** fatia vertical "criar login para este funcionário": use case em staff consumindo contrato de identity (criar usuário employee + convite/senha provisória) e vinculando `user_id` ao funcionário.

```yaml
stage_id: 3.5-employee-login-link
bounded_context: staff
camada_alvo: vertical (staff, consumindo port de identity)
arquivos_a_criar:
  - features/staff/application/ports/out/identity_gateway.py
  - features/staff/application/use_cases/create_login_for_employee.py
  - features/staff/adapters/out/identity/local_identity_gateway.py (chama use cases de identity in-process)
  - rota no router de staff + testes
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos:
  - IdentityGateway (port-out de staff)
contratos_consumidos:
  - invite_user/create_user de identity (2.2/2.5)
definition_of_done:
  - "e2e: botão-endpoint cria user employee, envia convite (ou senha provisória) e vincula ao funcionário"
non_goals:
  - página do funcionário ver escala (Step 4)
complexidade_estimada: S
gate_mode: strict
skills_hint: [hex-arch-python, composition-root]
```

> **Nota (2026-09-26): reconciliação pós-execução da Stage 3.5** (issue #51; concept e technical em
> `docs/stages/3.5-employee-login-link/`; ADRs 3.5.0001–0004). O bloco acima foi escrito antes do
> kickoff e fica como registro; o que a execução mudou:
>
> - **"Convite ou senha provisória" virou "convite por e-mail ou link de definição de senha
>   entregue em mãos"** (decisão do sponsor, concept §13 Q1; ADR 3.5.0002): a conta nasce
>   pendente com `unusable_hash` e o **mesmo** token de setup do convite; o canal `link` devolve
>   o link na resposta, com prazo próprio (`Settings.handover_link_ttl_hours`, 168h contra 72h).
>   Não há senha provisória nem reemissão de link — link perdido é recuperado pelo pedido público
>   de redefinição de senha.
> - **A travessia entre BCs ganhou forma** (ADR 3.5.0001): identity expõe
>   `features/identity/application/facade.py` (Open Host Service, primitivos) e staff a consome em
>   `adapters/out/identity/local_identity_gateway.py` — a **única** aresta, nomeada no contrato
>   `bc-independence` (um par + `unmatched_ignore_imports_alerting = error`), regra agora em
>   `LAYOUT.md` §3. Supersede parcialmente o ADR 3.4.0001 §3 ("zero `ignore_imports`"), por nota
>   datada no próprio ADR (`CONVENTIONS.md` §5, terceira forma).
> - **A Stage entregou em dois BCs** (divergência de PIPELINE §4.2 #4 autorizada pelo sponsor,
>   concept §13 Q6): em identity, `Email` recusa o byte NUL (era 500 em três rotas),
>   `ProvisionAccountUseCase`/`SendInvitationUseCase`/`RevokeAllSessionsUseCase`, o helper
>   `_invitation.py` (única casa do formato do link) e a fachada; em staff, `Employee.user_id`
>   (coluna `TEXT NULL` sem FK/UNIQUE/índice, migration `0004`, ADR 3.5.0004), o port
>   `IdentityGateway` com quatro leis e contrato fake × real, três use cases (R17 novo; R13 revoga
>   sessões antes de gravar; R15 recusa vinculado com 409 — ADR 3.5.0003), a rota R17 com **dupla
>   permissão** (`manage_staff` e `manage_users`) e `user_id` em toda resposta de funcionário.
> - **`complexidade_estimada: S` → M** (12 Tasks + 6 commits de `fix` vindos dos Checkpoints C e
>   da auditoria de testes; 5 Checkpoints C; auditoria independente; as oito mutações de CA28
>   mortas). `contratos_consumidos` não são `invite_user`/`create_user`: são os três use cases
>   novos de identity, atrás da fachada.
> - **Sincronização com o `develop` por merge** (`0c9fd8a` + `58f6694`): a #45 renomeou
>   `adapters/in` → `adapters/inbound` e centralizou os mappers de result; a 3.5 adotou
>   `to_employee_result` (com `user_id`) e `to_user_result`, e apagou o `use_cases/_results.py`
>   que ela havia criado para o mesmo fim. Decisão e divergência da Etapa 4 do GIT-WORKFLOW na
>   §7 do technical.
> - **Findings abertos** (technical §7): `AuthenticationResult.refresh_token` sem `repr=False`
>   (identity, herdado da 2.2); o guarda de não-ramificação não pega `__class__.__name__`;
>   `foi_revogado` do contrato real observa chamada, não estado; varredura derivada de
>   `validate_identifier` por rota. Issue #47 re-escopada (ADR 3.5.0001 §5): o tradutor de acesso
>   fica no `composition_root` até identity expor a autenticação fora do adapter de entrada.

#### Stage 3.7 — `3.7-application-authorization`

**Descrição humana:** a camada application de staff passa a ser fail-closed por si — todo use case recebe o port `AccessGuard` por construtor e autoriza o alvo do seu command antes de qualquer outra instrução de `execute`. A borda HTTP continua autorizando (defesa em profundidade) e responde igual. Nasce da issue [#49](https://github.com/MarceloSanC/restaurant-hub/issues/49), promovida a Stage em 2026-10-19 (PIPELINE §4.5: carrega ADR e uma propriedade sobre a camada inteira).

```yaml
stage_id: 3.7-application-authorization
bounded_context: staff
camada_alvo: application (staff) — com o ajuste dos dois consumidores (composition_root e router)
arquivos_a_criar:
  - tests/fakes/features/staff/{denying,permissive}_access_guard.py
  - tests/unit/features/staff/application/test_use_cases_authorize.py (propriedade, forma e totalidade sobre a pasta use_cases/)
  - teste da cadeia real (tradutor -> IdentityGuard -> AuthorizeActionUseCase em memoria)
arquivos_a_modificar:
  - features/staff/application/ports/out/access_guard.py (vocabulario de permissao migra da borda)
  - features/staff/application/dtos/{commands,queries}.py (o ator entra no command)
  - features/staff/application/use_cases/*.py (17 use cases)
  - features/staff/adapters/inbound/http/{router,dependencies}.py
  - composition_root.py (o guard entra em cada use case)
  - features/staff/application/ports/out/identity_gateway.py + adapters/out/identity/local_identity_gateway.py (so docstring)
  - docs: ADR 3.2.0002 e 3.4.0001 (supersessao parcial datada), concept 3.2 §5.16 (errata datada)
  - tests de application e de borda (unit) de staff; tests/e2e intocado
contratos_introduzidos:
  - campo actor em todo command/query de staff; vocabulario de permissao no port
contratos_consumidos:
  - AccessGuard + leis L-AG1..L-AG4 (3.4); ADR 0.0.0005; 17 use cases (3.2, 3.5)
definition_of_done:
  - "todo use case de staff autoriza pelo AccessGuard o alvo do proprio command antes de qualquer outra instrucao de execute — provado por propriedade sobre a pasta use_cases/ inteira, com as faixas HTTP inalteradas"
non_goals:
  - remover o guard da borda HTTP (continua, como defesa em profundidade)
  - mudar as quatro leis do port, o vocabulario str da permissao ou a matriz de papeis
  - estender o AccessGuard a identity (AuthorizeActionUseCase e a fachada sao outro caso)
  - mover o tradutor de acesso para fora do composition_root (issue #47)
complexidade_estimada: M
gate_mode: strict
skills_hint: [hex-arch-python, composition-root, pytest-with-fakes, fastapi-thin-adapter, task-ordering-hex]
```

> **Nota (2026-10-19): reconciliação pós-execução da Stage 3.7** (issue #49; concept e technical em
> `docs/stages/3.7-application-authorization/`; ADR 3.7.0001). O bloco acima foi escrito na promoção e
> fica como registro; o que a execução mostrou:
>
> - **A forma:** guard por construtor nos 17 use cases, ator como **primeiro campo** de todo command e
>   query (`execute(<Command>)` não muda — LAYOUT §5), e o tenant do command **confirmado** pelo guard,
>   não derivado do escopo (ADR 0.0.0005 cl. 1). Supersessão parcial datada nos ADRs 3.2.0002 ("use
>   cases sem ator"), 3.4.0001 §4 (só para `authorize`) e 3.6.0004 (a regra da checagem mais barata
>   vale depois da autorização), e errata no concept 3.2 §5.16.
> - **File-scope real:** os arquivos do bloco (os dois dublês num módulo só, `stub_access_guards.py`), mais `test_application_authorization_chain.py`
>   (CA14, cadeia de produção sem banco), as suítes de borda unitárias que montam use case por reflexão, as sequências exatas de chamada ao guard
>   e 178 citações por linha deste roadmap remapeadas em sete docs de scheduling (technical §7). `tests/e2e/` **intocado** e verde — nenhuma faixa HTTP mudou.
> - **7 Tasks + 3 `fix` + 1 `extra`.** Os Checkpoints C acharam três classes de buraco que um caminho
>   feliz não pega: o ator não registrado pelos dublês (autorizar `None` passava), tabela e código
>   errando juntos (a cópia autorizando a origem duas vezes) e recusa por motivo errado no CA14; a
>   auditoria independente aplicou **13 mutações reais, todas mortas**, e apontou dois testes de efeito
>   faltantes. **+307 testes** sobre a base, arquivos da Stage a **100%**.
> - **Findings abertos** (technical §7): autenticidade do ator e validação de identificador fora da
>   borda HTTP (Stage do primeiro driver não-HTTP), staff como provedor do `StaffReadPort` e a adoção do
>   padrão na 4.3, ponteiros `(#49)` do lado de identity, custo da dupla autorização (6.3).

#### Stage 3.8 — `3.8-termination-access-scope`

**Descrição humana:** desligar um registro de funcionário (R13) passa a revogar as sessões do login vinculado **só quando o registro é a fonte do acesso** — registro ativo, conta de papel `employee` e nenhum outro registro ativo **da mesma unidade** apontando para ela. Login de gerente/dono vinculado a um registro de escala, ou pessoa com outro registro ativo na unidade, não perde as sessões; desligar nunca desativa a conta. Promovida da issue #60 (achado F2 da auditoria pós-merge da 3.5; PIPELINE §4.5: contrato de port novo + ADR que supersede parcialmente o 3.5.0003).

```yaml
stage_id: 3.8-termination-access-scope
bounded_context: staff
camada_alvo: vertical (staff, consumindo consulta nova da fachada de identity)
depends_on: [3.5-employee-login-link]
arquivos_a_criar:
  - features/identity/application/use_cases/get_account_role.py
  - docs/adr/3_8_0001-termination-revokes-only-access-the-record-grants.md
arquivos_a_modificar:
  - features/identity/application/{facade.py,dtos/commands.py,dtos/results.py,use_cases/revoke_all_sessions.py}
  - features/staff/application/ports/out/identity_gateway.py (lei L-IG5)
  - features/staff/adapters/out/identity/local_identity_gateway.py
  - features/staff/application/{use_cases/deactivate_employee.py,errors.py}
  - composition_root.py (wiring da fachada)
  - docs/domain/staff/workforce.md (nota datada em §3.8); docs/adr/3_5_0003 (supersessao parcial)
contratos_introduzidos:
  - IdentityGateway.is_employee_login (L-IG5); IdentityFacade.account_role; GetAccountRoleUseCase
contratos_consumidos:
  - IdentityFacade e RevokeAllSessionsUseCase (3.5); L-IG4 (3.5); EmployeeRepository.list_by_unit (L-E6)
definition_of_done:
  - "R13 revoga as sessoes so se o registro estiver ativo, a conta for employee e nao houver outro registro ativo do login na mesma unidade; (a) e (b) travados por teste, inclusive e2e"
non_goals:
  - vincular/desvincular login existente (concept 3.5 §10)
  - User.is_active / desativacao de conta (ADR 3.8.0001: desligar nunca desativa)
  - olhar registros de outras unidades; revogacao por escopo de unidade
complexidade_estimada: S
gate_mode: strict
skills_hint: [hex-arch-python, pytest-with-fakes, composition-root]
```

> **Nota (2026-10-19): fechamento da Stage 3.8** (issue #60; concept e technical em
> `docs/stages/3.8-termination-access-scope/`; ADR 3.8.0001). O que a execução fixou:
>
> - **Quatro decisões do sponsor** (concept §13): revogar só com papel `employee` + último vínculo
>   ativo (Q1); desligar **nunca** desativa a conta (Q2); a Stage entrega em staff + identity
>   (Q3); "outro registro ativo" olha **só a mesma unidade** (Q4) — por isso não há método novo no
>   repositório: a checagem lê `list_by_unit` (L-E6).
> - **Identity:** `GetAccountRoleUseCase` + `IdentityFacade.account_role` (somente leitura).
>   **Staff:** lei L-IG5 (`is_employee_login`) com contrato fake × real; R13 com a regra e a guarda
>   `employee.active`. Sem migration.
> - **6 Tasks + 5 commits de correção** (Checkpoints C) **+ 1 extra** (auditoria de testes: 500 na
>   borda para falha antes da escrita, lacuna herdada da 3.5). Findings na §7 do technical.


#### Stage 3.9 — `3.9-error-hierarchy`

**Descrição humana:** tirar o protocolo HTTP de dentro da hierarquia de exceções. Hoje a ordem das classes-base de um erro "não encontrado" é escolhida para que o lookup de handler do Starlette (que percorre o `__mro__`) chegue ao 404 antes do 422, e a docstring de `shared/domain/exceptions/base.py` define as classes pelo status HTTP. A Stage desfaz a herança dupla, recria `ApplicationError` para os erros que não são violação de regra de negócio (cada um com entrada própria no mapa de status do BC) e põe um detector de vocabulário de protocolo nos módulos da hierarquia. Neutra em comportamento observável: as faixas 401/403/404/409/422 e os corpos ficam byte-idênticos. Promovida da issue #48 (supersede o ADR 2.2.0003 — PIPELINE §4.5: ADR que supera outro + regra sobre a camada inteira).

```yaml
stage_id: 3.9-error-hierarchy
bounded_context: shared
camada_alvo: shared (domain + application) + identity/staff/scheduling (application, adapters/inbound/http) + tooling
depends_on: [3.6-staff-http, 4.3-scheduling-application]
arquivos_a_criar:
  - shared/application/errors.py
  - docs/adr/3_9_0001-*.md
arquivos_a_modificar:
  - shared/domain/exceptions/base.py; shared/infrastructure/http/{error_handlers.py,app.py}
  - features/{identity,staff,scheduling}/application/errors.py
  - features/{identity,staff,scheduling}/domain/exceptions/errors.py (docstrings)
  - features/{identity,staff}/adapters/inbound/http/error_handlers.py
  - scripts/check_layout.py (regra nova); tests/unit/test_status_map.py
  - docs/adr/{2_2_0003,2_4_0001,3_4_0002}; docs/LAYOUT.md
contratos_introduzidos:
  - ApplicationError (shared/application) e uma raiz de aplicação por BC
contratos_consumidos:
  - mapa exaustivo erro -> status (Gate 3 da #45); ADR 2.4.0001 e 3.4.0002 (faixas e corpos)
definition_of_done:
  - "nenhuma classe de erro herda de duas raizes; erros que nao sao regra de negocio herdam de ApplicationError com entrada propria no mapa; modulos da hierarquia sem vocabulario de protocolo, travado por gate; e2e de faixas intocados e verdes"
non_goals:
  - mudar status ou corpo de qualquer resposta
  - mexer nas conversoes do guard que fecham oraculo de enumeracao (ADR 2.4.0001 §5)
  - mapa de status de scheduling (Stage 4.5)
complexidade_estimada: M
gate_mode: strict
skills_hint: [hex-arch-python, fastapi-thin-adapter, pytest-with-fakes]
```

> **Nota (2026-11-02): fechamento da Stage 3.9** (issue #48; concept e technical em
> `docs/stages/3.9-error-hierarchy/`; ADR 3.9.0001, que supera o 2.2.0003). O que a execução fixou:
>
> - **Partição por significado:** 14 erros de identity, 4 de staff e 6 de scheduling migram para a
>   raiz de aplicação do BC; `ScheduleVersionConflictError` fica no domínio (regra canônica de
>   concorrência, decisão do sponsor F8). Erro levantado por objeto de domínio é domínio por construção.
> - **`NotFoundError` e o handler genérico 404 saíram**; não há rede genérica para `ApplicationError`.
>   O Gate 3 cobra raiz única do BC, mapa total sobre as duas raízes e handler em cada raiz.
> - **Regra 11 de `check_layout.py`** reprova vocabulário de protocolo nos módulos de exceção.
> - **8 Tasks + 5 commits de correção** (Checkpoints C) **+ 2 extras** (auditoria de testes, 3 rodadas).
>   Oráculos e2e de faixa intocados. Findings para a 4.5 na §7 do technical.


---

### Step 4 — Escala manual publicável (BC `scheduling`)

- **Resultado de negócio:** gerente configura faixas por dia e demanda por função, aloca pessoas com validação ao vivo (bloquear/avisar configurável), salva=publica com auditoria; funcionário logado vê a própria escala; e-mail opcional a cada publicação; imagem/tabela gerada sob demanda; escalas anteriores viram referência fácil. **Aposenta a planilha.**
- **Depende de:** Step 3.
- **Tamanho estimado:** M–L (7 Stages; cada uma ≤ M)

> **Nota (2026-09-14, revista em 2026-09-26): gate de domínio do Step 4 cumprido (issue #52).**
> `docs/domain/scheduling/shift-scheduling.md` está `accepted` (ratificado pelo sponsor) com os
> ADRs 4.1.0001–4.1.0006. Os concepts 4.x consomem sem re-derivar: **salvar = publicar literal**
> (sem rascunho no servidor; `block` recusa a mutação; concorrência otimista por versão — 4.1.0001);
> **semana com dia de início configurável + dia operacional com corte configurável (default 05:00)**
> e **horas = duração − intervalo declarado na faixa** (4.1.0002); **8 políticas v1** — as quatro do
> bloco 4.2 (com o teto contado em dia e em semana; sobreposição em `block`) mais alocação ×
> indisponibilidade (`block` fixo), função não detida (`warn` com exceção de função na alocação)
> e sobre-cobertura da demanda (`warn`; `N` é alvo, não teto), defaults trabalhistas ancorados em fonte
> primária e configuráveis por restaurante (4.1.0003); **`hr` lê a escala** nas suas unidades
> (4.1.0004 — errata no ADR 3.4.0006 §3); **`Unit.timezone` em identity**, lido por port (4.1.0005);
> **desligamento reconciliado na leitura** — sem evento, sem FK, inativo omitido de toda tela até a
> página de histórico; guarda de remoção definitiva por port de consulta reverso (4.1.0006 —
> erratas nos ADRs 3.2.0006 e 3.4.0002). **Lacunas de escopo deste roadmap** (doc §6): (a) em que
> Stage entra a coluna `Unit.timezone` — 4.4 ou issue avulsa de identity antes da 4.3; (b) dono do
> mapa período nomeado → faixas (`workforce.md` §3.5 delega ao Step 4; nenhum bloco 4.x o lista) —
> proposta: 5.1, primeiro consumidor; (c) o bloco 5.2 fala em "rascunho de edição" e tem o
> non-goal "aplicar+publicar num passo só", em tensão com salvar = publicar — reavaliar no gate do
> Step 5; (d) o bloco 4.2 lista quatro políticas e `arquivos_a_criar` correspondentes — o concept
> da 4.2 declara a divergência (oito políticas; teto diário e semanal podem ser uma ou duas). O
> `depends_on: 3.5-employee-login-link` da 4.1 é ordenação, não dependência técnica (a 4.1 consome
> só ids de staff) — ajuste no kickoff da 4.1.

#### Stage 4.1 — `4.1-scheduling-domain`

> **Nota (2026-09-26): `depends_on` corrigido de `3.5-employee-login-link` para
> `3.1-staff-domain`** (tabela de Stages e grafo). A relação com a 3.5 era **ordenação**, não
> dependência técnica: a 4.1 consome apenas `EmployeeId`/`JobFunctionId` da 3.1 (por id, sem
> import de entidade) e nada que a 3.5 introduz. A nota do Step 4 já registrava o ajuste como
> pendente do kickoff (issue #55).

**Descrição humana:** modelar Escala (período configurável, default semanal), Faixa/Turno por dia, Demanda por função×faixa, Alocação de funcionário e o evento de publicação (salvar=publicar, com registro de quem/quando); invariantes estruturais (demanda ≥ 0, alocação dentro do período etc.).

```yaml
stage_id: 4.1-scheduling-domain
bounded_context: scheduling
camada_alvo: domain
arquivos_a_criar:
  - features/scheduling/domain/entities/{schedule,shift_demand,assignment}.py
  - features/scheduling/domain/value_objects/{schedule_period,time_range,demand_quantity}.py
  - features/scheduling/domain/exceptions/ + tests unit
arquivos_a_modificar: []
contratos_introduzidos:
  - Schedule, ShiftDemand, Assignment (entities); SchedulePeriod, TimeRange (value-objects)
contratos_consumidos:
  - EmployeeId/JobFunctionId de staff (referência por id, sem import de entidade — regra LAYOUT)
definition_of_done:
  - "montagem e publicação de escala com invariantes cobertas por testes unitários"
non_goals:
  - validações configuráveis (4.2); auto-fill (Step 5)
complexidade_estimada: M
gate_mode: strict
skills_hint: [ddd-tactical-patterns, hex-arch-python]
```

> **Nota (2026-09-27): reconciliação pós-execução da Stage 4.1** (issue #55; concept e technical em
> `docs/stages/4.1-scheduling-domain/`; ADRs 4.1.0007–4.1.0012). O bloco acima foi escrito antes do
> kickoff e fica como registro; as nove divergências estão declaradas no concept §1:
>
> - **Arquivos.** `arquivos_a_modificar` deixou de ser `[]`: `.importlinter` ganhou o contrato
>   `scheduling-domain-purity` e `scheduling` entrou em `bc-independence`. `arquivos_a_criar`
>   cresceu com os placeholders `application/` e `adapters/`, `identifiers.py`,
>   `operational_calendar.py` e `entities/shift_band.py`. Dois testes de nível de repositório
>   (`test_status_map.py`, `staff/test_bc_independence.py`) entraram no file-scope porque o
>   terceiro BC os reprovava.
> - **Modelo.** Quatro entidades, não três: a faixa habilitada é `ShiftBand`, glosa EN nova de
>   "faixas de funcionamento" (ADR 4.1.0010; nota em `shift-scheduling.md` §6). **Não há evento de
>   publicação** — superado pelo ADR 4.1.0001 §1; do F1/F8 sobra no domínio o contador de versão,
>   e o DoD lê-se "montagem da escala com invariantes cobertas por testes unitários".
> - **Contratos.** Introduzidos crescem: 8 ids próprios, `Weekday`/`DayCutoff`/`OperationalCalendar`,
>   `DemandQuantity`, `ShiftBand`, as marcas de `Assignment`, a versão, `SchedulingError` + 20
>   subclasses e 11 mutações na raiz. Consumido é só `DomainError` de `shared/`: scheduling tipa os
>   seus `EmployeeId`/`JobFunctionId`, sem import de staff. `depends_on` = `3.1-staff-domain`
>   (nota acima).
> - **ADRs da Stage.** 4.1.0007 (`TimeRange` de instantes ingênuos de minuto inteiro; sítio único de
>   horas), 4.1.0008 (faixa além do corte é do dia em que começa), 4.1.0009 (`Schedule` raiz
>   única), 4.1.0010 (faixa habilitada; demanda única por (faixa, função)), 4.1.0011 (intervalo na
>   faixa e na alocação; errata no 4.1.0002), 4.1.0012 (uma vaga por registro em cada faixa).
> - **Decisões do sponsor** (concept §13). Q1: desabilitar faixa ou retirar demanda com gente
>   alocada **recusa**, sem cascata. Q2: `reschedule_band` **preserva** demandas e alocações, no
>   mesmo dia operacional. Q3: intervalo **na faixa e na alocação**, divergência derivada. Q4: o
>   mesmo registro **não** ocupa duas vagas da mesma faixa (invariante). Q5: corte **sem teto**.
> - **Execução.** Variante autônoma até o PR, sem auto-merge; 10 Tasks; branch rebaseada sobre o
>   `develop` depois do merge da 3.5 (technical §7).
> - **Findings abertos** (technical §7), todos da **4.3** salvo o último: `operational_day_of`
>   aceita instante tz-aware ou com segundos → validar na entrada; `change_demand_quantity` com o
>   mesmo N gera versão → no-op no domínio (4.3, D2); `.env` sem `DATABASE_URL` → issue #58.

#### Stage 4.2 — `4.2-validation-policies`

**Descrição humana:** políticas de validação **parametrizáveis por restaurante** como estratégias plugáveis de domínio (sobreposição de alocações, descanso mínimo entre jornadas, teto de horas dia/semana, carga contratada), cada uma com modo `block`/`warn`; avaliador que devolve lista de violações para a UI exibir ao vivo.

```yaml
stage_id: 4.2-validation-policies
bounded_context: scheduling
camada_alvo: domain
arquivos_a_criar:
  - features/scheduling/domain/services/validation/{policy_protocol,overlap_policy,rest_between_shifts_policy,max_hours_policy,workload_policy,evaluator}.py
  - features/scheduling/domain/value_objects/validation_config.py
  - tests unit por política e do evaluator
arquivos_a_modificar: []
contratos_introduzidos:
  - ValidationPolicy (protocol), ValidationConfig, Violation (VOs)
contratos_consumidos:
  - entidades de 4.1; WorkloadProfile de staff (por dados, não import)
definition_of_done:
  - "evaluator aplica só políticas habilitadas na config do restaurante e distingue block × warn (testes unit)"
non_goals:
  - persistir config (4.4); UI
complexidade_estimada: M
gate_mode: strict
skills_hint: [ddd-tactical-patterns, hex-arch-python]
```

#### Stage 4.3 — `4.3-scheduling-application`

**Descrição humana:** use cases: criar/configurar escala do período, editar demanda e alocações com avaliação de violações a cada mudança, aceitar violações warn, publicar (salvar), consultar calendário (dia/semana/mês), listar escalas anteriores e "minha escala" do funcionário; ports (ScheduleRepository, StaffReadPort, ScheduleConfigRepository).

```yaml
stage_id: 4.3-scheduling-application
bounded_context: scheduling
camada_alvo: application
arquivos_a_criar:
  - features/scheduling/application/use_cases/{create_schedule,update_demand,assign_employee,evaluate_schedule,publish_schedule,get_calendar,list_past_schedules,get_my_schedule,...}.py
  - features/scheduling/application/ports/out/{schedule_repository,schedule_config_repository,staff_read_port}.py
  - dtos + tests com fakes
arquivos_a_modificar: []
contratos_introduzidos:
  - ScheduleRepository, ScheduleConfigRepository, StaffReadPort (ports-out)
contratos_consumidos:
  - domain 4.1/4.2; dados de staff via StaffReadPort
definition_of_done:
  - "fluxo editar→avaliar→publicar coberto com fakes, incluindo aceite consciente de warns"
non_goals:
  - e-mail (4.6), imagem (4.7), auto-fill (5)
complexidade_estimada: M
gate_mode: strict
skills_hint: [pytest-with-fakes, task-ordering-hex]
```

#### Stage 4.4 — `4.4-scheduling-persistence`

**Descrição humana:** persistência da escala (com histórico de edições — quem alterou o quê e quando, para auditoria), config de validação por restaurante e adapter do StaffReadPort; migrations; testes integração + contrato.

```yaml
stage_id: 4.4-scheduling-persistence
bounded_context: scheduling
camada_alvo: adapters/out/postgres
arquivos_a_criar:
  - features/scheduling/adapters/out/postgres/ (repos, mappers, tables, audit log de edição)
  - features/scheduling/adapters/out/staff/local_staff_read_adapter.py
  - migrations/versions/0003_scheduling.py
  - tests integration + contract
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos: []
contratos_consumidos:
  - ports-out de 4.3
definition_of_done:
  - "integração + contrato verdes; toda mutação de escala gera entrada de auditoria"
non_goals: []
complexidade_estimada: M
gate_mode: strict
skills_hint: [repository-pattern, composition-root]
```

#### Stage 4.5 — `4.5-scheduling-http`

**Descrição humana:** endpoints do editor (demanda, alocações, avaliação ao vivo, publicar), calendário dia/semana/mês, escalas anteriores e "minha escala" (RBAC: funcionário só vê a própria); e2e do fluxo completo.

```yaml
stage_id: 4.5-scheduling-http
bounded_context: scheduling
camada_alvo: adapters/inbound/http
arquivos_a_criar:
  - features/scheduling/adapters/inbound/http/{router,schemas}.py
  - tests/e2e/features/scheduling/
arquivos_a_modificar:
  - composition_root.py, app factory
contratos_introduzidos: []
contratos_consumidos:
  - use cases de 4.3
definition_of_done:
  - "e2e: montar demanda→alocar→ver violações→aceitar warn→publicar→funcionário consulta a própria escala"
non_goals: []
complexidade_estimada: M
gate_mode: strict
skills_hint: [fastapi-thin-adapter]
```

#### Stage 4.6 — `4.6-schedule-notifications`

**Descrição humana:** fatia vertical: opção por restaurante "sempre notificar alterações na escala" → publicação dispara e-mail aos funcionários afetados com e-mail cadastrado (reuso do EmailSender de 2.5).

```yaml
stage_id: 4.6-schedule-notifications
bounded_context: scheduling
camada_alvo: vertical (scheduling)
arquivos_a_criar:
  - features/scheduling/application/use_cases/notify_schedule_published.py (ou handler no publish)
  - config flag + testes (fake EmailSender)
arquivos_a_modificar:
  - publish_schedule (hook de notificação), composition_root.py
contratos_introduzidos: []
contratos_consumidos:
  - EmailSender (2.5); ScheduleRepository (4.3)
definition_of_done:
  - "com flag ligada, publicar envia e-mails aos afetados; desligada, não envia (testes)"
non_goals:
  - WhatsApp/outros canais
complexidade_estimada: S
gate_mode: strict
skills_hint: [task-ordering-hex]
```

#### Stage 4.7 — `4.7-schedule-image`

**Descrição humana:** fatia vertical: geração sob demanda (botão) de imagem/tabela imprimível da escala publicada para divulgação manual (ex.: WhatsApp); formato e biblioteca de render decididos no concept (ADR).

```yaml
stage_id: 4.7-schedule-image
bounded_context: scheduling
camada_alvo: vertical (scheduling)
arquivos_a_criar:
  - features/scheduling/application/ports/out/schedule_renderer.py
  - features/scheduling/adapters/out/render/ (implementação escolhida no ADR 4.7)
  - endpoint GET de imagem + testes
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos:
  - ScheduleRenderer (port-out)
contratos_consumidos:
  - ScheduleRepository (4.3)
definition_of_done:
  - "endpoint devolve imagem/tabela legível da escala publicada do período"
non_goals:
  - envio automático da imagem
complexidade_estimada: M
gate_mode: strict
skills_hint: [hex-arch-python]
```

---

### Step 5 — Auto-preenchimento (BC `scheduling`)

- **Resultado de negócio:** com a demanda definida, um clique gera proposta de escala respeitando carga, preferências e indisponibilidades, priorizando fixos, transbordando para sob demanda e distribuindo turnos ruins com justiça (histórico); gerente revisa e aplica.
- **Depende de:** Step 4.
- **Tamanho estimado:** M

#### Stage 5.1 — `5.1-autofill-domain`

**Descrição humana:** algoritmo de auto-preenchimento como estratégia plugável de domínio: entrada = demanda + funcionários elegíveis + histórico; saída = proposta de alocações + vagas não preenchíveis; heurística inicial (gulosa com score de justiça) definida em ADR; determinística para testes.

```yaml
stage_id: 5.1-autofill-domain
bounded_context: scheduling
camada_alvo: domain
arquivos_a_criar:
  - features/scheduling/domain/services/autofill/{autofill_strategy_protocol,greedy_fairness_strategy,fairness_score}.py
  - tests unit com cenários (fixos primeiro, transbordo, rodízio de fins de semana)
arquivos_a_modificar: []
contratos_introduzidos:
  - AutofillStrategy (protocol), AutofillProposal (VO)
contratos_consumidos:
  - entidades 4.1, políticas 4.2 (proposta nasce sem violações block)
definition_of_done:
  - "cenários de referência produzem proposta válida, justa e determinística (testes unit)"
non_goals:
  - otimização por custo; solver exato (ADR registra evolução futura)
complexidade_estimada: M
gate_mode: strict
skills_hint: [ddd-tactical-patterns, hex-arch-python]
```

#### Stage 5.2 — `5.2-autofill-delivery`

**Descrição humana:** fatia vertical: use case de preview (gera proposta sem aplicar) e de aplicação (grava alocações como rascunho de edição), endpoint(s) e histórico usado como insumo de justiça; e2e do fluxo gerar→revisar→aplicar.

```yaml
stage_id: 5.2-autofill-delivery
bounded_context: scheduling
camada_alvo: vertical (scheduling)
arquivos_a_criar:
  - features/scheduling/application/use_cases/{preview_autofill,apply_autofill}.py
  - rota no router de scheduling + testes (fakes + e2e)
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos: []
contratos_consumidos:
  - AutofillStrategy (5.1), ScheduleRepository/StaffReadPort (4.3)
definition_of_done:
  - "e2e: preview mostra proposta e vagas descobertas; aplicar preenche a escala editável"
non_goals:
  - aplicar+publicar num passo só
complexidade_estimada: S
gate_mode: strict
skills_hint: [task-ordering-hex, fastapi-thin-adapter]
```

---

### Step 6 — Implantação piloto

- **Resultado de negócio:** o restaurante piloto usa o sistema no dia a dia, no ambiente de menor custo viável, com backup e o mínimo de operação documentada.
- **Depende de:** Step 4 (escala manual utilizável); Step 5 chega via CD depois.
- **Tamanho estimado:** M

#### Stage 6.1 — `6.1-hosting-study`

**Descrição humana:** estudo de custo/viabilidade nuvem (PaaS/VPS) × executável local na máquina do restaurante, considerando a tensão com o SaaS central futuro (Step 13), backup, atualização remota e Control iD; decisão registrada em ADR.

```yaml
stage_id: 6.1-hosting-study
bounded_context: shared
camada_alvo: bootstrap
arquivos_a_criar:
  - docs/adr/6_1_0001-hosting-decision.md
arquivos_a_modificar: []
contratos_introduzidos: []
contratos_consumidos: []
definition_of_done:
  - "ADR accepted com comparação de custo mensal e caminho de migração futuro"
non_goals:
  - implementar o deploy (6.2)
complexidade_estimada: S
gate_mode: strict
skills_hint: [git-versioning-pointer]
```

#### Stage 6.2 — `6.2-deploy-pipeline`

**Descrição humana:** CD conforme ADR 6.1: `develop` → ambiente development (auto), `main` → production (aprovação manual), com migrations no deploy e secrets geridos; conforme GIT-WORKFLOW.

```yaml
stage_id: 6.2-deploy-pipeline
bounded_context: shared
camada_alvo: bootstrap
arquivos_a_criar:
  - .github/workflows/cd.yml (ou ajuste do existente do boilerplate)
  - infra conforme ADR (compose de produção / config PaaS)
arquivos_a_modificar:
  - docs/GIT-WORKFLOW.md (environments reais)
contratos_introduzidos: []
contratos_consumidos: []
definition_of_done:
  - "merge em develop publica em development; promoção a main publica em production com aprovação"
non_goals:
  - autoscaling, CDN, observabilidade avançada
complexidade_estimada: M
gate_mode: strict
skills_hint: [git-versioning-pointer]
```

#### Stage 6.3 — `6.3-ops-baseline`

**Descrição humana:** baseline operacional: backup automático do Postgres + teste de restore, healthcheck/uptime básico e runbook de operação (subir, restaurar, atualizar).

```yaml
stage_id: 6.3-ops-baseline
bounded_context: shared
camada_alvo: shared/infrastructure
arquivos_a_criar:
  - scripts/backup/ + agendamento conforme hosting
  - docs/runbooks/operate-pilot.md
arquivos_a_modificar:
  - healthcheck endpoint se necessário
contratos_introduzidos: []
contratos_consumidos: []
definition_of_done:
  - "backup diário verificado com restore de teste documentado no runbook"
non_goals:
  - alerting avançado/APM
complexidade_estimada: S
gate_mode: strict
skills_hint: []
```

---

### Step 7 — Ponto Control iD (BC `timeclock`)

- **Resultado de negócio:** as marcações do Control iD entram sozinhas no sistema e o previsto × realizado fica visível por funcionário/dia, sem conferência manual.
- **Depende de:** Step 4 (escala publicada para conciliar); 7.1 pode rodar cedo (valida ASSUM-1).
- **Tamanho estimado:** M

#### Stage 7.1 — `7.1-controlid-spike`

**Descrição humana:** spike com a conta real do piloto: autenticação na API nuvem do Control iD (Control iD Cloud/RHiD), obtenção de marcações, limites/formatos; resultado vira ADR + rascunho do port `TimeRecordSource`. Valida ASSUM-1.

```yaml
stage_id: 7.1-controlid-spike
bounded_context: timeclock
camada_alvo: bootstrap
arquivos_a_criar:
  - docs/adr/7_1_0001-controlid-api.md
  - spike descartável (não mergeia código de produção)
arquivos_a_modificar: []
contratos_introduzidos: []
contratos_consumidos: []
definition_of_done:
  - "ADR accepted com endpoints/auth/rate limits reais e amostra de payload de marcações"
non_goals:
  - código de produção
complexidade_estimada: S
gate_mode: strict
skills_hint: []
```

#### Stage 7.2 — `7.2-timeclock-domain`

**Descrição humana:** modelar Marcação de ponto e a conciliação previsto × realizado (matching de alocações da escala com marcações, com tolerâncias configuráveis de atraso/antecipação); status por alocação (cumprido, atraso, falta, extra fora de escala).

```yaml
stage_id: 7.2-timeclock-domain
bounded_context: timeclock
camada_alvo: domain
arquivos_a_criar:
  - features/timeclock/domain/entities/time_record.py
  - features/timeclock/domain/services/reconciliation.py
  - features/timeclock/domain/value_objects/{tolerance_config,attendance_status}.py
  - tests unit
arquivos_a_modificar: []
contratos_introduzidos:
  - TimeRecord (entity), ReconciliationResult, ToleranceConfig (VOs)
contratos_consumidos:
  - dados de alocação da escala (por DTO, sem import de entidade de scheduling)
definition_of_done:
  - "conciliação classifica cumprido/atraso/falta/extra com tolerâncias configuráveis (testes unit)"
non_goals:
  - cálculo monetário de horas extras / banco de horas
complexidade_estimada: M
gate_mode: strict
skills_hint: [ddd-tactical-patterns]
```

#### Stage 7.3 — `7.3-controlid-adapter`

**Descrição humana:** adapter do port `TimeRecordSource` para a API real (conforme ADR 7.1), com sincronização agendada/manual, idempotência e persistência das marcações; contract test com fake + teste de integração gravado (respostas de exemplo).

```yaml
stage_id: 7.3-controlid-adapter
bounded_context: timeclock
camada_alvo: adapters/out/controlid
arquivos_a_criar:
  - features/timeclock/application/ports/out/{time_record_source,time_record_repository}.py
  - features/timeclock/adapters/out/controlid/client.py
  - features/timeclock/adapters/out/postgres/
  - migrations/versions/0004_timeclock.py
  - tests contract + integration
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos:
  - TimeRecordSource, TimeRecordRepository (ports-out)
contratos_consumidos:
  - TimeRecord de 7.2
definition_of_done:
  - "sync importa marcações reais/gravadas sem duplicar em re-execução (idempotente)"
non_goals:
  - webhooks/tempo real
complexidade_estimada: M
gate_mode: strict
skills_hint: [repository-pattern, pytest-with-fakes]
```

#### Stage 7.4 — `7.4-timeclock-delivery`

**Descrição humana:** fatia vertical: use cases de sincronizar e consultar previsto × realizado (por unidade/período/funcionário) + endpoints; e2e com fake source.

```yaml
stage_id: 7.4-timeclock-delivery
bounded_context: timeclock
camada_alvo: vertical (timeclock)
arquivos_a_criar:
  - features/timeclock/application/use_cases/{sync_time_records,get_reconciliation_report}.py
  - features/timeclock/adapters/inbound/http/router.py
  - tests (fakes + e2e)
arquivos_a_modificar:
  - composition_root.py, app factory
contratos_introduzidos: []
contratos_consumidos:
  - ports de 7.3; leitura de escala publicada (port de leitura de scheduling)
definition_of_done:
  - "e2e: sync + relatório previsto × realizado do período com status por alocação"
non_goals:
  - alertas em tempo real (fora do escopo v1 do overview)
complexidade_estimada: M
gate_mode: strict
skills_hint: [task-ordering-hex, fastapi-thin-adapter]
```

---

### Step 8 — Hub v1 (BC `hub`)

- **Resultado de negócio:** diretor abre o hub e vê, por unidade e na **Unidade Geral**, o calendário da escala e as métricas: cobertura da demanda, previsto × realizado, horas contratadas × escaladas × cumpridas e uso de extras.
- **Depende de:** Steps 5 e 7 (dados de escala + ponto).
- **Tamanho estimado:** M

#### Stage 8.1 — `8.1-hub-read-models`

**Descrição humana:** read models/queries agregadas do hub consumindo contratos de leitura de scheduling e timeclock (ROADMAP-6): cobertura, horas, extras, pontualidade; agregação multi-unidade (Unidade Geral).

```yaml
stage_id: 8.1-hub-read-models
bounded_context: hub
camada_alvo: application
arquivos_a_criar:
  - features/hub/application/queries/{schedule_coverage,attendance_summary,hours_summary,on_demand_usage,general_unit_aggregate}.py
  - features/hub/application/ports/out/{scheduling_read_port,timeclock_read_port}.py
  - adapters locais desses ports + tests com fakes
arquivos_a_modificar:
  - composition_root.py
contratos_introduzidos:
  - SchedulingReadPort, TimeclockReadPort (ports-out do hub)
contratos_consumidos:
  - dados publicados por scheduling (4.x) e timeclock (7.x)
definition_of_done:
  - "queries devolvem métricas corretas em cenários de referência, por unidade e agregado (testes com fakes)"
non_goals:
  - warehouse/ETL; métricas de módulos futuros
complexidade_estimada: M
gate_mode: strict
skills_hint: [pytest-with-fakes, hex-arch-python]
```

#### Stage 8.2 — `8.2-hub-http`

**Descrição humana:** endpoints dos painéis do hub (aba escala) com RBAC de diretor/dono (tudo do tenant) × gerente (só a própria unidade); e2e de visibilidade.

```yaml
stage_id: 8.2-hub-http
bounded_context: hub
camada_alvo: adapters/inbound/http
arquivos_a_criar:
  - features/hub/adapters/inbound/http/{router,schemas}.py
  - tests/e2e/features/hub/
arquivos_a_modificar:
  - composition_root.py, app factory
contratos_introduzidos: []
contratos_consumidos:
  - queries de 8.1
definition_of_done:
  - "e2e: dono vê métricas de todas as unidades + Unidade Geral; gerente só a própria unidade"
non_goals: []
complexidade_estimada: S
gate_mode: strict
skills_hint: [fastapi-thin-adapter]
```

---

### Steps 9–13 — Backlog de módulos (sem decomposição ainda)

| Step | Módulo | Por que ainda não decompõe |
|---|---|---|
| 9 | Estoque de insumos | Exige levantar fichas técnicas/receitas e formato das NFs do piloto |
| 10 | Integração Eyemobile | ASSUM-2 (API/export) precisa de spike próprio antes |
| 11 | Pedidos em mesa | UX e hardware (tablet/QR) a definir com o piloto |
| 12 | Delivery | Depende de decisões de logística do piloto |
| 13 | Auto-cadastro e cobrança | Gateway de pagamento e termos; só quando SaaS abrir a terceiros |

A decomposição em Stages acontece quando cada Step for planejado (nova rodada de Fase 2 sobre o Step, atualizando este documento).

---

## Lacunas conhecidas

- **Frontend:** este roadmap cobre o backend; o repo `restaurant-hub-frontend` terá roadmap próprio espelhando os Steps 1–8 (telas de login/equipe/editor de escala/calendário/hub). Overview §7. Um Step de produto só fecha com o front correspondente entregue.
- **Steps 9–13** sem Stages — informação insuficiente (tabela acima). Overview §3 (módulos subsequentes).
- **Heurística exata do auto-fill** (pesos de justiça, tratamento de empates) será fixada no concept/ADR da 5.1 — Overview §3 dá os requisitos, não o algoritmo.
- **Formato da imagem da escala** (PNG server-side × HTML imprimível) — ADR na 4.7.
- **Retenção/LGPD de dados de ponto** — revisar na 7.2 (dado sensível de jornada).

## Premissas adotadas no Roadmap

- **ROADMAP-1:** bounded contexts nomeados `identity`, `staff`, `scheduling`, `timeclock`, `hub` (código em inglês, CONVENTIONS §1). Justificativa: recorte por subdomínio do overview, um BC por módulo/preocupação.
- **ROADMAP-2:** este roadmap governa o repo backend; o frontend tem repo e roadmap próprios espelhando os Steps de produto. Justificativa: decisão do overview (dois repos, padrões do erp-intel-frontend); Stages não podem cruzar repositórios.
- **ROADMAP-3:** multi-tenancy por **row-level `tenant_id`** num único PostgreSQL na v1 (sem schema-per-tenant), mantendo aberta a porta de instância local por restaurante (Step 6/ADR 6.1). Justificativa: menor custo/complexidade para 1 piloto; isolamento reforçado em código + testes.
- **ROADMAP-4:** autenticação por JWT (access+refresh) e hash argon2/bcrypt; detalhes finos no concept da 2.4. Justificativa: padrão maduro para SPA + API.
- **ROADMAP-5:** e-mail via port `EmailSender` compartilhado com adapter free-tier (Resend/Brevo/SendGrid — ASSUM-3) e `ConsoleSender` em dev. Justificativa: overview exige convite/notificação com custo zero.
- **ROADMAP-6:** hub v1 lê por queries agregadas no mesmo Postgres (sem warehouse/eventos). Justificativa: volume do piloto (ASSUM-5) não justifica infra analítica dedicada; port de leitura preserva evolução.
- **ROADMAP-7:** ordem dos Steps 6/7 pode inverter conforme urgência do piloto (deploy antes de ponto ou vice-versa); `depends_on` é a fonte da ordem real.

## Histórico de mudanças do roadmap

| Data | Mudança | Motivo |
|---|---|---|
| 2026-07-10 | Criação inicial (Steps 1–8 decompostos, 9–13 backlog) | Fase 2 do RUNBOOK-INIT-PROJECT |
| 2026-07-12 | Criação da Tabela de Issues (avulsas) | Referenciada por `PROMPT-issue-single-session.md` e pelo PR template, mas inexistente — issue #2 |
| 2026-07-14 | Stage 1.1-bootstrap concluída (`done`); bloco corrigido para o escopo real; Step 1 → `in_progress` | Execução da Stage 1.1 — issue #1 |
| 2026-07-17 | Stage 1.2-ci concluída (`done`); bloco corrigido (nota datada — arquivos reais + ADR); Step 1 → `done` (fundação fechada) | Execução da Stage 1.2 — issue #9 |
| 2026-07-18 | Stage 2.1-identity-domain concluída (`done`); bloco corrigido (nota datada — file-scope e contratos reais); Step 2 → `in_progress` (primeiro código de domínio do projeto) | Execução da Stage 2.1 — issue #17 |
| 2026-07-19 | Stage 2.2-identity-application concluída (`done`); bloco corrigido (nota datada — 6º port `SessionRepository`, file-scope real e consequências para 2.3/2.4) | Execução da Stage 2.2 — issue #20 |
| 2026-07-19 | Stage 2.3-identity-persistence concluída (`done`); bloco corrigido (nota datada — tabela `sessions` e `session_repository` reconciliados do ADR 2.2.0001, `integrity_errors.py`, CI exigindo Postgres real, 5 ADRs) | Execução da Stage 2.3 — issue #22 |
| 2026-07-20 | Stage 2.4-identity-http concluída (`done`); bloco corrigido (nota datada — `decode_access_token` estendendo `TokenIssuer`, use cases de rotação/logout, contract test de segurança, argon2 sem bcrypt, 4 ADRs); primeira superfície de runtime do projeto | Execução da Stage 2.4 — issue #24 |
| 2026-07-20 | Stage 2.5-email-invite concluída (`done`); bloco corrigido (nota datada — 5 divergências: persistência no escopo, 3 use cases, sem adapter real, sem `TokenIssuer`, port em `ports/out/`; 4 ADRs). **Todas as Stages de backend do Step 2 estão `done`; o Step permanece `in_progress`** — falta a contraparte de frontend (regra do §Escopo deste roadmap e §Lacunas conhecidas) | Execução da Stage 2.5 — issue #27 |
| 2026-07-29 | Stage 3.1-staff-domain concluída (`done`); bloco corrigido (nota datada — `.importlinter` modificado com contratos de pureza `staff.domain` e independência identity × staff, `identifiers.py`, placeholders application/adapters, `DayPeriod` co-locado, hierarquia `StaffError` + 8 subclasses; ADRs 3.1.0001–0006); Step 3 → `in_progress` (primeiro código do BC staff) | Execução da Stage 3.1 — issue #32 |
| 2026-08-09 | Stage 3.2-staff-application concluída (`done`); bloco corrigido (nota datada — **quatro** eixos: camada-alvo expandida para o domínio da 3.1, file-scope real, DTOs/erros/use cases/fakes nos contratos introduzidos, `IdGenerator` e `DomainError`/`NotFoundError` nos consumidos). Decisões do sponsor mudaram o ciclo de vida das duas entidades da 3.1 (ADR 3.2.0005 supersede o 3.1.0003; ADR 3.2.0006), e o **ADR 3.2.0007** nasceu na execução, quando a auditoria de testes provou que a interação entre editar e desligar nunca fora especificada | Execução da Stage 3.2 — issue #35 |
| 2026-08-11 | Stage 3.3-staff-persistence concluída (`done`); bloco corrigido (nota datada — **cinco** eixos: migration `0003` e não `0002`, file-scope real incluindo `migrations/env.py`/`tests/conftest.py`/fakes/ports e a **promoção** das suítes de lei para `tests/contract/`, `L-ORD` nos contratos introduzidos, `complexidade_estimada` `S`→`M`, oito `non_goals`). ADRs 3.3.0001–3.3.0007. A auditoria de testes independente encontrou **5 mutações sobreviventes em arquivos com 100% de cobertura de linha e branch** — entre elas o escopo por `employee_id` dos `DELETE` de filha, cuja ausência destruiria dado **cross-tenant** em silêncio; todas fechadas por teste com prova de mutação | Execução da Stage 3.3 — issue #38 |
| 2026-08-12 | Stage 3.4 **cortada em duas** na Fase 3A (issue #40): `3.4-staff-access-scope` (fundação de acesso e escopo, 6 Tasks, sem rota) e **`3.6-staff-http`** (a borda HTTP, 8 Tasks). Motivo: com as três decisões do sponsor sobre os forks F1/F2/F3 e os achados do Checkpoint A, o plano mediu **14 Tasks** — o alarme de CONVENTIONS §6 —, e **7 delas não estavam no bloco original**. A fronteira separa emendar Stage fechada de escrever superfície nova, e faz os dois buracos de acesso fecharem antes de existir rota que os exponha. `3.5` passou a depender de `3.6`; a numeração fora de ordem é legal (número é identidade, ordem é `depends_on`). 8 ADRs (3.4.0001–3.4.0008), cinco governando a 3.4 e três a 3.6. Expansão de camada-alvo para `features/identity` autorizada pelo sponsor | Fase 3A da Stage 3.4 — issue #40 |
| 2026-08-18 | Stage 3.4-staff-access-scope concluída (`done`); bloco **confirmado sem correção estrutural** (primeira do Step 3) e acrescido de nota datada de reconciliação pós-execução: file-scope real de 22 arquivos de `src/`, as fixtures de fechamento do CA20 são **três** e não duas (sem regressão do concept — o DoD fala da categoria; decisão e medições na §7), errata no ADR 3.4.0001 e quatro `[finding]` novos. A Stage fecha o **furo de acesso intra-tenant**: a unidade entrou no endereço do funcionário até a assinatura do port (ADR 3.4.0007), provado nos dois parâmetros da suíte de contrato com um corpo de teste só. A auditoria de testes independente encontrou **2 mutações sobreviventes** em arquivos com 100% de cobertura — as duas da mesma família, lei universal travada num representante estreito —, ambas fechadas com prova de mutação. Nenhuma rota e nenhuma migration | Execução da Stage 3.4 — issue #40 |
| 2026-08-30 | Stage 3.6-staff-http concluída (`done`); bloco **confirmado sem correção estrutural** (as três desatualizações já tinham sido medidas na §1 do concept, antes da execução) e acrescido de nota datada de reconciliação pós-execução: as **16 rotas** de staff sob `/api/v1` ao lado das **10 de identity** (26 operações no OpenAPI), file-scope real de 10 arquivos de `src/` mais `LAYOUT.md` e `overview.md` §10, e nenhuma migration. **Cinco ADRs** — 3.6.0001–3.6.0004 e o **global 0.0.0005** (`bounded_context: transversal`), nascido aqui: o tenant que decide acesso vem do token, sem o qual **nenhuma das 16 rotas era alcançável por nenhum papel**. **Terceira expansão de camada para trás no BC staff** (3.6 → `application` da 3.2, ADR 3.6.0004, com errata na §5.16 do concept da 3.2), registrada como `[finding]` para a retrospectiva do Step 3. A auditoria independente aplicou **~25 mutações** e **3 sobreviveram**, todas em linhas com 100% de cobertura de linha e ramo — autenticar-antes-de-validar travada em 1 rota de 9, `EmptyShiftPreferenceError` sem caminho HTTP e a reincidência de `L-AG3` no tenant vazio do argumento —, as três fechadas por lei quantificada sobre domínio derivado, com prova de mutação. O Step 3 segue `in_progress` (falta a 3.5 e o frontend) | Execução da Stage 3.6 — issue #43 |
| 2026-09-27 | Stage 4.1-scheduling-domain concluída (`done`); bloco acrescido de nota datada de reconciliação pós-execução (nove divergências declaradas no concept §1: file-scope com `.importlinter` e duas varreduras de repositório, quatro entidades com `ShiftBand`, sem evento de publicação, contratos, ADRs 4.1.0007–0012, decisões Q1–Q5 do sponsor, findings para a 4.3); Step 4 → `in_progress` (primeiro código do BC `scheduling`) | Execução da Stage 4.1 — issue #55 |
| 2026-10-19 | Stage 4.2-validation-policies concluída (`done`); bloco **não** recebe nota interna (deslocaria as citações por linha do doc de domínio e dos ADRs 4.1.x): as sete divergências estão no concept §1 — nove políticas (não quatro), file-scope com `errors.py`, dois testes de totalidade e `LAYOUT.md` (`services/` sai de `[planejado]`), `EmployeeFacts` por dados, quatro invariantes do doc que não resistem a mudança de staff (pergunta P para a 4.3), `enabled` em toda política configurável, período de 7 dias exigido no insumo. ADRs 4.2.0001 (função não detida segue o cadastro atual — decisão do sponsor) e 4.2.0002 (insumo do avaliador e identidade da violação); findings para 4.3, 4.5 e 8.1 na §7 do technical | Execução da Stage 4.2 — issue #64 |
| 2026-10-19 | Issue #46 promovida à Stage `2.6-identity-unit-of-work` (Step 2); linha sai da Tabela de Issues | O corpo da issue virou mini-concept (port + ADR, PIPELINE §4.5); Step 2 porque o BC é identity e quatro das cinco dívidas nasceram ali |
| 2026-10-19 | Stage 2.6-identity-unit-of-work concluída (`done`); bloco acrescido de nota datada (revoke → bool, 13 Tasks, renumeração); issues #67 e #68 na Tabela de Issues | Execução da Stage 2.6 — issue #46 |
| 2026-10-19 | Issue **#49** promovida a **Stage `3.7-application-authorization`** (Step 3, BC staff; `depends_on: 3.5-employee-login-link`): a linha sai da Tabela de Issues e entra na de Stages, com bloco próprio. O corpo da issue já se declarava candidato a Stage — exige ADR (forma do guard na application e destino do `AuthorizedScope`), toca os 17 use cases e pede uma propriedade sobre a camada inteira — o litmus de PIPELINE §4.5. Step 3 passa a `3.1 → 3.7` | Promoção da issue #49 |
| 2026-10-19 | Stage 3.7-application-authorization concluída (`done`); bloco acrescido de nota datada de reconciliação pós-execução. Os 17 use cases de staff autorizam o alvo do próprio command pelo `AccessGuard` injetado antes de qualquer outra instrução; a borda HTTP segue autorizando (defesa em profundidade) e nenhuma faixa muda (`tests/e2e/` intocado). ADR 3.7.0001; supersessão parcial datada em 3.2.0002, 3.4.0001 e 3.6.0004; errata no concept 3.2 §5.16. 13 mutações reais na auditoria independente, todas mortas | Execução da Stage 3.7 — issue #49 |
| 2026-11-01 | Issue **#60** promovida a **Stage `3.8-termination-access-scope`** (Step 3, BC staff; `depends_on: 3.5-employee-login-link`) e concluída (`done`): a linha sai da Tabela de Issues e entra na de Stages, com bloco próprio e nota datada de fechamento. Executada como `3.7` em paralelo à #49; **renumerada para 3.8** no rebase sobre o #71, que ficou com o número (pasta, ADR 3.8.0001, workforce §3.8, nota no ADR 3.5.0003). A aresta do grafo vai na mesma linha da 3.7; as citações por linha deslocadas pelo bloco (+48 a partir do Step 4, +1 na tabela de Stages) acompanham — as do #70 seguem com a #79. Step 3 passa a `3.1 → 3.8` | Execução da Stage 3.8 — issue #60 |
| 2026-11-02 | Issue **#48** promovida a **Stage `3.9-error-hierarchy`** (Step 3, BC shared; `depends_on: 3.6-staff-http, 4.3-scheduling-application`, #45): a linha sai da Tabela de Issues e entra na de Stages, com bloco próprio. Supersede o ADR 2.2.0003 e pede uma propriedade sobre a hierarquia inteira dos três BCs (detector de protocolo) — o litmus de PIPELINE §4.5. Step 3 passa a `3.1 → 3.9` | Promoção da issue #48 |
| 2026-11-02 | Stage 3.9-error-hierarchy concluída (`done`); bloco acrescido de nota datada de fechamento. Uma raiz por significado (`DomainError` × `ApplicationError`, de volta em `shared/application`), status só pelo mapa do adapter, `NotFoundError` removida, regra 11 do `check_layout.py`. ADR 3.9.0001 supera o 2.2.0003, com supersessão parcial datada em 2.3.0003, 2.4.0001 e 3.4.0002; `LAYOUT.md` §2–§4 emendado. Nenhuma faixa nem corpo muda (`tests/e2e/` só perde a sonda 404 do smoke) | Execução da Stage 3.9 — issue #48 |
| 2026-11-02 | Issue #30 concluída (`done`): `docs/domain/identity/tenancy-and-access.md` `accepted` — backfill do gate de domínio do Step 2, consolidando os ADRs de identity sem regra nova (lacunas e achados declarados no doc). **O Step 2 permanece `in_progress`**: o gate de domínio deixa de ser pendência, mas falta a contraparte de frontend (§Escopo deste roadmap; §"Lacunas conhecidas" › "Frontend") e o relatório do Step | Execução da issue #30 |

## Próxima revisão de roadmap

- **Quando:** ao fechar a Stage atualmente em `in_progress`, ou no máximo a cada 30 dias.
- **O que revisar:** Steps/Stages em `draft` ainda fazem sentido? Surgiu nova Stage? Alguma dependência mudou? Step 6/7 devem inverter? Algum Step do backlog 9–13 já pode ser decomposto?

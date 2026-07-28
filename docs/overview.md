---
title: Visão Geral — restaurant-hub
description: Business briefing da plataforma SaaS modular de gestão de restaurantes (escala, estoque, pedidos, delivery + hub de análise)
when-use: Consultar no início de qualquer nova sessão de detalhamento ou planejamento; serve como contexto base do projeto inteiro
keywords: [overview, briefing, restaurantes, escala, saas, hub, multi-tenant]
status: done
created_at: 2026-07-10
updated_at: 2026-07-23
project_name: restaurant-hub
stakeholders:
  - Sponsor / Desenvolvedor / Admin da plataforma: Marcelo (Whaka)
  - Dono do restaurante piloto: a definir (feedback de produto)
---

# Visão Geral — restaurant-hub

> Documento vivo, mas mudanças estruturais (escopo, objetivos) exigem revisão consciente. Atualizações tópicas (stakeholders, contexto) podem ser feitas inline.

## 1. Resumo executivo

**restaurant-hub** (nome de trabalho; sigla/marca definitiva será escolhida depois) é um SaaS web modular de gestão de restaurantes. Cada setor da operação vira um módulo entregue incrementalmente — começando pela escala de funcionários, seguido de estoque de insumos, pedidos em mesa e delivery — e todos alimentam um **hub** de dashboards onde diretores analisam dados para insight e tomada de decisão. Nasce operando um restaurante piloto, mas é modelada desde o primeiro dia para múltiplos restaurantes (tenants), cada um com múltiplas unidades.

## 2. Contexto de negócio

### Problema
A escala é feita em planilha e papel: o gerente precisa lembrar manualmente das últimas escalas, realocar pessoas em urgências e acionar extras (ou o próprio dono/chef) para cobrir picos e buracos. O estoque não avisa quando um insumo está acabando. Os diretores decidem sem dados consolidados da operação.

### Oportunidade
Centralizar a operação em módulos integrados: escala montada automaticamente e com justiça distributiva, previsto × realizado do ponto sem conferência manual, estoque com alerta de reposição, e um hub que transforma dados operacionais em insight de direção. Como SaaS, o mesmo produto pode ser vendido a outros restaurantes no futuro.

### Estado atual
Escala em planilha/papel. O piloto já opera com **Control ID** (ponto por reconhecimento facial; acesso presumido via nuvem) e PDV **Getnet Eyemobile** — as integrações serão contra sistemas reais em produção, não hipotéticos.

## 3. Escopo

### Dentro do escopo — primeira entrega (fundação + módulo escala)
- Fundação SaaS multi-tenant: restaurante (tenant) → unidades → funcionários por unidade. Unidades não compartilham funcionários (não se enxergam), mas o cadastro pode ser **copiado** para outra unidade.
- RBAC: papéis dono, gerente, RH e funcionário + **admin de plataforma** (gerencia acessos/tenants); permissões definem quem faz o quê; trilha de auditoria das alterações.
- Funcionário cadastrado pelo gerente; **login opcional** ("criar login para este funcionário") via convite por e-mail ou senha provisória entregue em mãos; perfil de jornada **fixa** (carga horária determinada) ou **sob demanda** (extra/gerente/dono), com preferência de turno; períodos de **indisponibilidade** na página do funcionário (cobre férias/atestados na v1).
- Escala com período configurável (default **semanal**): por dia, habilitam-se faixas de horário livres e define-se a **demanda por função × faixa** (ex.: qua = 1 cozinheiro 16h–00h + 1 assistente 18h–23h + 2 atendentes 16h–00h). Funções são criadas e parametrizadas pelo gerente — nada é pré-determinado.
- **Auto-preenchimento**: respeita carga, preferência de turno e indisponibilidade; prioriza jornada fixa e usa sob demanda como transbordo quando os fixos estouram; busca **justiça distributiva** com base no histórico (rodízio de fins de semana/turnos ruins). Sem otimização de custo na v1.
- **Validações parametrizáveis por restaurante** (modo bloquear ou avisar): sobreposição de alocação, descanso entre jornadas, tetos de horas etc. Avisos ao vivo durante a edição; o editor corrige ou aceita conscientemente.
- Publicação: **salvar = publicar**; e-mail opcional a cada atualização (opção "sempre notificar alterações na escala"); **imagem/tabela gerada sob demanda** (botão gerar/imprimir) para divulgação manual; funcionário com login consulta a própria escala.
- Integração **Control ID (nuvem)**: importar marcações e exibir **previsto × realizado**; sem alertas na v1 — apenas relatório no hub.
- **Hub (aba escala)**: visão principal é o **calendário** dia/semana/mês com mini-cards de funcionários sobre as faixas de funcionamento; em seguida, métricas de cobertura da demanda, previsto × realizado, horas contratadas × escaladas × cumpridas e uso de extras. Visão por unidade + **"Unidade Geral"** (agregado/comparativo entre unidades do mesmo restaurante).
- Fácil visualização das escalas anteriores ao montar a nova.

### Dentro do escopo — módulos subsequentes (Steps futuros; ordem indicativa, pode mudar ou paralelizar)
1. **Controle de estoque de insumos**: entrada por nota fiscal; baixa por fechamento de caixa × receita/ficha técnica dos produtos; alertas de reposição.
2. **Integração PDV Getnet Eyemobile**: dados de fechamento de caixa (diário/mensal).
3. **Pedidos em mesa**: tablet na mesa ou QR code abrindo página web no celular do cliente.
4. **Delivery**: gestão de entregadores e rotas de entrega.
5. **Auto-cadastro de restaurantes** com cobrança/assinatura e onboarding guiado.

### Fora do escopo (explicitamente) — v1
- Folha de pagamento / valorização monetária de horas extras; banco de horas formal.
- Solicitação de troca de turno pelo funcionário (gerente com permissão edita direto).
- App nativo (web responsivo atende funcionário no celular).
- Auto-cadastro e cobrança (Step futuro).
- Tutorial/onboarding guiado (futuro).
- Alertas de ponto em tempo real (v1 = só relatório).
- Otimização de custo no auto-preenchimento.
- i18n (PT-BR na v1; tradução vira etapa futura se necessário).

### Premissas
- **ASSUM-1**: o Control ID do piloto é acessível por API na nuvem (Control iD Cloud / RHiD) no plano contratado. Validar antes da stage de integração.
- **ASSUM-2**: o Eyemobile expõe API/exportação dos dados de fechamento de caixa. Validar antes do módulo de estoque.
- **ASSUM-3**: free tier de e-mail transacional (Resend 3k/mês, Brevo 300/dia ou SendGrid 100/dia) cobre o volume de notificações do piloto.
- **ASSUM-4**: o piloto opera 1 unidade hoje (multi-unidade modelado desde já, exercitado quando existir a 2ª).
- **ASSUM-5**: quadro do piloto em porte pequeno/médio (dezenas de funcionários, não centenas).

## 4. Objetivos

### Objetivos gerais
- Substituir planilha/papel na gestão de escala do restaurante piloto.
- Dar aos diretores visão de dados por setor (hub) para decisão inteligente.
- Construir plataforma modular e escalável que absorva novos módulos, novos restaurantes e particularidades por configuração/estratégias plugáveis — sem retrabalho estrutural e sem overengineering descalibrado.

### Critérios de sucesso
- **Feedback dos usuários do piloto** é a fonte primária de avaliação (decisão do sponsor).
- Escala da semana montada no sistema em minutos (auto-preenchimento + ajustes); planilha/papel abandonados após algumas semanas de adoção.
- Divergências previsto × realizado visíveis no hub sem conferência manual.
- Diretores consultando o hub semanalmente.

## 5. Stakeholders

| Papel | Nome / Área | Interesse principal |
|---|---|---|
| Sponsor / Desenvolvedor / Admin da plataforma | Marcelo (Whaka) | Plataforma modular, escalável e vendável a múltiplos restaurantes |
| Dono do restaurante piloto | a definir | Escala sem esforço manual; visão da operação; dá feedback de produto |
| Gerente / RH (usuários primários) | restaurante piloto | Montar/ajustar escala rápido, com validações, histórico e auditoria |
| Funcionários | restaurante piloto | Consultar a própria escala (login ou imagem divulgada) |

## 6. Restrições

### Técnicas
- **Backend**: Python 3.12, FastAPI 0.111+, PostgreSQL 15+, SQLAlchemy 2 (Core), Alembic, Pydantic v2, uv, Docker — arquitetura hexagonal + vertical slices (boilerplate do `whaka-dev-project-template`).
- **Frontend**: repositório separado seguindo os padrões do `erp-intel-frontend` — React 19, TypeScript 5.9, Vite 8, Tailwind CSS 4, TanStack Query 5, React Router 7, Radix UI, Recharts, Vitest; tipos gerados do OpenAPI do backend (`openapi-typescript`, contract-first).
- **Dois repositórios** (back e front), cada um com o pipeline de docs do padrão Whaka. Git somente nos repos do sistema — o template permanece sem git (decisão do sponsor; gates de doc na Fase 1–2 são flip de status sem commit, e o histórico começa no bootstrap).
- **Hospedagem: indefinida** — estudo de custo comparará nuvem × executável instalado na máquina do restaurante. Docker desde o dia 1 mantém as duas portas abertas.
- Fuso horário configurável por unidade.

### Negócio
- Desenvolvimento **solo** (Marcelo); dono do piloto participa com feedback.
- **Qualidade > prazo**: sem deadline; cada feature nasce com a mínima abordagem que a torna viável, sem restringir evolução futura para ferramenta mais robusta.
- Custo de infraestrutura minimizado (motivação do estudo de hospedagem).

### Regulatórias / compliance
- **LGPD** básica (dados pessoais de funcionários: jornada, ponto, e-mail); aprofundar apenas se alguma feature exigir legalmente.
- Regras trabalhistas (CLT) **não são hard-coded**: entram como validações configuráveis por restaurante (ex.: descanso entre jornadas; antecedência de convocação de intermitente, se o restaurante adotar esse contrato).

## 7. Abordagem geral

Monolito modular Python em arquitetura hexagonal com vertical slices por bounded context (um módulo de negócio por entrega), com frontend SPA em repositório separado consumindo a API via contrato OpenAPI. Particularidades de cada restaurante são absorvidas por **configuração** e por **estratégias plugáveis** (políticas intercambiáveis por tenant) — nunca por hard-code. O hub é consumidor dos dados que cada módulo produz: cada novo módulo nasce com sua aba/painéis. Entrega incremental: fundação + módulo escala primeiro (valor imediato ao piloto); módulos seguintes em Steps próprios do roadmap. A decisão de hospedagem fica para um estudo de custo dedicado (nuvem × instalação local), com a tensão registrada entre instalação local por restaurante e o futuro auto-cadastro SaaS central.

## 8. Riscos conhecidos

| Risco | Impacto | Mitigação inicial |
|---|---|---|
| API do Control iD (nuvem) com acesso/documentação aquém do esperado no plano contratado | alto | Validar ASSUM-1 com spike antes da stage de integração; port de ponto independente de fornecedor |
| Tensão hospedagem nuvem × instalação local adiada | médio | Docker + 12-factor desde o início; estudo de custo como stage própria antes do deploy do piloto |
| Escopo dos módulos futuros crescer antes de a escala fechar | médio | Pipeline de Steps/Stages com gates; um módulo por entrega |
| Dependência de desenvolvedor único | médio | Pipeline de docs/ADRs/gates preserva contexto e permite retomada em qualquer sessão |

## 9. Glossário

Termos escolhidos por pesquisa de mercado (jul/2026) priorizando o vocabulário real do food service brasileiro:

- **Escala**: quadro de quem trabalha em quais dias/turnos (período configurável; default semanal).
- **Turno**: faixa de horário demandada/trabalhada num dia (ex.: 16h–00h).
- **Setor**: área da operação (cozinha, salão, bar, caixa...). Preferido a "praça", jargão interno de brigada.
- **Função**: papel de trabalho customizável por restaurante (cozinheiro, atendente...); a demanda da escala é definida por função.
- **Demanda / Vaga**: necessidade de N pessoas de uma função num turno de um dia.
- **Jornada fixa / sob demanda**: perfis de carga do funcionário — carga horária determinada vs. atuação quando acionado (extra, gerente, dono). "Intermitente" designa apenas o contrato CLT específico.
- **Extra**: pessoa sob demanda acionada para cobrir turno/reforçar a equipe (freelancer de diária — termo consagrado no setor).
- **Publicar**: salvar a escala tornando-a visível (dispara notificações, se habilitadas).
- **Previsto × Realizado**: comparação da escala planejada com as marcações do Control ID.
- **Hub**: área de dashboards por setor para diretores.
- **Unidade Geral**: visão agregada/comparativa entre as unidades de um restaurante.
- **Tenant**: um restaurante cliente da plataforma, isolado dos demais.

## 10. Referências

- Pipeline/template: `whaka-dev-project-template` — `RUNBOOK-INIT-PROJECT.md` (Fases 1–2 conduzidas em sessão Claude Code, 2026-07-09/10).
- Padrões do frontend: `C:\Users\Marcelo\Documents\Code\erp-intel-frontend` (docs/ + stack de referência).
- Control iD (ponto na nuvem — Control iD Cloud / RHiD): https://www.controlid.com.br/
- Getnet Eyemobile: PDV em operação no piloto (documentação de API a levantar — ASSUM-2).
- Pesquisa de terminologia: [Factorial HR](https://factorialhr.com.br/blog/escala-restaurante/), [Shifton](https://shifton.com/features/shift-schedule/), [Goomer](https://goomer.com.br/blog/contratar-garcom-freelancer), [EPOC](https://epoc.com.br/blog/garcom-freelancer/), [GastronoMundo](https://www.gastronomundo.com/brigada-de-cozinha/), [Saipos](https://saipos.com/sistema/restaurante/brigada-de-cozinha), [tio.digital](https://blog.tio.digital/contrato-intermitente-para-bares-e-restaurantes/), [Fecomercio](https://www.fecomercio.com.br/noticia/atente-se-as-regras-de-remuneracao-e-convocacao-do-trabalhador-intermitente).
- Legislação trabalhista (fonte primária — fronteira terminológica sob demanda × intermitente; consumida por `docs/domain/staff/workforce.md`; verificada no Planalto em 2026-07-23):
  - BRASIL. **Decreto-Lei nº 5.452, de 1º de maio de 1943** (Consolidação das Leis do Trabalho), arts. 443, *caput* e § 3º, e 452-A, com redação dada pela **Lei nº 13.467, de 13 de julho de 2017** (Reforma Trabalhista). Texto consolidado. Brasília: Presidência da República. Disponível em: https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452.htm. Acesso em: 23 jul. 2026.
  - BRASIL. **Lei nº 13.467, de 13 de julho de 2017**. Altera a Consolidação das Leis do Trabalho (CLT). Disponível em: https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13467.htm. Acesso em: 23 jul. 2026.
  - (Nota: a MP nº 808/2017, que alterava temporariamente o art. 452-A e criava os arts. 452-B a 452-H, teve vigência encerrada em 23/04/2018 — Ato Declaratório CN nº 22/2018 — e não integra o direito vigente.)

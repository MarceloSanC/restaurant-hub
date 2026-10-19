---
title: Concept — Fronteira transacional nos use cases de identity que escrevem mais de uma vez
description: Unidade de trabalho de identity (port, adapter Postgres, fake), os cinco use cases que passam a escrever atomicamente, o que fica de fora (staff, travessia entre BCs) e o gate que impede a regressão
when-use: Consultar ao iniciar a Fase 3B desta Stage; revisar antes de acrescentar uma escrita a um use case de identity ou de tornar transacional uma travessia entre BCs
keywords: [concept, unit-of-work, transacao, atomicidade, identity, savepoint, contextvar, gate, check-layout]
status: done
created_at: 2026-10-19
updated_at: 2026-10-19
stage_id: 2.6-identity-unit-of-work
stage_title: Fronteira transacional nos use cases que escrevem mais de uma vez
step_id: 2
step_title: Restaurante e acesso
depends_on: [3.5-employee-login-link]
---

# Concept — Stage 2.6 — Fronteira transacional nos use cases de identity que escrevem mais de uma vez

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Origem:** issue #46, promovida a Stage em 2026-10-19 (PIPELINE §4.5: o corpo
> pedia port novo e um trade-off com ADR).

## 1. Escopo

### Dentro do escopo
- Port `UnitOfWork` de identity, seu adapter Postgres e seu fake, com uma suíte de
  contrato única para os dois (ADR 2.6.0001).
- Os repositórios Postgres de identity passam a usar a conexão da unidade ativa
  quando há uma — sem mudar construtor nem port.
- Os cinco use cases de identity que escrevem mais de uma vez por requisição
  passam a escrever dentro de uma unidade: `set_password_with_token`,
  `invite_user`, `provision_account`, `request_password_reset` e a rotação de
  `refresh_session` (ADR 2.6.0002 §1).
- `SessionRepository.revoke` passa a devolver `bool` (`True` só se esta chamada
  revogou), como `consume` já faz; a rotação trata `False` como **reuso** — fecha a
  janela em que um refresh concorrente passaria sem alarme (ADR 2.6.0002 §1b).
- Teste de integração por use case: falha na N-ésima escrita ⇒ banco inalterado,
  para todo N; e as corridas de duas redenções do mesmo token e de duas rotações do
  mesmo refresh, com intercalação forçada.
- O ponteiro órfão do docstring de `set_password_with_token` ("aponta para a
  4.4") passa a citar esta Stage e a #46; os docstrings e comentários que dizem que
  o UoW não existe ou que ele é futuro (`refresh_session`, módulos e núcleos
  "ponto de troca para um futuro UoW" dos repositórios) passam a descrever o que
  existe.
- Regra 10 do `scripts/check_layout.py`: use case com mais de uma escrita fora de
  unidade reprova, salvo allowlist contável (ADR 2.6.0002 §5).
- `LAYOUT.md` ganha a regra da fronteira transacional.

### Fora do escopo (explicitamente)
- **Staff.** Nenhum use case de staff escreve duas vezes dentro de staff; os
  repositórios de staff, o `REPEATABLE READ` das leituras e o ADR 3.3.0006 ficam
  como estão (ADR 2.6.0002 §2).
- **Transação atravessando bounded contexts** — `create_login_for_employee` e
  `deactivate_employee` mantêm a ordem e as janelas declaradas na 3.5 (ADR 4.1.0006
  Alt. A; ADR 2.6.0002 Alt. A).
- **Check-then-act com uma escrita** (`delete_job_function`, `create_unit`,
  `create_user`, …) — a unidade em `READ COMMITTED` não fecha a corrida; o schema
  fecha (ADR 2.6.0002 §4).
- Locking otimista / versão de agregado (ADR 3.3.0006); mudar a ordem fail-closed
  de `set_password_with_token`; ports assíncronos (ADR 2.2.0004) — não-objetivos da
  #46.
- Outbox / envio assíncrono de e-mail (ADR 2.6.0002 Alt. C).
- **Provisionamento composto restaurante + dono** (ADR 2.4.0003 Alt. B). O ADR
  2.4.0003 manda "revisitar quando existir um port de transação" — esta Stage cria
  o port, então o gatilho dispara; mas compor as duas rotas é mudança de contrato
  HTTP e de fluxo do admin, não de atomicidade de algo que já existe.
  `[finding]` registrado, com issue nova (§10 do technical).
- **As janelas da 3.5 que não são de transação** — ver a disposição de cada uma em
  §3 ("Janelas herdadas da 3.5").

### Vínculo com o roadmap
Stage `2.6-identity-unit-of-work` do Step 2 (identity), dependendo da 3.5 — é a
dívida transacional que as Stages 2.4 (rotação de sessão), 2.5 (redefinição,
convite) e 3.5 (órfão dentro de identity) escalaram e que o docstring de
`set_password_with_token` apontava para a 4.4, cujo escopo (persistência da
escala) não a comporta. Mora no Step 2 porque o BC é identity e quatro das cinco
dívidas nasceram ali (PIPELINE §4.5, "Step certo"); depende da 3.5 porque
`provision_account` e a fachada vêm dela.

### Divergências declaradas em relação ao roadmap e ao PIPELINE
1. **Camada-alvo mista** (PIPELINE §4.2 #1): application (use cases e port) +
   adapters/out/postgres (adapter e repositórios) + tooling (regra 10). Não é
   fatia vertical de feature nova; é uma propriedade transversal (atomicidade)
   que só existe com as três peças — separar a regra 10 numa Stage própria
   deixaria a propriedade sem gate entre as duas.
2. **Dois resultados** (PIPELINE §4.2 #2): atomicidade **e** gate. O gate é o que
   impede a atomicidade de regredir; não tem valor sozinho.
3. **Toca artefatos de staff** sem mudar código de produção de staff: a fixture
   `_gateway_real` do contrato de staff (que constrói `ProvisionAccountUseCase`) e
   a allowlist da regra 10, que nomeia os dois use cases de travessia.
4. **Número.** A #46 foi promovida primeiro como 3.7; em 2026-10-19 duas outras
   Stages paralelas (#49, #60) tomaram o mesmo número. Esta foi renumerada para
   2.6 antes de qualquer commit de gate (Step correto, número livre).

## 2. Objetivo da Stage

Nenhum use case de identity deixa escrita parcial no banco: quando a N-ésima
escrita de uma requisição falha, as anteriores são desfeitas — e um gate impede que
um use case novo volte a escrever duas vezes fora de uma unidade.

## 3. Contexto e premissas

### Contexto
Hoje cada repositório recebe um `Engine` e abre a própria transação por método
público (concept 2.3 §7 Decisão 6). A 2.3 recusou o UoW por falta de consumidor;
o consumidor apareceu. O caso mais agudo: `set_password_with_token` faz
`consume → revoke_all_for_user → invalidate_all_for_user → set_password_hash`, quatro
escritas em três repositórios, protegidas só pela **ordem** (fail-closed): o pior
caso é link queimado, sessões revogadas e senha inalterada.

As consequências medidas do status quo, uma por use case:

| Use case | Falha entre escritas hoje deixa | Com a unidade |
|---|---|---|
| `set_password_with_token` | link consumido, sessões revogadas, senha antiga | nada muda; o mesmo link funciona de novo |
| `refresh_session` (rotação) | refresh antigo revogado, nenhum novo — a retentativa do cliente vira **reuso** e revoga **todas** as sessões | refresh antigo válido; retentativa funciona |
| `invite_user` / `provision_account` | conta sem token; reconvidar responde 409 | nem conta nem token |
| `request_password_reset` | redefinições anteriores invalidadas, nenhuma nova | nada muda (e o 202 continua igual) |

Inventário completo de escritas por use case: tabela do ADR 2.6.0002 §Context.

### Janelas herdadas da 3.5
O concept 3.5 §6.4 apontou para a #46 as janelas de "dois BCs escritos numa
requisição sem Unit of Work", e o §10 de lá nomeou "a mesma Stage da #46" para a
última escrita sobre `user_id`. Disposição de cada uma:

| Janela (3.5 §6.4) | Disposição |
|---|---|
| Órfão em identity ao criar (`employees.update` falha depois do provisionamento) | **mantida** — fechá-la exige transação entre BCs (ADR 2.6.0002 §2). O caminho de recuperação (vincular login existente) **ainda não existe**: é `[finding]` da 3.5 §10, Stage candidata 4.3 ou uma Stage de gestão de acesso |
| Órfão dentro de identity (`users.add` sem `tokens.add`) | **fechada** — `provision_account` passa a escrever numa unidade |
| Última escrita vence sobre `user_id` | **mantida e reencaminhada** — é lost update dentro de staff, não atomicidade de identity. O ADR 3.3.0006 Alt. B recusou o `FOR UPDATE` atravessando leitura e escrita por exigir a abstração adiada; o port desta Stage é de identity e não resolve staff (bc-independence). A correção barata nomeada pela 3.5 (`UPDATE … WHERE user_id IS NULL`, método dedicado do port de staff) é `[finding]` desta Stage, com issue nova |
| E-mail digitado errado | **fora** — não é janela de transação; segue o `[finding]` de desvincular/trocar login (3.5 §10) |
| E-mail > ~2.700 bytes ⇒ 500 | **fora** — limite do índice, não de transação; segue o finding de NUL/tamanho de identity (3.5 §10) |

### Premissas
- Toda requisição HTTP roda o use case numa thread do threadpool, num
  `copy_context()` próprio (verificado: anyio 4.14.1
  `_backends/_asyncio.py:2588`/`:1029`) — a variável de contexto do adapter não
  vaza entre requisições.
- Os repositórios em memória validam antes de mutar. **Hoje isso não está pinado**
  (os testes de duplicata da suíte de contrato só asseveram o `raises`, não o estado
  depois); esta Stage acrescenta a asserção de estado inalterado a esses testes
  (CA14), e é ela que sustenta a lei L3 no fake.
- O fake de `users.add` não impõe as FKs de vínculo que o Postgres impõe —
  divergência anterior a esta Stage, fora do escopo; nenhum teste desta Stage
  depende dela.

### Dependências
- `2.3-identity-persistence` / `2.5-email-invite`: os repositórios e o port de
  token cujas escritas passam a ser agrupadas.
- `3.5-employee-login-link`: `provision_account`, a fachada de identity e as
  janelas declaradas em §6.4 (uma fechada aqui, as demais mantidas).
- Issue #45: o estilo de gate com allowlist contável (`check_layout.py` regra 6).

## 4. Contratos

### Introduzidos
- **`UnitOfWork`** (`port-out`, `features/identity/application/ports/out/unit_of_work.py`)
  ```python
  class UnitOfWork(Protocol):
      def transaction(self) -> AbstractContextManager[None]:
          """Abre uma unidade: tudo ou nada nas escritas de repositório feitas dentro."""
          ...
  ```
  Leis L1–L6 (ADR 2.6.0001 §1): **L1** tudo ou nada; **L2** a exceção atravessa
  intacta (o **mesmo** objeto, `is`); **L3** chamada que falha não deixa efeito
  próprio nem envenena a unidade; **L4** leitura dentro vê as escritas da unidade;
  **L5** não reentrante — `RuntimeError` antes de tocar em qualquer coisa (observável:
  nenhuma conexão retirada do pool, nenhum estado novo publicado); **L6** fora de
  unidade, nada muda.
- **`SessionRepository.revoke(...) -> bool`** (`port-out` existente, mudança
  aditiva): `True` se esta chamada revogou, `False` se a sessão não existe ou já
  estava revogada. Quem ignorava o retorno (`revoke_session`, logout) continua
  ignorando.
- **`PostgresUnitOfWork(engine)`** — adapter em
  `features/identity/adapters/out/postgres/unit_of_work.py`.
- **`InMemoryUnitOfWork(*repositorios)`** — fake em
  `tests/fakes/features/identity/in_memory_unit_of_work.py`.
- **Construtores** dos cinco use cases ganham o parâmetro obrigatório
  `unit_of_work: UnitOfWork` (obrigatório de propósito: esquecer a fiação reprova
  no mypy, não passa calado).
- **Regra 10 de `check_layout.py`** (contrato de tooling, ADR 2.6.0002 §5).

### Consumidos
- `UserRepository`, `SessionRepository`, `PasswordSetupTokenRepository`,
  `RestaurantRepository`, `UnitRepository` — Stages 2.2/2.5, sem mudança de
  assinatura.
- `IdentityFacade.provision_account` — Stage 3.5; o comportamento externo não muda.

## 5. Invariantes e regras

1. **R1 — Atomicidade.** Em cada um dos cinco use cases, se qualquer escrita da
   unidade falha, nenhuma escrita da unidade fica gravada.
2. **R2 — A ordem fail-closed de `set_password_with_token` permanece** (não-objetivo
   mudá-la); passa a ser redundante, não errada, e o docstring diz isso. **Troca
   declarada:** a ordem garantia que, numa falha parcial, as sessões já tinham sido
   revogadas mesmo com a senha inalterada (CA8b da 2.5); com a unidade, a falha
   desfaz também a revogação, e as sessões vivas sobrevivem até a retentativa do
   usuário. Aceito: com a senha inalterada, quem tem a senha reabre sessão de
   qualquer jeito — a revogação isolada protegia pouco, e a retentativa agora
   funciona com o mesmo link.
3. **R3 — O caminho de reuso de `refresh_session` grava a revogação em massa**
   antes de levantar `RefreshTokenReuseError` — fora da unidade, como escrita única.
4. **R4 — Efeito colateral depois do commit.** E-mail sai depois de a unidade
   fechar: `invite_user` continua deixando a conta criada quando o envio falha
   (regra 13 da 2.5); `request_password_reset` continua absorvendo toda falha,
   inclusive o rollback da unidade, com status/corpo idênticos nos dois caminhos.
5. **R5 — Hash fora da unidade.** O argon2 de `set_password_with_token` roda antes
   de a unidade abrir, para não estender a janela de lock pelo tempo de CPU.
6. **R6 — Anti-replay preservado.** Duas redenções concorrentes do mesmo token: a
   segunda espera o lock da linha até a primeira terminar. Se a primeira **comita**,
   uma e só uma define a senha e a outra recebe `InvalidSetupTokenError`. Se a
   primeira **desfaz** depois do `consume`, o token nunca foi consumido e a segunda
   prossegue e define a senha — comportamento novo, correto (o link continua válido).
7. **R6b — Rotação concorrente do mesmo refresh.** Das duas, uma rotaciona; a outra
   encontra `revoke` devolvendo `False` dentro da unidade, desfaz a própria unidade,
   revoga todas as sessões do usuário (fora da unidade, gravando) e levanta
   `RefreshTokenReuseError`. Fail-closed: é a semântica de reuso do ADR 2.2.0001, e
   fecha uma janela que existia antes desta Stage (concorrente que lia a sessão
   antes do commit da revogação) e que a unidade alargaria. Se a primeira rotação
   **desfaz** (ex.: o `add` falha), o `revoke` da segunda reavalia, devolve `True` e
   ela rotaciona normalmente — análogo à variante de R6.
8. **R7 — Fiação única.** A unidade e os repositórios de identity compartilham o
   **mesmo** `Engine` no composition root (sem isso a unidade é ignorada em
   silêncio — ADR 2.6.0001 §Negative).
9. **R8 — Gate.** Use case com duas ou mais escritas precisa de **todas** dentro de
   **um único** bloco de unidade, exceto o padrão "grava e recusa" (escrita seguida
   de `raise` no mesmo bloco); escrita dentro de laço conta como duas. Fora disso
   reprova o `check_layout`, salvo entrada na allowlist; entrada sem correspondente
   também reprova (ADR 2.6.0002 §5).

## 6. Casos de erro e exceções

| Cenário | Comportamento |
|---|---|
| Exceção de domínio/aplicação dentro da unidade (`UserNotFoundError` → `InvalidSetupTokenError`, `SessionAlreadyExistsError`, …) | rollback; a mesma exceção sobe (L2); status HTTP inalterado |
| Erro de infraestrutura dentro da unidade (`OperationalError`, conexão perdida) | rollback; sobe cru, como hoje (500) |
| `consume` devolve `False` (perdeu a corrida) | `InvalidSetupTokenError` — nada foi escrito pela unidade |
| Falha do `EmailSender` em `invite_user` | conta e token já comitados; a exceção sobe (inalterado) |
| Qualquer falha em `request_password_reset` | absorvida; 202 idêntico (inalterado) |
| Unidade aberta dentro de outra | `RuntimeError` (L5) — erro de programação, 500 |
| Rotação concorrente do mesmo refresh (perdedora) | `RefreshTokenReuseError` + todas as sessões revogadas (R6b) |
| Deadlock entre duas unidades (ex.: o mesmo usuário redime convite e link de redefinição ao mesmo tempo: cada um trava o próprio token e espera as sessões/o token do outro) | o Postgres aborta uma (`40P01`, `OperationalError` → 500); ela desfaz inteira, o link continua válido. Novo com a unidade; raro; seguro |
| `COMMIT` falha por conexão perdida | **em dúvida**: o commit pode ter acontecido. Sobe cru (500). Não há como a aplicação saber; declarado, não tratado |
| O próprio rollback falha | sobe o erro do rollback (o SQLAlchemy o encadeia ao original); a L2 não se aplica — a conexão está perdida de qualquer forma |
| Falha de `employees.update` depois de `provision_employee_login` (staff) | **inalterado:** conta pendente em identity sem vínculo — janela declarada (3.5 §6.4); o caminho de recuperação (vincular login existente) ainda não existe (3.5 §10) |

## 7. Decisões técnicas relevantes

### D1 — Port em identity, não em `shared`
- **O quê:** `UnitOfWork` em `features/identity/application/ports/out/`.
- **Por quê:** só identity consome. `[decision:C]` degrau 1 — LAYOUT §4 ("reutilizado
  é medido, não previsto") e `check_dead_shared.py` (issue #45). A issue sugeria
  `shared/` primeiro; LAYOUT > issue na hierarquia de fonte.
- **Fonte:** LAYOUT §4; issue #46 §Critério de pronto.
- **ADR:** [`2.6.0001`](../../adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md) Alt. A

### D2 — O use case abre a unidade, em volta só das escritas
- **O quê:** `with self._unit_of_work.transaction():` no corpo do use case; leitura
  e checagem antes, hash antes, e-mail depois.
- **Por quê:** `[decision:E]` — embrulhar o `execute` inteiro (de fora do use case)
  desfaria a revogação do caminho de reuso (que levanta depois de revogar) e mandaria
  e-mail de dentro de uma transação que ainda pode desfazer. A "context manager
  entregue pelo composition root" que a #46 cita é, na leitura desta Stage, a
  escolhida: o composition root entrega o port; quem decide onde a unidade abre é
  o use case.
- **Fonte:** `refresh_session.py` (passo 3, revoga e levanta); `invite_user.py`
  (`execute`: `_emitir_token` seguido de `_enviar_convite`).
- **ADR:** 2.6.0001 §2 e Alt. C

### D3 — Conexão ambiente por `ContextVar`, chaveada pelo `Engine`; savepoint por chamada
- **O quê:** os repositórios trocam `engine.begin()`/`engine.connect()` por dois
  helpers que usam a conexão da unidade ativa do **mesmo** engine, dentro de
  `begin_nested()`; sem unidade, abrem a própria transação como hoje.
- **Por quê:** `[decision:C]` degrau 4 contra o formato *Cosmic Python* (mesma
  garantia, superfície várias vezes maior: construtores de todos os use cases,
  inclusive os seis de escrita única, e repositórios por requisição num grafo que o
  composition root monta uma vez); degrau 2 contra "sem savepoint" (commit de
  transação abortada vira `ROLLBACK` silencioso — fail-open; fake e real só
  concordam com o savepoint). Base: SQLAlchemy 2.0.51 `engine/base.py:867`,
  `:2771`; anyio 4.14.1 `_backends/_asyncio.py:2588`.
- **Fonte:** núcleos sobre `Connection` dos repositórios ("ponto de troca para um
  futuro UoW", ex.: `restaurant_repository.py:55`); `composition_root.py:480-690`
  (instâncias únicas). **Desvio do plano documentado:** o docstring de
  `restaurant_repository.py:14-18` previa que "passar a aceitar uma `Connection` de
  fora vira uma mudança de construtor"; esta Stage escolhe não mudar o construtor
  (ADR 2.6.0001 Alt. B explica por quê).
- **ADR:** 2.6.0001 §3, Alt. B e D

### D4 — `READ COMMITTED` mantido
- **O quê:** a unidade abre no nível default.
- **Por quê:** `[decision:E]` — a trava anti-replay é o `UPDATE` condicional; dentro
  da unidade o lock da linha dura até o commit e a redenção concorrente reavalia o
  predicado contra a linha comitada. **Medido** por teste de integração com duas
  threads (CA7), não presumido.
- **ADR:** 2.6.0001 §5

### D5 — Escopo: os cinco use cases de identity com 2+ escritas
- **O quê:** ver §1; `refresh_session` só na rotação.
- **Por quê:** é a população com escrita múltipla dentro de um BC; staff não tem
  nenhuma (inventário em ADR 2.6.0002 §Context).
- **ADR:** 2.6.0002 §1–§2

### D6 — Sem transação entre BCs
- **O quê:** staff não ganha unidade; as travessias da 3.5 mantêm a ordem.
- **Por quê:** `[decision:C]` degrau 1 — ADR 4.1.0006 Alt. A e ADR 3.3.0002 já
  rejeitaram transação atravessando BCs. O concept 3.5 (§1, fora do escopo) deixou
  "Unit of Work entre os dois BCs" para a #46; o ADR posterior, de hierarquia maior,
  decide. A janela "órfão dentro de identity" fecha aqui mesmo assim, porque a metade
  identity da travessia (`provision_account`) fica atômica.
- **ADR:** 2.6.0002 §2 e Alt. A

### D7 — E-mail depois do commit
- **O quê:** R4.
- **Por quê:** `[decision:C]` degrau 1 — ADR 3.5.0002 §4 e a regra 13 da 2.5. E-mail
  não se desfaz; mandá-lo de dentro de uma unidade que depois desfaz entrega link
  para token inexistente.
- **ADR:** 2.6.0002 §3 e Alt. C

### D9 — `SessionRepository.revoke` devolve `bool`; perdedor da rotação é reuso
- **O quê:** R6b. Mudança aditiva no port (de `None` para `bool`), com fake,
  Postgres (`rowcount == 1`) e contrato.
- **Por quê:** `[decision:C]` degrau 1 — o port de token já tem o precedente
  (`PasswordSetupTokenRepository.consume -> bool`, mesma forma de `UPDATE`
  condicional); degrau 2 para tratar o perdedor como reuso (fail-closed, ADR
  2.2.0001). Sem isso a unidade **alarga** a janela em que um replay concorrente
  recebe par válido sem alarme: a revogação só fica visível no commit. E a janela
  já existe hoje: o concept 2.4 §6 declarou como desfecho aceito "a segunda
  encontra a sessão já revogada e dispara a revogação de família", mas o `revoke`
  descarta o `rowcount` e a auditoria de 2026-09-28 (develop `368a3ae`) mediu o
  oposto — 11 de 12 corridas deixaram **dois** refresh vivos. D9 realiza o que a
  2.4 descreveu.
- **Fonte:** `session_repository.py` (`_revoke`, `WHERE revoked_at IS NULL`);
  `docs/stages/2.4-identity-http/concept.md` §6 ("Rotação concorrente do mesmo
  refresh"); achado do Checkpoint A.
- **ADR:** 2.6.0002 §1b

### D8 — Gate de escrita múltipla, substituindo o da #45 que não existe
- **O quê:** regra 10 do `check_layout.py` (ADR 2.6.0002 §5); allowlist inicial com
  `CreateLoginForEmployeeUseCase` e `DeactivateEmployeeUseCase`.
- **Por quê:** a #46 pede "atualizar ou remover o gate de allowlist da #45 (escrita
  multi-repo declarada)"; o gate **não existe** (`grep` em `scripts/` e `tests/` em
  `2c71615`). Sem gate, a próxima escrita entra fora da unidade com a suíte verde.
  Divergência do texto da issue, registrada.
- **ADR:** 2.6.0002 §5 e Alt. D

## 8. Integrações

### Internas
- **Composition root:** constrói um `PostgresUnitOfWork(engine)` com o mesmo
  `Engine` dos repositórios de identity e o injeta nos cinco use cases (inclusive no
  `ProvisionAccountUseCase` da fachada).
- **Staff (contrato do gateway):** a fixture `_gateway_real` monta
  `ProvisionAccountUseCase` sobre fakes de identity — passa a receber o
  `InMemoryUnitOfWork` desses fakes.

### Externas
- Nenhuma. O `EmailSender` continua sendo chamado como hoje, depois da unidade.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Repositório fiado com outro `Engine` ignora a unidade em silêncio | B | A | R7 pinado por teste de bootstrap (identidade do engine) |
| Testes unitários que asseveram escrita parcial (`TestOrdemFailClosed` e, fora da classe, `test_falha_ao_revogar_sessoes_ja_consumiu_o_token` em `test_set_password_with_token.py:349`; `test_revoke_da_antiga_precede_o_add_da_nova` em `test_refresh_session.py:246`) passam a falhar | A | B | reescritos na Task do use case: a asserção vira "nada gravado" (é o objetivo da Stage) |
| Método de repositório esquecido na migração para a conexão da unidade (escrita comita sozinha; leitura não vê a unidade; `UPDATE` em linha já travada pela unidade espera numa segunda conexão — trava que o Postgres não enxerga como deadlock) | M | A | teste mecânico: nenhum `_engine.begin(`/`_engine.connect(` em `identity/adapters/out/postgres/*_repository.py`; L1 do contrato parametrizada por **todo** método de escrita e L4 por todo método de leitura |
| Rollback do fake apaga o registro dos injetores de falha, e "nada gravado" passa vazio quando o use case falha antes de escrever | M | M | o fake restaura **só o estado persistido declarado** por cada repositório, **no lugar** (dicts/listas), e os testes asseveram que o injetor disparou na escrita N |
| Deadlock entre unidades concorrentes | B | B | declarado (§6); desfecho seguro |
| Variável de contexto vazando entre requisições | B | A | `copy_context()` por chamada (verificado na fonte) + `reset` em `finally`; teste com duas threads |
| Lock mantido até o commit causa espera em redenções concorrentes | M | B | as unidades contêm só escritas; hash fora (R5) |
| Gate por nome classifica errado um método de escrita | B | M | prefixos de leitura fixados; teste do classificador sobre os ports reais |

## 11. Critérios de aceitação

- [ ] **CA1** — `UnitOfWork` existe em `features/identity/application/ports/out/unit_of_work.py`, sem import de SQLAlchemy (`make check`: contratos de pureza verdes).
- [ ] **CA2** — Suíte de contrato da unidade parametrizada `[fake]`/`[postgres]` passa nas duas implementações e cobre: L1 parametrizada por **todo** método de escrita dos cinco repositórios; L2 com `is`; L3 com uma falha **originada no banco** (violação real de constraint, ex.: fingerprint de sessão duplicado) seguida de outra escrita e commit; L4 parametrizada por todo método de leitura; L5 com nenhuma conexão retirada do pool e nenhum estado publicado; L6.
- [ ] **CA3** — Fora de unidade os repositórios de identity se comportam como antes: suítes de contrato e integração existentes de identity verdes sem edição de asserção (salvo as acrescentadas por CA13/CA14); e nenhum `_engine.begin(`/`_engine.connect(` sobra em `features/identity/adapters/out/postgres/*_repository.py` (teste mecânico).
- [ ] **CA4** — Os cinco use cases recebem `unit_of_work` obrigatório; unit test com fake, para cada escrita N do use case: o injetor dispara **na escrita N**, as escritas 1..N-1 foram tentadas, e nenhum estado persistido sobra.
- [ ] **CA5** — Integração contra Postgres real para `set_password_with_token`, `invite_user`, `provision_account`, `request_password_reset` e a rotação de `refresh_session`: falha injetada **depois** de a N-ésima escrita delegar ⇒ tabelas envolvidas idênticas ao estado anterior, para todo N; e ao menos um caso com falha originada no banco.
- [ ] **CA6** — Integração (Postgres): o reuso de `refresh_session` revoga todas as sessões **e grava** antes de levantar; a rotação que falha no `add` deixa o refresh antigo válido e uma nova rotação com ele funciona.
- [ ] **CA7** — Integração (Postgres, duas threads, intercalação forçada por barreira dentro da unidade da primeira, depois do `consume`): a segunda redenção fica bloqueada até a primeira sair; se a primeira comita, a segunda recebe `InvalidSetupTokenError` e o hash final é o da primeira; se a primeira falha depois do `consume`, a segunda define a senha.
- [ ] **CA8** — `invite_user` com envio falhando deixa conta e token comitados e sobe a exceção; `request_password_reset` absorve toda falha **dentro do `try`** (inclusive o rollback da unidade) e, sem falha, grava de fato o token pela unidade real (integração positiva).
- [ ] **CA9** — No composition root, para cada uma das cinco instâncias de use case (inclusive o `ProvisionAccountUseCase` da fachada), todo repositório de identity injetado tem o **mesmo** `Engine` que a unidade injetada (teste de bootstrap).
- [ ] **CA10** — Nenhum texto em `src/` aponta a atomicidade de identity para a 4.4 nem afirma que não há unidade de trabalho / que ela é futura. Lista fechada dos trechos que hoje o fazem e passam a descrever o que existe: `set_password_with_token.py` (nota 2, "aponta para a 4.4"), `refresh_session.py:113-117` ("não há port de unidade de trabalho"), `invite_user.py:16-20` ("a transação de `add` já fechou"), `restaurant_repository.py:3-18`, `unit_repository.py:3-11`, `user_repository.py`/`session_repository.py`/`unit_repository.py`/`restaurant_repository.py` (comentário "ponto de troca para um futuro UoW") e, em staff, `employee_repository.py:7-14` e `job_function_repository.py:5-11` (citam o desvio "que identity assumiu… sem UoW"). Verificação: `grep -rniE "unit.of.work|unidade de trabalho|UoW|4\.4|não são atômic" src/restaurant_hub` revisado ocorrência a ocorrência no relatório, sem nenhuma que contradiga esta Stage; o de `set_password_with_token` cita a #46/Stage 2.6.
- [ ] **CA11** — Regra 10 do `check_layout`, com fixtures sintéticas: reprova escrita fora de unidade num use case com outra escrita dentro (o `consume` movido para fora), reprova dois blocos de unidade, reprova escrita em laço fora de unidade, aceita "grava e recusa", segue `self._helper()`, reprova entrada de allowlist sem correspondente; `make check` verde com a allowlist de duas entradas.
- [ ] **CA12** — `LAYOUT.md` descreve a fronteira transacional (onde abre, o que fica fora, que não atravessa BC).
- [ ] **CA13** — Integração (Postgres, duas threads, intercalação forçada): duas rotações do mesmo refresh ⇒ exatamente uma devolve par novo; a outra levanta `RefreshTokenReuseError` e, ao fim, todas as sessões do usuário estão revogadas; variante em que a primeira desfaz (falha no `add`) ⇒ a segunda rotaciona normalmente. `revoke` devolve `True`/`False` conforme o contrato (fake e Postgres).
- [ ] **CA14** — Os testes de duplicata da suíte de contrato de identity asseveram o estado inalterado depois da recusa (sustenta a premissa da L3 no fake).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida?
- [x] Toda decisão em §7 tem fonte rastreável?
- [x] Toda integração externa tem contrato definido? (nenhuma nova)
- [x] Decisões com alternativa real descartada têm ADR escrito? (2.6.0001, 2.6.0002)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.5 done)
- [x] Stage cabe em ~3–12 Tasks? (13 previstas; abaixo do alarme de 14)
- [x] Riscos críticos têm mitigação plausível?
- [x] Cada não-objetivo da #46 continua fora? (locking otimista, ordem fail-closed, async)

## 13. Questões em aberto

Nenhuma bloqueante. Forks fechados por evidência/convenção (`[decision:E|C]` em §7);
nenhum de classe P.

## 14. Referências

- [`../../overview.md`](../../overview.md)
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.6-identity-unit-of-work`
- ADRs: [2.6.0001](../../adr/2_6_0001-identity-unit-of-work-port-and-ambient-connection.md), [2.6.0002](../../adr/2_6_0002-unit-of-work-scope-identity-only-no-cross-bc-transaction.md); 2.2.0004, 3.3.0002, 3.3.0006, 3.5.0002, 3.5.0003, 4.1.0006
- `docs/stages/2.3-identity-persistence/concept.md` §7 Decisão 6 (superada para identity)
- `docs/stages/2.4-identity-http/technical.md` §7 — finding de atomicidade
- `docs/stages/3.5-employee-login-link/concept.md` §6.4, §10
- Issue #46

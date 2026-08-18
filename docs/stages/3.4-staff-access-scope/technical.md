---
title: Technical — Acesso e escopo de equipe
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, staff-access-scope, permissao, escopo-unidade, access-guard, byte-nul, tenant-wide]
status: done
created_at: 2026-08-12
updated_at: 2026-08-17
stage_id: 3.4-staff-access-scope
stage_title: Acesso e escopo de equipe
step_id: 3
step_title: Equipe da unidade
depends_on: [3.3-staff-persistence]
concept_ref: ./concept.md
issue_id: 40
branch: feat/40-3-4-staff-http
tasks_count: 6
---

# Technical — Stage 3.4 — Acesso e escopo de equipe

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.4/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 3.4: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/40-3-4-staff-http` — nome antigo, mantido de propósito: a branch nasceu
> antes do corte da Fase 3A, e renomeá-la depois do primeiro push só produziria
> ruído de referência. Não há sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage **não escreve funcionalidade nova** — ela emenda código já mergeado de
cinco Stages (`2.1`, `2.2`, `3.1`, `3.2`, `3.3`) em dois bounded contexts, para
fechar dois defeitos de acesso e uma divergência fake ≢ real **antes** de existir
borda HTTP que os exponha (a borda é a Stage 3.6). O trabalho tem quatro
naturezas: (a) estender o vocabulário de acesso de `identity` com duas permissões
de equipe e um conjunto tenant-wide que dispensa a exigência de unidade no passo 4
do guard; (b) fazer a **unidade entrar no endereço do funcionário até a assinatura
do port**, propagando por dez commands, dez use cases, os dois implementadores e a
suíte de contrato; (c) rejeitar o byte NUL nos nomes do domínio de staff e dar a
`DayPeriod` um `from_string` tipado; (d) criar o port `AccessGuard` de staff com
quatro leis publicadas e montar o tradutor sobre o `IdentityGuard` no composition
root, mantendo `bc-independence` sem nenhuma supressão. **Nenhuma rota nasce
aqui.**

### Estratégia

**O risco desta Stage é a emenda de contrato mergeado**, e a ordem foi montada em
torno de uma pergunta só: *este commit deixa `make check` verde?* Duas
propriedades mecânicas do repositório governam a resposta e precisam estar na
cabeça de quem executa:

- **`make typecheck` = `mypy src/ tests/fakes/`** (`Makefile:111`). Mudar a
  assinatura de um método do `Protocol` quebra **no mesmo instante** todo chamador
  em `src/` (os use cases), o adapter Postgres (verificado estruturalmente onde é
  passado aos construtores tipados dos use cases, no `composition_root`) **e** o
  fake. Os três não podem ser separados em commits distintos.
- **`make test-gate` roda a suíte inteira**, e a suíte de contrato
  (`tests/contract/features/staff/`) exercita **o mesmo corpo de teste** contra
  fake e Postgres. Mudar a aridade de um lado só a derruba imediatamente.

Daí a ordem abaixo, que **é exceção declarada ao default da skill
`task-ordering-hex`**: esta não é uma vertical slice nova, é o caso "emenda sobre
BC consolidado", em que o inside-out clássico (domain → application → adapters →
wiring) não se aplica porque as camadas já existem e o que muda é um contrato que
as atravessa.

| # | Task | Natureza da mudança | Por que o commit fica verde |
|---|---|---|---|
| 01 | identity: permissões + `TENANT_WIDE_PERMISSIONS` + passo 4 | **aditiva** | acrescenta membros a um `StrEnum` e a três entradas de um mapa **total**; o passo 4 ganha uma condição que só pode **permitir mais**, e nenhuma permissão hoje em uso está no conjunto novo |
| 02 | staff domain: byte NUL + `DayPeriod.from_string` | **restritiva, sem população violadora** | medido: **nenhum `.py` de `tests/` contém `\x00`** (varredura por bytes; os 158 arquivos com NUL bruto sob `tests/` são todos `.pyc` de `__pycache__`), então a restrição não invalida fixture existente; `from_string` é puro acréscimo |
| 03 | os dez commands ganham `unit_id` | **aditiva em `src/`, mecânica nos testes** | os commands **não têm chamador em `src/`** — não há adapter de entrada de staff (é o que a 3.3 declarou ao wirar 16 use cases sem consumidor) —, então o campo novo só exige atualizar os nove arquivos de teste que os constroem |
| 04 | a unidade na assinatura do port | **restritiva e atômica** | é o commit grande, e é grande **por necessidade**: port + dez use cases + adapter Postgres + fake + suíte de contrato **+ a suíte de integração de Postgres** são o conjunto mínimo que deixa a suíte verde. A integração viaja junto por um motivo que a §Premissas não pega sozinha: `mypy` **não** alcança `tests/integration/`, então lá o desalinhamento de aridade não vira erro de tipo — vira `TypeError` em execução, nos **31** call sites medidos (caixa abaixo) |
| 05 | port `AccessGuard` + leis + fake | **criação isolada** | arquivos novos; nada existente os importa |
| 06 | tradutor + wiring no composition root | **aditiva** | um campo novo no `dataclass` de dependências e uma construção nova em `wire_dependencies`; `build_http_wiring` **não** muda (CA21) |

> **Por que a Task 04 fica atômica.** **Nenhum corte por camada** deixa o commit
> verde — e vale nomear os três cortes tentadores, para que ninguém os tente na
> Fase 4:
>
> - *port + fake primeiro, use cases depois* → mypy reprova os dez use cases por
>   argumento faltante (`src/` é checado).
> - *port + use cases primeiro, adapter depois* → `PostgresEmployeeRepository`
>   deixa de satisfazer o `Protocol` no ponto em que o `composition_root` o passa
>   aos construtores tipados, **e** a suíte de contrato quebra no parâmetro
>   `[postgres]`.
> - *tudo em `src/` primeiro, fake depois* → `mypy tests/fakes/` reprova, e a
>   suíte de contrato quebra no parâmetro `[fake]`.
>
> **Existe um quarto corte, e ele É verde: o corte por MÉTODO.** Commit A dá
> `unit_id` só a `find_by_id` (docstring, fake, adapter, os dez use cases de
> leitura e os call sites de leitura); commit B faz o mesmo com `delete`. Cada
> metade é internamente consistente — mypy verde, contrato verde nos dois
> parâmetros —, e o fake permite porque o seu `delete` resolve pelo privado
> `_find`, e não pelo `find_by_id` público
> (`in_memory_employee_repository.py:101`): os dois métodos públicos são de fato
> desacoplados. **Registrar isto é obrigação** — a alternativa seria uma premissa
> absoluta falsa sustentando a exceção ao critério de ≤ 5 arquivos.
>
> **Recusamos o corte por método por COESÃO, não por vermelhidão.** `find_by_id` e
> `delete` recebem **uma** lei — a unidade entra no endereço do funcionário
> (ADR 3.4.0007 §1) —, e a suíte de contrato a prova com um corpo só. Parti-la em
> dois commits dobra a superfície de revisão do **mesmo** invariante e abre uma
> janela em que metade do endereço está protegida e metade não, sem que nada no
> repositório sinalize a assimetria. O ganho seria de ~6 arquivos num commit de 26;
> o custo é revisar duas vezes a mesma decisão de segurança.
>
> A alternativa a recusar **por vermelhidão de propósito** é outra: dar a `unit_id`
> um **default `None`** por um commit. Ela produziria um commit inteiro em que a
> lei de segurança está escrita no port e **não é exigida** pelo sistema de tipos —
> exatamente a forma de defeito que esta Stage existe para fechar.

**A lei de unidade nasce no port, não no SQL.** É a razão declarada do
ADR 3.4.0007 §2, e a Task 04 a executa nessa ordem: primeiro a **docstring do
`Protocol`** (que é especificação neste projeto — ver o cabeçalho de
`employee_repository.py`), depois o fake, depois o adapter, e a suíte de contrato
provando os dois lados com **um corpo de teste só**. Um plano que pusesse a
filtragem apenas no `WHERE` do Postgres estaria contra o concept §5.6 e
reintroduziria a divergência fake ≢ real que este Step já pagou uma vez (byte
NUL), agora sobre um invariante de **segurança**.

### Desvio declarado em relação à tabela indicativa do concept §13

O concept lista as mesmas 6 Tasks com um agrupamento ligeiramente diferente (port
+ commands + fakes | use cases | adapters + contrato como três Tasks separadas, e
`AccessGuard` + tradutor como uma só). Este plano **regrupa sem mudar conteúdo,
contrato, fronteira nem critério de aceite**, por duas razões mecânicas:

- as três Tasks de escopo de unidade **colapsam em duas** (03 e 04), porque o
  corte entre elas produz commit vermelho — a caixa acima demonstra;
- a Task de `AccessGuard` **se divide em duas** (05 e 06), porque o critério 4 de
  Task Atômica ([`PIPELINE.md`](../../PIPELINE.md) §4.3) proíbe criar port e
  adapter desse port no mesmo commit — e o tradutor **é** o adapter do
  `AccessGuard`.

Total: **6 Tasks**, o mesmo número que o concept validou em §12. Pelo critério de
[`PROMPT-stage-single-session.md`](../../PROMPT-stage-single-session.md)
§"Verificação de gap no Concept", isto é **refinamento de detalhe**, não gap
material — o concept **não regride**.

### O achado do CA20, e por que ele é o critério funcionando

**Não houve contradição, e não há decisão pendente.** A redação original do CA20
dizia: *"A suíte de identity passa sem alteração de asserção. Se alguma precisar
mudar, a mudança não foi aditiva — **é achado, não ajuste**."* A cláusula final
**antecipa** este caso e prescreve o tratamento; a Fase 3B mediu o caso e o
registrou como achado, que é exatamente o que o critério mandava.

Medição em `tests/unit/features/identity/domain/test_role_permission.py`:

- **linha 27** — `test_permission_e_conjunto_fechado` assere o conjunto **exato**
  dos valores do enum `Permission` (`{"manage_platform", "manage_tenant",
  "manage_users"}`). Acrescentar `MANAGE_STAFF` e `MANAGE_JOB_FUNCTIONS` **exige**
  editar esta asserção.
- **linhas 66–78** — `test_conteudo_exato_do_mapa_por_papel` é parametrizado com o
  conjunto **exato** de permissões de cada papel. Dar as duas permissões novas a
  `OWNER`, `MANAGER` e `HR` **exige** editar três dos cinco parâmetros.

**O conteúdo do achado:** a inferência do CA20 — *"asserção mudou ⟹ a mudança não
foi aditiva"* — tem **falso positivo para teste de fechamento**. Um teste que
assere o conjunto exato de um enum é *projetado* para exigir atualização
consciente quando o conjunto cresce legitimamente; é o mecanismo que o
ADR 3.4.0008 §5 pede (*"adding a permission to the set is a deliberate, reviewed
act rather than a one-word diff that no test observes"*). Ele mudar é o teste
funcionando. A regressão que CA20 existe para pegar é outra: **decisão de acesso**
mudando — papel perdendo permissão, permissão sumindo do enum, `authorize`
passando a permitir o que negava.

**Disposição — corrigido, via regressão de CONVENTIONS §3.2.** CA20 é **critério
de aceite**, e a §7 deste technical pode *registrar* um achado mas não pode
*emendar* um critério do concept sem inverter a hierarquia Concept > Technical.
Além disso o **mesmo texto vivia no 5º bullet do `definition_of_done` do bloco 3.4
do `roadmap.md`** (fonte mais alta), de modo que uma nota só aqui deixaria dois
artefatos superiores afirmando o que a Stage viola na leitura literal — a classe
de afirmação-sobre-outro-arquivo que este Step vem policiando. Os três commits:

| Commit | O que faz |
|---|---|
| `c3523f5` | `chore(concept): revert to draft — revision-from-technical: falso positivo do CA20` |
| `e64f95e` | `stage 3.4: conceptual approved` — CA20 refinado + nota datada com o achado; §5.11 e a linha de risco da §10 em sincronia |
| `9c4a30f` | `docs(staff): reconciliar o DoD do bloco 3.4 com o CA20 refinado [3.4/--]` |

**O conjunto de comportamentos protegidos não mudou** — mudou a formulação que o
descreve. O critério refinado (concept §11) discrimina:

- **proibido** — qualquer asserção de **decisão de acesso** mudar (par
  papel↔permissão já existente; resultado de `AuthorizeActionUseCase` nos casos já
  cobertos);
- **obrigatório** — as fixtures de **fechamento de vocabulário** acompanharem o
  conjunto que cresceu, com a aditividade **provada**: nenhum membro removido de
  `Permission`, nenhum papel perdendo permissão que já tinha, e as duas fixtures
  listadas nominalmente no corpo do commit.

### Pré-condições

- Stage `3.3-staff-persistence` em `done` e **mergeada** em `develop` — é o código
  que esta Stage emenda.
- Branch `feat/40-3-4-staff-http`, working tree limpo, issue **#40** OPEN.
- `concept.md` desta Stage em `status: done` (gate `09aab7a`).
- **PostgreSQL real no ar** — exigência do ADR 2.3.0001, **sem skip**: a suíte de
  contrato falha alto quando o banco não responde, e é isso que impede a Stage de
  reportar verde por não ter olhado. **Vale para TODA Task, não só para as duas que
  tocam o banco diretamente:** as seis terminam em `make check`, que encadeia
  `test-gate` → `pytest tests/`, e `tests/conftest.py` não tem caminho de skip.
  Subir e esperar o banco é passo de abertura de **toda** sessão desta Stage:

  ```powershell
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  ```

  > **Container órfão de worktree anterior retém a porta.** Se o `pg_isready`
  > passar mas a suíte falhar sobre dados que ninguém gravou, confira `docker ps`
  > — é infra da Stage anterior.

- Ambiente de `make` no Windows: `$env:PATH += ";C:\msys64\usr\bin"` e
  `$env:UV_SYSTEM_CERTS="1"` em toda sessão PowerShell.

### Premissas técnicas

- **`mypy` cobre `src/` e `tests/fakes/`** (`Makefile:111`) e **não** cobre o
  restante de `tests/`. É a propriedade que define quais arquivos precisam viajar
  no mesmo commit (§1 Estratégia).
- **Não há migration nesta Stage.** O schema é o da 3.3 (`0003_staff`); a lei de
  unidade é imposta na consulta, não na estrutura (concept §9). O ADR 3.3.0006
  §Consequences aloca a coluna de versão do controle otimista à *"migration da
  3.4"* — **isso é falso**, e já está reconciliado na nota datada do
  `roadmap.md`. **Nenhum arquivo em `migrations/` é tocado.**
- **Cobertura de `Protocol` medida, não suposta:** os módulos de port existentes
  marcam **100%** no `term-missing` (corpo `docstring + ...` não conta como
  statement não executado). O `access_guard.py` novo não vai precisar de
  justificativa de cobertura.
- **`create_engine` não abre conexão** — montar o tradutor no composition root não
  muda o comportamento de boot.
- **Nenhum `.py` de `tests/` contém `\x00`** — varredura por bytes sobre todos os
  arquivos de `tests/`: 158 acusam NUL bruto e **todos** são `.pyc` de
  `__pycache__`; nos `.py`, zero. A restrição da Task 02 não invalida fixture
  existente.
- **`AuthorizedActor.actor_tenant_id` é `RestaurantId | None`** — ausente só para
  `platform_admin`. É a fonte do `tenant_id` do `AuthorizedScope` e o gatilho da
  lei **L-AG3**.
- **`IdentityGuard` vive sob o pacote `in`** e só é alcançável por `importlib`;
  o `composition_root` já o guarda como `Any` (linhas 185–188). O tradutor herda
  essa forma — é a razão medida do ADR 3.4.0001 §Decision 3.

### Estrutura de pastas afetada

```
src/restaurant_hub/
├── composition_root.py                                    # M — tradutor + campo (Task 06)
└── features/
    ├── identity/
    │   ├── domain/value_objects/permission.py             # M — 2 permissões + TENANT_WIDE (01)
    │   ├── domain/value_objects/role.py                   # M — mapa de papéis (01)
    │   └── application/use_cases/authorize_action.py      # M — passo 4 (01)
    └── staff/
        ├── domain/entities/employee.py                    # M — byte NUL (02)
        ├── domain/entities/job_function.py                # M — byte NUL (02)
        ├── domain/value_objects/shift_preference.py       # M — DayPeriod.from_string (02)
        ├── domain/exceptions/errors.py                    # M — InvalidDayPeriodError (02)
        ├── application/dtos/commands.py                   # M — 10 commands (03)
        ├── application/ports/out/employee_repository.py   # M — unidade na assinatura (04)
        ├── application/ports/out/access_guard.py          # N — port + AuthorizedScope (05)
        ├── application/use_cases/*.py                     # M — 10 use cases (04)
        └── adapters/out/postgres/employee_repository.py   # M — unidade no WHERE (04)

tests/
├── fakes/features/staff/
│   ├── in_memory_employee_repository.py                   # M — a mesma lei (04)
│   └── in_memory_access_guard.py                          # N — 2ª implementação (05)
├── contract/features/staff/
│   ├── test_employee_repository_laws.py                   # M — NUL (02) + unidade (04)
│   └── test_job_function_repository_laws.py               # M — NUL (02)
└── unit/features/
    ├── identity/domain/test_role_permission.py            # M (01)
    ├── identity/application/test_authorize_action.py      # M (01)
    └── staff/
        ├── domain/test_{employee,job_function,shift_preference,exceptions}.py  # M (02)
        ├── application/test_*.py                          # M (03, 04)
        ├── application/test_access_guard_laws.py          # N (05)
        ├── test_bc_independence.py                        # N (05)
        └── adapters/test_composition_root_staff.py        # M (06)
```

**Nenhum arquivo nasce em `src/restaurant_hub/features/staff/adapters/in/`** — é o
CA21, e é o que torna esta Stage segura de mergear.

## 2. Tasks

> Faixa saudável: **3–12 Tasks por Stage**. ≥ 14 = Stage grande demais. Esta tem
> **6** — o mesmo número validado no concept §12, com o regrupamento justificado
> em §1.

### Task 01 — identity: duas permissões de staff, o mapa de papéis, `TENANT_WIDE_PERMISSIONS` e a dispensa do passo 4

- **Arquivos a criar:**
  - `tests/unit/features/identity/domain/test_rbac_additivity.py`
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/identity/domain/value_objects/permission.py`
  - `src/restaurant_hub/features/identity/domain/value_objects/role.py`
  - `src/restaurant_hub/features/identity/application/use_cases/authorize_action.py`
  - `tests/unit/features/identity/domain/test_role_permission.py`
  - `tests/unit/features/identity/application/test_authorize_action.py`
  - `tests/unit/features/identity/domain/test_rbac_additivity.py` **(criar)**
- **O que fazer:** dar a `identity` o vocabulário de acesso que o Step 3 precisa —
  duas permissões novas, as entradas correspondentes no mapa de papéis, o conjunto
  `TENANT_WIDE_PERMISSIONS` e a única condição de `AuthorizeActionUseCase` que o
  consulta. É a Task que torna `manager` e `hr` capazes de alcançar o catálogo de
  funções sem afrouxar nada sobre registro de funcionário.
- **Detalhes técnicos:**
  - **`Permission`** ganha `MANAGE_STAFF = "manage_staff"` e
    `MANAGE_JOB_FUNCTIONS = "manage_job_functions"`. O docstring do módulo já
    prevê a extensão (*"as Stages/BCs seguintes estendem o vocabulário"*); a
    docstring passa a nomear o eixo de unidade das duas.
  - **`TENANT_WIDE_PERMISSIONS: frozenset[Permission]`**, no **mesmo módulo**
    (ADR 3.4.0008 §1), contendo **exatamente** `{MANAGE_JOB_FUNCTIONS}`. O comentário
    de definição declara o critério de entrada: *permissão cujo alvo é o
    restaurante, não a unidade* — e que `MANAGE_STAFF` está fora **de propósito**.
  - **`_ROLE_PERMISSIONS`** (`role.py`): `OWNER`, `MANAGER` e `HR` ganham as duas;
    `EMPLOYEE` e `PLATFORM_ADMIN` **nada**. O comentário sobre `manager`/`hr`
    ("coincidem em identity e divergem no eixo de visibilidade") passa a citar a
    restrição para frente do ADR 3.4.0006 §3 — **o Step 4 não pode dar a `hr`
    permissão sobre a escala**, e este é o arquivo que quem estender o mapa lê.
  - **Passo 4 de `AuthorizeActionUseCase`**, literal do ADR 3.4.0008 §2:

    ```python
    if (
        command.unit_id is None
        and not user.bypasses_unit_scope()
        and command.permission not in TENANT_WIDE_PERMISSIONS
    ):
        raise UnitScopeRequiredError(user.role.value)
    ```

    Import de `TENANT_WIDE_PERMISSIONS` a partir de
    `identity.domain.value_objects.permission` — `application → domain`, direção
    legal (LAYOUT §3). **Passos 3 e 5 não são tocados** (concept §5.5).
  - **A dispensa é por permissão, nunca por papel** (concept §5.4): nada é
    acrescentado a `_UNIT_SCOPE_BYPASS_ROLES`, e a docstring do use case diz por
    quê — pôr `manager`/`hr` lá daria alcance tenant-wide sobre **todas** as
    permissões, inclusive `MANAGE_STAFF`.
  - **Testes novos** em `test_role_permission.py`: CA2 (parametrizado sobre os
    cinco papéis, cada um com o subconjunto de staff esperado), CA3 (`hr` e
    `manager` têm conjuntos de permissão de staff **idênticos** — falha se alguém
    os separar sem ADR), CA6 (`TENANT_WIDE_PERMISSIONS` == lista esperada
    explícita), CA7 (`MANAGE_STAFF` **não** está no conjunto — mata a mutação que
    daria alcance cross-unidade sobre registros).
  - **Testes novos** em `test_authorize_action.py`: CA4 (ator unit-scoped
    exercendo `MANAGE_JOB_FUNCTIONS` **sem** unidade é **autorizado**), CA5 (o
    mesmo ator com `MANAGE_STAFF` sem unidade continua recebendo
    `UnitScopeRequiredError`) e CA8 (passos 3 e 5 inalterados: ator de outro
    tenant negado, e unidade não visível negada, **também** para permissão
    tenant-wide). CA4 e CA5 juntos cobrem os dois ramos da condição nova — é o que
    a cobertura de branch do projeto exige.
  - **A aditividade do CA20 vira teste, não inspeção** (`test_rbac_additivity.py`).
    Sem isto, as três provas do critério dependem de alguém ler um `git diff` e uma
    mensagem de commit — auditoria por olho, que é o modo de falha que esta Stage
    inteira existe para fechar. Duas asserções de **subconjunto**, com as baselines
    congeladas como constantes do módulo (os valores anteriores a esta Stage):

    ```python
    BASELINE_PERMISSIONS = {"manage_platform", "manage_tenant", "manage_users"}
    BASELINE_ROLE_PERMISSIONS = {
        Role.PLATFORM_ADMIN: {Permission.MANAGE_PLATFORM},
        Role.OWNER: {Permission.MANAGE_TENANT, Permission.MANAGE_USERS},
        Role.MANAGER: {Permission.MANAGE_USERS},
        Role.HR: {Permission.MANAGE_USERS},
        Role.EMPLOYEE: set(),
    }
    # nenhum membro removido do enum
    assert BASELINE_PERMISSIONS <= {p.value for p in Permission}
    # nenhum papel perdeu permissão que já tinha
    for papel, antes in BASELINE_ROLE_PERMISSIONS.items():
        assert antes <= papel.permissions
    ```

    **É `<=`, não `==`, de propósito:** crescer é permitido, encolher não. O teste
    sobrevive a esta Stage e passa a guardar **toda** extensão futura do
    vocabulário — é o antídoto permanente para o falso positivo que o CA20 tinha.
- **Critério de aceite:**
  - CA1, CA2, CA3, CA6, CA7 (vocabulário e mapa) e CA4, CA5, CA8 (autorização),
    todos com teste verde.
  - **CA20 (refinado — concept §11), nas duas metades:**
    - *proibido* — nenhuma asserção de **decisão de acesso** muda: nenhum par
      papel↔permissão **já existente** é alterado, e nenhum caso já coberto de
      `AuthorizeActionUseCase` muda de resultado. Verificação:
      `git diff -- tests/unit/features/identity/` não mostra edição fora das duas
      fixtures de fechamento.
    - *obrigatório, com aditividade **provada*** — as duas fixtures de fechamento
      (`test_permission_e_conjunto_fechado`, linha 27; e três dos cinco parâmetros
      de `test_conteudo_exato_do_mapa_por_papel`, linhas 66–78) acompanham o
      conjunto que cresceu. A prova é positiva, não a ausência de falha: nenhum
      membro removido de `Permission`, nenhum papel perdendo permissão que já
      tinha, e **as duas fixtures listadas nominalmente no corpo do commit**. As
      duas primeiras provas são **mecânicas** (`test_rbac_additivity.py`); só a
      listagem nominal no commit é de olho.
  - Cobertura ≥ 90% nos três arquivos de `src/` tocados.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/identity/ -v
  git diff -- tests/unit/features/identity/   # confirmar: só as 2 fixtures de fechamento
  uv run pytest tests/ --cov=src/restaurant_hub/features/identity --cov-report=term-missing
  make check
  ```
- **Commit sugerido:** `feat(identity): permissoes de equipe, conjunto tenant-wide e a dispensa do passo 4 [3.4/task-01]`

---

### Task 02 — staff domain: byte NUL recusado no nome, `DayPeriod.from_string` e `InvalidDayPeriodError`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/domain/exceptions/errors.py`
  - `src/restaurant_hub/features/staff/domain/entities/employee.py`
  - `src/restaurant_hub/features/staff/domain/entities/job_function.py`
  - `src/restaurant_hub/features/staff/domain/value_objects/shift_preference.py`
  - `tests/unit/features/staff/domain/test_employee.py`
  - `tests/unit/features/staff/domain/test_job_function.py`
  - `tests/unit/features/staff/domain/test_shift_preference.py`
  - `tests/unit/features/staff/domain/test_exceptions.py`
  - `tests/contract/features/staff/test_employee_repository_laws.py`
  - `tests/contract/features/staff/test_job_function_repository_laws.py`
- **O que fazer:** fechar, no domínio, as duas divergências que a 3.3 mediu e
  escalou — nome com byte NUL (que o fake gravava e o Postgres recusava
  client-side com `psycopg.DataError`, sem `sqlstate`, fora do alcance do tradutor
  de integridade) e a conversão de texto para `DayPeriod` (hoje `ValueError`, que
  não é `StaffError`).
- **Detalhes técnicos:**
  - **`InvalidDayPeriodError(StaffError)`** em `errors.py`, no mesmo formato dos
    demais (mensagem com o valor recebido), espelhando `InvalidRoleError` de
    identity.
  - **`DayPeriod.from_string(value: str) -> DayPeriod`** em `shift_preference.py`,
    idêntico em forma ao `Role.from_string`: `try: return cls(value)` /
    `except ValueError as exc: raise InvalidDayPeriodError(value) from exc`. **A
    causa original é preservada** (`from exc`) — há teste equivalente em identity e
    deve haver aqui.
  - **Byte NUL em `Employee.__post_init__` e `JobFunction.__post_init__`:**
    acrescentar, **junto** da checagem de nome vazio já existente
    (`employee.py:83-84`, `job_function.py:56-57`), a recusa de `"\x00" in
    self.name` com `InvalidNameError`. Por estar em `__post_init__`, vale para
    **todos** os caminhos de construção — `rename` (que passa por
    `dataclasses.replace`) e a **reidratação do mapper** da 3.3
    (`mappers.py:103`, `:265`), que é o caminho que a CA16 nomeia.
  - **Escopo da restrição: só o byte NUL** (concept §5.10, ADR 3.4.0003 §2). Nada
    de outros caracteres de controle, normalização de espaço ou limite de
    tamanho — a 3.3 mediu que todo o resto faz round-trip verbatim nos dois lados,
    e alargar seria normalização silenciosa por outro nome (contra o ADR 2.3.0005).
  - **A suíte de contrato ganha o caso** (CA17), nos dois arquivos de lei: gravar
    um registro cujo nome contém `\x00` levanta `InvalidNameError` **na construção
    da entidade**, antes de qualquer port — e por isso `[fake]` e `[postgres]`
    concordam **por construção**. É esta asserção que hoje reprovaria em
    `[postgres]` e passará nos dois. **É a razão de esta Task exigir Postgres no
    ar.**
  - **CA18 no mesmo commit:** teste parametrizado provando que acento, emoji com
    ZWJ, `\n`, aspas e 1000 caracteres **continuam aceitos** e fazem round-trip
    verbatim. Sem ele, a restrição não tem prova de que é do tamanho da
    divergência, e nada impede que ela cresça depois.
- **Critério de aceite:**
  - CA16 (`InvalidNameError` para `\x00` em `Employee` e `JobFunction`, inclusive
    pela reidratação do mapper), CA17 (a suíte de lei exercita o NUL e **os dois
    parâmetros passam**), CA18 (os cinco adversariais continuam aceitos verbatim) e
    CA19 (`DayPeriod.from_string("xpto")` → `InvalidDayPeriodError`, que é
    `StaffError`).
  - A suíte de staff inteira verde, **sem** alteração de fixture existente — a
    varredura de §1 provou que nenhuma usa `\x00`.
  - Cobertura ≥ 90% nos quatro arquivos de `src/` tocados.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  uv run pytest tests/unit/features/staff/domain/ -v
  uv run pytest tests/contract/features/staff/ -v -k "nul or verbatim"
  make check
  ```
- **Commit sugerido:** `feat(staff): recusar byte NUL no nome e tipar a conversao de periodo do dia [3.4/task-02]`
  > **Exceção declarada ao critério de ≤ 5 arquivos** (PIPELINE §4.3): são 10, e as
  > duas correções são a **mesma** mudança lógica vista em quatro pontas — a
  > declaração (entidade/VO), o erro, o teste unitário e a suíte de contrato que
  > prova que fake e real concordam. Separá-las em duas Tasks deixaria a suíte de
  > contrato citando um erro que ainda não existe.

---

### Task 03 — os dez commands que atuam sobre registro existente ganham `unit_id`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/features/staff/application/dtos/commands.py`
  - `tests/unit/features/staff/application/test_dtos.py`
  - `tests/unit/features/staff/application/test_assign_job_functions.py`
  - `tests/unit/features/staff/application/test_copy_employee_to_unit.py`
  - `tests/unit/features/staff/application/test_delete_employee.py`
  - `tests/unit/features/staff/application/test_employee_edit_use_cases.py`
  - `tests/unit/features/staff/application/test_employee_lifecycle.py`
  - `tests/unit/features/staff/application/test_staff_flow.py`
  - `tests/unit/features/staff/application/test_terminated_employee_edits.py`
  - `tests/unit/features/staff/application/test_unavailability_use_cases.py`
- **O que fazer:** pôr a unidade no **pedido**, antes de pô-la no **endereço**. É a
  metade "expandir" da mudança de contrato: o campo passa a existir e a ser
  obrigatório, e a Task 04 o consome.
- **Detalhes técnicos:**
  - **`unit_id: UnitId` obrigatório** (sem default) nos **dez** commands do
    ADR 3.4.0007 §3: `RenameEmployeeCommand`, `AssignJobFunctionsCommand`,
    `ChangeWorkloadProfileCommand`, `DeclareShiftPreferenceCommand`,
    `RegisterUnavailabilityCommand`, `RemoveUnavailabilityCommand`,
    `DeactivateEmployeeCommand`, `ReactivateEmployeeCommand`,
    `DeleteEmployeeCommand` e `CopyEmployeeToUnitCommand`.
  - **Em `CopyEmployeeToUnitCommand`, `unit_id` é a unidade de ORIGEM**
    (`target_unit_id` já existia e é o destino). A docstring do command precisa
    dizer isso em uma linha — é o par em que confundir os dois campos produz
    exatamente a exfiltração cross-unidade que esta Stage fecha.
  - **`CreateEmployeeCommand` já carrega `unit_id`** (`commands.py:83`) e não muda.
    **As duas queries não mudam** — `ListEmployeesQuery` já o exige, e
    `ListJobFunctionsQuery` é tenant-scoped por desenho.
  - **Sem default, deliberadamente.** Um `unit_id: UnitId | None = None` faria o
    campo ser esquecível, e "omitir vira caminho de escalada" é a propriedade que o
    ADR 3.2.0002 já comprou para o tenant.
  - Nos nove arquivos de teste, a mudança é mecânica: cada construção dos dez
    commands ganha `unit_id=<a unidade do registro sob teste>`.
- **Critério de aceite:**
  - Os dez commands expõem `unit_id` obrigatório — metade "commands" do CA11.
  - A suíte de staff inteira verde. **Nenhum arquivo de `src/` além de
    `commands.py`** é tocado, e é o que prova que o campo ainda não tem consumidor
    (a Task 04 é quem o dá).
  - `test_dtos.py` cobre a obrigatoriedade (construir sem `unit_id` é `TypeError`)
    e a distinção origem × destino em `CopyEmployeeToUnitCommand`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/ -v
  git diff --name-only -- src/    # deve listar APENAS dtos/commands.py
  make check
  ```
- **Commit sugerido:** `feat(staff): os dez commands de registro existente passam a exigir a unidade [3.4/task-03]`
  > **Exceção declarada ao critério de ≤ 5 arquivos:** são 10, e nove são os
  > arquivos de teste que constroem os commands. A mudança lógica é **uma** (o
  > pedido passa a nomear a unidade); dividi-la por command produziria dez commits
  > sem valor de revisão.

---

### Task 04 — a unidade entra no endereço: port, use cases, fake, adapter Postgres e a suíte de contrato

- **Arquivos a criar:** nenhum
- **Arquivos a modificar (`src/`):**
  - `application/ports/out/employee_repository.py` — **a lei**
  - `application/use_cases/rename_employee.py`
  - `application/use_cases/assign_job_functions.py`
  - `application/use_cases/change_workload_profile.py`
  - `application/use_cases/declare_shift_preference.py`
  - `application/use_cases/register_unavailability.py`
  - `application/use_cases/remove_unavailability.py`
  - `application/use_cases/deactivate_employee.py`
  - `application/use_cases/reactivate_employee.py`
  - `application/use_cases/delete_employee.py`
  - `application/use_cases/copy_employee_to_unit.py`
  - `adapters/out/postgres/employee_repository.py`
- **Arquivos a modificar (`tests/`):**
  - `tests/fakes/features/staff/in_memory_employee_repository.py`
  - `tests/contract/features/staff/test_employee_repository_laws.py`
  - `tests/unit/features/staff/application/test_{assign_job_functions,copy_employee_to_unit,create_employee,delete_employee,employee_edit_use_cases,employee_lifecycle,list_employees,staff_repository_fakes,terminated_employee_edits,unavailability_use_cases}.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_employee_repository.py`
  - `tests/integration/features/staff/adapters/out/postgres/test_staff_conduct.py`

  > **Por que a suíte de integração está nesta lista, e por que ela quase não
  > esteve.** A §Premissas nomeia o alcance do `mypy` como a propriedade que decide
  > quais arquivos viajam juntos — e `make typecheck` é `mypy src/ tests/fakes/`,
  > **sem `tests/integration/`**. Aplicar a propriedade onde ela alcança e parar aí
  > deixa de fora justamente os arquivos onde o desalinhamento **não** vira erro de
  > tipo: vira `TypeError` em tempo de execução. Contagem medida dos call sites do
  > repositório de **funcionário** (os de função de trabalho não mudam):
  >
  > | Arquivo | `find_by_id` | `delete` | Total |
  > |---|---|---|---|
  > | `test_employee_repository.py` | 24 | 4 | **28** |
  > | `test_staff_conduct.py` | 3 | 0 | **3** |
  > | | | | **31** |
  >
  > `test_job_function_repository.py` e `test_schema.py` **não** entram: o primeiro
  > só toca o port de função (assinatura inalterada) e o único `find_by_id` do
  > segundo está dentro de uma docstring.
- **O que fazer:** fazer a unidade parte do **endereço** do funcionário até a
  assinatura do port, e reconciliar tudo que a assinatura alcança. É o coração da
  Stage: depois deste commit, registro de outra unidade do mesmo tenant é
  **inalcançável por construção**, e quem não sabe a unidade **não consegue formar
  a chamada**.
- **Detalhes técnicos, na ordem em que devem ser escritos:**
  1. **A lei, no `Protocol`** (ADR 3.4.0007 §1 e §4). As assinaturas passam a ser
     `find_by_id(tenant_id, unit_id, employee_id) -> Employee | None` e
     `delete(tenant_id, unit_id, employee_id) -> None`. As docstrings — que **são
     especificação** neste módulo — reescrevem **L-E2**, **L-E3** e **L-E5** sobre
     o endereço de três partes, e a **ordem de checagem normativa** do cabeçalho
     passa a dizer `(tenant_id, unit_id, id)`: lookup primeiro, ausente ⇒
     `EmployeeNotFoundError`, e só depois qualquer outra guarda. Registro de outra
     unidade é **não encontrado**, pela mesma regra que já valia para outro tenant
     — nenhum erro confirma existência de registro que o chamador não pode
     endereçar (concept 3.2 §5.4).
  2. **`L-E3` sobrevive com gatilho mais estreito** (ADR 3.4.0007 §5): a docstring
     de `update` passa a registrar que `EmployeeRelocationError` deixa de ser
     alcançável **pelos use cases** — que agora recarregam da mesma unidade em que
     escrevem — e permanece lei porque um segundo adapter de entrada poderia
     tentá-la. **Não remover a lei nem o erro.**
  3. **O fake carrega a mesma lei** — `in_memory_employee_repository.py` passa a
     casar `(tenant_id, unit_id, id)` nos dois métodos. É o ponto do ADR 3.4.0007
     §2: filtrar só no adapter deixaria o fake aceitando o que o real recusa.
  4. **O adapter Postgres** acrescenta `unit_id` ao `WHERE` de `find_by_id` e de
     `delete` (`employee_repository.py:178`, `:188`), **sem** mudar a ordem das
     checagens nem o `FOR UPDATE`/`REPEATABLE READ` que a 3.3 fixou.
  5. **Os dez use cases** passam `command.unit_id` ao port. `copy_employee_to_unit`
     usa a **origem** (`command.unit_id`) na leitura e `target_unit_id` na
     escrita — o único ponto onde os dois convivem.
  6. **`create_employee` e `list_employees` não mudam**: já endereçam por unidade
     (`add` grava a entidade, que carrega `unit_id`; `list_by_unit` já a exige).
     Com eles, são **doze** use cases de funcionário sob a lei — é o CA11.
  7. **A suíte de contrato** ganha os casos de CA9 nos dois parâmetros: registro
     criado na unidade A **não é encontrado** com `unit_id` da B, em `find_by_id`
     **e** em `delete`, e o erro é `EmployeeNotFoundError` — nunca um que confirme
     a existência. Um corpo de teste só, rodando `[fake]` e `[postgres]` (CA10).
  8. **Teste de não-regressão do endereço (CA11, metade "use cases"):** com o
     `store.calls` do fake, assere que cada use case chamou o port com **três**
     argumentos e com a unidade do command. Falha se algum voltar a resolver por
     `(tenant, id)`.
- **Critério de aceite:**
  - CA9, CA10 e CA11 verdes; a suíte de contrato prova a lei de unidade nos **dois**
    parâmetros com um corpo de teste só.
  - **Nenhum `skip`** na suíte de contrato — banco parado ⇒ suíte **falha**.
  - `make check` verde: mypy sobre `src/` e `tests/fakes/`, `lint-imports`,
    `layout-check` e a suíte inteira.
  - Cobertura ≥ 90% em cada arquivo de `src/` tocado.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  docker compose up -d postgres
  do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
  uv run mypy src/ tests/fakes/
  uv run pytest tests/contract/features/staff/ -v
  uv run pytest tests/unit/features/staff/ tests/integration/features/staff/ -v
  make check
  ```
- **Commit sugerido:** `feat(staff): a unidade entra no endereco do funcionario ate a assinatura do port [3.4/task-04]`
  > **Exceção declarada ao critério de ≤ 5 arquivos:** são **26** (12 em `src/`, 14
  > em `tests/`). Nenhum corte **por camada** deixa o commit verde — os três cortes
  > tentadores estão diagnosticados na caixa da §1. O corte **por método** (um commit
  > para `find_by_id`, outro para `delete`) **seria** verde, e está recusado lá por
  > **coesão**: é uma lei só, provada por um corpo de teste só. A mudança lógica é
  > **uma** (o endereço do funcionário ganha uma parte), e cada arquivo a recebe em
  > 1–3 linhas.
  >
  > **Sobre o critério 4 (não misturar port com adapter):** aqui não há criação de
  > port nem de adapter — os dois existem desde as Stages 3.2 e 3.3. O que o
  > critério protege (desenhar port e implementação no mesmo fôlego, deixando o SQL
  > moldar o contrato) está preservado pela **ordem de escrita** dos passos 1–4: a
  > lei primeiro, na docstring do `Protocol`; o SQL por último.

---

### Task 05 — port `AccessGuard` de staff: `AuthorizedScope`, as quatro leis, o fake e a guarda de `bc-independence`

- **Arquivos a criar:**
  - `src/restaurant_hub/features/staff/application/ports/out/access_guard.py`
  - `tests/fakes/features/staff/in_memory_access_guard.py`
  - `tests/unit/features/staff/application/test_access_guard_laws.py`
  - `tests/unit/features/staff/test_bc_independence.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** dar a staff um vocabulário próprio para pedir autorização, sem
  que nenhum módulo do BC saiba que `identity` existe. O port declara **o que staff
  precisa**; nunca **como identity decide**.
- **Detalhes técnicos:**
  - **Forma do port** (concept §4, ADR 3.4.0001 §1):

    ```python
    Actor = object   # credencial já verificada; staff não a interpreta

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

    **Entradas como `str` opaca** (regra literal do `identifiers.py` de staff e do
    contrato `bc-independence`); **saída** com os `NewType` de staff. O nome da
    permissão é `str` porque o vocabulário fechado vive em identity; os dois nomes
    que o Step 3 usa são `"manage_staff"` e `"manage_job_functions"`, e o port os
    cita na docstring como **valores**, jamais importando `Permission`.
  - **As quatro leis, na docstring do módulo** — sem elas uma segunda implementação
    satisfaz o tipo e destrói as propriedades de segurança sem falhar nenhum type
    check:
    - **L-AG1** — `authenticate` levanta quando não há credencial válida, e a
      exceção **sai crua**: o implementador não a traduz.
    - **L-AG2** — `authorize` levanta quando o ator não pode agir sobre o alvo, e
      a exceção **sai crua**, pela mesma razão.
    - **L-AG3** — `authorize` **nunca** devolve `AuthorizedScope` com `tenant_id`
      vazio ou ausente. Ator sem tenant é **negado**, não coagido para `""`:
      `TenantId` é `NewType` sem validação de runtime, então
      `TenantId(actor_tenant_id or "")` compilaria, passaria mypy strict e
      produziria consultas de tenant vazio.
    - **L-AG4** — `authorize` é chamado **uma vez por alvo**; autorizar um alvo
      não autoriza outro.
  - **Onde o port mora, e por quê** (ADR 3.4.0001 §4): `application/ports/out/`, e
    **não** dentro do adapter HTTP. O consumidor da Stage 3.6 é o router, o que
    argumentaria por `adapters/in/http/`; a colocação antecipa a Stage 3.5, cujo
    `IdentityGateway` é consumido por **use case**. A justificativa é o critério de
    escalabilidade progressiva do projeto, **não** LAYOUT §5 — que descreve port de
    saída como consumido por use case e ainda não é literalmente verdade aqui.
    **Esta frase precisa estar na docstring do módulo**, pelo mesmo princípio que
    esta Stage aplica a si mesma: não afirmar conformidade que não se tem.
  - **O fake** (`in_memory_access_guard.py`) é a **segunda implementação** que dá
    às leis o seu poder de refutação: credencial configurável, mapa de
    `(permissão, tenant, unidade)` autorizados, exceções-sentinela próprias e um
    **registro de chamadas** (mesma forma do `InMemoryStaffStore.record`) para
    L-AG4. `mypy tests/fakes/` já o verifica contra o `Protocol`.
  - **`test_access_guard_laws.py` (CA14):** um teste por lei, com o nome da lei no
    identificador (convenção das suítes de lei do Step 3) — L-AG1 e L-AG2 asserem
    **identidade do objeto levantado** (`excinfo.value is sentinela`, que é o que
    prova "sai crua"; `pytest.raises(TipoX)` sozinho não prova); L-AG3 assere
    recusa quando o ator não tem tenant, e que **nenhum** `AuthorizedScope`
    devolvido tem `tenant_id` falsy; L-AG4 assere uma chamada por alvo pelo
    registro.
  - **`test_bc_independence.py` (CA12 + CA13):** varredura por AST de **todos** os
    módulos sob `src/restaurant_hub/features/staff/` — nenhum importa
    `features.identity`, e nenhum **nomeia** `Role` ou `Permission` (a segunda
    metade importa: um `Literal["manage_staff"]` é aceitável, um import do enum
    não). E leitura do `.importlinter`: a seção
    `[importlinter:contract:bc-independence]` **não tem** chave `ignore_imports`
    — o teste falha se a lista aparecer. A forma é a do
    `test_composition_root_staff.py`, que já faz varredura por AST.
- **Critério de aceite:**
  - CA12, CA13 e CA14 verdes; `lint-imports` verde.
  - `mypy src/ tests/fakes/` limpo — o fake satisfaz o `Protocol` estruturalmente.
  - Cobertura ≥ 90% em `access_guard.py`.
  - **Nada em `features/staff/` importa `features/identity/`**, e o `.importlinter`
    segue com **zero** supressão em `bc-independence`.
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/application/test_access_guard_laws.py -v
  uv run pytest tests/unit/features/staff/test_bc_independence.py -v
  uv run lint-imports
  uv run mypy src/ tests/fakes/
  make check
  ```
- **Commit sugerido:** `feat(staff): port AccessGuard com as quatro leis e o fake que as prova [3.4/task-05]`
  > **Exceção declarada ao critério 4 de Task Atômica** (não misturar criação de
  > port com criação de implementação): o **fake** é implementação do port. É a
  > mesma exceção da Task 04 da Stage 3.3 e da Task 02 da 2.3, pela mesma razão
  > mecânica — publicar leis num `Protocol` sem uma implementação que as obedeça
  > deixaria as leis sem refutação por um commit inteiro. O que o critério protege
  > de verdade — desenhar port e implementação **de produção** no mesmo fôlego —
  > está preservado: **o tradutor é a Task 06.**

---

### Task 06 — o tradutor sobre `IdentityGuard` no composition root, e a prova de que nenhuma rota nasceu

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/restaurant_hub/composition_root.py`
  - `tests/unit/features/staff/adapters/test_composition_root_staff.py`
- **O que fazer:** montar a implementação de produção do `AccessGuard` **no único
  módulo que já importa os dois bounded contexts por desenho**, fechando a Stage
  sem nenhuma supressão de import — e travar por teste que a Stage não publicou
  superfície.
- **Detalhes técnicos:**
  - **O tradutor é definido no próprio `composition_root.py`** (ADR 3.4.0001 §3).
    A alternativa — um adapter em `features/staff/adapters/out/identity/` — caiu na
    medição do ADR: `IdentityGuard` vive sob o pacote `in`, keyword Python, então o
    adapter não conseguiria sequer **anotar** o objeto que embrulha, e a supressão
    seriam **três** pares de `ignore_imports`, não um. Aqui são **zero**.
  - **Ele embrulha o MESMO `IdentityGuard`** que já é construído em
    `wire_dependencies` (linha 299) e exposto como `identity_guard` — não um
    segundo grafo. É metade do CA15, e o teste assere identidade de objeto.
  - **Tradução de `authorize`:** `permission: str` → `Permission(permission)`;
    `tenant_id`/`unit_id` `str` → os `NewType` de identity; o `AuthorizedActor`
    devolvido → `AuthorizedScope`.
  - **L-AG3 no tradutor:** se `AuthorizedActor.actor_tenant_id` for `None` (hoje só
    `platform_admin`), o tradutor **nega** — nunca `TenantId(... or "")`. Ver a
    entrada `[decision]` da §7 sobre qual exceção usar.
  - **L-AG1/L-AG2 no tradutor:** `authenticate` e `authorize` **não** têm
    `try/except`. Toda exceção de identity sobe crua — é o que fará a faixa 401/403
    da Stage 3.6 ser byte-idêntica à de identity.
  - **`ApplicationDependencies` ganha `staff_access_guard: AccessGuard`**, anotado
    com o **port** e não com a classe concreta: é o campo cujo tipo precisa ser
    abstrato, ao contrário dos campos de use case (o docstring do contêiner explica
    a assimetria).
  - **`build_http_wiring` NÃO muda.** Não há router de staff a registrar, e é
    exatamente o que o CA21 trava.
  - **Testes** em `test_composition_root_staff.py`:
    - **CA15** — `deps.staff_access_guard` satisfaz `AccessGuard`; o
      `IdentityGuard` que ele embrulha **é** (`is`) `deps.identity_guard`; e as
      asserções mecânicas já existentes (os 16 use cases sobre os adapters
      Postgres, nada instanciando adapter fora do composition root) seguem verdes.
    - **CA21** — o diretório `src/restaurant_hub/features/staff/adapters/in/`
      **não existe**, e `build_http_wiring(deps).router` é o router de identity —
      único registrado. Assim a promessa "nenhuma rota nasce aqui" é verificada,
      não afirmada.
- **Critério de aceite:**
  - CA15 e CA21 verdes; `make check` verde.
  - `bc-independence` sem supressão (o teste da Task 05 continua verde).
  - Cobertura ≥ 90% em `composition_root.py`.
  - `uv run uvicorn restaurant_hub.main:app` sobe — o grafo montado não quebrou o
    boot (é a verificação funcional da §3).
- **Comando de verificação:**
  ```powershell
  $env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
  uv run pytest tests/unit/features/staff/adapters/test_composition_root_staff.py -v
  uv run pytest tests/unit/test_bootstrap.py tests/e2e/ -v
  uv run python -c "from restaurant_hub.composition_root import wire_dependencies; d = wire_dependencies(); print(type(d.staff_access_guard).__name__)"
  make check
  ```
- **Commit sugerido:** `feat(staff): montar o tradutor do AccessGuard sobre o IdentityGuard no composition root [3.4/task-06]`

## 2.1 Matriz de rastreabilidade

**Regra:** nada órfão nos dois sentidos — todo critério, lei e ADR de fundação tem
ao menos uma Task que o entrega, e nenhuma Task existe sem item que a justifique.

### Critérios de aceite do concept §11 → Task

| Critério | Task(s) | Onde o check acontece |
|---|---|---|
| CA1 — as duas permissões existem; mapa de papéis continua **total** | **01** | `test_role_permission.py::test_mapa_de_permissoes_e_total_sobre_todos_os_papeis` (já existente) |
| CA2 — `owner`/`manager`/`hr` detêm as duas; `employee`/`platform_admin` nenhuma | **01** | teste parametrizado sobre os cinco papéis |
| CA3 — `hr` e `manager` com conjuntos de staff **idênticos** | **01** | teste dedicado, falha se alguém os separar sem ADR |
| CA4 — unit-scoped com `MANAGE_JOB_FUNCTIONS` sem unidade é **autorizado** | **01** | `test_authorize_action.py` (ramo verdadeiro da condição nova) |
| CA5 — unit-scoped com `MANAGE_STAFF` sem unidade → `UnitScopeRequiredError` | **01** | `test_authorize_action.py` (ramo falso) |
| CA6 — `TENANT_WIDE_PERMISSIONS` == `{MANAGE_JOB_FUNCTIONS}`, lista explícita | **01** | `test_role_permission.py` |
| CA7 — `MANAGE_STAFF` **não** está no conjunto | **01** | idem — mata a mutação de alcance cross-unidade |
| CA8 — passos 3 e 5 inalterados, inclusive para permissão tenant-wide | **01** | `test_authorize_action.py` |
| CA9 — registro da unidade A não é encontrado com unidade B (`find_by_id` **e** `delete`) | **04** | suíte de contrato de funcionário |
| CA10 — CA9 provado nos **dois** lados com um corpo de teste só | **04** | `pytest -v` mostrando `[fake]` e `[postgres]` |
| CA11 — dez commands carregam `unit_id`; doze use cases o repassam | **03** (commands) + **04** (use cases) | `test_dtos.py` + asserção sobre `store.calls` |
| CA12 — nada em `features/staff/` importa `features.identity` nem nomeia `Role`/`Permission` | **05** | `test_bc_independence.py` (AST) + `lint-imports` |
| CA13 — `bc-independence` sem nenhum `ignore_imports` | **05** | `test_bc_independence.py` lê o `.importlinter` |
| CA14 — L-AG1…L-AG4 testadas contra uma **segunda** implementação | **05** | `test_access_guard_laws.py` contra o fake |
| CA15 — tradutor montado sobre o **mesmo** `IdentityGuard`; teste mecânico verde | **06** | `test_composition_root_staff.py` (`is`) |
| CA16 — `\x00` rejeitado em `Employee` e `JobFunction`, **inclusive na reidratação** | **02** | `tests/unit/features/staff/domain/` |
| CA17 — a suíte de lei exercita o NUL e **fake e Postgres concordam** | **02** | suíte de contrato, `[fake]` **e** `[postgres]` |
| CA18 — acento, ZWJ, `\n`, aspas, 1000 chars continuam aceitos verbatim | **02** | teste parametrizado (prova que a restrição não cresceu) |
| CA19 — `DayPeriod.from_string("xpto")` → `InvalidDayPeriodError` (`StaffError`) | **02** | `test_shift_preference.py` + `test_exceptions.py` |
| CA20 — nenhuma asserção de **decisão de acesso** muda; fixtures de fechamento com aditividade **provada** (critério refinado — §1) | **01** | `test_rbac_additivity.py` (as duas asserções de subconjunto, mecânicas) + `git diff -- tests/unit/features/identity/` + as duas fixtures nominadas no commit |
| CA21 — nenhuma rota nasce; sem `features/staff/adapters/in/` | **06** | `test_composition_root_staff.py` + §3 |
| CA22 — `make check` verde | **todas** + §3 | comando de verificação de cada Task |
| CA23 — cobertura ≥ 90% em cada arquivo novo/tocado | **todas** + §3 | `--cov-report=term-missing` lido arquivo a arquivo |

### Leis novas ou alteradas → Task que as entrega

| Lei | Estado | Task | Provada onde |
|---|---|---|---|
| **L-E2** `update` é `UPDATE` | **reescrita** sobre o endereço de três partes | **04** | contrato, nos dois parâmetros |
| **L-E3** localização imutável | **reescrita** — gatilho mais estreito, lei preservada (ADR 3.4.0007 §5) | **04** | contrato, nos dois parâmetros |
| **L-E5** remoção guardada | **reescrita** — `delete` exige a unidade | **04** | contrato, nos dois parâmetros |
| **L-E1, L-E4, L-E6, L-E7, L-JF1…L-JF5, `L-ORD`** | **inalteradas** — consumidas | — | suítes de contrato da 3.3 seguem verdes (não-regressão) |
| **L-AG1** exceção de autenticação sai crua | **nova** | **05** (declarada + fake) | `test_access_guard_laws.py`; tradutor sem `try/except` na **06** |
| **L-AG2** exceção de autorização sai crua | **nova** | **05** | idem |
| **L-AG3** `tenant_id` nunca vazio; ator sem tenant é negado | **nova** | **05** (declarada) + **06** (tradutor a cumpre) | `test_access_guard_laws.py` + `test_composition_root_staff.py` |
| **L-AG4** uma autorização por alvo | **nova** | **05** | registro de chamadas do fake |
| **Nome sem byte NUL** (invariante de `Employee`/`JobFunction`) | **nova** — restrição de contrato de domínio | **02** | unit + contrato nos dois parâmetros |
| **Dispensa de unidade por permissão tenant-wide** | **nova** — condição do passo 4 | **01** | `test_authorize_action.py`, os dois ramos |

### ADRs de fundação desta Stage → Task que os efetiva

| ADR | O que decide | Task(s) |
|---|---|---|
| **3.4.0001** — port `AccessGuard` de staff, tradutor no composition root | §1 port e vocabulário, §2 as quatro leis, §4 colocação em `ports/out/` | **05** |
| | §3 implementação montada no composition root, zero `ignore_imports` | **06** (com a guarda de CA13 na **05**) |
| **3.4.0003** — byte NUL recusado no domínio; `DayPeriod.from_string` | §1–§4 (o §5 "identity não é tocada" é `[finding]`, não Task) | **02** |
| **3.4.0006** — duas permissões e `hr` ≡ `manager` em staff | §2 paridade, §4 as duas permissões e o mapa, §3 restrição para frente registrada no `role.py` | **01** |
| **3.4.0007** — a unidade entra no endereço do funcionário | §3 os dez commands | **03** |
| | §1 assinatura, §2 lei de port e não SQL, §4 ordem de checagem, §5 `L-E3`, §6 expansão declarada | **04** |
| **3.4.0008** — permissão tenant-wide dispensa o escopo de unidade | §1 o conjunto, §2 a condição do passo 4, §3 por permissão nunca por papel, §4 passos 3 e 5 intactos, §5 totalidade é teste | **01** |

**Os três ADRs da Stage 3.6 (3.4.0002 mapa de status, 3.4.0004 sem paginação,
3.4.0005 cópia repetida) não têm Task aqui, e é o correto** — decididos nesta
Stage, executados na 3.6 (concept §13). Se alguma Task deste plano os citasse como
entregável, seria escopo vazado.

### Decisões de §7 do concept sem ADR → Task

| Decisão | Task |
|---|---|
| **D6** — o corte, e a fronteira com a 3.6 | processo; já registrada na nota datada do `roadmap.md` |
| **D7** — sem `gate_mode: batch` | §3 (Checkpoints A/B/C completos, sem alívio) |

## 3. Gate de saída da Stage

### Verificações automatizadas

```powershell
$env:PATH += ";C:\msys64\usr\bin"; $env:UV_SYSTEM_CERTS="1"
docker compose up -d postgres          # o gate exige banco real (ADR 2.3.0001), sem skip
do { Start-Sleep -Seconds 1; docker compose exec -T postgres pg_isready -q } while ($LASTEXITCODE -ne 0)
make check                             # lint + typecheck + layout + import + lock + docs + testes com cobertura
uv run pytest tests/ --cov=src/restaurant_hub --cov-report=term-missing
uv run python scripts/check_technical_postexec.py docs/stages/3.4-staff-access-scope/technical.md
git diff --name-only (git merge-base origin/develop HEAD) HEAD -- src/   # cobertura por arquivo tocado
```

### Verificações funcionais

- [ ] **Nenhuma rota nova** — `build_http_wiring(deps)` registra **só** o router de
      identity, e `src/restaurant_hub/features/staff/adapters/in/` não existe
      (CA21).
- [ ] **A app sobe** — `uv run uvicorn restaurant_hub.main:app` inicia com o
      `staff_access_guard` montado; o grafo de dependências não quebrou o boot.
- [ ] **A suíte de contrato roda contra o banco real** — o output mostra `[fake]`
      **e** `[postgres]` para cada lei; com o container **parado**, a suíte
      **falha** (não pula).
- [ ] **O escopo de unidade é inalcançável por omissão** — não existe forma de
      chamar `find_by_id`/`delete` sem nomear a unidade (verificação por
      assinatura, não por convenção).
- [ ] **Nenhuma migration nova** — `git diff --name-only origin/develop..HEAD --
      migrations/` vazio.

### Checklist de fechamento da Stage

- [ ] Todas as 6 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] **CA20 nas duas metades** — `git diff -- tests/unit/features/identity/` sem
      edição fora das duas fixtures de fechamento, e as duas nominadas no commit da
      Task 01 (o critério refinado vive no concept §11; o achado que o produziu,
      na §7 deste documento)
- [ ] Cobertura ≥ 90% global **e** em cada arquivo de `src/` tocado
- [ ] Auditoria de Testes com todos os itens "sim"
- [ ] Checkpoints A, B e C executados, com todos os achados dispostos
- [ ] §7 deste documento reflete a execução real
- [ ] `[finding]` escalados têm Stage candidata identificada (os sete do concept
      §10 + os que a execução produzir)
- [ ] Commit final `stage 3.4: complete` aplicado
- [ ] `roadmap.md` atualizado: Stage `3.4-staff-access-scope` em `status: done`,
      `updated_at` e `last_reviewed_at` na data do merge
- [ ] ADRs `3_4_0001`–`3_4_0008` seguem em `status: accepted`
- [ ] `concept.md` não precisa de retoque retrospectivo (se precisar por causa de
      CA20, é regressão declarada, não silêncio)

## 4. Ordem de dependência entre Tasks

```
Task 01 (identity: permissões + passo 4) ───────────────┐
                                                        │
Task 02 (staff domain: NUL + DayPeriod) ──► Task 04     │
                                             ▲          │
Task 03 (commands +unit_id) ─────────────────┘          │
                                                        ▼
Task 05 (port AccessGuard + leis + fake) ─────────► Task 06 (tradutor + wiring)
```

- **02 → 04:** a suíte de contrato de funcionário é tocada nas duas; com o domínio
  já recusando o NUL, a Task 04 mexe num arquivo cuja asserção nova já é verde.
- **03 → 04:** os use cases da 04 leem `command.unit_id`, que a 03 criou. Invertê-las
  faria a 04 alterar `commands.py` **e** o port no mesmo commit, sem ganho.
- **01 → 06:** o tradutor converte `str` em `Permission`; os dois nomes que o Step 3
  usa precisam existir para o teste de wiring ser mais do que sintático.
- **05 → 06:** critério 4 de Task Atômica — port antes do seu adapter de produção.
- **01, 02, 03 e 05 são mutuamente independentes.** A ordem entre elas é de leitura
  (do vocabulário de acesso para o escopo, e do escopo para o port), não de
  compilação.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| A Task 04 é grande e a tentação de dividi-la reaparece durante a execução | Os três cortes **por camada** estão diagnosticados como vermelhos na caixa da §1, e o corte **por método** está lá reconhecido como verde e recusado por **coesão** — a decisão já foi tomada, não é para retomá-la na Fase 4. Se aparecer um corte verde **ainda não catalogado**, **PARE e registre**: é achado sobre o plano, não licença |
| Um teste de use case constrói o command sem `unit_id` e passa por acidente na 03 | `unit_id` é **obrigatório sem default**: construir sem ele é `TypeError` na coleta. É o teste que falha, não o silêncio |
| A cobertura de branch cair no passo 4 do guard (condição de três termos) | CA4 e CA5 são os dois ramos, e o projeto mede **branch coverage** (`branch = true`). Se o `term-missing` apontar ramo faltante, cobrir — nunca justificar |
| O tradutor coagir `tenant_id` para `""` sem que nada reclame | L-AG3 tem teste contra o fake (Task 05) **e** asserção no wiring (Task 06). Se aparecer um caminho em que o ator sem tenant chega ao `AuthorizedScope`, é **blocker**, não ajuste |
| Postgres da worktree anterior retido na porta, e a Stage testar contra infra alheia | `docker ps` antes do gate; a limpeza é no **setup** de cada suíte (convenção do projeto), não no teardown |
| A metade "obrigatório" do CA20 virar licença para editar qualquer asserção de identity que atrapalhe | A aditividade é **provada, não afirmada**: nenhum membro removido de `Permission`, nenhum papel perdendo permissão, e só as duas fixtures de fechamento nominadas no commit. Edição fora delas é **achado**, e o `git diff` da §3 a expõe |
| A execução inventar migration por causa do texto do ADR 3.3.0006 | §Premissas e a verificação funcional da §3: `git diff -- migrations/` **vazio**. O texto do ADR já está reconciliado na nota do `roadmap.md` |
| A execução tentar resolver algum `[finding]` da 3.6 (mapa de status, paginação, cópia repetida) | A matriz §2.1 declara que os três ADRs da 3.6 **não têm Task aqui**; qualquer arquivo em `adapters/in/` reprova CA21 |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (§4 contratos, §5
  invariantes, §11 critérios, §13 fronteira com a 3.6)
- [`../../roadmap.md`](../../roadmap.md) — bloco `3.4-staff-access-scope` e a nota
  datada de 2026-08-12 (o corte e as reconciliações)
- [`../../overview.md`](../../overview.md) §3, §6, §9
- [`../../domain/staff/workforce.md`](../../domain/staff/workforce.md) §3.1, §3.2, §4
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §1 (idioma do código), §4
  (commits), §6 (tamanho de Stage)
- [`../../LAYOUT.md`](../../LAYOUT.md) §3 (dependências), §6 (composition root), §8
  (o pacote `in`)
- [`../../PIPELINE.md`](../../PIPELINE.md) §4.3 (Task Atômica)
- Stages precedentes: [`../3.2-staff-application/concept.md`](../3.2-staff-application/concept.md)
  (leis dos ports), [`../3.3-staff-persistence/technical.md`](../3.3-staff-persistence/technical.md)
  (§7 byte NUL; a promoção da suíte de contrato),
  [`../2.4-identity-http/technical.md`](../2.4-identity-http/technical.md) (a Stage
  que construiu o guard que esta estende)
- **ADRs de fundação desta Stage:** [`3.4.0001`](../../adr/3_4_0001-staff-owned-access-guard-port.md),
  [`3.4.0003`](../../adr/3_4_0003-reject-nul-byte-in-staff-domain-names.md),
  [`3.4.0006`](../../adr/3_4_0006-staff-rbac-two-permissions-and-hr-parity.md),
  [`3.4.0007`](../../adr/3_4_0007-unit-enters-the-employee-address.md),
  [`3.4.0008`](../../adr/3_4_0008-tenant-wide-permissions-exempt-from-unit-scope.md)
- **ADRs decididos aqui e executados na 3.6** (fora do escopo deste plano):
  `3.4.0002`, `3.4.0004`, `3.4.0005`
- ADRs consumidos: 2.1.0001, 2.2.0002, 2.3.0001, 2.3.0003, 2.3.0005, 2.4.0001,
  2.4.0003, 3.1.0001, 3.1.0002, 3.1.0006, 3.2.0002, 3.2.0003, 3.2.0006, 3.2.0007,
  3.3.0002, 3.3.0003, 3.3.0004, 3.3.0006, 3.3.0007
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `composition-root`,
  `pytest-with-fakes`, `repository-pattern`, `import-linter-rules`
- **Issue [#40](https://github.com/MarceloSanC/restaurant-hub/issues/40)** (esta
  Stage); issue #41 (habilitação de função por unidade — alicerçada aqui, não
  implementada)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
>
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão. Apenas após a decisão, registre a entrada
> abaixo. Na dúvida sobre se algo é "pequeno o suficiente para decidir
> sozinho", **pergunte**.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo inclui
  "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

> **As três entradas de 2026-08-17 são PRÉ-execução, e isso é deliberado.** O
> cabeçalho acima descreve a §7 como preenchida durante/após a Fase 4; estas
> nasceram na Fase 3B, antes da Task 01. Elas podem estar aqui porque o gate
> reservado `stage 3.4: technical approved` **ainda não existe** — sem ele,
> `check_technical_postexec.py` não tem baseline com que comparar e não arma o
> freeze (script §2, "sem commit de aprovação ⇒ nada a comparar"). Consequência
> prática: as três **fazem parte da baseline aprovada**, não são desvios sobre
> ela. As entradas da Fase 4 virão depois destas, e aí sim sob o freeze.

---

### 2026-08-17 — [decision] Fase 3B — exceção que o tradutor levanta ao cumprir L-AG3 — Claude

**Contexto:** L-AG3 exige que o ator sem tenant seja **negado**, não coagido para
`TenantId("")`. O concept e o ADR 3.4.0001 fixam a **propriedade** (negar) mas não
o **tipo de exceção**, e o único ator sem tenant hoje (`platform_admin`) já seria
negado antes, no passo 2 do guard, por não deter nenhuma das duas permissões novas.
**Pergunta:** que exceção o tradutor levanta nesse caminho?
**Opções:**
- A — exceção nova, de staff, no módulo do port.
- B — `PermissionDeniedError` de identity, levantada pelo tradutor. ✅ recomendada
**Decisão:** B.
**Razão:** trivial e sem alternativa real de desenho, ancorada em princípio
existente: L-AG2 exige que a exceção de autorização **saia crua** para que a faixa
403 da Stage 3.6 tenha corpo constante. Uma exceção nova de staff produziria uma
faixa de erro distinta para um caminho que é, semanticamente, "este ator não pode
agir sobre este alvo". `PermissionDeniedError` mora em identity e é levantada no
composition root, que já importa os dois BCs — `bc-independence` intacto.

---

### 2026-08-17 — [decision] Fase 3B — onde mora o teste de `bc-independence` de staff — Claude

**Contexto:** CA12 e CA13 são varreduras sobre o BC **inteiro** (todos os módulos
de `features/staff/` + o arquivo `.importlinter`), e não sobre uma camada. O
espelho de `tests/unit/features/staff/` é por camada
(`domain/`, `application/`, `adapters/`), então nenhuma delas é o lugar natural.
**Decisão:** `tests/unit/features/staff/test_bc_independence.py`, na raiz do pacote
de testes da feature.
**Razão:** trivial e sem alternativa real. Pô-lo dentro de `application/`
afirmaria que a regra é da camada application, o que é falso — ela vale para o BC
inteiro. **É analogia, não precedente literal, e a distinção importa:**
`tests/unit/test_bootstrap.py` ocupa a raiz de `tests/unit/` por ser transversal
às camadas; o arquivo proposto ocupa a raiz de `tests/unit/features/staff/`, que
hoje só tem `__init__.py`. O raciocínio é o mesmo (teste de regra transversal sobe
ao nível cuja fronteira a regra descreve), mas **abre um slot novo** naquele nível
em vez de ocupar um já usado. Nada valida caminhos sob `tests/` — `check_layout.py`
só olha `src/` —, então a escolha é de convenção, e fica declarada aqui em vez de
implícita.

---

### 2026-08-17 — [finding] Fase 3B — a inferência do CA20 tem falso positivo para teste de fechamento — Claude (achado **corrigido** nesta Stage)

**Contexto:** CA20 do concept §11 — e o 5º bullet do `definition_of_done` do bloco
3.4 do `roadmap.md`, que carregava o **mesmo texto** — exigiam que a suíte de
identity passasse *"sem alteração de asserção"*. Medição em
`tests/unit/features/identity/domain/test_role_permission.py`: a linha 27 assere o
conjunto **exato** dos valores do enum `Permission`, e as linhas 66–78 parametrizam
o conjunto **exato** de permissões por papel. Acrescentar duas permissões e
concedê-las a três papéis **exige** editar as duas.

**O achado:** a inferência *"asserção mudou ⟹ a mudança não foi aditiva"* tem falso
positivo para teste de **fechamento** — que existe justamente para exigir
atualização consciente quando o conjunto cresce legitimamente (o mecanismo que o
ADR 3.4.0008 §5 pede). A cláusula *"é achado, não ajuste"* do próprio CA20 mandava
tratar o caso assim: **o critério disparou como projetado.**

**Disposição: corrigido** (não escalado, não devolvido) — regressão de
CONVENTIONS §3.2, porque CA20 é **critério de aceite** e porque a §7 de um
technical não pode emendar um critério do concept sem inverter a hierarquia
Concept > Technical. Commits: `c3523f5` (revert to draft), `e64f95e`
(`stage 3.4: conceptual approved`, com CA20 refinado + nota datada com este
achado), `9c4a30f` (reconciliação do DoD do roadmap, que carregava o mesmo texto).
**O conjunto de comportamentos protegidos é o mesmo; mudou a formulação.**

---

### 2026-08-17 — [deviation] Task 01 — a fixture de fechamento de vocabulário são TRÊS, não duas — Claude

**Contexto:** a §1 (*"O achado do CA20"*) mediu **duas** fixtures de fechamento em
`tests/unit/features/identity/`, ambas em `domain/test_role_permission.py`. Ao
rodar a Task 01, uma terceira reprovou:
`adapters/test_http_dependencies.py::test_conjunto_de_permissoes_exigidas_por_papel_alvo`
(3 dos 5 parâmetros: `manager`, `hr`, `owner`). Ela assere o retorno de
`required_permissions_for_role`, que é **derivado** do mapa de papéis
(`frozenset({MANAGE_USERS}) | target_role.permissions`, `dependencies.py:97`) — logo
cresce sozinho toda vez que o vocabulário cresce. A medição da Fase 3B varreu
`domain/`, não o BC inteiro; é a mesma classe de erro que a §1 já nomeia sobre o
alcance do `mypy` (aplicar a propriedade onde ela alcança e parar aí).

**Ajuste aplicado:** os três parâmetros foram atualizados, e o arquivo
`tests/unit/features/identity/adapters/test_http_dependencies.py` entrou no commit
da Task 01 **fora** da lista de "arquivos a modificar" do plano.

**Por que é `[deviation]` e não achado bloqueante de CA20.** O critério refinado
(concept §11) proíbe mudar **decisão de acesso** e obriga as fixtures de
**fechamento de vocabulário** a acompanharem o conjunto. Esta é da segunda classe,
e a prova foi feita **mecanicamente, não por prosa**: o mesmo commit acrescenta
`test_matriz_de_quem_cria_quem_nao_regride`, com a matriz "quem pode criar quem"
congelada no valor **anterior** à Stage e asserida por **igualdade** (não
subconjunto — aqui encolher e crescer são ambos regressão). A matriz é idêntica
antes e depois: as duas permissões novas são detidas por `owner`, `manager` e `hr`
simultaneamente, então exigi-las a mais nunca retira alcance de quem já o tinha. O
sentido da mudança é fail-closed (o conjunto exigido só cresce), e a derivação
passar a cobrir as capacidades novas sozinha é o desenho de `dependencies.py`
funcionando.

**Consequência para o gate de saída:** o item da §3 que lê *"`git diff --
tests/unit/features/identity/` sem edição fora das **duas** fixtures de
fechamento"* deve ser lido como **três**, nominadas no corpo do commit da Task 01
junto das outras duas. O conjunto de comportamentos protegidos não mudou.

---

### 2026-08-17 — [decision] Task 02 — `InvalidNameError` ganha um `reason` opcional — Claude

**Contexto:** o ADR 3.4.0003 manda **reutilizar** `InvalidNameError` para o byte
NUL (*"a dedicated error class would fragment the 422 band"*), e o plano seguiu.
Mas a mensagem do erro é fixa: `"nome de {entity} não pode ser vazio"`. Aplicada a
um nome que **tem** conteúdo e só carrega um `\x00`, ela descreve o defeito errado
— e é essa mensagem que a Stage 3.6 devolve no corpo do 422.

**Pergunta:** reusar a mensagem existente, ou dar ao erro um motivo variável?
**Opções:**
- A — manter a mensagem única; o 422 diz "não pode ser vazio" para um nome não-vazio.
- B — `reason: str = "não pode ser vazio"` como segundo parâmetro opcional. ✅ recomendada
**Decisão:** B.
**Razão:** reversível-barata e **ancorada**: a disciplina que este Step vem
policiando é a de não afirmar o que não é verdade, e A produz exatamente uma
afirmação falsa na superfície que o usuário lê. O default preserva byte a byte
todas as mensagens existentes — nenhuma asserção de suíte anterior muda —, o erro
continua **um só** (a faixa 422 do ADR 3.4.0003 não fragmenta) e o mapa de status
da 3.6 não ganha entrada nova. `test_exceptions.py` trava as duas mensagens.

---

### 2026-08-17 — [deviation] Task 02 — a reidratação do mapper entra no commit — Claude

**Contexto:** CA16 exige o NUL rejeitado *"em **todos** os caminhos de construção,
**inclusive a reidratação do mapper**"*. A lista de arquivos da Task 02 cobre as
entidades, os erros, os testes de domínio e as duas suítes de contrato — mas não
`tests/unit/features/staff/adapters/test_mappers.py`, que é onde o caminho do
mapper é exercitado. Com a lista literal, a metade "reidratação" do critério
ficaria provada por **argumento** (*"a validação está em `__post_init__`, logo o
mapper a herda"*) e não por teste.

**Ajuste aplicado:** um teste novo,
`test_ca16_byte_nul_na_linha_levanta_ao_ser_lido_nas_duas_entidades`, cobrindo
`row_to_job_function` e `row_to_employee`. É **puramente aditivo** — nenhum teste
existente do arquivo foi renomeado, reparametrizado ou teve asserção alterada.

**Razão:** o argumento é verdadeiro, mas "afirmar conformidade sem verificar" é a
classe de defeito que esta Stage inteira existe para fechar, e o critério nomeia a
reidratação de propósito. O custo é um teste; o risco evitado é um
`object.__setattr__` futuro no lugar do construtor apagando a garantia sem quebrar
nada.

---

### 2026-08-17 — [deviation] Task 04 — o teste de CA11 não pôde nascer dentro do `store.calls` — Claude

**Contexto:** o passo 8 dos detalhes técnicos da Task 04 pede *"com o `store.calls`
do fake, assere que cada use case chamou o port com **três** argumentos e com a
unidade do command"*. Medido na execução: `InMemoryStaffStore.record` recebe uma
**`str` nua** e `calls` é `list[str]`
(`tests/fakes/features/staff/in_memory_staff_store.py:54-58`) — ele registra o
**nome** do método, nunca os argumentos. Enriquecer a string gravada (p.ex.
`"employees.find_by_id(t,u,e)"`) quebraria as asserções de **igualdade e
pertinência exata** sobre `calls` espalhadas por nove suítes
(`test_job_function_use_cases.py:136`, `test_staff_repository_fakes.py:93`,
`test_delete_job_function.py:93`, entre outras) — e `in_memory_staff_store.py`
**não está** na lista de arquivos da Task 04.

**Ajuste aplicado:** a metade "use cases" de CA11 virou **duas** provas, ambas
dentro dos arquivos listados:

- **comportamental (10 testes, todos os dez use cases)** — o command endereça uma
  unidade **alheia** (`_U2`) para um registro gravado em `_U1`; o resultado tem de
  ser `EmployeeNotFoundError` **e** `fakes.store.calls[antes:] == ["employees.find_by_id"]`.
  A asserção de conduta é a peça que discrimina: um use case que voltasse a
  resolver por `(tenant, id)` **encontraria** o registro e a lista traria também
  `employees.update` / `employees.delete`. Distribuídos por
  `test_assign_job_functions.py` (1), `test_delete_employee.py` (1),
  `test_copy_employee_to_unit.py` (1), `test_employee_edit_use_cases.py` (3,
  parametrizado), `test_employee_lifecycle.py` (2) e
  `test_unavailability_use_cases.py` (2).
- **mecânica (aridade e ordem)** — `test_ca11_o_endereco_do_funcionario_tem_tres_partes_na_assinatura`
  em `test_staff_repository_fakes.py`, por `inspect.signature`, sobre o `Protocol`
  **e** sobre o fake: `["self", "tenant_id", "unit_id", "employee_id"]`. É a metade
  "três argumentos" do passo 8, e ela **ganha valor** justamente pela propriedade
  que a §1 nomeia: `mypy` não alcança `tests/integration/`, e uma asserção que roda
  na suíte alcança.

**Razão:** o alvo do passo 8 é *"falha se algum voltar a resolver por
`(tenant, id)`"*, e as duas provas juntas o cumprem com margem — verificado por
**mutação**, não por leitura: removida a comparação de unidade do fake, os 10
testes comportamentais reprovam (os 2 de assinatura passam, corretamente, porque
não dependem da implementação); removida também do `WHERE` do adapter, 8 dos 10
testes de CA9 da suíte de contrato reprovam nos dois parâmetros. O caminho
alternativo — mudar a forma de `record()` — trocaria uma prova por uma regressão
em nove suítes, e tocaria arquivo fora da lista.

**Nenhum arquivo fora da lista da Task 04 foi tocado:** o commit fecha em
**exatamente** os 26 previstos (12 em `src/`, 14 em `tests/`).

<!-- END: post-execution -->

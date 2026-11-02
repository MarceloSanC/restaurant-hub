"""Port de saída: persistência de registros de funcionário.

**As docstrings deste módulo são especificação, não comentário.** Cada método
cita a lei nomeada do concept §4 da Stage 3.2 (L-E1…L-E7) **+ `L-ORD`
(ADR 3.3.0003, Stage 3.3)** que o governa e o erro que levanta — é o texto que a
Stage 3.3 implementa em Postgres e que o teste de contrato de lá pareia lei a
lei (ADR 2.3.0003).

**`L-ORD` — ordem total, determinística e independente de ambiente.** Duas
cláusulas, uma para a listagem e outra para dentro do agregado:

- **`list_by_unit`** devolve os registros ordenados por `name` e, em empate, por
  `id` — comparação **byte a byte** (codepoint), que em Postgres é
  `ORDER BY name COLLATE "C", id COLLATE "C"` e em Python é
  `sorted(…, key=lambda e: (e.name, e.id))`, medidos como **idênticos**. O
  desempate por `id` não é zelo: nome de funcionário **não é único** — homônimos
  são legítimos (concept 3.1 §5.2) —, então sem ele a ordem não é total, e ordem
  não-total pagina duplicando e omitindo linhas na Stage 3.4. As duas colunas
  levam a colação explícita porque `COLLATE` liga-se ao operando à sua esquerda:
  um `id` sem ela volta a depender da colação do banco, justamente no termo que
  a paginação usa como cursor.
- **`find_by_id` e `list_by_unit`** — os dois métodos que montam agregado —
  reidratam `Employee.unavailabilities` ordenadas por `start`. É ordem **total
  por funcionário** porque períodos do mesmo registro não se sobrepõem, logo o
  início é único dentro do agregado.

`shift_preference` e `job_function_ids` são `frozenset`: **sem ordem, sem lei**.

A lei vale para as **duas** implementações — o fake in-memory ordena igual, e a
lei não se relaxa para acomodá-lo (precedente literal do ADR 2.3.0003). É isso
que permite à suíte de contrato ter **um** corpo de teste só.

**Escopo de tenant na assinatura** (ADR 3.2.0002), e a listagem exige também a
**unidade**: não existe listagem tenant-wide de funcionário. A ausência é
deliberada — é o que torna impossível **por assinatura** a consulta que vazaria
unidades (workforce §3.1).

**O endereço do funcionário tem três partes** (ADR 3.4.0007, Stage 3.4):
`(tenant_id, unit_id, id)`. `find_by_id` e `delete` **exigem a unidade**, e isso
é **lei do port**, não filtro de SQL do adapter: quem não sabe a unidade **não
consegue formar a chamada**, e as duas implementações carregam a mesma regra.
Pôr o filtro apenas no `WHERE` do Postgres deixaria o fake in-memory aceitando o
que o real recusa — a divergência fake ≢ real que este Step já pagou uma vez
sobre o byte NUL, agora sobre um invariante de **segurança**. É por ser
assinatura que a suíte de contrato prova os dois lados com **um** corpo só.

`update` **não** recebe a unidade em separado: a entidade já a carrega, e é a
comparação entre a unidade da entidade e a gravada que L-E3 guarda.
`exists_by_job_function` segue **tenant-wide por desenho** — a guarda de remoção
conta referências em **qualquer** unidade (workforce §3.2).

**Ordem de checagem, normativa** (concept §4/L-E3 e §5.4, com a unidade dobrada
no primeiro passo pelo ADR 3.4.0007 §4): todo método que recebe `tenant_id`
resolve **primeiro** o lookup — por `(tenant_id, unit_id, id)` onde a assinatura
traz a unidade, por `(tenant_id, id)` em `update` — ausente ⇒
`EmployeeNotFoundError`, e só **depois** avalia qualquer outra guarda
(divergência de `unit_id`, conjunto de funções, referências). Invertê-la faz o
port responder um erro que **confirma a existência de registro de outro
tenant**. Pela mesma regra, registro que existe em **outra unidade do mesmo
tenant** é **não encontrado**: nenhum erro confirma a existência de registro que
o chamador não pode endereçar.

**Não há `exists_by_name`**, e a ausência é declaração: nome de funcionário
**não** é único — homônimos são legítimos (concept 3.1 §5.2).
"""

from typing import Protocol

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)


class EmployeeRepository(Protocol):
    """Contrato de persistência da raiz de agregado `Employee`."""

    def add(self, employee: Employee) -> None:
        """Persiste um registro novo.

        **L-E1 — é inserção, não upsert.** Id já gravado ⇒
        `EmployeeAlreadyExistsError`, com escopo **global** do id (na 3.3 o id é
        a chave primária — mesma razão de `JobFunctionRepository.add`).

        **L-E4 — validade referencial.** Toda id de `employee.job_function_ids`
        precisa existir **no mesmo tenant**; alguma ausente (ou existente em
        outro tenant) ⇒ `JobFunctionNotFoundError`, e nada é gravado. Sem esta
        lei, uma função removida entre a checagem do use case e a gravação faria
        o adapter da 3.3 bater na FK `RESTRICT` e levantar um erro **não
        previsto pelo contrato** — que a 3.4 converteria em 500. Com ela, a
        corrida termina no mesmo erro tipado do caminho comum.
        """
        ...

    def update(self, employee: Employee) -> None:
        """Grava o agregado **inteiro** de um registro existente.

        **L-E2 — é `UPDATE`, não upsert.** Registro inexistente **no tenant** ⇒
        `EmployeeNotFoundError`, e **nada** é gravado. Aqui o lookup é por
        `(tenant_id, id)`, e **não** pelo endereço de três partes: a unidade
        vem dentro da entidade, e compará-la com a gravada é **exatamente** o
        que a L-E3 faz no passo seguinte. Escopar o lookup pela unidade
        recebida converteria toda relocalização em `EmployeeNotFoundError` e
        apagaria a L-E3 do contrato. Grava nome, perfil,
        preferência, conjunto de funções, indisponibilidades **e estado** — as
        entidades são `frozen` e as transições devolvem nova instância, então
        não há mutação in-place que a persistência pudesse observar.

        **L-E3 — localização imutável.** `unit_id` divergente do gravado,
        **no mesmo tenant** ⇒ `EmployeeRelocationError`. A lei tem erro nomeado
        de propósito: sem ele a saída seria gravar o que veio (mover o registro
        em silêncio) ou gravar o que estava (descartar a escrita em silêncio), e
        as duas são corrupção silenciosa. O único caminho para existir em outra
        unidade é a cópia.

        **A L-E3 é sobre `unit_id`, dentro do mesmo tenant — não sobre
        `tenant_id`.** Tenant divergente não é relocalização: é o registro
        **não existir** naquele escopo, e §5.4 é mais alta e vence
        (`EmployeeNotFoundError`). Daí a ordem fixa: lookup por
        `(tenant_id, id)` **antes** da comparação de `unit_id`. Invertê-la
        vazaria a existência do registro alheio justamente no caso em que as
        duas divergem.

        **A L-E3 sobrevive com gatilho mais estreito** (ADR 3.4.0007 §5). Desde
        a Stage 3.4 os use cases recarregam o registro **da mesma unidade em
        que escrevem** — o endereço de três partes de `find_by_id` —, então
        nenhum caminho de use case consegue mais entregar aqui uma entidade com
        unidade divergente: `EmployeeRelocationError` deixa de ser alcançável
        **por eles**. A lei e o erro **permanecem**, e não são removidos: um
        segundo adapter de entrada (CLI, worker, importador) monta a entidade
        sozinho e ainda pode tentá-la, e é o port — não o use case — que
        responde por ela.

        **L-E4** vale aqui igual ao `add`.
        """
        ...

    def link_login(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId, user_id: UserId
    ) -> None:
        """Grava o vínculo de login do registro — **só** se ainda não houver um.

        **`L-LINK` — escrita própria e condicional do vínculo** (issue #68,
        ADR 0.0.0010). O vínculo é "definido uma vez" (ADR 3.5.0004 §2), e essa
        regra vale aqui sobre o estado **gravado**, não sobre uma entidade lida
        antes: a checagem e a escrita são **uma** operação atômica. É o que
        impede que um segundo R17 concorrente troque o vínculo em silêncio — a
        metade "dois R17" da janela "última escrita vence sobre `user_id`" do
        concept 3.5 §6.4.

        Endereço de **três** partes (ADR 3.4.0007) e ordem de checagem
        normativa, a mesma de `Employee.assert_can_link_login`:

        1. inexistente **no endereço** `(tenant_id, unit_id, id)` ⇒
           `EmployeeNotFoundError` — registro de outra unidade ou de outro
           tenant é indistinguível de inexistente;
        2. já vinculado **no gravado** ⇒ `EmployeeAlreadyHasLoginError`, e o
           vínculo gravado fica intacto (vinculado vence desligado);
        3. desligado **no gravado** ⇒ `TerminatedEmployeeLoginError`.

        Em qualquer erro, **nada** é gravado. Nenhum outro campo do registro é
        tocado: o vínculo tem escrita própria justamente para não carregar um
        agregado inteiro, possivelmente desatualizado.
        """
        ...

    def delete(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId) -> None:
        """Remove o registro **definitivamente** — o oposto de desligar.

        **L-E5 — remoção guardada, no endereço de três partes.** Inexistente
        **no par `(tenant_id, unit_id)`** ⇒ `EmployeeNotFoundError`;
        **referenciado por qualquer registro de outro agregado** ⇒
        `EmployeeInUseError`.

        Registro que existe em **outra unidade do mesmo tenant** é **não
        encontrado** — mesmo erro, mesma mensagem que o de outro tenant já
        recebia (ADR 3.4.0007 §4). A distinção seria justamente o que confirma
        a existência de um registro que o chamador não pode endereçar.

        Em v1 **nada referencia** o registro de funcionário, então a segunda
        metade é vacuamente satisfeita: o erro e a lei existem porque o
        **Step 4** (alocação) é quem os preenche, e publicá-los agora evita que
        a 3.4/Step 4 retroajam o contrato do port. Declarado, não fingido — a
        suíte da Task 06 fixa a **ausência** de produtor em v1.
        """
        ...

    def find_by_id(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId
    ) -> Employee | None:
        """Devolve o registro **do tenant e da unidade**, ou `None`.

        O endereço é `(tenant_id, unit_id, id)` (ADR 3.4.0007 §1). Registro que
        existe em **outra unidade do mesmo tenant** devolve `None`, pela mesma
        regra que já valia para outro tenant: o resultado não distingue "não
        existe" de "existe onde você não alcança".

        Não filtra por estado: o **desligado continua endereçável por id**
        (ADR 3.2.0006) — ele some da listagem default, não do sistema.

        **`L-ORD` —** `unavailabilities` vem ordenada por `start`.
        """
        ...

    def list_by_unit(
        self, tenant_id: TenantId, unit_id: UnitId, *, include_inactive: bool = False
    ) -> tuple[Employee, ...]:
        """Lista os registros de **uma** unidade.

        **L-E6 —** exige a unidade e devolve **apenas ativos** por default;
        `include_inactive=True` é opt-in explícito. Não existe listagem
        tenant-wide de funcionário nesta Stage, e essa ausência é o que torna a
        consulta que vazaria unidades irrepresentável.

        **`L-ORD` —** ordenado por `name`, desempatando por `id`, byte a byte;
        e cada agregado devolvido tem `unavailabilities` ordenada por `start`.
        """
        ...

    def exists_by_job_function(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> bool:
        """Diz se **algum** registro do tenant referencia a função.

        **L-E7 —** é a consulta que sustenta a guarda de remoção (L-JF3): é
        **global no tenant** (qualquer unidade) e conta registros **ativos e
        inativos**. Referência de **outro** tenant devolve `False`.

        Atravessar unidades aqui não fura "nenhuma operação de staff atravessa
        unidades implicitamente" (workforce §3.1): aquela invariante protege
        **dados de funcionário**, e esta consulta devolve um **booleano sobre
        uma função**, que é tenant-scoped — não expõe registro, unidade nem
        contagem. A guarda **tem** de ser tenant-wide porque a função é: uma
        referência em qualquer unidade impede a remoção.
        """
        ...

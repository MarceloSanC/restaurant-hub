"""Port de saída: persistência de registros de funcionário.

**As docstrings deste módulo são especificação, não comentário.** Cada método
cita a lei nomeada do concept §4 (L-E1…L-E7) que o governa e o erro que levanta
— é o texto que a Stage 3.3 implementa em Postgres e que o teste de contrato de
lá pareia lei a lei (ADR 2.3.0003).

**Escopo de tenant na assinatura** (ADR 3.2.0002), e a listagem exige também a
**unidade**: não existe listagem tenant-wide de funcionário. A ausência é
deliberada — é o que torna impossível **por assinatura** a consulta que vazaria
unidades (workforce §3.1).

**Ordem de checagem, normativa** (concept §4/L-E3 e §5.4): todo método que
recebe `tenant_id` resolve **primeiro** o lookup por `(tenant_id, id)` — ausente
⇒ `EmployeeNotFoundError` — e só **depois** avalia qualquer outra guarda
(divergência de `unit_id`, conjunto de funções, referências). Invertê-la faz o
port responder um erro que **confirma a existência de registro de outro
tenant**.

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
        `EmployeeNotFoundError`, e **nada** é gravado. Grava nome, perfil,
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

        **L-E4** vale aqui igual ao `add`.
        """
        ...

    def delete(self, tenant_id: TenantId, employee_id: EmployeeId) -> None:
        """Remove o registro **definitivamente** — o oposto de desligar.

        **L-E5 — remoção guardada.** Inexistente **no tenant** ⇒
        `EmployeeNotFoundError`; **referenciado por qualquer registro de outro
        agregado** ⇒ `EmployeeInUseError`.

        Em v1 **nada referencia** o registro de funcionário, então a segunda
        metade é vacuamente satisfeita: o erro e a lei existem porque o
        **Step 4** (alocação) é quem os preenche, e publicá-los agora evita que
        a 3.4/Step 4 retroajam o contrato do port. Declarado, não fingido — a
        suíte da Task 06 fixa a **ausência** de produtor em v1.
        """
        ...

    def find_by_id(self, tenant_id: TenantId, employee_id: EmployeeId) -> Employee | None:
        """Devolve o registro **do tenant**, ou `None` se não existir nele.

        Não filtra por estado: o **desligado continua endereçável por id**
        (ADR 3.2.0006) — ele some da listagem default, não do sistema.
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

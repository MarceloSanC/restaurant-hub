"""Fake in-memory de `EmployeeRepository` — visão de funcionários do store do par.

Implementa as sete leis L-E1…L-E7 do concept §4 **e a `L-ORD`** (ADR 3.3.0003,
Stage 3.3). A **ordem de checagem** é normativa e está codificada aqui: o lookup
vem **antes** de qualquer outra guarda. Invertê-la faria o port responder um erro
que confirma a existência de registro de outro tenant (§5.4) — e é o único
defeito desta classe que passaria despercebido, porque o teste "erro certo no
tenant certo" continuaria verde.

**O endereço tem três partes desde a Stage 3.4** (ADR 3.4.0007): `find_by_id` e
`delete` resolvem por `(tenant_id, unit_id, id)`, e este fake carrega a mesma lei
que o adapter Postgres — **é o ponto do ADR §2**. Filtrar a unidade só no `WHERE`
do real deixaria este fake aceitando o que o real recusa, e a suíte de contrato,
que roda **um corpo só** contra os dois, não teria como expressar a diferença.
Sobre um invariante de **segurança**, essa divergência é estritamente pior do que
sobre um detalhe de armazenamento.

`update` continua resolvendo por `(tenant_id, id)`: a unidade vem dentro da
entidade, e compará-la com a gravada **é** a L-E3. Escopar o lookup do `update`
pela unidade recebida transformaria toda relocalização em `EmployeeNotFoundError`
e apagaria a lei — por isso `_find` (tenant + id) e `_find_no_endereco`
(tenant + unidade + id) são dois métodos, e não um.

**Sobre a ordenação (`L-ORD`), e por que ela é mais que um `sorted` na
listagem.** O `sorted()` do Python sobre `str` compara por **codepoint**, medido
como **idêntico** a `ORDER BY name COLLATE "C", id COLLATE "C"` no Postgres — é
essa coincidência que permite à suíte de contrato ter um corpo só. Mas há um
segundo ponto, e é o que inverte a direção habitual da divergência: este fake
guarda o agregado **inteiro** como foi entregue, e `Employee.add_unavailability`
**não** ordena (ele concatena). Sem reordenar na leitura, seria o **fake** a
reprovar CA11 enquanto o Postgres passaria, porque lá a ordem vem do
`ORDER BY start_at` do adapter. A reordenação usa `dataclasses.replace`, que
passa pelo `__post_init__` como uma construção direta passaria.
"""

import dataclasses

from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    EmployeeNotFoundError,
    EmployeeRelocationError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from tests.fakes.features.staff.in_memory_staff_store import InMemoryStaffStore


def _com_periodos_ordenados(employee: Employee) -> Employee:
    """`L-ORD` — `unavailabilities` sai por `start`, que é único no agregado.

    Total por funcionário: períodos do mesmo registro não se sobrepõem, logo
    não há empate a desempatar.
    """
    ordenados = tuple(sorted(employee.unavailabilities, key=lambda periodo: periodo.start))
    if ordenados == employee.unavailabilities:
        return employee
    return dataclasses.replace(employee, unavailabilities=ordenados)


class InMemoryEmployeeRepository:
    """Visão de funcionários do `InMemoryStaffStore` compartilhado."""

    def __init__(self, store: InMemoryStaffStore) -> None:
        self._store = store

    # --- escrita -------------------------------------------------------------

    def add(self, employee: Employee) -> None:
        """L-E1 (inserção, id global) + L-E4 (validade referencial do conjunto)."""
        self._store.record("employees.add")
        if employee.id in self._store.employees:
            raise EmployeeAlreadyExistsError(employee.id)
        self._guard_job_functions(employee)
        self._store.employees[employee.id] = employee

    def update(self, employee: Employee) -> None:
        """L-E2 (`UPDATE`, não upsert) + L-E3 (localização imutável) + L-E4.

        A ordem das três é o contrato, não detalhe: existência no tenant,
        depois unidade, depois conjunto de funções.
        """
        self._store.record("employees.update")
        # (1) Lookup por (tenant_id, id). Precede a comparação de unidade
        # DE PROPÓSITO: com tenant alheio o registro simplesmente não existe
        # naquele escopo, e responder EmployeeRelocationError confirmaria a
        # existência do registro de outro restaurante (§5.4 vence a L-E3).
        gravado = self._find(employee.tenant_id, employee.id)
        if gravado is None:
            raise EmployeeNotFoundError(employee.id)
        # (2) Localização imutável — erro INTRA-tenant.
        if gravado.unit_id != employee.unit_id:
            raise EmployeeRelocationError(employee.id, gravado.unit_id, employee.unit_id)
        # (3) Validade referencial do conjunto.
        self._guard_job_functions(employee)
        self._store.employees[employee.id] = employee

    def link_login(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId, user_id: UserId
    ) -> None:
        """`L-LINK` — o vínculo, só se o **gravado** ainda não tiver um (issue #68).

        Endereço de três partes primeiro; depois as guardas sobre o **gravado**,
        pela própria transição do domínio: `link_login` passa por
        `assert_can_link_login`, então a precedência vinculado > desligado tem
        **uma** casa, e este fake não a reescreve. Só `user_id` muda — o resto
        do agregado é o que já estava gravado.
        """
        self._store.record("employees.link_login")
        gravado = self._find_no_endereco(tenant_id, unit_id, employee_id)
        if gravado is None:
            raise EmployeeNotFoundError(employee_id)
        self._store.employees[employee_id] = gravado.link_login(user_id)

    def delete(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId) -> None:
        """L-E5 — remoção definitiva guardada, no endereço de três partes.

        Registro de **outra unidade do mesmo tenant** é `EmployeeNotFoundError`,
        idêntico ao de outro tenant (ADR 3.4.0007 §4).

        A guarda de referências **não tem produtor em v1**: nada referencia o
        registro de funcionário no escopo atual. Quem a preenche é o Step 4
        (alocação), pela FK da 3.3 — a lei e o `EmployeeInUseError` existem
        agora para que a 3.4/Step 4 não precisem retroagir o contrato do port.
        """
        self._store.record("employees.delete")
        if self._find_no_endereco(tenant_id, unit_id, employee_id) is None:
            raise EmployeeNotFoundError(employee_id)
        del self._store.employees[employee_id]

    # --- leitura -------------------------------------------------------------

    def find_by_id(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId
    ) -> Employee | None:
        """Registro do tenant **e da unidade**, ou `None`. **Não filtra por
        estado**: o desligado continua endereçável por id (ADR 3.2.0006).

        Registro de outra unidade do mesmo tenant devolve `None` — o resultado
        não distingue "não existe" de "existe onde você não alcança".

        `L-ORD` — `unavailabilities` sai ordenada por `start`.
        """
        self._store.record("employees.find_by_id")
        employee = self._find_no_endereco(tenant_id, unit_id, employee_id)
        if employee is None:
            return None
        return _com_periodos_ordenados(employee)

    def list_by_unit(
        self, tenant_id: TenantId, unit_id: UnitId, *, include_inactive: bool = False
    ) -> tuple[Employee, ...]:
        """L-E6 — só a unidade pedida, só ativos por default.

        `L-ORD` — ordenado por `(name, id)`, e cada agregado devolvido tem
        `unavailabilities` ordenada por `start`.
        """
        self._store.record("employees.list_by_unit")
        selecionados = (
            _com_periodos_ordenados(employee)
            for employee in self._store.employees.values()
            if employee.tenant_id == tenant_id
            and employee.unit_id == unit_id
            and (include_inactive or employee.active)
        )
        return tuple(sorted(selecionados, key=lambda registro: (registro.name, registro.id)))

    def exists_by_job_function(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> bool:
        """L-E7 — global no tenant, contando ativos **e** inativos."""
        self._store.record("employees.exists_by_job_function")
        return any(
            employee.tenant_id == tenant_id and job_function_id in employee.job_function_ids
            for employee in self._store.employees.values()
        )

    # --- internos ------------------------------------------------------------

    def _find(self, tenant_id: TenantId, employee_id: EmployeeId) -> Employee | None:
        """Lookup por `(tenant_id, id)` — espelha o `WHERE tenant_id = … AND id = …`.

        **Só o `update` o usa**, e de propósito: é ele quem precisa enxergar o
        registro cuja unidade diverge da recebida, para poder levantar
        `EmployeeRelocationError` em vez de `EmployeeNotFoundError` (L-E3).
        """
        employee = self._store.employees.get(employee_id)
        if employee is None or employee.tenant_id != tenant_id:
            return None
        return employee

    def _find_no_endereco(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId
    ) -> Employee | None:
        """Lookup pelo endereço de três partes — espelha o `WHERE` do adapter.

        `find_by_id` e `delete` resolvem por aqui (ADR 3.4.0007 §1): registro de
        outra unidade do mesmo tenant é **indistinguível de inexistente**.
        """
        employee = self._find(tenant_id, employee_id)
        if employee is None or employee.unit_id != unit_id:
            return None
        return employee

    def _guard_job_functions(self, employee: Employee) -> None:
        """L-E4 — toda id do conjunto existe **no mesmo tenant**.

        Id existente em outro tenant conta como **ausente**: a resolução é
        escopada, e a alternativa vazaria a existência da função alheia.
        A iteração é ordenada para que a id reportada seja determinística
        quando falta mais de uma.
        """
        for job_function_id in sorted(employee.job_function_ids):
            job_function = self._store.job_functions.get(job_function_id)
            if job_function is None or job_function.tenant_id != employee.tenant_id:
                raise JobFunctionNotFoundError(job_function_id)


_conforms: EmployeeRepository = InMemoryEmployeeRepository(InMemoryStaffStore())

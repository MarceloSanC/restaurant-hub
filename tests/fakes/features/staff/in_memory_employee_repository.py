"""Fake in-memory de `EmployeeRepository` — visão de funcionários do store do par.

Implementa as sete leis L-E1…L-E7 do concept §4. A **ordem de checagem** é
normativa e está codificada aqui: lookup por `(tenant_id, id)` **antes** de
qualquer outra guarda. Invertê-la faria o port responder um erro que confirma a
existência de registro de outro tenant (§5.4) — e é o único defeito desta classe
que passaria despercebido, porque o teste "erro certo no tenant certo"
continuaria verde.
"""

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
)
from tests.fakes.features.staff.in_memory_staff_store import InMemoryStaffStore


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

    def delete(self, tenant_id: TenantId, employee_id: EmployeeId) -> None:
        """L-E5 — remoção definitiva guardada.

        A guarda de referências **não tem produtor em v1**: nada referencia o
        registro de funcionário no escopo atual. Quem a preenche é o Step 4
        (alocação), pela FK da 3.3 — a lei e o `EmployeeInUseError` existem
        agora para que a 3.4/Step 4 não precisem retroagir o contrato do port.
        """
        self._store.record("employees.delete")
        if self._find(tenant_id, employee_id) is None:
            raise EmployeeNotFoundError(employee_id)
        del self._store.employees[employee_id]

    # --- leitura -------------------------------------------------------------

    def find_by_id(self, tenant_id: TenantId, employee_id: EmployeeId) -> Employee | None:
        """Registro do tenant, ou `None`. **Não filtra por estado**: o desligado
        continua endereçável por id (ADR 3.2.0006)."""
        self._store.record("employees.find_by_id")
        return self._find(tenant_id, employee_id)

    def list_by_unit(
        self, tenant_id: TenantId, unit_id: UnitId, *, include_inactive: bool = False
    ) -> tuple[Employee, ...]:
        """L-E6 — só a unidade pedida, só ativos por default."""
        self._store.record("employees.list_by_unit")
        return tuple(
            employee
            for employee in self._store.employees.values()
            if employee.tenant_id == tenant_id
            and employee.unit_id == unit_id
            and (include_inactive or employee.active)
        )

    def exists_by_job_function(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> bool:
        """L-E7 — global no tenant, contando ativos **e** inativos."""
        self._store.record("employees.exists_by_job_function")
        return any(
            employee.tenant_id == tenant_id and job_function_id in employee.job_function_ids
            for employee in self._store.employees.values()
        )

    # --- internos ------------------------------------------------------------

    def _find(self, tenant_id: TenantId, employee_id: EmployeeId) -> Employee | None:
        """Lookup por `(tenant_id, id)` — espelha o `WHERE tenant_id = … AND id = …`."""
        employee = self._store.employees.get(employee_id)
        if employee is None or employee.tenant_id != tenant_id:
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

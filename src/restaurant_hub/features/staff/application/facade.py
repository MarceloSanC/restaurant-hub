"""Fachada de leitura de staff — o *Open Host Service* in-process para outros bounded contexts.

**É o único módulo de staff que outro BC pode importar** (LAYOUT §3, ADR 3.5.0001): o
contrato `bc-independence` nomeia o par
`scheduling.adapters.out.staff.* -> staff.application.facade` (Stage 4.4, ADR 4.4.0004), e
qualquer outro import de staff a partir de scheduling continua reprovando.

Três propriedades a definem:

1. **Assinaturas e retornos em primitivos.** Entram `str` e `frozenset[str]`; saem
   dataclasses congeladas de `str`, `bool`, `Decimal`, `datetime` e tuplas. O consumidor
   nunca nomeia `Employee`, `JobFunction`, `WorkloadProfile` nem os ids tipados de staff.
2. **Não autoriza.** O use case consumidor (scheduling) já autorizou a leitura com
   permissão de scheduling (ADR 4.3.0003 › "Served by a non-authorizing staff facade"). Por
   isso a fachada lê os **repositórios** de staff e não os use cases, que autorizam com
   ator e permissão de staff (ADR 3.7.0001). Não traduz exceção.
3. **Nunca cruza unidade nem tenant.** Toda leitura de registro passa pela listagem da
   unidade (`list_by_unit`), e o catálogo pela do tenant (`list_by_tenant`): os únicos
   métodos usados, que a Stage 3.11 não muda de assinatura. O vínculo de login filtra a
   unidade aqui (concept 4.4 §7 D-USERID) e o `user_id` não sai na resposta.

Montada uma vez, no `composition_root`, sobre as **mesmas** instâncias de repositório que
servem as rotas de staff.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import TenantId, UnitId
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule


@dataclass(frozen=True)
class StaffRecord:
    """Um registro de funcionário em primitivos.

    Attributes:
        employee_id: o registro.
        unit_id: a unidade do registro.
        name: o nome atual.
        active: se o registro está ativo.
        job_function_ids: as funções que o registro detém.
        weekly_hours: carga semanal contratada; `None` = perfil sob demanda.
        unavailabilities: os pares `(start, end)` ingênuos de indisponibilidade.
    """

    employee_id: str
    unit_id: str
    name: str
    active: bool
    job_function_ids: frozenset[str]
    weekly_hours: Decimal | None
    unavailabilities: tuple[tuple[datetime, datetime], ...]


@dataclass(frozen=True)
class StaffFunction:
    """Uma função do catálogo do tenant, em primitivos."""

    job_function_id: str
    name: str


def _record(employee: Employee) -> StaffRecord:
    profile = employee.workload_profile
    return StaffRecord(
        employee_id=str(employee.id),
        unit_id=str(employee.unit_id),
        name=employee.name,
        active=employee.active,
        job_function_ids=frozenset(str(fid) for fid in employee.job_function_ids),
        weekly_hours=profile.weekly_hours if isinstance(profile, FixedSchedule) else None,
        unavailabilities=tuple((period.start, period.end) for period in employee.unavailabilities),
    )


class StaffReadFacade:
    """As leituras de staff que outro BC pode fazer, sem autorizar."""

    def __init__(self, employees: EmployeeRepository, job_functions: JobFunctionRepository) -> None:
        self._employees = employees
        self._job_functions = job_functions

    def _unit_employees(
        self, tenant_id: str, unit_id: str, *, include_inactive: bool
    ) -> tuple[Employee, ...]:
        return self._employees.list_by_unit(
            TenantId(tenant_id), UnitId(unit_id), include_inactive=include_inactive
        )

    def list_active_records(self, tenant_id: str, unit_id: str) -> tuple[StaffRecord, ...]:
        """Os registros ativos da unidade."""
        employees = self._unit_employees(tenant_id, unit_id, include_inactive=False)
        return tuple(_record(employee) for employee in employees)

    def list_records(
        self, tenant_id: str, unit_id: str, employee_ids: frozenset[str]
    ) -> tuple[StaffRecord, ...]:
        """Os registros pedidos que são da unidade, ativos ou não; os demais são omitidos."""
        if not employee_ids:
            return ()
        employees = self._unit_employees(tenant_id, unit_id, include_inactive=True)
        return tuple(_record(employee) for employee in employees if employee.id in employee_ids)

    def list_records_of_user(
        self, tenant_id: str, unit_id: str, user_id: str
    ) -> tuple[StaffRecord, ...]:
        """Os registros da unidade vinculados ao login, ativos ou não."""
        employees = self._unit_employees(tenant_id, unit_id, include_inactive=True)
        return tuple(
            _record(employee)
            for employee in employees
            if employee.user_id is not None and employee.user_id == user_id
        )

    def list_functions(self, tenant_id: str) -> tuple[StaffFunction, ...]:
        """O catálogo de funções do tenant."""
        return tuple(
            StaffFunction(job_function_id=str(function.id), name=function.name)
            for function in self._job_functions.list_by_tenant(TenantId(tenant_id))
        )

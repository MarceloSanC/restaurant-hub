"""Adapter de saída: `StaffReadPort` implementado sobre a fachada de leitura de staff.

**A aresta scheduling → staff** (ADR 4.4.0004; LAYOUT §3 "Travessia entre bounded
contexts"). Este módulo é o único de scheduling autorizado a importar staff, e importa **um**
módulo dela — `restaurant_hub.features.staff.application.facade` —, pelo par nomeado no
contrato `bc-independence` do `.importlinter`. Qualquer outro import de staff, aqui ou em
outro módulo de scheduling, reprova `lint-imports` e `test_bc_independence.py`.

O que o adapter faz é **tradução de vocabulário**: os primitivos da fachada viram os tipos
de scheduling (`StaffMember`, `JobFunctionEntry`, `UnavailabilityWindow`, os ids próprios do
BC). Não nomeia o vocabulário de decisão de staff — nem entidade, nem perfil de jornada.

Não autoriza: o use case de scheduling já autorizou a leitura com permissão de scheduling
(ADR 4.3.0003), e a fachada não autoriza. Não traduz exceção: nenhuma das leituras tem
falha de negócio — id que não é da unidade é omitido (L-ST3).
"""

from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
    StaffMember,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.application.facade import StaffReadFacade, StaffRecord


def _member(record: StaffRecord) -> StaffMember:
    return StaffMember(
        employee_id=EmployeeId(record.employee_id),
        unit_id=UnitId(record.unit_id),
        display_name=record.name,
        active=record.active,
        job_function_ids=frozenset(JobFunctionId(fid) for fid in record.job_function_ids),
        contracted_weekly_hours=record.weekly_hours,
        unavailabilities=tuple(
            UnavailabilityWindow(start=start, end=end) for start, end in record.unavailabilities
        ),
    )


class LocalStaffReadAdapter:
    """O `StaffReadPort` sobre a `StaffReadFacade`, no mesmo processo."""

    def __init__(self, facade: StaffReadFacade) -> None:
        self._facade = facade

    def list_active_members(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[StaffMember, ...]:
        return tuple(_member(r) for r in self._facade.list_active_records(tenant_id, unit_id))

    def list_members(
        self, tenant_id: TenantId, unit_id: UnitId, employee_ids: frozenset[EmployeeId]
    ) -> tuple[StaffMember, ...]:
        records = self._facade.list_records(
            tenant_id, unit_id, frozenset(str(eid) for eid in employee_ids)
        )
        return tuple(_member(r) for r in records)

    def list_members_of_user(
        self, tenant_id: TenantId, unit_id: UnitId, user_id: str
    ) -> tuple[StaffMember, ...]:
        records = self._facade.list_records_of_user(tenant_id, unit_id, user_id)
        return tuple(_member(r) for r in records)

    def list_job_functions(self, tenant_id: TenantId) -> tuple[JobFunctionEntry, ...]:
        return tuple(
            JobFunctionEntry(job_function_id=JobFunctionId(f.job_function_id), name=f.name)
            for f in self._facade.list_functions(tenant_id)
        )

"""Fake in-memory do `StaffReadPort` — semeável e com registro de chamadas.

Obedece L-ST1…L-ST5 (suíte de contrato). `calls` registra cada leitura, para os testes
de "nenhum port tocado antes da autorização".
"""

from dataclasses import dataclass, field

from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
    StaffMember,
    StaffReadPort,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    TenantId,
    UnitId,
)


@dataclass
class InMemoryStaffRead:
    """Registros por (tenant, unidade), vínculo de login e catálogo por tenant."""

    calls: list[str] = field(default_factory=list)
    _members: dict[tuple[str, str, str], StaffMember] = field(default_factory=dict)
    _users: dict[tuple[str, str, str], str] = field(default_factory=dict)
    _catalog: dict[str, dict[str, JobFunctionEntry]] = field(default_factory=dict)

    # --- semeadura (fora do port) ------------------------------------------------

    def add_member(self, tenant_id: str, member: StaffMember, user_id: str | None = None) -> None:
        """Grava (ou substitui) o registro; `user_id` vincula um login."""
        chave = (tenant_id, member.unit_id, member.employee_id)
        self._members[chave] = member
        if user_id is not None:
            self._users[chave] = user_id

    def remove_member(self, tenant_id: str, unit_id: str, employee_id: str) -> None:
        """Remove o registro — reproduz a remoção definitiva em staff (registro ausente)."""
        self._members.pop((tenant_id, unit_id, employee_id), None)
        self._users.pop((tenant_id, unit_id, employee_id), None)

    def add_job_function(self, tenant_id: str, entry: JobFunctionEntry) -> None:
        """Acrescenta uma função ao catálogo do tenant."""
        self._catalog.setdefault(tenant_id, {})[entry.job_function_id] = entry

    # --- port ----------------------------------------------------------------------

    def _da_unidade(self, tenant_id: str, unit_id: str) -> list[tuple[str, StaffMember]]:
        return [
            (chave[2], membro)
            for chave, membro in self._members.items()
            if chave[0] == tenant_id and chave[1] == unit_id
        ]

    def list_active_members(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[StaffMember, ...]:
        self.calls.append("list_active_members")
        return tuple(m for _, m in self._da_unidade(tenant_id, unit_id) if m.active)

    def list_members(
        self, tenant_id: TenantId, unit_id: UnitId, employee_ids: frozenset[EmployeeId]
    ) -> tuple[StaffMember, ...]:
        self.calls.append("list_members")
        return tuple(m for eid, m in self._da_unidade(tenant_id, unit_id) if eid in employee_ids)

    def list_members_of_user(
        self, tenant_id: TenantId, unit_id: UnitId, user_id: str
    ) -> tuple[StaffMember, ...]:
        self.calls.append("list_members_of_user")
        return tuple(
            m
            for eid, m in self._da_unidade(tenant_id, unit_id)
            if self._users.get((tenant_id, unit_id, eid)) == user_id
        )

    def list_job_functions(self, tenant_id: TenantId) -> tuple[JobFunctionEntry, ...]:
        self.calls.append("list_job_functions")
        return tuple(self._catalog.get(tenant_id, {}).values())


_conforms: StaffReadPort = InMemoryStaffRead()

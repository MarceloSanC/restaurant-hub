"""Port de saída: leitura dos registros de staff que scheduling precisa (ADR 4.3.0003).

Scheduling não importa staff (contrato `bc-independence`): lê por este port, com DTO
**próprio** (doc §3.10.1). O adapter (Stage 4.4) é servido por uma **fachada de staff
que não autoriza** — o use case de scheduling já autorizou a leitura com permissão de
scheduling (ADR 3.5.0001: o chamador autoriza; finding 1 da issue #72).

Quatro leituras **em lote**, todas com a unidade no endereço exceto o catálogo, que é
do tenant. Não há listagem tenant-wide de registro.

**Leis** (suíte `tests/contract/features/scheduling/test_staff_read_port_laws.py`):

- **L-ST1 — endereço.** Nenhuma leitura devolve registro de outra unidade ou tenant.
- **L-ST2 — quadro completo.** `list_active_members` = todos os ativos da unidade, só
  eles.
- **L-ST3 — lote.** `list_members(ids)` devolve um `StaffMember` por id pedido que é
  da unidade, ativo **ou não**; id desconhecido ou de outra unidade é omitido.
- **L-ST4 — vínculo de login.** `list_members_of_user` = os registros da unidade
  vinculados ao `user_id`, ativos ou não, só eles.
- **L-ST5 — catálogo.** `list_job_functions` = todas as funções do tenant, só elas.

Nenhuma ordem é garantida: o use case ordena.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)


@dataclass(frozen=True)
class StaffMember:
    """O registro de funcionário como scheduling o lê.

    Attributes:
        employee_id: o registro.
        unit_id: a unidade do registro.
        display_name: o nome de exibição **atual** (reconciliação na leitura).
        active: se o registro está ativo.
        job_function_ids: as funções que o registro detém hoje.
        contracted_weekly_hours: carga semanal contratada; `None` = sob demanda.
        unavailabilities: as janelas de indisponibilidade.
    """

    employee_id: EmployeeId
    unit_id: UnitId
    display_name: str
    active: bool
    job_function_ids: frozenset[JobFunctionId]
    contracted_weekly_hours: Decimal | None
    unavailabilities: tuple[UnavailabilityWindow, ...]


@dataclass(frozen=True)
class JobFunctionEntry:
    """Uma função do catálogo do tenant."""

    job_function_id: JobFunctionId
    name: str


class StaffReadPort(Protocol):
    """As leituras de staff de que scheduling depende."""

    def list_active_members(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[StaffMember, ...]:
        """Todos os registros ativos da unidade (L-ST2)."""
        ...

    def list_members(
        self, tenant_id: TenantId, unit_id: UnitId, employee_ids: frozenset[EmployeeId]
    ) -> tuple[StaffMember, ...]:
        """Os registros pedidos que são da unidade, ativos ou não (L-ST3)."""
        ...

    def list_members_of_user(
        self, tenant_id: TenantId, unit_id: UnitId, user_id: str
    ) -> tuple[StaffMember, ...]:
        """Os registros da unidade vinculados ao login, ativos ou não (L-ST4)."""
        ...

    def list_job_functions(self, tenant_id: TenantId) -> tuple[JobFunctionEntry, ...]:
        """O catálogo de funções do tenant (L-ST5)."""
        ...

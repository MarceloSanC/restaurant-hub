"""Port de saída: a configuração de escala do restaurante (calendário + validação).

A configuração é do tenant (ADR 4.1.0003). Um tenant que nunca a gravou não tem
configuração: o port devolve `None` e o **use case** aplica os defaults de domínio, num
sítio só (`use_cases/_inputs.py`, concept §5.12) — o port não inventa default.

`SchedulingSettings` não define método algum (regra 10 do `check_layout`).

**L-CF1** (suíte `test_schedule_config_repository_laws.py`): `find_settings` devolve a
configuração gravada **do tenant pedido**, ou `None` — nunca a de outro tenant.
"""

from dataclasses import dataclass
from typing import Protocol

from restaurant_hub.features.scheduling.domain.value_objects.identifiers import TenantId
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    ValidationConfig,
)


@dataclass(frozen=True)
class SchedulingSettings:
    """O calendário operacional e a configuração de validação do tenant."""

    calendar: OperationalCalendar
    validation: ValidationConfig


class ScheduleConfigRepository(Protocol):
    """Leitura da configuração de escala do tenant."""

    def find_settings(self, tenant_id: TenantId) -> SchedulingSettings | None:
        """A configuração gravada do tenant, ou `None` (L-CF1)."""
        ...

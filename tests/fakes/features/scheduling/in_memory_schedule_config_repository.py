"""Fake in-memory do `ScheduleConfigRepository` — obedece L-CF1, com registro de chamadas."""

from dataclasses import dataclass, field

from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import TenantId


@dataclass
class InMemoryScheduleConfigRepository:
    """Configuração por tenant; tenant sem entrada devolve `None`."""

    calls: list[str] = field(default_factory=list)
    _settings: dict[str, SchedulingSettings] = field(default_factory=dict)

    def set_settings(self, tenant_id: str, settings: SchedulingSettings) -> None:
        """Grava a configuração do tenant (semeadura, fora do port)."""
        self._settings[tenant_id] = settings

    def find_settings(self, tenant_id: TenantId) -> SchedulingSettings | None:
        self.calls.append("find_settings")
        return self._settings.get(tenant_id)


_conforms: ScheduleConfigRepository = InMemoryScheduleConfigRepository()

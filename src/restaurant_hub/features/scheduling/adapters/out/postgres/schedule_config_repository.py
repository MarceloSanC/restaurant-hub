"""Adapter Postgres de `ScheduleConfigRepository` — L-CF1.

Uma leitura pela PK de `scheduling_settings`; a linha volta pelo mapper, que reidrata pelos
construtores e **não aplica default** (os defaults são do use case, `_inputs.py`). Tenant
sem linha devolve `None`.

Só leitura: a escrita da configuração é da Stage 4.8, que acrescenta o método ao port e o
upsert nesta tabela sem migration (concept 4.4 §7 D-CONFIG).
"""

from sqlalchemy import Engine, select

from restaurant_hub.features.scheduling.adapters.out.postgres import mappers
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import scheduling_settings
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import TenantId


class PostgresScheduleConfigRepository:
    """Implementação PostgreSQL do port `ScheduleConfigRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_settings(self, tenant_id: TenantId) -> SchedulingSettings | None:
        """A configuração gravada do tenant, ou `None` — nunca a de outro (L-CF1)."""
        with self._engine.connect() as connection:
            row = connection.execute(
                select(scheduling_settings).where(scheduling_settings.c.tenant_id == tenant_id)
            ).one_or_none()
        return mappers.row_to_settings(row) if row is not None else None

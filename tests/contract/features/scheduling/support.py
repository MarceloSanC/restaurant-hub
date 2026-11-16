"""Apoio das suítes de scheduling que comparam o gravado com o lido.

**Por que uma projeção.** As entidades de scheduling são iguais **por identidade**
(`ShiftBand.__eq__` compara só o `id`, e assim as demais): `lida.bands == gravada.bands`
compara a tupla de ids das faixas e nada do que há dentro delas. Um adapter que perdesse a
quantidade de uma demanda ou o intervalo de uma alocação passaria por essa igualdade. A
fidelidade (L-SC8) é sobre **conteúdo e ordem**, e `project` a torna comparável: achata a
escala em tuplas de primitivos, nos três níveis, na ordem das tuplas do agregado.

**Semeadura do real** (Stage 4.4). `seed_settings` grava a configuração por `INSERT`
direto: o port não tem escrita (a da configuração é da Stage 4.8), e a linha é montada
**aqui**, campo a campo, sem passar pelo mapper do adapter — uma suíte que semeasse pelo
inverso do mapper que ela mesma testa provaria só que o mapper concorda consigo.
"""

from typing import Any

from sqlalchemy import Engine

from restaurant_hub.features.scheduling.adapters.out.postgres.tables import scheduling_settings
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import PolicyRule

Projection = tuple[object, ...]


def project(schedule: Schedule) -> Projection:
    """A escala inteira em primitivos, na ordem das tuplas — o que L-SC8 compara."""
    return (
        schedule.id,
        schedule.tenant_id,
        schedule.unit_id,
        schedule.period.first_day,
        schedule.period.days,
        schedule.calendar.week_start.value,
        schedule.calendar.day_cutoff.at,
        schedule.version,
        tuple(
            (
                band.id,
                band.time_range.start,
                band.time_range.end,
                band.time_range.break_minutes,
                tuple(
                    (
                        demand.id,
                        demand.job_function_id,
                        demand.quantity.value,
                        tuple(
                            (
                                assignment.id,
                                assignment.employee_id,
                                assignment.counts_toward_workload,
                                assignment.function_exception,
                                assignment.break_minutes,
                            )
                            for assignment in demand.assignments
                        ),
                    )
                    for demand in band.demands
                ),
            )
            for band in schedule.bands
        ),
    )


def seed_settings(engine: Engine, tenant_id: str, settings: SchedulingSettings) -> None:
    """Grava a linha de `scheduling_settings` do tenant, coluna a coluna."""
    validation = settings.validation
    row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "week_start": settings.calendar.week_start.value,
        "day_cutoff": settings.calendar.day_cutoff.at,
        "min_rest_minutes": validation.min_rest_minutes,
        "daily_cap_minutes": validation.daily_cap_minutes,
        "weekly_cap_minutes": validation.weekly_cap_minutes,
        "workload_tolerance_minutes": validation.workload_tolerance_minutes,
        "workload_direction": validation.workload_direction.value,
    }
    for name, value in vars(validation).items():
        if isinstance(value, PolicyRule):
            row[f"{name}_enabled"] = value.enabled
            row[f"{name}_mode"] = value.mode.value
    with engine.begin() as connection:
        connection.execute(scheduling_settings.insert().values(row))

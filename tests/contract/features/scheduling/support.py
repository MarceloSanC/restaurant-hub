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

**Vizinhas como um chamador honesto as leria** (issue #199). `neighbours_now` lê as duas
vagas pelo próprio port (`list_in_range`), com a regra de `neighbours_of` da application:
é o `ExpectedNeighbours` de quem leu agora e escreve sem que nada mude no meio. Os testes
que não são sobre L-SC9 o passam ao `save`; os de L-SC9 montam o esperado à mão.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, select

from restaurant_hub.features.scheduling.adapters.out.postgres.mappers import row_to_change
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    schedule_changes,
    scheduling_settings,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ExpectedNeighbours,
    NeighbourVersion,
    ScheduleChange,
    ScheduleRepository,
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


def read_trail(engine: Engine, schedule_id: str) -> tuple[ScheduleChange, ...]:
    """A trilha gravada da escala, em ordem de `seq`, lida pelo codec do adapter."""
    with engine.connect() as connection:
        rows = connection.execute(
            select(schedule_changes)
            .where(schedule_changes.c.schedule_id == schedule_id)
            .order_by(schedule_changes.c.seq)
        ).all()
    return tuple(row_to_change(row) for row in rows)


NO_NEIGHBOURS = ExpectedNeighbours(previous=None, following=None)


def _seen(schedule: Schedule | None) -> NeighbourVersion | None:
    return None if schedule is None else NeighbourVersion(schedule.id, schedule.version)


def neighbours_now(repo: ScheduleRepository, schedule: Schedule) -> ExpectedNeighbours:
    """As vagas vizinhas de `schedule` lidas agora pelo port (L-SC9)."""
    um_dia = timedelta(days=1)
    anterior = schedule.period.first_day - um_dia
    seguinte = schedule.period.last_day + um_dia
    unidade = (schedule.tenant_id, schedule.unit_id)
    previous = next(
        (
            e
            for e in repo.list_in_range(*unidade, anterior, anterior)
            if e.period.last_day == anterior and e.id != schedule.id
        ),
        None,
    )
    following = next(
        (
            e
            for e in repo.list_in_range(*unidade, seguinte, seguinte)
            if e.period.first_day == seguinte and e.id != schedule.id
        ),
        None,
    )
    return ExpectedNeighbours(previous=_seen(previous), following=_seen(following))


def save_as_read(
    repo: ScheduleRepository, schedule: Schedule, expected_version: int, change: ScheduleChange
) -> None:
    """`save` com as vizinhas lidas agora — o chamador honesto dos testes fora de L-SC9."""
    repo.save(schedule, expected_version, neighbours_now(repo, schedule), change)

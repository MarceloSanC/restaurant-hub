"""Apoio das suítes de scheduling que comparam o gravado com o lido.

**Por que uma projeção.** As entidades de scheduling são iguais **por identidade**
(`ShiftBand.__eq__` compara só o `id`, e assim as demais): `lida.bands == gravada.bands`
compara a tupla de ids das faixas e nada do que há dentro delas. Um adapter que perdesse a
quantidade de uma demanda ou o intervalo de uma alocação passaria por essa igualdade. A
fidelidade (L-SC8) é sobre **conteúdo e ordem**, e `project` a torna comparável: achata a
escala em tuplas de primitivos, nos três níveis, na ordem das tuplas do agregado.
"""

from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule

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

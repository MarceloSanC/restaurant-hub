"""Cenários dos testes de validação — escalas montadas pela API pública da raiz.

Cada `Turno` é uma alocação: o par `(start, end)` vira uma faixa (compartilhada por
quem tem o mesmo par), a função vira a demanda da faixa e o registro é alocado
nela. A quantidade da demanda é, por default, o número de alocados — para que a
sobre-cobertura só apareça no teste que a pede (`quantidades`). Os ids levam o id
da escala como prefixo, então duas escalas do mesmo cenário nunca colidem.

Nada aqui conta horas nem avalia política: só monta o estado.
"""

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    EmployeeFacts,
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    ValidationConfig,
)

SEGUNDA = date(2026, 9, 28)
"""Segunda-feira — início da semana do calendário default."""

COZINHEIRO = JobFunctionId("cozinheiro")
ATENDENTE = JobFunctionId("atendente")


def em(dia: int, hora: int, minuto: int = 0, *, base: date = SEGUNDA) -> datetime:
    """Instante ingênuo `dia` dias depois de `base`, às `hora:minuto`."""
    return datetime.combine(base + timedelta(days=dia), time(hora, minuto))


@dataclass(frozen=True)
class Turno:
    """Uma alocação do cenário."""

    employee: str
    start: datetime
    end: datetime
    function: JobFunctionId = COZINHEIRO
    band_break: int = 0
    alloc_break: int | None = None
    counts: bool = True
    function_exception: bool = False


def escala(
    turnos: Iterable[Turno],
    *,
    schedule_id: str = "s",
    first_day: date = SEGUNDA,
    endereco: tuple[str, str] = ("t1", "u1"),
    quantidades: Mapping[tuple[datetime, datetime, JobFunctionId], int] | None = None,
) -> Schedule:
    """Escala de 7 dias com os turnos dados; `endereco` é `(tenant, unidade)`."""
    calendario = OperationalCalendar.default()
    raiz = Schedule(
        id=ScheduleId(schedule_id),
        tenant_id=TenantId(endereco[0]),
        unit_id=UnitId(endereco[1]),
        period=SchedulePeriod(first_day=first_day),
        calendar=calendario,
    )
    lista = list(turnos)
    faixas: dict[tuple[datetime, datetime], ShiftBandId] = {}
    demandas: dict[tuple[datetime, datetime, JobFunctionId], ShiftDemandId] = {}
    for turno in lista:
        par = (turno.start, turno.end)
        if par not in faixas:
            faixas[par] = ShiftBandId(f"{schedule_id}-b{len(faixas)}")
            raiz = raiz.enable_band(
                faixas[par], TimeRange(turno.start, turno.end, turno.band_break)
            )
        chave = (*par, turno.function)
        if chave not in demandas:
            demandas[chave] = ShiftDemandId(f"{faixas[par]}-{turno.function}")
            alocados = sum(
                1 for outro in lista if (outro.start, outro.end, outro.function) == chave
            )
            alvo = (quantidades or {}).get(chave, alocados)
            raiz = raiz.declare_demand(
                demandas[chave], faixas[par], turno.function, DemandQuantity(alvo)
            )
    for indice, turno in enumerate(lista):
        alocacao = AssignmentId(f"{schedule_id}-a{indice}")
        raiz = raiz.assign(
            alocacao,
            demandas[(turno.start, turno.end, turno.function)],
            EmployeeId(turno.employee),
            counts_toward_workload=turno.counts,
            function_exception=turno.function_exception,
        )
        if turno.alloc_break is not None:
            raiz = raiz.declare_allocation_break(alocacao, turno.alloc_break)
    return raiz


def fatos(
    employee: str,
    *,
    funcoes: Iterable[JobFunctionId] = (COZINHEIRO,),
    horas: Decimal | None = None,
    ativo: bool = True,
    indisponivel: Iterable[tuple[datetime, datetime]] = (),
) -> EmployeeFacts:
    """Fatos de staff de um registro (sob demanda por default)."""
    return EmployeeFacts(
        employee_id=EmployeeId(employee),
        active=ativo,
        job_function_ids=frozenset(funcoes),
        contracted_weekly_hours=horas,
        unavailabilities=tuple(UnavailabilityWindow(inicio, fim) for inicio, fim in indisponivel),
    )


def contexto(
    avaliada: Schedule,
    *extras: EmployeeFacts,
    previous: Schedule | None = None,
    next: Schedule | None = None,
) -> EvaluationContext:
    """Contexto com fatos default para todo alocado sem fatos explícitos."""
    explicitos = {fato.employee_id: fato for fato in extras}
    alocados = {
        alocacao.employee_id
        for escala_ in (previous, avaliada, next)
        if escala_ is not None
        for faixa in escala_.bands
        for demanda in faixa.demands
        for alocacao in demanda.assignments
    }
    for registro in sorted(alocados - explicitos.keys()):
        explicitos[registro] = fatos(registro)
    return EvaluationContext(
        schedule=avaliada, facts=tuple(explicitos.values()), previous=previous, next=next
    )


def config(**campos: object) -> ValidationConfig:
    """A config default com os campos dados trocados."""
    return dataclasses.replace(ValidationConfig.default(), **campos)  # type: ignore[arg-type]

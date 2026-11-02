"""Queries — a entrada dos use cases que não gravam (concept 4.3 §4).

Mesma forma dos commands: `actor` primeiro (`repr=False`), depois o endereço sem
defaults. Dias são `date` — `datetime` é recusado pelo use case
(`InvalidScheduleRequestError`), porque `datetime` é subclasse de `date` e o tipo
sozinho não o barra (concept §5.15).
"""

from dataclasses import dataclass, field
from datetime import date

from restaurant_hub.features.scheduling.application.dtos.commands import ScheduleOperation
from restaurant_hub.features.scheduling.application.ports.out.access_guard import Actor
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ScheduleId,
    TenantId,
    UnitId,
)


@dataclass(frozen=True)
class EvaluateScheduleQuery:
    """Avaliação ao vivo de um lote, sem gravar."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    schedule_id: ScheduleId
    expected_version: int
    operations: tuple[ScheduleOperation, ...]


@dataclass(frozen=True)
class GetScheduleQuery:
    """A escala vigente com as violações atuais."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    schedule_id: ScheduleId


@dataclass(frozen=True)
class GetCalendarQuery:
    """As faixas de um recorte de dias operacionais (até 42 dias)."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    first_day: date
    last_day: date


@dataclass(frozen=True)
class ListPastSchedulesQuery:
    """As escalas que terminam antes de `before`, mais recente primeiro."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    before: date
    limit: int = 10


@dataclass(frozen=True)
class GetMyScheduleQuery:
    """As alocações do próprio ator na unidade, num recorte de até 42 dias."""

    actor: Actor = field(repr=False)
    tenant_id: TenantId
    unit_id: UnitId
    first_day: date
    last_day: date

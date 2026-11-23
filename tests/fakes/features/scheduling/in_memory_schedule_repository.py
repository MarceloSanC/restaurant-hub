"""Fake in-memory do `ScheduleRepository` — obedece L-SC1…L-SC8.

No `save` troca o objeto inteiro: período e calendário são da criação e uma escala que os
traga diferentes está fora do contrato do port (Stage 4.4), então o fake não os confere.

L-SC9: as vagas vizinhas são achadas pela mesma regra do adapter — a escala da unidade
que termina no dia anterior ao período e a que começa no dia seguinte — e comparadas,
anterior antes da seguinte, com o `ExpectedNeighbours` recebido.

Grava o estado e a `ScheduleChange` juntos (L-SC3) e os expõe (`changes_of`) para os
testes da trilha. `calls` registra cada método chamado, para os testes de "nada
gravado" e "nenhum port tocado antes da autorização".
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    ScheduleNotFoundError,
    SchedulePeriodTakenError,
    ScheduleVersionConflictError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ExpectedNeighbours,
    NeighbourVersion,
    ScheduleChange,
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ScheduleId,
    TenantId,
    UnitId,
)


def _internal_ids(schedule: Schedule) -> dict[str, set[str]]:
    demandas = [d for f in schedule.bands for d in f.demands]
    return {
        "ShiftBandId": {f.id for f in schedule.bands},
        "ShiftDemandId": {d.id for d in demandas},
        "AssignmentId": {a.id for d in demandas for a in d.assignments},
    }


def _changed_neighbour(
    stored: NeighbourVersion | None, expected: NeighbourVersion | None
) -> str | None:
    """A escala a nomear se a vaga não está como lida: a que a ocupa, ou a lida se esvaziou."""
    if stored is not None and stored != expected:
        return stored.schedule_id
    if stored is None and expected is not None:
        return expected.schedule_id
    return None


def _version_of(schedule: Schedule | None) -> NeighbourVersion | None:
    return None if schedule is None else NeighbourVersion(schedule.id, schedule.version)


@dataclass
class InMemoryScheduleRepository:
    """Escalas por (tenant, unidade, id) e a trilha por escala."""

    calls: list[str] = field(default_factory=list)
    _schedules: dict[tuple[str, str, str], Schedule] = field(default_factory=dict)
    _changes: dict[str, list[ScheduleChange]] = field(default_factory=dict)

    def changes_of(self, schedule_id: str) -> tuple[ScheduleChange, ...]:
        """A trilha da escala, em ordem de gravação (fora do port)."""
        return tuple(self._changes.get(schedule_id, ()))

    def _da_unidade(self, tenant_id: str, unit_id: str) -> list[Schedule]:
        return [e for (t, u, _), e in self._schedules.items() if (t, u) == (tenant_id, unit_id)]

    def _check_ids_against_others(self, schedule: Schedule) -> None:
        # L-SC4: primeiro tipo em conflito (faixa → demanda → alocação) e, dele, o menor id
        # por codepoint entre TODAS as outras escalas da unidade — nunca a ordem de gravação.
        novos = _internal_ids(schedule)
        outras = [
            _internal_ids(outra)
            for outra in self._da_unidade(schedule.tenant_id, schedule.unit_id)
            if outra.id != schedule.id
        ]
        for tipo, ids in novos.items():
            comuns = {usado for outra in outras for usado in outra[tipo]} & ids
            if comuns:
                raise IdentifierInUseError(tipo, min(comuns))

    def _vagas(self, schedule: Schedule) -> tuple[NeighbourVersion | None, NeighbourVersion | None]:
        um_dia = timedelta(days=1)
        anterior = schedule.period.first_day - um_dia
        seguinte = schedule.period.last_day + um_dia
        outras = [
            e for e in self._da_unidade(schedule.tenant_id, schedule.unit_id) if e.id != schedule.id
        ]
        previous = next((e for e in outras if e.period.last_day == anterior), None)
        following = next((e for e in outras if e.period.first_day == seguinte), None)
        return _version_of(previous), _version_of(following)

    def _check_neighbours(
        self, schedule: Schedule, stored_version: int, expected: ExpectedNeighbours
    ) -> None:
        # L-SC9: qualquer diferença na vaga recusa — outra escala, outra versão, vaga que
        # esvaziou ou que passou a ter escala. A anterior antes da seguinte.
        for gravada, esperada in zip(
            self._vagas(schedule), (expected.previous, expected.following), strict=True
        ):
            changed = _changed_neighbour(gravada, esperada)
            if changed is not None:
                raise ScheduleVersionConflictError(
                    stored_version, stored_version, changed_neighbour_id=changed
                )

    def add(self, schedule: Schedule, change: ScheduleChange) -> None:
        self.calls.append("add")
        if any(e.id == schedule.id for e in self._schedules.values()):
            raise IdentifierInUseError("ScheduleId", schedule.id)
        dias = set(schedule.period.operational_days)
        for outra in self._da_unidade(schedule.tenant_id, schedule.unit_id):
            if dias & set(outra.period.operational_days):
                raise SchedulePeriodTakenError()
        self._check_ids_against_others(schedule)
        self._schedules[(schedule.tenant_id, schedule.unit_id, schedule.id)] = schedule
        self._changes[schedule.id] = [change]

    def save(
        self,
        schedule: Schedule,
        expected_version: int,
        expected_neighbours: ExpectedNeighbours,
        change: ScheduleChange,
    ) -> None:
        self.calls.append("save")
        chave = (schedule.tenant_id, schedule.unit_id, schedule.id)
        gravada = self._schedules.get(chave)
        if gravada is None:
            raise ScheduleNotFoundError(schedule.id)
        if gravada.version != expected_version:
            raise ScheduleVersionConflictError(expected_version, gravada.version)
        self._check_neighbours(schedule, gravada.version, expected_neighbours)
        self._check_ids_against_others(schedule)
        self._schedules[chave] = schedule
        self._changes[schedule.id].append(change)

    def find_by_id(
        self, tenant_id: TenantId, unit_id: UnitId, schedule_id: ScheduleId
    ) -> Schedule | None:
        self.calls.append("find_by_id")
        return self._schedules.get((tenant_id, unit_id, schedule_id))

    def list_in_range(
        self, tenant_id: TenantId, unit_id: UnitId, first_day: date, last_day: date
    ) -> tuple[Schedule, ...]:
        self.calls.append("list_in_range")
        cruzam = [
            e
            for e in self._da_unidade(tenant_id, unit_id)
            if e.period.first_day <= last_day and e.period.last_day >= first_day
        ]
        return tuple(sorted(cruzam, key=lambda e: e.period.first_day))

    def list_ending_before(
        self, tenant_id: TenantId, unit_id: UnitId, before: date, limit: int
    ) -> tuple[Schedule, ...]:
        self.calls.append("list_ending_before")
        anteriores = [e for e in self._da_unidade(tenant_id, unit_id) if e.period.last_day < before]
        anteriores.sort(key=lambda e: e.period.first_day, reverse=True)
        return tuple(anteriores[:limit])


_conforms: ScheduleRepository = InMemoryScheduleRepository()

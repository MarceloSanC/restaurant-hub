"""Issue #199 — o publish não grava uma violação de fronteira que a avaliação não viu.

Duas gerentes publicam semanas adjacentes da mesma unidade. Cada lote, sozinho, não viola
nada: a Ana entra no domingo à noite na semana anterior e na segunda cedo nesta. Juntos,
somam 7h de descanso entre jornadas (mínimo de 11h, `warn`). A segunda publicação foi
avaliada antes de a primeira gravar — viu a vizinha antiga.

A corrida é simulada **de forma determinística** no fake: o `save` da publicação X
executa, antes de gravar, a publicação Y inteira. Sem L-SC9, X gravaria sobre a avaliação
velha; com ela, X recusa com `ScheduleVersionConflictError` nomeando a vizinha, nada é
gravado, e a nova tentativa enxerga a violação e pede o aceite.
"""

import dataclasses
from collections.abc import Callable
from datetime import timedelta

import pytest

from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    PublishScheduleCommand,
)
from restaurant_hub.features.scheduling.application.errors import (
    ScheduleVersionConflictError,
    UnacknowledgedViolationsError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ExpectedNeighbours,
    ScheduleChange,
)
from restaurant_hub.features.scheduling.application.use_cases.publish_schedule import (
    PublishScheduleUseCase,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
)
from tests.fakes.features.scheduling.in_memory_schedule_repository import (
    InMemoryScheduleRepository,
)
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    T1,
    U1,
    World,
    at,
    blank_change,
    schedule,
)

pytestmark = pytest.mark.unit

_DOMINGO = MONDAY - timedelta(days=1)
_ANTERIOR, _ESTA = ScheduleId("sA"), ScheduleId("s1")
_LOTES = {
    # semana anterior: Ana no domingo 18h–23h
    _ANTERIOR: (AssignEmployee(AssignmentId("a-dom"), ShiftDemandId("eA"), EmployeeId("ana")),),
    # esta semana: Ana na segunda 06h–10h (7h depois)
    _ESTA: (AssignEmployee(AssignmentId("a-seg"), ShiftDemandId("d1"), EmployeeId("ana")),),
}


@dataclasses.dataclass
class _SaveIntercalado(InMemoryScheduleRepository):
    """Roda `antes_do_save` uma vez, dentro do próximo `save`, antes de gravar."""

    antes_do_save: Callable[[], None] | None = None
    vizinhas_recebidas: list[ExpectedNeighbours] = dataclasses.field(default_factory=list)

    def save(
        self,
        schedule: Schedule,
        expected_version: int,
        expected_neighbours: ExpectedNeighbours,
        change: ScheduleChange,
    ) -> None:
        self.vizinhas_recebidas.append(expected_neighbours)
        gancho, self.antes_do_save = self.antes_do_save, None
        if gancho is not None:
            gancho()
        super().save(schedule, expected_version, expected_neighbours, change)


def _semear(world: World) -> _SaveIntercalado:
    repo = _SaveIntercalado()
    world.schedules = repo
    anterior = (
        schedule("sA", MONDAY - timedelta(days=7))
        .enable_band(ShiftBandId("gA"), TimeRange(start=at(_DOMINGO, 18), end=at(_DOMINGO, 23)))
        .declare_demand(ShiftDemandId("eA"), ShiftBandId("gA"), COOK, DemandQuantity(1))
    )
    esta = (
        schedule("s1")
        .enable_band(ShiftBandId("f1"), TimeRange(start=at(MONDAY, 6), end=at(MONDAY, 10)))
        .declare_demand(ShiftDemandId("d1"), ShiftBandId("f1"), COOK, DemandQuantity(1))
    )
    for escala in (anterior, esta):
        repo.add(dataclasses.replace(escala, version=1), blank_change())
    return repo


def _publicar(world: World, sid: ScheduleId) -> None:
    gravada = world.schedules.find_by_id(T1, U1, sid)
    assert gravada is not None
    PublishScheduleUseCase(
        world.schedules, world.config, world.staff, world.clock, world.guard
    ).execute(PublishScheduleCommand(world.manager, T1, U1, sid, gravada.version, _LOTES[sid], ()))


@pytest.mark.parametrize(
    ("primeira", "segunda"),
    [(_ESTA, _ANTERIOR), (_ANTERIOR, _ESTA)],
    ids=["vizinha-anterior-muda", "vizinha-seguinte-muda"],
)
def test_publicacao_avaliada_contra_a_vizinha_antiga_recusa_e_a_nova_tentativa_ve_a_violacao(
    world: World, primeira: ScheduleId, segunda: ScheduleId
) -> None:
    """`primeira` grava no meio da publicação de `segunda`, depois da avaliação desta."""
    repo = _semear(world)
    repo.antes_do_save = lambda: _publicar(world, primeira)
    with pytest.raises(ScheduleVersionConflictError) as excinfo:
        _publicar(world, segunda)
    assert (excinfo.value.changed_neighbour_id, excinfo.value.current_version) == (primeira, 1)
    # Nada gravado pela recusa: estado e trilha da `segunda` como estavam.
    recusada = repo.find_by_id(T1, U1, segunda)
    assert recusada is not None
    assert recusada.version == 1
    assert len(repo.changes_of(segunda)) == 1
    assert len(repo.changes_of(primeira)) == 2  # noqa: PLR2004
    # A nova tentativa reavalia contra a vizinha atual: o descanso de 7h aparece.
    with pytest.raises(UnacknowledgedViolationsError) as pendentes:
        _publicar(world, segunda)
    assert [v.policy for v in pendentes.value.violations] == [PolicyKind.REST_BETWEEN_SHIFTS]


def test_o_publish_entrega_ao_save_as_vizinhas_que_a_avaliacao_leu(world: World) -> None:
    repo = _semear(world)
    _publicar(world, _ESTA)
    (vizinhas,) = repo.vizinhas_recebidas
    assert vizinhas.following is None
    assert vizinhas.previous is not None
    assert (vizinhas.previous.schedule_id, vizinhas.previous.version) == (_ANTERIOR, 1)

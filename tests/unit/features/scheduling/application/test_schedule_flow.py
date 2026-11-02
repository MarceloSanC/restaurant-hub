"""Fluxo editar → avaliar → aceitar `warn` → publicar, com fakes (CA22; DoD do roadmap 4.3).

A `key` que o avaliar devolve casa no publicar porque os ids de criação vêm do cliente
(ADR 4.3.0004): avaliar e publicar aplicam o mesmo lote e produzem as mesmas alocações.
"""

from uuid import UUID

import pytest

from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    CreateScheduleCommand,
    DeclareDemand,
    EnableBand,
    PublishScheduleCommand,
    ScheduleOperation,
    ViolationAcknowledgement,
)
from restaurant_hub.features.scheduling.application.dtos.queries import EvaluateScheduleQuery
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    UnacknowledgedViolationsError,
)
from restaurant_hub.features.scheduling.application.use_cases.create_schedule import (
    CreateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.evaluate_schedule import (
    EvaluateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.publish_schedule import (
    PublishScheduleUseCase,
)
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
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    T1,
    U1,
    World,
    at,
    member,
)

pytestmark = pytest.mark.unit

_LOTE: tuple[ScheduleOperation, ...] = (
    EnableBand(ShiftBandId("c-f1"), TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 16))),
    DeclareDemand(ShiftDemandId("c-d1"), ShiftBandId("c-f1"), COOK, DemandQuantity(1)),
    AssignEmployee(AssignmentId("c-a1"), ShiftDemandId("c-d1"), EmployeeId("ana")),
    AssignEmployee(AssignmentId("c-a2"), ShiftDemandId("c-d1"), EmployeeId("carla")),
)


def test_ca22_fluxo_completo_com_aceite_casando_pelos_ids_do_cliente(world: World) -> None:
    world.staff.add_member(T1, member("carla"))
    criada = CreateScheduleUseCase(
        world.schedules, world.config, world.ids, world.clock, world.guard
    ).execute(CreateScheduleCommand(world.manager, T1, U1, MONDAY))
    sid = criada.schedule_id
    assert sid == ScheduleId(str(UUID(int=1)))
    avaliar = EvaluateScheduleUseCase(world.schedules, world.config, world.staff, world.guard)
    publicar = PublishScheduleUseCase(
        world.schedules, world.config, world.staff, world.clock, world.guard
    )

    avaliado = avaliar.execute(EvaluateScheduleQuery(world.manager, T1, U1, sid, 1, _LOTE))
    assert [v.policy for v in avaliado.warnings] == [PolicyKind.OVER_COVERAGE]
    (excedente,) = avaliado.warnings
    assert excedente.assignment_ids == {"c-a1", "c-a2"}

    with pytest.raises(UnacknowledgedViolationsError):
        publicar.execute(PublishScheduleCommand(world.manager, T1, U1, sid, 1, _LOTE))

    aceite = ViolationAcknowledgement(excedente.key, excedente.observed, excedente.limit)
    publicado = publicar.execute(
        PublishScheduleCommand(world.manager, T1, U1, sid, 1, _LOTE, (aceite,))
    )
    assert publicado.summary.version == 1 + len(_LOTE)
    (faixa,) = publicado.bands
    assert [a.assignment_id for a in faixa.demands[0].assignments] == ["c-a1", "c-a2"]
    assert world.schedules.changes_of(sid)[-1].acknowledged == (excedente,)

    # Depois de publicar, o mesmo id de criação é recusado.
    with pytest.raises(IdentifierInUseError):
        avaliar.execute(
            EvaluateScheduleQuery(
                world.manager,
                T1,
                U1,
                sid,
                publicado.summary.version,
                (AssignEmployee(AssignmentId("c-a1"), ShiftDemandId("c-d1"), EmployeeId("bia")),),
            )
        )

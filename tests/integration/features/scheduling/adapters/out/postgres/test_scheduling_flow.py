"""Os use cases da 4.3 sobre os adapters reais, contra o Postgres — CA17.

Criar → avaliar → publicar um lote com aceite de `warn` → ler a escala e "minha escala",
com o guard **fake** (o `AccessGuard` de scheduling é da 4.5) e os três ports de dados
reais: `PostgresScheduleRepository`, `PostgresScheduleConfigRepository` e o
`LocalStaffReadAdapter` sobre a `StaffReadFacade` sobre os repositórios Postgres de staff.
A trilha fica com uma linha por escrita, com o autor do escopo.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine

from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_config_repository import (
    PostgresScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository import (
    PostgresScheduleRepository,
)
from restaurant_hub.features.scheduling.adapters.out.staff.local_staff_read_adapter import (
    LocalStaffReadAdapter,
)
from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    CreateScheduleCommand,
    DeclareDemand,
    EnableBand,
    PublishScheduleCommand,
    ScheduleOperation,
    ViolationAcknowledgement,
)
from restaurant_hub.features.scheduling.application.dtos.queries import (
    EvaluateScheduleQuery,
    GetMyScheduleQuery,
    GetScheduleQuery,
)
from restaurant_hub.features.scheduling.application.errors import UnacknowledgedViolationsError
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
)
from restaurant_hub.features.scheduling.application.use_cases.create_schedule import (
    CreateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.evaluate_schedule import (
    EvaluateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_my_schedule import (
    GetMyScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_schedule import (
    GetScheduleUseCase,
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
    JobFunctionId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
)
from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.facade import StaffReadFacade
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects import identifiers as staff_ids
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.contract.features.scheduling.support import read_trail
from tests.fakes.features.scheduling.in_memory_access_guard import InMemoryAccessGuard
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = [pytest.mark.integration]

_T, _U = TenantId("t1"), UnitId("u1")
_SEG = date(2026, 11, 2)
_AGORA = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
_COZINHEIRO = JobFunctionId("cozinheiro")


def _semear_staff(engine: Engine) -> None:
    """Uma função e dois registros, gravados pelos ports Postgres de staff."""
    funcoes = PostgresJobFunctionRepository(engine)
    registros = PostgresEmployeeRepository(engine)
    funcoes.add(
        JobFunction(
            id=staff_ids.JobFunctionId(_COZINHEIRO),
            tenant_id=staff_ids.TenantId(_T),
            name="Cozinheiro",
        )
    )
    for eid in ("ana", "carla"):
        registros.add(
            Employee(
                id=staff_ids.EmployeeId(eid),
                tenant_id=staff_ids.TenantId(_T),
                unit_id=staff_ids.UnitId(_U),
                name=eid.capitalize(),
                workload_profile=FixedSchedule(Decimal("40")),
                shift_preference=None,
                job_function_ids=frozenset({staff_ids.JobFunctionId(_COZINHEIRO)}),
            )
        )
    registros.link_login(
        staff_ids.TenantId(_T),
        staff_ids.UnitId(_U),
        staff_ids.EmployeeId("ana"),
        staff_ids.UserId("user-ana"),
    )


def _lote() -> tuple[ScheduleOperation, ...]:
    inicio = datetime.combine(_SEG, time(10))
    return (
        EnableBand(
            ShiftBandId("f1"), TimeRange(start=inicio, end=datetime.combine(_SEG, time(16)))
        ),
        DeclareDemand(ShiftDemandId("d1"), ShiftBandId("f1"), _COZINHEIRO, DemandQuantity(1)),
        AssignEmployee(AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana")),
        AssignEmployee(AssignmentId("a2"), ShiftDemandId("d1"), EmployeeId("carla")),
    )


def test_criar_publicar_com_aceite_e_ler_sobre_os_adapters_reais(banco_limpo: Engine) -> None:
    _semear_staff(banco_limpo)
    escalas = PostgresScheduleRepository(banco_limpo)
    configuracao = PostgresScheduleConfigRepository(banco_limpo)
    staff = LocalStaffReadAdapter(
        StaffReadFacade(
            employees=PostgresEmployeeRepository(banco_limpo),
            job_functions=PostgresJobFunctionRepository(banco_limpo),
        )
    )
    guard = InMemoryAccessGuard()
    gerente = guard.issue("user-ger", _T)
    ana = guard.issue("user-ana", _T)
    for permissao in (
        PERMISSION_MANAGE_SCHEDULE,
        PERMISSION_VIEW_SCHEDULE,
        PERMISSION_VIEW_OWN_SCHEDULE,
    ):
        guard.grant(permissao, tenant_id=_T, unit_id=_U)
    relogio = FakeClock(_AGORA)

    criada = CreateScheduleUseCase(
        escalas, configuracao, FakeIdGenerator([UUID(int=7)]), relogio, guard
    ).execute(CreateScheduleCommand(gerente, _T, _U, _SEG))
    sid = criada.schedule_id

    avaliado = EvaluateScheduleUseCase(escalas, configuracao, staff, guard).execute(
        EvaluateScheduleQuery(gerente, _T, _U, sid, 1, _lote())
    )
    (excedente,) = avaliado.warnings
    assert excedente.policy is PolicyKind.OVER_COVERAGE

    publicar = PublishScheduleUseCase(escalas, configuracao, staff, relogio, guard)
    with pytest.raises(UnacknowledgedViolationsError):
        publicar.execute(PublishScheduleCommand(gerente, _T, _U, sid, 1, _lote()))
    aceite = ViolationAcknowledgement(excedente.key, excedente.observed, excedente.limit)
    publicado = publicar.execute(
        PublishScheduleCommand(gerente, _T, _U, sid, 1, _lote(), (aceite,))
    )
    assert publicado.summary.version == 1 + len(_lote())

    lida = GetScheduleUseCase(escalas, configuracao, staff, guard).execute(
        GetScheduleQuery(gerente, _T, _U, sid)
    )
    (faixa,) = lida.bands
    (demanda,) = faixa.demands
    assert demanda.job_function_name == "Cozinheiro"
    assert [(a.assignment_id, a.display_name) for a in demanda.assignments] == [
        ("a1", "Ana"),
        ("a2", "Carla"),
    ]

    minha = GetMyScheduleUseCase(escalas, staff, guard).execute(
        GetMyScheduleQuery(ana, _T, _U, _SEG, _SEG)
    )
    assert [(t.assignment_id, t.employee_id) for t in minha.shifts] == [("a1", "ana")]

    trilha = read_trail(banco_limpo, sid)
    assert [(m.previous_version, m.author_user_id) for m in trilha] == [
        (None, "user-ger"),
        (1, "user-ger"),
    ]
    assert trilha[0].operations == ()
    assert trilha[1].operations == _lote()
    assert trilha[1].acknowledged == (excedente,)
    assert all(m.occurred_at == _AGORA for m in trilha)

"""Fixtures das suítes de lei dos ports de scheduling, por implementação.

A ramificação por implementação mora **aqui**, não nos módulos de teste (precedente de
staff, `tests/contract/features/staff/conftest.py`): a 4.4 acrescenta o adapter real ao
`params` e a sua semeadura, e as leis não mudam.

**Uma tupla de implementações por fixture** (Stage 4.4). Constantes nomeadas, e não
literais em `params`, porque é sobre elas que `test_no_implementation_branching.py` assere:
retirar `"postgres"` de uma delas faria a suíte voltar a exercitar uma implementação só,
com tudo verde. Cada fixture é promovida pela Task que entrega o seu adapter.

O ramo `postgres` trunca **no setup** (convenção do projeto, conftest de staff) e falha
alto sem banco: a fixture `engine` não tem caminho de skip (ADR 2.3.0001).
"""

from collections.abc import Callable, Iterator
from datetime import time
from decimal import Decimal

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
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
    StaffMember,
    StaffReadPort,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    ValidationConfig,
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
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId as StaffEmployeeId,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId as StaffJobFunctionId,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId as StaffTenantId,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    UnitId as StaffUnitId,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    UserId as StaffUserId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.conftest import truncar_tudo
from tests.contract.features.scheduling.support import read_trail, seed_settings
from tests.fakes.features.scheduling.in_memory_schedule_config_repository import (
    InMemoryScheduleConfigRepository,
)
from tests.fakes.features.scheduling.in_memory_schedule_repository import (
    InMemoryScheduleRepository,
)
from tests.fakes.features.scheduling.in_memory_staff_read import InMemoryStaffRead

T1, T2 = TenantId("t1"), TenantId("t2")

CONFIG_IMPLEMENTATIONS = ("fake", "postgres")
SCHEDULE_IMPLEMENTATIONS = ("fake", "postgres")
STAFF_READ_IMPLEMENTATIONS = ("fake", "postgres")
U1, U2 = UnitId("u1"), UnitId("u2")


def staff_member(
    eid: str, unidade: UnitId, *, ativo: bool = True, funcao: str = "cozinheiro"
) -> StaffMember:
    return StaffMember(
        employee_id=EmployeeId(eid),
        unit_id=unidade,
        display_name=f"Nome {eid}",
        active=ativo,
        job_function_ids=frozenset({JobFunctionId(funcao)}),
        contracted_weekly_hours=Decimal("40"),
        unavailabilities=(),
    )


# O mundo semeado, como dados: o MESMO para as duas implementações. Registro com login
# vinculado leva o `user_id`.
#
# `dani` detém uma função do catálogo do PRÓPRIO tenant: registro de `t2` com função de `t1`
# é estado que staff não representa (lei L-E4 de staff; id de função global), e o mundo tem
# de ser semeável nas duas implementações (Stage 4.4).
_REGISTROS: tuple[tuple[TenantId, StaffMember, str | None], ...] = (
    (T1, staff_member("ana", U1), "user-ana"),
    (T1, staff_member("bia", U1), None),
    (T1, staff_member("caio", U1, ativo=False), "user-ana"),
    (T1, staff_member("ana-u2", U2), "user-ana"),
    (T2, staff_member("dani", U1, funcao="garcom"), "user-ana"),
)
# Habilitação por unidade (Stage 3.11; L-ST6, issue #209): `None` = todas as unidades.
# `atendente` vale só em u2 — nenhum registro a detém, como staff exige (ADR 3.11.0002);
# `barman`, de t2, nomeia o mesmo id `u2` e não pode vazar para t1.
_CATALOGO: tuple[tuple[TenantId, JobFunctionEntry, frozenset[UnitId] | None], ...] = (
    (T1, JobFunctionEntry(JobFunctionId("cozinheiro"), "Cozinheiro"), None),
    (T1, JobFunctionEntry(JobFunctionId("atendente"), "Atendente"), frozenset({U2})),
    (T2, JobFunctionEntry(JobFunctionId("garcom"), "Garçom"), None),
    (T2, JobFunctionEntry(JobFunctionId("barman"), "Barman"), frozenset({U2})),
)


def _semear(fake: InMemoryStaffRead) -> None:
    for tenant, membro, user_id in _REGISTROS:
        fake.add_member(tenant, membro, user_id=user_id)
    for tenant, entrada, unidades in _CATALOGO:
        fake.add_job_function(
            tenant, entrada, units=None if unidades is None else frozenset(unidades)
        )


def _semear_staff_real(engine: Engine) -> StaffReadFacade:
    """O mesmo mundo, gravado pelos ports de staff sobre o Postgres; devolve a fachada.

    Ordem que staff exige: função → registro → vínculo de login → desligamento (staff recusa
    vincular registro desligado, e o registro exige função do próprio tenant).
    """
    funcoes = PostgresJobFunctionRepository(engine)
    registros = PostgresEmployeeRepository(engine)
    for tenant, entrada, unidades in _CATALOGO:
        funcoes.add(
            JobFunction(
                id=StaffJobFunctionId(entrada.job_function_id),
                tenant_id=StaffTenantId(tenant),
                name=entrada.name,
                unit_enablement=(
                    UnitEnablement.everywhere()
                    if unidades is None
                    else UnitEnablement.only(frozenset(StaffUnitId(u) for u in unidades))
                ),
            )
        )
    for tenant, membro, user_id in _REGISTROS:
        assert membro.contracted_weekly_hours is not None
        registro = Employee(
            id=StaffEmployeeId(membro.employee_id),
            tenant_id=StaffTenantId(tenant),
            unit_id=StaffUnitId(membro.unit_id),
            name=membro.display_name,
            workload_profile=FixedSchedule(membro.contracted_weekly_hours),
            shift_preference=None,
            job_function_ids=frozenset(StaffJobFunctionId(f) for f in membro.job_function_ids),
        )
        registros.add(registro)
        if user_id is not None:
            registros.link_login(
                registro.tenant_id, registro.unit_id, registro.id, StaffUserId(user_id)
            )
        if not membro.active:
            registros.update(registro.deactivate())
    return StaffReadFacade(registros, funcoes)


@pytest.fixture(params=STAFF_READ_IMPLEMENTATIONS)
def mundo(request: pytest.FixtureRequest) -> Iterator[StaffReadPort]:
    if request.param == "fake":
        fake = InMemoryStaffRead()
        _semear(fake)
        yield fake
        return
    if request.param == "postgres":
        engine: Engine = request.getfixturevalue("engine")
        truncar_tudo(engine)
        yield LocalStaffReadAdapter(_semear_staff_real(engine))
        return
    raise AssertionError(f"implementação desconhecida: {request.param!r}")


@pytest.fixture(params=SCHEDULE_IMPLEMENTATIONS)
def schedule_repo(request: pytest.FixtureRequest) -> Iterator[ScheduleRepository]:
    if request.param == "fake":
        yield InMemoryScheduleRepository()
        return
    if request.param == "postgres":
        engine: Engine = request.getfixturevalue("engine")
        truncar_tudo(engine)
        yield PostgresScheduleRepository(engine)
        return
    raise AssertionError(f"implementação desconhecida: {request.param!r}")


@pytest.fixture
def trail_of(
    request: pytest.FixtureRequest, schedule_repo: ScheduleRepository
) -> Callable[[str], tuple[ScheduleChange, ...]]:
    """Leitor da trilha gravada (L-SC3), por implementação.

    O do real lê `schedule_changes` pelo codec do adapter (`support.read_trail`): o port
    não tem leitura da trilha (concept 4.4 §7 D-TRAILREAD).
    """
    if isinstance(schedule_repo, InMemoryScheduleRepository):
        return schedule_repo.changes_of
    if isinstance(schedule_repo, PostgresScheduleRepository):
        engine: Engine = request.getfixturevalue("engine")
        return lambda schedule_id: read_trail(engine, schedule_id)
    raise AssertionError(f"implementação sem leitor de trilha: {type(schedule_repo)!r}")


@pytest.fixture(params=CONFIG_IMPLEMENTATIONS)
def config_world(
    request: pytest.FixtureRequest,
) -> Iterator[tuple[ScheduleConfigRepository, SchedulingSettings]]:
    """O port e a configuração gravada para o tenant `t1` (o `t2` não tem nenhuma)."""
    gravada = SchedulingSettings(
        calendar=OperationalCalendar(week_start=Weekday.SUNDAY, day_cutoff=DayCutoff(at=time(4))),
        validation=ValidationConfig.default(),
    )
    if request.param == "fake":
        fake = InMemoryScheduleConfigRepository()
        fake.set_settings(T1, gravada)
        yield fake, gravada
        return
    if request.param == "postgres":
        engine: Engine = request.getfixturevalue("engine")
        truncar_tudo(engine)
        seed_settings(engine, T1, gravada)
        yield PostgresScheduleConfigRepository(engine), gravada
        return
    raise AssertionError(f"implementação desconhecida: {request.param!r}")

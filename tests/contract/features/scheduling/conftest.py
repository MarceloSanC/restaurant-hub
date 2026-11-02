"""Fixtures das suítes de lei dos ports de scheduling, por implementação.

A ramificação por implementação mora **aqui**, não nos módulos de teste (precedente de
staff, `tests/contract/features/staff/conftest.py`): a 4.4 acrescenta o adapter real ao
`params` e a sua semeadura, e as leis não mudam.
"""

from collections.abc import Iterator
from decimal import Decimal

import pytest

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
from tests.fakes.features.scheduling.in_memory_staff_read import InMemoryStaffRead

T1, T2 = TenantId("t1"), TenantId("t2")
U1, U2 = UnitId("u1"), UnitId("u2")


def staff_member(eid: str, unidade: UnitId, *, ativo: bool = True) -> StaffMember:
    return StaffMember(
        employee_id=EmployeeId(eid),
        unit_id=unidade,
        display_name=f"Nome {eid}",
        active=ativo,
        job_function_ids=frozenset({JobFunctionId("cozinheiro")}),
        contracted_weekly_hours=Decimal("40"),
        unavailabilities=(),
    )


def _semear(fake: InMemoryStaffRead) -> None:
    fake.add_member(T1, staff_member("ana", U1), user_id="user-ana")
    fake.add_member(T1, staff_member("bia", U1))
    fake.add_member(T1, staff_member("caio", U1, ativo=False), user_id="user-ana")
    fake.add_member(T1, staff_member("ana-u2", U2), user_id="user-ana")
    fake.add_member(T2, staff_member("dani", U1), user_id="user-ana")
    fake.add_job_function(T1, JobFunctionEntry(JobFunctionId("cozinheiro"), "Cozinheiro"))
    fake.add_job_function(T1, JobFunctionEntry(JobFunctionId("atendente"), "Atendente"))
    fake.add_job_function(T2, JobFunctionEntry(JobFunctionId("garcom"), "Garçom"))


@pytest.fixture(params=["fake"])
def mundo(request: pytest.FixtureRequest) -> Iterator[StaffReadPort]:
    assert request.param == "fake"
    fake = InMemoryStaffRead()
    _semear(fake)
    yield fake

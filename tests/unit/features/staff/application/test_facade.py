"""`StaffReadFacade` — a fachada de leitura de staff para outros BCs (CA14, Stage 4.4).

Sobre os fakes de staff (`staff_repositories()`): as cinco leituras devolvem só primitivos;
`list_records` e `list_records_of_user` incluem inativos e não cruzam unidade nem tenant;
jornada fixa vira `Decimal`, sob demanda vira `None`; as funções de uma unidade são as
habilitadas nela (issue #209); e a fachada não recebe ator.
"""

import dataclasses
import inspect
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.facade import (
    StaffFunction,
    StaffReadFacade,
    StaffRecord,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)
from tests.fakes.features.staff.in_memory_staff_store import staff_repositories

pytestmark = pytest.mark.unit

_FERIAS = (datetime(2026, 11, 3, 0, 0), datetime(2026, 11, 5, 12, 30))


def _registro(
    eid: str,
    unidade: str = "u1",
    *,
    tenant: str = "t1",
    funcao: str = "cozinheiro",
    fixa: bool = True,
) -> Employee:
    return Employee(
        id=EmployeeId(eid),
        tenant_id=TenantId(tenant),
        unit_id=UnitId(unidade),
        name=f"Nome {eid}",
        workload_profile=FixedSchedule(Decimal("22.33")) if fixa else OnDemand(),
        shift_preference=None,
        job_function_ids=frozenset({JobFunctionId(funcao)}),
    )


@pytest.fixture
def fachada() -> StaffReadFacade:
    repos = staff_repositories()
    repos.job_functions.add(JobFunction(JobFunctionId("cozinheiro"), TenantId("t1"), "Cozinheiro"))
    repos.job_functions.add(JobFunction(JobFunctionId("atendente"), TenantId("t1"), "Atendente"))
    repos.job_functions.add(JobFunction(JobFunctionId("garcom"), TenantId("t2"), "Garçom"))
    # Habilitação por unidade (Stage 3.11): `caixa` vale só em u2; `barman`, de t2, nomeia
    # uma unidade com o mesmo id `u2` — e não vaza para t1.
    repos.job_functions.add(
        JobFunction(
            JobFunctionId("caixa"),
            TenantId("t1"),
            "Caixa",
            unit_enablement=UnitEnablement.only(frozenset({UnitId("u2")})),
        )
    )
    repos.job_functions.add(
        JobFunction(
            JobFunctionId("barman"),
            TenantId("t2"),
            "Barman",
            unit_enablement=UnitEnablement.only(frozenset({UnitId("u2")})),
        )
    )
    ana = dataclasses.replace(
        _registro("ana"), unavailabilities=(UnavailabilityPeriod(*_FERIAS),)
    ).link_login(UserId("user-ana"))
    repos.employees.add(ana)
    repos.employees.add(_registro("bia", fixa=False))
    repos.employees.add(_registro("caio").link_login(UserId("user-ana")).deactivate())
    repos.employees.add(_registro("ana-u2", "u2").link_login(UserId("user-ana")))
    repos.employees.add(
        _registro("dani", tenant="t2", funcao="garcom").link_login(UserId("user-ana"))
    )
    return StaffReadFacade(repos.employees, repos.job_functions)


def _ids(registros: tuple[StaffRecord, ...]) -> set[str]:
    return {r.employee_id for r in registros}


def test_ativos_da_unidade_e_so_eles(fachada: StaffReadFacade) -> None:
    assert _ids(fachada.list_active_records("t1", "u1")) == {"ana", "bia"}
    assert _ids(fachada.list_active_records("t1", "u2")) == {"ana-u2"}
    assert _ids(fachada.list_active_records("t2", "u1")) == {"dani"}
    assert fachada.list_active_records("t2", "u2") == ()


def test_lote_inclui_inativos_e_omite_o_que_nao_e_da_unidade(fachada: StaffReadFacade) -> None:
    pedidos = frozenset({"ana", "caio", "ana-u2", "dani", "zé"})
    devolvidos = fachada.list_records("t1", "u1", pedidos)
    assert {r.employee_id: r.active for r in devolvidos} == {"ana": True, "caio": False}
    assert fachada.list_records("t1", "u1", frozenset()) == ()


def test_vinculo_de_login_na_unidade_ativos_ou_nao(fachada: StaffReadFacade) -> None:
    assert _ids(fachada.list_records_of_user("t1", "u1", "user-ana")) == {"ana", "caio"}
    assert _ids(fachada.list_records_of_user("t1", "u2", "user-ana")) == {"ana-u2"}
    assert _ids(fachada.list_records_of_user("t2", "u1", "user-ana")) == {"dani"}
    assert fachada.list_records_of_user("t1", "u1", "user-outro") == ()


def test_catalogo_do_tenant_e_so_ele(fachada: StaffReadFacade) -> None:
    assert set(fachada.list_functions("t1")) == {
        StaffFunction("cozinheiro", "Cozinheiro"),
        StaffFunction("atendente", "Atendente"),
        StaffFunction("caixa", "Caixa"),
    }
    assert set(fachada.list_functions("t2")) == {
        StaffFunction("garcom", "Garçom"),
        StaffFunction("barman", "Barman"),
    }


def test_funcoes_da_unidade_sao_as_habilitadas_nela(fachada: StaffReadFacade) -> None:
    """Issue #209: "todas as unidades" entra em toda unidade; o conjunto, só nas que nomeia."""

    def _ids_de(tenant: str, unidade: str) -> set[str]:
        return {f.job_function_id for f in fachada.list_unit_functions(tenant, unidade)}

    assert _ids_de("t1", "u1") == {"cozinheiro", "atendente"}
    assert _ids_de("t1", "u2") == {"cozinheiro", "atendente", "caixa"}
    assert _ids_de("t2", "u1") == {"garcom"}
    assert _ids_de("t2", "u2") == {"garcom", "barman"}
    assert StaffFunction("caixa", "Caixa") in fachada.list_unit_functions("t1", "u2")
    assert all(
        type(f.job_function_id) is str and type(f.name) is str
        for f in fachada.list_unit_functions("t1", "u2")
    )


def test_o_registro_sai_inteiro_e_em_primitivos(fachada: StaffReadFacade) -> None:
    ana, bia = sorted(fachada.list_active_records("t1", "u1"), key=lambda r: r.employee_id)
    assert ana == StaffRecord(
        employee_id="ana",
        unit_id="u1",
        name="Nome ana",
        active=True,
        job_function_ids=frozenset({"cozinheiro"}),
        weekly_hours=Decimal("22.33"),
        unavailabilities=(_FERIAS,),
    )
    assert bia.weekly_hours is None
    for registro in (ana, bia):
        for campo in dataclasses.fields(registro):
            valor = getattr(registro, campo.name)
            assert type(valor) in {str, bool, frozenset, Decimal, tuple, type(None)}, campo.name
        assert all(type(f) is str for f in registro.job_function_ids)
        assert all(type(i) is datetime for par in registro.unavailabilities for i in par)
    assert type(ana.weekly_hours) is Decimal


def test_a_fachada_nao_recebe_ator_nem_expoe_o_login() -> None:
    for nome in (
        "list_active_records",
        "list_records",
        "list_records_of_user",
        "list_functions",
        "list_unit_functions",
    ):
        parametros = set(inspect.signature(getattr(StaffReadFacade, nome)).parameters)
        assert not {"actor", "ator"} & parametros, nome
    assert "user_id" not in {campo.name for campo in dataclasses.fields(StaffRecord)}

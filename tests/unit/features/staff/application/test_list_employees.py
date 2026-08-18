"""Use case `list_employees` — escopo por unidade (Task 09).

O que esta suíte protege é o **não-vazamento**: a listagem é a superfície mais
larga da camada, e é por ela que um erro de escopo apareceria como "dados do
outro restaurante na tela do gerente".
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.queries import ListEmployeesQuery
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_F1 = JobFunctionId("f1")
_FB = JobFunctionId("f-b")


def _com_funcoes() -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_FB, tenant_id=_B, name="Cozinheiro"))
    return fakes


def _grava(
    fakes: StaffFakes,
    id_: str,
    *,
    tenant: TenantId = _A,
    unit: UnitId = _U1,
    active: bool = True,
) -> None:
    fakes.employees.add(
        Employee(
            id=EmployeeId(id_),
            tenant_id=tenant,
            unit_id=unit,
            name=f"Funcionário {id_}",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F1 if tenant == _A else _FB}),
            active=active,
        )
    )


def _listar(fakes: StaffFakes) -> ListEmployeesUseCase:
    return ListEmployeesUseCase(fakes.employees)


def test_lista_os_registros_da_unidade_pedida() -> None:
    fakes = _com_funcoes()
    _grava(fakes, "e1")
    _grava(fakes, "e2")
    resultados = _listar(fakes).execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1))
    assert {resultado.id for resultado in resultados} == {"e1", "e2"}
    assert all(resultado.unit_id == _U1 for resultado in resultados)


def test_nao_vaza_registro_de_outra_unidade_nos_dois_sentidos() -> None:
    """Não-vazamento entre unidades — as duas direções, não uma."""
    fakes = _com_funcoes()
    _grava(fakes, "e1", unit=_U1)
    _grava(fakes, "e2", unit=_U2)

    da_u1 = _listar(fakes).execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1))
    assert {resultado.id for resultado in da_u1} == {"e1"}

    da_u2 = _listar(fakes).execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U2))
    assert {resultado.id for resultado in da_u2} == {"e2"}


def test_listar_com_tenant_de_outro_restaurante_devolve_vazio() -> None:
    """Nem erro, nem dado: a unidade simplesmente não tem registros para o B."""
    fakes = _com_funcoes()
    _grava(fakes, "e1")
    assert _listar(fakes).execute(ListEmployeesQuery(tenant_id=_B, unit_id=_U1)) == ()


def test_esconde_desligados_por_default() -> None:
    fakes = _com_funcoes()
    _grava(fakes, "e1")
    _grava(fakes, "e2", active=False)
    resultados = _listar(fakes).execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1))
    assert {resultado.id for resultado in resultados} == {"e1"}


def test_inclui_desligados_com_include_inactive() -> None:
    """O desligado **sobrevive**: some da lista default, não do sistema."""
    fakes = _com_funcoes()
    _grava(fakes, "e1")
    _grava(fakes, "e2", active=False)
    resultados = _listar(fakes).execute(
        ListEmployeesQuery(tenant_id=_A, unit_id=_U1, include_inactive=True)
    )
    assert {resultado.id for resultado in resultados} == {"e1", "e2"}
    assert {resultado.id for resultado in resultados if not resultado.active} == {"e2"}


def test_include_inactive_nao_atravessa_unidade_nem_tenant() -> None:
    """A flag amplia o **estado**, nunca o escopo.

    Sem este caso, um port que tratasse `include_inactive=True` como "traga
    tudo" passaria nos dois testes acima e vazaria unidade e tenant de uma vez.
    """
    fakes = _com_funcoes()
    _grava(fakes, "e1", unit=_U1, active=False)
    _grava(fakes, "e2", unit=_U2, active=False)
    _grava(fakes, "e3", tenant=_B, unit=_U1, active=False)

    resultados = _listar(fakes).execute(
        ListEmployeesQuery(tenant_id=_A, unit_id=_U1, include_inactive=True)
    )
    assert {resultado.id for resultado in resultados} == {"e1"}


def test_unidade_sem_registros_devolve_vazio() -> None:
    fakes = _com_funcoes()
    assert _listar(fakes).execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1)) == ()


def test_o_result_carrega_o_registro_campo_a_campo() -> None:
    """A listagem devolve **DTO**, não entidade — e com o conteúdo certo."""
    fakes = _com_funcoes()
    _grava(fakes, "e1")
    (resultado,) = _listar(fakes).execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1))
    gravado = fakes.employees.find_by_id(_A, _U1, EmployeeId("e1"))
    assert gravado is not None
    assert (
        resultado.id,
        resultado.tenant_id,
        resultado.unit_id,
        resultado.name,
        resultado.workload_profile,
        resultado.shift_preference,
        resultado.job_function_ids,
        resultado.unavailabilities,
        resultado.active,
    ) == (
        gravado.id,
        gravado.tenant_id,
        gravado.unit_id,
        gravado.name,
        gravado.workload_profile,
        gravado.shift_preference,
        gravado.job_function_ids,
        gravado.unavailabilities,
        gravado.active,
    )

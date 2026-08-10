"""Use case `delete_employee` — remoção definitiva (Task 12).

O irmão duro de `deactivate_employee`: aqui a história some. Existe para o
cadastro criado por engano, não para quem saiu da equipe.

O teste que mais importa é o da **ausência de produtor** de
`EmployeeInUseError` em v1: ele fixa como critério que a classe existe pelo
contrato do Step 4, e não por engano. Note que ele não cobre um `if` morto — o
use case **não tem** ramo que levante esse erro, deliberadamente (ver a
docstring do módulo de produção).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    DeactivateEmployeeCommand,
    DeleteEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import ListEmployeesQuery
from restaurant_hub.features.staff.application.errors import (
    EmployeeInUseError,
    EmployeeNotFoundError,
)
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
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
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)


def _fakes() -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    return fakes


def _grava(
    fakes: StaffFakes,
    *,
    id_: EmployeeId = _E1,
    funcoes: frozenset[JobFunctionId] = frozenset({_F1}),
    periodos: tuple[UnavailabilityPeriod, ...] = (),
    active: bool = True,
) -> None:
    fakes.employees.add(
        Employee(
            id=id_,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=funcoes,
            unavailabilities=periodos,
            active=active,
        )
    )


def _apagar(fakes: StaffFakes) -> DeleteEmployeeUseCase:
    return DeleteEmployeeUseCase(fakes.employees)


def test_remove_o_registro_definitivamente() -> None:
    fakes = _fakes()
    _grava(fakes)
    _apagar(fakes).execute(DeleteEmployeeCommand(tenant_id=_A, employee_id=_E1))
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_o_removido_some_das_duas_listagens() -> None:
    """Diferente do desligado, que só some de uma."""
    fakes = _fakes()
    _grava(fakes)
    _apagar(fakes).execute(DeleteEmployeeCommand(tenant_id=_A, employee_id=_E1))
    listar = ListEmployeesUseCase(fakes.employees)
    assert listar.execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1)) == ()
    assert (
        listar.execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1, include_inactive=True)) == ()
    )


def test_remover_desligado_tambem_funciona() -> None:
    """Apagar é ortogonal a desligar: o desligado é removível como qualquer um."""
    fakes = _fakes()
    _grava(fakes)
    DeactivateEmployeeUseCase(fakes.employees).execute(
        DeactivateEmployeeCommand(tenant_id=_A, employee_id=_E1)
    )
    _apagar(fakes).execute(DeleteEmployeeCommand(tenant_id=_A, employee_id=_E1))
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_remover_libera_a_funcao_que_o_registro_bloqueava() -> None:
    """O contrapositivo da guarda de L-JF3: sem referenciador, a função sai."""
    fakes = _fakes()
    _grava(fakes)
    _apagar(fakes).execute(DeleteEmployeeCommand(tenant_id=_A, employee_id=_E1))
    assert fakes.employees.exists_by_job_function(_A, _F1) is False


def test_registro_inexistente_e_not_found_sem_tentar_apagar() -> None:
    fakes = _fakes()
    antes = len(fakes.store.calls)
    with pytest.raises(EmployeeNotFoundError):
        _apagar(fakes).execute(
            DeleteEmployeeCommand(tenant_id=_A, employee_id=EmployeeId("fantasma"))
        )
    assert "employees.delete" not in fakes.store.calls[antes:]


def test_registro_de_outro_tenant_e_not_found_e_nao_e_removido() -> None:
    fakes = _fakes()
    _grava(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _apagar(fakes).execute(DeleteEmployeeCommand(tenant_id=_B, employee_id=_E1))

    assert "employees.delete" not in fakes.store.calls[antes:]
    assert fakes.employees.find_by_id(_A, _E1) is not None


@pytest.mark.parametrize(
    "cenario",
    ["ativo", "desligado", "varias-funcoes", "com-indisponibilidade", "completo"],
)
def test_nenhum_cenario_construivel_de_v1_produz_employee_in_use_error(cenario: str) -> None:
    """A ausência de produtor em v1 é **critério**, não esquecimento.

    Nada no escopo atual referencia o registro de funcionário: o que existe são
    referências **saindo** dele (funções) e valores **dentro** dele
    (indisponibilidades). Este teste percorre os cenários que v1 consegue
    montar e afirma que **todos** removem.

    Quem passa a produzir o erro é o Step 4 (alocação), pela FK da 3.3. O use
    case **não tem** ramo que o levante — se tivesse, seria código morto, e a
    cobertura de branch obrigaria alguém a mascará-lo com `pragma: no cover`.
    """
    fakes = _fakes()
    configuracoes = {
        "ativo": {},
        "desligado": {"active": False},
        "varias-funcoes": {"funcoes": frozenset({_F1, _F2})},
        "com-indisponibilidade": {"periodos": (_PERIODO,)},
        "completo": {
            "active": False,
            "funcoes": frozenset({_F1, _F2}),
            "periodos": (_PERIODO,),
        },
    }
    _grava(fakes, **configuracoes[cenario])  # type: ignore[arg-type]

    _apagar(fakes).execute(DeleteEmployeeCommand(tenant_id=_A, employee_id=_E1))
    assert fakes.employees.find_by_id(_A, _E1) is None


def test_employee_in_use_error_existe_e_e_instanciavel() -> None:
    """A classe é contrato publicado para o Step 4, não classe morta por engano."""
    assert "e-1" in str(EmployeeInUseError("e-1"))

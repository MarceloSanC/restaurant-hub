"""Use case `assign_job_functions` — validade referencial numa edição (Task 11).

Duas coisas separadas são travadas aqui: que o conjunto **substitui** (não
acumula) e que a validade referencial vale na edição como vale na criação.

Os caminhos de rejeição aserem `store.calls`: a lei L-E4 do port já recusaria a
escrita e levantaria o mesmo `JobFunctionNotFoundError`, então só a conduta —
`employees.update` **nem ser tentado** — distingue a guarda do use case da lei
do port (tabela ao final do concept §5).
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import AssignJobFunctionsCommand
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.use_cases.assign_job_functions import (
    AssignJobFunctionsUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmptyJobFunctionsError,
    StaffError,
)
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
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_F3 = JobFunctionId("f3")
_FB = JobFunctionId("f-b")


def _fakes() -> StaffFakes:
    fakes = staff_repositories()
    for id_, nome in ((_F1, "Cozinheiro"), (_F2, "Chapeiro"), (_F3, "Garçom")):
        fakes.job_functions.add(JobFunction(id=id_, tenant_id=_A, name=nome))
    fakes.job_functions.add(JobFunction(id=_FB, tenant_id=_B, name="Cozinheiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F1}),
        )
    )
    return fakes


def _atribuir(fakes: StaffFakes) -> AssignJobFunctionsUseCase:
    return AssignJobFunctionsUseCase(fakes.employees, fakes.job_functions)


def _conjunto_gravado(fakes: StaffFakes) -> frozenset[JobFunctionId]:
    employee = fakes.employees.find_by_id(_A, _E1)
    assert employee is not None
    return employee.job_function_ids


def test_atribuicao_substitui_o_conjunto_e_nao_acumula() -> None:
    """O command traz o estado final, não um delta.

    A asserção é de **igualdade**, não de continência: um use case que fizesse
    união passaria em `assert _F2 in gravado` e falharia aqui — e o registro
    acumularia funções que ninguém pediu, para sempre.
    """
    fakes = _fakes()
    resultado = _atribuir(fakes).execute(
        AssignJobFunctionsCommand(
            tenant_id=_A, unit_id=_U1, employee_id=_E1, job_function_ids=frozenset({_F2, _F3})
        )
    )
    assert resultado.job_function_ids == frozenset({_F2, _F3})
    assert _conjunto_gravado(fakes) == frozenset({_F2, _F3})
    assert _F1 not in _conjunto_gravado(fakes)


def test_atribuir_o_mesmo_conjunto_e_aceito() -> None:
    fakes = _fakes()
    resultado = _atribuir(fakes).execute(
        AssignJobFunctionsCommand(
            tenant_id=_A, unit_id=_U1, employee_id=_E1, job_function_ids=frozenset({_F1})
        )
    )
    assert resultado.job_function_ids == frozenset({_F1})


def test_funcao_inexistente_no_tenant_nao_grava() -> None:
    fakes = _fakes()
    antes = len(fakes.store.calls)
    with pytest.raises(JobFunctionNotFoundError):
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                job_function_ids=frozenset({JobFunctionId("f99")}),
            )
        )
    assert "employees.update" not in fakes.store.calls[antes:]
    assert _conjunto_gravado(fakes) == frozenset({_F1})


def test_funcao_de_outro_tenant_nao_grava() -> None:
    fakes = _fakes()
    antes = len(fakes.store.calls)
    with pytest.raises(JobFunctionNotFoundError):
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A, unit_id=_U1, employee_id=_E1, job_function_ids=frozenset({_FB})
            )
        )
    assert "employees.update" not in fakes.store.calls[antes:]
    assert _conjunto_gravado(fakes) == frozenset({_F1})


def test_conjunto_parcialmente_valido_e_rejeitado_inteiro() -> None:
    """Sem `calls`, um use case que só reprovasse quando NADA fosse encontrado
    passaria — a lei L-E4 do port levantaria o mesmo erro no `update`."""
    fakes = _fakes()
    antes = len(fakes.store.calls)
    with pytest.raises(JobFunctionNotFoundError):
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                job_function_ids=frozenset({_F2, JobFunctionId("f99")}),
            )
        )
    assert "employees.update" not in fakes.store.calls[antes:]
    assert _conjunto_gravado(fakes) == frozenset({_F1})


def test_id_de_funcao_ausente_reportada_e_deterministica() -> None:
    """Mesma determinância do `create_employee` (achado F-04).

    Vale nos dois porque os dois resolvem o mesmo conjunto — e um `sorted(...)`
    corrigido só num dos lados daria mensagens diferentes para a mesma falha,
    conforme o caminho.
    """
    fakes = _fakes()
    faltantes = frozenset({JobFunctionId("f97"), JobFunctionId("f99")})
    with pytest.raises(JobFunctionNotFoundError) as excecao:
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A, unit_id=_U1, employee_id=_E1, job_function_ids=faltantes
            )
        )
    assert "f97" in str(excecao.value)


def test_conjunto_vazio_e_erro_do_dominio_sem_gravar() -> None:
    fakes = _fakes()
    antes = len(fakes.store.calls)
    with pytest.raises(EmptyJobFunctionsError):
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A, unit_id=_U1, employee_id=_E1, job_function_ids=frozenset()
            )
        )
    assert "employees.update" not in fakes.store.calls[antes:]
    assert _conjunto_gravado(fakes) == frozenset({_F1})


def test_registro_inexistente_e_not_found() -> None:
    fakes = _fakes()
    with pytest.raises(EmployeeNotFoundError):
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                job_function_ids=frozenset({_F2}),
            )
        )


def test_registro_de_outro_tenant_e_not_found() -> None:
    fakes = _fakes()
    with pytest.raises(EmployeeNotFoundError):
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_B, unit_id=_U1, employee_id=_E1, job_function_ids=frozenset({_FB})
            )
        )
    assert _conjunto_gravado(fakes) == frozenset({_F1})


def test_precedencia_registro_inexistente_vence_funcao_inexistente() -> None:
    """Par duplo de §5.16: as duas checagens falham; **EmployeeNotFound vence**.

    E a ordem é observável: a resolução das funções nem chega a acontecer. Se
    ela viesse primeiro, a resposta a um id de funcionário inexistente diria
    algo sobre o **catálogo de funções** do tenant — informação de outro
    agregado, entregue a quem pediu por um registro que não existe.
    """
    fakes = _fakes()
    antes = len(fakes.store.calls)

    with pytest.raises(StaffError) as excecao:
        _atribuir(fakes).execute(
            AssignJobFunctionsCommand(
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                job_function_ids=frozenset({JobFunctionId("f99")}),
            )
        )
    assert type(excecao.value) is EmployeeNotFoundError

    conduta = fakes.store.calls[antes:]
    assert "job_functions.find_all_by_ids" not in conduta
    assert "employees.update" not in conduta

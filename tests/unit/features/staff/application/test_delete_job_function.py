"""Use case `delete_job_function` — a guarda de remoção (Task 08).

Esta suíte cobre a **segunda** regra cross-agregado delegada pela 3.1
(concept §5.9). O teste que mais importa é o de precedência: função do tenant A,
**referenciada**, apagada com `tenant_id` do B tem de devolver `NotFound` — o
erro não pode confirmar que ela existe *nem* que está em uso.
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import DeleteJobFunctionCommand
from restaurant_hub.features.staff.application.errors import (
    JobFunctionInUseError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError
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


def _com_funcao_no_tenant_a() -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    return fakes


def _funcionario(
    fakes: StaffFakes,
    *,
    tenant: TenantId = _A,
    unit: UnitId = _U1,
    funcao: JobFunctionId = _F1,
    active: bool = True,
) -> None:
    """Grava UM funcionário — cada teste desta suíte precisa de no máximo um."""
    fakes.employees.add(
        Employee(
            id=EmployeeId("e1"),
            tenant_id=tenant,
            unit_id=unit,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({funcao}),
            active=active,
        )
    )


def _apagar(fakes: StaffFakes) -> DeleteJobFunctionUseCase:
    return DeleteJobFunctionUseCase(fakes.job_functions, fakes.employees)


def test_remove_funcao_sem_referencias() -> None:
    fakes = _com_funcao_no_tenant_a()
    _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_A, job_function_id=_F1))
    assert fakes.job_functions.find_by_id(_A, _F1) is None


def test_funcao_referenciada_nao_e_removida_e_continua_legivel() -> None:
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes)
    with pytest.raises(JobFunctionInUseError):
        _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_A, job_function_id=_F1))
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_referenciador_em_outra_unidade_do_tenant_bloqueia() -> None:
    """A guarda é tenant-wide porque a **função** é tenant-scoped (workforce §3.2)."""
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes, unit=_U2)
    with pytest.raises(JobFunctionInUseError):
        _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_A, job_function_id=_F1))
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_referenciador_desligado_tambem_bloqueia() -> None:
    """O desligado sobrevive com a história e ainda aponta para a função.

    Uma implementação que contasse só ativos apagaria a função e deixaria o
    registro desligado apontando para função inexistente — furando a invariante
    "ao menos uma função" da 3.1 no momento em que alguém o recontratasse.
    """
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes, active=False)
    with pytest.raises(JobFunctionInUseError):
        _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_A, job_function_id=_F1))
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_referencia_de_outro_tenant_nao_bloqueia_a_remocao() -> None:
    """A guarda conta referências **do tenant da função**, não do mundo.

    O contrapositivo do teste anterior: sem ele, um fake que ignorasse
    `tenant_id` em `exists_by_job_function` passaria — e o restaurante A ficaria
    impedido de apagar a própria função por causa de um registro do B.
    """
    fakes = _com_funcao_no_tenant_a()
    fakes.job_functions.add(JobFunction(id=JobFunctionId("f-b"), tenant_id=_B, name="Cozinheiro"))
    _funcionario(fakes, tenant=_B, funcao=JobFunctionId("f-b"))

    _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_A, job_function_id=_F1))
    assert fakes.job_functions.find_by_id(_A, _F1) is None


def test_apagar_funcao_inexistente_e_not_found() -> None:
    fakes = staff_repositories()
    with pytest.raises(JobFunctionNotFoundError):
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(tenant_id=_A, job_function_id=JobFunctionId("fantasma"))
        )


def test_precedencia_not_found_vence_in_use_com_tenant_alheio() -> None:
    """Par duplo de §5.16: as duas checagens falhariam; **NotFound vence**.

    Este é o cenário em que a ordem importa de verdade. A função existe e está
    **em uso** no tenant A; o pedido vem com `tenant_id` do B. Se a guarda de
    referências rodasse primeiro, a resposta seria `JobFunctionInUseError` — e
    esse erro sozinho confirma ao tenant B que a função existe **e** que há
    alguém usando-a no restaurante alheio (§5.4).

    Asserção por **tipo exato**: `pytest.raises(JobFunctionNotFoundError)` puro
    não distinguiria "acertou a precedência" de "levantou outra coisa".
    """
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes)  # a função está EM USO no tenant A

    with pytest.raises(StaffError) as excecao:
        _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_B, job_function_id=_F1))
    assert type(excecao.value) is JobFunctionNotFoundError
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_apagar_funcao_de_outro_tenant_sem_referencias_tambem_e_not_found() -> None:
    """A meia-verdade do teste acima, isolada: nem sem uso o tenant B a alcança."""
    fakes = _com_funcao_no_tenant_a()
    with pytest.raises(JobFunctionNotFoundError):
        _apagar(fakes).execute(DeleteJobFunctionCommand(tenant_id=_B, job_function_id=_F1))
    assert fakes.job_functions.find_by_id(_A, _F1) is not None

"""Testes da **forma** do par acoplado de fakes do BC staff (Task 05).

Aqui se trava o que o par É — round-trip, store compartilhado, alcance do
registro de chamadas. O que o par **obedece** (as doze leis) é a Task 06.

O par existe porque L-JF3 e L-E4 falam de dados do **outro** agregado: fakes
isolados não conseguiriam impô-las, e a Stage fecharia com lei declarada e não
implementada. Por isso o teste central deste módulo é o de que os dois fakes
enxergam **o mesmo** store — sem ele, todo o resto passaria vacuamente.
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.errors import JobFunctionInUseError
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import (
    InMemoryStaffStore,
    StaffFakes,
    staff_repositories,
)

pytestmark = pytest.mark.unit

_TENANT = TenantId("t1")
_UNIDADE = UnitId("u1")


def _funcao(id_: str = "f1", *, tenant: str = "t1", name: str = "Cozinheiro") -> JobFunction:
    return JobFunction(id=JobFunctionId(id_), tenant_id=TenantId(tenant), name=name)


def _funcionario(
    id_: str = "e1",
    *,
    tenant: str = "t1",
    unit: str = "u1",
    funcoes: frozenset[JobFunctionId] = frozenset({JobFunctionId("f1")}),
    active: bool = True,
) -> Employee:
    return Employee(
        id=EmployeeId(id_),
        tenant_id=TenantId(tenant),
        unit_id=UnitId(unit),
        name="Maria",
        workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
        shift_preference=None,
        job_function_ids=funcoes,
        active=active,
    )


# --- forma do holder ---------------------------------------------------------


def test_helper_devolve_os_tres_objetos_num_holder_frozen() -> None:
    """O store vem no holder, e não só o par.

    Sem ele, os critérios "não tocou o port" das Tasks 07+ só alcançariam
    `calls` por atributo de um dos fakes — acoplando a suíte à representação
    interna do fake, que é o que a skill `pytest-with-fakes` manda evitar.
    """
    fakes = staff_repositories()
    assert isinstance(fakes, StaffFakes)
    assert isinstance(fakes.store, InMemoryStaffStore)
    assert fakes.store.calls == []


def test_cada_chamada_ao_par_e_registrada_no_store() -> None:
    """`calls` é o que permite asserir "o use case NÃO consultou o port"."""
    fakes = staff_repositories()
    fakes.job_functions.find_by_name(_TENANT, "Cozinheiro")
    fakes.employees.list_by_unit(_TENANT, _UNIDADE)
    assert fakes.store.calls == ["job_functions.find_by_name", "employees.list_by_unit"]


def test_dois_helpers_nao_compartilham_estado() -> None:
    """Cada teste da Stage parte de um store limpo — do contrário a ordem importaria."""
    primeiro = staff_repositories()
    primeiro.job_functions.add(_funcao())
    assert staff_repositories().job_functions.find_by_id(_TENANT, JobFunctionId("f1")) is None


# --- round-trip --------------------------------------------------------------


def test_round_trip_de_funcao() -> None:
    fakes = staff_repositories()
    funcao = _funcao()
    fakes.job_functions.add(funcao)
    gravada = fakes.job_functions.find_by_id(_TENANT, JobFunctionId("f1"))
    assert gravada is not None
    # Comparação campo a campo: `JobFunction.__eq__` compara só por id, então
    # `assert gravada == funcao` passaria mesmo com o nome corrompido.
    assert (gravada.id, gravada.tenant_id, gravada.name) == (
        funcao.id,
        funcao.tenant_id,
        funcao.name,
    )


def test_funcao_inexistente_devolve_none() -> None:
    fakes = staff_repositories()
    assert fakes.job_functions.find_by_id(_TENANT, JobFunctionId("fantasma")) is None


def test_round_trip_de_funcionario() -> None:
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao())
    funcionario = _funcionario()
    fakes.employees.add(funcionario)
    gravado = fakes.employees.find_by_id(_TENANT, EmployeeId("e1"))
    assert gravado is not None
    assert (gravado.id, gravado.unit_id, gravado.name, gravado.job_function_ids) == (
        funcionario.id,
        funcionario.unit_id,
        funcionario.name,
        funcionario.job_function_ids,
    )


def test_funcionario_inexistente_devolve_none() -> None:
    fakes = staff_repositories()
    assert fakes.employees.find_by_id(_TENANT, EmployeeId("fantasma")) is None


# --- o par é acoplado: um store, duas visões ---------------------------------


def test_funcao_gravada_por_uma_visao_e_vista_pela_guarda_da_outra() -> None:
    """Checagem básica de L-E4: sem store único, o `add` do funcionário
    rejeitaria uma função que acabou de ser gravada."""
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao())
    fakes.employees.add(_funcionario())  # não levanta JobFunctionNotFoundError
    assert fakes.employees.find_by_id(_TENANT, EmployeeId("e1")) is not None


def test_funcionario_gravado_por_uma_visao_e_visto_pela_guarda_da_outra() -> None:
    """Checagem básica de L-JF3, no sentido inverso: sem store único, a remoção
    da função não enxergaria o referenciador e apagaria a função em uso."""
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao())
    fakes.employees.add(_funcionario())
    with pytest.raises(JobFunctionInUseError):
        fakes.job_functions.delete(_TENANT, JobFunctionId("f1"))


def test_as_duas_visoes_escrevem_no_mesmo_store() -> None:
    """Prova direta do acoplamento, sem passar por lei nenhuma."""
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao())
    fakes.employees.add(_funcionario())
    assert set(fakes.store.job_functions) == {JobFunctionId("f1")}
    assert set(fakes.store.employees) == {EmployeeId("e1")}

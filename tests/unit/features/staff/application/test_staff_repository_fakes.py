"""Testes da **forma** do par acoplado de fakes do BC staff (Task 05).

Aqui se trava o que o par É — round-trip, store compartilhado, alcance do
registro de chamadas. O que o par **obedece** (as doze leis) é a Task 06.

O par existe porque L-JF3 e L-E4 falam de dados do **outro** agregado: fakes
isolados não conseguiriam impô-las, e a Stage fecharia com lei declarada e não
implementada. Por isso o teste central deste módulo é o de que os dois fakes
enxergam **o mesmo** store — sem ele, todo o resto passaria vacuamente.
"""

import contextlib
import inspect
from collections.abc import Callable
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.errors import JobFunctionInUseError
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
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


def _metodos_publicos(port: type) -> set[str]:
    """Nomes dos métodos declarados no `Protocol` — a fonte da verdade do par."""
    return {
        nome for nome, _ in inspect.getmembers(port, inspect.isfunction) if not nome.startswith("_")
    }


def _invocacoes(fakes: StaffFakes) -> list[tuple[str, Callable[[], object]]]:
    """Uma invocação por método do par, na ordem em que o estado as permite.

    O valor devolvido e o erro levantado são irrelevantes aqui: o que se mede é
    se a chamada **foi registrada**. Por isso as chamadas que levantam
    (`update` de inexistente, `delete`) entram na lista sem cerimônia — o
    `record()` acontece antes de qualquer guarda, e é justamente essa ordem que
    faz `calls` valer como evidência de "o port foi tocado".
    """
    nova = _funcao(id_="f-nova", name="Nova")
    return [
        ("job_functions.add", lambda: fakes.job_functions.add(nova)),
        ("job_functions.update", lambda: fakes.job_functions.update(nova)),
        (
            "job_functions.find_by_id",
            lambda: fakes.job_functions.find_by_id(_TENANT, JobFunctionId("f-nova")),
        ),
        ("job_functions.find_by_name", lambda: fakes.job_functions.find_by_name(_TENANT, "Nova")),
        (
            "job_functions.find_all_by_ids",
            lambda: fakes.job_functions.find_all_by_ids(
                _TENANT, frozenset({JobFunctionId("f-nova")})
            ),
        ),
        ("job_functions.list_by_tenant", lambda: fakes.job_functions.list_by_tenant(_TENANT)),
        (
            "job_functions.delete",
            lambda: fakes.job_functions.delete(_TENANT, JobFunctionId("f-nova")),
        ),
        ("employees.add", lambda: fakes.employees.add(_funcionario(id_="e-novo"))),
        ("employees.update", lambda: fakes.employees.update(_funcionario(id_="e-novo"))),
        (
            "employees.find_by_id",
            lambda: fakes.employees.find_by_id(_TENANT, _UNIDADE, EmployeeId("e-novo")),
        ),
        ("employees.list_by_unit", lambda: fakes.employees.list_by_unit(_TENANT, _UNIDADE)),
        (
            "employees.exists_by_job_function",
            lambda: fakes.employees.exists_by_job_function(_TENANT, JobFunctionId("f1")),
        ),
        (
            "employees.delete",
            lambda: fakes.employees.delete(_TENANT, _UNIDADE, EmployeeId("e-novo")),
        ),
    ]


def test_todo_metodo_do_par_registra_exatamente_uma_chamada() -> None:
    """Cada um dos 13 métodos do par tem o seu `record()` travado por teste.

    **Por que isto não é zelo excessivo.** `store.calls` sustenta todos os
    critérios "sem tocar o port" das Tasks 07/09/13 — e um critério desses é
    uma asserção sobre uma lista **vazia**. Se um `record()` sumir, a asserção
    vira **vacuamente verdadeira**: o teste continua verde enquanto o use case
    consulta o port justamente onde não deveria. Evidência de ausência só vale
    se a presença estiver garantida em todos os caminhos.
    """
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao())  # estado mínimo para as invocações

    for esperado, invocar in _invocacoes(fakes):
        antes = len(fakes.store.calls)
        # O erro é irrelevante aqui — o registro da chamada não é.
        with contextlib.suppress(StaffError):
            invocar()
        registradas = fakes.store.calls[antes:]
        assert registradas == [esperado], f"{esperado} não registrou exatamente uma chamada"


def test_as_invocacoes_cobrem_todo_metodo_declarado_nos_dois_protocolos() -> None:
    """A lista acima **é** a superfície do par, não uma amostra dela.

    Sem esta asserção, um 14º método de port entraria sem `record()` e sem
    ninguém notar — e a Task seguinte herdaria um `calls` incompleto, que é o
    mesmo defeito de fundo do achado anterior sobre listas literais.
    """
    esperados = {nome for nome, _ in _invocacoes(staff_repositories())}
    declarados = {f"job_functions.{nome}" for nome in _metodos_publicos(JobFunctionRepository)} | {
        f"employees.{nome}" for nome in _metodos_publicos(EmployeeRepository)
    }
    assert esperados == declarados


@pytest.mark.parametrize("metodo", ["find_by_id", "delete"])
def test_ca11_o_endereco_do_funcionario_tem_tres_partes_na_assinatura(metodo: str) -> None:
    """CA11, metade mecânica: `(tenant_id, unit_id, employee_id)`, nesta ordem.

    **Por que uma asserção de assinatura, se `mypy` já a cobre.** `make typecheck`
    é `mypy src/ tests/fakes/` — ele **não** alcança `tests/integration/`. Lá um
    call site de duas partes não vira erro de tipo: vira `TypeError` na execução,
    e só se aquele caminho for exercitado. Esta asserção põe a aridade sob o
    alcance da suíte, que roda inteira.

    A **ordem** dos nomes importa tanto quanto a contagem: `UnitId` e
    `EmployeeId` são `NewType` distintos, então trocá-los é erro de tipo em
    `src/` — mas fora do alcance do `mypy` o troco passaria calado, e um
    `find_by_id(tenant, employee_id, unit_id)` acharia sempre `None`,
    convertendo a lei de isolamento em recusa universal.
    """
    parametros = list(inspect.signature(getattr(EmployeeRepository, metodo)).parameters)

    assert parametros == ["self", "tenant_id", "unit_id", "employee_id"]
    # O fake é a segunda implementação, e carrega a mesma lei (ADR 3.4.0007 §2).
    concreto = list(inspect.signature(getattr(staff_repositories().employees, metodo)).parameters)
    assert concreto == ["tenant_id", "unit_id", "employee_id"]


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
    gravado = fakes.employees.find_by_id(_TENANT, _UNIDADE, EmployeeId("e1"))
    assert gravado is not None
    assert (gravado.id, gravado.unit_id, gravado.name, gravado.job_function_ids) == (
        funcionario.id,
        funcionario.unit_id,
        funcionario.name,
        funcionario.job_function_ids,
    )


def test_funcionario_inexistente_devolve_none() -> None:
    fakes = staff_repositories()
    assert fakes.employees.find_by_id(_TENANT, _UNIDADE, EmployeeId("fantasma")) is None


# --- o par é acoplado: um store, duas visões ---------------------------------


def test_funcao_gravada_por_uma_visao_e_vista_pela_guarda_da_outra() -> None:
    """Checagem básica de L-E4: sem store único, o `add` do funcionário
    rejeitaria uma função que acabou de ser gravada."""
    fakes = staff_repositories()
    fakes.job_functions.add(_funcao())
    fakes.employees.add(_funcionario())  # não levanta JobFunctionNotFoundError
    assert fakes.employees.find_by_id(_TENANT, _UNIDADE, EmployeeId("e1")) is not None


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

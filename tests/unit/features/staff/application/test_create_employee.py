"""Use case `create_employee` — validade referencial do conjunto (Task 09).

Cobre a terceira regra cross-agregado delegada pela 3.1 (concept §5.8) e o par
duplo de precedência que a acompanha: nome vazio **e** função inexistente
⇒ vence `JobFunctionNotFoundError`, porque a falha real do pedido é
referencial.
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import CreateEmployeeCommand
from restaurant_hub.features.staff.application.errors import JobFunctionNotFoundError
from restaurant_hub.features.staff.application.use_cases.create_employee import (
    CreateEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmptyJobFunctionsError,
    InvalidNameError,
    StaffError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_FIXA = FixedSchedule(weekly_hours=Decimal("44"))


def _com_funcoes() -> StaffFakes:
    """`f1`/`f2` no tenant A e `f-b` no tenant B."""
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    fakes.job_functions.add(JobFunction(id=JobFunctionId("f-b"), tenant_id=_B, name="Cozinheiro"))
    return fakes


def _comando(
    *,
    name: str = "Maria",
    funcoes: frozenset[JobFunctionId] = frozenset({_F1}),
    preferencia: ShiftPreference | None = None,
) -> CreateEmployeeCommand:
    return CreateEmployeeCommand(
        tenant_id=_A,
        unit_id=_U1,
        name=name,
        workload_profile=_FIXA,
        job_function_ids=funcoes,
        shift_preference=preferencia,
    )


def _criar(fakes: StaffFakes, gerador: FakeIdGenerator | None = None) -> CreateEmployeeUseCase:
    return CreateEmployeeUseCase(fakes.employees, fakes.job_functions, gerador or FakeIdGenerator())


# --- caminho feliz -----------------------------------------------------------


def test_cria_registro_ativo_com_o_conjunto_pedido() -> None:
    fakes = _com_funcoes()
    gerador = FakeIdGenerator()
    resultado = _criar(fakes, gerador).execute(_comando(funcoes=frozenset({_F1, _F2})))

    # Conversão canônica do id (concept §5.3).
    assert resultado.id == str(gerador.generated[0])
    assert resultado.active is True
    assert resultado.job_function_ids == frozenset({_F1, _F2})

    gravado = fakes.employees.find_by_id(_A, EmployeeId(resultado.id))
    assert gravado is not None
    assert (gravado.name, gravado.unit_id, gravado.job_function_ids, gravado.active) == (
        "Maria",
        _U1,
        frozenset({_F1, _F2}),
        True,
    )


def test_cria_registro_com_preferencia_declarada() -> None:
    fakes = _com_funcoes()
    preferencia = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
    resultado = _criar(fakes).execute(_comando(preferencia=preferencia))
    assert resultado.shift_preference == preferencia
    gravado = fakes.employees.find_by_id(_A, EmployeeId(resultado.id))
    assert gravado is not None
    assert gravado.shift_preference == preferencia


def test_cria_registro_sob_demanda() -> None:
    fakes = _com_funcoes()
    comando = CreateEmployeeCommand(
        tenant_id=_A,
        unit_id=_U1,
        name="Maria",
        workload_profile=OnDemand(),
        job_function_ids=frozenset({_F1}),
    )
    resultado = _criar(fakes).execute(comando)
    assert resultado.workload_profile == OnDemand()
    # Releitura pelo port, como o resto da suíte: o result é o que o use case
    # diz ter feito; a releitura é o que ele gravou.
    gravado = fakes.employees.find_by_id(_A, EmployeeId(resultado.id))
    assert gravado is not None
    assert gravado.workload_profile == OnDemand()


def test_registro_novo_nasce_sem_indisponibilidades() -> None:
    fakes = _com_funcoes()
    assert _criar(fakes).execute(_comando()).unavailabilities == ()


def test_nome_e_gravado_verbatim() -> None:
    fakes = _com_funcoes()
    resultado = _criar(fakes).execute(_comando(name="  Maria "))
    gravado = fakes.employees.find_by_id(_A, EmployeeId(resultado.id))
    assert gravado is not None
    assert gravado.name == "  Maria "


# --- validade referencial ----------------------------------------------------


def test_funcao_inexistente_no_tenant_e_not_found_sem_tentar_gravar() -> None:
    fakes = _com_funcoes()
    antes = len(fakes.store.calls)
    with pytest.raises(JobFunctionNotFoundError):
        _criar(fakes).execute(_comando(funcoes=frozenset({JobFunctionId("f99")})))
    assert "employees.add" not in fakes.store.calls[antes:]
    assert fakes.employees.list_by_unit(_A, _U1, include_inactive=True) == ()


def test_funcao_existente_em_outro_tenant_e_not_found() -> None:
    """A resolução é escopada: id de função alheia conta como **ausente**."""
    fakes = _com_funcoes()
    antes = len(fakes.store.calls)
    with pytest.raises(JobFunctionNotFoundError):
        _criar(fakes).execute(_comando(funcoes=frozenset({JobFunctionId("f-b")})))
    assert "employees.add" not in fakes.store.calls[antes:]
    assert fakes.employees.list_by_unit(_A, _U1, include_inactive=True) == ()


def test_conjunto_parcialmente_valido_e_rejeitado_inteiro_sem_tentar_gravar() -> None:
    """A regra é sobre **toda** id do conjunto, não sobre "alguma existir".

    A asserção sobre `calls` é o que dá dente ao teste. Sem ela, um use case
    que só reprovasse o conjunto quando **nenhuma** função fosse encontrada
    (`if ausentes and not encontradas`) passaria: o `add` seria chamado e a lei
    L-E4 do port levantaria o mesmo `JobFunctionNotFoundError`. O resultado
    seria idêntico e a regra do use case, inexistente — que é precisamente a
    diferença entre as duas camadas de enforcement da tabela do concept §5.
    """
    fakes = _com_funcoes()
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionNotFoundError):
        _criar(fakes).execute(_comando(funcoes=frozenset({_F1, JobFunctionId("f99")})))

    assert "employees.add" not in fakes.store.calls[antes:]
    assert fakes.employees.list_by_unit(_A, _U1, include_inactive=True) == ()


def test_conjunto_vazio_e_erro_do_dominio() -> None:
    """Não é caso especial no use case: nada falta, e o agregado é quem recusa.

    `find_all_by_ids(frozenset())` devolve vazio, nenhuma id está ausente, e o
    `EmptyJobFunctionsError` sobe na construção — sem reembrulho (§5.15).
    """
    fakes = _com_funcoes()
    with pytest.raises(EmptyJobFunctionsError):
        _criar(fakes).execute(_comando(funcoes=frozenset()))


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_erro_do_dominio(invalido: str) -> None:
    fakes = _com_funcoes()
    with pytest.raises(InvalidNameError):
        _criar(fakes).execute(_comando(name=invalido))
    assert fakes.employees.list_by_unit(_A, _U1, include_inactive=True) == ()


def test_precedencia_funcao_inexistente_vence_nome_vazio() -> None:
    """Par duplo de §5.16: as duas checagens falham; **a referencial vence**.

    A ordem é o que decide qual causa o gerente lê. Construir a entidade
    primeiro devolveria `InvalidNameError` para um pedido cuja falha real é a
    função que não existe — e ele corrigiria o nome para bater no mesmo erro de
    novo. Asserção por **tipo exato**.
    """
    fakes = _com_funcoes()
    with pytest.raises(StaffError) as excecao:
        _criar(fakes).execute(_comando(name="", funcoes=frozenset({JobFunctionId("f99")})))
    assert type(excecao.value) is JobFunctionNotFoundError


def test_conjunto_vazio_nunca_produz_erro_referencial() -> None:
    """O contrapositivo do par duplo: com conjunto **vazio** não há id ausente.

    Fixa que a checagem referencial não inventa uma ausência a partir do nada —
    o vazio é problema do agregado, não do catálogo.

    A asserção é **negativa** de propósito. Qual dos dois erros de domínio
    aparece quando o nome também é inválido é decidido pela ordem dos campos no
    `__post_init__` da 3.1 (nome antes do conjunto), **não** por este use case:
    afirmar um deles aqui travaria como contrato desta camada uma decisão que
    pertence à entidade, e o teste quebraria numa reordenação legítima de lá.
    O que **é** garantia deste use case é a negativa.
    """
    fakes = _com_funcoes()
    with pytest.raises(StaffError) as excecao:
        _criar(fakes).execute(_comando(name="", funcoes=frozenset()))
    assert not isinstance(excecao.value, JobFunctionNotFoundError)
    assert fakes.employees.list_by_unit(_A, _U1, include_inactive=True) == ()

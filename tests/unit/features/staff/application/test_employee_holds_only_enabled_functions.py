"""Um registro só detém função habilitada na sua unidade (Stage 3.11, ADR 3.11.0002).

A regra é **uma** e tem três produtores nesta camada — criar o registro, atribuir
funções e copiar para outra unidade —, e por isso mora num módulo só: o que se
trava aqui é a propriedade, e não cada use case por representante. O quarto
ponto, estreitar a habilitação, é do `test_set_job_function_units.py`.

Em cada produtor confere-se o mesmo par: a recusa **e** a ausência da escrita
(`store.calls`), porque o fake de repositório não impõe a regra — nenhuma
constraint a expressa (ADR 3.11.0002, "Declared limit") —, e um use case sem a
checagem gravaria o registro em silêncio.
"""

from collections.abc import Callable
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    AssignJobFunctionsCommand,
    CopyEmployeeToUnitCommand,
    CreateEmployeeCommand,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    JobFunctionNotEnabledInUnitError,
    JobFunctionNotFoundError,
    SameUnitCopyError,
)
from restaurant_hub.features.staff.application.use_cases.assign_job_functions import (
    AssignJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.copy_employee_to_unit import (
    CopyEmployeeToUnitUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_employee import (
    CreateEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_T = TenantId("tenant-a")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_F_TODAS = JobFunctionId("f-todas")
_F_U1 = JobFunctionId("f-u1")
_F_U2 = JobFunctionId("f-u2")
_F_U2_B = JobFunctionId("a-tambem-so-u2")  # menor que `f-u2` na ordem de id
_F_AMBAS = JobFunctionId("f-u1-u2")
_FIXA = FixedSchedule(weekly_hours=Decimal("44"))


def _mundo(*, funcoes_do_registro: frozenset[JobFunctionId] = frozenset({_F_U1})) -> StaffFakes:
    """Catálogo com uma função de cada habilitação, e `e1` em u1."""
    fakes = staff_repositories()
    for id_, nome, habilitacao in (
        (_F_TODAS, "Cozinheiro", UnitEnablement.everywhere()),
        (_F_U1, "Atendente", UnitEnablement.only(frozenset({_U1}))),
        (_F_U2, "Barman", UnitEnablement.only(frozenset({_U2}))),
        (_F_U2_B, "Sommelier", UnitEnablement.only(frozenset({_U2}))),
        (_F_AMBAS, "Caixa", UnitEnablement.only(frozenset({_U1, _U2}))),
    ):
        fakes.job_functions.add(
            JobFunction(id=id_, tenant_id=_T, name=nome, unit_enablement=habilitacao)
        )
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_T,
            unit_id=_U1,
            name="Maria",
            workload_profile=_FIXA,
            shift_preference=None,
            job_function_ids=funcoes_do_registro,
        )
    )
    return fakes


def _criar(
    fakes: StaffFakes, ids: FakeIdGenerator, funcoes: frozenset[JobFunctionId], unidade: UnitId
) -> object:
    return CreateEmployeeUseCase(
        fakes.employees, fakes.job_functions, ids, guard=PermissiveAccessGuard()
    ).execute(
        CreateEmployeeCommand(
            actor=TEST_ACTOR,
            tenant_id=_T,
            unit_id=unidade,
            name="João",
            workload_profile=_FIXA,
            job_function_ids=funcoes,
            shift_preference=None,
        )
    )


def _atribuir(
    fakes: StaffFakes, ids: FakeIdGenerator, funcoes: frozenset[JobFunctionId], unidade: UnitId
) -> object:
    return AssignJobFunctionsUseCase(
        fakes.employees, fakes.job_functions, guard=PermissiveAccessGuard()
    ).execute(
        AssignJobFunctionsCommand(
            actor=TEST_ACTOR,
            tenant_id=_T,
            unit_id=unidade,
            employee_id=_E1,
            job_function_ids=funcoes,
        )
    )


def _copiar(
    fakes: StaffFakes, ids: FakeIdGenerator, destino: UnitId, origem: UnitId = _U1
) -> object:
    return CopyEmployeeToUnitUseCase(
        fakes.employees, fakes.job_functions, ids, guard=PermissiveAccessGuard()
    ).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR,
            tenant_id=_T,
            unit_id=origem,
            employee_id=_E1,
            target_unit_id=destino,
        )
    )


Produtor = Callable[[StaffFakes, FakeIdGenerator, frozenset[JobFunctionId], UnitId], object]

_CRIAR_E_ATRIBUIR: dict[str, Produtor] = {"criar": _criar, "atribuir": _atribuir}


def _escritas_de_funcionario(fakes: StaffFakes, desde: int) -> list[str]:
    return [
        chamada
        for chamada in fakes.store.calls[desde:]
        if chamada in ("employees.add", "employees.update")
    ]


# --- criar e atribuir (CA6) ---------------------------------------------------


@pytest.mark.parametrize("produtor", sorted(_CRIAR_E_ATRIBUIR))
def test_ca6_funcao_nao_habilitada_na_unidade_do_registro_e_recusada_sem_gravar(
    produtor: str,
) -> None:
    fakes = _mundo()
    ids = FakeIdGenerator()
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionNotEnabledInUnitError) as excinfo:
        _CRIAR_E_ATRIBUIR[produtor](fakes, ids, frozenset({_F_TODAS, _F_U2}), _U1)

    assert str(excinfo.value) == ("função de trabalho 'f-u2' não está habilitada na unidade 'u1'")
    assert _escritas_de_funcionario(fakes, antes) == []
    assert ids.generated == []
    assert [e.id for e in fakes.employees.list_by_unit(_T, _U1)] == [_E1]
    gravado = fakes.employees.find_by_id(_T, _U1, _E1)
    assert gravado is not None
    assert gravado.job_function_ids == frozenset({_F_U1})


@pytest.mark.parametrize("produtor", sorted(_CRIAR_E_ATRIBUIR))
@pytest.mark.parametrize(
    "funcoes",
    [frozenset({_F_TODAS}), frozenset({_F_U1}), frozenset({_F_AMBAS, _F_TODAS, _F_U1})],
    ids=["todas", "so-da-unidade", "mistura-que-cobre"],
)
def test_ca6_funcao_que_cobre_a_unidade_e_aceita(
    produtor: str, funcoes: frozenset[JobFunctionId]
) -> None:
    """O lado positivo: "todas" e o conjunto que nomeia a unidade valem igual."""
    fakes = _mundo()

    resultado = _CRIAR_E_ATRIBUIR[produtor](fakes, FakeIdGenerator(), funcoes, _U1)

    assert resultado.job_function_ids == funcoes  # type: ignore[attr-defined]


@pytest.mark.parametrize("produtor", sorted(_CRIAR_E_ATRIBUIR))
def test_r10_com_varias_fora_da_unidade_o_erro_nomeia_a_menor_id(produtor: str) -> None:
    fakes = _mundo()

    with pytest.raises(JobFunctionNotEnabledInUnitError, match="'a-tambem-so-u2'"):
        _CRIAR_E_ATRIBUIR[produtor](
            fakes, FakeIdGenerator(), frozenset({_F_U2, _F_U2_B, _F_U1}), _U1
        )


@pytest.mark.parametrize("produtor", sorted(_CRIAR_E_ATRIBUIR))
def test_funcao_inexistente_vence_funcao_fora_da_unidade(produtor: str) -> None:
    """A checagem referencial vem antes (R8): 404 da função, não 409 da habilitação."""
    fakes = _mundo()

    with pytest.raises(JobFunctionNotFoundError):
        _CRIAR_E_ATRIBUIR[produtor](
            fakes, FakeIdGenerator(), frozenset({_F_U2, JobFunctionId("nao-existe")}), _U1
        )


def test_atribuir_a_registro_inexistente_vence_a_habilitacao() -> None:
    """`EmployeeNotFoundError` primeiro: id alheio não aprende nada do catálogo."""
    fakes = _mundo()

    with pytest.raises(EmployeeNotFoundError):
        _atribuir(fakes, FakeIdGenerator(), frozenset({_F_U2}), _U2)  # e1 mora em u1


# --- copiar (CA5) -------------------------------------------------------------


def test_ca5_copia_para_unidade_onde_a_funcao_nao_vale_e_recusada_sem_gravar() -> None:
    """Recusar — não habilita junto, não copia assim mesmo, não descarta a função."""
    fakes = _mundo(funcoes_do_registro=frozenset({_F_TODAS, _F_U1}))
    ids = FakeIdGenerator()
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionNotEnabledInUnitError) as excinfo:
        _copiar(fakes, ids, _U2)

    assert str(excinfo.value) == ("função de trabalho 'f-u1' não está habilitada na unidade 'u2'")
    conduta = fakes.store.calls[antes:]
    assert "employees.add" not in conduta
    assert "job_functions.update_enablement" not in conduta  # não habilita junto
    assert ids.generated == []
    assert fakes.employees.list_by_unit(_T, _U2) == ()
    funcao = fakes.job_functions.find_by_id(_T, _F_U1)
    assert funcao is not None
    assert funcao.unit_enablement == UnitEnablement.only(frozenset({_U1}))


@pytest.mark.parametrize(
    "funcoes",
    [frozenset({_F_TODAS}), frozenset({_F_AMBAS}), frozenset({_F_TODAS, _F_AMBAS})],
    ids=["todas", "nas-duas", "mistura"],
)
def test_ca5_copia_com_todas_as_funcoes_valendo_no_destino_e_aceita(
    funcoes: frozenset[JobFunctionId],
) -> None:
    fakes = _mundo(funcoes_do_registro=funcoes)

    copia = _copiar(fakes, FakeIdGenerator(), _U2)

    assert copia.unit_id == _U2  # type: ignore[attr-defined]
    assert copia.job_function_ids == funcoes  # type: ignore[attr-defined]


def test_ca5_a_resolucao_das_funcoes_vem_depois_da_origem_e_antes_da_escrita() -> None:
    fakes = _mundo(funcoes_do_registro=frozenset({_F_AMBAS}))
    antes = len(fakes.store.calls)

    _copiar(fakes, FakeIdGenerator(), _U2)

    assert fakes.store.calls[antes:] == [
        "employees.find_by_id",
        "job_functions.find_all_by_ids",
        "employees.add",
    ]


def test_ca5_origem_inexistente_vence_a_habilitacao() -> None:
    """404 antes de 409: o registro endereçado pela unidade errada não revela o catálogo."""
    fakes = _mundo(funcoes_do_registro=frozenset({_F_U1}))
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _copiar(fakes, FakeIdGenerator(), _U1, origem=_U2)

    assert "job_functions.find_all_by_ids" not in fakes.store.calls[antes:]


def test_ca5_mesma_unidade_vence_a_habilitacao() -> None:
    """422 antes de 409 — inclusive para um registro que já detém função fora da unidade.

    O estado (função restrita a u2 num registro de u1) é o que a corrida declarada
    no ADR 3.11.0002 pode deixar; o fake o aceita porque nenhuma constraint o impede.
    """
    fakes = _mundo(funcoes_do_registro=frozenset({_F_U2}))
    antes = len(fakes.store.calls)

    with pytest.raises(SameUnitCopyError):
        _copiar(fakes, FakeIdGenerator(), _U1)

    assert "job_functions.find_all_by_ids" not in fakes.store.calls[antes:]


def test_ca5_funcao_apagada_entre_a_atribuicao_e_a_copia_e_not_found() -> None:
    """A referência pendurada é 404 da função, como em atribuir — e nada é gravado."""
    fakes = _mundo(funcoes_do_registro=frozenset({_F_AMBAS}))
    del fakes.store.job_functions[_F_AMBAS]  # o que só uma corrida produz
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionNotFoundError):
        _copiar(fakes, FakeIdGenerator(), _U2)

    assert "employees.add" not in fakes.store.calls[antes:]


def test_ca5_varias_funcoes_apagadas_a_copia_nomeia_a_menor_id() -> None:
    """R8/R10 — como em atribuir, o 404 nomeia a menor id ausente, não uma qualquer."""
    fakes = _mundo(funcoes_do_registro=frozenset({_F_AMBAS, _F_TODAS}))
    del fakes.store.job_functions[_F_AMBAS]
    del fakes.store.job_functions[_F_TODAS]

    with pytest.raises(JobFunctionNotFoundError, match=f"'{_F_TODAS}'"):
        _copiar(fakes, FakeIdGenerator(), _U2)

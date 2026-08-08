"""Testes dos DTOs de fronteira da camada de aplicação do BC staff (concept §11).

Os DTOs são `frozen` por duas razões que estes testes travam separadamente:
**imutabilidade** (ninguém edita o command a meio caminho) e **igualdade por
valor** — é esta última que torna o `EmployeeResult` o alvo correto das
asserções "nenhum outro campo mudou" das Tasks 10 a 13. As entidades da 3.1 não
serviriam: elas comparam só por id.
"""

import dataclasses
import typing
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    AssignJobFunctionsCommand,
    ChangeWorkloadProfileCommand,
    CopyEmployeeToUnitCommand,
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    DeactivateEmployeeCommand,
    DeclareShiftPreferenceCommand,
    DeleteEmployeeCommand,
    DeleteJobFunctionCommand,
    ReactivateEmployeeCommand,
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
    RenameEmployeeCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import (
    ListEmployeesQuery,
    ListJobFunctionsQuery,
)
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    JobFunctionResult,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
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
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)

pytestmark = pytest.mark.unit

_TENANT = TenantId("t1")
_UNIDADE = UnitId("u1")
_FUNCAO = JobFunctionId("f1")
_FUNCIONARIO = EmployeeId("e1")
_FIXA = FixedSchedule(weekly_hours=Decimal("44"))
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)

_RESULTADO_BASE = EmployeeResult(
    id=_FUNCIONARIO,
    tenant_id=_TENANT,
    unit_id=_UNIDADE,
    name="Maria",
    workload_profile=_FIXA,
    shift_preference=_PREFERENCIA,
    job_function_ids=frozenset({_FUNCAO}),
    unavailabilities=(_PERIODO,),
    active=True,
)

# Uma instância de CADA um dos 18 DTOs — construir todos é critério de aceite,
# e é a lista que os testes de imutabilidade percorrem.
_TODOS_OS_DTOS: tuple[object, ...] = (
    CreateJobFunctionCommand(tenant_id=_TENANT, name="Cozinheiro"),
    RenameJobFunctionCommand(tenant_id=_TENANT, job_function_id=_FUNCAO, name="Chapeiro"),
    DeleteJobFunctionCommand(tenant_id=_TENANT, job_function_id=_FUNCAO),
    CreateEmployeeCommand(
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=_FIXA,
        job_function_ids=frozenset({_FUNCAO}),
    ),
    RenameEmployeeCommand(tenant_id=_TENANT, employee_id=_FUNCIONARIO, name="Joana"),
    AssignJobFunctionsCommand(
        tenant_id=_TENANT, employee_id=_FUNCIONARIO, job_function_ids=frozenset({_FUNCAO})
    ),
    ChangeWorkloadProfileCommand(
        tenant_id=_TENANT, employee_id=_FUNCIONARIO, workload_profile=OnDemand()
    ),
    DeclareShiftPreferenceCommand(
        tenant_id=_TENANT, employee_id=_FUNCIONARIO, shift_preference=_PREFERENCIA
    ),
    RegisterUnavailabilityCommand(tenant_id=_TENANT, employee_id=_FUNCIONARIO, period=_PERIODO),
    RemoveUnavailabilityCommand(tenant_id=_TENANT, employee_id=_FUNCIONARIO, period=_PERIODO),
    DeactivateEmployeeCommand(tenant_id=_TENANT, employee_id=_FUNCIONARIO),
    ReactivateEmployeeCommand(tenant_id=_TENANT, employee_id=_FUNCIONARIO),
    DeleteEmployeeCommand(tenant_id=_TENANT, employee_id=_FUNCIONARIO),
    CopyEmployeeToUnitCommand(
        tenant_id=_TENANT, employee_id=_FUNCIONARIO, target_unit_id=UnitId("u2")
    ),
    ListJobFunctionsQuery(tenant_id=_TENANT),
    ListEmployeesQuery(tenant_id=_TENANT, unit_id=_UNIDADE),
    JobFunctionResult(id=_FUNCAO, tenant_id=_TENANT, name="Cozinheiro"),
    _RESULTADO_BASE,
)


_DTOS_ESPERADOS = 14 + 2 + 2  # commands + queries + results (concept §4)


def test_a_stage_declara_catorze_commands_duas_queries_e_dois_results() -> None:
    """Guarda a contagem do concept §4: DTO novo ou removido força revisão."""
    assert len(_TODOS_OS_DTOS) == _DTOS_ESPERADOS
    # Nenhum DTO repetido na lista: 18 entradas de 18 tipos distintos.
    assert len({type(dto) for dto in _TODOS_OS_DTOS}) == _DTOS_ESPERADOS


@pytest.mark.parametrize("dto", _TODOS_OS_DTOS, ids=lambda dto: type(dto).__name__)
def test_todo_dto_e_frozen(dto: object) -> None:
    """Command editado a meio caminho seria um contrato que muda sob o use case."""
    primeiro_campo = dataclasses.fields(dto)[0].name  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(dto, primeiro_campo, "outro")


@pytest.mark.parametrize("dto", _TODOS_OS_DTOS, ids=lambda dto: type(dto).__name__)
def test_todo_dto_tem_igualdade_por_valor(dto: object) -> None:
    """`frozen=True` gera `__eq__` por valor — o oposto das entidades da 3.1."""
    assert dataclasses.replace(dto) == dto  # type: ignore[type-var]


def test_criar_funcionario_sem_preferencia_usa_o_default_none() -> None:
    """`None` = sem preferência declarada (ADR 3.1.0004) — o default do cadastro novo."""
    comando = CreateEmployeeCommand(
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=_FIXA,
        job_function_ids=frozenset({_FUNCAO}),
    )
    assert comando.shift_preference is None


def test_declarar_preferencia_nao_tem_default() -> None:
    """Aqui `None` significa "LIMPE", não "não mexa" — por isso é obrigatório.

    Um default silencioso faria `DeclareShiftPreferenceCommand(tenant, id)`
    limpar a preferência sem que ninguém tivesse pedido — exatamente a
    ambiguidade que o ADR 3.2.0004 evitou ao recusar o update parcial.
    """
    campos = {campo.name: campo for campo in dataclasses.fields(DeclareShiftPreferenceCommand)}
    assert campos["shift_preference"].default is dataclasses.MISSING


def test_listagem_de_funcionarios_esconde_inativos_por_default() -> None:
    """Incluir desligado é opt-in explícito (L-E6)."""
    assert ListEmployeesQuery(tenant_id=_TENANT, unit_id=_UNIDADE).include_inactive is False
    incluindo = ListEmployeesQuery(tenant_id=_TENANT, unit_id=_UNIDADE, include_inactive=True)
    assert incluindo.include_inactive is True


def test_results_iguais_campo_a_campo_sao_iguais() -> None:
    """A base da asserção "nenhum outro campo mudou" das Tasks 10 a 13."""
    gemeo = EmployeeResult(
        id=_FUNCIONARIO,
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.NIGHT})),
        job_function_ids=frozenset({JobFunctionId("f1")}),
        unavailabilities=(_PERIODO,),
        active=True,
    )
    # Instâncias distintas, VOs reconstruídos: a igualdade é por valor mesmo.
    assert gemeo is not _RESULTADO_BASE
    assert gemeo == _RESULTADO_BASE


@pytest.mark.parametrize(
    ("campo", "outro_valor"),
    [
        ("id", EmployeeId("e2")),
        ("tenant_id", TenantId("t2")),
        ("unit_id", UnitId("u2")),
        ("name", "Joana"),
        ("workload_profile", OnDemand()),
        ("shift_preference", None),
        ("job_function_ids", frozenset({JobFunctionId("f2")})),
        ("unavailabilities", ()),
        ("active", False),
    ],
)
def test_divergir_em_um_unico_campo_torna_os_results_diferentes(
    campo: str, outro_valor: object
) -> None:
    """Um caso por campo, de propósito.

    Testar só um campo daria falso verde para os outros oito: é exatamente
    assim que uma comparação de result deixaria passar a mudança de um campo
    que o use case não deveria ter tocado.
    """
    divergente = dataclasses.replace(_RESULTADO_BASE, **{campo: outro_valor})
    assert divergente != _RESULTADO_BASE


def test_result_de_funcionario_tem_o_estado_de_ciclo_de_vida() -> None:
    """Sem `active` no result, a listagem não teria como distinguir o desligado."""
    nomes = {campo.name for campo in dataclasses.fields(EmployeeResult)}
    assert "active" in nomes


def test_nenhum_result_carrega_vinculo_de_login() -> None:
    """Guarda para a 3.5 (concept §11/Cópia).

    Hoje a asserção é vacuamente verdadeira — o campo não existe no modelo da
    3.1. Ela está aqui para **falhar** quando a 3.5 acrescentar `user_id` ao
    registro sem revisitar a decisão de que a cópia não o carrega
    (workforce §3.7).
    """
    proibidos = ("user_id", "login", "credential", "account_id", "password")
    for result in (EmployeeResult, JobFunctionResult):
        for campo in dataclasses.fields(result):
            assert not any(proibido in campo.name for proibido in proibidos), (
                f"{result.__name__}.{campo.name} parece vínculo de login"
            )


def _tipos_folha(anotacao: object) -> set[object]:
    """Achata uma anotação em folhas (`frozenset[JobFunctionId]` → {frozenset, JobFunctionId}).

    A checagem precisa ser **estrutural**, não textual: `EmployeeId` contém a
    substring "Employee", então um `"Employee" not in str(anotacao)` reprovaria
    o id tipado e daria a impressão de estar guardando algo.
    """
    argumentos = typing.get_args(anotacao)
    if not argumentos:
        return {anotacao}
    folhas: set[object] = set()
    for argumento in argumentos:
        folhas |= _tipos_folha(argumento)
    return folhas


@pytest.mark.parametrize("result", [EmployeeResult, JobFunctionResult])
def test_nenhum_campo_de_result_e_anotado_com_entidade(result: type) -> None:
    """Use case devolve DTO, nunca entidade (CLAUDE.md nota 6; LAYOUT §7).

    VO de domínio pode trafegar (`WorkloadProfile`, `ShiftPreference`,
    `UnavailabilityPeriod`); entidade, não — ela tem identidade e ciclo de vida,
    e vazá-la daria ao adapter da 3.4 acesso às transições do agregado.
    """
    anotacoes = typing.get_type_hints(result)
    for nome, anotacao in anotacoes.items():
        folhas = _tipos_folha(anotacao)
        assert Employee not in folhas, f"{result.__name__}.{nome} expõe a entidade Employee"
        assert JobFunction not in folhas, f"{result.__name__}.{nome} expõe a entidade JobFunction"

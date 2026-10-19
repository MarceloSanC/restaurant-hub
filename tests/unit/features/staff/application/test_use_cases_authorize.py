"""A camada application de staff nega sozinha — propriedade sobre a pasta `use_cases/`.

Stage 3.7 (issue #49, ADR 3.7.0001). Até aqui o isolamento de tenant e de unidade
era disciplina do router: `ListEmployeesUseCase.execute(...)` devolvia o que o
chamador pedisse. Este módulo trava a propriedade que substitui a disciplina, **por
use case e não por representante** (memória do projeto: "teste trava o caso, não a
propriedade"):

- **CA03** — com um guard que **sempre nega**, todo use case levanta a própria
  sentinela do guard (`is`: a exceção sobe crua, L-AG2) e **não produz efeito
  nenhum**: nenhuma chamada nova ao store dos repositórios (que registra leituras
  **e** escritas), nenhuma ao gateway de identity, nenhum id gerado. A medição
  começa **depois** da semeadura, porque semear também passa pelo store.
- **CA05** — com o guard permissivo, a sequência de `authorize` é **exatamente** a
  da matriz do concept (R3): permissão, tenant do command **nomeado**, unidade do
  command quando há.
- **CA07** — o guard permissivo devolve um escopo **inventado** (tenant e unidade
  que ninguém semeou). O efeito tem de cair no endereço do **command**: um use
  case que lesse o escopo escreveria num endereço inexistente, e a releitura pelo
  port o denunciaria (concept R4).

**Uma tabela, montagem por reflexão.** `CENARIOS` diz, por módulo da pasta, qual
classe montar, que command passar, que alvos esperar e como verificar o
endereço. O use case é construído pelo seu construtor — cada parâmetro é
preenchido pelo nome com o fake correspondente —, o mesmo mecanismo do ambiente de
borda: um parâmetro novo aparece aqui como falha de montagem, não some.

A cobrança de que `CENARIOS` cobre a pasta inteira (CA04) nasce quando a tabela
está completa (technical da 3.7, Task 07).
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    AssignJobFunctionsCommand,
    ChangeWorkloadProfileCommand,
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    DeclareShiftPreferenceCommand,
    DeleteEmployeeCommand,
    DeleteJobFunctionCommand,
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
    RenameEmployeeCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import (
    ListEmployeesQuery,
    ListJobFunctionsQuery,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import AccessGuard
from restaurant_hub.features.staff.application.use_cases.assign_job_functions import (
    AssignJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.change_workload_profile import (
    ChangeWorkloadProfileUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_employee import (
    CreateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.declare_shift_preference import (
    DeclareShiftPreferenceUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_job_functions import (
    ListJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.register_unavailability import (
    RegisterUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.remove_unavailability import (
    RemoveUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
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
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import (
    TEST_ACTOR,
    AuthorizeCall,
    DenyingAccessGuard,
    PermissiveAccessGuard,
    StubAuthorizationDenied,
)
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_A: Final = TenantId("tenant-a")
_U1: Final = UnitId("u1")
_F_EM_USO: Final = JobFunctionId("f-em-uso")
_F_LIVRE: Final = JobFunctionId("f-livre")
_E_ATIVO: Final = EmployeeId("e-ativo")
_PERIODO_GRAVADO: Final = UnavailabilityPeriod(
    start=datetime(2026, 11, 2, 8, 0), end=datetime(2026, 11, 2, 12, 0)
)
_PERIODO_NOVO: Final = UnavailabilityPeriod(
    start=datetime(2026, 11, 9, 8, 0), end=datetime(2026, 11, 9, 12, 0)
)

_MANAGE_STAFF: Final = "manage_staff"
_MANAGE_JOB_FUNCTIONS: Final = "manage_job_functions"
_MANAGE_USERS: Final = "manage_users"


@dataclass
class Montagem:
    """O que um cenário entrega: o use case montado e o que ele pode tocar."""

    use_case: Any
    fakes: StaffFakes
    gateway: InMemoryIdentityGateway
    ids: FakeIdGenerator


def _semear() -> StaffFakes:
    """O mesmo mundo para todo cenário: um tenant, uma unidade, duas funções, um registro.

    `f-em-uso` é referenciada pelo funcionário; `f-livre` não é — é a que
    `delete_job_function` consegue apagar no caminho feliz.
    """
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F_EM_USO, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_F_LIVRE, tenant_id=_A, name="Garçom"))
    fakes.employees.add(
        Employee(
            id=_E_ATIVO,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F_EM_USO}),
            unavailabilities=(_PERIODO_GRAVADO,),
        )
    )
    return fakes


def _montar(classe: type, guard: AccessGuard) -> Montagem:
    """Constrói o use case pelo construtor, preenchendo cada parâmetro pelo nome."""
    fakes = _semear()
    gateway = InMemoryIdentityGateway()
    ids = FakeIdGenerator()
    disponiveis: dict[str, object] = {
        "employees": fakes.employees,
        "job_functions": fakes.job_functions,
        "id_generator": ids,
        "gateway": gateway,
        "guard": guard,
    }
    parametros = [nome for nome in inspect.signature(classe.__init__).parameters if nome != "self"]
    faltando = [nome for nome in parametros if nome not in disponiveis]
    assert faltando == [], f"{classe.__name__} pede o que a montagem não conhece: {faltando}"
    return Montagem(
        use_case=classe(**{nome: disponiveis[nome] for nome in parametros}),
        fakes=fakes,
        gateway=gateway,
        ids=ids,
    )


@dataclass(frozen=True)
class Cenario:
    """Um use case sob a propriedade.

    Attributes:
        classe: a classe do use case.
        command: o command (ou query) **válido** do caminho feliz.
        alvos: a sequência exata de `authorize` da matriz R3 do concept.
        no_endereco_do_command: asserção de que o efeito do caminho feliz caiu no
            tenant (e unidade) do command, e não no escopo devolvido pelo guard.
    """

    classe: type
    command: object
    alvos: tuple[AuthorizeCall, ...]
    no_endereco_do_command: Callable[[Montagem, object], None]


# --- verificações de endereço (CA07) -----------------------------------------


def _funcao_criada_no_tenant(montagem: Montagem, resultado: object) -> None:
    assert resultado.tenant_id == _A
    assert montagem.fakes.job_functions.find_by_id(_A, JobFunctionId(resultado.id)) is not None


def _catalogo_do_tenant(montagem: Montagem, resultado: object) -> None:
    assert {r.id for r in resultado} == {_F_EM_USO, _F_LIVRE}
    assert {r.tenant_id for r in resultado} == {_A}


def _funcao_renomeada_no_tenant(montagem: Montagem, resultado: object) -> None:
    assert resultado.tenant_id == _A
    relida = montagem.fakes.job_functions.find_by_id(_A, _F_EM_USO)
    assert relida is not None
    assert relida.name == "Chef"


def _funcao_apagada_no_tenant(montagem: Montagem, resultado: object) -> None:
    assert resultado is None
    assert montagem.fakes.job_functions.find_by_id(_A, _F_LIVRE) is None


def _registro_no_endereco(montagem: Montagem, employee_id: EmployeeId) -> Employee | None:
    return montagem.fakes.employees.find_by_id(_A, _U1, employee_id)


def _funcionario_criado_no_endereco(montagem: Montagem, resultado: object) -> None:
    assert resultado.tenant_id == _A
    assert resultado.unit_id == _U1
    assert _registro_no_endereco(montagem, EmployeeId(resultado.id)) is not None


def _equipe_da_unidade(montagem: Montagem, resultado: object) -> None:
    assert [(r.tenant_id, r.unit_id, r.id) for r in resultado] == [(_A, _U1, _E_ATIVO)]


def _funcionario_renomeado_no_endereco(montagem: Montagem, resultado: object) -> None:
    assert (resultado.tenant_id, resultado.unit_id) == (_A, _U1)
    relido = _registro_no_endereco(montagem, _E_ATIVO)
    assert relido is not None
    assert relido.name == "Maria Clara"


def _funcionario_apagado_no_endereco(montagem: Montagem, resultado: object) -> None:
    assert resultado is None
    assert _registro_no_endereco(montagem, _E_ATIVO) is None


def _relido(montagem: Montagem) -> Employee:
    """O registro relido **no endereço do command** — se o efeito foi para lá."""
    relido = _registro_no_endereco(montagem, _E_ATIVO)
    assert relido is not None
    return relido


def _devolve_o_registro_do_endereco(resultado: object) -> None:
    assert (resultado.tenant_id, resultado.unit_id, resultado.id) == (_A, _U1, _E_ATIVO)


def _funcoes_atribuidas(montagem: Montagem, resultado: object) -> None:
    _devolve_o_registro_do_endereco(resultado)
    assert _relido(montagem).job_function_ids == frozenset({_F_EM_USO, _F_LIVRE})


def _jornada_trocada(montagem: Montagem, resultado: object) -> None:
    _devolve_o_registro_do_endereco(resultado)
    assert _relido(montagem).workload_profile == OnDemand()


def _preferencia_declarada(montagem: Montagem, resultado: object) -> None:
    _devolve_o_registro_do_endereco(resultado)
    assert _relido(montagem).shift_preference == ShiftPreference(
        periods=frozenset({DayPeriod.MORNING})
    )


def _indisponibilidade_registrada(montagem: Montagem, resultado: object) -> None:
    _devolve_o_registro_do_endereco(resultado)
    assert _PERIODO_NOVO in _relido(montagem).unavailabilities


def _indisponibilidade_removida(montagem: Montagem, resultado: object) -> None:
    _devolve_o_registro_do_endereco(resultado)
    assert _PERIODO_GRAVADO not in _relido(montagem).unavailabilities


CENARIOS: Final[dict[str, Cenario]] = {
    "create_job_function": Cenario(
        classe=CreateJobFunctionUseCase,
        command=CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name="Caixa"),
        alvos=((_MANAGE_JOB_FUNCTIONS, _A, None),),
        no_endereco_do_command=_funcao_criada_no_tenant,
    ),
    "list_job_functions": Cenario(
        classe=ListJobFunctionsUseCase,
        command=ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_A),
        alvos=((_MANAGE_JOB_FUNCTIONS, _A, None),),
        no_endereco_do_command=_catalogo_do_tenant,
    ),
    "rename_job_function": Cenario(
        classe=RenameJobFunctionUseCase,
        command=RenameJobFunctionCommand(
            actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F_EM_USO, name="Chef"
        ),
        alvos=((_MANAGE_JOB_FUNCTIONS, _A, None),),
        no_endereco_do_command=_funcao_renomeada_no_tenant,
    ),
    "delete_job_function": Cenario(
        classe=DeleteJobFunctionUseCase,
        command=DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F_LIVRE),
        alvos=((_MANAGE_JOB_FUNCTIONS, _A, None),),
        no_endereco_do_command=_funcao_apagada_no_tenant,
    ),
    "create_employee": Cenario(
        classe=CreateEmployeeUseCase,
        command=CreateEmployeeCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            name="João",
            workload_profile=OnDemand(),
            job_function_ids=frozenset({_F_EM_USO}),
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_funcionario_criado_no_endereco,
    ),
    "list_employees": Cenario(
        classe=ListEmployeesUseCase,
        command=ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_equipe_da_unidade,
    ),
    "rename_employee": Cenario(
        classe=RenameEmployeeUseCase,
        command=RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E_ATIVO, name="Maria Clara"
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_funcionario_renomeado_no_endereco,
    ),
    "delete_employee": Cenario(
        classe=DeleteEmployeeUseCase,
        command=DeleteEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E_ATIVO
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_funcionario_apagado_no_endereco,
    ),
    "assign_job_functions": Cenario(
        classe=AssignJobFunctionsUseCase,
        command=AssignJobFunctionsCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E_ATIVO,
            job_function_ids=frozenset({_F_EM_USO, _F_LIVRE}),
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_funcoes_atribuidas,
    ),
    "change_workload_profile": Cenario(
        classe=ChangeWorkloadProfileUseCase,
        command=ChangeWorkloadProfileCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E_ATIVO,
            workload_profile=OnDemand(),
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_jornada_trocada,
    ),
    "declare_shift_preference": Cenario(
        classe=DeclareShiftPreferenceUseCase,
        command=DeclareShiftPreferenceCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E_ATIVO,
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.MORNING})),
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_preferencia_declarada,
    ),
    "register_unavailability": Cenario(
        classe=RegisterUnavailabilityUseCase,
        command=RegisterUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E_ATIVO, period=_PERIODO_NOVO
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_indisponibilidade_registrada,
    ),
    "remove_unavailability": Cenario(
        classe=RemoveUnavailabilityUseCase,
        command=RemoveUnavailabilityCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E_ATIVO,
            period=_PERIODO_GRAVADO,
        ),
        alvos=((_MANAGE_STAFF, _A, _U1),),
        no_endereco_do_command=_indisponibilidade_removida,
    ),
}

_NOMES: Final = sorted(CENARIOS)


@pytest.mark.parametrize("nome", _NOMES)
def test_ca03_guard_que_nega_faz_o_use_case_levantar_sem_efeito_nenhum(nome: str) -> None:
    """O "SempreNega" da #49: levanta a sentinela do guard e não toca porta nenhuma."""
    cenario = CENARIOS[nome]
    guard = DenyingAccessGuard()
    montagem = _montar(cenario.classe, guard)
    chamadas_ao_store = len(montagem.fakes.store.calls)
    chamadas_ao_gateway = len(montagem.gateway.calls)
    ids_gerados = len(montagem.ids.generated)

    with pytest.raises(StubAuthorizationDenied) as excinfo:
        montagem.use_case.execute(cenario.command)

    assert excinfo.value is guard.denial
    assert len(guard.actors) == 1
    assert guard.actors[0] is cenario.command.actor
    assert montagem.fakes.store.calls[chamadas_ao_store:] == []
    assert montagem.gateway.calls[chamadas_ao_gateway:] == []
    assert montagem.ids.generated[ids_gerados:] == []
    # A negação aconteceu na **primeira** autorização: nada antes dela.
    assert guard.calls == [cenario.alvos[0]]


@pytest.mark.parametrize("nome", _NOMES)
def test_ca05_o_use_case_autoriza_exatamente_os_alvos_da_matriz(nome: str) -> None:
    """Permissão, tenant nomeado e unidade do command — nem mais, nem menos, nesta ordem."""
    cenario = CENARIOS[nome]
    guard = PermissiveAccessGuard()
    montagem = _montar(cenario.classe, guard)

    montagem.use_case.execute(cenario.command)

    assert guard.calls == list(cenario.alvos)
    # O ator autorizado é **o do command**, por identidade — o primeiro elemento
    # de R3, que a tupla de alvos não carrega.
    assert len(guard.actors) == len(cenario.alvos)
    assert all(ator is cenario.command.actor for ator in guard.actors)


@pytest.mark.parametrize("nome", _NOMES)
def test_ca07_o_efeito_cai_no_endereco_do_command_e_nao_no_do_escopo(nome: str) -> None:
    """O escopo devolvido é inventado; quem o lesse escreveria onde nada existe."""
    cenario = CENARIOS[nome]
    montagem = _montar(cenario.classe, PermissiveAccessGuard())

    resultado = montagem.use_case.execute(cenario.command)

    cenario.no_endereco_do_command(montagem, resultado)


def test_os_alvos_da_tabela_nomeiam_sempre_o_tenant() -> None:
    """A application nomeia o tenant em toda chamada (R3); omitir é o pedido da borda."""
    omitem = [nome for nome, c in CENARIOS.items() if any(alvo[1] is None for alvo in c.alvos)]
    assert omitem == []


def test_toda_permissao_da_tabela_e_do_vocabulario_de_staff() -> None:
    """Uma permissão digitada errado na tabela faria CA05 travar o erro, não o acerto."""
    usadas = {alvo[0] for c in CENARIOS.values() for alvo in c.alvos}
    assert usadas <= {_MANAGE_STAFF, _MANAGE_JOB_FUNCTIONS, _MANAGE_USERS}

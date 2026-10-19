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
from decimal import Decimal
from typing import Any, Final

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    CreateJobFunctionCommand,
    DeleteJobFunctionCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import ListJobFunctionsQuery
from restaurant_hub.features.staff.application.ports.out.access_guard import AccessGuard
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_job_functions import (
    ListJobFunctionsUseCase,
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
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
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
            unavailabilities=(),
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

"""Edição de funcionário **desligado** (ADR 3.2.0007; concept §5.7-bis, §11).

**Por que este arquivo existe.** A auditoria de testes independente de
2026-08-09 aplicou 26 mutações à camada e **nove** sobreviveram, todas aqui:
cada um dos seis use cases de edição podia trocar o `active` preservado por um
`active=True` fixo sem que nada falhasse, e dois deles podiam embutir um
`.reactivate()` — **ressuscitando o desligado em silêncio** — com a suíte
verde. Pior: a leitura **oposta** (recusar a edição de um desligado com um
`raise`) também passava verde, o que prova que o comportamento nunca esteve
especificado, apenas acontecia.

A causa era estrutural e não de descuido pontual: **todas** as fixtures de
edição criavam o registro com `active=True`, então nenhum teste jamais
exercitou uma edição sobre registro desligado. É a armadilha registrada na
memória do projeto — *"teste trava o caso, não a propriedade"* — com 100% de
cobertura de linha **e** de desvio por cima.

A regra que este arquivo trava (ADR 3.2.0007):

1. o desligado **é editável** por todas as seis operações, e a edição tem
   efeito — verificado **relendo pelo port**;
2. **nenhuma** delas escreve `active`: quem reativa é `reactivate_employee`, e
   mais ninguém.

Um teste **por operação**, não um representante: é a asserção (2) que mata o
`.reactivate()` embutido, e ela precisa existir em cada caminho porque é em
**um** deles que alguém o embutiria.
"""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    AssignJobFunctionsCommand,
    ChangeWorkloadProfileCommand,
    DeclareShiftPreferenceCommand,
    ReactivateEmployeeCommand,
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
    RenameEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import ListEmployeesQuery
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.use_cases.assign_job_functions import (
    AssignJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.change_workload_profile import (
    ChangeWorkloadProfileUseCase,
)
from restaurant_hub.features.staff.application.use_cases.declare_shift_preference import (
    DeclareShiftPreferenceUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.application.use_cases.reactivate_employee import (
    ReactivateEmployeeUseCase,
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
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_U1 = UnitId("u1")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)
_OUTRO_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 4, 8, 0),
    end=datetime(2026, 8, 4, 12, 0),
)
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))


def _desligado() -> StaffFakes:
    """Registro criado **já desligado**, com cadastro cheio.

    `active=False` na fixture é o ponto inteiro do arquivo: era a sua ausência
    que deixava as nove mutações vivas.
    """
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F1}),
            unavailabilities=(_PERIODO,),
            active=False,
        )
    )
    return fakes


def _relido(fakes: StaffFakes) -> Employee:
    employee = fakes.employees.find_by_id(_A, _U1, _E1)
    assert employee is not None
    return employee


# Cada entrada: (nome, executar, verificar o efeito no registro relido).
_EDICOES: list[tuple[str, Callable[[StaffFakes], EmployeeResult], Callable[[Employee], None]]] = [
    (
        "rename_employee",
        lambda fakes: RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
            RenameEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name="Joana"
            )
        ),
        lambda relido: _assert(relido.name == "Joana", f"nome não mudou: {relido.name!r}"),
    ),
    (
        "change_workload_profile",
        lambda fakes: ChangeWorkloadProfileUseCase(fakes.employees).execute(
            ChangeWorkloadProfileCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                workload_profile=OnDemand(),
            )
        ),
        lambda relido: _assert(
            relido.workload_profile == OnDemand(), "perfil de jornada não mudou"
        ),
    ),
    (
        "declare_shift_preference",
        lambda fakes: DeclareShiftPreferenceUseCase(fakes.employees).execute(
            DeclareShiftPreferenceCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                shift_preference=_PREFERENCIA,
            )
        ),
        lambda relido: _assert(
            relido.shift_preference == _PREFERENCIA, "preferência não foi gravada"
        ),
    ),
    (
        "assign_job_functions",
        lambda fakes: AssignJobFunctionsUseCase(fakes.employees, fakes.job_functions).execute(
            AssignJobFunctionsCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                job_function_ids=frozenset({_F2}),
            )
        ),
        lambda relido: _assert(
            relido.job_function_ids == frozenset({_F2}), "conjunto de funções não mudou"
        ),
    ),
    (
        "register_unavailability",
        lambda fakes: RegisterUnavailabilityUseCase(fakes.employees).execute(
            RegisterUnavailabilityCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_OUTRO_PERIODO
            )
        ),
        lambda relido: _assert(
            relido.unavailabilities == (_PERIODO, _OUTRO_PERIODO), "período não foi acrescentado"
        ),
    ),
    (
        "remove_unavailability",
        lambda fakes: RemoveUnavailabilityUseCase(fakes.employees).execute(
            RemoveUnavailabilityCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_PERIODO
            )
        ),
        lambda relido: _assert(relido.unavailabilities == (), "período não foi removido"),
    ),
]


def _assert(condicao: bool, mensagem: str) -> None:
    assert condicao, mensagem


@pytest.mark.parametrize(
    ("executar", "verificar"),
    [(executar, verificar) for _, executar, verificar in _EDICOES],
    ids=[nome for nome, _, _ in _EDICOES],
)
def test_edicao_de_desligado_tem_efeito(
    executar: Callable[[StaffFakes], EmployeeResult],
    verificar: Callable[[Employee], None],
) -> None:
    """Metade (1): o desligado **é** editável, e a edição chega ao port."""
    fakes = _desligado()
    executar(fakes)
    verificar(_relido(fakes))


@pytest.mark.parametrize(
    "executar",
    [executar for _, executar, _ in _EDICOES],
    ids=[nome for nome, _, _ in _EDICOES],
)
def test_nenhuma_edicao_reativa_o_desligado(
    executar: Callable[[StaffFakes], EmployeeResult],
) -> None:
    """Metade (2): a asserção que mata o `.reactivate()` embutido.

    Verifica nos **dois** lugares que importam — o result devolvido ao chamador
    e o registro relido pelo port. Um use case que reativasse só no result
    enganaria a 3.4; um que reativasse só na escrita enganaria o teste que
    olhasse apenas o retorno.
    """
    fakes = _desligado()
    resultado = executar(fakes)
    assert resultado.active is False
    assert _relido(fakes).active is False


@pytest.mark.parametrize(
    "executar",
    [executar for _, executar, _ in _EDICOES],
    ids=[nome for nome, _, _ in _EDICOES],
)
def test_desligado_editado_continua_fora_da_listagem_default(
    executar: Callable[[StaffFakes], EmployeeResult],
) -> None:
    """A consequência observável de (2), pelo caminho que o gerente enxerga.

    Se uma edição reativasse o registro, ele **reapareceria** na lista da
    unidade e no seletor de escala do Step 4 sem que ninguém tivesse
    recontratado ninguém. Este teste fala essa língua, e não a do booleano.
    """
    fakes = _desligado()
    executar(fakes)
    listar = ListEmployeesUseCase(fakes.employees, guard=PermissiveAccessGuard())
    assert listar.execute(ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1)) == ()
    incluindo = listar.execute(
        ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, include_inactive=True)
    )
    assert [resultado.id for resultado in incluindo] == [_E1]


def test_reactivate_e_o_unico_caminho_de_volta() -> None:
    """O contrapositivo: depois de todas as seis edições, o registro só volta
    à lista quando `reactivate_employee` é chamado explicitamente."""
    fakes = _desligado()
    for _, executar, _ in _EDICOES:
        executar(fakes)
    assert _relido(fakes).active is False

    ReactivateEmployeeUseCase(fakes.employees).execute(
        ReactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert _relido(fakes).active is True
    listado = ListEmployeesUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1)
    )
    assert [resultado.id for resultado in listado] == [_E1]

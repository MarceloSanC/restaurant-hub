"""Use case `delete_employee` — remoção definitiva (Task 12).

O irmão duro de `deactivate_employee`: aqui a história some. Existe para o
cadastro criado por engano, não para quem saiu da equipe.

O teste que mais importa é o da **ausência de produtor** de
`EmployeeInUseError` em v1: ele fixa como critério que a classe existe pelo
contrato do Step 4, e não por engano. Note que ele não cobre um `if` morto — o
use case **não tem** ramo que levante esse erro, deliberadamente (ver a
docstring do módulo de produção).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    DeactivateEmployeeCommand,
    DeleteEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import ListEmployeesQuery
from restaurant_hub.features.staff.application.errors import (
    EmployeeHasLoginError,
    EmployeeInUseError,
    EmployeeNotFoundError,
)
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_F2 = JobFunctionId("f2")
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)


def _fakes() -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.job_functions.add(JobFunction(id=_F2, tenant_id=_A, name="Chapeiro"))
    return fakes


def _grava(
    fakes: StaffFakes,
    *,
    id_: EmployeeId = _E1,
    funcoes: frozenset[JobFunctionId] = frozenset({_F1}),
    periodos: tuple[UnavailabilityPeriod, ...] = (),
    active: bool = True,
) -> None:
    fakes.employees.add(
        Employee(
            id=id_,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=funcoes,
            unavailabilities=periodos,
            active=active,
        )
    )


def _apagar(fakes: StaffFakes) -> DeleteEmployeeUseCase:
    return DeleteEmployeeUseCase(fakes.employees)


def test_remove_o_registro_definitivamente() -> None:
    fakes = _fakes()
    _grava(fakes)
    _apagar(fakes).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert fakes.employees.find_by_id(_A, _U1, _E1) is None


def test_o_removido_some_das_duas_listagens() -> None:
    """Diferente do desligado, que só some de uma."""
    fakes = _fakes()
    _grava(fakes)
    _apagar(fakes).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    listar = ListEmployeesUseCase(fakes.employees)
    assert listar.execute(ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1)) == ()
    assert (
        listar.execute(
            ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, include_inactive=True)
        )
        == ()
    )


def test_remover_desligado_tambem_funciona() -> None:
    """Apagar é ortogonal a desligar: o desligado é removível como qualquer um."""
    fakes = _fakes()
    _grava(fakes)
    DeactivateEmployeeUseCase(fakes.employees, InMemoryIdentityGateway()).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    _apagar(fakes).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert fakes.employees.find_by_id(_A, _U1, _E1) is None


def test_remover_libera_a_funcao_que_o_registro_bloqueava() -> None:
    """O contrapositivo da guarda de L-JF3: sem referenciador, a função sai."""
    fakes = _fakes()
    _grava(fakes)
    _apagar(fakes).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert fakes.employees.exists_by_job_function(_A, _F1) is False


def test_registro_inexistente_e_not_found_sem_tentar_apagar() -> None:
    fakes = _fakes()
    antes = len(fakes.store.calls)
    with pytest.raises(EmployeeNotFoundError):
        _apagar(fakes).execute(
            DeleteEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=EmployeeId("fantasma")
            )
        )
    assert "employees.delete" not in fakes.store.calls[antes:]


def test_registro_de_outro_tenant_e_not_found_e_nao_e_removido() -> None:
    fakes = _fakes()
    _grava(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _apagar(fakes).execute(
            DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_B, unit_id=_U1, employee_id=_E1)
        )

    assert "employees.delete" not in fakes.store.calls[antes:]
    assert fakes.employees.find_by_id(_A, _U1, _E1) is not None


@pytest.mark.parametrize(
    "cenario",
    ["ativo", "desligado", "varias-funcoes", "com-indisponibilidade", "completo"],
)
def test_nenhum_cenario_construivel_de_v1_produz_employee_in_use_error(cenario: str) -> None:
    """A ausência de produtor em v1 é **critério**, não esquecimento.

    Nada no escopo atual referencia o registro de funcionário: o que existe são
    referências **saindo** dele (funções) e valores **dentro** dele
    (indisponibilidades). Este teste percorre os cenários que v1 consegue
    montar e afirma que **todos** removem.

    Quem passa a produzir o erro é o Step 4 (alocação), pela FK da 3.3. O use
    case **não tem** ramo que o levante — se tivesse, seria código morto, e a
    cobertura de branch obrigaria alguém a mascará-lo com `pragma: no cover`.
    """
    fakes = _fakes()
    configuracoes = {
        "ativo": {},
        "desligado": {"active": False},
        "varias-funcoes": {"funcoes": frozenset({_F1, _F2})},
        "com-indisponibilidade": {"periodos": (_PERIODO,)},
        "completo": {
            "active": False,
            "funcoes": frozenset({_F1, _F2}),
            "periodos": (_PERIODO,),
        },
    }
    _grava(fakes, **configuracoes[cenario])  # type: ignore[arg-type]

    _apagar(fakes).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert fakes.employees.find_by_id(_A, _U1, _E1) is None


def test_employee_in_use_error_existe_e_e_instanciavel() -> None:
    """A classe é contrato publicado para o Step 4, não classe morta por engano."""
    assert "e-1" in str(EmployeeInUseError("e-1"))


# --- CA11: o endereço do funcionário tem três partes (ADR 3.4.0007) ----------
#
# **O que estes testes matam.** Antes da Stage 3.4 o use case resolvia o
# registro por `(tenant_id, employee_id)`, e a unidade do path só era conferida
# contra o **ator** — nunca contra o **registro**. Um gerente da unidade A
# alcançava qualquer funcionário do mesmo restaurante pondo a própria unidade no
# endereço. Se algum use case voltar a resolver por `(tenant, id)`, o registro é
# encontrado apesar da unidade alheia e a escrita acontece.
#
# A asserção sobre `fakes.store.calls` é o que dá poder ao teste: `pytest.raises`
# sozinho não distingue "não encontrou porque a unidade não bate" de "não
# encontrou por outro motivo e nada mais foi tentado". A conduta esperada é
# **exatamente** uma chamada — o lookup — e nenhuma escrita depois dela.


def test_ca11_remocao_com_unidade_alheia_nao_alcanca_o_registro() -> None:
    """O `delete` nem chega a ser tentado — e o registro sobrevive intacto."""
    fakes = _fakes()
    _grava(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(StaffError) as excecao:
        _apagar(fakes).execute(
            DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=_E1)
        )
    assert type(excecao.value) is EmployeeNotFoundError

    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
    assert fakes.employees.find_by_id(_A, _U1, _E1) is not None


# ---------------------------------------------------------------------------
# Stage 3.5 — R15 recusa registro com login (ADR 3.5.0003 §1b, Q7 do concept)
# ---------------------------------------------------------------------------


def _vincula(fakes: StaffFakes, *, depois_desliga: bool) -> None:
    """Vincula pelo caminho real — e, se pedido, desliga **depois** (a ordem legítima).

    Desligado não recebe login (`TerminatedEmployeeLoginError`); um registro
    vinculado e desligado só existe por vínculo seguido de desligamento, que é
    justamente o estado em que R15 continua recusando.
    """
    registro = fakes.employees.find_by_id(_A, _U1, _E1)
    assert registro is not None
    vinculado = registro.link_login(UserId("login-1"))
    fakes.employees.update(vinculado.deactivate() if depois_desliga else vinculado)


@pytest.mark.parametrize("active", [True, False], ids=["ativo", "desligado"])
def test_remover_vinculado_e_recusado_antes_de_qualquer_delete(active: bool) -> None:
    """Vale para ativo **e** desligado: o vínculo permanece no desligamento."""
    fakes = _fakes()
    _grava(fakes)
    _vincula(fakes, depois_desliga=not active)
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeHasLoginError) as excinfo:
        _apagar(fakes).execute(
            DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )

    assert type(excinfo.value) is EmployeeHasLoginError
    assert "desligue-o" in str(excinfo.value)
    assert "employees.delete" not in fakes.store.calls[antes:]
    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == UserId("login-1")
    assert relido.active is active


def test_remover_sem_login_continua_removendo() -> None:
    """A suíte da 3.2 acima é a prova de não-regressão; este é o contraste direto."""
    fakes = _fakes()
    _grava(fakes)

    _apagar(fakes).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert fakes.employees.find_by_id(_A, _U1, _E1) is None


def test_inexistente_precede_a_guarda_de_login() -> None:
    """404 antes de 409: o endereço vem primeiro (concept §6 precedência)."""
    fakes = _fakes()

    with pytest.raises(EmployeeNotFoundError):
        _apagar(fakes).execute(
            DeleteEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=EmployeeId("nao-existe")
            )
        )

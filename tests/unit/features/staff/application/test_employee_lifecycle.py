"""Ciclo de vida do funcionário: desligar e recontratar (Task 12).

Esta suíte prova a propriedade central da decisão do sponsor (ADR 3.2.0006):
**o desligado sobrevive**. Some da lista da unidade, mas não some do sistema —
continua endereçável, mantém a história e continua bloqueando a remoção das
funções que aponta.

É por isso que a suíte cruza três use cases (`deactivate`, `list_employees`,
`delete_job_function`) em vez de olhar só o campo `active`: a propriedade não é
"o booleano virou False", é o que **deixa e não deixa** de acontecer por causa
disso.
"""

import dataclasses
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    DeactivateEmployeeCommand,
    DeleteJobFunctionCommand,
    ReactivateEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import ListEmployeesQuery
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    JobFunctionInUseError,
)
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.application.use_cases.reactivate_employee import (
    ReactivateEmployeeUseCase,
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
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)


def _fakes() -> StaffFakes:
    """Registro com história: preferência, função e indisponibilidade."""
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=ShiftPreference(periods=frozenset({DayPeriod.NIGHT})),
            job_function_ids=frozenset({_F1}),
            unavailabilities=(_PERIODO,),
        )
    )
    return fakes


def _result(fakes: StaffFakes) -> EmployeeResult:
    employee = fakes.employees.find_by_id(_A, _U1, _E1)
    assert employee is not None
    return EmployeeResult(
        id=employee.id,
        tenant_id=employee.tenant_id,
        unit_id=employee.unit_id,
        name=employee.name,
        workload_profile=employee.workload_profile,
        shift_preference=employee.shift_preference,
        job_function_ids=employee.job_function_ids,
        unavailabilities=employee.unavailabilities,
        active=employee.active,
    )


def _exceto_active(resultado: EmployeeResult) -> dict[str, object]:
    return {
        f.name: getattr(resultado, f.name)
        for f in dataclasses.fields(resultado)
        if f.name != "active"
    }


def _desligar(
    fakes: StaffFakes, gateway: InMemoryIdentityGateway | None = None
) -> DeactivateEmployeeUseCase:
    return DeactivateEmployeeUseCase(fakes.employees, gateway or InMemoryIdentityGateway())


def _recontratar(fakes: StaffFakes) -> ReactivateEmployeeUseCase:
    return ReactivateEmployeeUseCase(fakes.employees)


# --- as duas transições ------------------------------------------------------


def test_desligar_poe_inativo_sem_mexer_em_mais_nada() -> None:
    fakes = _fakes()
    antes = _result(fakes)

    resultado = _desligar(fakes).execute(
        DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert resultado.active is False
    depois = _result(fakes)
    assert depois.active is False
    # A história inteira sobrevive — campo a campo.
    assert _exceto_active(depois) == _exceto_active(antes)


def test_recontratar_poe_ativo_sem_mexer_em_mais_nada() -> None:
    fakes = _fakes()
    _desligar(fakes).execute(DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1))
    antes = _result(fakes)

    resultado = _recontratar(fakes).execute(
        ReactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert resultado.active is True
    depois = _result(fakes)
    assert depois.active is True
    assert _exceto_active(depois) == _exceto_active(antes)


def test_desligar_duas_vezes_e_idempotente_no_valor() -> None:
    """Repetir não é erro — a borda não precisa consultar o estado antes de agir."""
    fakes = _fakes()
    desligar = _desligar(fakes)
    desligar.execute(DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1))
    resultado = desligar.execute(
        DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert resultado.active is False
    assert _result(fakes).active is False


def test_recontratar_quem_ja_esta_ativo_e_idempotente_no_valor() -> None:
    fakes = _fakes()
    resultado = _recontratar(fakes).execute(
        ReactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert resultado.active is True
    assert _result(fakes).active is True


def test_ciclo_desligar_e_recontratar_preserva_a_historia() -> None:
    fakes = _fakes()
    antes = _result(fakes)
    _desligar(fakes).execute(DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1))
    _recontratar(fakes).execute(
        ReactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert _result(fakes) == antes  # volta idêntico, inclusive `active`


# --- o desligado sobrevive ---------------------------------------------------


def test_desligado_some_da_listagem_default_mas_aparece_no_opt_in() -> None:
    fakes = _fakes()
    _desligar(fakes).execute(DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1))
    listar = ListEmployeesUseCase(fakes.employees)

    assert listar.execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1)) == ()

    incluindo = listar.execute(ListEmployeesQuery(tenant_id=_A, unit_id=_U1, include_inactive=True))
    assert [resultado.id for resultado in incluindo] == [_E1]
    assert incluindo[0].active is False


def test_desligado_continua_enderecavel_por_id() -> None:
    """É o que torna a recontratação possível — e o que separa desligar de apagar."""
    fakes = _fakes()
    _desligar(fakes).execute(DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1))
    assert fakes.employees.find_by_id(_A, _U1, _E1) is not None


def test_desligado_continua_bloqueando_a_remocao_das_suas_funcoes() -> None:
    """A metade da decisão que uma implementação "só ativos" perderia.

    Se a guarda contasse apenas ativos, desligar alguém liberaria a remoção da
    função que ele aponta — e a recontratação depois restauraria um registro
    apontando para função inexistente, furando a invariante "ao menos uma
    função" da 3.1.
    """
    fakes = _fakes()
    _desligar(fakes).execute(DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1))

    with pytest.raises(JobFunctionInUseError):
        DeleteJobFunctionUseCase(fakes.job_functions, fakes.employees).execute(
            DeleteJobFunctionCommand(tenant_id=_A, job_function_id=_F1)
        )
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


# --- escopo ------------------------------------------------------------------


@pytest.mark.parametrize("tenant", [_A, _B])
def test_transicoes_em_registro_inexistente_ou_alheio_nao_gravam(tenant: TenantId) -> None:
    fakes = _fakes()
    antes = _result(fakes)
    employee_id = EmployeeId("fantasma") if tenant == _A else _E1
    antes_calls = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _desligar(fakes).execute(
            DeactivateEmployeeCommand(tenant_id=tenant, unit_id=_U1, employee_id=employee_id)
        )
    with pytest.raises(EmployeeNotFoundError):
        _recontratar(fakes).execute(
            ReactivateEmployeeCommand(tenant_id=tenant, unit_id=_U1, employee_id=employee_id)
        )

    assert "employees.update" not in fakes.store.calls[antes_calls:]
    assert _result(fakes) == antes


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


def _transicoes_com_unidade_alheia() -> list[tuple[str, Callable[[StaffFakes], object]]]:
    return [
        (
            "deactivate_employee",
            lambda fakes: _desligar(fakes).execute(
                DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U2, employee_id=_E1)
            ),
        ),
        (
            "reactivate_employee",
            lambda fakes: _recontratar(fakes).execute(
                ReactivateEmployeeCommand(tenant_id=_A, unit_id=_U2, employee_id=_E1)
            ),
        ),
    ]


@pytest.mark.parametrize(
    ("nome", "executar"),
    _transicoes_com_unidade_alheia(),
    ids=[nome for nome, _ in _transicoes_com_unidade_alheia()],
)
def test_ca11_transicao_com_unidade_alheia_nao_alcanca_o_registro(
    nome: str, executar: Callable[[StaffFakes], object]
) -> None:
    fakes = _fakes()
    antes_estado = _result(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(StaffError) as excecao:
        executar(fakes)
    assert type(excecao.value) is EmployeeNotFoundError, nome

    assert fakes.store.calls[antes:] == ["employees.find_by_id"], nome
    assert _result(fakes) == antes_estado, nome


# ---------------------------------------------------------------------------
# Stage 3.5 — R13 corta o acesso do login vinculado (ADR 3.5.0003 §1, CA11)
# ---------------------------------------------------------------------------


def _fakes_com_login() -> StaffFakes:
    fakes = _fakes()
    vinculado = fakes.employees.find_by_id(_A, _U1, _E1)
    assert vinculado is not None
    fakes.employees.update(vinculado.link_login(UserId("login-1")))
    return fakes


def test_desligar_vinculado_revoga_as_sessoes_antes_de_gravar() -> None:
    """A ordem é o contrato: `revoke_login_sessions` **antes** de `employees.update`.

    Os dois ledgers são lidos pela posição relativa: a revogação é a última
    chamada ao gateway antes de o store registrar o `update`. Gravar primeiro
    deixaria um desligado com sessão viva quando identity estivesse fora.
    """
    fakes = _fakes_com_login()
    gateway = InMemoryIdentityGateway()
    antes = len(fakes.store.calls)

    resultado = _desligar(fakes, gateway).execute(
        DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert gateway.revoked == [UserId("login-1")]
    assert gateway.calls == ["revoke_login_sessions('login-1')"]
    assert fakes.store.calls[antes:] == ["employees.find_by_id", "employees.update"]
    assert resultado.active is False
    # Desligar não é desvincular: o `user_id` permanece (ADR 3.5.0003 §2).
    assert resultado.user_id == UserId("login-1")
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == UserId("login-1")


def test_desligar_sem_login_nao_toca_o_gateway() -> None:
    fakes = _fakes()
    gateway = InMemoryIdentityGateway()

    _desligar(fakes, gateway).execute(
        DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert gateway.calls == []


def test_falha_da_revogacao_sobe_crua_e_o_registro_continua_ativo() -> None:
    """Revogar antes de gravar: se identity falha, nada foi desligado."""
    fakes = _fakes_com_login()
    falha = RuntimeError("identity fora")

    class _GatewayQueFalha(InMemoryIdentityGateway):
        def revoke_login_sessions(self, user_id: UserId) -> None:
            raise falha

    antes = len(fakes.store.calls)
    with pytest.raises(RuntimeError) as excinfo:
        _desligar(fakes, _GatewayQueFalha()).execute(
            DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )

    assert excinfo.value is falha
    assert "employees.update" not in fakes.store.calls[antes:]
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.active is True


def test_desligar_duas_vezes_um_vinculado_revoga_duas_vezes_sem_erro() -> None:
    """Idempotente no valor (3.2) **e** idempotente em identity (L-IG4)."""
    fakes = _fakes_com_login()
    gateway = InMemoryIdentityGateway()
    comando = DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)

    _desligar(fakes, gateway).execute(comando)
    _desligar(fakes, gateway).execute(comando)

    assert gateway.revoked == [UserId("login-1"), UserId("login-1")]


def test_recontratar_nao_toca_o_gateway_e_o_login_continua_vinculado() -> None:
    """R14 não altera o vínculo (ADR 3.5.0003 §2): a conta nunca deixou de existir."""
    fakes = _fakes_com_login()
    gateway = InMemoryIdentityGateway()
    _desligar(fakes, gateway).execute(
        DeactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    resultado = _recontratar(fakes).execute(
        ReactivateEmployeeCommand(tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert resultado.active is True
    assert resultado.user_id == UserId("login-1")
    assert gateway.calls == ["revoke_login_sessions('login-1')"]

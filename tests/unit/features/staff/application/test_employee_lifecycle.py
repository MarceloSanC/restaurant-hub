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
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
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
from tests.fakes.features.staff.in_memory_employee_repository import InMemoryEmployeeRepository
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

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
    return DeactivateEmployeeUseCase(
        fakes.employees, gateway or InMemoryIdentityGateway(), guard=PermissiveAccessGuard()
    )


def _recontratar(fakes: StaffFakes) -> ReactivateEmployeeUseCase:
    return ReactivateEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard())


# --- as duas transições ------------------------------------------------------


def test_desligar_poe_inativo_sem_mexer_em_mais_nada() -> None:
    fakes = _fakes()
    antes = _result(fakes)

    resultado = _desligar(fakes).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert resultado.active is False
    depois = _result(fakes)
    assert depois.active is False
    # A história inteira sobrevive — campo a campo.
    assert _exceto_active(depois) == _exceto_active(antes)


def test_recontratar_poe_ativo_sem_mexer_em_mais_nada() -> None:
    fakes = _fakes()
    _desligar(fakes).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    antes = _result(fakes)

    resultado = _recontratar(fakes).execute(
        ReactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert resultado.active is True
    depois = _result(fakes)
    assert depois.active is True
    assert _exceto_active(depois) == _exceto_active(antes)


def test_desligar_duas_vezes_e_idempotente_no_valor() -> None:
    """Repetir não é erro — a borda não precisa consultar o estado antes de agir."""
    fakes = _fakes()
    desligar = _desligar(fakes)
    desligar.execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    resultado = desligar.execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert resultado.active is False
    assert _result(fakes).active is False


def test_recontratar_quem_ja_esta_ativo_e_idempotente_no_valor() -> None:
    fakes = _fakes()
    resultado = _recontratar(fakes).execute(
        ReactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert resultado.active is True
    assert _result(fakes).active is True


def test_ciclo_desligar_e_recontratar_preserva_a_historia() -> None:
    fakes = _fakes()
    antes = _result(fakes)
    _desligar(fakes).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    _recontratar(fakes).execute(
        ReactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert _result(fakes) == antes  # volta idêntico, inclusive `active`


# --- o desligado sobrevive ---------------------------------------------------


def test_desligado_some_da_listagem_default_mas_aparece_no_opt_in() -> None:
    fakes = _fakes()
    _desligar(fakes).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    listar = ListEmployeesUseCase(fakes.employees, guard=PermissiveAccessGuard())

    assert listar.execute(ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1)) == ()

    incluindo = listar.execute(
        ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, include_inactive=True)
    )
    assert [resultado.id for resultado in incluindo] == [_E1]
    assert incluindo[0].active is False


def test_desligado_continua_enderecavel_por_id() -> None:
    """É o que torna a recontratação possível — e o que separa desligar de apagar."""
    fakes = _fakes()
    _desligar(fakes).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )
    assert fakes.employees.find_by_id(_A, _U1, _E1) is not None


def test_desligado_continua_bloqueando_a_remocao_das_suas_funcoes() -> None:
    """A metade da decisão que uma implementação "só ativos" perderia.

    Se a guarda contasse apenas ativos, desligar alguém liberaria a remoção da
    função que ele aponta — e a recontratação depois restauraria um registro
    apontando para função inexistente, furando a invariante "ao menos uma
    função" da 3.1.
    """
    fakes = _fakes()
    _desligar(fakes).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    with pytest.raises(JobFunctionInUseError):
        DeleteJobFunctionUseCase(
            fakes.job_functions, fakes.employees, guard=PermissiveAccessGuard()
        ).execute(DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1))
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
            DeactivateEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=tenant, unit_id=_U1, employee_id=employee_id
            )
        )
    with pytest.raises(EmployeeNotFoundError):
        _recontratar(fakes).execute(
            ReactivateEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=tenant, unit_id=_U1, employee_id=employee_id
            )
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
                DeactivateEmployeeCommand(
                    actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=_E1
                )
            ),
        ),
        (
            "reactivate_employee",
            lambda fakes: _recontratar(fakes).execute(
                ReactivateEmployeeCommand(
                    actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=_E1
                )
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
# R13 corta o acesso que o registro concede — e só esse
# (Stage 3.5, ADR 3.5.0003 §1 e §2; alcance da Stage 3.8, ADR 3.8.0001 §1 e §2)
# ---------------------------------------------------------------------------
#
# Os testes da 3.5 vinculavam um `UserId("login-1")` que o fake não conhecia; com
# L-IG5 ("desconhecido ⇒ False") eles deixariam de revogar. O login agora nasce
# pelo **próprio** fake (`provision_employee_login`) — é ele quem diz que o login
# é de funcionário. Uma expectativa da 3.5 se inverte: desligar duas vezes revoga
# **uma** vez (CA12 da 3.8).
#
# Todas as asserções de ordem usam um **ledger único**: as chamadas ao gateway são
# espelhadas em `store.calls` (`mirror`), porque dois ledgers separados não têm
# posição relativa.

_EMAIL = "maria@cantina.com"


def _gateway_espelhado(fakes: StaffFakes) -> InMemoryIdentityGateway:
    return InMemoryIdentityGateway(mirror=lambda call: fakes.store.record(f"gateway.{call}"))


def _vincular(fakes: StaffFakes, gateway: InMemoryIdentityGateway) -> UserId:
    """Provisiona um login de funcionário pelo fake e o vincula a `_E1`.

    É arranjo: as chamadas que ele produz saem do ledger do gateway, e os testes
    medem `store.calls` a partir de um índice tomado **depois** dele.
    """
    login = gateway.provision_employee_login(
        email=_EMAIL, tenant_id=_A, unit_id=_U1, delivery=LoginDelivery.LINK
    )
    vinculado = fakes.employees.find_by_id(_A, _U1, _E1)
    assert vinculado is not None
    fakes.employees.update(vinculado.link_login(login.user_id))
    gateway.calls.clear()
    return login.user_id


def _outro_registro(
    fakes: StaffFakes,
    id_: str,
    *,
    unit_id: UnitId = _U1,
    user_id: UserId | None = None,
    active: bool = True,
) -> None:
    registro = Employee(
        id=EmployeeId(id_),
        tenant_id=_A,
        unit_id=unit_id,
        name=f"Registro {id_}",
        workload_profile=FixedSchedule(weekly_hours=Decimal("20")),
        shift_preference=None,
        job_function_ids=frozenset({_F1}),
    )
    fakes.employees.add(registro)
    if user_id is not None:
        registro = registro.link_login(user_id)
    if not active:
        registro = registro.deactivate()
    fakes.employees.update(registro)


def _desligar_e1(use_case: DeactivateEmployeeUseCase) -> EmployeeResult:
    return use_case.execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )


def test_ca05_registro_unico_de_funcionario_revoga_antes_de_gravar_na_ordem() -> None:
    """A ordem é o contrato: unidade → papel → revogar → gravar (concept §5.2).

    Gravar primeiro deixaria um desligado com sessão viva quando identity estivesse
    fora; a consulta local primeiro decide sem cruzar a fronteira.
    """
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    login = _vincular(fakes, gateway)
    antes = len(fakes.store.calls)

    resultado = _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == [login]
    assert fakes.store.calls[antes:] == [
        "employees.find_by_id",
        "employees.list_by_unit",
        f"gateway.is_employee_login({login!r})",
        f"gateway.revoke_login_sessions({login!r})",
        "employees.update",
    ]
    assert resultado.active is False
    # Desligar não é desvincular: o `user_id` permanece (ADR 3.5.0003 §3).
    assert resultado.user_id == login
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == login


def test_ca06_outro_registro_ativo_do_login_na_unidade_nao_toca_o_gateway() -> None:
    """Caso (a) da issue #60: é o outro registro que ainda concede o acesso."""
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    login = _vincular(fakes, gateway)
    _outro_registro(fakes, "e2", user_id=login)
    antes = len(fakes.store.calls)

    resultado = _desligar_e1(_desligar(fakes, gateway))

    assert gateway.calls == []
    assert fakes.store.calls[antes:] == [
        "employees.find_by_id",
        "employees.list_by_unit",
        "employees.update",
    ]
    assert resultado.active is False


def test_ca07_o_outro_registro_do_login_na_unidade_ja_desligado_nao_impede() -> None:
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    login = _vincular(fakes, gateway)
    _outro_registro(fakes, "e2", user_id=login, active=False)

    _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == [login]


def test_ca08_outro_registro_ativo_do_login_em_outra_unidade_nao_impede() -> None:
    """Decisão do sponsor (concept §13 Q4): só a unidade conta; a pessoa loga de novo."""
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    login = _vincular(fakes, gateway)
    _outro_registro(fakes, "e2", unit_id=_U2, user_id=login)

    _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == [login]


def test_ca09_outros_ativos_da_unidade_sem_o_login_nao_impedem() -> None:
    """O filtro é por `user_id`: qualquer outro ativo bloqueando seria nunca revogar."""
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    login = _vincular(fakes, gateway)
    outro_login = gateway.provision_employee_login(
        email="joao@cantina.com", tenant_id=_A, unit_id=_U1, delivery=LoginDelivery.LINK
    ).user_id
    gateway.calls.clear()
    _outro_registro(fakes, "e2", user_id=outro_login)
    _outro_registro(fakes, "e3")

    _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == [login]


def test_ca10_login_de_outro_papel_nao_e_revogado() -> None:
    """Caso (b) da issue #60: gerente ou dono vinculado a um registro de escala."""
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    gerente = UserId("login-do-gerente")
    gateway.seed_login_of_other_role(gerente, tenant_id=_A, unit_id=_U1)
    vinculado = fakes.employees.find_by_id(_A, _U1, _E1)
    assert vinculado is not None
    fakes.employees.update(vinculado.link_login(gerente))
    antes = len(fakes.store.calls)

    resultado = _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == []
    assert fakes.store.calls[antes:] == [
        "employees.find_by_id",
        "employees.list_by_unit",
        f"gateway.is_employee_login({gerente!r})",
        "employees.update",
    ]
    assert resultado.active is False


def test_ca11_login_desconhecido_de_identity_nao_e_revogado_e_o_registro_grava() -> None:
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    vinculado = fakes.employees.find_by_id(_A, _U1, _E1)
    assert vinculado is not None
    fakes.employees.update(vinculado.link_login(UserId("login-que-identity-nao-conhece")))

    resultado = _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == []
    assert resultado.active is False


def test_ca12_desligar_de_novo_um_desligado_nao_toca_o_gateway() -> None:
    """A conta permanece: as sessões abertas depois do primeiro desligamento ficam.

    Inverte a expectativa da 3.5 (`..._revoga_duas_vezes_sem_erro`): o duplo clique
    não derruba quem logou de novo.
    """
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    login = _vincular(fakes, gateway)
    _desligar_e1(_desligar(fakes, gateway))
    antes = len(fakes.store.calls)

    resultado = _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == [login]
    assert fakes.store.calls[antes:] == ["employees.find_by_id", "employees.update"]
    assert resultado.active is False


class _GatewayQueFalhaNaRevogacao(InMemoryIdentityGateway):
    def __init__(self, falha: Exception) -> None:
        super().__init__()
        self._falha = falha

    def revoke_login_sessions(self, user_id: UserId) -> None:
        raise self._falha


@pytest.mark.parametrize("onde", ["list_by_unit", "is_employee_login", "revoke_login_sessions"])
def test_ca13_falha_antes_de_gravar_sobe_crua_e_o_registro_continua_ativo(onde: str) -> None:
    """Tudo antes da escrita: qualquer falha deixa o registro ativo (ADR 3.5.0003 §2)."""
    fakes = _fakes()
    falha = RuntimeError(f"{onde} fora")
    gateway = (
        _GatewayQueFalhaNaRevogacao(falha)
        if onde == "revoke_login_sessions"
        else InMemoryIdentityGateway()
    )
    _vincular(fakes, gateway)
    if onde == "is_employee_login":
        gateway.fail_role_query_with = falha

    class _RegistrosQueFalhamNaListagem(InMemoryEmployeeRepository):
        def list_by_unit(
            self, tenant_id: TenantId, unit_id: UnitId, *, include_inactive: bool = False
        ) -> tuple[Employee, ...]:
            raise falha

    # Sobre o **mesmo** store: o ledger e o estado são os do holder.
    employees = (
        _RegistrosQueFalhamNaListagem(fakes.store) if onde == "list_by_unit" else fakes.employees
    )
    antes = len(fakes.store.calls)

    with pytest.raises(RuntimeError) as excinfo:
        DeactivateEmployeeUseCase(employees, gateway, guard=PermissiveAccessGuard()).execute(
            DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )

    assert excinfo.value is falha
    assert "employees.update" not in fakes.store.calls[antes:]
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.active is True


def test_nova_tentativa_depois_de_falha_na_gravacao_revoga_de_novo() -> None:
    """A guarda `active` não torna a nova tentativa insegura (concept §6, última linha).

    A gravação falhou, o registro continua ativo — então a segunda tentativa roda a
    regra inteira de novo e revoga outra vez (L-IG4: inócuo).
    """
    fakes = _fakes()
    gateway = InMemoryIdentityGateway()
    login = _vincular(fakes, gateway)
    falha = RuntimeError("banco fora na gravação")

    class _RegistrosQueFalhamNaGravacao(InMemoryEmployeeRepository):
        def update(self, employee: Employee) -> None:
            raise falha

    with pytest.raises(RuntimeError):
        DeactivateEmployeeUseCase(
            _RegistrosQueFalhamNaGravacao(fakes.store), gateway, guard=PermissiveAccessGuard()
        ).execute(
            DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )
    resultado = _desligar_e1(_desligar(fakes, gateway))

    assert gateway.revoked == [login, login]
    assert resultado.active is False


def test_ca14_registro_sem_login_so_le_e_grava() -> None:
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    antes = len(fakes.store.calls)

    _desligar_e1(_desligar(fakes, gateway))

    assert gateway.calls == []
    assert fakes.store.calls[antes:] == ["employees.find_by_id", "employees.update"]


def test_ca15_vinculado_em_endereco_alheio_so_faz_o_lookup() -> None:
    """Endereço que não alcança o registro: nenhuma das chamadas novas acontece."""
    fakes = _fakes()
    gateway = _gateway_espelhado(fakes)
    _vincular(fakes, gateway)
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _desligar(fakes, gateway).execute(
            DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=_E1)
        )

    assert gateway.calls == []
    assert fakes.store.calls[antes:] == ["employees.find_by_id"]


def test_recontratar_nao_toca_o_gateway_e_o_login_continua_vinculado() -> None:
    """R14 não altera o vínculo (ADR 3.5.0003 §4): a conta nunca deixou de existir."""
    fakes = _fakes()
    gateway = InMemoryIdentityGateway()
    login = _vincular(fakes, gateway)
    _desligar_e1(_desligar(fakes, gateway))
    assert gateway.revoked == [login]  # o desligamento cortou; a recontratação não devolve nada

    resultado = _recontratar(fakes).execute(
        ReactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert resultado.active is True
    assert resultado.user_id == login
    # A conta nunca deixou de existir: o login continua sendo de funcionário, e
    # um novo desligamento volta a cortar (o registro está ativo de novo).
    _desligar_e1(_desligar(fakes, gateway))
    assert gateway.revoked == [login, login]

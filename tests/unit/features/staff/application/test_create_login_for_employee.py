"""Testes do use case `create_login_for_employee` — Stage 3.5 (CA03, CA05, CA09, CA30).

O que se protege, acima de tudo, é a **ordem** (concept §5.4): guardas do domínio
antes de identity; vínculo gravado antes de o segredo ser entregue; o link só
sai no canal `link`. Cada posição da ordem tem um teste que morreria se ela
fosse trocada — e as asserções são sobre os **ledgers** dos fakes
(`fakes.store.calls`, `gateway.calls`), não só sobre o resultado.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    CreateLoginForEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.results import EmployeeLoginResult
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    InvalidLoginEmailError,
    LoginEmailAlreadyInUseError,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases.create_login_for_employee import (
    CreateLoginForEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    TerminatedEmployeeLoginError,
)
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
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_EMAIL = "maria@cantina.com"
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 9, 14, 8, 0),
    end=datetime(2026, 9, 14, 12, 0),
)


def _fakes(*, active: bool = True, user_id: UserId | None = None) -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheira"))
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
            active=active,
            user_id=user_id,
        )
    )
    return fakes


def _gateway(fakes: StaffFakes) -> InMemoryIdentityGateway:
    """O fake do gateway com as chamadas **espelhadas** no ledger do store.

    Os dois ledgers separados não respondem "o vínculo foi gravado **antes** do
    envio?" — a ordem entre `employees.update` e `send_login_invitation` só é
    observável num ledger único. Espelhar é o que torna a asserção de CA30
    literal, em vez de inferida.
    """
    return InMemoryIdentityGateway(mirror=lambda call: fakes.store.record(f"gateway.{call}"))


def _comando(
    *,
    delivery: LoginDelivery = LoginDelivery.LINK,
    email: str = _EMAIL,
    tenant_id: TenantId = _A,
    unit_id: UnitId = _U1,
    employee_id: EmployeeId = _E1,
) -> CreateLoginForEmployeeCommand:
    return CreateLoginForEmployeeCommand(
        actor=TEST_ACTOR,
        tenant_id=tenant_id,
        unit_id=unit_id,
        employee_id=employee_id,
        email=email,
        delivery=delivery,
    )


def _relido(fakes: StaffFakes) -> Employee:
    employee = fakes.employees.find_by_id(_A, _U1, _E1)
    assert employee is not None
    return employee


def _provisionamentos(gateway: InMemoryIdentityGateway) -> list[str]:
    return [c for c in gateway.calls if c.startswith("provision_employee_login(")]


# ---------------------------------------------------------------------------
# CA03 — os dois canais
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("delivery", list(LoginDelivery), ids=lambda d: d.value)
def test_grava_o_user_id_provisionado_e_repassa_o_canal(delivery: LoginDelivery) -> None:
    fakes = _fakes()
    gateway = _gateway(fakes)

    resultado = CreateLoginForEmployeeUseCase(
        fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(_comando(delivery=delivery))

    (user_id,) = gateway.logins
    assert _relido(fakes).user_id == user_id
    assert resultado.employee.user_id == user_id
    assert gateway.logins[user_id].delivery is delivery
    assert gateway.logins[user_id].email == _EMAIL
    assert gateway.logins[user_id].tenant_id == _A
    assert gateway.logins[user_id].unit_id == _U1


def test_canal_email_envia_uma_vez_e_nao_devolve_o_link() -> None:
    fakes = _fakes()
    gateway = _gateway(fakes)

    resultado = CreateLoginForEmployeeUseCase(
        fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(_comando(delivery=LoginDelivery.EMAIL))

    (user_id,) = gateway.logins
    assert gateway.sent == [(_EMAIL, gateway.logins[user_id].setup_link)]
    assert resultado.setup_link is None


def test_canal_link_devolve_o_link_e_nao_envia_nada() -> None:
    fakes = _fakes()
    gateway = _gateway(fakes)

    resultado = CreateLoginForEmployeeUseCase(
        fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(_comando(delivery=LoginDelivery.LINK))

    (user_id,) = gateway.logins
    assert resultado.setup_link == gateway.logins[user_id].setup_link
    assert gateway.sent == []


def test_o_result_traz_o_estado_resultante_pelo_mapper() -> None:
    """CA06/CA13 — o mesmo `EmployeeResult` de toda resposta de funcionário, vinculado."""
    fakes = _fakes()
    gateway = _gateway(fakes)

    resultado = CreateLoginForEmployeeUseCase(
        fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(_comando())

    relido = _relido(fakes)
    assert isinstance(resultado, EmployeeLoginResult)
    assert resultado.employee.id == relido.id
    assert resultado.employee.name == relido.name
    assert resultado.employee.unavailabilities == relido.unavailabilities
    assert resultado.employee.active is True
    assert resultado.employee.user_id == relido.user_id
    assert resultado.employee.user_id is not None


def test_o_link_nao_aparece_no_repr_do_result() -> None:
    """CA05 — `repr=False`: o segredo não sai em traceback nem em log de debug."""
    fakes = _fakes()
    gateway = _gateway(fakes)

    resultado = CreateLoginForEmployeeUseCase(
        fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(_comando())

    assert resultado.setup_link is not None
    assert resultado.setup_link not in repr(resultado)
    assert "token" not in repr(resultado)


# ---------------------------------------------------------------------------
# CA09 — as guardas do domínio vêm ANTES de identity
# ---------------------------------------------------------------------------


def test_ja_vinculado_recusa_sem_tocar_em_identity() -> None:
    fakes = _fakes(user_id=UserId("login-existente"))
    gateway = _gateway(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeAlreadyHasLoginError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando())

    assert _provisionamentos(gateway) == []
    assert gateway.calls == []
    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
    assert _relido(fakes).user_id == UserId("login-existente")


def test_desligado_recusa_sem_tocar_em_identity() -> None:
    fakes = _fakes(active=False)
    gateway = _gateway(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(TerminatedEmployeeLoginError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando())

    assert gateway.calls == []
    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
    assert _relido(fakes).user_id is None


def test_vinculado_e_desligado_recusa_pelo_vinculo_primeiro() -> None:
    """Precedência de `assert_can_link_login`: vinculado > desligado (concept §5.4)."""
    fakes = _fakes(active=False, user_id=UserId("login-existente"))
    gateway = _gateway(fakes)

    with pytest.raises(EmployeeAlreadyHasLoginError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando())

    assert gateway.calls == []


@pytest.mark.parametrize(
    ("tenant_id", "unit_id", "employee_id"),
    [
        pytest.param(_B, _U1, _E1, id="outro-tenant"),
        pytest.param(_A, _U2, _E1, id="outra-unidade"),
        pytest.param(_A, _U1, EmployeeId("nao-existe"), id="id-inexistente"),
    ],
)
def test_registro_fora_do_endereco_e_404_sem_tocar_em_identity(
    tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId
) -> None:
    """CA11 — a unidade faz parte do endereço; fora dele, nada de identity acontece."""
    fakes = _fakes()
    gateway = _gateway(fakes)

    with pytest.raises(EmployeeNotFoundError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando(tenant_id=tenant_id, unit_id=unit_id, employee_id=employee_id))

    assert gateway.calls == []
    assert _relido(fakes).user_id is None


# ---------------------------------------------------------------------------
# L-IG2 traduzido pelo gateway — o use case não grava nada
# ---------------------------------------------------------------------------


def test_email_ja_usado_sobe_traduzido_e_nada_e_gravado() -> None:
    fakes = _fakes()
    gateway = _gateway(fakes)
    gateway.used_emails.add(_EMAIL)

    with pytest.raises(LoginEmailAlreadyInUseError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando())

    assert _relido(fakes).user_id is None
    assert "employees.update" not in fakes.store.calls
    assert gateway.sent == []


def test_email_invalido_sobe_traduzido_e_nada_e_gravado() -> None:
    fakes = _fakes()
    gateway = _gateway(fakes)
    gateway.invalid_emails.add("nao-e-email")

    with pytest.raises(InvalidLoginEmailError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando(email="nao-e-email"))

    assert _relido(fakes).user_id is None
    assert "employees.update" not in fakes.store.calls


# ---------------------------------------------------------------------------
# CA30 — gravar antes de entregar
# ---------------------------------------------------------------------------


def test_o_vinculo_e_gravado_antes_do_envio() -> None:
    """A ordem literal no ledger único: `employees.update` precede o envio."""
    fakes = _fakes()
    gateway = _gateway(fakes)

    CreateLoginForEmployeeUseCase(fakes.employees, gateway, guard=PermissiveAccessGuard()).execute(
        _comando(delivery=LoginDelivery.EMAIL)
    )

    calls = fakes.store.calls
    posicao_update = calls.index("employees.update")
    posicao_envio = next(
        i for i, c in enumerate(calls) if c.startswith("gateway.send_login_invitation(")
    )
    posicao_provisao = next(
        i for i, c in enumerate(calls) if c.startswith("gateway.provision_employee_login(")
    )
    assert posicao_provisao < posicao_update < posicao_envio


def test_falha_do_envio_sobe_na_mesma_instancia_e_o_vinculo_fica() -> None:
    """ADR 3.5.0002 §4 — SMTP fora não desfaz o vínculo; a recuperação é o reset público."""
    fakes = _fakes()
    gateway = _gateway(fakes)
    falha = RuntimeError("smtp indisponível")
    gateway.fail_send_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando(delivery=LoginDelivery.EMAIL))

    assert excinfo.value is falha
    (user_id,) = gateway.logins
    assert _relido(fakes).user_id == user_id


def test_segundo_pedido_apos_falha_do_envio_e_ja_vinculado() -> None:
    """O caminho de recuperação **não** é um segundo R17 — o registro já aponta."""
    fakes = _fakes()
    gateway = _gateway(fakes)
    gateway.fail_send_with = RuntimeError("smtp indisponível")
    with pytest.raises(RuntimeError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando(delivery=LoginDelivery.EMAIL))
    gateway.fail_send_with = None

    with pytest.raises(EmployeeAlreadyHasLoginError):
        CreateLoginForEmployeeUseCase(
            fakes.employees, gateway, guard=PermissiveAccessGuard()
        ).execute(_comando(delivery=LoginDelivery.EMAIL))

    assert len(gateway.logins) == 1

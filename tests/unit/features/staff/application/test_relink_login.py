"""R19 — trocar o login vinculado (Stage 3.10, concept §5 R7; ADR 3.10.0001 §1).

A regra de fim de vínculo por condição está em `test_login_link_single_point.py`
(CA4) e a elegibilidade em `test_resolve_linkable_login.py`. Aqui: a ordem de R19, a
precedência das guardas (CA6), a troca pelo mesmo login (sem escrita nem revogação),
as recusas da conta nova sem tocar o vínculo antigo (CA2) e a escrita condicional
sob concorrência.
"""

import dataclasses
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import RelinkLoginCommand
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    InvalidLoginEmailError,
    LoginAccountNotFoundError,
    LoginAlreadyLinkedInUnitError,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases.relink_login import RelinkLoginUseCase
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeHasNoLoginError,
    EmployeeLoginChangedError,
    TerminatedEmployeeLoginError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_employee_repository import InMemoryEmployeeRepository
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_NOVA = UserId("conta-certa")
_EMAIL_NOVO = "certa@cantina.com"

_REGISTRO = Employee(
    id=_E1,
    tenant_id=_A,
    unit_id=_U1,
    name="Carla",
    workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
    shift_preference=None,
    job_function_ids=frozenset({JobFunctionId("f1")}),
)


def _arranjo(
    *, active: bool = True, **conta: object
) -> tuple[StaffFakes, InMemoryIdentityGateway, UserId]:
    fakes = staff_repositories()
    gateway = InMemoryIdentityGateway(mirror=lambda call: fakes.store.record(f"gateway.{call}"))
    antigo = gateway.provision_employee_login(
        email="errada@cantina.com", tenant_id=_A, unit_id=_U1, delivery=LoginDelivery.LINK
    ).user_id
    gateway.seed_account(
        _NOVA,
        email=_EMAIL_NOVO,
        employee=True,
        **{"tenant_id": _A, "unit_ids": frozenset({_U1}), **conta},  # type: ignore[arg-type]
    )
    gateway.calls.clear()
    fakes.store.employees[_E1] = dataclasses.replace(_REGISTRO, user_id=antigo, active=active)
    return fakes, gateway, antigo


def _trocar(
    fakes: StaffFakes,
    gateway: InMemoryIdentityGateway,
    *,
    email: str = _EMAIL_NOVO,
    unit_id: UnitId = _U1,
    employees: InMemoryEmployeeRepository | None = None,
) -> object:
    return RelinkLoginUseCase(
        employees or fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(
        RelinkLoginCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=unit_id, employee_id=_E1, email=email
        )
    )


def _relido(fakes: StaffFakes) -> Employee:
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    return relido


def test_troca_o_login_validando_a_conta_nova_antes_de_encerrar_o_antigo() -> None:
    fakes, gateway, antigo = _arranjo()
    antes = len(fakes.store.calls)

    resultado = _trocar(fakes, gateway)
    chamadas = fakes.store.calls[antes:]

    assert chamadas == [
        "employees.find_by_id",
        f"gateway.find_login_by_email({_EMAIL_NOVO!r})",
        "employees.list_by_unit",  # R10, ativos e desligados
        "employees.list_by_unit",  # regra de fim de vínculo, só ativos
        f"gateway.is_employee_login({antigo!r})",
        f"gateway.revoke_login_sessions({antigo!r})",
        "employees.relink_login",
    ]
    assert resultado.user_id == _NOVA  # type: ignore[attr-defined]
    relido = _relido(fakes)
    assert relido.user_id == _NOVA
    assert dataclasses.astuple(dataclasses.replace(relido, user_id=None)) == dataclasses.astuple(
        _REGISTRO
    )


def test_trocar_pelo_login_atual_nao_escreve_nem_revoga() -> None:
    fakes, gateway, antigo = _arranjo()
    email_atual = gateway.logins[antigo].email
    antes = len(fakes.store.calls)

    resultado = _trocar(fakes, gateway, email=email_atual)

    assert fakes.store.calls[antes:] == [
        "employees.find_by_id",
        f"gateway.find_login_by_email({email_atual!r})",
    ]
    assert gateway.revoked == []
    assert resultado.user_id == antigo  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("registro", "erro"),
    [
        pytest.param(
            {"user_id": None, "active": False}, EmployeeHasNoLoginError, id="sem-login-vence"
        ),
        pytest.param({"user_id": None}, EmployeeHasNoLoginError, id="sem-login"),
        pytest.param({"active": False}, TerminatedEmployeeLoginError, id="desligado"),
    ],
)
def test_ca6_guardas_locais_vem_antes_de_identity(
    registro: dict[str, object], erro: type[Exception]
) -> None:
    fakes, gateway, _ = _arranjo()
    fakes.store.employees[_E1] = dataclasses.replace(
        fakes.store.employees[_E1],
        **registro,  # type: ignore[arg-type]
    )
    antes = len(fakes.store.calls)

    with pytest.raises(erro):
        _trocar(fakes, gateway)

    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
    assert gateway.calls == []


def test_registro_fora_do_endereco_e_404() -> None:
    fakes, gateway, _ = _arranjo()

    with pytest.raises(EmployeeNotFoundError):
        _trocar(fakes, gateway, unit_id=_U2)

    assert gateway.calls == []


@pytest.mark.parametrize(
    "conta",
    [
        pytest.param({"tenant_id": TenantId("tenant-b")}, id="outro-tenant"),
        pytest.param({"tenant_id": None, "unit_ids": frozenset()}, id="platform-admin"),
        pytest.param({"unit_ids": frozenset({_U2})}, id="sem-membership-na-unidade"),
    ],
)
def test_ca2_conta_nova_fora_do_alcance_e_404_e_o_vinculo_antigo_fica(
    conta: dict[str, object],
) -> None:
    fakes, gateway, antigo = _arranjo(**conta)

    with pytest.raises(LoginAccountNotFoundError):
        _trocar(fakes, gateway)

    assert _relido(fakes).user_id == antigo
    assert gateway.revoked == []
    assert "employees.relink_login" not in fakes.store.calls


def test_ca2_email_sem_conta_e_404_sem_revogar() -> None:
    fakes, gateway, antigo = _arranjo()

    with pytest.raises(LoginAccountNotFoundError):
        _trocar(fakes, gateway, email="ninguem@cantina.com")

    assert gateway.revoked == []
    assert _relido(fakes).user_id == antigo


def test_email_malformado_e_422_sem_revogar() -> None:
    fakes, gateway, antigo = _arranjo()
    gateway.invalid_emails.add("nao-e-email")

    with pytest.raises(InvalidLoginEmailError):
        _trocar(fakes, gateway, email="nao-e-email")

    assert gateway.revoked == []
    assert _relido(fakes).user_id == antigo


def test_ca12_conta_nova_ja_em_outro_registro_da_unidade_e_409() -> None:
    fakes, gateway, antigo = _arranjo()
    fakes.store.employees[EmployeeId("e2")] = dataclasses.replace(
        _REGISTRO, id=EmployeeId("e2"), user_id=_NOVA
    )

    with pytest.raises(LoginAlreadyLinkedInUnitError):
        _trocar(fakes, gateway)

    assert gateway.revoked == []
    assert _relido(fakes).user_id == antigo


class _TrocaConcorrente(InMemoryEmployeeRepository):
    """Outro R19 que trocou o login entre a leitura e a escrita deste."""

    def relink_login(
        self,
        tenant_id: TenantId,
        unit_id: UnitId,
        employee_id: EmployeeId,
        *,
        expected_user_id: UserId,
        user_id: UserId,
    ) -> None:
        super().relink_login(
            tenant_id,
            unit_id,
            employee_id,
            expected_user_id=expected_user_id,
            user_id=UserId("do-primeiro"),
        )
        super().relink_login(
            tenant_id,
            unit_id,
            employee_id,
            expected_user_id=expected_user_id,
            user_id=user_id,
        )


def test_troca_concorrente_e_recusada_e_o_gravado_e_o_do_primeiro() -> None:
    fakes, gateway, _ = _arranjo()

    with pytest.raises(EmployeeLoginChangedError):
        _trocar(fakes, gateway, employees=_TrocaConcorrente(fakes.store))

    assert _relido(fakes).user_id == UserId("do-primeiro")

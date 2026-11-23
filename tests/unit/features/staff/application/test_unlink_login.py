"""R20 — desvincular o login de um registro (Stage 3.10, concept §5 R7, R8).

A regra de fim de vínculo é cobrada condição a condição para os três chamadores em
`test_login_link_single_point.py` (CA4); aqui ficam a ordem de R20, as recusas, o
caso do registro desligado (R8), o caminho para a remoção (R15) e a escrita
condicional sob concorrência.
"""

import dataclasses
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    DeleteEmployeeCommand,
    UnlinkLoginCommand,
)
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.unlink_login import UnlinkLoginUseCase
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeHasNoLoginError,
    EmployeeLoginChangedError,
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

_REGISTRO = Employee(
    id=_E1,
    tenant_id=_A,
    unit_id=_U1,
    name="Carla",
    workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
    shift_preference=None,
    job_function_ids=frozenset({JobFunctionId("f1")}),
)


def _arranjo(*, active: bool = True) -> tuple[StaffFakes, InMemoryIdentityGateway, UserId]:
    fakes = staff_repositories()
    gateway = InMemoryIdentityGateway(mirror=lambda call: fakes.store.record(f"gateway.{call}"))
    login = gateway.provision_employee_login(
        email="carla@cantina.com", tenant_id=_A, unit_id=_U1, delivery=LoginDelivery.LINK
    ).user_id
    gateway.calls.clear()
    fakes.store.employees[_E1] = dataclasses.replace(_REGISTRO, user_id=login, active=active)
    return fakes, gateway, login


def _desvincular(
    fakes: StaffFakes,
    gateway: InMemoryIdentityGateway,
    *,
    unit_id: UnitId = _U1,
    employees: InMemoryEmployeeRepository | None = None,
) -> object:
    return UnlinkLoginUseCase(
        employees or fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(UnlinkLoginCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=unit_id, employee_id=_E1))


def _relido(fakes: StaffFakes) -> Employee:
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    return relido


def test_ca5_desvincula_registro_ativo_revogando_antes_de_gravar() -> None:
    fakes, gateway, login = _arranjo()
    antes = len(fakes.store.calls)

    resultado = _desvincular(fakes, gateway)
    chamadas = fakes.store.calls[antes:]

    assert chamadas == [
        "employees.find_by_id",
        "employees.list_by_unit",
        f"gateway.is_employee_login({login!r})",
        f"gateway.revoke_login_sessions({login!r})",
        "employees.unlink_login",
    ]
    assert resultado.user_id is None  # type: ignore[attr-defined]
    assert resultado.active is True  # type: ignore[attr-defined]
    relido = _relido(fakes)
    assert relido.user_id is None
    assert dataclasses.astuple(relido) == dataclasses.astuple(_REGISTRO)


def test_ca5_r8_desvincula_registro_desligado_sem_tocar_identity() -> None:
    fakes, gateway, _ = _arranjo(active=False)

    resultado = _desvincular(fakes, gateway)

    assert gateway.calls == []
    assert resultado.user_id is None  # type: ignore[attr-defined]
    assert (_relido(fakes).user_id, _relido(fakes).active) == (None, False)


def test_ca5_depois_de_desvincular_a_remocao_e_aceita() -> None:
    """O caminho para remover um registro que recebeu login por engano (ADR 0.0.0013)."""
    fakes, gateway, _ = _arranjo(active=False)

    _desvincular(fakes, gateway)
    DeleteEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        DeleteEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert fakes.employees.find_by_id(_A, _U1, _E1) is None


def test_ca6_registro_sem_login_e_409_antes_de_identity() -> None:
    fakes, gateway, _ = _arranjo()
    fakes.store.employees[_E1] = _REGISTRO
    antes = len(fakes.store.calls)

    with pytest.raises(EmployeeHasNoLoginError):
        _desvincular(fakes, gateway)

    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
    assert gateway.calls == []


def test_registro_fora_do_endereco_e_404() -> None:
    fakes, gateway, login = _arranjo()

    with pytest.raises(EmployeeNotFoundError):
        _desvincular(fakes, gateway, unit_id=_U2)

    assert gateway.calls == []
    assert _relido(fakes).user_id == login


@pytest.mark.parametrize("onde", ["consulta_de_papel", "revogacao"])
def test_falha_de_identity_na_regra_sobe_crua_e_nada_e_gravado(onde: str) -> None:
    fakes, gateway, login = _arranjo()
    falha = RuntimeError("identity fora")
    if onde == "revogacao":
        gateway.fail_revoke_with = falha
    else:
        gateway.fail_role_query_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        _desvincular(fakes, gateway)

    assert excinfo.value is falha
    assert _relido(fakes).user_id == login
    assert "employees.unlink_login" not in fakes.store.calls


class _TrocaConcorrente(InMemoryEmployeeRepository):
    """Um R19 concorrente que troca o login entre a leitura e a escrita deste R20."""

    def unlink_login(
        self,
        tenant_id: TenantId,
        unit_id: UnitId,
        employee_id: EmployeeId,
        *,
        expected_user_id: UserId,
        expected_active: bool,
    ) -> None:
        super().relink_login(
            tenant_id,
            unit_id,
            employee_id,
            expected_user_id=expected_user_id,
            user_id=UserId("do-concorrente"),
        )
        super().unlink_login(
            tenant_id,
            unit_id,
            employee_id,
            expected_user_id=expected_user_id,
            expected_active=expected_active,
        )


def test_login_trocado_entre_a_leitura_e_a_escrita_recusa_e_mantem_o_novo() -> None:
    fakes, gateway, _ = _arranjo()

    with pytest.raises(EmployeeLoginChangedError):
        _desvincular(fakes, gateway, employees=_TrocaConcorrente(fakes.store))

    assert _relido(fakes).user_id == UserId("do-concorrente")


def test_o_port_recebe_o_estado_lido() -> None:
    vistos: list[tuple[UserId, bool]] = []

    class _Espiao(InMemoryEmployeeRepository):
        def unlink_login(
            self,
            tenant_id: TenantId,
            unit_id: UnitId,
            employee_id: EmployeeId,
            *,
            expected_user_id: UserId,
            expected_active: bool,
        ) -> None:
            vistos.append((expected_user_id, expected_active))
            super().unlink_login(
                tenant_id,
                unit_id,
                employee_id,
                expected_user_id=expected_user_id,
                expected_active=expected_active,
            )

    for ativo in (True, False):
        fakes, gateway, login = _arranjo(active=ativo)
        _desvincular(fakes, gateway, employees=_Espiao(fakes.store))
        assert vistos[-1] == (login, ativo)

"""R18 — vincular a um registro uma conta que já existe (Stage 3.10, concept §5 R7).

A autorização tem a sua varredura (`test_use_cases_authorize.py`); a elegibilidade
e "um login por unidade" têm a sua (`test_resolve_linkable_login.py`). Aqui fica o
que é do use case: a ordem das checagens, as guardas locais **antes** de identity
(CA6), o caminho feliz para cada tipo de conta elegível (CA1) e a escrita pelo
`link_login` condicional.
"""

import dataclasses
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import LinkExistingLoginCommand
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    InvalidLoginEmailError,
    LoginAccountNotFoundError,
    LoginAlreadyLinkedInUnitError,
)
from restaurant_hub.features.staff.application.use_cases.link_existing_login import (
    LinkExistingLoginUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
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
_EMAIL = "gerente@cantina.com"
_CONTA = UserId("conta-do-gerente")

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
    registro: Employee = _REGISTRO, **conta: object
) -> tuple[StaffFakes, InMemoryIdentityGateway]:
    fakes = staff_repositories()
    fakes.store.employees[registro.id] = registro
    gateway = InMemoryIdentityGateway(mirror=lambda call: fakes.store.record(f"gateway.{call}"))
    gateway.seed_account(
        _CONTA,
        email=_EMAIL,
        **{"tenant_id": _A, "unit_ids": frozenset({_U1}), **conta},  # type: ignore[arg-type]
    )
    return fakes, gateway


def _vincular(
    fakes: StaffFakes,
    gateway: InMemoryIdentityGateway,
    *,
    email: str = _EMAIL,
    unit_id: UnitId = _U1,
    employees: InMemoryEmployeeRepository | None = None,
) -> object:
    return LinkExistingLoginUseCase(
        employees or fakes.employees, gateway, guard=PermissiveAccessGuard()
    ).execute(
        LinkExistingLoginCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=unit_id, employee_id=_E1, email=email
        )
    )


@pytest.mark.parametrize(
    "conta",
    [
        pytest.param({"employee": True}, id="funcionario-membro"),
        pytest.param({}, id="gerente-membro"),
        pytest.param({"unit_ids": frozenset(), "every_unit": True}, id="dono-sem-membership"),
    ],
)
def test_ca1_vincula_a_conta_elegivel_e_so_o_login_muda(conta: dict[str, object]) -> None:
    fakes, gateway = _arranjo(**conta)
    antes = len(fakes.store.calls)

    resultado = _vincular(fakes, gateway)
    chamadas = fakes.store.calls[antes:]

    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _CONTA
    assert dataclasses.astuple(dataclasses.replace(relido, user_id=None)) == dataclasses.astuple(
        _REGISTRO
    )
    assert resultado.user_id == _CONTA  # type: ignore[attr-defined]
    assert resultado.id == _E1  # type: ignore[attr-defined]
    assert chamadas == [
        "employees.find_by_id",
        f"gateway.find_login_by_email({_EMAIL!r})",
        "employees.list_by_unit",
        "employees.link_login",
    ]
    assert gateway.revoked == []


def test_vincular_nao_toca_as_sessoes_nem_pergunta_o_papel() -> None:
    fakes, gateway = _arranjo(employee=True)

    _vincular(fakes, gateway)

    assert not any("revoke" in c or "is_employee_login" in c for c in gateway.calls)


def test_registro_fora_do_endereco_e_404_antes_de_identity() -> None:
    fakes, gateway = _arranjo()

    with pytest.raises(EmployeeNotFoundError):
        _vincular(fakes, gateway, unit_id=_U2)

    assert gateway.calls == []


@pytest.mark.parametrize(
    ("registro", "erro"),
    [
        pytest.param(
            dataclasses.replace(_REGISTRO, user_id=UserId("outro"), active=False),
            EmployeeAlreadyHasLoginError,
            id="vinculado-e-desligado-vinculado-vence",
        ),
        pytest.param(
            dataclasses.replace(_REGISTRO, user_id=UserId("outro")),
            EmployeeAlreadyHasLoginError,
            id="vinculado",
        ),
        pytest.param(
            dataclasses.replace(_REGISTRO, active=False),
            TerminatedEmployeeLoginError,
            id="desligado",
        ),
    ],
)
def test_ca6_guardas_locais_vem_antes_de_consultar_identity(
    registro: Employee, erro: type[Exception]
) -> None:
    fakes, gateway = _arranjo(registro)
    antes = len(fakes.store.calls)

    with pytest.raises(erro):
        _vincular(fakes, gateway)

    assert gateway.calls == []
    assert fakes.store.calls[antes:] == ["employees.find_by_id"]


def test_ca6_registro_vinculado_com_email_malformado_responde_a_guarda() -> None:
    """A guarda local vence o 422: o e-mail só é validado por identity, depois."""
    fakes, gateway = _arranjo(dataclasses.replace(_REGISTRO, user_id=UserId("outro")))
    gateway.invalid_emails.add("nao-e-email")

    with pytest.raises(EmployeeAlreadyHasLoginError):
        _vincular(fakes, gateway, email="nao-e-email")


def test_email_malformado_sobe_traduzido_e_nada_e_gravado() -> None:
    fakes, gateway = _arranjo()
    gateway.invalid_emails.add("nao-e-email")

    with pytest.raises(InvalidLoginEmailError):
        _vincular(fakes, gateway, email="nao-e-email")

    assert "employees.link_login" not in fakes.store.calls


@pytest.mark.parametrize(
    "conta",
    [
        pytest.param({"tenant_id": TenantId("tenant-b")}, id="outro-tenant"),
        pytest.param({"tenant_id": None, "unit_ids": frozenset()}, id="platform-admin"),
        pytest.param({"unit_ids": frozenset({_U2})}, id="sem-membership-na-unidade"),
    ],
)
def test_ca2_conta_fora_do_alcance_e_404_sem_gravar(conta: dict[str, object]) -> None:
    fakes, gateway = _arranjo(**conta)

    with pytest.raises(LoginAccountNotFoundError):
        _vincular(fakes, gateway)

    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id is None
    assert "employees.link_login" not in fakes.store.calls


def test_ca2_email_sem_conta_e_404() -> None:
    fakes, gateway = _arranjo()

    with pytest.raises(LoginAccountNotFoundError):
        _vincular(fakes, gateway, email="ninguem@cantina.com")


def test_ca12_conta_ja_em_outro_registro_da_unidade_e_409_sem_gravar() -> None:
    fakes, gateway = _arranjo()
    fakes.store.employees[EmployeeId("e2")] = dataclasses.replace(
        _REGISTRO, id=EmployeeId("e2"), user_id=_CONTA, active=False
    )

    with pytest.raises(LoginAlreadyLinkedInUnitError):
        _vincular(fakes, gateway)

    assert "employees.link_login" not in fakes.store.calls


def test_ca12_conta_em_registro_de_outra_unidade_e_vinculada() -> None:
    fakes, gateway = _arranjo(unit_ids=frozenset({_U1, _U2}))
    fakes.store.employees[EmployeeId("e2")] = dataclasses.replace(
        _REGISTRO, id=EmployeeId("e2"), unit_id=_U2, user_id=_CONTA
    )

    _vincular(fakes, gateway)

    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == _CONTA


class _VinculoConcorrente(InMemoryEmployeeRepository):
    """Um R17/R18 concorrente que vincula outra conta logo antes da escrita deste."""

    def link_login(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId, user_id: UserId
    ) -> None:
        super().link_login(tenant_id, unit_id, employee_id, UserId("do-concorrente"))
        super().link_login(tenant_id, unit_id, employee_id, user_id)


def test_vinculo_concorrente_gravado_depois_da_leitura_e_recusado_pela_escrita() -> None:
    fakes, gateway = _arranjo()

    with pytest.raises(EmployeeAlreadyHasLoginError):
        _vincular(fakes, gateway, employees=_VinculoConcorrente(fakes.store))

    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.user_id == UserId("do-concorrente")

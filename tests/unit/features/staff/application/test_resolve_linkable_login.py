"""`resolve_linkable_login` — elegibilidade da conta existente e um login por unidade.

Stage 3.10 (ADR 3.10.0002 §3; ADR 3.10.0001 §6). O critério que mais importa é a
**recusa uniforme**: os quatro casos de conta fora do alcance do registro levantam a
mesma classe com a mesma mensagem (CA2), e o teste compara as mensagens entre si —
um erro com a causa embutida passaria em `pytest.raises` e vazaria o oráculo.
"""

import dataclasses
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.errors import (
    InvalidLoginEmailError,
    LoginAccountNotFoundError,
    LoginAlreadyLinkedInUnitError,
)
from restaurant_hub.features.staff.application.use_cases._login_link import (
    resolve_linkable_login,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_EMAIL = "ana@cantina.com"
_CONTA = UserId("conta-ana")

_REGISTRO = Employee(
    id=EmployeeId("e1"),
    tenant_id=_A,
    unit_id=_U1,
    name="Ana",
    workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
    shift_preference=None,
    job_function_ids=frozenset({JobFunctionId("f1")}),
)


def _arranjo(**conta: object) -> tuple[StaffFakes, InMemoryIdentityGateway]:
    fakes = staff_repositories()
    fakes.store.employees[_REGISTRO.id] = _REGISTRO
    gateway = InMemoryIdentityGateway()
    if conta:
        gateway.seed_account(_CONTA, email=_EMAIL, **conta)  # type: ignore[arg-type]
    return fakes, gateway


def _resolver(
    fakes: StaffFakes,
    gateway: InMemoryIdentityGateway,
    registro: Employee = _REGISTRO,
    email: str = _EMAIL,
) -> UserId:
    return resolve_linkable_login(fakes.employees, gateway, email, registro)


@pytest.mark.parametrize(
    "conta",
    [
        pytest.param({"tenant_id": _A, "unit_ids": frozenset({_U1})}, id="membro-da-unidade"),
        pytest.param(
            {"tenant_id": _A, "unit_ids": frozenset({_U1, _U2})}, id="membro-de-varias-unidades"
        ),
        pytest.param({"tenant_id": _A, "every_unit": True}, id="dono-sem-membership"),
    ],
)
def test_conta_do_tenant_que_alcanca_a_unidade_e_elegivel(conta: dict[str, object]) -> None:
    fakes, gateway = _arranjo(**conta)

    assert _resolver(fakes, gateway) == _CONTA


_FORA_DO_ALCANCE = [
    pytest.param({}, id="email-sem-conta"),
    pytest.param(
        {"tenant_id": TenantId("tenant-b"), "unit_ids": frozenset({_U1})}, id="outro-tenant"
    ),
    pytest.param(
        {"tenant_id": TenantId("tenant-b"), "every_unit": True}, id="dono-de-outro-tenant"
    ),
    pytest.param({"tenant_id": None}, id="platform-admin"),
    pytest.param({"tenant_id": _A, "unit_ids": frozenset({_U2})}, id="sem-membership-na-unidade"),
    pytest.param({"tenant_id": _A}, id="sem-membership-nenhuma"),
]


@pytest.mark.parametrize("conta", _FORA_DO_ALCANCE)
def test_conta_fora_do_alcance_e_recusada_sem_ler_a_unidade(conta: dict[str, object]) -> None:
    fakes, gateway = _arranjo(**conta)
    antes = len(fakes.store.calls)

    with pytest.raises(LoginAccountNotFoundError):
        _resolver(fakes, gateway)

    assert fakes.store.calls[antes:] == []


def test_as_recusas_sao_indistinguiveis_entre_si() -> None:
    """CA2: mesma classe, mesma mensagem — nenhuma resposta revela por que recusou."""
    mensagens = set()
    for parametro in _FORA_DO_ALCANCE:
        fakes, gateway = _arranjo(**parametro.values[0])  # type: ignore[arg-type]
        with pytest.raises(LoginAccountNotFoundError) as excinfo:
            _resolver(fakes, gateway)
        assert type(excinfo.value) is LoginAccountNotFoundError
        mensagens.add(str(excinfo.value))

    assert len(mensagens) == 1


def test_a_recusa_cita_o_email_enviado() -> None:
    """A mensagem nomeia o que o gerente digitou, e só isso (docstring do erro).

    Sem este teste, trocar o e-mail por `None` na recusa sobrevivia: as mensagens
    continuavam iguais entre si (o mutante do `mutation-access-modules` na auditoria
    do PR #230).
    """
    fakes, gateway = _arranjo()
    with pytest.raises(LoginAccountNotFoundError) as excinfo:
        _resolver(fakes, gateway)

    assert str(excinfo.value) == (
        f"nenhuma conta deste restaurante com o e-mail nesta unidade: {_EMAIL!r}"
    )


def test_a_conta_atual_do_registro_volta_sem_checagens() -> None:
    """R19 com o login atual: ele já é do registro, mesmo fora do alcance hoje."""
    fakes, gateway = _arranjo(tenant_id=_A, unit_ids=frozenset({_U2}))
    registro = dataclasses.replace(_REGISTRO, user_id=_CONTA)
    fakes.store.employees[registro.id] = registro
    antes = len(fakes.store.calls)

    assert _resolver(fakes, gateway, registro) == _CONTA
    assert fakes.store.calls[antes:] == []


@pytest.mark.parametrize("ativo", [True, False], ids=["ativo", "desligado"])
def test_conta_ja_vinculada_a_outro_registro_da_unidade_e_recusada(ativo: bool) -> None:
    fakes, gateway = _arranjo(tenant_id=_A, unit_ids=frozenset({_U1}))
    outro = dataclasses.replace(_REGISTRO, id=EmployeeId("e2"), user_id=_CONTA, active=ativo)
    fakes.store.employees[outro.id] = outro

    with pytest.raises(LoginAlreadyLinkedInUnitError, match="e1"):
        _resolver(fakes, gateway)


def test_conta_vinculada_a_registro_de_outra_unidade_e_elegivel() -> None:
    fakes, gateway = _arranjo(tenant_id=_A, unit_ids=frozenset({_U1, _U2}))
    outro = dataclasses.replace(_REGISTRO, id=EmployeeId("e2"), unit_id=_U2, user_id=_CONTA)
    fakes.store.employees[outro.id] = outro

    assert _resolver(fakes, gateway) == _CONTA


def test_outro_registro_da_unidade_com_outra_conta_nao_impede() -> None:
    fakes, gateway = _arranjo(tenant_id=_A, unit_ids=frozenset({_U1}))
    outro = dataclasses.replace(_REGISTRO, id=EmployeeId("e2"), user_id=UserId("outra"))
    fakes.store.employees[outro.id] = outro

    assert _resolver(fakes, gateway) == _CONTA


def test_email_malformado_sobe_traduzido_pelo_gateway() -> None:
    fakes, gateway = _arranjo()
    gateway.invalid_emails.add("nao-e-email")

    with pytest.raises(InvalidLoginEmailError):
        _resolver(fakes, gateway, email="nao-e-email")


def test_falha_da_consulta_sobe_crua() -> None:
    fakes, gateway = _arranjo(tenant_id=_A, unit_ids=frozenset({_U1}))
    falha = RuntimeError("identity fora")
    gateway.fail_account_query_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        _resolver(fakes, gateway)

    assert excinfo.value is falha


def test_o_proprio_registro_ja_gravado_com_a_conta_nao_conta_como_outro() -> None:
    """Vínculo concorrente da mesma conta ao próprio registro: quem responde é L-LINK.

    O registro foi lido sem login e está gravado com a conta. R10 olha só os
    **outros** registros da unidade; se contasse o próprio, a resposta seria
    "outro registro" em vez do `EmployeeAlreadyHasLoginError` da escrita.
    """
    fakes, gateway = _arranjo(tenant_id=_A, unit_ids=frozenset({_U1}))
    fakes.store.employees[_REGISTRO.id] = dataclasses.replace(_REGISTRO, user_id=_CONTA)

    assert _resolver(fakes, gateway, _REGISTRO) == _CONTA

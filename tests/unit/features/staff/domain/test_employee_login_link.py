"""Transições do vínculo de login conforme o estado lido (Stage 3.10, ADR 3.10.0001 §2).

As escritas condicionais do repositório aplicam estas transições ao registro
**gravado**, com o que o use case leu; aqui elas são provadas sobre a entidade. Cada
teste nomeia um ramo e a precedência entre ramos, para que inverter uma condição ou
trocar a ordem derrube um teste.
"""

import dataclasses
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeHasNoLoginError,
    EmployeeLoginChangedError,
    InvalidIdentifierError,
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

pytestmark = pytest.mark.unit

_A = UserId("login-a")
_B = UserId("login-b")

_BASE = Employee(
    id=EmployeeId("e1"),
    tenant_id=TenantId("t1"),
    unit_id=UnitId("u1"),
    name="Maria",
    workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
    shift_preference=None,
    job_function_ids=frozenset({JobFunctionId("f1")}),
)


def _registro(*, user_id: UserId | None = _A, active: bool = True) -> Employee:
    return dataclasses.replace(_BASE, user_id=user_id, active=active)


# --- assert_link_state -------------------------------------------------------


@pytest.mark.parametrize("ativo", [True, False])
def test_estado_igual_ao_lido_passa(ativo: bool) -> None:
    _registro(active=ativo).assert_link_state(_A, was_active=ativo)


def test_sem_vinculo_lido_e_gravado_passa() -> None:
    _registro(user_id=None).assert_link_state(None, was_active=True)


@pytest.mark.parametrize(
    ("gravado", "lido"), [(_B, _A), (None, _A), (_A, None)], ids=["trocado", "desfeito", "criado"]
)
def test_login_gravado_diferente_do_lido_recusa(
    gravado: UserId | None, lido: UserId | None
) -> None:
    with pytest.raises(EmployeeLoginChangedError, match="e1"):
        _registro(user_id=gravado).assert_link_state(lido, was_active=True)


def test_lido_desligado_e_gravado_ativo_recusa() -> None:
    """Recontratado no meio: encerrar agora encerraria um vínculo ativo sem a regra."""
    with pytest.raises(EmployeeLoginChangedError):
        _registro(active=True).assert_link_state(_A, was_active=False)


def test_lido_ativo_e_gravado_desligado_nao_recusa() -> None:
    """Quem desligou no meio já passou pela regra de fim de vínculo."""
    _registro(active=False).assert_link_state(_A, was_active=True)


# --- unlink_login ------------------------------------------------------------


@pytest.mark.parametrize("ativo", [True, False])
def test_desvincular_tira_so_o_login(ativo: bool) -> None:
    registro = _registro(active=ativo)

    desvinculado = registro.unlink_login(_A, was_active=ativo)

    assert desvinculado.user_id is None
    assert dataclasses.replace(desvinculado, user_id=_A) == registro
    assert desvinculado.active is ativo
    assert registro.user_id == _A  # imutável: nova instância


def test_desvincular_sem_login_recusa_antes_de_conferir_o_lido() -> None:
    with pytest.raises(EmployeeHasNoLoginError, match="e1"):
        _registro(user_id=None).unlink_login(_A, was_active=False)


def test_desvincular_login_trocado_recusa() -> None:
    with pytest.raises(EmployeeLoginChangedError):
        _registro(user_id=_B).unlink_login(_A, was_active=True)


def test_desvincular_registro_recontratado_no_meio_recusa() -> None:
    with pytest.raises(EmployeeLoginChangedError):
        _registro(active=True).unlink_login(_A, was_active=False)


# --- relink_login ------------------------------------------------------------


def test_trocar_grava_o_login_novo() -> None:
    trocado = _registro().relink_login(_A, _B)

    assert trocado.user_id == _B
    assert trocado.active is True


def test_trocar_pelo_mesmo_login_e_identidade() -> None:
    assert _registro().relink_login(_A, _A).user_id == _A


def test_trocar_sem_login_vence_desligado_e_lido() -> None:
    with pytest.raises(EmployeeHasNoLoginError):
        _registro(user_id=None, active=False).relink_login(_A, _B)


def test_trocar_em_desligado_vence_login_trocado() -> None:
    with pytest.raises(TerminatedEmployeeLoginError, match="e1"):
        _registro(user_id=_B, active=False).relink_login(_A, _B)


def test_trocar_login_trocado_recusa() -> None:
    with pytest.raises(EmployeeLoginChangedError):
        _registro(user_id=_B).relink_login(_A, UserId("login-c"))


@pytest.mark.parametrize("vazio", ["", "   "])
def test_trocar_para_login_vazio_e_recusado_pelo_construtor(vazio: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        _registro().relink_login(_A, UserId(vazio))


# --- deactivate_as_read ------------------------------------------------------


@pytest.mark.parametrize("login", [_A, None])
def test_desligar_como_lido_desliga_e_mantem_o_login(login: UserId | None) -> None:
    desligado = _registro(user_id=login).deactivate_as_read(login, was_active=True)

    assert desligado.active is False
    assert desligado.user_id == login


def test_desligar_de_novo_e_idempotente() -> None:
    assert _registro(active=False).deactivate_as_read(_A, was_active=False).active is False


def test_desligamento_concorrente_ja_gravado_nao_recusa() -> None:
    assert _registro(active=False).deactivate_as_read(_A, was_active=True).active is False


@pytest.mark.parametrize(
    ("gravado", "lido"),
    [(_A, None), (None, _A), (_B, _A)],
    ids=["vinculado", "desvinculado", "trocado"],
)
def test_desligar_com_login_diferente_do_lido_recusa(
    gravado: UserId | None, lido: UserId | None
) -> None:
    with pytest.raises(EmployeeLoginChangedError):
        _registro(user_id=gravado).deactivate_as_read(lido, was_active=True)


def test_desligar_registro_recontratado_no_meio_recusa() -> None:
    with pytest.raises(EmployeeLoginChangedError):
        _registro(active=True).deactivate_as_read(_A, was_active=False)


# --- as guardas com casa única (Checkpoint C, bloco T08–T10, F2) -------------


def test_as_guardas_de_desvincular_e_trocar_devolvem_o_login_atual() -> None:
    assert _registro().assert_can_unlink_login() == _A
    assert _registro(active=False).assert_can_unlink_login() == _A
    assert _registro().assert_can_relink_login() == _A


def test_guarda_de_trocar_sem_login_vence_desligado() -> None:
    with pytest.raises(EmployeeHasNoLoginError):
        _registro(user_id=None, active=False).assert_can_relink_login()
    with pytest.raises(TerminatedEmployeeLoginError):
        _registro(active=False).assert_can_relink_login()
    with pytest.raises(EmployeeHasNoLoginError):
        _registro(user_id=None).assert_can_unlink_login()

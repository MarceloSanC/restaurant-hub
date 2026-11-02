"""As leis L-SG1…L-SG4 do `AccessGuard` de scheduling, provadas contra o fake (CA21).

A 4.4/4.5 acrescentam o tradutor de produção à mesma prova.
"""

import pytest

from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
)
from tests.fakes.features.scheduling.in_memory_access_guard import (
    FakeActor,
    InMemoryAccessGuard,
)

pytestmark = pytest.mark.unit

_T, _U, _U2 = "t1", "u1", "u2"


def _guard() -> tuple[InMemoryAccessGuard, FakeActor]:
    guard = InMemoryAccessGuard()
    ator = guard.issue("user-1", _T)
    guard.grant(PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U)
    return guard, ator


def test_permissoes_sao_os_tres_valores_do_concept() -> None:
    assert (PERMISSION_VIEW_SCHEDULE, PERMISSION_MANAGE_SCHEDULE, PERMISSION_VIEW_OWN_SCHEDULE) == (
        "view_schedule",
        "manage_schedule",
        "view_own_schedule",
    )


def test_l_sg2_o_escopo_confirma_o_alvo_pedido() -> None:
    guard, ator = _guard()
    escopo = guard.authorize(ator, PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U)
    assert (escopo.tenant_id, escopo.unit_id) == (_T, _U)


def test_l_sg4_o_sujeito_e_o_do_ator() -> None:
    guard, ator = _guard()
    escopo = guard.authorize(ator, PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U)
    assert escopo.user_id == "user-1"


@pytest.mark.parametrize(
    ("permissao", "tenant", "unidade"),
    [
        (PERMISSION_MANAGE_SCHEDULE, _T, _U2),  # L-SG3 — outra unidade
        (PERMISSION_VIEW_SCHEDULE, _T, _U),  # L-SG3 — outra permissão
        (PERMISSION_MANAGE_SCHEDULE, "t2", _U),  # L-SG2 — outro tenant
    ],
)
def test_l_sg1_l_sg3_alvo_nao_concedido_levanta_a_sentinela_crua(
    permissao: str, tenant: str, unidade: str
) -> None:
    guard, ator = _guard()
    with pytest.raises(Exception) as excinfo:
        guard.authorize(ator, permissao, tenant_id=tenant, unit_id=unidade)
    assert excinfo.value is guard.authorization_error


@pytest.mark.parametrize(
    "ator_invalido",
    [None, FakeActor(user_id="user-1", tenant_id=_T)],  # nulo; forjado (não emitido)
)
def test_l_sg1_ator_nao_emitido_e_negado(ator_invalido: object) -> None:
    guard, _ = _guard()
    with pytest.raises(Exception) as excinfo:
        guard.authorize(ator_invalido, PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U)
    assert excinfo.value is guard.authorization_error


@pytest.mark.parametrize(("user_id", "tenant"), [("user-1", None), ("  ", _T), ("", _T)])
def test_l_sg2_l_sg4_ator_sem_tenant_ou_sem_sujeito_e_negado_mesmo_concedido(
    user_id: str, tenant: str | None
) -> None:
    guard, _ = _guard()
    ator = guard.issue(user_id, tenant)
    with pytest.raises(Exception) as excinfo:
        guard.authorize(ator, PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U)
    assert excinfo.value is guard.authorization_error


def test_l_sg3_cada_alvo_e_uma_chamada_registrada() -> None:
    guard, ator = _guard()
    guard.grant(PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U2)
    guard.authorize(ator, PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U)
    guard.authorize(ator, PERMISSION_MANAGE_SCHEDULE, tenant_id=_T, unit_id=_U2)
    assert guard.calls == [
        f"authorize({PERMISSION_MANAGE_SCHEDULE},{_T},{_U})",
        f"authorize({PERMISSION_MANAGE_SCHEDULE},{_T},{_U2})",
    ]

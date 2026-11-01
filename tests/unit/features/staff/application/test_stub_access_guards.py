"""Os dois dublês infiéis do `AccessGuard` fazem o que as suítes da 3.7 assumem.

Não é suíte de lei — os dublês não implementam as leis (ver o módulo deles). É a
garantia de que a infidelidade é a **escolhida**: se o guard que nega deixasse
passar um pedido, ou o permissivo devolvesse o escopo pedido, as suítes de
autorização dos use cases ficariam verdes medindo menos do que dizem.
"""

import pytest

from restaurant_hub.features.staff.application.ports.out.access_guard import AuthorizedScope
from tests.fakes.features.staff.stub_access_guards import (
    INFIDEL_TENANT,
    INFIDEL_UNIT,
    TEST_ACTOR,
    DenyingAccessGuard,
    PermissiveAccessGuard,
)

pytestmark = pytest.mark.unit

_PEDIDOS = [
    pytest.param("manage_staff", "t1", "u1", id="com-unidade"),
    pytest.param("manage_job_functions", "t1", None, id="sem-unidade"),
    pytest.param("manage_staff", None, "u1", id="tenant-omitido"),
]


@pytest.mark.parametrize(("permission", "tenant_id", "unit_id"), _PEDIDOS)
def test_o_guard_que_nega_levanta_sempre_a_mesma_instancia(
    permission: str, tenant_id: str | None, unit_id: str | None
) -> None:
    guard = DenyingAccessGuard()

    for _ in range(2):
        with pytest.raises(type(guard.denial)) as excinfo:
            guard.authorize(TEST_ACTOR, permission, tenant_id=tenant_id, unit_id=unit_id)
        assert excinfo.value is guard.denial

    assert guard.calls == [(permission, tenant_id, unit_id)] * 2
    assert all(ator is TEST_ACTOR for ator in guard.actors)
    assert len(guard.actors) == 2  # noqa: PLR2004 — as duas chamadas do laço


def test_o_guard_permissivo_concede_e_devolve_um_escopo_que_ninguem_pediu() -> None:
    guard = PermissiveAccessGuard()

    escopo = guard.authorize(TEST_ACTOR, "manage_staff", tenant_id="t1", unit_id="u1")

    assert escopo == AuthorizedScope(tenant_id=INFIDEL_TENANT, unit_id=INFIDEL_UNIT)
    assert escopo.tenant_id != "t1"
    assert escopo.unit_id != "u1"
    assert guard.calls == [("manage_staff", "t1", "u1")]
    assert guard.actors == [TEST_ACTOR]


def test_o_guard_permissivo_recusa_o_pedido_que_omite_o_tenant() -> None:
    """A application sempre nomeia o tenant; omitir é o pedido da borda, não dela."""
    guard = PermissiveAccessGuard()

    with pytest.raises(type(guard.denial)) as excinfo:
        guard.authorize(TEST_ACTOR, "manage_staff", unit_id="u1")

    assert excinfo.value is guard.denial
    assert guard.calls == [("manage_staff", None, "u1")]


def test_o_endereco_infiel_nao_colide_com_nenhum_tenant_de_teste() -> None:
    """Se colidisse, ler o escopo e ler o command voltariam a ser o mesmo valor."""
    assert INFIDEL_TENANT not in {"tenant-a", "tenant-b", "t1", "t2", TEST_ACTOR.tenant_id}
    assert INFIDEL_UNIT not in {"u1", "u2", "unit-1", "unit-2"}

"""Leis L-ST1…L-ST5 do `StaffReadPort` (concept 4.3 §4; CA21).

Parametrizada por implementação: nesta Stage só o fake; a 4.4 acrescenta o adapter
real ao `params` da fixture `mundo` (precedente 3.5). O mundo semeado é o mesmo para
toda implementação: dois tenants, duas unidades, ativos, um desligado, vínculos de
login e catálogo.
"""

import pytest

from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    StaffMember,
    StaffReadPort,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import EmployeeId
from tests.contract.features.scheduling.conftest import T1 as _T1
from tests.contract.features.scheduling.conftest import T2 as _T2
from tests.contract.features.scheduling.conftest import U1 as _U1
from tests.contract.features.scheduling.conftest import U2 as _U2
from tests.contract.features.scheduling.conftest import staff_member as _membro

pytestmark = pytest.mark.contract


def _ids(membros: tuple[StaffMember, ...]) -> set[str]:
    return {m.employee_id for m in membros}


def test_l_st2_quadro_ativo_e_todos_os_ativos_da_unidade_e_so_eles(mundo: StaffReadPort) -> None:
    assert _ids(mundo.list_active_members(_T1, _U1)) == {"ana", "bia"}


def test_l_st1_nenhuma_leitura_cruza_unidade_ou_tenant(mundo: StaffReadPort) -> None:
    assert _ids(mundo.list_active_members(_T1, _U2)) == {"ana-u2"}
    assert _ids(mundo.list_active_members(_T2, _U1)) == {"dani"}
    assert mundo.list_active_members(_T2, _U2) == ()


def test_l_st3_lote_devolve_os_da_unidade_ativos_ou_nao_e_omite_os_demais(
    mundo: StaffReadPort,
) -> None:
    pedidos = frozenset({EmployeeId(e) for e in ("ana", "caio", "ana-u2", "dani", "zé")})
    devolvidos = mundo.list_members(_T1, _U1, pedidos)
    assert _ids(devolvidos) == {"ana", "caio"}
    assert {m.employee_id: m.active for m in devolvidos} == {"ana": True, "caio": False}


def test_l_st3_lote_vazio_devolve_vazio(mundo: StaffReadPort) -> None:
    assert mundo.list_members(_T1, _U1, frozenset()) == ()


def test_l_st4_vinculo_de_login_na_unidade_ativos_ou_nao(mundo: StaffReadPort) -> None:
    assert _ids(mundo.list_members_of_user(_T1, _U1, "user-ana")) == {"ana", "caio"}
    assert _ids(mundo.list_members_of_user(_T1, _U2, "user-ana")) == {"ana-u2"}
    assert mundo.list_members_of_user(_T1, _U1, "user-outro") == ()


def test_l_st5_catalogo_e_o_do_tenant_e_so_ele(mundo: StaffReadPort) -> None:
    assert {f.job_function_id: f.name for f in mundo.list_job_functions(_T1)} == {
        "cozinheiro": "Cozinheiro",
        "atendente": "Atendente",
    }
    assert {f.job_function_id for f in mundo.list_job_functions(_T2)} == {"garcom"}


def test_os_valores_do_registro_chegam_inteiros(mundo: StaffReadPort) -> None:
    (ana,) = mundo.list_members(_T1, _U1, frozenset({EmployeeId("ana")}))
    assert ana == _membro("ana", _U1)

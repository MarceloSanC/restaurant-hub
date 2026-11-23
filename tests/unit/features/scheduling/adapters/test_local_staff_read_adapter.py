"""`LocalStaffReadAdapter` — a tradução de primitivos de staff para os tipos de scheduling (CA15).

O adapter roda aqui sobre uma fachada **dublê** que devolve primitivos fixos: o que se mede é
a tradução, e as leis L-ST1 a L-ST6 rodam na suíte de contrato contra o adapter sobre a
fachada real e os repositórios Postgres. A forma da aresta (só o gateway importa staff, e só
a fachada) é cobrada em `tests/unit/features/scheduling/test_bc_independence.py`.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.adapters.out.staff.local_staff_read_adapter import (
    LocalStaffReadAdapter,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
    StaffMember,
    StaffReadPort,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.application.facade import StaffFunction, StaffRecord

pytestmark = pytest.mark.unit

_JANELA = (datetime(2026, 11, 3, 8, 0), datetime(2026, 11, 3, 18, 30))
_ANA = StaffRecord(
    employee_id="ana",
    unit_id="u1",
    name="Ana",
    active=True,
    job_function_ids=frozenset({"cozinheiro", "caixa"}),
    weekly_hours=Decimal("22.33"),
    unavailabilities=(_JANELA,),
)
_BIA = StaffRecord(
    employee_id="bia",
    unit_id="u1",
    name="Bia",
    active=False,
    job_function_ids=frozenset({"atendente"}),
    weekly_hours=None,
    unavailabilities=(),
)


class _FachadaDuble:
    """Devolve primitivos fixos e registra os argumentos — a fachada não decide nada aqui."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[object, ...]] = []

    def list_active_records(self, tenant_id: str, unit_id: str) -> tuple[StaffRecord, ...]:
        self.chamadas.append(("ativos", tenant_id, unit_id))
        return (_ANA,)

    def list_records(
        self, tenant_id: str, unit_id: str, employee_ids: frozenset[str]
    ) -> tuple[StaffRecord, ...]:
        self.chamadas.append(("lote", tenant_id, unit_id, employee_ids))
        return (_ANA, _BIA)

    def list_records_of_user(
        self, tenant_id: str, unit_id: str, user_id: str
    ) -> tuple[StaffRecord, ...]:
        self.chamadas.append(("login", tenant_id, unit_id, user_id))
        return (_BIA,)

    def list_functions(self, tenant_id: str) -> tuple[StaffFunction, ...]:
        self.chamadas.append(("catalogo", tenant_id))
        return (StaffFunction("cozinheiro", "Cozinheiro"),)

    def list_unit_functions(self, tenant_id: str, unit_id: str) -> tuple[StaffFunction, ...]:
        self.chamadas.append(("unidade", tenant_id, unit_id))
        return (StaffFunction("caixa", "Caixa"),)


def _adapter() -> tuple[StaffReadPort, _FachadaDuble]:
    fachada = _FachadaDuble()
    return LocalStaffReadAdapter(fachada), fachada  # type: ignore[arg-type]


def test_o_registro_vira_staff_member_campo_a_campo() -> None:
    adapter, fachada = _adapter()
    (ana,) = adapter.list_active_members(TenantId("t1"), UnitId("u1"))
    assert ana == StaffMember(
        employee_id=EmployeeId("ana"),
        unit_id=UnitId("u1"),
        display_name="Ana",
        active=True,
        job_function_ids=frozenset({JobFunctionId("cozinheiro"), JobFunctionId("caixa")}),
        contracted_weekly_hours=Decimal("22.33"),
        unavailabilities=(UnavailabilityWindow(start=_JANELA[0], end=_JANELA[1]),),
    )
    assert type(ana.unavailabilities[0]) is UnavailabilityWindow
    assert type(ana.contracted_weekly_hours) is Decimal
    assert fachada.chamadas == [("ativos", "t1", "u1")]


def test_sob_demanda_e_inativo_atravessam() -> None:
    adapter, fachada = _adapter()
    ids = frozenset({EmployeeId("ana"), EmployeeId("bia")})
    _, bia = adapter.list_members(TenantId("t1"), UnitId("u1"), ids)
    assert (bia.active, bia.contracted_weekly_hours, bia.unavailabilities) == (False, None, ())
    assert fachada.chamadas == [("lote", "t1", "u1", frozenset({"ana", "bia"}))]


def test_vinculo_de_login_repassa_o_endereco_e_o_login() -> None:
    adapter, fachada = _adapter()
    (bia,) = adapter.list_members_of_user(TenantId("t1"), UnitId("u2"), "user-bia")
    assert bia.employee_id == "bia"
    assert fachada.chamadas == [("login", "t1", "u2", "user-bia")]


def test_o_catalogo_vira_job_function_entry() -> None:
    adapter, fachada = _adapter()
    assert adapter.list_job_functions(TenantId("t2")) == (
        JobFunctionEntry(JobFunctionId("cozinheiro"), "Cozinheiro"),
    )
    assert fachada.chamadas == [("catalogo", "t2")]


def test_as_funcoes_da_unidade_viram_job_function_entry() -> None:
    """Issue #209: a leitura das funções habilitadas repassa o endereço inteiro."""
    fachada = _FachadaDuble()
    adapter = LocalStaffReadAdapter(fachada)  # type: ignore[arg-type]
    (caixa,) = adapter.list_unit_job_functions(TenantId("t1"), UnitId("u2"))
    assert caixa == JobFunctionEntry(JobFunctionId("caixa"), "Caixa")
    assert type(caixa.job_function_id) is str
    assert fachada.chamadas == [("unidade", "t1", "u2")]

"""O repositório de escala sem banco — CA06 (varredura) e os statements das checagens.

A trilha é só de inserção (ADR 4.4.0002): o módulo não pode ter `UPDATE` nem `DELETE` sobre
`schedule_changes`, nem pela API do Core nem por SQL cru. E os statements das checagens da
lei compilam para o dialeto Postgres com o SQL que o protocolo de escrita promete — o
primeiro lugar onde um erro de SQL aparece é aqui, não no Actions.
"""

import ast
import inspect
import re
from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import Executable
from sqlalchemy.dialects import postgresql

from restaurant_hub.features.scheduling.adapters.out.postgres import schedule_repository
from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository import (
    internal_ids_in_use_statements,
    next_seq_statement,
    period_taken_statement,
    schedule_id_taken_statement,
    stored_version_statement,
    unit_lock_statement,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import scheduling_metadata
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange

pytestmark = pytest.mark.unit

_SEG = date(2026, 11, 2)


def _sql(statement: Executable) -> str:
    compilado = statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return " ".join(str(compilado).split())


def _escala() -> Schedule:
    inicio = datetime.combine(_SEG, time(10))
    return (
        Schedule(
            id=ScheduleId("s1"),
            tenant_id=TenantId("t1"),
            unit_id=UnitId("u1"),
            period=SchedulePeriod(first_day=_SEG),
            calendar=OperationalCalendar.default(),
        )
        .enable_band(ShiftBandId("fB"), TimeRange(start=inicio, end=inicio + timedelta(hours=4)))
        .enable_band(
            ShiftBandId("fa"),
            TimeRange(start=inicio + timedelta(hours=5), end=inicio + timedelta(hours=9)),
        )
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("fB"), JobFunctionId("c"), DemandQuantity(1)
        )
        .assign(AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana"))
    )


# ---------------------------------------------------------------------------
# A trilha é só de inserção
# ---------------------------------------------------------------------------


def test_o_modulo_nao_atualiza_nem_apaga_a_trilha() -> None:
    fonte = inspect.getsource(schedule_repository)
    arvore = ast.parse(fonte)
    mutacoes = [
        no.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Attribute)
        and no.attr in {"update", "delete"}
        and isinstance(no.value, ast.Name)
        and no.value.id == "schedule_changes"
    ]
    assert mutacoes == []
    textos = [
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str)
    ]
    assert not [t for t in textos if re.search(r"(?i)(update|delete\s+from)\s+schedule_changes", t)]


def test_as_escritas_nomeadas_do_modulo_sao_as_do_protocolo() -> None:
    """`UPDATE` só da raiz (a versão); `DELETE` só das faixas (a reescrita, em cascata).

    As filhas são inseridas por um laço sobre as três tabelas (`_insert_children`), que não
    aparece aqui pelo nome; toda outra escrita nomeada sobre uma tabela do BC aparece.
    """
    arvore = ast.parse(inspect.getsource(schedule_repository))
    escritas = {
        (no.value.id, no.attr)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Attribute)
        and no.attr in {"insert", "update", "delete"}
        and isinstance(no.value, ast.Name)
        and no.value.id in scheduling_metadata.tables
    }
    assert escritas == {
        ("schedules", "insert"),
        ("schedules", "update"),
        ("schedule_bands", "delete"),
        ("schedule_changes", "insert"),
    }


# ---------------------------------------------------------------------------
# Os statements das checagens, compilados para o Postgres
# ---------------------------------------------------------------------------


def test_o_lock_da_unidade_e_transacional_sobre_o_hash_de_tenant_e_unidade() -> None:
    compilado = unit_lock_statement("t1", "u1").compile(dialect=postgresql.dialect())
    assert " ".join(str(compilado).split()) == (
        "SELECT pg_advisory_xact_lock(hashtextextended(%(hashtextextended_1)s, "
        "%(hashtextextended_2)s)) AS pg_advisory_xact_lock_1"
    )
    # O separador é o caractere de controle 0x1F — `split()` o trataria como branco.
    assert compilado.params == {"hashtextextended_1": "t1\x1fu1", "hashtextextended_2": 0}


def test_a_chave_do_lock_separa_tenant_e_unidade() -> None:
    assert _sql(unit_lock_statement("ab", "c")) != _sql(unit_lock_statement("a", "bc"))


def test_o_id_da_escala_e_procurado_em_qualquer_tenant() -> None:
    assert _sql(schedule_id_taken_statement("s1")) == (
        "SELECT schedules.id FROM schedules WHERE schedules.id = 's1'"
    )


def test_o_periodo_e_comparado_como_faixa_semiaberta_na_unidade() -> None:
    """`[first, first + days)` contra `[_SEG, _SEG + 7)`: adjacente não cruza."""
    assert _sql(period_taken_statement(_escala())) == (
        "SELECT schedules.id FROM schedules WHERE schedules.tenant_id = 't1' "
        "AND schedules.unit_id = 'u1' AND schedules.first_day < '2026-11-09' "
        "AND schedules.first_day + schedules.days > '2026-11-02'"
    )


def test_os_ids_internos_sao_procurados_por_tipo_nas_outras_escalas_da_unidade() -> None:
    statements = internal_ids_in_use_statements(_escala())
    assert [tipo for tipo, _ in statements] == ["ShiftBandId", "ShiftDemandId", "AssignmentId"]
    _, faixas = statements[0]
    assert _sql(faixas) == (
        "SELECT schedule_bands.id FROM schedule_bands WHERE schedule_bands.tenant_id = 't1' "
        "AND schedule_bands.unit_id = 'u1' AND schedule_bands.schedule_id != 's1' "
        "AND schedule_bands.id IN ('fB', 'fa')"
    )


def test_tipo_sem_ids_nao_vai_ao_banco() -> None:
    vazia = Schedule(
        id=ScheduleId("s1"),
        tenant_id=TenantId("t1"),
        unit_id=UnitId("u1"),
        period=SchedulePeriod(first_day=_SEG),
        calendar=OperationalCalendar.default(),
    )
    assert internal_ids_in_use_statements(vazia) == ()


def test_a_versao_e_lida_no_endereco_de_tres_partes() -> None:
    assert _sql(stored_version_statement(_escala())) == (
        "SELECT schedules.version FROM schedules WHERE schedules.id = 's1' "
        "AND schedules.tenant_id = 't1' AND schedules.unit_id = 'u1'"
    )


def test_o_proximo_seq_e_o_maior_da_escala_mais_um() -> None:
    assert _sql(next_seq_statement("s1")) == (
        "SELECT coalesce(max(schedule_changes.seq), 0) + 1 AS anon_1 FROM schedule_changes "
        "WHERE schedule_changes.schedule_id = 's1'"
    )

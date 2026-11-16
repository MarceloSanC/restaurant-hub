"""Testes do schema declarado em `tables.py` do BC scheduling — sem banco (CA08).

Não substituem os de integração (`test_schema.py`, contra o schema **migrado**); guardam o
que é fácil de quebrar por edição descuidada e caro de descobrir em produção:

- nome de constraint alterado quebra a tradução por nome (ADR 3.3.0004) e só aparece como
  erro cru no primeiro conflito real;
- a exclusion constraint de L-SC2 com outro operador ou outra faixa deixaria passar dias
  sobrepostos com a suíte verde — daí a igualdade sobre o DDL **compilado**;
- um valor novo num enum do domínio sem a `CHECK` correspondente só apareceria como
  `IntegrityError` em produção — daí a asserção de **derivação**;
- uma coluna anulável em `scheduling_settings` tornaria representável a configuração
  incompleta que o port não completa (L-CF1).
"""

import dataclasses
import re
from datetime import date

import pytest
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Integer,
    Table,
    Text,
    Time,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.schema import AddConstraint

from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    EX_SCHEDULES_UNIT_DAYS_DISJOINT,
    LIMIT_CHECKS,
    PK_SCHEDULES,
    POLICY_FIELDS,
    schedule_assignments,
    schedule_bands,
    schedule_changes,
    schedule_demands,
    schedules,
    scheduling_metadata,
    scheduling_settings,
)
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidSchedulePeriodError,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import Weekday
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyRule,
    ValidationConfig,
    WorkloadDirection,
)

pytestmark = pytest.mark.unit

_FILHAS = (schedule_bands, schedule_demands, schedule_assignments)


def _nomes_de_constraint(table: Table) -> set[str]:
    return {str(c.name) for c in table.constraints if c.name is not None}


def _checks(table: Table) -> dict[str, str]:
    return {
        str(c.name): " ".join(str(c.sqltext).split())
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


def _fks(table: Table) -> dict[str, ForeignKeyConstraint]:
    return {
        str(c.name): c for c in table.constraints if isinstance(c, ForeignKeyConstraint) and c.name
    }


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def test_metadata_declara_exatamente_as_seis_tabelas() -> None:
    """Tabela nova ou removida força revisão consciente — e da migration junto."""
    assert set(scheduling_metadata.tables) == {
        "schedules",
        "schedule_bands",
        "schedule_demands",
        "schedule_assignments",
        "schedule_changes",
        "scheduling_settings",
    }


def test_toda_constraint_e_todo_indice_tem_nome_explicito() -> None:
    for table in scheduling_metadata.tables.values():
        for constraint in table.constraints:
            assert constraint.name is not None, f"constraint sem nome em {table.name}"
            assert not str(constraint.name).startswith("_unnamed_"), table.name
        for index in table.indexes:
            assert index.name is not None, f"índice sem nome em {table.name}"


def test_nomes_de_constraint_de_cada_tabela() -> None:
    """Igualdade de conjunto: constraint acrescentada em silêncio muda o que o banco recusa."""
    assert _nomes_de_constraint(schedules) == {
        PK_SCHEDULES,
        "uq_schedules_tenant_unit_id",
        EX_SCHEDULES_UNIT_DAYS_DISJOINT,
        "ck_schedules_days_range",
        "ck_schedules_version_positive",
        "ck_schedules_week_start_known",
    }
    assert _nomes_de_constraint(schedule_bands) == {
        "pk_schedule_bands",
        "uq_schedule_bands_schedule_id",
        "fk_schedule_bands_schedule",
        "ck_schedule_bands_period",
        "ck_schedule_bands_break_non_negative",
    }
    assert _nomes_de_constraint(schedule_demands) == {
        "pk_schedule_demands",
        "uq_schedule_demands_schedule_id",
        "fk_schedule_demands_band",
        "ck_schedule_demands_quantity_non_negative",
    }
    assert _nomes_de_constraint(schedule_assignments) == {
        "pk_schedule_assignments",
        "fk_schedule_assignments_demand",
        "ck_schedule_assignments_break_non_negative",
    }
    assert _nomes_de_constraint(schedule_changes) == {
        "pk_schedule_changes",
        "fk_schedule_changes_schedule",
        "ck_schedule_changes_seq_positive",
        "ck_schedule_changes_operations_is_array",
        "ck_schedule_changes_acknowledged_is_array",
    }
    assert _nomes_de_constraint(scheduling_settings) == {
        "pk_scheduling_settings",
        "ck_scheduling_settings_week_start_known",
        "ck_scheduling_settings_workload_direction_known",
        *(f"ck_scheduling_settings_{policy}_mode_known" for policy in POLICY_FIELDS),
        *(f"ck_scheduling_settings_{name}_range" for name, _ in LIMIT_CHECKS),
    }


def test_o_unico_indice_alem_das_chaves_e_o_das_leituras() -> None:
    """ADR 4.4.0001: o de `schedules` serve as três leituras; nada além do medido."""
    indices = {
        index.name: [column.name for column in index.columns]
        for table in scheduling_metadata.tables.values()
        for index in table.indexes
    }
    assert indices == {
        "ix_schedules_tenant_unit_first_day": ["tenant_id", "unit_id", "first_day"],
    }


def test_id_da_escala_colide_no_banco_inteiro_e_os_internos_por_unidade() -> None:
    """L-SC1: a PK da raiz não inclui o tenant; ADR 4.3.0004 §1: a das filhas inclui a unidade."""
    assert [c.name for c in schedules.primary_key.columns] == ["id"]
    for filha in _FILHAS:
        assert [c.name for c in filha.primary_key.columns] == ["tenant_id", "unit_id", "id"]
    assert [c.name for c in schedule_changes.primary_key.columns] == ["schedule_id", "seq"]


def test_o_cerco_fks_compostas_com_tenant_unidade_e_escala() -> None:
    """Toda filha referencia o pai pela chave que inclui tenant, unidade e escala.

    Uma FK sem `schedule_id` deixaria a demanda de uma escala presa à faixa de outra.
    """
    esperado = {
        schedule_bands: (
            "fk_schedule_bands_schedule",
            ["tenant_id", "unit_id", "schedule_id"],
            ["schedules.tenant_id", "schedules.unit_id", "schedules.id"],
        ),
        schedule_demands: (
            "fk_schedule_demands_band",
            ["tenant_id", "unit_id", "schedule_id", "band_id"],
            [
                "schedule_bands.tenant_id",
                "schedule_bands.unit_id",
                "schedule_bands.schedule_id",
                "schedule_bands.id",
            ],
        ),
        schedule_assignments: (
            "fk_schedule_assignments_demand",
            ["tenant_id", "unit_id", "schedule_id", "demand_id"],
            [
                "schedule_demands.tenant_id",
                "schedule_demands.unit_id",
                "schedule_demands.schedule_id",
                "schedule_demands.id",
            ],
        ),
    }
    for filha, (nome, colunas, alvos) in esperado.items():
        fks = _fks(filha)
        assert set(fks) == {nome}
        assert [c.name for c in fks[nome].columns] == colunas
        assert [e.target_fullname for e in fks[nome].elements] == alvos
        assert fks[nome].ondelete == "CASCADE"
        # FK composta é MATCH SIMPLE: com uma coluna anulável o cerco seria decorativo.
        for coluna in colunas:
            assert filha.c[coluna].nullable is False, f"{filha.name}.{coluna}"


def test_a_trilha_referencia_a_escala_com_restrict() -> None:
    """ADR 4.4.0002: apagar uma escala exige decidir o destino da trilha dela."""
    fks = _fks(schedule_changes)
    assert set(fks) == {"fk_schedule_changes_schedule"}
    fk = fks["fk_schedule_changes_schedule"]
    assert [c.name for c in fk.columns] == ["schedule_id"]
    assert [e.target_fullname for e in fk.elements] == ["schedules.id"]
    assert fk.ondelete == "RESTRICT"


def test_nenhuma_fk_aponta_para_fora_do_metadata_de_scheduling() -> None:
    """ADR 3.3.0002: tenant, unidade, registro, função e autor são texto opaco."""
    tabelas_do_bc = set(scheduling_metadata.tables)
    for table in scheduling_metadata.tables.values():
        for fk in table.foreign_keys:
            assert fk.column.table.name in tabelas_do_bc, table.name
    assert set(schedules.foreign_keys) == set()
    assert set(scheduling_settings.foreign_keys) == set()


def test_a_exclusion_constraint_compila_para_o_sql_de_d_disjoint() -> None:
    """L-SC2: `daterange(first, first + days)` é `[)` e cobre exatamente os `days` dias."""
    (exclusao,) = [c for c in schedules.constraints if isinstance(c, ExcludeConstraint)]
    ddl = " ".join(
        str(AddConstraint(exclusao).compile(dialect=postgresql.dialect())).split()  # type: ignore[no-untyped-call]
    )
    assert ddl == (
        f"ALTER TABLE schedules ADD CONSTRAINT {EX_SCHEDULES_UNIT_DAYS_DISJOINT} "
        "EXCLUDE USING gist (tenant_id WITH =, unit_id WITH =, "
        "daterange(first_day, first_day + days) WITH &&)"
    )
    # `NOT NULL` nas colunas da faixa é load-bearing: limite nulo produz faixa infinita.
    for coluna in ("tenant_id", "unit_id", "first_day", "days"):
        assert schedules.c[coluna].nullable is False


def test_os_dois_regimes_de_tempo() -> None:
    """§5.12: faixas em wall-clock ingênuo; o carimbo da trilha em instante absoluto."""
    for coluna in (schedule_bands.c.start_at, schedule_bands.c.end_at):
        assert isinstance(coluna.type, TIMESTAMP)
        assert coluna.type.timezone is False
    assert isinstance(schedule_changes.c.occurred_at.type, TIMESTAMP)
    assert schedule_changes.c.occurred_at.type.timezone is True
    assert isinstance(schedules.c.first_day.type, Date)
    for coluna in (schedules.c.day_cutoff, scheduling_settings.c.day_cutoff):
        assert isinstance(coluna.type, Time)
        assert coluna.type.timezone is False


def test_tipos_das_demais_colunas() -> None:
    texto = {
        schedules: ("id", "tenant_id", "unit_id", "week_start"),
        schedule_demands: ("job_function_id",),
        schedule_assignments: ("employee_id",),
        schedule_changes: ("schedule_id", "author_user_id"),
    }
    for tabela, colunas in texto.items():
        for coluna in colunas:
            assert isinstance(tabela.c[coluna].type, Text), f"{tabela.name}.{coluna}"
    inteiros = {
        schedules: ("days", "version"),
        schedule_bands: ("position", "break_minutes"),
        schedule_demands: ("position", "quantity"),
        schedule_assignments: ("position", "break_minutes"),
        schedule_changes: ("seq", "previous_version", "resulting_version"),
    }
    for tabela, colunas in inteiros.items():
        for coluna in colunas:
            assert isinstance(tabela.c[coluna].type, Integer), f"{tabela.name}.{coluna}"
    for coluna in ("counts_toward_workload", "function_exception"):
        assert isinstance(schedule_assignments.c[coluna].type, Boolean)
    for coluna in ("operations", "acknowledged"):
        assert isinstance(schedule_changes.c[coluna].type, JSONB)


def test_anulaveis_sao_so_os_dois_estados_que_o_dominio_distingue() -> None:
    """`break_minutes` da alocação (`None` herda, `0` é zero) e `previous_version` (criação)."""
    anulaveis = {
        f"{table.name}.{column.name}"
        for table in scheduling_metadata.tables.values()
        for column in table.columns
        if column.nullable
    }
    assert anulaveis == {
        "schedule_assignments.break_minutes",
        "schedule_changes.previous_version",
    }


def test_nenhuma_coluna_tem_default_de_servidor() -> None:
    """L-CF1: o port não inventa default; os do domínio são do use case."""
    for table in scheduling_metadata.tables.values():
        for column in table.columns:
            assert column.server_default is None, f"{table.name}.{column.name}"
            assert column.default is None, f"{table.name}.{column.name}"


def test_as_politicas_configuraveis_sao_os_campos_policy_rule_de_validation_config() -> None:
    """Fonte única: política nova no domínio chega às colunas sem segunda lista."""
    assert (
        tuple(f.name for f in dataclasses.fields(ValidationConfig) if f.type is PolicyRule)
        == POLICY_FIELDS
    )
    assert len(POLICY_FIELDS) == 8  # noqa: PLR2004


def test_scheduling_settings_tem_uma_coluna_por_campo_da_configuracao() -> None:
    """Calendário, um par por política, os quatro limites e a direção — e nada mais."""
    esperadas = {
        "tenant_id",
        "week_start",
        "day_cutoff",
        *(f"{policy}_enabled" for policy in POLICY_FIELDS),
        *(f"{policy}_mode" for policy in POLICY_FIELDS),
        *(name for name, _ in LIMIT_CHECKS),
        "workload_direction",
    }
    assert {c.name for c in scheduling_settings.columns} == esperadas
    assert [c.name for c in scheduling_settings.primary_key.columns] == ["tenant_id"]
    for policy in POLICY_FIELDS:
        assert isinstance(scheduling_settings.c[f"{policy}_enabled"].type, Boolean)
        assert isinstance(scheduling_settings.c[f"{policy}_mode"].type, Text)
    for name, _ in LIMIT_CHECKS:
        assert isinstance(scheduling_settings.c[name].type, Integer)


def test_os_limites_sao_os_campos_inteiros_de_validation_config() -> None:
    inteiros = tuple(f.name for f in dataclasses.fields(ValidationConfig) if f.type is int)
    assert tuple(name for name, _ in LIMIT_CHECKS) == inteiros


def test_texto_exato_das_checks_derivadas_dos_enums() -> None:
    """A lista de cada `CHECK` é derivada do enum **aqui também** — senão o teste seria a
    segunda fonte que a derivação elimina."""
    dias = _in_list(tuple(w.value for w in Weekday))
    modos = _in_list(tuple(m.value for m in EnforcementMode))
    direcoes = _in_list(tuple(d.value for d in WorkloadDirection))
    assert _checks(schedules)["ck_schedules_week_start_known"] == f"week_start IN ({dias})"
    configuracao = _checks(scheduling_settings)
    assert configuracao["ck_scheduling_settings_week_start_known"] == f"week_start IN ({dias})"
    assert (
        configuracao["ck_scheduling_settings_workload_direction_known"]
        == f"workload_direction IN ({direcoes})"
    )
    for policy in POLICY_FIELDS:
        assert (
            configuracao[f"ck_scheduling_settings_{policy}_mode_known"]
            == f"{policy}_mode IN ({modos})"
        )


def test_texto_exato_das_checks_de_faixa_numerica() -> None:
    """A operação lógica, não a presença dos operandos: `>` virando `>=` tem de reprovar."""
    assert _checks(schedules)["ck_schedules_days_range"] == "days BETWEEN 1 AND 31"
    assert _checks(schedules)["ck_schedules_version_positive"] == "version >= 1"
    assert _checks(schedule_bands) == {
        "ck_schedule_bands_period": "start_at < end_at",
        "ck_schedule_bands_break_non_negative": "break_minutes >= 0",
    }
    assert _checks(schedule_demands) == {
        "ck_schedule_demands_quantity_non_negative": "quantity >= 0",
    }
    assert _checks(schedule_assignments) == {
        "ck_schedule_assignments_break_non_negative": "break_minutes IS NULL OR break_minutes >= 0",
    }
    assert _checks(schedule_changes) == {
        "ck_schedule_changes_seq_positive": "seq >= 1",
        "ck_schedule_changes_operations_is_array": "jsonb_typeof(operations) = 'array'",
        "ck_schedule_changes_acknowledged_is_array": "jsonb_typeof(acknowledged) = 'array'",
    }
    configuracao = _checks(scheduling_settings)
    assert {nome: texto for nome, texto in configuracao.items() if nome.endswith("_range")} == {
        "ck_scheduling_settings_min_rest_minutes_range": "min_rest_minutes >= 0",
        "ck_scheduling_settings_daily_cap_minutes_range": "daily_cap_minutes > 0",
        "ck_scheduling_settings_weekly_cap_minutes_range": "weekly_cap_minutes > 0",
        "ck_scheduling_settings_workload_tolerance_minutes_range": (
            "workload_tolerance_minutes >= 0"
        ),
    }


def test_a_faixa_de_days_e_a_de_schedule_period() -> None:
    """`days BETWEEN 1 AND 31` aceita exatamente o que o VO aceita, nas duas bordas."""
    minimo, maximo = (
        int(n) for n in re.findall(r"\d+", _checks(schedules)["ck_schedules_days_range"])
    )
    SchedulePeriod(first_day=date(2026, 11, 2), days=minimo)
    SchedulePeriod(first_day=date(2026, 11, 2), days=maximo)
    for fora in (minimo - 1, maximo + 1):
        with pytest.raises(InvalidSchedulePeriodError):
            SchedulePeriod(first_day=date(2026, 11, 2), days=fora)

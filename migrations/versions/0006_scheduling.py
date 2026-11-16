"""scheduling — as seis tabelas do bounded context de escala (Stage 4.4).

Materializa o schema que a Stage 4.4 declarou em
`features/scheduling/adapters/out/postgres/tables.py`: o agregado em quatro tabelas
(`schedules` → `schedule_bands` → `schedule_demands` → `schedule_assignments`), a
trilha de auditoria (`schedule_changes`) e a configuração do tenant
(`scheduling_settings`).

**Numeração:** `0006`, não `0003` como o bloco 4.4 do roadmap dizia. `0003` é de staff
desde a Stage 3.3, e a `0005` é da Stage 3.11 (PR #188), que correu em paralelo com esta.
As duas nasceram sobre a `0004`; a 3.11 mergeou primeiro, e esta passou a apontar para a
`0005`, para o Alembic ter um head só (concept 4.4 §7 D-MIG).

**A extensão `btree_gist`** é criada aqui: a exclusion constraint de dias disjuntos
(L-SC2, ADR 4.4.0001) compara `tenant_id` e `unit_id` com `=` dentro de um índice GiST,
o que exige os operadores de B-tree para GiST. É *trusted* no PostgreSQL 16 (instalável
por quem tem `CREATE` no banco). O `downgrade` **não** a remove: ela pode ter existido
antes desta migration, e outro objeto pode depender dela.

**Escrita à mão, como as anteriores:** a migration é registro histórico congelado. Os
conjuntos fechados das `CHECK` (dias da semana, modos, direções) e as oito políticas
configuráveis estão congelados abaixo em vez de importados do domínio — uma migration
que lesse o enum de hoje descreveria o schema de hoje, e não o do dia em que foi
aplicada.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sem fuso: wall-clock da unidade (ADR 4.1.0007). Com fuso: o carimbo da trilha.
_TIMESTAMP_SEM_FUSO = sa.TIMESTAMP(timezone=False)
_TIMESTAMP_COM_FUSO = sa.TIMESTAMP(timezone=True)
_TIME_SEM_FUSO = sa.Time(timezone=False)

# Congelados no valor desta data — ver o docstring.
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MODES = ("block", "warn")
_DIRECTIONS = ("excess", "both")
_POLICIES = (
    "overlap",
    "rest_between_shifts",
    "daily_cap",
    "weekly_cap",
    "workload",
    "function_mismatch",
    "over_coverage",
    "break_divergence",
)
_LIMITS = (
    ("min_rest_minutes", ">= 0"),
    ("daily_cap_minutes", "> 0"),
    ("weekly_cap_minutes", "> 0"),
    ("workload_tolerance_minutes", ">= 0"),
)


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Cria a extensão (se faltar) e o schema do BC scheduling."""
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "schedules",
        sa.Column("id", sa.Text(), nullable=False),
        # Opacos: nenhuma FK atravessa o bounded context (ADR 3.3.0002).
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("first_day", sa.Date(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        # O calendário fotografado na criação (ADR 4.1.0009).
        sa.Column("week_start", sa.Text(), nullable=False),
        sa.Column("day_cutoff", _TIME_SEM_FUSO, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # Colisão de id é global (L-SC1): o tenant não entra na PK.
        sa.PrimaryKeyConstraint("id", name="pk_schedules"),
        # Âncora das FKs compostas das faixas.
        sa.UniqueConstraint("tenant_id", "unit_id", "id", name="uq_schedules_tenant_unit_id"),
        # L-SC2: `daterange(d, d + n)` é `[)` e cobre exatamente os `n` dias.
        postgresql.ExcludeConstraint(
            (sa.column("tenant_id"), "="),
            (sa.column("unit_id"), "="),
            (sa.literal_column("daterange(first_day, first_day + days)"), "&&"),
            name="ex_schedules_unit_days_disjoint",
            using="gist",
        ),
        sa.CheckConstraint("days BETWEEN 1 AND 31", name="ck_schedules_days_range"),
        sa.CheckConstraint("version >= 1", name="ck_schedules_version_positive"),
        sa.CheckConstraint(
            f"week_start IN ({_in_list(_WEEKDAYS)})", name="ck_schedules_week_start_known"
        ),
    )
    op.create_index(
        "ix_schedules_tenant_unit_first_day", "schedules", ["tenant_id", "unit_id", "first_day"]
    )

    op.create_table(
        "schedule_bands",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("schedule_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_at", _TIMESTAMP_SEM_FUSO, nullable=False),
        sa.Column("end_at", _TIMESTAMP_SEM_FUSO, nullable=False),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        # Ids internos únicos por (tenant, unidade) — ADR 4.3.0004 §1.
        sa.PrimaryKeyConstraint("tenant_id", "unit_id", "id", name="pk_schedule_bands"),
        sa.UniqueConstraint(
            "tenant_id", "unit_id", "schedule_id", "id", name="uq_schedule_bands_schedule_id"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "unit_id", "schedule_id"],
            ["schedules.tenant_id", "schedules.unit_id", "schedules.id"],
            name="fk_schedule_bands_schedule",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("start_at < end_at", name="ck_schedule_bands_period"),
        sa.CheckConstraint("break_minutes >= 0", name="ck_schedule_bands_break_non_negative"),
    )

    op.create_table(
        "schedule_demands",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("schedule_id", sa.Text(), nullable=False),
        sa.Column("band_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("job_function_id", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "unit_id", "id", name="pk_schedule_demands"),
        sa.UniqueConstraint(
            "tenant_id", "unit_id", "schedule_id", "id", name="uq_schedule_demands_schedule_id"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "unit_id", "schedule_id", "band_id"],
            [
                "schedule_bands.tenant_id",
                "schedule_bands.unit_id",
                "schedule_bands.schedule_id",
                "schedule_bands.id",
            ],
            name="fk_schedule_demands_band",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_schedule_demands_quantity_non_negative"),
    )

    op.create_table(
        "schedule_assignments",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("schedule_id", sa.Text(), nullable=False),
        sa.Column("demand_id", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("counts_toward_workload", sa.Boolean(), nullable=False),
        sa.Column("function_exception", sa.Boolean(), nullable=False),
        # `NULL` herda o intervalo da faixa; `0` é intervalo próprio de zero (ADR 4.1.0011).
        sa.Column("break_minutes", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("tenant_id", "unit_id", "id", name="pk_schedule_assignments"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "unit_id", "schedule_id", "demand_id"],
            [
                "schedule_demands.tenant_id",
                "schedule_demands.unit_id",
                "schedule_demands.schedule_id",
                "schedule_demands.id",
            ],
            name="fk_schedule_assignments_demand",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "break_minutes IS NULL OR break_minutes >= 0",
            name="ck_schedule_assignments_break_non_negative",
        ),
    )

    op.create_table(
        "schedule_changes",
        sa.Column("schedule_id", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Text(), nullable=False),
        sa.Column("occurred_at", _TIMESTAMP_COM_FUSO, nullable=False),
        sa.Column("previous_version", sa.Integer(), nullable=True),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("operations", postgresql.JSONB(), nullable=False),
        sa.Column("acknowledged", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("schedule_id", "seq", name="pk_schedule_changes"),
        # `RESTRICT`: apagar uma escala exige decidir o destino da trilha dela.
        sa.ForeignKeyConstraint(
            ["schedule_id"],
            ["schedules.id"],
            name="fk_schedule_changes_schedule",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("seq >= 1", name="ck_schedule_changes_seq_positive"),
        sa.CheckConstraint(
            "jsonb_typeof(operations) = 'array'", name="ck_schedule_changes_operations_is_array"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(acknowledged) = 'array'",
            name="ck_schedule_changes_acknowledged_is_array",
        ),
    )

    # Sempre uma configuração completa: toda coluna `NOT NULL`, sem default de servidor.
    op.create_table(
        "scheduling_settings",
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("week_start", sa.Text(), nullable=False),
        sa.Column("day_cutoff", _TIME_SEM_FUSO, nullable=False),
        *(
            column
            for policy in _POLICIES
            for column in (
                sa.Column(f"{policy}_enabled", sa.Boolean(), nullable=False),
                sa.Column(f"{policy}_mode", sa.Text(), nullable=False),
            )
        ),
        *(sa.Column(name, sa.Integer(), nullable=False) for name, _ in _LIMITS),
        sa.Column("workload_direction", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_scheduling_settings"),
        sa.CheckConstraint(
            f"week_start IN ({_in_list(_WEEKDAYS)})",
            name="ck_scheduling_settings_week_start_known",
        ),
        *(
            sa.CheckConstraint(
                f"{policy}_mode IN ({_in_list(_MODES)})",
                name=f"ck_scheduling_settings_{policy}_mode_known",
            )
            for policy in _POLICIES
        ),
        *(
            sa.CheckConstraint(f"{name} {bound}", name=f"ck_scheduling_settings_{name}_range")
            for name, bound in _LIMITS
        ),
        sa.CheckConstraint(
            f"workload_direction IN ({_in_list(_DIRECTIONS)})",
            name="ck_scheduling_settings_workload_direction_known",
        ),
    )


def downgrade() -> None:
    """Remove as seis tabelas, filhas antes das mães; a extensão fica (ver o docstring)."""
    op.drop_table("scheduling_settings")
    op.drop_table("schedule_changes")
    op.drop_table("schedule_assignments")
    op.drop_table("schedule_demands")
    op.drop_table("schedule_bands")
    op.drop_index("ix_schedules_tenant_unit_first_day", table_name="schedules")
    op.drop_table("schedules")

"""staff — as cinco tabelas do bounded context de equipe.

Terceira migration do projeto. Materializa o schema que a Stage 3.3 declarou em
`features/staff/adapters/out/postgres/tables.py`: as duas raízes de agregado
(`job_functions`, `employees`) e as três tabelas-filhas de `employees`.

**Numeração:** `0003`, não `0002`. O bloco 3.3 do roadmap ainda diz
`0002_staff.py`, mas `0002` foi consumido por `password_setup_tokens` na Stage
2.5 — a divergência é reconciliada por nota datada no roadmap (concept D10).

**Escrita à mão, como a `0001` e a `0002`, e pela mesma razão:** a migration é um
**registro histórico congelado** — descreve o schema como ele era neste ponto, e
não pode ser derivada de `tables.py`, que continua evoluindo. Por isso os valores
de `workload_kind` e de `period` estão congelados abaixo em vez de importados do
código: uma migration que lesse o enum de hoje descreveria o schema de hoje, e
não o do dia em que foi aplicada.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sem fuso: `UnavailabilityPeriod` guarda wall-clock do fuso da unidade e
# rejeita tz-aware na construção (ADR 3.1.0005). É o oposto de identity, e é
# deliberado.
_TIMESTAMP_SEM_FUSO = sa.TIMESTAMP(timezone=False)

# Congelados no valor desta data — ver a nota do docstring sobre registro
# histórico.
_WORKLOAD_KINDS = ("fixed", "on_demand")
_WORKLOAD_KIND_IN_LIST = ", ".join(f"'{kind}'" for kind in _WORKLOAD_KINDS)

_PERIODS = ("morning", "afternoon", "night", "overnight")
_PERIOD_IN_LIST = ", ".join(f"'{period}'" for period in _PERIODS)


def upgrade() -> None:
    """Cria o schema do BC staff."""
    op.create_table(
        "job_functions",
        sa.Column("id", sa.Text(), nullable=False),
        # Opaco: nenhuma FK para `restaurants` de identity (ADR 3.3.0002).
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # Colisão de id é global (L-JF1): o tenant não entra na PK.
        sa.PrimaryKeyConstraint("id", name="pk_job_functions"),
        # Unicidade verbatim e por tenant — sem `lower()`, sem `btrim`.
        sa.UniqueConstraint("tenant_id", "name", name="uq_job_functions_tenant_name"),
        # Âncora obrigatória da FK composta de `employee_job_functions`: o
        # Postgres exige índice único cobrindo exatamente as colunas
        # referenciadas. Sem ela, o `create_table` seguinte falha.
        sa.UniqueConstraint("id", "tenant_id", name="uq_job_functions_id_tenant"),
    )

    op.create_table(
        "employees",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("workload_kind", sa.Text(), nullable=False),
        # `NUMERIC` **sem precisão**: `NUMERIC(5,2)` arredondaria em silêncio
        # (`22.555 → 22.56`) e corromperia dado contra a disciplina verbatim.
        sa.Column("weekly_hours", sa.Numeric(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_employees"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_employees_id_tenant"),
        sa.CheckConstraint(
            f"workload_kind IN ({_WORKLOAD_KIND_IN_LIST})",
            name="ck_employees_workload_kind_known",
        ),
        # **iff**, não "permite nulo": barra `fixed` sem horas e `on_demand`
        # com horas.
        sa.CheckConstraint(
            "(workload_kind = 'fixed') = (weekly_hours IS NOT NULL)",
            name="ck_employees_workload_iff_hours",
        ),
        sa.CheckConstraint(
            "weekly_hours IS NULL OR weekly_hours > 0",
            name="ck_employees_weekly_hours_positive",
        ),
    )
    op.create_index("ix_employees_tenant_unit", "employees", ["tenant_id", "unit_id"])

    op.create_table(
        "employee_job_functions",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("job_function_id", sa.Text(), nullable=False),
        # `NOT NULL` mantém as FKs compostas ativas: MATCH SIMPLE ignora a FK
        # inteira quando qualquer coluna referenciante é nula.
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("employee_id", "job_function_id", name="pk_employee_job_functions"),
        sa.ForeignKeyConstraint(
            ["employee_id", "tenant_id"],
            ["employees.id", "employees.tenant_id"],
            name="fk_employee_job_functions_employee",
            ondelete="CASCADE",
        ),
        # `RESTRICT` implementa a remoção guardada de L-JF3.
        sa.ForeignKeyConstraint(
            ["job_function_id", "tenant_id"],
            ["job_functions.id", "job_functions.tenant_id"],
            name="fk_employee_job_functions_job_function",
            ondelete="RESTRICT",
        ),
    )
    # Sem este índice o `RESTRICT` acima varre a tabela inteira a cada remoção
    # de função — não é otimização.
    op.create_index(
        "ix_employee_job_functions_function",
        "employee_job_functions",
        ["job_function_id", "tenant_id"],
    )

    op.create_table(
        "employee_unavailabilities",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("start_at", _TIMESTAMP_SEM_FUSO, nullable=False),
        sa.Column("end_at", _TIMESTAMP_SEM_FUSO, nullable=False),
        sa.PrimaryKeyConstraint("employee_id", "start_at", name="pk_employee_unavailabilities"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_unavailabilities_employee",
            ondelete="CASCADE",
        ),
        # Semi-aberto `[start, end)`: intervalo vazio é recusado.
        sa.CheckConstraint("start_at < end_at", name="ck_employee_unavailabilities_period"),
    )

    op.create_table(
        "employee_shift_preferences",
        sa.Column("employee_id", sa.Text(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("employee_id", "period", name="pk_employee_shift_preferences"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_shift_preferences_employee",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"period IN ({_PERIOD_IN_LIST})",
            name="ck_employee_shift_preferences_period_known",
        ),
    )


def downgrade() -> None:
    """Remove o schema do BC staff, na ordem inversa das dependências de FK.

    As três filhas primeiro, depois `employees`, depois `job_functions`. O
    `CASCADE` resolveria sozinho, mas a ordem explícita documenta o grafo — e o
    `downgrade` é o caminho de rollback que ninguém exercita até precisar dele
    às três da manhã.
    """
    op.drop_table("employee_shift_preferences")
    op.drop_table("employee_unavailabilities")
    op.drop_index("ix_employee_job_functions_function", table_name="employee_job_functions")
    op.drop_table("employee_job_functions")
    op.drop_index("ix_employees_tenant_unit", table_name="employees")
    op.drop_table("employees")
    op.drop_table("job_functions")

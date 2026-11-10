"""staff — habilitação de função de trabalho por unidade (Stage 3.11).

Quinta migration do projeto. Materializa o modelo do ADR 3.11.0001: a função
continua do restaurante e passa a dizer **onde vale** — em todas as unidades
(`job_functions.enabled_in_all_units`) ou num conjunto não-vazio de unidades
(linhas de `job_function_units`).

**As funções que já existem nascem em todas as unidades** (issue #41, "default
seguro, preserva o comportamento atual"): o `DEFAULT true` da coluna preenche cada
linha existente, e nenhuma linha de vínculo é escrita. É por isso que "todas" é um
valor próprio e não a lista das unidades de hoje — esta migration **não lê** a
tabela `units` de identity (nenhum acesso nem FK entre BCs, ADR 3.3.0002).

Escrita à mão, como as anteriores — a migration é registro histórico congelado,
não derivação de `tables.py`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "job_functions",
        sa.Column("enabled_in_all_units", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "job_function_units",
        sa.Column("job_function_id", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("job_function_id", "unit_id", name="pk_job_function_units"),
        sa.ForeignKeyConstraint(
            ["job_function_id", "tenant_id"],
            ["job_functions.id", "job_functions.tenant_id"],
            name="fk_job_function_units_job_function",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_job_function_units_tenant_unit", "job_function_units", ["tenant_id", "unit_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_job_function_units_tenant_unit", table_name="job_function_units")
    op.drop_table("job_function_units")
    op.drop_column("job_functions", "enabled_in_all_units")

"""password setup tokens — tabela do fluxo de convite e redefinição de senha.

Segunda migration do projeto. Cria a tabela que torna o **uso único** do token de
definição de senha uma garantia do banco, e não uma esperança da aplicação: é a
coluna `consumed_at` mais o `UPDATE ... WHERE consumed_at IS NULL` do repositório
que decidem, atomicamente, qual de duas redenções simultâneas do mesmo token
vence (ADR 2.5.0002).

**Escrita à mão, como a `0001`, e pela mesma razão:** a migration é um registro
histórico congelado — descreve o schema como ele era neste ponto, e não pode ser
derivada de `tables.py`, que continua evoluindo. A duplicação é deliberada.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMPTZ = TIMESTAMP(timezone=True)

# Congelado no valor de `SetupTokenPurpose` nesta data. Não é importado do enum
# de propósito: uma migration que lesse o código de hoje descreveria o schema de
# hoje, e não o do dia em que foi aplicada.
_PURPOSES = ("invitation", "password_reset")
_PURPOSE_IN_LIST = ", ".join(f"'{purpose}'" for purpose in _PURPOSES)


def upgrade() -> None:
    """Cria `password_setup_tokens`."""
    op.create_table(
        "password_setup_tokens",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        # Só o fingerprint. Não há coluna para o valor do token, de propósito.
        sa.Column("token_fingerprint", sa.Text(), nullable=False),
        sa.Column("issued_at", _TIMESTAMPTZ, nullable=False),
        sa.Column("expires_at", _TIMESTAMPTZ, nullable=False),
        sa.Column("consumed_at", _TIMESTAMPTZ, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_password_setup_tokens"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_setup_tokens_user"),
        sa.UniqueConstraint("token_fingerprint", name="uq_setup_tokens_fingerprint"),
        sa.CheckConstraint(
            f"purpose IN ({_PURPOSE_IN_LIST})", name="ck_setup_tokens_purpose_known"
        ),
    )
    op.create_index("ix_setup_tokens_user_id", "password_setup_tokens", ["user_id"])
    op.create_index("ix_setup_tokens_expires_at", "password_setup_tokens", ["expires_at"])


def downgrade() -> None:
    """Remove `password_setup_tokens`."""
    op.drop_index("ix_setup_tokens_expires_at", table_name="password_setup_tokens")
    op.drop_index("ix_setup_tokens_user_id", table_name="password_setup_tokens")
    op.drop_table("password_setup_tokens")

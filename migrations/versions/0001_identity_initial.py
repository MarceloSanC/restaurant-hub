"""identity initial — tabelas do bounded context identity.

Primeira migration do projeto. Cria as cinco tabelas do BC `identity` com as
constraints que carregam invariante de domínio (ADR 2.3.0002).

**Por que escrita à mão e não por `--autogenerate`:** o scaffold não trazia o
template `script.py.mako`, sem o qual `alembic revision` não gera arquivo nenhum
(corrigido nesta mesma Task, para as Stages seguintes). Independentemente disso, a
migration é um **registro histórico congelado**: ela descreve o schema como ele era
neste ponto da história, e não pode ser derivada de `tables.py`, que continua
evoluindo. Duplicação aqui é deliberada.

Revision ID: 0001
Revises:
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TIMESTAMPTZ = TIMESTAMP(timezone=True)

_ROLES = ("platform_admin", "owner", "manager", "hr", "employee")
_ROLE_IN_LIST = ", ".join(f"'{role}'" for role in _ROLES)


def upgrade() -> None:
    """Cria o schema do BC identity."""
    op.create_table(
        "restaurants",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_restaurants"),
    )

    op.create_table(
        "units",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("restaurant_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_units"),
        sa.ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_units_restaurant"),
        # Âncora obrigatória da FK composta de `unit_memberships`: o Postgres
        # exige índice único cobrindo exatamente as colunas referenciadas.
        sa.UniqueConstraint("id", "restaurant_id", name="uq_units_id_restaurant"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        # NOT NULL é load-bearing: uma CHECK só rejeita em FALSE, então com
        # `role` nulo o predicado do iff abaixo avalia NULL e a linha passaria.
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        # Unicidade GLOBAL de e-mail — sem tenant na chave (kickoff #2).
        sa.UniqueConstraint("email", name="uq_users_email"),
        # O VO `Email` normaliza, mas o Postgres compara byte a byte: sem esta
        # CHECK, `A@X.com` e `a@x.com` coexistiriam e reidratariam no mesmo login.
        sa.CheckConstraint("email = lower(btrim(email))", name="ck_users_email_normalized"),
        sa.CheckConstraint(f"role IN ({_ROLE_IN_LIST})", name="ck_users_role_known"),
        # O iff de tenancy (ADR 2.1.0002).
        sa.CheckConstraint(
            "(role = 'platform_admin') = (tenant_id IS NULL)",
            name="ck_users_tenant_iff_platform_admin",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["restaurants.id"], name="fk_users_tenant"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_users_id_tenant"),
    )

    op.create_table(
        "unit_memberships",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("unit_id", sa.Text(), nullable=False),
        # NOT NULL mantém as FKs compostas ativas: FK composta é MATCH SIMPLE por
        # default e é ignorada por inteiro se qualquer coluna referenciante for
        # nula.
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "unit_id", name="pk_unit_memberships"),
        # As duas juntas tornam vínculo cross-tenant irrepresentável.
        sa.ForeignKeyConstraint(
            ["unit_id", "tenant_id"],
            ["units.id", "units.restaurant_id"],
            name="fk_memberships_unit",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "tenant_id"],
            ["users.id", "users.tenant_id"],
            name="fk_memberships_user",
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        # Só o fingerprint — nunca o valor do refresh token (ADR 2.2.0001).
        sa.Column("refresh_token_fingerprint", sa.Text(), nullable=False),
        sa.Column("issued_at", _TIMESTAMPTZ, nullable=False),
        sa.Column("expires_at", _TIMESTAMPTZ, nullable=False),
        sa.Column("revoked_at", _TIMESTAMPTZ, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("refresh_token_fingerprint", name="uq_sessions_fingerprint"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])


def downgrade() -> None:
    """Remove o schema do BC identity.

    Ordem inversa à criação: quem referencia cai antes de quem é referenciado, ou
    o Postgres recusa o drop por dependência de FK.
    """
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("unit_memberships")
    op.drop_table("users")
    op.drop_table("units")
    op.drop_table("restaurants")

"""identity — a coluna `timezone` em `units` (issue #198, ADR 4.1.0005).

O fuso é atributo da unidade, de identity: chave IANA (`America/Sao_Paulo`,
`America/Manaus`), que scheduling, ponto e hub leem do dono para converter horário
de parede em instante (ADR 4.1.0005 §Decision 1-3).

- **`NOT NULL` com `DEFAULT 'America/Sao_Paulo'`**: o `ADD COLUMN` preenche toda
  unidade que já existe com o default do ADR, e nenhuma fica sem fuso. O default
  fica no banco depois da migration, igual ao do domínio (`Unit.timezone`).
- **Sem `CHECK` de chave**: o conjunto de chaves IANA muda a cada release do
  tzdata; quem o valida é a entidade, contra a base que o processo carrega. Uma
  lista congelada aqui recusaria fuso novo, ou aceitaria um que saiu.

Escrita à mão, como as anteriores: o default está congelado abaixo, não importado
do domínio.

**Numeração:** `0007`, sobre a `0006_scheduling`. Se outra migration nascer em
paralelo sobre a `0006`, quem mergear por último reencadeia o `down_revision`
para o Alembic ter um head só (precedente: a `0006`, concept 4.4 §7 D-MIG).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "units",
        sa.Column(
            "timezone",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'America/Sao_Paulo'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("units", "timezone")

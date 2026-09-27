"""staff — a coluna `user_id` em `employees` (vínculo de login, Stage 3.5).

Quarta migration do projeto. Materializa a única mudança de schema da Stage
3.5 (ADR 3.5.0004): o registro de funcionário passa a poder apontar para um
login em identity. **Uma coluna, nenhuma constraint, nenhum índice** — e cada
ausência é decisão, não esquecimento:

- **Sem FK** para `users`: nenhuma FK atravessa a fronteira entre bounded
  contexts (ADR 3.3.0002) — `user_id` é opaco, como `tenant_id` e `unit_id`.
- **Sem UNIQUE**: `workforce.md` §3.7 admite vários registros apontando para o
  mesmo `User` por vínculos explícitos; uma `UNIQUE` congelaria o contrário.
- **Sem índice**: nenhum acesso por `user_id` nesta Stage; índice acompanha
  acesso medido (ADR 3.3.0005) e entra com `find_by_user_id` no Step 4.
- **Anulável**: login é opcional e explícito por registro (workforce §3.8).

Escrita à mão, como as três anteriores — a migration é registro histórico
congelado, não derivação de `tables.py`.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("user_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "user_id")

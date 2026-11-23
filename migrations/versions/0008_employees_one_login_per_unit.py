"""staff — um login por unidade, imposto pelo banco (issue #241, ADR 0.0.0025).

Cria o índice único parcial `uq_employees_tenant_unit_user` sobre
`employees (tenant_id, unit_id, user_id) WHERE user_id IS NOT NULL`. A regra "um
login por unidade" (ADR 3.10.0001 §6) era checada lendo a unidade antes de gravar,
e dois vínculos concorrentes da mesma conta em dois registros da unidade podiam
passar os dois; com o índice, o segundo espera o primeiro e é recusado.

- **Parcial**: só as linhas vinculadas entram; registro sem login não é limitado.
- **Sem `active` no predicado**: o desligado conta, como na regra.
- **Entre unidades, nada muda**: `workforce.md` §3.7 admite registros do mesmo
  login em unidades diferentes (ADR 3.5.0004 §3, superado só por unidade).

**Dados existentes.** A migration **não** conserta duplicatas: se duas linhas da
mesma unidade carregam o mesmo login, o `CREATE UNIQUE INDEX` falha e a migration
aborta sem aplicar nada (fail-closed). Premissa registrada no ADR 0.0.0025 §5: o
projeto não tem dados de produção, e pela API essas linhas só nasciam pela corrida
que este índice fecha.

Escrita à mão, como as anteriores: o predicado está congelado abaixo, não importado
de `tables.py`.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    return
    op.create_index(
        "uq_employees_tenant_unit_user",
        "employees",
        ["tenant_id", "unit_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_employees_tenant_unit_user", table_name="employees")

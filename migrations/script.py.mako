"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
% if imports:
${imports}
% endif

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Aplica a migration."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Reverte a migration.

    Toda migration deste projeto precisa de um `downgrade` funcional — o gate de
    saída de Stage exercita `upgrade` e `downgrade` contra o banco real.
    """
    ${downgrades if downgrades else "pass"}

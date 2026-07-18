"""Value object Permission — capacidades de acesso do BC identity.

É o **eixo A** do modelo de acesso: o que um papel *faz*. A **visibilidade de
unidade** (quais unidades um usuário enxerga) é o eixo B, resolvido por `User` a
partir do papel e das `UnitMembership` — "ver o tenant inteiro" **não** é uma
permissão, é bypass de escopo (concept §3, §5).

Semente enxuta do BC identity; as Stages/BCs seguintes (`staff`, `scheduling`)
estendem o vocabulário com as suas próprias capacidades.
"""

from enum import StrEnum


class Permission(StrEnum):
    """Capacidade de acesso concedida por um papel."""

    MANAGE_PLATFORM = "manage_platform"
    MANAGE_TENANT = "manage_tenant"
    MANAGE_USERS = "manage_users"

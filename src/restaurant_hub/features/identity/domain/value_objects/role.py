"""Value object Role — papel fixo de acesso (RBAC) e o seu conjunto de permissões.

Conjunto **fechado** de 5 papéis (kickoff #4). Não confundir com **função de
trabalho** (cozinheiro, atendente…), que é 100% customizável por restaurante e
pertence ao BC `staff` (Step 3) — vocabulários distintos (overview §9).

O mapa `Role -> frozenset[Permission]` é fixo e **total**: todo papel tem entrada,
mesmo que vazia (concept §5, regra 6). A totalidade é guardada por teste — papel
novo sem entrada no mapa quebra a suíte em vez de falhar em silêncio.
"""

from enum import StrEnum

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidRoleError
from restaurant_hub.features.identity.domain.value_objects.permission import Permission


class Role(StrEnum):
    """Papel fixo de acesso de um usuário dentro (ou fora) de um tenant."""

    PLATFORM_ADMIN = "platform_admin"
    OWNER = "owner"
    MANAGER = "manager"
    HR = "hr"
    EMPLOYEE = "employee"

    @classmethod
    def from_string(cls, value: str) -> "Role":
        """Converte texto em `Role`, com erro de domínio se o papel for desconhecido."""
        try:
            return cls(value)
        except ValueError as exc:
            raise InvalidRoleError(value) from exc

    @property
    def permissions(self) -> frozenset[Permission]:
        """Conjunto fixo de permissões deste papel."""
        return _ROLE_PERMISSIONS[self]


# Mapa total papel -> permissões. `platform_admin` fica restrito a MANAGE_PLATFORM:
# acesso de plataforma não é acesso de restaurante (concept §5, regra 7).
# `manager` e `hr` coincidem em identity e divergem no eixo de visibilidade.
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.PLATFORM_ADMIN: frozenset({Permission.MANAGE_PLATFORM}),
    Role.OWNER: frozenset({Permission.MANAGE_TENANT, Permission.MANAGE_USERS}),
    Role.MANAGER: frozenset({Permission.MANAGE_USERS}),
    Role.HR: frozenset({Permission.MANAGE_USERS}),
    Role.EMPLOYEE: frozenset(),
}

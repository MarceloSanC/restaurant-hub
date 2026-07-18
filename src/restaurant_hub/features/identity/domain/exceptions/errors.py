"""Exceções de domínio do bounded context identity.

Todas herdam de `IdentityError`, que por sua vez herda de `DomainError`
(`shared/domain`) — o error handler HTTP (Stage 2.4) converte a hierarquia
`DomainError` em resposta 4xx. Aqui garante-se apenas a hierarquia e a mensagem;
nenhuma exceção carrega estado além do texto.
"""

from restaurant_hub.shared.domain.exceptions.base import DomainError


class IdentityError(DomainError):
    """Erro de negócio do bounded context identity."""


class InvalidEmailError(IdentityError):
    """E-mail com formato inválido (ver `Email`)."""

    def __init__(self, value: str) -> None:
        super().__init__(f"e-mail inválido: {value!r}")


class InvalidRoleError(IdentityError):
    """Papel desconhecido — fora do conjunto fechado de `Role`."""

    def __init__(self, value: str) -> None:
        super().__init__(f"papel inválido: {value!r}")


class MissingTenantError(IdentityError):
    """Usuário de papel de restaurante criado sem `tenant_id` (invariante 1)."""

    def __init__(self, role: str) -> None:
        super().__init__(f"usuário de papel {role!r} exige tenant_id")


class PlatformAdminTenantError(IdentityError):
    """`platform_admin` não pertence a tenant algum (invariante 2, ADR 2.1.0002)."""

    def __init__(self) -> None:
        super().__init__("platform_admin não pode pertencer a um tenant")


class PlatformAdminMembershipError(IdentityError):
    """`platform_admin` não é escopado por unidade — não recebe vínculo."""

    def __init__(self) -> None:
        super().__init__("platform_admin não pode ser vinculado a uma unidade")


class CrossTenantError(IdentityError):
    """Tentativa de vincular recursos de tenants distintos (invariante 3)."""

    def __init__(self, user_tenant: str | None, unit_tenant: str) -> None:
        super().__init__(
            f"isolamento de tenant violado: usuário do tenant {user_tenant!r} "
            f"e unidade do tenant {unit_tenant!r}"
        )

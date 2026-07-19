"""Erros da camada de aplicação do BC identity.

Todos herdam de `IdentityError` (domínio, Stage 2.1) e, por consequência, de
`DomainError` — **nunca** de `ApplicationError`, que não tem handler HTTP
registrado e viraria 500 (ADR 2.2.0003). O pior caso não-ajustado é 422; a Stage
2.4 refina para 401/403/404 registrando handlers, sem tocar nesta camada.

Os três erros de "não encontrado" herdam também de `NotFoundError`, **nesta
ordem**: a MRO fica `… -> IdentityError -> NotFoundError -> DomainError`, e o
lookup de handler do Starlette (que percorre `type(exc).__mro__`) alcança o
handler 404 antes do 422.

Erros de invariante do domínio (`CrossTenantError`, `PlatformAdminMembershipError`
etc.) **não** são reembrulhados: sobem como estão, com a mesma raiz `IdentityError`.
"""

from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError
from restaurant_hub.shared.domain.exceptions.base import NotFoundError


class EmailAlreadyRegisteredError(IdentityError):
    """E-mail já usado por outro usuário.

    A unicidade é **global**, não escopada por tenant (decisão de kickoff #2):
    o mesmo e-mail não pode existir em dois restaurantes diferentes.
    """

    def __init__(self, email: str) -> None:
        super().__init__(f"e-mail já registrado: {email!r}")


class InvalidCredentialsError(IdentityError):
    """Credencial inválida — e-mail inexistente **ou** senha incorreta.

    A mensagem é deliberadamente idêntica nos dois casos, e não cita o e-mail
    tentado: distinguir os cenários entregaria um oráculo de enumeração de contas
    (concept §5.14).
    """

    def __init__(self) -> None:
        super().__init__("credenciais inválidas")


class PermissionDeniedError(IdentityError):
    """Eixo RBAC: o papel do ator não concede a permissão exigida."""

    def __init__(self, role: str, permission: str) -> None:
        super().__init__(f"papel {role!r} não concede a permissão {permission!r}")


class TenantScopeRequiredError(IdentityError):
    """O ator pertence a um tenant e não declarou o tenant alvo da ação.

    Exigir a declaração é o que impede que omitir o parâmetro vire caminho de
    escalada — a checagem de tenant não pode ser opcional (ADR 2.2.0002).
    """

    def __init__(self, role: str) -> None:
        super().__init__(f"ação de papel {role!r} exige declarar o tenant alvo")


class TenantNotVisibleError(IdentityError):
    """O ator agiu sobre um tenant que não é o seu, ou com alvo incoerente."""

    def __init__(self, actor_tenant: str | None, target_tenant: str) -> None:
        super().__init__(
            f"isolamento de tenant violado: ator do tenant {actor_tenant!r} "
            f"e alvo no tenant {target_tenant!r}"
        )


class UnitScopeRequiredError(IdentityError):
    """Ator escopado por unidade não declarou a unidade alvo.

    Papéis sem bypass de escopo (`manager`, `hr`, `employee`) não têm autoridade
    tenant-wide: omitir a unidade é negado, não promovido.
    """

    def __init__(self, role: str) -> None:
        super().__init__(f"ação de papel {role!r} exige declarar a unidade alvo")


class UnitNotVisibleError(IdentityError):
    """Eixo de visibilidade: o ator não enxerga a unidade alvo."""

    def __init__(self, user_id: str, unit_id: str) -> None:
        super().__init__(f"usuário {user_id!r} não enxerga a unidade {unit_id!r}")


class RestaurantNotFoundError(IdentityError, NotFoundError):
    """Restaurante inexistente."""

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(f"restaurante não encontrado: {restaurant_id!r}")


class UnitNotFoundError(IdentityError, NotFoundError):
    """Unidade inexistente."""

    def __init__(self, unit_id: str) -> None:
        super().__init__(f"unidade não encontrada: {unit_id!r}")


class UserNotFoundError(IdentityError, NotFoundError):
    """Usuário inexistente."""

    def __init__(self, user_id: str) -> None:
        super().__init__(f"usuário não encontrado: {user_id!r}")

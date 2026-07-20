"""Commands — a entrada de cada use case do BC identity.

São DTOs `frozen`: o use case recebe dado, não entidade. Value objects imutáveis
do domínio (`Email`, `Role`, `Permission`) trafegam aqui por licença explícita do
LAYOUT §7 — são valores puros, indistinguíveis de primitivos para o consumidor.
Entidades, não.

A conversão de texto cru para VO (`Role.from_string`, `Email(...)`) é do adapter
que recebe a requisição (Stage 2.4): quando ela falha, o erro já é de domínio e
vira 4xx, em vez de estourar dentro do use case.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role


@dataclass(frozen=True)
class CreateRestaurantCommand:
    """Criação de um restaurante — que é, ele próprio, o tenant."""

    name: str


@dataclass(frozen=True)
class CreateUnitCommand:
    """Criação de uma unidade sob um restaurante existente."""

    restaurant_id: RestaurantId
    name: str


@dataclass(frozen=True)
class CreateUserCommand:
    """Criação de uma conta de acesso.

    Attributes:
        email: e-mail de login; a unicidade é global, não por tenant.
        plain_password: senha em claro — só atravessa o `PasswordHasher`, nunca
            é persistida nem devolvida.
        role: papel fixo de acesso.
        tenant_id: restaurante do usuário; `None` apenas para `platform_admin`.
        unit_ids: unidades a que o usuário fica vinculado (visibilidade).
            Duplicatas são deduplicadas pelo use case.
    """

    email: Email
    plain_password: str
    role: Role
    tenant_id: RestaurantId | None
    unit_ids: Sequence[UnitId] = ()


@dataclass(frozen=True)
class AuthenticateUserCommand:
    """Tentativa de login por e-mail e senha."""

    email: Email
    plain_password: str


@dataclass(frozen=True)
class RefreshSessionCommand:
    """Pedido de rotação: troca um refresh token por um par novo.

    Carrega o **valor** do token, não o fingerprint: derivá-lo é papel do
    `TokenIssuer`, e exigir que o chamador o derivasse espalharia criptografia
    para fora do port.
    """

    refresh_token: str


@dataclass(frozen=True)
class RevokeSessionCommand:
    """Logout: revoga a sessão do refresh token apresentado.

    A autoridade da operação é a **posse** do token — não exige access token.
    """

    refresh_token: str


@dataclass(frozen=True)
class AuthorizeActionCommand:
    """Pedido de autorização de uma ação.

    `tenant_id` e `unit_id` descrevem o **alvo** da ação, não o ator. Ambos são
    opcionais no tipo, mas não na regra: o use case exige `tenant_id` de quem
    pertence a um tenant, e `unit_id` de quem é escopado por unidade — omitir não
    é caminho de escalada (concept §5.6).
    """

    actor_id: UserId
    permission: Permission
    tenant_id: RestaurantId | None = None
    unit_id: UnitId | None = None

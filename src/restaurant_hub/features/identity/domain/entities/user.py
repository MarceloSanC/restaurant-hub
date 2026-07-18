"""Entidade User — conta de acesso, raiz de agregado.

Amarra os **dois eixos de acesso** (concept §3, §5), que são ortogonais:

- **RBAC** — o papel fixo define o conjunto de permissões (`has_permission`).
- **Visibilidade de unidade** — `owner` e `platform_admin` ignoram o vínculo e
  enxergam todo o seu escopo; `manager`/`hr`/`employee` só enxergam as unidades a
  que estão vinculados por `UnitMembership`.

Invariante de tenancy (ADR 2.1.0002): `tenant_id` é `None` **se e somente se** o
papel for `platform_admin` — acesso de plataforma vive fora de qualquer tenant.

A entidade é **imutável** (`frozen`): a invariante vale para o `User`, não só para
o instante da construção. Sem isso, `user.role = PLATFORM_ADMIN` levaria a entidade
a um estado inválido e furaria o isolamento — e a reidratação por mapper (Stage 2.3)
seria exatamente esse caminho. Mudança de estado se faz por `dataclasses.replace`,
que reexecuta `__post_init__` e revalida.

Igualdade por **identidade**.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.exceptions.errors import (
    CrossTenantError,
    MissingTenantError,
    PlatformAdminMembershipError,
    PlatformAdminTenantError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)

# Papéis que enxergam todo o seu escopo, ignorando o vínculo por unidade.
_UNIT_SCOPE_BYPASS_ROLES = frozenset({Role.OWNER, Role.PLATFORM_ADMIN})


@dataclass(frozen=True, eq=False)
class User:
    """Conta de acesso de uma pessoa.

    Attributes:
        id: identidade do usuário.
        email: e-mail de login (a unicidade global é garantida na persistência, 2.3).
        role: papel fixo de acesso.
        tenant_id: restaurante a que pertence; `None` apenas para `platform_admin`.
    """

    id: UserId
    email: Email
    role: Role
    tenant_id: RestaurantId | None

    def __post_init__(self) -> None:
        if self.role is Role.PLATFORM_ADMIN and self.tenant_id is not None:
            raise PlatformAdminTenantError()
        if self.role is not Role.PLATFORM_ADMIN and self.tenant_id is None:
            raise MissingTenantError(self.role.value)

    def has_permission(self, permission: Permission) -> bool:
        """True se o papel do usuário concede a permissão."""
        return permission in self.role.permissions

    def bypasses_unit_scope(self) -> bool:
        """True para os papéis que ignoram o vínculo por unidade."""
        return self.role in _UNIT_SCOPE_BYPASS_ROLES

    def link_to_unit(self, unit: Unit) -> UnitMembership:
        """Cria o vínculo com uma unidade, impondo o isolamento de tenant.

        Raises:
            PlatformAdminMembershipError: `platform_admin` não é escopado por unidade.
            CrossTenantError: a unidade pertence a outro tenant.
        """
        if self.role is Role.PLATFORM_ADMIN:
            raise PlatformAdminMembershipError()
        if self.tenant_id != unit.tenant_id:
            raise CrossTenantError(self.tenant_id, unit.tenant_id)
        return UnitMembership(user_id=self.id, unit_id=unit.id)

    def can_view_unit(self, unit: Unit, memberships: Iterable[UnitMembership]) -> bool:
        """True se o usuário enxerga a unidade, dados os seus vínculos.

        A **ordem** das checagens é parte da invariante: o `platform_admin` é
        resolvido antes de qualquer comparação de tenant, porque não tem
        `tenant_id`. O vínculo precisa casar usuário **e** unidade — vínculo de
        outro usuário não concede visibilidade.
        """
        if self.role is Role.PLATFORM_ADMIN:
            return True
        if self.tenant_id != unit.tenant_id:
            return False
        if self.bypasses_unit_scope():
            return True
        return any(
            membership.user_id == self.id and membership.unit_id == unit.id
            for membership in memberships
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

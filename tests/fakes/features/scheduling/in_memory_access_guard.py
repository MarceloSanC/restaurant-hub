"""Fake in-memory do `AccessGuard` de scheduling — a segunda implementação das leis.

Lei que só a implementação de produção cumpre não é lei, é descrição (ADR 3.4.0001
Implementation notes). Este fake obedece L-SG1…L-SG4 e a suíte
`tests/unit/features/scheduling/application/test_access_guard_laws.py` o prova.

- **Sentinela por identidade** (L-SG1): o fake levanta exatamente a instância
  `authorization_error`, e os testes assertam `excinfo.value is guard.authorization_error`.
- **Concessão por tripla exata** `(permission, tenant_id, unit_id)` (L-SG3).
- **Ator emitido por este guard** (`issue`): ator forjado, `None` ou de outro guard é
  negado; ator sem tenant ou sem sujeito também (L-SG2, L-SG4).
- **`calls` com o alvo**, para "uma chamada por alvo" e "nada antes da decisão".
"""

from dataclasses import dataclass, field

from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)


class FakeAuthorizationRejected(Exception):
    """Sentinela de recusa — tipo **do fake**, não de identity (L-SG1)."""


@dataclass(frozen=True)
class FakeActor:
    """Credencial verificada, na forma mínima que as leis exigem.

    Attributes:
        user_id: o sujeito autenticado (L-SG4). Vazio reproduz um token defeituoso.
        tenant_id: o restaurante do ator; `None` reproduz o `platform_admin`.
    """

    user_id: str
    tenant_id: str | None


@dataclass
class InMemoryAccessGuard:
    """Guard configurável: atores emitidos, concessões e registro de chamadas."""

    grants: set[tuple[str, str, str]] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)
    authorization_error: Exception = field(default_factory=FakeAuthorizationRejected)
    _issued: list[FakeActor] = field(default_factory=list)

    def issue(self, user_id: str, tenant_id: str | None) -> FakeActor:
        """Emite um ator — o equivalente, no fake, a autenticar um token."""
        ator = FakeActor(user_id=user_id, tenant_id=tenant_id)
        self._issued.append(ator)
        return ator

    def grant(self, permission: str, *, tenant_id: str, unit_id: str) -> None:
        """Concede **um** alvo."""
        self.grants.add((permission, tenant_id, unit_id))

    def authorize(
        self,
        actor: object,
        permission: str,
        *,
        tenant_id: str,
        unit_id: str,
    ) -> AuthorizedScope:
        """Autoriza este alvo exato, ou levanta a sentinela crua."""
        self.calls.append(f"authorize({permission},{tenant_id},{unit_id})")
        if not isinstance(actor, FakeActor) or not any(actor is a for a in self._issued):
            raise self.authorization_error
        # L-SG2/L-SG4 antes da concessão: ator sem tenant ou sem sujeito é negado
        # mesmo com o alvo concedido.
        if not actor.tenant_id or not actor.user_id.strip():
            raise self.authorization_error
        if actor.tenant_id != tenant_id:
            raise self.authorization_error
        if (permission, tenant_id, unit_id) not in self.grants:
            raise self.authorization_error
        return AuthorizedScope(
            tenant_id=TenantId(tenant_id), unit_id=UnitId(unit_id), user_id=actor.user_id
        )


_conforms: AccessGuard = InMemoryAccessGuard()

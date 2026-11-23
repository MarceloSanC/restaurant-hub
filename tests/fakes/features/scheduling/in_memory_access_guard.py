"""Fake in-memory do `AccessGuard` de scheduling — a segunda implementação das leis.

Lei que só a implementação de produção cumpre não é lei, é descrição (ADR 3.4.0001
Implementation notes). Este fake obedece L-SG1…L-SG5 e a suíte
`tests/unit/features/scheduling/application/test_access_guard_laws.py` o prova.

- **Sentinelas por identidade** (L-SG1): o fake levanta exatamente a instância
  `authorization_error` (ou `authentication_error`), e os testes assertam
  `excinfo.value is guard.authorization_error`.
- **Concessão por tripla exata** `(permission, tenant_id, unit_id)` (L-SG3).
- **Ator emitido por este guard** (`issue`): ator forjado, `None` ou de outro guard é
  negado; ator sem tenant ou sem sujeito também (L-SG2, L-SG4, L-SG5).
- **`authenticate`** lê o cabeçalho `authorization: Bearer <user_id>` de um objeto com
  `headers` (o `Request` do Starlette) ou de um `Mapping`, e devolve o ator emitido com
  esse sujeito; sem cabeçalho, ou sujeito que o guard não emitiu, levanta a sentinela de
  autenticação. É o que a borda HTTP usa nos testes sem identity.
- **`calls` com o alvo**, para "uma chamada por alvo" e "nada antes da decisão".
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)

_BEARER = "Bearer "


class FakeAuthorizationRejected(Exception):
    """Sentinela de recusa — tipo **do fake**, não de identity (L-SG1)."""


class FakeAuthenticationRejected(Exception):
    """Sentinela de credencial inválida — tipo **do fake** (L-SG1)."""


@dataclass(frozen=True)
class FakeActor:
    """Credencial verificada, na forma mínima que as leis exigem.

    Attributes:
        user_id: o sujeito autenticado (L-SG4). Vazio reproduz um token defeituoso.
        tenant_id: o restaurante do ator; `None` reproduz o `platform_admin`.
    """

    user_id: str
    tenant_id: str | None


def _header(request: object) -> str | None:
    headers = getattr(request, "headers", request)
    if not isinstance(headers, Mapping):
        return None
    value = headers.get("authorization")
    return value if isinstance(value, str) else None


@dataclass
class InMemoryAccessGuard:
    """Guard configurável: atores emitidos, concessões e registro de chamadas."""

    grants: set[tuple[str, str, str]] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)
    authorization_error: Exception = field(default_factory=FakeAuthorizationRejected)
    authentication_error: Exception = field(default_factory=FakeAuthenticationRejected)
    _issued: list[FakeActor] = field(default_factory=list)

    def issue(self, user_id: str, tenant_id: str | None) -> FakeActor:
        """Emite um ator — o equivalente, no fake, a autenticar um token."""
        ator = FakeActor(user_id=user_id, tenant_id=tenant_id)
        self._issued.append(ator)
        return ator

    def grant(self, permission: str, *, tenant_id: str, unit_id: str) -> None:
        """Concede **um** alvo."""
        self.grants.add((permission, tenant_id, unit_id))

    def authenticate(self, request: object) -> FakeActor:
        """O ator emitido cujo sujeito o cabeçalho nomeia, ou a sentinela crua."""
        self.calls.append("authenticate")
        header = _header(request)
        if header is None or not header.startswith(_BEARER):
            raise self.authentication_error
        subject = header.removeprefix(_BEARER)
        for ator in self._issued:
            if ator.user_id == subject:
                return ator
        raise self.authentication_error

    def authorize(
        self,
        actor: object,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str,
    ) -> AuthorizedScope:
        """Autoriza este alvo exato, ou levanta a sentinela crua."""
        self.calls.append(f"authorize({permission},{tenant_id},{unit_id})")
        if not isinstance(actor, FakeActor) or not any(actor is a for a in self._issued):
            raise self.authorization_error
        # L-SG2/L-SG4/L-SG5 antes da concessão: ator sem tenant ou sem sujeito é negado
        # mesmo com o alvo concedido — e com o tenant omitido também.
        if not actor.tenant_id or not actor.user_id.strip():
            raise self.authorization_error
        target_tenant = actor.tenant_id if tenant_id is None else tenant_id
        # L-SG2 — alvo vazio nunca é concedido (nada de escopo com `""`).
        if not target_tenant.strip() or not unit_id.strip():
            raise self.authorization_error
        if actor.tenant_id != target_tenant:
            raise self.authorization_error
        if (permission, target_tenant, unit_id) not in self.grants:
            raise self.authorization_error
        return AuthorizedScope(
            tenant_id=TenantId(target_tenant), unit_id=UnitId(unit_id), user_id=actor.user_id
        )


_conforms: AccessGuard = InMemoryAccessGuard()

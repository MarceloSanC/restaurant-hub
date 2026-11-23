"""Adapter de saída: o `AccessGuard` de scheduling sobre a fachada de acesso de identity.

A forma do adapter de staff (issue #47, ADR 0.0.0016) reaplicada a scheduling (ADR
4.5.0003): importa **um** módulo de identity, `identity.application.facade`, pelo par
nomeado no contrato `bc-independence`.

**As duas metades vêm por caminhos diferentes:**

- **Autenticar** é do adapter de entrada de identity (extrair o Bearer, verificar, anotar o
  ator para o log), numa cópia só: este adapter recebe por construtor o chamável
  `IdentityGuard.authenticate_principal`, ligado pelo `composition_root`, e o repassa.
- **Autorizar** passa pela fachada de acesso, em primitivos, com os dois oráculos de
  identity já fechados do lado de lá.

**O que este módulo decide, e é por isso que ele existe** (as leis do port):

- **L-SG1 — sem `try/except`.** Toda exceção de identity sobe **crua**: a faixa 401/403
  de scheduling fica byte-idêntica à de identity.
- **L-SG5 — tenant omitido é o do ator.** A borda HTTP não conhece o tenant (ADR
  0.0.0005, cláusula 3): só a implementação que produziu o ator o lê. Só a **ausência**
  (`None`) é resolvida; um `""` explícito segue como alvo e é negado por identity.
- **L-SG2/L-SG5 — ator sem tenant é negado aqui**, e não delegado à matriz de papéis, com a
  `PermissionDeniedError` de identity (a mesma faixa 403 de corpo constante).
- **L-SG4 — o sujeito é o do token** (`AccessPrincipal.user_id`), que identity reconsulta.
"""

from collections.abc import Callable

from restaurant_hub.features.identity.application.facade import (
    AccessPrincipal,
    IdentityAccessFacade,
    PermissionDeniedError,
)
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    Actor,
    AuthorizedScope,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)


class LocalAccessGuard:
    """Implementação in-process do `AccessGuard` de scheduling, sobre a fachada de acesso."""

    def __init__(
        self,
        access: IdentityAccessFacade,
        authenticate_request: Callable[[object], AccessPrincipal],
    ) -> None:
        self._access = access
        self._authenticate_request = authenticate_request

    def authenticate(self, request: object) -> Actor:
        """L-SG1 — repassa e não captura; o ator é o `AccessPrincipal` de identity."""
        return self._authenticate_request(request)

    def authorize(
        self,
        actor: Actor,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str,
    ) -> AuthorizedScope:
        """Resolve o tenant omitido, delega a decisão e nega o ator sem tenant na volta.

        Raises:
            TypeError: `actor` não veio de `authenticate` deste guard — defeito de wiring,
                não decisão de acesso; mascará-lo como 403 esconderia a borda quebrada.
            PermissionDeniedError: ator autorizado sem tenant (L-SG2/L-SG5).
            Exception: qualquer outra exceção de identity, sem tradução (L-SG1).
        """
        if not isinstance(actor, AccessPrincipal):
            msg = f"ator não autenticado por este guard: {type(actor).__name__}"
            raise TypeError(msg)

        target_tenant_id = tenant_id if tenant_id is not None else actor.tenant_id

        grant = self._access.authorize(
            actor, permission, tenant_id=target_tenant_id, unit_id=unit_id
        )

        actor_tenant_id = grant.actor_tenant_id
        if not actor_tenant_id or not target_tenant_id:
            # A exceção de identity, e não uma nova de scheduling: "este ator não pode agir
            # sobre este alvo", com a mesma faixa 403 de corpo constante (L-SG1).
            raise PermissionDeniedError(grant.role, permission)

        return AuthorizedScope(
            tenant_id=TenantId(target_tenant_id),
            unit_id=UnitId(unit_id),
            user_id=actor.user_id,
        )

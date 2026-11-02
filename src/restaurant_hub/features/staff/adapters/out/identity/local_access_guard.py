"""Adapter de saída: `AccessGuard` implementado sobre a fachada de acesso de identity.

**O tradutor de acesso de staff, fora do `composition_root`** (issue #47, ADR
0.0.0016). Até aqui ele morava no composition root como `_IdentityAccessGuard`,
embrulhando o `IdentityGuard` do adapter HTTP de identity num `Any` — o único
arquivo com uma decisão de isolamento de tenant (L-AG3) que nenhum gate de
import inspecionava. Agora ele é um adapter de staff como o
`LocalIdentityGateway` ao lado, e herda a mesma permissão — e só ela — do par
nomeado no contrato `bc-independence`: importa **um** módulo de identity,
`identity.application.facade`.

**As duas metades vêm por caminhos diferentes, e a assimetria é medida:**

- **Autenticar** é ler um header HTTP, verificar o Bearer e anotar o ator para
  o log (#26). Tudo isso é do adapter de entrada de identity, e ali continua,
  numa cópia só: este adapter recebe por construtor um **chamável** que devolve
  o `AccessPrincipal` da fachada (`IdentityGuard.authenticate_principal`, ligado
  pelo `composition_root`). Nenhum import, nenhum `Any`: o tipo que atravessa é o
  publicado pela fachada.
- **Autorizar** passa pela fachada de acesso (`IdentityAccessFacade`), em
  primitivos, com os dois oráculos de identity já fechados do lado de lá.

**O que este módulo decide, e é por isso que ele existe** (ADR 3.4.0001 §2):

- **L-AG1/L-AG2 — sem `try/except`.** Toda exceção de identity sobe **crua**,
  e é isso que mantém a faixa 401/403 de staff byte-idêntica à de identity.
- **ADR 0.0.0005, cláusula 3 — `tenant_id` omitido é o tenant do ator.** A
  camada confiável única que resolve o tenant segue a opacidade do ator: o port
  declara `Actor = object`, e este é o único módulo de staff que **conhece** o
  ator, porque foi ele que o devolveu. A leitura é tipada, sem `getattr`.
- **L-AG3 — ator sem tenant é negado aqui**, e não delegado à matriz de papéis:
  confiar em *"`platform_admin` é negado antes, no passo 2"* faria o isolamento
  de tenant refém do mapa RBAC, que é editável.

**O `ValueError` de uma permissão desconhecida é o preço declarado do `str`**
(ADR 3.4.0001 §Trade-offs) e não é traduzido: nome de permissão inválido é
defeito de programação da borda, não decisão de acesso.
"""

from collections.abc import Callable

from restaurant_hub.features.identity.application.facade import (
    AccessPrincipal,
    IdentityAccessFacade,
    PermissionDeniedError,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    Actor,
    AuthorizedScope,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)


class LocalAccessGuard:
    """Implementação in-process do `AccessGuard`, sobre a fachada de acesso."""

    def __init__(
        self,
        access: IdentityAccessFacade,
        authenticate_request: Callable[[object], AccessPrincipal],
    ) -> None:
        self._access = access
        self._authenticate_request = authenticate_request

    def authenticate(self, request: object) -> Actor:
        """L-AG1 — repassa e não captura; o ator é o `AccessPrincipal` de identity."""
        return self._authenticate_request(request)

    def authorize(
        self,
        actor: Actor,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> AuthorizedScope:
        """Resolve o tenant omitido, delega a decisão e impõe L-AG3 na volta.

        **A resolução acontece ANTES de delegar, e L-AG3 continua DEPOIS.** O que
        se resolve aqui é o alvo que identity recebe; resolver depois seria
        resolver um valor que a decisão de acesso já não usa. E a guarda de L-AG3
        é sobre o `actor_tenant_id` que **identity** devolve, lido do banco.

        Raises:
            TypeError: `actor` não veio de `authenticate` deste guard — defeito
                de wiring, não decisão de acesso; mascará-lo como 403 esconderia
                a borda quebrada atrás de uma negação plausível.
            PermissionDeniedError: ator autorizado sem tenant (L-AG3).
            Exception: qualquer outra exceção de identity, sem tradução (L-AG2).
        """
        if not isinstance(actor, AccessPrincipal):
            msg = f"ator não autenticado por este guard: {type(actor).__name__}"
            raise TypeError(msg)

        # Só a **ausência** carrega significado. Um `tenant_id=""` explícito é o
        # chamador nomeando um tenant vazio, e segue para a decisão de acesso
        # como qualquer outro alvo — que o negará. Trocar por truthiness aqui
        # reescreveria o pedido em silêncio (ADR 2.3.0005).
        target_tenant_id = tenant_id if tenant_id is not None else actor.tenant_id

        grant = self._access.authorize(
            actor, permission, tenant_id=target_tenant_id, unit_id=unit_id
        )

        actor_tenant_id = grant.actor_tenant_id
        if not actor_tenant_id:
            # `PermissionDeniedError` de identity, e não uma exceção nova de
            # staff: o caminho é, semanticamente, "este ator não pode agir sobre
            # este alvo", e uma exceção nova produziria uma faixa de erro
            # distinta para ele, contra o corpo constante que L-AG2 protege.
            raise PermissionDeniedError(grant.role, permission)

        scope_unit_id = grant.scope_unit_id
        return AuthorizedScope(
            tenant_id=TenantId(actor_tenant_id),
            unit_id=UnitId(scope_unit_id) if scope_unit_id is not None else None,
        )

"""Results — a saída de cada use case do BC identity.

Regra dura (CLAUDE.md §6, LAYOUT §7): use case devolve DTO, **nunca** entidade.
Por isso `UserResult` carrega campos, não um `User`.

Regra de segurança (concept §5.9): nenhum result carrega senha em claro nem
`PasswordHash`. Os segredos que saem daqui são o `refresh_token`, que é para o
cliente e — por definição — nunca é persistido (concept §5.11), e o `setup_link`
de `ProvisionedAccountResult`, carve-out **único** e declarado (ADR 3.5.0002).
"""

from dataclasses import dataclass, field
from datetime import datetime

from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role


@dataclass(frozen=True)
class RestaurantResult:
    """Restaurante criado."""

    id: RestaurantId
    name: str


@dataclass(frozen=True)
class UnitResult:
    """Unidade criada."""

    id: UnitId
    restaurant_id: RestaurantId
    name: str


@dataclass(frozen=True)
class UserResult:
    """Usuário criado, com os vínculos de unidade efetivamente gravados."""

    id: UserId
    email: Email
    role: Role
    tenant_id: RestaurantId | None
    unit_ids: tuple[UnitId, ...]


@dataclass(frozen=True)
class ProvisionedAccountResult:
    """Conta pendente provisionada **e** o link que a ativa (Stage 3.5).

    É o único result de identity que carrega o valor de um token de setup — o
    carve-out da regra 1 da 2.5 está no ADR 3.5.0002 §Status. Existe porque quem
    provisiona (o gateway de staff) ainda vai decidir o canal: e-mail ou em mãos.

    `repr=False` em `setup_link` pelo mesmo motivo de `AuthenticationResult`
    não imprimir o refresh token: o result atravessa a fachada e o gateway e
    fica nos locals de qualquer frame que falhe depois dele.
    """

    user: UserResult
    setup_link: str = field(repr=False)


@dataclass(frozen=True)
class AuthenticationResult:
    """Par de tokens emitido por um login bem-sucedido.

    `refresh_token` é o valor opaco entregue ao cliente; o que a sessão persiste é
    apenas o seu fingerprint (ADR 2.2.0001).
    """

    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    user_id: UserId


@dataclass(frozen=True)
class AuthorizedActor:
    """Ator autorizado **e** o escopo que acabou de ser validado.

    `actor_tenant_id` é o tenant do próprio ator (`None` para `platform_admin`);
    `scope_tenant_id`/`scope_unit_id` são o alvo aprovado. Devolver o escopo evita
    que o adapter (2.4) tenha de re-derivar o alvo do request — o que reintroduziria
    no adapter a decisão que este use case existe para tomar.
    """

    user_id: UserId
    role: Role
    actor_tenant_id: RestaurantId | None
    scope_tenant_id: RestaurantId | None
    scope_unit_id: UnitId | None

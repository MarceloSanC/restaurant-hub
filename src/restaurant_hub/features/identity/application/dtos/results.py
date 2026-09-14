"""Results — a saída de cada use case do BC identity.

Regra dura (CLAUDE.md §6, LAYOUT §7): use case devolve DTO, **nunca** entidade.
Por isso `UserResult` carrega campos, não um `User`.

Regra de segurança (concept §5.9): nenhum result carrega senha em claro nem
`PasswordHash`. O único segredo que sai daqui é o `refresh_token`, que é para o
cliente e — por definição — nunca é persistido (concept §5.11).

**Cada result é construído num sítio só, e o sítio mora aqui** (issue #45,
Gate 8). `UserResult` era montado em `create_user` e `invite_user`;
`AuthenticationResult`, em `authenticate_user` e `refresh_session`. Dois sítios
já bastam para a falha que a regra fecha: acrescentar um campo ao result e
lembrar de um só dos dois compila, passa mypy quando o campo tem default, e
produz duas respostas diferentes para o mesmo recurso — a de login e a de
refresh, que os clientes tratam como intercambiáveis. A regra é mecânica
(`scripts/check_layout.py`, regra 8).

**`to_authentication_result` recebe o `IssuedRefreshToken`, não a `str`.** É o
que dá trabalho à função em vez de fazê-la um repasse: ela é o único ponto que
escolhe `.value` (o segredo que vai ao cliente) e nunca `.fingerprint` (o que
fica no banco). Aceitar a `str` já extraída devolveria essa escolha aos dois
chamadores, que é exatamente onde ela não deve morar.
"""

from dataclasses import dataclass
from datetime import datetime

from restaurant_hub.features.identity.application.dtos.tokens import IssuedRefreshToken
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)


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


def to_user_result(user: User, memberships: tuple[UnitMembership, ...]) -> UserResult:
    """O único sítio de construção de `UserResult` (Gate 8, issue #45).

    Recebe os vínculos **efetivamente gravados**, e não os pedidos: é o que o
    docstring da classe promete, e a ordem em que eles chegam é observável na
    resposta (`_link_units` deduplica preservando-a).
    """
    return UserResult(
        id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
        unit_ids=tuple(membership.unit_id for membership in memberships),
    )


def to_authentication_result(
    *,
    access_token: str,
    issued_refresh: IssuedRefreshToken,
    access_token_expires_at: datetime,
    refresh_token_expires_at: datetime,
    user_id: UserId,
) -> AuthenticationResult:
    """O único sítio de construção de `AuthenticationResult` (Gate 8, issue #45).

    Só argumentos nomeados: os dois `datetime` e os dois valores de token são
    intercambiáveis por posição e trocá-los não é erro de tipo — seria um par de
    tokens com as expirações invertidas, servido com status 200.
    """
    return AuthenticationResult(
        access_token=access_token,
        refresh_token=issued_refresh.value,
        access_token_expires_at=access_token_expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
        user_id=user_id,
    )

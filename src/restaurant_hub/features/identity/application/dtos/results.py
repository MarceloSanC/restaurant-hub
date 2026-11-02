"""Results — a saída de cada use case do BC identity.

Regra dura (CLAUDE.md §6, LAYOUT §7): use case devolve DTO, **nunca** entidade.
Por isso `UserResult` carrega campos, não um `User`.

Regra de segurança (concept §5.9): nenhum result carrega senha em claro nem
`PasswordHash`. Os segredos que saem daqui são o `refresh_token`, que é para o
cliente e — por definição — nunca é persistido (concept §5.11), e o `setup_link`
de `ProvisionedAccountResult`, carve-out **único** e declarado (ADR 3.5.0002).

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

`ProvisionedAccountResult` (Stage 3.5) é construído em `provision_account.py`, e o
`UserResult` que ele embrulha vem de `to_user_result` — a regra 8 vale para ele
como para os outros, contado pelo sítio da classe.
"""

from dataclasses import dataclass, field
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
class ProvisionedAccountResult:
    """Conta pendente provisionada **e** o link que a ativa (Stage 3.5).

    É o único result de identity que carrega o valor de um token de setup — o
    carve-out da regra 1 da 2.5 está no ADR 3.5.0002 §Status. Existe porque quem
    provisiona (o gateway de staff) ainda vai decidir o canal: e-mail ou em mãos.

    `repr=False` em `setup_link` pelo mesmo motivo de
    `RefreshSessionCommand.refresh_token`: o result atravessa a fachada e o
    gateway e fica nos locals de qualquer frame que falhe depois dele.
    (`AuthenticationResult.refresh_token` **não** tem `repr=False` — finding
    herdado da 2.2, registrado na Stage 3.5; fora da lista fechada de §5.13.)
    """

    user: UserResult
    setup_link: str = field(repr=False)


@dataclass(frozen=True)
class ProvisionedRestaurantResult:
    """Restaurante provisionado **com** o seu primeiro `owner` (ADR 0.0.0013).

    Os campos do restaurante vão planos, e não num `RestaurantResult` aninhado:
    o restaurante e o dono nascem juntos, numa unidade, e o result descreve essa
    única operação. O `UserResult` do dono vem de `to_user_result`, como em todo
    result que carrega usuário (regra 8).
    """

    id: RestaurantId
    name: str
    owner: UserResult


@dataclass(frozen=True)
class AccountRoleResult:
    """O papel de uma conta existente (Stage 3.8, ADR 3.8.0001 §3).

    Carrega o `Role` — como `UserResult` e `AuthorizedActor` —, não o valor em
    texto: a conversão para primitivo é da fachada, que é quem fala com outro
    bounded context.
    """

    role: Role


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

"""Mapeamento domínio↔linha do BC identity.

Funções puras: recebem linha, devolvem entidade; recebem entidade, devolvem
`dict` de colunas. Nenhuma consulta, nenhuma sessão, nenhum efeito — o que torna
este módulo testável sem banco e o lugar certo para concentrar as duas regras
delicadas da persistência.

**Regra 1 — reidratar SEMPRE pelo construtor.**
As entidades da 2.1 são `frozen` e validam as invariantes no `__post_init__`. A
auditoria daquela Stage apontou a persistência como o caminho mais provável para
furá-las, e é por isso que aqui **não** se usa `object.__setattr__`, `__new__`,
`dataclasses.fields` ou qualquer atalho que produza a entidade sem passar pela
validação. A consequência é deliberada: uma linha corrompida no banco (um
`platform_admin` com tenant, um papel desconhecido) **levanta ao ser lida**, em vez
de reintroduzir no sistema uma entidade em estado inválido que o resto do código
vai tratar como legítima.

**Regra 2 — datetime atravessa a fronteira aware, em UTC.**
`timestamptz` guarda um instante, mas o psycopg o devolve no fuso **da sessão**.
Sem normalizar, o mesmo teste passa no runner (UTC) e falha numa máquina em
`America/Sao_Paulo`, e o `is_active` de uma sessão passa a depender do fuso de quem
consulta. `_to_utc` fecha isso na leitura; o `Engine` também fixa `timezone=UTC`
na conexão (cinto e suspensório: este mapper pode receber linha de um `Engine` que
não passou pelo composition root).
"""

from datetime import UTC, datetime
from typing import Any

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
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

Row = Any


def _to_utc(moment: datetime) -> datetime:
    """Normaliza um datetime lido do banco para aware em UTC.

    Aceita naive por robustez (um `TIMESTAMP` sem fuso, ou um driver configurado
    de outro jeito) e o interpreta como UTC, que é a convenção do projeto
    (`SystemClock` devolve `datetime.now(UTC)`). Devolver naive daqui faria
    `Session.is_active` comparar naive com aware e levantar `TypeError` no meio de
    uma renovação de token.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


# ---------------------------------------------------------------------------
# Restaurant
# ---------------------------------------------------------------------------


def restaurant_to_row(restaurant: Restaurant) -> dict[str, Any]:
    """`name` vai **verbatim** — a persistência não normaliza (ADR 2.3.0005)."""
    return {"id": restaurant.id, "name": restaurant.name}


def row_to_restaurant(row: Row) -> Restaurant:
    return Restaurant(id=RestaurantId(row.id), name=row.name)


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


def unit_to_row(unit: Unit) -> dict[str, Any]:
    return {"id": unit.id, "restaurant_id": unit.restaurant_id, "name": unit.name}


def row_to_unit(row: Row) -> Unit:
    return Unit(
        id=UnitId(row.id),
        restaurant_id=RestaurantId(row.restaurant_id),
        name=row.name,
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


def user_to_row(user: User, password_hash: PasswordHash) -> dict[str, Any]:
    """O hash viaja ao lado da entidade — `User` não carrega senha (DTO da 2.2)."""
    return {
        "id": user.id,
        # `Email` já guarda o valor normalizado; a coluna tem CHECK exigindo isso.
        "email": user.email.value,
        "role": user.role.value,
        "tenant_id": user.tenant_id,
        "password_hash": password_hash,
    }


def row_to_user(row: Row) -> User:
    """Reidrata `User` **pelo construtor**, revalidando todas as invariantes.

    A ordem é parte da especificação (concept §6): `Role.from_string` primeiro
    (papel desconhecido levanta antes de qualquer outra coisa), depois `Email`,
    e por fim `User`, cujo `__post_init__` checa id vazio → iff de `platform_admin`
    → tenant ausente, nessa ordem.

    As duas conversões saem para variáveis locais **de propósito**. Avaliá-las
    inline nos argumentos do construtor faria a precedência depender da ordem em que
    os kwargs estão escritos — Python avalia argumentos na ordem da fonte — e um
    reorder futuro (de um formatter, ou de quem só quis alinhar com a assinatura de
    `User`) inverteria a exceção observada em silêncio, sem quebrar nada visível. Com
    as locais, a ordem especificada é o próprio fluxo do código.
    """
    role = Role.from_string(row.role)
    email = Email(row.email)
    return User(
        id=UserId(row.id),
        email=email,
        role=role,
        tenant_id=RestaurantId(row.tenant_id) if row.tenant_id is not None else None,
    )


# ---------------------------------------------------------------------------
# UnitMembership
# ---------------------------------------------------------------------------


def membership_to_row(membership: UnitMembership, tenant_id: RestaurantId) -> dict[str, Any]:
    """O `tenant_id` é denormalizado na tabela e ancorado por duas FKs compostas.

    Ele não vem do próprio `UnitMembership` (que só carrega os dois ids) — quem o
    fornece é o repositório, a partir do usuário dono. As FKs compostas rejeitam a
    linha se o valor não bater com o tenant do usuário **e** o da unidade, então um
    valor errado aqui não passa despercebido.
    """
    return {
        "user_id": membership.user_id,
        "unit_id": membership.unit_id,
        "tenant_id": tenant_id,
    }


def row_to_membership(row: Row) -> UnitMembership:
    return UnitMembership(user_id=UserId(row.user_id), unit_id=UnitId(row.unit_id))


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def session_to_row(session: Session) -> dict[str, Any]:
    """Persiste o **fingerprint**, nunca o valor do refresh token (ADR 2.2.0001).

    Não existe coluna capaz de guardar o valor, então não existe nem a
    possibilidade de gravá-lo por engano — a garantia é estrutural, não de
    disciplina.
    """
    return {
        "id": session.id,
        "user_id": session.user_id,
        "refresh_token_fingerprint": session.refresh_token_fingerprint,
        "issued_at": session.issued_at,
        "expires_at": session.expires_at,
        "revoked_at": session.revoked_at,
    }


def row_to_session(row: Row) -> Session:
    return Session(
        id=SessionId(row.id),
        user_id=UserId(row.user_id),
        refresh_token_fingerprint=row.refresh_token_fingerprint,
        issued_at=_to_utc(row.issued_at),
        expires_at=_to_utc(row.expires_at),
        revoked_at=_to_utc(row.revoked_at) if row.revoked_at is not None else None,
    )


# ---------------------------------------------------------------------------
# PasswordSetupToken (Stage 2.5)
# ---------------------------------------------------------------------------


def setup_token_to_row(token: PasswordSetupToken) -> dict[str, Any]:
    """Persiste o **fingerprint**, nunca o valor do token (ADR 2.5.0002).

    Mesma disciplina de `session_to_row`: não existe coluna capaz de guardar o
    valor, então não existe nem a possibilidade de gravá-lo por engano.
    """
    return {
        "id": token.id,
        "user_id": token.user_id,
        "purpose": token.purpose.value,
        "token_fingerprint": token.token_fingerprint,
        "issued_at": token.issued_at,
        "expires_at": token.expires_at,
        "consumed_at": token.consumed_at,
    }


def row_to_setup_token(row: Row) -> PasswordSetupToken:
    """Reidrata o registro, convertendo o propósito de volta para o enum.

    `SetupTokenPurpose(row.purpose)` levanta `ValueError` para um valor que o
    enum não conhece — e é o desejado: a CHECK do banco só aceita os valores
    correntes, então uma linha fora do conjunto significa schema divergente do
    código, que precisa estourar alto em vez de virar um token de propósito
    silenciosamente errado.
    """
    return PasswordSetupToken(
        id=SetupTokenId(row.id),
        user_id=UserId(row.user_id),
        purpose=SetupTokenPurpose(row.purpose),
        token_fingerprint=row.token_fingerprint,
        issued_at=_to_utc(row.issued_at),
        expires_at=_to_utc(row.expires_at),
        consumed_at=_to_utc(row.consumed_at) if row.consumed_at is not None else None,
    )

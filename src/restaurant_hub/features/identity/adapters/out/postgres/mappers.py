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
consulta. `_para_utc` fecha isso na leitura; o `Engine` também fixa `timezone=UTC`
na conexão (cinto e suspensório: este mapper pode receber linha de um `Engine` que
não passou pelo composition root).
"""

from datetime import UTC, datetime
from typing import Any

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
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


def _para_utc(momento: datetime) -> datetime:
    """Normaliza um datetime lido do banco para aware em UTC.

    Aceita naive por robustez (um `TIMESTAMP` sem fuso, ou um driver configurado
    de outro jeito) e o interpreta como UTC, que é a convenção do projeto
    (`SystemClock` devolve `datetime.now(UTC)`). Devolver naive daqui faria
    `Session.is_active` comparar naive com aware e levantar `TypeError` no meio de
    uma renovação de token.
    """
    if momento.tzinfo is None:
        return momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC)


# ---------------------------------------------------------------------------
# Restaurant
# ---------------------------------------------------------------------------


def restaurante_para_linha(restaurant: Restaurant) -> dict[str, Any]:
    """`name` vai **verbatim** — a persistência não normaliza (ADR 2.3.0005)."""
    return {"id": restaurant.id, "name": restaurant.name}


def linha_para_restaurante(row: Row) -> Restaurant:
    return Restaurant(id=RestaurantId(row.id), name=row.name)


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------


def unidade_para_linha(unit: Unit) -> dict[str, Any]:
    return {"id": unit.id, "restaurant_id": unit.restaurant_id, "name": unit.name}


def linha_para_unidade(row: Row) -> Unit:
    return Unit(
        id=UnitId(row.id),
        restaurant_id=RestaurantId(row.restaurant_id),
        name=row.name,
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


def usuario_para_linha(user: User, password_hash: PasswordHash) -> dict[str, Any]:
    """O hash viaja ao lado da entidade — `User` não carrega senha (DTO da 2.2)."""
    return {
        "id": user.id,
        # `Email` já guarda o valor normalizado; a coluna tem CHECK exigindo isso.
        "email": user.email.value,
        "role": user.role.value,
        "tenant_id": user.tenant_id,
        "password_hash": password_hash,
    }


def linha_para_usuario(row: Row) -> User:
    """Reidrata `User` **pelo construtor**, revalidando todas as invariantes.

    A ordem é parte da especificação (concept §6): `Role.from_string` primeiro
    (papel desconhecido levanta antes de qualquer outra coisa), depois `Email`,
    e por fim `User`, cujo `__post_init__` checa id vazio → iff de `platform_admin`
    → tenant ausente, nessa ordem.
    """
    return User(
        id=UserId(row.id),
        email=Email(row.email),
        role=Role.from_string(row.role),
        tenant_id=RestaurantId(row.tenant_id) if row.tenant_id is not None else None,
    )


# ---------------------------------------------------------------------------
# UnitMembership
# ---------------------------------------------------------------------------


def vinculo_para_linha(membership: UnitMembership, tenant_id: RestaurantId) -> dict[str, Any]:
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


def linha_para_vinculo(row: Row) -> UnitMembership:
    return UnitMembership(user_id=UserId(row.user_id), unit_id=UnitId(row.unit_id))


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def sessao_para_linha(session: Session) -> dict[str, Any]:
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


def linha_para_sessao(row: Row) -> Session:
    return Session(
        id=SessionId(row.id),
        user_id=UserId(row.user_id),
        refresh_token_fingerprint=row.refresh_token_fingerprint,
        issued_at=_para_utc(row.issued_at),
        expires_at=_para_utc(row.expires_at),
        revoked_at=_para_utc(row.revoked_at) if row.revoked_at is not None else None,
    )

"""Material de token que atravessa o `TokenIssuer`.

A separação entre `value` e `fingerprint` é o que permite revogar sem guardar
segredo: o cliente recebe o `value`, o banco guarda só o `fingerprint`. Um dump
do banco, portanto, não devolve nenhum refresh token utilizável (ADR 2.2.0001).

`AccessTokenClaims` carrega `session_id` para que uma checagem de introspecção na
Stage 2.4 possa, no futuro, fechar a janela residual entre revogar a sessão e o
access token expirar por conta própria — sem precisar mudar a forma deste port.
"""

from dataclasses import dataclass
from datetime import datetime

from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role


@dataclass(frozen=True)
class IssuedRefreshToken:
    """Refresh token recém-emitido.

    Attributes:
        value: valor opaco entregue ao cliente — **nunca** persistido.
        fingerprint: derivação determinística do valor, essa sim persistida.
            Vale a lei do port: `issuer.fingerprint(value) == fingerprint`.
    """

    value: str
    fingerprint: str


@dataclass(frozen=True)
class AccessTokenClaims:
    """Conteúdo do access token a ser assinado pelo adapter de segurança (2.4).

    Attributes:
        subject: usuário dono do token.
        role: papel fixo, para o guard não precisar reconsultar o banco.
        tenant_id: tenant do usuário; `None` para `platform_admin`.
        session_id: sessão que originou o token.
        expires_at: instante de expiração do access token.
    """

    subject: UserId
    role: Role
    tenant_id: RestaurantId | None
    session_id: SessionId
    expires_at: datetime

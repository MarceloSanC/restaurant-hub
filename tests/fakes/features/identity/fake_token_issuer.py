"""Fake determinístico de `TokenIssuer`.

A lei do port (`fingerprint(t.value) == t.fingerprint`) é honrada **por
construção**: `issue_refresh_token` deriva o fingerprint chamando o próprio
`fingerprint`, em vez de montar a string duas vezes. Duplicar a fórmula seria
justamente o defeito que a lei existe para impedir — e um fake que a duplicasse
poderia divergir de si mesmo.
"""

from restaurant_hub.features.identity.application.dtos.tokens import (
    AccessTokenClaims,
    IssuedRefreshToken,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer


class FakeTokenIssuer:
    """Implementação determinística do port, com histórico de claims emitidas."""

    def __init__(self) -> None:
        self._counter = 0
        self.issued_claims: list[AccessTokenClaims] = []

    def issue_access_token(self, claims: AccessTokenClaims) -> str:
        self.issued_claims.append(claims)
        return f"access::{claims.subject}::{claims.session_id}"

    def issue_refresh_token(self) -> IssuedRefreshToken:
        self._counter += 1
        value = f"refresh-{self._counter}"
        return IssuedRefreshToken(value=value, fingerprint=self.fingerprint(value))

    def fingerprint(self, refresh_token_value: str) -> str:
        return f"fp::{refresh_token_value}"


_conforms: TokenIssuer = FakeTokenIssuer()

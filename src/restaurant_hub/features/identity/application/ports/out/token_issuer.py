"""Port de saída: emissão de tokens (JWT de acesso + refresh opaco).

Implementado na Stage 2.4. Concentra **toda** a criptografia de token: assinar o
access token, gerar o material aleatório do refresh e derivar o fingerprint que a
sessão persiste. A aplicação nunca assina, gera segredo nem hasheia por conta
própria.

**Lei do port** (vale para o fake e para o adapter real):

    t = issuer.issue_refresh_token()
    assert issuer.fingerprint(t.value) == t.fingerprint

Sem essa lei, um adapter poderia derivar o fingerprint de um jeito na emissão e
de outro na consulta — as duas metades pareceriam corretas isoladamente, e
**toda** busca de refresh na 2.4 falharia, sem que nenhum teste desta Stage
percebesse. É por isso que o critério de aceite assere via
`issuer.fingerprint(...)`, e não por igualdade de campo.
"""

from typing import Protocol

from restaurant_hub.features.identity.application.dtos.tokens import (
    AccessTokenClaims,
    IssuedRefreshToken,
)


class TokenIssuer(Protocol):
    """Contrato de emissão de tokens de acesso e de refresh."""

    def issue_access_token(self, claims: AccessTokenClaims) -> str:
        """Assina e devolve o access token com as claims dadas."""
        ...

    def issue_refresh_token(self) -> IssuedRefreshToken:
        """Gera um refresh token opaco e o seu fingerprint."""
        ...

    def fingerprint(self, refresh_token_value: str) -> str:
        """Deriva o fingerprint de um refresh token, para consulta na sessão."""
        ...

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

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Verifica um access token e devolve as suas claims (Stage 2.4).

        **Lei:** `decode_access_token(issue_access_token(c))` devolve `c`, e
        **nada mais** atravessa este método. Verificar significa assinatura *e*
        expiração; qualquer falha — assinatura inválida, formato quebrado, token
        expirado, algoritmo inesperado, claim ausente — levanta
        `InvalidAccessTokenError`. **Nunca** devolve claims de um token que não
        passou na verificação.

        **Não existe variante "decodificar sem verificar", e a ausência é
        deliberada.** Um método desses é o footgun clássico: alguém o alcança
        "só para ler o subject" num log ou numa métrica, e a verificação some do
        caminho sem que nenhum teste perceba — o token passa a ser confiável por
        omissão.

        Mora neste port, e não num `AccessTokenVerifier` separado, porque
        emissão e verificação compartilham segredo e algoritmo: separá-las
        criaria dois pontos de configuração capazes de divergir em silêncio, e a
        divergência se manifestaria como "todo token é inválido" — que parece bug
        de autenticação, não de configuração, com as duas metades corretas
        isoladamente. ADR 2.4.0002.
        """
        ...

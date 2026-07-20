"""Fake determinístico de `TokenIssuer`.

A lei do port (`fingerprint(t.value) == t.fingerprint`) é honrada **por
construção**: `issue_refresh_token` deriva o fingerprint chamando o próprio
`fingerprint`, em vez de montar a string duas vezes. Duplicar a fórmula seria
justamente o defeito que a lei existe para impedir — e um fake que a duplicasse
poderia divergir de si mesmo.

`decode_access_token` (Stage 2.4) segue a mesma disciplina: em vez de fabricar
claims a partir do texto do token, o fake guarda o que emitiu e devolve o
registro. Assim o round-trip `decode(issue(c)) == c` vale por construção, e
qualquer token que este fake não tenha emitido — inclusive um forjado com o
formato certo — levanta `InvalidAccessTokenError`, como o adapter real faz para
assinatura inválida.
"""

from restaurant_hub.features.identity.application.dtos.tokens import (
    AccessTokenClaims,
    IssuedRefreshToken,
)
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer


class FakeTokenIssuer:
    """Implementação determinística do port, com histórico de claims emitidas."""

    def __init__(self) -> None:
        self._counter = 0
        self.issued_claims: list[AccessTokenClaims] = []
        # Token emitido -> claims. É o que torna a decodificação uma inversão
        # real da emissão, e não uma segunda implementação capaz de divergir.
        self._emitidos: dict[str, AccessTokenClaims] = {}

    def issue_access_token(self, claims: AccessTokenClaims) -> str:
        self.issued_claims.append(claims)
        token = f"access::{claims.subject}::{claims.session_id}"
        self._emitidos[token] = claims
        return token

    def issue_refresh_token(self) -> IssuedRefreshToken:
        self._counter += 1
        value = f"refresh-{self._counter}"
        return IssuedRefreshToken(value=value, fingerprint=self.fingerprint(value))

    def fingerprint(self, refresh_token_value: str) -> str:
        return f"fp::{refresh_token_value}"

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        claims = self._emitidos.get(token)
        if claims is None:
            # Token que este emissor não assinou. O adapter real chega aqui por
            # assinatura inválida; o fake, por não reconhecer o valor. A exceção
            # é a mesma, que é o que o contrato exige.
            raise InvalidAccessTokenError()
        return claims

    def invalidar(self, token: str) -> None:
        """Faz um token já emitido passar a ser recusado (auxílio de teste).

        Existe porque o fake não tem relógio: sem isto, o caminho "token
        expirado" seria inalcançável no teste que usa o fake, e a cobertura do
        guard dependeria do adapter real.
        """
        self._emitidos.pop(token, None)


_conforms: TokenIssuer = FakeTokenIssuer()

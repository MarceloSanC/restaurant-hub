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

**E o fake expira.** A lei do port diz que verificar é assinatura *e* expiração;
uma primeira versão deste fake só checava o reconhecimento do valor, e portanto
aceitava indefinidamente um token vencido. Isso é exatamente a mentira que o
teste de contrato existe para impedir: o guard HTTP delega a expiração ao issuer,
então qualquer teste de guard escrito com um fake que não expira passa verde
sobre um sistema que não expira nada. O relógio é injetável para que o teste possa
controlá-lo; sem injeção, usa o relógio real, de modo que o default é honesto.
"""

from datetime import UTC, datetime

from restaurant_hub.features.identity.application.dtos.tokens import (
    AccessTokenClaims,
    IssuedRefreshToken,
)
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.shared.application.ports.out.clock import Clock


class FakeTokenIssuer:
    """Implementação determinística do port, com histórico de claims emitidas."""

    def __init__(self, clock: Clock | None = None) -> None:
        # Sem relógio injetado, usa o real: o default precisa ser o honesto, ou
        # o fake volta a mentir para quem não pensou no assunto.
        self._clock = clock
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
        # Expiração: metade da lei do port, e a metade que um fake esquece.
        # `>=` porque o intervalo é half-open, como em `Session.is_active`.
        if self._now() >= claims.expires_at:
            raise InvalidAccessTokenError()
        return claims

    def _now(self) -> datetime:
        return self._clock.now() if self._clock is not None else datetime.now(UTC)


_conforms: TokenIssuer = FakeTokenIssuer()

"""Adapter de `TokenIssuer` sobre JWT (`PyJWT`) e `secrets`/`hashlib`.

Duas metades com naturezas opostas, e é importante não confundi-las:

- **Access token: JWT assinado.** Carrega claims, é auto-contido e é verificado
  por assinatura. Ninguém o consulta no banco — por isso o TTL é curto.
- **Refresh token: valor opaco aleatório.** Não carrega nada, não é parseável, e
  a sua validade vem de existir uma sessão viva com o fingerprint correspondente.

Escolhas e parâmetros em ADR 2.4.0004.
"""

import hashlib
import secrets
from datetime import UTC, datetime

import jwt

from restaurant_hub.features.identity.application.dtos.identifiers import SessionId
from restaurant_hub.features.identity.application.dtos.tokens import (
    AccessTokenClaims,
    IssuedRefreshToken,
)
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.domain.exceptions.errors import InvalidRoleError
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

# Bytes de entropia do refresh token. 32 bytes = 256 bits do CSPRNG do SO —
# espaço de busca que não se percorre, o que é o que permite guardar apenas um
# hash rápido do valor (ver `fingerprint`).
_REFRESH_ENTROPY_BYTES = 32


class JwtTokenIssuer:
    """Implementação de `TokenIssuer` com JWT simétrico."""

    def __init__(self, secret_key: str, algorithm: str = "HS256") -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm

    def issue_access_token(self, claims: AccessTokenClaims) -> str:
        """Assina o access token com as claims dadas."""
        payload = {
            "sub": str(claims.subject),
            "role": claims.role.value,
            "tenant_id": claims.tenant_id,
            "sid": str(claims.session_id),
            "exp": claims.expires_at,
        }
        token: str = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
        return token

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Verifica assinatura e expiração e devolve as claims.

        **`algorithms` é uma allowlist de um item, e essa linha é a defesa mais
        importante do módulo.** Sem ela — ou pior, passando o `alg` lido do
        cabeçalho do próprio token — abre-se a confusão de algoritmo: o atacante
        troca o cabeçalho para `none` e apresenta um token sem assinatura, ou
        troca de RS256 para HS256 e assina com a chave pública, que é pública.
        PyJWT exige a lista justamente para que a escolha seja do servidor, nunca
        do portador do token (RFC 8725 §3.1).

        **Toda falha vira `InvalidAccessTokenError`**, sem distinguir a causa: o
        cliente não deve saber se errou a assinatura, se o token expirou ou se a
        claim estava faltando. `PyJWTError` é a raiz da hierarquia da lib e cobre
        expiração, assinatura, formato e algoritmo; o `KeyError`/`ValueError`
        cobre um payload bem assinado mas com forma errada — cenário real durante
        uma troca de formato de claims, em que os tokens antigos ainda circulam.
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
            tenant_id = payload["tenant_id"]
            return AccessTokenClaims(
                subject=UserId(payload["sub"]),
                role=Role.from_string(payload["role"]),
                # `None` é estado legítimo, não ausência: é o tenant de um
                # `platform_admin` (ADR 2.1.0002). Colapsá-lo numa string vazia
                # quebraria a invariante de `User` do outro lado.
                tenant_id=None if tenant_id is None else RestaurantId(tenant_id),
                session_id=SessionId(payload["sid"]),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        except (jwt.PyJWTError, InvalidRoleError, KeyError, ValueError, TypeError) as exc:
            raise InvalidAccessTokenError() from exc

    def issue_refresh_token(self) -> IssuedRefreshToken:
        """Gera um refresh token opaco e o seu fingerprint.

        O fingerprint é derivado **chamando `self.fingerprint`**, não repetindo a
        fórmula. Repeti-la é precisamente o defeito que a lei do port existe para
        impedir: as duas metades pareceriam corretas isoladamente, e toda busca de
        sessão falharia — um bug que se manifesta como "nenhum refresh token
        jamais é encontrado", longe da linha que o causou.
        """
        value = secrets.token_urlsafe(_REFRESH_ENTROPY_BYTES)
        return IssuedRefreshToken(value=value, fingerprint=self.fingerprint(value))

    def fingerprint(self, refresh_token_value: str) -> str:
        """Deriva o fingerprint determinístico do refresh token.

        **SHA-256 sem sal, e isso é correto aqui — mas seria errado para senha.**
        A diferença é a entropia da entrada. Senha é escolhida por humano e
        pertence a um espaço pequeno, então o ataque é dicionário e a defesa é
        sal + KDF lento. Um refresh token tem 256 bits uniformes do CSPRNG: não há
        dicionário a percorrer nem rainbow table que possa existir, então um hash
        rápido não vaza nada.

        E o determinismo não é opcional: `find_by_fingerprint` busca por valor
        exato, então um sal por registro tornaria a consulta impossível. Argon2
        aqui seria, ao mesmo tempo, mais lento e não-funcional.
        """
        return hashlib.sha256(refresh_token_value.encode("utf-8")).hexdigest()

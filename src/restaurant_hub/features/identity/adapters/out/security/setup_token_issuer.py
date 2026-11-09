"""Adapter de `SetupTokenIssuer` sobre `secrets` + SHA-256.

**Separado do `JwtTokenIssuer` de propósito** (ADR 2.5.0002). A forma é parecida
— valor opaco mais fingerprint —, e é exatamente por isso que a separação é
estrutural: uma futura troca da criptografia do refresh token (RS256, outra
derivação de fingerprint, ambas antecipadas pelo ADR 2.4.0002) mudaria em
silêncio os tokens de convite, invalidando os que estivessem em voo, sem que
nenhum teste apontasse a causa.

**SHA-256 puro, e não um KDF — a escolha é deliberada e vale explicação, porque
"hash de credencial sem KDF" costuma ser defeito.** Um KDF (argon2, bcrypt)
existe para tornar cara a busca no espaço de entradas, e só faz sentido quando o
espaço é pequeno: senhas humanas. Aqui a entrada é
`secrets.token_urlsafe(32)` — 256 bits de aleatoriedade criptográfica —, então não
há espaço de busca a proteger: enumerá-lo é inviável independentemente do custo
por tentativa. Trocar por argon2 não acrescentaria segurança e adicionaria
centenas de milissegundos a **cada** apresentação de token, numa rota **pública** e
sem rate limit — isto é, transformaria a defesa num vetor de negação de serviço.
É a mesma escolha que o fingerprint de refresh da 2.4 fez, pela mesma razão.

O que o hash **faz** aqui é impedir que um dump do banco devolva tokens
utilizáveis: guarda-se a derivação, nunca o valor.
"""

import hashlib
import secrets

from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    IssuedSetupToken,
)

# 32 bytes de entropia, codificados em base64url (~43 caracteres). Entra em URL
# de e-mail sem escape, que é o único motivo de ser `urlsafe` e não `hex`.
_ENTROPY_BYTES = 32


class Sha256SetupTokenIssuer:
    """Implementação de `SetupTokenIssuer` com token opaco e fingerprint SHA-256."""

    def issue(self) -> IssuedSetupToken:
        """Gera um token novo.

        O fingerprint é derivado chamando o próprio `fingerprint`, e não repetindo
        a fórmula. Repeti-la é precisamente o defeito que a lei do port existe
        para impedir: as duas metades pareceriam corretas isoladamente, e **toda**
        redenção falharia, porque a consulta procuraria um fingerprint diferente
        do que a emissão gravou.
        """
        value = secrets.token_urlsafe(_ENTROPY_BYTES)
        return IssuedSetupToken(value=value, fingerprint=self.fingerprint(value))

    def fingerprint(self, token_value: str) -> str:
        """Deriva o fingerprint determinístico do valor.

        Sem salt, e a ausência é obrigatória, não esquecimento: um salt por
        chamada tornaria a derivação não determinística, e a redenção não
        encontraria o registro que a emissão gravou. O que dispensa o salt é a
        entropia da entrada — não há dicionário de tokens a pré-computar.
        """
        return hashlib.sha256(token_value.encode("utf-8")).hexdigest()

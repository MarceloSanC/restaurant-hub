"""Port de saída: emissão do token de definição de senha.

**Separado do `TokenIssuer`, de propósito** (ADR 2.5.0002). O `TokenIssuer` serve
à sessão autenticada; este serve a um token de uso único entregue por e-mail. A
forma é parecida — valor opaco + fingerprint —, e é exatamente por isso que a
separação precisa ser estrutural: com um port só, uma futura troca da criptografia
do refresh token (RS256, outra derivação de fingerprint — ambas antecipadas pelo
ADR 2.4.0002) mudaria em silêncio os tokens de convite, invalidando os que
estivessem em voo, sem que nenhum teste apontasse a causa.

**Lei do port** (vale para o fake e para o adapter real):

    t = issuer.issue()
    assert issuer.fingerprint(t.value) == t.fingerprint

Sem ela, um adapter poderia derivar o fingerprint de um jeito na emissão e de
outro na consulta; as duas metades pareceriam corretas isoladamente e **toda**
redenção de token falharia. É por isso que o teste de contrato assere via
`issuer.fingerprint(...)`, e não por igualdade de campo.
"""

from typing import Protocol

from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    IssuedSetupToken,
)


class SetupTokenIssuer(Protocol):
    """Contrato de emissão do token de definição de senha."""

    def issue(self) -> IssuedSetupToken:
        """Gera um token opaco novo e o seu fingerprint.

        Cada chamada devolve um valor **diferente**: o token identifica uma
        emissão, não um usuário.
        """
        ...

    def fingerprint(self, token_value: str) -> str:
        """Deriva o fingerprint de um valor, para consulta no repositório.

        Determinístico: o mesmo valor sempre produz o mesmo fingerprint, senão a
        redenção não encontraria o registro que a emissão gravou.
        """
        ...

"""Fake determinístico de `SetupTokenIssuer`.

A lei do port (`fingerprint(t.value) == t.fingerprint`) é honrada **por
construção**: `issue` deriva o fingerprint chamando o próprio `fingerprint`, em
vez de montar a string duas vezes. Duplicar a fórmula seria justamente o defeito
que a lei existe para impedir — um fake que a duplicasse poderia divergir de si
mesmo e ainda assim passar no teste que compara os dois campos.

O contador garante que duas emissões produzem valores distintos, que é a outra
metade do contrato: um issuer que devolvesse sempre o mesmo valor faria dois
convites compartilharem o mesmo link, e o teste de "segundo token invalida o
primeiro" passaria por acidente.
"""

from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    IssuedSetupToken,
)
from restaurant_hub.features.identity.application.ports.out.setup_token_issuer import (
    SetupTokenIssuer,
)


class FakeSetupTokenIssuer:
    """Implementação determinística do port, com valores previsíveis."""

    def __init__(self) -> None:
        self._counter = 0

    def issue(self) -> IssuedSetupToken:
        self._counter += 1
        value = f"setup-{self._counter}"
        return IssuedSetupToken(value=value, fingerprint=self.fingerprint(value))

    def fingerprint(self, token_value: str) -> str:
        return f"sfp::{token_value}"


_conforms: SetupTokenIssuer = FakeSetupTokenIssuer()

"""Fake determinístico de `PasswordHasher`.

O hash é `hashed::<senha>` — legível na asserção e trivialmente reversível, o que
é aceitável **porque é um fake de teste** e nunca sai daqui. O que importa é que
as leis do port sejam honradas: `verify` não levanta, e `dummy_hash()` é
inatingível.

`verify_calls` existe para o CA7: o teste precisa provar que o login verifica a
senha **mesmo quando o e-mail não existe**, que é a defesa contra enumeração por
tempo de resposta. Sem o contador, esse caminho seria indistinguível de um
curto-circuito.
"""

from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)

_PREFIX = "hashed::"

# Não começa com `_PREFIX`, então nenhuma senha pode produzi-lo: `verify` contra
# este valor é sempre False, que é exatamente a lei 2 do port.
_DUMMY = PasswordHash("dummy::inatingivel")


class FakePasswordHasher:
    """Implementação determinística do port, com contagem de verificações."""

    def __init__(self) -> None:
        self.verify_calls = 0

    def hash(self, plain_password: str) -> PasswordHash:
        return PasswordHash(f"{_PREFIX}{plain_password}")

    def verify(self, plain_password: str, password_hash: PasswordHash) -> bool:
        self.verify_calls += 1
        # Nunca levanta, mesmo com hash malformado — lei 1 do port.
        return password_hash == f"{_PREFIX}{plain_password}"

    def dummy_hash(self) -> PasswordHash:
        return _DUMMY


_conforms: PasswordHasher = FakePasswordHasher()

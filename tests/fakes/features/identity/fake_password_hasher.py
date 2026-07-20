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
        # Guarda os argumentos, não só a contagem: o CA7 precisa provar **contra
        # qual hash** o caminho de e-mail inexistente verificou. Contar chamadas
        # não distingue `dummy_hash()` de um hash qualquer — e um hash qualquer
        # devolveria `False` de imediato no argon2 real, sem rodar o KDF,
        # reabrindo o oráculo de tempo que a defesa existe para fechar.
        self.verify_args: list[tuple[str, PasswordHash]] = []
        self._unusable_counter = 0

    def hash(self, plain_password: str) -> PasswordHash:
        return PasswordHash(f"{_PREFIX}{plain_password}")

    def verify(self, plain_password: str, password_hash: PasswordHash) -> bool:
        self.verify_calls += 1
        self.verify_args.append((plain_password, password_hash))
        # Nunca levanta, mesmo com hash malformado — lei 1 do port.
        return password_hash == f"{_PREFIX}{plain_password}"

    def dummy_hash(self) -> PasswordHash:
        return _DUMMY

    def unusable_hash(self) -> PasswordHash:
        """Hash inatingível e **diferente a cada chamada** (ADR 2.5.0004).

        Não começa com `_PREFIX`, então nenhuma senha o produz e `verify` sempre
        devolve `False` — inclusive para a sentinela do adapter argon2, que é a
        senha que o teste de contrato assere nominalmente.

        O contador existe para honrar a lei 2 do método: um fake que devolvesse
        uma constante deixaria passar um adapter que faz o mesmo, e todo
        convidado compartilharia a mesma string em `users.password_hash`.
        """
        self._unusable_counter += 1
        return PasswordHash(f"unusable::{self._unusable_counter}")


_conforms: PasswordHasher = FakePasswordHasher()

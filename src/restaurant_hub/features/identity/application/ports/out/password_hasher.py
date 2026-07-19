"""Port de saída: hash e verificação de senha.

Implementado com argon2 (ou bcrypt) na Stage 2.4. Toda a criptografia de senha
fica atrás deste port — a camada de aplicação nunca hasheia nem compara nada por
conta própria.

**Leis do port** (valem para o fake e para o adapter real):

1. `verify` **nunca levanta exceção**. Hash malformado, vazio ou de outro
   algoritmo devolve `False`. Argon2 cru levanta `InvalidHash` nesse caso, e é o
   adapter quem absorve isso — deixar vazar transformaria "credencial inválida"
   num erro 500.
2. `dummy_hash()` devolve um hash **válido**, com os mesmos parâmetros de custo
   da produção, contra o qual `verify` sempre falha.

A segunda lei existe por causa de um ataque concreto: se o login curto-circuitar
quando o e-mail não existe, ele responde muito mais rápido do que quando a senha
está errada, e essa diferença de tempo enumera as contas cadastradas. Para pagar
o mesmo custo nos dois caminhos, `authenticate_user` verifica contra o dummy —
e o hash constante precisa vir do adapter, porque a camada de aplicação não tem
como fabricar um hash argon2 legítimo nem deve conhecer os parâmetros dele.
"""

from typing import Protocol

from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash


class PasswordHasher(Protocol):
    """Contrato de hash e verificação de senha."""

    def hash(self, plain_password: str) -> PasswordHash:
        """Deriva o hash de uma senha em claro."""
        ...

    def verify(self, plain_password: str, password_hash: PasswordHash) -> bool:
        """True se a senha corresponde ao hash. Nunca levanta (lei 1)."""
        ...

    def dummy_hash(self) -> PasswordHash:
        """Hash válido e inatingível, para equalizar o tempo do login (lei 2)."""
        ...

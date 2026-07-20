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
        """Hash válido e inatingível, para equalizar o tempo do login (lei 2).

        **Só serve a esse propósito, e a Stage 2.5 descobriu por quê.** A lei 2
        promete que `verify` "sempre falha", mas o adapter argon2 deriva este
        valor de uma constante literal do repositório: `verify(_SENTINELA_DUMMY,
        dummy_hash())` devolve **`True`**. Enquanto o valor só é comparado e
        descartado, conhecer a pré-imagem não vale nada. **Persistido como
        credencial**, valeria uma tomada de conta — daí `unusable_hash()`.
        """
        ...

    def unusable_hash(self) -> PasswordHash:
        """Hash válido, aleatório e **sem pré-imagem conhecida por ninguém**.

        É o que uma conta convidada carrega em `users.password_hash` enquanto a
        pessoa não define a própria senha (ADR 2.5.0004). O adapter o deriva de
        material gerado com `secrets` e descartado na hora — ninguém, nem quem
        escreveu o código, consegue produzir uma senha que verifique contra ele.

        **Leis** (valem para o fake e para o adapter real):

        1. `verify(p, unusable_hash())` é `False` para **todo** `p` — inclusive
           a sentinela do `dummy_hash()`. O teste de contrato assere essa senha
           **nominalmente**, e é essa asserção que impede alguém de "simplificar"
           os dois métodos num só no futuro.
        2. Duas chamadas devolvem valores **diferentes**. Não é preciosismo: um
           valor constante faria toda conta não ativada carregar a mesma string
           em `users.password_hash`, entregando a quem tem leitura no banco a
           lista exata das contas pendentes — que é o conjunto de alvos mais
           valioso do sistema.

        Note o contraste deliberado com `dummy_hash()`, que é computado **uma
        vez** no construtor: lá a estabilidade é obrigatória (recomputar pagaria
        dois KDFs no caminho "e-mail inexistente" e reabriria o oráculo de
        tempo); aqui a variação é obrigatória. São requisitos opostos, e é por
        isso que são dois métodos.
        """
        ...

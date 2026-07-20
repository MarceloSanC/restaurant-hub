"""Adapter de `PasswordHasher` sobre argon2id (`argon2-cffi`).

Escolha e parâmetros em ADR 2.4.0004: argon2id é a primeira recomendação do OWASP
Password Storage Cheat Sheet, e os parâmetros de custo são os **defaults da
biblioteca** — um custo mal calibrado à mão é pior que um default mantido, e a
lib acompanha a recomendação corrente a cada release.

O salt é gerado por hash pela própria `argon2-cffi` e viaja embutido na string
codificada; este adapter não adiciona nenhum.

**As duas leis do port são implementadas aqui, e as duas existem por um ataque
concreto** — ver os docstrings de `verify` e `dummy_hash`.
"""

from argon2 import PasswordHasher as Argon2Backend
from argon2.exceptions import Argon2Error, InvalidHashError

from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash

# Senha-semente do hash inatingível. Nunca é uma senha real de ninguém: o hash
# derivado dela só existe para ser comparado e falhar.
_SENTINELA_DUMMY = "dummy-password-that-never-authenticates"


class Argon2PasswordHasher:
    """Implementação de `PasswordHasher` com argon2id."""

    def __init__(self, backend: Argon2Backend | None = None) -> None:
        self._backend = backend or Argon2Backend()
        # Computado UMA vez, no construtor, e não a cada chamada de
        # `dummy_hash()`. Recomputar pareceria inofensivo e reabriria pelo outro
        # lado o oráculo de tempo que a lei 2 fecha: o caminho "e-mail
        # inexistente" passaria a pagar DOIS argon2 (derivar o dummy + verificar
        # contra ele) enquanto o caminho "senha errada" paga um só — e a
        # diferença voltaria a distinguir os dois casos no relógio.
        self._dummy_hash = PasswordHash(self._backend.hash(_SENTINELA_DUMMY))

    def hash(self, plain_password: str) -> PasswordHash:
        """Deriva o hash argon2id da senha, com salt novo a cada chamada."""
        return PasswordHash(self._backend.hash(plain_password))

    def verify(self, plain_password: str, password_hash: PasswordHash) -> bool:
        """True se a senha corresponde ao hash. **Nunca levanta** (lei 1).

        `argon2-cffi` levanta em dois cenários distintos que, para o chamador,
        são a mesma coisa: senha errada (`VerifyMismatchError`) e hash que ela
        não consegue sequer interpretar (`InvalidHashError` — vazio, truncado,
        de bcrypt, corrompido no banco). Deixar o segundo escapar transformaria
        "credencial inválida" num **500**, o que é pior duas vezes: entrega ao
        atacante um sinal de que aquele registro é diferente dos outros, e
        transforma um dado corrompido numa página de erro em vez de um login
        recusado.

        `Argon2Error` é a raiz da hierarquia da lib e cobre também
        `VerificationError` e falhas de backend; `InvalidHashError` é capturada
        explicitamente porque **não** herda de `Argon2Error`.

        `argon2-cffi` **nunca devolve `False`**: ou devolve `True`, ou levanta.
        Por isso o retorno é construído aqui em vez de repassado — repassar
        devolveria o `Any` da lib como se fosse `bool`, e o type-checker teria de
        acreditar sem verificar.
        """
        try:
            self._backend.verify(password_hash, plain_password)
        except (Argon2Error, InvalidHashError):
            return False
        return True

    def dummy_hash(self) -> PasswordHash:
        """Hash válido e inatingível, para equalizar o tempo do login (lei 2).

        O ataque que isto fecha: se o login curto-circuitasse ao não achar o
        e-mail, responderia em microssegundos, enquanto o caminho "senha errada"
        pagaria o custo do argon2. Medida de fora, a diferença enumera as contas
        cadastradas. `authenticate_user` verifica contra este hash para pagar o
        mesmo custo nos dois caminhos.

        Precisa ser **válido** (parseável, com os parâmetros de produção) — um
        valor arbitrário faria o argon2 falhar no parse e voltar `False` de
        imediato, sem rodar o KDF, o que reabriria o oráculo que o método fecha.
        """
        return self._dummy_hash

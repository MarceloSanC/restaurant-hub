"""Testes do adapter argon2id contra as duas leis do port `PasswordHasher`.

As leis não são detalhe de implementação — cada uma fecha um ataque concreto, e
ambas são invisíveis num teste de "hash e verify funcionam". Por isso a maior
parte deste arquivo testa **falha**, não sucesso.
"""

import pytest

from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)

pytestmark = pytest.mark.unit

_SENHA = "s3nha-muito-secreta"


def test_adapter_satisfaz_o_protocolo() -> None:
    """Conformidade estrutural com o port.

    A anotação vive no teste, e não como `_conforms` no módulo de produção: uma
    instância em nível de módulo instanciaria adapter fora do composition root
    (LAYOUT §6) e faria todo import pagar um argon2 completo, porque o
    `dummy_hash` é computado no construtor.
    """
    hasher: PasswordHasher = Argon2PasswordHasher()

    assert hasher.verify(_SENHA, hasher.hash(_SENHA)) is True


def test_hash_e_verify_casam() -> None:
    hasher = Argon2PasswordHasher()

    assert hasher.verify(_SENHA, hasher.hash(_SENHA)) is True


def test_verify_rejeita_senha_errada() -> None:
    hasher = Argon2PasswordHasher()

    assert hasher.verify("outra-senha", hasher.hash(_SENHA)) is False


def test_hash_da_mesma_senha_difere_a_cada_chamada() -> None:
    """Salt por hash.

    Sem salt, hashes iguais denunciariam senhas iguais entre usuários — e um
    único hash quebrado quebraria todas as contas que compartilham a senha.
    """
    hasher = Argon2PasswordHasher()

    assert hasher.hash(_SENHA) != hasher.hash(_SENHA)


@pytest.mark.parametrize(
    "malformado",
    [
        "",
        "nao-e-um-hash",
        "$argon2id$truncado",
        # Hash de bcrypt: formato válido de OUTRO algoritmo. É o caso realista
        # de uma migração de algoritmo pela metade.
        "$2b$12$KIXQJ0k7X8Zq1YQZ8Q1Q1eR0k7X8Zq1YQZ8Q1Q1eR0k7X8Zq1YQZ8",
        "$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$hash-invalido",
    ],
)
def test_verify_nunca_levanta_com_hash_malformado(malformado: str) -> None:
    """Lei 1 do port: hash que a lib não consegue interpretar é `False`, não exceção.

    Este é o teste que impede um 500 no login. `argon2-cffi` levanta
    `InvalidHashError` para cada uma destas entradas; se a exceção escapasse, um
    registro corrompido no banco derrubaria a requisição em vez de recusá-la — e
    a diferença entre 500 e 401 diria ao atacante que aquela conta é especial.
    """
    hasher = Argon2PasswordHasher()

    assert hasher.verify(_SENHA, PasswordHash(malformado)) is False


def test_dummy_hash_e_parseavel_pelo_proprio_argon2() -> None:
    """Lei 2, primeira metade: o hash inatingível precisa ser **válido**.

    Se fosse um valor arbitrário, o argon2 falharia no parse e devolveria `False`
    imediatamente, sem rodar o KDF — e o caminho "e-mail inexistente" voltaria a
    ser mais rápido que "senha errada", que é exatamente o oráculo de tempo que a
    lei fecha. Verificar que ele é parseável é verificar que o custo foi pago.
    """
    hasher = Argon2PasswordHasher()
    dummy = hasher.dummy_hash()

    assert dummy.startswith("$argon2id$")
    # Um hash real de referência tem o mesmo prefixo de parâmetros: é isso que
    # significa "mesmos parâmetros de custo da produção".
    referencia = hasher.hash(_SENHA)
    assert dummy.split("$")[1:4] == referencia.split("$")[1:4]


@pytest.mark.parametrize("tentativa", ["", _SENHA, "dummy", "admin", "123456"])
def test_dummy_hash_e_inatingivel_por_qualquer_senha(tentativa: str) -> None:
    """Lei 2, segunda metade: nenhuma senha autentica contra o dummy."""
    hasher = Argon2PasswordHasher()

    assert hasher.verify(tentativa, hasher.dummy_hash()) is False


def test_dummy_hash_e_estavel_na_mesma_instancia() -> None:
    """Computado uma vez no construtor, não a cada chamada.

    Recomputar pareceria inofensivo e reabriria o oráculo pelo outro lado: o
    caminho "e-mail inexistente" pagaria dois argon2 (derivar + verificar) contra
    um só do caminho "senha errada", e a diferença voltaria a distingui-los no
    relógio. A estabilidade do valor é o sintoma observável dessa decisão.
    """
    hasher = Argon2PasswordHasher()

    assert hasher.dummy_hash() is hasher.dummy_hash()

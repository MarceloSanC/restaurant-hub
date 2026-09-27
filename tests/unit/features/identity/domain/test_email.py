"""Testes do value object Email (domain/value_objects/email.py)."""

import pytest

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidEmailError
from restaurant_hub.features.identity.domain.value_objects import email as modulo_email
from restaurant_hub.features.identity.domain.value_objects.email import Email

pytestmark = pytest.mark.unit


def test_normaliza_espacos_e_caixa() -> None:
    assert Email("  Dono@Restaurante.COM  ").value == "dono@restaurante.com"


def test_igualdade_por_valor_apos_normalizacao() -> None:
    # VO compara por valor: duas grafias do mesmo e-mail são o mesmo Email.
    assert Email("Dono@Restaurante.com") == Email("  dono@restaurante.com  ")


def test_emails_diferentes_nao_sao_iguais() -> None:
    assert Email("a@b.com") != Email("c@d.com")


def test_e_hashavel_e_deduplica_por_valor() -> None:
    assert len({Email("a@b.com"), Email("A@B.COM")}) == 1


@pytest.mark.parametrize(
    "valido",
    [
        "dono@restaurante.com",
        "gerente.rh@grupo.com.br",
        "a@b.co",
        "com+tag@dominio.com",
    ],
)
def test_aceita_emails_bem_formados(valido: str) -> None:
    assert Email(valido).value == valido


@pytest.mark.parametrize(
    "invalido",
    [
        "",
        "   ",
        "sem-arroba",
        "@sem-local.com",
        "sem-dominio@",
        "sem@ponto",
        "com espaco@dominio.com",
        "a@dominio .com",
        "dois@@dominio.com",
    ],
)
def test_rejeita_email_malformado(invalido: str) -> None:
    with pytest.raises(InvalidEmailError) as excinfo:
        Email(invalido)
    mensagem = str(excinfo.value)
    assert "e-mail inválido" in mensagem
    # A mensagem precisa carregar o valor ofensivo original — não só o prefixo.
    assert repr(invalido) in mensagem


def test_terminador_de_linha_e_removido_e_nao_sobrevive_no_valor() -> None:
    # O `.strip()` corre antes da validação, então nenhum terminador chega ao
    # valor guardado — não há vetor de injeção por quebra de linha.
    assert Email("dono@cantina.com\n").value == "dono@cantina.com"
    assert Email("dono@cantina.com\r\n").value == "dono@cantina.com"


def test_quebra_de_linha_no_meio_e_rejeitada() -> None:
    with pytest.raises(InvalidEmailError):
        Email("dono@cantina.com\nEVIL")


def test_mensagem_de_erro_preserva_o_valor_nao_normalizado() -> None:
    # O relato tem que mostrar o que o usuário digitou (com espaços e maiúsculas),
    # não a versão normalizada — senão o diagnóstico engana.
    with pytest.raises(InvalidEmailError) as excinfo:
        Email("  A@B  ")
    assert "'  A@B  '" in str(excinfo.value)


# --- byte NUL (Stage 3.5, D8) ---------------------------------------------------


@pytest.mark.parametrize(
    "com_nul",
    [
        "fulano\x00@cantina.com",  # bem-formado para a regex — era o 500
        "\x00",
        "ana@cantina.com\x00",
        "\x00ana@cantina.com",
    ],
)
def test_rejeita_o_byte_nul_em_qualquer_posicao(com_nul: str) -> None:
    """A regex aceita NUL (a classe de espaço não o casa); o `psycopg` o recusa client-side.

    Medido no Checkpoint A da Stage 3.5: um e-mail bem-formado com NUL no meio
    construía e ia ao banco — 500 em três rotas de identity. A regra é do
    tamanho da divergência: só o NUL; acento, `+`, subdomínio continuam aceitos
    (ver `test_aceita_emails_bem_formados`).
    """
    with pytest.raises(InvalidEmailError):
        Email(com_nul)


def test_a_regex_sozinha_aceitaria_o_nul() -> None:
    """Documenta a **razão** da regra: sem a checagem explícita, a regex passa.

    Se um dia a regex mudar e passar a recusar NUL, este teste avisa que a
    checagem explícita virou redundante — e aí a decisão de removê-la é
    consciente, não acidental.
    """
    assert modulo_email._EMAIL_RE.match("fulano\x00@cantina.com") is not None

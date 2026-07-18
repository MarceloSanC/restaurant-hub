"""Testes do value object Email (domain/value_objects/email.py)."""

import pytest

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidEmailError
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
    with pytest.raises(InvalidEmailError, match="e-mail inválido"):
        Email(invalido)
